"""Construct graph stage: the drive routing graph and each hex's origin/destination nodes.

1. reduce_isolated_edges: drive graph cut to its largest strongly connected component.
2. find_split_candidate_edges: each hex's nearest roads (candidates).
3. split_edges: candidate roads cut into equal pieces.
4. centroid_node_assignment: each hex rounded to the nearest piece node.
Each step is skipped when its files exist, unless should_rebuild. Walk retired (DESIGN.md Q3).
"""
import gc
import itertools
import math
import pickle
from collections import Counter
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import LineString

import config
from functions.output_helper import is_already_built, project_relative, write_pickle
from functions.subject_paths import all_layers_tags, resolve_subject, subject_file

SPLIT_LENGTH_TOL_M = 1e-6        # split pieces must add up to the original edge length within this
TWO_WAY_LENGTH_TOL_M = 0.01      # both directions of a two-way road must have the same length within this
UNSCALED_EDGE_ATTRS = {'geometry', 'travel_time', 'time_raw_s', 'speed_kph'}   # would be copied unscaled onto pieces

# Graph attributes (road_graphs.py)
NODE_LON_ATTR = "x"
NODE_LAT_ATTR = "y"
EDGE_LENGTH_ATTR = "length"
EDGE_HIGHWAY_ATTR = "highway"

# Filled hex grid columns (hex_tile_construction.py)
HEX_ID_COL = "hex_id"
CENTROID_LAT_COL = "centroid_lat"
CENTROID_LON_COL = "centroid_lon"
GEOMETRY_COL = "geometry"

# Candidate table columns
EDGE_U_COL = "u"
EDGE_V_COL = "v"
ROAD_A_COL = "road_a"            # smaller end node id: a two-way road is one road
ROAD_B_COL = "road_b"
LINK_A_COL = "link_a"            # the road chain through degree-2 nodes, named by its smallest road
LINK_B_COL = "link_b"
ROAD_DIST_COL = "dist"           # metres from the hex centroid to the road
CANDIDATE_HEX_COL = "nearest_hex_id"

# Hex-node table columns: drive_node_<j>, drive_road_dist_<j>_m, drive_node_dist_<j>_m (j = candidate rank)
NODE_COL_PREFIX = "drive"


def _subject_path(path, subject_lat, subject_lon):
    """path in the subject's subfolder, tagged with the filled grid's data layers; folder created."""
    out = subject_file(path, subject_lat, subject_lon, all_layers_tags())
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _node_col(quantity, rank):
    """drive_node_1, or drive_road_dist_1_m / drive_node_dist_1_m for a distance."""
    name = f"{NODE_COL_PREFIX}_{quantity}_{rank}"
    return name if quantity == "node" else f"{name}_m"


def _load_graph(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def _write_gpkg(gdf, path):
    """Write gdf to path as GeoPackage, replacing an existing file's layer (pair with is_already_built)."""
    gdf.to_file(path, driver="GPKG")


# --- 1. reduce -------------------------------------------------------------------------------------

def reduce_isolated_edges(should_rebuild=False):
    """Drive graph cut to its largest strongly connected component (every kept node can be both
    reached and left by car). Skipped if the reduced graph exists (unless should_rebuild)."""
    if is_already_built([config.REDUCED_DRIVE_GRAPH_PATH], should_rebuild):
        return
    config.ROUTING_GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    drive_graph = _load_graph(config.DRIVE_GRAPH_PATH)
    n_nodes_before = drive_graph.number_of_nodes()
    weak = max(nx.weakly_connected_components(drive_graph), key=len)
    strong = max(nx.strongly_connected_components(drive_graph), key=len)
    print(f"drive: {n_nodes_before:,} nodes | largest weak {len(weak):,} | strong {len(strong):,}")

    drive_graph.remove_nodes_from([node for node in drive_graph if node not in strong])
    drive_graph.graph.update(built_at=datetime.now().isoformat(timespec='seconds'),
                             source=project_relative(config.DRIVE_GRAPH_PATH), component='strong',
                             n_nodes_before=n_nodes_before, n_nodes_after=len(strong),
                             weak_largest=len(weak))
    write_pickle(drive_graph, config.REDUCED_DRIVE_GRAPH_PATH)
    print(f"saved {config.REDUCED_DRIVE_GRAPH_PATH}: {drive_graph.number_of_nodes():,} nodes")


# --- 2. candidates ---------------------------------------------------------------------------------

def _link_finder(graph):
    """Function road -> link id. A link is a chain of roads through degree-2 nodes (one street
    between junctions), named by its smallest road key, so the result is deterministic."""
    undirected = graph.to_undirected(as_view=True)
    parent = {}

    def find(road):
        parent.setdefault(road, road)
        while parent[road] != road:
            parent[road] = parent[parent[road]]
            road = parent[road]
        return road

    for node in undirected.nodes:
        neighbours = [other for other in undirected.neighbors(node) if other != node]
        if len(neighbours) == 2:
            road_1, road_2 = (tuple(sorted((node, other))) for other in neighbours)
            root_1, root_2 = find(road_1), find(road_2)
            if root_1 != root_2:
                parent[max(root_1, root_2)] = min(root_1, root_2)
    return find


def _edges_to_gdf(graph, excluded_highway_types):
    """One straight line per edge (lon/lat), without edges of an excluded highway type."""
    rows = []
    for u, v, data in graph.edges(data=True):
        # chords are exact only on an unsimplified graph; fail loudly if that changes
        assert 'geometry' not in data, f"edge ({u}, {v}) has geometry; graph is simplified"
        highway = data.get(EDGE_HIGHWAY_ATTR)
        highways = set(highway) if isinstance(highway, list) else {highway}
        if highways & excluded_highway_types:
            continue
        line = LineString([(graph.nodes[u][NODE_LON_ATTR], graph.nodes[u][NODE_LAT_ATTR]),
                           (graph.nodes[v][NODE_LON_ATTR], graph.nodes[v][NODE_LAT_ATTR])])
        rows.append({EDGE_U_COL: u, EDGE_V_COL: v,
                     EDGE_HIGHWAY_ATTR: highway if not isinstance(highway, list) else ",".join(map(str, highway)),
                     GEOMETRY_COL: line})
    return gpd.GeoDataFrame(rows, crs=config.GEOGRAPHIC_CRS)


def _nearest_roads_per_hex(centroids_df, edges_gdf, tree):
    """Per hex: every road within the nearest road's distance + CANDIDATE_TIE_WINDOW_M, ranked by
    distance, one per link, the first CANDIDATES_PER_HEX kept."""
    u, v = edges_gdf[EDGE_U_COL].to_numpy(), edges_gdf[EDGE_V_COL].to_numpy()
    edges_gdf = edges_gdf.assign(**{ROAD_A_COL: np.minimum(u, v),
                                    ROAD_B_COL: np.maximum(u, v)}).reset_index(drop=True)
    geoms = edges_gdf.geometry.to_numpy()
    hex_ids = centroids_df[HEX_ID_COL].to_numpy()

    transformer = Transformer.from_crs(config.GEOGRAPHIC_CRS, config.METRIC_CRS, always_xy=True)
    x, y = transformer.transform(centroids_df[CENTROID_LON_COL].to_numpy(),
                                 centroids_df[CENTROID_LAT_COL].to_numpy())
    points = shapely.points(x, y)

    # nearest road distance per hex
    (hex_ix, _), nearest_dist_m = tree.query_nearest(points, max_distance=None, return_distance=True)
    min_dist_m = np.full(len(points), np.inf)
    np.minimum.at(min_dist_m, hex_ix, nearest_dist_m)
    is_found = np.isfinite(min_dist_m)
    skipped = hex_ids[~is_found].astype(int).tolist()

    # every road inside each hex's tie window
    found_ix = np.flatnonzero(is_found)
    hex_ix, edge_ix = tree.query(points[found_ix], predicate='dwithin',
                                 distance=min_dist_m[found_ix] + config.CANDIDATE_TIE_WINDOW_M)
    hex_ix = found_ix[hex_ix]
    dist_m = shapely.distance(points[hex_ix], geoms[edge_ix])

    # rank, one per link, keep
    candidates = (edges_gdf.iloc[edge_ix].reset_index(drop=True)
                  .assign(**{ROAD_DIST_COL: dist_m, CANDIDATE_HEX_COL: hex_ids[hex_ix].astype(int)})
                  .sort_values([CANDIDATE_HEX_COL, ROAD_DIST_COL, ROAD_A_COL, ROAD_B_COL], kind='stable')
                  .drop_duplicates([CANDIDATE_HEX_COL, LINK_A_COL, LINK_B_COL])
                  .groupby(CANDIDATE_HEX_COL, sort=False).head(config.CANDIDATES_PER_HEX)
                  .reset_index(drop=True))
    candidates = gpd.GeoDataFrame(candidates, geometry=GEOMETRY_COL, crs=config.METRIC_CRS)

    print(f"hexes: {len(points):,} | skipped (no road found): {len(skipped):,}")
    return candidates


def find_split_candidate_edges(subject_lat=None, subject_lon=None, should_rebuild=False):
    """Each hex's candidate roads (motorways excluded). Skipped if the candidate table exists
    (unless should_rebuild)."""
    subject_lat, subject_lon = resolve_subject(subject_lat, subject_lon)
    candidates_path = _subject_path(config.NEAREST_DRIVE_EDGES_PATH, subject_lat, subject_lon)
    if is_already_built([candidates_path], should_rebuild):
        return

    centroids_df = gpd.read_file(subject_file(config.HEX_GRID_POP_PATH, subject_lat, subject_lon, all_layers_tags())
                                 )[[HEX_ID_COL, CENTROID_LAT_COL, CENTROID_LON_COL]]
    assert centroids_df[HEX_ID_COL].is_unique, "duplicate hex_id in centroids"

    drive_graph = _load_graph(config.REDUCED_DRIVE_GRAPH_PATH)
    find_link = _link_finder(drive_graph)
    edges_gdf = _edges_to_gdf(drive_graph, config.CANDIDATE_EXCLUDED_HIGHWAY_TYPES)
    road_key = (np.minimum(edges_gdf[EDGE_U_COL], edges_gdf[EDGE_V_COL]).astype(str) + '_'
                + np.maximum(edges_gdf[EDGE_U_COL], edges_gdf[EDGE_V_COL]).astype(str))
    edges_gdf = edges_gdf[~road_key.duplicated()].reset_index(drop=True)   # one row per two-way road

    links = [find_link((min(u, v), max(u, v))) for u, v in zip(edges_gdf[EDGE_U_COL], edges_gdf[EDGE_V_COL])]
    edges_gdf[LINK_A_COL], edges_gdf[LINK_B_COL] = map(list, zip(*links))
    del drive_graph
    edges_gdf = edges_gdf.to_crs(config.METRIC_CRS)
    tree = STRtree(edges_gdf.geometry.values)
    candidates = _nearest_roads_per_hex(centroids_df, edges_gdf, tree)
    _write_gpkg(candidates, candidates_path)


# --- 3. split --------------------------------------------------------------------------------------

def _interpolate_latlon(lat1, lon1, lat2, lon2, fraction):
    lat = lat1 + (lat2 - lat1) * fraction
    lon = lon1 + (lon2 - lon1) * fraction
    return lat, lon


def _check_split(graph, split_graph, chains):
    """Each direction's pieces add up to the original length; new nodes have one in and one out
    edge per direction; edge count grows by exactly the pieces added."""
    added = 0
    for (road_a, road_b), (nodes, directions) in chains.items():
        for p, q in directions:
            assert not split_graph.has_edge(p, q), (p, q)
            path = [road_a, *nodes, road_b] if (p, q) == (road_a, road_b) else [road_b, *nodes[::-1], road_a]
            total_m = sum(split_graph.edges[x, y][EDGE_LENGTH_ATTR] for x, y in zip(path[:-1], path[1:]))
            assert abs(total_m - graph.edges[p, q][EDGE_LENGTH_ATTR]) < SPLIT_LENGTH_TOL_M, (p, q)
            added += len(nodes)
        if graph.is_directed():
            n_directions = len(directions)
            for node in nodes:
                assert (split_graph.in_degree(node) == n_directions
                        and split_graph.out_degree(node) == n_directions), (node, road_a, road_b)
    assert split_graph.number_of_edges() == graph.number_of_edges() + added
    print("edge count and per-direction lengths preserved;", len(chains), "roads split")


def _split_roads(graph, candidates):
    """Cut each candidate road longer than ROAD_PIECE_MAX_M into equal pieces; both directions share
    the same new nodes. Returns the split graph, chains {road: (new nodes, directions)} and counts."""
    assert config.SPLIT_NODE_ID_START > max(graph.nodes), "SPLIT_NODE_ID_START collides with existing node IDs"
    roads = sorted(set(zip(candidates[ROAD_A_COL].astype('int64'),
                           candidates[ROAD_B_COL].astype('int64'))))

    new_id = itertools.count(config.SPLIT_NODE_ID_START)
    split_graph = graph.copy()
    chains, stats = {}, Counter()

    for road_a, road_b in roads:
        if graph.is_directed():
            directions = [e for e in ((road_a, road_b), (road_b, road_a)) if graph.has_edge(*e)]
        else:
            directions = [(road_a, road_b)] if graph.has_edge(road_a, road_b) else []
        if not directions:
            stats['missing'] += 1
            continue

        lengths_m = [graph.edges[e][EDGE_LENGTH_ATTR] for e in directions]
        if len(lengths_m) == 2:
            assert abs(lengths_m[0] - lengths_m[1]) < TWO_WAY_LENGTH_TOL_M, (road_a, road_b, lengths_m)
        if lengths_m[0] <= config.ROAD_PIECE_MAX_M:
            stats['short'] += 1
            continue

        n_pieces = math.ceil(lengths_m[0] / config.ROAD_PIECE_MAX_M)
        lat1, lon1 = graph.nodes[road_a][NODE_LAT_ATTR], graph.nodes[road_a][NODE_LON_ATTR]
        lat2, lon2 = graph.nodes[road_b][NODE_LAT_ATTR], graph.nodes[road_b][NODE_LON_ATTR]
        nodes = []
        for i in range(1, n_pieces):
            lat, lon = _interpolate_latlon(lat1, lon1, lat2, lon2, i / n_pieces)
            node_id = next(new_id)
            split_graph.add_node(node_id, **{NODE_LAT_ATTR: lat, NODE_LON_ATTR: lon},
                                 synthetic=True, parent_a=road_a, parent_b=road_b)
            nodes.append(node_id)

        for p, q in directions:
            data = dict(graph.edges[p, q])
            unscaled = UNSCALED_EDGE_ATTRS & data.keys()
            assert not unscaled, f"({p}, {q}) carries {unscaled}; would be copied unscaled"
            path = [road_a, *nodes, road_b] if (p, q) == (road_a, road_b) else [road_b, *nodes[::-1], road_a]
            piece_m = data[EDGE_LENGTH_ATTR] / n_pieces
            split_graph.remove_edge(p, q)
            for x, y in zip(path[:-1], path[1:]):
                split_graph.add_edge(x, y, **{**data, EDGE_LENGTH_ATTR: piece_m})

        chains[(road_a, road_b)] = (nodes, directions)
        stats['two_way' if len(directions) == 2 else 'one_way'] += 1

    return split_graph, chains, stats


def split_edges(subject_lat=None, subject_lon=None, should_rebuild=False):
    """Reduced graph with every candidate road split. Skipped if the split graph and its chains exist
    (unless should_rebuild)."""
    subject_lat, subject_lon = resolve_subject(subject_lat, subject_lon)
    graph_path = config.REDUCED_DRIVE_GRAPH_PATH
    candidates_path, split_path, chains_path = (
        _subject_path(p, subject_lat, subject_lon)
        for p in (config.NEAREST_DRIVE_EDGES_PATH, config.SPLIT_DRIVE_GRAPH_PATH, config.SPLIT_DRIVE_CHAINS_PATH))
    if is_already_built([split_path, chains_path], should_rebuild):
        return
    assert graph_path.exists(), f"{graph_path} missing"
    assert candidates_path.exists(), f"{candidates_path} missing; run find_split_candidate_edges"

    candidates = gpd.read_file(candidates_path)
    graph = _load_graph(graph_path)
    split_graph, chains, stats = _split_roads(graph, candidates)
    n_roads = candidates[[ROAD_A_COL, ROAD_B_COL]].drop_duplicates().shape[0]
    print("drive:", dict(stats), "| roads in candidates:", n_roads, "| piece max (m):", config.ROAD_PIECE_MAX_M)
    assert stats['missing'] == 0, "candidates don't match this graph"
    assert sum(stats.values()) == n_roads
    _check_split(graph, split_graph, chains)

    print(f"drive graph: {graph.number_of_nodes():,} -> {split_graph.number_of_nodes():,} nodes, "
          f"{graph.number_of_edges():,} -> {split_graph.number_of_edges():,} edges")

    split_graph.graph.update(split_from=project_relative(graph_path),
                             split_candidates=project_relative(candidates_path),
                             split_threshold_m=config.ROAD_PIECE_MAX_M,
                             split_at=datetime.now().isoformat(timespec='seconds'))
    write_pickle(split_graph, split_path)
    write_pickle(chains, chains_path)
    print(f"saved {split_path}")

    del graph, split_graph, chains
    gc.collect()


# --- 4. hex -> node --------------------------------------------------------------------------------

def _assign_nodes(hex_ids, hex_x, hex_y, transformer, split_path, chains_path, candidates_path):
    """Project each hex centroid onto each of its candidate roads and round to the nearest piece node.
    node_dist is measured to the piece node's position on the straight road, in metres."""
    candidates = gpd.read_file(candidates_path, ignore_geometry=True)
    candidates = candidates.sort_values([CANDIDATE_HEX_COL, ROAD_DIST_COL], kind="stable")
    candidates["rank"] = candidates.groupby(CANDIDATE_HEX_COL).cumcount() + 1
    candidates = candidates[candidates["rank"] <= config.CANDIDATES_PER_HEX].reset_index(drop=True)
    road_a = candidates[ROAD_A_COL].to_numpy("int64")
    road_b = candidates[ROAD_B_COL].to_numpy("int64")

    # endpoint coordinates only; the graph isn't needed after this
    split_graph = _load_graph(split_path)
    ends = np.unique(np.concatenate([road_a, road_b]))
    end_x, end_y = transformer.transform(np.array([split_graph.nodes[n][NODE_LON_ATTR] for n in ends]),
                                         np.array([split_graph.nodes[n][NODE_LAT_ATTR] for n in ends]))
    del split_graph
    gc.collect()
    ends_index = pd.Index(ends)
    a_ix, b_ix = ends_index.get_indexer(road_a), ends_index.get_indexer(road_b)
    ax, ay, bx, by = end_x[a_ix], end_y[a_ix], end_x[b_ix], end_y[b_ix]

    # pieces per road, and a flat table of split nodes by position
    with open(chains_path, "rb") as f:
        chains = pickle.load(f)
    pieces = pd.Series([len(nodes) + 1 for nodes, _ in chains.values()],
                       index=pd.MultiIndex.from_tuples(list(chains.keys())))
    n_pieces = pieces.reindex(pd.MultiIndex.from_arrays([road_a, road_b])).fillna(1).to_numpy("int64")
    chain_nodes_df = pd.DataFrame([(ra, rb, k, node) for (ra, rb), (nodes, _) in chains.items()
                                   for k, node in enumerate(nodes, start=1)],
                                  columns=[ROAD_A_COL, ROAD_B_COL, "k", "node"])

    # project each centroid onto its road, round to the nearest node
    hex_ix = pd.Index(hex_ids).get_indexer(candidates[CANDIDATE_HEX_COL])
    px, py = hex_x[hex_ix], hex_y[hex_ix]
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / np.where(length_sq > 0, length_sq, 1), 0, 1)
    k = np.rint(t * n_pieces).astype("int64")
    node_dist_m = np.hypot(px - (ax + dx * k / n_pieces), py - (ay + dy * k / n_pieces))

    node = np.where(k == 0, road_a, np.where(k == n_pieces, road_b, -1))
    is_mid = node == -1
    if is_mid.any():
        lookup = pd.DataFrame({ROAD_A_COL: road_a[is_mid], ROAD_B_COL: road_b[is_mid], "k": k[is_mid]})
        hit = lookup.merge(chain_nodes_df, on=[ROAD_A_COL, ROAD_B_COL, "k"], how="left")["node"]
        assert hit.notna().all(), "split node missing from chains"
        node[is_mid] = hit.to_numpy("int64")

    # long -> wide: drive_node_1, drive_node_2, drive_road_dist_1_m, ...
    long_df = pd.DataFrame({HEX_ID_COL: candidates[CANDIDATE_HEX_COL].to_numpy(),
                            "rank": candidates["rank"].to_numpy(), "node": node,
                            "road_dist": candidates[ROAD_DIST_COL].to_numpy(), "node_dist": node_dist_m})
    wide_df = long_df.pivot(index=HEX_ID_COL, columns="rank")
    wide_df.columns = [_node_col(quantity, rank) for quantity, rank in wide_df.columns]
    print(f"drive: {len(wide_df):,} hexes assigned")
    return wide_df.reset_index()


def centroid_node_assignment(subject_lat=None, subject_lon=None, should_rebuild=False):
    """Filled hex grid plus each hex's candidate nodes and distances. Skipped if the hex-node table
    exists (unless should_rebuild)."""
    subject_lat, subject_lon = resolve_subject(subject_lat, subject_lon)
    hex_nodes_path = _subject_path(config.HEX_NODES_PATH, subject_lat, subject_lon)
    if is_already_built([hex_nodes_path], should_rebuild):
        return
    split_path, chains_path, candidates_path = (
        _subject_path(p, subject_lat, subject_lon)
        for p in (config.SPLIT_DRIVE_GRAPH_PATH, config.SPLIT_DRIVE_CHAINS_PATH, config.NEAREST_DRIVE_EDGES_PATH))
    for path in (split_path, chains_path, candidates_path):
        assert path.exists(), f"{path} missing"

    transformer = Transformer.from_crs(config.GEOGRAPHIC_CRS, config.METRIC_CRS, always_xy=True)
    centroids_gdf = gpd.read_file(subject_file(config.HEX_GRID_POP_PATH, subject_lat, subject_lon, all_layers_tags()))
    hex_x, hex_y = transformer.transform(centroids_gdf[CENTROID_LON_COL].values,
                                         centroids_gdf[CENTROID_LAT_COL].values)
    hex_ids = centroids_gdf[HEX_ID_COL].to_numpy()

    nodes_df = _assign_nodes(hex_ids, hex_x, hex_y, transformer, split_path, chains_path, candidates_path)
    node_cols = [_node_col("node", rank) for rank in range(1, config.CANDIDATES_PER_HEX + 1)]
    nodes_df[node_cols] = nodes_df[node_cols].astype("Int64")

    # --- checks printed ---
    first_node_col, second_node_col = node_cols[0], node_cols[1]
    missing = len(centroids_gdf) - nodes_df[first_node_col].notna().sum()
    if missing:
        print(f"WARNING: {missing:,} hexes had no drive node")
    same = (nodes_df[first_node_col].fillna(-1) == nodes_df[second_node_col].fillna(-2)).sum()
    print(f"{same:,} hexes with {first_node_col} == {second_node_col}")

    road_dist_col = _node_col("road_dist", 1)
    print("\ndrive snap distance (m):")
    print(nodes_df[road_dist_col].describe(percentiles=[.5, .9, .99]).to_string())
    farthest = nodes_df.nlargest(10, road_dist_col)[[HEX_ID_COL, road_dist_col]]
    print(f"farthest 10:\n{farthest.to_string(index=False)}")

    # --- merge and save ---
    out_gdf = centroids_gdf.merge(nodes_df, on=HEX_ID_COL, how="left")
    n_missing = out_gdf[first_node_col].isna().sum()
    if n_missing:
        print(f"WARNING: {n_missing:,} NaN node assignments after merge")
    _write_gpkg(out_gdf, hex_nodes_path)
    print(f"\nsaved {hex_nodes_path}")
