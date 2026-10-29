"""How does DetailedItineraries fare with more departure draws than r5py's 60?

Claim under test (concepts/transit.md T7 (e), TRN-6): R5's departure sampler, which DetailedItineraries
(DI) runs (McRaptorSuboptimalPathProfileRouter, read from the r5-v7.5.1-r5py jar's bytecode 2026-10-17),
works only at a few draws per minute, so raising monteCarloDraws (r5py fixes 60; regional_task.py L157)
can't buy denser departures. The sampler, with W the window in seconds and D the draws:
  step = W // D; half = step // 2; first time = start + U{0..step-1}; each next = previous +
  U{0..step-1} + half, while inside the window; the whole list is redrawn until it holds exactly D times,
  with no attempt limit (route(), L102-127 of the bytecode). D = 200 is refused outright.
Prediction, set before the r5py runs (2026-10-17) from simulate_sampler() below at W = 600 s: runs at
D = 30, 60, 70, 100; hangs at 80 and 120 (P(exactly D) ~ 0: the walk's mean count is far above D);
step 1 at D = 600, every step 0, the list grows until the heap runs out. Rule: CONFIRMED if every case's
outcome matches its prediction (finished / no result within the time limit / heap error).
Where the pipeline relies on it: TRN-6 takes DI at r5py's default (10-min window, 60 draws) and keeps
the options departing inside Google's minute; this checks there is no better draw setting.

Method: one exploration pair (PAIR_DRAW_NO) at its drawn minute on WINDOW_DATE, 10-min window. Each case
runs in its own process (the JVM dies with it) under a time limit that covers the network load. DI's
per-pair code is called directly (TripPlanner on a RegionalTask, as detailed_itineraries.py L209-216)
so monteCarloDraws can be set; r5py 1.1.7. Reported per finished case: options, distinct departure
seconds, distinct boarding sequences, routing seconds.

Conclusion (run 2026-10-17): CONFIRMED, all 7 cases as predicted. 30, 60, 70, 100 draws finish (~1 s
routing each); 80 and 120 give no result in 300 s; 600 runs out of heap in 12 s (the 1-min / 60-draw
heap error's mechanism, reproduced). More draws buy nothing: every finished case returns D + 1 options
(D samples plus the direct walk) but the same 5 distinct boarding sequences and the same 4 distinct
first-leg departure times. The latter is a second sign of the walk-leg cache (T7 e: r5py reuses each
stop's access leg and overwrites its times), unproven. r5py's 60 draws stand at 10 min.
Run 2 (1-min window, same pair): CONFIRMED: 1, 5, 6, 10 draws finish (~1 s); 60 runs out of heap in
11 s. DI's earliest arrival equals TTM's (11 min) in all 4, but this pair's fastest trip is the direct
walk, so the rides go untested. The legs show the walk-leg cache plainly: at 5 draws the 5 tram options
wait 6:24 to 7:15 (they leave at different seconds) yet all report one access walk departing 11:19:44,
and every egress walk starts 11:36:00 though the tram arrives 11:35. DI's walk-leg clock times are not
usable; rides are; arrivals use TRN-6's formula (option_arrival).

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release), the
OSM extract in frozen_inputs/osm_extract/, the transit pair draw in outputs/transit_validation/.
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls; r5py
only (~15 min, mostly time limits). The case table is saved data: a rerun reuses the newest one and says
so. Results carry the run date; a same-day rerun replaces that day's results.
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
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_di_draws"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "4G"                           # config.TRANSIT_DRAW_R5_MAX_MEMORY
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
MAX_TIME_MIN = 90                              # as the window diagnostics of 2026-10-17

# --- the run ---------------------------------------------------------------------------------------
PAIR_DRAW_NO = 687                             # an exploration pair DI routed on 2026-10-16 (frequent service)
DI_WINDOW_MIN = 10                             # r5py's default
SECONDS_PER_MIN = 60
CASES = [                                      # (draws, predicted outcome) at DI_WINDOW_MIN
    (30, "finished"), (60, "finished"), (70, "finished"), (100, "finished"),
    (80, "timed out"), (120, "timed out"), (600, "heap error")]
# Run 2 (user, 2026-10-17): Google's own minute, few draws. Prediction from simulate_sampler() at
# W = 60 s, set before the run: 1, 5, 6, 10 draws finish (P(exactly D) 0.28-0.87 per pass); 60 runs
# out of heap (step 1, the original 2026-10-16 failure). Same rule as run 1. Added: the earliest arrival
# among DI's options vs TTM at the same 1-min window (the 2026-10-16 planned test), in whole minutes
# from the window start; rule: agree within ARRIVAL_TOLERANCE_MIN.
NARROW_WINDOW_MIN = 1                          # config.TRANSIT_VALIDATION_WINDOW_MIN
NARROW_CASES = [(1, "finished"), (5, "finished"), (6, "finished"), (10, "finished"), (60, "heap error")]
NARROW_TAG = "1min"                            # saved data of run 2
ARRIVAL_TOLERANCE_MIN = 1
TTM_PERCENTILE = 49                            # any one but 50 (r5py renames a lone p50); 1 min gives one value
CASE_TIME_LIMIT_S = 300                        # network load (cached, ~1 min) plus routing
SIMULATION_PASSES = 20000
SIMULATION_SEED = 20261017
HEAP_ERROR_TEXT = "OutOfMemoryError"
RESULT_PREFIX = "RESULT "


def simulate_sampler(window_s, draws, rng):
    """Share of the sampler's passes that hold exactly `draws` times (R5's acceptance test)."""
    step = window_s // draws
    half = step // 2
    if step <= 1:
        return 0.0
    hits = 0
    for _ in range(SIMULATION_PASSES):
        departure_s, count = rng.integers(step), 0
        while departure_s < window_s and count <= draws:
            count += 1
            departure_s += rng.integers(step) + half
        hits += count == draws
    return hits / SIMULATION_PASSES


def option_arrival(option_df, departure):
    """An option's arrival by TRN-6's formula: last ride departure + ride + the legs after it (r5py's walk
    legs carry cached times, so their clock times aren't used); walk only: departure + walk time."""
    is_ride = option_df.route_id.notna() & (option_df.route_id != "")
    if not is_ride.any():
        return departure + option_df.travel_time.sum()
    last_ride = option_df[is_ride].iloc[-1]
    after_df = option_df[option_df.segment > last_ride.segment]
    return last_ride.departure_time + last_ride.travel_time + after_df.travel_time.sum()


def run_case(window_min, draws):
    """Child process: DI's per-pair routing for one window and draw count, plus TTM at that window;
    prints one RESULT line."""
    sys.argv += ["--max-memory", R5_MAX_MEMORY]                         # r5py reads its JVM settings at import
    import geopandas as gpd
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    from r5py.r5.regional_task import RegionalTask
    from r5py.r5.trip_planner import TripPlanner

    pair = pd.read_csv(PAIRS_PATH).set_index("draw_no").loc[PAIR_DRAW_NO]
    departure = datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(
        minutes=int(pair.dep_min_of_day))
    network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
    origin = gpd.points_from_xy([pair.origin_lon], [pair.origin_lat], crs="EPSG:4326")[0]
    destination = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326",
                                   geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
    request = RegionalTask(network, origin=origin, destinations=destination, departure=departure,
                           departure_time_window=datetime.timedelta(minutes=window_min),
                           transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
                           max_time=datetime.timedelta(minutes=MAX_TIME_MIN))
    request._regional_task.toLat, request._regional_task.toLon = pair.dest_lat, pair.dest_lon
    request._regional_task.monteCarloDraws = draws
    print(f"network ready, routing {draws} draws", flush=True)

    started = time.perf_counter()
    trips = TripPlanner(network, request).trips
    seconds = time.perf_counter() - started
    rows = [[option] + segment for option, trip in enumerate(trips) for segment in trip.as_table()]
    legs_df = pd.DataFrame(rows, columns=["option", "segment", "transport_mode", "departure_time", "distance",
                                          "travel_time", "wait_time", "feed", "agency_id", "route_id",
                                          "start_stop_id", "end_stop_id", "geometry"])
    is_ride = legs_df.route_id.notna() & (legs_df.route_id != "")
    boardings = (legs_df[is_ride].assign(board=lambda df: df.route_id + "@" + df.departure_time.astype(str))
                 .groupby("option").board.agg("|".join))
    first_departures = legs_df[legs_df.segment == 0].departure_time
    arrivals = pd.Series([option_arrival(option_df, departure) for _, option_df in legs_df.groupby("option")])
    origin_gdf = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=[origin])
    ttm_df = pd.DataFrame(TravelTimeMatrix(
        network, origins=origin_gdf, destinations=destination, departure=departure,
        departure_time_window=datetime.timedelta(minutes=window_min), percentiles=[TTM_PERCENTILE],
        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=datetime.timedelta(minutes=MAX_TIME_MIN)))
    result = {"n_options": len(trips), "n_departure_seconds": int(first_departures.nunique()),
              "n_distinct_boardings": int(boardings.nunique()), "routing_s": round(seconds, 1),
              "first_departure_s": int((first_departures.min() - departure).total_seconds()),
              "last_departure_s": int((first_departures.max() - departure).total_seconds()),
              "di_earliest_arrival_min": (arrivals.min() - departure).total_seconds() // SECONDS_PER_MIN,
              "ttm_min": float(ttm_df[f"travel_time_p{TTM_PERCENTILE}"].iloc[0])}
    print(RESULT_PREFIX + json.dumps(result), flush=True)


def run_cases(window_min, cases):
    """Parent: each case in its own process under CASE_TIME_LIMIT_S; outcome from exit and output."""
    rows = []
    for draws, predicted in cases:
        started = time.perf_counter()
        try:
            child = subprocess.run([sys.executable, "-u", __file__, "--case", str(window_min), str(draws)], capture_output=True,
                                   text=True, timeout=CASE_TIME_LIMIT_S)
            output = child.stdout + child.stderr
            result_lines = [line for line in child.stdout.splitlines() if line.startswith(RESULT_PREFIX)]
            if result_lines:
                outcome, details = "finished", json.loads(result_lines[-1][len(RESULT_PREFIX):])
            else:
                outcome = "heap error" if HEAP_ERROR_TEXT in output else "failed"
                details = {"error_tail": output.strip().splitlines()[-1] if output.strip() else ""}
        except subprocess.TimeoutExpired:
            outcome, details = "timed out", {}
        row = {"window_min": window_min, "draws": draws, "step_s": window_min * SECONDS_PER_MIN // draws, "predicted": predicted,
               "outcome": outcome, "wall_s": round(time.perf_counter() - started), **details}
        print(f"  {row}", flush=True)
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_date = datetime.date.today().strftime("%Y%m%d")
    lines = []
    rng = np.random.default_rng(SIMULATION_SEED)
    for window_min, cases, tag in [(DI_WINDOW_MIN, CASES, ""), (NARROW_WINDOW_MIN, NARROW_CASES, NARROW_TAG)]:
        saved_cases = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_{tag}cases.csv".replace("__", "_")))
        saved_cases = [path for path in saved_cases if tag or NARROW_TAG not in path.name]
        if saved_cases:
            print(f"reusing saved table {saved_cases[-1].name}")
            cases_df = pd.read_csv(saved_cases[-1])
        else:
            cases_df = run_cases(window_min, cases)
            cases_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_{tag}{'_' if tag else ''}cases.csv", index=False)
        window_s = window_min * SECONDS_PER_MIN
        cases_df["p_exact_simulated"] = [simulate_sampler(window_s, draws, rng) for draws in cases_df.draws]
        is_confirmed = (cases_df.predicted == cases_df.outcome).all()
        lines += [f"{NAME} {run_date}: draw {PAIR_DRAW_NO}, {window_min}-min window, time limit {CASE_TIME_LIMIT_S} s",
                  f"VERDICT (outcomes): {'CONFIRMED' if is_confirmed else 'NOT CONFIRMED'}"]
        if "ttm_min" in cases_df:
            is_finished = cases_df.outcome == "finished"
            gap = (cases_df.di_earliest_arrival_min - cases_df.ttm_min).abs()[is_finished]
            lines.append(f"VERDICT (DI earliest arrival vs TTM, within {ARRIVAL_TOLERANCE_MIN} min): "
                         f"{'AGREE' if (gap <= ARRIVAL_TOLERANCE_MIN).all() else 'DISAGREE'} on {int(is_finished.sum())} cases")
        lines.append(cases_df.drop(columns=["window_min"], errors="ignore").to_string(index=False))
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    if "--case" in sys.argv:
        case_at = sys.argv.index("--case")
        run_case(int(sys.argv[case_at + 1]), int(sys.argv[case_at + 2]))
    else:
        main()
