"""R5 patch P7 (TRN-16 register; named p5 in this file's tables and variant keys (jars renamed p7_in_seat 2026-10-23), P5 being the 64th's transfer penalty): GTFS in-seat continuations (transfer_type 4) ridden as one ride, for the frozen model's
exposure to treating them as transfers.

Claim under test (concepts/transit.md TRN-16 register, Limitations; 77th session, user): the frozen model (R5 7.5.1 + P1
+ P3 + P2, transit_holdout_score.py's freeze record) treats PTV's in-seat continuations as alight-and-reboard. R5's
GtfsTransferLoader skips every transfer_type > 3 ("In-seat transfer information may be 'supported', but not consumed")
and with the default OSM_ONLY transfer config never reads transfers.txt at all. PTV's train feed publishes only type 4,
trip to trip at the from-trip's last stop (Flinders Street, Town Hall; 1,169 of 2,914 weekday train trips continue, 2026-10-28,
release 20261018; ~30% turnbacks, ~70% cross-city through-running). Under P3 a reboard waits 200 s, so with a 1-3 min
dwell the rider cannot catch their own train. Not a pipeline claim: the frozen model stays frozen (user, 77th); this
measures the exposure, for a Limitations line. If ever adopted, RCH-26's oracle must treat continuations as one ride
too, or it stops being generous.

Patch 5 sits on the frozen jar (every jar here is the frozen jar with three classes replaced):
  GtfsTransferLoader  keeps type-4 trip-to-trip rows (scoped trip ids, from -> to) in TransitLayer, before the transfer
      config's early return; nothing else read or changed.
  TransitLayer        one serialized field (the map) and one lazily built, transient index (from-trip schedule -> pattern
      and trip index of its continuation).
  FastRaptorWorker    (from P3's patched source) after scanning a scheduled pattern, if on a trip at the pattern's last stop
      and the trip continues: alight along the continuation's stops in the same round, with the first trip's boarding
      stop, board time and wait (no board wait, no extra ride), up to IN_SEAT_MAX_HOPS continuations. The continuation
      must start at that stop, run on the date and not depart before the trip arrives. Times only: the path pointer
      names the continuation's pattern with the first trip's boarding stop; TravelTimeMatrix reconstructs no paths.
Variants: recompiled (the three classes from unchanged sources: upstream TransitLayer and GtfsTransferLoader, P3's
FastRaptorWorker), off (patched, IN_SEAT false), p5 (patched, IN_SEAT true). off and p5 load the same network (the map
built in both); they differ in the one constant.

Network: r5py caches built networks by input digest, not by jar, so the frozen model's cache would be loaded without the
new field. Patched runs point r5py's cache (LOCALAPPDATA) at CACHE_ROOT below, so the network is built fresh there; the
frozen cache is untouched. (78th: CACHE_ROOT moved to a new folder `_b`; the first one holds the mapdb of the network
build the user stopped in the 77th, which MapDB may not reopen cleanly. Kept, S1.)

Steps (modes; one JVM per process):
  Source alignment (found by B1's first run, 77th): the shipped r5py jar's TransitLayer initialises saveShapes to true,
      the 7.5.1 source to false (r5py's build sets it); every variant's TransitLayer source is aligned to the jar.
  build  B1: recompiled vs the frozen jar's classes (the three and their inner classes), javap -c -p identical, else
      stop. B2: off / p5 vs the jar, differing lines with pool indices masked, printed (expected: the loader block, the
      TransitLayer field and index method, the worker's call site, constants and method; nothing else).
  route <variant> <release>  every scored pair of the release's sets (20261009: train, test; 20261016: second, topup,
      test_ext, holdout), each on its own date, as transit_holdout_score.route: drawn points, 4.143 km/h, 1-min window,
      p49, max 90; transit call only (walk is not touched by RAPTOR; the frozen walk is reused). N1 printed at load: map
      size and resolved continuations. Rows appended per pair; a rerun resumes.
  score  Frozen = transit_holdout_score's routes (test, test_ext, holdout) and transit_r5_patch_connector's p2orig
      training routes (train, second, topup). Rules (Claude's, written before any result):
      (T1) off transit = frozen transit on every pair (NaN = NaN). Any difference fails; nothing else is read.
      (T2) p5 transit <= off transit on every pair (NaN only where off is NaN or both). A violation fails.
      Two parts, report only, no verdict (user's design, 77th):
      (R1) Overall, as the other model comparisons: TRN-13 / TRN-15's checks (copied from transit_holdout_score:
          zones 7-13 / 17-23 with floor, noise bar and balance; hard misses lost / false at cuts 10 / 20; count ratios;
          error to the range) for frozen and p5 side by side, on training (fitted), old test, holdout and all pooled;
          pairs whose minute changes and band calls that flip.
      (R2) The changed trips: pairs whose pair time min(transit, walk) falls with p5; gain in minutes and as a share
          of the frozen pair time ((frozen - p5) / frozen), by the frozen pair minute (<= 10, 11-20, 21-30, > 30) and
          in the zones 7-13 / 17-23; model - Google default before / after; Google default's vehicles and boardings.

Predictions (written before any result).
  Claude's: B1 passes; B2 shows only the listed sites. N1: map = PTV's type-4 rows of the release, nearly all resolved.
    T1 exact, T2 holds. p5 faster on 1-3% of pairs (train-involved, crossing Flinders Street or the Metro Tunnel),
    typically by a headway (3-10 min, the next train); band flips 0.1-0.3% of pairs; on changed pairs the error to
    Google's default moves toward 0 (frozen late there). Gain roughly a fixed number of minutes, so its share falls
    with trip length: ~30% of the time near 10 min, ~15% near 20.
  User's: R1 as Claude's (small overall effect). R2: more dramatic on the short side, since agents either ate the 200 s
    or took another, slower path: changed trips near 10 min about 25% faster, near 20 min about 7% (read as the median
    share in the zones 7-13 and 17-23).

Conclusion (78th, 2026-10-22; facts, routed in a fresh cache `_b`): N1: 15,397 continuations (release 20261009) and
14,991 (20261016) in the network, all resolved to running trips. T1 PASS (off = frozen on 12,696 of 12,696 pairs,
NaN = NaN), T2 PASS (0 violations). p5 faster on 177 pairs (1.39%; per set 1.3-1.5%, topup 0); pair minute changes
on 169; band calls at cuts 10 / 20 flip on 0 pairs. (R1) every zone, hard-miss, ratio check unchanged between frozen
and p5 on every part (z2 noise bar on training moves by 0.01); verdicts as frozen (training / holdout hard lost 20 FAIL,
pooled z1 balance FAIL, both pre-existing). (R2) no changed pair has a frozen pair time under 21 min (min 25, median
44): 21-30 n 8, gain median 2.5 min, 8.5% of frozen time; > 30 n 169, 4.4 min, 9.9%. Against Google's default on the
177: frozen median +1.0 / mean +1.50 / MAE 4.56, p5 -1.0 / -3.56 / 4.04. Split by Google's mode: train-involved (111)
frozen +4.0 median -> p5 0.0; tram (59) frozen -3.0 -> p5 -7.0 (the model already beat Google's default choice there).
Both predictions (gain ~25-30% near 10 min) are wrong on the short side. Claude's reading (unchecked): continuations
sit at Flinders Street / Town Hall, and a trip to the subject's area that rides through one is already long.

Inputs (read only): the frozen jar, `inputs/r5py/` source, P3's patched FastRaptorWorker source, v2 networks and feeds,
the scored pair sets and Google route tables, saved frozen routes. Writes jars to outputs/r5_patches/, a fresh r5py
cache under CACHE_ROOT and tables to diagnostics/diagnostic_data/. Self-contained (CLAUDE.md D1). No paid API calls.
Usage: `python transit_r5_patch_in_seat.py build`, `... route <off|p5> <20261009|20261016>`, `... route_all`, `... score`.
"""
import datetime
import difflib
import hashlib
import os
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
NAME = "transit_r5_patch_in_seat"
PATCH_DIR = PROJECT_ROOT / "outputs" / "r5_patches"
JDK_BIN_DIR = Path(r"C:\Program Files\Java\jdk-21.0.12\bin")
R5_SOURCE_DIR = PROJECT_ROOT / "inputs" / "r5py" / "r5-7.5.1" / "src" / "main" / "java"
P3_SOURCE_DIR = PATCH_DIR / "transit_r5_patch_board_wait_p3" / "src"
RECORD_NAME = "transit_r5_patch_connector"
FROZEN_JAR_PATH = PATCH_DIR / f"r5-v7.5.1-r5py-all_{RECORD_NAME}_p2.jar"
FROZEN_JAR_SHA256 = "62a8f6c1afa2e0a0c86860e336da499f9344e46e6c6d259d9c4824d129e68eb3"
CACHE_ROOT = DIAGNOSTIC_DATA_DIR / f"{NAME}_r5py_cache_b"     # r5py's cache for patched runs (LOCALAPPDATA); _b: the
                                                              # first folder holds a half-built mapdb (run stopped, 77th)
HOLDOUT_NAME = "transit_holdout_score"
V2_NAME = "transit_pathway_network_v2"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
RESERVE_PATH = SUBJECT_DIR / f"transit_pairs_reserve_{FILE_TAG}.csv"
TOPUP_PATH = SUBJECT_DIR / f"transit_pairs_topup_{FILE_TAG}.csv"
TOPUP_SELECTION_PATH = SUBJECT_DIR / f"transit_topup_selection_{FILE_TAG}.csv"
TEST_EXT_PATH = SUBJECT_DIR / f"transit_pairs_test_ext_{FILE_TAG}.csv"
HOLDOUT_PATH = SUBJECT_DIR / f"transit_pairs_holdout_{FILE_TAG}.csv"
HOLDOUT_ANSWERS_PATH = SUBJECT_DIR / f"transit_google_holdout_20261016_{FILE_TAG}.csv"
ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                "test": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv",
                "test_ext": SUBJECT_DIR / f"transit_google_test_ext_20261016_{FILE_TAG}.routes.csv",
                "holdout": SUBJECT_DIR / f"transit_google_holdout_20261016_{FILE_TAG}.routes.csv"}

# --- patch -----------------------------------------------------------------------------------------
WORKER_CLASS = "com.conveyal.r5.profile.FastRaptorWorker"
LAYER_CLASS = "com.conveyal.r5.transit.TransitLayer"
LOADER_CLASS = "com.conveyal.r5.transit.GtfsTransferLoader"
PATCHED_CLASSES = [WORKER_CLASS, LAYER_CLASS, LOADER_CLASS]
GUARD_CLASSES = PATCHED_CLASSES + ["com.conveyal.r5.streets.StreetRouter", "com.conveyal.r5.streets.LinkedPointSet",
                                   "com.conveyal.r5.analyst.TravelTimeReducer"]
VARIANT_IN_SEAT = {"off": False, "p5": True}
VARIANTS = ["recompiled"] + list(VARIANT_IN_SEAT)
IN_SEAT_MAX_HOPS = 4                           # continuations followed from one boarding (A -> B -> ... )
IN_SEAT_TRANSFER_TYPE = 4                      # GTFS transfers.txt: in-seat transfer
TAG = "// PLATICA TRN-16 P5"
SITES = {   # class -> (old text, new text) pairs, each old text found exactly once
    WORKER_CLASS: [
        ("                        boardStop = stop;\n                    }\n                }\n            }\n        }\n    }\n",
         "                        boardStop = stop;\n                    }\n                }\n            }\n"
         f"            if (IN_SEAT && onTrip != NONE) rideOnInSeat(outputState, pattern, schedule, boardStop, boardTime, waitTime); {TAG}\n"
         "        }\n    }\n")],
    LAYER_CLASS: [
        ("    public TIntObjectMap<TIntList> gtfsTransfers = new TIntObjectHashMap<>();\n",
         "    public TIntObjectMap<TIntList> gtfsTransfers = new TIntObjectHashMap<>();\n" + """
    TAG: GTFS in-seat continuations (transfer_type 4, trip to trip), scoped trip ids, from -> to.
    public Map<String, String> inSeatContinuations = new HashMap<>();

    TAG: from-trip schedule -> {pattern index, trip index} of its continuation; built on first use, not serialized.
    private transient Map<TripSchedule, int[]> inSeatNext;

    public synchronized Map<TripSchedule, int[]> inSeatNext () {
        if (inSeatNext == null) {
            Map<String, int[]> whereForTripId = new HashMap<>();
            Map<String, TripSchedule> scheduleForTripId = new HashMap<>();
            for (int p = 0; p < tripPatterns.size(); p++) {
                List<TripSchedule> schedules = tripPatterns.get(p).tripSchedules;
                for (int t = 0; t < schedules.size(); t++) {
                    whereForTripId.put(schedules.get(t).tripId, new int[] {p, t});
                    scheduleForTripId.put(schedules.get(t).tripId, schedules.get(t));
                }
            }
            Map<TripSchedule, int[]> next = new java.util.IdentityHashMap<>();
            for (Map.Entry<String, String> entry : inSeatContinuations.entrySet()) {
                TripSchedule from = scheduleForTripId.get(entry.getKey());
                int[] where = whereForTripId.get(entry.getValue());
                if (from != null && where != null) next.put(from, where);
            }
            inSeatNext = next;
        }
        return inSeatNext;
    }
""".replace("TAG", TAG))],
    LOADER_CLASS: [
        ("        if (transferConfig == OSM_ONLY) return;\n",
         f"        {TAG}: keep in-seat continuations (trip to trip) before the transfer config's early return.\n"
         "        if (feed.transfers != null) {\n"
         "            int nInSeat = 0;\n"
         "            for (Transfer transfer : feed.transfers.values()) {\n"
         f"                if (transfer.transfer_type == {IN_SEAT_TRANSFER_TYPE} && !isNullOrEmpty(transfer.from_trip_id)"
         " && !isNullOrEmpty(transfer.to_trip_id)) {\n"
         "                    transit.inSeatContinuations.put(String.join(\":\", feed.feedId, transfer.from_trip_id),\n"
         "                                                    String.join(\":\", feed.feedId, transfer.to_trip_id));\n"
         "                    nInSeat += 1;\n"
         "                }\n"
         "            }\n"
         "            if (nInSeat > 0) LOG.info(\"GTFS {} in-seat continuations kept: {}\", feed.feedId, nInSeat);\n"
         "        }\n"
         "        if (transferConfig == OSM_ONLY) return;\n")]}
SOURCE_ALIGNMENT = {   # class -> (source text, the shipped r5py jar's) pairs, applied to every variant, recompiled too
    LAYER_CLASS: [("    public boolean saveShapes = false;\n", "    public boolean saveShapes = true;\n")]}
CLASS_END = "\n}\n"
WORKER_METHOD = """
    TAG: GTFS in-seat continuations (transfer_type 4). A rider on a trip at its pattern's last stop stays on board as
    // the trip's continuation (and its continuation, up to IN_SEAT_MAX_HOPS): alight times along the continuation's stops
    // in the same round, with the first trip's boarding stop, board time and wait (no board wait, no extra ride). Times
    // only: the path pointer names the continuation's pattern with the first trip's boarding stop.
    private static final boolean IN_SEAT = @IN_SEAT_VALUE@;
    private static final int IN_SEAT_MAX_HOPS = @MAX_HOPS_VALUE@;

    private void rideOnInSeat (RaptorState outputState, TripPattern pattern, TripSchedule schedule, int boardStop,
                               int boardTime, int waitTime) {
        java.util.Map<TripSchedule, int[]> next = transit.inSeatNext();
        for (int hop = 0; hop < IN_SEAT_MAX_HOPS; hop++) {
            int[] where = next.get(schedule);
            if (where == null) return;
            TripPattern nextPattern = transit.tripPatterns.get(where[0]);
            TripSchedule nextSchedule = nextPattern.tripSchedules.get(where[1]);
            int lastStopInPattern = pattern.stops.length - 1;
            if (nextPattern.stops[0] != pattern.stops[lastStopInPattern]
                || !filteredPatterns.runningScheduledPatterns.get(where[0])
                || !servicesActive.get(nextSchedule.serviceCode)
                || nextSchedule.headwaySeconds != null
                || nextSchedule.departures[0] < schedule.arrivals[lastStopInPattern]) {
                return;
            }
            for (int stopInPattern = 1; stopInPattern < nextPattern.stops.length; stopInPattern++) {
                if (nextPattern.dropoffs[stopInPattern] == PickDropType.NONE) continue;
                int alightTime = nextSchedule.arrivals[stopInPattern];
                outputState.setTimeAtStop(nextPattern.stops[stopInPattern], alightTime, where[0], boardStop, waitTime,
                                          alightTime - boardTime, false);
            }
            pattern = nextPattern;
            schedule = nextSchedule;
        }
    }
"""
CONST_POOL_REF = re.compile(r"#\d+(:#\d+)?")
CODE_OFFSET = re.compile(r"^\s*\d+: ")
BRANCH_TARGET = re.compile(r"\b(goto|goto_w|if\w*|jsr)\s+\d+")
SWITCH_TARGET = re.compile(r"^\s*(-?\d+|default): \d+$")

# --- the frozen model (values copied from transit_holdout_score.py) -----------------------------------
R5_MAX_MEMORY = "7G"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
SPEED_KMH = 4.143                              # Q24 (2) median; user 2026-10-21
MAX_TIME_MIN = 90
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
PROGRESS_EVERY = 500
SECONDS_PER_MIN = 60
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]  # TRN-11
# values copied from transit_holdout_score.py (TRN-13 / TRN-15 checks)
TEST_SCORE_NAME = "transit_test_score"
RANGE_NAME = "transit_hard_miss_range"
OLD_TEST_SETS = ["test", "test_ext"]
TOPUP_SET = "topup"                            # not random: zones only, no hard test (TRN-13)
ZONES_MIN = {1: (7, 13), 2: (17, 23)}
CUTS_MIN = {1: 10, 2: 20}
AWAY_RANGES_MIN = [(0, 6), (14, 16), (24, 30)]
GATING_K = 2
WILSON_Z = 1.959964
FLOOR = 0.6
N_SIMULATIONS = 2000
SIMULATION_SEED = 20261018
SIGN_TEST_ALPHA = 0.05
CLOSE_TOLERANCE = 0.10
COUNT_RATIO_RANGE = (0.90, 1.10)
HARD_WINDOW_NEAR_MIN = 3
HARD_WINDOW_FAR_MIN = 10
HARD_MISS_MAX = 0.05
REPORT_ONLY_TESTS = ["lost 10"]
STRATUM_LOW_MAX_TRIPS = 36
STRATUM_HIGH_MIN_TRIPS = 131
TRAM_TYPE = "TRAM"
TRAIN_TYPE = "HEAVY_RAIL"
BOARDING_GROUPS = ["0", "1", "2+"]
BINS_MIN = [("<= 10", 0, 10), ("11-20", 11, 20), ("21-30", 21, 30), ("> 30", 31, np.inf)]   # (R2) frozen pair minute
RELEASE_SETS = {"20261009": ["train", "test"], "20261016": ["second", "topup", "test_ext", "holdout"]}
TRAINING_SETS = ["train", "second", "topup"]
PAIR_COLUMNS = ["draw_no", "origin_lat", "origin_lon", "dest_lat", "dest_lon", "dest_hex", "dep_min_of_day"]


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def check_frozen_jar():
    with open(FROZEN_JAR_PATH, "rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    assert digest == FROZEN_JAR_SHA256, f"{FROZEN_JAR_PATH.name} sha256 {digest} != frozen {FROZEN_JAR_SHA256}"


JAR_LABEL = "p7_in_seat"                       # jars renamed 2026-10-23 (user): patch number + description; was {NAME}_<variant>


def jar_path(variant):
    return PATCH_DIR / f"r5-v7.5.1-r5py-all_{JAR_LABEL}{'' if variant == 'p5' else '_' + variant}.jar"


# --- build (as transit_r5_patch_connector.build) ------------------------------------------------------
def class_file(name):
    return name.replace(".", "/")


def class_names(classes_dir):
    return sorted(p.relative_to(classes_dir).with_suffix("").as_posix().replace("/", ".")
                  for p in classes_dir.rglob("*.class"))


def javap(classpath, names):
    out = subprocess.run([str(JDK_BIN_DIR / "javap"), "-c", "-p", "-cp", str(classpath)] + names,
                         capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def pool_masked(lines):
    """javap lines with constant-pool indices, code offsets and branch / switch targets masked (as P3's B2)."""
    masked = []
    for line in lines:
        line = BRANCH_TARGET.sub(r"\1 L", CODE_OFFSET.sub("", CONST_POOL_REF.sub("#", line)))
        line = SWITCH_TARGET.sub(r"\1: L", line)
        masked.append(" ".join(line.split()))
    return masked


def diff_lines(a, b):
    return [line for line in difflib.unified_diff(a, b, n=0, lineterm="") if not line.startswith(("---", "+++"))]


def source_of(class_name):
    base_dir = P3_SOURCE_DIR if class_name == WORKER_CLASS else R5_SOURCE_DIR
    source = (base_dir / f"{class_file(class_name)}.java").read_text(encoding="utf-8")
    for old, new in SOURCE_ALIGNMENT.get(class_name, []):
        assert source.count(old) == 1, f"{class_name}: alignment site not found exactly once: {old}"
        source = source.replace(old, new)
    return source


def patched_source(source, class_name, is_in_seat):
    for old, new in SITES[class_name]:
        assert source.count(old) == 1, f"{class_name}: site not found exactly once: {old[:80]}"
        source = source.replace(old, new)
    if class_name == WORKER_CLASS:
        assert source.endswith(CLASS_END)
        method = (WORKER_METHOD.replace("TAG", TAG).replace("@IN_SEAT_VALUE@", str(is_in_seat).lower())
                  .replace("@MAX_HOPS_VALUE@", str(IN_SEAT_MAX_HOPS)))
        source = source[:-len(CLASS_END)] + "\n" + method + CLASS_END
    return source


def build():
    check_frozen_jar()
    sources = {c: source_of(c) for c in PATCHED_CLASSES}
    lines = [f"{NAME} {run_date()} build (base: {FROZEN_JAR_PATH.name})"]
    texts = {"recompiled": sources}
    texts.update({v: {c: patched_source(s, c, flag) for c, s in sources.items()} for v, flag in VARIANT_IN_SEAT.items()})
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
        subprocess.run([str(JDK_BIN_DIR / "javac"), "--release", "21", "-proc:none", "-nowarn", "-cp", str(FROZEN_JAR_PATH),
                        "-d", str(classes_dir)] + src_paths, check=True)
        names = class_names(classes_dir)
        assert all(any(n == c or n.startswith(c + "$") for c in PATCHED_CLASSES) for n in names), f"unexpected classes: {names}"
        base_javap = javap(FROZEN_JAR_PATH, names)
        diff = diff_lines(base_javap, javap(classes_dir, names))
        jar = jar_path(variant)
        shutil.copyfile(FROZEN_JAR_PATH, jar)
        class_files = [p.relative_to(classes_dir).as_posix() for p in classes_dir.rglob("*.class")]
        subprocess.run([str(JDK_BIN_DIR / "jar"), "uf", str(jar)] + sum([["-C", str(classes_dir), f] for f in class_files], []),
                       check=True)
        assert diff_lines(base_javap, javap(jar, names)) == diff, f"{jar.name}: classes in the jar differ from the compiled classes"
        n_diff = sum(line[0] in "+-" for line in diff)
        if variant == "recompiled":
            lines.append(f"(B1) recompiled vs the frozen jar's classes ({len(names)}: {names}), javap -c -p: "
                         f"{'PASS' if not diff else 'FAIL'} ({n_diff} differing lines)")
            is_ok &= not diff
        else:
            masked = diff_lines(pool_masked(base_javap), pool_masked(javap(classes_dir, names)))
            lines.append(f"(B2) {variant} (IN_SEAT {VARIANT_IN_SEAT[variant]}) vs the frozen jar's classes, javap -c -p "
                         f"differing lines (constant-pool indices masked; {n_diff} lines unmasked):")
            lines += [f"    {line}" for line in masked]
        lines.append(f"    jar {jar.relative_to(PROJECT_ROOT)}")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_build.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    assert is_ok, "B1 failed: stop"


# --- pairs (copied from transit_holdout_score.py) -----------------------------------------------------
def pairs_of_set(set_name):
    if set_name in ("train", "test"):
        split_df = pd.read_csv(SPLIT_PATH, usecols=["draw_no", "half"])
        pairs_df = pd.read_csv(PAIRS_PATH, usecols=PAIR_COLUMNS)
        return pairs_df[pairs_df.draw_no.isin(split_df.draw_no[split_df.half == set_name])]
    if set_name == "second":
        return pd.read_csv(RESERVE_PATH, usecols=PAIR_COLUMNS)
    if set_name == "test_ext":
        return pd.read_csv(TEST_EXT_PATH, usecols=PAIR_COLUMNS)
    if set_name == "holdout":
        return pd.read_csv(HOLDOUT_PATH, usecols=PAIR_COLUMNS)
    topup_df = pd.read_csv(TOPUP_PATH, usecols=PAIR_COLUMNS)
    return topup_df[topup_df.draw_no.isin(pd.read_csv(TOPUP_SELECTION_PATH).draw_no)]


def own_dates(set_name, release):
    if set_name == "holdout":
        answers_df = pd.read_csv(HOLDOUT_ANSWERS_PATH, usecols=["draw_no", "departure_local"])
        return pd.DataFrame({"draw_no": answers_df.draw_no,
                             "own_date": pd.to_datetime(answers_df.departure_local.str[:10]).dt.date})
    kind = "owndate" if set_name in TRAINING_SETS else "test"                      # v2's own-date runs: training / test
    routes_df = pd.read_csv(newest(f"{V2_NAME}_2*_routes_{kind}_{release}.csv"))
    routes_df = routes_df[routes_df.set_name == set_name]
    return pd.DataFrame({"draw_no": routes_df.draw_no, "own_date": pd.to_datetime(routes_df.own_date).dt.date})


# --- route (as transit_holdout_score.route, transit call only) ----------------------------------------
def network_paths(release):
    feed_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{release}"
    pbf_path = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{release}.osm.pbf"
    gtfs = [feed_dir / (f"{name}_{V2_NAME}_{release}_moved.zip" if name == TRAIN_FEED else f"{name}_{V2_NAME}_{release}.zip")
            for name in FEED_NAMES]
    return pbf_path, gtfs


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (memory r5py-working-copy-cache)."""
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


def open_network(variant, release):
    """Start the JVM on the variant's jar (guarded), r5py's cache under CACHE_ROOT, load the release's v2 network; N1."""
    jar = jar_path(variant)
    assert jar.exists(), "build first"
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALAPPDATA"] = str(CACHE_ROOT)                                    # before r5py's Config is read
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(jar)]          # r5py reads these at import
    import geopandas as gpd
    import jpype
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    from r5py.util.config import Config
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    assert Path(Config().CACHE_DIR).resolve().is_relative_to(CACHE_ROOT.resolve()), f"r5py cache at {Config().CACHE_DIR}"
    for name in GUARD_CLASSES:
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == jar.resolve(), f"{name} loaded from {location}"
    print(f"{', '.join(c.rsplit('.', 1)[1] for c in GUARD_CLASSES)} from {jar.name}; r5py cache {Config().CACHE_DIR}", flush=True)
    pbf_path, gtfs = network_paths(release)
    assert pbf_path.exists() and all(p.exists() for p in gtfs), "transit_pathway_network_v2 build / feeds first"
    check_working_copies([pbf_path] + gtfs)
    network = TransportNetwork(pbf_path, gtfs)
    transit_layer = network._transport_network.transitLayer
    print(f"(N1) in-seat continuations in the network: {transit_layer.inSeatContinuations.size()}, "
          f"resolved to running trips: {transit_layer.inSeatNext().size()}", flush=True)

    def ttm(origin, destination, departure):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([origin[1]], [origin[0]]))
        targets = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326",
                                   geometry=gpd.points_from_xy([destination[1]], [destination[0]]))
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=targets, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=datetime.timedelta(minutes=MAX_TIME_MIN),
            speed_walking=SPEED_KMH))
        return float(matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0])

    return network, ttm


def route(variant, release):
    """Route every pair of the release's sets with the variant's jar, each on its own date; appends, resumes."""
    assert variant in VARIANT_IN_SEAT and release in RELEASE_SETS
    frozen_keys = frozen_routes()[["set_name", "draw_no"]]                         # the pairs the frozen tables hold
    pairs_df = pd.concat([pairs_of_set(s).merge(own_dates(s, release), on="draw_no", how="left", validate="one_to_one")
                          .assign(set_name=s) for s in RELEASE_SETS[release]], ignore_index=True)
    pairs_df = pairs_df.merge(frozen_keys, on=["set_name", "draw_no"], how="inner", validate="one_to_one")
    assert pairs_df.own_date.notna().all(), "pairs without a departure date"
    saved = newest(f"{NAME}_2*_routes_{variant}_{release}.csv")
    table_path = saved if saved is not None else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_routes_{variant}_{release}.csv"
    done = (set(zip(*pd.read_csv(table_path, usecols=["set_name", "draw_no"]).to_dict("list").values()))
            if table_path.exists() else set())
    todo_df = pairs_df[[(s, d) not in done for s, d in zip(pairs_df.set_name, pairs_df.draw_no)]]
    print(f"{variant} {release}: {len(pairs_df)} pairs, {len(done)} done, {len(todo_df)} to route -> {table_path.name}",
          flush=True)
    if todo_df.empty:
        return
    network, ttm = open_network(variant, release)
    for own_date in sorted(todo_df.own_date.unique()):
        assert network.transit_layer.covers(own_date), f"release {release} does not cover {own_date}"
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        departure = (datetime.datetime.combine(pair.own_date, datetime.time())
                     + datetime.timedelta(minutes=int(pair.dep_min_of_day)))
        row = {"set_name": pair.set_name, "draw_no": pair.draw_no, "release": release, "own_date": pair.own_date,
               "transit": ttm((pair.origin_lat, pair.origin_lon), (pair.dest_lat, pair.dest_lon), departure)}
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % PROGRESS_EVERY == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


def route_all():
    """off then p5, each release in its own process (one JVM per process); stops on a failure."""
    for variant in VARIANT_IN_SEAT:
        for release in RELEASE_SETS:
            print(f"== {variant} {release}", flush=True)
            subprocess.run([sys.executable, "-u", str(Path(__file__).resolve()), "route", variant, release], check=True)


# --- score: checks (copied from transit_holdout_score.py) -------------------------------------------
def frozen_routes():
    """The frozen model's saved seconds per (set_name, draw_no): transit and walk."""
    frames = []
    for release, set_names in RELEASE_SETS.items():
        record_df = pd.read_csv(newest(f"{RECORD_NAME}_2*_trainroutes_p2orig_{release}.csv"))
        for set_name in set_names:
            if set_name in TRAINING_SETS:
                draw_nos = set(pairs_of_set(set_name).draw_no)
                frames.append(record_df[record_df.draw_no.isin(draw_nos)][["draw_no", "transit", "walk"]].assign(set_name=set_name))
            else:
                path = newest(f"{HOLDOUT_NAME}_2*_routes_{set_name}.csv")
                assert path is not None, f"{HOLDOUT_NAME} route {set_name} first"
                frames.append(pd.read_csv(path)[["draw_no", "set_name", "transit", "walk"]])
    return pd.concat(frames, ignore_index=True)


def google_table(set_name, draw_nos):
    """Default minute, scope, range low (k = 2), default's wait / walk-only / vehicles / boardings."""
    routes_df = pd.read_csv(ROUTES_PATHS[set_name])
    routes_df = routes_df[routes_df.draw_no.isin(draw_nos)].sort_values(["draw_no", "route_ix"])
    default_df = routes_df[routes_df.is_default].drop_duplicates("draw_no").set_index("draw_no")
    out_df = pd.DataFrame({"default_min": np.round(default_df.arrival_from_request_s / SECONDS_PER_MIN),
                           "default_s": default_df.arrival_from_request_s,
                           "is_scored": default_df.route_scope.isin(GOOGLE_SCOPES) & default_df.arrival_from_request_s.notna(),
                           "default_wait_s": default_df.leave_wait_s, "default_walk_only": default_df.is_walk_only,
                           "default_vehicles": default_df.vehicle_types.fillna(""),
                           "default_steps": default_df.n_transit_steps, "default_lines": default_df.lines.fillna("")})
    usable_df = routes_df[routes_df.route_scope.isin(GOOGLE_SCOPES) & routes_df.arrival_from_request_s.notna()].copy()
    usable_df["minute"] = np.round(usable_df.arrival_from_request_s / SECONDS_PER_MIN)
    usable_df["rank"] = usable_df.groupby("draw_no").cumcount() + 1
    low = usable_df[usable_df["rank"] <= GATING_K].groupby("draw_no").minute.min().reindex(out_df.index)
    out_df[f"low_{GATING_K}"] = np.fmin(low.to_numpy(), out_df.default_min.to_numpy())
    return out_df.reset_index()


def rounded_min(seconds):
    """Seconds to the nearest whole minute, half up (SCR-10); NaN (over max_time) -> inf."""
    return np.floor(np.nan_to_num(np.asarray(seconds, dtype=float), nan=np.inf, posinf=np.inf) / SECONDS_PER_MIN + 0.5)


def mode_group(walk_only, vehicles):
    if walk_only:
        return "walk"
    kinds = set(vehicles.split("|"))
    if TRAIN_TYPE in kinds:
        return "train-involved"
    if kinds == {TRAM_TYPE}:
        return "tram"
    if TRAM_TYPE in kinds:
        return "tram+bus"
    return "bus"


def with_strata(df):
    frames = [pd.read_csv(newest(f"{RANGE_NAME}_2*_service_owndate.csv"), usecols=["set_name", "draw_no", "origin_trips"]),
              pd.read_csv(newest(f"{TEST_SCORE_NAME}_2*_service_test.csv"), usecols=["set_name", "draw_no", "origin_trips"]),
              pd.read_csv(newest(f"{HOLDOUT_NAME}_2*_service_holdout.csv"), usecols=["set_name", "draw_no", "origin_trips"])]
    df = df.merge(pd.concat(frames, ignore_index=True), on=["set_name", "draw_no"], how="left", validate="one_to_one")
    assert df.origin_trips.notna().all(), "pairs without a service count"
    df["stratum"] = np.select([df.origin_trips <= STRATUM_LOW_MAX_TRIPS, df.origin_trips >= STRATUM_HIGH_MIN_TRIPS],
                              ["low", "high"], "mid")
    return df


def with_model(df, transit_column):
    """model_s / model_min = min(transit, walk) for one variant's transit seconds."""
    transit_s, walk_s = df[transit_column].fillna(np.inf).to_numpy(), df.walk.fillna(np.inf).to_numpy()
    df = df.copy()
    df["model_s"] = np.fmin(transit_s, walk_s)
    df["model_min"] = rounded_min(df.model_s)
    df["is_r5_walk"] = walk_s <= transit_s
    return df


def wilson(successes, n):
    if n == 0:
        return np.nan, np.nan
    share = successes / n
    centre = (share + WILSON_Z ** 2 / (2 * n)) / (1 + WILSON_Z ** 2 / n)
    half_width = WILSON_Z * np.sqrt(share * (1 - share) / n + WILSON_Z ** 2 / (4 * n ** 2)) / (1 + WILSON_Z ** 2 / n)
    return centre - half_width, centre + half_width


def is_away(google_min):
    return np.logical_or.reduce([(google_min >= low) & (google_min <= high) for low, high in AWAY_RANGES_MIN])


def google_side(low, high, is_r5_below, cut_min):
    is_low_below, is_high_below = low <= cut_min, high <= cut_min
    return np.where(is_low_below != is_high_below, is_r5_below, is_high_below)


def distance_to_range(r5_min, low, high):
    return np.where(r5_min < low, r5_min - low, np.where(r5_min > high, r5_min - high, 0.0))


def zone_checks(zone_df, cut_min, centred_errors, rng):
    from scipy.stats import binomtest
    low, high, r5 = zone_df[f"low_{GATING_K}"].to_numpy(), zone_df.default_min.to_numpy(), zone_df.model_min.to_numpy()
    is_r5_below = r5 <= cut_min
    is_google_below = google_side(low, high, is_r5_below, cut_min)
    both = int((is_google_below & is_r5_below).sum())
    rec_n, prec_n = int(is_google_below.sum()), int(is_r5_below.sum())
    rec, prec = both / rec_n, both / prec_n if prec_n else np.nan
    rec_low, rec_high = wilson(both, rec_n)
    prec_low, prec_high = wilson(both, prec_n)
    sim_recall, sim_precision = [], []
    for _ in range(N_SIMULATIONS):
        sim_r5 = high + rng.choice(centred_errors, size=len(high), replace=True)
        is_sim_below = sim_r5 <= cut_min
        is_sim_google = google_side(low, high, is_sim_below, cut_min)
        sim_both = (is_sim_google & is_sim_below).sum()
        sim_recall.append(sim_both / is_sim_google.sum() if is_sim_google.sum() else np.nan)
        sim_precision.append(sim_both / is_sim_below.sum() if is_sim_below.sum() else np.nan)
    bar_recall, bar_precision = np.nanmedian(sim_recall), np.nanmedian(sim_precision)
    n_early = int((is_r5_below & ~is_google_below).sum())
    n_late = int((~is_r5_below & is_google_below).sum())
    sign_p = binomtest(n_early, n_early + n_late, 0.5).pvalue if n_early + n_late else 1.0
    gap = abs(rec - prec)
    return {"recall": (f"{rec:.3f} ({both}/{rec_n}, {rec_low:.2f}-{rec_high:.2f})", None),
            "precision": (f"{prec:.3f} ({both}/{prec_n}, {prec_low:.2f}-{prec_high:.2f})", None),
            "floor": (f"{min(rec_low, prec_low):.3f}", rec_low > FLOOR and prec_low > FLOOR),
            "noise bar": (f"{rec_high:.2f}/{bar_recall:.2f}, {prec_high:.2f}/{bar_precision:.2f}",
                          rec_high >= bar_recall and prec_high >= bar_precision),
            "balance": (f"{n_early}e/{n_late}l p {sign_p:.3f}, gap {gap:.3f}", sign_p >= SIGN_TEST_ALPHA and gap <= CLOSE_TOLERANCE)}


def hard_windows(df):
    """{test: boolean window mask over df, miss mask}."""
    out = {}
    default = df.default_min.to_numpy()
    for cut_min in CUTS_MIN.values():
        is_r5_below = df.model_min.to_numpy() <= cut_min
        is_google_below = google_side(df[f"low_{GATING_K}"].to_numpy(), default, is_r5_below, cut_min)
        for kind, low_min, high_min in [("lost", cut_min - HARD_WINDOW_FAR_MIN, cut_min - HARD_WINDOW_NEAR_MIN),
                                        ("false", cut_min + HARD_WINDOW_NEAR_MIN, cut_min + HARD_WINDOW_FAR_MIN)]:
            is_window = (default >= low_min) & (default <= high_min)
            out[f"{kind} {cut_min}"] = (is_window, is_window & (is_r5_below != is_google_below))
    return out


def score_set(df, zone_df, error_df):
    """TRN-13 / TRN-15 checks on one set (as transit_holdout_score.score_set, without miss groups or the stop condition)."""
    checks = {}
    is_away_pair = is_away(error_df.default_min.to_numpy()) & np.isfinite(error_df.model_min.to_numpy())
    errors = distance_to_range(error_df.model_min.to_numpy(), error_df[f"low_{GATING_K}"].to_numpy(),
                               error_df.default_min.to_numpy())[is_away_pair]
    rng = np.random.default_rng(SIMULATION_SEED)
    for zone_no, cut_min in CUTS_MIN.items():
        is_zone = (zone_df.default_min >= ZONES_MIN[zone_no][0]) & (zone_df.default_min <= ZONES_MIN[zone_no][1])
        checks.update({f"z{zone_no} {name}": value
                       for name, value in zone_checks(zone_df[is_zone], cut_min, errors - np.median(errors), rng).items()})
    for test, (is_window, is_miss) in hard_windows(df).items():
        k_miss, n = int(is_miss.sum()), int(is_window.sum())
        high = wilson(k_miss, n)[1]
        is_report_only = test in REPORT_ONLY_TESTS
        checks[f"hard {test}"] = (f"{k_miss}/{n}, upper {high:.3f}{' (report-only)' if is_report_only else ''}",
                                  None if is_report_only else high <= HARD_MISS_MAX)
    for cut_min in CUTS_MIN.values():
        n_google = int((df.default_min <= cut_min).sum())
        n_r5 = int((df.model_min.to_numpy() <= cut_min).sum())
        checks[f"ratio <= {cut_min}"] = (f"{n_r5 / n_google:.3f} ({n_r5}/{n_google})",
                                         COUNT_RATIO_RANGE[0] <= n_r5 / n_google <= COUNT_RATIO_RANGE[1])
    finite = np.isfinite(df.model_min.to_numpy())
    signed = (df.model_min - df.default_min).to_numpy()[finite]
    checks["error to range (away)"] = (f"median {np.median(errors):+.1f}, mean {errors.mean():+.2f}, inside "
                                       f"{np.mean(errors == 0):.2f} (n {len(errors)})", None)
    checks["model - default"] = (f"median {np.median(signed):+.1f}, mean {signed.mean():+.2f}, MAE {np.abs(signed).mean():.2f}", None)
    failures = [name for name, (_, is_pass) in checks.items() if is_pass is not None and not is_pass]
    checks["verdict"] = ("PASS" if not failures else "FAIL: " + ", ".join(failures), None)
    return checks


def table_text(table):
    table_df = pd.DataFrame({label: {name: f"{text}{'' if is_pass is None else (' ok' if is_pass else ' FAIL')}"
                                     for name, (text, is_pass) in checks.items()} for label, checks in table.items()})
    with pd.option_context("display.width", 400, "display.max_columns", 12, "display.max_colwidth", 48):
        return table_df, table_df.to_string()


def random_scored(df):
    return df[df.is_scored & (df.set_name != TOPUP_SET)]


def equal(a, b):
    return (a == b) | (a.isna() & b.isna())


# --- score -----------------------------------------------------------------------------------------
def load_table():
    """Per pair: set, Google's table, stratum, frozen / off / p5 transit seconds, frozen walk."""
    variant_dfs = {v: pd.concat([pd.read_csv(newest(f"{NAME}_2*_routes_{v}_{r}.csv")) for r in RELEASE_SETS],
                                ignore_index=True)[["set_name", "draw_no", "transit"]].rename(columns={"transit": v})
                   for v in VARIANT_IN_SEAT}
    table_df = (frozen_routes().rename(columns={"transit": "frozen"})
                .merge(variant_dfs["off"], on=["set_name", "draw_no"], validate="one_to_one")
                .merge(variant_dfs["p5"], on=["set_name", "draw_no"], validate="one_to_one"))
    google_df = pd.concat([google_table(s, set(g.draw_no)).assign(set_name=s) for s, g in table_df.groupby("set_name")],
                          ignore_index=True)
    table_df = table_df.merge(google_df, on=["set_name", "draw_no"], how="left", validate="one_to_one")
    assert table_df.default_min.notna().all(), "pairs without a Google default"
    table_df["is_scored"] = table_df.is_scored.astype(bool)
    table_df["mode_group"] = [mode_group(bool(w), v) for w, v in zip(table_df.default_walk_only, table_df.default_vehicles)]
    table_df["boardings"] = [BOARDING_GROUPS[min(int(x), 2)] if np.isfinite(x) else "?"
                             for x in table_df.default_steps.astype(float)]
    return with_strata(table_df)


def write_score(lines, frames=None):
    text = "\n".join(lines)
    print(text)
    prefix = f"{NAME}_{run_date()}_score"
    (DIAGNOSTIC_DATA_DIR / f"{prefix}.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    for tag, frame in (frames or {}).items():
        frame.to_csv(DIAGNOSTIC_DATA_DIR / f"{prefix}_{tag}.csv", index=False)


def share_line(label, part_df):
    if part_df.empty:
        return f"  {label}: n 0"
    gain_min = part_df.gain_s / SECONDS_PER_MIN
    share = part_df.gain_s / part_df.frozen_s
    return (f"  {label}: n {len(part_df)}; gain min median {gain_min.median():.1f} (IQR {gain_min.quantile(0.25):.1f}-"
            f"{gain_min.quantile(0.75):.1f}, max {gain_min.max():.1f}); share of frozen time median {share.median():.1%} "
            f"(IQR {share.quantile(0.25):.1%}-{share.quantile(0.75):.1%}), mean {share.mean():.1%}")


def score():
    table_df = load_table()
    lines = [f"{NAME} {run_date()} score: {len(table_df)} pairs "
             f"({', '.join(f'{s} {n}' for s, n in table_df.set_name.value_counts().items())}); scored {int(table_df.is_scored.sum())}"]
    t1_off = ~equal(table_df.off, table_df.frozen)
    lines.append(f"(T1) off = frozen transit: {'PASS' if not t1_off.any() else 'FAIL'} ({t1_off.sum()} of {len(table_df)} differ)")
    t2_off = (table_df.p5 > table_df.off) | (table_df.p5.isna() & table_df.off.notna())
    lines.append(f"(T2) p5 <= off transit: {'PASS' if not t2_off.any() else 'FAIL'} ({t2_off.sum()} violations)")
    if t1_off.any() or t2_off.any():
        lines.append(table_df[t1_off | t2_off][["set_name", "draw_no", "frozen", "off", "p5"]].head(20).to_string(index=False))
        write_score(lines)
        raise SystemExit("T1 or T2 failed: the report is not read")
    frozen_df, p5_df = with_model(table_df, "frozen"), with_model(table_df, "p5")

    # (R1) overall, frozen vs p5 side by side
    table = {}
    for label, sets in [("training", TRAINING_SETS), ("old test", OLD_TEST_SETS), ("holdout", ["holdout"]),
                        ("all pooled", TRAINING_SETS + OLD_TEST_SETS + ["holdout"])]:
        for variant, variant_df in [("frozen", frozen_df), ("p5", p5_df)]:
            scored_df = variant_df[variant_df.is_scored & variant_df.set_name.isin(sets)]
            table[f"{label} {variant}"] = score_set(random_scored(scored_df), scored_df, scored_df)
    checks_df, text = table_text(table)
    is_transit_faster = table_df.p5.fillna(np.inf) < table_df.off.fillna(np.inf)
    is_minute_changed = p5_df.model_min != frozen_df.model_min
    lines += ["", "(R1) overall, frozen vs p5 (zones and ratios on all scored pairs, hard misses on random scored; "
              "training is fitted, old test seen, holdout as opened in the 69th):", text, "",
              f"  transit faster with p5 on {is_transit_faster.sum()} of {len(table_df)} pairs ({is_transit_faster.mean():.2%}); "
              f"pair minute changes on {is_minute_changed.sum()} ({is_minute_changed.mean():.2%})"]
    for cut_min in CUTS_MIN.values():
        flips = (frozen_df.model_min <= cut_min) != (p5_df.model_min <= cut_min)
        lines.append(f"  band call at cut {cut_min} flips on {flips.sum()} pairs ({flips.mean():.2%}); "
                     f"scored {int((flips & table_df.is_scored).sum())}")
    for set_name, group in table_df.assign(is_changed=is_minute_changed).groupby("set_name", sort=False):
        lines.append(f"  {set_name}: minute changes {group.is_changed.sum()} of {len(group)} ({group.is_changed.mean():.2%})")

    # (R2) the changed trips
    changed_df = table_df.assign(frozen_s=frozen_df.model_s, p5_s=p5_df.model_s, frozen_min=frozen_df.model_min,
                                 p5_min=p5_df.model_min)[(p5_df.model_s < frozen_df.model_s).to_numpy()].copy()
    changed_df["frozen_s"] = changed_df.frozen_s.clip(upper=MAX_TIME_MIN * SECONDS_PER_MIN)   # over max_time: capped
    changed_df["gain_s"] = changed_df.frozen_s - changed_df.p5_s
    lines += ["", f"(R2) changed trips: pair time falls on {len(changed_df)} pairs; gain by the frozen pair minute:"]
    for label, low_min, high_min in BINS_MIN:
        lines.append(share_line(label, changed_df[(changed_df.frozen_min >= low_min) & (changed_df.frozen_min <= high_min)]))
    lines.append("  in the zones (frozen pair minute):")
    for zone_no, (low_min, high_min) in ZONES_MIN.items():
        lines.append(share_line(f"z{zone_no} {low_min}-{high_min}",
                                changed_df[(changed_df.frozen_min >= low_min) & (changed_df.frozen_min <= high_min)]))
    scored_changed_df = changed_df[changed_df.is_scored]
    if not scored_changed_df.empty:
        finite = np.isfinite(scored_changed_df.p5_min) & np.isfinite(scored_changed_df.frozen_min)
        for variant in ["frozen", "p5"]:
            error = (scored_changed_df[f"{variant}_min"] - scored_changed_df.default_min)[finite]
            lines.append(f"  model - Google default, {variant}: n {len(error)}, median {error.median():+.1f}, "
                         f"mean {error.mean():+.2f}, MAE {error.abs().mean():.2f} min")
        lines.append(f"  Google default's mode: {scored_changed_df.mode_group.value_counts().to_dict()}; boardings: "
                     f"{scored_changed_df.boardings.value_counts().to_dict()}")
    write_score(lines, {"table": checks_df.reset_index(), "changed": changed_df})


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "build":
        build()
    elif mode == "route":
        route(sys.argv[2], sys.argv[3])
    elif mode == "route_all":
        route_all()
    elif mode == "score":
        score()
    else:
        raise SystemExit(__doc__)
