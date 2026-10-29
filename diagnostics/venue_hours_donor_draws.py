"""Do donor schedules (SCR-13) describe a venue's week better than independent per-slot draws, and what do they change?

Claim: scoring draws hours per venue (SCR-13; functions/hours_imputation.DonorSampler, scoring.venue_week_draws): a
venue without its own hours adopts, in each draw, the whole weekly schedule of a donor, a pulled venue picked from a
level of its shrinkage chain (VEN-13) by the level's weight. Over draws its open rate per slot equals the imputed share
(checked in the pipeline's acceptance, 91st). The alternative keeping the same shares is independent draws per slot.
The two agree on every single-slot quantity; they differ on joint ones: whether a venue open at the start of the
subject's dinner window stays open through it, how often it switches, whether a weekend venue open at lunch is open at
dinner. Scoring's expected share per slot is a single-slot quantity per venue, so the headline (a mean over slots) does
not depend on the choice, except through the Mon-Thu day shared by all venues in a draw (closures on the same day).

Tested, leave-one-out over the pulled venues (each venue held out of its own chain's groups and of the pooled mean), at
the subject's windows (config.REACH_SUBJECT_WINDOWS, copied below), per day type, on the truth (the venue's own week),
donor draws (exact expectation: level weight x the held-out groups' mean statistic) and independent draws (from the
held-out shrink shares, M = 5):
  whole      P(open at every slot of the window);
  switches   expected open/closed changes between adjacent slots inside the window;
  both       weekend only: P(open at 13:00 and at 19:00).
Plus the Mon-Thu shared day: the pulled venues' open count per day (Mon, Tue, Wed, Thu) at the subject's Mon-Thu slots.
Rule (Claude's, written before the run, not user-approved): donors pass if, on each statistic and window, their mean
over venues is closer to the truth's than independent draws' mean, or within 0.02 of the truth.

Self-contained (CLAUDE.md D1): imports nothing from functions/, config.py or pipeline modules. No API.

Conclusion (run 2026-10-23, 1,612 venues): PASS, 14 / 14. Independent slots get every joint statistic wrong: P(open
through the whole Mon-Thu dinner window) 0.08 vs truth 0.52 (donors 0.52); switches inside a window 1.4-2.9 vs truth
0.06-0.34 (donors 0.06-0.26). Per venue, donors' error is below independent draws' on 12 of 14 (Fri / Sat dinner
"whole" within 0.02 either way). Donors switch a little less than the truth at dinner (0.12 vs 0.17 Mon-Thu): venues
carrying many tags sit in more groups and are drawn more often. Weekend lunch-and-dinner: donors 0.52 / 0.46 vs truth
0.55 / 0.48 (independent 0.52 / 0.41). Mon-Thu shared day: at 19:00 847 pulled venues are open on Monday, 1,003 Tue,
1,139 Wed, 1,229 Thu (spread 36% of the mean); 30% of venues are shut on some Mon-Thu days but not all. A Monday draw
has about a third fewer competitors than a Thursday one, so the shared day moves the headline (Top-N is nonlinear in
K), where independent days per venue would average it away.
"""
import datetime
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths ------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENUES_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"
HOURS_PULL_DIRS = [PROJECT_ROOT / "frozen_inputs" / "places_enterprise_hours_20260902",
                   PROJECT_ROOT / "outputs" / "places_enterprise_hours" / "places_enterprise_hours_20261010"]
NAME = "venue_hours_donor_draws"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SUMMARY_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_summary.csv"
DAYS_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_monthu_days.csv"
LOG_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"

# --- copied (config.py, places_hours, hours_imputation, 2026-10-23) -----------------------------------
SLOT_MIN = 30
MINUTES_PER_DAY = 1440
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY
SLOTS_PER_DAY = MINUTES_PER_DAY // SLOT_MIN
TAG_SEPARATOR = "|"
OPERATIONAL_STATUS = "OPERATIONAL"
FIXED_RECORD_KEY = "is_fixed"
DAY_TYPES = {"Mon-Thu": [1, 2, 3, 4], "Fri": [5], "Sat": [6], "Sun": [0]}      # Google day index, 0 = Sunday
DAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu"}
SUBJECT_WINDOWS = {"Mon-Thu": [("17:30", "21:00")], "Fri": [("17:30", "21:30")],
                   "Sat": [("12:30", "15:00"), ("17:00", "21:30")], "Sun": [("12:30", "15:00"), ("17:00", "21:00")]}
MAX_TAGS = 10
SHRINK_M = 5

# --- this diagnostic --------------------------------------------------------------------------------
BOTH_SLOTS = ("13:00", "19:00")             # weekend lunch and dinner
WEEKEND = ["Sat", "Sun"]
PASS_TOLERANCE = 0.02


class Tee:
    def __init__(self):
        self.stdout, self.lines = sys.stdout, []

    def write(self, text):
        self.stdout.write(text)
        self.lines.append(text)

    def flush(self):
        self.stdout.flush()


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


def slot_index(hhmm):
    return (int(hhmm[:2]) * 60 + int(hhmm[3:])) // SLOT_MIN


def load():
    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "types"]).drop_duplicates("place_id")
    tag_sets = [set(t.split(TAG_SEPARATOR)) - {""} for t in venues_df.types.fillna("")]
    universal = set.intersection(*tag_sets)
    tags_of = dict(zip(venues_df.place_id, [sorted(t - universal) for t in tag_sets]))
    records = {}
    for pull_dir in HOURS_PULL_DIRS:
        for path in pull_dir.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            place_id = record.get("id") or path.stem
            if place_id not in records or record.get("fetched_date", "") > records[place_id].get("fetched_date", ""):
                records[place_id] = record
    ids, weeks = [], []
    for place_id, record in records.items():
        if (place_id not in tags_of or record.get(FIXED_RECORD_KEY)
                or record.get("businessStatus", "") != OPERATIONAL_STATUS):
            continue
        is_open = week_open(record)
        if is_open is None:
            continue
        ids.append(place_id)
        weeks.append(is_open.reshape(7, SLOTS_PER_DAY))
    return ids, [tags_of[i] for i in ids], np.array(weeks)


def day_type_shares(weeks):
    """venues x day types x slots of day."""
    return np.stack([weeks[:, days].mean(axis=1) for days in DAY_TYPES.values()], axis=1)


# --- statistics per venue (truth and donors from weeks; independent from shares) ---------------------
def window_slots(day_type):
    return [np.arange(slot_index(start), slot_index(end)) for start, end in SUBJECT_WINDOWS[day_type]]


def week_stats(weeks):
    """Per venue: {(stat, day type, window): value}, each averaged over the day type's days."""
    out = {}
    for day_type, days in DAY_TYPES.items():
        day_weeks = weeks[:, days]                                       # venues x days x slots
        for w, slots in enumerate(window_slots(day_type)):
            block = day_weeks[:, :, slots]
            out["whole", day_type, w] = block.all(axis=2).mean(axis=1)
            out["switches", day_type, w] = (block[:, :, 1:] != block[:, :, :-1]).sum(axis=2).mean(axis=1)
        if day_type in WEEKEND:
            lunch, dinner = (slot_index(t) for t in BOTH_SLOTS)
            out["both", day_type, 0] = (day_weeks[:, :, lunch] & day_weeks[:, :, dinner]).mean(axis=1)
    return out


def independent_stats(shares):
    """As week_stats, under independent slots with the given day-type shares (venues x day types x slots)."""
    out = {}
    for t, day_type in enumerate(DAY_TYPES):
        p = shares[:, t]
        for w, slots in enumerate(window_slots(day_type)):
            block = p[:, slots]
            out["whole", day_type, w] = block.prod(axis=1)
            a, b = block[:, :-1], block[:, 1:]
            out["switches", day_type, w] = (a * (1 - b) + (1 - a) * b).sum(axis=1)
        if day_type in WEEKEND:
            lunch, dinner = (slot_index(x) for x in BOTH_SLOTS)
            out["both", day_type, 0] = p[:, lunch] * p[:, dinner]
    return out


# --- leave-one-out chain ----------------------------------------------------------------------------
class Groups:
    def __init__(self, tag_lists):
        vocab = set(itertools.chain.from_iterable(tag_lists))
        self.has_tag = {tag: np.array([tag in set(t) for t in tag_lists]) for tag in vocab}
        self.cache = {}

    def members(self, subset):
        if subset not in self.cache:
            self.cache[subset] = np.flatnonzero(np.logical_and.reduce([self.has_tag[t] for t in subset]))
        return self.cache[subset]


def loo_levels(v, tags, groups, n_venues):
    """[(member rows without v, weight), ...] from the pooled level up, as hours_imputation's level weights."""
    steps, current, left = [], (), list(tags[:MAX_TAGS])
    while left:
        options = []
        for tag in left:
            subset = tuple(sorted(current + (tag,)))
            rows = groups.members(subset)
            rows = rows[rows != v]
            options.append((len(rows), tag, subset, rows))
        n, tag, subset, rows = max(options, key=lambda o: o[0])
        if n == 0:
            break
        steps.append(rows)
        current = subset
        left.remove(tag)
    levels, remaining = [], 1.0
    for rows in reversed(steps):
        keep = len(rows) / (len(rows) + SHRINK_M)
        levels.append((rows, remaining * keep))
        remaining *= 1 - keep
    pooled = np.delete(np.arange(n_venues), v)
    levels.append((pooled, remaining))
    return levels[::-1]


def main():
    tee = Tee()
    sys.stdout = tee
    ids, tag_lists, weeks = load()
    n_venues = len(ids)
    print(f"{NAME} run {RUN_DATE}: {n_venues} pulled venues (operational, readable hours, not fixed)")
    groups = Groups(tag_lists)
    truth = week_stats(weeks)
    keys = list(truth)
    stat_matrix = np.column_stack([truth[k] for k in keys])               # per donor candidate: its statistics
    shares = day_type_shares(weeks)                                       # venues x day types x slots
    donor = np.empty((n_venues, len(keys)))
    loo_shares = np.empty_like(shares)
    for v in range(n_venues):
        levels = loo_levels(v, tag_lists[v], groups, n_venues)
        donor[v] = sum(weight * stat_matrix[rows].mean(axis=0) for rows, weight in levels)
        loo_shares[v] = sum(weight * shares[rows].mean(axis=0) for rows, weight in levels)
    indep = independent_stats(loo_shares)

    rows = []
    for j, key in enumerate(keys):
        stat, day_type, w = key
        t_mean, d_mean, i_mean = truth[key].mean(), donor[:, j].mean(), indep[key].mean()
        is_pass = abs(d_mean - t_mean) <= abs(i_mean - t_mean) or abs(d_mean - t_mean) <= PASS_TOLERANCE
        window = (f"{BOTH_SLOTS[0]}&{BOTH_SLOTS[1]}" if stat == "both"
                  else "-".join(SUBJECT_WINDOWS[day_type][w]))
        rows.append({"stat": stat, "day_type": day_type, "window": window, "truth": t_mean, "donor": d_mean,
                     "independent": i_mean, "donor_mae": np.abs(donor[:, j] - truth[key]).mean(),
                     "independent_mae": np.abs(indep[key] - truth[key]).mean(), "pass": is_pass})
    summary_df = pd.DataFrame(rows)
    print("\nmean over venues (leave-one-out), and mean absolute error per venue:")
    print(summary_df.round(3).to_string(index=False))
    print(f"\nrule: donors pass on {summary_df['pass'].sum()} / {len(summary_df)} statistics; "
          f"{'PASS' if summary_df['pass'].all() else 'FAIL'}")

    slots = window_slots("Mon-Thu")[0]
    day_df = pd.DataFrame({DAY_NAMES[d]: weeks[:, d][:, slots].sum(axis=0) for d in DAY_TYPES["Mon-Thu"]},
                          index=[f"{(s * SLOT_MIN) // 60:02d}:{(s * SLOT_MIN) % 60:02d}" for s in slots])
    day_df["spread_rel"] = (day_df.max(axis=1) - day_df.min(axis=1)) / day_df.mean(axis=1)
    print("\nMon-Thu shared day: pulled venues open per day at the subject's Mon-Thu slots")
    print(day_df.round(3).to_string())
    closed_any = (~weeks[:, DAY_TYPES["Mon-Thu"]][:, :, slot_index("19:00")]).any(axis=1)
    closed_all = (~weeks[:, DAY_TYPES["Mon-Thu"]][:, :, slot_index("19:00")]).all(axis=1)
    print(f"at 19:00: venues shut on some Mon-Thu days but not all: {(closed_any & ~closed_all).mean():.1%}; "
          f"shut all four: {closed_all.mean():.1%}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(SUMMARY_PATH, index=False)
    day_df.to_csv(DAYS_PATH)
    print(f"\nsaved {SUMMARY_PATH.name}, {DAYS_PATH.name}")
    sys.stdout = tee.stdout
    LOG_PATH.write_text("".join(tee.lines), encoding="utf-8")


if __name__ == "__main__":
    main()
