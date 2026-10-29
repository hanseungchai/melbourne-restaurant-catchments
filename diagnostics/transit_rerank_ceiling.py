"""Does R5's own option list hold Google's default trip on the hard misses? (re-rank ceiling, check 1)

Claim under test (musing 2026-10-19, user's idea; concepts/transit.md TRN-13, candidate "re-rank R5's alternatives
with Google's preference"): the no-wait model's hard misses arise because R5 returns only its fastest trip, while
Google ranks alternatives by preference; a re-rank of R5's own options (after routing, no change to how R5 routes)
could pick Google's trip. A re-rank can only work where Google's trip is among R5's options, so this measures that
ceiling first. Where the pipeline would rely on it: nowhere yet; it decides whether a re-rank is worth building.

Method (Claude's, set 2026-10-19 before any result of this script was seen):
- Pairs: the hard misses of the model of record (no-wait plain, k = 2) on the v2 pathways network
  (transit_pathway_network_v2_*_range_misses.csv), one row per pair (31 pairs; a pair in two tests counts once).
- R5: the multi-criteria router behind r5py's DetailedItineraries (McRaptorSuboptimalPathProfileRouter), called
  as r5py 1.1.7's TripPlanner does (as transit_di_raw_states.py), on the v2 network of the pair's release, walk
  4.16 km/h, Wed 2026-10-21, departures from t - 1 min over a WINDOW_SPAN_MIN window (Google's default may wait at
  home: home wait p95 ~18 min, stage 1b), every final state of every sampled departure read (r5py keeps one per
  departure second). Run at two values of R5's suboptimalMinutes (options kept if no more than that many minutes
  worse than the best at their departure): R5's default, and SUBOPTIMAL_WIDE_MIN, a request field (no Java change).
- Option time: corrected arrival - t (Google's framing, home wait included), where the corrected arrival is the
  alighting time at the last stop plus a walk-only TravelTimeMatrix time from that stop to the destination (DI's
  own egress walk is faulty, transit_router_egress.py). Whole minutes.
- Google's default: its rides from transit_invehicle_stretch_*_rides_matched.csv (line, vehicle, board and alight
  stop, board and alight clock time; train half and second batch), route_ix 0 (the default on every scored pair).
- Match levels for an R5 option against Google's default (rule set before results):
    lines  same ride count, same line on each ride (short name, case-insensitive, train " line" dropped);
    route  lines + each ride's board and alight stop within STOP_MATCH_M (100 m, as transit_stop_match.py);
    trip   route + each ride boarding within BOARD_MATCH_MIN (1 min) of Google's board clock time of day.
  A miss is "fixable" by a re-rank if some option at the trip level (reported also at route level) has an option
  time on Google's side of the miss's cut (false reach: > cut; lost reach: <= cut).
- Verdict (Claude's rule, not user-approved): the re-rank idea survives check 1 if Google's default trip is among
  R5's options (trip level) on at least half of the early misses (false reach, the only ones a re-rank, which can
  only pick a slower option, could fix), at either suboptimalMinutes value; otherwise the idea stops here. Late
  misses (lost reach) reported, no verdict.

Conclusion (run 2026-10-19): SURVIVES check 1. Google's default trip (same lines, stops within 100 m, boarding
  within 1 min) is among R5's options on 13 / 23 early misses at R5's default suboptimalMinutes (5) and 16 / 23 at
  20 (0.696; the same route at any departure on 17 and 22); every trip-level match puts the miss on Google's side
  of the cut. By group (at 20): Google waits at home 4/5, R5 walks where Google rides 5/5, Google rides a tram and
  R5 is faster 6/10, other 1/3. Late misses: Google's route is in R5's set on 8/8 but never its vehicle (R5
  can't make the knife-edge boarding), so a re-rank fixes none, as expected. Checks: trip-matched option times
  equal Google's default to the minute on 10 of 16 (within 1 on 14); R5's fastest option equals stock R5 (TTM) on
  19 of 31 (the two routers differ, known, T7 e). Cost signal: distinct options per pair, median 56 at 5, 1,700 at
  20 (max 12,259). A ceiling only: whether a preference rule picks these trips without breaking correct pairs
  is check 2, untested.

Random-sample mode: path baseline on the current model (user, 2026-10-19, TRN-13; autonomous run 2026-10-19).
Rules from the user (HANDOFF task 0): 300 random scored pairs from the training half and the second batch,
stratified by set, seeded; test half and top-up out; v2 network, each set on its own release; walk 4.16 km/h;
Wed 2026-10-21; departures t - 1 .. t + 20 min; match definitions as transit_stop_match.py (stops within 100 m,
short-name lines, " line" dropped), Google's default in scope only (TRN-11); path stays closed unless route-level
coverage >= 0.8; no time verdict. Details set by Claude before any sample result (Claude's rule, not user-approved):
- Population: v2 range results (scored), set train or second, Google's default route_scope in_scope or
  name_mismatch (each set's own route table). Allocation proportional to set size (rounded), each set drawn with
  numpy's default_rng(SAMPLE_SEED) without replacement. Routed: SAMPLE_ROUTED (100; user cut it from 300 after
  the first pairs ran ~85 s each, exploratory), the first ones per set of a seeded permutation of the draw, again
  proportional; if route-level coverage at 20 falls inside EXTEND_BAND (0.70-0.90), too close to the bar, the
  subset is extended from the same permutation (Claude's rule, set before results).
- Google's default: route_ix 0 rides from the full extract transit_invehicle_stretch_*_google_rides.csv (the
  matched file drops rides it could not match to the timetable); walk only per the route table's is_walk_only.
- R5's path (stand-in for the time model's path, which TTM does not give): among R5's options at its default
  suboptimalMinutes, the one with the smallest option time (ties: fewer rides, then later first boarding), against
  a walk-only TravelTimeMatrix time origin -> destination; walk wins if its minutes <= the best option's.
- Baseline (as transit_stop_match.py): walk-or-transit agreement; among both-transit pairs, first boarding stop,
  last alighting stop, same ride count, same lines, full route (lines + every board and alight stop); path
  agreement over all sampled pairs (both walk only = match).
- Ceiling: Google's default among R5's options (any departure in the window) at route and trip level, at both
  suboptimalMinutes values; a walk-only default counts as covered (walk is always available, as transit_stop_match).
  The rule reads route-level coverage over all sampled pairs at the wide value (20); the default value is reported.
- Re-rank risk, pairs a re-rank might break: (a) path-correct pairs (full route) with a distinct slower option of
  another route; (b) for cuts 10 and 20, pairs where R5's pick is <= cut and Google's default is <= cut, with an
  option of another route > cut (a re-rank that picked it would lose reach), counted at both suboptimalMinutes.
- Checks: R5's pick minutes against the model of record (no-wait plain, n_min); run seconds and options per pair.
- Post-hoc (Claude, added after the first report showed same-line, same-minute non-matches): option times are
  whole minutes, so several options often tie for fastest and the pick among them is arbitrary; an upper bound
  counts the baseline matched if any tied-fastest option matches. Both are reported.
- Rank mode (user's question, 2026-10-19; rule Claude's, set before running): at each suboptimalMinutes value,
  R5's options collapse to distinct routes (lines + board / alight stop per ride), each keeping its fastest option
  time; walk only is one more candidate (walk-only TTM minutes). Routes are ranked fastest first; Google's rank is
  the first route matching its default at route level (a walk-only default matches walk only). Whole-minute ties
  give a best and a worst rank. Reported: cumulative share matched at ranks RANKS_REPORTED, median rank.

Conclusion, random-sample mode (run 2026-10-19, 100 pairs): R5's fastest matches Google's default full route on
  0.152 of both-transit pairs (0.467 if any whole-minute tied-fastest option counts); walk-or-transit 0.960.
  Route-level coverage 0.750 at suboptimalMinutes 5, 0.910 at 20: the user's 0.8 rule is met at 20 only. Rank:
  Google's route at rank 1 on 0.13-0.47, decaying; within rank 10 0.53-0.65 at both settings, so 20 adds coverage
  only beyond rank 20. Re-rank parked (user); a foot-traffic reading from the rank decay is open (TRN-12).

Inputs (read only): diagnostic_data/transit_pathway_network_v2_* (derived OSM per release, moved / renamed feeds,
range misses, range results), transit_invehicle_stretch_*_rides_matched.csv and _google_rides.csv, Google route
tables in outputs/transit_validation/. Self-contained (CLAUDE.md D1): imports nothing from functions/ or config.py.
No paid API calls; r5py only. Saved per-release option tables are reused if present; the sample's option tables
are appended per pair, so a rerun resumes.
Usage: `python transit_rerank_ceiling.py explore 20261009`; `... route 20261009`; `... route 20261016`; `... report`;
`... sample_route 20261009`; `... sample_route 20261016`; `... sample_report`.
"""
import copy
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_rerank_ceiling"
V2_NAME = "transit_pathway_network_v2"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
MISSES_GLOB = f"{V2_NAME}_2*_range_misses.csv"
RIDES_GLOB = "transit_invehicle_stretch_*_rides_matched.csv"
MISS_MODEL = "no-wait plain (reported)"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_pathway_network_v2.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WALK_SPEED_KMH = 4.16                          # config.WALK_SPEED_KMH
MAX_TIME_MIN = 90                              # as transit_di_raw_states.py
BOARD_SLACK_MIN = 1                            # no-wait start t - 1 min (T7 e)
WINDOW_SPAN_MIN = 21                           # t - 1 .. t + 20: covers Google's home waits (p95 ~18 min, stage 1b)
DEPARTURE_STEP_S = 20                          # sampler step; draws = span / step
SUBOPTIMAL_WIDE_MIN = 20                       # widened suboptimalMinutes (request field)
STOP_MATCH_M = 100                             # as transit_stop_match.py
BOARD_MATCH_MIN = 1
TRAIN_LINE_SUFFIX = " line"
EGRESS_STOP = -1                               # R5 marks the final (egress) state with stop -1
SECONDS_PER_MIN = 60
EARTH_RADIUS_M = 6_371_000
LOCAL_TZ = "Australia/Melbourne"
CUTS_MIN = {"10": 10, "20": 20}

# --- random-sample mode (path baseline) ---------------------------------------------------------------
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
ROUTE_TABLE_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                     "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv"}
RESULTS_GLOB = f"{V2_NAME}_2*_range_results.csv"
GOOGLE_RIDES_GLOB = "transit_invehicle_stretch_*_google_rides.csv"
SET_RELEASE = {"train": "20261009", "second": "20261016"}
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]  # TRN-11
SAMPLE_SIZE = 300
SAMPLE_SEED = 20261019
SAMPLE_ROUTED = 100                            # routed subset (user, 2026-10-19: exploratory; 300 took ~7 h)
EXTEND_BAND = (0.70, 0.90)                     # Claude's rule: coverage inside this band -> extend the subset
SAMPLE_TAG = "sample"
RANKS_REPORTED = [1, 2, 3, 5, 10, 20, 50]
COVERAGE_RULE = 0.8                           # user: path stays closed below this route-level coverage


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def misses():
    misses_df = pd.read_csv(newest(MISSES_GLOB))
    misses_df = misses_df[misses_df.model == MISS_MODEL].copy()
    misses_df["release"] = misses_df.release.astype(int).astype(str)
    return misses_df.drop_duplicates(["set_name", "draw_no"])


# --- network (as transit_pathway_network_v2.py load_network, copied) --------------------------------
def network_paths(release):
    pbf_path = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{release}.osm.pbf"
    feed_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{release}"
    paths = [feed_dir / (f"{name}_{V2_NAME}_{release}_moved.zip" if name == TRAIN_FEED else f"{name}_{V2_NAME}_{release}.zip")
             for name in FEED_NAMES]
    return pbf_path, paths


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (stale copy under the same name)."""
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


def load_network(release):
    from r5py import TransportNetwork
    pbf_path, paths = network_paths(release)
    assert pbf_path.exists() and all(path.exists() for path in paths), f"v2 network files missing for {release}"
    check_working_copies([pbf_path] + paths)
    print(f"network {pbf_path.name} + {[path.name for path in paths]}", flush=True)
    return TransportNetwork(pbf_path, paths)


# --- R5 options --------------------------------------------------------------------------------------
def start_of(pair):
    """Google's request minute t on WINDOW_DATE."""
    return datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))


def planner_for(network, pair, suboptimal_min):
    import geopandas as gpd
    from r5py import TransportMode
    from r5py.r5.regional_task import RegionalTask
    from r5py.r5.trip_planner import TripPlanner
    origin = gpd.points_from_xy([pair.origin_lon], [pair.origin_lat], crs="EPSG:4326")[0]
    destination = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
    request = RegionalTask(network, origin=origin, destinations=destination,
                           departure=start_of(pair) - datetime.timedelta(minutes=BOARD_SLACK_MIN),
                           departure_time_window=datetime.timedelta(minutes=WINDOW_SPAN_MIN),
                           transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
                           max_time=datetime.timedelta(minutes=MAX_TIME_MIN), speed_walking=WALK_SPEED_KMH)
    request._regional_task.toLat, request._regional_task.toLon = pair.dest_lat, pair.dest_lon
    request._regional_task.monteCarloDraws = WINDOW_SPAN_MIN * SECONDS_PER_MIN // DEPARTURE_STEP_S
    if suboptimal_min is not None:
        request._regional_task.suboptimalMinutes = suboptimal_min
    return TripPlanner(network, request)


def run_router(network, planner):
    """Every final state of the multi-criteria router, as r5py 1.1.7 TripPlanner.transit_paths sets it up."""
    import com.conveyal.r5
    router_request = copy.copy(planner.request)
    suboptimal_minutes = max(router_request._regional_task.suboptimalMinutes, 0)

    def list_supplier_callback(departure_time):
        return com.conveyal.r5.profile.SuboptimalDominatingList(suboptimal_minutes)

    router = com.conveyal.r5.profile.McRaptorSuboptimalPathProfileRouter(
        network, router_request, planner._transit_access_times, planner._transit_egress_times,
        list_supplier_callback, None, True)
    router.route()
    return router, suboptimal_minutes


def explore(release):
    """One pair: print the state's Java fields, R5's default suboptimalMinutes and the sampled departures."""
    network = load_network(release)
    pair = next(misses()[lambda df: df.release == release].itertuples())
    planner = planner_for(network, pair, None)
    router, suboptimal_minutes = run_router(network, planner)
    print("default suboptimalMinutes", suboptimal_minutes, "draws", planner.request._regional_task.monteCarloDraws)
    keys = sorted(int(key) for key in router.finalStatesByDepartureTime.keys())
    print("departures", len(keys), [key - keys[0] for key in keys][:12], "...")
    state = list(router.finalStatesByDepartureTime.values())[0]
    state = list(state)[0]
    for field in state.getClass().getDeclaredFields():
        field.setAccessible(True)
        print("  field", field.getName(), field.getType().getName(), field.get(state))
    chain = state
    while chain is not None:
        print("  chain stop", chain.stop, "time", chain.time, "pattern", chain.pattern)
        chain = chain.back


def norm_line(name):
    name = str(name).strip().lower()
    return name[: -len(TRAIN_LINE_SUFFIX)] if name.endswith(TRAIN_LINE_SUFFIX) else name


def option_rides(network, state):
    """Rides of a final state, first ride first: line, board / alight stop index, board / alight second of day."""
    transit_layer = network._transport_network.transitLayer
    rides = []
    chain = state.back
    while chain is not None and chain.back is not None:
        if chain.pattern != -1:
            pattern = transit_layer.tripPatterns.get(chain.pattern)
            route = transit_layer.routes.get(pattern.routeIndex)
            short_name = str(route.route_short_name or "")
            rides.append({"line": norm_line(short_name if short_name not in ("", "None") else str(route.route_long_name or "")),
                          "board_stop": int(pattern.stops[chain.boardStopPosition]), "alight_stop": int(chain.stop),
                          "board_s": int(chain.boardTime), "alight_s": int(chain.time),
                          "key": f"{chain.pattern}:{chain.trip}:{chain.boardStopPosition}:{chain.alightStopPosition}"})
        chain = chain.back
    return list(reversed(rides))


def egress_walk_min(network, stops, pair, stop_coords):
    """Walk-only TravelTimeMatrix minutes from each stop to the pair's destination (DI's egress walk is faulty)."""
    import geopandas as gpd
    from r5py import TransportMode, TravelTimeMatrix
    origins = gpd.GeoDataFrame({"id": stops}, crs="EPSG:4326",
                               geometry=gpd.points_from_xy([stop_coords[s][1] for s in stops], [stop_coords[s][0] for s in stops]))
    destinations = gpd.GeoDataFrame({"id": [-1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
    matrix_df = pd.DataFrame(TravelTimeMatrix(network, origins=origins, destinations=destinations, departure=start_of(pair),
                                              transport_modes=[TransportMode.WALK], speed_walking=WALK_SPEED_KMH,
                                              max_time=datetime.timedelta(minutes=MAX_TIME_MIN)))
    return dict(zip(matrix_df.from_id, matrix_df.travel_time))


def stop_coordinates(network):
    transit_layer = network._transport_network.transitLayer
    fixed_degrees = 1e7
    coords = {}
    for stop in range(transit_layer.getStopCount()):
        coordinate = transit_layer.getCoordinateForStopFixed(stop)
        coords[stop] = (coordinate.y / fixed_degrees, coordinate.x / fixed_degrees)
    return coords


def route(release):
    """Every distinct R5 option on each miss pair of this release, at both suboptimalMinutes values."""
    import json
    network = load_network(release)
    stop_coords = stop_coordinates(network)
    rows = []
    pairs_df = misses()[lambda df: df.release == release]
    for pair in pairs_df.itertuples():
        start_s = int(pair.dep_min_of_day) * SECONDS_PER_MIN
        for suboptimal_min in (None, SUBOPTIMAL_WIDE_MIN):
            try:
                router, suboptimal_used = run_router(network, planner_for(network, pair, suboptimal_min))
                options = {}
                for states in router.finalStatesByDepartureTime.values():
                    for state in states:
                        rides = option_rides(network, state)
                        if not rides:
                            continue
                        key = "|".join(ride["key"] for ride in rides)
                        if key not in options:
                            options[key] = rides
                walks = egress_walk_min(network, sorted({rides[-1]["alight_stop"] for rides in options.values()}), pair, stop_coords)
                for key, rides in options.items():
                    for ride in rides:
                        ride.update({"board_lat": stop_coords[ride["board_stop"]][0], "board_lon": stop_coords[ride["board_stop"]][1],
                                     "alight_lat": stop_coords[ride["alight_stop"]][0], "alight_lon": stop_coords[ride["alight_stop"]][1]})
                    walk_min = walks.get(rides[-1]["alight_stop"], np.nan)
                    arrival_s = rides[-1]["alight_s"] + walk_min * SECONDS_PER_MIN
                    rows.append({"set_name": pair.set_name, "draw_no": pair.draw_no, "suboptimal_min": suboptimal_used,
                                 "lines": "+".join(ride["line"] for ride in rides), "n_rides": len(rides),
                                 "first_board_s": rides[0]["board_s"], "egress_walk_min": walk_min,
                                 "option_min": (arrival_s - start_s) // SECONDS_PER_MIN, "rides": json.dumps(rides)})
                print(f"  {pair.set_name} {pair.draw_no} suboptimal {suboptimal_used}: {len(options)} options", flush=True)
            except Exception as error:                                   # recorded per pair, read after
                rows.append({"set_name": pair.set_name, "draw_no": pair.draw_no, "suboptimal_min": suboptimal_min,
                             "error": f"{type(error).__name__}: {error}"[:300]})
                print(f"  {pair.set_name} {pair.draw_no}: ERROR {error}", flush=True)
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_options_{release}.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"saved {path.name}")


# --- report ------------------------------------------------------------------------------------------
def distance_m(lat1, lon1, lat2, lon2):
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((phi2 - phi1) / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def google_default_rides():
    rides_df = pd.read_csv(newest(RIDES_GLOB))
    rides_df = rides_df[rides_df.route_ix == 0].copy()
    local = pd.to_datetime(rides_df.board_time, utc=True).dt.tz_convert(LOCAL_TZ)
    rides_df["board_s"] = local.dt.hour * 3600 + local.dt.minute * 60 + local.dt.second
    rides_df["line_norm"] = rides_df.line.map(norm_line)
    return {key: group.sort_values("board_s").to_dict("records") for key, group in rides_df.groupby(["set_name", "draw_no"])}


def match_level(google_rides, r5_rides):
    """Highest level reached: 'trip' > 'route' > 'lines' > ''."""
    if len(google_rides) != len(r5_rides) or any(g["line_norm"] != r["line"] for g, r in zip(google_rides, r5_rides)):
        return ""
    def near(g, r, end):
        return distance_m(g[f"{end}_lat"], g[f"{end}_lon"], r[f"{end}_lat"], r[f"{end}_lon"]) <= STOP_MATCH_M
    if not all(near(g, r, "board") and near(g, r, "alight") for g, r in zip(google_rides, r5_rides)):
        return "lines"
    if not all(abs(g["board_s"] - r["board_s"]) <= BOARD_MATCH_MIN * SECONDS_PER_MIN for g, r in zip(google_rides, r5_rides)):
        return "route"
    return "trip"


def report():
    import json
    run_date = f"{datetime.date.today():%Y%m%d}"
    misses_df = misses()
    options_df = pd.concat([pd.read_csv(newest(f"{NAME}_2*_options_{release}.csv")) for release in ("20261009", "20261016")],
                           ignore_index=True)
    google = google_default_rides()
    lines = [f"{NAME} {run_date}: is Google's default among R5's own options on the hard misses ({MISS_MODEL}, v2, k = 2)?",
             f"pairs {len(misses_df)}; window t - {BOARD_SLACK_MIN} .. +{WINDOW_SPAN_MIN} min, step ~{DEPARTURE_STEP_S} s; "
             f"walk {WALK_SPEED_KMH} km/h; levels lines / route ({STOP_MATCH_M} m) / trip (+-{BOARD_MATCH_MIN} min board)"]
    if "error" in options_df and options_df.error.notna().any():
        lines.append(f"errors: {options_df.error.notna().sum()} rows: {options_df.error.dropna().unique()[:3]}")
    rows = []
    level_rank = {"": 0, "lines": 1, "route": 2, "trip": 3}
    for pair in misses_df.itertuples():
        g_rides = google.get((pair.set_name, pair.draw_no), [])
        cut = CUTS_MIN[pair.test.split()[-1]]
        is_false = pair.test.startswith("false")
        for suboptimal_min, pair_df in options_df[(options_df.set_name == pair.set_name) & (options_df.draw_no == pair.draw_no)
                                                  & options_df.option_min.notna()].groupby("suboptimal_min"):
            best = {"level": "", "fix_trip": False, "fix_route": False, "trip_min": np.nan}
            for option in pair_df.itertuples():
                level = match_level(g_rides, json.loads(option.rides)) if g_rides else ""
                is_google_side = option.option_min > cut if is_false else option.option_min <= cut
                if level_rank[level] > level_rank[best["level"]]:
                    best["level"] = level
                if level == "trip":
                    best["fix_trip"] |= is_google_side
                    if np.isnan(best["trip_min"]) or abs(option.option_min - pair.default_min) < abs(best["trip_min"] - pair.default_min):
                        best["trip_min"] = option.option_min
                if level in ("trip", "route"):
                    best["fix_route"] |= is_google_side
            rows.append({"set_name": pair.set_name, "draw_no": pair.draw_no, "test": pair.test, "group": pair.group,
                         "is_false": is_false, "suboptimal_min": int(suboptimal_min), "n_options": len(pair_df),
                         "google_rides": len(g_rides), "google_lines": "+".join(g["line_norm"] for g in g_rides),
                         "default_min": pair.default_min, "model_min": pair.model_min, "stock_min": pair.stock_min,
                         "r5_best_option_min": pair_df.option_min.min(), **best})
    result_df = pd.DataFrame(rows)
    result_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_results.csv", index=False)
    for suboptimal_min, sub in result_df.groupby("suboptimal_min"):
        lines += ["", f"suboptimalMinutes {suboptimal_min}: options per pair median {sub.n_options.median():.0f} (max {sub.n_options.max()})",
                  f"  check: R5's fastest option time - stock R5 (TTM from t): "
                  f"{(sub.r5_best_option_min - sub.stock_min).value_counts().sort_index().to_dict()}"]
        trip = sub[sub.level == "trip"]
        lines.append(f"  check: trip-matched option time - Google default: {(trip.trip_min - trip.default_min).value_counts().sort_index().to_dict()}")
        for label, part in (("early (false reach)", sub[sub.is_false]), ("late (lost reach)", sub[~sub.is_false])):
            lines.append(f"  {label} n {len(part)}: level reached {part.level.replace('', 'none').value_counts().to_dict()}; "
                         f"trip {int((part.level == 'trip').sum())}/{len(part)}, route+ {int(part.level.isin(['trip', 'route']).sum())}/{len(part)}; "
                         f"fixable at trip {int(part.fix_trip.sum())}, at route+ {int(part.fix_route.sum())}")
            by_group = part.groupby("group").agg(n=("draw_no", "size"), trip=("level", lambda s: int((s == "trip").sum())),
                                                 fix_trip=("fix_trip", "sum"))
            lines.append("    by group: " + "; ".join(f"{group} {row.trip}/{row.n} (fixable {int(row.fix_trip)})" for group, row in by_group.iterrows()))
    early = result_df[result_df.is_false]
    best_share = early.groupby("suboptimal_min").apply(lambda df: (df.level == "trip").mean()).max()
    lines += ["", f"verdict (Claude's rule, not user-approved): Google's default trip among R5's options on "
              f"{best_share:.3f} of early misses at the better suboptimalMinutes value (bar >= 0.5): "
              + ("SURVIVES check 1" if best_share >= 0.5 else "STOPS here")]
    lines += ["", "per pair (suboptimal default / wide): level, fixable at trip, Google lines, default, R5 no-wait, options"]
    for (set_name, draw_no), part in result_df.groupby(["set_name", "draw_no"]):
        first = part.iloc[0]
        lines.append(f"  {set_name} {draw_no} | {first.test} | {first.group} | Google {first.google_lines} {first.default_min:.0f} min, "
                     f"R5 {first.model_min:.0f} | " + " / ".join(f"{row.level or 'none'} fix {row.fix_trip} ({row.n_options})"
                                                         for row in part.sort_values("suboptimal_min").itertuples()))
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")


# --- random-sample mode: path baseline ------------------------------------------------------------------
def sample_pairs():
    """SAMPLE_SIZE scored pairs, train half and second batch, Google's default in scope, stratified by set."""
    results_df = pd.read_csv(newest(RESULTS_GLOB))
    results_df = results_df[results_df.set_name.isin(SET_RELEASE)].copy()
    results_df["release"] = results_df.release.astype(int).astype(str)
    parts = []
    for set_name, route_table_path in ROUTE_TABLE_PATHS.items():
        default_df = pd.read_csv(route_table_path)
        default_df = default_df[default_df.is_default & default_df.route_scope.isin(GOOGLE_SCOPES)]
        set_df = results_df[results_df.set_name == set_name].merge(
            default_df[["draw_no", "is_walk_only", "route_scope"]], on="draw_no")
        parts.append(set_df.sort_values("draw_no").reset_index(drop=True))
    population = sum(len(part) for part in parts)
    sampled = []
    for part in parts:
        n_draw = round(SAMPLE_SIZE * len(part) / population)
        rng = np.random.default_rng(SAMPLE_SEED)
        drawn = part.iloc[np.sort(rng.choice(len(part), size=n_draw, replace=False))]
        n_routed = round(SAMPLE_ROUTED * len(part) / population)
        sampled.append(drawn.iloc[np.sort(np.random.default_rng(SAMPLE_SEED).permutation(len(drawn))[:n_routed])])
    sample_df = pd.concat(sampled, ignore_index=True)
    sample_df.attrs["population"] = {part.set_name.iloc[0]: len(part) for part in parts}
    return sample_df


def collect_options(network, pair, suboptimal_min, stop_coords):
    """Distinct R5 options (rides list) of one pair at one suboptimalMinutes value, and the value used."""
    router, suboptimal_used = run_router(network, planner_for(network, pair, suboptimal_min))
    options = {}
    for states in router.finalStatesByDepartureTime.values():
        for state in states:
            rides = option_rides(network, state)
            if rides:
                options.setdefault("|".join(ride["key"] for ride in rides), rides)
    for rides in options.values():
        for ride in rides:
            ride.update({"board_lat": stop_coords[ride["board_stop"]][0], "board_lon": stop_coords[ride["board_stop"]][1],
                         "alight_lat": stop_coords[ride["alight_stop"]][0], "alight_lon": stop_coords[ride["alight_stop"]][1]})
            del ride["key"]
    return options, suboptimal_used


def walk_only_min(network, pair):
    import geopandas as gpd
    from r5py import TransportMode, TravelTimeMatrix
    origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.origin_lon], [pair.origin_lat]))
    destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
    matrix_df = pd.DataFrame(TravelTimeMatrix(network, origins=origins, destinations=destinations, departure=start_of(pair),
                                              transport_modes=[TransportMode.WALK], speed_walking=WALK_SPEED_KMH,
                                              max_time=datetime.timedelta(minutes=MAX_TIME_MIN)))
    return float(matrix_df.travel_time.iloc[0])


def sample_paths(release):
    prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_{SAMPLE_TAG}"
    return Path(f"{prefix}_options_{release}.csv.gz"), Path(f"{prefix}_pairs_{release}.csv")


def sample_route(release):
    """R5's options at both suboptimalMinutes values and the walk-only time, per sampled pair; appended per pair."""
    import json
    import time
    options_path, pairs_path = sample_paths(release)
    pairs_df = sample_pairs()[lambda df: df.release == release]
    done = set(pd.read_csv(pairs_path).draw_no) if pairs_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"release {release}: {len(pairs_df)} sampled pairs, {len(done)} done, {len(todo_df)} to route", flush=True)
    if todo_df.empty:
        return
    network = load_network(release)
    stop_coords = stop_coordinates(network)
    for pair in todo_df.itertuples():
        start_s = int(pair.dep_min_of_day) * SECONDS_PER_MIN
        meta = {"set_name": pair.set_name, "draw_no": pair.draw_no, "release": release, "error": ""}
        option_rows = []
        try:
            meta["walk_only_min"] = walk_only_min(network, pair)
            for suboptimal_min in (None, SUBOPTIMAL_WIDE_MIN):
                clock = time.perf_counter()
                options, suboptimal_used = collect_options(network, pair, suboptimal_min, stop_coords)
                walks = egress_walk_min(network, sorted({rides[-1]["alight_stop"] for rides in options.values()}),
                                        pair, stop_coords) if options else {}
                for rides in options.values():
                    walk_min = walks.get(rides[-1]["alight_stop"], np.nan)
                    option_rows.append({"set_name": pair.set_name, "draw_no": pair.draw_no, "suboptimal_min": suboptimal_used,
                                        "lines": "+".join(ride["line"] for ride in rides), "n_rides": len(rides),
                                        "first_board_s": rides[0]["board_s"], "egress_walk_min": walk_min,
                                        "option_min": (rides[-1]["alight_s"] + walk_min * SECONDS_PER_MIN - start_s) // SECONDS_PER_MIN,
                                        "rides": json.dumps(rides)})
                label = "default" if suboptimal_min is None else "wide"
                meta.update({f"suboptimal_{label}": suboptimal_used, f"n_options_{label}": len(options),
                             f"seconds_{label}": round(time.perf_counter() - clock, 1)})
        except Exception as error:                                       # recorded per pair, read after
            meta["error"] = f"{type(error).__name__}: {error}"[:300]
        if option_rows:
            pd.DataFrame(option_rows).to_csv(options_path, mode="a", header=not options_path.exists(), index=False)
        pd.DataFrame([meta]).to_csv(pairs_path, mode="a", header=not pairs_path.exists(), index=False)
        print(f"  {pair.set_name} {pair.draw_no}: walk {meta.get('walk_only_min')}, options "
              f"{meta.get('n_options_default')} / {meta.get('n_options_wide')}, s {meta.get('seconds_default')} / "
              f"{meta.get('seconds_wide')} {meta['error']}", flush=True)


def full_extract_rides():
    """Google's default (route_ix 0) rides from the full extract, keyed by (set, draw_no), first ride first."""
    rides_df = pd.read_csv(newest(GOOGLE_RIDES_GLOB))
    rides_df = rides_df[rides_df.route_ix == 0].copy()
    local = pd.to_datetime(rides_df.board_time, utc=True).dt.tz_convert(LOCAL_TZ)
    rides_df["board_s"] = local.dt.hour * 3600 + local.dt.minute * 60 + local.dt.second
    rides_df["line_norm"] = rides_df.line.map(norm_line)
    return {key: group.sort_values("board_s").to_dict("records") for key, group in rides_df.groupby(["set_name", "draw_no"])}


def as_google(rides):
    """An R5 rides list in Google's record form, so match_level can compare two R5 options."""
    return [{**ride, "line_norm": ride["line"]} for ride in rides]


def path_flags(google_rides, r5_rides):
    """transit_stop_match.py's measures for one pair (both lists non-empty)."""
    def near(g, r, end):
        return distance_m(g[f"{end}_lat"], g[f"{end}_lon"], r[f"{end}_lat"], r[f"{end}_lon"]) <= STOP_MATCH_M
    same_count = len(google_rides) == len(r5_rides)
    same_lines = same_count and all(g["line_norm"] == r["line"] for g, r in zip(google_rides, r5_rides))
    same_stops = same_count and all(near(g, r, "board") and near(g, r, "alight") for g, r in zip(google_rides, r5_rides))
    return {"first_board": near(google_rides[0], r5_rides[0], "board"), "last_alight": near(google_rides[-1], r5_rides[-1], "alight"),
            "same_count": same_count, "same_lines": same_lines, "full": same_lines and same_stops}


def sample_report():
    import json
    run_date = f"{datetime.date.today():%Y%m%d}"
    sample_df = sample_pairs()
    population = sample_df.attrs["population"]
    pairs_meta_df = pd.concat([pd.read_csv(newest(f"{NAME}_2*_{SAMPLE_TAG}_pairs_{release}.csv")) for release in SET_RELEASE.values()],
                              ignore_index=True)
    options_df = pd.concat([pd.read_csv(newest(f"{NAME}_2*_{SAMPLE_TAG}_options_{release}.csv.gz")) for release in SET_RELEASE.values()],
                           ignore_index=True)
    options_df = options_df[options_df.option_min.notna()]
    google = full_extract_rides()
    sample_df = sample_df.merge(pairs_meta_df, on=["set_name", "draw_no"], suffixes=("", "_meta"))
    level_rank = {"": 0, "lines": 1, "route": 2, "trip": 3}
    options_by_pair = {key: group for key, group in options_df.groupby(["set_name", "draw_no", "suboptimal_min"])}
    rows = []
    for pair in sample_df.itertuples():
        g_rides = [] if pair.is_walk_only else google.get((pair.set_name, pair.draw_no), [])
        row = {"set_name": pair.set_name, "draw_no": pair.draw_no, "error": pair.error if isinstance(pair.error, str) else "",
               "google_walk_only": bool(pair.is_walk_only), "google_rides_missing": not pair.is_walk_only and not g_rides,
               "google_rides": len(g_rides), "google_lines": "+".join(g["line_norm"] for g in g_rides),
               "default_min": pair.default_min, "model_min": pair.n_min, "walk_only_min": pair.walk_only_min}
        settings = {"default": pair.suboptimal_default, "wide": pair.suboptimal_wide}
        parsed = {label: [] for label in settings}
        for label, value in settings.items():
            if (pair.set_name, pair.draw_no, value) in options_by_pair:
                pair_options = options_by_pair[(pair.set_name, pair.draw_no, value)]
                parsed[label] = list(zip(pair_options.option_min, pair_options.n_rides, pair_options.first_board_s,
                                         [json.loads(rides) for rides in pair_options.rides]))
        # R5's pick: fastest option at the default value, ties to fewer rides then later boarding; walk if not slower
        best = min(parsed["default"], key=lambda o: (o[0], o[1], -o[2]), default=None)
        walk = pair.walk_only_min if not np.isnan(pair.walk_only_min) else np.inf
        is_r5_walk = best is None or walk <= best[0]
        pick_rides = [] if is_r5_walk else best[3]
        row.update({"r5_walk_only": is_r5_walk, "r5_pick_min": walk if is_r5_walk else best[0],
                    "r5_lines": "+".join(ride["line"] for ride in pick_rides), "r5_rides": len(pick_rides)})
        flag_names = ["first_board", "last_alight", "same_count", "same_lines", "full"]
        if g_rides and pick_rides:
            row.update(path_flags(g_rides, pick_rides))
        else:
            row.update(dict.fromkeys(flag_names, not g_rides and not pick_rides and not row["google_rides_missing"]))
        # post-hoc (added after the first report, Claude): whole-minute ties make the pick arbitrary among options
        # arriving in the same minute (e.g. one train boarded at either of two CBD stations); the upper bound
        # counts a match if any tied-fastest option (walk included when it ties) matches
        tied = [option[3] for option in parsed["default"] if best is not None and option[0] == min(best[0], walk)]
        tied += [[]] if walk <= (best[0] if best is not None else np.inf) else []
        row["n_tied"] = len(tied)
        for name in flag_names:
            row[f"{name}_any"] = any((path_flags(g_rides, rides)[name] if g_rides and rides else not g_rides and not rides)
                                     for rides in tied)
        for label, options in parsed.items():
            row[f"n_options_{label}"] = len(options)
            level = ""
            for option in options:
                if g_rides:
                    option_level = match_level(g_rides, option[3])
                    if level_rank[option_level] > level_rank[level]:
                        level = option_level
            if pair.is_walk_only:
                level = "trip"                                  # walk only is always available
            row[f"level_{label}"] = level
            # re-rank risk: options of another route than R5's pick
            pick_google = as_google(pick_rides)
            other_min = [option[0] for option in options
                         if not pick_rides or level_rank[match_level(pick_google, option[3])] < level_rank["route"]]
            row[f"slowest_other_min_{label}"] = max(other_min, default=np.nan)
            row[f"n_other_routes_{label}"] = len(other_min)
        rows.append(row)
    result_df = pd.DataFrame(rows)
    result_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_{SAMPLE_TAG}_results.csv", index=False)

    ok = result_df[(result_df.error == "") & ~result_df.google_rides_missing]
    lines = [f"{NAME} {run_date}, random-sample mode: path baseline on the current model (no-wait plain, v2)",
             f"population (scored, default in scope): {population}; sampled {sample_df.set_name.value_counts().to_dict()} "
             f"(seed {SAMPLE_SEED}); errors {int((result_df.error != '').sum())}; transit defaults without rides in the "
             f"extract {int(result_df.google_rides_missing.sum())}; scored here {len(ok)}",
             "R5's pick = fastest option at R5's default suboptimalMinutes vs walk only (stand-in for the time model's path)"]
    seconds = pairs_meta_df[["seconds_default", "seconds_wide"]]
    lines.append(f"run time per pair: default median {seconds.seconds_default.median():.1f} s (max {seconds.seconds_default.max():.0f}), "
                 f"wide median {seconds.seconds_wide.median():.1f} s (max {seconds.seconds_wide.max():.0f}); total "
                 f"{seconds.sum().sum() / 60:.0f} min routing")
    lines.append(f"check: R5's pick minutes - model of record (n_min): "
                 f"{(ok.r5_pick_min - ok.model_min).clip(-5, 5).value_counts().sort_index().to_dict()} (clipped at +-5)")
    for scope_label, part in [("pooled", ok)] + [(name, ok[ok.set_name == name]) for name in SET_RELEASE]:
        both = part[~part.google_walk_only & ~part.r5_walk_only]
        lines += ["", f"[{scope_label}] n {len(part)}",
                  "  walk-or-transit (rows Google, columns R5):",
                  "  " + pd.crosstab(part.google_walk_only.map({True: "walk", False: "transit"}),
                                     part.r5_walk_only.map({True: "walk", False: "transit"})).to_string().replace("\n", "\n  "),
                  f"  walk-or-transit agreement {(part.google_walk_only == part.r5_walk_only).mean():.3f}",
                  f"  both transit ({len(both)}): first boarding {both.first_board.mean():.3f}, last alighting "
                  f"{both.last_alight.mean():.3f}, same ride count {both.same_count.mean():.3f}, same lines "
                  f"{both.same_lines.mean():.3f}, full route {both.full.mean():.3f}",
                  f"  path agreement, all pairs (both walk = match): {part.full.mean():.3f}",
                  f"  upper bound, any tied-fastest option (post-hoc, Claude; tied options per pair median "
                  f"{part.n_tied.median():.0f}, max {part.n_tied.max()}): both transit first boarding "
                  f"{both.first_board_any.mean():.3f}, last alighting {both.last_alight_any.mean():.3f}, same ride count "
                  f"{both.same_count_any.mean():.3f}, same lines {both.same_lines_any.mean():.3f}, full route "
                  f"{both.full_any.mean():.3f}; all pairs path {part.full_any.mean():.3f}"]
        for label in ("default", "wide"):
            transit_part = part[~part.google_walk_only]
            lines.append(f"  ceiling at suboptimalMinutes {SUBOPTIMAL_WIDE_MIN if label == 'wide' else 'default'}: "
                         f"route-level coverage {part[f'level_{label}'].isin(['route', 'trip']).mean():.3f} "
                         f"(trip {(part[f'level_{label}'] == 'trip').mean():.3f}); transit defaults only: route "
                         f"{transit_part[f'level_{label}'].isin(['route', 'trip']).mean():.3f}, trip "
                         f"{(transit_part[f'level_{label}'] == 'trip').mean():.3f}; options per pair median "
                         f"{part[f'n_options_{label}'].median():.0f} (max {part[f'n_options_{label}'].max()})")
    lines += ["", "re-rank risk (pooled):"]
    for label in ("default", "wide"):
        correct = ok[ok.full]
        lines.append(f"  suboptimal {label}: path-correct pairs {len(correct)}, with a distinct option of another route "
                     f"{int((correct[f'n_other_routes_{label}'] > 0).sum())}")
        for cut in CUTS_MIN.values():
            in_reach = ok[(ok.r5_pick_min <= cut) & (ok.default_min <= cut)]
            at_risk = in_reach[in_reach[f"slowest_other_min_{label}"] > cut]
            lines.append(f"    cut {cut}: R5 and Google both <= cut {len(in_reach)}; with another-route option > cut "
                         f"{len(at_risk)} (a re-rank picking it would lose reach)")
    wide_coverage = ok.level_wide.isin(["route", "trip"]).mean()
    lines += ["", f"rule (user): path stays closed unless route-level coverage >= {COVERAGE_RULE}: coverage at "
              f"suboptimalMinutes {SUBOPTIMAL_WIDE_MIN} {wide_coverage:.3f}: "
              + ("MET (path may reopen)" if wide_coverage >= COVERAGE_RULE else "NOT MET (path stays closed)"),
              f"extend rule (Claude's): coverage inside {EXTEND_BAND} -> extend the routed subset: "
              + ("EXTEND" if EXTEND_BAND[0] <= wide_coverage <= EXTEND_BAND[1] else "no extension needed"),
              "no time verdict (user)."]
    lines += ["", "examples, both transit, full route not matched (first 15): Google lines | R5 lines | default / pick min"]
    for row in ok[~ok.google_walk_only & ~ok.r5_walk_only & ~ok.full].head(15).itertuples():
        lines.append(f"  {row.set_name} {row.draw_no}: {row.google_lines} | {row.r5_lines} | {row.default_min:.0f} / {row.r5_pick_min:.0f}"
                     f" | levels {row.level_default or 'none'} / {row.level_wide or 'none'}")
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_{SAMPLE_TAG}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")


def sample_rank():
    """Google's default's rank among R5's distinct routes, fastest first, at both suboptimalMinutes values."""
    import json
    run_date = f"{datetime.date.today():%Y%m%d}"
    sample_df = sample_pairs().merge(pd.concat([pd.read_csv(newest(f"{NAME}_2*_{SAMPLE_TAG}_pairs_{release}.csv"))
                                                for release in SET_RELEASE.values()]), on=["set_name", "draw_no"])
    options_df = pd.concat([pd.read_csv(newest(f"{NAME}_2*_{SAMPLE_TAG}_options_{release}.csv.gz")) for release in SET_RELEASE.values()],
                           ignore_index=True)
    options_df = options_df[options_df.option_min.notna()]
    options_by_pair = {key: group for key, group in options_df.groupby(["set_name", "draw_no", "suboptimal_min"])}
    google = full_extract_rides()
    rows = []
    for pair in sample_df.itertuples():
        g_rides = [] if pair.is_walk_only else google[(pair.set_name, pair.draw_no)]
        walk = pair.walk_only_min if not np.isnan(pair.walk_only_min) else np.inf
        for label, value in (("default", pair.suboptimal_default), ("wide", pair.suboptimal_wide)):
            routes = {}                                  # route key -> (fastest minutes, rides)
            pair_options = options_by_pair.get((pair.set_name, pair.draw_no, value))
            if pair_options is not None:
                for option_min, rides_json in zip(pair_options.option_min, pair_options.rides):
                    rides = json.loads(rides_json)
                    key = tuple((ride["line"], ride["board_stop"], ride["alight_stop"]) for ride in rides)
                    if key not in routes or option_min < routes[key][0]:
                        routes[key] = (option_min, rides)
            candidates = sorted([(minutes, rides) for minutes, rides in routes.values()] + [(walk, [])], key=lambda c: c[0])
            matched = [i for i, (minutes, rides) in enumerate(candidates)
                       if (not g_rides and not rides) or (g_rides and rides and match_level(g_rides, rides) in ("route", "trip"))]
            row = {"set_name": pair.set_name, "draw_no": pair.draw_no, "setting": label, "n_routes": len(candidates)}
            if matched:
                match_min = candidates[matched[0]][0]
                row.update({"rank_best": 1 + sum(c[0] < match_min for c in candidates),
                            "rank_worst": sum(c[0] <= match_min for c in candidates) - sum(
                                c[0] == match_min for i, c in enumerate(candidates) if i in matched[1:]),
                            "match_min": match_min, "fastest_min": candidates[0][0]})
            rows.append(row)
    rank_df = pd.DataFrame(rows)
    rank_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_{SAMPLE_TAG}_rank.csv", index=False)
    lines = [f"{NAME} {run_date}, rank mode: Google's default among R5's distinct routes, fastest first ({len(sample_df)} pairs)"]
    for label, part in rank_df.groupby("setting", sort=False):
        lines += ["", f"suboptimalMinutes {SUBOPTIMAL_WIDE_MIN if label == 'wide' else 'default'}: distinct routes per pair "
                      f"median {part.n_routes.median():.0f} (max {part.n_routes.max()}); Google's route found on "
                      f"{part.rank_best.notna().mean():.3f}"]
        for name, column in (("best (ties in Google's favour)", "rank_best"), ("worst (ties against)", "rank_worst")):
            shares = ", ".join(f"<= {n}: {(part[column] <= n).mean():.3f}" for n in RANKS_REPORTED)
            lines.append(f"  {name}: cumulative share {shares}; median rank among found {part[column].median():.0f}")
        found = part[part.rank_best.notna()]
        lines.append(f"  Google's route minus fastest route, minutes (found): median "
                     f"{(found.match_min - found.fastest_min).median():.0f}, p75 {(found.match_min - found.fastest_min).quantile(0.75):.0f}, "
                     f"p90 {(found.match_min - found.fastest_min).quantile(0.9):.0f}")
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_{SAMPLE_TAG}_rank_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "sample_rank":
        sample_rank()
        sys.exit()
    if mode == "sample_route":
        sys.argv += ["--max-memory", R5_MAX_MEMORY]
        sample_route(sys.argv[2])
        sys.exit()
    if mode == "sample_report":
        sample_report()
        sys.exit()
    if mode != "report":
        sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import
    if mode == "explore":
        explore(sys.argv[2])
    elif mode == "route":
        route(sys.argv[2])
    else:
        report()
