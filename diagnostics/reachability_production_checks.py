"""Reachability production checks: does the production pass reproduce the diagnostics it was ported from?

Claim under test (concepts/reachability.md RCH-18; HANDOFF 82nd, steps 2-4): production recomputes everything (user,
82nd); the diagnostics' saved outputs serve only as equivalence checks. Where the pipeline relies on it: reachability.py
(build_transit_network, drive_pass, transit_subject_pass) and functions/pt_pathways.py, reachability_drive.py,
transit_oracle.py, ported from transit_pathway_network_v2.py, reachability_drive_pilot.py, reachability_graph_oracle.py.

Checks (Claude's rules, not user-approved; written 2026-10-23 before any production output existed):
  network  (N1) the production release folder's hubs and spurs tables equal the v2 diagnostic's for release 20261016
           (every value; floats to 1e-9); (N2) every table of every production feed equals the v2 diagnostic's copy
           (member contents byte for byte; zip metadata ignored); (N3) the derived extracts: byte-identical, else
           reported (routing decides). Any N1 / N2 difference fails.
  route    one process per network (`route production`, `route diagnostic`), frozen jar (TRN-16), 300 origins from
           transit_departure_sampling's origin sample (seeded) to every venue hex, Wed 2026-10-28 18:00, 1-min window,
           max 31 min, 4.143 km/h; (N4, `compare`) every pair's time equal (union of reached pairs). Any difference
           fails.
  drive    (D1) the production drive pass's rows for the pilot's 102 venue hexes equal the pilot's 2.5x rows
           (source hex, node, cost s), as sets; any difference fails.
  oracle   (O1) the production envelope's subject oracle seconds at slots Mon-Thu 19:30 and Fri 18:30 equal the
           graph oracle diagnostic's saved values at cut 30 (subject = venue hex 0) on every hex both saved, where
           either is <= 30 min, within 1e-3 s; hexes inside the 30-min set on one side only are listed; any fails.

Conclusion (run 2026-10-23, 83rd autonomous; Claude's rules above): network N1 + N2 PASS (hubs 576, spurs 2,751,
  every feed table equal) and N3 the derived extract byte-identical, so N4 (routing) was not run: identical inputs.
  drive D1 PASS (112,263,009 rows, 0 on one side only). oracle O1 PASS (Mon-Thu 19:30: 339 hexes compared, 0 differ,
  0 saved-set hexes missing from the envelope; Fri 18:30: 290, 0, 0). The first oracle run compared only hexes both
  sides saved (inner join), so a saved-set hex missing from the envelope would not have shown; the "one side only"
  count was added and rerun the same day (still PASS). Only ~3% of the set is compared (the saved oracle holds its
  sample and bands), as the saved data allows.
Inputs (read only): production outputs under outputs/reachability/; the diagnostics' saved data. Self-contained
(CLAUDE.md D1). No API calls. Usage: `python reachability_production_checks.py network | route production |
route diagnostic | compare | drive | oracle`.
"""
import datetime
import hashlib
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "reachability_production_checks"
SUBJECT = "-37.76870_144.97196"
FILE_TAG = f"res2021_wrk2021_ven20260925_{SUBJECT}"
RELEASE = "20261016"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
V2_NAME = "transit_pathway_network_v2"
V2_RUN_DATE = "20261019"
PRODUCTION_NETWORK_DIR = PROJECT_ROOT / "outputs" / "reachability" / "network" / RELEASE
PRODUCTION_TAG = "reach"
REACH_DIR = PROJECT_ROOT / "outputs" / "reachability" / SUBJECT
FROZEN_JAR_PATH = PROJECT_ROOT / "outputs" / "r5_patches" / "r5-v7.5.1-r5py-all_transit_r5_patch_connector_p2.jar"
FROZEN_JAR_SHA256 = "62a8f6c1afa2e0a0c86860e336da499f9344e46e6c6d259d9c4824d129e68eb3"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"
VENUES_WITH_HEX_PATH = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT / f"venues_with_hex_ven20260925_{SUBJECT}.csv"
ORIGIN_SAMPLE_PATH = DIAGNOSTIC_DATA_DIR / "transit_departure_sampling_routes_20261023" / "origin_sample.csv"
PILOT_ROWS_PATH = DIAGNOSTIC_DATA_DIR / "reachability_drive_pilot_20261022_rows_x2.5.parquet"
ORACLE_PATH = DIAGNOSTIC_DATA_DIR / "reachability_graph_oracle_20261022_superset_oracle.parquet"
R5_MAX_MEMORY = "7G"
SPEED_KMH = 4.143
MAX_TIME_MIN = 31
ROUTE_ORIGINS = 300
ROUTE_DEPARTURE = datetime.datetime(2026, 10, 28, 18, 0)
SINGLE_PERCENTILE = 49
SEED = 20261023
FLOAT_TOL = 1e-9
ORACLE_TOL_S = 1e-3
ORACLE_CUT_MIN = 30
SECONDS_PER_MIN = 60
SUBJECT_VENUE_HEX = 0
ORACLE_SLOTS = {"Mon-Thu 19:30": ("Mon-Thu", "19:30"), "Fri 18:30": ("Fri", "18:30")}


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def write(mode, lines):
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_{mode}.txt").write_text(text + "\n", encoding="utf-8", newline="\n")


def network_files(which):
    """(derived extract, [train (moved), tram, bus]) of the production or the v2 diagnostic network."""
    if which == "production":
        return (PRODUCTION_NETWORK_DIR / f"osm_pathways_{PRODUCTION_TAG}_{RELEASE}.osm.pbf",
                [PRODUCTION_NETWORK_DIR / (f"{n}_{PRODUCTION_TAG}_{RELEASE}_moved.zip" if n == TRAIN_FEED
                                           else f"{n}_{PRODUCTION_TAG}_{RELEASE}.zip") for n in FEED_NAMES])
    feed_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{RELEASE}"
    return (DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{RELEASE}.osm.pbf",
            [feed_dir / (f"{n}_{V2_NAME}_{RELEASE}_moved.zip" if n == TRAIN_FEED else f"{n}_{V2_NAME}_{RELEASE}.zip")
             for n in FEED_NAMES])


def sha256(path):
    with open(path, "rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def frames_equal(a_df, b_df):
    if list(a_df.columns) != list(b_df.columns) or len(a_df) != len(b_df):
        return False
    for column in a_df.columns:
        a, b = a_df[column].to_numpy(), b_df[column].to_numpy()
        if a.dtype.kind == "f" or b.dtype.kind == "f":
            if not np.allclose(a.astype(float), b.astype(float), rtol=0, atol=FLOAT_TOL, equal_nan=True):
                return False
        elif not np.array_equal(a.astype(str), b.astype(str)):
            return False
    return True


def check_network():
    lines = [f"{NAME} {run_date()} network: production {PRODUCTION_NETWORK_DIR.relative_to(PROJECT_ROOT)} vs "
             f"{V2_NAME} release {RELEASE}"]
    is_ok = True
    for table in ["hubs", "spurs"]:
        production_df = pd.read_csv(PRODUCTION_NETWORK_DIR / f"{table}_{RELEASE}.csv")
        diagnostic_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_{V2_RUN_DATE}_{table}_{RELEASE}.csv")
        same = frames_equal(production_df, diagnostic_df)
        is_ok &= same
        lines.append(f"(N1) {table}: {len(production_df)} vs {len(diagnostic_df)} rows: {'equal' if same else 'DIFFER'}")
    production_pbf, production_feeds = network_files("production")
    diagnostic_pbf, diagnostic_feeds = network_files("diagnostic")
    for production, diagnostic in zip(production_feeds, diagnostic_feeds):
        with zipfile.ZipFile(production) as a_zip, zipfile.ZipFile(diagnostic) as b_zip:
            a_names, b_names = sorted(a_zip.namelist()), sorted(b_zip.namelist())
            differing = [n for n in set(a_names) & set(b_names) if a_zip.read(n) != b_zip.read(n)]
        same = a_names == b_names and not differing
        is_ok &= same
        lines.append(f"(N2) {production.name} vs {diagnostic.name}: members {len(a_names)} / {len(b_names)}, "
                     f"differing {sorted(differing)}: {'equal' if same else 'DIFFER'}")
    same_pbf = sha256(production_pbf) == sha256(diagnostic_pbf)
    lines.append(f"(N3) derived extract byte-identical: {same_pbf} (report only)")
    lines.append(f"N1 + N2: {'PASS' if is_ok else 'FAIL'}")
    write("network", lines)


def route(which):
    """Frozen-model times on one network (one JVM per process)."""
    import geopandas as gpd
    import pyogrio
    assert sha256(FROZEN_JAR_PATH) == FROZEN_JAR_SHA256, "not the frozen jar"
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(FROZEN_JAR_PATH)]
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    pbf_path, gtfs = network_files(which)
    network = TransportNetwork(pbf_path, gtfs)
    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False, columns=["hex_id", "centroid_lat", "centroid_lon"])
    venue_ids = pd.read_csv(VENUES_WITH_HEX_PATH, usecols=["hex_id"]).hex_id.dropna().astype(np.int64).unique()
    sample_ids = np.sort(pd.read_csv(ORIGIN_SAMPLE_PATH).hex_id.unique())
    origin_ids = np.random.default_rng(SEED).choice(sample_ids, ROUTE_ORIGINS, replace=False)

    def points(df):
        return gpd.GeoDataFrame({"id": df.hex_id.to_numpy()}, crs="EPSG:4326",
                                geometry=gpd.points_from_xy(df.centroid_lon, df.centroid_lat))

    matrix_df = pd.DataFrame(TravelTimeMatrix(
        network, origins=points(hex_df[hex_df.hex_id.isin(origin_ids)]),
        destinations=points(hex_df[hex_df.hex_id.isin(venue_ids)]), departure=ROUTE_DEPARTURE,
        departure_time_window=datetime.timedelta(minutes=1), percentiles=[SINGLE_PERCENTILE],
        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=datetime.timedelta(minutes=MAX_TIME_MIN),
        speed_walking=SPEED_KMH))
    column = f"travel_time_p{SINGLE_PERCENTILE}"
    matrix_df.dropna(subset=[column])[["from_id", "to_id", column]].to_parquet(
        DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_route_{which}.parquet", index=False)
    print(f"route {which}: {matrix_df[column].notna().sum():,} reached pairs")


def compare():
    column = f"travel_time_p{SINGLE_PERCENTILE}"
    a_df, b_df = [pd.read_parquet(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_route_{w}.parquet")
                  .set_index(["from_id", "to_id"])[column] for w in ("production", "diagnostic")]
    both = pd.concat([a_df.rename("production"), b_df.rename("diagnostic")], axis=1)
    bad = both[both.production.fillna(-1) != both.diagnostic.fillna(-1)]
    lines = [f"{NAME} {run_date()} route: {ROUTE_ORIGINS} origins x venue hexes, {ROUTE_DEPARTURE:%a %Y-%m-%d %H:%M}, "
             f"frozen jar; reached pairs production {a_df.size:,}, diagnostic {b_df.size:,}",
             f"(N4) differing pairs {len(bad)} of {len(both):,}: {'PASS' if bad.empty else 'FAIL'}"]
    lines += [f"    {i}: production {r.production}, diagnostic {r.diagnostic}" for i, r in bad.head(20).iterrows()]
    write("route", lines)


def newest_pass(kind):
    folders = sorted(REACH_DIR.glob(f"{kind}_*"), key=lambda p: p.stat().st_mtime)
    assert folders, f"no {kind} pass under {REACH_DIR}"
    return folders[-1]


def check_drive():
    import pyarrow.dataset as ds
    pilot_df = pd.read_parquet(PILOT_ROWS_PATH)
    hexes = np.unique(pilot_df.source_hex)
    folder = newest_pass("drive")
    production_df = (ds.dataset(sorted(folder.glob("costs_*.parquet")), format="parquet")
                     .to_table(filter=ds.field("source_hex").isin(hexes)).to_pandas())
    key = ["source_hex", "node", "cost_s"]
    merged = pilot_df[key].merge(production_df[key], on=key, how="outer", indicator=True)
    only = merged._merge.value_counts()
    is_ok = only.get("left_only", 0) == 0 and only.get("right_only", 0) == 0
    lines = [f"{NAME} {run_date()} drive: {folder.relative_to(PROJECT_ROOT)} vs the pilot's 2.5x rows, "
             f"{len(hexes)} venue hexes",
             f"(D1) rows pilot {len(pilot_df):,}, production {len(production_df):,}; pilot only "
             f"{only.get('left_only', 0):,}, production only {only.get('right_only', 0):,}: {'PASS' if is_ok else 'FAIL'}"]
    write("drive", lines)


def check_oracle():
    saved_df = pd.read_parquet(ORACLE_PATH)
    saved_df = saved_df[(saved_df.venue_hex == SUBJECT_VENUE_HEX) & (saved_df.cut_min == ORACLE_CUT_MIN)]
    folder = newest_pass("transit")
    cut_s = ORACLE_CUT_MIN * SECONDS_PER_MIN
    lines = [f"{NAME} {run_date()} oracle: {folder.relative_to(PROJECT_ROOT)} envelopes vs {ORACLE_PATH.name} "
             f"(subject, cut {ORACLE_CUT_MIN})"]
    is_ok = True
    for label, (day_type, clock) in ORACLE_SLOTS.items():
        chunk_dirs = [d for d in folder.glob(f"{day_type}_*") if clock in pd.read_csv(d / "envelope.csv", nrows=0).columns]
        assert len(chunk_dirs) == 1, f"{label}: {len(chunk_dirs)} chunks hold the slot"
        production = pd.read_csv(chunk_dirs[0] / "envelope.csv", usecols=["hex_id", clock]).set_index("hex_id")[clock]
        saved = saved_df[saved_df.slot == label].set_index("hex_id").oracle_s
        envelope_hexes = production.index
        saved_only = saved[(saved <= cut_s) & ~saved.index.isin(envelope_hexes)]   # in the saved set, not in the envelope
        is_ok &= saved_only.empty
        lines.append(f"(O1) {label}: saved hexes <= {ORACLE_CUT_MIN} min missing from the production envelope: "
                     f"{len(saved_only)}")
        both = pd.concat([production.rename("production"), saved.rename("saved")], axis=1, join="inner")
        both = both[(both.production <= cut_s) | (both.saved <= cut_s)]
        differ = both[~np.isclose(both.production.fillna(np.inf), both.saved.fillna(np.inf), rtol=0, atol=ORACLE_TOL_S)]
        is_ok &= differ.empty
        lines.append(f"(O1) {label}: {len(both):,} hexes compared (saved {len(saved):,}, production set "
                     f"{int((production <= cut_s).sum()):,}); differing {len(differ)}")
        lines += [f"    hex {i}: production {r.production}, saved {r.saved}" for i, r in differ.head(20).iterrows()]
    lines.append(f"O1: {'PASS' if is_ok else 'FAIL'}")
    write("oracle", lines)


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "network":
        check_network()
    elif mode == "route":
        route(sys.argv[2])
    elif mode == "compare":
        compare()
    elif mode == "drive":
        check_drive()
    elif mode == "oracle":
        check_oracle()
