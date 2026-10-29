"""Reach and catchment for a handful of venues: how much does the answer depend on which venue is the subject?

Question (user, 2026-10-22, after the 69th autonomous run): another sensitivity dimension is the subject itself;
pick some venues at random, a few fixed departure times as a light stand-in for opening hours, and compare their
reach and catchments. Report only.

Venues: the subject ([subject] Brunswick East, hex 0), [subject] Melbourne Central (the other fixed venue of the hours pull,
CBD), and PER_RING random venue hexes per ring of haversine distance to the subject (inner < 5 km, mid 5-25, outer
>= 25), seeded.
Drive (band 3): the 2tier all-pairs model on the blind bundle, reversed graph from the venue hex's eligible nodes
(as reachability_drive_pilot.py, copied, D1); catchment = residents / workers / venue count of grid hexes within
1,200 s predicted (cost <= 1,200 / ALPHA routed); time-blind (no RCH-14 factor).
Transit (bands 1-2): the frozen model (TRN-16: P1 + P3 + P2 jar, 4.143 km/h, v2 20261016, 1-min window, p49) or
stock R5 (r5py's bundled jar, 4.143 km/h) as a control; origins = every non-empty hex within RADIUS_KM of any venue
(each venue counts only hexes within RADIUS_KM of itself), destinations = the venues, one TravelTimeMatrix per
departure plus walk-only once; pair time = min(transit, walk), seconds rounded half up for the patched jar; cap
CAP_MIN. Departures: DEPARTURES (Wednesday dinner, Saturday lunch; inside the subject's hours).
Guard: per venue, the farthest hex within 21 min against GUARD_SHARE x RADIUS_KM (beyond it, the radius may cut).

Conclusion (run 2026-10-22; report only; M0 routed, 68,394 origin hexes x 3 departures, 26 min; P0 not run, time):
  Drive <= 20 min residents vary ~3x across the 8 venues (subject 536k, inner 463-466k, Melbourne Central 412k, mid
  168-316k, outer 159-169k); workers up to 713k for the CBD-side venues. Transit <= 20 min varies ~16x: Melbourne
  Central 97k residents / 412k workers, inner 2 60k / 216k, subject 50k / 20k, inner 1 32k, mid 10-12k, outer 6k;
  transit is 4-24% of the drive catchment (subject 9%). Departure spread differs by venue: inner 1 17.8k-46.3k
  (2.6x), subject 35.8k-57.7k, Melbourne Central 92.6k-102.0k (stable), Geelong (outer 1) 6,579 at every departure:
  walking only, its buses are outside the three metro feeds (a coverage limit for regional venues). GUARD FAILS for
  5 of 8 venues (a hex within 21 min at 4.89-4.99 km of the 5 km radius: Melbourne Central, inner 1 and 2, mid 1,
  outer 2): their transit totals are lower bounds; a wider radius (~8 km or more near rail) is the next run (~1 h).
  Reading (Claude's): the subject is not typical; catchment levels and their time-of-day sensitivity depend
  strongly on the venue, so sensitivity results for the subject do not transfer as ratios to every venue.

Inputs (read only): the routing bundle, edge attrs, 2tier params, hex nodes table, hex grid and its layer parquets,
venues with hex, the frozen jar, the v2 network files. Self-contained (CLAUDE.md D1). No API calls. One JVM per
process. Usage: `python reachability_venue_compare.py drive`, `... route <M0|P0>`, `... report`.
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
NAME = "reachability_venue_compare"
CALIBRATION_DIR = PROJECT_ROOT / "outputs" / "pathing_calibration"
BUNDLE_DIR = CALIBRATION_DIR / "prepared_graphs" / f"split_drive_edges_timed_blind_{FILE_TAG}_routing_b0_2"
EDGE_ATTRS_PATH = CALIBRATION_DIR / "fit" / SUBJECT / f"edge_attrs_{FILE_TAG}.npz"
PARAMS_PATH = CALIBRATION_DIR / "fit" / "model" / SUBJECT / "2tier_all_pairs_params.json"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"
HEX_DIR = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT
HEX_VENUES_PATH = HEX_DIR / f"hex_venue_counts_ven20260925_{SUBJECT}.parquet"
VENUES_WITH_HEX_PATH = HEX_DIR / f"venues_with_hex_ven20260925_{SUBJECT}.csv"
V2_NAME = "transit_pathway_network_v2"
RELEASE = "20261016"
V2_PBF_PATH = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{RELEASE}.osm.pbf"
V2_FEED_DIR = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{RELEASE}"
V2_FEED_PATHS = [V2_FEED_DIR / f"ptv_metro_train_{V2_NAME}_{RELEASE}_moved.zip",
                 V2_FEED_DIR / f"ptv_tram_{V2_NAME}_{RELEASE}.zip",
                 V2_FEED_DIR / f"ptv_metro_bus_{V2_NAME}_{RELEASE}.zip"]
FROZEN_JAR_PATH = PROJECT_ROOT / "outputs" / "r5_patches" / "r5-v7.5.1-r5py-all_transit_r5_patch_connector_p2.jar"
FROZEN_JAR_SHA256 = "62a8f6c1afa2e0a0c86860e336da499f9344e46e6c6d259d9c4824d129e68eb3"

# --- values ----------------------------------------------------------------------------------------
SUBJECT_LAT, SUBJECT_LON = -37.7687014, 144.9719611
FIXED_VENUES = {"subject (Brunswick East)": 0, "[subject] Melbourne Central": 10873}   # hex ids
RING_EDGES_KM = [0, 5, 25, np.inf]
RING_LABELS = ["inner", "mid", "outer"]
PER_RING = 2
SEED = 20261023
RADIUS_KM = 5.0
GUARD_SHARE = 0.8
GUARD_MIN = 21
BAND_3_PREDICTED_S = 1200
CUTS_MIN = [10, 20]
CAP_MIN = 22
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
SPEED_KMH = 4.143
R5_MAX_MEMORY = "7G"
DEPARTURES = [datetime.datetime(2026, 10, 28, 18, 0), datetime.datetime(2026, 10, 28, 20, 0),
              datetime.datetime(2026, 10, 31, 13, 0)]
VARIANTS = {"M0": True, "P0": False}            # frozen jar?
TIE_WINDOW_M = 1
MIN_CSR_WEIGHT = 1e-9
SECONDS_PER_MIN = 60
EARTH_RADIUS_M = 6_371_000
WEIGHTS = ["residents", "workers", "venue_count"]


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def hexes():
    """Grid hexes with nodes, centroids and weights (venue_count joined from its layer)."""
    import pyogrio
    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False, columns=[
        "hex_id", "centroid_lat", "centroid_lon", "drive_node_1", "drive_node_2", "drive_road_dist_1_m",
        "drive_road_dist_2_m", "residents", "workers"])
    venues_df = pd.read_parquet(HEX_VENUES_PATH)[["hex_id", "venue_count"]]
    hex_df = hex_df.merge(venues_df, on="hex_id", how="left")
    for weight in WEIGHTS:
        hex_df[weight] = hex_df[weight].fillna(0)
    return hex_df


def pick_venues(hex_df):
    """Fixed venues plus PER_RING random venue hexes per ring (seeded); saved once per run date."""
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_venues.csv"
    if path.exists():
        return pd.read_csv(path)
    venue_hexes = pd.read_csv(VENUES_WITH_HEX_PATH, usecols=["hex_id"]).hex_id.dropna().astype(np.int64).unique()
    candidates = hex_df[hex_df.hex_id.isin(venue_hexes) & ~hex_df.hex_id.isin(FIXED_VENUES.values())].copy()
    candidates["ring"] = pd.cut(haversine_m(SUBJECT_LAT, SUBJECT_LON, candidates.centroid_lat, candidates.centroid_lon) / 1000,
                                RING_EDGES_KM, labels=RING_LABELS, right=False)
    rng = np.random.default_rng(SEED)
    rows = [{"label": label, "hex_id": hex_id} for label, hex_id in FIXED_VENUES.items()]
    for ring in RING_LABELS:
        members = candidates[candidates.ring == ring]
        for k, i in enumerate(rng.choice(len(members), size=PER_RING, replace=False)):
            rows.append({"label": f"random {ring} {k + 1}", "hex_id": int(members.hex_id.iat[i])})
    venues_df = pd.DataFrame(rows).merge(hex_df[["hex_id", "centroid_lat", "centroid_lon"]], on="hex_id")
    venues_df["km_from_subject"] = haversine_m(SUBJECT_LAT, SUBJECT_LON, venues_df.centroid_lat, venues_df.centroid_lon) / 1000
    venues_df.to_csv(path, index=False)
    return venues_df


def drive():
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    hex_df = hexes()
    venues_df = pick_venues(hex_df)
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    (low, high), = params["groups"]
    indptr, indices = np.load(BUNDLE_DIR / "indptr.npy"), np.load(BUNDLE_DIR / "indices.npy")
    nodes, signals = np.load(BUNDLE_DIR / "nodes.npy"), np.load(BUNDLE_DIR / "signals.npy")
    with np.load(EDGE_ATTRS_PATH) as attrs:
        level = attrs["level"]
    weight = np.maximum(np.load(BUNDLE_DIR / "raw_time_raw_s.npy") * np.where((level >= low) & (level <= high),
                        params["multipliers"][0], 1.0) + params["beta"] * signals[indices], MIN_CSR_WEIGHT)
    reverse = csr_matrix((weight, indices, indptr), shape=(len(nodes),) * 2).T.tocsr()
    row_1 = np.searchsorted(nodes, hex_df.drive_node_1.to_numpy(np.int64))
    node_2 = hex_df.drive_node_2.to_numpy()
    is_2 = (~np.isnan(node_2) & (hex_df.drive_road_dist_2_m.to_numpy() - hex_df.drive_road_dist_1_m.to_numpy() <= TIE_WINDOW_M)
            & (node_2 != hex_df.drive_node_1.to_numpy()))
    row_2 = np.where(is_2, np.searchsorted(nodes, np.nan_to_num(node_2).astype(np.int64)), -1)
    position = pd.Series(np.arange(len(hex_df)), index=hex_df.hex_id.to_numpy())
    cut = BAND_3_PREDICTED_S / params["alpha"]
    rows = []
    for venue in venues_df.itertuples():
        pos = int(position[venue.hex_id])
        sources = [row_1[pos]] + ([row_2[pos]] if row_2[pos] >= 0 else [])
        dist = dijkstra(reverse, directed=True, indices=sources, min_only=True, limit=cut)
        inside = np.minimum(dist[row_1], np.where(row_2 >= 0, dist[np.maximum(row_2, 0)], np.inf)) <= cut
        rows.append({"hex_id": venue.hex_id, "hexes": int(inside.sum()), **{w: float(hex_df[w].to_numpy()[inside].sum()) for w in WEIGHTS}})
    pd.DataFrame(rows).to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_drive.csv", index=False)
    print(pd.DataFrame(rows).to_string())


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (from transit_catchment_sensitivity)."""
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


def route(variant):
    is_frozen = VARIANTS[variant]
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_transit_{variant}.csv"
    assert not out_path.exists(), f"{out_path.name} exists (one run per day)"
    hex_df = hexes()
    venues_df = pick_venues(hex_df)
    is_nonempty = (hex_df[WEIGHTS] > 0).any(axis=1).to_numpy()
    near = np.zeros(len(hex_df), bool)
    for venue in venues_df.itertuples():
        near |= haversine_m(venue.centroid_lat, venue.centroid_lon, hex_df.centroid_lat.to_numpy(),
                            hex_df.centroid_lon.to_numpy()) <= RADIUS_KM * 1000
    origin_df = hex_df[near & is_nonempty]
    print(f"{variant}: {len(venues_df)} venues, {len(origin_df):,} origin hexes", flush=True)
    sys.argv += ["--max-memory", R5_MAX_MEMORY]
    if is_frozen:
        with open(FROZEN_JAR_PATH, "rb") as file:
            assert hashlib.file_digest(file, "sha256").hexdigest() == FROZEN_JAR_SHA256, "not the frozen jar"
        sys.argv += ["--r5-classpath", str(FROZEN_JAR_PATH)]
    import geopandas as gpd
    import jpype
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    location = str(jpype.JClass("com.conveyal.r5.profile.FastRaptorWorker").class_.getProtectionDomain()
                   .getCodeSource().getLocation().toURI())
    assert (Path(location.removeprefix("file:/")).resolve() == FROZEN_JAR_PATH.resolve()) == is_frozen, location
    check_working_copies([V2_PBF_PATH] + V2_FEED_PATHS)
    network = TransportNetwork(V2_PBF_PATH, V2_FEED_PATHS)
    origins = gpd.GeoDataFrame({"id": origin_df.hex_id}, crs="EPSG:4326",
                               geometry=gpd.points_from_xy(origin_df.centroid_lon, origin_df.centroid_lat))
    # destination ids offset so no origin id equals a destination id (r5py reads from_id == to_id as 0)
    destinations = gpd.GeoDataFrame({"id": -1 - venues_df.hex_id}, crs="EPSG:4326",
                                    geometry=gpd.points_from_xy(venues_df.centroid_lon, venues_df.centroid_lat))

    def ttm(departure, modes):
        return pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=modes, max_time=datetime.timedelta(minutes=CAP_MIN), speed_walking=SPEED_KMH))

    started = datetime.datetime.now()
    walk_df = ttm(DEPARTURES[0], [TransportMode.WALK]).rename(columns={f"travel_time_p{SINGLE_PERCENTILE}": "walk"})
    frames = []
    for dep_no, departure in enumerate(DEPARTURES):
        transit_df = ttm(departure, [TransportMode.TRANSIT, TransportMode.WALK])
        transit_df = transit_df.rename(columns={f"travel_time_p{SINGLE_PERCENTILE}": "transit"}).merge(
            walk_df, on=["from_id", "to_id"], how="left")
        transit_df["dep_no"] = dep_no
        frames.append(transit_df.dropna(subset=["transit", "walk"], how="all"))
        print(f"  {departure}: {datetime.datetime.now() - started}", flush=True)
    table_df = pd.concat(frames, ignore_index=True)
    table_df["venue_hex"] = -1 - table_df.to_id
    table_df["unit"] = "s" if is_frozen else "min"
    table_df.to_csv(out_path, index=False)
    print(f"{variant} done in {datetime.datetime.now() - started}", flush=True)


def transit_totals(variant, hex_df, venues_df):
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_transit_{variant}.csv"
    if not path.exists():
        return None
    table_df = pd.read_csv(path)
    time = np.fmin(table_df.transit.to_numpy(float), table_df.walk.to_numpy(float))
    time = np.where(np.isnan(time), np.inf, time)
    if (table_df.unit == "s").all():
        time = np.floor(time / SECONDS_PER_MIN + 0.5)
    table_df["minutes"] = time
    table_df = table_df.merge(hex_df[["hex_id", "centroid_lat", "centroid_lon"] + WEIGHTS], left_on="from_id", right_on="hex_id")
    venue_xy = venues_df.set_index("hex_id")[["centroid_lat", "centroid_lon"]]
    table_df["km"] = haversine_m(table_df.centroid_lat, table_df.centroid_lon,
                                 venue_xy.centroid_lat.reindex(table_df.venue_hex).to_numpy(),
                                 venue_xy.centroid_lon.reindex(table_df.venue_hex).to_numpy()) / 1000
    table_df = table_df[table_df.km <= RADIUS_KM]
    rows = []
    for (venue_hex, dep_no), part in table_df.groupby(["venue_hex", "dep_no"]):
        row = {"venue_hex": venue_hex, "dep_no": dep_no,
               "guard_km": float(part.loc[part.minutes <= GUARD_MIN, "km"].max()) if (part.minutes <= GUARD_MIN).any() else 0.0}
        for cut in CUTS_MIN:
            for weight in WEIGHTS:
                row[f"{weight}_{cut}"] = float(part.loc[part.minutes <= cut, weight].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def report():
    hex_df = hexes()
    venues_df = pick_venues(hex_df)
    drive_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_drive.csv").set_index("hex_id")
    lines = [f"{NAME} {run_date()}: {len(venues_df)} venues; transit departures "
             + ", ".join(f"{d:%a %H:%M}" for d in DEPARTURES) + f"; origins within {RADIUS_KM} km per venue",
             "venue (km from subject): drive <= 20 residents / workers / venues | transit M0 <= 10, <= 20 residents / "
             "workers / venues (mean over departures; residents range) | guard km (max) | P0 / M0 residents at 20"]
    totals = {variant: transit_totals(variant, hex_df, venues_df) for variant in VARIANTS}
    for venue in venues_df.itertuples():
        d = drive_df.loc[venue.hex_id]
        text = (f"  {venue.label} ({venue.km_from_subject:.1f} km): drive {d.residents:,.0f} / {d.workers:,.0f} / "
                f"{d.venue_count:,.0f}")
        m0 = totals["M0"]
        if m0 is not None:
            part = m0[m0.venue_hex == venue.hex_id]
            if len(part):
                text += (f" | transit 10: {part.residents_10.mean():,.0f} / {part.workers_10.mean():,.0f} / "
                         f"{part.venue_count_10.mean():,.0f}; 20: {part.residents_20.mean():,.0f} / {part.workers_20.mean():,.0f} / "
                         f"{part.venue_count_20.mean():,.0f} (residents {part.residents_20.min():,.0f}-{part.residents_20.max():,.0f})"
                         f" | guard {part.guard_km.max():.2f} km")
            else:
                text += " | transit: nothing within the cap"
            p0 = totals["P0"]
            if p0 is not None and len(part):
                p_part = p0[p0.venue_hex == venue.hex_id].set_index("dep_no")
                ratio = p_part.residents_20.reindex(part.dep_no).to_numpy() / part.residents_20.to_numpy()
                text += f" | P0 / M0 {np.nanmean(ratio):.3f}"
        lines.append(text)
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    {"drive": drive, "route": route, "report": report}[sys.argv[1]](*sys.argv[2:3])
