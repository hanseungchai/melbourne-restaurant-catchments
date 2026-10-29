"""R5 patch 1 (TRN-16 register): TravelTimeReducer.convertToMinutes returns seconds; rounding moves to Python (SCR-10).

Claim under test (concepts/transit.md TRN-16; DESIGN.md Q24 (3); SCR-10): R5 computes travel times in whole seconds and
loses them in one place, `TravelTimeReducer.convertToMinutes` (`seconds / 60`, integer division, so it truncates). A
one-line patch that returns the seconds unchanged (a) moves nothing else: the patched seconds // 60 are stock R5's
minutes on every call; and (b) gives, rounded to the nearest minute in Python, the minutes the Q24 destination stubs
give (a 30 s dead-end walk on stock R5: floor(t + 30 s) = round(t)). Where the pipeline would rely on it: transit bands
1-2 (SCR-1, RCH-1) through the model of record once Q24 goes into production, replacing the stubs (TRN-16 (5): stubs vs
patch chosen on training equivalence before the holdout is scored).

The patch, in Python terms: `convert_to_minutes(s)` was `UNREACHED if s == UNREACHED else s // 60`; patched it is
`UNREACHED if s == UNREACHED else s`. Nothing else on r5py's path reads these values: TravelTimeResult.setTarget stores
the ints (no range check; seconds stay far below int range), max_time prunes in seconds before this point, accessibility
reads the seconds array, and r5py's `_parse_results` only copies, zeroes from == to and turns MAX_INT into NaN (read
2026-10-21). So r5py's `travel_time` column holds seconds under the patched jar.

Steps (modes; one JVM per process, the jar is chosen at JVM start through r5py's `--r5-classpath`):
  build  The class twice from `inputs/r5py/r5-7.5.1` (never edited): unchanged ("recompiled") and patched; javac 21
      against the stock jar; each class put into its own copy of the stock jar in outputs/r5_patches/ (the original
      jar untouched). (B1) recompiled vs the jar's class: javap -c -p identical, else stop. (B2) patched vs the jar's
      class: the differing javap lines, printed (expected: only convertToMinutes's divide).
  draw  The 100-pair set, from the training pairs (train half, second batch, top-up; scored; test half and holdout
      closed) that have a median-speed stub. Seed DRAW_SEED. Strata, from the saved stock stub run at the median speed
      (4.143 km/h; transit_q24_combined.py run 3) and Google's default route (written before the draw):
        near_max (10): any of the six saved stock values (stock / shifted / walk calls; snapped and stub-tip
            destinations) within NEAR_MAX_MIN of its call's max_time (90, 91, 90 min);
        walk_only (20): otherwise, R5 walks (no-wait model: shifted >= walk on the snapped destination);
        one_boarding (40): otherwise, transit wins and Google's default has one transit step;
        transfers (30): otherwise, transit wins and Google's default has two or more.
      Google's step count stands in for R5's boardings, which TTM does not return; 4 pairs where R5 rides but Google's
      default walks belong to no stratum.
  route <variant> <release>  variant stock | recompiled | patched. Per pair, as transit_q24_combined.py route_stubs on
      the same stub extract (b4 2026-10-09, b5 2026-10-16) at the median speed: origin = R5's split on v2, destinations
      [snapped (stub base), stub tip]; three TTM calls (stock, from t - 1 min = shifted, walk-only). Guard: the loaded
      TravelTimeReducer's code source must be the variant's jar. Values saved as r5py returns them (minutes, or seconds
      under the patch).
  score  Rules (Claude's, from the TRN-16 register (user, 2026-10-21); written before any result):
      (T0, reported) stock now vs the saved run-3 stock values: reproduction of the stub run.
      (T1) recompiled = stock, every value exactly (NaN = NaN): off is stock. Any difference fails.
      (T2) patched seconds // 60 = stock minutes, every value: should not differ. Share of pairs with any differing
           value < MINOR_SHARE = flagged minor deviation (each listed), >= MINOR_SHARE fails.
      (T3) round(patched snapped seconds / 60) vs stock stub-tip minutes, every call: expected equal. Rounding half up
           (floor(s / 60 + 1/2)), the stub's own convention; SCR-10 does not say how a :30 tie rounds (Claude's
           choice, flagged). Same < MINOR_SHARE / fail line; every mismatch listed and examined. Reported too: patched
           tip seconds - snapped seconds (30 on every call if the stub is charged exactly 30 s).

Predictions (Claude's, before any result): B1 passes; B2 differs only in convertToMinutes. T0, T1, T2 exact on all 100.
T3 exact on all 100 with tip - snapped = 30 s on every call, since the stub is a dead end and charged exactly 30 s
(run 3 check C4); a mismatch could only come from a path that changes at the cap (a tip value over max_time).

Conclusion (run 2026-10-21; rules above written before any result):
  B1 PASS (0 differing javap lines); B2 differs only in convertToMinutes (`bipush 60; idiv` removed).
  Draw: near_max 10 of 90, walk_only 20 of 381, one_boarding 40 of 1,987, transfers 30 of 986 (40 pairs 2026-10-09,
  60 pairs 2026-10-16).
  T0: stock now = saved run-3 stock, 600 / 600 values. T1 PASS (600 / 600). T2 PASS (600 / 600; patched values whole
  seconds, 180-5,398 s; NaN wherever stock's are).
  T3 FAIL on the pre-set line (3 pairs of 100 >= 1%). Examined, all three in the stub, not the patch:
    - draws 28022, 41908 (near_max, walk call): snapped 5,398 s and 5,385 s round to 90 min; the stub's +30 s pushes
      the tip past the 90-min max_time (NaN). The cap effect predicted above.
    - draw 44367 (transfers, walk call): snapped 4,890 s (81:30) rounds up to 82; the stub added 29 s, not 30
      (4,919 s), so it truncates to 81.
  The stub adds 30 s on 221 of 262 finite calls and 29 s on 41 (stock 9, shifted 8, walk 24; both releases):
  inside TTM the stub is not exactly 30 s, although run 3's check C4 (StreetRouter, base to tip) measured 30 s on
  every stub. Cause unread (Claude's hunch: R5's per-edge or split-point whole-second rounding). A 29-s stub only
  changes a minute when the snapped seconds end in :30, hence one mismatch.
  Reading (Claude's): the patch does what it claims (T1, T2 exact); the stubs' "exact per pair" holds on ~84% of
  calls, off by one second elsewhere, so the patch is the more exact mechanism for Q24 (3) (TRN-16 (5) is the
  user's call). Rounded - truncated: +1 min on 0.549 of finite calls.

Inputs (read only): `inputs/r5py/` jar and source; transit_q24_combined.py run 3's stub extracts, stub tables, origin
splits and stub routes, and the v2 range results, in diagnostics/diagnostic_data/; Google route tables in
outputs/transit_validation/. Writes jars to outputs/r5_patches/ and tables to diagnostics/diagnostic_data/. Self-
contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls; r5py only.
Usage: `python transit_r5_patch_seconds.py build`, `... draw`, `... route <variant> <release>`, `... score`.
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
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
GOOGLE_ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                       "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                       "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
STOCK_JAR_PATH = PROJECT_ROOT / "inputs" / "r5py" / "r5-v7.5.1-r5py-all.jar"
R5_SOURCE_DIR = PROJECT_ROOT / "inputs" / "r5py" / "r5-7.5.1" / "src" / "main" / "java"
PATCH_DIR = PROJECT_ROOT / "outputs" / "r5_patches"
JDK_BIN_DIR = Path(r"C:\Program Files\Java\jdk-21.0.12\bin")
CLASS_NAME = "com.conveyal.r5.analyst.TravelTimeReducer"
CLASS_FILE = CLASS_NAME.replace(".", "/")
RANGE_RESULTS_PATH = DIAGNOSTIC_DATA_DIR / "transit_pathway_network_v2_20261020_range_owndate_results.csv"
Q24_NAME = "transit_q24_combined_20261021"
STUB_BUILDS = {"20261009": "4135_4143_4160_b4", "20261016": "4135_4143_4160_b5"}   # run 3's final builds
V2_NAME = "transit_pathway_network_v2"
NAME = "transit_r5_patch_seconds"

# --- the patch -------------------------------------------------------------------------------------
PATCH_OLD = "            int timeMinutes = timeSeconds / FastRaptorWorker.SECONDS_PER_MINUTE;\n"
PATCH_NEW = ("            int timeMinutes = timeSeconds; // PLATICA TRN-16 P1: seconds out "
             "(was timeSeconds / FastRaptorWorker.SECONDS_PER_MINUTE); rounding in Python (SCR-10)\n")
VARIANTS = ["stock", "recompiled", "patched"]

# --- values copied from transit_q24_combined.py and the record -------------------------------------
R5_MAX_MEMORY = "7G"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
SPEED_TAG = "median"
SPEED_KMH = 4.143                              # Q24 (2) median (transit_q24_combined_20261021_speeds.json); user 2026-10-21
MAX_TIME_MIN = 90
BOARD_SLACK_MIN = 1
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
SPLIT_RADIUS_M = 1600
FIXED_DEGREES = 1e7
SECONDS_PER_MIN = 60
CALLS = ["stock", "shifted", "walk"]
CALL_CAPS_MIN = {"stock": MAX_TIME_MIN, "shifted": MAX_TIME_MIN + BOARD_SLACK_MIN, "walk": MAX_TIME_MIN}
ENDS = ["snap", "off"]                         # snapped destination (stub base), stub tip

# --- draw and rules ---------------------------------------------------------------------------------
DRAW_SEED = 20261021
STRATA = {"near_max": 10, "walk_only": 20, "one_boarding": 40, "transfers": 30}
NEAR_MAX_MIN = 3
MINOR_SHARE = 0.01
TIP_EXTRA_S = 30


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def jar_path(variant):
    return STOCK_JAR_PATH if variant == "stock" else PATCH_DIR / f"r5-v7.5.1-r5py-all_{NAME}_{variant}.jar"


def javap(classpath):
    out = subprocess.run([str(JDK_BIN_DIR / "javap"), "-c", "-p", "-cp", str(classpath), CLASS_NAME],
                         capture_output=True, text=True, check=True).stdout
    return out.splitlines()


# --- build -----------------------------------------------------------------------------------------
def build():
    source_path = R5_SOURCE_DIR / f"{CLASS_FILE}.java"
    source = source_path.read_text(encoding="utf-8")
    assert source.count(PATCH_OLD) == 1, "patch anchor not found exactly once"
    stock_javap = javap(STOCK_JAR_PATH)
    lines = [f"{NAME} {run_date()} build"]
    for variant, text in [("recompiled", source), ("patched", source.replace(PATCH_OLD, PATCH_NEW))]:
        variant_dir = PATCH_DIR / f"{NAME}_{variant}"
        src_path = variant_dir / "src" / f"{CLASS_FILE}.java"
        classes_dir = variant_dir / "classes"
        src_path.parent.mkdir(parents=True, exist_ok=True)
        classes_dir.mkdir(parents=True, exist_ok=True)
        src_path.write_text(text, encoding="utf-8", newline="\n")
        subprocess.run([str(JDK_BIN_DIR / "javac"), "--release", "21", "-proc:none", "-nowarn", "-cp", str(STOCK_JAR_PATH),
                        "-d", str(classes_dir), str(src_path)], check=True)
        compiled = sorted(p.relative_to(classes_dir).as_posix() for p in classes_dir.rglob("*.class"))
        assert compiled == [f"{CLASS_FILE}.class"], f"unexpected classes: {compiled}"
        diff = [line for line in difflib.unified_diff(stock_javap, javap(classes_dir), "jar", variant, n=0, lineterm="")
                if not line.startswith(("---", "+++"))]
        jar = jar_path(variant)
        shutil.copyfile(STOCK_JAR_PATH, jar)
        subprocess.run([str(JDK_BIN_DIR / "jar"), "uf", str(jar), "-C", str(classes_dir), f"{CLASS_FILE}.class"], check=True)
        jar_diff = [line for line in difflib.unified_diff(stock_javap, javap(jar), n=0, lineterm="")
                    if not line.startswith(("---", "+++"))]
        assert jar_diff == diff, f"{jar.name}: class in the jar differs from the compiled class"
        if variant == "recompiled":
            lines.append(f"(B1) recompiled vs the jar's class, javap -c -p: {'PASS' if not diff else 'FAIL'} "
                         f"({sum(line[0] in '+-' for line in diff)} differing lines)")
        else:
            lines.append("(B2) patched vs the jar's class, javap -c -p differing lines:")
            lines += [f"    {line}" for line in diff]
        lines.append(f"    jar {jar.relative_to(PROJECT_ROOT)}")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_build.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    assert "(B1) recompiled vs the jar's class, javap -c -p: PASS" in text, "B1 failed: stop"


# --- draw ------------------------------------------------------------------------------------------
def stub_routes():
    return pd.concat([pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{Q24_NAME}_stubroutes_full_{release}_{build_tag}.csv")
                      for release, build_tag in STUB_BUILDS.items()], ignore_index=True)


def draw():
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_pairs.csv"
    assert not list(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_pairs.csv")), "the set is drawn once: reuse it"
    routes_df = stub_routes()
    routes_df = routes_df[routes_df[f"is_offset_{SPEED_TAG}"].astype(bool)]
    google_df = pd.concat([pd.read_csv(path).assign(set_name=name) for name, path in GOOGLE_ROUTES_PATHS.items()])
    google_df = google_df[google_df.is_default.astype(bool)][["set_name", "draw_no", "n_transit_steps"]]
    df = routes_df.merge(google_df, on=["set_name", "draw_no"], how="left", validate="one_to_one")
    is_near = np.zeros(len(df), dtype=bool)
    for call, cap in CALL_CAPS_MIN.items():
        for end in ENDS:
            is_near |= (df[f"{call}_min_{SPEED_TAG}_{end}"] >= cap - NEAR_MAX_MIN).to_numpy()
    is_transit = (df[f"shifted_min_{SPEED_TAG}_snap"].fillna(np.inf) < df[f"walk_min_{SPEED_TAG}_snap"].fillna(np.inf)).to_numpy()
    steps = df.n_transit_steps.to_numpy()
    masks = {"near_max": is_near, "walk_only": ~is_near & ~is_transit,
             "one_boarding": ~is_near & is_transit & (steps == 1), "transfers": ~is_near & is_transit & (steps >= 2)}
    rng = np.random.default_rng(DRAW_SEED)
    picks = []
    for stratum, n in STRATA.items():
        pool = df[masks[stratum]].sort_values("draw_no")
        chosen = rng.choice(len(pool), size=n, replace=False)
        picks.append(pool.iloc[np.sort(chosen)].assign(stratum=stratum, pool_n=len(pool)))
        print(f"{stratum}: {n} of {len(pool)}")
    pairs_df = pd.read_csv(RANGE_RESULTS_PATH)[["draw_no", "own_date", "dep_min_of_day", "origin_lat", "origin_lon",
                                                 "dest_lat", "dest_lon"]]
    sample_df = pd.concat(picks)[["draw_no", "set_name", "release", "stratum", "pool_n", "n_transit_steps"]]
    sample_df = sample_df.merge(pairs_df, on="draw_no", how="left", validate="one_to_one")
    assert sample_df.own_date.notna().all() and sample_df.draw_no.is_unique
    sample_df.to_csv(out_path, index=False)
    print(f"{len(sample_df)} pairs -> {out_path.name}; per release {sample_df.release.value_counts().to_dict()}")


def sample_pairs():
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_pairs.csv"))
    assert paths, "draw first"
    return pd.read_csv(paths[-1])


# --- route -----------------------------------------------------------------------------------------
def network_paths(release):
    """The run-3 stub extract of a release and v2's uniquely named feeds (as transit_q24_combined.py)."""
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


def route(variant, release):
    assert variant in VARIANTS and release in STUB_BUILDS
    jar = jar_path(variant)
    assert jar.exists(), "build first"
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(jar)]   # r5py reads these at import
    import geopandas as gpd
    import jpype
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    location = str(jpype.JClass(CLASS_NAME).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
    assert Path(location.removeprefix("file:/")).resolve() == jar.resolve(), f"{CLASS_NAME} loaded from {location}"
    print(f"{CLASS_NAME} from {jar.name}", flush=True)

    pairs_df = sample_pairs()
    pairs_df = pairs_df[pairs_df.release.astype(str) == release]
    stubs_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{Q24_NAME}_stubs_{release}_{STUB_BUILDS[release]}.csv")
    stubs_df = stubs_df[(stubs_df.status == "ok") & (stubs_df.speed_tag == SPEED_TAG)]
    stub_of = {(s.dest_lat, s.dest_lon): s for s in stubs_df.itertuples()}
    origins_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{Q24_NAME}_originsplits_{release}.csv")
    origin_of = {(o.origin_lat, o.origin_lon): (o.split_lat, o.split_lon) for o in origins_df.itertuples()}
    pbf_path, gtfs = network_paths(release)
    check_working_copies([pbf_path] + gtfs)
    print(f"reusing {pbf_path.name} and {[p.name for p in gtfs]}", flush=True)
    network = TransportNetwork(pbf_path, gtfs)

    def ttm(origin, destinations, departure, transport_modes, max_time_min):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([origin[1]], [origin[0]]))
        targets = gpd.GeoDataFrame({"id": list(range(1, len(destinations) + 1))}, crs="EPSG:4326",
                                   geometry=gpd.points_from_xy([d[1] for d in destinations], [d[0] for d in destinations]))
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=targets, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=transport_modes, max_time=datetime.timedelta(minutes=max_time_min), speed_walking=SPEED_KMH))
        return matrix_df.sort_values("to_id")[f"travel_time_p{SINGLE_PERCENTILE}"].to_numpy(dtype=float)

    transit = [TransportMode.TRANSIT, TransportMode.WALK]
    rows = []
    started = datetime.datetime.now()
    for pair in pairs_df.itertuples():
        stub = stub_of[(pair.dest_lat, pair.dest_lon)]
        origin = origin_of[(pair.origin_lat, pair.origin_lon)]
        destinations = [(stub.base_lat, stub.base_lon), (stub.tip_lat, stub.tip_lon)]
        departure = (datetime.datetime.combine(datetime.date.fromisoformat(str(pair.own_date)), datetime.time())
                     + datetime.timedelta(minutes=int(pair.dep_min_of_day)))
        got = {"stock": ttm(origin, destinations, departure, transit, CALL_CAPS_MIN["stock"]),
               "shifted": ttm(origin, destinations, departure - datetime.timedelta(minutes=BOARD_SLACK_MIN), transit,
                              CALL_CAPS_MIN["shifted"]),
               "walk": ttm(origin, destinations, departure, [TransportMode.WALK], CALL_CAPS_MIN["walk"])}
        row = {"draw_no": pair.draw_no, "release": release, "variant": variant}
        for call, values in got.items():
            for end, value in zip(ENDS, values):
                row[f"{call}_{end}"] = value
        rows.append(row)
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
    return pd.concat(frames).set_index("draw_no").sort_index()


def value_columns():
    return [f"{call}_{end}" for call in CALLS for end in ENDS]


def equal(a_df, b_df):
    """Per value: equal, NaN = NaN."""
    a, b = a_df.to_numpy(dtype=float), b_df.to_numpy(dtype=float)
    return (a == b) | (np.isnan(a) & np.isnan(b))


def mismatch_lines(label, is_equal, a_df, b_df, strata):
    lines = []
    for i in np.flatnonzero(~is_equal.all(axis=1)):
        cols = [c for c, ok in zip(a_df.columns, is_equal[i]) if not ok]
        lines.append(f"    {label} draw {a_df.index[i]} ({strata.iloc[i]}): "
                     + ", ".join(f"{c} {a_df.iloc[i][c]} vs {b_df.iloc[i][c]}" for c in cols))
    return lines


def verdict(n_pairs_off, n_pairs, is_exact_rule=False):
    if n_pairs_off == 0:
        return "PASS"
    if is_exact_rule:
        return "FAIL"
    return "MINOR DEVIATION (flagged)" if n_pairs_off / n_pairs < MINOR_SHARE else "FAIL"


def score():
    pairs_df = sample_pairs().set_index("draw_no").sort_index()
    strata = pairs_df.stratum
    cols = value_columns()
    stock_df, recompiled_df, patched_df = (routed(v)[cols] for v in VARIANTS)
    assert list(stock_df.index) == list(pairs_df.index) == list(recompiled_df.index) == list(patched_df.index)
    n = len(pairs_df)
    lines = [f"{NAME} {run_date()} score: {n} pairs ({strata.value_counts().to_dict()}), speed {SPEED_KMH} km/h"]

    saved_df = stub_routes().set_index("draw_no").loc[pairs_df.index]
    saved_df = pd.DataFrame({f"{call}_{end}": saved_df[f"{call}_min_{SPEED_TAG}_{end}"] for call in CALLS for end in ENDS})
    is_eq = equal(stock_df, saved_df)
    off = int((~is_eq.all(axis=1)).sum())
    lines.append(f"(T0, reported) stock now vs saved run-3 stock: {off} pairs differ, {int((~is_eq).sum())} of {is_eq.size} values")
    lines += mismatch_lines("T0", is_eq, stock_df, saved_df, strata)

    is_eq = equal(recompiled_df, stock_df)
    off = int((~is_eq.all(axis=1)).sum())
    lines.append(f"(T1) recompiled = stock, exactly: {verdict(off, n, is_exact_rule=True)} ({off} pairs, "
                 f"{int((~is_eq).sum())} of {is_eq.size} values differ)")
    lines += mismatch_lines("T1", is_eq, recompiled_df, stock_df, strata)

    floor_df = np.floor(patched_df / SECONDS_PER_MIN)
    is_eq = equal(floor_df, stock_df)
    off = int((~is_eq.all(axis=1)).sum())
    lines.append(f"(T2) patched seconds // 60 = stock minutes: {verdict(off, n)} ({off} pairs, {int((~is_eq).sum())} of "
                 f"{is_eq.size} values differ; minor line {MINOR_SHARE:.0%} of pairs)")
    lines += mismatch_lines("T2", is_eq, floor_df, stock_df, strata)
    finite = patched_df.to_numpy(dtype=float)
    finite = finite[np.isfinite(finite)]
    lines.append(f"    patched values: {finite.size} finite, seconds {finite.min():.0f}-{finite.max():.0f}, "
                 f"whole seconds {bool(np.all(finite == np.round(finite)))}; NaN pattern = stock's "
                 f"{bool(np.array_equal(patched_df.isna().to_numpy(), stock_df.isna().to_numpy()))}")

    rounded_df = pd.DataFrame({call: np.floor(patched_df[f"{call}_snap"] / SECONDS_PER_MIN + 0.5) for call in CALLS})
    tip_df = pd.DataFrame({call: stock_df[f"{call}_off"] for call in CALLS})
    is_eq = equal(rounded_df, tip_df)
    off = int((~is_eq.all(axis=1)).sum())
    lines.append(f"(T3) round(patched snapped seconds / 60) vs stock stub-tip minutes: {verdict(off, n)} ({off} pairs, "
                 f"{int((~is_eq).sum())} of {is_eq.size} calls differ)")
    lines += mismatch_lines("T3", is_eq, rounded_df, tip_df, strata)
    extra = pd.concat([patched_df[f"{call}_off"] - patched_df[f"{call}_snap"] for call in CALLS]).dropna()
    lines.append(f"    patched tip - snapped seconds over finite calls: {extra.value_counts().sort_index().to_dict()} "
                 f"(n {len(extra)}; expected {TIP_EXTRA_S} on every call)")
    nan_tip_only = int(sum((patched_df[f"{c}_off"].isna() & patched_df[f"{c}_snap"].notna()).sum() for c in CALLS))
    lines.append(f"    calls finite at the snapped point but NaN at the tip (pushed past max_time): {nan_tip_only}")
    floor_moves = (np.floor(patched_df[[f"{c}_snap" for c in CALLS]].to_numpy() / SECONDS_PER_MIN + 0.5)
                   - np.floor(patched_df[[f"{c}_snap" for c in CALLS]].to_numpy() / SECONDS_PER_MIN))
    floor_moves = floor_moves[np.isfinite(floor_moves)]
    lines.append(f"    rounded - truncated minutes: +1 on {np.mean(floor_moves == 1):.3f} of {floor_moves.size} finite calls")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_score.txt").write_text(text + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    {"build": build, "draw": draw, "route": route, "score": score}[sys.argv[1]](*sys.argv[2:])
