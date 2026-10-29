"""Does stock R5 put pairs in Google's travel-time band often enough (time half of TRN-12)?

Claim under test (concepts/transit.md TRN-12, T7 i; DESIGN.md Q22): time for the reachability bands is
predicted by stock R5 at WALK_SPEED_KMH (4.16 km/h). Where the pipeline relies on it: the transit bands
(SCR-1, RCH-1). Also asked by the user (2026-10-18): does r5py's default (3.6 km/h), with or without a 1-min
shift, already do it?

Measure: band agreement, whole minutes (as Google displays them, SCR-10), bands <= 10, 10-20, > 20 min, R5
vs Google's default route's arrival from the requested departure (T7 f target), training half. Reported beside
it, because > 20 min holds ~85% of pairs (the draw window is r5py <= 40 min): the trivial "all > 20"
agreement, and the share of Google's <= 20 min pairs R5 puts in the same band. Rule (user, 2026-10-18): the
time prediction is good enough at >= 90% band agreement (set before this script; applied by Claude to the
overall agreement, the user's literal reading). Variants: stock R5 at 4.16 (transit_preference_arms arm B,
seconds); r5py default 3.6 and 4.2 km/h, stock and no-first-wait (TTM from t - 1 min, minus 1, i.e. R5's 60 s
board slack removed) from transit_board_slack's table (whole minutes); each also + 1 min. Error by Google
time (T7 i check a): median, mean and MAE of R5 - Google per Google band of 0-10, 10-20, 20-30, 30-45, 45+ min.

Conclusion (run 2026-10-18): PASSES the user's rule. Stock R5 at 4.16: 0.965 band agreement (1,246 pairs;
trivial 0.854), Google's <= 20 min pairs placed right 0.824 (182); misses at the 20 min edge (23 of Google's
10-20 above 20, 12 the other way, 9 swaps between <= 10 and 10-20, none across both). r5py's default 3.6:
0.936 (0.610 on <= 20); no-first-wait 0.950 (0.710); a + 1 min shift lowers agreement at 3.6 and 4.16. Error
by Google time: medians -0.2 to +0.4 min up to 45 min, MAE 1.1-2.8 min; beyond 45 min R5 early (median -4.5,
MAE 12.2): the tail (T7 h), outside the bands.

Inputs (read only): diagnostics/diagnostic_data/transit_preference_arms_20261017_pairs.csv and
transit_board_slack_20261017_results.csv (saved data of those diagnostics). No routing, no paid API calls.
Self-contained (CLAUDE.md D1). The test half is not read.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
ARMS_PAIRS_PATH = DIAGNOSTIC_DATA_DIR / "transit_preference_arms_20261017_pairs.csv"
SLACK_RESULTS_PATH = DIAGNOSTIC_DATA_DIR / "transit_board_slack_20261017_results.csv"
NAME = "transit_time_bands"

SECONDS_PER_MIN = 60
BAND_LIMITS_MIN = [10, 20]                     # <= 10, <= 20, else > 20 (DESIGN.md Cross-cutting positions)
BAND_LABELS = ["<=10", "10-20", ">20"]
SHIFTS_MIN = [0, 1]                            # user, 2026-10-18: "+ 1 min shift"
SPEEDS = ["3_6", "4_2", "5_0"]                 # transit_board_slack column suffixes (km/h)
SLACK_VARIANTS = ["stock", "no_wait_hi"]       # stock TTM; TTM from t - 1 min, minus 1
ERROR_BINS_MIN = [0, 10, 20, 30, 45, np.inf]
BAND_RULE = 0.90                               # user, 2026-10-18


def band(minutes):
    return np.select([minutes <= BAND_LIMITS_MIN[0], minutes <= BAND_LIMITS_MIN[1]], BAND_LABELS[:2], BAND_LABELS[2])


def agreement_line(label, r5_min, google_min):
    r5_band, google_band = band(r5_min), band(google_min)
    is_within = google_band != BAND_LABELS[2]
    return (f"{label}: n {len(r5_min)}, agreement {np.mean(r5_band == google_band):.3f} (trivial "
            f"{np.mean(google_band == BAND_LABELS[2]):.3f}); Google <= 20 ({is_within.sum()}) placed right "
            f"{np.mean(r5_band[is_within] == google_band[is_within]):.3f}; R5 <= 20 where Google > 20 "
            f"{int(((r5_band != BAND_LABELS[2]) & ~is_within).sum())}")


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    lines = [f"{NAME} run {run_date}", ""]

    arms_df = pd.read_csv(ARMS_PAIRS_PATH)
    arms_df = arms_df[arms_df.is_scored]
    google_min = np.round(arms_df.google_s.to_numpy() / SECONDS_PER_MIN)
    for shift in SHIFTS_MIN:
        r5_min = np.round(arms_df.pred_B_s.to_numpy() / SECONDS_PER_MIN) + shift
        lines.append(agreement_line(f"stock R5 4.16 km/h + {shift} min", r5_min, google_min))
    lines += ["", "bands (rows Google, columns stock R5 4.16):",
              pd.crosstab(band(google_min), band(np.round(arms_df.pred_B_s.to_numpy() / SECONDS_PER_MIN))).to_string(), ""]

    slack_df = pd.read_csv(SLACK_RESULTS_PATH)
    slack_df = slack_df[slack_df.google_min.notna()]
    for speed in SPEEDS:
        walk_min = slack_df[f"walk_{speed}"].fillna(np.inf).to_numpy()
        for variant in SLACK_VARIANTS:
            r5_min = slack_df[f"{variant}_{speed}"].to_numpy(float)
            if variant != "stock":
                r5_min = np.fmin(np.nan_to_num(r5_min, nan=np.inf), walk_min)
            for shift in SHIFTS_MIN:
                lines.append(agreement_line(f"board-slack table {speed} km/h {variant} + {shift} min",
                                            r5_min + shift, slack_df.google_min.to_numpy()))

    lines += ["", "error R5 - Google by Google time (stock R5 4.16, min):"]
    error_min = (arms_df.pred_B_s - arms_df.google_s) / SECONDS_PER_MIN
    google_time_min = arms_df.google_s / SECONDS_PER_MIN
    for low, high in zip(ERROR_BINS_MIN[:-1], ERROR_BINS_MIN[1:]):
        part = error_min[(google_time_min > low) & (google_time_min <= high)]
        lines.append(f"  {low}-{high} min: n {len(part)}, median {part.median():+.2f}, mean {part.mean():+.2f}, "
                     f"MAE {part.abs().mean():.2f}")

    overall = np.mean(band(np.round(arms_df.pred_B_s.to_numpy() / SECONDS_PER_MIN)) == band(google_min))
    lines += ["", f"user's rule (band agreement >= {BAND_RULE:.2f}, stock R5 4.16): "
              + ("PASSES" if overall >= BAND_RULE else "FAILS") + f" ({overall:.3f})"]
    summary = "\n".join(lines)
    Path(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
