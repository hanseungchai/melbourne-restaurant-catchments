"""Transit search cap (RCH-19): does a 30-min cap on the frozen model's time lose any pair Google reaches within a band?

Claim under test (concepts/reachability.md RCH-19; user 2026-10-19): routing bands 1-2 with R5's max time at the cap
(30 min, stored to 31 min so that times in [30:00, 30:30) still round to 30, SCR-10) keeps every pair whose Google time
is within the 20-min band, so the uncertainty around the cut stays visible. Where the pipeline relies on it: the transit
reachability pass (config.REACH_TRANSIT_MAX_TIME_MIN; reachability.transit_subject_pass).

Method (no routing; saved frozen-model scores): transit_holdout_score's scored pairs (TRN-16 frozen model, max 90 min,
min(transit, walk) seconds), seen + holdout. Model minutes = seconds rounded half up (SCR-10). Google's time read two
ways: its default route (default_min) and TRN-15's range lower end (low_2: earliest of its first 2 in-scope routes).
Per band cut (10, 20): pairs with Google <= cut; how many the model puts past the cut, their quantiles, and how many
past each candidate cap (25, 30, 35).
Reading rule (Claude's, not user-approved; written 2026-10-23 before any result of this script): the 30-min cap holds
if no scored pair with Google (either reading) <= 20 min has a model time past 30 min (rounded). Report only: the
same for 10 min; quantiles; the share of all scored pairs past 30 min (work the cap saves). RCH-19's in-session figures
(no-wait plain v2, 3,239 pairs: median 22, p90 25, max 29) were on another model; this is the frozen model's check.

Conclusion (run 2026-10-23, 83rd autonomous): rule FAIL as written: of 12,677 scored pairs, 1,936 have Google's
default <= 20 min; 101 of them the model puts past 20 (median 22, p90 28, max 40) and 4 past 30 (32, 34, 37, 40
min; 3 seen, 1 holdout), 0.21% of the band; same 4 with the range reading. Band 1: 0 past 25. A 35-min cap would keep
2 of the 4. 65% of all scored pairs lie past 30 (the work the cap saves). Claude's reading: the 4 are the model-error
tail RCH-26 prices as the shelf (cut 30 misses 0 core persons, 0.06% with the shelf); the cap stays the user's
decision (30, RCH-19 / RCH-26), not changed here.
Inputs (read only): transit_holdout_score's seen and holdout results (2026-10-22). Self-contained (CLAUDE.md D1).
No API calls. Usage: `python transit_search_cap.py`.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_search_cap"
SCORE_NAME = "transit_holdout_score"
SCORE_DATE = "20261022"
SETS = ["seen", "holdout"]
CUTS_MIN = [10, 20]
CAP_MIN = 30
CANDIDATE_CAPS_MIN = [25, 30, 35]
GOOGLE_READINGS = {"default": "default_min", "range low (k = 2)": "low_2"}
QUANTILES = [0.5, 0.9, 1.0]
SECONDS_PER_MIN = 60


def half_up_min(seconds):
    return np.floor(seconds / SECONDS_PER_MIN + 0.5)


def main():
    run_date = f"{datetime.date.today():%Y%m%d}"
    frames = [pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{SCORE_NAME}_{SCORE_DATE}_{name}_results.csv").assign(score_set=name)
              for name in SETS]
    pairs_df = pd.concat(frames, ignore_index=True)
    pairs_df = pairs_df[pairs_df.is_scored].copy()
    pairs_df["model_min_r"] = half_up_min(pairs_df.model_s)
    lines = [f"{NAME} {run_date}: {len(pairs_df):,} scored pairs ({', '.join(f'{n} {k:,}' for n, k in pairs_df.score_set.value_counts().items())}); "
             f"model minutes = seconds rounded half up; cap {CAP_MIN} min"]
    is_ok = True
    for label, column in GOOGLE_READINGS.items():
        for cut in CUTS_MIN:
            within = pairs_df[pairs_df[column] <= cut]
            past = within[within.model_min_r > cut]
            caps = {cap: int((within.model_min_r > cap).sum()) for cap in CANDIDATE_CAPS_MIN}
            quantiles = past.model_min_r.quantile(QUANTILES).to_dict() if len(past) else {}
            lines.append(f"Google {label} <= {cut} min: {len(within):,} pairs; model past {cut}: {len(past):,} "
                         f"(model min quantiles {', '.join(f'q{q:g} {v:.0f}' for q, v in quantiles.items())}); "
                         f"past cap: {', '.join(f'{c} min {n}' for c, n in caps.items())}")
            if cut == max(CUTS_MIN):
                is_ok &= caps[CAP_MIN] == 0
                lines += [f"    past {CAP_MIN}: draw {r.draw_no} ({r.score_set}) Google {r[column]:.0f}, model "
                          f"{r.model_min_r:.0f}" for _, r in within[within.model_min_r > CAP_MIN].iterrows()]
    lines.append(f"scored pairs with model past {CAP_MIN} min (routing the cap saves): "
                 f"{(pairs_df.model_min_r > CAP_MIN).mean():.1%}")
    lines.append(f"rule (Claude's): no pair with Google <= {max(CUTS_MIN)} has model > {CAP_MIN}: "
                 f"{'PASS' if is_ok else 'FAIL'}")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
