"""How often is a venue in a diner's transit field (bands 1-2) outside the same diner's drive field (band 3)?

Claim: staged best-of-K (SCR-23, DESIGN Q32 (4)) nests the bands: a band-3 diner's stages run over band 1's field,
then band 2's, then band 3's, each field holding the one before. Bands 1-2 are walk + transit and band 3 is drive, so
nesting is not guaranteed: a venue next to a station can be within 20 min by train and beyond 20 min by car. Where the
pipeline relies on it: the band-3 build of staged best-of-K (not built; Q32 owed "band 3 nesting check").

Method: the subject's reach table (the run of record's, reach_table_893947a445): for every slot and every hex with
both transit and drive rows (the subject's contestable hexes in both), each venue hex's transit chance (band 1, band
2) against its drive chance (band 3; 0 where the pair has no drive row, i.e. below the 1% floor). Measures: the
expected count of venue hexes in the transit field (sum of chances), the expected count outside the drive field
(sum of transit chance x (1 - drive chance), independent draws), and that as a share; per band, over hexes and slots.

Rules: none (a count for the user's decision on band 3's stages: union of fields, or drive-only outer stage).

Self-contained (CLAUDE.md D1): reads the reach table's parquet files only; no imports from functions/ or config.py.
No API.

Conclusion (run 2026-10-26, 5,015 hexes, all slots): the bands nest almost exactly. Band 1: a transit field of 19.4
venue hexes on average, none outside the drive field (0.00%). Band 2: 105.2 venue hexes, 0.29 outside (0.28% pooled;
median 0.04%, p95 0.61%). Taking band 3's field as the union with bands 1-2 changes almost nothing; the open question
for band 3 is not nesting but the missing transit fields on drive hexes beyond the transit pass's origins.
"""
import datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TABLE_DIR = PROJECT_ROOT / "outputs" / "scoring" / "-37.76870_144.97196" / "reach_table_893947a445"
TRANSIT_PATH = TABLE_DIR / "transit_competitor_reach.parquet"
DRIVE_PATH = TABLE_DIR / "drive_competitor_reach.parquet"
NAME = "band3_nesting"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SUMMARY_PATH = DATA_DIR / f"{NAME}_{RUN_DATE}_summary.csv"
P_LEVELS = 255                      # the reach table's uint8 chance levels (config.REACH_TABLE_P_LEVELS)
HEX, VENUE_HEX, LEVEL, BAND, SLOT = "hex_id", "venue_hex", "reach_p_level", "band", "slot"


def main():
    print(f"{NAME}, run {RUN_DATE}; table {TABLE_DIR.name}")
    transit_df = pq.read_table(TRANSIT_PATH).to_pandas()
    hexes = transit_df[HEX].unique()
    drive_df = pq.read_table(DRIVE_PATH, columns=[HEX, VENUE_HEX, LEVEL],
                             filters=[(HEX, "in", hexes.tolist())]).to_pandas()
    print(f"  transit rows {len(transit_df):,} on {len(hexes):,} hexes; drive rows on those hexes {len(drive_df):,}")
    drive_hexes = set(drive_df[HEX].unique())
    transit_df = transit_df[transit_df[HEX].isin(drive_hexes)]
    drive_df = drive_df.rename(columns={LEVEL: "drive_level"})
    merged = transit_df.merge(drive_df, on=[HEX, VENUE_HEX], how="left")
    merged["drive_p"] = merged.drive_level.fillna(0) / P_LEVELS
    merged["transit_p"] = merged[LEVEL] / P_LEVELS
    merged["outside_p"] = merged.transit_p * (1 - merged.drive_p)
    per_hex = merged.groupby([BAND, SLOT, HEX], observed=True)[["transit_p", "outside_p"]].sum().reset_index()
    rows = []
    for band, part in per_hex.groupby(BAND):
        share = part.outside_p / part.transit_p
        rows.append({"band": int(band), "hex_slots": len(part), "field_mean": part.transit_p.mean(),
                     "outside_mean": part.outside_p.mean(), "outside_share_pooled": part.outside_p.sum()
                     / part.transit_p.sum(), "outside_share_median": share.median(),
                     "outside_share_p95": share.quantile(0.95), "hex_slots_any_outside_ge_1": int(
                         (part.outside_p >= 1).sum())})
        print(f"  band {int(band)}: {len(part):,} hex-slots; transit field {part.transit_p.mean():.1f} venue hexes "
              f"(mean), outside the drive field {part.outside_p.mean():.2f} ({rows[-1]['outside_share_pooled']:.2%} "
              f"pooled; median {share.median():.2%}, p95 {share.quantile(0.95):.2%})")
    pd.DataFrame(rows).to_csv(SUMMARY_PATH, index=False)
    print(f"  wrote {SUMMARY_PATH.name}")


if __name__ == "__main__":
    main()
