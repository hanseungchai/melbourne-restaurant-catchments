"""Transit catchment sensitivity on the frozen model: control models and parameters reverted to default (report only).

Question (user, 2026-10-22, after the 69th autonomous run: sensitivity analysis on the reachability pass, other modes
than drive too; control models, parameters reverted to default; metrics such as population in the catchment).
Where it would be relied on: RCH-13's transit interval and the write-up's robustness section.

Method: transit_catchment_sensitivity.py's census (its saved 2026-10-20 hex list: every non-empty hex within 5.5 km of
the subject, 14,731 hexes; reused, never redrawn), direction hex -> subject, v2 pathways network of release 20261016
(copied loading and stale-copy guard, D1). Departures inside the subject's opening hours (Places pull 2026-10-10;
user: run within the subject's hours): DEPARTURES below (Wednesday dinner, Saturday lunch and dinner). Per variant,
per departure: TravelTimeMatrix transit + walk, 1-min window, p49, cap CAP_MIN; walk-only once per variant; pair
time = min(transit, walk). Units: the patched jars return seconds, rounded to whole minutes half up (SCR-10);
stock R5 returns whole minutes (its own truncation), used as given: part of "stock".
Variants (one JVM process each, run in turn):
  M0 the frozen model (TRN-16): P1 + P3 + P2 jar, walk 4.143 km/h.
  W0 the frozen jar with r5py's default walk speed (3.6 km/h).
  P0 stock R5 (r5py's bundled jar, no patches) at 4.143 km/h.
  D0 all defaults: stock R5 at 3.6 km/h.
Metrics: residents, workers, venues within 10 / 20 min per departure; ratio to M0 per departure (mean, range);
M0's spread across departures (time of day); M0 at cut +-1 min.
Reading: report only (no rule).

Conclusion (run 2026-10-22; report only; 14,731 hexes x 5 departures per variant, ~11-12 min each): M0 within 20
  min: residents 35,815 (Sat 13:00) to 53,082 (Wed 19:00), range / mean 0.38; workers 12,737-21,261 (0.49);
  Saturday ~25% below the weekday evening. Within 10 min the departure matters more: residents 7,163-14,466 (Wed
  19:00 about double the others: one well-timed service). Cut +-1 min at 20: 0.934 / 1.134 residents. Ratios to M0
  (mean [min-max] over departures): W0 (walk 3.6) residents 20 0.855 [0.79-0.89], workers 0.805, residents 10 0.807;
  P0 (stock R5) residents 20 0.957 [0.88-1.10], workers 0.911, but residents 10 1.111 [0.81-1.55]; D0 (all
  defaults) residents 20 0.771, workers 0.686, residents 10 0.705. Caveat: stock R5 returns truncated minutes, M0
  rounds seconds half up, which favours P0 / D0 by ~0.5 min (~5% at 20); part of P0's 10-min excess is that.
  Reading (Claude's): the walk speed is the largest single parameter (-15% at 20 from 4.143 -> 3.6), larger than
  the patches (P0 -4%); departure time moves the catchment more than any model choice (+-20% at 20, x2 at 10), so
  the RCH-14-style time-of-day handling and the choice of departures matter most for bands 1-2.

Inputs (read only): the census hex list, the frozen jar, the v2 network files. Self-contained (CLAUDE.md D1). No API
calls. Usage: `python transit_catchment_variants.py route <variant>` (one per process), `... report`.
"""
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_catchment_variants"
CENSUS_HEXES_PATH = DIAGNOSTIC_DATA_DIR / "transit_catchment_sensitivity_20261020_census_hexes.csv"
V2_NAME = "transit_pathway_network_v2"
RELEASE = "20261016"
V2_PBF_PATH = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{RELEASE}.osm.pbf"
V2_FEED_DIR = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{RELEASE}"
V2_FEED_PATHS = [V2_FEED_DIR / f"ptv_metro_train_{V2_NAME}_{RELEASE}_moved.zip",
                 V2_FEED_DIR / f"ptv_tram_{V2_NAME}_{RELEASE}.zip",
                 V2_FEED_DIR / f"ptv_metro_bus_{V2_NAME}_{RELEASE}.zip"]
FROZEN_JAR_PATH = PROJECT_ROOT / "outputs" / "r5_patches" / "r5-v7.5.1-r5py-all_transit_r5_patch_connector_p2.jar"
FROZEN_JAR_SHA256 = "62a8f6c1afa2e0a0c86860e336da499f9344e46e6c6d259d9c4824d129e68eb3"

# --- values ----------------------------------------------------------------------------------------
SUBJECT_LAT, SUBJECT_LON = -37.7687014, 144.9719611
DEST_ID = -1                                    # disjoint from every hex id (r5py: from_id == to_id reads 0)
R5_MAX_MEMORY = "7G"
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
CAP_MIN = 22                                    # cut 20 + 1 min yardstick, with room for half-up rounding
FROZEN_SPEED_KMH = 4.143                        # TRN-16
DEFAULT_SPEED_KMH = 3.6                         # r5py's default walking speed
VARIANTS = {"M0": (True, FROZEN_SPEED_KMH), "W0": (True, DEFAULT_SPEED_KMH),
            "P0": (False, FROZEN_SPEED_KMH), "D0": (False, DEFAULT_SPEED_KMH)}   # (frozen jar?, walk km/h)
DEPARTURES = [datetime.datetime(2026, 10, 28, 17, 30), datetime.datetime(2026, 10, 28, 19, 0),
              datetime.datetime(2026, 10, 28, 20, 30), datetime.datetime(2026, 10, 31, 13, 0),
              datetime.datetime(2026, 10, 31, 19, 0)]
CUTS_MIN = [10, 20]
YARDSTICK_MIN = 1
SECONDS_PER_MIN = 60
WEIGHTS = ["residents", "workers", "venue_count"]


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def routes_path(variant):
    return DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_routes_{variant}.csv"


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (from transit_catchment_sensitivity)."""
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


def route(variant):
    is_frozen, speed_kmh = VARIANTS[variant]
    path = routes_path(variant)
    assert not path.exists(), f"{path.name} exists (one run per day)"
    sys.argv += ["--max-memory", R5_MAX_MEMORY]
    if is_frozen:
        with open(FROZEN_JAR_PATH, "rb") as file:
            assert hashlib.file_digest(file, "sha256").hexdigest() == FROZEN_JAR_SHA256, "not the frozen jar"
        sys.argv += ["--r5-classpath", str(FROZEN_JAR_PATH)]
    import geopandas as gpd
    import jpype
    from r5py import TransportMode, TransportNetwork, TravelTimeMatrix
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    location = str(jpype.JClass("com.conveyal.r5.profile.FastRaptorWorker").class_.getProtectionDomain()
                   .getCodeSource().getLocation().toURI())
    is_loaded_frozen = Path(location.removeprefix("file:/")).resolve() == FROZEN_JAR_PATH.resolve()
    assert is_loaded_frozen == is_frozen, f"R5 loaded from {location}"
    print(f"{variant}: R5 from {Path(location).name}, walk {speed_kmh} km/h", flush=True)
    check_working_copies([V2_PBF_PATH] + V2_FEED_PATHS)
    network = TransportNetwork(V2_PBF_PATH, V2_FEED_PATHS)
    for day in sorted({d.date() for d in DEPARTURES}):
        assert network.transit_layer.covers(day), f"release {RELEASE} does not cover {day}"
    hexes_df = pd.read_csv(CENSUS_HEXES_PATH)
    origins = gpd.GeoDataFrame({"id": hexes_df.hex_id}, crs="EPSG:4326",
                               geometry=gpd.points_from_xy(hexes_df.centroid_lon, hexes_df.centroid_lat))
    destinations = gpd.GeoDataFrame({"id": [DEST_ID]}, crs="EPSG:4326", geometry=gpd.points_from_xy([SUBJECT_LON], [SUBJECT_LAT]))

    def ttm(departure, modes):
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=modes, max_time=datetime.timedelta(minutes=CAP_MIN), speed_walking=speed_kmh))
        return matrix_df.set_index("from_id")[f"travel_time_p{SINGLE_PERCENTILE}"]

    started = datetime.datetime.now()
    walk = ttm(DEPARTURES[0], [TransportMode.WALK])
    frames = []
    for dep_no, departure in enumerate(DEPARTURES):
        transit = ttm(departure, [TransportMode.TRANSIT, TransportMode.WALK])
        frames.append(pd.DataFrame({"hex_id": transit.index, "dep_no": dep_no, "departure": departure.isoformat(),
                                    "transit": transit.values, "walk": walk.reindex(transit.index).values}))
        print(f"  departure {departure}: {datetime.datetime.now() - started}", flush=True)
    table_df = pd.concat(frames, ignore_index=True)
    table_df["unit"] = "s" if is_frozen else "min"
    table_df.to_csv(path, index=False)
    print(f"{variant} done in {datetime.datetime.now() - started}", flush=True)


def minutes(table_df):
    """Pair time in whole minutes: min(transit, walk); seconds rounded half up (SCR-10); over the cap = inf."""
    time = np.fmin(table_df.transit.to_numpy(float), table_df.walk.to_numpy(float))
    time = np.where(np.isnan(time), np.inf, time)
    if (table_df.unit == "s").all():
        time = np.floor(time / SECONDS_PER_MIN + 0.5)
    return time


def report():
    hexes_df = pd.read_csv(CENSUS_HEXES_PATH)
    totals = {}
    for variant in VARIANTS:
        table_df = pd.read_csv(routes_path(variant)).merge(hexes_df[["hex_id"] + WEIGHTS], on="hex_id")
        table_df["minutes"] = minutes(table_df)
        rows = []
        for dep_no, dep_df in table_df.groupby("dep_no"):
            row = {"dep_no": dep_no, "departure": dep_df.departure.iloc[0]}
            for cut in CUTS_MIN + [CUTS_MIN[1] - YARDSTICK_MIN, CUTS_MIN[1] + YARDSTICK_MIN]:
                for weight in WEIGHTS:
                    row[f"{weight}_{cut}"] = float(dep_df.loc[dep_df.minutes <= cut, weight].sum())
            rows.append(row)
        totals[variant] = pd.DataFrame(rows).set_index("dep_no")
    lines = [f"{NAME} {run_date()}: census {len(hexes_df):,} hexes within 5.5 km; departures "
             + ", ".join(f"{d:%a %H:%M}" for d in DEPARTURES)]
    base = totals["M0"]
    lines.append("M0 totals per departure (residents / workers / venues within 10 | 20 min):")
    for dep_no, row in base.iterrows():
        lines.append(f"  {row.departure}: " + " | ".join(
            " / ".join(f"{row[f'{w}_{c}']:,.0f}" for w in WEIGHTS) for c in CUTS_MIN))
    for weight in WEIGHTS[:2]:
        values = base[f"{weight}_{CUTS_MIN[1]}"]
        lines.append(f"  M0 {weight} within 20 across departures: min {values.min():,.0f}, max {values.max():,.0f} "
                     f"(range / mean {(values.max() - values.min()) / values.mean():.3f}); cut 19 / 21: "
                     f"{(base[f'{weight}_19'] / values).mean():.3f} / {(base[f'{weight}_21'] / values).mean():.3f}")
    lines += ["", "ratio to M0 (mean over departures [min-max]):"]
    for variant in list(VARIANTS)[1:]:
        parts = []
        for cut in CUTS_MIN:
            for weight in WEIGHTS[:2]:
                ratio = totals[variant][f"{weight}_{cut}"] / base[f"{weight}_{cut}"]
                parts.append(f"{weight} {cut} {ratio.mean():.3f} [{ratio.min():.3f}-{ratio.max():.3f}]")
        lines.append(f"  {variant}: " + "; ".join(parts))
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    {"route": route, "report": report}[sys.argv[1]](*sys.argv[2:3])
