"""Do the 2026-09-02 opening hours still describe venues' hours a month later?

Claim under test: the weekday open-share histogram built from the 2026-09-02 Places Enterprise
pull (900 venues, 814 usable) is still representative, so departure hours can be drawn from it.
Test: a fresh, independent draw of 60 venues from the expanded venue table (seed 20260930;
50 fetched from the API on 2026-09-30, 10 looked up by hand on Google Maps). For each statistic,
a 95% bootstrap interval over the fresh venues (B = 10,000); the old value DISAGREES if it falls
outside. The verdict uses the pre-set rule slots (12:00, 19:00, 22:00) and the weekday median
last close; 15:30 (the afternoon trough) is descriptive only.
Where the pipeline relies on it: the hours histogram (built in opening_hours.py, outputs in
outputs/opening_hours/), used for departure-time weights (DESIGN_pre_spine "Opening hours").
Conclusion (run 2026-09-30, 55 of 60 fresh venues included: 45 API + 10 manual): AGREE. No old
value falls outside its interval: 12:00 old 0.731 vs fresh 0.760 (0.665-0.847), 19:00 0.663 vs
0.695 (0.589-0.796), 22:00 0.230 vs 0.218 (0.120-0.327), median close 21.0 vs 21.0 (20.5-22.0).
15:30 moved most (0.547 vs 0.640, 0.524-0.753), still inside. Detail and observations:
docs/stale_project_mds/session_docs_to_20261013/claude_PLATICA_hours_check_Sep_30.md.

Inputs, all saved data (no API calls here; the draw and the fetch were one-off runs of the
deprecated google_enterprise_fetch.draw_hours_check and fetch_hours_check, see docs/DEPRECATED.md):
- frozen_inputs/places_enterprise_hours_20260902/: the old pull.
- frozen_inputs/google_enterprise_fetch_fresh60/: the 50 API responses (2026-09-30).
- diagnostic_data/hours_check_fresh60_20260930_inputs/: the draw, its meta, and the 2026-09-30
  result and log, which every rerun is checked against.
- diagnostic_data/hours_check_fresh60_20260930_manual_inputs/: the 10 hand-copied Maps hours.

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). The opening-hours
rules below are copies of the pipeline's; a rerun that no longer matches the 2026-09-30 result
means they have drifted apart.
"""
import datetime
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths and run naming
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FROZEN_INPUTS_DIR = PROJECT_ROOT / "frozen_inputs"
OLD_HOURS_DIR = FROZEN_INPUTS_DIR / "places_enterprise_hours_20260902"
FRESH_HOURS_DIR = FROZEN_INPUTS_DIR / "google_enterprise_fetch_fresh60"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SAVED_INPUTS_DIR = DIAGNOSTIC_DATA_DIR / "hours_check_fresh60_20260930_inputs"
DRAW_PATH = SAVED_INPUTS_DIR / "fresh60_draw.csv"
REFERENCE_RESULT_PATH = SAVED_INPUTS_DIR / "hours_check_result.csv"
REFERENCE_LOG_PATH = SAVED_INPUTS_DIR / "hours_check_fresh_log.csv"
MANUAL_HOURS_PATH = (DIAGNOSTIC_DATA_DIR / "hours_check_fresh60_20260930_manual_inputs"
                     / "fresh60_manual_filled_in.csv")

DIAGNOSTIC_NAME = "hours_check_fresh60"
RUN_START = datetime.datetime.now()
RUN_PREFIX = f"{DIAGNOSTIC_NAME}_{RUN_START:%Y%m%d}"   # one run per day: a same-day rerun replaces that day's files (D1)
RESULT_FILE_SUFFIX = "_result.csv"
LOG_FILE_SUFFIX = "_fresh_log.csv"

# ---------------------------------------------------------------------------
# Check parameters (as run on 2026-09-30)
# ---------------------------------------------------------------------------
SLOT_MIN = 30                              # histogram slot length
RULE_SLOTS = ["12:00", "19:00", "22:00"]   # weekday slots in the pre-set verdict rule
DESCRIPTIVE_SLOTS = ["15:30"]              # reported, not part of the verdict
MEDIAN_CLOSE_STAT = "median_close"         # weekday median last close, hours after midnight
BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 20260930
INTERVAL_PERCENTILES = [2.5, 97.5]         # 95% bootstrap interval
REPRODUCTION_TOL = 1e-9                    # rerun vs 2026-09-30 result, absolute

API_METHOD = "api"                         # draw rows fetched from the API
MANUAL_METHOD = "manual"                   # draw rows looked up by hand on Google Maps
MISSING_STATUS = "MISSING"                 # API draw row with no saved response
NOT_FOUND_STATUS = "NOT_FOUND"             # manual draw row with no hours pasted

# ---------------------------------------------------------------------------
# Opening-hours rules (copies of the pipeline's)
# ---------------------------------------------------------------------------
MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR
DAYS_PER_WEEK = 7
MINUTES_PER_WEEK = DAYS_PER_WEEK * MINUTES_PER_DAY
FIRST_WEEKDAY, LAST_WEEKDAY = 1, 5         # Google day index: 0 = Sunday, so Mon-Fri
DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
ENTERPRISE_FILE_PATTERN = "*.json"
OPERATIONAL_STATUS = "OPERATIONAL"
FLAG_OK, FLAG_24H, FLAG_NO_HOURS, FLAG_MALFORMED = "ok", "24h", "no_hours", "malformed"
INCLUDED_FLAGS = (FLAG_OK, FLAG_24H)

# Manual Maps copy-paste, e.g. "Wednesday, 11 am–8 pm / Thursday, 11 am–3 pm, 5–9 pm / ..."
FULL_DAY_INDEX = {day_name: i for i, day_name in enumerate(
    ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"])}
DAY_ENTRY_SEPARATOR = " / "
DAY_NAME_SEPARATOR = ","                   # first comma splits the day name from its hours
BLOCK_SEPARATOR = ","                      # split service: blocks separated by commas
BLOCK_RANGE_PATTERN = re.compile(r"\s*[–-]\s*")   # en dash or hyphen between open and close
CLOCK_PATTERN = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", re.I)
CLOSED_TEXT = "closed"
OPEN_24_HOURS_TEXT = "open 24 hours"
MAPS_SPACE_CHARACTERS = [" ", "\xa0"]  # narrow and non-breaking spaces in Maps text
HOURS_PER_HALF_DAY = 12
AM_SUFFIX, PM_SUFFIX = "am", "pm"


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def main():
    print_saved_inputs()
    print("\n--- manual hours, parsed back to clock times (check against the pastes) ---")
    print_manual_hours(pd.read_csv(MANUAL_HOURS_PATH))
    result_df, fresh_log_df = compare_hours()
    save_outputs(result_df, fresh_log_df)
    check_reproduction(result_df, fresh_log_df)


def print_saved_inputs():
    """Name every saved input and its date; nothing is fetched."""
    print("Reusing saved data (no API calls):")
    for path in (OLD_HOURS_DIR, FRESH_HOURS_DIR, DRAW_PATH, MANUAL_HOURS_PATH,
                 REFERENCE_RESULT_PATH, REFERENCE_LOG_PATH):
        if path.is_dir():
            n_files = len(list(path.glob(ENTERPRISE_FILE_PATTERN)))
            fetched_dates = sorted({record.get("fetched_date", "")
                                    for record in load_enterprise(path).values()})
            print(f"  {path.relative_to(PROJECT_ROOT)}  ({n_files} files, fetched_date {fetched_dates})")
        else:
            modified = datetime.date.fromtimestamp(path.stat().st_mtime)
            print(f"  {path.relative_to(PROJECT_ROOT)}  (modified {modified})")


def compare_hours():
    """Old vs fresh weekday statistics, with bootstrap intervals over the fresh venues."""
    slot_starts_min = np.arange(0, MINUTES_PER_WEEK, SLOT_MIN)
    slot_days = slot_starts_min // MINUTES_PER_DAY
    is_weekday_slot = (slot_days >= FIRST_WEEKDAY) & (slot_days <= LAST_WEEKDAY)
    slot_names = RULE_SLOTS + DESCRIPTIVE_SLOTS
    slot_columns = {name: np.where(is_weekday_slot
                                   & (slot_starts_min % MINUTES_PER_DAY == _clock_text_to_min(name)))[0]
                    for name in slot_names}

    def venue_features(intervals, flag):
        """Weekday open share at each checkpoint slot, and this venue's weekday last closes."""
        is_open = venue_slots(intervals, SLOT_MIN)
        open_shares = [is_open[slot_columns[name]].mean() for name in slot_names]
        closes_h = ([] if flag == FLAG_24H else
                    [close_h for day, close_h in venue_day_closes(intervals).items()
                     if FIRST_WEEKDAY <= day <= LAST_WEEKDAY])
        return open_shares, np.array(closes_h)

    # ---- old: the 2026-09-02 pull ----
    old_records = load_enterprise(OLD_HOURS_DIR)
    old_features = [venue_features(*venue_intervals(record)) for record in old_records.values()
                    if record.get("businessStatus") == OPERATIONAL_STATUS
                    and venue_intervals(record)[1] in INCLUDED_FLAGS]

    # ---- fresh: the 60-venue draw ----
    draw_df = pd.read_csv(DRAW_PATH)
    fresh_records = load_enterprise(FRESH_HOURS_DIR)
    manual_df = pd.read_csv(MANUAL_HOURS_PATH).set_index("place_id")
    fresh_features, fresh_methods, fresh_log = [], [], []
    for row in draw_df.sort_values("draw_no").itertuples():
        if row.method == API_METHOD:
            record = fresh_records.get(row.place_id)
            status = record.get("businessStatus", "") if record else MISSING_STATUS
            intervals, flag = venue_intervals(record) if record else ([], FLAG_NO_HOURS)
        else:
            pasted_hours = (manual_df.hours_copy_paste.get(row.place_id)
                            if row.place_id in manual_df.index else None)
            intervals, flag = manual_intervals(pasted_hours)
            status = OPERATIONAL_STATUS if flag != FLAG_NO_HOURS else NOT_FOUND_STATUS
        is_included = status == OPERATIONAL_STATUS and flag in INCLUDED_FLAGS
        fresh_log.append({"draw_no": row.draw_no, "place_id": row.place_id, "method": row.method,
                          "status": status, "flag": flag, "included": is_included})
        if is_included:
            fresh_features.append(venue_features(intervals, flag))
            fresh_methods.append(row.method)
    fresh_log_df = pd.DataFrame(fresh_log)

    # ---- point values ----
    def point_values(features):
        open_shares = np.array([venue[0] for venue in features])
        closes_h = [venue[1] for venue in features]
        return open_shares, closes_h, np.r_[open_shares.mean(0), np.median(np.concatenate(closes_h))]

    _, _, old_values = point_values(old_features)
    fresh_open_shares, fresh_closes_h, fresh_values = point_values(fresh_features)

    # ---- bootstrap over fresh venues ----
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n_fresh = len(fresh_features)
    boot_values = np.empty((BOOTSTRAP_DRAWS, len(slot_names) + 1))
    for b in range(BOOTSTRAP_DRAWS):
        resample = rng.integers(0, n_fresh, n_fresh)
        boot_values[b, :-1] = fresh_open_shares[resample].mean(0)
        boot_values[b, -1] = np.median(np.concatenate([fresh_closes_h[i] for i in resample]))
    lower, upper = np.percentile(boot_values, INTERVAL_PERCENTILES, axis=0)

    stat_names = slot_names + [MEDIAN_CLOSE_STAT]
    result_df = pd.DataFrame({
        "stat": stat_names, "old": old_values, "fresh": fresh_values, "lo95": lower, "hi95": upper,
        "in_rule": [name in RULE_SLOTS or name == MEDIAN_CLOSE_STAT for name in stat_names]})
    result_df["old_outside"] = (result_df.old < result_df.lo95) | (result_df.old > result_df.hi95)

    # ---- report ----
    print(f"\nold n {len(old_features)} | fresh drawn {len(draw_df)} | fresh included {n_fresh} "
          f"(api {fresh_methods.count(API_METHOD)}, manual {fresh_methods.count(MANUAL_METHOD)})")
    print("\nfresh status x flag:")
    print(pd.crosstab(fresh_log_df.status, fresh_log_df.flag).to_string())
    print("\n" + result_df.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    is_disagree = result_df.loc[result_df.in_rule, "old_outside"].any()
    print(f"\nVERDICT: {'DISAGREE -> draw from fresh 60 + larger floor' if is_disagree else 'AGREE -> draw from old 814 + floor'}")
    by_method_df = (pd.DataFrame(fresh_open_shares, columns=slot_names)
                    .assign(method=fresh_methods).groupby("method").mean())
    print("\nby method (descriptive only, manual n is tiny):")
    print(by_method_df.to_string(float_format=lambda x: f"{x:.2f}"))
    return result_df, fresh_log_df


def save_outputs(result_df, fresh_log_df):
    """Write this run's files under the day's prefix; a same-day rerun replaces them (D1)."""
    result_path = DIAGNOSTIC_DATA_DIR / f"{RUN_PREFIX}{RESULT_FILE_SUFFIX}"
    log_path = DIAGNOSTIC_DATA_DIR / f"{RUN_PREFIX}{LOG_FILE_SUFFIX}"
    result_df.to_csv(result_path, index=False)
    fresh_log_df.to_csv(log_path, index=False)
    print(f"\nsaved {result_path.name}, {log_path.name}")


def check_reproduction(result_df, fresh_log_df):
    """Compare this run with the saved 2026-09-30 result and log."""
    reference_result_df = pd.read_csv(REFERENCE_RESULT_PATH)
    reference_log_df = pd.read_csv(REFERENCE_LOG_PATH)
    print(f"\n--- reproduction of the 2026-09-30 run (tol {REPRODUCTION_TOL}) ---")
    float_columns = ["old", "fresh", "lo95", "hi95"]
    other_columns = [c for c in reference_result_df.columns if c not in float_columns]
    max_diff = (result_df[float_columns] - reference_result_df[float_columns]).abs().to_numpy().max()
    is_result_same = (list(result_df.columns) == list(reference_result_df.columns)
                      and len(result_df) == len(reference_result_df)
                      and result_df[other_columns].astype(str).equals(reference_result_df[other_columns].astype(str))
                      and max_diff <= REPRODUCTION_TOL)
    is_log_same = fresh_log_df.astype(str).equals(reference_log_df.astype(str))
    print(f"result: {'same' if is_result_same else 'DIFFERS'} (max float diff {max_diff:.3g})")
    print(f"log:    {'same' if is_log_same else 'DIFFERS'} ({len(fresh_log_df)} vs {len(reference_log_df)} rows)")


# ---------------------------------------------------------------------------
# Opening-hours rules (copies of the pipeline's)
# ---------------------------------------------------------------------------
def load_enterprise(src_dir):
    """One record per place id (latest fetched_date wins)."""
    records = {}
    for path in src_dir.glob(ENTERPRISE_FILE_PATTERN):
        record = json.loads(path.read_text(encoding="utf-8"))
        place_id = record.get("id") or path.stem
        if (place_id not in records
                or record.get("fetched_date", "") > records[place_id].get("fetched_date", "")):
            records[place_id] = record
    return records


def _minute_of_week(period_point):
    """Minute of week for a Google open/close point {day, hour, minute}."""
    return (period_point["day"] * MINUTES_PER_DAY + period_point.get("hour", 0) * MINUTES_PER_HOUR
            + period_point.get("minute", 0))


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
        start_min, end_min = _minute_of_week(period["open"]), _minute_of_week(period["close"])
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


def venue_day_closes(intervals):
    """Last close per open-day, hours after that day's midnight (1 am next day -> 25.0)."""
    last_close_h = {}
    for start_min, end_min in intervals:
        day = start_min // MINUTES_PER_DAY
        last_close_h[day] = max(last_close_h.get(day, 0.0),
                                (end_min - day * MINUTES_PER_DAY) / MINUTES_PER_HOUR)
    return last_close_h


# ---------------------------------------------------------------------------
# Manual hours: Google Maps copy-paste -> intervals, same form as venue_intervals
# ---------------------------------------------------------------------------
def _clock_text_to_min(clock_text):
    """'15:30' -> minutes after midnight."""
    hours, minutes = clock_text.split(":")
    return int(hours) * MINUTES_PER_HOUR + int(minutes)


def _clock(text, default_suffix=None):
    """'11 am', '8:30 pm', or '5' with a default suffix -> (minutes after midnight, suffix)."""
    match = CLOCK_PATTERN.match(text)
    if not match:
        raise ValueError(f"unparsed time {text!r}")
    suffix = (match.group(3) or default_suffix or "").lower()
    if suffix not in (AM_SUFFIX, PM_SUFFIX):
        raise ValueError(f"no am/pm for {text!r}")
    hour = int(match.group(1)) % HOURS_PER_HALF_DAY + (HOURS_PER_HALF_DAY if suffix == PM_SUFFIX else 0)
    return hour * MINUTES_PER_HOUR + int(match.group(2) or 0), suffix


def manual_intervals(text):
    """Maps copy-paste -> ([(start, end)], flag). A start with no am/pm takes the end's suffix;
    a close at or before the open means the next day."""
    if not isinstance(text, str) or not text.strip():
        return [], FLAG_NO_HOURS
    for space_character in MAPS_SPACE_CHARACTERS:
        text = text.replace(space_character, " ")
    intervals, n_days_24h = [], 0
    for entry in text.split(DAY_ENTRY_SEPARATOR):
        day_name, spec = entry.split(DAY_NAME_SEPARATOR, 1)
        day, spec = FULL_DAY_INDEX[day_name.strip()], spec.strip()
        day_start_min = day * MINUTES_PER_DAY
        if spec.lower() == CLOSED_TEXT:
            continue
        if spec.lower() == OPEN_24_HOURS_TEXT:
            intervals.append((day_start_min, day_start_min + MINUTES_PER_DAY))
            n_days_24h += 1
            continue
        for block in spec.split(BLOCK_SEPARATOR):
            open_text, close_text = BLOCK_RANGE_PATTERN.split(block.strip())
            end_min, suffix = _clock(close_text)
            start_min, _ = _clock(open_text, default_suffix=suffix)
            if end_min <= start_min:
                end_min += MINUTES_PER_DAY                   # closes next day
            intervals.append((day_start_min + start_min, day_start_min + end_min))
    if n_days_24h == DAYS_PER_WEEK:
        return [(0, MINUTES_PER_WEEK)], FLAG_24H
    return intervals, FLAG_OK


def print_manual_hours(manual_df):
    """Print each manual row back as clock times, to eyeball against the paste."""
    def clock(minute_of_week):
        minute_of_day = minute_of_week % MINUTES_PER_DAY
        return f"{minute_of_day // MINUTES_PER_HOUR:02d}:{minute_of_day % MINUTES_PER_HOUR:02d}"

    for row in manual_df.itertuples():
        intervals, flag = manual_intervals(row.hours_copy_paste)
        shown = [f"{DAY_NAMES[start // MINUTES_PER_DAY]} {clock(start)}-{clock(end)}"
                 f"{'+1' if end // MINUTES_PER_DAY > start // MINUTES_PER_DAY else ''}"
                 for start, end in sorted(intervals)]
        print(f"{row.draw_no:>3} {row.name[:28]:<28} {flag:<8} {' | '.join(shown)}")


if __name__ == "__main__":
    main()
