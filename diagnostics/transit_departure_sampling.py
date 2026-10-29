"""Transit departure sampling: how few departures per day give the same catchment readings as a dense schedule?

Question (DESIGN.md Q25 subject pass, Q26 60-venue sample; user, 2026-10-23, 80th autonomous run): the subject pass
plans one random-minute departure per 30-min slot (Q25, k = 1); the 60-venue sample's departures are open (Q26). Each
departure costs the same, so the schedule sets the cost. Where the pipeline would rely on it: the transit
reachability pass (RCH-21, RCH-23) and R-bar's venue sample (RCH-7). Measurement for a cost-of-choice table; no
verdict, the schedule is the user's.

Method (free: frozen transit model, no API):
  Model: the frozen jar (TRN-16) on the v2 pathways network of release 20261016, TravelTimeMatrix at a 1-min window,
    percentile 49, walk 4.143 km/h, transit + walk, as reachability_transit_pilot.py (copied, D1). Direction hex ->
    venue (RCH-16). Max time ROUTE_MAX_MIN; band 2 = rounded minutes <= 20, i.e. <= 1,229 s (SCR-10), band 1 <= 629 s.
  Venues: the 8 of reachability_venue_compare (subject, branch, inner / mid / outer pairs): density mix.
  Origins: per venue, its envelope = populated hexes (residents + workers >= 1) with oracle <= ENVELOPE_MIN at any of
    reachability_graph_oracle's three saved departures (single-departure oracle, cut 30 + 5 min margin; RCH-26). A
    seeded simple random sample of ORIGINS_PER_VENUE per venue (all if fewer); the union is routed once to every venue
    hex (8,959), so each origin's competitor count is exact. A venue's estimates use only its own sample, weighted
    N_v / n_v (inclusion f_v = n_v / N_v).
  Days: DAY_WINDOWS (dates inside the release's window, Oct 22 - Nov 2); slots of 30 min over the subject's open
    hours (Places pull 2026-10-10), plus extra hours where stated. Dense reference: DEPARTURES_PER_SLOT departures per
    slot, every STEP_MIN min from a seeded offset in [0, STEP_MIN).
  Readings per venue v, departure d (band 2 unless stated): persons P_v(d) = sum over origins h reaching v of
    persons_h / f_v; flat share F_v(d) = sum persons_h / K_h(d) / f_v, K_h(d) = venues (not hexes) h reaches
    (SCR-3's N -> infinity limit, a share proxy before scoring exists; Claude's); competitor overlap vector
    C_v(d)[v'] = sum persons_h [h reaches v and v'] / f_v. Headline per venue and day = equal-weight mean over the
    day's slots of the slot mean (SCR-13).
  Schemes (from the dense reference; no extra routing): k random-minute departures per slot (k = 1, 2, 3, 6), every
    s-th slot (s = 1, 2, 3, 4; phase random) or the whole day; error of the scheme's day headline against the true
    one (infinitely many departures), as MSE = slot-skipping bias^2 (averaged over phases) + departure variance,
    from per-slot means mu and within-slot variances sigma^2 (6 departures, ddof 1): variance part
    (1 / m^2) sum over chosen slots sigma^2 / k; bias part (mean of chosen mu - mean of all mu)^2 minus its own
    noise sum a^2 sigma^2 / 6 (floored at 0 after averaging over phases). Reported as relative RMS error (sqrt MSE /
    headline); competitor overlap as relative L2 error (sqrt of summed element MSEs / L2 norm of the headline vector).
    Also: the dense reference's own error, day types compared on their common slots (Wed vs Fri, Sat vs Sun; the
    difference against its standard error), the within-slot vs between-slot split.
  Origin subsampling inflates the departure variance of a total by its independent part; within-slot variance is
    estimated for the full envelope: Var(S) = Var(sum_s p_h x_h) / f^2 - (1 / f^2 - 1 / f) sum_s p_h^2 var(x_h)
    (Horvitz-Thompson for the double sum; floored at 0), the raw subsample figure reported beside it.
  Changed before any results were read (same day): the competitor error was planned as L1 over simulated draws; L2
    lets the error split into variance and bias per element and take the subsampling correction; the analytic MSE
    replaces simulation for the same reason (simulation from a pool of 6 understates the error).

Reading rule (written before any results; Claude's, not user-approved): report only. A scheme is "close" if its
  relative RMS error on the day headline is <= 2% for persons and flat share and its competitor overlap relative L2
  error is <= 5%, on every venue and day (band 2); the cheapest close scheme is reported as a proposal, never adopted.

Conclusion (run 2026-10-23, 80th autonomous; facts; band 2 unless stated; 3,949 origins = 500 per venue; 252 dense
  departures Wed / Sat / Fri / Sun, 130-205 s each; the route run was paused after Sat for the window mode and resumed):
  Departure noise dominates: within-slot SD of persons (corrected for subsampling) subject 16-20%, inner 1 23-26%,
  mid 1 25-40%, mid 2 18-24%, outer 2 14-18%, Melbourne Central 4-6%, inner 2 5-8%, outer 1 0 (walk-only); the SD of
  slot means is 3-14%. Reading rule: no scheme is "close" (2% / 5%) on every venue and day, dense included at day level
  (k = 6 every slot: worst 5.1% Wed). One departure per slot (Q25 plan, 42 a week): week headline error subject 3.7%
  persons / 4.2% flat share, worst venue 6.7% / 8.0%; Neyman by day type at the same budget 2.9% / 3.3%. Skipping
  slots always loses to spreading the same departures over every slot. Slot resemblance (reach maps): for the noisy
  venues slots differ no more than a slot from itself (median ratio 0.92-1.01; adjacent 0.89-1.03); where noise is low
  (inner 2, Melbourne Central) adjacent slots still match (1.01 / 0.98) but day types differ (same clock 1.36 / 1.08);
  late weekend evenings stand out at the central venues. Day types on common slots: Fri ~ Wed (all |z| < 2 except
  inner 2 -6%); Sun vs Sat -12% to +7% (z up to 3.4); Sat vs Wed evening lower by 3-20% (inner 2 z -10). Span scheme
  (Claude's spans: weekday evening, weekend lunch / dinner, Sat late; Neyman, >= 1 per span): equal error to one per
  slot with 23-28 departures for the noisy venues (vs 42), 37-41 for the central ones. R-bar over 60 venues: one per
  slot 0.53%; 7 per venue (one per span) 0.95%, 12 -> 0.77%, 24 -> 0.54%. Noise / spread of headlines across venues
  (log) 0.0006. Window (stock reporting, 5 percentiles, Wed): expected catchment / dense mean 0.93-1.02, within 2 SE
  on every slot for the noisy venues, biased low where noise is low (top bin read 0.95); one 30-min window ~3.6 singles.
  The exact version of the window is transit_r5_patch_reach.py (P8r).

Inputs (read only): the frozen jar, transit_pathway_network_v2's 20261016 network files, reachability_graph_oracle's
saved oracle sets, reachability_venue_compare's venues, the hex nodes table, venues with hex. Self-contained
(CLAUDE.md D1). No API calls. One JVM per process.
Usage: `python transit_departure_sampling.py timing | route | analyse | window`.
"""
import datetime
import hashlib
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "-37.76870_144.97196"
FILE_TAG = f"res2021_wrk2021_ven20260925_{SUBJECT}"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_departure_sampling"
V2_NAME = "transit_pathway_network_v2"
ORACLE_PATH = DIAGNOSTIC_DATA_DIR / "reachability_graph_oracle_20261022_oracle.parquet"
VENUES_PATH = DIAGNOSTIC_DATA_DIR / "reachability_venue_compare_20261022_venues.csv"
FROZEN_JAR_PATH = PROJECT_ROOT / "outputs" / "r5_patches" / "r5-v7.5.1-r5py-all_transit_r5_patch_connector_p2.jar"
FROZEN_JAR_SHA256 = "62a8f6c1afa2e0a0c86860e336da499f9344e46e6c6d259d9c4824d129e68eb3"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"
VENUES_WITH_HEX_PATH = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT / f"venues_with_hex_ven20260925_{SUBJECT}.csv"
ROUTES_DIR = DIAGNOSTIC_DATA_DIR / f"{NAME}_routes_20261023"   # one parquet per departure (routed 2026-10-23; reused, never overwritten)

# --- transit (frozen model, TRN-16) ----------------------------------------------------------------
RELEASE = "20261016"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
R5_MAX_MEMORY = "7G"
SPEED_KMH = 4.143
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
ROUTE_MAX_MIN = 21                              # band 2 needs <= 1,229 s
BAND_CUTS_S = {"band1": 629, "band2": 1229}     # SCR-10 rounding
GUARD_CLASSES = ["com.conveyal.r5.profile.FastRaptorWorker", "com.conveyal.r5.streets.StreetRouter",
                 "com.conveyal.r5.streets.LinkedPointSet", "com.conveyal.r5.analyst.TravelTimeReducer"]

# --- origins ---------------------------------------------------------------------------------------
POPULATED_MIN_PERSONS = 1.0
ENVELOPE_MIN = 35                               # single-departure oracle, cut 30 + 5 min margin
ORIGINS_PER_VENUE = 500
SEED = 20261023
SECONDS_PER_MIN = 60

# --- departures ------------------------------------------------------------------------------------
SLOT_MIN = 30
STEP_MIN = 5
DEPARTURES_PER_SLOT = SLOT_MIN // STEP_MIN
DAY_WINDOWS = {                                 # day: (date, [(first slot start, last slot end)]), subject's hours
    "Wed": (datetime.date(2026, 10, 28), [(datetime.time(17, 30), datetime.time(21, 0))]),
    "Sat": (datetime.date(2026, 10, 31), [(datetime.time(12, 30), datetime.time(15, 0)),
                                          (datetime.time(17, 0), datetime.time(21, 30))]),
    "Fri": (datetime.date(2026, 10, 30), [(datetime.time(17, 30), datetime.time(21, 30))]),
    "Sun": (datetime.date(2026, 11, 1), [(datetime.time(12, 30), datetime.time(15, 0)),
                                         (datetime.time(17, 0), datetime.time(21, 0))]),
}
TIMING_DEPARTURE = datetime.datetime(2026, 10, 28, 18, 0)
TIMING_ORIGINS = 1000


def run_date():
    return datetime.date.today().strftime("%Y%m%d")


def check_jar():
    with open(FROZEN_JAR_PATH, "rb") as file:
        assert hashlib.file_digest(file, "sha256").hexdigest() == FROZEN_JAR_SHA256, "not the frozen jar"


def network_paths():
    """(from transit_holdout_score.py)"""
    feed_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{RELEASE}"
    pbf_path = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{RELEASE}.osm.pbf"
    gtfs = [feed_dir / (f"{name}_{V2_NAME}_{RELEASE}_moved.zip" if name == TRAIN_FEED else f"{name}_{V2_NAME}_{RELEASE}.zip")
            for name in FEED_NAMES]
    return pbf_path, gtfs


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (from transit_holdout_score.py)."""
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


def hex_table():
    import pyogrio
    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False,
                                    columns=["hex_id", "centroid_lat", "centroid_lon", "residents", "workers"])
    hex_df["persons"] = hex_df.residents.fillna(0) + hex_df.workers.fillna(0)
    return hex_df


def venue_hex_ids():
    venues_df = pd.read_csv(VENUES_WITH_HEX_PATH, usecols=["place_id", "hex_id"]).dropna(subset=["hex_id"])
    return venues_df.hex_id.astype(np.int64)


def study_venues():
    return pd.read_csv(VENUES_PATH)[["label", "hex_id"]]


def origin_sample(hex_df):
    """Per study venue: envelope size N_v and its seeded sample; returns (sample rows, envelope sizes)."""
    oracle_df = pd.read_parquet(ORACLE_PATH)
    populated = set(hex_df.hex_id[hex_df.persons >= POPULATED_MIN_PERSONS])
    inside_df = oracle_df[oracle_df.oracle_s <= ENVELOPE_MIN * SECONDS_PER_MIN]
    rng = np.random.default_rng(SEED)
    rows, sizes = [], {}
    for venue in study_venues().itertuples():
        envelope = np.array(sorted(set(inside_df.hex_id[inside_df.venue_hex == venue.hex_id]) & populated))
        sizes[venue.hex_id] = len(envelope)
        picked = envelope if len(envelope) <= ORIGINS_PER_VENUE else rng.choice(envelope, ORIGINS_PER_VENUE, replace=False)
        rows += [{"venue_hex": venue.hex_id, "hex_id": int(h)} for h in picked]
    return pd.DataFrame(rows), sizes


def departures():
    """Every dense departure: day, slot start, departure datetime, seeded offset per slot."""
    rng = np.random.default_rng(SEED)
    rows = []
    for day, (date, windows) in DAY_WINDOWS.items():
        for first, last in windows:
            start = datetime.datetime.combine(date, first)
            end = datetime.datetime.combine(date, last)
            while start < end:
                offset = int(rng.integers(STEP_MIN))
                for j in range(DEPARTURES_PER_SLOT):
                    rows.append({"day": day, "slot": start.strftime("%H:%M"),
                                 "departure": start + datetime.timedelta(minutes=offset + j * STEP_MIN)})
                start += datetime.timedelta(minutes=SLOT_MIN)
    return pd.DataFrame(rows)


def open_network():
    check_jar()
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(FROZEN_JAR_PATH)]   # r5py reads these at import
    import jpype
    from r5py import TransportNetwork
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    for name in GUARD_CLASSES:
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == FROZEN_JAR_PATH.resolve(), f"{name} loaded from {location}"
    pbf_path, gtfs = network_paths()
    check_working_copies([pbf_path] + gtfs)
    network = TransportNetwork(pbf_path, gtfs)
    for date, _ in DAY_WINDOWS.values():
        assert network.transit_layer.covers(date), f"release does not cover {date}"
    return network


def points(df):
    import geopandas as gpd
    return gpd.GeoDataFrame({"id": df.hex_id.to_numpy()}, crs="EPSG:4326",
                            geometry=gpd.points_from_xy(df.centroid_lon, df.centroid_lat))


def route(network, origins_gdf, destinations_gdf, departure):
    from r5py import TransportMode, TravelTimeMatrix
    matrix_df = pd.DataFrame(TravelTimeMatrix(
        network, origins=origins_gdf, destinations=destinations_gdf, departure=departure,
        departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=datetime.timedelta(minutes=ROUTE_MAX_MIN),
        speed_walking=SPEED_KMH))
    matrix_df = matrix_df.dropna(subset=[f"travel_time_p{SINGLE_PERCENTILE}"])
    return pd.DataFrame({"from_id": matrix_df.from_id.astype("int32"), "to_id": matrix_df.to_id.astype("int32"),
                         "travel_time_s": matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].astype("int32")})


def run_timing():
    hex_df = hex_table()
    sample_df, sizes = origin_sample(hex_df)
    union = sample_df.hex_id.unique()
    print(f"envelopes (oracle <= {ENVELOPE_MIN} min, populated): {sizes}; sample union {len(union):,} origins", flush=True)
    tick = time.perf_counter()
    network = open_network()
    print(f"network load {time.perf_counter() - tick:.0f} s", flush=True)
    destinations_gdf = points(hex_df[hex_df.hex_id.isin(venue_hex_ids().unique())])
    rng = np.random.default_rng(SEED)
    timing_ids = rng.choice(union, min(TIMING_ORIGINS, len(union)), replace=False)
    origins_gdf = points(hex_df[hex_df.hex_id.isin(timing_ids)])
    for minutes in (0, 7):
        tick = time.perf_counter()
        rows_df = route(network, origins_gdf, destinations_gdf, TIMING_DEPARTURE + datetime.timedelta(minutes=minutes))
        wall_s = time.perf_counter() - tick
        print(f"departure +{minutes} min: {len(origins_gdf)} origins -> {len(destinations_gdf):,} venue hexes, "
              f"{wall_s:.0f} s ({wall_s / len(origins_gdf):.3f} s per origin), rows {len(rows_df):,}; "
              f"union of {len(union):,} at this rate {wall_s / len(origins_gdf) * len(union) / 60:.1f} min per departure",
              flush=True)


def run_route():
    hex_df = hex_table()
    sample_df, sizes = origin_sample(hex_df)
    ROUTES_DIR.mkdir(exist_ok=True)
    sample_df.to_csv(ROUTES_DIR / "origin_sample.csv", index=False)
    pd.Series(sizes, name="envelope_hexes").rename_axis("venue_hex").to_csv(ROUTES_DIR / "envelope_sizes.csv")
    plan_df = departures()
    plan_df.to_csv(ROUTES_DIR / "departures.csv", index=False)
    union = sample_df.hex_id.unique()
    network = open_network()
    destinations_gdf = points(hex_df[hex_df.hex_id.isin(venue_hex_ids().unique())])
    origins_gdf = points(hex_df[hex_df.hex_id.isin(union)])
    print(f"{NAME} route {run_date()}: {len(origins_gdf):,} origins, {len(destinations_gdf):,} destinations, "
          f"{len(plan_df)} departures", flush=True)
    for row in plan_df.itertuples():
        path = ROUTES_DIR / f"{row.departure:%Y%m%d_%H%M}.parquet"
        if path.exists():
            continue
        tick = time.perf_counter()
        rows_df = route(network, origins_gdf, destinations_gdf, row.departure)
        partial = path.with_suffix(".partial")
        rows_df.to_parquet(partial, index=False)
        partial.rename(path)
        print(f"{datetime.datetime.now():%H:%M:%S} {row.day} {row.departure:%Y-%m-%d %H:%M}: {len(rows_df):,} rows, "
              f"{time.perf_counter() - tick:.0f} s", flush=True)
    print("route done", flush=True)


def departure_elements(rows_df, cut_s, sample_df, venue_counts):
    """One departure's nonzero x values per study venue, long: venue_hex, element, hex_id, x.

    Elements: "persons" (x = 1 if h reaches v), "flat_share" (x = 1 / K_h), "c<v'>" (x = 1 if h reaches v and v')."""
    reach_df = rows_df[rows_df.travel_time_s <= cut_s]
    competitors_k = reach_df.to_id.map(venue_counts).fillna(0).groupby(reach_df.from_id).sum()
    parts = []
    for venue_hex, members in sample_df.groupby("venue_hex").hex_id:
        reached = reach_df.from_id[(reach_df.to_id == venue_hex) & reach_df.from_id.isin(members)].unique()
        if len(reached) == 0:
            continue
        parts.append(pd.DataFrame({"venue_hex": venue_hex, "element": "persons", "hex_id": reached, "x": 1.0}))
        parts.append(pd.DataFrame({"venue_hex": venue_hex, "element": "flat_share", "hex_id": reached,
                                   "x": 1.0 / competitors_k.reindex(reached).to_numpy()}))
        pairs_df = reach_df[reach_df.from_id.isin(reached) & (reach_df.to_id != venue_hex)]
        parts.append(pd.DataFrame({"venue_hex": venue_hex, "element": "c" + pairs_df.to_id.astype(str),
                                   "hex_id": pairs_df.from_id.to_numpy(), "x": 1.0}))
    return pd.concat(parts, ignore_index=True)


def slot_moments(elements_df, n_departures, persons, inclusion):
    """Per venue x element: slot mean mu, raw within-slot variance, subsampling-corrected variance (HT)."""
    elements_df = elements_df.assign(p=elements_df.hex_id.map(persons))
    elements_df["f"] = elements_df.venue_hex.map(inclusion)
    elements_df["x2"] = elements_df.x ** 2
    totals = (elements_df.assign(px=elements_df.p * elements_df.x / elements_df.f)
              .pivot_table(index=["venue_hex", "element"], columns="d", values="px", aggfunc="sum", fill_value=0.0)
              .reindex(columns=range(n_departures), fill_value=0.0))
    out_df = pd.DataFrame({"mu": totals.mean(axis=1), "var_raw": totals.var(axis=1, ddof=1)})
    per_hex = elements_df.groupby(["venue_hex", "element", "hex_id"]).agg(sx=("x", "sum"), sx2=("x2", "sum"),
                                                                          p=("p", "first"), f=("f", "first"))
    per_hex["var_h"] = (per_hex.sx2 - per_hex.sx ** 2 / n_departures) / (n_departures - 1)
    per_hex["term"] = (1 / per_hex.f ** 2 - 1 / per_hex.f) * per_hex.p ** 2 * per_hex.var_h
    out_df["var_corr"] = (out_df.var_raw - per_hex.term.groupby(["venue_hex", "element"]).sum()
                          .reindex(out_df.index, fill_value=0.0)).clip(lower=0.0)
    return out_df.reset_index()


def run_moments():
    """Slot moments for every day and band, from the saved routes (rerun freely; reads only)."""
    hex_df = hex_table()
    persons = hex_df.set_index("hex_id").persons
    sample_df = pd.read_csv(ROUTES_DIR / "origin_sample.csv")
    sizes = pd.read_csv(ROUTES_DIR / "envelope_sizes.csv", index_col="venue_hex").envelope_hexes
    inclusion = sample_df.groupby("venue_hex").size() / sizes
    venue_counts = venue_hex_ids().value_counts()
    plan_df = pd.read_csv(ROUTES_DIR / "departures.csv", parse_dates=["departure"])
    parts = []
    for (day, slot), slot_df in plan_df.groupby(["day", "slot"], sort=False):
        paths = [ROUTES_DIR / f"{departure:%Y%m%d_%H%M}.parquet" for departure in slot_df.departure]
        if not all(path.exists() for path in paths):
            continue
        routes = [pd.read_parquet(path) for path in paths]
        for band, cut_s in BAND_CUTS_S.items():
            elements_df = pd.concat([departure_elements(rows_df, cut_s, sample_df, venue_counts).assign(d=d)
                                     for d, rows_df in enumerate(routes)], ignore_index=True)
            parts.append(slot_moments(elements_df, len(routes), persons, inclusion).assign(day=day, slot=slot, band=band))
        print(f"moments {day} {slot}", flush=True)
    moments_df = pd.concat(parts, ignore_index=True)
    moments_df.to_parquet(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_moments.parquet", index=False)
    return moments_df


SCHEME_K = [1, 2, 3, 6]
SCHEME_S = [1, 2, 3, 4]
SCALAR_ELEMENTS = ["persons", "flat_share"]
CLOSE_SCALAR = 0.02
CLOSE_VECTOR = 0.05
COMMON_DAYS = [("Wed", "Fri"), ("Sat", "Sun"), ("Wed", "Sat")]


def scheme_mse(group_df, k, s, variance):
    """MSE per element of a scheme's day headline (k departures per slot, every s-th slot, random phase)."""
    mu = group_df.pivot(index="element", columns="slot", values="mu").fillna(0.0)
    sigma2 = group_df.pivot(index="element", columns="slot", values=variance).fillna(0.0)
    n_slots = mu.shape[1]
    bias2, var_part = 0.0, 0.0
    phases = range(min(s, n_slots))
    for phase in phases:
        chosen = np.arange(phase, n_slots, s)
        weights = -np.full(n_slots, 1 / n_slots)
        weights[chosen] += 1 / len(chosen)
        bias2 = bias2 + ((mu.to_numpy() @ weights) ** 2 - sigma2.to_numpy() @ weights ** 2 / DEPARTURES_PER_SLOT)
        var_part = var_part + sigma2.to_numpy()[:, chosen].sum(axis=1) / len(chosen) ** 2 / k
    bias2 = np.clip(bias2 / len(phases), 0, None)
    return pd.Series(bias2 + var_part / len(phases), index=mu.index), mu.mean(axis=1), n_slots


DAYS_PER_TYPE = {"Wed": 4, "Fri": 1, "Sat": 1, "Sun": 1}   # Wed stands for Mon-Thu (one date per day type, Q25)
WEEK_BUDGETS = [42, 84, 126, 252]                           # departures per week, one date per day type
R_BAR_VENUES = 60                                           # Q26 sample size


def week_lines(moments_df, labels):
    """Week headline (equal weight per open slot, Mon-Thu x 4): uniform k vs Neyman allocation over day types;
    R-bar error over a venue sample; noise against the spread between venues."""
    band2_df = moments_df[(moments_df.band == "band2") & moments_df.element.isin(SCALAR_ELEMENTS)]
    days = [day for day in DAYS_PER_TYPE if day in set(band2_df.day)]
    if len(days) < 2:
        return []
    lines = ["", f"week headline (band2; day types {days}, Mon-Thu weight 4; slot skipping not used): relative RMS error "
                 "persons / flat share at a weekly departure budget; uniform k per slot vs Neyman allocation by day type"]
    headlines = {}
    for venue_hex, venue_df in band2_df.groupby("venue_hex"):
        cells = []
        for element in SCALAR_ELEMENTS:
            element_df = venue_df[venue_df.element == element]
            slots = element_df.groupby("day").size().reindex(days)
            weight = pd.Series(DAYS_PER_TYPE).reindex(days)
            total_weight = float((weight * slots).sum())
            headline = float((element_df.groupby("day").mu.sum().reindex(days) * weight).sum() / total_weight)
            headlines[(venue_hex, element)] = headline
            a = (weight / total_weight) ** 2 * element_df.groupby("day").var_corr.sum().reindex(days)
            per_budget = []
            for budget in WEEK_BUDGETS:
                uniform_k = budget / slots.sum()
                uniform = np.sqrt((a / uniform_k).sum()) / headline
                k = np.sqrt(a / slots)
                k = k * budget / float((k * slots).sum()) if k.sum() > 0 else pd.Series(uniform_k, index=days)
                k = k.clip(lower=1e-9)
                neyman = np.sqrt((a / k).sum()) / headline
                per_budget.append(f"{100 * uniform:.1f}/{100 * neyman:.1f}")
            cells.append(element + " " + " ".join(per_budget))
        lines.append(f"  {labels[venue_hex]}: " + "; ".join(cells))
    lines.append(f"  budgets {WEEK_BUDGETS} departures per week (uniform/neyman); weekly slots "
                 f"{int(band2_df[band2_df.element == 'persons'].groupby('day').slot.nunique().reindex(days).sum())}")

    lines += ["", f"R-bar and venue percentiles (band2, persons): week headline error at 1 departure per slot, the mean "
                  f"over {R_BAR_VENUES} venues (independent noise), and noise variance / spread of headlines across "
                  f"the 8 venues (log scale)"]
    persons_df = band2_df[band2_df.element == "persons"]
    errors, values = [], []
    for venue_hex, venue_df in persons_df.groupby("venue_hex"):
        slots = venue_df.groupby("day").size().reindex(days)
        weight = pd.Series(DAYS_PER_TYPE).reindex(days)
        total_weight = float((weight * slots).sum())
        variance = float(((weight / total_weight) ** 2 * venue_df.groupby("day").var_corr.sum().reindex(days)).sum())
        headline = headlines[(venue_hex, "persons")]
        if headline > 0:
            errors.append(np.sqrt(variance) / headline)
            values.append(headline)
    relative = np.array(errors)
    lines.append(f"  per-venue relative error median {100 * np.median(relative):.1f}%, max {100 * relative.max():.1f}%; "
                 f"R-bar over {R_BAR_VENUES} venues ~{100 * np.sqrt(np.mean(relative ** 2) / R_BAR_VENUES):.1f}%; "
                 f"noise / spread on log scale {np.mean(relative ** 2) / np.var(np.log(values), ddof=1):.4f}")
    return lines


SPAN_SPLITS = {"Sat": "20:30"}                 # Sat dinner split: later slots form "Sat late" (Claude's, from resemblance)
LUNCH_END = "16:00"
SPAN_BUDGETS_PER_VENUE = [4, 7, 8, 12, 16, 24]


def span_of(day, slot):
    """Claude's spans (80th, after the resemblance read-out): weekday evening; weekend lunch / dinner; Sat late."""
    if DAYS_PER_TYPE[day] > 1 or day == "Fri":
        return f"{day} evening"
    if slot < LUNCH_END:
        return f"{day} lunch"
    if day in SPAN_SPLITS and slot >= SPAN_SPLITS[day]:
        return f"{day} late"
    return f"{day} dinner"


def span_variances(venue_df):
    """Per span: weight^2-scaled variance of one random departure across the span (within + between-slot), and the
    one-per-slot variance of the week headline; returns (a per span, previous variance, headline)."""
    weight = venue_df.day.map(DAYS_PER_TYPE)
    total_weight = float(weight.sum())
    headline = float((weight * venue_df.mu).sum() / total_weight)
    previous = float(((weight / total_weight) ** 2 * venue_df.var_corr).sum())
    a = {}
    for span, span_df in venue_df.assign(w=weight).groupby(venue_df.apply(lambda r: span_of(r.day, r.slot), axis=1)):
        n = len(span_df)
        tau2 = max(span_df.mu.var(ddof=0) - span_df.var_corr.mean() / DEPARTURES_PER_SLOT * (n - 1) / n, 0.0) if n > 1 else 0.0
        a[span] = (span_df.w.iloc[0] * n / total_weight) ** 2 * (span_df.var_corr.mean() + tau2)
    return pd.Series(a), previous, headline


def span_error(a, headline, budget):
    """Week headline relative RMS error with `budget` departures Neyman-allocated over spans (>= 1 per span)."""
    root = np.sqrt(a)
    departures = np.maximum(1, np.round(root / root.sum() * budget)) if root.sum() > 0 else pd.Series(1, index=a.index)
    return float(np.sqrt((a / departures).sum()) / headline), int(departures.sum())


def span_lines(moments_df, labels):
    """Span scheme vs one departure per slot (Q25 plan): departures needed for equal error; R-bar by budget."""
    band2_df = moments_df[(moments_df.band == "band2") & moments_df.element.isin(SCALAR_ELEMENTS)]
    days = [day for day in DAYS_PER_TYPE if day in set(band2_df.day)]
    lines = ["", f"span scheme (band2, week headline; days {days}; spans {sorted({span_of(d, s) for d, s in zip(band2_df.day, band2_df.slot)})}): "
                 "departures for the error of one departure per slot, Neyman over spans, >= 1 per span"]
    errors = {budget: [] for budget in SPAN_BUDGETS_PER_VENUE}
    previous_errors = []
    for (venue_hex, element), venue_df in band2_df.groupby(["venue_hex", "element"]):
        a, previous, headline = span_variances(venue_df)
        if headline <= 0 or previous <= 0:
            continue
        target = np.sqrt(previous) / headline
        needed = next((used for budget in range(len(a), 400) for error, used in [span_error(a, headline, budget)]
                       if error <= target), None)
        lines.append(f"  {labels[venue_hex]} {element}: one per slot {len(venue_df)} departures, error {100 * target:.1f}%; "
                     f"spans need {needed}")
        if element == "persons":
            previous_errors.append(target)
            for budget in SPAN_BUDGETS_PER_VENUE:
                errors[budget].append(span_error(a, headline, budget)[0])
    lines.append(f"  R-bar over {R_BAR_VENUES} venues (persons, independent noise): one per slot "
                 f"{100 * np.sqrt(np.mean(np.square(previous_errors)) / R_BAR_VENUES):.2f}%; spans "
                 + ", ".join(f"{budget} -> {100 * np.sqrt(np.mean(np.square(e)) / R_BAR_VENUES):.2f}%"
                             for budget, e in errors.items()))
    return lines


def resemblance_lines(labels):
    """Slot resemblance (band2 persons): distance between two slots' mean reach maps (3 departures each, alternate
    halves), over the mean of their within-slot half-vs-half distances; 1.0 = as alike as a slot with itself."""
    hex_df = hex_table()
    persons = hex_df.set_index("hex_id").persons
    sample_df = pd.read_csv(ROUTES_DIR / "origin_sample.csv")
    plan_df = pd.read_csv(ROUTES_DIR / "departures.csv", parse_dates=["departure"])
    cut_s = BAND_CUTS_S["band2"]
    reached = {}
    for departure in plan_df.departure:
        rows_df = pd.read_parquet(ROUTES_DIR / f"{departure:%Y%m%d_%H%M}.parquet")
        reached[departure] = rows_df[(rows_df.travel_time_s <= cut_s) & rows_df.to_id.isin(labels.index)]
    keys = list(plan_df.groupby(["day", "slot"], sort=False).groups)

    def distance(x, y):
        total = (x.sum() + y.sum()) / 2
        return np.abs(x - y).sum() / total if total > 0 else np.nan

    lines = ["", "slot resemblance (band2 persons): pair distance / noise floor; median over pairs, adjacent slots, same "
                 "clock on another day; the three most distinct slots (mean ratio, total vs mean)"]
    for venue_hex in labels.index:
        members = sample_df.hex_id[sample_df.venue_hex == venue_hex].to_numpy()
        weights = persons.reindex(members).to_numpy()
        halves = {}
        for day, slot in keys:
            departures = plan_df.departure[(plan_df.day == day) & (plan_df.slot == slot)].tolist()
            matrix = np.array([np.isin(members, reached[d].from_id[reached[d].to_id == venue_hex]) for d in departures],
                              float) * weights
            halves[(day, slot)] = (matrix[0::2].mean(axis=0), matrix[1::2].mean(axis=0))
        floors = {key: distance(*halves[key]) for key in keys}
        if not np.nanmean(list(floors.values())) > 0:
            lines.append(f"  {labels[venue_hex]}: no departure noise (every slot identical)")
            continue
        n = len(keys)
        ratio = np.full((n, n), np.nan)
        for i, a in enumerate(keys):
            for j, b in enumerate(keys):
                floor = (floors[a] + floors[b]) / 2
                if i != j and floor > 0:
                    ratio[i, j] = (distance(halves[a][0], halves[b][1]) + distance(halves[a][1], halves[b][0])) / 2 / floor
        adjacent = [ratio[i, i + 1] for i in range(n - 1) if keys[i][0] == keys[i + 1][0]]
        same_clock = [ratio[i, j] for i in range(n) for j in range(i + 1, n) if keys[i][0] != keys[j][0] and keys[i][1] == keys[j][1]]
        row_mean = np.nanmean(ratio, axis=1)
        totals = np.array([(halves[k][0].sum() + halves[k][1].sum()) / 2 for k in keys])
        totals = totals / totals.mean()
        distinct = ", ".join(f"{keys[i][0]} {keys[i][1]} {row_mean[i]:.2f} ({totals[i]:.2f})" for i in np.argsort(-row_mean)[:3])
        lines.append(f"  {labels[venue_hex]}: floor {np.nanmean(list(floors.values())):.2f}; median {np.nanmedian(ratio):.2f} "
                     f"(p90 {np.nanpercentile(ratio, 90):.2f}); adjacent {np.nanmedian(adjacent):.2f}; same clock "
                     f"{np.nanmedian(same_clock):.2f}; most distinct {distinct}")
    return lines


def run_analyse():
    moments_df = run_moments()                  # recomputed each run: routes may still be arriving
    labels = study_venues().set_index("hex_id").label
    rows = []
    for (band, day, venue_hex), group_df in moments_df.groupby(["band", "day", "venue_hex"]):
        for variance in ("var_corr", "var_raw"):
            for k in SCHEME_K:
                for s in SCHEME_S:
                    mse, headline, n_slots = scheme_mse(group_df, k, s, variance)
                    is_vector = mse.index.str.startswith("c")
                    record = {"band": band, "day": day, "venue": labels[venue_hex], "variance": variance, "k": k, "s": s,
                              "departures": k * int(np.ceil(n_slots / s)), "slots": n_slots,
                              "competitors_l2": float(np.sqrt(mse[is_vector].sum()) / np.sqrt((headline[is_vector] ** 2).sum()))}
                    for element in SCALAR_ELEMENTS:
                        record[element] = float(np.sqrt(mse.get(element, 0.0)) / headline.get(element, np.nan))
                        record[f"{element}_headline"] = float(headline.get(element, np.nan))
                    rows.append(record)
    schemes_df = pd.DataFrame(rows)
    prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}"
    schemes_df.to_csv(f"{prefix}_schemes.csv", index=False)

    lines = [f"{NAME} analyse {run_date()}: days {sorted(moments_df.day.unique())}; relative RMS error of the day headline "
             f"vs infinitely many departures (corrected for origin subsampling; raw in the csv)"]
    corrected_df = schemes_df[schemes_df.variance == "var_corr"]
    for band in BAND_CUTS_S:
        band_df = corrected_df[corrected_df.band == band]
        lines += ["", f"[{band}] worst venue per day, persons / flat share / competitors L2 (%); departures per day"]
        for (k, s), scheme_df in band_df.groupby(["k", "s"]):
            cells = [f"{day} {100 * g.persons.max():.1f}/{100 * g.flat_share.max():.1f}/{100 * g.competitors_l2.max():.1f} "
                     f"({g.departures.iloc[0]})" for day, g in scheme_df.groupby("day")]
            is_close = ((scheme_df.persons <= CLOSE_SCALAR) & (scheme_df.flat_share <= CLOSE_SCALAR)
                        & (scheme_df.competitors_l2 <= CLOSE_VECTOR)).all()
            lines.append(f"  k={k} s={s}: " + "; ".join(cells) + ("  CLOSE" if is_close else ""))

    persons_df = moments_df[(moments_df.element == "persons")]
    lines += ["", "within-slot vs between-slot (band2, persons): sqrt(mean sigma^2) / headline, sd of slot means / headline"]
    for (day, venue_hex), g in persons_df[persons_df.band == "band2"].groupby(["day", "venue_hex"]):
        headline = g.mu.mean()
        lines.append(f"  {day} {labels[venue_hex]}: within {100 * np.sqrt(g.var_corr.mean()) / headline:.1f}% "
                     f"(raw {100 * np.sqrt(g.var_raw.mean()) / headline:.1f}%), between {100 * g.mu.std(ddof=1) / headline:.1f}%")

    lines += ["", "per-slot readings (SCR-13 reports slots too), band2: median over slots of relative RMS error at k "
                  f"departures per slot, persons / flat share, by venue and day; k = {SCHEME_K}"]
    band2_df = moments_df[(moments_df.band == "band2") & moments_df.element.isin(SCALAR_ELEMENTS)]
    for (day, venue_hex), g in band2_df.groupby(["day", "venue_hex"]):
        cells = []
        for k in SCHEME_K:
            relative = np.sqrt(g.var_corr / k) / g.mu
            cells.append("/".join(f"{100 * relative[g.element == element].median():.1f}" for element in SCALAR_ELEMENTS))
        lines.append(f"  {day} {labels[venue_hex]}: " + "  ".join(cells))

    lines += ["", "day types on common slots (band2): relative difference of the mean, z = difference / SE"]
    for first, second in COMMON_DAYS:
        for element in SCALAR_ELEMENTS:
            band_df = moments_df[(moments_df.band == "band2") & (moments_df.element == element)]
            a_df, b_df = band_df[band_df.day == first], band_df[band_df.day == second]
            if a_df.empty or b_df.empty:
                continue
            for venue_hex in a_df.venue_hex.unique():
                joined = a_df[a_df.venue_hex == venue_hex].merge(b_df[b_df.venue_hex == venue_hex], on="slot", suffixes=("_a", "_b"))
                difference = joined.mu_b.mean() - joined.mu_a.mean()
                se = np.sqrt((joined.var_corr_a.sum() + joined.var_corr_b.sum()) / DEPARTURES_PER_SLOT) / len(joined)
                slot_z = (joined.mu_b - joined.mu_a) / np.sqrt((joined.var_corr_a + joined.var_corr_b) / DEPARTURES_PER_SLOT)
                lines.append(f"  {second} vs {first} {element} {labels[venue_hex]}: {100 * difference / joined.mu_a.mean():+.1f}% "
                             f"(z {difference / se:+.1f}; slots |z| > 2: {(slot_z.abs() > 2).sum()} of {len(joined)})")
    lines += week_lines(moments_df, labels)
    lines += span_lines(moments_df, labels)
    lines += resemblance_lines(labels)
    summary = "\n".join(lines)
    Path(f"{prefix}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


WINDOW_DIR = DIAGNOSTIC_DATA_DIR / f"{NAME}_windows_20261023"  # one parquet per slot (routed 2026-10-23; reused, never overwritten)
WINDOW_DAY = "Wed"
WINDOW_PERCENTILES = [10, 30, 50, 70, 90]                 # R5's maximum of 5 (AnalysisWorkerTask.MAX_PERCENTILES)
WINDOW_FRACTIONS = [0.2, 0.4, 0.6, 0.8, 0.95]             # reach fraction read when percentile i is the highest <= cut
                                                          # (bin midpoints; none <= cut reads 0)


def run_window():
    """Each WINDOW_DAY slot as one 30-min window (R5 range RAPTOR, every minute) with 5 percentiles; then the expected
    band-2 catchment per slot vs the dense 6-departure mean. Evidence on Q25's 'window percentiles not pursued'."""
    hex_df = hex_table()
    sample_df = pd.read_csv(ROUTES_DIR / "origin_sample.csv")
    plan_df = pd.read_csv(ROUTES_DIR / "departures.csv", parse_dates=["departure"])
    slots = plan_df[plan_df.day == WINDOW_DAY].slot.unique()
    date = DAY_WINDOWS[WINDOW_DAY][0]
    network = open_network()
    from r5py import TransportMode, TravelTimeMatrix   # after open_network: the frozen jar must load first
    destinations_gdf = points(hex_df[hex_df.hex_id.isin(venue_hex_ids().unique())])
    origins_gdf = points(hex_df[hex_df.hex_id.isin(sample_df.hex_id.unique())])
    WINDOW_DIR.mkdir(exist_ok=True)
    columns = [f"travel_time_p{p}" for p in WINDOW_PERCENTILES]
    for slot in slots:
        path = WINDOW_DIR / f"{date:%Y%m%d}_{slot.replace(':', '')}.parquet"
        if path.exists():
            continue
        start = datetime.datetime.combine(date, datetime.time.fromisoformat(slot))
        tick = time.perf_counter()
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins_gdf, destinations=destinations_gdf, departure=start,
            departure_time_window=datetime.timedelta(minutes=SLOT_MIN), percentiles=WINDOW_PERCENTILES,
            transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=datetime.timedelta(minutes=ROUTE_MAX_MIN),
            speed_walking=SPEED_KMH)).dropna(subset=columns, how="all")
        matrix_df[["from_id", "to_id"]] = matrix_df[["from_id", "to_id"]].astype("int32")
        matrix_df.to_parquet(path, index=False)
        print(f"{datetime.datetime.now():%H:%M:%S} window {WINDOW_DAY} {slot}: {len(matrix_df):,} rows, "
              f"{time.perf_counter() - tick:.0f} s (one single departure ~130 s)", flush=True)
    compare_windows()


def compare_windows():
    hex_df = hex_table()
    persons = hex_df.set_index("hex_id").persons
    sample_df = pd.read_csv(ROUTES_DIR / "origin_sample.csv")
    sizes = pd.read_csv(ROUTES_DIR / "envelope_sizes.csv", index_col="venue_hex").envelope_hexes
    inclusion = sample_df.groupby("venue_hex").size() / sizes
    labels = study_venues().set_index("hex_id").label
    plan_df = pd.read_csv(ROUTES_DIR / "departures.csv", parse_dates=["departure"])
    date = DAY_WINDOWS[WINDOW_DAY][0]
    cut_s = BAND_CUTS_S["band2"]
    rows = []
    for slot, slot_df in plan_df[plan_df.day == WINDOW_DAY].groupby("slot"):
        window_df = pd.read_parquet(WINDOW_DIR / f"{date:%Y%m%d}_{slot.replace(':', '')}.parquet")
        fraction = pd.Series(0.0, index=window_df.index)
        for p, value in zip(WINDOW_PERCENTILES, WINDOW_FRACTIONS):
            fraction[window_df[f"travel_time_p{p}"] <= cut_s] = value
        median_in = window_df[f"travel_time_p{WINDOW_PERCENTILES[2]}"] <= cut_s
        dense = [pd.read_parquet(ROUTES_DIR / f"{d:%Y%m%d_%H%M}.parquet") for d in slot_df.departure]
        for venue_hex, members in sample_df.groupby("venue_hex").hex_id:
            scale = 1 / inclusion[venue_hex]
            is_pair = (window_df.to_id == venue_hex) & window_df.from_id.isin(members)
            weights = window_df.from_id[is_pair].map(persons) * scale
            dense_values = [float(df.from_id[(df.to_id == venue_hex) & df.from_id.isin(members) & (df.travel_time_s <= cut_s)]
                                  .map(persons).sum() * scale) for df in dense]
            rows.append({"slot": slot, "venue": labels[venue_hex], "window_expected": float((weights * fraction[is_pair]).sum()),
                         "window_median": float(weights[median_in[is_pair]].sum()), "dense_mean": np.mean(dense_values),
                         "dense_se": np.std(dense_values, ddof=1) / np.sqrt(len(dense_values))})
    compare_df = pd.DataFrame(rows)
    prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}"
    compare_df.to_csv(f"{prefix}_windows.csv", index=False)
    lines = [f"window vs dense ({WINDOW_DAY}, band2 persons): per venue, day sums; ratio window / dense; slots where "
             f"|window - dense| > 2 dense SE"]
    for venue, g in compare_df.groupby("venue"):
        if g.dense_mean.sum() == 0:
            continue
        lines.append(f"  {venue}: expected {g.window_expected.sum() / g.dense_mean.sum():.3f}, median-in "
                     f"{g.window_median.sum() / g.dense_mean.sum():.3f}; slots off "
                     f"{int(((g.window_expected - g.dense_mean).abs() > 2 * g.dense_se).sum())} of {len(g)}; day SD of "
                     f"slot values window {g.window_expected.std() / g.window_expected.mean():.3f} vs dense "
                     f"{g.dense_mean.std() / g.dense_mean.mean():.3f}")
    summary = "\n".join(lines)
    Path(f"{prefix}_windows_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    {"timing": run_timing, "route": run_route, "moments": run_moments, "analyse": run_analyse,
     "window": run_window, "compare_windows": compare_windows}[sys.argv[1]]()
