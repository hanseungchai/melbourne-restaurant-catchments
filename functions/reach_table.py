"""Reach table (SCR-11, SCR-12; RCH-23): per band, 30-min slot and contestable hex of the subject, every venue hex's
chance of reaching the hex within the band, read from the saved passes.

A chance is P(Google's rounded minute <= the band's cut | the model's time) (functions/trip_uncertainty.py, RCH-23
(b)). Transit averages it over the slot's departure minutes, which brings in departure noise (RCH-23 (a)); drive has
no departure, so one chance per pair and no slot. Rows where the subject's or the venue's chance is below
config.REACH_TABLE_FLOOR_P are dropped; chances are stored as uint8 levels (round(P x REACH_TABLE_P_LEVELS)).
"""
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

import config
from functions import trip_uncertainty

TRANSIT_MODE, DRIVE_MODE = "transit", "drive"
TRANSIT_BANDS, DRIVE_BAND = (1, 2), 3
DRIVE_SLOT = "all"                    # drive rows hold for every slot
DRIVE_DEPARTURE_MIN = 0               # drive's error fit has one group: any departure minute reads the same
UNREACHED_S = np.iinfo(np.uint16).max # pass value for "not reached within the cap" (transit) / out of range (drive)
GRID_CUT_FACTOR = 3                   # chance computed up to this x the band cut; assumed 0 beyond (checked)
MINUTE_COL_PREFIX = "m"               # transit pass: one column per departure minute
CHUNK_NAME_SEP = "_"                  # transit chunk folder: <day type>_<HHMM>_<N>min
CHUNK_MIN_SUFFIX = "min"
MIN_PER_HOUR = 60

# Pass columns
ORIGIN_HEX_COL, DEST_HEX_COL = "origin_hex", "dest_hex"
SOURCE_HEX_COL, NODE_COL, COST_COL = "source_hex", "node", "cost_s"
# Table columns
BAND_COL, SLOT_COL, HEX_COL, VENUE_HEX_COL, LEVEL_COL = "band", "slot", "hex_id", "venue_hex", "reach_p_level"
SUBJECT_SCHEMA = pa.schema([(BAND_COL, pa.uint8()), (SLOT_COL, pa.string()), (HEX_COL, pa.int32()),
                            (LEVEL_COL, pa.uint8())])
COMPETITOR_SCHEMA = pa.schema([(BAND_COL, pa.uint8()), (SLOT_COL, pa.string()), (HEX_COL, pa.int32()),
                               (VENUE_HEX_COL, pa.int32()), (LEVEL_COL, pa.uint8())])
# Band-3 diners' transit fields (RCH-27): per field (a slot's own minutes, or a span's window) and stage band, each
# routed point's or exact hex's chance per venue hex; members map every band-3 hex to the point it reads.
FIELD_COL, POINT_COL = "field", "point_id"
BAND3_FIELD_SCHEMA = pa.schema([(FIELD_COL, pa.string()), (BAND_COL, pa.uint8()), (POINT_COL, pa.int32()),
                                (VENUE_HEX_COL, pa.int32()), (LEVEL_COL, pa.uint8())])
BAND3_MEMBER_SCHEMA = pa.schema([(FIELD_COL, pa.string()), (BAND_COL, pa.uint8()), (HEX_COL, pa.int32()),
                                 (POINT_COL, pa.int32())])


# --- chances ----------------------------------------------------------------------------------------
def error_fits(transit_fit_paths, drive_fit_path, drive_model_name):
    """trip_uncertainty fits: transit on the scored pairs (frozen model vs Google's default), drive on the selected
    model's test-half predictions."""
    transit_df = pd.concat([pd.read_csv(path) for path in transit_fit_paths], ignore_index=True)
    transit_df = transit_df[transit_df.is_scored.astype(bool) & np.isfinite(transit_df.model_s)]
    drive_df = pd.read_csv(drive_fit_path)
    drive_df = drive_df[drive_df.model == drive_model_name]
    return {TRANSIT_MODE: trip_uncertainty.fit_trip_error(TRANSIT_MODE, transit_df.model_s, transit_df.default_s,
                                                          transit_df.dep_min_of_day),
            DRIVE_MODE: trip_uncertainty.fit_trip_error(DRIVE_MODE, drive_df.predicted_s,
                                                        drive_df.google_drive_duration_sec, np.zeros(len(drive_df)))}


def chance_grid(fit, cut_min, departure_min_of_day):
    """Chance for every whole predicted second 0..UNREACHED_S (a lookup table indexed by the pass's uint16 seconds):
    computed up to GRID_CUT_FACTOR x the cut, 0 beyond and at UNREACHED_S."""
    seconds = np.arange(GRID_CUT_FACTOR * cut_min * trip_uncertainty.SECONDS_PER_MIN)
    grid = np.zeros(UNREACHED_S + 1)
    grid[seconds] = trip_uncertainty.band_probability(fit, seconds, departure_min_of_day, cut_min)
    assert grid[seconds[-1]] < config.REACH_TABLE_FLOOR_P, f"chance at {seconds[-1]} s still above the floor"
    return grid


def levels(chance):
    return np.rint(np.asarray(chance) * config.REACH_TABLE_P_LEVELS).astype(np.uint8)


# --- transit, bands 1-2 -----------------------------------------------------------------------------
def chunk_slots(chunk_name):
    """(slot label, first minute column, departure minute of day) for each 30-min slot of a pass chunk folder."""
    day_type, start, minutes = chunk_name.split(CHUNK_NAME_SEP)
    start_min = int(start[:2]) * MIN_PER_HOUR + int(start[2:])
    n_slots = int(minutes.removesuffix(CHUNK_MIN_SUFFIX)) // config.HOURS_SLOT_MIN
    slots = []
    for k in range(n_slots):
        slot_min = start_min + k * config.HOURS_SLOT_MIN
        label = f"{day_type}{CHUNK_NAME_SEP}{slot_min // MIN_PER_HOUR:02d}{slot_min % MIN_PER_HOUR:02d}"
        slots.append((label, k * config.HOURS_SLOT_MIN, slot_min))
    return slots


def slot_columns(first_minute):
    return [f"{MINUTE_COL_PREFIX}{m:02d}" for m in range(first_minute, first_minute + config.HOURS_SLOT_MIN)]


def transit_chunk_tables(chunk_dir, subject_hex, fit, file_pattern):
    """One pass chunk: the subject's table rows and the competitor rows (both bands, every slot of the chunk; a band's
    rows on its own contestable hexes and those of every outer band)."""
    slots = chunk_slots(chunk_dir.name)
    grids = {(label, band): chance_grid(fit, config.BAND_CUTS_MIN[band], departure_min)
             for label, _, departure_min in slots for band in TRANSIT_BANDS}
    files = sorted(chunk_dir.glob(file_pattern))
    subject_df = pd.concat([pq.read_table(path, filters=[(DEST_HEX_COL, "=", subject_hex)]).to_pandas()
                            for path in files], ignore_index=True)
    subject_parts, contest = [], {}
    for label, first_minute, _ in slots:
        times = subject_df[slot_columns(first_minute)].to_numpy()
        for band in TRANSIT_BANDS:
            chance = grids[label, band][times].mean(axis=1)
            is_kept = chance >= config.REACH_TABLE_FLOOR_P
            contest[label, band] = subject_df[ORIGIN_HEX_COL].to_numpy()[is_kept]
            subject_parts.append(pd.DataFrame({BAND_COL: band, SLOT_COL: label,
                                               HEX_COL: contest[label, band], LEVEL_COL: levels(chance[is_kept])}))
    any_contest = np.unique(np.concatenate(list(contest.values())))
    # a band's competitor rows cover the hexes of its own band and every outer one: under staged best-of-K (SCR-23)
    # a band-2 diner's first stage is band 1's field
    row_hexes = {(label, band): np.unique(np.concatenate([contest[label, outer] for outer in TRANSIT_BANDS
                                                          if outer >= band]))
                 for label, _, _ in slots for band in TRANSIT_BANDS}
    competitor_parts = []
    for path in files:
        times_df = pq.read_table(path, filters=[(ORIGIN_HEX_COL, "in", any_contest.tolist())]).to_pandas()
        for label, first_minute, _ in slots:
            times = times_df[slot_columns(first_minute)].to_numpy()
            for band in TRANSIT_BANDS:
                chance = grids[label, band][times].mean(axis=1)
                is_kept = ((chance >= config.REACH_TABLE_FLOOR_P)
                           & np.isin(times_df[ORIGIN_HEX_COL].to_numpy(), row_hexes[label, band]))
                competitor_parts.append(pd.DataFrame({
                    BAND_COL: band, SLOT_COL: label, HEX_COL: times_df[ORIGIN_HEX_COL].to_numpy()[is_kept],
                    VENUE_HEX_COL: times_df[DEST_HEX_COL].to_numpy()[is_kept], LEVEL_COL: levels(chance[is_kept])}))
    return pd.concat(subject_parts, ignore_index=True), pd.concat(competitor_parts, ignore_index=True)


def window_times(parts, first_minute, origin_ids, file_pattern):
    """One field's travel seconds read from pass folders: (origin ids, venue hexes, times: rows x HOURS_SLOT_MIN).
    parts: [(folder, first column of the window in it, minutes it holds)] in minute order, as the window's chunks;
    the field's minutes are first_minute .. + HOURS_SLOT_MIN of the window. origin_ids: rows kept (None = all). A pair
    missing from one part (not reached there) reads UNREACHED_S in its minutes."""
    frames, offset = [], 0
    for folder, first_col, held in parts:
        lo, hi = max(first_minute, offset), min(first_minute + config.HOURS_SLOT_MIN, offset + held)
        if lo < hi:
            columns = [f"{MINUTE_COL_PREFIX}{first_col + m - offset:02d}" for m in range(lo, hi)]
            filters = None if origin_ids is None else [(ORIGIN_HEX_COL, "in", list(map(int, origin_ids)))]
            frame = pd.concat([pq.read_table(path, columns=[ORIGIN_HEX_COL, DEST_HEX_COL, *columns],
                                             filters=filters).to_pandas()
                               for path in sorted(folder.glob(file_pattern))], ignore_index=True)
            frames.append(frame.rename(columns={col: m for col, m in zip(columns, range(lo, hi))}))
        offset += held
    times_df = frames[0]
    for frame in frames[1:]:
        times_df = times_df.merge(frame, on=[ORIGIN_HEX_COL, DEST_HEX_COL], how="outer")
    minutes = list(range(first_minute, first_minute + config.HOURS_SLOT_MIN))
    times = times_df[minutes].fillna(UNREACHED_S).to_numpy().astype(np.int64)
    return times_df[ORIGIN_HEX_COL].to_numpy(), times_df[DEST_HEX_COL].to_numpy(), times


def field_rows(field, origins, dests, times, grids, bands):
    """A field's rows (BAND3_FIELD_SCHEMA) per band: chance averaged over the field's minutes, kept at the floor."""
    parts = []
    for band in bands:
        chance = grids[band][times].mean(axis=1)
        is_kept = chance >= config.REACH_TABLE_FLOOR_P
        parts.append(pd.DataFrame({FIELD_COL: field, BAND_COL: band, POINT_COL: origins[is_kept],
                                   VENUE_HEX_COL: dests[is_kept], LEVEL_COL: levels(chance[is_kept])}))
    return pd.concat(parts, ignore_index=True)


# --- drive, band 3 ----------------------------------------------------------------------------------
def hex_drive_seconds(node_cost_s, alpha, row_1, row_2, n_nodes):
    """Predicted drive seconds per hex (ALPHA x the cheaper eligible node's routed cost, RCH-2), UNREACHED_S when
    neither node is stored. node_cost_s: routed seconds per CSR row, inf if not stored."""
    padded = np.append(node_cost_s, np.inf)                       # index n_nodes: "no second row"
    routed = np.minimum(padded[row_1], padded[np.where(row_2 < 0, n_nodes, row_2)])
    predicted = np.where(np.isfinite(routed), np.rint(alpha * routed), UNREACHED_S)
    return np.minimum(predicted, UNREACHED_S).astype(np.int64)


def drive_tables(cost_paths, subject_hex, hex_ids, alpha, row_1, row_2, n_nodes, grid, log):
    """The subject's drive rows and every venue hex's drive rows on the subject's contestable hexes (slot-free)."""
    dataset = ds.dataset(cost_paths, format="parquet")
    subject = dataset.to_table(columns=[NODE_COL, COST_COL], filter=ds.field(SOURCE_HEX_COL) == subject_hex)
    node_cost_s = np.full(n_nodes, np.inf)
    node_cost_s[subject[NODE_COL].to_numpy()] = subject[COST_COL].to_numpy()
    chance = grid[hex_drive_seconds(node_cost_s, alpha, row_1, row_2, n_nodes)]
    contest = np.flatnonzero(chance >= config.REACH_TABLE_FLOOR_P)          # positions in the hex table
    subject_df = pd.DataFrame({BAND_COL: DRIVE_BAND, SLOT_COL: DRIVE_SLOT, HEX_COL: hex_ids[contest],
                               LEVEL_COL: levels(chance[contest])})
    # node -> contestable hexes it serves (node 1, and node 2 where eligible)
    has_second = row_2[contest] >= 0
    node_hex_df = pd.DataFrame({NODE_COL: np.concatenate([row_1[contest], row_2[contest][has_second]]),
                                HEX_COL: np.concatenate([hex_ids[contest], hex_ids[contest][has_second]])})
    is_contest_node = np.zeros(n_nodes, dtype=bool)
    is_contest_node[node_hex_df[NODE_COL].to_numpy()] = True
    last_s = int(np.flatnonzero(grid >= config.REACH_TABLE_FLOOR_P).max())
    cut_routed_s = (last_s + 0.5) / alpha                                    # any cost past this rounds past last_s
    log(f"drive: {len(contest):,} contestable hexes, {int(is_contest_node.sum()):,} nodes; chance >= floor up to "
        f"{last_s} s predicted")
    parts = []
    for i, path in enumerate(cost_paths):
        hits = []                                                   # streamed: a file holds ~320 M rows
        for batch in pq.ParquetFile(path).iter_batches(columns=[SOURCE_HEX_COL, NODE_COL, COST_COL]):
            node, cost_s = batch[NODE_COL].to_numpy(), batch[COST_COL].to_numpy()
            is_hit = is_contest_node[node] & (cost_s <= cut_routed_s)
            hits.append(pd.DataFrame({VENUE_HEX_COL: batch[SOURCE_HEX_COL].to_numpy()[is_hit], NODE_COL: node[is_hit],
                                      COST_COL: cost_s[is_hit]}))
        rows_df = pd.concat(hits, ignore_index=True)
        del hits
        best_df = (rows_df.merge(node_hex_df, on=NODE_COL).groupby([HEX_COL, VENUE_HEX_COL], sort=False)[COST_COL]
                   .min().reset_index())
        venue_chance = grid[np.minimum(np.rint(alpha * best_df[COST_COL].to_numpy()), UNREACHED_S).astype(np.int64)]
        is_kept = venue_chance >= config.REACH_TABLE_FLOOR_P
        parts.append(pd.DataFrame({BAND_COL: DRIVE_BAND, SLOT_COL: DRIVE_SLOT,
                                   HEX_COL: best_df[HEX_COL].to_numpy()[is_kept],
                                   VENUE_HEX_COL: best_df[VENUE_HEX_COL].to_numpy()[is_kept],
                                   LEVEL_COL: levels(venue_chance[is_kept])}))
        log(f"  drive file {i + 1}/{len(cost_paths)}: {int(is_kept.sum()):,} rows")
    return subject_df, pd.concat(parts, ignore_index=True)


def to_arrow(df, schema):
    return pa.Table.from_pandas(df, schema=schema, preserve_index=False)
