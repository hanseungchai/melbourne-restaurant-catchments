"""Network-wide weekend coverage, per GTFS release: where does weekend transit run, compared with a weekday?

Question (concepts/reachability.md RCH-25 (2); DESIGN.md Q25): weekends differ from weekdays in where service runs,
not only how often (user), so a weekend reach estimate is supported only where weekend conditions resemble weekday
conditions the model was validated on. This map is that check, network-wide (any subject is a readout from it, user).
Where the pipeline would rely on it: the weekend decision in Q25 for bands 1-2. Report only; inclusion is the user's
call.

Method (per release, from the cleaned GTFS each release's pairs route on; free, no routing, no API):
  Days: a matched weekday (Wednesday) and the Saturday / Sunday of one week inside the release's window:
    20261009: Sat 17, Sun 18, Wed 21 Oct; 20261016: Sat 24, Sun 25, Wed 28 Oct (Melbourne Cup Day 3 Nov avoided).
  Hours: centres 11:30-21:00 every 30 min (the union of the subject's and its sibling's hours, RCH-21), windows
    +-30 min (as transit_holdout_score's origin_trips: distinct trips at stops within 700 m).
  (a) Stops: departures (stop_times rows) per stop in 11:00-21:30, weekday vs each weekend day; a stop is lost when it
      has weekday departures in those hours and none on the weekend day. Routes likewise (trips in those hours).
  (b) 500 m cells holding a populated hex (residents + workers >= 1), cell centre on a local equirectangular grid:
      per cell and centre, S = distinct trips within 700 m; weekend vs the same weekday centre (same_hour ratio) and
      vs the cell's weekday peak (07:00-19:00, every 30 min: rel, as transit_error_by_service.py); coverage loss =
      weekday S > 0 and weekend S = 0 at that centre. Population-weighted shares use the cell's residents + workers.
  (c) Similar conditions: a weekend cell-centre is covered when its rel tier x absolute third holds >= 50 scored
      weekday pairs in transit_error_by_service's tables (any hour; tiers and thirds as there).
A hex inherits its cell's values (approximation: 700 m around the cell centre, not the hex centroid). Trips after
midnight on the previous service day are not counted (no effect inside 11:00-21:30).

Conclusion (run 2026-10-22, 73rd, autonomous; facts, the reading is the user's): 521,044 populated hexes in 16,161
cells. Both releases alike except train. (a) Tram: every stop and route served on both weekend days (volume Sat 0.84,
Sun 0.76 of Wed). Bus: Sat loses 4% of stops / 15-16% of routes, Sun 10-11% / 26-27% (volume 0.64 / 0.55). Train: 11-
12% of routes (2 of 17-18) and 15-23% of stops have no weekend service 11:00-21:30 (20261009 23%, 20261016 15-17%; a
weekend line closure or replacement buses, cause not checked). (b) Population-weighted: 13.3% of persons live in
cells with no weekday trip within 700 m in these hours (no transit reach either way); of the rest, 1.3% (Sat) /
2.2% (Sun) lose all service at a given weekend centre. Same-hour weekend / weekday trips: median Sat 0.67-0.77
midday, 0.57-0.60 at 17-19 (weekday evening peak), back to 0.75-0.80 by 21:00; Sun ~0.07-0.10 lower. Relative to the
cell's weekday peak: median rel 0.50 Sat / 0.44-0.46 Sun, falling to 0.40 / 0.35 at 21:00. rel tier shares: < 0.4
Sat 17%, Sun 29%; 0.4-0.6 39-43%. (c) Of persons in served cells, 99.5% sit in a weekend tier x third with >= 50
scored weekday pairs (uncovered: rel > 1 at low service, 2.3 M person-cells). Reading (Claude's): weekend service is
thinner, not mostly elsewhere, except bus routes on Sunday and the train lines without weekend service in the
releases checked; with transit_error_by_service.py (thinness alone does not widen the error), the uncovered part is
where service runs (about 1-2% of served persons per centre, more on lines shut for works), not how often.
----

Inputs (read only): cleaned GTFS of both releases, the hex population layer, transit_error_by_service's per-pair
service table and the frozen model's scored pairs. Self-contained (CLAUDE.md D1). Usage: `python
transit_weekend_coverage.py`.
"""
import datetime
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
NAME = "transit_weekend_coverage"
ERROR_NAME = "transit_error_by_service"
SCORE_NAME = "transit_holdout_score"
SUBJECT = "-37.76870_144.97196"
FILE_TAG = f"res2021_wrk2021_ven20260925_{SUBJECT}"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"
CLEANED_DIRS = {20261009: PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned",
                20261016: DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016"}

# --- days and hours --------------------------------------------------------------------------------
RELEASE_DAYS = {20261009: {"Wed": datetime.date(2026, 10, 21), "Sat": datetime.date(2026, 10, 17),
                           "Sun": datetime.date(2026, 10, 18)},
                20261016: {"Wed": datetime.date(2026, 10, 28), "Sat": datetime.date(2026, 10, 24),
                           "Sun": datetime.date(2026, 10, 25)}}
WEEKDAY, WEEKEND_DAYS = "Wed", ["Sat", "Sun"]
MIN_PER_HOUR = 60
SECONDS_PER_MIN = 60
WEEKEND_CENTRES_MIN = np.arange(11 * MIN_PER_HOUR + 30, 21 * MIN_PER_HOUR + 1, 30)  # 11:30-21:00 every 30 min
PEAK_CENTRES_MIN = np.arange(7 * MIN_PER_HOUR, 19 * MIN_PER_HOUR + 1, 30)          # 07:00-19:00 every 30 min
HOURS_SPAN_MIN = (11 * MIN_PER_HOUR, 21 * MIN_PER_HOUR + 30)                         # stops and routes: 11:00-21:30
MAP_CENTRES_MIN = [13 * MIN_PER_HOUR, 20 * MIN_PER_HOUR]                             # figure columns

# --- service (copied from transit_holdout_score.py) --------------------------------------------------
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
FEED_MODES = {"ptv_metro_train": "train", "ptv_tram": "tram", "ptv_metro_bus": "bus"}
SERVICE_RADIUS_M = 700
SERVICE_HALF_WINDOW_MIN = 30
EARTH_RADIUS_M = 6_371_008.8
STOP_TIMES_CHUNK_ROWS = 2_000_000
GTFS_ENCODING = "utf-8-sig"
WEEKDAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EXCEPTION_ADDED, EXCEPTION_REMOVED = 1, 2

# --- cells and tiers -------------------------------------------------------------------------------
CELL_M = 500
GRID_ORIGIN_LAT, GRID_ORIGIN_LON = -37.8136, 144.9631          # Melbourne CBD; local equirectangular grid
POPULATED_MIN_PERSONS = 1.0                                    # as reachability_transit_pilot.py
REL_EDGES = [0, 0.4, 0.6, 0.8, 1.0001, np.inf]                 # as transit_error_by_service.py
REL_LABELS = ["<0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0", ">1"]
STRATUM_LOW_MAX_TRIPS = 36
STRATUM_HIGH_MIN_TRIPS = 131
COVERAGE_MIN_N = 50


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def newest(pattern):
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return saved[-1] if saved else None


# --- GTFS (copied from transit_holdout_score.py; all stops, route kept) -------------------------------
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


def release_tables(release):
    """Stops (key, lat, lon, mode) and departures (day, stop_key, trip_code, route_key, dep_min) on the release's days."""
    days = RELEASE_DAYS[release]
    stop_frames, frames = [], []
    for feed_name in FEED_NAMES:
        with zipfile.ZipFile(CLEANED_DIRS[release] / f"{feed_name}.zip") as gtfs_zip:
            stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype={"stop_id": str}, encoding=GTFS_ENCODING,
                                   usecols=["stop_id", "stop_lat", "stop_lon"])
            stop_frames.append(stops_df.assign(stop_key=feed_name + "|" + stops_df.stop_id, mode=FEED_MODES[feed_name]))
            services_by_day = {day: active_service_ids(gtfs_zip, date) for day, date in days.items()}
            trips_df = pd.read_csv(gtfs_zip.open("trips.txt"), dtype=str, usecols=["trip_id", "service_id", "route_id"],
                                   encoding=GTFS_ENCODING)
            trips_df = trips_df[trips_df.service_id.isin(set().union(*services_by_day.values()))]
            active_trips = set(trips_df.trip_id)
            kept = []
            for chunk in pd.read_csv(gtfs_zip.open("stop_times.txt"), dtype=str, encoding=GTFS_ENCODING,
                                     usecols=["trip_id", "departure_time", "stop_id"], chunksize=STOP_TIMES_CHUNK_ROWS):
                kept.append(chunk[chunk.trip_id.isin(active_trips)])
            feed_df = pd.concat(kept, ignore_index=True).merge(trips_df, on="trip_id", how="left")
            feed_df["dep_min"] = minutes_of(feed_df.departure_time)
        for day, day_service_ids in services_by_day.items():
            day_df = feed_df[feed_df.service_id.isin(day_service_ids)]
            frames.append(pd.DataFrame({"day": day, "stop_key": feed_name + "|" + day_df.stop_id,
                                        "trip_key": feed_name + "|" + day_df.trip_id,
                                        "route_key": feed_name + "|" + day_df.route_id, "dep_min": day_df.dep_min,
                                        "mode": FEED_MODES[feed_name]}))
        print(f"  {release} {feed_name}: {len(feed_df):,} stop departures on {len(days)} days", flush=True)
    departures_df = pd.concat(frames, ignore_index=True)
    departures_df["trip_code"] = pd.factorize(departures_df.trip_key)[0]
    return pd.concat(stop_frames, ignore_index=True), departures_df


# --- (a) stops and routes ----------------------------------------------------------------------------
def stop_route_tables(departures_df, release):
    span_df = departures_df[(departures_df.dep_min >= HOURS_SPAN_MIN[0]) & (departures_df.dep_min < HOURS_SPAN_MIN[1])]
    stop_counts = span_df.groupby(["stop_key", "mode", "day"]).size().unstack("day", fill_value=0)
    route_counts = span_df.groupby(["route_key", "mode", "day"]).trip_key.nunique().unstack("day", fill_value=0)
    rows = []
    for unit, counts in (("stops", stop_counts), ("routes", route_counts)):
        served = counts[counts[WEEKDAY] > 0]
        for mode, mode_df in list(served.groupby(level="mode")) + [("all", served)]:
            for day in WEEKEND_DAYS:
                rows.append({"release": release, "unit": unit, "mode": mode, "day": day, "weekday_served": len(mode_df),
                             "lost": int((mode_df[day] == 0).sum()), "lost_share": (mode_df[day] == 0).mean(),
                             "volume_ratio": mode_df[day].sum() / mode_df[WEEKDAY].sum()})
    return pd.DataFrame(rows)


# --- (b) cells -----------------------------------------------------------------------------------------
def local_xy_m(lat, lon):
    x = np.radians(np.asarray(lon) - GRID_ORIGIN_LON) * EARTH_RADIUS_M * np.cos(np.radians(GRID_ORIGIN_LAT))
    y = np.radians(np.asarray(lat) - GRID_ORIGIN_LAT) * EARTH_RADIUS_M
    return x, y


def populated_cells():
    import pyogrio
    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False,
                                    columns=["hex_id", "centroid_lat", "centroid_lon", "residents", "workers"])
    hex_df["persons"] = hex_df.residents.fillna(0) + hex_df.workers.fillna(0)
    hex_df = hex_df[hex_df.persons >= POPULATED_MIN_PERSONS]
    x, y = local_xy_m(hex_df.centroid_lat, hex_df.centroid_lon)
    hex_df["cell_i"], hex_df["cell_j"] = np.floor(x / CELL_M).astype(int), np.floor(y / CELL_M).astype(int)
    cells_df = hex_df.groupby(["cell_i", "cell_j"]).agg(hexes=("hex_id", "size"), persons=("persons", "sum")).reset_index()
    centre_x, centre_y = (cells_df.cell_i + 0.5) * CELL_M, (cells_df.cell_j + 0.5) * CELL_M
    cells_df["lat"] = GRID_ORIGIN_LAT + np.degrees(centre_y / EARTH_RADIUS_M)
    cells_df["lon"] = GRID_ORIGIN_LON + np.degrees(centre_x / (EARTH_RADIUS_M * np.cos(np.radians(GRID_ORIGIN_LAT))))
    return cells_df, len(hex_df)


def window_counts(by_stop, day, keys, centres):
    """Distinct trips departing the given stops within +-SERVICE_HALF_WINDOW_MIN of each centre (both ends inclusive)."""
    parts = [by_stop[(day, key)] for key in keys if (day, key) in by_stop]
    if not parts:
        return np.zeros(len(centres), dtype=int)
    dep = np.concatenate([p[0] for p in parts])
    trip = np.concatenate([p[1] for p in parts])
    order = np.argsort(dep, kind="stable")
    dep, trip = dep[order], trip[order]
    lows = np.searchsorted(dep, centres - SERVICE_HALF_WINDOW_MIN, side="left")
    highs = np.searchsorted(dep, centres + SERVICE_HALF_WINDOW_MIN, side="right")
    return np.array([np.unique(trip[a:b]).size for a, b in zip(lows, highs)])


def cell_table(cells_df, stops_df, departures_df, release):
    from sklearn.neighbors import BallTree
    tree = BallTree(np.radians(stops_df[["stop_lat", "stop_lon"]].to_numpy()), metric="haversine")
    near = tree.query_radius(np.radians(cells_df[["lat", "lon"]].to_numpy()), r=SERVICE_RADIUS_M / EARTH_RADIUS_M)
    by_stop = {key: (group.dep_min.to_numpy(), group.trip_code.to_numpy())
               for key, group in departures_df.groupby(["day", "stop_key"])}
    stop_keys = stops_df.stop_key.to_numpy()
    rows = []
    for i, cell in enumerate(cells_df.itertuples()):
        keys = stop_keys[near[i]]
        weekday = window_counts(by_stop, WEEKDAY, keys, np.concatenate([WEEKEND_CENTRES_MIN, PEAK_CENTRES_MIN]))
        same_hour, peak = weekday[:len(WEEKEND_CENTRES_MIN)], weekday[len(WEEKEND_CENTRES_MIN):].max()
        for day in WEEKEND_DAYS:
            weekend = window_counts(by_stop, day, keys, WEEKEND_CENTRES_MIN)
            rows += [{"release": release, "cell_i": cell.cell_i, "cell_j": cell.cell_j, "persons": cell.persons,
                      "day": day, "centre_min": int(c), "s_weekday": int(w), "s_weekend": int(s), "s_peak": int(peak)}
                     for c, w, s in zip(WEEKEND_CENTRES_MIN, same_hour, weekend)]
    table_df = pd.DataFrame(rows)
    table_df["rel"] = table_df.s_weekend / table_df.s_peak.where(table_df.s_peak > 0)
    table_df["same_hour"] = table_df.s_weekend / table_df.s_weekday.where(table_df.s_weekday > 0)
    table_df["is_lost"] = (table_df.s_weekday > 0) & (table_df.s_weekend == 0)
    table_df["rel_tier"] = pd.cut(table_df.rel, REL_EDGES, right=False, labels=REL_LABELS)
    table_df["stratum"] = np.select([table_df.s_weekend <= STRATUM_LOW_MAX_TRIPS, table_df.s_weekend >= STRATUM_HIGH_MIN_TRIPS],
                                    ["low", "high"], "mid")
    return table_df


# --- (c) support from weekday pairs ------------------------------------------------------------------------
def weekday_support():
    service_df = pd.read_csv(newest(f"{ERROR_NAME}_2*_service_pairs.csv"))
    results_df = pd.concat([pd.read_csv(newest(f"{SCORE_NAME}_2*_seen_results.csv")),
                            pd.read_csv(newest(f"{SCORE_NAME}_2*_holdout_results.csv"))], ignore_index=True)
    df = results_df.merge(service_df, on=["set_name", "draw_no"], validate="one_to_one")
    df = df[df.is_scored.astype(bool) & np.isfinite(df.model_s)].copy()
    df["rel_tier"] = pd.cut(df.s_dep / df.s_peak.where(df.s_peak > 0), REL_EDGES, right=False, labels=REL_LABELS)
    df["stratum"] = np.select([df.s_dep <= STRATUM_LOW_MAX_TRIPS, df.s_dep >= STRATUM_HIGH_MIN_TRIPS], ["low", "high"], "mid")
    return df.groupby(["rel_tier", "stratum"], observed=True).size()


def weighted_share(df, column):
    return (df[column] * df.persons).sum() / df.persons.sum()


def main():
    tag = run_date()
    cells_df, n_hexes = populated_cells()
    support = weekday_support()
    lines = [f"{NAME} {tag}: {n_hexes:,} populated hexes in {len(cells_df):,} cells of {CELL_M} m; weekend centres "
             f"11:30-21:00 every 30 min; matched weekday Wed; service = distinct trips within {SERVICE_RADIUS_M} m, "
             f"+-{SERVICE_HALF_WINDOW_MIN} min"]
    stop_frames, cell_frames = [], []
    for release in RELEASE_DAYS:
        stops_df, departures_df = release_tables(release)
        stop_frames.append(stop_route_tables(departures_df, release))
        cell_frames.append(cell_table(cells_df, stops_df, departures_df, release))
        print(f"  {release}: cells counted", flush=True)
    stops_table = pd.concat(stop_frames, ignore_index=True)
    cells_table = pd.concat(cell_frames, ignore_index=True)
    cells_table["weekday_pairs"] = [support.get((t, s), 0) for t, s in zip(cells_table.rel_tier, cells_table.stratum)]
    cells_table["is_covered"] = cells_table.weekday_pairs >= COVERAGE_MIN_N
    stops_table.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_stops_routes.csv", index=False)
    cells_table.to_parquet(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_cells.parquet", index=False)

    lines += ["", "(a) stops and routes with weekday service 11:00-21:30 and none on the weekend day; volume ratio = weekend / "
              "weekday departures (stops) or trips (routes):",
              stops_table.to_string(index=False, float_format=lambda x: f"{x:.3f}")]
    has_service = cells_table[cells_table.s_weekday > 0]
    summary_rows = []
    for (release, day), group in cells_table.groupby(["release", "day"]):
        served = group[group.s_weekday > 0]
        summary_rows.append({"release": release, "day": day,
                             "persons_no_weekday_service": 1 - weighted_share(group.assign(x=group.s_weekday > 0), "x"),
                             "lost_share": weighted_share(served, "is_lost"),
                             "median_same_hour": served.same_hour.median(), "median_rel": group.rel.median(),
                             "covered": weighted_share(group, "is_covered")})
    summary_df = pd.DataFrame(summary_rows)
    by_centre = has_service.groupby(["release", "day", "centre_min"]).apply(
        lambda g: pd.Series({"lost": weighted_share(g, "is_lost"), "same_hour": g.same_hour.median(), "rel": g.rel.median()}),
        include_groups=False).unstack(["release", "day"])
    by_centre.index = [f"{c // MIN_PER_HOUR:02d}:{c % MIN_PER_HOUR:02d}" for c in by_centre.index]
    tier_share = cells_table.groupby(["release", "day"]).apply(
        lambda g: g.groupby("rel_tier", observed=False).persons.sum() / g.persons.sum(), include_groups=False)
    lines += ["", "(b) cells, population-weighted (residents + workers); lost = weekday trips > 0 and weekend 0 at the same "
              "centre, share of persons in cells with weekday service; covered = (c):",
              summary_df.to_string(index=False, float_format=lambda x: f"{x:.3f}"), "",
              "rel tier shares (persons):", tier_share.to_string(float_format=lambda x: f"{x:.3f}"), "",
              "by centre (lost share, median same-hour ratio, median rel):",
              by_centre.to_string(float_format=lambda x: f"{x:.2f}")]
    figure(cells_table, cells_df, tag)
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)


def figure(cells_table, cells_df, tag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    release = max(RELEASE_DAYS)
    fig, axes = plt.subplots(2, len(MAP_CENTRES_MIN), figsize=(12, 11), sharex=True, sharey=True)
    for row, day in enumerate(WEEKEND_DAYS):
        for col, centre in enumerate(MAP_CENTRES_MIN):
            ax = axes[row, col]
            cell_df = cells_table[(cells_table.release == release) & (cells_table.day == day) & (cells_table.centre_min == centre)]
            served = cell_df[cell_df.s_weekday > 0]
            points = ax.scatter(served.cell_i, served.cell_j, c=served.same_hour.clip(upper=1.5), s=1.5, cmap="viridis",
                                vmin=0, vmax=1.5)
            lost = served[served.is_lost]
            ax.scatter(lost.cell_i, lost.cell_j, c="red", s=2, label=f"lost ({len(lost)} cells)")
            ax.set_title(f"{release} {day} {centre // MIN_PER_HOUR:02d}:00: weekend / weekday trips")
            ax.set_aspect("equal")
            ax.legend(loc="lower left", fontsize=8)
    fig.colorbar(points, ax=axes, shrink=0.6, label="same-hour ratio (clipped at 1.5)")
    fig.savefig(DIAGNOSTIC_IMG_DIR / f"{NAME}_{tag}_map.png", dpi=110)


if __name__ == "__main__":
    main()
