"""Does a faster walk close TTM's late arrivals against Google?

Claim under test (concepts/walk.md WLK-1 lead, concepts/transit.md T7 (e); from
diagnostics/transit_di_raw_states.py run 2, 2026-10-17): where TravelTimeMatrix (TTM, 1-min window) arrives
LATE_GAP_MIN or more after Google's earliest in-scope arrival, TTM's walk to the first stop is too slow
(r5py's default speed_walking 3.6 km/h; nothing in the pipeline sets it), so it misses a vehicle Google
just catches. Google's own answers walk at about 4.2 km/h (median walk distance / walk time of the 2,625
default routes of the 2026-10-17 fetch: 4.21 on transit routes with >= 300 m of walk, 4.24 on walk-only
routes; Google's public figure is 5 km/h).
Where the pipeline relies on it: the walk-speed fit (WLK-1, WLK-2: the speed passed into R5) and TTM as
TRN-6's validation router.

Method: the 100 pairs of transit_di_window.py's sample; the test set is the 25 with TTM - Google >=
LATE_GAP_MIN, the controls the 53 with |TTM - Google| <= ARRIVAL_TOLERANCE_MIN (both from run 2's
definitions: TTM's t1_min from transit_di_window.py's results, Google's earliest in-scope or name-mismatch
arrival in whole minutes from the requested minute). TTM rerun at a 1-min window from the drawn minute at
each speed in SPEEDS_KMH. 3.6 km/h is a sanity check: it must reproduce t1_min on all 78.
Rule (set with the user before the run, 2026-10-17), judged at PRIMARY_SPEED_KMH (Google's measured speed):
  SUPPORTED  if >= MIN_LATE_CLOSED of the 25 come within ARRIVAL_TOLERANCE_MIN of Google AND
             >= MIN_CONTROL_SHARE of the 53 controls stay within ARRIVAL_TOLERANCE_MIN;
  PARTIAL    if >= MIN_LATE_CLOSED of the 25 shrink their gap by >= ARRIVAL_TOLERANCE_MIN but fewer
             than MIN_LATE_CLOSED come within it;
  REFUTED    otherwise.
5.0 km/h (Google's public figure) is reported, not judged. Also per pair: Google's walk_m and leave wait;
controls turned early (TTM - Google < -ARRIVAL_TOLERANCE_MIN). Small sample: a pass is a lead for the
WLK-1 fit, not the fit.

Conclusion (run 2026-10-17): PARTIAL at 4.2 km/h. Sanity: 3.6 km/h reproduces t1_min on 78 of 78. At 4.2
the late gap shrinks on 22 of 25 (mean +5.88 -> +2.40 min) but only 10 come within 1 min; controls hold
49 of 53 (0.92; 4 turn 2 min early, the rest drift by up to 1 min, mostly earlier). At 5.0 (reported only)
15 of 25 late close, but controls hold only 34 of 53 (19 early, down to -17): 5.0 overshoots. Walk speed is
a real part of the late gap, not all of it: 5 pairs stay 6+ min late at 4.2 and close only at 5.0 (25587,
25486, 22087, 25455, 18359), and 3 overshoot at 4.2 (26611 -6, 18014 -4, 11311 -2: TTM finds a trip Google
doesn't offer). Untested: whether those 5 hinge on walk distance (R5's path or stop linking vs Google's)
rather than speed.

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release), the
OSM extract in frozen_inputs/osm_extract/, the transit pair draw and Google route table in
outputs/transit_validation/, transit_di_window.py's results in diagnostics/diagnostic_data/ (newest).
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls; r5py
only. The per-pair table is saved data: a rerun reuses the newest one and says so. Results carry the run
date; a same-day rerun replaces that day's results.
"""
import datetime
import sys
from pathlib import Path

import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
GTFS_CLEANED_DIR = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
GOOGLE_ROUTES_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
WINDOW_RESULTS_GLOB = "transit_di_window_*_results.csv"     # transit_di_window.py's per-pair results (sample, TTM)
NAME = "transit_walk_speed_lead"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "7G"                           # as transit_di_window.py
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_MIN = 1                                 # config.TRANSIT_VALIDATION_WINDOW_MIN
MAX_TIME_MIN = 90                              # as transit_di_window.py
SINGLE_PERCENTILE = 49                         # as transit_di_window.py (r5py renames a lone p50)
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]   # TRN-11: a name mismatch is the same line under another short name
SECONDS_PER_MIN = 60
MIN_PER_HOUR = 60
LOCAL_TIMEZONE = "Australia/Melbourne"

# --- test ------------------------------------------------------------------------------------------
BASELINE_SPEED_KMH = 3.6                       # r5py's default; must reproduce t1_min
PRIMARY_SPEED_KMH = 4.2                        # Google's measured walk speed (docstring); the judged speed
PUBLIC_SPEED_KMH = 5.0                         # Google's public figure; reported only
SPEEDS_KMH = [BASELINE_SPEED_KMH, PRIMARY_SPEED_KMH, PUBLIC_SPEED_KMH]
ARRIVAL_TOLERANCE_MIN = 1
LATE_GAP_MIN = 3                               # test set: TTM later than Google by at least this
MIN_LATE_CLOSED = 15                           # of the 25 late pairs
MIN_CONTROL_SHARE = 0.90                       # of the 53 controls

sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import

import geopandas as gpd  # noqa: E402
from r5py import TransportMode, TransportNetwork, TravelTimeMatrix  # noqa: E402


def departure_of(pair):
    """The pair's drawn minute on WINDOW_DATE."""
    return datetime.datetime.combine(WINDOW_DATE, datetime.time()) + datetime.timedelta(minutes=int(pair.dep_min_of_day))


def ttm_min(network, pair, speed_walking_kmh):
    """TTM travel time (whole minutes) for one pair at a 1-min window from its drawn minute."""
    origins = gpd.GeoDataFrame({"id": [0]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.origin_lon], [pair.origin_lat]))
    destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326", geometry=gpd.points_from_xy([pair.dest_lon], [pair.dest_lat]))
    matrix_df = pd.DataFrame(TravelTimeMatrix(
        network, origins=origins, destinations=destinations, departure=departure_of(pair),
        departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=datetime.timedelta(minutes=MAX_TIME_MIN),
        speed_walking=speed_walking_kmh))
    return matrix_df[f"travel_time_p{SINGLE_PERCENTILE}"].iloc[0]


def google_earliest_df():
    """Google's earliest in-scope arrival per pair, whole minutes from the requested minute (as
    transit_di_raw_states.py run 2)."""
    routes_df = pd.read_csv(GOOGLE_ROUTES_PATH)
    routes_df = routes_df[routes_df.route_scope.isin(GOOGLE_SCOPES)]
    earliest_df = routes_df.loc[routes_df.groupby("draw_no").arrival_from_request_s.idxmin()]
    return pd.DataFrame({"draw_no": earliest_df.draw_no.values,
                         "google_min": (earliest_df.arrival_from_request_s // SECONDS_PER_MIN).values,
                         "google_leave_wait_s": earliest_df.leave_wait_s.values,
                         "google_walk_m": earliest_df.walk_m.values})


def speed_column(speed_kmh):
    return f"ttm_min_{speed_kmh:.1f}".replace(".", "_")


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    window_path = sorted(DIAGNOSTIC_DATA_DIR.glob(WINDOW_RESULTS_GLOB))[-1]
    window_df = pd.read_csv(window_path)[["draw_no", "t1_min"]]
    pairs_df = window_df.merge(google_earliest_df(), on="draw_no", how="left")
    pairs_df["gap_before"] = pairs_df.t1_min - pairs_df.google_min
    pairs_df["group"] = None
    pairs_df.loc[pairs_df.gap_before >= LATE_GAP_MIN, "group"] = "late"
    pairs_df.loc[pairs_df.gap_before.abs() <= ARRIVAL_TOLERANCE_MIN, "group"] = "control"
    pairs_df = pairs_df[pairs_df.group.notna()]
    print(f"sample and t1_min from {window_path.name}; {(pairs_df.group == 'late').sum()} late, "
          f"{(pairs_df.group == 'control').sum()} controls")

    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_pairs.csv"))
    if saved:
        print(f"reusing saved table {saved[-1].name}")
        speeds_df = pd.read_csv(saved[-1])
    else:
        network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
        draw_df = pd.read_csv(PAIRS_PATH).set_index("draw_no").loc[pairs_df.draw_no]
        rows = []
        for pair in draw_df.itertuples():
            row = {"draw_no": pair.Index}
            for speed_kmh in SPEEDS_KMH:
                row[speed_column(speed_kmh)] = ttm_min(network, pair, speed_kmh)
            print(f"  {row}", flush=True)
            rows.append(row)
        speeds_df = pd.DataFrame(rows)
        speeds_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_pairs.csv", index=False)

    table_df = pairs_df.merge(speeds_df, on="draw_no")
    is_late = table_df.group == "late"
    is_control = table_df.group == "control"
    baseline = table_df[speed_column(BASELINE_SPEED_KMH)]
    is_reproduced = baseline == table_df.t1_min
    lines = [f"{NAME} {run_date}: {int(is_late.sum())} late pairs (TTM - Google >= {LATE_GAP_MIN}), "
             f"{int(is_control.sum())} controls (|TTM - Google| <= {ARRIVAL_TOLERANCE_MIN}); 1-min window; "
             f"whole minutes from Google's requested minute; small-sample lead, not the WLK-1 fit",
             f"sanity: TTM at {BASELINE_SPEED_KMH} km/h reproduces t1_min on {int(is_reproduced.sum())} of {len(table_df)}"
             + ("" if is_reproduced.all() else f" (not on {table_df.draw_no[~is_reproduced].tolist()})")]
    for speed_kmh in SPEEDS_KMH:
        gap = table_df[speed_column(speed_kmh)] - table_df.google_min
        table_df[f"gap_{speed_column(speed_kmh)[8:]}"] = gap
        late_gap, control_gap = gap[is_late], gap[is_control]
        n_late_within = int((late_gap.abs() <= ARRIVAL_TOLERANCE_MIN).sum())
        n_late_shrunk = int((table_df.gap_before[is_late] - late_gap >= ARRIVAL_TOLERANCE_MIN).sum())
        n_control_within = int((control_gap.abs() <= ARRIVAL_TOLERANCE_MIN).sum())
        n_control_early = int((control_gap < -ARRIVAL_TOLERANCE_MIN).sum())
        lines.append(f"{speed_kmh} km/h: late within tol {n_late_within} of {int(is_late.sum())}, gap shrunk by >= "
                     f"{ARRIVAL_TOLERANCE_MIN} on {n_late_shrunk}, late gap mean {late_gap.mean():.2f} "
                     f"(distribution {late_gap.value_counts().sort_index().to_dict()}); controls within tol "
                     f"{n_control_within} of {int(is_control.sum())} ({n_control_within / is_control.sum():.2f}), "
                     f"turned early {n_control_early}, control gap distribution {control_gap.value_counts().sort_index().to_dict()}")
        if speed_kmh == PRIMARY_SPEED_KMH:
            is_control_held = n_control_within >= MIN_CONTROL_SHARE * is_control.sum()
            if n_late_within >= MIN_LATE_CLOSED and is_control_held:
                verdict = "SUPPORTED"
            elif n_late_shrunk >= MIN_LATE_CLOSED and n_late_within < MIN_LATE_CLOSED:
                verdict = "PARTIAL"
            else:
                verdict = "REFUTED"
            verdict_line = (f"VERDICT at {PRIMARY_SPEED_KMH} km/h: {verdict} (late within tol {n_late_within}, need "
                            f"{MIN_LATE_CLOSED}; shrunk {n_late_shrunk}; controls held {n_control_within}, need "
                            f">= {MIN_CONTROL_SHARE:.0%} of {int(is_control.sum())})")
    lines.insert(2, verdict_line)
    lines.append("late pairs:")
    lines.append(table_df[is_late].drop(columns=["group"]).to_string(index=False))
    lines.append("controls that moved at any speed:")
    moved = (table_df[[speed_column(s) for s in SPEEDS_KMH]].nunique(axis=1) > 1) & is_control
    lines.append(table_df[moved].drop(columns=["group"]).to_string(index=False))
    summary = "\n".join(lines)
    print(summary)
    with open(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt", "w", encoding="utf-8", newline="\n") as file:
        file.write(summary)


if __name__ == "__main__":
    main()
