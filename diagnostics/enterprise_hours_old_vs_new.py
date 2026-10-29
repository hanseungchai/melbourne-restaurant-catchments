"""Does the 2026-10-10 Places Enterprise pull give the same opening-hours histogram as the 2026-09-02 pull?

Claim under test: the weekday open-share histogram from the 2026-09-02 pull (900 venues, a sample
that barely covers the outer ring) describes the venue table's hours; a fresh uniform draw of 900
venues from the expanded venue table (pulled 2026-10-10, seed 20261010) gives the same shares.
Where the pipeline relies on it: the hours histogram (opening_hours.build_opening_hours,
outputs/opening_hours/), used for departure-time weights (DESIGN_pre_spine "Opening hours"); the choice
between replacing it with the new pull or pooling both.

Comparisons (each statistic: weekday mean open share at the checkpoint slots, weekday median last
close; 95% venue bootstrap intervals, B = BOOTSTRAP_DRAWS):
- raw: old pull vs new pull, as sampled;
- old reweighted: old venues weighted so their ring mix (run_id in the venue table) matches the new
  draw's; separates ring composition from a change in hours;
- by ring: old vs new within each ring;
- overlap: venues in both pulls, included in both: share with identical regularOpeningHours
  periods and slot-level agreement (the baseline churn of hours over 38 days).
A difference "DIFFERS" when its 95% interval (new minus old, independent resamples) excludes 0.
First run (2026-10-10): descriptive, no pre-set verdict rule.

Conclusion (run 2026-10-10; 814 old vs 845 new included venues): AGREE. Raw, every interval holds
0: 12:00 old 0.731 vs new 0.707 (diff -0.025, -0.065 to 0.015), 15:30 0.547 vs 0.546, 19:00 0.663
vs 0.688, 22:00 0.230 vs 0.198 (-0.068 to 0.005), median close 21.0 vs 21.0. Old reweighted to the
new ring mix: also AGREE on all five. Whole weekday curve: mean |diff| 0.018, largest 0.048 at
16:30 (the one slot whose band just excludes 0, chance-level over 48 slots). By ring, 1 of 15
DIFFERS (old_legacy 19:00, 0.645 -> 0.718), chance-level; outer ring has only 39 old venues.
Overlap: 43 venues in both pulls, all 43 with identical periods (1 status change); the 38
included in both agree on every slot, so hours did not churn in 38 days and the gaps above are
sampling. Decision (user, 2026-10-10): the new pull REPLACES the old as the histogram source; it
is a proportional draw across rings, so it needs no weights, which pooling would. Outputs already
built downstream from the old histogram (e.g. the 2026-09-30 OD draws' departure times) stay
valid: the new hours match the old within the 95% intervals.

Inputs (saved data only; no API calls):
- frozen_inputs/places_enterprise_hours_20260902/: the old pull.
- outputs/places_enterprise_hours/places_enterprise_hours_20261010/: the new pull (fixed venues,
  is_fixed true, left out), and its draw list.
- outputs/legacy_rebuilds/venues/venues_20260925_expanded.csv: venue table, for each venue's ring.

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). The opening-hours
rules below are copies of opening_hours.py's.
"""
import datetime
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths and run naming
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OLD_HOURS_DIR = PROJECT_ROOT / "frozen_inputs" / "places_enterprise_hours_20260902"
NEW_HOURS_DIR = (PROJECT_ROOT / "outputs" / "places_enterprise_hours"
                 / "places_enterprise_hours_20261010")
VENUE_TABLE_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"
DIAGNOSTICS_DIR = PROJECT_ROOT / "diagnostics"
DIAGNOSTIC_DATA_DIR = DIAGNOSTICS_DIR / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = DIAGNOSTICS_DIR / "diagnostic_img"

DIAGNOSTIC_NAME = "enterprise_hours_old_vs_new"
RUN_PREFIX = f"{DIAGNOSTIC_NAME}_{datetime.date.today():%Y%m%d}"  # one run per day (D1)
SUMMARY_PATH = DIAGNOSTIC_DATA_DIR / f"{RUN_PREFIX}_summary.csv"
CURVES_PATH = DIAGNOSTIC_DATA_DIR / f"{RUN_PREFIX}_weekday_curves.csv"
FIGURE_PATH = DIAGNOSTIC_IMG_DIR / f"{RUN_PREFIX}_histogram.png"

OLD_LABEL = "2026-09-02"
NEW_LABEL = "2026-10-10"

# ---------------------------------------------------------------------------
# Check parameters
# ---------------------------------------------------------------------------
SLOT_MIN = 30
CHECKPOINT_SLOTS = ["12:00", "15:30", "19:00", "22:00"]
MEDIAN_CLOSE_STAT = "median_close"        # weekday median last close, hours after midnight
BOOTSTRAP_DRAWS = 2_000
BOOTSTRAP_SEED = 20261010
INTERVAL_PERCENTILES = [2.5, 97.5]
RING_COL = "run_id"
NOT_IN_TABLE_RING = "not_in_table"        # old-pull venue no longer in the venue table
ALL_RINGS = "all"

# Figure
OLD_COLOR = "#2a78d6"                     # categorical slot 1 (blue)
NEW_COLOR = "#eb6834"                     # categorical slot 2 (orange)
BAND_ALPHA = 0.2
LINE_WIDTH = 2
FIGURE_SIZE_IN = (11, 10)
FIGURE_DPI = 150

# ---------------------------------------------------------------------------
# Opening-hours rules (copies of opening_hours.py's)
# ---------------------------------------------------------------------------
MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR
DAYS_PER_WEEK = 7
MINUTES_PER_WEEK = DAYS_PER_WEEK * MINUTES_PER_DAY
DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]  # Google periods: day 0 = Sunday
FIRST_WEEKDAY, LAST_WEEKDAY = 1, 5
OPERATIONAL_STATUS = "OPERATIONAL"
FLAG_OK, FLAG_24H, FLAG_NO_HOURS, FLAG_MALFORMED = "ok", "24h", "no_hours", "malformed"
INCLUDED_FLAGS = (FLAG_OK, FLAG_24H)
SLOTS_PER_DAY = MINUTES_PER_DAY // SLOT_MIN
SLOT_STARTS_MIN = np.arange(0, MINUTES_PER_WEEK, SLOT_MIN)


def load_records(src_dir, should_drop_fixed):
    """One record per place id (latest fetched_date wins); fixed venues dropped if asked."""
    records = {}
    for path in src_dir.glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if should_drop_fixed and record.get("is_fixed"):
            continue
        place_id = record.get("id") or path.stem
        if place_id not in records or record.get("fetched_date", "") > records[place_id].get("fetched_date", ""):
            records[place_id] = record
    return records


def minute_of_week(point):
    return point["day"] * MINUTES_PER_DAY + point.get("hour", 0) * MINUTES_PER_HOUR + point.get("minute", 0)


def venue_intervals(record):
    """regularOpeningHours -> ([(start, end)], flag); end exclusive, minutes of week."""
    periods = record.get("regularOpeningHours", {}).get("periods", [])
    if not periods:
        return [], FLAG_NO_HOURS
    if len(periods) == 1 and "close" not in periods[0]:
        open_point = periods[0].get("open", {})
        if (open_point.get("day", 0), open_point.get("hour", 0), open_point.get("minute", 0)) == (0, 0, 0):
            return [(0, MINUTES_PER_WEEK)], FLAG_24H
        return [], FLAG_MALFORMED
    intervals = []
    for period in periods:
        if "open" not in period or "close" not in period:
            return [], FLAG_MALFORMED
        start_min, end_min = minute_of_week(period["open"]), minute_of_week(period["close"])
        if end_min <= start_min:
            end_min += MINUTES_PER_WEEK
        intervals.append((start_min, end_min))
    return intervals, FLAG_OK


def venue_slots(intervals):
    """Point-in-time rule: open at slot t iff start <= t < end."""
    is_open = np.zeros(len(SLOT_STARTS_MIN), dtype=bool)
    for start_min, end_min in intervals:
        is_open |= (SLOT_STARTS_MIN >= start_min) & (SLOT_STARTS_MIN < end_min)
        if end_min > MINUTES_PER_WEEK:
            is_open |= SLOT_STARTS_MIN < (end_min - MINUTES_PER_WEEK)
    return is_open


def venue_weekday_closes(intervals):
    """Last close per weekday open-day, hours after that day's midnight."""
    last_close_h = {}
    for start_min, end_min in intervals:
        day = start_min // MINUTES_PER_DAY
        last_close_h[day] = max(last_close_h.get(day, 0.0), (end_min - day * MINUTES_PER_DAY) / MINUTES_PER_HOUR)
    return [close_h for day, close_h in last_close_h.items() if FIRST_WEEKDAY <= day <= LAST_WEEKDAY]


def score(records, ring_by_id):
    """Included venues only: ids, rings, week open matrix (venues x slots), weekday closes per venue."""
    place_ids, rings, open_rows, closes, status_rows = [], [], [], [], []
    for place_id, record in records.items():
        intervals, flag = venue_intervals(record)
        status = record.get("businessStatus", "")
        status_rows.append((status, flag))
        if status != OPERATIONAL_STATUS or flag not in INCLUDED_FLAGS:
            continue
        place_ids.append(place_id)
        rings.append(ring_by_id.get(place_id, NOT_IN_TABLE_RING))
        open_rows.append(venue_slots(intervals))
        closes.append(venue_weekday_closes(intervals) if flag == FLAG_OK else [])
    status_df = pd.DataFrame(status_rows, columns=["status", "flag"])
    return {"place_id": np.array(place_ids), "ring": np.array(rings), "open": np.vstack(open_rows),
            "closes": closes, "status_df": status_df}


def weekday_curve_matrix(open_matrix):
    """venues x slots-of-day: share of weekdays (Mon-Fri) the venue is open at that clock slot."""
    weekday_cols = [open_matrix[:, day * SLOTS_PER_DAY:(day + 1) * SLOTS_PER_DAY]
                    for day in range(FIRST_WEEKDAY, LAST_WEEKDAY + 1)]
    return np.mean(weekday_cols, axis=0)


def bootstrap_weights(n_venues, rng):
    """B x n multinomial resample counts (row b = how often each venue is drawn in resample b)."""
    return rng.multinomial(n_venues, np.full(n_venues, 1 / n_venues), size=BOOTSTRAP_DRAWS)


def weighted_median(values, weights):
    order = np.argsort(values)
    cum_weights = np.cumsum(weights[order])
    return values[order][np.searchsorted(cum_weights, cum_weights[-1] / 2)]


def sample_stats(sample, venue_weights, boot_counts):
    """Point value and bootstrap draws of each statistic; venue_weights reweight venues (ring mix)."""
    curve_matrix = weekday_curve_matrix(sample["open"])
    close_values = np.concatenate([np.asarray(c, dtype=float) for c in sample["closes"]])
    close_owner = np.concatenate([np.full(len(c), i) for i, c in enumerate(sample["closes"])]).astype(int)

    point_weights = venue_weights
    boot_weights = boot_counts * venue_weights                    # B x n
    point_curve = point_weights @ curve_matrix / point_weights.sum()
    boot_curves = boot_weights @ curve_matrix / boot_weights.sum(axis=1, keepdims=True)

    stats = {}
    slot_labels = [f"{minute // MINUTES_PER_HOUR:02d}:{minute % MINUTES_PER_HOUR:02d}"
                   for minute in SLOT_STARTS_MIN[:SLOTS_PER_DAY]]
    for slot in CHECKPOINT_SLOTS:
        col = slot_labels.index(slot)
        stats[slot] = (point_curve[col], boot_curves[:, col])
    point_close = weighted_median(close_values, point_weights[close_owner])
    boot_close = np.array([weighted_median(close_values, boot_weights[b, close_owner] + 0.0)
                           if boot_weights[b, close_owner].sum() > 0 else np.nan
                           for b in range(BOOTSTRAP_DRAWS)])
    stats[MEDIAN_CLOSE_STAT] = (point_close, boot_close)
    return stats, point_curve, boot_curves, slot_labels


def interval(draws):
    low, high = np.nanpercentile(draws, INTERVAL_PERCENTILES)
    return low, high


def compare_rows(comparison, ring, old_stats, new_stats, n_old, n_new):
    rows = []
    for stat in CHECKPOINT_SLOTS + [MEDIAN_CLOSE_STAT]:
        old_point, old_draws = old_stats[stat]
        new_point, new_draws = new_stats[stat]
        diff_low, diff_high = interval(new_draws - old_draws)
        rows.append({"comparison": comparison, "ring": ring, "stat": stat, "n_old": n_old, "n_new": n_new,
                     "old": old_point, "old_low": interval(old_draws)[0], "old_high": interval(old_draws)[1],
                     "new": new_point, "new_low": interval(new_draws)[0], "new_high": interval(new_draws)[1],
                     "diff": new_point - old_point, "diff_low": diff_low, "diff_high": diff_high,
                     "verdict": "AGREE" if diff_low <= 0 <= diff_high else "DIFFERS"})
    return rows


def subset(sample, mask):
    return {"place_id": sample["place_id"][mask], "ring": sample["ring"][mask], "open": sample["open"][mask],
            "closes": [c for c, keep in zip(sample["closes"], mask) if keep]}


def overlap_rows(old_records, new_records, old_sample, new_sample):
    """Venues in both pulls: identical periods, and slot agreement among those included in both."""
    shared_ids = sorted(set(old_records) & set(new_records))
    n_same_periods = sum(old_records[i].get("regularOpeningHours", {}).get("periods")
                         == new_records[i].get("regularOpeningHours", {}).get("periods") for i in shared_ids)
    old_index = {place_id: i for i, place_id in enumerate(old_sample["place_id"])}
    new_index = {place_id: i for i, place_id in enumerate(new_sample["place_id"])}
    both_ids = [i for i in shared_ids if i in old_index and i in new_index]
    old_open = old_sample["open"][[old_index[i] for i in both_ids]]
    new_open = new_sample["open"][[new_index[i] for i in both_ids]]
    n_status_changed = sum(old_records[i].get("businessStatus") != new_records[i].get("businessStatus")
                           for i in shared_ids)
    return {"n_shared": len(shared_ids), "n_identical_periods": n_same_periods,
            "n_status_changed": n_status_changed, "n_included_both": len(both_ids),
            "slot_agreement": float((old_open == new_open).mean()) if both_ids else np.nan,
            "n_venues_any_slot_changed": int((old_open != new_open).any(axis=1).sum())}


def plot(old_curve, old_boot, new_curve, new_boot, slot_labels, old_sample, new_sample, n_old, n_new):
    hours = np.arange(SLOTS_PER_DAY) * SLOT_MIN / MINUTES_PER_HOUR
    fig, (ax_day, ax_diff, ax_week) = plt.subplots(3, 1, figsize=FIGURE_SIZE_IN,
                                                   gridspec_kw={"height_ratios": [3, 1.4, 2.4]})
    for label, color, curve, boot, n in ((f"{OLD_LABEL} (n={n_old})", OLD_COLOR, old_curve, old_boot, n_old),
                                         (f"{NEW_LABEL} (n={n_new})", NEW_COLOR, new_curve, new_boot, n_new)):
        low, high = np.percentile(boot, INTERVAL_PERCENTILES, axis=0)
        ax_day.step(hours, curve, where="post", color=color, lw=LINE_WIDTH, label=label)
        ax_day.fill_between(hours, low, high, step="post", color=color, alpha=BAND_ALPHA, lw=0)
    ax_day.set_title("Weekday (Mon-Fri) share of venues open, 30-min slots, 95% bootstrap band")
    ax_day.set_ylabel("share open")
    ax_day.legend(frameon=False, loc="upper left")

    diff_boot = new_boot - old_boot
    diff_low, diff_high = np.percentile(diff_boot, INTERVAL_PERCENTILES, axis=0)
    ax_diff.axhline(0, color="0.5", lw=1)
    ax_diff.step(hours, new_curve - old_curve, where="post", color="0.2", lw=LINE_WIDTH)
    ax_diff.fill_between(hours, diff_low, diff_high, step="post", color="0.2", alpha=BAND_ALPHA, lw=0)
    ax_diff.set_ylabel(f"new - old")
    ax_diff.set_title("Difference (new minus old), 95% band")
    for ax in (ax_day, ax_diff):
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 2))
        ax.grid(axis="y", color="0.9")
        ax.spines[["top", "right"]].set_visible(False)
    ax_diff.set_xlabel("time of day (h)")

    week_hours = SLOT_STARTS_MIN / MINUTES_PER_HOUR
    for color, sample in ((OLD_COLOR, old_sample), (NEW_COLOR, new_sample)):
        ax_week.step(week_hours, sample["open"].mean(axis=0), where="post", color=color, lw=LINE_WIDTH / 1.5)
    # x axis in Mon..Sun order is easier to read; Google's week starts Sunday, so label day starts.
    ax_week.set_xticks(np.arange(DAYS_PER_WEEK) * 24)
    ax_week.set_xticklabels(DAY_NAMES)
    ax_week.set_xlim(0, DAYS_PER_WEEK * 24)
    ax_week.set_ylabel("share open")
    ax_week.set_title("Full week (Google week, Sunday first)")
    ax_week.grid(axis="y", color="0.9")
    ax_week.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def main():
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    ring_by_id = pd.read_csv(VENUE_TABLE_PATH, usecols=["place_id", RING_COL]).set_index("place_id")[RING_COL].to_dict()
    old_records = load_records(OLD_HOURS_DIR, should_drop_fixed=False)
    new_records = load_records(NEW_HOURS_DIR, should_drop_fixed=True)
    old_sample, new_sample = score(old_records, ring_by_id), score(new_records, ring_by_id)
    n_old, n_new = len(old_sample["place_id"]), len(new_sample["place_id"])

    print(f"old pull: {len(old_records)} venues, {n_old} included | new pull: {len(new_records)} venues "
          f"(fixed excluded), {n_new} included")
    for label, sample in ((OLD_LABEL, old_sample), (NEW_LABEL, new_sample)):
        print(f"\n{label} status x flag:\n{pd.crosstab(sample['status_df'].status, sample['status_df'].flag).to_string()}")
        print(f"included by ring: {pd.Series(sample['ring']).value_counts().to_dict()}")

    old_boot_counts = bootstrap_weights(n_old, rng)
    new_boot_counts = bootstrap_weights(n_new, rng)
    old_stats, old_curve, old_boot, slot_labels = sample_stats(old_sample, np.ones(n_old), old_boot_counts)
    new_stats, new_curve, new_boot, _ = sample_stats(new_sample, np.ones(n_new), new_boot_counts)
    rows = compare_rows("raw", ALL_RINGS, old_stats, new_stats, n_old, n_new)

    # Old venues reweighted to the new draw's ring mix (old venues not in the table get weight 0).
    new_ring_share = pd.Series(new_sample["ring"]).value_counts(normalize=True)
    old_ring_share = pd.Series(old_sample["ring"]).value_counts(normalize=True)
    ring_weight = (new_ring_share / old_ring_share).fillna(0)
    old_weights = np.array([ring_weight.get(ring, 0.0) for ring in old_sample["ring"]])
    reweighted_stats, _, _, _ = sample_stats(old_sample, old_weights, old_boot_counts)
    rows += compare_rows("old_reweighted_to_new_ring_mix", ALL_RINGS, reweighted_stats, new_stats, n_old, n_new)

    for ring in sorted(new_ring_share.index):
        old_mask, new_mask = old_sample["ring"] == ring, new_sample["ring"] == ring
        ring_old, ring_new = subset(old_sample, old_mask), subset(new_sample, new_mask)
        ring_old_stats, _, _, _ = sample_stats(ring_old, np.ones(old_mask.sum()), bootstrap_weights(old_mask.sum(), rng))
        ring_new_stats, _, _, _ = sample_stats(ring_new, np.ones(new_mask.sum()), bootstrap_weights(new_mask.sum(), rng))
        rows += compare_rows("by_ring", ring, ring_old_stats, ring_new_stats, int(old_mask.sum()), int(new_mask.sum()))

    summary_df = pd.DataFrame(rows)
    overlap = overlap_rows(old_records, new_records, old_sample, new_sample)
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(SUMMARY_PATH, index=False)
    pd.DataFrame({"slot": slot_labels, "old_share": old_curve, "new_share": new_curve,
                  "diff": new_curve - old_curve}).to_csv(CURVES_PATH, index=False)
    plot(old_curve, old_boot, new_curve, new_boot, slot_labels, old_sample, new_sample, n_old, n_new)

    pd.set_option("display.width", 200)
    show_cols = ["comparison", "ring", "stat", "n_old", "n_new", "old", "new", "diff", "diff_low", "diff_high", "verdict"]
    print("\n" + summary_df[show_cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    curve_diff = new_curve - old_curve
    worst = int(np.argmax(np.abs(curve_diff)))
    print(f"\nweekday curve: largest |new - old| {abs(curve_diff[worst]):.3f} at {slot_labels[worst]}; "
          f"mean |diff| {np.abs(curve_diff).mean():.3f}")
    print(f"overlap: {overlap}")
    print(f"\nsaved {SUMMARY_PATH.name}, {CURVES_PATH.name}, {FIGURE_PATH.name}")


if __name__ == "__main__":
    main()
