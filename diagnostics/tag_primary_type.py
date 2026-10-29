"""Does a venue's tag say what its main business is? Tags vs Google's primaryType.

Claim under test (premise of excluding by tag; DESIGN.md Q17, presentation of tag exclusions): a
reader who excludes a tag (e.g. gas_station, atm) removes venues whose main business is not food.
The premise fails where venues carrying the tag are mostly food businesses with a side feature
(user, 2026-10-12: "just because the venue has an atm doesn't mean their primary business can't be
a restaurant"). Where it holds, the tag is mixed-use: its venues are mainly something else, though
some still compete (the user's car wash with a kebab food truck and lounge, for a fast-food subject).

Data (free, no API calls): the venue table's tags (`types`, what readers would choose from) and
primaryType from the Enterprise pulls of the same venues.
  main sample   the 2026-10-10 pull, a uniform draw of 900 from the venue table (no weights needed);
  sensitivity   both pulls, the newer fetch winning (the 2026-09-02 pull under-covers the outer ring).
The two [subject] venues (is_fixed) are left out.

Rules, set before the run:
  food primary  primaryType is in Google's own "Food and Drink" category (Places API Table A,
                FOOD_PRIMARY_TYPES, source and date beside it): the platform's grouping, not ours.
                Every observed primaryType is listed with its class. History: the first run
                (2026-10-12) used a hand-made list that missed kebab_shop, noodle_shop, bistro and
                others; it was replaced by Google's category the same day.
  per tag T     n = sample venues carrying T; food share = those with a food primary / n, Wilson 95%.
                Reported when n >= MIN_N. Universal tags (on every table venue) are not tags to choose.
  mixed-use     food share < MIXED_SHARE (a convention, not evidence): label "mixed-use: check".
  premise fails for T where food share's lower Wilson bound >= MIXED_SHARE (excluding T would mostly
                remove food businesses).
  rule cost     share of the sample removed by "exclude T" vs by "exclude T unless the primary is food".

Results (one run per day): diagnostic_data/tag_primary_type_<run date>_{tags.csv,log.txt}

Conclusion (run 2026-10-12, Google's category): the pool is 94.5% food-primary (main sample, 898
venues; 94.8% under the hand-made list, same mixed-use tags). Only
gas_station, atm and finance are mixed-use, and they are the same venues: atm and finance ride on gas
stations (9 of 9 atm venues have primary gas_station), not on restaurants with a cash machine. Every
gas_station venue (13; 16 in both pulls) is primarily a gas station, so "exclude gas_station" and
"exclude gas_station unless food primary" remove the same 1.5% of the pool. supermarket (n = 5, both
pulls only), grocery_or_supermarket and lodging sit near the line with wide intervals. Two
venues have primaryType food (Table B, generic), classed OTHER by the rule. Every
cuisine and food-service tag (and broad ones: store, bar, cafe, event_venue, service) is mainly food,
so excluding by those tags would remove food businesses: their exclusion needs the primary type.
"""

import datetime
import json
import math
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENUES_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"
HOURS_PULL_DIRS = {
    "20261010": PROJECT_ROOT / "outputs" / "places_enterprise_hours" / "places_enterprise_hours_20261010",
    "20260902": PROJECT_ROOT / "frozen_inputs" / "places_enterprise_hours_20260902",
}
MAIN_PULL = "20261010"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "tag_primary_type"
RUN_DATE = f"{datetime.date.today():%Y%m%d}"
TAGS_OUT_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_tags.csv"
LOG_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_log.txt"

TAG_SEPARATOR = "|"
# Google Places API (New) place types, Table A, category "Food and Drink", as listed at
# GOOGLE_TYPES_URL (page last updated 2026-10-08, read 2026-10-12). The platform's own grouping.
GOOGLE_TYPES_URL = "https://developers.google.com/maps/documentation/places/web-service/place-types"
FOOD_PRIMARY_TYPES = frozenset({  # 166 types
    "acai_shop", "afghani_restaurant", "african_restaurant", "american_restaurant",
    "argentinian_restaurant", "asian_fusion_restaurant", "asian_restaurant", "australian_restaurant",
    "austrian_restaurant", "bagel_shop", "bakery", "bangladeshi_restaurant", "bar", "bar_and_grill",
    "barbecue_restaurant", "basque_restaurant", "bavarian_restaurant", "beer_garden",
    "belgian_restaurant", "bistro", "brazilian_restaurant", "breakfast_restaurant", "brewery", "brewpub",
    "british_restaurant", "brunch_restaurant", "buffet_restaurant", "burmese_restaurant",
    "burrito_restaurant", "cafe", "cafeteria", "cajun_restaurant", "cake_shop", "californian_restaurant",
    "cambodian_restaurant", "candy_store", "cantonese_restaurant", "caribbean_restaurant", "cat_cafe",
    "chicken_restaurant", "chicken_wings_restaurant", "chilean_restaurant", "chinese_noodle_restaurant",
    "chinese_restaurant", "chocolate_factory", "chocolate_shop", "cocktail_bar", "coffee_roastery",
    "coffee_shop", "coffee_stand", "colombian_restaurant", "confectionery", "croatian_restaurant",
    "cuban_restaurant", "czech_restaurant", "danish_restaurant", "deli", "dessert_restaurant",
    "dessert_shop", "dim_sum_restaurant", "diner", "dog_cafe", "donut_shop", "dumpling_restaurant",
    "dutch_restaurant", "eastern_european_restaurant", "ethiopian_restaurant", "european_restaurant",
    "falafel_restaurant", "family_restaurant", "fast_food_restaurant", "filipino_restaurant",
    "fine_dining_restaurant", "fish_and_chips_restaurant", "fondue_restaurant", "food_court",
    "french_restaurant", "fusion_restaurant", "gastropub", "german_restaurant", "greek_restaurant",
    "gyro_restaurant", "halal_restaurant", "hamburger_restaurant", "hawaiian_restaurant", "hookah_bar",
    "hot_dog_restaurant", "hot_dog_stand", "hot_pot_restaurant", "hungarian_restaurant", "ice_cream_shop",
    "indian_restaurant", "indonesian_restaurant", "irish_pub", "irish_restaurant", "israeli_restaurant",
    "italian_restaurant", "japanese_curry_restaurant", "japanese_izakaya_restaurant",
    "japanese_restaurant", "juice_shop", "kebab_shop", "korean_barbecue_restaurant", "korean_restaurant",
    "latin_american_restaurant", "lebanese_restaurant", "lounge_bar", "malaysian_restaurant",
    "meal_delivery", "meal_takeaway", "mediterranean_restaurant", "mexican_restaurant",
    "middle_eastern_restaurant", "mongolian_barbecue_restaurant", "moroccan_restaurant", "noodle_shop",
    "north_indian_restaurant", "oyster_bar_restaurant", "pakistani_restaurant", "pastry_shop",
    "persian_restaurant", "peruvian_restaurant", "pizza_delivery", "pizza_restaurant",
    "polish_restaurant", "portuguese_restaurant", "pub", "ramen_restaurant", "restaurant",
    "romanian_restaurant", "russian_restaurant", "salad_shop", "sandwich_shop", "scandinavian_restaurant",
    "seafood_restaurant", "shawarma_restaurant", "snack_bar", "soul_food_restaurant", "soup_restaurant",
    "south_american_restaurant", "south_indian_restaurant", "southwestern_us_restaurant",
    "spanish_restaurant", "sports_bar", "sri_lankan_restaurant", "steak_house", "sushi_restaurant",
    "swiss_restaurant", "taco_restaurant", "taiwanese_restaurant", "tapas_restaurant", "tea_house",
    "tex_mex_restaurant", "thai_restaurant", "tibetan_restaurant", "tonkatsu_restaurant",
    "turkish_restaurant", "ukrainian_restaurant", "vegan_restaurant", "vegetarian_restaurant",
    "vietnamese_restaurant", "western_restaurant", "wine_bar", "winery", "yakiniku_restaurant",
    "yakitori_restaurant",
})
MIN_N = 5
MIXED_SHARE = 0.5
WILSON_Z = 1.96
N_TOP_PRIMARY = 3
PCT = 100.0


class Tee:
    """Print to the console and keep every line for the run log."""

    def __init__(self):
        self.stdout = sys.stdout
        self.lines = []

    def write(self, text):
        self.stdout.write(text)
        self.lines.append(text)

    def flush(self):
        self.stdout.flush()


def is_food_primary(primary_type):
    return isinstance(primary_type, str) and (primary_type in FOOD_PRIMARY_TYPES)


def wilson(k, n):
    p, z2 = k / n, WILSON_Z ** 2
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = WILSON_Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return centre - half, centre + half


def load():
    """One row per pulled venue: pull, primaryType, table tags (universal tags dropped)."""
    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "types"]).drop_duplicates("place_id")
    tag_sets = venues_df.set_index("place_id")["types"].fillna("").str.split(TAG_SEPARATOR).apply(lambda t: set(t) - {""})
    universal = set.intersection(*tag_sets)
    rows, fetched = {}, {}
    for pull, hours_dir in HOURS_PULL_DIRS.items():
        for path in hours_dir.rglob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            place_id = record.get("id") or path.stem
            if record.get("is_fixed") or place_id not in tag_sets.index:
                continue
            if place_id in fetched and fetched[place_id] >= record.get("fetched_date", ""):
                continue                                  # the newer fetch wins
            fetched[place_id] = record.get("fetched_date", "")
            rows[place_id] = dict(place_id=place_id, pull=pull, primary_type=record.get("primaryType"),
                                  tags=sorted(tag_sets[place_id] - universal))
    sample_df = pd.DataFrame(list(rows.values()))
    sample_df["is_food_primary"] = sample_df["primary_type"].apply(is_food_primary)
    return sample_df, universal


def tag_table(sample_df):
    exploded = sample_df.explode("tags").dropna(subset=["tags"])
    rows = []
    for tag, group in exploded.groupby("tags"):
        n, k = len(group), int(group["is_food_primary"].sum())
        if n < MIN_N:
            continue
        lo, hi = wilson(k, n)
        top = group["primary_type"].fillna("(none)").value_counts().head(N_TOP_PRIMARY)
        rows.append(dict(tag=tag, n=n, food_share=k / n, ci_lo=lo, ci_hi=hi,
                         is_mixed_use=k / n < MIXED_SHARE, premise_fails=lo >= MIXED_SHARE,
                         removed_by_tag_pct=n / len(sample_df) * PCT,
                         removed_unless_food_pct=(n - k) / len(sample_df) * PCT,
                         top_primary=", ".join(f"{t} {c}" for t, c in top.items())))
    return pd.DataFrame(rows).sort_values(["food_share", "n"], ascending=[True, False])


def report(sample_df, label):
    print(f"\n=== {label}: {len(sample_df)} venues; food primary {sample_df['is_food_primary'].mean():.1%}; "
          f"no primaryType {sample_df['primary_type'].isna().sum()}")
    table_df = tag_table(sample_df)
    with pd.option_context("display.width", 250, "display.max_rows", 500, "display.max_colwidth", 70):
        print(table_df.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print(f"mixed-use (share < {MIXED_SHARE}): {', '.join(table_df.loc[table_df.is_mixed_use, 'tag']) or 'none'}")
    print(f"premise fails (lower bound >= {MIXED_SHARE}): {', '.join(table_df.loc[table_df.premise_fails, 'tag']) or 'none'}")
    return table_df


def main():
    tee = Tee()
    sys.stdout = tee
    print(f"{NAME}, run {RUN_DATE}. Pulls: {', '.join(HOURS_PULL_DIRS)} (saved Enterprise JSON, reused; no API calls)")
    sample_df, universal = load()
    print(f"universal tags dropped: {sorted(universal)}; MIN_N {MIN_N}")

    print("\nObserved primaryTypes and their class (audit of the food rule), all pulls:")
    counts = sample_df["primary_type"].fillna("(none)").value_counts()
    for primary_type, count in counts.items():
        print(f"  {'food ' if is_food_primary(primary_type) else 'OTHER'}  {primary_type:<32} {count}")

    main_df = report(sample_df[sample_df["pull"] == MAIN_PULL], f"main: pull {MAIN_PULL} (uniform draw)")
    both_df = report(sample_df, "sensitivity: both pulls")

    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    main_df.assign(sample="main").pipe(lambda d: pd.concat([d, both_df.assign(sample="both")])).to_csv(TAGS_OUT_PATH, index=False)
    sys.stdout = tee.stdout
    LOG_PATH.write_text("".join(tee.lines), encoding="utf-8")
    print(f"saved {TAGS_OUT_PATH.name}, {LOG_PATH.name}")


if __name__ == "__main__":
    main()
