"""Does a walk weight, or a boarding/transfer penalty, bring R5 closer to Google's default transit route?

Claim under test (concepts/transit.md T7 a-c, f; DESIGN.md Q22): R5 returns the fastest trip, Google trades
time mainly for less walking (diagnostics/transit_default_route.py: walk weight ~2 explains 0.945 of Google's
defaults, boarding/transfer penalties alone nothing). Where the pipeline would rely on it: the transit
router's route choice for the reachability bands (RCH-1, SCR-1).

Implementation in R5 (read from TTM's path results, 2026-10-17 probe): R5 minimises arrival only, so a walk
weight w is applied as walking at WALK_SPEED_KMH / w for every walk (access, transfers, egress). Riding the
same vehicles, walking faster before boarding only lengthens the waits, so the true time of the route R5
picks is its slowed time minus (1 - 1/w) x its final (egress) walk. This is "routes still makeable at a
slower pace", not OpenTripPlanner's generalised cost (each walk minute counted w times); the two agree
on egress and on missed connections, not on access walks absorbed by a wait. Stated, not corrected.
Boardings: TTM with the ride cap c in RIDE_CAPS (R5 maxRides) gives the fastest route with at most c rides
and its path (rides k <= c, egress s); walk-only seconds W from one pairwise DetailedItineraries walk call
at WALK_SPEED_KMH (slowed walk-only = w x W). Per pair, R5's choice among {walk only, each cap's route} is
the least of slowed time + beta * [k >= 1] + tau * max(k - 1, 0) (ties to fewer rides); the prediction is
that route's true time.

Target (T7 f, recommended by Claude 2026-10-17, taken with the plan): Google's default route's arrival
from the requested departure (arrival_from_request_s). Scored pairs: training half (half == "train"), the
default route in scope (TRN-11), R5 result present. Error = R5 - Google (min).

Arms (user, 2026-10-17), all at WALK_SPEED_KMH, stock R5 (60 s board slack kept as a bias):
  B  baseline: w = 1, beta = tau = 0 (stock R5).
  C  control: OpenTripPlanner's defaults, w = 2 (walkReluctance), transfer penalty 0, no boarding penalty.
  F  fitted from Google's choices (transit_default_route.py's method: Google's own routes, cost
     arrival + (w - 1) x walk time + penalties, hit share maximised) on the 4 other CV folds of the training
     half, w on W_GRID, beta and tau 0..PENALTY_MAX_S in FIT_STEP_S; applied to the held-out fold.
  E1 exploratory: beta, tau only (w = 1), fitted on R5's error (MAE) on the 4 other folds.
  E2 exploratory: w, beta, tau fitted on R5's error on the 4 other folds (R5_FIT_STEP_S grid).
B and C have nothing fitted: scored on all scored pairs. F, E1, E2: pooled held-out predictions.

Rule (set with the user before the run, 2026-10-17):
  An arm PASSES against B if its mean absolute error is at least MAE_GAIN_MIN lower than B's AND neither
  band's share (whole-minute times <= 10 / <= 20 min; DESIGN.md Cross-cutting positions) moves by more
  than BAND_MOVE_PP percentage points from B's. Otherwise FAILS. Applied to C and F (E1, E2 reported, no
  verdict). F replaces C only if F passes the same rule against C; otherwise C stands (if C passes) or
  neither is adopted. F's values lie inside Google's range by construction; E2's are checked against it.
  Also reported, no verdict: each arm's band shares beside Google's (the literal rule caps the move from
  B, whichever direction it goes; a move toward Google beyond 2 pp would fail it and is flagged).
Sanity gates (must hold, else no verdict): G1 w = 1 uncapped: TTM's whole minutes = floor(min(R5 transit
seconds, W) / 60) within GATE_MIN_TOLERANCE on >= GATE_SHARE of pairs; G2 pairs whose w = 1 and w = 2
uncapped routes are the same (lines, board and alight stops) and reach the last stop at the same time: true
times within GATE_SAME_ROUTE_S on >= GATE_SHARE (checks R5's speed parameter on the egress walk). Deviation,
set by Claude after the 60-pair smoke test and before the full run: G2 first compared lines and stops only
and failed (0.615 of 13); at the slower walk R5 often takes a later vehicle of the same line, a different
trip, so the last-stop time was added. Same-line later trips are counted and reported.

Conclusion (run 2026-10-17, resumed from 100 of 1,252 pairs; 1,246 scored): gates passed (G1 0.995, G2 1.000
on 191 pairs; path departure = requested minute 1.000). C FAILS against B (MAE 8.65 vs 5.26 min, gain -3.39;
band 2 -5.38 pp); F FAILS against B (8.71, gain -3.45; band 2 -5.22 pp; w 2.0 on every fold, beta 30-80 s,
tau 440-480 s) and against C (gain -0.06). Stock R5 (B) stands. The walk weight as slowed walking makes R5
late (median +4 min): routes still makeable at half pace are not Google's routes. OpenTripPlanner-style
generalised cost (each walk minute counted w times) is NOT tested by this; it needs a router that
minimises cost, not arrival (open). Exploratory: E1 = E2 (w 1, beta 0-30 s, tau 360-510 s) gain +0.07 min,
nothing. B is early on Google's default (mean -3.04, median -0.23 min); only +0.75 min of that is Google's
preference (default minus its earliest in-scope route); the rest is a tail: 29 pairs off by > 20 min (24 R5
early, Google's first wait median 19 min, 13 at night) where R5 walks or rides while Google waits for a
later service. Without the tail, B's MAE is 3.29 min (mean -1.26, median -0.22). Verdicts are by the user's
rule; the tail breakdown was added after the run (exploratory, no verdict).

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release), the OSM
extract in frozen_inputs/osm_extract/, the transit pairs, split and Google route table in
outputs/transit_validation/. Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1).
No paid API calls; r5py only. Saved data (per pair R5 routes on the w x cap grid; walk-only seconds) is
reused if it exists, newest first, and says so; a partial routes file is resumed. Results carry the run
date; a same-day rerun replaces that day's results. The test half is not read.
"""
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
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
GOOGLE_ROUTES_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_preference_arms"
ROUTES_SUFFIX = "_routes.csv"                  # saved data: R5 per pair, w and cap
WALK_SUFFIX = "_walk.csv"                      # saved data: walk-only seconds per pair

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_di_window.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
WALK_SPEED_KMH = 4.16                          # config.WALK_SPEED_KMH (WLK-1)
SINGLE_PERCENTILE = 49                         # as transit_di_window.py (r5py renames a lone p50)
MAX_TIME_MIN = 120                             # room for slowed walking (window pairs are <= 40 min)
TRAIN_HALF = "train"
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]   # TRN-11
BAND_LIMITS_MIN = {"band_1": 10, "band_2": 20}  # walk + PT <= 600 s, <= 1,200 s
SECONDS_PER_MIN = 60
MIN_PER_HOUR = 60
M_PER_KM = 1000
S_PER_HOUR = 3600

# --- grid ------------------------------------------------------------------------------------------
W_GRID = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]   # walk weights routed (transit_default_route.py's range)
CONTROL_W = 2.0                                # OpenTripPlanner walkReluctance default
RIDE_CAPS = [1, 2, 8]                          # 8 = r5py's default maxRides (uncapped in practice)
UNCAPPED = 8
PENALTY_MAX_S = 15 * SECONDS_PER_MIN           # T7 (b)'s grid, 0-15 min
FIT_STEP_S = 10                                # F's grid (Google's choices)
R5_FIT_STEP_S = 30                             # E1 / E2 grid (R5's error)
CHECKPOINT_EVERY = 50                          # pairs per append to the routes file
TIE_S_PER_RIDE = 1e-6                          # cost tie-break: fewer rides win
WALK_ONLY_HOUR = 12                            # walk-only departure hour (time does not matter)
GEOGRAPHIC_CRS = "EPSG:4326"

# --- rule and gates --------------------------------------------------------------------------------
MAE_GAIN_MIN = 0.5                             # user, 2026-10-17
BAND_MOVE_PP = 2.0                             # user, 2026-10-17 (as transit_board_slack.py)
GOOGLE_RANGE_PP = 1.0                          # Google's range: cells within 1 pp of the best hit share
GATE_SHARE = 0.98
GATE_MIN_TOLERANCE = 1
GATE_SAME_ROUTE_S = 10
CLOSE_MIN = 1                                  # reported: |error| <= 1 min
FAR_MIN = 3                                    # reported: 3+ min late or early
TAIL_MIN = 20                                  # exploratory: |B - Google| beyond this is the tail (added after the run)
NIGHT_HOURS = (6, 22)                          # exploratory: departures before the first or from the second hour count as night

sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import


# === routing (saved data) ==========================================================================
def newest(suffix):
    files = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*{suffix}"))
    return files[-1] if files else None


_network = []                                 # the one r5py TransportNetwork, built on first use


def transport_network():
    if not _network:
        from r5py import TransportNetwork
        _network.append(TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES]))
    return _network[0]


def path_summary(result):
    """Fastest transit route in a TTM result with path results: total s, rides, egress s, identity."""
    templates = result.paths.iterationsForPathTemplates[0] if result.paths is not None else None
    best = None
    if templates is not None:
        for route_sequence in templates.keySet():
            if route_sequence.stopSequence.boardStops is None:    # R5's direct-walk template: walk handled apart
                continue
            for iteration in templates.get(route_sequence):
                if best is None or iteration.totalTime < best[1].totalTime:
                    best = (route_sequence, iteration)
    if best is None:
        return {"transit_s": np.nan, "rides": np.nan, "egress_s": np.nan, "access_s": np.nan,
                "dep_s": np.nan, "route_id": ""}
    route_sequence, iteration = best
    stops = route_sequence.stopSequence
    routes = "+".join(str(int(route)) for route in route_sequence.routes.toArray())
    boards = "+".join(str(int(stop)) for stop in stops.boardStops.toArray())
    alights = "+".join(str(int(stop)) for stop in stops.alightStops.toArray())
    return {"transit_s": int(iteration.totalTime), "rides": int(stops.boardStops.size()),
            "egress_s": int(stops.egress.time) if stops.egress is not None else 0,
            "access_s": int(stops.access.time) if stops.access is not None else 0,
            "dep_s": int(iteration.departureTime), "route_id": f"{routes}|{boards}|{alights}"}


def route_pairs(pairs_df, routes_path):
    """TTM with path results per pair, w in W_GRID, cap in RIDE_CAPS; appended to routes_path, resumable."""
    import geopandas as gpd
    from r5py import TransportMode
    from r5py.r5.regional_task import RegionalTask
    import com.conveyal.r5  # importable once r5py has started the JVM

    done = set(pd.read_csv(routes_path, usecols=["draw_no"]).draw_no) if routes_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"routing {len(todo_df)} pairs ({len(done)} already in {routes_path.name})", flush=True)
    if todo_df.empty:
        return
    network = transport_network()
    rows = []
    for i, pair in enumerate(todo_df.itertuples(index=False), start=1):
        origin = gpd.points_from_xy([pair.origin_lon], [pair.origin_lat], crs=GEOGRAPHIC_CRS)[0]
        destination = gpd.GeoDataFrame({"id": [1]}, crs=GEOGRAPHIC_CRS,
                                       geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
        departure = (datetime.datetime.combine(WINDOW_DATE, datetime.time())
                     + datetime.timedelta(minutes=int(pair.dep_min_of_day)))
        for walk_weight in W_GRID:
            for cap in RIDE_CAPS:
                request = RegionalTask(
                    network, origin=origin, destinations=destination, departure=departure,
                    departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
                    transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
                    max_time=datetime.timedelta(minutes=MAX_TIME_MIN),
                    max_time_walking=datetime.timedelta(minutes=MAX_TIME_MIN),
                    speed_walking=WALK_SPEED_KMH / walk_weight, max_public_transport_rides=cap)
                request._regional_task.includePathResults = True
                result = com.conveyal.r5.analyst.TravelTimeComputer(request, network).computeTravelTimes()
                ttm_min = result.travelTimes.getValues()[0][0]
                rows.append({"draw_no": pair.draw_no, "walk_weight": walk_weight, "cap": cap,
                             "ttm_min": ttm_min, "request_s": int(pair.dep_min_of_day) * SECONDS_PER_MIN,
                             **path_summary(result)})
        if i % CHECKPOINT_EVERY == 0 or i == len(todo_df):
            chunk_df = pd.DataFrame(rows)
            chunk_df.to_csv(routes_path, mode="a", header=not routes_path.exists(), index=False)
            rows = []
            print(f"  {i}/{len(todo_df)} pairs", flush=True)


def walk_only_seconds(pairs_df, walk_path):
    """Walk-only seconds per pair at WALK_SPEED_KMH, one pairwise DetailedItineraries walk call."""
    import geopandas as gpd
    from r5py import DetailedItineraries, TransportMode
    network = transport_network()
    origins = gpd.GeoDataFrame({"id": pairs_df.draw_no.values}, crs=GEOGRAPHIC_CRS,
                               geometry=gpd.points_from_xy(pairs_df.origin_lon, pairs_df.origin_lat))
    destinations = gpd.GeoDataFrame({"id": pairs_df.draw_no.values}, crs=GEOGRAPHIC_CRS,
                                    geometry=gpd.points_from_xy(pairs_df.dest_lon, pairs_df.dest_lat))
    departure = datetime.datetime.combine(WINDOW_DATE, datetime.time(WALK_ONLY_HOUR))   # walk-only: time does not matter
    di_df = pd.DataFrame(DetailedItineraries(network, origins=origins, destinations=destinations, departure=departure,
                                             transport_modes=[TransportMode.WALK], speed_walking=WALK_SPEED_KMH,
                                             max_time=datetime.timedelta(minutes=MAX_TIME_MIN)))
    walk_df = di_df.groupby("from_id").agg(walk_s=("travel_time", "sum")).reset_index()
    walk_df["walk_s"] = walk_df.walk_s.dt.total_seconds()
    walk_df.rename(columns={"from_id": "draw_no"}).to_csv(walk_path, index=False)


# === choice and scoring ============================================================================
def candidate_arrays(routes_df, walk_s, draw_nos):
    """Per w: slowed cost, true time and rides, pairs x (walk, caps...) arrays (NaN cost: no route)."""
    arrays = {}
    for walk_weight in W_GRID:
        costs, trues, rides = [walk_weight * walk_s], [walk_s], [np.zeros_like(walk_s)]
        for cap in RIDE_CAPS:
            cap_df = (routes_df[(routes_df.walk_weight == walk_weight) & (routes_df.cap == cap)]
                      .set_index("draw_no").reindex(draw_nos))
            transit_s = cap_df.transit_s.to_numpy(float) - cap_df.request_s.to_numpy(float) + cap_df.dep_s.to_numpy(float)
            costs.append(transit_s)
            trues.append(transit_s - (1 - 1 / walk_weight) * cap_df.egress_s.to_numpy(float))
            rides.append(cap_df.rides.to_numpy(float))
        cost = np.column_stack(costs)
        arrays[walk_weight] = (np.where(np.isnan(cost), np.inf, cost), np.column_stack(trues),
                               np.nan_to_num(np.column_stack(rides)))
    return arrays


def predict(arrays, walk_weight, beta_s, tau_s):
    """True seconds of R5's choice per pair for one (w, beta, tau)."""
    cost, true_s, rides = arrays[walk_weight]
    total = cost + beta_s * (rides >= 1) + tau_s * np.maximum(rides - 1, 0) + rides * TIE_S_PER_RIDE   # ties: fewer rides
    choice = np.argmin(total, axis=1)
    return true_s[np.arange(len(choice)), choice]


def r5_grid_fit(arrays, target_s, rows, walk_weights, step_s):
    """(w, beta, tau) with the least MAE on the given rows."""
    grid_s = np.arange(0, PENALTY_MAX_S + 1, step_s, dtype=float)
    best = (np.inf, None)
    for walk_weight in walk_weights:
        cost, true_s, rides = arrays[walk_weight]
        cost, true_s, rides = cost[rows], true_s[rows], rides[rows]
        has_ride, n_transfers = (rides >= 1), np.maximum(rides - 1, 0)
        for beta_s in grid_s:
            total = (cost + beta_s * has_ride + rides * TIE_S_PER_RIDE)[:, :, None] + n_transfers[:, :, None] * grid_s[None, None, :]
            choice = np.argmin(total, axis=1)                                     # pairs x taus
            picked = np.take_along_axis(true_s[:, :, None].repeat(len(grid_s), 2), choice[:, None, :], 1)[:, 0, :]
            mae = np.abs(picked - target_s[rows, None]).mean(axis=0)
            if mae.min() < best[0]:
                best = (mae.min(), (walk_weight, beta_s, grid_s[mae.argmin()]))
    return best[1]


def google_hit_shares(google_df, walk_weights, step_s):
    """transit_default_route.py's method: per (w, beta, tau), share of pairs whose default is the least
    of arrival + (w - 1) x walk time + penalties (random tie-break). Returns cells_df with hit_share."""
    google_df = google_df.sort_values(["draw_no", "route_ix"]).reset_index(drop=True)
    starts = np.flatnonzero(google_df.draw_no.ne(google_df.draw_no.shift()).to_numpy())
    pair_of_route = np.cumsum(np.isin(np.arange(len(google_df)), starts)) - 1
    walk_s = google_df.walk_m.to_numpy() / (WALK_SPEED_KMH * M_PER_KM / S_PER_HOUR)
    boardings = google_df.n_transit_steps.to_numpy()
    is_default = google_df.is_default.to_numpy(bool)
    grid_s = np.arange(0, PENALTY_MAX_S + 1, step_s, dtype=float)
    cells = []
    for walk_weight in walk_weights:
        base = google_df.arrival_from_request_s.to_numpy(float) + (walk_weight - 1) * walk_s
        for tau_s in grid_s:
            costs = (base[:, None] + (boardings >= 1)[:, None] * grid_s[None, :]
                     + (np.maximum(boardings - 1, 0) * tau_s)[:, None])
            pair_min = np.minimum.reduceat(costs, starts, axis=0)
            is_min = costs <= pair_min[pair_of_route]
            n_min = np.add.reduceat(is_min.astype(np.int32), starts, axis=0)
            default_is_min = np.add.reduceat(is_min & is_default[:, None], starts, axis=0) > 0
            shares = (default_is_min / n_min).mean(axis=0)
            cells += [(walk_weight, beta_s, tau_s, share) for beta_s, share in zip(grid_s, shares)]
    return pd.DataFrame(cells, columns=["walk_weight", "beta_s", "tau_s", "hit_share"])


def multi_route(google_df):
    n_routes = google_df.groupby("draw_no").draw_no.transform("size")
    return google_df[n_routes >= 2]


def band_shares_pp(seconds):
    minutes = np.round(seconds / SECONDS_PER_MIN)
    return {band: 100 * float((minutes <= limit).mean()) for band, limit in BAND_LIMITS_MIN.items()}


def arm_stats(pred_s, target_s):
    error_min = (pred_s - target_s) / SECONDS_PER_MIN
    return {"mae_min": float(np.abs(error_min).mean()), "mean_min": float(error_min.mean()),
            "close_share": float((np.abs(error_min) <= CLOSE_MIN).mean()),
            "late_far": int((error_min >= FAR_MIN).sum()), "early_far": int((error_min <= -FAR_MIN).sum()),
            **band_shares_pp(pred_s)}


def verdict(arm, reference):
    gain = reference["mae_min"] - arm["mae_min"]
    moves = {band: arm[band] - reference[band] for band in BAND_LIMITS_MIN}
    is_pass = gain >= MAE_GAIN_MIN and all(abs(move) <= BAND_MOVE_PP for move in moves.values())
    return ("PASS" if is_pass else "FAIL"), gain, moves


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    out_prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}"
    split_df = pd.read_csv(SPLIT_PATH)
    train_df = split_df[split_df.half == TRAIN_HALF][["draw_no", "fold"]]
    pairs_df = pd.read_csv(PAIRS_PATH).merge(train_df, on="draw_no").sort_values("draw_no").reset_index(drop=True)

    routes_path = newest(ROUTES_SUFFIX) or Path(f"{out_prefix}{ROUTES_SUFFIX}")
    walk_path = newest(WALK_SUFFIX)
    lines = [f"{NAME} run {run_date}"]
    if walk_path is None:
        walk_path = Path(f"{out_prefix}{WALK_SUFFIX}")
        walk_only_seconds(pairs_df, walk_path)
    else:
        lines.append(f"reusing walk-only seconds {walk_path.name}")
    route_pairs(pairs_df, routes_path)
    lines.append(f"routes from {routes_path.name}")

    routes_df = pd.read_csv(routes_path)
    walk_s = pairs_df[["draw_no"]].merge(pd.read_csv(walk_path), on="draw_no", how="left").walk_s.to_numpy(float)
    draw_nos = pairs_df.draw_no.to_numpy()
    arrays = candidate_arrays(routes_df, walk_s, draw_nos)

    # gates
    uncapped_1 = routes_df[(routes_df.walk_weight == 1.0) & (routes_df.cap == UNCAPPED)].set_index("draw_no").reindex(draw_nos)
    uncapped_2 = routes_df[(routes_df.walk_weight == CONTROL_W) & (routes_df.cap == UNCAPPED)].set_index("draw_no").reindex(draw_nos)
    transit_1 = (uncapped_1.transit_s - uncapped_1.request_s + uncapped_1.dep_s).to_numpy(float)
    expected_min = np.floor(np.fmin(np.where(np.isnan(transit_1), np.inf, transit_1), walk_s) / SECONDS_PER_MIN)
    g1_share = float((np.abs(uncapped_1.ttm_min.to_numpy(float) - expected_min) <= GATE_MIN_TOLERANCE).mean())
    is_same_line = (uncapped_1.route_id.fillna("").to_numpy() == uncapped_2.route_id.fillna("").to_numpy()) \
        & (uncapped_1.route_id.fillna("").to_numpy() != "")
    last_stop_1 = (uncapped_1.transit_s - uncapped_1.egress_s - uncapped_1.request_s + uncapped_1.dep_s).to_numpy(float)
    last_stop_2 = (uncapped_2.transit_s - uncapped_2.egress_s - uncapped_2.request_s + uncapped_2.dep_s).to_numpy(float)
    is_same = is_same_line & (last_stop_1 == last_stop_2)
    true_1, true_2 = arrays[1.0][1][:, -1], arrays[CONTROL_W][1][:, -1]
    g2_share = float((np.abs(true_1 - true_2)[is_same] <= GATE_SAME_ROUTE_S).mean())
    dep_matches = float((uncapped_1.dep_s == uncapped_1.request_s)[uncapped_1.route_id.fillna("") != ""].mean())
    is_gated = g1_share >= GATE_SHARE and g2_share >= GATE_SHARE
    lines += [f"G1 TTM minutes = floor(min(transit, walk)) within {GATE_MIN_TOLERANCE} min: {g1_share:.3f}",
              f"same lines and stops at w 1 and {CONTROL_W}: {int(is_same_line.sum())}, of which a later trip at "
              f"w {CONTROL_W}: {int((is_same_line & (last_stop_2 > last_stop_1)).sum())}",
              f"G2 same route and last-stop time at w 1 and {CONTROL_W} ({int(is_same.sum())} pairs): true times within "
              f"{GATE_SAME_ROUTE_S} s {g2_share:.3f}",
              f"path departure = requested minute: {dep_matches:.3f}",
              "gates " + ("passed" if is_gated else "FAILED: no verdict"), ""]

    # scored pairs
    google_df = pd.read_csv(GOOGLE_ROUTES_PATH)
    google_df = google_df[google_df.draw_no.isin(draw_nos)]
    default_df = google_df[google_df.is_default].set_index("draw_no").reindex(draw_nos)
    target_s = default_df.arrival_from_request_s.to_numpy(float)
    is_scored = default_df.route_scope.isin(GOOGLE_SCOPES).to_numpy() & ~np.isnan(target_s) \
        & np.isfinite(predict(arrays, 1.0, 0, 0))
    folds = pairs_df.fold.to_numpy()
    lines.append(f"training pairs {len(draw_nos)}; scored (default in scope, R5 present) {int(is_scored.sum())}")

    predictions = {"B": predict(arrays, 1.0, 0, 0), "C": predict(arrays, CONTROL_W, 0, 0)}
    fitted = {"F": [], "E1": [], "E2": []}
    held_out = {arm: np.full(len(draw_nos), np.nan) for arm in fitted}
    for fold in np.unique(folds):
        fit_rows = is_scored & (folds != fold)
        test_rows = folds == fold
        fold_google_df = multi_route(google_df[google_df.draw_no.isin(draw_nos[folds != fold])])
        cells_df = google_hit_shares(fold_google_df, W_GRID, FIT_STEP_S)
        best = cells_df.loc[cells_df.hit_share.idxmax()]
        params = {"F": (best.walk_weight, best.beta_s, best.tau_s),
                  "E1": r5_grid_fit(arrays, target_s, fit_rows, [1.0], R5_FIT_STEP_S),
                  "E2": r5_grid_fit(arrays, target_s, fit_rows, W_GRID, R5_FIT_STEP_S)}
        for arm, (walk_weight, beta_s, tau_s) in params.items():
            fitted[arm].append((int(fold), float(walk_weight), float(beta_s), float(tau_s)))
            held_out[arm][test_rows] = predict(arrays, walk_weight, beta_s, tau_s)[test_rows]
    predictions.update(held_out)

    # Google's range on the whole training half (for E2's check)
    all_cells_df = google_hit_shares(multi_route(google_df), W_GRID, FIT_STEP_S)
    in_range_df = all_cells_df[all_cells_df.hit_share >= all_cells_df.hit_share.max() - GOOGLE_RANGE_PP / 100]
    in_range = set(map(tuple, in_range_df[["walk_weight", "beta_s", "tau_s"]].to_numpy()))
    lines.append(f"Google's range (whole training half, within {GOOGLE_RANGE_PP} pp of best "
                 f"{all_cells_df.hit_share.max():.3f}): {len(in_range_df)} cells; w "
                 f"{sorted(float(w) for w in in_range_df.walk_weight.unique())}, beta {in_range_df.beta_s.min():.0f}-"
                 f"{in_range_df.beta_s.max():.0f} s, tau {in_range_df.tau_s.min():.0f}-{in_range_df.tau_s.max():.0f} s")
    for arm, values in fitted.items():
        lines.append(f"{arm} per fold (fold, w, beta s, tau s): {values}")
    e2_in = [(w, b, t) in in_range for _, w, b, t in fitted["E2"]]
    lines.append(f"E2 folds inside Google's range: {sum(e2_in)} of {len(e2_in)}")

    stats = {arm: arm_stats(pred[is_scored], target_s[is_scored]) for arm, pred in predictions.items()}
    stats["Google"] = band_shares_pp(target_s[is_scored])
    stats_df = pd.DataFrame(stats).T
    lines += ["", stats_df.round(3).to_string(), ""]
    for arm, reference in [("C", "B"), ("F", "B"), ("F", "C"), ("E1", "B"), ("E2", "B")]:
        result, gain, moves = verdict(stats[arm], stats[reference])
        label = result if arm in ("C", "F") else f"(exploratory) {result}"
        to_google = {band: abs(stats[arm][band] - stats["Google"][band]) - abs(stats[reference][band] - stats["Google"][band])
                     for band in BAND_LIMITS_MIN}
        lines.append(f"{arm} vs {reference}: {label if is_gated else 'no verdict (gates)'}; MAE gain {gain:+.3f} min; "
                     f"band moves {', '.join(f'{b} {m:+.2f} pp' for b, m in moves.items())}; distance to Google's "
                     f"share changes {', '.join(f'{b} {m:+.2f} pp' for b, m in to_google.items())}")

    # exploratory, added after the run (no verdict): how much of B's error is Google's preference, and the tail
    best_in_s = (google_df[google_df.route_scope.isin(GOOGLE_SCOPES)].groupby("draw_no").arrival_from_request_s.min()
                 .reindex(draw_nos).to_numpy(float))
    first_wait_min = default_df.leave_wait_s.to_numpy(float) / SECONDS_PER_MIN
    error_b_min = (predictions["B"] - target_s) / SECONDS_PER_MIN
    is_tail = np.abs(error_b_min) > TAIL_MIN
    error_best_min = ((predictions["B"] - best_in_s) / SECONDS_PER_MIN)[is_scored]
    lines += ["", "exploratory (added after the run, no verdict):",
              f"B vs Google's earliest in-scope route (not its default): mean {error_best_min.mean():+.2f}, median "
              f"{np.median(error_best_min):+.2f}, MAE {np.abs(error_best_min).mean():.2f} min; default minus earliest: "
              f"mean {np.nanmean(((target_s - best_in_s) / SECONDS_PER_MIN)[is_scored]):+.2f} min",
              f"tail |B - Google| > {TAIL_MIN} min: {int((is_tail & is_scored).sum())} pairs, R5 early on "
              f"{int((is_tail & is_scored & (error_b_min < 0)).sum())}; Google's first wait median "
              f"{np.nanmedian(first_wait_min[is_tail & is_scored]):.1f} min (all scored "
              f"{np.nanmedian(first_wait_min[is_scored]):.1f}); departures before {NIGHT_HOURS[0]}:00 or from {NIGHT_HOURS[1]}:00 "
              f"{int((is_tail & is_scored & ((pairs_df.dep_min_of_day < NIGHT_HOURS[0] * MIN_PER_HOUR) | (pairs_df.dep_min_of_day >= NIGHT_HOURS[1] * MIN_PER_HOUR)).to_numpy()).sum())}"]
    for arm in predictions:
        error_min = ((predictions[arm] - target_s) / SECONDS_PER_MIN)[is_scored & ~is_tail]
        lines.append(f"  {arm} without the tail ({len(error_min)}): MAE {np.abs(error_min).mean():.2f}, mean "
                     f"{error_min.mean():+.2f}, median {np.median(error_min):+.2f} min")

    pd.DataFrame({"draw_no": draw_nos, "fold": folds, "is_scored": is_scored, "google_s": target_s, "walk_s": walk_s,
                  **{f"pred_{arm}_s": pred for arm, pred in predictions.items()}}).to_csv(f"{out_prefix}_pairs.csv", index=False)
    summary = "\n".join(lines)
    Path(f"{out_prefix}_summary.txt").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
