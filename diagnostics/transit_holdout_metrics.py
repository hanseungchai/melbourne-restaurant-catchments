"""Performance metrics of the frozen transit model on the holdout, beside training and the old test (report only).

Claim reported (concepts/transit.md TRN-16; DESIGN.md Q24): how close the frozen model's minutes and bands are to
Google's default on the holdout (opened 2026-10-22 by transit_holdout_score.py), on the same footing as training and
the old test. Report only: the verdict is transit_holdout_score's reading rule; nothing here is a test. Asked by the
user, 2026-10-22 (69th, autonomous session).

Measures (scored pairs, model finite; bands 1 <= 10, 2 11-20, 3 > 20 min): minute error model - default (mean,
median, MAE, median |error|, RMSE, correlation); shares exact / within 1 / 2 / 5 / 10 min, inside Google's range
[low_2, default], early / late; 3-band accuracy against the default and against either end of the range; band
confusion; recall / precision at <= 10 and <= 20; by Google default's mode.

Conclusion (run 2026-10-22): holdout (3,995 scored, 3,969 finite) 3-band accuracy 0.969 (range 0.975); <= 10 recall /
precision 0.892 / 0.904; <= 20 0.939 / 0.900; error mean -1.84, median 0, MAE 3.00, median |error| 1.0, RMSE 11.8,
corr 0.79; within 1 min 0.643, 5 min 0.860; early 0.42 / late 0.20. Training (train + second) and old test alike
(accuracy 0.971 / 0.974, MAE 3.46 / 3.19): no sign of overfitting. 85% of pairs are band 3, so the 3-band accuracy is
flattered; the <= 10 / <= 20 rows carry the information.

Inputs (read only): transit_holdout_score_20261022_{holdout, seen}_results.csv. Self-contained (CLAUDE.md D1).
Usage: `python transit_holdout_metrics.py`.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
HOLDOUT_RESULTS_PATH = DIAGNOSTIC_DATA_DIR / "transit_holdout_score_20261022_holdout_results.csv"
SEEN_RESULTS_PATH = DIAGNOSTIC_DATA_DIR / "transit_holdout_score_20261022_seen_results.csv"
NAME = "transit_holdout_metrics"

CUTS_MIN = [10, 20]                             # bands 1-2 (SCR-1)
WITHIN_MIN = [1, 2, 5, 10]
RANGE_LOW_COLUMN = "low_2"                      # k = 2 (TRN-15)
SUBSETS = {"holdout": ("holdout",), "training random (train + second)": ("train", "second"),
           "old test (seen)": ("test", "test_ext")}


def band(minutes):
    return np.where(minutes <= CUTS_MIN[0], 1, np.where(minutes <= CUTS_MIN[1], 2, 3))


def metrics(df, label):
    df = df[df.is_scored.astype(bool)]
    finite_df = df[np.isfinite(df.model_min)]
    error = finite_df.model_min - finite_df.default_min
    abs_error = error.abs()
    model_band, google_band = band(finite_df.model_min), band(finite_df.default_min)
    low_band = band(finite_df[RANGE_LOW_COLUMN])
    is_in_range = (finite_df.model_min >= finite_df[RANGE_LOW_COLUMN]) & (finite_df.model_min <= finite_df.default_min)
    within = ", ".join(f"+-{m} {np.mean(abs_error <= m):.3f}" for m in WITHIN_MIN)
    lines = [f"{label}: scored {len(df)}, model finite {len(finite_df)} (over the cap {len(df) - len(finite_df)})",
             f"  minutes, model - Google default: mean {error.mean():+.2f}, median {error.median():+.1f}, MAE "
             f"{abs_error.mean():.2f}, median |error| {abs_error.median():.1f}, RMSE {np.sqrt((error ** 2).mean()):.2f}, "
             f"corr {np.corrcoef(finite_df.model_min, finite_df.default_min)[0, 1]:.3f}",
             f"  exact {np.mean(abs_error == 0):.3f}, {within}; inside Google's range {is_in_range.mean():.3f}; "
             f"R5 early {np.mean(error < 0):.3f} / late {np.mean(error > 0):.3f}",
             f"  3-band accuracy vs default {np.mean(model_band == google_band):.3f}; vs range (either end) "
             f"{np.mean((model_band == google_band) | (model_band == low_band)):.3f}",
             "  confusion (rows Google default band, columns model band):"]
    confusion = pd.crosstab(pd.Series(google_band, name="google"), pd.Series(model_band, name="model"))
    lines += ["    " + row for row in confusion.to_string().splitlines()]
    for k, cut in enumerate(CUTS_MIN, start=1):
        hits = int(np.sum((model_band <= k) & (google_band <= k)))
        lines.append(f"  <= {cut} min: recall {hits / np.sum(google_band <= k):.3f} ({hits}/{np.sum(google_band <= k)}), "
                     f"precision {hits / np.sum(model_band <= k):.3f} ({hits}/{np.sum(model_band <= k)})")
    lines.append("  by Google default's mode: n, mean error, median error, MAE, 3-band accuracy")
    scored = finite_df.assign(error=error, abs_error=abs_error, is_band_ok=model_band == google_band)
    for mode, mode_df in scored.groupby("mode_group"):
        lines.append(f"    {mode:15} {len(mode_df):5} {mode_df.error.mean():+6.2f} {mode_df.error.median():+5.1f} "
                     f"{mode_df.abs_error.mean():5.2f} {mode_df.is_band_ok.mean():.3f}")
    return lines


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    results_df = pd.concat([pd.read_csv(HOLDOUT_RESULTS_PATH), pd.read_csv(SEEN_RESULTS_PATH)])
    lines = [f"{NAME} run {run_date}: saved results {HOLDOUT_RESULTS_PATH.name}, {SEEN_RESULTS_PATH.name}"]
    for label, set_names in SUBSETS.items():
        lines += [""] + metrics(results_df[results_df.set_name.isin(set_names)], label)
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main()
