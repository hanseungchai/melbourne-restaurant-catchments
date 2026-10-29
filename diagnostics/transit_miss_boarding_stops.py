"""Can R5 reach the stop where Google boards, in time for Google's vehicle, on the stage-1 hard misses?

Claim under test (concepts/transit.md TRN-13 (d), stop linking; groups of the hard misses; reported): group 4
misses (R5 late: same line as Google, next vehicle; transit_hard_miss_itineraries.py) come from R5's walk to the
boarding stop, not from the timetable; and early misses that ride trains come from Google's longer station access.
Where it is used: whether a stop-linking or station-access fix is cheap and clear (TRN-13 plan (a): stretch only).

Method (Claude's): for each stage-1 miss (transit_hard_miss_range, no-wait plain, k = 2), Google's default's first
boarding stop (name, point) and its walk there (first walk step: metres, static seconds) from the raw answer.
R5 (4.16 km/h, walk only, the pair's release network) walks origin -> Google's stop point and origin -> the nearest
feed stop to it (within MATCH_RADIUS_M). The feed is searched for a departure at the stops within MATCH_RADIUS_M of
Google's stop, on WINDOW_DATE, within +-DEPARTURE_TOLERANCE_MIN of Google's board clock time, on a route whose short
name is Google's line name. "Reachable" = drawn minute + R5's walk to the feed stop + R5's 1-min board slack <= that
departure. Google's board clock time is read in local time; the feed's weekday timetable is assumed to match the
weekday Google answered for (both are weekdays inside the release).

Conclusion (run 2026-10-18): Google's vehicle found in the feed on 33/35. Group 4 (late, 7): R5's walk to
  Google's stop ~ Google's (ratio median 1.07); R5 misses the vehicle by ~1 min on 6 of 7, where Google itself
  boards with 0.1-0.6 min to spare: knife-edge connections at one moment (framing (c)), not stop linking. Groups
  1 / 2 / 3: Google's vehicle reachable in R5 on 5/5, 5/5, 12/14; R5 picks a faster option. Google's walk to
  underground loop stations is slow for its length (Parliament 236 m in 6.5 min, Melbourne Central 439 m in 9.7):
  in-station time Google counts and R5 does not (R5 reads no pathways.txt; the train feed has pathways for 225
  stations, traversal median 60 s, up to 1,800 s).

Inputs (read only): diagnostic_data/transit_hard_miss_range_*_misses.csv (newest); the Google raw answers in
outputs/transit_validation/; the cleaned feeds and OSM extract as transit_band_metric. Self-contained (D1). No API.
Usage: `python transit_miss_boarding_stops.py route 20261009`, `... route 20261016`, then `... report`.
"""
import datetime
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
CLEANED_DIRS = {"20261009": PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned",
                "20261016": DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016"}
NAME = "transit_miss_boarding_stops"
RANGE_NAME = "transit_hard_miss_range"
MISS_MODEL = "no-wait plain (reported)"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
RAW_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl",
             "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.raw.jsonl"}

R5_MAX_MEMORY = "7G"
WINDOW_DATE = datetime.date(2026, 10, 21)
WALK_SPEED_KMH = 4.16
MAX_WALK_MIN = 60
BOARD_SLACK_MIN = 1
SINGLE_PERCENTILE = 49
MATCH_RADIUS_M = 150
DEPARTURE_TOLERANCE_MIN = 3
EARTH_RADIUS_M = 6_371_008.8
SECONDS_PER_MIN = 60
MIN_PER_HOUR = 60
GTFS_ENCODING = "utf-8-sig"
LOCAL_TZ = "Australia/Melbourne"
WEEKDAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EXCEPTION_ADDED, EXCEPTION_REMOVED = 1, 2


def misses():
    misses_df = pd.read_csv(sorted(DIAGNOSTIC_DATA_DIR.glob(f"{RANGE_NAME}_*_misses.csv"))[-1])
    return misses_df[misses_df.model == MISS_MODEL].drop_duplicates(["set_name", "draw_no"])


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def google_boardings(misses_df):
    """Google's default: first boarding stop, line, board time, and the walk before it."""
    rows = []
    for set_name, path in RAW_PATHS.items():
        wanted = set(misses_df.draw_no[misses_df.set_name == set_name])
        with open(path, encoding="utf-8") as file:
            for line in file:
                record = json.loads(line)
                if record["draw_no"] not in wanted:
                    continue
                steps = record["resp"]["routes"][0]["legs"][0]["steps"]
                first = next((i for i, step in enumerate(steps) if step.get("travelMode") == "TRANSIT"), None)
                if first is None:
                    rows.append({"set_name": set_name, "draw_no": record["draw_no"], "google_walk_only": True})
                    continue
                details = steps[first]["transitDetails"]
                stop = details["stopDetails"]["departureStop"]
                walk_steps = steps[:first]
                board_local = pd.Timestamp(details["stopDetails"]["departureTime"]).tz_convert(LOCAL_TZ)
                rows.append({"set_name": set_name, "draw_no": record["draw_no"], "google_walk_only": False,
                             "stop_name": stop.get("name", ""), "stop_lat": stop["location"]["latLng"]["latitude"],
                             "stop_lon": stop["location"]["latLng"]["longitude"],
                             "line": details.get("transitLine", {}).get("nameShort") or details.get("transitLine", {}).get("name", ""),
                             "vehicle": details.get("transitLine", {}).get("vehicle", {}).get("type", ""),
                             "board_min_of_day": board_local.hour * MIN_PER_HOUR + board_local.minute,
                             "google_walk_m": sum(step.get("distanceMeters", 0) for step in walk_steps),
                             "google_walk_s": sum(float(step.get("staticDuration", "0s").rstrip("s")) for step in walk_steps)})
    return pd.DataFrame(rows)


def feed_tables(release):
    stops, departures = [], []
    for feed_name in FEED_NAMES:
        with zipfile.ZipFile(CLEANED_DIRS[release] / f"{feed_name}.zip") as gtfs_zip:
            stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype={"stop_id": str}, encoding=GTFS_ENCODING,
                                   usecols=["stop_id", "stop_name", "stop_lat", "stop_lon"])
            stops.append(stops_df.assign(feed=feed_name))
    return pd.concat(stops, ignore_index=True), departures


def active_services(gtfs_zip):
    date_int = int(f"{WINDOW_DATE:%Y%m%d}")
    calendar_df = pd.read_csv(gtfs_zip.open("calendar.txt"), dtype={"service_id": str}, encoding=GTFS_ENCODING)
    services = set(calendar_df.service_id[(calendar_df[WEEKDAY_COLUMNS[WINDOW_DATE.weekday()]] == 1)
                                          & (calendar_df.start_date <= date_int) & (calendar_df.end_date >= date_int)])
    if "calendar_dates.txt" in gtfs_zip.namelist():
        dates_df = pd.read_csv(gtfs_zip.open("calendar_dates.txt"), dtype={"service_id": str}, encoding=GTFS_ENCODING)
        dates_df = dates_df[dates_df.date == date_int]
        services |= set(dates_df.service_id[dates_df.exception_type == EXCEPTION_ADDED])
        services -= set(dates_df.service_id[dates_df.exception_type == EXCEPTION_REMOVED])
    return services


def departures_near(release, stops_df, near_stop_rows):
    """Departures on WINDOW_DATE at the given stops (feed, stop_id), with route short names."""
    frames = []
    for feed_name in FEED_NAMES:
        feed_stops = set(near_stop_rows.stop_id[near_stop_rows.feed == feed_name])
        if not feed_stops:
            continue
        with zipfile.ZipFile(CLEANED_DIRS[release] / f"{feed_name}.zip") as gtfs_zip:
            services = active_services(gtfs_zip)
            trips_df = pd.read_csv(gtfs_zip.open("trips.txt"), dtype=str, usecols=["trip_id", "route_id", "service_id"], encoding=GTFS_ENCODING)
            trips_df = trips_df[trips_df.service_id.isin(services)]
            routes_df = pd.read_csv(gtfs_zip.open("routes.txt"), dtype=str, encoding=GTFS_ENCODING, usecols=["route_id", "route_short_name", "route_long_name"])
            kept = []
            for chunk in pd.read_csv(gtfs_zip.open("stop_times.txt"), dtype=str, encoding=GTFS_ENCODING,
                                     usecols=["trip_id", "departure_time", "stop_id"], chunksize=2_000_000):
                kept.append(chunk[chunk.stop_id.isin(feed_stops)])
        times_df = pd.concat(kept).merge(trips_df, on="trip_id").merge(routes_df, on="route_id")
        parts = times_df.departure_time.str.split(":", expand=True).astype(int)
        times_df["dep_min"] = parts[0] * MIN_PER_HOUR + parts[1] + parts[2] / SECONDS_PER_MIN
        frames.append(times_df.assign(feed=feed_name))
    return pd.concat(frames, ignore_index=True)


def route(release):
    sys.argv += ["--max-memory", R5_MAX_MEMORY]
    import geopandas as gpd
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    from sklearn.neighbors import BallTree

    misses_df = misses()
    misses_df = misses_df[misses_df.release.astype(int).astype(str) == release]
    boardings_df = google_boardings(misses_df).merge(
        misses_df[["set_name", "draw_no", "origin_lat", "origin_lon", "dep_min_of_day", "group", "test"]], on=["set_name", "draw_no"])
    boardings_df = boardings_df[~boardings_df.google_walk_only].reset_index(drop=True)
    stops_df, _ = feed_tables(release)
    tree = BallTree(np.radians(stops_df[["stop_lat", "stop_lon"]].to_numpy()), metric="haversine")
    near_lists = tree.query_radius(np.radians(boardings_df[["stop_lat", "stop_lon"]].to_numpy()), r=MATCH_RADIUS_M / EARTH_RADIUS_M)
    departures_df = departures_near(release, stops_df, stops_df.iloc[np.unique(np.concatenate(near_lists))])
    network = TransportNetwork(PBF_PATH, [CLEANED_DIRS[release] / f"{name}.zip" for name in FEED_NAMES])

    def walk_min(lat, lon, to_lat, to_lon):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([lon], [lat]))
        destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([to_lon], [to_lat]))
        matrix_df = pd.DataFrame(TravelTimeMatrix(network, origins=origins, destinations=destinations,
                                                  departure=datetime.datetime.combine(WINDOW_DATE, datetime.time(12)),
                                                  transport_modes=[TransportMode.WALK], percentiles=[SINGLE_PERCENTILE],
                                                  max_time=datetime.timedelta(minutes=MAX_WALK_MIN), speed_walking=WALK_SPEED_KMH))
        return matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]

    rows = []
    for i, board in boardings_df.iterrows():
        near_df = stops_df.iloc[near_lists[i]].copy()
        near_df["distance_m"] = haversine_m(board.stop_lat, board.stop_lon, near_df.stop_lat.to_numpy(), near_df.stop_lon.to_numpy())
        candidates = departures_df.merge(near_df[["feed", "stop_id", "stop_name", "distance_m", "stop_lat", "stop_lon"]], on=["feed", "stop_id"])
        is_line = (candidates.route_short_name.fillna("").str.strip() == str(board.line).strip()) | \
                  candidates.route_long_name.fillna("").str.contains(str(board.line), regex=False)
        is_time = (candidates.dep_min - board.board_min_of_day).abs() <= DEPARTURE_TOLERANCE_MIN
        match_df = candidates[is_line & is_time].sort_values(["distance_m", "dep_min"])
        row = board.to_dict()
        row["straight_m"] = haversine_m(board.origin_lat, board.origin_lon, board.stop_lat, board.stop_lon)
        row["r5_walk_to_google_stop_min"] = walk_min(board.origin_lat, board.origin_lon, board.stop_lat, board.stop_lon)
        row["n_line_departures_near"] = int(is_line.sum())
        if not match_df.empty:
            match = match_df.iloc[0]
            row.update({"feed_stop": match.stop_name, "feed_stop_m": round(match.distance_m), "feed_dep_min": match.dep_min,
                        "r5_walk_to_feed_stop_min": walk_min(board.origin_lat, board.origin_lon, match.stop_lat, match.stop_lon)})
        rows.append(row)
        print(f"  {board.set_name} {board.draw_no} done", flush=True)
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_stops_{release}.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"saved {path.name}")


def report():
    run_date = f"{datetime.date.today():%Y%m%d}"
    df = pd.concat([pd.read_csv(sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_stops_{release}.csv"))[-1]) for release in CLEANED_DIRS],
                   ignore_index=True)
    df["google_walk_min"] = df.google_walk_s / SECONDS_PER_MIN
    df["ready_min"] = df.dep_min_of_day + df.r5_walk_to_feed_stop_min + BOARD_SLACK_MIN
    df["is_reachable"] = df.ready_min <= df.feed_dep_min
    df["walk_ratio"] = df.r5_walk_to_google_stop_min / df.google_walk_min
    lines = [f"{NAME} {run_date}: R5's walk to Google's boarding stop on the stage-1 misses ({MISS_MODEL}); "
             f"{len(df)} riding defaults; Google's vehicle found in the feed (line, +-{DEPARTURE_TOLERANCE_MIN} min, "
             f"<= {MATCH_RADIUS_M} m) on {int(df.feed_dep_min.notna().sum())}"]
    columns = ["set_name", "draw_no", "group", "test", "vehicle", "line", "stop_name", "straight_m", "google_walk_m", "google_walk_min",
               "r5_walk_to_google_stop_min", "walk_ratio", "feed_stop_m", "feed_dep_min", "board_min_of_day", "ready_min", "is_reachable"]
    with pd.option_context("display.width", 300, "display.max_columns", 30, "display.max_colwidth", 28, "display.precision", 1):
        lines.append(df.sort_values(["group", "draw_no"])[columns].to_string(index=False))
    for group, group_df in df.groupby("group"):
        lines.append(f"{group}: n {len(group_df)}; R5 walk / Google walk to Google's stop median {group_df.walk_ratio.median():.2f}; "
                     f"Google's vehicle reachable in R5 {int(group_df.is_reachable.sum())}/{int(group_df.feed_dep_min.notna().sum())}")
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "route":
        route(sys.argv[2])
    else:
        report()
