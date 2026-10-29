"""Transit time-of-day spans: which hours of the week give alike catchments? (report only)

Question (concepts/reachability.md RCH-20, DESIGN.md Q25, open): the transit pass costs ~4.6 h per 1-min departure
for all populated hexes, so it needs the coarsest departure schedule the data allows. The user's direction (70th):
the 30-min opening-hours slot is the unit; let the data define the spans (cluster hours by similarity of results)
rather than guessing lunch / dinner / commute; keep sensitivity light. Where the pipeline would rely on it: the
departure schedule of the transit reachability pass. Report only; the schedule is the user's choice.

Mode `route`: the frozen model exactly as reachability_transit_pilot.py opens it (jar sha256, v2 network of release
20261016, TravelTimeMatrix 1-min window, percentile 49, walk 4.143 km/h, transit + walk, max_time 30 min; copied,
D1). Origins: 60 populated hexes (residents + workers >= 1), 20 per ring by haversine to the subject: inner < 5 km,
mid 5-15, outer 15-35 (Claude's choice: beyond 35 km almost nothing is reached), seeded. Destinations: all venue
hex centroids. Direction hex -> venue only (ODS-2, RCH-16; user 70th: venues are destinations, never origins).
Departures: the week of gtfs_service_profile.py (Mon 2026-10-26 to Sun 2026-11-01), every service hour it lists,
one departure per step block at a seeded random minute inside the block (jitter, against headway aliasing). Blocks
are routed even-indexed first, then odd (so a cut run still covers every hour; the halves are the split halves).
One TTM call per departure; rows <= 30 min saved per departure (checkpoint files, resumable).

Claude's rules, not user-approved (written before the run):
- Timing gate: time 12 calls at seeded service-hour departures (timing only, not used); the step is the finest of
  5 / 10 / 15 min whose projected total (mean call time x calls) is <= 35 min, else 20 min. Routing then stops at
  ROUTE_TIME_BOX_MIN wall minutes whatever the projection (resume continues it).
- Minutes = seconds rounded half up (the frozen jar returns seconds), kept <= 30.

Mode `cluster` (no routing): pairs kept = (origin, venue hex) <= 30 min at any departure. Value per departure =
min(minutes, 31) (unreached = 31). Hour profile = per pair, mean of the values over the hour's departures. Hour
distance = mean absolute difference over pairs (minutes). Noise floor = per hour, the distance between the means of
its even and odd departures (split halves), median over hours; note a half-hour mean is noisier than a whole-hour
mean, so this floor is conservative (it lets more merge). Agglomerative average linkage (mean pairwise hour
distance), merges allowed only between clusters that touch: adjacent hours of a day (23 -> next day's 00) or the
same hour on another day. Claude's cut: merge while the linkage distance <= 1.5 x the noise floor; 1.0x and 2.0x
shown too. Per span: its hours; the error of one departure vs the span mean: per origin, venue hexes reached <= 10
/ <= 20 min, one departure vs the mean over the span's departures, median and p90 absolute % error (origins with a
mean >= 1); share of (pair, departure) whose <= 10 / <= 20 call differs from the pair's majority call in the span
(pairs reached at that cut at least once in the span). The same metrics with each hour as its own span are the
baseline. Span edges vs service steps (gtfs_service_profile.py): descriptive. Pass-cost table for the subject's
opening hours (Places pull 2026-10-10, as reachability_transit_pilot.py), at 4.6 h per departure for all populated
hexes: one departure per span overlapping them vs one per hour vs one per 30-min slot.

Conclusion (run 2026-10-22, autonomous 71st; report only, the schedule is the user's choice): gate mean call 2.96 s,
step 15 min, 568 departures in 25.5 min; 20,118 pairs from all 60 origins. The noise floor (split half, 1.043 min)
is as large as the median distance between hours (0.962; max 2.159): single 1-min departures vary as much inside an
hour as hours differ from each other. So the pre-set cut (1.5x) merges everything but the night (Tue-Fri 00, weekend
00-02) into one span; 2.0x into one. Added after the first run (labelled): 0.707x (floor scaled to whole-hour means)
gives 45 spans whose weekday splits pair hours arbitrarily (Mon 19 + Thu 19, Tue 19 alone): noise, not structure.
The readable cut is 1.0x, 6 spans matching the service profile: weekday 05; weekday 06-20; weekday 21-23 + Sat 08-23
+ Sun 07-23 (evening and weekend together); night; Sat 07 and Sun 06 alone. Error of one departure vs its span mean
is close to the per-hour baseline: per-origin venue hexes reached <= 20 min, median abs error 23.2% for weekday
06-20 vs 17.4% with each hour its own span (the baseline mean holds the departure itself, 1 of 4, so ~20% is the
like-for-like figure); p90 ~60-75% everywhere; pair calls flipping vs the span majority 12-14% at 20 min, 6-8% at
10 (per hour 19.5% / 10.4%). The error of the pass is the single departure, not the span. Pass cost for the
subject's hours (4.6 h per departure): one per 30-min slot every day 63 (~290 h), per hour every day 36 (~166 h),
weekdays only per hour Mon-Fri as one 5 (~23 h); one per 1.0x span 2 (~9 h). Per-origin % errors are inflated by
small counts; the venue-level catchment error (sums over many origins) was not measured (60 origins too few).

Inputs (read only): the frozen jar, transit_pathway_network_v2's 20261016 network files, the hex nodes table, venues
with hex, gtfs_service_profile's service-hours CSV. Self-contained (CLAUDE.md D1). No API calls. One JVM.
Usage: `python transit_time_of_day_spans.py route` then `python transit_time_of_day_spans.py cluster`.
"""
import datetime
import hashlib
import json
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
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
V2_NAME = "transit_pathway_network_v2"
FROZEN_JAR_PATH = PROJECT_ROOT / "outputs" / "r5_patches" / "r5-v7.5.1-r5py-all_transit_r5_patch_connector_p2.jar"
FROZEN_JAR_SHA256 = "62a8f6c1afa2e0a0c86860e336da499f9344e46e6c6d259d9c4824d129e68eb3"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"
VENUES_WITH_HEX_PATH = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT / f"venues_with_hex_ven20260925_{SUBJECT}.csv"
SERVICE_PROFILE_DATE = "20261022"
SERVICE_HOURS_PATH = DIAGNOSTIC_DATA_DIR / f"gtfs_service_profile_{SERVICE_PROFILE_DATE}_service_hours.csv"
NAME = "transit_time_of_day_spans"
ROUTES_DIR = DIAGNOSTIC_DATA_DIR / f"{NAME}_routes_20261022"     # saved routing data, reused, never overwritten

# --- frozen model (TRN-16, as reachability_transit_pilot.py) ----------------------------------------
RELEASE = "20261016"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
R5_MAX_MEMORY = "7G"
SPEED_KMH = 4.143
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
CAP_MIN = 30                                    # RCH-19
GUARD_CLASSES = ["com.conveyal.r5.profile.FastRaptorWorker", "com.conveyal.r5.streets.StreetRouter",
                 "com.conveyal.r5.streets.LinkedPointSet", "com.conveyal.r5.analyst.TravelTimeReducer"]

# --- sample and schedule ---------------------------------------------------------------------------
SUBJECT_LAT, SUBJECT_LON = -37.7687014, 144.9719611
RING_EDGES_KM = [0, 5, 15, 35]
RING_LABELS = ["inner", "mid", "outer"]
ORIGINS_PER_RING = 20
POPULATED_MIN_PERSONS = 1.0
SEED = 20261022
EARTH_RADIUS_M = 6_371_000
CANDIDATE_STEPS_MIN = [5, 10, 15]
FALLBACK_STEP_MIN = 20
GATE_CALLS = 12
ROUTE_BUDGET_MIN = 35                           # projected total for the gate
ROUTE_TIME_BOX_MIN = 35                         # hard wall-clock stop of the routing loop

# --- cluster ---------------------------------------------------------------------------------------
UNREACHED_MIN = CAP_MIN + 1
CUT_FACTORS = [0.707, 1.0, 1.5, 2.0]            # 0.707 = 1/sqrt(2): floor scaled to whole-hour means (added after the first run)
CHOSEN_CUT_FACTOR = 1.5                         # Claude's rule
BAND_CUTS_MIN = [10, 20]
PASS_HOURS_PER_DEPARTURE = 4.6                  # reachability_transit_pilot.py chunk mode
SLOT_MIN = 30                                   # config.HOURS_SLOT_MIN
WEEKDAYS = [0, 1, 2, 3, 4]                      # Monday..Friday
# subject's opening hours (Places pull 2026-10-10; weekday index 0 = Monday): (open, close) as "HH:MM"
SUBJECT_HOURS = {0: [("17:30", "21:00")], 1: [("17:30", "21:00")], 2: [("17:45", "21:00")], 3: [("17:30", "21:00")],
                 4: [("17:30", "21:30")], 5: [("12:30", "15:00"), ("17:00", "21:30")],
                 6: [("12:45", "15:00"), ("17:00", "21:00")]}


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


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


def service_hours():
    hours_df = pd.read_csv(SERVICE_HOURS_PATH, parse_dates=["date"])
    return hours_df[hours_df.is_service_hour][["date", "hour"]].reset_index(drop=True)


def schedule(step_min):
    """One departure per step block of every service hour, at a seeded random minute; even blocks first, then odd."""
    rng = np.random.default_rng([SEED, step_min])
    rows = []
    for hour_row in service_hours().itertuples(index=False):
        hour_start = hour_row.date + pd.Timedelta(hours=hour_row.hour)
        for block in range(60 // step_min):
            minute = block * step_min + int(rng.integers(step_min))
            rows.append({"departure": hour_start + pd.Timedelta(minutes=minute), "date": hour_row.date,
                         "hour": hour_row.hour, "block": block, "half": block % 2})
    schedule_df = pd.DataFrame(rows)
    return schedule_df.sort_values(["half", "block", "departure"], kind="stable").reset_index(drop=True)


def sample_origins():
    import pyogrio
    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False,
                                    columns=["hex_id", "centroid_lat", "centroid_lon", "residents", "workers"])
    hex_df["distance_km"] = haversine_m(SUBJECT_LAT, SUBJECT_LON, hex_df.centroid_lat, hex_df.centroid_lon) / 1000
    hex_df["ring"] = pd.cut(hex_df.distance_km, RING_EDGES_KM, labels=RING_LABELS, right=False)
    populated_df = hex_df[(hex_df.residents.fillna(0) + hex_df.workers.fillna(0) >= POPULATED_MIN_PERSONS)
                          & hex_df.ring.notna()]
    rng = np.random.default_rng(SEED)
    origins_df = pd.concat([members.iloc[rng.choice(len(members), size=ORIGINS_PER_RING, replace=False)]
                            for _, members in populated_df.groupby("ring", observed=True)])
    venue_ids = pd.read_csv(VENUES_WITH_HEX_PATH, usecols=["hex_id"]).hex_id.dropna().astype(np.int64).unique()
    return origins_df, hex_df[hex_df.hex_id.isin(venue_ids)]


def route():
    ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    log_path = ROUTES_DIR / "route.log"

    def log(text):
        print(text, flush=True)
        with open(log_path, "a", encoding="utf-8") as file:
            file.write(f"{datetime.datetime.now():%H:%M:%S} {text}\n")

    check_jar()
    origins_df, venue_df = sample_origins()
    origins_df[["hex_id", "ring", "distance_km", "centroid_lat", "centroid_lon"]].to_csv(ROUTES_DIR / "origins.csv", index=False)
    log(f"origins {len(origins_df)} ({origins_df.ring.value_counts().to_dict()}); venue hexes {len(venue_df):,}")

    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(FROZEN_JAR_PATH)]   # r5py reads these at import
    import geopandas as gpd
    import jpype
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    for name in GUARD_CLASSES:
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == FROZEN_JAR_PATH.resolve(), f"{name} loaded from {location}"
    pbf_path, gtfs = network_paths()
    check_working_copies([pbf_path] + gtfs)
    network = TransportNetwork(pbf_path, gtfs)
    for date in service_hours().date.dt.date.unique():
        assert network.transit_layer.covers(date), f"network does not cover {date}"
    origins = gpd.GeoDataFrame({"id": origins_df.hex_id.to_numpy()}, crs="EPSG:4326",
                               geometry=gpd.points_from_xy(origins_df.centroid_lon, origins_df.centroid_lat))
    destinations = gpd.GeoDataFrame({"id": venue_df.hex_id.to_numpy()}, crs="EPSG:4326",
                                     geometry=gpd.points_from_xy(venue_df.centroid_lon, venue_df.centroid_lat))

    def call(departure):
        tick = time.perf_counter()
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure.to_pydatetime(),
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=datetime.timedelta(minutes=CAP_MIN),
            speed_walking=SPEED_KMH))
        seconds = matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"]
        minutes = np.floor(seconds / 60 + 0.5)
        keep = minutes <= CAP_MIN
        rows_df = pd.DataFrame({"from_id": matrix_df.from_id[keep].astype(np.int64),
                                "to_id": matrix_df.to_id[keep].astype(np.int64),
                                "minutes": minutes[keep].astype(np.int8)})
        return rows_df, time.perf_counter() - tick

    gate_path = ROUTES_DIR / "gate.json"
    if gate_path.exists():
        gate = json.loads(gate_path.read_text())
        log(f"gate reused: step {gate['step_min']} min")
    else:
        hours_df = service_hours()
        rng = np.random.default_rng([SEED, 0])
        picks = hours_df.iloc[rng.choice(len(hours_df), size=GATE_CALLS, replace=False)]
        call_s = []
        for pick in picks.itertuples(index=False):
            departure = pick.date + pd.Timedelta(hours=pick.hour, minutes=int(rng.integers(60)))
            _, wall_s = call(departure)
            call_s.append(wall_s)
            log(f"gate call {departure}: {wall_s:.1f} s")
        mean_s = float(np.mean(call_s))
        projected = {step: mean_s * len(schedule(step)) / 60 for step in CANDIDATE_STEPS_MIN}
        fitting = [step for step in CANDIDATE_STEPS_MIN if projected[step] <= ROUTE_BUDGET_MIN]
        gate = {"call_s": call_s, "mean_call_s": mean_s, "projected_min": projected,
                "step_min": min(fitting) if fitting else FALLBACK_STEP_MIN}
        gate_path.write_text(json.dumps(gate, indent=1))
        log(f"gate: mean call {mean_s:.2f} s; projected min {({k: round(v, 1) for k, v in projected.items()})}; "
            f"step {gate['step_min']} min")

    schedule_df = schedule(gate["step_min"])
    schedule_df.to_csv(ROUTES_DIR / "schedule.csv", index=False)
    start = time.perf_counter()
    done = 0
    for row in schedule_df.itertuples(index=False):
        out_path = ROUTES_DIR / f"dep_{row.departure:%Y%m%d_%H%M}.parquet"
        if out_path.exists():
            done += 1
            continue
        if time.perf_counter() - start > ROUTE_TIME_BOX_MIN * 60:
            log(f"time box {ROUTE_TIME_BOX_MIN} min reached: {done} of {len(schedule_df)} departures done")
            return
        rows_df, wall_s = call(row.departure)
        rows_df.to_parquet(out_path, index=False)
        done += 1
        if done % 25 == 0:
            log(f"{done} / {len(schedule_df)}: last {row.departure} {wall_s:.1f} s, rows {len(rows_df):,}")
    log(f"all {len(schedule_df)} departures done in {(time.perf_counter() - start) / 60:.1f} min")


def load_values():
    """(pairs x departures) array of min(minutes, 31), and the departures' schedule rows."""
    schedule_df = pd.read_csv(ROUTES_DIR / "schedule.csv", parse_dates=["departure", "date"])
    schedule_df["path"] = [ROUTES_DIR / f"dep_{d:%Y%m%d_%H%M}.parquet" for d in schedule_df.departure]
    schedule_df = schedule_df[[path.exists() for path in schedule_df.path]].sort_values("departure").reset_index(drop=True)
    frames = [pd.read_parquet(path).assign(dep=i) for i, path in enumerate(schedule_df.path)]
    rows_df = pd.concat(frames, ignore_index=True)
    pairs = rows_df[["from_id", "to_id"]].drop_duplicates().reset_index(drop=True)
    pair_index = pd.MultiIndex.from_frame(pairs)
    values = np.full((len(pairs), len(schedule_df)), UNREACHED_MIN, dtype=np.float32)
    values[pair_index.get_indexer(pd.MultiIndex.from_frame(rows_df[["from_id", "to_id"]])), rows_df.dep.to_numpy()] = rows_df.minutes
    return pairs, values, schedule_df


def cluster_hours(distance, cells, threshold):
    """Average-linkage merges between touching clusters while the linkage distance <= threshold. Returns labels."""
    n_cells = len(cells)
    day_index = {(c.date, c.hour): i for i, c in enumerate(cells.itertuples(index=False))}
    touch = np.zeros((n_cells, n_cells), dtype=bool)
    for i, cell in enumerate(cells.itertuples(index=False)):
        later = cell.date + pd.Timedelta(hours=cell.hour + 1)
        j = day_index.get((later.normalize(), later.hour))
        if j is not None:
            touch[i, j] = touch[j, i] = True
    same_hour = cells.hour.to_numpy()[:, None] == cells.hour.to_numpy()[None, :]
    touch |= same_hour
    np.fill_diagonal(touch, False)
    members = {i: [i] for i in range(n_cells)}
    adjacent = {i: set(np.flatnonzero(touch[i])) for i in range(n_cells)}
    while True:
        best = None
        for a in members:
            for b in adjacent[a]:
                if b <= a:
                    continue
                link = distance[np.ix_(members[a], members[b])].mean()
                if best is None or link < best[0]:
                    best = (link, a, b)
        if best is None or best[0] > threshold:
            break
        _, a, b = best
        members[a] += members.pop(b)
        adjacent[a] = (adjacent[a] | adjacent.pop(b)) - {a, b}
        for other in adjacent[a]:
            adjacent[other] = (adjacent[other] - {b}) | {a}
    labels = np.empty(n_cells, dtype=int)
    for label, (_, cell_ids) in enumerate(sorted(members.items(), key=lambda item: min(item[1]))):
        labels[cell_ids] = label
    return labels


def span_errors(values, pairs, dep_labels):
    """Per span: one departure vs span mean (per-origin reach <= 10 / <= 20) and call flips vs majority."""
    from_ids = pairs.from_id.to_numpy()
    origin_codes, origin_index = np.unique(from_ids, return_inverse=True)
    records = []
    for label in np.unique(dep_labels):
        span_values = values[:, dep_labels == label]
        record = {"span": label, "departures": span_values.shape[1]}
        for cut in BAND_CUTS_MIN:
            reached = span_values <= cut
            per_origin = np.zeros((len(origin_codes), reached.shape[1]))
            np.add.at(per_origin, origin_index, reached)
            mean = per_origin.mean(axis=1, keepdims=True)
            ok = mean[:, 0] >= 1
            errors = np.abs(per_origin[ok] - mean[ok]) / mean[ok] if ok.any() else np.array([np.nan])
            record[f"reach{cut}_median_abs_pct"] = float(np.nanmedian(errors) * 100)
            record[f"reach{cut}_p90_abs_pct"] = float(np.nanpercentile(errors, 90) * 100)
            ever = reached.any(axis=1)
            majority = reached[ever].mean(axis=1, keepdims=True) > 0.5
            record[f"flip{cut}_share"] = float((reached[ever] != majority).mean()) if ever.any() else np.nan
        records.append(record)
    return pd.DataFrame(records)


def slot_cells(day, opens, closes):
    """Calendar (weekday, hour) and (weekday, slot start minute) cells overlapping [open, close)."""
    def minutes(text):
        hours, mins = text.split(":")
        return int(hours) * 60 + int(mins)
    start, end = minutes(opens), minutes(closes)
    hours = {(day, h) for h in range(start // 60, (end - 1) // 60 + 1)}
    slots = {(day, s) for s in range(start // SLOT_MIN * SLOT_MIN, end, SLOT_MIN)}
    return hours, slots


def cluster():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    run_tag = datetime.date.today().strftime("%Y%m%d")
    out_prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_tag}"
    gate = json.loads((ROUTES_DIR / "gate.json").read_text())
    pairs, values, schedule_df = load_values()
    origins_df = pd.read_csv(ROUTES_DIR / "origins.csv")
    lines = [f"{NAME} cluster run {run_tag}: step {gate['step_min']} min (gate: mean call {gate['mean_call_s']:.2f} s, "
             f"projected {({k: round(v, 1) for k, v in gate['projected_min'].items()})} min); departures routed "
             f"{len(schedule_df)}; pairs kept (<= {CAP_MIN} min at any departure) {len(pairs):,} from "
             f"{pairs.from_id.nunique()} of {len(origins_df)} origins"]

    cells = schedule_df[["date", "hour"]].drop_duplicates().sort_values(["date", "hour"]).reset_index(drop=True)
    cell_of_dep = pd.MultiIndex.from_frame(schedule_df[["date", "hour"]]).map(
        {key: i for i, key in enumerate(zip(cells.date, cells.hour))}.get).to_numpy()
    profiles = np.stack([values[:, cell_of_dep == i].mean(axis=1) for i in range(len(cells))], axis=1)
    distance = np.abs(profiles[:, :, None] - profiles[:, None, :]).mean(axis=0)
    split_half = []
    for i in range(len(cells)):
        in_cell = schedule_df[cell_of_dep == i]
        halves = [values[:, in_cell.index[in_cell.half == h]] for h in (0, 1)]
        if all(half.shape[1] for half in halves):
            split_half.append(np.abs(halves[0].mean(axis=1) - halves[1].mean(axis=1)).mean())
    assert split_half, "no hour has both halves routed: resume the route run first"
    noise_floor = float(np.median(split_half))
    lines.append(f"hour distance (mean |diff| over pairs, min): median {np.median(distance[np.triu_indices(len(cells), 1)]):.3f}, "
                 f"max {distance.max():.3f}; noise floor (median split-half over {len(split_half)} hours) {noise_floor:.3f}")
    cells["weekday"] = cells.date.dt.weekday
    cells_out = cells.copy()

    span_tables = {}
    baseline = span_errors(values, pairs, cell_of_dep)
    lines.append(f"\nbaseline, one span per hour ({len(cells)}): median over hours of reach10 median / p90 abs % "
                 f"{baseline.reach10_median_abs_pct.median():.1f} / {baseline.reach10_p90_abs_pct.median():.1f}; reach20 "
                 f"{baseline.reach20_median_abs_pct.median():.1f} / {baseline.reach20_p90_abs_pct.median():.1f}; flip10 "
                 f"{baseline.flip10_share.median():.3f}; flip20 {baseline.flip20_share.median():.3f}")
    for factor in CUT_FACTORS:
        labels = cluster_hours(distance, cells, factor * noise_floor)
        cells_out[f"span_{factor}"] = labels
        errors_df = span_errors(values, pairs, labels[cell_of_dep])
        errors_df["cells"] = [int((labels == s).sum()) for s in errors_df.span]
        errors_df["members"] = [describe_span(cells[labels == s]) for s in errors_df.span]
        span_tables[factor] = errors_df
        errors_df.to_csv(f"{out_prefix}_spans_{factor}x.csv", index=False)
        lines.append(f"\ncut {factor}x noise floor ({factor * noise_floor:.3f} min){' (Claude rule)' if factor == CHOSEN_CUT_FACTOR else ''}: "
                     f"{len(errors_df)} spans")
        for row in errors_df.itertuples(index=False):
            lines.append(f"  span {row.span}: {row.cells} hours, {row.departures} departures; reach10 abs % median / p90 "
                         f"{row.reach10_median_abs_pct:.1f} / {row.reach10_p90_abs_pct:.1f}; reach20 "
                         f"{row.reach20_median_abs_pct:.1f} / {row.reach20_p90_abs_pct:.1f}; flips 10 / 20 "
                         f"{row.flip10_share:.3f} / {row.flip20_share:.3f}; {row.members}")
    cells_out.to_csv(f"{out_prefix}_cells.csv", index=False)

    # span edges vs service steps
    service_df = pd.read_csv(SERVICE_HOURS_PATH, parse_dates=["date"])
    share = {(d, h): s for d, h, s in zip(service_df.date, service_df.hour, service_df.share_of_peak)}
    labels = cells_out[f"span_{CHOSEN_CUT_FACTOR}"].to_numpy()
    edge_steps, inner_steps = [], []
    for i in range(len(cells) - 1):
        a, b = cells.iloc[i], cells.iloc[i + 1]
        if a.date == b.date and b.hour == a.hour + 1:
            step = abs(share[(b.date, b.hour)] - share[(a.date, a.hour)])
            (edge_steps if labels[i] != labels[i + 1] else inner_steps).append(step)
    lines.append(f"\nspan edges vs service steps (cut {CHOSEN_CUT_FACTOR}x; |change in all-mode active trips, share of "
                 f"peak| between consecutive hours): at edges n {len(edge_steps)} median "
                 f"{np.median(edge_steps) if edge_steps else float('nan'):.3f}; inside spans n {len(inner_steps)} median "
                 f"{np.median(inner_steps) if inner_steps else float('nan'):.3f}")

    # pass cost for the subject's hours
    hour_cells, slot_cells_set = set(), set()
    for day, intervals in SUBJECT_HOURS.items():
        for opens, closes in intervals:
            hours, slots = slot_cells(day, opens, closes)
            hour_cells |= hours
            slot_cells_set |= slots
    cell_lookup = {(w, h): i for i, (w, h) in enumerate(zip(cells.weekday, cells.hour))}
    lines.append(f"\npass cost for the subject's opening hours ({PASS_HOURS_PER_DEPARTURE} h per departure, all populated hexes):")
    mon_thu = [0, 1, 2, 3]
    shared_hours = {(0 if w in mon_thu else w, h) for w, h in hour_cells}
    shared_slots = {(0 if w in mon_thu else w, s) for w, s in slot_cells_set}
    options = [("one per 30-min slot, every day", len(slot_cells_set)),
               ("one per 30-min slot, Mon-Thu as one day", len(shared_slots)),
               ("one per hour, every day", len(hour_cells)),
               ("one per hour, Mon-Thu as one day", len(shared_hours))]
    # weekday-only scope (od-sampling.md Limitations), one weekday standing for all (user's idea, 71st)
    weekday_hours = {(0, h) for w, h in hour_cells if w in WEEKDAYS}
    weekday_slots = {(0, s) for w, s in slot_cells_set if w in WEEKDAYS}
    options += [("weekdays only, one per 30-min slot, Mon-Fri as one day", len(weekday_slots)),
                ("weekdays only, one per hour, Mon-Fri as one day", len(weekday_hours))]
    for factor in CUT_FACTORS:
        spans = {cells_out[f"span_{factor}"].iloc[cell_lookup[c]] for c in hour_cells if c in cell_lookup}
        options.append((f"one per span overlapping them, cut {factor}x", len(spans)))
        spans = {cells_out[f"span_{factor}"].iloc[cell_lookup[c]] for c in hour_cells
                 if c in cell_lookup and c[0] in WEEKDAYS}
        options.append((f"weekdays only, one per span overlapping them, cut {factor}x", len(spans)))
    for label, n_departures in options:
        lines.append(f"  {label}: {n_departures} departures, ~{n_departures * PASS_HOURS_PER_DEPARTURE:.0f} h")

    # figures: span map beside the service profile
    fig, axes = plt.subplots(1, 1 + len(CUT_FACTORS), figsize=(22, 4.5))
    service_grid = service_df.share_of_peak.to_numpy().reshape(7, 24)
    day_labels = [d.strftime("%a %d") for d in sorted(service_df.date.unique())]
    axes[0].imshow(service_grid, aspect="auto", cmap="viridis")
    axes[0].set_title("all-mode active trips, share of peak (gtfs_service_profile)")
    for axis, factor in zip(axes[1:], CUT_FACTORS):
        grid = np.full((7, 24), np.nan)
        grid[cells_out.weekday.to_numpy(), cells_out.hour.to_numpy()] = cells_out[f"span_{factor}"].to_numpy()
        n_spans = int(np.nanmax(grid)) + 1
        axis.imshow(grid, aspect="auto", cmap="tab20" if n_spans <= 20 else "nipy_spectral", interpolation="nearest")
        for (day, hour), value in np.ndenumerate(grid):
            if not np.isnan(value):
                axis.text(hour, day, int(value), ha="center", va="center", fontsize=6)
        axis.set_title(f"spans, cut {factor}x noise floor ({n_spans} spans)")
    for axis in axes:
        axis.set_yticks(range(7), day_labels)
        axis.set_xticks(range(0, 24, 2))
        axis.set_xlabel("hour of day")
    fig.tight_layout()
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(DIAGNOSTIC_IMG_DIR / f"{NAME}_{run_tag}_spans.png", dpi=110)

    summary = "\n".join(lines)
    Path(f"{out_prefix}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


def describe_span(span_cells):
    """'Mon 17-20, Tue 17-20, ...' runs of hours per day."""
    parts = []
    for date, day_df in span_cells.groupby("date", sort=True):
        hours = sorted(day_df.hour)
        runs, run_start = [], hours[0]
        for previous, current in zip(hours, hours[1:] + [None]):
            if current != previous + 1:
                runs.append(f"{run_start}" if run_start == previous else f"{run_start}-{previous}")
                run_start = current
        parts.append(f"{pd.Timestamp(date):%a} {','.join(runs)}")
    return "; ".join(parts)


if __name__ == "__main__":
    {"route": route, "cluster": cluster}[sys.argv[1]]()
