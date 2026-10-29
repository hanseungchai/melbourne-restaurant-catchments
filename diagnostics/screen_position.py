"""Where was the phone? Trilaterate a phone's position from the distances on its Google Maps cards (DESIGN.md Q19 (b)).

Claim: the phone screens' fits (screen_rank_drivers.py, screen_walk_distance.py, screen_transit_time.py) measure
distance from a position the screen never shows (no map centre on the phone list; distance from the blue dot only).
This script recovers that position from the card distances and the venue table's coordinates.
The 105th trilaterated the user's phone ad hoc (-37.810112, 144.951035, median residual 15 m; script not kept);
this script redoes it for any transcribed phone screen, and the user's phone is the check that it reproduces.

Data (saved; no requests):
  diagnostic_data/screen_match_20261025_<screen>.csv   cards in list order (transcribed by eye)
  outputs/legacy_rebuilds/venues/venues_20260925_expanded.csv   place_id, name, lat, lng, reviews
Method: cards matched to the venue table by name (ratio >= 0.85, best match, review count to break ties) among
venues within SEARCH_RADIUS_M of a seed (the user's phone position); sponsored and repeat cards dropped; cards
under MAX_CARD_DISTANCE_M only (the app shows 10 m steps below 1 km, 100 m steps above). Least squares on
haversine distance minus card distance (soft-L1 loss, so a wrong name match counts less), then matches whose
residual exceeds OUTLIER_M are dropped and the fit redone once.

Results (one run per day): diagnostic_data/screen_position_<run date>_<screen>_{log.txt,cards.csv}

Conclusion: pending.
"""

import argparse
import difflib
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NAME = "screen_position"
RUN_DATE = date.today().strftime("%Y%m%d")
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SCREEN_PATH_TEMPLATE = "screen_match_20261025_{screen}.csv"
VENUES_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"

SEED_CENTRE = (-37.810112, 144.951035)   # the user's phone, 105th (ad hoc trilateration)
SEARCH_RADIUS_M = 5000                   # venues considered for a name match
NAME_CUTOFF = 0.85
MAX_CARD_DISTANCE_M = 1000               # cards at or above this show 100 m steps
SOFT_L1_SCALE_M = 30                     # residual size where the loss turns linear
OUTLIER_M = 150                          # matches this far off after the first fit are dropped
EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1, lng1, lat2, lng2):
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin(np.radians(lat2 - lat1) / 2) ** 2
         + np.cos(phi1) * np.cos(phi2) * np.sin(np.radians(lng2 - lng1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def normalise(name):
    return re.sub(r"[^a-z0-9 ]", "", str(name).lower()).strip()


def match_card(card, venues_df):
    target = normalise(card["name"])
    sims = venues_df["norm"].map(lambda n: difflib.SequenceMatcher(None, target, n).ratio())
    cands = venues_df[sims >= NAME_CUTOFF].assign(sim=sims[sims >= NAME_CUTOFF])
    if cands.empty:
        return None
    cands = cands[cands["sim"] >= cands["sim"].max() - 0.05]
    cost = (np.log1p(cands["user_ratings_total"].fillna(0)) - np.log1p(card["n_reviews"])).abs()
    return cands.loc[cost.idxmin(), "place_id"]


def fit_position(cards_df, start):
    def residuals(pos):
        return haversine_m(pos[0], pos[1], cards_df["lat"], cards_df["lng"]) - cards_df["distance_m"]

    fit = least_squares(residuals, np.array(start), loss="soft_l1", f_scale=SOFT_L1_SCALE_M, x_scale=[1e-3, 1e-3])
    return tuple(fit.x), residuals(fit.x)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", required=True, help="e.g. phone, partner_phone")
    screen = parser.parse_args().screen
    out_prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_{screen}"
    lines = []

    def say(text=""):
        print(text)
        lines.append(text)

    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "name", "lat", "lng", "user_ratings_total"])
    venues_df = venues_df.drop_duplicates("place_id")
    venues_df = venues_df[haversine_m(*SEED_CENTRE, venues_df["lat"], venues_df["lng"]) < SEARCH_RADIUS_M]
    venues_df = venues_df.assign(norm=venues_df["name"].map(normalise)).reset_index(drop=True)

    cards_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / SCREEN_PATH_TEMPLATE.format(screen=screen))
    cards_df["n_reviews"] = cards_df["n_reviews"].fillna(0)
    is_kept = ~cards_df["is_repeat"].astype(bool) & (cards_df["distance_m"] < MAX_CARD_DISTANCE_M)
    if "is_sponsored" in cards_df:
        is_kept &= ~cards_df["is_sponsored"].astype(bool)
    cards_df = cards_df[is_kept].copy()
    cards_df["place_id"] = [match_card(card, venues_df) for _, card in cards_df.iterrows()]
    cards_df = cards_df.dropna(subset=["place_id"]).merge(venues_df[["place_id", "lat", "lng"]], on="place_id")

    centre, resid = fit_position(cards_df, SEED_CENTRE)
    cards_df["residual_m"] = resid
    is_outlier = cards_df["residual_m"].abs() > OUTLIER_M
    centre, resid = fit_position(cards_df[~is_outlier], centre)
    cards_df["residual_m"] = haversine_m(*centre, cards_df["lat"], cards_df["lng"]) - cards_df["distance_m"]

    say(f"{NAME} run {RUN_DATE}: screen {screen}, {len(cards_df)} matched cards under {MAX_CARD_DISTANCE_M} m, "
        f"{int(is_outlier.sum())} dropped as outliers (> {OUTLIER_M} m after the first fit)")
    say(f"  position: {centre[0]:.6f}, {centre[1]:.6f}")
    say(f"  |residual| over the {int((~is_outlier).sum())} kept: median {np.median(np.abs(resid)):.0f} m, "
        f"max {np.max(np.abs(resid)):.0f} m")
    say(f"  from the seed (the user's phone, 105th): {haversine_m(*SEED_CENTRE, *centre):.0f} m")
    for _, card in cards_df.iterrows():
        flag = "  OUTLIER" if abs(card["residual_m"]) > OUTLIER_M else ""
        say(f"    {card['rank']:>3} {card['name'][:40]:40s} card {card['distance_m']:>5.0f} m  "
            f"residual {card['residual_m']:+5.0f} m{flag}")
    cards_df.drop(columns=["norm"], errors="ignore").to_csv(f"{out_prefix}_cards.csv", index=False)
    Path(f"{out_prefix}_log.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
