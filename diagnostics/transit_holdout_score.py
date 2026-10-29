"""Freeze record and holdout scorer: does the frozen transit band model hold on pairs nothing was fitted or read on?

Claim under test (concepts/transit.md TRN-15, TRN-16; DESIGN.md Q23, Q24): the frozen model passes TRN-13's zone checks
on the fresh holdout, with its hard misses a recorded cost, not barred. Where the pipeline relies on it: transit
bands 1-2 (SCR-1, RCH-1) before they go into reachability (RCH-18).

FREEZE RECORD (written 2026-10-22, 67th, before any holdout answer is compared with R5; user OK):
  Model: R5 7.5.1 through r5py with three source patches (TRN-16): P1 first board wait 0 s, P3 transfer board wait
    200 s (FastRaptorWorker), P2 connector convention (StreetRouter / LinkedPointSet); jar
    outputs/r5_patches/r5-v7.5.1-r5py-all_transit_r5_patch_connector_p2.jar, sha256 FROZEN_JAR_SHA256 below.
    Walk 4.143 km/h (Q24 (2)), v2 pathways network of each pair's release, drawn points, TravelTimeMatrix at a 1-min
    window, percentile 49, max 90 min; pair time = min(transit, walk) seconds, rounded to the nearest minute half up
    (SCR-10); cuts 10 / 20 (bands 1-2). Google's time a range: earliest of its first 2 in-scope routes to its default
    (k = 2). Nothing in this list changes after the freeze; a change is a new model and needs a new holdout.
  Holdout reading rule (TRN-15's test rule, user 2026-10-20, carried over; settled points from the 66th):
    Pairs: the 4,000 holdout pairs (release 20261016, own departure dates Oct 22 - Nov 2), scored where Google's
      default is in scope (TRN-11). One release, all random, so pooled = the holdout and no per-release split.
    (1) Zones 7-13 / 17-23: floor (both Wilson lowers > 0.6), noise bar (from the holdout's own off-cut pairs,
        centred), balance (sign p >= 0.05 and |recall - precision| <= 0.10). (2) Hard misses per cut, Wilson upper
        <= 0.05; a fail is a recorded cost, barred if severe (upper > 0.10, n >= 35) or concentrated (>= 5 misses,
        >= 2/3 in one service third holding < 1/3 of the tested pairs; thirds fixed at training: low <= 36,
        mid 37-130, high >= 131 origin trips). (3) Lost 10 report-only. (4) Count ratio 0.90-1.10: a fail a
        recorded cost, never a bar alone. (5) Medians beside means. (6) The tail (|model - default| > 20 min) is
        counted and reported, never excluded from the verdict. (7) Report-only: the unseen-destination subset
        (destination hex in no training set: training half, second batch, top-up; TRN-15 (9)), the subset unseen by
        any scored set (old test too), and breakdowns by Google default's mode (walk / bus / tram / train-involved,
        the pathways reading) and boardings.
  Order: freeze -> check (scorer reproduces the model's training tables) -> seen (old test re-routed, report-only)
    -> predictions -> holdout, opened once.

Seen pairs (report-only, never a validation): the training sets were fitted on; the old test (test half 1,248 +
extension 4,000, opened 2026-10-20 on the no-wait model) shaped what was worked on after, though no value was fitted
on it. `seen` reports training, old test (before / after on the same pairs), and all seen pooled.

Checks: (F0) the jar's sha256 equals FROZEN_JAR_SHA256 (every route and score mode). (C1, `check`) on the training
sets, the model's minutes equal transit_r5_patch_connector's saved p2orig_min on every pair, and the hard misses and
count ratios equal the model of record's (transit_buffer_sweep b = 200): lost 10 0/50, false 10 2/294, lost 20
7/248, false 20 14/503, ratios 0.981 / 1.042. `holdout` refuses to run unless today's check says PASS and the
predictions file exists.

Seen (run 2026-10-22, report-only): C1 PASS (3,448 / 3,448 minutes, every table value). Old test re-routed on the
  frozen jar: hard misses 49 -> 31 on the same 5,234 scored pairs (lost 10 0 -> 1, false 10 4 -> 3, lost 20 11 -> 9,
  false 20 34 -> 18), 61 band calls change; every check passes pooled (z1 floor 0.790, z2 0.872; ratios 0.989 / 1.042);
  release 20261009 alone fails false 10 / lost 20 / false 20 and ratio <= 20 (n 90-190, none severe). All seen pooled
  (8,473 random): every check passes (lost 20 16/665, false 20 32/1,295, ratios 0.986 / 1.042). Train-involved defaults
  carry lost 20 at 5/24 (R5 late near 20 on train trips; the pathways reading), tram most of false 20 (17/32).
Predictions (written 2026-10-22 before the opening). User: the holdout looks like the seen pairs (same draw, nothing
  fitted on it); maybe more hard misses, the transfer work having been targeted; pathways worth watching. Claude:
  `predict` ranges (lost 20 3-14 misses, false 20 8-23, false 10 0-6, lost 10 0-3 report-only); zones pass (every
  seen subset of this size passes); ratios 0.96-1.06 / 1.01-1.07; median error 0, mean model - default about -2 min;
  tail about 1.2% of scored pairs (~45-50); train-involved lost 20 again the highest rate.
Conclusion (holdout opened 2026-10-22, autonomous 69th session; facts only, the reading is owed to the user): check
  PASS the same day. 4,000 pairs, 3,995 scored (5 out of scope); thirds low 1,315 / mid 1,319 / high 1,361.
  By the freeze record's rule: (1) zones pass: z1 recall 0.844 (81/96) precision 0.890 (81/91), floor 0.758, noise bar
  and balance ok (10e/15l p 0.424, gap 0.046); z2 recall 0.868 (210/242) precision 0.897 (210/234), floor 0.819,
  balance 24e/32l p 0.350, gap 0.030. (2) Hard misses: false 10 1/365 (upper 0.015) ok; false 20 15/603 (0.041) ok;
  lost 20 9/272 (upper 0.062) FAIL, not severe (<= 0.10) and not concentrated (thirds 2 / 4 / 3 of tested 38 / 54 /
  180), so a recorded cost, not barred (the training sets failed the same line, 7/248, upper 0.057). (3) Lost 10 1/70
  report-only. (4) Ratios 0.986 (146/148) / 1.044 (598/573) ok. (5) Away from the cuts: median +0.0, mean +0.29, inside
  0.52; model - default median 0, mean -1.84 min, MAE 3.00. (6) Tail 42 of 3,969 (1.06%).
  Against predictions: lost 20 9 in 3-14 (median 7; n 272 vs ~314 expected); false 20 15 in 8-23 (median 15); false 10
  1 in 0-6; lost 10 1 in 0-3; ratios inside 0.96-1.06 / 1.01-1.07; mean -1.84 near "about -2"; tail 42 just under
  ~45-50; zones pass as predicted. User's "maybe more hard misses": 26 total vs training's 23 on fewer pairs (3,215
  scored), rates alike. Train-involved lost 20 2/7, again the highest rate (n small); tram carries 4 of 9 lost 20 and
  8 of 15 false 20; misses all group 4 (R5 late, misses Google's ride) for lost 20.
  Report-only subsets: unseen by training (1,469 scored) fails lost 20 (1/62, upper 0.086) and false 20 (4/196, upper
  0.051) on the 5% line only (Wilson width at small n; rates 0.016 / 0.020 are below the holdout's); unseen by any seen
  set (753) fails z1 floor and balance on n 7-8 and every hard line on n 33-85 (rates 0.00-0.03 apart from lost 10
  1/5). Boardings: 2+ boardings mean -2.39 min (R5 earlier), 23 of 42 tail pairs.

Inputs (read only): the frozen jar, v2 networks and feeds, pair files, Google route tables and the holdout answer
file (departure dates only before the opening), saved training routes and service tables. Self-contained (CLAUDE.md
D1). No API calls. One JVM per process. Usage: `python transit_holdout_score.py route <set>` (test | test_ext |
holdout), `... route_all`, `... check`, `... seen`, `... predict`, `... holdout`.
"""
import datetime
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_holdout_score"
V2_NAME = "transit_pathway_network_v2"
RECORD_NAME = "transit_r5_patch_connector"
TEST_SCORE_NAME = "transit_test_score"
RANGE_NAME = "transit_hard_miss_range"
FROZEN_JAR_PATH = PROJECT_ROOT / "outputs" / "r5_patches" / f"r5-v7.5.1-r5py-all_{RECORD_NAME}_p2.jar"
FROZEN_JAR_SHA256 = "62a8f6c1afa2e0a0c86860e336da499f9344e46e6c6d259d9c4824d129e68eb3"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
RESERVE_PATH = SUBJECT_DIR / f"transit_pairs_reserve_{FILE_TAG}.csv"
TOPUP_PATH = SUBJECT_DIR / f"transit_pairs_topup_{FILE_TAG}.csv"
TOPUP_SELECTION_PATH = SUBJECT_DIR / f"transit_topup_selection_{FILE_TAG}.csv"
TEST_EXT_PATH = SUBJECT_DIR / f"transit_pairs_test_ext_{FILE_TAG}.csv"
HOLDOUT_PATH = SUBJECT_DIR / f"transit_pairs_holdout_{FILE_TAG}.csv"            # config.TRANSIT_HOLDOUT_PAIRS_PATH
HOLDOUT_ANSWERS_PATH = SUBJECT_DIR / f"transit_google_holdout_20261016_{FILE_TAG}.csv"
ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                "test": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv",
                "test_ext": SUBJECT_DIR / f"transit_google_test_ext_20261016_{FILE_TAG}.routes.csv",
                "holdout": SUBJECT_DIR / f"transit_google_holdout_20261016_{FILE_TAG}.routes.csv"}
CLEANED_DIRS = {20261009: PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned",
                20261016: DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016"}

# --- sets ------------------------------------------------------------------------------------------
SET_RELEASE = {"train": 20261009, "second": 20261016, "topup": 20261016, "test": 20261009, "test_ext": 20261016,
               "holdout": 20261016}
TRAINING_SETS = ["train", "second", "topup"]
OLD_TEST_SETS = ["test", "test_ext"]
ROUTED_SETS = OLD_TEST_SETS + ["holdout"]      # routed here with the frozen jar
TOPUP_SET = "topup"                            # not random: zones only, no hard test (TRN-13)

# --- the frozen model (values copied from transit_r5_patch_connector.py / transit_buffer_sweep.py) ----
R5_MAX_MEMORY = "7G"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
SPEED_KMH = 4.143                              # Q24 (2) median; user 2026-10-21
MAX_TIME_MIN = 90
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
GUARD_CLASSES = ["com.conveyal.r5.profile.FastRaptorWorker", "com.conveyal.r5.streets.StreetRouter",
                 "com.conveyal.r5.streets.LinkedPointSet", "com.conveyal.r5.analyst.TravelTimeReducer"]
PROGRESS_EVERY = 500

# --- scoring values (copied from transit_test_score.py) ----------------------------------------------
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]  # TRN-11
SECONDS_PER_MIN = 60
MIN_PER_HOUR = 60
ZONES_MIN = {1: (7, 13), 2: (17, 23)}
CUTS_MIN = {1: 10, 2: 20}
AWAY_RANGES_MIN = [(0, 6), (14, 16), (24, 30)]
GATING_K = 2
WILSON_Z = 1.959964
FLOOR = 0.6
N_SIMULATIONS = 2000
SIMULATION_SEED = 20261018
SIGN_TEST_ALPHA = 0.05
CLOSE_TOLERANCE = 0.10
COUNT_RATIO_RANGE = (0.90, 1.10)
HARD_WINDOW_NEAR_MIN = 3
HARD_WINDOW_FAR_MIN = 10
HARD_MISS_MAX = 0.05
SEVERE_MAX = 0.10
SEVERE_MIN_N = 35
REPORT_ONLY_TESTS = ["lost 10"]
CONCENTRATED_SHARE = 2 / 3
CONCENTRATION_MIN_MISSES = 5
CONCENTRATION_TESTED_MAX = 1 / 3
STRATUM_LOW_MAX_TRIPS = 36
STRATUM_HIGH_MIN_TRIPS = 131
STRATUM_LABELS = ["low", "mid", "high"]
HOME_WAIT_GROUP_S = 300
TRAM_TYPE = "TRAM"
TRAIN_TYPE = "HEAVY_RAIL"
TAIL_MIN = 20                                  # holdout rule (6)
MODE_GROUPS = ["walk", "bus", "tram", "tram+bus", "train-involved"]
BOARDING_GROUPS = ["0", "1", "2+"]

# --- service density (copied from transit_test_score.py) --------------------------------------------
SERVICE_RADIUS_M = 700
SERVICE_HALF_WINDOW_MIN = 30
EARTH_RADIUS_M = 6_371_008.8
STOP_TIMES_CHUNK_ROWS = 2_000_000
GTFS_ENCODING = "utf-8-sig"
WEEKDAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EXCEPTION_ADDED, EXCEPTION_REMOVED = 1, 2

# --- acceptance (C1): the model of record's training tables (transit_buffer_sweep_20261022, b = 200) --
EXPECTED_HARD = {"lost 10": (0, 50), "false 10": (2, 294), "lost 20": (7, 248), "false 20": (14, 503)}
EXPECTED_RATIOS = {10: "0.981", 20: "1.042"}

# --- predictions (Claude's method, written before the holdout is opened) -----------------------------
N_DRAWS = 4000
PRIOR = 0.5
PREDICTION_SEED = 20261022
PREDICTION_LEVEL = 0.90

PAIR_COLUMNS = ["draw_no", "origin_lat", "origin_lon", "dest_lat", "dest_lon", "dest_hex", "dep_min_of_day"]


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def newest(pattern):
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return saved[-1] if saved else None


def check_jar():
    """(F0) the frozen jar is the one the freeze record names."""
    with open(FROZEN_JAR_PATH, "rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    assert digest == FROZEN_JAR_SHA256, f"F0 FAIL: {FROZEN_JAR_PATH.name} sha256 {digest} != frozen {FROZEN_JAR_SHA256}"
    print(f"(F0) {FROZEN_JAR_PATH.name} sha256 matches the freeze record", flush=True)


# --- pairs -----------------------------------------------------------------------------------------
def pairs_of_set(set_name):
    if set_name in ("train", "test"):
        split_df = pd.read_csv(SPLIT_PATH, usecols=["draw_no", "half"])
        pairs_df = pd.read_csv(PAIRS_PATH, usecols=PAIR_COLUMNS)
        return pairs_df[pairs_df.draw_no.isin(split_df.draw_no[split_df.half == set_name])]
    if set_name == "second":
        return pd.read_csv(RESERVE_PATH, usecols=PAIR_COLUMNS)
    if set_name == "test_ext":
        return pd.read_csv(TEST_EXT_PATH, usecols=PAIR_COLUMNS)
    if set_name == "holdout":
        return pd.read_csv(HOLDOUT_PATH, usecols=PAIR_COLUMNS)
    topup_df = pd.read_csv(TOPUP_PATH, usecols=PAIR_COLUMNS)
    return topup_df[topup_df.draw_no.isin(pd.read_csv(TOPUP_SELECTION_PATH).draw_no)]


def own_dates(set_name):
    """Each pair's departure date as sent to Google (as transit_pathway_network_v2.own_dates)."""
    if set_name == "holdout":
        answers_df = pd.read_csv(HOLDOUT_ANSWERS_PATH, usecols=["draw_no", "departure_local"])
        return pd.DataFrame({"draw_no": answers_df.draw_no,
                             "own_date": pd.to_datetime(answers_df.departure_local.str[:10]).dt.date})
    release = SET_RELEASE[set_name]
    routes_df = pd.read_csv(newest(f"{V2_NAME}_2*_routes_test_{release}.csv"))
    routes_df = routes_df[routes_df.set_name == set_name]
    return pd.DataFrame({"draw_no": routes_df.draw_no, "own_date": pd.to_datetime(routes_df.own_date).dt.date})


# --- route (copied from transit_buffer_sweep.py) -----------------------------------------------------
def network_paths(release):
    feed_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{release}"
    pbf_path = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{release}.osm.pbf"
    gtfs = [feed_dir / (f"{name}_{V2_NAME}_{release}_moved.zip" if name == TRAIN_FEED else f"{name}_{V2_NAME}_{release}.zip")
            for name in FEED_NAMES]
    return pbf_path, gtfs


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (memory r5py-working-copy-cache)."""
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


def open_network(release):
    """Start the JVM on the frozen jar (guarded), load the release's v2 network; returns (network, ttm)."""
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(FROZEN_JAR_PATH)]   # r5py reads these at import
    import geopandas as gpd
    import jpype
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    for name in GUARD_CLASSES:
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == FROZEN_JAR_PATH.resolve(), f"{name} loaded from {location}"
    print(f"{', '.join(c.rsplit('.', 1)[1] for c in GUARD_CLASSES)} from {FROZEN_JAR_PATH.name}", flush=True)
    pbf_path, gtfs = network_paths(release)
    assert pbf_path.exists() and all(p.exists() for p in gtfs), "transit_pathway_network_v2 build / feeds first"
    check_working_copies([pbf_path] + gtfs)
    network = TransportNetwork(pbf_path, gtfs)

    def ttm(origin, destination, departure, is_transit):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([origin[1]], [origin[0]]))
        targets = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326",
                                   geometry=gpd.points_from_xy([destination[1]], [destination[0]]))
        transport_modes = [TransportMode.TRANSIT, TransportMode.WALK] if is_transit else [TransportMode.WALK]
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=targets, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=transport_modes, max_time=datetime.timedelta(minutes=MAX_TIME_MIN), speed_walking=SPEED_KMH))
        return float(matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0])

    return network, ttm


def route(set_name):
    """Route one set with the frozen jar on its release, each pair on its own date; appends a row per pair, resumes."""
    assert set_name in ROUTED_SETS
    check_jar()
    release = SET_RELEASE[set_name]
    pairs_df = pairs_of_set(set_name).merge(own_dates(set_name), on="draw_no", how="left", validate="one_to_one")
    assert pairs_df.own_date.notna().all(), "pairs without a departure date"
    saved = newest(f"{NAME}_2*_routes_{set_name}.csv")
    table_path = saved if saved is not None else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_routes_{set_name}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"{set_name} ({release}): {len(pairs_df)} pairs, {len(done)} done, {len(todo_df)} to route -> {table_path.name}",
          flush=True)
    if todo_df.empty:
        return
    network, ttm = open_network(str(release))
    for own_date in sorted(todo_df.own_date.unique()):
        assert network.transit_layer.covers(own_date), f"release {release} does not cover {own_date}"
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        origin, destination = (pair.origin_lat, pair.origin_lon), (pair.dest_lat, pair.dest_lon)
        departure = datetime.datetime.combine(pair.own_date, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))
        row = {"draw_no": pair.draw_no, "set_name": set_name, "release": release, "own_date": pair.own_date,
               "transit": ttm(origin, destination, departure, True), "walk": ttm(origin, destination, departure, False)}
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % PROGRESS_EVERY == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


def route_all():
    """The old test sets, then the holdout, each in its own process (one JVM per process); stops on a failure."""
    for set_name in ROUTED_SETS:
        print(f"== {set_name}", flush=True)
        subprocess.run([sys.executable, "-u", str(Path(__file__).resolve()), "route", set_name], check=True)


# --- load ------------------------------------------------------------------------------------------
def google_table(set_name, draw_nos):
    """Default minute, scope, range low (k = 2), default's wait / walk-only / vehicles / boardings (from transit_test_score)."""
    routes_df = pd.read_csv(ROUTES_PATHS[set_name])
    routes_df = routes_df[routes_df.draw_no.isin(draw_nos)].sort_values(["draw_no", "route_ix"])
    default_df = routes_df[routes_df.is_default].drop_duplicates("draw_no").set_index("draw_no")
    out_df = pd.DataFrame({"default_min": np.round(default_df.arrival_from_request_s / SECONDS_PER_MIN),
                           "default_s": default_df.arrival_from_request_s,
                           "is_scored": default_df.route_scope.isin(GOOGLE_SCOPES) & default_df.arrival_from_request_s.notna(),
                           "default_wait_s": default_df.leave_wait_s, "default_walk_only": default_df.is_walk_only,
                           "default_vehicles": default_df.vehicle_types.fillna(""),
                           "default_steps": default_df.n_transit_steps})
    usable_df = routes_df[routes_df.route_scope.isin(GOOGLE_SCOPES) & routes_df.arrival_from_request_s.notna()].copy()
    usable_df["minute"] = np.round(usable_df.arrival_from_request_s / SECONDS_PER_MIN)
    usable_df["rank"] = usable_df.groupby("draw_no").cumcount() + 1
    low = usable_df[usable_df["rank"] <= GATING_K].groupby("draw_no").minute.min().reindex(out_df.index)
    out_df[f"low_{GATING_K}"] = np.fmin(low.to_numpy(), out_df.default_min.to_numpy())
    return out_df.reset_index()


def routes_of(set_names):
    frames = []
    if any(name in TRAINING_SETS for name in set_names):
        record = pd.concat([pd.read_csv(newest(f"{RECORD_NAME}_2*_trainroutes_p2orig_{release}.csv"))
                            for release in (20261009, 20261016)], ignore_index=True)
        frames.append(record[["draw_no", "transit", "walk"]].assign(is_training=True))
    for name in set_names:
        if name in ROUTED_SETS:
            path = newest(f"{NAME}_2*_routes_{name}.csv")
            assert path is not None, f"route {name} first"
            frames.append(pd.read_csv(path)[["draw_no", "set_name", "transit", "walk"]].assign(is_training=False))
    return frames


def rounded_min(seconds):
    """Seconds to the nearest whole minute, half up (SCR-10); NaN (over max_time) -> inf (from transit_buffer_sweep)."""
    return np.floor(np.nan_to_num(np.asarray(seconds, dtype=float), nan=np.inf, posinf=np.inf) / SECONDS_PER_MIN + 0.5)


def mode_group(walk_only, vehicles):
    if walk_only:
        return "walk"
    kinds = set(vehicles.split("|"))
    if TRAIN_TYPE in kinds:
        return "train-involved"
    if kinds == {TRAM_TYPE}:
        return "tram"
    if TRAM_TYPE in kinds:
        return "tram+bus"
    return "bus"


def load(set_names):
    frames = []
    for set_name in set_names:
        pairs_df = pairs_of_set(set_name).assign(set_name=set_name, release=SET_RELEASE[set_name])
        frames.append(pairs_df.merge(google_table(set_name, pairs_df.draw_no), on="draw_no", how="left", validate="one_to_one"))
    df = pd.concat(frames, ignore_index=True)
    assert df.default_min.notna().all(), "pairs without a Google default"
    routed = routes_of(set_names)
    training_df = df[df.set_name.isin(TRAINING_SETS)].merge(
        next((f for f in routed if f.is_training.all()), pd.DataFrame(columns=["draw_no", "transit", "walk"])).drop(
            columns="is_training", errors="ignore"), on="draw_no", how="left", validate="one_to_one")
    other = [f.drop(columns="is_training") for f in routed if not f.is_training.all()]
    other_df = df[~df.set_name.isin(TRAINING_SETS)]
    if other:
        other_df = other_df.merge(pd.concat(other, ignore_index=True), on=["set_name", "draw_no"], how="left", validate="one_to_one")
    df = pd.concat([training_df, other_df], ignore_index=True)
    assert df.transit.notna().sum() + df.walk.notna().sum() > 0 and len(df) == sum(len(f) for f in frames)
    transit_s, walk_s = df.transit.fillna(np.inf).to_numpy(), df.walk.fillna(np.inf).to_numpy()
    df["model_s"] = np.fmin(transit_s, walk_s)
    df["model_min"] = rounded_min(df.model_s)
    df["is_r5_walk"] = walk_s <= transit_s
    df["is_scored"] = df.is_scored.astype(bool)
    df["mode_group"] = [mode_group(bool(w), v) for w, v in zip(df.default_walk_only, df.default_vehicles)]
    df["boardings"] = [BOARDING_GROUPS[min(int(x), 2)] if np.isfinite(x) else "?" for x in df.default_steps.astype(float)]
    return df


# --- service density (copied from transit_test_score.py) ---------------------------------------------
def active_service_ids(gtfs_zip, date):
    date_int = int(f"{date:%Y%m%d}")
    calendar_df = pd.read_csv(gtfs_zip.open("calendar.txt"), dtype={"service_id": str}, encoding=GTFS_ENCODING)
    is_active = ((calendar_df[WEEKDAY_COLUMNS[date.weekday()]] == 1) & (calendar_df.start_date <= date_int)
                 & (calendar_df.end_date >= date_int))
    service_ids = set(calendar_df.service_id[is_active])
    if "calendar_dates.txt" in gtfs_zip.namelist():
        dates_df = pd.read_csv(gtfs_zip.open("calendar_dates.txt"), dtype={"service_id": str}, encoding=GTFS_ENCODING)
        dates_df = dates_df[dates_df.date == date_int]
        service_ids |= set(dates_df.service_id[dates_df.exception_type == EXCEPTION_ADDED])
        service_ids -= set(dates_df.service_id[dates_df.exception_type == EXCEPTION_REMOVED])
    return service_ids


def near_stop_lists(stops_df, points_lat, points_lon):
    from sklearn.neighbors import BallTree
    tree = BallTree(np.radians(stops_df[["stop_lat", "stop_lon"]].to_numpy()), metric="haversine")
    return tree.query_radius(np.radians(np.column_stack([points_lat, points_lon])), r=SERVICE_RADIUS_M / EARTH_RADIUS_M)


def minutes_of(time_text):
    parts = time_text.str.split(":", expand=True).astype(int)
    return parts[0] * MIN_PER_HOUR + parts[1] + parts[2] / SECONDS_PER_MIN


def release_departures(release, stop_keys, dates):
    frames = []
    for feed_name in FEED_NAMES:
        with zipfile.ZipFile(CLEANED_DIRS[release] / f"{feed_name}.zip") as gtfs_zip:
            services_by_date = {date: active_service_ids(gtfs_zip, date) for date in dates}
            service_ids = set().union(*services_by_date.values())
            trips_df = pd.read_csv(gtfs_zip.open("trips.txt"), dtype=str, usecols=["trip_id", "service_id"], encoding=GTFS_ENCODING)
            active_trips = set(trips_df.trip_id[trips_df.service_id.isin(service_ids)])
            feed_stops = {key.split("|", 1)[1] for key in stop_keys if key.startswith(feed_name + "|")}
            kept = []
            for chunk in pd.read_csv(gtfs_zip.open("stop_times.txt"), dtype=str, encoding=GTFS_ENCODING,
                                     usecols=["trip_id", "departure_time", "stop_id"], chunksize=STOP_TIMES_CHUNK_ROWS):
                kept.append(chunk[chunk.stop_id.isin(feed_stops) & chunk.trip_id.isin(active_trips)])
            feed_df = pd.concat(kept, ignore_index=True).merge(trips_df, on="trip_id", how="left")
            print(f"  {release} {feed_name}: {len(dates)} dates, {len(feed_df)} departures kept", flush=True)
        for date, date_service_ids in services_by_date.items():
            date_df = feed_df[feed_df.service_id.isin(date_service_ids)]
            frames.append(pd.DataFrame({"date": date, "stop_key": feed_name + "|" + date_df.stop_id,
                                        "trip_key": feed_name + "|" + date_df.trip_id, "dep_min": minutes_of(date_df.departure_time)}))
    return pd.concat(frames, ignore_index=True)


def holdout_service_counts():
    """Origin trips per holdout pair on its own date (saved data: reused when present). Reads no Google answer."""
    saved = newest(f"{NAME}_2*_service_holdout.csv")
    if saved is not None:
        print(f"reusing {saved.name} ({datetime.date.fromtimestamp(saved.stat().st_mtime)})")
        return pd.read_csv(saved)
    release = SET_RELEASE["holdout"]
    pairs_df = pairs_of_set("holdout").merge(own_dates("holdout"), on="draw_no", validate="one_to_one")
    stop_frames = []
    for feed_name in FEED_NAMES:
        with zipfile.ZipFile(CLEANED_DIRS[release] / f"{feed_name}.zip") as gtfs_zip:
            stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype={"stop_id": str}, encoding=GTFS_ENCODING,
                                   usecols=["stop_id", "stop_lat", "stop_lon"])
        stop_frames.append(stops_df.assign(stop_key=feed_name + "|" + stops_df.stop_id))
    stops_df = pd.concat(stop_frames, ignore_index=True)
    origin_lists = near_stop_lists(stops_df, pairs_df.origin_lat.to_numpy(), pairs_df.origin_lon.to_numpy())
    count_dates = pairs_df.own_date.to_numpy()
    near_keys = set(stops_df.stop_key.to_numpy()[np.concatenate(list(origin_lists))])
    departures_df = release_departures(release, near_keys, sorted(set(count_dates)))
    by_stop = {key: group for key, group in departures_df.groupby(["date", "stop_key"])}
    stop_keys = stops_df.stop_key.to_numpy()
    rows = []
    for i, pair in enumerate(pairs_df.itertuples()):
        groups = [by_stop[(count_dates[i], key)] for key in stop_keys[origin_lists[i]] if (count_dates[i], key) in by_stop]
        trips = 0
        if groups:
            near_df = pd.concat(groups)
            is_window = ((near_df.dep_min >= pair.dep_min_of_day - SERVICE_HALF_WINDOW_MIN)
                         & (near_df.dep_min <= pair.dep_min_of_day + SERVICE_HALF_WINDOW_MIN))
            trips = int(near_df.trip_key[is_window].nunique())
        rows.append({"set_name": "holdout", "draw_no": pair.draw_no, "origin_trips": trips})
    service_df = pd.DataFrame(rows)
    service_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_service_holdout.csv", index=False)
    return service_df


def with_strata(df):
    frames = []
    if df.set_name.isin(TRAINING_SETS).any():
        frames.append(pd.read_csv(newest(f"{RANGE_NAME}_2*_service_owndate.csv"), usecols=["set_name", "draw_no", "origin_trips"]))
    if df.set_name.isin(OLD_TEST_SETS).any():
        frames.append(pd.read_csv(newest(f"{TEST_SCORE_NAME}_2*_service_test.csv"), usecols=["set_name", "draw_no", "origin_trips"]))
    if (df.set_name == "holdout").any():
        frames.append(holdout_service_counts())
    service_df = pd.concat(frames, ignore_index=True)
    df = df.merge(service_df, on=["set_name", "draw_no"], how="left", validate="one_to_one")
    assert df.origin_trips.notna().all(), "pairs without a service count"
    df["stratum"] = np.select([df.origin_trips <= STRATUM_LOW_MAX_TRIPS, df.origin_trips >= STRATUM_HIGH_MIN_TRIPS],
                              ["low", "high"], "mid")
    return df


# --- statistics (copied from transit_test_score.py) --------------------------------------------------
def wilson(successes, n):
    if n == 0:
        return np.nan, np.nan
    share = successes / n
    centre = (share + WILSON_Z ** 2 / (2 * n)) / (1 + WILSON_Z ** 2 / n)
    half_width = WILSON_Z * np.sqrt(share * (1 - share) / n + WILSON_Z ** 2 / (4 * n ** 2)) / (1 + WILSON_Z ** 2 / n)
    return centre - half_width, centre + half_width


def is_away(google_min):
    return np.logical_or.reduce([(google_min >= low) & (google_min <= high) for low, high in AWAY_RANGES_MIN])


def google_side(low, high, is_r5_below, cut_min):
    is_low_below, is_high_below = low <= cut_min, high <= cut_min
    return np.where(is_low_below != is_high_below, is_r5_below, is_high_below)


def distance_to_range(r5_min, low, high):
    return np.where(r5_min < low, r5_min - low, np.where(r5_min > high, r5_min - high, 0.0))


def zone_checks(zone_df, cut_min, centred_errors, rng):
    from scipy.stats import binomtest
    low, high, r5 = zone_df[f"low_{GATING_K}"].to_numpy(), zone_df.default_min.to_numpy(), zone_df.model_min.to_numpy()
    is_r5_below = r5 <= cut_min
    is_google_below = google_side(low, high, is_r5_below, cut_min)
    both = int((is_google_below & is_r5_below).sum())
    rec_n, prec_n = int(is_google_below.sum()), int(is_r5_below.sum())
    rec, prec = both / rec_n, both / prec_n if prec_n else np.nan
    rec_low, rec_high = wilson(both, rec_n)
    prec_low, prec_high = wilson(both, prec_n)
    sim_recall, sim_precision = [], []
    for _ in range(N_SIMULATIONS):
        sim_r5 = high + rng.choice(centred_errors, size=len(high), replace=True)
        is_sim_below = sim_r5 <= cut_min
        is_sim_google = google_side(low, high, is_sim_below, cut_min)
        sim_both = (is_sim_google & is_sim_below).sum()
        sim_recall.append(sim_both / is_sim_google.sum() if is_sim_google.sum() else np.nan)
        sim_precision.append(sim_both / is_sim_below.sum() if is_sim_below.sum() else np.nan)
    bar_recall, bar_precision = np.nanmedian(sim_recall), np.nanmedian(sim_precision)
    n_early = int((is_r5_below & ~is_google_below).sum())
    n_late = int((~is_r5_below & is_google_below).sum())
    sign_p = binomtest(n_early, n_early + n_late, 0.5).pvalue if n_early + n_late else 1.0
    gap = abs(rec - prec)
    return {"recall": (f"{rec:.3f} ({both}/{rec_n}, {rec_low:.2f}-{rec_high:.2f})", None),
            "precision": (f"{prec:.3f} ({both}/{prec_n}, {prec_low:.2f}-{prec_high:.2f})", None),
            "floor": (f"{min(rec_low, prec_low):.3f}", rec_low > FLOOR and prec_low > FLOOR),
            "noise bar": (f"{rec_high:.2f}/{bar_recall:.2f}, {prec_high:.2f}/{bar_precision:.2f}",
                          rec_high >= bar_recall and prec_high >= bar_precision),
            "balance": (f"{n_early}e/{n_late}l p {sign_p:.3f}, gap {gap:.3f}", sign_p >= SIGN_TEST_ALPHA and gap <= CLOSE_TOLERANCE)}


def hard_windows(df):
    """{test: boolean window mask over df, miss mask}."""
    out = {}
    default = df.default_min.to_numpy()
    for cut_min in CUTS_MIN.values():
        is_r5_below = df.model_min.to_numpy() <= cut_min
        is_google_below = google_side(df[f"low_{GATING_K}"].to_numpy(), default, is_r5_below, cut_min)
        for kind, low_min, high_min in [("lost", cut_min - HARD_WINDOW_FAR_MIN, cut_min - HARD_WINDOW_NEAR_MIN),
                                        ("false", cut_min + HARD_WINDOW_NEAR_MIN, cut_min + HARD_WINDOW_FAR_MIN)]:
            is_window = (default >= low_min) & (default <= high_min)
            out[f"{kind} {cut_min}"] = (is_window, is_window & (is_r5_below != is_google_below))
    return out


def group_of(miss, is_r5_below_cut):
    if not is_r5_below_cut:
        return "4 R5 misses Google's ride (late)"
    if miss.is_r5_walk and not miss.default_walk_only:
        return "2 R5 walks, Google rides"
    if miss.default_wait_s >= HOME_WAIT_GROUP_S:
        return "1 Google waits at home"
    if TRAM_TYPE in miss.default_vehicles:
        return "3 Google rides a tram, R5 faster"
    return "other early"


def score_set(df, zone_df, error_df, label):
    """TRN-13 / TRN-15 checks on one set: zones on zone_df, noise errors on error_df, hard misses and ratios on df."""
    checks, notes, verdicts, miss_frames = {}, [], [], []
    is_away_pair = is_away(error_df.default_min.to_numpy()) & np.isfinite(error_df.model_min.to_numpy())
    errors = distance_to_range(error_df.model_min.to_numpy(), error_df[f"low_{GATING_K}"].to_numpy(),
                               error_df.default_min.to_numpy())[is_away_pair]
    rng = np.random.default_rng(SIMULATION_SEED)
    for zone_no, cut_min in CUTS_MIN.items():
        is_zone = (zone_df.default_min >= ZONES_MIN[zone_no][0]) & (zone_df.default_min <= ZONES_MIN[zone_no][1])
        checks.update({f"z{zone_no} {name}": value
                       for name, value in zone_checks(zone_df[is_zone], cut_min, errors - np.median(errors), rng).items()})
    for test, (is_window, is_miss) in hard_windows(df).items():
        k_miss, n = int(is_miss.sum()), int(is_window.sum())
        low, high = wilson(k_miss, n)
        is_report_only = test in REPORT_ONLY_TESTS
        checks[f"hard {test}"] = (f"{k_miss}/{n}, upper {high:.3f}{' (report-only)' if is_report_only else ''}",
                                  None if is_report_only else high <= HARD_MISS_MAX)
        miss_df = df[is_miss].assign(test=test)
        miss_df["group"] = [group_of(miss, test.startswith("false")) for miss in miss_df.itertuples()]
        miss_frames.append(miss_df)
        by_stratum = miss_df.stratum.value_counts().reindex(STRATUM_LABELS, fill_value=0).to_dict()
        tested_by = df[is_window].stratum.value_counts().reindex(STRATUM_LABELS, fill_value=0).to_dict()
        notes.append(f"  {test}: {k_miss}/{n} = {k_miss / n if n else np.nan:.3f} (95% {low:.3f}-{high:.3f}); misses by third "
                     f"{by_stratum} of tested {tested_by}; groups {miss_df.group.value_counts().to_dict()}; "
                     f"modes {miss_df.mode_group.value_counts().to_dict()}")
        if is_report_only:
            continue
        if n >= SEVERE_MIN_N and high > SEVERE_MAX:
            verdicts.append(f"severe ({test} upper {high:.3f} > {SEVERE_MAX})")
        if high > HARD_MISS_MAX and k_miss >= CONCENTRATION_MIN_MISSES:
            top = max(STRATUM_LABELS, key=lambda name: by_stratum[name])
            tested_share = tested_by[top] / n
            if by_stratum[top] / k_miss >= CONCENTRATED_SHARE and tested_share < CONCENTRATION_TESTED_MAX:
                verdicts.append(f"concentrated ({test}: {by_stratum[top]}/{k_miss} in {top}, {tested_share:.2f} of tested)")
            elif by_stratum[top] / k_miss >= CONCENTRATED_SHARE:
                notes.append(f"  {test}: {by_stratum[top]}/{k_miss} misses in {top}, which holds {tested_share:.2f} of tested: not concentrated")
    for cut_min in CUTS_MIN.values():
        n_google = int((df.default_min <= cut_min).sum())
        n_r5 = int((df.model_min.to_numpy() <= cut_min).sum())
        checks[f"ratio <= {cut_min}"] = (f"{n_r5 / n_google:.3f} ({n_r5}/{n_google})",
                                         COUNT_RATIO_RANGE[0] <= n_r5 / n_google <= COUNT_RATIO_RANGE[1])
    finite = np.isfinite(df.model_min.to_numpy())
    signed = (df.model_min - df.default_min).to_numpy()[finite]
    notes.insert(0, f"  error to the range away from the cuts: n {len(errors)}, median {np.median(errors):+.1f}, mean {errors.mean():+.2f}, "
                    f"inside {np.mean(errors == 0):.2f}; model - default, all scored: median {np.median(signed):+.1f}, mean {signed.mean():+.2f}, "
                    f"MAE {np.abs(signed).mean():.2f} (n {len(signed)}; tail > {TAIL_MIN} min off {int((np.abs(signed) > TAIL_MIN).sum())})")
    failures = [name for name, (_, is_pass) in checks.items() if is_pass is not None and not is_pass]
    is_hard_fail = any(name.startswith("hard") for name in failures)
    checks["verdict"] = ("PASS" if not failures else "FAIL: " + ", ".join(failures), None)
    checks["stop condition"] = (("BARRED: " + "; ".join(verdicts)) if verdicts else
                                ("hard-miss fail is a recorded cost" if is_hard_fail else "no hard-miss fail"), None)
    return checks, [f"{label}:"] + notes, pd.concat(miss_frames, ignore_index=True).assign(subset=label)


def breakdown(df, column, groups):
    """Report-only: per group, n, error to the range (median / mean), seconds error vs Google's default, hard misses."""
    rows = []
    windows = hard_windows(df)
    for group in groups:
        mask = (df[column] == group).to_numpy()
        finite = mask & np.isfinite(df.model_min.to_numpy())
        if not finite.any():
            continue
        distance = distance_to_range(df.model_min.to_numpy(), df[f"low_{GATING_K}"].to_numpy(), df.default_min.to_numpy())[finite]
        seconds = (df.model_s - df.default_s).to_numpy()[finite]
        row = {column: group, "n": int(mask.sum()), "range_err_median": np.median(distance), "range_err_mean": distance.mean(),
               "agree": np.mean(distance == 0), "sec_err_median": np.median(seconds), "sec_err_mean": seconds.mean(),
               f"tail>{TAIL_MIN}": int((np.abs(distance) > TAIL_MIN).sum())}
        for test, (is_window, is_miss) in windows.items():
            row[test] = f"{int((is_miss & mask).sum())}/{int((is_window & mask).sum())}"
        rows.append(row)
    return pd.DataFrame(rows).round(3).to_string(index=False)


def table_text(table):
    table_df = pd.DataFrame({label: {name: f"{text}{'' if is_pass is None else (' ok' if is_pass else ' FAIL')}"
                                     for name, (text, is_pass) in checks.items()} for label, checks in table.items()})
    with pd.option_context("display.width", 320, "display.max_columns", 10, "display.max_colwidth", 60):
        return table_df, table_df.to_string()


def write(mode, lines, table_df=None, frames=None):
    text = "\n".join(lines)
    print(text)
    prefix = f"{NAME}_{run_date()}_{mode}"
    (DIAGNOSTIC_DATA_DIR / f"{prefix}_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    if table_df is not None:
        table_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{prefix}_table.csv")
    for tag, frame in (frames or {}).items():
        frame.to_csv(DIAGNOSTIC_DATA_DIR / f"{prefix}_{tag}.csv", index=False)


def random_scored(df):
    return df[df.is_scored & (df.set_name != TOPUP_SET)]


def score_subsets(subsets, lines):
    table, detail, misses = {}, [], []
    for label, (hard_df, zone_df, error_df) in subsets.items():
        checks, notes, miss_df = score_set(hard_df, zone_df, error_df, label)
        table[label] = checks
        detail += notes
        misses.append(miss_df)
    table_df, text = table_text(table)
    lines += ["", text, ""] + detail
    return table, table_df, pd.concat(misses, ignore_index=True)


# --- modes -----------------------------------------------------------------------------------------
def check():
    """(C1) the scorer, on the frozen model's saved training routes, reproduces the model of record's training tables."""
    check_jar()
    df = with_strata(load(TRAINING_SETS))
    scored_df = df[df.is_scored]
    lines = [f"{NAME} {run_date()} check: frozen model on the training sets ({df.set_name.value_counts().to_dict()}); "
             f"scored {len(scored_df)}"]
    saved = pd.read_csv(newest(f"{RECORD_NAME}_2*_train_scored.csv")).set_index("draw_no")
    both = scored_df.set_index("draw_no").join(saved[["p2orig_min"]], how="inner")
    off_min = int((both.model_min.to_numpy() != both.p2orig_min.to_numpy(dtype=float)).sum())
    lines.append(f"pairs matched to the saved scored table {len(both)} of {len(saved)}; minutes off {off_min}")
    table, table_df, _ = score_subsets({"training (fitted)": (random_scored(df), scored_df, scored_df)}, lines)
    checks = table["training (fitted)"]
    mismatches = [f"{test}: {checks[f'hard {test}'][0]} vs {k}/{n}" for test, (k, n) in EXPECTED_HARD.items()
                  if not checks[f"hard {test}"][0].startswith(f"{k}/{n},")]
    mismatches += [f"ratio <= {cut}: {checks[f'ratio <= {cut}'][0]} vs {value}" for cut, value in EXPECTED_RATIOS.items()
                   if not checks[f"ratio <= {cut}"][0].startswith(value)]
    is_pass = not mismatches and off_min == 0 and len(both) == len(saved)
    lines += ["", f"table differences: {mismatches or 'none'}", f"acceptance: {'PASS' if is_pass else 'FAIL'}"]
    write("check", lines, table_df)


def require_check():
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_check_summary.txt"
    assert path.exists() and "acceptance: PASS" in path.read_text(encoding="utf-8"), "run check first today (must PASS)"


def seen():
    """Report-only: training, old test (before / after), all seen pooled. Never a validation."""
    check_jar()
    require_check()
    df = with_strata(load(TRAINING_SETS + OLD_TEST_SETS))
    scored_df = df[df.is_scored]
    training_df = scored_df[scored_df.set_name.isin(TRAINING_SETS)]
    old_df = scored_df[scored_df.set_name.isin(OLD_TEST_SETS)]
    lines = [f"{NAME} {run_date()} seen (REPORT-ONLY, not a validation): frozen model; pairs {len(df)} by set "
             f"{df.set_name.value_counts().to_dict()}; scored {len(scored_df)}"]
    subsets = {"training (fitted)": (random_scored(training_df), training_df, training_df),
               "old test (seen)": (old_df, old_df, old_df)}
    for set_name in OLD_TEST_SETS:
        part_df = old_df[old_df.set_name == set_name]
        subsets[f"old {set_name} ({SET_RELEASE[set_name]})"] = (part_df, part_df, part_df)
    subsets["all seen pooled"] = (random_scored(scored_df), scored_df, scored_df)
    _, table_df, misses = score_subsets(subsets, lines)

    before_df = pd.read_csv(newest(f"{TEST_SCORE_NAME}_2*_test_results.csv"), usecols=["set_name", "draw_no", "model_min"])
    pair_df = old_df.merge(before_df, on=["set_name", "draw_no"], suffixes=("", "_before"), validate="one_to_one")
    after_hard = {t: int(m.sum()) for t, (_, m) in hard_windows(pair_df).items()}
    before_hard = {t: int(m.sum()) for t, (_, m) in hard_windows(pair_df.assign(model_min=pair_df.model_min_before)).items()}
    band = lambda m: np.where(m <= CUTS_MIN[1], 1, np.where(m <= CUTS_MIN[2], 2, 3))   # noqa: E731
    is_finite = np.isfinite(pair_df.model_min.to_numpy()) & np.isfinite(pair_df.model_min_before.to_numpy())
    low, high = pair_df[f"low_{GATING_K}"].to_numpy()[is_finite], pair_df.default_min.to_numpy()[is_finite]
    lines += ["", f"old test before (no-wait, 2026-10-20) vs after (frozen), same {len(pair_df)} scored pairs:",
              f"  hard misses before {before_hard} (total {sum(before_hard.values())}); after {after_hard} "
              f"(total {sum(after_hard.values())})",
              f"  minutes changed {int((pair_df.model_min != pair_df.model_min_before).sum())}; band calls changed "
              f"{int((band(pair_df.model_min.to_numpy()) != band(pair_df.model_min_before.to_numpy())).sum())}",
              "  error to range (median / mean): before "
              + "{:+.1f} / {:+.2f}".format(*(lambda d: (np.median(d), d.mean()))(distance_to_range(pair_df.model_min_before.to_numpy()[is_finite], low, high)))
              + ", after "
              + "{:+.1f} / {:+.2f}".format(*(lambda d: (np.median(d), d.mean()))(distance_to_range(pair_df.model_min.to_numpy()[is_finite], low, high)))
              + f" (n {int(is_finite.sum())}, both finite)"]
    for label, part_df in [("training", random_scored(training_df)), ("old test", old_df), ("all seen", random_scored(scored_df))]:
        lines += ["", f"by Google default's mode, {label} (report-only):", breakdown(part_df, "mode_group", MODE_GROUPS),
                  f"by boardings, {label}:", breakdown(part_df, "boardings", BOARDING_GROUPS)]
    write("seen", lines, table_df, {"misses": misses, "results": df})


def predict():
    """Claude's predicted holdout ranges from the all-seen random counts (Beta posterior, binomial at the expected n)."""
    path = newest(f"{NAME}_2*_seen_results.csv")
    assert path is not None, "run seen first"
    df = pd.read_csv(path)
    df = df[df.is_scored.astype(bool) & (df.set_name != TOPUP_SET)]
    n_holdout = len(pairs_of_set("holdout"))
    scale = n_holdout / len(df[df.set_name.isin(["train", "second", "test", "test_ext"])].drop_duplicates(["set_name", "draw_no"]))
    rng = np.random.default_rng(PREDICTION_SEED)
    tail = (1 - PREDICTION_LEVEL) / 2
    lines = [f"{NAME} {run_date()} predict: holdout ({n_holdout} pairs) from {len(df)} all-seen random scored pairs; "
             f"{PREDICTION_LEVEL:.0%} predictive ranges (Beta(k + {PRIOR}, n - k + {PRIOR}), binomial at the expected n)"]
    for test, (is_window, is_miss) in hard_windows(df).items():
        k, n = int(is_miss.sum()), int(is_window.sum())
        n_expected = int(round(n * scale * (1 - (df.is_scored == False).mean())))   # noqa: E712
        rates = rng.beta(k + PRIOR, n - k + PRIOR, N_DRAWS)
        misses = rng.binomial(n_expected, rates)
        uppers = np.array([wilson(m, n_expected)[1] for m in misses])
        lines.append(f"  {test}: seen {k}/{n}; holdout n ~{n_expected}: misses {np.quantile(misses, tail):.0f}-"
                     f"{np.quantile(misses, 1 - tail):.0f} (median {np.median(misses):.0f}), upper {np.quantile(uppers, tail):.3f}-"
                     f"{np.quantile(uppers, 1 - tail):.3f}; passes 5% with P {np.mean(uppers <= HARD_MISS_MAX):.2f}; "
                     f"severe P {np.mean(uppers > SEVERE_MAX):.2f}")
    write("predict", lines)


def holdout():
    """The holdout, opened once, by the freeze record's reading rule."""
    check_jar()
    require_check()
    assert newest(f"{NAME}_2*_predict_summary.txt") is not None, "predictions first"
    assert newest(f"{NAME}_2*_holdout_summary.txt") is None, "the holdout has been opened: never re-opened"
    df = with_strata(load(["holdout"]))
    scored_df = df[df.is_scored]
    lines = [f"{NAME} {run_date()} holdout (opened once): frozen model; pairs {len(df)}, scored {len(scored_df)} "
             f"(out of scope {int((~df.is_scored).sum())})",
             f"service thirds (fixed at training): {scored_df.stratum.value_counts().reindex(STRATUM_LABELS).to_dict()}"]
    training_hexes = set(pd.concat([pairs_of_set(name).dest_hex for name in TRAINING_SETS]))
    seen_hexes = training_hexes | set(pd.concat([pairs_of_set(name).dest_hex for name in OLD_TEST_SETS]))
    unseen_df = scored_df[~scored_df.dest_hex.isin(training_hexes)]
    unseen_all_df = scored_df[~scored_df.dest_hex.isin(seen_hexes)]
    lines.append(f"unseen by training: {len(unseen_df)} scored; unseen by any seen set: {len(unseen_all_df)} scored")
    subsets = {"holdout (verdict)": (scored_df, scored_df, scored_df),
               "unseen by training (report-only)": (unseen_df, unseen_df, unseen_df),
               "unseen by any seen set (report-only)": (unseen_all_df, unseen_all_df, unseen_all_df)}
    _, table_df, misses = score_subsets(subsets, lines)
    lines += ["", "by Google default's mode (report-only):", breakdown(scored_df, "mode_group", MODE_GROUPS),
              "by boardings (report-only):", breakdown(scored_df, "boardings", BOARDING_GROUPS)]
    write("holdout", lines, table_df, {"misses": misses, "results": df})


if __name__ == "__main__":
    {"route": route, "route_all": route_all, "check": check, "seen": seen, "predict": predict,
     "holdout": holdout}[sys.argv[1]](*sys.argv[2:])
