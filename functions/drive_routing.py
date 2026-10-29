"""Drive routing pieces shared by the sample_drive_pairs stage (the draw's window gate) and the
calibrate_pathing_agent stage (routing runs): snap-node eligibility, signal penalties, the penalised
timed graph, and the OD-table columns and graph attributes both read."""
import pickle

import pandas as pd

import config

# Hex nodes table / joined OD table: each end's snap candidates.
DRIVE_NODE_COLS = ("drive_node_1", "drive_node_2")
DRIVE_ROAD_DIST_COLS = ("drive_road_dist_1_m", "drive_road_dist_2_m")
PAIR_ID_COL = "pair_id"            # joined OD table: one id per pair (= draw_no)

# Graph attributes, as speed_graphs.enrich writes them.
VARIANT_KEY = "variant"
SIGNALS_ATTR = "signals"           # node flag: signalised head node
TIME_ATTR = "time_raw_s"           # edge seconds before signal penalties
LEN_ATTR = "length"                # edge metres
HIGHWAY_ATTR = "highway"           # edge: OSM highway tag
SPEED_SOURCE_ATTR = "speed_source" # edge: where its speed came from (speed_graphs)
TAGGED_SOURCE = "tagged"           # speed_source value: posted limit (x factor)

MIN_CSR_WEIGHT = 1e-9              # scipy reads a zero weight as "no edge"


def eligible_nodes(row, end):
    """Snap nodes a trip may start (end) on: node 1, plus node 2 when its road is within
    config.CANDIDATE_TIE_WINDOW_M of node 1's and it is a different node. end = column prefix
    ("origin", "dest", or "hex" in the draw). Returns (n1,) or (n1, n2) as int node ids (node 2 is
    read as float, its column holds NaN)."""
    node_1 = int(getattr(row, f"{end}_{DRIVE_NODE_COLS[0]}"))
    node_2 = getattr(row, f"{end}_{DRIVE_NODE_COLS[1]}")
    road_dist_1_m = getattr(row, f"{end}_{DRIVE_ROAD_DIST_COLS[0]}")
    road_dist_2_m = getattr(row, f"{end}_{DRIVE_ROAD_DIST_COLS[1]}")
    is_node_2_eligible = (pd.notna(node_2) and road_dist_2_m - road_dist_1_m <= config.CANDIDATE_TIE_WINDOW_M
                          and node_2 != node_1)
    return (node_1, int(node_2)) if is_node_2_eligible else (node_1,)


def penalised_time_attr(beta):
    """Edge attribute holding time_raw_s plus beta per signalised head node."""
    return f"time_total_s_b{beta:g}"


def apply_signal_penalty(graph, beta, attr="time_total_s"):
    """attr = time_raw_s + beta on every edge whose HEAD node is signalised. Each node on a path is
    paid for exactly once, by the single edge arriving at it. beta = 0 reduces to time_raw_s.
    Returns the number of penalised edges."""
    n_penalised = 0
    for _, head, data in graph.edges(data=True):
        penalty_s = beta if graph.nodes[head].get(SIGNALS_ATTR) else 0.0
        data[attr] = data[TIME_ATTR] + penalty_s
        n_penalised += penalty_s > 0
    return n_penalised


def load_penalised_graph(graph_path, betas):
    """Load a timed graph and add one penalised weight per beta."""
    with open(graph_path, "rb") as f:
        graph = pickle.load(f)
    for beta in betas:
        apply_signal_penalty(graph, beta, attr=penalised_time_attr(beta))
    return graph
