"""Sample transit pairs stage (TRN-7, TRN-10, T3-T5): origin-destination draws for validating r5py
against Google transit, and their train / test split. Free: r5py only, no API.

1. Draw (draw_transit_pairs): origin hex weighted by residents or workers (p = 0.5), destination a venue
   drawn uniformly, as drive (ODS-2). Candidates farther apart than config.TRANSIT_PREFILTER_KM skip r5py
   and are rejected; the rest are kept if r5py's fastest time over the weekday (percentile
   config.TRANSIT_WINDOW_PERCENTILE over config.TRANSIT_WINDOW_HOURS on config.TRANSIT_WINDOW_DATE) is
   within config.TRANSIT_WINDOW_S. config.TRANSIT_SMOKE_TEST_N pairs r5py placed over the window are drawn
   as the T5 smoke test. Each pair gets a weekday and minute (TRN-7: mean of the two drive draws' rules,
   per-pair streams); its date is assigned later, from the release it is fetched under.
   r5py runs in config.TRANSIT_DRAW_N_PROCESSES worker processes; results are checkpointed per batch, so
   a stopped draw resumes where it left off.
2. Split (split_transit_pairs): train / test halves grouped by destination hex, CV folds inside the
   training half, and the exploration subset; written once. Smoke-test pairs are in neither half.
3. Extend (extend_transit_checkpoint): optional, after the split; routes the same random stream further,
   into the checkpoint only, so a larger draw later costs no new routing.
4. Reserve (draw_transit_set("reserve")): the second batch's pairs, replayed from the checkpoint (TRN-10).
5. Top-up (draw_transit_topup): boundary top-up candidates on haversine ranges only, no r5py (TRN-14).
6. Test-half extension (TRN-15): screen_transit_stream("test_ext") screens the stream on past the
   checkpoint's end on the next release, into its own checkpoint; draw_transit_set("test_ext") replays both
   checkpoints for the pairs past the reserve.
7. Fresh holdout (user, 2026-10-21): screen_transit_stream("holdout") screens the stream on past the
   extension by the same gate, into a third checkpoint; draw_transit_set("holdout") replays all three for the
   pairs past the test extension. Drawn only; a fetch needs its own go (S5).
The stream sets (4, 6, 7) are listed in STREAM_SETS, in stream order.
"""
import json
from io import StringIO
from collections import Counter
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
import pyogrio
from sklearn.model_selection import StratifiedGroupKFold

import config
from functions import pt_network
from functions.geometry import haversine_m
from functions.output_helper import is_already_built
from functions.pair_sampling import assign_venue_hex, departure_probabilities
from functions.subject_paths import subject_layers_file
from functions.transit_window import FASTEST_MIN_COL, TransitWindowPool

# Hex nodes table and venue table columns read here (as drive_samples).
HEX_ID_COL = "hex_id"
RESIDENTS_COL, WORKERS_COL = "residents", "workers"
CENTROID_LAT_COL, CENTROID_LON_COL = "centroid_lat", "centroid_lon"
PLACE_ID_COL, VENUE_LAT_COL, VENUE_LON_COL = "place_id", "lat", "lng"

# Opening-hours histogram (opening_hours.build_opening_hours), as drive_samples reads it.
HOURS_WEEKDAY_COL, HOURS_DAY_COL, HOURS_DAY_NAME_COL = "weekday", "day", "day_name"
HOURS_MINUTE_OF_WEEK_COL, HOURS_OPEN_COL = "minute_of_week", "n_open"
GOOGLE_WEEKDAYS = [1, 2, 3, 4, 5]  # Google's day index: 1 = Mon ... 5 = Fri
MIN_PER_HOUR = 60
SLOTS_PER_DAY = 24 * MIN_PER_HOUR // config.HOURS_SLOT_MIN

# Random streams: the pair draw uses TRANSIT_PAIRS_SEED itself; these are child streams.
SMOKE_TEST_STREAM = 1                       # under TRANSIT_PAIRS_SEED
CELL_STREAM, MINUTE_STREAM = 1, 2           # under TRANSIT_DEPARTURE_SEED, per draw_no (date: later)
EXPLORATION_STREAM = 1                      # under TRANSIT_SPLIT_SEED
ORIGIN_POOLS = np.array(["resident", "worker"])

DRAW_NO_COL = "draw_no"
POOL_COL, DEST_HEX_COL = "pool", "dest_hex"
M_PER_KM = 1000
N_FASTEST_PRINTED = 10                      # highest straight-line speeds shown in the draw's log
CHECKPOINT_SUFFIX = ".evaluated.csv"        # r5py result per evaluated draw_no
CHECKPOINT_META_SUFFIX = ".evaluated.json"  # the settings the checkpoint was made under
RANGE_COL_FORMAT = "in_range_{}"            # top-up: the pair is listed for that zone's range (TRN-14)
TEST_EXT_CHECKPOINT_SUFFIX_FORMAT = ".evaluated_{}.csv"        # checkpoint screened on that release (TRN-15)
TEST_EXT_CHECKPOINT_META_SUFFIX_FORMAT = ".evaluated_{}.json"
HOLDOUT_CHECKPOINT_SUFFIX_FORMAT = ".evaluated_{}_holdout.csv"      # fresh holdout's own checkpoint (2026-10-21)
HOLDOUT_CHECKPOINT_META_SUFFIX_FORMAT = ".evaluated_{}_holdout.json"
RELEASE_COL = "window_release"              # PTV export date a pair was screened on, as text
# _screen_row's outcomes; the drop reasons are also the draw log's counts keys.
SAME_HEX, PREFILTER, DUPLICATE_PAIR = "same_hex", "prefilter", "duplicate_pair"
OVER_WINDOW, ZERO_TIME_ARTEFACT, KEPT = "over_window", "zero_time_artefact", "kept"


class StreamSet(NamedTuple):
    """A pair set taken from the draw's random stream past the draw (module docstring, steps 4, 6, 7)."""
    n_pairs: int                    # in-window pairs the set takes
    pairs_path: Path                # the set's pairs file (subject_layers_file applied at use)
    checkpoint_suffix_formats: tuple | None  # (csv, json) of its own checkpoint; None = screened into the draw's
    screen_release: str             # release its checkpoint rows were screened on
    n_screened: int                 # in-window pairs its screen adds past the sets before it


# In stream order: each set takes the in-window pairs past the one before it.
STREAM_SETS = {
    "reserve": StreamSet(config.TRANSIT_RESERVE_N, config.TRANSIT_RESERVE_PAIRS_PATH, None,
                         config.TRANSIT_DRAW_RELEASE, config.TRANSIT_RESERVE_SCREEN_PAIRS),
    "test_ext": StreamSet(config.TRANSIT_TEST_EXT_N, config.TRANSIT_TEST_EXT_PAIRS_PATH,
                          (TEST_EXT_CHECKPOINT_SUFFIX_FORMAT, TEST_EXT_CHECKPOINT_META_SUFFIX_FORMAT),
                          config.TRANSIT_SECOND_RELEASE, config.TRANSIT_TEST_EXT_SCREEN_PAIRS),
    "holdout": StreamSet(config.TRANSIT_HOLDOUT_N, config.TRANSIT_HOLDOUT_PAIRS_PATH,
                         (HOLDOUT_CHECKPOINT_SUFFIX_FORMAT, HOLDOUT_CHECKPOINT_META_SUFFIX_FORMAT),
                         config.TRANSIT_SECOND_RELEASE, config.TRANSIT_HOLDOUT_N),
}


def _weekday_hist(hist_path):
    """Weekday open-share histogram, Mon-Fri x slots (row 0 = Mon), and each slot's day name."""
    hours_df = pd.read_csv(hist_path)
    weekday_hours_df = hours_df[hours_df[HOURS_WEEKDAY_COL]].sort_values(HOURS_MINUTE_OF_WEEK_COL)
    assert (list(weekday_hours_df[HOURS_DAY_COL].unique()) == GOOGLE_WEEKDAYS
            and len(weekday_hours_df) == len(GOOGLE_WEEKDAYS) * SLOTS_PER_DAY), "expected Mon-Fri x 48 slots"
    hist = weekday_hours_df[HOURS_OPEN_COL].to_numpy(float).reshape(len(GOOGLE_WEEKDAYS), SLOTS_PER_DAY)
    return hist, weekday_hours_df[HOURS_DAY_NAME_COL].to_numpy()


def _draw_departures(pairs_df):
    """Weekday slot and minute per pair (TRN-7 A, D): the equal-weight mean of each hours pull's
    slot-probability vector, then a uniform minute in the slot; one child stream per draw_no."""
    hists = [_weekday_hist(path) for path in config.TRANSIT_DEPARTURE_HIST_PATHS]
    assert all((names == hists[0][1]).all() for _, names in hists), "hours pulls disagree on slot order"
    p_departure = np.mean([departure_probabilities(hist) for hist, _ in hists], axis=0)
    cells = np.array([np.random.default_rng([config.TRANSIT_DEPARTURE_SEED, CELL_STREAM, draw_no])
                      .choice(p_departure.size, p=p_departure) for draw_no in pairs_df[DRAW_NO_COL]])
    minutes = np.array([np.random.default_rng([config.TRANSIT_DEPARTURE_SEED, MINUTE_STREAM, draw_no])
                        .integers(0, config.HOURS_SLOT_MIN) for draw_no in pairs_df[DRAW_NO_COL]])
    pairs_df = pairs_df.copy()
    pairs_df["dep_day"] = cells // SLOTS_PER_DAY + 1                       # Google index: 1 = Mon ... 5 = Fri
    pairs_df["dep_day_name"] = hists[0][1][cells]
    pairs_df["dep_slot_min"] = (cells % SLOTS_PER_DAY) * config.HOURS_SLOT_MIN
    pairs_df["dep_min_of_day"] = pairs_df.dep_slot_min + minutes
    pairs_df["dep_p"] = p_departure[cells]
    return pairs_df


def _checkpoint_meta(release=config.TRANSIT_DRAW_RELEASE, gtfs_dir_name=config.PT_GTFS_DIR.name,
                     walk_speed_kmh=config.WALK_SPEED_KMH):
    """The settings an r5py checkpoint depends on; a resume must match them."""
    return {"seed": config.TRANSIT_PAIRS_SEED, "batch": config.TRANSIT_DRAW_BATCH,
            "window_s": config.TRANSIT_WINDOW_S, "window_date": str(config.TRANSIT_WINDOW_DATE),
            "window_hours": list(config.TRANSIT_WINDOW_HOURS), "percentile": config.TRANSIT_WINDOW_PERCENTILE,
            "prefilter_km": config.TRANSIT_PREFILTER_KM, "release": release,
            "gtfs_dir": gtfs_dir_name, "walk_speed_kmh": walk_speed_kmh}


def _load_checkpoint(checkpoint_path, meta_path, meta):
    """Evaluated draw_no -> fastest minutes from an earlier run made under meta; empty if none."""
    if not checkpoint_path.exists():
        meta_path.write_text(json.dumps(meta, indent=2))
        return pd.DataFrame(columns=[DRAW_NO_COL, FASTEST_MIN_COL])
    saved_meta = json.loads(meta_path.read_text())
    if saved_meta != meta:
        raise RuntimeError(f"{checkpoint_path.name} was made under other settings: {saved_meta}. "
                           "Rename it, or restore those settings.")
    evaluated_df = pd.read_csv(checkpoint_path)
    print(f"resuming: {len(evaluated_df):,} candidates already evaluated by r5py")
    return evaluated_df


def _draw_inputs(subject_lat, subject_lon, counts):
    """Hexes, venues (one row per place ID, each on its hex) and the two origin pools' probabilities."""
    hexes_df = pyogrio.read_dataframe(subject_layers_file(config.HEX_NODES_PATH, subject_lat, subject_lon),
                                      columns=[HEX_ID_COL, RESIDENTS_COL, WORKERS_COL,
                                               CENTROID_LAT_COL, CENTROID_LON_COL], read_geometry=False)
    venues_df = pd.read_csv(config.VENUE_TABLES[config.HEX_VENUES_DATE])
    counts["venue_dup_rows"] = len(venues_df) - venues_df[PLACE_ID_COL].nunique()
    venues_df, counts["venue_off_grid"] = assign_venue_hex(venues_df.drop_duplicates(PLACE_ID_COL), hexes_df)
    print(f"{len(hexes_df):,} hexes, {len(venues_df):,} venues ({counts['venue_off_grid']} off grid)")
    p_residents = hexes_df[RESIDENTS_COL].fillna(0).to_numpy(float, copy=True)
    p_residents /= p_residents.sum()
    p_workers = hexes_df[WORKERS_COL].fillna(0).to_numpy(float, copy=True)
    p_workers /= p_workers.sum()
    return hexes_df, venues_df, p_residents, p_workers


def _candidate_batches(hexes_df, venues_df, p_residents, p_workers, seed=config.TRANSIT_PAIRS_SEED, first_draw_no=1):
    """Candidates, config.TRANSIT_DRAW_BATCH at a time, without end: one random stream (seed; the draw's
    is TRANSIT_PAIRS_SEED) drawn by the same calls in the same order for every caller, so a draw_no names
    the same candidate in the draw and in its checkpoint extension. draw_no counts from first_draw_no."""
    rng = np.random.default_rng(seed)
    batch = config.TRANSIT_DRAW_BATCH
    batch_no = 0
    while True:
        pool = rng.choice(ORIGIN_POOLS, size=batch)
        origin_by_residents = rng.choice(len(hexes_df), size=batch, p=p_residents)
        origin_by_workers = rng.choice(len(hexes_df), size=batch, p=p_workers)
        origin_ix = np.where(pool == ORIGIN_POOLS[0], origin_by_residents, origin_by_workers)
        venue_ix = rng.integers(len(venues_df), size=batch)
        batch_df = pd.DataFrame({
            DRAW_NO_COL: first_draw_no + batch_no * batch + np.arange(batch), POOL_COL: pool,
            "origin_hex": hexes_df[HEX_ID_COL].to_numpy()[origin_ix],
            "origin_lat": hexes_df[CENTROID_LAT_COL].to_numpy()[origin_ix],
            "origin_lon": hexes_df[CENTROID_LON_COL].to_numpy()[origin_ix],
            PLACE_ID_COL: venues_df[PLACE_ID_COL].to_numpy()[venue_ix],
            DEST_HEX_COL: venues_df[HEX_ID_COL].to_numpy()[venue_ix],
            "dest_lat": venues_df[VENUE_LAT_COL].to_numpy()[venue_ix],
            "dest_lon": venues_df[VENUE_LON_COL].to_numpy()[venue_ix]})
        batch_df["haversine_m"] = haversine_m(batch_df.origin_lat, batch_df.origin_lon,
                                              batch_df.dest_lat, batch_df.dest_lon)
        batch_no += 1
        yield batch_df


def _screen_row(row, fastest_by_draw_no, seen):
    """The draw's keep rules for one candidate, in order: the reason it is dropped (a counts key) or KEPT.
    seen holds the (origin_hex, place_id) pairs already kept. Raises KeyError if a candidate that passes
    the first three rules has no r5py result in fastest_by_draw_no."""
    if row.origin_hex == row.dest_hex:
        return SAME_HEX
    if row.haversine_m > config.TRANSIT_PREFILTER_KM * M_PER_KM:
        return PREFILTER
    if (row.origin_hex, row.place_id) in seen:
        return DUPLICATE_PAIR
    fastest_min = fastest_by_draw_no[row.draw_no]
    if pd.isna(fastest_min):
        return OVER_WINDOW
    if fastest_min == 0 and row.haversine_m > config.TRANSIT_ZERO_TIME_MAX_M:
        return ZERO_TIME_ARTEFACT
    return KEPT


def _draw_until(n_kept, checkpoint_path, meta_path, inputs, counts, gtfs_paths=None, meta=None,
                walk_speed_kmh=config.WALK_SPEED_KMH, prior_df=None):
    """Route candidates batch by batch (r5py on gtfs_paths, walking at walk_speed_kmh, checkpointed under
    meta) and keep them by the draw's rules until n_kept are in the window; the batch that reaches n_kept
    is routed whole. prior_df: results of an earlier checkpoint, read only, never routed again. Defaults:
    the pipeline's network and walk speed. Returns the kept and the over-window candidates as lists of rows."""
    if gtfs_paths is None:
        gtfs_paths = [config.PT_GTFS_CLEANED_DIR / f"{name}.zip" for name in config.PT_GTFS_SOURCE_PATHS]
    evaluated_df = _load_checkpoint(checkpoint_path, meta_path, _checkpoint_meta() if meta is None else meta)
    if prior_df is not None:
        evaluated_df = pd.concat([prior_df[[DRAW_NO_COL, FASTEST_MIN_COL]], evaluated_df], ignore_index=True)
    fastest_by_draw_no = dict(zip(evaluated_df[DRAW_NO_COL], evaluated_df[FASTEST_MIN_COL]))
    kept, over_window, seen = [], [], set()
    batches = _candidate_batches(*inputs)
    with TransitWindowPool(config.TRANSIT_DRAW_N_PROCESSES, config.TRANSIT_DRAW_R5_MAX_MEMORY,
                           config.ROAD_EXTRACT_PBF_PATH, gtfs_paths) as window_pool:
        while len(kept) < n_kept:
            batch_df = next(batches)
            counts["batches"] += 1
            is_routed = ((batch_df.origin_hex != batch_df[DEST_HEX_COL])
                         & (batch_df.haversine_m <= config.TRANSIT_PREFILTER_KM * M_PER_KM))
            to_route_df = batch_df[is_routed & ~batch_df[DRAW_NO_COL].isin(fastest_by_draw_no)]
            if len(to_route_df):
                print(f"batch {counts['batches']}: routing {len(to_route_df):,} candidates "
                      f"({to_route_df.origin_hex.nunique():,} origins); kept so far {len(kept):,}")
                result_df = window_pool.fastest_minutes(
                    to_route_df, config.TRANSIT_WINDOW_DATE, config.TRANSIT_WINDOW_HOURS,
                    config.TRANSIT_WINDOW_PERCENTILE, config.TRANSIT_WINDOW_S, config.TRANSIT_DRAW_CHUNK_ORIGINS,
                    walk_speed_kmh)
                result_df.to_csv(checkpoint_path, mode="a", header=not checkpoint_path.exists(), index=False)
                fastest_by_draw_no.update(zip(result_df[DRAW_NO_COL], result_df[FASTEST_MIN_COL]))

            for row in batch_df.itertuples(index=False):
                counts["drawn"] += 1
                reason = _screen_row(row, fastest_by_draw_no, seen)
                if reason == OVER_WINDOW:
                    over_window.append(row._asdict())
                if reason != KEPT:
                    counts[reason] += 1
                    continue
                seen.add((row.origin_hex, row.place_id))
                kept.append({**row._asdict(), FASTEST_MIN_COL: fastest_by_draw_no[row.draw_no]})
                if len(kept) == n_kept:
                    break
    return kept, over_window


def draw_transit_pairs(subject_lat, subject_lon, should_rebuild=False):
    """Draw the transit pairs (module docstring, step 1); writes config.TRANSIT_PAIRS_PATH and its log.
    Skipped if the draw exists: Google times will be keyed to it by draw_no."""
    out_path = Path(subject_layers_file(config.TRANSIT_PAIRS_PATH, subject_lat, subject_lon))
    log_path = subject_layers_file(config.TRANSIT_PAIRS_LOG_PATH, subject_lat, subject_lon)
    if is_already_built([out_path, log_path], should_rebuild):
        return pd.read_csv(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    inputs = _draw_inputs(subject_lat, subject_lon, counts)
    kept, over_window = _draw_until(config.TRANSIT_N_PAIRS, out_path.with_suffix(CHECKPOINT_SUFFIX),
                                    out_path.with_suffix(CHECKPOINT_META_SUFFIX), inputs, counts)

    kept_df = pd.DataFrame(kept).assign(is_smoke_test=False)
    over_window_df = pd.DataFrame(over_window)
    smoke_ix = np.random.default_rng([config.TRANSIT_PAIRS_SEED, SMOKE_TEST_STREAM]).choice(
        len(over_window_df), size=config.TRANSIT_SMOKE_TEST_N, replace=False)
    smoke_df = over_window_df.iloc[np.sort(smoke_ix)].assign(**{FASTEST_MIN_COL: np.nan, "is_smoke_test": True})
    pairs_df = pd.concat([kept_df, smoke_df], ignore_index=True).sort_values(DRAW_NO_COL, ignore_index=True)
    pairs_df["window_release"] = config.TRANSIT_DRAW_RELEASE
    pairs_df = _draw_departures(pairs_df)
    # descriptive only, drops nothing: straight-line speed of r5py's fastest trip, walk and wait included
    pairs_df["haversine_kmh"] = pairs_df.haversine_m / M_PER_KM / (pairs_df[FASTEST_MIN_COL] / MIN_PER_HOUR)

    counts["kept"], counts["smoke_test"] = len(kept_df), len(smoke_df)
    counts["accept_rate"] = len(kept_df) / counts["drawn"]
    print("\nSampling log:", dict(counts))
    print(f"r5py fastest minutes (kept): {pairs_df[FASTEST_MIN_COL].describe().round(1).to_dict()}")
    print(f"haversine km/h (kept): {pairs_df.haversine_kmh.describe().round(1).to_dict()}; fastest pairs:")
    print(pairs_df.nlargest(N_FASTEST_PRINTED, "haversine_kmh")[
        [DRAW_NO_COL, "haversine_m", FASTEST_MIN_COL, "haversine_kmh"]].round(1).to_string(index=False))
    pairs_df.to_csv(out_path, index=False)
    with open(log_path, "w") as log_file:
        json.dump({key: float(value) for key, value in counts.items()}, log_file, indent=2)
    print(f"saved {len(pairs_df):,} pairs to {out_path}")
    return pairs_df


def extend_transit_checkpoint(subject_lat, subject_lon):
    """Route further candidates of the draw's random stream until config.TRANSIT_RESERVE_SCREEN_PAIRS more pairs
    than config.TRANSIT_N_PAIRS would be kept, appending to the draw's r5py checkpoint only. The draw and
    its split are not touched; a later rebuild with TRANSIT_N_PAIRS raised by up to that many reads these
    rows instead of routing them. Runs only once the draw and its split exist."""
    out_path = Path(subject_layers_file(config.TRANSIT_PAIRS_PATH, subject_lat, subject_lon))
    split_path = Path(subject_layers_file(config.TRANSIT_SPLIT_PATH, subject_lat, subject_lon))
    if not (out_path.exists() and split_path.exists()):
        raise FileNotFoundError(f"extend the checkpoint only after the draw and its split exist: "
                                f"{out_path.name} {out_path.exists()}, {split_path.name} {split_path.exists()}")
    checkpoint_path = out_path.with_suffix(CHECKPOINT_SUFFIX)
    n_rows_before = len(pd.read_csv(checkpoint_path, usecols=[DRAW_NO_COL]))
    counts = Counter()
    inputs = _draw_inputs(subject_lat, subject_lon, counts)
    kept, _ = _draw_until(config.TRANSIT_N_PAIRS + config.TRANSIT_RESERVE_SCREEN_PAIRS, checkpoint_path,
                          out_path.with_suffix(CHECKPOINT_META_SUFFIX), inputs, counts)
    n_rows_added = len(pd.read_csv(checkpoint_path, usecols=[DRAW_NO_COL])) - n_rows_before
    print(f"checkpoint extended: {counts['batches']} batches, {n_rows_added:,} rows appended; "
          f"{len(kept):,} pairs in window through draw_no {kept[-1][DRAW_NO_COL]:,}")


def _second_release_gtfs_paths():
    """config.TRANSIT_SECOND_RELEASE's feeds cleaned as construct_pt_graph cleans them (empty tables and
    excluded route types dropped, TRN-11), each named <feed>_<release>.zip so r5py's cache, keyed by file
    name, can't hand back another release's copy. Made once, then reused."""
    config.TRANSIT_SECOND_GTFS_CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    gtfs_paths = []
    for feed_name, src_path in config.TRANSIT_SECOND_GTFS_SOURCE_PATHS.items():
        dst_path = config.TRANSIT_SECOND_GTFS_CLEANED_DIR / f"{feed_name}_{config.TRANSIT_SECOND_RELEASE}.zip"
        if not dst_path.exists():
            rows_to_drop = pt_network.excluded_route_type_rows(src_path, config.PT_EXCLUDED_ROUTE_TYPES)
            dropped_tables = pt_network.copy_gtfs_dropping_empty(src_path, dst_path, rows_to_drop)
            print(f"{feed_name}: cleaned copy made; empty tables dropped {dropped_tables}")
        gtfs_paths.append(dst_path)
    return gtfs_paths


def _checkpoint_paths(set_name, draw_path):
    """A stream set's own checkpoint and its settings file, next to the draw's."""
    stream_set = STREAM_SETS[set_name]
    csv_format, meta_format = stream_set.checkpoint_suffix_formats
    return (draw_path.with_suffix(csv_format.format(stream_set.screen_release)),
            draw_path.with_suffix(meta_format.format(stream_set.screen_release)))


def _sets_through(set_name):
    """The stream sets up to and including set_name, in stream order."""
    set_names = list(STREAM_SETS)
    return set_names[:set_names.index(set_name) + 1]


def _evaluated_checkpoints(draw_path, set_names):
    """The draw's checkpoint and the own checkpoints of set_names, each row with the release it was
    screened on (RELEASE_COL)."""
    frames = [pd.read_csv(draw_path.with_suffix(CHECKPOINT_SUFFIX)).assign(**{RELEASE_COL: config.TRANSIT_DRAW_RELEASE})]
    for set_name in set_names:
        if STREAM_SETS[set_name].checkpoint_suffix_formats is not None:
            checkpoint_path, _ = _checkpoint_paths(set_name, draw_path)
            frames.append(pd.read_csv(checkpoint_path).assign(**{RELEASE_COL: STREAM_SETS[set_name].screen_release}))
    return pd.concat(frames, ignore_index=True)


def screen_transit_stream(set_name, subject_lat, subject_lon):
    """Route the draw's random stream on past the earlier sets' checkpoints until the set's n_screened more
    pairs are in window: the draw's gate (stock r5py at config.TRANSIT_DRAW_WALK_SPEED_KMH, the draw's window)
    on config.TRANSIT_SECOND_RELEASE's feeds (TRN-15; user, 2026-10-20). New rows go to the set's own
    checkpoint; earlier checkpoints are only read. Resumes like the draw. The reserve, screened into the
    draw's checkpoint, has extend_transit_checkpoint instead."""
    if STREAM_SETS[set_name].checkpoint_suffix_formats is None:
        raise ValueError(f"{set_name} is screened into the draw's checkpoint: extend_transit_checkpoint")
    draw_path = Path(subject_layers_file(config.TRANSIT_PAIRS_PATH, subject_lat, subject_lon))
    set_names = _sets_through(set_name)
    prior_df = _evaluated_checkpoints(draw_path, set_names[:-1])
    checkpoint_path, meta_path = _checkpoint_paths(set_name, draw_path)
    meta = _checkpoint_meta(STREAM_SETS[set_name].screen_release, config.TRANSIT_SECOND_GTFS_DIR.name,
                            config.TRANSIT_DRAW_WALK_SPEED_KMH)
    n_kept = config.TRANSIT_N_PAIRS + sum(STREAM_SETS[name].n_screened for name in set_names)
    counts = Counter()
    inputs = _draw_inputs(subject_lat, subject_lon, counts)
    kept, _ = _draw_until(n_kept, checkpoint_path, meta_path, inputs, counts, _second_release_gtfs_paths(), meta,
                          config.TRANSIT_DRAW_WALK_SPEED_KMH, prior_df)
    screened_df = pd.read_csv(checkpoint_path)
    assert not set(screened_df[DRAW_NO_COL]) & set(prior_df[DRAW_NO_COL]), "a draw_no is in two checkpoints"
    print(f"{set_name} checkpoint: {len(screened_df):,} rows, draw_no {screened_df[DRAW_NO_COL].min():,}-"
          f"{screened_df[DRAW_NO_COL].max():,}; {len(kept):,} pairs in window through draw_no {kept[-1][DRAW_NO_COL]:,}")


def split_transit_pairs(subject_lat, subject_lon, should_rebuild=False):
    """Split the in-window pairs once (T3): train / test halves grouped by destination hex and
    stratified by origin pool, config.TRANSIT_CV_FOLDS folds inside the training half by the same rule,
    and config.TRANSIT_EXPLORATION_N training-half pairs flagged for the first fetch (TRN-10). Smoke-test
    pairs get half "smoke_test". Writes config.TRANSIT_SPLIT_PATH: draw_no, dest_hex, pool, half, fold,
    is_exploration. Skipped if the file exists: the test half must stay the same pairs."""
    out_path = subject_layers_file(config.TRANSIT_SPLIT_PATH, subject_lat, subject_lon)
    if is_already_built([out_path], should_rebuild):
        return pd.read_csv(out_path)
    pairs_df = pd.read_csv(subject_layers_file(config.TRANSIT_PAIRS_PATH, subject_lat, subject_lon),
                           usecols=[DRAW_NO_COL, DEST_HEX_COL, POOL_COL, "is_smoke_test"])
    in_window_df = pairs_df[~pairs_df.is_smoke_test].reset_index(drop=True)

    halves = StratifiedGroupKFold(n_splits=config.TRANSIT_SPLIT_N_HALVES, shuffle=True,
                                  random_state=config.TRANSIT_SPLIT_SEED)
    _, test_ix = next(halves.split(in_window_df, in_window_df[POOL_COL], in_window_df[DEST_HEX_COL]))
    in_window_df["half"] = "train"
    in_window_df.loc[test_ix, "half"] = "test"

    train_df = in_window_df[in_window_df.half == "train"]
    folds = StratifiedGroupKFold(n_splits=config.TRANSIT_CV_FOLDS, shuffle=True,
                                 random_state=config.TRANSIT_SPLIT_SEED)
    in_window_df["fold"] = pd.NA
    for fold, (_, fold_ix) in enumerate(folds.split(train_df, train_df[POOL_COL], train_df[DEST_HEX_COL]), start=1):
        in_window_df.loc[train_df.index[fold_ix], "fold"] = fold
    in_window_df["fold"] = in_window_df["fold"].astype("Int64")

    exploration_draw_nos = np.random.default_rng([config.TRANSIT_SPLIT_SEED, EXPLORATION_STREAM]).choice(
        train_df[DRAW_NO_COL].to_numpy(), size=config.TRANSIT_EXPLORATION_N, replace=False)
    in_window_df["is_exploration"] = in_window_df[DRAW_NO_COL].isin(exploration_draw_nos)

    smoke_df = pairs_df[pairs_df.is_smoke_test].assign(half="smoke_test", fold=pd.NA, is_exploration=False)
    split_df = pd.concat([in_window_df, smoke_df.drop(columns="is_smoke_test")], ignore_index=True)
    split_df["fold"] = split_df["fold"].astype("Int64")
    split_df = split_df.drop(columns="is_smoke_test", errors="ignore").sort_values(DRAW_NO_COL, ignore_index=True)

    train_hexes = set(split_df.loc[split_df.half == "train", DEST_HEX_COL])
    assert not train_hexes & set(split_df.loc[split_df.half == "test", DEST_HEX_COL]), "a hex is in both halves"
    print(pd.crosstab(split_df.half, split_df[POOL_COL], margins=True))
    print(pd.crosstab(split_df.fold, split_df[POOL_COL], margins=True))
    print(f"exploration: {split_df.is_exploration.sum()} training-half pairs")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    split_df.to_csv(out_path, index=False)
    print(f"saved {len(split_df):,} pairs to {out_path}")
    return split_df


def _replay_checkpoint(inputs, fastest_by_draw_no, n_kept, n_reserve, counts):
    """The draw's keep rules (_draw_until) replayed on the checkpoint alone, no routing: the first n_kept
    in-window pairs and the over-window pairs met before them (the draw), then the next n_reserve
    in-window pairs (the reserve), duplicates checked against both. Raises if the checkpoint runs out."""
    kept, over_window, reserve, seen = [], [], [], set()
    batches = _candidate_batches(*inputs)
    while len(reserve) < n_reserve:
        for row in next(batches).itertuples(index=False):
            try:
                reason = _screen_row(row, fastest_by_draw_no, seen)
            except KeyError:
                raise RuntimeError(f"draw_no {row.draw_no} not in the checkpoint: reserve ran out at "
                                   f"{len(reserve):,} pairs") from None
            if reason == OVER_WINDOW and len(kept) < n_kept:
                over_window.append(row._asdict())
            if reason == ZERO_TIME_ARTEFACT:
                counts[reason] += 1
            if reason != KEPT:
                continue
            seen.add((row.origin_hex, row.place_id))
            target = kept if len(kept) < n_kept else reserve
            target.append({**row._asdict(), FASTEST_MIN_COL: fastest_by_draw_no[row.draw_no]})
            if len(reserve) == n_reserve:
                break
    return kept, over_window, reserve


def _as_saved(pairs_df):
    """pairs_df as it reads back from CSV (the saved files' dtypes), for exact comparison."""
    return pd.read_csv(StringIO(pairs_df.to_csv(index=False)), dtype={RELEASE_COL: str})


def _check_draw_replay(kept, over_window, draw_path):
    """Stop check: rebuild the draw from a replay as draw_transit_pairs does; raise unless it equals the
    saved draw exactly, every column. Returns the saved draw."""
    kept_df = pd.DataFrame(kept).assign(is_smoke_test=False)
    over_window_df = pd.DataFrame(over_window)
    smoke_ix = np.random.default_rng([config.TRANSIT_PAIRS_SEED, SMOKE_TEST_STREAM]).choice(
        len(over_window_df), size=config.TRANSIT_SMOKE_TEST_N, replace=False)
    smoke_df = over_window_df.iloc[np.sort(smoke_ix)].assign(**{FASTEST_MIN_COL: np.nan, "is_smoke_test": True})
    draw_df = pd.concat([kept_df, smoke_df], ignore_index=True).sort_values(DRAW_NO_COL, ignore_index=True)
    draw_df[RELEASE_COL] = config.TRANSIT_DRAW_RELEASE
    draw_df = _draw_departures(draw_df)
    draw_df["haversine_kmh"] = draw_df.haversine_m / M_PER_KM / (draw_df[FASTEST_MIN_COL] / MIN_PER_HOUR)
    saved_df = pd.read_csv(draw_path, dtype={RELEASE_COL: str})
    pd.testing.assert_frame_equal(_as_saved(draw_df), saved_df, check_exact=True)
    print(f"stop check passed: replay reproduces all {len(saved_df):,} draw pairs, {saved_df.shape[1]} columns, exactly")
    return saved_df


def _past_draw_pairs(rows, window_release):
    """In-window pairs past the draw (reserve rows) as a frame: weekday and minute drawn as the draw's
    (per-draw_no streams); window_release is the release each was screened on (one value or one per row)."""
    pairs_df = pd.DataFrame(rows).assign(is_smoke_test=False, **{RELEASE_COL: window_release})
    pairs_df = _draw_departures(pairs_df)
    pairs_df["haversine_kmh"] = pairs_df.haversine_m / M_PER_KM / (pairs_df[FASTEST_MIN_COL] / MIN_PER_HOUR)
    return pairs_df


def draw_transit_set(set_name, subject_lat, subject_lon, should_rebuild=False):
    """A stream set's pairs (TRN-10, TRN-15, fresh holdout): its n_pairs in-window pairs past the sets
    before it, replayed from the draw's checkpoint and the sets' own (free, no routing), weekday and minute
    drawn as the draw's (per-draw_no streams). Stop checks first: the replay reproduces the saved draw and
    every earlier set exactly, every column. window_release is the release each pair was screened on. Writes
    the set's pairs_path; every other file is only read. Pairs shared with the boundary top-up (its own
    stream) are counted, not dropped."""
    out_path = subject_layers_file(STREAM_SETS[set_name].pairs_path, subject_lat, subject_lon)
    if is_already_built([out_path], should_rebuild):
        return pd.read_csv(out_path, dtype={RELEASE_COL: str})
    draw_path = Path(subject_layers_file(config.TRANSIT_PAIRS_PATH, subject_lat, subject_lon))
    set_names = _sets_through(set_name)
    evaluated_df = _evaluated_checkpoints(draw_path, set_names)
    conflicts = evaluated_df.groupby(DRAW_NO_COL)[[FASTEST_MIN_COL, RELEASE_COL]].nunique(dropna=False)
    assert (conflicts <= 1).all().all(), "the checkpoints give one draw_no two r5py times or two releases"
    fastest_by_draw_no = dict(zip(evaluated_df[DRAW_NO_COL], evaluated_df[FASTEST_MIN_COL]))
    release_by_draw_no = dict(zip(evaluated_df[DRAW_NO_COL], evaluated_df[RELEASE_COL]))
    counts = Counter()
    inputs = _draw_inputs(subject_lat, subject_lon, counts)
    kept, over_window, past_draw = _replay_checkpoint(
        inputs, fastest_by_draw_no, config.TRANSIT_N_PAIRS, sum(STREAM_SETS[name].n_pairs for name in set_names), counts)

    saved_dfs = [_check_draw_replay(kept, over_window, draw_path)]
    n_before = 0
    for earlier_name in set_names[:-1]:
        earlier_path = STREAM_SETS[earlier_name].pairs_path
        rows = past_draw[n_before:n_before + STREAM_SETS[earlier_name].n_pairs]
        n_before += STREAM_SETS[earlier_name].n_pairs
        saved_df = pd.read_csv(subject_layers_file(earlier_path, subject_lat, subject_lon), dtype={RELEASE_COL: str})
        replayed_df = _past_draw_pairs(rows, [release_by_draw_no[row[DRAW_NO_COL]] for row in rows])
        pd.testing.assert_frame_equal(_as_saved(replayed_df), saved_df, check_exact=True)
        print(f"stop check passed: replay reproduces all {len(saved_df):,} pairs of {Path(earlier_path).name} exactly")
        saved_dfs.append(saved_df)

    set_rows = past_draw[n_before:]
    set_df = _past_draw_pairs(set_rows, [release_by_draw_no[row[DRAW_NO_COL]] for row in set_rows])
    set_keys = set(zip(set_df.origin_hex, set_df[PLACE_ID_COL]))
    for earlier_df in saved_dfs:
        assert not set(set_df[DRAW_NO_COL]) & set(earlier_df[DRAW_NO_COL]), f"a {set_name} draw_no is already used"
        assert not set_keys & set(zip(earlier_df.origin_hex, earlier_df[PLACE_ID_COL])), f"a {set_name} pair is already used"
    topup_path = subject_layers_file(config.TRANSIT_TOPUP_PAIRS_PATH, subject_lat, subject_lon)
    if Path(topup_path).exists():
        topup_df = pd.read_csv(topup_path, usecols=["origin_hex", PLACE_ID_COL])
        print(f"pairs also in the top-up: {len(set_keys & set(zip(topup_df.origin_hex, topup_df[PLACE_ID_COL])))}")
    earlier_dest_hexes = set().union(*(set(df[DEST_HEX_COL]) for df in saved_dfs))
    print(f"{set_name}: {len(set_df):,} pairs, draw_no {set_df[DRAW_NO_COL].min():,}-{set_df[DRAW_NO_COL].max():,}; "
          f"screened on {set_df[RELEASE_COL].value_counts().sort_index().to_dict()}; r5py fastest minutes "
          f"{set_df[FASTEST_MIN_COL].describe().round(1).to_dict()}; destination hex in an earlier set "
          f"{set_df[DEST_HEX_COL].isin(earlier_dest_hexes).sum():,}; counts {dict(counts)}")
    set_df.to_csv(out_path, index=False)
    print(f"saved {len(set_df):,} pairs to {out_path}")
    return set_df


def draw_transit_topup(subject_lat, subject_lon, should_rebuild=False):
    """The boundary top-up's candidates (TRN-14): pairs drawn by the draw's pair rule (TRN-10) on their own
    stream (config.TRANSIT_TOPUP_SEED, draw_no from config.TRANSIT_TOPUP_FIRST_DRAW_NO), kept if their
    haversine falls in a zone's range (config.TRANSIT_TOPUP_RANGES_M), until each range holds
    config.TRANSIT_TOPUP_N_PER_RANGE. No r5py window: R5 is never consulted. Pairs of the draw or the
    reserve are left out; a pair in both ranges is one row, flagged for both. Weekday and minute as the
    draw's (per-draw_no streams). Writes config.TRANSIT_TOPUP_PAIRS_PATH; the fetch takes each range's
    rows in draw_no order (the stream's random order)."""
    out_path = subject_layers_file(config.TRANSIT_TOPUP_PAIRS_PATH, subject_lat, subject_lon)
    if is_already_built([out_path], should_rebuild):
        return pd.read_csv(out_path, dtype={"window_release": str})
    taken_df = pd.concat([pd.read_csv(subject_layers_file(path, subject_lat, subject_lon),
                                      usecols=["origin_hex", PLACE_ID_COL])
                          for path in (config.TRANSIT_PAIRS_PATH, config.TRANSIT_RESERVE_PAIRS_PATH)])
    seen = set(zip(taken_df.origin_hex, taken_df[PLACE_ID_COL]))
    counts = Counter()
    inputs = _draw_inputs(subject_lat, subject_lon, counts)
    batches = _candidate_batches(*inputs, seed=config.TRANSIT_TOPUP_SEED,
                                 first_draw_no=config.TRANSIT_TOPUP_FIRST_DRAW_NO)
    n_in_range = Counter()
    kept = []
    while min(n_in_range[zone] for zone in config.TRANSIT_TOPUP_RANGES_M) < config.TRANSIT_TOPUP_N_PER_RANGE:
        for row in next(batches).itertuples(index=False):
            counts["drawn"] += 1
            if row.origin_hex == row.dest_hex:
                counts["same_hex"] += 1
                continue
            in_ranges = {zone: low_m <= row.haversine_m <= high_m
                         for zone, (low_m, high_m) in config.TRANSIT_TOPUP_RANGES_M.items()}
            is_wanted = {zone: is_in and n_in_range[zone] < config.TRANSIT_TOPUP_N_PER_RANGE
                         for zone, is_in in in_ranges.items()}
            if not any(is_wanted.values()):
                counts["outside_ranges_or_full"] += 1
                continue
            if (row.origin_hex, row.place_id) in seen:
                counts["duplicate_pair"] += 1
                continue
            seen.add((row.origin_hex, row.place_id))
            n_in_range.update(zone for zone, is_in in is_wanted.items() if is_in)
            kept.append({**row._asdict(), **{RANGE_COL_FORMAT.format(zone): is_in for zone, is_in in is_wanted.items()}})

    topup_df = pd.DataFrame(kept).assign(is_smoke_test=False, window_release=config.TRANSIT_TOPUP_RELEASE)
    topup_df = _draw_departures(topup_df)
    for zone, (low_m, high_m) in config.TRANSIT_TOPUP_RANGES_M.items():
        range_df = topup_df[topup_df[RANGE_COL_FORMAT.format(zone)]]
        assert range_df.haversine_m.between(low_m, high_m).all(), f"range {zone} holds a pair outside it"
        print(f"range {zone} ({low_m:,}-{high_m:,} m): {len(range_df):,} pairs, haversine median "
              f"{range_df.haversine_m.median():,.0f} m, draw_no {range_df[DRAW_NO_COL].min():,}-"
              f"{range_df[DRAW_NO_COL].max():,}")
    range_cols = [RANGE_COL_FORMAT.format(zone) for zone in config.TRANSIT_TOPUP_RANGES_M]
    print(f"top-up: {len(topup_df):,} pairs ({topup_df[range_cols].all(axis=1).sum():,} in both ranges); "
          f"counts {dict(counts)}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    topup_df.to_csv(out_path, index=False)
    print(f"saved {len(topup_df):,} pairs to {out_path}")
    return topup_df
