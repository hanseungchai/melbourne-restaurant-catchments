"""Venue open shares per 30-min slot and day type (SCR-13, VEN-13): own pulled hours, else imputed from tags.

Open share of venue v in slot s of a day type: the share of the day type's days on which v is open at the slot's start
(point-in-time rule, functions/places_hours.py), so a venue shut on Mondays is 0.75 open at Mon-Thu 19:00.

Imputation by partial pooling along a chain of the venue's tags (rule "shrink" of
diagnostics/venue_hours_slot_imputation.py, which beat VEN-13's spread-test backoff at the subject's slots):
  chain      pooled venues; then the venue's tag carried by the most pulled venues; then that set plus the tag that
             keeps the most; ... until no pulled venue carries the whole set (at most MAX_TAGS tags, sorted);
  step       e_k = (n_k mean_k + M e_(k-1)) / (n_k + M), n_k and mean_k the pulled venues carrying the k-th set and
             their mean open share per slot; e_0 the pooled mean of every pulled venue.
Tags carried by every venue of the table are dropped first. depth = chain length (0 = no tag carried by a pulled venue).

Donor hours (SCR-13): unrolled, e_K = sum_k w_k mean_k with a_k = n_k / (n_k + M), w_K = a_K,
w_(k-1) = (1 - a_K) ... (1 - a_k) a_(k-1), w_0 = prod_k (1 - a_k). A draw picks level k with chance w_k, then one
pulled venue of the k-th group at random, and the venue adopts that donor's weekly schedule: over draws its open rate
is e_K exactly (DonorSampler).
"""
import numpy as np

from functions.places_hours import MINUTES_PER_DAY

SOURCE_OWN, SOURCE_IMPUTED = "own", "imputed"


def day_type_shares(week, day_types, slot_min):
    """One venue's open share per (day type, slot of day), flattened day type by day type, from its weekly open flags
    (functions/places_hours.venue_slots)."""
    slots_per_day = MINUTES_PER_DAY // slot_min
    by_day = np.asarray(week).reshape(-1, slots_per_day)                        # Google day index x slot of day
    return np.concatenate([by_day[days].mean(axis=0) for days in day_types.values()])


class ShrinkImputer:
    """Partial pooling along a greedy tag chain, from the pulled venues' tags and open shares (venues x slot columns)."""

    def __init__(self, train_tag_lists, train_shares, shrink_m, max_tags):
        self.shares, self.shrink_m, self.max_tags = train_shares, shrink_m, max_tags
        self.pooled = train_shares.mean(axis=0)
        vocab = {tag for tags in train_tag_lists for tag in tags}
        self.has_tag = {tag: np.array([tag in set(tags) for tags in train_tag_lists]) for tag in vocab}
        self.groups = {}                                     # sorted tag tuple -> (n, mean per slot column)

    def group(self, subset):
        if subset not in self.groups:
            members = np.logical_and.reduce([self.has_tag[tag] for tag in subset])
            n_members = int(members.sum())
            self.groups[subset] = (n_members, self.shares[members].mean(axis=0) if n_members else None)
        return self.groups[subset]

    def members(self, subset):
        """Training rows carrying every tag of subset (all rows for the empty subset)."""
        if not subset:
            return np.arange(len(self.shares))
        return np.flatnonzero(np.logical_and.reduce([self.has_tag[tag] for tag in subset]))

    def chain(self, tags):
        """The greedy chain for one tag list (informative tags, sorted): [(sorted tag tuple, n members), ...], from
        level 1 (one tag) on; empty when no tag is carried by a pulled venue."""
        steps, current = [], ()
        left = [tag for tag in tags[:self.max_tags] if tag in self.has_tag]
        while left:
            options = [(self.group(tuple(sorted(current + (tag,))))[0], tag) for tag in left]
            n_members, tag = max(options, key=lambda option: option[0])
            if n_members == 0:
                break
            current = tuple(sorted(current + (tag,)))
            steps.append((current, n_members))
            left.remove(tag)
        return steps

    def impute(self, tags):
        """(imputed share per slot column, chain length) for one tag list (informative tags, sorted)."""
        estimate = self.pooled.copy()
        steps = self.chain(tags)
        for subset, n_members in steps:
            estimate = (n_members * self.group(subset)[1] + self.shrink_m * estimate) / (n_members + self.shrink_m)
        return estimate, len(steps)

    def level_weights(self, tags):
        """[(sorted tag tuple, weight), ...] from level 0 (the pooled venues, empty tuple) to the chain's end; weights
        sum to 1 and weight the levels' means to impute()'s estimate."""
        steps = self.chain(tags)
        weights, remaining = [], 1.0
        for subset, n_members in reversed(steps):
            keep = n_members / (n_members + self.shrink_m)
            weights.append((subset, remaining * keep))
            remaining *= 1 - keep
        weights.append(((), remaining))
        return weights[::-1]


class DonorSampler:
    """Per draw, one donor (a training row) for every imputed venue (SCR-13): a level of its chain by weight, then a
    random member of that level's group. Vectorised over venues: each venue's levels are padded to the longest chain."""

    def __init__(self, imputer, tag_lists):
        keys = [tuple(tags) for tags in tag_lists]
        level_lists = {key: imputer.level_weights(list(key)) for key in set(keys)}
        n_levels = max(len(levels) for levels in level_lists.values())
        member_parts, starts, sizes, cum = [], {}, {}, {}
        offset = 0
        for key, levels in level_lists.items():
            for subset, _ in levels:
                if subset not in starts:
                    rows = imputer.members(subset)
                    starts[subset], sizes[subset] = offset, len(rows)
                    member_parts.append(rows)
                    offset += len(rows)
            cum[key] = np.cumsum([weight for _, weight in levels])
        self.members = np.concatenate(member_parts)
        self.level_cum = np.ones((len(keys), n_levels))           # padded levels are never picked (cum already 1)
        self.level_start = np.zeros((len(keys), n_levels), np.int64)
        self.level_size = np.ones((len(keys), n_levels), np.int64)
        for row, key in enumerate(keys):
            levels = level_lists[key]
            self.level_cum[row, :len(levels)] = cum[key]
            self.level_cum[row, len(levels) - 1] = 1.0              # float sums: the last level closes the row
            self.level_start[row, :len(levels)] = [starts[subset] for subset, _ in levels]
            self.level_size[row, :len(levels)] = [sizes[subset] for subset, _ in levels]

    def draw(self, rng):
        """One donor training row per venue (as tag_lists' order)."""
        n_venues = len(self.level_cum)
        level = (rng.random((n_venues, 1)) < self.level_cum).argmax(axis=1)
        rows = np.arange(n_venues)
        start, size = self.level_start[rows, level], self.level_size[rows, level]
        return self.members[start + (rng.random(n_venues) * size).astype(np.int64)]


class WeekDraws:
    """Every venue's weekly open flags in one draw (SCR-13): own hours where pulled, otherwise a donor's whole week."""

    def __init__(self, own_weeks, is_imputed, sampler, train_weeks):
        self.own_weeks, self.is_imputed = own_weeks, is_imputed        # venues x week slots (bool); imputed mask
        self.sampler, self.train_weeks = sampler, train_weeks          # sampler over the imputed venues, in order

    def draw(self, rng):
        weeks = self.own_weeks.copy()
        weeks[self.is_imputed] = self.train_weeks[self.sampler.draw(rng)]
        return weeks

    def expected(self):
        """Each venue's open rate per week slot over draws (exact: level weights x donor groups' means)."""
        weeks = self.own_weeks.astype(np.float64)
        sampler, rows = self.sampler, np.flatnonzero(self.is_imputed)
        member_weeks = self.train_weeks[sampler.members].astype(np.float64)
        cum_members = np.vstack([np.zeros(member_weeks.shape[1]), np.cumsum(member_weeks, axis=0)])
        weights = np.diff(np.hstack([np.zeros((len(rows), 1)), sampler.level_cum]), axis=1)
        for i, row in enumerate(rows):
            total = np.zeros(member_weeks.shape[1])
            for level in np.flatnonzero(weights[i] > 0):
                start, size = sampler.level_start[i, level], sampler.level_size[i, level]
                total += weights[i, level] * (cum_members[start + size] - cum_members[start]) / size
            weeks[row] = total
        return weeks


def draw_days(draw, day_types):
    """One Google day index per day type for draw number `draw` (Mon-Thu: one of its days, shared by every venue).
    Stratified, not random: draw d takes the (d mod n)-th day, so every n draws cover each day once and the day's
    shared noise (Monday has ~30% fewer venues open than Thursday, diagnostics/venue_hours_donor_draws.py) cancels."""
    return {day_type: int(days[draw % len(days)]) for day_type, days in day_types.items()}
