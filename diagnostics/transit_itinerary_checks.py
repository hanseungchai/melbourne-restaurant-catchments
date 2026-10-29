"""Can r5py's DetailedItineraries give per-route detail for validation, and what do ride-cap matrices cost?

Claims under test (concepts/transit.md T7 (e), preconditions for TRN-6 validation and the T7 ride cap):
(A) r5py's DetailedItineraries (DI) can report Google-comparable routes (legs, boardings, times) for a
    validation pair. Planned test (pre-registered 2026-10-16): DI's earliest arrival within 1 min of
    TravelTimeMatrix (TTM) for 20 pairs at a one-minute departure window (config
    TRANSIT_VALIDATION_WINDOW_MIN). That test could not run: DI ran out of Java heap on the first pair at
    4G and at 7G with a one-minute window (also with max_time 45-90 min and max_time_walking 10-15 min);
    log kept as diagnostic_data/transit_itinerary_checks_20261016_oom_7g_1min.log. At r5py's default
    ten-minute window DI finishes (~8 s per pair), so (A) is tested there instead, for a defect seen in
    the session probe: r5py caches each stop's access and egress walk legs (r5py/r5/trip_planner.py,
    access_legs_by_stop / egress_legs_by_stop) and overwrites their departure and arrival times for every
    option, so all options carry the last option's walk times.
    Rule for the revised check (set before its first run, 2026-10-16): DEFECT CONFIRMED if, on any pair
    with at least 2 transit options whose boarding times differ, every option reports the same egress
    arrival. R5's own route count per departure minute (the router call copied from r5py) is reported
    alongside: r5py keeps one route per minute (dict keyed by departure time, L245-250).
(B) Timing: the T7 bulk pass would route 4-5 matrices (walk only, at most 1, 2, 3 boardings, and r5py's
    default 8). Time each on one small batch at one minute (no rule; seconds per matrix). Also reported:
    the boardings of each pair's fastest trip, read from the caps alone as the smallest cap whose time
    equals the default's, which would replace DI's boarding count in TRN-6 if (A) fails.
Where the pipeline relies on it: TRN-6 validation planned to read legs and boardings from DI while times
come from TTM; T7 (a) chooses the ride cap per pair.

Pairs: N_PAIRS exploration pairs (seeded), each at its drawn minute of day on WINDOW_DATE, a Wednesday
inside the 2026-10-09 release (the fetch date is assigned later, TRN-7; any covered weekday serves).
Timing batch: the first BATCH_N_ORIGINS exploration origins to all their venues, at one departure time.

Conclusion (run 2026-10-16): (A) the planned one-minute test is NOT TESTABLE: DI runs out of heap there.
The revised rule gives DEFECT NOT CONFIRMED: on the 4 testable pairs (of 5) options never all share one
egress arrival. Weaker sign, not the rule: every testable pair shows fewer distinct egress arrivals (2-3)
than distinct boarding sequences (3-5), as the cache would cause wherever options share an egress stop;
unproven. DI returns 52-61 options for a 10-min window, but only 1-5 distinct boarding sequences, and R5
holds up to 35 routes at one departure time before r5py keeps one. DI is not usable for TRN-6 as
planned. (B) Ride caps are cheap: ~1 s per matrix (50 origins x 64 venues, one minute), all five within
0.7-1.0 s. On the batch's 64 own pairs at 12:00 (39 reached within 40 min), caps 2 and 3 equal the
default on every reached pair; cap 1 is slower on 4. Boardings of the fastest trip read from the caps:
0 on 5 pairs, 1 on 24, 2 on 10, none needing 3 (25 not reached at that minute).

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release), the
OSM extract in frozen_inputs/osm_extract/, the transit pair draw and split in outputs/transit_validation/.
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls; r5py
only (a few minutes). The per-pair, timing and cap tables are saved data: a rerun reuses the newest ones
and says so. Results carry the run date; a same-day rerun replaces that day's results.
"""
import datetime
import sys
import time
from pathlib import Path

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
GTFS_CLEANED_DIR = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_itinerary_checks"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # 4G (config.TRANSIT_DRAW_R5_MAX_MEMORY) ran out in DetailedItineraries (2026-10-16)
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
VALIDATION_WINDOW_MIN = 1                      # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 40                              # config.TRANSIT_WINDOW_S / 60

# --- the run ---------------------------------------------------------------------------------------
N_PAIRS = 5                                    # check (A)
SEED = 20261016
DI_WINDOW_MIN = 10                             # r5py's default; DI runs out of heap at one minute
PERCENTILE = 1                                 # any percentile but 50 (r5py renames p50): one minute gives one value
BATCH_N_ORIGINS = 50                           # check (B): exploration origins in the timing batch
BATCH_DEPARTURE = datetime.time(12, 0)         # check (B): one departure time for the whole batch
RIDE_CAPS = [0, 1, 2, 3, 8]                    # 0 = walk only (transport_modes WALK); 8 = r5py's default
DEFAULT_RIDE_CAP = 8
SECONDS_PER_MIN = 60

sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from r5py import DetailedItineraries, TransportMode, TransportNetwork, TravelTimeMatrix  # noqa: E402
from r5py.r5.regional_task import RegionalTask  # noqa: E402
from r5py.r5.trip_planner import TripPlanner  # noqa: E402
import com.conveyal.r5  # noqa: E402  (the Java package; importable once r5py has started the JVM)


def points_gdf(ids, lats, lons):
    """r5py origins or destinations: an id column and point geometry."""
    return gpd.GeoDataFrame({"id": np.asarray(ids)}, crs="EPSG:4326", geometry=gpd.points_from_xy(lons, lats))


def exploration_pairs_df():
    """Exploration pairs (training half, fetched first), with their drawn departure minute."""
    pairs_df = pd.read_csv(PAIRS_PATH)
    split_df = pd.read_csv(SPLIT_PATH)
    exploration_draws = split_df.loc[split_df.is_exploration, "draw_no"]
    return pairs_df[pairs_df.draw_no.isin(exploration_draws)].reset_index(drop=True)


def r5_routes_per_minute(network, itineraries_request):
    """R5's McRAPTOR routes per departure minute, before r5py's dict keeps one; copied from
    r5py/r5/trip_planner.py TripPlanner.transit_paths (r5py 1.1.7). Returns (minutes with a route,
    most routes at one minute, suboptimalMinutes)."""
    planner = TripPlanner(network, itineraries_request)
    suboptimal_minutes = max(itineraries_request._regional_task.suboptimalMinutes, 0)

    def list_supplier_callback(departure_time):
        return com.conveyal.r5.profile.SuboptimalDominatingList(suboptimal_minutes)

    router = com.conveyal.r5.profile.McRaptorSuboptimalPathProfileRouter(
        network, itineraries_request, planner._transit_access_times, planner._transit_egress_times,
        list_supplier_callback, None, True)
    router.route()
    counts = [len(list(states)) for states in router.finalStatesByDepartureTime.values()]
    return sum(count > 0 for count in counts), max(counts, default=0), suboptimal_minutes


def check_one_pair(network, pair):
    """DI options at DI_WINDOW_MIN: how many, how many distinct boarding sequences, how many distinct
    egress arrivals; R5's own routes per minute."""
    departure = datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(
        minutes=int(pair.dep_min_of_day))
    origin = points_gdf([0], [pair.origin_lat], [pair.origin_lon])
    destination = points_gdf([1], [pair.dest_lat], [pair.dest_lon])    # ids disjoint: r5py gives 0 where equal
    settings = dict(departure=departure, departure_time_window=datetime.timedelta(minutes=DI_WINDOW_MIN),
                    transport_modes=[TransportMode.TRANSIT, TransportMode.WALK])

    di_df = pd.DataFrame(DetailedItineraries(network, origins=origin, destinations=destination, **settings))
    di_df["arrival"] = di_df.departure_time + di_df.travel_time
    is_ride = di_df.route_id.notna() & (di_df.route_id != "")
    boardings = (di_df[is_ride].assign(board=lambda df: df.route_id + "@" + df.departure_time.astype(str))
                 .groupby("option").board.agg("|".join))
    egress_arrivals = di_df[di_df.option.isin(boardings.index)].groupby("option").arrival.max()

    regional_task = RegionalTask(network, origin=origin.geometry.iloc[0], destinations=destination, **settings)
    regional_task._regional_task.toLat, regional_task._regional_task.toLon = pair.dest_lat, pair.dest_lon
    n_minutes, max_routes_per_minute, suboptimal_minutes = r5_routes_per_minute(network, regional_task)

    row = {"draw_no": pair.draw_no, "haversine_m": round(pair.haversine_m), "departure": departure,
           "di_n_options": di_df.option.nunique(), "di_n_transit_options": len(boardings),
           "di_n_distinct_boardings": boardings.nunique(), "di_n_distinct_egress_arrivals": egress_arrivals.nunique(),
           "r5_minutes_with_route": n_minutes, "r5_max_routes_per_minute": max_routes_per_minute,
           "suboptimal_minutes": suboptimal_minutes}
    print(f"  {row}", flush=True)
    return row


def time_ride_caps(network, pairs_df):
    """Seconds per matrix for each ride cap on one batch, plus each cap's times for the batch's own pairs."""
    batch_df = pairs_df[pairs_df.origin_hex.isin(pairs_df.origin_hex.unique()[:BATCH_N_ORIGINS])]
    origins_df = batch_df.drop_duplicates("origin_hex")
    venues_df = batch_df.drop_duplicates("place_id").reset_index(drop=True)
    venue_ids = origins_df.origin_hex.max() + 1 + venues_df.index.to_numpy()
    origins = points_gdf(origins_df.origin_hex, origins_df.origin_lat, origins_df.origin_lon)
    destinations = points_gdf(venue_ids, venues_df.dest_lat, venues_df.dest_lon)
    cells_df = batch_df[["draw_no", "origin_hex"]].assign(
        to_id=pd.Series(venue_ids, index=venues_df.place_id).loc[batch_df.place_id].to_numpy())
    departure = datetime.datetime.combine(WINDOW_DATE, BATCH_DEPARTURE)

    timing_rows = []
    for cap in RIDE_CAPS:
        modes = [TransportMode.WALK] if cap == 0 else [TransportMode.TRANSIT, TransportMode.WALK]
        started = time.perf_counter()
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=VALIDATION_WINDOW_MIN), percentiles=[PERCENTILE],
            transport_modes=modes, max_public_transport_rides=max(cap, 1),
            max_time=datetime.timedelta(minutes=MAX_TIME_MIN)))
        seconds = time.perf_counter() - started
        own_df = cells_df.merge(matrix_df, left_on=["origin_hex", "to_id"], right_on=["from_id", "to_id"])
        cells_df[f"t{cap}_min"] = own_df[f"travel_time_p{PERCENTILE}"].to_numpy()
        timing_rows.append({"ride_cap": cap, "seconds": round(seconds, 1), "n_origins": len(origins),
                            "n_destinations": len(destinations), "n_cells": len(origins) * len(destinations),
                            "n_reached_cells": int(matrix_df[f"travel_time_p{PERCENTILE}"].notna().sum())})
        print(f"  ride cap {cap}: {seconds:.1f} s")
    return pd.DataFrame(timing_rows), cells_df


def fastest_boardings(caps_df):
    """Per pair, the smallest ride cap whose time equals the default cap's: the boardings of r5py's
    fastest trip (NaN where the default reaches nothing)."""
    default_col = f"t{DEFAULT_RIDE_CAP}_min"
    boardings = pd.Series(np.nan, index=caps_df.index)
    for cap in reversed(RIDE_CAPS):
        boardings[caps_df[f"t{cap}_min"] == caps_df[default_col]] = cap
    return boardings


def main():
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_date = datetime.date.today().strftime("%Y%m%d")
    saved_pairs = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_pairs.csv"))
    saved_timing = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_timing.csv"))
    saved_caps = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_caps.csv"))
    if saved_pairs and saved_timing and saved_caps:
        print(f"reusing saved tables {saved_pairs[-1].name}, {saved_timing[-1].name}, {saved_caps[-1].name}")
        checks_df, timing_df, caps_df = (pd.read_csv(p[-1]) for p in (saved_pairs, saved_timing, saved_caps))
    else:
        pairs_df = exploration_pairs_df()
        network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        sample_df = pairs_df.sample(N_PAIRS, random_state=SEED)
        checks_df = pd.DataFrame([check_one_pair(network, pair) for pair in sample_df.itertuples()])
        checks_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_pairs.csv", index=False)
        timing_df, caps_df = time_ride_caps(network, pairs_df)
        timing_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_timing.csv", index=False)
        caps_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_caps.csv", index=False)

    is_testable = (checks_df.di_n_transit_options >= 2) & (checks_df.di_n_distinct_boardings >= 2)
    is_defect = is_testable & (checks_df.di_n_distinct_egress_arrivals == 1)
    verdict_a = "DEFECT CONFIRMED" if is_defect.any() else "DEFECT NOT CONFIRMED"
    default_col = f"t{DEFAULT_RIDE_CAP}_min"
    cap_lines = []
    for cap in RIDE_CAPS[:-1]:
        cap_col = f"t{cap}_min"
        is_both = caps_df[[cap_col, default_col]].notna().all(axis=1)
        cap_lines.append(f"  cap {cap}: reached {int(caps_df[cap_col].notna().sum())}/{len(caps_df)} own pairs; "
                         f"slower than default on {int((caps_df[cap_col] > caps_df[default_col])[is_both].sum())}, "
                         f"equal on {int((caps_df[cap_col] == caps_df[default_col])[is_both].sum())}")
    lines = [f"{NAME} {run_date}",
             f"(A) DI at a {DI_WINDOW_MIN}-min window: {verdict_a}: {int(is_defect.sum())} of {int(is_testable.sum())} "
             f"testable pairs report one egress arrival across differing boardings (suboptimalMinutes = "
             f"{checks_df.suboptimal_minutes.iloc[0]}; R5 routes per minute at most "
             f"{checks_df.r5_max_routes_per_minute.max()})",
             checks_df.drop(columns=["departure", "suboptimal_minutes"]).round(2).to_string(index=False),
             f"(B) timing, {VALIDATION_WINDOW_MIN}-min window at {BATCH_DEPARTURE:%H:%M}, max_time {MAX_TIME_MIN} min:",
             timing_df.to_string(index=False),
             f"  own pairs in the batch ({len(caps_df)}), each cap vs the default ({DEFAULT_RIDE_CAP}):",
             *cap_lines,
             "  boardings of the fastest trip (smallest cap equal to the default), own pairs:",
             "  " + str(fastest_boardings(caps_df).value_counts(dropna=False).sort_index().to_dict())]
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()
