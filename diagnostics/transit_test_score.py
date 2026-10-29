"""TRN-15 (b)-(c): the test scorer; does the transit band model hold on the test (test half + extension)?

Claim under test (concepts/transit.md TRN-13, TRN-15; DESIGN.md Q23): the model of record for transit bands 1-2
(no-wait plain at cuts 10 / 20 on the v2 pathways network, each pair on its own date and its release's network,
scored against Google's range at k = 2) passes TRN-13's zone checks on unseen pairs, with its hard misses a
recorded cost, not barred. Where the pipeline relies on it: the transit bands (SCR-1, RCH-1) before they go into
reachability (RCH-18).

Rules (TRN-15 test reading rule, user 2026-10-20; scoring logic copied from transit_hard_miss_range.py, model
"no-wait plain (reported)", k = 2):
  Pairs: test half (1,248, release 2026-10-09) + extension (4,000, release 2026-10-16), all random; a pair is
    scored only if Google's default is in scope (TRN-11). R5: transit_pathway_network_v2.py `route <release> --test`.
  (1) Zones (7-13, 17-23 Google default minutes): floor (both Wilson lowers > 0.6), noise bar (error to the range
    on the test's own pairs away from the cuts, centred), balance (sign test p >= 0.05 and |recall - precision|
    <= 0.10). (2) Hard misses per cut (windows c-10..c-3 lost, c+3..c+10 false), each Wilson upper <= 0.05; a fail
    is a recorded cost, barred if severe (upper > 0.10) or concentrated (>= 5 misses, >= 2/3 in one service third
    holding < 1/3 of that test's tested pairs). (3) Lost reach at 10 report-only (no verdict, no severe).
    (4) Severe only where n >= 35. (5) Pooled test is the verdict; per release reported, severe per release at
    n >= 35. (6) Count ratio 0.90-1.10: a fail is a recorded cost, never a bar alone. (7) Service thirds fixed at
    training: low <= 36, mid 37-130, high >= 131 origin trips (Claude's tie rule, set before results: the
    training split put 23 of 29 pairs at 36 in low and 5 of 6 at 131 in high, so each tie value goes to that
    side). (8) Means beside medians. (9) Unseen-destination subset (destination hex in no training set: training
    half, second batch, top-up) report-only.
  Acceptance before the test is opened (`check`): on the training sets the scorer reproduces the own-date training
    tables exactly (z1 / z2 floor 0.737 / 0.826, false 10 4/294, lost 20 8/248, false 20 18/503, count ratio
    1.097 / 1.073) and, pair by pair, transit_pathway_network_v2_*_range_owndate_results.csv (default minute,
    range low, model minute). `test` refuses to run until today's check summary says PASS.
Predictions written before: diagnostics/transit_test_predictions.py.

Conclusion (opened once 2026-10-20; check PASS first: 3,448 / 3,448 pairs and every table value as the own-date
  training run): 5,248 pairs, 5,234 scored. Pooled (the verdict): zones z1 floor 0.799, z2 floor 0.828, noise bars
  pass, z1 balance passes, z2 balance FAILS (43 early / 24 late, sign p 0.027; gap 0.053); hard false 10 4/514,
  lost 20 11/417 (upper 0.047, passes), false 20 34/792 (upper 0.059) FAILS, not severe, not concentrated; lost 10
  0/83 (report-only); count ratio 1.011 / 1.084. Per release (TRN-15 (5)): 2026-10-09 test half false 20 14/190
  (upper 0.120 > 0.10, n >= 35): severe under the per-release rule; z2 balance and ratio <= 20 (1.164) fail there
  too. 2026-10-16 extension: hard lost 20 / false 20 fail, not severe. Unseen destinations (report-only): 2,045
  pairs here, not the recorded 1,364 (definition to settle); lost 20 5/100 (upper 0.112). Reading owed to the user.

Inputs (read only): the v2 route tables, the Google route tables and pair files in outputs/transit_validation/,
the cleaned feeds (service counts). Self-contained (CLAUDE.md D1). No API calls, no R5.
Usage: `python transit_test_score.py check`, then `... test`. Results carry the run date; a same-day rerun replaces
them; the test's service table is saved data and reused.
"""
import datetime
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_test_score"
V2_NAME = "transit_pathway_network_v2"
RANGE_NAME = "transit_hard_miss_range"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
RESERVE_PATH = SUBJECT_DIR / f"transit_pairs_reserve_{FILE_TAG}.csv"
TOPUP_PATH = SUBJECT_DIR / f"transit_pairs_topup_{FILE_TAG}.csv"
TOPUP_SELECTION_PATH = SUBJECT_DIR / f"transit_topup_selection_{FILE_TAG}.csv"
TEST_EXT_PATH = SUBJECT_DIR / f"transit_pairs_test_ext_{FILE_TAG}.csv"       # config.TRANSIT_TEST_EXT_PAIRS_PATH
ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                "test": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv",
                "test_ext": SUBJECT_DIR / f"transit_google_test_ext_20261016_{FILE_TAG}.routes.csv"}
CLEANED_DIRS = {20261009: PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned",
                20261016: DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016"}

# --- sets ------------------------------------------------------------------------------------------
TRAIN_HALF, TEST_HALF = "train", "test"
CHECK_SET_RELEASE = {"train": 20261009, "second": 20261016, "topup": 20261016}
TEST_SET_RELEASE = {"test": 20261009, "test_ext": 20261016}
CHECK_RANDOM_SETS = ["train", "second"]
TEST_RANDOM_SETS = ["test", "test_ext"]
TRAINING_SETS = ["train", "second", "topup"]   # for the unseen-destination subset (TRN-15 (9))
ROUTE_TAGS = {"check": "routes_owndate", "test": "routes_test"}

# --- values copied from the record (transit_hard_miss_range.py) ------------------------------------
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]  # TRN-11
SECONDS_PER_MIN = 60
MIN_PER_HOUR = 60
BOARD_SLACK_MIN = 1                            # no-wait = shifted run minus the 1-min shift
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
SEVERE_MIN_N = 35                              # TRN-15 (4)
REPORT_ONLY_TESTS = ["lost 10"]                # TRN-15 (3)
CONCENTRATED_SHARE = 2 / 3
CONCENTRATION_MIN_MISSES = 5
CONCENTRATION_TESTED_MAX = 1 / 3
STRATUM_LOW_MAX_TRIPS = 36                     # TRN-15 (7), tie rule Claude's
STRATUM_HIGH_MIN_TRIPS = 131
STRATUM_LABELS = ["low", "mid", "high"]
HOME_WAIT_GROUP_S = 300
TRAM_TYPE = "TRAM"

# --- service density (copied from transit_hard_miss_range.py) --------------------------------------
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
SERVICE_RADIUS_M = 700
SERVICE_HALF_WINDOW_MIN = 30
EARTH_RADIUS_M = 6_371_008.8
STOP_TIMES_CHUNK_ROWS = 2_000_000
GTFS_ENCODING = "utf-8-sig"
WEEKDAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EXCEPTION_ADDED, EXCEPTION_REMOVED = 1, 2

# --- acceptance (own-date training tables, 2026-10-20) ---------------------------------------------
EXPECTED_CHECK = {"z1 floor": "0.737", "z2 floor": "0.826", "z1 noise bar": "0.92/0.90, 0.89/0.77",
                  "z2 noise bar": "0.93/0.90, 0.91/0.85", "z1 balance": "17e/12l p 0.458, gap 0.045",
                  "z2 balance": "28e/22l p 0.480, gap 0.024", "hard false 10": "4/294", "hard lost 10": "0/50",
                  "hard lost 20": "8/248", "hard false 20": "18/503", "ratio <= 10": "1.097", "ratio <= 20": "1.073"}
PAIR_COLUMNS = ["draw_no", "origin_lat", "origin_lon", "dest_lat", "dest_lon", "dest_hex", "haversine_m", "dep_min_of_day"]


def newest(pattern):
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    assert saved, f"no {pattern}"
    return saved[-1]


# --- pairs -----------------------------------------------------------------------------------------
def pairs_of_set(set_name):
    if set_name in (TRAIN_HALF, TEST_HALF):
        split_df = pd.read_csv(SPLIT_PATH, usecols=["draw_no", "half"])
        pairs_df = pd.read_csv(PAIRS_PATH, usecols=PAIR_COLUMNS)
        return pairs_df[pairs_df.draw_no.isin(split_df.draw_no[split_df.half == set_name])]
    if set_name == "second":
        return pd.read_csv(RESERVE_PATH, usecols=PAIR_COLUMNS)
    if set_name == "test_ext":
        return pd.read_csv(TEST_EXT_PATH, usecols=PAIR_COLUMNS)
    topup_df = pd.read_csv(TOPUP_PATH, usecols=PAIR_COLUMNS)
    return topup_df[topup_df.draw_no.isin(pd.read_csv(TOPUP_SELECTION_PATH).draw_no)]


def google_table(set_name, draw_nos):
    """Default minute, scope, range lows (k = 1, 2), default's wait / walk-only / vehicles, for the given pairs."""
    routes_df = pd.read_csv(ROUTES_PATHS[set_name])
    routes_df = routes_df[routes_df.draw_no.isin(draw_nos)].sort_values(["draw_no", "route_ix"])
    default_df = routes_df[routes_df.is_default].drop_duplicates("draw_no").set_index("draw_no")
    out_df = pd.DataFrame({"default_min": np.round(default_df.arrival_from_request_s / SECONDS_PER_MIN),
                           "is_scored": default_df.route_scope.isin(GOOGLE_SCOPES) & default_df.arrival_from_request_s.notna(),
                           "default_wait_s": default_df.leave_wait_s, "default_walk_only": default_df.is_walk_only,
                           "default_vehicles": default_df.vehicle_types.fillna("")})
    usable_df = routes_df[routes_df.route_scope.isin(GOOGLE_SCOPES) & routes_df.arrival_from_request_s.notna()].copy()
    usable_df["minute"] = np.round(usable_df.arrival_from_request_s / SECONDS_PER_MIN)
    usable_df["rank"] = usable_df.groupby("draw_no").cumcount() + 1
    low = usable_df[usable_df["rank"] <= GATING_K].groupby("draw_no").minute.min().reindex(out_df.index)
    out_df[f"low_{GATING_K}"] = np.fmin(low.to_numpy(), out_df.default_min.to_numpy())
    return out_df.reset_index()


def load(mode):
    set_release = CHECK_SET_RELEASE if mode == "check" else TEST_SET_RELEASE
    frames = []
    for set_name, release in set_release.items():
        pairs_df = pairs_of_set(set_name).assign(set_name=set_name, release=release)
        frames.append(pairs_df.merge(google_table(set_name, pairs_df.draw_no), on="draw_no", how="left", validate="one_to_one"))
    df = pd.concat(frames, ignore_index=True)
    routes = []
    for release in sorted(set(set_release.values())):
        path = newest(f"{V2_NAME}_2*_{ROUTE_TAGS[mode]}_{release}.csv")
        print(f"reusing {path.name} ({datetime.date.fromtimestamp(path.stat().st_mtime)})")
        routes.append(pd.read_csv(path).drop(columns="release"))
    routes_df = pd.concat(routes, ignore_index=True)
    df = df.merge(routes_df, on=["set_name", "draw_no"], how="left", validate="one_to_one")
    assert df.default_min.notna().all(), "pairs without a Google default"
    assert df.own_date.notna().all(), f"not routed: {int(df.own_date.isna().sum())} pairs"
    walk, shifted = df.walk_min.fillna(np.inf).to_numpy(), df.shifted_min.fillna(np.inf).to_numpy()
    df["is_transit_won"] = shifted < walk
    df["model_min"] = np.where(df.is_transit_won, shifted - BOARD_SLACK_MIN, walk)
    df["is_r5_walk"] = ~df.is_transit_won
    df["is_scored"] = df.is_scored.astype(bool)
    return df


# --- service density (copied from transit_hard_miss_range.py, own date) ----------------------------
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


def service_counts(df):
    """Origin trips per pair on its own date (saved data: reused when present)."""
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_service_test.csv"))
    if saved:
        print(f"reusing {saved[-1].name} ({datetime.date.fromtimestamp(saved[-1].stat().st_mtime)})")
        return pd.read_csv(saved[-1])
    rows = []
    for release, release_df in df.groupby("release"):
        stop_frames = []
        for feed_name in FEED_NAMES:
            with zipfile.ZipFile(CLEANED_DIRS[release] / f"{feed_name}.zip") as gtfs_zip:
                stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype={"stop_id": str}, encoding=GTFS_ENCODING,
                                       usecols=["stop_id", "stop_lat", "stop_lon"])
            stop_frames.append(stops_df.assign(stop_key=feed_name + "|" + stops_df.stop_id))
        stops_df = pd.concat(stop_frames, ignore_index=True)
        origin_lists = near_stop_lists(stops_df, release_df.origin_lat.to_numpy(), release_df.origin_lon.to_numpy())
        count_dates = pd.to_datetime(release_df.own_date).dt.date.to_numpy()
        near_keys = set(stops_df.stop_key.to_numpy()[np.concatenate(list(origin_lists))])
        departures_df = release_departures(release, near_keys, sorted(set(count_dates)))
        by_stop = {key: group for key, group in departures_df.groupby(["date", "stop_key"])}
        stop_keys = stops_df.stop_key.to_numpy()
        for i, pair in enumerate(release_df.itertuples()):
            groups = [by_stop[(count_dates[i], key)] for key in stop_keys[origin_lists[i]] if (count_dates[i], key) in by_stop]
            trips = 0
            if groups:
                near_df = pd.concat(groups)
                is_window = ((near_df.dep_min >= pair.dep_min_of_day - SERVICE_HALF_WINDOW_MIN)
                             & (near_df.dep_min <= pair.dep_min_of_day + SERVICE_HALF_WINDOW_MIN))
                trips = int(near_df.trip_key[is_window].nunique())
            rows.append({"set_name": pair.set_name, "draw_no": pair.draw_no, "origin_trips": trips})
        print(f"release {release}: {len(release_df)} pairs counted", flush=True)
    service_df = pd.DataFrame(rows)
    service_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_service_test.csv", index=False)
    return service_df


def stratum_of(trips):
    return np.select([trips <= STRATUM_LOW_MAX_TRIPS, trips >= STRATUM_HIGH_MIN_TRIPS], ["low", "high"], "mid")


# --- statistics (copied from transit_hard_miss_range.py) -------------------------------------------
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
                     f"{by_stratum} of tested {tested_by}; groups {miss_df.group.value_counts().to_dict()}")
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
                    f"MAE {np.abs(signed).mean():.2f} (n {len(signed)}; > 20 min off {int((np.abs(signed) > 20).sum())})")
    failures = [name for name, (_, is_pass) in checks.items() if is_pass is not None and not is_pass]
    is_hard_fail = any(name.startswith("hard") for name in failures)
    checks["verdict"] = ("PASS" if not failures else "FAIL: " + ", ".join(failures), None)
    checks["stop condition"] = (("BARRED: " + "; ".join(verdicts)) if verdicts else
                                ("hard-miss fail is a recorded cost" if is_hard_fail else "no hard-miss fail"), None)
    return checks, [f"{label}:"] + notes, pd.concat(miss_frames, ignore_index=True).assign(subset=label)


def run(mode):
    run_date = f"{datetime.date.today():%Y%m%d}"
    if mode == "test":
        check_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_check_summary.txt"
        assert check_path.exists() and "acceptance: PASS" in check_path.read_text(encoding="utf-8"), "run check first (must PASS)"
    df = load(mode)
    lines = [f"{NAME} {run_date} {mode}: no-wait plain, cuts 10 / 20, k = {GATING_K}, v2 pathways, own dates",
             f"pairs {len(df)} by set {df.set_name.value_counts().to_dict()}; scored {int(df.is_scored.sum())} "
             f"(out of scope {int((~df.is_scored).sum())})"]
    if mode == "check":
        service_df = pd.read_csv(newest(f"{RANGE_NAME}_2*_service_owndate.csv"), usecols=["set_name", "draw_no", "origin_trips"])
    else:
        service_df = service_counts(df)
    df = df.merge(service_df, on=["set_name", "draw_no"], how="left", validate="one_to_one")
    assert df.origin_trips.notna().all(), "pairs without a service count"
    df["stratum"] = stratum_of(df.origin_trips.to_numpy())
    scored_df = df[df.is_scored].copy()
    lines.append(f"service thirds (fixed at training): {scored_df.stratum.value_counts().reindex(STRATUM_LABELS).to_dict()} scored pairs")

    random_sets = CHECK_RANDOM_SETS if mode == "check" else TEST_RANDOM_SETS
    random_df = scored_df[scored_df.set_name.isin(random_sets)]
    subsets = {"pooled": (random_df, scored_df, scored_df)}
    if mode == "test":
        training_hexes = set(pd.concat([pairs_of_set(name).dest_hex for name in TRAINING_SETS]))
        for set_name, release in TEST_SET_RELEASE.items():
            part_df = scored_df[scored_df.set_name == set_name]
            subsets[f"release {release} ({set_name})"] = (part_df, part_df, part_df)
        unseen_df = scored_df[~scored_df.dest_hex.isin(training_hexes)]
        lines.append(f"unseen-destination pairs: {int((~df.dest_hex.isin(training_hexes)).sum())} of {len(df)} "
                     f"({len(unseen_df)} scored)")
        subsets["unseen destinations"] = (unseen_df, unseen_df, unseen_df)
    table, detail, misses = {}, [], []
    for label, (hard_df, zone_df, error_df) in subsets.items():
        checks, notes, miss_df = score_set(hard_df, zone_df, error_df, label)
        table[label] = checks
        detail += notes
        misses.append(miss_df)
    table_df = pd.DataFrame({label: {name: f"{text}{'' if is_pass is None else (' ok' if is_pass else ' FAIL')}"
                                     for name, (text, is_pass) in checks.items()} for label, checks in table.items()})
    with pd.option_context("display.width", 300, "display.max_columns", 10, "display.max_colwidth", 70):
        lines += ["", table_df.to_string(), ""]
    lines += detail
    if mode == "check":
        pooled = table["pooled"]
        mismatches = [f"{name}: {pooled[name][0]} vs {expected}" for name, expected in EXPECTED_CHECK.items()
                      if not pooled[name][0].startswith(expected)]
        reference_df = pd.read_csv(newest(f"{V2_NAME}_2*_range_owndate_results.csv"))
        reference_df = reference_df.rename(columns={"n_min": "model_min"})
        compared = ["default_min", f"low_{GATING_K}", "model_min"]
        both_df = df.merge(reference_df[["set_name", "draw_no", "is_scored"] + compared],
                           on=["set_name", "draw_no"], suffixes=("", "_ref"), validate="one_to_one")
        pair_diffs = {column: int((~np.isclose(both_df[column].replace(np.inf, -1).fillna(-1),
                                               both_df[f"{column}_ref"].replace(np.inf, -1).fillna(-1))).sum()) for column in compared}
        pair_diffs["is_scored"] = int((both_df.is_scored != both_df.is_scored_ref.astype(bool)).sum())
        is_pass = not mismatches and len(both_df) == len(reference_df) and not any(pair_diffs.values())
        lines += ["", f"pairs matched to the reference {len(both_df)} of {len(reference_df)}; per-pair differences {pair_diffs}",
                  f"table differences: {mismatches or 'none'}", f"acceptance: {'PASS' if is_pass else 'FAIL'}"]
    summary = "\n".join(lines)
    print(summary)
    out_prefix = f"{NAME}_{run_date}_{mode}"
    (DIAGNOSTIC_DATA_DIR / f"{out_prefix}_summary.txt").write_text(summary + "\n", encoding="utf-8")
    table_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{out_prefix}_table.csv")
    pd.concat(misses, ignore_index=True).to_csv(DIAGNOSTIC_DATA_DIR / f"{out_prefix}_misses.csv", index=False)
    df.to_csv(DIAGNOSTIC_DATA_DIR / f"{out_prefix}_results.csv", index=False)


if __name__ == "__main__":
    assert sys.argv[1] in ("check", "test"), "usage: check | test"
    run(sys.argv[1])
