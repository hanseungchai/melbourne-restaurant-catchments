"""Q24 combined model: connectors dropped, walk speed refit in seconds, 30 s destination offset; scored on training pairs.

Claim under test (DESIGN.md Q24; concepts/walk.md WLK-1, WLK-3, WLK-6; concepts/transit.md TRN-6, TRN-13; SCR-10): three
principled timing corrections, each matching how Google reports time, change the transit band model's calls toward
Google's: (a) no walk charged from the origin or destination point to the street (WLK-3); (b) walking speed refit on
Google's walk-only routes in seconds, without connectors; (c) R5's truncated minutes read as rounded through a 30 s
offset at the destination end (floor(t + 30) = round(t), exact per pair). Where the pipeline would rely on it: transit
bands 1-2 (SCR-1, RCH-1) through the model of record (TRN-13: no-wait at plain cuts on the pathways v2 network).
Autonomous session 2026-10-21 (user's go; milestone: the combined model scored on the training pairs). In-sample: the
speed is fitted on part of these pairs and the pairs have been read before; a good result argues for a fresh holdout,
it does not validate.

Steps (modes; one JVM per process):
  probe 20261009  Does TTM charge the destination's off-street distance at the request's walk speed? Probe pairs: scored
      2026-10-09 pairs in draw order, walk-only (Google default walk-only, R5 walk finite) and transit-won (shifted <
      walk); each destination snapped (StreetLayer.findSplit, WALK), then moved straight off its edge segment (the
      perpendicular, the original point's side first) 0 to PROBE_MAX_M in PROBE_STEP_M steps; only offsets whose split
      keeps the edge (same edge pair), the along-edge position (distance0 within ALONG_TOLERANCE_M) and an off-street
      distance within OFFSTREET_TOLERANCE_M of the offset are kept, contiguous from 0. Pairs whose kept range reaches
      PROBE_MIN_RANGE_M; first PROBE_PAIRS of each kind. One TTM call per pair (snapped origin, all offsets as
      destinations, own date and drawn minute, 1-min window, 4.16 km/h; walk-only pairs WALK only, transit pairs
      TRANSIT + WALK). Ticks = offsets where the minute steps up.
      Pass rule (Claude's, OK'd by the user 2026-10-21 before the run), all three:
        (P1) every pair with >= 2 ticks: metres per minute (first to last tick / ticks - 1) within RATE_TOLERANCE of
             60 x walk speed (69.33 m at 4.16 km/h), walk-only and transit both; (R5's 1.3 m/s would give 78 m);
        (P2) every step is exactly +1 minute and minutes never fall;
        (P3) at a 30 s offset (30 x walk speed), >= EDGE_KEEP_MIN of all scored 2026-10-09 destinations keep the edge.
      Fail = stop the autonomous run and report (the R5 jar's TravelTimeReducer is not opened without the user).
  speedfit <release>, speedfit_report  (b): pairs with a Google walk-only route (the default if walk-only, else the first
      walk-only alternative; as walk_only_speed_fit.py) among the scored pairs (train half, second batch, top-up; test half
      closed). R5 street metres: snapped origin to snapped destination, forward StreetRouter (WALK, request at 4.16 km/h,
      time limit FIT_TIME_LIMIT_S), state at the destination split (StreetRouter.getState(Split), as
      transit_router_egress.py C4). Speed per pair = R5 metres / Google duration_s; mean and median in km/h, 3 decimals.
      Both are carried (user 2026-10-21: run both).
  route <release>  Reproduction first, else stop: (R1) SNAP_CHECK_PAIRS pairs unsnapped at 4.16 = the saved v2 own-date
      table exactly (3 calls each); (R2) snapped at 4.16 with no offset = run 2's snap table (transit_access_walk.py),
      every pair, checked on the first SNAP_CHECK_PAIRS before going on and counted over all. Then per pair: origin
      snapped; destinations [snapped, offset by 30 s of walking at that speed]; speeds 4.16 (run 2's), median and mean;
      per speed three TTM calls as v2 `route --own-date` (stock, from t - 1 min = shifted, walk-only). An offset point that
      keeps no edge (either side) is flagged; that pair uses its snapped minutes for (c) (reported count).
  score  Variants (each = no-wait plain: shifted - 1 if shifted < walk, else walk; transit_model_compare model 1):
      baseline (saved model of record, n_min); (a) snapped 4.16 (= run 2); (a)+(c) 4.16; (a)+(b) median; (a)+(b) mean;
      (a)+(b)+(c) median, (a)+(b)+(c) mean (the combined model, primary).
      Reported per variant: late / agree / early to Google's k = 2 range; error to the range (median, mean); the four
      hard-miss tests (lost / false reach at 10 and 20, windows 3-10 min from the cut, Wilson upper vs 0.05, random samples
      only: top-up out; transit_hard_miss_range.py); TRN-13 zone measures on Google's rounded minutes (zones 7-13 / 17-23,
      recall, precision, Wilson 95%, floor 0.6, balance: sign test and |recall - precision| <= 0.10, noise bar from the
      off-cut pairs' errors centred to median 0) and count ratios <= 10 / <= 20 on the random samples (0.90-1.10); band
      calls changed against baseline; walk-only defaults' error (walk - Google default minutes, mean, median, exact).
      Reading (Claude's rule, OK'd by the user 2026-10-21 before results), per variant against baseline: IMPROVES if the
      four hard tests' misses fall in total below the baseline's and no test gains more than SNAP_TOLERANCE_MISSES;
      WORSENS if the total rises; else MIXED.

Predictions (Claude's, written before any result of this run): the probe passes P1 / P2 (TTM's egress table is a
distance divided by the walk speed, transit_router_egress.py C3); P3 near 0.99. The refit speed falls below 4.16
(about 4.0: the connectors' ~16 m and ~26 s per walk-only trip leave R5's metres), mean above median by < 0.1. Each
of (b) and (c) moves minutes later; combined about +0.5 to +0.9 min mean against baseline; late rises, early falls;
hard misses 30 -> 25-33 (MIXED most likely; lost 20 grows, false 20 shrinks); zone 2 balance nearer pass.

Conclusion (probe run 2026-10-21, autonomous; rule set before the run): PROBE FAIL, so the run stopped there (user's
stop condition); speedfit, route and score were not run.
  (P3) FAIL, decisively: at a 30 s offset (34.67 m at 4.16 km/h) only 48 of 1,246 scored 2026-10-09 destinations
       (0.039) keep their edge on either side; within about 5-20 m of most destinations another walkable edge is nearer
       (footways, service lanes, the other carriageway), so a point placed 35 m off its street links elsewhere. (c) as a
       moved destination cannot be exact per pair on this network.
  (P1) not measurable: no scored destination keeps its edge for 140 m; with the screen lowered to 70 m (two ticks
       possible, not guaranteed) one transit pair qualified (draw 7071, 113.5 m) and showed one tick (60.75 m); no walk-
       only pair qualified. So whether TTM charges the off-street link at the request's walk speed stays unchecked
       here (transit_router_egress.py C3 read it from the jar as distance / walk speed).
  (P2) PASS on the one pair (unit step, never falling).
  Deviations from the plan, all before any probe result: the first attempt's geometric normal drifted ~0.4 m along the
  edge per metre off (bug), replaced by a numerical normal from R5's own distance0 (drift ~1-2 cm per metre); the
  candidate pool widened from the first 80 per kind to all, with a same-edge screen, after the first attempt kept none.
  Options for the user (Claude's, not run): (i) the jar fallback recorded in Q24 (read TravelTimeReducer); (ii) a
  destination stub: a dead-end footway of 30 s walking added from each destination's split point to the derived OSM,
  the destination at its far end (v2 already moves platform stops onto 2 m stubs), so the link is an edge that nothing
  else is nearer to; a dead end creates no shortcut, but it is a graph edit per destination set; (iii) run (a) + (b)
  alone (speed refit without the offset), which does not depend on the probe.

Run 3, destination stubs (user 2026-10-21 after the probe: option (ii), "similar to our pathway"; quick run first).
Network: the pathways v2 derived extract of the release plus, per scored destination and per speed, a straight stub of
OFFSET_S x speed metres from the destination's nearest point on a walkable, linkable way (a node spliced in, or an
existing node within SNAP_M): all of it `highway=footway, tunnel=yes` (R5 links nothing to a tunnel way, as v2's
spurs) except the last STUB_TIP_M, a plain footway, at whose end the destination is placed. Direction: of
STUB_DIRECTIONS, the one whose points every CLEARANCE_STEP_M along it lie farthest from any existing walkable or
platform way; one direction per speed. Written as a new, uniquely named extract (r5py caches by file name); v2's
feeds reused. Routing as `route`: origin and destination snapped (R5 split of the original points); the (c) point of a
speed = its stub tip. Checks before any routing (Claude's rule, the user OK'd the idea 2026-10-21; all must hold, else
stop): (C1) no transit stop links to a stub way; (C2) every stub tip links to its own tip way, 0 m off; (C3) no
origin's or destination's split lies on a stub way; (C4) R5's walk from stub base to tip = OFFSET_S +- STUB_SECONDS_TOL
at that speed. Reported: base vs R5's split of the original destination (m). Quick run (`build_stubs 20261009 quick`,
`route 20261009 quick`): 4.16 km/h only, the first QUICK_PAIRS scored 2026-10-09 pairs, plus (C5, reported) each call's
tip minus snapped minutes in {0, +1} with the +1 share near 0.5 (truncation of a uniform second).

Conclusion, run 3 (2026-10-21, autonomous; reading rule OK'd by the user before results; check revisions Claude's, each
made after the failure it fixes and stated here):
  Build history: b1 stubs on Claude's nearest way (some on pruned islands; venues inside blocks linked to tips); b2 stubs
  hang from R5's own split on v2 and the (a) destination is that stored point; b3 tip margin; b4 R5's sphere for the
  geometry (v2's 110,574 m per degree drew north-south stubs ~0.56% short, so 67 / 149 bodies tipped to 30 s and the stub
  to 31 s: confirmed, C4 then 30 s on every stub, C6 bodies within 3.3 cm of intended); origins stored as R5's split on
  v2 (b4 C3: 42 origins sat nearer a tip than their street); b5 (2026-10-16 only) stop safety on R5's own stop links
  (b4 C1: Box Hill Bus Station linked to a tip). Check fixes: C1 counted a stop linked at a stub's base node (harmless);
  C4 measured from a start ~1 cm along an edge; R1 skips pairs whose original point links to a stub (never routed: 4 on
  2026-10-09, 7 on 2026-10-16) and allows R1_MAX_MISMATCHES (one walk-only call at the 90-min cap failed exact).
  Final checks: C1-C4 PASS on both releases (3,234 + 5,826 stubs); R1 PASS (0 and 1 mismatch); R2 (snapped 4.16 vs
  run 2) 21 / 3,738 and 56 / 6,606 calls differ by a minute (spliced nodes shift R5's per-edge rounding; reported).
  Quick run C5: every call moves 0 or +1 min, +1 on 0.53.
  (b) speeds: median 4.143 km/h, mean 4.135 (651 pairs with a Google walk-only route; ratio of sums 4.143); predicted
  ~4.0 with the mean above the median: wrong on both, the connector refit barely moves the speed.
  Readings vs baseline (model of record, hard misses 30: lost 10 0/50, false 10 4/294, lost 20 8/248, false 20 18/503):
    (a) snap 4.16             32 WORSENS (= run 2)       (a)+(b) median / mean  31 / 31 WORSENS
    (a)+(c) 4.16              28 IMPROVES                (a)+(b)+(c) median / mean  25 / 25 IMPROVES
  Combined (a)+(b)+(c), median: false 10 2/294, lost 20 7/248, false 20 16/503 (upper 0.051, still over 0.05; lost 20
  upper 0.057); labels late 681 / agree 1,317 / early 1,450 (baseline 450 / 1,131 / 1,867); error to the range median
  +0.0 (baseline -1.0), mean -2.52 (-2.75); +0.24 min mean vs baseline, 48 band calls change; off-cut error mean -0.16
  (-0.39); count ratios 0.961 / 1.046 (1.097 / 1.073); zone 2 balance now PASSES (38 early / 26 late, p 0.169; gap 0.049)
  but zone 1 noise bar now FAILS (recall 0.793 vs bar 0.874; zone 1 misses 13 early / 18 late); walk-only defaults
  +0.27 min (baseline -0.06). Mean speed: the same hard counts.
  Reading (Claude's): (c) does the work, (a) and (b) alone make R5 earlier; together hard misses 30 -> 25 and the model's
  lean toward early is mostly gone, at the cost of zone 1 recall. In-sample (training pairs, speed fitted on part of
  them); a fresh holdout is what could confirm it.

Inputs (read only): the pathways v2 derived OSM extracts and unique feed copies, the v2 own-date routing tables and
range results, run 2's snap tables (transit_access_walk.py) in diagnostics/diagnostic_data/; Google route tables in
outputs/transit_validation/. Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API
calls; r5py only. Saved tables are reused when present and said so; results carry the run date.
Usage: `python transit_q24_combined.py probe 20261009`, `... speedfit 20261009`, `... speedfit 20261016`,
`... speedfit_report`, `... route 20261009`, `... route 20261016`, `... score`; run 3: `... build_stubs <release> [quick]`,
`... route_stubs <release> [quick]`.
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
GOOGLE_ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                       "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                       "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
V2_NAME = "transit_pathway_network_v2"
RANGE_RESULTS_GLOB = f"{V2_NAME}_2*_range_owndate_results.csv"
V2_ROUTES_GLOB = V2_NAME + "_2*_routes_owndate_{release}.csv"
RUN2_SNAP_GLOB = "transit_access_walk_2*_snap_{release}.csv"
NAME = "transit_q24_combined"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_pathway_network_v2.py
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
BASE_SPEED_KMH = 4.16                          # config.WALK_SPEED_KMH (WLK-1)
SPLIT_RADIUS_M = 1600                          # as StreetRouter.setOrigin (transit_router_egress.py)
FIXED_DEGREES = 1e7                            # R5's fixed-point coordinates
EARTH_RADIUS_M = 6_371_000
MM_PER_M = 1000
M_PER_KM = 1000
SECONDS_PER_HOUR = 3600
SECONDS_PER_MIN = 60
MAX_TIME_MIN = 90                              # as transit_pathway_network_v2.py
BOARD_SLACK_MIN = 1
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
TOPUP_SET = "topup"

# --- probe (rule above) ----------------------------------------------------------------------------
PROBE_PAIRS = 10                               # per kind (walk-only, transit)
PROBE_CANDIDATES = 10_000                      # per kind (all): the first attempt's 80 kept none (dense edges)
PROBE_SCREEN_M = [35.0, 70.0]                  # quick same-edge screen before the full sweep
GRADIENT_STEP_M = 0.5
PROBE_MAX_M = 150.0
PROBE_STEP_M = 0.25
PROBE_MIN_RANGE_M = 70.0                       # >= 69.3 m: two ticks possible (140 m kept none, 2026-10-21)
ALONG_TOLERANCE_M = 0.5
OFFSTREET_TOLERANCE_M = 0.5
RATE_TOLERANCE = 0.02
EDGE_KEEP_MIN = 0.98

# --- run 3: destination stubs ----------------------------------------------------------------------
STUB_EPS_S = 0.05                              # body 29 - eps s, tip 1 - eps s: R5 rounds each edge's seconds up (quick
                                               # run 1: 29.25 s -> 30, 0.87 s -> 1), so it charges exactly 30 s; 0.003
                                               # (build b2) left 87 / 149 at 31 s (7-decimal coordinates move ~1 cm)
BASE_ON_WAY_TOL_M = 0.05                       # R5's split must lie on its OSM way this close
STOP_MARGIN_M = 1.0                            # a tip must be this much farther from a stop than the stop's street
STUB_DIRECTIONS = 16
CLEARANCE_STEP_M = 5.0
STUB_SECONDS_TOL = 1.0                         # (C4)
SNAP_M = 0.05                                  # reuse an existing node this close instead of splicing
LOCAL_DEG = 0.003                              # segments within this of a destination enter its clearance (~300 m)
GRID_DEG = 0.004                               # candidate-way grid cell (as v2)
NEW_NODE_ID_BASE = 60_000_000_000              # above v2's own new ids (50e9 + n; checked at build)
NEW_WAY_ID_BASE = 9_500_000_000                # above v2's (9e9 + n; checked)
TAG_SOURCE = ("platica", "q24_stub")
QUICK_PAIRS = 150
R1_MAX_MISMATCHES = 3                          # of 90 calls; b5 2026-10-16: exact rule (0) failed on a walk-only call at
                                               # the 90-min cap (splice rounding, as R2's 0.6% on 2026-10-09) and an origin
                                               # on a stub (now skipped); revised by Claude after seeing them, stated
STUB_BUILD = {"20261009": "b4", "20261016": "b5"}   # in every stub file name: r5py caches by name (build 1 renamed
                                               # _build1); b5: stop safety on R5's own stop links (b4 2026-10-16 C1:
                                               # Box Hill Bus Station linked to a tip; 2026-10-09 b4 passed, kept)
STOP_LINK_RADIUS_M = 300                       # R5's first stop-link radius (as v2)
# R5 measures edges on a sphere (EARTH_RADIUS_M); v2's 110,574 / 111,320 m per degree drew north-south stubs ~0.56% short
# of R5's length, enough to tip a body over 29 s (b3: 67 / 149 stubs at 31 s; Claude's reading, checked by C4 / C6 in b4)
METRES_PER_DEG_LAT = math.pi * EARTH_RADIUS_M / 180
METRES_PER_DEG_LON_EQUATOR = math.pi * EARTH_RADIUS_M / 180
WALKABLE_HIGHWAYS = {"footway", "path", "pedestrian", "steps", "living_street", "residential", "service",
                     "unclassified", "tertiary", "tertiary_link", "secondary", "secondary_link", "primary",
                     "primary_link", "trunk", "trunk_link", "track", "cycleway", "road", "corridor"}   # as v2
NO_ACCESS = {"no", "private"}
PLATFORM_KEYS = ["railway", "public_transport", "highway"]
NOT_LINKABLE = [("tunnel", "yes"), ("covered", "yes")]
OFFSET_S = 30                                  # (c): floor(t + 30) = round(t)

# --- speed fit -------------------------------------------------------------------------------------
FIT_TIME_LIMIT_S = 2 * SECONDS_PER_HOUR

# --- route / score ---------------------------------------------------------------------------------
SNAP_CHECK_PAIRS = 30
SNAP_TOLERANCE_MISSES = 2                      # as transit_access_walk.py run 2 (Claude's)
CUTS_MIN = {1: 10, 2: 20}
ZONES_MIN = {1: (7, 13), 2: (17, 23)}
AWAY_RANGES_MIN = [(0, 6), (14, 16), (24, 30)]
HARD_WINDOW_NEAR_MIN = 3
HARD_WINDOW_FAR_MIN = 10
HARD_MISS_MAX = 0.05
WILSON_Z = 1.959963984540054
FLOOR = 0.6
N_SIMULATIONS = 2000
SIMULATION_SEED = 20261018
SIGN_TEST_ALPHA = 0.05
CLOSE_TOLERANCE = 0.10
COUNT_RATIO_RANGE = (0.90, 1.10)
LABELS = ["late", "agree", "early"]
SPEED_TAGS = ["base", "median", "mean"]


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def scored_pairs(release=None):
    path = newest(RANGE_RESULTS_GLOB)
    pairs_df = pd.read_csv(path)
    pairs_df = pairs_df[pairs_df.is_scored.astype(bool)]
    if release is not None:
        pairs_df = pairs_df[pairs_df.release.astype(str) == release]
    return pairs_df


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


class Router:
    """One release's network in this process, with the street helpers the modes share."""

    def __init__(self, release, stub_pbf_path=None):
        sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import
        import geopandas as gpd
        from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
        import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
        from com.conveyal.r5.profile import StreetMode
        self.gpd, self.TransportMode, self.TravelTimeMatrix = gpd, TransportMode, TravelTimeMatrix
        self.walk_mode = StreetMode.WALK
        pbf_path, gtfs = network_paths(release)
        if stub_pbf_path is not None:
            pbf_path = stub_pbf_path
        assert pbf_path.exists() and all(path.exists() for path in gtfs), "transit_pathway_network_v2 build / feeds first"
        check_working_copies([pbf_path] + gtfs)
        print(f"reusing {pbf_path.name} ({datetime.date.fromtimestamp(pbf_path.stat().st_mtime)}) and {[p.name for p in gtfs]}", flush=True)
        self.network = TransportNetwork(pbf_path, gtfs)
        self.street_layer = self.network._transport_network.streetLayer
        self.edge_store = self.street_layer.edgeStore

    def split(self, lat, lon):
        return self.street_layer.findSplit(float(lat), float(lon), SPLIT_RADIUS_M, self.walk_mode)

    def snapped(self, lat, lon):
        """(lat, lon, off-street m, split) of the point's split on its nearest walkable edge."""
        split = self.split(lat, lon)
        if split is None:
            return lat, lon, None, None
        return split.fixedLat / FIXED_DEGREES, split.fixedLon / FIXED_DEGREES, split.distanceToEdge_mm / MM_PER_M, split

    def normals(self, split, lat, lon):
        """Unit normals (east m, north m) of the split's edge, the original point's side first. The along-edge direction
        is the numerical gradient of R5's own distance0 at the split point (GRADIENT_STEP_M east and north), so the
        normal is perpendicular in R5's projection (a geometric normal from the edge's coordinates drifted ~0.4 m along
        per metre off, first probe attempt 2026-10-21)."""
        gradient = []
        for normal in [(1.0, 0.0), (0.0, 1.0)]:
            moved_lat, moved_lon = self.moved(split, normal, GRADIENT_STEP_M)
            moved_split = self.split(moved_lat, moved_lon)
            if moved_split is None or int(moved_split.edge) // 2 != int(split.edge) // 2:
                return []
            gradient.append((moved_split.distance0_mm - split.distance0_mm) / MM_PER_M / GRADIENT_STEP_M)
        length = math.hypot(*gradient)
        if length == 0:
            return []
        normal = (-gradient[1] / length, gradient[0] / length)
        metres_per_deg = math.pi * EARTH_RADIUS_M / 180
        cos_lat = math.cos(math.radians(split.fixedLat / FIXED_DEGREES))
        ox = (lon - split.fixedLon / FIXED_DEGREES) * metres_per_deg * cos_lat
        oy = (lat - split.fixedLat / FIXED_DEGREES) * metres_per_deg
        if ox * normal[0] + oy * normal[1] < 0:
            normal = (-normal[0], -normal[1])
        return [normal, (-normal[0], -normal[1])]

    def moved(self, split, normal, offset_m):
        metres_per_deg = math.pi * EARTH_RADIUS_M / 180
        base_lat, base_lon = split.fixedLat / FIXED_DEGREES, split.fixedLon / FIXED_DEGREES
        cos_lat = math.cos(math.radians(base_lat))
        return base_lat + normal[1] * offset_m / metres_per_deg, base_lon + normal[0] * offset_m / (metres_per_deg * cos_lat)

    def keeps_edge(self, base_split, lat, lon, offset_m):
        split = self.split(lat, lon)
        if split is None:
            return False
        return (int(split.edge) // 2 == int(base_split.edge) // 2
                and abs(split.distance0_mm - base_split.distance0_mm) / MM_PER_M <= ALONG_TOLERANCE_M
                and abs(split.distanceToEdge_mm / MM_PER_M - offset_m) <= OFFSTREET_TOLERANCE_M)

    def offset_point(self, lat, lon, offset_m):
        """The snapped point moved offset_m straight off its edge (either side) keeping the edge, or None."""
        _, _, _, split = self.snapped(lat, lon)
        if split is None:
            return None
        for normal in self.normals(split, lat, lon):
            moved_lat, moved_lon = self.moved(split, normal, offset_m)
            if self.keeps_edge(split, moved_lat, moved_lon, offset_m):
                return moved_lat, moved_lon
        return None

    def ttm(self, origin, destinations, departure, transport_modes, max_time_min, speed_kmh):
        """Minutes from one origin to each destination (list of (lat, lon)); NaN past max_time."""
        gpd = self.gpd
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([origin[1]], [origin[0]]))
        targets = gpd.GeoDataFrame({"id": list(range(1, len(destinations) + 1))}, crs="EPSG:4326",
                                   geometry=gpd.points_from_xy([d[1] for d in destinations], [d[0] for d in destinations]))
        matrix_df = pd.DataFrame(self.TravelTimeMatrix(
            self.network, origins=origins, destinations=targets, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=transport_modes, max_time=datetime.timedelta(minutes=max_time_min),
            speed_walking=speed_kmh))
        return matrix_df.sort_values("to_id")[f"travel_time_p{SINGLE_PERCENTILE}"].to_numpy(dtype=float)

    def three_calls(self, origin, destinations, pair, speed_kmh):
        """stock / shifted / walk minutes per destination, as v2 `route --own-date`."""
        departure = (datetime.datetime.combine(datetime.date.fromisoformat(str(pair.own_date)), datetime.time())
                     + datetime.timedelta(minutes=int(pair.dep_min_of_day)))
        transit = [self.TransportMode.TRANSIT, self.TransportMode.WALK]
        return {"stock_min": self.ttm(origin, destinations, departure, transit, MAX_TIME_MIN, speed_kmh),
                "shifted_min": self.ttm(origin, destinations, departure - datetime.timedelta(minutes=BOARD_SLACK_MIN),
                                        transit, MAX_TIME_MIN + BOARD_SLACK_MIN, speed_kmh),
                "walk_min": self.ttm(origin, destinations, departure, [self.TransportMode.WALK], MAX_TIME_MIN, speed_kmh)}


def same(value, expected):
    return (pd.isna(value) and pd.isna(expected)) or value == expected


def street_router(router, lat, lon, speed_kmh, limit_s):
    """A forward WALK StreetRouter from (lat, lon) at speed_kmh, routed."""
    from com.conveyal.r5.streets import StreetRouter
    from r5py.r5.regional_task import RegionalTask
    gpd = router.gpd
    request = RegionalTask(router.network, origin=gpd.points_from_xy([lon], [lat], crs="EPSG:4326")[0],
                           destinations=gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([lon], [lat])),
                           departure=datetime.datetime(2026, 10, 21, 12), transport_modes=[router.TransportMode.WALK],
                           speed_walking=speed_kmh)
    task = request._regional_task
    task.reverseSearch = False
    walker = StreetRouter(router.street_layer)
    walker.profileRequest = task
    walker.streetMode = router.walk_mode
    walker.timeLimitSeconds = limit_s
    walker.setOrigin(float(lat), float(lon))
    walker.route()
    return walker


# --- run 3: stub network (no JVM) ------------------------------------------------------------------
def local_xy(lat, lon, lat0, lon0):
    return ((np.asarray(lon) - lon0) * METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0)),
            (np.asarray(lat) - lat0) * METRES_PER_DEG_LAT)


def from_xy(x, y, lat0, lon0):
    return lat0 + y / METRES_PER_DEG_LAT, lon0 + x / (METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0)))


def is_walkable_linkable(tags):
    """As transit_pathway_network_v2.is_walkable_linkable."""
    if tags.get("highway") not in WALKABLE_HIGHWAYS or tags.get("area") == "yes":
        return False
    if any(tags.get(key) == value for key, value in NOT_LINKABLE):
        return False
    if tags.get("foot") in NO_ACCESS:
        return False
    return not (tags.get("access") in NO_ACCESS and tags.get("foot") not in {"yes", "designated", "permissive"})


def is_platform_way(tags):
    is_platform = any(tags.get(key) == "platform" for key in PLATFORM_KEYS)
    return is_platform and not any(tags.get(key) == value for key, value in NOT_LINKABLE)


def candidate_ways(pbf_path, points_lat, points_lon, wanted_ids=frozenset()):
    """Walkable or platform ways with a node in a grid cell next to any point (as v2), and every way in wanted_ids
    whatever its tags: {way_id: (refs, lats, lons, is_walk)}."""
    import osmium
    cells = set()
    for lat, lon in zip(points_lat, points_lon):
        row, col = math.floor(lat / GRID_DEG), math.floor(lon / GRID_DEG)
        cells |= {(row + i, col + j) for i in (-1, 0, 1) for j in (-1, 0, 1)}
    ways, max_ids = {}, {"node": 0, "way": 0}
    for obj in osmium.FileProcessor(str(pbf_path)).with_locations():
        if obj.is_node():
            max_ids["node"] = max(max_ids["node"], obj.id)
            continue
        if not obj.is_way():
            continue
        max_ids["way"] = max(max_ids["way"], obj.id)
        tags = dict(obj.tags)
        is_walk = is_walkable_linkable(tags)
        is_wanted = obj.id in wanted_ids
        if not (is_walk or is_wanted or is_platform_way(tags)):
            continue
        if not all(node.location.valid() for node in obj.nodes):
            continue
        refs = [(node.ref, node.lat, node.lon) for node in obj.nodes]
        if len(refs) < 2 or not is_wanted and not any((math.floor(lat / GRID_DEG), math.floor(lon / GRID_DEG)) in cells for _, lat, lon in refs):
            continue
        ways[obj.id] = ([ref for ref, _, _ in refs], np.array([lat for _, lat, _ in refs]),
                        np.array([lon for _, _, lon in refs]), is_walk)
    return ways, max_ids


def segment_table(ways):
    """Flat arrays of every candidate segment: way id, index, end points, walkable flag."""
    parts = {name: [] for name in ["way_id", "index", "lat1", "lon1", "lat2", "lon2", "is_walk"]}
    for way_id, (_, lats, lons, is_walk) in ways.items():
        n_segments = len(lats) - 1
        parts["way_id"].append(np.full(n_segments, way_id))
        parts["index"].append(np.arange(n_segments))
        parts["lat1"].append(lats[:-1]), parts["lon1"].append(lons[:-1])
        parts["lat2"].append(lats[1:]), parts["lon2"].append(lons[1:])
        parts["is_walk"].append(np.full(n_segments, is_walk))
    return {name: np.concatenate(values) for name, values in parts.items()}


def local_segments(lat, lon, segments):
    is_near = ((np.minimum(segments["lat1"], segments["lat2"]) <= lat + LOCAL_DEG)
               & (np.maximum(segments["lat1"], segments["lat2"]) >= lat - LOCAL_DEG)
               & (np.minimum(segments["lon1"], segments["lon2"]) <= lon + LOCAL_DEG)
               & (np.maximum(segments["lon1"], segments["lon2"]) >= lon - LOCAL_DEG))
    return {name: values[is_near] for name, values in segments.items()}


def point_distances(px, py, local, lat0, lon0):
    """Distance (m) from each point (local x, y around lat0, lon0) to the nearest local segment, plus that segment's t."""
    x1, y1 = local_xy(local["lat1"], local["lon1"], lat0, lon0)
    x2, y2 = local_xy(local["lat2"], local["lon2"], lat0, lon0)
    dx, dy = x2 - x1, y2 - y1
    length2 = np.where(dx ** 2 + dy ** 2 > 0, dx ** 2 + dy ** 2, 1)
    px, py = np.asarray(px)[:, None], np.asarray(py)[:, None]
    t = np.clip(((px - x1) * dx + (py - y1) * dy) / length2, 0, 1)
    distance = np.hypot(x1 + t * dx - px, y1 + t * dy - py)
    nearest = np.argmin(distance, axis=1)
    return distance[np.arange(len(nearest)), nearest], nearest, t[np.arange(len(nearest)), nearest]


def spliced_nodes(refs, splice_list):
    by_segment = {}
    for segment, t, node_id in splice_list:
        by_segment.setdefault(segment, []).append((t, node_id))
    out = []
    for i, ref in enumerate(refs):
        out.append(ref)
        out += [node_id for _, node_id in sorted(by_segment.get(i, []))]
    return out


def stub_speeds(mode):
    if mode == "quick":
        return {"base": BASE_SPEED_KMH}
    speeds_path = newest(f"{NAME}_2*_speeds.json")
    assert speeds_path is not None, "speedfit_report first"
    return {"base": BASE_SPEED_KMH, **json.loads(speeds_path.read_text(encoding="utf-8"))}


def speeds_tag(speeds, release):
    return "_".join(f"{speed:.3f}".replace(".", "") for speed in sorted(set(speeds.values()))) + f"_{STUB_BUILD[release]}"


def stub_paths(release, speeds):
    tag = speeds_tag(speeds, release)
    pbf = newest(f"{NAME}_2*_osm_{release}_{tag}.osm.pbf")
    table = newest(f"{NAME}_2*_stubs_{release}_{tag}.csv")
    return pbf, table, tag


def dest_splits(release):
    """R5's split of every scored destination on the v2 network (the (a) point, as run 2) with its edge's OSM way, and
    every transit stop's position; saved for build_stubs (one JVM)."""
    splits_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_destsplits_{release}.csv"
    stops_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_stops_{release}.csv"
    if newest(f"{NAME}_2*_destsplits_{release}.csv") is not None and newest(f"{NAME}_2*_stops_{release}.csv") is not None:
        print("reusing saved destination splits and stops")
        return
    dests_df = scored_pairs(release)[["dest_lat", "dest_lon"]].drop_duplicates().reset_index(drop=True)
    router = Router(release)
    cursor = router.edge_store.getCursor()
    rows = []
    for dest in dests_df.itertuples():
        split = router.split(dest.dest_lat, dest.dest_lon)
        cursor.seek(int(split.edge))
        rows.append({"dest_lat": dest.dest_lat, "dest_lon": dest.dest_lon, "split_lat": split.fixedLat / FIXED_DEGREES,
                     "split_lon": split.fixedLon / FIXED_DEGREES, "split_off_m": split.distanceToEdge_mm / MM_PER_M,
                     "split_osm_id": int(cursor.getOSMID())})
    pd.DataFrame(rows).to_csv(splits_path, index=False)
    transit_layer = router.network._transport_network.transitLayer
    stops = []
    for stop in range(transit_layer.getStopCount()):
        coordinate = transit_layer.getCoordinateForStopFixed(stop)
        stops.append({"stop": stop, "stop_lat": coordinate.y / FIXED_DEGREES, "stop_lon": coordinate.x / FIXED_DEGREES})
    pd.DataFrame(stops).to_csv(stops_path, index=False)
    print(f"{len(rows)} destination splits -> {splits_path.name}; {len(stops)} stops -> {stops_path.name}")


def stop_links(release):
    """R5's link distance of every transit stop on the v2 network (findSplit at STOP_LINK_RADIUS_M, then SPLIT_RADIUS_M),
    for the stub direction rule (b5; one JVM)."""
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_stoplinks_{release}.csv"
    if newest(f"{NAME}_2*_stoplinks_{release}.csv") is not None:
        print("reusing saved stop links")
        return
    router = Router(release)
    transit_layer = router.network._transport_network.transitLayer
    rows = []
    for stop in range(transit_layer.getStopCount()):
        coordinate = transit_layer.getCoordinateForStopFixed(stop)
        lat, lon = coordinate.y / FIXED_DEGREES, coordinate.x / FIXED_DEGREES
        split = (router.street_layer.findSplit(lat, lon, STOP_LINK_RADIUS_M, router.walk_mode)
                 or router.street_layer.findSplit(lat, lon, SPLIT_RADIUS_M, router.walk_mode))
        rows.append({"stop": stop, "link_m": split.distanceToEdge_mm / MM_PER_M if split is not None else np.inf})
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"{len(rows)} stop links -> {path.name}")


def origin_splits(release):
    """R5's split of every scored origin on the v2 network (no stubs): the (a) origin. On the stub network an origin can
    sit nearer a stub tip than its street (full b4 checks: 42 / 1,246 on 2026-10-09), so it is snapped here (one JVM)."""
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_originsplits_{release}.csv"
    if newest(f"{NAME}_2*_originsplits_{release}.csv") is not None:
        print("reusing saved origin splits")
        return
    origins_df = scored_pairs(release)[["origin_lat", "origin_lon"]].drop_duplicates().reset_index(drop=True)
    router = Router(release)
    rows = []
    for origin in origins_df.itertuples():
        split = router.split(origin.origin_lat, origin.origin_lon)
        rows.append({"origin_lat": origin.origin_lat, "origin_lon": origin.origin_lon,
                     "split_lat": split.fixedLat / FIXED_DEGREES, "split_lon": split.fixedLon / FIXED_DEGREES})
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"{len(rows)} origin splits -> {path.name}")


def build_stubs(release, mode="full"):
    """Run 3 network: v2's derived extract of the release plus destination stubs (docstring, run 3)."""
    import osmium
    speeds = stub_speeds(mode)
    pbf, table, tag = stub_paths(release, speeds)
    if pbf is not None and table is not None:
        print(f"reusing {pbf.name} and {table.name}")
        return
    started = datetime.datetime.now()
    source_pbf, _ = network_paths(release)
    splits_path, stops_path = newest(f"{NAME}_2*_destsplits_{release}.csv"), newest(f"{NAME}_2*_stops_{release}.csv")
    assert splits_path is not None and stops_path is not None, "dest_splits first"
    print(f"reusing {splits_path.name}, {stops_path.name}", flush=True)
    dests_df = pd.read_csv(splits_path)
    stops_df = pd.read_csv(stops_path)
    links_path = newest(f"{NAME}_2*_stoplinks_{release}.csv")
    if links_path is not None and STUB_BUILD[release] != "b4":
        print(f"reusing {links_path.name}", flush=True)
        stops_df = stops_df.merge(pd.read_csv(links_path)[["stop", "link_m"]], on="stop", validate="one_to_one")
    ways, max_ids = candidate_ways(source_pbf, dests_df.dest_lat.to_numpy(), dests_df.dest_lon.to_numpy(),
                                   set(dests_df.split_osm_id))
    assert max_ids["node"] < NEW_NODE_ID_BASE and max_ids["way"] < NEW_WAY_ID_BASE, f"new id bases collide: {max_ids}"
    segments = segment_table(ways)
    print(f"{len(dests_df)} destinations; {len(ways)} candidate ways, {len(segments['index'])} segments; max ids {max_ids}; "
          f"{datetime.datetime.now() - started}", flush=True)
    body_s, tip_s = OFFSET_S - 1 - STUB_EPS_S, 1 - STUB_EPS_S
    counter = {"node": NEW_NODE_ID_BASE, "way": NEW_WAY_ID_BASE}
    new_nodes, new_ways, splices, rows = [], [], {}, []

    def add_node(lat, lon):
        counter["node"] += 1
        new_nodes.append((counter["node"], round(lat, 7), round(lon, 7)))
        return counter["node"]

    def add_way(node_ids, tags):
        counter["way"] += 1
        new_ways.append((counter["way"], node_ids, {**tags, TAG_SOURCE[0]: TAG_SOURCE[1]}))
        return counter["way"]

    angles = 2 * np.pi * np.arange(STUB_DIRECTIONS) / STUB_DIRECTIONS
    by_length = sorted(speeds.items(), key=lambda item: -item[1])
    stubs_of_base = {}                             # destinations sharing R5's split point share its stubs
    for dest in dests_df.itertuples():
        row = {"dest_lat": dest.dest_lat, "dest_lon": dest.dest_lon, "base_lat": dest.split_lat, "base_lon": dest.split_lon,
               "base_off_m": dest.split_off_m}
        base_key = (dest.split_lat, dest.split_lon)
        if base_key in stubs_of_base:
            rows += [{**row, **stub} for stub in stubs_of_base[base_key]]
            continue
        if dest.split_osm_id not in ways:
            rows.append({**row, "status": "split way not read"})
            continue
        refs, lats, lons, _ = ways[dest.split_osm_id]
        one_way = {"lat1": lats[:-1], "lon1": lons[:-1], "lat2": lats[1:], "lon2": lons[1:]}
        on_way_m, nearest, t = point_distances([0.0], [0.0], one_way, dest.split_lat, dest.split_lon)
        if on_way_m[0] > BASE_ON_WAY_TOL_M:
            rows.append({**row, "status": f"split {on_way_m[0]:.2f} m off its way"})
            continue
        segment, t = int(nearest[0]), float(t[0])
        base_lat, base_lon = dest.split_lat, dest.split_lon
        end_x, end_y = local_xy([lats[segment], lats[segment + 1]], [lons[segment], lons[segment + 1]], base_lat, base_lon)
        end_distance = np.hypot(end_x, end_y)
        if end_distance.min() <= SNAP_M:
            base_node = refs[segment + int(np.argmin(end_distance))]
        else:
            base_node = add_node(base_lat, base_lon)
            splices.setdefault(dest.split_osm_id, []).append((segment, t, base_node))
        local = local_segments(base_lat, base_lon, segments)
        walk_local = {name: values[local["is_walk"]] for name, values in local.items()}
        is_near_stop = ((stops_df.stop_lat - base_lat).abs() <= LOCAL_DEG) & ((stops_df.stop_lon - base_lon).abs() <= LOCAL_DEG)
        near_stops = stops_df[is_near_stop]
        stop_x, stop_y = local_xy(near_stops.stop_lat.to_numpy(), near_stops.stop_lon.to_numpy(), base_lat, base_lon)
        if "link_m" in near_stops:                 # R5's own stop links (stop_links), from b5
            stop_link_m = near_stops.link_m.to_numpy()
        else:                                      # b4: estimated from the candidate ways (missed one stop, Box Hill)
            stop_link_m = (point_distances(stop_x, stop_y, walk_local, base_lat, base_lon)[0]
                           if len(near_stops) and len(walk_local["index"]) else np.full(len(near_stops), np.inf))
        used, stubs = set(), []
        for speed_tag, speed_kmh in by_length:
            speed_ms = speed_kmh * M_PER_KM / SECONDS_PER_HOUR
            body_m, length_m = body_s * speed_ms, (body_s + tip_s) * speed_ms
            steps = np.append(np.arange(CLEARANCE_STEP_M, length_m, CLEARANCE_STEP_M), length_m)
            best = None
            for k, angle in enumerate(angles):
                if k in used:
                    continue
                px, py = steps * math.cos(angle), steps * math.sin(angle)
                clearance = float(point_distances(px, py, local, base_lat, base_lon)[0].min())
                tip_x, tip_y = length_m * math.cos(angle), length_m * math.sin(angle)
                is_stop_safe = bool(np.all(np.hypot(stop_x - tip_x, stop_y - tip_y) > stop_link_m + STOP_MARGIN_M))
                score = (is_stop_safe, clearance)
                if best is None or score > best[0]:
                    best = (score, k, angle)
            (is_stop_safe, clearance), k, angle = best
            used.add(k)
            body_lat, body_lon = from_xy(body_m * math.cos(angle), body_m * math.sin(angle), base_lat, base_lon)
            tip_lat, tip_lon = from_xy(length_m * math.cos(angle), length_m * math.sin(angle), base_lat, base_lon)
            body_node, tip_node = add_node(body_lat, body_lon), add_node(tip_lat, tip_lon)
            body_way = add_way([base_node, body_node], {"highway": "footway", "tunnel": "yes"})
            tip_way = add_way([body_node, tip_node], {"highway": "footway"})
            stubs.append({"status": "ok", "speed_tag": speed_tag, "speed_kmh": speed_kmh, "length_m": length_m,
                          "tip_lat": round(tip_lat, 7), "tip_lon": round(tip_lon, 7), "body_way": body_way,
                          "tip_way": tip_way, "clearance_m": clearance, "is_stop_safe": is_stop_safe})
        stubs_of_base[base_key] = stubs
        rows += [{**row, **stub} for stub in stubs]
    stubs_df = pd.DataFrame(rows)
    run = f"{datetime.date.today():%Y%m%d}"
    pbf = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run}_osm_{release}_{tag}.osm.pbf"
    writer = osmium.SimpleWriter(str(pbf))
    state = {"nodes": False, "ways": False}

    def flush_nodes():
        for node_id, lat, lon in new_nodes:
            writer.add_node(osmium.osm.mutable.Node(id=node_id, location=(lon, lat), version=1, tags={}))
        state["nodes"] = True

    def flush_ways():
        for way_id, node_ids, tags in new_ways:
            writer.add_way(osmium.osm.mutable.Way(id=way_id, nodes=node_ids, version=1, tags=tags))
        state["ways"] = True

    try:
        for obj in osmium.FileProcessor(str(source_pbf)):
            if obj.is_way() and not state["nodes"]:
                flush_nodes()
            if obj.is_relation() and not state["ways"]:
                flush_ways()
            if obj.is_way() and obj.id in splices:
                refs = [node.ref for node in obj.nodes]
                assert refs == ways[obj.id][0], f"way {obj.id}: node list differs from the first pass"
                writer.add_way(obj.replace(nodes=spliced_nodes(refs, splices[obj.id])))
            else:
                writer.add(obj)
        if not state["nodes"]:
            flush_nodes()
        if not state["ways"]:
            flush_ways()
    finally:
        writer.close()
    stubs_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run}_stubs_{release}_{tag}.csv", index=False)
    ok = stubs_df[stubs_df.status == "ok"]
    text = (f"{NAME} {run} build_stubs {release} ({mode}, speeds {speeds}): {len(dests_df)} destinations, stubs {len(ok)}, "
            f"not built {int((stubs_df.status != 'ok').sum())}; ways spliced {len(splices)}, new nodes {len(new_nodes)}, new ways "
            f"{len(new_ways)}; base off the original point median {ok.base_off_m.median():.1f} m; clearance median "
            f"{ok.clearance_m.median():.1f} m, min {ok.clearance_m.min():.2f} m; stop-safe {int(ok.is_stop_safe.sum())}/{len(ok)}; "
            f"not built by status {stubs_df[stubs_df.status != 'ok'].status.value_counts().to_dict()}; -> {pbf.name} in {datetime.datetime.now() - started}")
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run}_stubs_{release}_{tag}_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")


# --- probe -----------------------------------------------------------------------------------------
def probe(release):
    pairs_df = scored_pairs(release)
    router = Router(release)
    speed_ms = BASE_SPEED_KMH * M_PER_KM / SECONDS_PER_HOUR
    expected_m_per_min = SECONDS_PER_MIN * speed_ms
    offsets = np.arange(0, PROBE_MAX_M + PROBE_STEP_M / 2, PROBE_STEP_M)
    is_walk = pairs_df.default_walk_only.astype(bool) & pairs_df.walk_min.notna()
    is_transit = pairs_df.shifted_min.fillna(np.inf) < pairs_df.walk_min.fillna(np.inf)
    lines = [f"{NAME} {run_date()} probe on {release}: offsets 0-{PROBE_MAX_M} m by {PROBE_STEP_M} m; expected "
             f"{expected_m_per_min:.2f} m per minute at {BASE_SPEED_KMH} km/h (1.3 m/s would give {SECONDS_PER_MIN * 1.3:.1f})"]
    rows = []
    for kind, kind_df in [("walk", pairs_df[is_walk]), ("transit", pairs_df[is_transit & ~is_walk])]:
        kept = 0
        for pair in kind_df.head(PROBE_CANDIDATES).itertuples():
            if kept >= PROBE_PAIRS:
                break
            _, _, _, split = router.snapped(pair.dest_lat, pair.dest_lon)
            if split is None:
                continue
            best = None
            for normal in router.normals(split, pair.dest_lat, pair.dest_lon):
                if not all(router.keeps_edge(split, *router.moved(split, normal, offset_m), offset_m)
                           for offset_m in PROBE_SCREEN_M):
                    continue
                points = []
                for offset_m in offsets:
                    lat, lon = router.moved(split, normal, offset_m)
                    if not router.keeps_edge(split, lat, lon, offset_m):
                        break
                    points.append((offset_m, lat, lon))
                if best is None or len(points) > len(best):
                    best = points
            if not best or best[-1][0] < PROBE_MIN_RANGE_M:
                continue
            kept += 1
            origin = router.snapped(pair.origin_lat, pair.origin_lon)[:2]
            departure = (datetime.datetime.combine(datetime.date.fromisoformat(str(pair.own_date)), datetime.time())
                         + datetime.timedelta(minutes=int(pair.dep_min_of_day)))
            modes = ([router.TransportMode.WALK] if kind == "walk"
                     else [router.TransportMode.TRANSIT, router.TransportMode.WALK])
            minutes = router.ttm(origin, [(lat, lon) for _, lat, lon in best], departure, modes, MAX_TIME_MIN, BASE_SPEED_KMH)
            offs = np.array([offset_m for offset_m, _, _ in best])
            steps = np.diff(minutes)
            tick_ix = np.flatnonzero(steps != 0) + 1
            ticks = offs[tick_ix]
            is_unit = bool(np.all(np.isin(steps, [0, 1])))
            rate = (ticks[-1] - ticks[0]) / (len(ticks) - 1) if len(ticks) >= 2 else np.nan
            row = {"kind": kind, "draw_no": pair.draw_no, "range_m": offs[-1], "minutes_at_0": minutes[0],
                   "n_ticks": len(ticks), "ticks_m": ";".join(f"{tick:.2f}" for tick in ticks), "is_unit_steps": is_unit,
                   "m_per_min": rate, "rate_ratio": rate / expected_m_per_min}
            rows.append(row)
            print(f"  {row}", flush=True)
        lines.append(f"{kind}: {kept} probe pairs of {min(len(kind_df), PROBE_CANDIDATES)} candidates")
    probe_df = pd.DataFrame(rows, columns=["kind", "draw_no", "range_m", "minutes_at_0", "n_ticks", "ticks_m", "is_unit_steps", "m_per_min", "rate_ratio"])
    is_two = probe_df.n_ticks >= 2
    is_rate = (probe_df.rate_ratio - 1).abs() <= RATE_TOLERANCE
    p1 = bool(is_two.any() and is_rate[is_two].all() and set(probe_df[is_two].kind) == {"walk", "transit"})
    p2 = bool(probe_df.is_unit_steps.all())

    offset_m = OFFSET_S * speed_ms
    n_keep = n_all = 0
    for pair in pairs_df.itertuples():
        n_all += 1
        n_keep += router.offset_point(pair.dest_lat, pair.dest_lon, offset_m) is not None
    keep_share = n_keep / n_all
    p3 = keep_share >= EDGE_KEEP_MIN
    lines.append(probe_df.to_string(index=False))
    lines.append(f"(P1) metres per minute within {RATE_TOLERANCE:.0%} of {expected_m_per_min:.2f}: {int(is_rate[is_two].sum())} of "
                 f"{int(is_two.sum())} pairs with >= 2 ticks (walk {int((is_two & (probe_df.kind == 'walk')).sum())}, transit "
                 f"{int((is_two & (probe_df.kind == 'transit')).sum())}); rate ratio median {probe_df.rate_ratio.median():.4f}, "
                 f"range {probe_df.rate_ratio.min():.4f}-{probe_df.rate_ratio.max():.4f}: {'PASS' if p1 else 'FAIL'}")
    lines.append(f"(P2) unit steps, never falling: {int(probe_df.is_unit_steps.sum())} of {len(probe_df)}: {'PASS' if p2 else 'FAIL'}")
    lines.append(f"(P3) destinations keeping the edge at a {OFFSET_S} s offset ({offset_m:.2f} m): {n_keep}/{n_all} = "
                 f"{keep_share:.4f} (>= {EDGE_KEEP_MIN}): {'PASS' if p3 else 'FAIL'}")
    lines.append(f"PROBE: {'PASS' if p1 and p2 and p3 else 'FAIL'}")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_probe_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    probe_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_probe.csv", index=False)


# --- speed fit -------------------------------------------------------------------------------------
def walk_only_routes():
    """Per scored pair, Google's walk-only route: the default if walk-only, else the first walk-only alternative."""
    pairs_df = scored_pairs()
    frames = []
    for set_name, path in GOOGLE_ROUTES_PATHS.items():
        routes_df = pd.read_csv(path)
        wanted = set(pairs_df.draw_no[pairs_df.set_name == set_name])
        routes_df = routes_df[routes_df.draw_no.isin(wanted) & routes_df.is_walk_only.astype(bool)]
        routes_df = routes_df.sort_values(["draw_no", "is_default", "route_ix"], ascending=[True, False, True])
        frames.append(routes_df.drop_duplicates("draw_no").assign(set_name=set_name))
    routes_df = pd.concat(frames, ignore_index=True)[["draw_no", "set_name", "route_ix", "is_default", "duration_s", "distance_m"]]
    return routes_df.merge(pairs_df[["draw_no", "release", "origin_lat", "origin_lon", "dest_lat", "dest_lon"]], on="draw_no")


def speedfit(release):
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_speedfit_{release}.csv"
    saved = newest(f"{NAME}_2*_speedfit_{release}.csv")
    if saved is not None:
        print(f"reusing {saved.name}")
        return
    todo_df = walk_only_routes()
    todo_df = todo_df[todo_df.release.astype(str) == release]
    print(f"release {release}: {len(todo_df)} pairs with a Google walk-only route", flush=True)
    router = Router(release)
    from com.conveyal.r5.streets import StreetRouter
    from r5py.r5.regional_task import RegionalTask
    rows = []
    for pair in todo_df.itertuples():
        origin_lat, origin_lon, origin_off_m, _ = router.snapped(pair.origin_lat, pair.origin_lon)
        dest_lat, dest_lon, dest_off_m, _ = router.snapped(pair.dest_lat, pair.dest_lon)
        origin = router.gpd.points_from_xy([origin_lon], [origin_lat], crs="EPSG:4326")[0]
        request = RegionalTask(router.network, origin=origin, destinations=router.gpd.GeoDataFrame(
            {"id": [1]}, crs="EPSG:4326", geometry=router.gpd.points_from_xy([dest_lon], [dest_lat])),
            departure=datetime.datetime(2026, 10, 21, 12), transport_modes=[router.TransportMode.WALK],
            speed_walking=BASE_SPEED_KMH)
        task = request._regional_task
        task.reverseSearch = False
        street_router = StreetRouter(router.street_layer)
        street_router.profileRequest = task
        street_router.streetMode = router.walk_mode
        street_router.timeLimitSeconds = FIT_TIME_LIMIT_S
        street_router.setOrigin(origin_lat, origin_lon)
        street_router.route()
        dest_split = router.split(dest_lat, dest_lon)
        state = street_router.getState(dest_split) if dest_split is not None else None
        rows.append({"draw_no": pair.draw_no, "set_name": pair.set_name, "release": release, "is_default": pair.is_default,
                     "google_s": pair.duration_s, "google_m": pair.distance_m,
                     "origin_offstreet_m": origin_off_m, "dest_offstreet_m": dest_off_m,
                     "dest_offstreet_after_m": dest_split.distanceToEdge_mm / MM_PER_M if dest_split is not None else None,
                     "r5_m": state.distance / MM_PER_M if state is not None else None,
                     "r5_s": state.getDurationSeconds() if state is not None else None})
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"{len(rows)} pairs -> {path.name}", flush=True)


def speedfit_report():
    paths = [newest(f"{NAME}_2*_speedfit_{release}.csv") for release in ["20261009", "20261016"]]
    assert all(paths), "speedfit both releases first"
    df = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)
    usable = df[df.r5_m.notna() & (df.google_s > 0)].copy()
    usable["speed_kmh"] = usable.r5_m / usable.google_s * SECONDS_PER_HOUR / M_PER_KM
    speeds = {"median": round(float(usable.speed_kmh.median()), 3), "mean": round(float(usable.speed_kmh.mean()), 3)}
    defaults = usable[usable.is_default.astype(bool)]
    lines = [f"{NAME} {run_date()} speed fit (b): reusing {[p.name for p in paths]}",
             f"pairs {len(df)}, usable {len(usable)} (defaults {len(defaults)}); by set {usable.set_name.value_counts().to_dict()}",
             f"off-street after snapping: destination max {df.dest_offstreet_after_m.max():.3f} m; removed connectors median "
             f"origin {df.origin_offstreet_m.median():.1f} m, destination {df.dest_offstreet_m.median():.1f} m",
             f"check: R5 m / s median {(usable.r5_m / usable.r5_s).median():.4f} m/s (request {BASE_SPEED_KMH / 3.6:.4f})",
             f"speed R5 snapped metres / Google seconds, km/h: median {speeds['median']:.3f}, mean {speeds['mean']:.3f}, "
             f"quartiles {usable.speed_kmh.quantile(0.25):.3f}/{usable.speed_kmh.quantile(0.75):.3f}; "
             f"defaults only median {defaults.speed_kmh.median():.3f}, mean {defaults.speed_kmh.mean():.3f}; "
             f"ratio of sums {usable.r5_m.sum() / usable.google_s.sum() * 3.6:.3f}",
             f"R5 snapped metres / Google metres: median {(usable.r5_m / usable.google_m).median():.3f}"]
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_speedfit_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_speeds.json").write_text(json.dumps(speeds), encoding="utf-8")


# --- route -----------------------------------------------------------------------------------------
def route(release):
    speeds_path = newest(f"{NAME}_2*_speeds.json")
    assert speeds_path is not None, "speedfit_report first"
    speeds = {"base": BASE_SPEED_KMH, **json.loads(speeds_path.read_text(encoding="utf-8"))}
    print(f"speeds {speeds} (from {speeds_path.name})", flush=True)
    pairs_df = scored_pairs(release)
    saved = newest(f"{NAME}_2*_routes_{release}.csv")
    table_path = saved if saved is not None else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_routes_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"release {release}: {len(pairs_df)} scored pairs; table {table_path.name}, {len(done)} done, {len(todo_df)} to route", flush=True)
    if todo_df.empty:
        return
    router = Router(release)
    run2_df = pd.read_csv(newest(RUN2_SNAP_GLOB.format(release=release))).set_index("draw_no")
    if not done:
        v2_df = pd.read_csv(newest(V2_ROUTES_GLOB.format(release=release))).set_index("draw_no")
        mismatches = 0
        for pair in pairs_df.head(SNAP_CHECK_PAIRS).itertuples():
            got = router.three_calls((pair.origin_lat, pair.origin_lon), [(pair.dest_lat, pair.dest_lon)], pair, BASE_SPEED_KMH)
            for key, values in got.items():
                if not same(values[0], v2_df.at[pair.draw_no, key]):
                    mismatches += 1
                    print(f"  R1 mismatch {pair.draw_no} {key}: {values[0]} vs {v2_df.at[pair.draw_no, key]}", flush=True)
        print(f"(R1) unsnapped {SNAP_CHECK_PAIRS} pairs x 3 calls vs saved v2: {'PASS' if mismatches == 0 else 'FAIL'} ({mismatches})", flush=True)
        assert mismatches == 0, "R1 failed: stop"

    started = datetime.datetime.now()
    r2_mismatches = 0
    for i, pair in enumerate(todo_df.itertuples()):
        origin = router.snapped(pair.origin_lat, pair.origin_lon)[:2]
        dest = router.snapped(pair.dest_lat, pair.dest_lon)[:2]
        row = {"draw_no": pair.draw_no, "set_name": pair.set_name, "release": release}
        for tag in SPEED_TAGS:
            speed_kmh = speeds[tag]
            offset_m = OFFSET_S * speed_kmh * M_PER_KM / SECONDS_PER_HOUR
            moved = router.offset_point(pair.dest_lat, pair.dest_lon, offset_m)
            row[f"is_offset_{tag}"] = moved is not None
            got = router.three_calls(origin, [dest, moved if moved is not None else dest], pair, speed_kmh)
            for key, values in got.items():
                row[f"{key}_{tag}_snap"] = values[0]
                row[f"{key}_{tag}_off"] = values[1]
        for key in ["stock_min", "shifted_min", "walk_min"]:
            if pair.draw_no in run2_df.index and not same(row[f"{key}_base_snap"], run2_df.at[pair.draw_no, key]):
                r2_mismatches += 1
        if i == SNAP_CHECK_PAIRS - 1 and not done:
            print(f"(R2) snapped 4.16 vs run 2 on the first {SNAP_CHECK_PAIRS} pairs: {'PASS' if r2_mismatches == 0 else 'FAIL'} "
                  f"({r2_mismatches})", flush=True)
            assert r2_mismatches == 0, "R2 failed: stop"
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % 200 == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}: {row}", flush=True)
    print(f"(R2) snapped 4.16 vs run 2, all routed pairs: {r2_mismatches} mismatching calls", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


def stub_checks(router, stubs_df, pairs_df, speeds, origin_of):
    """(C1)-(C4) on the stub network (docstring, run 3): (lines, is_pass)."""
    stub_ways = set(stubs_df.body_way) | set(stubs_df.tip_way)
    cursor = router.edge_store.getCursor()
    street_layer = router.street_layer
    transit_layer = router.network._transport_network.transitLayer

    def osm_of(split):
        cursor.seek(int(split.edge))
        return int(cursor.getOSMID())

    bad_stops = 0                                  # a stop whose own split lies on a stub way (R5 links stops by findSplit);
    for stop in range(transit_layer.getStopCount()):   # a stop linked at a stub's base node is fine (b2 check flagged those)
        coordinate = transit_layer.getCoordinateForStopFixed(stop)
        split = street_layer.findSplit(coordinate.y / FIXED_DEGREES, coordinate.x / FIXED_DEGREES, STOP_LINK_RADIUS_M,
                                       router.walk_mode)
        bad_stops += split is not None and osm_of(split) in stub_ways
    tips_ok, tip_offs = 0, []
    for stub in stubs_df.itertuples():
        split = router.split(stub.tip_lat, stub.tip_lon)
        tip_offs.append(split.distanceToEdge_mm / MM_PER_M if split is not None else np.inf)
        tips_ok += split is not None and osm_of(split) == stub.tip_way and split.distanceToEdge_mm <= 50
    origin_bad = sum(osm_of(router.split(*origin_of[(p.origin_lat, p.origin_lon)])) in stub_ways for p in pairs_df.itertuples())
    base_of = {(s.dest_lat, s.dest_lon): (s.base_lat, s.base_lon) for s in stubs_df.itertuples()}
    dest_bad = sum(osm_of(router.split(*base_of[(p.dest_lat, p.dest_lon)])) in stub_ways
                   for p in pairs_df.itertuples() if (p.dest_lat, p.dest_lon) in base_of)
    seconds, base_gaps, length_gaps = [], [], []
    for stub in stubs_df.itertuples():
        walker = street_router(router, stub.base_lat, stub.base_lon, stub.speed_kmh, 10 * OFFSET_S)
        state = walker.getState(router.split(stub.tip_lat, stub.tip_lon))
        base_state = walker.getState(router.split(stub.base_lat, stub.base_lon))   # the start sits ~1 cm along an edge,
        seconds.append(state.getDurationSeconds() - base_state.getDurationSeconds()   # up to 1 s (b3 run: 67 at 31)
                       if state is not None and base_state is not None else np.nan)
        walker_state, stub_mm = state, {}
        while walker_state is not None and walker_state.backEdge >= 0:    # R5's own lengths of the stub's edges
            cursor.seek(walker_state.backEdge)
            stub_mm[int(cursor.getOSMID())] = cursor.getLengthMm()
            walker_state = walker_state.backState
        speed_ms = stub.speed_kmh * M_PER_KM / SECONDS_PER_HOUR
        length_gaps.append((stub_mm.get(stub.body_way, np.nan) / MM_PER_M - (OFFSET_S - 1 - STUB_EPS_S) * speed_ms,
                            stub_mm.get(stub.tip_way, np.nan) / MM_PER_M - (1 - STUB_EPS_S) * speed_ms))
        dest_lat, dest_lon, _, _ = router.snapped(stub.dest_lat, stub.dest_lon)
        base_gaps.append(math.hypot(*local_xy(dest_lat, dest_lon, stub.base_lat, stub.base_lon)))
    seconds, base_gaps = np.array(seconds, dtype=float), np.array(base_gaps)
    is_c4 = np.abs(seconds - OFFSET_S) <= STUB_SECONDS_TOL
    checks = {"C1": bad_stops == 0, "C2": tips_ok == len(stubs_df), "C3": origin_bad == 0 and dest_bad == 0, "C4": bool(is_c4.all())}
    lines = [f"(C1) transit stops whose split lies on a stub way: {bad_stops} of {transit_layer.getStopCount()}: {'PASS' if checks['C1'] else 'FAIL'}",
             f"(C2) stub tips linking to their own tip way within 0.05 m: {tips_ok}/{len(stubs_df)}: {'PASS' if checks['C2'] else 'FAIL'}",
             f"(C3) origins / destinations whose split lies on a stub way: {origin_bad} / {dest_bad} of {len(pairs_df)}: "
             f"{'PASS' if checks['C3'] else 'FAIL'}",
             f"(C4) base -> tip seconds within {OFFSET_S} +- {STUB_SECONDS_TOL}: {int(is_c4.sum())}/{len(seconds)}; values "
             f"{pd.Series(seconds).value_counts().sort_index().to_dict()}: {'PASS' if checks['C4'] else 'FAIL'}",
             f"reported: stub base vs R5's split of the original destination on the stub network: median {np.median(base_gaps):.2f} m, "
             f"> 1 m {np.mean(base_gaps > 1):.3f}, max {base_gaps.max():.1f} m",
             f"reported (C6): R5's edge length minus intended, body: median {np.nanmedian(np.array(length_gaps)[:, 0]) * 100:+.1f} cm, "
             f"range {np.nanmin(np.array(length_gaps)[:, 0]) * 100:+.1f} to {np.nanmax(np.array(length_gaps)[:, 0]) * 100:+.1f} cm; tip: median "
             f"{np.nanmedian(np.array(length_gaps)[:, 1]) * 100:+.1f} cm, range {np.nanmin(np.array(length_gaps)[:, 1]) * 100:+.1f} to "
             f"{np.nanmax(np.array(length_gaps)[:, 1]) * 100:+.1f} cm"]
    return lines, all(checks.values())


def route_stubs(release, mode="full"):
    """Run 3 routing on the stub network (docstring); quick mode: QUICK_PAIRS pairs, 4.16 only, plus (C5)."""
    speeds = stub_speeds(mode)
    pbf, table, tag = stub_paths(release, speeds)
    assert pbf is not None and table is not None, "build_stubs first"
    stubs_all = pd.read_csv(table)
    stubs_all = stubs_all[stubs_all.status == "ok"]
    pairs_df = scored_pairs(release)
    if mode == "quick":
        pairs_df = pairs_df.head(QUICK_PAIRS)
    keys = set(zip(pairs_df.dest_lat, pairs_df.dest_lon))
    stubs_df = stubs_all[[key in keys for key in zip(stubs_all.dest_lat, stubs_all.dest_lon)]]
    tip_of = {(s.dest_lat, s.dest_lon, s.speed_tag): (s.tip_lat, s.tip_lon) for s in stubs_df.itertuples()}
    base_of = {(s.dest_lat, s.dest_lon): (s.base_lat, s.base_lon) for s in stubs_df.itertuples()}   # (a): R5's split on v2
    origin_path = newest(f"{NAME}_2*_originsplits_{release}.csv")
    assert origin_path is not None, "origin_splits first"
    origin_of = {(o.origin_lat, o.origin_lon): (o.split_lat, o.split_lon) for o in pd.read_csv(origin_path).itertuples()}
    saved = newest(f"{NAME}_2*_stubroutes_{mode}_{release}_{tag}.csv")
    table_path = saved if saved is not None else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_stubroutes_{mode}_{release}_{tag}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"release {release} ({mode}): {len(pairs_df)} pairs, {len(stubs_df)} stubs; table {table_path.name}, {len(done)} done, "
          f"{len(todo_df)} to route; reusing {pbf.name}", flush=True)
    router = Router(release, pbf)
    if not done:
        lines, is_pass = stub_checks(router, stubs_df, pairs_df, speeds, origin_of)
        text = "\n".join([f"{NAME} {run_date()} stub checks {release} ({mode}, {pbf.name})"] + lines
                         + [f"CHECKS: {'PASS' if is_pass else 'FAIL'}"])
        print(text, flush=True)
        (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_stubchecks_{mode}_{release}_{tag}.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
        assert is_pass, "stub checks failed: stop"
        v2_df = pd.read_csv(newest(V2_ROUTES_GLOB.format(release=release))).set_index("draw_no")
        mismatches, skipped = 0, 0
        stub_ways = set(stubs_all.body_way) | set(stubs_all.tip_way)
        cursor = router.edge_store.getCursor()
        for pair in pairs_df.head(SNAP_CHECK_PAIRS).itertuples():
            is_on_stub = False                                     # an original point nearer a stub tip than its street
            for lat, lon in [(pair.dest_lat, pair.dest_lon), (pair.origin_lat, pair.origin_lon)]:   # links to the tip;
                cursor.seek(int(router.split(lat, lon).edge))      # never routed (b3: destinations 269, 316, 520; b5:
                is_on_stub |= int(cursor.getOSMID()) in stub_ways  # origins too); R2 checks the routed points
            if is_on_stub:
                print(f"  R1 skipped {pair.draw_no}: an original point links to a stub", flush=True)
                skipped += 1
                continue
            got = router.three_calls((pair.origin_lat, pair.origin_lon), [(pair.dest_lat, pair.dest_lon)], pair, BASE_SPEED_KMH)
            for key, values in got.items():
                if not same(values[0], v2_df.at[pair.draw_no, key]):
                    mismatches += 1
                    print(f"  R1 mismatch {pair.draw_no} {key}: {values[0]} vs {v2_df.at[pair.draw_no, key]}", flush=True)
        print(f"(R1) unsnapped {SNAP_CHECK_PAIRS} pairs x 3 calls on the stub network vs saved v2: "
              f"{'PASS' if mismatches <= R1_MAX_MISMATCHES else 'FAIL'} ({mismatches}, at most {R1_MAX_MISMATCHES}; skipped, "
              f"an original point on a stub: {skipped})", flush=True)
        assert mismatches <= R1_MAX_MISMATCHES, "R1 failed: stop"
    run2_df = pd.read_csv(newest(RUN2_SNAP_GLOB.format(release=release))).set_index("draw_no")
    started = datetime.datetime.now()
    r2_mismatches = 0
    for i, pair in enumerate(todo_df.itertuples()):
        origin = origin_of[(pair.origin_lat, pair.origin_lon)]          # (a): R5's split on v2 (no stubs)
        dest = base_of.get((pair.dest_lat, pair.dest_lon)) or router.snapped(pair.dest_lat, pair.dest_lon)[:2]
        row = {"draw_no": pair.draw_no, "set_name": pair.set_name, "release": release}
        for speed_tag, speed_kmh in speeds.items():
            tip = tip_of.get((pair.dest_lat, pair.dest_lon, speed_tag))
            row[f"is_offset_{speed_tag}"] = tip is not None
            got = router.three_calls(origin, [dest, tip if tip is not None else dest], pair, speed_kmh)
            for key, values in got.items():
                row[f"{key}_{speed_tag}_snap"] = values[0]
                row[f"{key}_{speed_tag}_off"] = values[1]
        for key in ["stock_min", "shifted_min", "walk_min"]:
            if pair.draw_no in run2_df.index and not same(row[f"{key}_base_snap"], run2_df.at[pair.draw_no, key]):
                r2_mismatches += 1
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % 200 == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}", flush=True)
    print(f"(R2) snapped 4.16 on the stub network vs run 2: {r2_mismatches} mismatching calls of {3 * len(todo_df)}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)
    if mode == "quick":
        df = pd.read_csv(table_path)
        lines = [f"{NAME} {run_date()} quick run 3 report {release}: {len(df)} pairs, {table_path.name}"]
        for key in ["stock_min", "shifted_min", "walk_min"]:
            diff = (df[f"{key}_base_off"] - df[f"{key}_base_snap"]).dropna()
            lines.append(f"(C5) {key}: tip - snapped minutes {diff.value_counts().sort_index().to_dict()} (n {len(diff)}); "
                         f"+1 share {np.mean(diff == 1):.3f}; outside {{0, +1}} {int((~diff.isin([0, 1])).sum())}")
        snap_nw = no_wait_min(df.shifted_min_base_snap, df.walk_min_base_snap)
        off_nw = no_wait_min(df.shifted_min_base_off, df.walk_min_base_off)
        finite = np.isfinite(snap_nw) & np.isfinite(off_nw)
        lines.append(f"no-wait model, (a)+(c) - (a): mean {np.mean(off_nw[finite] - snap_nw[finite]):+.3f} min, "
                     f"later on {np.mean(off_nw[finite] > snap_nw[finite]):.3f}")
        text = "\n".join(lines)
        print(text)
        (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_quick_{release}_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")


# --- score -----------------------------------------------------------------------------------------
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


def distance_to_range(r5_min, low, high):
    return np.where(r5_min < low, r5_min - low, np.where(r5_min > high, r5_min - high, 0.0))


def label_of(minutes, low, high):
    distance = distance_to_range(minutes, low, high)
    return np.where(distance > 0, "late", np.where(distance < 0, "early", "agree"))


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


def zone_lines(google, model, errors, rng):
    """TRN-13 zone measures on Google's rounded minutes (transit_band_metric.zone_block, gating checks only)."""
    from scipy.stats import binomtest
    lines, failures = [], []
    for zone_no, cut_min in CUTS_MIN.items():
        low_min, high_min = ZONES_MIN[zone_no]
        in_zone = (google >= low_min) & (google <= high_min)
        g, r = google[in_zone], model[in_zone]
        both = int(((g <= cut_min) & (r <= cut_min)).sum())
        rec_n, prec_n = int((g <= cut_min).sum()), int((r <= cut_min).sum())
        rec_low, rec_high = wilson(both, rec_n)
        prec_low, prec_high = wilson(both, prec_n)
        sim_recall, sim_precision = [], []
        for _ in range(N_SIMULATIONS):
            sim = g + rng.choice(errors, size=len(g), replace=True)
            sim_both = ((g <= cut_min) & (sim <= cut_min)).sum()
            sim_recall.append(sim_both / rec_n if rec_n else np.nan)
            n_sim_below = (sim <= cut_min).sum()
            sim_precision.append(sim_both / n_sim_below if n_sim_below else np.nan)
        bar_recall, bar_precision = np.nanmedian(sim_recall), np.nanmedian(sim_precision)
        n_early = int(((r <= cut_min) & (g > cut_min)).sum())
        n_late = int(((r > cut_min) & (g <= cut_min)).sum())
        sign_p = binomtest(n_early, n_early + n_late, 0.5).pvalue if n_early + n_late else 1.0
        gap = abs(both / rec_n - both / prec_n)
        checks = {"floor": rec_low > FLOOR and prec_low > FLOOR,
                  "noise bar": rec_high >= bar_recall and prec_high >= bar_precision,
                  "balance": sign_p >= SIGN_TEST_ALPHA and gap <= CLOSE_TOLERANCE}
        failures += [f"z{zone_no} {name}" for name, is_pass in checks.items() if not is_pass]
        lines.append(f"    zone {zone_no} (n {int(in_zone.sum())}): recall {both / rec_n:.3f} ({rec_low:.3f}-{rec_high:.3f}), precision "
                     f"{both / prec_n:.3f} ({prec_low:.3f}-{prec_high:.3f}); bar {bar_recall:.3f}/{bar_precision:.3f}; misses early "
                     f"{n_early} / late {n_late} (p {sign_p:.3f}), gap {gap:.3f}; "
                     + ", ".join(f"{name} {'pass' if is_pass else 'FAIL'}" for name, is_pass in checks.items()))
    return lines, failures


def score():
    paths = [newest(f"{NAME}_2*_stubroutes_full_{release}_*_{STUB_BUILD[release]}.csv") for release in ["20261009", "20261016"]]   # run 3
    assert all(paths), "route both releases first"
    base_path = newest(RANGE_RESULTS_GLOB)
    base_df = scored_pairs()
    routes_df = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)
    df = base_df.merge(routes_df.drop(columns=["set_name", "release"]), on="draw_no", validate="one_to_one")
    speeds = json.loads(newest(f"{NAME}_2*_speeds.json").read_text(encoding="utf-8"))
    lines = [f"{NAME} {run_date()} score: reusing {[p.name for p in paths]}; baseline {base_path.name}; speeds {speeds}",
             f"pairs {len(df)} of {len(base_df)} scored; offset kept the edge: "
             + ", ".join(f"{tag} {int(df[f'is_offset_{tag}'].sum())}" for tag in SPEED_TAGS)]
    low, high = df.low_2.to_numpy(), df.default_min.to_numpy()
    google = df.google_min.to_numpy()
    is_random = (df.set_name != TOPUP_SET).to_numpy()
    base_min = df.n_min.fillna(np.inf).to_numpy()
    recomputed = no_wait_min(df.shifted_min, df.walk_min)
    lines.append(f"check: baseline recomputed from saved shifted / walk = n_min: "
                 f"{'OK' if np.array_equal(np.nan_to_num(recomputed, posinf=-1), np.nan_to_num(base_min, posinf=-1)) else 'MISMATCH'}")
    variants = {"baseline": base_min,
                "(a) snap 4.16": no_wait_min(df.shifted_min_base_snap, df.walk_min_base_snap),
                "(a)+(c) 4.16": no_wait_min(df.shifted_min_base_off, df.walk_min_base_off),
                f"(a)+(b) median {speeds['median']}": no_wait_min(df.shifted_min_median_snap, df.walk_min_median_snap),
                f"(a)+(b) mean {speeds['mean']}": no_wait_min(df.shifted_min_mean_snap, df.walk_min_mean_snap),
                f"(a)+(b)+(c) median {speeds['median']}": no_wait_min(df.shifted_min_median_off, df.walk_min_median_off),
                f"(a)+(b)+(c) mean {speeds['mean']}": no_wait_min(df.shifted_min_mean_off, df.walk_min_mean_off)}
    is_walk_default = df.default_walk_only.astype(bool).to_numpy()
    base_hard = hard_counts(base_min[is_random], low[is_random], high[is_random])
    base_total = sum(k for k, _, _ in base_hard.values())
    readings = {}
    for label, minutes in variants.items():
        rng = np.random.default_rng(SIMULATION_SEED)
        finite = np.isfinite(minutes)
        distance = distance_to_range(minutes, low, high)
        labels = pd.Series(label_of(minutes, low, high)).value_counts().reindex(LABELS, fill_value=0).to_dict()
        hard = hard_counts(minutes[is_random], low[is_random], high[is_random])
        total = sum(k for k, _, _ in hard.values())
        worst_gain = max(hard[test][0] - base_hard[test][0] for test in hard)
        reading = ("-" if label == "baseline" else "IMPROVES" if total < base_total and worst_gain <= SNAP_TOLERANCE_MISSES
                   else "WORSENS" if total > base_total else "MIXED")
        readings[label] = (total, worst_gain, reading)
        shift = minutes[finite & np.isfinite(base_min)] - base_min[finite & np.isfinite(base_min)]
        away = np.isfinite(minutes) & np.logical_or.reduce([(google >= a) & (google <= b) for a, b in AWAY_RANGES_MIN])
        errors = (minutes - google)[away]
        walk_error = (minutes - df.default_min.to_numpy())[is_walk_default & finite]
        zone_text, zone_failures = zone_lines(google, minutes, errors - np.median(errors), rng)
        ratios = [((minutes[is_random] <= cut).sum() / (google[is_random] <= cut).sum()) for cut in CUTS_MIN.values()]
        lines += ["", f"{label}:",
                  f"  labels {labels}; error to range median {np.median(distance[finite]):+.1f}, mean {distance[finite].mean():+.2f}; "
                  f"minus baseline mean {shift.mean():+.3f} (earlier {np.mean(shift < 0):.3f}, later {np.mean(shift > 0):.3f}); "
                  f"band calls changed {int((band_of(minutes) != band_of(base_min)).sum())}",
                  "  hard: " + "; ".join(f"{test} {k}/{n} (upper {upper:.3f}{' FAIL' if upper > HARD_MISS_MAX else ''})"
                                         for test, (k, n, upper) in hard.items())
                  + f"; total {total} (largest gain {worst_gain:+d}) -> {reading}",
                  f"  off-cut error vs Google rounded (n {len(errors)}): median {np.median(errors):+.1f}, mean {errors.mean():+.2f}; "
                  f"count ratio <= 10 {ratios[0]:.3f}, <= 20 {ratios[1]:.3f}"
                  + "".join(" FAIL" if not COUNT_RATIO_RANGE[0] <= ratio <= COUNT_RATIO_RANGE[1] else "" for ratio in ratios),
                  f"  walk-only defaults (n {len(walk_error)}): error mean {walk_error.mean():+.2f}, median {np.median(walk_error):+.0f}, "
                  f"exact {np.mean(walk_error == 0):.3f}"]
        lines += zone_text
        lines.append(f"  zone failures: {', '.join(zone_failures) if zone_failures else 'none'}")
    lines += ["", "READINGS (Claude's rule, OK'd by the user 2026-10-21): hard misses total vs baseline "
              f"{base_total}, largest gain in one test, reading"]
    lines += [f"  {label}: {total} ({gain:+d}) {reading}" for label, (total, gain, reading) in readings.items()]
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    out_df = df[["draw_no", "set_name", "release", "google_min", "low_2", "default_min"]].copy()
    for label, minutes in variants.items():
        out_df[label] = minutes
    out_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_pairs.csv", index=False)


if __name__ == "__main__":
    {"probe": probe, "speedfit": speedfit, "speedfit_report": speedfit_report, "route": route,
     "dest_splits": dest_splits, "origin_splits": origin_splits, "stop_links": stop_links,
     "build_stubs": build_stubs, "route_stubs": route_stubs,
     "score": score}[sys.argv[1]](*sys.argv[2:])
