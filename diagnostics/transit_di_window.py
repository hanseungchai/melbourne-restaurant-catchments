"""Does DetailedItineraries at a 1-min window, with few draws, find TravelTimeMatrix's trip where transit wins?

Claim under test (concepts/transit.md T7 (e) "Next", TRN-6): DetailedItineraries (DI) at Google's own
minute (1-min window) with a few departure draws (monteCarloDraws, set past r5py's fixed 60) returns,
among its options, the trip TravelTimeMatrix (TTM) finds at that minute, so DI can supply validation's
per-route detail. Tested before only on one pair whose fastest trip was the direct walk
(diagnostics/transit_di_draws.py), so the rides went untested.
Rules, set by the user before the run (2026-10-17), zero failures allowed:
  R1  DI's earliest arrival (TRN-6's formula, option_arrival) within ARRIVAL_TOLERANCE_MIN of TTM's
      time at the same 1-min window, on every pair, at 5 and at 10 draws;
  R2  DI's earliest arrival at 5 vs 10 draws within ARRIVAL_TOLERANCE_MIN on every pair;
  1 draw is reported only. A pair with no DI result counts as a failure. Every failure is inspected one
  by one before DI's window and draws are chosen (TRN-6).
Where the pipeline relies on it: TRN-6 validation takes per-route detail (rides, boardings) from DI.

Pairs: exploration half (500), each at its drawn minute on WINDOW_DATE. Screened (one TTM process):
  t1      TTM at the 1-min window (transit + walk), whole minutes;
  walk    TTM walk only (one matrix, the diagonal kept): the direct walk;
  cap1    TTM at the 1-min window with at most one ride: has_transfer when t1 < cap1 (or cap1 unreached);
  spread  p99 - p1 over a 10-min window from t (the frequency proxy of transit_window_width_checks.py).
Kept: transit wins (t1 < walk, or walk unreached). Sample (seeded): N_TRANSFER pairs with a transfer
and the rest without, each half above and half below the winners' median spread (sparse / frequent);
a short stratum is taken whole and the others fill the gap.
DI: one process per draw count (the JVM dies with it), DI's per-pair code called directly (TripPlanner
on a RegionalTask, as transit_di_draws.py run_case) so monteCarloDraws can be set; r5py 1.1.7.

Conclusion (run 2026-10-17): R1 FAILS at 5 and at 10 draws, on the same 66 of 100 pairs; R2 fails on 1
(draw 20776). Transit wins on 455 of 500 screened pairs (183 with a transfer); sample 35 with a transfer,
65 without, half sparse each. DI - TTM in whole minutes: 1 draw mean +3.6 (-2 / +20), 5 draws +2.7
(-2 / +9), 10 draws +2.6 (-2 / +7), exact on 19-20. Not a sampling miss: at 10 draws every pair has 11
options but 1.33 distinct boarding sequences on average, and DI is late on 1-ride pairs too (median +2).
Three failures inspected by hand (draws 14046, 11110, 588): DI's arithmetic is right, but its only trips
are slower than TTM's best (TTM with at most 2 rides equals the default on all three; DI matches TTM's
1-ride time on 14046, is slower than it on 11110). Likely cause, unproven: r5py collects R5's results
into a dict keyed by departure second (r5py/r5/trip_planner.py L245-252), so each later state of R5's
list overwrites the earlier ones and one route per departure survives (the T7 (e) precondition read
from source on 2026-10-16). The 3 pairs where DI beats TTM by 1-2 min are not yet explained.

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release), the
OSM extract in frozen_inputs/osm_extract/, the transit pair draw and split in outputs/transit_validation/.
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls; r5py
only. The screen and each draw count's table are saved data: a rerun reuses the newest one and says so.
Results carry the run date; a same-day rerun replaces that day's results.
"""
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
GTFS_CLEANED_DIR = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_di_window"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # T7 (e) "Next": DI at 7G
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as the window diagnostics of 2026-10-17

# --- the run ---------------------------------------------------------------------------------------
DRAW_COUNTS = [1, 5, 10]                       # monteCarloDraws per DI run
RULE_DRAW_COUNTS = [5, 10]                     # R1 applies to these; 1 draw reported only
ARRIVAL_TOLERANCE_MIN = 1
N_PAIRS = 100
N_TRANSFER = 35                                # "at least ~30 with a transfer"
SEED = 20261017
SPREAD_WINDOW_MIN = 10                         # frequency proxy window, from t
SPREAD_PERCENTILES = [1, 99]
SINGLE_PERCENTILE = 49                         # any one but 50 (r5py renames a lone p50); 1 min gives one value
ONE_RIDE = 1
DEST_ID_OFFSET = 1_000_000                     # destination ids disjoint from origin ids (r5py gives 0 where equal)
SECONDS_PER_MIN = 60
PROCESS_TIME_LIMIT_S = 3600                    # per child process (network load ~1 min plus routing)
RESULT_PREFIX = "RESULT "


def points_gdf(ids, lats, lons):
    """r5py origins or destinations: an id column and point geometry."""
    import geopandas as gpd
    return gpd.GeoDataFrame({"id": np.asarray(ids)}, crs="EPSG:4326", geometry=gpd.points_from_xy(lons, lats))


def exploration_pairs_df():
    """Exploration pairs (training half, fetched first), with their drawn departure minute."""
    pairs_df = pd.read_csv(PAIRS_PATH)
    split_df = pd.read_csv(SPLIT_PATH)
    exploration_draws = split_df.loc[split_df.is_exploration, "draw_no"]
    return pairs_df[pairs_df.draw_no.isin(exploration_draws)].reset_index(drop=True)


def departure_of(pair):
    """The pair's drawn minute on WINDOW_DATE."""
    return datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))


def load_network():
    """r5py's network on the cleaned feeds (JVM memory set before r5py's import)."""
    sys.argv += ["--max-memory", R5_MAX_MEMORY]
    from r5py import TransportNetwork
    return TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])


def screen(output_path):
    """Child process: t1, walk, cap1 and spread for every exploration pair; saved to output_path."""
    network = load_network()
    from r5py import TransportMode, TravelTimeMatrix
    transit_modes = [TransportMode.TRANSIT, TransportMode.WALK]
    pairs_df = exploration_pairs_df()

    walk_df = pd.DataFrame(TravelTimeMatrix(
        network, origins=points_gdf(pairs_df.draw_no, pairs_df.origin_lat, pairs_df.origin_lon),
        destinations=points_gdf(pairs_df.draw_no + DEST_ID_OFFSET, pairs_df.dest_lat, pairs_df.dest_lon),
        transport_modes=[TransportMode.WALK], max_time=datetime.timedelta(minutes=MAX_TIME_MIN)))
    walk_df = walk_df[walk_df.to_id == walk_df.from_id + DEST_ID_OFFSET]
    walk_min = walk_df.set_index("from_id").travel_time

    def one_to_one(pair, departure, window_min, percentiles, **options):
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=points_gdf([0], [pair.origin_lat], [pair.origin_lon]),
            destinations=points_gdf([1], [pair.dest_lat], [pair.dest_lon]), departure=departure,
            departure_time_window=datetime.timedelta(minutes=window_min), percentiles=percentiles,
            transport_modes=transit_modes, max_time=datetime.timedelta(minutes=MAX_TIME_MIN), **options))
        return [matrix_df[f"travel_time_p{p}"].iloc[0] for p in percentiles]

    rows = []
    for pair in pairs_df.itertuples():
        departure = departure_of(pair)
        (t1,) = one_to_one(pair, departure, WINDOW_MIN, [SINGLE_PERCENTILE])
        (cap1,) = one_to_one(pair, departure, WINDOW_MIN, [SINGLE_PERCENTILE], max_public_transport_rides=ONE_RIDE)
        low, high = one_to_one(pair, departure, SPREAD_WINDOW_MIN, SPREAD_PERCENTILES)
        row = {"draw_no": pair.draw_no, "haversine_m": round(pair.haversine_m), "departure": departure,
               "t1_min": t1, "walk_min": walk_min.get(pair.draw_no, np.nan), "cap1_min": cap1,
               "spread_min": high - low}
        print(f"  {row}", flush=True)
        rows.append(row)
    pd.DataFrame(rows).to_csv(output_path, index=False)


def option_arrival(option_df, departure):
    """An option's arrival by TRN-6's formula: last ride departure + ride + the legs after it (r5py's walk
    legs carry cached times, so their clock times aren't used); walk only: departure + walk time."""
    is_ride = option_df.route_id.notna() & (option_df.route_id != "")
    if not is_ride.any():
        return departure + option_df.travel_time.sum()
    last_ride = option_df[is_ride].iloc[-1]
    after_df = option_df[option_df.segment > last_ride.segment]
    return last_ride.departure_time + last_ride.travel_time + after_df.travel_time.sum()


def run_di(draws, sample_path, output_path):
    """Child process: DI at WINDOW_MIN with `draws` departure draws for every sampled pair."""
    network = load_network()
    import geopandas as gpd
    from r5py import TransportMode
    from r5py.r5.regional_task import RegionalTask
    from r5py.r5.trip_planner import TripPlanner

    pairs_df = pd.read_csv(PAIRS_PATH).set_index("draw_no")
    rows = []
    for draw_no in pd.read_csv(sample_path).draw_no:
        pair = pairs_df.loc[draw_no]
        departure = departure_of(pair)
        row = {"draw_no": draw_no, "draws": draws}
        try:
            origin = gpd.points_from_xy([pair.origin_lon], [pair.origin_lat], crs="EPSG:4326")[0]
            destination = points_gdf([1], [pair.dest_lat], [pair.dest_lon])
            request = RegionalTask(network, origin=origin, destinations=destination, departure=departure,
                                   departure_time_window=datetime.timedelta(minutes=WINDOW_MIN),
                                   transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
                                   max_time=datetime.timedelta(minutes=MAX_TIME_MIN))
            request._regional_task.toLat, request._regional_task.toLon = pair.dest_lat, pair.dest_lon
            request._regional_task.monteCarloDraws = draws
            started = time.perf_counter()
            trips = TripPlanner(network, request).trips
            row["routing_s"] = round(time.perf_counter() - started, 2)
            legs = [[option] + segment for option, trip in enumerate(trips) for segment in trip.as_table()]
            legs_df = pd.DataFrame(legs, columns=["option", "segment", "transport_mode", "departure_time", "distance",
                                                  "travel_time", "wait_time", "feed", "agency_id", "route_id",
                                                  "start_stop_id", "end_stop_id", "geometry"])
            is_ride = legs_df.route_id.notna() & (legs_df.route_id != "")
            boardings = (legs_df[is_ride].assign(board=lambda df: df.route_id + "@" + df.departure_time.astype(str))
                         .groupby("option").board.agg("|".join))
            arrivals = pd.Series({option: option_arrival(option_df, departure)
                                  for option, option_df in legs_df.groupby("option")})
            row.update({"n_options": len(trips), "n_distinct_boardings": int(boardings.nunique())})
            if len(arrivals):
                best = arrivals.idxmin()
                row.update({"di_min": (arrivals.min() - departure).total_seconds() // SECONDS_PER_MIN,
                            "di_best_rides": int(is_ride[legs_df.option == best].sum()),
                            "di_best_boardings": boardings.get(best, "")})
        except Exception as error:                                       # recorded per pair, inspected after
            row["error"] = f"{type(error).__name__}: {error}"[:300]
        print(f"  {row}", flush=True)
        rows.append(row)
    pd.DataFrame(rows).to_csv(output_path, index=False)


def run_child(args, output_path, suffix, label):
    """Run one child process unless a saved table (any date) exists; return the table."""
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_{suffix}.csv"))
    if saved:
        print(f"reusing saved table {saved[-1].name} ({label})", flush=True)
        return pd.read_csv(saved[-1])
    print(f"running {label}", flush=True)
    child = subprocess.run([sys.executable, "-u", __file__, *args], timeout=PROCESS_TIME_LIMIT_S)
    if child.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {child.returncode}")
    return pd.read_csv(output_path)


def draw_sample(screen_df):
    """Transit-winning pairs: N_TRANSFER with a transfer, the rest without, each split sparse / frequent."""
    is_win = screen_df.t1_min.notna() & (screen_df.walk_min.isna() | (screen_df.t1_min < screen_df.walk_min))
    winners_df = screen_df[is_win].copy()
    winners_df["has_transfer"] = winners_df.cap1_min.isna() | (winners_df.t1_min < winners_df.cap1_min)
    winners_df["is_sparse"] = winners_df.spread_min > winners_df.spread_min.median()
    targets = {(True, True): N_TRANSFER // 2, (True, False): N_TRANSFER - N_TRANSFER // 2,
               (False, True): (N_PAIRS - N_TRANSFER) // 2, (False, False): N_PAIRS - N_TRANSFER - (N_PAIRS - N_TRANSFER) // 2}
    picked = []
    for (has_transfer, is_sparse), target in targets.items():
        stratum_df = winners_df[(winners_df.has_transfer == has_transfer) & (winners_df.is_sparse == is_sparse)]
        picked.append(stratum_df.sample(min(target, len(stratum_df)), random_state=SEED))
    sample_df = pd.concat(picked)
    shortfall = N_PAIRS - len(sample_df)
    if shortfall > 0:
        rest_df = winners_df.drop(sample_df.index)
        sample_df = pd.concat([sample_df, rest_df.sample(min(shortfall, len(rest_df)), random_state=SEED)])
    return winners_df, sample_df


def main():
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_date = datetime.date.today().strftime("%Y%m%d")
    screen_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_screen.csv"
    screen_df = run_child(["--screen", str(screen_path)], screen_path, "screen", "screen of the exploration pairs")
    winners_df, sample_df = draw_sample(screen_df)
    sample_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_sample.csv"
    sample_df.to_csv(sample_path, index=False)

    results_df = sample_df.copy()
    for draws in DRAW_COUNTS:
        di_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_di{draws}.csv"
        di_df = run_child(["--di", str(draws), str(sample_path), str(di_path)], di_path, f"di{draws}", f"DI at {draws} draws")
        keep = ["draw_no", "di_min", "n_options", "n_distinct_boardings", "di_best_rides", "di_best_boardings",
                "routing_s", "error"]
        di_df = di_df.reindex(columns=keep).rename(columns={col: f"{col}_d{draws}" for col in keep if col != "draw_no"})
        results_df = results_df.merge(di_df, on="draw_no", how="left")

    lines = [f"{NAME} {run_date}: {len(screen_df)} exploration pairs screened; transit wins on {len(winners_df)} "
             f"({int(winners_df.has_transfer.sum())} with a transfer; median spread {winners_df.spread_min.median()} min); "
             f"sampled {len(sample_df)}",
             "sample strata (has_transfer, is_sparse): " + json.dumps(
                 {str(key): int(count) for key, count in sample_df.groupby(["has_transfer", "is_sparse"]).size().items()}),
             f"window {WINDOW_MIN} min, max_time {MAX_TIME_MIN} min, tolerance {ARRIVAL_TOLERANCE_MIN} min; "
             "times in whole minutes from Google's minute"]
    failures = {}
    for draws in DRAW_COUNTS:
        gap = results_df[f"di_min_d{draws}"] - results_df.t1_min
        is_fail = gap.isna() | (gap.abs() > ARRIVAL_TOLERANCE_MIN)
        lines.append(f"DI {draws} draws - TTM: n with result {int(gap.notna().sum())}, mean {gap.mean():.2f}, "
                     f"range {gap.min()} / {gap.max()}, exact {int((gap == 0).sum())}, over tolerance or missing "
                     f"{int(is_fail.sum())}; routing s mean {results_df[f'routing_s_d{draws}'].mean():.2f}")
        if draws in RULE_DRAW_COUNTS:
            failures[f"R1 {draws} draws"] = results_df.draw_no[is_fail].tolist()
    gap_5_10 = results_df.di_min_d5 - results_df.di_min_d10
    is_fail = gap_5_10.isna() | (gap_5_10.abs() > ARRIVAL_TOLERANCE_MIN)
    lines.append(f"DI 5 - 10 draws: mean {gap_5_10.mean():.2f}, range {gap_5_10.min()} / {gap_5_10.max()}, "
                 f"over tolerance or missing {int(is_fail.sum())}")
    failures["R2 5 vs 10"] = results_df.draw_no[is_fail].tolist()
    for rule, draw_nos in failures.items():
        lines.append(f"VERDICT {rule}: {'PASS' if not draw_nos else 'FAIL'} ({len(draw_nos)} failures: {draw_nos})")
    lines.append(results_df.drop(columns=["departure"]).to_string(index=False))
    summary = "\n".join(lines)
    print(summary)
    results_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_results.csv", index=False)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary)


if __name__ == "__main__":
    if "--screen" in sys.argv:
        screen(Path(sys.argv[sys.argv.index("--screen") + 1]))
    elif "--di" in sys.argv:
        at = sys.argv.index("--di")
        run_di(int(sys.argv[at + 1]), Path(sys.argv[at + 2]), Path(sys.argv[at + 3]))
    else:
        main()
