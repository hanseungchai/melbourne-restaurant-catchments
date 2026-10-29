"""P3 transfer-buffer sweep: is 200 s the best transfer board wait for the model of record, or a knife-edge?

Claim under test (concepts/transit.md TRN-16 P3; DESIGN.md Q24; user, 2026-10-21, 65th: the sweep runs before the
freeze): P3 charges 0 s at the first boarding and TRANSFER_BUFFER_S = 200 s at every transfer, read off Google's
routes (transit_google_transfer_buffer.py: no Google slack in (0, 200 s]), not fitted. R5's transfer walk runs ~9 s
longer than Google's listed (transit_r5_transfer_walk.py), and a 190 s buffer was set aside as a fit to Google's error
(Not adopted, 55th / 61st) with a free sweep 170-230 s offered. TRN-16 (1) revised (61st) allows a declared fitted
value on training pairs. Where the pipeline would rely on it: transit bands 1-2 (SCR-1, RCH-1) through the frozen jar.

Model: the model of record (R5 + P1 + P3 + P2 at 4.143 km/h on v2, drawn points; transit_r5_patch_connector.py
p2orig) with only P3's TRANSFER_BOARD_WAIT_SEC changed, b in BUFFER_GRID_S (first boarding stays 0 s). Each jar is
P2's jar with FastRaptorWorker recompiled from `inputs/r5py/r5-7.5.1` (never edited) through P3's patch at (0, b).
Pair time = min(transit, walk) in seconds, rounded to the nearest minute half up (SCR-10). Pairs: every scored
training pair (v2's range results: train half, second batch, top-up); the test half and the holdout are not read.

Checks before any reading (stop on failure):
  (B1) the jar built at b = 200 holds FastRaptorWorker classes identical (javap -c -p) to P2's jar; every other b
       differs from it only in lines carrying the constant.
  (F1) the b = 200 run reproduces the model of record exactly: transit and walk seconds of the saved p2orig training
       routes on every pair, its scored minutes (p2orig_min) on every pair, and its hard-miss total (23).

Rule (user OK, 2026-10-21, 66th; the patch rule of transit_r5_patch_board_wait.py plus the zone gate the user added
the same day): hard misses as TRN-13 (k = 2 range, random pairs only).
  Pick: b* = the grid value with the fewest hard misses on the training half (set "train"); ties to the value
  closest to 200 (Google's reading); at equal distance, the smaller (Claude's, stated before the run).
  Verdict at b* against b = 200, each by the patch rule (IMPROVES if the total falls and no test gains more than
  SNAP_TOLERANCE_MISSES; WORSENS if it rises; else MIXED): (V1) the second batch alone is not WORSENS; (V2) the pooled
  random pairs (train + second) IMPROVES; (Z) every TRN-13 zone check that passes at 200 (floor, noise bar, balance,
  zones 1 and 2, on all scored pairs as the scorers) still passes at b*. b* is adopted only if V1, V2 and Z hold;
  otherwise 200 stays. If b* = 200 the reading is "200 stays" with no verdict. The top-up is not random: it enters no
  hard test (it does enter the zones, as in every scorer); reported only. Full measures at b* and 200; whole curve.
Prediction (Claude's, before the run): totals within 1-2 misses across the grid; 200 stays.

Conclusion (run 2026-10-21/22, 3,448 training pairs; rule above OK'd before the run): B1 PASS (200 identical to P2's
  jar; others differ only in the constant). F1 PASS (0 route values off, 0 pairs' minutes off, total 23). The curve is
  flat: every buffer 170-230 gives the same hard misses in every test and scope (training half 8, second batch 15,
  pooled 23), no band call changes and no zone failures; minutes change on 45-136 pairs (190 / 170) and the mean error
  to the range moves -1.85 (170) to -1.55 (230) min, about +0.05 min per 10 s. b* = 200 (all tied): 200 stays, no
  verdict. Prediction (totals within 1-2, 200 stays) held, more strongly: no change at all. Reading (Claude's): the
  buffer is not a knife-edge for band calls; within +/-30 s it moves only seconds.

Inputs (read only): P2's jar, `inputs/r5py/` source, v2 networks and feeds, v2's range results, the model of record's
training routes and scored table, Google's training route tables. Writes jars to outputs/r5_patches/ and tables to
diagnostics/diagnostic_data/. Self-contained (CLAUDE.md D1). No paid API calls. One JVM per process (R5 caches per
JVM; one jar per process). Usage: `python transit_buffer_sweep.py build`, `... route_train <buffer_s> <release>`,
`... route_all` (each buffer and release in its own process, in turn), `... score`.
"""
import datetime
import difflib
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
RECORD_NAME = "transit_r5_patch_connector"
BASE_JAR_PATH = PATCH_DIR / f"r5-v7.5.1-r5py-all_{RECORD_NAME}_p2.jar"   # the model of record's jar
RECORD_ROUTES_GLOB = f"{RECORD_NAME}_2*_trainroutes_p2orig_{{release}}.csv"
RECORD_SCORED_GLOB = f"{RECORD_NAME}_2*_train_scored.csv"
V2_NAME = "transit_pathway_network_v2"
NAME = "transit_buffer_sweep"

# --- the swept constant (P3's patch, copied from transit_r5_patch_board_wait.py) --------------------
RECORD_BUFFER_S = 200                          # evidence: diagnostics/transit_google_transfer_buffer.py
BUFFER_GRID_S = [170, 180, 190, 200, 210, 220, 230]
FIRST_BOARD_WAIT_S = 0
CLASS_NAME = "com.conveyal.r5.profile.FastRaptorWorker"
CLASS_FILE = CLASS_NAME.replace(".", "/")
GUARD_CLASSES = [CLASS_NAME, "com.conveyal.r5.streets.StreetRouter", "com.conveyal.r5.streets.LinkedPointSet",
                 "com.conveyal.r5.analyst.TravelTimeReducer"]
CONST_ANCHOR = "    private static final int MINIMUM_BOARD_WAIT_SEC = 60;\n"
CALL_OLD = "int earliestBoardTime = inputState.bestTimes[stop] + MINIMUM_BOARD_WAIT_SEC;"
CALL_NEW = ("int earliestBoardTime = inputState.bestTimes[stop] + boardWaitSec(inputState); "
            "// PLATICA TRN-16 P3 (was + MINIMUM_BOARD_WAIT_SEC)")
N_CALL_SITES = 2
METHOD_TEMPLATE = """
    // PLATICA TRN-16 P3: board wait by round. Round 1 (first boarding) reads round 0, the access search, whose
    // previous state is null; later rounds are transfers.
    private static final int FIRST_BOARD_WAIT_SEC = {first};
    private static final int TRANSFER_BOARD_WAIT_SEC = {transfer};

    private static int boardWaitSec (RaptorState inputState) {{
        return inputState.previous == null ? FIRST_BOARD_WAIT_SEC : TRANSFER_BOARD_WAIT_SEC;
    }}
"""

# --- values copied from transit_r5_patch_connector.py ----------------------------------------------
R5_MAX_MEMORY = "7G"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
SPEED_KMH = 4.143                              # Q24 (2) median; user 2026-10-21
MAX_TIME_MIN = 90
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
CALLS = ["transit", "walk"]
RELEASES = ["20261009", "20261016"]
SECONDS_PER_MIN = 60
GOOGLE_COL = "arrival_from_request_s"          # the scorers' Google quantity (transit_fetch.py google_min)
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
GOOGLE_ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                       "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                       "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
RANGE_RESULTS_GLOB = f"{V2_NAME}_2*_range_owndate_results.csv"
PICK_SET = "train"
CHECK_SET = "second"
TOPUP_SET = "topup"
RECORD_HARD_TOTAL = 23                         # the model of record's hard misses (transit_r5_patch_connector.py)
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
PROGRESS_EVERY = 500


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def jar_path(buffer_s):
    return PATCH_DIR / f"r5-v7.5.1-r5py-all_{NAME}_b{buffer_s}.jar"


# --- build -----------------------------------------------------------------------------------------
def class_names(classes_dir):
    return sorted(p.relative_to(classes_dir).with_suffix("").as_posix().replace("/", ".")
                  for p in classes_dir.rglob("*.class"))


def javap(classpath, names):
    out = subprocess.run([str(JDK_BIN_DIR / "javap"), "-c", "-p", "-cp", str(classpath)] + names,
                         capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def diff_lines(a, b):
    return [line for line in difflib.unified_diff(a, b, n=0, lineterm="") if not line.startswith(("---", "+++", "@@"))]


def patched_source(source, first_s, transfer_s):
    assert source.count(CONST_ANCHOR) == 1, "constant anchor not found exactly once"
    assert source.count(CALL_OLD) == N_CALL_SITES, f"expected {N_CALL_SITES} board-wait call sites"
    text = source.replace(CONST_ANCHOR, CONST_ANCHOR + METHOD_TEMPLATE.format(first=first_s, transfer=transfer_s))
    return text.replace(CALL_OLD, CALL_NEW)


def build():
    assert BASE_JAR_PATH.exists(), "P2's jar missing: run transit_r5_patch_connector.py build"
    source = (R5_SOURCE_DIR / f"{CLASS_FILE}.java").read_text(encoding="utf-8")
    lines = [f"{NAME} {run_date()} build (base: {BASE_JAR_PATH.name})"]
    is_ok = True
    for buffer_s in BUFFER_GRID_S:
        variant_dir = PATCH_DIR / f"{NAME}_b{buffer_s}"
        src_path = variant_dir / "src" / f"{CLASS_FILE}.java"
        classes_dir = variant_dir / "classes"
        src_path.parent.mkdir(parents=True, exist_ok=True)
        classes_dir.mkdir(parents=True, exist_ok=True)
        src_path.write_text(patched_source(source, FIRST_BOARD_WAIT_S, buffer_s), encoding="utf-8", newline="\n")
        subprocess.run([str(JDK_BIN_DIR / "javac"), "--release", "21", "-proc:none", "-nowarn", "-cp", str(BASE_JAR_PATH),
                        "-d", str(classes_dir), str(src_path)], check=True)
        names = class_names(classes_dir)
        assert all(n == CLASS_NAME or n.startswith(CLASS_NAME + "$") for n in names), f"unexpected classes: {names}"
        base_javap = javap(BASE_JAR_PATH, names)
        diff = diff_lines(base_javap, javap(classes_dir, names))
        jar = jar_path(buffer_s)
        shutil.copyfile(BASE_JAR_PATH, jar)
        class_files = [p.relative_to(classes_dir).as_posix() for p in classes_dir.rglob("*.class")]
        subprocess.run([str(JDK_BIN_DIR / "jar"), "uf", str(jar)] + sum([["-C", str(classes_dir), f] for f in class_files], []),
                       check=True)
        assert diff_lines(base_javap, javap(jar, names)) == diff, f"{jar.name}: classes in the jar differ from the compiled classes"
        if buffer_s == RECORD_BUFFER_S:
            is_pass = not diff
            lines.append(f"(B1) b {buffer_s} vs P2's jar ({len(names)} classes), javap -c -p: "
                         f"{'PASS' if is_pass else 'FAIL'} ({len(diff)} differing lines)")
        else:
            is_pass = bool(diff) and all(str(RECORD_BUFFER_S) in line or str(buffer_s) in line for line in diff)
            lines.append(f"(B1) b {buffer_s} vs P2's jar: {'PASS' if is_pass else 'FAIL'} (only constant lines differ):")
            lines += [f"    {line}" for line in diff]
        is_ok &= is_pass
        lines.append(f"    jar {jar.relative_to(PROJECT_ROOT)}")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_build.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    assert is_ok, "B1 failed: stop"


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
    is_transit) in seconds."""
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

    return ttm


def training_pairs():
    pairs_df = pd.read_csv(newest(RANGE_RESULTS_GLOB))
    return pairs_df[pairs_df.is_scored.astype(bool)]


def routes_glob(buffer_s, release):
    return f"{NAME}_2*_trainroutes_b{buffer_s}_{release}.csv"


def route_train(buffer_s, release):
    """Training routing for one buffer on one release, drawn points (p2orig); appends a row per pair, resumes."""
    buffer_s = int(buffer_s)
    assert buffer_s in BUFFER_GRID_S and release in RELEASES
    pairs_df = training_pairs()
    pairs_df = pairs_df[pairs_df.release.astype(str) == release]
    saved = newest(routes_glob(buffer_s, release))
    table_path = saved if saved is not None else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_trainroutes_b{buffer_s}_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"b{buffer_s} {release}: {len(pairs_df)} pairs, {len(done)} done, {len(todo_df)} to route -> {table_path.name}",
          flush=True)
    if todo_df.empty:
        return
    ttm = open_network(jar_path(buffer_s), release)
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


def route_all():
    """Every buffer on both releases, each in its own process (one JVM, one jar), b = 200 first; stops on a failure."""
    order = [RECORD_BUFFER_S] + [b for b in BUFFER_GRID_S if b != RECORD_BUFFER_S]
    for buffer_s in order:
        for release in RELEASES:
            print(f"== b{buffer_s} {release}", flush=True)
            subprocess.run([sys.executable, "-u", str(Path(__file__).resolve()), "route_train", str(buffer_s), release],
                           check=True)


# --- score (measures copied from transit_walk_charge.py) -------------------------------------------
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
    """Run 3's measures for one model, with medians beside means; returns (lines, hard counts, zone failures)."""
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
    return lines, hard, zone_failures


def reading_of(hard, base_hard):
    total, base_total = sum(k for k, _, _ in hard.values()), sum(k for k, _, _ in base_hard.values())
    gain = max(hard[test][0] - base_hard[test][0] for test in hard)
    reading = ("IMPROVES" if total < base_total and gain <= SNAP_TOLERANCE_MISSES
               else "WORSENS" if total > base_total else "MIXED")
    return total, base_total, gain, reading


def score():
    pairs_df = training_pairs().set_index("draw_no").sort_index()
    routes = {}
    for buffer_s in BUFFER_GRID_S:
        paths = [newest(routes_glob(buffer_s, release)) for release in RELEASES]
        assert all(paths), f"route_train b{buffer_s} on both releases first"
        routes[buffer_s] = pd.concat([pd.read_csv(p) for p in paths]).set_index("draw_no").sort_index()
        assert list(routes[buffer_s].index) == list(pairs_df.index), f"b{buffer_s}: routed pairs != training pairs"
    n = len(pairs_df)
    lines = [f"{NAME} {run_date()} score: {n} training pairs ({pairs_df.set_name.value_counts().to_dict()}), "
             f"speed {SPEED_KMH} km/h, v2 network, drawn points"]

    google_df = pd.concat([pd.read_csv(path).assign(set_name=name) for name, path in GOOGLE_ROUTES_PATHS.items()])
    google_df = google_df[google_df.is_default.astype(bool)].set_index(["set_name", "draw_no"])
    keys = list(zip(pairs_df.set_name, pairs_df.index))
    google_s = google_df[GOOGLE_COL].reindex(keys).to_numpy(dtype=float)
    steps = google_df.n_transit_steps.reindex(keys).to_numpy(dtype=float)
    df = pairs_df.reset_index().assign(boardings=[BOARDING_GROUPS[min(int(x), 2)] if np.isfinite(x) else np.nan for x in steps])
    low, high = df.low_2.to_numpy(), df.default_min.to_numpy()
    is_random = (df.set_name != TOPUP_SET).to_numpy()
    in_set = {name: (df.set_name == name).to_numpy() for name in [PICK_SET, CHECK_SET]}

    model_s = {b: np.fmin(r.transit.fillna(np.inf).to_numpy(), r.walk.fillna(np.inf).to_numpy()) for b, r in routes.items()}
    model_min = {b: rounded_min(s) for b, s in model_s.items()}
    base_min = model_min[RECORD_BUFFER_S]

    record_df = pd.concat([pd.read_csv(newest(RECORD_ROUTES_GLOB.format(release=r))) for r in RELEASES]
                          ).set_index("draw_no").sort_index().reindex(pairs_df.index)
    off_routes = int((~((routes[RECORD_BUFFER_S][CALLS].to_numpy() == record_df[CALLS].to_numpy())
                        | (np.isnan(routes[RECORD_BUFFER_S][CALLS].to_numpy()) & np.isnan(record_df[CALLS].to_numpy())))).sum())
    saved = pd.read_csv(newest(RECORD_SCORED_GLOB)).set_index("draw_no").reindex(pairs_df.index)
    off_min = int((base_min != saved.p2orig_min.to_numpy(dtype=float)).sum())
    base_total = sum(k for k, _, _ in hard_counts(base_min[is_random], low[is_random], high[is_random]).values())
    is_f1 = off_routes == 0 and off_min == 0 and base_total == RECORD_HARD_TOTAL
    lines.append(f"(F1) b {RECORD_BUFFER_S} reproduces the model of record: {'PASS' if is_f1 else 'FAIL'} ({off_routes} route "
                 f"values off, {off_min} pairs' minutes off, hard-miss total {base_total} vs {RECORD_HARD_TOTAL})")
    if not is_f1:
        print("\n".join(lines))
        raise SystemExit("F1 failed: stop")

    curve, texts, zone_failures, hards = [], {}, {}, {}
    for buffer_s in BUFFER_GRID_S:
        minutes, seconds = model_min[buffer_s], model_s[buffer_s]
        row = {"buffer_s": buffer_s}
        for scope, mask in [("pick", in_set[PICK_SET]), ("check", in_set[CHECK_SET]), ("pooled", is_random)]:
            hard = hard_counts(minutes[mask], low[mask], high[mask])
            row.update({f"{scope}_{test}": k for test, (k, _, _) in hard.items()})
            row[f"{scope}_total"] = sum(k for k, _, _ in hard.values())
        distance = distance_to_range(minutes, low, high)[np.isfinite(minutes)]
        row["error_to_range_median"], row["error_to_range_mean"] = np.median(distance), distance.mean()
        row["minutes_changed"] = int((minutes != base_min).sum())
        row["band_calls_changed"] = int((band_of(minutes) != band_of(base_min)).sum())
        text, hards[buffer_s], zone_failures[buffer_s] = model_lines(
            f"b = {buffer_s} s", minutes, seconds, df, google_s, is_random,
            None if buffer_s == RECORD_BUFFER_S else hards.get(RECORD_BUFFER_S))
        texts[buffer_s] = text
        row["zone_failures"] = "; ".join(zone_failures[buffer_s]) or "none"
        curve.append(row)
    curve_df = pd.DataFrame(curve)
    lines += ["", "curve (hard-miss counts by scope; error to range in min):", curve_df.round(3).to_string(index=False)]

    best = curve_df.pick_total.min()
    tied = curve_df[curve_df.pick_total == best].assign(distance=lambda d: (d.buffer_s - RECORD_BUFFER_S).abs())
    b_star = int(tied.sort_values(["distance", "buffer_s"]).buffer_s.iloc[0])   # closest to 200, then the smaller
    lines += texts[RECORD_BUFFER_S] + ([] if b_star == RECORD_BUFFER_S else texts[b_star])
    lines += ["", f"PICK: b* = {b_star} s (fewest training-half hard misses {best}; tied: {sorted(tied.buffer_s)}; "
                  "ties to the value closest to 200, then the smaller)"]
    if b_star == RECORD_BUFFER_S:
        lines.append(f"READING: 200 stays (b* = {RECORD_BUFFER_S}; no verdict)")
    else:
        verdicts = {}
        for scope, mask in [("V1 second batch", in_set[CHECK_SET]), ("V2 pooled random", is_random)]:
            verdicts[scope] = reading_of(hard_counts(model_min[b_star][mask], low[mask], high[mask]),
                                         hard_counts(base_min[mask], low[mask], high[mask]))
        newly_failing = sorted(set(zone_failures[b_star]) - set(zone_failures[RECORD_BUFFER_S]))
        is_v1 = verdicts["V1 second batch"][3] != "WORSENS"
        is_v2 = verdicts["V2 pooled random"][3] == "IMPROVES"
        is_z = not newly_failing
        lines += [f"{scope}: hard misses {total} vs b 200 {base} (largest gain {gain:+d}) -> {reading}"
                  for scope, (total, base, gain, reading) in verdicts.items()]
        lines.append(f"(Z) zone checks passing at 200 still pass at b*: {'PASS' if is_z else 'FAIL'} "
                     f"(newly failing: {', '.join(newly_failing) or 'none'})")
        lines.append(f"at b* vs 200: minutes changed on {int((model_min[b_star] != base_min).sum())} pairs; band calls changed "
                     f"{int((band_of(model_min[b_star]) != band_of(base_min)).sum())}")
        is_pass = is_v1 and is_v2 and is_z
        lines.append(f"READING: {'PASS: b* = ' + str(b_star) + ' s adopted by the rule' if is_pass else 'FAIL: 200 stays'} "
                     f"(V1 {'ok' if is_v1 else 'fails'}, V2 {'ok' if is_v2 else 'fails'}, Z {'ok' if is_z else 'fails'})")
    topup = ~is_random
    lines.append(f"top-up (report only, n {int(topup.sum())}): error to range mean at 200 "
                 f"{distance_to_range(base_min[topup], low[topup], high[topup]).mean():+.2f}, at b* "
                 f"{distance_to_range(model_min[b_star][topup], low[topup], high[topup]).mean():+.2f}")

    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    curve_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_curve.csv", index=False)


if __name__ == "__main__":
    {"build": build, "route_train": route_train, "route_all": route_all, "score": score}[sys.argv[1]](*sys.argv[2:])
