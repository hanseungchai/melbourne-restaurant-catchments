"""Which vehicles does R5 take on the hard misses left after stage 1, against Google's routes?

Claim under test (concepts/transit.md TRN-13, groups of the hard misses; reported): the misses left after stage 1
(transit_hard_miss_range, no-wait plain at k = 2) split into timing (R5 boards an earlier vehicle than Google's
default: a departure-window or wait question; group 1) and network (R5 rides or walks faster on the same or other
lines: groups 3, 4, 2). Where it is used: whether a paid stage 3 (Google at several departures) could explain the
misses (it can only explain timing), and which free fix, if any, is worth trying.

Method (Claude's): R5 DetailedItineraries (DI) at a 1-min window from t - 1 (the no-wait start), 5 Monte Carlo
draws (T7 e: avoids the heap error), walk 4.16 km/h, each pair on its own release's network. Kept per option: the
rides (route short name, board clock time, ride minutes, stops) and walk distance. Ride times and boarding clock
times are usable; walk clock times are not (T7 e), and DI's egress walk may be off by an edge end distance
(transit_router_egress.py). Google: every returned route (lines, first board time, home wait, arrival, walk_m).
Read side by side; the summary counts first rides on the same line (R5 vs Google's default) and whether R5
boards earlier.

Conclusion (run 2026-10-18): DI's best arrival is 3-5 min later than TTM's N on transit misses (median by
  group): the known DI egress fault (transit_router_egress.py), so DI times are not evidence here; ride choices
  are. Early misses (groups 1, 3, other): R5 rides trains on 11 of 24 false-20 misses, mostly from CBD stations
  (Southern Cross 5, Flagstaff 2, Parliament, Melbourne Central, Flinders St, Parkville), where Google rides trams or
  boards a later train. Late misses (group 4): R5 takes the same line as Google's default, the next vehicle.

Inputs (read only): diagnostic_data/transit_hard_miss_range_*_misses.csv and _results.csv (newest); the Google
route tables in outputs/transit_validation/; the cleaned feeds as transit_band_metric; the OSM extract.
Self-contained (CLAUDE.md D1). No paid API calls; r5py only.
Usage: `python transit_hard_miss_itineraries.py route 20261009`, `... route 20261016`, then `... report`.
"""
import datetime
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
CLEANED_DIRS = {"20261009": PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned",
                "20261016": DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016"}
NAME = "transit_hard_miss_itineraries"
RANGE_NAME = "transit_hard_miss_range"
MISS_MODEL = "no-wait plain (reported)"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}

R5_MAX_MEMORY = "7G"
WINDOW_DATE = datetime.date(2026, 10, 21)
WINDOW_MIN = 1
DRAWS = 5
MAX_TIME_MIN = 90
WALK_SPEED_KMH = 4.16
BOARD_SLACK_MIN = 1
SECONDS_PER_MIN = 60
GTFS_ENCODING = "utf-8-sig"
LOCAL_TZ = "Australia/Melbourne"


def misses():
    misses_df = pd.read_csv(sorted(DIAGNOSTIC_DATA_DIR.glob(f"{RANGE_NAME}_*_misses.csv"))[-1])
    misses_df = misses_df[misses_df.model == MISS_MODEL]
    return misses_df.drop_duplicates(["set_name", "draw_no"])


def route_names(release):
    frames = []
    for feed_name in FEED_NAMES:
        with zipfile.ZipFile(CLEANED_DIRS[release] / f"{feed_name}.zip") as gtfs_zip:
            routes_df = pd.read_csv(gtfs_zip.open("routes.txt"), dtype=str, encoding=GTFS_ENCODING)
        frames.append(routes_df[["route_id", "route_short_name", "route_long_name"]])
    routes_df = pd.concat(frames, ignore_index=True).drop_duplicates("route_id")
    return dict(zip(routes_df.route_id, routes_df.route_short_name.fillna("") + " " + routes_df.route_long_name.fillna("")))


def route(release):
    sys.argv += ["--max-memory", R5_MAX_MEMORY]
    import geopandas as gpd
    from r5py import TransportMode, TransportNetwork
    from r5py.r5.regional_task import RegionalTask
    from r5py.r5.trip_planner import TripPlanner

    misses_df = misses()
    misses_df = misses_df[misses_df.release.astype(int).astype(str) == release]
    names = route_names(release)
    network = TransportNetwork(PBF_PATH, [CLEANED_DIRS[release] / f"{name}.zip" for name in FEED_NAMES])
    rows = []
    for pair in misses_df.itertuples():
        departure = (datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))
                     - datetime.timedelta(minutes=BOARD_SLACK_MIN))
        try:
            origin = gpd.points_from_xy([pair.origin_lon], [pair.origin_lat], crs="EPSG:4326")[0]
            destination = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
            request = RegionalTask(network, origin=origin, destinations=destination, departure=departure,
                                   departure_time_window=datetime.timedelta(minutes=WINDOW_MIN),
                                   transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
                                   max_time=datetime.timedelta(minutes=MAX_TIME_MIN), speed_walking=WALK_SPEED_KMH)
            request._regional_task.toLat, request._regional_task.toLon = pair.dest_lat, pair.dest_lon
            request._regional_task.monteCarloDraws = DRAWS
            trips = TripPlanner(network, request).trips
            for option, trip in enumerate(trips):
                for segment in trip.as_table():
                    (seg_no, mode, seg_departure, distance, travel_time, wait_time, _feed, _agency, route_id,
                     start_stop, end_stop, _geometry) = segment
                    rows.append({"set_name": pair.set_name, "draw_no": pair.draw_no, "option": option, "segment": seg_no,
                                 "mode": str(mode), "departure": seg_departure, "distance_m": distance,
                                 "travel_min": travel_time.total_seconds() / SECONDS_PER_MIN if travel_time is not None else np.nan,
                                 "wait_min": wait_time.total_seconds() / SECONDS_PER_MIN if wait_time is not None else np.nan,
                                 "route": names.get(route_id, route_id) if isinstance(route_id, str) and route_id else "",
                                 "start_stop": start_stop, "end_stop": end_stop})
        except Exception as error:                                   # recorded per pair, read after
            rows.append({"set_name": pair.set_name, "draw_no": pair.draw_no, "error": f"{type(error).__name__}: {error}"[:300]})
        print(f"  {pair.set_name} {pair.draw_no} done", flush=True)
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_legs_{release}.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"saved {path.name}")


def report():
    run_date = f"{datetime.date.today():%Y%m%d}"
    misses_df = misses()
    legs_df = pd.concat([pd.read_csv(sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_legs_{release}.csv"))[-1]) for release in CLEANED_DIRS],
                        ignore_index=True)
    google_df = pd.concat([pd.read_csv(path).assign(set_name=set_name) for set_name, path in ROUTES_PATHS.items()], ignore_index=True)
    lines = [f"{NAME} {run_date}: R5 DI ({DRAWS} draws, 1-min window from t - 1) vs Google's routes on the stage-1 misses "
             f"({MISS_MODEL}, {len(misses_df)} pairs)"]
    for pair in misses_df.sort_values(["group", "test", "draw_no"]).itertuples():
        lines.append("")
        lines.append(f"{pair.set_name} {pair.draw_no} | {pair.test} | {pair.group} | Google default {pair.default_min:.0f}, low {pair.low_2:.0f}, "
                     f"R5 N {pair.model_min:.0f}, walk-only {pair.walk_min} | {pair.haversine_m:.0f} m, dep "
                     f"{int(pair.dep_min_of_day) // 60:02d}:{int(pair.dep_min_of_day) % 60:02d}")
        pair_google = google_df[(google_df.set_name == pair.set_name) & (google_df.draw_no == pair.draw_no)].sort_values("route_ix")
        for route in pair_google.itertuples():
            board = pd.Timestamp(route.first_board_time).tz_convert(LOCAL_TZ).strftime("%H:%M") if isinstance(route.first_board_time, str) else "--"
            lines.append(f"  G{route.route_ix}{'*' if route.is_default else ' '} arr {route.arrival_from_request_s / SECONDS_PER_MIN:5.1f} "
                         f"wait {route.leave_wait_s / SECONDS_PER_MIN:4.1f} board {board} walk {route.walk_m:5.0f} m | {route.lines} | {route.route_scope}")
        pair_legs = legs_df[(legs_df.set_name == pair.set_name) & (legs_df.draw_no == pair.draw_no)]
        if "error" in pair_legs and pair_legs.error.notna().any():
            lines.append(f"  R5 error: {pair_legs.error.dropna().iloc[0]}")
            continue
        for option, option_df in pair_legs.groupby("option"):
            parts = []
            for leg in option_df.itertuples():
                if isinstance(leg.route, str) and leg.route:
                    parts.append(f"{leg.route.strip()} @{str(leg.departure)[11:16]} {leg.travel_min:.0f}m")
                else:
                    parts.append(f"{leg.mode.split('.')[-1].lower()} {leg.distance_m:.0f}m")
            walk_m = option_df.distance_m[option_df.route.fillna("") == ""].sum()
            lines.append(f"  R{option} walk {walk_m:5.0f} m | " + " > ".join(parts))
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "route":
        route(sys.argv[2])
    else:
        report()
