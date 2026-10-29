"""Is the DI-TTM gap inside R5 the egress walk? And do TTM's late pairs hinge on walk distance or R5's board slack?

Claims under test (concepts/transit.md T7 (e), TRN-6; concepts/walk.md WLK-1), following
diagnostics/transit_di_raw_states.py (R5's full DetailedItineraries (DI) lists differ from TravelTimeMatrix
(TTM) by more than 1 min, or are earlier, on 19 of 100 pairs; near-miss refuted) and
diagnostics/transit_walk_speed_lead.py (PARTIAL at 4.2 km/h; 5 pairs close only at 5.0).

Read from the r5-v7.5.1-r5py jar (javap, 2026-10-17, autonomous session): both routers board only if the
vehicle departs more than 60 s after arrival at the stop (FastRaptorWorker.MINIMUM_BOARD_WAIT_SEC,
McRaptorSuboptimalPathProfileRouter.BOARD_SLACK); both build street transfers the same way (TTM's extra
gtfsTransfers table is empty on this network: checked in a scratch run). They differ at the ends: DI takes
r5py TripPlanner's egress times (a StreetRouter search from the destination, r5py trip_planner.py
L469-530), TTM propagates from stops to the destination through the destination's LinkedPointSet and
its EgressCostTable (PerTargetPropagater; off-street link at 1.3 m/s). A scratch run on 4 of the 19
(14135, 2019, 12947, 5979) showed the same lines, stops and boardings in TTM's path and DI's best state,
with the gap equal to the egress difference.

  C1  the DI-TTM gap is the egress walk. Method: TTM rerun with includePathResults (TTM's own path); DI's
      router run as in transit_di_raw_states.py (1-min window, DRAWS draws, all states read) twice: with
      TripPlanner's egress times (as r5py) and with TTM's egress times for the destination (its
      EgressCostTable read after the TTM run). Rule (Claude's rule, not user-approved; set before the run,
      2026-10-17): CONFIRMED if, with TTM's egress, DI's best arrival is within ARRIVAL_TOLERANCE_MIN of
      TTM on all 9 late pairs, no longer earlier than TTM (gap >= 0) on at least MIN_EARLIER_FIXED of the 10
      earlier pairs, and within ARRIVAL_TOLERANCE_MIN on all CONTROL_COUNT controls (pairs where DI's raw
      best equals TTM). Reported: per pair, TTM's lines, alight stop and egress seconds; DI's best state's
      lines, alight stop and egress seconds; TripPlanner's egress seconds for TTM's alight stop; Google's
      last walk (distance) where Google's last alight stop is within STOP_MATCH_M of TTM's.
  C2  descriptive, the 25 TTM-late pairs of transit_walk_speed_lead.py (no verdict on the 25): R5's
      walk to Google's first boarding stop (TripPlanner access seconds at 3.6 km/h, R5 stop within
      STOP_MATCH_M of Google's) against Google's first walk. Per pair, at PRIMARY_SPEED_KMH: does R5 miss
      Google's first vehicle only because of the 60 s slack (R5's walk alone is in time), because of
      distance (R5's walk is more than DISTANCE_RATIO_LONG times Google's and alone is too slow), or not at
      all? Rule for the 5 pairs that close only at 5.0 km/h (Claude's rule, not user-approved; set before the
      run): "slack, not distance" if, on at least 4 of the 5, R5's walk is within DISTANCE_RATIO_LONG of
      Google's and the miss at 4.2 is the slack.
  C3  descriptive, no rule (run 2, `--mechanism`): why the two egress times differ, on C1's 29 pairs at TTM's
      alight stop. Read: the destination's split as r5py's egress StreetRouter makes it
      (StreetLayer.findSplit, WALK) and as TTM's LinkedPointSet stores it (edge, off-street and along-edge
      distances); r5py's reverse StreetRouter state at the stop's vertex (duration s, distance mm); TTM's
      cost-table entry (mm). From the jar: TTM's walk egress table is a distance search from each stop
      capped at 2,000 m, divided by the walk speed; r5py's is a time search from the destination capped
      at 1 h.
  C4  run 3 (`--edges`), the C3 lead: the path-length gap is search direction on asymmetric walk edges.
      Per pair at TTM's alight stop: the destination edge pair's ALLOWS_PEDESTRIAN and
      NO_THRU_TRAFFIC_PEDESTRIAN flags (forward, back); r5py's reverse search from the destination
      (as run 2) with its path's edges counted by flag; the same search with reverseSearch off; a forward
      search from the stop's vertex read at the destination split (StreetRouter.getState(Split)). Rule
      (Claude's rule, not user-approved; set before the run, 2026-10-17): "direction" SUPPORTED if, on every
      pair where |r5py - TTM| > PATH_GAP_M, either the destination edge allows walking in one direction
      only, or r5py's reverse and forward-from-destination distances differ (reverseSearch changes the
      path); otherwise NOT SUPPORTED. Reported: forward-from-stop distance against TTM's cost, and
      no-through-traffic edges on r5py's path.
Where the pipeline relies on it: TRN-6 (TTM as the validation router; DI's role), WLK-1 (the speed fit).

Conclusion (run 2026-10-17, autonomous session; verdicts are Claude's rules, not user-approved):
C1 CONFIRMED. Sanity: TTM with path results = t1_min on 29 of 29; DI with r5py's egress = run 1's raw best
on 29 of 29. With TTM's egress times in DI's router, DI = TTM exactly (gap 0) on all 29: 9 late (were +2/+3),
10 earlier (were -1/-2), 10 controls. DI and TTM ride the same lines on 28 of 29 (11185: 59+Sandringham vs
Lilydale+Sandringham, same arrival once egress is swapped). The whole DI-TTM gap is the egress walk:
r5py's egress minus TTM's at TTM's alight stop is +80 to +198 s on the late pairs, -15 to -146 s on the
earlier, -39 to +37 s on the controls. TTM's egress is closer to Google's last walk: on the 17 pairs where
Google alights within 60 m of TTM's stop, |TTM - Google| median 28 m against 64 m for r5py's.
C2 (descriptive): R5's walk to Google's first boarding stop is a median 1.14 times Google's first walk
(> 1.10 on 13 of 25). At 4.2 km/h Google's first vehicle is missed only through R5's 60 s board slack on 12
of 25, by distance on 3; caught on 10 (those stay late for later reasons). Five pairs: rule NOT met ("slack,
not distance" on 1 of 5): all 5 miss at 4.2 only through the slack, but R5's walk is longer than Google's by
more than 10% on 4 (18359 1.19, 25486 1.15, 22087 1.29, 25455 1.51); 25587 (1.04) is slack alone. So the
residual late gap at 4.2 is slack plus R5's longer access walk, not speed.
C3 (run 2, descriptive): same street edge and identical split distances in both linkings on 29 of 29; r5py's
egress state duration = its egress leg on 29 of 29; the seconds gap equals the metres gap (corr 1.00). The
two egress searches find street paths of different length from the same split, often leaving the edge by
opposite ends (14135: TTM 28 m via the 8 m end, r5py 185 m via the 165 m end; 12947 the reverse). Lead,
untested: direction-dependent edge traversal (TTM searches forward from each stop; r5py searches in
reverse from the destination with reverseSearch set on the shared Java task, trip_planner.py L472).
C4 (run 3) SUPPORTED, 24 of 24 pairs with |r5py - TTM| > 20 m: no destination edge is one-way for walking
and no r5py path uses a no-through-traffic edge; the cause is reverseSearch itself. The same search from the
destination with reverseSearch off gives TTM's distance to the millimetre on 27 of 29 (27459, 3877 within
5 m), and a forward distance search from the stop is within 20 m of TTM's cost on 26 of 29. Mechanism, read
from the jar's bytecode (StreetRouter.setOrigin(double, double)) and checked on the run-2 table: the two
start states are costed distance0 (at vertex0) and distance1 (at vertex1); when reverseSearch is set, their
vertices are swapped but their costs are not, so each end of the destination's edge carries the other
end's along-edge distance. r5py - TTM = +-(distance0 - distance1) within 1 m on 26 of 29, and is bounded by
|distance0 - distance1| on 28 (where the other end becomes the shorter way out). So DI's egress walk is
off by up to the destination edge's length difference between its two ends; TTM is unaffected (its egress
tables search forward from stops), as is r5py's access (forward search). Applies to r5py 1.1.7 with R5
v7.5.1 wherever r5py's TripPlanner egress is used (DetailedItineraries).
Not run: GTFS transfers as a cause (the gtfsTransfers table is empty on this network, scratch check).

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release), the
OSM extract in frozen_inputs/osm_extract/, the transit pair draw and the Google raw answers and route table
in outputs/transit_validation/, and in diagnostics/diagnostic_data/ (newest of each): transit_di_window.py's
results (t1_min), transit_di_raw_states.py's per-pair table (raw_gap), transit_walk_speed_lead.py's table.
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls; r5py
only. The per-pair tables are saved data: a rerun reuses the newest and says so. Results carry the run
date; a same-day rerun replaces that day's results.
"""
import copy
import datetime
import json
import math
import sys
from pathlib import Path

import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
GTFS_CLEANED_DIR = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
GOOGLE_ROUTES_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv"
GOOGLE_RAW_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
WINDOW_RESULTS_GLOB = "transit_di_window_*_results.csv"        # t1_min (TTM at the drawn minute)
RAW_STATES_GLOB = "transit_di_raw_states_*_pairs.csv"          # raw_best_min (R5's full DI lists)
WALK_SPEED_GLOB = "transit_walk_speed_lead_*_pairs.csv"        # TTM at 3.6 / 4.2 / 5.0 km/h
NAME = "transit_router_egress"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_di_window.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as transit_di_window.py
DRAWS = 10                                     # as transit_di_raw_states.py
SINGLE_PERCENTILE = 49                         # as transit_di_window.py (r5py renames a lone p50)
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]   # TRN-11
SECONDS_PER_MIN = 60
EGRESS_STOP = -1                               # R5 marks the final (egress) state with stop -1
FIXED_DEGREES = 1e7                            # R5's fixed-point coordinates
EARTH_RADIUS_M = 6_371_000
MM_PER_M = 1000
KMH_PER_MS = 3.6

# --- test ------------------------------------------------------------------------------------------
ARRIVAL_TOLERANCE_MIN = 1
LATE_GAP_MIN = 3                               # C2 set: TTM later than Google by at least this (walk-speed test set)
CONTROL_COUNT = 10                             # C1 controls: the first pairs by draw_no with raw DI best = TTM
MIN_EARLIER_FIXED = 8                          # of the 10 earlier pairs
STOP_MATCH_M = 60                              # R5 stop counts as Google's stop within this distance
DISTANCE_RATIO_LONG = 1.10                     # R5's walk counts as longer than Google's above this ratio
BOARD_SLACK_S = 60                             # both routers (docstring)
BASELINE_SPEED_KMH = 3.6                       # r5py's default (the speed of the run)
PRIMARY_SPEED_KMH = 4.2                        # Google's measured walk speed (WLK-1 lead)
CLOSE_ONLY_AT_5 = [25587, 25486, 22087, 25455, 18359]   # transit_walk_speed_lead.py conclusion

MECHANISM_FLAG = "--mechanism"
SPLIT_RADIUS_M = 1600                          # as r5py's StreetRouter.setOrigin (jar: ldc 1600.0)
IS_MECHANISM_RUN = MECHANISM_FLAG in sys.argv
if IS_MECHANISM_RUN:
    sys.argv.remove(MECHANISM_FLAG)            # r5py parses sys.argv
EDGES_FLAG = "--edges"
PATH_GAP_M = 20                                # run 3: pairs whose egress paths differ by more than this
DISTANCE_LIMIT_M = 2000                        # run 3 forward search from the stop (as TTM's walk egress table, jar)
IS_EDGES_RUN = EDGES_FLAG in sys.argv
if IS_EDGES_RUN:
    sys.argv.remove(EDGES_FLAG)
sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import

import geopandas as gpd  # noqa: E402
from r5py import TransportMode, TransportNetwork  # noqa: E402
from r5py.r5.regional_task import RegionalTask  # noqa: E402
from r5py.r5.trip_planner import TripPlanner  # noqa: E402
import jpype  # noqa: E402
import com.conveyal.r5  # noqa: E402  (importable once r5py has started the JVM)
import gnu.trove.map.hash  # noqa: E402


def departure_of(pair):
    """The pair's drawn minute on WINDOW_DATE."""
    return datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))


def build_request(network, pair):
    """r5py's RegionalTask for one pair, as transit_di_raw_states.py (destination also set for DI)."""
    origin = gpd.points_from_xy([pair.origin_lon], [pair.origin_lat], crs="EPSG:4326")[0]
    destination = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326",
                                   geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
    request = RegionalTask(network, origin=origin, destinations=destination, departure=departure_of(pair),
                           departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
                           transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
                           max_time=datetime.timedelta(minutes=MAX_TIME_MIN))
    request._regional_task.toLat, request._regional_task.toLon = pair.dest_lat, pair.dest_lon
    request._regional_task.monteCarloDraws = DRAWS
    return request


def distance_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def stop_lat_lon(transit_layer, stop):
    coordinate = transit_layer.getCoordinateForStopFixed(stop)
    return coordinate.y / FIXED_DEGREES, coordinate.x / FIXED_DEGREES


def nearest_stop(transit_layer, stop_coords, lat, lon):
    """R5 stop index nearest a point and its distance (m)."""
    best = min(range(len(stop_coords)), key=lambda i: (stop_coords[i][0] - lat) ** 2 + (stop_coords[i][1] - lon) ** 2)
    return best, distance_m(lat, lon, *stop_coords[best])


def route_name(transit_layer, pattern_index):
    pattern = transit_layer.tripPatterns.get(pattern_index)
    route = transit_layer.routes.get(pattern.routeIndex)
    return str(route.route_short_name or pattern.routeId)


def ttm_with_path(network, request):
    """TTM minutes, its path (lines, board and alight stops, access and egress seconds), and TTM's egress
    seconds to the destination from every stop (its EgressCostTable, transposed after the run)."""
    ttm_request = copy.copy(request)
    ttm_request._regional_task.includePathResults = True
    result = com.conveyal.r5.analyst.TravelTimeComputer(ttm_request, network).computeTravelTimes()
    ttm_min = int(result.travelTimes.getValues()[0][0])
    transit_layer = network._transport_network.transitLayer
    path = {"ttm_lines": "", "ttm_board_stop": -1, "ttm_alight_stop": -1, "ttm_access_s": None, "ttm_egress_s": None}
    templates = result.paths.iterationsForPathTemplates[0] if result.paths is not None else None
    if templates is not None and not templates.isEmpty():
        route_sequence = list(templates.keySet())[0]
        stops = route_sequence.stopSequence
        lines = [str(transit_layer.routes.get(route).route_short_name) for route in route_sequence.routes.toArray()]
        path = {"ttm_lines": "+".join(lines), "ttm_board_stop": int(stops.boardStops.get(0)),
                "ttm_alight_stop": int(stops.alightStops.get(stops.alightStops.size() - 1)),
                "ttm_access_s": int(stops.access.time) if stops.access is not None else None,
                "ttm_egress_s": int(stops.egress.time) if stops.egress is not None else None}
    point_set = ttm_request._regional_task.destinationPointSets[0]
    linkage = network._transport_network.linkageCache.getLinkage(
        point_set, network._transport_network.streetLayer, com.conveyal.r5.profile.StreetMode.WALK)
    table = linkage.getEgressCostTable()
    table.destructivelyTransposeForPropagationAsNeeded()
    is_distance = str(table.linkageCostUnit) == "DISTANCE_MILLIMETERS"
    walk_speed_mm_s = request._regional_task.walkSpeed * MM_PER_M
    cost_map = table.getCostTableForPoint(0)
    egress_s = {}
    if cost_map is not None:
        for stop, cost in zip(cost_map.keys(), cost_map.values()):
            egress_s[int(stop)] = int(cost / walk_speed_mm_s) if is_distance else int(cost)
    return ttm_min, path, egress_s, str(table.linkageCostUnit)


def di_best(network, planner, egress_times):
    """DI's router (as r5py's TripPlanner.transit_paths) with the given egress map; its best final state."""
    router_request = copy.copy(planner.request)
    suboptimal_minutes = max(router_request._regional_task.suboptimalMinutes, 0)

    def list_supplier_callback(departure_time):
        return com.conveyal.r5.profile.SuboptimalDominatingList(suboptimal_minutes)

    router = com.conveyal.r5.profile.McRaptorSuboptimalPathProfileRouter(
        network, router_request, planner._transit_access_times, egress_times, list_supplier_callback, None, True)
    router.route()
    best = None
    for states in router.finalStatesByDepartureTime.values():
        for state in states:
            if best is None or state.time < best.time:
                best = state
    return best


def state_summary(transit_layer, state, start_s, prefix):
    """Arrival minute, lines, alight stop, egress seconds of a final state."""
    if state is None:
        return {f"{prefix}_min": None}
    lines = []
    walker = state
    while walker:
        if walker.stop != EGRESS_STOP and walker.back is not None and walker.pattern != -1:
            lines.append(route_name(transit_layer, walker.pattern))
        walker = walker.back
    return {f"{prefix}_min": int((state.time - start_s) // SECONDS_PER_MIN), f"{prefix}_lines": "+".join(reversed(lines)),
            f"{prefix}_alight_stop": int(state.back.stop), f"{prefix}_egress_s": int(state.time - state.back.time)}


def egress_map(egress_s):
    """Egress seconds per stop in the form McRaptorSuboptimalPathProfileRouter takes."""
    stops = list(egress_s.keys())
    return jpype.JObject({com.conveyal.r5.api.util.LegMode.WALK: gnu.trove.map.hash.TIntIntHashMap(
        stops, [egress_s[stop] for stop in stops])},
        "java.util.Map<com.conveyal.r5.LegMode, gnu.trove.map.TIntIntMap>")


def google_ends():
    """Per draw_no, Google's earliest in-scope route: first board stop and time from the request, first walk
    (m, s), last alight stop, last walk (m)."""
    routes_df = pd.read_csv(GOOGLE_ROUTES_PATH)
    routes_df = routes_df[routes_df.route_scope.isin(GOOGLE_SCOPES)]
    earliest = routes_df.loc[routes_df.groupby("draw_no").arrival_from_request_s.idxmin()].set_index("draw_no")
    ends = {}
    with open(GOOGLE_RAW_PATH, encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)
            draw_no = record["draw_no"]
            if draw_no not in earliest.index:
                continue
            steps = record["resp"]["routes"][int(earliest.at[draw_no, "route_ix"])]["legs"][0]["steps"]
            transit_ix = [i for i, step in enumerate(steps) if step["travelMode"] == "TRANSIT"]
            if not transit_ix:
                continue
            first, last = steps[transit_ix[0]]["transitDetails"]["stopDetails"], steps[transit_ix[-1]]["transitDetails"]["stopDetails"]
            requested = pd.Timestamp(record["request"]["departureTime"])
            ends[draw_no] = {
                "g_board_lat": first["departureStop"]["location"]["latLng"]["latitude"],
                "g_board_lon": first["departureStop"]["location"]["latLng"]["longitude"],
                "g_board_from_request_s": (pd.Timestamp(first["departureTime"]) - requested).total_seconds(),
                "g_first_walk_m": sum(s.get("distanceMeters", 0) for s in steps[:transit_ix[0]]),
                "g_first_walk_s": sum(int(s["staticDuration"].rstrip("s")) for s in steps[:transit_ix[0]]),
                "g_alight_lat": last["arrivalStop"]["location"]["latLng"]["latitude"],
                "g_alight_lon": last["arrivalStop"]["location"]["latLng"]["longitude"],
                "g_last_walk_m": sum(s.get("distanceMeters", 0) for s in steps[transit_ix[-1] + 1:])}
    return ends


def run_pairs(network, c1_df, c2_draws, ends):
    """C1 rows for the 19 + controls, C2 rows for the late pairs."""
    transit_layer = network._transport_network.transitLayer
    stop_coords = [stop_lat_lon(transit_layer, stop) for stop in range(transit_layer.getStopCount())]
    pairs_df = pd.read_csv(PAIRS_PATH).set_index("draw_no")
    c1_rows, c2_rows = [], []
    for item in c1_df.itertuples():
        pair = pairs_df.loc[item.draw_no]
        pair_row = pair.copy()
        departure = departure_of(pair_row)
        start_s = (departure - departure.replace(hour=0, minute=0)).total_seconds()
        request = build_request(network, pair_row)
        ttm_min, path, ttm_egress_s, cost_unit = ttm_with_path(network, request)
        planner = TripPlanner(network, request)
        row = {"draw_no": item.draw_no, "group": item.group, "t1_min": item.t1_min, "raw_best_min": item.raw_best_min,
               "ttm_min": ttm_min, **path, "cost_unit": cost_unit, "n_ttm_egress_stops": len(ttm_egress_s)}
        row.update(state_summary(transit_layer, di_best(network, planner, planner._transit_egress_times), start_s, "di"))
        row.update(state_summary(transit_layer, di_best(network, planner, egress_map(ttm_egress_s)), start_s, "di_ttm_egress"))
        planner_egress = {int(stop): round(leg.travel_time.total_seconds())
                          for paths in planner._transit_egress_paths.values() for stop, leg in paths.items()}
        row["planner_egress_at_ttm_alight_s"] = planner_egress.get(row["ttm_alight_stop"])
        row["ttm_egress_at_ttm_alight_s"] = ttm_egress_s.get(row["ttm_alight_stop"])
        if item.draw_no in ends and row["ttm_alight_stop"] >= 0:
            end = ends[item.draw_no]
            row["g_alight_vs_ttm_alight_m"] = round(distance_m(end["g_alight_lat"], end["g_alight_lon"],
                                                               *stop_coords[row["ttm_alight_stop"]]))
            row["g_last_walk_m"] = end["g_last_walk_m"]
        print(f"  C1 {row}", flush=True)
        c1_rows.append(row)

    for draw_no in c2_draws:
        if draw_no not in ends:
            c2_rows.append({"draw_no": draw_no})
            continue
        end = ends[draw_no]
        request = build_request(network, pairs_df.loc[draw_no].copy())
        planner = TripPlanner(network, request)
        stop, match_m = nearest_stop(transit_layer, stop_coords, end["g_board_lat"], end["g_board_lon"])
        access_s = {int(s): round(leg.travel_time.total_seconds())
                    for paths in planner._transit_access_paths.values() for s, leg in paths.items()}
        row = {"draw_no": draw_no, **{k: v for k, v in end.items() if not k.endswith(("_lat", "_lon"))},
               "r5_board_stop": stop, "r5_board_stop_name": str(transit_layer.stopNames.get(stop)),
               "stop_match_m": round(match_m), "r5_access_s_3_6": access_s.get(stop)}
        print(f"  C2 {row}", flush=True)
        c2_rows.append(row)
    return pd.DataFrame(c1_rows), pd.DataFrame(c2_rows)


def main():
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_date = datetime.date.today().strftime("%Y%m%d")
    window_path = sorted(DIAGNOSTIC_DATA_DIR.glob(WINDOW_RESULTS_GLOB))[-1]
    raw_path = sorted(DIAGNOSTIC_DATA_DIR.glob(RAW_STATES_GLOB))[-1]
    speed_path = sorted(DIAGNOSTIC_DATA_DIR.glob(WALK_SPEED_GLOB))[-1]
    print(f"t1_min from {window_path.name}; raw DI best from {raw_path.name}; speeds from {speed_path.name}")
    raw_df = pd.read_csv(raw_path)[["draw_no", "t1_min", "raw_best_min"]]
    raw_df["raw_gap"] = raw_df.raw_best_min - raw_df.t1_min
    raw_df["group"] = None
    raw_df.loc[raw_df.raw_gap > ARRIVAL_TOLERANCE_MIN, "group"] = "late"
    raw_df.loc[raw_df.raw_gap < 0, "group"] = "earlier"
    controls = raw_df[raw_df.raw_gap == 0].sort_values("draw_no").head(CONTROL_COUNT).index
    raw_df.loc[controls, "group"] = "control"
    c1_df = raw_df[raw_df.group.notna()]

    speeds_df = pd.read_csv(speed_path)
    google_df = pd.read_csv(GOOGLE_ROUTES_PATH)
    google_df = google_df[google_df.route_scope.isin(GOOGLE_SCOPES)]
    google_min = (google_df.groupby("draw_no").arrival_from_request_s.min() // SECONDS_PER_MIN).rename("google_min")
    speeds_df = speeds_df.merge(google_min, left_on="draw_no", right_index=True, how="left")
    c2_draws = speeds_df.draw_no[speeds_df.ttm_min_3_6 - speeds_df.google_min >= LATE_GAP_MIN].tolist()

    saved_c1 = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_c1.csv"))
    saved_c2 = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_c2.csv"))
    if saved_c1 and saved_c2:
        print(f"reusing saved tables {saved_c1[-1].name}, {saved_c2[-1].name}")
        result_c1_df, result_c2_df = pd.read_csv(saved_c1[-1]), pd.read_csv(saved_c2[-1])
    else:
        network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        result_c1_df, result_c2_df = run_pairs(network, c1_df, c2_draws, google_ends())
        result_c1_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_c1.csv", index=False)
        result_c2_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_c2.csv", index=False)
    summary = summarise(result_c1_df, result_c2_df, speeds_df, run_date)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary)


def summarise(c1_df, c2_df, speeds_df, run_date):
    lines = [f"{NAME} {run_date}: C1 on {len(c1_df)} pairs ({c1_df.group.value_counts().to_dict()}); C2 on "
             f"{len(c2_df)} TTM-late pairs; tolerance {ARRIVAL_TOLERANCE_MIN} min; Claude's rules, not user-approved"]
    is_reproduced = c1_df.ttm_min == c1_df.t1_min
    lines.append(f"sanity: TTM with path results = t1_min on {int(is_reproduced.sum())} of {len(c1_df)}; "
                 f"DI (r5py egress) best = run 1 raw best on {int((c1_df.di_min == c1_df.raw_best_min).sum())} "
                 f"of {len(c1_df)} (sampler unseeded); egress cost unit {c1_df.cost_unit.unique().tolist()}")
    gap_planner = c1_df.di_min - c1_df.ttm_min
    gap_swapped = c1_df.di_ttm_egress_min - c1_df.ttm_min
    c1_df = c1_df.assign(gap_planner=gap_planner, gap_swapped=gap_swapped,
                         same_lines=c1_df.ttm_lines == c1_df.di_lines,
                         egress_diff_s=c1_df.planner_egress_at_ttm_alight_s - c1_df.ttm_egress_at_ttm_alight_s)
    for group in ["late", "earlier", "control"]:
        group_df = c1_df[c1_df.group == group]
        lines.append(f"{group} (n={len(group_df)}): DI - TTM with r5py egress {group_df.gap_planner.value_counts().sort_index().to_dict()}; "
                     f"with TTM's egress {group_df.gap_swapped.value_counts().sort_index().to_dict()}; same lines (r5py egress) "
                     f"{int(group_df.same_lines.sum())}; TripPlanner - TTM egress at TTM's alight stop: mean "
                     f"{group_df.egress_diff_s.mean():.0f} s, range {group_df.egress_diff_s.min()} / {group_df.egress_diff_s.max()}")
    late, earlier, control = (c1_df[c1_df.group == g] for g in ["late", "earlier", "control"])
    n_late = int((late.gap_swapped.abs() <= ARRIVAL_TOLERANCE_MIN).sum())
    n_earlier = int((earlier.gap_swapped >= 0).sum())
    n_control = int((control.gap_swapped.abs() <= ARRIVAL_TOLERANCE_MIN).sum())
    is_confirmed = n_late == len(late) and n_earlier >= MIN_EARLIER_FIXED and n_control == len(control)
    lines.append(f"VERDICT C1 (Claude's rule): {'CONFIRMED' if is_confirmed else 'NOT CONFIRMED'} (late within tol "
                 f"{n_late} of {len(late)}, need all; earlier fixed {n_earlier} of {len(earlier)}, need {MIN_EARLIER_FIXED}; "
                 f"controls within tol {n_control} of {len(control)}, need all)")
    is_google_same_stop = c1_df.g_alight_vs_ttm_alight_m <= STOP_MATCH_M
    google_df = c1_df[is_google_same_stop]
    lines.append(f"egress vs Google, pairs where Google alights within {STOP_MATCH_M} m of TTM's stop (n={len(google_df)}): "
                 f"Google last walk m median {google_df.g_last_walk_m.median():.0f}; TTM egress s median "
                 f"{google_df.ttm_egress_at_ttm_alight_s.median():.0f}; TripPlanner egress s median "
                 f"{google_df.planner_egress_at_ttm_alight_s.median():.0f} (both at 1.0 m/s, so s ~ m); |TTM - Google m| median "
                 f"{(google_df.ttm_egress_at_ttm_alight_s - google_df.g_last_walk_m).abs().median():.0f}, |TripPlanner - Google m| median "
                 f"{(google_df.planner_egress_at_ttm_alight_s - google_df.g_last_walk_m).abs().median():.0f}")
    lines.append(c1_df.drop(columns=["cost_unit"]).to_string(index=False))

    c2_df = c2_df.merge(speeds_df[["draw_no", "ttm_min_3_6", "ttm_min_4_2", "ttm_min_5_0", "google_min"]], on="draw_no", how="left")
    speed_ratio = BASELINE_SPEED_KMH / PRIMARY_SPEED_KMH
    c2_df["r5_walk_m"] = c2_df.r5_access_s_3_6 * BASELINE_SPEED_KMH / KMH_PER_MS
    c2_df["walk_ratio"] = c2_df.r5_walk_m / c2_df.g_first_walk_m
    c2_df["r5_walk_s_4_2"] = c2_df.r5_access_s_3_6 * speed_ratio
    is_matched = c2_df.stop_match_m <= STOP_MATCH_M
    in_time_walk = c2_df.r5_walk_s_4_2 < c2_df.g_board_from_request_s
    in_time_slack = c2_df.r5_walk_s_4_2 + BOARD_SLACK_S < c2_df.g_board_from_request_s
    is_long = c2_df.walk_ratio > DISTANCE_RATIO_LONG
    c2_df["at_4_2"] = "catches"
    c2_df.loc[~in_time_slack & in_time_walk, "at_4_2"] = "slack"
    c2_df.loc[~in_time_walk & is_long, "at_4_2"] = "distance"
    c2_df.loc[~in_time_walk & ~is_long, "at_4_2"] = "speed"
    c2_df.loc[~is_matched | c2_df.r5_access_s_3_6.isna(), "at_4_2"] = "no stop match"
    lines.append(f"C2 (descriptive, n={len(c2_df)}): R5 / Google first walk ratio median {c2_df.walk_ratio[is_matched].median():.2f}; "
                 f"ratio > {DISTANCE_RATIO_LONG} on {int((is_long & is_matched).sum())}; at {PRIMARY_SPEED_KMH} km/h, Google's first vehicle: "
                 f"{c2_df.at_4_2.value_counts().to_dict()}")
    five_df = c2_df[c2_df.draw_no.isin(CLOSE_ONLY_AT_5)]
    n_slack = int(((five_df.at_4_2 == "slack") & (five_df.walk_ratio <= DISTANCE_RATIO_LONG)).sum())
    lines.append(f"VERDICT C2 five pairs (Claude's rule): {'slack, not distance' if n_slack >= 4 else 'not slack-not-distance'} "
                 f"(slack with R5 walk within {DISTANCE_RATIO_LONG} of Google's on {n_slack} of {len(five_df)}; "
                 f"classes {dict(zip(five_df.draw_no, five_df.at_4_2))})")
    lines.append(c2_df.to_string(index=False))
    return "\n".join(lines)


def mechanism_main():
    """Run 2: C3 on C1's pairs (saved C1 table required); saved run-2 table reused if present."""
    run_date = datetime.date.today().strftime("%Y%m%d")
    c1_path = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_c1.csv"))[-1]
    c1_df = pd.read_csv(c1_path)
    print(f"pairs and TTM alight stops from {c1_path.name}")
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_mechanism.csv"))
    if saved:
        print(f"reusing saved table {saved[-1].name}")
        mechanism_df = pd.read_csv(saved[-1])
    else:
        network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        java_network = network._transport_network
        walk = com.conveyal.r5.profile.StreetMode.WALK
        pairs_df = pd.read_csv(PAIRS_PATH).set_index("draw_no")
        rows = []
        for item in c1_df.itertuples():
            pair = pairs_df.loc[item.draw_no].copy()
            request = build_request(network, pair)
            stop = int(item.ttm_alight_stop)
            linkage = java_network.linkageCache.getLinkage(
                request._regional_task.destinationPointSets[0], java_network.streetLayer, walk)
            table = linkage.getEgressCostTable()
            table.destructivelyTransposeForPropagationAsNeeded()
            cost_map = table.getCostTableForPoint(0)
            split = java_network.streetLayer.findSplit(pair.dest_lat, pair.dest_lon, SPLIT_RADIUS_M, walk)
            egress_request = copy.copy(request)
            egress_request._regional_task.reverseSearch = True       # as r5py trip_planner.py L472-484
            router = com.conveyal.r5.streets.StreetRouter(java_network.streetLayer)
            router.profileRequest = egress_request._regional_task
            router.setOrigin(pair.dest_lat, pair.dest_lon)
            router.transitStopSearch = True
            router.timeLimitSeconds = round(TripPlanner.MAX_EGRESS_TIME.total_seconds())
            router.streetMode = walk
            router.route()
            state = router.getStateAtVertex(java_network.transitLayer.streetVertexForStop.get(stop))
            row = {"draw_no": item.draw_no, "group": item.group, "stop": stop,
                   "ttm_egress_s": item.ttm_egress_at_ttm_alight_s, "planner_egress_s": item.planner_egress_at_ttm_alight_s,
                   "ttm_cost_mm": int(cost_map.get(stop)) if cost_map is not None and cost_map.containsKey(stop) else None,
                   "planner_state_s": int(state.getDurationSeconds()) if state is not None else None,
                   "planner_state_mm": int(state.distance) if state is not None else None,
                   "linked_edge": int(linkage.edges[0]), "split_edge": int(split.edge) if split is not None else None,
                   "linked_off_street_mm": int(linkage.distancesToEdge_mm[0]),
                   "split_off_street_mm": int(split.distanceToEdge_mm) if split is not None else None,
                   "linked_d0_mm": int(linkage.distances0_mm[0]), "linked_d1_mm": int(linkage.distances1_mm[0]),
                   "split_d0_mm": int(split.distance0_mm) if split is not None else None,
                   "split_d1_mm": int(split.distance1_mm) if split is not None else None}
            print(f"  {row}", flush=True)
            rows.append(row)
        mechanism_df = pd.DataFrame(rows)
        mechanism_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_mechanism.csv", index=False)
    mechanism_df["same_edge"] = mechanism_df.linked_edge.eq(mechanism_df.split_edge) | (
        (mechanism_df.linked_edge // 2).eq(mechanism_df.split_edge // 2))     # R5 stores edge pairs (forward, back)
    mechanism_df["planner_minus_ttm_s"] = mechanism_df.planner_egress_s - mechanism_df.ttm_egress_s
    mechanism_df["planner_minus_ttm_m"] = (mechanism_df.planner_state_mm - mechanism_df.ttm_cost_mm) / MM_PER_M
    lines = [f"{NAME} run 2 (mechanism) {run_date}: {len(mechanism_df)} pairs; descriptive, no rule",
             f"same street edge (either direction) in both linkings: {int(mechanism_df.same_edge.sum())} of {len(mechanism_df)}",
             f"planner state duration = r5py egress leg s on {int((mechanism_df.planner_state_s == mechanism_df.planner_egress_s).sum())}",
             f"corr(planner - TTM seconds, planner - TTM metres) = {mechanism_df.planner_minus_ttm_s.corr(mechanism_df.planner_minus_ttm_m):.2f}",
             mechanism_df.to_string(index=False)]
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_mechanism_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary)


def edge_flags(java_network, edge_index):
    """ALLOWS_PEDESTRIAN and NO_THRU_TRAFFIC_PEDESTRIAN of one directed edge."""
    flag = com.conveyal.r5.streets.EdgeStore.EdgeFlag
    cursor = java_network.streetLayer.edgeStore.getCursor(edge_index)
    return bool(cursor.getFlag(flag.ALLOWS_PEDESTRIAN)), bool(cursor.getFlag(flag.NO_THRU_TRAFFIC_PEDESTRIAN))


def destination_search(java_network, request, pair, is_reverse):
    """r5py's egress StreetRouter (trip_planner.py L469-507) with reverseSearch set as given."""
    egress_request = copy.copy(request)
    egress_request._regional_task.reverseSearch = is_reverse
    router = com.conveyal.r5.streets.StreetRouter(java_network.streetLayer)
    router.profileRequest = egress_request._regional_task
    router.setOrigin(pair.dest_lat, pair.dest_lon)
    router.transitStopSearch = True
    router.timeLimitSeconds = round(TripPlanner.MAX_EGRESS_TIME.total_seconds())
    router.streetMode = com.conveyal.r5.profile.StreetMode.WALK
    router.route()
    return router


def edges_main():
    """Run 3: C4 on C1's pairs (saved run-2 table required); saved run-3 table reused if present."""
    run_date = datetime.date.today().strftime("%Y%m%d")
    mechanism_path = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_mechanism.csv"))[-1]
    mechanism_df = pd.read_csv(mechanism_path)
    print(f"pairs, stops and egress distances from {mechanism_path.name}")
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_edges.csv"))
    if saved:
        print(f"reusing saved table {saved[-1].name}")
        edges_df = pd.read_csv(saved[-1])
    else:
        network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        java_network = network._transport_network
        walk = com.conveyal.r5.profile.StreetMode.WALK
        no_thru = com.conveyal.r5.streets.EdgeStore.EdgeFlag.NO_THRU_TRAFFIC_PEDESTRIAN
        pairs_df = pd.read_csv(PAIRS_PATH).set_index("draw_no")
        rows = []
        for item in mechanism_df.itertuples():
            pair = pairs_df.loc[item.draw_no].copy()
            request = build_request(network, pair)
            stop_vertex = java_network.transitLayer.streetVertexForStop.get(int(item.stop))
            forward_edge = int(item.linked_edge) - int(item.linked_edge) % 2      # R5 edge pairs: even forward, odd back
            walk_fwd, no_thru_fwd = edge_flags(java_network, forward_edge)
            walk_back, no_thru_back = edge_flags(java_network, forward_edge + 1)
            row = {"draw_no": item.draw_no, "group": item.group, "ttm_cost_m": item.ttm_cost_mm / MM_PER_M,
                   "r5py_m": item.planner_state_mm / MM_PER_M, "walk_fwd": walk_fwd, "walk_back": walk_back,
                   "no_thru_fwd": no_thru_fwd, "no_thru_back": no_thru_back}
            for label, is_reverse in [("reverse", True), ("forward", False)]:
                state = destination_search(java_network, request, pair, is_reverse).getStateAtVertex(stop_vertex)
                row[f"from_dest_{label}_m"] = state.distance / MM_PER_M if state is not None else None
                if is_reverse and state is not None:
                    n_edges = n_no_thru = 0
                    walker = state
                    while walker is not None and walker.backEdge >= 0:
                        n_edges += 1
                        n_no_thru += int(java_network.streetLayer.edgeStore.getCursor(walker.backEdge).getFlag(no_thru))
                        walker = walker.backState
                    row.update({"r5py_path_edges": n_edges, "r5py_path_no_thru_edges": n_no_thru})
            stop_router = com.conveyal.r5.streets.StreetRouter(java_network.streetLayer)
            stop_router.profileRequest = request._regional_task
            stop_router.streetMode = walk
            stop_router.quantityToMinimize = com.conveyal.r5.streets.StreetRouter.State.RoutingVariable.DISTANCE_MILLIMETERS
            stop_router.distanceLimitMeters = DISTANCE_LIMIT_M
            stop_router.setOrigin(stop_vertex)
            stop_router.route()
            split = java_network.streetLayer.findSplit(pair.dest_lat, pair.dest_lon, SPLIT_RADIUS_M, walk)
            end_state = stop_router.getState(split)
            row["from_stop_forward_m"] = end_state.distance / MM_PER_M if end_state is not None else None
            print(f"  {row}", flush=True)
            rows.append(row)
        edges_df = pd.DataFrame(rows)
        edges_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_edges.csv", index=False)
    is_gap = (edges_df.r5py_m - edges_df.ttm_cost_m).abs() > PATH_GAP_M
    is_one_way = edges_df.walk_fwd != edges_df.walk_back
    is_reverse_effect = (edges_df.from_dest_reverse_m - edges_df.from_dest_forward_m).abs() > PATH_GAP_M
    is_explained = is_one_way | is_reverse_effect
    lines = [f"{NAME} run 3 (edges) {run_date}: {len(edges_df)} pairs; {int(is_gap.sum())} with |r5py - TTM| > {PATH_GAP_M} m",
             f"VERDICT C4 (Claude's rule): {'SUPPORTED' if is_explained[is_gap].all() else 'NOT SUPPORTED'} "
             f"(explained on {int(is_explained[is_gap].sum())} of {int(is_gap.sum())}: one-way walk edge "
             f"{int((is_one_way & is_gap).sum())}, reverseSearch changes the path {int((is_reverse_effect & is_gap).sum())})",
             f"reverse = r5py's run-2 distance on {int(((edges_df.from_dest_reverse_m - edges_df.r5py_m).abs() < 1).sum())} "
             f"of {len(edges_df)}; forward-from-stop within {PATH_GAP_M} m of TTM's cost on "
             f"{int(((edges_df.from_stop_forward_m - edges_df.ttm_cost_m).abs() <= PATH_GAP_M).sum())} of {len(edges_df)}; "
             f"pairs with no-through edges on r5py's path: {int((edges_df.r5py_path_no_thru_edges > 0).sum())} "
             f"(gap pairs {int(((edges_df.r5py_path_no_thru_edges > 0) & is_gap).sum())})",
             edges_df.to_string(index=False)]
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_edges_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary)


if __name__ == "__main__":
    if IS_EDGES_RUN:
        edges_main()
    elif IS_MECHANISM_RUN:
        mechanism_main()
    else:
        main()
