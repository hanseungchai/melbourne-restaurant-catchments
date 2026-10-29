"""Scoring report (94th): tables from the subject's finished shares folder (scoring.build_shares), written into it.

report_shares:  per band the headline (config.SCORING_HEADLINE_Q, the headline hours rule, the subject's own rating) in
                persons per open slot of the subject, the curve over q, Top-N, the rating slider, the band-3 unlock
                (config.SHARE_REPORT_UNLOCK_*), and one row per band and competitor with its denial credit and
                contention (SCR-14), and the rarity line per slider rating (SCR-22). Checks the ceiling (subject +
                credits) against the draws' entered persons.
profile_shares: the census profile (functions/census_profile.py) of the persons captured and of those reached, per
                band, beside the comparison region (DESIGN "Demographic showcase").
"""
import json

import pandas as pd
import pyogrio

import config
import reachability
import scoring
from functions import census_profile, reach_table, share_report
from functions.output_helper import project_relative

SHARE_RULES = ("q", "staged")       # q persistence (SCR-15, build_shares); staged best-of-K (SCR-23, build_staged_shares)
HEX_POP_COLUMNS = ["hex_id", "centroid_lat", "centroid_lon", "residents", "workers"]
REACHED_COL = "reached"
CAPTURED_KIND, REACHED_KIND = "captured", "reached"
SIDES = [("residents", "PROFILE_RESIDENT_TABLES", census_profile.SA2_COL),
         ("workers", "PROFILE_WORKER_TABLES", census_profile.DZN_COL)]


def log(message):
    scoring.log(message)


def headline_metric(rule=SHARE_RULES[0]):
    if rule == SHARE_RULES[0]:
        return f"q{config.SCORING_HEADLINE_Q:.2f}"
    return scoring.staged_metric(config.SCORING_HEADLINE_K)


def report_inputs(subject_lat, subject_lon, rule=SHARE_RULES[0]):
    """(shares folder of the share rule, summary, subject's open chance per slot, sum over the report's slots, hex
    populations)."""
    assert rule in SHARE_RULES, f"unknown share rule {rule}"
    build = scoring.build_shares if rule == SHARE_RULES[0] else scoring.build_staged_shares
    folder = build(subject_lat, subject_lon)
    summary = json.loads((folder / scoring.SUMMARY_FILE).read_text(encoding="utf-8"))
    open_df = pd.read_parquet(config.VENUE_OPEN_SHARE_PATH, filters=[("place_id", "==", summary["subject"]["place_id"])])
    open_of = open_df.set_index("slot").open_share
    hex_df = pyogrio.read_dataframe(reachability.drive_inputs(subject_lat, subject_lon)["hex_nodes"],
                                    read_geometry=False, columns=HEX_POP_COLUMNS)
    hex_df[["residents", "workers"]] = hex_df[["residents", "workers"]].fillna(0)
    hex_df["persons"] = hex_df.residents + hex_df.workers
    return folder, summary, open_of, hex_df


def hex_weights(folder, open_of, columns):
    """Per band and slot row of hex_shares, the subject's reach weighted by its open chance (REACHED_COL)."""
    shares_df = pd.read_parquet(folder / scoring.HEX_SHARES_FILE, columns=["band", "slot", "hex_id", "chance"] + columns)
    assert shares_df.slot.map(open_of).notna().all(), "a slot without the subject's open chance"
    shares_df[REACHED_COL] = shares_df.chance * shares_df.slot.map(open_of)
    return shares_df


def report_shares(subject_lat, subject_lon, rule=SHARE_RULES[0]):
    folder, summary, open_of, hex_df = report_inputs(subject_lat, subject_lon, rule)
    metric, rules, lead_rule = headline_metric(rule), config.SCORING_HOURS_RULES, config.SCORING_HOURS_RULES[0]
    headline_df = pd.read_parquet(folder / scoring.HEADLINE_FILE)
    credits_df = pd.read_parquet(folder / scoring.CREDITS_FILE)
    contention_df = pd.read_parquet(folder / scoring.CONTENTION_FILE)
    slots = sorted(headline_df.slot.unique())
    open_sum = float(open_of.reindex(slots).sum())
    rating = summary["subject"]["rating"]

    shares_df = hex_weights(folder, open_of, [])
    shares_df = shares_df.join(hex_df.set_index("hex_id").persons, on="hex_id")
    shares_df[REACHED_COL] *= shares_df.persons
    table_df = share_report.headline_table(headline_df, credits_df, shares_df, rating, metric, rules, open_sum)

    draws_df = pd.read_parquet(folder / scoring.DRAWS_FILE)
    # MC error from per-draw band totals (slots share hours draws); the old sum of slot errors kept for comparison
    table_df["mc_se_units_independent"] = table_df.mc_se
    table_df["mc_se"] = share_report.band_mc_se(draws_df, lead_rule, {reach_table.DRIVE_SLOT: len(slots)}, open_sum)
    entered = draws_df[draws_df.rule == lead_rule].groupby(["band", "reach_slot"]).entered_persons.mean()
    unit_slots = [len(slots) if slot == reach_table.DRIVE_SLOT else 1 for _, slot in entered.index]
    entered_ceiling = (entered * unit_slots).groupby("band").sum() / open_sum
    gap = ((table_df.ceiling_persons - entered_ceiling) / entered_ceiling).abs().max()
    assert gap < scoring.DENIAL_TOLERANCE, f"ceiling off the draws' entered persons by {gap:.1e}"

    slider_df = share_report.rating_slider(headline_df, metric, lead_rule, open_sum)
    has_unlock_band = config.SHARE_REPORT_UNLOCK_BAND in slider_df.columns          # staged: bands 1-2 only
    if has_unlock_band:
        unlock, unlock_share = share_report.unlock_rating(slider_df, table_df.reached_persons,
                                                          config.SHARE_REPORT_UNLOCK_BAND,
                                                          config.SHARE_REPORT_UNLOCK_SHARE)
    competitors_df = share_report.competitor_table(credits_df, contention_df, table_df.ceiling_persons, open_sum,
                                                   config.SCORING_SHRINK_M, config.SCORING_SHRINK_C,
                                                   config.SHARE_REPORT_NAME_SHARE, lead_rule)
    table_df.to_csv(folder / config.SHARE_REPORT_HEADLINE_NAME.format(metric=metric))
    competitors_path = folder / config.SHARE_REPORT_COMPETITORS_NAME.format(metric=metric, rule=lead_rule)
    competitors_df.to_csv(competitors_path, index=False)

    log(f"report: {summary['subject']['name']} at {rating}, {metric}, {lead_rule} hours; persons per open slot "
        f"(open-chance sum {open_sum:.2f}); ceiling vs entered {gap:.1e}")
    for band, row in table_df.iterrows():
        log(f"  band {band}: {row.headline_persons:,.1f} (MC {row.mc_se:.1f}), {row.share_of_ceiling:.1%} of ceiling "
            f"{row.ceiling_persons:,.0f}; slider " + ", ".join(f"{r}: {v:,.0f}" for r, v in slider_df[band].items()))
    if has_unlock_band:
        log(f"  band {config.SHARE_REPORT_UNLOCK_BAND} unlock (>= {config.SHARE_REPORT_UNLOCK_SHARE:.0%} of reached): "
            f"{unlock}; share by rating " + ", ".join(f"{r}: {v:.2%}" for r, v in unlock_share.items()))
    log(f"  competitors: {project_relative(competitors_path)} ({len(competitors_df):,} rows, "
        f"{int(competitors_df.is_named.sum())} named)")

    venues_df = pd.read_csv(reachability.drive_inputs(subject_lat, subject_lon)["venues_with_hex"],
                            usecols=scoring.VENUE_COLUMNS).drop_duplicates("place_id")
    rarity_df, window = share_report.rarity_lines(venues_df, summary["subject"]["place_id"], slider_df.index,
                                                  config.SHARE_REPORT_RARITY_HALF_WIDTH_PCT,
                                                  config.SHARE_REPORT_RARITY_COUNT_FLOOR,
                                                  config.SHARE_REPORT_RARITY_TENTHS_SHARE,
                                                  config.SHARE_REPORT_RARITY_MAX_DENOMINATOR,
                                                  config.SHARE_REPORT_RARITY_LARGE_BASE)
    rarity_path = folder / config.SHARE_REPORT_RARITY_NAME
    rarity_df.to_csv(rarity_path, index=False)
    log(f"  rarity (SCR-22): {rarity_df.n_window.iloc[0]:,} venues, percentile {window['subject_percentile']:.2f} "
        f"± {window['half_width_pct']}, {window['min_reviews']:,}-{window['max_reviews']:,} reviews; "
        f"{project_relative(rarity_path)}")
    for line in rarity_df.line:
        log(f"    {line}")
    return folder


def profile_shares(subject_lat, subject_lon, rule=SHARE_RULES[0]):
    folder, summary, open_of, hex_df = report_inputs(subject_lat, subject_lon, rule)
    metric = headline_metric(rule)
    shares_df = hex_weights(folder, open_of, [metric])
    weights_df = shares_df.groupby(["band", "hex_id"])[[metric, REACHED_COL]].sum().reset_index()
    hex_df = hex_df[hex_df.hex_id.isin(weights_df.hex_id.unique())]
    areas_df, comparison_sa2, comparison_dzn = census_profile.hex_areas(
        hex_df, config.PROFILE_SA1_BOUNDARIES_PATH, config.PROFILE_DZN_BOUNDARIES_PATH, config.PROFILE_STATE,
        config.PROFILE_COMPARISON_GCC)
    weights_df = weights_df.join(areas_df, on="hex_id").join(hex_df.set_index("hex_id")[["residents", "workers"]],
                                                             on="hex_id")
    rows, worst_match = [], {}
    for side, tables_name, area_col in SIDES:
        comparison = comparison_sa2 if area_col == census_profile.SA2_COL else comparison_dzn
        for metric_name, (path, level, groups) in getattr(config, tables_name).items():
            mix_df, total = census_profile.area_mix(path, level, groups, config.PROFILE_EXCLUDED_CATEGORIES)
            comparison_mix = census_profile.comparison_mix(mix_df, total, comparison)
            for band, band_df in weights_df.groupby("band"):
                for kind, col in [(CAPTURED_KIND, metric), (REACHED_KIND, REACHED_COL)]:
                    mix, matched = census_profile.profile(band_df[col] * band_df[side], band_df[area_col], mix_df)
                    worst_match[side] = min(worst_match.get(side, 1.0), matched)
                    rows += [{"side": side, "metric": metric_name, "category": category, "band": band, "kind": kind,
                              "share": share, "comparison": comparison_mix[category]}
                             for category, share in mix.items()]
    profile_df = pd.DataFrame(rows)
    path = folder / config.SHARE_REPORT_PROFILE_NAME.format(metric=metric, rule=config.SCORING_HOURS_RULES[0])
    profile_df.to_csv(path, index=False)
    log(f"profile: {project_relative(path)} ({len(profile_df):,} rows); hexes without an SA2 "
        f"{areas_df[census_profile.SA2_COL].isna().mean():.2%}; weight matched to a census area, worst "
        + ", ".join(f"{side} {share:.2%}" for side, share in worst_match.items()))
    return path
