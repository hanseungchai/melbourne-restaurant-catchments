"""Routing bundle: a timed graph as CSR arrays (.npy), memory-mapped and shared by every worker
process, plus the multi-source Dijkstra that routes on it. Built once per timed graph and beta set,
checked against networkx on its first pairs."""
import gc
import json
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra as cs_dijkstra

import config
from functions.drive_routing import (LEN_ATTR, MIN_CSR_WEIGHT, PAIR_ID_COL, SIGNALS_ATTR, TIME_ATTR,
                                     VARIANT_KEY, eligible_nodes, load_penalised_graph, penalised_time_attr)

BUNDLE_META_FILE = "meta.json"           # written last: its presence marks a complete bundle
BUNDLE_NODES_FILE = "nodes.npy"          # OSM node ids, ascending; CSR row i is nodes[i]
BUNDLE_INDPTR_FILE = "indptr.npy"
BUNDLE_INDICES_FILE = "indices.npy"
BUNDLE_SIGNALS_FILE = "signals.npy"      # per node: signalised
BUNDLE_RAW_WEIGHT_FILE = "raw_{}.npy"    # edge weight as in the graph, CSR order (costs, lengths)
BUNDLE_SEARCH_WEIGHT_FILE = "search_{}.npy"  # the same, floored at MIN_CSR_WEIGHT (Dijkstra input)
BUNDLE_WEIGHTS_KEY = "weights"           # meta.json: edge attributes saved
CSR_INDEX_DTYPE = np.int32               # scipy csgraph's index type
NO_PREDECESSOR = -9999                   # scipy's predecessor value for a search root or unreached node
ROUTE_COST_REL_TOL = 1e-9                # networkx parity check on route costs
N_PARITY_CHECKS = 20                     # first pairs of a new bundle also routed with networkx; must agree

_BUNDLE_CACHE = {}                 # per worker process: the one routing bundle it has loaded


@dataclass
class RoutingBundle:
    """One variant's timed graph as CSR arrays (memory-mapped, read-only) plus one scipy matrix per
    weight. Paths are lists of CSR row indices; nodes[row] is the OSM node id."""
    meta: dict
    nodes: np.ndarray
    indptr: np.ndarray
    indices: np.ndarray
    signals: np.ndarray
    raw_weights: dict
    search_matrices: dict


def path_cost(bundle, path, weight):
    """Sum of the raw edge weight along a path, added in path order (as networkx does)."""
    indptr, indices = bundle.indptr, bundle.indices
    raw = bundle.raw_weights[weight]
    cost = 0.0
    for tail, head in zip(path[:-1], path[1:]):
        start = indptr[tail]
        cost += float(raw[start + int(np.flatnonzero(indices[start:indptr[tail + 1]] == head)[0])])
    return cost


def path_node_ids(bundle, path):
    """A path of CSR rows as OSM node ids."""
    return [int(node) for node in bundle.nodes[path]]


def node_rows(bundle, node_ids):
    """CSR rows of the given OSM node ids, in order, skipping ids not in the graph."""
    ids = np.asarray(node_ids, dtype=np.int64)
    rows = np.searchsorted(bundle.nodes, ids).clip(max=len(bundle.nodes) - 1)
    return [int(row) for row, node in zip(rows, ids) if bundle.nodes[row] == node]


def route_drive(bundle, origin_nodes, dest_nodes, weight, limit_cost=np.inf):
    """Cheapest route under weight from any origin node to any destination node: one multi-source
    Dijkstra on the full graph, searching no further than limit_cost. Exact whatever the limit:
    every cost within it is final, and if no destination is reached the search reruns unlimited.
    Connector costs are zero, as Google charges none (backup/
    manual_diagnostic_20260922_google_od_connector_cost_check.py). Returns (cost, path of CSR rows) or
    (None, None)."""
    sources = node_rows(bundle, origin_nodes)
    targets = node_rows(bundle, dest_nodes)
    if not sources or not targets:
        return None, None

    dist, predecessors, _ = cs_dijkstra(bundle.search_matrices[weight], directed=True, indices=sources,
                                        min_only=True, return_predecessors=True, limit=limit_cost)
    best = targets[int(np.argmin(dist[targets]))]
    if not np.isfinite(dist[best]):
        if np.isfinite(limit_cost):
            return route_drive(bundle, origin_nodes, dest_nodes, weight)
        return None, None
    path = [best]
    while predecessors[path[-1]] != NO_PREDECESSOR:
        path.append(int(predecessors[path[-1]]))
    path.reverse()
    return path_cost(bundle, path, weight), path


def _routing_weights(betas):
    """Edge attributes a bundle holds: length, raw time, one penalised time per beta."""
    return [LEN_ATTR, TIME_ATTR, *(penalised_time_attr(beta) for beta in betas)]


def _write_bundle(graph, bundle_path, betas):
    """Save graph as CSR arrays in the folder bundle_path: rows sorted by node id, each row's edges by
    head. meta.json is written last."""
    weights = _routing_weights(betas)
    nodes = np.sort(np.fromiter(graph.nodes, dtype=np.int64, count=graph.number_of_nodes()))
    n_edges = graph.number_of_edges()
    tails, heads = np.empty(n_edges, np.int64), np.empty(n_edges, np.int64)
    raw = {weight: np.empty(n_edges) for weight in weights}
    for i, (tail, head, data) in enumerate(graph.edges(data=True)):
        tails[i], heads[i] = tail, head
        for weight in weights:
            raw[weight][i] = data[weight]
    tail_rows, head_rows = np.searchsorted(nodes, tails), np.searchsorted(nodes, heads)
    order = np.lexsort((head_rows, tail_rows))
    tail_rows, head_rows = tail_rows[order], head_rows[order]
    is_repeat = (tail_rows[1:] == tail_rows[:-1]) & (head_rows[1:] == head_rows[:-1])
    assert not is_repeat.any(), f"{int(is_repeat.sum())} parallel edges: the CSR keeps one edge per node pair"
    indptr = np.concatenate([[0], np.cumsum(np.bincount(tail_rows, minlength=len(nodes)))])

    bundle_path.mkdir(parents=True, exist_ok=True)
    np.save(bundle_path / BUNDLE_NODES_FILE, nodes)
    np.save(bundle_path / BUNDLE_INDPTR_FILE, indptr.astype(CSR_INDEX_DTYPE))
    np.save(bundle_path / BUNDLE_INDICES_FILE, head_rows.astype(CSR_INDEX_DTYPE))
    np.save(bundle_path / BUNDLE_SIGNALS_FILE, np.array([bool(graph.nodes[node].get(SIGNALS_ATTR)) for node in nodes]))
    for weight in weights:
        np.save(bundle_path / BUNDLE_RAW_WEIGHT_FILE.format(weight), raw[weight][order])
        np.save(bundle_path / BUNDLE_SEARCH_WEIGHT_FILE.format(weight), np.maximum(raw[weight][order], MIN_CSR_WEIGHT))
    meta = {VARIANT_KEY: graph.graph.get(VARIANT_KEY), "betas": list(betas), BUNDLE_WEIGHTS_KEY: weights,
            "n_nodes": len(nodes), "n_edges": n_edges}
    (bundle_path / BUNDLE_META_FILE).write_text(json.dumps(meta, indent=1), encoding="utf-8")


def _load_bundle(bundle_path):
    """Open a bundle's arrays memory-mapped (the OS shares the pages between worker processes)."""
    meta = json.loads((bundle_path / BUNDLE_META_FILE).read_text(encoding="utf-8"))

    def load(file_name):
        return np.load(bundle_path / file_name, mmap_mode="r")

    nodes, indptr, indices = load(BUNDLE_NODES_FILE), load(BUNDLE_INDPTR_FILE), load(BUNDLE_INDICES_FILE)
    shape = (len(nodes), len(nodes))
    return RoutingBundle(
        meta=meta, nodes=nodes, indptr=indptr, indices=indices, signals=load(BUNDLE_SIGNALS_FILE),
        raw_weights={weight: load(BUNDLE_RAW_WEIGHT_FILE.format(weight)) for weight in meta[BUNDLE_WEIGHTS_KEY]},
        search_matrices={weight: csr_matrix((load(BUNDLE_SEARCH_WEIGHT_FILE.format(weight)), indices, indptr),
                                            shape=shape, copy=False)
                         for weight in meta[BUNDLE_WEIGHTS_KEY]})


def get_bundle(bundle_path):
    """Per worker process: open the routing bundle once, dropping any other."""
    key = str(bundle_path)
    if key not in _BUNDLE_CACHE:
        _BUNDLE_CACHE.clear()
        gc.collect()
        _BUNDLE_CACHE[key] = _load_bundle(Path(bundle_path))
    return _BUNDLE_CACHE[key]


def _route_drive_networkx(graph, origin_nodes, dest_nodes, weight):
    """The pre-CSR router, kept for the parity check: bidirectional Dijkstra per origin x destination
    node, cheapest kept. Returns (cost, path of node ids) or (None, None)."""
    best = None
    for source in origin_nodes:
        for target in dest_nodes:
            try:
                cost, path = nx.bidirectional_dijkstra(graph, source, target, weight=weight)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            if best is None or cost < best[0]:
                best = (cost, path)
    return best if best is not None else (None, None)


def _check_bundle_parity(graph, bundle_path, betas, od_path):
    """The first N_PARITY_CHECKS pairs of od_path routed both ways, every weight: route costs must agree
    (relative ROUTE_COST_REL_TOL); a different path is allowed only as an equal-cost tie."""
    bundle = _load_bundle(bundle_path)
    pairs_df = pd.read_csv(od_path, nrows=N_PARITY_CHECKS)
    n_routes = n_tie_paths = 0
    for row in pairs_df.itertuples():
        origin_nodes, dest_nodes = eligible_nodes(row, "origin"), eligible_nodes(row, "dest")
        for weight in _routing_weights(betas):
            cost, path = route_drive(bundle, origin_nodes, dest_nodes, weight)
            cost_nx, path_nx = _route_drive_networkx(graph, origin_nodes, dest_nodes, weight)
            assert (cost is None) == (cost_nx is None), (getattr(row, PAIR_ID_COL), weight, cost, cost_nx)
            if cost is None:
                continue
            assert abs(cost - cost_nx) <= ROUTE_COST_REL_TOL * max(cost_nx, MIN_CSR_WEIGHT), \
                (getattr(row, PAIR_ID_COL), weight, cost, cost_nx)
            n_routes += 1
            n_tie_paths += path_node_ids(bundle, path) != path_nx
    print(f"  parity vs networkx: {len(pairs_df)} pairs, {n_routes} routes, costs agree; "
          f"different equal-cost paths {n_tie_paths}")


def prepared_path(graph_path, betas):
    """Routing bundle folder for a timed graph and a set of betas, in config.PREPARED_GRAPHS_DIR."""
    beta_tag = "_".join(f"{beta:g}" for beta in sorted(betas))
    return Path(config.PREPARED_GRAPHS_DIR) / f"{Path(graph_path).stem}_routing_b{beta_tag}"


def prep_graph(graph_path, betas, od_path):
    """Build the routing bundle once (rebuilt when the timed graph is newer) and check it against
    networkx on the first pairs of od_path."""
    bundle_path = prepared_path(graph_path, betas)
    meta_path = bundle_path / BUNDLE_META_FILE
    if meta_path.exists() and meta_path.stat().st_mtime > Path(graph_path).stat().st_mtime:
        return bundle_path
    graph = load_penalised_graph(graph_path, tuple(betas))
    _write_bundle(graph, bundle_path, tuple(betas))
    _check_bundle_parity(graph, bundle_path, tuple(betas), od_path)
    return bundle_path
