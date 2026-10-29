"""Are TravelTimeMatrix times at a 1-min departure window sound?

Claim under test (concepts/transit.md T7 (e), TRN-6; DESIGN.md Q22): TravelTimeMatrix (TTM) at a 1-min
window (config TRANSIT_VALIDATION_WINDOW_MIN) gives the same time as R5's range search over a wide
window gives for that minute. Doubt: r5py warns at every window below 5 min ("may cause adverse effects
with routing"); r5py issue #292 (an R5 developer: windows near or below headways give "weird paths").
Chosen 2026-10-17 (user) over a 10-min window, which costs ~1.8 min mean abs at Google's minute
(diagnostics/transit_window_width_checks.py).

Method: r5py can't return one minute's time from a wide window, only percentiles, so sorted lists are
compared. Per pair, WIDE_WINDOW_MIN 1-min TTM calls at minutes t, t+1, ..., sorted, vs the same
minutes' times from one wide-window TTM at t, recovered rank by rank through percentiles: R5 picks rank
ceil(p / 100 * n) - 1 of the n per-minute times (TravelTimeReducer.findPercentileIndex, read from the
r5-v7.5.1-r5py jar's bytecode 2026-10-17), so p = floor(k * 100 / n) + 1 hits rank k; r5py allows 5
percentiles per call (regional_task.py), so a pair takes n / 5 wide calls. Our GTFS has no
frequencies.txt, so both sides are deterministic. Equal sorted lists don't prove every minute is equal,
but an error that exactly reshuffles the minutes is unlikely (cost of the method, recorded).
Rule (set before the first run, 2026-10-17): SOUND if, on every pair, both sides reach the same number
of minutes within max_time and every rank reached by both agrees within TOLERANCE_MIN; else NOT SOUND,
with the failing pairs and ranks shown. Exact agreement is reported alongside.

Pairs: N_CANDIDATES exploration pairs (seeded), each from its drawn minute of day t on WINDOW_DATE. The
wide window runs on all candidates; the N_PAIRS_EACH with the largest spread of per-minute times
(sparse service, where narrow windows are doubted) and the N_PAIRS_EACH with the smallest are checked.
Where the pipeline relies on it: TRN-6 validation reads r5py's time at Google's departure minute from
TTM at a 1-min window.

Conclusion (run 2026-10-17): SOUND. 10 pairs x 60 minutes, 594 of 600 ranks exact, none over the
tolerance; the 6 others (all on draw 13556, a small-spread pair) differ by 1 min. Every large-spread pair
(per-minute times spanning 19-26 min, sparse service) matches exactly. Reached counts equal on every pair.
r5py's under-5-minute warning shows no effect on travel times here; it says nothing about the paths
(legs) a narrow window returns, which TTM doesn't report.

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release), the
OSM extract in frozen_inputs/osm_extract/, the transit pair draw and split in outputs/transit_validation/.
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls; r5py
only (~15 min). The wide and narrow tables are saved data: a rerun reuses the newest ones and says so.
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
NAME = "transit_narrow_window_soundness"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "4G"                           # config.TRANSIT_DRAW_R5_MAX_MEMORY
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
NARROW_WINDOW_MIN = 1                          # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as transit_window_width_checks run 2: drawn minutes exceed 40

# --- the run ---------------------------------------------------------------------------------------
N_CANDIDATES = 40
N_PAIRS_EACH = 5                               # largest and smallest spread
SEED = 20261018
WIDE_WINDOW_MIN = 60                           # minutes compared per pair; n per-minute times in the wide window
PERCENTILES_PER_CALL = 5                       # r5py's limit (R5's)
TOLERANCE_MIN = 1
PERCENT = 100

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


def rank_percentiles(n_times):
    """For each rank k of n_times sorted values, the smallest whole percentile R5 maps to it
    (rank = ceil(p / 100 * n) - 1)."""
    return [k * PERCENT // n_times + 1 for k in range(n_times)]


def ttm_minutes(network, pair, departure, window_min, percentiles):
    """One-to-one TTM: whole minutes (NaN if unreached) for each percentile."""
    origin = points_gdf([0], [pair.origin_lat], [pair.origin_lon])
    destination = points_gdf([1], [pair.dest_lat], [pair.dest_lon])    # ids disjoint: r5py gives 0 where equal
    matrix_df = pd.DataFrame(TravelTimeMatrix(
        network, origins=origin, destinations=destination, departure=departure,
        departure_time_window=datetime.timedelta(minutes=window_min), percentiles=percentiles,
        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
        max_time=datetime.timedelta(minutes=MAX_TIME_MIN)))
    column = "travel_time" if percentiles == [50] else None              # r5py renames a lone p50
    return [matrix_df[column or f"travel_time_p{p}"].iloc[0] for p in percentiles]


def pair_departure(pair):
    return datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))


def wide_ranks(network, pair):
    """The wide window's per-minute times in rank order (NaN = unreached), via percentiles."""
    percentiles = rank_percentiles(WIDE_WINDOW_MIN)
    ranks = []
    for start in range(0, len(percentiles), PERCENTILES_PER_CALL):
        ranks += ttm_minutes(network, pair, pair_departure(pair), WIDE_WINDOW_MIN,
                             percentiles[start:start + PERCENTILES_PER_CALL])
    return ranks


def narrow_minutes(network, pair):
    """1-min-window times at each minute of the wide window (NaN = unreached)."""
    return [ttm_minutes(network, pair, pair_departure(pair) + datetime.timedelta(minutes=minute),
                        NARROW_WINDOW_MIN, [PERCENT // 2 - 1])[0]               # any one percentile but 50
            for minute in range(WIDE_WINDOW_MIN)]


def compare(wide_df, narrow_df):
    """Per pair: reached counts, ranks compared, largest gap, exact ranks, verdict inputs."""
    rows = []
    for draw_no, narrow in narrow_df.groupby("draw_no"):
        narrow_sorted = np.sort(narrow.travel_min.to_numpy())                    # NaN sorts last, as unreached
        wide = wide_df[wide_df.draw_no == draw_no].sort_values("rank").travel_min.to_numpy()
        is_both = ~np.isnan(narrow_sorted) & ~np.isnan(wide)
        gaps = np.abs(narrow_sorted - wide)[is_both]
        rows.append({"draw_no": draw_no, "stratum": narrow.stratum.iloc[0],
                     "narrow_reached": int((~np.isnan(narrow_sorted)).sum()), "wide_reached": int((~np.isnan(wide)).sum()),
                     "ranks_compared": int(is_both.sum()), "ranks_exact": int((gaps == 0).sum()),
                     "ranks_over_tolerance": int((gaps > TOLERANCE_MIN).sum()),
                     "largest_gap_min": gaps.max() if len(gaps) else np.nan,
                     "narrow_min": np.nanmin(narrow_sorted), "narrow_max": np.nanmax(narrow_sorted),
                     "wide_min": np.nanmin(wide), "wide_max": np.nanmax(wide)})
    return pd.DataFrame(rows)


def main():
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_date = datetime.date.today().strftime("%Y%m%d")
    saved_wide = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_wide.csv"))
    saved_narrow = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_narrow.csv"))
    if saved_wide and saved_narrow:
        print(f"reusing saved tables {saved_wide[-1].name}, {saved_narrow[-1].name}")
        wide_df, narrow_df = pd.read_csv(saved_wide[-1]), pd.read_csv(saved_narrow[-1])
    else:
        network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        candidates_df = exploration_pairs_df().sample(N_CANDIDATES, random_state=SEED)
        wide_rows = []
        for pair in candidates_df.itertuples():
            ranks = wide_ranks(network, pair)
            wide_rows += [{"draw_no": pair.draw_no, "rank": k, "travel_min": value} for k, value in enumerate(ranks)]
            print(f"  wide {pair.draw_no}: {np.nanmin(ranks) if not np.all(np.isnan(ranks)) else 'unreached'}"
                  f" .. {np.nanmax(ranks) if not np.all(np.isnan(ranks)) else ''}", flush=True)
        wide_df = pd.DataFrame(wide_rows)
        spread = wide_df.groupby("draw_no").travel_min.agg(lambda times: times.max() - times.min()).dropna()
        spread = spread[wide_df.groupby("draw_no").travel_min.count() > 0].sort_values()
        strata = {**{d: "small_spread" for d in spread.index[:N_PAIRS_EACH]},
                  **{d: "large_spread" for d in spread.index[-N_PAIRS_EACH:]}}
        wide_df = wide_df[wide_df.draw_no.isin(strata)].assign(stratum=lambda df: df.draw_no.map(strata))
        narrow_rows = []
        for pair in candidates_df[candidates_df.draw_no.isin(strata)].itertuples():
            narrow_rows += [{"draw_no": pair.draw_no, "stratum": strata[pair.draw_no], "minute": minute, "travel_min": value}
                            for minute, value in enumerate(narrow_minutes(network, pair))]
            print(f"  narrow {pair.draw_no} done", flush=True)
        narrow_df = pd.DataFrame(narrow_rows)
        wide_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_wide.csv", index=False)
        narrow_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_narrow.csv", index=False)

    pairs_df = compare(wide_df, narrow_df)
    is_sound = ((pairs_df.narrow_reached == pairs_df.wide_reached) & (pairs_df.ranks_over_tolerance == 0)).all()
    lines = [f"{NAME} {run_date}: {len(pairs_df)} pairs x {WIDE_WINDOW_MIN} minutes, max_time {MAX_TIME_MIN}, "
             f"tolerance {TOLERANCE_MIN} min",
             f"VERDICT: {'SOUND' if is_sound else 'NOT SOUND'}; ranks exact {int(pairs_df.ranks_exact.sum())} of "
             f"{int(pairs_df.ranks_compared.sum())}, over tolerance {int(pairs_df.ranks_over_tolerance.sum())}",
             pairs_df.to_string(index=False)]
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()
