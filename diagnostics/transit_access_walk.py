"""H-walk: is R5's walk to Google's first boarding stop longer than Google's, and does that go with R5's late misses?

Claims under test (concepts/walk.md WLK-1, WLK-3; concepts/transit.md TRN-13, T7 (e); HANDOFF 2026-10-20, musings
2026-10-20 "Walking as the hidden lever"): walking speed is fitted to ~0 bias on walk-only trips (WLK-1), so if the
model's walk is off inside transit trips it is the access path (street path, stop linking, pathways), not the speed.
The 1.14x figure (transit_router_egress.py C2) came from 25 selected late pairs; this test is on every usable pair.
Where the pipeline would rely on it: transit bands 1-2 (SCR-1, RCH-1) through the model of record (TRN-13: no-wait
at plain cuts on the pathways v2 network, 4.16 km/h). Outcome either way (user): a stated limitation with its size,
or walk ruled out; no OSM edits toward Google, no global factor.

Pairs: the training half, the second batch and the top-up (scored pairs of the own-date range scoring,
transit_pathway_network_v2 `range_owndate`); the test half stays closed (its Google lines are skipped unread).
Google: the default route only (route 0, in scope by TRN-11), with a transit step: its first boarding stop and its
first walk (every step before the first transit step: distance, staticDuration). Mode = the first vehicle's type:
"train" (HEAVY_RAIL) apart from "street" (TRAM, BUS).
R5: the pathways v2 network of the pair's release (train half 2026-10-09, second and top-up 2026-10-16), walk at
4.16 km/h (config.WALK_SPEED_KMH). A forward StreetRouter walk search from the origin (as r5py's TripPlanner access
search, transit_router_egress.py C2; 1 h limit), read at the street vertex of the R5 stop nearest Google's boarding
stop, matched if within STOP_MATCH_M. Recorded per pair: R5 seconds and metres; metres on LINK edges (the stop's link,
and in v2 the station spurs are ordinary ways, so they count as street); the origin's off-street distance to its
edge (findSplit); the start state's metres (probe, 2026-10-20, before results: the search's start state holds the
along-edge part plus the off-street distance, so R5 charges the origin's off-street link at walk speed: WLK-3); and,
as a sensitivity, the shortest R5 walk to any stop within STOP_MATCH_M.

Rules (drafted with the user 2026-10-20, restated here before any result; additions marked Claude's):
  (1) Bias, per mode group (train, street) and pooled: ratio = R5 metres / Google first-walk metres on matched
      pairs with Google's first walk >= MIN_GOOGLE_WALK_M (Claude's: a ratio needs a denominator; shorter walks
      enter the seconds only). Median ratio with a bootstrap 95% CI (pairs resampled, BOOTSTRAP_REPS, fixed seed).
      MATERIAL if the CI excludes 1 and the median >= 1 + MATERIAL_EXCESS; PRESENT-SMALL if the CI excludes 1 and
      the median is nearer 1 than that; NONE if the CI holds 1. (Claude's: the same bars mirrored below 1, as
      MATERIAL-SHORT / PRESENT-SMALL-SHORT.) Also: seconds R5 minus Google at 4.16 km/h ((R5 m - Google m) / speed),
      median and mean, and the share over LONGER_S longer.
  (2) Link to misses: the ratio in R5-late, agreeing and R5-early pairs. Labels (Claude's reading of "scorer
      labels"): the scorer's distance to Google's range (transit_hard_miss_range.py distance_to_range, k = 2:
      [low_2, default_min]) for the model of record (no-wait plain, n_min): > 0 late, 0 agreeing, < 0 early.
      LINKED if the late median ratio > the agreeing median and the bootstrap 95% CI of that difference
      excludes 0; else NOT LINKED. Pooled is the verdict; per mode group reported. Stock R5 4.16 (stock_min)
      labels reported beside, no verdict.
  Reported, no verdict: stop match rate; R5 walk on LINK edges; origin off-street distance; ratio with the off-street
  distance taken out of R5 (as Google's view, WLK-3); the shortest-candidate-stop sensitivity; ratio by set.

Conclusion (run 2026-10-20, rules set before results; additions marked Claude's are not user-approved):
(1) MATERIAL, just over the bar: pooled median ratio 1.055 (95% 1.050-1.060, n 3,171); train 1.060, street 1.054
  (tram 1.072 material, bus 1.038 present-small). R5 walks a median +17 s longer at 4.16 km/h (mean +19 s); 16% of
  pairs > 60 s longer, 5% > 60 s shorter. Stop match 3,270 / 3,275 (median 1.9 m). R5 charges the origin's off-street
  link (check 1.000 of pairs): taking it out leaves street 1.020 and train 1.041 (no CI, reported), so on street stops
  most of the excess is the WLK-3 link Google does not charge. Train is sensitive to the platform matched (shortest
  candidate within 60 m: 0.926). Stop LINK edges ~2 m.
(2) LINKED: late median ratio 1.109 (n 396) vs agreeing 1.058 (n 1,023), difference +0.051 (95% +0.030 to +0.075);
  31% of late pairs walk > 60 s longer vs 15% agreeing. Driven by street stops (+0.072); train not separable
  (+0.013, CI holds 0). Stock R5 labels the same (+0.049). Early pairs walk longer too (1.046): the walk bias is
  offset elsewhere in the model (no-wait), not absent. Association, not proof of cause.
Run 2 (snap, 2026-10-20/21; reproduction PASS 30 x 3 calls per release; baseline recomputed = saved n_min; baseline
  hard tests reproduce the recorded ones: false 10 4/294, lost 20 8/248, false 20 18/503): WORSENS (Claude's rule),
  hard misses 30 -> 32 (lost 20 8 -> 7, false 10 4 -> 5, false 20 18 -> 20, lost 10 0 -> 0). Off-street median 8.1 m
  at each end. Dropping both connectors moves 17.6% of pairs 1 min earlier (mean -0.33 min), never later on
  transit; late 450 -> 365, early 1,867 -> 2,081, agree 1,131 -> 1,002; 22 band calls change. Walk-only defaults
  (n 172): error +0.05 -> -0.19 min: with 4.16 km/h, the connector is part of what makes R5's walk-only times match
  Google's, so Google's times carry an equivalent cost somewhere (Google not charging it, WLK-3, holds for its
  distances, not clearly for its times). Reading: the connector is real and goes with late misses, but the model
  leans early on the range (mean -2.75 min), so removing it trades late misses for early ones; not a lever.

Run 2 (`snap`, user 2026-10-20 after run 1): drop the connector at both ends, as Google's view (WLK-3), and see what
it does to the model of record. Every scored pair's origin and destination are moved to their R5 split point
(StreetLayer.findSplit, WALK: the point on the nearest walkable edge), so the off-street distance is 0 at the origin
(walk search start) and at the destination (TTM's egress link). Then routed as transit_pathway_network_v2 `route
--own-date` (TTM, 1-min window, own date, 4.16 km/h: stock, shifted by the 1-min board slack, walk-only) on the same
network per release. Model of record = no-wait plain: shifted - 1 if shifted < walk, else walk (transit_model_compare
model 1); cuts 10 / 20; Google's range k = 2. Reproduction first: SNAP_CHECK_PAIRS pairs per release routed unsnapped
must equal the saved v2 own-date table exactly, else stop.
Reported, baseline (saved v2 own-date) vs snapped, same pairs: late / agree / early counts; error to the range
(median, mean); the four hard-miss tests (lost / false reach at 10 and 20, windows 3-10 min from the cut, Wilson upper
vs 0.05, as transit_hard_miss_range.py, random samples only: top-up out); band calls changed; walk-only defaults' error (walk_min - Google). Reading
(Claude's rule, not user-approved, set before results): IMPROVES if the four hard tests' misses fall in total and no
test gains more than SNAP_TOLERANCE_MISSES; WORSENS if the total rises; else MIXED. Expected before results (Claude):
late falls, early rises (the model already leans early on the range: 1,808 early / 406 late), so MIXED or WORSENS is
possible even if the connector is real.

Inputs (read only): the pathways v2 derived OSM extracts and unique feed copies in diagnostics/diagnostic_data/
(transit_pathway_network_v2 build / feeds); the Google raw answers and route tables in outputs/transit_validation/;
the newest transit_pathway_network_v2_*_range_owndate_results.csv. Self-contained: imports nothing from functions/ or
config.py (CLAUDE.md D1). No paid API calls; r5py only.
Usage: `python transit_access_walk.py extract`, `... route 20261009`, `... route 20261016` (one JVM per process),
`... score`; run 2: `... snap 20261009`, `... snap 20261016`, `... snap_score`. Saved tables (extract, routes) are reused when present and said so; results carry the run date.
"""
import datetime
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
GOOGLE_RAW_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl",        # holds the test half too: skipped
                    "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.raw.jsonl",
                    "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.raw.jsonl"}
GOOGLE_ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                       "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                       "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
V2_NAME = "transit_pathway_network_v2"
RANGE_RESULTS_GLOB = f"{V2_NAME}_2*_range_owndate_results.csv"
NAME = "transit_access_walk"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_pathway_network_v2.py
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
SET_RELEASE = {"train": "20261009", "second": "20261016", "topup": "20261016"}   # as transit_pathway_network_v2.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE (the access walk is time-free)
WALK_SPEED_KMH = 4.16                          # config.WALK_SPEED_KMH (WLK-1)
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]  # TRN-11
TRAIN_TYPES = ["HEAVY_RAIL"]
STREET_TYPES = ["TRAM", "BUS"]
ACCESS_LIMIT_S = 3600                          # r5py TripPlanner.MAX_ACCESS_TIME
SPLIT_RADIUS_M = 1600                          # as StreetRouter.setOrigin (transit_router_egress.py)
FIXED_DEGREES = 1e7                            # R5's fixed-point coordinates
EARTH_RADIUS_M = 6_371_000
MM_PER_M = 1000
M_PER_KM = 1000
SECONDS_PER_HOUR = 3600
WALK_SPEED_MS = WALK_SPEED_KMH * M_PER_KM / SECONDS_PER_HOUR
ORIGIN_CHECK_M = 1.0                           # Google's request origin vs the scored pair's origin

# --- test ------------------------------------------------------------------------------------------
STOP_MATCH_M = 60                              # as transit_router_egress.py C2
MIN_GOOGLE_WALK_M = 50                         # ratio only where Google's first walk is at least this (Claude's)
MATERIAL_EXCESS = 0.05                         # rule (1): material at median ratio >= 1.05 (user)
LONGER_S = 60                                  # rule (1): share of pairs with R5's walk this much longer (user)
BOOTSTRAP_REPS = 10_000
BOOTSTRAP_SEED = 20261020
CI_LEVEL = 0.95
LABELS = ["late", "agree", "early"]
TOPUP_SET = "topup"                            # stratified, not random: out of the hard tests (as transit_hard_miss_range.py)
SNAP_CHECK_PAIRS = 30                          # run 2 reproduction check, per release
SNAP_TOLERANCE_MISSES = 2                      # run 2 reading: no hard test may gain more than this (Claude's)
CUTS_MIN = {1: 10, 2: 20}                      # as transit_hard_miss_range.py
HARD_WINDOW_NEAR_MIN = 3
HARD_WINDOW_FAR_MIN = 10
HARD_MISS_MAX = 0.05
WILSON_Z = 1.959963984540054
MAX_TIME_MIN = 90                              # as transit_pathway_network_v2.py
BOARD_SLACK_MIN = 1
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
V2_ROUTES_GLOB = V2_NAME + "_2*_routes_owndate_{release}.csv"


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def distance_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def scored_pairs():
    """Scored pairs of the own-date range scoring (train, second, top-up) with both models' minutes and the k = 2 range."""
    path = newest(RANGE_RESULTS_GLOB)
    columns = ["draw_no", "set_name", "release", "origin_lat", "origin_lon", "is_scored", "n_min", "stock_min",
               "low_2", "default_min"]
    pairs_df = pd.read_csv(path, usecols=columns)
    print(f"pairs from {path.name}", flush=True)
    return pairs_df[pairs_df.is_scored.astype(bool)].drop(columns="is_scored")


# --- extract (no JVM) ------------------------------------------------------------------------------
def extract():
    """Google's default route per scored pair: first boarding stop, first vehicle type, first walk (m, s)."""
    run_date = f"{datetime.date.today():%Y%m%d}"
    saved = newest(f"{NAME}_2*_google.csv")
    if saved is not None:
        print(f"reusing {saved.name} ({datetime.date.fromtimestamp(saved.stat().st_mtime)})")
        return
    pairs_df = scored_pairs().set_index("draw_no")
    rows = []
    for set_name, raw_path in GOOGLE_RAW_PATHS.items():
        routes_df = pd.read_csv(GOOGLE_ROUTES_PATHS[set_name])
        default_df = routes_df[routes_df.is_default].drop_duplicates("draw_no").set_index("draw_no")
        wanted = set(pairs_df.index[pairs_df.set_name == set_name])
        with open(raw_path, encoding="utf-8") as file:
            for line in file:
                draw_no = int(line[line.index(":") + 1:line.index(",")])   # read the id before parsing: test lines skipped
                if draw_no not in wanted:
                    continue
                record = json.loads(line)
                assert record["draw_no"] == draw_no
                row = {"draw_no": draw_no, "set_name": set_name}
                default = default_df.loc[draw_no]
                origin = record["request"]["origin"]["location"]["latLng"]
                row["origin_gap_m"] = distance_m(origin["latitude"], origin["longitude"],
                                                 pairs_df.at[draw_no, "origin_lat"], pairs_df.at[draw_no, "origin_lon"])
                row["route_scope"] = default.route_scope
                steps = record["resp"]["routes"][int(default.route_ix)]["legs"][0]["steps"]
                transit_ix = [i for i, step in enumerate(steps) if step["travelMode"] == "TRANSIT"]
                if transit_ix:
                    details = steps[transit_ix[0]]["transitDetails"]
                    stop = details["stopDetails"]["departureStop"]
                    row.update({"g_board_name": stop.get("name", ""),
                                "g_board_lat": stop["location"]["latLng"]["latitude"],
                                "g_board_lon": stop["location"]["latLng"]["longitude"],
                                "g_vehicle": details["transitLine"].get("vehicle", {}).get("type", ""),
                                "g_first_walk_m": sum(step.get("distanceMeters", 0) for step in steps[:transit_ix[0]]),
                                "g_first_walk_s": sum(int(step["staticDuration"].rstrip("s")) for step in steps[:transit_ix[0]])})
                rows.append(row)
    google_df = pd.DataFrame(rows)
    missing = len(pairs_df) - len(google_df)
    assert missing == 0, f"{missing} scored pairs without a Google answer"
    assert (google_df.origin_gap_m <= ORIGIN_CHECK_M).all(), "Google's origin differs from the scored pair's"
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_google.csv"
    google_df.to_csv(path, index=False)
    print(f"{len(google_df)} pairs -> {path.name}; with a transit default {google_df.g_vehicle.notna().sum()}; "
          f"vehicles {google_df.g_vehicle.value_counts().to_dict()}")


# --- route (one release per process) ---------------------------------------------------------------
def network_paths(release):
    """The pathways v2 network of a release, as transit_pathway_network_v2.load_network (unique file names)."""
    feed_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{release}"
    pbf_path = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{release}.osm.pbf"
    gtfs = [feed_dir / (f"{name}_{V2_NAME}_{release}_moved.zip" if name == TRAIN_FEED else f"{name}_{V2_NAME}_{release}.zip")
            for name in FEED_NAMES]
    return pbf_path, gtfs


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (memory r5py-working-copy-cache)."""
    import hashlib
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


def route(release):
    run_date = f"{datetime.date.today():%Y%m%d}"
    google_path = newest(f"{NAME}_2*_google.csv")
    assert google_path is not None, "run extract first"
    google_df = pd.read_csv(google_path)
    pairs_df = scored_pairs()
    todo_df = google_df[google_df.g_vehicle.notna()].merge(pairs_df[["draw_no", "origin_lat", "origin_lon"]], on="draw_no")
    todo_df = todo_df[todo_df.set_name.map(SET_RELEASE) == release]
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_routes_{release}.csv"))
    table_path = saved[-1] if saved else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_routes_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = todo_df[~todo_df.draw_no.isin(done)]
    print(f"release {release}: table {table_path.name}, {len(done)} done, {len(todo_df)} to route", flush=True)
    if todo_df.empty:
        return

    sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import
    import geopandas as gpd
    from r5py import TransportMode, TransportNetwork
    from r5py.r5.regional_task import RegionalTask
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    from com.conveyal.r5.streets import StreetRouter, EdgeStore
    from com.conveyal.r5.profile import StreetMode

    pbf_path, gtfs = network_paths(release)
    assert pbf_path.exists() and all(path.exists() for path in gtfs), "transit_pathway_network_v2 build / feeds first"
    check_working_copies([pbf_path] + gtfs)
    print(f"reusing {pbf_path.name} ({datetime.date.fromtimestamp(pbf_path.stat().st_mtime)}) and {[p.name for p in gtfs]}", flush=True)
    network = TransportNetwork(pbf_path, gtfs)
    java_network = network._transport_network
    street_layer, transit_layer = java_network.streetLayer, java_network.transitLayer
    edge_cursor = street_layer.edgeStore.getCursor()
    link_flag = EdgeStore.EdgeFlag.LINK
    stop_count = transit_layer.getStopCount()
    stop_lat = np.empty(stop_count)
    stop_lon = np.empty(stop_count)
    for stop in range(stop_count):
        coordinate = transit_layer.getCoordinateForStopFixed(stop)
        stop_lat[stop], stop_lon[stop] = coordinate.y / FIXED_DEGREES, coordinate.x / FIXED_DEGREES
    metres_per_deg_lat = math.pi * EARTH_RADIUS_M / 180

    def stops_near(lat, lon):
        """R5 stops within STOP_MATCH_M (equirectangular), nearest first, with distances."""
        dy = (stop_lat - lat) * metres_per_deg_lat
        dx = (stop_lon - lon) * metres_per_deg_lat * math.cos(math.radians(lat))
        gap_m = np.hypot(dx, dy)
        near = np.flatnonzero(gap_m <= STOP_MATCH_M)
        return near[np.argsort(gap_m[near])], gap_m

    def walk_to(router, stop):
        """Seconds, metres, metres on LINK edges, metres on whole edges, metres of the start state (None if unreached).
        The start state (no back state) carries the origin's split edge with distance = along-edge part + off-street
        distance (probe 2026-10-20: state distance increments = edge lengths on every other state)."""
        vertex = transit_layer.streetVertexForStop.get(int(stop))
        if vertex < 0:
            return None
        state = router.getStateAtVertex(vertex)
        if state is None:
            return None
        link_mm, edges_mm = 0, 0
        walker = state
        while walker.backState is not None:
            edge_cursor.seek(walker.backEdge)
            length_mm = edge_cursor.getLengthMm()
            edges_mm += length_mm
            if edge_cursor.getFlag(link_flag):
                link_mm += length_mm
            walker = walker.backState
        return (state.getDurationSeconds(), state.distance / MM_PER_M, link_mm / MM_PER_M, edges_mm / MM_PER_M,
                walker.distance / MM_PER_M)

    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        origin = gpd.points_from_xy([pair.origin_lon], [pair.origin_lat], crs="EPSG:4326")[0]
        destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.g_board_lon], [pair.g_board_lat]))
        request = RegionalTask(network, origin=origin, destinations=destinations,
                               departure=datetime.datetime.combine(WINDOW_DATE, datetime.time(12)),
                               transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], speed_walking=WALK_SPEED_KMH)
        task = request._regional_task
        task.reverseSearch = False
        router = StreetRouter(street_layer)
        router.profileRequest = task
        router.streetMode = StreetMode.WALK
        router.transitStopSearch = True
        router.timeLimitSeconds = ACCESS_LIMIT_S
        split = street_layer.findSplit(pair.origin_lat, pair.origin_lon, SPLIT_RADIUS_M, StreetMode.WALK)
        router.setOrigin(pair.origin_lat, pair.origin_lon)
        router.route()
        near, gap_m = stops_near(pair.g_board_lat, pair.g_board_lon)
        nearest = int(np.argmin(gap_m))
        row = {"draw_no": pair.draw_no, "set_name": pair.set_name, "release": release,
               "walk_speed_ms": float(task.walkSpeed),
               "origin_offstreet_m": split.distanceToEdge_mm / MM_PER_M if split is not None else None,
               "origin_d0_m": split.distance0_mm / MM_PER_M if split is not None else None,
               "origin_d1_m": split.distance1_mm / MM_PER_M if split is not None else None,
               "nearest_stop": nearest, "nearest_stop_m": round(float(gap_m[nearest]), 1),
               "nearest_stop_name": str(transit_layer.stopNames.get(nearest)), "n_candidates": len(near)}
        if len(near):
            walk = walk_to(router, near[0])
            if walk is not None:
                row.update(dict(zip(["r5_s", "r5_m", "r5_link_m", "r5_edges_m", "r5_start_m"], walk)))
            candidate_walks = [walk_to(router, stop) for stop in near]
            candidate_m = [walk[1] for walk in candidate_walks if walk is not None]
            if candidate_m:
                row["r5_min_candidate_m"] = min(candidate_m)
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % 200 == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}: {row}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


# --- score -----------------------------------------------------------------------------------------
def distance_to_range(r5_min, low, high):
    """As transit_hard_miss_range.py: minutes outside Google's range, signed (0 inside)."""
    return np.where(r5_min < low, r5_min - low, np.where(r5_min > high, r5_min - high, 0.0))


def label_of(minutes, low, high):
    distance = distance_to_range(minutes, low, high)
    return np.where(distance > 0, "late", np.where(distance < 0, "early", "agree"))


def bootstrap_medians(values, rng):
    values = np.asarray(values, dtype=float)
    medians = np.empty(BOOTSTRAP_REPS)
    chunk = 1000
    for start in range(0, BOOTSTRAP_REPS, chunk):
        draws = rng.integers(0, len(values), size=(min(chunk, BOOTSTRAP_REPS - start), len(values)))
        medians[start:start + len(draws)] = np.median(values[draws], axis=1)
    return medians


def ci(samples):
    tail = (1 - CI_LEVEL) / 2 * 100
    return np.percentile(samples, tail), np.percentile(samples, 100 - tail)


def bias_verdict(median, low, high):
    if low <= 1 <= high:
        return "NONE"
    side = "" if median > 1 else "-SHORT"
    return ("MATERIAL" if abs(median - 1) >= MATERIAL_EXCESS else "PRESENT-SMALL") + side


def bias_line(label, frame, rng):
    ratios = frame.ratio.dropna().to_numpy()
    if len(ratios) == 0:
        return f"  {label}: no pairs", None
    median = float(np.median(ratios))
    low, high = ci(bootstrap_medians(ratios, rng))
    extra_s = frame.extra_s.to_numpy()
    verdict = bias_verdict(median, low, high)
    return (f"  {label}: ratio n {len(ratios)}, median {median:.3f} (95% {low:.3f}-{high:.3f}), mean {ratios.mean():.3f}, "
            f"quartiles {np.percentile(ratios, 25):.3f}/{np.percentile(ratios, 75):.3f} -> {verdict}; seconds R5 - Google at "
            f"{WALK_SPEED_KMH} km/h (n {len(extra_s)}): median {np.median(extra_s):+.0f}, mean {extra_s.mean():+.1f}, "
            f"> {LONGER_S} s longer {np.mean(extra_s > LONGER_S):.3f}, > {LONGER_S} s shorter {np.mean(extra_s < -LONGER_S):.3f}"), verdict


def link_lines(frame, label_column, rng, is_verdict):
    lines, verdict = [], None
    medians = {}
    for label in LABELS:
        ratios = frame.loc[frame[label_column] == label, "ratio"].dropna().to_numpy()
        medians[label] = ratios
        if len(ratios):
            low, high = ci(bootstrap_medians(ratios, rng))
            lines.append(f"    {label}: n {len(ratios)}, median ratio {np.median(ratios):.3f} (95% {low:.3f}-{high:.3f}), "
                         f"share > {LONGER_S} s longer {np.mean(frame.loc[frame[label_column] == label, 'extra_s'] > LONGER_S):.3f}")
        else:
            lines.append(f"    {label}: no pairs")
    if len(medians["late"]) and len(medians["agree"]):
        difference = bootstrap_medians(medians["late"], rng) - bootstrap_medians(medians["agree"], rng)
        low, high = ci(difference)
        observed = np.median(medians["late"]) - np.median(medians["agree"])
        is_linked = observed > 0 and low > 0
        verdict = "LINKED" if is_linked else "NOT LINKED"
        lines.append(f"    late - agree median: {observed:+.3f} (95% {low:+.3f} to {high:+.3f})"
                     + (f" -> {verdict}" if is_verdict else " (reported)"))
    return lines, verdict


def score():
    run_date = f"{datetime.date.today():%Y%m%d}"
    google_path = newest(f"{NAME}_2*_google.csv")
    route_paths = [newest(f"{NAME}_2*_routes_{release}.csv") for release in sorted(set(SET_RELEASE.values()))]
    assert google_path is not None and all(route_paths), "extract and route both releases first"
    lines = [f"{NAME} {run_date}: H-walk access-walk test (rules in the docstring, set before results)",
             f"reusing {google_path.name} and {[path.name for path in route_paths]}"]
    google_df = pd.read_csv(google_path)
    routes_df = pd.concat([pd.read_csv(path) for path in route_paths], ignore_index=True)
    pairs_df = scored_pairs()
    df = pairs_df.merge(google_df.drop(columns="set_name"), on="draw_no", validate="one_to_one")
    df = df.merge(routes_df.drop(columns=["set_name", "release"]), on="draw_no", how="left", validate="one_to_one")
    df["group"] = np.where(df.g_vehicle.isin(TRAIN_TYPES), "train", np.where(df.g_vehicle.isin(STREET_TYPES), "street", "other"))
    df["label_model"] = label_of(df.n_min.fillna(np.inf).to_numpy(), df.low_2.to_numpy(), df.default_min.to_numpy())
    df["label_stock"] = label_of(df.stock_min.fillna(np.inf).to_numpy(), df.low_2.to_numpy(), df.default_min.to_numpy())

    has_transit = df.g_vehicle.notna()
    lines.append(f"scored pairs {len(df)}; Google default with a transit step {int(has_transit.sum())} "
                 f"(walk-only defaults {int((~has_transit).sum())}); groups {df[has_transit].group.value_counts().to_dict()}")
    df = df[has_transit & (df.group != "other")].copy()
    is_candidate = df.n_candidates > 0
    is_matched = is_candidate & df.r5_m.notna()
    lines.append(f"stop match within {STOP_MATCH_M} m: {int(is_candidate.sum())}/{len(df)} "
                 f"(train {int(is_candidate[df.group == 'train'].sum())}/{int((df.group == 'train').sum())}, "
                 f"street {int(is_candidate[df.group == 'street'].sum())}/{int((df.group == 'street').sum())}); "
                 f"matched stop reached by R5's walk {int(is_matched.sum())}; nearest-stop distance where matched: median "
                 f"{df.nearest_stop_m[is_candidate].median():.1f} m")
    df = df[is_matched].copy()
    df["extra_s"] = (df.r5_m - df.g_first_walk_m) / WALK_SPEED_MS
    is_ratio = df.g_first_walk_m >= MIN_GOOGLE_WALK_M
    df["ratio"] = np.where(is_ratio, df.r5_m / df.g_first_walk_m, np.nan)
    lines.append(f"ratio pairs (Google first walk >= {MIN_GOOGLE_WALK_M} m): {int(is_ratio.sum())} of {len(df)} matched")
    speed_check = df.r5_m / df.r5_s
    lines.append(f"check: R5 metres / seconds median {speed_check.median():.4f} m/s vs {WALK_SPEED_MS:.4f} "
                 f"(walk speed in the request {df.walk_speed_ms.median():.4f}); Google first walk m / s median "
                 f"{(df.g_first_walk_m / df.g_first_walk_s)[df.g_first_walk_s > 0].median():.3f} m/s")

    start_parts = df.r5_start_m - df.origin_offstreet_m
    is_split_end = ((start_parts - df.origin_d0_m).abs() < 1) | ((start_parts - df.origin_d1_m).abs() < 1)
    lines.append(f"check: R5 metres = whole edges + start state within 1 m on {np.mean((df.r5_edges_m + df.r5_start_m - df.r5_m).abs() < 1):.3f}; "
                 f"start state - off-street = one end of the split within 1 m on {is_split_end.mean():.3f} (R5 charges the off-street link)")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    lines.append("")
    lines.append("(1) bias, ratio R5 m / Google first-walk m:")
    verdicts = {}
    for label, frame in [("pooled", df), ("train", df[df.group == "train"]), ("street", df[df.group == "street"]),
                         ("street tram", df[df.g_vehicle == "TRAM"]), ("street bus", df[df.g_vehicle == "BUS"])]:
        line, verdict = bias_line(label, frame, rng)
        lines.append(line)
        verdicts[label] = verdict
    lines.append("")
    lines.append("(2) link to misses, model of record (no-wait plain, k = 2 range):")
    lines.append(f"  labels: {df.label_model.value_counts().to_dict()}")
    model_lines, link_verdict = link_lines(df, "label_model", rng, True)
    lines += ["  pooled:"] + model_lines
    for group in ["train", "street"]:
        group_lines, _ = link_lines(df[df.group == group], "label_model", rng, False)
        lines += [f"  {group} (reported):"] + group_lines
    lines.append(f"  stock R5 4.16 labels (reported): {df.label_stock.value_counts().to_dict()}")
    stock_lines, _ = link_lines(df, "label_stock", rng, False)
    lines += stock_lines

    lines.append("")
    lines.append("reported, no verdict:")
    for label, frame in [("train", df[df.group == "train"]), ("street", df[df.group == "street"])]:
        ratio_frame = frame[frame.ratio.notna()]
        lines.append(f"  {label}: LINK edges median {frame.r5_link_m.median():.1f} m (mean {frame.r5_link_m.mean():.1f}); "
                     f"origin off-street median {frame.origin_offstreet_m.median():.1f} m; ratio with off-street taken out "
                     f"{np.median((ratio_frame.r5_m - ratio_frame.origin_offstreet_m) / ratio_frame.g_first_walk_m):.3f}; "
                     f"ratio without LINK edges {np.median((ratio_frame.r5_m - ratio_frame.r5_link_m) / ratio_frame.g_first_walk_m):.3f}; "
                     f"shortest candidate stop {np.median(ratio_frame.r5_min_candidate_m / ratio_frame.g_first_walk_m):.3f}; "
                     f"Google first walk median {frame.g_first_walk_m.median():.0f} m, R5 {frame.r5_m.median():.0f} m")
    for set_name, frame in df.groupby("set_name"):
        lines.append(f"  set {set_name}: ratio median {frame.ratio.median():.3f} (n {int(frame.ratio.notna().sum())})")
    lines.append(f"  R5 seconds - Google's own first-walk seconds: median {np.median(df.r5_s - df.g_first_walk_s):+.0f}, "
                 f"mean {(df.r5_s - df.g_first_walk_s).mean():+.1f}")
    lines.append("")
    lines.append(f"VERDICT (1) bias: pooled {verdicts['pooled']}; train {verdicts['train']}; street {verdicts['street']}")
    lines.append(f"VERDICT (2) link to late misses (pooled, model of record): {link_verdict}")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_pairs.csv", index=False)


# --- run 2: connector dropped at both ends ----------------------------------------------------------
def snap(release):
    run_date = f"{datetime.date.today():%Y%m%d}"
    columns = ["draw_no", "set_name", "release", "own_date", "origin_lat", "origin_lon", "dest_lat", "dest_lon",
               "dep_min_of_day", "is_scored"]
    pairs_df = pd.read_csv(newest(RANGE_RESULTS_GLOB), usecols=columns)
    pairs_df = pairs_df[pairs_df.is_scored.astype(bool) & (pairs_df.release.astype(str) == release)]
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_snap_{release}.csv"))
    table_path = saved[-1] if saved else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_snap_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"release {release}: {len(pairs_df)} scored pairs; table {table_path.name}, {len(done)} done, {len(todo_df)} to route", flush=True)
    if todo_df.empty:
        return

    sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import
    import geopandas as gpd
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    from com.conveyal.r5.profile import StreetMode

    pbf_path, gtfs = network_paths(release)
    check_working_copies([pbf_path] + gtfs)
    network = TransportNetwork(pbf_path, gtfs)
    street_layer = network._transport_network.streetLayer
    transit_modes = [TransportMode.TRANSIT, TransportMode.WALK]

    def ttm_min(points, departure, transport_modes, max_time_min):
        origin_lat, origin_lon, dest_lat, dest_lon = points
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([origin_lon], [origin_lat]))
        destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([dest_lon], [dest_lat]))
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=transport_modes, max_time=datetime.timedelta(minutes=max_time_min),
            speed_walking=WALK_SPEED_KMH))
        return matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]

    def three_calls(points, pair):
        departure = (datetime.datetime.combine(datetime.date.fromisoformat(str(pair.own_date)), datetime.time())
                     + datetime.timedelta(minutes=int(pair.dep_min_of_day)))
        return {"stock_min": ttm_min(points, departure, transit_modes, MAX_TIME_MIN),
                "shifted_min": ttm_min(points, departure - datetime.timedelta(minutes=BOARD_SLACK_MIN),
                                       transit_modes, MAX_TIME_MIN + BOARD_SLACK_MIN),
                "walk_min": ttm_min(points, departure, [TransportMode.WALK], MAX_TIME_MIN)}

    if not done:
        v2_df = pd.read_csv(newest(V2_ROUTES_GLOB.format(release=release))).set_index("draw_no")
        mismatches = 0
        for pair in pairs_df.head(SNAP_CHECK_PAIRS).itertuples():
            got = three_calls((pair.origin_lat, pair.origin_lon, pair.dest_lat, pair.dest_lon), pair)
            for key, value in got.items():
                expected = v2_df.at[pair.draw_no, key]
                if not ((pd.isna(value) and pd.isna(expected)) or value == expected):
                    mismatches += 1
                    print(f"  check mismatch {pair.draw_no} {key}: {value} vs {expected}", flush=True)
        print(f"reproduction check (unsnapped, {SNAP_CHECK_PAIRS} pairs x 3 calls vs saved v2): "
              f"{'PASS' if mismatches == 0 else 'FAIL'} ({mismatches} mismatches)", flush=True)
        assert mismatches == 0, "reproduction failed: no snapped run"

    def split_point(lat, lon):
        split = street_layer.findSplit(lat, lon, SPLIT_RADIUS_M, StreetMode.WALK)
        if split is None:
            return lat, lon, None
        return split.fixedLat / FIXED_DEGREES, split.fixedLon / FIXED_DEGREES, split.distanceToEdge_mm / MM_PER_M

    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        origin_lat, origin_lon, origin_off_m = split_point(pair.origin_lat, pair.origin_lon)
        dest_lat, dest_lon, dest_off_m = split_point(pair.dest_lat, pair.dest_lon)
        after = street_layer.findSplit(origin_lat, origin_lon, SPLIT_RADIUS_M, StreetMode.WALK)
        row = {"draw_no": pair.draw_no, "set_name": pair.set_name, "release": release,
               "origin_offstreet_m": origin_off_m, "dest_offstreet_m": dest_off_m,
               "origin_offstreet_after_m": after.distanceToEdge_mm / MM_PER_M if after is not None else None,
               **three_calls((origin_lat, origin_lon, dest_lat, dest_lon), pair)}
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % 200 == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}: {row}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


def wilson(successes, n):
    if n == 0:
        return np.nan, np.nan
    share = successes / n
    centre = (share + WILSON_Z ** 2 / (2 * n)) / (1 + WILSON_Z ** 2 / n)
    half_width = WILSON_Z * np.sqrt(share * (1 - share) / n + WILSON_Z ** 2 / (4 * n ** 2)) / (1 + WILSON_Z ** 2 / n)
    return centre - half_width, centre + half_width


def no_wait_min(shifted_min, walk_min):
    """Model of record: shifted - 1 if transit wins (shifted < walk), else walk (transit_model_compare model 1)."""
    shifted, walk = shifted_min.fillna(np.inf).to_numpy(), walk_min.fillna(np.inf).to_numpy()
    return np.where(shifted < walk, shifted - BOARD_SLACK_MIN, walk)


def hard_counts(model_min, low, high):
    """Per-cut lost / false reach as transit_hard_miss_range.hard_tests (k = 2 range, plain cuts): {test: (k, n, upper)}."""
    results = {}
    for cut_min in CUTS_MIN.values():
        is_r5_below = model_min <= cut_min
        is_low_below, is_high_below = low <= cut_min, high <= cut_min
        is_google_below = np.where(is_low_below != is_high_below, is_r5_below, is_high_below)
        for kind, low_min, high_min in [("lost", cut_min - HARD_WINDOW_FAR_MIN, cut_min - HARD_WINDOW_NEAR_MIN),
                                        ("false", cut_min + HARD_WINDOW_NEAR_MIN, cut_min + HARD_WINDOW_FAR_MIN)]:
            is_window = (high >= low_min) & (high <= high_min)
            k, n = int((is_window & (is_r5_below != is_google_below)).sum()), int(is_window.sum())
            results[f"{kind} {cut_min}"] = (k, n, wilson(k, n)[1])
    return results


def band_of(minutes):
    return np.where(minutes <= CUTS_MIN[1], 1, np.where(minutes <= CUTS_MIN[2], 2, 3))


def snap_score():
    run_date = f"{datetime.date.today():%Y%m%d}"
    paths = [newest(f"{NAME}_2*_snap_{release}.csv") for release in sorted(set(SET_RELEASE.values()))]
    assert all(paths), "snap both releases first"
    base_path = newest(RANGE_RESULTS_GLOB)
    base_df = pd.read_csv(base_path)
    base_df = base_df[base_df.is_scored.astype(bool)]
    snap_df = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)
    df = base_df.merge(snap_df.drop(columns=["set_name", "release"]), on="draw_no", suffixes=("", "_snap"), validate="one_to_one")
    lines = [f"{NAME} {run_date} run 2 (snap): connector dropped at both ends; reusing {[p.name for p in paths]}, baseline {base_path.name}",
             f"pairs {len(df)} of {len(base_df)} scored; origin off-street median {df.origin_offstreet_m.median():.1f} m "
             f"(after snapping max {df.origin_offstreet_after_m.max():.3f} m), destination median {df.dest_offstreet_m.median():.1f} m"]
    low, high = df.low_2.to_numpy(), df.default_min.to_numpy()
    is_random = (df.set_name != TOPUP_SET).to_numpy()     # hard tests on the random samples only (top-up reported)
    base_min = no_wait_min(df.shifted_min, df.walk_min)
    is_same = np.array_equal(np.nan_to_num(base_min, posinf=-1), np.nan_to_num(df.n_min.fillna(np.inf).to_numpy(), posinf=-1))
    lines.append(f"check: baseline no-wait recomputed from saved shifted / walk = saved n_min: {'OK' if is_same else 'MISMATCH'}")
    snap_min = no_wait_min(df.shifted_min_snap, df.walk_min_snap)
    hard = {}
    for label, minutes in [("baseline", base_min), ("snapped", snap_min)]:
        distance = distance_to_range(minutes, low, high)
        finite = np.isfinite(distance)
        labels = pd.Series(label_of(minutes, low, high)).value_counts().reindex(LABELS, fill_value=0).to_dict()
        hard[label] = hard_counts(minutes[is_random], low[is_random], high[is_random])
        lines.append(f"{label}: labels {labels}; error to range median {np.median(distance[finite]):+.1f}, mean {distance[finite].mean():+.2f}")
        lines.append("    " + "; ".join(f"{test} {k}/{n} (upper {upper:.3f}{' FAIL' if upper > HARD_MISS_MAX else ''})"
                                         for test, (k, n, upper) in hard[label].items()))
    finite = np.isfinite(base_min) & np.isfinite(snap_min)
    shift = np.where(finite, snap_min - base_min, np.nan)
    lines.append(f"no-wait minutes snapped - baseline: mean {shift[finite].mean():+.3f}, earlier on {np.mean(shift[finite] < 0):.3f}, "
                 f"later on {np.mean(shift[finite] > 0):.3f}")
    for column in ["stock_min", "shifted_min", "walk_min"]:
        delta = (df[f"{column}_snap"] - df[column]).dropna()
        lines.append(f"  {column}: snapped - baseline mean {delta.mean():+.3f}, earlier on {np.mean(delta < 0):.3f}, later on {np.mean(delta > 0):.3f}")
    lines.append(f"band calls changed (10 / 20 cuts): {int((band_of(snap_min) != band_of(base_min)).sum())}")
    is_walk_default = df.default_walk_only.astype(bool) & df.walk_min.notna() & df.walk_min_snap.notna()
    for label, column in [("baseline", "walk_min"), ("snapped", "walk_min_snap")]:
        error = (df.loc[is_walk_default, column] - df.loc[is_walk_default, "default_min"]).dropna()
        lines.append(f"walk-only defaults (n {len(error)}), R5 walk - Google, {label}: mean {error.mean():+.2f}, "
                     f"median {error.median():+.0f}, exact {np.mean(error == 0):.3f}")
    base_total = sum(k for k, _, _ in hard["baseline"].values())
    snap_total = sum(k for k, _, _ in hard["snapped"].values())
    worst_gain = max(hard["snapped"][test][0] - hard["baseline"][test][0] for test in hard["baseline"])
    reading = ("IMPROVES" if snap_total < base_total and worst_gain <= SNAP_TOLERANCE_MISSES
               else "WORSENS" if snap_total > base_total else "MIXED")
    lines.append(f"READING (Claude's rule): hard misses {base_total} -> {snap_total}, largest gain in one test {worst_gain:+d} -> {reading}")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_snap_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    {"extract": extract, "route": route, "score": score, "snap": snap, "snap_score": snap_score}[sys.argv[1]](*sys.argv[2:])
