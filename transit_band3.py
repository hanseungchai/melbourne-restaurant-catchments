"""Band-3 transit pass (RCH-27): each band-3 diner's own bands 1-2 transit field, for staged best-of-K (SCR-23).

Band-3 hexes are the subject's drive-contestable hexes (the reach table's band-3 rows). Per hybrid window
(functions/transit_targeting.py, RCH-20 (2)), the populated band-3 hexes outside the subject pass's envelope for any
minute of the window are merged into flower points per stage band (config.REACH_BAND3_MERGE_PERSONS) and routed in
draws mode (P8r) to every venue hex, each point to its outermost band's max time (config.REACH_BAND3_MAX_TIME_MIN).
Hexes inside the envelope for every minute keep the subject pass's exact routes (read by the band-3 table, not here).

Writes one stamped folder (as reachability.py's passes, RCH-18): windows.csv, fields.csv (slot -> window and first
minute), and per window points.csv, members.csv, covered.csv and the routed times in long/ (band-2 points) and short/
(band-1-only points), resumable per origin file. The stamp holds the band-3 origins' hash, not the reach table's
folder, so a scoring edit does not discard the pass.
"""
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pyogrio

import config
import reachability
import scoring
from functions import reach_table, transit_reach, transit_targeting
from functions.output_helper import project_relative
from functions.subject_paths import subject_dir

WINDOWS_FILE = "windows.csv"
FIELDS_FILE = "fields.csv"
POINTS_FILE = "points.csv"
MEMBERS_FILE = "members.csv"
COVERED_FILE = "covered.csv"
SUMMARY_FILE = "summary.json"
WINDOW_DIR = "{}_{}_{}min"                      # day type, start HHMM, minutes (as the subject pass's chunks)
ROUTE_DIRS = {1: "short", 2: "long"}            # points whose outermost band is 1 / 2
HEX_COLUMNS = ["hex_id", "q", "r", "centroid_lat", "centroid_lon", "residents", "workers"]
CONFIG_NAMES = ["REACH_BAND3_MERGE_PERSONS", "REACH_BAND3_MAX_TIME_MIN", "REACH_HYBRID_WHOLE_DAY_TYPES",
                "REACH_HYBRID_SPAN_BREAKS", "REACH_HYBRID_WINDOW_MIN", "REACH_HYBRID_SEED", "REACH_SUBJECT_WINDOWS",
                "REACH_TRANSIT_CHUNK_MAX_MIN", "REACH_TRANSIT_WALK_SPEED_KMH", "REACH_TRANSIT_JAR_SHA256",
                "REACH_POPULATED_MIN_PERSONS", "REACH_ORIGINS_PER_FILE", "HOURS_SLOT_MIN"]


def band3_origins(subject_lat, subject_lon):
    """(populated band-3 hexes with q, r, centroid and persons; venue hexes (destinations); the subject pass's folder
    and chunk folders; the reach table folder)."""
    table_dir = scoring.build_reach_table(subject_lat, subject_lon)
    _, transit_dir, chunk_dirs = scoring.pass_folders(subject_lat, subject_lon)
    stamp = json.loads((transit_dir / config.REACH_STAMP_FILE).read_text(encoding="utf-8"))
    hex_df = pyogrio.read_dataframe(reachability.stamp_input_path(stamp, "hex_nodes"), read_geometry=False,
                                    columns=HEX_COLUMNS)
    hex_df["persons"] = hex_df.residents.fillna(0) + hex_df.workers.fillna(0)
    venue_hex_ids = (pd.read_csv(reachability.stamp_input_path(stamp, "venues_with_hex"), usecols=["hex_id"]).hex_id
                     .dropna().astype(np.int64).unique())
    destinations_df = hex_df[hex_df.hex_id.isin(venue_hex_ids)].sort_values("hex_id").reset_index(drop=True)
    subject_df = pd.read_parquet(table_dir / scoring.SUBJECT_TABLE_FILE, columns=[reach_table.BAND_COL,
                                                                                  reach_table.HEX_COL])
    band3_ids = subject_df.loc[subject_df[reach_table.BAND_COL] == reach_table.DRIVE_BAND, reach_table.HEX_COL]
    origins_df = hex_df[hex_df.hex_id.isin(band3_ids) & (hex_df.persons >= config.REACH_POPULATED_MIN_PERSONS)]
    origins_df = origins_df.sort_values("hex_id").reset_index(drop=True)
    return origins_df, destinations_df, transit_dir, chunk_dirs, table_dir


def band3_stamp(subject_lat, subject_lon, origins_df, transit_dir):
    origins_hash = hashlib.sha256(origins_df[["hex_id", "persons"]].to_numpy(np.float64).tobytes()).hexdigest()
    code = [Path(__file__), Path(transit_targeting.__file__), Path(transit_reach.__file__)]
    return {"kind": "transit band 3", "subject": [subject_lat, subject_lon],
            "subject_pass": project_relative(transit_dir), "origins": {"n": len(origins_df), "sha256": origins_hash},
            "config": {name: getattr(config, name) for name in CONFIG_NAMES},
            "code_sha256": {project_relative(path): reachability.file_sha256(path) for path in code},
            reachability.STAMP_COMMIT_KEY: reachability.git_commit()}


def band3_folder(subject_lat, subject_lon):
    """The current band-3 pass folder (as band3_pass names it; not made)."""
    origins_df, _, transit_dir, _, _ = band3_origins(subject_lat, subject_lon)
    stamp = band3_stamp(subject_lat, subject_lon, origins_df, transit_dir)
    return (subject_dir(config.REACHABILITY_DIR, subject_lat, subject_lon)
            / f"{config.REACH_BAND3_DIR_NAME}_{reachability.stamp_hash(stamp)}")


def route_points(network, jpype, out_dir, points_df, destinations_df, start, minutes, max_time_min):
    """reachability.route_chunk with the max time as an argument (that file is in the subject pass's stamp, so it is
    left as is): every point to every venue hex over the window, REACH_ORIGINS_PER_FILE points per parquet file
    (resume unit); origin_hex holds the point id. Returns (rows, wall seconds) of the files routed in this call."""
    import geopandas as gpd
    from shapely.geometry import Point
    destinations_gdf = gpd.GeoDataFrame(
        {"id": destinations_df.hex_id.to_numpy()}, crs=config.GEOGRAPHIC_CRS,
        geometry=gpd.points_from_xy(destinations_df.centroid_lon, destinations_df.centroid_lat))
    dest_hexes = destinations_df.hex_id.to_numpy()
    task = transit_reach.draws_task(network, destinations_gdf, start, minutes, max_time_min,
                                    config.REACH_TRANSIT_WALK_SPEED_KMH)
    transit_reach.set_report(jpype, minutes)
    n_rows, routed_s = 0, 0.0

    def route_point(point):
        by_iteration = transit_reach.origin_minutes(network._transport_network, task,
                                                    Point(point.centroid_lon, point.centroid_lat), minutes)
        return transit_reach.origin_rows(by_iteration, point.point_id, dest_hexes)

    out_dir.mkdir(parents=True, exist_ok=True)
    pool = ThreadPoolExecutor(max_workers=config.REACH_TRANSIT_THREADS)
    try:
        for file_no, first in enumerate(range(0, len(points_df), config.REACH_ORIGINS_PER_FILE)):
            path = out_dir / reachability.ORIGIN_FILE.format(file_no)
            if path.exists():
                continue
            tick = time.perf_counter()
            frames = list(pool.map(route_point, points_df.iloc[first:first + config.REACH_ORIGINS_PER_FILE]
                                   .itertuples()))
            frame = pd.concat(frames, ignore_index=True)
            partial = path.with_name(path.name + reachability.PARTIAL_SUFFIX)
            frame.to_parquet(partial, index=False, compression="zstd")
            partial.replace(path)
            n_rows += len(frame)
            routed_s += time.perf_counter() - tick
            print(f"    file {file_no}: {min(first + config.REACH_ORIGINS_PER_FILE, len(points_df)):,} of "
                  f"{len(points_df):,} points, {len(frame):,} rows, {time.perf_counter() - tick:.0f} s", flush=True)
    finally:
        pool.shutdown()
        transit_reach.clear_report(jpype)
    return n_rows, routed_s


def band3_pass(subject_lat, subject_lon, call_limit=None):
    """The band-3 pass (see the module docstring); returns its folder. call_limit: stop after this many routing calls
    (window x short / long; the timing run is 2)."""
    from functions import pt_network
    origins_df, destinations_df, transit_dir, chunk_dirs, _ = band3_origins(subject_lat, subject_lon)
    stamp = band3_stamp(subject_lat, subject_lon, origins_df, transit_dir)
    folder = reachability.pass_folder(config.REACH_BAND3_DIR_NAME, stamp, subject_lat, subject_lon)
    chunks = reachability.subject_chunks()
    windows, fields_df = transit_targeting.hybrid_windows(
        config.REACH_SUBJECT_WINDOWS, config.REACH_HYBRID_WHOLE_DAY_TYPES, config.REACH_HYBRID_SPAN_BREAKS,
        config.REACH_HYBRID_WINDOW_MIN, config.REACH_TRANSIT_CHUNK_MAX_MIN, config.HOURS_SLOT_MIN,
        config.REACH_HYBRID_SEED)
    window_rows = []
    for index, window in enumerate(windows):
        name = WINDOW_DIR.format(window["day_type"], window["start"].strftime("%H%M"), window["minutes"])
        cover = transit_targeting.covering_chunks(window, chunks)
        assert cover is not None, f"window {name} outside the subject pass's chunks"
        window_rows.append({"window": index, "dir": name, "day_type": window["day_type"],
                            "start": window["start"].isoformat(), "minutes": window["minutes"], "span": window["span"],
                            "subject_chunks": ";".join(f"{chunk_dirs[c].name}+{first}x{held}"
                                                       for c, first, held in cover)})
    windows_df = pd.DataFrame(window_rows)
    windows_df.to_csv(folder / WINDOWS_FILE, index=False)
    fields_df.to_csv(folder / FIELDS_FILE, index=False)
    assert set(fields_df.slot) >= {transit_targeting.slot_label(day_type, start + pd.Timedelta(minutes=offset))
                                   for day_type, _, start, minutes in chunks
                                   for offset in range(0, minutes, config.HOURS_SLOT_MIN)}, "a subject slot unread"

    plans = []                                       # (window row, window dir, band, points to route)
    for row in windows_df.itertuples():
        window_dir = folder / row.dir
        window_dir.mkdir(exist_ok=True)
        if not (window_dir / MEMBERS_FILE).exists():
            covered = None
            for part in row.subject_chunks.split(";"):
                envelope = set(pd.read_csv(transit_dir / part.split("+")[0] / reachability.ENVELOPE_FILE,
                                           usecols=["hex_id"]).hex_id)
                covered = envelope if covered is None else covered & envelope
            is_covered = origins_df.hex_id.isin(covered).to_numpy()
            points_df, members_df = transit_targeting.merged_points(origins_df[~is_covered],
                                                                    config.REACH_BAND3_MERGE_PERSONS)
            origins_df.loc[is_covered, ["hex_id"]].to_csv(window_dir / COVERED_FILE, index=False)
            points_df.to_csv(window_dir / POINTS_FILE, index=False)
            members_df.to_csv(window_dir / MEMBERS_FILE, index=False)
        points_df = pd.read_csv(window_dir / POINTS_FILE)
        for band in sorted(ROUTE_DIRS, reverse=True):
            plans.append((row, window_dir, band, points_df[points_df.max_band == band]))
    print(f"band-3 pass: {len(origins_df):,} populated band-3 hexes ({origins_df.persons.sum():,.0f} persons); "
          f"{len(windows_df)} windows, {len(fields_df.field.unique())} fields; points per call "
          f"{[len(p[3]) for p in plans]}", flush=True)

    jpype = transit_reach.start_jvm(config.REACH_TRANSIT_JAR_PATH, config.REACH_TRANSIT_JAR_SHA256,
                                    config.REACH_TRANSIT_R5_MAX_MEMORY)
    from r5py import TransportNetwork
    from r5py.util import Config as R5pyConfig
    pbf_path, gtfs_paths, _ = reachability.transit_network_paths()
    pt_network.check_r5py_working_copies([pbf_path, *gtfs_paths], Path(R5pyConfig().CACHE_DIR))
    network = TransportNetwork(pbf_path, gtfs_paths)
    n_calls = 0
    for row, window_dir, band, points_df in plans:
        out_dir = window_dir / ROUTE_DIRS[band]
        done_path = out_dir / reachability.CHUNK_DONE_FILE
        if done_path.exists():
            continue
        if call_limit is not None and n_calls >= call_limit:
            break
        start = pd.Timestamp(row.start).to_pydatetime()
        max_time = config.REACH_BAND3_MAX_TIME_MIN[band]
        print(f"  {row.dir} {ROUTE_DIRS[band]} ({max_time} min): routing {len(points_df):,} points", flush=True)
        n_rows, routed_s = route_points(network, jpype, out_dir, points_df, destinations_df, start, row.minutes,
                                        max_time)
        summary = {"window": row.dir, "band": band, "max_time_min": max_time, "points": len(points_df),
                   "rows_this_run": n_rows, "routed_s_this_run": round(routed_s),
                   "s_per_point_this_run": round(routed_s / max(len(points_df), 1), 4),
                   "bytes": sum(path.stat().st_size for path in out_dir.glob("times_*.parquet"))}
        done_path.write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
        print(f"  done: {json.dumps(summary)}", flush=True)
        n_calls += 1
    if all((window_dir / ROUTE_DIRS[band] / reachability.CHUNK_DONE_FILE).exists() for _, window_dir, band, _ in plans):
        summaries = [json.loads((window_dir / ROUTE_DIRS[band] / reachability.CHUNK_DONE_FILE).read_text())
                     for _, window_dir, band, _ in plans]
        (folder / SUMMARY_FILE).write_text(json.dumps({"calls": summaries}, indent=1), encoding="utf-8", newline="\n")
        print(f"band-3 pass done: {project_relative(folder)}", flush=True)
    return folder
