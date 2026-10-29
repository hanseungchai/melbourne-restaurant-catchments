"""Drive road graph built from the OSM extract (main.py stage map_construction).

Reads config.ROAD_EXTRACT_PBF_PATH; writes config.DRIVE_GRAPH_PATH (directed networkx DiGraph,
respects oneway). Nodes carry x (lon) and y (lat); edges carry length (m), highway and the raw
maxspeed tag. The walk graph built in the same pass is parked (docs/parked_code/walk_graph.md;
concepts/walk.md WLK-5): walking runs on r5py.
"""
from datetime import datetime

import networkx as nx
import numpy as np
import osmium

import config
from functions.geometry import haversine_m
from functions.output_helper import is_already_built, project_relative, write_pickle

# OSM tag keys and values read from each way
HIGHWAY_TAG = 'highway'
AREA_TAG = 'area'
ONEWAY_TAG = 'oneway'
JUNCTION_TAG = 'junction'
MAXSPEED_TAG = 'maxspeed'
MOTOR_VEHICLE_ACCESS_TAG = 'motor_vehicle'
VEHICLE_ACCESS_TAG = 'vehicle'
ACCESS_TAG = 'access'
AREA_YES_VALUE = 'yes'
ONEWAY_FORWARD_VALUES = ('yes', 'true', '1')
ONEWAY_REVERSE_VALUE = '-1'                        # one-way against the way's node order
ONEWAY_JUNCTION_VALUES = ('roundabout', 'circular')  # one-way when oneway is untagged
ONEWAY_IMPLIED_HIGHWAY = 'motorway'                  # one-way when oneway is untagged

# Graph schema (read downstream by routing_graph.py and speed_graphs.py)
NODE_LON_ATTR = 'x'
NODE_LAT_ATTR = 'y'
EDGE_LENGTH_ATTR = 'length'        # metres
EDGE_HIGHWAY_ATTR = 'highway'
EDGE_MAXSPEED_ATTR = 'maxspeed'    # raw tag, unparsed; no assumed speed applied
GRAPH_SOURCE_KEY = 'source_pbf'
GRAPH_BUILT_AT_KEY = 'built_at'

PROGRESS_EVERY_N_WAYS = 50_000
TOP_COMPONENTS_SHOWN = 20


def is_excluded_by_access(tags):
    """True if the way's access tags bar motor vehicles."""
    access_value = tags.get(MOTOR_VEHICLE_ACCESS_TAG) or tags.get(VEHICLE_ACCESS_TAG)
    access_value = access_value or tags.get(ACCESS_TAG)
    return access_value in config.NO_ACCESS_VALUES


class NetworkBuilder(osmium.SimpleHandler):
    """Reads highway ways and adds one edge per consecutive node pair to the drive graph."""

    def __init__(self):
        super().__init__()
        self.drive_graph = nx.DiGraph()  # directed, to respect oneway streets
        self.way_count = 0

    def way(self, w):
        highway = w.tags.get(HIGHWAY_TAG)
        if highway is None or highway in config.UNUSABLE_HIGHWAY_TYPES:
            return
        tags = {t.k: t.v for t in w.tags}

        if tags.get(AREA_TAG) == AREA_YES_VALUE:  # areas (plazas) are never driven
            return

        try:
            node_ids = [n.ref for n in w.nodes]
            coords = [(n.lat, n.lon) for n in w.nodes]
        except osmium.InvalidLocationError:
            return

        if len(node_ids) < 2:
            return

        oneway_tag = tags.get(ONEWAY_TAG)
        is_implied_oneway = tags.get(JUNCTION_TAG) in ONEWAY_JUNCTION_VALUES \
            or highway == ONEWAY_IMPLIED_HIGHWAY
        is_oneway_reverse = oneway_tag == ONEWAY_REVERSE_VALUE
        is_oneway = oneway_tag in ONEWAY_FORWARD_VALUES or (oneway_tag is None and is_implied_oneway)

        is_drivable = highway in config.DRIVE_HIGHWAY_TYPES and not is_excluded_by_access(tags)

        if is_drivable:
            lats, lons = np.array(coords).T
            segment_lengths_m = haversine_m(lats[:-1], lons[:-1], lats[1:], lons[1:]).tolist()
            maxspeed_raw = tags.get(MAXSPEED_TAG)
            for i in range(len(node_ids) - 1):
                node_a, node_b = node_ids[i], node_ids[i + 1]
                lat_a, lon_a = coords[i]
                lat_b, lon_b = coords[i + 1]
                self.drive_graph.add_node(node_a, **{NODE_LAT_ATTR: lat_a, NODE_LON_ATTR: lon_a})
                self.drive_graph.add_node(node_b, **{NODE_LAT_ATTR: lat_b, NODE_LON_ATTR: lon_b})

                edge_attrs = {EDGE_LENGTH_ATTR: segment_lengths_m[i], EDGE_HIGHWAY_ATTR: highway,
                              EDGE_MAXSPEED_ATTR: maxspeed_raw}
                if is_oneway_reverse:
                    self.drive_graph.add_edge(node_b, node_a, **edge_attrs)
                else:
                    self.drive_graph.add_edge(node_a, node_b, **edge_attrs)
                    if not is_oneway:
                        self.drive_graph.add_edge(node_b, node_a, **edge_attrs)

        self.way_count += 1
        if self.way_count % PROGRESS_EVERY_N_WAYS == 0:
            print(f"Processed {self.way_count} ways...")


def print_component_sizes(label, components, n_nodes):
    """Print the component count, the largest component's share and the largest component sizes."""
    sizes = sorted((len(c) for c in components), reverse=True)
    print(f"{label} connected components: {len(sizes)}")
    print(f"{label} largest component: {sizes[0]} / {n_nodes}")
    print(sizes[:TOP_COMPONENTS_SHOWN])


def build_road_graphs(should_rebuild=False):
    """Build the drive graph from the OSM extract and pickle it.
    Skipped if it exists (unless should_rebuild)."""
    if is_already_built([config.DRIVE_GRAPH_PATH], should_rebuild):
        return
    config.ROAD_GRAPHS_DIR.mkdir(parents=True, exist_ok=True)
    builder = NetworkBuilder()
    builder.apply_file(str(config.ROAD_EXTRACT_PBF_PATH), locations=True)  # resolves node lat/lon

    print(f"\nTotal ways processed: {builder.way_count}")
    print(f"Driving graph: {builder.drive_graph.number_of_nodes()} nodes, {builder.drive_graph.number_of_edges()} edges")
    print_component_sizes("Drive (weak)", nx.weakly_connected_components(builder.drive_graph),
                          builder.drive_graph.number_of_nodes())

    builder.drive_graph.graph.update({GRAPH_SOURCE_KEY: project_relative(config.ROAD_EXTRACT_PBF_PATH),
                                      GRAPH_BUILT_AT_KEY: datetime.now().isoformat(timespec='seconds')})
    write_pickle(builder.drive_graph, config.DRIVE_GRAPH_PATH)
    print(f"Saved {config.DRIVE_GRAPH_PATH}")
