"""TRN-13: does the no-wait plain-cut model's reach count match Google's, overall and by service-density third?

Claim under test (concepts/transit.md TRN-13; DESIGN.md Q23): the hard misses of the transit band model (no-wait,
plain cuts 10 / 20, pathways network v2) are a located cost that leaves the reach count, the quantity the output is
built from, unbiased against Google's range. Where the pipeline relies on it: the transit bands (SCR-1, RCH-1).
Stage 1's per-cut tests score pairs 3-10 min from a cut; this check scores every pair, knife-edge ones included,
and asks the output's question directly: how many pairs does R5 put within the cut, against Google?

Test details (Claude's rules, not user-approved; written before any result of this script was computed; the count
ratio against Google's default alone, 1.087 at 10 and 1.073 at 20, was already known from stage 1):
  Pairs: random samples only (train, second), as scored by transit_hard_miss_range.py on the v2 network (its
    newest range results). The origins are nearly all distinct (2,668 origins in 3,448 pairs), so a per-origin
    count is not possible: the check is on the share of pairs reached, which is what a reach count over random
    pairs estimates.
  Reach at cut c: R5 if n_min <= c; Google's range runs from its default (default_min <= c, the fewer pairs) to its
    earliest arrival among the first k = 2 routes (low_2 <= c, the more pairs).
  Net error at c = R5 share - nearest end of Google's range (0 inside it), in percentage points of pairs.
    Bootstrap 95% interval over pairs (paired resampling, fixed seed).
  Verdict per cut, overall and per third: "unbiased" if the interval of the net error contains 0; else "leans
    over" / "leans under". Overall is the gate; thirds are read for location.
  Service-density thirds: stage 1's own strata (origin trips within 700 m, +-30 min), unchanged.
  Prediction (Claude, from the no-wait design): the model skips the wait at the first stop, so any over-lean
    against Google's default is largest in the low-service third, where waits are longest.
  Secondary slice: thirds of straight-line distance from the origin to the CBD (Melbourne GPO); its rank
    correlation with origin trips is reported first, to show how far it repeats the density slice.

Conclusion (run 2026-10-19; Claude's rules): overall UNBIASED at both cuts, at 20 only just (net +0.46 pp,
  interval 0.00 to +0.96). R5 reaches 112 / 488 pairs at 10 / 20; Google's range 103-105 / 455-473. The lean sits
  in one place: the high-service third at 20 LEANS OVER (R5 302 vs range 276-288, net +1.30 pp of that third's
  pairs, interval +0.19 to +2.41); low and mid thirds are inside the range or within noise at both cuts.
  Prediction FAILS: the over-lean grows with service (low +0.19, mid +0.46, high +2.41 pp vs default at 20), so
  skipping the first wait is not the main driver; it matches stage 1's largest miss group, "Google rides a tram,
  R5 faster", mostly high-service. Distance to CBD repeats the density slice (Spearman -0.86; 984 of 1,079
  high-service pairs are in the near third), so it adds no independent evidence; its near third leans over likewise.

Inputs (read only): diagnostic_data/transit_pathway_network_v2_*_range_results.csv (newest).
Self-contained (CLAUDE.md D1). No API calls, no R5.
Usage: `python transit_net_reach.py`. Results carry the run date; a same-day rerun replaces them.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_net_reach"
RANGE_RESULTS_PATTERN = "transit_pathway_network_v2_2*_range_results.csv"

# --- test (Claude) ---------------------------------------------------------------------------------
RANDOM_SETS = ["train", "second"]
CUTS_MIN = [10, 20]
GATING_K = 2
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261019
INTERVAL_LOW_Q, INTERVAL_HIGH_Q = 0.025, 0.975
PERCENT = 100
STRATUM_LABELS = ["low", "mid", "high"]
DISTANCE_LABELS = ["near", "middle", "far"]
CBD_LAT, CBD_LON = -37.8136, 144.9631          # Melbourne GPO, the CBD reference point
EARTH_RADIUS_M = 6_371_008.8


def newest(pattern):
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    assert saved, f"no {pattern}"
    return saved[-1]


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def net_error(is_r5, is_default, is_low):
    """R5's share minus the nearest end of Google's range (0 inside), in share of pairs."""
    r5, default, low = is_r5.mean(axis=-1), is_default.mean(axis=-1), is_low.mean(axis=-1)
    return np.where(r5 < default, r5 - default, np.where(r5 > low, r5 - low, 0.0))


def score_group(df, cut_min, rng):
    is_r5 = (df.n_min.fillna(np.inf) <= cut_min).to_numpy()
    is_default = (df.default_min <= cut_min).to_numpy()
    is_low = (df[f"low_{GATING_K}"] <= cut_min).to_numpy()
    draws = rng.integers(0, len(df), size=(N_BOOTSTRAP, len(df)))
    boot = net_error(is_r5[draws], is_default[draws], is_low[draws])
    low_q, high_q = np.quantile(boot, [INTERVAL_LOW_Q, INTERVAL_HIGH_Q])
    point = float(net_error(is_r5, is_default, is_low))
    verdict = "unbiased" if low_q <= 0 <= high_q else ("leans over" if low_q > 0 else "leans under")
    return {"n": len(df), "r5": int(is_r5.sum()), "google_default": int(is_default.sum()), "google_earliest": int(is_low.sum()),
            "ratio_default": is_r5.sum() / is_default.sum(), "ratio_earliest": is_r5.sum() / is_low.sum(),
            "net_pp": point * PERCENT, "net_low_pp": low_q * PERCENT, "net_high_pp": high_q * PERCENT,
            "over_default_pp": (is_r5.mean() - is_default.mean()) * PERCENT, "verdict": verdict}


def main():
    run_date = f"{datetime.date.today():%Y%m%d}"
    source_path = newest(RANGE_RESULTS_PATTERN)
    df = pd.read_csv(source_path)
    df = df[df.set_name.isin(RANDOM_SETS) & df.is_scored.astype(bool)].copy()
    df["cbd_m"] = haversine_m(df.origin_lat, df.origin_lon, CBD_LAT, CBD_LON)
    df["distance_third"] = pd.qcut(df.cbd_m.rank(method="first"), len(DISTANCE_LABELS), labels=DISTANCE_LABELS)
    assert set(df.stratum) == set(STRATUM_LABELS), "stage 1 strata missing"
    rng = np.random.default_rng(BOOTSTRAP_SEED)

    rows = []
    for cut_min in CUTS_MIN:
        rows.append({"slice": "all", "group": "all", "cut_min": cut_min} | score_group(df, cut_min, rng))
        for column, labels in [("stratum", STRATUM_LABELS), ("distance_third", DISTANCE_LABELS)]:
            for label in labels:
                rows.append({"slice": column, "group": label, "cut_min": cut_min} | score_group(df[df[column] == label], cut_min, rng))
    table_df = pd.DataFrame(rows)

    rho = df[["cbd_m", "origin_trips"]].rank().corr().iloc[0, 1]
    crosstab = pd.crosstab(df.stratum, df.distance_third).reindex(index=STRATUM_LABELS, columns=DISTANCE_LABELS)
    lines = [f"{NAME} {run_date}: no-wait plain, cuts {CUTS_MIN}, Google's range k = {GATING_K}, random pairs n {len(df)}",
             f"reusing {source_path.name} ({datetime.date.fromtimestamp(source_path.stat().st_mtime)})",
             f"net = R5 share - nearest end of Google's range (0 inside), percentage points; bootstrap {N_BOOTSTRAP}, seed {BOOTSTRAP_SEED}",
             "", table_df.to_string(index=False, float_format=lambda value: f"{value:.3f}"), "",
             f"distance to CBD vs origin trips: Spearman rho {rho:.3f}", "service third x distance third:", crosstab.to_string()]
    for cut_min in CUTS_MIN:
        by_third = table_df[(table_df.slice == "stratum") & (table_df.cut_min == cut_min)].set_index("group").over_default_pp
        lines.append(f"prediction at {cut_min} (over-lean vs default largest in low third): "
                     f"{'HOLDS' if by_third.idxmax() == 'low' else 'FAILS'} ({', '.join(f'{g} {v:+.2f}' for g, v in by_third.items())} pp)")
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary + "\n", encoding="utf-8")
    table_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_table.csv", index=False)


if __name__ == "__main__":
    main()
