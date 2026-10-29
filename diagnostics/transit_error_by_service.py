"""Transit model error vs Google by predicted time and per-hour local service level, and how weekend service compares.

Claim under test (concepts/reachability.md RCH-23, RCH-25 (1); DESIGN.md Q25): the frozen transit model's error
against Google, read conditional on the predicted time (ETA), does not grow at weekday service levels as thin as
weekend service, so weekday validation can be carried to weekend hours for bands 1-2 (labelled, partial by design:
weekends also differ in where service runs, which RCH-25 (2) maps). Where the pipeline relies on it: the weekend
decision in Q25 and the inputs of the RCH-23 uncertainty function (mode, predicted time, departure, service level).

Data (saved, no routing, no API): every scored pair of the frozen model (transit_holdout_score: training train /
second / topup, old test test / test_ext, holdout; all weekday departures, TRN-7), its Google default and the model's
seconds. Error e = (model seconds - Google default seconds) / 60, unrounded; the log ratio log(model_s / default_s)
beside it. (Changed after the first run, same day: e was model minute - Google minute, whose MAD is 0 or 1 on whole
minutes, so the robust SD was degenerate; the rule, bins and tiers are unchanged.) Pairs over the model's 90 min cap are left out of the error tables (counted).
Service (per pair, from the cleaned GTFS of its release, copied from transit_holdout_score): S_dep = distinct trips
departing stops within 700 m of the origin within +-30 min of the departure on the pair's own date (equals the saved
origin_trips: acceptance check A1); S_peak = the largest such count over centres 07:00-19:00 every 30 min that day;
rel = S_dep / S_peak (the hour's service as a share of the origin's own weekday peak; "weekend-like" is low rel).
Weekend reference: the same origins (release 20261016 sets) on Sat 2026-10-24 and Sun 2026-10-25 at centres
11:30-21:00 every 30 min (the union of the subject's and its sibling's hours, RCH-21), rel against the origin's own
weekday peak. Trips that run after midnight on the previous day's service are not counted (early hours undercount).

Reading rule (Claude's, written before the first run; not OK'd by the user): in each predicted-ETA bin inside 5-30 min
(the bands' reach), compare the robust SD (1.4826 x MAD) of e for weekend-like pairs (rel < 0.6) with that for full
service (rel >= 0.8), bootstrap 90% interval of the ratio. "No worse" if every bin with n >= 50 on both sides has a
ratio <= 1.25, or its interval reaches below 1.25 ("not shown worse"); otherwise "worse" in that bin. Coverage: the
share of weekend cells (origin x hour) whose rel tier and absolute-service third hold >= 50 scored weekday pairs.
Report-only: tables by absolute service third (training thirds: <= 36, 37-130, >= 131 trips), by hour of day, the
ETA x rel cross, median and mean beside the spread, mode group.

Conclusion (run 2026-10-22, 73rd, autonomous; facts, the reading is the user's): 12,710 pairs, 12,575 scored (33
unscored, 102 over the cap); A1 PASS (S_dep = origin_trips on every pair). Spread grows with ETA: robust SD 0.67 min
at 5-10, 0.89-1.00 at 10-30, 1.19 at 30-45, 1.38 at 45+; mean (model - Google) -0.2 at 5-10 to -1.2 at 25-30 (the
model early, a long left tail: p10 -1.5 to -5.1). Rule: no worse in every bin 10-30 (ratios thin / full 0.87-1.13);
5-10 ratio 1.48 (interval 0.93-2.13, n 71 / 80) "not shown worse". By absolute third and by rel tier the spread is
flat (0.99-1.16); the means differ only through the night: rel < 0.4 at 45+ min and hours 00-07 carry the huge left
tail (mean -22.6 / -15.7; pairs where Google waits for the first service). Training, old test and holdout alike per
ETA bin. Weekend reference (6,816 origins, Sat 24 / Sun 25 Oct, 11:30-21:00): median rel Sat 0.56, Sun 0.49, falling
after 18:00 to 0.41 / 0.32 at 21:00; shares rel < 0.4: Sat 0.13, Sun 0.27 vs weekday pairs at those hours 0.01 (the
weekday pairs of rel < 0.4 come mostly from other hours); 99% of weekend cells covered (tier x third >= 50 pairs);
~1% of cells have no service within 700 m. Reading for Q25 (Claude's): service thinness alone does not widen the
error in the bands' reach; where weekend service runs is RCH-25 (2)'s question, not answered here.
----

Inputs (read only): transit_holdout_score_*_{seen,holdout}_results.csv, own dates (transit_hard_miss_range service
table, transit_pathway_network_v2 routes, the holdout answer file's departure_local), cleaned GTFS of both releases.
Self-contained (CLAUDE.md D1). Usage: `python transit_error_by_service.py` (service table reused when saved today or
earlier).
"""
import datetime
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
NAME = "transit_error_by_service"
SCORE_NAME = "transit_holdout_score"
RANGE_NAME = "transit_hard_miss_range"
V2_NAME = "transit_pathway_network_v2"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
HOLDOUT_ANSWERS_PATH = SUBJECT_DIR / f"transit_google_holdout_20261016_{FILE_TAG}.csv"
CLEANED_DIRS = {20261009: PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned",
                20261016: DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016"}

# --- sets ------------------------------------------------------------------------------------------
TRAINING_SETS = ["train", "second", "topup"]
OLD_TEST_SETS = ["test", "test_ext"]
SET_GROUPS = {"train": "training", "second": "training", "topup": "training", "test": "old test",
              "test_ext": "old test", "holdout": "holdout"}
WEEKEND_RELEASE = 20261016
WEEKEND_DATES = [datetime.date(2026, 10, 24), datetime.date(2026, 10, 25)]   # Sat, Sun inside the release's window

# --- service density (copied from transit_holdout_score.py) -----------------------------------------
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
SERVICE_RADIUS_M = 700
SERVICE_HALF_WINDOW_MIN = 30
EARTH_RADIUS_M = 6_371_008.8
STOP_TIMES_CHUNK_ROWS = 2_000_000
GTFS_ENCODING = "utf-8-sig"
WEEKDAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EXCEPTION_ADDED, EXCEPTION_REMOVED = 1, 2
SECONDS_PER_MIN = 60
MIN_PER_HOUR = 60
PEAK_CENTRES_MIN = np.arange(7 * MIN_PER_HOUR, 19 * MIN_PER_HOUR + 1, 30)          # 07:00-19:00 every 30 min
WEEKEND_CENTRES_MIN = np.arange(11 * MIN_PER_HOUR + 30, 21 * MIN_PER_HOUR + 1, 30)  # 11:30-21:00 every 30 min

# --- tiers and bins --------------------------------------------------------------------------------
ETA_EDGES_MIN = [0, 5, 10, 15, 20, 25, 30, 45, 91]
BAND_ETA_RANGE_MIN = (5, 30)                   # bins read by the rule
REL_EDGES = [0, 0.4, 0.6, 0.8, 1.0001, np.inf]
REL_LABELS = ["<0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0", ">1"]
WEEKEND_LIKE_REL = 0.6                         # rel below: weekend-like
FULL_SERVICE_REL = 0.8                         # rel at or above: full service
STRATUM_LOW_MAX_TRIPS = 36                     # training thirds (transit_holdout_score)
STRATUM_HIGH_MIN_TRIPS = 131
STRATUM_LABELS = ["low", "mid", "high"]
HOUR_GROUPS = [(0, 7, "00-07"), (7, 10, "07-10"), (10, 16, "10-16"), (16, 19, "16-19"), (19, 24, "19-24")]
MAD_TO_SD = 1.4826
BIG_ERROR_MIN = 3
RULE_MIN_N = 50
RULE_MAX_RATIO = 1.25
COVERAGE_MIN_N = 50
N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 20261022
INTERVAL_LEVEL = 0.90


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def newest(pattern):
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return saved[-1] if saved else None


# --- pairs -----------------------------------------------------------------------------------------
def own_dates():
    frames = [pd.read_csv(newest(f"{RANGE_NAME}_2*_service_owndate.csv"), usecols=["set_name", "draw_no", "count_date"])
              .rename(columns={"count_date": "own_date"})]
    for release in (20261009, 20261016):
        routes_df = pd.read_csv(newest(f"{V2_NAME}_2*_routes_test_{release}.csv"), usecols=["set_name", "draw_no", "own_date"])
        frames.append(routes_df[routes_df.set_name.isin(OLD_TEST_SETS)])
    answers_df = pd.read_csv(HOLDOUT_ANSWERS_PATH, usecols=["draw_no", "departure_local"])
    frames.append(pd.DataFrame({"set_name": "holdout", "draw_no": answers_df.draw_no,
                                "own_date": answers_df.departure_local.str[:10]}))
    dates_df = pd.concat(frames, ignore_index=True).drop_duplicates(["set_name", "draw_no"])
    dates_df["own_date"] = pd.to_datetime(dates_df.own_date).dt.date
    return dates_df


def load_pairs():
    frames = [pd.read_csv(newest(f"{SCORE_NAME}_2*_seen_results.csv")), pd.read_csv(newest(f"{SCORE_NAME}_2*_holdout_results.csv"))]
    pairs_df = pd.concat(frames, ignore_index=True).merge(own_dates(), on=["set_name", "draw_no"], how="left", validate="one_to_one")
    assert pairs_df.own_date.notna().all(), "pairs without an own date"
    assert all(date.weekday() < 5 for date in pairs_df.own_date), "a weekend own date"
    pairs_df["set_group"] = pairs_df.set_name.map(SET_GROUPS)
    return pairs_df


# --- service (copied from transit_holdout_score.py; dates per pair, counts at many centres) -----------
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


def release_stops(release):
    frames = []
    for feed_name in FEED_NAMES:
        with zipfile.ZipFile(CLEANED_DIRS[release] / f"{feed_name}.zip") as gtfs_zip:
            stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype={"stop_id": str}, encoding=GTFS_ENCODING,
                                   usecols=["stop_id", "stop_lat", "stop_lon"])
        frames.append(stops_df.assign(stop_key=feed_name + "|" + stops_df.stop_id))
    return pd.concat(frames, ignore_index=True)


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


def window_counts(by_stop, date, keys, centres):
    """Distinct trips departing the given stops within +-SERVICE_HALF_WINDOW_MIN of each centre (both ends inclusive)."""
    parts = [by_stop[(date, key)] for key in keys if (date, key) in by_stop]
    if not parts:
        return np.zeros(len(centres), dtype=int)
    dep = np.concatenate([p[0] for p in parts])
    trip = np.concatenate([p[1] for p in parts])
    order = np.argsort(dep, kind="stable")
    dep, trip = dep[order], trip[order]
    lows = np.searchsorted(dep, centres - SERVICE_HALF_WINDOW_MIN, side="left")
    highs = np.searchsorted(dep, centres + SERVICE_HALF_WINDOW_MIN, side="right")
    return np.array([np.unique(trip[a:b]).size for a, b in zip(lows, highs)])


def service_tables(pairs_df):
    """Per pair S_dep and S_peak on its own date; per release-20261016 origin the weekend cells. Saved data reused."""
    saved_pairs, saved_weekend = newest(f"{NAME}_2*_service_pairs.csv"), newest(f"{NAME}_2*_service_weekend.csv")
    if saved_pairs is not None and saved_weekend is not None:
        print(f"reusing {saved_pairs.name}, {saved_weekend.name} ({datetime.date.fromtimestamp(saved_pairs.stat().st_mtime)})")
        return pd.read_csv(saved_pairs), pd.read_csv(saved_weekend)
    pair_rows, weekend_rows = [], []
    for release, release_df in pairs_df.groupby("release"):
        stops_df = release_stops(release)
        stop_keys = stops_df.stop_key.to_numpy()
        origin_lists = near_stop_lists(stops_df, release_df.origin_lat.to_numpy(), release_df.origin_lon.to_numpy())
        near_keys = set(stop_keys[np.concatenate(list(origin_lists))])
        dates = sorted(set(release_df.own_date)) + (WEEKEND_DATES if release == WEEKEND_RELEASE else [])
        departures_df = release_departures(release, near_keys, dates)
        departures_df["trip_code"] = pd.factorize(departures_df.trip_key)[0]
        by_stop = {key: (group.dep_min.to_numpy(), group.trip_code.to_numpy())
                   for key, group in departures_df.groupby(["date", "stop_key"])}
        seen_origins = set()
        for i, pair in enumerate(release_df.itertuples()):
            keys = stop_keys[origin_lists[i]]
            centres = np.concatenate([[pair.dep_min_of_day], PEAK_CENTRES_MIN])
            counts = window_counts(by_stop, pair.own_date, keys, centres)
            pair_rows.append({"set_name": pair.set_name, "draw_no": pair.draw_no, "s_dep": int(counts[0]),
                              "s_peak": int(counts[1:].max())})
            origin = (round(pair.origin_lat, 7), round(pair.origin_lon, 7))
            if release == WEEKEND_RELEASE and origin not in seen_origins:
                seen_origins.add(origin)
                for date in WEEKEND_DATES:
                    weekend_counts = window_counts(by_stop, date, keys, WEEKEND_CENTRES_MIN)
                    weekend_rows += [{"set_name": pair.set_name, "draw_no": pair.draw_no, "date": date, "centre_min": int(c),
                                      "s_weekend": int(n), "s_peak": int(counts[1:].max())}
                                     for c, n in zip(WEEKEND_CENTRES_MIN, weekend_counts)]
        print(f"  {release}: {len(release_df)} pairs counted", flush=True)
    service_df, weekend_df = pd.DataFrame(pair_rows), pd.DataFrame(weekend_rows)
    service_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_service_pairs.csv", index=False)
    weekend_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_service_weekend.csv", index=False)
    return service_df, weekend_df


# --- tables ----------------------------------------------------------------------------------------
def robust_sd(values):
    values = np.asarray(values, dtype=float)
    return MAD_TO_SD * np.median(np.abs(values - np.median(values))) if len(values) else np.nan


def spread_row(group_df):
    e = group_df.error_min.to_numpy()
    return {"n": len(e), "median": np.median(e) if len(e) else np.nan, "mean": e.mean() if len(e) else np.nan,
            "robust_sd": robust_sd(e), "mae": np.abs(e).mean() if len(e) else np.nan,
            "p10": np.quantile(e, 0.1) if len(e) else np.nan, "p90": np.quantile(e, 0.9) if len(e) else np.nan,
            f"share_abs_ge_{BIG_ERROR_MIN}": (np.abs(e) >= BIG_ERROR_MIN).mean() if len(e) else np.nan,
            "log_ratio_robust_sd": robust_sd(group_df.log_ratio)}


def spread_table(df, by):
    rows = [{**dict(zip(by, key if isinstance(key, tuple) else (key,))), **spread_row(group)}
            for key, group in df.groupby(by, observed=True)]
    return pd.DataFrame(rows)


def ratio_interval(thin, full, rng):
    ratios = [robust_sd(rng.choice(thin, len(thin))) / robust_sd(rng.choice(full, len(full))) for _ in range(N_BOOTSTRAP)]
    tail = (1 - INTERVAL_LEVEL) / 2
    return np.nanquantile(ratios, tail), np.nanquantile(ratios, 1 - tail)


def tiers(values_df, trips_column):
    values_df["rel_tier"] = pd.cut(values_df.rel, REL_EDGES, right=False, labels=REL_LABELS)
    values_df["stratum"] = np.select([values_df[trips_column] <= STRATUM_LOW_MAX_TRIPS,
                                      values_df[trips_column] >= STRATUM_HIGH_MIN_TRIPS], ["low", "high"], "mid")
    return values_df


def main():
    tag = run_date()
    pairs_df = load_pairs()
    service_df, weekend_df = service_tables(pairs_df)
    df = pairs_df.merge(service_df, on=["set_name", "draw_no"], how="left", validate="one_to_one")
    mismatch = int((df.s_dep != df.origin_trips).sum())
    lines = [f"{NAME} {tag}: {len(df)} pairs ({df.set_group.value_counts().to_dict()}); frozen model, Google default",
             f"(A1) S_dep equals saved origin_trips on {len(df) - mismatch} / {len(df)} pairs: {'PASS' if mismatch == 0 else 'FAIL'}"]
    df["rel"] = np.where(df.s_peak > 0, df.s_dep / df.s_peak.where(df.s_peak > 0), np.nan)
    df = tiers(df, "s_dep")
    df["hour_group"] = pd.cut(df.dep_min_of_day / MIN_PER_HOUR, [g[0] for g in HOUR_GROUPS] + [24], right=False,
                              labels=[g[2] for g in HOUR_GROUPS])
    is_capped = ~np.isfinite(df.model_s)
    scored_df = df[df.is_scored.astype(bool) & ~is_capped].copy()
    scored_df["error_min"] = (scored_df.model_s - scored_df.default_s) / SECONDS_PER_MIN   # seconds, not rounded minutes
    scored_df["log_ratio"] = np.log(scored_df.model_s.clip(lower=1) / scored_df.default_s.clip(lower=1))
    scored_df["eta_bin"] = pd.cut(scored_df.model_min, ETA_EDGES_MIN, right=False)
    lines.append(f"scored {len(scored_df)} (left out: {int((~df.is_scored.astype(bool)).sum())} unscored, "
                 f"{int((df.is_scored.astype(bool) & is_capped).sum())} over the model's cap); no S_peak (no service "
                 f"07-19 within 700 m): {int(scored_df.rel.isna().sum())}")

    tables = {"eta": spread_table(scored_df, ["eta_bin"]), "rel": spread_table(scored_df, ["rel_tier"]),
              "stratum": spread_table(scored_df, ["stratum"]), "hour": spread_table(scored_df, ["hour_group"]),
              "eta_rel": spread_table(scored_df, ["eta_bin", "rel_tier"]),
              "eta_set": spread_table(scored_df, ["eta_bin", "set_group"]),
              "mode": spread_table(scored_df, ["mode_group"])}
    for name, table in tables.items():
        table.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_{name}.csv", index=False)
        lines += ["", f"by {name}:", table.to_string(index=False, float_format=lambda x: f"{x:.3f}")]

    # rule: weekend-like vs full service, per ETA bin inside the bands' reach
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    lines += ["", f"RULE (Claude's, pre-set): robust SD ratio rel < {WEEKEND_LIKE_REL} vs rel >= {FULL_SERVICE_REL}, "
              f"ETA bins in {BAND_ETA_RANGE_MIN}, n >= {RULE_MIN_N} both; no worse if ratio <= {RULE_MAX_RATIO} or "
              f"its {INTERVAL_LEVEL:.0%} interval reaches below it"]
    verdicts = []
    for eta_bin, group in scored_df.groupby("eta_bin", observed=True):
        if eta_bin.left < BAND_ETA_RANGE_MIN[0] or eta_bin.right > BAND_ETA_RANGE_MIN[1]:
            continue
        thin = group.error_min[group.rel < WEEKEND_LIKE_REL].to_numpy()
        full = group.error_min[group.rel >= FULL_SERVICE_REL].to_numpy()
        if len(thin) < RULE_MIN_N or len(full) < RULE_MIN_N:
            lines.append(f"  ETA {eta_bin}: n thin {len(thin)}, full {len(full)}: too few, not read")
            continue
        ratio = robust_sd(thin) / robust_sd(full)
        low, high = ratio_interval(thin, full, rng)
        verdict = "no worse" if ratio <= RULE_MAX_RATIO else ("not shown worse" if low <= RULE_MAX_RATIO else "worse")
        verdicts.append(verdict)
        lines.append(f"  ETA {eta_bin}: thin n {len(thin)} SD {robust_sd(thin):.2f}, full n {len(full)} SD "
                     f"{robust_sd(full):.2f}; ratio {ratio:.2f} ({low:.2f}-{high:.2f}): {verdict}")
    lines.append(f"  overall: {'WORSE in some bin' if 'worse' in verdicts else 'no worse' if verdicts else 'not read'}")

    # weekend reference: how thin is weekend service at the same origins, and do weekday pairs cover it
    weekend_df["rel"] = np.where(weekend_df.s_peak > 0, weekend_df.s_weekend / weekend_df.s_peak.where(weekend_df.s_peak > 0), np.nan)
    weekend_df = tiers(weekend_df, "s_weekend")
    weekend_df["day"] = pd.to_datetime(weekend_df.date).dt.day_name().str[:3]
    support = scored_df.groupby(["rel_tier", "stratum"], observed=True).size()
    cell_n = [support.get((tier, stratum), 0) for tier, stratum in zip(weekend_df.rel_tier, weekend_df.stratum)]
    weekend_df["weekday_pairs"] = cell_n
    weekend_df["is_covered"] = weekend_df.weekday_pairs >= COVERAGE_MIN_N
    weekday_band = scored_df[(scored_df.dep_min_of_day >= WEEKEND_CENTRES_MIN[0] - SERVICE_HALF_WINDOW_MIN)
                             & (scored_df.dep_min_of_day <= WEEKEND_CENTRES_MIN[-1] + SERVICE_HALF_WINDOW_MIN)]
    rel_share = pd.DataFrame({
        "weekday pairs 11-21.5h": weekday_band.rel_tier.value_counts(normalize=True).reindex(REL_LABELS),
        **{f"{day} cells": group.rel_tier.value_counts(normalize=True).reindex(REL_LABELS)
           for day, group in weekend_df.groupby("day")}})
    coverage = weekend_df.groupby("day").agg(cells=("is_covered", "size"), covered=("is_covered", "mean"),
                                             rel_median=("rel", "median"), no_service=("s_weekend", lambda s: (s == 0).mean()))
    by_centre = weekend_df.groupby(["day", "centre_min"]).rel.median().unstack(0)
    by_centre.index = [f"{c // MIN_PER_HOUR:02d}:{c % MIN_PER_HOUR:02d}" for c in by_centre.index]
    lines += ["", f"weekend reference: {weekend_df.drop_duplicates(['set_name', 'draw_no']).shape[0]} origins (release "
              f"{WEEKEND_RELEASE}), {', '.join(map(str, WEEKEND_DATES))}, centres 11:30-21:00 every 30 min; rel vs the "
              f"origin's own weekday peak", "rel tier shares:", rel_share.to_string(float_format=lambda x: f"{x:.3f}"),
              "", f"coverage (cell's rel tier x absolute third with >= {COVERAGE_MIN_N} scored weekday pairs):",
              coverage.to_string(float_format=lambda x: f"{x:.3f}"), "", "median rel by centre:",
              by_centre.to_string(float_format=lambda x: f"{x:.2f}")]
    weekend_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_weekend_cells.csv", index=False)

    figure(tables["eta_rel"], rel_share, tag)
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)


def figure(eta_rel_df, rel_share, tag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 4.5))
    labels = [str(b) for b in pd.cut(pd.Series([0]), ETA_EDGES_MIN, right=False).cat.categories]
    for tier in REL_LABELS:
        tier_df = eta_rel_df[(eta_rel_df.rel_tier == tier) & (eta_rel_df.n >= RULE_MIN_N)]
        positions = [labels.index(str(b)) for b in tier_df.eta_bin]
        left.plot(positions, tier_df.robust_sd, marker="o", label=f"rel {tier}")
    left.set_xticks(range(len(labels)), labels, rotation=30)
    left.set_xlabel("model's predicted minute (bin)")
    left.set_ylabel("robust SD of model - Google (min)")
    left.set_title(f"error spread by ETA and service share (n >= {RULE_MIN_N})")
    left.legend(fontsize=8)
    rel_share.plot.bar(ax=right)
    right.set_ylabel("share")
    right.set_xlabel("rel = trips this hour / origin's weekday peak")
    right.set_title("service share: weekday pairs vs weekend cells")
    fig.tight_layout()
    fig.savefig(DIAGNOSTIC_IMG_DIR / f"{NAME}_{tag}_spread.png", dpi=110)


if __name__ == "__main__":
    main()
