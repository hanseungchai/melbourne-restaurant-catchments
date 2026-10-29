"""Walk charge after routing: does adding (s - 1) x R5's walk seconds to transit trips bring R5's times nearer Google's?

Claim under test (concepts/transit.md TRN-16; DESIGN.md Q24; user's idea, 2026-10-21, 65th session): R5's early error on
transit pairs is route choice (transit_leg_error.py: same-line pairs unbiased, median +2 s; other-line pairs mean abs
263 s), and R5's routes there walk more than Google's (combos: beyond Google's walks 0.40 vs 0.19). Google weighs a
walking minute ~1.7x when it picks (transit_walk_weight.py). So a charge on the walk of R5's own fastest route, added
after routing, may stand in for Google's preference in the reported time. Unlike the failed arms (T7 (h)-(i)) and P6
(transit_walk_pick_check.py), the search is untouched: R5's route and its vehicles stay as found, only the reported
seconds grow. Walk-only trips are not charged. Where the pipeline would rely on it: transit bands 1-2 (SCR-1, RCH-1)
as a declared fitted value (TRN-16 (1) revised); it would reverse the 63rd's "reported time stays the route's real
time" (TRN-16), recorded as such if adopted.

Model: for each training pair, charged = transit_s + (s - 1) x walk_s, where transit_s is the model of record's transit
call (R5 + P1 + P3 + P2 at 4.143 km/h on v2, drawn points: transit_r5_patch_connector.py route_train p2orig) and walk_s
= access + egress + transfer walks of that same path (transit_leg_error.py route_train; transfer = the path's remainder
after waits and rides). Paths with no boarding (R5 reached no stop, or rode nothing) get no charge. The pair's time is
min(charged, the walk call), as the scorers; seconds to minutes half up (SCR-10). Grid s = 1.00-2.00 by 0.05.

Checks before any reading (stop on failure):
  (F1) the leg tables' ttm_s = the model of record's transit seconds on every pair where both have a value.
  (F2) at s = 1 the model reproduces the model of record's scored minutes on every pair, and its hard-miss total
       (transit_r5_patch_connector.py score_train: p2orig).

Rule (user, 2026-10-21, 65th: the patch rule of transit_r5_patch_board_wait.py; Claude's fitted-s addition agreed in
chat; the top-up adjustment stated before the run): hard misses as TRN-13 (k = 2 range, random pairs only).
  Pick: s* = the grid value with the lowest hard-miss total on the training half (set "train"); ties to the smallest s.
  Verdict at s* against the model of record (s = 1), each by the patch rule (IMPROVES if the total falls and no test
  gains more than SNAP_TOLERANCE_MISSES; WORSENS if it rises; else MIXED): (V1) the second batch alone (out of the pick);
  (V2) the pooled random pairs (train + second). Passes if V2 IMPROVES and V1 is not WORSENS. The top-up is not random,
  so it enters no hard test: reported only. Full measures (labels, zones, count ratios, walk-only, seconds error by
  Google's boardings, band calls changed, winner flips) at s* and s = 1; the whole curve reported.
Predictions (Claude's, before the run): s* in 1.10-1.40; false 20 falls, lost 20 rises; total 21-25; MIXED most likely;
  1-boarding median seconds error turns positive; walk-only defaults unchanged.

Conclusion (run 2026-10-21, 3,448 training pairs; rule above stated before the run): F1 PASS (0 of 3,424), F2 PASS
  (0 pairs off, total 23). Charged walk on boarded pairs median 777 s. s* = 1.10 (training-half total 8 -> 5; 1.10-1.20
  tie). V1 second batch 15 -> 14 IMPROVES; V2 pooled 23 -> 19 (false 20 14 -> 8, lost 20 7 -> 9) IMPROVES: rule PASS.
  But the charge shifts nearly every transit pair later, not the wrong-route ones: minutes change on 2,797 pairs,
  agree labels 1,492 -> 760 (late 790 -> 2,037); seconds error median 1 boarding -7 -> +54 s, 2+ -20 -> +52 s, median
  abs 41 -> 84 and 60 -> 115 s; zones fail z1 noise bar, z2 noise bar, z2 balance (late 48 / early 22, p 0.003), all
  passing at s = 1; count ratios 0.981 / 1.042 -> 0.942 / 0.956. The mean improves (-1.67 -> -0.46 min to range)
  because the tail pulls it; walk time does not single out R5's wrong-route pairs. Predictions: s* in range, false 20
  down, lost 20 up, 1-boarding median positive, walk-only unchanged all held; total 19 below 21-25, IMPROVES not MIXED.
  Adoption: the user's call (not decided).
"""
import datetime
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_walk_charge"
V2_NAME = "transit_pathway_network_v2"
RANGE_RESULTS_GLOB = f"{V2_NAME}_2*_range_owndate_results.csv"
RECORD_NAME = "transit_r5_patch_connector"
RECORD_ROUTES_GLOB = f"{RECORD_NAME}_2*_trainroutes_p2orig_{{release}}.csv"
RECORD_SCORED_GLOB = f"{RECORD_NAME}_2*_train_scored.csv"
LEGS_GLOB = "transit_leg_error_2*_trainlegs_{release}.csv"
RELEASES = ["20261009", "20261016"]
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
GOOGLE_ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                       "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                       "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
GOOGLE_COL = "arrival_from_request_s"          # the scorers' Google quantity (transit_fetch.py google_min)
WALK_LEGS = ["access_s", "egress_s", "transfer_walk_s"]
STREET_ONLY = -1                               # n_templates when R5 reached no stop (transit_leg_error.py)
S_GRID = np.round(np.arange(1.0, 2.0001, 0.05), 2)
BASE_S = 1.0
PICK_SET = "train"
CHECK_SET = "second"
TOPUP_SET = "topup"
SNAP_TOLERANCE_MISSES = 2
CUTS_MIN = {1: 10, 2: 20}
ZONES_MIN = {1: (7, 13), 2: (17, 23)}
AWAY_RANGES_MIN = [(0, 6), (14, 16), (24, 30)]
HARD_WINDOW_NEAR_MIN = 3
HARD_WINDOW_FAR_MIN = 10
HARD_MISS_MAX = 0.05
WILSON_Z = 1.959963984540054
FLOOR = 0.6
N_SIMULATIONS = 2000
SIMULATION_SEED = 20261018
SIGN_TEST_ALPHA = 0.05
CLOSE_TOLERANCE = 0.10
COUNT_RATIO_RANGE = (0.90, 1.10)
LABELS = ["late", "agree", "early"]
BOARDING_GROUPS = {0: "0", 1: "1", 2: "2+"}    # Google default's transit steps, 2 and over pooled
SECONDS_PER_MIN = 60


def run_date():
    return datetime.date.today().strftime("%Y%m%d")


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def training_pairs():
    pairs_df = pd.read_csv(newest(RANGE_RESULTS_GLOB))
    return pairs_df[pairs_df.is_scored.astype(bool)]


def wilson(successes, n):
    if n == 0:
        return np.nan, np.nan
    share = successes / n
    centre = (share + WILSON_Z ** 2 / (2 * n)) / (1 + WILSON_Z ** 2 / n)
    half_width = WILSON_Z * np.sqrt(share * (1 - share) / n + WILSON_Z ** 2 / (4 * n ** 2)) / (1 + WILSON_Z ** 2 / n)
    return centre - half_width, centre + half_width


def distance_to_range(r5_min, low, high):
    return np.where(r5_min < low, r5_min - low, np.where(r5_min > high, r5_min - high, 0.0))


def label_of(minutes, low, high):
    distance = distance_to_range(minutes, low, high)
    return np.where(distance > 0, "late", np.where(distance < 0, "early", "agree"))


def hard_counts(model_min, low, high):
    """Per-cut lost / false reach as transit_hard_miss_range.hard_tests (k = 2 range, plain cuts): {test: (k, n, upper)}."""
    results = {}
    for cut_min in CUTS_MIN.values():
        is_r5_below = model_min <= cut_min
        is_low_below, is_high_below = low <= cut_min, high <= cut_min
        is_google_below = np.where(is_low_below != is_high_below, is_r5_below, is_high_below)
        for kind, low_min, high_min in [("lost", cut_min - HARD_WINDOW_FAR_MIN, cut_min - HARD_WINDOW_NEAR_MIN),
                                        ("false", cut_min + HARD_WINDOW_NEAR_MIN, cut_min + HARD_WINDOW_FAR_MIN)]:
            is_window = (high >= low_min) & (high <= high_min)
            k, n = int((is_window & (is_r5_below != is_google_below)).sum()), int(is_window.sum())
            results[f"{kind} {cut_min}"] = (k, n, wilson(k, n)[1])
    return results


def band_of(minutes):
    return np.where(minutes <= CUTS_MIN[1], 1, np.where(minutes <= CUTS_MIN[2], 2, 3))


def zone_lines(google, model, errors, rng):
    """TRN-13 zone measures on Google's rounded minutes (transit_band_metric.zone_block, gating checks only)."""
    from scipy.stats import binomtest
    lines, failures = [], []
    for zone_no, cut_min in CUTS_MIN.items():
        low_min, high_min = ZONES_MIN[zone_no]
        in_zone = (google >= low_min) & (google <= high_min)
        g, r = google[in_zone], model[in_zone]
        both = int(((g <= cut_min) & (r <= cut_min)).sum())
        rec_n, prec_n = int((g <= cut_min).sum()), int((r <= cut_min).sum())
        rec_low, rec_high = wilson(both, rec_n)
        prec_low, prec_high = wilson(both, prec_n)
        sim_recall, sim_precision = [], []
        for _ in range(N_SIMULATIONS):
            sim = g + rng.choice(errors, size=len(g), replace=True)
            sim_both = ((g <= cut_min) & (sim <= cut_min)).sum()
            sim_recall.append(sim_both / rec_n if rec_n else np.nan)
            n_sim_below = (sim <= cut_min).sum()
            sim_precision.append(sim_both / n_sim_below if n_sim_below else np.nan)
        bar_recall, bar_precision = np.nanmedian(sim_recall), np.nanmedian(sim_precision)
        n_early = int(((r <= cut_min) & (g > cut_min)).sum())
        n_late = int(((r > cut_min) & (g <= cut_min)).sum())
        sign_p = binomtest(n_early, n_early + n_late, 0.5).pvalue if n_early + n_late else 1.0
        gap = abs(both / rec_n - both / prec_n)
        checks = {"floor": rec_low > FLOOR and prec_low > FLOOR,
                  "noise bar": rec_high >= bar_recall and prec_high >= bar_precision,
                  "balance": sign_p >= SIGN_TEST_ALPHA and gap <= CLOSE_TOLERANCE}
        failures += [f"z{zone_no} {name}" for name, is_pass in checks.items() if not is_pass]
        lines.append(f"    zone {zone_no} (n {int(in_zone.sum())}): recall {both / rec_n:.3f} ({rec_low:.3f}-{rec_high:.3f}), precision "
                     f"{both / prec_n:.3f} ({prec_low:.3f}-{prec_high:.3f}); bar {bar_recall:.3f}/{bar_precision:.3f}; misses early "
                     f"{n_early} / late {n_late} (p {sign_p:.3f}), gap {gap:.3f}; "
                     + ", ".join(f"{name} {'pass' if is_pass else 'FAIL'}" for name, is_pass in checks.items()))
    return lines, failures


def rounded_min(seconds):
    """Seconds to the nearest whole minute, half up (patch 1's T3; SCR-10); NaN (over max_time) -> inf."""
    return np.floor(np.nan_to_num(np.asarray(seconds, dtype=float), nan=np.inf, posinf=np.inf) / SECONDS_PER_MIN + 0.5)


def model_lines(label, minutes, seconds, df, google_s, is_random, base_hard=None):
    """Run 3's measures for one model, with medians beside means; returns (lines, hard counts, total, largest gain)."""
    low, high, google = df.low_2.to_numpy(), df.default_min.to_numpy(), df.google_min.to_numpy()
    finite = np.isfinite(minutes)
    distance = distance_to_range(minutes, low, high)[finite]
    labels = pd.Series(label_of(minutes, low, high)).value_counts().reindex(LABELS, fill_value=0).to_dict()
    hard = hard_counts(minutes[is_random], low[is_random], high[is_random])
    total = sum(k for k, _, _ in hard.values())
    gain = 0 if base_hard is None else max(hard[test][0] - base_hard[test][0] for test in hard)
    away = finite & np.logical_or.reduce([(google >= a) & (google <= b) for a, b in AWAY_RANGES_MIN])
    errors = (minutes - google)[away]
    is_walk_default = df.default_walk_only.astype(bool).to_numpy()
    walk_error = (minutes - high)[is_walk_default & finite]
    ratios = [((minutes[is_random] <= cut).sum() / (google[is_random] <= cut).sum()) for cut in CUTS_MIN.values()]
    zone_text, zone_failures = zone_lines(google, minutes, errors - np.median(errors), np.random.default_rng(SIMULATION_SEED))
    lines = ["", f"{label}:",
             f"  labels {labels}; error to range median {np.median(distance):+.1f}, mean {distance.mean():+.2f}",
             "  hard: " + "; ".join(f"{test} {k}/{n} (upper {upper:.3f}{' FAIL' if upper > HARD_MISS_MAX else ''})"
                                    for test, (k, n, upper) in hard.items()) + f"; total {total} (largest gain {gain:+d})",
             f"  off-cut error vs Google rounded (n {len(errors)}): median {np.median(errors):+.1f}, mean {errors.mean():+.2f}; "
             f"count ratio <= 10 {ratios[0]:.3f}, <= 20 {ratios[1]:.3f}"
             + "".join(" FAIL" if not COUNT_RATIO_RANGE[0] <= ratio <= COUNT_RATIO_RANGE[1] else "" for ratio in ratios),
             f"  walk-only defaults (n {len(walk_error)}): error median {np.median(walk_error):+.0f}, mean {walk_error.mean():+.2f}, "
             f"exact {np.mean(walk_error == 0):.3f}"]
    lines += zone_text
    lines.append(f"  zone failures: {', '.join(zone_failures) if zone_failures else 'none'}")
    sec_err = pd.DataFrame({"err_s": np.where(np.isfinite(seconds), seconds, np.nan) - google_s,
                            "group": df.boardings.to_numpy()}).dropna()
    g = sec_err.groupby("group").err_s
    sec_table = pd.DataFrame({"n": g.size(), "median_s": g.median(), "mean_s": g.mean(),
                              "median_abs_s": g.apply(lambda x: x.abs().median()),
                              "mean_abs_s": g.apply(lambda x: x.abs().mean())})
    sec_table.loc["all"] = [len(sec_err), sec_err.err_s.median(), sec_err.err_s.mean(), sec_err.err_s.abs().median(),
                            sec_err.err_s.abs().mean()]
    lines.append(f"  seconds error vs Google {GOOGLE_COL} by Google default's boardings:\n" + sec_table.round(1).to_string())
    return lines, hard, total, gain


def reading_of(hard, base_hard):
    total, base_total = sum(k for k, _, _ in hard.values()), sum(k for k, _, _ in base_hard.values())
    gain = max(hard[test][0] - base_hard[test][0] for test in hard)
    reading = ("IMPROVES" if total < base_total and gain <= SNAP_TOLERANCE_MISSES
               else "WORSENS" if total > base_total else "MIXED")
    return total, base_total, gain, reading


def charged_seconds(transit_s, walk_s, walk_call_s, s):
    return np.fmin(transit_s + (s - 1) * walk_s, walk_call_s)


def score():
    pairs_df = training_pairs().set_index("draw_no").sort_index()
    record_df = pd.concat([pd.read_csv(newest(RECORD_ROUTES_GLOB.format(release=r))) for r in RELEASES]
                          ).set_index("draw_no").sort_index()
    legs_paths = [newest(LEGS_GLOB.format(release=r)) for r in RELEASES]
    legs_df = pd.concat([pd.read_csv(p) for p in legs_paths]).drop_duplicates("draw_no", keep="last").set_index("draw_no")
    assert list(record_df.index) == list(pairs_df.index), "model of record's routes != training pairs"
    n = len(pairs_df)
    lines = [f"{NAME} {run_date()} score: {n} training pairs ({pairs_df.set_name.value_counts().to_dict()})",
             f"model of record: {', '.join(newest(RECORD_ROUTES_GLOB.format(release=r)).name for r in RELEASES)}",
             f"legs: {', '.join(p.name for p in legs_paths)}"]

    legs_df = legs_df.reindex(pairs_df.index)
    lines.append(f"pairs with a leg row: {int(legs_df.ttm_s.notna().sum() + (legs_df.n_templates == STREET_ONLY).sum())} "
                 f"of {n} (transit seconds present on the record: {int(record_df.transit.notna().sum())})")
    both = record_df.transit.notna() & legs_df.ttm_s.notna()
    off_f1 = int((record_df.transit[both] != legs_df.ttm_s[both]).sum())
    record_only = int((record_df.transit.notna() & legs_df.ttm_s.isna() & (legs_df.n_templates != STREET_ONLY)).sum())
    is_f1 = off_f1 == 0 and record_only == 0
    lines.append(f"(F1) leg ttm_s = record transit seconds: {'PASS' if is_f1 else 'FAIL'} ({off_f1} of {int(both.sum())} "
                 f"off; {record_only} record pairs without legs)")
    if not is_f1:
        print("\n".join(lines))
        raise SystemExit("F1 failed: stop")

    is_boarded = (legs_df.n_templates != STREET_ONLY) & (legs_df.n_boardings.fillna(0) >= 1)
    walk_s = np.where(is_boarded, legs_df[WALK_LEGS].fillna(0).sum(axis=1), 0.0)
    transit_s = record_df.transit.fillna(np.inf).to_numpy()
    walk_call_s = record_df.walk.fillna(np.inf).to_numpy()

    google_df = pd.concat([pd.read_csv(path).assign(set_name=name) for name, path in GOOGLE_ROUTES_PATHS.items()])
    google_df = google_df[google_df.is_default.astype(bool)].set_index(["set_name", "draw_no"])
    keys = list(zip(pairs_df.set_name, pairs_df.index))
    google_s = google_df[GOOGLE_COL].reindex(keys).to_numpy(dtype=float)
    steps = google_df.n_transit_steps.reindex(keys).to_numpy(dtype=float)
    df = pairs_df.reset_index().assign(boardings=[BOARDING_GROUPS[min(int(x), 2)] if np.isfinite(x) else np.nan for x in steps])
    low, high = df.low_2.to_numpy(), df.default_min.to_numpy()
    is_random = (df.set_name != TOPUP_SET).to_numpy()
    in_set = {name: (df.set_name == name).to_numpy() for name in [PICK_SET, CHECK_SET]}

    base_s = charged_seconds(transit_s, walk_s, walk_call_s, BASE_S)
    base_min = rounded_min(base_s)
    saved = pd.read_csv(newest(RECORD_SCORED_GLOB)).set_index("draw_no").reindex(pairs_df.index)
    off_f2 = int((base_min != saved.p2orig_min.to_numpy(dtype=float)).sum())
    base_total = sum(k for k, _, _ in hard_counts(base_min[is_random], low[is_random], high[is_random]).values())
    is_f2 = off_f2 == 0
    lines.append(f"(F2) s = 1 reproduces the record's minutes: {'PASS' if is_f2 else 'FAIL'} ({off_f2} pairs off); "
                 f"hard-miss total {base_total}")
    if not is_f2:
        print("\n".join(lines))
        raise SystemExit("F2 failed: stop")
    lines.append(f"charged walk (s), boarded pairs: n {int(is_boarded.sum())}, median {np.median(walk_s[is_boarded]):.0f}, "
                 f"mean {walk_s[is_boarded].mean():.0f}")

    curve = []
    for s in S_GRID:
        minutes = rounded_min(charged_seconds(transit_s, walk_s, walk_call_s, s))
        row = {"s": s}
        for scope, mask in [("pick", in_set[PICK_SET]), ("check", in_set[CHECK_SET]), ("pooled", is_random)]:
            hard = hard_counts(minutes[mask], low[mask], high[mask])
            row.update({f"{scope}_{test}": k for test, (k, _, _) in hard.items()})
            row[f"{scope}_total"] = sum(k for k, _, _ in hard.values())
        distance = distance_to_range(minutes, low, high)[np.isfinite(minutes)]
        row["error_to_range_median"], row["error_to_range_mean"] = np.median(distance), distance.mean()
        row["band_calls_changed"] = int((band_of(minutes) != band_of(base_min)).sum())
        curve.append(row)
    curve_df = pd.DataFrame(curve)
    s_star = float(curve_df.loc[curve_df.pick_total.idxmin(), "s"])   # idxmin takes the first: ties to the smallest s
    lines += ["", "curve (hard-miss counts by scope; error to range in min):", curve_df.round(3).to_string(index=False)]

    star_s = charged_seconds(transit_s, walk_s, walk_call_s, s_star)
    star_min = rounded_min(star_s)
    verdicts = {}
    for scope, mask in [("V1 second batch", in_set[CHECK_SET]), ("V2 pooled random", is_random)]:
        hard = hard_counts(star_min[mask], low[mask], high[mask])
        base_hard = hard_counts(base_min[mask], low[mask], high[mask])
        verdicts[scope] = reading_of(hard, base_hard)
    is_pass = verdicts["V2 pooled random"][3] == "IMPROVES" and verdicts["V1 second batch"][3] != "WORSENS"

    record_text, record_hard, _, _ = model_lines("model of record (s = 1)", base_min, base_s, df, google_s, is_random)
    star_text, _, _, _ = model_lines(f"walk charge s* = {s_star:.2f}", star_min, star_s, df, google_s, is_random, record_hard)
    is_base_transit, is_star_transit = transit_s < walk_call_s, transit_s + (s_star - 1) * walk_s < walk_call_s
    lines += record_text + star_text
    lines += ["", f"at s* vs s = 1: minutes changed on {int((star_min != base_min).sum())} pairs; band calls changed "
                  f"{int((band_of(star_min) != band_of(base_min)).sum())}; winner flips transit -> walk "
                  f"{int((is_base_transit & ~is_star_transit).sum())}"]
    topup = ~is_random
    topup_err = distance_to_range(star_min[topup], low[topup], high[topup]), distance_to_range(base_min[topup], low[topup], high[topup])
    lines.append(f"top-up (report only, n {int(topup.sum())}): error to range mean {topup_err[1].mean():+.2f} -> "
                 f"{topup_err[0].mean():+.2f}; labels {pd.Series(label_of(base_min[topup], low[topup], high[topup])).value_counts().to_dict()}"
                 f" -> {pd.Series(label_of(star_min[topup], low[topup], high[topup])).value_counts().to_dict()}")
    lines += ["", f"PICK: s* = {s_star:.2f} (lowest training-half total, ties to the smallest s)"]
    lines += [f"{scope}: hard misses {total} vs record {base} (largest gain {gain:+d}) -> {reading}"
              for scope, (total, base, gain, reading) in verdicts.items()]
    lines.append(f"READING: {'PASS' if is_pass else 'FAIL'} (V2 IMPROVES and V1 not WORSENS)")

    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    curve_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_curve.csv", index=False)


if __name__ == "__main__":
    {"score": score}[sys.argv[1]](*sys.argv[2:])
