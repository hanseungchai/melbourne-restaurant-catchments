"""Does one multiplier on R5's transit times bring stock R5 closer to Google?

Claim under test (concepts/transit.md T7 g, DESIGN.md Q22): after the walk speed (WLK-1, 4.16 km/h) and the
preference arms (diagnostics/transit_preference_arms.py: stock R5 stands), a single scalar s on R5's
door-to-door time is "kept as a test; a value near 1 is a result". Where the pipeline would rely on it: the
transit times behind the reachability bands (RCH-1, SCR-1); with s near 1, R5's times are used unscaled.

Method (Claude, 2026-10-17, set before the run, autonomous session): stock R5 at 4.16 km/h (arm B's
predictions, read from the arms diagnostic's saved pairs file). s multiplies R5's time only on pairs where
R5 picks a transit route; where it picks the direct walk the time stays (walk-only is calibrated by WLK-1).
Target: Google's default route's arrival from the requested departure (T7 f). Scored pairs: as the arms
diagnostic (training half, default in scope, R5 present). s is fitted on the 4 other CV folds by least mean
absolute error on S_GRID and applied to the held-out fold; pooled held-out predictions are scored.
Rule (Claude's rule, not user-approved; it reuses the user's arms rule of 2026-10-17): the scalar PASSES
against s = 1 if its MAE is at least MAE_GAIN_MIN lower AND neither band share (whole-minute times <= 10 /
<= 20 min) moves by more than BAND_MOVE_PP. Otherwise s = 1 stands ("near 1" is then the result). Also
reported, no verdict: s per fold; the same fit with s on every pair; the fit without the tail
(|R5 - Google| > TAIL_MIN at s = 1, the arms diagnostic's exploratory tail).

Conclusion (run 2026-10-17, 1,246 scored, R5 transit on 1,126): s = 1.01 on every fold, in all three fits
(transit only, every pair, without the 29-pair tail). MAE gain +0.02 min, band 2 -0.24 pp: FAILS the rule,
s = 1 stands. The scalar is near 1: R5's transit times need no overall stretch; the remaining error is
pair-level (the tail, route choice), not a uniform bias.

Inputs (read only): the arms diagnostic's newest *_pairs.csv in diagnostics/diagnostic_data/. Self-contained:
imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls, no routing. Results carry the
run date; a same-day rerun replaces that day's results.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_time_scalar"
ARMS_PAIRS_GLOB = "transit_preference_arms_*_pairs.csv"

S_GRID = np.round(np.arange(0.80, 1.2001, 0.005), 3)   # multipliers tried
MAE_GAIN_MIN = 0.5                             # user's arms rule, 2026-10-17
BAND_MOVE_PP = 2.0                             # user's arms rule, 2026-10-17
BAND_LIMITS_MIN = {"band_1": 10, "band_2": 20}
TAIL_MIN = 20                                  # as the arms diagnostic's exploratory tail
WALK_MATCH_S = 1                               # R5's pick is the direct walk if its time is within this of walk_s
SECONDS_PER_MIN = 60


def scaled(pred_s, is_transit, scale):
    return np.where(is_transit, pred_s * scale, pred_s)


def best_scale(pred_s, target_s, is_transit, rows):
    maes = [np.abs(scaled(pred_s[rows], is_transit[rows], s) - target_s[rows]).mean() for s in S_GRID]
    return float(S_GRID[int(np.argmin(maes))])


def stats(pred_s, target_s):
    error_min = (pred_s - target_s) / SECONDS_PER_MIN
    minutes = np.round(pred_s / SECONDS_PER_MIN)
    return {"mae_min": float(np.abs(error_min).mean()), "mean_min": float(error_min.mean()),
            "median_min": float(np.median(error_min)),
            **{band: 100 * float((minutes <= limit).mean()) for band, limit in BAND_LIMITS_MIN.items()}}


def cross_validated(pred_s, target_s, is_transit, folds, is_scored):
    held_out, per_fold = np.full(len(pred_s), np.nan), []
    for fold in np.unique(folds):
        scale = best_scale(pred_s, target_s, is_transit, is_scored & (folds != fold))
        per_fold.append((int(fold), scale))
        held_out[folds == fold] = scaled(pred_s, is_transit, scale)[folds == fold]
    return held_out, per_fold


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    pairs_path = sorted(DIAGNOSTIC_DATA_DIR.glob(ARMS_PAIRS_GLOB))[-1]
    pairs_df = pd.read_csv(pairs_path)
    pred_s, target_s = pairs_df.pred_B_s.to_numpy(float), pairs_df.google_s.to_numpy(float)
    folds, is_scored = pairs_df.fold.to_numpy(), pairs_df.is_scored.to_numpy(bool)
    is_transit = np.abs(pred_s - pairs_df.walk_s.to_numpy(float)) > WALK_MATCH_S
    is_tail = np.abs(pred_s - target_s) / SECONDS_PER_MIN > TAIL_MIN
    lines = [f"{NAME} run {run_date}", f"reading {pairs_path.name}",
             f"scored {int(is_scored.sum())}; R5 picks transit on {int((is_transit & is_scored).sum())}", ""]

    reference = stats(pred_s[is_scored], target_s[is_scored])
    held_out, per_fold = cross_validated(pred_s, target_s, is_transit, folds, is_scored)
    primary = stats(held_out[is_scored], target_s[is_scored])
    every_pair, every_fold = cross_validated(pred_s, target_s, np.ones_like(is_transit), folds, is_scored)
    no_tail, no_tail_fold = cross_validated(pred_s, target_s, is_transit, folds, is_scored & ~is_tail)
    rows = {"s = 1": reference, "s on transit (rule)": primary,
            "s on every pair": stats(every_pair[is_scored], target_s[is_scored]),
            "s = 1, no tail": stats(pred_s[is_scored & ~is_tail], target_s[is_scored & ~is_tail]),
            "s on transit, no tail": stats(no_tail[is_scored & ~is_tail], target_s[is_scored & ~is_tail])}
    lines += [pd.DataFrame(rows).T.round(3).to_string(), "",
              f"s per fold (rule): {per_fold}", f"s per fold (every pair): {every_fold}",
              f"s per fold (no tail, {int((is_scored & is_tail).sum())} tail pairs out): {no_tail_fold}", ""]

    gain = reference["mae_min"] - primary["mae_min"]
    moves = {band: primary[band] - reference[band] for band in BAND_LIMITS_MIN}
    is_pass = gain >= MAE_GAIN_MIN and all(abs(move) <= BAND_MOVE_PP for move in moves.values())
    lines.append(f"scalar vs s = 1 (Claude's rule, not user-approved): {'PASS' if is_pass else 'FAIL: s = 1 stands'}; "
                 f"MAE gain {gain:+.3f} min; band moves {', '.join(f'{b} {m:+.2f} pp' for b, m in moves.items())}")
    summary = "\n".join(lines)
    Path(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
