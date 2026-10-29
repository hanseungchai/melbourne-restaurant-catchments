"""TRN-15 (a): Claude's predicted test results, written from the training numbers before the test half is opened.

Claim: the test (test half 1,248 + extension 4,000 pairs, no-wait plain at cuts 10 / 20, k = 2 range, v2 pathways,
each pair on its own date and its release's network) should land inside the ranges below if the training results
generalise. Where the pipeline relies on it: TRN-15's order (predictions, scorer check, open once); a test far
outside these ranges says the training sets were not representative, whatever the verdict.

Method (Claude's): the own-date training results (transit_pathway_network_v2_*_range_owndate_results.csv, random
sets only: training half + second batch, 3,239 scored pairs) give counts per zone (both below / R5 early / R5 late /
neither), per hard-miss window and per count ratio. Expected test size: 5,248 x 3,239 / 3,252 = ~5,227 scored
(x 1.614). 90% predictive ranges: Dirichlet / Beta (counts + 0.5) on the training counts, then multinomial /
binomial at the test size (4,000 draws, seed below). Zones here use random pairs only (the training table's zones
also hold the top-up; the test has none). Noise bar and per-release figures not simulated (judged below).

Predictions (written 2026-10-20, before the test scorer was built or any test answer read; run date in file names):
  zone 1 (n ~253): recall 0.78-0.95 (median 0.88), precision 0.72-0.90 (0.82), floor 0.64-0.82 (0.73); floor
    passes with P 0.98; balance passes with P 0.68 (training: 14 early / 9 late).
  zone 2 (n ~481): recall 0.84-0.94 (0.89), precision 0.82-0.92 (0.88), floor 0.76-0.87 (0.82); floor P 1.00;
    balance P 0.77.
  noise bar (judged, not simulated): training z1 recall upper 0.92 vs bar 0.90 is tight; a larger test narrows the
    upper end, so z1 noise bar is the zone check most likely to fail (Claude's guess P ~0.6 pass); z2 likely passes.
  hard misses (test n per window ~81 / 474 / 400 / 812):
    lost 10 (report-only): misses 0-4 (median 0), upper 0.045-0.120; passes the 5% bar with P 0.62.
    false 10: misses 1-15 (7), upper 0.012-0.052; passes P 0.93.
    lost 20: misses 5-24 (13), upper 0.029-0.088 (0.055); passes P 0.41; severe P 0.02.
    false 20: misses 17-45 (29), upper 0.033-0.073 (0.051); passes P 0.47; severe P 0.00.
  count ratio <= 10: 0.99-1.22 (median 1.096), inside 0.90-1.10 with P 0.53; <= 20: 1.03-1.12 (1.072), P 0.85.
  Pooled verdict most likely: zones pass; fail on lost 20 and / or false 20 (both pass P ~0.2), not severe, not
    concentrated -> a recorded cost, as in training. Per release and the unseen-destination subset (1,364 pairs):
    same rates expected within their wider ranges; the unseen subset has few CBD destinations, so fewer tram /
    high-service misses (false 20) are expected there.
Conclusion (test scored 2026-10-20, transit_test_score.py): every predicted quantity landed inside its 90% range:
  z1 recall / precision 0.870 / 0.892, floor 0.799; z2 0.922 / 0.869, floor 0.828; false 10 4/514, lost 20 11/417
  (passes), false 20 34/792 (fails), lost 10 0/83; ratios 1.011 / 1.084. The z2 balance fail (P pass 0.77) and the
  test half's own false 20 (14/190) were not predicted.

Self-contained (CLAUDE.md D1). No API calls, no R5; reads only the saved training results.
Usage: `python transit_test_predictions.py` (writes transit_test_predictions_<date>_summary.txt).
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_test_predictions"
RESULTS_PATTERN = "transit_pathway_network_v2_2*_range_owndate_results.csv"
RANDOM_SETS = ["train", "second"]
N_TEST_PAIRS = 5248                            # test half 1,248 + extension 4,000 (TRN-15)
N_RANDOM_PAIRS = 3252                          # training half 1,252 + second batch 2,000
ZONES_MIN = {1: (7, 13), 2: (17, 23)}
CUTS_MIN = {1: 10, 2: 20}
HARD_TRAINING = {"lost 10": (0, 50), "false 10": (4, 294), "lost 20": (8, 248), "false 20": (18, 503)}
GATING_LOW = "low_2"
N_DRAWS = 4000
SEED = 20261020
PRIOR = 0.5
WILSON_Z = 1.959964
FLOOR = 0.6
HARD_MISS_MAX = 0.05
SEVERE_MAX = 0.10
SIGN_TEST_ALPHA = 0.05
CLOSE_TOLERANCE = 0.10
COUNT_RATIO_RANGE = (0.90, 1.10)
LOW_PERCENTILE, HIGH_PERCENTILE = 5, 95


def wilson(successes, n):
    if n == 0:
        return np.nan, np.nan
    share = successes / n
    centre = (share + WILSON_Z ** 2 / (2 * n)) / (1 + WILSON_Z ** 2 / n)
    half_width = WILSON_Z * np.sqrt(share * (1 - share) / n + WILSON_Z ** 2 / (4 * n ** 2)) / (1 + WILSON_Z ** 2 / n)
    return centre - half_width, centre + half_width


def google_side(low, high, is_r5_below, cut_min):
    is_low_below, is_high_below = low <= cut_min, high <= cut_min
    return np.where(is_low_below != is_high_below, is_r5_below, is_high_below)


def spread(values):
    return (f"{np.nanpercentile(values, LOW_PERCENTILE):.3f}-{np.nanpercentile(values, HIGH_PERCENTILE):.3f} "
            f"(median {np.nanmedian(values):.3f})")


def main():
    rng = np.random.default_rng(SEED)
    path = sorted(DIAGNOSTIC_DATA_DIR.glob(RESULTS_PATTERN))[-1]
    df = pd.read_csv(path)
    df = df[df.is_scored.astype(bool) & df.set_name.isin(RANDOM_SETS)]
    n_test = round(N_TEST_PAIRS * len(df) / N_RANDOM_PAIRS)
    factor = n_test / len(df)
    lines = [f"{NAME} {datetime.date.today():%Y%m%d}: from {path.name}; training random scored {len(df)}; expected test "
             f"scored ~{n_test} (x{factor:.3f}); {HIGH_PERCENTILE - LOW_PERCENTILE}% predictive ranges, {N_DRAWS} draws"]
    for zone_no, (low_min, high_min) in ZONES_MIN.items():
        cut_min = CUTS_MIN[zone_no]
        zone_df = df[(df.default_min >= low_min) & (df.default_min <= high_min)]
        is_r5_below = zone_df.n_min.fillna(np.inf).to_numpy() <= cut_min
        is_google_below = google_side(zone_df[GATING_LOW].to_numpy(), zone_df.default_min.to_numpy(), is_r5_below, cut_min)
        counts = np.array([(is_r5_below & is_google_below).sum(), (is_r5_below & ~is_google_below).sum(),
                           (~is_r5_below & is_google_below).sum(), (~is_r5_below & ~is_google_below).sum()])
        n_zone = round(len(zone_df) * factor)
        recalls, precisions, floors, balances = [], [], [], []
        for _ in range(N_DRAWS):
            both, early, late, _ = rng.multinomial(n_zone, rng.dirichlet(counts + PRIOR))
            recall, precision = both / (both + late), both / (both + early)
            recalls.append(recall)
            precisions.append(precision)
            floors.append(min(wilson(both, both + late)[0], wilson(both, both + early)[0]))
            sign_p = binomtest(early, early + late, 0.5).pvalue if early + late else 1.0
            balances.append(sign_p >= SIGN_TEST_ALPHA and abs(recall - precision) <= CLOSE_TOLERANCE)
        lines.append(f"zone {zone_no}: training both {counts[0]}, early {counts[1]}, late {counts[2]}; test n ~{n_zone}")
        lines.append(f"  recall {spread(recalls)}; precision {spread(precisions)}; floor {spread(floors)}; "
                     f"P(floor > {FLOOR}) {np.mean(np.array(floors) > FLOOR):.2f}; P(balance passes) {np.mean(balances):.2f}")
    for test, (misses, n) in HARD_TRAINING.items():
        n_window = round(n * factor)
        test_misses = rng.binomial(n_window, rng.beta(misses + PRIOR, n - misses + PRIOR, N_DRAWS))
        uppers = np.array([wilson(k, n_window)[1] for k in test_misses])
        lines.append(f"{test}: training {misses}/{n}; test n ~{n_window}: misses {np.percentile(test_misses, LOW_PERCENTILE):.0f}-"
                     f"{np.percentile(test_misses, HIGH_PERCENTILE):.0f} (median {np.median(test_misses):.0f}); upper {spread(uppers)}; "
                     f"P(upper <= {HARD_MISS_MAX}) {np.mean(uppers <= HARD_MISS_MAX):.2f}; P(severe) {np.mean(uppers > SEVERE_MAX):.2f}")
    for cut_min in CUTS_MIN.values():
        is_r5_below = df.n_min.fillna(np.inf).to_numpy() <= cut_min
        is_google_below = df.default_min.to_numpy() <= cut_min
        counts = np.array([(is_r5_below & is_google_below).sum(), (is_r5_below & ~is_google_below).sum(),
                           (~is_r5_below & is_google_below).sum(), (~is_r5_below & ~is_google_below).sum()])
        ratios = []
        for _ in range(N_DRAWS):
            both, r5_only, google_only, _ = rng.multinomial(n_test, rng.dirichlet(counts + PRIOR))
            ratios.append((both + r5_only) / (both + google_only))
        ratios = np.array(ratios)
        lines.append(f"count ratio <= {cut_min}: training {counts[0] + counts[1]}/{counts[0] + counts[2]}; test {spread(ratios)}; "
                     f"P(in {COUNT_RATIO_RANGE}) {np.mean((ratios >= COUNT_RATIO_RANGE[0]) & (ratios <= COUNT_RATIO_RANGE[1])):.2f}")
    summary = "\n".join(lines)
    print(summary)
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_summary.txt"
    out_path.write_text(summary + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
