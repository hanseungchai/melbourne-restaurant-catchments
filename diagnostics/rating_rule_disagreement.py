"""How differently do the rating-rule candidates order the subject's band 1-2 competitors (DESIGN Q29)?

Claim: the share step orders every venue in reach by one rating key (SCR-20, S* as built). Q29 asks whether another
key orders the venues diners actually weigh against each other differently enough to matter, before any band rerun.
Where the pipeline relies on it: scoring.build_shares' rating key (config SCORING_RATING_KEY); the band 1-2 reruns
of the 96th session read the rules defined here.

Grade sheet (scoring.md Notes "Rating-rule grade sheet"; a grade argued over, not a hard bar, user): R1-R11 (Notes
"Rating-rule criteria"), R12 a lower displayed rating can overcome a higher one through review count, R13 thin-rating
inflation corrected (a thin 5.0 placed within its review-count peers), R14 near-equals tie (same displayed rating,
both well-reviewed), R15 blind plausibility (the user judges pairs the rules order differently, rules hidden).
Output effects are reported, not graded. Rules are conventions, not evidence (scoring is low-conviction, FRM-25).

Rules (r displayed rating, n review count; unrated = no rating or n = 0):
  F    flat displayed rating; equal displayed ratings tie; unrated below every rated venue (Google's sort; Claude's
       reading, no inference of ours).                                                          control (user)
  S*   shrunk s = (n r + m C) / (n + m), m 15, C 4.25 (SCR-20 as built); unrated at C.          control (user)
  S*'  S* with a displayed 5.0 read as 4.975 (the middle of 4.95-5.0).                          challenger
  P    percentile midrank of r among the P_NEIGHBOURS rated venues nearest in log n (the venue itself excluded);
       unrated below every rated venue. 250 and 1,000 reported as sensitivity.                  challenger
B, B~ and R are out of this session's scope (user, 96th).

Pairs (Claude's rules, written before the run, not user-approved): competitors (the subject excluded) whose venue
hexes reach a common subject band 1-2 hex at the reach table's floor, any slot; one pair per venue pair. Weighted two
ways: unweighted, and persons-weighted (residents + workers of the hexes the two share, summed; no reach chance).
A disagreement: the two rules order the pair differently (a tie under one and an order under the other counts).
Pair types (first match): unrated (either unrated); thin_top (one at >= 4.9 on <= 20 reviews, the other >= 100);
near_equal (|r difference| <= 0.1, both >= 100); mid_count (both 21-99); other.
Blind pairs: BLIND_N pairs on which the four rules don't all agree, sampled by persons weight within type quotas
(seeded); shown as (r, n) only, sides shuffled; the answer key is a separate file, opened only after the user judges.

Self-contained (CLAUDE.md D1): imports nothing from functions/, config.py or pipeline modules. No API.

Conclusion (run 2026-10-24, reach table 613829060a, venue table 2026-09-25): 6,052 competitors reach 5,015 subject
band 1-2 hexes; 12.9 M pairs. Share of pairs ordered differently (persons-weighted within 0.5 points of these):
  vs S*:  S*' 0.1% (thin_top 0.7%): reading 5.0 as 4.975 barely moves anything; F 13.9% (thin_top 51%, near_equal
          34%: F ties equal displayed ratings, S* splits them by count; unrated 32%: F puts them last, S* at C);
          P 8.2% (thin_top 27%, near_equal 15%, mid_count 3%).
  vs F:   P 10.4% (thin_top 25%, near_equal 39%: P splits equal ratings by count peers too).
P sits between F and S* on thin 5.0s: among few-review peers about half show 5.0, so a thin 5.0 lands mid-to-high
in its peer group (inflation corrected, R13) without S*'s pull toward C for noise. P250 / P1000 move thin_top by
5 points at most. Subject keys: S* 4.795, P 0.958 (P250 0.948, P1000 0.962). 30 blind pairs written for R15
(8 thin_top, 8 near_equal, 7 mid_count, 7 other). Output effects: the band 1-2 reruns (96th).
Judged by the user blind (2026-10-24; `_blind_pairs_judged.csv`): agreement S*' 21 / 30, S* 19, P 10, F 7. On the
22 pairs the user ordered, S*' 21, S* 19, P 10, F 1; on the 8 the user tied, only F ties (6). thin_top: S*' 8 / 8,
S* 6, P 0, F 0 (S*' and S* split on a 5.0 on 1 review vs 4.3 on ~180). The user's ties are same-rating pairs with
counts within ~1.5-2x (and 4.4 on 192 vs 4.3 on 1,983); larger count gaps were ordered by count. One judge,
30 pairs drawn from disagreements: illustration for R15, not a measurement.
"""
import datetime
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pyogrio

# --- paths ------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_TAG = "-37.76870_144.97196"
TABLE_DIR = PROJECT_ROOT / "outputs" / "scoring" / SUBJECT_TAG / "reach_table_613829060a"
VENUES_PATH = (PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT_TAG
               / f"venues_with_hex_ven20260925_{SUBJECT_TAG}.csv")
HEX_NODES_PATH = (PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT_TAG
                  / f"hex_population_and_nodes_res2021_wrk2021_ven20260925_{SUBJECT_TAG}.gpkg")
NAME = "rating_rule_disagreement"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SUMMARY_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_summary.csv"
KEYS_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_venue_keys.csv"
BLIND_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_blind_pairs.csv"
ANSWER_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_blind_pairs_ANSWER_KEY.csv"
LOG_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"

# --- this diagnostic --------------------------------------------------------------------------------
SUBJECT_LAT, SUBJECT_LON = -37.76870, 144.97196
BANDS = (1, 2)
SHRINK_M, SHRINK_C = 15, 4.25                 # SCR-20 as built (config SCORING_SHRINK_M, SCORING_SHRINK_C)
TOP_RATING, TOP_READ = 5.0, 4.975             # S*': a displayed 5.0 read as the middle of 4.95-5.0
P_NEIGHBOURS = 500
P_SENSITIVITY = [250, 1000]
RATING_DECIMALS = 1                           # displayed resolution
UNRATED_KEY = -1.0                            # below every rated key (F, P)
TIE_TOL = 1e-9
THIN_TOP_RATING, THIN_MAX_N, WELL_MIN_N = 4.9, 20, 100
NEAR_EQUAL_GAP = 0.1 + 1e-9
MID_MIN_N, MID_MAX_N = 21, 99
PAIR_TYPES = ["unrated", "thin_top", "near_equal", "mid_count", "other"]
BLIND_N = 30
BLIND_QUOTA = {"thin_top": 8, "near_equal": 8, "mid_count": 7, "other": 7}
SEED = 20261024
PAIR_CHUNK = 512                              # venues per row block of the pair matrices
RULES = ["F", "S*", "S*'", "P"]
CONTROLS = ["F", "S*"]


class Tee:
    def __init__(self, path):
        self.file = open(path, "w", encoding="utf-8")

    def write(self, text):
        sys.__stdout__.write(text)
        self.file.write(text)

    def flush(self):
        sys.__stdout__.flush()
        self.file.flush()


def is_rated(ratings, counts):
    return np.isfinite(ratings) & (counts > 0)


def flat_key(ratings, counts):
    return np.where(is_rated(ratings, counts), np.round(ratings, RATING_DECIMALS), UNRATED_KEY)


def shrunk_key(ratings, counts, read_top=False):
    r = np.where(is_rated(ratings, counts), np.nan_to_num(ratings, nan=SHRINK_C), SHRINK_C)
    if read_top:
        r = np.where(np.isclose(r, TOP_RATING), TOP_READ, r)
    n = np.where(counts > 0, counts, 0)
    return (n * r + SHRINK_M * SHRINK_C) / (n + SHRINK_M)


def percentile_key(ratings, counts, ref_ratings, ref_counts, n_neighbours, self_index):
    """Midrank percentile of each rating among the n_neighbours reference venues nearest in log count.

    self_index: each query's row in the reference (excluded from its own neighbours), -1 for none."""
    order = np.argsort(np.log(ref_counts), kind="stable")
    ref_log = np.log(ref_counts)[order]
    ref_r = np.round(ref_ratings[order], RATING_DECIMALS)
    position_of = np.empty(len(order), int)
    position_of[order] = np.arange(len(order))
    out = np.full(len(ratings), UNRATED_KEY)
    rated = is_rated(ratings, counts)
    for i in np.flatnonzero(rated):
        q_log = np.log(counts[i])
        pos = np.searchsorted(ref_log, q_log)
        lo, hi = max(pos - n_neighbours - 1, 0), min(pos + n_neighbours + 1, len(ref_log))
        window = np.arange(lo, hi)
        if self_index[i] >= 0:
            window = window[window != position_of[self_index[i]]]
        dist = np.abs(ref_log[window] - q_log)
        nearest = window[np.argsort(dist, kind="stable")[:n_neighbours]]
        r = round(float(ratings[i]), RATING_DECIMALS)
        below = (ref_r[nearest] < r - TIE_TOL).sum()
        equal = (np.abs(ref_r[nearest] - r) <= TIE_TOL).sum()
        out[i] = (below + 0.5 * equal) / len(nearest)
    return out


def pair_type(r_a, n_a, r_b, n_b):
    """Vectorised pair type label index (PAIR_TYPES order) for venue pairs."""
    unrated = ~is_rated(r_a, n_a) | ~is_rated(r_b, n_b)
    thin_a = (r_a >= THIN_TOP_RATING - TIE_TOL) & (n_a <= THIN_MAX_N) & (n_b >= WELL_MIN_N)
    thin_b = (r_b >= THIN_TOP_RATING - TIE_TOL) & (n_b <= THIN_MAX_N) & (n_a >= WELL_MIN_N)
    near = (np.abs(r_a - r_b) <= NEAR_EQUAL_GAP) & (n_a >= WELL_MIN_N) & (n_b >= WELL_MIN_N)
    mid = (n_a >= MID_MIN_N) & (n_a <= MID_MAX_N) & (n_b >= MID_MIN_N) & (n_b <= MID_MAX_N)
    return np.select([unrated, thin_a | thin_b, near, mid], [0, 1, 2, 3], default=4)


def order_sign(key, a, b):
    gap = key[a] - key[b]
    return np.where(np.abs(gap) <= TIE_TOL, 0, np.sign(gap)).astype(np.int8)


def main():
    sys.stdout = Tee(LOG_PATH)
    print(f"{NAME} run {RUN_DATE}; reach table {TABLE_DIR.name}")
    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "name", "rating", "user_ratings_total", "hex_id",
                                                  "lat", "lng"]).drop_duplicates("place_id").reset_index(drop=True)
    dist = np.hypot(venues_df.lat - SUBJECT_LAT, (venues_df.lng - SUBJECT_LON) * np.cos(np.radians(SUBJECT_LAT)))
    subject_row = int(dist.argmin())
    print(f"subject: {venues_df.name[subject_row]} ({venues_df.rating[subject_row]}, "
          f"{venues_df.user_ratings_total[subject_row]})")
    ratings = venues_df.rating.to_numpy(float)
    counts = venues_df.user_ratings_total.fillna(0).to_numpy(float)
    rated = is_rated(ratings, counts)
    ref_rows = np.flatnonzero(rated)
    self_index = np.full(len(venues_df), -1)
    self_index[ref_rows] = np.arange(len(ref_rows))

    keys = {"F": flat_key(ratings, counts), "S*": shrunk_key(ratings, counts),
            "S*'": shrunk_key(ratings, counts, read_top=True)}
    for k in [P_NEIGHBOURS] + P_SENSITIVITY:
        name = "P" if k == P_NEIGHBOURS else f"P{k}"
        keys[name] = percentile_key(ratings, counts, ratings[ref_rows], counts[ref_rows], k, self_index)
    keys_df = venues_df[["place_id", "name", "rating", "user_ratings_total", "hex_id"]].copy()
    for name, key in keys.items():
        keys_df[name] = key
    keys_df.to_csv(KEYS_PATH, index=False)
    print(f"keys for {len(venues_df):,} venues ({rated.sum():,} rated) -> {KEYS_PATH.name}")
    print("subject keys: " + ", ".join(f"{n} {k[subject_row]:.4f}" for n, k in keys.items()))

    subject_df = pd.read_parquet(TABLE_DIR / "subject_reach.parquet")
    subject_hexes = np.unique(subject_df.hex_id[subject_df.band.isin(BANDS)].to_numpy())
    comp = pq.read_table(TABLE_DIR / "transit_competitor_reach.parquet", columns=["band", "hex_id", "venue_hex"],
                         filters=[("band", "in", list(BANDS))])
    pair_code = np.unique(comp.column("hex_id").to_numpy().astype(np.int64) * 2 ** 32
                          + comp.column("venue_hex").to_numpy().astype(np.int64))
    del comp
    hex_of, vhex_of = pair_code // 2 ** 32, pair_code % 2 ** 32
    keep = np.isin(hex_of, subject_hexes)
    hex_of, vhex_of = hex_of[keep], vhex_of[keep]
    pop_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False, columns=["hex_id", "residents", "workers"])
    persons_of = (pop_df.residents.fillna(0) + pop_df.workers.fillna(0)).groupby(pop_df.hex_id).sum()

    in_reach = venues_df.hex_id.isin(np.unique(vhex_of)).to_numpy().copy()
    in_reach[subject_row] = False
    rows = np.flatnonzero(in_reach)
    print(f"{len(subject_hexes):,} subject band 1-2 hexes; {len(np.unique(vhex_of)):,} venue hexes; "
          f"{len(rows):,} competitor venues in reach")
    from scipy import sparse
    vhexes = np.unique(vhex_of)
    hexes = np.unique(hex_of)
    vpos = pd.Series(np.arange(len(vhexes)), index=vhexes)
    hpos = pd.Series(np.arange(len(hexes)), index=hexes)
    incidence = sparse.csr_matrix((np.ones(len(hex_of)), (hpos[hex_of].to_numpy(), vpos[vhex_of].to_numpy())),
                                  shape=(len(hexes), len(vhexes)))
    weighted = sparse.diags(persons_of.reindex(hexes).fillna(0).to_numpy()) @ incidence
    shared_persons = (incidence.T @ weighted).toarray()        # venue hex x venue hex: persons of shared hexes
    shared_any = (incidence.T @ incidence).toarray() > 0
    venue_vpos = vpos[venues_df.hex_id.to_numpy()[rows]].to_numpy()

    rules = RULES + [f"P{k}" for k in P_SENSITIVITY]
    tallies = []                                              # (type, rule, control, unweighted, persons)
    totals = np.zeros((len(PAIR_TYPES), 2))
    rng = np.random.default_rng(SEED)
    candidates = []
    r_rows, n_rows = ratings[rows], counts[rows]
    sub_keys = {name: keys[name][rows] for name in rules}
    for start in range(0, len(rows), PAIR_CHUNK):
        a_local = np.arange(start, min(start + PAIR_CHUNK, len(rows)))
        a_idx, b_idx = np.meshgrid(a_local, np.arange(len(rows)), indexing="ij")
        upper = b_idx > a_idx
        a_idx, b_idx = a_idx[upper], b_idx[upper]
        share = shared_any[venue_vpos[a_idx], venue_vpos[b_idx]]
        a_idx, b_idx = a_idx[share], b_idx[share]
        persons = shared_persons[venue_vpos[a_idx], venue_vpos[b_idx]]
        types = pair_type(r_rows[a_idx], n_rows[a_idx], r_rows[b_idx], n_rows[b_idx])
        signs = {name: order_sign(sub_keys[name], a_idx, b_idx) for name in rules}
        for t in range(len(PAIR_TYPES)):
            is_t = types == t
            totals[t] += [is_t.sum(), persons[is_t].sum()]
            for control in CONTROLS:
                for name in rules:
                    if name == control:
                        continue
                    differ = is_t & (signs[name] != signs[control])
                    tallies.append((PAIR_TYPES[t], name, control, differ.sum(), persons[differ].sum()))
        main_signs = np.stack([signs[name] for name in RULES])
        split = (main_signs != main_signs[0]).any(axis=0)
        for t_name in BLIND_QUOTA:
            pick = np.flatnonzero(split & (types == PAIR_TYPES.index(t_name)) & (persons > 0))
            if len(pick):
                # Gumbel-top-k over the whole run: keep each chunk's best scores, choose at the end
                score = np.log(persons[pick]) - np.log(-np.log(rng.random(len(pick))))
                best = pick[np.argsort(-score)[:BLIND_QUOTA[t_name]]]
                candidates += [(t_name, s, rows[a_idx[i]], rows[b_idx[i]], persons[i])
                               for i, s in zip(best, score[np.argsort(-score)[:BLIND_QUOTA[t_name]]])]

    tally_df = pd.DataFrame(tallies, columns=["pair_type", "rule", "control", "pairs_differ", "persons_differ"])
    tally_df = tally_df.groupby(["pair_type", "rule", "control"], as_index=False).sum()
    total_df = pd.DataFrame(totals, columns=["pairs", "persons"], index=PAIR_TYPES).rename_axis("pair_type")
    all_df = tally_df.groupby(["rule", "control"], as_index=False)[["pairs_differ", "persons_differ"]].sum()
    all_df.insert(0, "pair_type", "all")
    tally_df = pd.concat([tally_df, all_df], ignore_index=True)
    total_df.loc["all"] = total_df.sum()
    tally_df = tally_df.merge(total_df.reset_index(), on="pair_type")
    tally_df["share_pairs"] = tally_df.pairs_differ / tally_df.pairs
    tally_df["share_persons"] = tally_df.persons_differ / tally_df.persons
    tally_df.to_csv(SUMMARY_PATH, index=False)
    print("\npairs per type (unweighted, persons-weighted):")
    print(total_df.to_string(float_format=lambda v: f"{v:,.0f}"))
    print("\nshare of pairs ordered differently from each control:")
    wide = tally_df.pivot_table(index=["pair_type"], columns=["control", "rule"], values="share_pairs")
    print(wide.reindex(PAIR_TYPES + ["all"]).to_string(float_format=lambda v: f"{v:.1%}"))
    print("\nsame, persons-weighted:")
    wide = tally_df.pivot_table(index=["pair_type"], columns=["control", "rule"], values="share_persons")
    print(wide.reindex(PAIR_TYPES + ["all"]).to_string(float_format=lambda v: f"{v:.1%}"))

    cand_df = pd.DataFrame(candidates, columns=["pair_type", "score", "row_a", "row_b", "persons"])
    cand_df = cand_df.sort_values("score", ascending=False).drop_duplicates(["row_a", "row_b"])
    cand_df = cand_df[cand_df.groupby("pair_type").cumcount() < cand_df.pair_type.map(BLIND_QUOTA)]
    cand_df = cand_df.sample(frac=1, random_state=SEED).reset_index(drop=True)
    flip = rng.random(len(cand_df)) < 0.5
    left = np.where(flip, cand_df.row_b, cand_df.row_a)
    right = np.where(flip, cand_df.row_a, cand_df.row_b)
    blind_df = pd.DataFrame({"pair": np.arange(1, len(cand_df) + 1),
                             "A_rating": ratings[left], "A_reviews": counts[left].astype(int),
                             "B_rating": ratings[right], "B_reviews": counts[right].astype(int),
                             "your_pick (A / B / tie)": ""})
    blind_df.to_csv(BLIND_PATH, index=False)
    answer_df = blind_df.iloc[:, :5].copy()
    answer_df["pair_type"] = cand_df.pair_type.to_numpy()
    answer_df["shared_persons"] = cand_df.persons.round().to_numpy()
    answer_df["A_name"], answer_df["B_name"] = venues_df.name.to_numpy()[left], venues_df.name.to_numpy()[right]
    for name in RULES:
        sign = np.sign(np.where(np.abs(keys[name][left] - keys[name][right]) <= TIE_TOL, 0,
                                keys[name][left] - keys[name][right]))
        answer_df[name] = np.select([sign > 0, sign < 0], ["A", "B"], default="tie")
    answer_df.to_csv(ANSWER_PATH, index=False)
    print(f"\n{len(blind_df)} blind pairs -> {BLIND_PATH.name}; answer key -> {ANSWER_PATH.name}")
    print("blind pair types:", cand_df.pair_type.value_counts().to_dict())


if __name__ == "__main__":
    main()
