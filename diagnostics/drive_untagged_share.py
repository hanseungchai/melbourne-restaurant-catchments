"""Do untagged (class-default speed) edges matter to the fitted density model?

Claim under test: the drive model fit (DESIGN_pre_spine "Drive model selection", item 1) may scale only
edges with a posted limit (tagged, not motorway/trunk) by its per-tier factors and leave class-default
(untagged) edges unscaled, because (a) untagged edges carry little route time in every tier the 4-tier
structure scales (levels 15, 11-14, 6-10), and (b) slowing the tagged dense edges does not push routes
onto untagged ones (no rat-running).
Where the pipeline relies on it: the fitting round in pathing_calibration (calibrate_pathing_agent),
which scales tagged reducible edges only (user, 2026-10-11).
Pre-registered rule (set before the first run): SUPPORTED if, on the training-half routes under
dense beta=12, the untagged share of route time is below 5% in each of tiers 15, 11-14 and 6-10, AND
the tier-15 untagged share rises by less than 2 percentage points from blind beta=2 to dense beta=12.
Otherwise NOT SUPPORTED: fit a variant with untagged edges scaled too and compare.
Route time is measured on one yardstick for both routings: each edge's blind time_raw_s (no signal
penalty, no density factor); an edge's tier is its start node's Valhalla density level.
Conclusion (run 2026-10-11, 3,999 training pairs): NOT SUPPORTED on both parts. Untagged share of
route time under dense beta=12: tier 15 11.6%, 11-14 10.1%, 6-10 12.4% (all above 5%); tier 15 rises
from 7.0% (blind beta=2) to 11.6%, +4.6 pp (rat-running). Larger finding: motorway/trunk, never
scaled, carry 46-66% of route time in every tier; when the tagged dense edges are slowed, routes
leave them (scaled share in tier 15 45% -> 34%) for untagged streets and trunk. Follow-up: which
edges the factor should act on (diagnostics/drive_fit_edge_set.py).
Self-check: the copied level rule reproduces exactly the 38,066 edges the dense variant slows.

Inputs: the blind timed graph (per-edge speed source, highway, node coordinates), the road density
raster, the routing bundles blind b0_2 and dense b12, the joined pairs and the train/test split
(training half only; the test half is never read). Default subject only.
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
Saved edge arrays (diagnostic_data) are reused on later runs and never overwritten.
"""
import datetime
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
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
BLIND_GRAPH_PATH = (PROJECT_ROOT / "outputs" / "speed_graphs" / SUBJECT_DIR_NAME
                    / f"split_drive_edges_timed_blind_{FILE_TAG}.pkl")
DENSITY_RASTER_PATH = PROJECT_ROOT / "outputs" / "road_density" / "road_density_raster.npz"
BLIND_BUNDLE_DIR = CALIBRATION_DIR / "prepared_graphs" / f"split_drive_edges_timed_blind_{FILE_TAG}_routing_b0_2"
DENSE_BUNDLE_DIR = CALIBRATION_DIR / "prepared_graphs" / f"split_drive_edges_timed_dense_{FILE_TAG}_routing_b12"
PAIRS_PATH = CALIBRATION_DIR / SUBJECT_DIR_NAME / f"od_expanded_drive_enriched_{FILE_TAG}.csv"
SPLIT_PATH = CALIBRATION_DIR / SUBJECT_DIR_NAME / f"drive_split_{FILE_TAG}.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "drive_untagged_share"

# --- rules copied from the pipeline (speed_graphs, road_density, drive_routing) ---------------------
GEOGRAPHIC_CRS = "EPSG:4326"
LEVEL_SCALE = 0.7                  # level = floor(km/km2 x 0.7 + 0.5), capped
HALF_UP = 0.5
MAX_LEVEL = 15
OUTSIDE_RASTER_LEVEL = 0           # functions/density_levels.node_levels: nodes off the raster are rural
UNREDUCED_HIGHWAY_TYPES = {"motorway", "motorway_link", "trunk", "trunk_link"}
TAGGED_SOURCE = "tagged"
CANDIDATE_TIE_WINDOW_M = 1.0       # second snap node eligible within this of the first
NO_PREDECESSOR = -9999

# --- the check -------------------------------------------------------------------------------------
TIERS = {"15": (15, 15), "11-14": (11, 14), "6-10": (6, 10), "0-5": (0, 5)}   # 4-tier structure
SCALED_TIERS = ("15", "11-14", "6-10")
EDGE_CLASSES = ("tagged_reducible", "tagged_unreduced", "untagged")
ROUTINGS = {"blind_b2": (BLIND_BUNDLE_DIR, "time_total_s_b2"), "dense_b12": (DENSE_BUNDLE_DIR, "time_total_s_b12")}
MAX_UNTAGGED_SHARE = 0.05          # pre-registered
MAX_DENSE_TIER_RISE = 0.02         # pre-registered: percentage points as a share
DENSE_RATIO_MIN = 1.0001           # dense raw time / blind raw time above this = slowed edge
N_JOBS = 8
BATCH = 50

_CACHE = {}


def edge_arrays_path():
    """Saved per-edge arrays: the newest saved file if any (reused, never overwritten), else today's."""
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_edges.npz"))
    if saved:
        return saved[-1], True
    return DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_edges.npz", False


def build_edge_arrays(out_path):
    """Per edge, in the bundles' CSR order: start-node level, edge class, blind raw time."""
    print(f"loading {BLIND_GRAPH_PATH.name} ...", flush=True)
    with open(BLIND_GRAPH_PATH, "rb") as f:
        graph = pickle.load(f)
    nodes = np.load(BLIND_BUNDLE_DIR / "nodes.npy")
    indptr = np.load(BLIND_BUNDLE_DIR / "indptr.npy")
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
    is_tagged, is_unreduced, time_raw_s = np.empty(n_edges, bool), np.empty(n_edges, bool), np.empty(n_edges)
    for i, (tail, head, data) in enumerate(graph.edges(data=True)):
        tails[i], heads[i] = tail, head
        is_tagged[i] = data["speed_source"] == TAGGED_SOURCE
        is_unreduced[i] = data["highway"] in UNREDUCED_HIGHWAY_TYPES
        time_raw_s[i] = data["time_raw_s"]
    del graph
    tail_rows, head_rows = np.searchsorted(nodes, tails), np.searchsorted(nodes, heads)
    order = np.lexsort((head_rows, tail_rows))
    assert np.array_equal(head_rows[order], indices), "edge order differs from the bundle's CSR"
    assert np.array_equal(np.searchsorted(tail_rows[order], np.arange(len(nodes))), indptr[:-1]), "indptr differs"
    edge_class = np.where(~is_tagged[order], 2, np.where(is_unreduced[order], 1, 0)).astype(np.int8)
    edge_level = node_level[tail_rows[order]].astype(np.int8)
    time_raw_s = time_raw_s[order]
    assert np.allclose(time_raw_s, np.load(BLIND_BUNDLE_DIR / "raw_time_raw_s.npy"), rtol=0, atol=1e-9)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, edge_class=edge_class, edge_level=edge_level, time_raw_s=time_raw_s)
    print(f"saved {out_path.name}", flush=True)


def _graph(bundle_dir, weight):
    key = (str(bundle_dir), weight)
    if key not in _CACHE:
        _CACHE.clear()
        nodes = np.load(bundle_dir / "nodes.npy", mmap_mode="r")
        indptr = np.load(bundle_dir / "indptr.npy", mmap_mode="r")
        indices = np.load(bundle_dir / "indices.npy", mmap_mode="r")
        search = np.load(bundle_dir / f"search_{weight}.npy", mmap_mode="r")
        _CACHE[key] = dict(nodes=nodes, indptr=indptr, indices=indices,
                           matrix=csr_matrix((search, indices, indptr), shape=(len(nodes),) * 2, copy=False))
    return _CACHE[key]


def _rows(nodes, ids):
    ids = np.asarray(ids, dtype=np.int64)
    rows = np.searchsorted(nodes, ids).clip(max=len(nodes) - 1)
    return [int(row) for row, node in zip(rows, ids) if nodes[row] == node]


def route_batch(bundle_dir, weight, jobs):
    """jobs: (pair_id, origin ids, dest ids). Returns (pair_id, CSR edge positions of the route)."""
    graph = _graph(bundle_dir, weight)
    out = []
    for pair_id, origin_ids, dest_ids in jobs:
        sources, targets = _rows(graph["nodes"], origin_ids), _rows(graph["nodes"], dest_ids)
        dist, pred, _ = dijkstra(graph["matrix"], directed=True, indices=sources, min_only=True,
                                 return_predecessors=True)
        best = targets[int(np.argmin(dist[targets]))]
        assert np.isfinite(dist[best]), pair_id
        path = [best]
        while pred[path[-1]] != NO_PREDECESSOR:
            path.append(int(pred[path[-1]]))
        path.reverse()
        positions = []
        for tail, head in zip(path[:-1], path[1:]):
            start, end = graph["indptr"][tail], graph["indptr"][tail + 1]
            positions.append(int(start + np.searchsorted(graph["indices"][start:end], head)))
        out.append((pair_id, np.array(positions, dtype=np.int64)))
    return out


def eligible(row, end):
    node_1 = int(getattr(row, f"{end}_drive_node_1"))
    node_2 = getattr(row, f"{end}_drive_node_2")
    gap_m = getattr(row, f"{end}_drive_road_dist_2_m") - getattr(row, f"{end}_drive_road_dist_1_m")
    return (node_1, int(node_2)) if pd.notna(node_2) and gap_m <= CANDIDATE_TIE_WINDOW_M and node_2 != node_1 else (node_1,)


def main():
    run_date = f"{datetime.date.today():%Y%m%d}"
    arrays_path, is_reused = edge_arrays_path()
    if is_reused:
        print(f"reusing saved edge arrays {arrays_path.name} (data of {arrays_path.name.split('_')[3]})")
    else:
        build_edge_arrays(arrays_path)
    with np.load(arrays_path) as arrays:
        edge_class, edge_level, time_raw_s = arrays["edge_class"], arrays["edge_level"], arrays["time_raw_s"]

    # self-check: the copied level rule reproduces exactly the edges the dense variant slows
    is_slowed = np.load(DENSE_BUNDLE_DIR / "raw_time_raw_s.npy") / time_raw_s > DENSE_RATIO_MIN
    expected = (edge_class == 0) & (edge_level == MAX_LEVEL)
    n_mismatch = int((is_slowed != expected).sum())
    print(f"self-check: dense-slowed edges {int(is_slowed.sum()):,}, tagged reducible level-15 edges "
          f"{int(expected.sum()):,}, mismatched {n_mismatch}")
    assert n_mismatch == 0, "level rule copy disagrees with the dense variant"

    edge_tier = np.full(len(edge_level), -1, np.int8)
    for tier_ix, (low, high) in enumerate(TIERS.values()):
        edge_tier[(edge_level >= low) & (edge_level <= high)] = tier_ix
    assert (edge_tier >= 0).all()

    split_df = pd.read_csv(SPLIT_PATH)
    train_ids = set(split_df.loc[split_df.half == "train", "draw_no"])
    pairs_df = pd.read_csv(PAIRS_PATH)
    pairs_df = pairs_df[pairs_df.draw_no.isin(train_ids)].reset_index(drop=True)
    assert not set(pairs_df.draw_no) & set(split_df.loc[split_df.half == "test", "draw_no"])
    jobs = [(row.pair_id, eligible(row, "origin"), eligible(row, "dest")) for row in pairs_df.itertuples()]
    print(f"training pairs: {len(jobs):,}", flush=True)

    rows = []
    for routing, (bundle_dir, weight) in ROUTINGS.items():
        t_start = datetime.datetime.now()
        batches = [jobs[i:i + BATCH] for i in range(0, len(jobs), BATCH)]
        results = Parallel(n_jobs=N_JOBS)(delayed(route_batch)(bundle_dir, weight, batch) for batch in batches)
        positions = np.concatenate([edges for batch in results for _, edges in batch])
        print(f"{routing}: routed in {datetime.datetime.now() - t_start}", flush=True)
        sums = np.zeros((len(TIERS), len(EDGE_CLASSES)))
        np.add.at(sums, (edge_tier[positions], edge_class[positions]), time_raw_s[positions])
        for tier_ix, tier in enumerate(TIERS):
            total_s = sums[tier_ix].sum()
            rows.append(dict(routing=routing, tier=tier, route_time_h=total_s / 3600,
                             tier_share_of_all=total_s / sums.sum(),
                             **{f"{name}_share": sums[tier_ix, k] / total_s for k, name in enumerate(EDGE_CLASSES)}))

    summary_df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(summary_df.round(4).to_string(index=False))
    share = summary_df.set_index(["routing", "tier"])["untagged_share"]
    is_small = {tier: bool(share[("dense_b12", tier)] < MAX_UNTAGGED_SHARE) for tier in SCALED_TIERS}
    rise = share[("dense_b12", "15")] - share[("blind_b2", "15")]
    is_supported = all(is_small.values()) and rise < MAX_DENSE_TIER_RISE
    verdict = dict(untagged_share_dense_b12={tier: round(float(share[("dense_b12", tier)]), 4) for tier in SCALED_TIERS},
                   below_5pct=is_small, tier15_rise_pp=round(float(rise) * 100, 2),
                   verdict="SUPPORTED" if is_supported else "NOT SUPPORTED")
    print(json.dumps(verdict, indent=1))

    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.csv", index=False)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_verdict.json").write_text(json.dumps(verdict, indent=1))


if __name__ == "__main__":
    sys.exit(main())
