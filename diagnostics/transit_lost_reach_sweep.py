"""Are the test's lost-reach-at-20 misses a departure-time knife edge? (TRN-15 result, stated limitation)

Claim (concepts/transit.md Limitations, TRN-15 result 2026-10-20): R5's lost-reach misses at 20 min are knife-edge
boardings: R5 reaches the boarding point ~1-2 min later than Google, misses the vehicle Google catches and waits
for the next one, so a small access gap turns into a 5-15 min late arrival. Where the pipeline relies on it: the
stated cost of the transit band model (no-wait plain, v2 pathways) behind transit bands 1-2 (SCR-1, RCH-1).

Method (Claude's, exploratory, run after the test was opened; not a verdict): the 11 pooled lost-20 misses of
transit_test_score.py test (Google default 13-17 min, R5 21-32). Each pair re-routed on its own date and release's
v2 network (r5py TravelTimeMatrix, transit + walk, 1-min window, 4.16 km/h, max 90 min) at departures from 5 min
before to 2 min after Google's requested minute t; arrival from t = offset + travel time. The no-wait model already
reads departures from t - 1.

Conclusion (run 2026-10-20; "caught" = arrival from t <= Google's default or the cut): leaving 1 min early catches
it on 1 of 11 (at the cut, 20 min); 2 min early on 7 (arrivals 15-18 vs Google 15-17), 3 min early on 10, 5 min
early on all 11. Not departure-minute noise: R5 is ~1-2 min slower
to the boarding (consistent with R5's 1.14x access walk, TRN-13), then waits for the next vehicle.

Inputs (read only): transit_test_score_*_test_misses.csv, the test pair files, Google's departure dates, v2's
derived OSM extracts and uniquely named feeds. Self-contained (CLAUDE.md D1). No API calls.
Usage: `python transit_lost_reach_sweep.py 20261009`, then `... 20261016` (one network per process), then
`... report`. Saved sweeps are reused when present.
"""
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_lost_reach_sweep"
SCORE_NAME = "transit_test_score"
V2_NAME = "transit_pathway_network_v2"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATHS = {"test": SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv",
               "test_ext": SUBJECT_DIR / f"transit_pairs_test_ext_{FILE_TAG}.csv"}
GOOGLE_PATHS = {"test": SUBJECT_DIR / f"transit_google_{FILE_TAG}.csv",            # departure_local: the date only
                "test_ext": SUBJECT_DIR / f"transit_google_test_ext_20261016_{FILE_TAG}.csv"}
SET_RELEASE = {"test": "20261009", "test_ext": "20261016"}
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
MISS_TEST = "lost 20"
POOLED = "pooled"
R5_MAX_MEMORY = "7G"
WINDOW_MIN = 1
MAX_TIME_MIN = 90
SINGLE_PERCENTILE = 49
WALK_SPEED_KMH = 4.16
OFFSETS_MIN = range(-5, 3)


def misses():
    path = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{SCORE_NAME}_2*_test_misses.csv"))[-1]
    misses_df = pd.read_csv(path)
    return misses_df[(misses_df.subset == POOLED) & (misses_df.test == MISS_TEST)]


def gtfs_paths(release):
    feed_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{release}"
    return [feed_dir / (f"{TRAIN_FEED}_{V2_NAME}_{release}_moved.zip" if name == TRAIN_FEED else f"{name}_{V2_NAME}_{release}.zip")
            for name in FEED_NAMES]


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (memory: r5py-working-copy-cache)."""
    from r5py.util.config import Config
    for path in paths:
        cached = Path(Config().CACHE_DIR) / Path(path).name
        if cached.exists():
            digests = [hashlib.file_digest(open(candidate, "rb"), "blake2s").hexdigest() for candidate in (path, cached)]
            assert digests[0] == digests[1], f"stale r5py working copy {cached}"


def sweep(release):
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_sweep_{release}.csv"))
    if saved:
        print(f"saved sweep {saved[-1].name} exists ({datetime.date.fromtimestamp(saved[-1].stat().st_mtime)}); reused")
        return
    set_name = [name for name, set_release in SET_RELEASE.items() if set_release == release][0]
    pairs_df = pd.read_csv(PAIRS_PATHS[set_name]).merge(misses()[["draw_no"]], on="draw_no")
    dates_df = pd.read_csv(GOOGLE_PATHS[set_name], usecols=["draw_no", "departure_local"])
    pairs_df = pairs_df.merge(dates_df, on="draw_no")
    sys.argv += ["--max-memory", R5_MAX_MEMORY]
    import geopandas as gpd
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    pbf_path = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{release}.osm.pbf"
    check_working_copies([pbf_path] + gtfs_paths(release))
    network = TransportNetwork(pbf_path, gtfs_paths(release))
    rows = []
    for pair in pairs_df.itertuples():
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.origin_lon], [pair.origin_lat]))
        destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
        own_date = datetime.date.fromisoformat(pair.departure_local[:10])
        requested = datetime.datetime.combine(own_date, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))
        for offset_min in OFFSETS_MIN:
            matrix_df = pd.DataFrame(TravelTimeMatrix(
                network, origins=origins, destinations=destinations, departure=requested + datetime.timedelta(minutes=offset_min),
                departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
                transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=datetime.timedelta(minutes=MAX_TIME_MIN),
                speed_walking=WALK_SPEED_KMH))
            rows.append({"draw_no": pair.draw_no, "offset_min": offset_min,
                         "travel_min": matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]})
    out_df = pd.DataFrame(rows)
    out_df["arrival_from_t"] = out_df.offset_min + out_df.travel_min
    out_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_sweep_{release}.csv", index=False)


def report():
    sweep_df = pd.concat([pd.read_csv(sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_sweep_{release}.csv"))[-1])
                          for release in SET_RELEASE.values()], ignore_index=True)
    sweep_df = sweep_df.merge(misses()[["draw_no", "default_min"]], on="draw_no")
    lines = [f"{NAME} {datetime.date.today():%Y%m%d}: {sweep_df.draw_no.nunique()} lost-20 misses, arrival from t by departure offset",
             sweep_df.pivot(index="draw_no", columns="offset_min", values="arrival_from_t").to_string()]
    for offset_min in sorted(OFFSETS_MIN):
        caught = sweep_df[(sweep_df.offset_min == offset_min) & (sweep_df.arrival_from_t <= np.maximum(sweep_df.default_min, 20))]
        lines.append(f"leaving {offset_min:+d} min: R5 arrives by Google's default (or the cut) on {caught.draw_no.nunique()}")
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_summary.txt").write_text(summary + "\n", encoding="utf-8")


if __name__ == "__main__":
    report() if sys.argv[1] == "report" else sweep(sys.argv[1])
