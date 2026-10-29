"""TRN-13 scaler: does Google stretch tram and bus ride times beyond the timetable in dense areas?

Claim under test (concepts/transit.md TRN-13 "Open (user, 2026-10-19)"; DESIGN.md Q23): the high service-density
third leans over at 20 min (R5 reaches more than Google) partly because Google times tram and bus rides on
historical road traffic (all requests point to the future, so live data is out of scope; user, 2026-10-19), which
the timetable R5 routes on does not carry. If so, a stretch of the feed's stop times before routing, applied to
tram and bus hops in dense areas (a yes / no flag at Valhalla's top density level 15, as the drive model 2tier,
DRV-1), would remove the lean; trains run on their own track and are the control. Where the pipeline would rely
on it: a timetable stretch before the transit bands (SCR-1, RCH-1), not built. Alternative the check can't rule
out but can expose: Google rides the timetable and the lean is R5 choosing faster trip combinations (path match
is weak, TRN-12).

Method: every transit ride in every Google route (default and alternatives) of the training half (main fetch,
release 20261009) and the second batch (release 20261016) is matched to one timetable trip of the pair's release:
same mode's feed; a board stop and a later alight stop within STOP_MATCH_M of Google's; the trip's departure at
the board stop within MATCH_EARLIER_MIN before to MATCH_LATER_MIN after Google's (a stretched trip may be late
upstream); the same line name preferred; then the smallest departure offset. Unmatched and ambiguous rides
(tied candidates with different ride times) are counted and left out. Duplicate rides (same trip, board, alight)
count once. Per ride: Google's ride seconds (alight - board time) and the timetable's, split by hop into dense
seconds (hop starts at a stop of density level 15) and other seconds (dwell at a stop goes with the hop leaving it).
Fit per mode, through the origin: google_s = m_dense x dense_s + m_other x other_s (least squares); 95% interval
by bootstrap over pairs.

Rule (Claude's, not user-approved; set before any result of this script was computed):
  MATERIAL = 0.02 (a 2% stretch, ~20 s on a 15-min ride, below which a scaler isn't worth building).
  Stretch present for a mode if its m_dense interval lies above 1 + MATERIAL and above its m_other (interval of
  m_dense - m_other above 0). Train control holds if train's m_dense and m_other intervals both lie below
  1 + MATERIAL.
  SUPPORTED: stretch present for tram or bus, and the train control holds. KILLED: the m_dense interval of tram
  and of bus both lie below 1 + MATERIAL (Google rides the timetable in dense areas). Otherwise UNCLEAR.
  Reported, no rule: share of rides where Google's ride time equals the timetable's to the minute, and the
  departure offset, per mode and dense class.

Conclusion (run 2026-10-19; Claude's rule): KILLED. Google rides the timetable. 26,347 rides read; matched train
  0.926, tram 1.000, bus 0.988 (nearly all on the same line, 5 ambiguous); 24,951 used. Google departs at the
  timetable's minute on >= 0.987 of rides in every mode and class, so no upstream delay either. Ride time equals the
  timetable's to the minute on 0.88-0.94 of tram and bus rides (train >= 0.99); mean differences +4 to +9 s, medians
  0. Fitted factors: tram m_dense 1.0047 [1.0038, 1.0058], m_other 1.0055 (dense no higher than other); bus m_dense
  1.0074 [1.0057, 1.0092], m_other 1.0035; train 1.003 / 1.001. All far below 1 + MATERIAL. A dense-area stretch
  of about 0.5% (~5 s on a 15-min ride) can't explain the high-third lean, so the lean comes from R5's choice of
  trips and transfers, not from slower rides on Google's side.

Inputs (read only): raw Google answers and the split in outputs/transit_validation/<subject>/; cleaned feeds
(outputs/pt_graph/gtfs_cleaned/ for 20261009, diagnostic_data/transit_band_metric_gtfs_cleaned_20261016/); the
road density raster outputs/road_density/road_density_raster.npz. The test half is not read. Self-contained
(CLAUDE.md D1). No API calls, no R5. Saved data (Google's rides) is reused if it exists and says so.
Usage: `python transit_invehicle_stretch.py`. Results carry the run date; a same-day rerun replaces them.
"""
import datetime
import json
import zipfile
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pyproj import Transformer
from sklearn.neighbors import BallTree

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_invehicle_stretch"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
RAW_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl",
             "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.raw.jsonl"}
CLEANED_DIRS = {"20261009": PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned",
                "20261016": DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016"}
DENSITY_RASTER_PATH = PROJECT_ROOT / "outputs" / "road_density" / "road_density_raster.npz"
RIDES_SUFFIX = "_google_rides.csv"              # saved data: Google's rides

# --- values copied from config.py and the record ---------------------------------------------------
FEED_BY_VEHICLE = {"HEAVY_RAIL": "ptv_metro_train", "TRAM": "ptv_tram", "BUS": "ptv_metro_bus"}
MODE_BY_FEED = {"ptv_metro_train": "train", "ptv_tram": "tram", "ptv_metro_bus": "bus"}
TRAIN_HALF = "train"
LOCAL_TZ = ZoneInfo("Australia/Melbourne")
GTFS_ENCODING = "utf-8-sig"
WEEKDAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EXCEPTION_ADDED, EXCEPTION_REMOVED = 1, 2
EARTH_RADIUS_M = 6_371_008.8
GEOGRAPHIC_CRS = "EPSG:4326"
DENSITY_LEVEL_SCALE = 0.7                       # config.ROAD_DENSITY_LEVEL_SCALE
HALF_UP = 0.5                                   # functions/density_levels.HALF_UP
MAX_LEVEL = 15                                  # config.ROAD_DENSITY_MAX_LEVEL; dense = this level (2tier, DRV-1)
CELL_M = 100                                    # config.ROAD_DENSITY_CELL_M
TRAIN_LINE_SUFFIX = " line"
SECONDS_PER_MIN = 60
MIN_PER_HOUR = 60
MIN_PER_DAY = 1440

# --- test (Claude) ---------------------------------------------------------------------------------
STOP_MATCH_M = 200                              # platforms of one station sit apart; line and time also match
MATCH_EARLIER_MIN = 10                          # timetable departure up to this much before Google's ...
MATCH_LATER_MIN = 2                             # ... or this much after
MATERIAL = 0.02
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261019
INTERVAL_LOW_Q, INTERVAL_HIGH_Q = 0.025, 0.975
MODES = ["train", "tram", "bus"]
DENSE_CLASSES = [("none dense", 0.0, 0.0), ("mixed", 1e-9, 1 - 1e-9), ("all dense", 1.0, 1.0)]


def newest(suffix):
    files = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*{suffix}"))
    return files[-1] if files else None


def norm_line(name):
    name = str(name).strip().lower()
    return name.removesuffix(TRAIN_LINE_SUFFIX)


# === saved data: Google's rides ====================================================================
def extract_google_rides(out_path):
    split_df = pd.read_csv(SPLIT_PATH)
    train_draws = set(split_df.draw_no[split_df.half == TRAIN_HALF])
    rows = []
    for set_name, raw_path in RAW_PATHS.items():
        with open(raw_path, encoding="utf-8") as raw_file:
            for line in raw_file:
                answer = json.loads(line)
                if set_name == "train" and answer["draw_no"] not in train_draws:
                    continue                    # test and smoke-test halves never read
                for route_ix, route in enumerate(answer["resp"].get("routes", [])):
                    for leg in route.get("legs", []):
                        for step in leg.get("steps", []):
                            details = step.get("transitDetails")
                            if details is None:
                                continue
                            stops, transit_line = details["stopDetails"], details.get("transitLine", {})
                            board, alight = stops["departureStop"], stops["arrivalStop"]
                            rows.append({
                                "set_name": set_name, "draw_no": answer["draw_no"],
                                "release": answer["window_release"], "route_ix": route_ix,
                                "line": transit_line.get("nameShort") or transit_line.get("name", ""),
                                "vehicle": transit_line.get("vehicle", {}).get("type", ""),
                                "stop_count": details.get("stopCount", np.nan),
                                "board_lat": board["location"]["latLng"]["latitude"],
                                "board_lon": board["location"]["latLng"]["longitude"],
                                "alight_lat": alight["location"]["latLng"]["latitude"],
                                "alight_lon": alight["location"]["latLng"]["longitude"],
                                "board_time": stops.get("departureTime", ""),
                                "alight_time": stops.get("arrivalTime", "")})
    pd.DataFrame(rows).to_csv(out_path, index=False)


# === timetable =====================================================================================
def active_service_ids(gtfs_zip, date):
    date_int = int(f"{date:%Y%m%d}")
    calendar_df = pd.read_csv(gtfs_zip.open("calendar.txt"), dtype={"service_id": str}, encoding=GTFS_ENCODING)
    is_active = ((calendar_df[WEEKDAY_COLUMNS[date.weekday()]] == 1) & (calendar_df.start_date <= date_int)
                 & (calendar_df.end_date >= date_int))
    service_ids = set(calendar_df.service_id[is_active])
    if "calendar_dates.txt" in gtfs_zip.namelist():
        dates_df = pd.read_csv(gtfs_zip.open("calendar_dates.txt"), dtype={"service_id": str}, encoding=GTFS_ENCODING)
        dates_df = dates_df[dates_df.date == date_int]
        service_ids |= set(dates_df.service_id[dates_df.exception_type == EXCEPTION_ADDED])
        service_ids -= set(dates_df.service_id[dates_df.exception_type == EXCEPTION_REMOVED])
    return service_ids


def minutes_of(time_text):
    parts = time_text.str.split(":", expand=True).astype(int)
    return parts[0] * MIN_PER_HOUR + parts[1] + parts[2] / SECONDS_PER_MIN


def stop_levels(stops_df):
    """Valhalla density level (0-15) at each stop; outside the raster -> 0 (as functions/density_levels.node_levels)."""
    with np.load(DENSITY_RASTER_PATH) as raster:
        density = raster["density"]
        x0, y0, crs = float(raster["x0"]), float(raster["y0"]), str(raster["crs"])
        assert int(raster["cell_m"]) == CELL_M
    x, y = Transformer.from_crs(GEOGRAPHIC_CRS, crs, always_xy=True).transform(
        stops_df.stop_lon.to_numpy(), stops_df.stop_lat.to_numpy())
    ix = np.floor((np.asarray(x) - x0) / CELL_M).astype(int)
    iy = np.floor((np.asarray(y) - y0) / CELL_M).astype(int)
    is_inside = (ix >= 0) & (ix < density.shape[0]) & (iy >= 0) & (iy < density.shape[1])
    sampled = np.full(len(stops_df), np.nan)
    sampled[is_inside] = density[ix[is_inside], iy[is_inside]]
    level = np.minimum(np.floor(sampled * DENSITY_LEVEL_SCALE + HALF_UP), MAX_LEVEL)
    return np.where(np.isfinite(level), level, 0.0)


def match_feed(rides_df, release, feed_name):
    """Match one feed's rides (one release) to timetable trips; one result row per ride."""
    with zipfile.ZipFile(CLEANED_DIRS[release] / f"{feed_name}.zip") as gtfs_zip:
        stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype={"stop_id": str}, encoding=GTFS_ENCODING)
        routes_df = pd.read_csv(gtfs_zip.open("routes.txt"), dtype={"route_id": str, "route_short_name": str},
                                encoding=GTFS_ENCODING)
        trips_df = pd.read_csv(gtfs_zip.open("trips.txt"), dtype={"route_id": str, "service_id": str, "trip_id": str},
                               encoding=GTFS_ENCODING)
        stop_times_df = pd.read_csv(gtfs_zip.open("stop_times.txt"), dtype={"trip_id": str, "stop_id": str},
                                    usecols=["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
                                    encoding=GTFS_ENCODING)
        service_dates = sorted({date for ride_date in rides_df.local_date
                                for date in (ride_date, ride_date - datetime.timedelta(days=1))})
        services = {date: active_service_ids(gtfs_zip, date) for date in service_dates}

    stops_df["level"] = stop_levels(stops_df)
    level_by_stop = dict(zip(stops_df.stop_id, stops_df.level))
    trips_df = trips_df.merge(routes_df[["route_id", "route_short_name", "route_long_name"]], on="route_id", how="left")
    line_by_trip = dict(zip(trips_df.trip_id, trips_df.route_short_name.fillna(trips_df.route_long_name).map(norm_line)))
    service_by_trip = dict(zip(trips_df.trip_id, trips_df.service_id))

    tree = BallTree(np.radians(stops_df[["stop_lat", "stop_lon"]].to_numpy()), metric="haversine")
    radius = STOP_MATCH_M / EARTH_RADIUS_M
    board_near = tree.query_radius(np.radians(rides_df[["board_lat", "board_lon"]].to_numpy()), r=radius)
    alight_near = tree.query_radius(np.radians(rides_df[["alight_lat", "alight_lon"]].to_numpy()), r=radius)
    stop_ids = stops_df.stop_id.to_numpy()

    needed = set(stop_ids[np.concatenate(list(board_near) + [np.array([], dtype=int)])])
    board_times_df = stop_times_df[stop_times_df.stop_id.isin(needed)].copy()
    board_times_df["dep_min"] = minutes_of(board_times_df.departure_time)
    by_stop = {stop: group for stop, group in board_times_df.groupby("stop_id")}

    candidates = []                             # (ride row index, trip, board seq, dep offset min)
    for row_ix, (ride, near_ix) in enumerate(zip(rides_df.itertuples(), board_near)):
        for service_date, day_shift in ((ride.local_date, 0), (ride.local_date - datetime.timedelta(days=1), MIN_PER_DAY)):
            google_min = ride.board_min + day_shift
            active = services[service_date]
            for stop in stop_ids[near_ix]:
                group = by_stop.get(stop)
                if group is None:
                    continue
                offset = google_min - group.dep_min.to_numpy()
                keep = (offset <= MATCH_EARLIER_MIN) & (offset >= -MATCH_LATER_MIN)
                for trip, seq, off in zip(group.trip_id.to_numpy()[keep], group.stop_sequence.to_numpy()[keep], offset[keep]):
                    if service_by_trip.get(trip) in active:
                        candidates.append((row_ix, trip, seq, off))
    if not candidates:
        return pd.DataFrame()
    cand_df = pd.DataFrame(candidates, columns=["row_ix", "trip_id", "board_seq", "dep_offset_min"])

    trip_times_df = stop_times_df[stop_times_df.trip_id.isin(set(cand_df.trip_id))].copy()
    trip_times_df["arr_min"] = minutes_of(trip_times_df.arrival_time)
    trip_times_df["dep_min"] = minutes_of(trip_times_df.departure_time)
    trip_times_df = trip_times_df.sort_values(["trip_id", "stop_sequence"])
    by_trip = {trip: group for trip, group in trip_times_df.groupby("trip_id")}

    results = []
    for row_ix, group in cand_df.groupby("row_ix"):
        ride = rides_df.iloc[row_ix]
        alight_stops = set(stop_ids[alight_near[row_ix]])
        options = []
        for cand in group.itertuples():
            trip_df = by_trip[cand.trip_id]
            seq = trip_df.stop_sequence.to_numpy()
            board_pos = int(np.flatnonzero(seq == cand.board_seq)[0])
            later = trip_df.iloc[board_pos + 1:]
            hit = np.flatnonzero(later.stop_id.isin(alight_stops).to_numpy())
            if len(hit) == 0:
                continue
            leg_df = trip_df.iloc[board_pos: board_pos + 1 + int(hit[0]) + 1]
            dep = leg_df.dep_min.to_numpy()
            arr = leg_df.arr_min.to_numpy()
            hop_s = (arr[1:] - dep[:-1]) * SECONDS_PER_MIN + np.r_[0.0, (dep[1:-1] - arr[1:-1])] * SECONDS_PER_MIN
            is_dense = np.array([level_by_stop.get(stop, 0.0) >= MAX_LEVEL for stop in leg_df.stop_id.to_numpy()[:-1]])
            options.append({"trip_id": cand.trip_id, "board_seq": cand.board_seq,
                            "alight_seq": int(leg_df.stop_sequence.iloc[-1]), "n_hops": len(leg_df) - 1,
                            "dep_offset_min": cand.dep_offset_min,
                            "is_line_match": line_by_trip.get(cand.trip_id) == norm_line(ride.line),
                            "timetable_s": (arr[-1] - dep[0]) * SECONDS_PER_MIN,
                            "dense_s": float(hop_s[is_dense].sum()), "other_s": float(hop_s[~is_dense].sum())})
        if not options:
            continue
        options_df = pd.DataFrame(options)
        if options_df.is_line_match.any():
            options_df = options_df[options_df.is_line_match]
        options_df = options_df.assign(abs_offset=options_df.dep_offset_min.abs())
        best_df = options_df[options_df.abs_offset == options_df.abs_offset.min()]
        is_ambiguous = best_df.timetable_s.nunique() > 1
        best = best_df.iloc[0].to_dict()
        best.update({"row_ix": row_ix, "is_ambiguous": is_ambiguous})
        results.append(best)
    return pd.DataFrame(results)


# === fit ===========================================================================================
def fit_factors(df):
    design = df[["dense_s", "other_s"]].to_numpy()
    target = df.google_s.to_numpy()
    if np.linalg.matrix_rank(design) < 2:
        return np.nan, np.nan
    coef, *_ = np.linalg.lstsq(design, target, rcond=None)
    return coef[0], coef[1]


def bootstrap_factors(df, rng):
    pair_keys = df.set_name + ":" + df.draw_no.astype(str)
    unique_keys = pair_keys.unique()
    index_by_key = {key: np.flatnonzero((pair_keys == key).to_numpy()) for key in unique_keys}
    draws = []
    for _ in range(N_BOOTSTRAP):
        picked = rng.choice(unique_keys, size=len(unique_keys), replace=True)
        rows = np.concatenate([index_by_key[key] for key in picked])
        m_dense, m_other = fit_factors(df.iloc[rows])
        draws.append((m_dense, m_other, m_dense - m_other))
    return np.array(draws)


def interval(values):
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return np.nan, np.nan
    return np.quantile(values, INTERVAL_LOW_Q), np.quantile(values, INTERVAL_HIGH_Q)


def main():
    run_date = datetime.date.today()
    stamp = f"{run_date:%Y%m%d}"
    rides_path = newest(RIDES_SUFFIX)
    if rides_path is None:
        rides_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{stamp}{RIDES_SUFFIX}"
        extract_google_rides(rides_path)
        print(f"extracted Google's rides -> {rides_path.name}")
    else:
        print(f"reusing {rides_path.name} ({datetime.date.fromtimestamp(rides_path.stat().st_mtime)})")
    rides_df = pd.read_csv(rides_path, dtype={"release": str})
    n_raw = len(rides_df)

    board_local = pd.to_datetime(rides_df.board_time, utc=True).dt.tz_convert(LOCAL_TZ)
    alight_local = pd.to_datetime(rides_df.alight_time, utc=True).dt.tz_convert(LOCAL_TZ)
    rides_df["local_date"] = board_local.dt.date
    rides_df["board_min"] = board_local.dt.hour * MIN_PER_HOUR + board_local.dt.minute
    rides_df["google_s"] = (alight_local - board_local).dt.total_seconds()
    rides_df["feed"] = rides_df.vehicle.map(FEED_BY_VEHICLE)
    lines = [f"{NAME} {stamp}: Google ride time vs timetable, by mode and Valhalla density level {MAX_LEVEL} hops",
             f"rides read: {n_raw:,} (train half + second batch, all routes); rule: Claude's, set before the run", ""]
    out_of_feeds = rides_df.feed.isna()
    lines.append(f"rides on vehicles outside the three feeds (left out): {out_of_feeds.sum():,} "
                 f"{rides_df.vehicle[out_of_feeds].value_counts().to_dict()}")
    rides_df = rides_df[~out_of_feeds].reset_index(drop=True)

    matched = []
    for (release, feed_name), group in rides_df.groupby(["release", "feed"]):
        group = group.reset_index()
        print(f"matching {release} {feed_name}: {len(group):,} rides")
        result_df = match_feed(group, release, feed_name)
        if result_df.empty:
            continue
        result_df["source_ix"] = group["index"].to_numpy()[result_df.row_ix.to_numpy()]
        matched.append(result_df.drop(columns="row_ix"))
    match_df = pd.concat(matched, ignore_index=True)
    df = rides_df.reset_index().rename(columns={"index": "source_ix"}).merge(match_df, on="source_ix", how="left")
    df["mode"] = df.feed.map(MODE_BY_FEED)
    df["is_matched"] = df.trip_id.notna()

    lines.append("match counts per mode (rides; matched; same line; ambiguous; Google stopCount = timetable hops):")
    for mode in MODES:
        mode_df = df[df["mode"] == mode]
        hit_df = mode_df[mode_df.is_matched]
        lines.append(f"  {mode}: {len(mode_df):,}; {len(hit_df):,} ({len(hit_df) / max(len(mode_df), 1):.3f}); "
                     f"{hit_df.is_line_match.astype(bool).sum():,}; {hit_df.is_ambiguous.astype(bool).sum():,}; "
                     f"{(hit_df.stop_count == hit_df.n_hops).mean():.3f}")

    use_df = df[df.is_matched & ~df.is_ambiguous.astype(bool)].copy()
    n_before = len(use_df)
    use_df = use_df.drop_duplicates(["release", "local_date", "trip_id", "board_seq", "alight_seq"])
    lines.append(f"used: {len(use_df):,} rides after dropping ambiguous and {n_before - len(use_df):,} duplicates")
    use_df["delta_s"] = use_df.google_s - use_df.timetable_s
    use_df["dense_share"] = use_df.dense_s / use_df.timetable_s.where(use_df.timetable_s > 0)
    use_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{stamp}_rides_matched.csv", index=False)

    lines += ["", "per mode and dense class: n; Google = timetable (to the minute); mean / median delta s (Google - "
              "timetable); departure offset 0 share; mean timetable min"]
    for mode in MODES:
        for label, low, high in DENSE_CLASSES:
            cls_df = use_df[(use_df["mode"] == mode) & (use_df.dense_share >= low) & (use_df.dense_share <= high)]
            if cls_df.empty:
                lines.append(f"  {mode:5s} {label:10s}: n 0")
                continue
            lines.append(f"  {mode:5s} {label:10s}: n {len(cls_df):5,}; equal {(cls_df.delta_s == 0).mean():.3f}; "
                         f"delta {cls_df.delta_s.mean():+.1f} / {cls_df.delta_s.median():+.0f}; "
                         f"offset0 {(cls_df.dep_offset_min == 0).mean():.3f}; "
                         f"{cls_df.timetable_s.mean() / SECONDS_PER_MIN:.1f} min")

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    fits = {}
    lines += ["", f"fit google_s = m_dense x dense_s + m_other x other_s, 95% bootstrap over pairs ({N_BOOTSTRAP})"]
    for mode in MODES:
        mode_df = use_df[use_df["mode"] == mode].reset_index(drop=True)
        m_dense, m_other = fit_factors(mode_df)
        draws = bootstrap_factors(mode_df, rng)
        fits[mode] = {"m_dense": m_dense, "m_other": m_other, "dense_iv": interval(draws[:, 0]),
                      "other_iv": interval(draws[:, 1]), "diff_iv": interval(draws[:, 2]),
                      "dense_min": mode_df.dense_s.sum() / SECONDS_PER_MIN, "other_min": mode_df.other_s.sum() / SECONDS_PER_MIN}
        fit = fits[mode]
        lines.append(f"  {mode:5s}: m_dense {m_dense:.4f} [{fit['dense_iv'][0]:.4f}, {fit['dense_iv'][1]:.4f}]; "
                     f"m_other {m_other:.4f} [{fit['other_iv'][0]:.4f}, {fit['other_iv'][1]:.4f}]; "
                     f"dense - other [{fit['diff_iv'][0]:+.4f}, {fit['diff_iv'][1]:+.4f}]; "
                     f"timetable min dense {fit['dense_min']:,.0f} / other {fit['other_min']:,.0f}")

    bar = 1 + MATERIAL
    stretch = {mode: fits[mode]["dense_iv"][0] > bar and fits[mode]["diff_iv"][0] > 0 for mode in ["tram", "bus"]}
    control = fits["train"]["dense_iv"][1] < bar and fits["train"]["other_iv"][1] < bar
    no_stretch = all(fits[mode]["dense_iv"][1] < bar for mode in ["tram", "bus"])
    if (stretch["tram"] or stretch["bus"]) and control:
        verdict = "SUPPORTED"
    elif no_stretch:
        verdict = "KILLED"
    else:
        verdict = "UNCLEAR"
    lines += ["", f"stretch present (m_dense lower > {bar}, above m_other): tram {stretch['tram']}, bus {stretch['bus']}; "
              f"train control (both upper < {bar}): {control}; tram and bus m_dense upper < {bar}: {no_stretch}",
              f"VERDICT: {verdict}"]
    summary_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{stamp}_summary.txt"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
