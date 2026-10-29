"""Which tag-imputation rule predicts a venue's open share best at the subject's 30-min slots?

Claim: scoring (SCR-13) gives every venue without its own pulled hours an open share per slot and day type, imputed
from its Google tags (VEN-13; functions/hours_imputation.py, scoring.build_venue_open_shares). VEN-13's backoff was
validated for the drive time-of-day factor (weekday hours, averaged; diagnostics/venue_hours_imputation.py). At slot
level open shares are near 0 or 1, and the 90th session found its trust test (a tag group is confident when its
spread beats random groups) fails there: spread is p(1 - p), set by the mean, so groups far from 0.5 pass and groups
that differ from the average but sit near 0.5 fail (pulled cafes are 0.32 open at Fri 19:30, imputed 0.73).

Rules compared, leave-one-out over the pulled venues (each venue's own hours held out of every group and the pooled
mean), at the subject's 42 slots (config.REACH_SUBJECT_WINDOWS, copied below):
  pooled     the pooled mean (no tags);
  spread     VEN-13 as built: backoff, confident = spread below random groups' (one-sided, ALPHA);
  mean_test  (a) same backoff, confident = |group mean - pooled| above random groups' of the same size (ALPHA);
             among confident groups of one size, the largest; ties across 0.5 back off, as VEN-13;
  shrink     (b) partial pooling along a chain: pooled, then the venue's tag with the most pulled venues, then that
             set plus the tag that keeps the most, ...; each step e_k = (n_k mean_k + M e_(k-1)) / (n_k + M); M picked
             on a grid by this same leave-one-out score (one parameter, slight optimism; reported per M).
Truth: the held-out venue's own open share (share of the day type's days open at the slot start).
Rule (written before the run, user 2026-10-23, 90th): the lowest Brier score (mean squared error over venue x slot)
wins; calibration table, backoff depth and a venue-bootstrap CI of each difference to the winner shown beside it.

Self-contained (CLAUDE.md D1): imports nothing from functions/, config.py or pipeline modules. No API.

Conclusion (run 2026-10-23, 1,612 venues x 42 slots): shrink wins by the rule. Brier: all open 0.314, pooled 0.204,
spread (VEN-13 as built) 0.185, mean_test 0.170, shrink 0.168 at M = 5 (M 2-10 within 0.001; 1 and 20+ worse).
Differences to shrink (venue bootstrap 95% CI): spread +0.017 (+0.013 to +0.020), mean_test +0.0015 (-0.0004 to
+0.0036: a near tie), pooled +0.036. Spread backs off to the pooled mean in 66% of venue-slots, mean_test 59%.
Shrink is the best calibrated in the middle bins (0.3-0.8 predicted -> 0.42-0.79 observed); every rule under-predicts
at the low end (0-0.1 -> 0.11-0.18 observed). Tags help most at weekday and Friday dinner (Brier 0.12-0.13 vs pooled
0.17) and hardly at weekend lunch (0.18-0.22 vs 0.19-0.23): cuisine tags don't say which restaurants skip lunch.
First run had a bug (training venues' tags cut to their first 10, so groups missed members); fixed, same verdict.
"""
import datetime
import itertools
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# --- paths ------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENUES_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"
HOURS_PULL_DIRS = [PROJECT_ROOT / "frozen_inputs" / "places_enterprise_hours_20260902",
                   PROJECT_ROOT / "outputs" / "places_enterprise_hours" / "places_enterprise_hours_20261010"]
NAME = "venue_hours_slot_imputation"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
SUMMARY_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_summary.json"
CALIBRATION_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_calibration.csv"
LOG_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"
CALIBRATION_FIG_PATH = IMG_DIR / f"{NAME}_{RUN_DATE}_calibration.png"
HIST_FIG_PATH = IMG_DIR / f"{NAME}_{RUN_DATE}_histograms.png"

# --- copied (config.py, opening_hours / places_hours, 2026-10-23) ------------------------------------
SLOT_MIN = 30
MINUTES_PER_DAY = 1440
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY
TAG_SEPARATOR = "|"
OPERATIONAL_STATUS = "OPERATIONAL"
FIXED_RECORD_KEY = "is_fixed"
DAY_TYPES = {"Mon-Thu": [1, 2, 3, 4], "Fri": [5], "Sat": [6], "Sun": [0]}      # Google day index, 0 = Sunday
SUBJECT_WINDOWS = {"Mon-Thu": [("17:30", "21:00")], "Fri": [("17:30", "21:30")],
                   "Sat": [("12:30", "15:00"), ("17:00", "21:30")], "Sun": [("12:30", "15:00"), ("17:00", "21:00")]}
MIN_GROUP = 3
ALPHA = 0.05
NULL_DRAWS = 500
MAX_TAGS = 10
OPEN_SIDE = 0.5
SEED = 20261012

# --- this diagnostic --------------------------------------------------------------------------------
SHRINK_M_GRID = [1, 2, 5, 10, 20, 50, 100]
N_BOOTSTRAP = 2000
CALIBRATION_BINS = np.linspace(0, 1, 11)
HIST_SLOTS = ["Mon-Thu_1900", "Fri_1930", "Sat_1300", "Sun_1300"]
HIST_BINS = np.linspace(0, 1, 21)
COLORS = {"truth": "#eb6834", "pooled": "#52514e", "spread": "#2a78d6", "mean_test": "#1baf7a", "shrink": "#6250d6"}
INK, MUTED = "#0b0b0b", "#52514e"


class Tee:
    def __init__(self):
        self.stdout, self.lines = sys.stdout, []

    def write(self, text):
        self.stdout.write(text)
        self.lines.append(text)

    def flush(self):
        self.stdout.flush()


# --- hours --------------------------------------------------------------------------------------------
def minute_of_week(point):
    return point["day"] * MINUTES_PER_DAY + point.get("hour", 0) * 60 + point.get("minute", 0)


def week_open(record):
    """Open flag per 30-min slot of the week (point-in-time rule); None if hours are missing or malformed."""
    periods = record.get("regularOpeningHours", {}).get("periods", [])
    if not periods:
        return None
    slots = np.arange(0, MINUTES_PER_WEEK, SLOT_MIN)
    if len(periods) == 1 and "close" not in periods[0]:
        point = periods[0].get("open", {})
        is_always = (point.get("day", 0), point.get("hour", 0), point.get("minute", 0)) == (0, 0, 0)
        return np.ones(len(slots), bool) if is_always else None
    is_open = np.zeros(len(slots), bool)
    for period in periods:
        if "open" not in period or "close" not in period:
            return None
        start, end = minute_of_week(period["open"]), minute_of_week(period["close"])
        if end <= start:
            end += MINUTES_PER_WEEK
        is_open |= (slots >= start) & (slots < end)
        if end > MINUTES_PER_WEEK:
            is_open |= slots < end - MINUTES_PER_WEEK
    return is_open


def subject_slots():
    """(label, day type, slot-of-day index) for every slot of the subject's windows."""
    out = []
    for day_type, windows in SUBJECT_WINDOWS.items():
        for start, end in windows:
            minute, end_min = (int(t[:2]) * 60 + int(t[3:]) for t in (start, end))
            while minute < end_min:
                out.append((f"{day_type}_{minute // 60:02d}{minute % 60:02d}", day_type, minute // SLOT_MIN))
                minute += SLOT_MIN
    return out


def load():
    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "types"]).drop_duplicates("place_id")
    tag_sets = [set(t.split(TAG_SEPARATOR)) - {""} for t in venues_df.types.fillna("")]
    universal = set.intersection(*tag_sets)
    tags_of = dict(zip(venues_df.place_id, [sorted(t - universal) for t in tag_sets]))   # full: membership
    records = {}
    for pull_dir in HOURS_PULL_DIRS:
        for path in pull_dir.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            place_id = record.get("id") or path.stem
            if place_id not in records or record.get("fetched_date", "") > records[place_id].get("fetched_date", ""):
                records[place_id] = record
    slots = subject_slots()
    ids, rows = [], []
    for place_id, record in records.items():
        if (place_id not in tags_of or record.get(FIXED_RECORD_KEY)
                or record.get("businessStatus", "") != OPERATIONAL_STATUS):
            continue
        is_open = week_open(record)
        if is_open is None:
            continue
        by_day = is_open.reshape(7, -1)
        rows.append([by_day[DAY_TYPES[day_type], k].mean() for _, day_type, k in slots])
        ids.append(place_id)
    return ids, [tags_of[i] for i in ids], np.array(rows), [label for label, _, _ in slots], universal


# --- rules --------------------------------------------------------------------------------------------
class Groups:
    """Per tag combination: member count, sum and sum of squares of open shares (for leave-one-out stats)."""

    def __init__(self, tag_lists, y):
        self.y = y
        vocab = set(itertools.chain.from_iterable(tag_lists))
        self.has_tag = {tag: np.array([tag in set(t) for t in tag_lists]) for tag in vocab}
        self.cache = {}

    def stats(self, subset):
        if subset not in self.cache:
            members = np.logical_and.reduce([self.has_tag[t] for t in subset])
            ym = self.y[members]
            self.cache[subset] = (int(members.sum()), ym.sum(axis=0), (ym ** 2).sum(axis=0))
        return self.cache[subset]

    def loo(self, subset, yv):
        """Group stats with the held-out venue (a member: every subset is of its own tags) removed."""
        n, total, total_sq = self.stats(subset)
        n -= 1
        if n < 1:
            return 0, None, None
        mean = (total - yv) / n
        return n, mean, np.maximum((total_sq - yv ** 2) / n - mean ** 2, 0.0)


class Null:
    """Random groups of the training venues, per size: spread and |mean - pooled| per slot."""

    def __init__(self, y, rng):
        self.y, self.rng, self.pooled, self.cache = y, rng, y.mean(axis=0), {}

    def __call__(self, size):
        if size not in self.cache:
            draws = [self.y[self.rng.choice(len(self.y), size, replace=False)] for _ in range(NULL_DRAWS)]
            self.cache[size] = (np.vstack([d.var(axis=0) for d in draws]),
                                np.vstack([np.abs(d.mean(axis=0) - self.pooled) for d in draws]))
        return self.cache[size]


def backoff(tags, yv, pooled, groups, null, test):
    """VEN-13 backoff with the given confidence test ('spread' or 'mean_test'); (prediction, depth) per slot."""
    tags = tags[:MAX_TAGS]                                          # subsets of the first MAX_TAGS tags only
    pred, depth = pooled.copy(), np.zeros(len(pooled), int)
    unresolved = np.ones(len(pooled), bool)
    for size in range(len(tags), 0, -1):
        cands = []
        for subset in itertools.combinations(tags, size):
            n, mean, spread = groups.loo(subset, yv)
            if n < MIN_GROUP:
                continue
            null_spread, null_gap = null(n)
            if test == "spread":
                confident = (null_spread <= spread).mean(axis=0) < ALPHA
                rank_key = spread                                   # lowest spread wins
            else:
                confident = (null_gap >= np.abs(mean - pooled)).mean(axis=0) < ALPHA
                rank_key = np.full(len(pooled), -n, float)          # largest group wins
            cands.append((mean, rank_key, confident))
        if not cands:
            continue
        means, keys, confs = (np.array(x) for x in zip(*cands))
        for col in np.flatnonzero(unresolved):
            ok = confs[:, col]
            if not ok.any():
                continue
            sides = means[ok, col] > OPEN_SIDE
            if sides.any() and not sides.all():
                continue                                            # tie across 0.5: back off one size
            best = np.flatnonzero(ok)[np.argmin(keys[ok, col])]
            pred[col], depth[col] = means[best, col], size
            unresolved[col] = False
        if not unresolved.any():
            break
    return pred, depth


def shrink_chain(tags, yv, groups):
    """Greedy chain of growing tag sets (most pulled venues kept at each step): [(n, loo mean), ...]."""
    chain, current, left = [], (), list(tags[:MAX_TAGS])
    while left:
        options = []
        for tag in left:
            subset = tuple(sorted(current + (tag,)))
            n, mean, _ = groups.loo(subset, yv)
            if n >= 1:
                options.append((n, tag, subset, mean))
        if not options:
            break
        n, tag, current, mean = max(options, key=lambda o: o[0])
        chain.append((n, mean))
        left.remove(tag)
    return chain


def shrink(chain, pooled, m):
    estimate = pooled.copy()
    for n, mean in chain:
        estimate = (n * mean + m * estimate) / (n + m)
    return estimate


# --- run ------------------------------------------------------------------------------------------------
def main():
    tee = Tee()
    sys.stdout = tee
    ids, tag_lists, y, labels, universal = load()
    n_venues, n_slots = y.shape
    print(f"{NAME} run {RUN_DATE}: {n_venues} pulled venues (operational, readable hours, not fixed), {n_slots} slots; "
          f"universal tags dropped {sorted(universal)}")
    groups, null = Groups(tag_lists, y), Null(y, np.random.default_rng(SEED))
    total = y.sum(axis=0)
    preds = {name: np.empty_like(y) for name in ["pooled", "spread", "mean_test"]}
    depths = {name: np.empty(y.shape, int) for name in ["spread", "mean_test"]}
    shrink_preds = {m: np.empty_like(y) for m in SHRINK_M_GRID}
    for v in range(n_venues):
        pooled = (total - y[v]) / (n_venues - 1)
        preds["pooled"][v] = pooled
        for test in ["spread", "mean_test"]:
            preds[test][v], depths[test][v] = backoff(tag_lists[v], y[v], pooled, groups, null, test)
        chain = shrink_chain(tag_lists[v], y[v], groups)
        for m in SHRINK_M_GRID:
            shrink_preds[m][v] = shrink(chain, pooled, m)
        if (v + 1) % 400 == 0:
            print(f"  {v + 1} / {n_venues} venues", flush=True)

    venue_sq = lambda pred: ((pred - y) ** 2).mean(axis=1)                       # noqa: E731
    shrink_brier = {m: venue_sq(p).mean() for m, p in shrink_preds.items()}
    print("shrink, Brier per M: " + ", ".join(f"{m}: {b:.4f}" for m, b in shrink_brier.items()))
    best_m = min(shrink_brier, key=shrink_brier.get)
    preds["shrink"] = shrink_preds[best_m]
    preds_all_open = np.ones_like(y)
    briers = {name: venue_sq(p).mean() for name, p in preds.items()}
    briers["all_open"] = venue_sq(preds_all_open).mean()
    winner = min((n for n in preds), key=briers.get)
    rng = np.random.default_rng(SEED)
    boot_idx = rng.integers(0, n_venues, (N_BOOTSTRAP, n_venues))
    print(f"\nBrier (mean over venue x slot; lower is better), shrink at M = {best_m}:")
    ci = {}
    for name in ["all_open", "pooled", "spread", "mean_test", "shrink"]:
        diff = venue_sq(preds_all_open if name == "all_open" else preds[name]) - venue_sq(preds[winner])
        low, high = np.percentile(diff[boot_idx].mean(axis=1), (2.5, 97.5))
        ci[name] = (diff.mean(), low, high)
        print(f"  {name:10s} {briers[name]:.4f}   vs {winner}: {diff.mean():+.4f} (CI {low:+.4f} to {high:+.4f})")
    print(f"winner by the rule: {winner}")

    print("\nbackoff depth (share of venue-slots; 0 = pooled mean):")
    for name in ["spread", "mean_test"]:
        share = pd.Series(depths[name].ravel()).value_counts(normalize=True).sort_index()
        print(f"  {name:10s} " + ", ".join(f"{k}: {s:.1%}" for k, s in share.items()))

    print("\ncalibration (predicted bin -> mean observed open share, venue-slots):")
    cal_rows = []
    for name in ["pooled", "spread", "mean_test", "shrink"]:
        bins = np.clip(np.digitize(preds[name].ravel(), CALIBRATION_BINS) - 1, 0, len(CALIBRATION_BINS) - 2)
        for b in range(len(CALIBRATION_BINS) - 1):
            mask = bins == b
            if mask.any():
                cal_rows.append({"rule": name, "bin_low": CALIBRATION_BINS[b], "bin_high": CALIBRATION_BINS[b + 1],
                                 "n": int(mask.sum()), "mean_pred": preds[name].ravel()[mask].mean(),
                                 "mean_obs": y.ravel()[mask].mean()})
    cal_df = pd.DataFrame(cal_rows)
    print(cal_df.pivot_table(index=["bin_low"], columns="rule", values=["mean_obs", "n"]).round(2).to_string())

    print("\nper slot Brier:")
    slot_df = pd.DataFrame({name: ((p - y) ** 2).mean(axis=0) for name, p in preds.items()}, index=labels)
    print(slot_df.round(3).to_string())

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    cal_df.to_csv(CALIBRATION_PATH, index=False)
    summary = {"run_date": RUN_DATE, "n_venues": n_venues, "n_slots": n_slots, "brier": briers, "winner": winner,
               "shrink_m": best_m, "shrink_brier_per_m": shrink_brier,
               "diff_to_winner_ci": {k: list(v) for k, v in ci.items()}}
    SUMMARY_PATH.write_text(json.dumps(summary, indent=1), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(5.2, 5))
    ax.plot([0, 1], [0, 1], color=MUTED, linewidth=1, linestyle=":")
    for name in ["pooled", "spread", "mean_test", "shrink"]:
        d = cal_df[cal_df.rule == name]
        ax.plot(d.mean_pred, d.mean_obs, marker="o", markersize=5, linewidth=2, color=COLORS[name],
                label=f"{name} (Brier {briers[name]:.3f})")
    ax.set_xlabel("predicted open share (leave-one-out)", color=MUTED)
    ax.set_ylabel("observed open share", color=MUTED)
    ax.set_title("Calibration at the subject's 42 slots", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(CALIBRATION_FIG_PATH, dpi=130)

    rules = ["spread", "mean_test", "shrink"]
    fig, axes = plt.subplots(len(rules), len(HIST_SLOTS), figsize=(14, 8), sharex=True, sharey=True)
    for i, name in enumerate(rules):
        for j, slot in enumerate(HIST_SLOTS):
            ax, col = axes[i, j], labels.index(slot)
            weights = np.full(n_venues, 1 / n_venues)
            ax.hist(preds[name][:, col], bins=HIST_BINS, weights=weights, color=COLORS[name], rwidth=0.85,
                    label=f"{name} (imputed, held out)")
            ax.hist(y[:, col], bins=HIST_BINS, weights=weights, histtype="step", linewidth=2, color=COLORS["truth"],
                    label="own hours (truth)")
            ax.axvline(preds["pooled"][:, col].mean(), color=INK, linestyle="--", linewidth=1, label="pooled mean")
            if i == 0:
                ax.set_title(slot.replace("_", " "), color=INK, fontsize=10)
            if j == 0:
                ax.set_ylabel("share of venues", color=MUTED)
                ax.legend(frameon=False, fontsize=7, loc="upper left")
            if i == len(rules) - 1:
                ax.set_xlabel("open share", color=MUTED)
            for spine in ("top", "right"):
                ax.spines[spine].set_visible(False)
    fig.suptitle("Imputed open share per pulled venue (leave-one-out) vs its own hours", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(HIST_FIG_PATH, dpi=130)
    print(f"\nsaved {SUMMARY_PATH.name}, {CALIBRATION_PATH.name}, {CALIBRATION_FIG_PATH.name}, {HIST_FIG_PATH.name}")
    sys.stdout = tee.stdout
    LOG_PATH.write_text("".join(tee.lines), encoding="utf-8")


if __name__ == "__main__":
    main()
