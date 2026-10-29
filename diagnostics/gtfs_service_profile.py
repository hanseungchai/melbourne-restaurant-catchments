"""GTFS service profile: how much transit runs in each hour of a week? (report only, free, no routing)

Question (concepts/reachability.md RCH-20, DESIGN.md Q25): the transit pass needs the coarsest departure schedule
the data allows. This profile is the timetable side of that choice: per mode, per calendar day x hour of one week,
how much service runs. transit_time_of_day_spans.py is the routing side and reads this script's service hours.
Where the pipeline would rely on it: the departure schedule of the transit reachability pass (RCH-20, open).
Report only; the schedule is the user's choice.

Method: raw PTV feeds of release 20261016 (inputs/gtfs_ptv_20261018/: metro_train, tram, metro_bus), bus without
route_type 701 (TRN-11). Active (date, service_id) pairs from calendar.txt + calendar_dates.txt (as
transit_window_trip_counts.py). Week Mon 2026-10-26 to Sun 2026-11-01 (inside the release's window; Melbourne Cup
Day 2026-11-03 outside); service day Sun 2026-10-25 is read too so its after-midnight trips land on Monday. Times
>= 24:00 move to the next calendar day; trips spilling past Sunday 24:00 are dropped. Per mode, per day x hour:
(1) active trips = trips started and not finished (first departure <= t < last arrival), mean of the 12 five-minute
samples in the hour (vehicles-in-service proxy); (2) stop departures in the hour (stop_times rows).
Also reported: block_id fill share (true vehicle counts need it), whether Mon-Thu are identical hour by hour, and
the hours with ~no service.

Claude's rule, not user-approved (written before the first run): a "service hour" is a calendar hour whose active
trips, summed over the three modes, are >= 5% of the week's busiest hour (SERVICE_SHARE_MIN). Hours below it count as
~no service; transit_time_of_day_spans.py routes only service hours.

Conclusion (run 2026-10-22, autonomous 71st; report only): block_id is filled on 71% of train trips and 0% of tram
and bus trips, so true vehicle counts are not possible; active trips stay the proxy. Week peak active trips: train
178, tram 343, bus 1,271 (all modes 1,774, Mon-Fri 17:00). Weekdays share one shape: 0.18 of peak at 05:00, 0.97 at
08:00, a flat ~0.73 midday, 1.00 at 17:00, then down to 0.66 / 0.50 / 0.39 / 0.23 at 19-22. Saturday rises to a flat
~0.55 from 10:00 to 17:00; Sunday to ~0.48 from 11:00 to 17:00. Service hours (Claude's rule): 142 of 168; ~no
service Mon 00-04, Tue-Fri 01-04, Sat 03-04, Sun 03-05 (weekend nights keep ~0.05 from the night trains). Mon-Thu are
not identical hour by hour: tram and bus differ by <= 1.1 active trips except at 00:00 (Monday's hour 0 holds Sunday
night's spill: bus 3.9 vs 38.7); train runs ~17 more active trips on Mon and Wed evenings (20-23 h) than on Tue and
Thu (calendar difference, cause not checked). Friday runs more from 18:00 (tram +10 to +21 active trips).

Inputs (read only): the three zipped feeds. Self-contained: imports nothing from functions/ or config.py (CLAUDE.md
D1). No API calls. Results carry the run date; a same-day rerun replaces that day's results.
Usage: `python gtfs_service_profile.py`.
"""
import datetime
import io
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GTFS_DIR = PROJECT_ROOT / "inputs" / "gtfs_ptv_20261018"
FEED_PATHS = {
    "train": GTFS_DIR / "metro_train" / "google_transit.zip",
    "tram":  GTFS_DIR / "tram" / "google_transit.zip",
    "bus":   GTFS_DIR / "metro_bus" / "google_transit.zip",
}
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
NAME = "gtfs_service_profile"

# --- values ----------------------------------------------------------------------------------------
EXCLUDED_ROUTE_TYPES = {701}                   # config.PT_EXCLUDED_ROUTE_TYPES (TRN-11)
WEEK_START = datetime.date(2026, 10, 26)       # Monday
WEEK_DAYS = 7
SAMPLE_STEP_S = 300                            # active-trip samples every 5 min
SERVICE_SHARE_MIN = 0.05                       # Claude's rule: service hour = >= 5% of the week's busiest hour
HOUR_S = 3600
DAY_S = 86400
MAX_SERVICE_DAY_S = 2 * DAY_S                  # GTFS times run past 24:00; 48 h is ample
GTFS_DATE_FORMAT = "%Y%m%d"
WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MON_THU = [0, 1, 2, 3]
EXCEPTION_ADDED = 1
EXCEPTION_REMOVED = 2


def read_table(zip_file, table_name, columns=None):
    """One GTFS table as strings (utf-8-sig drops PTV's byte-order mark)."""
    with zip_file.open(table_name) as raw:
        return pd.read_csv(io.TextIOWrapper(raw, encoding="utf-8-sig"), dtype=str, usecols=columns)


def to_seconds(times):
    """'HH:MM:SS' (hours may pass 24) -> seconds after the service day's midnight."""
    parts = times.str.split(":", expand=True).astype(np.int32)
    return (parts[0] * HOUR_S + parts[1] * 60 + parts[2]).to_numpy()


def active_services(calendar_df, calendar_dates_df, dates):
    """{date: set of service_id} for the given dates (weekly calendar, then exceptions)."""
    active = {service_date: set() for service_date in dates}
    for row in calendar_df.itertuples(index=False):
        start = datetime.datetime.strptime(row.start_date, GTFS_DATE_FORMAT).date()
        end = datetime.datetime.strptime(row.end_date, GTFS_DATE_FORMAT).date()
        for service_date in dates:
            if start <= service_date <= end and getattr(row, WEEKDAY_NAMES[service_date.weekday()]) == "1":
                active[service_date].add(row.service_id)
    for row in calendar_dates_df.itertuples(index=False):
        service_date = datetime.datetime.strptime(row.date, GTFS_DATE_FORMAT).date()
        if service_date in active:
            if int(row.exception_type) == EXCEPTION_ADDED:
                active[service_date].add(row.service_id)
            elif int(row.exception_type) == EXCEPTION_REMOVED:
                active[service_date].discard(row.service_id)
    return active


def profile_feed(feed_path):
    """Per service_id: stop departures per hour offset and active trips per 5-min sample; block_id fill share."""
    with zipfile.ZipFile(feed_path) as zip_file:
        calendar_df = read_table(zip_file, "calendar.txt")
        calendar_dates_df = read_table(zip_file, "calendar_dates.txt")
        trips_df = read_table(zip_file, "trips.txt", ["route_id", "service_id", "trip_id", "block_id"])
        routes_df = read_table(zip_file, "routes.txt", ["route_id", "route_type"])
        stop_times_df = read_table(zip_file, "stop_times.txt", ["trip_id", "arrival_time", "departure_time"])
    excluded = set(routes_df.loc[routes_df.route_type.astype(int).isin(EXCLUDED_ROUTE_TYPES), "route_id"])
    trips_df = trips_df[~trips_df.route_id.isin(excluded)]
    block_fill = float(trips_df.block_id.notna().mean())
    stop_times_df = stop_times_df[stop_times_df.trip_id.isin(trips_df.trip_id)]
    stop_times_df = stop_times_df.assign(dep_s=to_seconds(stop_times_df.departure_time),
                                         arr_s=to_seconds(stop_times_df.arrival_time))
    stop_times_df["service_id"] = stop_times_df.trip_id.map(trips_df.set_index("trip_id").service_id)

    n_hours = MAX_SERVICE_DAY_S // HOUR_S
    sample_s = np.arange(0, MAX_SERVICE_DAY_S, SAMPLE_STEP_S)
    departures_by_service, active_by_service = {}, {}
    spans_df = stop_times_df.groupby(["service_id", "trip_id"]).agg(start_s=("dep_s", "min"), end_s=("arr_s", "max"))
    for service_id, group in stop_times_df.groupby("service_id"):
        departures_by_service[service_id] = np.bincount(group.dep_s.to_numpy() // HOUR_S, minlength=n_hours)[:n_hours]
    for service_id, spans in spans_df.groupby(level="service_id"):
        starts, ends = np.sort(spans.start_s.to_numpy()), np.sort(spans.end_s.to_numpy())
        active_by_service[service_id] = (np.searchsorted(starts, sample_s, side="right")
                                         - np.searchsorted(ends, sample_s, side="right"))
    return calendar_df, calendar_dates_df, departures_by_service, active_by_service, block_fill


def week_profile(feed_path):
    """Long table: calendar date x hour -> active trips (mean of samples) and stop departures."""
    calendar_df, calendar_dates_df, departures_by_service, active_by_service, block_fill = profile_feed(feed_path)
    service_dates = [WEEK_START + datetime.timedelta(days=offset) for offset in range(-1, WEEK_DAYS)]
    active = active_services(calendar_df, calendar_dates_df, service_dates)
    week_hours = WEEK_DAYS * 24
    samples_per_hour = HOUR_S // SAMPLE_STEP_S
    departures = np.zeros(week_hours)
    active_samples = np.zeros(week_hours * samples_per_hour)
    n_hours = MAX_SERVICE_DAY_S // HOUR_S
    for service_date, service_ids in active.items():
        offset_h = (service_date - WEEK_START).days * 24        # -24 for the Sunday before
        hour_index = offset_h + np.arange(n_hours)
        keep = (hour_index >= 0) & (hour_index < week_hours)
        sample_index = offset_h * samples_per_hour + np.arange(n_hours * samples_per_hour)
        keep_samples = (sample_index >= 0) & (sample_index < len(active_samples))
        for service_id in service_ids:
            if service_id not in departures_by_service:
                continue
            departures[hour_index[keep]] += departures_by_service[service_id][keep]
            active_samples[sample_index[keep_samples]] += active_by_service[service_id][keep_samples]
    active_trips = active_samples.reshape(week_hours, samples_per_hour).mean(axis=1)
    dates = [WEEK_START + datetime.timedelta(days=h // 24) for h in range(week_hours)]
    return pd.DataFrame({"date": dates, "weekday": [d.strftime("%a") for d in dates],
                         "hour": np.arange(week_hours) % 24, "active_trips": active_trips,
                         "stop_departures": departures.astype(int)}), block_fill


def main():
    run_tag = datetime.date.today().strftime(GTFS_DATE_FORMAT)
    out_prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_tag}"
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
    frames, lines = [], [f"{NAME} run {run_tag}: week {WEEK_START} (Mon) + {WEEK_DAYS - 1} days, feeds {GTFS_DIR.name}"]
    for mode, path in FEED_PATHS.items():
        mode_df, block_fill = week_profile(path)
        frames.append(mode_df.assign(mode=mode))
        lines.append(f"{mode}: block_id filled on {block_fill:.1%} of trips; week peak active trips "
                     f"{mode_df.active_trips.max():.0f}; stop departures {mode_df.stop_departures.sum():,}")
        print(lines[-1], flush=True)
    profile_df = pd.concat(frames, ignore_index=True)
    profile_df.to_csv(f"{out_prefix}_per_hour.csv", index=False)

    lines.append("\nMon-Thu identical hour by hour (active trips and stop departures)?")
    for mode, mode_df in profile_df.groupby("mode", sort=False):
        days = [mode_df[pd.to_datetime(mode_df.date).dt.weekday == day] for day in MON_THU]
        max_diff_trips = max(np.abs(days[0].active_trips.to_numpy() - d.active_trips.to_numpy()).max() for d in days[1:])
        max_diff_deps = max(np.abs(days[0].stop_departures.to_numpy() - d.stop_departures.to_numpy()).max() for d in days[1:])
        lines.append(f"  {mode}: max |diff| vs Monday: active trips {max_diff_trips:.2f}, stop departures {max_diff_deps}")

    total_df = profile_df.groupby(["date", "weekday", "hour"], as_index=False)[["active_trips", "stop_departures"]].sum()
    total_df["share_of_peak"] = total_df.active_trips / total_df.active_trips.max()
    total_df["is_service_hour"] = total_df.share_of_peak >= SERVICE_SHARE_MIN
    total_df.to_csv(f"{out_prefix}_service_hours.csv", index=False)
    lines.append(f"\nService hours (all modes' active trips >= {SERVICE_SHARE_MIN:.0%} of the week's busiest hour, "
                 f"{total_df.active_trips.max():.0f}; Claude's rule): {int(total_df.is_service_hour.sum())} of "
                 f"{len(total_df)}")
    for (date, weekday), day_df in total_df.groupby(["date", "weekday"], sort=True):
        quiet = day_df.loc[~day_df.is_service_hour, "hour"].tolist()
        lines.append(f"  {date} {weekday}: ~no service at hours {quiet}; share of peak by hour "
                     + " ".join(f"{v:.2f}" for v in day_df.share_of_peak))

    fig, axes = plt.subplots(2, len(FEED_PATHS), figsize=(18, 7))
    day_labels = [f"{(WEEK_START + datetime.timedelta(days=d)):%a %d}" for d in range(WEEK_DAYS)]
    for col, mode in enumerate(FEED_PATHS):
        mode_df = profile_df[profile_df["mode"] == mode]
        for row, column in enumerate(["active_trips", "stop_departures"]):
            axis = axes[row, col]
            grid = mode_df[column].to_numpy().reshape(WEEK_DAYS, 24)
            image = axis.imshow(grid, aspect="auto", cmap="viridis")
            axis.set_yticks(range(WEEK_DAYS), day_labels)
            axis.set_xticks(range(0, 24, 2))
            axis.set_title(f"{mode}: {column.replace('_', ' ')} per hour")
            fig.colorbar(image, ax=axis)
    axes[1, 0].set_xlabel("hour of day (calendar; times >= 24:00 moved to the next day)")
    fig.suptitle(f"PTV GTFS release 20261016, week of {WEEK_START} (bus excl. route_type 701)")
    fig.tight_layout()
    fig.savefig(DIAGNOSTIC_IMG_DIR / f"{NAME}_{run_tag}_heatmaps.png", dpi=110)

    summary = "\n".join(lines)
    Path(f"{out_prefix}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main()
