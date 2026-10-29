"""Can a venue's opening hours be imputed from its Google tags well enough for the time-of-day factor?

Context (user, 2026-10-12): DESIGN Q17 proposes a per-venue drive-time factor from the venue's own
trading hours (evidence: drive_time_of_day_factor). Hours exist for the 845 usable venues of the
2026-10-10 Enterprise pull only (~4% of the 19,030-venue table). Training adds the legacy 2026-09-02
pull (frozen_inputs; user, 2026-10-12: defensible, cf. enterprise_hours_old_vs_new, no hours churn);
the newer fetch wins for shared venues. Its outer-ring under-coverage matters less here than for the
histogram: imputation conditions on tags, not location. Proposal: impute the rest from tags
with the scheme of docs/stale_project_mds/session_docs_to_20261013/claude_2026-10-05_side-note_hours-imputation.md (Q10).
Where the pipeline would rely on it: the reachability pass (Q17), and possibly competitor hours
overlap (the side note's own purpose). No API.

Scheme (side note, as implemented here):
  tags       the venue table's `types`; tags on every venue of the table are dropped (universal).
  p_v(h)     venue v's weekday open share at hour h (0-23): share of its Mon-Fri half-hour slots
             h:00 and h:30 that are open (point-in-time rule, as opening_hours.py).
  group(S)   venues whose tags include every tag of S (a tag combination); held venue excluded.
  q_S(h)     mean p_v(h) over group(S): the imputed open share at h.
  confident  S is confident at h if group(S) has >= MIN_GROUP venues and its spread at h (variance of
             p_v(h) over the group) is lower than random groups of the same size in at least
             1 - ALPHA of NULL_DRAWS draws (one-sided; random-group test, side note item 4).
  backoff    per venue and hour, the largest confident S among subsets of the venue's tags; at the
             same size, confident subsets on opposite sides of 0.5 are a tie: count it and back off
             one size (item 6); otherwise take the lowest-spread one. Nothing confident: overall
             mean (the generic bucket).
User's recollection (2026-10-12): collapse generic and low-sample tags into one generic bucket and
strip generic tags from venues that have distinct ones. Here the backoff does that implicitly
(generic tags only ever narrow a group; low-sample combinations fail the test), and only literally
universal tags are dropped, as the side note records. Conflict flagged, not resolved.

Evaluation, leave-one-out over the 845 venues:
  f(p)   the time-of-day factor (drive_time_of_day_factor, band coefficients a): band weights from
         p(h) summed per band, f = weights . a - pooled weights . a; drive-time change exp(-f) - 1.
  Rule (written before the run): imputation beats the default (f = 0, every unknown venue at the
  pooled average) if the mean absolute error of the drive-time change, imputed minus default, has a
  venue-bootstrap 95% CI below 0. Also: Brier score of p(h) against the pooled open share; backoff
  depth; tie rate.
  Run A: tags as in the table (Details types on old_legacy rows, Legacy Nearby types elsewhere).
  Run B: every venue's tags cut to the Nearby vocabulary (tags seen on non-old_legacy rows), i.e.
  what tags look like without the Q9 Essentials pull. A passing B means Q9 is not needed for this.
  Check 3 (added 2026-10-12 with the user, descriptive, no rule): marginal venue types (gas stations,
  groceries and the like, whose competitor status the project does not rule on): count in the table
  and in the sample, mean true and imputed (run A) drive-time change. Does the factor inflate them?

Self-contained: imports nothing from functions/, config.py or pipeline modules (CLAUDE.md D1).

Conclusion (run 2026-10-12, 1,614 venues: 845 from 2026-10-10 + 769 legacy): imputation beats the
default by the rule, but modestly. Run A: drive-time-change MAE 2.51 pp vs 2.80 pp for f = 0
(difference -0.29, CI -0.34 to -0.25); correlation with the true change 0.38; Brier 0.118 vs 0.132;
75% of venue-hours fall back to the generic bucket; ties 0.27%. The legacy pull helps a little
(2026-10-10 only: MAE 2.54, correlation 0.31). Run B (Nearby vocabulary only) passes too, MAE 2.57:
the Q9 Essentials pull is not needed for this use. Universal tags dropped: establishment, food,
point_of_interest, restaurant. Imputed factors are shrunk toward 0, which is the intended
"average when unsure" behaviour. Check 3: only 24-hour types gain reach (gas stations -4.0% on own
hours, 212 table venues, ~1%; night clubs -4.2%); groceries, supermarkets, convenience and liquor
stores lose a little (+1 to +2%, daytime hours). The factor changes reach, not membership.
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
HOURS_PULLS = {                               # pull date: (raw JSON folder, opening_hours venue log)
    "20261010": (PROJECT_ROOT / "outputs" / "places_enterprise_hours" / "places_enterprise_hours_20261010",
                 PROJECT_ROOT / "outputs" / "opening_hours" / "opening_hours_20261010_venue_log.csv"),
    "20260902": (PROJECT_ROOT / "frozen_inputs" / "places_enterprise_hours_20260902",
                 PROJECT_ROOT / "outputs" / "opening_hours" / "opening_hours_20260902_venue_log.csv"),
}
NEW_PULL = "20261010"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "venue_hours_imputation"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
VENUES_OUT_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_venues.csv"
SUMMARY_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_summary.json"
LOG_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"

# --- copied (opening_hours.py; drive_time_of_day_factor 2026-10-12 all-training band coefficients) --
MINUTES_PER_DAY = 1440
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY
SLOT_MIN = 30
WEEKDAY_INDICES = range(1, 6)                 # Google periods: day 0 = Sunday
OLD_LEGACY_RUN = "old_legacy"
TAG_SEPARATOR = "|"
BAND_HOURS = {"night": range(0, 7), "am_peak": range(7, 10), "midday": range(10, 16),
              "pm_peak": range(16, 19), "evening": range(19, 24)}
BAND_COEF = np.array([+0.1961, -0.0607, -0.0347, -0.0803, +0.1269])   # log(pred / G) per band

# --- rules ------------------------------------------------------------------------------------------
N_HOURS = 24
MIN_GROUP = 3
ALPHA = 0.05
NULL_DRAWS = 500
MAX_TAGS = 10                                 # subsets enumerated over at most this many tags
OPEN_SIDE = 0.5
N_BOOTSTRAP = 2000
SEED = 20261012
PCT = 100.0
MARGINAL_TYPES = ("gas_station", "convenience_store", "grocery_store", "supermarket", "laundry", "lodging",
                  "liquor_store", "night_club", "bar", "store")


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


def minute_of_week(point):
    return point["day"] * MINUTES_PER_DAY + point.get("hour", 0) * 60 + point.get("minute", 0)


def weekday_hour_profile(record):
    """p(h): share of Mon-Fri half-hour slots open at hour h; None if hours are missing or malformed."""
    periods = record.get("regularOpeningHours", {}).get("periods", [])
    if not periods:
        return None
    if len(periods) == 1 and "close" not in periods[0]:
        point = periods[0].get("open", {})
        return np.ones(N_HOURS) if (point.get("day", 0), point.get("hour", 0), point.get("minute", 0)) == (0, 0, 0) else None
    slots = np.arange(0, MINUTES_PER_WEEK, SLOT_MIN)
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
    by_day = is_open.reshape(7, N_HOURS, MINUTES_PER_DAY // N_HOURS // SLOT_MIN)
    return by_day[list(WEEKDAY_INDICES)].mean(axis=(0, 2))


def load():
    venues_df = pd.read_csv(VENUES_PATH, usecols=["run_id", "place_id", "types"])
    profiles, pull_of, fetched = {}, {}, {}
    for pull, (hours_dir, log_path) in HOURS_PULLS.items():
        included = set(pd.read_csv(log_path).query("included")["place_id"])
        for path in hours_dir.rglob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            place_id = record.get("id") or path.stem
            if place_id not in included or record.get("is_fixed"):
                continue
            if place_id in fetched and fetched[place_id] >= record.get("fetched_date", ""):
                continue                                  # the newer fetch wins
            profile = weekday_hour_profile(record)
            if profile is not None:
                profiles[place_id], pull_of[place_id], fetched[place_id] = profile, pull, record.get("fetched_date", "")
    tag_sets = venues_df.drop_duplicates("place_id").set_index("place_id")["types"].fillna("").str.split(TAG_SEPARATOR)
    all_tags = [set(tags) - {""} for tags in tag_sets]
    universal = set.intersection(*all_tags)
    nearby_vocab = set().union(*[set(t) for t, run in zip(tag_sets, venues_df.drop_duplicates("place_id")["run_id"])
                                 if run != OLD_LEGACY_RUN]) - {""}
    ids = [pid for pid in profiles if pid in tag_sets.index]
    run_of = venues_df.drop_duplicates("place_id").set_index("place_id")["run_id"]
    sample_df = pd.DataFrame(dict(place_id=ids, run_id=run_of.loc[ids].to_numpy(), pull=[pull_of[i] for i in ids],
                                  tags=[sorted(set(tag_sets[pid]) - universal - {""}) for pid in ids]))
    p = np.vstack([profiles[pid] for pid in ids])
    return sample_df, p, universal, nearby_vocab


class NullSpread:
    """Spread (variance of p(h)) of random groups, per group size, cached."""

    def __init__(self, p, rng):
        self.p, self.rng, self.cache = p, rng, {}

    def __call__(self, size):
        if size not in self.cache:
            draws = np.array([self.rng.choice(len(self.p), size, replace=False) for _ in range(NULL_DRAWS)])
            self.cache[size] = self.p[draws].var(axis=1)          # NULL_DRAWS x hours
        return self.cache[size]


def impute(tag_lists, p, null_spread):
    """Leave-one-out imputed p(h) per venue; backoff size used per venue and hour; ties counted."""
    n = len(tag_lists)
    vocab = sorted(set(itertools.chain.from_iterable(tag_lists)))
    has_tag = {tag: np.array([tag in set(tags) for tags in tag_lists]) for tag in vocab}
    total = p.sum(axis=0)
    imputed, depth = np.empty_like(p), np.zeros(p.shape, np.int64)
    ties = 0
    for v, tags in enumerate(tag_lists):
        generic = (total - p[v]) / (n - 1)
        imputed[v] = generic
        unresolved = np.ones(N_HOURS, bool)
        for size in range(min(len(tags), MAX_TAGS), 0, -1):
            candidates = []
            for subset in itertools.combinations(tags[:MAX_TAGS], size):
                members = np.logical_and.reduce([has_tag[t] for t in subset])
                members[v] = False
                if members.sum() < MIN_GROUP:
                    continue
                share, spread = p[members].mean(axis=0), p[members].var(axis=0)
                p_value = (null_spread(int(members.sum())) <= spread).mean(axis=0)
                candidates.append((share, spread, p_value < ALPHA))
            if not candidates:
                continue
            shares, spreads, confident = (np.array(x) for x in zip(*candidates))
            for h in np.flatnonzero(unresolved):
                ok = confident[:, h]
                if not ok.any():
                    continue
                sides = shares[ok, h] > OPEN_SIDE
                if sides.any() and not sides.all():
                    ties += 1
                    continue
                best = np.flatnonzero(ok)[np.argmin(spreads[ok, h])]
                imputed[v, h], depth[v, h] = shares[best, h], size
                unresolved[h] = False
            if not unresolved.any():
                break
    return imputed, depth, ties


def band_factor(p, reference_weights=None):
    """Time-of-day factor f per venue from p(h); and the pooled band weights."""
    band_sums = np.column_stack([p[:, list(hours)].sum(axis=1) for hours in BAND_HOURS.values()])
    weights = band_sums / np.maximum(band_sums.sum(axis=1, keepdims=True), 1e-12)
    if reference_weights is None:
        reference_weights = band_sums.sum(axis=0) / band_sums.sum()
    return weights @ BAND_COEF - reference_weights @ BAND_COEF, reference_weights


def evaluate(label, tag_lists, p, rng):
    print(f"\n=== run {label} ===")
    tag_counts = pd.Series([len(t) for t in tag_lists])
    print(f"informative tags per venue: median {tag_counts.median():.0f}, none {int((tag_counts == 0).sum())}, "
          f"vocabulary {len(set(itertools.chain.from_iterable(tag_lists)))}")
    imputed, depth, ties = impute(tag_lists, p, NullSpread(p, rng))
    is_open_weekdays = p.sum(axis=1) > 0
    f_true, reference = band_factor(p)
    f_imputed, _ = band_factor(imputed, reference)
    change_true, change_imputed = np.expm1(-f_true) * PCT, np.expm1(-f_imputed) * PCT
    err_imputed = np.abs(change_imputed - change_true)[is_open_weekdays]
    err_default = np.abs(change_true)[is_open_weekdays]
    diff = err_imputed - err_default
    boot = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(N_BOOTSTRAP)]
    low, high = np.percentile(boot, (2.5, 97.5))
    pooled_share = p.mean(axis=0)
    brier_imputed, brier_default = ((imputed - p) ** 2).mean(), ((pooled_share - p) ** 2).mean()
    depth_share = pd.Series(depth.ravel()).value_counts(normalize=True).sort_index()
    correlation = np.corrcoef(change_true[is_open_weekdays], change_imputed[is_open_weekdays])[0, 1]
    is_pass = bool(high < 0)
    print(f"venues {len(p)} ({int(is_open_weekdays.sum())} open on weekdays)")
    print(f"true drive-time change: SD {change_true[is_open_weekdays].std():.2f} pp, "
          f"range {change_true[is_open_weekdays].min():+.1f} to {change_true[is_open_weekdays].max():+.1f}%")
    print(f"MAE drive-time change: imputed {err_imputed.mean():.2f} pp, default (f = 0) {err_default.mean():.2f} pp; "
          f"difference {diff.mean():+.2f} pp (CI {low:+.2f} to {high:+.2f}) -> imputation beats default: {is_pass}")
    print(f"correlation true vs imputed change: {correlation:.3f}")
    print(f"Brier p(h): imputed {brier_imputed:.4f}, pooled share {brier_default:.4f}")
    print("backoff depth (share of venue-hours; 0 = generic bucket): "
          + ", ".join(f"{int(k)}: {v:.1%}" for k, v in depth_share.items()))
    print(f"ties: {ties} venue-hours ({ties / p.size:.2%})")
    summary = dict(n=len(p), mae_imputed=err_imputed.mean(), mae_default=err_default.mean(), diff=diff.mean(),
                   diff_low=low, diff_high=high, is_pass=is_pass, correlation=correlation,
                   brier_imputed=brier_imputed, brier_default=brier_default, ties=ties,
                   depth_share={int(k): v for k, v in depth_share.items()})
    return summary, change_true, change_imputed


def main():
    sys.stdout = tee = Tee()
    print(f"{NAME}  run {RUN_DATE}")
    sample_df, p, universal, nearby_vocab = load()
    print(f"{len(sample_df)} venues with hours and tags; universal tags dropped: {sorted(universal)}")
    print(f"sample by pull: {sample_df['pull'].value_counts().to_dict()}; by run: {sample_df['run_id'].value_counts().to_dict()}; Nearby vocabulary {len(nearby_vocab)} tags")
    rng = np.random.default_rng(SEED)
    summary = dict(run_date=RUN_DATE, universal=sorted(universal))
    is_new = (sample_df["pull"] == NEW_PULL).to_numpy()
    summary["A_new_pull_only"], _, _ = evaluate("A, 2026-10-10 pull only", list(sample_df.loc[is_new, "tags"]), p[is_new], rng)
    summary["A"], true_a, imputed_a = evaluate("A (table tags), both pulls", list(sample_df["tags"]), p, rng)
    coarse = [[t for t in tags if t in nearby_vocab] for tags in sample_df["tags"]]
    summary["B"], _, imputed_b = evaluate("B (Nearby vocabulary only), both pulls", coarse, p, rng)
    is_rich = (sample_df["run_id"] == OLD_LEGACY_RUN).to_numpy()
    for label, rows in (("Details-typed venues", is_rich), ("Nearby-typed venues", ~is_rich)):
        err_a = np.abs(imputed_a - true_a)[rows].mean()
        err_b = np.abs(imputed_b - true_a)[rows].mean()
        print(f"  {label} ({rows.sum()}): MAE run A {err_a:.2f} pp, run B {err_b:.2f} pp, default {np.abs(true_a)[rows].mean():.2f} pp")
    print("\nCheck 3: marginal venue types (table tags; true = own hours, imputed = run A)")
    table_tags = pd.read_csv(VENUES_PATH, usecols=["place_id", "types"]).drop_duplicates("place_id")["types"]
    table_sets = table_tags.fillna("").str.split(TAG_SEPARATOR).map(set)
    sample_sets = [set(tags) for tags in sample_df["tags"]]
    rows = []
    for tag in MARGINAL_TYPES:
        is_in = np.array([tag in tags for tags in sample_sets])
        rows.append(dict(type=tag, n_table=int(table_sets.map(lambda tags: tag in tags).sum()), n_sample=int(is_in.sum()),
                         true_pct=true_a[is_in].mean() if is_in.any() else np.nan,
                         imputed_pct=imputed_a[is_in].mean() if is_in.any() else np.nan))
    marginal_df = pd.DataFrame(rows)
    print(marginal_df.to_string(index=False, float_format="{:+.2f}".format))
    summary["check3"] = marginal_df.to_dict("records")
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    sample_df.assign(tags=sample_df["tags"].str.join(TAG_SEPARATOR), change_true_pct=true_a,
                     change_imputed_a_pct=imputed_a, change_imputed_b_pct=imputed_b).to_csv(VENUES_OUT_PATH, index=False)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=1, default=float))
    sys.stdout = tee.stdout
    LOG_PATH.write_text("".join(tee.lines))
    print(f"saved {VENUES_OUT_PATH.name}, {SUMMARY_PATH.name}, {LOG_PATH.name}")


if __name__ == "__main__":
    main()
