"""Build speed graphs stage: signal flags and edge times on the subject's split drive graph.

enrich() reads the subject's split drive graph (config.SPLIT_DRIVE_GRAPH_PATH) and writes one timed
graph per drive model variant in config.SPEED_GRAPH_VARIANTS, named from config.TIMED_DRIVE_GRAPH_PATH
with the variant as suffix. A variant whose file exists is skipped unless should_rebuild.
1. Nodes: signals flag from the OSM traffic_signals nodes in config.ROAD_EXTRACT_PBF_PATH (the graph's
   own source extract, asserted); split nodes never carry a signal.
2. Nodes: Valhalla density level from the road-density raster, with road_density's rule; nodes
   outside the raster (outside the extract, asserted) get level 0.
3. Edges: density tier from the start node's level (as Valhalla), then speed_kmh and time_raw_s.
   blind, dense, dense_fringe: posted limit x a tier factor (none for config.UNREDUCED_HIGHWAY_TYPES),
   else the highway class's default speed;
   osmtable: the OpenStreetMapSpeeds AU-VIC table by tier (DESIGN_pre_spine "Drive layer").
"""
import json
import pickle
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import osmium

import config
from functions.density_levels import node_levels   # same density level rule as the hexes
from functions.drive_routing import HIGHWAY_ATTR, SPEED_SOURCE_ATTR, TAGGED_SOURCE
from functions.osm_tags import parse_maxspeed
from functions.output_helper import is_already_built, project_relative, write_pickle
from functions.subject_paths import all_layers_tags, subject_file

# Valhalla road classes (graphconstants.h RoadClass) and speed-table rules (speed_assigner.h)
ROAD_CLASS_BY_HIGHWAY = {"motorway": 0, "trunk": 1, "primary": 2, "secondary": 3,
                         "tertiary": 4, "unclassified": 5, "residential": 6}
OTHER_ROAD_CLASS = 7                             # service and everything else
LINK_SUFFIX = "_link"
LINK_EXITING_HIGHWAY_TYPES = {"motorway_link", "trunk_link"}   # signage proxy
ROUNDABOUT_JUNCTIONS = ("roundabout", "circular")
KMH_PER_M_S = 3.6

# Density tiers stored on each edge (density_tier). osmtable uses Valhalla's tiers, which are also the
# speed table's keys; the other variants split the levels at their own thresholds.
RURAL_TIER = "rural"                              # osmtable: levels 0-5
SUBURBAN_TIER = "suburban"                        # osmtable: levels 6-10
URBAN_TIER = "urban"                              # osmtable: levels 11-15
DENSE_URBAN_TIER = "dense_urban"                  # level 15
FRINGE_URBAN_TIER = "fringe_urban"                # dense_fringe: levels 12-14
BELOW_DENSE_URBAN_TIER = "below_dense_urban"      # blind, dense: levels 0-14
BELOW_FRINGE_URBAN_TIER = "below_fringe_urban"    # dense_fringe: levels 0-11
NO_LEVEL_TIER = "default"                         # tier_valhalla: node without a density level

# Graph attribute names: read from the split graph (OSM tags, length, coordinates) and written here
MAXSPEED_ATTR = "maxspeed"
JUNCTION_ATTR = "junction"
LENGTH_ATTR = "length"                            # metres
SYNTHETIC_ATTR = "synthetic"                      # split node (no OSM id)
SOURCE_PBF_KEY = "source_pbf"                     # graph metadata: extract the graph was built from
SIGNALS_ATTR = "signals"                          # node: OSM traffic signal
DENSITY_TIER_ATTR = "density_tier"
URBAN_ATTR = "urban"
SPEED_KMH_ATTR = "speed_kmh"
TIME_RAW_S_ATTR = "time_raw_s"                    # length / speed, before signal penalties

# speed_source values
DEFAULT_SOURCE = "default"                        # class default speed
TABLE_SOURCE = "table"                            # osmtable speed table

# OSM node tags
TRAFFIC_SIGNALS_VALUE = "traffic_signals"
STOP_VALUE = "stop"
SERVICE_HIGHWAY = "service"                       # class used for highway types missing from the defaults

# Speed table entry keys (OpenStreetMapSpeeds)
WAY_KEY = "way"
ROUNDABOUT_KEY = "roundabout"
LINK_EXITING_KEY = "link_exiting"
LINK_TURNING_KEY = "link_turning"

# Density raster keys (written by road_density.build_density_raster)


def load_speed_table(speed_table_path, country=config.OSM_SPEED_TABLE_COUNTRY, state=config.OSM_SPEED_TABLE_STATE):
    speed_tables = json.load(open(speed_table_path))
    # Valhalla's order: country+state, then country, then global
    for iso_codes in ((country, state), (country, None), (None, None)):
        for table in speed_tables:
            if (table.get("iso3166-1"), table.get("iso3166-2")) == iso_codes:
                return table
    raise KeyError("no matching speed table")


def table_kmh(speed_table, highway, tier, roundabout=False):
    tier_table = speed_table[tier]
    if highway.endswith(LINK_SUFFIX):
        road_class = ROAD_CLASS_BY_HIGHWAY.get(highway.removesuffix(LINK_SUFFIX))
        if road_class is not None and road_class < config.FIRST_ROAD_CLASS_WITHOUT_LINK_SPEED:
            speed_kmh = (tier_table[LINK_EXITING_KEY] if highway in LINK_EXITING_HIGHWAY_TYPES
                         else tier_table[LINK_TURNING_KEY])[road_class]
            if speed_kmh is not None:
                return speed_kmh
        highway = highway.removesuffix(LINK_SUFFIX)                   # parent class
    road_class = ROAD_CLASS_BY_HIGHWAY.get(highway, OTHER_ROAD_CLASS)
    if roundabout:
        speed_kmh = tier_table[ROUNDABOUT_KEY][road_class]
        return speed_kmh if speed_kmh is not None else tier_table[WAY_KEY][road_class] * config.ROUNDABOUT_SPEED_FACTOR
    return tier_table[WAY_KEY][road_class]


def tier_dense(level):
    if np.isfinite(level) and level >= config.ROAD_DENSITY_MAX_LEVEL:
        return DENSE_URBAN_TIER
    return BELOW_DENSE_URBAN_TIER


def tier_fringe(level):
    if level >= config.ROAD_DENSITY_MAX_LEVEL: return DENSE_URBAN_TIER
    if level >= config.FRINGE_MIN_DENSITY_LEVEL: return FRINGE_URBAN_TIER
    return BELOW_FRINGE_URBAN_TIER


def tier_valhalla(level):
    if np.isnan(level):
        return NO_LEVEL_TIER
    if level <= config.ROAD_DENSITY_MIN_SUBURBAN_LEVEL:
        return RURAL_TIER
    if not np.isfinite(level):
        raise ValueError(f"node has no density level: {level}")
    return SUBURBAN_TIER if level <= config.ROAD_DENSITY_MAX_SUBURBAN_LEVEL else URBAN_TIER


class SignalCollector(osmium.SimpleHandler):
    """Read-only pass over nodes; collects OSM ids of signalised intersections."""

    def __init__(self):
        super().__init__()
        self.signals = set()
        self.stops = set()

    def node(self, osm_node):
        highway = osm_node.tags.get(HIGHWAY_ATTR)
        if highway == TRAFFIC_SIGNALS_VALUE:
            self.signals.add(osm_node.id)
        elif highway == STOP_VALUE:
            self.stops.add(osm_node.id)


def _default_speed_kmh(speed_by_highway, highway, fallback_kmh):
    if highway in speed_by_highway:
        return speed_by_highway[highway]
    parent_highway = highway.removesuffix(LINK_SUFFIX)
    if highway.endswith(LINK_SUFFIX) and parent_highway in speed_by_highway:   # e.g. residential_link -> residential
        return speed_by_highway[parent_highway]
    return speed_by_highway.get(SERVICE_HIGHWAY, fallback_kmh)                  # Valhalla: unlisted types are class 7


def _assign_speeds(drive_graph, level_by_node, tier_rule, rules_by_tier):
    edge_counts = Counter()
    unlisted_highway_counts = Counter()
    speeds_by_tier = {}
    for start_node, end_node, edge in drive_graph.edges(data=True):
        highway = edge.get(HIGHWAY_ATTR)
        tier = tier_rule(level_by_node[start_node])  # Valhalla: start node (graphenhancer.cc)
        speed_by_highway, fallback_kmh, posted_speed_factor = rules_by_tier[tier]
        edge[DENSITY_TIER_ATTR] = tier
        edge[URBAN_ATTR] = tier == DENSE_URBAN_TIER

        posted = parse_maxspeed(edge.get(MAXSPEED_ATTR))
        if posted is not None:
            kmh = posted if highway in config.UNREDUCED_HIGHWAY_TYPES else posted * posted_speed_factor
            edge[SPEED_SOURCE_ATTR] = TAGGED_SOURCE
        else:
            kmh = _default_speed_kmh(speed_by_highway, highway, fallback_kmh)
            edge[SPEED_SOURCE_ATTR] = DEFAULT_SOURCE
            if highway not in speed_by_highway:
                unlisted_highway_counts[(highway, tier)] += 1
        edge_counts[(edge[SPEED_SOURCE_ATTR], tier)] += 1
        speeds_by_tier.setdefault(tier, []).append(kmh)
        edge[SPEED_KMH_ATTR] = kmh
        edge[TIME_RAW_S_ATTR] = edge[LENGTH_ATTR] / (kmh / KMH_PER_M_S)

    n_edges_total = sum(edge_counts.values())
    print(f"  {'tier':<20}{'edges':>11}{'share':>8}{'tagged':>10}{'default':>10}{'mean km/h':>11}")
    for tier in speeds_by_tier:
        n_tagged = edge_counts[(TAGGED_SOURCE, tier)]
        n_default = edge_counts[(DEFAULT_SOURCE, tier)]
        n_edges = n_tagged + n_default
        print(f"  {tier:<20}{n_edges:>11,}{n_edges / n_edges_total:>8.1%}{n_tagged:>10,}{n_default:>10,}"
              f"{np.mean(speeds_by_tier[tier]):>11.1f}")
    if unlisted_highway_counts:
        print(f"  highway types falling to fallback: {dict(unlisted_highway_counts)}")

    if any(edge[SPEED_KMH_ATTR] <= 0 for _, _, edge in drive_graph.edges(data=True)):
        print("ERROR: Found zero or negative speeds")


def _assign_table_speeds(drive_graph, level_by_node, speed_table):
    edge_counts = Counter()
    for start_node, end_node, edge in drive_graph.edges(data=True):
        tier = tier_valhalla(level_by_node[start_node])            # Valhalla: start node
        assert tier != NO_LEVEL_TIER, f"edge {start_node}->{end_node} has no density level"
        kmh = table_kmh(speed_table, edge[HIGHWAY_ATTR], tier,
                        roundabout=edge.get(JUNCTION_ATTR) in ROUNDABOUT_JUNCTIONS)
        assert kmh > 0, f"edge {start_node}->{end_node}: non-positive speed {kmh}"
        edge[DENSITY_TIER_ATTR] = tier
        edge[URBAN_ATTR] = tier == URBAN_TIER
        edge[SPEED_SOURCE_ATTR] = TABLE_SOURCE
        edge[SPEED_KMH_ATTR] = kmh
        edge[TIME_RAW_S_ATTR] = edge[LENGTH_ATTR] / (kmh / KMH_PER_M_S)
        edge_counts[(tier, ROAD_CLASS_BY_HIGHWAY.get(edge[HIGHWAY_ATTR].removesuffix(LINK_SUFFIX), OTHER_ROAD_CLASS))] += 1
    print(f"  edges by (tier, road class): {dict(sorted(edge_counts.items()))}")


def enrich(subject_lat, subject_lon,
           speed_by_highway=config.DEFAULT_SPEED_KMH_BY_HIGHWAY,
           fallback_kmh=config.FALLBACK_SPEED_KMH,
           posted_speed_factor=config.POSTED_SPEED_FACTOR,
           urban_posted_speed_factor=config.URBAN_POSTED_SPEED_FACTOR,
           density_raster_path=config.ROAD_DENSITY_RASTER_PATH,
           timed_graph_stem=config.TIMED_DRIVE_GRAPH_PATH, variants=config.SPEED_GRAPH_VARIANTS,
           split_graph_path=config.SPLIT_DRIVE_GRAPH_PATH, should_rebuild=False):
    split_graph_path = subject_file(Path(split_graph_path), subject_lat, subject_lon, all_layers_tags())
    default_rules = (speed_by_highway, fallback_kmh, posted_speed_factor)
    urban_rules = (speed_by_highway, fallback_kmh, urban_posted_speed_factor)
    rules_by_variant = {
        "blind": (tier_dense, {BELOW_DENSE_URBAN_TIER: default_rules,
                               DENSE_URBAN_TIER: default_rules}),  # M0: no urban reduction
        "dense": (tier_dense, {BELOW_DENSE_URBAN_TIER: default_rules, DENSE_URBAN_TIER: urban_rules}),
        "dense_fringe": (tier_fringe, {
            BELOW_FRINGE_URBAN_TIER: default_rules,
            FRINGE_URBAN_TIER: (speed_by_highway, fallback_kmh, posted_speed_factor * config.FRINGE_FACTOR),
            DENSE_URBAN_TIER: urban_rules,
        }),
        "osmtable": (tier_valhalla, None)
    }
    if isinstance(variants, str):
        variants = (variants,)
    unknown = set(variants) - set(rules_by_variant)
    assert not unknown, f"unknown variants: {unknown}"
    selected_variants = {variant: rules for variant, rules in rules_by_variant.items() if variant in variants}

    # one graph per variant; a variant whose file exists is skipped unless should_rebuild
    timed_graph_stem = Path(timed_graph_stem)
    paths = {variant: subject_file(timed_graph_stem.with_name(
                 f"{timed_graph_stem.stem}_{variant}{timed_graph_stem.suffix}"),
                 subject_lat, subject_lon, all_layers_tags())
             for variant in selected_variants}
    selected_variants = {variant: rules for variant, rules in selected_variants.items()
                         if not is_already_built([paths[variant]], should_rebuild)}
    if not selected_variants:
        return paths

    print("Collecting signal nodes from PBF...")
    signal_collector = SignalCollector()
    signal_collector.apply_file(str(config.ROAD_EXTRACT_PBF_PATH))
    print(f"  traffic_signals: {len(signal_collector.signals):,}   stop signs: {len(signal_collector.stops):,}")

    print("\nLoading graph...")
    with open(split_graph_path, "rb") as f:
        drive_graph = pickle.load(f)
    print(f"  {drive_graph.number_of_nodes():,} nodes, {drive_graph.number_of_edges():,} edges")

    source_pbf = drive_graph.graph.get(SOURCE_PBF_KEY)
    assert source_pbf == project_relative(config.ROAD_EXTRACT_PBF_PATH), \
        f"graph built from {source_pbf}, signals read from {config.ROAD_EXTRACT_PBF_PATH}"

    # --- nodes: signal flag (identical across variants) ---
    n_signal_nodes = n_synthetic_nodes = 0
    for node, node_attrs in drive_graph.nodes(data=True):
        if node_attrs.get(SYNTHETIC_ATTR, False):
            node_attrs[SIGNALS_ATTR] = False
            n_synthetic_nodes += 1
            continue
        node_attrs[SIGNALS_ATTR] = node in signal_collector.signals
        n_signal_nodes += node_attrs[SIGNALS_ATTR]

    print(f"\ntraffic signal nodes in graph: {n_signal_nodes:,} "
          f"({n_signal_nodes / len(signal_collector.signals) * 100:.1f}% of PBF)   synthetic: {n_synthetic_nodes:,}")

    print("\nAssigning Valhalla density levels to nodes...")
    level_by_node = node_levels(drive_graph, density_raster_path=density_raster_path)

    speed_table = load_speed_table(config.OSM_SPEED_TABLE_PATH)            # AU/VIC entry
    for variant, (tier_rule, rules_by_tier) in selected_variants.items():
        print(f"\n=== variant: {variant} ===")
        for _, _, edge in drive_graph.edges(data=True):  # reset
            edge[TIME_RAW_S_ATTR] = float('nan')

        if rules_by_tier is None:
            _assign_table_speeds(drive_graph, level_by_node, speed_table)
        else:
            _assign_speeds(drive_graph, level_by_node, tier_rule, rules_by_tier)

        stale = sum(1 for _, _, edge in drive_graph.edges(data=True)
                    if edge.get(TIME_RAW_S_ATTR) != edge.get(TIME_RAW_S_ATTR))  # nan check
        assert stale == 0, f"{variant}: {stale:,} edges left without time_raw_s"
        path = paths[variant]
        path.parent.mkdir(parents=True, exist_ok=True)

        drive_graph.graph.update(variant=variant, signals_pbf=project_relative(config.ROAD_EXTRACT_PBF_PATH),
                                 density_fp=project_relative(density_raster_path),
                                 enriched_at=datetime.now().isoformat(timespec="seconds"))

        write_pickle(drive_graph, path)
        print(f"  saved to {path}")

    return paths
