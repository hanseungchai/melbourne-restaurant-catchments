"""Scoring weekday: does routing R5 on Wednesday 2026-10-21 instead of each pair's own date change the band calls?

Claim under test (concepts/transit.md TRN-13 Open, DESIGN.md Q23 block; user 2026-10-20): every transit scorer
(transit_band_metric.py, transit_model_compare.py, transit_pathway_network_v2.py `route`) routes R5 at the pair's drawn
minute on WINDOW_DATE (Wed 2026-10-21), while Google answered on the pair's own date (TRN-7: Mon 19 - Fri 23 Oct for the
training half). Likely a holdover of the one-Wednesday pin. Where the pipeline would rely on it: the scored model of
record (no-wait model at plain cuts 10 / 20, v2 pathways network; TRN-13) and the test half's reading (TRN-15).

Method (Claude's rules, written before any result): training half only (1,252 pairs, release 20261009, v2 pathways
network as transit_pathway_network_v2.py builds it). Each pair routed again, same three TTM calls as v2 `route`, on the
date of Google's departure_local. Wednesday pairs must reproduce the 2026-10-19 v2 table exactly (reproduction check;
a mismatch stops the reading). No-wait band call: N = shifted - BOARD_SLACK_MIN if shifted < walk else walk, bands cut
at 10.5 / 20.5 (plain cuts 10 / 20). Per weekday: minutes changed, band calls changed (later / earlier); on scored
pairs, agreement with Google's range at k = 2 (N's band is a band of some whole minute in [low_2, default_min]) on
Wednesday and on the own date. This agreement is a simple stand-in for transit_hard_miss_range's zone and hard-miss
tests, not a replica.
Bar (Claude, set before results; the user settles the scoring date): Wednesday scoring stands if band calls changed
< 1% of pairs AND agreement moves by <= 0.5 pp overall; otherwise score on the own date and rescore the training half
before the test half is opened.

Conclusion (run 2026-10-20; Claude's bar, set before results): Wednesday scoring stands. Reproduction 260 / 260
  Wednesday pairs identical. Mon-Thu: 0 band calls change. Friday: 81 / 250 pairs change minutes (mean -0.2), 4 band
  calls (1.6%; 3 now inside Google's range, 1 no longer). Overall 4 / 1,252 (0.32% < 1%); agreement 0.970 -> 0.971
  (+0.16 pp <= 0.5). The user settles the scoring date (concepts/transit.md TRN-13 Open).

Inputs (read only): transit_pathway_network_v2's derived OSM extract and feeds for 20261009 and its 2026-10-19 routes
and range results; the pairs, split and Google answers of the training half. Self-contained (CLAUDE.md D1). No API.
Usage: `python transit_scoring_weekday.py route`, then `... report`. Saved data is reused; results carry the run date.
"""
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_scoring_weekday"
V2_NAME = "transit_pathway_network_v2"
RELEASE = "20261009"
V2_RUN_DATE = "20261019"
V2_PBF_PATH = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{RELEASE}.osm.pbf"
V2_FEED_DIR = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{RELEASE}"
V2_FEED_PATHS = [V2_FEED_DIR / f"ptv_metro_train_{V2_NAME}_{RELEASE}_moved.zip",
                 V2_FEED_DIR / f"ptv_tram_{V2_NAME}_{RELEASE}.zip",
                 V2_FEED_DIR / f"ptv_metro_bus_{V2_NAME}_{RELEASE}.zip"]
V2_ROUTES_PATH = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_{V2_RUN_DATE}_routes_{RELEASE}.csv"
V2_RESULTS_PATH = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_{V2_RUN_DATE}_range_results.csv"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
GOOGLE_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.csv"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_pathway_network_v2.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE (the date under test)
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as transit_pathway_network_v2.py
SINGLE_PERCENTILE = 49                         # as transit_pathway_network_v2.py (r5py renames a lone p50)
WALK_SPEED_KMH = 4.16                          # config.WALK_SPEED_KMH
BOARD_SLACK_MIN = 1                            # as transit_pathway_network_v2.py
TRAIN_HALF = "train"
BAND_EDGES_MIN = [10.5, 20.5]                  # plain cuts 10 / 20 on whole minutes (TRN-13)
RANGE_LOW_COLUMN = "low_2"                     # Google's range at k = 2 (TRN-13)

# --- bar (Claude, set before results) --------------------------------------------------------------
MAX_CHANGED_SHARE = 0.01
MAX_AGREEMENT_MOVE_PP = 0.5


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (stale copy under the same name)."""
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


def training_pairs():
    columns = ["draw_no", "origin_lat", "origin_lon", "dest_lat", "dest_lon", "dep_day_name", "dep_min_of_day"]
    split_df = pd.read_csv(SPLIT_PATH, usecols=["draw_no", "half"])
    pairs_df = pd.read_csv(PAIRS_PATH, usecols=columns)
    pairs_df = pairs_df[pairs_df.draw_no.isin(split_df.draw_no[split_df.half == TRAIN_HALF])]
    google_df = pd.read_csv(GOOGLE_PATH, usecols=["draw_no", "departure_local"])
    pairs_df = pairs_df.merge(google_df, on="draw_no", how="left", validate="one_to_one")
    pairs_df["own_date"] = pd.to_datetime(pairs_df.departure_local.str[:10]).dt.date
    return pairs_df


def route():
    run_date = f"{datetime.date.today():%Y%m%d}"
    sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import
    import geopandas as gpd
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    assert V2_PBF_PATH.exists() and all(path.exists() for path in V2_FEED_PATHS), "v2 network files missing"
    check_working_copies([V2_PBF_PATH] + V2_FEED_PATHS)
    print(f"reusing {V2_PBF_PATH.name} ({datetime.date.fromtimestamp(V2_PBF_PATH.stat().st_mtime)}) and "
          f"{[path.name for path in V2_FEED_PATHS]}", flush=True)
    network = TransportNetwork(V2_PBF_PATH, V2_FEED_PATHS)
    pairs_df = training_pairs()
    for own_date in sorted(pairs_df.own_date.unique()):
        is_covered = network.transit_layer.covers(own_date)
        print("covers", own_date, is_covered, flush=True)
        assert is_covered, f"release {RELEASE} does not cover {own_date}"

    def ttm_min(pair, departure, transport_modes, max_time_min):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.origin_lon], [pair.origin_lat]))
        destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=transport_modes, max_time=datetime.timedelta(minutes=max_time_min),
            speed_walking=WALK_SPEED_KMH))
        return matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]

    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_routes_{RELEASE}.csv"))
    table_path = saved[-1] if saved else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_routes_{RELEASE}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"{len(pairs_df)} pairs; table {table_path.name}, {len(done)} done, {len(todo_df)} to route", flush=True)
    transit_modes = [TransportMode.TRANSIT, TransportMode.WALK]
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        departure = datetime.datetime.combine(pair.own_date, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))
        shifted_departure = departure - datetime.timedelta(minutes=BOARD_SLACK_MIN)
        row = {"draw_no": pair.draw_no, "own_date": pair.own_date, "dep_day_name": pair.dep_day_name,
               "stock_min": ttm_min(pair, departure, transit_modes, MAX_TIME_MIN),
               "shifted_min": ttm_min(pair, shifted_departure, transit_modes, MAX_TIME_MIN + BOARD_SLACK_MIN),
               "walk_min": ttm_min(pair, departure, [TransportMode.WALK], MAX_TIME_MIN)}
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % 100 == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


# --- report ----------------------------------------------------------------------------------------
def no_wait_min(routes_df):
    shifted, walk = routes_df.shifted_min.fillna(np.inf), routes_df.walk_min.fillna(np.inf)
    return pd.Series(np.where(shifted < walk, shifted - BOARD_SLACK_MIN, walk), index=routes_df.index)


def band(minutes):
    return np.digitize(minutes, BAND_EDGES_MIN)


def agrees_with_range(n_min, low_min, default_min):
    """N's band is the band of some whole minute in Google's range [low, default] (bands are contiguous)."""
    return (band(n_min) >= band(low_min)) & (band(n_min) <= band(default_min))


def report():
    run_date = f"{datetime.date.today():%Y%m%d}"
    own_df = pd.read_csv(sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_routes_{RELEASE}.csv"))[-1])
    wed_df = pd.read_csv(V2_ROUTES_PATH)
    both = wed_df.merge(own_df, on="draw_no", suffixes=("_wed", "_own"), validate="one_to_one")
    results_df = pd.read_csv(V2_RESULTS_PATH)
    results_df = results_df[results_df.set_name == TRAIN_HALF][["draw_no", "is_scored", "default_min", RANGE_LOW_COLUMN]]
    both = both.merge(results_df, on="draw_no", how="left", validate="one_to_one")
    for tag in ("wed", "own"):
        part = both[[f"stock_min_{tag}", f"shifted_min_{tag}", f"walk_min_{tag}"]]
        part.columns = ["stock_min", "shifted_min", "walk_min"]
        both[f"n_{tag}"] = no_wait_min(part)
        both[f"band_{tag}"] = band(both[f"n_{tag}"])
        both[f"agree_{tag}"] = agrees_with_range(both[f"n_{tag}"], both[RANGE_LOW_COLUMN], both.default_min)
    lines = [f"{NAME} {run_date}: training half, release {RELEASE}, v2 pathways network; R5 on {WINDOW_DATE} "
             f"(v2 {V2_RUN_DATE} table) vs on Google's own date; no-wait plain cuts 10 / 20; agreement = band within "
             f"Google's range at k = 2 ([{RANGE_LOW_COLUMN}, default_min]), scored pairs"]
    is_wed = both.own_date == f"{WINDOW_DATE}"
    columns = ["stock_min", "shifted_min", "walk_min"]
    wed_part = both[is_wed]
    mismatch = sum(int((wed_part[f"{c}_wed"].fillna(-1) != wed_part[f"{c}_own"].fillna(-1)).sum()) for c in columns)
    lines.append(f"reproduction check (Wednesday pairs, {len(wed_part)}): {mismatch} differing values: "
                 f"{'PASS' if mismatch == 0 else 'FAIL (reading stops here)'}")
    rows = []
    for label, group in list(both.groupby("dep_day_name", sort=False)) + [("all", both), ("not Wed", both[~is_wed])]:
        scored = group[group.is_scored.fillna(False).astype(bool)]
        changed = group.band_own != group.band_wed
        rows.append({"day": label, "date": ",".join(sorted(group.own_date.unique())) if label not in ("all", "not Wed") else "",
                     "pairs": len(group),
                     "n_min_changed": int((group.n_own.fillna(np.inf) != group.n_wed.fillna(np.inf)).sum()),
                     "n_min_mean_change": (group.n_own - group.n_wed).replace([np.inf, -np.inf], np.nan).mean(),
                     "band_changed": int(changed.sum()), "band_changed_share": changed.mean(),
                     "later": int((group.band_own > group.band_wed).sum()), "earlier": int((group.band_own < group.band_wed).sum()),
                     "scored": len(scored), "agree_wed": scored.agree_wed.mean(), "agree_own": scored.agree_own.mean(),
                     "agree_move_pp": 100 * (scored.agree_own.mean() - scored.agree_wed.mean()),
                     "fixed": int((scored.agree_own & ~scored.agree_wed).sum()),
                     "broken": int((~scored.agree_own & scored.agree_wed).sum())})
    table_df = pd.DataFrame(rows)
    order = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "all": 5, "not Wed": 6}
    table_df = table_df.sort_values("day", key=lambda s: s.map(order))
    lines.append(table_df.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    overall = table_df[table_df.day == "all"].iloc[0]
    is_kept = overall.band_changed_share < MAX_CHANGED_SHARE and abs(overall.agree_move_pp) <= MAX_AGREEMENT_MOVE_PP
    lines.append(f"bar: band calls changed {overall.band_changed_share:.3%} (< {MAX_CHANGED_SHARE:.0%}) and agreement move "
                 f"{overall.agree_move_pp:+.2f} pp (|.| <= {MAX_AGREEMENT_MOVE_PP}): "
                 f"{'Wednesday scoring stands' if is_kept else 'own-date scoring recommended; rescore the training half'}")
    changed_df = both[both.band_own != both.band_wed][["draw_no", "dep_day_name", "own_date", "n_wed", "n_own",
                                                       "default_min", RANGE_LOW_COLUMN, "agree_wed", "agree_own"]]
    lines.append(f"changed band calls ({len(changed_df)}):")
    lines.append(changed_df.to_string(index=False) if len(changed_df) else "  none")
    text = "\n".join(lines)
    print(text)
    both.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_pairs.csv", index=False)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(text + "\n")


if __name__ == "__main__":
    {"route": route, "report": report}[sys.argv[1]]()
