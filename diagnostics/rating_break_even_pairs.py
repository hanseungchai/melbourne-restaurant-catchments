"""At what review count does a higher displayed rating beat a lower one on many reviews, for a diner (DESIGN Q31)?

Claim: the rating key's m (config SCORING_SHRINK_M, SCR-20) sets how many reviews a thin high rating needs before it
outranks a well-reviewed lower one. Q31 asks which m; the 96th's blind pairs rule out m below ~15 but are flat from 15
to 120 (101st check), because none tests a 4.9 on 100-400 reviews against a 4.8 on 1,000+. This set does.
Where the pipeline relies on it: scoring.rating_keys (S*' key), every share run's ordering of rivals.

Pairs (Claude's design, 101st; synthetic: (rating, review count) only, no names, so no brand pulls): the core block
holds the subject's own case (4.8 on 1,664) against a 4.9 or 5.0 on a ladder of counts; a second block checks the
break-even away from the subject's count; a low block tests the cost of high m below the field mean C (a thin 4.0 lifted
above a 4.1 on 900); two repeats with sides swapped check consistency; one obvious pair is a sanity check. Order and
sides shuffled (seeded); the answer key is a separate file, opened only after the judges answer.

Framing (user, 101st: a high count is proof of demand and resilience, not only a clearer signal): the judge picks where
they would go, not which is "better quality", so count-as-demand enters the answer the way it enters a diner's choice.

Key per pair: S*' s = (n r' + m C) / (n + m), r' = r with 5.0 read as 4.975 and 1.0 as 1.025, C 4.25 (copied, D1).
m* = the m at which the two keys tie: picking the higher rating on fewer reviews means the judge's m is below m*,
picking the other means above (low block: reversed, since there shrinkage lifts the thin rating). Answers bound m.

Self-contained (CLAUDE.md D1): imports nothing from functions/, config.py or pipeline modules. No API.

Conclusion: pending (sheet written 2026-10-25; judges: the user's partner and a friend, separately).
"""
import csv
import random
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "diagnostic_data"
NAME = "rating_break_even_pairs"
RUN_DATE = date.today().strftime("%Y%m%d")
SEED = 20261025

SHRINK_C = 4.25                       # field mean, the shrink target (config SCORING_SHRINK_C)
TOP_RATING, TOP_READ = 5.0, 4.975     # a displayed 5.0 read mid-range (config SCORING_TOP_RATING / _READ)
BOTTOM_RATING, BOTTOM_READ = 1.0, 1.025
M_REPORTED = (9, 15, 35, 48)          # the 101st's reruns
SUBJECT_RATING, SUBJECT_REVIEWS = 4.8, 1664

# (block, thin rating, thin count, full rating, full count): "thin" = the side with fewer reviews
CORE_49_COUNTS = (30, 60, 100, 150, 220, 320, 500)
CORE_50_COUNTS = (15, 40, 80, 140, 250)
AWAY_PAIRS = [("away", 4.9, n, 4.8, 600) for n in (40, 120, 300)] \
    + [("away", 4.8, n, 4.7, 1500) for n in (50, 150, 400)]
LOW_PAIRS = [("low", 4.0, 25, 4.1, 900), ("low", 3.9, 40, 4.1, 800), ("low", 4.2, 30, 4.2, 900)]
SANITY_PAIRS = [("sanity", 4.8, SUBJECT_REVIEWS, 4.9, 2500)]
REPEAT_COUNTS = (100, 220)            # core 4.9 pairs asked twice, sides swapped

INSTRUCTIONS = """\
Imagine you are looking for dinner nearby on Google Maps. Each question shows two restaurants.
They serve the same kind of food, cost about the same, are the same distance away and are both open now.
All you can see is the star rating and the number of reviews.
Which one would you go to? Answer A or B. If you honestly can't choose, answer "same".
Go with your first instinct, don't go back to change answers, and don't discuss them with anyone until you're done."""


def read_rating(rating):
    return TOP_READ if rating >= TOP_RATING else BOTTOM_READ if rating <= BOTTOM_RATING else rating


def key(rating, reviews, m):
    return (reviews * read_rating(rating) + m * SHRINK_C) / (reviews + m)


def tie_m(r_thin, n_thin, r_full, n_full):
    """m at which the two keys tie (None if they never do for m > 0)."""
    a, b = read_rating(r_thin) - SHRINK_C, read_rating(r_full) - SHRINK_C
    denominator = n_thin * a - n_full * b
    if denominator == 0:
        return None
    m = n_thin * n_full * (b - a) / denominator
    return m if m > 0 else None


def pairs():
    core = [("core", 4.9, n, SUBJECT_RATING, SUBJECT_REVIEWS) for n in CORE_49_COUNTS] \
        + [("core", 5.0, n, SUBJECT_RATING, SUBJECT_REVIEWS) for n in CORE_50_COUNTS]
    repeats = [("repeat", 4.9, n, SUBJECT_RATING, SUBJECT_REVIEWS) for n in REPEAT_COUNTS]
    return core + AWAY_PAIRS + LOW_PAIRS + SANITY_PAIRS + repeats


def main():
    rng = random.Random(SEED)
    items = pairs()
    rng.shuffle(items)
    sheet, answer_key = [], []
    repeat_sides = {}
    for question, (block, r_thin, n_thin, r_full, n_full) in enumerate(items, start=1):
        thin_is_a = rng.random() < 0.5
        if block in ("core", "repeat") and n_thin in REPEAT_COUNTS:   # a repeat shows the other side
            if n_thin in repeat_sides:
                thin_is_a = not repeat_sides[n_thin]
            repeat_sides[n_thin] = thin_is_a
        a, b = ((r_thin, n_thin), (r_full, n_full)) if thin_is_a else ((r_full, n_full), (r_thin, n_thin))
        sheet.append({"question": question, "A_rating": a[0], "A_reviews": a[1], "B_rating": b[0], "B_reviews": b[1]})
        m_tie = tie_m(r_thin, n_thin, r_full, n_full)
        row = {"question": question, "block": block, "thin_side": "A" if thin_is_a else "B",
               "thin": f"{r_thin} ({n_thin})", "full": f"{r_full} ({n_full})",
               "tie_m": None if m_tie is None else round(m_tie, 1)}
        for m in M_REPORTED:
            thin_wins = key(r_thin, n_thin, m) > key(r_full, n_full, m)
            row[f"pick_m{m}"] = ("A" if thin_is_a else "B") if thin_wins else ("B" if thin_is_a else "A")
        answer_key.append(row)

    DATA_DIR.mkdir(exist_ok=True)
    for suffix, rows in [("sheet", sheet), ("ANSWER_KEY", answer_key)]:
        path = DATA_DIR / f"{NAME}_{RUN_DATE}_{suffix}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    lines = [INSTRUCTIONS, ""] + [
        f"{row['question']:2d}.  A: {row['A_rating']:.1f} stars, {row['A_reviews']:,} reviews"
        f"    B: {row['B_rating']:.1f} stars, {row['B_reviews']:,} reviews    ->  ____"
        for row in sheet]
    text_path = DATA_DIR / f"{NAME}_{RUN_DATE}_sheet.txt"
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(sheet)} questions -> {text_path}")


if __name__ == "__main__":
    main()
