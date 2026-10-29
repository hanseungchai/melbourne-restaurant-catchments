"""Model error vs Google, conditional on the predicted time: is a nearest-neighbour residual draw calibrated out of fold?

Claim under test (concepts/reachability.md RCH-23 (b), RCH-13): Google's time given the model's predicted time can be
drawn from the residuals of fit pairs with similar predicted times, and the resulting intervals and band
probabilities (e.g. P(Google <= 20 | predicted 18.5)) are calibrated on pairs the residuals were not taken from.
Where the pipeline would rely on it: the uncertainty function planned in functions/ (RCH-23), which draws model
error per trip in the reachability pass; this diagnostic comes first (RCH-23: "built after its diagnostic").

Method (Claude's, written before the first run; not OK'd by the user):
  Residual r = log(google_s / model_s), model_s clipped below at MIN_MODEL_S. For a query predicted time p, take the
  K_NEIGHBOURS fit pairs nearest in log(model_s) and use their r: Google ~ p x exp(r). Interval = quantiles of that
  set; band probability = share of round(p x exp(r) / 60) <= cut (Google's minute rounded, as the band checks).
  Transit: departures before NIGHT_END_MIN (00-07 h) form their own stratum (transit_error_by_service.py: the night
  carries the long left tail; service level alone does not widen the error), the rest one stratum. Drive: one
  stratum (the selected model, 2tier; RCH-13's "by tier" is not defined per trip: a trip crosses density tiers).
  Baselines: pooled (all fit residuals, no conditioning) and ETA-binned (bins as transit_error_by_service.py).
  Folds: transit: fit on the seen pairs (training + old test) and check on the holdout, then the reverse (each
  set is weekday, release 20261009 / 20261016 mixed; holdout 20261016 only). Drive: the 2tier test half (4,001
  pairs, 2 draws) in 5 folds grouped by destination hex.
  Checks per fold, on the check set: coverage of the central 50 / 80 / 90% intervals; PIT spread (KS distance of
  the PIT values from uniform); for each cut (transit 10 / 20, drive 20), Brier score and calibration by predicted-
  probability decile (mean predicted vs observed share), only on pairs with p within CUT_WINDOW_MIN of the cut.
  Reading rule (pre-set): calibrated if every coverage is within COVERAGE_TOLERANCE of its nominal level and the
  near-cut Brier score is no worse than the ETA-binned baseline's; otherwise the failing check is named.

Conclusion (run 2026-10-22, 73rd, autonomous; facts, the reading is the user's): transit 12,575 pairs (night 439),
drive 2tier 8,001 rows (4,001 pairs x 2 draws). Transit, fit seen / check holdout: coverage 0.516 / 0.803 / 0.905
(50 / 80 / 90%), PIT KS 0.019; reverse 0.472 / 0.783 / 0.888, KS 0.031. Drive (5 folds): 50% coverage 0.45-0.53,
80% 0.78-0.82, 90% 0.88-0.91. Near-cut Brier: transit 10 0.086 / 0.075, 20 0.113 / 0.103; drive 20 0.147-0.184.
By the pre-set rule: transit check seen calibrated; holdout fails only on Brier 10 (0.0863 vs binned 0.0859);
drive folds 2 and 4 calibrated, 0 fails on Brier (0.1730 vs 0.1727), 1 and 3 on 50% coverage (0.531, 0.453: just
outside 0.03; fold-to-fold spread grouped by destination hex). KNN, binned and pooled are within ~0.005 of each other
everywhere: on the log-ratio scale the residual distribution barely depends on the predicted time inside the data,
so ETA conditioning adds little; calibration deciles track the diagonal (largest gap drive 0.6-0.7: 0.65 vs 0.57).
Worked examples (all pairs as fit): transit predicted 18.5 min -> P(Google <= 20) 0.82; 20.0 -> 0.69; 21.5 -> 0.12;
drive 18.5 -> 0.68, 20.0 -> 0.52, 21.5 -> 0.35 (drive error wider: 10-90% at 20 min 17.1-25.2 vs transit 18.8-23.7).
----

Inputs (read only): transit_holdout_score's per-pair results (frozen model; seen and holdout), the drive test-half
predictions (outputs/pathing_calibration/fit/<subject>/20261012/test/test_predictions.csv). Self-contained
(CLAUDE.md D1). No API calls. Usage: `python trip_error_conditional.py`.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
NAME = "trip_error_conditional"
SCORE_NAME = "transit_holdout_score"
SUBJECT = "-37.76870_144.97196"
DRIVE_TEST_PATH = (PROJECT_ROOT / "outputs" / "pathing_calibration" / "fit" / SUBJECT / "20261012" / "test"
                   / "test_predictions.csv")
DRIVE_MODEL = "2tier"                          # DRV-1

# --- method ----------------------------------------------------------------------------------------
SECONDS_PER_MIN = 60
MIN_MODEL_S = 30
K_NEIGHBOURS = 400
NIGHT_END_MIN = 7 * 60                         # transit night stratum: departures before 07:00
ETA_EDGES_MIN = [0, 5, 10, 15, 20, 25, 30, 45, np.inf]
TRANSIT_CUTS_MIN = [10, 20]                    # bands 1-2 (SCR-1)
DRIVE_CUTS_MIN = [20]                          # band 3 (config DRIVE_BAND_DURATION_MIN)
CUT_WINDOW_MIN = 5                             # near-cut pairs: |p - cut| <= this
INTERVAL_LEVELS = [0.5, 0.8, 0.9]
COVERAGE_TOLERANCE = 0.03
N_DECILES = 10
N_DRIVE_FOLDS = 5
FOLD_SEED = 20261022


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def newest(pattern):
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return saved[-1] if saved else None


# --- data ------------------------------------------------------------------------------------------
def transit_pairs():
    frames = {"seen": pd.read_csv(newest(f"{SCORE_NAME}_2*_seen_results.csv")),
              "holdout": pd.read_csv(newest(f"{SCORE_NAME}_2*_holdout_results.csv"))}
    rows = []
    for fold, df in frames.items():
        df = df[df.is_scored.astype(bool) & np.isfinite(df.model_s)]
        rows.append(pd.DataFrame({"fold": fold, "model_s": df.model_s.clip(lower=MIN_MODEL_S), "google_s": df.default_s,
                                  "stratum": np.where(df.dep_min_of_day < NIGHT_END_MIN, "night", "day")}))
    return pd.concat(rows, ignore_index=True)


def drive_pairs():
    df = pd.read_csv(DRIVE_TEST_PATH)
    df = df[df.model == DRIVE_MODEL]
    hexes = df.dest_hex_id.unique()
    fold_of = dict(zip(np.random.default_rng(FOLD_SEED).permutation(hexes), np.arange(len(hexes)) % N_DRIVE_FOLDS))
    return pd.DataFrame({"fold": df.dest_hex_id.map(fold_of).to_numpy(), "model_s": df.predicted_s.clip(lower=MIN_MODEL_S).to_numpy(),
                         "google_s": df.google_drive_duration_sec.to_numpy(), "stratum": "all"})


# --- conditional residuals ---------------------------------------------------------------------------
def neighbour_residuals(fit_df, query_s, method):
    """Per query, the residual set r = log(google / model) used to draw Google's time; rows = queries."""
    fit_x = np.log(fit_df.model_s.to_numpy())
    residuals = np.log(fit_df.google_s.to_numpy() / fit_df.model_s.to_numpy())
    if method == "pooled":
        return np.broadcast_to(residuals, (len(query_s), len(residuals)))
    if method == "binned":
        fit_bin = np.digitize(fit_df.model_s.to_numpy() / SECONDS_PER_MIN, ETA_EDGES_MIN)
        query_bin = np.digitize(np.asarray(query_s) / SECONDS_PER_MIN, ETA_EDGES_MIN)
        return [residuals[fit_bin == b] if (fit_bin == b).any() else residuals for b in query_bin]
    order = np.argsort(fit_x)
    sorted_x, sorted_r = fit_x[order], residuals[order]
    k = min(K_NEIGHBOURS, len(sorted_x))
    rows = []
    for x in np.log(np.asarray(query_s)):
        centre = np.searchsorted(sorted_x, x)
        low, high = max(0, centre - k), min(len(sorted_x), centre + k)
        window = np.arange(low, high)
        nearest = window[np.argsort(np.abs(sorted_x[window] - x), kind="stable")[:k]]
        rows.append(sorted_r[nearest])
    return rows


def evaluate(fit_df, check_df, cuts_min, method):
    rows_r = []
    index = []
    for stratum, check_part in check_df.groupby("stratum"):
        fit_part = fit_df[fit_df.stratum == stratum]
        if len(fit_part) < K_NEIGHBOURS:
            fit_part = fit_df
        rows_r += list(neighbour_residuals(fit_part, check_part.model_s.to_numpy(), method))
        index += list(check_part.index)
    check_df = check_df.loc[index]
    model_s, google_s = check_df.model_s.to_numpy(), check_df.google_s.to_numpy()
    observed_r = np.log(google_s / model_s)
    pit = np.array([(r < o).mean() + 0.5 * (r == o).mean() for r, o in zip(rows_r, observed_r)])
    result = {"n": len(check_df)}
    for level in INTERVAL_LEVELS:
        result[f"cover_{level:.0%}"] = ((pit >= (1 - level) / 2) & (pit <= 1 - (1 - level) / 2)).mean()
    sorted_pit = np.sort(pit)
    uniform = np.arange(1, len(pit) + 1) / len(pit)
    result["pit_ks"] = np.max(np.abs(sorted_pit - uniform))
    calibration = []
    for cut in cuts_min:
        probability = np.array([(np.round(s * np.exp(r) / SECONDS_PER_MIN) <= cut).mean() for s, r in zip(model_s, rows_r)])
        is_below = np.round(google_s / SECONDS_PER_MIN) <= cut
        is_near = np.abs(model_s / SECONDS_PER_MIN - cut) <= CUT_WINDOW_MIN
        result[f"brier_{cut}"] = np.mean((probability[is_near] - is_below[is_near]) ** 2)
        result[f"n_near_{cut}"] = int(is_near.sum())
        deciles = pd.qcut(probability[is_near], N_DECILES, duplicates="drop")
        calibration.append(pd.DataFrame({"cut": cut, "p": probability[is_near], "y": is_below[is_near], "decile": deciles})
                           .groupby("decile", observed=True).agg(predicted=("p", "mean"), observed=("y", "mean"), n=("y", "size"))
                           .reset_index().assign(cut=cut))
    return result, pd.concat(calibration, ignore_index=True)


def run_mode(mode, pairs_df, cuts_min, folds):
    rows, calibrations = [], []
    for check_fold in folds:
        fit_df, check_df = pairs_df[pairs_df.fold != check_fold], pairs_df[pairs_df.fold == check_fold]
        for method in ["knn", "binned", "pooled"]:
            result, calibration = evaluate(fit_df, check_df, cuts_min, method)
            rows.append({"mode": mode, "check": check_fold, "method": method, **result})
            calibrations.append(calibration.assign(mode=mode, check=check_fold, method=method))
    return pd.DataFrame(rows), pd.concat(calibrations, ignore_index=True)


def verdicts(results_df, cuts_min):
    lines = []
    for check, group in results_df.groupby("check"):
        knn, binned = group[group.method == "knn"].iloc[0], group[group.method == "binned"].iloc[0]
        failing = [f"cover {level:.0%} {knn[f'cover_{level:.0%}']:.3f}" for level in INTERVAL_LEVELS
                   if abs(knn[f"cover_{level:.0%}"] - level) > COVERAGE_TOLERANCE]
        failing += [f"Brier {cut} {knn[f'brier_{cut}']:.4f} > binned {binned[f'brier_{cut}']:.4f}" for cut in cuts_min
                    if knn[f"brier_{cut}"] > binned[f"brier_{cut}"]]
        lines.append(f"  check {check}: {'calibrated' if not failing else 'NOT: ' + '; '.join(failing)}")
    return lines


def main():
    tag = run_date()
    transit_df, drive_df = transit_pairs(), drive_pairs()
    transit_results, transit_cal = run_mode("transit", transit_df, TRANSIT_CUTS_MIN, ["holdout", "seen"])
    drive_results, drive_cal = run_mode("drive", drive_df, DRIVE_CUTS_MIN, list(range(N_DRIVE_FOLDS)))
    results_df = pd.concat([transit_results, drive_results], ignore_index=True)
    calibration_df = pd.concat([transit_cal, drive_cal], ignore_index=True)
    results_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_results.csv", index=False)
    calibration_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_calibration.csv", index=False)
    fmt = lambda x: f"{x:.3f}"  # noqa: E731
    lines = [f"{NAME} {tag}: K {K_NEIGHBOURS} nearest in log(predicted); transit {len(transit_df)} pairs "
             f"(night {int((transit_df.stratum == 'night').sum())}), drive {DRIVE_MODEL} {len(drive_df)} pairs "
             f"in {N_DRIVE_FOLDS} folds by destination hex",
             "", "transit (fit on the other set, check on the named one):",
             transit_results.dropna(axis=1, how="all").to_string(index=False, float_format=fmt),
             "rule (knn):", *verdicts(transit_results, TRANSIT_CUTS_MIN),
             "", "drive (fit on 4 folds, check on the named one):",
             drive_results.dropna(axis=1, how="all").to_string(index=False, float_format=fmt),
             "rule (knn):", *verdicts(drive_results, DRIVE_CUTS_MIN),
             "", "near-cut calibration, knn (predicted vs observed share below the cut, by decile, folds pooled):"]
    knn_cal = calibration_df[calibration_df.method == "knn"]
    pooled_cal = knn_cal.assign(weight=knn_cal.n * knn_cal.predicted, hits=knn_cal.n * knn_cal.observed)
    pooled_cal["band"] = pd.cut(pooled_cal.predicted, np.linspace(0, 1, N_DECILES + 1), include_lowest=True)
    table = pooled_cal.groupby(["mode", "cut", "band"], observed=True).agg(n=("n", "sum"), w=("weight", "sum"), h=("hits", "sum"))
    table["predicted"], table["observed"] = table.w / table.n, table.h / table.n
    lines.append(table[["n", "predicted", "observed"]].to_string(float_format=fmt))
    examples = []
    for mode, pairs_df, cuts in (("transit", transit_df[transit_df.stratum == "day"], TRANSIT_CUTS_MIN),
                                 ("drive", drive_df, DRIVE_CUTS_MIN)):
        for cut in cuts:
            for offset in (-3, -1.5, 0, 1.5, 3):
                query_s = (cut + offset) * SECONDS_PER_MIN
                r = neighbour_residuals(pairs_df, [query_s], "knn")[0]
                draws = query_s * np.exp(r) / SECONDS_PER_MIN
                examples.append(f"  {mode} predicted {cut + offset:.1f} min: P(Google <= {cut}) "
                                f"{(np.round(draws) <= cut).mean():.2f}; Google 10/50/90% "
                                f"{np.quantile(draws, 0.1):.1f} / {np.quantile(draws, 0.5):.1f} / {np.quantile(draws, 0.9):.1f}")
    lines += ["", "worked examples (all pairs as fit; transit day stratum):", *examples]
    figure(calibration_df, tag)
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)


def figure(calibration_df, tag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    panels = calibration_df[["mode", "cut"]].drop_duplicates().to_numpy()
    fig, axes = plt.subplots(1, len(panels), figsize=(4.5 * len(panels), 4.2))
    for ax, (mode, cut) in zip(np.atleast_1d(axes), panels):
        for method in ["knn", "binned", "pooled"]:
            part = calibration_df[(calibration_df["mode"] == mode) & (calibration_df.cut == cut) & (calibration_df.method == method)]
            ax.plot(part.predicted, part.observed, "o", ms=3, alpha=0.7, label=method)
        ax.plot([0, 1], [0, 1], color="grey", lw=0.8)
        ax.set_title(f"{mode}, cut {cut} min (|p - cut| <= {CUT_WINDOW_MIN})")
        ax.set_xlabel("predicted P(Google <= cut)")
        ax.set_ylabel("observed share")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(DIAGNOSTIC_IMG_DIR / f"{NAME}_{tag}_calibration.png", dpi=110)


if __name__ == "__main__":
    main()
