"""Pathways network (TRN-13 (f); v2 of diagnostics/transit_pathway_network_v2.py, ported): train station entrances
spliced into the OSM extract, entrance -> platform and platform -> platform spurs drawn as tunnel footways whose length
walks in pathways.txt's time, and every hub platform stop moved to the far end of a short stub drawn away from the
nearest street, so R5 links the stop to its stub only. Writes a derived extract and a moved copy of the train feed.
evidence: diagnostics/transit_pathway_network_v2.py (validation A link, B walk, C transit)"""
import heapq
import math
import zipfile

import numpy as np
import pandas as pd

import config

GTFS_ENCODING = "utf-8-sig"
METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON_EQUATOR = 111_320.0
M_PER_KM = 1000
SECONDS_PER_HOUR = 3600
ASYMMETRIC_SPUR_S = 30                       # reported: spurs whose two directions differ by more than this
WALKABLE_HIGHWAYS = {"footway", "path", "pedestrian", "steps", "living_street", "residential", "service",
                     "unclassified", "tertiary", "tertiary_link", "secondary", "secondary_link", "primary",
                     "primary_link", "trunk", "trunk_link", "track", "cycleway", "road", "corridor"}
NO_ACCESS = {"no", "private"}
FOOT_ALLOWED = {"yes", "designated", "permissive"}
PLATFORM_KEYS = ["railway", "public_transport", "highway"]   # "=platform": counted for the stub's clearance only
NOT_LINKABLE = [("tunnel", "yes"), ("covered", "yes")]     # R5 TypeOfEdgeLabeler (motorway not in the set above)
SPUR_TAGS = {"highway": "footway", "tunnel": "yes"}
LINK_TAGS = {"highway": "footway"}


def local_xy(lat, lon, lat0, lon0):
    return ((np.asarray(lon) - lon0) * METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0)),
            (np.asarray(lat) - lat0) * METRES_PER_DEG_LAT)


def from_xy(x, y, lat0, lon0):
    return lat0 + y / METRES_PER_DEG_LAT, lon0 + x / (METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0)))


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


def spur_table(train_feed_path):
    """Hubs (platform coordinates), entrances, and spur times entrance -> hub and hub -> hub, in seconds."""
    with zipfile.ZipFile(train_feed_path) as gtfs_zip:
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
    entrances_df = stops_df[stops_df.location_type == config.PATHWAY_ENTRANCE_TYPE]
    platforms_df = stops_df[stops_df.stop_id.isin(used)
                            & stops_df.location_type.fillna("").isin(config.PATHWAY_PLATFORM_TYPES)
                            & stops_df.stop_id.isin(has_pathway)
                            & stops_df.parent_station.isin(entrances_df.parent_station)].copy()
    platforms_df["hub"] = platforms_df.stop_lat.round(7).astype(str) + "," + platforms_df.stop_lon.round(7).astype(str)
    entrance_rows, hub_rows = [], []
    for platform in platforms_df.itertuples():
        out_s = shortest_from(forward, platform.stop_id)      # platform -> x
        in_s = shortest_from(backward, platform.stop_id)      # x -> platform
        for entrance in entrances_df[entrances_df.parent_station == platform.parent_station].itertuples():
            if entrance.stop_id in in_s and entrance.stop_id in out_s:
                entrance_rows.append({"hub": platform.hub, "platform_id": platform.stop_id,
                                      "entrance_id": entrance.stop_id, "in_s": in_s[entrance.stop_id],
                                      "out_s": out_s[entrance.stop_id]})
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
              f"asymmetric > {ASYMMETRIC_SPUR_S} s": int(((entrance_spurs.in_s - entrance_spurs.out_s).abs()
                                                          > ASYMMETRIC_SPUR_S).sum())}
    return hubs, entrances, entrance_spurs, hub_spurs, counts


def is_walkable_linkable(tags):
    if tags.get("highway") not in WALKABLE_HIGHWAYS or tags.get("area") == "yes":
        return False
    if any(tags.get(key) == value for key, value in NOT_LINKABLE):
        return False
    if tags.get("foot") in NO_ACCESS:
        return False
    return not (tags.get("access") in NO_ACCESS and tags.get("foot") not in FOOT_ALLOWED)


def is_platform_way(tags):
    """Platform ways R5 can link to although they carry no walkable highway tag (e.g. railway=platform)."""
    is_platform = any(tags.get(key) == "platform" for key in PLATFORM_KEYS)
    return is_platform and not any(tags.get(key) == value for key, value in NOT_LINKABLE)


def candidate_ways(pbf_path, points_lat, points_lon):
    """Walkable, linkable ways (and platform ways) with a node in a grid cell next to any point:
    {way_id: (node_ids, lats, lons, is_walk)}, plus the extract's largest node and way ids."""
    import osmium
    grid = config.PATHWAY_GRID_DEG
    cells = set()
    for lat, lon in zip(points_lat, points_lon):
        row, col = math.floor(lat / grid), math.floor(lon / grid)
        cells |= {(row + i, col + j) for i in (-1, 0, 1) for j in (-1, 0, 1)}
    ways, max_ids = {}, {"node": 0, "way": 0}
    for obj in osmium.FileProcessor(str(pbf_path)).with_locations():
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
        if len(refs) < 2 or not any((math.floor(lat / grid), math.floor(lon / grid)) in cells for _, lat, lon in refs):
            continue
        ways[obj.id] = ([ref for ref, _, _ in refs], np.array([lat for _, lat, _ in refs]),
                        np.array([lon for _, _, lon in refs]), is_walk)
    return ways, max_ids


def segment_table(ways, is_walk_only):
    """Flat arrays of every candidate segment (walkable ways only, or platform ways too): way id, index, end points."""
    way_ids, indices, lat1, lon1, lat2, lon2 = [], [], [], [], [], []
    for way_id, (_, lats, lons, is_walk) in ways.items():
        if is_walk_only and not is_walk:
            continue
        n_segments = len(lats) - 1
        way_ids.append(np.full(n_segments, way_id))
        indices.append(np.arange(n_segments))
        lat1.append(lats[:-1])
        lon1.append(lons[:-1])
        lat2.append(lats[1:])
        lon2.append(lons[1:])
    return {name: np.concatenate(parts) for name, parts in
            [("way_id", way_ids), ("index", indices), ("lat1", lat1), ("lon1", lon1), ("lat2", lat2), ("lon2", lon2)]}


def nearest_splice(lat, lon, segments):
    """Nearest point on any candidate segment: (distance_m, way_id, segment index, t in [0, 1], point lat, lon)."""
    grid = config.PATHWAY_GRID_DEG
    is_near = ((np.minimum(segments["lat1"], segments["lat2"]) <= lat + grid)
               & (np.maximum(segments["lat1"], segments["lat2"]) >= lat - grid)
               & (np.minimum(segments["lon1"], segments["lon2"]) <= lon + grid)
               & (np.maximum(segments["lon1"], segments["lon2"]) >= lon - grid))
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
    n_teeth = max(1, math.ceil(straight / config.PATHWAY_ZIGZAG_TOOTH_MIN_M),
                  math.ceil(length_m / (2 * config.PATHWAY_ZIGZAG_AMPLITUDE_MAX_M)))
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


def plan_network(spurs, ways, segments, clearance_segments, id_counter):
    """New nodes, new ways and way splices for one release's spur table; plus spur and hub tables and counts."""
    hubs, entrances, entrance_spurs, hub_spurs, counts = spurs
    walk_speed_ms = config.PATHWAY_WALK_SPEED_KMH * M_PER_KM / SECONDS_PER_HOUR
    new_nodes, new_ways, splices = [], [], {}     # splices: way_id -> list of (segment index, t, node id)
    node_of = {}

    def add_node(lat, lon):
        id_counter["node"] += 1
        new_nodes.append((id_counter["node"], lat, lon))
        return id_counter["node"]

    def add_way(node_ids, tags):
        id_counter["way"] += 1
        new_ways.append((id_counter["way"], node_ids, {**tags, config.PATHWAY_TAG[0]: config.PATHWAY_TAG[1]}))

    link_rows = []
    for entrance_id in entrance_spurs.entrance_id.unique():
        lat, lon = entrances.loc[entrance_id]
        distance_m, way_id, segment, t, point_lat, point_lon = nearest_splice(lat, lon, segments)
        link_rows.append({"entrance_id": entrance_id, "link_m": distance_m})
        if way_id is None or distance_m > config.PATHWAY_LINK_RADIUS_M:
            continue
        refs, lats, lons, _ = ways[way_id]
        end_x, end_y = local_xy([lats[segment], lats[segment + 1]], [lons[segment], lons[segment + 1]],
                                point_lat, point_lon)
        end_distance = np.hypot(end_x, end_y)
        if end_distance.min() <= config.PATHWAY_SNAP_M:
            street_node = refs[segment + int(np.argmin(end_distance))]
        else:
            street_node = add_node(point_lat, point_lon)
            splices.setdefault(way_id, []).append((segment, t, street_node))
        entrance_node = add_node(lat, lon)
        add_way([street_node, entrance_node], LINK_TAGS)
        node_of[entrance_id] = entrance_node
    hub_rows = []
    for hub, (lat, lon) in hubs.iterrows():
        node_of[hub] = add_node(lat, lon)
        street_m = nearest_splice(lat, lon, clearance_segments)[0]
        best = None
        for k in range(config.PATHWAY_STUB_DIRECTIONS):
            angle = 2 * math.pi * k / config.PATHWAY_STUB_DIRECTIONS
            end_lat, end_lon = from_xy(config.PATHWAY_STUB_M * math.cos(angle), config.PATHWAY_STUB_M * math.sin(angle),
                                       lat, lon)
            end_lat, end_lon = round(end_lat, 7), round(end_lon, 7)
            clearance_m = nearest_splice(end_lat, end_lon, clearance_segments)[0]
            if best is None or clearance_m > best[0]:
                best = (clearance_m, end_lat, end_lon)
        clearance_m, stub_lat, stub_lon = best
        add_way([node_of[hub], add_node(stub_lat, stub_lon)], LINK_TAGS)
        hub_rows.append({"hub": hub, "hub_lat": lat, "hub_lon": lon, "stub_way_id": id_counter["way"],
                         "stop_lat": stub_lat, "stop_lon": stub_lon, "hub_street_m": street_m,
                         "stop_street_m": clearance_m})
    hubs_df = pd.DataFrame(hub_rows)
    spur_rows = []
    for kind, spur_df, start_column, end_column in [("entrance", entrance_spurs, "entrance_id", "hub"),
                                                    ("hub", hub_spurs, "hub", "other_hub")]:
        for spur in spur_df.itertuples():
            start, end = getattr(spur, start_column), getattr(spur, end_column)
            if start not in node_of:
                spur_rows.append({"kind": kind, "start": start, "end": end, "time_s": spur.time_s,
                                  "status": "no street link"})
                continue
            start_lat, start_lon = (entrances.loc[start] if kind == "entrance" else hubs.loc[start])
            end_lat, end_lon = hubs.loc[end]
            target_m = spur.time_s * walk_speed_ms
            points, straight_m, is_straight = zigzag(start_lat, start_lon, end_lat, end_lon, target_m)
            node_ids = [node_of[start]] + [add_node(lat, lon) for lat, lon in points] + [node_of[end]]
            add_way(node_ids, SPUR_TAGS)
            lats = [start_lat] + [p[0] for p in points] + [end_lat]
            lons = [start_lon] + [p[1] for p in points] + [end_lon]
            spur_rows.append({"kind": kind, "start": start, "end": end, "time_s": spur.time_s, "target_m": target_m,
                              "straight_m": straight_m, "drawn_m": polyline_m(np.array(lats), np.array(lons)),
                              "status": "straight (time shorter)" if is_straight else "ok"})
    spurs_df = pd.DataFrame(spur_rows)
    links_df = pd.DataFrame(link_rows)
    counts.update({"entrances used": len(links_df),
                   "entrances linked": int((links_df.link_m <= config.PATHWAY_LINK_RADIUS_M).sum()),
                   "ways spliced": len(splices), "new nodes": len(new_nodes), "new ways": len(new_ways),
                   "stop clearance m min": round(float(hubs_df.stop_street_m.min()), 2),
                   "stop clearance m median": round(float(hubs_df.stop_street_m.median()), 2)})
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


def write_derived_extract(pbf_path, out_path, plan, ways):
    """Copy of the extract with the plan's nodes and ways added and its splices applied (one pass)."""
    import osmium
    new_nodes, new_ways, splices = plan[:3]
    state = {"nodes_flushed": False, "ways_flushed": False}
    writer = osmium.SimpleWriter(str(out_path))

    def flush_nodes():
        for node_id, lat, lon in new_nodes:
            writer.add_node(osmium.osm.mutable.Node(id=node_id, location=(lon, lat), version=1, tags={}))
        state["nodes_flushed"] = True

    def flush_ways():
        for way_id, node_ids, tags in new_ways:
            writer.add_way(osmium.osm.mutable.Way(id=way_id, nodes=node_ids, version=1, tags=tags))
        state["ways_flushed"] = True

    try:
        for obj in osmium.FileProcessor(str(pbf_path)):
            if obj.is_way() and not state["nodes_flushed"]:
                flush_nodes()
            if obj.is_relation() and not state["ways_flushed"]:
                flush_ways()
            if obj.is_way() and obj.id in splices:
                refs = [node.ref for node in obj.nodes]
                assert refs == ways[obj.id][0], f"way {obj.id}: node list differs from the first pass"
                writer.add_way(obj.replace(nodes=spliced_nodes(refs, splices[obj.id])))
            else:
                writer.add(obj)
        if not state["nodes_flushed"]:
            flush_nodes()
        if not state["ways_flushed"]:
            flush_ways()
    finally:
        writer.close()


def write_moved_feed(source_path, target_path, hubs_df):
    """Copy of the train feed with each hub platform stop at its stub's far end (other files byte for byte).
    Returns the number of stops moved."""
    moved = hubs_df.set_index("hub")[["stop_lat", "stop_lon"]]
    n_moved = 0
    with zipfile.ZipFile(source_path) as source_zip, zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED) as target_zip:
        for member in source_zip.infolist():
            if member.filename != "stops.txt":
                target_zip.writestr(member, source_zip.read(member.filename))
                continue
            stops_df = pd.read_csv(source_zip.open("stops.txt"), dtype=str, encoding=GTFS_ENCODING,
                                   keep_default_na=False)
            is_platform = stops_df.location_type.isin(config.PATHWAY_PLATFORM_TYPES)
            hub = (stops_df.stop_lat.astype(float).round(7).astype(str) + ","
                   + stops_df.stop_lon.astype(float).round(7).astype(str))
            is_moved = is_platform & hub.isin(moved.index)
            stops_df.loc[is_moved, "stop_lat"] = [f"{value:.7f}" for value in moved.loc[hub[is_moved], "stop_lat"]]
            stops_df.loc[is_moved, "stop_lon"] = [f"{value:.7f}" for value in moved.loc[hub[is_moved], "stop_lon"]]
            target_zip.writestr("stops.txt", stops_df.to_csv(index=False, lineterminator="\n"))
            n_moved = int(is_moved.sum())
    return n_moved


def build_pathways(pbf_path, train_feed_path, derived_pbf_path, moved_feed_path):
    """The derived extract and the moved train feed for one release; returns (spurs_df, hubs_df, counts)."""
    spurs = spur_table(train_feed_path)
    hubs, entrances, entrance_spurs = spurs[:3]
    points = pd.concat([entrances.loc[entrance_spurs.entrance_id.unique()], hubs])   # hubs: stub clearance
    ways, max_ids = candidate_ways(pbf_path, points.stop_lat.to_numpy(), points.stop_lon.to_numpy())
    assert max_ids["node"] < config.PATHWAY_NEW_NODE_ID_BASE and max_ids["way"] < config.PATHWAY_NEW_WAY_ID_BASE, \
        "new id bases collide with the extract's ids"
    id_counter = {"node": config.PATHWAY_NEW_NODE_ID_BASE, "way": config.PATHWAY_NEW_WAY_ID_BASE}
    plan = plan_network(spurs, ways, segment_table(ways, is_walk_only=True), segment_table(ways, is_walk_only=False),
                        id_counter)
    spurs_df, counts, hubs_df = plan[3], plan[4], plan[5]
    counts["platform stops moved"] = write_moved_feed(train_feed_path, moved_feed_path, hubs_df)
    write_derived_extract(pbf_path, derived_pbf_path, plan, ways)
    return spurs_df, hubs_df, counts
