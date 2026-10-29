"""Why does the Google regression under-predict dense trips: its paces, its routes, or departure time?

Context: compare_drive_models (2026-10-12) left the Google regression (pathing_calibration,
fit_google_regression) under-predicting level-15 trips by ~12% out-of-fold (density-share guard),
although it is fitted on Google's own path. Two candidate causes, both raised 2026-10-12:
  (a) route exploitation (Claude): routing on the fitted table finds paths cheaper than Google's path
      priced by the same table, and the gap is larger in dense areas (Q16, route-choice gap);
  (b) departure time (user): the regression is time-blind; dense areas may have harsher peaks, a
      shape a time-blind fit cannot follow, which could bias it by density.
Where the pipeline relies on it: DESIGN_pre_spine "Drive model selection" item 4 (first comparison),
the density-share guard's reading, and Q16. Training half only, 3,999 pairs; the test half is never
read. Reuses the 2026-10-12 regression run (per-fold parameters and out-of-fold routed predictions);
no routing, no API.

Notation, per pair:
  G   Google traffic-aware time (s), google_drive_duration_sec
  G0  Google static time, no traffic (s), static_duration_sec
  P   regression time on Google's matched path, out-of-fold parameters (s): matched length x pace +
      unmatched length x dummy pace + beta x signals (the fit's own prediction)
  R   regression time on its own routed path, out-of-fold (s), oof_predictions.csv
  e_P = log(P / G)   path error (what the paces get wrong)
  e_R = log(R / G)   routed error (what the comparison scored)
  gap = log(R / P) = e_R - e_P   routing gap (< 0: routing found a path cheaper than Google's)
  shares: Google polyline length share per density tier (0-5, 6-10, 11-14, 15), raster level per piece
  peak: departure Mon-Fri 07:00-09:59 or 16:00-18:59 local (every pair departs on a weekday)

Checks (rules written before the run):
1. Decomposition. Density-share regression (as the pipeline's guard: y on tier shares 6-10, 11-14,
   15 with 0-5 as reference, plus log G; effect = exp(coef) - 1; destination-hex bootstrap, 2,000
   draws, 95% CI) for y = e_R, e_P and gap. Since e_R = e_P + gap and OLS is linear, the effects add
   on the log scale.
   Rule: route exploitation is a cause if gap's level-15 CI lies below 0; it is the main cause if its
   log-scale coefficient is at least half of e_R's. Same for e_P (the paces).
2. Departure shape (user's hypothesis).
   2a. Do dense areas have harsher peaks? y = log(G / G0) on tier shares, peak, peak x each share,
       log G0. Rule: premise holds if the peak x level-15 coefficient's CI lies above 0.
   2b. Does a time-blind fit then misprice dense trips? e_P's density-share regression on peak and
       off-peak pairs separately. Reading: level-15 effect negative at peak and positive off-peak is the
       shape the user describes (one pace for both). Bias overall needs more: the effect over all
       pairs (check 1, e_P) with CI excluding 0.
   2c. Skew: on dense-heavy pairs (level-15 share >= 0.5), mean vs median of e_P. A time-blind,
       robust (soft_l1) fit sits near the median; a long peak tail puts the mean below it.
Descriptive: medians of e_P, e_R, gap by level-15 share band.

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1).

Conclusion (run 2026-10-12): routing is the main cause. Level-15 effects: e_R -12.2% (CI -15.9 to
-8.5) = e_P -3.8% (-7.2 to -0.2) + gap -8.7% (-11.1 to -6.1). 2a: premise holds; peak x level-15
share +0.065 on log(G/G0) (CI +0.017 to +0.116), and tiers 6-10 and 11-14 too (rural reference thin,
4% of length). 2b: e_P level-15 effect -8.5% at peak (1,247 pairs), -1.1% off-peak (CI includes 0).
2c: dense-heavy e_P mean -0.9%, median -1.9%, skew small: time-blindness adds spread, little bias.
"""

import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths ------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "-37.76870_144.97196"
LAYERS_SUFFIX = f"res2021_wrk2021_ven20260925_{SUBJECT}"
CALIBRATION_DIR = PROJECT_ROOT / "outputs" / "pathing_calibration"
PAIRS_PATH = CALIBRATION_DIR / SUBJECT / f"od_expanded_drive_enriched_{LAYERS_SUFFIX}.csv"
INPUTS_PATH = CALIBRATION_DIR / "fit" / SUBJECT / f"google_regression_inputs_{LAYERS_SUFFIX}.npz"
REGRESSION_RUN_DIR = CALIBRATION_DIR / "fit" / SUBJECT / "20261012" / "google_regression"
OOF_PATH = REGRESSION_RUN_DIR / "oof_predictions.csv"
PARAMS_FILE = "google_regression_fold{fold}_params.json"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "drive_regression_route_gap"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
PAIRS_OUT_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_pairs.csv"
SUMMARY_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_summary.json"
LOG_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"

# --- copied from the pipeline (config.py, pathing_calibration.py, 2026-10-12) -----------------------
TIERS = ((0, 5), (6, 10), (11, 14), (15, 15))
TIER_NAMES = ["0-5", "6-10", "11-14", "15"]
N_ROAD_CLASSES = 9
N_LEVELS = 16
PAIR_ID_COL = "pair_id"
FOLD_COL = "fold"
PREDICTED_COL = "predicted_s"
DEST_HEX_COL = "dest_hex_id"
GOOGLE_COL = "google_drive_duration_sec"
STATIC_COL = "static_duration_sec"
DAY_COL = "dep_day_name"
MINUTE_COL = "dep_min_of_day"

# --- rules ------------------------------------------------------------------------------------------
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
PEAK_WINDOWS_MIN = ((7 * 60, 10 * 60), (16 * 60, 19 * 60))   # local departure minute, [start, end)
DENSE_HEAVY_SHARE = 0.5
SHARE_BANDS = (0.0, 1e-9, 0.25, 0.5, 1.0 + 1e-9)             # level-15 share bands: 0, (0, .25), ...
SHARE_BAND_NAMES = ["0", "0-0.25", "0.25-0.5", "0.5-1"]
MAIN_CAUSE_FRACTION = 0.5
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261012
CI_PERCENTILES = (2.5, 97.5)


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


def tier_of_level():
    tier = np.empty(N_LEVELS, np.int64)
    for tier_no, (low, high) in enumerate(TIERS):
        tier[low:high + 1] = tier_no
    return tier


def path_prediction(theta, inputs, rows):
    """The regression's time on Google's matched path (pathing_calibration._regression_predict)."""
    n_tiers = len(TIERS)
    sizes = np.cumsum([N_ROAD_CLASSES, N_ROAD_CLASSES * n_tiers, N_ROAD_CLASSES * N_LEVELS, n_tiers])
    class_term, tier_dev, level_dev, log_dummy, log_beta = np.split(np.asarray(theta), sizes)
    log_pace = (class_term[:, None] + tier_dev.reshape(N_ROAD_CLASSES, n_tiers)[:, tier_of_level()]
                + level_dev.reshape(N_ROAD_CLASSES, N_LEVELS))
    return (inputs["cell_length_m"][rows] @ np.exp(log_pace).ravel()
            + inputs["unmatched_length_m"][rows] @ np.exp(log_dummy) + np.exp(log_beta[0]) * inputs["signals"][rows])


def bootstrap_rows(hex_ids, rng):
    """Row index sets, destination hexes resampled with replacement."""
    hex_ix = pd.factorize(hex_ids)[0]
    n_hex = hex_ix.max() + 1
    members = np.split(np.argsort(hex_ix, kind="stable"), np.cumsum(np.bincount(hex_ix, minlength=n_hex))[:-1])
    for _ in range(N_BOOTSTRAP):
        yield np.concatenate([members[h] for h in rng.integers(0, n_hex, n_hex)])


def ols_with_ci(y, design, hex_ids, columns):
    """OLS coefficients on the named design columns, with hex-bootstrap 95% CIs (log scale)."""
    point = np.linalg.lstsq(design, y, rcond=None)[0][columns]
    boot = [np.linalg.lstsq(design[rows], y[rows], rcond=None)[0][columns]
            for rows in bootstrap_rows(hex_ids, np.random.default_rng(BOOTSTRAP_SEED))]
    low, high = np.percentile(np.array(boot), CI_PERCENTILES, axis=0)
    return point, low, high


def share_design(df, extra=()):
    shares = df[[f"share_{name}" for name in TIER_NAMES[1:]]].to_numpy()
    return np.column_stack([np.ones(len(df)), shares, *extra])


def density_effects(df, y_col):
    """Density-share regression as the pipeline's guard; rows per tier: coef, effect, CI."""
    design = share_design(df, [np.log(df[GOOGLE_COL].to_numpy(float))])
    point, low, high = ols_with_ci(df[y_col].to_numpy(), design, df[DEST_HEX_COL].to_numpy(), slice(1, len(TIERS)))
    return pd.DataFrame(dict(y=y_col, tier=TIER_NAMES[1:], coef=point, coef_low=low, coef_high=high,
                             effect=np.expm1(point), effect_low=np.expm1(low), effect_high=np.expm1(high)))


def show(df):
    with pd.option_context("display.width", 200, "display.max_columns", None, "display.float_format", "{:+.4f}".format):
        print(df.to_string(index=False))


def load_pairs():
    oof_df = pd.read_csv(OOF_PATH)
    pairs_df = pd.read_csv(PAIRS_PATH, usecols=[PAIR_ID_COL, GOOGLE_COL, STATIC_COL, DAY_COL, MINUTE_COL])
    df = oof_df.merge(pairs_df.drop(columns=GOOGLE_COL), on=PAIR_ID_COL, how="left", validate="one_to_one")
    inputs = dict(np.load(INPUTS_PATH))
    row_of = pd.Series(np.arange(len(inputs[PAIR_ID_COL])), index=inputs[PAIR_ID_COL])
    rows = row_of.loc[df[PAIR_ID_COL]].to_numpy()
    path_s = np.empty(len(df))
    for fold in np.unique(df[FOLD_COL]):
        theta = json.loads((REGRESSION_RUN_DIR / PARAMS_FILE.format(fold=fold)).read_text())["theta"]
        is_fold = (df[FOLD_COL] == fold).to_numpy()
        path_s[is_fold] = path_prediction(theta, inputs, rows[is_fold])
    tier_m = inputs["tier_length_m"][rows]
    for tier_no, name in enumerate(TIER_NAMES):
        df[f"share_{name}"] = tier_m[:, tier_no] / tier_m.sum(axis=1)
    google_s = df[GOOGLE_COL].to_numpy(float)
    df["path_s"] = path_s
    df["e_P"] = np.log(path_s / google_s)
    df["e_R"] = np.log(df[PREDICTED_COL] / google_s)
    df["gap"] = df["e_R"] - df["e_P"]
    df["log_traffic"] = np.log(google_s / df[STATIC_COL])
    minute = df[MINUTE_COL].to_numpy()
    df["is_peak"] = df[DAY_COL].isin(WEEKDAYS).to_numpy() & np.any(
        [(minute >= start) & (minute < end) for start, end in PEAK_WINDOWS_MIN], axis=0)
    return df


def main():
    sys.stdout = tee = Tee()
    print(f"{NAME}  run {RUN_DATE}")
    df = load_pairs()
    print(f"{len(df):,} training pairs, {df['is_peak'].sum():,} at peak; "
          f"level-15 share mean {df['share_15'].mean():.3f}, reference tier 0-5 mean {df['share_0-5'].mean():.3f}")
    summary = dict(run_date=RUN_DATE, n_pairs=len(df), n_peak=int(df["is_peak"].sum()))

    print("\nDescriptive: medians by level-15 share band")
    df["band"] = pd.cut(df["share_15"], SHARE_BANDS, right=False, labels=SHARE_BAND_NAMES)
    band_df = df.groupby("band", observed=True).agg(n=("e_P", "size"), e_P=("e_P", "median"), e_R=("e_R", "median"),
                                                    gap=("gap", "median"), traffic=("log_traffic", "median")).reset_index()
    show(band_df)
    summary["bands"] = band_df.astype({"band": str}).to_dict("records")

    print("\nCheck 1: density-share effects (exp(coef) - 1), e_R = e_P + gap")
    effects_df = pd.concat([density_effects(df, y) for y in ("e_R", "e_P", "gap")], ignore_index=True)
    show(effects_df)
    dense = effects_df[effects_df["tier"] == "15"].set_index("y")
    verdict_1 = {}
    for y in ("gap", "e_P"):
        is_cause = bool(dense.loc[y, "coef_high"] < 0)
        is_main = is_cause and dense.loc[y, "coef"] <= MAIN_CAUSE_FRACTION * dense.loc["e_R", "coef"]
        verdict_1[y] = dict(is_cause=is_cause, is_main_cause=bool(is_main))
        print(f"  {y}: cause {is_cause}, main cause {bool(is_main)}")
    summary["check1"] = dict(effects=effects_df.to_dict("records"), verdict=verdict_1)

    print("\nCheck 2a: Google's own traffic factor log(G / G0); peak x share interactions")
    peak = df["is_peak"].to_numpy(float)
    shares = df[[f"share_{name}" for name in TIER_NAMES[1:]]].to_numpy()
    design = share_design(df, [peak, *(peak[:, None] * shares).T, np.log(df[STATIC_COL].to_numpy(float))])
    names = [f"share {t}" for t in TIER_NAMES[1:]] + ["peak"] + [f"peak x share {t}" for t in TIER_NAMES[1:]]
    point, low, high = ols_with_ci(df["log_traffic"].to_numpy(), design, df[DEST_HEX_COL].to_numpy(),
                                   slice(1, 1 + len(names)))
    traffic_df = pd.DataFrame(dict(term=names, coef=point, coef_low=low, coef_high=high))
    show(traffic_df)
    is_premise = bool(traffic_df.iloc[-1]["coef_low"] > 0)
    print(f"  premise (harsher peaks in level 15): {is_premise}")
    print(f"  median log(G/G0): peak {df.loc[df.is_peak, 'log_traffic'].median():+.4f}, "
          f"off-peak {df.loc[~df.is_peak, 'log_traffic'].median():+.4f}")
    summary["check2a"] = dict(terms=traffic_df.to_dict("records"), is_premise=is_premise)

    print("\nCheck 2b: e_P density-share effects, peak vs off-peak")
    split_df = pd.concat([density_effects(df[df.is_peak], "e_P").assign(pairs="peak"),
                          density_effects(df[~df.is_peak], "e_P").assign(pairs="off-peak")], ignore_index=True)
    show(split_df)
    summary["check2b"] = split_df.to_dict("records")

    print(f"\nCheck 2c: dense-heavy pairs (level-15 share >= {DENSE_HEAVY_SHARE}), e_P mean vs median")
    skew_rows = []
    for label, is_in in (("all", df["share_15"] >= DENSE_HEAVY_SHARE),
                         ("peak", (df["share_15"] >= DENSE_HEAVY_SHARE) & df.is_peak),
                         ("off-peak", (df["share_15"] >= DENSE_HEAVY_SHARE) & ~df.is_peak)):
        values = df.loc[is_in, "e_P"]
        skew_rows.append(dict(pairs=label, n=int(is_in.sum()), mean=values.mean(), median=values.median(),
                              skew=values.skew()))
    skew_df = pd.DataFrame(skew_rows)
    show(skew_df)
    summary["check2c"] = skew_df.to_dict("records")

    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.drop(columns="band").to_csv(PAIRS_OUT_PATH, index=False)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=1, default=float))
    sys.stdout = tee.stdout
    LOG_PATH.write_text("".join(tee.lines))
    print(f"saved {PAIRS_OUT_PATH.name}, {SUMMARY_PATH.name}, {LOG_PATH.name}")


if __name__ == "__main__":
    main()
