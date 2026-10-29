"""Share report tables from a finished shares folder (SCR-13, SCR-14, SCR-15, SCR-16).

Unit: expected persons per open slot of the subject = sum over slots of persons / sum over slots of the subject's open
chance (closure-weighted equal weight over open slots, SCR-13). Credits and contention use the same unit, so the
subject plus its denial credits is the band's ceiling (SCR-14).
"""
import numpy as np
import pandas as pd

from functions import share_draws

DONOR_RULE = "donor"
CONTENTION_SIDES = ("above", "below")


def per_open_slot(values_df, value_col, open_sum, by="band"):
    return values_df.groupby(by)[value_col].sum() / open_sum


def headline_table(headline_df, credits_df, hex_reach_df, rating, metric, rules, open_sum):
    """Per band: headline persons and its MC error, residents, each other hours rule, ceiling, reached persons."""
    at_rating = headline_df[(headline_df.focal_rating == rating) & (headline_df.metric == metric)]
    lead = at_rating[at_rating.rule == rules[0]]
    table_df = pd.DataFrame({
        "headline_persons": per_open_slot(lead, "persons", open_sum),
        "mc_se": (lead.persons_se ** 2).groupby(lead.band).sum() ** 0.5 / open_sum,
        "residents": per_open_slot(lead, "residents", open_sum)})
    for rule in rules[1:]:
        table_df[f"{rule}_persons"] = per_open_slot(at_rating[at_rating.rule == rule], "persons", open_sum)
    table_df["ceiling_persons"] = (per_open_slot(credits_df[credits_df.rule == rules[0]], "credit_persons", open_sum)
                                   + table_df.headline_persons)
    table_df["reached_persons"] = per_open_slot(hex_reach_df, "reached", open_sum)
    table_df["share_of_ceiling"] = table_df.headline_persons / table_df.ceiling_persons
    table_df["share_of_reached"] = table_df.headline_persons / table_df.reached_persons
    return table_df


def band_mc_se(draws_df, rule, unit_weights, open_sum):
    """Per band: the headline's MC error from the per-draw values (draws_df: band, reach_slot, rule, draw, persons).
    Draw d is the same hours draw in every unit, so units are correlated: Var(sum_u w_u mean_u) = sum_u sum_v w_u w_v
    cov_uv n_uv / (n_u n_v), cov_uv over the n_uv = min(n_u, n_v) draws both ran (draws 0 .. n - 1 in every unit).
    unit_weights: reach slot -> slots a unit's per-draw value stands for (q's slot-free drive unit: every slot)."""
    out = {}
    for band, band_df in draws_df[draws_df.rule == rule].groupby("band"):
        wide = band_df.pivot(index="draw", columns="reach_slot", values="persons").sort_index()
        values = wide.to_numpy() * wide.columns.map(lambda slot: unit_weights.get(slot, 1)).to_numpy()[None, :]
        n_draws = np.isfinite(values).sum(axis=0)
        assert all(np.isfinite(values[:n, u]).all() for u, n in enumerate(n_draws)), "a unit's draws not 0 .. n - 1"
        variance = 0.0
        for u in range(values.shape[1]):
            for v in range(values.shape[1]):
                common = min(n_draws[u], n_draws[v])
                x, y = values[:common, u], values[:common, v]
                covariance = ((x - x.mean()) * (y - y.mean())).sum() / (common - 1)
                variance += covariance * common / (n_draws[u] * n_draws[v])
        out[band] = np.sqrt(max(variance, 0.0)) / open_sum
    return pd.Series(out)


def metric_curve(headline_df, rating, prefix, rule, open_sum):
    """Persons per band (columns) and metric (rows) whose name starts with prefix ("q" the curve, "top" Top-N)."""
    rows_df = headline_df[(headline_df.rule == rule) & (headline_df.focal_rating == rating)
                          & headline_df.metric.str.startswith(prefix)]
    return rows_df.groupby(["band", "metric"]).persons.sum().unstack(0) / open_sum


def rating_slider(headline_df, metric, rule, open_sum):
    """Persons per band (columns) and slider rating (rows)."""
    rows_df = headline_df[(headline_df.rule == rule) & (headline_df.metric == metric)]
    return rows_df.groupby(["band", "focal_rating"]).persons.sum().unstack(0) / open_sum


def unlock_rating(slider_df, reached, band, min_share):
    """(lowest slider rating capturing >= min_share of the band's reached persons or None, share by rating)."""
    share = slider_df[band] / reached[band]
    hit = share[share >= min_share]
    return (float(hit.index[0]) if len(hit) else None), share


def rarity_lines(venues_df, subject_place_id, slider_ratings, half_width_pct, count_floor, tenths_share,
                 max_denominator, large_base):
    """One row per slider rating (SCR-22): how many rated venues near the subject's review-count percentile show it or
    higher, and the line. Window: |percentile - subject's| <= min(half_width_pct, 100 - subject's), subject excluded;
    percentiles are average ranks among rated venues (rating and > 0 reviews). A denominator above max_denominator
    ("1 in 442", "2 of 883") is restated per large_base ("2 in 1,000"), and per 10,000, 100,000, ... while that
    rounds to 0, so a rare rating never reads as none; "NONE of" (capitals: no peer holds it) keeps the window size."""
    rated_df = venues_df[venues_df.rating.notna() & (venues_df.user_ratings_total > 0)].reset_index(drop=True)
    percentile = rated_df.user_ratings_total.rank(pct=True, method="average") * 100
    is_subject = rated_df.place_id == subject_place_id
    assert is_subject.sum() == 1, "subject is not a single rated venue"
    subject_pct = float(percentile[is_subject].iloc[0])
    half_width = min(half_width_pct, 100 - subject_pct)
    window_df = rated_df[((percentile - subject_pct).abs() <= half_width) & ~is_subject]
    n_window = len(window_df)
    shown = window_df.rating.round(1)
    rows = []
    for rating in slider_ratings:
        n_at_least = int((shown >= rating).sum())
        share = n_at_least / n_window
        if n_at_least == 0:
            rarity = f"NONE of {n_window:,}"
        elif share > tenths_share:
            rarity = f"{round(10 * share)} in 10"
        elif (n_window if n_at_least < count_floor else round(1 / share)) > max_denominator:
            base = large_base
            while round(base * share) == 0:
                base *= 10
            rarity = f"{round(base * share)} in {base:,}"
        elif n_at_least < count_floor:
            rarity = f"{n_at_least} of {n_window:,}"
        else:
            rarity = f"1 in {round(1 / share)}"
        rows.append({"focal_rating": rating, "n_window": n_window, "n_at_least": n_at_least, "share": share,
                     "line": f"Venues with a similar review count: {rarity} show {rating:.1f} or higher"})
    window = {"subject_percentile": subject_pct, "half_width_pct": half_width,
              "min_reviews": int(window_df.user_ratings_total.min()), "max_reviews": int(window_df.user_ratings_total.max())}
    return pd.DataFrame(rows), window


def competitor_table(credits_df, contention_df, ceiling, open_sum, shrink_m, shrink_c, name_share, rule):
    """One row per band and competitor: denial (SCR-14 (1)), contention above and below (SCR-14 (2)), is_named."""
    info_cols = ["place_id", "name", "rating", "user_ratings_total"]
    denial = (credits_df[credits_df.rule == rule].groupby(["band", "place_id"]).credit_persons.sum()
              / open_sum).rename("denial_persons")
    peers = (contention_df[contention_df.rule == rule].groupby(["band", "place_id", "side"]).contention_persons.sum()
             .unstack("side", fill_value=0) / open_sum)
    peers = peers.reindex(columns=list(CONTENTION_SIDES), fill_value=0)
    peers.columns = [f"contention_{side}_persons" for side in peers.columns]
    rows_df = denial.reset_index().merge(peers.reset_index(), on=["band", "place_id"], how="outer").fillna(0)
    info_df = pd.concat([credits_df[info_cols], contention_df[info_cols]]).drop_duplicates("place_id")
    rows_df = rows_df.merge(info_df, on="place_id")
    rows_df["shrunk_key"] = share_draws.shrunk_key(rows_df.rating, rows_df.user_ratings_total, shrink_m, shrink_c)
    band_ceiling = rows_df.band.map(ceiling)
    rows_df["denial_share_of_ceiling"] = rows_df.denial_persons / band_ceiling
    contention = rows_df.contention_above_persons + rows_df.contention_below_persons
    rows_df["is_named"] = (rows_df.denial_share_of_ceiling >= name_share) | (contention / band_ceiling >= name_share)
    columns = ["band", "place_id", "name", "rating", "user_ratings_total", "shrunk_key", "denial_persons",
               "denial_share_of_ceiling", "contention_above_persons", "contention_below_persons", "is_named"]
    return rows_df.sort_values(["band", "denial_persons"], ascending=[True, False])[columns]
