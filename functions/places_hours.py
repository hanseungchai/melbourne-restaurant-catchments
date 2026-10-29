"""Places Details (Enterprise) hours records: loading a pull and reading regularOpeningHours as minutes of the week.

Shared by the opening-hours histogram (opening_hours.py) and the venue hours imputation (scoring). Google periods
index days from 0 = Sunday; times are minutes from Sunday 00:00.
"""
import json

import numpy as np

MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR
DAYS_PER_WEEK = 7
MINUTES_PER_WEEK = DAYS_PER_WEEK * MINUTES_PER_DAY

ENTERPRISE_FILE_PATTERN = "*.json"    # Places Enterprise: one <place_id>.json per venue

# Hours flag per venue (venue_intervals).
FLAG_OK = "ok"
FLAG_24H = "24h"
FLAG_NO_HOURS = "no_hours"
FLAG_MALFORMED = "malformed"


def load_enterprise_records(src_dir):
    """One record per place id (latest fetched_date wins). Returns (records, n_files)."""
    file_paths = list(src_dir.glob(ENTERPRISE_FILE_PATTERN))
    records = {}
    for path in file_paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        place_id = record.get("id") or path.stem
        if (place_id not in records
                or record.get("fetched_date", "") > records[place_id].get("fetched_date", "")):
            records[place_id] = record
    return records, len(file_paths)


def venue_intervals(record):
    """regularOpeningHours -> ([(start, end)], flag). End exclusive, in minutes of week;
    end > MINUTES_PER_WEEK means the period wraps past Saturday midnight."""
    periods = record.get("regularOpeningHours", {}).get("periods", [])
    if not periods:
        return [], FLAG_NO_HOURS
    if len(periods) == 1 and "close" not in periods[0]:
        open_point = periods[0].get("open", {})
        if (open_point.get("day", 0), open_point.get("hour", 0), open_point.get("minute", 0)) == (0, 0, 0):
            return [(0, MINUTES_PER_WEEK)], FLAG_24H        # Google's always-open encoding
        return [], FLAG_MALFORMED
    intervals = []
    for period in periods:
        if "open" not in period or "close" not in period:
            return [], FLAG_MALFORMED
        start_min, end_min = minute_of_week(period["open"]), minute_of_week(period["close"])
        if end_min <= start_min:                             # Sat -> Sun wrap
            end_min += MINUTES_PER_WEEK
        intervals.append((start_min, end_min))
    return intervals, FLAG_OK


def venue_slots(intervals, slot_min):
    """Point-in-time rule: open at slot t iff start <= t < end."""
    slot_starts_min = np.arange(0, MINUTES_PER_WEEK, slot_min)
    is_open = np.zeros(len(slot_starts_min), dtype=bool)
    for start_min, end_min in intervals:
        is_open |= (slot_starts_min >= start_min) & (slot_starts_min < end_min)
        if end_min > MINUTES_PER_WEEK:                       # wrapped tail lands at start of week
            is_open |= slot_starts_min < (end_min - MINUTES_PER_WEEK)
    return is_open


def minute_of_week(period_point):
    """Minute of week for a Google open/close point {day, hour, minute}."""
    return (period_point["day"] * MINUTES_PER_DAY + period_point.get("hour", 0) * MINUTES_PER_HOUR
            + period_point.get("minute", 0))
