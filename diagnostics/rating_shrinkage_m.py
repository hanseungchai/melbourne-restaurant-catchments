"""How strongly should a thin rating be pulled toward the field mean (SCR-20's m), and toward which mean (C)?

Claim: scoring orders venues by the shrunk rating s = (n*r + m*C) / (n + m) (SCR-20; config SCORING_SHRINK_M and
SCORING_SHRINK_C, used by the share step, SCR-19). r is the displayed rating, n the review count. m = sigma^2 / tau^2:
tau the spread of true ratings between venues, sigma the spread of one venue's reviews around its own mean. m is the
review count at which a venue's own rating and C weigh equally.

Method (scoring.md Notes "Rating-rule criteria", fits; the 92nd's ad hoc scripts recomputed):
  tau      from venues with TAU_MIN_N-TAU_MAX_N reviews: Var(r) - mean(sigma^2 / n) - rounding variance (0.1 steps).
           Many reviews make sampling noise small; above ~900 chains dominate (mean 4.19).
  sigma    at the most a 1-5 scale allows for a venue whose mean is C: sigma^2 = (C - 1)(5 - C) (Bhatia-Davis bound).
           Our pulls hold no individual reviews, so nothing measures sigma directly; the bound is wrong toward
           scepticism if wrong (more shrinkage).
  C        precision-weighted field mean, each venue weighted by n / (n + m), the weight the rule itself gives its
           own rating. C, sigma and tau depend on each other: iterated to a fixed point. Plain and n >= 10 means
           reported beside it.
Supporting fit, reported, not used for m:
  free     Var(r | n) = tau^2 + sigma^2 / n fitted across review-count bins (weighted least squares on bin variances).
           The 92nd found sigma above the scale's 2-star maximum: spread falls faster with n than sampling allows.
Dropped (user, 2026-10-24): the 92nd's snapshot fit, sigma from rating changes between the venue table
(2026-09-24/25) and the 2026-10-10 hours pull. Over 15 days the changes carry almost no sampling signal: of 442
venues with new reviews, 395 show the same displayed rating, 43 move by 0.1 (rounding-boundary flips, 30-60x what
sampling allows at their counts), 3 by 0.2-0.6; half have an expected sampling change below 0.003 stars. Fits with
independent rounding errors (sigma 0.68, biased down) or only pairs with expected change >= 0.1 (13 pairs) measure
nothing. The 92nd's 71 venues and sigma 1.65 could not be reproduced (its filter is unrecorded).

Rule (Claude's, written before the run): config takes m and C from the main method, m rounded to the nearest integer
(m is not known to better than that), C to 2 decimals. The free fit is evidence on how
spread falls with n, not a replacement for the ceiling.

Self-contained (CLAUDE.md D1): imports nothing from functions/, config.py or pipeline modules. No API.

Conclusion (run 2026-10-24, 18,213 rated venues, venue table 2026-09-25): C = 4.251 (plain mean 4.238, n >= 10 mean
4.250); tau = 0.399 from 5,176 venues with 300-900 reviews (mean 4.29); sigma at the ceiling 1.56; m = 15.3. Config
takes m = 15, C = 4.25. Anchors: subject 4.8 on 1,664 -> 4.795; 5.0 on 10 -> 4.55; 5.0 on 42 -> 4.80 (ties the
subject); 4.9 on 132 -> 4.83; 4.8 on 188 -> 4.76; no reviews -> 4.25. Free fit: sigma 1.52 (n >= 1), 2.34 (n >= 5),
2.76 (n >= 10): above 5 reviews it passes the scale's 2-star maximum, so the free fit can't stand in for the ceiling;
its m (9.5-42) is not used. Venues above 900 reviews: 2,287, mean 4.19 (chains). sigma remains a bound, not a
measurement (scoring.md Limitations).
"""
import datetime
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# --- paths ------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENUES_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"
NAME = "rating_shrinkage_m"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
SUMMARY_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_summary.csv"
BINS_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_count_bins.csv"
LOG_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"
FIGURE_PATH = IMG_DIR / f"{NAME}_{RUN_DATE}_variance_by_count.png"

# --- this diagnostic --------------------------------------------------------------------------------
SCALE_MIN, SCALE_MAX = 1.0, 5.0             # Google's star scale
RATING_STEP = 0.1                           # displayed resolution
ROUNDING_VAR = RATING_STEP ** 2 / 12        # variance added by rounding to RATING_STEP
TAU_MIN_N, TAU_MAX_N = 300, 900             # review counts the tau estimate uses
CHAIN_N = 900                               # above this, chains dominate (reported, not fitted)
MIN_N_FOR_MEAN = 10                         # the n >= 10 field mean reported beside C
FREE_FIT_MIN_N = [1, 5, 10]                 # lower count limits of the free fit (upper: CHAIN_N)
N_COUNT_BINS = 24                           # log-spaced count bins for the free fit and figure
FIXED_POINT_ITERATIONS = 50
FIXED_POINT_TOLERANCE = 1e-10
M_DECIMALS, C_DECIMALS = 0, 2               # rounding of the values config takes
# Anchors (scoring.md Notes): (label, displayed rating, review count); the subject is [subject] Brunswick East.
ANCHORS = [("subject", 4.8, 1664), ("5.0 on 10", 5.0, 10), ("5.0 on 42 (5.0 median)", 5.0, 42),
           ("4.9 on 132", 4.9, 132), ("4.8 on 188", 4.8, 188), ("no reviews", np.nan, 0)]


class Tee:
    def __init__(self):
        self.stdout, self.lines = sys.stdout, []

    def write(self, text):
        self.stdout.write(text)
        self.lines.append(text)

    def flush(self):
        self.stdout.flush()


def ceiling_sigma_sq(field_mean):
    """Largest variance of single reviews on the 1-5 scale for a venue whose mean is field_mean."""
    return (field_mean - SCALE_MIN) * (SCALE_MAX - field_mean)


def shrunk(rating, review_count, m, field_mean):
    rating = np.nan_to_num(np.asarray(rating, float), nan=field_mean)
    review_count = np.asarray(review_count, float)
    return (review_count * rating + m * field_mean) / (review_count + m)


def load_rated_venues():
    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "rating", "user_ratings_total"])
    is_rated = venues_df.rating.notna() & (venues_df.user_ratings_total > 0)
    return venues_df[is_rated].reset_index(drop=True)


def fit_main(rated_df):
    """Fixed point of C (precision-weighted mean), sigma^2 at the ceiling, tau^2 from the TAU_MIN_N-TAU_MAX_N group."""
    ratings, counts = rated_df.rating.to_numpy(), rated_df.user_ratings_total.to_numpy(float)
    is_tau_group = (counts >= TAU_MIN_N) & (counts <= TAU_MAX_N)
    field_mean = ratings.mean()
    for _ in range(FIXED_POINT_ITERATIONS):
        sigma_sq = ceiling_sigma_sq(field_mean)
        tau_sq = (ratings[is_tau_group].var(ddof=1) - np.mean(sigma_sq / counts[is_tau_group]) - ROUNDING_VAR)
        m = sigma_sq / tau_sq
        weights = counts / (counts + m)
        new_mean = np.sum(weights * ratings) / weights.sum()
        is_converged = abs(new_mean - field_mean) < FIXED_POINT_TOLERANCE
        field_mean = new_mean
        if is_converged:
            break
    return {"C": field_mean, "sigma_sq": sigma_sq, "tau_sq": tau_sq, "m": m, "n_tau_group": int(is_tau_group.sum()),
            "tau_group_mean": ratings[is_tau_group].mean()}


def count_bins(rated_df):
    counts = rated_df.user_ratings_total.to_numpy(float)
    edges = np.unique(np.round(np.geomspace(1, counts.max() + 1, N_COUNT_BINS + 1)))
    bin_index = np.digitize(counts, edges[1:-1])
    rows = []
    for index, group_df in rated_df.groupby(bin_index):
        if len(group_df) < 2:
            continue
        rows.append({"n_low": int(group_df.user_ratings_total.min()), "n_high": int(group_df.user_ratings_total.max()),
                     "venues": len(group_df), "mean_inv_n": np.mean(1 / group_df.user_ratings_total),
                     "mean_rating": group_df.rating.mean(), "var_rating": group_df.rating.var(ddof=1)})
    return pd.DataFrame(rows)


def fit_free(rated_df, min_n):
    """Weighted least squares of per-bin variance on mean 1/n, counts min_n..CHAIN_N."""
    in_range_df = rated_df[(rated_df.user_ratings_total >= min_n) & (rated_df.user_ratings_total <= CHAIN_N)]
    bins_df = count_bins(in_range_df)
    design = np.column_stack([np.ones(len(bins_df)), bins_df.mean_inv_n])
    sqrt_weights = np.sqrt(bins_df.venues.to_numpy(float))
    target = bins_df.var_rating.to_numpy() - ROUNDING_VAR
    (tau_sq, sigma_sq), *_ = np.linalg.lstsq(design * sqrt_weights[:, None], target * sqrt_weights, rcond=None)
    return {"min_n": min_n, "venues": len(in_range_df), "tau_sq": tau_sq, "sigma_sq": sigma_sq,
            "m": sigma_sq / tau_sq if tau_sq > 0 else np.nan}


def draw_figure(bins_df, main, free_fits):
    figure, axis = plt.subplots(figsize=(8, 5))
    axis.scatter(bins_df.mean_inv_n ** -1, bins_df.var_rating, s=np.sqrt(bins_df.venues) * 3, color="0.3",
                 label="venues in count bin (area ~ count)")
    n_grid = np.geomspace(1, CHAIN_N, 200)
    axis.plot(n_grid, main["tau_sq"] + main["sigma_sq"] / n_grid + ROUNDING_VAR, color="tab:blue",
              label=f"adopted: tau {np.sqrt(main['tau_sq']):.2f}, sigma at ceiling {np.sqrt(main['sigma_sq']):.2f}")
    for free in free_fits:
        axis.plot(n_grid, free["tau_sq"] + free["sigma_sq"] / n_grid + ROUNDING_VAR, linestyle="--",
                  label=f"free fit n >= {free['min_n']}: sigma {np.sqrt(max(free['sigma_sq'], 0)):.2f}")
    axis.axvspan(TAU_MIN_N, TAU_MAX_N, color="tab:blue", alpha=0.08, label="tau group")
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("review count n")
    axis.set_ylabel("variance of displayed rating (stars^2)")
    axis.set_title("Spread of ratings by review count, venue table 2026-09-25")
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(FIGURE_PATH, dpi=150)
    plt.close(figure)


def main():
    tee = Tee()
    sys.stdout = tee
    print(f"{NAME}, run {RUN_DATE}; venue table {VENUES_PATH.name}")
    rated_df = load_rated_venues()
    counts = rated_df.user_ratings_total
    print(f"rated venues: {len(rated_df):,} (review count median {counts.median():.0f}, max {counts.max():,})")

    fit = fit_main(rated_df)
    print("\nMain fit (fixed point):")
    print(f"  C (precision-weighted mean) {fit['C']:.4f}; plain mean {rated_df.rating.mean():.4f}; "
          f"n >= {MIN_N_FOR_MEAN} mean {rated_df.rating[counts >= MIN_N_FOR_MEAN].mean():.4f}")
    print(f"  tau group {TAU_MIN_N}-{TAU_MAX_N} reviews: {fit['n_tau_group']:,} venues, mean {fit['tau_group_mean']:.3f}")
    print(f"  tau {np.sqrt(fit['tau_sq']):.4f}; sigma at ceiling {np.sqrt(fit['sigma_sq']):.4f}; m {fit['m']:.2f}")
    chain_mean = rated_df.rating[counts > CHAIN_N].mean()
    print(f"  venues above {CHAIN_N} reviews: {int((counts > CHAIN_N).sum()):,}, mean {chain_mean:.3f}")
    config_m = round(fit["m"], M_DECIMALS)
    config_c = round(fit["C"], C_DECIMALS)
    print(f"  config takes m = {config_m:.0f}, C = {config_c:.2f} (rule in the docstring)")

    print("\nAnchors at config's m and C (s = shrunk rating, ordering only):")
    for label, rating, review_count in ANCHORS:
        value = shrunk([rating], [review_count], config_m, config_c)[0]
        print(f"  {label:<24} -> {value:.3f}")

    bins_df = count_bins(rated_df)
    bins_df.to_csv(BINS_PATH, index=False)
    free_fits = [fit_free(rated_df, min_n) for min_n in FREE_FIT_MIN_N]
    print(f"\nFree fit, Var(r | n) = tau^2 + sigma^2 / n over count bins, n <= {CHAIN_N} (scale maximum sigma 2):")
    for free in free_fits:
        sigma_text = f"{np.sqrt(free['sigma_sq']):.2f}" if free["sigma_sq"] > 0 else "negative"
        tau_text = f"{np.sqrt(free['tau_sq']):.3f}" if free["tau_sq"] > 0 else "negative"
        print(f"  n >= {free['min_n']:>2}: {free['venues']:,} venues, tau {tau_text}, sigma {sigma_text}, "
              f"m {free['m']:.1f}")

    draw_figure(bins_df, fit, free_fits)
    summary_rows = [{"quantity": "C", "value": fit["C"]}, {"quantity": "tau", "value": np.sqrt(fit["tau_sq"])},
                    {"quantity": "sigma_ceiling", "value": np.sqrt(fit["sigma_sq"])}, {"quantity": "m", "value": fit["m"]},
                    {"quantity": "config_m", "value": config_m}, {"quantity": "config_C", "value": config_c}]
    summary_rows += [{"quantity": f"free_sigma_n{free['min_n']}", "value": np.sqrt(max(free["sigma_sq"], 0))}
                     for free in free_fits]
    pd.DataFrame(summary_rows).to_csv(SUMMARY_PATH, index=False)
    print(f"\nsaved: {SUMMARY_PATH.name}, {BINS_PATH.name}, {FIGURE_PATH.name}")
    sys.stdout = tee.stdout
    LOG_PATH.write_text("".join(tee.lines), encoding="utf-8")


if __name__ == "__main__":
    main()
