"""How heavily does Google weigh a walking minute against an arrival minute when it picks its default transit route?

Claim under test (user's choice, 2026-10-21, 62nd; rule written by Claude and OK'd by the user before any result):
Google's default route is the least-cost route among those it returns, with cost
    C(r) = A(r) + (w - 1) * T(r)
where A = arrival_from_request_s (s, arrival minus the requested departure, home wait included), T = walk time (s,
Google's listed walk_m at WALK_SPEED_KMH), w = walk weight (dimensionless; w = 1 is plain earliest arrival). Where the
pipeline would rely on it: preference fitting under TRN-16 (1) revised (Google is the fit target; how a weight is
applied is decided after this estimate). Earlier evidence: concepts/transit.md T7 (h) (`transit_default_route.py`,
first training half, w ~2 with penalties); the 61st's railtram bound (~1.6, descriptive).

Revealed preference: Google picking d over r gives C(d) <= C(r), i.e. (w - 1)(T_d - T_r) <= A_r - A_d. d later but
walking less gives a lower bound on w; d earlier but walking more an upper bound; d later and walking at least as
much fits no w ("not walk").

Method (rule fixed before results): pairs = training half + second batch + top-up with 2+ Google routes; every route
Google returned counts (in scope or not, walk-only included). Hit share at w = mean over pairs of 1 / n_tied when the
default is among the least-cost routes, else 0. w on W_GRID (1 to 4 by 0.05). Estimate = the w with the best share;
range = every w within RANGE_TOLERANCE of it; bootstrap over pairs (N_BOOTSTRAP draws) of the best w.
Reading rule:
  R1 Google has a walk weight if the best share beats w = 1 by >= MIN_GAIN and the bootstrap interval excludes 1.
  R2 Stable if each set's own bootstrap interval covers the pooled estimate; else reported unstable, not used.
  Report only: ceiling (share of pairs any single w >= 1 can explain); w with a transfer penalty tau (cost adds
  tau * max(boardings - 1, 0)); agreement with the railtram bound (~1.6).

Conclusion (run 2026-10-21; 3,340 pairs: train 1,209, second 1,939, top-up 192): earliest arrival (w = 1) picks the
default on 0.720; best w 1.70 picks it on 0.853 (gain +0.133); within 1 pp 1.55-2.05; bootstrap 1.55 / 1.75 / 1.95.
R1 YES (Google has a walk weight). R2 YES (stable): train 1.70 (1.55-2.00), second 1.80 (1.55-2.00), top-up 1.85
(1.30-1.95). Report only: a single w >= 1 can explain 0.962 of pairs at most (0.038 fit no w); 648 pairs need w > 1
(lower bounds median 1.40), 1,548 cap it (upper bounds median 3.78). A transfer penalty adds most: tau 450 s with
w 1.95 picks 0.942 (as T7 (h): w 2.0, tau 480 s). Railtram's ~1.6 inside the interval (share 0.850). Reading
(Claude's): Google's default behaves as if a walking minute costs ~1.7-1.8 arrival minutes, and a transfer ~7.5 min.

Inputs (read only): the transit split and Google route tables in outputs/transit_validation/ (test-half rows of the
first table are dropped by the split before any value is used). Self-contained: imports nothing from functions/ or
config.py (CLAUDE.md D1). No paid API calls, no r5py. Stored answers only; results carry the run date; a same-day
rerun replaces that day's results.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
GOOGLE_ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",   # holds the test half too
                       "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                       "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_walk_weight"

# --- values copied from config.py and the record ---------------------------------------------------
TRAIN_HALF = "train"
WALK_SPEED_KMH = 4.143                         # DESIGN Q24 (2), final (user, 59th)
S_PER_HOUR = 3600
M_PER_KM = 1000
RAILTRAM_BOUND_W = 1.6                         # 61st, transit_leg_error.py railtram (descriptive)

# --- grid and reading rule -------------------------------------------------------------------------
W_GRID = np.round(np.arange(1.0, 4.0 + 1e-9, 0.05), 2)
TAU_GRID_S = np.arange(0, 900 + 1, 30)         # report-only transfer penalty, s per transfer
RANGE_TOLERANCE = 0.01                         # w within 1 percentage point of the best share
MIN_GAIN = 0.05                                # R1: best share minus share at w = 1
N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 20261021
BOOTSTRAP_QUANTILES = [0.025, 0.5, 0.975]
TIE_TOLERANCE_S = 1e-6

# --- columns ---------------------------------------------------------------------------------------
DRAW_NO_COL = "draw_no"
SET_COL = "set"
ARRIVAL_COL = "arrival_from_request_s"
WALK_M_COL = "walk_m"
BOARDINGS_COL = "n_transit_steps"
DEFAULT_COL = "is_default"
HALF_COL = "half"


def load_routes():
    """Every Google route of every training pair with 2+ routes, keyed by (set, draw_no)."""
    split_df = pd.read_csv(SPLIT_PATH)
    train_draws = set(split_df.loc[split_df[HALF_COL] == TRAIN_HALF, DRAW_NO_COL])
    frames = []
    for set_name, path in GOOGLE_ROUTES_PATHS.items():
        routes_df = pd.read_csv(path)
        if set_name == "train":
            routes_df = routes_df[routes_df[DRAW_NO_COL].isin(train_draws)]
        frames.append(routes_df.assign(**{SET_COL: set_name}))
    routes_df = pd.concat(frames, ignore_index=True)
    n_routes = routes_df.groupby([SET_COL, DRAW_NO_COL])[DRAW_NO_COL].transform("size")
    routes_df = routes_df[n_routes >= 2].copy()
    routes_df["walk_s"] = routes_df[WALK_M_COL] / (WALK_SPEED_KMH * M_PER_KM / S_PER_HOUR)
    routes_df["transfers"] = (routes_df[BOARDINGS_COL] - 1).clip(lower=0)
    return routes_df


def pair_arrays(routes_df):
    """Per pair: arrival, walk time, transfers and default flag as lists of arrays."""
    pairs = []
    for (set_name, _), pair_df in routes_df.groupby([SET_COL, DRAW_NO_COL], sort=True):
        pairs.append({"set": set_name,
                      "arrival": pair_df[ARRIVAL_COL].to_numpy(float),
                      "walk": pair_df["walk_s"].to_numpy(float),
                      "transfers": pair_df["transfers"].to_numpy(float),
                      "default": pair_df[DEFAULT_COL].to_numpy(bool)})
    return pairs


def hit(cost, is_default):
    """1 / n_tied if the default is among the least-cost routes, else 0."""
    is_min = cost <= cost.min() + TIE_TOLERANCE_S
    return 1.0 / is_min.sum() if is_min[is_default].any() else 0.0


def hit_matrix(pairs, tau_s=0.0):
    """Pairs x W_GRID hit matrix."""
    return np.array([[hit(p["arrival"] + (w - 1) * p["walk"] + tau_s * p["transfers"], p["default"])
                      for w in W_GRID] for p in pairs])


def feasible_interval(pair):
    """[lower, upper] of w >= 1 under which the default is least-cost; None if no w works (not walk)."""
    d = np.flatnonzero(pair["default"])[0]
    lower, upper = 1.0, np.inf
    for r in range(len(pair["arrival"])):
        if r == d:
            continue
        gain_s = pair["arrival"][r] - pair["arrival"][d]       # how much later r arrives than d
        walk_diff_s = pair["walk"][d] - pair["walk"][r]        # how much more d walks than r
        if walk_diff_s == 0:
            if gain_s < 0:
                return None
            continue
        bound = 1 + gain_s / walk_diff_s
        if walk_diff_s > 0:
            upper = min(upper, bound)
        else:
            lower = max(lower, bound)
    return (lower, upper) if lower <= upper else None


def best_of(share):
    best_ix = int(np.argmax(share))
    return W_GRID[best_ix], share[best_ix]


def bootstrap_best(matrix, rng):
    n_pairs = matrix.shape[0]
    draws = [W_GRID[int(np.argmax(matrix[rng.integers(0, n_pairs, n_pairs)].mean(axis=0)))]
             for _ in range(N_BOOTSTRAP)]
    return np.quantile(draws, BOOTSTRAP_QUANTILES)


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    out_prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}"
    lines = []

    def say(text):
        print(text)
        lines.append(text)

    pairs = pair_arrays(load_routes())
    sets = np.array([p["set"] for p in pairs])
    say(f"{NAME} {run_date}: {len(pairs)} pairs with 2+ Google routes; per set "
        f"{ {str(k): int(v) for k, v in zip(*np.unique(sets, return_counts=True))} }; walk speed {WALK_SPEED_KMH} km/h")

    matrix = hit_matrix(pairs)
    share = matrix.mean(axis=0)
    best_w, best_share = best_of(share)
    share_w1 = share[0]
    in_range = W_GRID[share >= best_share - RANGE_TOLERANCE]
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    ci = bootstrap_best(matrix, rng)
    say(f"pooled: w = 1 share {share_w1:.3f}; best w {best_w:.2f} share {best_share:.3f} "
        f"(gain {best_share - share_w1:+.3f}); within {RANGE_TOLERANCE:.0%}: {in_range.min():.2f}-{in_range.max():.2f}; "
        f"bootstrap best w {ci[0]:.2f} / {ci[1]:.2f} / {ci[2]:.2f}")
    is_r1 = (best_share - share_w1 >= MIN_GAIN) and ci[0] > 1.0
    say(f"R1 walk weight: {'YES' if is_r1 else 'NO'} (gain >= {MIN_GAIN} and interval excludes 1)")

    set_rows = []
    is_stable = True
    for set_name in GOOGLE_ROUTES_PATHS:
        set_matrix = matrix[sets == set_name]
        set_share = set_matrix.mean(axis=0)
        set_best_w, set_best_share = best_of(set_share)
        set_ci = bootstrap_best(set_matrix, rng)
        covers = set_ci[0] <= best_w <= set_ci[2]
        is_stable &= covers
        set_rows.append({"set": set_name, "n": len(set_matrix), "share_w1": set_share[0], "best_w": set_best_w,
                         "best_share": set_best_share, "ci_lo": set_ci[0], "ci_hi": set_ci[2], "covers": covers})
        say(f"  {set_name}: n {len(set_matrix)}; w = 1 {set_share[0]:.3f}; best w {set_best_w:.2f} share "
            f"{set_best_share:.3f}; bootstrap {set_ci[0]:.2f}-{set_ci[2]:.2f}; covers pooled: {covers}")
    say(f"R2 stable: {'YES' if is_stable else 'NO'}")

    # report only: ceiling and the bounds' spread
    intervals = [feasible_interval(p) for p in pairs]
    feasible = [iv for iv in intervals if iv is not None]
    lowers = np.array([lo for lo, _ in feasible if lo > 1.0])
    uppers = np.array([hi for _, hi in feasible if np.isfinite(hi)])
    say(f"ceiling (report only): some single w >= 1 explains {len(feasible) / len(pairs):.3f} of pairs; on the grid "
        f"{(matrix.max(axis=1) == 1).mean():.3f}; not walk (no w works) {1 - len(feasible) / len(pairs):.3f}")
    say(f"  pairs whose default needs w > 1: {len(lowers)}, lower bound quartiles "
        f"{np.round(np.quantile(lowers, [0.25, 0.5, 0.75]), 2).tolist()}; pairs capping w: {len(uppers)}, upper "
        f"bound quartiles {np.round(np.quantile(uppers, [0.25, 0.5, 0.75]), 2).tolist()}")

    # report only: transfer penalty alongside w
    tau_rows = []
    for tau_s in TAU_GRID_S:
        tau_share = hit_matrix(pairs, tau_s).mean(axis=0)
        tau_w, tau_best = best_of(tau_share)
        tau_rows.append({"tau_s": tau_s, "best_w": tau_w, "best_share": tau_best})
    tau_df = pd.DataFrame(tau_rows)
    top = tau_df.loc[tau_df["best_share"].idxmax()]
    say(f"transfer penalty (report only): best tau {top.tau_s:.0f} s with w {top.best_w:.2f}, share "
        f"{top.best_share:.3f} (vs {best_share:.3f} without)")
    say(f"railtram bound ~{RAILTRAM_BOUND_W} (report only): {'inside' if ci[0] <= RAILTRAM_BOUND_W <= ci[2] else 'outside'} "
        f"the bootstrap interval; share at {RAILTRAM_BOUND_W}: {share[np.isclose(W_GRID, RAILTRAM_BOUND_W)][0]:.3f}")

    pd.DataFrame({"w": W_GRID, "share": share}).to_csv(f"{out_prefix}_curve.csv", index=False)
    pd.DataFrame(set_rows).to_csv(f"{out_prefix}_sets.csv", index=False)
    tau_df.to_csv(f"{out_prefix}_tau.csv", index=False)
    Path(f"{out_prefix}_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
