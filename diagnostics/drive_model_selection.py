"""Is 2tier the drive model the selection round chose, by its own pre-set rules?

Claim: the drive model the pipeline uses is 2tier (fitted level-15 factor on every edge, beta per
signal, ALPHA), chosen in the 2026-10-11/12 selection round (docs/concepts/drive-calibration.md):
  DCL-4  the structure rule: the simplest structure passing the guards wins unless a more complex one
         beats it on out-of-fold loss AND accuracy, each paired 95% CI excluding 0;
  DCL-8  the final comparison (out-of-fold, training half): 2tier has the top accuracy; no model
         passes every guard; 2tier fails only the rural density tier (user's choice, 2026-10-12);
  DCL-9  the one opening of the test half: 2tier accuracy 0.9233, rural +13.8% (the stated limitation).
Where the pipeline relies on it: calibrate_pathing_agent fits 2tier only (config.DRIVE_MODEL_NAME)
and the reachability pass routes with its parameters.

Method: reads the round's saved tables from output_backup/drive_model_selection_20261012_backup/
(copies of outputs/pathing_calibration/fit/<subject>/; the selection code that made them is parked
in docs/parked_code/drive_model_selection.md). It
  1. recomputes the point scores (accuracy at the cut, bias, drift, loss) from the saved predictions
     and checks them against the saved score tables, so the tables follow from the predictions;
  2. applies the DCL-4 rule to the CV scores;
  3. lists every model's guard results in the comparison and on the test half.
The bootstrap CIs are read as saved, not recomputed (the destination-hex resampling is the parked
code's; rerunning it would only repeat it).

Conclusion (run 2026-10-13): holds. Point scores recomputed from the predictions match the saved
tables (8 model rows, CV and test; max difference 4.9e-6, the tables' 5-decimal rounding).
DCL-4: 3tier and 4tier beat 2tier on loss but not on accuracy (CIs -0.0025 to +0.0041 and -0.0023 to
+0.0041), so 2tier. Comparison: 2tier top accuracy 0.9255 (regression 0.9220, Valhalla 0.9040, blind
0.8997); no model passes every guard; 2tier fails only density tier (0, 5) +8.3%. Test half: 2tier top
accuracy 0.9233, bias and drift pass, fails only (0, 5) +13.8%; the regression (0.9208) fails (0, 5)
+8.5% and (15, 15) -9.2%.

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1); scoring constants are
copied from config.py "Scoring" as of 2026-10-13. No API calls. Writes one summary table per run date.
"""
import ast
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_DIR_NAME = "-37.76870_144.97196"
BACKUP_DIR = PROJECT_ROOT / "output_backup" / "drive_model_selection_20261012_backup" / SUBJECT_DIR_NAME
CV_DIR = BACKUP_DIR / "20261011" / "all"                 # fit_drive_models, edge set "all"
COMPARE_DIR = BACKUP_DIR / "20261012" / "compare"
TEST_DIR = BACKUP_DIR / "20261012" / "test"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
RUN_DATE = datetime.date.today().strftime("%Y%m%d")
SUMMARY_PATH = DIAGNOSTIC_DATA_DIR / f"drive_model_selection_{RUN_DATE}_summary.csv"

# --- scoring constants (copied from config.py "Scoring") -------------------------------------------
SCORE_CUT_S = 20 * 60
BIAS_WINDOW_S = (15 * 60, 25 * 60)
DRIFT_WINDOW_S = (10 * 60, 30 * 60)
LOSS_SCALE = 0.1                          # soft_l1 scale on log(predicted / Google)
POINT_TOLERANCE = 1e-5                    # saved scores are rounded to 5 decimals

# --- table columns and names ----------------------------------------------------------------------
SELECTED_MODEL = "2tier"
STRUCTURES = ("2tier", "3tier", "4tier")  # nested, simplest first
PAIR_ID_COL = "pair_id"
MODEL_COL = "model"
PREDICTED_COL = "predicted_s"
GOOGLE_COL = "google_drive_duration_sec"
PAIRS_COL = "pairs"
ALL_PAIRS = "all"
VALHALLA_PAIRS = "valhalla"               # the pairs Valhalla routed
VALHALLA_MODEL = "valhalla_speed_table"
METRICS = ("accuracy", "bias", "drift", "loss")


def score_metrics(predicted_s, google_s):
    """Point scores as the round defined them (DCL-7): accuracy at the cut, median % error in the
    bias window, slope of log error on log2 Google time in the drift window, mean soft_l1 loss."""
    log_error = np.log(predicted_s / google_s)
    is_bias = (google_s >= BIAS_WINDOW_S[0]) & (google_s <= BIAS_WINDOW_S[1])
    is_drift = (google_s >= DRIFT_WINDOW_S[0]) & (google_s <= DRIFT_WINDOW_S[1])
    soft_l1 = LOSS_SCALE ** 2 * 2 * (np.sqrt(1 + (log_error / LOSS_SCALE) ** 2) - 1)
    return dict(accuracy=float(np.mean((predicted_s <= SCORE_CUT_S) == (google_s <= SCORE_CUT_S))),
                bias=float(np.median(predicted_s[is_bias] / google_s[is_bias] - 1)),
                drift=float(np.polyfit(np.log2(google_s[is_drift]), log_error[is_drift], 1)[0]),
                loss=float(soft_l1.mean()))


def check_points(predictions_df, scores_df, label):
    """Recompute each model's point scores from its predictions; return the largest difference
    from the saved table (all pairs; Valhalla on the pairs it routed)."""
    max_diff = 0.0
    for model, model_df in predictions_df.groupby(MODEL_COL):
        pairs = VALHALLA_PAIRS if model == VALHALLA_MODEL else ALL_PAIRS
        if PAIRS_COL in scores_df:
            saved = scores_df.loc[(scores_df[MODEL_COL] == model) & (scores_df[PAIRS_COL] == pairs)].iloc[0]
        else:
            saved = scores_df.loc[scores_df[MODEL_COL] == model].iloc[0]
        recomputed = score_metrics(model_df[PREDICTED_COL].to_numpy(float), model_df[GOOGLE_COL].to_numpy(float))
        diffs = {metric: abs(recomputed[metric] - saved[metric]) for metric in METRICS}
        max_diff = max(max_diff, *diffs.values())
        is_match = all(diff <= POINT_TOLERANCE for diff in diffs.values())
        print(f"  {label:<8} {model:<20} n {len(model_df):>5,}  "
              + "  ".join(f"{metric} {recomputed[metric]:+.5f}" for metric in METRICS)
              + f"  {'match' if is_match else 'MISMATCH'}")
        assert is_match, f"{label} {model}: recomputed scores differ from the saved table: {diffs}"
    return max_diff


def structure_rule(cv_scores_df):
    """DCL-4: a more complex structure replaces the simplest only if its loss CI and accuracy CI
    against the simplest both exclude 0 in its favour."""
    winner = STRUCTURES[0]
    for structure in STRUCTURES[1:]:
        row = cv_scores_df.loc[cv_scores_df[MODEL_COL] == structure].iloc[0]
        loss_ci = ast.literal_eval(row["loss_vs_reference_ci"])
        accuracy_ci = ast.literal_eval(row["accuracy_vs_reference_ci"])
        is_better_loss = loss_ci[1] < 0
        is_better_accuracy = accuracy_ci[0] > 0
        print(f"  {structure} vs {STRUCTURES[0]}: loss CI {loss_ci} {'better' if is_better_loss else 'not separated'}; "
              f"accuracy CI {accuracy_ci} {'better' if is_better_accuracy else 'not separated'}")
        if is_better_loss and is_better_accuracy:
            winner = structure
    return winner


def guard_summary(scores_df, density_df, stage):
    """One row per model: accuracy, bias and drift guard, failing density tiers. All pairs, except
    Valhalla, which is scored only on the pairs it routed."""
    rows = []
    is_shown = (((scores_df[PAIRS_COL] == ALL_PAIRS) & (scores_df[MODEL_COL] != VALHALLA_MODEL))
                | ((scores_df[PAIRS_COL] == VALHALLA_PAIRS) & (scores_df[MODEL_COL] == VALHALLA_MODEL)))
    for _, row in scores_df[is_shown].iterrows():
        model_density_df = density_df[(density_df[MODEL_COL] == row[MODEL_COL])
                                      & (density_df[PAIRS_COL] == row[PAIRS_COL])]
        failing = model_density_df.loc[~model_density_df["is_ok"]]
        rows.append(dict(stage=stage, model=row[MODEL_COL], n_pairs=row["n_pairs"], accuracy=row["accuracy"],
                         bias=row["bias"], is_bias_ok=row["is_bias_ok"], drift=row["drift"],
                         is_drift_ok=row["is_drift_ok"] if pd.notna(row["is_drift_ok"]) else "control",
                         density_failing="; ".join(f"{tier} {effect:+.1%}" for tier, effect
                                                   in zip(failing["tier"], failing["effect"])) or "none"))
    return pd.DataFrame(rows)


def main():
    print(f"drive_model_selection: reading saved tables from {BACKUP_DIR}")
    cv_scores_df = pd.read_csv(CV_DIR / "scores.csv")
    compare_scores_df = pd.read_csv(COMPARE_DIR / "compare_scores.csv")
    test_scores_df = pd.read_csv(TEST_DIR / "test_scores.csv")

    print("\n1. Point scores recomputed from the saved predictions")
    max_diff = check_points(pd.read_csv(CV_DIR / "oof_predictions.csv"), cv_scores_df, "CV")
    test_df = pd.read_csv(TEST_DIR / "test_predictions.csv")
    max_diff = max(max_diff, check_points(test_df, test_scores_df, "test"))
    print(f"  max difference {max_diff:.1e} (tolerance {POINT_TOLERANCE:.0e})")

    print("\n2. Structure rule (DCL-4), CV on the training half")
    winner = structure_rule(cv_scores_df)
    print(f"  winner: {winner}")
    assert winner == SELECTED_MODEL, f"the rule picks {winner}, not {SELECTED_MODEL}"

    print("\n3. Guards: final comparison (training half, out of fold) and test half")
    summary_df = pd.concat([guard_summary(compare_scores_df, pd.read_csv(COMPARE_DIR / "compare_density_guard.csv"),
                                          "compare"),
                            guard_summary(test_scores_df, pd.read_csv(TEST_DIR / "test_density_guard.csv"), "test")],
                           ignore_index=True)
    with pd.option_context("display.width", 250, "display.max_columns", None):
        print(summary_df.to_string(index=False))
    for stage, stage_df in summary_df.groupby("stage"):
        top_model = stage_df.loc[stage_df["accuracy"].idxmax(), MODEL_COL]
        print(f"  {stage}: top accuracy {top_model}")

    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(SUMMARY_PATH, index=False)
    print(f"\nsummary -> {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
