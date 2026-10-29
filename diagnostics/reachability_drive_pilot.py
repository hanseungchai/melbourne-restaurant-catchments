"""Reachability drive pilot: rows per search, run time and disk size per storage cutoff (DESIGN.md Q21).

Claim scoped (concepts/reachability.md RCH-15..17; DESIGN.md Q21): the drive slice can store node-level costs
out to RCH-4's 2.5x the band cut (~2,500 s routed) for all 8,959 venue hexes at a manageable time and size; the
cutoff is set from a ~100-hex pilot (inner, mid, outer). Where the pipeline would rely on it: the planned
reachability pass (`reachability.py`, not built). Scoping only, no pass/fail; the cutoff is the user's decision.

Method: the 2tier all-pairs fit on the blind routing bundle, as functions/drive_model_fit._fit_graph builds it
(copied, D1): edge seconds = time_raw_s x m on density level 15 edges (edge set "all"), x 1 elsewhere, + beta per
signalised head node; predicted = ALPHA x routed, so band 3's cut is routed <= 1,200 / ALPHA. Direction hex ->
venue (RCH-16), so each search runs on the reversed graph from the venue hex's eligible drive nodes (node 1,
plus node 2 within the 1 m tie window: drive_routing.eligible_nodes, copied), multi-source, min only.
Sample: PILOT_PER_RING venue hexes in each ring by haversine distance to the subject (inner < 5 km, mid 5-25 km,
outer >= 25 km), seeded. Per search: nodes reached and grid hexes reached (min over each hex's eligible nodes) at
each cutoff; wall time of the search at the largest cutoff and at the band cut. Disk: one parquet per cutoff
holding every pilot search's rows (source hex int32, node int32, routed seconds uint16), zstd; bytes per row
and the extrapolation to 8,959 hexes (scaled by each ring's share of venue hexes).

Conclusion (run 2026-10-22, autonomous 69th; scoping, the cutoff is the user's call): 102 venue hexes (34 per
ring; venue hexes inner 991 / mid 4,416 / outer 3,552). Search time is negligible: 0.13 s mean per hex at 2.5x
(0.02 s at the band cut), all 8,959 hexes ~0.32 h in one process. Disk is the constraint (zstd parquet, ~4.7
bytes per row): node-level rows 1x 1.28 bn / 6.0 GB, 1.5x 3.5 bn / 16.6 GB, 2.5x 9.5 bn / 44.8 GB; per grid hex
(min over its nodes) 1x 1.7 GB, 2.5x 18.2 GB; per populated hex (residents + workers >= 1: 521,044 of 4,078,906)
1x 1.2 GB, 2.5x 9.5 GB (hex sizes use node-level bytes per row: estimates). Claude's reading: with a search this
cheap, RCH-4's reason to store 2.5x (re-threshold, never re-route) is weak: a counterfactual can re-route all
hexes in ~20 min, so storing near the cut plus the RCH-14 / RCH-13 margin per populated hex looks enough.

Inputs (read only): the blind routing bundle (CSR .npy), edge attrs .npz, 2tier_all_pairs_params.json, the hex
nodes table, venues with hex. Self-contained (CLAUDE.md D1). No API calls. Usage: `python reachability_drive_pilot.py`.
"""
import datetime
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "-37.76870_144.97196"
FILE_TAG = f"res2021_wrk2021_ven20260925_{SUBJECT}"
CALIBRATION_DIR = PROJECT_ROOT / "outputs" / "pathing_calibration"
BUNDLE_DIR = CALIBRATION_DIR / "prepared_graphs" / f"split_drive_edges_timed_blind_{FILE_TAG}_routing_b0_2"
EDGE_ATTRS_PATH = CALIBRATION_DIR / "fit" / SUBJECT / f"edge_attrs_{FILE_TAG}.npz"
PARAMS_PATH = CALIBRATION_DIR / "fit" / "model" / SUBJECT / "2tier_all_pairs_params.json"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"
VENUES_WITH_HEX_PATH = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT / f"venues_with_hex_ven20260925_{SUBJECT}.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "reachability_drive_pilot"

# --- values ----------------------------------------------------------------------------------------
SUBJECT_LAT, SUBJECT_LON = -37.7687014, 144.9719611
BAND_3_PREDICTED_S = 1200                       # RCH-1
STORAGE_FACTORS = [1.0, 1.25, 1.5, 2.0, 2.5]    # x the routed band cut; 2.5 = RCH-4's starting point
RING_EDGES_KM = [0, 5, 25, np.inf]
RING_LABELS = ["inner", "mid", "outer"]
PILOT_PER_RING = 34                             # ~100 hexes (RCH-17)
SEED = 20261022
TIE_WINDOW_M = 1                                # config.CANDIDATE_TIE_WINDOW_M
MIN_CSR_WEIGHT = 1e-9                           # scipy reads a zero weight as "no edge"
EARTH_RADIUS_M = 6_371_000
N_VENUE_HEXES_EXPECTED = 8959                   # RCH-16
POPULATED_MIN_PERSONS = 1.0                     # residents + workers (area-shared, fractional) for a hex to count as populated


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def fitted_reverse_matrix():
    """The 2tier all-pairs graph, reversed (CSR), and ALPHA (as drive_model_fit._fit_graph, edge set 'all')."""
    from scipy.sparse import csr_matrix
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    (low, high), = params["groups"]
    assert params["edge_set"] == "all"
    indptr, indices = np.load(BUNDLE_DIR / "indptr.npy"), np.load(BUNDLE_DIR / "indices.npy")
    time_s = np.load(BUNDLE_DIR / "raw_time_raw_s.npy")
    signals = np.load(BUNDLE_DIR / "signals.npy")
    nodes = np.load(BUNDLE_DIR / "nodes.npy")
    with np.load(EDGE_ATTRS_PATH) as attrs:
        level = attrs["level"]
    scale = np.where((level >= low) & (level <= high), params["multipliers"][0], 1.0)
    weight = np.maximum(time_s * scale + params["beta"] * signals[indices].astype(float), MIN_CSR_WEIGHT)
    matrix = csr_matrix((weight, indices, indptr), shape=(len(nodes),) * 2)
    return matrix.T.tocsr(), nodes, params


def eligible_rows(hex_df, nodes):
    """Per hex: CSR rows of node 1, and of node 2 when within the tie window and different (else -1)."""
    row_1 = np.searchsorted(nodes, hex_df.drive_node_1.to_numpy(np.int64))
    node_2 = hex_df.drive_node_2.to_numpy()
    is_2 = (~np.isnan(node_2) & (hex_df.drive_road_dist_2_m.to_numpy() - hex_df.drive_road_dist_1_m.to_numpy() <= TIE_WINDOW_M)
            & (node_2 != hex_df.drive_node_1.to_numpy()))
    row_2 = np.where(is_2, np.searchsorted(nodes, np.nan_to_num(node_2).astype(np.int64)), -1)
    assert np.array_equal(nodes[row_1], hex_df.drive_node_1.to_numpy(np.int64)), "node 1 not in the bundle"
    return row_1, row_2


def main():
    import pyogrio
    from scipy.sparse.csgraph import dijkstra
    run_date = datetime.date.today().strftime("%Y%m%d")
    out_prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}"
    started = time.perf_counter()
    reverse, nodes, params = fitted_reverse_matrix()
    band_cut_s = BAND_3_PREDICTED_S / params["alpha"]
    cutoffs_s = [factor * band_cut_s for factor in STORAGE_FACTORS]
    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False, columns=[
        "hex_id", "centroid_lat", "centroid_lon", "drive_node_1", "drive_node_2", "drive_road_dist_1_m",
        "drive_road_dist_2_m", "residents", "workers"])
    is_populated = hex_df.residents.fillna(0).to_numpy() + hex_df.workers.fillna(0).to_numpy() >= POPULATED_MIN_PERSONS
    row_1, row_2 = eligible_rows(hex_df, nodes)
    lines = [f"{NAME} run {run_date}: graph {reverse.shape[0]:,} nodes, {reverse.nnz:,} edges; ALPHA "
             f"{params['alpha']:.4f}, m {params['multipliers'][0]:.4f} (levels {params['groups'][0]}), beta "
             f"{params['beta']:.2f} s; band cut routed {band_cut_s:.1f} s; grid hexes {len(hex_df):,} "
             f"(populated {int(is_populated.sum()):,}; load {time.perf_counter() - started:.0f} s)"]

    venue_hexes = np.sort(pd.read_csv(VENUES_WITH_HEX_PATH, usecols=["hex_id"]).hex_id.dropna().unique().astype(np.int64))
    position = pd.Series(np.arange(len(hex_df)), index=hex_df.hex_id.to_numpy())
    venue_pos = position.reindex(venue_hexes).dropna().astype(int).to_numpy()
    distance_km = haversine_m(SUBJECT_LAT, SUBJECT_LON, hex_df.centroid_lat.to_numpy()[venue_pos],
                              hex_df.centroid_lon.to_numpy()[venue_pos]) / 1000
    ring = pd.cut(distance_km, RING_EDGES_KM, labels=RING_LABELS, right=False)
    ring_counts = pd.Series(ring).value_counts().reindex(RING_LABELS)
    lines.append(f"venue hexes {len(venue_hexes):,} (expected {N_VENUE_HEXES_EXPECTED:,}; on the nodes table "
                 f"{len(venue_pos):,}); by ring {ring_counts.to_dict()}")
    rng = np.random.default_rng(SEED)
    pilot = []
    for label in RING_LABELS:
        members = np.flatnonzero(np.asarray(ring) == label)
        for k in rng.choice(members, size=min(PILOT_PER_RING, len(members)), replace=False):
            pilot.append((label, venue_pos[k], distance_km[k]))

    records, frames = [], {factor: [] for factor in STORAGE_FACTORS}
    for label, pos, km in pilot:
        sources = [row_1[pos]] + ([row_2[pos]] if row_2[pos] >= 0 else [])
        tick = time.perf_counter()
        dist = dijkstra(reverse, directed=True, indices=sources, min_only=True, limit=cutoffs_s[-1])
        search_s = time.perf_counter() - tick
        tick = time.perf_counter()
        dijkstra(reverse, directed=True, indices=sources, min_only=True, limit=band_cut_s)
        band_search_s = time.perf_counter() - tick
        hex_cost = np.minimum(dist[row_1], np.where(row_2 >= 0, dist[np.maximum(row_2, 0)], np.inf))
        record = {"ring": label, "hex_id": int(hex_df.hex_id.iat[pos]), "distance_km": km, "search_s": search_s,
                  "band_search_s": band_search_s}
        for factor, cutoff in zip(STORAGE_FACTORS, cutoffs_s):
            reached = np.flatnonzero(dist <= cutoff)
            record[f"nodes_{factor:g}"] = len(reached)
            record[f"hexes_{factor:g}"] = int((hex_cost <= cutoff).sum())
            record[f"pop_hexes_{factor:g}"] = int(((hex_cost <= cutoff) & is_populated).sum())
            frames[factor].append(pd.DataFrame({"source_hex": np.full(len(reached), record["hex_id"], np.int32),
                                                "node": reached.astype(np.int32),
                                                "cost_s": np.ceil(dist[reached]).astype(np.uint16)}))
        records.append(record)
    pilot_df = pd.DataFrame(records)
    pilot_df.to_csv(f"{out_prefix}_searches.csv", index=False)

    lines += ["", f"pilot: {len(pilot_df)} venue hexes; search wall time at {STORAGE_FACTORS[-1]}x: median "
              f"{pilot_df.search_s.median():.2f} s, mean {pilot_df.search_s.mean():.2f}, max {pilot_df.search_s.max():.2f}; "
              f"at the band cut: median {pilot_df.band_search_s.median():.2f} s"]
    lines.append("  by ring (median nodes / hexes reached at 1x and 2.5x; median search s at 2.5x):")
    for label, ring_df in pilot_df.groupby("ring", observed=True):
        lines.append(f"    {label} ({len(ring_df)}, {ring_df.distance_km.min():.0f}-{ring_df.distance_km.max():.0f} km): "
                     f"nodes {ring_df['nodes_1'].median():,.0f} / {ring_df['nodes_2.5'].median():,.0f}; hexes "
                     f"{ring_df['hexes_1'].median():,.0f} / {ring_df['hexes_2.5'].median():,.0f}; "
                     f"{ring_df.search_s.median():.2f} s")
    weights = ring_counts / ring_counts.sum()
    lines += ["", "per storage cutoff (extrapolated to all venue hexes by ring share; one process, no parallelism):",
              "  factor  routed s  rows/search (mean)  bytes/row  disk all hexes  time all hexes"]
    for factor, cutoff in zip(STORAGE_FACTORS, cutoffs_s):
        table = pd.concat(frames[factor], ignore_index=True)
        path = Path(f"{out_prefix}_rows_x{factor:g}.parquet")
        table.to_parquet(path, compression="zstd", index=False)
        bytes_per_row = path.stat().st_size / max(len(table), 1)
        ring_mean_rows = pilot_df.groupby("ring", observed=True)[f"nodes_{factor:g}"].mean().reindex(RING_LABELS)
        total_rows = float((ring_mean_rows * ring_counts).sum())
        lines.append(f"  {factor:>5g}x  {cutoff:8.0f}  {float((ring_mean_rows * weights).sum()):18,.0f}  {bytes_per_row:9.2f}"
                     f"  {total_rows * bytes_per_row / 1e9:11.2f} GB  (rows {total_rows / 1e6:,.0f} M)")
        for unit in ("hexes", "pop_hexes"):
            unit_rows = float((pilot_df.groupby("ring", observed=True)[f"{unit}_{factor:g}"].mean().reindex(RING_LABELS)
                               * ring_counts).sum())
            lines.append(f"          stored per {unit.replace('pop_hexes', 'populated hex').replace('hexes', 'grid hex')} "
                         f"instead: {unit_rows / 1e6:,.0f} M rows, ~{unit_rows * bytes_per_row / 1e9:.2f} GB "
                         f"(node-level bytes per row)")
    total_time_s = float((pilot_df.groupby("ring", observed=True).search_s.mean().reindex(RING_LABELS) * ring_counts).sum())
    lines.append(f"  search time for all venue hexes at {STORAGE_FACTORS[-1]}x: {total_time_s / 3600:.2f} h in one process "
                 f"(the same for every cutoff stored from one search); at the band cut only "
                 f"{float((pilot_df.groupby('ring', observed=True).band_search_s.mean().reindex(RING_LABELS) * ring_counts).sum()) / 3600:.2f} h")
    lines.append(f"total run {time.perf_counter() - started:.0f} s")
    summary = "\n".join(lines)
    Path(f"{out_prefix}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main()
