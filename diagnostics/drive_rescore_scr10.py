"""Does the drive model selection hold when the 20-min cut is read as Google displays it (SCR-10)?

Claim: the selection round (DCL-4, DCL-8, DCL-9; docs/concepts/drive-calibration.md) scored accuracy at
<= 1,200 s and its bias and drift guards on 15-25 and 10-30 min windows. SCR-10 (scoring.md) reads a band
of N min as Google's rounded minutes, so 20 min covers up to 1,229 s. The claim is that 2tier stays the
selected model, and its test-half scores stand, under that cut. Where the pipeline relies on it:
calibrate_pathing_agent fits 2tier only (config.DRIVE_MODEL_NAME); reachability's drive band (RCH-15).

Why no refit: the fit minimises soft_l1 on log(predicted / Google) and never reads the cut
(functions/drive_model_fit.py; parked selection code), so refitted parameters, routes and predictions
would be the same. The cut and the guard windows enter only the scores, which this script recomputes
from the round's saved predictions.

Settings (user, 2026-10-18): "recorded" = cut 1,200 s, bias window 900-1,500 s, drift window 600-1,800 s;
"scr10" = cut 1,229 s and both windows shifted by the same +29 s (929-1,529, 629-1,829). Pass/fail rules as
recorded (copied from the parked config): bias |median % error| <= 5%; drift: upper 95% CI of |slope| -
|blind slope| < 0.03; DCL-4: a more complex structure replaces 2tier only if its loss and accuracy CIs
against 2tier both exclude 0 in its favour. Paired bootstrap over destination hexes, 2,000 resamples,
seed 20261011, exactly as the parked score_drive_models. The density-share guard reads neither the cut
nor the windows, so it is read as saved.
Stop check: under "recorded", every point score and CI must match the saved tables (5-decimal rounding).

The test half was opened once (2026-10-12, DCL-9); this rescores its saved predictions under the new
cut (user, 2026-10-18): a re-read, not a new opening; no model is chosen on it.

Conclusion (run 2026-10-18): HOLDS. Stop check: "recorded" reproduces every saved table exactly (7 tables,
point and CI differences 0). DCL-4 at scr10: 2tier (3tier and 4tier better on loss, accuracy CIs
-0.00206 to +0.00350 and -0.00075 to +0.00466 include 0). No bias or drift guard flips in any table.
Out-of-fold 2tier accuracy 0.92548 -> 0.92448, still top in the comparison (regression 0.91873, Valhalla
0.90520, blind 0.89497); bias +3.7% -> +4.1% (bar 5%). Test half (re-read): 2tier 0.92327 -> 0.91877, still
top (regression 0.91502); bias +3.8% -> +3.9%; 64 of 4,001 Google times fall in (1,200, 1,229] s.

Inputs (read only): outputs/pathing_calibration/fit/-37.76870_144.97196/20261011/all/ (CV),
20261012/google_regression/, 20261012/compare/, 20261012/test/. Self-contained (CLAUDE.md D1): imports
nothing from functions/ or config.py. No routing, no API calls. Writes one summary per run date.
"""
import ast
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIT_DIR = PROJECT_ROOT / "outputs" / "pathing_calibration" / "fit" / "-37.76870_144.97196"
CV_DIR = FIT_DIR / "20261011" / "all"
REGRESSION_DIR = FIT_DIR / "20261012" / "google_regression"
COMPARE_DIR = FIT_DIR / "20261012" / "compare"
TEST_DIR = FIT_DIR / "20261012" / "test"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "drive_rescore_scr10"

# --- settings (user, 2026-10-18) and rules (copied from the parked config) --------------------------
SCR10_SHIFT_S = 29                           # SCR-10: 20 min displayed covers up to 1,229 s
SETTINGS = {"recorded": dict(cut_s=1200, bias_window_s=(900, 1500), drift_window_s=(600, 1800))}
SETTINGS["scr10"] = dict(cut_s=1200 + SCR10_SHIFT_S,
                         bias_window_s=tuple(edge + SCR10_SHIFT_S for edge in SETTINGS["recorded"]["bias_window_s"]),
                         drift_window_s=tuple(edge + SCR10_SHIFT_S for edge in SETTINGS["recorded"]["drift_window_s"]))
MAX_BIAS = 0.05
DRIFT_MARGIN = 0.03
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261011
LOSS_SCALE = 0.1
CI_PERCENTILES = (2.5, 97.5)
POINT_TOLERANCE = 1e-5                       # saved tables round to 5 decimals
CI_TOLERANCE = 2e-5                          # CI ends: rounded percentile of rounded-free values

PAIR_ID_COL, MODEL_COL, PREDICTED_COL = "pair_id", "model", "predicted_s"
DEST_HEX_COL, GOOGLE_COL, DRAW_COL = "dest_hex_id", "google_drive_duration_sec", "draw"
CONTROL_MODEL = "blind_b2"
REFERENCE_MODEL = "2tier"
STRUCTURES = ("2tier", "3tier", "4tier")
VALHALLA_MODEL = "valhalla_speed_table"
METRICS = ("accuracy", "bias", "drift", "loss")
CI_COLUMNS = ("accuracy_ci", "bias_ci", "drift_ci", "drift_vs_control_ci", "accuracy_vs_control_ci",
              "loss_vs_reference_ci", "accuracy_vs_reference_ci")


def score_metrics(predicted_s, google_s, setting):
    log_error = np.log(predicted_s / google_s)
    bias_low, bias_high = setting["bias_window_s"]
    drift_low, drift_high = setting["drift_window_s"]
    is_bias = (google_s >= bias_low) & (google_s <= bias_high)
    is_drift = (google_s >= drift_low) & (google_s <= drift_high)
    soft_l1 = LOSS_SCALE ** 2 * 2 * (np.sqrt(1 + (log_error / LOSS_SCALE) ** 2) - 1)
    cut_s = setting["cut_s"]
    return dict(accuracy=float(np.mean((predicted_s <= cut_s) == (google_s <= cut_s))),
                bias=float(np.median(predicted_s[is_bias] / google_s[is_bias] - 1)),
                drift=float(np.polyfit(np.log2(google_s[is_drift]), log_error[is_drift], 1)[0]),
                loss=float(soft_l1.mean()))


def hex_bootstrap_indices(dest_hexes):
    _, hex_ix = np.unique(dest_hexes, return_inverse=True)
    order = np.argsort(hex_ix, kind="stable")
    bounds = np.searchsorted(hex_ix[order], np.arange(hex_ix.max() + 2))
    members = [order[bounds[h]:bounds[h + 1]] for h in range(hex_ix.max() + 1)]
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for _ in range(N_BOOTSTRAP):
        yield np.concatenate([members[h] for h in rng.integers(len(members), size=len(members))])


def score_models(pred_df, setting):
    """As the parked score_drive_models, with the cut and windows from setting."""
    wide_df = pred_df.pivot(index=PAIR_ID_COL, columns=MODEL_COL, values=PREDICTED_COL)
    pair_df = pred_df.drop_duplicates(PAIR_ID_COL).set_index(PAIR_ID_COL).loc[wide_df.index]
    google_s = pair_df[GOOGLE_COL].to_numpy(float)
    models = list(wide_df.columns)
    point = {model: score_metrics(wide_df[model].to_numpy(), google_s, setting) for model in models}
    boot = {model: [] for model in models}
    for rows in hex_bootstrap_indices(pair_df[DEST_HEX_COL].to_numpy()):
        for model in models:
            boot[model].append(score_metrics(wide_df[model].to_numpy()[rows], google_s[rows], setting))
    boot = {model: pd.DataFrame(records) for model, records in boot.items()}

    def ci(values):
        low, high = np.percentile(values, CI_PERCENTILES)
        return round(float(low), 5), round(float(high), 5)

    rows = []
    for model in models:
        row = dict(model=model, n_pairs=len(google_s), **{metric: round(value, 5) for metric, value in point[model].items()},
                   accuracy_ci=ci(boot[model].accuracy), bias_ci=ci(boot[model].bias), drift_ci=ci(boot[model].drift),
                   is_bias_ok=abs(point[model]["bias"]) <= MAX_BIAS)
        if model != CONTROL_MODEL:
            drift_vs_control = ci(boot[model].drift.abs() - boot[CONTROL_MODEL].drift.abs())
            row.update(drift_vs_control_ci=drift_vs_control, is_drift_ok=drift_vs_control[1] < DRIFT_MARGIN,
                       accuracy_vs_control_ci=ci(boot[model].accuracy - boot[CONTROL_MODEL].accuracy))
        if REFERENCE_MODEL in models and model not in (CONTROL_MODEL, REFERENCE_MODEL):
            row.update(loss_vs_reference_ci=ci(boot[model].loss - boot[REFERENCE_MODEL].loss),
                       accuracy_vs_reference_ci=ci(boot[model].accuracy - boot[REFERENCE_MODEL].accuracy))
        rows.append(row)
    return pd.DataFrame(rows)


def tables():
    """{table name: (predictions, saved scores rows)} for every scored table of the round."""
    cv_df = pd.read_csv(CV_DIR / "oof_predictions.csv")
    regression_df = pd.read_csv(REGRESSION_DIR / "oof_predictions.csv")
    compare_df = pd.concat([cv_df[cv_df[MODEL_COL].isin([REFERENCE_MODEL, CONTROL_MODEL])], regression_df], ignore_index=True)
    compare_saved = pd.read_csv(COMPARE_DIR / "compare_scores.csv")
    test_df = pd.read_csv(TEST_DIR / "test_predictions.csv")
    test_saved = pd.read_csv(TEST_DIR / "test_scores.csv")
    is_valhalla = test_df[MODEL_COL] == VALHALLA_MODEL
    test_main = test_df[~is_valhalla]
    test_subset = pd.concat([test_main[test_main[PAIR_ID_COL].isin(test_df.loc[is_valhalla, PAIR_ID_COL])],
                             test_df[is_valhalla]], ignore_index=True)
    out = {"cv": (cv_df, pd.read_csv(CV_DIR / "scores.csv")),
           "compare_all": (compare_df, compare_saved[compare_saved.pairs == "all"]),
           "compare_valhalla": (pd.read_csv(COMPARE_DIR / "valhalla_pairs_oof.csv"), compare_saved[compare_saved.pairs == "valhalla"]),
           "test_all": (test_main, test_saved[test_saved.pairs == "all"]),
           "test_valhalla": (test_subset, test_saved[test_saved.pairs == "valhalla"])}
    for draw, draw_df in test_main.groupby(DRAW_COL):
        out[f"test_draw{draw}"] = (draw_df, test_saved[test_saved.pairs == f"draw{draw}"])
    return out


def compare_to_saved(scores_df, saved_df):
    """Largest point and CI difference from the saved table; list of mismatches."""
    mismatches, max_point, max_ci = [], 0.0, 0.0
    for _, row in scores_df.iterrows():
        saved = saved_df[saved_df[MODEL_COL] == row[MODEL_COL]]
        if saved.empty:
            mismatches.append(f"{row[MODEL_COL]} not in saved table")
            continue
        saved = saved.iloc[0]
        for metric in METRICS:
            diff = abs(row[metric] - saved[metric])
            max_point = max(max_point, diff)
            if diff > POINT_TOLERANCE:
                mismatches.append(f"{row[MODEL_COL]} {metric} {row[metric]} vs {saved[metric]}")
        for column in CI_COLUMNS:
            if column in row and isinstance(row[column], tuple) and isinstance(saved.get(column), str):
                saved_ci = ast.literal_eval(saved[column])
                diff = max(abs(a - b) for a, b in zip(row[column], saved_ci))
                max_ci = max(max_ci, diff)
                if diff > CI_TOLERANCE:
                    mismatches.append(f"{row[MODEL_COL]} {column} {row[column]} vs {saved_ci}")
        for flag in ("is_bias_ok", "is_drift_ok"):
            if flag in row and pd.notna(row[flag]) and pd.notna(saved.get(flag)) and bool(row[flag]) != (str(saved[flag]) == "True"):
                mismatches.append(f"{row[MODEL_COL]} {flag} {row[flag]} vs {saved[flag]}")
    return max_point, max_ci, mismatches


def structure_winner(cv_scores_df):
    winner, lines = STRUCTURES[0], []
    for structure in STRUCTURES[1:]:
        row = cv_scores_df[cv_scores_df[MODEL_COL] == structure].iloc[0]
        loss_ci, accuracy_ci = row["loss_vs_reference_ci"], row["accuracy_vs_reference_ci"]
        is_better = loss_ci[1] < 0 and accuracy_ci[0] > 0
        lines.append(f"    {structure} vs 2tier: loss CI {loss_ci}, accuracy CI {accuracy_ci}: {'replaces' if is_better else 'not separated'}")
        if is_better:
            winner = structure
    return winner, lines


def main():
    run_date = f"{datetime.date.today():%Y%m%d}"
    lines = [f"{NAME} {run_date}: settings {SETTINGS}"]
    results = {}
    for table_name, (pred_df, saved_df) in tables().items():
        for setting_name, setting in SETTINGS.items():
            scores_df = score_models(pred_df, setting)
            results[(table_name, setting_name)] = scores_df
            if setting_name == "recorded":
                max_point, max_ci, mismatches = compare_to_saved(scores_df, saved_df)
                status = "match" if not mismatches else "MISMATCH: " + "; ".join(mismatches)
                lines.append(f"stop check {table_name}: {len(scores_df)} models, max point diff {max_point:.1e}, max CI diff {max_ci:.1e}: {status}")
                print(lines[-1], flush=True)
    is_stop_ok = all("MISMATCH" not in line for line in lines if line.startswith("stop check"))
    lines.insert(1, f"STOP CHECK {'PASSED' if is_stop_ok else 'FAILED: scr10 results below are not trustworthy'}")

    for setting_name in SETTINGS:
        winner, rule_lines = structure_winner(results[("cv", setting_name)])
        lines.append(f"DCL-4 ({setting_name}): winner {winner}")
        lines += rule_lines
    for table_name in [name for name, _ in results if _ == "recorded"]:
        lines.append(f"{table_name}:")
        for setting_name in SETTINGS:
            scores_df = results[(table_name, setting_name)]
            top = scores_df.loc[scores_df.accuracy.idxmax(), MODEL_COL]
            for _, row in scores_df.iterrows():
                lines.append(f"  {setting_name:<8} {row[MODEL_COL]:<21} n {row.n_pairs:>5} acc {row.accuracy:.5f} {row.accuracy_ci} "
                             f"bias {row.bias:+.5f} ({'ok' if row.is_bias_ok else 'FAIL'}) drift {row.drift:+.5f} "
                             f"({'control' if row[MODEL_COL] == CONTROL_MODEL else 'ok' if row.is_drift_ok else 'FAIL'}) loss {row.loss:.5f}")
            lines.append(f"  {setting_name:<8} top accuracy: {top}")
        for model in results[(table_name, "recorded")][MODEL_COL]:
            old = results[(table_name, "recorded")].set_index(MODEL_COL).loc[model]
            new = results[(table_name, "scr10")].set_index(MODEL_COL).loc[model]
            flips = [flag for flag in ("is_bias_ok", "is_drift_ok") if flag in old and pd.notna(old[flag]) and bool(old[flag]) != bool(new[flag])]
            if flips:
                lines.append(f"  GUARD FLIP {model}: {flips}")
    test_df = tables()["test_all"][0]
    google_s = test_df.drop_duplicates(PAIR_ID_COL)[GOOGLE_COL]
    lines.append(f"test half: Google times in (1,200, 1,229] s: {int(((google_s > 1200) & (google_s <= 1229)).sum())} of {len(google_s)} pairs")
    summary = "\n".join(lines)
    print(summary)
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")
    pd.concat([df.assign(table=t, setting=s) for (t, s), df in results.items()]).to_csv(
        DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_scores.csv", index=False)


if __name__ == "__main__":
    main()
