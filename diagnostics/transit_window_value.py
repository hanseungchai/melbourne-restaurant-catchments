"""TRN-13 stage 2: how far does R5's value over a departure window move transit band calls from the single moment?

Claim under test (concepts/transit.md TRN-13, framing (c) and stage 2; DESIGN.md Q23; reported, not gating): the
reachability value is the expected time from a random moment over a departure window, wait included. Stage 2
reports how many band calls the window value moves against R5 at the single drawn minute, and how it scores
against Google's range (Google answered at one moment only, so that score is context, not a test). Where the
pipeline relies on it: the window length and statistic for transit bands (RCH-18), not yet decided.

Method (Claude's choices, written before the run):
  R5 at WALK_SPEED_KMH, each set on its own release's network (as transit_band_metric). Windows start at the
  pair's drawn minute and run forward n min (n = 10, 20, 30; the profile decision's t..t+n). One TravelTimeMatrix
  call per pair and window with percentiles 25 / 50 / 75: R5 times every minute of the window (wait at the stop
  included) and reduces them to percentiles, so the median is exact and the mean is not available (a per-minute
  profile, 1-min calls, costs ~n x the time: about 3 h at n = 30; not run). No-wait correction per minute as the
  production rule (T7 e): the window starts 1 min early, and a percentile P becomes P - 1 if P < W (walk-only,
  from the saved band-metric table), else W. A 1-min window from t - 1 reproduces the saved shifted_min (check,
  first CHECK_PAIRS pairs of each release).
  Reported: band calls (median) that differ from the single moment (no-wait plain, N), by direction and by
  window length; spread (75th - 25th); TRN-13 zone and per-cut hard-miss scores of the median against Google's
  range at k = 2 (as transit_hard_miss_range), for both the single moment and each window.

Conclusion (run 2026-10-18): 1-min window from t - 1 reproduces saved N on 57/57. Window medians move 3.7-3.9% of
  band calls (10 min: 134 of 3,448, 69 later / 65 earlier; 20 and 30 min similar, slightly more later), but move
  40-43% of pairs by 3+ min; p75 - p25 spread median 4-5 min. Against Google's single moment the window median
  scores worse (z2 recall 0.77-0.79 vs 0.90; false 20 27-34 misses): expected, Google answered one moment, so this
  is not a test of the window value. It puts 5 of the 7 late (group 4) misses and 3-4 of the 14 group 3 on Google's
  side. Validating the window value needs Google over a window (stage 3) or acceptance as a convention.

Inputs (read only): diagnostic_data/transit_hard_miss_range_*_results.csv (pairs, ranges, strata, N, W); the
cleaned feeds as transit_band_metric; the OSM extract in frozen_inputs/osm_extract/. The test half is not read.
Self-contained (CLAUDE.md D1). No paid API calls; r5py only.
Usage: `python transit_window_value.py route 20261009`, `... route 20261016` (one network per process), then
`... score`. Routing tables are saved data, written row by row: a rerun resumes the newest one.
"""
import datetime
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
CLEANED_DIRS = {"20261009": PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned",
                "20261016": DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016"}
NAME = "transit_window_value"
RANGE_NAME = "transit_hard_miss_range"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
MAX_TIME_MIN = 90
WALK_SPEED_KMH = 4.16                          # config.WALK_SPEED_KMH
BOARD_SLACK_MIN = 1
SINGLE_PERCENTILE = 49                         # r5py renames a lone p50
WINDOWS_MIN = [10, 20, 30]
PERCENTILES = [25, 50, 75]
CHECK_PAIRS = 30
CUTS_MIN = {1: 10, 2: 20}
ZONES_MIN = {1: (7, 13), 2: (17, 23)}
RANDOM_SETS = ["train", "second"]
GATING_K = 2
HARD_WINDOW_NEAR_MIN = 3
HARD_WINDOW_FAR_MIN = 10
WILSON_Z = 1.959964


# --- routing ---------------------------------------------------------------------------------------
def route(release):
    sys.argv += ["--max-memory", R5_MAX_MEMORY]
    import geopandas as gpd
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix

    def ttm(network, pair, departure, window_min, percentiles):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.origin_lon], [pair.origin_lat]))
        destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=window_min), percentiles=percentiles,
            transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
            max_time=datetime.timedelta(minutes=MAX_TIME_MIN + BOARD_SLACK_MIN), speed_walking=WALK_SPEED_KMH))
        return matrix_df

    pairs_df = pd.read_csv(sorted(DIAGNOSTIC_DATA_DIR.glob(f"{RANGE_NAME}_*_results.csv"))[-1])
    pairs_df = pairs_df[pairs_df.release.astype(int).astype(str) == release]
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_routes_{release}.csv"))
    table_path = saved[-1] if saved else DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_routes_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"release {release}: {len(pairs_df)} pairs; table {table_path.name}, {len(done)} done, {len(todo_df)} to route", flush=True)
    if todo_df.empty:
        return
    network = TransportNetwork(PBF_PATH, [CLEANED_DIRS[release] / f"{name}.zip" for name in FEED_NAMES])
    print("covers", WINDOW_DATE, network.transit_layer.covers(WINDOW_DATE), flush=True)
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        departure = (datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))
                     - datetime.timedelta(minutes=BOARD_SLACK_MIN))
        row = {"draw_no": pair.draw_no, "set_name": pair.set_name}
        for window_min in WINDOWS_MIN:
            matrix_df = ttm(network, pair, departure, window_min, PERCENTILES)
            for percentile in PERCENTILES:
                row[f"w{window_min}_p{percentile}"] = matrix_df[f"travel_time_p{percentile}"].iloc[0]
        if i < CHECK_PAIRS:
            row["check_1min"] = ttm(network, pair, departure, 1, [SINGLE_PERCENTILE])[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % 200 == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


# --- scoring ---------------------------------------------------------------------------------------
def wilson_upper(successes, n):
    if n == 0:
        return np.nan
    share = successes / n
    centre = (share + WILSON_Z ** 2 / (2 * n)) / (1 + WILSON_Z ** 2 / n)
    return centre + WILSON_Z * np.sqrt(share * (1 - share) / n + WILSON_Z ** 2 / (4 * n ** 2)) / (1 + WILSON_Z ** 2 / n)


def no_wait(percentile_min, walk_min):
    return np.where(percentile_min < walk_min, percentile_min - BOARD_SLACK_MIN, walk_min)


def band_of(minutes):
    return np.select([minutes <= CUTS_MIN[1], minutes <= CUTS_MIN[2]], [1, 2], 3)


def range_scores(df, minutes):
    """Zone recall / precision and per-cut hard misses (random sets) against Google's range at GATING_K."""
    low, high = df[f"low_{GATING_K}"].to_numpy(), df.default_min.to_numpy()
    parts = []
    is_random = df.set_name.isin(RANDOM_SETS).to_numpy()
    for zone_no, cut_min in CUTS_MIN.items():
        is_r5_below = minutes <= cut_min
        is_low_below, is_high_below = low <= cut_min, high <= cut_min
        is_google_below = np.where(is_low_below != is_high_below, is_r5_below, is_high_below)
        is_zone = (high >= ZONES_MIN[zone_no][0]) & (high <= ZONES_MIN[zone_no][1])
        both = (is_zone & is_google_below & is_r5_below).sum()
        early = (is_zone & is_r5_below & ~is_google_below).sum()
        late = (is_zone & ~is_r5_below & is_google_below).sum()
        parts.append(f"z{zone_no} rec {both / (is_zone & is_google_below).sum():.3f} prec {both / (is_zone & is_r5_below).sum():.3f} "
                     f"({early}e/{late}l)")
        for kind, low_min, high_min in [("lost", cut_min - HARD_WINDOW_FAR_MIN, cut_min - HARD_WINDOW_NEAR_MIN),
                                        ("false", cut_min + HARD_WINDOW_NEAR_MIN, cut_min + HARD_WINDOW_FAR_MIN)]:
            is_window = is_random & (high >= low_min) & (high <= high_min)
            misses = int((is_window & (is_r5_below != is_google_below)).sum())
            parts.append(f"{kind} {cut_min} {misses}/{int(is_window.sum())} (up {wilson_upper(misses, int(is_window.sum())):.3f})")
    return "; ".join(parts)


def score():
    run_date = f"{datetime.date.today():%Y%m%d}"
    range_path = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{RANGE_NAME}_*_results.csv"))[-1]
    df = pd.read_csv(range_path)
    tables = [pd.read_csv(sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_routes_{release}.csv"))[-1]) for release in CLEANED_DIRS]
    df = df.merge(pd.concat(tables, ignore_index=True).drop(columns="set_name"), on="draw_no", how="left")
    assert df[f"w{WINDOWS_MIN[0]}_p50"].notna().sum() + df[f"w{WINDOWS_MIN[0]}_p50"].isna().sum() == len(df)
    lines = [f"{NAME} {run_date}: R5 {WALK_SPEED_KMH} km/h over departure windows {WINDOWS_MIN} min from the drawn minute, "
             f"no-wait per minute; reading {range_path.name}", f"scored pairs {len(df)}"]
    walk = df.walk_min.fillna(np.inf).to_numpy()
    checked = df[df.check_1min.notna()]
    n_check_ok = int((no_wait(checked.check_1min.to_numpy(), checked.walk_min.fillna(np.inf).to_numpy())
                      == checked.n_min.to_numpy()).sum())
    lines.append(f"check, 1-min window from t - 1 with the no-wait rule = saved N: {n_check_ok}/{len(checked)} "
                 f"{'OK' if n_check_ok == len(checked) else 'MISMATCH'}")
    single = df.n_min.fillna(np.inf).to_numpy()
    lines.append(f"single moment (no-wait plain N) vs range: {range_scores(df, single)}")
    for window_min in WINDOWS_MIN:
        values = {p: no_wait(df[f"w{window_min}_p{p}"].fillna(np.inf).to_numpy(), walk) for p in PERCENTILES}
        median = values[50]
        is_finite = np.isfinite(median) & np.isfinite(single)
        shift = (median - single)[is_finite]
        spread = (values[75] - values[25])[np.isfinite(values[75]) & np.isfinite(values[25])]
        single_band, window_band = band_of(single), band_of(median)
        moved = single_band != window_band
        lines += [f"window {window_min} min, median: shift vs single moment median {np.median(shift):+.1f}, mean {shift.mean():+.2f}, "
                  f"|shift| >= 3 on {np.mean(np.abs(shift) >= 3):.3f}; spread p75 - p25 median {np.median(spread):.1f}, p90 {np.percentile(spread, 90):.1f}",
                  f"  band calls moved {int(moved.sum())} of {len(df)} ({moved.mean():.3f}): later {int((moved & (window_band > single_band)).sum())}, "
                  f"earlier {int((moved & (window_band < single_band)).sum())}; random-sample counts <= 10 / <= 20: single "
                  f"{int((single[df.set_name.isin(RANDOM_SETS)] <= 10).sum())} / {int((single[df.set_name.isin(RANDOM_SETS)] <= 20).sum())}, window "
                  f"{int((median[df.set_name.isin(RANDOM_SETS)] <= 10).sum())} / {int((median[df.set_name.isin(RANDOM_SETS)] <= 20).sum())}",
                  f"  vs range (context only; Google answered at one moment): {range_scores(df, median)}"]
        misses_path = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{RANGE_NAME}_*_misses.csv"))[-1]
        misses_df = pd.read_csv(misses_path)
        misses_df = misses_df[misses_df.model == "no-wait plain (reported)"].merge(
            df[["draw_no", "set_name"]].assign(window_median=median), on=["draw_no", "set_name"])
        by_group = []
        for group, group_df in misses_df.groupby("group"):
            cut_min = group_df.test.str.split().str[1].astype(int)
            is_fixed = np.where(group_df.test.str.startswith("false"), group_df.window_median > cut_min, group_df.window_median <= cut_min)
            by_group.append(f"{group}: {int(is_fixed.sum())}/{len(group_df)}")
        lines.append(f"  stage-1 misses (no-wait plain, k {GATING_K}) the window median puts on Google's side: {'; '.join(by_group)}")
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "route":
        route(sys.argv[2])
    else:
        score()
