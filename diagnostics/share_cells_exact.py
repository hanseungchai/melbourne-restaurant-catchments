"""Are the share step's key cells exact for the subject, and are its per-cell share formulas right?

Claim: the share step (scoring.build_shares, functions/share_draws.py; SCR-19 layout, SCR-20, SCR-14, SCR-15) counts
entrants per key cell instead of ranking them, and still gets (1) the subject's share at every slider rating exactly
(q rule and Top-N), (2) entrant shares that sum to the hex (the denial sum), (3) contention, the share moved by
swapping the subject with each venue in the nearest occupied cell above or below, split equally within that cell.
Where the pipeline relies on it: every headline, slider value, denial credit and contention figure of the share step.

Method: cells built as the pipeline builds them (an exact cell per slider key: the subject's displayed slider ratings
shrunk at its own review count; credit edges every 0.02 from 4.0 and 0.1 below; tie tolerance 1e-9) on the real
venue keys. Random entrant sets drawn from the real venues; each formula on the cell counts against brute force on
the raw keys: the subject ranked by key (ties share the average weight of their ranks), contention as the difference
of the subject's brute-force shares one rank apart, divided by the occupants of the nearest occupied cell.

Rules (Claude's, written before the first run, 94th; not user-approved): cell ids never fall as the key rises; each
slider cell holds only keys within the tolerance of its slider key; worst absolute differences against brute force
below 1e-12 for shares and contention, 1e-9 for the entrant share sum.

Self-contained (CLAUDE.md D1): imports nothing from functions/, config.py or pipeline modules; the functions below are
copies of functions/share_draws.py (shrunk_key, KeyCells, credit_edges, q_powers, subject_shares, bin_shares,
contention_shares) at the 94th. No API.

Conclusion (run 2026-10-24, 18,497 competitors, 98 cells, 2,000 sets of 0-399 entrants): PASS on every rule; worst
share difference 3e-16, entrant sum 2e-16, contention 4e-17. Interval cells blur rivals within 0.02 for credits only
(by design); the subject's share is exact at every slider value.
"""
import datetime
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths ------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENUES_PATH = (PROJECT_ROOT / "outputs" / "hex_grid" / "-37.76870_144.97196"
               / "venues_with_hex_ven20260925_-37.76870_144.97196.csv")
NAME = "share_cells_exact"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SUMMARY_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_summary.csv"
LOG_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"

# --- copied from config.py at the 94th ---------------------------------------------------------------
SUBJECT_PLACE_ID = "<place_id: subject, Brunswick East>"   # [subject] Brunswick East
SHRINK_M, SHRINK_C = 15, 4.25
RATING_RANGE = (1.0, 5.0)
RATING_STEP = 0.1
FOCAL_RATING_RANGE = (4.3, 5.0)
CREDIT_KEY_STEP, CREDIT_FINE_FROM, CREDIT_COARSE_STEP = 0.02, 4.0, 0.1
KEY_TIE_TOL = 1e-9
Q_GRID = [round(0.05 * k, 2) for k in range(1, 20)]
HEADLINE_Q = 0.7
TOP_N = [1, 2, 3]

# --- this diagnostic --------------------------------------------------------------------------------
N_SETS = 2000
MAX_ENTRANTS = 400
SEED = 20261024
SHARE_TOL, SUM_TOL, CONTENTION_TOL = 1e-12, 1e-9, 1e-12


# --- copies of functions/share_draws.py ----------------------------------------------------------------
def shrunk_key(ratings, review_counts, shrink_m, shrink_c):
    counts = np.nan_to_num(np.asarray(review_counts, float))
    ratings = np.where(counts > 0, np.nan_to_num(np.asarray(ratings, float), nan=shrink_c), shrink_c)
    return (counts * ratings + shrink_m * shrink_c) / (counts + shrink_m)


class KeyCells:
    def __init__(self, credit_edges, slider_keys, tie_tol):
        self.slider_keys = np.asarray(slider_keys, float)
        self.edges = np.unique(np.concatenate([np.asarray(credit_edges, float), self.slider_keys]))
        self.tie_tol = tie_tol
        is_slider = np.isclose(self.edges[:, None], self.slider_keys[None, :], rtol=0, atol=tie_tol).any(axis=1)
        raw_ids = np.arange(2 * len(self.edges) + 1)
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
    coarse = np.arange(lowest, fine_from, coarse_step)
    fine = np.arange(fine_from, highest + fine_step / 2, fine_step)
    return np.round(np.concatenate([coarse, fine]), 6)


def q_powers(q_values, max_count):
    return np.power(np.asarray(q_values, float)[:, None], np.arange(max_count + 1)[None, :])


def subject_shares(counts, focal_bins, q_pow, top_n):
    counts = np.rint(counts).astype(np.int64)
    total = counts.sum(axis=1) + 1
    above_cum = np.cumsum(counts[:, ::-1], axis=1)[:, ::-1]
    out = np.empty((len(counts), len(focal_bins), len(q_pow) + len(top_n)))
    for j, focal in enumerate(focal_bins):
        above = above_cum[:, focal + 1] if focal + 1 < counts.shape[1] else np.zeros(len(counts), np.int64)
        tied = counts[:, focal] + 1
        num = q_pow[:, above] * (1 - q_pow[:, tied])
        out[:, j, :len(q_pow)] = (num / (tied[None, :] * (1 - q_pow[:, total]))).T
        for k, n in enumerate(top_n):
            in_top = np.clip(np.minimum(n, above + tied) - above, 0, None)
            out[:, j, len(q_pow) + k] = in_top / tied / np.minimum(n, total)
    return out


def bin_shares(counts, subject_bin, q, max_count):
    counts = np.rint(counts).astype(np.int64)
    counts[:, subject_bin] += 1
    q_pow = q ** np.arange(max_count + 2)
    total = counts.sum(axis=1)
    above = np.cumsum(counts[:, ::-1], axis=1)[:, ::-1] - counts
    with np.errstate(invalid="ignore", divide="ignore"):
        share = q_pow[above] * (1 - q_pow[counts]) / (counts * (1 - q_pow[total])[:, None])
    return np.where(counts > 0, share, 0.0)


def contention_shares(counts, subject_bin, q, max_count):
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


# --- brute force on raw keys ---------------------------------------------------------------------------
def brute_q_share(rank, n_total, q):
    """Weight of rank (1-based) over all ranks' weights, q rule."""
    weights = q ** np.arange(n_total)
    return weights[rank - 1] / weights.sum()


class Tee:
    def __init__(self):
        self.lines = []

    def write(self, text):
        self.lines.append(text)
        sys.__stdout__.write(text)

    def flush(self):
        sys.__stdout__.flush()


def main():
    tee = Tee()
    sys.stdout = tee
    print(f"{NAME}, run {RUN_DATE}; venue table {VENUES_PATH.name}")
    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "rating", "user_ratings_total"]).drop_duplicates(
        "place_id")
    subject = venues_df[venues_df.place_id == SUBJECT_PLACE_ID].iloc[0]
    competitors_df = venues_df[venues_df.place_id != SUBJECT_PLACE_ID]
    subject_n = int(subject.user_ratings_total)
    focal_ratings = np.round(np.arange(FOCAL_RATING_RANGE[0], FOCAL_RATING_RANGE[1] + RATING_STEP / 2, RATING_STEP), 1)
    focal_keys = shrunk_key(focal_ratings, np.full(len(focal_ratings), subject_n), SHRINK_M, SHRINK_C)
    cells = KeyCells(credit_edges(*RATING_RANGE[:1], RATING_RANGE[1], CREDIT_COARSE_STEP, CREDIT_FINE_FROM,
                                  CREDIT_KEY_STEP), focal_keys, KEY_TIE_TOL)
    keys = shrunk_key(competitors_df.rating, competitors_df.user_ratings_total, SHRINK_M, SHRINK_C)
    cell_ids = cells.assign(keys)
    focal_cells = cells.assign(focal_keys)
    subject_cell = int(cells.assign(shrunk_key([subject.rating], [subject_n], SHRINK_M, SHRINK_C))[0])
    print(f"subject {subject.rating} on {subject_n} reviews; {len(keys):,} competitors; {cells.n_cells} cells")

    order = np.argsort(keys, kind="stable")
    is_monotone = bool((np.diff(cell_ids[order]) >= 0).all())
    is_exact = all(np.all(np.abs(keys[cell_ids == cell] - key) <= KEY_TIE_TOL)
                   for cell, key in zip(focal_cells, focal_keys)) and len(set(focal_cells)) == len(focal_cells)
    for cell, key, rating in zip(focal_cells, focal_keys, focal_ratings):
        print(f"  slider {rating}: key {key:.4f}, {int((cell_ids == cell).sum())} competitors tied exactly")

    rng = np.random.default_rng(SEED)
    q_pow = q_powers(Q_GRID, len(keys) + 2)
    worst_share = worst_sum = worst_contention = 0.0
    for _ in range(N_SETS):
        n_entrants = int(rng.integers(0, MAX_ENTRANTS))
        picked = keys[rng.choice(len(keys), n_entrants, replace=False)]
        counts = np.bincount(cells.assign(picked), minlength=cells.n_cells)[None, :].astype(float)
        n_total = n_entrants + 1
        got = subject_shares(counts, focal_cells, q_pow, TOP_N)[0]
        for j, key in enumerate(focal_keys):
            above = int((picked > key + KEY_TIE_TOL).sum())
            tied = int((np.abs(picked - key) <= KEY_TIE_TOL).sum()) + 1
            for m, q in enumerate(Q_GRID):
                expected = np.mean([brute_q_share(r, n_total, q) for r in range(above + 1, above + tied + 1)])
                worst_share = max(worst_share, abs(got[j, m] - expected))
            for k, n in enumerate(TOP_N):
                expected = (np.arange(above, above + tied) < n).sum() / tied / min(n, n_total)
                worst_share = max(worst_share, abs(got[j, len(Q_GRID) + k] - expected))
        with_subject = counts[0].copy()
        with_subject[subject_cell] += 1
        entrant_sum = (bin_shares(counts, subject_cell, HEADLINE_Q, len(keys) + 2)[0] * with_subject).sum()
        worst_sum = max(worst_sum, abs(entrant_sum - 1))
        got_peers = contention_shares(counts, subject_cell, HEADLINE_Q, len(keys) + 2)[0]
        expected_peers = np.zeros(cells.n_cells)
        n_above = int(counts[0, subject_cell + 1:].sum())
        up = [c for c in range(subject_cell + 1, cells.n_cells) if counts[0, c] > 0]
        down = [c for c in range(subject_cell - 1, -1, -1) if counts[0, c] > 0]
        if up:
            expected_peers[up[0]] = ((brute_q_share(n_above, n_total, HEADLINE_Q)
                                      - brute_q_share(n_above + 1, n_total, HEADLINE_Q)) / counts[0, up[0]])
        if down:
            expected_peers[down[0]] = ((brute_q_share(n_above + 1, n_total, HEADLINE_Q)
                                        - brute_q_share(n_above + 2, n_total, HEADLINE_Q)) / counts[0, down[0]])
        worst_contention = max(worst_contention, float(np.abs(got_peers - expected_peers).max()))

    checks = [("cell ids monotone in the key", is_monotone, "", ""),
              ("slider cells exact", is_exact, "", ""),
              ("subject share vs brute force", worst_share < SHARE_TOL, worst_share, SHARE_TOL),
              ("entrant shares sum to 1", worst_sum < SUM_TOL, worst_sum, SUM_TOL),
              ("contention vs brute-force swaps", worst_contention < CONTENTION_TOL, worst_contention,
               CONTENTION_TOL)]
    summary_df = pd.DataFrame(checks, columns=["check", "is_pass", "worst", "tolerance"])
    print(summary_df.to_string(index=False))
    print("PASS" if summary_df.is_pass.all() else "FAIL")
    summary_df.to_csv(SUMMARY_PATH, index=False)
    sys.stdout = sys.__stdout__
    LOG_PATH.write_text("".join(tee.lines), encoding="utf-8")


if __name__ == "__main__":
    main()
