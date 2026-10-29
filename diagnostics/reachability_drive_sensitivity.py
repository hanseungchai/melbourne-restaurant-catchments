"""Drive catchment sensitivity: how much do venue catchments move under control models and reverted parameters?

Question (user, 2026-10-22, after the 69th autonomous run: "sensitivity analysis on the reachability pass; control
models, parameters reverted to default; metrics such as population in the catchment"). Pilot for RCH-13's
uncertainty and the write-up's robustness section; report only, nothing here changes the model of record.

Method: the drive pilot's graph build (reachability_drive_pilot.py, copied, D1): edge seconds = time_raw_s x m on
density level 15 edges + beta per signalised head node; band 3's cut = routed <= predicted cut / ALPHA; reversed
graph, multi-source from the venue hex's eligible nodes (hex -> venue, RCH-16). Venue hexes: the drive pilot's
102 (same seed and rings) plus the subject (hex 0). Catchment = residents and workers (CEN-1, never blended) of the
grid hexes whose cost (min over their eligible nodes) is within the cut.
Variants (all against M0):
  M0 model of record: 2tier all-pairs fit.
  C1 selection control: blind_b2 (no density factor, beta 2 s, its own ALPHA; training-half fit, DCL).
  R0 uncalibrated: blind speeds as built, ALPHA 1, beta 0 (OSM speed defaults, no fit).
  D0 M0 without the density factor (m = 1; ALPHA, beta kept): what the density term does.
  S0 M0 without the signal penalty (beta 0; ALPHA, m kept): what signals do.
  F1 fit stability: 2tier fitted on the training half only.
  E+ / E- cut +-1 min predicted (edge and rounding sensitivity).
  TE / TD time of day (RCH-14 scale, not the per-venue factor): predicted cut x 1.13 (evening, model too slow) and
     x 0.94 (daytime, model too fast); illustrative magnitudes from RCH-14's band errors.
Metrics per variant: median and 10-90% range of the catchment ratio to M0 per venue hex (residents, workers);
Spearman rank correlation of venue hexes' resident catchments with M0's; the subject's catchments.
Reading: report only (no rule); large moves under C1 / R0 say the calibration matters, small moves under E / F1
say the output is stable.

Conclusion (run 2026-10-22; report only): ratios to M0 over 102 venue hexes, median [10-90%], residents / workers;
  Spearman of venue ranking by resident catchment; subject residents / workers (M0 536,103 / 335,395).
  Fit stability F1 1.005 / 1.006, Spearman 1.000: the fit is stable. Cut +-1 min: 1.120 / 0.886 residents (~11-12%
  per minute), ranking ~unchanged (0.995-0.997). Time of day at RCH-14 scale: evening x1.13 cut -> 1.344, day x0.94
  -> 0.866: the factor matters about as much as 1-3 min of cut. Parameters reverted: density factor off (D0) 1.044
  [1.000-1.307], larger for inner venues (Spearman 0.912; subject workers x2.0: the CBD sits at the edge); signal
  penalty off (S0) 1.865 [1.215-2.394] (beta 16 s per signal is the largest single term); selection control C1
  (blind_b2) median 0.949 but [0.629-1.404] and Spearman 0.729 (it reorders venues: too fast in the dense core, too
  slow outside; subject workers 725,688 = x2.2); uncalibrated R0 x3.0 (OSM speed defaults reach three times the
  population). Reading (Claude's): the calibrated model's catchments are stable to the fit and move ~11% per
  minute of error, so the RCH-13 interval is dominated by time error near the cut; the subject's worker catchment
  is the most fragile number (the CBD lies near 20 min under M0).

Inputs (read only): the blind routing bundle, edge attrs, the 2tier params (all pairs, training half), blind_b2
params, the hex nodes table, venues with hex. Self-contained (CLAUDE.md D1). No API calls.
Usage: `python reachability_drive_sensitivity.py`.
"""
import datetime
import json
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
MODEL_DIR = CALIBRATION_DIR / "fit" / "model" / SUBJECT
ALL_PAIRS_PARAMS_PATH = MODEL_DIR / "2tier_all_pairs_params.json"
TRAINING_PARAMS_PATH = MODEL_DIR / "2tier_training_half_params.json"
CONTROL_PARAMS_PATH = CALIBRATION_DIR / "fit" / SUBJECT / "20261012" / "test" / "blind_b2_all_training_params.json"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"
VENUES_WITH_HEX_PATH = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT / f"venues_with_hex_ven20260925_{SUBJECT}.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "reachability_drive_sensitivity"

# --- values ----------------------------------------------------------------------------------------
SUBJECT_LAT, SUBJECT_LON = -37.7687014, 144.9719611
SUBJECT_HEX_ID = 0
BAND_3_PREDICTED_S = 1200                       # RCH-1
EDGE_MIN_S = 60                                 # E+ / E-: cut +- 1 min predicted
TIME_OF_DAY_SCALES = {"TE": 1.13, "TD": 0.94}   # RCH-14 band errors (evening +13%, day -5 to -8%), illustrative
RING_EDGES_KM = [0, 5, 25, np.inf]              # as reachability_drive_pilot.py
RING_LABELS = ["inner", "mid", "outer"]
PILOT_PER_RING = 34
SEED = 20261022
TIE_WINDOW_M = 1                                # config.CANDIDATE_TIE_WINDOW_M
MIN_CSR_WEIGHT = 1e-9
EARTH_RADIUS_M = 6_371_000
QUANTILES = (0.10, 0.90)


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def reverse_matrix(bundle, level, multiplier, beta):
    """Reversed CSR of time_raw_s x multiplier on level-15 edges + beta per signalised head (as the drive pilot)."""
    from scipy.sparse import csr_matrix
    scale = np.where(level == 15, multiplier, 1.0)
    weight = np.maximum(bundle["time_s"] * scale + beta * bundle["head_signal"], MIN_CSR_WEIGHT)
    n_nodes = len(bundle["nodes"])
    return csr_matrix((weight, bundle["indices"], bundle["indptr"]), shape=(n_nodes, n_nodes)).T.tocsr()


def main():
    import pyogrio
    from scipy.sparse.csgraph import dijkstra
    run_date = datetime.date.today().strftime("%Y%m%d")
    bundle = {name: np.load(BUNDLE_DIR / f"{name}.npy") for name in ("indptr", "indices", "nodes", "signals")}
    bundle["time_s"] = np.load(BUNDLE_DIR / "raw_time_raw_s.npy")
    bundle["head_signal"] = bundle["signals"][bundle["indices"]].astype(float)
    with np.load(EDGE_ATTRS_PATH) as attrs:
        level = attrs["level"]
    params = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in
              (("all", ALL_PAIRS_PARAMS_PATH), ("train", TRAINING_PARAMS_PATH), ("control", CONTROL_PARAMS_PATH))}
    m0 = params["all"]
    assert m0["groups"] == [[15, 15]] and params["train"]["groups"] == [[15, 15]] and params["control"]["groups"] == []
    # variant: (multiplier, beta, alpha, predicted cut s)
    variants = {"M0": (m0["multipliers"][0], m0["beta"], m0["alpha"], BAND_3_PREDICTED_S),
                "C1": (1.0, params["control"]["beta"], params["control"]["alpha"], BAND_3_PREDICTED_S),
                "R0": (1.0, 0.0, 1.0, BAND_3_PREDICTED_S),
                "D0": (1.0, m0["beta"], m0["alpha"], BAND_3_PREDICTED_S),
                "S0": (m0["multipliers"][0], 0.0, m0["alpha"], BAND_3_PREDICTED_S),
                "F1": (params["train"]["multipliers"][0], params["train"]["beta"], params["train"]["alpha"], BAND_3_PREDICTED_S),
                "E+": (m0["multipliers"][0], m0["beta"], m0["alpha"], BAND_3_PREDICTED_S + EDGE_MIN_S),
                "E-": (m0["multipliers"][0], m0["beta"], m0["alpha"], BAND_3_PREDICTED_S - EDGE_MIN_S),
                **{name: (m0["multipliers"][0], m0["beta"], m0["alpha"], BAND_3_PREDICTED_S * scale)
                   for name, scale in TIME_OF_DAY_SCALES.items()}}

    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False, columns=[
        "hex_id", "centroid_lat", "centroid_lon", "drive_node_1", "drive_node_2", "drive_road_dist_1_m",
        "drive_road_dist_2_m", "residents", "workers"])
    nodes = bundle["nodes"]
    row_1 = np.searchsorted(nodes, hex_df.drive_node_1.to_numpy(np.int64))
    node_2 = hex_df.drive_node_2.to_numpy()
    is_2 = (~np.isnan(node_2) & (hex_df.drive_road_dist_2_m.to_numpy() - hex_df.drive_road_dist_1_m.to_numpy() <= TIE_WINDOW_M)
            & (node_2 != hex_df.drive_node_1.to_numpy()))
    row_2 = np.where(is_2, np.searchsorted(nodes, np.nan_to_num(node_2).astype(np.int64)), -1)
    residents, workers = hex_df.residents.fillna(0).to_numpy(), hex_df.workers.fillna(0).to_numpy()

    venue_hexes = np.sort(pd.read_csv(VENUES_WITH_HEX_PATH, usecols=["hex_id"]).hex_id.dropna().unique().astype(np.int64))
    position = pd.Series(np.arange(len(hex_df)), index=hex_df.hex_id.to_numpy())
    venue_pos = position.reindex(venue_hexes).dropna().astype(int).to_numpy()
    distance_km = haversine_m(SUBJECT_LAT, SUBJECT_LON, hex_df.centroid_lat.to_numpy()[venue_pos],
                              hex_df.centroid_lon.to_numpy()[venue_pos]) / 1000
    ring = np.asarray(pd.cut(distance_km, RING_EDGES_KM, labels=RING_LABELS, right=False))
    rng = np.random.default_rng(SEED)
    pilot = [(label, venue_pos[k]) for label in RING_LABELS
             for k in rng.choice(np.flatnonzero(ring == label), size=PILOT_PER_RING, replace=False)]
    pilot.append(("subject", int(position[SUBJECT_HEX_ID])))

    records = []
    for name, (multiplier, beta, alpha, cut_s) in variants.items():
        reverse = reverse_matrix(bundle, level, multiplier, beta)
        routed_cut = cut_s / alpha
        for label, pos in pilot:
            sources = [row_1[pos]] + ([row_2[pos]] if row_2[pos] >= 0 else [])
            dist = dijkstra(reverse, directed=True, indices=sources, min_only=True, limit=routed_cut)
            hex_cost = np.minimum(dist[row_1], np.where(row_2 >= 0, dist[np.maximum(row_2, 0)], np.inf))
            inside = hex_cost <= routed_cut
            records.append({"variant": name, "ring": label, "hex_id": int(hex_df.hex_id.iat[pos]),
                            "residents": float(residents[inside].sum()), "workers": float(workers[inside].sum()),
                            "hexes": int(inside.sum())})
        print(f"{name} done", flush=True)
    result_df = pd.DataFrame(records)
    result_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_catchments.csv", index=False)

    base = result_df[result_df.variant == "M0"].set_index("hex_id")
    lines = [f"{NAME} run {run_date}: {len(pilot) - 1} venue hexes + the subject; band 3 cut {BAND_3_PREDICTED_S} s predicted",
             "variant (multiplier, beta, ALPHA, cut s): residents ratio to M0 median [10-90%], workers ratio median "
             "[10-90%], Spearman of resident catchments vs M0; subject residents / workers"]
    for name, (multiplier, beta, alpha, cut_s) in variants.items():
        part = result_df[result_df.variant == name].set_index("hex_id")
        venues = part[part.ring != "subject"]
        ratio_r = venues.residents / base.residents.reindex(venues.index)
        ratio_w = venues.workers / base.workers.reindex(venues.index)
        spearman = venues.residents.rank().corr(base.residents.reindex(venues.index).rank())
        subject = part.loc[SUBJECT_HEX_ID]
        lines.append(f"  {name} ({multiplier:.3f}, {beta:.1f}, {alpha:.3f}, {cut_s:.0f}): residents {ratio_r.median():.3f} "
                     f"[{ratio_r.quantile(QUANTILES[0]):.3f}-{ratio_r.quantile(QUANTILES[1]):.3f}], workers "
                     f"{ratio_w.median():.3f} [{ratio_w.quantile(QUANTILES[0]):.3f}-{ratio_w.quantile(QUANTILES[1]):.3f}], "
                     f"Spearman {spearman:.3f}; subject {subject.residents:,.0f} / {subject.workers:,.0f}")
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main()
