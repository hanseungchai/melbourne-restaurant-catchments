"""Do R5's own DetailedItineraries results hold TravelTimeMatrix's trip before r5py collapses them?

Claims under test (concepts/transit.md T7 (e), TRN-6), following diagnostics/transit_di_window.py (run
2026-10-17: DI later than TTM by more than 1 min on 66 of 100 transit-winning pairs at 5 and 10 draws,
earlier by 1-2 min on 3):
  C1  the 66 failures come from r5py's collection step: r5py builds a dict keyed by departure second
      from R5's finalStatesByDepartureTime (r5py/r5/trip_planner.py L245-252), so only the last state of
      each departure's list survives. Rule (set before the run, 2026-10-17): CONFIRMED if, on every one
      of the 66, some state in R5's full lists arrives within ARRIVAL_TOLERANCE_MIN of TTM.
  C2  on the 3 pairs where DI beats TTM: if R5's own best arrival is also earlier than TTM's, the
      difference is inside R5 (DI's and TTM's routers differ: destination linking or transfer rules),
      not r5py's assembly of legs. Reported per pair, with the best state's egress seconds in R5 against
      r5py's egress leg for that stop (both come from the same street search: _transit_egress_times is
      built from _transit_egress_paths' travel_time).
Where the pipeline relies on it: TRN-6 validation would take per-route detail from DI.

Method: the 100 pairs sampled by transit_di_window.py (its saved sample), DI's router called exactly as
r5py 1.1.7's TripPlanner.transit_paths does (McRaptorSuboptimalPathProfileRouter with TripPlanner's
access and egress times, SuboptimalDominatingList(suboptimalMinutes)), 1-min window, DRAWS draws, but
every state of every departure is read. Arrival = the final (egress) state's time; times in whole
minutes from Google's minute, as TTM. R5's departure sampler is unseeded, so the sampled seconds differ
from transit_di_window.py's run; the survivor columns (last state per departure, r5py's rule) are
recomputed here from this run's own lists.

Conclusion (run 2026-10-17): C1 NOT CONFIRMED, though the collapse is the main cause. R5's full lists
(10-1,543 states per pair, mean 162) hold a trip within 1 min of TTM on 88 of 100 pairs (50 exact) and on
56 of the 66 R1 failures; r5py's survivors give mean +2.67 (33 within 1 min), as transit_di_window.py's
DI did. Not found on 10 failures: 9 later than TTM by 2-3 min (2019, 5195, 11311, 12089, 14135, 14562,
21260, 24145, 25455; 4 of them single-ride with the 1-ride TTM time equal to TTM's), 1 earlier by 2
(12947). C2: R5's own best is earlier than TTM on 10 pairs (by 1 on 7, 2 on 3: 12947, 5979, 1635), on
the 3 earlier pairs included; the best state's egress seconds equal r5py's egress leg on 100 of 100, so
the earlier arrivals arise inside R5 (DI's router vs TTM's), not in r5py's assembly of legs. Causes of
the 9 late and the earlier arrivals not tested.

Run 2 (`--near-miss`, added 2026-10-17; a small-scale exploratory test: 9 pairs for C3, 100 for C4):
  C3  near-miss: on the pairs where R5's own best is later than TTM by more than ARRIVAL_TOLERANCE_MIN
      (the 9 above), DI's sampled departures fall after t:00 and miss a vehicle TTM, routing from t:00
      exactly, just catches. TTM at a 1-min window departing at t + 1 min. Rule (set before the run,
      2026-10-17): CONFIRMED on a pair if (a) TTM(t+1) + 1 is later than TTM(t) and (b) it is within
      ARRIVAL_TOLERANCE_MIN of R5's raw best (run 1's table); the hypothesis explains the 9 only if
      confirmed on all 9. Reported alongside, same form, no verdict: DI's router rerun on the pair, and
      TTM departing at that rerun's earliest sampled second (r5py drops seconds from a departure, so
      the departure setter is wrapped to keep them); the lines of the rerun's best state (TTM has no
      path, so its lines are unknown).
  C4  descriptive, no rule: TTM and R5's raw DI best against Google's earliest arrival (in-scope and
      name-mismatch routes, TRN-11; walk-only included; whole minutes from the requested minute) on the 100 and on the 10 pairs where
      R5's best beats TTM. Does Google confirm DI's earlier trips? Not a choice of fit target (T7 f).

Conclusion run 2 (2026-10-17): C3 NOT CONFIRMED (1 of 9, draw 24145): TTM at t + 1 arrives as TTM at t on
8 of 9, and TTM from DI's earliest sampled second (2 s on all 9) equals TTM(t) on 9 of 9, so the late
arrivals arise inside R5 (DI's router vs TTM's from the same start), not from DI's later start. On 14135
and 21260 DI's best rides the same lines as Google's earliest, which matches TTM, but later. C4 (100 of 100
with a Google answer once name-mismatch routes count; in-scope only gave 99, +0.71 / +1.10): TTM - Google
mean +0.67 (within 1 min on 53), DI raw - Google +1.06 (47); the -27 is draw 4140, where Google's only
earlier routes use a rail-replacement bus (out of scope). On the 10 pairs where DI beats TTM, DI equals
Google on 4 where TTM is 1 min late, but undercuts Google by 3-11 min on 3 (27407, 12947, 5979). DI's
earlier trips are not systematically confirmed; TTM is closer overall. No regional coach in any Google
answer of the 100. Where TTM is later than Google by >= 3 min (25 pairs), Google's earliest leaves within
150 s of the request on 80% (median 82 s), against 30% (median 231 s) where they agree within 1 min; TTM
often matches Google's next vehicle on the same line (22087, 25587). Lead, untested: TTM's walk to the
first stop is slower or longer than Google's, so it misses a vehicle Google just catches (walk speed, WLK-1).

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release), the
OSM extract in frozen_inputs/osm_extract/, the transit pair draw in outputs/transit_validation/, and
transit_di_window.py's saved sample and results in diagnostics/diagnostic_data/ (newest of each).
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls; r5py
only (a few minutes). The per-pair table is saved data: a rerun reuses the newest one and says so.
Results carry the run date; a same-day rerun replaces that day's results.
"""
import copy
import datetime
import sys
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
WINDOW_RESULTS_GLOB = "transit_di_window_*_results.csv"     # transit_di_window.py's per-pair results (sample, TTM, DI)
NAME = "transit_di_raw_states"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_di_window.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as transit_di_window.py
DRAWS = 10                                     # transit_di_window.py's largest draw count
ARRIVAL_TOLERANCE_MIN = 1
SECONDS_PER_MIN = 60
EGRESS_STOP = -1                               # R5 marks the final (egress) state with stop -1

# --- run 2 (near-miss and Google) ------------------------------------------------------------------
NEAR_MISS_FLAG = "--near-miss"
NEAR_MISS_OFFSET_MIN = 1                       # TTM departs at t + this
SINGLE_PERCENTILE = 49                         # as transit_di_window.py (r5py renames a lone p50)
GOOGLE_ROUTES_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv"
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]   # TRN-11: a name mismatch is the same line under another short name
LATE_GAP_MIN = 3                               # C4 breakdown: TTM later / earlier than Google by at least this
SHORT_LEAVE_WAIT_S = 150                       # C4 breakdown: Google says leave within this of the request
MIN_PER_HOUR = 60
LOCAL_TIMEZONE = "Australia/Melbourne"

IS_NEAR_MISS_RUN = NEAR_MISS_FLAG in sys.argv
if IS_NEAR_MISS_RUN:
    sys.argv.remove(NEAR_MISS_FLAG)            # r5py parses sys.argv
sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import

import geopandas as gpd  # noqa: E402
from r5py import TransportMode, TransportNetwork, TravelTimeMatrix  # noqa: E402
from r5py.r5.regional_task import RegionalTask  # noqa: E402
from r5py.r5.trip_planner import TripPlanner  # noqa: E402
import com.conveyal.r5  # noqa: E402  (importable once r5py has started the JVM)


def departure_of(pair):
    """The pair's drawn minute on WINDOW_DATE."""
    return datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))


def state_rides(state):
    """Rides on a final state's chain (r5py's leg rule: not egress, not access, not a transfer)."""
    rides = 0
    while state:
        if state.stop != EGRESS_STOP and state.back is not None and state.pattern != -1:
            rides += 1
        state = state.back
    return rides


def raw_states(network, pair):
    """Every final state of DI's router for one pair: departure second, arrival second, rides, and the
    position in its departure's list; plus the TripPlanner (for its egress legs)."""
    departure = departure_of(pair)
    origin = gpd.points_from_xy([pair.origin_lon], [pair.origin_lat], crs="EPSG:4326")[0]
    destination = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326",
                                   geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
    request = RegionalTask(network, origin=origin, destinations=destination, departure=departure,
                           departure_time_window=datetime.timedelta(minutes=WINDOW_MIN),
                           transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
                           max_time=datetime.timedelta(minutes=MAX_TIME_MIN))
    request._regional_task.toLat, request._regional_task.toLon = pair.dest_lat, pair.dest_lon
    request._regional_task.monteCarloDraws = DRAWS
    planner = TripPlanner(network, request)

    # as r5py 1.1.7 TripPlanner.transit_paths (trip_planner.py L198-241)
    router_request = copy.copy(planner.request)
    suboptimal_minutes = max(router_request._regional_task.suboptimalMinutes, 0)

    def list_supplier_callback(departure_time):
        return com.conveyal.r5.profile.SuboptimalDominatingList(suboptimal_minutes)

    router = com.conveyal.r5.profile.McRaptorSuboptimalPathProfileRouter(
        network, router_request, planner._transit_access_times, planner._transit_egress_times,
        list_supplier_callback, None, True)
    router.route()
    rows = []
    for departure_s, states in zip(router.finalStatesByDepartureTime.keys(), router.finalStatesByDepartureTime.values()):
        states = list(states)
        for position, state in enumerate(states):
            rows.append({"departure_s": int(departure_s), "arrival_s": int(state.time), "rides": state_rides(state),
                         "is_survivor": position == len(states) - 1, "egress_stop": int(state.back.stop),
                         "egress_r5_s": int(state.time - state.back.time), "lines": state_lines(network, state)})
    return pd.DataFrame(rows), planner, departure


def check_one_pair(network, pair, t1_min):
    """R5's best arrival over all states and over r5py's survivors, against TTM, for one pair."""
    states_df, planner, departure = raw_states(network, pair)
    start_s = (departure - departure.replace(hour=0, minute=0)).total_seconds()
    row = {"draw_no": pair.Index, "t1_min": t1_min, "n_departures": states_df.departure_s.nunique(),
           "n_states": len(states_df)}
    if states_df.empty:
        return row
    states_df["arrival_min"] = (states_df.arrival_s - start_s) // SECONDS_PER_MIN
    best = states_df.loc[states_df.arrival_s.idxmin()]
    survivors_df = states_df[states_df.is_survivor]
    survivor_best = survivors_df.loc[survivors_df.arrival_s.idxmin()]
    egress_legs = [paths[int(best.egress_stop)] for paths in planner._transit_egress_paths.values()
                   if int(best.egress_stop) in paths]
    row.update({"raw_best_min": best.arrival_min, "raw_best_rides": int(best.rides),
                "survivor_best_min": survivor_best.arrival_min, "survivor_best_rides": int(survivor_best.rides),
                "n_states_within_tol": int(((states_df.arrival_min - t1_min).abs() <= ARRIVAL_TOLERANCE_MIN).sum()),
                "best_egress_r5_s": int(best.egress_r5_s),
                "best_egress_leg_s": round(min(leg.travel_time for leg in egress_legs).total_seconds()) if egress_legs else np.nan})
    print(f"  {row}", flush=True)
    return row


def main():
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_date = datetime.date.today().strftime("%Y%m%d")
    window_path = sorted(DIAGNOSTIC_DATA_DIR.glob(WINDOW_RESULTS_GLOB))[-1]
    window_df = pd.read_csv(window_path).set_index("draw_no")
    print(f"sample and TTM times from {window_path.name}")
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_pairs.csv"))
    if saved:
        print(f"reusing saved table {saved[-1].name}")
        checks_df = pd.read_csv(saved[-1])
    else:
        network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        pairs_df = pd.read_csv(PAIRS_PATH).set_index("draw_no").loc[window_df.index]
        checks_df = pd.DataFrame([check_one_pair(network, pair, window_df.at[pair.Index, "t1_min"])
                                  for pair in pairs_df.itertuples()])
        checks_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_pairs.csv", index=False)

    checks_df = checks_df.merge(window_df[["di_min_d10"]].reset_index(), on="draw_no")
    previous_gap = checks_df.di_min_d10 - checks_df.t1_min
    is_r1_failure = previous_gap.isna() | (previous_gap.abs() > ARRIVAL_TOLERANCE_MIN)
    is_earlier = previous_gap < 0
    raw_gap = checks_df.raw_best_min - checks_df.t1_min
    survivor_gap = checks_df.survivor_best_min - checks_df.t1_min
    is_found = raw_gap.abs() <= ARRIVAL_TOLERANCE_MIN
    lines = [f"{NAME} {run_date}: {len(checks_df)} pairs from {window_path.name}; {WINDOW_MIN}-min window, "
             f"{DRAWS} draws, tolerance {ARRIVAL_TOLERANCE_MIN} min; whole minutes from Google's minute",
             f"states per pair: mean {checks_df.n_states.mean():.1f}, range {checks_df.n_states.min()} / "
             f"{checks_df.n_states.max()}; departures per pair mean {checks_df.n_departures.mean():.1f}"]
    for label, gap in [("R5 best over all states - TTM", raw_gap), ("R5 best over survivors - TTM", survivor_gap)]:
        lines.append(f"{label}: mean {gap.mean():.2f}, range {gap.min()} / {gap.max()}, exact {int((gap == 0).sum())}, "
                     f"within tol {int((gap.abs() <= ARRIVAL_TOLERANCE_MIN).sum())} of {int(gap.notna().sum())}; "
                     f"distribution {gap.value_counts().sort_index().to_dict()}")
    lines.append(f"VERDICT C1: {'CONFIRMED' if is_found[is_r1_failure].all() else 'NOT CONFIRMED'} "
                 f"(R5's lists hold a trip within tol on {int(is_found[is_r1_failure].sum())} of "
                 f"{int(is_r1_failure.sum())} R1 failures; not on {checks_df.draw_no[is_r1_failure & ~is_found].tolist()})")
    is_egress_equal = checks_df.best_egress_r5_s == checks_df.best_egress_leg_s
    lines.append(f"best state's egress seconds, R5 = r5py leg on {int(is_egress_equal.sum())} of {len(checks_df)}; "
                 f"R5 - leg mean {(checks_df.best_egress_r5_s - checks_df.best_egress_leg_s).mean():.1f} s")
    lines.append("C2, pairs where transit_di_window.py's DI beat TTM:")
    lines.append(checks_df[is_earlier].to_string(index=False))
    lines.append(checks_df.to_string(index=False))
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary)


def keep_departure_seconds():
    """Wrap RegionalTask's departure setter so R5's fromTime keeps the departure's seconds (r5py 1.1.7
    sets fromTime from hours and minutes only); toTime moves with it."""
    setter = RegionalTask.departure.fset

    def setter_with_seconds(self, departure):
        setter(self, departure)
        self._regional_task.fromTime += departure.second
        self._regional_task.toTime += departure.second

    RegionalTask.departure = RegionalTask.departure.setter(setter_with_seconds)


def ttm_min(network, pair, departure):
    """TTM travel time (whole minutes) for one pair at a 1-min window from `departure`."""
    origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.origin_lon], [pair.origin_lat]))
    destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
    matrix_df = pd.DataFrame(TravelTimeMatrix(
        network, origins=origins, destinations=destinations, departure=departure,
        departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=datetime.timedelta(minutes=MAX_TIME_MIN)))
    return matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]


def state_lines(network, state):
    """Route short names (or ids) of a final state's rides, first ride first."""
    lines = []
    while state:
        if state.stop != EGRESS_STOP and state.back is not None and state.pattern != -1:
            pattern = network._transport_network.transitLayer.tripPatterns.get(state.pattern)
            route = network._transport_network.transitLayer.routes.get(pattern.routeIndex)
            lines.append(str(route.route_short_name or pattern.routeId))
        state = state.back
    return "+".join(reversed(lines))


def near_miss_one_pair(network, pair, t1_min):
    """C3 for one pair: TTM at t + 1, DI's router rerun, TTM at the rerun's earliest sampled second."""
    departure = departure_of(pair)
    start_s = (departure - departure.replace(hour=0, minute=0)).total_seconds()
    offset = datetime.timedelta(minutes=NEAR_MISS_OFFSET_MIN)
    row = {"draw_no": pair.Index, "t1_min": t1_min,
           "ttm_plus1_arrival_min": ttm_min(network, pair, departure + offset) + NEAR_MISS_OFFSET_MIN}

    states_df, planner, _ = raw_states(network, pair)
    first_s = int(states_df.departure_s.min() - start_s)
    best = states_df.loc[states_df.arrival_s.idxmin()]
    row.update({"rerun_best_min": (best.arrival_s - start_s) // SECONDS_PER_MIN, "rerun_first_s": first_s,
                "rerun_best_departure_s": int(best.departure_s - start_s),
                "ttm_first_s_arrival_min": (ttm_min(network, pair, departure + datetime.timedelta(seconds=first_s))
                                            + first_s / SECONDS_PER_MIN) // 1,
                "rerun_best_lines": best.lines})
    print(f"  {row}", flush=True)
    return row


def near_miss_main():
    """Run 2: C3 on the late pairs (saved table reused if present), then C4 against Google."""
    run_date = datetime.date.today().strftime("%Y%m%d")
    window_path = sorted(DIAGNOSTIC_DATA_DIR.glob(WINDOW_RESULTS_GLOB))[-1]
    window_df = pd.read_csv(window_path).set_index("draw_no")
    run1_path = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_pairs.csv"))[-1]
    run1_df = pd.read_csv(run1_path)
    print(f"sample and TTM times from {window_path.name}; R5 raw best from {run1_path.name}")
    run1_df["raw_gap"] = run1_df.raw_best_min - run1_df.t1_min
    late_draws = run1_df.draw_no[run1_df.raw_gap > ARRIVAL_TOLERANCE_MIN].tolist()

    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_near_miss.csv"))
    if saved:
        print(f"reusing saved table {saved[-1].name}")
        near_df = pd.read_csv(saved[-1])
    else:
        keep_departure_seconds()
        network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        pairs_df = pd.read_csv(PAIRS_PATH).set_index("draw_no").loc[late_draws]
        near_df = pd.DataFrame([near_miss_one_pair(network, pair, window_df.at[pair.Index, "t1_min"])
                                for pair in pairs_df.itertuples()])
        near_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_near_miss.csv", index=False)

    near_df = near_df.merge(run1_df[["draw_no", "raw_best_min"]], on="draw_no")
    is_later = near_df.ttm_plus1_arrival_min > near_df.t1_min
    is_near_raw = (near_df.ttm_plus1_arrival_min - near_df.raw_best_min).abs() <= ARRIVAL_TOLERANCE_MIN
    near_df["c3_confirmed"] = is_later & is_near_raw
    is_first_later = near_df.ttm_first_s_arrival_min > near_df.t1_min
    is_first_near = (near_df.ttm_first_s_arrival_min - near_df.rerun_best_min).abs() <= ARRIVAL_TOLERANCE_MIN
    near_df["first_s_same_form"] = is_first_later & is_first_near

    google_df = google_earliest_df()
    near_df = near_df.merge(google_df[["draw_no", "google_min", "google_lines"]], on="draw_no", how="left")
    lines = [f"{NAME} run 2 (near-miss, Google) {run_date}: small-scale exploratory test; "
             f"{len(near_df)} late pairs for C3, {len(run1_df)} for C4; tolerance {ARRIVAL_TOLERANCE_MIN} min",
             f"VERDICT C3: {'CONFIRMED' if near_df.c3_confirmed.all() else 'NOT CONFIRMED'} "
             f"(on {int(near_df.c3_confirmed.sum())} of {len(near_df)}: (a) later than TTM(t) on {int(is_later.sum())}, "
             f"(b) within tol of R5 raw best on {int(is_near_raw.sum())})",
             f"reported, same form at DI's earliest sampled second: {int(near_df.first_s_same_form.sum())} of {len(near_df)}; "
             f"earliest sampled second per pair {near_df.rerun_first_s.tolist()}",
             near_df.to_string(index=False)]

    c4_df = run1_df[["draw_no", "t1_min", "raw_best_min", "raw_gap"]].merge(
        google_df, on="draw_no", how="left").merge(
        pd.read_csv(PAIRS_PATH)[["draw_no", "dep_min_of_day"]], on="draw_no")
    is_minute_match = c4_df.requested_min_of_day == c4_df.dep_min_of_day
    lines.append(f"C4: Google earliest in-scope or name-mismatch arrival found on {int(c4_df.google_min.notna().sum())} of {len(c4_df)}; "
                 f"requested minute = drawn minute on {int(is_minute_match.sum())}")
    c4_df["ttm_minus_google"] = c4_df.t1_min - c4_df.google_min
    c4_df["di_raw_minus_google"] = c4_df.raw_best_min - c4_df.google_min
    for label, subset_df in [("all", c4_df), ("R5 best earlier than TTM", c4_df[c4_df.raw_gap < 0])]:
        for column in ["ttm_minus_google", "di_raw_minus_google"]:
            gap = subset_df[column]
            lines.append(f"  {label} (n={len(subset_df)}), {column}: mean {gap.mean():.2f}, median {gap.median():.1f}, "
                         f"range {gap.min()} / {gap.max()}, within tol {int((gap.abs() <= ARRIVAL_TOLERANCE_MIN).sum())}; "
                         f"distribution {gap.value_counts().sort_index().to_dict()}")
    ttm_gap = c4_df.ttm_minus_google
    for label, is_group in [(f"TTM later by >= {LATE_GAP_MIN}", ttm_gap >= LATE_GAP_MIN),
                            (f"within {ARRIVAL_TOLERANCE_MIN}", ttm_gap.abs() <= ARRIVAL_TOLERANCE_MIN),
                            (f"TTM earlier by >= {LATE_GAP_MIN}", ttm_gap <= -LATE_GAP_MIN)]:
        group_df = c4_df[is_group]
        lines.append(f"  {label} (n={len(group_df)}): Google's earliest leaves within {SHORT_LEAVE_WAIT_S} s on "
                     f"{(group_df.google_leave_wait_s <= SHORT_LEAVE_WAIT_S).mean():.2f}; leave wait median "
                     f"{group_df.google_leave_wait_s.median():.0f} s; walk median {group_df.google_walk_m.median():.0f} m")
    lines.append(f"C4, pairs with TTM later than Google by >= {LATE_GAP_MIN} (walk-speed test set):")
    lines.append(c4_df[ttm_gap >= LATE_GAP_MIN].drop(columns=["requested_min_of_day", "dep_min_of_day"]).to_string(index=False))
    lines.append("C4, pairs where R5's best beats TTM:")
    lines.append(c4_df[c4_df.raw_gap < 0].drop(columns=["requested_min_of_day", "dep_min_of_day"]).to_string(index=False))
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_near_miss_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary)


def google_earliest_df():
    """Google's earliest in-scope arrival per pair, whole minutes from the requested minute, and its lines;
    the requested minute is checked against the pair's drawn minute."""
    routes_df = pd.read_csv(GOOGLE_ROUTES_PATH)
    routes_df = routes_df[routes_df.route_scope.isin(GOOGLE_SCOPES)]
    earliest_df = routes_df.loc[routes_df.groupby("draw_no").arrival_from_request_s.idxmin()]
    requested = pd.to_datetime(earliest_df.requested_utc, utc=True).dt.tz_convert(LOCAL_TIMEZONE)
    return pd.DataFrame({"draw_no": earliest_df.draw_no.values,
                         "google_min": (earliest_df.arrival_from_request_s // SECONDS_PER_MIN).values,
                         "google_lines": earliest_df.lines.values,
                         "google_leave_wait_s": earliest_df.leave_wait_s.values, "google_walk_m": earliest_df.walk_m.values,
                         "requested_min_of_day": (requested.dt.hour * MIN_PER_HOUR + requested.dt.minute).values})


if __name__ == "__main__":
    if IS_NEAR_MISS_RUN:
        near_miss_main()
    else:
        main()
