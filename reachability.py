"""Reachability pass (RCH-1..26): drive band 3 for every venue hex; transit bands 1-2 for the subject's envelope.

Each pass writes into its own folder under config.REACHABILITY_DIR, named by the hash of its build stamp (RCH-18):
inputs (paths, mtimes, hashes), the config values used and the code that computes it. A rerun reuses saved files only
inside a folder whose stamp matches; the git commit is recorded in the stamp but kept out of its hash, so a commit
alone does not discard a pass. The drive pass is stamped apart from the GTFS release (RCH-18).
"""
import datetime
import hashlib
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pyogrio

import config
from functions import reachability_drive
from functions.output_helper import project_relative
from functions.routing_bundle import prepared_path
from functions.subject_paths import (subject_dir, subject_file, subject_layers_file, timed_graph_path,
                                     venues_tags)

PARAMS_FILE = "{}_{}_params.json"            # as pathing_calibration (model, pairs)
STAMP_COMMIT_KEY = "commit"                  # recorded, not hashed
DRIVE_MANIFEST_FILE = "manifest.csv"
DRIVE_SUMMARY_FILE = "summary.txt"
DRIVE_COORDS_FILE = "node_coords.npz"
DRIVE_BATCH_FILE = "costs_{:03d}.parquet"
PARTIAL_SUFFIX = ".partial"
HEX_NODE_COLUMNS = [reachability_drive.HEX_ID_COL, reachability_drive.DRIVE_NODE_1_COL,
                    reachability_drive.DRIVE_NODE_2_COL, reachability_drive.DRIVE_ROAD_DIST_1_COL,
                    reachability_drive.DRIVE_ROAD_DIST_2_COL]
SECONDS_PER_MIN = 60
BYTES_PER_GB = 1e9


def file_sha256(path):
    with open(path, "rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def file_record(path):
    """Path (project-relative), mtime and size of an input; directories by their newest member."""
    path = Path(path)
    members = [p for p in path.rglob("*") if p.is_file()] if path.is_dir() else [path]
    return {"path": project_relative(path), "mtime": max(p.stat().st_mtime for p in members),
            "bytes": sum(p.stat().st_size for p in members)}


def git_commit():
    result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=config.PROJECT_ROOT)
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=config.PROJECT_ROOT)
    return result.stdout.strip() + (" (uncommitted changes)" if dirty.stdout.strip() else "")


def stamp_hash(stamp):
    hashed = {key: value for key, value in stamp.items() if key != STAMP_COMMIT_KEY}
    return hashlib.sha256(json.dumps(hashed, sort_keys=True, default=str).encode()).hexdigest()[
        :config.REACH_STAMP_HASH_CHARS]


def pass_folder(kind, stamp, subject_lat, subject_lon):
    """The pass's folder (made if new) with its stamp written; an existing folder must hold the same stamp."""
    folder = subject_dir(config.REACHABILITY_DIR, subject_lat, subject_lon) / f"{kind}_{stamp_hash(stamp)}"
    stamp_path = folder / config.REACH_STAMP_FILE
    if stamp_path.exists():
        saved = json.loads(stamp_path.read_text(encoding="utf-8"))
        assert stamp_hash(saved) == stamp_hash(stamp), f"{stamp_path}: stamp differs from its folder name"
        print(f"{kind} pass: resuming in {project_relative(folder)} (stamp matches; saved commit "
              f"{saved[STAMP_COMMIT_KEY]})")
    else:
        folder.mkdir(parents=True, exist_ok=True)
        stamp_path.write_text(json.dumps(stamp, indent=1, default=str), encoding="utf-8", newline="\n")
        print(f"{kind} pass: new folder {project_relative(folder)}")
    return folder


# --- drive, band 3 ---------------------------------------------------------------------------------
def drive_inputs(subject_lat, subject_lon):
    graph_path = timed_graph_path(config.DRIVE_FIT_BASE_VARIANT, subject_lat, subject_lon)
    return {"graph": graph_path,
            "bundle": prepared_path(graph_path, config.DRIVE_RUN_BETAS[config.DRIVE_FIT_BASE_VARIANT]),
            "attrs": subject_layers_file(config.DRIVE_FIT_EDGE_ATTRS_PATH, subject_lat, subject_lon),
            "params": subject_dir(config.DRIVE_MODEL_DIR, subject_lat, subject_lon)
            / PARAMS_FILE.format(config.DRIVE_MODEL_NAME, config.REACH_DRIVE_MODEL_PAIRS),
            "hex_nodes": subject_layers_file(config.HEX_NODES_PATH, subject_lat, subject_lon),
            "venues_with_hex": subject_file(config.VENUES_WITH_HEX_PATH, subject_lat, subject_lon, venues_tags())}


def drive_stamp(inputs):
    code = [Path(reachability_drive.__file__)]       # not this stage file: transit edits keep the drive pass
    return {"kind": "drive band 3", "inputs": {name: file_record(path) for name, path in inputs.items()},
            "params_sha256": file_sha256(inputs["params"]),
            "config": {"DRIVE_BAND_DURATION_MIN": config.DRIVE_BAND_DURATION_MIN,
                       "DRIVE_MODEL_NAME": config.DRIVE_MODEL_NAME,
                       "REACH_DRIVE_MODEL_PAIRS": config.REACH_DRIVE_MODEL_PAIRS,
                       "REACH_DRIVE_STORAGE_FACTOR": config.REACH_DRIVE_STORAGE_FACTOR,
                       "REACH_DRIVE_BATCH_HEXES": config.REACH_DRIVE_BATCH_HEXES,
                       "REACH_EDGE_FLAG_M": config.REACH_EDGE_FLAG_M,
                       "CANDIDATE_TIE_WINDOW_M": config.CANDIDATE_TIE_WINDOW_M},
            "code_sha256": {project_relative(path): file_sha256(path) for path in code},
            STAMP_COMMIT_KEY: git_commit()}


def drive_pass(subject_lat, subject_lon, hex_limit=None):
    """Band 3 for every venue hex (RCH-15..17): node-level routed costs to REACH_DRIVE_STORAGE_FACTOR x the routed
    cut, one parquet per batch of venue hexes (resumable), a manifest with the edge flag (Q5) and a summary.
    hex_limit: route only the first n venue hexes (a check run, own stamp)."""
    inputs = drive_inputs(subject_lat, subject_lon)
    stamp = drive_stamp(inputs)
    stamp["hex_limit"] = hex_limit
    folder = pass_folder("drive", stamp, subject_lat, subject_lon)
    started = time.perf_counter()
    reverse, nodes, params = reachability_drive.fitted_reverse_matrix(inputs["bundle"], inputs["attrs"],
                                                                      inputs["params"])
    band_cut_s = config.DRIVE_BAND_DURATION_MIN * SECONDS_PER_MIN / params["alpha"]   # RCH-2: predicted = ALPHA x routed
    limit_s = config.REACH_DRIVE_STORAGE_FACTOR * band_cut_s
    hex_df = pyogrio.read_dataframe(inputs["hex_nodes"], read_geometry=False, columns=HEX_NODE_COLUMNS)
    row_1, row_2 = reachability_drive.eligible_rows(hex_df, nodes)
    venue_hex_ids = (pd.read_csv(inputs["venues_with_hex"], usecols=[reachability_drive.HEX_ID_COL])
                     [reachability_drive.HEX_ID_COL].dropna().astype(np.int64).unique())
    sources = reachability_drive.venue_hex_sources(hex_df, venue_hex_ids, row_1, row_2)[:hex_limit]
    del hex_df
    lat, lon = reachability_drive.node_coordinates(inputs["graph"], nodes, folder / DRIVE_COORDS_FILE)
    boundary, n_hull = reachability_drive.boundary_rows(lat, lon, config.REACH_EDGE_FLAG_M)
    print(f"drive pass: {reverse.shape[0]:,} nodes, ALPHA {params['alpha']:.4f}, routed cut {band_cut_s:.1f} s, "
          f"stored to {limit_s:.1f} s; {len(sources):,} venue hexes; {len(boundary):,} boundary nodes (hull "
          f"{n_hull} corners); load {time.perf_counter() - started:.0f} s", flush=True)

    manifest_parts = []
    for batch_no, start in enumerate(range(0, len(sources), config.REACH_DRIVE_BATCH_HEXES)):
        batch_path = folder / DRIVE_BATCH_FILE.format(batch_no)
        manifest_path = batch_path.with_suffix(".manifest.csv")
        if batch_path.exists() and manifest_path.exists():
            manifest_parts.append(pd.read_csv(manifest_path))
            continue
        tick = time.perf_counter()
        partial_path = batch_path.with_name(batch_path.name + PARTIAL_SUFFIX)
        records = reachability_drive.search_venue_hexes(
            reverse, sources[start:start + config.REACH_DRIVE_BATCH_HEXES], limit_s, partial_path, boundary,
            reachability_drive.stored_schema())
        partial_path.replace(batch_path)
        batch_df = pd.DataFrame(records)
        batch_df.to_csv(manifest_path, index=False)
        manifest_parts.append(batch_df)
        print(f"  batch {batch_no}: {len(batch_df)} hexes, {batch_df.n_nodes.sum():,} rows, "
              f"{batch_path.stat().st_size / BYTES_PER_GB:.2f} GB, {time.perf_counter() - tick:.0f} s", flush=True)
    manifest_df = pd.concat(manifest_parts, ignore_index=True)
    manifest_df.to_csv(folder / DRIVE_MANIFEST_FILE, index=False)
    disk_gb = sum(path.stat().st_size for path in folder.glob("costs_*.parquet")) / BYTES_PER_GB
    lines = [f"drive pass {datetime.date.today():%Y-%m-%d}: {len(manifest_df):,} venue hexes, "
             f"{manifest_df.n_nodes.sum():,} node rows, {disk_gb:.1f} GB; routed cut {band_cut_s:.1f} s, stored to "
             f"{limit_s:.1f} s ({config.REACH_DRIVE_STORAGE_FACTOR}x)",
             f"edge flag (Q5, {config.REACH_EDGE_FLAG_M} m from the hull of {n_hull} corners): "
             f"{int(manifest_df.is_edge.sum()):,} venue hexes flagged; flagged hexes' cheapest boundary node median "
             f"{manifest_df.min_boundary_cost_s.median():.0f} s",
             f"rows per hex: median {manifest_df.n_nodes.median():,.0f}, max {manifest_df.n_nodes.max():,}"]
    (folder / DRIVE_SUMMARY_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    return folder


# --- transit network, bands 1-2 ---------------------------------------------------------------------
NETWORK_SUMMARY_FILE = "network_summary.json"
NETWORK_TAG = "reach"                         # in every input file name: r5py caches inputs by name (TRN-2)
DERIVED_PBF_FILE = "osm_pathways_{}_{}.osm.pbf"
FEED_FILE = "{}_{}_{}.zip"
MOVED_FEED_FILE = "{}_{}_{}_moved.zip"
SPURS_FILE = "spurs_{}.csv"
HUBS_FILE = "hubs_{}.csv"


def transit_network_paths(release=None):
    """(derived extract, [train (moved), tram, bus feeds], network folder) for a release (default: config's)."""
    release = release or config.REACH_GTFS_RELEASE
    folder = config.REACH_NETWORK_DIR / release
    gtfs = [folder / (MOVED_FEED_FILE if name == config.REACH_TRAIN_FEED else FEED_FILE).format(name, NETWORK_TAG,
                                                                                                release)
            for name in config.REACH_GTFS_SOURCE_PATHS]
    return folder / DERIVED_PBF_FILE.format(NETWORK_TAG, release), gtfs, folder


def build_transit_network(should_rebuild=False):
    """The release's feeds cleaned as construct_pt_graph cleans them (TRN-11), then the pathways network (derived
    extract + moved train feed). Skipped when every file exists, unless should_rebuild."""
    from functions import pt_network, pt_pathways
    release = config.REACH_GTFS_RELEASE
    pbf_path, gtfs_paths, folder = transit_network_paths(release)
    if not should_rebuild and pbf_path.exists() and all(path.exists() for path in gtfs_paths):
        print(f"transit network {release}: reused ({project_relative(folder)})")
        return
    folder.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    summary = {"release": release, "source": {name: file_record(path)
                                              for name, path in config.REACH_GTFS_SOURCE_PATHS.items()}}
    cleaned = {}
    for name, src_path in config.REACH_GTFS_SOURCE_PATHS.items():
        cleaned[name] = folder / FEED_FILE.format(name, NETWORK_TAG, release)
        rows_to_drop = pt_network.excluded_route_type_rows(src_path, config.PT_EXCLUDED_ROUTE_TYPES)
        summary[f"{name} empty tables dropped"] = pt_network.copy_gtfs_dropping_empty(src_path, cleaned[name],
                                                                                     rows_to_drop)
    spurs_df, hubs_df, counts = pt_pathways.build_pathways(
        config.ROAD_EXTRACT_PBF_PATH, cleaned[config.REACH_TRAIN_FEED], pbf_path,
        folder / MOVED_FEED_FILE.format(config.REACH_TRAIN_FEED, NETWORK_TAG, release))
    spurs_df.to_csv(folder / SPURS_FILE.format(release), index=False)
    hubs_df.to_csv(folder / HUBS_FILE.format(release), index=False)
    summary["pathways"] = counts
    summary["build_s"] = round(time.perf_counter() - started)
    (folder / NETWORK_SUMMARY_FILE).write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8",
                                               newline="\n")
    print(f"transit network {release}: built in {summary['build_s']} s; pathways {counts}")


# --- transit subject pass, bands 1-2 ----------------------------------------------------------------
TRANSIT_SPLITS_FILE = "hex_splits.parquet"
CHUNK_DIR = "{}_{}_{}min"                     # day type, start HHMM, window minutes
ENVELOPE_FILE = "envelope.csv"
ORIGIN_FILE = "times_{:03d}.parquet"
CHUNK_DONE_FILE = "chunk_summary.json"
CLOCK_FORMAT = "%H:%M"
HEX_COLUMNS = ["hex_id", "centroid_lat", "centroid_lon", "residents", "workers"]
SECONDS_PER_HOUR = 3600


def subject_chunks():
    """Every chunk of the subject's windows: (day type, date, start datetime, minutes), whole 30-min slots, at most
    REACH_TRANSIT_CHUNK_MAX_MIN each, in window order."""
    chunks = []
    for day_type, (day, windows) in config.REACH_SUBJECT_WINDOWS.items():
        for first, last in windows:
            start = datetime.datetime.combine(day, datetime.datetime.strptime(first, CLOCK_FORMAT).time())
            end = datetime.datetime.combine(day, datetime.datetime.strptime(last, CLOCK_FORMAT).time())
            assert (end - start).seconds % (config.HOURS_SLOT_MIN * SECONDS_PER_MIN) == 0, "window not whole slots"
            while start < end:
                minutes = min(config.REACH_TRANSIT_CHUNK_MAX_MIN, int((end - start).total_seconds()) // SECONDS_PER_MIN)
                chunks.append((day_type, day, start, minutes))
                start += datetime.timedelta(minutes=minutes)
    return chunks


def transit_stamp(subject_lat, subject_lon):
    from functions import pt_pathways, transit_oracle, transit_reach
    pbf_path, gtfs_paths, _ = transit_network_paths()
    inputs = {"pbf": pbf_path, **{path.stem: path for path in gtfs_paths},
              "hex_nodes": subject_layers_file(config.HEX_NODES_PATH, subject_lat, subject_lon),
              "venues_with_hex": subject_file(config.VENUES_WITH_HEX_PATH, subject_lat, subject_lon, venues_tags())}
    code = [Path(module.__file__) for module in (transit_oracle, transit_reach, pt_pathways)] + [Path(__file__)]
    names = ["REACH_GTFS_RELEASE", "REACH_TRANSIT_JAR_SHA256", "REACH_TRANSIT_WALK_SPEED_KMH",
             "REACH_TRANSIT_MAX_TIME_MIN", "REACH_TRANSIT_CHUNK_MAX_MIN", "REACH_ORACLE_CUT_MIN",
             "REACH_ORACLE_TRANSFER_CHARGE_S", "REACH_ORACLE_SPLIT_RADIUS_M", "REACH_POPULATED_MIN_PERSONS",
             "REACH_ORIGINS_PER_FILE", "REACH_SUBJECT_WINDOWS", "REACH_ORACLE_DAY_TYPE_DATES", "HOURS_SLOT_MIN"]
    return {"kind": "transit bands 1-2, subject", "subject": [subject_lat, subject_lon],
            "inputs": {name: file_record(path) for name, path in inputs.items()},
            "network_sha256": {path.name: file_sha256(path) for path in [pbf_path, *gtfs_paths]},
            "jar": file_record(config.REACH_TRANSIT_JAR_PATH),
            "config": {name: getattr(config, name) for name in names},
            "code_sha256": {project_relative(path): file_sha256(path) for path in code},
            STAMP_COMMIT_KEY: git_commit()}


def stamp_input_path(stamp, name):
    return config.PROJECT_ROOT / stamp["inputs"][name]["path"]


def subject_venue_hex(hex_df, venue_hex_ids, subject_lat, subject_lon):
    """The venue hex whose centroid is nearest the subject's point, and its distance in metres."""
    from functions.geometry import haversine_m
    venues = hex_df[hex_df.hex_id.isin(venue_hex_ids)]
    distance_m = haversine_m(subject_lat, subject_lon, venues.centroid_lat.to_numpy(), venues.centroid_lon.to_numpy())
    nearest = int(np.argmin(distance_m))
    return venues.iloc[nearest], float(distance_m[nearest])


class OracleContext:
    """R5's walk graph, stops, schedules and the origin hexes' splits: everything the span oracle needs."""

    def __init__(self, network, jpype, origins_df, splits_path):
        from functions import transit_oracle
        self.jpype = jpype
        self.street_layer = network._transport_network.streetLayer
        self.transit_layer = network._transport_network.transitLayer
        self.n_vertices = int(self.street_layer.vertexStore.getVertexCount())
        self.walk, self.from_pair = transit_oracle.walk_edges(self.street_layer, jpype,
                                                              config.REACH_TRANSIT_WALK_SPEED_KMH)
        self.stop_vertex = transit_oracle.as_numpy(self.transit_layer.streetVertexForStop)
        self.schedules = transit_oracle.all_schedules(self.transit_layer)
        if splits_path.exists():
            split_df = pd.read_parquet(splits_path)
        else:
            split_df = transit_oracle.splits(self.street_layer, origins_df.centroid_lat.to_numpy(),
                                             origins_df.centroid_lon.to_numpy(), jpype,
                                             config.REACH_ORACLE_SPLIT_RADIUS_M)
            split_df.to_parquet(splits_path, index=False)
        self.hexes = transit_oracle.HexSplits(split_df, self.from_pair)
        self.trips_by_day_type = {}

    def slot_oracle_s(self, day_type, slot_start_s, venue_split):
        """Oracle seconds from every origin hex to the venue, span oracle of one 30-min slot (RCH-26)."""
        from functions import transit_oracle
        if day_type not in self.trips_by_day_type:
            self.trips_by_day_type = {day_type: transit_oracle.day_type_trips(
                self.transit_layer, self.jpype, self.schedules, config.REACH_ORACLE_DAY_TYPE_DATES[day_type])}
        cut_s = config.REACH_ORACLE_CUT_MIN * SECONDS_PER_MIN
        rides_df = transit_oracle.ride_edges(self.trips_by_day_type[day_type], slot_start_s,
                                             slot_start_s + config.HOURS_SLOT_MIN * SECONDS_PER_MIN + cut_s)
        graph = transit_oracle.reverse_graph(self.walk, rides_df, self.stop_vertex, self.n_vertices,
                                             config.REACH_ORACLE_TRANSFER_CHARGE_S)
        return transit_oracle.venue_oracle(graph, self.n_vertices, self.from_pair, self.hexes, venue_split,
                                           config.REACH_TRANSIT_WALK_SPEED_KMH, cut_s)


def chunk_envelope(oracle, origins_df, day_type, start, minutes, venue_split):
    """Origin hexes with oracle <= REACH_ORACLE_CUT_MIN in any slot of the chunk, with each slot's oracle seconds
    (NaN past the cut; columns named by slot start), and the per-slot set sizes."""
    cut_s = config.REACH_ORACLE_CUT_MIN * SECONDS_PER_MIN
    columns, sizes = {}, {}
    for offset in range(0, minutes, config.HOURS_SLOT_MIN):
        slot = start + datetime.timedelta(minutes=offset)
        oracle_s = oracle.slot_oracle_s(day_type, slot.hour * SECONDS_PER_HOUR + slot.minute * SECONDS_PER_MIN,
                                        venue_split)
        columns[slot.strftime(CLOCK_FORMAT)] = np.where(oracle_s <= cut_s, oracle_s, np.nan).astype(np.float32)
        sizes[slot.strftime(CLOCK_FORMAT)] = int((oracle_s <= cut_s).sum())
    oracle_df = pd.DataFrame(columns)
    is_inside = oracle_df.notna().any(axis=1).to_numpy()
    return origins_df[is_inside], oracle_df[is_inside].assign(hex_id=origins_df.hex_id.to_numpy()[is_inside]), sizes


def route_chunk(network, jpype, chunk_dir, envelope_df, destinations_df, start, minutes):
    """Every envelope origin to every venue hex over the chunk's window (draws mode), REACH_ORIGINS_PER_FILE
    origins per parquet file (resume unit). Returns (rows, wall seconds) of the files routed in this call."""
    import geopandas as gpd
    from shapely.geometry import Point
    from functions import transit_reach
    destinations_gdf = gpd.GeoDataFrame(
        {"id": destinations_df.hex_id.to_numpy()}, crs=config.GEOGRAPHIC_CRS,
        geometry=gpd.points_from_xy(destinations_df.centroid_lon, destinations_df.centroid_lat))
    dest_hexes = destinations_df.hex_id.to_numpy()
    task = transit_reach.draws_task(network, destinations_gdf, start, minutes, config.REACH_TRANSIT_MAX_TIME_MIN,
                                    config.REACH_TRANSIT_WALK_SPEED_KMH)
    transit_reach.set_report(jpype, minutes)
    n_rows, routed_s = 0, 0.0

    def route_origin(origin):
        # R5 releases the GIL in Java and shares the read-only network; each call clones the task (r5py __copy__)
        by_iteration = transit_reach.origin_minutes(network._transport_network, task,
                                                    Point(origin.centroid_lon, origin.centroid_lat), minutes)
        return transit_reach.origin_rows(by_iteration, origin.hex_id, dest_hexes)

    pool = ThreadPoolExecutor(max_workers=config.REACH_TRANSIT_THREADS)
    try:
        for file_no, first in enumerate(range(0, len(envelope_df), config.REACH_ORIGINS_PER_FILE)):
            path = chunk_dir / ORIGIN_FILE.format(file_no)
            if path.exists():
                continue
            tick = time.perf_counter()
            origins = envelope_df.iloc[first:first + config.REACH_ORIGINS_PER_FILE].itertuples()
            frames = list(pool.map(route_origin, origins))               # map keeps the origins' order
            frame = pd.concat(frames, ignore_index=True)
            partial = path.with_name(path.name + PARTIAL_SUFFIX)
            frame.to_parquet(partial, index=False, compression="zstd")
            partial.replace(path)
            n_rows += len(frame)
            routed_s += time.perf_counter() - tick
            print(f"    file {file_no}: {min(first + config.REACH_ORIGINS_PER_FILE, len(envelope_df)):,} of "
                  f"{len(envelope_df):,} origins, {len(frame):,} rows, {time.perf_counter() - tick:.0f} s", flush=True)
    finally:
        pool.shutdown()
        transit_reach.clear_report(jpype)
    return n_rows, routed_s


def transit_subject_pass(subject_lat, subject_lon, chunk_limit=None):
    """Bands 1-2 for the subject (RCH-20, RCH-21): per chunk of the subject's hours, the oracle envelope (RCH-26),
    then every envelope origin to every venue hex at every minute (P8r draws). Resumable per chunk and per origin
    file. chunk_limit: stop after this many chunks (the timing run is chunk 1)."""
    from functions import pt_network, transit_oracle, transit_reach
    stamp = transit_stamp(subject_lat, subject_lon)
    folder = pass_folder("transit", stamp, subject_lat, subject_lon)
    jpype = transit_reach.start_jvm(config.REACH_TRANSIT_JAR_PATH, config.REACH_TRANSIT_JAR_SHA256,
                                    config.REACH_TRANSIT_R5_MAX_MEMORY)
    from r5py import TransportNetwork
    from r5py.util import Config as R5pyConfig
    pbf_path, gtfs_paths, _ = transit_network_paths()
    pt_network.check_r5py_working_copies([pbf_path, *gtfs_paths], Path(R5pyConfig().CACHE_DIR))
    started = time.perf_counter()
    network = TransportNetwork(pbf_path, gtfs_paths)
    chunks = subject_chunks()
    for day in {day for _, day, _, _ in chunks}:
        assert network.transit_layer.covers(day), f"{day} outside the release's service (TRN-7)"

    hex_df = pyogrio.read_dataframe(stamp_input_path(stamp, "hex_nodes"), read_geometry=False, columns=HEX_COLUMNS)
    hex_df["persons"] = hex_df.residents.fillna(0) + hex_df.workers.fillna(0)
    venue_hex_ids = (pd.read_csv(stamp_input_path(stamp, "venues_with_hex"), usecols=["hex_id"]).hex_id
                     .dropna().astype(np.int64).unique())
    destinations_df = hex_df[hex_df.hex_id.isin(venue_hex_ids)].sort_values("hex_id").reset_index(drop=True)
    origins_df = hex_df[hex_df.persons >= config.REACH_POPULATED_MIN_PERSONS].reset_index(drop=True)
    subject_hex, subject_m = subject_venue_hex(hex_df, venue_hex_ids, subject_lat, subject_lon)
    del hex_df
    oracle = OracleContext(network, jpype, origins_df, folder / TRANSIT_SPLITS_FILE)
    venue_split = transit_oracle.splits(oracle.street_layer, [subject_hex.centroid_lat], [subject_hex.centroid_lon],
                                        jpype, config.REACH_ORACLE_SPLIT_RADIUS_M).iloc[0]
    assert not np.isnan(venue_split.edge), "the subject's venue hex is not linked to R5's street layer"
    print(f"transit pass: network + oracle setup {time.perf_counter() - started:.0f} s; {len(origins_df):,} populated "
          f"origins ({int((~oracle.hexes.is_linked).sum())} unlinked), {len(destinations_df):,} venue hexes; subject "
          f"venue hex {int(subject_hex.hex_id)} ({subject_m:.0f} m); {len(chunks)} chunks", flush=True)

    envelopes = []                                # every chunk's envelope first (cheap), so a partial run knows the rest
    for chunk_no, (day_type, _, start, minutes) in enumerate(chunks):
        chunk_dir = folder / CHUNK_DIR.format(day_type, start.strftime("%H%M"), minutes)
        chunk_dir.mkdir(exist_ok=True)
        envelope_path = chunk_dir / ENVELOPE_FILE
        if not envelope_path.exists():
            tick = time.perf_counter()
            _, oracle_df, slot_sizes = chunk_envelope(oracle, origins_df, day_type, start, minutes, venue_split)
            oracle_df[["hex_id", *slot_sizes]].to_csv(envelope_path, index=False)
            print(f"  chunk {chunk_no} {day_type} {start:%Y-%m-%d %H:%M} +{minutes} min: envelope {len(oracle_df):,} "
                  f"origins ({time.perf_counter() - tick:.0f} s; per slot {slot_sizes})", flush=True)
        envelope_df = origins_df[origins_df.hex_id.isin(pd.read_csv(envelope_path).hex_id)]
        envelopes.append((chunk_no, day_type, start, minutes, chunk_dir, envelope_df))
    print(f"transit pass: envelopes {[len(e[5]) for e in envelopes]}; {sum(len(e[5]) for e in envelopes):,} "
          f"origin-chunks in all", flush=True)

    for chunk_no, day_type, start, minutes, chunk_dir, envelope_df in envelopes[:chunk_limit]:
        if (chunk_dir / CHUNK_DONE_FILE).exists():
            continue
        print(f"  chunk {chunk_no} {day_type} {start:%Y-%m-%d %H:%M} +{minutes} min: routing {len(envelope_df):,} origins",
              flush=True)
        n_rows, routed_s = route_chunk(network, jpype, chunk_dir, envelope_df, destinations_df, start, minutes)
        summary = {"day_type": day_type, "start": start.isoformat(), "minutes": minutes,
                   "envelope_origins": len(envelope_df), "rows_this_run": n_rows, "routed_s_this_run": round(routed_s),
                   "s_per_origin_this_run": round(routed_s / max(len(envelope_df), 1), 4),
                   "bytes": sum(path.stat().st_size for path in chunk_dir.glob("times_*.parquet"))}
        (chunk_dir / CHUNK_DONE_FILE).write_text(json.dumps(summary, indent=1), encoding="utf-8",
                                                     newline="\n")
        print(f"  chunk {chunk_no} done: {json.dumps(summary)}", flush=True)
    return folder
