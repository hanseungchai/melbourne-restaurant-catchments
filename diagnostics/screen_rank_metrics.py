"""Which card metrics move with list position across all transcribed Google Maps screens? (DESIGN.md Q19 (b))

Claim (Q19 (b), user 2026-10-13): within reach, better-rated venues are shown first, distance held roughly equal.
screen_rank_drivers.py fits one screen at a time on venue-table values; this script asks the user's 107th
question across every screen we hold: distance, rating, review count, price, open status and time to closing
(Claude's hunch), each read off the card itself as the diner saw it, so no venue matching is needed and the
partner's own transcription can join.

Data (saved; no requests), all transcribed by eye, sponsored cards and repeat cards dropped:
  screen_match_20261025_phone.csv           the user's phone 12:06-12:12, 107 cards
  screen_match_20261025_partner_phone.csv   the partner's phone 13:34-13:35, 27 cards (Claude's transcription)
  screen_match_20261025_partner_phone_1336_1459_partner_transcribed.csv  the partner's own transcription,
      unchecked against her screenshots: 13:36 account (13 cards, "map searched a wider area"), 14:58-14:59
      account and 14:58 incognito (rows in file order taken as list order)
  screen_match_20261025_browser.csv         the user's browser 12:19-12:21, 29 cards (no card distance)
Distance is the card's own rounded figure (from the device's position). Time to closing: minutes from the card's
clock to its "Closes ..." time (a weekday means tomorrow; a time before the clock means after midnight); open
venues only. Price: midpoint of the card's range.

Two readings:
  per screen  Spearman rho, list position vs each metric (positive = later as the metric grows)
  pooled      Plackett-Luce over the screens with card distance, each screen its own sequence of choices,
              all metrics together, standardised over the pooled cards; complete cases only. The three
              partner screens of 13:36-14:59 overlap heavily (top-20 Spearman 0.96-0.98, 106th), so pooling
              counts much the same list three times: the pooled intervals are too narrow, read them as rough.
User's observation, 2026-10-25 (illustration, not transcribed): zooming the map leaves the list unchanged except
the sponsored cards.

Results (one run per day): diagnostic_data/screen_rank_metrics_<run date>_{log.txt,cards.csv}

Conclusion (run 20261025, read in the 107th; no pass rule applied): distance leads, then rating, then open status;
review count and price add nothing to the order. Joint fit on the two distinct sessions, per 1 SD: log distance
-1.11, rating +0.78, open +0.47, log hours to closing +0.21 (interval spans 0), log reviews -0.04. The form and size
are Huff's (lambda ~ 2.1 per log metre). The partner's 13:36 screen (wider search area) runs the other way on
distance (n 12). Read with DESIGN Q19 (107th): the order runs from the map's search anchor, so this describes
first exposure, not the flagship's share rule (framing.md FRM-27).
"""

import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NAME = "screen_rank_metrics"
RUN_DATE = date.today().strftime("%Y%m%d")
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
OUT_PREFIX = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}"

OWN_SCREENS = {   # Claude's transcriptions: screen -> (file, label)
    "phone": ("screen_match_20261025_phone.csv", "user phone 12:06-12:12"),
    "partner_1334": ("screen_match_20261025_partner_phone.csv", "partner phone 13:34-13:35"),
    "browser": ("screen_match_20261025_browser.csv", "user browser 12:19-12:21"),
}
PARTNER_CSV = "screen_match_20261025_partner_phone_1336_1459_partner_transcribed.csv"
PARTNER_SCREENS = {   # the partner's transcription: screen -> (session, screenshot times, label)
    "partner_1336_acc": ("account", ["13:36"], "partner account 13:36 (wider area)"),
    "partner_1458_acc": ("account", ["14:58", "14:59"], "partner account 14:58-14:59"),
    "partner_1458_inc": ("incognito", ["14:58"], "partner incognito 14:58"),
}
OPEN_STATUSES = {"open", "closing soon", "open 24 hours"}
CLOSED_STATUSES = {"closed", "opens soon"}
YES = "yes"
MINUTES_PER_DAY = 24 * 60
OPEN_24H_MIN = MINUTES_PER_DAY            # "Open 24 hours" read as a full day left
METRICS = ["distance_m", "rating", "n_reviews", "price_mid", "is_open", "min_to_close"]
PL_COVARIATES = ["log_distance", "rating", "log_reviews", "is_open", "log_hours_left"]
Z_95 = 1.96
MIN_PAIRS = 5                             # fewest cards for a per-screen Spearman

CLOSES_RE = re.compile(r"closes\s+(?:(mon|tue|wed|thu|fri|sat|sun)\w*\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?"
                       r"(?:\s+(mon|tue|wed|thu|fri|sat|sun)\w*)?", re.I)
PRICE_RE = re.compile(r"\$(\d+)\s*-\s*(\d+)")


def clock_min(text):
    hours, minutes = str(text).split(":")
    return int(hours) * 60 + int(minutes)


def minutes_to_close(hours_text, clock):
    if pd.isna(hours_text):
        return np.nan
    if "24 hours" in str(hours_text).lower():
        return OPEN_24H_MIN
    found = CLOSES_RE.search(str(hours_text))
    if not found:
        return np.nan
    day_before, hour, minute, meridiem, day_after = found.groups()
    hour = int(hour) % 12 + (12 if meridiem and meridiem.lower() == "pm" else 0) if meridiem else int(hour)
    close_min = hour * 60 + int(minute or 0)
    now_min = clock_min(clock)
    if day_before or day_after or close_min <= now_min:
        close_min += MINUTES_PER_DAY
    return close_min - now_min


def price_mid(text):
    found = PRICE_RE.search(str(text))
    return (int(found.group(1)) + int(found.group(2))) / 2 if found else np.nan


def open_flag(status, hours_text):
    status = str(status).lower()
    if status in OPEN_STATUSES or "24 hours" in str(hours_text).lower():
        return 1.0
    if status in CLOSED_STATUSES:
        return 0.0
    return np.nan


def load_own(screen, file_name):
    cards_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / file_name)
    if "is_sponsored" in cards_df:
        cards_df = cards_df[~cards_df["is_sponsored"].astype(bool)]
    if "is_repeat" in cards_df:
        cards_df = cards_df[~cards_df["is_repeat"].astype(bool)]
    return pd.DataFrame({
        "screen": screen, "name": cards_df["name"], "clock": cards_df["clock"],
        "distance_m": cards_df["distance_m"] if "distance_m" in cards_df else np.nan,
        "rating": cards_df["rating"], "n_reviews": cards_df["n_reviews"], "price": cards_df["price"],
        "status": cards_df["open_status"], "hours": cards_df["hours_note"]})


def load_partner(screen, session, times):
    cards_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / PARTNER_CSV)
    cards_df = cards_df[(cards_df["session"] == session) & cards_df["screenshot_time"].isin(times)]
    if screen == "partner_1336_acc":
        cards_df = cards_df[cards_df["group"].str.startswith("acc13")]
    cards_df = cards_df[cards_df["sponsored"] != YES]
    cards_df = cards_df[cards_df["name"] != cards_df["name"].shift()]   # a card listed twice in a row
    return pd.DataFrame({
        "screen": screen, "name": cards_df["name"], "clock": cards_df["screenshot_time"],
        "distance_m": cards_df["distance_m"], "rating": cards_df["rating"],
        "n_reviews": cards_df["review_count"], "price": cards_df["price_range"],
        "status": cards_df["status"], "hours": cards_df["hours"]})


def build_cards():
    frames = [load_own(screen, file_name) for screen, (file_name, _) in OWN_SCREENS.items()]
    frames += [load_partner(screen, session, times) for screen, (session, times, _) in PARTNER_SCREENS.items()]
    cards_df = pd.concat(frames, ignore_index=True)
    cards_df["position"] = cards_df.groupby("screen").cumcount() + 1
    cards_df["price_mid"] = cards_df["price"].map(price_mid)
    cards_df["is_open"] = [open_flag(s, h) for s, h in zip(cards_df["status"], cards_df["hours"])]
    cards_df["min_to_close"] = [minutes_to_close(h, c) if o == 1 else np.nan
                                for h, c, o in zip(cards_df["hours"], cards_df["clock"], cards_df["is_open"])]
    cards_df["n_reviews"] = cards_df["n_reviews"].fillna(0)
    return cards_df


def plackett_luce(sequences):
    """sequences: list of (n_i, k) arrays, each in list order. Pooled beta, SEs, log-likelihood."""
    def negloglik(beta):
        total = 0.0
        for x in sequences:
            u = x @ beta
            tail_lse = np.logaddexp.accumulate(u[::-1])[::-1]
            total -= (u - tail_lse)[:-1].sum()
        return total

    n_cov = sequences[0].shape[1]
    beta = minimize(negloglik, np.zeros(n_cov), method="BFGS").x
    info = np.zeros((n_cov, n_cov))
    for x in sequences:
        u = x @ beta
        for i in range(len(x) - 1):
            w = np.exp(u[i:] - u[i:].max())
            w /= w.sum()
            centred = x[i:] - w @ x[i:]
            info += centred.T @ (centred * w[:, None])
    return beta, np.sqrt(np.diag(np.linalg.inv(info))), -negloglik(beta)


def pl_design(cards_df):
    design_df = cards_df.dropna(subset=["distance_m", "rating", "is_open"]).copy()
    design_df = design_df[(design_df["is_open"] == 0) | design_df["min_to_close"].notna()]
    design_df["log_distance"] = np.log(design_df["distance_m"])
    design_df["log_reviews"] = np.log1p(design_df["n_reviews"])
    is_open = design_df["is_open"] == 1
    design_df["log_hours_left"] = np.log(design_df["min_to_close"] / 60)
    for col in PL_COVARIATES:
        ref = design_df.loc[is_open, col] if col == "log_hours_left" else design_df[col]
        design_df[col] = (design_df[col] - ref.mean()) / ref.std()
    design_df.loc[~is_open, "log_hours_left"] = 0.0   # closed venues: no time left, the open flag carries them
    return design_df


def main():
    lines = []

    def say(text=""):
        print(text)
        lines.append(text)

    cards_df = build_cards()
    labels = {s: v[-1] for s, v in {**OWN_SCREENS, **PARTNER_SCREENS}.items()}
    say(f"{NAME} run {RUN_DATE}: card metrics vs list position, sponsored and repeat cards dropped")
    say()
    say("Spearman rho, position vs metric (positive = later in the list as the metric grows); n in brackets")
    header = f"  {'screen':38s}" + "".join(f"{m:>17s}" for m in METRICS)
    say(header)
    for screen, screen_df in cards_df.groupby("screen", sort=False):
        cells = []
        for metric in METRICS:
            pair_df = screen_df[["position", metric]].dropna()
            if len(pair_df) < MIN_PAIRS or pair_df[metric].nunique() < 2:
                cells.append(f"{'-':>17s}")
                continue
            rho, p_value = spearmanr(pair_df["position"], pair_df[metric])
            star = "*" if p_value < 0.05 else " "
            cells.append(f"{rho:+8.2f}{star}({len(pair_df):3d})  ")
        say(f"  {labels[screen] + f' [{len(screen_df)}]':38s}" + "".join(cells))
    say("  * p < 0.05. min_to_close over open venues only. Browser cards carry no distance.")
    say()

    design_df = pl_design(cards_df)
    for title, screens in [("all five screens with card distance", None),
                           ("distinct sessions only (user phone, partner 13:34)", ["phone", "partner_1334"])]:
        part_df = design_df if screens is None else design_df[design_df["screen"].isin(screens)]
        sequences = [g.sort_values("position")[PL_COVARIATES].to_numpy()
                     for _, g in part_df.groupby("screen", sort=False)]
        beta, se, loglik = plackett_luce(sequences)
        say(f"Plackett-Luce, {title}: per 1 SD, positive = placed earlier; n {len(part_df)} cards, "
            f"{len(sequences)} screens, loglik {loglik:.2f}")
        for col, b, s in zip(PL_COVARIATES, beta, se):
            say(f"  {col:15s} {b:+.3f}  95% [{b - Z_95 * s:+.3f}, {b + Z_95 * s:+.3f}]")
        say()
    dropped = len(cards_df[cards_df["screen"] != "browser"]) - len(design_df)
    say(f"Complete cases: {len(design_df)} of {len(cards_df[cards_df['screen'] != 'browser'])} cards "
        f"({dropped} dropped: no rating, open status or parsable closing time). log_hours_left is standardised "
        "over open cards and set to 0 for closed ones.")

    cards_df.to_csv(f"{OUT_PREFIX}_cards.csv", index=False)
    Path(f"{OUT_PREFIX}_log.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
