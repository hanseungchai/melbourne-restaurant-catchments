"""Drive model fit (DCL-1..3): edge time = blind time_raw_s x m_group + beta per signalised head node,
predicted = ALPHA x route cost. Per route the fit is linear in ALPHA, ALPHA x m_group and ALPHA x beta;
it is iterated with rerouting until the routes and parameters settle. Routes on a routing bundle
(functions.routing_bundle) with the scaled weights built per worker process."""
import hashlib
import pickle
import time

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.optimize import least_squares
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra as cs_dijkstra

import config
from functions.drive_routing import (HIGHWAY_ATTR, MIN_CSR_WEIGHT, PAIR_ID_COL, SPEED_SOURCE_ATTR, TAGGED_SOURCE,
                                     TIME_ATTR, eligible_nodes)
from functions.routing_bundle import (BUNDLE_INDICES_FILE, BUNDLE_NODES_FILE, NO_PREDECESSOR, get_bundle,
                                      node_rows)
from functions.density_levels import node_levels   # same density level rule as the timed graphs

FIT_EDGE_SETS = ("tagged", "not_fast", "not_motorway", "all")    # config.DRIVE_FIT_EDGE_SET values
MOTORWAY_TYPES = {"motorway", "motorway_link"}
TRUNK_TYPES = {"trunk", "trunk_link"}
REST_GROUP = 0                     # edges no group scales: blind time, m = 1
GOOGLE_DURATION_COL = "google_drive_duration_sec"
FIT_LIMIT_SLACK = 1e-6             # relative and absolute slack on the previous route's cost (search limit)
ROUTE_HASH_BYTES = 8
GROUP_TIME_COL = "time_g{}_s"      # route composition: blind seconds in group g
SIGNALS_COL = "signals"
ROUTE_HASH_COL = "route_hash"

_FIT_CACHE = {}                    # per worker process: the scaled weights it has built


def build_fit_edge_attrs(graph_path, bundle_path, out_path):
    """Per edge of the bundle, in its CSR order: start-node density level (the speed graphs' rule),
    tagged, motorway, trunk. Saved to out_path (.npz)."""
    with open(graph_path, "rb") as f:
        graph = pickle.load(f)
    level_by_node = node_levels(graph)
    nodes = np.load(bundle_path / BUNDLE_NODES_FILE)
    indices = np.load(bundle_path / BUNDLE_INDICES_FILE)
    n_edges = graph.number_of_edges()
    tails, heads = np.empty(n_edges, np.int64), np.empty(n_edges, np.int64)
    is_tagged, is_motorway, is_trunk = (np.empty(n_edges, bool) for _ in range(3))
    for i, (tail, head, data) in enumerate(graph.edges(data=True)):
        tails[i], heads[i] = tail, head
        is_tagged[i] = data[SPEED_SOURCE_ATTR] == TAGGED_SOURCE
        is_motorway[i] = data[HIGHWAY_ATTR] in MOTORWAY_TYPES
        is_trunk[i] = data[HIGHWAY_ATTR] in TRUNK_TYPES
    node_level = np.array([level_by_node[int(node)] for node in nodes])
    del graph, level_by_node
    tail_rows, head_rows = np.searchsorted(nodes, tails), np.searchsorted(nodes, heads)
    order = np.lexsort((head_rows, tail_rows))
    assert np.array_equal(head_rows[order], indices), "edge order differs from the bundle's CSR"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out_path, level=node_level[tail_rows[order]].astype(np.int8), is_tagged=is_tagged[order],
             is_motorway=is_motorway[order], is_trunk=is_trunk[order])
    print(f"saved {out_path}")
    return out_path


def edge_groups(attrs, groups, edge_set):
    """Group of every edge: 1..k for the scaled level ranges in groups (edges in edge_set only), else
    REST_GROUP."""
    assert edge_set in FIT_EDGE_SETS, edge_set
    is_fast = attrs["is_motorway"] | attrs["is_trunk"]
    in_set = {"tagged": attrs["is_tagged"] & ~is_fast,
              "not_fast": ~is_fast,
              "not_motorway": ~attrs["is_motorway"],
              "all": np.ones_like(is_fast)}[edge_set]
    group = np.full(len(in_set), REST_GROUP, np.int8)
    for group_no, (low, high) in enumerate(groups, start=1):
        is_member = in_set & (attrs["level"] >= low) & (attrs["level"] <= high)
        assert not (group[is_member] != REST_GROUP).any(), "groups overlap"
        group[is_member] = group_no
    return group


def _fit_graph(bundle_path, attrs_path, groups, edge_set, multipliers, beta):
    """Per worker process: the base graph with every group's edges x its m, plus beta per signal."""
    key = (str(bundle_path), str(attrs_path), groups, edge_set, multipliers, beta)
    if key not in _FIT_CACHE:
        _FIT_CACHE.clear()
        bundle = get_bundle(bundle_path)
        with np.load(attrs_path) as attrs:
            group = edge_groups(attrs, groups, edge_set)
        time_s = np.asarray(bundle.raw_weights[TIME_ATTR])
        head_signal = bundle.signals[bundle.indices].astype(float)
        scale = np.concatenate([[1.0], multipliers])[group]
        weight = np.maximum(time_s * scale + beta * head_signal, MIN_CSR_WEIGHT)
        _FIT_CACHE[key] = dict(bundle=bundle, group=group, time_s=time_s, head_signal=head_signal,
                               matrix=csr_matrix((weight, bundle.indices, bundle.indptr),
                                                 shape=(len(bundle.nodes),) * 2, copy=False))
    return _FIT_CACHE[key]


def _path_edge_positions(bundle, path):
    """CSR positions of a path's edges."""
    positions = np.empty(len(path) - 1, dtype=np.int64)
    for k, (tail, head) in enumerate(zip(path[:-1], path[1:])):
        start, end = bundle.indptr[tail], bundle.indptr[tail + 1]
        positions[k] = start + np.searchsorted(bundle.indices[start:end], head)
    return positions


def _route_fit_batch(bundle_path, attrs_path, groups, edge_set, multipliers, beta, jobs):
    """jobs: (pair_id, origin nodes, dest nodes, search limit). Per pair: blind seconds per group,
    signals paid and a route hash. Exact whatever the limit (reruns unlimited if nothing is reached)."""
    graph = _fit_graph(bundle_path, attrs_path, groups, edge_set, multipliers, beta)
    bundle, n_groups = graph["bundle"], len(groups) + 1
    records = []
    for pair_id, origin_nodes, dest_nodes, limit in jobs:
        sources, targets = node_rows(bundle, origin_nodes), node_rows(bundle, dest_nodes)
        dist, predecessors, _ = cs_dijkstra(graph["matrix"], directed=True, indices=sources, min_only=True,
                                            return_predecessors=True, limit=limit)
        best = targets[int(np.argmin(dist[targets]))]
        if not np.isfinite(dist[best]):
            dist, predecessors, _ = cs_dijkstra(graph["matrix"], directed=True, indices=sources, min_only=True,
                                                return_predecessors=True)
            best = targets[int(np.argmin(dist[targets]))]
        assert np.isfinite(dist[best]), f"pair {pair_id}: no route"
        path = [best]
        while predecessors[path[-1]] != NO_PREDECESSOR:
            path.append(int(predecessors[path[-1]]))
        path.reverse()
        positions = _path_edge_positions(bundle, path)
        group_s = np.bincount(graph["group"][positions], weights=graph["time_s"][positions], minlength=n_groups)
        records.append({PAIR_ID_COL: pair_id,
                        **{GROUP_TIME_COL.format(g): float(group_s[g]) for g in range(n_groups)},
                        SIGNALS_COL: float(graph["head_signal"][positions].sum()),
                        ROUTE_HASH_COL: hashlib.blake2b(positions.tobytes(), digest_size=ROUTE_HASH_BYTES).hexdigest()})
    return records


def _route_fit(pairs_df, bundle_path, attrs_path, groups, edge_set, multipliers, beta, limits):
    """Route every pair under one parameter set (config.DRIVE_FIT_N_JOBS workers); rows in pairs_df order."""
    jobs = [(getattr(row, PAIR_ID_COL), eligible_nodes(row, "origin"), eligible_nodes(row, "dest"), limit)
            for row, limit in zip(pairs_df.itertuples(), limits)]
    batches = [jobs[i:i + config.DRIVE_FIT_BATCH_SIZE] for i in range(0, len(jobs), config.DRIVE_FIT_BATCH_SIZE)]
    results = Parallel(n_jobs=config.DRIVE_FIT_N_JOBS)(
        delayed(_route_fit_batch)(bundle_path, attrs_path, groups, edge_set, multipliers, beta, batch)
        for batch in batches)
    routes_df = pd.DataFrame([record for batch in results for record in batch])
    assert (routes_df[PAIR_ID_COL].to_numpy() == pairs_df[PAIR_ID_COL].to_numpy()).all()
    return routes_df


def _group_times(routes_df, n_groups):
    return routes_df[[GROUP_TIME_COL.format(g) for g in range(n_groups)]].to_numpy()


def _route_cost(routes_df, multipliers, beta):
    """Each route's cost under (multipliers, beta), before ALPHA."""
    return (_group_times(routes_df, len(multipliers) + 1) @ np.concatenate([[1.0], multipliers])
            + beta * routes_df[SIGNALS_COL].to_numpy())


def _round0_limits(n_pairs, multipliers, beta):
    limit_s = (config.DRIVE_FIT_ROUND0_LIMIT_WINDOW_FACTOR * config.ROUTES_DRIVE_WINDOW_S * max((1.0, *multipliers))
               + beta * config.DRIVE_FIT_ROUND0_LIMIT_PER_BETA)
    return [limit_s] * n_pairs


def soft_l1_loss(residual):
    """Per-pair soft_l1 loss at scale config.DRIVE_FIT_LOSS_SCALE (scipy's definition)."""
    scale = config.DRIVE_FIT_LOSS_SCALE
    return scale ** 2 * 2 * (np.sqrt(1 + (residual / scale) ** 2) - 1)


def _fit_params(routes_df, google_s, n_scaled, beta_fixed, x0):
    """Robust fit of Google time on route composition. Free beta: p = (c0, c1..ck, d); fixed beta:
    p = (c0, c1..ck). ALPHA = c0, m_g = c_g / c0, beta = d / c0."""
    group_s = _group_times(routes_df, n_scaled + 1)
    signals = routes_df[SIGNALS_COL].to_numpy()
    if beta_fixed is None:
        design = np.column_stack([group_s, signals])
    else:
        design = np.column_stack([group_s[:, 0] + beta_fixed * signals, group_s[:, 1:]])
    result = least_squares(lambda p: np.log(design @ p / google_s), x0, loss="soft_l1",
                           f_scale=config.DRIVE_FIT_LOSS_SCALE, bounds=(config.DRIVE_FIT_MIN_PARAM, np.inf))
    p = result.x
    beta = p[-1] / p[0] if beta_fixed is None else beta_fixed
    return p, float(p[0]), tuple(float(c / p[0]) for c in p[1:n_scaled + 1]), float(beta)


def fit_drive_model(pairs_df, bundle_path, attrs_path, groups, edge_set, beta_fixed=None, label=""):
    """Iterate route -> fit on pairs_df until < config.DRIVE_FIT_TOL_ROUTE_SHARE of routes change and
    every m and beta moves < config.DRIVE_FIT_TOL_PARAM_REL. Returns (params dict, history DataFrame)."""
    n_scaled = len(groups)
    multipliers = (config.DRIVE_FIT_START_M,) * n_scaled
    beta = config.DRIVE_FIT_START_BETA_S if beta_fixed is None else beta_fixed
    google_s = pairs_df[GOOGLE_DURATION_COL].to_numpy(float)
    x0 = np.array([config.DRIVE_FIT_START_ALPHA, *multipliers] + ([beta] if beta_fixed is None else []))
    is_route_fixed = n_scaled == 0 and beta_fixed is not None      # nothing fitted moves the routes
    previous_df, history, is_converged = None, [], False
    for round_no in range(config.DRIVE_FIT_MAX_ROUNDS):
        t_start = time.time()
        limits = (_round0_limits(len(pairs_df), multipliers, beta) if previous_df is None
                  else list(_route_cost(previous_df, multipliers, beta) * (1 + FIT_LIMIT_SLACK) + FIT_LIMIT_SLACK))
        routes_df = _route_fit(pairs_df, bundle_path, attrs_path, groups, edge_set, multipliers, beta, limits)
        changed = (1.0 if previous_df is None
                   else float(np.mean(routes_df[ROUTE_HASH_COL].to_numpy() != previous_df[ROUTE_HASH_COL].to_numpy())))
        x0, alpha, new_multipliers, new_beta = _fit_params(routes_df, google_s, n_scaled, beta_fixed, x0)
        residual = np.log(alpha * _route_cost(routes_df, new_multipliers, new_beta) / google_s)
        moves = [abs(new - old) / old for new, old in zip(new_multipliers, multipliers)]
        moves.append(abs(new_beta - beta) / max(beta, config.DRIVE_FIT_TOL_BETA_FLOOR_S))
        record = dict(label=label, round=round_no, routes_changed=changed, alpha=alpha,
                      **{f"m{g}": m for g, m in enumerate(new_multipliers, start=1)}, beta=new_beta,
                      loss=float(soft_l1_loss(residual).sum()), max_param_move=max(moves),
                      route_s=round(time.time() - t_start, 1))
        history.append(record)
        print(f"  {label} round {round_no}: routes changed {changed:.2%}, ALPHA {alpha:.4f}, "
              f"m {tuple(round(m, 4) for m in new_multipliers)}, beta {new_beta:.3f}, loss {record['loss']:.3f} "
              f"({record['route_s']:.0f} s)", flush=True)
        is_converged = is_route_fixed or (round_no > 0 and changed < config.DRIVE_FIT_TOL_ROUTE_SHARE
                                          and max(moves) < config.DRIVE_FIT_TOL_PARAM_REL)
        previous_df, multipliers, beta = routes_df, new_multipliers, new_beta
        if is_converged:
            break
    if not is_converged:
        print(f"  WARNING {label}: not converged after {config.DRIVE_FIT_MAX_ROUNDS} rounds")
    params = dict(alpha=alpha, multipliers=list(multipliers), beta=beta, rounds=len(history),
                  is_converged=is_converged, loss=history[-1]["loss"])
    return params, pd.DataFrame(history)
