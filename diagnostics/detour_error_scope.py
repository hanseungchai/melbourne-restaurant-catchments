"""How noisy would a transit / walk detour be? (scoping for FRM-19's detour layer, report only)

Claim scoped (concepts/framing.md FRM-19: "detours difference two times, so random error does not cancel:
short-trip time accuracy is the check"): a detour via v is t(o->v) + t(v->d) - t(o->d), three model times, judged
against bands of 3 / 5 min (walk) and transit at stops. This reports the frozen transit model's minute error
against Google's default by trip length on every random scored pair (training, old test, holdout), and the noise a
detour would carry if the three errors were independent: SD_detour = sqrt(SD_a^2 + SD_b^2 + SD_c^2). Independence
is an assumption, stated: legs sharing streets or a line share error, which would partly cancel in the difference
(lower noise) or add (higher), unmeasured without triples. Robust spread (1.4826 x MAD) is given beside the SD,
since the tail (|error| > 20 min) dominates the SD.

Conclusion (run 2026-10-22, autonomous 69th; scoping): 12,366 random scored pairs. Short trips are accurate: under 10
  min (mostly walk-only) 87-94% within 1 min, SD 1.3-1.4 min; 10-20 min SD 2.0-2.4 (75-77% within 1 min); 20-45 min
  SD 3.4-3.8. Worked example (legs 10, 10, 15 min, independent errors): detour noise SD 3.7 min (robust 2.6) against
  bands of 3 / 5 min, so a transit detour band at 3 min would be mostly noise and 5 min marginal; walk detours (walk
  legs within 1 min on ~90% of short walk-only pairs) hold up. Reading (Claude's): FRM-23's walk-detour definition is
  supportable; transit commuter detours need either wider bands or the correlated-error case measured; drive detours
  are unchecked here (the drive test residuals are the analogue). The robust SD is coarse (whole-minute errors give
  MAD 0 or 1). Added after the drive check (2026-10-22): shared-end correlation as the intraclass correlation of
  errors within a destination hex, Var = sa^2 + sb^2 + sc^2 + 2 rho (sa sb - sa sc - sb sc): small (ICC 0.05 all,
  0.10 under 25 min), the example ~3.5 min, so independence is close.

Inputs (read only): transit_holdout_score_20261022_{holdout, seen}_results.csv. Self-contained (CLAUDE.md D1).
Usage: `python detour_error_scope.py`.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
HOLDOUT_RESULTS_PATH = DIAGNOSTIC_DATA_DIR / "transit_holdout_score_20261022_holdout_results.csv"
SEEN_RESULTS_PATH = DIAGNOSTIC_DATA_DIR / "transit_holdout_score_20261022_seen_results.csv"
NAME = "detour_error_scope"

RANDOM_SETS = ["train", "second", "test", "test_ext", "holdout"]   # topup is not random (TRN-13)
LENGTH_BINS_MIN = [0, 5, 10, 15, 20, 30, 45]
MAD_TO_SD = 1.4826
DETOUR_BANDS_MIN = [3, 5]                       # walk detour bands (FRM-19)
EXAMPLE_LEGS_MIN = (10, 10, 15)                 # o->v, v->d, o->d for the worked example
MIN_GROUP_PAIRS = 2                             # destination hexes with at least this many pairs enter the ICC
SHORT_MAX_MIN = 25                              # the ICC also on Google trips shorter than this


def spread(errors):
    return float(errors.std()), float(MAD_TO_SD * (errors - errors.median()).abs().median())


def icc(values, groups):
    """One-way ANOVA intraclass correlation within groups (as drive_detour_error_scope.py)."""
    frame = pd.DataFrame({"v": values, "g": groups})
    frame = frame[frame.groupby("g").v.transform("size") >= MIN_GROUP_PAIRS]
    sizes = frame.groupby("g").v.size()
    k, n = len(sizes), len(frame)
    between = (sizes * (frame.groupby("g").v.mean() - frame.v.mean()) ** 2).sum() / (k - 1)
    within = ((frame.v - frame.groupby("g").v.transform("mean")) ** 2).sum() / (n - k)
    n0 = (n - (sizes ** 2).sum() / n) / (k - 1)
    return float((between - within) / (between + (n0 - 1) * within)), k, n


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    df = pd.concat([pd.read_csv(HOLDOUT_RESULTS_PATH), pd.read_csv(SEEN_RESULTS_PATH)])
    df = df[df.set_name.isin(RANDOM_SETS) & df.is_scored.astype(bool) & np.isfinite(df.model_min)]
    df["error_min"] = df.model_min - df.default_min
    df["length_bin"] = pd.cut(df.default_min, LENGTH_BINS_MIN, right=False)
    lines = [f"{NAME} run {run_date}: {len(df):,} random scored pairs (frozen model), error = model - Google default (min)",
             "  Google length bin: n, mean, median, SD, robust SD, share |error| <= 1 / <= 3 min; walk-only defaults apart"]
    bin_sd = {}
    for length_bin, bin_df in df.groupby("length_bin", observed=True):
        sd, robust = spread(bin_df.error_min)
        bin_sd[length_bin] = (sd, robust)
        walk_df = bin_df[bin_df.default_walk_only.astype(bool)]
        walk_text = (f"; walk-only n {len(walk_df)}, robust SD {spread(walk_df.error_min)[1]:.2f}" if len(walk_df) >= 20 else "")
        lines.append(f"  {str(length_bin):10} {len(bin_df):5} {bin_df.error_min.mean():+6.2f} {bin_df.error_min.median():+5.1f} "
                     f"{sd:6.2f} {robust:6.2f}  {np.mean(bin_df.error_min.abs() <= 1):.3f} / "
                     f"{np.mean(bin_df.error_min.abs() <= 3):.3f}{walk_text}")
    lookup = lambda minutes: next(v for k, v in bin_sd.items() if k.left <= minutes < k.right)   # noqa: E731
    sds = [lookup(m) for m in EXAMPLE_LEGS_MIN]
    detour_sd = np.sqrt(sum(s[0] ** 2 for s in sds))
    detour_robust = np.sqrt(sum(s[1] ** 2 for s in sds))
    lines += ["", f"worked example (legs {EXAMPLE_LEGS_MIN} min, independent errors): detour noise SD {detour_sd:.1f} min, "
              f"robust {detour_robust:.1f} min, against detour bands {DETOUR_BANDS_MIN} min"]
    rho_all = icc(df.error_min.to_numpy(), df.dest_hex.to_numpy())
    short_df = df[df.default_min < SHORT_MAX_MIN]
    rho_short = icc(short_df.error_min.to_numpy(), short_df.dest_hex.to_numpy())
    sa, sb, sc = (s[0] for s in sds)
    correlated = np.sqrt(sa ** 2 + sb ** 2 + sc ** 2 + 2 * rho_short[0] * (sa * sb - sa * sc - sb * sc))
    lines.append(f"shared-end correlation (ICC within destination hex): all {rho_all[0]:.3f} ({rho_all[1]} hexes), "
                 f"Google < {SHORT_MAX_MIN} min {rho_short[0]:.3f} ({rho_short[1]} hexes); worked example with that "
                 f"rho: {correlated:.1f} min")
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main()
