"""Band-3 flower merging: how much of a diner's transit field the merged origin misplaces (RCH-27).

Claim: routing band-3 diners' transit fields from threshold-then-weighted flower points, T 20 persons for the 10-min
stage (band 1) and T 80 for the 20-min stage (band 2), misplaces about 0.1% and 3% of the fields' persons-weighted
mass, with a bias of at most ~0.1%, against each hex's own route.
Where the pipeline relies on it: config.REACH_BAND3_MERGE_PERSONS (transit_band3.py, functions/transit_targeting.py):
the band-3 pass routes merged points instead of every populated hex.

Method (the 111th's ad hoc test, made a D1 diagnostic in the 112th): 200 aperture-7 flowers (seed 20261026), every
populated member a band-3 hex inside the subject pass's Mon-Thu 19:00 +90 min envelope, so each member has its own exact
route there. Per threshold T, the members with persons < T are routed from their persons-weighted centroid (saved
routes, 90 departure minutes, 31-min search); members >= T keep their own route. Per member m and stage cut c,
p_m(v) = share of the 90 minutes in which venue hex v is reached within c (no trip-time error model: a plain cut).
Field error E = sum_v |p_point(v) - p_m(v)| / sum_v p_m(v) (gains and losses both count), bias = (sum p_point -
sum p_m) / sum p_m, persons-weighted over every member (own-route members count 0). The member's own hex is left out.

Self-contained (D1): reads the hex layer, the reach table's subject rows (band-3 set), the subject pass's envelopes and
times, and the saved point routes; routes nothing. If the saved routes are missing it stops (routing them needs R5;
rerun the 111th's ad hoc flower_error.py).

Conclusion (2026-10-26): T20 at 10 min misplaces 0.09% of the field (bias +0.004%; 1.7% of persons merged); T80 at
20 min 2.9% (bias -0.06%; 58% of persons merged). Both small next to band 2's ~10% model error; the claim holds.
"""
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyogrio

PROJECT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT / "diagnostics" / "diagnostic_data"
NAME = "band3_flower_merge_error"
SUBJECT_DIR = "-37.76870_144.97196"
TRANSIT_PASS = PROJECT / "outputs" / "reachability" / SUBJECT_DIR / "transit_86cb259c15"
REACH_TABLE = PROJECT / "outputs" / "scoring" / SUBJECT_DIR / "reach_table_f68f32d6c9"
ROUTES_DIR = DATA_DIR / "band3_routing_adhoc_20261026" / "routes" / "flower_points_n200"   # saved 2026-10-26
CHUNK = "Mon-Thu_1900_90min"
WINDOW_MIN = 90
N_FLOWERS = 200
SEED = 20261026
THRESHOLDS = [10, 20, 40, 80, np.inf]        # the ad hoc set, in its order (point ids follow it)
CHOSEN = {10: 20, 20: 80}                    # stage cut (min) -> chosen T (config.REACH_BAND3_MERGE_PERSONS)
STAGE_CUTS_MIN = [10, 20]
MIN_PERSONS = 1.0                            # config.REACH_POPULATED_MIN_PERSONS
BAND3 = 3
SECONDS_PER_MIN = 60
TO_CENTRE = {1: (-1, 0), 6: (1, 0), 3: (0, -1), 4: (0, 1), 5: (-1, 1), 2: (1, -1)}   # v = (q + 3r) mod 7 -> centre step
HEX_COLUMNS = ["hex_id", "q", "r", "centroid_lat", "centroid_lon", "residents", "workers"]


def flower_keys(q, r):
    q, r = np.asarray(q, np.int64), np.asarray(r, np.int64)
    v = (q + 3 * r) % 7
    cq, cr = q.copy(), r.copy()
    for value, (dq, dr) in TO_CENTRE.items():
        cq[v == value] += dq
        cr[v == value] += dr
    assert ((cq + 3 * cr) % 7 == 0).all()
    return cq * 100_000 + cr


def reach_shares(df, cut_min):
    minutes = df[[f"m{m:02d}" for m in range(WINDOW_MIN)]].to_numpy()
    p = (minutes <= cut_min * SECONDS_PER_MIN).mean(axis=1)
    out = pd.Series(p, index=pd.MultiIndex.from_arrays([df.origin_hex.to_numpy(), df.dest_hex.to_numpy()]))
    return out[out > 0]


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    if not any(ROUTES_DIR.glob("times_*.parquet")):
        sys.exit(f"saved point routes missing in {ROUTES_DIR}: rerun the 111th's ad hoc flower_error.py (R5)")
    print(f"reusing saved point routes from 2026-10-26 ({ROUTES_DIR.relative_to(PROJECT)})")
    stamp = json.loads((TRANSIT_PASS / "stamp.json").read_text(encoding="utf-8"))
    hex_df = pyogrio.read_dataframe(PROJECT / stamp["inputs"]["hex_nodes"]["path"], read_geometry=False,
                                    columns=HEX_COLUMNS)
    hex_df["persons"] = hex_df.residents.fillna(0) + hex_df.workers.fillna(0)
    hex_df["flower"] = flower_keys(hex_df.q, hex_df.r)
    subject_df = pd.read_parquet(REACH_TABLE / "subject_reach.parquet", columns=["band", "hex_id"])
    band3 = set(subject_df.loc[subject_df.band == BAND3, "hex_id"].unique())
    envelope = set(pd.read_csv(TRANSIT_PASS / CHUNK / "envelope.csv", usecols=["hex_id"]).hex_id)

    populated = hex_df[hex_df.persons >= MIN_PERSONS]
    size = hex_df.groupby("flower").size()
    by_flower = populated.groupby("flower").agg(
        n=("hex_id", "size"), inside=("hex_id", lambda h: all(x in envelope and x in band3 for x in h)))
    candidates = by_flower[(by_flower.n >= 2) & by_flower.inside & (size.reindex(by_flower.index) == 7)].index
    picked = np.random.default_rng(SEED).choice(np.asarray(candidates), size=min(N_FLOWERS, len(candidates)),
                                                replace=False)
    members_df = populated[populated.flower.isin(picked)]
    assign, point_id = [], -1                    # (member, variant, point id or None for its own route)
    for flower, group in members_df.groupby("flower"):
        for threshold in THRESHOLDS:
            light = group[group.persons < threshold]
            if len(light):
                assign += [(h, threshold, point_id) for h in light.hex_id]
                point_id -= 1
            assign += [(h, threshold, None) for h in group.hex_id[group.persons >= threshold]]
        point_id -= 1                            # the ad hoc geometric-centre point (not read here)
    assign_df = pd.DataFrame(assign, columns=["hex_id", "threshold", "point_id"])
    point_rows = pd.concat([pd.read_parquet(p) for p in sorted(ROUTES_DIR.glob("times_*.parquet"))], ignore_index=True)
    assert point_rows.origin_hex.min() >= point_id + 1, "saved routes do not match the recomputed points"
    own_rows = ds.dataset(sorted((TRANSIT_PASS / CHUNK).glob("times_*.parquet"))).to_table(
        filter=ds.field("origin_hex").isin(members_df.hex_id.astype(np.int32).tolist())).to_pandas()
    persons = members_df.set_index("hex_id").persons
    print(f"{len(picked)} flowers, {len(members_df):,} populated members ({members_df.persons.sum():,.0f} persons); "
          f"{point_rows.origin_hex.nunique():,} routed points")

    rows = []
    for cut in STAGE_CUTS_MIN:
        own, pts = reach_shares(own_rows, cut), reach_shares(point_rows, cut)
        own_ids, pt_ids = set(own.index.get_level_values(0)), set(pts.index.get_level_values(0))
        for threshold, group in assign_df.groupby("threshold"):
            diffs, gains, sizes, weights = [], [], [], []
            for hex_id, pid in zip(group.hex_id, group.point_id):
                mine = own.loc[hex_id].drop(hex_id, errors="ignore") if hex_id in own_ids else pd.Series(dtype=float)
                if pd.isna(pid):
                    theirs = mine
                else:
                    theirs = (pts.loc[int(pid)].drop(hex_id, errors="ignore") if int(pid) in pt_ids
                              else pd.Series(dtype=float))
                both = pd.concat([mine, theirs], axis=1).fillna(0)
                diffs.append((both.iloc[:, 0] - both.iloc[:, 1]).abs().sum())
                gains.append(theirs.sum() - mine.sum())
                sizes.append(mine.sum())
                weights.append(persons[hex_id])
            diffs, gains, sizes, weights = map(np.asarray, (diffs, gains, sizes, weights))
            is_merged = ~group.point_id.isna().to_numpy()
            rows.append({"cut_min": cut, "threshold": threshold, "is_chosen": CHOSEN[cut] == threshold,
                         "persons_merged_pct": 100 * weights[is_merged].sum() / weights.sum(),
                         "field_error_pct": 100 * (weights * diffs).sum() / (weights * sizes).sum(),
                         "field_bias_pct": 100 * (weights * gains).sum() / (weights * sizes).sum()})
    result = pd.DataFrame(rows)
    out_path = DATA_DIR / f"{NAME}_{run_date}_summary.csv"
    result.to_csv(out_path, index=False)
    with pd.option_context("display.width", 160):
        print(result.round(3).to_string(index=False))
    chosen = result[result.is_chosen]
    print("chosen: " + "; ".join(f"T{t:.0f} at {c} min: error {e:.2f}%, bias {b:+.3f}%" for c, t, e, b in
                                  zip(chosen.cut_min, chosen.threshold, chosen.field_error_pct, chosen.field_bias_pct)))
    print(f"saved {out_path.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
