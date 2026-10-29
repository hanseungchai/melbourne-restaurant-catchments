"""TRN-13 stage 1b: how often, and by how much, does Google's default trail its own earliest route, and what does it buy?

Claim under test (concepts/transit.md TRN-13 (c) stage 1b; reported, not gating): Google's default is not its
earliest arrival on a share of pairs (T7 f: 0.734 earliest); the gap, its drivers (home wait, transfers, walking)
and the earliest route's position set (a) whether the range needs 3+ routes and (b) the wait preference the
departure-profile oracle would copy and the longest home wait (profile length n). Where the pipeline relies on
it: the candidate window value (TRN-13, after stages 1b and 2) and stage 1's k = 2.

Method (Claude's): random samples (training half, second batch), pairs whose default is in scope; all of
Google's returned routes in scope (TRN-11) with an arrival. Earliest = smallest arrival_from_request_s (ties:
lowest route_ix). Minutes unrounded here (seconds / 60).

Conclusion (run 2026-10-18): 3,239 pairs; the default is Google's earliest on 0.784, trails on 0.216 by median
  2.7 min (p90 8.2); where it trails, the earliest is at the third route or later on 0.434 (k = 2 misses it, yet
  stage 1 moves little from k 2 to all). The default buys less walking (0.901 of trailing pairs, median -448 m) and
  pays in home wait (+2.8 min median); transfers do not differ. Trailing rises with the default's home wait (0.118
  under 2 min, 0.402 over 20). Riding defaults wait at home median 4.3 min, p90 13.1, p95 17.9: a departure profile
  of n ~ 15-20 min covers 90-95% of Google's waits.

Inputs (read only): the Google route tables and split in outputs/transit_validation/. The test half is not read.
Self-contained (CLAUDE.md D1). No API calls.
Usage: `python transit_google_preference.py`. Results carry the run date; a same-day rerun replaces them.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_google_preference"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv"}
TRAIN_HALF = "train"
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]
SECONDS_PER_MIN = 60
WAIT_BINS_MIN = [0, 2, 5, 10, 20, np.inf]
GAP_REPORT_PERCENTILES = [50, 75, 90]
POSITION_LATE = 2                              # route_ix 2 = third route


def load_routes():
    split_df = pd.read_csv(SPLIT_PATH, usecols=["draw_no", "half"])
    frames = []
    for set_name, path in ROUTES_PATHS.items():
        routes_df = pd.read_csv(path)
        if set_name == "train":
            routes_df = routes_df[routes_df.draw_no.isin(split_df.draw_no[split_df.half == TRAIN_HALF])]
        frames.append(routes_df.assign(set_name=set_name))
    routes_df = pd.concat(frames, ignore_index=True)
    default_ok = routes_df[routes_df.is_default & routes_df.route_scope.isin(GOOGLE_SCOPES) & routes_df.arrival_from_request_s.notna()]
    routes_df = routes_df.merge(default_ok[["set_name", "draw_no"]], on=["set_name", "draw_no"])
    routes_df = routes_df[routes_df.route_scope.isin(GOOGLE_SCOPES) & routes_df.arrival_from_request_s.notna()].copy()
    routes_df["arrival_min"] = routes_df.arrival_from_request_s / SECONDS_PER_MIN
    routes_df["wait_min"] = routes_df.leave_wait_s / SECONDS_PER_MIN
    return routes_df


def main():
    run_date = f"{datetime.date.today():%Y%m%d}"
    routes_df = load_routes()
    keys = ["set_name", "draw_no"]
    default_df = routes_df[routes_df.is_default].set_index(keys)
    earliest_df = routes_df.sort_values(keys + ["arrival_from_request_s", "route_ix"]).drop_duplicates(keys).set_index(keys)
    pair_df = default_df[["route_ix", "arrival_min", "wait_min", "walk_m", "n_transit_steps", "is_walk_only", "vehicle_types"]].join(
        earliest_df[["route_ix", "arrival_min", "wait_min", "walk_m", "n_transit_steps", "is_walk_only"]], rsuffix="_earliest")
    pair_df["gap_min"] = pair_df.arrival_min - pair_df.arrival_min_earliest
    pair_df["n_routes"] = routes_df.groupby(keys).size()
    is_trailing = pair_df.gap_min > 0
    lines = [f"{NAME} {run_date}: Google's default vs its earliest in-scope route; random samples, default in scope",
             f"pairs {len(pair_df)}; routes per pair {pair_df.n_routes.value_counts().sort_index().to_dict()}",
             f"default is the earliest on {1 - is_trailing.mean():.3f}; trails on {int(is_trailing.sum())} ({is_trailing.mean():.3f})"]
    gaps = pair_df.gap_min[is_trailing]
    lines.append("  gap where trailing (min): " + ", ".join(f"p{p} {np.percentile(gaps, p):.1f}" for p in GAP_REPORT_PERCENTILES)
                 + f", max {gaps.max():.1f}; >= 3 min on {int((gaps >= 3).sum())}, >= 5 on {int((gaps >= 5).sum())}")
    position = pair_df.route_ix_earliest[is_trailing]
    lines.append(f"  earliest route's position (route_ix) where trailing: {position.value_counts().sort_index().to_dict()}; "
                 f"at the third route or later: {int((position >= POSITION_LATE).sum())} ({(position >= POSITION_LATE).mean():.3f})")
    trailing_df = pair_df[is_trailing]
    lines += ["  what the default buys over the earliest (trailing pairs; default minus earliest):",
              f"    home wait: median {np.median(trailing_df.wait_min - trailing_df.wait_min_earliest):+.1f} min; "
              f"default waits longer on {(trailing_df.wait_min > trailing_df.wait_min_earliest).mean():.3f}",
              f"    walking: median {np.median(trailing_df.walk_m - trailing_df.walk_m_earliest):+.0f} m; less walking on "
              f"{(trailing_df.walk_m < trailing_df.walk_m_earliest).mean():.3f}",
              f"    transit legs: fewer on {(trailing_df.n_transit_steps < trailing_df.n_transit_steps_earliest).mean():.3f}, more on "
              f"{(trailing_df.n_transit_steps > trailing_df.n_transit_steps_earliest).mean():.3f}",
              f"    default walk-only while the earliest rides: {int((trailing_df.is_walk_only & ~trailing_df.is_walk_only_earliest).sum())}; "
              f"default rides while the earliest walks: {int((~trailing_df.is_walk_only & trailing_df.is_walk_only_earliest).sum())}"]
    wait_bins = pd.cut(pair_df.wait_min, WAIT_BINS_MIN, right=False)
    lines.append("  by the default's home wait (min): share trailing, median gap where trailing, n")
    for bin_value, bin_df in pair_df.groupby(wait_bins, observed=True):
        bin_gaps = bin_df.gap_min[bin_df.gap_min > 0]
        lines.append(f"    {bin_value}: {(bin_df.gap_min > 0).mean():.3f}, {bin_gaps.median() if len(bin_gaps) else np.nan:.1f}, n {len(bin_df)}")
    lines.append("  by the default's transit legs: share trailing, n")
    for legs, legs_df in pair_df.groupby("n_transit_steps"):
        lines.append(f"    {legs}: {(legs_df.gap_min > 0).mean():.3f}, n {len(legs_df)}")
    ride_df = pair_df[~pair_df.is_walk_only]
    lines.append(f"  default's home wait (riding defaults, n {len(ride_df)}): " + ", ".join(
        f"p{p} {np.percentile(ride_df.wait_min, p):.1f}" for p in [50, 75, 90, 95, 99]) + f", max {ride_df.wait_min.max():.1f} min; "
        f">= 5 min on {(ride_df.wait_min >= 5).mean():.3f}, >= 10 on {(ride_df.wait_min >= 10).mean():.3f}")
    earliest_ride = pair_df[~pair_df.is_walk_only_earliest]
    lines.append(f"  earliest route's home wait (riding, n {len(earliest_ride)}): " + ", ".join(
        f"p{p} {np.percentile(earliest_ride.wait_min_earliest, p):.1f}" for p in [50, 90, 99]))
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary + "\n")
    pair_df.reset_index().to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_pairs.csv", index=False)


if __name__ == "__main__":
    main()
