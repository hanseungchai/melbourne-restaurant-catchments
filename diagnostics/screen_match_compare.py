"""How close is the API order to the on-screen order? (DESIGN.md Q19, screen-matching test)

Claim (planned, 103rd): one Text Search (New) setting reproduces the "Restaurants" list the user saw on
screen closely enough to stand in for it; the best arm sets the main fetch's search area and open-status
handling. Side claim (user, 2026-10-25): the browser list centres on the map view (no location
permission), the phone list on the blue dot. Nothing in the pipeline relies on either yet.

Inputs (all saved; no requests):
  screens  diagnostic_data/screen_match_20261025_{phone,browser}.csv  (transcribed by eye, 104th)
  API      diagnostic_data/screen_match_api_20261025_raw.jsonl        (diagnostics/screen_match_api.py)
  venues   outputs/legacy_rebuilds/venues/venues_20260925_expanded.csv (place_id, name, lat, lng, reviews)
Screen cards are matched to place IDs by name (difflib ratio >= NAME_CUTOFF, venues within
SEARCH_RADIUS_M); ties broken by review count and, on the phone, by card distance. API IDs not in the
venue table are only counted (names would need a paid field, S5).

Per (screen, arm): overlap of the screen's top k with the API's 60 (the API returns at most 60), and
Spearman's rho of the two orders over the venues both hold. Centring: median distance of each list's
venues to the browser URL centre and to the phone's trilaterated position.

Results (one run per day): diagnostic_data/screen_match_compare_<run date>_{summary.csv,items.csv,log.txt}

Conclusion: pending.
"""

import difflib
import json
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NAME = "screen_match_compare"
RUN_DATE = date.today().strftime("%Y%m%d")
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SCREEN_PATHS = {screen: DIAGNOSTIC_DATA_DIR / f"screen_match_20261025_{screen}.csv" for screen in ("phone", "browser")}
API_RAW_PATH = DIAGNOSTIC_DATA_DIR / "screen_match_api_20261025_raw.jsonl"
VENUES_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"
OUT_PREFIX = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}"

BROWSER_CENTRE = (-37.817501, 144.9501715)   # browser URL
PHONE_CENTRE = (-37.810112, 144.951035)      # trilaterated from phone card distances (screen_match_api.py --centre)
SEARCH_RADIUS_M = 5000                       # venues considered for a name match
NAME_CUTOFF = 0.85                           # difflib ratio on normalised names
PHONE_DISTANCE_SCALE_M = 200                 # tie-break weight: this many metres off counts as 1 log-review unit
PHONE_MATCH_TOLERANCE_M = 300                # phone match rejected if table distance is this far off the card distance
TOP_KS = (10, 20, 40, 60)
EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1, lng1, lat2, lng2):
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin(np.radians(lat2 - lat1) / 2) ** 2
         + np.cos(phi1) * np.cos(phi2) * np.sin(np.radians(lng2 - lng1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def normalise(name):
    return re.sub(r"[^a-z0-9 ]", "", str(name).lower()).strip()


def load_venues():
    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "name", "lat", "lng", "rating", "user_ratings_total"])
    venues_df = venues_df.drop_duplicates("place_id")
    venues_df["d_browser_m"] = haversine_m(*BROWSER_CENTRE, venues_df["lat"], venues_df["lng"])
    venues_df["d_phone_m"] = haversine_m(*PHONE_CENTRE, venues_df["lat"], venues_df["lng"])
    near_df = venues_df[venues_df["d_browser_m"] < SEARCH_RADIUS_M].copy()
    near_df["norm"] = near_df["name"].map(normalise)
    return venues_df.set_index("place_id"), near_df.reset_index(drop=True)


def match_card(card, near_df, screen):
    target = normalise(card["name"])
    sims = near_df["norm"].map(lambda n: difflib.SequenceMatcher(None, target, n).ratio())
    cands = near_df[sims >= NAME_CUTOFF].assign(sim=sims[sims >= NAME_CUTOFF])
    if screen == "phone" and not pd.isna(card.get("distance_m")):
        cands = cands[(cands["d_phone_m"] - card["distance_m"]).abs() <= PHONE_MATCH_TOLERANCE_M]
    if cands.empty:
        return None
    best_sim = cands["sim"].max()
    cands = cands[cands["sim"] >= best_sim - 0.05]
    cost = (np.log1p(cands["user_ratings_total"].fillna(0)) - np.log1p(card["n_reviews"] or 0)).abs()
    if screen == "phone" and not pd.isna(card.get("distance_m")):
        cost += (cands["d_phone_m"] - card["distance_m"]).abs() / PHONE_DISTANCE_SCALE_M
    return cands.loc[cost.idxmin(), "place_id"]


def load_screens(near_df):
    screens = {}
    for screen, path in SCREEN_PATHS.items():
        cards_df = pd.read_csv(path)
        cards_df["n_reviews"] = cards_df["n_reviews"].fillna(0)
        cards_df["place_id"] = [match_card(card, near_df, screen) for _, card in cards_df.iterrows()]
        screens[screen] = cards_df
    return screens


def load_api():
    with API_RAW_PATH.open(encoding="utf-8") as f:
        return {rec["arm"]: rec for rec in map(json.loads, f)}


def first_positions(ids):
    """place_id -> first position (1-based); repeats keep their first place."""
    pos = {}
    for i, place_id in enumerate(ids, start=1):
        pos.setdefault(place_id, i)
    return pos


def compare(screen_ids, api_ids):
    screen_pos, api_pos = first_positions(screen_ids), first_positions(api_ids)
    row = {}
    for k in TOP_KS:
        top = [p for p, i in screen_pos.items() if i <= k]
        row[f"screen_top{k}_in_api"] = f"{sum(p in api_pos for p in top)}/{len(top)}"
    common = [p for p in screen_pos if p in api_pos]
    row["n_common"] = len(common)
    if len(common) >= 3:
        rho, p_value = spearmanr([screen_pos[p] for p in common], [api_pos[p] for p in common])
        row["spearman_rho"], row["spearman_p"] = round(rho, 3), round(p_value, 4)
    common20 = [p for p in screen_pos if screen_pos[p] <= 20 and api_pos.get(p, 99) <= 20]
    row["top20_both"] = len(common20)
    return row


def main():
    venues_df, near_df = load_venues()
    screens = load_screens(near_df)
    api = load_api()
    lines = []

    def say(text=""):
        print(text)
        lines.append(text)

    say(f"{NAME} run {RUN_DATE}; screens 2026-10-25 12:06-12:21, API 12:40-12:41 (saved data, no requests)")
    for screen, cards_df in screens.items():
        say(f"{screen}: {cards_df['place_id'].notna().sum()} of {len(cards_df)} cards matched to a place_id; "
            f"unmatched: {', '.join(cards_df.loc[cards_df['place_id'].isna(), 'name'])}")
    for arm, rec in api.items():
        n_in = sum(p in venues_df.index for p in rec["ids"])
        say(f"{arm}: {len(rec['ids'])} IDs, {len(set(rec['ids']))} distinct, {n_in} in the venue table")

    summary_rows = []
    for screen, cards_df in screens.items():
        screen_ids = cards_df["place_id"].dropna().tolist()
        for arm, rec in api.items():
            summary_rows.append({"screen": screen, "arm": arm, **compare(screen_ids, rec["ids"])})
    summary_df = pd.DataFrame(summary_rows)
    say()
    say(summary_df.to_string(index=False))

    say()
    say("Centring: median distance (m) of each list's matched venues to the browser URL centre / phone position")
    lists = {f"screen_{s}": df["place_id"].dropna().tolist() for s, df in screens.items()}
    lists.update({arm: rec["ids"] for arm, rec in api.items()})
    for label, ids in lists.items():
        known = [p for p in dict.fromkeys(ids) if p in venues_df.index]
        sub = venues_df.loc[known]
        say(f"  {label:40s} n={len(sub):3d}  to URL centre {sub['d_browser_m'].median():5.0f}  "
            f"to phone {sub['d_phone_m'].median():5.0f}")

    item_rows = []
    for screen, cards_df in screens.items():
        for _, card in cards_df.iterrows():
            row = {"screen": screen, "rank": card["rank"], "name": card["name"], "place_id": card["place_id"]}
            for arm, rec in api.items():
                row[arm] = first_positions(rec["ids"]).get(card["place_id"])
            item_rows.append(row)
    pd.DataFrame(item_rows).to_csv(f"{OUT_PREFIX}_items.csv", index=False)
    summary_df.to_csv(f"{OUT_PREFIX}_summary.csv", index=False)
    Path(f"{OUT_PREFIX}_log.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
