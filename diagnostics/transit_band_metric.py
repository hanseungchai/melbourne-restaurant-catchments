"""Does stock R5 call transit bands 1-2 right at the 10 and 20 min cutoffs (TRN-13)?

Claim under test (concepts/transit.md TRN-13; DESIGN.md Q23): stock R5 at WALK_SPEED_KMH (4.16 km/h) with
the no-first-wait correction (TTM from t - 1 min, minus 1; T7 e) predicts transit bands 1 (<= 10 min) and
2 (<= 20 min) well enough for reachability. Where the pipeline relies on it: the transit bands (SCR-1,
RCH-1) before they go into reachability.

Test details (proposed by Claude, OK'd by the user 2026-10-18 before any R5 result on these pairs was seen):
  Data: training half (2026-10-09 release), second batch and boundary top-up (2026-10-16 release; TRN-10,
  TRN-14). Each set is routed on the network built from the release its Google answers came from (user,
  2026-10-18): the 2026-10-09 cleaned feeds in outputs/pt_graph/gtfs_cleaned/, and copies of the
  2026-10-16 feeds cleaned the same way (empty tables and route type 701 dropped, TRN-11), made here.
  R5 departs at the pair's drawn minute on WINDOW_DATE (a Wednesday inside both releases), 1-min window.
  Google time: the default route's arrival from the requested departure, rounded to whole minutes, scored
  only if that route is in scope (as transit_zone_ranges). Zones: Google 7-13 (cut 10), 17-23 (cut 20).
  R5 time: whole minutes with no first-board wait (N, transit_board_slack's rule); ties (walk-only equal)
  read as N_hi, N_lo reported. R5 counts below a cut when N <= cut (what reachability does with R5's
  minutes); N <= cut - 1 reported, not gating (R5 truncates, Google rounds: SCR-10, TRN-6).
  (1) Per zone, recall (of Google-below pairs, share R5 puts below) and precision (of R5-below pairs,
      share Google puts below), each with a Wilson 95% interval.
  (2a) Floor: each interval's lower end > FLOOR.
  (2b) Unbiased-noise bar: R5's error N - Google on pairs away from the cuts (Google 0-6, 14-16, 24-30),
      shifted to median 0; each zone pair simulated N_sim = Google + error drawn with replacement,
      N_SIMULATIONS times; bar = the median simulated score. Pass if the interval's upper end reaches it.
  (2c) Balance: in-zone misses split into R5 early (R5 below, Google above) and R5 late; two-sided exact
      sign test p >= SIGN_TEST_ALPHA; and |recall - precision| <= CLOSE_TOLERANCE.
  (3) Hard misses, on the random samples only (training half and second batch; the top-up was picked near
      the cuts): Google in band 1-2 outside the zones with R5 in another band, plus Google > 23 min with
      R5 <= 20; share of Google's band 1-2 pairs outside the zones; pass if the Wilson upper end
      <= HARD_MISS_MAX. Each listed. Top-up hard misses reported per draw range only.
      Count ratio (R5's pairs <= cut / Google's), random samples only: pass if within COUNT_RATIO_RANGE.
  (4) Reported only: full-band recall and precision; strata by distance and time of day. Inner / middle /
      outer is not reported: no definition is recorded.
  Google against itself: skipped (user).

Conclusion (run 2026-10-18): FAILS. 3,462 pairs (3,448 scored); zone counts 206 / 365 as expected.
  Zone 1 (n 206): recall 0.851 (0.761-0.911), precision 0.747 (0.654-0.823); floor and noise bar pass;
  balance fails narrowly (misses 25 early / 13 late, p 0.073; |recall - precision| 0.103 > 0.10).
  Zone 2 (n 365): recall 0.899 (0.850-0.934), precision 0.762 (0.703-0.812); floor passes; noise bar fails
  (precision bar 0.840 above the upper end); balance fails (56 early / 20 late, p < 0.001; gap 0.138).
  R5 is early: error away from the cuts median -1.0 min (n 654). Hard misses 33 of 141 (0.234, upper 0.310):
  7 band swaps, 26 Google > 23 min that R5 calls band 1-2 (7 of them R5 walking where Google's default is
  transit). Count ratios 1.097 (<= 10) and 1.099 (<= 20): pass, at the bar's edge. Reported: strict
  N <= cut - 1 gives zone 2 recall 0.784 / precision 0.817, zone 1 0.690 / 0.857.

Inputs (read only): the transit pair files, split and Google route tables in outputs/transit_validation/;
the cleaned 2026-10-09 feeds in outputs/pt_graph/gtfs_cleaned/; the 2026-10-16 feeds in
inputs/gtfs_ptv_20261018/; the OSM extract in frozen_inputs/osm_extract/. The test half is not read.
Self-contained (CLAUDE.md D1). No paid API calls; r5py only.
Usage: `python transit_band_metric.py route 20261009`, `... route 20261016` (one network per process),
then `... score`. Routing tables are saved data (one per release), written row by row: a rerun resumes the
newest one or reuses it when complete. Results carry the run date; a same-day rerun replaces them.
"""
import csv
import datetime
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
OLD_CLEANED_DIR = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned"      # 2026-10-09 release
NEW_SOURCE_DIR = PROJECT_ROOT / "inputs" / "gtfs_ptv_20261018"                # 2026-10-16 release
NEW_SOURCE_PATHS = {"ptv_metro_train": NEW_SOURCE_DIR / "metro_train" / "google_transit.zip",
                    "ptv_tram": NEW_SOURCE_DIR / "tram" / "google_transit.zip",
                    "ptv_metro_bus": NEW_SOURCE_DIR / "metro_bus" / "google_transit.zip"}
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_band_metric"
NEW_CLEANED_DIR = DIAGNOSTIC_DATA_DIR / f"{NAME}_gtfs_cleaned_20261016"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
RESERVE_PATH = SUBJECT_DIR / f"transit_pairs_reserve_{FILE_TAG}.csv"
TOPUP_PATH = SUBJECT_DIR / f"transit_pairs_topup_{FILE_TAG}.csv"
TOPUP_SELECTION_PATH = SUBJECT_DIR / f"transit_topup_selection_{FILE_TAG}.csv"
FIRST_ROUTES_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv"
SECOND_ROUTES_PATH = SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv"
TOPUP_ROUTES_PATH = SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_board_slack.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as transit_board_slack.py
SINGLE_PERCENTILE = 49                         # as transit_board_slack.py (r5py renames a lone p50)
WALK_SPEED_KMH = 4.16                          # config.WALK_SPEED_KMH (TRN-13's scored model)
BOARD_SLACK_MIN = 1                            # R5's 60 s first-board slack; also the departure shift (T7 e)
EXCLUDED_ROUTE_TYPES = [701]                   # config.PT_EXCLUDED_ROUTE_TYPES (TRN-11)
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]  # TRN-11, as transit_zone_ranges
TRAIN_HALF = "train"
SECONDS_PER_MIN = 60
SET_RELEASE = {"train": "20261009", "second": "20261016", "topup": "20261016"}
RANDOM_SETS = ["train", "second"]              # random samples; the top-up was picked near the cuts
ZONES_MIN = {1: (7, 13), 2: (17, 23)}          # Google minutes, +-3 around the cuts (TRN-13 (1))
CUTS_MIN = {1: 10, 2: 20}
AWAY_RANGES_MIN = [(0, 6), (14, 16), (24, 30)]  # Google minutes away from the cuts (TRN-13 (2b))
EXPECTED_ZONE_COUNTS = {1: {"train": 67, "second": 90, "topup": 49},
                        2: {"train": 119, "second": 179, "topup": 67}}  # transit_zone_ranges + top-up report
CHECK_COVERS_DATE = WINDOW_DATE

# --- test (user OK 2026-10-18) ---------------------------------------------------------------------
WILSON_Z = 1.959964                            # 95% interval
FLOOR = 0.6                                    # interval lower end above this (chance ~0.5)
N_SIMULATIONS = 2000
SIMULATION_SEED = 20261018
SIGN_TEST_ALPHA = 0.05
CLOSE_TOLERANCE = 0.10                         # |recall - precision|
HARD_MISS_MAX = 0.05                           # Wilson upper end
COUNT_RATIO_RANGE = (0.90, 1.10)
DISTANCE_BINS_M = [0, 1000, 2000, 4000, np.inf]
HOUR_BINS = [0, 7, 10, 16, 19, 24]

GTFS_TABLE_SUFFIX = ".txt"
GTFS_TEXT_ENCODING = "utf-8-sig"
GTFS_FILE_ENCODING = "utf-8"
BYTE_ORDER_MARK = "﻿"
MAX_LINES_EMPTY_TABLE = 1


# --- feed cleaning (copied from functions/pt_network.py, D1) ----------------------------------------
def excluded_route_type_rows(gtfs_path, excluded_route_types):
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
    return {"routes.txt": ("route_id", excluded_route_ids), "trips.txt": ("trip_id", excluded_trip_ids),
            "stop_times.txt": ("trip_id", excluded_trip_ids), "stops.txt": ("stop_id", excluded_stop_ids)}


def drop_table_rows(table_text, key_column, drop_keys):
    lines = table_text.splitlines(keepends=True)
    header_fields = next(csv.reader([lines[0].lstrip(BYTE_ORDER_MARK)]))
    key_index = header_fields.index(key_column)
    data_lines = lines[1:]
    parsed_rows = list(csv.reader(data_lines))
    assert len(parsed_rows) == len(data_lines), "a quoted field spans lines; line-wise filtering would misalign"
    kept_lines = [line for line, row in zip(data_lines, parsed_rows) if row[key_index] not in drop_keys]
    return "".join([lines[0]] + kept_lines), len(data_lines) - len(kept_lines)


def copy_gtfs_dropping_empty(src_path, dst_path, rows_to_drop):
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


def new_cleaned_paths():
    """The 2026-10-16 feeds cleaned as the pipeline cleans the 2026-10-09 ones; made once, then reused."""
    NEW_CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for feed_name in FEED_NAMES:
        dst_path = NEW_CLEANED_DIR / f"{feed_name}.zip"
        if dst_path.exists():
            print(f"reusing {dst_path.name} ({datetime.date.fromtimestamp(dst_path.stat().st_mtime)})")
        else:
            src_path = NEW_SOURCE_PATHS[feed_name]
            dropped = copy_gtfs_dropping_empty(src_path, dst_path, excluded_route_type_rows(src_path, EXCLUDED_ROUTE_TYPES))
            print(f"{feed_name}: cleaned copy made; empty tables dropped {dropped}")
        paths.append(dst_path)
    return paths


# --- pairs and Google times -------------------------------------------------------------------------
def pairs_of_set(set_name):
    """Pairs of one set with the columns routing and strata need."""
    columns = ["draw_no", "origin_lat", "origin_lon", "dest_lat", "dest_lon", "haversine_m", "dep_min_of_day"]
    if set_name == "train":
        split_df = pd.read_csv(SPLIT_PATH, usecols=["draw_no", "half"])
        pairs_df = pd.read_csv(PAIRS_PATH, usecols=columns)
        return pairs_df[pairs_df.draw_no.isin(split_df.draw_no[split_df.half == TRAIN_HALF])]
    if set_name == "second":
        return pd.read_csv(RESERVE_PATH, usecols=columns)
    topup_df = pd.read_csv(TOPUP_PATH, usecols=columns)
    return topup_df[topup_df.draw_no.isin(pd.read_csv(TOPUP_SELECTION_PATH).draw_no)]


def google_minutes(set_name):
    routes_path = {"train": FIRST_ROUTES_PATH, "second": SECOND_ROUTES_PATH, "topup": TOPUP_ROUTES_PATH}[set_name]
    routes_df = pd.read_csv(routes_path)
    default_df = routes_df[routes_df.is_default].drop_duplicates("draw_no")
    is_scored = default_df.route_scope.isin(GOOGLE_SCOPES) & default_df.arrival_from_request_s.notna()
    return pd.DataFrame({"draw_no": default_df.draw_no.values,
                         "google_min": np.round(default_df.arrival_from_request_s.to_numpy() / SECONDS_PER_MIN),
                         "is_scored": is_scored.to_numpy()})


# --- routing ---------------------------------------------------------------------------------------
def route(release):
    sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import
    import geopandas as gpd
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix

    def ttm_min(network, pair, departure, transport_modes, max_time_min):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.origin_lon], [pair.origin_lat]))
        destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=transport_modes, max_time=datetime.timedelta(minutes=max_time_min),
            speed_walking=WALK_SPEED_KMH))
        return matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]

    set_names = [name for name, set_release in SET_RELEASE.items() if set_release == release]
    pairs_df = pd.concat([pairs_of_set(name).assign(set_name=name) for name in set_names], ignore_index=True)
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_routes_{release}.csv"))
    table_path = saved[-1] if saved else DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_routes_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"release {release}: sets {set_names}, {len(pairs_df)} pairs; table {table_path.name}, "
          f"{len(done)} done, {len(todo_df)} to route", flush=True)
    if todo_df.empty:
        return
    gtfs_paths = [OLD_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES] if release == "20261009" else new_cleaned_paths()
    network = TransportNetwork(PBF_PATH, gtfs_paths)
    print("covers", CHECK_COVERS_DATE, network.transit_layer.covers(CHECK_COVERS_DATE), flush=True)
    transit_modes = [TransportMode.TRANSIT, TransportMode.WALK]
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        departure = datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))
        row = {"draw_no": pair.draw_no, "set_name": pair.set_name, "release": release,
               "stock_min": ttm_min(network, pair, departure, transit_modes, MAX_TIME_MIN),
               "shifted_min": ttm_min(network, pair, departure - datetime.timedelta(minutes=BOARD_SLACK_MIN),
                                      transit_modes, MAX_TIME_MIN + BOARD_SLACK_MIN),
               "walk_min": ttm_min(network, pair, departure, [TransportMode.WALK], MAX_TIME_MIN)}
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % 100 == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


# --- scoring ---------------------------------------------------------------------------------------
def no_wait_minutes(table_df):
    """N_hi, N_lo and the tie flag from S, H, W (transit_board_slack.no_wait_minutes); NaN past max_time = inf."""
    stock = table_df.stock_min.fillna(np.inf)
    walk = table_df.walk_min.fillna(np.inf)
    shifted = table_df.shifted_min.fillna(np.inf)
    is_transit_won = shifted < walk
    is_resolved_tie = ~is_transit_won & (stock < walk)
    is_tie = ~is_transit_won & ~is_resolved_tie & np.isfinite(walk)
    n_hi = np.where(is_transit_won, shifted - BOARD_SLACK_MIN, np.where(is_resolved_tie, walk - BOARD_SLACK_MIN, walk))
    n_lo = np.where(is_tie, walk - BOARD_SLACK_MIN, n_hi)
    return n_hi, n_lo, is_tie.to_numpy()


def wilson(successes, n):
    if n == 0:
        return np.nan, np.nan
    share = successes / n
    centre = (share + WILSON_Z ** 2 / (2 * n)) / (1 + WILSON_Z ** 2 / n)
    half_width = WILSON_Z * np.sqrt(share * (1 - share) / n + WILSON_Z ** 2 / (4 * n ** 2)) / (1 + WILSON_Z ** 2 / n)
    return centre - half_width, centre + half_width


def recall_precision(google_min, r5_min, cut_min):
    """(recall, n Google-below), (precision, n R5-below)."""
    is_google_below, is_r5_below = google_min <= cut_min, r5_min <= cut_min
    both = int((is_google_below & is_r5_below).sum())
    return (both, int(is_google_below.sum())), (both, int(is_r5_below.sum()))


def score_line(label, successes, n):
    low, high = wilson(successes, n)
    return f"{label} {successes / n if n else np.nan:.3f} ({successes}/{n}, 95% {low:.3f}-{high:.3f})"


def band_of(minutes):
    return np.select([minutes <= CUTS_MIN[1], minutes <= CUTS_MIN[2]], [1, 2], 3)


def is_away(google_min):
    return np.logical_or.reduce([(google_min >= low) & (google_min <= high) for low, high in AWAY_RANGES_MIN])


def zone_block(zone_df, cut_min, errors, rng, r5_column, is_gating):
    """Lines for one zone; returns (lines, failures)."""
    google, r5 = zone_df.google_min.to_numpy(), zone_df[r5_column].to_numpy()
    (rec_k, rec_n), (prec_k, prec_n) = recall_precision(google, r5, cut_min)
    lines = [f"  {score_line('recall', rec_k, rec_n)}; {score_line('precision', prec_k, prec_n)}"]
    failures = []
    if not is_gating:
        return lines, failures
    rec_low, rec_high = wilson(rec_k, rec_n)
    prec_low, prec_high = wilson(prec_k, prec_n)
    is_floor = rec_low > FLOOR and prec_low > FLOOR
    lines.append(f"  (2a) floor: lower ends {rec_low:.3f}, {prec_low:.3f} > {FLOOR}: {'PASS' if is_floor else 'FAIL'}")
    sim_recall, sim_precision = [], []
    for _ in range(N_SIMULATIONS):
        sim_r5 = google + rng.choice(errors, size=len(google), replace=True)
        (k_r, n_r), (k_p, n_p) = recall_precision(google, sim_r5, cut_min)
        sim_recall.append(k_r / n_r if n_r else np.nan)
        sim_precision.append(k_p / n_p if n_p else np.nan)
    bar_recall, bar_precision = np.nanmedian(sim_recall), np.nanmedian(sim_precision)
    is_noise = rec_high >= bar_recall and prec_high >= bar_precision
    lines.append(f"  (2b) unbiased-noise bar: recall {bar_recall:.3f} (sim 2.5-97.5% {np.nanpercentile(sim_recall, 2.5):.3f}-"
                 f"{np.nanpercentile(sim_recall, 97.5):.3f}), precision {bar_precision:.3f} ({np.nanpercentile(sim_precision, 2.5):.3f}-"
                 f"{np.nanpercentile(sim_precision, 97.5):.3f}); upper ends {rec_high:.3f}, {prec_high:.3f}: {'PASS' if is_noise else 'FAIL'}")
    from scipy.stats import binomtest
    n_early = int(((r5 <= cut_min) & (google > cut_min)).sum())
    n_late = int(((r5 > cut_min) & (google <= cut_min)).sum())
    sign_p = binomtest(n_early, n_early + n_late, 0.5).pvalue if n_early + n_late else 1.0
    gap = abs(rec_k / rec_n - prec_k / prec_n)
    is_balance = sign_p >= SIGN_TEST_ALPHA and gap <= CLOSE_TOLERANCE
    lines.append(f"  (2c) balance: misses R5 early {n_early}, late {n_late}, sign test p {sign_p:.3f} (>= {SIGN_TEST_ALPHA}); "
                 f"|recall - precision| {gap:.3f} (<= {CLOSE_TOLERANCE}): {'PASS' if is_balance else 'FAIL'}")
    for check, is_pass in [("floor", is_floor), ("noise bar", is_noise), ("balance", is_balance)]:
        if not is_pass:
            failures.append(check)
    return lines, failures


def score():
    run_date = f"{datetime.date.today():%Y%m%d}"
    tables = []
    for release in ["20261009", "20261016"]:
        saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_routes_{release}.csv"))
        assert saved, f"no routing table for {release}: run `route {release}` first"
        tables.append(pd.read_csv(saved[-1]))
        print(f"routing table {saved[-1].name}")
    routes_df = pd.concat(tables, ignore_index=True)
    frames = []
    for set_name in SET_RELEASE:
        set_df = pairs_of_set(set_name).merge(google_minutes(set_name), on="draw_no", how="left").assign(set_name=set_name)
        frames.append(set_df)
    df = pd.concat(frames, ignore_index=True).merge(routes_df.drop(columns="set_name"), on="draw_no", how="left")
    assert df.stock_min.notna().sum() + df.stock_min.isna().sum() == len(df)
    n_unrouted = int(df.release.isna().sum())
    assert n_unrouted == 0, f"{n_unrouted} pairs not routed"
    df["n_hi"], df["n_lo"], df["is_tie"] = no_wait_minutes(df)
    df["n_strict"] = df.n_hi + 1          # N <= cut - 1  <=>  N + 1 <= cut
    df["is_scored"] = df.is_scored.fillna(False).astype(bool)
    scored_df = df[df.is_scored].copy()
    scored_df["zone"] = 0
    for zone_no, (low, high) in ZONES_MIN.items():
        scored_df.loc[(scored_df.google_min >= low) & (scored_df.google_min <= high), "zone"] = zone_no

    lines = [f"{NAME} {run_date}: stock R5 {WALK_SPEED_KMH} km/h, no first wait, {WINDOW_DATE} at drawn minutes, 1-min window; "
             f"each set on its own release's network ({SET_RELEASE})",
             f"pairs {len(df)} by set {df.set_name.value_counts().to_dict()}; scored (Google default in scope) {len(scored_df)}; "
             f"ties (walk-only = transit) {int(df.is_tie.sum())}"]
    counts = {zone_no: scored_df[scored_df.zone == zone_no].set_name.value_counts().to_dict() for zone_no in ZONES_MIN}
    is_count_ok = all(counts[zone_no].get(name, 0) == expected for zone_no, by_set in EXPECTED_ZONE_COUNTS.items()
                      for name, expected in by_set.items())
    lines.append(f"stop check, zone counts by set {counts} vs expected {EXPECTED_ZONE_COUNTS}: {'OK' if is_count_ok else 'MISMATCH'}")

    is_away_pair = is_away(scored_df.google_min.to_numpy()) & np.isfinite(scored_df.n_hi.to_numpy())
    errors = (scored_df.n_hi - scored_df.google_min).to_numpy()[is_away_pair]
    error_median = np.median(errors)
    centred_errors = errors - error_median
    lines.append(f"R5 error away from the cuts (Google {AWAY_RANGES_MIN}, N_hi - Google): n {len(errors)}, median {error_median:+.1f}, "
                 f"mean {errors.mean():+.2f}, MAE {np.abs(errors).mean():.2f}; centred to median 0 for (2b)")

    rng = np.random.default_rng(SIMULATION_SEED)
    failures = []
    for zone_no, cut_min in CUTS_MIN.items():
        zone_df = scored_df[scored_df.zone == zone_no]
        lines.append(f"zone {zone_no} (Google {ZONES_MIN[zone_no][0]}-{ZONES_MIN[zone_no][1]}, cut {cut_min}), n {len(zone_df)}: gating on N_hi <= {cut_min}")
        zone_lines, zone_failures = zone_block(zone_df, cut_min, centred_errors, rng, "n_hi", True)
        lines += zone_lines
        failures += [f"zone {zone_no} {check}" for check in zone_failures]
        for label, column in [("N_lo (ties as transit)", "n_lo"), (f"strict N <= {cut_min - 1}", "n_strict")]:
            lines.append(f" reported, {label}:")
            lines += zone_block(zone_df, cut_min, centred_errors, rng, column, False)[0]
        for set_name in SET_RELEASE:
            lines.append(f" reported, {set_name} only:")
            lines += zone_block(zone_df[zone_df.set_name == set_name], cut_min, centred_errors, rng, "n_hi", False)[0]

    random_df = scored_df[scored_df.set_name.isin(RANDOM_SETS)]
    google_band, r5_band = band_of(random_df.google_min.to_numpy()), band_of(random_df.n_hi.to_numpy())
    is_outside_zones = (random_df.zone == 0).to_numpy()
    is_base = (google_band <= 2) & is_outside_zones
    is_band_miss = is_base & (r5_band != google_band)
    is_far_called = (random_df.google_min.to_numpy() > ZONES_MIN[2][1]) & (r5_band <= 2)
    n_hard = int(is_band_miss.sum() + is_far_called.sum())
    hard_low, hard_high = wilson(n_hard, int(is_base.sum()))
    is_hard = hard_high <= HARD_MISS_MAX
    lines.append(f"(3) hard misses, random samples ({len(random_df)} scored): Google band 1-2 outside zones {int(is_base.sum())}; "
                 f"R5 in another band {int(is_band_miss.sum())}; Google > {ZONES_MIN[2][1]} called band 1-2 {int(is_far_called.sum())}; "
                 f"share {n_hard / is_base.sum():.3f} (95% {hard_low:.3f}-{hard_high:.3f}; upper <= {HARD_MISS_MAX}): {'PASS' if is_hard else 'FAIL'}")
    hard_df = random_df[is_band_miss | is_far_called]
    for pair in hard_df.itertuples():
        lines.append(f"    {pair.set_name} draw_no {pair.draw_no}: Google {pair.google_min:.0f}, R5 N {pair.n_hi:.0f} "
                     f"(stock {pair.stock_min}, walk-only {pair.walk_min}), {pair.haversine_m:.0f} m, dep {int(pair.dep_min_of_day) // 60:02d}:{int(pair.dep_min_of_day) % 60:02d}")
    if not is_hard:
        failures.append("hard misses")
    for cut_min in CUTS_MIN.values():
        n_google, n_r5 = int((random_df.google_min <= cut_min).sum()), int((random_df.n_hi <= cut_min).sum())
        ratio = n_r5 / n_google
        is_ratio = COUNT_RATIO_RANGE[0] <= ratio <= COUNT_RATIO_RANGE[1]
        lines.append(f"    count ratio <= {cut_min}: R5 {n_r5} / Google {n_google} = {ratio:.3f} (bar {COUNT_RATIO_RANGE}): {'PASS' if is_ratio else 'FAIL'}")
        if not is_ratio:
            failures.append(f"count ratio <= {cut_min}")
    topup_df = scored_df[scored_df.set_name == "topup"].merge(pd.read_csv(TOPUP_SELECTION_PATH)[["draw_no", "sent_for_range"]], on="draw_no")
    for range_no, range_df in topup_df.groupby("sent_for_range"):
        g_band, r_band = band_of(range_df.google_min.to_numpy()), band_of(range_df.n_hi.to_numpy())
        base = (g_band <= 2) & (range_df.zone == 0).to_numpy()
        far = (range_df.google_min.to_numpy() > ZONES_MIN[2][1]) & (r_band <= 2)
        lines.append(f"    top-up range {range_no} (reported): {len(range_df)} scored, band 1-2 outside zones {int(base.sum())}, "
                     f"R5 in another band {int((base & (r_band != g_band)).sum())}, Google > {ZONES_MIN[2][1]} called band 1-2 {int(far.sum())}")

    lines.append("(4) reported, random samples: full bands")
    for cut_min in CUTS_MIN.values():
        (rec_k, rec_n), (prec_k, prec_n) = recall_precision(random_df.google_min.to_numpy(), random_df.n_hi.to_numpy(), cut_min)
        lines.append(f"  <= {cut_min}: {score_line('recall', rec_k, rec_n)}; {score_line('precision', prec_k, prec_n)}")
    zones_df = scored_df[scored_df.zone > 0].copy()
    zones_df["distance_bin"] = pd.cut(zones_df.haversine_m, DISTANCE_BINS_M, right=False)
    zones_df["hour_bin"] = pd.cut(zones_df.dep_min_of_day // 60, HOUR_BINS, right=False)
    for stratum in ["distance_bin", "hour_bin"]:
        lines.append(f"  zone pairs by {stratum} (all sets): R5 agrees with Google on its side of the cut")
        for zone_no, cut_min in CUTS_MIN.items():
            for bin_value, bin_df in zones_df[zones_df.zone == zone_no].groupby(stratum, observed=True):
                agree = ((bin_df.google_min <= cut_min) == (bin_df.n_hi <= cut_min)).sum()
                lines.append(f"    zone {zone_no} {bin_value}: {agree}/{len(bin_df)} = {agree / len(bin_df):.2f}")

    lines.insert(2, f"VERDICT: {'PASS' if not failures else 'FAIL on ' + ', '.join(failures)}"
                    f"{'' if is_count_ok else ' (zone-count stop check MISMATCH: read with care)'}")
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")
    df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_results.csv", index=False)


if __name__ == "__main__":
    if sys.argv[1] == "route":
        route(sys.argv[2])
    else:
        score()
