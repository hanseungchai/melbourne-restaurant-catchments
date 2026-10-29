"""Does adding the train feed's pathway times to R5's street network change TRN-13's hard misses, and how?

Claim under test (concepts/transit.md TRN-13 (f); DESIGN.md Q23): pathways go into the network on fidelity, since
the free check (diagnostics/transit_pathway_check.py) accepted the data (0.777 vs 2/3). The rerun reports, per hard-miss
test, the misses fixed / created / unchanged, reads each created miss, and the stop condition still binds (user,
2026-10-18). Where the pipeline would rely on it: the network behind transit bands 1-2 (SCR-1, RCH-1).

Network (Claude's build, autonomous session 2026-10-19; derived copy of the OSM extract, one per release; the feeds are
not edited):
  Hub: one new node per train platform coordinate (platforms used by a trip, with pathway data and an entrance); a
    STUB_M footway stub at the hub (linkable), so R5 links the platform stop to it (0 m away) and not to a street.
  Spur entrance -> hub: footway tagged tunnel=yes (R5 never links points to tunnel / covered / motorway ways: jar,
    TypeOfEdgeLabeler, read 2026-10-19), so no origin or destination snaps onto it; its length is the pathway time
    x WALK_SPEED_KMH, drawn as a zigzag between the two points. Pathway time = shortest traversal_time path in
    pathways.txt (is_bidirectional honoured, elevators kept: user), mean of the two directions (Claude: entrance ->
    platform and back differ by > 30 s on 4 of 2,166 pairs, max 66 s; one spur carries one time). Spur time shorter
    than the straight line: straight line, counted (Claude's default, TRN-13 (f) (d)).
  Spur hub -> hub within a station: shortest pathway time between the platforms, as above, so a change of platform
    doesn't go out through an entrance and back.
  Entrance: a new node at its coordinates, joined by a short footway to the nearest point of the nearest walkable,
    linkable street segment within LINK_RADIUS_M (a node spliced into that way, as R5 splits an edge when it links a
    point; an existing node within SNAP_M is reused). Entrances with no street in range are left out, counted.
  Platforms sharing a coordinate share a hub (spur time = the shorter).
Build check (Claude's rule, set before any result): R5 on the derived network, walk-only from each pathway-check side's
  end to its platform point, must reproduce transit_pathway_check's best "R5 walk to entrance + spur" within
  CHECK_TOLERANCE_S on >= CHECK_SHARE of sides; else no rerun. The spur is taken as built (drawn length at
  WALK_SPEED_KMH, so the straight-line floor counts). First version (v1, files *_check_v1_*) expected the feed's
  pathway time and failed (0.943 / 0.916): its misses were the straight-line spurs the spec itself draws, an error in
  the check's expected value, not in the network; the bar was not changed. v1's share is reported beside.
Rerun: the three R5 calls of transit_band_metric.route (stock S, shifted H, walk-only W) on every pair of each
  release on its derived network; then transit_model_compare.py and transit_hard_miss_range.py score them with
  `--network=pathways` (unchanged tests, outputs under this script's name); `diff` compares with the 2026-10-18 runs.

Conclusion (run 2026-10-19, autonomous; Claude's build and check rules, not user-approved): network built for both
  releases: 584 / 576 hubs, 2,159 / 2,141 entrance spurs (189 / 188 drawn straight: pathway time under the straight
  line), 640 / 610 hub spurs; all 746 / 748 entrances linked (median 0.4 m to a street). Build check PASSES on the
  as-built expectation: 0.991 (435/439) and 0.984 (797/810), median +3 s; v1 (feed time) 0.943 / 0.916. Residuals: at
  Holmesglen and Reservoir R5 reaches the platform without the spur (new = old walk); not explained, ~1% of sides.
  On the sides, R5 vs Google's walk within +-60 s: 0.756 / 0.746 (old network 0.688 / 0.669).
  Rerun: transit times later on ~18% of pairs (median +1-2 min), walk-only changed on 4 of 3,462 (station cut-through
  negligible); 14 no-wait band calls change, all to a later band. Stage 1, no-wait plain at k = 2 (the decided model):
  zone checks all pass; hard misses false 10 4/294, lost 20 7 -> 8/248 (upper 0.062), false 20 24 -> 20/503 (upper
  0.077 -> 0.061); fail, not severe, not concentrated: a recorded cost, as before. Misses fixed 4 (3 tram-group pairs
  where R5 rode a train with free platform access, 1 home-wait), created 1 (second 43620, Eaglemont -> Ivanhoe: R5's
  street walk to the entrance is already longer than Google's whole walk; +49 s of pathway tips a knife-edge boarding,
  Google waits 88 s). Stock R5 4.16 stays barred (lost 20 22/248). Scalar fit s 1.025 -> 1.019 (R5 less early).

Inputs (read only): the OSM extract in frozen_inputs/osm_extract/; the cleaned feeds (outputs/pt_graph/gtfs_cleaned/
for 2026-10-09, diagnostic_data/transit_band_metric_gtfs_cleaned_20261016/ for 2026-10-16); the pairs in
outputs/transit_validation/; transit_pathway_check's saved sides and walks; the 2026-10-18 band-metric routing tables,
model-compare and hard-miss-range results. Self-contained (CLAUDE.md D1). No API calls.
Usage: `python transit_pathway_network.py build` (both releases, one read of the extract), `... route 20261009`,
`... route 20261016` (one network per process; build check first), then the two scorers with `--network=pathways`,
then `... diff`. Saved data (derived extracts, routing tables) is reused when present; results carry the run date.
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
NAME = "transit_pathway_network"
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

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_band_metric.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as transit_band_metric.py
SINGLE_PERCENTILE = 49                         # as transit_band_metric.py (r5py renames a lone p50)
WALK_SPEED_KMH = 4.16                          # config.WALK_SPEED_KMH
BOARD_SLACK_MIN = 1                            # as transit_band_metric.py
TRAIN_HALF = "train"
SET_RELEASE = {"train": "20261009", "second": "20261016", "topup": "20261016"}
SECONDS_PER_MIN = 60
SECONDS_PER_HOUR = 3600
M_PER_KM = 1000

# --- network build (Claude) ------------------------------------------------------------------------
ENTRANCE_TYPE = "2"
PLATFORM_TYPES = ["0", ""]
LINK_RADIUS_M = 300                            # as R5's first stop-link radius
SNAP_M = 0.5                                   # reuse a street node this close instead of splicing
STUB_M = 1.0
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
NOT_LINKABLE = [("tunnel", "yes"), ("covered", "yes")]     # R5 TypeOfEdgeLabeler (motorway not in the set above)
METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON_EQUATOR = 111_320.0
GTFS_ENCODING = "utf-8-sig"

# --- build check and diff (Claude, set before any result) ------------------------------------------
CHECK_TOLERANCE_S = 15
CHECK_SHARE = 0.95
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
        if not is_walkable_linkable(tags):
            continue
        if not all(node.location.valid() for node in obj.nodes):
            continue                                   # cut by the extract's edge: never spliced
        refs = [(node.ref, node.lat, node.lon) for node in obj.nodes]
        if len(refs) < 2 or not any((math.floor(lat / GRID_DEG), math.floor(lon / GRID_DEG)) in cells for _, lat, lon in refs):
            continue
        ways[obj.id] = ([ref for ref, _, _ in refs], np.array([lat for _, lat, _ in refs]), np.array([lon for _, _, lon in refs]))
    return ways, max_ids


def segment_table(ways):
    """Flat arrays of every candidate segment: way id, index in the way, end points."""
    way_ids, indices, lat1, lon1, lat2, lon2 = [], [], [], [], [], []
    for way_id, (_, lats, lons) in ways.items():
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


def plan_release(release, ways, segments, id_counter):
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
        refs, lats, lons = ways[way_id]
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
    for hub, (lat, lon) in hubs.iterrows():
        node_of[hub] = add_node(lat, lon)
        stub_lat, stub_lon = from_xy(STUB_M, 0.0, lat, lon)
        add_way([node_of[hub], add_node(stub_lat, stub_lon)], {"highway": "footway"})
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
                   "ways spliced": len(splices), "new nodes": len(new_nodes), "new ways": len(new_ways)})
    return new_nodes, new_ways, splices, spurs_df, counts


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
        _, entrances, entrance_spurs, _, _ = spur_table(release)
        entrance_points.append(entrances.loc[entrance_spurs.entrance_id.unique()])
    points = pd.concat(entrance_points)
    ways, max_ids = candidate_ways(points.stop_lat.to_numpy(), points.stop_lon.to_numpy())
    segments = segment_table(ways)
    print(f"pass 1: {len(ways)} candidate ways, {len(segments['index'])} segments; max ids {max_ids}; "
          f"{datetime.datetime.now() - started}", flush=True)
    assert max_ids["node"] < NEW_NODE_ID_BASE and max_ids["way"] < NEW_WAY_ID_BASE, "new id bases collide"
    plans, lines = {}, [f"{NAME} {run_date}: build"]
    for release in todo:
        id_counter = {"node": NEW_NODE_ID_BASE, "way": NEW_WAY_ID_BASE}
        plans[release] = plan_release(release, ways, segments, id_counter)
        spurs_df, counts = plans[release][3], plans[release][4]
        spurs_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_spurs_{release}.csv", index=False)
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
    if set_name == "train":
        split_df = pd.read_csv(SPLIT_PATH, usecols=["draw_no", "half"])
        pairs_df = pd.read_csv(PAIRS_PATH, usecols=columns)
        return pairs_df[pairs_df.draw_no.isin(split_df.draw_no[split_df.half == TRAIN_HALF])]
    if set_name == "second":
        return pd.read_csv(RESERVE_PATH, usecols=columns)
    topup_df = pd.read_csv(TOPUP_PATH, usecols=columns)
    return topup_df[topup_df.draw_no.isin(pd.read_csv(TOPUP_SELECTION_PATH).draw_no)]


# --- routing ---------------------------------------------------------------------------------------
def build_check(network, release, run_date):
    """R5 walk end -> platform point on the derived network vs the pathway check's best entrance + pathway time."""
    import geopandas as gpd
    from r5py import DetailedItineraries, TransportMode
    sides_path, walks_path = newest(f"{PATHWAY_CHECK_NAME}_*_sides.csv"), newest(f"{PATHWAY_CHECK_NAME}_*_walks.csv")
    sides_df = pd.read_csv(sides_path, dtype={"platform_id": str, "entrance_id": str, "release": str})
    sides_df = sides_df[(sides_df.status == "ok") & (sides_df.release == release)]
    walks_df = pd.read_csv(walks_path)
    keys = ["side", "end_lat", "end_lon"]
    entrance_walks = walks_df.rename(columns={"point_lat": "entrance_lat", "point_lon": "entrance_lon", "r5_s": "r5_entrance_s"})
    platform_walks = walks_df.rename(columns={"point_lat": "platform_lat", "point_lon": "platform_lon", "r5_s": "old_platform_s"})
    ok_df = sides_df.merge(entrance_walks[keys + ["entrance_lat", "entrance_lon", "r5_entrance_s"]],
                           on=keys + ["entrance_lat", "entrance_lon"])
    spurs_df = pd.read_csv(newest(f"{NAME}_2*_spurs_{release}.csv"))
    spurs_df = spurs_df[spurs_df.kind == "entrance"].rename(columns={"start": "entrance_id", "end": "hub"})
    ok_df["hub"] = ok_df.platform_lat.round(7).astype(str) + "," + ok_df.platform_lon.round(7).astype(str)
    ok_df = ok_df.merge(spurs_df[["entrance_id", "hub", "drawn_m"]], on=["entrance_id", "hub"], how="left")
    assert ok_df.drawn_m.notna().all(), "side entrance without a built spur"
    ok_df["raw_expected_s"] = ok_df.r5_entrance_s + ok_df.path_s          # pathway time as in the feed
    ok_df["expected_s"] = ok_df.r5_entrance_s + ok_df.drawn_m / WALK_SPEED_MS   # as built (straight line floor)
    side_keys = ["set_name", "draw_no", "side"]
    raw_best = ok_df.groupby(side_keys).raw_expected_s.min()
    best_df = ok_df.loc[ok_df.groupby(side_keys).expected_s.idxmin()].drop(columns="raw_expected_s").merge(
        raw_best.reset_index(), on=side_keys).merge(
        platform_walks[keys + ["platform_lat", "platform_lon", "old_platform_s"]], on=keys + ["platform_lat", "platform_lon"])
    targets = best_df[keys + ["platform_lat", "platform_lon"]].drop_duplicates().reset_index(drop=True)
    is_board = targets.side == "board"
    origins = gpd.GeoDataFrame({"id": targets.index}, crs="EPSG:4326", geometry=gpd.points_from_xy(
        np.where(is_board, targets.end_lon, targets.platform_lon), np.where(is_board, targets.end_lat, targets.platform_lat)))
    destinations = gpd.GeoDataFrame({"id": targets.index}, crs="EPSG:4326", geometry=gpd.points_from_xy(
        np.where(is_board, targets.platform_lon, targets.end_lon), np.where(is_board, targets.platform_lat, targets.end_lat)))
    di_df = pd.DataFrame(DetailedItineraries(network, origins=origins, destinations=destinations,
                                             departure=datetime.datetime.combine(WINDOW_DATE, datetime.time(12)),
                                             transport_modes=[TransportMode.WALK], speed_walking=WALK_SPEED_KMH))
    walked = di_df.groupby("from_id").travel_time.sum().dt.total_seconds().rename("new_platform_s")
    targets = targets.join(walked)
    best_df = best_df.merge(targets, on=keys + ["platform_lat", "platform_lon"], how="left")
    best_df["diff_s"] = best_df.new_platform_s - best_df.expected_s
    is_ok = best_df.diff_s.abs() <= CHECK_TOLERANCE_S
    share = float(is_ok.mean())
    best_df["google_diff_new_s"] = best_df.new_platform_s - best_df.google_walk_s
    best_df["google_diff_old_s"] = best_df.old_platform_s - best_df.google_walk_s
    lines = [f"build check {release}: sides {len(best_df)} (from {sides_path.name}, {walks_path.name}); no walk "
             f"{int(best_df.new_platform_s.isna().sum())}; within +-{CHECK_TOLERANCE_S} s of expected {int(is_ok.sum())} = {share:.3f} "
             f"(bar {CHECK_SHARE}) -> {'PASS' if share >= CHECK_SHARE else 'FAIL'}",
             f"  diff new - expected: median {best_df.diff_s.median():+.1f} s, p05 {best_df.diff_s.quantile(0.05):+.1f}, "
             f"p95 {best_df.diff_s.quantile(0.95):+.1f}; over +{CHECK_TOLERANCE_S} {int((best_df.diff_s > CHECK_TOLERANCE_S).sum())}, "
             f"under -{CHECK_TOLERANCE_S} {int((best_df.diff_s < -CHECK_TOLERANCE_S).sum())}",
             f"  beside, vs the feed's pathway time (no straight-line floor; the first check, v1): within +-{CHECK_TOLERANCE_S} s "
             f"{float(((best_df.new_platform_s - best_df.raw_expected_s).abs() <= CHECK_TOLERANCE_S).mean()):.3f}",
             f"  vs Google's walk within +-60 s: new network {float((best_df.google_diff_new_s.abs() <= 60).mean()):.3f}, "
             f"old network {float((best_df.google_diff_old_s.abs() <= 60).mean()):.3f}"]
    best_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_check_{release}.csv", index=False)
    return lines, share >= CHECK_SHARE


def route(release):
    sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import
    import geopandas as gpd
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    run_date = f"{datetime.date.today():%Y%m%d}"

    def ttm_min(network, pair, departure, transport_modes, max_time_min):
        origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.origin_lon], [pair.origin_lat]))
        destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=transport_modes, max_time=datetime.timedelta(minutes=max_time_min),
            speed_walking=WALK_SPEED_KMH))
        return matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]

    pbf_path = derived_pbf_path(release)
    assert pbf_path.exists(), f"run build first ({pbf_path.name} missing)"
    print(f"reusing {pbf_path.name} ({datetime.date.fromtimestamp(pbf_path.stat().st_mtime)})", flush=True)
    network = TransportNetwork(pbf_path, [CLEANED_DIRS[release] / f"{name}.zip" for name in FEED_NAMES])
    print("covers", WINDOW_DATE, network.transit_layer.covers(WINDOW_DATE), flush=True)
    check_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_check_{release}_summary.txt"
    if not check_path.exists():
        lines, is_pass = build_check(network, release, run_date)
        with open(check_path, "w", encoding="utf-8", newline="\n") as file:
            file.write("\n".join(lines) + "\n")
    lines = check_path.read_text(encoding="utf-8").splitlines()
    print("\n".join(lines), flush=True)
    if "-> PASS" not in lines[0]:
        print("build check failed: no rerun")
        return

    set_names = [name for name, set_release in SET_RELEASE.items() if set_release == release]
    pairs_df = pd.concat([pairs_of_set(name).assign(set_name=name) for name in set_names], ignore_index=True)
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_2*_routes_{release}.csv"))
    table_path = saved[-1] if saved else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_routes_{release}.csv"
    done = set(pd.read_csv(table_path).draw_no) if table_path.exists() else set()
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"release {release}: sets {set_names}, {len(pairs_df)} pairs; table {table_path.name}, "
          f"{len(done)} done, {len(todo_df)} to route", flush=True)
    transit_modes = [TransportMode.TRANSIT, TransportMode.WALK]
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        departure = datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))
        row = {"draw_no": pair.draw_no, "set_name": pair.set_name, "release": release,
               "stock_min": ttm_min(network, pair, departure, transit_modes, MAX_TIME_MIN),
               "shifted_min": ttm_min(network, pair, departure - datetime.timedelta(minutes=BOARD_SLACK_MIN),
                                      transit_modes, MAX_TIME_MIN + BOARD_SLACK_MIN),
               "walk_min": ttm_min(network, pair, departure, [TransportMode.WALK], MAX_TIME_MIN)}
        pd.DataFrame([row]).to_csv(table_path, mode="a", header=not table_path.exists(), index=False)
        if i % 100 == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)


# --- diff against the 2026-10-18 runs --------------------------------------------------------------
def diff():
    run_date = f"{datetime.date.today():%Y%m%d}"
    lines = [f"{NAME} {run_date}: diff, pathways network vs the {OLD_RUN_DATE} runs"]
    for release in RELEASES:
        old_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{BAND_METRIC_NAME}_{OLD_RUN_DATE}_routes_{release}.csv")
        new_df = pd.read_csv(newest(f"{NAME}_2*_routes_{release}.csv"))
        both = old_df.merge(new_df, on="draw_no", suffixes=("_old", "_new"))
        parts = []
        for column in ["stock_min", "shifted_min", "walk_min"]:
            change = both[f"{column}_new"].fillna(np.inf) - both[f"{column}_old"].fillna(np.inf)
            change = change[np.isfinite(change)]
            parts.append(f"{column}: changed {int((change != 0).sum())}/{len(both)}, up {int((change > 0).sum())} "
                         f"(median {change[change > 0].median() if (change > 0).any() else 0:+.0f}), down {int((change < 0).sum())} "
                         f"(median {change[change < 0].median() if (change < 0).any() else 0:+.0f}), mean {change.mean():+.3f}")
        lines.append(f"release {release}: {len(both)} pairs; " + "; ".join(parts))
    old_results = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"transit_hard_miss_range_{OLD_RUN_DATE}_results.csv")
    new_results = pd.read_csv(newest(f"{NAME}_2*_range_results.csv"))
    merged = old_results.merge(new_results, on=["set_name", "draw_no"], suffixes=("_old", "_new"))
    merged = merged[merged.is_scored_old.astype(bool)]
    for label, column in [("no-wait (n_min)", "n_min"), ("stock (stock_min)", "stock_min")]:
        old_min, new_min = merged[f"{column}_old"].fillna(np.inf), merged[f"{column}_new"].fillna(np.inf)
        band_old = np.digitize(old_min, [10.5, 20.5])
        band_new = np.digitize(new_min, [10.5, 20.5])
        lines.append(f"{label}: scored {len(merged)}, minutes changed {int((old_min != new_min).sum())}, band calls changed "
                     f"{int((band_old != band_new).sum())} (later band {int((band_new > band_old).sum())}, earlier "
                     f"{int((band_new < band_old).sum())})")
    old_misses = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"transit_hard_miss_range_{OLD_RUN_DATE}_misses.csv")
    new_misses = pd.read_csv(newest(f"{NAME}_2*_range_misses.csv"))
    key = ["model", "test", "set_name", "draw_no"]
    for model in old_misses.model.unique():
        old_keys = set(map(tuple, old_misses[old_misses.model == model][key].to_numpy()))
        new_keys = set(map(tuple, new_misses[new_misses.model == model][key].to_numpy()))
        lines.append(f"model {model}: misses {len(old_keys)} -> {len(new_keys)}; fixed {len(old_keys - new_keys)}, created "
                     f"{len(new_keys - old_keys)}, unchanged {len(old_keys & new_keys)}")
        for test in sorted(set(old_misses.test) | set(new_misses.test)):
            old_t = {k for k in old_keys if k[1] == test}
            new_t = {k for k in new_keys if k[1] == test}
            lines.append(f"  {test}: {len(old_t)} -> {len(new_t)} (fixed {len(old_t - new_t)}, created {len(new_t - old_t)}, "
                         f"unchanged {len(old_t & new_t)})")
        for label, keys_set, frame in [("fixed", old_keys - new_keys, old_misses), ("created", new_keys - old_keys, new_misses)]:
            for k in sorted(keys_set, key=lambda item: (item[1], item[2], item[3])):
                row = merged[(merged.set_name == k[2]) & (merged.draw_no == k[3])]
                miss = frame[(frame.model == model) & (frame.test == k[1]) & (frame.set_name == k[2]) & (frame.draw_no == k[3])].iloc[0]
                lines.append(f"    {label} | {k[1]} | {k[2]} {k[3]}: default {miss.default_min:.0f}, low {miss.low_2:.0f}, "
                             f"n_min {row.n_min_old.iloc[0]} -> {row.n_min_new.iloc[0]}, stock {row.stock_min_old.iloc[0]} -> "
                             f"{row.stock_min_new.iloc[0]}, walk {row.walk_min_old.iloc[0]} -> {row.walk_min_new.iloc[0]}; "
                             f"{miss.default_vehicles if isinstance(miss.default_vehicles, str) else 'WALK'}, {miss.haversine_m:.0f} m, "
                             f"group {miss.group}")
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_diff_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")


if __name__ == "__main__":
    {"build": build, "route": route, "diff": diff}[sys.argv[1]](*sys.argv[2:])
