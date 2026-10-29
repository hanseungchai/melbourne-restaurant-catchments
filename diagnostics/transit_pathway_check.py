"""Does the train feed's pathway data (entrance to platform times) match Google's walks to and from stations?

Claim under test (concepts/transit.md TRN-13 (f), pathways; rule set before the run, user 2026-10-18): R5 reads no
pathways.txt, so it skips in-station time that people really walk. The feed's pathway times are kept (on fidelity, not
on the score) if they match reality, with Google's walks as the evidence. Where the pipeline would rely on it: a
derived street network for transit bands 1-2 (an OSM footway spur per entrance, the platform stop moved to the spur
end; outputs/ only), then the stage 1 rerun.

Rule (user): over every scored pair where Google's default boards or alights at a train platform with pathway data
(not only the 11 false-20 misses: those were picked for a slow Google walk), predicted extra = (pathway time minus
R5's own platform link) and observed extra = (Google's walk minus R5's walk to the same platform); match = within
MATCH_TOLERANCE_S either way; data accepted if >= ACCEPT_SHARE match. Overshoot (predicted > observed) reported apart.
Whether traversal_time is filled (not only length) is checked first.

Method (Claude's): Google's default (route default_ix of the stage-1 results) gives, per side, the train stop
(first TRANSIT step for boarding, last for alighting, if HEAVY_RAIL), its clock time and the walk between it and the
pair's origin (boarding) or destination (alighting), as summed walk-step staticDuration. The platform is the feed stop
within MATCH_RADIUS_M of Google's stop with a departure (boarding) or arrival (alighting) on Google's line within
+-TIME_TOLERANCE_MIN of Google's clock time on WINDOW_DATE, in the pair's release; nearest first. Pathway time per
entrance (location_type 2) = shortest traversal_time path in pathways.txt (is_bidirectional honoured), entrance ->
platform for boarding, platform -> entrance for alighting. R5 walks (one r5py DetailedItineraries walk-only call,
WALK_SPEED_KMH; travel_time in seconds, R5's point-to-street link included): end -> platform point (as R5 now) and
end -> each entrance point. With pathways, R5's walk = min over entrances (R5 walk to entrance + pathway time); the
entrance is the one that minimises it (user: Google's own entrance not extracted, small gain). Then predicted extra
- observed extra = R5 walk with pathways - Google's walk: the rule is whether R5 with pathways reproduces Google's walk.
Reported beside: the same without pathways (R5 as now); elevators excluded (user: most people take stairs; not
expected to matter); paths using a round placeholder time (PLACEHOLDER_VALUES_S) apart; per station and side.
Caveat: Google may itself read this feed's pathways, so a match may show shared data rather than reality.

Conclusion (run 2026-10-18): traversal_time filled on every row (3,832 / 3,838; no length column). 1,320 train
  sides on 814 scored pairs; 1,249 scored (61 no platform on Google's line and time, 10 no pathway data). R5 +
  pathways within +-60 s of Google's walk on 971/1,249 = 0.777 (Wilson 0.754-0.800): data ACCEPTED (bar 2/3).
  Overshoot 155, undershoot 123. Beside: R5 as now 0.676 (undershoot 248); elevators excluded 0.780 (no effect);
  no chosen path uses a 300 / 600 s placeholder; alighting 0.844, boarding 0.704; the 8 false-20 miss pairs
  with a train side 8/8. Pathway time is small at most stations (predicted extra median +12 s) and large at
  the deep Metro Tunnel stations (Town Hall +308 s vs Google +392, State Library +143 vs +174).

Inputs (read only): diagnostic_data/transit_hard_miss_range_*_results.csv (newest); the Google raw answers in
outputs/transit_validation/; the cleaned feeds and OSM extract as transit_band_metric. Self-contained (D1). No API.
Saved data (reused if present, with its date): the sides table (extract) and the R5 walks (route).
Usage: `python transit_pathway_check.py extract`, `... route`, then `... report`.
"""
import datetime
import heapq
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
CLEANED_DIRS = {"20261009": PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned",
                "20261016": DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016"}
WALK_NETWORK_RELEASE = "20261009"     # walk-only routing: the street network is the same in both releases
NAME = "transit_pathway_check"
RANGE_NAME = "transit_hard_miss_range"
MISS_MODEL = "no-wait plain (reported)"
FALSE_20_TEST = "false 20"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
RAW_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl",
             "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.raw.jsonl",
             "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.raw.jsonl"}

R5_MAX_MEMORY = "7G"
WINDOW_DATE = datetime.date(2026, 10, 21)
WALK_SPEED_KMH = 4.16
MATCH_TOLERANCE_S = 60                # user: +-1 min either way
ACCEPT_SHARE = 2 / 3                  # user: half was too generous
MATCH_RADIUS_M = 150
TIME_TOLERANCE_MIN = 3
PLACEHOLDER_VALUES_S = {300, 600}     # round traversal times common in the feed (600 s on 155 rows)
ELEVATOR_MODE = 5
ENTRANCE_TYPE = "2"
HEAVY_RAIL = "HEAVY_RAIL"
WILSON_Z = 1.96
EARTH_RADIUS_M = 6_371_008.8
SECONDS_PER_MIN = 60
MIN_PER_HOUR = 60
MIN_PER_DAY = 1440
GTFS_ENCODING = "utf-8-sig"
LOCAL_TZ = "Australia/Melbourne"
WEEKDAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EXCEPTION_ADDED, EXCEPTION_REMOVED = 1, 2


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def wilson(successes, n):
    if n == 0:
        return float("nan"), float("nan")
    share = successes / n
    centre = (share + WILSON_Z ** 2 / (2 * n)) / (1 + WILSON_Z ** 2 / n)
    half = WILSON_Z * np.sqrt(share * (1 - share) / n + WILSON_Z ** 2 / (4 * n ** 2)) / (1 + WILSON_Z ** 2 / n)
    return centre - half, centre + half


def seconds(step):
    return float(step.get("staticDuration", "0s").rstrip("s"))


def google_sides(results_df):
    """Per scored pair, the boarding and alighting train stops of Google's default and the walk on that side."""
    rows = []
    for set_name, path in RAW_PATHS.items():
        set_df = results_df[results_df.set_name == set_name].set_index("draw_no")
        with open(path, encoding="utf-8") as file:
            for line in file:
                record = json.loads(line)
                if record["draw_no"] not in set_df.index:
                    continue
                pair = set_df.loc[record["draw_no"]]
                steps = record["resp"]["routes"][int(pair.default_ix)]["legs"][0]["steps"]
                transit_ix = [i for i, step in enumerate(steps) if step.get("travelMode") == "TRANSIT"]
                if not transit_ix:
                    continue
                for side, ix, walk_steps, stop_key, time_key, end in [
                        ("board", transit_ix[0], steps[:transit_ix[0]], "departureStop", "departureTime", "origin"),
                        ("alight", transit_ix[-1], steps[transit_ix[-1] + 1:], "arrivalStop", "arrivalTime", "dest")]:
                    details = steps[ix]["transitDetails"]
                    transit_line = details.get("transitLine", {})
                    if transit_line.get("vehicle", {}).get("type", "") != HEAVY_RAIL:
                        continue
                    stop = details["stopDetails"][stop_key]
                    clock = pd.Timestamp(details["stopDetails"][time_key]).tz_convert(LOCAL_TZ)
                    rows.append({"set_name": set_name, "draw_no": record["draw_no"], "release": str(int(pair.release)),
                                 "side": side, "end_lat": pair[f"{end}_lat"], "end_lon": pair[f"{end}_lon"],
                                 "stop_name": stop.get("name", ""), "stop_lat": stop["location"]["latLng"]["latitude"],
                                 "stop_lon": stop["location"]["latLng"]["longitude"],
                                 "line": transit_line.get("nameShort") or transit_line.get("name", ""),
                                 "clock_min": clock.hour * MIN_PER_HOUR + clock.minute + clock.second / SECONDS_PER_MIN,
                                 "google_walk_m": sum(step.get("distanceMeters", 0) for step in walk_steps),
                                 "google_walk_s": sum(seconds(step) for step in walk_steps)})
    return pd.DataFrame(rows)


def active_services(gtfs_zip):
    date_int = int(f"{WINDOW_DATE:%Y%m%d}")
    calendar_df = pd.read_csv(gtfs_zip.open("calendar.txt"), dtype={"service_id": str}, encoding=GTFS_ENCODING)
    services = set(calendar_df.service_id[(calendar_df[WEEKDAY_COLUMNS[WINDOW_DATE.weekday()]] == 1)
                                          & (calendar_df.start_date <= date_int) & (calendar_df.end_date >= date_int)])
    if "calendar_dates.txt" in gtfs_zip.namelist():
        dates_df = pd.read_csv(gtfs_zip.open("calendar_dates.txt"), dtype={"service_id": str}, encoding=GTFS_ENCODING)
        dates_df = dates_df[dates_df.date == date_int]
        services |= set(dates_df.service_id[dates_df.exception_type == EXCEPTION_ADDED])
        services -= set(dates_df.service_id[dates_df.exception_type == EXCEPTION_REMOVED])
    return services


def clock_to_min(series):
    parts = series.str.split(":", expand=True).astype(int)
    return parts[0] * MIN_PER_HOUR + parts[1] + parts[2] / SECONDS_PER_MIN


def train_tables(release):
    """The release's train stops, pathways and its WINDOW_DATE stop times (with route names) at platforms."""
    with zipfile.ZipFile(CLEANED_DIRS[release] / f"{TRAIN_FEED}.zip") as gtfs_zip:
        stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype=str, encoding=GTFS_ENCODING)
        pathways_df = pd.read_csv(gtfs_zip.open("pathways.txt"), dtype={"from_stop_id": str, "to_stop_id": str},
                                  encoding=GTFS_ENCODING)
        services = active_services(gtfs_zip)
        trips_df = pd.read_csv(gtfs_zip.open("trips.txt"), dtype=str, usecols=["trip_id", "route_id", "service_id"],
                               encoding=GTFS_ENCODING)
        trips_df = trips_df[trips_df.service_id.isin(services)]
        routes_df = pd.read_csv(gtfs_zip.open("routes.txt"), dtype=str, encoding=GTFS_ENCODING,
                                usecols=["route_id", "route_short_name", "route_long_name"])
        times_df = pd.read_csv(gtfs_zip.open("stop_times.txt"), dtype=str, encoding=GTFS_ENCODING,
                               usecols=["trip_id", "arrival_time", "departure_time", "stop_id"])
    stops_df["stop_lat"] = stops_df.stop_lat.astype(float)
    stops_df["stop_lon"] = stops_df.stop_lon.astype(float)
    times_df = times_df.merge(trips_df, on="trip_id").merge(routes_df, on="route_id")
    times_df["dep_min"] = clock_to_min(times_df.departure_time)
    times_df["arr_min"] = clock_to_min(times_df.arrival_time)
    return stops_df, pathways_df, times_df


def pathway_times(pathways_df, platform_id, is_to_platform, skip_mode=None):
    """Shortest traversal_time from each node to the platform (or from it), with whether it uses a placeholder time."""
    edges = {}
    for row in pathways_df.itertuples():
        if row.pathway_mode == skip_mode:
            continue
        pairs = [(row.from_stop_id, row.to_stop_id)] + ([(row.to_stop_id, row.from_stop_id)] if row.is_bidirectional else [])
        for start, end in pairs:
            if is_to_platform:
                start, end = end, start       # search backwards from the platform
            edges.setdefault(start, []).append((end, row.traversal_time))
    best = {platform_id: (0, False)}
    queue = [(0, platform_id, False)]
    while queue:
        cost, node, has_placeholder = heapq.heappop(queue)
        if cost > best[node][0]:
            continue
        for neighbour, time_s in edges.get(node, []):
            candidate = cost + time_s
            if neighbour not in best or candidate < best[neighbour][0]:
                best[neighbour] = (candidate, has_placeholder or time_s in PLACEHOLDER_VALUES_S)
                heapq.heappush(queue, (candidate, neighbour, best[neighbour][1]))
    return best


def extract():
    """Sides table: Google's train side, matched feed platform, and each reachable entrance's pathway time."""
    results_df = pd.read_csv(newest(f"{RANGE_NAME}_*_results.csv"))
    results_df = results_df[results_df.is_scored]
    sides_df = google_sides(results_df)
    print(f"{len(sides_df)} train sides on {sides_df[['set_name', 'draw_no']].drop_duplicates().shape[0]} scored pairs")
    rows = []
    for release, release_df in sides_df.groupby("release"):
        stops_df, pathways_df, times_df = train_tables(release)
        print(f"release {release}: pathways {len(pathways_df)} rows; traversal_time filled "
              f"{int(pathways_df.traversal_time.notna().sum())}; length column {'length' in pathways_df.columns}")
        platforms_df = stops_df[stops_df.location_type.fillna("0").isin(["0", ""])]
        has_pathway = set(pathways_df.from_stop_id) | set(pathways_df.to_stop_id)
        entrances_df = stops_df[stops_df.location_type == ENTRANCE_TYPE].set_index("stop_id")
        cache = {}
        for side in release_df.itertuples():
            row = side._asdict()
            row.pop("Index")
            distance_m = haversine_m(side.stop_lat, side.stop_lon, platforms_df.stop_lat.to_numpy(), platforms_df.stop_lon.to_numpy())
            near_df = platforms_df[distance_m <= MATCH_RADIUS_M].assign(distance_m=distance_m[distance_m <= MATCH_RADIUS_M])
            candidates = times_df[times_df.stop_id.isin(near_df.stop_id)].merge(near_df[["stop_id", "distance_m"]], on="stop_id")
            is_line = (candidates.route_short_name.fillna("").str.strip() == str(side.line).strip()) | \
                candidates.route_long_name.fillna("").str.contains(str(side.line), regex=False)
            time_column = "dep_min" if side.side == "board" else "arr_min"
            gap_min = (candidates[time_column] - side.clock_min).abs()
            gap_min = np.minimum(gap_min, (candidates[time_column] - side.clock_min - MIN_PER_DAY).abs())   # 24:03 = 00:03
            is_time = gap_min <= TIME_TOLERANCE_MIN
            match_df = candidates[is_line & is_time].sort_values("distance_m")
            row.update({"n_near_platforms": len(near_df), "platform_id": None})
            if match_df.empty:
                rows.append({**row, "status": "no platform match"})
                continue
            platform = platforms_df.set_index("stop_id").loc[match_df.stop_id.iloc[0]]
            row.update({"platform_id": match_df.stop_id.iloc[0], "platform_lat": platform.stop_lat,
                        "platform_lon": platform.stop_lon, "station_id": platform.parent_station,
                        "platform_m": round(match_df.distance_m.iloc[0])})
            if row["platform_id"] not in has_pathway:
                rows.append({**row, "status": "no pathway data"})
                continue
            key = (row["platform_id"], side.side == "board")
            if key not in cache:
                cache[key] = (pathway_times(pathways_df, *key), pathway_times(pathways_df, *key, skip_mode=ELEVATOR_MODE))
            all_modes, no_elevator = cache[key]
            reached = [node for node in all_modes if node in entrances_df.index]
            if not reached:
                rows.append({**row, "status": "no entrance reached"})
                continue
            for entrance_id in reached:
                entrance = entrances_df.loc[entrance_id]
                rows.append({**row, "status": "ok", "entrance_id": entrance_id, "entrance_lat": float(entrance.stop_lat),
                             "entrance_lon": float(entrance.stop_lon), "path_s": all_modes[entrance_id][0],
                             "has_placeholder": all_modes[entrance_id][1],
                             "path_no_elevator_s": no_elevator.get(entrance_id, (np.nan, False))[0]})
    out_df = pd.DataFrame(rows)
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_sides.csv"
    out_df.to_csv(path, index=False)
    side_df = out_df.drop_duplicates(["set_name", "draw_no", "side"])
    print(side_df.status.value_counts().to_string())
    print(f"saved {path.name}")


def route():
    """R5 walk-only times (s) between each side's end and its platform point and each entrance point."""
    sides_path = newest(f"{NAME}_*_sides.csv")
    print(f"sides table {sides_path.name}")
    sides_df = pd.read_csv(sides_path, dtype={"platform_id": str, "entrance_id": str})
    sides_df = sides_df[sides_df.status == "ok"]
    targets = pd.concat([
        sides_df[["side", "end_lat", "end_lon", "platform_lat", "platform_lon"]].drop_duplicates()
        .rename(columns={"platform_lat": "point_lat", "platform_lon": "point_lon"}),
        sides_df[["side", "end_lat", "end_lon", "entrance_lat", "entrance_lon"]].drop_duplicates()
        .rename(columns={"entrance_lat": "point_lat", "entrance_lon": "point_lon"})]).drop_duplicates().reset_index(drop=True)
    print(f"{len(targets)} walk pairs", flush=True)
    sys.argv += ["--max-memory", R5_MAX_MEMORY]
    import geopandas as gpd
    from r5py import DetailedItineraries, TransportMode, TransportNetwork

    network = TransportNetwork(PBF_PATH, [CLEANED_DIRS[WALK_NETWORK_RELEASE] / f"{name}.zip" for name in FEED_NAMES])
    is_board = targets.side == "board"
    from_lat = np.where(is_board, targets.end_lat, targets.point_lat)
    from_lon = np.where(is_board, targets.end_lon, targets.point_lon)
    to_lat = np.where(is_board, targets.point_lat, targets.end_lat)
    to_lon = np.where(is_board, targets.point_lon, targets.end_lon)
    origins = gpd.GeoDataFrame({"id": targets.index}, crs="EPSG:4326", geometry=gpd.points_from_xy(from_lon, from_lat))
    destinations = gpd.GeoDataFrame({"id": targets.index}, crs="EPSG:4326", geometry=gpd.points_from_xy(to_lon, to_lat))
    departure = datetime.datetime.combine(WINDOW_DATE, datetime.time(12))   # walk-only: time does not matter
    di_df = pd.DataFrame(DetailedItineraries(network, origins=origins, destinations=destinations, departure=departure,
                                             transport_modes=[TransportMode.WALK], speed_walking=WALK_SPEED_KMH))
    walks_df = di_df.groupby("from_id").agg(r5_m=("distance", "sum"), r5_s=("travel_time", "sum")).reset_index()
    walks_df["r5_s"] = walks_df.r5_s.dt.total_seconds()
    out_df = targets.join(walks_df.set_index("from_id"))
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_walks.csv"
    out_df.to_csv(path, index=False)
    print(f"saved {path.name}; no walk found on {int(out_df.r5_s.isna().sum())}")


def share_line(label, is_match, diff_s):
    n, k = len(is_match), int(is_match.sum())
    low, high = wilson(k, n)
    return (f"{label}: match {k}/{n} = {k / n if n else float('nan'):.3f} (Wilson 95% {low:.3f}-{high:.3f}); "
            f"overshoot {int((diff_s > MATCH_TOLERANCE_S).sum())}, undershoot {int((diff_s < -MATCH_TOLERANCE_S).sum())}; "
            f"diff median {diff_s.median():+.0f} s")


def report():
    run_date = f"{datetime.date.today():%Y%m%d}"
    sides_path, walks_path = newest(f"{NAME}_*_sides.csv"), newest(f"{NAME}_*_walks.csv")
    sides_df = pd.read_csv(sides_path, dtype={"platform_id": str, "entrance_id": str})
    walks_df = pd.read_csv(walks_path)
    keys = ["side", "end_lat", "end_lon"]
    platform_walks = walks_df.rename(columns={"point_lat": "platform_lat", "point_lon": "platform_lon", "r5_s": "r5_platform_s"})
    entrance_walks = walks_df.rename(columns={"point_lat": "entrance_lat", "point_lon": "entrance_lon", "r5_s": "r5_entrance_s"})
    ok_df = sides_df[sides_df.status == "ok"].merge(
        platform_walks[keys + ["platform_lat", "platform_lon", "r5_platform_s"]], on=keys + ["platform_lat", "platform_lon"]).merge(
        entrance_walks[keys + ["entrance_lat", "entrance_lon", "r5_entrance_s"]], on=keys + ["entrance_lat", "entrance_lon"])
    ok_df["with_path_s"] = ok_df.r5_entrance_s + ok_df.path_s
    ok_df["with_path_no_elevator_s"] = ok_df.r5_entrance_s + ok_df.path_no_elevator_s
    side_keys = ["set_name", "draw_no", "side"]
    best_df = ok_df.loc[ok_df.groupby(side_keys).with_path_s.idxmin()].copy()
    best_df["with_path_no_elevator_s"] = ok_df.groupby(side_keys).with_path_no_elevator_s.min().reindex(
        pd.MultiIndex.from_frame(best_df[side_keys])).to_numpy()
    best_df = best_df.dropna(subset=["r5_platform_s", "with_path_s"])
    best_df["predicted_extra_s"] = best_df.with_path_s - best_df.r5_platform_s
    best_df["observed_extra_s"] = best_df.google_walk_s - best_df.r5_platform_s
    best_df["diff_s"] = best_df.predicted_extra_s - best_df.observed_extra_s
    best_df["is_match"] = best_df.diff_s.abs() <= MATCH_TOLERANCE_S
    best_df["diff_no_path_s"] = best_df.r5_platform_s - best_df.google_walk_s
    best_df["diff_no_elevator_s"] = best_df.with_path_no_elevator_s - best_df.google_walk_s
    misses_df = pd.read_csv(newest(f"{RANGE_NAME}_*_misses.csv"))
    false20 = misses_df[(misses_df.model == MISS_MODEL) & (misses_df.test == FALSE_20_TEST)][["set_name", "draw_no"]]
    best_df["is_false20_miss"] = pd.MultiIndex.from_frame(best_df[["set_name", "draw_no"]]).isin(pd.MultiIndex.from_frame(false20))

    status_df = sides_df.drop_duplicates(side_keys)
    is_match = best_df.is_match
    share = is_match.mean()
    lines = [f"{NAME} {run_date}: sides {sides_path.name}, walks {walks_path.name} (saved data reused)",
             f"train sides on scored pairs {len(status_df)}: " + ", ".join(f"{k} {v}" for k, v in status_df.status.value_counts().items())
             + f"; R5 walk found on {len(best_df)}",
             share_line("RULE, R5 + pathways vs Google's walk", is_match, best_df.diff_s),
             f"VERDICT: data {'ACCEPTED' if share >= ACCEPT_SHARE else 'NOT ACCEPTED'} (share {share:.3f} vs bar {ACCEPT_SHARE:.3f})",
             share_line("beside, R5 as now (no pathways)", best_df.diff_no_path_s.abs() <= MATCH_TOLERANCE_S, best_df.diff_no_path_s),
             share_line("beside, elevators excluded", best_df.diff_no_elevator_s.abs() <= MATCH_TOLERANCE_S, best_df.diff_no_elevator_s),
             f"predicted extra median {best_df.predicted_extra_s.median():+.0f} s, observed extra median {best_df.observed_extra_s.median():+.0f} s"]
    for label, group_col in [("side", "side"), ("placeholder time on the chosen path", "has_placeholder"),
                             ("false-20 miss pair", "is_false20_miss")]:
        for value, group_df in best_df.groupby(group_col):
            lines.append(share_line(f"  {label} = {value}", group_df.is_match, group_df.diff_s))
    station_df = best_df.groupby("stop_name").agg(n=("is_match", "size"), match=("is_match", "mean"),
                                                  diff_median_s=("diff_s", "median"),
                                                  observed_median_s=("observed_extra_s", "median"),
                                                  predicted_median_s=("predicted_extra_s", "median")).sort_values("n", ascending=False)
    with pd.option_context("display.width", 200, "display.precision", 2):
        lines.append("per station (n >= 5):\n" + station_df[station_df.n >= 5].to_string())
    summary = "\n".join(lines)
    print(summary)
    best_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_table.csv", index=False)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")


if __name__ == "__main__":
    {"extract": extract, "route": route, "report": report}[sys.argv[1]]()
