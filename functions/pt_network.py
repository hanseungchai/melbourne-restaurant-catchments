"""PT network helpers: GTFS feed copies and checks on an r5py build and its log (construct_pt_graph)."""
import csv
import hashlib
import re
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

GTFS_TABLE_SUFFIX = ".txt"
GTFS_STOPS_TABLE = "stops.txt"
GTFS_ROUTES_TABLE = "routes.txt"
GTFS_TEXT_ENCODING = "utf-8-sig"          # PTV tables may carry a byte-order mark
GTFS_FILE_ENCODING = "utf-8"              # decodes and re-encodes a table with its byte-order mark kept
BYTE_ORDER_MARK = "﻿"
MAX_LINES_EMPTY_TABLE = 1                 # header only, or blank

# R5 log messages (R5's own wording) the build summary searches for.
LOG_MESSAGE_SEPARATOR = " - "             # R5 log lines: "<timestamp> [thread] LEVEL logger - <message>"
LOG_SUMMARY_KEYS = ["zero-duration hops found", "errors in feed", "Done creating", "time zone set to"]
LOG_COUNT_KEYS = ["zero-duration", "Done creating", "errors in feed", "Using file name", "google_transit", "ptv_"]
LOG_UNLINKED_KEY = "has not been linked"
LOG_UNLINKED_STOP_PATTERN = r"Stop (\d+) has not been linked"
LOG_SKIPPED_TRIP_PATTERN = r"negative|[Ss]kipping trip"
LOG_ERROR_KEY = " ERROR "
LOG_RESTRICTION_KEY = "Restriction"       # OSM turn-restriction errors: expected, not counted
LOG_SKIPPED_TRIP_PRINT_LIMIT = 10
LOG_MESSAGE_PRINT_CHARS = 60
LOG_LINE_PRINT_CHARS = 120

R5_FEED_STOP_SEPARATOR = ":"              # R5 stop ids are "<feed>:<stop_id>", e.g. "ptv_metro_bus:12345"


def excluded_route_type_rows(gtfs_path: Path, excluded_route_types: list[int]) -> dict[str, tuple[str, set[str]]]:
    """Rows to leave out for the excluded route types, as {table: (key column, key values to drop)}.

    Drops the routes, their trips and stop_times, and the stops no kept trip serves. Shapes and
    calendars only those trips use stay; R5 ignores rows no trip refers to.
    """
    with zipfile.ZipFile(gtfs_path) as gtfs_zip:
        routes_df = pd.read_csv(gtfs_zip.open("routes.txt"), dtype={"route_id": str})
        excluded_route_ids = set(routes_df.route_id[routes_df.route_type.isin(excluded_route_types)])
        if not excluded_route_ids:
            return {}
        trips_df = pd.read_csv(gtfs_zip.open("trips.txt"), dtype=str, usecols=["route_id", "trip_id"])
        excluded_trip_ids = set(trips_df.trip_id[trips_df.route_id.isin(excluded_route_ids)])
        stop_times_df = pd.read_csv(gtfs_zip.open("stop_times.txt"), dtype=str, usecols=["trip_id", "stop_id"])
    is_excluded_stop_time = stop_times_df.trip_id.isin(excluded_trip_ids)
    excluded_stop_ids = set(stop_times_df.stop_id[is_excluded_stop_time]) - set(stop_times_df.stop_id[~is_excluded_stop_time])
    return {"routes.txt": ("route_id", excluded_route_ids),
            "trips.txt": ("trip_id", excluded_trip_ids),
            "stop_times.txt": ("trip_id", excluded_trip_ids),
            "stops.txt": ("stop_id", excluded_stop_ids)}


def drop_table_rows(table_text: str, key_column: str, drop_keys: set[str]) -> tuple[str, int]:
    """A GTFS table's text without the rows whose key_column value is in drop_keys; kept lines are untouched.

    Returns the new text and the number of rows dropped.
    """
    lines = table_text.splitlines(keepends=True)
    header_fields = next(csv.reader([lines[0].lstrip(BYTE_ORDER_MARK)]))
    key_index = header_fields.index(key_column)
    data_lines = lines[1:]
    parsed_rows = list(csv.reader(data_lines))
    assert len(parsed_rows) == len(data_lines), "a quoted field spans lines; line-wise filtering would misalign"
    kept_lines = [line for line, row in zip(data_lines, parsed_rows) if row[key_index] not in drop_keys]
    return "".join([lines[0]] + kept_lines), len(data_lines) - len(kept_lines)


def copy_gtfs_dropping_empty(src_path: Path, dst_path: Path,
                             rows_to_drop: dict[str, tuple[str, set[str]]] | None = None) -> list[str]:
    """Copy a GTFS zip, leaving out tables with no rows (R5 fails on header-only tables).

    rows_to_drop ({table: (key column, key values)}, from excluded_route_type_rows) also leaves out
    those rows, and prints how many went per table. Returns the names of the tables left out.
    """
    rows_to_drop = rows_to_drop or {}
    dropped_tables = []
    with zipfile.ZipFile(src_path) as zip_in, zipfile.ZipFile(dst_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
        for item in zip_in.infolist():
            table_bytes = zip_in.read(item.filename)
            nonblank_lines = [line for line in table_bytes.decode(GTFS_TEXT_ENCODING).splitlines() if line.strip()]
            if item.filename.endswith(GTFS_TABLE_SUFFIX) and len(nonblank_lines) <= MAX_LINES_EMPTY_TABLE:
                dropped_tables.append(item.filename)
                continue
            if item.filename in rows_to_drop:
                key_column, drop_keys = rows_to_drop[item.filename]
                table_text, dropped_row_count = drop_table_rows(table_bytes.decode(GTFS_FILE_ENCODING), key_column, drop_keys)
                table_bytes = table_text.encode(GTFS_FILE_ENCODING)
                print(f"{src_path.parent.name}/{item.filename}: dropped {dropped_row_count} rows")
            zip_out.writestr(item, table_bytes)
    return dropped_tables


def file_sha256(path: Path) -> str:
    """The file's SHA-256 hex digest."""
    with open(path, "rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def check_r5py_working_copies(input_paths: list[Path], r5py_cache_dir: Path) -> None:
    """Stop if r5py's cache holds a different file under an input's name.

    r5py builds from a copy of each input in its cache folder, made only when no file of that name is
    there yet (r5py.util.WorkingCopy, on Windows). A changed input under an old name would otherwise be
    ignored silently, and the cached network of the old inputs loaded instead.
    """
    stale_copies = [r5py_cache_dir / path.name for path in input_paths
                    if (r5py_cache_dir / path.name).exists()
                    and file_sha256(r5py_cache_dir / path.name) != file_sha256(path)]
    if stale_copies:
        raise RuntimeError(f"r5py's cache holds stale copies of changed inputs: {[str(path) for path in stale_copies]}. "
                           "Rename or remove them, then rerun.")


def read_log_lines(log_path: Path) -> list[str]:
    """The build log's lines, undecodable bytes skipped."""
    with open(log_path, encoding="utf-8", errors="ignore") as log_file:
        return log_file.read().splitlines()


def unlinked_stop_indices(log_lines: list[str]) -> set[int]:
    """R5 stop indices the log reports as not linked to the street network."""
    return {int(match.group(1)) for line in log_lines
            if (match := re.search(LOG_UNLINKED_STOP_PATTERN, line))}


def print_log_summary(log_lines: list[str]) -> None:
    """Print the build log's feed messages, unlinked-stop count, skipped trips, errors and key counts."""
    for key in LOG_SUMMARY_KEYS:
        for line in log_lines:
            if key in line:
                print(line.split(LOG_MESSAGE_SEPARATOR, 1)[-1])
    print("unlinked stops:", sum(LOG_UNLINKED_KEY in line for line in log_lines))
    print("skip/negative (non-restriction):",
          [line for line in log_lines if re.search(LOG_SKIPPED_TRIP_PATTERN, line)][:LOG_SKIPPED_TRIP_PRINT_LIMIT])
    print("other ERRORs:", Counter(line.split(LOG_MESSAGE_SEPARATOR, 1)[-1][:LOG_MESSAGE_PRINT_CHARS]
                                   for line in log_lines
                                   if LOG_ERROR_KEY in line and LOG_RESTRICTION_KEY not in line))

    print(len(log_lines), "lines")
    print("first:", log_lines[0][:LOG_LINE_PRINT_CHARS])
    print("last:", log_lines[-1][:LOG_LINE_PRINT_CHARS])
    for key in LOG_COUNT_KEYS:
        print(key, sum(key in line for line in log_lines))


def is_outside_extent(stops_df: pd.DataFrame, extent_bounds: tuple) -> pd.Series:
    """True for stops outside the (west, south, east, north) extent."""
    west_lon, south_lat, east_lon, north_lat = extent_bounds
    return ~stops_df.stop_lon.between(west_lon, east_lon) | ~stops_df.stop_lat.between(south_lat, north_lat)


def read_feed_stops_df(gtfs_path: Path, **read_csv_kwargs) -> pd.DataFrame:
    """A GTFS zip's stops table."""
    with zipfile.ZipFile(gtfs_path) as gtfs_zip:
        return pd.read_csv(gtfs_zip.open(GTFS_STOPS_TABLE), **read_csv_kwargs)


def read_feed_routes_df(gtfs_path: Path, **read_csv_kwargs) -> pd.DataFrame:
    """A GTFS zip's routes table."""
    with zipfile.ZipFile(gtfs_path) as gtfs_zip:
        return pd.read_csv(gtfs_zip.open(GTFS_ROUTES_TABLE), **read_csv_kwargs)


def print_stops_outside_extent(gtfs_paths: list[Path], extent_bounds: tuple) -> None:
    """Print each feed's stop count and how many stops fall outside the built street network's extent."""
    total_stops = total_outside = 0
    for gtfs_path in gtfs_paths:
        stops_df = read_feed_stops_df(gtfs_path)
        outside_count = is_outside_extent(stops_df, extent_bounds).sum()
        print(gtfs_path.name, len(stops_df), "stops,", outside_count, "outside extent")
        total_stops += len(stops_df)
        total_outside += outside_count
    print("total", total_stops, "outside", total_outside)


def unlinked_stops_df(transit_layer, unlinked_indices: set[int]) -> pd.DataFrame:
    """Unlinked stops as R5 index, full R5 id, feed and GTFS stop_id.

    transit_layer is R5's Java TransitLayer (TransportNetwork._transport_network.transitLayer).
    """
    sorted_indices = sorted(unlinked_indices)
    full_ids = [str(transit_layer.stopIdForIndex.get(stop_index)) for stop_index in sorted_indices]
    feed_stop_pairs = [full_id.split(R5_FEED_STOP_SEPARATOR, 1) for full_id in full_ids]   # empty when none unlinked
    return pd.DataFrame({"r5_idx": sorted_indices, "full_id": full_ids,
                         "feed": [feed for feed, _ in feed_stop_pairs],
                         "stop_id": [stop_id for _, stop_id in feed_stop_pairs]})


def print_unlinked_inside_extent(unlinked_df: pd.DataFrame, gtfs_paths: list[Path], extent_bounds: tuple) -> None:
    """Print how many unlinked stops lie inside the extent, by feed and by GTFS location_type."""
    stop_frames = []
    for gtfs_path in gtfs_paths:
        stops_df = read_feed_stops_df(gtfs_path, dtype={"stop_id": str})
        stops_df["feed"] = gtfs_path.stem
        stop_frames.append(stops_df)
    all_stops_df = pd.concat(stop_frames)

    unlinked_stops_located_df = unlinked_df.merge(all_stops_df, on=["feed", "stop_id"], how="left")
    inside_df = unlinked_stops_located_df[~is_outside_extent(unlinked_stops_located_df, extent_bounds)]
    print(len(inside_df), inside_df.feed.value_counts().to_dict())
    print(inside_df.get("location_type", pd.Series()).value_counts(dropna=False).to_dict())
