"""FRM-23's free checks: how many venues near the subject carry a price level and a cuisine tag?

Claim checked (concepts/framing.md FRM-23; venues.md VEN-3, VEN-8): the purchase-journey scenario (students walking
from a campus to the subject, competitors along the way by detour band x rating x price x cuisine) has enough price
levels and cuisine tags to fill its table. Where it would be relied on: the anchor showcase (FRM-19 part 3), not
built. Report only.

Measures: per ring of haversine distance to the subject (0-2, 2-5, 5-7, 7+ km; inside 7 km the June scan's rows with
Places (New) types stand, VEN-3), the share of venues with a price level and with a cuisine tag (a type ending in
"_restaurant" other than the generic ones listed in GENERIC_RESTAURANT_TYPES).

Conclusion (run 2026-10-22, autonomous 69th): inside 7 km (all June-scan rows) price level on 0.42-0.44 of venues,
  a cuisine tag on 0.60-0.65, both on 0.31-0.33 (0-2 km 321 venues, 2-5 km 2,224, 5-7 km 1,946); beyond 7 km price
  0.44 and no cuisine tags at all (ring rows, VEN-8). Some "_restaurant" tags are meal formats, not cuisines
  (breakfast, brunch, hamburger rank 3rd, 7th, 8th within 5 km). For FRM-23: a campus within ~5 km of the subject
  has cuisine on about two thirds of competitors; price is missing on more than half, so the table needs a "price
  unknown" row rather than dropping venues; a scenario beyond 7 km would need the Details pull (Q9) first.

Inputs (read only): venues with hex (the hex stage's table). Self-contained (CLAUDE.md D1). No API calls.
Usage: `python venue_anchor_tag_coverage.py`.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "-37.76870_144.97196"
VENUES_WITH_HEX_PATH = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT / f"venues_with_hex_ven20260925_{SUBJECT}.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "venue_anchor_tag_coverage"

SUBJECT_LAT, SUBJECT_LON = -37.7687014, 144.9719611
RING_EDGES_KM = [0, 2, 5, 7, np.inf]
RING_LABELS = ["0-2 km", "2-5 km", "5-7 km", "7+ km"]
TYPE_SEPARATOR = "|"
CUISINE_SUFFIX = "_restaurant"
GENERIC_RESTAURANT_TYPES = {"restaurant", "fast_food_restaurant"}
EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    venues_df = pd.read_csv(VENUES_WITH_HEX_PATH, usecols=["place_id", "types", "price_level", "lat", "lng", "run_id"])
    venues_df["ring"] = pd.cut(haversine_m(SUBJECT_LAT, SUBJECT_LON, venues_df.lat, venues_df.lng) / 1000,
                               RING_EDGES_KM, labels=RING_LABELS, right=False)
    tag_lists = venues_df.types.fillna("").str.split(TYPE_SEPARATOR)
    venues_df["cuisine"] = tag_lists.map(lambda tags: next((t for t in tags if t.endswith(CUISINE_SUFFIX)
                                                            and t not in GENERIC_RESTAURANT_TYPES), None))
    lines = [f"{NAME} run {run_date}: {len(venues_df):,} venues on the grid"]
    for ring, ring_df in venues_df.groupby("ring", observed=True):
        lines.append(f"  {ring}: {len(ring_df):,} venues (June scan {(ring_df.run_id == 'old_legacy').mean():.2f}); price "
                     f"level {ring_df.price_level.notna().mean():.3f}; cuisine tag {ring_df.cuisine.notna().mean():.3f}; "
                     f"both {(ring_df.price_level.notna() & ring_df.cuisine.notna()).mean():.3f}")
    near_df = venues_df[venues_df.ring.isin(RING_LABELS[:2])]
    lines += ["", "top cuisine tags within 5 km: " + ", ".join(f"{k} {v}" for k, v in near_df.cuisine.value_counts().head(12).items())]
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main()
