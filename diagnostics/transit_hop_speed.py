"""Are the current feed's scheduled times free of impossible speeds?

Claim under test: on the PTV feeds config.PT_GTFS_DIR points at (2026-10-13 download, 2026-10-09
export), no scheduled ride between stops implies a speed no vehicle of its mode could reach, i.e. the
timetable carries no time misinputs (a stop time typed an hour or a few minutes early).
Where the pipeline relies on it: TRN-4 routes on raw published durations with no repair, and R5 prices
a ride as arrival at B - departure at A from stop_times alone (it never uses lengths), so a misinput
reaches every reachability and validation time that rides through it, unseen.
Method: per trip, in stop_sequence order, for each timed stop the span to the first later stop whose
arrival is at least MIN_SPAN_S after this stop's departure (so minute rounding can't give a zero or
near-zero time); span distance = sum of straight-line (haversine) hops between the stops passed. The
straight line is shorter than the track, so the speed is a lower bound: a flagged span is too fast
for certain. Times going backwards within a trip are flagged on their own. Untimed stops are skipped
(dropping them keeps the distance a lower bound). Bus drops route_type 701 (TRN-11), as the network
does. Not caught: times too slow (a misinput that lengthens a ride), which no speed cap can see.
Pre-registered rule (set before the first run, 2026-10-16): SUPPORTED if no span exceeds its mode's
cap (bus and tram 120 km/h, train 160 km/h) and no trip's times go backwards. Otherwise NOT
SUPPORTED: list the flagged spans (route, trip, stops, times) and look at them before the next fetch.
Conclusion (run 2026-10-16): NOT SUPPORTED. Train (max 85.0 km/h) and tram (max 43.9) pass; bus has
629 spans on 193 of 195,369 trips over 120 km/h (max 302.8; 4-10 km timetabled at 2-3 min; routes 788,
887 and 479 for 95%); no trip's times go backwards in any feed. Looked at and accepted (user,
2026-10-16): TRN-4 stands, the feed is routed as published; dropping the trips changes every trip
that connects with them, and no defensible repair exists. Stated in transit.md Limitations.

Inputs: the three zipped feeds in inputs/gtfs_ptv_20261013/ (read only).
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
Results carry the run date; a same-day rerun replaces that day's results.
Memory: the bus stop_times table is ~684 MB unzipped; run when a few GB of RAM are free.
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
GTFS_DIR = PROJECT_ROOT / "inputs" / "gtfs_ptv_20261013"
FEED_PATHS = {
    "train": GTFS_DIR / "metro_train" / "google_transit.zip",
    "tram":  GTFS_DIR / "tram" / "google_transit.zip",
    "bus":   GTFS_DIR / "metro_bus" / "google_transit.zip",
}
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
NAME = "transit_hop_speed"

# --- rules copied from the pipeline and the record -------------------------------------------------
EXCLUDED_ROUTE_TYPES = {701}                   # config.PT_EXCLUDED_ROUTE_TYPES (TRN-11)

# --- the rule --------------------------------------------------------------------------------------
MIN_SPAN_S = 120                               # shortest scheduled time a span may have
SPEED_CAP_KMH = {"train": 160, "tram": 120, "bus": 120}

EARTH_RADIUS_M = 6_371_008.8
SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60
HOURS_PER_DAY = 24
TRIP_GAP_DAYS = 10                             # spacing of trips on the shared time axis; > any service day
METRES_PER_KM = 1000
STOP_TIME_COLUMNS = ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]
TOP_N_PRINTED = 10                             # fastest spans printed per mode
HISTOGRAM_BIN_KMH = 5


def read_table(zip_file, table_name, columns=None):
    """One GTFS table as strings (utf-8-sig drops PTV's byte-order mark)."""
    with zip_file.open(table_name) as raw:
        return pd.read_csv(io.TextIOWrapper(raw, encoding="utf-8-sig"), dtype=str, usecols=columns)


def gtfs_time_to_seconds(time_series):
    """'HH:MM:SS' (hours may pass 24) to seconds since the service day's start."""
    parts = time_series.str.split(":", expand=True).astype(float)
    return parts[0] * SECONDS_PER_HOUR + parts[1] * SECONDS_PER_MINUTE + parts[2]


def haversine_m(lat_a, lon_a, lat_b, lon_b):
    """Great-circle distance in metres between arrays of points given in degrees."""
    lat_a, lon_a, lat_b, lon_b = map(np.radians, (lat_a, lon_a, lat_b, lon_b))
    half_chord = (np.sin((lat_b - lat_a) / 2) ** 2
                  + np.cos(lat_a) * np.cos(lat_b) * np.sin((lon_b - lon_a) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(half_chord))


def load_timed_stop_times(feed_path):
    """In-scope timed stop times, sorted by trip and stop_sequence, with stop coordinates and route."""
    with zipfile.ZipFile(feed_path) as zip_file:
        routes_df = read_table(zip_file, "routes.txt", ["route_id", "route_short_name", "route_type"])
        trips_df = read_table(zip_file, "trips.txt", ["trip_id", "route_id"])
        stops_df = read_table(zip_file, "stops.txt", ["stop_id", "stop_name", "stop_lat", "stop_lon"])
        stop_times_df = read_table(zip_file, "stop_times.txt", STOP_TIME_COLUMNS)

    excluded_route_ids = set(routes_df.loc[routes_df["route_type"].astype(int).isin(EXCLUDED_ROUTE_TYPES),
                                           "route_id"])
    in_scope_trip_ids = set(trips_df.loc[~trips_df["route_id"].isin(excluded_route_ids), "trip_id"])
    stop_times_df = stop_times_df[stop_times_df["trip_id"].isin(in_scope_trip_ids)]

    n_rows = len(stop_times_df)
    is_timed = stop_times_df["arrival_time"].notna() & stop_times_df["departure_time"].notna()
    stop_times_df = stop_times_df[is_timed].copy()
    stop_times_df["arrival_s"] = gtfs_time_to_seconds(stop_times_df["arrival_time"])
    stop_times_df["departure_s"] = gtfs_time_to_seconds(stop_times_df["departure_time"])
    stop_times_df["stop_sequence"] = stop_times_df["stop_sequence"].astype(int)
    stop_times_df = stop_times_df.drop(columns=["arrival_time", "departure_time"])

    stops_df[["stop_lat", "stop_lon"]] = stops_df[["stop_lat", "stop_lon"]].astype(float)
    stop_times_df = stop_times_df.merge(stops_df, on="stop_id", how="left")
    stop_times_df = stop_times_df.merge(trips_df, on="trip_id", how="left")
    stop_times_df = stop_times_df.merge(routes_df[["route_id", "route_short_name"]], on="route_id",
                                        how="left")
    stop_times_df = stop_times_df.sort_values(["trip_id", "stop_sequence"], ignore_index=True)
    return stop_times_df, n_rows - len(stop_times_df)


def backwards_times(stop_times_df):
    """Rows whose arrival is before the previous stop's departure, or whose departure is before its arrival."""
    is_same_trip = stop_times_df["trip_id"].eq(stop_times_df["trip_id"].shift())
    is_before_previous = is_same_trip & (stop_times_df["arrival_s"] < stop_times_df["departure_s"].shift())
    is_dwell_negative = stop_times_df["departure_s"] < stop_times_df["arrival_s"]
    return stop_times_df[is_before_previous | is_dwell_negative]


def spans(stop_times_df):
    """Per timed stop, the span to the first later stop of its trip at least MIN_SPAN_S later.

    Trips are laid end to end on one time axis (trip index * a gap longer than any service day + time)
    so one searchsorted finds each span's end; a start whose end falls in the next trip has no span.
    Assumes times never go backwards within a trip (checked separately).
    """
    trip_index = pd.factorize(stop_times_df["trip_id"])[0].astype(np.int64)
    trip_gap_s = TRIP_GAP_DAYS * HOURS_PER_DAY * SECONDS_PER_HOUR
    arrival_axis = trip_index * trip_gap_s + stop_times_df["arrival_s"].to_numpy()
    departure_axis = trip_index * trip_gap_s + stop_times_df["departure_s"].to_numpy()
    end = np.searchsorted(arrival_axis, departure_axis + MIN_SPAN_S, side="left")
    has_end = end < len(stop_times_df)
    has_end[has_end] = trip_index[end[has_end]] == trip_index[has_end]

    lat = stop_times_df["stop_lat"].to_numpy()
    lon = stop_times_df["stop_lon"].to_numpy()
    is_same_trip = np.r_[False, trip_index[1:] == trip_index[:-1]]
    hop_m = np.where(is_same_trip, haversine_m(np.r_[lat[0], lat[:-1]], np.r_[lon[0], lon[:-1]], lat, lon), 0)
    cumulative_m = np.cumsum(hop_m)

    start = np.flatnonzero(has_end)
    end = end[has_end]
    span_m = cumulative_m[end] - cumulative_m[start]
    span_s = stop_times_df["arrival_s"].to_numpy()[end] - stop_times_df["departure_s"].to_numpy()[start]
    span_df = pd.DataFrame({
        "route_short_name": stop_times_df["route_short_name"].to_numpy()[start],
        "trip_id": stop_times_df["trip_id"].to_numpy()[start],
        "from_stop": stop_times_df["stop_name"].to_numpy()[start],
        "to_stop": stop_times_df["stop_name"].to_numpy()[end],
        "from_sequence": stop_times_df["stop_sequence"].to_numpy()[start],
        "to_sequence": stop_times_df["stop_sequence"].to_numpy()[end],
        "departure_s": stop_times_df["departure_s"].to_numpy()[start],
        "arrival_s": stop_times_df["arrival_s"].to_numpy()[end],
        "span_km": span_m / METRES_PER_KM,
        "span_min": span_s / SECONDS_PER_MINUTE,
    })
    span_df["speed_kmh"] = span_m / span_s * SECONDS_PER_HOUR / METRES_PER_KM
    return span_df


def main():
    run_tag = datetime.date.today().strftime("%Y%m%d")
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)

    summary_rows, flagged_frames, speeds_per_mode = [], [], {}
    is_supported = True
    for mode, feed_path in FEED_PATHS.items():
        stop_times_df, n_untimed = load_timed_stop_times(feed_path)
        backwards_df = backwards_times(stop_times_df)
        span_df = spans(stop_times_df)
        cap_kmh = SPEED_CAP_KMH[mode]
        flagged_df = span_df[span_df["speed_kmh"] > cap_kmh].sort_values("speed_kmh", ascending=False)
        speeds_per_mode[mode] = span_df["speed_kmh"].to_numpy()

        summary_rows.append({
            "mode": mode, "timed_stop_times": len(stop_times_df), "untimed_skipped": n_untimed,
            "trips": stop_times_df["trip_id"].nunique(), "spans": len(span_df),
            "median_kmh": span_df["speed_kmh"].median(), "p99_kmh": span_df["speed_kmh"].quantile(0.99),
            "max_kmh": span_df["speed_kmh"].max(), "cap_kmh": cap_kmh,
            "spans_over_cap": len(flagged_df), "trips_over_cap": flagged_df["trip_id"].nunique(),
            "backwards_rows": len(backwards_df), "backwards_trips": backwards_df["trip_id"].nunique(),
        })
        is_supported = is_supported and flagged_df.empty and backwards_df.empty
        flagged_frames.append(flagged_df.assign(mode=mode, kind="over_cap"))
        if not backwards_df.empty:
            flagged_frames.append(backwards_df.assign(mode=mode, kind="backwards"))

        print(f"\n{mode}: fastest {TOP_N_PRINTED} spans")
        with pd.option_context("display.width", 220, "display.max_colwidth", 40):
            print(span_df.nlargest(TOP_N_PRINTED, "speed_kmh").to_string(index=False, float_format="{:.2f}".format))
        del stop_times_df, span_df

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_tag}_summary.csv", index=False)
    pd.concat(flagged_frames, ignore_index=True).to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_tag}_flagged.csv",
                                                        index=False)
    print()
    with pd.option_context("display.width", 220):
        print(summary_df.to_string(index=False, float_format="{:.1f}".format))
    print(f"\nVerdict: {'SUPPORTED' if is_supported else 'NOT SUPPORTED'}")

    fig, axes = plt.subplots(len(FEED_PATHS), 1, figsize=(10, 9))
    for axis, (mode, speeds_kmh) in zip(axes, speeds_per_mode.items()):
        bins = np.arange(0, max(speeds_kmh.max(), SPEED_CAP_KMH[mode]) + HISTOGRAM_BIN_KMH, HISTOGRAM_BIN_KMH)
        axis.hist(speeds_kmh, bins=bins, color="0.4")
        axis.axvline(SPEED_CAP_KMH[mode], color="red", linewidth=1, label=f"cap {SPEED_CAP_KMH[mode]} km/h")
        axis.set_yscale("log")
        axis.set_ylabel(f"{mode} spans")
        axis.legend(loc="upper right")
    axes[-1].set_xlabel(f"straight-line speed over spans >= {MIN_SPAN_S // SECONDS_PER_MINUTE} min (km/h)")
    axes[0].set_title("Scheduled span speeds, PTV feeds 2026-10-13 (bus excl. route_type 701)")
    fig.tight_layout()
    fig.savefig(DIAGNOSTIC_IMG_DIR / f"{NAME}_{run_tag}_speeds.png", dpi=120)


if __name__ == "__main__":
    main()
