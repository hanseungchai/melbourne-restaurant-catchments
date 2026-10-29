"""Catchment sensitivity: how much does the subject's transit catchment move between stock R5 and the no-wait model?

Claim under test (concepts/reachability.md RCH-13, planned diagnostic, user 2026-10-20; extra, not a gate): the
transit model's known misses (TRN-15: of about the size of the stock-vs-no-wait gap, or smaller) move the output, the
subject's catchment totals within 10 / 20 min (bands 1-2, RCH-1), by a size this run measures. Where the pipeline
would rely on it: the transit interval of RCH-13 and its wording; the reachability pass for bands 1-2.

Experiment (agreed with the user 2026-10-20): stock R5 (rejected: lost reach at 20, TRN-13) vs no-wait (model of
record: first board's 60 s slack removed, at most 1 min faster on a transit trip). If the catchment barely moves
between them, errors of that size barely move the output. Yardstick: the no-wait cut moved +-1 min (9 / 11, 19 / 21).
It measures sensitivity to an error of the known size, not the error itself (no Google), and the subject only (not
competitor order; location-specific error stays a limitation, RCH-13).

Method (Claude's, user-approved 2026-10-20):
  Hexes: uniform random sample of N_SAMPLE_HEXES non-empty hexes (residents, workers or venues > 0) within
    R_SCAN_KM of the subject (frame 67,608 hexes); totals scaled by frame / sample. Direction hex -> subject (ODS-2).
  Departures: N_DEPARTURES drawn from the whole week's open-share histogram (2026-10-10 hours pull, weight = share
    of venues open in the 30-min slot, minute uniform inside it; no floor, user), each on its weekday in the week
    WEEK_START (Mon) to +6 days, inside release 20261016's window (to 2026-11-02).
  Network: v2 pathways, release 20261016, as transit_pathway_network_v2.py (its saved pbf and uniquely named feeds;
    stale-copy guard). r5py TravelTimeMatrix, 1-min window, p49, walk 4.16 km/h.
  Per departure: stock S (cap CAP_MIN), shifted H (departure - 1 min, cap CAP_MIN + 1); walk-only W once (cap
    CAP_MIN). No-wait N = H - 1 if H < W else W (TRN-13). Missing (over the cap) = infinity.
  Total T(m, c, d) = frame / sample x sum over sampled hexes h of weight_h x [t_m(h, d) <= c], weight = residents,
    workers or venue_count; m in {S, N}; c in {10, 20} (plus 9, 11, 19, 21 for N); d a departure.
  Gap = (T(N, c, d) - T(S, c, d)) / T(S, c, d); yardstick = (T(N, c + 1, d) - T(N, c, d)) / T(N, c, d) and
    (T(N, c, d) - T(N, c - 1, d)) / T(N, c, d). Reported per departure, with mean and median over departures;
    90% bootstrap interval of the mean gap over sampled hexes (N_BOOT resamples, departures kept).
  Checks (Claude's rules, set before results): (1) N <= S for every hex and departure, except the model of
    record's unsettled ties (S = W - 1, H = W: N = W = S + 1; TRN-13 "stock S only settles ties", user OK; N uses H
    and W only, as transit_model_compare.py model 1); any other violation is reported and the gap is not read until
    explained. Deviation: the first wording (no exception) was revised after the 500-hex pilot showed 6 such ties,
    before any full result; (2) radius guard: no sampled hex with N or S <= 21 min lies
    beyond GUARD_SHARE x R_SCAN_KM (else widen the radius and rerun).

Prediction (Claude's, written 2026-10-20 before any routing): N <= S everywhere. 10 min: residents gap < 3% (band 1
  is mostly walking). 20 min: residents and workers +4 to +10% under no-wait; venues the same order. The yardstick
  (+-1 min at the cut) is of the same size as the gap at 20 (the gap is a minute at the edge on transit hexes only,
  so somewhat smaller than the +1 min yardstick).

Conclusion (run 2026-10-20; 5,000 hexes x 12 departures, 30 min): checks pass (1: 0 violations, 59 unsettled ties;
  2: farthest hex within 21 min at 4.07 km). The choice of transit model moves the subject's catchment by about a
  tenth: pooled gap (N - S) / S at 20 min residents +0.109 [0.081, 0.144], workers +0.194 [0.132, 0.262], venues
  +0.125 [0.054, 0.279]; at 10 min residents +0.114 [0.042, 0.223] (venues: ~3 in reach, not readable). Per-departure
  gaps at 20 range +0.05 to +0.20 (residents). Yardstick at 20: +1 min +0.045, -1 min +0.102 (residents).
  Prediction missed: larger than predicted at 20 for workers (+19% vs 4-10%) and at 10 (+11% vs < 3%). Why: no-wait
  is not "at most 1 min faster": dropping the first board's slack catches a vehicle stock just misses, so the gain
  is a headway (median 4 min, max 11, on the 306 hex-departures where N < S); and band 1 here is about half transit
  (113 of 213 in-reach hex-departures walk-only). Catchment within 20 min reaches only ~4 km: the 12 km frame left
  ~110 sampled hexes in reach per departure (~18 at 10), so intervals are sample-limited (a census within ~5.5 km
  would tighten them). Deviation: the summary statistic was changed after the first report from the mean
  of per-departure ratios to the ratio of mean totals (the former divided by zero on venue resamples); the per-
  departure medians and ranges are reported beside it.
Census conclusion (rerun 2026-10-20, user: every non-empty hex within 5.5 km, 14,731 hexes x 12 departures, 56 min;
  interval = 5-95% bootstrap over departures): the headline holds and tightens. Gap at 20 min: residents +0.103
  [0.096, 0.109], workers +0.164 [0.154, 0.175], venues +0.166 [0.150, 0.184]; at 10 min: residents +0.129 [0.113,
  0.146], workers +0.158 [0.134, 0.183], venues +0.096 [0.047, 0.151]. Per departure at 20 (residents) +0.07 to +0.13.
  Yardstick at 20 (residents): +1 min +0.041, -1 min +0.060, so the model choice is worth about two minutes of cut.
  Totals within 20 min (mean over departures): residents S 47,298 / N 52,148; workers 18,601 / 21,652; venues 311 /
  363. Check 1 PASS (624 unsettled ties). Check 2 FAIL by margin: farthest hex within 21 min at 4.42 km against the
  4.4 km guard. Not widened (deviation from Claude's rule, decided on this evidence): every hex from 4.42 to 5.5 km
  was routed and none is within 21 min; 0.5% of the 20-min residents lie beyond 4.0 km; and the 12 km sample's
  3,897 hexes beyond 5.5 km reached nothing in 46,764 hex-departures. Reading (Claude's, untested): stock was barred
  for lost reach and no-wait is slightly generous against Google (TRN-15 count ratio 1.084 at 20), so Google's
  catchment likely lies between the two; the transit model's uncertainty on band-2 totals is then of order +-10%.

Inputs (read only): the hex grid, residents, workers and venue-count parquets of the default subject; the opening-
hours histogram; transit_pathway_network_v2's saved pbf and feeds. Self-contained (CLAUDE.md D1). No API calls.
Usage: `python transit_catchment_sensitivity.py sample`, `... route [--limit=N] [--deps=K]` (pilot), `... route`,
`... report`. Census rerun (user, 2026-10-20; every non-empty hex within R_CENSUS_KM, scale 1, the same departures,
interval from resampling departures): the same three commands with `--census`. Saved data (sample, departures, routes) is reused when present and never overwritten; results carry
the run date.
"""
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
NAME = "transit_catchment_sensitivity"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SUBJECT_TAG = "-37.76870_144.97196"
HEX_DIR = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT_TAG
HEX_GRID_PATH = HEX_DIR / f"hex_grid_{SUBJECT_TAG}.gpkg"
HEX_RESIDENTS_PATH = HEX_DIR / f"hex_residents_res2021_{SUBJECT_TAG}.parquet"
HEX_WORKERS_PATH = HEX_DIR / f"hex_workers_wrk2021_{SUBJECT_TAG}.parquet"
HEX_VENUES_PATH = HEX_DIR / f"hex_venue_counts_ven20260925_{SUBJECT_TAG}.parquet"
HOURS_HIST_PATH = PROJECT_ROOT / "outputs" / "opening_hours" / "opening_hours_20261010_hist_30min.csv"
V2_NAME = "transit_pathway_network_v2"
RELEASE = "20261016"
V2_PBF_PATH = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{RELEASE}.osm.pbf"
V2_FEED_DIR = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{RELEASE}"
V2_FEED_PATHS = [V2_FEED_DIR / f"ptv_metro_train_{V2_NAME}_{RELEASE}_moved.zip",
                 V2_FEED_DIR / f"ptv_tram_{V2_NAME}_{RELEASE}.zip",
                 V2_FEED_DIR / f"ptv_metro_bus_{V2_NAME}_{RELEASE}.zip"]

# --- values copied from config.py and the record ---------------------------------------------------
SUBJECT_LAT, SUBJECT_LON = -37.7687014, 144.9719611   # framing.md: [subject] Brunswick East, hex 0
R5_MAX_MEMORY = "7G"                           # as transit_pathway_network_v2.py
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
SINGLE_PERCENTILE = 49                         # as transit_band_metric.py (r5py renames a lone p50)
WALK_SPEED_KMH = 4.16                          # config.WALK_SPEED_KMH
BOARD_SLACK_MIN = 1                            # as transit_band_metric.py
SLOT_MIN = 30                                  # config.HOURS_SLOT_MIN
METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON_EQUATOR = 111_320.0
M_PER_KM = 1000
DEST_ID = -1                                   # destination id disjoint from every hex id (r5py: from_id == to_id reads 0)

# --- design (Claude's, user-approved 2026-10-20) ---------------------------------------------------
R_SCAN_KM = 12
R_CENSUS_KM = 5.5                              # census rerun (user, 2026-10-20): every non-empty hex; guard 4.4 km
CENSUS_TAG = "census_"
DATE_GLOB = "[0-9]" * 8
GUARD_SHARE = 0.8
N_SAMPLE_HEXES = 5000
N_DEPARTURES = 12
HEX_SEED = 20261022
DEPARTURE_SEED = 20261021
WEEK_START = datetime.date(2026, 10, 26)       # a Monday inside release 20261016's window (to 2026-11-02)
CUTS_MIN = [10, 20]
YARDSTICK_STEP_MIN = 1
CAP_MIN = 22                                   # covers cut 20 + yardstick 1 (times <= 21 are all that is read)
N_BOOT = 1000
BOOT_SEED = 20261023
WEIGHTS = ["residents", "workers", "venue_count"]
INTERVAL = (5, 95)                             # percentiles of the bootstrap interval


SET_TAG = ""                                   # "" = the 12 km sample; CENSUS_TAG with --census


def newest(kind, is_tagged=True):
    """Newest saved file <NAME>_<date>_<set tag><kind> (the date glob keeps the sample and census sets apart)."""
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_{DATE_GLOB}_{SET_TAG if is_tagged else ''}{kind}"))
    return paths[-1] if paths else None


def out(kind, is_tagged=True):
    return DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_{SET_TAG if is_tagged else ''}{kind}"


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


# --- sample ----------------------------------------------------------------------------------------
def frame(radius_km):
    """Non-empty hexes within radius_km of the subject, with their weights."""
    import pyogrio
    hex_df = pyogrio.read_dataframe(HEX_GRID_PATH, columns=["hex_id", "centroid_lat", "centroid_lon"], read_geometry=False)
    for path in (HEX_RESIDENTS_PATH, HEX_WORKERS_PATH, HEX_VENUES_PATH):
        layer_df = pd.read_parquet(path)
        hex_df = hex_df.merge(layer_df[["hex_id"] + [c for c in WEIGHTS if c in layer_df]], on="hex_id", validate="one_to_one")
    dy_m = (hex_df.centroid_lat - SUBJECT_LAT) * METRES_PER_DEG_LAT
    dx_m = (hex_df.centroid_lon - SUBJECT_LON) * METRES_PER_DEG_LON_EQUATOR * np.cos(np.radians(SUBJECT_LAT))
    hex_df["distance_km"] = np.hypot(dx_m, dy_m) / M_PER_KM
    is_nonempty = (hex_df[WEIGHTS] > 0).any(axis=1)
    return hex_df[is_nonempty & (hex_df.distance_km <= radius_km)].reset_index(drop=True)


def week_date(day):
    """Histogram day (0 = Sunday) -> its date in the week starting WEEK_START (Monday)."""
    return WEEK_START + datetime.timedelta(days=(day - 1) % 7)


def sample():
    if newest("hexes.csv") is not None:
        print("sample exists:", newest("hexes.csv").name, "(not redrawn)")
        return
    if SET_TAG == CENSUS_TAG:
        census_df = frame(R_CENSUS_KM)
        assert newest("departures.csv", is_tagged=False) is not None, "draw the sample (and its departures) first"
        meta = {"frame_hexes": len(census_df), **{f"frame_{c}": float(census_df[c].sum()) for c in WEIGHTS},
                "sample_hexes": len(census_df), "r_scan_km": R_CENSUS_KM}
        census_df.to_csv(out("hexes.csv"), index=False)
        out("frame.json").write_text(json.dumps(meta, indent=1))
        print(json.dumps(meta, indent=1))
        return
    frame_df = frame(R_SCAN_KM)
    rng = np.random.default_rng(HEX_SEED)
    picked = np.sort(rng.choice(len(frame_df), size=N_SAMPLE_HEXES, replace=False))
    sample_df = frame_df.iloc[picked]
    hist_df = pd.read_csv(HOURS_HIST_PATH)
    rng = np.random.default_rng(DEPARTURE_SEED)
    slots = rng.choice(len(hist_df), size=N_DEPARTURES, replace=True, p=hist_df.share / hist_df.share.sum())
    offsets = rng.integers(0, SLOT_MIN, size=N_DEPARTURES)
    rows = []
    for dep_no, (slot, offset) in enumerate(zip(slots, offsets)):
        slot_row = hist_df.iloc[slot]
        minute_of_day = int(slot_row.minute_of_week) % (24 * 60) + int(offset)
        departure = datetime.datetime.combine(week_date(int(slot_row.day)), datetime.time()) + datetime.timedelta(minutes=minute_of_day)
        rows.append({"dep_no": dep_no, "day_name": slot_row.day_name, "slot": slot_row.slot, "share": slot_row.share,
                     "departure": departure.isoformat(timespec="minutes")})
    deps_df = pd.DataFrame(rows)
    meta = {"frame_hexes": len(frame_df), **{f"frame_{c}": float(frame_df[c].sum()) for c in WEIGHTS},
            "sample_hexes": N_SAMPLE_HEXES, "r_scan_km": R_SCAN_KM, "hex_seed": HEX_SEED, "departure_seed": DEPARTURE_SEED}
    sample_df.to_csv(out("hexes.csv"), index=False)
    deps_df.to_csv(out("departures.csv", is_tagged=False), index=False)
    out("frame.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta, indent=1))
    print(deps_df.to_string(index=False))


# --- routing ---------------------------------------------------------------------------------------
def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (stale copy under the same name)."""
    import hashlib
    from r5py.util.config import Config
    for path in paths:
        cached = Path(Config().CACHE_DIR) / Path(path).name
        if not cached.exists():
            continue
        digests = []
        for candidate in (path, cached):
            with open(candidate, "rb") as file:
                digests.append(hashlib.file_digest(file, "blake2s").hexdigest())
        assert digests[0] == digests[1], f"r5py's cached {cached} differs from {path}: stale working copy"


def load_network(dates):
    sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import
    from r5py import TransportNetwork
    assert V2_PBF_PATH.exists() and all(path.exists() for path in V2_FEED_PATHS), "transit_pathway_network_v2 build / feeds first"
    check_working_copies([V2_PBF_PATH] + V2_FEED_PATHS)
    network = TransportNetwork(V2_PBF_PATH, V2_FEED_PATHS)
    for day in sorted(set(dates)):
        is_covered = network.transit_layer.covers(day)
        print("covers", day, is_covered, flush=True)
        assert is_covered, f"release {RELEASE} does not cover {day}"
    return network


def route(*args):
    options = dict(arg[2:].split("=") for arg in args if arg.startswith("--"))
    limit = int(options.get("limit", 0))
    n_deps = int(options.get("deps", N_DEPARTURES))
    sample_path = newest("hexes.csv")
    assert sample_path is not None, "run sample first"
    sample_df = pd.read_csv(sample_path)
    deps_df = pd.read_csv(newest("departures.csv", is_tagged=False)).head(n_deps)
    if limit:
        sample_df = sample_df.head(limit)
    departures = [datetime.datetime.fromisoformat(value) for value in deps_df.departure]
    network = load_network([value.date() for value in departures])
    import geopandas as gpd
    from r5py import TransportMode, TravelTimeMatrix
    origins = gpd.GeoDataFrame({"id": sample_df.hex_id}, crs="EPSG:4326",
                               geometry=gpd.points_from_xy(sample_df.centroid_lon, sample_df.centroid_lat))
    destinations = gpd.GeoDataFrame({"id": [DEST_ID]}, crs="EPSG:4326", geometry=gpd.points_from_xy([SUBJECT_LON], [SUBJECT_LAT]))

    def ttm(departure, transport_modes, cap_min):
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=transport_modes, max_time=datetime.timedelta(minutes=cap_min), speed_walking=WALK_SPEED_KMH))
        return matrix_df.set_index("from_id")[f"travel_time_p{SINGLE_PERCENTILE}"]

    tag = "pilot" if limit or n_deps < N_DEPARTURES else "routes"
    walk_path = newest(f"{tag}_walk.csv") or out(f"{tag}_walk.csv")
    routes_path = newest(f"{tag}.csv") or out(f"{tag}.csv")
    transit_modes = [TransportMode.TRANSIT, TransportMode.WALK]
    started = datetime.datetime.now()
    if not walk_path.exists():
        walk = ttm(departures[0], [TransportMode.WALK], CAP_MIN)
        walk.rename("walk_min").rename_axis("hex_id").reset_index().to_csv(walk_path, index=False)
        print(f"walk: {len(walk)} hexes after {datetime.datetime.now() - started}", flush=True)
    done = set(pd.read_csv(routes_path).dep_no) if routes_path.exists() else set()
    for dep_no, departure in zip(deps_df.dep_no, departures):
        if dep_no in done:
            continue
        stock = ttm(departure, transit_modes, CAP_MIN)
        shifted = ttm(departure - datetime.timedelta(minutes=BOARD_SLACK_MIN), transit_modes, CAP_MIN + BOARD_SLACK_MIN)
        table_df = pd.DataFrame({"hex_id": stock.index, "dep_no": dep_no, "stock_min": stock.values,
                                 "shifted_min": shifted.reindex(stock.index).values})
        table_df.to_csv(routes_path, mode="a", header=not routes_path.exists(), index=False)
        print(f"departure {dep_no} ({departure}): done after {datetime.datetime.now() - started}", flush=True)
    print(f"done: {tag} -> {routes_path.name} in {datetime.datetime.now() - started}", flush=True)


# --- report ----------------------------------------------------------------------------------------
def times():
    """Long table hex x departure with S, N and W (minutes; infinity = over the cap)."""
    routes_df = pd.read_csv(newest("routes.csv"))
    walk_df = pd.read_csv(newest("routes_walk.csv"))
    table_df = routes_df.merge(walk_df, on="hex_id", validate="many_to_one")
    for column in ("stock_min", "shifted_min", "walk_min"):
        table_df[column] = table_df[column].fillna(np.inf)
    table_df["nowait_min"] = np.where(table_df.shifted_min < table_df.walk_min,
                                      table_df.shifted_min - BOARD_SLACK_MIN, table_df.walk_min)
    return table_df


def totals(table_df, weights_df, scale):
    """T(m, c, d) per departure for every weight: columns <model>_<cut>_<weight>."""
    table_df = table_df.merge(weights_df, on="hex_id")
    rows = {}
    cuts = sorted({c + step for c in CUTS_MIN for step in (-YARDSTICK_STEP_MIN, 0, YARDSTICK_STEP_MIN)})
    for model, column in (("S", "stock_min"), ("N", "nowait_min")):
        for cut in cuts:
            is_in = (table_df[column] <= cut).to_numpy()
            for weight in WEIGHTS:
                rows[f"{model}_{cut}_{weight}"] = (table_df[weight] * is_in).groupby(table_df.dep_no).sum() * scale
    return pd.DataFrame(rows)


def gaps(totals_df):
    """Gap and yardsticks per departure (rows), or pooled over departures as a ratio of means when given the
    one-row frame of mean totals: columns <kind>_<cut>_<weight>."""
    out = {}
    for cut in CUTS_MIN:
        for weight in WEIGHTS:
            base = totals_df[f"N_{cut}_{weight}"]
            out[f"gap_{cut}_{weight}"] = base / totals_df[f"S_{cut}_{weight}"] - 1
            out[f"plus1_{cut}_{weight}"] = totals_df[f"N_{cut + YARDSTICK_STEP_MIN}_{weight}"] / base - 1
            out[f"minus1_{cut}_{weight}"] = 1 - totals_df[f"N_{cut - YARDSTICK_STEP_MIN}_{weight}"] / base
    return pd.DataFrame(out)


def report():
    date = run_date()
    meta = json.loads(newest("frame.json").read_text())
    sample_df = pd.read_csv(newest("hexes.csv"))
    deps_df = pd.read_csv(newest("departures.csv", is_tagged=False))
    table_df = times()
    scale = meta["frame_hexes"] / meta["sample_hexes"]
    weights_df = sample_df[["hex_id"] + WEIGHTS]
    lines = [f"{NAME} report {date}: {table_df.hex_id.nunique()} hexes x {table_df.dep_no.nunique()} departures, "
             f"frame {meta['frame_hexes']} hexes within {meta['r_scan_km']} km, scale {scale:.3f}"]

    # check 1: N <= S
    is_tie = (np.isfinite(table_df.stock_min) & (table_df.stock_min == table_df.walk_min - BOARD_SLACK_MIN) & (table_df.shifted_min == table_df.walk_min)
              & (table_df.nowait_min == table_df.stock_min + BOARD_SLACK_MIN))
    is_violation = (table_df.nowait_min > table_df.stock_min) & ~is_tie
    lines.append(f"check 1 (N <= S but unsettled ties): {int(is_violation.sum())} of {len(table_df)} hex-departures violate"
                 f" -> {'PASS' if not is_violation.any() else 'FAIL'}; unsettled ties (N = S + 1) {int(is_tie.sum())}")
    is_faster = table_df.nowait_min < table_df.stock_min
    gain = (table_df.stock_min - table_df.nowait_min)[is_faster & np.isfinite(table_df.stock_min)]
    lines.append(f"  N < S on {int(is_faster.sum())} hex-departures; gain (S finite) median {gain.median():.0f}, max {gain.max():.0f} min")

    # check 2: radius guard
    max_cut = max(CUTS_MIN) + YARDSTICK_STEP_MIN
    is_reached = (table_df[["stock_min", "nowait_min"]].min(axis=1) <= max_cut)
    reached_km = sample_df.set_index("hex_id").distance_km.reindex(table_df.hex_id[is_reached])
    guard_km = GUARD_SHARE * meta["r_scan_km"]
    lines.append(f"check 2 (radius guard): farthest hex within {max_cut} min at {reached_km.max():.2f} km (guard {guard_km:.1f})"
                 f" -> {'PASS' if reached_km.max() <= guard_km else 'FAIL: widen the radius'}")

    totals_df = totals(table_df, weights_df, scale)
    gaps_df = gaps(totals_df)
    rng = np.random.default_rng(BOOT_SEED)
    hex_ids = sample_df.hex_id.to_numpy()
    boot_rows = []
    is_census = SET_TAG == CENSUS_TAG
    for _ in range(N_BOOT if not is_census else 0):
        drawn = rng.choice(len(hex_ids), size=len(hex_ids), replace=True)
        boot_weights_df = weights_df.iloc[drawn].copy()
        multiplicity = boot_weights_df.groupby("hex_id").size()
        boot_weights_df = boot_weights_df.drop_duplicates("hex_id").set_index("hex_id")
        boot_weights_df[WEIGHTS] = boot_weights_df[WEIGHTS].mul(multiplicity, axis=0)
        boot_rows.append(gaps(totals(table_df, boot_weights_df.reset_index(), scale).mean().to_frame().T).iloc[0])
    for _ in range(N_BOOT if is_census else 0):      # census: no sampling error; resample departures instead
        drawn = rng.choice(len(totals_df), size=len(totals_df), replace=True)
        boot_rows.append(gaps(totals_df.iloc[drawn].mean().to_frame().T).iloc[0])
    boot_df = pd.DataFrame(boot_rows)
    pooled = gaps(totals_df.mean().to_frame().T).iloc[0]

    lines.append("")
    lines.append("Totals (mean over departures; scaled to the frame): S = stock, N = no-wait")
    for cut in CUTS_MIN:
        for weight in WEIGHTS:
            lines.append(f"  {cut:>2} min {weight:<12} S {totals_df[f'S_{cut}_{weight}'].mean():>12,.0f}"
                         f"   N {totals_df[f'N_{cut}_{weight}'].mean():>12,.0f}"
                         f"   (frame {meta[f'frame_{weight}']:,.0f})")
    lines.append("")
    lines.append(f"Gap (N - S) / S and yardsticks (+-1 min at the cut, model N): pooled = ratio of the mean totals over "
                 f"departures, {INTERVAL[0]}-{INTERVAL[1]}% bootstrap over {'departures' if is_census else 'hexes'}; median and range of the per-departure ratios")
    for kind in ("gap", "plus1", "minus1"):
        for cut in CUTS_MIN:
            for weight in WEIGHTS:
                column = f"{kind}_{cut}_{weight}"
                low, high = np.nanpercentile(boot_df[column], INTERVAL)
                values = gaps_df[column]
                lines.append(f"  {kind:<6} {cut:>2} {weight:<12} pooled {pooled[column]:+.3f} [{low:+.3f}, {high:+.3f}]"
                             f"  median {values.median():+.3f}  range {values.min():+.3f} .. {values.max():+.3f}")
    lines.append("")
    lines.append("Per departure (residents): S_10, N_10, gap_10, S_20, N_20, gap_20")
    for dep in deps_df.itertuples():
        if dep.dep_no not in totals_df.index:
            continue
        row = totals_df.loc[dep.dep_no]
        lines.append(f"  {dep.dep_no:>2} {dep.departure} ({dep.day_name}, open share {dep.share:.2f}): "
                     f"{row.S_10_residents:>9,.0f} {row.N_10_residents:>9,.0f} {gaps_df.loc[dep.dep_no, 'gap_10_residents']:+.3f}   "
                     f"{row.S_20_residents:>10,.0f} {row.N_20_residents:>10,.0f} {gaps_df.loc[dep.dep_no, 'gap_20_residents']:+.3f}")
    lines.append("")
    is_walk = table_df.nowait_min == table_df.walk_min
    for cut in CUTS_MIN:
        is_in = table_df.nowait_min <= cut
        switched = (table_df.nowait_min <= cut) & (table_df.stock_min > cut)
        lines.append(f"  cut {cut}: hex-departures in reach (N) {int(is_in.sum())}, of them walk-only {int((is_in & is_walk).sum())};"
                     f" switched in by no-wait {int(switched.sum())}")
    text = "\n".join(lines)
    print(text)
    out("summary.txt").write_text(text + "\n", encoding="utf-8")
    totals_df.join(gaps_df).to_csv(out("per_departure.csv"))


if __name__ == "__main__":
    if "--census" in sys.argv:
        sys.argv.remove("--census")
        SET_TAG = CENSUS_TAG
    {"sample": sample, "route": route, "report": report}[sys.argv[1]](*sys.argv[2:])
