"""R5 patch 4 (TRN-16 register): walk time from the path's distance, rounded once per path instead of ceiled per edge.

Claim under test (concepts/transit.md TRN-16; DESIGN.md Q24 (2); evidence for the cause:
diagnostics/transit_r5_edge_rounding.py): R5 charges each walked edge ceil(length / speed) (+0.48 s per edge on
training walks, median 108 edges), so its walks run slower than the walk speed fitted as R5 path / Google seconds
(Q24 (2)). A patch that charges a walk edge the step in round(cumulative path distance / speed) gives R5 walks of
path / speed (ends unchanged), and moves nothing else. Source read 2026-10-21 (inputs/r5py/r5-7.5.1, never edited):
EdgeStore.Edge.traverse takes the edge's seconds from timeCalculator.traversalTimeSeconds (BasicTraversalTimeCalculator:
ceil) and keeps the state's cumulative distance (mm) in State.distance; a zero increment is forced to 1 s (loop guard,
kept: StreetRouter's dominance lets an equal existing state beat a new one, so zero steps could not loop, but the guard
stays as R5 wrote it; its cost is counted). Walk paths affected: walk-only TTM and the access walk to stops (StreetRouter);
egress and stop-to-stop transfers already use distance tables (distance / speed), unchanged.
Where the pipeline would rely on it: transit bands 1-2 through the patched jar.

The patch, one site in EdgeStore.Edge.traverse after the stock seconds, through a private helper in Edge:
  walkSecondsFromPathDistance(s0, streetMode, req, timeCalculator, stockSeconds) = round((s0.distance + length_mm) /
  1000 / speed) - round(s0.distance / 1000 / speed) when the constant is on, the mode is WALK on both states and the
  calculator is BasicTraversalTimeCalculator; else stockSeconds. Math.round = half up. Telescoping: a path's edges
  cost round(D_end / v) - round(D_start / v) plus any forced 1 s steps.
Variants, every jar P2's jar (P1 + P3 + P2) with EdgeStore's classes replaced:
  recompiled  EdgeStore compiled from the unchanged source.
  off         the patched code with the constant off (the new code path, stock behaviour).
  p4          the patch on.

Steps (one JVM per process, jar chosen at JVM start through r5py's `--r5-classpath`):
  build  javac 21 against P2's jar, per variant into its own copy of that jar in outputs/r5_patches/. (B1) recompiled =
      the jar's EdgeStore classes, javap -c -p identical, else stop. (B2) off and p4 vs the jar: the differing javap
      lines, pool indices masked (expected: the helper and its constant in EdgeStore$Edge, one call in traverse; off and
      p4 differ only in the constant). (B3) serialver of EdgeStore equal in P2's jar and each variant's, else stop.
  route <variant> <release>  The seeded 100-pair set of transit_r5_patch_seconds.py (never redrawn), drawn points,
      pathways v2 network of the release, 4.143 km/h; transit at t (max_time MAX_TIME_MIN) and walk-only. Guard:
      EdgeStore, EdgeStore$Edge, StreetRouter, LinkedPointSet, FastRaptorWorker load from the variant's jar.
  walkcheck <release>  p4's jar: each of the 100 pairs' walk-only path rebuilt as transit_r5_edge_rounding.py does,
      with p4's arithmetic.
  score  Rules (Claude's; TRN-16 register; written before any result). Baseline = P2's saved 100-pair routes on the
      drawn points (transit_r5_patch_connector.py route p2 orig; the same jar, points and network).
      (T1) recompiled = baseline, every value (NaN = NaN). Any difference fails.
      (T2) off = baseline, every value. Any difference fails.
      (T3) p4 <= baseline on every value (charging less never arrives later; walk can exceed only by the final
           rounding on a path whose ceil excess is under 1 s). < MINOR_SHARE of pairs flagged minor, else fails.
      (T4) walkcheck: rebuilt = p4's TTM walk seconds on every pair, and every edge increment = max(1, round step).
           Any difference fails.
      (T5) walkcheck: p4 walk excess over path / speed, |median| <= END_TOLERANCE_S (ends only, as the rounding test
           found ~-1.4 s), forced 1 s steps counted.
      (R, reported) saving = baseline - p4 (s) by stratum and call: n, mean, median, max.
  Predictions (Claude's, before any result): B1, B3 pass; B2 shows one helper, one constant, one call. T1, T2
  exact. T3 holds (0 or 1 pair). T4 exact. T5 median ~-1 s, forced steps < 1 per path. R: walk saving median ~15-50 s
  by stratum (walk_only ~14 s, near_max larger); transit saving smaller in seconds (access walk only), a few large
  where a vehicle is caught.

Conclusion (run 2026-10-21; rules above written before any result):
  B1 PASS (0 differing javap lines over EdgeStore's 5 classes). B2 as predicted: the constant, one call in traverse,
  the helper (off: javac folded it to `iload 5; ireturn`, the stock seconds). B3 PASS (serialVersionUID
  8096937624519883587 in all jars). T1 PASS, T2 PASS (0 of 200 values each). T3 PASS (p4 never later). T4 PASS
  (rebuilt = TTM on every pair; 0 of 7,658 edge increments off). T5 PASS: excess over path / speed median -1.20 s,
  mean -0.99, range -2.88 to +4.01 (66 walk paths); forced 1 s steps 27 over 7,658 edges (0.41 per path).
  (R) walk saving median 54 s (walk_only 16, one_boarding 55, transfers 65, near_max 91.5; max 120). Transit saving
  median 0 in every stratum but walk_only (15 s, where the walk wins): a shorter access walk moves the arrival only
  when it catches an earlier vehicle (one pair, 360 s).
  Prediction check: all checks as predicted; walk savings above the predicted 15-50 s on the longer strata (they walk
  further than walk_only pairs); transit as predicted.

Full training run (TRN-16 verdict; rule written before the run, as P2's and P3's, user go 2026-10-21). Pairs: every
scored training pair (v2's range results: train half, second batch, top-up; test half closed), drawn points, v2
network of its release, 4.143 km/h. `route_train <release>`: P4's jar, transit at t and walk-only per pair; rows
appended per pair, a rerun resumes. `score_train`: baseline = P2's saved full run (transit_r5_patch_connector.py
route_train p2orig: same pairs, points, network, the model of record).
  Model per variant: min(transit, walk) in seconds, rounded to the nearest minute (half up; SCR-10).
  Check first, else stop: (F1) the 100 pairs routed by `route p4` reproduce exactly, both calls.
  Reported (as P2's score_train): labels to Google's k = 2 range, error to the range (median, mean), the four hard-miss
  tests (random samples only), TRN-13 zones, count ratios, walk-only defaults, seconds error to Google's
  arrival_from_request_s by the boardings of Google's default (0 / 1 / 2+), band calls changed, winner flips; pairs
  whose seconds and minutes change, by size.
  Reading (run 3's rule): IMPROVES if p4's hard-miss total falls below the baseline's and no test gains more than
  SNAP_TOLERANCE_MISSES; WORSENS if it rises; else MIXED.
  Predictions (Claude's, before the run): 0-boarding seconds error median moves toward 0 by ~15 s (rounding test:
  18 -> 4 s on Google-walk pairs), 1 and 2+ boardings move < 5 s; walk-only defaults exact share up; minutes change on
  ~5% of pairs, almost all -1; winner flips transit -> walk a few dozen; hard misses within 2 of 23, lost 10 / lost 20
  down or equal, false 10 / false 20 up or equal; MIXED most likely.
  Conclusion (run 2026-10-21, 3,448 pairs; rule above written before the run): F1 PASS (0 values off). Hard misses
  p2orig -> p4orig: lost 10 0/50 -> 0/50, false 10 2/294 -> 5/294, lost 20 7/248 -> 6/248, false 20 14/503 -> 16/503
  (upper 0.051, now over 0.05); total 23 -> 27, largest gain +3: WORSENS. Labels late / agree / early 790 / 1,492 /
  1,166 -> 740 / 1,480 / 1,228; error to the range median 0 both, mean -1.67 -> -1.83; count ratios <= 10 0.981 ->
  1.068, <= 20 1.042 -> 1.057; zones: zone 2 balance now FAILS (misses early 42 / late 23, p 0.025). Walk-only
  defaults exact 0.422 -> 0.439, mean +0.25 -> -0.02 min. Seconds error vs Google, median (mean): 0 boardings +16
  (+14.8) -> -1 (-2.1) s; 1 boarding -7 (-101) -> -8 (-112); 2+ -20 (-207) -> -23 (-216). Seconds differ on 404 of
  3,424 pairs, all earlier (median -21 s; >= 60 s on 112); minutes on 208 (123 by -1; tail to -46); band calls 20;
  winner flips transit -> walk 19, walk -> transit 8.
  Prediction check: 0-boarding error right (16 -> -1 s); transit moved less than 5 s in median, as predicted, but the
  minute changes (208, ~6%) and their tail of earlier vehicles were larger; hard misses outside the predicted +-2
  (+4), false reach up as predicted, lost reach not down at 10 min. MIXED predicted, WORSENS read.
  Reading (Claude's): P4 does what it claims (Google walks now match to ~1 s), but on transit pairs R5 was already
  early (median -7 / -20 s, means -100 / -200 s), and the per-edge ceiling's extra access walk was partly offsetting
  that; removing it moves transit pairs earlier still and false reach up.

Inputs (read only): P2's jar and saved 100-pair routes, patch 1's pair set, v2 networks and feeds, `inputs/r5py/`
source. Writes jars to outputs/r5_patches/ and tables to diagnostics/diagnostic_data/. Self-contained (CLAUDE.md D1).
No paid API calls. Usage: `python transit_r5_patch_walk_path.py build`, `... route <variant> <release>`,
`... walkcheck <release>`, `... score`, `... route_train <release>`, `... score_train`.
"""
import datetime
import difflib
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
R5_SOURCE_DIR = PROJECT_ROOT / "inputs" / "r5py" / "r5-7.5.1" / "src" / "main" / "java"
PATCH_DIR = PROJECT_ROOT / "outputs" / "r5_patches"
JDK_BIN_DIR = Path(r"C:\Program Files\Java\jdk-21.0.12\bin")
P1_NAME = "transit_r5_patch_seconds"
P2_NAME = "transit_r5_patch_connector"
BASE_JAR_PATH = PATCH_DIR / f"r5-v7.5.1-r5py-all_{P2_NAME}_p2.jar"
P1_PAIRS_PATH = DIAGNOSTIC_DATA_DIR / f"{P1_NAME}_20261021_pairs.csv"
P2_ROUTES_DATE = "20261021"
V2_NAME = "transit_pathway_network_v2"
NAME = "transit_r5_patch_walk_path"

# --- the patch -------------------------------------------------------------------------------------
EDGE_STORE_CLASS = "com.conveyal.r5.streets.EdgeStore"
GUARD_CLASSES = [EDGE_STORE_CLASS, EDGE_STORE_CLASS + "$Edge", "com.conveyal.r5.streets.StreetRouter",
                 "com.conveyal.r5.streets.LinkedPointSet", "com.conveyal.r5.profile.FastRaptorWorker"]
VARIANT_SWITCH = {"off": False, "p4": True}
VARIANTS = ["recompiled"] + list(VARIANT_SWITCH)
TAG = "// PLATICA TRN-16 P4"
SITE_OLD = "            int traverseTimeSeconds = timeCalculator.traversalTimeSeconds(this, streetMode, req);\n"
SITE_NEW = SITE_OLD + ("            traverseTimeSeconds = walkSecondsFromPathDistance(s0, streetMode, req, timeCalculator, "
                       f"traverseTimeSeconds); {TAG}\n")
HELPER_ANCHOR = "        /** Can we turn onto this edge from this state? Also copies still-applicable restrictions forward. */\n"
HELPER_TEMPLATE = """        {tag}: a walk edge costs the step in round(cumulative path distance / speed), so a path's edges cost
        // round(D_end / v) - round(D_start / v) (plus R5's forced 1 s steps) instead of the sum of each edge's ceil.
        private static final boolean WALK_FROM_PATH_DISTANCE = {switch};

        private int walkSecondsFromPathDistance (StreetRouter.State s0, StreetMode streetMode, ProfileRequest req,
                                                 TraversalTimeCalculator timeCalculator, int stockSeconds) {{
            if (!WALK_FROM_PATH_DISTANCE || streetMode != StreetMode.WALK || s0.streetMode != StreetMode.WALK
                    || !(timeCalculator instanceof BasicTraversalTimeCalculator)) {{
                return stockSeconds;
            }}
            double speedMetersPerSecond = calculateSpeed(req, streetMode);
            long secondsBefore = Math.round(s0.distance / 1000d / speedMetersPerSecond);
            long secondsAfter = Math.round((s0.distance + getLengthMm()) / 1000d / speedMetersPerSecond);
            return (int) (secondsAfter - secondsBefore);
        }}

"""
CONST_POOL_REF = re.compile(r"#\d+(:#\d+)?")
CODE_OFFSET = re.compile(r"^\s*\d+: ")
BRANCH_TARGET = re.compile(r"\b(goto|goto_w|if\w*|jsr)\s+\d+")
SWITCH_TARGET = re.compile(r"^\s*(-?\d+|default): \d+$")

# --- values copied from transit_r5_patch_connector.py ----------------------------------------------
RELEASES = ["20261009", "20261016"]
R5_MAX_MEMORY = "7G"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
SPEED_KMH = 4.143                              # Q24 (2) median; user 2026-10-21
MAX_TIME_MIN = 90
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
CALLS = ["transit", "walk"]
MINOR_SHARE = 0.01
SPLIT_RADIUS_M = 1600                          # R5's StreetLayer.LINK_RADIUS_METERS
MM_PER_M = 1000
SECONDS_PER_MIN = 60
SECONDS_PER_HOUR = 3600

# --- walkcheck (values copied from transit_r5_edge_rounding.py) -------------------------------------
MIN_EDGE_INCREMENT_S = 1                       # EdgeStore.traverse: a state never keeps the same time
END_TOLERANCE_S = 2.0                          # (T5) |median| excess over path / speed

# --- full training run (values copied from transit_r5_patch_connector.py) --------------------------
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
GOOGLE_ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                       "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                       "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
GOOGLE_COL = "arrival_from_request_s"          # the scorers' Google quantity (transit_fetch.py google_min)
RANGE_RESULTS_GLOB = f"{V2_NAME}_2*_range_owndate_results.csv"
BASELINE_TRAIN = "p2orig"                      # P2's saved full run, the model of record
TRAIN_VARIANT = "p4orig"
TOPUP_SET = "topup"
SNAP_TOLERANCE_MISSES = 2
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
BOARDING_GROUPS = {0: "0", 1: "1", 2: "2+"}    # Google default's transit steps, 2 and over pooled
DIFF_BINS_S = [(1, 2), (3, 59), (60, np.inf)]  # |p4orig - p2orig| seconds
PROGRESS_EVERY = 500


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def jar_path(variant):
    return PATCH_DIR / f"r5-v7.5.1-r5py-all_{NAME}_{variant}.jar"


def class_file(name):
    return name.replace(".", "/")


def class_names(classes_dir):
    return sorted(p.relative_to(classes_dir).with_suffix("").as_posix().replace("/", ".")
                  for p in classes_dir.rglob("*.class"))


def javap(classpath, names):
    out = subprocess.run([str(JDK_BIN_DIR / "javap"), "-c", "-p", "-cp", str(classpath)] + names,
                         capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def serialver(classpath):
    return subprocess.run([str(JDK_BIN_DIR / "serialver"), "-classpath", str(classpath), EDGE_STORE_CLASS],
                          capture_output=True, text=True, check=True).stdout.strip()


def pool_masked(lines):
    """javap lines with constant-pool indices, code offsets and branch / switch targets masked and whitespace collapsed
    (as P3's B2), so B2 shows code changes, not the renumbering a new method causes."""
    masked = []
    for line in lines:
        line = BRANCH_TARGET.sub(r"\1 L", CODE_OFFSET.sub("", CONST_POOL_REF.sub("#", line)))
        line = SWITCH_TARGET.sub(r"\1: L", line)
        masked.append(" ".join(line.split()))
    return masked


def patched_source(source, is_on):
    for old in (SITE_OLD, HELPER_ANCHOR):
        assert source.count(old) == 1, f"site not found exactly once: {old.strip()}"
    helper = HELPER_TEMPLATE.format(tag=TAG, switch=str(is_on).lower())
    return source.replace(SITE_OLD, SITE_NEW).replace(HELPER_ANCHOR, helper + HELPER_ANCHOR)


def diff_lines(a, b):
    return [line for line in difflib.unified_diff(a, b, n=0, lineterm="") if not line.startswith(("---", "+++"))]


# --- build -----------------------------------------------------------------------------------------
def build():
    assert BASE_JAR_PATH.exists(), "P2's jar missing: run transit_r5_patch_connector.py build"
    source = (R5_SOURCE_DIR / f"{class_file(EDGE_STORE_CLASS)}.java").read_text(encoding="utf-8")
    lines = [f"{NAME} {run_date()} build (base: {BASE_JAR_PATH.name})"]
    base_serial = serialver(BASE_JAR_PATH)
    texts = {"recompiled": source}
    texts.update({v: patched_source(source, is_on) for v, is_on in VARIANT_SWITCH.items()})
    is_ok = True
    for variant, text in texts.items():
        variant_dir = PATCH_DIR / f"{NAME}_{variant}"
        classes_dir = variant_dir / "classes"
        classes_dir.mkdir(parents=True, exist_ok=True)
        src_path = variant_dir / "src" / f"{class_file(EDGE_STORE_CLASS)}.java"
        src_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.write_text(text, encoding="utf-8", newline="\n")
        subprocess.run([str(JDK_BIN_DIR / "javac"), "--release", "21", "-proc:none", "-nowarn", "-cp", str(BASE_JAR_PATH),
                        "-d", str(classes_dir), str(src_path)], check=True)
        names = class_names(classes_dir)
        assert all(n == EDGE_STORE_CLASS or n.startswith(EDGE_STORE_CLASS + "$") for n in names), f"unexpected classes: {names}"
        base_javap = javap(BASE_JAR_PATH, names)
        diff = diff_lines(base_javap, javap(classes_dir, names))
        jar = jar_path(variant)
        shutil.copyfile(BASE_JAR_PATH, jar)
        class_files = [p.relative_to(classes_dir).as_posix() for p in classes_dir.rglob("*.class")]
        subprocess.run([str(JDK_BIN_DIR / "jar"), "uf", str(jar)] + sum([["-C", str(classes_dir), f] for f in class_files], []),
                       check=True)
        assert diff_lines(base_javap, javap(jar, names)) == diff, f"{jar.name}: classes in the jar differ from the compiled classes"
        n_diff = sum(line[0] in "+-" for line in diff)
        if variant == "recompiled":
            lines.append(f"(B1) recompiled vs the jar's classes ({len(names)}: {names}), javap -c -p: "
                         f"{'PASS' if not diff else 'FAIL'} ({n_diff} differing lines)")
            is_ok &= not diff
        else:
            masked = diff_lines(pool_masked(base_javap), pool_masked(javap(classes_dir, names)))
            lines.append(f"(B2) {variant} (switch {VARIANT_SWITCH[variant]}) vs the jar's classes, javap -c -p differing "
                         f"lines (constant-pool indices masked; {n_diff} lines unmasked):")
            lines += [f"    {line}" for line in masked]
        serial = serialver(jar)
        lines.append(f"(B3) {variant} EdgeStore serialVersionUID: {'PASS' if serial == base_serial else 'FAIL'} ({serial})")
        is_ok &= serial == base_serial
        lines.append(f"    jar {jar.relative_to(PROJECT_ROOT)}")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_build.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    assert is_ok, "B1 or B3 failed: stop"


# --- route -----------------------------------------------------------------------------------------
def network_paths(release):
    """The pathways v2 network of a release, as transit_q24_combined.network_paths (unique file names)."""
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


def open_network(jar, release):
    """Start the JVM on a jar (guarded), load the release's v2 network; returns ttm(origin, destination, departure,
    is_transit) in seconds and the network."""
    assert jar.exists(), "build first"
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(jar)]   # r5py reads these at import
    import geopandas as gpd
    import jpype
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    for name in GUARD_CLASSES:
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == jar.resolve(), f"{name} loaded from {location}"
    print(f"{', '.join(c.rsplit('.', 1)[1] for c in GUARD_CLASSES)} from {jar.name}", flush=True)
    pbf_path, gtfs = network_paths(release)
    assert pbf_path.exists() and all(p.exists() for p in gtfs), "transit_pathway_network_v2 build / feeds first"
    check_working_copies([pbf_path] + gtfs)
    print(f"reusing {pbf_path.name} and {[p.name for p in gtfs]}", flush=True)
    network = TransportNetwork(pbf_path, gtfs)

    def ttm(origin, destination, departure, is_transit):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([origin[1]], [origin[0]]))
        targets = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326",
                                   geometry=gpd.points_from_xy([destination[1]], [destination[0]]))
        transport_modes = [TransportMode.TRANSIT, TransportMode.WALK] if is_transit else [TransportMode.WALK]
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=targets, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=transport_modes, max_time=datetime.timedelta(minutes=MAX_TIME_MIN), speed_walking=SPEED_KMH))
        return float(matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0])

    return ttm, network


def release_pairs(release):
    pairs_df = pd.read_csv(P1_PAIRS_PATH)
    return pairs_df[pairs_df.release.astype(str) == release]


def route(variant, release):
    assert variant in VARIANTS and release in RELEASES
    ttm, _ = open_network(jar_path(variant), release)
    rows = []
    started = datetime.datetime.now()
    for pair in release_pairs(release).itertuples():
        origin, destination = (pair.origin_lat, pair.origin_lon), (pair.dest_lat, pair.dest_lon)
        departure = (datetime.datetime.combine(datetime.date.fromisoformat(str(pair.own_date)), datetime.time())
                     + datetime.timedelta(minutes=int(pair.dep_min_of_day)))
        rows.append({"draw_no": pair.draw_no, "release": release, "variant": variant,
                     "transit": ttm(origin, destination, departure, True), "walk": ttm(origin, destination, departure, False)})
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_routes_{variant}_{release}.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"done: {len(rows)} pairs in {datetime.datetime.now() - started} -> {out_path.name}", flush=True)


# --- walkcheck -------------------------------------------------------------------------------------
def walk_speeds():
    """R5's speeds: walkSpeed as a Java float (m/s), the destination's integer mm/s, and the exact m/s."""
    exact_m_s = SPEED_KMH * MM_PER_M / SECONDS_PER_HOUR
    float_m_s = np.float32(exact_m_s)
    speed_mm_s = int(float_m_s * np.float32(MM_PER_M))
    return float(float_m_s), speed_mm_s, exact_m_s


def java_round(x):
    """Java's Math.round(double): floor(x + 0.5)."""
    return math.floor(x + 0.5)


def decompose(street_layer, router_class, request, routing_variable, walk_mode, origin, destination):
    """One walk-only search on p4, rebuilt as TTM's (as transit_r5_edge_rounding.decompose, p4's edge step)."""
    float_m_s, speed_mm_s, exact_m_s = walk_speeds()
    router = router_class(street_layer)
    router.profileRequest = request
    router.streetMode = walk_mode
    router.timeLimitSeconds = MAX_TIME_MIN * SECONDS_PER_MIN
    router.quantityToMinimize = routing_variable
    if not router.setOrigin(float(origin[0]), float(origin[1])):
        return None
    router.route()
    origin_split = router.getOriginSplit()
    dest_split = street_layer.findSplit(float(destination[0]), float(destination[1]), float(SPLIT_RADIUS_M), walk_mode)
    if dest_split is None:
        return None
    if int(origin_split.edge) == int(dest_split.edge):
        along_mm = abs(int(origin_split.distance0_mm) - int(dest_split.distance0_mm))
        return {"r5_s": along_mm // speed_mm_s, "n_edges": 0, "path_mm": along_mm, "n_increment_off": 0, "n_forced": 0}
    ends = []
    for vertex, dest_mm in [(dest_split.vertex0, dest_split.distance0_mm), (dest_split.vertex1, dest_split.distance1_mm)]:
        vertex_s = int(router.getTravelTimeToVertex(int(vertex)))
        if vertex_s != np.iinfo(np.int32).max:
            ends.append((vertex_s + int(dest_mm) // speed_mm_s, int(vertex), int(dest_mm)))
    if not ends:
        return None
    r5_s, vertex, dest_mm = min(ends)
    states = []
    state = router.getStateAtVertex(vertex)
    while state is not None:
        states.append(state)
        state = state.backState
    states.reverse()
    edge_cursor = street_layer.edgeStore.getCursor()
    n_edges, n_increment_off, n_forced = 0, 0, 0
    for before, after in zip(states, states[1:]):
        edge_cursor.seek(int(after.backEdge))
        before_mm = int(before.distance)
        step_s = (java_round((before_mm + int(edge_cursor.getLengthMm())) / MM_PER_M / float_m_s)
                  - java_round(before_mm / MM_PER_M / float_m_s))
        n_forced += step_s < MIN_EDGE_INCREMENT_S
        n_increment_off += int(after.getDurationSeconds()) - int(before.getDurationSeconds()) != max(MIN_EDGE_INCREMENT_S, step_s)
        n_edges += 1
    return {"r5_s": r5_s, "n_edges": n_edges, "path_mm": int(states[-1].distance) + dest_mm,
            "n_increment_off": n_increment_off, "n_forced": n_forced}


def walkcheck(release):
    assert release in RELEASES
    _, network = open_network(jar_path("p4"), release)
    import jpype
    from com.conveyal.r5.profile import ProfileRequest, StreetMode
    from com.conveyal.r5.streets import StreetRouter
    routing_variable = jpype.JClass("com.conveyal.r5.streets.StreetRouter$State$RoutingVariable").DURATION_SECONDS
    request = ProfileRequest()
    request.walkSpeed = walk_speeds()[0]
    street_layer = network._transport_network.streetLayer
    rows = []
    for pair in release_pairs(release).itertuples():
        row = decompose(street_layer, StreetRouter, request, routing_variable, StreetMode.WALK,
                        (pair.origin_lat, pair.origin_lon), (pair.dest_lat, pair.dest_lon))
        rows.append({"draw_no": pair.draw_no, "release": release, **(row if row is not None else {"r5_s": np.nan})})
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_walkcheck_{release}.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"done: {len(rows)} pairs -> {out_path.name}", flush=True)


# --- score -----------------------------------------------------------------------------------------
def newest_table(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    assert paths, f"missing {pattern}"
    return pd.read_csv(paths[-1])


def routed(variant):
    if variant == "baseline":
        frames = [pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{P2_NAME}_{P2_ROUTES_DATE}_routes_p2_orig_{r}.csv") for r in RELEASES]
    else:
        frames = [newest_table(f"{NAME}_2*_routes_{variant}_{r}.csv") for r in RELEASES]
    return pd.concat(frames).set_index("draw_no").sort_index()


def equal(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return (a == b) | (np.isnan(a) & np.isnan(b))


def verdict(n_off, n, is_exact_rule=False):
    if n_off == 0:
        return "PASS"
    if is_exact_rule:
        return "FAIL"
    return "MINOR DEVIATION (flagged)" if n_off / n < MINOR_SHARE else "FAIL"


def listed(label, mask, frame, strata):
    return [f"    {label} draw {d} ({strata.loc[d]}): " + ", ".join(f"{c} {frame.loc[d, c]}" for c in frame.columns)
            for d in frame.index[mask]]


def score():
    pairs_df = pd.read_csv(P1_PAIRS_PATH).set_index("draw_no").sort_index()
    strata = pairs_df.stratum
    n = len(pairs_df)
    got = {v: routed(v) for v in ["baseline"] + VARIANTS}
    assert all(list(df.index) == list(pairs_df.index) for df in got.values())
    base = got["baseline"][CALLS]
    lines = [f"{NAME} {run_date()} score: {n} pairs ({strata.value_counts().to_dict()}), speed {SPEED_KMH} km/h, "
             f"v2 network, drawn points"]

    for label, variant in [("T1", "recompiled"), ("T2", "off")]:
        is_eq = equal(got[variant][CALLS], base)
        off = int((~is_eq.all(axis=1)).sum())
        lines.append(f"({label}) {variant} = baseline: {verdict(off, n, True)} ({off} pairs, {int((~is_eq).sum())} of "
                     f"{is_eq.size} values differ)")
        lines += listed(label, ~is_eq.all(axis=1), got[variant][CALLS].join(base, rsuffix="_base"), strata)

    p4 = got["p4"][CALLS]
    is_ok = (p4 <= base) | (p4.isna() & base.isna()) | (base.isna() & p4.notna())
    mask = ~is_ok.all(axis=1)
    off = int(mask.sum())
    lines.append(f"(T3) p4 <= baseline, every value: {verdict(off, n)} ({off} pairs off)")
    lines += listed("T3", mask, p4.join(base, rsuffix="_base"), strata)

    check_df = pd.concat([newest_table(f"{NAME}_2*_walkcheck_{r}.csv") for r in RELEASES]).set_index("draw_no").sort_index()
    is_rebuilt = equal(check_df.r5_s, p4.walk.loc[check_df.index]) | p4.walk.loc[check_df.index].isna()
    n_rebuild_off = int((~is_rebuilt).sum())
    n_increment_off = int(check_df.n_increment_off.fillna(0).sum())
    is_t4 = n_rebuild_off == 0 and n_increment_off == 0
    lines.append(f"(T4) walkcheck rebuilt = p4 walk on every pair ({n_rebuild_off} differ), edge increments = max(1, "
                 f"round step) ({n_increment_off} of {int(check_df.n_edges.sum())} differ): {'PASS' if is_t4 else 'FAIL'}")
    lines += listed("T4", ~is_rebuilt.values, check_df.join(p4.walk.rename("p4_walk")), strata)
    has_walk = p4.walk.loc[check_df.index].notna()
    excess_s = (check_df.r5_s - check_df.path_mm / MM_PER_M / walk_speeds()[2])[has_walk]
    median_s = excess_s.median()
    lines.append(f"(T5) p4 walk excess over path / speed: median {median_s:.2f} s, mean {excess_s.mean():.2f}, min "
                 f"{excess_s.min():.2f}, max {excess_s.max():.2f} (n {len(excess_s)}): "
                 f"{'PASS' if abs(median_s) <= END_TOLERANCE_S else 'FAIL'}; forced 1 s steps "
                 f"{int(check_df.n_forced[has_walk].sum())} over {int(check_df.n_edges[has_walk].sum())} edges "
                 f"({check_df.n_forced[has_walk].mean():.2f} per path)")

    saving = (base - p4).join(strata)
    lines.append("(R) saving, baseline - p4 (s):")
    for call in CALLS:
        table = saving.groupby("stratum")[call].describe(percentiles=[.5])[["count", "mean", "50%", "max"]]
        table.loc["all"] = saving[call].describe(percentiles=[.5])[["count", "mean", "50%", "max"]]
        lines.append(f"  {call}:\n" + table.round(1).to_string())
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_score.txt").write_text(text + "\n", encoding="utf-8", newline="\n")


# --- full training run -----------------------------------------------------------------------------
def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def training_pairs():
    pairs_df = pd.read_csv(newest(RANGE_RESULTS_GLOB))
    return pairs_df[pairs_df.is_scored.astype(bool)]


def route_train(release):
    """Full training routing on P4's jar (docstring); appends a row per pair, resumes from the newest table."""
    assert release in RELEASES
    pairs_df = training_pairs()
    pairs_df = pairs_df[pairs_df.release.astype(str) == release]
    saved = newest(f"{NAME}_2*_trainroutes_{TRAIN_VARIANT}_{release}.csv")
    table_path = saved if saved is not None else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_trainroutes_{TRAIN_VARIANT}_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"{TRAIN_VARIANT} {release}: {len(pairs_df)} pairs, {len(done)} done, {len(todo_df)} to route -> {table_path.name}",
          flush=True)
    ttm, _ = open_network(jar_path("p4"), release)
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        origin, destination = (pair.origin_lat, pair.origin_lon), (pair.dest_lat, pair.dest_lon)
        departure = (datetime.datetime.combine(datetime.date.fromisoformat(str(pair.own_date)), datetime.time())
                     + datetime.timedelta(minutes=int(pair.dep_min_of_day)))
        row = {"draw_no": pair.draw_no, "release": release, "transit": ttm(origin, destination, departure, True),
               "walk": ttm(origin, destination, departure, False)}
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % PROGRESS_EVERY == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


def wilson(successes, n):
    if n == 0:
        return np.nan, np.nan
    share = successes / n
    centre = (share + WILSON_Z ** 2 / (2 * n)) / (1 + WILSON_Z ** 2 / n)
    half_width = WILSON_Z * np.sqrt(share * (1 - share) / n + WILSON_Z ** 2 / (4 * n ** 2)) / (1 + WILSON_Z ** 2 / n)
    return centre - half_width, centre + half_width


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


def rounded_min(seconds):
    """Seconds to the nearest whole minute, half up (patch 1's T3; SCR-10); NaN (over max_time) -> inf."""
    return np.floor(np.nan_to_num(np.asarray(seconds, dtype=float), nan=np.inf, posinf=np.inf) / SECONDS_PER_MIN + 0.5)


def model_lines(label, minutes, seconds, df, google_s, is_random, base_hard=None):
    """Run 3's measures for one model, with medians beside means; returns (lines, hard counts, total, largest gain)."""
    low, high, google = df.low_2.to_numpy(), df.default_min.to_numpy(), df.google_min.to_numpy()
    finite = np.isfinite(minutes)
    distance = distance_to_range(minutes, low, high)[finite]
    labels = pd.Series(label_of(minutes, low, high)).value_counts().reindex(LABELS, fill_value=0).to_dict()
    hard = hard_counts(minutes[is_random], low[is_random], high[is_random])
    total = sum(k for k, _, _ in hard.values())
    gain = 0 if base_hard is None else max(hard[test][0] - base_hard[test][0] for test in hard)
    away = finite & np.logical_or.reduce([(google >= a) & (google <= b) for a, b in AWAY_RANGES_MIN])
    errors = (minutes - google)[away]
    is_walk_default = df.default_walk_only.astype(bool).to_numpy()
    walk_error = (minutes - high)[is_walk_default & finite]
    ratios = [((minutes[is_random] <= cut).sum() / (google[is_random] <= cut).sum()) for cut in CUTS_MIN.values()]
    zone_text, zone_failures = zone_lines(google, minutes, errors - np.median(errors), np.random.default_rng(SIMULATION_SEED))
    lines = ["", f"{label}:",
             f"  labels {labels}; error to range median {np.median(distance):+.1f}, mean {distance.mean():+.2f}",
             "  hard: " + "; ".join(f"{test} {k}/{n} (upper {upper:.3f}{' FAIL' if upper > HARD_MISS_MAX else ''})"
                                    for test, (k, n, upper) in hard.items()) + f"; total {total} (largest gain {gain:+d})",
             f"  off-cut error vs Google rounded (n {len(errors)}): median {np.median(errors):+.1f}, mean {errors.mean():+.2f}; "
             f"count ratio <= 10 {ratios[0]:.3f}, <= 20 {ratios[1]:.3f}"
             + "".join(" FAIL" if not COUNT_RATIO_RANGE[0] <= ratio <= COUNT_RATIO_RANGE[1] else "" for ratio in ratios),
             f"  walk-only defaults (n {len(walk_error)}): error median {np.median(walk_error):+.0f}, mean {walk_error.mean():+.2f}, "
             f"exact {np.mean(walk_error == 0):.3f}"]
    lines += zone_text
    lines.append(f"  zone failures: {', '.join(zone_failures) if zone_failures else 'none'}")
    sec_err = pd.DataFrame({"err_s": np.where(np.isfinite(seconds), seconds, np.nan) - google_s,
                            "group": df.boardings.to_numpy()}).dropna()
    g = sec_err.groupby("group").err_s
    sec_table = pd.DataFrame({"n": g.size(), "median_s": g.median(), "mean_s": g.mean(),
                              "median_abs_s": g.apply(lambda x: x.abs().median()),
                              "mean_abs_s": g.apply(lambda x: x.abs().mean())})
    sec_table.loc["all"] = [len(sec_err), sec_err.err_s.median(), sec_err.err_s.mean(), sec_err.err_s.abs().median(),
                            sec_err.err_s.abs().mean()]
    lines.append(f"  seconds error vs Google {GOOGLE_COL} by Google default's boardings:\n" + sec_table.round(1).to_string())
    return lines, hard, total, gain


def score_train():
    pairs_df = training_pairs().set_index("draw_no").sort_index()
    routes = {}
    for train_variant, prefix in [(BASELINE_TRAIN, f"{P2_NAME}_{P2_ROUTES_DATE}"), (TRAIN_VARIANT, f"{NAME}_2*")]:
        paths = [newest(f"{prefix}_trainroutes_{train_variant}_{release}.csv") for release in RELEASES]
        assert all(paths), f"{train_variant} training routes on both releases first"
        routes[train_variant] = pd.concat([pd.read_csv(p) for p in paths]).set_index("draw_no").sort_index()
        assert list(routes[train_variant].index) == list(pairs_df.index), f"{train_variant}: routed pairs != training pairs"
    n = len(pairs_df)
    lines = [f"{NAME} {run_date()} score_train: {n} training pairs ({pairs_df.set_name.value_counts().to_dict()}), "
             f"speed {SPEED_KMH} km/h, v2 network, drawn points"]

    saved = routed("p4")[CALLS]
    off_f1 = int((~equal(routes[TRAIN_VARIANT].loc[saved.index, CALLS], saved)).sum())
    lines.append(f"(F1) the 100 pairs routed by `route p4` reproduce exactly: {'PASS' if off_f1 == 0 else 'FAIL'} "
                 f"({off_f1} values off)")
    if off_f1:
        print("\n".join(lines))
        raise SystemExit("F1 failed: stop")

    google_df = pd.concat([pd.read_csv(path).assign(set_name=name) for name, path in GOOGLE_ROUTES_PATHS.items()])
    google_df = google_df[google_df.is_default.astype(bool)].set_index(["set_name", "draw_no"])
    keys = list(zip(pairs_df.set_name, pairs_df.index))
    google_s = google_df[GOOGLE_COL].reindex(keys).to_numpy(dtype=float)
    steps = google_df.n_transit_steps.reindex(keys).to_numpy(dtype=float)
    df = pairs_df.reset_index().assign(boardings=[BOARDING_GROUPS[min(int(s), 2)] if np.isfinite(s) else np.nan for s in steps])
    lines.append(f"Google defaults found: {int(np.isfinite(google_s).sum())} of {n}")
    is_random = (df.set_name != TOPUP_SET).to_numpy()

    model_s = {v: np.fmin(r.transit.fillna(np.inf).to_numpy(), r.walk.fillna(np.inf).to_numpy()) for v, r in routes.items()}
    labels = {BASELINE_TRAIN: "p2orig (P2 jar, drawn points, v2; model of record)", TRAIN_VARIANT: "p4orig (P4 jar, drawn points, v2)"}
    minutes = {v: rounded_min(s) for v, s in model_s.items()}
    readings = {}
    base_hard = None
    for v in [BASELINE_TRAIN, TRAIN_VARIANT]:
        text, hard, total, gain = model_lines(labels[v], minutes[v], model_s[v], df, google_s, is_random, base_hard)
        lines += text
        readings[v] = (total, gain)
        if base_hard is None:
            base_hard = hard

    p2_s, p4_s = model_s[BASELINE_TRAIN], model_s[TRAIN_VARIANT]
    p2_min, p4_min = minutes[BASELINE_TRAIN], minutes[TRAIN_VARIANT]
    both_finite = np.isfinite(p2_s) & np.isfinite(p4_s)
    gap_s = np.abs(p4_s - p2_s)[both_finite]
    signed = (p4_s - p2_s)[both_finite]
    is_transit = {v: r.transit.fillna(np.inf).to_numpy() < r.walk.fillna(np.inf).to_numpy() for v, r in routes.items()}
    lines += ["", "p4orig vs p2orig (reported):",
              f"  seconds differ on {int((gap_s > 0).sum())} of {int(both_finite.sum())} pairs ("
              + ", ".join(f"{lo}-{hi} s: {int(((gap_s >= lo) & (gap_s <= hi)).sum())}" for lo, hi in DIFF_BINS_S)
              + f"); finite in one only: {int((np.isfinite(p2_s) != np.isfinite(p4_s)).sum())}",
              f"  p4 - p2 (s) where they differ: median {np.median(signed[signed != 0]) if (signed != 0).any() else 0:+.0f}, "
              f"earlier {int((signed < 0).sum())}, later {int((signed > 0).sum())}",
              f"  minutes changed on {int((p4_min != p2_min).sum())} pairs; change (min) "
              + str(pd.Series(p4_min - p2_min)[np.isfinite(p4_min - p2_min)].value_counts().sort_index().to_dict()),
              f"  band calls changed {int((band_of(p4_min) != band_of(p2_min)).sum())}",
              f"  winner flips: transit -> walk {int((is_transit[BASELINE_TRAIN] & ~is_transit[TRAIN_VARIANT]).sum())}, "
              f"walk -> transit {int((~is_transit[BASELINE_TRAIN] & is_transit[TRAIN_VARIANT]).sum())}"]
    base_total = readings[BASELINE_TRAIN][0]
    total, gain = readings[TRAIN_VARIANT]
    reading = ("IMPROVES" if total < base_total and gain <= SNAP_TOLERANCE_MISSES
               else "WORSENS" if total > base_total else "MIXED")
    lines += ["", f"READING (run 3's rule): p4orig hard misses {total} vs p2orig {base_total}, largest gain in one test "
              f"{gain:+d} -> {reading}"]
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_train_score.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    pd.DataFrame({"draw_no": pairs_df.index, "set_name": df.set_name, "release": df.release, "boardings": df.boardings,
                  "google_s": google_s, "google_min": df.google_min, "p2orig_s": p2_s, "p4orig_s": p4_s,
                  "p2orig_min": p2_min, "p4orig_min": p4_min}).to_csv(
        DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_train_scored.csv", index=False)


if __name__ == "__main__":
    {"build": build, "route": route, "walkcheck": walkcheck, "score": score, "route_train": route_train,
     "score_train": score_train}[sys.argv[1]](*sys.argv[2:])
