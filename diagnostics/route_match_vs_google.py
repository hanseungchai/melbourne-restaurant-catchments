"""How much of Google's drive route does each model's route miss? (path match, not time)

Claim to test: the drive models differ in how often they pick Google's roads, and some model (an
off-the-shelf engine, a speed table, a fitted structure) does clearly better than the selected 2tier.
Context: blind and the 2tier screen variants leave ~38% of Google's route length off their route
(drive_motorway_absorption check 1; DESIGN.md Q16), though Google's route lies on our graph for 99.4%
of its length (google_polyline_match). The other models were never scored on path; Valhalla only on time
(valhalla_vs_google_drive). Where it would matter: a commuter-flow (corridor) layer needs routes on the
right roads, not only right times (docs/musings.md, 2026-10-14). Nothing in the pipeline relies on this
yet; descriptive, no decision rule.

Models, all on the same 3,999 training pairs (the test half is never read). On our graph (blind bundle
topology; every prepared bundle shares it, checked 2026-10-14), from the pipeline's eligible snap nodes:
  blind_b2, osmtable_b0, osmtable_b2, dense_b12, dense_fringe_b10   bundle times + beta per signal
      (fixed; their ALPHA scales time only, so it does not move routes)
  2tier, 3tier, 4tier     fitted density factors + beta, edge set "all" (2026-10-11 fit); out-of-fold:
                          each pair routed with the parameters of the fold that held it out
  google_regression       fitted pace table + beta (2026-10-12), out-of-fold edge weights
Off our graph, from Google's own leg start and end (g_o_lat ... g_d_lon):
  valhalla_defaults, valhalla_speed_table   Valhalla "auto" costing on the 2026-10-07 tile builds
      (valhalla_vs_google_drive, recipe 3)
Measure (drive_motorway_absorption's): lines cut into pieces <= 10 m; a piece is matched if a segment of
the other line lies within 10 m with heading difference <= 45 deg. Our routes are straight segments
between graph nodes.
  miss_google = share of Google's route length NOT on the model's route (primary)
  extra_route = share of the model's route length NOT on Google's route (same test reversed)
Reported: per-pair mean (hex-bootstrap 95% CI, destination hexes resampled), pooled (length-weighted),
quartiles, share of pairs under 10% / over 50% missed, by Google time band, and every model's paired
difference against 2tier (the selected model).
Check: blind_b2 here should reproduce drive_motorway_absorption's blind overlap_google (0.622).
Caveat: Valhalla starts and ends where Google's legs do; our routes at our own snap nodes, so trip ends
(where Google's unmatched length concentrates, google_polyline_match) favour Valhalla a little.

Conclusion (run 2026-10-14, 3,998 pairs, 1,976 destination hexes; 1 pair unroutable by Valhalla, dropped
from every model): the claim fails. No model fixes the route-choice gap. Mean miss_google [95% CI]:
valhalla_defaults 0.345 [0.334, 0.356], google_regression 0.355, dense_fringe_b10 0.358, osmtable_b2 0.360,
dense_b12 0.364, osmtable_b0 0.368, valhalla_speed_table 0.374, blind_b2 0.378 (reproduces
drive_motorway_absorption's 0.622 overlap), 4tier 0.383, 3tier 0.385, 2tier 0.386. Best minus 2tier:
-0.041 [-0.052, -0.031]. Real but small: every model leaves 35-39% of Google's length off its route.
The fitted tier models (2/3/4tier) match Google's roads worst; 3tier and 4tier are indistinguishable
from 2tier (pairs >= 10 pts apart: ~3% each way). The time fit buys time accuracy, not path accuracy.
The per-pair miss is bimodal for every model: ~25-34% of pairs miss under 10% (same route), ~30-35%
miss over 50% (a different route), with little in between (median 0.24-0.31). So the gap is a choice
between whole alternative routes, not small deviations, and the alternatives differ by pair: against
2tier, every non-tier model is >= 10 pts better on 13-34% of pairs and worse on 7-27%.
Read for the commuter-flow idea: per-trip path matching is weak for every model, Valhalla included.
Whether aggregate street flows still agree (alternatives may run on parallel streets) is not
tested here; that is the relevant test for a flow layer.

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
Reads (never writes) pipeline outputs, drive_motorway_absorption's node geometry and
valhalla_vs_google_drive's tiles. Its own routes are saved once per model and reused, never overwritten.
"""
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from joblib import Parallel, delayed
from pyproj import Transformer
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_DIR_NAME = "-37.76870_144.97196"
LAYERS_TAG = "res2021_wrk2021_ven20260925"
FILE_TAG = f"{LAYERS_TAG}_{SUBJECT_DIR_NAME}"
CALIBRATION_DIR = PROJECT_ROOT / "outputs" / "pathing_calibration"
PAIRS_PATH = CALIBRATION_DIR / SUBJECT_DIR_NAME / f"od_expanded_drive_enriched_{FILE_TAG}.csv"
SPLIT_PATH = CALIBRATION_DIR / SUBJECT_DIR_NAME / f"drive_split_{FILE_TAG}.csv"
BUNDLES_DIR = CALIBRATION_DIR / "prepared_graphs"
BUNDLE_DIRS = {name: BUNDLES_DIR / f"split_drive_edges_timed_{name}_{FILE_TAG}_routing_{suffix}"
               for name, suffix in [("blind", "b0_2"), ("osmtable", "b0_2"), ("dense", "b12"),
                                    ("dense_fringe", "b2_10_12_14")]}
EDGE_ATTRS_PATH = CALIBRATION_DIR / "fit" / SUBJECT_DIR_NAME / f"edge_attrs_{FILE_TAG}.npz"
FIT_DIR = CALIBRATION_DIR / "fit" / SUBJECT_DIR_NAME / "20261011" / "all"
REGRESSION_DIR = CALIBRATION_DIR / "fit" / SUBJECT_DIR_NAME / "20261012" / "google_regression"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
GEOMETRY_PATH = DIAGNOSTIC_DATA_DIR / "drive_motorway_absorption_20261012_geometry.npz"   # node x, y (EPSG:7855)
VALHALLA_TILES_DIRS = {
    "valhalla_defaults": DIAGNOSTIC_DATA_DIR / "valhalla_vs_google_drive_20261007_2338_defaults_tiles",
    "valhalla_speed_table": DIAGNOSTIC_DATA_DIR / "valhalla_vs_google_drive_20261007_2343_speed_table_tiles"}
VALHALLA_CONFIG_FILENAME = "valhalla_config.json"
BUILD_DONE_FILENAME = "build_done.json"
NAME = "route_match_vs_google"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
ROUTES_GLOB = f"{NAME}_*_routes_{{model}}.npz"
SHAPES_GLOB = f"{NAME}_*_shapes_{{model}}.csv"
PAIRS_OUT_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_pairs.csv"
SUMMARY_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_summary.json"
LOG_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"

# --- models --------------------------------------------------------------------------------------------
FIXED_MODELS = {"blind_b2": ("blind", 2), "osmtable_b0": ("osmtable", 0), "osmtable_b2": ("osmtable", 2),
                "dense_b12": ("dense", 12), "dense_fringe_b10": ("dense_fringe", 10)}   # bundle, beta (s/signal)
FITTED_MODELS = ["2tier", "3tier", "4tier"]
REGRESSION_MODEL = "google_regression"
VALHALLA_MODELS = list(VALHALLA_TILES_DIRS)
OUR_GRAPH_MODELS = list(FIXED_MODELS) + FITTED_MODELS + [REGRESSION_MODEL]
MODELS = OUR_GRAPH_MODELS + VALHALLA_MODELS
REFERENCE_MODEL = "2tier"
N_FOLDS = 5
FIT_EDGE_SET = "all"               # every fitted file used here; asserted
TIME_FILE = "raw_time_raw_s.npy"
SIGNALS_FILE = "signals.npy"
VALHALLA_COSTING = "auto"
VALHALLA_SHAPE_PRECISION = 1e6     # Valhalla encodes shapes as polyline6
GOOGLE_POLYLINE_PRECISION = 1e5
EXPECTED_BUILD_RECIPE = 3

# --- routing (drive_motorway_absorption's) -------------------------------------------------------------
CANDIDATE_TIE_WINDOW_M = 1.0
NO_PREDECESSOR = -9999
MIN_CSR_WEIGHT = 1e-9
ROUTE_LIMIT_S = 3 * 1500           # first search limit (s, times the largest multiplier), unlimited on a miss
ROUTE_LIMIT_PER_BETA = 100         # plus this many signals' worth of beta
N_JOBS = 8
BATCH = 20

# --- matching (drive_motorway_absorption's tolerances) -------------------------------------------------
GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:7855"           # GDA2020 / MGA 55, metres
PIECE_M = 10.0
MATCH_M = 10.0
HEADING_TOL_DEG = 45.0

# --- summary -----------------------------------------------------------------------------------------
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261014
GOOD_MISS = 0.10                   # a pair counts as "on Google's roads" below this miss share
BAD_MISS = 0.50                    # a pair counts as "mostly other roads" above this
DIFF_PTS = 0.10                    # paired gap counted as a clearly better / worse path
QUANTILES = [0.25, 0.5, 0.75]
GOOGLE_BAND_EDGES_MIN = [0, 10, 20, 30, np.inf]
SECONDS_PER_MIN = 60
PROGRESS_EVERY_N_PAIRS = 1000


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


# --- our graph -----------------------------------------------------------------------------------------
def fold_specs(model):
    """Per fold: (held-out pair ids, edge weight array, search limit)."""
    blind = BUNDLE_DIRS["blind"]
    indices = np.load(blind / "indices.npy")
    time_s = np.load(blind / TIME_FILE)
    head_signal = np.load(blind / SIGNALS_FILE)[indices].astype(float)
    specs = []
    for fold in range(1, N_FOLDS + 1):
        if model == REGRESSION_MODEL:
            params = json.loads((REGRESSION_DIR / f"{model}_fold{fold}_params.json").read_text())
            weight = np.load(REGRESSION_DIR / f"{model}_fold{fold}_edge_weight.npy")   # pace x length + beta x signal
            oof_path = REGRESSION_DIR / f"{model}_fold{fold}_oof.csv"
            limit = ROUTE_LIMIT_S + params["beta"] * ROUTE_LIMIT_PER_BETA
        else:
            params = json.loads((FIT_DIR / f"{model}_fold{fold}_params.json").read_text())
            assert params["edge_set"] == FIT_EDGE_SET, params
            with np.load(EDGE_ATTRS_PATH) as attrs:
                level = attrs["level"]
            scale = np.ones(len(level))
            for (low, high), multiplier in zip(params["groups"], params["multipliers"]):
                scale[(level >= low) & (level <= high)] = multiplier
            weight = time_s * scale + params["beta"] * head_signal
            oof_path = FIT_DIR / f"{model}_fold{fold}_oof.csv"
            limit = ROUTE_LIMIT_S * max(params["multipliers"]) + params["beta"] * ROUTE_LIMIT_PER_BETA
        specs.append((set(pd.read_csv(oof_path).pair_id), np.maximum(weight, MIN_CSR_WEIGHT), limit))
    return specs


def fixed_spec(model):
    bundle_name, beta = FIXED_MODELS[model]
    bundle = BUNDLE_DIRS[bundle_name]
    indices = np.load(bundle / "indices.npy")
    weight = np.load(bundle / TIME_FILE) + beta * np.load(bundle / SIGNALS_FILE)[indices].astype(float)
    return np.maximum(weight, MIN_CSR_WEIGHT), ROUTE_LIMIT_S + beta * ROUTE_LIMIT_PER_BETA


_TOPOLOGY = {}   # per worker process: the shared graph topology


def route_batch(weight, limit, jobs):
    """jobs: (origin ids, dest ids). Per pair: the route's CSR edge positions, in travel order."""
    if not _TOPOLOGY:
        blind = BUNDLE_DIRS["blind"]
        _TOPOLOGY.update(nodes=np.load(blind / "nodes.npy"), indptr=np.load(blind / "indptr.npy"),
                         indices=np.load(blind / "indices.npy"))
    nodes, indptr, indices = _TOPOLOGY["nodes"], _TOPOLOGY["indptr"], _TOPOLOGY["indices"]
    matrix = csr_matrix((weight, indices, indptr), shape=(len(nodes),) * 2, copy=False)
    out = []
    for origin_ids, dest_ids in jobs:
        sources = [int(np.searchsorted(nodes, node)) for node in origin_ids]
        targets = [int(np.searchsorted(nodes, node)) for node in dest_ids]
        assert all(nodes[row] == node for row, node in zip(sources + targets, origin_ids + dest_ids))
        dist, pred, _ = dijkstra(matrix, directed=True, indices=sources, min_only=True,
                                 return_predecessors=True, limit=limit)
        best = targets[int(np.argmin(dist[targets]))]
        if not np.isfinite(dist[best]):
            dist, pred, _ = dijkstra(matrix, directed=True, indices=sources, min_only=True, return_predecessors=True)
            best = targets[int(np.argmin(dist[targets]))]
        path = [best]
        while pred[path[-1]] != NO_PREDECESSOR:
            path.append(int(pred[path[-1]]))
        path.reverse()
        positions = np.empty(len(path) - 1, dtype=np.int64)
        for k, (tail, head) in enumerate(zip(path[:-1], path[1:])):
            start = indptr[tail]
            positions[k] = start + np.searchsorted(indices[start:indptr[tail + 1]], head)
        out.append(positions)
    return out


def eligible(row, end):
    """The pipeline's snap candidates: the nearest drive node, plus the second if within the tie window."""
    node_1 = int(getattr(row, f"{end}_drive_node_1"))
    node_2 = getattr(row, f"{end}_drive_node_2")
    gap_m = getattr(row, f"{end}_drive_road_dist_2_m") - getattr(row, f"{end}_drive_road_dist_1_m")
    return [node_1, int(node_2)] if pd.notna(node_2) and gap_m <= CANDIDATE_TIE_WINDOW_M and node_2 != node_1 else [node_1]


def our_routes(model, pairs_df):
    """Every pair's route under a model on our graph; saved once, reused on later runs."""
    saved = latest_saved(ROUTES_GLOB.format(model=model))
    if saved is not None:
        print(f"[{model}] reusing routes from {saved.name}")
        with np.load(saved) as data:
            positions, offsets = data["positions"], data["offsets"]
        assert len(offsets) == len(pairs_df) + 1, "saved routes are for a different pair set"
        return [positions[offsets[i]:offsets[i + 1]] for i in range(len(pairs_df))]
    t_start = datetime.datetime.now()
    ends = [(eligible(row, "origin"), eligible(row, "dest")) for row in pairs_df.itertuples()]
    if model in FIXED_MODELS:
        weight, limit = fixed_spec(model)
        specs = [(set(pairs_df.pair_id), weight, limit)]
    else:
        specs = fold_specs(model)
        assert set().union(*(ids for ids, _, _ in specs)) == set(pairs_df.pair_id), "folds do not cover the pairs"
    routes = [None] * len(pairs_df)
    for ids, weight, limit in specs:
        rows = np.flatnonzero(pairs_df.pair_id.isin(ids).to_numpy())
        batches = [rows[i:i + BATCH] for i in range(0, len(rows), BATCH)]
        results = Parallel(n_jobs=N_JOBS)(delayed(route_batch)(weight, limit, [ends[r] for r in batch])
                                          for batch in batches)
        for batch, batch_routes in zip(batches, results):
            for r, positions in zip(batch, batch_routes):
                routes[r] = positions
    offsets = np.concatenate([[0], np.cumsum([len(r) for r in routes])])
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_routes_{model}.npz"
    np.savez_compressed(out_path, positions=np.concatenate(routes), offsets=offsets)
    print(f"[{model}] routed {len(routes):,} pairs in {(datetime.datetime.now() - t_start).total_seconds():.0f} s; "
          f"saved {out_path.name}", flush=True)
    return routes


# --- Valhalla ------------------------------------------------------------------------------------------
def valhalla_shapes(model, pairs_df):
    """Valhalla route shape (polyline6) per pair; saved once, reused on later runs."""
    saved = latest_saved(SHAPES_GLOB.format(model=model))
    if saved is not None:
        print(f"[{model}] reusing shapes from {saved.name}")
        shapes_df = pd.read_csv(saved, keep_default_na=False)
        assert list(shapes_df.pair_id) == list(pairs_df.pair_id)
        return shapes_df
    from valhalla import Actor, ValhallaError   # only needed when routing; keeps reruns light
    tiles_dir = VALHALLA_TILES_DIRS[model]
    build_done = json.loads((tiles_dir / BUILD_DONE_FILENAME).read_text())
    assert build_done["recipe"] == EXPECTED_BUILD_RECIPE, build_done
    actor = Actor(str(tiles_dir / VALHALLA_CONFIG_FILENAME))
    rows = []
    for i, pair in enumerate(pairs_df.itertuples(index=False)):
        request = {"locations": [{"lat": pair.g_o_lat, "lon": pair.g_o_lon},
                                 {"lat": pair.g_d_lat, "lon": pair.g_d_lon}],
                   "costing": VALHALLA_COSTING, "directions_type": "none"}
        try:
            rows.append(dict(pair_id=pair.pair_id, shape=actor.route(request)["trip"]["legs"][0]["shape"], error=""))
        except ValhallaError as error:
            rows.append(dict(pair_id=pair.pair_id, shape="", error=str(error)))
        if (i + 1) % PROGRESS_EVERY_N_PAIRS == 0:
            print(f"  [{model}] routed {i + 1:,} / {len(pairs_df):,}", flush=True)
    shapes_df = pd.DataFrame(rows)
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_shapes_{model}.csv"
    shapes_df.to_csv(out_path, index=False)
    print(f"[{model}] {(shapes_df.error != '').sum()} failed; saved {out_path.name}", flush=True)
    return shapes_df


# --- matching --------------------------------------------------------------------------------------------
def decode_polyline(encoded, precision):
    """Encoded polyline -> array of (lat, lon)."""
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
        coords.append((lat / precision, lon / precision))
    return np.array(coords)


def bearing_deg(dx, dy):
    return np.degrees(np.arctan2(dy, dx)) % 360


def heading_difference(a_deg, b_deg):
    """Angle between two directions of travel, 0..180."""
    return np.abs((a_deg - b_deg + 180) % 360 - 180)


def to_segments(lat_lon, to_metric):
    """(lat, lon) vertices -> metric segments ax, ay, bx, by, zero-length ones dropped."""
    x, y = to_metric.transform(lat_lon[:, 1], lat_lon[:, 0])
    is_real = np.hypot(np.diff(x), np.diff(y)) > 0
    return x[:-1][is_real], y[:-1][is_real], x[1:][is_real], y[1:][is_real]


def pieces(ax, ay, bx, by):
    """Segments cut into pieces of at most PIECE_M: midpoint x, y, length, heading."""
    dx, dy = bx - ax, by - ay
    seg_len = np.hypot(dx, dy)
    n_pieces = np.maximum(np.ceil(seg_len / PIECE_M).astype(int), 1)
    seg_ix = np.repeat(np.arange(len(seg_len)), n_pieces)
    piece_ix = np.arange(len(seg_ix)) - np.repeat(np.cumsum(n_pieces) - n_pieces, n_pieces)
    fraction = (piece_ix + 0.5) / n_pieces[seg_ix]
    return dict(x=ax[seg_ix] + fraction * dx[seg_ix], y=ay[seg_ix] + fraction * dy[seg_ix],
                length=seg_len[seg_ix] / n_pieces[seg_ix], heading=bearing_deg(dx, dy)[seg_ix])


def matched_length(piece, ax, ay, bx, by):
    """Length of the pieces lying within MATCH_M of a segment with heading difference <= HEADING_TOL_DEG."""
    if len(ax) == 0:
        return 0.0
    geoms = shapely.linestrings(np.stack([np.column_stack([ax, ay]), np.column_stack([bx, by])], axis=1))
    point_ix, seg_ix = shapely.STRtree(geoms).query(shapely.points(piece["x"], piece["y"]),
                                                    predicate="dwithin", distance=MATCH_M)
    is_aligned = heading_difference(piece["heading"][point_ix], bearing_deg(bx - ax, by - ay)[seg_ix]) <= HEADING_TOL_DEG
    is_matched = np.zeros(len(piece["x"]), bool)
    is_matched[point_ix[is_aligned]] = True
    return piece["length"][is_matched].sum()


def match_pair(google_line, google_piece, route_line):
    """(miss_google, extra_route, route length m) for one pair; NaN when the model has no route."""
    route_piece = pieces(*route_line)
    route_len_m = route_piece["length"].sum()
    if route_len_m == 0:
        return np.nan, np.nan, 0.0
    miss = 1 - matched_length(google_piece, *route_line) / google_piece["length"].sum()
    extra = 1 - matched_length(route_piece, *google_line) / route_len_m
    return miss, extra, route_len_m


def hex_bootstrap_mean(values, hex_ix, n_hex, draws):
    """Mean of values per pair, and its 95% CI with destination hexes resampled."""
    sums = np.bincount(hex_ix, weights=values, minlength=n_hex)
    counts = np.bincount(hex_ix, minlength=n_hex).astype(float)
    boot = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    low, high = np.percentile(boot, [2.5, 97.5])
    return [round(float(values.mean()), 4), round(float(low), 4), round(float(high), 4)]


def main():
    tee = Tee()
    sys.stdout = tee
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"{NAME}  run {RUN_DATE}")
    split_df = pd.read_csv(SPLIT_PATH)
    train_ids = set(split_df.loc[split_df.half == "train", "draw_no"])
    pairs_df = pd.read_csv(PAIRS_PATH)
    pairs_df = pairs_df[pairs_df.draw_no.isin(train_ids)].reset_index(drop=True)
    assert pairs_df.polyline.notna().all()
    print(f"training pairs: {len(pairs_df):,}", flush=True)

    to_metric = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
    google_lines = [to_segments(decode_polyline(encoded, GOOGLE_POLYLINE_PRECISION), to_metric)
                    for encoded in pairs_df.polyline]
    google_pieces = [pieces(*line) for line in google_lines]
    with np.load(GEOMETRY_PATH) as geometry:
        node_x, node_y = geometry["x"], geometry["y"]
    indptr = np.load(BUNDLE_DIRS["blind"] / "indptr.npy")
    indices = np.load(BUNDLE_DIRS["blind"] / "indices.npy")
    tail_rows = np.repeat(np.arange(len(indptr) - 1), np.diff(indptr))
    edge_ax, edge_ay, edge_bx, edge_by = node_x[tail_rows], node_y[tail_rows], node_x[indices], node_y[indices]

    out_df = pairs_df[["pair_id", "draw_no", "dest_hex_id", "google_drive_duration_sec"]].copy()
    out_df["google_len_m"] = [piece["length"].sum() for piece in google_pieces]
    for model in MODELS:
        if model in VALHALLA_MODELS:
            shapes = valhalla_shapes(model, pairs_df)["shape"]
            lines = [to_segments(decode_polyline(s, VALHALLA_SHAPE_PRECISION), to_metric) if s else
                     (np.empty(0),) * 4 for s in shapes]
        else:
            lines = [(edge_ax[p], edge_ay[p], edge_bx[p], edge_by[p]) for p in our_routes(model, pairs_df)]
        results = np.array([match_pair(google_lines[i], google_pieces[i], lines[i]) for i in range(len(lines))])
        for k, column in enumerate(("miss_google", "extra_route", "route_len_m")):
            out_df[f"{model}_{column}"] = results[:, k]
        print(f"[{model}] matched; mean miss_google {np.nanmean(results[:, 0]):.4f}; "
              f"{np.isnan(results[:, 0]).sum()} pairs without a route", flush=True)

    is_complete = out_df[[f"{model}_miss_google" for model in MODELS]].notna().all(axis=1).to_numpy()
    scored_df = out_df[is_complete].reset_index(drop=True)
    hex_codes, hex_ix = np.unique(scored_df.dest_hex_id, return_inverse=True)
    n_hex = len(hex_codes)
    draws = np.random.default_rng(BOOTSTRAP_SEED).integers(n_hex, size=(N_BOOTSTRAP, n_hex))
    band = pd.cut(scored_df.google_drive_duration_sec.to_numpy() / SECONDS_PER_MIN, GOOGLE_BAND_EDGES_MIN, right=False)
    google_len = scored_df.google_len_m.to_numpy()
    print(f"\nscored pairs (every model routed): {len(scored_df):,} of {len(out_df):,}; destination hexes {n_hex:,}")
    print("miss = share of Google's route length not on the model's route; "
          "extra = share of the model's route not on Google's. Pair shares: miss < 10% / miss > 50%.")

    summary = dict(run_date=RUN_DATE, n_pairs=len(scored_df), n_hex=n_hex, piece_m=PIECE_M, match_m=MATCH_M,
                   heading_tol_deg=HEADING_TOL_DEG, models={}, minus_reference={})
    print(f"\n{'model':21s} {'miss mean [95% CI]':24s} {'pooled':>7s} {'q25':>6s} {'median':>7s} {'q75':>6s} "
          f"{'<10%':>6s} {'>50%':>6s} {'extra':>6s}")
    for model in MODELS:
        miss = scored_df[f"{model}_miss_google"].to_numpy()
        extra = scored_df[f"{model}_extra_route"].to_numpy()
        stats = dict(miss_google=hex_bootstrap_mean(miss, hex_ix, n_hex, draws),
                     miss_google_pooled=round(float((miss * google_len).sum() / google_len.sum()), 4),
                     miss_google_quantiles=[round(float(q), 4) for q in np.quantile(miss, QUANTILES)],
                     share_pairs_under_good=round(float((miss < GOOD_MISS).mean()), 4),
                     share_pairs_over_bad=round(float((miss > BAD_MISS).mean()), 4),
                     extra_route=hex_bootstrap_mean(extra, hex_ix, n_hex, draws),
                     miss_google_by_band={str(b): round(float(miss[band == b].mean()), 4) for b in band.categories})
        summary["models"][model] = stats
        m, q = stats["miss_google"], stats["miss_google_quantiles"]
        print(f"{model:21s} {m[0]:.3f} [{m[1]:.3f}, {m[2]:.3f}]     {stats['miss_google_pooled']:7.3f} "
              f"{q[0]:6.3f} {q[1]:7.3f} {q[2]:6.3f} {stats['share_pairs_under_good']:6.1%} "
              f"{stats['share_pairs_over_bad']:6.1%} {stats['extra_route'][0]:6.3f}")

    counts = band.value_counts().reindex(band.categories)
    print("\nmean miss by Google time band (min): " + ", ".join(f"{b} n={n}" for b, n in counts.items()))
    for model in MODELS:
        print(f"  {model:21s} " + "  ".join(f"{v:.3f}" for v in summary["models"][model]["miss_google_by_band"].values()))

    print(f"\npaired difference in miss vs {REFERENCE_MODEL} (negative: misses less), hex-bootstrap 95% CI; "
          f"share of pairs >= {DIFF_PTS:.0%} better / worse")
    reference = scored_df[f"{REFERENCE_MODEL}_miss_google"].to_numpy()
    for model in MODELS:
        if model == REFERENCE_MODEL:
            continue
        gap = scored_df[f"{model}_miss_google"].to_numpy() - reference
        ci = hex_bootstrap_mean(gap, hex_ix, n_hex, draws)
        better, worse = round(float((gap <= -DIFF_PTS).mean()), 4), round(float((gap >= DIFF_PTS).mean()), 4)
        summary["minus_reference"][model] = dict(mean_ci=ci, share_better=better, share_worse=worse)
        print(f"  {model:21s} {ci[0]:+.3f} [{ci[1]:+.3f}, {ci[2]:+.3f}]   better {better:6.1%}  worse {worse:6.1%}")

    out_df.to_csv(PAIRS_OUT_PATH, index=False)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=1))
    sys.stdout = tee.stdout
    LOG_PATH.write_text("".join(tee.lines))
    print(f"\nsaved {PAIRS_OUT_PATH.name}, {SUMMARY_PATH.name}, {LOG_PATH.name}")


if __name__ == "__main__":
    main()
