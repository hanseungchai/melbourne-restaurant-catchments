"""Asymmetry check: how much longer is hex -> venue than venue -> hex, so the oracle envelope's margin can be set?

Claim under test (concepts/reachability.md RCH-21, RCH-22; DESIGN.md Q25): a forward search from a venue to all hexes
(venue -> hex, cheap) finds every origin hex that can reach the venue within the pass's 30 min cap (hex -> venue,
RCH-19), once its cut is raised by a margin m. A -> B is not B -> A (waits, one-way streets, turns), so m is set from
the upper tail of d = t(hex -> venue) - t(venue -> hex). Where the pipeline would rely on it: Stage A of the subject-
scoped transit pass (RCH-21); Stage B's outer-ring self-check catches what the margin misses.

Method (free: frozen transit model, own drive graph; no API):
  Venues: the 8 of reachability_venue_compare (subject, [subject] Melbourne Central, 2 inner, 2 mid, 2 outer; saved list).
  Hexes: per venue, populated hexes (residents + workers >= 1) sampled by distance: HEXES_PER_STRATUM in each of
    0-2, 2-5, 5-10, 10-20 km, seeded.
  Transit: the frozen model (TRN-16 freeze record: jar sha256, v2 20261016 network, walk 4.143 km/h, 1-min window,
    percentile 49), max time 90 min, departures Wed 2026-10-28 12:00 and 18:30 and Sat 2026-10-31 13:00 (Saturday
    reported apart). Both directions at the same departure time; time = min(transit, walk), seconds.
  Drive: the 2tier all-pairs graph (as reachability_drive_pilot.py, copied); venue -> hex on the forward graph and
    hex -> venue on the reversed graph, from the venue hex's eligible nodes (node 1, node 2 inside the 1 m tie
    window), hex time = min over its eligible nodes; predicted = ALPHA x routed.
  Read on pairs with hex -> venue <= CAP_MIN (transit 30, the pass cap; drive 30 predicted): d's quantiles, and the
    miss share at margin m (share whose venue -> hex > CAP_MIN + m) for m = 0..MAX_MARGIN_MIN. (The miss side is
    d = venue -> hex minus hex -> venue; RCH-22's wording has the difference the other way round: flagged.)
  Rule (Claude's, written before the first run; not OK'd by the user): the margin is the smallest whole m whose
    pooled weekday miss share <= POOLED_MISS_MAX and every venue's <= VENUE_MISS_MAX; Saturday reported, not ruled.

Conclusion (run 2026-10-22, 73rd, autonomous; facts, the margin is the user's call): 8 venues x 400 hexes. Transit
weekday (2 departures, 1,729 pairs with hex -> venue <= 30): d = vh - hv median 0, q90 +5.4, q95 +8.0, q99 +14.2, max
+23.4 min; venue -> hex longer in 43%. Miss share pooled / worst venue at margin 0: 0.085 / 0.18; 5: 0.029 / 0.086;
10: 0.009 / 0.034; 15: 0.0035 / 0.024; 20: 0.0006 / 0.005. Rule margin 20 min (oracle cut 50 min). Saturday 13:00
alike (q99 +16.0; miss 0 at 15). Per venue q99 +6 (subject, inner 2) to +17 (Melbourne Central, mid 2); outer 1
(walk-only) 0. Drive (2tier predicted, 2,660 pairs): q99 +3.2, max +7.4; rule margin 3 min. First routing run used
the reverse sign in its printed quantiles (hv - vh); the miss table was right; report fixed same day.
----

Inputs (read only): reachability_venue_compare's venues, the hex nodes table, the frozen jar and v2 network, the
blind routing bundle, edge attrs and 2tier params. Self-contained (CLAUDE.md D1). One JVM per process.
Usage: `python reachability_asymmetry.py transit`, `... drive`, `... report`.
"""
import datetime
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "-37.76870_144.97196"
FILE_TAG = f"res2021_wrk2021_ven20260925_{SUBJECT}"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "reachability_asymmetry"
VENUES_NAME = "reachability_venue_compare"
V2_NAME = "transit_pathway_network_v2"
FROZEN_JAR_PATH = PROJECT_ROOT / "outputs" / "r5_patches" / "r5-v7.5.1-r5py-all_transit_r5_patch_connector_p2.jar"
FROZEN_JAR_SHA256 = "62a8f6c1afa2e0a0c86860e336da499f9344e46e6c6d259d9c4824d129e68eb3"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"
CALIBRATION_DIR = PROJECT_ROOT / "outputs" / "pathing_calibration"
BUNDLE_DIR = CALIBRATION_DIR / "prepared_graphs" / f"split_drive_edges_timed_blind_{FILE_TAG}_routing_b0_2"
EDGE_ATTRS_PATH = CALIBRATION_DIR / "fit" / SUBJECT / f"edge_attrs_{FILE_TAG}.npz"
PARAMS_PATH = CALIBRATION_DIR / "fit" / "model" / SUBJECT / "2tier_all_pairs_params.json"

# --- sample --------------------------------------------------------------------------------------------
DISTANCE_EDGES_KM = [0, 2, 5, 10, 20]
HEXES_PER_STRATUM = 100
POPULATED_MIN_PERSONS = 1.0
SEED = 20261022
EARTH_RADIUS_M = 6_371_000

# --- transit (frozen model, TRN-16) ----------------------------------------------------------------------
RELEASE = "20261016"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
R5_MAX_MEMORY = "7G"
SPEED_KMH = 4.143
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
MAX_TIME_MIN = 90
DEPARTURES = {"Wed 12:00": datetime.datetime(2026, 10, 28, 12, 0), "Wed 18:30": datetime.datetime(2026, 10, 28, 18, 30),
              "Sat 13:00": datetime.datetime(2026, 10, 31, 13, 0)}
WEEKEND_LABELS = ["Sat 13:00"]
GUARD_CLASSES = ["com.conveyal.r5.profile.FastRaptorWorker", "com.conveyal.r5.streets.StreetRouter",
                 "com.conveyal.r5.streets.LinkedPointSet", "com.conveyal.r5.analyst.TravelTimeReducer"]

# --- drive (as reachability_drive_pilot.py) ----------------------------------------------------------------
TIE_WINDOW_M = 1
MIN_CSR_WEIGHT = 1e-9
DRIVE_LIMIT_PREDICTED_S = 3600                 # search limit, predicted seconds

# --- reading ---------------------------------------------------------------------------------------------
SECONDS_PER_MIN = 60
CAP_MIN = 30
MAX_MARGIN_MIN = 20
POOLED_MISS_MAX = 0.001
VENUE_MISS_MAX = 0.005
QUANTILES = [0.5, 0.9, 0.95, 0.99, 1.0]


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def newest(pattern):
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return saved[-1] if saved else None


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def sample(hex_columns=()):
    """Venues and, per venue, the seeded distance-stratified hex sample (the same in both modes)."""
    import pyogrio
    venues_df = pd.read_csv(newest(f"{VENUES_NAME}_2*_venues.csv"))
    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False,
                                    columns=["hex_id", "centroid_lat", "centroid_lon", "residents", "workers", *hex_columns])
    is_populated = hex_df.residents.fillna(0).to_numpy() + hex_df.workers.fillna(0).to_numpy() >= POPULATED_MIN_PERSONS
    rng = np.random.default_rng(SEED)
    rows = []
    for venue in venues_df.itertuples():
        km = haversine_m(venue.centroid_lat, venue.centroid_lon, hex_df.centroid_lat.to_numpy(), hex_df.centroid_lon.to_numpy()) / 1000
        for low, high in zip(DISTANCE_EDGES_KM[:-1], DISTANCE_EDGES_KM[1:]):
            members = np.flatnonzero(is_populated & (km >= low) & (km < high) & (hex_df.hex_id.to_numpy() != venue.hex_id))
            for k in rng.choice(members, size=min(HEXES_PER_STRATUM, len(members)), replace=False):
                rows.append({"venue": venue.label, "venue_hex": venue.hex_id, "hex_id": int(hex_df.hex_id.iat[k]),
                             "km": km[k], "stratum": f"{low}-{high}"})
    return venues_df, pd.DataFrame(rows), hex_df


# --- transit -------------------------------------------------------------------------------------------
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


def route_transit():
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_transit.csv"
    with open(FROZEN_JAR_PATH, "rb") as file:
        assert hashlib.file_digest(file, "sha256").hexdigest() == FROZEN_JAR_SHA256, "not the frozen jar"
    venues_df, pairs_df, hex_df = sample()
    points_df = hex_df.set_index("hex_id").loc[pairs_df.hex_id.unique(), ["centroid_lat", "centroid_lon"]].reset_index()
    print(f"transit: {len(venues_df)} venues, {len(pairs_df)} pairs, {len(points_df)} hexes", flush=True)
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
    network = TransportNetwork(pbf_path, gtfs)
    # venue ids offset so no hex id equals a venue id (r5py reads from_id == to_id as 0)
    venues = gpd.GeoDataFrame({"id": -1 - venues_df.hex_id}, crs="EPSG:4326",
                              geometry=gpd.points_from_xy(venues_df.centroid_lon, venues_df.centroid_lat))
    hexes = gpd.GeoDataFrame({"id": points_df.hex_id}, crs="EPSG:4326",
                             geometry=gpd.points_from_xy(points_df.centroid_lon, points_df.centroid_lat))

    def ttm(origins, destinations, departure, modes):
        table = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=modes, max_time=datetime.timedelta(minutes=MAX_TIME_MIN), speed_walking=SPEED_KMH))
        return table.rename(columns={f"travel_time_p{SINGLE_PERCENTILE}": "s"})

    frames = []
    started = datetime.datetime.now()
    for label, departure in DEPARTURES.items():
        assert network.transit_layer.covers(departure.date())
        for direction, origins, destinations in (("vh", venues, hexes), ("hv", hexes, venues)):
            both = None
            for kind, modes in (("transit", [TransportMode.TRANSIT, TransportMode.WALK]), ("walk", [TransportMode.WALK])):
                table = ttm(origins, destinations, departure, modes).rename(columns={"s": kind})
                both = table if both is None else both.merge(table, on=["from_id", "to_id"], how="outer")
            venue_ids = both.from_id if direction == "vh" else both.to_id
            hex_ids = both.to_id if direction == "vh" else both.from_id
            frames.append(pd.DataFrame({"departure": label, "direction": direction, "venue_hex": -1 - venue_ids,
                                        "hex_id": hex_ids, "s": np.fmin(both.transit.fillna(np.inf), both.walk.fillna(np.inf))}))
        print(f"  {label}: {datetime.datetime.now() - started}", flush=True)
    routes_df = pd.concat(frames, ignore_index=True)
    table_df = routes_df.pivot_table(index=["departure", "venue_hex", "hex_id"], columns="direction", values="s").reset_index()
    out_df = pairs_df.merge(table_df, on=["venue_hex", "hex_id"], how="left")
    out_df.to_csv(out_path, index=False)
    print(f"transit done in {datetime.datetime.now() - started}: {out_path.name}", flush=True)


# --- drive ---------------------------------------------------------------------------------------------
def fitted_matrices():
    """The 2tier all-pairs graph forward and reversed (CSR), and its params (as reachability_drive_pilot.py)."""
    from scipy.sparse import csr_matrix
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    (low, high), = params["groups"]
    assert params["edge_set"] == "all"
    indptr, indices = np.load(BUNDLE_DIR / "indptr.npy"), np.load(BUNDLE_DIR / "indices.npy")
    time_s = np.load(BUNDLE_DIR / "raw_time_raw_s.npy")
    signals = np.load(BUNDLE_DIR / "signals.npy")
    nodes = np.load(BUNDLE_DIR / "nodes.npy")
    with np.load(EDGE_ATTRS_PATH) as attrs:
        level = attrs["level"]
    scale = np.where((level >= low) & (level <= high), params["multipliers"][0], 1.0)
    weight = np.maximum(time_s * scale + params["beta"] * signals[indices].astype(float), MIN_CSR_WEIGHT)
    matrix = csr_matrix((weight, indices, indptr), shape=(len(nodes),) * 2)
    return matrix, matrix.T.tocsr(), nodes, params


def eligible_rows(hex_df, nodes):
    """Per hex: CSR rows of node 1, and of node 2 when within the tie window and different (else -1)."""
    row_1 = np.searchsorted(nodes, hex_df.drive_node_1.to_numpy(np.int64))
    node_2 = hex_df.drive_node_2.to_numpy()
    is_2 = (~np.isnan(node_2) & (hex_df.drive_road_dist_2_m.to_numpy() - hex_df.drive_road_dist_1_m.to_numpy() <= TIE_WINDOW_M)
            & (node_2 != hex_df.drive_node_1.to_numpy()))
    row_2 = np.where(is_2, np.searchsorted(nodes, np.nan_to_num(node_2).astype(np.int64)), -1)
    assert np.array_equal(nodes[row_1], hex_df.drive_node_1.to_numpy(np.int64)), "node 1 not in the bundle"
    return row_1, row_2


def route_drive():
    from scipy.sparse.csgraph import dijkstra
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_drive.csv"
    venues_df, pairs_df, hex_df = sample(["drive_node_1", "drive_node_2", "drive_road_dist_1_m", "drive_road_dist_2_m"])
    forward, reverse, nodes, params = fitted_matrices()
    limit_s = DRIVE_LIMIT_PREDICTED_S / params["alpha"]
    position = pd.Series(np.arange(len(hex_df)), index=hex_df.hex_id.to_numpy())
    row_1, row_2 = eligible_rows(hex_df, nodes)
    frames = []
    for venue in venues_df.itertuples():
        pos = position[venue.hex_id]
        sources = [row_1[pos]] + ([row_2[pos]] if row_2[pos] >= 0 else [])
        venue_pairs = pairs_df[pairs_df.venue_hex == venue.hex_id]
        hex_pos = position[venue_pairs.hex_id].to_numpy()
        out = {}
        for direction, graph in (("vh", forward), ("hv", reverse)):
            dist = dijkstra(graph, directed=True, indices=sources, min_only=True, limit=limit_s)
            out[direction] = params["alpha"] * np.minimum(
                dist[row_1[hex_pos]], np.where(row_2[hex_pos] >= 0, dist[np.maximum(row_2[hex_pos], 0)], np.inf))
        frames.append(venue_pairs.assign(departure="drive", **out))
        print(f"  {venue.label}: {len(venue_pairs)} hexes", flush=True)
    pd.concat(frames, ignore_index=True).to_csv(out_path, index=False)
    print(f"drive done: {out_path.name}", flush=True)


# --- report --------------------------------------------------------------------------------------------
def margin_lines(df, label):
    reached = df[df.hv <= CAP_MIN * SECONDS_PER_MIN].copy()
    reached["vh"] = reached.vh.fillna(np.inf)                                 # unreached within the search limit
    reached["d_min"] = (reached.vh - reached.hv) / SECONDS_PER_MIN            # venue -> hex minus hex -> venue (the miss side)
    quantiles = np.quantile(reached.d_min, QUANTILES) if len(reached) else []
    lines = [f"{label}: pairs {len(df)}, hex -> venue <= {CAP_MIN} min {len(reached)}; d = vh - hv (min) quantiles "
             + ", ".join(f"q{q:g} {v:+.1f}" for q, v in zip(QUANTILES, quantiles))
             + f"; venue -> hex longer in {(reached.d_min > 0).mean():.2f}, unreached <= {MAX_TIME_MIN} min {np.isinf(reached.d_min).mean():.4f}"]
    miss = {m: float((reached.vh > (CAP_MIN + m) * SECONDS_PER_MIN).mean()) for m in range(MAX_MARGIN_MIN + 1)}
    by_venue = {m: reached.groupby("venue").apply(lambda g: (g.vh > (CAP_MIN + m) * SECONDS_PER_MIN).mean(), include_groups=False)
                for m in range(MAX_MARGIN_MIN + 1)}
    lines.append("  miss share by margin m (pooled; worst venue): " + ", ".join(
        f"{m}: {miss[m]:.4f} / {by_venue[m].max():.3f}" for m in (0, 1, 2, 3, 5, 7, 10, 15, 20)))
    chosen = next((m for m in range(MAX_MARGIN_MIN + 1) if miss[m] <= POOLED_MISS_MAX and by_venue[m].max() <= VENUE_MISS_MAX), None)
    return lines, chosen, reached


def report():
    tag = run_date()
    transit_df = pd.read_csv(newest(f"{NAME}_2*_transit.csv"))
    drive_df = pd.read_csv(newest(f"{NAME}_2*_drive.csv"))
    lines = [f"{NAME} {tag}: venues 8 (reachability_venue_compare), hexes {HEXES_PER_STRATUM} per stratum "
             f"{DISTANCE_EDGES_KM} km; cap {CAP_MIN} min; rule: smallest m with pooled miss <= {POOLED_MISS_MAX} and "
             f"every venue <= {VENUE_MISS_MAX} (weekday transit and drive; Saturday report-only)", ""]
    weekday_df = transit_df[~transit_df.departure.isin(WEEKEND_LABELS)]
    for label, df in [("transit weekday (pooled)", weekday_df)] + [(f"transit {d}", g) for d, g in transit_df.groupby("departure")] \
            + [("drive (predicted)", drive_df)]:
        block, chosen, reached = margin_lines(df, label)
        lines += block
        if label.startswith("transit weekday") or label.startswith("drive"):
            lines.append(f"  RULE margin: {chosen if chosen is not None else f'> {MAX_MARGIN_MIN}'} min")
            per_venue = reached.groupby("venue").d_min.agg(n="size", q95=lambda d: d.quantile(0.95), q99=lambda d: d.quantile(0.99))
            lines.append(per_venue.to_string(float_format=lambda x: f"{x:+.1f}"))
        lines.append("")
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    {"transit": route_transit, "drive": route_drive, "report": report}[sys.argv[1]]()
