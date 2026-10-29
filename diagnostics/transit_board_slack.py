"""Does R5's 60 s first-board slack move the transit band shares?

Claim under test (DESIGN.md Q22, concepts/transit.md T7 (e), concepts/walk.md WLK-1): R5 waits 60 s before
every boarding (hard-coded; Google has none). Removing the wait at the first boarding changes the share of
pairs in band 1 (walk + PT <= 10 min) and band 2 (<= 20 min) by at most SMALL_SHARE_PP percentage points.
Where the pipeline relies on it: TTM as TRN-6's validation router and the reachability bands (RCH-1, SCR-1)
on stock R5; if the claim holds, the slack stays as a stated bias and R5 is not rebuilt (Q22).

Why the shift works (read from the r5-v7.5.1-r5py jar, javap, 2026-10-17): FastRaptorWorker boards a trip
at a stop only if it departs after bestTimes[stop] + 60 s (bipush 60, inlined), in every round; in round 1
bestTimes is departure + access walk (initializeScheduleState). An agent leaving at t - 1 min reaches stop
s at t - 1 + w_s and may board after t + w_s: exactly what a no-wait agent leaving at t may board. Later
boardings keep their 60 s in both. R5 works in seconds and the shift is exactly 60 s, so whole-minute
flooring commutes with it: no rounding tolerance. So transit with no first-board wait, from t, is
Tns = (transit from t - 1) - 1.
r5py always adds a direct walk (regional_task.py: access modes double as direct modes), so the shifted run
returns H = min(W, Tns + 1), W the walk-only time. Then: H < W -> no-wait time N = H - 1 (transit won);
H = W -> N = W, except N = W - 1 when Tns + 1 = W exactly, which H cannot show. Those tie pairs are
flagged and band shares are reported both ways (N_hi = W, N_lo = W - 1). (Corrects the recorded
min(W, H - 1), which gives W - 1 whenever walking wins.)
Deviation (after run 1, 2026-10-17; Claude): run 1's "N <= S" check failed on 6 / 6 / 14 pairs (3.6 / 4.2 /
5.0 km/h), all ties with S = W - 1. There transit with the wait already took W - 1 (Tns <= S < W and
Tns + 1 >= W give Tns = W - 1), so the tie is resolved by S: N = W - 1. Run 1's rule ignored S and gave W.
Ties now count only where S = W. Fixed in no_wait_minutes; summary rerun on the saved table, no rerouting.

Method: the training half of the transit split (half == "train"), each pair at its drawn minute on
WINDOW_DATE, 1-min window, three runs per walk speed: stock TTM from t (S), TTM from t - 1 min with
max_time + 1 min (H), walk-only (W). Speeds: BASELINE 3.6 km/h (r5py's default, what the pipeline uses)
is judged; 4.2 (Google's measured walk speed, WLK-1) and 5.0 (Google's public figure, a control) are
reported only. Against Google, on the exploration pairs (inside the training half): TTM - Google before
and after, Google's earliest in-scope arrival in whole minutes from the requested minute (as
transit_walk_speed_lead.py). The test half is not read.
Hard checks (any failure stops the run before the verdict): N <= S, S <= W, H <= W on every pair.
Rule (set with the user before the run, 2026-10-17), at 3.6 km/h, band shares over the training half:
  SMALL       if both bands' shares move by <= SMALL_SHARE_PP percentage points under both tie readings;
  LARGE       if either band moves by more than SMALL_SHARE_PP under both readings;
  UNRESOLVED  otherwise (the tie pairs decide).
SMALL: keep stock R5, state the slack as a bias. LARGE: consider a rebuilt jar (Q22), checked against
this shift on single-boarding trips. Transfers keep their slack here, so on multi-boarding trips this
understates a no-slack-anywhere Google.

Conclusion (run 2026-10-17, summary rerun after the deviation): SMALL at 3.6 km/h. Hard checks pass at
every speed. Training half (1,252): band 1 2.56% -> 2.56% (N_hi) / 3.04% (N_lo); band 2 11.50% -> 13.26%
(+1.76 pp, both readings); 196 pairs faster, by a median 5 min (mean 6.3, max 31): a missed vehicle, the
rest unchanged; 94 unresolved ties. Exploration pairs vs Google: mean +1.34 -> +0.41 min, within 1 min
245 -> 271 of 493, 3+ late 141 -> 95. At 4.2 (reported): band 2 +1.60 pp; within 1 min 295 -> 312, late
67 -> 31, mean -1.19 -> -2.17 (R5 finds trips Google does not offer: the penalty's job). At 5.0 (control):
overshoots (median -2 with no wait). Decision (user): stock R5 kept, the slack stated as a bias.

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release), the
OSM extract in frozen_inputs/osm_extract/, the transit pair draw, split and Google route table in
outputs/transit_validation/. Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1).
No paid API calls; r5py only. The per-pair table is saved data, written row by row: a rerun reuses the
newest complete one and says so, or resumes the newest partial one. Results carry the run date; a
same-day rerun replaces that day's results.
"""
import datetime
import sys
from pathlib import Path

import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
GTFS_CLEANED_DIR = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
GOOGLE_ROUTES_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_board_slack"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_di_window.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as transit_di_window.py
SINGLE_PERCENTILE = 49                         # as transit_di_window.py (r5py renames a lone p50)
TRAIN_HALF = "train"                           # transit split's training half (T3)
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]   # TRN-11: a name mismatch is the same line under another short name
SECONDS_PER_MIN = 60
BAND_LIMITS_MIN = {"band_1": 10, "band_2": 20}  # walk + PT <= 600 s, <= 1,200 s (DESIGN.md Cross-cutting positions)

# --- test ------------------------------------------------------------------------------------------
BOARD_SLACK_MIN = 1                            # R5's 60 s first-board slack; also the departure shift
BASELINE_SPEED_KMH = 3.6                       # r5py's default; the judged speed
PRIMARY_SPEED_KMH = 4.2                        # Google's measured walk speed (WLK-1); reported only
PUBLIC_SPEED_KMH = 5.0                         # Google's public figure; a control, reported only
SPEEDS_KMH = [BASELINE_SPEED_KMH, PRIMARY_SPEED_KMH, PUBLIC_SPEED_KMH]
SMALL_SHARE_PP = 2.0                           # band-share move counted small (percentage points; user, 2026-10-17)
ARRIVAL_TOLERANCE_MIN = 1                      # TTM within this of Google counts as close (as transit_walk_speed_lead.py)
LATE_GAP_MIN = 3                               # TTM later than Google by at least this counts as late (as transit_walk_speed_lead.py)

sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
from r5py import TransportMode, TransportNetwork, TravelTimeMatrix  # noqa: E402


def departure_of(pair):
    """The pair's drawn minute on WINDOW_DATE."""
    return datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))


def ttm_min(network, pair, departure, transport_modes, max_time_min, speed_walking_kmh):
    """TTM travel time (whole minutes; NaN past max_time) for one pair at a 1-min window."""
    origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.origin_lon], [pair.origin_lat]))
    destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
    matrix_df = pd.DataFrame(TravelTimeMatrix(
        network, origins=origins, destinations=destinations, departure=departure,
        departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
        transport_modes=transport_modes, max_time=datetime.timedelta(minutes=max_time_min),
        speed_walking=speed_walking_kmh))
    return matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]


def speed_tag(speed_kmh):
    return f"{speed_kmh:.1f}".replace(".", "_")


def pair_row(network, pair):
    """Stock (S), shifted (H) and walk-only (W) minutes at every speed for one pair."""
    departure = departure_of(pair)
    shifted_departure = departure - datetime.timedelta(minutes=BOARD_SLACK_MIN)
    transit_modes = [TransportMode.TRANSIT, TransportMode.WALK]
    row = {"draw_no": pair.Index}
    for speed_kmh in SPEEDS_KMH:
        tag = speed_tag(speed_kmh)
        row[f"stock_{tag}"] = ttm_min(network, pair, departure, transit_modes, MAX_TIME_MIN, speed_kmh)
        row[f"shifted_{tag}"] = ttm_min(network, pair, shifted_departure, transit_modes,
                                        MAX_TIME_MIN + BOARD_SLACK_MIN, speed_kmh)
        row[f"walk_{tag}"] = ttm_min(network, pair, departure, [TransportMode.WALK], MAX_TIME_MIN, speed_kmh)
    return row


def saved_table(draw_nos):
    """The newest saved per-pair table and whether it covers every pair; (None, False) if none."""
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_pairs.csv"))
    if not saved:
        return None, False
    saved_df = pd.read_csv(saved[-1])
    return saved[-1], set(draw_nos) <= set(saved_df.draw_no)


def no_wait_minutes(table_df, tag):
    """N_hi, N_lo (no first-board wait) and the tie flag from S, H, W (docstring); NaN past max_time = inf.
    A tie (H = W) with S < W is resolved: transit with the wait already took S = W - 1, so N = W - 1."""
    stock = table_df[f"stock_{tag}"].fillna(np.inf)
    walk = table_df[f"walk_{tag}"].fillna(np.inf)
    shifted = table_df[f"shifted_{tag}"].fillna(np.inf)
    is_transit_won = shifted < walk
    is_resolved_tie = ~is_transit_won & (stock < walk)
    is_tie = ~is_transit_won & ~is_resolved_tie & np.isfinite(walk)
    n_hi = np.where(is_transit_won, shifted - BOARD_SLACK_MIN, np.where(is_resolved_tie, walk - BOARD_SLACK_MIN, walk))
    n_lo = np.where(is_tie, walk - BOARD_SLACK_MIN, n_hi)
    return pd.Series(n_hi, index=table_df.index), pd.Series(n_lo, index=table_df.index), is_tie


def band_shares_pp(minutes):
    return {band: 100 * float((minutes <= limit_min).mean()) for band, limit_min in BAND_LIMITS_MIN.items()}


def google_earliest_df():
    """Google's earliest in-scope arrival per pair, whole minutes from the requested minute."""
    routes_df = pd.read_csv(GOOGLE_ROUTES_PATH)
    routes_df = routes_df[routes_df.route_scope.isin(GOOGLE_SCOPES)]
    earliest_df = routes_df.loc[routes_df.groupby("draw_no").arrival_from_request_s.idxmin()]
    return pd.DataFrame({"draw_no": earliest_df.draw_no.values,
                         "google_min": (earliest_df.arrival_from_request_s // SECONDS_PER_MIN).values})


def gap_line(label, gap):
    gap = gap.dropna()
    return (f"{label}: mean {gap.mean():+.2f}, median {gap.median():+.1f}, within {ARRIVAL_TOLERANCE_MIN} min "
            f"{int((gap.abs() <= ARRIVAL_TOLERANCE_MIN).sum())} of {len(gap)}, late >= {LATE_GAP_MIN} {int((gap >= LATE_GAP_MIN).sum())}")


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    split_df = pd.read_csv(SPLIT_PATH)
    train_df = split_df[split_df.half == TRAIN_HALF]
    draw_df = pd.read_csv(PAIRS_PATH).set_index("draw_no").loc[train_df.draw_no]

    saved_path, is_complete = saved_table(draw_df.index)
    if is_complete:
        print(f"reusing saved table {saved_path.name}")
    else:
        table_path = saved_path or DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_pairs.csv"
        done = set(pd.read_csv(table_path).draw_no) if saved_path else set()
        print(f"{'resuming ' + table_path.name + f' ({len(done)} done)' if saved_path else 'new table ' + table_path.name}; "
              f"{len(draw_df) - len(done)} pairs to route", flush=True)
        network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        for pair in draw_df[~draw_df.index.isin(done)].itertuples():
            row = pair_row(network, pair)
            pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
            print(f"  {row}", flush=True)
        saved_path = table_path
    table_df = pd.read_csv(saved_path).set_index("draw_no").loc[draw_df.index].reset_index()
    table_df = table_df.merge(train_df[["draw_no", "is_exploration"]], on="draw_no")
    table_df = table_df.merge(google_earliest_df(), on="draw_no", how="left")

    lines = [f"{NAME} {run_date}: {len(table_df)} training-half pairs ({int(table_df.is_exploration.sum())} exploration), "
             f"table {saved_path.name}; 1-min window; no-wait = TTM from t - 1 min, minus 1 (first boarding only)"]
    checks_failed = []
    verdict_line = None
    for speed_kmh in SPEEDS_KMH:
        tag = speed_tag(speed_kmh)
        stock = table_df[f"stock_{tag}"].fillna(np.inf)
        walk = table_df[f"walk_{tag}"].fillna(np.inf)
        shifted = table_df[f"shifted_{tag}"].fillna(np.inf)
        n_hi, n_lo, is_tie = no_wait_minutes(table_df, tag)
        table_df[f"no_wait_hi_{tag}"], table_df[f"no_wait_lo_{tag}"], table_df[f"is_tie_{tag}"] = n_hi, n_lo, is_tie
        for check_name, is_broken in [("N <= S", n_hi > stock), ("S <= W", stock > walk), ("H <= W", shifted > walk)]:
            if is_broken.any():
                checks_failed.append(f"{speed_kmh} km/h {check_name} fails on {table_df.draw_no[is_broken].tolist()}")
        saved_min = stock - n_hi
        stock_pp, hi_pp, lo_pp = band_shares_pp(stock), band_shares_pp(n_hi), band_shares_pp(n_lo)
        moves_hi = {band: hi_pp[band] - stock_pp[band] for band in BAND_LIMITS_MIN}
        moves_lo = {band: lo_pp[band] - stock_pp[band] for band in BAND_LIMITS_MIN}
        lines.append(f"{speed_kmh} km/h{' (judged)' if speed_kmh == BASELINE_SPEED_KMH else ' (reported)'}: "
                     f"ties {int(is_tie.sum())}; faster without the wait on {int((saved_min > 0).sum())} pairs, "
                     f"saving (N_hi) {saved_min[saved_min > 0].describe()[['mean', '50%', 'max']].round(2).to_dict()}")
        for band in BAND_LIMITS_MIN:
            lines.append(f"  {band}: stock {stock_pp[band]:.2f}%, no-wait {hi_pp[band]:.2f}% (N_hi, {moves_hi[band]:+.2f} pp) / "
                         f"{lo_pp[band]:.2f}% (N_lo, {moves_lo[band]:+.2f} pp); pairs entering "
                         f"{int(((stock > BAND_LIMITS_MIN[band]) & (n_hi <= BAND_LIMITS_MIN[band])).sum())} (N_hi)")
        is_exploration = table_df.is_exploration.astype(bool)
        google = table_df.google_min[is_exploration]
        lines.append("  " + gap_line("TTM - Google, stock", stock[is_exploration].replace(np.inf, np.nan) - google))
        lines.append("  " + gap_line("TTM - Google, no-wait N_hi", n_hi[is_exploration].replace(np.inf, np.nan) - google))
        lines.append("  " + gap_line("TTM - Google, no-wait N_lo", n_lo[is_exploration].replace(np.inf, np.nan) - google))
        if speed_kmh == BASELINE_SPEED_KMH:
            is_small_hi = all(abs(move) <= SMALL_SHARE_PP for move in moves_hi.values())
            is_small_lo = all(abs(move) <= SMALL_SHARE_PP for move in moves_lo.values())
            verdict = "SMALL" if is_small_hi and is_small_lo else "LARGE" if not (is_small_hi or is_small_lo) else "UNRESOLVED"
            verdict_line = (f"VERDICT at {BASELINE_SPEED_KMH} km/h: {verdict} (band moves N_hi "
                            f"{ {band: round(move, 2) for band, move in moves_hi.items()} }, N_lo "
                            f"{ {band: round(move, 2) for band, move in moves_lo.items()} } pp; small if all <= {SMALL_SHARE_PP})")
    if checks_failed:
        lines.insert(1, "HARD CHECKS FAILED, no verdict: " + "; ".join(checks_failed))
    else:
        lines.insert(1, "hard checks passed (N <= S, S <= W, H <= W) at every speed")
        lines.insert(2, verdict_line)
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary)
    table_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_results.csv", index=False)


if __name__ == "__main__":
    main()
