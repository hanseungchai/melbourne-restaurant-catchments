"""Is the staged best-of-K closed form (SCR-23) right, and what does the independent-stage build choice cost?

Claim: functions/share_staged.py gives, from entrant counts per ring and key cell, each entrant's chance to be chosen
under staged best-of-K (a band-b diner searches b stages, each K_s looks without replacement from its nested field,
best by key among all seen wins), and the subject's share at every slider cell and its contention, exactly for the
process it states (stages independent: a later stage may look again at an inner venue). Where the pipeline relies
on it: every staged headline, slider value, denial credit and contention figure (scoring.build_staged_shares).
Second claim (cost of the build choice): the independent-stage form stays close to the decided "minus those seen"
process (DESIGN Q32 (4)), which draws later stages only from venues not yet seen.

Method: (1) known values: K = 1 is flat 1/M; K >= M is top-1; one stage equals sum_j p_j C(M-r, j-1) / C(M, j) and
the 108th's worked examples (scoring.md Notes "Best-of-K"). (2) Monte Carlo of the stated process on random small
hexes (1-3 rings, 0-12 venues per ring, distinct keys; then ties inside one ring; then ties across rings, where the
seen-chance split is an approximation): per-entrant shares, the subject's slider shares, contention (as differences
of subject shares with one venue moved across the subject). (3) Exact "minus those seen" (geometric K, a dynamic
programme over looks spent) vs the independent form on synthetic hexes sized like bands 1-2 (ring 1 5-300 venues,
ring 2 50-2,000; the subject's better venues 0-15% of each ring), the subject's share, k 2.5 / 3.3 / 5.

Rules (Claude's, written before the first run, 2026-10-26; not user-approved): (1) known values within 1e-12
(the worked examples to their printed digits; amended after the first run: within half a printed unit, at k = 10/3,
the 108th's "3.3" being q 0.7's 1 / (1 - q), found when 3.3 gave rank 1 3.30% against the printed 3.33); (2) every Monte Carlo difference within 4 standard errors plus 1e-4,
for distinct keys and one-ring ties; shares sum to 1 within 1e-12; cross-ring ties reported, not judged; (3) cost:
reported as the distribution of relative differences (no pass mark; the user judges the choice).

Self-contained (CLAUDE.md D1): imports nothing from functions/, config.py or pipeline modules; the functions below are
copies of functions/share_staged.py at 2026-10-26. No API.

Conclusion (run 2026-10-26): the closed form is right for the process it states. Known values exact (1e-15: K = 1
flat, K >= M top-1, one stage = the formula); Monte Carlo within 4 SE for distinct keys, one-ring ties and the slider;
shares sum to 1 (2e-16); contention equals the brute subject-share change (1e-17). One judged miss, explained: the
108th's Poisson M 5 rank 2 is printed 0.252, exact 0.2514 (a hand-rounding slip in scoring.md Notes; the formula
check passes). Cross-ring ties (reported): the seen-chance split misses equal splitting by up to 0.125 in tiny hexes
with 4 key values; in the pipeline it touches only credits within a 0.02-wide interval cell (sums exact) and exact
subject ties (equal rating and reviews). Cost of independent stages vs "minus those seen" on the subject's share:
median within +-0.09%, worst -1.2% / +0.8% (2 stages, k 5); 3 stages within -0.8% / +0.5%.
"""
import datetime
import math
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NAME = "best_of_k_checks"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SUMMARY_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_summary.csv"
COST_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_minus_seen_cost.csv"

SEED = 20261026
TAIL_TOL = 1e-12
EXACT_TOL = 1e-12
MC_SIMS = 200_000
MC_SE_FACTOR, MC_ABS_TOL = 4.0, 1e-4
N_MC_HEXES = 40
MAX_RING_VENUES = 12
N_COST_HEXES = 300
COST_K = [2.5, 3.3, 5.0]
WORKED_M5_K2 = {"geometric": [0.388, 0.225, 0.163, 0.125, 0.100], "poisson": [0.399, 0.252, 0.166, 0.110, 0.074]}
WORKED_M100_K33 = {1: 3.33, 10: 2.25, 50: 0.71, 100: 0.30}        # percent
WORKED_K = 1 / (1 - 0.7)                                            # the 108th's "k 3.3" is q 0.7's 1 / (1 - q)
WORKED_HALF_UNIT = (0.0005 + 1e-12, 0.005 + 1e-12)                  # half the printed last digit

# --- copies of functions/share_staged.py -----------------------------------------------------------------
GEOMETRIC, POISSON = "geometric", "poisson"
def look_weights(mean_looks, shape, tail_tol):
    """P(K = j), j = 1 .. L: K >= 1 with mean mean_looks; L the first j with P(K > j) < tail_tol, that tail folded into
    j = L so the weights sum to 1."""
    weights, total, j = [], 0.0, 1
    if shape == GEOMETRIC:
        stop = 1.0 / mean_looks
        chance = lambda j: stop * (1.0 - stop) ** (j - 1)
    elif shape == POISSON:
        rate = mean_looks - 1.0
        chance = lambda j: math.exp(-rate) * rate ** (j - 1) / math.factorial(j - 1)
    else:
        raise ValueError(f"unknown look-count shape {shape!r}")
    while True:
        weights.append(chance(j))
        total += weights[-1]
        if 1.0 - total < tail_tol:
            break
        j += 1
    weights[-1] += 1.0 - total
    return np.array(weights)


def avoid_chance(better, field, weights):
    """h(x, F): chance one stage of looks (weights from look_weights) misses all x marked venues in a field of F;
    a stage with K >= F sees the whole field; an empty field misses everything."""
    better = np.asarray(better, np.float64)
    field = np.asarray(field, np.float64)
    kept = np.ones(np.broadcast(better, field).shape)            # C(F - x, j) / C(F, j)
    out = np.zeros_like(kept)
    tail = 1.0                                                   # P(K >= j)
    for j, weight in enumerate(weights, start=1):
        kept *= np.clip(field - better - (j - 1), 0, None) / np.maximum(field - (j - 1), 1)
        out += np.where(j < field, weight, np.where(j == field, tail, 0.0)) * kept
        tail -= weight
        if j >= field.max(initial=0):
            break
    return np.where(field == 0, 1.0, out)


def ring_fields(counts):
    """Field per stage (hexes x stages): entrants of rings 1..s; counts (hexes x rings x cells)."""
    return np.cumsum(counts.sum(axis=2), axis=1)


def seen_chances(fields, weights):
    """Chance a venue of ring r is seen at all (hexes x rings): 1 - product over stages s >= r of h(1, F_s)."""
    miss = avoid_chance(np.minimum(fields, 1), fields, weights)
    return 1.0 - np.cumprod(miss[:, ::-1], axis=1)[:, ::-1]


def avoid_upper(counts, fields, weights):
    """A(cells >= c) for c = 0 .. cells (hexes x cells + 1; the last, nothing above, is 1)."""
    upper = np.cumsum(np.cumsum(counts[:, :, ::-1], axis=2)[:, :, ::-1], axis=1)   # hexes x stages x cells
    out = np.ones((counts.shape[0], counts.shape[2] + 1))
    out[:, :-1] = np.prod(avoid_chance(upper, fields[:, :, None], weights), axis=1)
    return out


def member_shares(counts, weights):
    """Each entrant's chance to be chosen (hexes x rings x cells), counts with every entrant (the subject included);
    the shares of all entrants sum to 1 in every hex with one."""
    fields = ring_fields(counts)
    avoid = avoid_upper(counts, fields, weights)
    group = avoid[:, 1:] - avoid[:, :-1]                         # the cell's group is chosen
    seen = seen_chances(fields, weights)
    split = np.einsum("hrc,hr->hc", counts, seen)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = group[:, None, :] * seen[:, :, None] / split[:, None, :]
    return np.where(counts > 0, out, 0.0)


def ring_indicator(subject_ring, n_stages):
    """1 in stages s >= the subject's ring (hexes x stages); subject_ring 0-based."""
    return (np.arange(n_stages)[None, :] >= subject_ring[:, None]).astype(np.float64)


def subject_shares(counts, subject_ring, focal_cells, weights):
    """The subject's share per hex at each focal cell (hexes x focal); counts (hexes x rings x cells) of the other
    entrants; subject_ring (hexes) 0-based. The subject joins the focal cell's group and the split by seen chance."""
    n_hexes, n_stages, _ = counts.shape
    subject_in = ring_indicator(subject_ring, n_stages)
    fields = ring_fields(counts) + subject_in
    seen = seen_chances(fields, weights)
    subject_seen = seen[np.arange(n_hexes), subject_ring]
    upper = np.cumsum(np.cumsum(counts[:, :, ::-1], axis=2)[:, :, ::-1], axis=1)
    upper = np.concatenate([upper, np.zeros((n_hexes, n_stages, 1))], axis=2)
    focal_cells = np.asarray(focal_cells)
    above = upper[:, :, focal_cells + 1]                         # hexes x stages x focal
    with_group = upper[:, :, focal_cells] + subject_in[:, :, None]
    group = (np.prod(avoid_chance(above, fields[:, :, None], weights), axis=1)
             - np.prod(avoid_chance(with_group, fields[:, :, None], weights), axis=1))
    tied_seen = np.einsum("hrf,hr->hf", counts[:, :, focal_cells], seen)
    return group * subject_seen[:, None] / (subject_seen[:, None] + tied_seen)


def contention_shares(counts, subject_ring, subject_cell, weights):
    """Each entrant's contention share (hexes x rings x cells): in the nearest occupied cell above the subject's, the
    share the subject gains by passing one of its venues of ring r; in the nearest below, the share it loses when one
    of ring r passes it; each venue holds its ring's change divided by its cell's occupants; zero elsewhere.
    counts (hexes x rings x cells) of the other entrants."""
    n_hexes, n_stages, n_cells = counts.shape
    subject_in = ring_indicator(subject_ring, n_stages)
    fields = ring_fields(counts) + subject_in
    seen = seen_chances(fields, weights)
    rows = np.arange(n_hexes)
    subject_seen = seen[rows, subject_ring]
    above = np.cumsum(counts[:, :, subject_cell + 1:].sum(axis=2), axis=1)              # hexes x stages
    tied = np.cumsum(counts[:, :, subject_cell], axis=1)
    tie_split = subject_seen / (subject_seen + np.einsum("hr,hr->h", counts[:, :, subject_cell], seen))

    def share(better):
        return (np.prod(avoid_chance(better, fields, weights), axis=1)
                - np.prod(avoid_chance(better + tied + subject_in, fields, weights), axis=1)) * tie_split

    base = share(above)
    occupied = counts.sum(axis=1) > 0                                                   # hexes x cells
    out = np.zeros_like(counts, dtype=np.float64)
    for side, cells in (("above", np.arange(subject_cell + 1, n_cells)), ("below", np.arange(subject_cell)[::-1])):
        if not len(cells):
            continue
        has = occupied[:, cells].any(axis=1)
        cell = cells[occupied[:, cells].argmax(axis=1)]
        cell_total = counts[rows, :, cell].sum(axis=1)
        for ring in range(n_stages):
            moved = (np.arange(n_stages)[None, :] >= ring).astype(np.float64)
            change = share(above - moved) - base if side == "above" else base - share(above + moved)
            is_held = has & (counts[rows, ring, cell] > 0)
            out[rows[is_held], ring, cell[is_held]] = change[is_held] / cell_total[is_held]
    return out


# --- tests ---
def flat_formula(rank, n_venues, weights):
    """One stage, no ties: sum_j p_j C(M - r, j - 1) / C(M, j), K beyond M seeing all M."""
    total, tail = 0.0, 1.0
    for j, weight in enumerate(weights, start=1):
        if j > n_venues:
            break
        p_j = weight if j < n_venues else tail
        total += p_j * math.comb(n_venues - rank, j - 1) / math.comb(n_venues, j)
        tail -= weight
    return total


def hex_counts(keys, rings, n_rings, cell_keys):
    """counts (1 x rings x cells) of venues by ring and key cell."""
    counts = np.zeros((1, n_rings, len(cell_keys)))
    np.add.at(counts, (0, rings, np.searchsorted(cell_keys, keys)), 1)
    return counts


def simulate(keys, rings, n_rings, mean_looks, rng, n_sims):
    """Monte Carlo of the stated process (independent stages, geometric K): each venue's chosen share and its SE."""
    n_venues = len(keys)
    seen = np.zeros((n_sims, n_venues), bool)
    for stage in range(n_rings):
        field = np.flatnonzero(rings <= stage)
        if not len(field):
            continue
        looks = np.minimum(rng.geometric(1.0 / mean_looks, n_sims), len(field))
        order = np.argsort(rng.random((n_sims, len(field))), axis=1)
        picked = np.arange(len(field))[None, :] < looks[:, None]
        sim_rows = np.repeat(np.arange(n_sims), len(field)).reshape(n_sims, len(field))
        seen[sim_rows[picked], field[order[picked]]] = True
    seen_keys = np.where(seen, keys[None, :], -np.inf)
    best = seen_keys.max(axis=1, keepdims=True)
    winners = seen & (seen_keys == best)
    chosen = winners / winners.sum(axis=1, keepdims=True)
    return chosen.mean(axis=0), chosen.std(axis=0) / np.sqrt(n_sims)


def avoid_minus_seen(better, fields, stop):
    """Exact chance of avoiding the marked venues when each stage draws only from venues not yet seen (geometric K,
    stop chance `stop` after each look); better and fields cumulative per stage."""
    n_max = int(sum(fields)) + 2
    entering = np.zeros(n_max)
    entering[0] = 1.0
    looks = np.arange(n_max)
    for field, marked in zip(fields, better):
        pool = field - looks
        current, leaving = entering.copy(), np.zeros(n_max)
        while current.sum() > 1e-16:
            is_open = pool > 0
            leaving += current * ~is_open
            current = current * is_open
            moved = np.zeros(n_max)
            with np.errstate(invalid="ignore", divide="ignore"):
                moved[1:] = np.where(is_open, current * (pool - marked) / pool, 0.0)[:-1]
            is_done = pool <= 0
            leaving += moved * np.where(is_done, 1.0, stop)
            current = moved * np.where(is_done, 0.0, 1.0 - stop)
        entering = leaving
    return entering.sum()


def contention_by_moves(other_counts, ring, cell, weights, n_rings):
    """Brute contention: per held (ring, cell), the subject-share change when one venue there crosses the subject,
    divided by the cell's occupants."""
    base = subject_shares(other_counts, ring, [cell], weights)[0, 0]
    out = {}
    for r_held in range(n_rings):
        for c_held in range(other_counts.shape[2]):
            if other_counts[0, r_held, c_held] == 0 or c_held == cell:
                continue
            moved = other_counts.copy()
            moved[0, r_held, c_held] -= 1
            if c_held > cell:                          # passed: the venue drops to a new bottom cell
                moved = np.concatenate([np.zeros((1, n_rings, 1)), moved], axis=2)
                moved[0, r_held, 0] += 1
                change = subject_shares(moved, ring, [cell + 1], weights)[0, 0] - base
            else:                                      # passes the subject: the venue rises to a new top cell
                moved = np.concatenate([moved, np.zeros((1, n_rings, 1))], axis=2)
                moved[0, r_held, -1] += 1
                change = base - subject_shares(moved, ring, [cell], weights)[0, 0]
            out[r_held, c_held] = change / other_counts[0, :, c_held].sum()
    return out


def main():
    rng = np.random.default_rng(SEED)
    rows = []

    def record(check, value, limit, is_judged=True):
        rows.append({"check": check, "value": value, "limit": limit, "pass": (value <= limit) if is_judged else None})
        verdict = "" if not is_judged else ("" if value <= limit else "  FAIL")
        print(f"  {check}: {value:.3g} (limit {limit:.3g}){'' if is_judged else ' (reported)'}{verdict}")

    print(f"{NAME}, run {RUN_DATE}")
    # (1) known values
    worst = 0.0
    flat = look_weights(1.0, GEOMETRIC, TAIL_TOL)
    for n_venues in (1, 2, 5, 37, 400):
        top = np.zeros(n_venues)
        top[-1] = 1.0                                                    # K = M: sees all
        counts = np.ones((1, 1, n_venues))
        shares = {k: member_shares(counts, look_weights(k, GEOMETRIC, TAIL_TOL))[0, 0] for k in (2.0, 3.3, 5.0)}
        share_flat, share_top = member_shares(counts, flat)[0, 0], member_shares(counts, top)[0, 0]
        for rank in range(1, n_venues + 1):
            cell = n_venues - rank
            worst = max(worst, abs(share_flat[cell] - 1 / n_venues), abs(share_top[cell] - (rank == 1)))
            for k, share in shares.items():
                weights = look_weights(k, GEOMETRIC, TAIL_TOL)
                worst = max(worst, abs(share[cell] - flat_formula(rank, n_venues, weights)))
    record("known values: K=1 flat, K=M top-1, one stage = formula", worst, EXACT_TOL)
    worst = 0.0
    for shape, values in WORKED_M5_K2.items():
        weights = look_weights(2.0, shape, TAIL_TOL)
        for rank, value in enumerate(values, start=1):
            worst = max(worst, abs(flat_formula(rank, 5, weights) - value) - WORKED_HALF_UNIT[0])
    weights = look_weights(WORKED_K, GEOMETRIC, TAIL_TOL)
    for rank, value in WORKED_M100_K33.items():
        worst = max(worst, abs(100 * flat_formula(rank, 100, weights) - value) - WORKED_HALF_UNIT[1])
    record("108th worked examples (within half a printed unit)", max(worst, 0.0), EXACT_TOL)

    # (2) Monte Carlo of the stated process
    for case in ("distinct", "one-ring ties", "cross-ring ties"):
        worst_z, worst_sum, worst_focal_z, worst_cont = 0.0, 0.0, 0.0, 0.0
        for _ in range(N_MC_HEXES):
            n_rings = int(rng.integers(1, 4))
            sizes = rng.integers(0, MAX_RING_VENUES + 1, n_rings)
            sizes[-1] = max(sizes[-1], 1)
            rings = np.repeat(np.arange(n_rings), sizes)
            if case == "distinct":
                keys = rng.permutation(len(rings)) * 2.0
            elif case == "one-ring ties":
                keys = (rings * 100 + rng.integers(0, 4, len(rings))) * 2.0
            else:
                keys = rng.integers(0, 4, len(rings)) * 2.0
            k = float(rng.choice([1.5, 2.5, 3.3, 5.0]))
            weights = look_weights(k, GEOMETRIC, TAIL_TOL)
            cell_keys = np.unique(keys)
            counts = hex_counts(keys, rings, n_rings, cell_keys)
            exact = member_shares(counts, weights)[0]
            worst_sum = max(worst_sum, abs((exact * counts[0]).sum() - 1))
            simulated, se = simulate(keys, rings, n_rings, k, rng, MC_SIMS)
            cells = np.searchsorted(cell_keys, keys)
            worst_z = max(worst_z, float((np.abs(exact[rings, cells] - simulated) - MC_SE_FACTOR * se).max()))
            if case != "distinct":
                continue
            subject = len(keys) - 1                    # the subject (last venue) at focal keys between the others'
            others = np.arange(subject)
            ring = rings[[subject]]
            focal_keys = np.arange(-1, 2 * len(keys) + 1, 2.0)
            all_keys = np.unique(np.concatenate([keys[others], focal_keys, keys[[subject]]]))
            other_counts = hex_counts(keys[others], rings[others], n_rings, all_keys)
            focal = np.searchsorted(all_keys, focal_keys)
            slider = subject_shares(other_counts, ring, focal, weights)[0]
            for j in rng.choice(len(focal_keys), min(3, len(focal_keys)), replace=False):
                moved = keys.copy()
                moved[subject] = focal_keys[j]
                sim, se = simulate(moved, rings, n_rings, k, rng, MC_SIMS)
                worst_focal_z = max(worst_focal_z, abs(slider[j] - sim[subject]) - MC_SE_FACTOR * se[subject])
            cell = int(np.searchsorted(all_keys, keys[subject]))
            cont = contention_shares(other_counts, ring, cell, weights)[0]
            brute = contention_by_moves(other_counts, ring, cell, weights, n_rings)
            for (r_held, c_held), value in brute.items():
                is_nearest = cont[r_held, c_held] != 0 or value == 0
                if is_nearest:
                    worst_cont = max(worst_cont, abs(cont[r_held, c_held] - value))
            nonzero = list(zip(*np.nonzero(cont)))
            worst_cont = max(worst_cont, *[abs(cont[rc] - brute.get(rc, np.inf)) for rc in nonzero], 0.0)
        is_judged = case != "cross-ring ties"
        record(f"MC {case}: worst |exact - MC| beyond 4 SE", max(worst_z, 0.0), MC_ABS_TOL, is_judged)
        record(f"MC {case}: shares sum to 1", worst_sum, EXACT_TOL)
        if case == "distinct":
            record("MC distinct: slider shares beyond 4 SE", max(worst_focal_z, 0.0), MC_ABS_TOL)
            record("contention = subject-share change / occupants (nearest cells)", worst_cont, EXACT_TOL)

    # (3) cost of independent stages vs "minus those seen"
    cost_rows = []
    for n_stages in (2, 3):
        for _ in range(N_COST_HEXES // 2):
            ring_sizes = [int(rng.integers(5, 301)), int(rng.integers(50, 2001))]
            if n_stages == 3:
                ring_sizes.append(int(rng.integers(1000, 14001)))
            better = [int(rng.binomial(n, rng.uniform(0, 0.15))) for n in ring_sizes]
            subject_ring = int(rng.integers(0, n_stages))
            in_stage = (np.arange(n_stages) >= subject_ring).astype(int)
            fields = np.cumsum(ring_sizes) + in_stage
            above = np.cumsum(better)
            for k in COST_K:
                weights = look_weights(k, GEOMETRIC, TAIL_TOL)
                independent = (np.prod(avoid_chance(above, fields, weights))
                               - np.prod(avoid_chance(above + in_stage, fields, weights)))
                exact = avoid_minus_seen(above, fields, 1 / k) - avoid_minus_seen(above + in_stage, fields, 1 / k)
                cost_rows.append({"stages": n_stages, "k": k, "subject_ring": subject_ring + 1,
                                  "ring_1": ring_sizes[0], "better_1": better[0], "independent": independent,
                                  "minus_seen": exact, "rel_diff": (independent - exact) / exact})
    cost_df = pd.DataFrame(cost_rows)
    cost_df.to_csv(COST_PATH, index=False)
    print("  cost (independent / minus-seen - 1), quantiles 0 / 50 / 95 / 100%:")
    for (n_stages, k), part in cost_df.groupby(["stages", "k"]):
        q = part.rel_diff.quantile([0, 0.5, 0.95, 1.0]).to_numpy()
        print(f"    {n_stages} stages, k {k}: {q[0]:+.4%} / {q[1]:+.4%} / {q[2]:+.4%} / {q[3]:+.4%}")
        rows.append({"check": f"cost {n_stages} stages k {k}: median rel diff (limit col: max)", "value": q[1],
                     "limit": q[3], "pass": None})
    pd.DataFrame(rows).to_csv(SUMMARY_PATH, index=False)
    judged = [row["pass"] for row in rows if row["pass"] is not None]
    print(f"{'PASS' if all(judged) else 'FAIL'} ({sum(judged)} / {len(judged)} judged checks); {SUMMARY_PATH.name}")


if __name__ == "__main__":
    main()
