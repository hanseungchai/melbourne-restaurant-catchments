"""Weekday open-share histogram from a Places Details (Enterprise fields) hours pull; no API.

build_opening_hours() reads the pull named by config.OPENING_HOURS_PULL_DATE (a key of
config.OPENING_HOURS_PULL_DIRS: the frozen 2026-09-02 pull or a fresh pull made by
places_details.py) and writes the histogram, a venue log, last closes and a meta file to
config.OPENING_HOURS_DIR, named by that date. Used for departure-time weights.
"""
import json
from datetime import date

import numpy as np
import pandas as pd

import config
from functions.places_hours import (FLAG_24H, FLAG_OK, MINUTES_PER_DAY, MINUTES_PER_HOUR, MINUTES_PER_WEEK,
                                    load_enterprise_records, venue_intervals, venue_slots)

OPERATIONAL_STATUS = "OPERATIONAL"    # Places businessStatus of an open venue
FIXED_RECORD_KEY = "is_fixed"         # set by places_details on venues fetched outside the draw

DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]  # Google periods: day 0 = Sunday
FIRST_WEEKDAY, LAST_WEEKDAY = 1, 5    # Google day index of Monday and Friday

# Hours flags (functions/places_hours.py) that count in the histogram.
INCLUDED_FLAGS = (FLAG_OK, FLAG_24H)

# Counting rules, written into the opening-hours meta file.
HISTOGRAM_RULES = {
    "open_rule": "point-in-time: open at slot t iff open <= t < close",
    "day_index": "Google periods, 0 = Sunday",
    "past_midnight": "spills into next day's slots; Sat->Sun wraps to week start",
    "24h": "single period, open Sun 00:00, no close -> open every slot; no close recorded",
    "hours_field": "regularOpeningHours only; secondary hours ignored",
    "denominator": "businessStatus == OPERATIONAL and flag in {ok, 24h}",
    "closes": "last close per venue-day, hours after that day's midnight",
    "dedup": "one record per place id, latest fetched_date",
    "fixed": "records with is_fixed true (subject venues of a fresh pull) left out",
}


def build_opening_hours(place_ids=None):
    """Weekday open-share histogram from the hours pull named by config.OPENING_HOURS_PULL_DATE.

    Input:   the Place Details JSONs in config.OPENING_HOURS_PULL_DIRS[config.OPENING_HOURS_PULL_DATE]
             (latest fetched_date per place id), fixed venues (is_fixed) left out; place_ids, if
             given, restricts them to a subset.
    Outputs: config.OPENING_HOURS_HIST_PATH (share of included venues open at each
             config.HOURS_SLOT_MIN slot of the week), config.OPENING_HOURS_VENUE_LOG_PATH (one row
             per venue: status, hours flag, included), config.OPENING_HOURS_CLOSES_PATH (last close
             per venue-day) and config.OPENING_HOURS_META_PATH (run metadata and HISTOGRAM_RULES).
    """
    pull_dir = config.OPENING_HOURS_PULL_DIRS[config.OPENING_HOURS_PULL_DATE]
    records, n_files = load_enterprise_records(pull_dir)
    fixed_ids = [place_id for place_id, record in records.items() if record.get(FIXED_RECORD_KEY)]
    records = {place_id: record for place_id, record in records.items() if place_id not in fixed_ids}
    print(f"pull {config.OPENING_HOURS_PULL_DATE}: {len(fixed_ids)} fixed venues left out")
    if place_ids is not None:
        missing_ids = set(place_ids) - set(records)
        records = {place_id: record for place_id, record in records.items() if place_id in set(place_ids)}
        print(f"subset: {len(records)} of {len(place_ids)} requested ids found ({len(missing_ids)} missing)")

    venue_log_df, open_slots, closes_df = _score_venue_hours(records, config.HOURS_SLOT_MIN)
    hist_df = _open_share_table(open_slots, config.HOURS_SLOT_MIN)

    config.OPENING_HOURS_DIR.mkdir(parents=True, exist_ok=True)
    hist_df.to_csv(config.OPENING_HOURS_HIST_PATH, index=False)
    venue_log_df.to_csv(config.OPENING_HOURS_VENUE_LOG_PATH, index=False)
    closes_df.to_csv(config.OPENING_HOURS_CLOSES_PATH, index=False)
    n_unique_ids = len(records) + len(fixed_ids)     # fixed venues are unique ids too, just left out
    meta = _opening_hours_meta(n_files, n_unique_ids, venue_log_df, len(open_slots))
    meta["n_fixed_excluded"] = len(fixed_ids)
    config.OPENING_HOURS_META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    _print_opening_hours_summary(n_files, n_unique_ids, meta, venue_log_df, hist_df, closes_df)
    print(f"saved {config.OPENING_HOURS_HIST_PATH.name}, {config.OPENING_HOURS_VENUE_LOG_PATH.name}, "
          f"{config.OPENING_HOURS_CLOSES_PATH.name}, {config.OPENING_HOURS_META_PATH.name}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_venue_hours(records, slot_min):
    """Per venue: log row, open slots (included venues only) and last closes (venues with a close)."""
    venue_log, open_slots, close_rows = [], [], []
    for place_id, record in records.items():
        status = record.get("businessStatus", "")
        intervals, flag = venue_intervals(record)
        is_included = status == OPERATIONAL_STATUS and flag in INCLUDED_FLAGS
        venue_log.append({"place_id": place_id, "name": record.get("displayName", {}).get("text", ""),
                          "fetched_date": record.get("fetched_date", ""), "status": status,
                          "flag": flag, "n_periods": len(intervals), "included": is_included})
        if not is_included:
            continue
        open_slots.append(venue_slots(intervals, slot_min))
        if flag == FLAG_OK:                                  # 24h venues have no close
            for day, close_h in _venue_day_closes(intervals).items():
                close_rows.append({"place_id": place_id, "day": day, "close_h": close_h})
    venue_log_df = pd.DataFrame(venue_log)
    closes_df = pd.DataFrame(close_rows, columns=["place_id", "day", "close_h"])
    return venue_log_df, open_slots, closes_df


def _open_share_table(open_slots, slot_min):
    """One row per slot of the week: venues open, venues counted, share open, weekday or not."""
    slot_starts_min = np.arange(0, MINUTES_PER_WEEK, slot_min)
    slot_days = slot_starts_min // MINUTES_PER_DAY
    open_matrix = (np.vstack(open_slots) if open_slots
                   else np.zeros((0, len(slot_starts_min)), dtype=bool))   # venues x slots
    n_venues = open_matrix.shape[0]
    hist_df = pd.DataFrame({
        "minute_of_week": slot_starts_min,
        "day": slot_days,
        "day_name": [DAY_NAMES[day] for day in slot_days],
        "slot": [_clock_label(minute) for minute in slot_starts_min],
        "n_open": open_matrix.sum(axis=0),
        "n_venues": n_venues,
    })
    hist_df["share"] = hist_df.n_open / n_venues if n_venues else np.nan
    hist_df["weekday"] = hist_df.day.between(FIRST_WEEKDAY, LAST_WEEKDAY)
    return hist_df


def _opening_hours_meta(n_files, n_unique_ids, venue_log_df, n_included):
    """Run metadata and the counting rules, for the meta file."""
    return {
        "created": str(date.today()),
        "src_dir": config.OPENING_HOURS_PULL_DIRS[config.OPENING_HOURS_PULL_DATE]
                   .relative_to(config.PROJECT_ROOT).as_posix(),
        "pull_date": config.OPENING_HOURS_PULL_DATE, "slot_min": config.HOURS_SLOT_MIN,
        "n_files": n_files, "n_unique_ids": n_unique_ids, "n_included": n_included,
        "fetched_date_range": ([venue_log_df.fetched_date.min(), venue_log_df.fetched_date.max()]
                               if len(venue_log_df) else None),
        "rules": HISTOGRAM_RULES,
    }


def _print_opening_hours_summary(n_files, n_unique_ids, meta, venue_log_df, hist_df, closes_df):
    print(f"files {n_files} | unique ids {n_unique_ids} | duplicates {n_files - n_unique_ids}")
    print(f"fetched_date {meta['fetched_date_range']}")
    print("\nstatus x flag:")
    print(pd.crosstab(venue_log_df.status, venue_log_df.flag).to_string())
    print(f"\nincluded (denominator): {meta['n_included']}")
    weekday_hist_df = hist_df[hist_df.weekday]
    print("\nweekday open-share at checkpoints:")
    for slot in config.HOURS_CHECKPOINT_SLOTS:
        print(f"  {slot}  {weekday_hist_df.loc[weekday_hist_df.slot == slot, 'share'].mean():.1%}")
    weekday_closes_df = closes_df[closes_df.day.between(FIRST_WEEKDAY, LAST_WEEKDAY)]
    print(f"\nweekday median last close: {weekday_closes_df.close_h.median():.2f} h  "
          f"(n venue-days {len(weekday_closes_df)})")


def _venue_day_closes(intervals):
    """Last close per open-day, hours after that day's midnight (1 am next day -> 25.0)."""
    last_close_h = {}
    for start_min, end_min in intervals:
        day = start_min // MINUTES_PER_DAY
        last_close_h[day] = max(last_close_h.get(day, 0.0),
                                (end_min - day * MINUTES_PER_DAY) / MINUTES_PER_HOUR)
    return last_close_h


def _clock_label(minute_of_week):
    """Minute of week -> 'HH:MM' within its day."""
    minute_of_day = minute_of_week % MINUTES_PER_DAY
    return f"{minute_of_day // MINUTES_PER_HOUR:02d}:{minute_of_day % MINUTES_PER_HOUR:02d}"
