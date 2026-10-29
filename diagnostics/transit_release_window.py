"""Which weekdays form a PTV release's fetch window (TRN-7), and is that window a steady timetable?

Claim under test: for the 2026-10-09 PTV release (inputs/gtfs_ptv_20261013/), the TRN-7 window rule
(decided 2026-10-14) gives a set of weekdays on which every in-scope route group runs and each weekday's
dates are interchangeable. The rule: weekdays (1) after the fetch day (Melbourne time); (2) within 30 days
of the release's export date; (3) before the first date any in-scope route_id group drops out of the feed
for good; (4) minus public holidays; (5) minus any weekday more than 2% off its weekday's median trip count
inside the window, per mode.
Where the pipeline relies on it: config TRANSIT_RELEASE_FETCH_DATES (first and last fetch date per
release; provisional until this check) and through it transit_fetch.assign_departures, which picks a
pair's date uniformly among the window's dates on its weekday; config PT_COVERS_CHECK_DATES (the window's
ends, TRN-7).
Route groups: the route_id's leading field (before the first "-"), as in the 2026-10-14 session check
(prefix 42: 34 routes cancelled from Oct 26; 36 and 53 from Nov 3-4). A group's horizon is the day after
its last date with any in-scope trip; this closes the D1 gap "route-group horizons" (TRN-7 evidence).
Trips are counted per service day from calendar.txt + calendar_dates.txt + trips.txt, bus without
route_type 701 (TRN-11), as in diagnostics/transit_window_trip_counts.py (copied, D1).
Pre-registered rule (set before the first run, 2026-10-16): SUPPORTED if the window holds at least one
date on every weekday Monday-Friday and no window date is dropped by step (5). Otherwise NOT SUPPORTED:
report which weekdays are missing or dropped; the window is then the user's call.
Context, no rule: per-date counts from the export date to the 30-day limit, so the open flag "Oct 8-23
train counts not steady (2,746-3,055)" is visible.

Conclusion (run 2026-10-16): SUPPORTED. Window 2026-10-19 to 2026-10-23, one date per weekday: steps
(1)-(2) give 15 weekdays (Oct 19 - Nov 6); step (3) cuts at Oct 26, when bus group 42 stops (next: bus 53
from Nov 4, bus 36 and 49 from Dec 21); no holiday inside; step (5) drops nothing, but with one date per
weekday it cannot bite (each date is its own median). The flagged train spread is between weekdays, not
within one: Mon-Wed 2,842, Thu 2,746, Fri 2,852 (Oct 12-16: 2,828 / 2,748 / 3,055). Matches the
provisional config value. Consequence: the fetch must run before the pairs' dates; fetching after Oct 19
removes Monday from this release's window (then NOT SUPPORTED under this rule).

Inputs: the three zipped feeds in inputs/gtfs_ptv_20261013/ (read only). Self-contained: imports nothing
from functions/ or config.py (CLAUDE.md D1). No paid API calls. Results carry the run date; a same-day
rerun replaces that day's results.
"""
import datetime
import io
import zipfile
from pathlib import Path

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
NAME = "transit_release_window"

# --- the release and the rule (TRN-7, decided 2026-10-14) --------------------------------------------
RELEASE = "20261009"                           # PTV export date of these feeds (config.TRANSIT_DRAW_RELEASE)
EXPORT_DATE = datetime.date(2026, 10, 9)
VALID_DAYS = 30                                # each weekly export is valid for 30 days (PTV dataset page)
FETCH_DAY = datetime.date(2026, 10, 16)        # window starts after this (Melbourne); the planned fetch day
PUBLIC_HOLIDAYS = [datetime.date(2026, 11, 3),     # Melbourne Cup
                   datetime.date(2026, 12, 25),    # Christmas Day
                   datetime.date(2026, 12, 28)]    # Boxing Day (substitute Monday)
TOLERANCE_SHARE = 0.02                         # step (5): max |count / weekday median - 1|
EXCLUDED_ROUTE_TYPES = {701}                   # config.PT_EXCLUDED_ROUTE_TYPES (TRN-11)

ROUTE_GROUP_SEPARATOR = "-"
GTFS_DATE_FORMAT = "%Y%m%d"
WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
N_WEEKDAYS = 5                                 # Monday..Friday are weekday indices 0..4
EXCEPTION_ADDED = 1
EXCEPTION_REMOVED = 2


def read_table(zip_file, table_name):
    """One GTFS table as strings (utf-8-sig drops PTV's byte-order mark)."""
    with zip_file.open(table_name) as raw:
        return pd.read_csv(io.TextIOWrapper(raw, encoding="utf-8-sig"), dtype=str)


def trips_per_date_and_group(feed_path):
    """Scheduled in-scope trips per (service date, route group) over the feed's whole calendar."""
    with zipfile.ZipFile(feed_path) as zip_file:
        calendar_df = read_table(zip_file, "calendar.txt")
        calendar_dates_df = read_table(zip_file, "calendar_dates.txt")
        trips_df = read_table(zip_file, "trips.txt")[["route_id", "service_id"]]
        routes_df = read_table(zip_file, "routes.txt")[["route_id", "route_type"]]

    excluded_route_ids = set(routes_df.loc[routes_df["route_type"].astype(int).isin(EXCLUDED_ROUTE_TYPES),
                                           "route_id"])
    trips_df = trips_df[~trips_df["route_id"].isin(excluded_route_ids)]
    trips_df = trips_df.assign(group=trips_df["route_id"].str.split(ROUTE_GROUP_SEPARATOR).str[0])
    trips_per_service = trips_df.groupby(["service_id", "group"]).size().rename("trips").reset_index()

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

    active_df = pd.DataFrame(sorted(active), columns=["service_date", "service_id"])
    return (active_df.merge(trips_per_service, on="service_id")
            .groupby(["service_date", "group"]).trips.sum().reset_index())


def main():
    run_tag = datetime.date.today().strftime(GTFS_DATE_FORMAT)
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    per_group = pd.concat([trips_per_date_and_group(path).assign(mode=mode) for mode, path in FEED_PATHS.items()],
                          ignore_index=True)
    per_group["mode_group"] = per_group["mode"] + ":" + per_group["group"]

    # step (3): each group's horizon, the day after its last date with trips
    horizons = (per_group.groupby("mode_group").service_date.max() + datetime.timedelta(days=1)).sort_values()
    first_horizon = horizons.iloc[0]
    feed_end = per_group.service_date.max()

    last_valid = EXPORT_DATE + datetime.timedelta(days=VALID_DAYS)
    candidates = [FETCH_DAY + datetime.timedelta(days=k) for k in range(1, (last_valid - FETCH_DAY).days + 1)]
    steps = {}
    weekdays = [d for d in candidates if d.weekday() < N_WEEKDAYS]
    steps["(1)-(2) weekdays after the fetch day, within 30 days of export"] = list(weekdays)
    weekdays = [d for d in weekdays if d < first_horizon]
    steps[f"(3) before the first group horizon {first_horizon}"] = list(weekdays)
    weekdays = [d for d in weekdays if d not in PUBLIC_HOLIDAYS]
    steps["(4) minus public holidays"] = list(weekdays)

    counts_df = per_group.pivot_table(index="service_date", columns="mode", values="trips", aggfunc="sum",
                                      fill_value=0)[list(FEED_PATHS)]
    window_df = counts_df.loc[counts_df.index.isin(weekdays)].copy()
    window_df["weekday"] = [d.strftime("%a") for d in window_df.index]
    dropped = set()
    deviation_rows = []
    for mode in FEED_PATHS:
        for weekday, group_df in window_df.groupby("weekday"):
            deviation = group_df[mode] / group_df[mode].median() - 1
            for service_date, value in deviation.items():
                deviation_rows.append({"mode": mode, "service_date": service_date, "weekday": weekday,
                                       "trips": group_df.loc[service_date, mode], "deviation": value})
                if abs(value) > TOLERANCE_SHARE:
                    dropped.add(service_date)
    weekdays = [d for d in weekdays if d not in dropped]
    steps[f"(5) minus dates > {TOLERANCE_SHARE:.0%} off their weekday median"] = list(weekdays)

    covered = {d.weekday() for d in weekdays}
    is_supported = covered == set(range(N_WEEKDAYS)) and not dropped
    verdict = "SUPPORTED" if is_supported else "NOT SUPPORTED"

    context_df = counts_df.loc[(counts_df.index >= EXPORT_DATE) & (counts_df.index <= last_valid)].copy()
    context_df["weekday"] = [d.strftime("%a") for d in context_df.index]
    context_df["in_window"] = context_df.index.isin(weekdays)
    lines = [f"{NAME} {run_tag}: {verdict} (release {RELEASE}, fetch day {FETCH_DAY}, feed calendar ends {feed_end})",
             *[f"  {step}: {len(dates)} dates, {dates[0] if dates else '-'} to {dates[-1] if dates else '-'}"
               for step, dates in steps.items()],
             f"window: {[d.isoformat() for d in weekdays]}",
             f"weekdays covered: {sorted(WEEKDAY_NAMES[i][:3] for i in covered)}",
             f"proposed config: TRANSIT_RELEASE_FETCH_DATES = {{\"{RELEASE}\": ({weekdays[0]!r}, {weekdays[-1]!r})}}"
             if weekdays else "no window",
             "earliest route-group horizons (group: first day without trips):",
             horizons.head(8).to_string(),
             "per-date trips, export date to the 30-day limit:",
             context_df.to_string()]
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_tag}_summary.txt").write_text(summary, encoding="utf-8")
    horizons.rename("horizon").to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_tag}_group_horizons.csv")
    pd.DataFrame(deviation_rows).to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_tag}_window_deviation.csv", index=False)


if __name__ == "__main__":
    main()
