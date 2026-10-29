"""How much does TravelTimeMatrix's departure window change the transit time compared with Google?

Claim under test (concepts/transit.md T7 (e), TRN-6; DESIGN.md Q22): the window TravelTimeMatrix (TTM)
uses when validating against Google's single departure can follow r5py's 10-min default instead of the
configured 1 min (config TRANSIT_VALIDATION_WINDOW_MIN) at little cost to the output. Not a pass/fail
check: it measures the cost of each choice (2026-10-17, user chose to measure before deciding):
  t1        TTM at a 1-min window from the pair's departure minute t: the trip at Google's minute;
  start10   TTM median over a 10-min window from t (r5py's default window, starting at the request);
  centred10 TTM median over a 10-min window from t - 5 min (centred on Google's minute).
Reported per pair: each time (whole minutes, TTM truncates), its band (scoring.md SCR-1: <= 10 min,
<= 20 min), the 10-min window's spread (p99 - p1, a frequency proxy: large where service is sparse).
Summary: differences to t1 (mean, mean absolute, largest), and pairs whose band changes.
Where the pipeline relies on it: TRN-6 validation reads r5py's time at Google's departure from TTM.

Pairs: N_PAIRS exploration pairs (seeded), each at its drawn minute of day on WINDOW_DATE, a Wednesday
inside the 2026-10-09 release. One-to-one TTM calls, max_time MAX_TIME_MIN.

Conclusion (runs 2026-10-17): run 1 (20 pairs, max_time 40) was too thin: 10 pairs unreached at their
drawn minute. Run 2 (100 pairs, max_time 90; 99 reached by all three), differences to t1 in minutes:
start10 mean -0.31, mean abs 2.84, range -5 to +12, within 1 min on 33 of 99; 18 pairs at exactly -5
(the median sits ~5 min into the window: same trip, less initial wait). centred10 mean -0.31, mean abs
1.77, range -7 to +4, within 1 min on 50 of 99. Band changes vs t1: 3 (start10), 2 (centred10). Error
grows with the window's spread (start10 mean abs 0.7 / 2.7 / 4.1 for spreads < 5, 5-10, >= 10 min).
A 10-min window is not a stand-in for the trip at Google's minute; the centred one roughly halves the
error. r5py itself warns at every 1-min call ("below 5 minutes ... may cause adverse effects with
routing"); 1-min soundness is not tested here.

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release), the
OSM extract in frozen_inputs/osm_extract/, the transit pair draw and split in outputs/transit_validation/.
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls; r5py
only (a few minutes). The per-pair table is saved data: a rerun reuses the newest one and says so.
Results carry the run date; a same-day rerun replaces that day's results.
"""
import datetime
import sys
from pathlib import Path

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
GTFS_CLEANED_DIR = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_window_width_checks"
RUN_TAG_FORMAT = "n{n_pairs}_max{max_time_min}"  # saved data per sample size and max_time

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "4G"                           # config.TRANSIT_DRAW_R5_MAX_MEMORY
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
VALIDATION_WINDOW_MIN = 1                      # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # above config.TRANSIT_WINDOW_S / 60 (40): drawn minutes often exceed it (run 1: 10 of 20 unreached)
BAND_EDGES_MIN = [10, 20]                      # scoring.md SCR-1 transit bands 1 and 2

# --- the run ---------------------------------------------------------------------------------------
N_PAIRS = 100                                  # run 1 (2026-10-17): 20 pairs, max_time 40, saved before the tag (files without one)
SEED = 20261017
DEFAULT_WINDOW_MIN = 10                        # r5py's default departure_time_window
CENTRE_OFFSET_MIN = DEFAULT_WINDOW_MIN // 2    # the centred window starts this much before t
PERCENTILES = [1, 50, 99]                      # median compared; p99 - p1 is the spread
NO_BAND = 0                                    # band label for times past the last band edge or unreached

sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from r5py import TransportMode, TransportNetwork, TravelTimeMatrix  # noqa: E402


def points_gdf(ids, lats, lons):
    """r5py origins or destinations: an id column and point geometry."""
    return gpd.GeoDataFrame({"id": np.asarray(ids)}, crs="EPSG:4326", geometry=gpd.points_from_xy(lons, lats))


def exploration_pairs_df():
    """Exploration pairs (training half, fetched first), with their drawn departure minute."""
    pairs_df = pd.read_csv(PAIRS_PATH)
    split_df = pd.read_csv(SPLIT_PATH)
    exploration_draws = split_df.loc[split_df.is_exploration, "draw_no"]
    return pairs_df[pairs_df.draw_no.isin(exploration_draws)].reset_index(drop=True)


def ttm_percentiles(network, pair, departure, window_min):
    """One-to-one TTM: {percentile: whole minutes or NaN} for one pair, departure and window."""
    origin = points_gdf([0], [pair.origin_lat], [pair.origin_lon])
    destination = points_gdf([1], [pair.dest_lat], [pair.dest_lon])    # ids disjoint: r5py gives 0 where equal
    matrix_df = pd.DataFrame(TravelTimeMatrix(
        network, origins=origin, destinations=destination, departure=departure,
        departure_time_window=datetime.timedelta(minutes=window_min), percentiles=PERCENTILES,
        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
        max_time=datetime.timedelta(minutes=MAX_TIME_MIN)))
    return {p: matrix_df[f"travel_time_p{p}"].iloc[0] for p in PERCENTILES}


def check_one_pair(network, pair):
    """The three windows' times for one pair, plus the default window's spread."""
    departure = datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(
        minutes=int(pair.dep_min_of_day))
    t1 = ttm_percentiles(network, pair, departure, VALIDATION_WINDOW_MIN)
    start10 = ttm_percentiles(network, pair, departure, DEFAULT_WINDOW_MIN)
    centred10 = ttm_percentiles(network, pair, departure - datetime.timedelta(minutes=CENTRE_OFFSET_MIN),
                                DEFAULT_WINDOW_MIN)
    row = {"draw_no": pair.draw_no, "haversine_m": round(pair.haversine_m), "departure": departure,
           "t1_min": t1[50], "start10_min": start10[50], "centred10_min": centred10[50],
           "start10_spread_min": start10[99] - start10[1], "centred10_spread_min": centred10[99] - centred10[1]}
    print(f"  {row}", flush=True)
    return row


def band(minutes):
    """SCR-1 transit band of a TTM time (1, 2, or NO_BAND past the last edge or unreached)."""
    bands = pd.Series(NO_BAND, index=minutes.index)
    for band_no, edge_min in reversed(list(enumerate(BAND_EDGES_MIN, start=1))):
        bands[minutes <= edge_min] = band_no
    return bands


def main():
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_date = datetime.date.today().strftime("%Y%m%d")
    run_tag = RUN_TAG_FORMAT.format(n_pairs=N_PAIRS, max_time_min=MAX_TIME_MIN)
    saved_pairs = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_{run_tag}_pairs.csv"))
    if saved_pairs:
        print(f"reusing saved table {saved_pairs[-1].name}")
        checks_df = pd.read_csv(saved_pairs[-1])
    else:
        network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        sample_df = exploration_pairs_df().sample(N_PAIRS, random_state=SEED)
        checks_df = pd.DataFrame([check_one_pair(network, pair) for pair in sample_df.itertuples()])
        checks_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_{run_tag}_pairs.csv", index=False)

    lines = [f"{NAME} {run_date} {run_tag}: {len(checks_df)} pairs; TTM times in whole minutes, max_time {MAX_TIME_MIN}"]
    for col in ["t1_min", "start10_min", "centred10_min"]:
        checks_df[col.replace("_min", "_band")] = band(checks_df[col])
    for col in ["start10_min", "centred10_min"]:
        is_both = checks_df[["t1_min", col]].notna().all(axis=1)
        diff = (checks_df[col] - checks_df.t1_min)[is_both]
        reach_mismatch = int((checks_df[col].notna() != checks_df.t1_min.notna()).sum())
        band_changes = int((checks_df[col.replace("_min", "_band")] != checks_df.t1_band).sum())
        lines.append(f"{col} - t1_min on {int(is_both.sum())} pairs reached by both: mean {diff.mean():+.2f}, "
                     f"mean abs {diff.abs().mean():.2f}, largest {diff.min():+.0f} / {diff.max():+.0f}; "
                     f"reached by one only: {reach_mismatch}; band changes vs t1: {band_changes}")
    lines.append(checks_df.drop(columns=["departure"]).to_string(index=False))
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_{run_tag}_summary.txt").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()
