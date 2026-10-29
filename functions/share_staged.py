"""Staged best-of-K share rule (SCR-23, DESIGN Q32): closed form per hex from entrant counts per ring and key cell.

A band-b diner searches b stages; stage s draws K_s looks without replacement from its field F_s (every entrant of
rings 1..s, the bands nested) and the best by the key among all venues seen wins; tied venues split. K_s is drawn
afresh per stage, geometric with mean k (Poisson the sensitivity), K beyond the field seeing the whole field.

Build choice (Claude's, 2026-10-26, not user-approved): stages are independent, so a later stage may look again at an
inner venue already seen (a wasted look) instead of drawing only from the unseen (the 108th's "minus those seen",
which couples the stages through the looks spent; ~100x the cost). Measured in diagnostics/best_of_k_checks.py.

Avoiding a set X: one stage h(x, F) = sum_j P(K = j) C(F - x, j) / C(F, j); all stages: the product over s of
h(x_s, F_s), x_s the members of X in F_s. A cell's group wins when all better venues are avoided and not all of the
cell is: A(cells > c) - A(cells >= c). Within a cell the group's chance is split by each member's chance of being seen
(1 - product over the stages holding it of h(1, F_s)): exact for a cell of one venue or of one ring; interval cells
are approximate for credits only, their sum exact (as SCR-19's cells).

Every function takes a weight table (weight_table: one row of look weights per mean k) and returns a leading axis of
one entry per row, so the whole k grid shares one pass over the looks (110th: the product C(F - x, j) / C(F, j) does
not depend on k). h runs in a compiled, threaded loop (numba): one element at a time, no array temporaries.
Evidence: diagnostics/best_of_k_checks.py (closed form vs known values and Monte Carlo; cost of independent stages).

GPU (DESIGN Q32, 116th): the share functions run on NumPy or CuPy arrays alike, picked from the counts (and the weight
table, which must sit on the same device); h on the GPU is a CUDA twin of the numba loop, float64 as on the CPU (the
shares subtract near-equal avoid chances). CuPy is imported only when a CuPy array arrives.
"""
import math

import numba
import numpy as np

GEOMETRIC, POISSON = "geometric", "poisson"
GPU_THREADS_PER_BLOCK = 256

_AVOID_CUDA_SOURCE = r"""
extern "C" __global__ void avoid_kernel(const double* better, const double* field, const double* table,
                                        const double* tails, double* out, long long size, int n_rows, int width) {
    long long n = (long long)blockIdx.x * blockDim.x + threadIdx.x;
    if (n >= size) return;
    double x = better[n], f = field[n];
    if (f == 0.0) {
        for (int m = 0; m < n_rows; m++) out[m * size + n] = 1.0;
        return;
    }
    double kept = 1.0;                                           // C(F - x, j) / C(F, j)
    int last = min(width, (int)f);
    for (int j = 1; j <= last; j++) {
        kept *= fmax(f - x - (j - 1), 0.0) / fmax(f - (j - 1), 1.0);
        if (kept == 0.0) break;
        const double* weight = (j < f) ? table : tails;          // K >= F sees the whole field
        for (int m = 0; m < n_rows; m++) out[m * size + n] += weight[m * width + j - 1] * kept;
    }
}
"""
_avoid_cuda = None                                               # compiled on first GPU call


def array_module(array):
    """numpy, or cupy for a CuPy array (imported only then)."""
    if type(array).__module__.split(".")[0] == "cupy":
        import cupy
        return cupy
    return np


def weights_to(xp, weights):
    """A weight table (from weight_table) on the device of array module xp."""
    return tuple(xp.asarray(part) for part in weights)


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


def weight_table(weights_list):
    """(P(K = j), P(K >= j)) for j = 1 .. the longest L, one row per entry of weights_list (each from look_weights),
    zero past its own L."""
    width = max(len(weights) for weights in weights_list)
    table = np.zeros((len(weights_list), width))
    for m, weights in enumerate(weights_list):
        table[m, :len(weights)] = weights
    tails = np.clip(1.0 - np.cumsum(table, axis=1) + table, 0.0, None)
    return table, tails


@numba.njit(parallel=True, cache=True)
def _avoid_kernel(better, field, table, tails, out):
    n_rows, width = table.shape
    for n in numba.prange(better.size):
        x, f = better[n], field[n]
        if f == 0:
            out[:, n] = 1.0
            continue
        kept = 1.0                                               # C(F - x, j) / C(F, j)
        for j in range(1, min(width, int(f)) + 1):
            kept *= max(f - x - (j - 1), 0.0) / max(f - (j - 1), 1.0)
            if kept == 0.0:
                break
            if j < f:
                for m in range(n_rows):
                    out[m, n] += table[m, j - 1] * kept
            else:                                                # K >= F sees the whole field
                for m in range(n_rows):
                    out[m, n] += tails[m, j - 1] * kept


def avoid_chance(better, field, weights):
    """h(x, F) per weight-table row (rows x the broadcast shape): chance one stage of looks misses all x marked venues
    in a field of F; a stage with K >= F sees the whole field; an empty field misses everything."""
    xp = array_module(field)
    table, tails = weights
    better, field = xp.broadcast_arrays(xp.asarray(better, xp.float64), xp.asarray(field, xp.float64))
    shape = better.shape
    out = xp.zeros((len(table), better.size))
    better, field = xp.ascontiguousarray(better).ravel(), xp.ascontiguousarray(field).ravel()
    if xp is np:
        _avoid_kernel(better, field, table, tails, out)
    else:
        _avoid_gpu(xp, better, field, table, tails, out)
    return out.reshape((len(table),) + shape)


def _avoid_gpu(cp, better, field, table, tails, out):
    global _avoid_cuda
    if _avoid_cuda is None:
        _avoid_cuda = cp.RawKernel(_AVOID_CUDA_SOURCE, "avoid_kernel")
    size, (n_rows, width) = better.size, table.shape
    n_blocks = (size + GPU_THREADS_PER_BLOCK - 1) // GPU_THREADS_PER_BLOCK
    _avoid_cuda((max(n_blocks, 1),), (GPU_THREADS_PER_BLOCK,),
                (better, field, cp.ascontiguousarray(table, cp.float64), cp.ascontiguousarray(tails, cp.float64), out,
                 np.int64(size), np.int32(n_rows), np.int32(width)))


def ring_fields(counts):
    """Field per stage (hexes x stages): entrants of rings 1..s; counts (hexes x rings x cells)."""
    xp = array_module(counts)
    return xp.cumsum(counts.sum(axis=2), axis=1)


def seen_chances(fields, weights):
    """Chance a venue of ring r is seen at all (rows x hexes x rings): 1 - product over stages s >= r of h(1, F_s)."""
    xp = array_module(fields)
    miss = avoid_chance(xp.minimum(fields, 1), fields, weights)
    return 1.0 - xp.cumprod(miss[:, :, ::-1], axis=2)[:, :, ::-1]


def avoid_upper(counts, fields, weights):
    """A(cells >= c) for c = 0 .. cells (rows x hexes x cells + 1; the last, nothing above, is 1)."""
    xp = array_module(counts)
    upper = xp.cumsum(xp.cumsum(counts[:, :, ::-1], axis=2)[:, :, ::-1], axis=1)   # hexes x stages x cells
    out = xp.ones((len(weights[0]), counts.shape[0], counts.shape[2] + 1))
    out[:, :, :-1] = xp.prod(avoid_chance(upper, fields[:, :, None], weights), axis=2)
    return out


def member_shares(counts, weights):
    """Each entrant's chance to be chosen (rows x hexes x rings x cells), counts with every entrant (the subject
    included); the shares of all entrants sum to 1 in every hex with one."""
    xp = array_module(counts)
    fields = ring_fields(counts)
    avoid = avoid_upper(counts, fields, weights)
    group = avoid[:, :, 1:] - avoid[:, :, :-1]                   # the cell's group is chosen
    seen = seen_chances(fields, weights)
    split = xp.einsum("hrc,khr->khc", counts, seen)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = group[:, :, None, :] * seen[:, :, :, None] / split[:, :, None, :]
    return xp.where(counts > 0, out, 0.0)


def ring_indicator(subject_ring, n_stages):
    """1 in stages s >= the subject's ring (hexes x stages); subject_ring 0-based."""
    xp = array_module(subject_ring)
    return (xp.arange(n_stages)[None, :] >= subject_ring[:, None]).astype(xp.float64)


def subject_shares(counts, subject_ring, focal_cells, weights):
    """The subject's share per hex at each focal cell (rows x hexes x focal); counts (hexes x rings x cells) of the
    other entrants; subject_ring (hexes) 0-based. The subject joins the focal cell's group and the split by seen
    chance."""
    xp = array_module(counts)
    n_hexes, n_stages, _ = counts.shape
    subject_in = ring_indicator(subject_ring, n_stages)
    fields = ring_fields(counts) + subject_in
    seen = seen_chances(fields, weights)
    subject_seen = seen[:, xp.arange(n_hexes), subject_ring]     # rows x hexes
    upper = xp.cumsum(xp.cumsum(counts[:, :, ::-1], axis=2)[:, :, ::-1], axis=1)
    upper = xp.concatenate([upper, xp.zeros((n_hexes, n_stages, 1))], axis=2)
    focal_cells = xp.asarray(focal_cells)
    above = upper[:, :, focal_cells + 1]                         # hexes x stages x focal
    with_group = upper[:, :, focal_cells] + subject_in[:, :, None]
    group = (xp.prod(avoid_chance(above, fields[:, :, None], weights), axis=2)
             - xp.prod(avoid_chance(with_group, fields[:, :, None], weights), axis=2))
    tied_seen = xp.einsum("hrf,khr->khf", counts[:, :, focal_cells], seen)
    return group * subject_seen[:, :, None] / (subject_seen[:, :, None] + tied_seen)


def contention_shares(counts, subject_ring, subject_cell, weights):
    """Each entrant's contention share (rows x hexes x rings x cells): in the nearest occupied cell above the
    subject's, the share the subject gains by passing one of its venues of ring r; in the nearest below, the share it
    loses when one of ring r passes it; each venue holds its ring's change divided by its cell's occupants; zero
    elsewhere. counts (hexes x rings x cells) of the other entrants."""
    xp = array_module(counts)
    n_hexes, n_stages, n_cells = counts.shape
    subject_in = ring_indicator(subject_ring, n_stages)
    fields = ring_fields(counts) + subject_in
    seen = seen_chances(fields, weights)
    rows = xp.arange(n_hexes)
    subject_seen = seen[:, rows, subject_ring]                                          # rows x hexes
    above = xp.cumsum(counts[:, :, subject_cell + 1:].sum(axis=2), axis=1)              # hexes x stages
    tied = xp.cumsum(counts[:, :, subject_cell], axis=1)
    tie_split = subject_seen / (subject_seen + xp.einsum("hr,khr->kh", counts[:, :, subject_cell], seen))

    def share(better):
        return (xp.prod(avoid_chance(better, fields, weights), axis=2)
                - xp.prod(avoid_chance(better + tied + subject_in, fields, weights), axis=2)) * tie_split

    base = share(above)
    occupied = counts.sum(axis=1) > 0                                                   # hexes x cells
    out = xp.zeros((len(weights[0]),) + counts.shape)
    for side, cells in (("above", xp.arange(subject_cell + 1, n_cells)), ("below", xp.arange(subject_cell)[::-1])):
        if not len(cells):
            continue
        has = occupied[:, cells].any(axis=1)
        cell = cells[occupied[:, cells].argmax(axis=1)]
        cell_total = counts[rows, :, cell].sum(axis=1)
        for ring in range(n_stages):
            moved = (xp.arange(n_stages)[None, :] >= ring).astype(xp.float64)
            change = share(above - moved) - base if side == "above" else base - share(above + moved)
            is_held = has & (counts[rows, ring, cell] > 0)
            out[:, rows[is_held], ring, cell[is_held]] = change[:, is_held] / cell_total[is_held]
    return out
