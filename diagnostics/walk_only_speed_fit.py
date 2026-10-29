"""What walk speed do Google's walk-only answers give R5, and where does it point for transit?

Exploratory (user, 2026-10-17: "try the walk-only speed fit and see where it points"); no pass rule, no
verdict. Proposal under test (not yet a decision; concepts/walk.md WLK-1, concepts/transit.md T7 (g)):
fit R5's walk speed on walk-only trips, where no boarding slack, ride penalty or timetable can leak into
it, and use it for walking inside transit too; R5's longer access walk (median 1.14x Google's,
transit_router_egress.py) then stays a separate access bias instead of being absorbed into the speed.
Where the pipeline would rely on it: the speed passed into R5 for bands 1-2 (WLK-1, WLK-2, RCH-1).

Method, part A (fit): training-half pairs (transit split, half == "train") with a Google walk-only route
(the default if it is walk-only, else the first walk-only alternative). R5's walk-only path length L_r5
from one r5py DetailedItineraries call (walk only, pairwise); Google's distance L_g and duration T_g.
Sanity (must hold, else stop): R5's walk time is L_r5 / speed, checked against the whole-minute walk-only
TTM times of transit_board_slack.py's saved table at 3.6, 4.2 and 5.0 km/h (floor(L_r5 / v) = TTM within
FLOOR_TOLERANCE_MIN on >= SANITY_SHARE of pairs).
Reported: effective speed L_r5 / T_g (median, the primary figure, as Google's own 4.23 is a median; also
least squares through the origin and with an intercept T_g = a + L_r5 / v); Google's pure speed L_g / T_g;
the path regression L_r5 = a + b * L_g with bootstrap 95% intervals (the pure-vs-effective check of T7 g:
intercept near 0 -> proportional -> effective speed; clear intercept -> fixed offset); all pairs, pairs with
L_g >= LONG_WALK_M, and walk-only defaults only.
Part B (where it points): the exploration pairs (inside the training half) rerouted with TTM at the fitted
speed, stock and with no first-board wait (transit_board_slack.py's shift, its corrected tie rule), against
Google's earliest in-scope arrival; set beside that table's 3.6 / 4.2 / 5.0 rows. The test half is not read.

Conclusion (run 2026-10-17): fitted 4.16 km/h (median effective speed, 217 pairs; IQR 3.97-4.32; least
squares through the origin 4.16; with an intercept 4.21 km/h + 25 s; 65 defaults alone 4.19). Sanity
passed (floor(L_r5 / v) within 1 min of TTM's walk on >= 0.98 at all three speeds; TTM is 0 or 1 min
above, DI's time ~26 s above L_r5 / 3.6 km/h: likely the point-to-street link, so the exact match may sit
slightly above 4.16). Google's pure speed 4.24. R5's walk-only path is Google's length (median ratio
0.99; L_r5 = +31 m [-2, +67] + 0.96 [0.94, 0.98] L_g; defaults +9 m, 0.99): effective ~ pure, so the 1.14x
access walk (transit_router_egress.py) is specific to reaching stops. Part B, 500 exploration pairs:
4.16 stock within 1 min 294 of 494, late 70, early 86 (mean -1.09); no first wait 313, 31, 107 (-2.07);
4.2 within one pair of it. Decision (user, 2026-10-17): 4.16 km/h for all walking (WLK-1).

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release), the
OSM extract in frozen_inputs/osm_extract/, the transit pair draw, split and Google route table in
outputs/transit_validation/, transit_board_slack.py's per-pair results in diagnostics/diagnostic_data/
(newest). Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls;
r5py only. The per-pair tables (A: lengths, B: TTM at the fitted speed) are saved data: a rerun reuses the
newest and says so. Results carry the run date; a same-day rerun replaces that day's results.
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
SLACK_RESULTS_GLOB = "transit_board_slack_*_results.csv"   # transit_board_slack.py's per-pair results
NAME = "walk_only_speed_fit"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_di_window.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as transit_di_window.py
SINGLE_PERCENTILE = 49                         # as transit_di_window.py (r5py renames a lone p50)
TRAIN_HALF = "train"
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]   # TRN-11
SECONDS_PER_MIN = 60
M_PER_KM = 1000
S_PER_HOUR = 3600

# --- fit and checks --------------------------------------------------------------------------------
SLACK_SPEEDS_KMH = [3.6, 4.2, 5.0]             # transit_board_slack.py's speeds (sanity and comparison)
BOARD_SLACK_MIN = 1                            # R5's 60 s first-board slack; the departure shift
FLOOR_TOLERANCE_MIN = 1                        # sanity: floor(L_r5 / v) vs TTM's walk-only minutes
SANITY_SHARE = 0.95
LONG_WALK_M = 300                              # subset with Google walk >= this (as WLK-1's 4.21 figure)
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261017
ARRIVAL_TOLERANCE_MIN = 1                      # as transit_board_slack.py
LATE_GAP_MIN = 3

sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
from r5py import DetailedItineraries, TransportMode, TransportNetwork, TravelTimeMatrix  # noqa: E402


def google_walk_df(train_draw_nos):
    """One Google walk-only route per training pair: the default if walk-only, else the first walk-only alternative."""
    routes_df = pd.read_csv(GOOGLE_ROUTES_PATH)
    walk_df = routes_df[routes_df.is_walk_only & routes_df.draw_no.isin(train_draw_nos)]
    walk_df = walk_df.sort_values(["draw_no", "is_default", "route_ix"], ascending=[True, False, True])
    walk_df = walk_df.groupby("draw_no").head(1)
    return walk_df[["draw_no", "is_default", "distance_m", "duration_s"]].rename(
        columns={"distance_m": "google_m", "duration_s": "google_s"})


def r5_walk_lengths_df(network, pairs_df):
    """R5's walk-only path length per pair (metres), from one pairwise DetailedItineraries call."""
    origins = gpd.GeoDataFrame({"id": pairs_df.draw_no.values}, crs="EPSG:4326",
                               geometry=gpd.points_from_xy(pairs_df.origin_lon, pairs_df.origin_lat))
    destinations = gpd.GeoDataFrame({"id": pairs_df.draw_no.values}, crs="EPSG:4326",
                                    geometry=gpd.points_from_xy(pairs_df.dest_lon, pairs_df.dest_lat))
    departure = datetime.datetime.combine(WINDOW_DATE, datetime.time(12))   # walk-only: time does not matter
    di_df = pd.DataFrame(DetailedItineraries(network, origins=origins, destinations=destinations, departure=departure,
                                             transport_modes=[TransportMode.WALK]))
    lengths_df = di_df.groupby("from_id").agg(r5_m=("distance", "sum"), r5_di_s=("travel_time", "sum")).reset_index()
    lengths_df["r5_di_s"] = lengths_df.r5_di_s.dt.total_seconds()
    return lengths_df.rename(columns={"from_id": "draw_no"})


def bootstrap_line(x, y, rng):
    """Least squares y = a + b x, with bootstrap 95% intervals."""
    slope, intercept = np.polyfit(x, y, 1)
    draws = []
    for _ in range(N_BOOTSTRAP):
        pick = rng.integers(0, len(x), len(x))
        draws.append(np.polyfit(x[pick], y[pick], 1))
    draws = np.array(draws)
    slope_ci = np.percentile(draws[:, 0], [2.5, 97.5])
    intercept_ci = np.percentile(draws[:, 1], [2.5, 97.5])
    return intercept, intercept_ci, slope, slope_ci


def fit_lines(fit_df, label, rng):
    """Speed and path-regression lines for one subset."""
    effective_kmh = fit_df.r5_m / fit_df.google_s * S_PER_HOUR / M_PER_KM
    pure_kmh = fit_df.google_m / fit_df.google_s * S_PER_HOUR / M_PER_KM
    through_origin_kmh = (fit_df.r5_m ** 2).sum() / (fit_df.r5_m * fit_df.google_s).sum() * S_PER_HOUR / M_PER_KM
    time_slope, time_intercept = np.polyfit(fit_df.r5_m.values, fit_df.google_s.values, 1)
    path_a, path_a_ci, path_b, path_b_ci = bootstrap_line(fit_df.google_m.values, fit_df.r5_m.values, rng)
    ratio = fit_df.r5_m / fit_df.google_m
    return [f"{label} (n = {len(fit_df)}):",
            f"  effective speed L_r5 / T_g: median {effective_kmh.median():.2f} km/h (IQR {effective_kmh.quantile(0.25):.2f}-"
            f"{effective_kmh.quantile(0.75):.2f}); least squares through origin {through_origin_kmh:.2f}; with intercept "
            f"{S_PER_HOUR / M_PER_KM / time_slope:.2f} km/h + {time_intercept:+.0f} s",
            f"  Google pure speed L_g / T_g: median {pure_kmh.median():.2f} km/h (IQR {pure_kmh.quantile(0.25):.2f}-"
            f"{pure_kmh.quantile(0.75):.2f})",
            f"  path L_r5 / L_g: median {ratio.median():.3f} (IQR {ratio.quantile(0.25):.3f}-{ratio.quantile(0.75):.3f}); "
            f"L_r5 = a + b L_g: a {path_a:+.0f} m [{path_a_ci[0]:+.0f}, {path_a_ci[1]:+.0f}], "
            f"b {path_b:.3f} [{path_b_ci[0]:.3f}, {path_b_ci[1]:.3f}]"], float(effective_kmh.median())


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


def fitted_speed_row(network, pair, speed_kmh):
    """Stock (S), shifted (H) and walk-only (W) minutes at the fitted speed (as transit_board_slack.py)."""
    departure = datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))
    transit_modes = [TransportMode.TRANSIT, TransportMode.WALK]
    return {"draw_no": pair.Index,
            "stock": ttm_min(network, pair, departure, transit_modes, MAX_TIME_MIN, speed_kmh),
            "shifted": ttm_min(network, pair, departure - datetime.timedelta(minutes=BOARD_SLACK_MIN), transit_modes,
                               MAX_TIME_MIN + BOARD_SLACK_MIN, speed_kmh),
            "walk": ttm_min(network, pair, departure, [TransportMode.WALK], MAX_TIME_MIN, speed_kmh)}


def no_wait_minutes(stock, shifted, walk):
    """No-first-board-wait minutes, N_hi (ties = W) and N_lo (ties = W - 1), as transit_board_slack.py (corrected rule)."""
    stock, shifted, walk = stock.fillna(np.inf), shifted.fillna(np.inf), walk.fillna(np.inf)
    is_transit_won = shifted < walk
    is_resolved_tie = ~is_transit_won & (stock < walk)
    is_tie = ~is_transit_won & ~is_resolved_tie & np.isfinite(walk)
    n_hi = pd.Series(np.where(is_transit_won, shifted - BOARD_SLACK_MIN,
                              np.where(is_resolved_tie, walk - BOARD_SLACK_MIN, walk)), index=stock.index)
    return n_hi, n_hi.where(~is_tie, walk - BOARD_SLACK_MIN)


def google_earliest_df():
    """Google's earliest in-scope arrival per pair, whole minutes from the requested minute."""
    routes_df = pd.read_csv(GOOGLE_ROUTES_PATH)
    routes_df = routes_df[routes_df.route_scope.isin(GOOGLE_SCOPES)]
    earliest_df = routes_df.loc[routes_df.groupby("draw_no").arrival_from_request_s.idxmin()]
    return pd.DataFrame({"draw_no": earliest_df.draw_no.values,
                         "google_min": (earliest_df.arrival_from_request_s // SECONDS_PER_MIN).values})


def gap_line(label, ttm, google):
    gap = (ttm.replace(np.inf, np.nan) - google).dropna()
    return (f"  {label}: mean {gap.mean():+.2f}, median {gap.median():+.1f}, within {ARRIVAL_TOLERANCE_MIN} min "
            f"{int((gap.abs() <= ARRIVAL_TOLERANCE_MIN).sum())} of {len(gap)}, late >= {LATE_GAP_MIN} "
            f"{int((gap >= LATE_GAP_MIN).sum())}, early <= -{LATE_GAP_MIN} {int((gap <= -LATE_GAP_MIN).sum())}")


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    split_df = pd.read_csv(SPLIT_PATH)
    train_df = split_df[split_df.half == TRAIN_HALF]
    pairs_df = pd.read_csv(PAIRS_PATH)
    slack_path = sorted(DIAGNOSTIC_DATA_DIR.glob(SLACK_RESULTS_GLOB))[-1]
    slack_df = pd.read_csv(slack_path)
    network = None

    # --- part A: fit ---
    walk_df = google_walk_df(train_df.draw_no).merge(pairs_df, on="draw_no")
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_lengths.csv"))
    if saved:
        print(f"reusing saved lengths {saved[-1].name}")
        lengths_df = pd.read_csv(saved[-1])
    else:
        network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        lengths_df = r5_walk_lengths_df(network, walk_df)
        lengths_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_lengths.csv", index=False)
    fit_df = walk_df[["draw_no", "is_default", "google_m", "google_s"]].merge(lengths_df, on="draw_no")
    fit_df = fit_df.merge(slack_df[["draw_no"] + [f"walk_{v:.1f}".replace(".", "_") for v in SLACK_SPEEDS_KMH]], on="draw_no")

    lines = [f"{NAME} {run_date}: exploratory, no verdict. {len(walk_df)} training pairs with a Google walk-only route "
             f"({int(walk_df.is_default.sum())} defaults); R5 lengths for {len(fit_df)}; slack table {slack_path.name}"]
    sanity = []
    for speed_kmh in SLACK_SPEEDS_KMH:
        predicted_min = np.floor(fit_df.r5_m / (speed_kmh * M_PER_KM / S_PER_HOUR) / SECONDS_PER_MIN)
        ttm_walk = fit_df[f"walk_{speed_kmh:.1f}".replace(".", "_")]
        share = float(((predicted_min - ttm_walk).abs() <= FLOOR_TOLERANCE_MIN).mean())
        sanity.append(share >= SANITY_SHARE)
        lines.append(f"sanity {speed_kmh} km/h: floor(L_r5 / v) within {FLOOR_TOLERANCE_MIN} min of TTM walk on {share:.3f} "
                     f"(need {SANITY_SHARE}); exact on {float((predicted_min == ttm_walk).mean()):.3f}; "
                     f"TTM - predicted {(ttm_walk - predicted_min).value_counts().sort_index().to_dict()}")
    lines.append(f"DI time vs L_r5 / 3.6 km/h: median diff {(fit_df.r5_di_s - fit_df.r5_m / (SLACK_SPEEDS_KMH[0] * M_PER_KM / S_PER_HOUR)).median():+.1f} s")
    if not all(sanity):
        lines.insert(1, "SANITY FAILED: R5's walk time is not L_r5 / v; part A's speeds and part B not computed")
        summary = "\n".join(lines)
        print(summary)
        with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
            file.write(summary)
        return
    all_lines, fitted_kmh = fit_lines(fit_df, "all walk-only pairs", rng)
    lines += all_lines
    lines += fit_lines(fit_df[fit_df.google_m >= LONG_WALK_M], f"Google walk >= {LONG_WALK_M} m", rng)[0]
    lines += fit_lines(fit_df[fit_df.is_default], "walk-only defaults", rng)[0]
    fitted_kmh = round(fitted_kmh, 2)
    lines.append(f"FITTED (median effective speed, all pairs): {fitted_kmh} km/h")

    # --- part B: where it points ---
    exploration_df = pairs_df.set_index("draw_no").loc[train_df.draw_no[train_df.is_exploration]]
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_ttm_*kmh.csv"))
    saved = [path for path in saved if path.stem.endswith(f"{fitted_kmh:.2f}".replace(".", "_") + "kmh")]
    if saved:
        print(f"reusing saved TTM table {saved[-1].name}")
        ttm_df = pd.read_csv(saved[-1])
    else:
        if network is None:
            network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        rows = []
        for pair in exploration_df.itertuples():
            rows.append(fitted_speed_row(network, pair, fitted_kmh))
            print(f"  {rows[-1]}", flush=True)
        ttm_df = pd.DataFrame(rows)
        speed_label = f"{fitted_kmh:.2f}".replace(".", "_")
        ttm_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_ttm_{speed_label}kmh.csv", index=False)
    ttm_df = ttm_df.merge(google_earliest_df(), on="draw_no", how="left")
    n_hi, n_lo = no_wait_minutes(ttm_df.stock, ttm_df.shifted, ttm_df.walk)
    lines.append(f"part B, {len(ttm_df)} exploration pairs, TTM - Google's earliest in-scope arrival (minutes):")
    lines.append(gap_line(f"{fitted_kmh} km/h stock", ttm_df.stock.fillna(np.inf), ttm_df.google_min))
    lines.append(gap_line(f"{fitted_kmh} km/h no-wait N_hi", n_hi, ttm_df.google_min))
    lines.append(gap_line(f"{fitted_kmh} km/h no-wait N_lo", n_lo, ttm_df.google_min))
    slack_exploration_df = slack_df[slack_df.is_exploration.astype(bool)]
    for speed_kmh in SLACK_SPEEDS_KMH:
        tag = f"{speed_kmh:.1f}".replace(".", "_")
        lines.append(gap_line(f"{speed_kmh} km/h stock (slack table)", slack_exploration_df[f"stock_{tag}"].fillna(np.inf),
                              slack_exploration_df.google_min))
        lines.append(gap_line(f"{speed_kmh} km/h no-wait N_hi (slack table)", slack_exploration_df[f"no_wait_hi_{tag}"],
                              slack_exploration_df.google_min))
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary)
    fit_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_fit.csv", index=False)


if __name__ == "__main__":
    main()
