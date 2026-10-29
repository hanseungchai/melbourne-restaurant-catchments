"""Can every public-transport stop be reached on foot from the walk graph?

Claim: every PTV stop (metro train, tram, metro bus) served on a typical weekday and inside the road
extract lies within STOP_SNAP_THRESHOLD_M of the walk graph's largest connected component, so a
walk leg can start or end at any stop without an invented link.
Where the pipeline relies on it: walk+PT bands 1-2 (DESIGN_pre_spine "Walk and transit layer"): r5py
links each stop to the street network from the same OSM extract, and the own walk graph is the
calibration network (walking speed). PT is not injected into the walk graph; this is an overlay check.
Test: stops served on SERVICE_DATE (calendar + calendar_dates) with location_type 0/empty. Distance
= straight line from the stop to the nearest walk edge (point-to-segment) of the largest component,
in a local metric projection. Stops outside ROAD_EXTRACT_BOUNDS are counted, not judged. Outliers
(over the threshold) are listed and saved as CSV, and drawn red.
Figure: walk graph as a grey base; each route drawn with its most-used shape, line width by weekday
WINDOW_START-WINDOW_END trips per hour per direction, coloured by mode. Two panels: VIEW_RADIUS_M and
ZOOM_RADIUS_M around the subject; served stops dotted in the zoom panel.
Conclusion (run 2026-10-09; same as 2026-10-08): NOT SUPPORTED at 50 m, narrowly. 24,488 stops served on Tue
15 Sep 2026; 487 outside the extract; of the 24,001 judged, 10 are over 50 m and none over 90 m.
Six are Southern Cross platforms (51.5-55.0 m; the platforms are not in the walk graph); four are
bus stops: DFO Essendon/Perimeter Rd 89.1 m, Princes Fwy 69.4 m, Chesterfield Farm/Ferntree Gully
Rd 60.0 m, Catholic Regional College/Santa Monica Dr 50.5 m. Median distance: bus 9.7 m, train
6.2 m, tram 6.7 m; 99th percentile: bus 44.1 m, train 51.5 m, tram 27.7 m. The walk graph's
largest component holds 98.6% of its nodes.
Accepted as a known limit (user, 2026-10-08): a minor claim; the walk graph's job is walking-speed
calibration and r5py links stops itself. Threshold kept at 50 m; platforms not added to the walk graph.

Inputs: frozen_inputs/gtfs_ptv/{metro_train,tram,metro_bus}/google_transit.zip (read straight from
the zips) and the map_construction stage's walk graph (outputs/road_graphs/walk_graph.gpickle).
The walk graph build was parked on 2026-10-13 (docs/parked_code/walk_graph.md); the file built on
2026-10-09 is left in place and is what this reads.

Self-contained: imports nothing from functions/, config.py or the pipeline (CLAUDE.md D1).
"""
import datetime
import gc
import io
import math
import pickle
import zipfile
from pathlib import Path

import contextily as cx
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from scipy.spatial import cKDTree

# ---------------------------------------------------------------------------
# Paths and run naming
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GTFS_DIR = PROJECT_ROOT / "frozen_inputs" / "gtfs_ptv"
GTFS_ZIP_NAME = "google_transit.zip"
WALK_GRAPH_PATH = PROJECT_ROOT / "outputs" / "road_graphs" / "walk_graph.gpickle"
SUBJECT_COORD_PATH = PROJECT_ROOT / "frozen_inputs" / "manual_inputs" / "subject_business_coord.txt"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"

DIAGNOSTIC_NAME = "pt_stop_walk_access"
RUN_PREFIX = f"{DIAGNOSTIC_NAME}_{datetime.datetime.now():%Y%m%d}"   # one run per day: a same-day rerun replaces that day's files (D1)
FIGURE_PATH = DIAGNOSTIC_IMG_DIR / f"{RUN_PREFIX}_map.png"
STOPS_TABLE_PATH = DIAGNOSTIC_DATA_DIR / f"{RUN_PREFIX}_stops.csv"
OUTLIERS_TABLE_PATH = DIAGNOSTIC_DATA_DIR / f"{RUN_PREFIX}_outliers.csv"
ROUTES_TABLE_PATH = DIAGNOSTIC_DATA_DIR / f"{RUN_PREFIX}_routes.csv"

# feed folder -> (mode label, line colour); PTV network colours
FEEDS = {
    "metro_bus": ("bus", "#FF8200"),
    "tram": ("tram", "#78BE20"),
    "metro_train": ("train", "#0072CE"),
}   # drawn in this order: train on top

# ---------------------------------------------------------------------------
# Claim and service-day parameters
# ---------------------------------------------------------------------------
STOP_SNAP_THRESHOLD_M = 50       # a stop farther than this from the walk graph is an outlier
SERVICE_DATE = datetime.date(2026, 9, 15)   # a Tuesday in school term, inside the feeds' period
WINDOW_START_S = 7 * 3600        # weekday morning window, trips by first departure
WINDOW_END_S = 9 * 3600
WINDOW_HOURS = (WINDOW_END_S - WINDOW_START_S) / 3600
ROAD_EXTRACT_BOUNDS = (143.599, -38.893, 146.327, -36.735)   # BBBike extract: min lon, min lat, max lon, max lat
EDGE_SEARCH_RADIUS_M = 2_000     # walk nodes this close to an outlier candidate supply its candidate edges
STOP_LOCATION_TYPES = {"", "0"}  # GTFS: stop or platform (not station, entrance, node)
CALENDAR_ADDED = 1               # calendar_dates exception_type
CALENDAR_REMOVED = 2
STOP_TIMES_CHUNK_ROWS = 2_000_000
METRES_PER_DEGREE_LAT = 111_320

# ---------------------------------------------------------------------------
# Figure parameters
# ---------------------------------------------------------------------------
WIDTH_PER_TRIP_PER_H = 0.12      # line width (pt) per trip/h per direction
MIN_ROUTE_WIDTH = 0.15           # routes with little or no service in the window
MAX_ROUTE_WIDTH = 3.0
ROUTE_ALPHA = 0.85
WALK_COLOUR = "#bdbdbd"
WALK_WIDTH = 0.05
OUTLIER_COLOUR = "red"
STOP_DOT_SIZE = 2
OUTLIER_MARKER_SIZE = 25
VIEW_RADIUS_M = 60_000           # full panel: box half-width around the subject (covers the metro network)
ZOOM_RADIUS_M = 10_000
FIGURE_SIZE_IN = (24, 12)
FIGURE_DPI = 200
SHOULD_ADD_BASEMAP = False       # the walk graph is the base
LEGEND_FREE_RECT = (0, 0.05, 1, 1)
LEGEND_TRIPS_PER_H = [2, 6, 12, 20]

NODE_LON_ATTR = "x"
NODE_LAT_ATTR = "y"


def read_subject_location():
    first_line = SUBJECT_COORD_PATH.read_text(encoding="utf-8").splitlines()[0]
    lat_text, lon_text = first_line.split(",")
    return float(lat_text), float(lon_text)


def read_gtfs_table(zip_file, name, **kwargs):
    with zip_file.open(name) as f:
        return pd.read_csv(io.TextIOWrapper(f, encoding="utf-8-sig"), dtype=str, keep_default_na=False, **kwargs)


def gtfs_time_to_s(times):
    """'HH:MM:SS' (hours may pass 24) -> seconds after midnight."""
    parts = times.str.split(":", expand=True).astype(int)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def services_on(zip_file, date):
    """service_ids running on date: calendar weekday rule, then calendar_dates additions and removals."""
    calendar_df = read_gtfs_table(zip_file, "calendar.txt")
    date_text = date.strftime("%Y%m%d")
    weekday_column = date.strftime("%A").lower()
    in_period = (calendar_df["start_date"] <= date_text) & (calendar_df["end_date"] >= date_text)
    services = set(calendar_df.loc[in_period & (calendar_df[weekday_column] == "1"), "service_id"])
    exceptions_df = read_gtfs_table(zip_file, "calendar_dates.txt")
    on_date_df = exceptions_df[exceptions_df["date"] == date_text]
    services |= set(on_date_df.loc[on_date_df["exception_type"].astype(int) == CALENDAR_ADDED, "service_id"])
    services -= set(on_date_df.loc[on_date_df["exception_type"].astype(int) == CALENDAR_REMOVED, "service_id"])
    return services


def read_feed(feed_name):
    """One feed's served stops, and per route: trips/h per direction in the window and the shape to draw."""
    mode, colour = FEEDS[feed_name]
    with zipfile.ZipFile(GTFS_DIR / feed_name / GTFS_ZIP_NAME) as zip_file:
        services = services_on(zip_file, SERVICE_DATE)
        trips_df = read_gtfs_table(zip_file, "trips.txt", usecols=["route_id", "service_id", "trip_id", "shape_id", "direction_id"])
        trips_df = trips_df[trips_df["service_id"].isin(services)]
        trip_ids = set(trips_df["trip_id"])

        served_stop_ids = set()
        first_departures = []
        with zip_file.open("stop_times.txt") as f:   # kept open while the chunks are read
            reader = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8-sig"), dtype=str, keep_default_na=False,
                                 usecols=["trip_id", "departure_time", "stop_id", "stop_sequence"],
                                 chunksize=STOP_TIMES_CHUNK_ROWS)
            for chunk_df in reader:
                chunk_df = chunk_df[chunk_df["trip_id"].isin(trip_ids)]
                served_stop_ids |= set(chunk_df["stop_id"])
                chunk_df = chunk_df.assign(stop_sequence=chunk_df["stop_sequence"].astype(int))
                first_departures.append(chunk_df.loc[chunk_df.groupby("trip_id")["stop_sequence"].idxmin(),
                                                     ["trip_id", "stop_sequence", "departure_time"]])
        first_df = pd.concat(first_departures)   # a trip split across chunks: keep its lowest sequence
        first_df = first_df.loc[first_df.groupby("trip_id")["stop_sequence"].idxmin()]
        departure_s = gtfs_time_to_s(first_df.set_index("trip_id")["departure_time"])

        trips_df = trips_df.assign(departure_s=trips_df["trip_id"].map(departure_s))
        trips_df["is_in_window"] = trips_df["departure_s"].between(WINDOW_START_S, WINDOW_END_S, inclusive="left")
        routes_df = route_frequency(trips_df)

        shapes_df = read_gtfs_table(zip_file, "shapes.txt", usecols=["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"])
        shapes_df = shapes_df[shapes_df["shape_id"].isin(set(routes_df["shape_id"]))]
        stops_df = read_gtfs_table(zip_file, "stops.txt", usecols=["stop_id", "stop_name", "stop_lat", "stop_lon", "location_type"])

    stops_df = stops_df[stops_df["location_type"].isin(STOP_LOCATION_TYPES) & stops_df["stop_id"].isin(served_stop_ids)]
    stops_df = stops_df.assign(mode=mode, lat=stops_df["stop_lat"].astype(float), lon=stops_df["stop_lon"].astype(float))
    stops_df = stops_df[["stop_id", "stop_name", "mode", "lat", "lon"]]
    shape_lines = {}
    shapes_df = shapes_df.assign(seq=shapes_df["shape_pt_sequence"].astype(int)).sort_values(["shape_id", "seq"])
    for shape_id, points_df in shapes_df.groupby("shape_id"):
        shape_lines[shape_id] = points_df[["shape_pt_lon", "shape_pt_lat"]].astype(float).to_numpy()
    routes_df = routes_df.assign(mode=mode, colour=colour)
    print(f"{mode}: {len(services)} services on {SERVICE_DATE}, {len(trips_df):,} trips, "
          f"{trips_df['is_in_window'].sum():,} start in the window; {len(routes_df)} routes; {len(stops_df):,} served stops")
    return stops_df, routes_df, shape_lines


def route_frequency(trips_df):
    """Per route: window trips per hour per direction, and its most-used shape (window trips first)."""
    rows = []
    for route_id, route_trips_df in trips_df.groupby("route_id"):
        window_df = route_trips_df[route_trips_df["is_in_window"]]
        n_directions = max(window_df["direction_id"].nunique(), 1)
        trips_per_h = len(window_df) / WINDOW_HOURS / n_directions
        shape_source_df = window_df if len(window_df) else route_trips_df
        rows.append((route_id, len(window_df), trips_per_h, shape_source_df["shape_id"].mode().iloc[0]))
    return pd.DataFrame(rows, columns=["route_id", "window_trips", "trips_per_h_per_direction", "shape_id"])


def to_metres(lats, lons, origin_lat, origin_lon):
    """Local equirectangular projection around the origin (error well under 1 m per 50 m in the metro area)."""
    x = (np.asarray(lons) - origin_lon) * METRES_PER_DEGREE_LAT * math.cos(math.radians(origin_lat))
    y = (np.asarray(lats) - origin_lat) * METRES_PER_DEGREE_LAT
    return x, y


def load_walk_graph():
    """Walk nodes (lon, lat, is in largest component) and edges as node-index pairs."""
    print(f"Loading {WALK_GRAPH_PATH} ...")
    with open(WALK_GRAPH_PATH, "rb") as f:
        walk_graph = pickle.load(f)
    print(f"Walk graph: {walk_graph.number_of_nodes():,} nodes, {walk_graph.number_of_edges():,} edges")
    largest_component = max(nx.connected_components(walk_graph), key=len)
    node_ids = list(walk_graph.nodes)
    node_index = {node_id: i for i, node_id in enumerate(node_ids)}
    node_lon = np.array([walk_graph.nodes[n][NODE_LON_ATTR] for n in node_ids])
    node_lat = np.array([walk_graph.nodes[n][NODE_LAT_ATTR] for n in node_ids])
    is_in_largest = np.array([n in largest_component for n in node_ids])
    edges = np.array([(node_index[u], node_index[v]) for u, v in walk_graph.edges()], dtype=np.int64)
    print(f"Largest component: {is_in_largest.sum():,} nodes ({is_in_largest.mean():.1%})")
    del walk_graph, largest_component, node_index, node_ids
    gc.collect()
    return node_lon, node_lat, is_in_largest, edges


def point_segment_distance_m(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = np.where(length_sq > 0, ((px - ax) * dx + (py - ay) * dy) / np.where(length_sq > 0, length_sq, 1), 0)
    t = np.clip(t, 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def stop_distances_m(stops_df, node_lon, node_lat, is_in_largest, edges, origin_lat, origin_lon):
    """Distance from each stop to the nearest largest-component walk edge (nearest node, refined when over threshold)."""
    node_x, node_y = to_metres(node_lat, node_lon, origin_lat, origin_lon)
    stop_x, stop_y = to_metres(stops_df["lat"], stops_df["lon"], origin_lat, origin_lon)
    largest_index = np.flatnonzero(is_in_largest)
    tree = cKDTree(np.column_stack([node_x[largest_index], node_y[largest_index]]))
    node_distance_m, _ = tree.query(np.column_stack([stop_x, stop_y]))
    distance_m = node_distance_m.copy()

    largest_edges = edges[is_in_largest[edges[:, 0]] & is_in_largest[edges[:, 1]]]
    candidates = np.flatnonzero(node_distance_m > STOP_SNAP_THRESHOLD_M)
    print(f"Stops over {STOP_SNAP_THRESHOLD_M} m from every node: {len(candidates):,}; refining against edges")
    for i in candidates:
        near = largest_index[tree.query_ball_point([stop_x[i], stop_y[i]], EDGE_SEARCH_RADIUS_M)]
        if len(near) == 0:
            continue
        near_edges = largest_edges[np.isin(largest_edges[:, 0], near) | np.isin(largest_edges[:, 1], near)]
        a, b = near_edges[:, 0], near_edges[:, 1]
        distance_m[i] = point_segment_distance_m(stop_x[i], stop_y[i], node_x[a], node_y[a], node_x[b], node_y[b]).min()
    return node_distance_m, distance_m


def view_box(subject_lat, subject_lon, radius_m):
    d_lat = radius_m / METRES_PER_DEGREE_LAT
    d_lon = radius_m / (METRES_PER_DEGREE_LAT * math.cos(math.radians(subject_lat)))
    return subject_lon - d_lon, subject_lon + d_lon, subject_lat - d_lat, subject_lat + d_lat


def route_width(trips_per_h):
    return np.clip(np.asarray(trips_per_h) * WIDTH_PER_TRIP_PER_H, MIN_ROUTE_WIDTH, MAX_ROUTE_WIDTH)


def draw_panel(ax, walk_lines, routes_df, shape_lines, stops_df, subject_lat, subject_lon, radius_m, title, should_dot_stops):
    lon_min, lon_max, lat_min, lat_max = view_box(subject_lat, subject_lon, radius_m)
    in_view = (walk_lines[:, :, 0].min(axis=1) <= lon_max) & (walk_lines[:, :, 0].max(axis=1) >= lon_min) \
        & (walk_lines[:, :, 1].min(axis=1) <= lat_max) & (walk_lines[:, :, 1].max(axis=1) >= lat_min)
    print(f"{title}: {in_view.sum():,} walk edges in view")
    ax.add_collection(LineCollection(walk_lines[in_view], linewidths=WALK_WIDTH, colors=WALK_COLOUR))
    for mode, colour in FEEDS.values():
        mode_df = routes_df[routes_df["mode"] == mode].sort_values("width")
        lines = [shape_lines[shape_id] for shape_id in mode_df["shape_id"]]
        ax.add_collection(LineCollection(lines, linewidths=mode_df["width"].to_numpy(), colors=colour,
                                         alpha=ROUTE_ALPHA, capstyle="round"))
    if should_dot_stops:
        for mode, colour in FEEDS.values():
            mode_stops_df = stops_df[stops_df["mode"] == mode]
            ax.scatter(mode_stops_df["lon"], mode_stops_df["lat"], s=STOP_DOT_SIZE, color=colour, linewidths=0, zorder=3)
    outliers_df = stops_df[stops_df["is_outlier"]]
    ax.scatter(outliers_df["lon"], outliers_df["lat"], s=OUTLIER_MARKER_SIZE, facecolors="none",
               edgecolors=OUTLIER_COLOUR, linewidths=1, zorder=4)
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_aspect(1 / math.cos(math.radians(subject_lat)))
    if SHOULD_ADD_BASEMAP:
        cx.add_basemap(ax, crs="EPSG:4326", source=cx.providers.Esri.WorldGrayCanvas, attribution_size=6)
    ax.plot(subject_lon, subject_lat, marker="*", color="red", markersize=12, markeredgecolor="black", zorder=5)
    ax.set_title(title)
    ax.set_axis_off()


def main():
    subject_lat, subject_lon = read_subject_location()
    feed_results = [read_feed(feed_name) for feed_name in FEEDS]
    stops_df = pd.concat([stops for stops, _, _ in feed_results], ignore_index=True)
    routes_df = pd.concat([routes for _, routes, _ in feed_results], ignore_index=True)
    shape_lines = {shape_id: line for _, _, lines in feed_results for shape_id, line in lines.items()}

    lon_min, lat_min, lon_max, lat_max = ROAD_EXTRACT_BOUNDS
    stops_df["is_in_extent"] = stops_df["lon"].between(lon_min, lon_max) & stops_df["lat"].between(lat_min, lat_max)
    print(f"\nServed stops: {len(stops_df):,}; outside the road extract (not judged): {(~stops_df['is_in_extent']).sum():,}")

    node_lon, node_lat, is_in_largest, edges = load_walk_graph()
    node_distance_m, distance_m = stop_distances_m(stops_df, node_lon, node_lat, is_in_largest, edges, subject_lat, subject_lon)
    stops_df["nearest_node_m"] = node_distance_m
    stops_df["nearest_edge_m"] = distance_m
    stops_df["is_outlier"] = stops_df["is_in_extent"] & (stops_df["nearest_edge_m"] > STOP_SNAP_THRESHOLD_M)

    judged_df = stops_df[stops_df["is_in_extent"]]
    print(f"\nDistance to the walk graph (largest component), {len(judged_df):,} stops in extent:")
    print(judged_df.groupby("mode")["nearest_edge_m"].describe(percentiles=[0.5, 0.9, 0.99]).to_string(float_format=lambda x: f"{x:.1f}"))
    outliers_df = stops_df[stops_df["is_outlier"]].sort_values("nearest_edge_m", ascending=False)
    print(f"\nOutliers (> {STOP_SNAP_THRESHOLD_M} m): {len(outliers_df):,}")
    if len(outliers_df):
        print(outliers_df[["mode", "stop_id", "stop_name", "lat", "lon", "nearest_edge_m"]].to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    stops_df.to_csv(STOPS_TABLE_PATH, index=False)
    outliers_df.to_csv(OUTLIERS_TABLE_PATH, index=False)
    routes_df.drop(columns="colour").to_csv(ROUTES_TABLE_PATH, index=False)
    print(f"Saved {STOPS_TABLE_PATH}\nSaved {OUTLIERS_TABLE_PATH}\nSaved {ROUTES_TABLE_PATH}")

    print("\nWindow trips/h per direction by mode:")
    print(routes_df.groupby("mode")["trips_per_h_per_direction"].describe(percentiles=[0.5, 0.9]).to_string(float_format=lambda x: f"{x:.1f}"))
    routes_df["width"] = route_width(routes_df["trips_per_h_per_direction"])

    walk_lines = np.stack([np.column_stack([node_lon[edges[:, 0]], node_lat[edges[:, 0]]]),
                           np.column_stack([node_lon[edges[:, 1]], node_lat[edges[:, 1]]])], axis=1)
    del edges
    gc.collect()
    fig, axes = plt.subplots(1, 2, figsize=FIGURE_SIZE_IN)
    draw_panel(axes[0], walk_lines, routes_df, shape_lines, stops_df, subject_lat, subject_lon, VIEW_RADIUS_M,
               f"PT routes over the walk graph ({VIEW_RADIUS_M // 1000} km around subject)", should_dot_stops=False)
    draw_panel(axes[1], walk_lines, routes_df, shape_lines, stops_df, subject_lat, subject_lon, ZOOM_RADIUS_M,
               f"Zoom: {ZOOM_RADIUS_M // 1000} km around subject, served stops dotted", should_dot_stops=True)
    handles = [Line2D([], [], color="black", linewidth=float(route_width(n)), label=f"{n} trips/h") for n in LEGEND_TRIPS_PER_H]
    handles += [Line2D([], [], color=colour, linewidth=2, label=mode) for mode, colour in FEEDS.values()]
    handles += [Line2D([], [], color=WALK_COLOUR, linewidth=2, label="walk graph"),
                Line2D([], [], marker="o", linestyle="", markerfacecolor="none", markeredgecolor=OUTLIER_COLOUR,
                       label=f"stop > {STOP_SNAP_THRESHOLD_M} m from walk graph")]
    fig.tight_layout(rect=LEGEND_FREE_RECT)
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False,
               title=f"Line width = trips per hour per direction, {SERVICE_DATE:%a %d %b %Y} "
                     f"{WINDOW_START_S // 3600:02d}:00-{WINDOW_END_S // 3600:02d}:00 (first departure)")
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    print(f"Saved {FIGURE_PATH}")

    n_outliers = int(stops_df["is_outlier"].sum())
    verdict = "SUPPORTED" if n_outliers == 0 else f"NOT SUPPORTED ({n_outliers:,} served stops over the threshold)"
    print(f"\nClaim (every served stop in extent within {STOP_SNAP_THRESHOLD_M} m of the walk graph): {verdict}")


if __name__ == "__main__":
    main()
