"""What orders the Google Maps app's restaurant list: distance, rating, review count? (DESIGN.md Q19 (b))

Claim (Q19 (b), user 2026-10-13): within reach, better-rated venues are shown first or more often,
distance held roughly equal. The tolerance framing and Top-N rest on it (SCR-1, SCR-2, SCR-4).
Why the screen and not the API: no API order resembles the app (screen_match_compare.py, 2026-10-25: 25
Text Search and Nearby settings, best phone top-10 overlap 3/10), so the app's own list is the only
record of what a diner sees. Limit, stated: one user, one device, one place, one time (n = 1 user).

Data (saved; no requests):
  diagnostic_data/screen_match_20261025_phone.csv   107 cards in list order (transcribed by eye)
  outputs/legacy_rebuilds/venues/venues_20260925_expanded.csv   place_id, types, lat, lng, rating, reviews
Cards matched to place IDs as in screen_match_compare.py (name ratio >= 0.85, table distance within
300 m of the card's). Repeat cards keep their first position. Rating and review count come from the
venue table (Sept 2026) for every venue, shown or not, so both sides use one source.

Two fits, covariates standardised (per 1 SD: log distance, rating, log(1 + reviews)):
  order      Plackett-Luce (rank-ordered logit) over the matched cards in list order: who is placed
             next among those not yet placed.
  inclusion  logit: in the first 107 cards vs not, over the candidate set = table venues within the
             farthest card's distance (CANDIDATE_RADIUS_M) of the phone. The list never ends (it loads
             more as you scroll; user), so "not shown" means "not in the first 107". Every table venue is
             restaurant-typed, so no typed subset is fitted.
Distance: straight-line from the trilaterated phone position; then walking distance (R5, WLK-1) from
screen_walk_distance.py's saved table (user, 2026-10-25): both fits rerun on the same venues with log walk
distance in place of log straight-line, compared by log-likelihood (same n, same number of parameters).
Transit (user, 2026-10-25), from screen_transit_time.py's saved table: door-to-door time (the faster of walk
and transit) in place of distance; and the direct test, walking time plus minutes saved by transit (only
venues transit reaches faster can tell them apart, user).
No pass rule is applied: Claude's 103rd proposals are still owed.
Screens (--screen, default phone): phone (the user's, 107 cards) and partner_phone (the user's partner's, 106th:
iPhone, Chinese interface, 27 cards, same house; position from screen_position.py). Sponsored cards are dropped
(an ad is placed by auction, not by the list's order); "first N cards" counts non-sponsored cards.

Results (one run per day): diagnostic_data/screen_rank_drivers_<run date>[_<screen>]_{log.txt,cards.csv}
(no suffix for phone, the 105th's name)

Conclusion: pending.
"""

import argparse
import difflib
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.optimize import minimize
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NAME = "screen_rank_drivers"
RUN_DATE = date.today().strftime("%Y%m%d")
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
VENUES_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"

# per screen: cards, phone position (lat, lng), candidate radius (farthest non-sponsored card, m), saved walk and
# transit tables (screen_walk_distance.py, screen_transit_time.py) and its departure window, output suffix
SCREENS = {
    "phone": {"label": "the user's phone 2026-10-25 12:06-12:12",
              "cards": "screen_match_20261025_phone.csv", "centre": (-37.810112, 144.951035),
              "candidate_radius_m": 1400, "walk": "screen_walk_distance_20261025_walk.csv",
              "transit": "screen_transit_time_20261025_times.csv", "window": "12:08-12:18", "suffix": ""},
    "partner_phone": {"label": "the partner's phone 2026-10-25 13:34-13:35",
                      "cards": "screen_match_20261025_partner_phone.csv", "centre": (-37.809748, 144.951763),
                      "candidate_radius_m": 1300, "walk": "screen_walk_distance_20261025_partner_phone_walk.csv",
                      "transit": "screen_transit_time_20261025_partner_phone_times.csv", "window": "13:30-13:40",
                      "suffix": "_partner_phone"},
}
SEARCH_RADIUS_M = 5000                    # venues considered for a name match
NAME_CUTOFF = 0.85
PHONE_MATCH_TOLERANCE_M = 300
PHONE_DISTANCE_SCALE_M = 200
MIN_TIME_MIN = 1                         # whole-minute times floored here before the log
COVARIATES = ["log_distance", "rating", "log_reviews"]
Z_95 = 1.96
EARTH_RADIUS_M = 6_371_000

_parser = argparse.ArgumentParser()
_parser.add_argument("--screen", default="phone", choices=sorted(SCREENS))
SCREEN = SCREENS[_parser.parse_args().screen]
PHONE_SCREEN_PATH = DIAGNOSTIC_DATA_DIR / SCREEN["cards"]
PHONE_CENTRE = SCREEN["centre"]
CANDIDATE_RADIUS_M = SCREEN["candidate_radius_m"]
WALK_PATH = DIAGNOSTIC_DATA_DIR / SCREEN["walk"]
TRANSIT_PATH = DIAGNOSTIC_DATA_DIR / SCREEN["transit"]
TRANSIT_WINDOW_LABEL = SCREEN["window"]
OUT_PREFIX = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}{SCREEN['suffix']}"


def haversine_m(lat1, lng1, lat2, lng2):
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin(np.radians(lat2 - lat1) / 2) ** 2
         + np.cos(phi1) * np.cos(phi2) * np.sin(np.radians(lng2 - lng1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def normalise(name):
    return re.sub(r"[^a-z0-9 ]", "", str(name).lower()).strip()


def load_venues():
    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "types", "name", "lat", "lng", "rating",
                                                  "user_ratings_total"]).drop_duplicates("place_id")
    venues_df["distance_m"] = haversine_m(*PHONE_CENTRE, venues_df["lat"], venues_df["lng"])
    venues_df = venues_df[venues_df["distance_m"] < SEARCH_RADIUS_M].reset_index(drop=True)
    venues_df["norm"] = venues_df["name"].map(normalise)
    return venues_df


def match_card(card, venues_df):
    target = normalise(card["name"])
    sims = venues_df["norm"].map(lambda n: difflib.SequenceMatcher(None, target, n).ratio())
    cands = venues_df[sims >= NAME_CUTOFF].assign(sim=sims[sims >= NAME_CUTOFF])
    cands = cands[(cands["distance_m"] - card["distance_m"]).abs() <= PHONE_MATCH_TOLERANCE_M]
    if cands.empty:
        return None
    cands = cands[cands["sim"] >= cands["sim"].max() - 0.05]
    cost = ((np.log1p(cands["user_ratings_total"].fillna(0)) - np.log1p(card["n_reviews"])).abs()
            + (cands["distance_m"] - card["distance_m"]).abs() / PHONE_DISTANCE_SCALE_M)
    return cands.loc[cost.idxmin(), "place_id"]


def add_covariates(df):
    df = df.copy()
    df["log_distance"] = np.log(df["distance_m"])
    df["log_reviews"] = np.log1p(df["user_ratings_total"].fillna(0))
    return df


def standardise(df, ref_df):
    return (df[COVARIATES] - ref_df[COVARIATES].mean()) / ref_df[COVARIATES].std()


def fit_inclusion(pool_df, shown_ids):
    is_shown = pool_df["place_id"].isin(shown_ids).astype(int)
    return sm.Logit(is_shown, sm.add_constant(standardise(pool_df, pool_df))).fit(disp=0), is_shown


def report_transit(say, pl_df, pool_df, shown_ids):
    """Door-to-door time (the faster of walk and transit) in place of distance, and the transit-saving test:
    walking time kept, plus minutes saved by transit (0 where walking is as fast). Only venues transit reaches
    faster can tell the two apart (user, 2026-10-25), so the saving term is the direct test."""
    times_df = pd.read_csv(TRANSIT_PATH)[["place_id", "transit_min", "walk_min"]].dropna()
    times_df["best_min"] = times_df[["transit_min", "walk_min"]].min(axis=1)
    times_df["saving_min"] = times_df["walk_min"] - times_df["best_min"]
    order_df = pl_df.merge(times_df, on="place_id")
    in_df = pool_df.merge(times_df, on="place_id")
    say(f"\nTransit (saved data {TRANSIT_PATH.name}; stock R5, Sunday, median over {TRANSIT_WINDOW_LABEL})")
    say(f"  transit faster than walking: {int((in_df['saving_min'] > 0).sum())} of {len(in_df)} candidates, "
        f"{int((order_df['saving_min'] > 0).sum())} of {len(order_df)} shown; saving where faster: median "
        f"{in_df.loc[in_df['saving_min'] > 0, 'saving_min'].median()} min, max {in_df['saving_min'].max()} min")
    for label, time_col in (("walking time", "walk_min"), ("door-to-door", "best_min")):
        fit_cols = [f"log_{time_col}", "rating", "log_reviews"]
        o_df = order_df.assign(**{f"log_{time_col}": np.log(order_df[time_col].clip(lower=MIN_TIME_MIN))})
        i_df = in_df.assign(**{f"log_{time_col}": np.log(in_df[time_col].clip(lower=MIN_TIME_MIN))})
        beta, se, loglik = plackett_luce(((o_df[fit_cols] - o_df[fit_cols].mean()) / o_df[fit_cols].std()).to_numpy())
        fit_t = sm.Logit(i_df["place_id"].isin(shown_ids).astype(int),
                         sm.add_constant((i_df[fit_cols] - i_df[fit_cols].mean()) / i_df[fit_cols].std())).fit(disp=0)
        say(f"  {label:13s} order: time {beta[0]:+.3f} (SE {se[0]:.3f}), rating {beta[1]:+.3f}, loglik {loglik:.2f} "
            f"(n {len(o_df)}) | inclusion: time {fit_t.params.iloc[1]:+.3f}, loglik {fit_t.llf:.2f} (n {len(i_df)})")
    fit_cols = ["log_walk_min", "saving_min", "rating", "log_reviews"]
    o_df = order_df.assign(log_walk_min=np.log(order_df["walk_min"].clip(lower=MIN_TIME_MIN)))
    i_df = in_df.assign(log_walk_min=np.log(in_df["walk_min"].clip(lower=MIN_TIME_MIN)))
    beta, se, _ = plackett_luce(((o_df[fit_cols] - o_df[fit_cols].mean()) / o_df[fit_cols].std()).to_numpy())
    fit_s = sm.Logit(i_df["place_id"].isin(shown_ids).astype(int),
                     sm.add_constant((i_df[fit_cols] - i_df[fit_cols].mean()) / i_df[fit_cols].std())).fit(disp=0)
    ci = fit_s.conf_int()
    say("  saving test, per 1 SD of minutes saved (positive = transit-reachable venues favoured beyond walking):")
    say(f"    order      {beta[1]:+.3f}  95% [{beta[1] - Z_95 * se[1]:+.3f}, {beta[1] + Z_95 * se[1]:+.3f}]")
    say(f"    inclusion  {fit_s.params['saving_min']:+.3f}  95% [{ci.loc['saving_min', 0]:+.3f}, "
        f"{ci.loc['saving_min', 1]:+.3f}]")


def plackett_luce(x):
    """x: (n, k) in list order. Returns beta and SEs from the exact Hessian (a sequence of conditional logits)."""
    n = len(x)

    def negloglik(beta):
        u = x @ beta
        tail_lse = np.logaddexp.accumulate(u[::-1])[::-1]   # log sum_{j >= i} exp(u_j)
        return -(u - tail_lse)[: n - 1].sum()

    beta = minimize(negloglik, np.zeros(x.shape[1]), method="BFGS").x
    u = x @ beta
    info = np.zeros((x.shape[1], x.shape[1]))
    for i in range(n - 1):
        w = np.exp(u[i:] - u[i:].max())
        w /= w.sum()
        mean = w @ x[i:]
        info += (x[i:] - mean).T @ ((x[i:] - mean) * w[:, None])
    return beta, np.sqrt(np.diag(np.linalg.inv(info))), -negloglik(beta)


def main():
    lines = []

    def say(text=""):
        print(text)
        lines.append(text)

    venues_df = load_venues()
    cards_df = pd.read_csv(PHONE_SCREEN_PATH)
    n_sponsored = 0
    if "is_sponsored" in cards_df:
        n_sponsored = int(cards_df["is_sponsored"].sum())
        cards_df = cards_df[~cards_df["is_sponsored"].astype(bool)]
    cards_df["n_reviews"] = cards_df["n_reviews"].fillna(0)
    cards_df["place_id"] = [match_card(card, venues_df) for _, card in cards_df.iterrows()]
    shown_df = cards_df.dropna(subset=["place_id"]).drop_duplicates("place_id")[["rank", "name", "place_id"]]
    shown_df = shown_df.merge(venues_df.drop(columns=["name"]), on="place_id").sort_values("rank")
    shown_df = add_covariates(shown_df)
    say(f"{NAME} run {RUN_DATE}: {SCREEN['label']}, {len(cards_df)} cards ({n_sponsored} sponsored dropped first), "
        f"{len(shown_df)} matched distinct venues (unmatched and repeats dropped)")

    say("\nSpearman rho, list position vs covariate (positive = later in the list as the covariate grows)")
    for col in ["distance_m", "rating", "user_ratings_total"]:
        rho, p_value = spearmanr(shown_df["rank"], shown_df[col], nan_policy="omit")
        say(f"  {col:20s} rho {rho:+.3f}  p {p_value:.4f}")

    say("\nOrder: Plackett-Luce over shown venues, per 1 SD (positive = placed earlier)")
    pl_df = shown_df.dropna(subset=COVARIATES)
    beta, se, _ = plackett_luce(standardise(pl_df, pl_df).to_numpy())
    for col, b, s in zip(COVARIATES, beta, se):
        say(f"  {col:12s} {b:+.3f}  95% [{b - Z_95 * s:+.3f}, {b + Z_95 * s:+.3f}]")
    say(f"  n = {len(pl_df)}; SD: log distance {pl_df['log_distance'].std():.2f}, rating {pl_df['rating'].std():.2f}, "
        f"log reviews {pl_df['log_reviews'].std():.2f}")

    shown_ids = set(shown_df["place_id"])
    pool_df = add_covariates(venues_df[venues_df["distance_m"] <= CANDIDATE_RADIUS_M]).dropna(subset=COVARIATES)
    fit, is_shown = fit_inclusion(pool_df, shown_ids)
    ci = fit.conf_int()
    say(f"\nInclusion logit: {is_shown.sum()} in the first {len(cards_df)} cards of {len(pool_df)} table venues "
        f"within {CANDIDATE_RADIUS_M} m (per 1 SD, positive = more likely in)")
    for col in COVARIATES:
        say(f"  {col:12s} {fit.params[col]:+.3f}  95% [{ci.loc[col, 0]:+.3f}, {ci.loc[col, 1]:+.3f}]")

    if not WALK_PATH.exists():
        say(f"\nWalking distance: {WALK_PATH.name} not found; run screen_walk_distance.py")
    else:
        walk_df = pd.read_csv(WALK_PATH)[["place_id", "walk_m"]]
        pool_w = pool_df.merge(walk_df, on="place_id").dropna(subset=["walk_m"])
        pl_w = pl_df.merge(walk_df, on="place_id").dropna(subset=["walk_m"])
        detour = pool_w["walk_m"] / pool_w["distance_m"]
        say(f"\nStraight-line vs walking distance (saved data {WALK_PATH.name}; same venues for both)")
        say(f"  walk / straight-line over candidates: median {detour.median():.2f}, 90th pct {detour.quantile(0.9):.2f}")
        for label, distance_col in (("straight-line", "distance_m"), ("walking", "walk_m")):
            order_df = add_covariates(pl_w.assign(distance_m=pl_w[distance_col]))
            in_df = add_covariates(pool_w.assign(distance_m=pool_w[distance_col]))
            beta, se, loglik = plackett_luce(standardise(order_df, order_df).to_numpy())
            fit_d, _ = fit_inclusion(in_df, shown_ids)
            say(f"  {label:13s} order: distance {beta[0]:+.3f} (SE {se[0]:.3f}), rating {beta[1]:+.3f}, "
                f"loglik {loglik:.2f} (n {len(order_df)}) | inclusion: distance {fit_d.params['log_distance']:+.3f}, "
                f"rating {fit_d.params['rating']:+.3f}, loglik {fit_d.llf:.2f} (n {len(in_df)})")

    if not TRANSIT_PATH.exists():
        say(f"\nTransit: {TRANSIT_PATH.name} not found; run screen_transit_time.py")
    else:
        report_transit(say, pl_df, pool_df, shown_ids)

    shown_df[["rank", "name", "place_id", "distance_m", "rating", "user_ratings_total"]].to_csv(
        f"{OUT_PREFIX}_cards.csv", index=False)
    Path(f"{OUT_PREFIX}_log.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
