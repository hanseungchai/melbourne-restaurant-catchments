"""Scoring (SCR-1..23). Steps: the reach table (functions/reach_table.py; SCR-11, SCR-12, RCH-23); venue open shares
per slot (functions/hours_imputation.py; SCR-13, VEN-13).

The table reads the subject's saved passes, found by their build stamps (RCH-18): a pass whose stamp no longer matches
the current code and inputs is not read. The table gets its own folder under config.SCORING_DIR, named by the hash of
its stamp (the passes it read, the fit inputs, the config values and the code); a finished folder is reused.
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import get_context
from types import SimpleNamespace

import numba
import numpy as np
import pandas as pd
import psutil
import pyarrow.parquet as pq
import pyogrio
from threadpoolctl import threadpool_limits

import config
import reachability
from functions import (hours_imputation, places_hours, reach_table, reachability_drive, share_draws, share_staged,
                       trip_uncertainty)
from functions.output_helper import project_relative
from functions.routing_bundle import get_bundle
from functions.subject_paths import subject_dir

SUBJECT_TABLE_FILE = "subject_reach.parquet"
TRANSIT_TABLE_FILE = "transit_competitor_reach.parquet"
DRIVE_TABLE_FILE = "drive_competitor_reach.parquet"
SUMMARY_FILE = "summary.json"
PARTIAL_SUFFIX = ".partial"
TABLE_KIND = "reach_table"
BAND3_TABLE_KIND = "band3"                    # band-3 transit fields: folder in the reach table's, + the pass's hash
BAND3_FIELDS_FILE = "fields.parquet"
BAND3_MEMBERS_FILE = "members.parquet"
BAND3_SLOT_FIELDS_FILE = "slot_fields.csv"
MIN_PER_HOUR = 60
SECONDS_PER_MIN = 60
TRANSIT_TIMES_PATTERN = "times_*.parquet"
DRIVE_COSTS_PATTERN = "costs_*.parquet"
HEX_COLUMNS = ["hex_id", "centroid_lat", "centroid_lon"]
TAG_SEPARATOR = "|"                           # venue table `types`
OPERATIONAL_STATUS = "OPERATIONAL"            # Places businessStatus of an open venue
OWN_HOURS_FLAGS = (places_hours.FLAG_OK, places_hours.FLAG_24H)
FIXED_RECORD_KEY = "is_fixed"                 # subject venues, fetched outside the draw
OWN_DEPTH = -1                                # depth for venues not imputed
SLOT_LABEL_SEP = "_"                          # slot labels as the reach table's: "<day type>_<HHMM>"
CONFIG_NAMES = ["BAND_CUTS_MIN", "REACH_TABLE_FLOOR_P", "REACH_TABLE_P_LEVELS", "HOURS_SLOT_MIN", "DRIVE_MODEL_NAME",
                "TRIP_ERROR_K_NEIGHBOURS", "TRIP_ERROR_MIN_MODEL_S", "TRIP_ERROR_NIGHT_END_MIN"]


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def pass_folders(subject_lat, subject_lon):
    """The subject's current drive and transit pass folders (stamps as drive_pass and transit_subject_pass write
    them); asserts both exist and are finished."""
    drive_stamp = reachability.drive_stamp(reachability.drive_inputs(subject_lat, subject_lon))
    drive_stamp["hex_limit"] = None                                        # a full pass, as drive_pass stamps it
    passes_dir = subject_dir(config.REACHABILITY_DIR, subject_lat, subject_lon)
    drive_dir = passes_dir / f"drive_{reachability.stamp_hash(drive_stamp)}"
    transit_dir = passes_dir / f"transit_{reachability.stamp_hash(reachability.transit_stamp(subject_lat, subject_lon))}"
    assert (drive_dir / reachability.DRIVE_SUMMARY_FILE).exists(), f"no finished drive pass at {drive_dir}"
    chunk_dirs = [transit_dir / reachability.CHUNK_DIR.format(day_type, start.strftime("%H%M"), minutes)
                  for day_type, _, start, minutes in reachability.subject_chunks()]
    unfinished = [d.name for d in chunk_dirs if not (d / reachability.CHUNK_DONE_FILE).exists()]
    assert not unfinished, f"transit pass {transit_dir.name} unfinished: {unfinished}"
    return drive_dir, transit_dir, chunk_dirs


def fit_inputs(subject_lat, subject_lon):
    drive_fit_path = (subject_dir(config.DRIVE_FIT_DIR, subject_lat, subject_lon) / config.TRIP_ERROR_DRIVE_FIT_RUN
                      / config.TRIP_ERROR_DRIVE_FIT_FILE)
    return config.TRIP_ERROR_TRANSIT_FIT_PATHS, drive_fit_path


def table_folder(subject_lat, subject_lon, drive_dir, transit_dir):
    """The table's folder (made if new, stamp written)."""
    transit_fit_paths, drive_fit_path = fit_inputs(subject_lat, subject_lon)
    code = [reach_table.__file__, trip_uncertainty.__file__, __file__]
    stamp = {"kind": TABLE_KIND, "subject": [subject_lat, subject_lon],
             "passes": {"drive": project_relative(drive_dir), "transit": project_relative(transit_dir)},
             "fit_inputs": {project_relative(path): reachability.file_record(path)
                            for path in [*transit_fit_paths, drive_fit_path]},
             "config": {name: getattr(config, name) for name in CONFIG_NAMES},
             "code_sha256": {project_relative(path): reachability.file_sha256(path) for path in code},
             reachability.STAMP_COMMIT_KEY: reachability.git_commit()}
    folder = (subject_dir(config.SCORING_DIR, subject_lat, subject_lon)
              / f"{TABLE_KIND}_{reachability.stamp_hash(stamp)}")
    folder.mkdir(parents=True, exist_ok=True)
    stamp_path = folder / config.REACH_STAMP_FILE
    if not stamp_path.exists():
        stamp_path.write_text(json.dumps(stamp, indent=1, default=str), encoding="utf-8", newline="\n")
    return folder


def write_table(df_parts, schema, path):
    """Concatenated parts to parquet, through a .partial file so a crash never leaves a table that looks finished."""
    partial = path.with_name(path.name + PARTIAL_SUFFIX)
    with pq.ParquetWriter(partial, schema) as writer:
        for part in df_parts:
            writer.write_table(reach_table.to_arrow(part, schema))
    partial.replace(path)


def build_reach_table(subject_lat, subject_lon):
    """The subject's reach table (see functions/reach_table.py); returns its folder."""
    started = time.perf_counter()
    drive_dir, transit_dir, chunk_dirs = pass_folders(subject_lat, subject_lon)
    folder = table_folder(subject_lat, subject_lon, drive_dir, transit_dir)
    if (folder / SUMMARY_FILE).exists():
        log(f"reach table: finished table in {project_relative(folder)}, reused")
        return folder
    log(f"reach table: {project_relative(folder)} from {drive_dir.name}, {transit_dir.name}")
    transit_fit_paths, drive_fit_path = fit_inputs(subject_lat, subject_lon)
    fits = reach_table.error_fits(transit_fit_paths, drive_fit_path, config.DRIVE_MODEL_NAME)

    drive_inputs = reachability.drive_inputs(subject_lat, subject_lon)
    hex_df = pyogrio.read_dataframe(drive_inputs["hex_nodes"], read_geometry=False,
                                    columns=[*HEX_COLUMNS, *reachability.HEX_NODE_COLUMNS[1:]])
    venue_hex_ids = (pd.read_csv(drive_inputs["venues_with_hex"], usecols=["hex_id"]).hex_id
                     .dropna().astype(np.int64).unique())
    subject_hex, _ = reachability.subject_venue_hex(hex_df, venue_hex_ids, subject_lat, subject_lon)
    subject_hex_id = int(subject_hex.hex_id)

    subject_parts, summary_rows = [], []

    def transit_parts():                       # one chunk at a time, written as it comes
        for chunk_dir in chunk_dirs:
            tick = time.perf_counter()
            subject_df, competitor_df = reach_table.transit_chunk_tables(chunk_dir, subject_hex_id,
                                                                         fits[reach_table.TRANSIT_MODE],
                                                                         TRANSIT_TIMES_PATTERN)
            subject_parts.append(subject_df)
            log(f"  transit {chunk_dir.name}: {len(subject_df):,} subject rows, {len(competitor_df):,} competitor "
                f"rows ({time.perf_counter() - tick:.0f} s)")
            yield competitor_df

    write_table(transit_parts(), reach_table.COMPETITOR_SCHEMA, folder / TRANSIT_TABLE_FILE)

    bundle_nodes = np.asarray(get_bundle(drive_inputs["bundle"]).nodes)
    alpha = json.loads(drive_inputs["params"].read_text(encoding="utf-8"))["alpha"]
    row_1, row_2 = reachability_drive.eligible_rows(hex_df, bundle_nodes)
    drive_grid = reach_table.chance_grid(fits[reach_table.DRIVE_MODE], config.BAND_CUTS_MIN[reach_table.DRIVE_BAND],
                                         reach_table.DRIVE_DEPARTURE_MIN)
    subject_drive_df, drive_df = reach_table.drive_tables(sorted(drive_dir.glob(DRIVE_COSTS_PATTERN)), subject_hex_id,
                                                          hex_df.hex_id.to_numpy(), alpha, row_1, row_2,
                                                          len(bundle_nodes), drive_grid, log)
    subject_parts.append(subject_drive_df)
    write_table([drive_df], reach_table.COMPETITOR_SCHEMA, folder / DRIVE_TABLE_FILE)
    write_table(subject_parts, reach_table.SUBJECT_SCHEMA, folder / SUBJECT_TABLE_FILE)

    subject_all_df = pd.concat(subject_parts, ignore_index=True)
    transit_counts = (pq.read_table(folder / TRANSIT_TABLE_FILE, columns=[reach_table.BAND_COL, reach_table.SLOT_COL])
                      .to_pandas().value_counts())
    for (band, slot), n_subject in subject_all_df.groupby([reach_table.BAND_COL, reach_table.SLOT_COL]).size().items():
        n_rows = len(drive_df) if band == reach_table.DRIVE_BAND else int(transit_counts.get((band, slot), 0))
        summary_rows.append({"band": int(band), "slot": slot, "subject_hexes": int(n_subject), "competitor_rows": n_rows})
    summary = {"subject_hex": subject_hex_id, "seconds": round(time.perf_counter() - started),
               "bytes": {path.name: path.stat().st_size for path in folder.glob("*.parquet")},
               "per_band_slot": summary_rows}
    (folder / SUMMARY_FILE).write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
    log(f"reach table done in {summary['seconds']} s: {summary['bytes']}")
    return folder


def band3_table_dir(table_dir, band3_dir):
    return table_dir / f"{BAND3_TABLE_KIND}_{band3_dir.name.rsplit('_', 1)[-1]}"


def build_band3_table(subject_lat, subject_lon):
    """Band-3 diners' bands 1-2 transit fields (RCH-27) from the band-3 pass (transit_band3.py), in a folder inside
    the reach table's named by the pass's hash: fields (per field, stage band and point, every venue hex's chance),
    members (per field and stage band, each populated band-3 hex's point: its own hex id when the subject pass covers
    it exactly), slot_fields.csv (slot -> field) and a summary. Returns the folder."""
    import transit_band3
    started = time.perf_counter()
    table_dir = build_reach_table(subject_lat, subject_lon)
    band3_dir = transit_band3.band3_folder(subject_lat, subject_lon)
    assert (band3_dir / transit_band3.SUMMARY_FILE).exists(), f"no finished band-3 pass at {band3_dir}"
    folder = band3_table_dir(table_dir, band3_dir)
    if (folder / SUMMARY_FILE).exists():
        log(f"band-3 table: finished in {project_relative(folder)}, reused")
        return folder
    folder.mkdir(exist_ok=True)
    _, transit_dir, _ = pass_folders(subject_lat, subject_lon)
    transit_fit_paths, drive_fit_path = fit_inputs(subject_lat, subject_lon)
    fit = reach_table.error_fits(transit_fit_paths, drive_fit_path, config.DRIVE_MODEL_NAME)[reach_table.TRANSIT_MODE]
    windows_df = pd.read_csv(band3_dir / transit_band3.WINDOWS_FILE)
    fields_df = pd.read_csv(band3_dir / transit_band3.FIELDS_FILE)
    fields_df[["slot", "field"]].to_csv(folder / BAND3_SLOT_FIELDS_FILE, index=False)
    log(f"band-3 table: {project_relative(folder)} from {band3_dir.name}; {fields_df.field.nunique()} fields")

    member_parts, counts = [], []

    def field_parts():
        for (field, window, first_minute), _ in fields_df.groupby(["field", "window", "first_minute"], sort=False):
            tick = time.perf_counter()
            row = windows_df.set_index("window").loc[window]
            window_dir = band3_dir / row.dir
            start = pd.Timestamp(row.start)
            departure_min = start.hour * MIN_PER_HOUR + start.minute + first_minute
            grids = {band: reach_table.chance_grid(fit, config.BAND_CUTS_MIN[band], departure_min)
                     for band in reach_table.TRANSIT_BANDS}
            for band, grid in grids.items():                # every chance above the floor lies inside the search
                last_s = int(np.flatnonzero(grid >= config.REACH_TABLE_FLOOR_P).max())
                assert last_s < config.REACH_BAND3_MAX_TIME_MIN[band] * SECONDS_PER_MIN, f"band {band} cap too short"
            covered = pd.read_csv(window_dir / transit_band3.COVERED_FILE).hex_id.to_numpy()
            exact_parts = []
            for part in row.subject_chunks.split(";"):
                name, cols = part.split("+")
                first_col, held = map(int, cols.split("x"))
                exact_parts.append((transit_dir / name, first_col, held))
            origins, dests, times = reach_table.window_times(exact_parts, first_minute, covered, TRANSIT_TIMES_PATTERN)
            frames = [reach_table.field_rows(field, origins, dests, times, grids, reach_table.TRANSIT_BANDS)]
            for band, route_dir in transit_band3.ROUTE_DIRS.items():
                origins, dests, times = reach_table.window_times([(window_dir / route_dir, 0, int(row.minutes))],
                                                                 first_minute, None, TRANSIT_TIMES_PATTERN)
                frames.append(reach_table.field_rows(field, origins, dests, times, grids,
                                                     [b for b in reach_table.TRANSIT_BANDS if b <= band]))
            members_df = pd.read_csv(window_dir / transit_band3.MEMBERS_FILE)
            member_parts.append(pd.concat(
                [members_df.assign(field=field)]
                + [pd.DataFrame({"field": field, reach_table.BAND_COL: band, reach_table.HEX_COL: covered,
                                 reach_table.POINT_COL: covered}) for band in reach_table.TRANSIT_BANDS],
                ignore_index=True))
            field_df = pd.concat(frames, ignore_index=True)
            counts.append({"field": field, "covered_hexes": len(covered), "rows": len(field_df),
                           "seconds": round(time.perf_counter() - tick)})
            log(f"  field {field}: {len(covered):,} exact hexes, {len(field_df):,} rows ({counts[-1]['seconds']} s)")
            yield field_df

    write_table(field_parts(), reach_table.BAND3_FIELD_SCHEMA, folder / BAND3_FIELDS_FILE)
    write_table([pd.concat(member_parts, ignore_index=True)[reach_table.BAND3_MEMBER_SCHEMA.names]],
                reach_table.BAND3_MEMBER_SCHEMA, folder / BAND3_MEMBERS_FILE)
    summary = {"band3_pass": project_relative(band3_dir), "fields": counts,
               "seconds": round(time.perf_counter() - started),
               "bytes": {path.name: path.stat().st_size for path in folder.glob("*.parquet")}}
    (folder / SUMMARY_FILE).write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
    log(f"band-3 table done in {summary['seconds']} s: {summary['bytes']}")
    return folder


# --- venue hours (SCR-13, VEN-13) -------------------------------------------------------------------
def venue_hours_inputs():
    """The venue table's place ids, each venue's informative tags (sorted), the own hours of operational venues with
    readable hours (place id -> weekly 30-min open flags, config.HOURS_SLOT_MIN), the training ids (own hours, not
    fixed) and the ShrinkImputer fitted on them. Inputs as build_venue_open_shares."""
    venues_df = (pd.read_csv(config.VENUE_TABLES[config.HEX_VENUES_DATE], usecols=["place_id", "types"])
                 .drop_duplicates("place_id"))
    tag_sets = [set(types.split(TAG_SEPARATOR)) - {""} for types in venues_df.types.fillna("")]
    universal_tags = set.intersection(*tag_sets)
    tags_of = dict(zip(venues_df.place_id, [sorted(tags - universal_tags) for tags in tag_sets]))

    records = {}
    for pull in config.HOURS_IMPUTATION_PULLS:
        pull_records, _ = places_hours.load_enterprise_records(config.OPENING_HOURS_PULL_DIRS[pull])
        for place_id, record in pull_records.items():
            if (place_id not in records
                    or record.get("fetched_date", "") > records[place_id].get("fetched_date", "")):
                records[place_id] = record

    own_weeks, train_ids = {}, []
    for place_id, record in records.items():
        if place_id not in tags_of:
            continue
        intervals, flag = places_hours.venue_intervals(record)
        if record.get("businessStatus", "") != OPERATIONAL_STATUS or flag not in OWN_HOURS_FLAGS:
            continue                                                       # closed or no readable hours: imputed
        own_weeks[place_id] = places_hours.venue_slots(intervals, config.HOURS_SLOT_MIN)
        if not record.get(FIXED_RECORD_KEY):
            train_ids.append(place_id)
    own = {place_id: hours_imputation.day_type_shares(week, config.HOURS_DAY_TYPES, config.HOURS_SLOT_MIN)
           for place_id, week in own_weeks.items()}
    imputer = hours_imputation.ShrinkImputer([tags_of[i] for i in train_ids], np.vstack([own[i] for i in train_ids]),
                                             config.HOURS_IMPUTATION_SHRINK_M, config.HOURS_IMPUTATION_MAX_TAGS)
    log(f"venue hours inputs: {len(tags_of):,} venues, {len(own):,} with own hours, {len(train_ids):,} training; "
        f"universal tags dropped: {sorted(universal_tags)}")
    return venues_df.place_id.tolist(), tags_of, own_weeks, train_ids, imputer


def build_venue_open_shares():
    """Every venue's open share per 30-min slot and day type: own pulled hours, else imputed from its tags.

    Input:   the venue table config.VENUE_TABLES[config.HEX_VENUES_DATE]; the hours pulls named by
             config.HOURS_IMPUTATION_PULLS (newest fetched_date per venue).
    Output:  config.VENUE_OPEN_SHARE_PATH, one row per venue, day type and slot: open_share, source (own: an operational
             venue with readable hours; imputed), depth (tag-chain length, 0 = the pooled mean; -1 for own),
             pooled_share (the pooled mean of pulled venues). Fixed (subject) venues get their own hours but stay out of
             training, as in the histogram. Venues a pull found closed are imputed like venues without hours: the venue
             table is a snapshot, later closures don't apply to it (VEN-14).
    """
    started = time.perf_counter()
    place_ids, tags_of, own, train_ids, imputer = venue_hours_inputs()
    own = {place_id: hours_imputation.day_type_shares(week, config.HOURS_DAY_TYPES, config.HOURS_SLOT_MIN)
           for place_id, week in own.items()}
    by_tags = {}
    n_columns = len(imputer.pooled)
    shares = np.empty((len(place_ids), n_columns), np.float32)
    depths = np.empty((len(place_ids), n_columns), np.int8)
    sources = []
    for row, place_id in enumerate(place_ids):
        if place_id in own:
            shares[row], depths[row] = own[place_id], OWN_DEPTH
            sources.append(hours_imputation.SOURCE_OWN)
        else:
            key = tuple(tags_of[place_id])
            if key not in by_tags:
                by_tags[key] = imputer.impute(list(key))
            shares[row], depths[row] = by_tags[key]
            sources.append(hours_imputation.SOURCE_IMPUTED)

    slots_per_day = places_hours.MINUTES_PER_DAY // config.HOURS_SLOT_MIN
    slot_labels = [f"{day_type}{SLOT_LABEL_SEP}{(k * config.HOURS_SLOT_MIN) // places_hours.MINUTES_PER_HOUR:02d}"
                   f"{(k * config.HOURS_SLOT_MIN) % places_hours.MINUTES_PER_HOUR:02d}"
                   for day_type in config.HOURS_DAY_TYPES for k in range(slots_per_day)]
    open_df = pd.DataFrame({
        "place_id": np.repeat(place_ids, n_columns),
        "slot": np.tile(slot_labels, len(place_ids)),
        "open_share": shares.ravel(),
        "depth": depths.ravel(),
        "source": np.repeat(sources, n_columns),
        "pooled_share": np.tile(imputer.pooled.astype(np.float32), len(place_ids)),
    })
    open_df["day_type"] = open_df.slot.str.split(SLOT_LABEL_SEP).str[0]
    config.VENUE_OPEN_SHARE_PATH.parent.mkdir(parents=True, exist_ok=True)
    open_df.to_parquet(config.VENUE_OPEN_SHARE_PATH, index=False)
    log(f"venue open shares: {len(place_ids):,} venues ({sources.count(hours_imputation.SOURCE_OWN)} own, "
        f"{sources.count(hours_imputation.SOURCE_IMPUTED):,} imputed from "
        f"{len(by_tags):,} tag lists; {len(train_ids)} training venues); {time.perf_counter() - started:.0f} s")
    return config.VENUE_OPEN_SHARE_PATH


def venue_week_draws():
    """(place ids, WeekDraws) for the venue table: own weekly hours where pulled, otherwise donors (SCR-13)."""
    place_ids, tags_of, own_weeks, train_ids, imputer = venue_hours_inputs()
    n_week_slots = places_hours.MINUTES_PER_WEEK // config.HOURS_SLOT_MIN
    is_imputed = np.array([place_id not in own_weeks for place_id in place_ids])
    weeks = np.zeros((len(place_ids), n_week_slots), bool)
    for row, place_id in enumerate(place_ids):
        if place_id in own_weeks:
            weeks[row] = own_weeks[place_id]
    sampler = hours_imputation.DonorSampler(imputer, [tags_of[i] for i, imputed in zip(place_ids, is_imputed)
                                                      if imputed])
    train_weeks = np.vstack([own_weeks[i] for i in train_ids])
    return place_ids, hours_imputation.WeekDraws(weeks, is_imputed, sampler, train_weeks)



# --- share step (SCR-19) ------------------------------------------------------------------------------
SHARES_KIND = "shares"
STAGED_RULE = "staged_best_of_k"                  # the variant stamp's rule name for staged best-of-K (SCR-23)
CPU_BACKEND, GPU_BACKEND = "cpu", "gpu"            # config.SCORING_BACKEND_BY_BAND values
STAGED_POLL_S = 2                                  # seconds between checks on the worker pools' finished units
HEX_SHARES_FILE = "hex_shares.parquet"
HEX_FOCAL_FILE = "hex_shares_focal.parquet"
HEADLINE_FILE = "headline.parquet"
CREDITS_FILE = "competitor_credits.parquet"
CONTENTION_FILE = "competitor_contention.parquet"
DRAWS_FILE = "draws.parquet"
UNITS_FILE = "units.csv"
SHARE_CONFIG_NAMES = ["HOURS_DAY_TYPES", "HOURS_IMPUTATION_PULLS", "HOURS_IMPUTATION_SHRINK_M",
                      "HOURS_IMPUTATION_MAX_TAGS", "HOURS_SLOT_MIN", "HEX_VENUES_DATE", "SCORING_HOURS_RULES",
                      "SCORING_RATING_STEP", "SCORING_RATING_RANGE", "SCORING_FOCAL_RATING_RANGE", "SCORING_SHRINK_M",
                      "SCORING_SHRINK_C", "SCORING_CREDIT_KEY_STEP", "SCORING_CREDIT_FINE_FROM",
                      "SCORING_CREDIT_COARSE_STEP", "SCORING_KEY_TIE_TOL",
                      "SCORING_Q_GRID", "SCORING_HEADLINE_Q", "SCORING_TOP_N", "SCORING_MC_REL_SE", "SCORING_MC_ABS_SE",
                      "SCORING_MIN_DRAWS", "SCORING_MAX_DRAWS", "SCORING_DRAW_BATCH", "SCORING_SEED", "REACH_TABLE_P_LEVELS",
                      "SCORING_TOP_RATING", "SCORING_TOP_READ", "SCORING_BOTTOM_RATING", "SCORING_BOTTOM_READ",
                      "SCORING_UNRATED_KEY", "SCORING_PERCENTILE_NEIGHBOURS",
                      "SCORING_PERCENTILE_COARSE_STEP", "SCORING_PERCENTILE_FINE_FROM", "SCORING_PERCENTILE_FINE_STEP",
                      "SCORING_NICHE_TAG", "SCORING_OVERLAP_OPEN_MIN"]
RULE_ALL_OPEN = "all_open"
HOURS_STREAM, REACH_STREAM, POOL_STREAM = 0, 1, 2  # seed streams: the same hours and pool draw d in every reach unit
DENIAL_TOLERANCE = 1e-3                            # relative: subject + credits vs persons of the hexes it entered
PERSONS_COLS = ["persons", "residents"]            # SCR-18: residents + workers, and residents only
VENUE_COLUMNS = ["place_id", "name", "rating", "user_ratings_total", "hex_id", "lat", "lng", "types"]
VENUE_KEYS_FILE = "venue_keys.parquet"
KEY_SHRUNK, KEY_FLAT, KEY_SHRUNK_TOP, KEY_PERCENTILE = config.SCORING_RATING_KEYS
POOL_ALL, POOL_NICHE, POOL_OVERLAP, POOL_OVERLAP_FLAT = config.SCORING_POOLS


def slot_of_day(slot_label):
    """(day type, slot-of-day index) of a slot label "<day type>_<HHMM>"."""
    day_type, hhmm = slot_label.split(SLOT_LABEL_SEP)
    minute = int(hhmm[:2]) * places_hours.MINUTES_PER_HOUR + int(hhmm[2:])
    return day_type, minute // config.HOURS_SLOT_MIN


class HoursDraws:
    """Open flags per draw (given venue rows x slots), the same draw d in every reach unit (common random numbers)."""

    def __init__(self, week_draws, venue_rows, slot_labels):
        self.week_draws, self.venue_rows, self.cache = week_draws, venue_rows, {}
        self.slots_per_day = places_hours.MINUTES_PER_DAY // config.HOURS_SLOT_MIN
        self.slot_parts = [slot_of_day(label) for label in slot_labels]

    def __call__(self, draw):
        if draw not in self.cache:
            rng = np.random.default_rng([config.SCORING_SEED, HOURS_STREAM, draw])
            weeks = self.week_draws.draw(rng)[self.venue_rows]
            days = hours_imputation.draw_days(draw, config.HOURS_DAY_TYPES)
            self.cache[draw] = weeks[:, [days[day_type] * self.slots_per_day + k for day_type, k in self.slot_parts]]
        return self.cache[draw]


def rating_keys(rating_key, venues_df, subject_row, focal_ratings):
    """(every venue's ordering key, the subject's slider keys at its own review count, credit cell edges) for one rating
    key of config.SCORING_RATING_KEYS (SCR-20; Q29 variants)."""
    ratings = venues_df.rating.to_numpy(float)
    counts = venues_df.user_ratings_total.fillna(0).to_numpy(float)
    focal_counts = np.full(len(focal_ratings), counts[subject_row])
    decimals = int(round(-np.log10(config.SCORING_RATING_STEP)))
    shrink_args = (config.SCORING_SHRINK_M, config.SCORING_SHRINK_C)
    edges = share_draws.credit_edges(config.SCORING_RATING_RANGE[0], config.SCORING_RATING_RANGE[1],
                                     config.SCORING_CREDIT_COARSE_STEP, config.SCORING_CREDIT_FINE_FROM,
                                     config.SCORING_CREDIT_KEY_STEP)
    if rating_key in (KEY_SHRUNK, KEY_SHRUNK_TOP):
        if rating_key == KEY_SHRUNK_TOP:
            end_args = (config.SCORING_TOP_RATING, config.SCORING_TOP_READ,
                        config.SCORING_BOTTOM_RATING, config.SCORING_BOTTOM_READ)
            ratings = share_draws.read_ends(ratings, *end_args)
            focal_ratings = share_draws.read_ends(focal_ratings, *end_args)
        return (share_draws.shrunk_key(ratings, counts, *shrink_args),
                share_draws.shrunk_key(focal_ratings, focal_counts, *shrink_args), edges)
    if rating_key == KEY_FLAT:
        return (share_draws.flat_key(ratings, counts, decimals, config.SCORING_UNRATED_KEY),
                np.round(focal_ratings, decimals), edges)
    assert rating_key == KEY_PERCENTILE, f"unknown rating key {rating_key}"
    ref_rows = np.flatnonzero(np.isfinite(ratings) & (counts > 0))
    self_index = np.full(len(ratings), -1)
    self_index[ref_rows] = np.arange(len(ref_rows))
    ref_args = (ratings[ref_rows], counts[ref_rows], config.SCORING_PERCENTILE_NEIGHBOURS)
    tail_args = (decimals, config.SCORING_UNRATED_KEY)
    edges = share_draws.credit_edges(0.0, 1.0, config.SCORING_PERCENTILE_COARSE_STEP,
                                     config.SCORING_PERCENTILE_FINE_FROM, config.SCORING_PERCENTILE_FINE_STEP)
    return (share_draws.percentile_key(ratings, counts, *ref_args, self_index, *tail_args),
            share_draws.percentile_key(focal_ratings, focal_counts, *ref_args,
                                       np.full(len(focal_ratings), self_index[subject_row]), *tail_args), edges)


def pool_weights(pool, competitors_df, subject_place_id):
    """Each competitor's chance of being in the pool, per draw (config.SCORING_POOLS)."""
    if pool == POOL_ALL:
        return np.ones(len(competitors_df))
    if pool == POOL_NICHE:
        return np.array([config.SCORING_NICHE_TAG in str(types).split(TAG_SEPARATOR)
                         for types in competitors_df.types.fillna("")], float)
    if pool == POOL_OVERLAP_FLAT:
        return np.full(len(competitors_df), pool_weights(POOL_OVERLAP, competitors_df, subject_place_id).mean())
    assert pool == POOL_OVERLAP, f"unknown pool {pool}"
    _, tags_of, _, _, imputer = venue_hours_inputs()
    slots_per_day = places_hours.MINUTES_PER_DAY // config.HOURS_SLOT_MIN
    day_weights = np.repeat([len(days) for days in config.HOURS_DAY_TYPES.values()], slots_per_day)
    is_subject_slot = imputer.impute(tags_of[subject_place_id])[0] >= config.SCORING_OVERLAP_OPEN_MIN
    by_tags = {}
    for tags in {tuple(tags_of[place_id]) for place_id in competitors_df.place_id}:
        profile = imputer.impute(list(tags))[0] * day_weights
        by_tags[tags] = profile[is_subject_slot].sum() / max(profile.sum(), 1e-12)
    log(f"overlap pool: subject's tags {tags_of[subject_place_id]}, predicted open "
        f"{(is_subject_slot * day_weights).sum() * config.HOURS_SLOT_MIN / places_hours.MINUTES_PER_HOUR:.1f} h a week")
    return np.array([by_tags[tuple(tags_of[place_id])] for place_id in competitors_df.place_id])


class PoolDraws:
    """In-pool flags per draw (competitors), the same draw d in every reach unit; fixed when every chance is 0 or 1."""

    def __init__(self, weights):
        self.weights, self.cache = weights, {}
        self.is_fixed = bool(np.isin(weights, [0.0, 1.0]).all())

    def __call__(self, draw):
        if self.is_fixed:
            return self.weights > 0
        if draw not in self.cache:
            rng = np.random.default_rng([config.SCORING_SEED, POOL_STREAM, draw])
            self.cache[draw] = rng.random(len(self.weights)) < self.weights
        return self.cache[draw]


def shares_folder(table_dir, venues_path, variant):
    code = [share_draws.__file__, hours_imputation.__file__, places_hours.__file__, __file__]
    if variant.get("rule") == STAGED_RULE:
        code.append(share_staged.__file__)
    stamp = {"kind": SHARES_KIND, "reach_table": project_relative(table_dir), "variant": variant,
             "venues": {project_relative(venues_path): reachability.file_record(venues_path)},
             "config": {name: getattr(config, name) for name in SHARE_CONFIG_NAMES},
             "code_sha256": {project_relative(path): reachability.file_sha256(path) for path in code},
             reachability.STAMP_COMMIT_KEY: reachability.git_commit()}
    folder = table_dir / f"{SHARES_KIND}_{reachability.stamp_hash(stamp)}"
    folder.mkdir(parents=True, exist_ok=True)
    stamp_path = folder / config.REACH_STAMP_FILE
    if not stamp_path.exists():
        stamp_path.write_text(json.dumps(stamp, indent=1, default=str), encoding="utf-8", newline="\n")
    return folder


def reach_units(table_dir, band_limit=None):
    """(band, reach slot, competitor rows) per reach unit: transit per band and slot, then the drive band (slot-free)."""
    transit_df = pq.read_table(table_dir / TRANSIT_TABLE_FILE, read_dictionary=[reach_table.SLOT_COL]).to_pandas()
    for (band, slot), unit_df in transit_df.groupby([reach_table.BAND_COL, reach_table.SLOT_COL], observed=True):
        if band_limit is None or int(band) in band_limit:
            yield int(band), str(slot), unit_df
    del transit_df
    if band_limit is None or reach_table.DRIVE_BAND in band_limit:
        yield reach_table.DRIVE_BAND, reach_table.DRIVE_SLOT, pq.read_table(
            table_dir / DRIVE_TABLE_FILE,
            columns=[reach_table.HEX_COL, reach_table.VENUE_HEX_COL, reach_table.LEVEL_COL]).to_pandas()


def share_setup(subject_lat, subject_lon, variant, band_limit=None, is_worker=False):
    """What every share rule's build reads (SimpleNamespace): the reach table, the variant's stamped folder (is_finished
    when its summary exists), the subject and its competitors, the rating key's cells (focal: the slider), hours draws
    and hex populations. variant: rating_key and pool, plus the rule's own stamp entries. A worker (is_worker) writes
    nothing: the calling process already wrote the venue keys."""
    table_dir = build_reach_table(subject_lat, subject_lon)
    drive_inputs = reachability.drive_inputs(subject_lat, subject_lon)
    rating_key, pool = variant["rating_key"], variant["pool"]
    folder = shares_folder(table_dir, drive_inputs["venues_with_hex"], variant)
    if (folder / SUMMARY_FILE).exists():
        log(f"shares: finished in {project_relative(folder)}, reused")
        return SimpleNamespace(is_finished=True, folder=folder)
    log(f"shares: {project_relative(folder)}, {variant}" + (f" (bands {band_limit} only)" if band_limit else ""))
    subject_hex_id = json.loads((table_dir / SUMMARY_FILE).read_text(encoding="utf-8"))["subject_hex"]

    from functions.geometry import haversine_m
    venues_df = pd.read_csv(drive_inputs["venues_with_hex"], usecols=VENUE_COLUMNS).drop_duplicates("place_id")
    subject_row = int(np.argmin(haversine_m(subject_lat, subject_lon, venues_df.lat.to_numpy(),
                                            venues_df.lng.to_numpy())))
    subject_venue = venues_df.iloc[subject_row]
    assert int(subject_venue.hex_id) == subject_hex_id, "subject venue is not in the reach table's subject hex"
    competitors_df = venues_df.drop(venues_df.index[subject_row]).reset_index(drop=True)
    focal_ratings = np.round(np.arange(config.SCORING_FOCAL_RATING_RANGE[0],
                                       config.SCORING_FOCAL_RATING_RANGE[1] + config.SCORING_RATING_STEP / 2,
                                       config.SCORING_RATING_STEP), 1)
    venue_keys, focal_keys, edges = rating_keys(rating_key, venues_df, subject_row, focal_ratings)
    cells = share_draws.KeyCells(edges, focal_keys, config.SCORING_KEY_TIE_TOL)
    competitor_keys = np.delete(venue_keys, subject_row)
    bins = cells.assign(competitor_keys)
    n_bins = cells.n_cells
    focal_bins = cells.assign(focal_keys)
    subject_bin = int(cells.assign(venue_keys[[subject_row]])[0])
    weights = pool_weights(pool, competitors_df, subject_venue.place_id)
    in_pool = PoolDraws(weights)
    if not is_worker:
        pd.DataFrame({"place_id": competitors_df.place_id, "key": competitor_keys, "cell": bins,
                      "pool_chance": weights}).to_parquet(folder / VENUE_KEYS_FILE, index=False)
    log(f"key {rating_key}: subject {venue_keys[subject_row]:.4f}, slider {np.round(focal_keys, 4).tolist()}; "
        f"pool {pool}: expected {weights.sum():,.1f} of {len(weights):,} competitors")
    assert len(np.unique(focal_bins)) == len(focal_bins), "two slider values share a cell"
    assert subject_bin in focal_bins, "the subject's rating is off the slider grid (SCORING_FOCAL_RATING_RANGE)"
    actual_focal = int(np.flatnonzero(focal_bins == subject_bin)[0])
    log(f"subject {subject_venue['name']} ({subject_venue.rating}, {int(subject_venue.user_ratings_total)} reviews), "
        f"hex {subject_hex_id}; {len(competitors_df):,} competitors; {n_bins} key cells")

    place_ids, week_draws = venue_week_draws()
    row_of = {place_id: row for row, place_id in enumerate(place_ids)}
    assert all(place_id in row_of for place_id in venues_df.place_id), "venues missing from the venue table"
    subject_reach_df = pd.read_parquet(table_dir / SUBJECT_TABLE_FILE)
    slot_labels = sorted(s for s in subject_reach_df[reach_table.SLOT_COL].unique() if s != reach_table.DRIVE_SLOT)
    slot_index = {label: i for i, label in enumerate(slot_labels)}
    venue_hours = HoursDraws(week_draws, competitors_df.place_id.map(row_of).to_numpy(), slot_labels)
    subject_hours = HoursDraws(week_draws, np.array([row_of[subject_venue.place_id]]), slot_labels)
    all_open = np.ones((len(competitors_df), len(slot_labels)), bool)

    def open_flags(rule, draw):
        return (all_open if rule == RULE_ALL_OPEN else venue_hours(draw)) & in_pool(draw)[:, None]

    hex_pop_df = pyogrio.read_dataframe(drive_inputs["hex_nodes"], read_geometry=False,
                                        columns=["hex_id", "residents", "workers"])
    hex_pop_df["persons"] = hex_pop_df.residents.fillna(0) + hex_pop_df.workers.fillna(0)
    hex_pop_df["residents"] = hex_pop_df.residents.fillna(0)
    pop_of = hex_pop_df.set_index("hex_id")[PERSONS_COLS]

    return SimpleNamespace(is_finished=False, folder=folder, table_dir=table_dir, subject_hex_id=subject_hex_id,
                           subject_venue=subject_venue, competitors_df=competitors_df, focal_ratings=focal_ratings,
                           bins=bins, n_bins=n_bins, focal_bins=focal_bins, subject_bin=subject_bin,
                           actual_focal=actual_focal, subject_reach_df=subject_reach_df, slot_labels=slot_labels,
                           slot_index=slot_index, subject_hours=subject_hours, open_flags=open_flags, pop_of=pop_of,
                           band3_table=variant.get("band3_table"))


def build_shares(subject_lat, subject_lon, band_limit=None, rating_key=None, pool=None):
    """The subject's expected share per band, slot and hex, its headlines and competitor credits (SCR-19); its folder.

    Input:   the subject's reach table (build_reach_table), the venue table with hexes, venue hours (SCR-13).
    Output:  a stamped folder inside the reach table's: hex_shares (headline hours rule, the subject's own rating: its
             chance of entering, expected share per q and Top-N), headline (persons and residents captured per band,
             slot, hours rule, focal rating and metric, with MC errors), hex_shares_focal (headline hours rule and q: the
             subject's expected share per hex at every slider rating), competitor_credits (SCR-14 denial at the
             headline q, persons, per venue and slot), competitor_contention (SCR-14 peers, headline rule and q), draws (per draw headline), units.csv and summary.json.
             band_limit (bands to run, a check run) writes to the folder too but leaves no summary.
             rating_key, pool: a variant (config.SCORING_RATING_KEYS, SCORING_POOLS; default the headline's), in its own
             folder; venue_keys holds each competitor's key, cell and pool chance.
    """
    started = time.perf_counter()
    rating_key = rating_key or config.SCORING_RATING_KEY
    pool = pool or config.SCORING_POOL
    setup = share_setup(subject_lat, subject_lon, {"rating_key": rating_key, "pool": pool}, band_limit)
    if setup.is_finished:
        return setup.folder
    (folder, table_dir, subject_hex_id, subject_venue, competitors_df, focal_ratings, bins, n_bins, focal_bins,
     subject_bin, actual_focal, subject_reach_df, slot_labels, slot_index, subject_hours, open_flags,
     pop_of) = (setup.folder, setup.table_dir, setup.subject_hex_id, setup.subject_venue, setup.competitors_df,
                setup.focal_ratings, setup.bins, setup.n_bins, setup.focal_bins, setup.subject_bin, setup.actual_focal,
                setup.subject_reach_df, setup.slot_labels, setup.slot_index, setup.subject_hours, setup.open_flags,
                setup.pop_of)

    q_values = config.SCORING_Q_GRID
    metric_names = [f"q{q:.2f}" for q in q_values] + [f"top{n}" for n in config.SCORING_TOP_N]
    headline_metric = q_values.index(config.SCORING_HEADLINE_Q)
    max_count = len(competitors_df) + 1
    q_pow = share_draws.q_powers(q_values, max_count)
    rules = config.SCORING_HOURS_RULES
    hex_parts, focal_parts, headline_rows, credit_parts, contention_parts = [], [], [], [], []
    draw_rows, unit_rows = [], []

    for unit_index, (band, reach_slot, rows_df) in enumerate(reach_units(table_dir, band_limit)):
        tick = time.perf_counter()
        unit_slots = slot_labels if reach_slot == reach_table.DRIVE_SLOT else [reach_slot]
        columns = [slot_index[label] for label in unit_slots]
        n_slots = len(unit_slots)
        subj_df = subject_reach_df[(subject_reach_df[reach_table.BAND_COL] == band)
                                   & (subject_reach_df[reach_table.SLOT_COL] == reach_slot)]
        hex_ids = subj_df[reach_table.HEX_COL].to_numpy()
        hex_pos = pd.Series(np.arange(len(hex_ids)), index=hex_ids)
        rows_df = rows_df[rows_df[reach_table.HEX_COL].isin(hex_ids)]
        venue_hexes = np.union1d(rows_df[reach_table.VENUE_HEX_COL].unique(), [subject_hex_id])
        vhex_pos = pd.Series(np.arange(len(venue_hexes)), index=venue_hexes)
        levels = np.zeros((len(hex_ids), len(venue_hexes)), np.uint8)
        levels[hex_pos[rows_df[reach_table.HEX_COL]].to_numpy(),
               vhex_pos[rows_df[reach_table.VENUE_HEX_COL]].to_numpy()] = rows_df[reach_table.LEVEL_COL].to_numpy()
        del rows_df
        subject_col = int(vhex_pos[subject_hex_id])
        subject_levels = subj_df[reach_table.LEVEL_COL].to_numpy()
        n_level_diff = int((levels[:, subject_col] != subject_levels).sum())
        levels[:, subject_col] = subject_levels                     # the subject's chance moves its whole venue hex
        unit_venues = np.flatnonzero(competitors_df.hex_id.isin(venue_hexes).to_numpy())
        venue_col = vhex_pos[competitors_df.hex_id.to_numpy()[unit_venues]].to_numpy()
        venue_bins = bins[unit_venues]
        pop = pop_of.reindex(hex_ids).fillna(0).to_numpy()          # hexes x (persons, residents)

        share_sums = np.zeros((len(hex_ids), n_slots, len(metric_names)))       # headline rule, own rating
        focal_sums = np.zeros((len(hex_ids), n_slots, len(focal_bins)))         # headline rule and q, every rating
        agg = {rule: [] for rule in rules}                          # per draw: slots x focal x metrics x persons cols
        credits = {rule: np.zeros((len(unit_venues), n_slots)) for rule in rules}
        contention = np.zeros((len(unit_venues), n_slots))          # headline rule only
        denial_worst, n_draws = 0.0, 0
        while True:
            for draw in range(n_draws, n_draws + config.SCORING_DRAW_BATCH):
                rng = np.random.default_rng([config.SCORING_SEED, REACH_STREAM, band, unit_index, draw])
                subject_open = subject_hours(draw)[0, columns]
                unit_open = {rule: open_flags(rule, draw)[unit_venues][:, columns] for rule in rules}
                venue_counts = {rule: share_draws.open_counts(unit_open[rule], venue_col, venue_bins,
                                                              len(venue_hexes), n_bins) for rule in rules}
                draw_agg = {rule: np.zeros((n_slots, len(focal_bins), len(metric_names), len(PERSONS_COLS)))
                            for rule in rules}
                draw_credit = {rule: np.zeros((len(venue_hexes), n_slots * n_bins)) for rule in rules}
                draw_entered = np.zeros((n_slots, len(PERSONS_COLS)))
                draw_contention = np.zeros((len(venue_hexes), n_slots * n_bins))
                for start in range(0, len(hex_ids), config.SCORING_HEX_CHUNK):
                    block = slice(start, start + config.SCORING_HEX_CHUNK)
                    uniform = rng.random(levels[block].shape, dtype=np.float32)
                    entry = (uniform * config.REACH_TABLE_P_LEVELS < levels[block]).astype(np.float32)
                    entered = (entry[:, subject_col] > 0)[:, None] & subject_open[None, :]     # hexes x slots
                    draw_entered += entered.T.astype(float) @ pop[block]
                    for rule in rules:
                        counts = (entry @ venue_counts[rule]).reshape(len(entry), n_slots, n_bins)
                        weights = np.zeros((len(entry), n_slots, n_bins), np.float32)
                        if rule == rules[0]:
                            peer_weights = np.zeros((len(entry), n_slots, n_bins), np.float32)
                        for s in range(n_slots):
                            shares = share_draws.subject_shares(counts[:, s], focal_bins, q_pow, config.SCORING_TOP_N)
                            shares *= entered[:, s, None, None]
                            draw_agg[rule][s] += np.einsum("hfm,hp->fmp", shares, pop[block])
                            if rule == rules[0]:
                                share_sums[block, s] += shares[:, actual_focal]
                                focal_sums[block, s] += shares[:, :, headline_metric]
                            bin_share = share_draws.bin_shares(counts[:, s], subject_bin, config.SCORING_HEADLINE_Q,
                                                               max_count)
                            weights[:, s] = bin_share * (pop[block, 0] * entered[:, s])[:, None]
                            if rule == rules[0]:
                                peer_share = share_draws.contention_shares(counts[:, s], subject_bin,
                                                                           config.SCORING_HEADLINE_Q, max_count)
                                peer_weights[:, s] = peer_share * (pop[block, 0] * entered[:, s])[:, None]
                        draw_credit[rule] += entry.T @ weights.reshape(len(entry), n_slots * n_bins)
                        if rule == rules[0]:
                            draw_contention += entry.T @ peer_weights.reshape(len(entry), n_slots * n_bins)
                contention += (draw_contention.reshape(len(venue_hexes), n_slots, n_bins)[venue_col, :, venue_bins]
                               * unit_open[rules[0]])
                for rule in rules:
                    held = draw_credit[rule].reshape(len(venue_hexes), n_slots, n_bins)[venue_col, :, venue_bins]
                    held = held * unit_open[rule]
                    credits[rule] += held
                    agg[rule].append(draw_agg[rule])
                    subject_persons = draw_agg[rule][:, actual_focal, headline_metric, 0]
                    gap = np.abs(held.sum(axis=0) + subject_persons - draw_entered[:, 0])
                    denial_worst = max(denial_worst, float((gap / np.maximum(draw_entered[:, 0], 1.0)).max()))
                    draw_rows.append({"band": band, "reach_slot": reach_slot, "rule": rule, "draw": draw,
                                      "persons": float(subject_persons.mean()),
                                      "entered_persons": float(draw_entered[:, 0].mean())})
            n_draws += config.SCORING_DRAW_BATCH
            per_draw = np.array([a[:, actual_focal, headline_metric, 0].mean() for a in agg[rules[0]]])
            abs_se = per_draw.std(ddof=1) / np.sqrt(n_draws)
            rel_se = abs_se / max(per_draw.mean(), 1e-12)
            if band == reach_table.DRIVE_BAND:
                log(f"    band {band}: {n_draws} draws, headline {per_draw.mean():.2f} persons, MC {abs_se:.2f} "
                    f"({rel_se:.2%}) ({time.perf_counter() - tick:.0f} s)")
            is_precise = rel_se < config.SCORING_MC_REL_SE or abs_se < config.SCORING_MC_ABS_SE
            if n_draws >= config.SCORING_MAX_DRAWS or (n_draws >= config.SCORING_MIN_DRAWS and is_precise):
                break
        assert denial_worst < DENIAL_TOLERANCE, f"denial sum off by {denial_worst:.2e} in band {band} {reach_slot}"

        for rule in rules:
            stack = np.stack(agg[rule])                              # draws x slots x focal x metrics x persons
            mean, se = stack.mean(axis=0), stack.std(axis=0, ddof=1) / np.sqrt(n_draws)
            for s, label in enumerate(unit_slots):
                for j, rating in enumerate(focal_ratings):
                    for m, metric in enumerate(metric_names):
                        headline_rows.append({"band": band, "slot": label, "rule": rule, "focal_rating": rating,
                                              "metric": metric, "persons": mean[s, j, m, 0],
                                              "persons_se": se[s, j, m, 0], "residents": mean[s, j, m, 1],
                                              "residents_se": se[s, j, m, 1], "n_draws": n_draws})
            credit_df = pd.DataFrame(credits[rule] / n_draws, columns=unit_slots)
            credit_df["place_id"] = competitors_df.place_id.to_numpy()[unit_venues]
            credit_df = credit_df.melt(id_vars="place_id", var_name="slot", value_name="credit_persons")
            credit_df = credit_df[credit_df.credit_persons > 0]
            credit_df.insert(0, "rule", rule)
            credit_df.insert(0, "band", band)
            credit_parts.append(credit_df)
        peer_df = pd.DataFrame(contention / n_draws, columns=unit_slots)
        peer_df["place_id"] = competitors_df.place_id.to_numpy()[unit_venues]
        peer_df["side"] = np.where(venue_bins > subject_bin, "above", "below")
        peer_df = peer_df.melt(id_vars=["place_id", "side"], var_name="slot", value_name="contention_persons")
        peer_df = peer_df[peer_df.contention_persons > 0]
        peer_df.insert(0, "rule", rules[0])
        peer_df.insert(0, "band", band)
        contention_parts.append(peer_df)
        mean_share = share_sums / n_draws
        for s, label in enumerate(unit_slots):
            part = pd.DataFrame(mean_share[:, s].astype(np.float32), columns=metric_names)
            part.insert(0, "chance", (subject_levels / config.REACH_TABLE_P_LEVELS).astype(np.float32))
            part.insert(0, "hex_id", hex_ids)
            part.insert(0, "slot", label)
            part.insert(0, "band", band)
            hex_parts.append(part)
            focal_part = pd.DataFrame(focal_sums[:, s].astype(np.float32) / n_draws, columns=focal_ratings)
            focal_part.insert(0, "hex_id", hex_ids)
            focal_part = focal_part.melt(id_vars="hex_id", var_name="focal_rating", value_name="share")
            focal_part.insert(0, "slot", label)
            focal_part.insert(0, "band", band)
            focal_parts.append(focal_part)
        unit_rows.append({"band": band, "reach_slot": reach_slot, "hexes": len(hex_ids),
                          "venue_hexes": len(venue_hexes), "venues": len(unit_venues), "draws": n_draws,
                          "rel_se": float(rel_se), "abs_se": float(abs_se), "denial_worst": denial_worst,
                          "subject_level_mismatch": n_level_diff, "seconds": round(time.perf_counter() - tick, 1)})
        log(f"  band {band} {reach_slot}: {len(hex_ids):,} hexes x {len(venue_hexes):,} venue hexes, {n_draws} draws, "
            f"MC {rel_se:.2%}, denial {denial_worst:.1e}, subject level mismatches {n_level_diff} "
            f"({time.perf_counter() - tick:.0f} s)")
        del levels

    pd.concat(hex_parts, ignore_index=True).to_parquet(folder / HEX_SHARES_FILE, index=False)
    pd.concat(focal_parts, ignore_index=True).to_parquet(folder / HEX_FOCAL_FILE, index=False)
    pd.DataFrame(headline_rows).to_parquet(folder / HEADLINE_FILE, index=False)
    credits_df = pd.concat(credit_parts, ignore_index=True).merge(
        competitors_df[["place_id", "name", "rating", "user_ratings_total", "hex_id"]], on="place_id")
    credits_df.to_parquet(folder / CREDITS_FILE, index=False)
    venue_info_df = competitors_df[["place_id", "name", "rating", "user_ratings_total", "hex_id"]]
    pd.concat(contention_parts, ignore_index=True).merge(venue_info_df, on="place_id").to_parquet(
        folder / CONTENTION_FILE, index=False)
    pd.DataFrame(draw_rows).to_parquet(folder / DRAWS_FILE, index=False)
    pd.DataFrame(unit_rows).to_csv(folder / UNITS_FILE, index=False)
    if band_limit is None:
        summary = {"subject": {"place_id": subject_venue.place_id, "name": subject_venue["name"],
                               "rating": float(subject_venue.rating), "hex": subject_hex_id},
                   "seconds": round(time.perf_counter() - started), "units": len(unit_rows)}
        (folder / SUMMARY_FILE).write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
    log(f"shares done in {round(time.perf_counter() - started)} s")
    return folder


def staged_units(table_dir, slot_labels, band_limit=None):
    """(band, slot, None) per staged reach unit: transit bands 1-2 per slot, then band 3 per slot. Each unit reads its
    own rows where it runs (transit_unit_rows; band 3: band3_levels), so no process holds the whole transit table
    (117th: its groups took ~3 GB in the parent)."""
    pairs_df = pq.read_table(table_dir / TRANSIT_TABLE_FILE, columns=[reach_table.BAND_COL, reach_table.SLOT_COL]
                             ).to_pandas().drop_duplicates()
    pairs = zip(pairs_df[reach_table.BAND_COL].astype(int), pairs_df[reach_table.SLOT_COL].astype(str))
    for band, slot in sorted(pairs):
        if band_limit is None or band in band_limit:
            yield band, slot, None
    if band_limit is None or reach_table.DRIVE_BAND in band_limit:
        for slot in slot_labels:
            yield reach_table.DRIVE_BAND, slot, None


def transit_unit_rows(table_dir, band, slot):
    """{inner band: its competitor rows} at the slot for every transit band up to band (a transit unit's stages)."""
    rows_df = pq.read_table(table_dir / TRANSIT_TABLE_FILE,
                            filters=[(reach_table.SLOT_COL, "=", slot), (reach_table.BAND_COL, "<=", band)],
                            columns=[reach_table.BAND_COL, reach_table.HEX_COL, reach_table.VENUE_HEX_COL,
                                     reach_table.LEVEL_COL]).to_pandas()
    return {int(inner): inner_df for inner, inner_df in rows_df.groupby(reach_table.BAND_COL)}


def peak_rss_gb():
    """This process's peak resident memory so far (Windows: peak working set), GB."""
    info = psutil.Process().memory_info()
    return getattr(info, "peak_wset", info.rss) / 1e9


def staged_metric(mean_looks):
    return f"k{mean_looks:.2f}"


def staged_plan(look_shape, backend=CPU_BACKEND):
    """What every staged unit shares beyond the setup: metric names per k, the headline's index, the weight tables of
    the k grid and of the headline k (functions/share_staged.weight_table, on the backend's device), the hours rules,
    the backend and its array module. is_numpy_draws (tests only): a GPU unit takes numpy's uniforms, copied over, so
    its draws equal the CPU's."""
    k_values = config.SCORING_K_GRID
    headline_metric = k_values.index(config.SCORING_HEADLINE_K)
    look_weights = [share_staged.look_weights(k, look_shape, config.SCORING_LOOK_TAIL_TOL) for k in k_values]
    if backend == GPU_BACKEND:
        import cupy as xp
    else:
        xp = np
    return SimpleNamespace(metric_names=[staged_metric(k) for k in k_values], headline_metric=headline_metric,
                           grid_weights=share_staged.weights_to(xp, share_staged.weight_table(look_weights)),
                           headline_weights=share_staged.weights_to(
                               xp, share_staged.weight_table([look_weights[headline_metric]])),
                           rules=config.SCORING_STAGED_HOURS_RULES, backend=backend, xp=xp, is_numpy_draws=False)


_staged_worker = None                # per worker process: (setup, plan, seconds its setup took)
_levels_ahead = {}                   # per GPU worker: band-3 slot -> Future of its levels, built during the last unit
_levels_builder = None               # its one-thread executor
_levels_ready = {}                   # per worker: (band, slot) -> levels built for staged_unit to take


def _staged_init(subject_lat, subject_lon, variant, band_limit, look_shape, n_threads, backend):
    """Per worker: thread budget (numba, BLAS), then its own setup (closures don't pickle under spawn)."""
    global _staged_worker
    tick = time.perf_counter()
    numba.set_num_threads(n_threads)
    threadpool_limits(n_threads)
    setup = share_setup(subject_lat, subject_lon, variant, band_limit, is_worker=True)
    _staged_worker = (setup, staged_plan(look_shape, backend), time.perf_counter() - tick)


def _staged_task(task):
    """One unit in a worker: its parts, plus the worker's pid and setup seconds. A band-3 task naming the next band-3
    slot starts that slot's levels on a CPU thread before running its own draws (the GPU worker's tasks run in order)."""
    global _levels_builder
    setup, plan, setup_s = _staged_worker
    unit_index, band, slot, band_rows, next_slot = task
    if band == reach_table.DRIVE_BAND:
        _levels_ready[band, slot] = (_levels_ahead.pop(slot).result() if slot in _levels_ahead
                                     else band3_levels(setup, slot))
        if next_slot is not None:
            _levels_builder = _levels_builder or ThreadPoolExecutor(1)
            _levels_ahead[next_slot] = _levels_builder.submit(band3_levels, setup, next_slot)
    result = staged_unit(setup, plan, unit_index, band, slot, band_rows)
    result.worker, result.worker_setup_s = os.getpid(), setup_s
    return result


def subject_stage_levels(setup, slot, inner, hex_ids):
    """The subject's chance level per hex (uint8) in stage band inner at the slot (band 3: slot-free rows)."""
    subject_reach_df = setup.subject_reach_df
    reach_slot = reach_table.DRIVE_SLOT if inner == reach_table.DRIVE_BAND else slot
    inner_df = subject_reach_df[(subject_reach_df[reach_table.SLOT_COL] == reach_slot)
                                & (subject_reach_df[reach_table.BAND_COL] == inner)
                                & subject_reach_df[reach_table.HEX_COL].isin(hex_ids)]
    subject_levels = np.zeros(len(hex_ids), np.uint8)
    subject_levels[np.searchsorted(hex_ids, inner_df[reach_table.HEX_COL].to_numpy())] = inner_df[reach_table.LEVEL_COL]
    return subject_levels


def transit_levels(setup, band, slot, band_rows):
    """A transit unit's (hex ids, venue hexes, levels: stages x hexes x venue hexes, subject level mismatches,
    unnested pairs); inner stages clipped to outer ones (rounding)."""
    subject_reach_df = setup.subject_reach_df
    stages = sorted(band_rows)
    n_stages = len(stages)
    subject_rows = subject_reach_df[subject_reach_df[reach_table.SLOT_COL] == slot]
    subj_df = subject_rows[subject_rows[reach_table.BAND_COL] == band]
    hex_ids = subj_df[reach_table.HEX_COL].to_numpy()
    hex_pos = pd.Series(np.arange(len(hex_ids)), index=hex_ids)
    band_rows = {inner: rows_df[rows_df[reach_table.HEX_COL].isin(hex_ids)] for inner, rows_df in band_rows.items()}
    venue_hexes = np.union1d(np.concatenate([rows_df[reach_table.VENUE_HEX_COL].unique()
                                             for rows_df in band_rows.values()]), [setup.subject_hex_id])
    vhex_pos = pd.Series(np.arange(len(venue_hexes)), index=venue_hexes)
    subject_col = int(vhex_pos[setup.subject_hex_id])
    levels = np.zeros((n_stages, len(hex_ids), len(venue_hexes)), np.uint8)
    n_level_diff = 0
    for s, inner in enumerate(stages):
        rows_df = band_rows[inner]
        levels[s, hex_pos[rows_df[reach_table.HEX_COL]].to_numpy(),
               vhex_pos[rows_df[reach_table.VENUE_HEX_COL]].to_numpy()] = rows_df[reach_table.LEVEL_COL].to_numpy()
        inner_df = subject_rows[(subject_rows[reach_table.BAND_COL] == inner)
                                & subject_rows[reach_table.HEX_COL].isin(hex_ids)]
        subject_levels = np.zeros(len(hex_ids), np.uint8)
        subject_levels[hex_pos[inner_df[reach_table.HEX_COL]].to_numpy()] = inner_df[reach_table.LEVEL_COL]
        n_level_diff += int((levels[s, :, subject_col] != subject_levels).sum())
        levels[s, :, subject_col] = subject_levels              # the subject's chance moves its whole venue hex
    n_unnested = int((levels[:-1] > levels[1:]).sum())
    levels = np.minimum.accumulate(levels[::-1], axis=0)[::-1]  # inner band's chance <= outer's (rounding)
    return hex_ids, venue_hexes, levels, n_level_diff, n_unnested


_band3_data = None                   # per process: band3_data's result, loaded on the first band-3 unit


def band3_data(setup):
    """Per process, once: band-3 hexes (sorted), venue hexes (every competitor's and the subject's, sorted), the drive
    stage's dense levels on them (the subject's column from its own drive rows), slot -> field, the members table and
    the fields table's path."""
    global _band3_data
    if _band3_data is not None:
        return _band3_data
    tick = time.perf_counter()
    subject_reach_df = setup.subject_reach_df
    hex_ids = np.sort(subject_reach_df.loc[subject_reach_df[reach_table.BAND_COL] == reach_table.DRIVE_BAND,
                                           reach_table.HEX_COL].to_numpy())
    venue_hexes = np.union1d(setup.competitors_df.hex_id.astype(np.int64).unique(), [setup.subject_hex_id])
    drive = np.zeros((len(hex_ids), len(venue_hexes)), np.uint8)
    n_outside = 0
    for batch in pq.ParquetFile(setup.table_dir / DRIVE_TABLE_FILE).iter_batches(
            columns=[reach_table.HEX_COL, reach_table.VENUE_HEX_COL, reach_table.LEVEL_COL]):
        hexes, vhexes = batch[reach_table.HEX_COL].to_numpy(), batch[reach_table.VENUE_HEX_COL].to_numpy()
        rows, cols = np.searchsorted(hex_ids, hexes), np.searchsorted(venue_hexes, vhexes)
        is_in = ((rows < len(hex_ids)) & (hex_ids[np.minimum(rows, len(hex_ids) - 1)] == hexes)
                 & (cols < len(venue_hexes)) & (venue_hexes[np.minimum(cols, len(venue_hexes) - 1)] == vhexes))
        n_outside += int((~is_in).sum())
        drive[rows[is_in], cols[is_in]] = batch[reach_table.LEVEL_COL].to_numpy()[is_in]
    subject_col = int(np.searchsorted(venue_hexes, setup.subject_hex_id))
    subject_levels = subject_stage_levels(setup, None, reach_table.DRIVE_BAND, hex_ids)
    n_drive_diff = int((drive[:, subject_col] != subject_levels).sum())
    drive[:, subject_col] = subject_levels
    band3_dir = setup.table_dir / setup.band3_table
    _band3_data = SimpleNamespace(
        hex_ids=hex_ids, venue_hexes=venue_hexes, drive=drive, drive_used=drive.any(axis=0),
        n_drive_diff=n_drive_diff, n_drive_outside=n_outside,
        field_of=pd.read_csv(band3_dir / BAND3_SLOT_FIELDS_FILE).set_index("slot").field,
        members_df=pd.read_parquet(band3_dir / BAND3_MEMBERS_FILE), fields_path=band3_dir / BAND3_FIELDS_FILE)
    log(f"band-3 data: {len(hex_ids):,} hexes x {len(venue_hexes):,} venue hexes ({int(drive.any(axis=0).sum()):,} "
        f"in drive fields); drive rows outside {n_outside}, subject drive level mismatches {n_drive_diff} "
        f"({time.perf_counter() - tick:.0f} s)")
    return _band3_data


def band3_levels(setup, slot):
    """A band-3 unit's (hex ids, venue hexes, levels: 3 stages x hexes x venue hexes, subject level mismatches,
    unnested pairs) for one slot: stages 1-2 from the band-3 table's field for the slot (each hex reads its point's
    row), stage 3 the drive rows. The fields nest by union (outer = max of inner and own; Claude's build choice,
    112th: a transit-field venue outside the drive field stays in the band-3 field)."""
    data = band3_data(setup)
    field = data.field_of[slot]
    fields_df = pq.read_table(data.fields_path, filters=[(reach_table.FIELD_COL, "=", field)],
                              columns=[reach_table.BAND_COL, reach_table.POINT_COL, reach_table.VENUE_HEX_COL,
                                       reach_table.LEVEL_COL]).to_pandas()
    members_df = data.members_df[data.members_df[reach_table.FIELD_COL] == field]
    used = data.drive_used.copy()
    used[np.searchsorted(data.venue_hexes, fields_df[reach_table.VENUE_HEX_COL].unique())] = True
    used[np.searchsorted(data.venue_hexes, setup.subject_hex_id)] = True
    venue_hexes = data.venue_hexes[used]
    subject_col = int(np.searchsorted(venue_hexes, setup.subject_hex_id))
    n_hexes = len(data.hex_ids)
    levels = np.zeros((len(reach_table.TRANSIT_BANDS) + 1, n_hexes, len(venue_hexes)), np.uint8)
    levels[-1] = data.drive[:, used]
    n_level_diff = 0
    for s, inner in enumerate(reach_table.TRANSIT_BANDS):
        rows_df = fields_df[fields_df[reach_table.BAND_COL] == inner]
        point_ids = np.unique(rows_df[reach_table.POINT_COL].to_numpy())
        points = np.zeros((len(point_ids) + 1, len(venue_hexes)), np.uint8)       # last row: a point with no rows
        points[np.searchsorted(point_ids, rows_df[reach_table.POINT_COL].to_numpy()),
               np.searchsorted(venue_hexes, rows_df[reach_table.VENUE_HEX_COL].to_numpy())] = (
            rows_df[reach_table.LEVEL_COL].to_numpy())
        band_members = members_df[members_df[reach_table.BAND_COL] == inner]
        member_points = band_members[reach_table.POINT_COL].to_numpy()
        point_rows = np.searchsorted(point_ids, member_points)
        has_rows = (point_rows < len(point_ids)) & (point_ids[np.minimum(point_rows, len(point_ids) - 1)]
                                                    == member_points)
        levels[s, np.searchsorted(data.hex_ids, band_members[reach_table.HEX_COL].to_numpy())] = (
            points[np.where(has_rows, point_rows, len(point_ids))])
        subject_levels = subject_stage_levels(setup, slot, inner, data.hex_ids)
        n_level_diff += int((levels[s, :, subject_col] != subject_levels).sum())
        levels[s, :, subject_col] = subject_levels
    n_unnested = int((levels[:-1] > levels[1:]).sum())
    levels = np.maximum.accumulate(levels, axis=0)
    return data.hex_ids, venue_hexes, levels, n_level_diff, n_unnested


def staged_unit(setup, plan, unit_index, band, slot, band_rows=None):
    """One staged reach unit (band, slot) of build_staged_shares: its output parts (SimpleNamespace of lists) and log
    line. plan: the k grid's metric names, headline index, weight tables and hours rules (staged_plan)."""
    competitors_df, bins, n_bins, focal_bins = setup.competitors_df, setup.bins, setup.n_bins, setup.focal_bins
    subject_bin, actual_focal = setup.subject_bin, setup.actual_focal
    metric_names, headline_metric, rules = plan.metric_names, plan.headline_metric, plan.rules
    grid_weights, headline_weights = plan.grid_weights, plan.headline_weights
    hex_parts, focal_parts, headline_rows, credit_parts, contention_parts = [], [], [], [], []
    draw_rows, unit_rows = [], []

    tick = time.perf_counter()
    xp, is_gpu = plan.xp, plan.backend == GPU_BACKEND
    to_host = xp.asnumpy if is_gpu else np.asarray
    columns = [setup.slot_index[slot]]
    if (band, slot) in _levels_ready:                          # built ahead (_staged_task)
        hex_ids, venue_hexes, levels, n_level_diff, n_unnested = _levels_ready.pop((band, slot))
    elif band == reach_table.DRIVE_BAND:
        hex_ids, venue_hexes, levels, n_level_diff, n_unnested = band3_levels(setup, slot)
    else:
        band_rows = band_rows or transit_unit_rows(setup.table_dir, band, slot)
        hex_ids, venue_hexes, levels, n_level_diff, n_unnested = transit_levels(setup, band, slot, band_rows)
    del band_rows
    n_stages, n_hexes, n_vhexes = levels.shape
    vhex_pos = pd.Series(np.arange(len(venue_hexes)), index=venue_hexes)
    subject_col = int(vhex_pos[setup.subject_hex_id])
    unit_venues = np.flatnonzero(competitors_df.hex_id.isin(venue_hexes).to_numpy())
    venue_col = vhex_pos[competitors_df.hex_id.to_numpy()[unit_venues]].to_numpy()
    venue_bins = bins[unit_venues]
    pop = xp.asarray(setup.pop_of.reindex(hex_ids).fillna(0).to_numpy())    # hexes x (persons, residents)
    subject_chance = levels[-1, :, subject_col] / config.REACH_TABLE_P_LEVELS
    levels = xp.asarray(levels)                                 # GPU: the host copy is freed here
    subject_levels = levels[-1, :, subject_col]
    ring_start = xp.float32(0) if is_gpu else 0                 # GPU rings stay float32 (exact 0 / 1)
    product_dtype = xp.float32 if is_gpu else np.float64        # GPU credit / contention products (~1e-7, 114th)
    day_type, _ = slot_of_day(slot)
    n_days = len(config.HOURS_DAY_TYPES[day_type])              # draw d takes day d mod n_days (draw_days)

    share_sums = xp.zeros((n_hexes, len(metric_names)))         # headline rule, own rating
    focal_sums = xp.zeros((n_hexes, len(focal_bins)))           # headline rule and k, every rating
    agg = {rule: [] for rule in rules}                          # per draw: focal x metrics x persons cols
    credits = {rule: np.zeros(len(unit_venues)) for rule in rules}
    contention = np.zeros(len(unit_venues))                     # headline rule only
    denial_worst, n_draws = 0.0, 0
    while True:
        for draw in range(n_draws, n_draws + config.SCORING_DRAW_BATCH):
            seed = [config.SCORING_SEED, REACH_STREAM, band, unit_index, draw]
            is_device_rng = is_gpu and not plan.is_numpy_draws
            rng = xp.random.default_rng(seed) if is_device_rng else np.random.default_rng(seed)
            subject_open = bool(setup.subject_hours(draw)[0, columns[0]])
            unit_open = {rule: setup.open_flags(rule, draw)[unit_venues][:, columns[0]] for rule in rules}
            venue_counts = {rule: xp.asarray(share_draws.open_counts(unit_open[rule][:, None], venue_col, venue_bins,
                                                                     len(venue_hexes), n_bins)) for rule in rules}
            draw_agg = {rule: xp.zeros((len(focal_bins), len(metric_names), len(PERSONS_COLS))) for rule in rules}
            draw_credit = {rule: xp.zeros((len(venue_hexes), n_bins), product_dtype) for rule in rules}
            draw_contention = xp.zeros((len(venue_hexes), n_bins), product_dtype)
            draw_entered = xp.zeros(len(PERSONS_COLS))
            for start in range(0, n_hexes, config.SCORING_HEX_CHUNK):
                if not subject_open:
                    break                                                  # every row adds 0 (per-draw stream)
                block = slice(start, start + config.SCORING_HEX_CHUNK)
                shape = (min(n_hexes, start + config.SCORING_HEX_CHUNK) - start, n_vhexes)
                uniform = xp.asarray(rng.random(shape, dtype=np.float32) * config.REACH_TABLE_P_LEVELS)
                kept = xp.flatnonzero(uniform[:, subject_col] < subject_levels[block])
                if not len(kept):
                    continue
                block, uniform = start + kept, uniform[kept]               # rows where the subject is entered
                field = (uniform[None] < levels[:, block]).astype(xp.float32)      # stages x hexes x venue hexes
                rings = xp.diff(field, axis=0, prepend=ring_start)                 # entered first in that band
                subject_field = field[:, :, subject_col]
                del uniform, field
                is_entered = (subject_field[-1] > 0) & subject_open
                subject_ring = (n_stages - subject_field.sum(axis=0)).astype(xp.int64).clip(0, n_stages - 1)
                persons = pop[block] * is_entered[:, None]
                draw_entered += persons.sum(axis=0)
                for rule in rules:
                    counts = xp.stack([rings[s] @ venue_counts[rule] for s in range(n_stages)], axis=1)
                    if is_gpu:
                        counts = counts.astype(xp.float64)                     # whole numbers, exact in float32
                    shares = share_staged.subject_shares(counts, subject_ring, focal_bins, grid_weights)
                    shares *= is_entered[None, :, None]                        # k values x hexes x focal
                    draw_agg[rule] += xp.einsum("khf,hp->fkp", shares, pop[block])
                    if rule == rules[0]:
                        share_sums[block] += shares[:, :, actual_focal].T
                        focal_sums[block] += shares[headline_metric]
                    with_subject = counts.copy()
                    with_subject[xp.arange(len(counts)), subject_ring, subject_bin] += 1
                    members = share_staged.member_shares(with_subject, headline_weights)[0]
                    members *= persons[:, 0, None, None]
                    if is_gpu:
                        members = members.astype(product_dtype)
                    for s in range(n_stages):
                        draw_credit[rule] += rings[s].T @ members[:, s]
                    if rule == rules[0]:
                        peers = share_staged.contention_shares(counts, subject_ring, subject_bin,
                                                               headline_weights)[0]
                        peers *= persons[:, 0, None, None]
                        if is_gpu:
                            peers = peers.astype(product_dtype)
                        for s in range(n_stages):
                            draw_contention += rings[s].T @ peers[:, s]
            draw_entered = to_host(draw_entered)
            contention += to_host(draw_contention).astype(np.float64)[venue_col, venue_bins] * unit_open[rules[0]]
            for rule in rules:
                held = to_host(draw_credit[rule]).astype(np.float64)[venue_col, venue_bins] * unit_open[rule]
                credits[rule] += held
                agg[rule].append(to_host(draw_agg[rule]))
                subject_persons = agg[rule][-1][actual_focal, headline_metric, 0]
                gap = abs(held.sum() + subject_persons - draw_entered[0])
                denial_worst = max(denial_worst, gap / max(draw_entered[0], 1.0))
                draw_rows.append({"band": band, "reach_slot": slot, "rule": rule, "draw": draw,
                                  "persons": float(subject_persons), "entered_persons": float(draw_entered[0])})
        n_draws += config.SCORING_DRAW_BATCH
        per_draw = np.array([a[actual_focal, headline_metric, 0] for a in agg[rules[0]]])
        if n_days > 1:                    # stratified by day (113th, user): within-day variance only
            assert n_draws % n_days == 0, "draw batches must hold whole day cycles"
            abs_se = np.sqrt(per_draw.reshape(-1, n_days).var(axis=0, ddof=1).mean() / n_draws)
        else:
            abs_se = per_draw.std(ddof=1) / np.sqrt(n_draws)
        rel_se = abs_se / max(per_draw.mean(), 1e-12)
        is_precise = rel_se < config.SCORING_MC_REL_SE or abs_se < config.SCORING_MC_ABS_SE
        if n_draws >= config.SCORING_MAX_DRAWS or (n_draws >= config.SCORING_MIN_DRAWS and is_precise):
            break
    share_sums, focal_sums = to_host(share_sums), to_host(focal_sums)
    assert denial_worst < DENIAL_TOLERANCE, f"denial sum off by {denial_worst:.2e} in band {band} {slot}"

    for rule in rules:
        stack = np.stack(agg[rule])                              # draws x focal x metrics x persons
        mean, se = stack.mean(axis=0), stack.std(axis=0, ddof=1) / np.sqrt(n_draws)
        for j, rating in enumerate(setup.focal_ratings):
            for m, metric in enumerate(metric_names):
                headline_rows.append({"band": band, "slot": slot, "rule": rule, "focal_rating": rating,
                                      "metric": metric, "persons": mean[j, m, 0], "persons_se": se[j, m, 0],
                                      "residents": mean[j, m, 1], "residents_se": se[j, m, 1], "n_draws": n_draws})
        credit_df = pd.DataFrame({"place_id": competitors_df.place_id.to_numpy()[unit_venues], "slot": slot,
                                  "credit_persons": credits[rule] / n_draws})
        credit_df = credit_df[credit_df.credit_persons > 0]
        credit_df.insert(0, "rule", rule)
        credit_df.insert(0, "band", band)
        credit_parts.append(credit_df)
    peer_df = pd.DataFrame({"place_id": competitors_df.place_id.to_numpy()[unit_venues],
                            "side": np.where(venue_bins > subject_bin, "above", "below"), "slot": slot,
                            "contention_persons": contention / n_draws})
    peer_df = peer_df[peer_df.contention_persons > 0]
    peer_df.insert(0, "rule", rules[0])
    peer_df.insert(0, "band", band)
    contention_parts.append(peer_df)
    part = pd.DataFrame((share_sums / n_draws).astype(np.float32), columns=metric_names)
    part.insert(0, "chance", subject_chance.astype(np.float32))
    part.insert(0, "hex_id", hex_ids)
    part.insert(0, "slot", slot)
    part.insert(0, "band", band)
    hex_parts.append(part)
    focal_part = pd.DataFrame((focal_sums / n_draws).astype(np.float32), columns=setup.focal_ratings)
    focal_part.insert(0, "hex_id", hex_ids)
    focal_part = focal_part.melt(id_vars="hex_id", var_name="focal_rating", value_name="share")
    focal_part.insert(0, "slot", slot)
    focal_part.insert(0, "band", band)
    focal_parts.append(focal_part)
    unit_rows.append({"band": band, "reach_slot": slot, "hexes": len(hex_ids), "venue_hexes": len(venue_hexes),
                      "venues": len(unit_venues), "draws": n_draws, "rel_se": float(rel_se),
                      "abs_se": float(abs_se), "denial_worst": denial_worst,
                      "subject_level_mismatch": n_level_diff, "unnested_pairs": n_unnested,
                      "backend": plan.backend, "peak_rss_gb": round(peak_rss_gb(), 2),
                      "seconds": round(time.perf_counter() - tick, 1)})
    message = (f"  band {band} {slot} ({plan.backend}): {len(hex_ids):,} hexes x {len(venue_hexes):,} venue hexes, {n_draws} draws, "
               f"MC {rel_se:.2%}, denial {denial_worst:.1e}, subject level mismatches {n_level_diff}, unnested "
               f"{n_unnested}, peak RSS {peak_rss_gb():.1f} GB ({time.perf_counter() - tick:.0f} s)")
    return SimpleNamespace(hex_parts=hex_parts, focal_parts=focal_parts, headline_rows=headline_rows,
                           credit_parts=credit_parts, contention_parts=contention_parts, draw_rows=draw_rows,
                           unit_rows=unit_rows, message=message)


def build_staged_shares(subject_lat, subject_lon, band_limit=None, rating_key=None, pool=None, look_shape=None,
                        n_workers=None, is_overlapped=None):
    """build_shares under staged best-of-K (SCR-23; functions/share_staged.py): the same outputs in their own folder,
    metrics per mean looks k (config.SCORING_K_GRID) in place of q and Top-N; credits and contention at
    config.SCORING_HEADLINE_K. Per draw a band-b unit's hexes see every venue hex enter each band's field on one
    uniform per pair (u < the pair's chance for that band), so the fields nest; a venue's ring is the first band it
    entered, the subject's too. Bands 1-3 (staged_units; band 3 from the band-3 table, build_band3_table).
    Rows where the subject is not entered in a draw (and draws where it is closed) are skipped: they add exactly 0
    (112th pilot: outputs equal to 1e-15, 1.5x faster on band 3, skip_rows_pilot_20261026.log).
    Each unit runs on its band's backend (config.SCORING_BACKEND_BY_BAND): CPU units in a pool of n_workers, GPU
    units in one CuPy process beside it (is_overlapped, default config.SCORING_GPU_OVERLAP) or after it (memory); a
    GPU-run variant gets its own folder.
    """
    started = time.perf_counter()
    look_shape = look_shape or config.SCORING_LOOK_SHAPE
    variant = {"rating_key": rating_key or config.SCORING_RATING_KEY, "pool": pool or config.SCORING_POOL,
               "rule": STAGED_RULE, "look_shape": look_shape, "k_grid": config.SCORING_K_GRID,
               "headline_k": config.SCORING_HEADLINE_K, "tail_tol": config.SCORING_LOOK_TAIL_TOL,
               "hours_rules": config.SCORING_STAGED_HOURS_RULES}
    bands = band_limit or [*reach_table.TRANSIT_BANDS, reach_table.DRIVE_BAND]
    backend_of = {band: config.SCORING_BACKEND_BY_BAND[band] for band in bands}
    if GPU_BACKEND in backend_of.values():
        variant["backend_by_band"] = backend_of            # GPU draws differ from the CPU's: never one folder
    if band_limit is None or reach_table.DRIVE_BAND in band_limit:
        variant["band3_table"] = build_band3_table(subject_lat, subject_lon).name
    setup = share_setup(subject_lat, subject_lon, variant, band_limit)
    if setup.is_finished:
        return setup.folder
    competitors_df = setup.competitors_df
    hex_parts, focal_parts, headline_rows, credit_parts, contention_parts = [], [], [], [], []
    draw_rows, unit_rows = [], []
    n_workers = n_workers or config.SCORING_STAGED_WORKERS
    is_overlapped = config.SCORING_GPU_OVERLAP if is_overlapped is None else is_overlapped
    slot_labels = list(setup.slot_labels)
    tasks = ((unit_index, band, slot, band_rows,
              slot_labels[slot_labels.index(slot) + 1] if band == reach_table.DRIVE_BAND and slot != slot_labels[-1]
              else None)
             for unit_index, (band, slot, band_rows) in enumerate(staged_units(setup.table_dir, slot_labels,
                                                                                band_limit)))
    results, worker_setup_s = {}, {}

    def take(unit_index, result):
        results[unit_index] = result
        if hasattr(result, "worker"):
            worker_setup_s[result.worker] = result.worker_setup_s
            result.unit_rows[0]["worker"] = result.worker
        log(result.message)

    if n_workers == 1:
        plans = {backend: staged_plan(look_shape, backend) for backend in set(backend_of.values())}
        for task in tasks:
            take(task[0], staged_unit(setup, plans[backend_of[task[1]]], *task[:4]))
    else:
        pools, pending = {}, []

        def wait(backends):
            while any(backend in backends for backend, _, _ in pending):
                done = [entry for entry in pending if entry[2].ready()]
                for entry in done:
                    pending.remove(entry)
                    take(entry[1], entry[2].get())
                if not done:
                    time.sleep(STAGED_POLL_S)

        for task in tasks:
            backend = backend_of[task[1]]
            if backend not in pools:
                if backend == GPU_BACKEND and not is_overlapped:
                    wait({CPU_BACKEND})                    # memory: the GPU process starts once the CPU pool is done
                n_procs = 1 if backend == GPU_BACKEND else n_workers
                n_threads = (config.SCORING_GPU_THREADS if backend == GPU_BACKEND
                             else max(1, (os.cpu_count() or 1) // n_workers))
                log(f"staged {backend} units on {n_procs} workers x {n_threads} threads")
                pools[backend] = get_context("spawn").Pool(
                    n_procs, initializer=_staged_init,
                    initargs=(subject_lat, subject_lon, variant, band_limit, look_shape, n_threads, backend))
            pending.append((backend, task[0], pools[backend].apply_async(_staged_task, (task,))))
        del task
        wait(set(pools))
        for pool_of in pools.values():
            pool_of.close()
            pool_of.join()
        log("worker setups: " + ", ".join(f"{seconds:.1f}" for seconds in worker_setup_s.values()) + " s")
    for unit_index in sorted(results):
        result = results.pop(unit_index)
        hex_parts += result.hex_parts
        focal_parts += result.focal_parts
        headline_rows += result.headline_rows
        credit_parts += result.credit_parts
        contention_parts += result.contention_parts
        draw_rows += result.draw_rows
        unit_rows += result.unit_rows

    folder = setup.folder
    pd.concat(hex_parts, ignore_index=True).to_parquet(folder / HEX_SHARES_FILE, index=False)
    pd.concat(focal_parts, ignore_index=True).to_parquet(folder / HEX_FOCAL_FILE, index=False)
    pd.DataFrame(headline_rows).to_parquet(folder / HEADLINE_FILE, index=False)
    venue_info_df = competitors_df[["place_id", "name", "rating", "user_ratings_total", "hex_id"]]
    pd.concat(credit_parts, ignore_index=True).merge(venue_info_df, on="place_id").to_parquet(folder / CREDITS_FILE,
                                                                                               index=False)
    pd.concat(contention_parts, ignore_index=True).merge(venue_info_df, on="place_id").to_parquet(
        folder / CONTENTION_FILE, index=False)
    pd.DataFrame(draw_rows).to_parquet(folder / DRAWS_FILE, index=False)
    pd.DataFrame(unit_rows).to_csv(folder / UNITS_FILE, index=False)
    if band_limit is None:
        subject_venue = setup.subject_venue
        summary = {"subject": {"place_id": subject_venue.place_id, "name": subject_venue["name"],
                               "rating": float(subject_venue.rating), "hex": setup.subject_hex_id},
                   "rule": variant, "bands": [*reach_table.TRANSIT_BANDS, reach_table.DRIVE_BAND],
                   "seconds": round(time.perf_counter() - started), "units": len(unit_rows)}
        (folder / SUMMARY_FILE).write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
    log(f"staged shares done in {round(time.perf_counter() - started)} s")
    return folder
