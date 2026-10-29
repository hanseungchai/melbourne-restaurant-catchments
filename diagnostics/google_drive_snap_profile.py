"""What kind of road does Google start and end a drive trip on? (DESIGN.md Q12)

Claim: none yet. Exploratory profile, no pre-registered criterion. It follows google_drive_snap_side.py,
which found Google's start/end road is the requested point's nearest road only 81.6% of the time, and
that banning service roads outright makes it worse (Google itself uses a service road for ~25% of
endpoints). This profiles the roads Google snaps to, to find a rule that separates the ones it uses from
the ones it skips. Where the pipeline would rely on it: the candidate-road rule in routing_graph
(config.CANDIDATE_EXCLUDED_HIGHWAY_TYPES, config.CANDIDATE_TIE_WINDOW_M), also routing's tie rule.

Method (no API calls): the frozen 2026-09-30 Routes responses (origin = hex centroid, destination =
venue, both sent as lat/lng, not place_id) give Google's snapped start and end points and the route
polyline for 4,000 pairs. Roads come straight from the frozen OSM extract, not the drive graph: the graph
keeps no service or access tags and drops access=private/no ways, which Google may still use.
1. Vehicle roads: every OSM highway way except footpath-type and unbuilt ones (NON_VEHICLE_HIGHWAY_TYPES)
   and area=yes, cut into node-to-node segments, kept near the endpoints. Each is flagged in_drive_graph
   by the road_graphs rule (drive highway type, not barred by access).
2. Google's road: the way nearest Google's snapped point within UNMATCHED_M. If another way is within
   AMBIGUOUS_M of that, the polyline's first (last) POLYLINE_PROBE_M decide, by POLYLINE_SEPARATION_M;
   otherwise "ambiguous".
3. Per endpoint: Google's road attributes (class, service subtype, access, one-way, in_drive_graph);
   travel direction over the first (last) HEADING_M of the route; whether that heads toward or away from
   the other end of the trip (angle to the straight origin->destination line); which side of travel the
   requested point lies on (left = kerb side, Australia drives on the left); and the same road attributes
   for the vehicle road nearest the requested point (baseline). "Google took the nearest" = Google's road
   is within NEAREST_TIE_M of the nearest road's distance from the requested point.

Conclusion (run 2026-10-10, 8,000 endpoints; 7,280 matched, 587 unmatched, 133 ambiguous): no OSM tag
or direction cleanly predicts Google's choice. When the requested point's nearest road is a named, public,
non-service road, Google takes it 91-96% of the time. When the nearest is a service road it takes it ~65%
(parking aisle ~73%, alley ~65%, driveway ~47%); unnamed ~60%; access=private 23-47%. So no road type is
reliably skipped, and a filter on these tags trades about as many hits as it gains. Direction plays no
visible part: toward/sideways/away shares are the same whether or not Google took the nearest road, and
on two-way roads the requested point is left of travel ~50% of the time (the left bias on one-way roads,
69-81%, just reflects the near carriageway of a dual road). Most likely Google snaps to the nearest road
in its own map, which agrees with OSM on public streets but only about half the time on minor service
roads; 587 Google points have no OSM vehicle road within 15 m at all.

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
"""

import datetime
import math
import pickle
import sys
from pathlib import Path

import numpy as np
import osmium
import pandas as pd
import shapely
from pyproj import Transformer

DIAGNOSTIC_NAME = "google_drive_snap_profile"
RUN_DATE = datetime.date.today().strftime("%Y%m%d")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTES_DIR = PROJECT_ROOT / "frozen_inputs" / "routes_drive_eta_20260930"
DRAWS_PATH = ROUTES_DIR / "od_sample_pairs.csv"
ETA_PATH = ROUTES_DIR / "od_sample_pairs_google_estimates.csv"
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
PREFIX = f"{DIAGNOSTIC_NAME}_{RUN_DATE}"
SEGMENTS_SUFFIX = "_segments.pkl"                # saved data, reused on later runs, never overwritten
SEGMENTS_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}{SEGMENTS_SUFFIX}"
ENDPOINTS_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_endpoints.csv"
LOG_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_log.txt"

GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:7855"                        # GDA2020 / MGA 55, metres
HTTP_OK = 200
POLYLINE_PRECISION = 1e5                        # Google encoded polyline: 5 decimal places

# OSM tags, as road_graphs.py reads them
DRIVE_HIGHWAY_TYPES = {                         # as config.DRIVE_HIGHWAY_TYPES
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "motorway_link", "trunk_link", "primary_link",
    "secondary_link", "tertiary_link", "living_street", "service"}
NO_ACCESS_VALUES = ("no", "private")            # as config.NO_ACCESS_VALUES
NON_VEHICLE_HIGHWAY_TYPES = {
    "footway", "path", "cycleway", "steps", "pedestrian", "corridor", "bridleway", "elevator",
    "platform", "proposed", "construction", "abandoned", "razed", "via_ferrata", "traffic_island"}
ONEWAY_VALUES = ("yes", "true", "1", "-1")
ONEWAY_JUNCTION_VALUES = ("roundabout", "circular")
TAG_KEYS = ("highway", "service", "access", "motor_vehicle", "vehicle", "oneway", "junction", "name", "ref")
NO_TAG = "none"
ROAD_CLASSES = {                                # highway value -> class
    "motorway": "arterial", "trunk": "arterial", "primary": "arterial", "secondary": "arterial",
    "motorway_link": "arterial_link", "trunk_link": "arterial_link", "primary_link": "arterial_link",
    "secondary_link": "arterial_link",
    "tertiary": "collector", "tertiary_link": "collector",
    "residential": "local", "unclassified": "local", "living_street": "local", "road": "local",
    "service": "service"}
OTHER_CLASS = "other"
ACCESS_GROUPS = {"private": "private", "no": "private",
                 "destination": "destination", "customers": "destination", "delivery": "destination"}
PUBLIC_ACCESS = "public"                        # untagged, yes, permissive, ...

# Geometry and thresholds
WAY_FILTER_CELL_DEG = 0.002                     # grid cell (~200 m) for picking ways near endpoints
WAY_FILTER_RADIUS_M = 500                       # ways with a node this close to an endpoint are kept
METRES_PER_DEG_LAT = 111_000
SEARCH_RADIUS_M = 300                           # baseline: nearest road to the requested point within this
UNMATCHED_M = 15                                # as google_drive_snap_side.py
AMBIGUOUS_M = 3
POLYLINE_PROBE_M = (5, 10, 15, 20)
POLYLINE_SEPARATION_M = 2
PROBE_RADIUS_M = 60
HEADING_M = 15                                  # route length over which the travel direction is taken
TOWARD_MAX_DEG = 60                             # heading within this of the O->D line: toward
AWAY_MIN_DEG = 120                              # beyond this: away; between: sideways
NEAREST_TIE_M = 0.5                             # Google's road counts as the nearest within this
OFFSET_QUANTILES = (0.25, 0.5, 0.75, 0.9)
PROGRESS_EVERY_N_WAYS = 200_000

ENDS = ("origin", "dest")


class Tee:
    """Print to the console and keep every line for the run log."""

    def __init__(self):
        self.stdout = sys.stdout
        self.lines = []

    def write(self, text):
        self.stdout.write(text)
        self.lines.append(text)

    def flush(self):
        self.stdout.flush()


def decode_polyline(encoded):
    """Google encoded polyline -> array of (lat, lon)."""
    coords, index, lat, lon = [], 0, 0, 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift, result = 0, 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lat / POLYLINE_PRECISION, lon / POLYLINE_PRECISION))
    return np.array(coords)


def load_endpoints(to_metric):
    """One row per (draw, end): requested point, Google's point, the other end's requested point and the
    route polyline in metres, walked from this end (reversed for destinations)."""
    draws_df = pd.read_csv(DRAWS_PATH)
    eta_df = pd.read_csv(ETA_PATH)
    pairs_df = draws_df.merge(eta_df, on="draw_no", how="inner", validate="one_to_one")
    pairs_df = pairs_df[(pairs_df.http_status == HTTP_OK) & pairs_df.g_o_lat.notna()
                        & pairs_df.g_d_lat.notna() & pairs_df.polyline.notna()]
    print(f"pairs: {len(draws_df):,} draws, {len(pairs_df):,} with Google points and a polyline")

    rows = []
    for pair in pairs_df.itertuples(index=False):
        lat_lon = decode_polyline(pair.polyline)
        line_x, line_y = to_metric.transform(lat_lon[:, 1], lat_lon[:, 0])
        line_xy = np.column_stack([line_x, line_y])
        for end in ENDS:
            if end == "origin":
                req = (pair.origin_lat, pair.origin_lon)
                google = (pair.g_o_lat, pair.g_o_lon)
                other = (pair.dest_lat, pair.dest_lon)
                route_xy = line_xy
            else:
                req = (pair.dest_lat, pair.dest_lon)
                google = (pair.g_d_lat, pair.g_d_lon)
                other = (pair.origin_lat, pair.origin_lon)
                route_xy = line_xy[::-1]
            rows.append(dict(draw_no=pair.draw_no, end=end, req_lat=req[0], req_lon=req[1],
                             g_lat=google[0], g_lon=google[1], other_lat=other[0], other_lon=other[1],
                             route_xy=route_xy))
    endpoints_df = pd.DataFrame(rows)
    for name in ("req", "g", "other"):
        endpoints_df[f"{name}_x"], endpoints_df[f"{name}_y"] = to_metric.transform(
            endpoints_df[f"{name}_lon"].to_numpy(), endpoints_df[f"{name}_lat"].to_numpy())
    return endpoints_df


def cell_of(lat, lon):
    return math.floor(lat / WAY_FILTER_CELL_DEG), math.floor(lon / WAY_FILTER_CELL_DEG)


def cells_near(endpoints_df):
    """Grid cells within WAY_FILTER_RADIUS_M of any requested or Google point."""
    lat_steps = math.ceil(WAY_FILTER_RADIUS_M / (METRES_PER_DEG_LAT * WAY_FILTER_CELL_DEG))
    cells = set()
    for lat_col, lon_col in (("req_lat", "req_lon"), ("g_lat", "g_lon")):
        for lat, lon in zip(endpoints_df[lat_col], endpoints_df[lon_col]):
            lon_steps = math.ceil(lat_steps / math.cos(math.radians(lat)))
            row, col = cell_of(lat, lon)
            for i in range(-lat_steps, lat_steps + 1):
                for j in range(-lon_steps, lon_steps + 1):
                    cells.add((row + i, col + j))
    return cells


class VehicleWayReader(osmium.SimpleHandler):
    """Collects vehicle ways with a node in one of the given cells: their tags and node coordinates."""

    def __init__(self, cells):
        super().__init__()
        self.cells = cells
        self.ways = []                  # (way_id, tags dict, [(lat, lon), ...])
        self.way_count = 0

    def way(self, w):
        highway = w.tags.get("highway")
        if highway is None or highway in NON_VEHICLE_HIGHWAY_TYPES or w.tags.get("area") == "yes":
            return
        self.way_count += 1
        if self.way_count % PROGRESS_EVERY_N_WAYS == 0:
            print(f"  {self.way_count:,} vehicle ways read, {len(self.ways):,} kept")
        try:
            coords = [(n.lat, n.lon) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(coords) < 2 or not any(cell_of(lat, lon) in self.cells for lat, lon in coords):
            return
        self.ways.append((w.id, {key: w.tags.get(key) for key in TAG_KEYS}, coords))


def is_in_drive_graph(tags):
    """The road_graphs rule: a drive highway type, not barred by access."""
    access_value = tags["motor_vehicle"] or tags["vehicle"] or tags["access"]
    return tags["highway"] in DRIVE_HIGHWAY_TYPES and access_value not in NO_ACCESS_VALUES


def read_segments(endpoints_df):
    """Vehicle-road segments near the endpoints, reused from the latest saved file if one exists."""
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{DIAGNOSTIC_NAME}_*{SEGMENTS_SUFFIX}"))
    if saved:
        print(f"reusing saved segments {saved[-1].name} (made {saved[-1].name.split('_')[-2]})")
        with open(saved[-1], "rb") as f:
            return pickle.load(f)
    print(f"reading vehicle ways from {PBF_PATH.name} (a few minutes) ...")
    reader = VehicleWayReader(cells_near(endpoints_df))
    reader.apply_file(str(PBF_PATH), locations=True)
    print(f"  {reader.way_count:,} vehicle ways, {len(reader.ways):,} near the endpoints")

    seg_rows, way_rows = [], []
    for way_id, tags, coords in reader.ways:
        access_value = tags["motor_vehicle"] or tags["vehicle"] or tags["access"]
        way_rows.append(dict(way_id=way_id, highway=tags["highway"],
                             road_class=ROAD_CLASSES.get(tags["highway"], OTHER_CLASS),
                             service=tags["service"] or NO_TAG, access=access_value or NO_TAG,
                             access_group=ACCESS_GROUPS.get(access_value, PUBLIC_ACCESS),
                             is_oneway=(tags["oneway"] in ONEWAY_VALUES
                                        or tags["junction"] in ONEWAY_JUNCTION_VALUES
                                        or tags["highway"] == "motorway"),
                             is_named=bool(tags["name"] or tags["ref"]),
                             in_drive_graph=is_in_drive_graph(tags)))
        for (lat_a, lon_a), (lat_b, lon_b) in zip(coords[:-1], coords[1:]):
            seg_rows.append((way_id, lat_a, lon_a, lat_b, lon_b))
    ways_df = pd.DataFrame(way_rows).set_index("way_id")
    segments_df = pd.DataFrame(seg_rows, columns=["way_id", "lat_a", "lon_a", "lat_b", "lon_b"])
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SEGMENTS_PATH, "wb") as f:
        pickle.dump((ways_df, segments_df), f)
    print(f"Saved {SEGMENTS_PATH}")
    return ways_df, segments_df


def segment_geometry(segments_df, to_metric):
    ax, ay = to_metric.transform(segments_df.lon_a.to_numpy(), segments_df.lat_a.to_numpy())
    bx, by = to_metric.transform(segments_df.lon_b.to_numpy(), segments_df.lat_b.to_numpy())
    return shapely.linestrings(np.stack([np.column_stack([ax, ay]), np.column_stack([bx, by])], axis=1))


def near_ways(points, tree, geoms, way_ids, radius_m):
    """Per point, every way within radius_m, nearest first: list of (way_ids array, dist_m array)."""
    pt_ix, seg_ix = tree.query(points, predicate="dwithin", distance=radius_m)
    near_df = (pd.DataFrame({"pt": pt_ix, "way_id": way_ids[seg_ix],
                             "dist_m": shapely.distance(points[pt_ix], geoms[seg_ix])})
               .groupby(["pt", "way_id"], as_index=False).dist_m.min()
               .sort_values(["pt", "dist_m", "way_id"], kind="stable"))
    bounds = np.searchsorted(near_df.pt.to_numpy(), np.arange(len(points) + 1))
    ways, dists = near_df.way_id.to_numpy(), near_df.dist_m.to_numpy()
    return [(ways[bounds[i]:bounds[i + 1]], dists[bounds[i]:bounds[i + 1]]) for i in range(len(points))]


def point_along(route_xy, distance_m):
    """The point distance_m along the route from its first vertex, or None if the route is shorter."""
    along = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(route_xy, axis=0).T))])
    if along[-1] < distance_m:
        return None
    return np.array([np.interp(distance_m, along, route_xy[:, 0]), np.interp(distance_m, along, route_xy[:, 1])])


def google_way(route_xy, candidates, tree, geoms, way_ids):
    """(way_id, status) for Google's snapped point; status matched / ambiguous / unmatched."""
    ways, dists = candidates
    if len(ways) == 0 or dists[0] > UNMATCHED_M:
        return None, "unmatched"
    contenders = ways[dists <= dists[0] + AMBIGUOUS_M]
    if len(contenders) == 1:
        return contenders[0], "matched"
    probes = [point_along(route_xy, d) for d in POLYLINE_PROBE_M]
    if any(p is None for p in probes):
        return None, "ambiguous"
    probe_points = shapely.points(np.array(probes))
    means = []
    for way_id in contenders:
        geom = shapely.union_all(geoms[way_ids == way_id])
        dist_m = np.minimum(shapely.distance(probe_points, geom), PROBE_RADIUS_M)
        means.append(dist_m.mean())
    order = np.argsort(means, kind="stable")
    if means[order[1]] - means[order[0]] < POLYLINE_SEPARATION_M:
        return None, "ambiguous"
    return contenders[order[0]], "matched"


def travel_geometry(ep):
    """Heading class (toward / sideways / away from the other end) and side of the requested point
    (left / right of travel), from the route's first (last) HEADING_M."""
    ahead = point_along(ep.route_xy, HEADING_M)
    if ahead is None:
        return None, None
    start = ep.route_xy[0]
    heading = ahead - start
    if ep.end == "dest":                 # route_xy runs backwards from the destination
        heading = -heading
    od_line = np.array([ep.other_x - ep.req_x, ep.other_y - ep.req_y])
    if ep.end == "dest":
        od_line = -od_line               # origin -> destination
    cos_angle = heading @ od_line / (np.linalg.norm(heading) * np.linalg.norm(od_line))
    angle_deg = math.degrees(math.acos(np.clip(cos_angle, -1, 1)))
    heading_class = ("toward" if angle_deg <= TOWARD_MAX_DEG else
                     "away" if angle_deg >= AWAY_MIN_DEG else "sideways")
    to_req = np.array([ep.req_x - start[0], ep.req_y - start[1]])
    cross = heading[0] * to_req[1] - heading[1] * to_req[0]
    return heading_class, ("left" if cross > 0 else "right")


def profile(endpoints_df, ways_df, segments_df, to_metric):
    geoms = segment_geometry(segments_df, to_metric)
    way_ids = segments_df.way_id.to_numpy()
    tree = shapely.STRtree(geoms)
    req_points = shapely.points(endpoints_df.req_x.to_numpy(), endpoints_df.req_y.to_numpy())
    g_points = shapely.points(endpoints_df.g_x.to_numpy(), endpoints_df.g_y.to_numpy())
    req_near = near_ways(req_points, tree, geoms, way_ids, SEARCH_RADIUS_M)
    g_near = near_ways(g_points, tree, geoms, way_ids, UNMATCHED_M + AMBIGUOUS_M)
    attrs = ways_df.to_dict("index")

    rows = []
    for i, ep in enumerate(endpoints_df.itertuples(index=False)):
        way_id, status = google_way(ep.route_xy, g_near[i], tree, geoms, way_ids)
        req_ways, req_dists = req_near[i]
        out = dict(draw_no=ep.draw_no, end=ep.end, status=status,
                   offset_m=math.hypot(ep.g_x - ep.req_x, ep.g_y - ep.req_y))
        if len(req_ways):
            out.update({f"nearest_{k}": v for k, v in attrs[req_ways[0]].items()},
                       nearest_way=req_ways[0], nearest_dist_m=req_dists[0])
        if status == "matched":
            out.update({f"google_{k}": v for k, v in attrs[way_id].items()}, google_way=way_id)
            google_dist = req_dists[req_ways == way_id]
            out["google_dist_m"] = google_dist[0] if len(google_dist) else np.nan
            out["took_nearest"] = bool(len(google_dist) and google_dist[0] - req_dists[0] <= NEAREST_TIE_M)
            out["heading"], out["side"] = travel_geometry(ep)
        rows.append(out)
    return pd.DataFrame(rows)


def shares(df, column):
    """Count and share of each value of column, per end and both ends."""
    counts = pd.crosstab(df[column], df.end).reindex(columns=list(ENDS), fill_value=0)
    counts["both"] = counts.sum(axis=1)
    table = counts.join(counts.div(counts.sum()).add_suffix("_share"))
    return table.sort_values("both", ascending=False)


def took_nearest_rate(df, column):
    """When the nearest road has this value of column: how often Google took it, per end."""
    grouped = df.groupby([f"nearest_{column}", "end"]).took_nearest.agg(["size", "mean"]).unstack("end")
    grouped.columns = [f"{stat}_{end}" for stat, end in grouped.columns]
    return grouped.sort_values([c for c in grouped.columns if c.startswith("size")], ascending=False)


def report(results_df):
    print(f"\nGoogle's point matched to an OSM vehicle road: {results_df.status.value_counts().to_dict()}")
    matched_df = results_df[results_df.status == "matched"]
    show = dict(float_format=lambda v: f"{v:.3f}")

    print("\n=== A. The roads Google snaps to (matched endpoints) ===")
    for column in ("google_road_class", "google_highway", "google_service", "google_access_group",
                   "google_is_oneway", "google_in_drive_graph", "google_is_named"):
        print(f"\n{column}:\n{shares(matched_df, column).to_string(**show)}")
    service_df = matched_df[matched_df.google_highway == "service"]
    print(f"\nservice roads Google used, subtype x access:\n"
          f"{pd.crosstab(service_df.google_service, [service_df.end, service_df.google_access_group])}")

    print("\n=== B. Baseline: the nearest road to the requested point, same endpoints ===")
    for column in ("nearest_road_class", "nearest_service", "nearest_access_group", "nearest_in_drive_graph"):
        print(f"\n{column}:\n{shares(matched_df, column).to_string(**show)}")

    print("\n=== C. When the nearest road is of a type, how often Google takes it ===")
    for column in ("road_class", "service", "access_group", "is_oneway", "is_named"):
        print(f"\nnearest {column}:\n{took_nearest_rate(matched_df, column).to_string(**show)}")
    nearest_service_df = matched_df[matched_df.nearest_highway == "service"]
    print(f"\nnearest is a service road: subtype x access, share Google took it (both ends):\n"
          f"{nearest_service_df.pivot_table(index='nearest_service', columns='nearest_access_group', values='took_nearest', aggfunc=['size', 'mean']).to_string(**show)}")

    print("\n=== D. Direction and side of travel ===")
    for column in ("heading", "side"):
        print(f"\n{column}:\n{shares(matched_df.dropna(subset=[column]), column).to_string(**show)}")
    for flag in ("took_nearest", "google_is_oneway"):
        print(f"\nside by {flag}:\n{pd.crosstab([matched_df.end, matched_df[flag]], matched_df.side, normalize='index').to_string(**show)}")
    print(f"\nheading by took_nearest:\n{pd.crosstab([matched_df.end, matched_df.took_nearest], matched_df.heading, normalize='index').to_string(**show)}")

    print("\n=== E. Distance from requested point to Google's point (m), by Google's road class ===")
    print(matched_df.groupby(["end", "google_road_class"]).offset_m.quantile(list(OFFSET_QUANTILES))
          .unstack().round(1).to_string())
    unmatched_df = results_df[results_df.status == "unmatched"]
    print(f"\nunmatched (no OSM vehicle road within {UNMATCHED_M} m of Google's point): "
          f"{unmatched_df.end.value_counts().to_dict()}; nearest road to the requested point there: "
          f"{unmatched_df.nearest_road_class.value_counts().to_dict()}")


def main():
    tee = Tee()
    sys.stdout = tee
    try:
        print(f"{DIAGNOSTIC_NAME}, run {RUN_DATE}. Reads frozen Routes responses and the frozen OSM extract; "
              f"no API calls.")
        to_metric = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
        endpoints_df = load_endpoints(to_metric)
        ways_df, segments_df = read_segments(endpoints_df)
        print(f"ways: {len(ways_df):,}, segments: {len(segments_df):,}")
        results_df = profile(endpoints_df, ways_df, segments_df, to_metric)
        results_df.to_csv(ENDPOINTS_PATH, index=False)
        print(f"Saved {ENDPOINTS_PATH}")
        with pd.option_context("display.width", 220, "display.max_columns", 30):
            report(results_df)
    finally:
        sys.stdout = tee.stdout
        LOG_PATH.write_text("".join(tee.lines), encoding="utf-8")
        print(f"Saved {LOG_PATH}")


if __name__ == "__main__":
    main()
