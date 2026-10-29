"""Reachability transit pilot: how long would bands 1-2 take on the frozen transit model? (scoping, report only)

Claim scoped (concepts/reachability.md RCH-1, RCH-3, RCH-19; DESIGN.md Q21): the transit bands can be computed for
every populated origin hex to every venue hex on the frozen model (TRN-16) in a manageable time. Where the pipeline
would rely on it: the planned reachability pass, after the frozen model enters the pipeline (RCH-18). Scoping only,
no pass/fail; design choices (departure times, cap, chunking) are the user's.

Method: the frozen jar (sha256 checked) and the v2 pathways network of release 20261016, as transit_holdout_score.py
opens them (copied, D1); TravelTimeMatrix at a 1-min window, percentile 49, walk 4.143 km/h, transit + walk,
max_time RCH-19's 30 min. Direction hex -> venue (RCH-16, T1): origins = sampled populated hexes (residents +
workers >= 1), PILOT_PER_RING per ring by haversine distance to the subject (inner < 5 km, mid 5-25, outer >= 25),
seeded; destinations = every venue hex centroid (8,959). One TTM call per ring (R5 threads over origins), one
departure (DEPARTURE, a Wednesday inside the release's window). Reported: wall time per call and per origin;
destinations reached <= 10 / <= 20 / <= 30 min per origin; extrapolation to every populated hex by ring, per
departure time. Network load time reported apart (once per run).

Conclusion (run 2026-10-22, autonomous 69th; scoping): network load 5 s (cached build); 100 origins per ring to 8,959
  venue hexes, one call each: inner (0-5 km) 6 s, mid (5-25) 4 s, outer (25-99) 4 s, i.e. 0.04-0.06 s per origin
  (each call includes linking the destinations, so large chunks should be cheaper per origin). Median venue hexes
  reached per origin <= 10 / 20 / 30 min: inner 6 / 67 / 248, mid 1 / 11 / 44, outer 0 / 3 / 10. Extrapolated to
  every populated hex (residents + workers >= 1: 521,044; inner 12,064, mid 201,789, outer 307,191): ~5.5 h per
  departure time in one JVM, ~26 M rows <= 30 min (small on disk). The cost driver is the number of departure
  times (each multiplies it) and outer origins with almost nothing in reach; a haversine prefilter (as the draw's
  35 km) would cut the outer ring. First run cut seconds at 10 / 20 (the jar returns seconds): fixed, rerun.
  Chunk mode (added after, same day): 3,000 random populated origins in one call: 96 s, 0.032 s per origin, so all
  populated hexes ~4.6 h per departure; origins reaching no venue hex <= 30 min: inner 0.000, mid 0.052, outer
  0.119, so a reach prefilter saves ~8% at most (the "halve" guess above is wrong). The subject's hours (Places
  pull 2026-10-10): Mon-Thu 17:30-21:00 (Wed 17:45), Fri 17:30-21:30, Sat 12:30-15:00 and 17:00-21:30, Sun
  12:45-15:00 and 17:00-21:00: at 10-min steps 21 departures a Mon-Thu evening (~97 h), the whole week 187 (~860 h);
  hourly weekday dinner 4 departures (~18 h).

Inputs (read only): the frozen jar, transit_pathway_network_v2's 20261016 network files, the hex nodes table (centroids,
residents, workers), venues with hex. Self-contained (CLAUDE.md D1). No API calls. One JVM. Usage:
`python reachability_transit_pilot.py`.
"""
import datetime
import hashlib
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "-37.76870_144.97196"
FILE_TAG = f"res2021_wrk2021_ven20260925_{SUBJECT}"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
V2_NAME = "transit_pathway_network_v2"
FROZEN_JAR_PATH = PROJECT_ROOT / "outputs" / "r5_patches" / "r5-v7.5.1-r5py-all_transit_r5_patch_connector_p2.jar"
FROZEN_JAR_SHA256 = "62a8f6c1afa2e0a0c86860e336da499f9344e46e6c6d259d9c4824d129e68eb3"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"
VENUES_WITH_HEX_PATH = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT / f"venues_with_hex_ven20260925_{SUBJECT}.csv"
NAME = "reachability_transit_pilot"

# --- values ----------------------------------------------------------------------------------------
RELEASE = "20261016"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
R5_MAX_MEMORY = "7G"
SPEED_KMH = 4.143                               # TRN-16 freeze record
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
CAP_MIN = 30                                    # RCH-19
CUTS_S = [600, 1200]                            # bands 1-2 (RCH-1); the frozen jar returns seconds (TRN-16)
DEPARTURE = datetime.datetime(2026, 10, 28, 12, 0)   # Wednesday, inside the 20261016 release's window (Oct 22 - Nov 2)
GUARD_CLASSES = ["com.conveyal.r5.profile.FastRaptorWorker", "com.conveyal.r5.streets.StreetRouter",
                 "com.conveyal.r5.streets.LinkedPointSet", "com.conveyal.r5.analyst.TravelTimeReducer"]
SUBJECT_LAT, SUBJECT_LON = -37.7687014, 144.9719611
RING_EDGES_KM = [0, 5, 25, np.inf]
RING_LABELS = ["inner", "mid", "outer"]
PILOT_PER_RING = 100
CHUNK_ORIGINS = 3000                            # one large call (mode "chunk"): per-origin cost at scale
SEED = 20261022
POPULATED_MIN_PERSONS = 1.0                     # as reachability_drive_pilot.py
EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def check_jar():
    with open(FROZEN_JAR_PATH, "rb") as file:
        assert hashlib.file_digest(file, "sha256").hexdigest() == FROZEN_JAR_SHA256, "not the frozen jar"


def network_paths():
    """(from transit_holdout_score.py)"""
    feed_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{RELEASE}"
    pbf_path = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{RELEASE}.osm.pbf"
    gtfs = [feed_dir / (f"{name}_{V2_NAME}_{RELEASE}_moved.zip" if name == TRAIN_FEED else f"{name}_{V2_NAME}_{RELEASE}.zip")
            for name in FEED_NAMES]
    return pbf_path, gtfs


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (from transit_holdout_score.py)."""
    from r5py.util.config import Config
    for path in paths:
        cached = Path(Config().CACHE_DIR) / Path(path).name
        if not cached.exists():
            continue
        digests = []
        for candidate in (path, cached):
            with open(candidate, "rb") as file:
                digests.append(hashlib.file_digest(file, "blake2s").hexdigest())
        assert digests[0] == digests[1], f"r5py's cached {cached} differs from {path}: stale working copy"


def main(mode="rings"):
    import pyogrio
    run_date = datetime.date.today().strftime("%Y%m%d")
    out_prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}"
    check_jar()
    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False,
                                    columns=["hex_id", "centroid_lat", "centroid_lon", "residents", "workers"])
    hex_df["distance_km"] = haversine_m(SUBJECT_LAT, SUBJECT_LON, hex_df.centroid_lat, hex_df.centroid_lon) / 1000
    hex_df["ring"] = pd.cut(hex_df.distance_km, RING_EDGES_KM, labels=RING_LABELS, right=False)
    populated_df = hex_df[hex_df.residents.fillna(0) + hex_df.workers.fillna(0) >= POPULATED_MIN_PERSONS]
    venue_ids = pd.read_csv(VENUES_WITH_HEX_PATH, usecols=["hex_id"]).hex_id.dropna().astype(np.int64).unique()
    venue_df = hex_df[hex_df.hex_id.isin(venue_ids)]
    ring_counts = populated_df.ring.value_counts().reindex(RING_LABELS)
    lines = [f"{NAME} run {run_date}: populated hexes {len(populated_df):,} by ring {ring_counts.to_dict()}; venue hexes "
             f"{len(venue_df):,}; departure {DEPARTURE:%Y-%m-%d %H:%M}; cap {CAP_MIN} min"]

    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(FROZEN_JAR_PATH)]   # r5py reads these at import
    import geopandas as gpd
    import jpype
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    for name in GUARD_CLASSES:
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == FROZEN_JAR_PATH.resolve(), f"{name} loaded from {location}"
    pbf_path, gtfs = network_paths()
    check_working_copies([pbf_path] + gtfs)
    tick = time.perf_counter()
    network = TransportNetwork(pbf_path, gtfs)
    assert network.transit_layer.covers(DEPARTURE.date())
    lines.append(f"network load {time.perf_counter() - tick:.0f} s")
    print(lines[-1], flush=True)
    destinations = gpd.GeoDataFrame({"id": venue_df.hex_id.to_numpy()}, crs="EPSG:4326",
                                    geometry=gpd.points_from_xy(venue_df.centroid_lon, venue_df.centroid_lat))
    rng = np.random.default_rng(SEED)
    if mode == "chunk":
        sample = populated_df.iloc[rng.choice(len(populated_df), size=CHUNK_ORIGINS, replace=False)]
        origins = gpd.GeoDataFrame({"id": sample.hex_id.to_numpy()}, crs="EPSG:4326",
                                   geometry=gpd.points_from_xy(sample.centroid_lon, sample.centroid_lat))
        tick = time.perf_counter()
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=DEPARTURE,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=datetime.timedelta(minutes=CAP_MIN),
            speed_walking=SPEED_KMH))
        wall_s = time.perf_counter() - tick
        reached = matrix_df.dropna(subset=[f"travel_time_p{SINGLE_PERCENTILE}"]).groupby("from_id").size()
        sample = sample.assign(reached=sample.hex_id.map(reached).fillna(0))
        lines += [f"chunk: {CHUNK_ORIGINS} random populated origins in one call: {wall_s:.0f} s, "
                  f"{wall_s / CHUNK_ORIGINS:.3f} s per origin; all {len(populated_df):,} at this rate "
                  f"{wall_s / CHUNK_ORIGINS * len(populated_df) / 3600:.1f} h per departure"]
        for label, ring_df in sample.groupby("ring", observed=True):
            lines.append(f"  {label}: {len(ring_df)} origins; share reaching no venue hex <= {CAP_MIN} min "
                         f"{(ring_df.reached == 0).mean():.3f}")
        summary = "\n".join(lines)
        Path(f"{out_prefix}_chunk_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
        print(summary)
        return
    records = []
    for label in RING_LABELS:
        members = populated_df[populated_df.ring == label]
        sample = members.iloc[rng.choice(len(members), size=min(PILOT_PER_RING, len(members)), replace=False)]
        origins = gpd.GeoDataFrame({"id": sample.hex_id.to_numpy()}, crs="EPSG:4326",
                                   geometry=gpd.points_from_xy(sample.centroid_lon, sample.centroid_lat))
        tick = time.perf_counter()
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=DEPARTURE,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=datetime.timedelta(minutes=CAP_MIN),
            speed_walking=SPEED_KMH))
        wall_s = time.perf_counter() - tick
        minutes = matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"]
        per_origin = matrix_df.assign(m=minutes).groupby("from_id").m.agg(
            reached_10=lambda m: int((m <= CUTS_S[0]).sum()), reached_20=lambda m: int((m <= CUTS_S[1]).sum()),
            reached_30=lambda m: int(m.notna().sum()))
        records.append({"ring": label, "origins": len(sample), "wall_s": wall_s, "per_origin_s": wall_s / len(sample),
                        "km_min": sample.distance_km.min(), "km_max": sample.distance_km.max(),
                        **{f"median_{k}": float(per_origin[k].median()) for k in per_origin.columns},
                        "rows_30": int(minutes.notna().sum())})
        print(records[-1], flush=True)
    pilot_df = pd.DataFrame(records)
    pilot_df.to_csv(f"{out_prefix}_rings.csv", index=False)
    lines += ["", "per ring: origins, wall s, s per origin, median venue hexes reached <= 10 / <= 20 / <= 30 min, rows <= 30"]
    for row in pilot_df.itertuples():
        lines.append(f"  {row.ring} ({row.km_min:.0f}-{row.km_max:.0f} km): {row.origins}, {row.wall_s:.0f} s, "
                     f"{row.per_origin_s:.2f} s; reached {row.median_reached_10:.0f} / {row.median_reached_20:.0f} / "
                     f"{row.median_reached_30:.0f}; rows {row.rows_30:,}")
    total_s = float((pilot_df.set_index("ring").per_origin_s.reindex(RING_LABELS) * ring_counts).sum())
    rows = float((pilot_df.set_index("ring").rows_30.reindex(RING_LABELS) / pilot_df.set_index("ring").origins.reindex(RING_LABELS)
                  * ring_counts).sum())
    lines += ["", f"extrapolated to every populated hex ({len(populated_df):,}), one departure: {total_s / 3600:.1f} h "
              f"({total_s / 86400:.2f} days); rows <= {CAP_MIN} min {rows / 1e6:,.0f} M. Each added departure time "
              f"multiplies the time; the 1-min window and percentile stay as frozen."]
    summary = "\n".join(lines)
    Path(f"{out_prefix}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main(*sys.argv[1:2])
