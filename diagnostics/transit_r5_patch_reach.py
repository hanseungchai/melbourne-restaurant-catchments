"""R5 reporting patch (TRN-16 register; user, 2026-10-23, 80th: reporting, not the frozen transit model): a departure
window reports, per origin -> destination, how many of its minutes reach within a cut ("reach"), or the travel times at
fixed minutes of the window ("draws"), instead of percentiles.

Claim under test (DESIGN.md Q25, Q26; concepts/scoring.md SCR-12, SCR-13; transit_departure_sampling.py): R5's range
RAPTOR routes every minute of a departure window as its own departure, and `TravelTimeReducer.
extractTravelTimePercentilesAndRecord` receives all of them (one per minute, in minute order: no frequency-based trips in
the PTV feeds, so no Monte Carlo draws) before sorting them into percentiles. Reporting a count per cut instead gives a
slot's reach probability exactly (all minutes, no departure noise) at a window's cost; reporting the times at fixed
minute indices gives joint departures (the same minute for every destination of an origin; SCR-12's draws). Travel
times are the frozen model's (TRN-16, P1-P3); only what is reported changes. Where the pipeline would rely on it: the
transit reachability pass (RCH-21, RCH-23) and R-bar's venue sample (RCH-7), if the user adopts it.

The patch, in Python terms (`TravelTimeReducer`, on top of P1's seconds-out line; the frozen jar is the base):
  the constructor reads the JVM property `platica.report` once per task: unset or empty = off (stock behaviour,
  P1 included); "reach:c1,c2,..." = one cut in seconds per requested percentile; "draws:i1,i2,..." = one minute index
  per percentile (0 = first minute of the window, checked in T3). In both modes the requested percentiles are
  placeholders (r5py needs 1-5 values); the reported value in column p_k is
    reach: n = number of minutes with time <= c_k (R5's UNREACHED never counts), reported as UNREACHED when n = 0
      (so r5py drops the pair as NaN); r5py zeroes from == to, which then reads as full reach;
    draws: the time at iteration i_k (UNREACHED if not reached that minute); iteration i is minute W - 1 - i of a
      W-minute window (range RAPTOR runs backwards; T3, 2026-10-23).
  Both entry points are covered: per-minute times (`extractTravelTimePercentilesAndRecord`) and the unvarying times of
  an origin that reaches no stop (`recordUnvaryingTravelTimeAtTarget`, every minute the same time).

Steps (modes; one JVM per process, the jar chosen at JVM start through r5py's `--r5-classpath`):
  build  `TravelTimeReducer` from `inputs/r5py/r5-7.5.1` (never edited) twice, both with P1's line: "recompiled"
      (P1 only) and "patched"; javac 21 against the frozen jar; each into its own copy of the frozen jar in
      outputs/r5_patches/. (B1) recompiled vs the frozen jar's class: javap -c -p identical, else stop. (B2) patched vs
      the frozen jar's class: differing javap lines (constant-pool indices masked), printed: expected additions only.
  test  On the v2 network of release 20261016 (as transit_departure_sampling.py), TEST_ORIGINS seeded origins from
      transit_departure_sampling's origin sample, every venue hex as destination, max ROUTE_MAX_MIN, walk 4.143 km/h,
      Wed 2026-10-28 TEST_SLOT (30-min window). Rules (Claude's, written before any result):
      (T1) patched jar, property unset, 1-min window at TEST_SLOT: equal to the frozen jar's value on every pair (the
           frozen values are saved by a run of this mode on the frozen jar first). Any difference fails.
      (T2) reach mode over the window vs the frozen jar's 30 single 1-min departures at minutes 0..29: count of
           minutes with time <= cut equal, every pair, cuts 629 / 1229 s. < MINOR_SHARE of pairs differing = minor,
           each listed; >= fails.
      (T3) draws mode at minute indices DRAW_INDICES vs the single departures at those minutes: equal, every pair;
           same line. If T3 fails as indexed but passes with index i read as minute 29 - i, the order is reversed:
           reported, and the docstring above corrected.
  timing  Reach mode, TIMING_ORIGINS origins, Wed windows of TIMING_WINDOWS_MIN starting 17:30: wall time per call
      vs one single departure on the same origins.

Conclusion (run 2026-10-23, 80th autonomous; rules above written before any result): build B1 PASS (stock + P1
  recompiles to the frozen jar's class, 0 differing lines); B2 additions only (199 lines, 0 removed: two fields, the
  constructor call, two early returns behind "mode set", two methods). Test (300 origins x 8,959 venue hexes, Wed 18:00):
  T1 PASS (off = frozen on 30,428 / 30,428 pairs); T2 PASS (reach counts = the 30 single departures' counts, 0 of
  4,188 pairs at 629 s, 0 of 28,384 at 1,229 s); T3 as indexed FAIL (46.75%), reversed PASS (0 of 152,065): iteration
  i is minute W - 1 - i (docstring corrected). Timing (1,000 origins, reach mode; one single departure 37 s): window
  30 min = 2.3 singles, 60 = 3.6, 120 = 5.9, 210 = 9.4 (0.078 -> 0.045 singles per minute covered). Named P8r (user:
  P8, -r = reporting only); jars `r5-v7.5.1-r5py-all_p8-r_reach{,_recompiled}.jar` (renamed after the build, same
  bytes). Register entry and adoption are the user's (to record).

Extension: draws cap lifted (user, 2026-10-23, 82nd; TRN-16, RCH-21; built in the 83rd). R5 allows at most 5
  percentiles per call (`AnalysisWorkerTask.validatePercentiles`, MAX_PERCENTILES = 5) and r5py asserts the same in its
  `RegionalTask.percentiles` setter, so draws mode read at most 5 minutes of a window. The production pass reads every
  minute of windows up to MAX_DRAWS = 90 min (placeholder percentiles 1..90 stay inside R5's 1-99 ascending rule).
  Changes: (a) `AnalysisWorkerTask.validatePercentiles` skips the count cap only while `platica.report` is set (off =
  stock: the cap holds); the 1-99 and ascending checks stay; (b) r5py's setter assertion is bypassed in this script
  (and in production) by replacing the property's setter at run time (`lift_r5py_percentile_cap`); r5py's code is not
  edited. The TravelTimeReducer patch is the 80th's, unchanged. Jar `r5-v7.5.1-r5py-all_p8-r_draws.jar` (Claude's
  name, user to confirm); the p8-r_reach jars are untouched; build folders and result files carry the jar label.
  Frozen singles are recomputed (no reuse of the 80th's): one per minute 17:30-18:59 Wed 2026-10-28 (T4_START, 90
  minutes); T1-T3 read the 18:00 slot from them (minutes 30-59).
  Rules (Claude's, not user-approved; written 2026-10-23 before any result of the extension):
    (B1) as before, for both classes (TravelTimeReducer with P1; AnalysisWorkerTask stock): javap identical to the
         frozen jar's, inner classes included.
    (B2) as before: patched vs frozen, additions only, printed.
    (T1-T3) as before, same thresholds, on the draws jar.
    (T4) draws mode, one 90-min window from T4_START, indices 0..89: the value at index i equals the frozen single at
         minute 89 - i (T3's reversed order), for every pair (from != to) and every index; 0 differing values = PASS,
         < MINOR_SHARE minor (each listed), else FAIL. Pairs are compared as the union of both sides' reached pairs
         (NaN on one side counts as a difference).
    (T0) tiny call first: 2 origins, 90 placeholders, draws mode; must return 90 columns without error before T4 is
         costed or run. T0 and T4 read R5's result arrays per origin (`ttm_direct`, the production interface):
         r5py's per-cell null fill makes a 90-column TravelTimeMatrix take hours (seen in the frozen run, ~1 min per
         300-origin single); set before any patched result.
  Conclusion (run 2026-10-23, 83rd autonomous; rules above written before any result): B1 PASS for TravelTimeReducer
    (stock + P1), AnalysisWorkerTask and AnalysisWorkerTask$Type (stock), 0 differing lines each; B2 TravelTimeReducer
    199 lines added, 0 removed (the 80th's patch); AnalysisWorkerTask 8 differing lines, 1 "removed" = the cap's
    branch inverted (if_icmpgt -> if_icmple) by the new `|| property set` condition, plus the property read: expected.
    Jar sha256 a4490e39d7aab425a790d3da1b7dd0e69be58850b0f077e89d41677c44c76656. Test (300 origins x 8,959 venue
    hexes, max 21 min): T0 PASS (90 columns); T1 PASS (0 of 33,541 pairs); T2 PASS (0 of 4,188 / 28,384); T3 PASS
    (0 of 87,847 values, reversed order as found in the 80th); T4 PASS (0 of 1,601,530 values: every minute of a
    90-min window equals its own single departure). T4's draws call: 43 s for 300 origins (0.14 s per origin per
    90-min window, direct reads).

Inputs (read only): the frozen jar and `inputs/r5py/` source; transit_departure_sampling's origin sample; the v2
network; the hex nodes table; venues with hex. Writes jars to outputs/r5_patches/ and tables to
diagnostics/diagnostic_data/. Self-contained (CLAUDE.md D1). No API calls; r5py only.
Usage: `python transit_r5_patch_reach.py build`, `... test frozen`, `... test patched`, `... timing`.
"""
import datetime
import difflib
import hashlib
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "-37.76870_144.97196"
FILE_TAG = f"res2021_wrk2021_ven20260925_{SUBJECT}"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
R5_SOURCE_DIR = PROJECT_ROOT / "inputs" / "r5py" / "r5-7.5.1" / "src" / "main" / "java"
PATCH_DIR = PROJECT_ROOT / "outputs" / "r5_patches"
JDK_BIN_DIR = Path(r"C:\Program Files\Java\jdk-21.0.12\bin")
FROZEN_JAR_PATH = PATCH_DIR / "r5-v7.5.1-r5py-all_transit_r5_patch_connector_p2.jar"
FROZEN_JAR_SHA256 = "62a8f6c1afa2e0a0c86860e336da499f9344e46e6c6d259d9c4824d129e68eb3"
V2_NAME = "transit_pathway_network_v2"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"
VENUES_WITH_HEX_PATH = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT / f"venues_with_hex_ven20260925_{SUBJECT}.csv"
ORIGIN_SAMPLE_PATH = DIAGNOSTIC_DATA_DIR / "transit_departure_sampling_routes_20261023" / "origin_sample.csv"
NAME = "transit_r5_patch_reach"

# --- the patch -------------------------------------------------------------------------------------
CLASS_NAME = "com.conveyal.r5.analyst.TravelTimeReducer"
CLASS_FILE = CLASS_NAME.replace(".", "/")
P1_OLD = "            int timeMinutes = timeSeconds / FastRaptorWorker.SECONDS_PER_MINUTE;\n"
P1_NEW = ("            int timeMinutes = timeSeconds; // PLATICA TRN-16 P1: seconds out "
          "(was timeSeconds / FastRaptorWorker.SECONDS_PER_MINUTE); rounding in Python (SCR-10)\n")
TAG = "// PLATICA reach report"
SITES = [   # (old, new): each old found exactly once in the P1 source
    ("        this.nPercentiles = task.percentiles.length;\n",
     "        this.nPercentiles = task.percentiles.length;\n"
     f"        platicaReadReport(); {TAG}\n"),
    ("        int[] travelTimePercentilesSeconds = new int[nPercentiles];\n"
     "        Arrays.fill(travelTimePercentilesSeconds, timeSeconds);\n",
     f"        if (platicaMode != null) {{ {TAG}\n"
     "            int[] everyMinute = new int[timesPerDestination];\n"
     "            Arrays.fill(everyMinute, timeSeconds);\n"
     "            recordTravelTimePercentilesForTarget(target, platicaReport(everyMinute));\n"
     "            return;\n"
     "        }\n"
     "        int[] travelTimePercentilesSeconds = new int[nPercentiles];\n"
     "        Arrays.fill(travelTimePercentilesSeconds, timeSeconds);\n"),
    ("        Arrays.sort(timesSeconds);\n",
     f"        if (platicaMode != null) {{ {TAG}\n"
     "            recordTravelTimePercentilesForTarget(target, platicaReport(timesSeconds));\n"
     "            return;\n"
     "        }\n"
     "        Arrays.sort(timesSeconds);\n"),
]
CAP_CLASS_NAME = "com.conveyal.r5.analyst.cluster.AnalysisWorkerTask"
CAP_CLASS_FILE = CAP_CLASS_NAME.replace(".", "/")
CAP_OLD = ('        checkArgument(nPercentiles <= MAX_PERCENTILES, "Maximum number of percentiles allowed is " + '
           'MAX_PERCENTILES);\n')
CAP_NEW = ('        checkArgument(nPercentiles <= MAX_PERCENTILES || !System.getProperty("platica.report", "").isEmpty(), '
           f'"Maximum number of percentiles allowed is " + MAX_PERCENTILES); {TAG}: cap lifted while a report is set\n')
CLASS_END = "\n}\n"
METHODS = f"""    {TAG}: off unless the JVM property platica.report is "reach:<cut s>,..." or "draws:<minute index>,...".
    private String platicaMode;
    private int[] platicaValues;

    private void platicaReadReport () {{
        String spec = System.getProperty("platica.report", "");
        int colon = spec.indexOf(':');
        if (colon < 0) {{
            platicaMode = null;
            return;
        }}
        platicaMode = spec.substring(0, colon);
        platicaValues = Arrays.stream(spec.substring(colon + 1).split(",")).mapToInt(Integer::parseInt).toArray();
        checkArgument(platicaMode.equals("reach") || platicaMode.equals("draws"), "platica.report mode: reach or draws");
        checkArgument(platicaValues.length == nPercentiles, "platica.report needs one value per percentile");
        if (platicaMode.equals("draws")) {{
            for (int index : platicaValues) {{
                checkArgument(index >= 0 && index < timesPerDestination, "platica.report draw index outside the window");
            }}
        }}
    }}

    private int[] platicaReport (int[] timesSeconds) {{
        int[] reported = new int[nPercentiles];
        for (int p = 0; p < nPercentiles; p++) {{
            if (platicaMode.equals("reach")) {{
                int minutes = 0;
                for (int t : timesSeconds) {{
                    if (t <= platicaValues[p]) {{
                        minutes++;
                    }}
                }}
                reported[p] = minutes == 0 ? UNREACHED : minutes;
            }} else {{
                reported[p] = timesSeconds[platicaValues[p]];
            }}
        }}
        return reported;
    }}
"""
CONST_POOL_REF = re.compile(r"#\d+(:#\d+)?")
CODE_OFFSET = re.compile(r"^\s*\d+: ")
BRANCH_TARGET = re.compile(r"\b(goto|goto_w|if\w*|jsr)\s+\d+")
SWITCH_TARGET = re.compile(r"^\s*(-?\d+|default): \d+$")

# --- routing ---------------------------------------------------------------------------------------
RELEASE = "20261016"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
R5_MAX_MEMORY = "7G"
SPEED_KMH = 4.143
SINGLE_PERCENTILE = 49
PLACEHOLDER_PERCENTILES = [1, 2, 3, 4, 5]
ROUTE_MAX_MIN = 21
CUTS_S = [629, 1229]                            # bands 1-2 (SCR-10)
DRAW_INDICES = [0, 7, 14, 22, 29]
WINDOW_MIN = 30
TEST_SLOT = datetime.datetime(2026, 10, 28, 18, 0)
TEST_ORIGINS = 300
SEED = 20261023
MINOR_SHARE = 0.01
TIMING_ORIGINS = 1000
TIMING_START = datetime.datetime(2026, 10, 28, 17, 30)
TIMING_WINDOWS_MIN = [30, 60, 120, 210]
REPORT_PROPERTY = "platica.report"
MAX_DRAWS = 90                                  # minutes per draws call (82nd: windows read in <= 90-min chunks)
T4_START = datetime.datetime(2026, 10, 28, 17, 30)
T0_ORIGINS = 2
R5_UNREACHED = 2_147_483_647                    # R5's NULL (MAX_INT32)
TEST_SLOT_OFFSET = int((TEST_SLOT - T4_START).total_seconds() // 60)   # 30: the 18:00 slot inside the T4 singles


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


JAR_LABEL = "p8-r_draws"                       # P8r: patch number, -r = reporting only, description (user, 2026-10-23);
                                               # the 80th built "p8-r_reach" (cap 5, AnalysisWorkerTask stock)


def jar_path(variant):
    if variant == "frozen":
        return FROZEN_JAR_PATH
    return PATCH_DIR / f"r5-v7.5.1-r5py-all_{JAR_LABEL}{'' if variant == 'patched' else '_' + variant}.jar"


def javap(classpath, class_name=CLASS_NAME):
    out = subprocess.run([str(JDK_BIN_DIR / "javap"), "-c", "-p", "-cp", str(classpath), class_name],
                         capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def pool_masked(lines):
    masked = []
    for line in lines:
        line = BRANCH_TARGET.sub(r"\1 L", CODE_OFFSET.sub("", CONST_POOL_REF.sub("#", line)))
        masked.append(" ".join(SWITCH_TARGET.sub(r"\1: L", line).split()))
    return masked


def diff_lines(a, b):
    return [line for line in difflib.unified_diff(a, b, n=0, lineterm="") if not line.startswith(("---", "+++"))]


def build():
    with open(FROZEN_JAR_PATH, "rb") as file:
        assert hashlib.file_digest(file, "sha256").hexdigest() == FROZEN_JAR_SHA256, "not the frozen jar"
    source = (R5_SOURCE_DIR / f"{CLASS_FILE}.java").read_text(encoding="utf-8")
    assert source.count(P1_OLD) == 1, "P1 anchor not found exactly once"
    p1_source = source.replace(P1_OLD, P1_NEW)
    patched = p1_source
    for old, new in SITES:
        assert patched.count(old) == 1, f"site not found exactly once: {old!r}"
        patched = patched.replace(old, new)
    assert patched.endswith(CLASS_END)
    patched = patched[:-len(CLASS_END)] + "\n" + METHODS + CLASS_END
    cap_source = (R5_SOURCE_DIR / f"{CAP_CLASS_FILE}.java").read_text(encoding="utf-8")
    assert cap_source.count(CAP_OLD) == 1, "cap anchor not found exactly once"
    cap_patched = cap_source.replace(CAP_OLD, CAP_NEW)
    lines = [f"{NAME} {run_date()} build {JAR_LABEL} (base: {FROZEN_JAR_PATH.name})"]
    is_ok = True
    for variant, texts in [("recompiled", {CLASS_FILE: p1_source, CAP_CLASS_FILE: cap_source}),
                           ("patched", {CLASS_FILE: patched, CAP_CLASS_FILE: cap_patched})]:
        variant_dir = PATCH_DIR / f"{NAME}_{JAR_LABEL}_{variant}"
        classes_dir = variant_dir / "classes"
        classes_dir.mkdir(parents=True, exist_ok=True)
        src_paths = []
        for class_file, text in texts.items():
            src_path = variant_dir / "src" / f"{class_file}.java"
            src_path.parent.mkdir(parents=True, exist_ok=True)
            src_path.write_text(text, encoding="utf-8", newline="\n")
            src_paths.append(str(src_path))
        subprocess.run([str(JDK_BIN_DIR / "javac"), "--release", "21", "-proc:none", "-nowarn", "-cp", str(FROZEN_JAR_PATH),
                        "-d", str(classes_dir)] + src_paths, check=True)
        class_files = sorted(p.relative_to(classes_dir).as_posix() for p in classes_dir.rglob("*.class"))
        assert all(f.startswith((CLASS_FILE, CAP_CLASS_FILE)) for f in class_files), f"unexpected classes: {class_files}"
        jar = jar_path(variant)
        shutil.copyfile(FROZEN_JAR_PATH, jar)
        subprocess.run([str(JDK_BIN_DIR / "jar"), "uf", str(jar)] + sum([["-C", str(classes_dir), f] for f in class_files], []),
                       check=True)
        for class_file in class_files:
            class_name = class_file.removesuffix(".class").replace("/", ".")
            frozen_javap = javap(FROZEN_JAR_PATH, class_name)
            diff = diff_lines(frozen_javap, javap(classes_dir, class_name))
            assert diff_lines(frozen_javap, javap(jar, class_name)) == diff, f"{jar.name}: {class_name} differs in the jar"
            if variant == "recompiled":
                lines.append(f"(B1) {class_name} recompiled (stock{' + P1' if class_name == CLASS_NAME else ''}) vs the "
                             f"frozen jar's, javap -c -p: {'PASS' if not diff else 'FAIL'} ({len(diff)} differing lines)")
                is_ok &= not diff
            else:
                masked = diff_lines(pool_masked(frozen_javap), pool_masked(javap(classes_dir, class_name)))
                removed = [line for line in masked if line.startswith("-")]
                lines.append(f"(B2) {class_name} patched vs the frozen jar's (pool indices masked): {len(masked)} "
                             f"differing lines, {len(removed)} removed")
                lines += [f"    {line}" for line in masked]
        with open(jar, "rb") as file:
            lines.append(f"    jar {jar.relative_to(PROJECT_ROOT)} sha256 {hashlib.file_digest(file, 'sha256').hexdigest()}")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_{JAR_LABEL}_build.txt").write_text(text + "\n", encoding="utf-8",
                                                                                 newline="\n")
    assert is_ok, "B1 failed: stop"


def network_paths():
    """(from transit_holdout_score.py)"""
    feed_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{RELEASE}"
    pbf_path = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{RELEASE}.osm.pbf"
    gtfs = [feed_dir / (f"{name}_{V2_NAME}_{RELEASE}_moved.zip" if name == TRAIN_FEED else f"{name}_{V2_NAME}_{RELEASE}.zip")
            for name in FEED_NAMES]
    return pbf_path, gtfs


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (from transit_holdout_score.py)."""
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


def open_network(variant):
    """Start the JVM on the variant's jar (guarded), load the v2 network; returns (network, jpype)."""
    jar = jar_path(variant)
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(jar)]   # r5py reads these at import
    import jpype
    from r5py import TransportNetwork
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    lift_r5py_percentile_cap()
    for name in [CLASS_NAME, "com.conveyal.r5.profile.FastRaptorWorker"]:
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == jar.resolve(), f"{name} loaded from {location}"
    pbf_path, gtfs = network_paths()
    check_working_copies([pbf_path] + gtfs)
    network = TransportNetwork(pbf_path, gtfs)
    assert network.transit_layer.covers(TEST_SLOT.date())
    return network, jpype


def points(df):
    import geopandas as gpd
    return gpd.GeoDataFrame({"id": df.hex_id.to_numpy()}, crs="EPSG:4326",
                            geometry=gpd.points_from_xy(df.centroid_lon, df.centroid_lat))


def hexes():
    import pyogrio
    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False, columns=["hex_id", "centroid_lat", "centroid_lon"])
    venue_ids = pd.read_csv(VENUES_WITH_HEX_PATH, usecols=["hex_id"]).hex_id.dropna().astype(np.int64).unique()
    sample_ids = pd.read_csv(ORIGIN_SAMPLE_PATH).hex_id.unique()
    rng = np.random.default_rng(SEED)
    return hex_df, points(hex_df[hex_df.hex_id.isin(venue_ids)]), np.sort(sample_ids), rng


def ttm_direct(network, jpype, origins_gdf, destinations_gdf, departure, window_min, report, n_values):
    """As ttm, but each origin's result arrays are read from R5 directly (r5py's per-cell null fill is too slow for 90
    columns): same columns, NaN where R5 reports UNREACHED, rows unreached in every column dropped, from == to set to
    0 (r5py's convention)."""
    import copy
    import com.conveyal.r5
    from r5py import RegionalTask, TransportMode
    jpype.JClass("java.lang.System").setProperty(REPORT_PROPERTY, report)
    task = RegionalTask(network, origin=None, destinations=destinations_gdf, departure=departure,
                        departure_time_window=datetime.timedelta(minutes=window_min),
                        percentiles=list(range(1, n_values + 1)),
                        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
                        max_time=datetime.timedelta(minutes=ROUTE_MAX_MIN), speed_walking=SPEED_KMH)
    to_ids = destinations_gdf.id.to_numpy()
    parts = []
    for from_id, point in zip(origins_gdf.id.to_numpy(), origins_gdf.geometry):
        request = copy.copy(task)
        request.origin = point
        values = com.conveyal.r5.analyst.TravelTimeComputer(request, network._transport_network).computeTravelTimes() \
            .travelTimes.getValues()
        assert len(values) == n_values
        times = np.stack([np.asarray(values[k]) for k in range(n_values)]).T.astype(float)
        times[to_ids == from_id] = 0
        times[times == R5_UNREACHED] = np.nan
        keep = ~np.isnan(times).all(axis=1)
        frame = pd.DataFrame(times[keep], columns=[f"travel_time_p{k + 1}" for k in range(n_values)])
        frame.insert(0, "to_id", to_ids[keep])
        frame.insert(0, "from_id", from_id)
        parts.append(frame)
    return pd.concat(parts, ignore_index=True).set_index(["from_id", "to_id"])


def lift_r5py_percentile_cap():
    """Replace r5py's `RegionalTask.percentiles` setter with one without its `len <= 5` assertion (extension (b))."""
    from r5py.r5.regional_task import RegionalTask

    def set_percentiles(self, percentiles):
        self._percentiles = percentiles
        self._regional_task.percentiles = percentiles

    RegionalTask.percentiles = RegionalTask.percentiles.setter(set_percentiles)


def ttm(network, jpype, origins_gdf, destinations_gdf, departure, window_min, report, percentiles, batch_origins=None):
    from r5py import TransportMode, TravelTimeMatrix
    jpype.JClass("java.lang.System").setProperty(REPORT_PROPERTY, report)
    batch_origins = batch_origins or len(origins_gdf)
    parts = []
    for start in range(0, len(origins_gdf), batch_origins):
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins_gdf.iloc[start:start + batch_origins], destinations=destinations_gdf,
            departure=departure, departure_time_window=datetime.timedelta(minutes=window_min), percentiles=percentiles,
            transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
            max_time=datetime.timedelta(minutes=ROUTE_MAX_MIN), speed_walking=SPEED_KMH))
        columns = [c for c in matrix_df.columns if c.startswith("travel_time")]
        parts.append(matrix_df.dropna(subset=columns, how="all").set_index(["from_id", "to_id"])[columns])
    return pd.concat(parts)


def single_column():
    return f"travel_time_p{SINGLE_PERCENTILE}"


def test(variant):
    hex_df, destinations_gdf, sample_ids, rng = hexes()
    test_ids = rng.choice(sample_ids, TEST_ORIGINS, replace=False)
    origins_gdf = points(hex_df[hex_df.hex_id.isin(test_ids)])
    network, jpype = open_network(variant)
    prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_{JAR_LABEL}"
    if variant == "frozen":
        singles = []
        for minute in range(MAX_DRAWS):
            df = ttm(network, jpype, origins_gdf, destinations_gdf, T4_START + datetime.timedelta(minutes=minute), 1, "",
                     [SINGLE_PERCENTILE])
            singles.append(df[single_column()].rename(str(minute)))
            print(f"frozen single minute {minute}: {len(df):,} pairs", flush=True)
        pd.concat(singles, axis=1).reset_index().to_parquet(f"{prefix}_frozen_singles.parquet", index=False)
        return
    singles_df = pd.read_parquet(f"{prefix}_frozen_singles.parquet").set_index(["from_id", "to_id"])
    singles_df.columns = singles_df.columns.astype(int)
    lines = [f"{NAME} {run_date()} test {JAR_LABEL}: {TEST_ORIGINS} origins x {len(destinations_gdf):,} venue hexes, "
             f"Wed; frozen singles {T4_START:%H:%M} + 0..{MAX_DRAWS - 1} min, {len(singles_df):,} pairs; max "
             f"{ROUTE_MAX_MIN} min"]

    all_indices = list(range(MAX_DRAWS))
    tiny_df = ttm_direct(network, jpype, origins_gdf.head(T0_ORIGINS), destinations_gdf, T4_START, MAX_DRAWS,
                         "draws:" + ",".join(map(str, all_indices)), MAX_DRAWS)
    lines.append(f"(T0) tiny call, {T0_ORIGINS} origins, {MAX_DRAWS} placeholders: {tiny_df.shape[1]} columns, "
                 f"{len(tiny_df):,} pairs: {'PASS' if tiny_df.shape[1] == MAX_DRAWS else 'FAIL'}")
    print(lines[-1], flush=True)
    assert tiny_df.shape[1] == MAX_DRAWS, "T0 failed: stop before T4"

    off_df = ttm(network, jpype, origins_gdf, destinations_gdf, TEST_SLOT, 1, "", [SINGLE_PERCENTILE])[single_column()]
    joined = pd.concat([off_df.rename("off"), singles_df[TEST_SLOT_OFFSET].rename("frozen")], axis=1)
    n_off = int((joined.off.fillna(-1) != joined.frozen.fillna(-1)).sum())
    lines.append(f"(T1) off (property unset) vs frozen, {TEST_SLOT:%H:%M}: {n_off} of {len(joined):,} pairs differ: "
                 f"{'PASS' if n_off == 0 else 'FAIL'}")

    slot_singles_df = singles_df[list(range(TEST_SLOT_OFFSET, TEST_SLOT_OFFSET + WINDOW_MIN))]
    reach_df = ttm(network, jpype, origins_gdf, destinations_gdf, TEST_SLOT, WINDOW_MIN,
                   "reach:" + ",".join(map(str, CUTS_S)), PLACEHOLDER_PERCENTILES[:len(CUTS_S)])
    is_self = reach_df.index.get_level_values(0) == reach_df.index.get_level_values(1)
    reach_df.loc[is_self, :] = WINDOW_MIN                                       # r5py zeroes from == to
    for k, cut_s in enumerate(CUTS_S):
        expected = (slot_singles_df <= cut_s).sum(axis=1)
        expected = expected[expected > 0]
        got = reach_df[f"travel_time_p{PLACEHOLDER_PERCENTILES[k]}"].dropna().astype(int)
        both = pd.concat([got.rename("reach"), expected.rename("singles")], axis=1).fillna(0)
        bad = both[both.reach != both.singles]
        share = len(bad) / len(both)
        verdict = "PASS" if share == 0 else ("minor" if share < MINOR_SHARE else "FAIL")
        lines.append(f"(T2) cut {cut_s} s: reach count vs singles' count, {len(bad)} of {len(both):,} pairs differ "
                     f"({100 * share:.2f}%): {verdict}")
        lines += [f"    {i}: reach {r.reach:.0f}, singles {r.singles:.0f}" for i, r in bad.head(20).iterrows()]

    draws_df = ttm(network, jpype, origins_gdf, destinations_gdf, TEST_SLOT, WINDOW_MIN,
                   "draws:" + ",".join(map(str, DRAW_INDICES)), PLACEHOLDER_PERCENTILES)
    minutes = [TEST_SLOT_OFFSET + WINDOW_MIN - 1 - i for i in DRAW_INDICES]
    lines.append(compare_draws("(T3)", draws_df, singles_df, PLACEHOLDER_PERCENTILES, minutes))

    tick = time.perf_counter()
    window_df = ttm_direct(network, jpype, origins_gdf, destinations_gdf, T4_START, MAX_DRAWS,
                           "draws:" + ",".join(map(str, all_indices)), MAX_DRAWS)
    lines.append(f"T4 draws call {time.perf_counter() - tick:.0f} s; {len(window_df):,} pairs")
    lines.append(compare_draws("(T4)", window_df, singles_df, [i + 1 for i in all_indices],
                               [MAX_DRAWS - 1 - i for i in all_indices]))
    text = "\n".join(lines)
    print(text)
    Path(f"{prefix}_test.txt").write_text(text + "\n", encoding="utf-8", newline="\n")


def compare_draws(label, draws_df, singles_df, percentiles, minutes):
    """Draw column p_k vs the frozen single at minutes[k], every pair (from != to), union of reached pairs."""
    n_bad, n_all, examples = 0, 0, []
    for percentile, minute in zip(percentiles, minutes):
        both = pd.concat([draws_df[f"travel_time_p{percentile}"].rename("draw"), singles_df[minute].rename("single")],
                         axis=1)
        both = both[[a != b for a, b in both.index]].dropna(how="all")
        is_bad = both.draw.fillna(-1) != both.single.fillna(-1)
        n_bad += int(is_bad.sum())
        n_all += len(both)
        examples += [f"    p{percentile} / minute {minute} {i}: draw {r.draw}, single {r.single}"
                     for i, r in both[is_bad].head(3).iterrows()]
    share = n_bad / n_all
    verdict = "PASS" if share == 0 else ("minor" if share < MINOR_SHARE else "FAIL")
    return "\n".join([f"{label} draws (minutes {minutes[0]}..{minutes[-1]}) vs singles: {n_bad} of {n_all:,} values "
                      f"differ ({100 * share:.2f}%): {verdict}"] + examples[:20])


def timing():
    hex_df, destinations_gdf, sample_ids, rng = hexes()
    timing_ids = rng.choice(sample_ids, TIMING_ORIGINS, replace=False)
    origins_gdf = points(hex_df[hex_df.hex_id.isin(timing_ids)])
    network, jpype = open_network("patched")
    report = "reach:" + ",".join(map(str, CUTS_S))
    tick = time.perf_counter()
    ttm(network, jpype, origins_gdf, destinations_gdf, TIMING_START, 1, "", [SINGLE_PERCENTILE])
    single_s = time.perf_counter() - tick
    lines = [f"{NAME} {run_date()} timing: {TIMING_ORIGINS} origins x {len(destinations_gdf):,} venue hexes; one single "
             f"departure {single_s:.0f} s"]
    print(lines[-1], flush=True)
    for window_min in TIMING_WINDOWS_MIN:
        tick = time.perf_counter()
        ttm(network, jpype, origins_gdf, destinations_gdf, TIMING_START, window_min, report,
            PLACEHOLDER_PERCENTILES[:len(CUTS_S)])
        wall_s = time.perf_counter() - tick
        lines.append(f"  window {window_min} min: {wall_s:.0f} s = {wall_s / single_s:.1f} single departures "
                     f"({wall_s / single_s / window_min:.3f} per minute covered)")
        print(lines[-1], flush=True)
    Path(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_timing.txt").write_text("\n".join(lines) + "\n", encoding="utf-8",
                                                                           newline="\n")


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
    elif sys.argv[1] == "test":
        test(sys.argv[2])
    elif sys.argv[1] == "timing":
        timing()
