"""How noisy would a drive detour be? (FRM-19's short-trip check for the drive detour bands, report only)

Claim checked (concepts/framing.md FRM-19: detour via v = t(o->v) + t(v->d) - t(o->d), drive bands 5 / 10 min;
"detours difference two times, so random error does not cancel: short-trip time accuracy is the check"). Asked by the
user 2026-10-22 (after the 69th autonomous run) before detour is presented as a legitimate measure.

Data: the selected drive model's test-half predictions (2tier fitted on the training half, test half opened once
2026-10-12; outputs/pathing_calibration/fit/<subject>/20261012/test/test_predictions.csv): predicted vs Google's
traffic-aware seconds, 4,001 pairs, pooled departure hours (no RCH-14 factor). Error = predicted - Google (min).
Measures by Google trip length: n, mean, median, SD, robust SD (1.4826 x MAD), shares within 1 / 2 / 5 min.
Detour noise from three legs: independent, SD = sqrt(sa^2 + sb^2 + sc^2); with shared-end correlation rho (each pair
of legs shares one end), Var = sa^2 + sb^2 + sc^2 + 2 rho (sa sb - sa sc - sb sc). rho is estimated as the
intraclass correlation of errors among test pairs sharing a destination hex (one-way ANOVA estimator), a stand-in for
"same end": stated, not a direct measurement on triples.
Reading (Claude's rule, written before the run, not user-approved): a detour band b is supportable if the detour
noise SD <= b / 2, marginal if <= b, else mostly noise; read on the worked examples below (short and medium detours).

Conclusion (run 2026-10-22; report only, Claude's rule): 4,001 test pairs. Short drives are accurate in level but
  spread grows with length: SD 0.9 (< 5 min), 1.5 (5-10), 2.3 (10-15), 2.9 (15-20), 3.5-3.8 (20-30), 4.8 (30-45);
  within 2 min 1.00 / 0.81 / 0.62 / 0.50 / 0.42-0.37 / 0.33; bias +0.6 to +1.0 min at 10-30 min (largely cancels in
  a + b - c). Shared-end correlation small (ICC 0.062, 924 destination hexes), so legs are close to independent.
  Detour noise SD: legs (5, 5, 8) 2.5 min -> 5 min band marginal (robust 2.2: supportable), 10 min supportable;
  (10, 10, 15) 4.2 -> 5 min marginal, 10 min supportable; (15, 15, 25) 5.4 -> 5 min noise, 10 min marginal. Reading:
  the drive 10 min detour band holds for detours built from legs up to ~15 min; the 5 min band is marginal at
  best, so it is read as indicative (or the bands widened); long-leg detours carry ~5 min of noise. Not covered:
  route-level errors shared along a corridor (the ICC by destination is a stand-in), the RCH-14 time-of-day factor.

Inputs (read only): the test predictions file above. Self-contained (CLAUDE.md D1). No API calls.
Usage: `python drive_detour_error_scope.py`.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "-37.76870_144.97196"
TEST_PREDICTIONS_PATH = (PROJECT_ROOT / "outputs" / "pathing_calibration" / "fit" / SUBJECT / "20261012" / "test"
                         / "test_predictions.csv")
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "drive_detour_error_scope"

MODEL = "2tier"                                  # config.DRIVE_MODEL_NAME
SECONDS_PER_MIN = 60
LENGTH_BINS_MIN = [0, 5, 10, 15, 20, 25, 30, 45]
WITHIN_MIN = [1, 2, 5]
MAD_TO_SD = 1.4826
DETOUR_BANDS_MIN = [5, 10]                       # FRM-19 drive bands
EXAMPLES_MIN = [(5, 5, 8), (10, 10, 15), (15, 15, 25)]   # (o->v, v->d, o->d)
MIN_GROUP_PAIRS = 2                              # destination hexes with at least this many pairs enter the ICC


def spread(errors):
    return float(errors.std()), float(MAD_TO_SD * (errors - errors.median()).abs().median())


def icc(values, groups):
    """One-way ANOVA intraclass correlation of values within groups (groups with >= MIN_GROUP_PAIRS members)."""
    frame = pd.DataFrame({"v": values, "g": groups})
    frame = frame[frame.groupby("g").v.transform("size") >= MIN_GROUP_PAIRS]
    sizes = frame.groupby("g").v.size()
    k, n = len(sizes), len(frame)
    grand = frame.v.mean()
    between = (sizes * (frame.groupby("g").v.mean() - grand) ** 2).sum() / (k - 1)
    within = ((frame.v - frame.groupby("g").v.transform("mean")) ** 2).sum() / (n - k)
    n0 = (n - (sizes ** 2).sum() / n) / (k - 1)
    return float((between - within) / (between + (n0 - 1) * within)), k, n


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    df = pd.read_csv(TEST_PREDICTIONS_PATH)
    df = df[df.model == MODEL].copy()
    df["google_min"] = df.google_drive_duration_sec / SECONDS_PER_MIN
    df["error_min"] = (df.predicted_s - df.google_drive_duration_sec) / SECONDS_PER_MIN
    df["length_bin"] = pd.cut(df.google_min, LENGTH_BINS_MIN, right=False)
    lines = [f"{NAME} run {run_date}: {MODEL} test half, {len(df):,} pairs; error = predicted - Google (min)",
             "  Google length bin: n, mean, median, SD, robust SD, share within " + " / ".join(f"{m}" for m in WITHIN_MIN) + " min"]
    bin_sd = {}
    for length_bin, bin_df in df.groupby("length_bin", observed=True):
        sd, robust = spread(bin_df.error_min)
        bin_sd[length_bin] = (sd, robust)
        lines.append(f"  {str(length_bin):10} {len(bin_df):5} {bin_df.error_min.mean():+6.2f} {bin_df.error_min.median():+6.2f} "
                     f"{sd:6.2f} {robust:6.2f}  " + " / ".join(f"{np.mean(bin_df.error_min.abs() <= m):.3f}" for m in WITHIN_MIN))
    rho, n_groups, n_pairs = icc(df.error_min.to_numpy(), df.dest_hex_id.to_numpy())
    lines += ["", f"shared-end correlation (ICC of errors within destination hex): rho {rho:.3f} ({n_groups} hexes, {n_pairs} pairs)"]

    def leg_sd(minutes, robust):
        for interval, (sd, robust_sd) in bin_sd.items():
            if interval.left <= minutes < interval.right:
                return robust_sd if robust else sd
        raise ValueError(minutes)

    lines += ["", f"detour noise SD (min) for (o->v, v->d, o->d); reading per band {DETOUR_BANDS_MIN} min "
              "(supportable <= b/2, marginal <= b, else noise):"]
    for legs in EXAMPLES_MIN:
        parts = []
        for robust in (False, True):
            sa, sb, sc = (leg_sd(m, robust) for m in legs)
            independent = np.sqrt(sa ** 2 + sb ** 2 + sc ** 2)
            correlated = np.sqrt(max(sa ** 2 + sb ** 2 + sc ** 2 + 2 * rho * (sa * sb - sa * sc - sb * sc), 0))
            readings = ", ".join(f"{b} min {'supportable' if correlated <= b / 2 else 'marginal' if correlated <= b else 'noise'}"
                                 for b in DETOUR_BANDS_MIN)
            parts.append(f"{'robust' if robust else 'SD'}: independent {independent:.1f}, with rho {correlated:.1f} ({readings})")
        lines.append(f"  {legs}: " + "; ".join(parts))
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main()
