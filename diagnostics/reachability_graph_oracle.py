"""Graph oracle superset check: does RCH-26's two-layer graph oracle, cut at 30 + 10 min, hold every hex the frozen model
reaches a venue from within 30 min?

Claim under test (concepts/reachability.md RCH-26, RCH-21; DESIGN.md Q25): one reverse Dijkstra from a venue on a
two-layer graph (walk graph and stops, each twice: took_transit no / yes; ride edges for every stop pair (i, j) of a
trip, weighted by the shortest single-trip t_j - t_i over trips in the window, zeros kept; first ride 0 s, every ride
inside layer 1 + 200 s, the frozen model's transfer charge; waits 0) is never slower than the frozen model, so its set
{oracle <= ORACLE_CUT_MIN} holds every origin hex with frozen-model hex -> venue <= CAP_MIN. Where the pipeline would
rely on it: Stage A of the subject-scoped transit pass (RCH-21), replacing the venue -> hex oracle and RCH-22's margin.

Method (free: frozen transit model, no API):
  Graph (Claude's choice): R5's own street layer of the frozen network, read from the JVM (pedestrian-allowed edges,
    length / 4.143 km/h, no per-edge ceil), so walk-graph mismatch drops out and only the oracle's own assumptions are
    tested; stops sit on R5's street vertices (streetVertexForStop). Trips: R5's trip patterns, services active on the
    date; a ride (i, j) counts if the trip departs i at >= t and arrives at j by t + ORACLE_CUT_MIN; pickup / drop-off
    types ignored (generous). Points (hexes and venues) linked by R5's findSplit (WALK, 1,600 m): along-edge metres
    charged, the off-street link not (generous; R5 charges it, WLK-3).
  Venues: the 8 of reachability_venue_compare (saved list). Departures Wed 2026-10-28 12:00 and 18:30; Sat 2026-10-31
    13:00 report-only (as reachability_asymmetry.py).
  Hexes: populated (residents + workers >= 1) within DISC_KM of the venue.
  Truth: the frozen model (TRN-16 freeze record) hex -> venue, min(transit, walk), max time TRUTH_MAX_MIN. Routing all
    ~209k-332k disc hexes is ~2 h per departure, so truth is routed for (a) every hex with ORACLE_CUT_MIN < oracle <=
    BAND_MIN for some venue at that departure (a hex there fails only if the oracle overshoots truth by 10-15 min), and
    (b) a seeded random SAMPLE_SHARE of all disc hexes (gross failures, e.g. an unlinked stop; generosity rate; the
    disc-edge check; envelope sizes). "Every hex" holds in the band only; elsewhere, the sample. BAND_MIN was 55 in the
    first draft; cut to 45 after the oracle run showed the 40-55 band at ~138k hexes per departure (~1.2 h of R5
    each), before any truth was routed. Hexes inside the oracle set cannot fail and are routed only in the sample.
  Also: the 73rd's envelope (frozen-model venue -> hex <= ORACLE_CUT_MIN) on the same hexes, for envelope size.

Reading rule (written before the first run; Claude's, applying the user's rule "always generous"):
  FAIL = a routed hex with truth <= CAP_MIN and oracle > ORACLE_CUT_MIN (outside the set), weekday departures. The
  superset check holds if no hex fails, in (a) or (b). Every fail is listed hex by hex: venue, departure, km, truth,
  oracle, walk-only truth, oracle gap; cause read by hand. No tuning of the cut.
  Report only: generosity violations (oracle > truth among routed hexes with truth <= TRUTH_MAX_MIN; quantiles);
  disc edge (any sampled hex in the outer ring EDGE_RING_KM with truth <= CAP_MIN); envelope sizes (oracle set vs the
  73rd's venue -> hex set vs truth <= CAP_MIN, in hexes; the sampled part scaled by 1 / SAMPLE_SHARE); oracle runtime
  per venue per departure; GTFS rounding figures for RCH-26 (share of 0-s minimum hops by feed; summed per-hop minima
  over each trip's window span / its actual span, median by feed), recomputed here (open flag, 74th).

Conclusion (partial, 2026-10-22, 75th; facts): oracle mode run at cut 40 (3 departures): R5 street layer 1.44 M
vertices, 3.84 M walk edges, 23,557 stops (0 unlinked), 7 of 331,620 disc hexes unlinked; ~430k ride pairs per weekday
departure (350k Sat), build ~3 s, reverse search 0.1-0.3 s per venue, sets 2.1k-41k hexes per venue; 0-s minimum hop
bus 24-28%, tram 11-18%, train 0%; summed hop minima / span median 0.89-1.0. The truth run was stopped before saving
(user's redesign: staged caps; pass / fail by expected persons missed <= 1%, P from trip_uncertainty; cut <= 55; span
oracles by day type x 30-min slot; RCH-26). The rule above is superseded by the 76th's rule below.

Redesigned test (76th, 2026-10-22, autonomous; modes tightness, spans, superset_*; written before any truth was routed):
  Span oracle: one graph per day type (Mon-Thu, Fri, Sat, Sun; week of 2026-10-26) x 30-min slot; rides = fastest
    single trip departing i at >= slot start and arriving at j by slot end + cut, over every date of the day type, each
    date with the service day before (times past 24:00 shifted back a day) and after (shifted forward); whole network.
    Covers every departure minute in the slot. Rest as the 75th (walk graph, splits, 200 s transfer charge, waits 0).
  (a) tightness: subject and the 8 venues, Wed 2026-10-28: set size for a single departure vs 30-min slot vs 1 h / 2 h
    bins vs a day span (06-21) and a night single / slot / span (00-06), at cuts 40 and 55 (slot windows 70 / 85 min);
    ride pairs and in-memory parquet size per graph; truth routing speed (400 origins x 8 venues, max 45 and 60).
  (b) spans: all 4 x 48 graphs at cuts 40 / 55: ride pairs, parquet size, build time (sizes for RCH-26's storage line).
  (c) superset: slots Mon-Thu 07:30 (truth Tue), 12:00 (Wed), 19:30 (Mon), Fri 18:30 ruled; Sat 13:00, Sun 10:00,
    Mon-Thu 05:30 (Thu, night) report-only. Truth = frozen model hex -> venue, min(transit, walk), max 60 min, at 2
    seeded minutes inside the slot (departure noise). Truth set per slot: every hex with cut < oracle <= cut + 5 at the
    start cut (cap + 10) for each cap, plus the seeded 3% sample of the union disc; later cuts add their bands.
    Expected persons per (hex, venue): persons (residents + workers) x mean over the truth departures of
    P(Google <= cap | truth) (trip_uncertainty's logic, copied: K = 400 nearest fit pairs in log time; fit pairs =
    transit_holdout_score's scored seen + holdout pairs, as the 75th's T_eps figures; truth past 60 min: P = 0).
    Shelf line (Claude's, user to confirm): the first time >= cap where P <= 5%; a (hex, departure) with truth past it is
    the model-error shelf, before it the core. Estimates are stratified: band hexes weight 1, the rest 1 / 0.03.
  Reading rule (Claude's, not user-approved; staged, cap 20 then cap 30): per venue x ruled slot, core share =
    expected core persons outside the oracle set {oracle <= cut} / expected core persons in the disc. A cut passes if
    every venue x ruled slot has core share <= 1%; the verdict is the smallest passing cut from cap + 10 up, in 5-min
    steps, max 55 (user). If the start cut fails, the band past the next cut is routed before reading it (estimates
    below the start cut and for cuts whose band was not routed rest on the sample only; reported, not ruled). Report
    only: the shelf share (core + shelf missed over core + shelf), per-venue standard errors, every routed pair outside
    the cut-55 set with truth <= 55 at some departure (generosity violations, read by hand), departure noise, set sizes;
    night slot with the night and day groups (open: which group nights use); weekend slots (inclusion open, Q25).
  Band routing cut by cost (user and Claude, 76th, before results): truth first for the 3% sample only (~1 h; full
    bands ~40 min per departure, ~9.5 h); bands routed afterwards where the sample points, so "every hex" holds only
    for slots and cuts whose band was routed (the cuts file says which). Padded bins (user's question, report only):
    the same test with the window padded 30 / 45 min on both sides of the slot (`pad N`; 45 = a centred 2 h bin) and
    the clock hour holding the slot (`clock`), same truth; cost read as set size.

Conclusion (76th, 2026-10-22; facts, sample truth only; the full band for Mon-Thu 12:00 was in flight at close):
  (a) Wed, 8 venues summed, cut 40: single departure 152.1k hexes, 30-min slot 154.4k (+1.5%), 1 h 155.2k, 2 h 156.1k,
  day span 06-21 201.5k (+32%); weekday 02:00 has no service (night span 00-06 is its 05-07 tail). Ride edges 1.2-1.9
  MB per graph as parquet (not GBs); build 4-10 s. Truth speed 0.019 s per origin at max 45, 0.027 at 60 (8 venues).
  (c) Shelf line: cap 20 day 23.1 min (night 24.0), cap 30 day 31.9 (night 34.8). Generosity: oracle > truth on 0 of
  ~44k routed pairs with truth <= cut, every slot and cut (oracle / truth median 0.80-0.89). Rule (Claude's): cap 20
  cut 30, cap 30 cut 40 (the start cuts); core share 0 from cut 25 / 35 everywhere, weekend and night included; at
  cap 30 cut 25 / 30 the worst venue misses 31% / 3%. Core + shelf share at cap 30 cut 40: pooled ~0.3%, worst venue
  3.0% (day group); night slot with the night group up to 11% (cap 20, cut 30, one venue). Departure noise: 25-35% of
  pairs within the cap at one departure are not at the other in the same slot. Bins (same truth): clock hour +0.2 to
  +1.2% persons in the set (Mon-Thu 07:30 +8%), pad 30 +0.5 to +9%, pad 45 +0.7 to +13%, AM shoulder largest; no
  misses to remove (none in the plain slot).

Revision (78th, 2026-10-22, before the band result was read): the 77th's band report read unsaved oracle rows as
  outside the set. `band_ids` routes a hex in the band of ANY venue to ALL venues, but `superset_oracle` saved rows
  only for the sample and for the band of THAT venue, so the report's reindex made every (band hex, other venue) pair
  oracle = inf. Fix (exact, not a stratum restriction): `superset_oracle` also saves the oracle time of every
  (hex, venue) pair whose hex the saved truth routed for that slot, at every cut; the report is unchanged. The pre-fix
  oracle, summary, mass and violations files are kept with the suffix `_before_fix`. Expectation (not a rule): 0
  generosity violations, as on the sample. The padded and clock variants already saved every plain-kept hex at every
  venue, so only their reports are rerun.

Conclusion (78th, 2026-10-22; facts, after the fix): (c) with the full band for Mon-Thu 12:00 (cuts 30 / 40 routed)
  and the 3% sample elsewhere: rule (Claude's) cap 20 -> cut 30, cap 30 -> cut 40, as on the sample; core share 0 from
  cut 25 (cap 20) / 35 (cap 30) on every venue x slot; cap 30 worst venue at cut 25 / 30: 31% / 3.0%. Generosity at cut
  55: 0 routed pairs outside the set. Oracle > truth on 10 of 135k routed pairs with truth <= 55 in Mon-Thu 12:00
  (0 elsewhere; every cut), all walk-only hexes next to a venue (truth 63-217 s), oracle slower by 0.07-1.4 s, all inside the set:
  read as R5's whole-metre / whole-second rounding at the ends (P2's setOrigin floor), not a ride-graph defect; at
  minute cuts it changes no membership. Pooled core + shelf share at cap 30 cut 40: 0.3-0.4% day slots, 1.2% night
  slot with the night group. pad 30 / pad 45 / clock: same verdicts, 0 violations. (b) spans: 4 day types x 48 slots,
  ride pairs max 627.5k (cut 40) / 668.3k (cut 55), <= 1.76 MB parquet and < 0.9 s build per graph; all 192 graphs
  202 MB at cut 40, 217 MB at cut 55, per GTFS release; whole run 165 s.
----

Inputs (read only): reachability_venue_compare's venues, the hex nodes table, the frozen jar and v2 network.
Self-contained (CLAUDE.md D1). One JVM per process.
Usage: `python reachability_graph_oracle.py oracle`, `... truth`, `... report`.
"""
import datetime
import hashlib
import io
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
NAME = "reachability_graph_oracle"
VENUES_NAME = "reachability_venue_compare"
V2_NAME = "transit_pathway_network_v2"
FROZEN_JAR_PATH = PROJECT_ROOT / "outputs" / "r5_patches" / "r5-v7.5.1-r5py-all_transit_r5_patch_connector_p2.jar"
FROZEN_JAR_SHA256 = "62a8f6c1afa2e0a0c86860e336da499f9344e46e6c6d259d9c4824d129e68eb3"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"

# --- hexes -----------------------------------------------------------------------------------------
POPULATED_MIN_PERSONS = 1.0
DISC_KM = 25
EDGE_RING_KM = (20, 25)
EARTH_RADIUS_M = 6_371_000
SPLIT_RADIUS_M = 1600                          # as R5's LINK_RADIUS_METERS

# --- transit (frozen model, TRN-16) ----------------------------------------------------------------------
RELEASE = "20261016"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
R5_MAX_MEMORY = "7G"
SPEED_KMH = 4.143
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
DEPARTURES = {"Wed 12:00": datetime.datetime(2026, 10, 28, 12, 0), "Wed 18:30": datetime.datetime(2026, 10, 28, 18, 30),
              "Sat 13:00": datetime.datetime(2026, 10, 31, 13, 0)}
WEEKEND_LABELS = ["Sat 13:00"]
GUARD_CLASSES = ["com.conveyal.r5.profile.FastRaptorWorker", "com.conveyal.r5.streets.StreetRouter",
                 "com.conveyal.r5.streets.LinkedPointSet", "com.conveyal.r5.analyst.TravelTimeReducer"]

# --- oracle (RCH-26) ---------------------------------------------------------------------------------
TRANSFER_CHARGE_S = 200                        # every ride after the first (the frozen model's P3)
ORACLE_CUT_MIN = 40                            # 30 + 10 (user's start)
ORACLE_LIMIT_MIN = 60                          # Dijkstra limit; oracle times above it are not saved
ZERO_WEIGHT_S = 1e-3                           # stands in for 0 s (scipy reads stored zeros as no edge)
LAYERS = 2

# --- truth -------------------------------------------------------------------------------------------
CAP_MIN = 30
TRUTH_MAX_MIN = 45
BAND_MIN = 45                                  # every hex with ORACLE_CUT_MIN < oracle <= this is routed
SAMPLE_SHARE = 0.03                            # of the other disc hexes
WALK_ONLY_KM = 2.5                             # walk-only truth for hexes this close to a venue (30 min ~ 2.1 km)
SEED = 20261022
SECONDS_PER_MIN = 60
MM_PER_M = 1000

# --- span oracles (RCH-26, 75th decisions) -----------------------------------------------------------
DAY_S = 86_400
DAY_OFFSETS = (-1, 0, 1)                       # service days before / after whose trips can fall in a window
SLOT_MIN = 30                                  # one opening-hours slot (config HOURS_SLOT_MIN)
SLOTS_PER_DAY = 48
MAX_CUT_MIN = 55                               # user, 75th
DAY_TYPES = {"Mon-Thu": [datetime.date(2026, 10, 26) + datetime.timedelta(days=k) for k in range(4)],
             "Fri": [datetime.date(2026, 10, 30)], "Sat": [datetime.date(2026, 10, 31)], "Sun": [datetime.date(2026, 11, 1)]}
RIDE_DTYPES = {"i": "int32", "j": "int32", "s": "int32"}
TIGHTNESS_DATE = datetime.date(2026, 10, 28)   # a Wednesday
TIGHTNESS_WINDOWS = {                          # label: (window start, departure window length in min)
    "single 12:00": (datetime.time(12, 0), 0), "slot 12:00": (datetime.time(12, 0), SLOT_MIN),
    "bin 1 h 12:00": (datetime.time(12, 0), 60), "bin 2 h 12:00": (datetime.time(12, 0), 120),
    "day span 06-21": (datetime.time(6, 0), 15 * 60),
    "single 02:00": (datetime.time(2, 0), 0), "slot 02:00": (datetime.time(2, 0), SLOT_MIN),
    "night span 00-06": (datetime.time(0, 0), 6 * 60)}
TIGHTNESS_CUTS_MIN = [40, MAX_CUT_MIN]         # windows 70 and 85 min for a slot
TIMING_ORIGINS = 400
TIMING_DEPARTURE = datetime.datetime(2026, 10, 28, 12, 0)
SUPERSET_TRUTH_MAX_MIN = 60                    # R5 max time for the superset test's truth
SUPERSET_SLOTS = {                             # label: (day type, truth date, slot start, ruled)
    "Mon-Thu 07:30": ("Mon-Thu", datetime.date(2026, 10, 27), datetime.time(7, 30), True),
    "Mon-Thu 12:00": ("Mon-Thu", datetime.date(2026, 10, 28), datetime.time(12, 0), True),
    "Mon-Thu 19:30": ("Mon-Thu", datetime.date(2026, 10, 26), datetime.time(19, 30), True),
    "Fri 18:30": ("Fri", datetime.date(2026, 10, 30), datetime.time(18, 30), True),
    "Sat 13:00": ("Sat", datetime.date(2026, 10, 31), datetime.time(13, 0), False),
    "Sun 10:00": ("Sun", datetime.date(2026, 11, 1), datetime.time(10, 0), False),
    "Mon-Thu 05:30": ("Mon-Thu", datetime.date(2026, 10, 29), datetime.time(5, 30), False)}
SUPERSET_DEPARTURES = 2                        # truth departures per slot (seeded minutes inside it)
SUPERSET_CAPS_MIN = [20, 30]                   # staged: 20 first, then 30 (user, 75th)
SUPERSET_CUTS_MIN = [25, 30, 35, 40, 45, 50, MAX_CUT_MIN]
START_MARGIN_MIN = 10                          # start cut = cap + 10 (user's 30 + 10)
BAND_WIDTH_MIN = 5                             # every hex this far past a routed cut is routed
MISSED_SHARE = 0.01                            # expected persons missed, share (user, 75th)
SHELF_LEVEL = 0.05                             # shelf line (Claude's, user to confirm)
GRID_STEP_S = 6
CLOCK_HOUR_MIN = 60                            # clock-hour bin variant
PREDICTED_GRID_S = np.arange(0, SUPERSET_TRUTH_MAX_MIN * SECONDS_PER_MIN + GRID_STEP_S, GRID_STEP_S)
SCORE_NAME = "transit_holdout_score"
TRIP_ERROR_K_NEIGHBOURS = 400                  # copies of config's TRIP_ERROR_* (functions/trip_uncertainty.py)
TRIP_ERROR_MIN_MODEL_S = 30
TRIP_ERROR_NIGHT_END_MIN = 7 * 60
DAY_GROUP, NIGHT_GROUP = "day", "night"


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def newest(pattern):
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return saved[-1] if saved else None


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def disc_hexes():
    """Venues, populated disc hexes (union), and per venue the hex ids within DISC_KM with their km."""
    import pyogrio
    venues_df = pd.read_csv(newest(f"{VENUES_NAME}_2*_venues.csv"))
    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False,
                                    columns=["hex_id", "centroid_lat", "centroid_lon", "residents", "workers"])
    hex_df["persons"] = hex_df.residents.fillna(0) + hex_df.workers.fillna(0)
    hex_df = hex_df[hex_df.persons >= POPULATED_MIN_PERSONS].reset_index(drop=True)
    frames = []
    for venue in venues_df.itertuples():
        km = haversine_m(venue.centroid_lat, venue.centroid_lon, hex_df.centroid_lat.to_numpy(), hex_df.centroid_lon.to_numpy()) / 1000
        inside = km < DISC_KM
        frames.append(pd.DataFrame({"venue_hex": venue.hex_id, "hex_id": hex_df.hex_id.to_numpy()[inside], "km": km[inside]}))
    disc_df = pd.concat(frames, ignore_index=True)
    union_df = hex_df[hex_df.hex_id.isin(disc_df.hex_id)].reset_index(drop=True)
    return venues_df, union_df, disc_df


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


def frozen_network():
    """Start the JVM on the frozen jar (guarded) and build the v2 network (from reachability_asymmetry.py)."""
    with open(FROZEN_JAR_PATH, "rb") as file:
        assert hashlib.file_digest(file, "sha256").hexdigest() == FROZEN_JAR_SHA256, "not the frozen jar"
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(FROZEN_JAR_PATH)]   # r5py reads these at import
    import jpype
    from r5py import TransportNetwork
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    for name in GUARD_CLASSES:
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == FROZEN_JAR_PATH.resolve(), f"{name} loaded from {location}"
    pbf_path, gtfs = network_paths()
    check_working_copies([pbf_path] + gtfs)
    return TransportNetwork(pbf_path, gtfs), jpype


# --- oracle --------------------------------------------------------------------------------------------
def as_numpy(trove_list):
    return np.asarray(trove_list.toArray(), dtype=np.int64)


def walk_edges(street_layer, jpype):
    """Directed pedestrian edges of R5's street layer: (from, to, seconds), and the pair endpoints."""
    edge_store = street_layer.edgeStore
    assert edge_store.edgeTraversalTimes is None and (edge_store.costFields is None or edge_store.costFields.size() == 0)
    from_pair, to_pair = as_numpy(edge_store.fromVertices), as_numpy(edge_store.toVertices)
    lengths_mm, flags = as_numpy(edge_store.lengths_mm), as_numpy(edge_store.flags)
    assert len(flags) == 2 * len(from_pair)
    pedestrian = int(jpype.JClass("com.conveyal.r5.streets.EdgeStore$EdgeFlag").ALLOWS_PEDESTRIAN.flag)
    edge = np.arange(len(flags))
    pair = edge >> 1
    is_forward = edge % 2 == 0
    source = np.where(is_forward, from_pair[pair], to_pair[pair])
    target = np.where(is_forward, to_pair[pair], from_pair[pair])
    keep = (flags & pedestrian) != 0
    seconds = lengths_mm[pair] / MM_PER_M / (SPEED_KMH / 3.6)
    return source[keep], target[keep], seconds[keep], from_pair


def active_trips(transit_layer, date, jpype):
    """Per trip active on the date: (stop indices, arrivals, departures); frequency trips counted and skipped."""
    services = transit_layer.getActiveServicesForDate(jpype.JClass("java.time.LocalDate").of(date.year, date.month, date.day))
    is_active = np.array([bool(services.get(i)) for i in range(transit_layer.services.size())])
    trips, n_frequency = [], 0
    for pattern in transit_layer.tripPatterns:
        stops = np.asarray(pattern.stops, dtype=np.int64)
        for schedule in pattern.tripSchedules:
            if not is_active[schedule.serviceCode]:
                continue
            if schedule.headwaySeconds is not None:
                n_frequency += 1
                continue
            trips.append((stops, np.asarray(schedule.arrivals, dtype=np.int64), np.asarray(schedule.departures, dtype=np.int64)))
    return trips, n_frequency


def ride_edges(trips, start_s, end_s):
    """Min single-trip time per stop pair (i before j on a trip, departs i >= start, arrives j <= end)."""
    from_stop, to_stop, seconds = [], [], []
    for stops, arrivals, departures in trips:
        first = np.searchsorted(departures, start_s)              # departures are non-decreasing along a trip
        last = np.searchsorted(arrivals, end_s, side="right")     # stops < last arrive by end_s
        if last - first < 2:
            continue
        i, j = np.triu_indices(last - first, k=1)
        from_stop.append(stops[first + i])
        to_stop.append(stops[first + j])
        seconds.append(arrivals[first + j] - departures[first + i])
    if not seconds:                                               # no service in the window (weekday nights)
        return pd.DataFrame({"i": np.empty(0, np.int64), "j": np.empty(0, np.int64), "s": np.empty(0, np.int64)})
    rides_df = pd.DataFrame({"i": np.concatenate(from_stop), "j": np.concatenate(to_stop), "s": np.concatenate(seconds)})
    return rides_df.groupby(["i", "j"], as_index=False).s.min()


def rounding_figures(trips, start_s, end_s, feed_of_stop):
    """RCH-26's GTFS rounding figures on the window: 0-s minimum hop share, summed hop minima / actual span (median)."""
    hops = []
    for k, (stops, arrivals, departures) in enumerate(trips):
        first = np.searchsorted(departures, start_s)
        last = np.searchsorted(arrivals, end_s, side="right")
        if last - first < 2:
            continue
        idx = np.arange(first, last - 1)
        hops.append(pd.DataFrame({"trip": k, "i": stops[idx], "j": stops[idx + 1], "s": arrivals[idx + 1] - departures[idx],
                                  "span": arrivals[last - 1] - departures[first]}))
    hops_df = pd.concat(hops, ignore_index=True)
    hops_df["feed"] = feed_of_stop[hops_df.i.to_numpy()]
    hop_min = hops_df.groupby(["i", "j"]).s.min().rename("hop_min")
    hops_df = hops_df.join(hop_min, on=["i", "j"])
    pairs_df = hop_min.reset_index().assign(feed=lambda d: feed_of_stop[d.i.to_numpy()])
    zero_share = pairs_df.groupby("feed").hop_min.apply(lambda s: (s == 0).mean())
    per_trip = hops_df.groupby(["trip", "feed"]).agg(summed=("hop_min", "sum"), span=("span", "first")).reset_index()
    per_trip = per_trip[per_trip.span > 0]
    ratio = per_trip.assign(r=per_trip.summed / per_trip.span).groupby("feed").r.median()
    return pd.DataFrame({"zero_min_hop_share": zero_share, "summed_min_over_span_median": ratio})


def deduplicated(rows, cols, weights):
    """Keep the smallest weight per (row, col): csr_matrix would sum duplicates."""
    frame = pd.DataFrame({"r": rows, "c": cols, "w": np.maximum(weights, ZERO_WEIGHT_S)})
    frame = frame.groupby(["r", "c"], as_index=False).w.min()
    return frame.r.to_numpy(), frame.c.to_numpy(), frame.w.to_numpy()


def reverse_graph(walk, rides_df, stop_vertex, n_vertices):
    """CSR of the reversed two-layer graph (row = forward target), plus one empty last row for the venue super node."""
    from scipy.sparse import csr_matrix
    source, target, seconds = walk
    linked = (stop_vertex[rides_df.i.to_numpy()] >= 0) & (stop_vertex[rides_df.j.to_numpy()] >= 0)
    vi, vj = stop_vertex[rides_df.i.to_numpy()[linked]], stop_vertex[rides_df.j.to_numpy()[linked]]
    ride_s = rides_df.s.to_numpy()[linked].astype(float)
    n = n_vertices
    forward_from = np.concatenate([source, source + n, vi, vi + n])
    forward_to = np.concatenate([target, target + n, vj + n, vj + n])
    weight = np.concatenate([seconds, seconds, ride_s, ride_s + TRANSFER_CHARGE_S])
    rows, cols, data = deduplicated(forward_to, forward_from, weight)
    size = LAYERS * n + 1
    return csr_matrix((data, (rows, cols)), shape=(size, size))


def with_super_sources(graph, targets, offsets):
    """The graph with the super node's (last row) edges set to targets / offsets (seconds)."""
    from scipy.sparse import csr_matrix
    indptr = graph.indptr.copy()
    indptr[-1] += len(targets)
    return csr_matrix((np.concatenate([graph.data, np.maximum(offsets, ZERO_WEIGHT_S)]),
                       np.concatenate([graph.indices, targets]), indptr), shape=graph.shape)


def splits(street_layer, lats, lons, jpype):
    """R5's findSplit (WALK) per point: edge, vertex0, vertex1, along-edge metres to each (-1 / nan if unlinked)."""
    walk_mode = jpype.JClass("com.conveyal.r5.profile.StreetMode").WALK
    out = np.full((len(lats), 5), np.nan)
    for k, (lat, lon) in enumerate(zip(lats, lons)):
        split = street_layer.findSplit(float(lat), float(lon), float(SPLIT_RADIUS_M), walk_mode)
        if split is not None:
            out[k] = (split.edge, split.vertex0, split.vertex1, split.distance0_mm / MM_PER_M, split.distance1_mm / MM_PER_M)
    return pd.DataFrame(out, columns=["edge", "v0", "v1", "d0_m", "d1_m"])


def oracle_setup():
    """JVM, R5's street walk graph, stops, and R5's splits for the disc hexes and venues (shared by every mode)."""
    venues_df, union_df, disc_df = disc_hexes()
    print(f"oracle: {len(venues_df)} venues, {len(union_df)} disc hexes (union), {len(disc_df)} venue-hex rows", flush=True)
    started = time.perf_counter()
    network, jpype = frozen_network()
    street_layer, transit_layer = network._transport_network.streetLayer, network._transport_network.transitLayer
    n_vertices = int(street_layer.vertexStore.getVertexCount())
    walk = walk_edges(street_layer, jpype)
    from_pair = walk[3]
    walk = walk[:3]
    stop_vertex = as_numpy(transit_layer.streetVertexForStop)
    feed_of_stop = np.array([str(transit_layer.feedFromStop(i)) for i in range(len(stop_vertex))])
    print(f"  network + walk graph {time.perf_counter() - started:.0f} s: {n_vertices} vertices, {len(walk[0])} walk edges, "
          f"{len(stop_vertex)} stops ({(stop_vertex < 0).sum()} unlinked); feeds {sorted(set(feed_of_stop))}", flush=True)
    split_started = time.perf_counter()
    hex_split = splits(street_layer, union_df.centroid_lat.to_numpy(), union_df.centroid_lon.to_numpy(), jpype)
    venue_split = splits(street_layer, venues_df.centroid_lat.to_numpy(), venues_df.centroid_lon.to_numpy(), jpype)
    print(f"  splits {time.perf_counter() - split_started:.0f} s; unlinked hexes {hex_split.edge.isna().sum()}, venues "
          f"{venue_split.edge.isna().sum()}", flush=True)
    assert venue_split.edge.notna().all()
    hex_ok = hex_split.edge.notna().to_numpy()
    hex_v0 = np.where(hex_ok, hex_split.v0, 0).astype(np.int64)
    hex_v1 = np.where(hex_ok, hex_split.v1, 0).astype(np.int64)
    hex_pair = np.where(hex_ok, hex_split.edge, -2).astype(np.int64) >> 1
    # position along the pair's forward direction, for points on the same edge pair as the venue
    hex_pos = np.where(hex_v0 == from_pair[np.maximum(hex_pair, 0)], hex_split.d0_m, hex_split.d1_m)
    hex_row = pd.Series(np.arange(len(union_df)), index=union_df.hex_id.to_numpy())
    return {"venues_df": venues_df, "union_df": union_df, "disc_df": disc_df, "network": network, "jpype": jpype,
            "street_layer": street_layer, "transit_layer": transit_layer, "n_vertices": n_vertices, "walk": walk,
            "from_pair": from_pair, "stop_vertex": stop_vertex, "feed_of_stop": feed_of_stop, "hex_split": hex_split,
            "venue_split": venue_split, "hex_ok": hex_ok, "hex_v0": hex_v0, "hex_v1": hex_v1, "hex_pair": hex_pair,
            "hex_pos": hex_pos, "hex_row": hex_row, "started": started}


def venue_oracle(ctx, graph, venue, vsplit, limit_min=ORACLE_LIMIT_MIN):
    """Oracle seconds venue <- each of its disc hexes (inf if unlinked or past limit_min): hex ids, seconds."""
    from scipy.sparse.csgraph import dijkstra
    n_vertices, from_pair, hex_split = ctx["n_vertices"], ctx["from_pair"], ctx["hex_split"]
    speed_mps = SPEED_KMH / 3.6
    super_node = graph.shape[0] - 1
    v0, v1 = int(vsplit.v0), int(vsplit.v1)
    targets = np.array([v0, v1, v0 + n_vertices, v1 + n_vertices])
    offsets = np.array([vsplit.d0_m, vsplit.d1_m, vsplit.d0_m, vsplit.d1_m]) / speed_mps
    dist = dijkstra(with_super_sources(graph, targets, offsets), directed=True, indices=super_node,
                    limit=limit_min * SECONDS_PER_MIN)
    disc_df = ctx["disc_df"]
    ids = disc_df.hex_id[disc_df.venue_hex == venue.hex_id].to_numpy()
    rows = ctx["hex_row"][ids].to_numpy()
    oracle_s = np.minimum(dist[ctx["hex_v0"][rows]] + hex_split.d0_m.to_numpy()[rows] / speed_mps,
                          dist[ctx["hex_v1"][rows]] + hex_split.d1_m.to_numpy()[rows] / speed_mps)
    venue_pair = int(vsplit.edge) >> 1
    venue_pos = vsplit.d0_m if v0 == from_pair[venue_pair] else vsplit.d1_m
    same_edge = ctx["hex_pair"][rows] == venue_pair
    oracle_s = np.where(same_edge, np.minimum(oracle_s, np.abs(ctx["hex_pos"][rows] - venue_pos) / speed_mps), oracle_s)
    return ids, np.where(ctx["hex_ok"][rows], oracle_s, np.inf)


def run_oracle():
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_oracle.parquet"
    timing_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_oracle_timing.csv"
    rounding_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_rounding.csv"
    ctx = oracle_setup()
    venues_df, venue_split, started = ctx["venues_df"], ctx["venue_split"], ctx["started"]
    walk, stop_vertex, n_vertices, feed_of_stop = ctx["walk"], ctx["stop_vertex"], ctx["n_vertices"], ctx["feed_of_stop"]
    frames, timing, rounding = [], [], []
    trips_by_date = {}
    for label, departure in DEPARTURES.items():
        if departure.date() not in trips_by_date:
            trips_by_date[departure.date()] = active_trips(ctx["transit_layer"], departure.date(), ctx["jpype"])
        trips, n_frequency = trips_by_date[departure.date()]
        start_s = departure.hour * 3600 + departure.minute * SECONDS_PER_MIN
        end_s = start_s + ORACLE_CUT_MIN * SECONDS_PER_MIN
        build_started = time.perf_counter()
        rides_df = ride_edges(trips, start_s, end_s)
        graph = reverse_graph(walk, rides_df, stop_vertex, n_vertices)
        build_s = time.perf_counter() - build_started
        rounding.append(rounding_figures(trips, start_s, end_s, feed_of_stop).assign(departure=label))
        print(f"  {label}: {len(trips)} active trips ({n_frequency} frequency, skipped), {len(rides_df)} ride pairs, "
              f"graph {graph.shape[0]} nodes / {graph.nnz} edges, built {build_s:.1f} s", flush=True)
        for venue, vsplit in zip(venues_df.itertuples(), venue_split.itertuples()):
            run_started = time.perf_counter()
            ids, oracle_s = venue_oracle(ctx, graph, venue, vsplit)
            run_s = time.perf_counter() - run_started
            keep = oracle_s <= ORACLE_LIMIT_MIN * SECONDS_PER_MIN
            frames.append(pd.DataFrame({"departure": label, "venue_hex": venue.hex_id, "hex_id": ids[keep], "oracle_s": oracle_s[keep]}))
            n_set = int((oracle_s <= ORACLE_CUT_MIN * SECONDS_PER_MIN).sum())
            timing.append({"departure": label, "venue": venue.label, "venue_hex": venue.hex_id, "graph_build_s": build_s,
                           "dijkstra_s": run_s, "disc_hexes": len(ids), "oracle_set_hexes": n_set})
            print(f"    {venue.label}: {run_s:.1f} s, oracle set {n_set} of {len(ids)} disc hexes", flush=True)
    pd.concat(frames, ignore_index=True).to_parquet(out_path, index=False)
    pd.DataFrame(timing).to_csv(timing_path, index=False)
    pd.concat(rounding).rename_axis("feed").reset_index().to_csv(rounding_path, index=False)
    print(f"oracle done in {time.perf_counter() - started:.0f} s: {out_path.name}", flush=True)


# --- span oracles (RCH-26, 75th decisions) -------------------------------------------------------------
def all_schedules(transit_layer):
    """Every scheduled trip once: (stops, arrivals, departures) and its service code; frequency trips counted, skipped."""
    trips, codes, n_frequency = [], [], 0
    for pattern in transit_layer.tripPatterns:
        stops = np.asarray(pattern.stops, dtype=np.int64)
        for schedule in pattern.tripSchedules:
            if schedule.headwaySeconds is not None:
                n_frequency += 1
                continue
            trips.append((stops, np.asarray(schedule.arrivals, dtype=np.int64), np.asarray(schedule.departures, dtype=np.int64)))
            codes.append(schedule.serviceCode)
    return trips, np.asarray(codes), n_frequency


def service_mask(transit_layer, date, jpype):
    services = transit_layer.getActiveServicesForDate(jpype.JClass("java.time.LocalDate").of(date.year, date.month, date.day))
    return np.array([bool(services.get(i)) for i in range(transit_layer.services.size())])


def day_type_trips(ctx, schedules, dates):
    """Trips running on any of the dates, on one service day's clock: service day D + k's trips shifted by k days
    (k in DAY_OFFSETS), so trips past 24:00 of the day before and early trips of the day after are in; one copy per
    (trip, shift)."""
    trips, codes = schedules
    keys = set()
    for date in dates:
        for offset in DAY_OFFSETS:
            mask = service_mask(ctx["transit_layer"], date + datetime.timedelta(days=offset), ctx["jpype"])
            keys.update((int(k), offset) for k in np.flatnonzero(mask[codes]))
    return [(trips[k][0], trips[k][1] + offset * DAY_S, trips[k][2] + offset * DAY_S) for k, offset in sorted(keys)]


def parquet_bytes(rides_df):
    """Size of the ride edges as a stored parquet (int32 columns), measured in memory."""
    buffer = io.BytesIO()
    rides_df.astype(RIDE_DTYPES).to_parquet(buffer, index=False)
    return buffer.tell()


def run_tightness():
    """(a) Oracle set size by departure window (one weekday), ride pairs and parquet size; truth routing speed."""
    tag = run_date()
    ctx = oracle_setup()
    venues_df, venue_split, union_df = ctx["venues_df"], ctx["venue_split"], ctx["union_df"]
    schedules = all_schedules(ctx["transit_layer"])
    print(f"  {len(schedules[0])} scheduled trips ({schedules[2]} frequency, skipped)", flush=True)
    trips = day_type_trips(ctx, schedules[:2], [TIGHTNESS_DATE])
    print(f"  {TIGHTNESS_DATE}: {len(trips)} trips with day shifts", flush=True)
    persons = union_df.set_index("hex_id").persons
    rows = []
    for label, (start, length_min) in TIGHTNESS_WINDOWS.items():
        start_s = start.hour * 3600 + start.minute * SECONDS_PER_MIN
        for cut_min in TIGHTNESS_CUTS_MIN:
            build_started = time.perf_counter()
            rides_df = ride_edges(trips, start_s, start_s + (length_min + cut_min) * SECONDS_PER_MIN)
            graph = reverse_graph(ctx["walk"], rides_df, ctx["stop_vertex"], ctx["n_vertices"])
            build_s = time.perf_counter() - build_started
            size = parquet_bytes(rides_df)
            for venue, vsplit in zip(venues_df.itertuples(), venue_split.itertuples()):
                ids, oracle_s = venue_oracle(ctx, graph, venue, vsplit, limit_min=cut_min)
                inside = oracle_s <= cut_min * SECONDS_PER_MIN
                rows.append({"window": label, "window_min": length_min, "cut_min": cut_min, "venue": venue.label,
                             "set_hexes": int(inside.sum()), "set_persons": float(persons[ids[inside]].sum()),
                             "ride_pairs": len(rides_df), "parquet_mb": size / 1e6, "build_s": build_s})
            print(f"  {label} cut {cut_min}: {len(rides_df)} ride pairs, {size / 1e6:.1f} MB, built {build_s:.1f} s; subject set "
                  f"{rows[-len(venues_df)]['set_hexes']}", flush=True)
    tight_df = pd.DataFrame(rows)
    tight_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_tightness.csv", index=False)
    # truth routing speed at the superset test's max time (and the 75th's 45 for comparison)
    sample_ids = np.random.default_rng(SEED).choice(union_df.hex_id.to_numpy(), size=TIMING_ORIGINS, replace=False)
    from r5py import TransportMode
    timing = []
    for max_min in (TRUTH_MAX_MIN, SUPERSET_TRUTH_MAX_MIN):
        step = time.perf_counter()
        ttm(ctx["network"], points_gdf(union_df, sample_ids), venues_gdf(venues_df), TIMING_DEPARTURE,
            [TransportMode.TRANSIT, TransportMode.WALK], max_min)
        seconds = time.perf_counter() - step
        timing.append({"max_min": max_min, "origins": TIMING_ORIGINS, "s": seconds, "s_per_origin": seconds / TIMING_ORIGINS})
        print(f"  truth speed, max {max_min}: {seconds:.0f} s for {TIMING_ORIGINS} origins x {len(venues_df)} venues "
              f"({seconds / TIMING_ORIGINS:.3f} s per origin)", flush=True)
    pd.DataFrame(timing).to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_truth_speed.csv", index=False)
    print(f"tightness done in {time.perf_counter() - ctx['started']:.0f} s", flush=True)


def run_spans():
    """(b) Every day type x 30-min slot graph, whole network: ride pairs, parquet size, build time at each cut."""
    tag = run_date()
    started = time.perf_counter()
    network, jpype = frozen_network()
    ctx = {"transit_layer": network._transport_network.transitLayer, "jpype": jpype}
    schedules = all_schedules(ctx["transit_layer"])
    rows = []
    for day_type, dates in DAY_TYPES.items():
        trips = day_type_trips(ctx, schedules[:2], dates)
        for slot in range(SLOTS_PER_DAY):
            start_s = slot * SLOT_MIN * SECONDS_PER_MIN
            for cut_min in TIGHTNESS_CUTS_MIN:
                build_started = time.perf_counter()
                rides_df = ride_edges(trips, start_s, start_s + (SLOT_MIN + cut_min) * SECONDS_PER_MIN)
                rows.append({"day_type": day_type, "slot": f"{slot // 2:02d}:{slot % 2 * SLOT_MIN:02d}", "cut_min": cut_min,
                             "trips": len(trips), "ride_pairs": len(rides_df), "parquet_mb": parquet_bytes(rides_df) / 1e6,
                             "build_s": time.perf_counter() - build_started})
            print(f"  {day_type} {rows[-1]['slot']}: {rows[-1]['ride_pairs']} ride pairs at cut {cut_min}", flush=True)
    spans_df = pd.DataFrame(rows)
    spans_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_spans.csv", index=False)
    print(spans_df.groupby(["day_type", "cut_min"]).agg(ride_pairs_max=("ride_pairs", "max"), parquet_mb_sum=("parquet_mb", "sum"),
                                                         build_s_mean=("build_s", "mean")).to_string(), flush=True)
    print(f"spans done in {time.perf_counter() - started:.0f} s", flush=True)


def points_gdf(union_df, ids):
    import geopandas as gpd
    rows = union_df.set_index("hex_id").loc[ids]
    return gpd.GeoDataFrame({"id": ids}, crs="EPSG:4326", geometry=gpd.points_from_xy(rows.centroid_lon, rows.centroid_lat))


def venues_gdf(venues_df):
    """Venue points; ids offset so no hex id equals a venue id (r5py reads from_id == to_id as 0)."""
    import geopandas as gpd
    return gpd.GeoDataFrame({"id": -1 - venues_df.hex_id}, crs="EPSG:4326",
                            geometry=gpd.points_from_xy(venues_df.centroid_lon, venues_df.centroid_lat))


def ttm(network, origins_gdf, destinations_gdf, departure, modes, max_min):
    """Frozen-model travel times (seconds, column s; NaN past max_min)."""
    from r5py import TravelTimeMatrix
    table = pd.DataFrame(TravelTimeMatrix(
        network, origins=origins_gdf, destinations=destinations_gdf, departure=departure,
        departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
        transport_modes=modes, max_time=datetime.timedelta(minutes=max_min), speed_walking=SPEED_KMH))
    return table.rename(columns={f"travel_time_p{SINGLE_PERCENTILE}": "s"})


# --- superset test (c) ---------------------------------------------------------------------------------
def slot_start_s(slot_time):
    return slot_time.hour * 3600 + slot_time.minute * SECONDS_PER_MIN


def truth_departures(label, date, slot_time):
    """SUPERSET_DEPARTURES seeded minutes inside the slot (seed from the slot label, so reruns repeat them)."""
    rng = np.random.default_rng([SEED, int(hashlib.sha256(label.encode()).hexdigest()[:8], 16)])
    minutes = np.sort(rng.choice(SLOT_MIN, size=SUPERSET_DEPARTURES, replace=False))
    start = datetime.datetime.combine(date, slot_time)
    return [start + datetime.timedelta(minutes=int(m)) for m in minutes]


def superset_sample_ids(union_df):
    return np.random.default_rng(SEED).choice(union_df.hex_id.to_numpy(), size=round(SAMPLE_SHARE * len(union_df)), replace=False)


def run_superset_oracle():
    """Span oracle per tested slot and cut: set sizes, and oracle times for the sample and the band past each cut. With
    `pad N`: the window padded N min on both sides of the slot (a coarser bin); with `clock`: the clock hour holding
    the slot; both keep every hex the plain run kept."""
    tag = run_date()
    variant = variant_name()
    suffix = f"_{variant}" if variant else ""
    plain_df = pd.read_parquet(newest(f"{NAME}_2*_superset_oracle.parquet"), columns=["slot", "hex_id"]) if variant else None
    truth_path = newest(f"{NAME}_2*_superset_truth.parquet")
    routed_df = pd.read_parquet(truth_path, columns=["slot", "hex_id"]) if truth_path else pd.DataFrame(columns=["slot", "hex_id"])
    ctx = oracle_setup()
    venues_df, venue_split, union_df = ctx["venues_df"], ctx["venue_split"], ctx["union_df"]
    persons = union_df.set_index("hex_id").persons
    sample_ids = superset_sample_ids(union_df)
    schedules = all_schedules(ctx["transit_layer"])
    trips_by_type = {}
    rows, sizes = [], []
    for label, (day_type, _, slot_time, _) in SUPERSET_SLOTS.items():
        if day_type not in trips_by_type:
            trips_by_type[day_type] = day_type_trips(ctx, schedules[:2], DAY_TYPES[day_type])
        trips = trips_by_type[day_type]
        start_s = slot_start_s(slot_time)
        kept_ids = np.unique(plain_df.hex_id[plain_df.slot == label]) if variant else None
        routed_ids = np.unique(routed_df.hex_id[routed_df.slot == label])     # every venue for a routed hex (78th fix)
        before_min, after_min = variant_padding(slot_time)
        for cut_min in SUPERSET_CUTS_MIN:
            build_started = time.perf_counter()
            rides_df = ride_edges(trips, start_s - before_min * SECONDS_PER_MIN,
                                  start_s + (SLOT_MIN + after_min + cut_min) * SECONDS_PER_MIN)
            graph = reverse_graph(ctx["walk"], rides_df, ctx["stop_vertex"], ctx["n_vertices"])
            build_s = time.perf_counter() - build_started
            for venue, vsplit in zip(venues_df.itertuples(), venue_split.itertuples()):
                ids, oracle_s = venue_oracle(ctx, graph, venue, vsplit, limit_min=SUPERSET_TRUTH_MAX_MIN)
                cut_s = cut_min * SECONDS_PER_MIN
                inside = oracle_s <= cut_s
                keep = np.isin(ids, sample_ids) | np.isin(ids, routed_ids) | ((oracle_s > cut_s) & (oracle_s <= cut_s + BAND_WIDTH_MIN * SECONDS_PER_MIN))
                if variant:
                    keep |= np.isin(ids, kept_ids)
                rows.append(pd.DataFrame({"slot": label, "cut_min": cut_min, "venue_hex": venue.hex_id, "hex_id": ids[keep],
                                          "oracle_s": oracle_s[keep].astype(np.float32)}))
                sizes.append({"slot": label, "cut_min": cut_min, "venue_hex": venue.hex_id, "venue": venue.label,
                              "set_hexes": int(inside.sum()), "set_persons": float(persons[ids[inside]].sum()),
                              "disc_persons": float(persons[ids].sum()), "ride_pairs": len(rides_df), "build_s": build_s})
            print(f"  {label} cut {cut_min}: {len(rides_df)} ride pairs, built {build_s:.1f} s; set hexes by venue "
                  f"{[s['set_hexes'] for s in sizes[-len(venues_df):]]}", flush=True)
    pd.concat(rows, ignore_index=True).to_parquet(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_superset_oracle{suffix}.parquet", index=False)
    pd.DataFrame(sizes).to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_superset_sizes{suffix}.csv", index=False)
    print(f"superset oracle done in {time.perf_counter() - ctx['started']:.0f} s", flush=True)


def variant_name():
    """Oracle window variant from the command line: '' (the slot), 'padN' or 'clock'."""
    if sys.argv[2:3] == ["pad"]:
        return f"pad{int(sys.argv[3])}"
    return "clock" if sys.argv[2:3] == ["clock"] else ""


def variant_padding(slot_time):
    """Minutes added before and after the slot's departure window for the command line's variant."""
    variant = variant_name()
    if variant == "clock":
        before_min = slot_time.minute
        return before_min, CLOCK_HOUR_MIN - SLOT_MIN - before_min
    pad_min = int(variant.removeprefix("pad")) if variant else 0
    return pad_min, pad_min


def band_ids(oracle_df, slot, cuts_min):
    """Hexes in the band past each of the cuts for one slot (any venue)."""
    parts = [np.empty(0, np.int64)] + [oracle_df.hex_id[(oracle_df.slot == slot) & (oracle_df.cut_min == cut_min) & (oracle_df.oracle_s > cut_min * SECONDS_PER_MIN)
                              & (oracle_df.oracle_s <= (cut_min + BAND_WIDTH_MIN) * SECONDS_PER_MIN)] for cut_min in cuts_min]
    return np.unique(np.concatenate(parts))


def run_superset_truth():
    """Frozen-model hex -> venue at the slot's truth departures, for the sample and the bands past the start cuts
    (or, with extra cut arguments `cap:cut`, for the band past those cuts, adding to the saved truth; with `sample`,
    the sample only; with a slot label first, e.g. `"Mon-Thu 12:00" 20:30`, that slot only)."""
    tag = run_date()
    args = sys.argv[2:]
    slots = [args.pop(0)] if args and args[0] in SUPERSET_SLOTS else list(SUPERSET_SLOTS)
    is_sample_only = args == ["sample"]
    extra = {} if is_sample_only else dict(map(int, arg.split(":")) for arg in args)
    cut_by_cap = {} if is_sample_only else extra or {cap: cap + START_MARGIN_MIN for cap in SUPERSET_CAPS_MIN}
    venues_df, union_df, _ = disc_hexes()
    oracle_df = pd.read_parquet(newest(f"{NAME}_2*_superset_oracle.parquet"))
    sample_ids = superset_sample_ids(union_df)
    truth_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_superset_truth.parquet"
    done_df = pd.read_parquet(truth_path) if truth_path.exists() else None
    network, _ = frozen_network()
    from r5py import TransportMode
    transit_modes, walk_modes = [TransportMode.TRANSIT, TransportMode.WALK], [TransportMode.WALK]
    near_km = np.min([haversine_m(v.centroid_lat, v.centroid_lon, union_df.centroid_lat.to_numpy(), union_df.centroid_lon.to_numpy())
                      for v in venues_df.itertuples()], axis=0) / 1000
    near_ids = union_df.hex_id.to_numpy()[near_km < WALK_ONLY_KM]
    started = time.perf_counter()
    frames = [] if done_df is None else [done_df]
    for label in slots:
        _, date, slot_time, _ = SUPERSET_SLOTS[label]
        ids = band_ids(oracle_df, label, cut_by_cap.values())
        if not extra:
            ids = np.union1d(ids, sample_ids)
        if done_df is not None:
            ids = np.setdiff1d(ids, done_df.hex_id[done_df.slot == label].unique())
        for departure in truth_departures(label, date, slot_time):
            assert network.transit_layer.covers(departure.date())
            step = time.perf_counter()
            transit = ttm(network, points_gdf(union_df, ids), venues_gdf(venues_df), departure, transit_modes,
                          SUPERSET_TRUTH_MAX_MIN).rename(columns={"s": "transit_s"})
            walk = ttm(network, points_gdf(union_df, np.intersect1d(ids, near_ids)), venues_gdf(venues_df), departure,
                       walk_modes, SUPERSET_TRUTH_MAX_MIN).rename(columns={"s": "walk_s"})
            both = transit.merge(walk, on=["from_id", "to_id"], how="left")
            frames.append(pd.DataFrame({"slot": label, "departure": departure, "hex_id": both.from_id, "venue_hex": -1 - both.to_id,
                                        "transit_s": both.transit_s.astype(np.float32), "walk_s": both.walk_s.astype(np.float32)}))
            seconds = time.perf_counter() - step
            print(f"  {label} {departure:%a %H:%M}: {len(ids)} origins in {seconds:.0f} s ({seconds / max(len(ids), 1):.3f} s per origin); "
                  f"elapsed {time.perf_counter() - started:.0f} s", flush=True)
        pd.concat(frames, ignore_index=True).to_parquet(truth_path, index=False)    # saved after every slot
    cuts_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_superset_truth_cuts.csv"
    cuts_df = pd.DataFrame({"slot": [slot for slot in slots for _ in cut_by_cap], "cap_min": list(cut_by_cap) * len(slots),
                            "cut_min": list(cut_by_cap.values()) * len(slots)})
    cuts_df.to_csv(cuts_path, mode="a", header=not cuts_path.exists(), index=False)
    print(f"superset truth done in {time.perf_counter() - started:.0f} s", flush=True)


def transit_fit_pairs():
    """Fit pairs for the error draws, as functions/trip_uncertainty.py is called in the 75th: transit_holdout_score's
    scored seen + holdout pairs (frozen model vs Google's default)."""
    frames = [pd.read_csv(newest(f"{SCORE_NAME}_2*_{part}_results.csv")) for part in ("seen", "holdout")]
    df = pd.concat(frames, ignore_index=True)
    df = df[df.is_scored.astype(bool) & np.isfinite(df.model_s)]
    model_s = np.maximum(df.model_s.to_numpy(dtype=float), TRIP_ERROR_MIN_MODEL_S)
    return pd.DataFrame({"group": np.where(df.dep_min_of_day < TRIP_ERROR_NIGHT_END_MIN, NIGHT_GROUP, DAY_GROUP),
                         "log_model": np.log(model_s), "residual": np.log(df.default_s.to_numpy(dtype=float) / model_s)})


def band_probability_grid(fit_df, group, cap_min):
    """P(Google's rounded minute <= cap | predicted s) on PREDICTED_GRID_S (copy of trip_uncertainty's logic:
    the K fit pairs nearest in log time inside the group, all pairs if the group is smaller than K)."""
    part = fit_df[fit_df.group == group] if (fit_df.group == group).sum() >= TRIP_ERROR_K_NEIGHBOURS else fit_df
    part = part.sort_values("log_model")
    log_model, residual = part.log_model.to_numpy(), part.residual.to_numpy()
    k = min(TRIP_ERROR_K_NEIGHBOURS, len(log_model))
    probability = []
    for predicted_s in np.maximum(PREDICTED_GRID_S, TRIP_ERROR_MIN_MODEL_S):
        centre = np.searchsorted(log_model, np.log(predicted_s))
        window = np.arange(max(0, centre - k), min(len(log_model), centre + k))
        nearest = window[np.argsort(np.abs(log_model[window] - np.log(predicted_s)), kind="stable")[:k]]
        probability.append((np.round(predicted_s * np.exp(residual[nearest]) / SECONDS_PER_MIN) <= cap_min).mean())
    return np.array(probability)


def shelf_line_s(probability, cap_min):
    """First grid time at or past the cap where P falls to SHELF_LEVEL: later times are the model-error shelf."""
    past = (PREDICTED_GRID_S >= cap_min * SECONDS_PER_MIN) & (probability <= SHELF_LEVEL)
    return PREDICTED_GRID_S[np.argmax(past)]


def run_superset_report():
    """With `pad N` or `clock`: set membership from that oracle variant; strata (which hexes were routed) from the plain one."""
    tag = run_date()
    variant = variant_name()
    suffix = f"_{variant}" if variant else ""
    venues_df, union_df, disc_df = disc_hexes()
    label_of = dict(zip(venues_df.hex_id, venues_df.label))
    oracle_df = pd.read_parquet(newest(f"{NAME}_2*_superset_oracle.parquet"))
    set_oracle_df = pd.read_parquet(newest(f"{NAME}_2*_superset_oracle{suffix}.parquet")) if variant else oracle_df
    sizes_df = pd.read_csv(newest(f"{NAME}_2*_superset_sizes{suffix}.csv"))
    truth_df = pd.read_parquet(newest(f"{NAME}_2*_superset_truth.parquet"))
    truth_df["truth_s"] = np.fmin(truth_df.transit_s.fillna(np.inf), truth_df.walk_s.fillna(np.inf))
    fit_df = transit_fit_pairs()
    sample_ids = superset_sample_ids(union_df)
    cuts_path = newest(f"{NAME}_2*_superset_truth_cuts.csv")
    routed_cuts_df = pd.read_csv(cuts_path) if cuts_path else pd.DataFrame(columns=["slot", "cap_min", "cut_min"])
    persons = union_df.set_index("hex_id").persons
    lines = [f"{NAME} {tag}, superset test (c): {len(venues_df)} venues, populated hexes within {DISC_KM} km; span oracle per "
             f"day type x {SLOT_MIN}-min slot; truth = frozen model at {SUPERSET_DEPARTURES} seeded minutes in the slot, max "
             f"{SUPERSET_TRUTH_MAX_MIN}; fit pairs {len(fit_df)} (night {(fit_df.group == NIGHT_GROUP).sum()})", ""]
    grids, shelf_s = {}, {}
    lines.append(f"P(Google <= cap | predicted) and the shelf line (first time >= cap with P <= {SHELF_LEVEL}):")
    for cap_min in SUPERSET_CAPS_MIN:
        for group in (DAY_GROUP, NIGHT_GROUP):
            grids[cap_min, group] = band_probability_grid(fit_df, group, cap_min)
            shelf_s[cap_min, group] = shelf_line_s(grids[cap_min, group], cap_min)
            at = {m: grids[cap_min, group][int(m * SECONDS_PER_MIN / GRID_STEP_S)] for m in (cap_min, cap_min + 2, cap_min + 5, cap_min + 10, SUPERSET_TRUTH_MAX_MIN - 1)}
            lines.append(f"  cap {cap_min} {group}: shelf line {shelf_s[cap_min, group] / 60:.1f} min; P at "
                         + ", ".join(f"{m} {p:.3f}" for m, p in at.items()))
    lines.append("")
    rows, violations, noise, generosity = [], [], [], []
    for slot, (day_type, _, slot_time, is_ruled) in SUPERSET_SLOTS.items():
        is_night = slot_time.hour * 60 + slot_time.minute < TRIP_ERROR_NIGHT_END_MIN
        truth = truth_df[truth_df.slot == slot]
        if truth.empty:
            lines.append(f"{slot}: no truth routed yet, left out")
            continue
        # two strata: the bands past the routed cuts (every hex routed, weight 1); the rest (seeded sample, 1 / share)
        certain = band_ids(oracle_df, slot, routed_cuts_df.cut_min[routed_cuts_df.slot == slot].unique())
        assert np.isin(certain, truth.hex_id.unique()).all(), f"{slot}: band hexes not routed"
        weight = pd.Series(1 / SAMPLE_SHARE, index=sample_ids)
        weight = pd.concat([weight[~weight.index.isin(certain)], pd.Series(1.0, index=certain)])
        pivot = truth.pivot_table(index=["venue_hex", "hex_id"], columns="departure", values="truth_s", aggfunc="first")
        pivot = pivot.reset_index().merge(disc_df[["venue_hex", "hex_id"]], on=["venue_hex", "hex_id"], how="inner")
        times = pivot.drop(columns=["venue_hex", "hex_id"]).to_numpy(dtype=float)
        # oracle times only fall as the cut (window) grows: a hex is inside at cut K if any saved time at a cut <= K
        # is <= K (rows were saved for the sample at every cut, for band hexes near their own cut)
        best = (set_oracle_df[set_oracle_df.slot == slot].pivot_table(index=["venue_hex", "hex_id"], columns="cut_min",
                                                                      values="oracle_s", aggfunc="min")
                .reindex(columns=SUPERSET_CUTS_MIN).fillna(np.inf).cummin(axis=1))
        best = best.reindex(pd.MultiIndex.from_frame(pivot[["venue_hex", "hex_id"]])).fillna(np.inf)
        base = pivot[["venue_hex", "hex_id"]].assign(w=lambda d: weight.reindex(d.hex_id).fillna(0).to_numpy(),
                                                    persons=lambda d: persons.reindex(d.hex_id).to_numpy())
        for cap_min in SUPERSET_CAPS_MIN:
            groups = [NIGHT_GROUP, DAY_GROUP] if is_night else [DAY_GROUP]
            reached = (times <= cap_min * SECONDS_PER_MIN)
            noise.append({"slot": slot, "cap_min": cap_min, "pairs reached at some departure": int(reached.any(axis=1).sum()),
                          "of which not at all": int((reached.any(axis=1) & ~reached.all(axis=1)).sum())})
            for group in groups:
                grid, line_s = grids[cap_min, group], shelf_s[cap_min, group]
                finite = np.isfinite(times)
                index = np.clip(np.round(np.where(finite, times, 0) / GRID_STEP_S).astype(int), 0, len(grid) - 1)
                p = np.where(finite, grid[index], 0.0)
                is_core = finite & (times <= line_s)
                frame = base.assign(core=(p * is_core).mean(axis=1), shelf=(p * ~is_core).mean(axis=1))
                for cut_min in SUPERSET_CUTS_MIN:
                    cut_s = cut_min * SECONDS_PER_MIN
                    joined = frame.assign(oracle_s=best[cut_min].to_numpy())
                    outside = ~(joined.oracle_s <= cut_s)
                    if cap_min == SUPERSET_CAPS_MIN[0] and group == groups[0]:
                        fastest = np.nanmin(np.where(np.isfinite(times), times, np.nan), axis=1)
                        slower = np.isfinite(fastest) & (fastest <= cut_s) & (joined.oracle_s.to_numpy() > fastest)
                        generosity.append({"slot": slot, "cut_min": cut_min, "pairs truth <= cut": int((fastest <= cut_s).sum()),
                                           "oracle > truth": int(slower.sum()), "of which outside set": int((slower & outside).sum()),
                                           "oracle / truth q50": np.nanmedian(joined.oracle_s.to_numpy()[fastest <= cut_s]
                                                                              / fastest[fastest <= cut_s])})
                    if cut_min == SUPERSET_CUTS_MIN[-1] and group == groups[0]:
                        violations.append(joined.assign(slot=slot, cut_min=cut_min, departures=[list(r) for r in times])
                                          [outside & (np.nanmin(np.where(np.isfinite(times), times, np.nan), axis=1) <= cut_s)])
                    for venue_hex, part in joined.groupby("venue_hex"):
                        out = outside[part.index]
                        y_core, y_shelf = part.w * part.persons * part.core, part.w * part.persons * part.shelf
                        sampled = part.w > 1
                        missed = (part.persons * part.core)[out & sampled]
                        rows.append({"slot": slot, "is_ruled": is_ruled, "group": group, "cap_min": cap_min, "cut_min": cut_min,
                                     "venue": label_of[venue_hex], "core_mass": y_core.sum(), "shelf_mass": y_shelf.sum(),
                                     "missed_core": y_core[out].sum(), "missed_shelf": y_shelf[out].sum(),
                                     "missed_core_se": np.sqrt(((1 - SAMPLE_SHARE) / SAMPLE_SHARE ** 2 * missed ** 2).sum()),
                                     "missed_core_hexes": int((out & (part.core > 0)).sum())})
    mass_df = pd.DataFrame(rows)
    for column in ("missed_core", "missed_core_se"):
        mass_df[column.replace("missed_core", "core_share")] = mass_df[column] / mass_df.core_mass
    mass_df["all_share"] = (mass_df.missed_core + mass_df.missed_shelf) / (mass_df.core_mass + mass_df.shelf_mass)
    mass_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_superset_mass{suffix}.csv", index=False)
    for cap_min in SUPERSET_CAPS_MIN:
        part = mass_df[mass_df.cap_min == cap_min]
        ruled = part[part.is_ruled & (part.group == DAY_GROUP)]
        worst = ruled.groupby("cut_min").core_share.max()
        passing = worst[(worst <= MISSED_SHARE) & (worst.index >= cap_min + START_MARGIN_MIN)]
        verdict = f"cut {passing.index.min()} min" if len(passing) else f"NONE up to {MAX_CUT_MIN}"
        lines.append(f"CAP {cap_min}: rule (ruled weekday slots, every venue, core share <= {MISSED_SHARE:.0%}, cuts from "
                     f"{cap_min + START_MARGIN_MIN}): {verdict}")
        lines.append("  worst ruled venue x slot core share by cut: " + ", ".join(f"{c} {v:.4f}" for c, v in worst.items()))
        pooled = part.groupby(["slot", "group", "cut_min"])[["missed_core", "core_mass", "missed_shelf", "shelf_mass"]].sum()
        pooled["core_share"] = pooled.missed_core / pooled.core_mass
        pooled["all_share"] = (pooled.missed_core + pooled.missed_shelf) / (pooled.core_mass + pooled.shelf_mass)
        lines.append("  pooled over venues (core share | core + shelf share):")
        lines.append(pooled[["core_share", "all_share"]].unstack("cut_min").to_string(float_format=lambda x: f"{x:.4f}"))
        lines.append("")
        lines.append(f"  per venue at the start cut {cap_min + START_MARGIN_MIN} (core share, se, missed core hexes routed):")
        start = part[part.cut_min == cap_min + START_MARGIN_MIN]
        lines.append(start[["slot", "group", "venue", "core_share", "core_share_se", "missed_core_hexes", "all_share"]]
                     .to_string(index=False, float_format=lambda x: f"{x:.4f}"))
        lines.append("")
    violation_df = pd.concat(violations, ignore_index=True) if violations else pd.DataFrame()
    lines.append(f"generosity at cut {SUPERSET_CUTS_MIN[-1]}: routed pairs outside the set with truth <= the cut at some departure: "
                 f"{len(violation_df)}")
    if len(violation_df):
        violation_df["venue"] = violation_df.venue_hex.map(label_of)
        lines.append(violation_df[["slot", "venue", "hex_id", "oracle_s", "departures"]].head(40).to_string(index=False))
        violation_df.drop(columns="departures").to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_superset_violations{suffix}.csv", index=False)
    lines += ["", "generosity by cut (routed pairs, fastest truth over the slot's departures; any oracle > truth is a defect):",
              pd.DataFrame(generosity).to_string(index=False, float_format=lambda x: f"{x:.3f}")]
    lines += ["", "departure noise (pairs reached <= cap at some truth departure; of which not at every one):",
              pd.DataFrame(noise).to_string(index=False), ""]
    lines.append("set sizes (hexes / persons in the set, by slot and cut; all venues summed):")
    lines.append(sizes_df.groupby(["slot", "cut_min"])[["set_hexes", "set_persons", "ride_pairs", "build_s"]]
                 .agg({"set_hexes": "sum", "set_persons": "sum", "ride_pairs": "first", "build_s": "first"}).unstack("cut_min")
                 .to_string(float_format=lambda x: f"{x:.0f}"))
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_superset_summary{suffix}.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)


# --- truth ---------------------------------------------------------------------------------------------
def truth_origins(union_df, oracle_df):
    """Per departure: hex ids routed (band at that departure, plus the seeded sample); and the sample's ids."""
    rng = np.random.default_rng(SEED)
    sample_ids = rng.choice(union_df.hex_id.to_numpy(), size=round(SAMPLE_SHARE * len(union_df)), replace=False)
    band = oracle_df[(oracle_df.oracle_s > ORACLE_CUT_MIN * SECONDS_PER_MIN) & (oracle_df.oracle_s <= BAND_MIN * SECONDS_PER_MIN)]
    return {label: np.union1d(band.hex_id[band.departure == label].unique(), sample_ids) for label in DEPARTURES}, sample_ids


def run_truth():
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_truth.parquet"
    envelope_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_venue_to_hex.parquet"
    venues_df, union_df, disc_df = disc_hexes()
    oracle_df = pd.read_parquet(newest(f"{NAME}_2*_oracle.parquet"))
    origins, sample_ids = truth_origins(union_df, oracle_df)
    for label, ids in origins.items():
        print(f"truth {label}: {len(ids)} origins ({len(sample_ids)} sampled)", flush=True)
    network, _ = frozen_network()
    import geopandas as gpd
    from r5py import TransportMode, TravelTimeMatrix
    points = union_df.set_index("hex_id")
    near_km = np.min([haversine_m(v.centroid_lat, v.centroid_lon, points.centroid_lat.to_numpy(), points.centroid_lon.to_numpy())
                      for v in venues_df.itertuples()], axis=0) / 1000
    near_ids = points.index.to_numpy()[near_km < WALK_ONLY_KM]
    # venue ids offset so no hex id equals a venue id (r5py reads from_id == to_id as 0)
    venues = gpd.GeoDataFrame({"id": -1 - venues_df.hex_id}, crs="EPSG:4326",
                              geometry=gpd.points_from_xy(venues_df.centroid_lon, venues_df.centroid_lat))

    def hexes(ids):
        rows = points.loc[ids]
        return gpd.GeoDataFrame({"id": ids}, crs="EPSG:4326", geometry=gpd.points_from_xy(rows.centroid_lon, rows.centroid_lat))

    def ttm(origins_gdf, destinations_gdf, departure, modes, max_min):
        table = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins_gdf, destinations=destinations_gdf, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=modes, max_time=datetime.timedelta(minutes=max_min), speed_walking=SPEED_KMH))
        return table.rename(columns={f"travel_time_p{SINGLE_PERCENTILE}": "s"})

    transit_modes, walk_modes = [TransportMode.TRANSIT, TransportMode.WALK], [TransportMode.WALK]
    frames, envelopes = [], []
    started = time.perf_counter()
    for label, departure in DEPARTURES.items():
        assert network.transit_layer.covers(departure.date())
        step = time.perf_counter()
        transit = ttm(hexes(origins[label]), venues, departure, transit_modes, TRUTH_MAX_MIN).rename(columns={"s": "transit_s"})
        transit_s = time.perf_counter() - step
        walk = ttm(hexes(np.intersect1d(origins[label], near_ids)), venues, departure, walk_modes, TRUTH_MAX_MIN)
        both = transit.merge(walk.rename(columns={"s": "walk_s"}), on=["from_id", "to_id"], how="left")
        frames.append(pd.DataFrame({"departure": label, "hex_id": both.from_id, "venue_hex": -1 - both.to_id,
                                    "transit_s": both.transit_s, "walk_s": both.walk_s}))
        vh = ttm(venues, hexes(union_df.hex_id.to_numpy()), departure, transit_modes, ORACLE_CUT_MIN)
        envelopes.append(pd.DataFrame({"departure": label, "venue_hex": -1 - vh.from_id, "hex_id": vh.to_id, "vh_s": vh.s})
                         .dropna(subset=["vh_s"]))
        print(f"  {label}: hex -> venue {transit_s:.0f} s ({transit_s / len(origins[label]):.3f} s per origin), all "
              f"{time.perf_counter() - step:.0f} s", flush=True)
    truth_df = pd.concat(frames, ignore_index=True)
    truth_df["truth_s"] = np.fmin(truth_df.transit_s.fillna(np.inf), truth_df.walk_s.fillna(np.inf))
    truth_df.to_parquet(out_path, index=False)
    pd.concat(envelopes, ignore_index=True).to_parquet(envelope_path, index=False)
    print(f"truth done in {time.perf_counter() - started:.0f} s: {out_path.name}", flush=True)


# --- report --------------------------------------------------------------------------------------------
def run_report():
    tag = run_date()
    venues_df, union_df, disc_df = disc_hexes()
    oracle_df = pd.read_parquet(newest(f"{NAME}_2*_oracle.parquet"))
    truth_df = pd.read_parquet(newest(f"{NAME}_2*_truth.parquet"))
    vh_df = pd.read_parquet(newest(f"{NAME}_2*_venue_to_hex.parquet"))
    timing_df = pd.read_csv(newest(f"{NAME}_2*_oracle_timing.csv"))
    rounding_df = pd.read_csv(newest(f"{NAME}_2*_rounding.csv"))
    _, sample_ids = truth_origins(union_df, oracle_df)
    label_of = dict(zip(venues_df.hex_id, venues_df.label))
    cap_s, cut_s = CAP_MIN * SECONDS_PER_MIN, ORACLE_CUT_MIN * SECONDS_PER_MIN
    df = disc_df.merge(truth_df, on=["venue_hex", "hex_id"], how="inner")      # routed (hex, venue) pairs inside the disc
    df = df.merge(oracle_df, on=["departure", "venue_hex", "hex_id"], how="left")
    df["oracle_s"] = df.oracle_s.fillna(np.inf)                               # above ORACLE_LIMIT_MIN or unlinked
    df["is_sample"] = df.hex_id.isin(sample_ids)
    df["is_band"] = (df.oracle_s > ORACLE_CUT_MIN * SECONDS_PER_MIN) & (df.oracle_s <= BAND_MIN * SECONDS_PER_MIN)
    df["venue"] = df.venue_hex.map(label_of)
    lines = [f"{NAME} {tag}: 8 venues, populated hexes within {DISC_KM} km; oracle cut {ORACLE_CUT_MIN} min, cap {CAP_MIN};"
             f" truth routed for {ORACLE_CUT_MIN} < oracle <= {BAND_MIN} min (every hex) + a {SAMPLE_SHARE:.0%} seeded sample; Saturday report-only", ""]
    fails = df[(df.truth_s <= cap_s) & (df.oracle_s > cut_s)].copy()
    fails["gap_min"] = (fails.oracle_s - fails.truth_s) / SECONDS_PER_MIN
    for weekend, name in ((False, "WEEKDAY (ruled)"), (True, "SATURDAY (report-only)")):
        part = df[df.departure.isin(WEEKEND_LABELS) == weekend]
        part_fails = fails[fails.departure.isin(WEEKEND_LABELS) == weekend]
        reached = part[part.truth_s <= cap_s]
        lines.append(f"{name}: routed pairs {len(part)}, truth <= {CAP_MIN} {len(reached)} (band {reached.is_band.sum()}, "
                     f"outside band {(~reached.is_band).sum()}); FAILS {len(part_fails)}")
    verdict = "HOLDS" if fails[~fails.departure.isin(WEEKEND_LABELS)].empty else "FAILS"
    lines += [f"RULE: superset check {verdict} (weekday)", ""]
    if len(fails):
        lines.append("fails, hex by hex (min):")
        lines.append(fails[["departure", "venue", "hex_id", "km", "truth_s", "walk_s", "oracle_s", "gap_min"]]
                     .assign(truth_s=lambda d: d.truth_s / 60, walk_s=lambda d: d.walk_s / 60, oracle_s=lambda d: d.oracle_s / 60)
                     .sort_values("gap_min", ascending=False).to_string(index=False, float_format=lambda x: f"{x:.1f}"))
        lines.append("")
    generous = df[np.isfinite(df.truth_s)]
    slower = generous[generous.oracle_s > generous.truth_s]
    excess = (slower.oracle_s - slower.truth_s) / SECONDS_PER_MIN
    lines.append(f"generosity (report only): oracle > truth on {len(slower)} of {len(generous)} pairs with truth <= {TRUTH_MAX_MIN}"
                 f" ({len(slower) / max(len(generous), 1):.4f}); excess min q50 / q90 / max "
                 + (" / ".join(f"{v:.2f}" for v in np.quantile(excess, [0.5, 0.9, 1.0])) if len(slower) else "-"))
    lines.append("  of those with truth <= CAP: " + str(int((slower.truth_s <= cap_s).sum())))
    ratio = generous[generous.truth_s > 0].pipe(lambda d: d.oracle_s / d.truth_s)
    lines.append(f"  oracle / truth (truth <= {TRUTH_MAX_MIN}): q10 / q50 / q90 " + " / ".join(f"{v:.2f}" for v in np.quantile(ratio, [0.1, 0.5, 0.9])))
    ring = df[df.is_sample & (df.km >= EDGE_RING_KM[0]) & (df.km < EDGE_RING_KM[1])]
    lines.append(f"disc edge: sampled hexes in {EDGE_RING_KM} km {len(ring)}, truth <= {CAP_MIN} {int((ring.truth_s <= cap_s).sum())}; "
                 f"oracle <= {ORACLE_CUT_MIN} anywhere in the ring (all hexes): "
                 f"{int(((oracle_df.oracle_s <= cut_s) & oracle_df.merge(disc_df, on=['venue_hex', 'hex_id']).km.ge(EDGE_RING_KM[0]).to_numpy()).sum())}")
    lines.append("")
    lines.append("envelope sizes (hexes, per venue x departure): oracle set (all disc hexes) | 73rd venue -> hex <= "
                 f"{ORACLE_CUT_MIN} | truth <= {CAP_MIN} (sample / {SAMPLE_SHARE} + band fails)")
    rows = []
    for (label, venue_hex), group in df.groupby(["departure", "venue_hex"]):
        oracle_set = int(((oracle_df.departure == label) & (oracle_df.venue_hex == venue_hex) & (oracle_df.oracle_s <= cut_s)).sum())
        vh_set = int(((vh_df.departure == label) & (vh_df.venue_hex == venue_hex) & (vh_df.vh_s <= cut_s)
                      & vh_df.hex_id.isin(disc_df.hex_id[disc_df.venue_hex == venue_hex])).sum())
        reached = group.truth_s <= cap_s
        truth_est = int((reached & group.is_sample).sum() / SAMPLE_SHARE + (reached & group.is_band & ~group.is_sample).sum())
        timing = timing_df[(timing_df.departure == label) & (timing_df.venue_hex == venue_hex)].iloc[0]
        rows.append({"departure": label, "venue": label_of[venue_hex], "oracle_set": oracle_set, "vh_envelope": vh_set,
                     "truth_30": truth_est, "oracle / truth": oracle_set / max(truth_est, 1), "vh / truth": vh_set / max(truth_est, 1),
                     "dijkstra_s": timing.dijkstra_s, "graph_build_s": timing.graph_build_s})
    lines.append(pd.DataFrame(rows).to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    lines += ["", "GTFS rounding (RCH-26 figures, on each departure's window):", rounding_df.to_string(index=False, float_format=lambda x: f"{x:.3f}")]
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_summary.txt").write_text(summary + "\n", encoding="utf-8")
    fails.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{tag}_fails.csv", index=False)
    print(summary)


if __name__ == "__main__":
    {"oracle": run_oracle, "truth": run_truth, "report": run_report, "tightness": run_tightness,
     "spans": run_spans, "superset_oracle": run_superset_oracle, "superset_truth": run_superset_truth,
     "superset_report": run_superset_report}[sys.argv[1]]()
