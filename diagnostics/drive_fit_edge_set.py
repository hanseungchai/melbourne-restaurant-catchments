"""Which edges should the fitted density factor act on?

Claim under test: the fitted density model (DESIGN_pre_spine "Drive model selection", item 1) fits Google
best when its dense-tier factor acts on a wider set of edges than "tagged, not motorway/trunk".
drive_untagged_share (2026-10-11) found that slowing only those edges pushes routes onto untagged
streets and motorway/trunk, which together carry over half the dense-tier route time and are never
scaled; many of Melbourne's at-grade signalised arterials are tagged trunk.
Three edge sets, each with one factor m on its dense-tier (level 15) edges:
  A  tagged, not motorway/trunk (as the dense variant and the dry run)
  B  A + untagged, not motorway/trunk
  C  everything except motorway / motorway_link (adds trunk, tagged or not)
Same model otherwise, 2-tier: edge time = blind time_raw_s x (m if in set and level 15, else 1)
+ beta per signalised head node; predicted = ALPHA x routed time. Per route the fit is linear:
Google ~ c0 B + c1 D + d S (B blind time off the scaled edges, D on them, S signals); ALPHA = c0,
m = c1 / c0, beta = d / c0. Loss soft_l1 on log(predicted / Google), scale 0.1. Iterated route ->
fit until < 0.5% of routes change and m, beta move < 0.5% (DESIGN_pre_spine). Training half only (3,999).
Where the pipeline relies on it: the fitting round in pathing_calibration (which edges its factors
scale).
Pre-registered rule (set before the first run): the set with the lowest converged loss wins; another
set is dropped only if its loss exceeds the winner's with a paired bootstrap 95% CI excluding 0
(destination hexes resampled, converged routes held fixed); sets not separated all go on to CV.
Same parameter count in every set, so in-sample loss compares them fairly.
Conclusion (run 2026-10-11, 3,999 training pairs, 1,977 destination hexes): C wins; A and B dropped.
  A  m 1.528 (factor 0.524), beta 16.8, ALPHA 1.209, loss 59.939, acc 92.65%, scaled time 4.9%
  B  m 1.465 (factor 0.546), beta 16.7, ALPHA 1.208, loss 59.626, acc 92.52%, scaled time 6.1%
  C  m 1.435 (factor 0.557), beta 15.3, ALPHA 1.217, loss 59.006, acc 92.45%, scaled time 9.6%
Loss vs C: A +0.93 (95% CI 0.50 to 1.42), B +0.62 (0.28 to 0.98). Each converged in 4-5 rounds.
The gain is real but small (~1.6% of loss); in-sample accuracy at the cut does not move (0.2 pp,
~8 pairs). The fitted dense factor is close across sets (0.52-0.56): what slows in dense areas is
similar for posted, default and trunk roads at this resolution. Whether it differs by road class is
the Google regression's question (DESIGN_pre_spine "Drive model selection", item 4).

Follow-up (user, 2026-10-11): motorways. C leaves motorway / motorway_link at the posted limit on
the a-priori ground that they are grade-separated; never tested. On Google's training-half polylines
motorway is 46% of route length overall and 31% in level 15 (scratch count, google_polyline_match
points, 10 m / 45 deg). Two more sets:
  D  everything at level 15, motorway included, one shared factor m (same parameter count as A-C)
  E  C, plus a separate free factor m_mw on level-15 motorway / motorway_link (one extra parameter):
     Google ~ c0 B + c1 D + c2 M + d S, m_mw = c2 / c0. Its fitted m_mw says directly how much
     Google slows dense-area motorways relative to their posted limit, ALPHA aside.
Pre-registered rule for D and E (set before their first run): D joins A-C under the rule above.
E has one parameter more, so its in-sample loss gain is biased in its favour, though by little next
to the gaps above (one parameter on 3,999 pairs). E goes on to CV only if its loss is below the best
of A-D with a paired bootstrap 95% CI excluding 0; otherwise motorway handling is settled by A-D.
The convergence test adds m_mw (< 0.5% move) for E.
Conclusion for D and E (same run): D has the lowest loss, so it is the reference: D m 1.396 (factor
0.573), beta 16.1, ALPHA 1.197, loss 58.758, acc 92.55%. C +0.248 vs D (CI -0.099 to 0.611): not
separated, so C and D go on to CV; A and B stay dropped. E m 1.410, m_mw 1.308, beta 15.9, loss
58.734, -0.025 vs D, CI including 0: E does not go on.
CV (5-fold out-of-fold, training half, pathing_calibration.fit_drive_models with edge set
"not_motorway" and "all"): C and D tie on every score, paired CIs all including 0 (accuracy C
0.9252, D 0.9255; loss 0.01479 vs 0.01473). Decided by diagnostics/drive_motorway_absorption.py:
edge set "all" (D), by a pre-set fallback, not by fit (DESIGN_pre_spine "Drive model selection", item 1).

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
Saved edge arrays (diagnostic_data) are reused on later runs and never overwritten.
"""
import datetime
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from pyproj import Transformer
from scipy.optimize import least_squares
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_DIR_NAME = "-37.76870_144.97196"
LAYERS_TAG = "res2021_wrk2021_ven20260925"
FILE_TAG = f"{LAYERS_TAG}_{SUBJECT_DIR_NAME}"
CALIBRATION_DIR = PROJECT_ROOT / "outputs" / "pathing_calibration"
BLIND_GRAPH_PATH = (PROJECT_ROOT / "outputs" / "speed_graphs" / SUBJECT_DIR_NAME
                    / f"split_drive_edges_timed_blind_{FILE_TAG}.pkl")
DENSITY_RASTER_PATH = PROJECT_ROOT / "outputs" / "road_density" / "road_density_raster.npz"
BLIND_BUNDLE_DIR = CALIBRATION_DIR / "prepared_graphs" / f"split_drive_edges_timed_blind_{FILE_TAG}_routing_b0_2"
PAIRS_PATH = CALIBRATION_DIR / SUBJECT_DIR_NAME / f"od_expanded_drive_enriched_{FILE_TAG}.csv"
SPLIT_PATH = CALIBRATION_DIR / SUBJECT_DIR_NAME / f"drive_split_{FILE_TAG}.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "drive_fit_edge_set"

# --- rules copied from the pipeline (speed_graphs, road_density, drive_routing) ---------------------
GEOGRAPHIC_CRS = "EPSG:4326"
LEVEL_SCALE = 0.7
HALF_UP = 0.5
MAX_LEVEL = 15                     # also the dense tier of the 2-tier structure
OUTSIDE_RASTER_LEVEL = 0
MOTORWAY_TYPES = {"motorway", "motorway_link"}
TRUNK_TYPES = {"trunk", "trunk_link"}
TAGGED_SOURCE = "tagged"
CANDIDATE_TIE_WINDOW_M = 1.0
NO_PREDECESSOR = -9999
MIN_CSR_WEIGHT = 1e-9

# --- fit settings (DESIGN_pre_spine "Drive model selection") -----------------------------------------------
LOSS_SCALE = 0.1                   # soft_l1 f_scale on log(pred / Google)
TOL_ROUTE_SHARE = 0.005            # converged: < 0.5% of routes change ...
TOL_PARAM_REL = 0.005              # ... and m, beta move < 0.5%
MAX_ROUNDS = 15
START_M, START_BETA = 1.5, 12.0    # near the dry-run fixed point (m 1.51, beta 17) and the dense variant
ROUND0_LIMIT_S = 3 * 1500          # round 0 search limit before the m / beta terms (3 x the draw window)
ROUND0_LIMIT_PER_BETA = 100        # ... plus beta x this (signals)
LIMIT_SLACK = 1e-6
CUT_S = 20 * 60                    # classification cut (accuracy, reported only)
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261011
N_JOBS = 8
BATCH = 20
EDGE_SETS = ("A", "B", "C", "D", "E")
SAME_COUNT_SETS = ("A", "B", "C", "D")  # one dense factor each; E has a second (motorway)
START_M_MW = 1.2                   # E: start for the motorway factor

_CACHE = {}


def edge_arrays_path():
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_edges.npz"))
    if saved:
        return saved[-1], True
    return DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_edges.npz", False


def build_edge_arrays(out_path):
    """Per edge, in the blind bundle's CSR order: start-node level, tagged, motorway, trunk."""
    print(f"loading {BLIND_GRAPH_PATH.name} ...", flush=True)
    with open(BLIND_GRAPH_PATH, "rb") as f:
        graph = pickle.load(f)
    nodes = np.load(BLIND_BUNDLE_DIR / "nodes.npy")
    indices = np.load(BLIND_BUNDLE_DIR / "indices.npy")
    with np.load(DENSITY_RASTER_PATH) as raster:
        density, x0, y0 = raster["density"], float(raster["x0"]), float(raster["y0"])
        cell_m, crs = float(raster["cell_m"]), str(raster["crs"])
    lon = np.array([graph.nodes[int(node)]["x"] for node in nodes])
    lat = np.array([graph.nodes[int(node)]["y"] for node in nodes])
    x, y = Transformer.from_crs(GEOGRAPHIC_CRS, crs, always_xy=True).transform(lon, lat)
    ix, iy = np.floor((x - x0) / cell_m).astype(int), np.floor((y - y0) / cell_m).astype(int)
    is_inside = (ix >= 0) & (ix < density.shape[0]) & (iy >= 0) & (iy < density.shape[1])
    node_density = np.full(len(nodes), np.nan)
    node_density[is_inside] = density[ix[is_inside], iy[is_inside]]
    node_level = np.minimum(np.floor(node_density * LEVEL_SCALE + HALF_UP), MAX_LEVEL)
    node_level[~np.isfinite(node_level)] = OUTSIDE_RASTER_LEVEL

    n_edges = graph.number_of_edges()
    tails, heads = np.empty(n_edges, np.int64), np.empty(n_edges, np.int64)
    is_tagged, is_motorway, is_trunk = (np.empty(n_edges, bool) for _ in range(3))
    for i, (tail, head, data) in enumerate(graph.edges(data=True)):
        tails[i], heads[i] = tail, head
        is_tagged[i] = data["speed_source"] == TAGGED_SOURCE
        is_motorway[i] = data["highway"] in MOTORWAY_TYPES
        is_trunk[i] = data["highway"] in TRUNK_TYPES
    del graph
    tail_rows, head_rows = np.searchsorted(nodes, tails), np.searchsorted(nodes, heads)
    order = np.lexsort((head_rows, tail_rows))
    assert np.array_equal(head_rows[order], indices), "edge order differs from the bundle's CSR"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, edge_level=node_level[tail_rows[order]].astype(np.int8),
                        is_tagged=is_tagged[order], is_motorway=is_motorway[order], is_trunk=is_trunk[order])
    print(f"saved {out_path.name}", flush=True)


def scaled_masks(arrays, edge_set):
    """Edges the dense-tier factor m acts on, and edges the motorway factor m_mw acts on (E only)."""
    is_dense = arrays["edge_level"] == MAX_LEVEL
    not_fast = ~arrays["is_motorway"] & ~arrays["is_trunk"]
    in_set = {"A": arrays["is_tagged"] & not_fast,
              "B": not_fast,
              "C": ~arrays["is_motorway"],
              "D": np.ones_like(is_dense),
              "E": ~arrays["is_motorway"]}[edge_set]
    in_motorway_set = arrays["is_motorway"] if edge_set == "E" else np.zeros_like(is_dense)
    return is_dense & in_set, is_dense & in_motorway_set


def _graph(arrays_path, edge_set, m, m_mw, beta):
    key = (edge_set, m, m_mw, beta)
    if key not in _CACHE:
        _CACHE.clear()
        with np.load(arrays_path) as arrays:
            is_scaled, is_mw_scaled = scaled_masks(arrays, edge_set)
        nodes = np.load(BLIND_BUNDLE_DIR / "nodes.npy", mmap_mode="r")
        indptr = np.load(BLIND_BUNDLE_DIR / "indptr.npy", mmap_mode="r")
        indices = np.load(BLIND_BUNDLE_DIR / "indices.npy", mmap_mode="r")
        time_s = np.load(BLIND_BUNDLE_DIR / "raw_time_raw_s.npy")
        head_signal = np.load(BLIND_BUNDLE_DIR / "signals.npy")[indices].astype(float)
        factor = np.where(is_scaled, m, 1.0) * np.where(is_mw_scaled, m_mw, 1.0)
        weight = np.maximum(time_s * factor + beta * head_signal, MIN_CSR_WEIGHT)
        _CACHE[key] = dict(nodes=nodes, indptr=indptr, indices=indices, time_s=time_s, is_scaled=is_scaled,
                           is_mw_scaled=is_mw_scaled,
                           head_signal=head_signal,
                           matrix=csr_matrix((weight, indices, indptr), shape=(len(nodes),) * 2, copy=False))
    return _CACHE[key]


def _rows(nodes, ids):
    ids = np.asarray(ids, dtype=np.int64)
    rows = np.searchsorted(nodes, ids).clip(max=len(nodes) - 1)
    return [int(row) for row, node in zip(rows, ids) if nodes[row] == node]


def route_batch(arrays_path, edge_set, m, m_mw, beta, jobs):
    """jobs: (pair_id, origin ids, dest ids, search limit). Per pair: B, D, M, S and a route hash."""
    graph = _graph(arrays_path, edge_set, m, m_mw, beta)
    out = []
    for pair_id, origin_ids, dest_ids, limit in jobs:
        sources, targets = _rows(graph["nodes"], origin_ids), _rows(graph["nodes"], dest_ids)
        dist, pred, _ = dijkstra(graph["matrix"], directed=True, indices=sources, min_only=True,
                                 return_predecessors=True, limit=limit)
        best = targets[int(np.argmin(dist[targets]))]
        if not np.isfinite(dist[best]):
            dist, pred, _ = dijkstra(graph["matrix"], directed=True, indices=sources, min_only=True,
                                     return_predecessors=True)
            best = targets[int(np.argmin(dist[targets]))]
        path = [best]
        while pred[path[-1]] != NO_PREDECESSOR:
            path.append(int(pred[path[-1]]))
        path.reverse()
        positions = np.empty(len(path) - 1, dtype=np.int64)
        for k, (tail, head) in enumerate(zip(path[:-1], path[1:])):
            start, end = graph["indptr"][tail], graph["indptr"][tail + 1]
            positions[k] = start + np.searchsorted(graph["indices"][start:end], head)
        time_s, is_scaled = graph["time_s"][positions], graph["is_scaled"][positions]
        is_mw_scaled = graph["is_mw_scaled"][positions]
        out.append(dict(pair_id=pair_id, B=float(time_s[~is_scaled & ~is_mw_scaled].sum()),
                        D=float(time_s[is_scaled].sum()), M=float(time_s[is_mw_scaled].sum()),
                        S=float(graph["head_signal"][positions].sum()), route_hash=hashlib.blake2b(positions.tobytes(), digest_size=8).hexdigest()))
    return out


def eligible(row, end):
    node_1 = int(getattr(row, f"{end}_drive_node_1"))
    node_2 = getattr(row, f"{end}_drive_node_2")
    gap_m = getattr(row, f"{end}_drive_road_dist_2_m") - getattr(row, f"{end}_drive_road_dist_1_m")
    return (node_1, int(node_2)) if pd.notna(node_2) and gap_m <= CANDIDATE_TIE_WINDOW_M and node_2 != node_1 else (node_1,)


def soft_l1(residual):
    return LOSS_SCALE ** 2 * 2 * (np.sqrt(1 + (residual / LOSS_SCALE) ** 2) - 1)


def fit(columns, google_s, x0):
    """columns: per-route time components (B, D[, M], S); p: their coefficients."""
    def predicted(p):
        return sum(coef * column for coef, column in zip(p, columns))
    result = least_squares(lambda p: np.log(predicted(p) / google_s), x0, loss="soft_l1", f_scale=LOSS_SCALE,
                           bounds=(1e-6, np.inf))
    p = result.x
    residual = np.log(predicted(p) / google_s)
    return p, residual, predicted(p)


def run_set(arrays_path, edge_set, pairs_df, google_s, ends):
    has_mw = edge_set == "E"
    m, m_mw, beta, prev, history = START_M, (START_M_MW if has_mw else 1.0), START_BETA, None, []
    p = np.array([1.0, START_M, START_M_MW, START_BETA] if has_mw else [1.0, START_M, START_BETA])
    for round_no in range(MAX_ROUNDS):
        t_start = datetime.datetime.now()
        if prev is None:
            limits = [ROUND0_LIMIT_S * max(m, m_mw, 1.0) + beta * ROUND0_LIMIT_PER_BETA] * len(ends)
        else:
            limits = list((prev.B + m * prev.D + m_mw * prev.M + beta * prev.S).to_numpy() * (1 + LIMIT_SLACK)
                          + LIMIT_SLACK)
        jobs = [(pair_id, o, d, limit) for (pair_id, o, d), limit in zip(ends, limits)]
        batches = [jobs[i:i + BATCH] for i in range(0, len(jobs), BATCH)]
        results = Parallel(n_jobs=N_JOBS)(delayed(route_batch)(arrays_path, edge_set, m, m_mw, beta, batch)
                                          for batch in batches)
        routes = pd.DataFrame([record for batch in results for record in batch])
        assert (routes.pair_id.to_numpy() == pairs_df.pair_id.to_numpy()).all()
        changed = float(np.mean(routes.route_hash.to_numpy() != prev.route_hash.to_numpy())) if prev is not None else 1.0
        columns = [routes.B.to_numpy(), routes.D.to_numpy(), *([routes.M.to_numpy()] if has_mw else []),
                   routes.S.to_numpy()]
        p, residual, predicted = fit(columns, google_s, p)
        new_m, new_beta = p[1] / p[0], p[-1] / p[0]
        new_m_mw = p[2] / p[0] if has_mw else 1.0
        record = dict(edge_set=edge_set, round=round_no, m_routed=m, m_mw_routed=m_mw, beta_routed=beta,
                      routes_changed=changed, alpha=p[0], m=new_m, m_mw=new_m_mw, beta=new_beta,
                      loss=float(soft_l1(residual).sum()),
                      median_log_err=float(np.median(residual)),
                      accuracy_at_cut=float(np.mean((predicted <= CUT_S) == (google_s <= CUT_S))),
                      scaled_time_share=float(routes.D.sum() / (routes.B + routes.D + routes.M).sum()),
                      mw_scaled_time_share=float(routes.M.sum() / (routes.B + routes.D + routes.M).sum()),
                      route_s=(datetime.datetime.now() - t_start).total_seconds())
        history.append(record)
        print(json.dumps({k: (round(v, 5) if isinstance(v, float) else v) for k, v in record.items()}), flush=True)
        is_converged = (round_no > 0 and changed < TOL_ROUTE_SHARE and abs(new_m - m) / m < TOL_PARAM_REL
                        and abs(new_m_mw - m_mw) / m_mw < TOL_PARAM_REL
                        and abs(new_beta - beta) / max(beta, 1.0) < TOL_PARAM_REL)
        prev, m, m_mw, beta = routes, new_m, new_m_mw, new_beta
        if is_converged:
            break
    return history, soft_l1(residual)


def main():
    run_date = f"{datetime.date.today():%Y%m%d}"
    arrays_path, is_reused = edge_arrays_path()
    if is_reused:
        print(f"reusing saved edge arrays {arrays_path.name}")
    else:
        build_edge_arrays(arrays_path)

    split_df = pd.read_csv(SPLIT_PATH)
    train_ids = set(split_df.loc[split_df.half == "train", "draw_no"])
    pairs_df = pd.read_csv(PAIRS_PATH)
    pairs_df = pairs_df[pairs_df.draw_no.isin(train_ids)].reset_index(drop=True)
    assert not set(pairs_df.draw_no) & set(split_df.loc[split_df.half == "test", "draw_no"])
    google_s = pairs_df.google_drive_duration_sec.to_numpy(float)
    ends = [(row.pair_id, eligible(row, "origin"), eligible(row, "dest")) for row in pairs_df.itertuples()]
    print(f"training pairs: {len(ends):,}, destination hexes {pairs_df.dest_hex_id.nunique():,}", flush=True)

    histories, pair_losses = [], {}
    for edge_set in EDGE_SETS:
        history, pair_losses[edge_set] = run_set(arrays_path, edge_set, pairs_df, google_s, ends)
        histories.extend(history)
    history_df = pd.DataFrame(histories)
    final_df = history_df.groupby("edge_set").tail(1).set_index("edge_set")

    # paired bootstrap over destination hexes, converged routes held fixed
    hex_codes, hex_ix = np.unique(pairs_df.dest_hex_id.to_numpy(), return_inverse=True)
    hex_losses = {s: np.bincount(hex_ix, weights=pair_losses[s], minlength=len(hex_codes)) for s in EDGE_SETS}
    winner = min(SAME_COUNT_SETS, key=lambda s: hex_losses[s].sum())  # E is judged against it separately
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = rng.integers(len(hex_codes), size=(N_BOOTSTRAP, len(hex_codes)))
    comparisons = {}
    for edge_set in EDGE_SETS:
        if edge_set == winner:
            continue
        diff = hex_losses[edge_set] - hex_losses[winner]
        boot = diff[draws].sum(axis=1)
        low, high = np.percentile(boot, [2.5, 97.5])
        comparisons[edge_set] = dict(loss_diff=round(float(diff.sum()), 3), ci95=[round(float(low), 3), round(float(high), 3)],
                                     is_dropped=bool(low > 0) if edge_set in SAME_COUNT_SETS else bool(high >= 0))
    verdict = dict(winner=winner, compared_to_winner=comparisons,
                   to_cv=[winner] + [s for s, c in comparisons.items() if not c["is_dropped"]],
                   final={s: dict(alpha=round(final_df.loc[s, "alpha"], 4), m=round(final_df.loc[s, "m"], 4),
                                  factor=round(0.8 / final_df.loc[s, "m"], 4), m_mw=round(final_df.loc[s, "m_mw"], 4),
                                  beta=round(final_df.loc[s, "beta"], 3),
                                  loss=round(final_df.loc[s, "loss"], 3),
                                  accuracy_at_cut=round(final_df.loc[s, "accuracy_at_cut"], 4),
                                  scaled_time_share=round(final_df.loc[s, "scaled_time_share"], 4),
                                  mw_scaled_time_share=round(final_df.loc[s, "mw_scaled_time_share"], 4),
                                  rounds=int(final_df.loc[s, "round"]) + 1) for s in EDGE_SETS})
    print(json.dumps(verdict, indent=1))
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    history_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_history.csv", index=False)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_verdict.json").write_text(json.dumps(verdict, indent=1))


if __name__ == "__main__":
    sys.exit(main())
