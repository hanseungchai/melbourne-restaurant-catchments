"""R5's transfer walk vs Google's listed transfer walk, on Google's own transfers (TRN-16 patch 3 check).

Claim under test (diagnostics/transit_r5_patch_board_wait.py; transit_google_transfer_buffer.py): R5 patch 3 copies
Google's transfer rule (listed walk + ~200 s) only if R5's walk between the two stops is close to Google's listed walk.
Where they differ, the gap belongs to the walk model (speed, path, station time), not to the buffer (user, 2026-10-21).
Where the pipeline would rely on it: patch 3's 200 s in the model of record (transit bands 1-2).

Data: every transfer in Google's training routes (first batch train half, second batch, top-up; all routes), with
Google's alighting stop and next boarding stop locations (stopDetails), its listed walk between them (walk_s, all walk
steps; fixed_s, the steps without a distance) and the release of the pair's window.
R5: walk-only TravelTimeMatrix per release, origins = unique alighting stops, destinations = unique boarding stops, on
run 3's stub extract of that release (as transit_r5_patch_board_wait.py; points are split onto streets by R5),
4.143 km/h, patch 1's seconds jar (walk times in whole seconds), max_time MAX_TIME_MIN. A point-to-point walk between
the stop coordinates stands in for R5's stop-to-stop transfer (TransferFinder links the stop vertices the same way, but
not checked here).

Quantities (Claude's, set before any result): diff_s = R5 walk - Google listed walk_s, per transfer; also against the
listed distance steps only (walk_s - fixed_s). Reported by rail / no rail, same stop name, and Google's walk_m bins:
n, mean, median, p10, p90, mean absolute; share with |diff| <= 30 s and <= 60 s; and the implied effect on patch 3:
R5's connection floor (R5 walk + 200 s) minus Google's (listed walk + 200 s) = diff_s. No verdict: this sizes the walk
term (the next decision is the user's).

Conclusion (run 2026-10-21): 8,159 transfers (4,158 stop pairs), R5 reached all. diff_s = R5 walk - Google listed
  walk: mean +13.2 s, median +9 s, p10 -47, p90 +86, mean abs 43.5; |diff| <= 30 s on 54%, <= 60 s on 76% (default routes
  alike: median +9, mean abs 44.9). No rail: median +7, p10 -29, p90 +73, 83% within 60 s. Rail: median +11, p10 -82,
  p90 +106, 63% within 60 s. No walk listed (574): +2 s median. By walk_m the median grows slowly (+4 to +36 s up to
  800 m); the 30 transfers over 800 m are noisy (mean -206). Against the distance steps only (Google's fixed steps left
  out) R5 is +16 s median: R5's point-to-point walk covers about what Google lists including its station steps.
  Reading (Claude's): R5's transfer walk matches Google's listed walk with a small late bias (~10 s median) and +-45 s
  scatter, wider at rail. So under patch 3 R5's connection floor sits about 10 s later than Google's on a typical
  transfer: second-order next to the 140 s the patch adds, and in the walk model, not the buffer. Point-to-point TTM
  stands in for R5's stop-to-stop transfer (not checked).

Inputs (read only): Google raw responses in outputs/transit_validation/; run 3's stub extracts and v2 feeds in
diagnostics/diagnostic_data/; patch 1's jar in outputs/r5_patches/. Writes diagnostics/diagnostic_data/
transit_r5_transfer_walk_<date>_{transfers.csv,r5_<release>.csv,summary.txt}. Self-contained (CLAUDE.md D1).
No paid API calls. Usage: `python transit_r5_transfer_walk.py extract`, `... route <release>`, `... score`.
"""
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
RAW_PATHS = {"first_batch": SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl",
             "second_batch": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.raw.jsonl",
             "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.raw.jsonl"}
FIRST_BATCH = "first_batch"
TRAIN_HALF = "train"
JAR_PATH = PROJECT_ROOT / "outputs" / "r5_patches" / "r5-v7.5.1-r5py-all_transit_r5_patch_seconds_patched.jar"
REDUCER_CLASS_NAME = "com.conveyal.r5.analyst.TravelTimeReducer"
Q24_NAME = "transit_q24_combined_20261021"
STUB_BUILDS = {"20261009": "4135_4143_4160_b4", "20261016": "4135_4143_4160_b5"}   # run 3's final builds
V2_NAME = "transit_pathway_network_v2"
NAME = "transit_r5_transfer_walk"

R5_MAX_MEMORY = "7G"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
SPEED_KMH = 4.143                              # Q24 (2) median; user 2026-10-21
MAX_TIME_MIN = 60
WALK_DEPARTURE = datetime.datetime(2026, 10, 21, 8, 0)   # any time: walk-only times do not depend on it
COORD_DECIMALS = 7
MODE_TRANSIT = "TRANSIT"
RAIL_TYPE = "HEAVY_RAIL"
TRANSFER_BUFFER_S = 200
WALK_M_BINS = [-1, 0, 50, 100, 200, 300, 500, 800, 3000]
CLOSE_S = [30, 60]


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def seconds(text):
    return float(text.rstrip("s"))


def latest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    assert paths, f"missing {pattern}"
    return paths[-1]


# --- extract ---------------------------------------------------------------------------------------
def extract():
    split_df = pd.read_csv(SPLIT_PATH)
    train_draws = set(split_df.loc[split_df["half"] == TRAIN_HALF, "draw_no"])
    rows = []
    for set_name, path in RAW_PATHS.items():
        for line in open(path, encoding="utf-8"):
            rec = json.loads(line)
            if set_name == FIRST_BATCH and rec["draw_no"] not in train_draws:
                continue
            for route_ix, route in enumerate(rec.get("resp", {}).get("routes", [])):
                steps = [s for leg in route["legs"] for s in leg.get("steps", [])]
                rides = [i for i, s in enumerate(steps) if s["travelMode"] == MODE_TRANSIT]
                for a, b in zip(rides, rides[1:]):
                    between = steps[a + 1:b]
                    arrive = steps[a]["transitDetails"]["stopDetails"]
                    depart = steps[b]["transitDetails"]["stopDetails"]
                    a_ll = arrive["arrivalStop"]["location"]["latLng"]
                    b_ll = depart["departureStop"]["location"]["latLng"]
                    rows.append({
                        "set_name": set_name, "draw_no": rec["draw_no"], "release": str(rec["window_release"]),
                        "route_ix": route_ix, "is_default": "DEFAULT_ROUTE" in route.get("routeLabels", []),
                        "from_type": steps[a]["transitDetails"]["transitLine"]["vehicle"]["type"],
                        "to_type": steps[b]["transitDetails"]["transitLine"]["vehicle"]["type"],
                        "is_same_stop_name": arrive["arrivalStop"]["name"] == depart["departureStop"]["name"],
                        "a_lat": round(a_ll["latitude"], COORD_DECIMALS), "a_lon": round(a_ll["longitude"], COORD_DECIMALS),
                        "b_lat": round(b_ll["latitude"], COORD_DECIMALS), "b_lon": round(b_ll["longitude"], COORD_DECIMALS),
                        "walk_s": sum(seconds(s.get("staticDuration", "0s")) for s in between),
                        "fixed_s": sum(seconds(s.get("staticDuration", "0s")) for s in between if "distanceMeters" not in s),
                        "walk_m": sum(s.get("distanceMeters", 0) for s in between)})
    df = pd.DataFrame(rows)
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_transfers.csv"
    df.to_csv(out_path, index=False)
    print(f"{len(df)} transfers, {df[['release', 'a_lat', 'a_lon', 'b_lat', 'b_lon']].drop_duplicates().shape[0]} "
          f"unique stop pairs, per release {df.release.value_counts().to_dict()} -> {out_path.name}")


# --- route -----------------------------------------------------------------------------------------
def network_paths(release):
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


def route(release):
    assert release in STUB_BUILDS
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(JAR_PATH)]   # r5py reads these at import
    import geopandas as gpd
    import jpype
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    location = str(jpype.JClass(REDUCER_CLASS_NAME).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
    assert Path(location.removeprefix("file:/")).resolve() == JAR_PATH.resolve(), f"loaded from {location}"

    df = pd.read_csv(latest(f"{NAME}_2*_transfers.csv"), dtype={"release": str})
    df = df[df.release == release]
    origins_df = df[["a_lat", "a_lon"]].drop_duplicates().reset_index(drop=True)
    targets_df = df[["b_lat", "b_lon"]].drop_duplicates().reset_index(drop=True)
    pbf_path, gtfs = network_paths(release)
    check_working_copies([pbf_path] + gtfs)
    network = TransportNetwork(pbf_path, gtfs)
    origins = gpd.GeoDataFrame({"id": origins_df.index}, crs="EPSG:4326",
                               geometry=gpd.points_from_xy(origins_df.a_lon, origins_df.a_lat))
    targets = gpd.GeoDataFrame({"id": targets_df.index}, crs="EPSG:4326",
                               geometry=gpd.points_from_xy(targets_df.b_lon, targets_df.b_lat))
    started = datetime.datetime.now()
    matrix_df = pd.DataFrame(TravelTimeMatrix(
        network, origins=origins, destinations=targets, departure=WALK_DEPARTURE,
        transport_modes=[TransportMode.WALK], max_time=datetime.timedelta(minutes=MAX_TIME_MIN), speed_walking=SPEED_KMH))
    matrix_df = matrix_df.merge(origins_df, left_on="from_id", right_index=True).merge(targets_df, left_on="to_id",
                                                                                      right_index=True)
    needed_df = df[["a_lat", "a_lon", "b_lat", "b_lon"]].drop_duplicates()
    out_df = needed_df.merge(matrix_df[["a_lat", "a_lon", "b_lat", "b_lon", "travel_time"]], how="left",
                             on=["a_lat", "a_lon", "b_lat", "b_lon"], validate="one_to_one")
    out_df = out_df.rename(columns={"travel_time": "r5_walk_s"}).assign(release=release)
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_r5_{release}.csv"
    out_df.to_csv(out_path, index=False)
    print(f"{release}: {len(origins_df)} x {len(targets_df)} in {datetime.datetime.now() - started}; {len(out_df)} pairs, "
          f"{int(out_df.r5_walk_s.isna().sum())} unreached -> {out_path.name}", flush=True)


# --- score -----------------------------------------------------------------------------------------
def stats(diff):
    diff = diff.dropna()
    row = {"n": len(diff), "mean_s": diff.mean(), "median_s": diff.median(), "p10_s": diff.quantile(.1),
           "p90_s": diff.quantile(.9), "mean_abs_s": diff.abs().mean()}
    row.update({f"share_abs_le_{c}": (diff.abs() <= c).mean() for c in CLOSE_S})
    return pd.Series(row)


def score():
    df = pd.read_csv(latest(f"{NAME}_2*_transfers.csv"), dtype={"release": str})
    r5_df = pd.concat([pd.read_csv(latest(f"{NAME}_2*_r5_{r}.csv"), dtype={"release": str}) for r in STUB_BUILDS])
    df = df.merge(r5_df, on=["release", "a_lat", "a_lon", "b_lat", "b_lon"], how="left", validate="many_to_one")
    df["diff_s"] = df.r5_walk_s - df.walk_s
    df["diff_dist_s"] = df.r5_walk_s - (df.walk_s - df.fixed_s)
    df["group"] = np.where((df.from_type == RAIL_TYPE) | (df.to_type == RAIL_TYPE), "rail", "no rail")
    lines = [f"{NAME} {run_date()}: {len(df)} transfers, R5 unreached {int(df.r5_walk_s.isna().sum())}, "
             f"speed {SPEED_KMH} km/h; diff = R5 walk - Google listed walk (s) = R5 floor - Google floor under patch 3"]
    lines.append("all transfers:\n" + pd.DataFrame({"diff_s": stats(df.diff_s), "diff_dist_s": stats(df.diff_dist_s)})
                 .round(3).to_string())
    for label, key in [("by rail", "group"), ("by same stop name", "is_same_stop_name"),
                       ("by Google walk_m", pd.cut(df.walk_m, WALK_M_BINS))]:
        lines.append(f"diff_s {label}:\n" + df.groupby(key, observed=True).diff_s.apply(stats).unstack().round(3).to_string())
    lines.append("diff_s, default routes only:\n" + stats(df[df.is_default].diff_s).round(3).to_string())
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_scored.csv", index=False)


if __name__ == "__main__":
    {"extract": extract, "route": route, "score": score}[sys.argv[1]](*sys.argv[2:])
