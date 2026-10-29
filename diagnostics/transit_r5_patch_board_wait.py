"""R5 patch 3 (TRN-16 register): board wait by RAPTOR round, 0 s at the first boarding and 200 s at transfers.

Claim under test (concepts/transit.md TRN-16; DESIGN.md Q24): R5's one board wait, `FastRaptorWorker.MINIMUM_BOARD_WAIT_SEC
= 60`, applied at every boarding (`earliestBoardTime = inputState.bestTimes[stop] + MINIMUM_BOARD_WAIT_SEC`, scheduled
and frequency searches), can be split by round with a patch that moves nothing else: round 1 (the first boarding; its
input state is round 0, the access search, whose `previous` is null) waits FIRST_BOARD_WAIT_S, later rounds (transfers)
TRANSFER_BOARD_WAIT_S. The values are Google's conventions (diagnostics/transit_google_transfer_buffer.py: no
first-boarding wait; about 200 s on top of the listed walk at every transfer), read off Google's output, not fitted to
its times. The other 60 s constants (PathWithTimes, McRaptorSuboptimalPathProfileRouter, StatsCalculator) shape
displayed paths only (TransportNetworkConfig's comment; not on TTM's path). Where the pipeline would rely on it: transit
bands 1-2 through the model of record, replacing its 1-min departure shift (no-wait: shifted - 1 min if transit wins)
and R5's 60 s at transfers.

Patch 3 sits on patch 1 (seconds out): every jar here is patch 1's patched jar with FastRaptorWorker replaced, so values
are seconds. Variants (FIRST_BOARD_WAIT_S / TRANSFER_BOARD_WAIT_S):
  recompiled  FastRaptorWorker compiled from the unchanged source.
  off         the patched code at 60 / 60 (the new code path, stock values).
  first0      0 / 60 (first boarding only).
  p3          0 / TRANSFER_BUFFER_S = 200.

Steps (modes; one JVM per process, jar chosen at JVM start through r5py's `--r5-classpath`):
  build  FastRaptorWorker.java from `inputs/r5py/r5-7.5.1` (never edited), per variant, javac 21 against patch 1's jar;
      each variant's classes into its own copy of that jar in outputs/r5_patches/. (B1) recompiled vs the jar's
      classes (FastRaptorWorker and its inner classes), javap -c -p identical, else stop. (B2) each patched variant vs
      the jar: the differing javap lines, printed (expected: the two earliestBoardTime lines call boardWaitSec, the
      new method, constants only differ between off / first0 / p3).
  route <variant> <release>  The seeded 100-pair set of transit_r5_patch_seconds.py (reused, never redrawn), same
      network (run 3's stub extract per release), origin split and snapped destination (stub base) at 4.143 km/h; two
      TTM calls: transit at t (max_time MAX_TIME_MIN) and walk-only. Guard: the loaded FastRaptorWorker and
      TravelTimeReducer both come from the variant's jar.
  score  Baseline = patch 1's saved seconds (transit_r5_patch_seconds_20261021_routes_patched_<release>.csv: stock_snap
      = transit at t with 60 / 60, shifted_snap = from t - 60 s with max_time + 1 min, walk_snap). Rules (Claude's;
      TRN-16 register (user, 2026-10-21); written before any result):
      (T1) recompiled = baseline, transit and walk, every value (NaN = NaN). Any difference fails.
      (T2) off = baseline, every value. Any difference fails (the new code path at stock values is stock).
      (T3) walk calls of first0 and p3 = baseline walk: should not differ (no RAPTOR on a walk-only search). < MINOR_SHARE
           of pairs = flagged minor deviation (listed), >= MINOR_SHARE fails.
      (T4) first0 vs the 1-min shift, on pairs where the shift's transit wins (shifted < walk): first0 transit =
           shifted - 60 s exactly. Elsewhere first0 transit lies in [min(walk, shifted) - 60, walk] or is NaN where
           shifted is NaN. Same minor / fail line. Departing at t - 60 with 60 s slack reaches the same first vehicle
           as departing at t with 0 s, and the rides after it see the same arrival times.
      (T5) p3 transit >= first0 transit on every value (a longer transfer wait can never arrive earlier; NaN only where
           over max_time). Same minor / fail line. Reported: p3 - first0 by stratum (0 on one-boarding pairs unless R5's
           best path transfers; up to 140 s per transfer, more where a connection is missed).
      (R, reported, no verdict) seconds error vs Google's default route, arrival - requested time (training;
           `arrival_from_request_s`, the scorers' quantity, transit_fetch.py) by stratum, for the model of record (no-wait on patch 1: shifted - 60 if shifted < walk, else walk)
           and for p3 (min(p3 transit, walk)): n, mean, median, mean absolute. In-sample, 100 pairs; the verdict is a
           full training run (TRN-16).

Predictions (Claude's, before any result): B1 passes; B2 shows the two call sites and the new method only. T1, T2, T3
exact. T4 exact where transit wins. T5 holds on all; p3 - first0 = 0 on most one-boarding pairs; transfers pairs
+60 to +200 s typically, a few larger. R: p3 moves the transfers stratum's mean error later by about a minute or two.

Revision after the first score (Claude's, 2026-10-21): (R) first compared with Google's `duration_s`, which leaves
out the wait before the first boarding while R5 counts from the requested time; corrected to `arrival_from_request_s`.
The T rules are unchanged.

Conclusion (run 2026-10-21; T rules above written before any result):
  B1 PASS (0 differing javap lines, FastRaptorWorker and FastRaptorWorker$FrequencyBoardingMode). B2 as predicted, for
  off / first0 / p3: the two constants, boardWaitSec (constants 60/60, 0/60, 0/200), and at each of the two sites
  `bipush 60` replaced by `aload; invokestatic boardWaitSec`; nothing else once pool indices and offsets are masked.
  T1 PASS (0 of 200 values). T2 PASS (0 of 200). T3 PASS (first0 and p3 walk = baseline on all pairs). T4 PASS: the
  shift's transit wins on 81 pairs and first0 = shifted - 60 s on all 81; the other 19 within the stated range.
  T5 PASS (p3 >= first0 on all). p3 - first0: 0 on 81 pairs; 19 pairs move +19 to +765 s (transfers 30 pairs: mean
  +98 s; one_boarding 40: +34 s, where R5 transfers although Google's default has one ride; walk_only 0).
  (R, in-sample, 99 pairs with Google): error R5 - Google (s), model of record -> p3:
      all        mean -258.8 -> -210.3, median -31.0 -> -8.0, mean abs 333.3 -> 289.9
      transfers  mean -153.6 -> -55.5,  median -49.0 -> -1.0, mean abs 242.9 -> 148.2
      one_board  mean -193.7 -> -159.3, median -51.5 -> -12.5, mean abs 261.6 -> 242.0
      walk_only  unchanged (mean -625 from the long tail, median -15)
  p3 changes the model's value on 21 of 100 pairs.
  Reading (Claude's): the patch does only what it claims (T1-T5 exact), and first0 reproduces the model of record's
  1-min shift exactly where transit wins, so the shift can be retired in favour of the patch. The 200 s buffer moves R5
  from early toward Google, most on transfers (median error -49 -> -1 s). 100 pairs, in-sample: the verdict is a full
  training run (TRN-16).

Full training run (TRN-16 verdict; rule OK'd by the user 2026-10-21 before the run). Pairs: every scored training pair
(v2's range results: train half, second batch, top-up; test half closed), on the same network, origin split, stub-base
destination and speed as `route`. Steps: `route_train <jar> <release>`, jar p1 (patch 1: shifted from t - 60 s with
max_time + 1 min, and walk-only) or p3 (transit at t); rows appended per pair, a rerun resumes. `score_train`:
  Models, seconds then rounded to the nearest minute (half up, as patch 1's T3; SCR-10):
    model of record = shifted - 60 if shifted < walk, else walk (no-wait on patch 1);
    p3 = min(p3 transit, walk).
  Checks first, else stop: (F1) the 100 pairs routed before reproduce exactly (p1 shifted / walk = patch 1's saved
  snapped values; p3 transit = this file's saved p3). (F2) where shifted < walk, p3 transit >= shifted - 60 (T4 + T5;
  NaN allowed when shifted - 60 is within the transfer buffer of the cap); < MINOR_SHARE flagged, >= fails.
  Reported per model, as run 3 (transit_q24_combined.py): labels to Google's k = 2 range, error to the range (median,
  mean), the four hard-miss tests (random samples only), TRN-13 zones, count ratios, walk-only defaults; band calls
  changed; medians beside means; seconds error to Google's arrival_from_request_s by the boardings of Google's default
  (0 / 1 / 2+); transit-or-walk winner flips. Context, no verdict: run 3's stub combined model (a)+(b)+(c) median.
  Reading (run 3's rule): IMPROVES if p3's hard-miss total falls below the model of record's and no test gains more than
  SNAP_TOLERANCE_MISSES; WORSENS if it rises; else MIXED.
  Predictions (Claude's, before any result): transfer pairs later by 1-2 min; false reach falls, lost reach rises a
  little; total about 22-27, MIXED most likely; median error to the range near 0.
  Conclusion (run 2026-10-21, 3,448 pairs; rule above written and OK'd before the run): F1 PASS (100 pairs exact on all
  three calls), F2 PASS (0 of 3,089). Hard misses, model of record -> p3: lost 10 0/50 -> 0/50, false 10 2/294 -> 2/294,
  lost 20 7/248 -> 7/248, false 20 16/503 -> 14/503 (upper 0.051 -> 0.046, now under 0.05); total 25 -> 23, largest
  gain 0: IMPROVES. Labels late / agree / early 674 / 1,327 / 1,447 -> 793 / 1,490 / 1,165; error to the range median
  0 both, mean -2.53 -> -1.66 min; off-cut error mean -0.16 -> +0.07 (median 0); count ratios 0.971 / 1.046 -> 0.981 /
  1.040; zones: every check passes for both (zone 1 recall 0.805 both, precision 0.843 -> 0.833). Seconds error vs
  Google (median / mean): 2+ boardings -113 / -330 -> -20 / -207 s; 1 boarding -12 / -124 -> -7 / -101 s; walk-only
  unchanged (+16 to +18 / +15 s); all -21 / -180 -> -9 / -128 s. p3 changes 629 pairs' minutes (22 by -1 min: walk ->
  transit flips; 90% of the rest +1 to +10 min, one +38), but only 4 band calls; winner flips 44 walk -> transit, 1
  transit -> walk. Model of record on patch 1 vs run 3's stubs: 34 pairs' minutes differ, hard misses equal (25), zone 1
  noise bar passes on patch 1 and fails on stubs.
  Prediction check: total in range, but IMPROVES rather than MIXED; lost reach did not rise (wrong).
  Reading (Claude's): p3 is a better match to Google than the 1-min shift on every reported measure. The model's mean
  still leans early (long-tail pairs, -1.66 min), so the remaining error is not board waiting. In-sample: training
  pairs, read many times; the holdout would confirm it. First run of score_train fixed after the first output, before
  any reading: np.nan_to_num turned inf into the largest float (garbage mean error to the range, 58 instead of 34 in
  the stubs count); every other number was unchanged.

Inputs (read only): patch 1's jar and saved routes and pair set, run 3's stub extracts, stub tables and origin splits
(diagnostics/diagnostic_data/), `inputs/r5py/` source, Google route tables in outputs/transit_validation/. Writes jars
to outputs/r5_patches/ and tables to diagnostics/diagnostic_data/. Self-contained (CLAUDE.md D1). No paid API calls.
B2 masks constant-pool indices, code offsets and branch targets (adding a method renumbers them). Usage: `python transit_r5_patch_board_wait.py build`, `... route <variant> <release>`, `... score`, `... route_train <p1|p3> <release>`,
`... score_train`.
"""
import datetime
import difflib
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
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
GOOGLE_ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                       "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                       "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
R5_SOURCE_DIR = PROJECT_ROOT / "inputs" / "r5py" / "r5-7.5.1" / "src" / "main" / "java"
PATCH_DIR = PROJECT_ROOT / "outputs" / "r5_patches"
JDK_BIN_DIR = Path(r"C:\Program Files\Java\jdk-21.0.12\bin")
P1_NAME = "transit_r5_patch_seconds"
BASE_JAR_PATH = PATCH_DIR / f"r5-v7.5.1-r5py-all_{P1_NAME}_patched.jar"
P1_PAIRS_PATH = DIAGNOSTIC_DATA_DIR / f"{P1_NAME}_20261021_pairs.csv"
P1_ROUTES_DATE = "20261021"
CLASS_NAME = "com.conveyal.r5.profile.FastRaptorWorker"
CLASS_FILE = CLASS_NAME.replace(".", "/")
REDUCER_CLASS_NAME = "com.conveyal.r5.analyst.TravelTimeReducer"
Q24_NAME = "transit_q24_combined_20261021"
STUB_BUILDS = {"20261009": "4135_4143_4160_b4", "20261016": "4135_4143_4160_b5"}   # run 3's final builds
V2_NAME = "transit_pathway_network_v2"
NAME = "transit_r5_patch_board_wait"

# --- the patch -------------------------------------------------------------------------------------
TRANSFER_BUFFER_S = 200                        # evidence: diagnostics/transit_google_transfer_buffer.py
STOCK_BOARD_WAIT_S = 60
VARIANT_WAITS_S = {"off": (STOCK_BOARD_WAIT_S, STOCK_BOARD_WAIT_S), "first0": (0, STOCK_BOARD_WAIT_S),
                   "p3": (0, TRANSFER_BUFFER_S)}
VARIANTS = ["recompiled"] + list(VARIANT_WAITS_S)
CONST_ANCHOR = "    private static final int MINIMUM_BOARD_WAIT_SEC = 60;\n"
CALL_OLD = "int earliestBoardTime = inputState.bestTimes[stop] + MINIMUM_BOARD_WAIT_SEC;"
CALL_NEW = ("int earliestBoardTime = inputState.bestTimes[stop] + boardWaitSec(inputState); "
            "// PLATICA TRN-16 P3 (was + MINIMUM_BOARD_WAIT_SEC)")
N_CALL_SITES = 2
CONST_POOL_REF = re.compile(r"#\d+(:#\d+)?")
CODE_OFFSET = re.compile(r"^\s*\d+: ")
BRANCH_TARGET = re.compile(r"\b(goto|goto_w|if\w*|jsr)\s+\d+")
SWITCH_TARGET = re.compile(r"^\s*(-?\d+|default): \d+$")
METHOD_TEMPLATE = """
    // PLATICA TRN-16 P3: board wait by round. Round 1 (first boarding) reads round 0, the access search, whose
    // previous state is null; later rounds are transfers.
    private static final int FIRST_BOARD_WAIT_SEC = {first};
    private static final int TRANSFER_BOARD_WAIT_SEC = {transfer};

    private static int boardWaitSec (RaptorState inputState) {{
        return inputState.previous == null ? FIRST_BOARD_WAIT_SEC : TRANSFER_BOARD_WAIT_SEC;
    }}
"""

# --- values copied from transit_r5_patch_seconds.py -------------------------------------------------
R5_MAX_MEMORY = "7G"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
SPEED_TAG = "median"
SPEED_KMH = 4.143                              # Q24 (2) median; user 2026-10-21
MAX_TIME_MIN = 90
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
SECONDS_PER_MIN = 60
SHIFT_S = 60                                   # the model of record's 1-min departure shift
CALLS = ["transit", "walk"]
MINOR_SHARE = 0.01
GOOGLE_COL = "arrival_from_request_s"          # the scorers' Google quantity (transit_fetch.py google_min)

# --- full training run (values copied from transit_q24_combined.py) ---------------------------------
RANGE_RESULTS_GLOB = f"{V2_NAME}_2*_range_owndate_results.csv"
Q24_PAIRS_PATH = DIAGNOSTIC_DATA_DIR / f"{Q24_NAME}_pairs.csv"   # run 3's scored minutes per variant
Q24_COMBINED_PREFIX = "(a)+(b)+(c) median"
TRAIN_JARS = {"p1": BASE_JAR_PATH, "p3": PATCH_DIR / f"r5-v7.5.1-r5py-all_{NAME}_p3.jar"}
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
PROGRESS_EVERY = 200


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def jar_path(variant):
    return PATCH_DIR / f"r5-v7.5.1-r5py-all_{NAME}_{variant}.jar"


def class_names(classes_dir):
    return sorted(p.relative_to(classes_dir).with_suffix("").as_posix().replace("/", ".")
                  for p in classes_dir.rglob("*.class"))


def javap(classpath, names):
    out = subprocess.run([str(JDK_BIN_DIR / "javap"), "-c", "-p", "-cp", str(classpath)] + names,
                         capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def pool_masked(lines):
    """javap lines with constant-pool indices, code offsets and branch / switch targets masked and whitespace collapsed,
    so B2 shows code changes, not the renumbering that adding a method and two calls causes."""
    masked = []
    for line in lines:
        line = BRANCH_TARGET.sub(r"\1 L", CODE_OFFSET.sub("", CONST_POOL_REF.sub("#", line)))
        line = SWITCH_TARGET.sub(r"\1: L", line)
        masked.append(" ".join(line.split()))
    return masked


def patched_source(source, first_s, transfer_s):
    assert source.count(CONST_ANCHOR) == 1, "constant anchor not found exactly once"
    assert source.count(CALL_OLD) == N_CALL_SITES, f"expected {N_CALL_SITES} board-wait call sites"
    text = source.replace(CONST_ANCHOR, CONST_ANCHOR + METHOD_TEMPLATE.format(first=first_s, transfer=transfer_s))
    return text.replace(CALL_OLD, CALL_NEW)


# --- build -----------------------------------------------------------------------------------------
def build():
    assert BASE_JAR_PATH.exists(), "patch 1's jar missing: run transit_r5_patch_seconds.py build"
    source = (R5_SOURCE_DIR / f"{CLASS_FILE}.java").read_text(encoding="utf-8")
    lines = [f"{NAME} {run_date()} build (base: {BASE_JAR_PATH.name})"]
    texts = {"recompiled": source}
    texts.update({v: patched_source(source, *waits) for v, waits in VARIANT_WAITS_S.items()})
    for variant, text in texts.items():
        variant_dir = PATCH_DIR / f"{NAME}_{variant}"
        src_path = variant_dir / "src" / f"{CLASS_FILE}.java"
        classes_dir = variant_dir / "classes"
        src_path.parent.mkdir(parents=True, exist_ok=True)
        classes_dir.mkdir(parents=True, exist_ok=True)
        src_path.write_text(text, encoding="utf-8", newline="\n")
        subprocess.run([str(JDK_BIN_DIR / "javac"), "--release", "21", "-proc:none", "-nowarn", "-cp", str(BASE_JAR_PATH),
                        "-d", str(classes_dir), str(src_path)], check=True)
        names = class_names(classes_dir)
        assert all(n == CLASS_NAME or n.startswith(CLASS_NAME + "$") for n in names), f"unexpected classes: {names}"
        base_javap = javap(BASE_JAR_PATH, names)
        diff = [line for line in difflib.unified_diff(base_javap, javap(classes_dir, names), "jar", variant, n=0,
                                                      lineterm="") if not line.startswith(("---", "+++"))]
        jar = jar_path(variant)
        shutil.copyfile(BASE_JAR_PATH, jar)
        class_files = [p.relative_to(classes_dir).as_posix() for p in classes_dir.rglob("*.class")]
        subprocess.run([str(JDK_BIN_DIR / "jar"), "uf", str(jar)] + sum([["-C", str(classes_dir), f] for f in class_files], []),
                       check=True)
        jar_diff = [line for line in difflib.unified_diff(base_javap, javap(jar, names), n=0, lineterm="")
                    if not line.startswith(("---", "+++"))]
        assert jar_diff == diff, f"{jar.name}: classes in the jar differ from the compiled classes"
        if variant == "recompiled":
            lines.append(f"(B1) recompiled vs the jar's classes {names}, javap -c -p: {'PASS' if not diff else 'FAIL'} "
                         f"({sum(line[0] in '+-' for line in diff)} differing lines)")
        else:
            masked = [line for line in difflib.unified_diff(pool_masked(base_javap), pool_masked(javap(classes_dir, names)),
                                                            n=0, lineterm="") if not line.startswith(("---", "+++"))]
            lines.append(f"(B2) {variant} {VARIANT_WAITS_S[variant]} vs the jar's classes, javap -c -p differing lines "
                         f"(constant-pool indices masked; {sum(line[0] in '+-' for line in diff)} lines unmasked):")
            lines += [f"    {line}" for line in masked]
        lines.append(f"    jar {jar.relative_to(PROJECT_ROOT)}")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_build.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    assert "PASS (0 differing lines)" in lines[1], "B1 failed: stop"


# --- route -----------------------------------------------------------------------------------------
def network_paths(release):
    """The run-3 stub extract of a release and v2's uniquely named feeds (as transit_r5_patch_seconds.py)."""
    feed_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{release}"
    pbf_path = DIAGNOSTIC_DATA_DIR / f"{Q24_NAME}_osm_{release}_{STUB_BUILDS[release]}.osm.pbf"
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
    """Start the JVM on a jar (guarded), load the release's network; returns ttm(origin, destination, departure,
    is_transit, max_time_min) in seconds, plus the stub and origin lookups."""
    assert jar.exists(), "build first"
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(jar)]   # r5py reads these at import
    import geopandas as gpd
    import jpype
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    for name in (CLASS_NAME, REDUCER_CLASS_NAME):
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == jar.resolve(), f"{name} loaded from {location}"
    print(f"{CLASS_NAME}, {REDUCER_CLASS_NAME} from {jar.name}", flush=True)

    stubs_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{Q24_NAME}_stubs_{release}_{STUB_BUILDS[release]}.csv")
    stubs_df = stubs_df[(stubs_df.status == "ok") & (stubs_df.speed_tag == SPEED_TAG)]
    stub_of = {(s.dest_lat, s.dest_lon): s for s in stubs_df.itertuples()}
    origins_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{Q24_NAME}_originsplits_{release}.csv")
    origin_of = {(o.origin_lat, o.origin_lon): (o.split_lat, o.split_lon) for o in origins_df.itertuples()}
    pbf_path, gtfs = network_paths(release)
    check_working_copies([pbf_path] + gtfs)
    print(f"reusing {pbf_path.name} and {[p.name for p in gtfs]}", flush=True)
    network = TransportNetwork(pbf_path, gtfs)

    def ttm(origin, destination, departure, is_transit, max_time_min=MAX_TIME_MIN):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([origin[1]], [origin[0]]))
        targets = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326",
                                   geometry=gpd.points_from_xy([destination[1]], [destination[0]]))
        transport_modes = [TransportMode.TRANSIT, TransportMode.WALK] if is_transit else [TransportMode.WALK]
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=targets, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=transport_modes, max_time=datetime.timedelta(minutes=max_time_min), speed_walking=SPEED_KMH))
        return float(matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0])

    return ttm, stub_of, origin_of


def pair_points(pair, stub_of, origin_of):
    """Origin split, stub-base destination and requested departure of a pair."""
    stub = stub_of[(pair.dest_lat, pair.dest_lon)]
    departure = (datetime.datetime.combine(datetime.date.fromisoformat(str(pair.own_date)), datetime.time())
                 + datetime.timedelta(minutes=int(pair.dep_min_of_day)))
    return origin_of[(pair.origin_lat, pair.origin_lon)], (stub.base_lat, stub.base_lon), departure


def route(variant, release):
    assert variant in VARIANTS and release in STUB_BUILDS
    ttm, stub_of, origin_of = open_network(jar_path(variant), release)
    pairs_df = pd.read_csv(P1_PAIRS_PATH)
    pairs_df = pairs_df[pairs_df.release.astype(str) == release]
    rows = []
    started = datetime.datetime.now()
    for pair in pairs_df.itertuples():
        origin, destination, departure = pair_points(pair, stub_of, origin_of)
        rows.append({"draw_no": pair.draw_no, "release": release, "variant": variant,
                     "transit": ttm(origin, destination, departure, True),
                     "walk": ttm(origin, destination, departure, False)})
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_routes_{variant}_{release}.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"done: {len(rows)} pairs in {datetime.datetime.now() - started} -> {out_path.name}", flush=True)


# --- score -----------------------------------------------------------------------------------------
def routed(variant):
    frames = []
    for release in STUB_BUILDS:
        paths = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_routes_{variant}_{release}.csv"))
        assert paths, f"route {variant} {release} first"
        frames.append(pd.read_csv(paths[-1]))
    return pd.concat(frames).set_index("draw_no").sort_index()[CALLS]


def baseline():
    frames = [pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{P1_NAME}_{P1_ROUTES_DATE}_routes_patched_{release}.csv")
              for release in STUB_BUILDS]
    df = pd.concat(frames).set_index("draw_no").sort_index()
    return pd.DataFrame({"transit": df.stock_snap, "shifted": df.shifted_snap, "walk": df.walk_snap})


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


def error_table(model_s, google_s, strata):
    err = pd.DataFrame({"err_s": model_s - google_s, "stratum": strata}).dropna()
    g = err.groupby("stratum").err_s
    table = pd.DataFrame({"n": g.size(), "mean_s": g.mean(), "median_s": g.median(), "mean_abs_s": g.apply(lambda x: x.abs().mean())})
    table.loc["all"] = [len(err), err.err_s.mean(), err.err_s.median(), err.err_s.abs().mean()]
    return table.round(1)


def score():
    pairs_df = pd.read_csv(P1_PAIRS_PATH).set_index("draw_no").sort_index()
    strata = pairs_df.stratum
    n = len(pairs_df)
    base_df = baseline()
    got = {v: routed(v) for v in VARIANTS}
    assert all(list(df.index) == list(pairs_df.index) for df in [base_df] + list(got.values()))
    lines = [f"{NAME} {run_date()} score: {n} pairs ({strata.value_counts().to_dict()}), speed {SPEED_KMH} km/h, "
             f"transfer buffer {TRANSFER_BUFFER_S} s"]

    for label, variant in [("T1", "recompiled"), ("T2", "off")]:
        is_eq = equal(got[variant][CALLS], base_df[CALLS])
        off = int((~is_eq.all(axis=1)).sum())
        lines.append(f"({label}) {variant} = patch-1 baseline, transit and walk: {verdict(off, n, True)} "
                     f"({off} pairs, {int((~is_eq).sum())} of {is_eq.size} values differ)")
        lines += listed(label, ~is_eq.all(axis=1), got[variant].join(base_df, rsuffix="_base"), strata)

    for variant in ["first0", "p3"]:
        is_eq = equal(got[variant].walk, base_df.walk)
        off = int((~is_eq).sum())
        lines.append(f"(T3) {variant} walk = baseline walk: {verdict(off, n)} ({off} pairs differ)")
        lines += listed("T3", ~is_eq, got[variant][["walk"]].join(base_df[["walk"]], rsuffix="_base"), strata)

    first0, shifted, walk = got["first0"].transit, base_df.shifted, base_df.walk
    is_won = shifted.fillna(np.inf) < walk.fillna(np.inf)
    is_ok = np.where(is_won, equal(first0, shifted - SHIFT_S),
                     (first0 >= np.fmin(walk, shifted) - SHIFT_S) & (first0 <= walk.fillna(np.inf))
                     | (first0.isna() & shifted.isna()))
    off = int((~is_ok).sum())
    lines.append(f"(T4) first0 transit vs the 1-min shift: {verdict(off, n)} ({off} pairs off; shift's transit wins on "
                 f"{int(is_won.sum())}: first0 = shifted - 60 on {int(equal(first0, shifted - SHIFT_S)[is_won].sum())})")
    t4_df = pd.DataFrame({"first0": first0, "shifted": shifted, "walk": walk, "is_won": is_won})
    lines += listed("T4", ~is_ok, t4_df, strata)

    p3 = got["p3"].transit
    is_ok = (p3 >= first0) | (p3.isna() & first0.isna()) | (p3.isna() & (first0 > (MAX_TIME_MIN * SECONDS_PER_MIN
                                                                                       - TRANSFER_BUFFER_S)))
    off = int((~is_ok).sum())
    lines.append(f"(T5) p3 transit >= first0 transit: {verdict(off, n)} ({off} pairs off)")
    lines += listed("T5", ~is_ok, pd.DataFrame({"p3": p3, "first0": first0}), strata)
    delta = (p3 - first0).rename("p3_minus_first0_s")
    lines.append("    p3 - first0 (s) by stratum:\n" + pd.DataFrame({"d": delta, "stratum": strata}).groupby("stratum").d
                 .describe(percentiles=[.5]).round(1).to_string())
    lines.append("    p3 - first0 values: " + str(delta.dropna().value_counts().sort_index().to_dict()))

    google_df = pd.concat([pd.read_csv(path).assign(set_name=name) for name, path in GOOGLE_ROUTES_PATHS.items()])
    google_df = google_df[google_df.is_default.astype(bool)].set_index(["set_name", "draw_no"])[GOOGLE_COL]
    google_s = pd.Series([google_df.loc[(s, d)] for s, d in zip(pairs_df.set_name, pairs_df.index)], index=pairs_df.index,
                         dtype=float)
    record_s = pd.Series(np.where(is_won, shifted - SHIFT_S, walk), index=pairs_df.index)
    p3_model_s = np.fmin(p3, walk)
    lines.append(f"(R) seconds error vs Google's default {GOOGLE_COL}, model of record (no-wait on patch 1):\n"
                 + error_table(record_s, google_s, strata).to_string())
    lines.append("(R) p3 (min(p3 transit, walk)):\n" + error_table(p3_model_s, google_s, strata).to_string())
    lines.append(f"    pairs where p3 model != model of record: {int((~equal(p3_model_s, record_s)).sum())}")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_score.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    pd.DataFrame({"stratum": strata, "google_s": google_s, "record_s": record_s, "first0_s": first0, "p3_s": p3,
                  "walk_s": walk}).to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_scored.csv")


# --- full training run -----------------------------------------------------------------------------
def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def training_pairs():
    pairs_df = pd.read_csv(newest(RANGE_RESULTS_GLOB))
    return pairs_df[pairs_df.is_scored.astype(bool)]


def route_train(jar_tag, release):
    """Full training routing on one jar (docstring); appends a row per pair, resumes from the newest table."""
    assert jar_tag in TRAIN_JARS and release in STUB_BUILDS
    pairs_df = training_pairs()
    pairs_df = pairs_df[pairs_df.release.astype(str) == release]
    saved = newest(f"{NAME}_2*_trainroutes_{jar_tag}_{release}.csv")
    table_path = saved if saved is not None else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_trainroutes_{jar_tag}_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"{jar_tag} {release}: {len(pairs_df)} pairs, {len(done)} done, {len(todo_df)} to route -> {table_path.name}",
          flush=True)
    ttm, stub_of, origin_of = open_network(TRAIN_JARS[jar_tag], release)
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        origin, destination, departure = pair_points(pair, stub_of, origin_of)
        row = {"draw_no": pair.draw_no, "release": release}
        if jar_tag == "p1":
            row["shifted"] = ttm(origin, destination, departure - datetime.timedelta(seconds=SHIFT_S), True,
                                 MAX_TIME_MIN + SHIFT_S // SECONDS_PER_MIN)
            row["walk"] = ttm(origin, destination, departure, False)
        else:
            row["transit"] = ttm(origin, destination, departure, True)
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
    """Run 3's measures for one model, with medians beside means; returns (lines, hard-miss total, largest gain)."""
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
    if seconds is not None:
        sec_err = pd.DataFrame({"err_s": np.where(np.isfinite(seconds), seconds, np.nan) - google_s,
                                "group": df.boardings.to_numpy()}).dropna()
        g = sec_err.groupby("group").err_s
        sec_table = pd.DataFrame({"n": g.size(), "median_s": g.median(), "mean_s": g.mean(),
                                  "median_abs_s": g.apply(lambda x: x.abs().median()),
                                  "mean_abs_s": g.apply(lambda x: x.abs().mean())})
        sec_table.loc["all"] = [len(sec_err), sec_err.err_s.median(), sec_err.err_s.mean(), sec_err.err_s.abs().median(),
                                sec_err.err_s.abs().mean()]
        lines.append(f"  seconds error vs Google {GOOGLE_COL} by Google default's boardings:\n"
                     + sec_table.round(1).to_string())
    return lines, hard, total, gain


def score_train():
    pairs_df = training_pairs().set_index("draw_no").sort_index()
    routes = {}
    for jar_tag in TRAIN_JARS:
        paths = [newest(f"{NAME}_2*_trainroutes_{jar_tag}_{release}.csv") for release in STUB_BUILDS]
        assert all(paths), f"route_train {jar_tag} on both releases first"
        routes[jar_tag] = pd.concat([pd.read_csv(p) for p in paths]).set_index("draw_no").sort_index()
        assert list(routes[jar_tag].index) == list(pairs_df.index), f"{jar_tag}: routed pairs != training pairs"
    shifted, walk, p3 = routes["p1"].shifted, routes["p1"].walk, routes["p3"].transit
    n = len(pairs_df)
    lines = [f"{NAME} {run_date()} score_train: {n} training pairs ({pairs_df.set_name.value_counts().to_dict()}), "
             f"speed {SPEED_KMH} km/h, transfer buffer {TRANSFER_BUFFER_S} s"]

    p1_df = baseline()
    p3_saved = routed("p3").transit
    ids = p1_df.index
    off_f1 = {"shifted": int((~equal(shifted.loc[ids], p1_df.shifted)).sum()),
              "walk": int((~equal(walk.loc[ids], p1_df.walk)).sum()),
              "p3 transit": int((~equal(p3.loc[ids], p3_saved.loc[ids])).sum())}
    is_f1 = sum(off_f1.values()) == 0
    lines.append(f"(F1) the {len(ids)} pairs routed before reproduce exactly: {'PASS' if is_f1 else 'FAIL'} ({off_f1})")
    is_won = (shifted.fillna(np.inf) < walk.fillna(np.inf)).to_numpy()
    floor_s = (shifted - SHIFT_S).to_numpy()
    is_ok = ~is_won | (p3.to_numpy() >= floor_s) | (p3.isna().to_numpy()
                                                    & (floor_s > MAX_TIME_MIN * SECONDS_PER_MIN - TRANSFER_BUFFER_S))
    off_f2 = int((~is_ok).sum())
    f2 = verdict(off_f2, n)
    lines.append(f"(F2) p3 transit >= shifted - 60 where shifted < walk ({int(is_won.sum())} pairs): {f2} ({off_f2} off)")
    lines += [f"    F2 draw {d}: p3 {p3.loc[d]}, shifted {shifted.loc[d]}, walk {walk.loc[d]}" for d in pairs_df.index[~is_ok]]
    if not is_f1 or f2 == "FAIL":
        print("\n".join(lines))
        raise SystemExit("checks failed: stop")

    google_df = pd.concat([pd.read_csv(path).assign(set_name=name) for name, path in GOOGLE_ROUTES_PATHS.items()])
    google_df = google_df[google_df.is_default.astype(bool)].set_index(["set_name", "draw_no"])
    keys = list(zip(pairs_df.set_name, pairs_df.index))
    google_s = google_df[GOOGLE_COL].reindex(keys).to_numpy(dtype=float)
    steps = google_df.n_transit_steps.reindex(keys).to_numpy(dtype=float)
    df = pairs_df.reset_index().assign(boardings=[BOARDING_GROUPS[min(int(s), 2)] if np.isfinite(s) else np.nan for s in steps])
    lines.append(f"Google defaults found: {int(np.isfinite(google_s).sum())} of {n}")
    is_random = (df.set_name != TOPUP_SET).to_numpy()

    record_s = np.where(is_won, shifted - SHIFT_S, walk.fillna(np.inf))
    p3_s = np.fmin(p3.fillna(np.inf).to_numpy(), walk.fillna(np.inf).to_numpy())
    models = {"model of record (patch 1, no-wait)": (rounded_min(record_s), record_s),
              "p3 (min(p3 transit, walk))": (rounded_min(p3_s), p3_s)}
    q24_df = pd.read_csv(Q24_PAIRS_PATH).set_index("draw_no").reindex(pairs_df.index)
    q24_col = next(c for c in q24_df.columns if c.startswith(Q24_COMBINED_PREFIX))
    context = {f"context: run 3 stubs {q24_col}": (q24_df[q24_col].fillna(np.inf).to_numpy(), None)}

    readings = {}
    base_hard = None
    for label, (minutes, seconds) in {**models, **context}.items():
        text, hard, total, gain = model_lines(label, minutes, seconds, df, google_s, is_random, base_hard)
        lines += text
        readings[label] = (total, gain)
        if base_hard is None:
            base_hard = hard
    record_min, p3_min = models["model of record (patch 1, no-wait)"][0], models["p3 (min(p3 transit, walk))"][0]
    is_p3_transit = p3.fillna(np.inf).to_numpy() < walk.fillna(np.inf).to_numpy()
    lines += ["", "p3 vs model of record:",
              f"  minutes changed on {int((p3_min != record_min).sum())} pairs; change (min) "
              + str(pd.Series(p3_min - record_min)[np.isfinite(p3_min - record_min)].value_counts().sort_index().to_dict()),
              f"  band calls changed {int((band_of(p3_min) != band_of(record_min)).sum())}",
              f"  winner flips: transit -> walk {int((is_won & ~is_p3_transit).sum())}, walk -> transit "
              f"{int((~is_won & is_p3_transit).sum())}",
              f"  model of record (patch 1) vs run 3 stubs: minutes differ on "
              f"{int((record_min != context[next(iter(context))][0]).sum())} pairs"]
    base_total = readings["model of record (patch 1, no-wait)"][0]
    total, gain = readings["p3 (min(p3 transit, walk))"]
    reading = ("IMPROVES" if total < base_total and gain <= SNAP_TOLERANCE_MISSES
               else "WORSENS" if total > base_total else "MIXED")
    lines += ["", f"READING (run 3's rule, OK'd by the user 2026-10-21): p3 hard misses {total} vs model of record "
              f"{base_total}, largest gain in one test {gain:+d} -> {reading}",
              f"  (context: run 3 stubs {readings[next(iter(context))][0]})"]
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_train_score.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    pd.DataFrame({"draw_no": pairs_df.index, "set_name": df.set_name, "release": df.release, "boardings": df.boardings,
                  "google_s": google_s, "google_min": df.google_min, "record_s": record_s, "p3_s": p3_s,
                  "record_min": record_min, "p3_min": p3_min}).to_csv(
        DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_train_scored.csv", index=False)


if __name__ == "__main__":
    {"build": build, "route": route, "score": score, "route_train": route_train,
     "score_train": score_train}[sys.argv[1]](*sys.argv[2:])
