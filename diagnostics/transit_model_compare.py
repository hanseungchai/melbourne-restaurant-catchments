"""Which transit model calls bands 1-2 best on TRN-13's bars: no-wait, stock controls, or no-wait x scalar?

Claim under test (concepts/transit.md TRN-13; DESIGN.md Q23): the no-wait model fails TRN-13 with R5 early
(median -1 min); a scalar s on its transit times, or a plain cut shift, may pass. Where the pipeline relies on
it: the transit bands (SCR-1, RCH-1) before they go into reachability.

Comparison (decided by the user 2026-10-18, discussion; production rule and model 5 OK'd 2026-10-18, build):
  Same pairs, Google times, networks and bars as diagnostics/transit_band_metric.py (TRN-13); each model is
  scored with TRN-13's checks (2a floor, 2b unbiased-noise bar, 2c balance, 3 hard misses, count ratios).
  Models (minutes R5 calls; R5 below a cut when minutes <= the model's cut):
    1 no-wait, production rule: from H (transit departing 1 min early) and W (walk-only) only, without stock S:
      N = H - 1 if H < W, else W. Differs from TRN-13's N_hi only on the ties S settles (S = W - 1, H = W),
      where it reads W, not W - 1; those pairs are counted and reported. TRN-13's as-run scores are its N_hi.
    2 stock R5 at 4.16 km/h: S as saved (first wait included, no correction). No reroute.
    3 r5py as shipped: walk 3.6 km/h (r5py 1.1.7's default), first wait included; rerouted here.
    4 no-wait x s: s x N on transit-won pairs (H < W), W unscaled on walk pairs; below a cut when s x N <= cut,
      unrounded. s fitted on training-set pairs away from the cuts (Google 0-6, 14-16, 24-30 min), transit-won
      only, by least squares on log(s N / Google) with soft_l1 at scale 0.1 (as drive's ALPHA, config
      DRIVE_FIT_LOSS_SCALE). Pairs with Google or N of 0 min are left out of the fit (log undefined).
      Google here is the rounded minute the test scores against (Claude's choice: N is whole minutes too).
    5 no-wait with transit cuts shifted: model 1 with transit-won pairs below a cut when N <= cut - k (k = 1
      at cut 10; k = 1 or 2 at cut 20), walk pairs at the plain cut (user, 2026-10-18: an all-trip shift, run
      first, is not a useful model). Whole minutes make s x N <= cut the same as N <= floor(cut / s) on
      transit-won pairs, so the variant matching model 4's floors must score as model 4 (a check).
  The noise bar (2b) uses each model's own error away from the cuts, centred to median 0; a cut shift does
  not change it. Picking among the models on these pairs is allowed (Q23): the test half stays the final
  check and is not read here.

Conclusion (run 2026-10-18): two models fail only on hard misses: 2 stock R5 4.16 (zone 1 recall 0.805 /
  precision 0.787, zone 2 0.774 / 0.774, hard 31/141, ratios 1.010 / 1.002) and 4 no-wait x s (s 1.0247 on 191
  training pairs; zone 1 0.782 / 0.800, zone 2 0.809 / 0.809, hard 27/141, ratios 0.981 / 1.020). Model 5 at
  transit cuts 9 / 19 makes the same band call as model 4 on all 3,448 scored pairs: the scalar is a 1-min
  transit cut shift. Model 1 fails zone 2's noise bar and balance (55 early / 21 late) and hard misses (33/141);
  model 3 (shipped 3.6) fails every check, R5 late (median +1 min; hard misses 24/141, fewest of models 1-4); model 5 at 9 / 18 overshoots zone 2 (29 early / 74 late). Hard misses fail under every
  model (20-33 of 141; bar upper end <= 0.05). Dropping S changes 3 band calls (33 settled ties). Reference
  column reproduces TRN-13's recorded scores exactly. Candidates kept (user): 2 and 4 (as transit cut - 1).

Inputs (read only): as transit_band_metric.py, plus its saved routing tables
(diagnostic_data/transit_band_metric_*_routes_<release>.csv, the newest per release) and its cleaned copy of
the 2026-10-16 feeds (diagnostic_data/transit_band_metric_gtfs_cleaned_20261016/). Self-contained (CLAUDE.md
D1). No paid API calls; r5py only.
Usage: `python transit_model_compare.py route 20261009`, `... route 20261016` (one network per process; model 3
only), then `... score` (`... score --network=pathways`: transit_pathway_network.py's routing tables, model 3
from the old network; outputs under that script's name; `--network=pathways_v2 --date=own`: v2's own-date tables,
outputs tagged `compare_owndate`; model 3 from `... route <release> --own-date`, table `shipped_owndate`). Model 3's routing tables are saved data (one per release), written row by row: a
rerun resumes the newest one or reuses it when complete. Results carry the run date; a same-day rerun replaces
them.
Own-date run (2026-10-20, `--network=pathways_v2 --date=own`): stop check and the model 4 = model 5 check OK; failure
pattern as before: model 1 no-wait fails z2 balance and hard misses (29/141), model 2 stock fails hard misses only,
model 3 (as shipped, own-date copies) fails every check; the official verdicts are transit_hard_miss_range's.
"""
import datetime
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
OLD_CLEANED_DIR = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned"      # 2026-10-09 release
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_model_compare"
IS_PATHWAYS_V2 = "--network=pathways_v2" in sys.argv   # transit_pathway_network_v2.py (stops moved onto stubs)
IS_PATHWAYS = "--network=pathways" in sys.argv or IS_PATHWAYS_V2   # tables from transit_pathway_network*.py; outputs under its name
PATHWAYS_NAME = "transit_pathway_network_v2" if IS_PATHWAYS_V2 else "transit_pathway_network"
IS_OWN_DATE = "--date=own" in sys.argv         # v2 tables routed on each pair's own date (TRN-13, user 2026-10-20)
assert not IS_OWN_DATE or IS_PATHWAYS_V2, "--date=own needs --network=pathways_v2"
BAND_METRIC_NAME = "transit_band_metric"
NEW_CLEANED_DIR = DIAGNOSTIC_DATA_DIR / f"{BAND_METRIC_NAME}_gtfs_cleaned_20261016"  # 2026-10-16 release
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
RESERVE_PATH = SUBJECT_DIR / f"transit_pairs_reserve_{FILE_TAG}.csv"
TOPUP_PATH = SUBJECT_DIR / f"transit_pairs_topup_{FILE_TAG}.csv"
TOPUP_SELECTION_PATH = SUBJECT_DIR / f"transit_topup_selection_{FILE_TAG}.csv"
FIRST_ROUTES_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv"
SECOND_ROUTES_PATH = SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv"
TOPUP_ROUTES_PATH = SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"
GOOGLE_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.csv",        # departure_local: each pair's own date
                "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.csv",
                "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.csv"}
V2_NAME = "transit_pathway_network_v2"
V2_FEED_DIR_PATTERN = f"{V2_NAME}_gtfs_{{release}}"   # v2's uniquely named copies of the cleaned feeds (own-date model 3)

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_band_metric.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as transit_band_metric.py
SINGLE_PERCENTILE = 49                         # as transit_band_metric.py (r5py renames a lone p50)
SHIPPED_WALK_SPEED_KMH = 3.6                   # r5py 1.1.7 RegionalTask default; checked at routing
BOARD_SLACK_MIN = 1                            # R5's 60 s first-board slack; also the departure shift (T7 e)
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]  # TRN-11, as transit_band_metric
TRAIN_HALF = "train"
TRAIN_SET = "train"
SECONDS_PER_MIN = 60
SET_RELEASE = {"train": "20261009", "second": "20261016", "topup": "20261016"}
RANDOM_SETS = ["train", "second"]              # random samples; the top-up was picked near the cuts
ZONES_MIN = {1: (7, 13), 2: (17, 23)}          # Google minutes, +-3 around the cuts (TRN-13 (1))
CUTS_MIN = {1: 10, 2: 20}
AWAY_RANGES_MIN = [(0, 6), (14, 16), (24, 30)]  # Google minutes away from the cuts (TRN-13 (2b))
EXPECTED_ZONE_COUNTS = {1: {"train": 67, "second": 90, "topup": 49},
                        2: {"train": 119, "second": 179, "topup": 67}}  # as transit_band_metric
EXPECTED_SETTLED_TIES = 33                     # S settles these ties (counted 2026-10-18, this session)
CHECK_COVERS_DATE = WINDOW_DATE

# --- test (TRN-13, user OK 2026-10-18) -------------------------------------------------------------
WILSON_Z = 1.959964                            # 95% interval
FLOOR = 0.6
N_SIMULATIONS = 2000
SIMULATION_SEED = 20261018
SIGN_TEST_ALPHA = 0.05
CLOSE_TOLERANCE = 0.10                         # |recall - precision|
HARD_MISS_MAX = 0.05                           # Wilson upper end
COUNT_RATIO_RANGE = (0.90, 1.10)

# --- model 4's fit (user, 2026-10-18) --------------------------------------------------------------
FIT_LOSS = "soft_l1"
FIT_LOSS_SCALE = 0.1                           # config.DRIVE_FIT_LOSS_SCALE
FIT_START = 1.0
MIN_FIT_PARAM = 1e-6
SHIFTED_CUTS_MIN = [{1: 9, 2: 19}, {1: 9, 2: 18}]   # model 5 variants: transit-won pairs' cuts


# --- pairs and Google times (copied from transit_band_metric.py) -----------------------------------
def pairs_of_set(set_name):
    columns = ["draw_no", "origin_lat", "origin_lon", "dest_lat", "dest_lon", "haversine_m", "dep_min_of_day"]
    if set_name == "train":
        split_df = pd.read_csv(SPLIT_PATH, usecols=["draw_no", "half"])
        pairs_df = pd.read_csv(PAIRS_PATH, usecols=columns)
        return pairs_df[pairs_df.draw_no.isin(split_df.draw_no[split_df.half == TRAIN_HALF])]
    if set_name == "second":
        return pd.read_csv(RESERVE_PATH, usecols=columns)
    topup_df = pd.read_csv(TOPUP_PATH, usecols=columns)
    return topup_df[topup_df.draw_no.isin(pd.read_csv(TOPUP_SELECTION_PATH).draw_no)]


def google_minutes(set_name):
    routes_path = {"train": FIRST_ROUTES_PATH, "second": SECOND_ROUTES_PATH, "topup": TOPUP_ROUTES_PATH}[set_name]
    routes_df = pd.read_csv(routes_path)
    default_df = routes_df[routes_df.is_default].drop_duplicates("draw_no")
    is_scored = default_df.route_scope.isin(GOOGLE_SCOPES) & default_df.arrival_from_request_s.notna()
    return pd.DataFrame({"draw_no": default_df.draw_no.values,
                         "google_min": np.round(default_df.arrival_from_request_s.to_numpy() / SECONDS_PER_MIN),
                         "is_scored": is_scored.to_numpy()})


# --- routing (model 3 only) ------------------------------------------------------------------------
def own_dates(set_name):
    """Each pair's own date: the date of Google's departure_local (TRN-13, scoring on the own date, user 2026-10-20)."""
    google_df = pd.read_csv(GOOGLE_PATHS[set_name], usecols=["draw_no", "departure_local"])
    return pd.DataFrame({"draw_no": google_df.draw_no, "own_date": pd.to_datetime(google_df.departure_local.str[:10]).dt.date})


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (stale copy under the same name)."""
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


def route(release, mode=""):
    """Model 3 (r5py as shipped, no pathways); `--own-date`: each pair on its own date, on v2's uniquely named copies of
    the cleaned feeds (the plain names hit r5py's stale working copy for 20261016), table `shipped_owndate`."""
    is_own_date = mode == "--own-date"
    sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import
    import geopandas as gpd
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    from r5py.r5.regional_task import RegionalTask
    import inspect
    default_speed = inspect.signature(RegionalTask.__init__).parameters["speed_walking"].default
    assert default_speed == SHIPPED_WALK_SPEED_KMH, f"r5py's default walk speed is {default_speed}, not {SHIPPED_WALK_SPEED_KMH}"

    def ttm_min(network, pair, departure):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.origin_lon], [pair.origin_lat]))
        destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
            max_time=datetime.timedelta(minutes=MAX_TIME_MIN)))  # speed_walking left at r5py's default
        return matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]

    if is_own_date:
        feed_dir = DIAGNOSTIC_DATA_DIR / V2_FEED_DIR_PATTERN.format(release=release)
        gtfs_paths = [feed_dir / f"{name}_{V2_NAME}_{release}.zip" for name in FEED_NAMES]
        missing = [path.name for path in gtfs_paths if not path.exists()]
        assert not missing, f"run transit_pathway_network_v2.py feeds first (missing: {missing})"
        check_working_copies([PBF_PATH] + gtfs_paths)
        print(f"reusing {[path.name for path in gtfs_paths]}")
    elif release == "20261009":
        gtfs_paths = [OLD_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES]
    else:
        gtfs_paths = [NEW_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES]
        missing = [path.name for path in gtfs_paths if not path.exists()]
        assert not missing, f"run transit_band_metric.py route 20261016 first (cleaned feeds missing: {missing})"
        print(f"reusing {NEW_CLEANED_DIR.name} ({datetime.date.fromtimestamp(gtfs_paths[0].stat().st_mtime)})")
    set_names = [name for name, set_release in SET_RELEASE.items() if set_release == release]
    pairs_df = pd.concat([pairs_of_set(name).assign(set_name=name) for name in set_names], ignore_index=True)
    if is_own_date:
        dates_df = pd.concat([own_dates(name) for name in set_names], ignore_index=True)
        pairs_df = pairs_df.merge(dates_df, on="draw_no", how="left", validate="one_to_one")
        assert pairs_df.own_date.notna().all(), "pairs without a Google departure date"
    else:
        pairs_df["own_date"] = WINDOW_DATE
    table_tag = "shipped_owndate" if is_own_date else "shipped"
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_{table_tag}_{release}.csv"))
    table_path = saved[-1] if saved else DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_{table_tag}_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"release {release}: sets {set_names}, {len(pairs_df)} pairs; table {table_path.name}, "
          f"{len(done)} done, {len(todo_df)} to route", flush=True)
    if todo_df.empty:
        return
    network = TransportNetwork(PBF_PATH, gtfs_paths)
    for covers_date in sorted(pairs_df.own_date.unique()):
        is_covered = network.transit_layer.covers(covers_date)
        print("covers", covers_date, is_covered, flush=True)
        assert is_covered or not is_own_date, f"release {release} does not cover {covers_date}"
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        departure = datetime.datetime.combine(pair.own_date, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))
        row = {"draw_no": pair.draw_no, "shipped_min": ttm_min(network, pair, departure)}
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % 100 == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


# --- statistics ------------------------------------------------------------------------------------
def wilson(successes, n):
    if n == 0:
        return np.nan, np.nan
    share = successes / n
    centre = (share + WILSON_Z ** 2 / (2 * n)) / (1 + WILSON_Z ** 2 / n)
    half_width = WILSON_Z * np.sqrt(share * (1 - share) / n + WILSON_Z ** 2 / (4 * n ** 2)) / (1 + WILSON_Z ** 2 / n)
    return centre - half_width, centre + half_width


def recall_precision(google_min, r5_min, cut_min, r5_cut_min):
    """(both, n Google-below), (both, n R5-below); R5 below when r5_min <= r5_cut_min."""
    is_google_below, is_r5_below = google_min <= cut_min, r5_min <= r5_cut_min
    both = int((is_google_below & is_r5_below).sum())
    return (both, int(is_google_below.sum())), (both, int(is_r5_below.sum()))


def is_away(google_min):
    return np.logical_or.reduce([(google_min >= low) & (google_min <= high) for low, high in AWAY_RANGES_MIN])


def band_of(minutes, cuts_min):
    return np.select([minutes <= cuts_min[1], minutes <= cuts_min[2]], [1, 2], 3)


def fit_scalar(train_df):
    """s minimising soft_l1 of log(s N / Google) on training pairs away from the cuts, transit-won only."""
    from scipy.optimize import least_squares
    is_fit = (is_away(train_df.google_min.to_numpy()) & train_df.is_transit_won.to_numpy()
              & (train_df.google_min.to_numpy() > 0) & (train_df.n_min.to_numpy() > 0)
              & np.isfinite(train_df.n_min.to_numpy()))
    n_min, google_min = train_df.n_min.to_numpy()[is_fit], train_df.google_min.to_numpy()[is_fit]
    result = least_squares(lambda p: np.log(p[0] * n_min / google_min), [FIT_START], loss=FIT_LOSS,
                           f_scale=FIT_LOSS_SCALE, bounds=(MIN_FIT_PARAM, np.inf))
    n_excluded_zero = int((is_away(train_df.google_min.to_numpy()) & train_df.is_transit_won.to_numpy()
                           & ((train_df.google_min.to_numpy() == 0) | (train_df.n_min.to_numpy() == 0))).sum())
    return float(result.x[0]), int(is_fit.sum()), n_excluded_zero, float(np.median(np.log(google_min / n_min)))


def pair_cuts(df, transit_cuts_min):
    """Per-pair R5 cuts: transit_cuts_min on transit-won pairs, CUTS_MIN on walk pairs."""
    is_transit_won = df.is_transit_won.to_numpy()
    return {zone_no: np.where(is_transit_won, transit_cuts_min[zone_no], cut_min) for zone_no, cut_min in CUTS_MIN.items()}


def score_model(scored_df, minutes, transit_cuts_min, rng):
    """TRN-13's checks for one model; R5 cuts per pair (pair_cuts). Returns (detail lines, {check: (value text, is_pass)})."""
    from scipy.stats import binomtest
    df = scored_df.assign(model_min=minutes)
    df_cuts = pair_cuts(df, transit_cuts_min)
    google_all = df.google_min.to_numpy()
    is_away_pair = is_away(google_all) & np.isfinite(df.model_min.to_numpy())
    errors = (df.model_min - df.google_min).to_numpy()[is_away_pair]
    centred_errors = errors - np.median(errors)
    lines = [f"  error away from the cuts (model - Google): n {len(errors)}, median {np.median(errors):+.2f}, "
             f"mean {errors.mean():+.2f}, MAE {np.abs(errors).mean():.2f}; transit cuts {transit_cuts_min}, walk cuts {CUTS_MIN}"]
    checks = {}
    for zone_no, cut_min in CUTS_MIN.items():
        is_zone = (df.zone == zone_no).to_numpy()
        zone_df = df[is_zone]
        google, r5 = zone_df.google_min.to_numpy(), zone_df.model_min.to_numpy()
        r5_cut = df_cuts[zone_no][is_zone]
        (rec_k, rec_n), (prec_k, prec_n) = recall_precision(google, r5, cut_min, r5_cut)
        rec, prec = rec_k / rec_n, prec_k / prec_n if prec_n else np.nan
        rec_low, rec_high = wilson(rec_k, rec_n)
        prec_low, prec_high = wilson(prec_k, prec_n)
        sim_recall, sim_precision = [], []
        for _ in range(N_SIMULATIONS):
            sim_r5 = google + rng.choice(centred_errors, size=len(google), replace=True)
            (k_r, n_r), (k_p, n_p) = recall_precision(google, sim_r5, cut_min, cut_min)
            sim_recall.append(k_r / n_r if n_r else np.nan)
            sim_precision.append(k_p / n_p if n_p else np.nan)
        bar_recall, bar_precision = np.nanmedian(sim_recall), np.nanmedian(sim_precision)
        n_early = int(((r5 <= r5_cut) & (google > cut_min)).sum())
        n_late = int(((r5 > r5_cut) & (google <= cut_min)).sum())
        sign_p = binomtest(n_early, n_early + n_late, 0.5).pvalue if n_early + n_late else 1.0
        gap = abs(rec - prec)
        lines += [f"  zone {zone_no} (n {len(zone_df)}, Google <= {cut_min} vs model <= {transit_cuts_min[zone_no]} transit / {cut_min} walk): recall {rec:.3f} ({rec_k}/{rec_n}, "
                  f"{rec_low:.3f}-{rec_high:.3f}), precision {prec:.3f} ({prec_k}/{prec_n}, {prec_low:.3f}-{prec_high:.3f})",
                  f"    noise bar recall {bar_recall:.3f}, precision {bar_precision:.3f}; misses early {n_early}, late {n_late}, "
                  f"sign p {sign_p:.3f}, |recall - precision| {gap:.3f}"]
        checks[f"z{zone_no} recall"] = (f"{rec:.3f} ({rec_low:.2f}-{rec_high:.2f})", None)
        checks[f"z{zone_no} precision"] = (f"{prec:.3f} ({prec_low:.2f}-{prec_high:.2f})", None)
        checks[f"z{zone_no} floor"] = (f"{min(rec_low, prec_low):.3f}", rec_low > FLOOR and prec_low > FLOOR)
        checks[f"z{zone_no} noise bar"] = (f"{rec_high:.2f}/{bar_recall:.2f}, {prec_high:.2f}/{bar_precision:.2f}",
                                           rec_high >= bar_recall and prec_high >= bar_precision)
        checks[f"z{zone_no} balance"] = (f"{n_early}e/{n_late}l p {sign_p:.3f}, gap {gap:.3f}",
                                         sign_p >= SIGN_TEST_ALPHA and gap <= CLOSE_TOLERANCE)

    is_random = df.set_name.isin(RANDOM_SETS).to_numpy()
    random_df = df[is_random]
    random_cuts = {zone_no: cuts[is_random] for zone_no, cuts in df_cuts.items()}
    google_band, r5_band = band_of(random_df.google_min.to_numpy(), CUTS_MIN), band_of(random_df.model_min.to_numpy(), random_cuts)
    is_base = (google_band <= 2) & (random_df.zone == 0).to_numpy()
    is_band_miss = is_base & (r5_band != google_band)
    is_far_called = (random_df.google_min.to_numpy() > ZONES_MIN[2][1]) & (r5_band <= 2)
    n_hard = int(is_band_miss.sum() + is_far_called.sum())
    hard_low, hard_high = wilson(n_hard, int(is_base.sum()))
    lines.append(f"  hard misses: {int(is_band_miss.sum())} band swaps + {int(is_far_called.sum())} Google > {ZONES_MIN[2][1]} called "
                 f"band 1-2, over {int(is_base.sum())}: {n_hard / is_base.sum():.3f} ({hard_low:.3f}-{hard_high:.3f})")
    checks["hard misses"] = (f"{n_hard}/{int(is_base.sum())}, upper {hard_high:.3f}", hard_high <= HARD_MISS_MAX)
    for zone_no, cut_min in CUTS_MIN.items():
        n_google = int((random_df.google_min <= cut_min).sum())
        n_r5 = int((random_df.model_min.to_numpy() <= random_cuts[zone_no]).sum())
        ratio = n_r5 / n_google
        lines.append(f"  count ratio <= {cut_min}: {n_r5} / {n_google} = {ratio:.3f}")
        checks[f"ratio <= {cut_min}"] = (f"{ratio:.3f}", COUNT_RATIO_RANGE[0] <= ratio <= COUNT_RATIO_RANGE[1])
    return lines, checks


# --- scoring ---------------------------------------------------------------------------------------
def newest_table(pattern, release):
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern.format(release=release)))
    assert saved, f"no table {pattern.format(release=release)}"
    return saved[-1]


def score():
    run_date = f"{datetime.date.today():%Y%m%d}"
    out_prefix = f"{PATHWAYS_NAME}_{run_date}_compare{'_owndate' if IS_OWN_DATE else ''}" if IS_PATHWAYS else f"{NAME}_{run_date}"
    lines = [f"{NAME} {run_date}{f' ({PATHWAYS_NAME}; model 3 from the old network)' if IS_PATHWAYS else ''}: TRN-13's bars, five models, same pairs and networks ({SET_RELEASE})"]
    tables = []
    for release in ["20261009", "20261016"]:
        band_name = PATHWAYS_NAME if IS_PATHWAYS else BAND_METRIC_NAME
        band_path = newest_table(f"{band_name}_2*_routes{'_owndate' if IS_OWN_DATE else ''}_{{release}}.csv", release)
        shipped_path = newest_table(f"{NAME}_*_shipped{'_owndate' if IS_OWN_DATE else ''}_{{release}}.csv", release)
        lines.append(f"reusing {band_path.name} ({datetime.date.fromtimestamp(band_path.stat().st_mtime)}) and {shipped_path.name}")
        tables.append(pd.read_csv(band_path).merge(pd.read_csv(shipped_path), on="draw_no", how="left", indicator="shipped_row"))
    routes_df = pd.concat(tables, ignore_index=True)
    frames = [pairs_of_set(name).merge(google_minutes(name), on="draw_no", how="left").assign(set_name=name) for name in SET_RELEASE]
    df = pd.concat(frames, ignore_index=True).merge(routes_df.drop(columns="set_name"), on="draw_no", how="left")
    n_unrouted = int(df.release.isna().sum())
    n_shipped_missing = int((df.shipped_row != "both").sum())
    assert n_unrouted == 0 and n_shipped_missing == 0, f"not routed: {n_unrouted} (band metric), {n_shipped_missing} (shipped)"
    df = df.drop(columns="shipped_row")

    stock, walk, shifted = [df[column].fillna(np.inf).to_numpy() for column in ("stock_min", "walk_min", "shifted_min")]
    df["is_transit_won"] = shifted < walk
    df["n_min"] = np.where(df.is_transit_won, shifted - BOARD_SLACK_MIN, walk)            # model 1 (H, W only)
    is_settled_tie = ~df.is_transit_won.to_numpy() & (stock < walk)
    df["n_hi_trn13"] = np.where(is_settled_tie, walk - BOARD_SLACK_MIN, df.n_min)          # TRN-13's N_hi
    df["is_scored"] = df.is_scored.fillna(False).astype(bool)
    df["zone"] = 0
    for zone_no, (low, high) in ZONES_MIN.items():
        df.loc[(df.google_min >= low) & (df.google_min <= high), "zone"] = zone_no
    scored_df = df[df.is_scored].copy()
    lines.append(f"pairs {len(df)} by set {df.set_name.value_counts().to_dict()}; scored {len(scored_df)}; transit-won (H < W) "
                 f"{int(df.is_transit_won.sum())}")
    counts = {zone_no: scored_df[scored_df.zone == zone_no].set_name.value_counts().to_dict() for zone_no in ZONES_MIN}
    is_count_ok = all(counts[zone_no].get(name, 0) == expected for zone_no, by_set in EXPECTED_ZONE_COUNTS.items()
                      for name, expected in by_set.items())
    lines.append(f"stop check, zone counts {counts}: {'OK' if is_count_ok else 'MISMATCH'}")

    # the production rule drops S: what changes (model 1 vs TRN-13's N_hi)
    n_settled = int(is_settled_tie.sum())
    settled_scored_df = scored_df[is_settled_tie[df.is_scored.to_numpy()]]
    n_band_change = int((band_of(settled_scored_df.n_min.to_numpy(), CUTS_MIN) != band_of(settled_scored_df.n_hi_trn13.to_numpy(), CUTS_MIN)).sum())
    n_zone_settled = int((settled_scored_df.zone > 0).sum())
    lines.append(f"production rule (no S): ties S settles {n_settled} (expected {EXPECTED_SETTLED_TIES}: "
                 f"{'OK' if n_settled == EXPECTED_SETTLED_TIES else 'MISMATCH'}), {len(settled_scored_df)} scored, {n_zone_settled} in a zone; "
                 f"band changes vs N_hi {n_band_change}")

    train_df = scored_df[scored_df.set_name == TRAIN_SET]
    s, n_fit, n_zero, median_log = fit_scalar(train_df)
    lines.append(f"model 4 fit: s {s:.4f} on {n_fit} training pairs (away, transit-won; {n_zero} left out at 0 min); "
                 f"median-ratio s would be {np.exp(median_log):.4f}; implied cuts N <= {CUTS_MIN[1] / s:.2f}, {CUTS_MIN[2] / s:.2f} "
                 f"(whole N: <= {np.floor(CUTS_MIN[1] / s):.0f}, {np.floor(CUTS_MIN[2] / s):.0f})")
    df["scaled_min"] = np.where(df.is_transit_won, s * df.n_min, df.n_min)
    scored_df["scaled_min"] = df.scaled_min[df.is_scored].to_numpy()

    models = [("1 no-wait", scored_df.n_min.to_numpy(), CUTS_MIN),
              ("2 stock 4.16", scored_df.stock_min.fillna(np.inf).to_numpy(), CUTS_MIN),
              ("3 shipped 3.6", scored_df.shipped_min.fillna(np.inf).to_numpy(), CUTS_MIN),
              (f"4 no-wait x {s:.3f}", scored_df.scaled_min.to_numpy(), CUTS_MIN)]
    models += [(f"5 no-wait transit N<={cuts[1]},{cuts[2]}", scored_df.n_min.to_numpy(), cuts) for cuts in SHIFTED_CUTS_MIN]
    models.append(("ref TRN-13 N_hi", scored_df.n_hi_trn13.to_numpy(), CUTS_MIN))
    results = {}
    detail = []
    for label, minutes, cuts in models:
        model_lines, checks = score_model(scored_df, minutes, cuts, np.random.default_rng(SIMULATION_SEED))
        results[label] = checks
        failures = [name for name, (_, is_pass) in checks.items() if is_pass is not None and not is_pass]
        detail += [f"model {label}: {'PASS' if not failures else 'FAIL on ' + ', '.join(failures)}"] + model_lines

    floor_cuts = {zone_no: int(np.floor(cut_min / s)) for zone_no, cut_min in CUTS_MIN.items()}
    floor_label = f"5 no-wait transit N<={floor_cuts[1]},{floor_cuts[2]}"
    if floor_label in results:
        scaled_band = band_of(scored_df.scaled_min.to_numpy(), CUTS_MIN)
        shifted_band = band_of(scored_df.n_min.to_numpy(), pair_cuts(scored_df, floor_cuts))
        n_differ = int((scaled_band != shifted_band).sum())
        lines.append(f"check, model 4 = model 5 at transit cuts {floor_cuts} (whole-minute floors of cut / s): band calls differ on "
                     f"{n_differ} of {len(scored_df)} pairs: {'OK' if n_differ == 0 else 'MISMATCH'} (noise bars may differ: each "
                     f"model's own error spread)")
    table_df = pd.DataFrame({label: {name: f"{text}{'' if is_pass is None else (' ok' if is_pass else ' FAIL')}"
                                     for name, (text, is_pass) in checks.items()} for label, checks in results.items()})
    with pd.option_context("display.width", 250, "display.max_columns", 20, "display.max_colwidth", 40):
        lines += ["", "side by side (ok / FAIL against TRN-13's bars; noise bar: upper end / bar):", table_df.to_string(), ""]
    lines += detail
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{out_prefix}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")
    table_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{out_prefix}_table.csv")
    df.to_csv(DIAGNOSTIC_DATA_DIR / f"{out_prefix}_results.csv", index=False)


if __name__ == "__main__":
    if sys.argv[1] == "route":
        route(*sys.argv[2:4])
    else:
        score()
