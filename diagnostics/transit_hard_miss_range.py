"""TRN-13 stage 1: do the transit candidates pass against Google's range, and where are the hard misses left?

Claim under test (concepts/transit.md TRN-13, "Decided 2026-10-18" (b)-(c) and "Plan and hard-miss bar"; DESIGN.md
Q23): scored against the range from the earliest arrival among Google's first 2 routes to its default (framing
(c)), stock R5 at 4.16 km/h calls transit bands 1-2 well enough, hard misses included. Where the pipeline relies
on it: the transit bands (SCR-1, RCH-1) before they go into reachability.

Test details (TRN-13's bars and the user's per-cut hard-miss bar; Claude's choices, written into docs/HANDOFF.md
before any result was computed, are marked "Claude"):
  Pairs, Google default minutes, R5 minutes and zones: as diagnostics/transit_model_compare.py (its saved results).
  Range (k routes): low = earliest rounded arrival among the default and the first k in-scope routes in Google's
    order (out-of-scope routes skipped: R5 can't ride them; Claude), high = the default's. k = 2 gates; k = 1
    (the test as run; reproduces transit_model_compare), 3 and all (up to 6) reported.
  Side of a cut c: R5 agrees if its side (minutes <= its cut) matches either end's side (a range spanning c
    agrees either way). Zones (TRN-13 (1)) on the default; recall and precision use Google's side as R5's when the
    range spans c, else the default's.
  (2a) floor, (2c) balance: as TRN-13. (2b) noise bar (Claude): error = signed distance from R5 to the range
    (0 inside) on pairs with the default away from the cuts, centred to median 0; simulated R5 = default + error,
    scored against the range.
  Hard misses per cut (user, replaces (3)'s pooled share), random samples (training half, second batch) only:
    lost reach = of pairs with the default at c-10..c-3 min, share R5 puts over c; false reach = of pairs at
    c+3..c+10, share R5 puts at or under c; each Wilson 95% upper <= 0.05. Windows inclusive (Claude). Top-up
    reported. Count ratio on the default, as (3).
  Stop condition (user, Claude's proposal): the model is barred from transit reachability if any per-cut share's
    upper > 0.10 (severe), or a failing share (upper > 0.05) with >= 5 misses (Claude) has >= 2/3 of them in one
    service-density third (concentrated). Otherwise a fail is a recorded cost.
  Service density (user's idea; Claude's measure): distinct trips departing within +-30 min of the pair's drawn
    minute on WINDOW_DATE (services active that day; after-midnight trips of the day before not counted) from any
    stop within 700 m straight line of the origin, on the pair's own release; thirds of the scored random-sample
    pairs (ranked by count, ties by set and draw_no). Destination count reported beside.
  Groups of the misses left (Claude, precedence in order): 4 R5 late (above the range); 2 R5 walk-only while
    Google's default rides; 1 Google's default waits >= 5 min at home; 3 Google's default rides a tram; else
    other early. "Large" = groups 1 + 3 >= 5 pairs or >= 1/3 of the misses (decides stages 1b / 2).
  Models: stock R5 4.16 (stage 1's subject) and no-wait at transit cuts 9 / 19 (= no-wait x s, TRN-13).
  Not blind: Claude had read the 38 hard-miss pairs (default and earliest arrivals) before these rules.

Conclusion (run 2026-10-18; Claude's rules marked above, not user-approved): stage 1 FAILS on hard misses for every
  model; zone checks pass for stock R5 and for plain no-wait against the range at k = 2.
  Stock R5 4.16 (k 2): zones pass (z1 0.817 / 0.854, z2 0.790 / 0.849); hard lost 20 22/248 (upper 0.131, all R5
  late) -> BARRED by the stop condition (severe). No-wait plain (k 2; reported model, added after the first run):
  every zone check passes (z1 0.859 / 0.806, z2 0.904 / 0.850, balance p 0.38 / 0.08); hard lost 10 0/50 (upper
  0.071: n too small to pass with no misses), false 10 4/294 (0.034), lost 20 7/248 (0.057), false 20 24/503
  (0.070) -> fail, not severe, not concentrated (false 20: 16/24 in the high-service third, which holds 0.40 of
  tested pairs): a recorded cost. No-wait at cuts 9 / 19 over-corrects under the range (z1, z2 noise bar, z2
  balance fail: R5 late). k = 3 / all change little. Concentration: Claude's pre-run reading dropped the user's
  "stratum under a third of tested pairs" clause on a false premise (thirds are over all pairs, not each test's);
  corrected to the user's wording after the first run, both readings reported. Groups of the 35 no-wait misses:
  3 tram / R5 faster 14, 4 late 7, 1 home wait 6, 2 R5 walks 5, other 3 (groups 1 + 3 large).

Inputs (read only): diagnostic_data/transit_model_compare_*_results.csv (newest); the three Google route tables
in outputs/transit_validation/; the cleaned feeds (outputs/pt_graph/gtfs_cleaned/ for 2026-10-09,
diagnostic_data/transit_band_metric_gtfs_cleaned_20261016/ for 2026-10-16). The test half is not read.
Self-contained (CLAUDE.md D1). No API calls, no R5.
Usage: `python transit_hard_miss_range.py service` (saved data, reused when present), then `... score`.
`... score --network=pathways` scores transit_pathway_network.py's rerun (its compare results; outputs under its name).
`... service --network=pathways_v2 --date=own` and `... score --network=pathways_v2 --date=own`: v2's own-date run,
service counted on each pair's own date (`service_owndate`), outputs tagged `range_owndate`.
Own-date conclusion (run 2026-10-20): service counts equal the 2026-10-18 table on all 481 pairs dated 2026-10-21;
every verdict as on Wednesday (2026-10-19). No-wait plain, k 2: z1 / z2 floor 0.737 / 0.826, false 10 4/294, lost 20
8/248 (upper 0.062), false 20 18/503 (upper 0.056, was 19): fail, not severe; stock R5 lost 20 20/248, still barred.
Results carry the run date; a same-day rerun replaces them.
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
NAME = "transit_hard_miss_range"
IS_PATHWAYS_V2 = "--network=pathways_v2" in sys.argv   # transit_pathway_network_v2.py (stops moved onto stubs)
IS_PATHWAYS = "--network=pathways" in sys.argv or IS_PATHWAYS_V2   # tables from transit_pathway_network*.py; outputs under its name
PATHWAYS_NAME = "transit_pathway_network_v2" if IS_PATHWAYS_V2 else "transit_pathway_network"
IS_OWN_DATE = "--date=own" in sys.argv         # v2's own-date compare results (TRN-13, user 2026-10-20)
assert not IS_OWN_DATE or IS_PATHWAYS_V2, "--date=own needs --network=pathways_v2"
OWN_TAG = "_owndate" if IS_OWN_DATE else ""
COMPARE_NAME = "transit_model_compare"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
CLEANED_DIRS = {20261009: PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned",
                20261016: DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016"}
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
TOPUP_SELECTION_PATH = SUBJECT_DIR / f"transit_topup_selection_{FILE_TAG}.csv"

# --- values copied from config.py and the record ---------------------------------------------------
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]  # TRN-11
SECONDS_PER_MIN = 60
MIN_PER_HOUR = 60
RANDOM_SETS = ["train", "second"]
ZONES_MIN = {1: (7, 13), 2: (17, 23)}
CUTS_MIN = {1: 10, 2: 20}
AWAY_RANGES_MIN = [(0, 6), (14, 16), (24, 30)]
NO_WAIT_TRANSIT_CUTS_MIN = {1: 9, 2: 19}       # no-wait x s as a transit cut shift (TRN-13)
PLAIN_NO_WAIT = "no-wait plain (reported)"
MODELS = ["stock 4.16", "no-wait cuts 9/19", PLAIN_NO_WAIT]   # the third added after the first run (Claude)
EXPECTED_STOCK_ZONE = {1: (0.805, 0.787), 2: (0.774, 0.774)}   # transit_model_compare, model 2, k = 1

# --- test ------------------------------------------------------------------------------------------
WILSON_Z = 1.959964
FLOOR = 0.6
N_SIMULATIONS = 2000
SIMULATION_SEED = 20261018
SIGN_TEST_ALPHA = 0.05
CLOSE_TOLERANCE = 0.10
COUNT_RATIO_RANGE = (0.90, 1.10)
GATING_K = 2
REPORTED_KS = [1, 2, 3, None]                  # None = all returned routes
HARD_WINDOW_NEAR_MIN = 3                       # per-cut windows: 3-10 min from the cut (user)
HARD_WINDOW_FAR_MIN = 10
HARD_MISS_MAX = 0.05                           # Wilson upper (user)
SEVERE_MAX = 0.10                              # stop condition: twice the bar (user)
CONCENTRATED_SHARE = 2 / 3                     # stop condition (user)
CONCENTRATION_MIN_MISSES = 5                   # Claude
CONCENTRATION_TESTED_MAX = 1 / 3               # the stratum holds under a third of that test's tested pairs (user)
N_STRATA = 3
STRATUM_LABELS = ["low", "mid", "high"]
HOME_WAIT_GROUP_S = 300                        # group 1: Google's default waits >= 5 min (Claude)
TRAM_TYPE = "TRAM"
LARGE_GROUP_MIN_PAIRS = 5                      # Claude
LARGE_GROUP_MIN_SHARE = 1 / 3                  # Claude

# --- service density (Claude) ----------------------------------------------------------------------
SERVICE_RADIUS_M = 700                         # ~10 min straight line at 4.16 km/h
SERVICE_HALF_WINDOW_MIN = 30
EARTH_RADIUS_M = 6_371_008.8
STOP_TIMES_CHUNK_ROWS = 2_000_000
GTFS_ENCODING = "utf-8-sig"
WEEKDAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EXCEPTION_ADDED, EXCEPTION_REMOVED = 1, 2


def newest(pattern):
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    assert saved, f"no {pattern}"
    return saved[-1]


def load_pairs():
    path = newest(f"{PATHWAYS_NAME}_2*_compare{OWN_TAG}_results.csv" if IS_PATHWAYS else f"{COMPARE_NAME}_*_results.csv")
    print(f"reusing {path.name} ({datetime.date.fromtimestamp(path.stat().st_mtime)})")
    return pd.read_csv(path)


# --- service density -------------------------------------------------------------------------------
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
    """For each point, the indices of stops_df within SERVICE_RADIUS_M (haversine)."""
    from sklearn.neighbors import BallTree
    tree = BallTree(np.radians(stops_df[["stop_lat", "stop_lon"]].to_numpy()), metric="haversine")
    return tree.query_radius(np.radians(np.column_stack([points_lat, points_lon])), r=SERVICE_RADIUS_M / EARTH_RADIUS_M)


def minutes_of(time_text):
    parts = time_text.str.split(":", expand=True).astype(int)
    return parts[0] * MIN_PER_HOUR + parts[1] + parts[2] / SECONDS_PER_MIN


def release_departures(release, stop_keys, dates):
    """Departures (date, stop key, trip key, minute) on each of dates at the given stops, all feeds of a release."""
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
                chunk = chunk[chunk.stop_id.isin(feed_stops) & chunk.trip_id.isin(active_trips)]
                kept.append(chunk)
            feed_df = pd.concat(kept, ignore_index=True).merge(trips_df, on="trip_id", how="left")
            print(f"  {release} {feed_name}: {len(dates)} dates, {len(service_ids)} services, {len(active_trips)} trips active, "
                  f"{len(feed_stops)} near stops, {len(feed_df)} departures kept", flush=True)
        for date, date_service_ids in services_by_date.items():
            date_df = feed_df[feed_df.service_id.isin(date_service_ids)]
            frames.append(pd.DataFrame({"date": date, "stop_key": feed_name + "|" + date_df.stop_id,
                                        "trip_key": feed_name + "|" + date_df.trip_id, "dep_min": minutes_of(date_df.departure_time)}))
    return pd.concat(frames, ignore_index=True)


def service():
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_service{OWN_TAG}.csv"))
    if saved:
        print(f"saved service table {saved[-1].name} exists ({datetime.date.fromtimestamp(saved[-1].stat().st_mtime)}); reused, not rebuilt")
        return
    pairs_df = load_pairs()
    pairs_df["count_date"] = pd.to_datetime(pairs_df.own_date).dt.date if IS_OWN_DATE else WINDOW_DATE
    rows = []
    for release, release_df in pairs_df.groupby("release"):
        release = int(release)
        stop_frames = []
        for feed_name in FEED_NAMES:
            with zipfile.ZipFile(CLEANED_DIRS[release] / f"{feed_name}.zip") as gtfs_zip:
                stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype={"stop_id": str}, encoding=GTFS_ENCODING,
                                       usecols=["stop_id", "stop_lat", "stop_lon"])
            stop_frames.append(stops_df.assign(stop_key=feed_name + "|" + stops_df.stop_id))
        stops_df = pd.concat(stop_frames, ignore_index=True)
        origin_lists = near_stop_lists(stops_df, release_df.origin_lat.to_numpy(), release_df.origin_lon.to_numpy())
        dest_lists = near_stop_lists(stops_df, release_df.dest_lat.to_numpy(), release_df.dest_lon.to_numpy())
        near_keys = set(stops_df.stop_key.to_numpy()[np.concatenate(list(origin_lists) + list(dest_lists))])
        departures_df = release_departures(release, near_keys, sorted(release_df.count_date.unique()))
        by_stop = {key: group for key, group in departures_df.groupby(["date", "stop_key"])}
        stop_keys = stops_df.stop_key.to_numpy()

        def trip_count(stop_indices, dep_min, date):
            groups = [by_stop[(date, key)] for key in stop_keys[stop_indices] if (date, key) in by_stop]
            if not groups:
                return 0
            near_df = pd.concat(groups)
            is_window = (near_df.dep_min >= dep_min - SERVICE_HALF_WINDOW_MIN) & (near_df.dep_min <= dep_min + SERVICE_HALF_WINDOW_MIN)
            return int(near_df.trip_key[is_window].nunique())

        for i, pair in enumerate(release_df.itertuples()):
            rows.append({"set_name": pair.set_name, "draw_no": pair.draw_no, "release": release,
                         "count_date": pair.count_date,
                         "origin_n_stops": len(origin_lists[i]),
                         "origin_trips": trip_count(origin_lists[i], pair.dep_min_of_day, pair.count_date),
                         "dest_n_stops": len(dest_lists[i]), "dest_trips": trip_count(dest_lists[i], pair.dep_min_of_day, pair.count_date)})
        print(f"release {release}: {len(release_df)} pairs counted", flush=True)
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_service{OWN_TAG}.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"saved {path.name}")


# --- Google's range --------------------------------------------------------------------------------
def google_ranges():
    """Per pair: default minute, range low for each k, and the default's wait, walk-only flag and vehicles."""
    frames = []
    for set_name, path in ROUTES_PATHS.items():
        routes_df = pd.read_csv(path).sort_values(["draw_no", "route_ix"])
        default_df = routes_df[routes_df.is_default].drop_duplicates("draw_no").set_index("draw_no")
        out_df = pd.DataFrame({"set_name": set_name, "default_ix": default_df.route_ix,
                               "default_min": np.round(default_df.arrival_from_request_s / SECONDS_PER_MIN),
                               "default_wait_s": default_df.leave_wait_s, "default_walk_only": default_df.is_walk_only,
                               "default_vehicles": default_df.vehicle_types.fillna("")})
        usable_df = routes_df[routes_df.route_scope.isin(GOOGLE_SCOPES) & routes_df.arrival_from_request_s.notna()].copy()
        usable_df["minute"] = np.round(usable_df.arrival_from_request_s / SECONDS_PER_MIN)
        usable_df["rank"] = usable_df.groupby("draw_no").cumcount() + 1
        for k in REPORTED_KS:
            first_df = usable_df if k is None else usable_df[usable_df["rank"] <= k]
            low = first_df.groupby("draw_no").minute.min().reindex(out_df.index)
            out_df[f"low_{k or 'all'}"] = np.fmin(low.to_numpy(), out_df.default_min.to_numpy())
        out_df["n_usable_routes"] = usable_df.groupby("draw_no").size().reindex(out_df.index).fillna(0).astype(int)
        frames.append(out_df.reset_index())
    return pd.concat(frames, ignore_index=True)


# --- statistics ------------------------------------------------------------------------------------
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
    """Google's side of the cut as the test reads it: R5's side when the range spans the cut, else the default's."""
    is_low_below, is_high_below = low <= cut_min, high <= cut_min
    return np.where(is_low_below != is_high_below, is_r5_below, is_high_below)


def distance_to_range(r5_min, low, high):
    return np.where(r5_min < low, r5_min - low, np.where(r5_min > high, r5_min - high, 0.0))


def zone_checks(zone_df, low_column, cut_min, r5_cut, centred_errors, rng):
    from scipy.stats import binomtest
    low, high, r5 = zone_df[low_column].to_numpy(), zone_df.default_min.to_numpy(), zone_df.model_min.to_numpy()
    is_r5_below = r5 <= r5_cut
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
    return {"recall": (f"{rec:.3f} ({rec_low:.2f}-{rec_high:.2f})", None),
            "precision": (f"{prec:.3f} ({prec_low:.2f}-{prec_high:.2f})", None),
            "floor": (f"{min(rec_low, prec_low):.3f}", rec_low > FLOOR and prec_low > FLOOR),
            "noise bar": (f"{rec_high:.2f}/{bar_recall:.2f}, {prec_high:.2f}/{bar_precision:.2f}",
                          rec_high >= bar_recall and prec_high >= bar_precision),
            "balance": (f"{n_early}e/{n_late}l p {sign_p:.3f}, gap {gap:.3f}", sign_p >= SIGN_TEST_ALPHA and gap <= CLOSE_TOLERANCE)}, (rec, prec)


def hard_tests(df, low_column, model_cuts):
    """Per-cut lost / false reach on the given pairs. Returns {test: (misses, n, low, high)} and the miss rows."""
    results, miss_frames = {}, []
    for zone_no, cut_min in CUTS_MIN.items():
        r5_cut = model_cuts[zone_no]
        is_r5_below = df.model_min.to_numpy() <= r5_cut
        is_google_below = google_side(df[low_column].to_numpy(), df.default_min.to_numpy(), is_r5_below, cut_min)
        default = df.default_min.to_numpy()
        for kind, low_min, high_min in [("lost", cut_min - HARD_WINDOW_FAR_MIN, cut_min - HARD_WINDOW_NEAR_MIN),
                                        ("false", cut_min + HARD_WINDOW_NEAR_MIN, cut_min + HARD_WINDOW_FAR_MIN)]:
            is_window = (default >= low_min) & (default <= high_min)
            is_miss = is_window & (is_r5_below != is_google_below)
            n, k = int(is_window.sum()), int(is_miss.sum())
            results[f"{kind} {cut_min}"] = (k, n) + wilson(k, n)
            miss_frames.append(df[is_miss].assign(test=f"{kind} {cut_min}"))
    return results, pd.concat(miss_frames, ignore_index=True)


def tested_pairs(df, test):
    """Pairs inside one per-cut window, test as 'lost 20' / 'false 10'."""
    kind, cut_text = test.split()
    cut_min = int(cut_text)
    if kind == "lost":
        low_min, high_min = cut_min - HARD_WINDOW_FAR_MIN, cut_min - HARD_WINDOW_NEAR_MIN
    else:
        low_min, high_min = cut_min + HARD_WINDOW_NEAR_MIN, cut_min + HARD_WINDOW_FAR_MIN
    return df[(df.default_min >= low_min) & (df.default_min <= high_min)]


def model_frame(df, model_label):
    if model_label == "stock 4.16":
        minutes = df.stock_min.fillna(np.inf).to_numpy()
        cuts = {zone_no: np.full(len(df), cut_min, dtype=float) for zone_no, cut_min in CUTS_MIN.items()}
        is_r5_walk = ~(df.stock_min.fillna(np.inf) < df.walk_min.fillna(np.inf)).to_numpy()
    else:
        minutes = df.n_min.fillna(np.inf).to_numpy()
        is_transit = df.is_transit_won.to_numpy().astype(bool)
        cuts = {zone_no: np.where(is_transit, NO_WAIT_TRANSIT_CUTS_MIN[zone_no], cut_min) for zone_no, cut_min in CUTS_MIN.items()}
        is_r5_walk = ~is_transit
        if model_label == PLAIN_NO_WAIT:
            cuts = {zone_no: np.full(len(df), cut_min, dtype=float) for zone_no, cut_min in CUTS_MIN.items()}
    return df.assign(model_min=minutes, is_r5_walk=is_r5_walk), cuts


def group_of(miss):
    if not miss.is_r5_below_cut:
        return "4 R5 misses Google's ride (late)"
    if miss.is_r5_walk and not miss.default_walk_only:
        return "2 R5 walks, Google rides"
    if miss.default_wait_s >= HOME_WAIT_GROUP_S:
        return "1 Google waits at home"
    if TRAM_TYPE in miss.default_vehicles:
        return "3 Google rides a tram, R5 faster"
    return "other early"


def score():
    run_date = f"{datetime.date.today():%Y%m%d}"
    out_prefix = f"{PATHWAYS_NAME}_{run_date}_range{OWN_TAG}" if IS_PATHWAYS else f"{NAME}_{run_date}"
    pairs_df = load_pairs()
    service_path = newest(f"{NAME}_*_service{OWN_TAG}.csv")
    lines = [f"{NAME} {run_date}{f' ({PATHWAYS_NAME})' if IS_PATHWAYS else ''}: TRN-13 stage 1, Google's range (gating k = {GATING_K}), per-cut hard misses, service strata",
             f"reusing {service_path.name} ({datetime.date.fromtimestamp(service_path.stat().st_mtime)})"]
    ranges_df = google_ranges()
    df = pairs_df.merge(ranges_df, on=["set_name", "draw_no"], how="left").merge(
        pd.read_csv(service_path).drop(columns="release"), on=["set_name", "draw_no"], how="left")
    assert df.default_min.notna().all() and df.origin_trips.notna().all(), "unmatched pairs"
    df = df[df.is_scored.astype(bool)].copy()
    n_default_mismatch = int((df.default_min != df.google_min).sum())
    lines.append(f"scored pairs {len(df)}; default minute = transit_model_compare's google_min on all: "
                 f"{'OK' if n_default_mismatch == 0 else f'MISMATCH {n_default_mismatch}'}; default is route 0 on "
                 f"{int((df.default_ix == 0).sum())} of {len(df)}")
    for k in REPORTED_KS:
        column = f"low_{k or 'all'}"
        width = df.default_min - df[column]
        lines.append(f"  range k = {k or 'all'}: default not the earliest on {int((width > 0).sum())} pairs; width median "
                     f"{width[width > 0].median():.0f} min where > 0; spans cut 10 on {int(((df[column] <= 10) & (df.default_min > 10)).sum())}, "
                     f"cut 20 on {int(((df[column] <= 20) & (df.default_min > 20)).sum())}")

    random_mask = df.set_name.isin(RANDOM_SETS)
    ranked = df[random_mask].sort_values(["origin_trips", "set_name", "draw_no"])
    thirds = np.array_split(ranked.index.to_numpy(), N_STRATA)
    df["stratum"] = ""
    for label, index in zip(STRATUM_LABELS, thirds):
        df.loc[index, "stratum"] = label
    bounds = [f"{label}: {df.loc[index, 'origin_trips'].min()}-{df.loc[index, 'origin_trips'].max()} trips (n {len(index)})"
              for label, index in zip(STRATUM_LABELS, thirds)]
    lines.append(f"service thirds (origin trips within {SERVICE_RADIUS_M} m, +-{SERVICE_HALF_WINDOW_MIN} min; random samples): {'; '.join(bounds)}")
    lines.append(f"  origin trips median {df.origin_trips.median():.0f}, zero on {int((df.origin_trips == 0).sum())}; "
                 f"destination median {df.dest_trips.median():.0f}, zero on {int((df.dest_trips == 0).sum())}")

    table, detail, miss_tables, reading_notes = {}, [], [], []
    for model_label in MODELS:
        model_df, model_cuts = model_frame(df, model_label)
        for k in REPORTED_KS:
            column = f"low_{k or 'all'}"
            label = f"{model_label}, k {k or 'all'}"
            checks = {}
            is_away_pair = is_away(model_df.default_min.to_numpy()) & np.isfinite(model_df.model_min.to_numpy())
            errors = distance_to_range(model_df.model_min.to_numpy(), model_df[column].to_numpy(), model_df.default_min.to_numpy())[is_away_pair]
            centred = errors - np.median(errors)
            rng = np.random.default_rng(SIMULATION_SEED)
            scores = {}
            for zone_no, cut_min in CUTS_MIN.items():
                is_zone = ((model_df.default_min >= ZONES_MIN[zone_no][0]) & (model_df.default_min <= ZONES_MIN[zone_no][1])).to_numpy()
                zone_results, scores[zone_no] = zone_checks(model_df[is_zone], column, cut_min, model_cuts[zone_no][is_zone], centred, rng)
                checks.update({f"z{zone_no} {name}": value for name, value in zone_results.items()})
            random_df = model_df[random_mask.to_numpy()]
            random_cuts = {zone_no: cuts[random_mask.to_numpy()] for zone_no, cuts in model_cuts.items()}
            hard, misses_df = hard_tests(random_df, column, random_cuts)
            verdicts = []
            for test, (k_miss, n, low, high) in hard.items():
                checks[f"hard {test}"] = (f"{k_miss}/{n}, upper {high:.3f}{' (0 misses: n too small)' if k_miss == 0 else ''}",
                                          high <= HARD_MISS_MAX)
                if high > SEVERE_MAX:
                    verdicts.append(f"severe ({test} upper {high:.3f} > {SEVERE_MAX})")
                if high > HARD_MISS_MAX and k_miss >= CONCENTRATION_MIN_MISSES:
                    counts = misses_df[misses_df.test == test].stratum.value_counts()
                    tested_share = (tested_pairs(random_df, test).stratum == counts.idxmax()).mean()
                    if counts.max() / k_miss >= CONCENTRATED_SHARE and tested_share < CONCENTRATION_TESTED_MAX:
                        verdicts.append(f"concentrated ({test}: {counts.max()}/{k_miss} in {counts.idxmax()}, {tested_share:.2f} of tested)")
                    elif counts.max() / k_miss >= CONCENTRATED_SHARE:
                        reading_notes.append(f"{label} {test}: {counts.max()}/{k_miss} misses in {counts.idxmax()}, which holds "
                                             f"{tested_share:.2f} of tested pairs (>= {CONCENTRATION_TESTED_MAX:.2f}): not concentrated "
                                             f"under the user's rule; concentrated under Claude's mistaken pre-run reading")
            for zone_no, cut_min in CUTS_MIN.items():
                n_google = int((random_df.default_min <= cut_min).sum())
                n_r5 = int((random_df.model_min.to_numpy() <= random_cuts[zone_no]).sum())
                checks[f"ratio <= {cut_min}"] = (f"{n_r5 / n_google:.3f}", COUNT_RATIO_RANGE[0] <= n_r5 / n_google <= COUNT_RATIO_RANGE[1])
            failures = [name for name, (_, is_pass) in checks.items() if is_pass is not None and not is_pass]
            is_hard_fail = any(name.startswith("hard") for name in failures)
            stop = ("BARRED: " + "; ".join(verdicts)) if verdicts else ("hard-miss fail is a recorded cost" if is_hard_fail else "no hard-miss fail")
            checks["verdict"] = ("PASS" if not failures else "FAIL: " + ", ".join(failures), None)
            checks["stop condition"] = (stop, None)
            table[label] = checks
            if k == 1 and model_label == "stock 4.16":
                is_repro = all(abs(scores[zone_no][0] - EXPECTED_STOCK_ZONE[zone_no][0]) < 0.0005
                               and abs(scores[zone_no][1] - EXPECTED_STOCK_ZONE[zone_no][1]) < 0.0005 for zone_no in CUTS_MIN)
                lines.append(f"check, k = 1 stock reproduces transit_model_compare's zone recall / precision {EXPECTED_STOCK_ZONE}: "
                             f"{'OK' if is_repro else 'MISMATCH ' + str(scores)}")
            if k == GATING_K:
                misses_df = misses_df.assign(model=model_label, is_r5_below_cut=lambda frame: frame.test.str.startswith("false"))
                misses_df["group"] = [group_of(miss) for miss in misses_df.itertuples()]
                miss_tables.append(misses_df)
                detail.append(f"model {label}: error to the range away from the cuts: n {len(errors)}, median {np.median(errors):+.1f}, "
                              f"mean {errors.mean():+.2f}, inside {np.mean(errors == 0):.2f}")
                for test, (k_miss, n, low, high) in hard.items():
                    test_df = misses_df[misses_df.test == test]
                    by_stratum = test_df.stratum.value_counts().reindex(STRATUM_LABELS, fill_value=0).to_dict()
                    tested_by = tested_pairs(random_df, test).stratum.value_counts().reindex(STRATUM_LABELS, fill_value=0).to_dict()
                    detail.append(f"  {test}: {k_miss}/{n} = {k_miss / n if n else np.nan:.3f} (95% {low:.3f}-{high:.3f}); misses by third {by_stratum} "
                                  f"of tested {tested_by}; groups {test_df.group.value_counts().to_dict()}")
                groups = misses_df.drop_duplicates("draw_no").group.value_counts()
                n_timing = int(groups.filter(regex="^[13] ").sum())
                is_large = n_timing >= LARGE_GROUP_MIN_PAIRS or n_timing >= LARGE_GROUP_MIN_SHARE * groups.sum()
                detail.append(f"  distinct missed pairs {int(groups.sum())}: {groups.to_dict()}; groups 1 + 3 = {n_timing}: "
                              f"{'LARGE (stages 1b / 2 run)' if is_large else 'not large'}")
                topup_df = model_df[(model_df.set_name == "topup").to_numpy()]
                topup_cuts = {zone_no: cuts[(model_df.set_name == "topup").to_numpy()] for zone_no, cuts in model_cuts.items()}
                topup_hard, _ = hard_tests(topup_df, column, topup_cuts)
                detail.append("  top-up (reported): " + "; ".join(f"{test} {k_miss}/{n}" for test, (k_miss, n, _, _) in topup_hard.items()))

    table_df = pd.DataFrame({label: {name: f"{text}{'' if is_pass is None else (' ok' if is_pass else ' FAIL')}"
                                     for name, (text, is_pass) in checks.items()} for label, checks in table.items()})
    with pd.option_context("display.width", 300, "display.max_columns", 20, "display.max_colwidth", 60):
        lines += ["", "side by side (zone checks on the range; hard = per-cut lost / false reach, random samples):",
                  table_df.to_string(), ""]
    lines += detail
    lines += ["", "concentration readings:"] + (reading_notes or ["  none"])
    misses_df = pd.concat(miss_tables, ignore_index=True)
    lines.append("")
    lines.append(f"misses at k = {GATING_K} (both models):")
    for miss in misses_df.sort_values(["model", "test", "draw_no"]).itertuples():
        lines.append(f"  {miss.model} | {miss.test} | {miss.set_name} {miss.draw_no}: default {miss.default_min:.0f}, low {getattr(miss, f'low_{GATING_K}'):.0f}, "
                     f"R5 {miss.model_min:.0f} (walk {miss.walk_min}), wait {miss.default_wait_s} s, {miss.default_vehicles or 'WALK'}, "
                     f"{miss.haversine_m:.0f} m, {int(miss.dep_min_of_day) // 60:02d}:{int(miss.dep_min_of_day) % 60:02d}, "
                     f"trips o/d {miss.origin_trips}/{miss.dest_trips} ({miss.stratum}) -> {miss.group}")
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{out_prefix}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")
    table_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{out_prefix}_table.csv")
    misses_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{out_prefix}_misses.csv", index=False)
    df.to_csv(DIAGNOSTIC_DATA_DIR / f"{out_prefix}_results.csv", index=False)


if __name__ == "__main__":
    if sys.argv[1] == "service":
        service()
    else:
        score()
