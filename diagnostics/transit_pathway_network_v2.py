"""Pathways network v2: platform stops moved onto their stubs; do trips through every pathway platform use the pathways?

Claim under test (concepts/transit.md TRN-13 (f); DESIGN.md Q23; user 2026-10-19: pathways to be implemented): in the
v1 network (transit_pathway_network.py) R5 linked one platform stop (Holmesglen 8766) to an OSM way 11 mm away
instead of its stub, so it bypassed its pathways (transit_pathway_residual_map.py). The fix (user OK, autonomous
session 2026-10-19): move every hub platform stop, in a copy of the train feed, to the far end of a STUB_M stub drawn
away from the nearest street, so the stop is 0 m from its stub and metres from anything else. Where the pipeline
would rely on it: the pathways network behind transit bands 1-2 (SCR-1, RCH-1).

Network: as v1 (spurs, entrance links, hub -> hub spurs; see transit_pathway_network.py), except the stub: STUB_M
long, in the one of STUB_DIRECTIONS directions whose far end is furthest from any walkable, linkable street way;
the stop goes to that far end (7-decimal coordinates, as the OSM node). Clearance (far end to nearest street) saved.
  Clearance counts platform ways too (railway / public_transport / highway = platform), which R5 can link to with no
  walkable highway tag: Holmesglen's 11 mm way is railway=platform (first v2 build missed it; rebuilt, same day).

Validation (Claude's rules, written before any result; every station, no sampling: 224 stations, ~585 platforms):
  A link (exact): the street vertex R5 assigned to each hub platform stop (TransitLayer.streetVertexForStop, across
    any LINK edges) lies on that platform's own stub way and nothing else. Bar: all. A fail stops the rerun.
  B walk (r5py DetailedItineraries, walk-only): from each entrance to each of its platform stops and back. The time
    must lie in [min over the station's entrances of spur + stub - tol, this entrance's spur + stub + tol] (a route
    under the lower end skipped every spur; one over the upper end didn't take its own). Bar: >= VALIDATE_SHARE.
  C transit (r5py DetailedItineraries, transit + walk, 08:00, r5py's 10-min window): per hub platform, from the
    entrance with the shortest spur to the parent station of the stop TRIP_STOPS_AHEAD calls down the line on the
    first trip after 08:00. Options that board at a platform of the origin station must have an access walk >= min
    over the station's entrances of spur + stub to that platform - tol. Bar: >= VALIDATE_SHARE of such options;
    options boarding elsewhere or walking only are counted. Access legs only (r5py's egress walk is off: T7 (e)).
Rerun: as v1 (transit_band_metric's three calls per pair; the scorers with `--network=pathways_v2`); `diff` vs v1
  and vs the 2026-10-18 runs. Expected: only pairs through Holmesglen 8766 move (the rest is the same network).

Conclusion (run 2026-10-19, second autonomous session; Claude's rules, set before results): the fix works, and every
  pathway platform is used. Both releases (586 / 578 hub platform stops, 224 / 225 stations, no sampling):
  A link 586/586 and 578/578 on their own stub only (PASS); B walk 4,318/4,318 and 4,282/4,282 inside [min spur,
  own spur] + stub (PASS; median 0.7 s under own spur + stub); C transit 22,439/22,439 and 22,397/22,397 boarding
  options with access >= min spur + stub - 15 s (PASS; median +2.3 s; 481 / 482 of 489 agents board at their station).
  Stage 1 (no-wait plain, k = 2): zones pass; false 10 4/294, lost 20 8/248 (upper 0.062), false 20 19/503 (upper
  0.058): fail, not severe, not concentrated (recorded cost). vs v1: 20-37 pairs per release change (mostly +1 min,
  the stub), 1 band call, 1 miss fixed (train 12473, R5 had ridden a train 16 -> 23 min); Holmesglen sides 15024 /
  20738 now walk through the pathways. vs no pathways: misses 35 -> 31 (fixed 5, created 1: second 43620, as v1).
  Run history (kept, renamed): build1 ignored railway=platform ways in the stub clearance (Holmesglen's 11 mm way
  is railway=platform), rebuilt; the first validation ("wrongfeed") failed A 0/586 and had 3 below-floor agents
  because r5py's WorkingCopy caches inputs by file name and never refreshes them: R5 had read the Oct 14 cached
  ptv_metro_train.zip, not the moved feed. Every feed now has a unique name and load_network stops on a stale copy
  (check_working_copies). The same cache bug made every earlier "release 20261016" run use the 2026-10-09 feeds:
  measured here with a correct no-pathways baseline, it changes 1 of 2,210 pairs by 1 min and no band call.

Inputs (read only): as transit_pathway_network.py. Self-contained (CLAUDE.md D1). No API calls.
Usage: `python transit_pathway_network_v2.py build`, `... validate 20261009`, `... validate 20261016`, `... route
20261009`, `... route 20261016` (one network per process), the two scorers with `--network=pathways_v2`, then
`... diff`. Own-date scoring (TRN-13, user 2026-10-20): `... route 20261009 --own-date`, `... route 20261016
--own-date`, `... own_check`, then the two scorers with `--network=pathways_v2 --date=own`. Own-date result
(2026-10-20): own_check PASS (2026-10-21 pairs 260 / 260 and 221 / 221 identical); stage 1 verdicts unchanged
(transit_hard_miss_range.py, own-date conclusion). Saved data is reused when
present; results carry the run date.
"""
import datetime
import heapq
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
CLEANED_DIRS = {"20261009": PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned",
                "20261016": DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016"}
RELEASES = list(CLEANED_DIRS)
NAME = "transit_pathway_network_v2"
V1_NAME = "transit_pathway_network"
PATHWAY_CHECK_NAME = "transit_pathway_check"
BAND_METRIC_NAME = "transit_band_metric"
OLD_RUN_DATE = "20261018"                      # the runs this one is compared with
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
RESERVE_PATH = SUBJECT_DIR / f"transit_pairs_reserve_{FILE_TAG}.csv"
TOPUP_PATH = SUBJECT_DIR / f"transit_pairs_topup_{FILE_TAG}.csv"
TOPUP_SELECTION_PATH = SUBJECT_DIR / f"transit_topup_selection_{FILE_TAG}.csv"
SECOND_ROUTES_PATH = SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv"
GOOGLE_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.csv",        # departure_local: each pair's own date
                "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.csv",
                "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.csv",
                "test": SUBJECT_DIR / f"transit_google_{FILE_TAG}.csv",         # departure_local only (the date)
                "test_ext": SUBJECT_DIR / f"transit_google_test_ext_20261016_{FILE_TAG}.csv"}
TEST_EXT_PATH = SUBJECT_DIR / f"transit_pairs_test_ext_{FILE_TAG}.csv"       # config.TRANSIT_TEST_EXT_PAIRS_PATH

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_band_metric.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as transit_band_metric.py
SINGLE_PERCENTILE = 49                         # as transit_band_metric.py (r5py renames a lone p50)
WALK_SPEED_KMH = 4.16                          # config.WALK_SPEED_KMH
BOARD_SLACK_MIN = 1                            # as transit_band_metric.py
TRAIN_HALF = "train"
TEST_HALF = "test"
SET_RELEASE = {"train": "20261009", "second": "20261016", "topup": "20261016"}
TEST_SET_RELEASE = {"test": "20261009", "test_ext": "20261016"}   # TRN-15: test half on 2026-10-09, extension on 2026-10-16
SECONDS_PER_MIN = 60
MIN_PER_HOUR = 60
SECONDS_PER_HOUR = 3600
M_PER_KM = 1000

# --- network build (Claude) ------------------------------------------------------------------------
ENTRANCE_TYPE = "2"
PLATFORM_TYPES = ["0", ""]
LINK_RADIUS_M = 300                            # as R5's first stop-link radius
SNAP_M = 0.5                                   # reuse a street node this close instead of splicing
STUB_M = 2.0                                   # v2: the stop sits at the far end (v1: 1 m, stop at the hub)
STUB_DIRECTIONS = 16
ZIGZAG_TOOTH_MIN_M = 20                        # straight run per tooth at most ...
ZIGZAG_AMPLITUDE_MAX_M = 30                    # ... and sideways reach at most this
GRID_DEG = 0.004                               # candidate-street grid cell (~350-450 m)
NEW_NODE_ID_BASE = 50_000_000_000              # above any OSM id in the extract (checked at build)
NEW_WAY_ID_BASE = 9_000_000_000
TAG_SOURCE = ("platica", "pathway")
WALKABLE_HIGHWAYS = {"footway", "path", "pedestrian", "steps", "living_street", "residential", "service",
                     "unclassified", "tertiary", "tertiary_link", "secondary", "secondary_link", "primary",
                     "primary_link", "trunk", "trunk_link", "track", "cycleway", "road", "corridor"}
NO_ACCESS = {"no", "private"}
PLATFORM_KEYS = ["railway", "public_transport", "highway"]   # "=platform": counted for the stub's clearance only
NOT_LINKABLE = [("tunnel", "yes"), ("covered", "yes")]     # R5 TypeOfEdgeLabeler (motorway not in the set above)
METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON_EQUATOR = 111_320.0
GTFS_ENCODING = "utf-8-sig"

# --- build check and diff (Claude, set before any result) ------------------------------------------
CHECK_TOLERANCE_S = 15
VALIDATE_SHARE = 0.99
TRIP_STOPS_AHEAD = 2
AGENT_DEPARTURE = datetime.time(8, 0)
PLAIN_NO_WAIT = "no-wait plain (reported)"
WALK_SPEED_MS = WALK_SPEED_KMH * M_PER_KM / SECONDS_PER_HOUR


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def derived_pbf_path(release):
    return DIAGNOSTIC_DATA_DIR / f"{NAME}_osm_{release}.osm.pbf"


def local_xy(lat, lon, lat0, lon0):
    return ((np.asarray(lon) - lon0) * METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0)),
            (np.asarray(lat) - lat0) * METRES_PER_DEG_LAT)


def from_xy(x, y, lat0, lon0):
    return lat0 + y / METRES_PER_DEG_LAT, lon0 + x / (METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0)))


# --- pathway times ---------------------------------------------------------------------------------
def shortest_from(edges, source):
    best = {source: 0.0}
    queue = [(0.0, source)]
    while queue:
        cost, node = heapq.heappop(queue)
        if cost > best[node]:
            continue
        for neighbour, time_s in edges.get(node, []):
            if neighbour not in best or cost + time_s < best[neighbour]:
                best[neighbour] = cost + time_s
                heapq.heappush(queue, (cost + time_s, neighbour))
    return best


def spur_table(release):
    """Hubs (platform coordinates), entrances, and spur times entrance -> hub and hub -> hub, in seconds."""
    with zipfile.ZipFile(CLEANED_DIRS[release] / f"{TRAIN_FEED}.zip") as gtfs_zip:
        stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype=str, encoding=GTFS_ENCODING)
        pathways_df = pd.read_csv(gtfs_zip.open("pathways.txt"), dtype={"from_stop_id": str, "to_stop_id": str},
                                  encoding=GTFS_ENCODING)
        used = set(pd.read_csv(gtfs_zip.open("stop_times.txt"), dtype=str, usecols=["stop_id"],
                               encoding=GTFS_ENCODING).stop_id)
    stops_df["stop_lat"] = stops_df.stop_lat.astype(float)
    stops_df["stop_lon"] = stops_df.stop_lon.astype(float)
    forward, backward = {}, {}
    for row in pathways_df.itertuples():
        pairs = [(row.from_stop_id, row.to_stop_id)] + ([(row.to_stop_id, row.from_stop_id)] if row.is_bidirectional else [])
        for start, end in pairs:
            forward.setdefault(start, []).append((end, float(row.traversal_time)))
            backward.setdefault(end, []).append((start, float(row.traversal_time)))
    has_pathway = set(pathways_df.from_stop_id) | set(pathways_df.to_stop_id)
    entrances_df = stops_df[stops_df.location_type == ENTRANCE_TYPE]
    platforms_df = stops_df[stops_df.stop_id.isin(used) & stops_df.location_type.fillna("").isin(PLATFORM_TYPES)
                            & stops_df.stop_id.isin(has_pathway) & stops_df.parent_station.isin(entrances_df.parent_station)].copy()
    platforms_df["hub"] = platforms_df.stop_lat.round(7).astype(str) + "," + platforms_df.stop_lon.round(7).astype(str)
    entrance_rows, hub_rows = [], []
    for platform in platforms_df.itertuples():
        out_s = shortest_from(forward, platform.stop_id)      # platform -> x
        in_s = shortest_from(backward, platform.stop_id)      # x -> platform
        for entrance in entrances_df[entrances_df.parent_station == platform.parent_station].itertuples():
            if entrance.stop_id in in_s and entrance.stop_id in out_s:
                entrance_rows.append({"hub": platform.hub, "platform_id": platform.stop_id, "entrance_id": entrance.stop_id,
                                      "in_s": in_s[entrance.stop_id], "out_s": out_s[entrance.stop_id]})
        for other in platforms_df[(platforms_df.parent_station == platform.parent_station)
                                  & (platforms_df.hub > platform.hub)].itertuples():
            if other.stop_id in in_s and other.stop_id in out_s:
                hub_rows.append({"hub": platform.hub, "other_hub": other.hub,
                                 "time_s": (in_s[other.stop_id] + out_s[other.stop_id]) / 2})
    entrance_spurs = pd.DataFrame(entrance_rows)
    entrance_spurs["time_s"] = (entrance_spurs.in_s + entrance_spurs.out_s) / 2
    entrance_spurs = entrance_spurs.sort_values("time_s").drop_duplicates(["hub", "entrance_id"])
    hub_spurs = pd.DataFrame(hub_rows).sort_values("time_s").drop_duplicates(["hub", "other_hub"])
    hubs = platforms_df.drop_duplicates("hub").set_index("hub")[["stop_lat", "stop_lon"]]
    entrances = entrances_df.set_index("stop_id")[["stop_lat", "stop_lon"]]
    counts = {"platforms used": int(stops_df.stop_id.isin(used).sum()), "platforms with hub": len(platforms_df),
              "hubs": len(hubs), "entrance spurs": len(entrance_spurs), "hub spurs": len(hub_spurs),
              "asymmetric > 30 s": int(((entrance_spurs.in_s - entrance_spurs.out_s).abs() > 30).sum())}
    return hubs, entrances, entrance_spurs, hub_spurs, counts


# --- OSM -------------------------------------------------------------------------------------------
def is_walkable_linkable(tags):
    if tags.get("highway") not in WALKABLE_HIGHWAYS or tags.get("area") == "yes":
        return False
    if any(tags.get(key) == value for key, value in NOT_LINKABLE):
        return False
    if tags.get("foot") in NO_ACCESS:
        return False
    return not (tags.get("access") in NO_ACCESS and tags.get("foot") not in {"yes", "designated", "permissive"})


def candidate_ways(points_lat, points_lon):
    """Walkable, linkable ways with a node in a grid cell next to any point: {way_id: (node_ids, lats, lons)}."""
    import osmium
    cells = set()
    for lat, lon in zip(points_lat, points_lon):
        row, col = math.floor(lat / GRID_DEG), math.floor(lon / GRID_DEG)
        cells |= {(row + i, col + j) for i in (-1, 0, 1) for j in (-1, 0, 1)}
    ways, max_ids = {}, {"node": 0, "way": 0}
    for obj in osmium.FileProcessor(str(PBF_PATH)).with_locations():
        if obj.is_node():
            max_ids["node"] = max(max_ids["node"], obj.id)
            continue
        if not obj.is_way():
            continue
        max_ids["way"] = max(max_ids["way"], obj.id)
        tags = dict(obj.tags)
        is_walk = is_walkable_linkable(tags)
        if not (is_walk or is_platform_way(tags)):
            continue
        if not all(node.location.valid() for node in obj.nodes):
            continue                                   # cut by the extract's edge: never spliced
        refs = [(node.ref, node.lat, node.lon) for node in obj.nodes]
        if len(refs) < 2 or not any((math.floor(lat / GRID_DEG), math.floor(lon / GRID_DEG)) in cells for _, lat, lon in refs):
            continue
        ways[obj.id] = ([ref for ref, _, _ in refs], np.array([lat for _, lat, _ in refs]), np.array([lon for _, _, lon in refs]), is_walk)
    return ways, max_ids


def is_platform_way(tags):
    """Platform ways R5 can link to although they carry no walkable highway tag (v2: Holmesglen's railway=platform)."""
    is_platform = any(tags.get(key) == "platform" for key in PLATFORM_KEYS)
    return is_platform and not any(tags.get(key) == value for key, value in NOT_LINKABLE)


def segment_table(ways, is_walk_only):
    """Flat arrays of every candidate segment (walkable ways only, or platform ways too): way id, index, end points."""
    way_ids, indices, lat1, lon1, lat2, lon2 = [], [], [], [], [], []
    for way_id, (_, lats, lons, is_walk) in ways.items():
        if is_walk_only and not is_walk:
            continue
        n_segments = len(lats) - 1
        way_ids.append(np.full(n_segments, way_id))
        indices.append(np.arange(n_segments))
        lat1.append(lats[:-1]), lon1.append(lons[:-1]), lat2.append(lats[1:]), lon2.append(lons[1:])
    return {name: np.concatenate(parts) for name, parts in
            [("way_id", way_ids), ("index", indices), ("lat1", lat1), ("lon1", lon1), ("lat2", lat2), ("lon2", lon2)]}


def nearest_splice(lat, lon, segments):
    """Nearest point on any candidate segment: (distance_m, way_id, segment index, t in [0, 1], point lat, lon)."""
    is_near = ((np.minimum(segments["lat1"], segments["lat2"]) <= lat + GRID_DEG)
               & (np.maximum(segments["lat1"], segments["lat2"]) >= lat - GRID_DEG)
               & (np.minimum(segments["lon1"], segments["lon2"]) <= lon + GRID_DEG)
               & (np.maximum(segments["lon1"], segments["lon2"]) >= lon - GRID_DEG))
    if not is_near.any():
        return (np.inf, None, None, None, None, None)
    x1, y1 = local_xy(segments["lat1"][is_near], segments["lon1"][is_near], lat, lon)
    x2, y2 = local_xy(segments["lat2"][is_near], segments["lon2"][is_near], lat, lon)
    dx, dy = x2 - x1, y2 - y1
    length2 = dx ** 2 + dy ** 2
    t = np.clip(-(x1 * dx + y1 * dy) / np.where(length2 > 0, length2, 1), 0, 1)
    px, py = x1 + t * dx, y1 + t * dy
    distance = np.hypot(px, py)
    i = int(np.argmin(distance))
    point_lat, point_lon = from_xy(px[i], py[i], lat, lon)
    return (float(distance[i]), int(segments["way_id"][is_near][i]), int(segments["index"][is_near][i]), float(t[i]),
            point_lat, point_lon)


def zigzag(lat_a, lon_a, lat_b, lon_b, length_m):
    """Intermediate points so the polyline a -> b is length_m long (straight if length_m <= the straight line)."""
    bx, by = local_xy(lat_b, lon_b, lat_a, lon_a)
    straight = float(np.hypot(bx, by))
    if length_m <= straight:
        return [], straight, True
    n_teeth = max(1, math.ceil(straight / ZIGZAG_TOOTH_MIN_M), math.ceil(length_m / (2 * ZIGZAG_AMPLITUDE_MAX_M)))
    half_base = straight / (2 * n_teeth)
    amplitude = math.sqrt(max((length_m / (2 * n_teeth)) ** 2 - half_base ** 2, 0))
    ux, uy = (bx / straight, by / straight) if straight > 0 else (1.0, 0.0)
    nx, ny = -uy, ux
    points = []
    for tooth in range(n_teeth):
        along = (2 * tooth + 1) * half_base
        side = 1 if tooth % 2 == 0 else -1
        points.append(from_xy(ux * along + nx * amplitude * side, uy * along + ny * amplitude * side, lat_a, lon_a))
        if tooth < n_teeth - 1:
            points.append(from_xy(ux * 2 * (tooth + 1) * half_base, uy * 2 * (tooth + 1) * half_base, lat_a, lon_a))
    return points, straight, False


def polyline_m(lats, lons):
    x, y = local_xy(lats, lons, lats[0], lons[0])
    return float(np.sum(np.hypot(np.diff(x), np.diff(y))))


def plan_release(release, ways, segments, clearance_segments, id_counter):
    """New nodes, new ways and way splices for one release; plus the spur table and counts."""
    hubs, entrances, entrance_spurs, hub_spurs, counts = spur_table(release)
    new_nodes, new_ways, splices = [], [], {}     # splices: way_id -> list of (segment index, t, node id)
    node_of = {}

    def add_node(lat, lon):
        id_counter["node"] += 1
        new_nodes.append((id_counter["node"], lat, lon))
        return id_counter["node"]

    def add_way(node_ids, tags):
        id_counter["way"] += 1
        new_ways.append((id_counter["way"], node_ids, {**tags, TAG_SOURCE[0]: TAG_SOURCE[1]}))

    link_rows = []
    for entrance_id in entrance_spurs.entrance_id.unique():
        lat, lon = entrances.loc[entrance_id]
        distance_m, way_id, segment, t, point_lat, point_lon = nearest_splice(lat, lon, segments)
        link_rows.append({"entrance_id": entrance_id, "link_m": distance_m})
        if way_id is None or distance_m > LINK_RADIUS_M:
            continue
        refs, lats, lons, _ = ways[way_id]
        end_x, end_y = local_xy([lats[segment], lats[segment + 1]], [lons[segment], lons[segment + 1]], point_lat, point_lon)
        end_distance = np.hypot(end_x, end_y)
        if end_distance.min() <= SNAP_M:
            street_node = refs[segment + int(np.argmin(end_distance))]
        else:
            street_node = add_node(point_lat, point_lon)
            splices.setdefault(way_id, []).append((segment, t, street_node))
        entrance_node = add_node(lat, lon)
        add_way([street_node, entrance_node], {"highway": "footway"})
        node_of[entrance_id] = entrance_node
    hub_rows = []
    for hub, (lat, lon) in hubs.iterrows():
        node_of[hub] = add_node(lat, lon)
        street_m = nearest_splice(lat, lon, clearance_segments)[0]
        best = None
        for k in range(STUB_DIRECTIONS):
            angle = 2 * math.pi * k / STUB_DIRECTIONS
            end_lat, end_lon = from_xy(STUB_M * math.cos(angle), STUB_M * math.sin(angle), lat, lon)
            end_lat, end_lon = round(end_lat, 7), round(end_lon, 7)
            clearance_m = nearest_splice(end_lat, end_lon, clearance_segments)[0]
            if best is None or clearance_m > best[0]:
                best = (clearance_m, end_lat, end_lon)
        clearance_m, stub_lat, stub_lon = best
        add_way([node_of[hub], add_node(stub_lat, stub_lon)], {"highway": "footway"})
        hub_rows.append({"hub": hub, "hub_lat": lat, "hub_lon": lon, "stub_way_id": id_counter["way"], "stop_lat": stub_lat,
                         "stop_lon": stub_lon, "hub_street_m": street_m, "stop_street_m": clearance_m})
    hubs_df = pd.DataFrame(hub_rows)
    spur_rows = []
    for kind, spurs, start_column, end_column in [("entrance", entrance_spurs, "entrance_id", "hub"),
                                                  ("hub", hub_spurs, "hub", "other_hub")]:
        for spur in spurs.itertuples():
            start, end = getattr(spur, start_column), getattr(spur, end_column)
            if start not in node_of:
                spur_rows.append({"kind": kind, "start": start, "end": end, "time_s": spur.time_s, "status": "no street link"})
                continue
            start_lat, start_lon = (entrances.loc[start] if kind == "entrance" else hubs.loc[start])
            end_lat, end_lon = hubs.loc[end]
            target_m = spur.time_s * WALK_SPEED_MS
            points, straight_m, is_straight = zigzag(start_lat, start_lon, end_lat, end_lon, target_m)
            node_ids = [node_of[start]] + [add_node(lat, lon) for lat, lon in points] + [node_of[end]]
            add_way(node_ids, {"highway": "footway", "tunnel": "yes"})
            lats = [start_lat] + [p[0] for p in points] + [end_lat]
            lons = [start_lon] + [p[1] for p in points] + [end_lon]
            spur_rows.append({"kind": kind, "start": start, "end": end, "time_s": spur.time_s, "target_m": target_m,
                              "straight_m": straight_m, "drawn_m": polyline_m(np.array(lats), np.array(lons)),
                              "status": "straight (time shorter)" if is_straight else "ok"})
    spurs_df = pd.DataFrame(spur_rows)
    links_df = pd.DataFrame(link_rows)
    counts.update({"entrances used": len(links_df), "entrances linked": int((links_df.link_m <= LINK_RADIUS_M).sum()),
                   "link m median": round(float(links_df.link_m.median()), 1), "link m p95": round(float(links_df.link_m.quantile(0.95)), 1),
                   "spurs by status": {f"{kind} {status}": int(n) for (kind, status), n in spurs_df.groupby(["kind", "status"]).size().items()},
                   "drawn vs target max abs m": round(float((spurs_df.drawn_m - spurs_df.target_m)[spurs_df.status == "ok"].abs().max()), 3),
                   "ways spliced": len(splices), "new nodes": len(new_nodes), "new ways": len(new_ways),
                   "stop clearance m min": round(float(hubs_df.stop_street_m.min()), 2),
                   "stop clearance m median": round(float(hubs_df.stop_street_m.median()), 2),
                   "hub street m < 0.5": int((hubs_df.hub_street_m < 0.5).sum())})
    return new_nodes, new_ways, splices, spurs_df, counts, hubs_df


def spliced_nodes(refs, splice_list):
    by_segment = {}
    for segment, t, node_id in splice_list:
        by_segment.setdefault(segment, []).append((t, node_id))
    out = []
    for i, ref in enumerate(refs):
        out.append(ref)
        out += [node_id for _, node_id in sorted(by_segment.get(i, []))]
    return out


def build():
    """Both releases' derived extracts from one read of the original."""
    import osmium
    todo = [release for release in RELEASES if not derived_pbf_path(release).exists()]
    if not todo:
        print("derived extracts exist (reused):", [derived_pbf_path(r).name for r in RELEASES])
        return
    run_date = f"{datetime.date.today():%Y%m%d}"
    started = datetime.datetime.now()
    entrance_points = []
    for release in todo:
        hubs, entrances, entrance_spurs, _, _ = spur_table(release)
        entrance_points += [entrances.loc[entrance_spurs.entrance_id.unique()], hubs]   # hubs: stub clearance
    points = pd.concat(entrance_points)
    ways, max_ids = candidate_ways(points.stop_lat.to_numpy(), points.stop_lon.to_numpy())
    segments = segment_table(ways, is_walk_only=True)
    clearance_segments = segment_table(ways, is_walk_only=False)
    print(f"pass 1: {len(ways)} candidate ways, {len(segments['index'])} segments; max ids {max_ids}; "
          f"{datetime.datetime.now() - started}", flush=True)
    assert max_ids["node"] < NEW_NODE_ID_BASE and max_ids["way"] < NEW_WAY_ID_BASE, "new id bases collide"
    plans, lines = {}, [f"{NAME} {run_date}: build"]
    for release in todo:
        id_counter = {"node": NEW_NODE_ID_BASE, "way": NEW_WAY_ID_BASE}
        plans[release] = plan_release(release, ways, segments, clearance_segments, id_counter)
        spurs_df, counts, hubs_df = plans[release][3], plans[release][4], plans[release][5]
        spurs_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_spurs_{release}.csv", index=False)
        hubs_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_hubs_{release}.csv", index=False)
        write_moved_feed(release, hubs_df)
        lines.append(f"release {release}: " + json.dumps(counts, default=str))
        print(lines[-1], flush=True)
    writers = {release: osmium.SimpleWriter(str(derived_pbf_path(release))) for release in todo}
    state = {"nodes_flushed": False, "ways_flushed": False}

    def flush_nodes():
        for release, writer in writers.items():
            for node_id, lat, lon in plans[release][0]:
                writer.add_node(osmium.osm.mutable.Node(id=node_id, location=(lon, lat), version=1, tags={}))
        state["nodes_flushed"] = True

    def flush_ways():
        for release, writer in writers.items():
            for way_id, node_ids, tags in plans[release][1]:
                writer.add_way(osmium.osm.mutable.Way(id=way_id, nodes=node_ids, version=1, tags=tags))
        state["ways_flushed"] = True

    try:
        for obj in osmium.FileProcessor(str(PBF_PATH)):
            if obj.is_way() and not state["nodes_flushed"]:
                flush_nodes()
            if obj.is_relation() and not state["ways_flushed"]:
                flush_ways()
            for release, writer in writers.items():
                splices = plans[release][2]
                if obj.is_way() and obj.id in splices:
                    refs = [node.ref for node in obj.nodes]
                    candidate_refs = ways[obj.id][0]
                    assert refs == candidate_refs, f"way {obj.id}: node list differs from pass 1"
                    writer.add_way(obj.replace(nodes=spliced_nodes(refs, splices[obj.id])))
                else:
                    writer.add(obj)
        if not state["nodes_flushed"]:
            flush_nodes()
        if not state["ways_flushed"]:
            flush_ways()
    finally:
        for writer in writers.values():
            writer.close()
    lines.append(f"written {[derived_pbf_path(r).name for r in todo]} in {datetime.datetime.now() - started}")
    print(lines[-1])
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_build_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(lines) + "\n")


# --- pairs (copied from transit_band_metric.py) ----------------------------------------------------
def pairs_of_set(set_name):
    columns = ["draw_no", "origin_lat", "origin_lon", "dest_lat", "dest_lon", "haversine_m", "dep_min_of_day"]
    if set_name in ("train", "test"):
        split_df = pd.read_csv(SPLIT_PATH, usecols=["draw_no", "half"])
        pairs_df = pd.read_csv(PAIRS_PATH, usecols=columns)
        half = TRAIN_HALF if set_name == "train" else TEST_HALF
        return pairs_df[pairs_df.draw_no.isin(split_df.draw_no[split_df.half == half])]
    if set_name == "test_ext":
        return pd.read_csv(TEST_EXT_PATH, usecols=columns)
    if set_name == "second":
        return pd.read_csv(RESERVE_PATH, usecols=columns)
    topup_df = pd.read_csv(TOPUP_PATH, usecols=columns)
    return topup_df[topup_df.draw_no.isin(pd.read_csv(TOPUP_SELECTION_PATH).draw_no)]




# --- moved train feed ------------------------------------------------------------------------------
def moved_feed_path(release):
    """Unique file name: r5py's WorkingCopy caches inputs by file name and never refreshes them (see check_working_copies)."""
    return DIAGNOSTIC_DATA_DIR / f"{NAME}_gtfs_{release}" / f"{TRAIN_FEED}_{NAME}_{release}_moved.zip"


def unique_feed_path(release, feed_name):
    """A copy of a cleaned feed under a name no other release or run shares (made if missing)."""
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_gtfs_{release}" / f"{feed_name}_{NAME}_{release}.zip"
    if not path.exists():
        import shutil
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CLEANED_DIRS[release] / f"{feed_name}.zip", path)
    return path


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (stale copy under the same name)."""
    import hashlib
    from r5py.util.config import Config
    for path in paths:
        cached = Path(Config().CACHE_DIR) / Path(path).name
        if not cached.exists():
            continue
        digests = []
        for candidate in (path, cached):
            with open(candidate, "rb") as file:
                digests.append(hashlib.file_digest(file, "blake2s").hexdigest())
        assert digests[0] == digests[1], f"r5py's cached {cached} differs from {path}: stale working copy"


def write_moved_feed(release, hubs_df):
    """Copy of the cleaned train feed with each hub platform stop at its stub's far end (other files byte for byte)."""
    source = CLEANED_DIRS[release] / f"{TRAIN_FEED}.zip"
    target = moved_feed_path(release)
    target.parent.mkdir(parents=True, exist_ok=True)
    moved = hubs_df.set_index("hub")[["stop_lat", "stop_lon"]]
    with zipfile.ZipFile(source) as source_zip, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as target_zip:
        for member in source_zip.infolist():
            if member.filename != "stops.txt":
                target_zip.writestr(member, source_zip.read(member.filename))
                continue
            stops_df = pd.read_csv(source_zip.open("stops.txt"), dtype=str, encoding=GTFS_ENCODING, keep_default_na=False)
            is_platform = stops_df.location_type.isin(PLATFORM_TYPES)
            hub = (stops_df.stop_lat.astype(float).round(7).astype(str) + "," + stops_df.stop_lon.astype(float).round(7).astype(str))
            is_moved = is_platform & hub.isin(moved.index)
            stops_df.loc[is_moved, "stop_lat"] = [f"{value:.7f}" for value in moved.loc[hub[is_moved], "stop_lat"]]
            stops_df.loc[is_moved, "stop_lon"] = [f"{value:.7f}" for value in moved.loc[hub[is_moved], "stop_lon"]]
            target_zip.writestr("stops.txt", stops_df.to_csv(index=False, lineterminator="\n"))
            print(f"release {release}: moved {int(is_moved.sum())} platform stops onto their stubs -> {target}", flush=True)


def gtfs_paths(release, is_pathways=True):
    return [moved_feed_path(release) if name == TRAIN_FEED and is_pathways else unique_feed_path(release, name)
            for name in FEED_NAMES]


def feeds():
    """Rewrite the moved train feeds from the saved hubs tables and make the unique feed copies (no OSM rebuild)."""
    for release in RELEASES:
        write_moved_feed(release, pd.read_csv(newest(f"{NAME}_2*_hubs_{release}.csv")))
        for name in FEED_NAMES:
            print(unique_feed_path(release, name))


def load_network(release, is_pathways=True):
    sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import
    from r5py import TransportNetwork
    pbf_path = derived_pbf_path(release) if is_pathways else PBF_PATH
    paths = gtfs_paths(release, is_pathways)
    assert pbf_path.exists() and all(path.exists() for path in paths), f"run build and feeds first ({pbf_path.name})"
    check_working_copies([pbf_path] + paths)
    print(f"reusing {pbf_path.name} ({datetime.date.fromtimestamp(pbf_path.stat().st_mtime)}) and {[path.name for path in paths]}",
          flush=True)
    network = TransportNetwork(pbf_path, paths)
    print("covers", WINDOW_DATE, network.transit_layer.covers(WINDOW_DATE), flush=True)
    return network


# --- validation ------------------------------------------------------------------------------------
def share_line(label, is_pass, bar=VALIDATE_SHARE):
    n, k = len(is_pass), int(np.sum(is_pass))
    is_ok = bool(n) and k / n >= bar
    return f"{label}: {k}/{n} = {k / n if n else float('nan'):.4f} (bar {bar}) -> {'PASS' if is_ok else 'FAIL'}", is_ok


def active_services(gtfs_zip):
    weekday = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][WINDOW_DATE.weekday()]
    date_int = int(f"{WINDOW_DATE:%Y%m%d}")
    calendar_df = pd.read_csv(gtfs_zip.open("calendar.txt"), dtype={"service_id": str}, encoding=GTFS_ENCODING)
    services = set(calendar_df.service_id[(calendar_df[weekday] == 1) & (calendar_df.start_date <= date_int)
                                          & (calendar_df.end_date >= date_int)])
    if "calendar_dates.txt" in gtfs_zip.namelist():
        dates_df = pd.read_csv(gtfs_zip.open("calendar_dates.txt"), dtype={"service_id": str}, encoding=GTFS_ENCODING)
        dates_df = dates_df[dates_df.date == date_int]
        services |= set(dates_df.service_id[dates_df.exception_type == 1])
        services -= set(dates_df.service_id[dates_df.exception_type == 2])
    return services


def clock_to_min(series):
    parts = series.str.split(":", expand=True).astype(int)
    return parts[0] * MIN_PER_HOUR + parts[1] + parts[2] / SECONDS_PER_MIN


def validate(release):
    run_date = f"{datetime.date.today():%Y%m%d}"
    import geopandas as gpd
    network = load_network(release)
    import jpype
    from r5py import DetailedItineraries, TransportMode
    java_network = network._transport_network
    street_layer, transit_layer = java_network.streetLayer, java_network.transitLayer
    hubs_df = pd.read_csv(newest(f"{NAME}_2*_hubs_{release}.csv"))
    spurs_df = pd.read_csv(newest(f"{NAME}_2*_spurs_{release}.csv"))
    _, entrances, _, _, _ = spur_table(release)
    with zipfile.ZipFile(moved_feed_path(release)) as gtfs_zip:
        stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype=str, encoding=GTFS_ENCODING)
        services = active_services(gtfs_zip)
        trips_df = pd.read_csv(gtfs_zip.open("trips.txt"), dtype=str, usecols=["trip_id", "service_id"], encoding=GTFS_ENCODING)
        times_df = pd.read_csv(gtfs_zip.open("stop_times.txt"), dtype=str, encoding=GTFS_ENCODING,
                               usecols=["trip_id", "departure_time", "stop_id", "stop_sequence"])
    stops_df["stop_lat"] = stops_df.stop_lat.astype(float)
    stops_df["stop_lon"] = stops_df.stop_lon.astype(float)
    platforms_df = stops_df[stops_df.location_type.fillna("").isin(PLATFORM_TYPES)].copy()
    stop_key = platforms_df.stop_lat.round(7).astype(str) + "," + platforms_df.stop_lon.round(7).astype(str)
    hub_of_stop_key = dict(zip(hubs_df.stop_lat.round(7).astype(str) + "," + hubs_df.stop_lon.round(7).astype(str), hubs_df.hub))
    platforms_df["hub"] = stop_key.map(hub_of_stop_key)
    platforms_df = platforms_df[platforms_df.hub.notna()]
    lines = [f"{NAME} {run_date}: validate {release}; hub platform stops {len(platforms_df)} at {platforms_df.hub.nunique()} "
             f"hubs, {platforms_df.parent_station.nunique()} stations"]

    # A: link
    stop_ids = [str(stop_id) for stop_id in transit_layer.stopIdForIndex]
    wanted = set(platforms_df.stop_id)
    prefixes = {stop_id.split(":", 1)[0] for stop_id in stop_ids}
    train_prefix = max(prefixes, key=lambda prefix: sum(stop_id.startswith(prefix + ":") and stop_id.split(":", 1)[1] in wanted
                                                        for stop_id in stop_ids))
    index_of = {stop_id.split(":", 1)[1]: i for i, stop_id in enumerate(stop_ids) if stop_id.startswith(train_prefix + ":")}
    link_flag = jpype.JClass("com.conveyal.r5.streets.EdgeStore$EdgeFlag").LINK
    stub_of_hub = dict(zip(hubs_df.hub, hubs_df.stub_way_id))

    def way_ids_near(vertex, depth=3):
        """OSM way ids of non-LINK edges at vertex, following LINK edges up to depth hops."""
        found, seen, frontier = set(), {vertex}, [vertex]
        for _ in range(depth):
            next_frontier = []
            for v in frontier:
                edge_lists = [street_layer.outgoingEdges.get(v), street_layer.incomingEdges.get(v)]
                for edge in [edges.get(i) for edges in edge_lists for i in range(edges.size())]:
                    cursor = street_layer.edgeStore.getCursor(int(edge))
                    if cursor.getFlag(link_flag):
                        for w in (int(cursor.getToVertex()), int(cursor.getFromVertex())):
                            if w not in seen:
                                seen.add(w)
                                next_frontier.append(w)
                    else:
                        found.add(int(cursor.getOSMID()))
            frontier = next_frontier
        return found

    link_rows = []
    for platform in platforms_df.itertuples():
        stop_index = index_of.get(platform.stop_id)
        vertex = int(transit_layer.streetVertexForStop.get(stop_index)) if stop_index is not None else -1
        ways = way_ids_near(vertex) if vertex >= 0 else set()
        link_rows.append({"platform_id": platform.stop_id, "stop_name": platform.stop_name, "hub": platform.hub,
                          "stop_index": stop_index, "vertex": vertex, "ways": " ".join(map(str, sorted(ways))),
                          "is_own_stub": ways == {int(stub_of_hub[platform.hub])}})
    link_df = pd.DataFrame(link_rows)
    link_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_validate_link_{release}.csv", index=False)
    line, _ = share_line(f"A link: stop's street vertex on its own stub only (feed prefix '{train_prefix}', unlinked "
                         f"{int((link_df.vertex < 0).sum())})", link_df.is_own_stub, 1.0)
    lines.append(line)
    for row in link_df[~link_df.is_own_stub].itertuples():
        lines.append(f"  not on own stub: {row.platform_id} {row.stop_name} vertex {row.vertex} ways {row.ways}")
    print("\n".join(lines), flush=True)

    # B: walk, entrance <-> platform stop
    spur_s = spurs_df[spurs_df.kind == "entrance"].assign(spur_s=lambda df: df.drawn_m / WALK_SPEED_MS)
    spur_s = spur_s[spur_s.status != "no street link"]
    stub_s = STUB_M / WALK_SPEED_MS
    one_stop = platforms_df.drop_duplicates("hub").set_index("hub")
    walk_df = spur_s.rename(columns={"start": "entrance_id", "end": "hub"})[["entrance_id", "hub", "spur_s"]]
    walk_df = walk_df.merge(walk_df.groupby("hub").spur_s.min().rename("min_spur_s"), on="hub")
    walk_df["entrance_lat"] = entrances.loc[walk_df.entrance_id, "stop_lat"].to_numpy()
    walk_df["entrance_lon"] = entrances.loc[walk_df.entrance_id, "stop_lon"].to_numpy()
    walk_df["stop_lat"] = one_stop.loc[walk_df.hub, "stop_lat"].to_numpy()
    walk_df["stop_lon"] = one_stop.loc[walk_df.hub, "stop_lon"].to_numpy()
    walk_df = pd.concat([walk_df.assign(direction="in"), walk_df.assign(direction="out")], ignore_index=True)
    is_in = (walk_df.direction == "in").to_numpy()
    origins = gpd.GeoDataFrame({"id": walk_df.index}, crs="EPSG:4326", geometry=gpd.points_from_xy(
        np.where(is_in, walk_df.entrance_lon, walk_df.stop_lon), np.where(is_in, walk_df.entrance_lat, walk_df.stop_lat)))
    destinations = gpd.GeoDataFrame({"id": walk_df.index}, crs="EPSG:4326", geometry=gpd.points_from_xy(
        np.where(is_in, walk_df.stop_lon, walk_df.entrance_lon), np.where(is_in, walk_df.stop_lat, walk_df.entrance_lat)))
    started = datetime.datetime.now()
    di_df = pd.DataFrame(DetailedItineraries(network, origins=origins, destinations=destinations,
                                             departure=datetime.datetime.combine(WINDOW_DATE, datetime.time(12)),
                                             transport_modes=[TransportMode.WALK], speed_walking=WALK_SPEED_KMH))
    walk_df = walk_df.join(di_df.groupby("from_id").travel_time.sum().dt.total_seconds().rename("r5_s"))
    walk_df["low_s"] = walk_df.min_spur_s + stub_s - CHECK_TOLERANCE_S
    walk_df["high_s"] = walk_df.spur_s + stub_s + CHECK_TOLERANCE_S
    walk_df["is_pass"] = (walk_df.r5_s >= walk_df.low_s) & (walk_df.r5_s <= walk_df.high_s)
    walk_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_validate_walk_{release}.csv", index=False)
    line, _ = share_line(f"B walk: entrance <-> platform stop within [min spur, own spur] + stub +-{CHECK_TOLERANCE_S} s "
                         f"({datetime.datetime.now() - started}; no route {int(walk_df.r5_s.isna().sum())})", walk_df.is_pass)
    lines += [line, f"  under (skipped every spur) {int((walk_df.r5_s < walk_df.low_s).sum())}, over (not its own spur) "
                    f"{int((walk_df.r5_s > walk_df.high_s).sum())}; r5 - own spur - stub median "
                    f"{(walk_df.r5_s - walk_df.spur_s - stub_s).median():+.1f} s"]
    for direction, group in walk_df.groupby("direction"):
        lines.append("  " + share_line(f"direction {direction}", group.is_pass)[0])
    print("\n".join(lines[-4:]), flush=True)

    # C: transit, best entrance -> board at the station -> TRIP_STOPS_AHEAD calls down the line
    times_df = times_df.merge(trips_df[trips_df.service_id.isin(services)], on="trip_id")
    times_df["dep_min"] = clock_to_min(times_df.departure_time)
    times_df["stop_sequence"] = times_df.stop_sequence.astype(int)
    agent_min = AGENT_DEPARTURE.hour * MIN_PER_HOUR + AGENT_DEPARTURE.minute
    station_of = stops_df.set_index("stop_id").parent_station
    station_xy = stops_df[stops_df.location_type == "1"].set_index("stop_id")[["stop_lat", "stop_lon"]]
    min_spur_of_hub = walk_df.drop_duplicates("hub").set_index("hub").min_spur_s
    first_calls = times_df[times_df.dep_min >= agent_min].sort_values("dep_min").drop_duplicates("stop_id").set_index("stop_id")
    agent_rows = []
    for hub, platform in one_stop.iterrows():
        hub_spurs = spur_s[spur_s.end == hub]
        if hub_spurs.empty or platform.stop_id not in first_calls.index:
            continue
        best = hub_spurs.loc[hub_spurs.spur_s.idxmin()]
        call = first_calls.loc[platform.stop_id]
        trip = times_df[times_df.trip_id == call.trip_id].sort_values("stop_sequence")
        ahead = trip[trip.stop_sequence > call.stop_sequence].head(TRIP_STOPS_AHEAD)
        if ahead.empty:
            continue
        dest_station = station_of.get(ahead.iloc[-1].stop_id)
        if dest_station not in station_xy.index:
            continue
        agent_rows.append({"hub": hub, "platform_id": platform.stop_id, "station": platform.parent_station,
                           "entrance_id": best.start, "origin_lat": entrances.loc[best.start, "stop_lat"],
                           "origin_lon": entrances.loc[best.start, "stop_lon"], "dest_station": dest_station,
                           "dest_lat": station_xy.loc[dest_station, "stop_lat"], "dest_lon": station_xy.loc[dest_station, "stop_lon"]})
    agents_df = pd.DataFrame(agent_rows)
    origins = gpd.GeoDataFrame({"id": agents_df.index}, crs="EPSG:4326",
                               geometry=gpd.points_from_xy(agents_df.origin_lon, agents_df.origin_lat))
    destinations = gpd.GeoDataFrame({"id": agents_df.index}, crs="EPSG:4326",
                                    geometry=gpd.points_from_xy(agents_df.dest_lon, agents_df.dest_lat))
    print(f"C: {len(agents_df)} agents of {len(one_stop)} hubs; routing", flush=True)
    started = datetime.datetime.now()
    di_df = pd.DataFrame(DetailedItineraries(network, origins=origins, destinations=destinations,
                                             departure=datetime.datetime.combine(WINDOW_DATE, AGENT_DEPARTURE),
                                             transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
                                             speed_walking=WALK_SPEED_KMH))
    elapsed = datetime.datetime.now() - started
    di_df["is_ride"] = di_df.route_id.notna() & (di_df.route_id.astype(str) != "") & (di_df.route_id.astype(str) != "None")
    di_df["travel_s"] = di_df.travel_time.dt.total_seconds()
    hub_of_platform = dict(zip(platforms_df.stop_id, platforms_df.hub))
    option_rows = []
    for (from_id, option), legs in di_df.sort_values("segment").groupby(["from_id", "option"]):
        agent = agents_df.loc[from_id]
        rides = legs[legs.is_ride]
        if rides.empty:
            option_rows.append({"agent": from_id, "option": option, "kind": "walk only"})
            continue
        first_ride = rides.iloc[0]
        access_s = float(legs[(legs.segment < first_ride.segment) & ~legs.is_ride].travel_s.sum())
        board_id = str(first_ride.start_stop_id)
        row = {"agent": from_id, "option": option, "board_id": board_id, "access_s": access_s}
        if station_of.get(board_id) != agent.station:
            option_rows.append({**row, "kind": "boards elsewhere"})
            continue
        board_hub = hub_of_platform.get(board_id)
        floor_s = min_spur_of_hub.get(board_hub, np.nan) + stub_s - CHECK_TOLERANCE_S
        option_rows.append({**row, "kind": "boards at station", "floor_s": floor_s, "is_pass": bool(access_s >= floor_s)})
    options_df = pd.DataFrame(option_rows).merge(agents_df[["hub", "platform_id", "station", "entrance_id", "dest_station"]],
                                                 left_on="agent", right_index=True)
    options_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_validate_transit_{release}.csv", index=False)
    at_station = options_df[options_df.kind == "boards at station"]
    line, _ = share_line(f"C transit: options boarding at the station with access >= min spur + stub - {CHECK_TOLERANCE_S} s "
                         f"({len(agents_df)} agents, {elapsed})", at_station.is_pass.astype(bool))
    agent_boards = options_df.groupby("agent").kind.agg(lambda kinds: "boards at station" in set(kinds))
    lines += [line, f"  options by kind {options_df.kind.value_counts().to_dict()}; agents with an option boarding at "
                    f"their station {int(agent_boards.sum())}/{len(agents_df)}; access - (min spur + stub) median "
                    f"{(at_station.access_s - at_station.floor_s - CHECK_TOLERANCE_S).median():+.1f} s"]
    for row in at_station[~at_station.is_pass.astype(bool)].drop_duplicates("agent").itertuples():
        lines.append(f"  below the floor: {row.platform_id} ({row.station}) access {row.access_s:.0f} s, floor {row.floor_s:.0f} s")
    print("\n".join(lines[-3:]))
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_validate_{release}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(lines) + "\n")


# --- routing ---------------------------------------------------------------------------------------
def own_dates(set_name):
    """Each pair's own date: the date of Google's departure_local (TRN-13, scoring on the own date, user 2026-10-20)."""
    google_df = pd.read_csv(GOOGLE_PATHS[set_name], usecols=["draw_no", "departure_local"])
    return pd.DataFrame({"draw_no": google_df.draw_no, "own_date": pd.to_datetime(google_df.departure_local.str[:10]).dt.date})


def route(release, mode=""):
    """Pathways v2 network; `--baseline`: no pathways (original extract, unique copies of the cleaned feeds);
    `--own-date`: v2 network, each pair routed on its own date instead of WINDOW_DATE (table `routes_owndate`);
    `--test`: as `--own-date` on the test sets (TRN-15; table `routes_test`); only the date of Google's answer is read."""
    run_date = f"{datetime.date.today():%Y%m%d}"
    is_pathways = mode != "--baseline"
    is_test = mode == "--test"
    is_own_date = mode == "--own-date" or is_test
    if is_pathways:
        summary_path = newest(f"{NAME}_2*_validate_{release}_summary.txt")
        assert summary_path is not None, "validate first"
        link_line = [line for line in summary_path.read_text(encoding="utf-8").splitlines() if line.startswith("A link")][0]
        if not link_line.endswith("PASS"):
            print(f"link check failed ({summary_path.name}): no rerun")
            return
    network = load_network(release, is_pathways)
    import geopandas as gpd
    from r5py import TransportMode, TravelTimeMatrix

    def ttm_min(pair, departure, transport_modes, max_time_min):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.origin_lon], [pair.origin_lat]))
        destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=transport_modes, max_time=datetime.timedelta(minutes=max_time_min),
            speed_walking=WALK_SPEED_KMH))
        return matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]

    set_releases = TEST_SET_RELEASE if is_test else SET_RELEASE
    set_names = [name for name, set_release in set_releases.items() if set_release == release]
    pairs_df = pd.concat([pairs_of_set(name).assign(set_name=name) for name in set_names], ignore_index=True)
    if is_own_date:
        dates_df = pd.concat([own_dates(name) for name in set_names], ignore_index=True)
        pairs_df = pairs_df.merge(dates_df, on="draw_no", how="left", validate="one_to_one")
        assert pairs_df.own_date.notna().all(), "pairs without a Google departure date"
        for own_date in sorted(pairs_df.own_date.unique()):
            is_covered = network.transit_layer.covers(own_date)
            print("covers", own_date, is_covered, flush=True)
            assert is_covered, f"release {release} does not cover {own_date}"
    else:
        pairs_df["own_date"] = WINDOW_DATE
    table_tag = "routes_test" if is_test else "routes_owndate" if is_own_date else "routes" if is_pathways else "routes_baseline"
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_{table_tag}_{release}.csv"))
    table_path = saved[-1] if saved else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_{table_tag}_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"release {release}: sets {set_names}, {len(pairs_df)} pairs; table {table_path.name}, "
          f"{len(done)} done, {len(todo_df)} to route", flush=True)
    transit_modes = [TransportMode.TRANSIT, TransportMode.WALK]
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        departure = datetime.datetime.combine(pair.own_date, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))
        row = {"draw_no": pair.draw_no, "set_name": pair.set_name, "release": release,
               **({"own_date": pair.own_date} if is_own_date else {}),
               "stock_min": ttm_min(pair, departure, transit_modes, MAX_TIME_MIN),
               "shifted_min": ttm_min(pair, departure - datetime.timedelta(minutes=BOARD_SLACK_MIN),
                                      transit_modes, MAX_TIME_MIN + BOARD_SLACK_MIN),
               "walk_min": ttm_min(pair, departure, [TransportMode.WALK], MAX_TIME_MIN)}
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % 100 == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


# --- diff ------------------------------------------------------------------------------------------
def diff_against(label, old_routes, old_results_path, old_misses_path, lines):
    lines.append(f"== vs {label}")
    for release in RELEASES:
        old_df = pd.read_csv(old_routes[release])
        new_df = pd.read_csv(newest(f"{NAME}_2*_routes_{release}.csv"))
        both = old_df.merge(new_df, on="draw_no", suffixes=("_old", "_new"))
        parts = []
        for column in ["stock_min", "shifted_min", "walk_min"]:
            change = both[f"{column}_new"].fillna(np.inf) - both[f"{column}_old"].fillna(np.inf)
            change = change[np.isfinite(change)]
            parts.append(f"{column}: changed {int((change != 0).sum())}/{len(both)} (up {int((change > 0).sum())}, down "
                         f"{int((change < 0).sum())}), mean {change.mean():+.3f}")
        lines.append(f"release {release}: " + "; ".join(parts))
    old_results = pd.read_csv(old_results_path)
    new_results = pd.read_csv(newest(f"{NAME}_2*_range_results.csv"))
    merged = old_results.merge(new_results, on=["set_name", "draw_no"], suffixes=("_old", "_new"))
    merged = merged[merged.is_scored_old.astype(bool)]
    old_min, new_min = merged.n_min_old.fillna(np.inf), merged.n_min_new.fillna(np.inf)
    band_old, band_new = np.digitize(old_min, [10.5, 20.5]), np.digitize(new_min, [10.5, 20.5])
    lines.append(f"no-wait: scored {len(merged)}, minutes changed {int((old_min != new_min).sum())}, band calls changed "
                 f"{int((band_old != band_new).sum())} (later {int((band_new > band_old).sum())}, earlier "
                 f"{int((band_new < band_old).sum())})")
    old_misses = pd.read_csv(old_misses_path)
    new_misses = pd.read_csv(newest(f"{NAME}_2*_range_misses.csv"))
    key = ["model", "test", "set_name", "draw_no"]
    for model in [PLAIN_NO_WAIT, "stock 4.16"]:
        old_keys = set(map(tuple, old_misses[old_misses.model == model][key].to_numpy()))
        new_keys = set(map(tuple, new_misses[new_misses.model == model][key].to_numpy()))
        lines.append(f"model {model}: misses {len(old_keys)} -> {len(new_keys)}; fixed {len(old_keys - new_keys)}, created "
                     f"{len(new_keys - old_keys)}, unchanged {len(old_keys & new_keys)}")
        for test in sorted(set(old_misses.test) | set(new_misses.test)):
            old_t, new_t = {k for k in old_keys if k[1] == test}, {k for k in new_keys if k[1] == test}
            lines.append(f"  {test}: {len(old_t)} -> {len(new_t)} (fixed {len(old_t - new_t)}, created {len(new_t - old_t)})")
        for tag, keys_set in [("fixed", old_keys - new_keys), ("created", new_keys - old_keys)]:
            for k in sorted(keys_set, key=lambda item: (item[1], item[2], item[3])):
                row = merged[(merged.set_name == k[2]) & (merged.draw_no == k[3])].iloc[0]
                lines.append(f"    {tag} | {k[1]} | {k[2]} {k[3]}: default {row.default_min_new:.0f}, low {row.low_2_new:.0f}, "
                             f"n_min {row.n_min_old} -> {row.n_min_new}, stock {row.stock_min_old} -> {row.stock_min_new}, "
                             f"walk {row.walk_min_old} -> {row.walk_min_new}")


def routes_diff(label, old_df, new_df, lines):
    """Routing-level change between two tables of the same pairs, and no-wait band calls (N = H - 1 if H < W, else W)."""
    both = old_df.merge(new_df, on="draw_no", suffixes=("_old", "_new"))
    parts = []
    for column in ["stock_min", "shifted_min", "walk_min"]:
        change = both[f"{column}_new"].fillna(np.inf) - both[f"{column}_old"].fillna(np.inf)
        change = change[np.isfinite(change)]
        parts.append(f"{column} changed {int((change != 0).sum())}/{len(both)} (up {int((change > 0).sum())}, down "
                     f"{int((change < 0).sum())}, mean {change.mean():+.3f})")
    calls = {}
    for tag in ("old", "new"):
        shifted, walk = both[f"shifted_min_{tag}"].fillna(np.inf), both[f"walk_min_{tag}"].fillna(np.inf)
        calls[tag] = np.digitize(np.where(shifted < walk, shifted - BOARD_SLACK_MIN, walk), [10.5, 20.5])
    lines.append(f"{label}: " + "; ".join(parts) + f"; no-wait band calls changed {int((calls['old'] != calls['new']).sum())} "
                 f"(later {int((calls['new'] > calls['old']).sum())}, earlier {int((calls['new'] < calls['old']).sum())})")


def diff():
    run_date = f"{datetime.date.today():%Y%m%d}"
    lines = [f"{NAME} {run_date}: diff"]
    release = "20261016"
    stale_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{BAND_METRIC_NAME}_{OLD_RUN_DATE}_routes_{release}.csv")
    baseline_df = pd.read_csv(newest(f"{NAME}_2*_routes_baseline_{release}.csv"))
    v2_df = pd.read_csv(newest(f"{NAME}_2*_routes_{release}.csv"))
    lines.append(f"== release {release}, every table on its own feeds (r5py working-copy fix)")
    routes_diff(f"feed effect, no pathways: 2026-10-09 feeds (stale cache, {OLD_RUN_DATE} runs) -> 2026-10-16 feeds",
                stale_df, baseline_df, lines)
    routes_diff("pathway effect on 2026-10-16 feeds: no pathways -> v2", baseline_df, v2_df, lines)
    v1_routes = {release: sorted(DIAGNOSTIC_DATA_DIR.glob(f"{V1_NAME}_2*_routes_{release}.csv"))[-1] for release in RELEASES}
    diff_against("v1 (pathways, stops not moved)", v1_routes,
                 sorted(DIAGNOSTIC_DATA_DIR.glob(f"{V1_NAME}_2*_range_results.csv"))[-1],
                 sorted(DIAGNOSTIC_DATA_DIR.glob(f"{V1_NAME}_2*_range_misses.csv"))[-1], lines)
    old_routes = {release: DIAGNOSTIC_DATA_DIR / f"{BAND_METRIC_NAME}_{OLD_RUN_DATE}_routes_{release}.csv" for release in RELEASES}
    diff_against(f"no pathways ({OLD_RUN_DATE})", old_routes,
                 DIAGNOSTIC_DATA_DIR / f"transit_hard_miss_range_{OLD_RUN_DATE}_results.csv",
                 DIAGNOSTIC_DATA_DIR / f"transit_hard_miss_range_{OLD_RUN_DATE}_misses.csv", lines)
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_diff_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")


def own_check():
    """Own-date tables vs the WINDOW_DATE tables: WINDOW_DATE pairs must match exactly; changes per weekday reported."""
    run_date = f"{datetime.date.today():%Y%m%d}"
    lines = [f"{NAME} {run_date}: own-date routing vs {WINDOW_DATE} routing (v2 network)"]
    columns = ["stock_min", "shifted_min", "walk_min"]
    is_reproduced = True
    for release in RELEASES:
        wed_path, own_path = newest(f"{NAME}_2*_routes_{release}.csv"), newest(f"{NAME}_2*_routes_owndate_{release}.csv")
        both = pd.read_csv(wed_path).merge(pd.read_csv(own_path), on=["draw_no", "set_name"], suffixes=("_wed", "_own"),
                                           validate="one_to_one")
        lines.append(f"== release {release}: {wed_path.name} vs {own_path.name}, {len(both)} pairs")
        both["day"] = pd.to_datetime(both.own_date).dt.day_name().str[:3]
        is_changed = np.zeros(len(both), dtype=bool)
        for column in columns:
            is_changed |= both[f"{column}_wed"].fillna(-1).to_numpy() != both[f"{column}_own"].fillna(-1).to_numpy()
        both["is_changed"] = is_changed
        wed_part = both[both.own_date == f"{WINDOW_DATE}"]
        n_mismatch = int(wed_part.is_changed.sum())
        is_reproduced &= n_mismatch == 0
        lines.append(f"reproduction ({WINDOW_DATE} pairs, {len(wed_part)}): {n_mismatch} differ: {'PASS' if n_mismatch == 0 else 'FAIL'}")
        lines.append(both.groupby(["set_name", "day"]).is_changed.agg(["size", "sum"]).rename(
            columns={"size": "pairs", "sum": "pairs_changed"}).to_string())
    lines.append(f"reproduction overall: {'PASS' if is_reproduced else 'FAIL (do not score)'}")
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_own_check_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")


if __name__ == "__main__":
    {"build": build, "feeds": feeds, "validate": validate, "route": route, "diff": diff,
     "own_check": own_check}[sys.argv[1]](*sys.argv[2:])
