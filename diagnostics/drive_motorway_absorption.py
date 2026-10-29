"""What does the dense factor absorb when it also scales motorways?

Context: drive_fit_edge_set (2026-10-11) left two edge sets tied in 5-fold CV: C (dense factor m on
every level-15 edge except motorway / motorway_link) and D (on every level-15 edge, motorway included).
Precedent (OSRM, Valhalla, r5r) has no convention exempting motorways; the user leans D provisionally
(2026-10-12) and asked what else m on dense motorways absorbs besides real congestion. Three checks,
all on the training half (3,999 pairs), routes at the screen's converged parameters, no fixed-point
iteration (the screen converged at them):
  C      m 1.4354, beta 15.252 s/signal (set C)
  D      m 1.3962, beta 16.118 s/signal (set D)
  blind  m 1, beta 2 (reference only)

Notation, per route (as drive_fit_edge_set; columns in route_batch):
  B  blind time on unscaled edges (s), column B
  D  blind time on scaled level-15 edges (s), column D
  S  signalised head nodes on the route (count), column S
  M  blind time on level-15 motorway / motorway_link edges (s), column M_dense_mw (any set)
  T  blind time on the whole route (s), column T
  predicted = ALPHA (B + m D + beta S); ALPHA, m, beta refitted on these routes (soft_l1, as the screen)
  residual  = log(predicted / Google), column log_resid

1. Route match (route choice; never tested before).
   Claim tested: scaling dense motorways moves the agent's routes nearer the roads Google drives, i.e.
   part of what m absorbs on motorways is route choice, not time.
   Measure: Google's polyline cut into pieces <= 10 m; a piece is on our route if a route edge (straight
   segment, direction of travel) lies within 10 m with heading difference <= 45 deg (the
   google_polyline_match tolerances). overlap_google = share of Google's length on our route (primary);
   overlap_route = share of our route's length on Google's polyline (secondary, same test reversed).
   Rule (pre-registered): mean per-pair overlap_google, D minus C, paired bootstrap over destination
   hexes (2,000 draws), 95% CI. CI above 0: D routes nearer Google (route choice is part of what m
   absorbs; a point for D beyond time fit). Below 0: C nearer. Includes 0: no detectable route-choice
   difference. The subset of pairs whose C and D routes differ is reported, not used for the decision.
   Motorway use: per-pair dense-motorway length share (level-15 motorway / motorway_link length over
   route length), ours vs Google's (Google pieces matched the same way to level-15 motorway edges).
   Rule: the agent over-uses dense motorways under a variant if (ours - Google) has a CI above 0.

2. Residuals vs dense-motorway share (is the motorway slowing real?).
   Under C's routes, regress C's residual on x = M / T. C leaves motorways at their posted limit, so
   if Google slows dense motorways, C under-predicts more as x rises: slope < 0 (log(pred / Google)).
   Same regression for D on D's routes: if D's shared factor fits motorways, its slope is ~0.
   Length confound: motorway-heavy trips are longer; a second fit adds log T as a control.
   Rule (pre-registered): a slope counts only if the plain and controlled fits agree in sign and both
   hex-bootstrap 95% CIs exclude 0. C negative: dense motorways slowed beyond the posted limit (against
   C's exemption). D positive: D over-slows them. Otherwise inconclusive.

3. Ramp meters (do motorway-ramp signals feed beta?).
   Signalised head nodes of motorway_link edges on each variant's routes, as a share of all S; also
   of motorway edges. Descriptive; pre-set reading: under 5% of S is not a material share of beta.

4. Classification at the cut (added 2026-10-12, after 1-3; rule set before its run, with the user).
   Does C's motorway bias reach the 20-minute cut? Uses the 5-fold out-of-fold predictions of the
   2-tier fit under each set (fit/<subject>/20261011/not_motorway and /all). Discordant pairs: C and D
   on opposite sides of the cut; on each, exactly one matches Google's side.
   Rule: D wins if (D right - C right) / pairs has a hex-bootstrap 95% CI above 0; otherwise C stays
   (tie-break agreed 2026-10-12: if the bias does not reach the cut it does not matter for this
   subject, and C's routes are nearer Google's). Note: this difference is the CV accuracy difference
   (D - C 95% CI -0.0021 to +0.0028), so a tie is expected; what is new is descriptive: whether the
   discordant pairs are motorway-heavy, and the direction of each model's errors near the cut
   (Google 15-25 min) by dense-motorway share (x on C's screen route, 2 above; over 10% = heavy).

5. Route choice on motorways, case by case (added 2026-10-12 with the user; descriptive, no rule).
   Per pair, motorway length (motorway / motorway_link, any density level) on our route and on
   Google's (Google pieces matched to motorway edges as in 1).
   C exploits: C's route has >= 1 km more motorway than Google's and D's does not.
   D over-avoids: Google's route has >= 1 km more motorway than D's and C's does not.
   Better path, on pairs whose C and D routes differ: the variant whose overlap_google is >= 5 points
   higher; else neither. Per group: count, pairs in the 10-30 min band, each model's out-of-fold mean
   log error and mean |log error|. "Proper path" means Google's path, one traffic-aware choice.
6. Motorway bias at the cut (added 2026-10-12 with the user; decides the edge set, with 4).
   Out-of-fold log error, log(predicted / Google), regressed on x (dense-motorway time share on the
   model's own screen route, 2 above), on pairs with Google time 10-30 min, weighted by closeness to
   the cut: w = 1 - |Google min - 20| / 10. Weighted least squares, hex-bootstrap 95% CI on the slope.
   Rule (set before the run): a model whose slope CI excludes 0 has a motorway bias at the cut and
   loses. Neither or both: D (one rule for every road; no precedent exempts motorways; C's stated
   reason, grade separation, failed check 2). Replaces 4's tie-break, which was set when C was
   wrongly treated as the incumbent (it was chosen 2026-10-11 pending confirmation).
   Why weighted: the fallback picks D when the test is inconclusive, so it needs power to be fair to
   C (15-25 min holds 1,228 pairs, 10-30 min 2,441); the weight keeps long trips, where C's bias may
   sit but cannot flip the cut, from deciding it.

Where the pipeline relies on it: the edge set the fitted density factor scales
(config.DRIVE_FIT_EDGE_SET; pathing_calibration.fit_drive_models).

Conclusion (run 2026-10-12, 3,999 training pairs, 1,977 destination hexes; refits reproduce the
screen: C loss 59.006, D 58.758). Values: mean, then hex-bootstrap 95% CI.
1. Route match: C's routes are nearer Google, not D's. overlap_google C 0.617, D 0.613, blind 0.622;
   D - C -0.0040 (-0.0069, -0.0012); on the 706 pairs whose C and D routes differ -0.023 (-0.039,
   -0.006). overlap_route agrees (D - C -0.0032, CI -0.0062 to -0.0002). So m on motorways does not
   absorb route choice; it moves routes slightly away from Google's roads. Dense-motorway length share:
   Google 0.0346; C over-uses (+0.0062, 0.0045 to 0.0079); D matches (+0.0010, -0.0004 to 0.0025);
   blind under-uses (-0.0108). D's motorway share is right on average but leaves the motorway on
   different trips than Google does. Both fitted variants match Google's roads less than blind. All
   three leave ~38% of Google's length off our route (Google is on our graph for 99.4% of its length:
   google_polyline_match), a large route-choice gap that the time fit does not see.
2. Residuals: under C, error falls as dense-motorway share rises: slope -0.141 (-0.220, -0.054), with
   log T control -0.203 (-0.280, -0.117); by share bin 0: -0.4%, 0-10%: -1.4%, 10-30%: -2.3%, >30%
   (26 pairs): -7.1%. By the rule: Google slows dense motorways beyond their posted limit, against C's
   exemption. Under D, no slope: +0.071 (-0.012, 0.162), controlled +0.006 (-0.076, 0.097).
3. Ramp signals: 6.4% of S under C, 6.2% under D (54% of pairs pass at least one); blind 2.9%. Material
   by the pre-set 5% reading: beta partly prices motorway entry.
4. Classification at the cut: 23 discordant pairs of 3,999; C right on 11, D on 12. D - C accuracy
   +0.0003 (-0.0022, +0.0027): by the rule, C stays. The discordant pairs are motorway-heavy (43% over
   10% share vs 15% of all pairs), so motorways do decide the classifications that differ, but evenly
   (heavy: C 4, D 6; light: C 7, D 6). Near the cut (Google 15-25 min), C's errors on motorway-heavy
   trips are not one-sided: 23 false reachable, 24 false unreachable (217 pairs; D 18 / 28). Median
   out-of-fold log error there: C +0.040, D +0.075 (light trips: C +0.039, D +0.031).
   (4's tie-break, C stays, was replaced by 6's rule before 6 ran; see 6.)
5. Route choice cases (out-of-fold errors; |err| = mean |log error|):
   C exploits (>= 1 km more motorway than Google, D not): 86 pairs (54 in 10-30 min); |err| C 0.123,
   D 0.128. D over-avoids (>= 1 km less than Google, C not): 40 pairs (25); |err| C 0.119, D 0.121.
   Both over-use motorways broadly: >= 1 km more than Google on 1,031 pairs (C) and 970 (D); >= 1 km
   less on 418 (C) and 449 (D). Of the 706 pairs whose C and D routes differ, C's path is nearer
   Google on 192, D's on 106, neither on 408. Where D's is nearer, C drove 10.0 km of motorway against
   Google's 6.8 (D 6.9): D wins by cutting C's motorway over-use. Where C's is nearer, motorway km
   barely differ (C 8.1, D 7.6, Google 7.6): D goes wrong on other roads. In every group C's time
   error is as small as D's or smaller, even where D's path is nearer Google: a nearer path does not
   buy a better time here.
6. Bias at the cut (2,441 pairs in 10-30 min, effective n 1,835): C slope -0.117 (-0.226, +0.008);
   D +0.086 (-0.032, +0.214). Neither CI excludes 0, so by the rule: D (fallback). C's upper bound sits
   just above 0; the two point estimates are similar in size and opposite in sign.
Read: what m absorbs on dense motorways is time, not route choice: C under-predicts motorway-heavy
trips (2) and D removes it, at a small cost in route match (1). Near the cut neither model shows a
motorway bias (6), and the classifications that differ split evenly (4), so the decision falls to
the pre-set fallback: D, one rule for every road. Route choice is mixed (5): C over-uses motorways
twice as often as D over-avoids them, yet C finds Google's path more often and its times are no
worse. Edge set: "all" (D).

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
Reuses drive_fit_edge_set's saved edge arrays (read only). Its own saved node/edge geometry and routes
are reused on later runs and never overwritten.
"""
import datetime
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
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
BLIND_BUNDLE_DIR = CALIBRATION_DIR / "prepared_graphs" / f"split_drive_edges_timed_blind_{FILE_TAG}_routing_b0_2"
PAIRS_PATH = CALIBRATION_DIR / SUBJECT_DIR_NAME / f"od_expanded_drive_enriched_{FILE_TAG}.csv"
SPLIT_PATH = CALIBRATION_DIR / SUBJECT_DIR_NAME / f"drive_split_{FILE_TAG}.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
FIT_RUN_DIR = CALIBRATION_DIR / "fit" / SUBJECT_DIR_NAME / "20261011"
OOF_PATHS = {"C": FIT_RUN_DIR / "not_motorway" / "oof_predictions.csv",
             "D": FIT_RUN_DIR / "all" / "oof_predictions.csv"}
OOF_MODEL = "2tier"
EDGE_ARRAYS_PATH = DIAGNOSTIC_DATA_DIR / "drive_fit_edge_set_20261011_edges.npz"  # edge_level, is_motorway, CSR order
NAME = "drive_motorway_absorption"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
GEOMETRY_GLOB = f"{NAME}_*_geometry.npz"
ROUTES_GLOB = f"{NAME}_*_routes_{{variant}}.npz"
PAIRS_OUT_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_pairs.csv"
SUMMARY_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_summary.json"
LOG_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"

# --- rules copied from the pipeline and earlier diagnostics -----------------------------------------
GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:7855"           # GDA2020 / MGA 55, metres
POLYLINE_PRECISION = 1e5
MAX_LEVEL = 15                     # dense tier
MOTORWAY_LINK = "motorway_link"
MOTORWAY = "motorway"
CANDIDATE_TIE_WINDOW_M = 1.0
NO_PREDECESSOR = -9999
MIN_CSR_WEIGHT = 1e-9
LOSS_SCALE = 0.1
ROUTE_LIMIT_S = 3 * 1500           # search limit before the m / beta terms (as the screen's round 0)
ROUTE_LIMIT_PER_BETA = 100
N_JOBS = 8
BATCH = 20

# --- variants (drive_fit_edge_set_20261011_verdict.json, final) -------------------------------------
VARIANTS = {"C": dict(m=1.4354, beta=15.252, scales_motorway=False),
            "D": dict(m=1.3962, beta=16.118, scales_motorway=True),
            "blind": dict(m=1.0, beta=2.0, scales_motorway=False)}

# --- matching and statistics ------------------------------------------------------------------------
PIECE_M = 10.0                     # lines cut into pieces of at most this length
MATCH_M = 10.0                     # a piece within this of a segment ...
HEADING_TOL_DEG = 45.0             # ... with heading difference at most this is matched
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261012
RAMP_MATERIAL_SHARE = 0.05         # pre-set: ramp signals under this share of S are not material
CUT_S = 20 * 60                    # classification cut
NEAR_CUT_S = (15 * 60, 25 * 60)    # Google times counted as near the cut
HEAVY_MW_SHARE = 0.10              # dense-motorway time share counted as motorway-heavy
MW_GAP_M = 1000.0                  # check 5: motorway length difference counted as a different choice
BETTER_PATH_GAP = 0.05             # check 5: overlap_google difference counted as a better path
BAND_S = (10 * 60, 30 * 60)        # check 6: Google times in the weighted band
BAND_HALF_WIDTH_S = 10 * 60        # check 6: weight falls to 0 this far from the cut


class Tee:
    """Print to the console and keep every line for the run log."""

    def __init__(self):
        self.stdout = sys.stdout
        self.lines = []

    def write(self, text):
        self.stdout.write(text)
        self.lines.append(text)

    def flush(self):
        self.stdout.flush()


def latest_saved(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def decode_polyline(encoded):
    """Google encoded polyline -> array of (lat, lon)."""
    coords, index, lat, lon = [], 0, 0, 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift, result = 0, 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lat / POLYLINE_PRECISION, lon / POLYLINE_PRECISION))
    return np.array(coords)


def bearing_deg(dx, dy):
    return np.degrees(np.arctan2(dy, dx)) % 360


def heading_difference(a_deg, b_deg):
    """Angle between two directions of travel, 0..180."""
    return np.abs((a_deg - b_deg + 180) % 360 - 180)


def load_geometry():
    """Per bundle node: metric x, y. Per edge in CSR order: motorway_link / motorway flags."""
    saved = latest_saved(GEOMETRY_GLOB)
    if saved is not None:
        print(f"reusing node and edge geometry from {saved.name}")
        with np.load(saved) as data:
            return {key: data[key] for key in data.files}
    print(f"loading {BLIND_GRAPH_PATH.name} ...", flush=True)
    with open(BLIND_GRAPH_PATH, "rb") as f:
        graph = pickle.load(f)
    nodes = np.load(BLIND_BUNDLE_DIR / "nodes.npy")
    indices = np.load(BLIND_BUNDLE_DIR / "indices.npy")
    lon = np.array([graph.nodes[int(node)]["x"] for node in nodes])
    lat = np.array([graph.nodes[int(node)]["y"] for node in nodes])
    x, y = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True).transform(lon, lat)
    n_edges = graph.number_of_edges()
    tails, heads = np.empty(n_edges, np.int64), np.empty(n_edges, np.int64)
    is_link, is_main = np.empty(n_edges, bool), np.empty(n_edges, bool)
    for i, (tail, head, data) in enumerate(graph.edges(data=True)):
        highway = data["highway"]
        highway = highway[0] if isinstance(highway, list) else str(highway)
        tails[i], heads[i] = tail, head
        is_link[i], is_main[i] = highway == MOTORWAY_LINK, highway == MOTORWAY
    del graph
    tail_rows, head_rows = np.searchsorted(nodes, tails), np.searchsorted(nodes, heads)
    order = np.lexsort((head_rows, tail_rows))
    assert np.array_equal(head_rows[order], indices), "edge order differs from the bundle's CSR"
    geometry = dict(x=x, y=y, is_motorway_link=is_link[order], is_motorway_main=is_main[order])
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_geometry.npz"
    np.savez_compressed(out_path, **geometry)
    print(f"saved {out_path.name}", flush=True)
    return geometry


_CACHE = {}


def _graph(variant):
    if variant not in _CACHE:
        _CACHE.clear()
        params = VARIANTS[variant]
        with np.load(EDGE_ARRAYS_PATH) as arrays:
            is_dense, is_motorway = arrays["edge_level"] == MAX_LEVEL, arrays["is_motorway"]
        is_scaled = is_dense & (np.ones_like(is_motorway) if params["scales_motorway"] else ~is_motorway)
        nodes = np.load(BLIND_BUNDLE_DIR / "nodes.npy", mmap_mode="r")
        indptr = np.load(BLIND_BUNDLE_DIR / "indptr.npy", mmap_mode="r")
        indices = np.load(BLIND_BUNDLE_DIR / "indices.npy", mmap_mode="r")
        time_s = np.load(BLIND_BUNDLE_DIR / "raw_time_raw_s.npy")
        head_signal = np.load(BLIND_BUNDLE_DIR / "signals.npy")[indices].astype(float)
        weight = np.maximum(time_s * np.where(is_scaled, params["m"], 1.0) + params["beta"] * head_signal,
                            MIN_CSR_WEIGHT)
        _CACHE[variant] = dict(nodes=nodes, indptr=indptr, indices=indices,
                               matrix=csr_matrix((weight, indices, indptr), shape=(len(nodes),) * 2, copy=False))
    return _CACHE[variant]


def _rows(nodes, ids):
    ids = np.asarray(ids, dtype=np.int64)
    rows = np.searchsorted(nodes, ids).clip(max=len(nodes) - 1)
    return [int(row) for row, node in zip(rows, ids) if nodes[row] == node]


def route_batch(variant, jobs):
    """jobs: (origin ids, dest ids). Per pair: the route's CSR edge positions, in travel order."""
    graph = _graph(variant)
    params = VARIANTS[variant]
    limit = ROUTE_LIMIT_S * params["m"] + params["beta"] * ROUTE_LIMIT_PER_BETA
    out = []
    for origin_ids, dest_ids in jobs:
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
        out.append(positions)
    return out


def load_routes(variant, ends):
    """Every pair's route under a variant: concatenated CSR positions plus offsets. Reused if saved."""
    saved = latest_saved(ROUTES_GLOB.format(variant=variant))
    if saved is not None:
        print(f"reusing {variant} routes from {saved.name}")
        with np.load(saved) as data:
            positions, offsets = data["positions"], data["offsets"]
        assert len(offsets) == len(ends) + 1, "saved routes are for a different pair set"
        return [positions[offsets[i]:offsets[i + 1]] for i in range(len(ends))]
    t_start = datetime.datetime.now()
    batches = [ends[i:i + BATCH] for i in range(0, len(ends), BATCH)]
    results = Parallel(n_jobs=N_JOBS)(delayed(route_batch)(variant, batch) for batch in batches)
    routes = [positions for batch in results for positions in batch]
    offsets = np.concatenate([[0], np.cumsum([len(r) for r in routes])])
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_routes_{variant}.npz"
    np.savez_compressed(out_path, positions=np.concatenate(routes), offsets=offsets)
    print(f"routed {variant}: {len(routes):,} pairs in {(datetime.datetime.now() - t_start).total_seconds():.0f} s; "
          f"saved {out_path.name}", flush=True)
    return routes


def eligible(row, end):
    node_1 = int(getattr(row, f"{end}_drive_node_1"))
    node_2 = getattr(row, f"{end}_drive_node_2")
    gap_m = getattr(row, f"{end}_drive_road_dist_2_m") - getattr(row, f"{end}_drive_road_dist_1_m")
    return (node_1, int(node_2)) if pd.notna(node_2) and gap_m <= CANDIDATE_TIE_WINDOW_M and node_2 != node_1 else (node_1,)


def pieces(ax, ay, bx, by):
    """Segments cut into pieces of at most PIECE_M: midpoint x, y, length, heading, source segment."""
    dx, dy = bx - ax, by - ay
    seg_len = np.hypot(dx, dy)
    n_pieces = np.maximum(np.ceil(seg_len / PIECE_M).astype(int), 1)
    seg_ix = np.repeat(np.arange(len(seg_len)), n_pieces)
    piece_ix = np.arange(len(seg_ix)) - np.repeat(np.cumsum(n_pieces) - n_pieces, n_pieces)
    fraction = (piece_ix + 0.5) / n_pieces[seg_ix]
    return dict(x=ax[seg_ix] + fraction * dx[seg_ix], y=ay[seg_ix] + fraction * dy[seg_ix],
                length=seg_len[seg_ix] / n_pieces[seg_ix], heading=bearing_deg(dx, dy)[seg_ix], seg_ix=seg_ix)


def matched(piece, ax, ay, bx, by, tree=None):
    """Per piece: True if a segment lies within MATCH_M with heading difference <= HEADING_TOL_DEG."""
    geoms = shapely.linestrings(np.stack([np.column_stack([ax, ay]), np.column_stack([bx, by])], axis=1))
    tree = tree or shapely.STRtree(geoms)
    point_geoms = shapely.points(piece["x"], piece["y"])
    point_ix, seg_ix = tree.query(point_geoms, predicate="dwithin", distance=MATCH_M)
    is_aligned = heading_difference(piece["heading"][point_ix], bearing_deg(bx - ax, by - ay)[seg_ix]) <= HEADING_TOL_DEG
    is_matched = np.zeros(len(piece["x"]), bool)
    is_matched[point_ix[is_aligned]] = True
    return is_matched


def soft_l1(residual):
    return LOSS_SCALE ** 2 * 2 * (np.sqrt(1 + (residual / LOSS_SCALE) ** 2) - 1)


def fit(columns, google_s, x0):
    def predicted(p):
        return sum(coef * column for coef, column in zip(p, columns))
    result = least_squares(lambda p: np.log(predicted(p) / google_s), x0, loss="soft_l1", f_scale=LOSS_SCALE,
                           bounds=(1e-6, np.inf))
    return result.x, np.log(predicted(result.x) / google_s)


def hex_bootstrap_mean(values, hex_ix, n_hex, draws):
    """Mean of values per pair, and its 95% CI with destination hexes resampled."""
    sums = np.bincount(hex_ix, weights=values, minlength=n_hex)
    counts = np.bincount(hex_ix, minlength=n_hex).astype(float)
    boot = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    low, high = np.percentile(boot, [2.5, 97.5])
    return float(values.mean()), float(low), float(high)


def ols_slope(y, columns):
    design = np.column_stack([np.ones(len(y)), *columns])
    return np.linalg.lstsq(design, y, rcond=None)[0][1]


def hex_bootstrap_slope(y, columns, hex_ix, n_hex, draws):
    """OLS slope on the first column, and its 95% CI with destination hexes resampled."""
    members = np.split(np.argsort(hex_ix, kind="stable"), np.cumsum(np.bincount(hex_ix, minlength=n_hex))[:-1])
    boot = []
    for draw in draws:
        rows = np.concatenate([members[h] for h in draw])
        boot.append(ols_slope(y[rows], [c[rows] for c in columns]))
    low, high = np.percentile(boot, [2.5, 97.5])
    return float(ols_slope(y, columns)), float(low), float(high)


def rounded(values):
    return [round(v, 5) for v in values]


def wls_slope(y, x, w):
    root_w = np.sqrt(w)
    design = np.column_stack([np.ones(len(y)), x]) * root_w[:, None]
    return np.linalg.lstsq(design, y * root_w, rcond=None)[0][1]


def oof_log_errors(out_df):
    """Out-of-fold log(predicted / Google) of the 2-tier fit under C and D, in out_df's pair order."""
    google_s = out_df.google_drive_duration_sec.to_numpy(float)
    errors = {}
    for variant, path in OOF_PATHS.items():
        oof_df = pd.read_csv(path)
        oof_df = oof_df[oof_df.model == OOF_MODEL].set_index("pair_id")
        predicted_s = oof_df.predicted_s.reindex(out_df.pair_id).to_numpy()
        assert np.isfinite(predicted_s).all(), f"{variant}: out-of-fold predictions missing pairs"
        errors[variant] = np.log(predicted_s / google_s)
    return errors


def route_choice_cases(out_df):
    """Check 5: motorway exploit / over-avoid cases and better-path cases, with each model's errors."""
    errors = oof_log_errors(out_df)
    google_s = out_df.google_drive_duration_sec.to_numpy(float)
    is_band = (google_s >= BAND_S[0]) & (google_s <= BAND_S[1])
    google_mw = out_df.google_mw_len_m.to_numpy()
    over = {v: out_df[f"{v}_mw_len_m"].to_numpy() - google_mw for v in VARIANTS}
    is_differ = out_df.C_route_hash.to_numpy() != out_df.D_route_hash.to_numpy()
    overlap_gap = (out_df.D_overlap_google - out_df.C_overlap_google).to_numpy()
    groups = {
        "C_exploits": (over["C"] >= MW_GAP_M) & (over["D"] < MW_GAP_M),
        "D_over_avoids": (-over["D"] >= MW_GAP_M) & (-over["C"] < MW_GAP_M),
        "C_more_mw_than_google_any": over["C"] >= MW_GAP_M,
        "D_more_mw_than_google_any": over["D"] >= MW_GAP_M,
        "C_less_mw_than_google_any": -over["C"] >= MW_GAP_M,
        "D_less_mw_than_google_any": -over["D"] >= MW_GAP_M,
        "routes_differ": is_differ,
        "C_better_path": is_differ & (overlap_gap <= -BETTER_PATH_GAP),
        "D_better_path": is_differ & (overlap_gap >= BETTER_PATH_GAP),
        "neither_better": is_differ & (np.abs(overlap_gap) < BETTER_PATH_GAP)}
    result = {}
    for name, mask in groups.items():
        result[name] = dict(n=int(mask.sum()), n_in_10_30_min=int((mask & is_band).sum()))
        if mask.any():
            for v, err in errors.items():
                result[name][v] = dict(mean_log_err=round(float(err[mask].mean()), 4),
                                       mean_abs_log_err=round(float(np.abs(err[mask]).mean()), 4))
    for name in ("C_better_path", "D_better_path"):
        mask = groups[name]
        result[name]["mean_mw_km"] = {v: round(float(out_df[f"{v}_mw_len_m"][mask].mean() / 1000), 3)
                                      for v in ("C", "D")}
        result[name]["mean_mw_km"]["google"] = round(float(google_mw[mask].mean() / 1000), 3)
    return result


def bias_at_cut(out_df):
    """Check 6: weighted slope of out-of-fold log error on dense-motorway share near the cut."""
    errors = oof_log_errors(out_df)
    google_s = out_df.google_drive_duration_sec.to_numpy(float)
    is_band = (google_s >= BAND_S[0]) & (google_s <= BAND_S[1])
    band_df = out_df[is_band]
    weight = 1 - np.abs(google_s[is_band] - CUT_S) / BAND_HALF_WIDTH_S
    hex_codes, hex_ix = np.unique(band_df.dest_hex_id.to_numpy(), return_inverse=True)
    n_hex = len(hex_codes)
    members = np.split(np.argsort(hex_ix, kind="stable"), np.cumsum(np.bincount(hex_ix, minlength=n_hex))[:-1])
    draws = np.random.default_rng(BOOTSTRAP_SEED).integers(n_hex, size=(N_BOOTSTRAP, n_hex))
    result = dict(n_pairs=int(is_band.sum()), n_hex=n_hex, effective_n=round(float(weight.sum() ** 2 / (weight ** 2).sum()), 1))
    has_bias = {}
    for variant in ("C", "D"):
        x = (band_df[f"{variant}_M_dense_mw"] / band_df[f"{variant}_T"]).to_numpy()
        y = errors[variant][is_band]
        boot = []
        for draw in draws:
            rows = np.concatenate([members[h] for h in draw])
            boot.append(wls_slope(y[rows], x[rows], weight[rows]))
        low, high = np.percentile(boot, [2.5, 97.5])
        has_bias[variant] = bool(low > 0 or high < 0)
        result[variant] = dict(slope=round(float(wls_slope(y, x, weight)), 5), ci95=[round(float(low), 5), round(float(high), 5)],
                               has_bias_at_cut=has_bias[variant], n_x_pos=int((x > 0).sum()))
    result["verdict"] = ("C" if has_bias["D"] and not has_bias["C"] else
                         "D" if has_bias["C"] and not has_bias["D"] else "D (fallback: neither or both)")
    return result


def classification_at_cut(out_df, hex_ix, n_hex, draws):
    """Check 4: discordant pairs at the cut under the C and D out-of-fold predictions."""
    predicted = {}
    for variant, path in OOF_PATHS.items():
        oof_df = pd.read_csv(path)
        oof_df = oof_df[oof_df.model == OOF_MODEL].set_index("pair_id")
        predicted[variant] = oof_df.predicted_s.reindex(out_df.pair_id).to_numpy()
        assert np.isfinite(predicted[variant]).all(), f"{variant}: out-of-fold predictions missing pairs"
    google_s = out_df.google_drive_duration_sec.to_numpy(float)
    x = (out_df.C_M_dense_mw / out_df.C_T).to_numpy()
    is_heavy = x > HEAVY_MW_SHARE
    is_google_in = google_s <= CUT_S
    is_in = {v: p <= CUT_S for v, p in predicted.items()}
    is_right = {v: is_in[v] == is_google_in for v in predicted}
    is_discordant = is_in["C"] != is_in["D"]
    result = dict(
        n_discordant=int(is_discordant.sum()),
        C_right=int((is_discordant & is_right["C"]).sum()), D_right=int((is_discordant & is_right["D"]).sum()),
        accuracy_D_minus_C=rounded(hex_bootstrap_mean(is_right["D"].astype(float) - is_right["C"].astype(float),
                                                      hex_ix, n_hex, draws)),
        mean_x_discordant=round(float(x[is_discordant].mean()), 5),
        mean_x_concordant=round(float(x[~is_discordant].mean()), 5),
        heavy_share_discordant=round(float(is_heavy[is_discordant].mean()), 4),
        heavy_share_all=round(float(is_heavy.mean()), 4),
        discordant_heavy={v: int((is_discordant & is_heavy & is_right[v]).sum()) for v in predicted},
        discordant_light={v: int((is_discordant & ~is_heavy & is_right[v]).sum()) for v in predicted})
    result["accuracy_D_minus_C"].append("D wins" if result["accuracy_D_minus_C"][1] > 0 else "C stays")
    is_near = (google_s >= NEAR_CUT_S[0]) & (google_s <= NEAR_CUT_S[1])
    near = {}
    for label, mask in (("heavy", is_near & is_heavy), ("light", is_near & ~is_heavy)):
        near[label] = dict(n=int(mask.sum()), n_google_in=int((mask & is_google_in).sum()))
        for v, p in predicted.items():
            near[label][v] = dict(
                false_reachable=int((mask & is_in[v] & ~is_google_in).sum()),
                false_unreachable=int((mask & ~is_in[v] & is_google_in).sum()),
                median_log_err=round(float(np.median(np.log(p[mask] / google_s[mask]))), 5))
    result["near_cut_by_motorway"] = near
    return result


def main():
    tee = Tee()
    sys.stdout = tee
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"{NAME}  run {RUN_DATE}")
    geometry = load_geometry()
    with np.load(EDGE_ARRAYS_PATH) as arrays:
        edge_level, is_motorway = arrays["edge_level"], arrays["is_motorway"]
    assert np.array_equal(is_motorway, geometry["is_motorway_link"] | geometry["is_motorway_main"])
    is_dense_mw = (edge_level == MAX_LEVEL) & is_motorway
    indptr = np.load(BLIND_BUNDLE_DIR / "indptr.npy")
    indices = np.load(BLIND_BUNDLE_DIR / "indices.npy")
    tail_rows = np.repeat(np.arange(len(indptr) - 1), np.diff(indptr))
    time_s = np.load(BLIND_BUNDLE_DIR / "raw_time_raw_s.npy")
    head_signal = np.load(BLIND_BUNDLE_DIR / "signals.npy")[indices].astype(float)
    node_x, node_y = geometry["x"], geometry["y"]
    edge_ax, edge_ay = node_x[tail_rows], node_y[tail_rows]
    edge_bx, edge_by = node_x[indices], node_y[indices]
    edge_len_m = np.hypot(edge_bx - edge_ax, edge_by - edge_ay)

    split_df = pd.read_csv(SPLIT_PATH)
    train_ids = set(split_df.loc[split_df.half == "train", "draw_no"])
    pairs_df = pd.read_csv(PAIRS_PATH)
    pairs_df = pairs_df[pairs_df.draw_no.isin(train_ids)].reset_index(drop=True)
    assert not set(pairs_df.draw_no) & set(split_df.loc[split_df.half == "test", "draw_no"])
    assert pairs_df.polyline.notna().all()
    google_s = pairs_df.google_drive_duration_sec.to_numpy(float)
    ends = [(eligible(row, "origin"), eligible(row, "dest")) for row in pairs_df.itertuples()]
    print(f"training pairs: {len(ends):,}, destination hexes {pairs_df.dest_hex_id.nunique():,}", flush=True)
    routes = {variant: load_routes(variant, ends) for variant in VARIANTS}

    # Google's polylines as pieces; their dense-motorway share (matched to level-15 motorway edges)
    to_metric = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
    dense_mw_ix = np.flatnonzero(is_dense_mw)
    dense_mw_tree = shapely.STRtree(shapely.linestrings(np.stack(
        [np.column_stack([edge_ax[dense_mw_ix], edge_ay[dense_mw_ix]]),
         np.column_stack([edge_bx[dense_mw_ix], edge_by[dense_mw_ix]])], axis=1)))
    mw_ix = np.flatnonzero(is_motorway)
    mw_tree = shapely.STRtree(shapely.linestrings(np.stack(
        [np.column_stack([edge_ax[mw_ix], edge_ay[mw_ix]]),
         np.column_stack([edge_bx[mw_ix], edge_by[mw_ix]])], axis=1)))
    google_lines, google_mw_share, google_mw_len_m = [], np.empty(len(pairs_df)), np.empty(len(pairs_df))
    for i, encoded in enumerate(pairs_df.polyline):
        lat_lon = decode_polyline(encoded)
        x, y = to_metric.transform(lat_lon[:, 1], lat_lon[:, 0])
        is_real = np.hypot(np.diff(x), np.diff(y)) > 0
        line = (x[:-1][is_real], y[:-1][is_real], x[1:][is_real], y[1:][is_real])
        google_lines.append(line)
        piece = pieces(*line)
        on_mw = matched(piece, edge_ax[dense_mw_ix], edge_ay[dense_mw_ix], edge_bx[dense_mw_ix],
                        edge_by[dense_mw_ix], tree=dense_mw_tree)
        google_mw_share[i] = piece["length"][on_mw].sum() / piece["length"].sum()
        on_any_mw = matched(piece, edge_ax[mw_ix], edge_ay[mw_ix], edge_bx[mw_ix], edge_by[mw_ix], tree=mw_tree)
        google_mw_len_m[i] = piece["length"][on_any_mw].sum()
    print(f"google polylines decoded; mean dense-motorway length share {google_mw_share.mean():.4f}", flush=True)

    out_df = pairs_df[["pair_id", "draw_no", "dest_hex_id", "google_drive_duration_sec"]].copy()
    out_df["google_dense_mw_share"] = google_mw_share
    out_df["google_mw_len_m"] = google_mw_len_m
    for variant, variant_routes in routes.items():
        columns = {name: np.empty(len(pairs_df)) for name in
                   ("overlap_google", "overlap_route", "dense_mw_share", "B", "D", "S", "M_dense_mw", "T",
                    "S_ramp", "S_motorway", "mw_len_m", "route_len_m")}
        hashes = []
        scales_mw = VARIANTS[variant]["scales_motorway"]
        for i, positions in enumerate(variant_routes):
            gx0, gy0, gx1, gy1 = google_lines[i]
            ax, ay, bx, by = edge_ax[positions], edge_ay[positions], edge_bx[positions], edge_by[positions]
            google_piece = pieces(gx0, gy0, gx1, gy1)
            columns["overlap_google"][i] = (google_piece["length"][matched(google_piece, ax, ay, bx, by)].sum()
                                            / google_piece["length"].sum())
            route_piece = pieces(ax, ay, bx, by)
            columns["overlap_route"][i] = (route_piece["length"][matched(route_piece, gx0, gy0, gx1, gy1)].sum()
                                           / route_piece["length"].sum())
            length = edge_len_m[positions]
            columns["dense_mw_share"][i] = length[is_dense_mw[positions]].sum() / length.sum()
            columns["mw_len_m"][i], columns["route_len_m"][i] = length[is_motorway[positions]].sum(), length.sum()
            t, dense, mw = time_s[positions], edge_level[positions] == MAX_LEVEL, is_motorway[positions]
            is_scaled = dense & (np.ones_like(mw) if scales_mw else ~mw)
            columns["B"][i], columns["D"][i] = t[~is_scaled].sum(), t[is_scaled].sum()
            columns["M_dense_mw"][i], columns["T"][i] = t[dense & mw].sum(), t.sum()
            signal = head_signal[positions]
            columns["S"][i] = signal.sum()
            columns["S_ramp"][i] = signal[geometry["is_motorway_link"][positions]].sum()
            columns["S_motorway"][i] = signal[geometry["is_motorway_main"][positions]].sum()
            hashes.append(hash(positions.tobytes()))
        for name, values in columns.items():
            out_df[f"{variant}_{name}"] = values
        out_df[f"{variant}_route_hash"] = hashes
        if variant != "blind":
            params = VARIANTS[variant]
            p, residual = fit([columns["B"], columns["D"], columns["S"]], google_s,
                              np.array([1.2, 1.2 * params["m"], 1.2 * params["beta"]]))
            out_df[f"{variant}_log_resid"] = residual
            print(f"{variant} refit on its routes: ALPHA {p[0]:.4f}, m {p[1] / p[0]:.4f}, beta {p[2] / p[0]:.3f}, "
                  f"loss {soft_l1(residual).sum():.3f}", flush=True)

    # statistics
    hex_codes, hex_ix = np.unique(out_df.dest_hex_id.to_numpy(), return_inverse=True)
    n_hex = len(hex_codes)
    draws = np.random.default_rng(BOOTSTRAP_SEED).integers(n_hex, size=(N_BOOTSTRAP, n_hex))
    summary = dict(run_date=RUN_DATE, n_pairs=len(out_df), n_hex=n_hex, variants=VARIANTS)

    is_differ = out_df.C_route_hash.to_numpy() != out_df.D_route_hash.to_numpy()
    match = {"pairs_C_D_routes_differ": int(is_differ.sum())}
    for metric in ("overlap_google", "overlap_route", "dense_mw_share"):
        match[metric] = {v: rounded(hex_bootstrap_mean(out_df[f"{v}_{metric}"].to_numpy(), hex_ix, n_hex, draws))
                         for v in VARIANTS}
        match[f"{metric}_D_minus_C"] = rounded(hex_bootstrap_mean(
            (out_df[f"D_{metric}"] - out_df[f"C_{metric}"]).to_numpy(), hex_ix, n_hex, draws))
        sub_hex_codes, sub_hex_ix = np.unique(out_df.dest_hex_id.to_numpy()[is_differ], return_inverse=True)
        sub_draws = np.random.default_rng(BOOTSTRAP_SEED).integers(len(sub_hex_codes), size=(N_BOOTSTRAP, len(sub_hex_codes)))
        match[f"{metric}_D_minus_C_differing_only"] = rounded(hex_bootstrap_mean(
            (out_df[f"D_{metric}"] - out_df[f"C_{metric}"]).to_numpy()[is_differ], sub_hex_ix, len(sub_hex_codes),
            sub_draws))
    match["google_dense_mw_share"] = rounded(hex_bootstrap_mean(google_mw_share, hex_ix, n_hex, draws))
    match["dense_mw_share_minus_google"] = {
        v: rounded(hex_bootstrap_mean(out_df[f"{v}_dense_mw_share"].to_numpy() - google_mw_share, hex_ix, n_hex, draws))
        for v in VARIANTS}
    summary["1_route_match"] = match

    residuals = {}
    for variant in ("C", "D"):
        x = (out_df[f"{variant}_M_dense_mw"] / out_df[f"{variant}_T"]).to_numpy()
        log_t = np.log(out_df[f"{variant}_T"].to_numpy())
        y = out_df[f"{variant}_log_resid"].to_numpy()
        residuals[variant] = dict(
            mean_x=round(float(x.mean()), 5), share_pairs_x_pos=round(float((x > 0).mean()), 4),
            slope_plain=rounded(hex_bootstrap_slope(y, [x], hex_ix, n_hex, draws)),
            slope_controlled_log_T=rounded(hex_bootstrap_slope(y, [x, log_t], hex_ix, n_hex, draws)),
            mean_resid_by_x_bin={label: round(float(y[mask].mean()), 5) if mask.any() else None
                                 for label, mask in (("0", x == 0), ("0-10%", (x > 0) & (x <= 0.1)),
                                                     ("10-30%", (x > 0.1) & (x <= 0.3)), (">30%", x > 0.3))},
            n_by_x_bin=[int((x == 0).sum()), int(((x > 0) & (x <= 0.1)).sum()),
                        int(((x > 0.1) & (x <= 0.3)).sum()), int((x > 0.3).sum())])
    summary["2_residual_vs_dense_mw_share"] = residuals

    summary["3_ramp_signals"] = {v: dict(
        S_total=int(out_df[f"{v}_S"].sum()), S_ramp=int(out_df[f"{v}_S_ramp"].sum()),
        S_motorway=int(out_df[f"{v}_S_motorway"].sum()),
        ramp_share=round(float(out_df[f"{v}_S_ramp"].sum() / out_df[f"{v}_S"].sum()), 5),
        pairs_with_ramp_signal=round(float((out_df[f"{v}_S_ramp"] > 0).mean()), 4),
        is_material=bool(out_df[f"{v}_S_ramp"].sum() / out_df[f"{v}_S"].sum() >= RAMP_MATERIAL_SHARE))
        for v in VARIANTS}

    summary["4_classification_at_cut"] = classification_at_cut(out_df, hex_ix, n_hex, draws)
    summary["5_route_choice_cases"] = route_choice_cases(out_df)
    summary["6_bias_at_cut"] = bias_at_cut(out_df)

    print(json.dumps(summary, indent=1))
    out_df.to_csv(PAIRS_OUT_PATH, index=False)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=1))
    sys.stdout = tee.stdout
    LOG_PATH.write_text("".join(tee.lines))


if __name__ == "__main__":
    sys.exit(main())
