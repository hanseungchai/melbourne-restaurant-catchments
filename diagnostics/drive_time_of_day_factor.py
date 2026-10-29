"""Does a time-of-day scalar on the time-blind drive model earn its place?

Context (user, 2026-10-12): the drive model stays time-blind (DESIGN_pre_spine "Rejected": departure-time-aware
reachability, Oct 1), fitted on departures drawn from the pooled opening-hours histogram, so every
venue gets typical business-hours traffic. Venues trading at atypical hours (e.g. 1 a.m.) would be
mispriced. Proposed fix, no rerouting: per venue, scale drive time by a factor from its own trading
hours. Peaks are harsher in denser areas (drive_regression_route_gap, check 2a), so the factor may
need a density term. This diagnostic decides which version, if any.
Where the pipeline would rely on it: the reachability pass (planned step; DESIGN_pre_spine "Drive model").
Training half only (3,999 pairs), 2tier out-of-fold predictions of the 2026-10-11 run (edge set
"all"); the test half is never read. No routing, no API.

Notation, per pair:
  G     Google traffic-aware time (s), google_drive_duration_sec
  pred  2tier out-of-fold prediction (s)
  e     log(pred / G), the model's error
  s     level-15 share of the 2tier route's blind time: time_g1_s / (time_g0_s + time_g1_s); from the
        model's own route, as the reachability pass would have it
  band  departure band, local time: night 00-07, am_peak 07-10, midday 10-16, pm_peak 16-19,
        evening 19-24 (every pair departs on a weekday)
Corrections, each fitted out-of-fold on 2tier's folds (fit on four folds, apply to the fifth; soft_l1,
scale 0.1, as the drive fit), applied as pred x exp(-f):
  none       f = 0
  band       f = a_band                    (5 parameters)
  band_dense f = a_band + b_band x s       (10 parameters)

Checks (rules written before the run):
1. Descriptive: per band, n, mean e with a destination-hex bootstrap 95% CI (2,000 draws); within
   band, OLS slope of e on s with CI.
2. Out-of-fold, against none: mean soft_l1 loss difference and accuracy difference at the 20-min cut,
   paired hex-bootstrap 95% CIs; pairs whose side of the cut changes.
   Rule: band is adopted if its loss difference vs none has a CI below 0; otherwise skip the scalar.
   band_dense is adopted instead if, in addition, its loss difference vs band has a CI below 0.
   Accuracy and flips are reported, not used (the scalar's purpose is per-venue hours, which this
   pooled sample cannot score directly).

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1).

Conclusion (run 2026-10-12): verdict band. 2tier's error by band: night +21% (CI +18 to +24, 181
pairs), evening +13%, am_peak -7%, midday -5%, pm_peak -8%. Band correction out-of-fold: loss -0.0036
(CI -0.0040 to -0.0033), accuracy +1.55 pp (+0.91 to +2.20), 176 pairs flip. The density term adds
nothing beyond band (loss difference 0.0000, CI -0.0001 to +0.0001); within-band slopes on s are ~0
except night (+0.15, CI +0.02 to +0.27). Note: these errors are at the sampled departure; per venue,
the factor is taken relative to the pooled hours the model was fitted on.
"""

import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

# --- paths ------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "-37.76870_144.97196"
LAYERS_SUFFIX = f"res2021_wrk2021_ven20260925_{SUBJECT}"
CALIBRATION_DIR = PROJECT_ROOT / "outputs" / "pathing_calibration"
PAIRS_PATH = CALIBRATION_DIR / SUBJECT / f"od_expanded_drive_enriched_{LAYERS_SUFFIX}.csv"
FIT_RUN_DIR = CALIBRATION_DIR / "fit" / SUBJECT / "20261011" / "all"
MODEL = "2tier"
OOF_PATH = FIT_RUN_DIR / "oof_predictions.csv"
FOLD_ROUTES_FILE = MODEL + "_fold{fold}_oof.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "drive_time_of_day_factor"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
PAIRS_OUT_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_pairs.csv"
SUMMARY_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_summary.json"
LOG_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"

# --- copied from the pipeline (config.py, pathing_calibration.py, 2026-10-12) -----------------------
PAIR_ID_COL = "pair_id"
FOLD_COL = "fold"
MODEL_COL = "model"
PREDICTED_COL = "predicted_s"
DEST_HEX_COL = "dest_hex_id"
GOOGLE_COL = "google_drive_duration_sec"
MINUTE_COL = "dep_min_of_day"
UNSCALED_COL = "time_g0_s"
DENSE_COL = "time_g1_s"
LOSS_SCALE = 0.1
CUT_S = 20 * 60

# --- rules ------------------------------------------------------------------------------------------
BANDS_MIN = {"night": (0, 7 * 60), "am_peak": (7 * 60, 10 * 60), "midday": (10 * 60, 16 * 60),
             "pm_peak": (16 * 60, 19 * 60), "evening": (19 * 60, 24 * 60)}
VARIANTS = ("none", "band", "band_dense")
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261012
CI_PERCENTILES = (2.5, 97.5)
PCT = 100.0


class Tee:
    """Print to the console and keep every line for the run log."""

    def __init__(self):
        self.stdout = sys.stdout
        self.lines = []

    def write(self, text):
        self.stdout.write(text)
        self.lines.append(text)

    def flush(self):
        self.stdout.flush()


def soft_l1(residual):
    return 2 * LOSS_SCALE ** 2 * (np.sqrt(1 + (residual / LOSS_SCALE) ** 2) - 1)


def bootstrap_draws(hex_ids):
    """Row index sets, destination hexes resampled with replacement."""
    hex_ix = pd.factorize(hex_ids)[0]
    n_hex = hex_ix.max() + 1
    members = np.split(np.argsort(hex_ix, kind="stable"), np.cumsum(np.bincount(hex_ix, minlength=n_hex))[:-1])
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    return [np.concatenate([members[h] for h in rng.integers(0, n_hex, n_hex)]) for _ in range(N_BOOTSTRAP)]


def with_ci(statistic, draws):
    """statistic(rows) on all rows, and its bootstrap 95% CI."""
    boot = [statistic(rows) for rows in draws]
    low, high = np.percentile(boot, CI_PERCENTILES)
    return statistic(slice(None)), low, high


def design(df, variant):
    """Columns of f: one indicator per band, then (band_dense) indicator x s."""
    indicators = np.column_stack([(df["band"] == band).to_numpy(float) for band in BANDS_MIN])
    if variant == "band":
        return indicators
    return np.column_stack([indicators, indicators * df["s"].to_numpy()[:, None]])


def fit_f(columns, error):
    """Coefficients of f by soft_l1 on e - f."""
    result = least_squares(lambda c: error - columns @ c, np.zeros(columns.shape[1]), loss="soft_l1",
                           f_scale=LOSS_SCALE)
    return result.x


def load_pairs():
    oof_df = pd.read_csv(OOF_PATH)
    oof_df = oof_df[oof_df[MODEL_COL] == MODEL]
    routes_df = pd.concat([pd.read_csv(FIT_RUN_DIR / FOLD_ROUTES_FILE.format(fold=fold),
                                       usecols=[PAIR_ID_COL, UNSCALED_COL, DENSE_COL])
                           for fold in sorted(oof_df[FOLD_COL].unique())])
    pairs_df = pd.read_csv(PAIRS_PATH, usecols=[PAIR_ID_COL, MINUTE_COL])
    df = (oof_df.merge(routes_df, on=PAIR_ID_COL, how="left", validate="one_to_one")
          .merge(pairs_df, on=PAIR_ID_COL, how="left", validate="one_to_one"))
    df["s"] = df[DENSE_COL] / (df[UNSCALED_COL] + df[DENSE_COL])
    df["e"] = np.log(df[PREDICTED_COL] / df[GOOGLE_COL])
    df["band"] = None
    for band, (start, end) in BANDS_MIN.items():
        df.loc[(df[MINUTE_COL] >= start) & (df[MINUTE_COL] < end), "band"] = band
    assert df["band"].notna().all() and df["s"].notna().all()
    return df.reset_index(drop=True)


def show(df):
    with pd.option_context("display.width", 200, "display.max_columns", None, "display.float_format", "{:+.4f}".format):
        print(df.to_string(index=False))


def main():
    sys.stdout = tee = Tee()
    print(f"{NAME}  run {RUN_DATE}")
    df = load_pairs()
    print(f"{len(df):,} training pairs ({MODEL}, out-of-fold); mean s {df['s'].mean():.3f}")
    draws = bootstrap_draws(df[DEST_HEX_COL].to_numpy())
    summary = dict(run_date=RUN_DATE, n_pairs=len(df))

    print("\nCheck 1: model error e = log(pred / G) by departure band (% = exp(e) - 1)")
    e, s = df["e"].to_numpy(), df["s"].to_numpy()
    rows = []
    for band in BANDS_MIN:
        is_band = (df["band"] == band).to_numpy()
        mean, low, high = with_ci(lambda r: e[r][is_band[r]].mean(), draws)

        def slope(r):
            x, y = s[r][is_band[r]], e[r][is_band[r]]
            return np.polyfit(x, y, 1)[0]

        b, b_low, b_high = with_ci(slope, draws)
        rows.append(dict(band=band, n=int(is_band.sum()), mean_pct=np.expm1(mean) * PCT,
                         ci_low_pct=np.expm1(low) * PCT, ci_high_pct=np.expm1(high) * PCT,
                         slope_s=b, slope_low=b_low, slope_high=b_high))
    band_df = pd.DataFrame(rows)
    show(band_df)
    summary["check1"] = band_df.to_dict("records")

    print("\nCheck 2: out-of-fold corrections, pred x exp(-f)")
    folds = df[FOLD_COL].to_numpy()
    corrected = {"none": df[PREDICTED_COL].to_numpy(float)}
    coefs = {}
    for variant in VARIANTS[1:]:
        columns = design(df, variant)
        f = np.empty(len(df))
        for fold in np.unique(folds):
            is_out = folds == fold
            f[is_out] = columns[is_out] @ fit_f(columns[~is_out], e[~is_out])
        corrected[variant] = corrected["none"] * np.exp(-f)
        coefs[variant] = fit_f(columns, e).tolist()
    google_s = df[GOOGLE_COL].to_numpy(float)
    loss = {v: soft_l1(np.log(p / google_s)) for v, p in corrected.items()}
    correct = {v: ((p <= CUT_S) == (google_s <= CUT_S)).astype(float) for v, p in corrected.items()}
    records = []
    for variant, base in (("band", "none"), ("band_dense", "none"), ("band_dense", "band")):
        loss_diff = loss[variant] - loss[base]
        acc_diff = correct[variant] - correct[base]
        d_loss, l_low, l_high = with_ci(lambda r: loss_diff[r].mean(), draws)
        d_acc, a_low, a_high = with_ci(lambda r: acc_diff[r].mean(), draws)
        flips = int(((corrected[variant] <= CUT_S) != (corrected[base] <= CUT_S)).sum())
        records.append(dict(variant=variant, against=base, loss_diff=d_loss, loss_low=l_low, loss_high=l_high,
                            acc_diff_pct=d_acc * PCT, acc_low_pct=a_low * PCT, acc_high_pct=a_high * PCT,
                            flips=flips))
    compare_df = pd.DataFrame(records)
    show(compare_df)
    for variant in VARIANTS:
        print(f"  {variant}: accuracy {correct[variant].mean():.4f}, mean loss {loss[variant].mean():.5f}")
    is_band = bool(compare_df.iloc[0]["loss_high"] < 0)
    is_dense = is_band and bool(compare_df.iloc[2]["loss_high"] < 0)
    verdict = "band_dense" if is_dense else "band" if is_band else "none"
    print(f"  verdict: {verdict}")
    print("  all-training coefficients (log scale; band_dense: a per band, then b per band):")
    for variant, values in coefs.items():
        print(f"    {variant}: " + ", ".join(f"{v:+.4f}" for v in values))
    summary["check2"] = dict(comparisons=compare_df.to_dict("records"), coefficients=coefs, verdict=verdict,
                             bands=list(BANDS_MIN))

    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.assign(**{f"pred_{v}": p for v, p in corrected.items()}).to_csv(PAIRS_OUT_PATH, index=False)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=1, default=float))
    sys.stdout = tee.stdout
    LOG_PATH.write_text("".join(tee.lines))
    print(f"saved {PAIRS_OUT_PATH.name}, {SUMMARY_PATH.name}, {LOG_PATH.name}")


if __name__ == "__main__":
    main()
