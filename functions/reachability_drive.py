"""Drive reachability, band 3 (RCH-2, RCH-15..17): one search per venue hex on the reversed fitted drive graph,
node-level routed costs stored out to a multiple of the band cut, and the edge flag (DESIGN.md Q5)."""
import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

import config
from functions.drive_model_fit import edge_groups
from functions.drive_routing import MIN_CSR_WEIGHT, TIME_ATTR
from functions.routing_bundle import get_bundle

HEX_ID_COL = "hex_id"
DRIVE_NODE_1_COL, DRIVE_NODE_2_COL = "drive_node_1", "drive_node_2"
DRIVE_ROAD_DIST_1_COL, DRIVE_ROAD_DIST_2_COL = "drive_road_dist_1_m", "drive_road_dist_2_m"
SOURCE_HEX_COL = "source_hex"          # stored rows: venue hex searched from (int32)
NODE_COL = "node"                      # stored rows: CSR row of the reached node (int32; bundle nodes[row] = OSM id)
COST_COL = "cost_s"                    # stored rows: routed seconds, rounded up (uint16)
NO_SECOND_ROW = -1
COORD_LAT_KEY, COORD_LON_KEY = "lat", "lon"


def fitted_reverse_matrix(bundle_path, attrs_path, params_path):
    """The fitted drive graph (DCL-1..3, as drive_model_fit builds it: blind time_raw_s x m on the scaled groups'
    edges, + beta per signalised head node), reversed for hex -> venue searches (RCH-16). Returns (matrix, nodes,
    params)."""
    params = json.loads(params_path.read_text(encoding="utf-8"))
    bundle = get_bundle(bundle_path)
    with np.load(attrs_path) as attrs:
        group = edge_groups(attrs, tuple(map(tuple, params["groups"])), params["edge_set"])
    scale = np.concatenate([[1.0], params["multipliers"]])[group]
    weight = np.maximum(np.asarray(bundle.raw_weights[TIME_ATTR]) * scale
                        + params["beta"] * bundle.signals[bundle.indices].astype(float), MIN_CSR_WEIGHT)
    matrix = csr_matrix((weight, bundle.indices, bundle.indptr), shape=(len(bundle.nodes),) * 2)
    return matrix.T.tocsr(), np.asarray(bundle.nodes), params


def eligible_rows(hex_df, nodes):
    """Per hex, the CSR rows a trip may end on (drive_routing.eligible_nodes, vectorised): node 1, and node 2 when
    its road is within config.CANDIDATE_TIE_WINDOW_M of node 1's and it is a different node (else NO_SECOND_ROW)."""
    node_1 = hex_df[DRIVE_NODE_1_COL].to_numpy(np.int64)
    node_2 = hex_df[DRIVE_NODE_2_COL].to_numpy(float)
    row_1 = np.searchsorted(nodes, node_1)
    assert np.array_equal(nodes[np.minimum(row_1, len(nodes) - 1)], node_1), "a hex's node 1 is not in the bundle"
    is_2 = (~np.isnan(node_2) & (node_2 != node_1)
            & (hex_df[DRIVE_ROAD_DIST_2_COL].to_numpy() - hex_df[DRIVE_ROAD_DIST_1_COL].to_numpy()
               <= config.CANDIDATE_TIE_WINDOW_M))
    row_2 = np.where(is_2, np.searchsorted(nodes, np.nan_to_num(node_2).astype(np.int64)), NO_SECOND_ROW)
    assert np.array_equal(nodes[row_2[is_2]], node_2[is_2].astype(np.int64)), "a hex's node 2 is not in the bundle"
    return row_1, row_2


def node_coordinates(graph_path, nodes, coords_path):
    """Lat and lon of every bundle node (CSR order), read once from the timed graph and saved to coords_path."""
    if coords_path.exists():
        with np.load(coords_path) as coords:
            return coords[COORD_LAT_KEY], coords[COORD_LON_KEY]
    import pickle
    with open(graph_path, "rb") as file:
        graph = pickle.load(file)
    lat = np.array([graph.nodes[node]["y"] for node in nodes.tolist()])
    lon = np.array([graph.nodes[node]["x"] for node in nodes.tolist()])
    del graph
    np.savez(coords_path, **{COORD_LAT_KEY: lat, COORD_LON_KEY: lon})
    return lat, lon


def boundary_rows(lat, lon, edge_flag_m):
    """CSR rows of the nodes within edge_flag_m of the drive graph's outer boundary, taken as the convex hull of
    every node (metres in config.METRIC_CRS). Returns (rows, hull vertex count)."""
    from pyproj import Transformer
    from scipy.spatial import ConvexHull
    x, y = Transformer.from_crs(config.GEOGRAPHIC_CRS, config.METRIC_CRS, always_xy=True).transform(lon, lat)
    points = np.column_stack([x, y])
    hull = ConvexHull(points)
    corners = points[hull.vertices]
    starts, ends = corners, np.roll(corners, -1, axis=0)
    near = np.zeros(len(points), bool)
    for start, end in zip(starts, ends):
        segment = end - start
        t = np.clip(((points - start) @ segment) / (segment @ segment), 0, 1)
        near |= np.hypot(*(points - start - t[:, None] * segment).T) <= edge_flag_m
    return np.flatnonzero(near), len(corners)


def search_venue_hexes(reverse, sources_by_hex, limit_s, out_path, boundary, writer_schema):
    """One multi-source search per venue hex (min over its eligible rows), rows with cost <= limit_s written to
    out_path (one row group per hex). Returns the per-hex manifest rows."""
    is_boundary = np.zeros(reverse.shape[0], bool)
    is_boundary[boundary] = True
    records = []
    with pq.ParquetWriter(out_path, writer_schema, compression="zstd") as writer:
        for hex_id, sources in sources_by_hex:
            dist = dijkstra(reverse, directed=True, indices=sources, min_only=True, limit=limit_s)
            reached = np.flatnonzero(dist <= limit_s)
            cost_s = np.ceil(dist[reached])
            writer.write_table(pa.table({SOURCE_HEX_COL: np.full(len(reached), hex_id, np.int32),
                                         NODE_COL: reached.astype(np.int32), COST_COL: cost_s.astype(np.uint16)},
                                        schema=writer_schema))
            on_boundary = is_boundary[reached]
            records.append({HEX_ID_COL: hex_id, "n_nodes": len(reached), "max_cost_s": float(cost_s.max()),
                            "is_edge": bool(on_boundary.any()),
                            "min_boundary_cost_s": float(cost_s[on_boundary].min()) if on_boundary.any() else np.nan})
    return records


def stored_schema():
    return pa.schema([(SOURCE_HEX_COL, pa.int32()), (NODE_COL, pa.int32()), (COST_COL, pa.uint16())])


def venue_hex_sources(hex_df, venue_hex_ids, row_1, row_2):
    """(hex_id, [eligible rows]) for every venue hex, in hex_id order; asserts each is on the hex nodes table."""
    position = pd.Series(np.arange(len(hex_df)), index=hex_df[HEX_ID_COL].to_numpy())
    missing = np.setdiff1d(venue_hex_ids, position.index.to_numpy())
    assert not len(missing), f"{len(missing)} venue hexes not on the hex nodes table (RCH-5)"
    out = []
    for hex_id in np.sort(venue_hex_ids):
        pos = position[hex_id]
        out.append((int(hex_id), [int(row_1[pos])] + ([int(row_2[pos])] if row_2[pos] != NO_SECOND_ROW else [])))
    return out
