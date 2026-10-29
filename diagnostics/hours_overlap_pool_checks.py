"""Does the hours-overlap pool chance separate venues by when they trade, or mostly thin the field evenly?

Claim tested: the "overlap" competitor pool (config SCORING_POOLS, scoring.pool_weights; scoring.md Notes "Hours-overlap
competitor pool", an idea, not decided) gives each competitor a chance of being in the subject's pool equal to the
share of its tag-predicted open time inside the subject's tag-predicted hours (slots where >= 50% of its tag peers
are open; subject's own hours blinded). If the chances are compressed (every type near the same value), the pool
mostly thins the field evenly, and the "overlap_flat" control (every competitor at the mean chance) should give
nearly the same share. Where the pipeline relies on it: the 96th's band 1-2 pool comparison.

Free checks (scoring.md Notes): cafe vs 24/7 separation; counts of near-24/7 and of high-rated low-overlap venues in
the subject's band 1-2 reach. Rules (Claude's, written before the run, not user-approved): near-24/7 = a venue's mean
open share over the week's slots (venue open-share table: own hours, else imputed) >= NEAR_ALL_DAY_SHARE;
low-overlap = pool chance < LOW_CHANCE; high-rated = displayed rating >= the subject's (4.8).

Self-contained (CLAUDE.md D1): imports nothing from functions/, config.py or pipeline modules. Reads the overlap run's
venue_keys.parquet (pool_chance), the venue open-share table, the venue table and the reach table. No API.

Conclusion (run 2026-10-24, pool chances of shares_448bc00302; subject's predicted hours 70 h a week): compressed.
Chances run 0.44-0.92, median 0.75; 50% of competitors sit at 0.72-0.75. The 7,529 generic-tag venues (only
"restaurant" and universal tags: VEN-8's coarse Legacy rows) all get exactly 0.75, the generic profile's value.
Mexican restaurants 0.72, bars 0.74, takeaways 0.69, fast food 0.63, cafes 0.57, coffee shops / breakfast 0.56, fuel
stations 0.49. Cafe vs 24/7: barely apart (0.57 vs 0.49 for the 132 near-24/7 venues), as the Note expected: both
spend about half their open time outside a dinner profile. Correlation with week open share -0.46. In band 1-2 reach:
6,052 competitors, expected 4,397 in pool (mean 0.73); 16 near-24/7; 906 rated >= 4.8, of which 139 below 0.6 (cafes,
brunch, bagels, kebabs). Reading: the pool mostly thins the field by ~0.73 evenly, with a mild discount on day
traders; the overlap_flat control isolates that. Tag profiles average over venues, so the separation a venue's own
hours would give is lost; any sharper version needs own hours (1,614 venues) or a different profile rule.
"""
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# --- paths ------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_TAG = "-37.76870_144.97196"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "scoring" / SUBJECT_TAG
VENUES_PATH = (PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT_TAG
               / f"venues_with_hex_ven20260925_{SUBJECT_TAG}.csv")
OPEN_SHARE_PATH = (PROJECT_ROOT / "outputs" / "opening_hours"
                   / "venue_open_share_ven20260925_hrs20260902-20261010_30min.parquet")
NAME = "hours_overlap_pool_checks"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
BY_TAG_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_by_tag.csv"
LOW_HIGH_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_high_rated_low_overlap.csv"
LOG_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"

# --- this diagnostic --------------------------------------------------------------------------------
POOL = "overlap"
BANDS = (1, 2)
SUBJECT_RATING = 4.8
NEAR_ALL_DAY_SHARE = 0.9
LOW_CHANCE = 0.6
DAY_TYPE_DAYS = {"Mon-Thu": 4, "Fri": 1, "Sat": 1, "Sun": 1}     # weekly weights of the open-share table's day types
TAGS = ["mexican_restaurant", "restaurant_only", "bar", "night_club", "meal_takeaway", "fast_food_restaurant",
        "cafe", "coffee_shop", "bakery", "breakfast_restaurant", "gas_station", "convenience_store"]
GENERIC_TAGS = {"restaurant", "food", "point_of_interest", "establishment"}


class Tee:
    def __init__(self, path):
        self.file = open(path, "w", encoding="utf-8")

    def write(self, text):
        sys.__stdout__.write(text)
        self.file.write(text)

    def flush(self):
        sys.__stdout__.flush()
        self.file.flush()


def overlap_folder():
    for stamp_path in sorted(SUBJECT_DIR.glob("reach_table_*/shares_*/stamp.json")):
        variant = json.loads(stamp_path.read_text(encoding="utf-8")).get("variant") or {}
        if variant.get("pool") == POOL and (stamp_path.parent / "venue_keys.parquet").exists():
            return stamp_path.parent
    raise FileNotFoundError("no overlap-pool shares folder with venue_keys.parquet")


def main():
    sys.stdout = Tee(LOG_PATH)
    folder = overlap_folder()
    print(f"{NAME} run {RUN_DATE}; pool chances from {folder.parent.name}/{folder.name}")
    keys_df = pd.read_parquet(folder / "venue_keys.parquet")
    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "name", "types", "rating", "user_ratings_total",
                                                  "hex_id"]).drop_duplicates("place_id")
    df = keys_df.merge(venues_df, on="place_id")
    open_df = pd.read_parquet(OPEN_SHARE_PATH, columns=["place_id", "day_type", "open_share"])
    open_df["weight"] = open_df.day_type.map(DAY_TYPE_DAYS)
    open_df["weighted"] = open_df.open_share * open_df.weight
    sums = open_df.groupby("place_id")[["weighted", "weight"]].sum()
    df["week_open_share"] = df.place_id.map(sums.weighted / sums.weight)

    tag_lists = df.types.fillna("").str.split("|")
    print(f"\npool chance over {len(df):,} competitors: " + ", ".join(
        f"{q:.0%} {df.pool_chance.quantile(q):.2f}" for q in [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1]))
    rows = []
    for tag in TAGS:
        if tag == "restaurant_only":
            mask = tag_lists.apply(lambda t: set(t) <= GENERIC_TAGS)
        else:
            mask = tag_lists.apply(lambda t: tag in t)
        sub = df[mask]
        rows.append({"tag": tag, "venues": len(sub), "mean": sub.pool_chance.mean(),
                     "q10": sub.pool_chance.quantile(0.1), "q90": sub.pool_chance.quantile(0.9),
                     "week_open_share": sub.week_open_share.mean()})
    by_tag_df = pd.DataFrame(rows)
    by_tag_df.to_csv(BY_TAG_PATH, index=False)
    print("\nby tag (pool chance; week_open_share = mean share of the week's slots open):")
    print(by_tag_df.to_string(index=False, float_format=lambda v: f"{v:.2f}"))

    near_all_day = df.week_open_share >= NEAR_ALL_DAY_SHARE
    print(f"\nnear-24/7 (week open share >= {NEAR_ALL_DAY_SHARE}): {near_all_day.sum():,} venues, pool chance mean "
          f"{df.pool_chance[near_all_day].mean():.2f}; others {df.pool_chance[~near_all_day].mean():.2f}")
    corr = np.corrcoef(df.week_open_share.fillna(df.week_open_share.mean()), df.pool_chance)[0, 1]
    print(f"correlation of pool chance with week open share: {corr:.2f}")

    table_dir = folder.parent
    subject_df = pd.read_parquet(table_dir / "subject_reach.parquet")
    hexes = np.unique(subject_df.hex_id[subject_df.band.isin(BANDS)].to_numpy())
    comp = pq.read_table(table_dir / "transit_competitor_reach.parquet", columns=["hex_id", "venue_hex"],
                         filters=[("band", "in", list(BANDS))])
    venue_hexes = np.unique(comp.column("venue_hex").to_numpy()[np.isin(comp.column("hex_id").to_numpy(), hexes)])
    in_reach = df.hex_id.isin(venue_hexes)
    high = df.rating >= SUBJECT_RATING - 1e-9
    low = df.pool_chance < LOW_CHANCE
    print(f"\nin band 1-2 reach: {in_reach.sum():,} competitors; near-24/7 {(in_reach & near_all_day).sum():,}; "
          f"rated >= {SUBJECT_RATING}: {(in_reach & high).sum():,}, of which pool chance < {LOW_CHANCE}: "
          f"{(in_reach & high & low).sum():,}")
    print(f"expected in-pool competitors in reach: {df.pool_chance[in_reach].sum():,.0f} of {in_reach.sum():,} "
          f"(mean {df.pool_chance[in_reach].mean():.2f}); rated >= {SUBJECT_RATING}: "
          f"{df.pool_chance[in_reach & high].sum():,.0f} of {(in_reach & high).sum():,}")
    low_high_df = df[in_reach & high & low].sort_values("user_ratings_total", ascending=False)
    low_high_df[["name", "types", "rating", "user_ratings_total", "pool_chance", "week_open_share"]].to_csv(
        LOW_HIGH_PATH, index=False)
    print(f"high-rated low-overlap venues in reach -> {LOW_HIGH_PATH.name}; top by reviews:")
    for _, r in low_high_df.head(10).iterrows():
        print(f"  {r['name'][:40]:40s} {r.rating} ({int(r.user_ratings_total)}) chance {r.pool_chance:.2f} "
              f"[{r.types}]")


if __name__ == "__main__":
    main()
