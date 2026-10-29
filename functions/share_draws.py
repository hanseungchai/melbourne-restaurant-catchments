"""Share step (SCR-19): the subject's share per hex and competitor credits, by draws of reach and hours.

A reach unit is one block of the reach table: a transit band and slot, or the drive band (slot-free: its reach serves
every slot). Per draw:
  reach    every (hex, venue hex) pair enters by its chance, one uniform per pair; the venues of a venue hex enter
           together (shared route noise). The subject enters hex h on the uniform of its own venue hex, so co-located
           venues enter exactly when it does.
  hours    every venue's week from functions/hours_imputation.WeekDraws (own hours, else a donor's; "all_open": all
           open), read at the slot on the draw's day (Mon-Thu: one day per draw, shared).
  counts   per hex, open entrants by key cell: X = R @ C, R the hex x venue hex entry matrix, C the venue hex x cell
           open counts. The key is the shrunk rating (SCR-20; Q29 variants: rating_key); cells (SCR-19 layout) are
           one exact cell per slider value's key (the subject's displayed slider ratings keyed at its own review
           count) and intervals between
           credit edges in between, so the subject's share is exact at every slider value and rivals in one interval
           tie for credits only. "bin" below means a cell.
  shares   subject at focal bin f: A = entrants in rated bins above f, T = entrants in bin f + 1 (itself), K = all + 1.
           q rule (SCR-15): q^A (1 - q^T) / (T (1 - q^K)) (ranks A+1 .. A+T, average weight q^(r-1), over the total
           (1 - q^K) / (1 - q)). Top-N (SCR-2): (ranks of A+1 .. A+T within N) / T / min(N, K). Zero where the subject
           did not enter or is closed.
  credits  (SCR-14 denial) in each draw where the subject entered, every open entrant holds its bin's share at the
           subject's own rating, q = SCORING_HEADLINE_Q; per venue hex G = R^T @ S, S the hex x bin persons-weighted
           shares; a venue's credit is G at its venue hex and bin when open.
  contention (SCR-14 peers) in the same draws, the nearest occupied cell above the subject and the nearest below: each
           venue in it holds an equal part of the share that would move if the subject swapped ranks with it, q rule
           at SCORING_HEADLINE_Q: above (q^(A-1) - q^A)(1 - q) / (1 - q^K), below (q^A - q^(A+1))(1 - q) / (1 - q^K),
           A the entrants above the subject, K all entrants; headline hours rule only.
Subject plus credits equal the persons of the hexes it entered, in every draw (the denial sum, checked).
"""
import numpy as np

def shrunk_key(ratings, review_counts, shrink_m, shrink_c):
    """Shrunk rating s = (n·r + m·C) / (n + m) (SCR-20); unrated or no reviews gives C."""
    counts = np.nan_to_num(np.asarray(review_counts, float))
    ratings = np.where(counts > 0, np.nan_to_num(np.asarray(ratings, float), nan=shrink_c), shrink_c)
    return (counts * ratings + shrink_m * shrink_c) / (counts + shrink_m)


def flat_key(ratings, review_counts, decimals, unrated_key):
    """Displayed rating (Q29 control F): equal displayed ratings tie; unrated or no reviews at unrated_key."""
    counts = np.nan_to_num(np.asarray(review_counts, float))
    ratings = np.asarray(ratings, float)
    is_rated = np.isfinite(ratings) & (counts > 0)
    return np.where(is_rated, np.round(np.nan_to_num(ratings), decimals), unrated_key)


def read_ends(ratings, top_rating, top_read, bottom_rating, bottom_read):
    """Displayed ratings with the top and bottom ratings read as top_read and bottom_read (Q29, SCR-20: a 5.0 as the
    middle of 4.95-5.0, a 1.0 as the middle of 1.0-1.05)."""
    ratings = np.asarray(ratings, float)
    ratings = np.where(np.isclose(ratings, top_rating), top_read, ratings)
    return np.where(np.isclose(ratings, bottom_rating), bottom_read, ratings)


def percentile_key(ratings, review_counts, ref_ratings, ref_counts, n_neighbours, self_index, decimals, unrated_key):
    """Midrank percentile of each displayed rating among the n_neighbours reference venues nearest in log review count
    (Q29 challenger P); self_index: each venue's row in the reference, excluded from its own neighbours (-1: none).
    Unrated or no reviews at unrated_key."""
    ratings = np.asarray(ratings, float)
    counts = np.nan_to_num(np.asarray(review_counts, float))
    order = np.argsort(np.log(ref_counts), kind="stable")
    ref_log = np.log(ref_counts)[order]
    ref_r = np.round(np.asarray(ref_ratings, float)[order], decimals)
    position_of = np.empty(len(order), int)
    position_of[order] = np.arange(len(order))
    half_step = 0.5 * 10.0 ** -decimals
    out = np.full(len(ratings), float(unrated_key))
    for i in np.flatnonzero(np.isfinite(ratings) & (counts > 0)):
        q_log = np.log(counts[i])
        pos = np.searchsorted(ref_log, q_log)
        window = np.arange(max(pos - n_neighbours - 1, 0), min(pos + n_neighbours + 1, len(ref_log)))
        if self_index[i] >= 0:
            window = window[window != position_of[self_index[i]]]
        nearest = window[np.argsort(np.abs(ref_log[window] - q_log), kind="stable")[:n_neighbours]]
        rating = round(float(ratings[i]), decimals)
        below = (ref_r[nearest] < rating - half_step).sum()
        equal = (np.abs(ref_r[nearest] - rating) < half_step).sum()
        out[i] = (below + 0.5 * equal) / len(nearest)
    return out


class KeyCells:
    """Ordered cells on the rating key: an exact cell at each slider key, intervals between edges and slider keys.

    Interval cells are left-closed between consecutive edges (credit edges and slider keys merged); a key within
    tie_tol of a slider key falls in that slider key's exact cell. Cell ids ascend with the key.
    """

    def __init__(self, credit_edges, slider_keys, tie_tol):
        self.slider_keys = np.asarray(slider_keys, float)
        self.edges = np.unique(np.concatenate([np.asarray(credit_edges, float), self.slider_keys]))
        self.tie_tol = tie_tol
        is_slider = np.isclose(self.edges[:, None], self.slider_keys[None, :], rtol=0, atol=tie_tol).any(axis=1)
        raw_ids = np.arange(2 * len(self.edges) + 1)              # even: interval below edge i // 2; odd: edge's point
        is_kept = (raw_ids % 2 == 0) | is_slider[np.minimum(raw_ids // 2, len(self.edges) - 1)]
        self.compact = np.cumsum(is_kept) - 1
        self.n_cells = int(is_kept.sum())

    def assign(self, keys):
        keys = np.asarray(keys, float)
        raw = 2 * np.searchsorted(self.edges, keys, side="right")
        gap = np.abs(keys[:, None] - self.slider_keys[None, :])
        nearest = gap.argmin(axis=1)
        is_tied = gap[np.arange(len(keys)), nearest] <= self.tie_tol
        slider_edge = np.searchsorted(self.edges, self.slider_keys[nearest] - self.tie_tol, side="left")
        raw = np.where(is_tied, 2 * slider_edge + 1, raw)
        return self.compact[raw]


def credit_edges(lowest, highest, coarse_step, fine_from, fine_step):
    """Credit cell edges: every coarse_step from lowest to fine_from, then every fine_step to highest."""
    coarse = np.arange(lowest, fine_from, coarse_step)
    fine = np.arange(fine_from, highest + fine_step / 2, fine_step)
    return np.round(np.concatenate([coarse, fine]), 6)


def open_counts(is_open, venue_hex_index, venue_bins, n_venue_hexes, n_bins):
    """Open venues per venue hex, slot and bin: (venue hexes, slots x bins) float32 from is_open (venues x slots)."""
    n_slots = is_open.shape[1]
    out = np.zeros((n_venue_hexes, n_slots, n_bins), np.float32)
    rows, slots = np.nonzero(is_open)
    np.add.at(out, (venue_hex_index[rows], slots, venue_bins[rows]), 1.0)
    return out.reshape(n_venue_hexes, n_slots * n_bins)


def q_powers(q_values, max_count):
    """q^n for n = 0 .. max_count, one row per q."""
    return np.power(np.asarray(q_values, float)[:, None], np.arange(max_count + 1)[None, :])


def subject_shares(counts, focal_bins, q_pow, top_n):
    """The subject's share per hex, per focal bin, per metric (the q grid, then each N), if it entered.

    counts (hexes x bins) of open entrants other than the subject. Returns (hexes, focal bins, len(q) + len(top_n)).
    """
    counts = np.rint(counts).astype(np.int64)
    total = counts.sum(axis=1) + 1                                          # K, the subject included
    above_cum = np.cumsum(counts[:, ::-1], axis=1)[:, ::-1]                 # entrants in bins >= b
    out = np.empty((len(counts), len(focal_bins), len(q_pow) + len(top_n)))
    for j, focal in enumerate(focal_bins):
        above = above_cum[:, focal + 1] if focal + 1 < counts.shape[1] else np.zeros(len(counts), np.int64)
        tied = counts[:, focal] + 1
        num = q_pow[:, above] * (1 - q_pow[:, tied])                        # (q, hexes)
        out[:, j, :len(q_pow)] = (num / (tied[None, :] * (1 - q_pow[:, total]))).T
        for k, n in enumerate(top_n):
            in_top = np.clip(np.minimum(n, above + tied) - above, 0, None)
            out[:, j, len(q_pow) + k] = in_top / tied / np.minimum(n, total)
    return out


def bin_shares(counts, subject_bin, q, max_count):
    """Each open entrant's share per bin (hexes x bins) with the subject in subject_bin, q rule at one q."""
    counts = np.rint(counts).astype(np.int64)
    counts[:, subject_bin] += 1
    q_pow = q ** np.arange(max_count + 2)
    total = counts.sum(axis=1)
    above = np.cumsum(counts[:, ::-1], axis=1)[:, ::-1] - counts            # entrants in bins > b
    with np.errstate(invalid="ignore", divide="ignore"):
        share = q_pow[above] * (1 - q_pow[counts]) / (counts * (1 - q_pow[total])[:, None])
    return np.where(counts > 0, share, 0.0)


def contention_shares(counts, subject_bin, q, max_count):
    """Each entrant's contention share per cell (hexes x cells): the swap share split over the nearest occupied cell
    above the subject's cell and the nearest below; zero elsewhere."""
    counts = np.rint(counts).astype(np.int64)
    n_hexes, n_cells = counts.shape
    q_pow = q ** np.arange(max_count + 2)
    above = counts[:, subject_bin + 1:].sum(axis=1)
    total = counts.sum(axis=1) + 1
    scale = (1 - q) / (1 - q_pow[total])
    out = np.zeros((n_hexes, n_cells))
    rows = np.arange(n_hexes)
    upper = counts[:, subject_bin + 1:] > 0
    if upper.shape[1]:
        has_up = upper.any(axis=1)
        up_cell = subject_bin + 1 + upper.argmax(axis=1)
        gain = (q_pow[np.maximum(above - 1, 0)] - q_pow[above]) * scale
        out[rows[has_up], up_cell[has_up]] = gain[has_up] / counts[rows[has_up], up_cell[has_up]]
    lower = counts[:, :subject_bin][:, ::-1] > 0
    if lower.shape[1]:
        has_low = lower.any(axis=1)
        low_cell = subject_bin - 1 - lower.argmax(axis=1)
        gain = (q_pow[above] - q_pow[above + 1]) * scale
        out[rows[has_low], low_cell[has_low]] = gain[has_low] / counts[rows[has_low], low_cell[has_low]]
    return out
