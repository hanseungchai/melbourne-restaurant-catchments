"""Which rule picks Google's default transit route, and what boarding and transfer penalties do its choices allow?

Exploratory (user, 2026-10-17: build the default-route diagnostic, then the penalty fit); no pass rule, no
verdict. Claims under test: concepts/transit.md T7 (f) (the fit target: earliest arrival, the default's
arrival, or the default's displayed duration, set from how Google picks its default) and T7 (c) (Google's
default vs its own alternatives bounds the penalties). Where the pipeline would rely on it: the target and
the penalty range of the ride-cap penalty fit (T7 a, b; DESIGN.md Q22), the next build step.

Method: training-half pairs (transit split, half == "train") with 2+ Google routes; every route Google
returned counts, in scope or not (this is about Google's choice, not R5's reach). Per route:
A = arrival_from_request_s (arrival minus the requested departure, initial wait included), D = duration_s
(Google's displayed duration, initial wait excluded), k = n_transit_steps (boardings), walk_m.
A rule picks the route with the least cost; its hit share is the mean over pairs of 1 / n_tied if the
default is among the least-cost routes, else 0 (a random tie-break's expected hit). Strict hits (default
alone at the minimum) are reported too. Rules:
  - earliest arrival (cost A); shortest duration (cost D); fewest boardings, then earliest arrival;
  - penalised: base + beta * [k >= 1] + tau * max(k - 1, 0), base A or D, beta (first boarding) and tau
    (each transfer) on a grid of 0..PENALTY_MAX_S in PENALTY_STEP_S; one alpha (beta = tau) is the grid's
    diagonal;
  - exploratory, beyond the user's two penalties: the best base with a walk weight w (cost adds
    (w - 1) * walk_m / walk speed), on a coarser grid.
Google's range: the grid cells within RANGE_TOLERANCE of the best hit share, and a pair bootstrap
(N_BOOTSTRAP draws) of the best cell. Late defaults (default arrives after the earliest route): how the
default compares with the earliest route on D, k, walk_m and the initial wait.

Conclusion (run 2026-10-17; 1,209 training pairs with 2+ routes, 43 single-route left out): earliest
arrival picks the default on 0.734 (strict 0.691); shortest duration 0.283; fewest boardings then earliest
arrival 0.589. Boarding and transfer penalties alone add nothing on arrival (best beta = tau = 0; cells
within 1 pp: beta 0-120 s, tau 0-340 s). The 260 late defaults (median 2.8 min late) walk less than the
earliest route on 238 (median -460 m), have fewer boardings on 53 and more on 53; less walk alone explains
99, all three leave 4. Exploratory walk weight on arrival: w 1.5 0.890, w 1.75 0.929, w 2.0 0.945 (beta
90 s, tau 480 s), w 2.5 0.908. Reading: Google trades arrival time mainly for less walking; a transfer
penalty appears only alongside a walk weight (fewer walks are bought with more transfers). Not decided.

Inputs (read only): the transit split and Google route table in outputs/transit_validation/. Self-contained:
imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls, no r5py. No saved data to
reuse (stored answers only); results carry the run date; a same-day rerun replaces that day's results.
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
GOOGLE_ROUTES_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_default_route"

# --- values copied from config.py and the record ---------------------------------------------------
TRAIN_HALF = "train"
WALK_SPEED_KMH = 4.16                          # config.WALK_SPEED_KMH (WLK-1)
S_PER_HOUR = 3600
M_PER_KM = 1000
SECONDS_PER_MIN = 60

# --- grid and reporting ----------------------------------------------------------------------------
PENALTY_MAX_S = 15 * SECONDS_PER_MIN           # T7 (b)'s grid, 0-15 min
PENALTY_STEP_S = 10
WALK_WEIGHTS = [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]   # exploratory walk weight
WALK_GRID_STEP_S = 30                          # coarser penalty grid for the walk-weight variant
RANGE_TOLERANCE = 0.01                         # cells within 1 percentage point of the best share
N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 20261017
BOOTSTRAP_QUANTILES = [0.025, 0.5, 0.975]
LATE_QUANTILES = [0.25, 0.5, 0.75, 0.9]

# --- columns ---------------------------------------------------------------------------------------
DRAW_NO_COL = "draw_no"
ARRIVAL_COL = "arrival_from_request_s"
DURATION_COL = "duration_s"
BOARDINGS_COL = "n_transit_steps"
WALK_M_COL = "walk_m"
WAIT_COL = "leave_wait_s"
DEFAULT_COL = "is_default"
BASES = {"arrival": ARRIVAL_COL, "duration": DURATION_COL}


def load_routes():
    """Training-half routes of pairs with 2+ routes, sorted by pair; one row per Google route."""
    split_df = pd.read_csv(SPLIT_PATH)
    routes_df = pd.read_csv(GOOGLE_ROUTES_PATH)
    train_draws = split_df.loc[split_df["half"] == TRAIN_HALF, DRAW_NO_COL]
    routes_df = routes_df[routes_df[DRAW_NO_COL].isin(train_draws)]
    n_routes = routes_df.groupby(DRAW_NO_COL)[DRAW_NO_COL].transform("size")
    n_pairs_single = routes_df.loc[n_routes < 2, DRAW_NO_COL].nunique()
    routes_df = routes_df[n_routes >= 2].sort_values([DRAW_NO_COL, "route_ix"]).reset_index(drop=True)
    n_defaults = routes_df.groupby(DRAW_NO_COL)[DEFAULT_COL].sum()
    if not (n_defaults == 1).all():
        raise ValueError(f"pairs without exactly one default: {n_defaults[n_defaults != 1].index.tolist()}")
    return routes_df, train_draws.size, n_pairs_single


def pair_starts(routes_df):
    """Start row of each pair (routes_df sorted by pair), for np.*.reduceat."""
    is_start = routes_df[DRAW_NO_COL].ne(routes_df[DRAW_NO_COL].shift()).to_numpy()
    return np.flatnonzero(is_start)


def hit_scores(costs, is_default, starts):
    """costs: routes x rules. Per pair and rule: (expected hit under a random tie-break, strict hit)."""
    pair_of_route = np.cumsum(np.isin(np.arange(costs.shape[0]), starts)) - 1
    pair_min = np.minimum.reduceat(costs, starts, axis=0)
    is_min = costs <= pair_min[pair_of_route]
    n_min = np.add.reduceat(is_min.astype(np.int32), starts, axis=0)
    default_is_min = np.add.reduceat(is_min & is_default[:, None], starts, axis=0) > 0
    return default_is_min / n_min, default_is_min & (n_min == 1)


def penalty_costs(base, boardings, betas, tau):
    """Routes x betas cost matrix for one tau."""
    has_ride = (boardings >= 1).astype(float)
    n_transfers = np.maximum(boardings - 1, 0)
    return base[:, None] + has_ride[:, None] * betas[None, :] + (n_transfers * tau)[:, None]


def penalty_grid(routes_df, starts, base_col, grid_s, walk_weight=1.0):
    """Per pair x (beta, tau) cell: expected hit. Returns (pairs x cells array, cells_df)."""
    walk_s = routes_df[WALK_M_COL].to_numpy() / (WALK_SPEED_KMH * M_PER_KM / S_PER_HOUR)
    base = routes_df[base_col].to_numpy(float) + (walk_weight - 1) * walk_s
    boardings = routes_df[BOARDINGS_COL].to_numpy()
    is_default = routes_df[DEFAULT_COL].to_numpy(bool)
    blocks, cells = [], []
    for tau in grid_s:
        expected, _ = hit_scores(penalty_costs(base, boardings, grid_s, tau), is_default, starts)
        blocks.append(expected)
        cells.extend((beta, tau) for beta in grid_s)
    cells_df = pd.DataFrame(cells, columns=["beta_s", "tau_s"]).assign(walk_weight=walk_weight)
    return np.hstack(blocks), cells_df


def bootstrap_best(expected, cells_df, rng):
    """Pair bootstrap of the best cell: quantiles of beta, tau and the best share."""
    n_pairs = expected.shape[0]
    weights = rng.multinomial(n_pairs, np.full(n_pairs, 1 / n_pairs), size=N_BOOTSTRAP) / n_pairs
    shares = weights @ expected
    best = shares.argmax(axis=1)
    draws_df = pd.DataFrame({"beta_s": cells_df["beta_s"].to_numpy()[best],
                             "tau_s": cells_df["tau_s"].to_numpy()[best],
                             "best_share": shares.max(axis=1)})
    return draws_df.quantile(BOOTSTRAP_QUANTILES)


def simple_rules(routes_df, starts):
    """Earliest arrival, shortest duration, fewest boardings then earliest arrival: shares."""
    arrival = routes_df[ARRIVAL_COL].to_numpy(float)
    boardings = routes_df[BOARDINGS_COL].to_numpy(float)
    big = arrival.max() + 1
    costs = np.column_stack([arrival, routes_df[DURATION_COL].to_numpy(float), boardings * big + arrival])
    expected, strict = hit_scores(costs, routes_df[DEFAULT_COL].to_numpy(bool), starts)
    names = ["earliest arrival", "shortest duration", "fewest boardings, then earliest arrival"]
    return pd.DataFrame({"rule": names, "hit_share": expected.mean(axis=0), "strict_share": strict.mean(axis=0)})


def late_defaults(routes_df):
    """Pairs whose default arrives after the earliest route: default minus earliest route (fewest
    boardings among the earliest), per pair."""
    earliest_s = routes_df.groupby(DRAW_NO_COL)[ARRIVAL_COL].transform("min")
    earliest_df = (routes_df[routes_df[ARRIVAL_COL] == earliest_s].sort_values([DRAW_NO_COL, BOARDINGS_COL])
                   .drop_duplicates(DRAW_NO_COL).set_index(DRAW_NO_COL))
    default_df = routes_df[routes_df[DEFAULT_COL]].set_index(DRAW_NO_COL)
    cols = [ARRIVAL_COL, DURATION_COL, BOARDINGS_COL, WALK_M_COL, WAIT_COL]
    diff_df = (default_df[cols] - earliest_df.loc[default_df.index, cols]).add_prefix("d_")
    return diff_df[diff_df["d_" + ARRIVAL_COL] > 0]


def describe_late(late_df):
    """How late defaults differ from the earliest route."""
    lines = [f"late defaults: {len(late_df)}",
             "  late by (min) quantiles: "
             + str((late_df["d_" + ARRIVAL_COL] / SECONDS_PER_MIN).quantile(LATE_QUANTILES).round(1).to_dict())]
    for col, label in [(DURATION_COL, "duration"), (BOARDINGS_COL, "boardings"), (WALK_M_COL, "walk_m"),
                       (WAIT_COL, "initial wait")]:
        diff = late_df["d_" + col]
        lines.append(f"  default vs earliest, {label}: less {int((diff < 0).sum())}, same {int((diff == 0).sum())}, "
                     f"more {int((diff > 0).sum())}; median diff {diff.median():.0f}")
    is_shorter = late_df["d_" + DURATION_COL] < 0
    is_fewer = late_df["d_" + BOARDINGS_COL] < 0
    is_less_walk = late_df["d_" + WALK_M_COL] < 0
    lines.append(f"  explained by none of shorter duration / fewer boardings / less walk: "
                 f"{int((~is_shorter & ~is_fewer & ~is_less_walk).sum())}")
    lines.append(f"  shorter duration only: {int((is_shorter & ~is_fewer & ~is_less_walk).sum())}; "
                 f"fewer boardings only: {int((is_fewer & ~is_shorter & ~is_less_walk).sum())}; "
                 f"less walk only: {int((is_less_walk & ~is_shorter & ~is_fewer).sum())}")
    return lines


def grid_summary(expected, cells_df, label, rng):
    """Best cell, range within tolerance, one-alpha diagonal best, bootstrap of the best cell."""
    shares = expected.mean(axis=0)
    cells_df = cells_df.assign(hit_share=shares)
    best = cells_df.loc[shares.argmax()]
    in_range = cells_df[cells_df["hit_share"] >= shares.max() - RANGE_TOLERANCE]
    diagonal = cells_df[cells_df["beta_s"] == cells_df["tau_s"]]
    best_alpha = diagonal.loc[diagonal["hit_share"].idxmax()]
    zero = cells_df[(cells_df["beta_s"] == 0) & (cells_df["tau_s"] == 0)]["hit_share"].iloc[0]
    boot_df = bootstrap_best(expected, cells_df, rng)
    lines = [f"{label} (walk weight {best['walk_weight']}):",
             f"  no penalty: {zero:.3f}; best: beta {best['beta_s']:.0f} s, tau {best['tau_s']:.0f} s, "
             f"share {best['hit_share']:.3f}",
             f"  one alpha (beta = tau): {best_alpha['beta_s']:.0f} s, share {best_alpha['hit_share']:.3f}",
             f"  cells within {RANGE_TOLERANCE:.0%} of best: {len(in_range)}; beta {in_range['beta_s'].min():.0f}-"
             f"{in_range['beta_s'].max():.0f} s, tau {in_range['tau_s'].min():.0f}-{in_range['tau_s'].max():.0f} s",
             "  bootstrap of the best cell (2.5 / 50 / 97.5%): "
             + "; ".join(f"{col} {' / '.join(f'{v:.3g}' for v in boot_df[col])}" for col in boot_df.columns)]
    return lines, cells_df


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    out_prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}"
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    routes_df, n_train, n_single = load_routes()
    starts = pair_starts(routes_df)
    n_pairs = len(starts)
    lines = [f"{NAME} run {run_date}",
             f"training pairs {n_train}; with 2+ routes {n_pairs} ({len(routes_df)} routes); "
             f"single-route pairs left out {n_single}",
             "default boardings: " + str(routes_df.loc[routes_df[DEFAULT_COL], BOARDINGS_COL]
                                         .value_counts().sort_index().to_dict()), "",
             "simple rules (hit share = expected under a random tie-break; strict = default alone at the minimum):"]
    simple_df = simple_rules(routes_df, starts)
    lines += [f"  {row.rule}: {row.hit_share:.3f} (strict {row.strict_share:.3f})" for row in simple_df.itertuples()]
    lines += [""] + describe_late(late_defaults(routes_df)) + [""]

    grid_s = np.arange(0, PENALTY_MAX_S + 1, PENALTY_STEP_S, dtype=float)
    grid_tables, best_shares = [], {}
    for base_name, base_col in BASES.items():
        expected, cells_df = penalty_grid(routes_df, starts, base_col, grid_s)
        grid_lines, cells_df = grid_summary(expected, cells_df, f"penalised, base {base_name}", rng)
        lines += grid_lines + [""]
        grid_tables.append(cells_df.assign(base=base_name))
        best_shares[base_name] = cells_df["hit_share"].max()

    best_base = max(best_shares, key=best_shares.get)
    walk_grid_s = np.arange(0, PENALTY_MAX_S + 1, WALK_GRID_STEP_S, dtype=float)
    lines.append(f"exploratory: walk weight on base {best_base} (penalty grid step {WALK_GRID_STEP_S} s):")
    for walk_weight in WALK_WEIGHTS:
        expected, cells_df = penalty_grid(routes_df, starts, BASES[best_base], walk_grid_s, walk_weight)
        shares = expected.mean(axis=0)
        best = cells_df.loc[shares.argmax()]
        lines.append(f"  w {walk_weight}: best share {shares.max():.3f} at beta {best['beta_s']:.0f} s, "
                     f"tau {best['tau_s']:.0f} s")

    pd.concat(grid_tables, ignore_index=True).to_csv(f"{out_prefix}_grid.csv", index=False)
    late_defaults(routes_df).to_csv(f"{out_prefix}_late_defaults.csv")
    summary = "\n".join(lines)
    Path(f"{out_prefix}_summary.txt").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
