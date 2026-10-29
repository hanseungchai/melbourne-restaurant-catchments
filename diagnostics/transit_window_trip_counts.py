"""Is the transit departure window a steady weekday timetable?

Claim under test: on the 2026-10-13 PTV feeds, the TRN-7 departure window (2026-11-04 to 2026-12-17,
32 weekdays) is a steady timetable: within the window, every date of a given weekday (Monday ...
Friday) runs the same scheduled service, per mode, with no public or school holiday inside it.
Where the pipeline relies on it: the TRN-7 departure draw picks a date uniformly among the window's
dates on the drawn weekday, so the dates must be interchangeable; config PT_COVERS_CHECK_DATES (the
window ends) and the transit validation pairs (TRN-8, TRN-10).
Pre-registered rule (set before the first run, 2026-10-14): SUPPORTED if, for each mode (train, tram,
in-scope bus) and each weekday, every window date's scheduled trip count is within 2% of the median
over that weekday's window dates. Otherwise NOT SUPPORTED: list the dates outside it and look at them
before the draw.
Trips are counted per service day (a trip after midnight belongs to the day it started on), from
calendar.txt + calendar_dates.txt + trips.txt. Bus counts drop route_type 701 (TRN-11), as the network
does. The dates just outside the window (2026-11-03 Melbourne Cup, from 2026-12-18 school holidays)
are reported as context, not tested. The figure covers the whole feed, so the 2026-10-14 open flag
(Wednesday bus count above the window's) is visible too.
Conclusion (run 2026-10-14): SUPPORTED. 32 window weekdays; every weekday's count is identical on all
its window dates, per mode (max deviation 0%): train 2,742 (Fri 2,852), tram 5,044 (Fri 5,267), bus
20,088-20,093 (Fri 20,442). Context: 2026-11-03 train 1,992 / bus 13,774 (tram unchanged, no holidays
recorded); 2026-12-18 equals a window Friday, and the school-holiday bus timetable starts 2026-12-21
(~16,100). Before the window, in-scope bus steps down: Oct 8-23 ~24,200, Oct 26-Nov 2 ~21,900; cause
not checked here (the 2026-10-14 flag's 24,198 is the first step, not a one-day oddity). Steady is
not complete: a session check the same day found the steps are whole route_id groups cancelled by
calendar_dates removals (prefix 42: 34 routes from Oct 26; 36 and 53: 28 routes from Nov 3-4), with
no replacements in this feed; the window has them throughout, so it is steady but missing them.
PTV's dataset page (read by the user) gives the cause: each weekly export is valid for 30 days, so
this release (exported 2026-10-09) is valid to ~2026-11-08 and the window is mostly past it. The
fixed window is dropped (TRN-7, 2026-10-14); this script is to be extended into the per-release
window check.

Inputs: the three zipped feeds in inputs/gtfs_ptv_20261013/ (read only).
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
Results carry the run date; a same-day rerun replaces that day's results.
"""
import datetime
import io
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GTFS_DIR = PROJECT_ROOT / "inputs" / "gtfs_ptv_20261013"
FEED_PATHS = {
    "train": GTFS_DIR / "metro_train" / "google_transit.zip",
    "tram":  GTFS_DIR / "tram" / "google_transit.zip",
    "bus":   GTFS_DIR / "metro_bus" / "google_transit.zip",
}
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
NAME = "transit_window_trip_counts"

# --- rules copied from the pipeline and the record -------------------------------------------------
EXCLUDED_ROUTE_TYPES = {701}                   # config.PT_EXCLUDED_ROUTE_TYPES (TRN-11)
WINDOW_START = datetime.date(2026, 11, 4)      # TRN-7 window, inclusive
WINDOW_END = datetime.date(2026, 12, 17)
EXPECTED_WINDOW_WEEKDAYS = 32                  # TRN-7
CONTEXT_DATES = [datetime.date(2026, 11, 3), datetime.date(2026, 12, 18)]

# --- the rule --------------------------------------------------------------------------------------
TOLERANCE_SHARE = 0.02                         # max |count / weekday median - 1| inside the window

GTFS_DATE_FORMAT = "%Y%m%d"
WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
N_WEEKDAYS = 5                                 # Monday..Friday are weekday indices 0..4
EXCEPTION_ADDED = 1
EXCEPTION_REMOVED = 2


def read_table(zip_file, table_name):
    """One GTFS table as strings (utf-8-sig drops PTV's byte-order mark)."""
    with zip_file.open(table_name) as raw:
        return pd.read_csv(io.TextIOWrapper(raw, encoding="utf-8-sig"), dtype=str)


def trips_per_date(feed_path):
    """Scheduled in-scope trips per service date over the feed's whole calendar."""
    with zipfile.ZipFile(feed_path) as zip_file:
        calendar_df = read_table(zip_file, "calendar.txt")
        calendar_dates_df = read_table(zip_file, "calendar_dates.txt")
        trips_df = read_table(zip_file, "trips.txt")[["route_id", "service_id"]]
        routes_df = read_table(zip_file, "routes.txt")[["route_id", "route_type"]]

    excluded_route_ids = set(routes_df.loc[routes_df["route_type"].astype(int).isin(EXCLUDED_ROUTE_TYPES),
                                           "route_id"])
    in_scope_trips_df = trips_df[~trips_df["route_id"].isin(excluded_route_ids)]
    trips_per_service = in_scope_trips_df.groupby("service_id").size()

    # active (date, service_id) pairs: the weekly calendar, then exceptions added and removed
    active = set()
    for row in calendar_df.itertuples(index=False):
        start = datetime.datetime.strptime(row.start_date, GTFS_DATE_FORMAT).date()
        end = datetime.datetime.strptime(row.end_date, GTFS_DATE_FORMAT).date()
        runs_on = [getattr(row, day) == "1" for day in WEEKDAY_NAMES]
        for service_date in pd.date_range(start, end).date:
            if runs_on[service_date.weekday()]:
                active.add((service_date, row.service_id))
    for row in calendar_dates_df.itertuples(index=False):
        service_date = datetime.datetime.strptime(row.date, GTFS_DATE_FORMAT).date()
        if int(row.exception_type) == EXCEPTION_ADDED:
            active.add((service_date, row.service_id))
        elif int(row.exception_type) == EXCEPTION_REMOVED:
            active.discard((service_date, row.service_id))

    counts = {}
    for service_date, service_id in active:
        counts[service_date] = counts.get(service_date, 0) + int(trips_per_service.get(service_id, 0))
    return pd.Series(counts).sort_index()


def main():
    run_tag = datetime.date.today().strftime(GTFS_DATE_FORMAT)
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)

    per_mode = {mode: trips_per_date(path) for mode, path in FEED_PATHS.items()}
    counts_df = pd.DataFrame(per_mode).fillna(0).astype(int)
    counts_df.index = pd.to_datetime(counts_df.index)
    counts_df.index.name = "service_date"
    counts_df["weekday"] = counts_df.index.day_name()
    counts_df["is_in_window"] = ((counts_df.index.date >= WINDOW_START)
                                 & (counts_df.index.date <= WINDOW_END))
    counts_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_tag}_per_date.csv")

    window_df = counts_df[counts_df["is_in_window"] & (counts_df.index.weekday < N_WEEKDAYS)]
    print(f"Window weekdays: {len(window_df)} (expected {EXPECTED_WINDOW_WEEKDAYS})")

    summary_rows, outside_rows = [], []
    for mode in FEED_PATHS:
        for weekday, group in window_df.groupby("weekday", sort=False):
            median = group[mode].median()
            deviation = group[mode] / median - 1
            summary_rows.append({"mode": mode, "weekday": weekday, "n_dates": len(group),
                                 "median": median, "min": group[mode].min(), "max": group[mode].max(),
                                 "max_abs_deviation": deviation.abs().max()})
            for service_date, value in deviation[deviation.abs() > TOLERANCE_SHARE].items():
                outside_rows.append({"mode": mode, "service_date": service_date.date(),
                                     "weekday": weekday, "trips": group.loc[service_date, mode],
                                     "median": median, "deviation": value})
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_tag}_window_summary.csv", index=False)
    with pd.option_context("display.width", 200):
        print(summary_df.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    print("\nContext dates (not tested):")
    for context_date in CONTEXT_DATES:
        row = counts_df.loc[pd.Timestamp(context_date)]
        print(f"  {context_date} {row['weekday']}: " + ", ".join(f"{m} {row[m]}" for m in FEED_PATHS))

    is_supported = not outside_rows and len(window_df) == EXPECTED_WINDOW_WEEKDAYS
    if outside_rows:
        print(f"\nDates outside {TOLERANCE_SHARE:.0%} of their weekday median:")
        print(pd.DataFrame(outside_rows).to_string(index=False))
    print(f"\nVerdict: {'SUPPORTED' if is_supported else 'NOT SUPPORTED'}")

    fig, axes = plt.subplots(len(FEED_PATHS), 1, figsize=(12, 9), sharex=True)
    for axis, mode in zip(axes, FEED_PATHS):
        is_weekday = counts_df.index.weekday < N_WEEKDAYS
        axis.plot(counts_df.index, counts_df[mode], color="0.7", linewidth=0.8)
        axis.scatter(counts_df.index[is_weekday], counts_df.loc[is_weekday, mode], s=10, label="weekday")
        axis.scatter(counts_df.index[~is_weekday], counts_df.loc[~is_weekday, mode], s=10, label="weekend")
        axis.axvspan(pd.Timestamp(WINDOW_START), pd.Timestamp(WINDOW_END), alpha=0.12, label="window")
        axis.set_ylabel(f"{mode} trips")
    axes[0].legend(loc="lower left")
    axes[0].set_title("Scheduled trips per service date, PTV feeds 2026-10-13 (bus excl. route_type 701)")
    fig.tight_layout()
    fig.savefig(DIAGNOSTIC_IMG_DIR / f"{NAME}_{run_tag}_per_date.png", dpi=120)


if __name__ == "__main__":
    main()
