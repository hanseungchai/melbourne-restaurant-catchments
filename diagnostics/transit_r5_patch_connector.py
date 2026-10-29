"""R5 patch 2 (TRN-16 register): no connector charge, the straight walk from a point to its street left out at both ends.

Claim under test (concepts/transit.md TRN-16; DESIGN.md Q24 (1); walk.md WLK-3, WLK-6): R5 charges the off-street
distance from a point to its split on the nearest walkable edge (`Split.distanceToEdge_mm`) at three places on TTM's
path, and a patch that zeroes it there moves nothing else. Source read 2026-10-21 (inputs/r5py/r5-7.5.1, never edited):
  origin       StreetRouter.setOrigin(lat, lon): offStreetTime added to both start states, distance too;
  destination  LinkedPointSet.timeToPoint (walk-only, any edge) and LinkedPointSet.eval (origin and destination on the
               same edge: both connectors);
  after transit LinkedPointSet.distanceToPoint (stop-to-destination egress tables, walk).
Google charges no connector (WLK-3). The model of record drops it by snapping both points onto R5's split in Python
(transit_q24_combined.py (a)); the patch is meant to give the same seconds on the original points, so production needs
no snapping. Where the pipeline would rely on it: transit bands 1-2 through the patched jar, origins and destinations
as drawn. The patch applies to every street mode (cars too); the pipeline routes only walk and transit in R5.

Patch 2 sits on patch 3 (and so on patch 1, seconds out): every jar here is P3's jar with StreetRouter and
LinkedPointSet replaced. One private static helper per class, `chargedOffStreetMm(mm)` = mm (charge) or 0, called at
the eight sites; private static so LinkedPointSet's default serialVersionUID (Serializable, none declared) is unchanged.
Variants:
  p3          P3's jar as built (no swap).
  recompiled  both classes compiled from the unchanged source.
  off         the patched code with the connector charged (the new code path, stock behaviour).
  p2          the patched code, connector not charged.
R5 caches each destination set's egress table inside the JVM, so one variant per process (never switched in a JVM).

Steps (modes; one JVM per process, jar chosen at JVM start through r5py's `--r5-classpath`):
  build  The two sources from `inputs/r5py/r5-7.5.1`, per variant, javac 21 against P3's jar; each variant's classes
      into its own copy of that jar in outputs/r5_patches/. (B1) recompiled vs the jar's classes (both classes and their
      inner classes), javap -c -p identical, else stop. (B2) off and p2 vs the jar: the differing javap lines, masked as
      P3's B2, printed (expected: the helper in each class and a call to it at each site; off and p2 differ only in the
      helper's constant). (B3) serialver of LinkedPointSet equal in P3's jar and in each variant's jar, else stop.
  route <variant> <points> <release>  The seeded 100-pair set of transit_r5_patch_seconds.py (reused, never redrawn),
      on the pathways v2 network of the release (no stubs: patch 1 replaced them for Q24 (3), user 2026-10-21) at
      4.143 km/h; points `snap` = origin split (transit_q24_combined originsplits) and destination split (the stub
      table's base point, R5's split on v2), or `orig` = the drawn points. Two TTM calls: transit at t (max_time
      MAX_TIME_MIN) and walk-only. Guard: StreetRouter, LinkedPointSet, FastRaptorWorker and TravelTimeReducer all load
      from the variant's jar.
  score  Rules (Claude's; TRN-16 register (user, 2026-10-21); equivalence test OK'd by the user 2026-10-21; written
      before any result). Baseline = p3 snap (P3 with Python snapping: the model of record's convention on P3).
      (T1) recompiled = p3, snap and orig, every value (NaN = NaN). Any difference fails.
      (T2) off = p3, snap and orig, every value. Any difference fails.
      (T3) p2 snap = p3 snap: should not differ (a snapped point sits within R5's fixed-point rounding, ~1 cm, of its
           edge, under one second). < MINOR_SHARE of pairs = flagged minor deviation (listed), >= MINOR_SHARE fails.
      (T4) p2 orig = p3 snap: the main equivalence, patch = Python snapping. Same minor / fail line; every differing
           pair listed with both values and its connector lengths.
      (T5) p2 orig <= p3 orig on every value (dropping a charge never arrives later; NaN in p2 only where p3 orig is
           NaN). Same minor / fail line.
      (R, reported, no verdict) connector cost = p3 orig - p2 orig (s) by stratum and call: n, mean, median, max; and
           the drawn points' connector lengths (origin, destination; m) from the saved splits.
      Context, no verdict: p3 snap here (v2, no stubs) vs P3's saved 100-pair routes (stub network, same points):
           values differing (the stubs' effect alone).

Predictions (Claude's, before any result): B1 passes; B2 shows two helpers and eight call sites; B3 passes. T1, T2, T3
exact. T4 exact, or a flagged handful one second off where the ~1 cm residual crosses an integer cut. T5 holds. R:
walk-only median ~14 s (median 8.1 m per end at 4.143 km/h, WLK-3); transit pairs similar, a few larger where the
earlier arrival catches an earlier vehicle. Context: 0 or a few values differ.

Conclusion (run 2026-10-21; rules above written before any result):
  B1 PASS (0 differing javap lines over the 7 classes). B2 as predicted: a private constant and helper in each class
  (`iload_0` when charged, `iconst_0` for p2) and one `invokestatic chargedOffStreetMm` at each of the eight sites;
  nothing else once pool indices and offsets are masked. B3 PASS (serialVersionUID 5478541176114557671 in all jars).
  T1 PASS and T2 PASS, snap and orig (0 of 200 values each). T5 PASS (p2 never later than p3 on the drawn points).
  T3 FAIL on the letter: 1 pair (1 %, the line is < 1 %), transit 1 s earlier. T4 FAIL: 5 pairs, 7 of 200 values, each
  1-2 s, either sign (p2 orig - p3 snap: +1, +1, +2, -1, +1 s).
  Cause (`why` mode, all six pairs, both releases): the snapped point is not the drawn point's split. It is that
  split written to coordinates and split again: on 3 pairs the split sat at an edge end and the copy, on the shared
  vertex, re-splits onto the neighbouring edge; on 3 it stays on its edge but moves 11-22 mm along it. A 1-2 s gap
  follows from R5's integer cuts (setOrigin floors the along-edge distance to whole metres, e.g. draw 46566 d1
  67,004 -> 66,993 mm, 67 -> 66 m; edge times are ceiled). P2 on the drawn points charges exactly the drawn point's
  own split without its connector, which is what snapping was meant to do; the differences are snapping's, not the
  patch's (Claude's reading; the T3 / T4 verdicts stand as FAIL on the pre-set line). Prediction check: T3 wrong
  (assumed only the off-street residual moves, ~1 cm; the along-edge position and edge choice move too); T4 inside
  the predicted kind.
  (R) connector cost p3 orig - p2 orig: walk call median 15 s, mean 23.8, max 164 (walk_only stratum median 10 s);
  transit call median 8 s, mean 23.2, max 1,020 s (an earlier vehicle caught). Drawn connectors: origin median 10.3 m
  (p90 40.3, max 175), destination 8.3 m (p90 21.1, max 48.4); snapped residual 0.011 m max.
  Context: v2 vs the stub network, same snapped points and jar: 44 of 200 values differ, nearly all walk 1-5 s later
  on the stub network (Claude's reading, unchecked: each stub splits an edge, adding one more ceiled edge time; the
  per-edge rounding candidate, TRN-16).
  Reading accepted by the user 2026-10-21: the T3 / T4 differences are snapping's rounding, not the patch; on to the
  full training run.

Full training run (TRN-16 verdict; rule written before the run, as P3's, user go 2026-10-21). Pairs: every scored
training pair (v2's range results: train half, second batch, top-up; test half closed), on the v2 network of its
release (no stubs) at 4.143 km/h. Steps: `route_train <p3snap|p2orig> <release>`: p3snap = P3's jar on the snapped
points (origin split, destination split), p2orig = P2's jar on the drawn points; transit at t and walk-only per pair;
rows appended per pair, a rerun resumes. `score_train`:
  Model per variant: min(transit, walk) in seconds, rounded to the nearest minute (half up; SCR-10).
  Check first, else stop: (F1) the 100 pairs routed by `route` reproduce exactly (p3snap = p3 snap, p2orig = p2 orig,
  both calls).
  Reported (as P3's score_train): labels to Google's k = 2 range, error to the range (median, mean), the four hard-miss
  tests (random samples only), TRN-13 zones, count ratios, walk-only defaults, seconds error to Google's
  arrival_from_request_s by the boardings of Google's default (0 / 1 / 2+), band calls changed, winner flips.
  Equivalence, reported, no verdict: pairs whose seconds differ between p2orig and p3snap, by size (1-2 s, 3-59 s,
  >= 60 s) and in minutes. Context, no verdict: P3's saved full-run model (stub network, snapped points).
  Reading (run 3's rule): IMPROVES if p2's hard-miss total falls below p3snap's and no test gains more than
  SNAP_TOLERANCE_MISSES; WORSENS if it rises; else MIXED.
  Predictions (Claude's, before any result): seconds differ on ~5% of pairs, almost all by 1-2 s, a few by a headway
  where a second decides a catch; minutes on ~1%; hard misses equal or within 1; MIXED (equal totals) most likely.
  p3snap on v2 within a pair or two of P3's saved 23.
  Conclusion (run 2026-10-21, 3,448 pairs; rule above written before the run): F1 PASS (0 values off on either
  variant). Hard misses p3snap -> p2orig: lost 10 0/50, false 10 2/294, lost 20 7/248, false 20 14/503 on both; total
  23 -> 23, largest gain 0: MIXED (equal). Labels late / agree / early 792 / 1,490 / 1,166 -> 790 / 1,492 / 1,166; error to
  the range median 0, mean -1.67 both; zones pass for both, identical; count ratios 0.981 / 1.042 both; walk-only
  exact 0.416 -> 0.422; seconds error vs Google identical to 0.1 s in every boardings group (all: median -9, mean
  -127.7 s). Equivalence: seconds differ on 35 of 3,424 pairs (1-2 s: 34, 3-59 s: 1, >= 60 s: 0; p2 earlier on 23),
  minutes on 3 (-1, -1, +1), band calls 0, winner flips 0. p3snap on v2 vs P3's saved run on the stub network: minutes
  differ on 5 pairs, hard misses 23 both.
  Prediction check: MIXED and equal totals right; seconds differ on 1.0%, not ~5%; minutes on 0.09%, not ~1%.
  Reading (Claude's): P2 on the drawn points gives the model of record's results without Python snapping; the
  differences are the snapping rounding found in `why`, too small to move a band call. The lost-reach FAIL flags are
  as before (lost 10 report-only; lost 20 upper 0.057 also on P3's saved run). The numpy "invalid value" warnings in
  score_train come from inf - inf on pairs over max_time in both, excluded by the finite masks.

Inputs (read only): P3's jar and saved 100-pair routes, patch 1's pair set, v2 networks and feeds, run 3's stub tables
and origin splits (diagnostics/diagnostic_data/), `inputs/r5py/` source. Writes jars to outputs/r5_patches/ and tables
to diagnostics/diagnostic_data/. Self-contained (CLAUDE.md D1). No paid API calls. Usage:
`python transit_r5_patch_connector.py build`, `... route <variant> <snap|orig> <release>`, `... score`, `... why <release>`
(added after the first score: R5's splits of the drawn and snapped points of the T3 / T4 differing pairs),
`... route_train <p3snap|p2orig> <release>`, `... score_train`.
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
R5_SOURCE_DIR = PROJECT_ROOT / "inputs" / "r5py" / "r5-7.5.1" / "src" / "main" / "java"
PATCH_DIR = PROJECT_ROOT / "outputs" / "r5_patches"
JDK_BIN_DIR = Path(r"C:\Program Files\Java\jdk-21.0.12\bin")
P1_NAME = "transit_r5_patch_seconds"
P3_NAME = "transit_r5_patch_board_wait"
BASE_JAR_PATH = PATCH_DIR / f"r5-v7.5.1-r5py-all_{P3_NAME}_p3.jar"
P1_PAIRS_PATH = DIAGNOSTIC_DATA_DIR / f"{P1_NAME}_20261021_pairs.csv"
P3_ROUTES_DATE = "20261021"
Q24_NAME = "transit_q24_combined_20261021"
STUB_BUILDS = {"20261009": "4135_4143_4160_b4", "20261016": "4135_4143_4160_b5"}   # run 3's final builds (splits only)
V2_NAME = "transit_pathway_network_v2"
NAME = "transit_r5_patch_connector"

# --- the patch -------------------------------------------------------------------------------------
ROUTER_CLASS = "com.conveyal.r5.streets.StreetRouter"
LINKAGE_CLASS = "com.conveyal.r5.streets.LinkedPointSet"
PATCHED_CLASSES = [ROUTER_CLASS, LINKAGE_CLASS]
GUARD_CLASSES = PATCHED_CLASSES + ["com.conveyal.r5.profile.FastRaptorWorker", "com.conveyal.r5.analyst.TravelTimeReducer"]
VARIANT_CHARGES = {"off": True, "p2": False}
VARIANTS = ["p3", "recompiled"] + list(VARIANT_CHARGES)
POINTS = ["snap", "orig"]
TAG = "// PLATICA TRN-16 P2"
SITES = {   # class -> (old line, new line) pairs, each old line found exactly once
    ROUTER_CLASS: [
        ("int offStreetTime = split.distanceToEdge_mm / (int) (profileRequest.walkSpeed * 1000);",
         f"int offStreetTime = chargedOffStreetMm(split.distanceToEdge_mm) / (int) (profileRequest.walkSpeed * 1000); {TAG}"),
        ("startState1.distance = split.distance1_mm + split.distanceToEdge_mm;",
         f"startState1.distance = split.distance1_mm + chargedOffStreetMm(split.distanceToEdge_mm); {TAG}"),
        ("startState0.distance = split.distance0_mm + split.distanceToEdge_mm;",
         f"startState0.distance = split.distance0_mm + chargedOffStreetMm(split.distanceToEdge_mm); {TAG}")],
    LINKAGE_CLASS: [
        ("travelTimes[i] = origin.distanceToEdge_mm / offStreetSpeed +",
         f"travelTimes[i] = chargedOffStreetMm(origin.distanceToEdge_mm) / offStreetSpeed + {TAG}"),
        ("distancesToEdge_mm[i] / offStreetSpeed; // from destination split point to destination",
         f"chargedOffStreetMm(distancesToEdge_mm[i]) / offStreetSpeed; {TAG} (from destination split point to destination)"),
        ("distance0 += distances0_mm[pointIndex] + distancesToEdge_mm[pointIndex];",
         f"distance0 += distances0_mm[pointIndex] + chargedOffStreetMm(distancesToEdge_mm[pointIndex]); {TAG}"),
        ("distance1 += distances1_mm[pointIndex] + distancesToEdge_mm[pointIndex];",
         f"distance1 += distances1_mm[pointIndex] + chargedOffStreetMm(distancesToEdge_mm[pointIndex]); {TAG}"),
        ("int offStreetTime = distancesToEdge_mm[pointIndex] / offStreetSpeed;",
         f"int offStreetTime = chargedOffStreetMm(distancesToEdge_mm[pointIndex]) / offStreetSpeed; {TAG}")]}
CLASS_END = "\n}\n"
METHOD_TEMPLATE = """
    {tag}: the straight walk between a point and its street split (distanceToEdge_mm), charged or not. Private static
    // so a Serializable class keeps its default serialVersionUID.
    private static final boolean CHARGE_CONNECTOR = {charge};

    private static int chargedOffStreetMm (int distanceToEdge_mm) {{
        return CHARGE_CONNECTOR ? distanceToEdge_mm : 0;
    }}
"""
CONST_POOL_REF = re.compile(r"#\d+(:#\d+)?")
CODE_OFFSET = re.compile(r"^\s*\d+: ")
BRANCH_TARGET = re.compile(r"\b(goto|goto_w|if\w*|jsr)\s+\d+")
SWITCH_TARGET = re.compile(r"^\s*(-?\d+|default): \d+$")

# --- values copied from transit_r5_patch_board_wait.py ----------------------------------------------
R5_MAX_MEMORY = "7G"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
SPEED_TAG = "median"
SPEED_KMH = 4.143                              # Q24 (2) median; user 2026-10-21
MAX_TIME_MIN = 90
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
CALLS = ["transit", "walk"]
MINOR_SHARE = 0.01
SPLIT_RADIUS_M = 1600                          # R5's StreetLayer.LINK_RADIUS_METERS (connector lengths for R only)
MM_PER_M = 1000
SECONDS_PER_MIN = 60
GOOGLE_COL = "arrival_from_request_s"          # the scorers' Google quantity (transit_fetch.py google_min)

# --- full training run (values copied from transit_r5_patch_board_wait.py) -------------------------
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
GOOGLE_ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                       "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                       "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
RANGE_RESULTS_GLOB = f"{V2_NAME}_2*_range_owndate_results.csv"
P3_TRAIN_SCORED_PATH = DIAGNOSTIC_DATA_DIR / f"{P3_NAME}_{P3_ROUTES_DATE}_train_scored.csv"
TRAIN_VARIANTS = {"p3snap": ("p3", "snap"), "p2orig": ("p2", "orig")}
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
DIFF_BINS_S = [(1, 2), (3, 59), (60, np.inf)]  # equivalence report: |p2orig - p3snap| seconds
PROGRESS_EVERY = 500


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def jar_path(variant):
    return BASE_JAR_PATH if variant == "p3" else PATCH_DIR / f"r5-v7.5.1-r5py-all_{NAME}_{variant}.jar"


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
    return subprocess.run([str(JDK_BIN_DIR / "serialver"), "-classpath", str(classpath), LINKAGE_CLASS],
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


def patched_source(source, class_name, is_charged):
    for old, new in SITES[class_name]:
        assert source.count(old) == 1, f"{class_name}: site not found exactly once: {old}"
        source = source.replace(old, new)
    assert source.endswith(CLASS_END) and source.count(TAG) == len(SITES[class_name])
    method = METHOD_TEMPLATE.format(tag=TAG, charge=str(is_charged).lower())
    return source[:-len(CLASS_END)] + "\n" + method + CLASS_END


def diff_lines(a, b):
    return [line for line in difflib.unified_diff(a, b, n=0, lineterm="") if not line.startswith(("---", "+++"))]


# --- build -----------------------------------------------------------------------------------------
def build():
    assert BASE_JAR_PATH.exists(), "P3's jar missing: run transit_r5_patch_board_wait.py build"
    sources = {c: (R5_SOURCE_DIR / f"{class_file(c)}.java").read_text(encoding="utf-8") for c in PATCHED_CLASSES}
    lines = [f"{NAME} {run_date()} build (base: {BASE_JAR_PATH.name})"]
    base_serial = serialver(BASE_JAR_PATH)
    texts = {"recompiled": sources}
    texts.update({v: {c: patched_source(s, c, charge) for c, s in sources.items()} for v, charge in VARIANT_CHARGES.items()})
    is_ok = True
    for variant, class_texts in texts.items():
        variant_dir = PATCH_DIR / f"{NAME}_{variant}"
        classes_dir = variant_dir / "classes"
        classes_dir.mkdir(parents=True, exist_ok=True)
        src_paths = []
        for class_name, text in class_texts.items():
            src_path = variant_dir / "src" / f"{class_file(class_name)}.java"
            src_path.parent.mkdir(parents=True, exist_ok=True)
            src_path.write_text(text, encoding="utf-8", newline="\n")
            src_paths.append(str(src_path))
        subprocess.run([str(JDK_BIN_DIR / "javac"), "--release", "21", "-proc:none", "-nowarn", "-cp", str(BASE_JAR_PATH),
                        "-d", str(classes_dir)] + src_paths, check=True)
        names = class_names(classes_dir)
        assert all(any(n == c or n.startswith(c + "$") for c in PATCHED_CLASSES) for n in names), f"unexpected classes: {names}"
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
            lines.append(f"(B2) {variant} (charge {VARIANT_CHARGES[variant]}) vs the jar's classes, javap -c -p differing lines "
                         f"(constant-pool indices masked; {n_diff} lines unmasked):")
            lines += [f"    {line}" for line in masked]
        serial = serialver(jar)
        lines.append(f"(B3) {variant} LinkedPointSet serialVersionUID: {'PASS' if serial == base_serial else 'FAIL'} ({serial})")
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


def split_lookups(release):
    """Saved splits of run 3: destination -> R5's split on v2 (stub base), origin -> R5's split on v2."""
    stubs_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{Q24_NAME}_stubs_{release}_{STUB_BUILDS[release]}.csv")
    stubs_df = stubs_df[(stubs_df.status == "ok") & (stubs_df.speed_tag == SPEED_TAG)]
    dest_of = {(s.dest_lat, s.dest_lon): (s.base_lat, s.base_lon) for s in stubs_df.itertuples()}
    origins_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{Q24_NAME}_originsplits_{release}.csv")
    origin_of = {(o.origin_lat, o.origin_lon): (o.split_lat, o.split_lon) for o in origins_df.itertuples()}
    return dest_of, origin_of


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


def route(variant, points, release):
    assert variant in VARIANTS and points in POINTS and release in STUB_BUILDS
    ttm, network = open_network(jar_path(variant), release)
    dest_of, origin_of = split_lookups(release)
    pairs_df = pd.read_csv(P1_PAIRS_PATH)
    pairs_df = pairs_df[pairs_df.release.astype(str) == release]
    street_layer = network._transport_network.streetLayer
    from com.conveyal.r5.profile import StreetMode
    rows = []
    started = datetime.datetime.now()
    for pair in pairs_df.itertuples():
        drawn_origin, drawn_dest = (pair.origin_lat, pair.origin_lon), (pair.dest_lat, pair.dest_lon)
        origin, destination = ((origin_of[drawn_origin], dest_of[drawn_dest]) if points == "snap"
                               else (drawn_origin, drawn_dest))
        departure = (datetime.datetime.combine(datetime.date.fromisoformat(str(pair.own_date)), datetime.time())
                     + datetime.timedelta(minutes=int(pair.dep_min_of_day)))
        row = {"draw_no": pair.draw_no, "release": release, "variant": variant, "points": points,
               "transit": ttm(origin, destination, departure, True), "walk": ttm(origin, destination, departure, False)}
        for end, (lat, lon) in [("origin", origin), ("dest", destination)]:
            split = street_layer.findSplit(float(lat), float(lon), SPLIT_RADIUS_M, StreetMode.WALK)
            row[f"{end}_connector_m"] = split.distanceToEdge_mm / MM_PER_M if split is not None else np.nan
        rows.append(row)
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_routes_{variant}_{points}_{release}.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"done: {len(rows)} pairs in {datetime.datetime.now() - started} -> {out_path.name}", flush=True)


# --- score -----------------------------------------------------------------------------------------
def routed(variant, points):
    frames = []
    for release in STUB_BUILDS:
        paths = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_routes_{variant}_{points}_{release}.csv"))
        assert paths, f"route {variant} {points} {release} first"
        frames.append(pd.read_csv(paths[-1]))
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
    got = {(v, p): routed(v, p) for v in VARIANTS for p in POINTS}
    assert all(list(df.index) == list(pairs_df.index) for df in got.values())
    base = got[("p3", "snap")][CALLS]
    lines = [f"{NAME} {run_date()} score: {n} pairs ({strata.value_counts().to_dict()}), speed {SPEED_KMH} km/h, v2 network"]

    for label, variant in [("T1", "recompiled"), ("T2", "off")]:
        for points in POINTS:
            ref = got[("p3", points)][CALLS]
            is_eq = equal(got[(variant, points)][CALLS], ref)
            off = int((~is_eq.all(axis=1)).sum())
            lines.append(f"({label}) {variant} {points} = p3 {points}: {verdict(off, n, True)} "
                         f"({off} pairs, {int((~is_eq).sum())} of {is_eq.size} values differ)")
            lines += listed(label, ~is_eq.all(axis=1), got[(variant, points)][CALLS].join(ref, rsuffix="_p3"), strata)

    for label, key in [("T3", ("p2", "snap")), ("T4", ("p2", "orig"))]:
        df = got[key]
        is_eq = equal(df[CALLS], base)
        mask = ~is_eq.all(axis=1)
        off = int(mask.sum())
        lines.append(f"({label}) p2 {key[1]} = p3 snap: {verdict(off, n)} ({off} pairs, {int((~is_eq).sum())} of "
                     f"{is_eq.size} values differ)")
        frame = df[CALLS].join(base, rsuffix="_p3snap").join(got[("p3", "orig")][["origin_connector_m", "dest_connector_m"]])
        lines += listed(label, mask, frame, strata)

    p2_orig, p3_orig = got[("p2", "orig")][CALLS], got[("p3", "orig")][CALLS]
    is_ok = (p2_orig <= p3_orig) | (p2_orig.isna() & p3_orig.isna()) | (p3_orig.isna() & p2_orig.notna())
    mask = ~is_ok.all(axis=1)
    off = int(mask.sum())
    lines.append(f"(T5) p2 orig <= p3 orig, every value: {verdict(off, n)} ({off} pairs off)")
    lines += listed("T5", mask, p2_orig.join(p3_orig, rsuffix="_p3orig"), strata)

    cost = (p3_orig - p2_orig).join(strata)
    lines.append("(R) connector cost, p3 orig - p2 orig (s):")
    for call in CALLS:
        table = cost.groupby("stratum")[call].describe(percentiles=[.5])[["count", "mean", "50%", "max"]]
        table.loc["all"] = cost[call].describe(percentiles=[.5])[["count", "mean", "50%", "max"]]
        lines.append(f"  {call}:\n" + table.round(1).to_string())
    connectors = got[("p3", "orig")][["origin_connector_m", "dest_connector_m"]]
    lines.append("(R) drawn points' connector length (m):\n" + connectors.describe(percentiles=[.5, .9]).round(2).to_string())
    snapped = got[("p3", "snap")][["origin_connector_m", "dest_connector_m"]]
    lines.append(f"    snapped points' residual connector, max (m): origin {snapped.origin_connector_m.max():.3f}, "
                 f"destination {snapped.dest_connector_m.max():.3f}")

    saved = pd.concat([pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{P3_NAME}_{P3_ROUTES_DATE}_routes_p3_{release}.csv")
                       for release in STUB_BUILDS]).set_index("draw_no").sort_index()[CALLS]
    is_eq = equal(base, saved.loc[base.index])
    lines.append(f"Context: p3 snap on v2 (no stubs) vs P3's saved routes on the stub network: {int((~is_eq).sum())} of "
                 f"{is_eq.size} values differ")
    lines += listed("context", ~is_eq.all(axis=1), base.join(saved, rsuffix="_stubnet"), strata)
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_score.txt").write_text(text + "\n", encoding="utf-8", newline="\n")


def why(release):
    """T3 / T4 differing pairs of a release: R5's split of the drawn and the snapped point at each end (edge, along-edge
    and off-street mm, and the whole metres setOrigin floors to), to see whether a 1-2 s gap is the ~1 cm coordinate
    rounding of the snapped point crossing a metre (origin) or millimetre-second (destination) cut."""
    assert release in STUB_BUILDS
    _, network = open_network(jar_path("p3"), release)
    from com.conveyal.r5.profile import StreetMode
    street_layer = network._transport_network.streetLayer
    dest_of, origin_of = split_lookups(release)
    pairs_df = pd.read_csv(P1_PAIRS_PATH).set_index("draw_no")
    base = routed("p3", "snap")[CALLS]
    is_off = ~(equal(routed("p2", "snap")[CALLS], base).all(axis=1) & equal(routed("p2", "orig")[CALLS], base).all(axis=1))
    lines = [f"{NAME} {run_date()} why {release}"]
    for draw_no in base.index[is_off]:
        pair = pairs_df.loc[draw_no]
        if str(pair.release) != release:
            continue
        lines.append(f"draw {draw_no} ({pair.stratum})")
        drawn = {"origin": (pair.origin_lat, pair.origin_lon), "dest": (pair.dest_lat, pair.dest_lon)}
        snapped = {"origin": origin_of[drawn["origin"]], "dest": dest_of[drawn["dest"]]}
        for end in drawn:
            for label, (lat, lon) in [("drawn", drawn[end]), ("snapped", snapped[end])]:
                split = street_layer.findSplit(float(lat), float(lon), SPLIT_RADIUS_M, StreetMode.WALK)
                lines.append(f"    {end} {label}: edge {int(split.edge)}, d0 {int(split.distance0_mm)} mm "
                             f"({int(split.distance0_mm) // MM_PER_M} m), d1 {int(split.distance1_mm)} mm "
                             f"({int(split.distance1_mm) // MM_PER_M} m), off-street {int(split.distanceToEdge_mm)} mm")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_why_{release}.txt").write_text(text + "\n", encoding="utf-8", newline="\n")


# --- full training run -----------------------------------------------------------------------------
def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def training_pairs():
    pairs_df = pd.read_csv(newest(RANGE_RESULTS_GLOB))
    return pairs_df[pairs_df.is_scored.astype(bool)]


def route_train(train_variant, release):
    """Full training routing for one variant (docstring); appends a row per pair, resumes from the newest table."""
    assert train_variant in TRAIN_VARIANTS and release in STUB_BUILDS
    variant, points = TRAIN_VARIANTS[train_variant]
    pairs_df = training_pairs()
    pairs_df = pairs_df[pairs_df.release.astype(str) == release]
    saved = newest(f"{NAME}_2*_trainroutes_{train_variant}_{release}.csv")
    table_path = saved if saved is not None else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_trainroutes_{train_variant}_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"{train_variant} {release}: {len(pairs_df)} pairs, {len(done)} done, {len(todo_df)} to route -> {table_path.name}",
          flush=True)
    ttm, _ = open_network(jar_path(variant), release)
    dest_of, origin_of = split_lookups(release)
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        drawn_origin, drawn_dest = (pair.origin_lat, pair.origin_lon), (pair.dest_lat, pair.dest_lon)
        origin, destination = ((origin_of[drawn_origin], dest_of[drawn_dest]) if points == "snap"
                               else (drawn_origin, drawn_dest))
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
    for train_variant in TRAIN_VARIANTS:
        paths = [newest(f"{NAME}_2*_trainroutes_{train_variant}_{release}.csv") for release in STUB_BUILDS]
        assert all(paths), f"route_train {train_variant} on both releases first"
        routes[train_variant] = pd.concat([pd.read_csv(p) for p in paths]).set_index("draw_no").sort_index()
        assert list(routes[train_variant].index) == list(pairs_df.index), f"{train_variant}: routed pairs != training pairs"
    n = len(pairs_df)
    lines = [f"{NAME} {run_date()} score_train: {n} training pairs ({pairs_df.set_name.value_counts().to_dict()}), "
             f"speed {SPEED_KMH} km/h, v2 network"]

    off_f1 = {}
    for train_variant, key in TRAIN_VARIANTS.items():
        saved = routed(*key)[CALLS]
        off_f1[train_variant] = int((~equal(routes[train_variant].loc[saved.index, CALLS], saved)).sum())
    is_f1 = sum(off_f1.values()) == 0
    lines.append(f"(F1) the 100 pairs routed by `route` reproduce exactly: {'PASS' if is_f1 else 'FAIL'} ({off_f1} values off)")
    if not is_f1:
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
    labels = {"p3snap": "p3snap (P3 jar, snapped points, v2)", "p2orig": "p2orig (P2 jar, drawn points, v2)"}
    models = {labels[v]: (rounded_min(s), s) for v, s in model_s.items()}
    p3_saved = pd.read_csv(P3_TRAIN_SCORED_PATH).set_index("draw_no").reindex(pairs_df.index)
    context = {"context: P3's saved full run (stub network, snapped)": (p3_saved.p3_min.to_numpy(dtype=float), None)}

    readings = {}
    base_hard = None
    for label, (minutes, seconds) in {**models, **context}.items():
        text, hard, total, gain = model_lines(label, minutes, seconds, df, google_s, is_random, base_hard)
        lines += text
        readings[label] = (total, gain)
        if base_hard is None:
            base_hard = hard

    p3_s, p2_s = model_s["p3snap"], model_s["p2orig"]
    p3_min, p2_min = models[labels["p3snap"]][0], models[labels["p2orig"]][0]
    both_finite = np.isfinite(p3_s) & np.isfinite(p2_s)
    gap_s = np.abs(p2_s - p3_s)[both_finite]
    is_p3_transit = routes["p3snap"].transit.fillna(np.inf).to_numpy() < routes["p3snap"].walk.fillna(np.inf).to_numpy()
    is_p2_transit = routes["p2orig"].transit.fillna(np.inf).to_numpy() < routes["p2orig"].walk.fillna(np.inf).to_numpy()
    signed = (p2_s - p3_s)[both_finite]
    lines += ["", "p2orig vs p3snap (equivalence, reported):",
              f"  seconds differ on {int((gap_s > 0).sum())} of {int(both_finite.sum())} pairs ("
              + ", ".join(f"{lo}-{hi} s: {int(((gap_s >= lo) & (gap_s <= hi)).sum())}" for lo, hi in DIFF_BINS_S)
              + f"); finite in one only: {int((np.isfinite(p3_s) != np.isfinite(p2_s)).sum())}",
              f"  p2 - p3 (s) where they differ: median {np.median(signed[signed != 0]) if (signed != 0).any() else 0:+.0f}, "
              f"earlier {int((signed < 0).sum())}, later {int((signed > 0).sum())}",
              f"  minutes changed on {int((p2_min != p3_min).sum())} pairs; change (min) "
              + str(pd.Series(p2_min - p3_min)[np.isfinite(p2_min - p3_min)].value_counts().sort_index().to_dict()),
              f"  band calls changed {int((band_of(p2_min) != band_of(p3_min)).sum())}",
              f"  winner flips: transit -> walk {int((is_p3_transit & ~is_p2_transit).sum())}, walk -> transit "
              f"{int((~is_p3_transit & is_p2_transit).sum())}",
              f"  p3snap (v2) vs P3's saved full run (stub network): minutes differ on "
              f"{int((p3_min != context[next(iter(context))][0]).sum())} pairs"]
    base_total = readings[labels["p3snap"]][0]
    total, gain = readings[labels["p2orig"]]
    reading = ("IMPROVES" if total < base_total and gain <= SNAP_TOLERANCE_MISSES
               else "WORSENS" if total > base_total else "MIXED")
    lines += ["", f"READING (run 3's rule): p2orig hard misses {total} vs p3snap {base_total}, largest gain in one test "
              f"{gain:+d} -> {reading}", f"  (context: P3's saved full run {readings[next(iter(context))][0]})"]
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_train_score.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    pd.DataFrame({"draw_no": pairs_df.index, "set_name": df.set_name, "release": df.release, "boardings": df.boardings,
                  "google_s": google_s, "google_min": df.google_min, "p3snap_s": p3_s, "p2orig_s": p2_s,
                  "p3snap_min": p3_min, "p2orig_min": p2_min}).to_csv(
        DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_train_scored.csv", index=False)


if __name__ == "__main__":
    {"build": build, "route": route, "score": score, "why": why, "route_train": route_train,
     "score_train": score_train}[sys.argv[1]](*sys.argv[2:])
