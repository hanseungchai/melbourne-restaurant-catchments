"""Which haversine range holds each TRN-13 zone's pairs, and how often a pair drawn in it lands in the zone?

Claim under test (concepts/transit.md TRN-14 (1); DESIGN.md Q23): the boundary top-up can be drawn on
haversine distance alone, one range per zone, each range holding ~95% of that zone's pairs among the
Google answers already fetched. Where the pipeline relies on it: config.TRANSIT_TOPUP_RANGES_M, the
top-up draw's ranges (transit_samples.draw_transit_topup), and the pilot's expected yield.

Zones (TRN-13 (1)): Google time within +-3 min of a band cutoff, whole minutes (as Google displays them,
SCR-10): zone 1 = 7-13 min (cut 10), zone 2 = 17-23 min (cut 20). Google time: the default route's arrival
from the requested departure (T7 f target, as transit_time_bands), scored only if the default route is in
scope (TRN-11: in_scope or name_mismatch). Range: the 2.5th to 97.5th percentile of the zone's haversine
distances (equal tails), widened outward to a multiple of RANGE_ROUND_M. The share of zone pairs outside it
is the stated gap. Hit rate: among answered pairs inside a range, the share in that zone, in the other
zone, scored but in neither, and not scorable (no answer or default out of scope); calls per zone pair =
1 / hit rate, so 200 zone pairs cost about 200 / hit rate calls. A hint only: these pairs passed the draw's
r5py <= 40 min window; the top-up has none.

Data: the training half of the first fetch (release 20261009; split half == "train") and the whole second
batch (release 20261016, outside the split). The test half and the T5 smoke-test pairs are not read.

Conclusion (run 2026-10-18): 3,252 pairs (1,252 training, 2,000 second batch), 3,239 scorable. Zone 1: 157
pairs, range 350-1,650 m (gap 3.8%); zone 2: 298 pairs, range 850-4,700 m (gap 4.7%); ranges overlap 850-1,650
m. Hint hit rates: range 1 lands 0.345 in zone 1 and 0.306 in zone 2; range 2 0.179 in zone 2. The pilot
(2026-10-18, no window) confirmed range 1 (0.33 / 0.33) but not range 2 (0.03: 28 of 30 over 30 min): the
r5py window had removed the slow far pairs that dominate range 2 when drawn without it.

Inputs (read only): outputs/transit_validation/<subject>/ draw, reserve, split and the two route tables.
No routing, no paid API calls. Self-contained (CLAUDE.md D1).
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
SUBJECT_SUFFIX = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{SUBJECT_SUFFIX}.csv"
RESERVE_PATH = SUBJECT_DIR / f"transit_pairs_reserve_{SUBJECT_SUFFIX}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{SUBJECT_SUFFIX}.csv"
FIRST_ROUTES_PATH = SUBJECT_DIR / f"transit_google_{SUBJECT_SUFFIX}.routes.csv"
SECOND_ROUTES_PATH = SUBJECT_DIR / f"transit_google_20261016_{SUBJECT_SUFFIX}.routes.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_zone_ranges"

SECONDS_PER_MIN = 60
ZONES_MIN = {1: (7, 13), 2: (17, 23)}         # TRN-13 (1): [low, high] whole Google minutes, cut 10 and 20
RANGE_TAIL_SHARE = 0.025                       # each tail left out: the range holds ~95% (TRN-14 (1))
RANGE_ROUND_M = 50                             # range ends widened outward to this step
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]  # TRN-11, as transit_preference_arms
TRAIN_HALF = "train"
TOPUP_TARGET_PER_ZONE = 200                    # TRN-14
PILOT_PER_ZONE = 30                            # TRN-14 (2)


def default_routes(routes_path, draw_nos, source):
    """One row per answered draw_no: Google's default route minutes and whether it is scorable."""
    routes_df = pd.read_csv(routes_path)
    default_df = routes_df[routes_df.is_default].drop_duplicates("draw_no").set_index("draw_no")
    default_df = default_df.reindex(sorted(draw_nos))
    is_scored = default_df.route_scope.isin(GOOGLE_SCOPES) & default_df.arrival_from_request_s.notna()
    return pd.DataFrame({"draw_no": default_df.index, "source": source,
                         "google_min": np.round(default_df.arrival_from_request_s.to_numpy() / SECONDS_PER_MIN),
                         "is_scored": is_scored.to_numpy()})


def zone_of(google_min, is_scored):
    zone = np.zeros(len(google_min), dtype=int)
    for zone_no, (low, high) in ZONES_MIN.items():
        zone[is_scored & (google_min >= low) & (google_min <= high)] = zone_no
    return zone


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    pairs_df = pd.read_csv(PAIRS_PATH, usecols=["draw_no", "haversine_m"])
    reserve_df = pd.read_csv(RESERVE_PATH, usecols=["draw_no", "haversine_m"])
    split_df = pd.read_csv(SPLIT_PATH, usecols=["draw_no", "half"])
    train_draw_nos = set(split_df.loc[split_df.half == TRAIN_HALF, "draw_no"])
    answered_df = pd.concat([default_routes(FIRST_ROUTES_PATH, train_draw_nos, "train_20261009"),
                             default_routes(SECOND_ROUTES_PATH, set(reserve_df.draw_no), "second_20261016")],
                            ignore_index=True)
    answered_df = answered_df.merge(pd.concat([pairs_df, reserve_df]), on="draw_no", how="left")
    assert answered_df.haversine_m.notna().all(), "a pair without haversine"
    answered_df["zone"] = zone_of(answered_df.google_min.to_numpy(), answered_df.is_scored.to_numpy())

    lines = [f"{NAME}, run {run_date}",
             f"pairs: {len(answered_df):,} ({answered_df.source.value_counts().to_dict()}); scorable "
             f"{answered_df.is_scored.sum():,}; zone counts {answered_df.zone.value_counts().sort_index().to_dict()} "
             "(0 = neither or not scorable)", ""]
    ranges = {}
    for zone_no, (low, high) in ZONES_MIN.items():
        zone_m = answered_df.loc[answered_df.zone == zone_no, "haversine_m"]
        q_low, q_high = zone_m.quantile([RANGE_TAIL_SHARE, 1 - RANGE_TAIL_SHARE])
        range_m = (RANGE_ROUND_M * np.floor(q_low / RANGE_ROUND_M), RANGE_ROUND_M * np.ceil(q_high / RANGE_ROUND_M))
        ranges[zone_no] = range_m
        is_out = ~zone_m.between(*range_m)
        lines += [f"zone {zone_no} (Google {low}-{high} min): n {len(zone_m)} "
                  f"({answered_df.loc[answered_df.zone == zone_no, 'source'].value_counts().to_dict()}); haversine m "
                  f"min {zone_m.min():,.0f}, p2.5 {q_low:,.0f}, median {zone_m.median():,.0f}, p97.5 {q_high:,.0f}, "
                  f"max {zone_m.max():,.0f}",
                  f"  range {range_m[0]:,.0f}-{range_m[1]:,.0f} m; gap: {is_out.sum()} zone pairs outside "
                  f"({is_out.mean():.1%}: {(zone_m < range_m[0]).sum()} below, {(zone_m > range_m[1]).sum()} above)"]

    lines += ["", "hit rate among answered pairs inside each range (a hint: these passed the r5py <= 40 min window)"]
    for zone_no, range_m in ranges.items():
        in_range_df = answered_df[answered_df.haversine_m.between(*range_m)]
        other_zone = 3 - zone_no
        hit = (in_range_df.zone == zone_no).mean()
        lines.append(
            f"range {zone_no} ({range_m[0]:,.0f}-{range_m[1]:,.0f} m): n {len(in_range_df)}; zone {zone_no} {hit:.3f}, "
            f"zone {other_zone} {(in_range_df.zone == other_zone).mean():.3f}, scored in neither "
            f"{(in_range_df.is_scored & (in_range_df.zone == 0)).mean():.3f}, not scorable "
            f"{(~in_range_df.is_scored).mean():.3f}; calls per zone pair {1 / hit:.1f}; pilot {PILOT_PER_ZONE} calls "
            f"-> ~{PILOT_PER_ZONE * hit:.0f} zone pairs; {TOPUP_TARGET_PER_ZONE} zone pairs ~ "
            f"{TOPUP_TARGET_PER_ZONE / hit:,.0f} calls (ignoring the other zone's spill)")
        lines.append("  Google minutes inside the range: " + ", ".join(
            f"{label} {share:.2f}" for label, share in pd.cut(
                in_range_df.loc[in_range_df.is_scored, "google_min"], [-1, 6, 13, 16, 23, 30, np.inf],
                labels=["0-6", "7-13", "14-16", "17-23", "24-30", "31+"]).value_counts(normalize=True)
            .sort_index().items()))
    overlap = (max(ranges[1][0], ranges[2][0]), min(ranges[1][1], ranges[2][1]))
    lines.append(f"ranges overlap: {overlap[0]:,.0f}-{overlap[1]:,.0f} m" if overlap[0] < overlap[1]
                 else "ranges do not overlap")

    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    answered_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_pairs.csv", index=False)
    summary_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt"
    summary_path.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nsaved {summary_path}")


if __name__ == "__main__":
    main()
