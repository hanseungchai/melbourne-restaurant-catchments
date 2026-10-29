"""How far can transit reach within the pair window? Evidence for the transit draw's distance prefilter.

Claim under test: no origin-venue pair inside the transit pair window (r5py's fastest time over
06:00-24:00 on 2026-10-21, percentile 1, at most 40 min; TRN-10) lies more than 35 km apart (haversine).
Where the pipeline relies on it: config TRANSIT_PREFILTER_KM. The transit pair draw skips r5py for
candidates farther apart than that and counts them out of window, so if the claim fails, the prefilter
drops pairs the window would have kept.
Worst case, not average: origins are every metro train station (location_type 1; express trains give the
longest reach) plus a seeded sample of tram and bus stops, each origin at the stop itself (no walk to
reach it). Destinations are every venue in the venue table the draw uses. The 2026-10-15 session probe
(398 population-weighted hex origins x 2,355 venues) found 28.1 km, which set the 35 km value (x 1.25).
Pre-registered rule (set before the first run, 2026-10-15): SUPPORTED if the longest in-window haversine
over all origins is at most 35 km. Otherwise NOT SUPPORTED: report the longest pairs; the prefilter value
is the user's call. Pairs r5py times at 0 min but more than 1 km apart are artefacts (the session probe
found one at 35.8 km): they are left out of the reach figure and counted separately.
Conclusion (run 2026-10-15): SUPPORTED. 984,980 in-window pairs from 376 origins (226 train stations, 136 bus and
14 tram stops); longest 31.3 km (Sandown Park and Frankston stations, 38-39 min),
99.9th percentile 24.2 km, so 35 km leaves a 12% margin over the worst case. The 376 "artefacts", one per
origin, were all cells with from_id == to_id: r5py returns 0 min there (origin and venue ids both counted
from 0 in that run). Not a network fault; ids are now disjoint here and in functions/transit_window.py.
The other 36 zero-minute pairs are venues within 1 km of their stop.

Inputs (read only): the cleaned GTFS copies in outputs/pt_graph/gtfs_cleaned/ (built from
inputs/gtfs_ptv_20261013, the 2026-10-09 release), the OSM extract in frozen_inputs/osm_extract/, the venue
table outputs/legacy_rebuilds/venues/venues_20260925_expanded.csv.
Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls; r5py
only (~25 min). The reach table is saved data: a rerun reuses the newest one and says so. Results carry
the run date; a same-day rerun replaces that day's results.
"""
import datetime
import io
import sys
import zipfile
from pathlib import Path

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
GTFS_CLEANED_DIR = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED, OTHER_FEEDS = "ptv_metro_train", ["ptv_tram", "ptv_metro_bus"]
VENUES_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
NAME = "transit_window_reach"

# --- values copied from config.py and the record ---------------------------------------------------
R5_MAX_MEMORY = "4G"                           # config.TRANSIT_DRAW_R5_MAX_MEMORY
WINDOW_DATE = datetime.date(2026, 10, 21)      # config.TRANSIT_WINDOW_DATE
WINDOW_HOURS = (6, 24)                         # config.TRANSIT_WINDOW_HOURS, local [start, end)
WINDOW_PERCENTILE = 1                          # config.TRANSIT_WINDOW_PERCENTILE
WINDOW_MIN = 40                                # config.TRANSIT_WINDOW_S / 60
PREFILTER_KM = 35                              # config.TRANSIT_PREFILTER_KM

# --- the run ---------------------------------------------------------------------------------------
N_OTHER_STOPS = 150                            # seeded sample of tram and bus stops, besides all stations
SEED = 20261015
ORIGIN_CHUNK = 50                              # origins per r5py call; keeps the full matrix small
ARTEFACT_MIN_KM = 1.0                          # 0-min pairs farther apart than this are artefacts
N_TOP_PAIRS = 10
STATION_LOCATION_TYPE = "1"
VENUE_ID_COL, VENUE_LAT_COL, VENUE_LON_COL = "place_id", "lat", "lng"
EARTH_RADIUS_M = 6_371_000
M_PER_KM = 1000

sys.argv += ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import

import geopandas as gpd  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from r5py import TransportMode, TransportNetwork, TravelTimeMatrix  # noqa: E402


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres; arrays broadcast."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(a, float)) for a in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def read_stops(feed_name):
    """stops.txt of one cleaned feed, as strings (utf-8-sig drops PTV's byte-order mark)."""
    with zipfile.ZipFile(GTFS_CLEANED_DIR / f"{feed_name}.zip") as zip_file, zip_file.open("stops.txt") as raw:
        stops_df = pd.read_csv(io.TextIOWrapper(raw, encoding="utf-8-sig"), dtype=str)
    stops_df["feed"] = feed_name
    return stops_df


def origins_gdf():
    """Every train station, plus N_OTHER_STOPS seeded tram and bus stops (not stations or entrances)."""
    train_df = read_stops(TRAIN_FEED)
    stations_df = train_df[train_df.location_type == STATION_LOCATION_TYPE]
    other_df = pd.concat([read_stops(name) for name in OTHER_FEEDS], ignore_index=True)
    other_df = other_df[other_df.location_type.fillna("0").isin(["", "0"])]
    other_df = other_df.sample(N_OTHER_STOPS, random_state=SEED)
    stops_df = pd.concat([stations_df, other_df], ignore_index=True)
    stops_df["id"] = range(len(stops_df))
    return gpd.GeoDataFrame(stops_df[["id", "feed", "stop_id", "stop_name"]],
                            geometry=gpd.points_from_xy(stops_df.stop_lon.astype(float),
                                                        stops_df.stop_lat.astype(float)), crs="EPSG:4326")


def build_reach_table(reach_path):
    """In-window pairs (time <= WINDOW_MIN) from every origin to every venue, with their haversine."""
    origins = origins_gdf()
    venues_df = pd.read_csv(VENUES_PATH, usecols=[VENUE_ID_COL, VENUE_LAT_COL, VENUE_LON_COL])
    venues_df = venues_df.drop_duplicates(VENUE_ID_COL).reset_index(drop=True)
    venues_df["id"] = len(origins) + np.arange(len(venues_df))     # r5py gives 0 min where from_id == to_id
    destinations = gpd.GeoDataFrame(venues_df[["id"]], crs="EPSG:4326",
                                    geometry=gpd.points_from_xy(venues_df[VENUE_LON_COL], venues_df[VENUE_LAT_COL]))
    print(f"{len(origins)} origins ({(origins.feed == TRAIN_FEED).sum()} stations), {len(destinations)} venues")

    network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
    departure = datetime.datetime.combine(WINDOW_DATE, datetime.time(WINDOW_HOURS[0]))
    window = datetime.timedelta(hours=WINDOW_HOURS[1] - WINDOW_HOURS[0])
    parts = []
    for start in range(0, len(origins), ORIGIN_CHUNK):
        chunk = origins.iloc[start:start + ORIGIN_CHUNK]
        matrix_df = pd.DataFrame(TravelTimeMatrix(
            network, origins=chunk, destinations=destinations, departure=departure,
            departure_time_window=window, percentiles=[WINDOW_PERCENTILE],
            transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
            max_time=datetime.timedelta(minutes=WINDOW_MIN)))
        time_col = f"travel_time_p{WINDOW_PERCENTILE}"
        parts.append(matrix_df[matrix_df[time_col].notna()].rename(columns={time_col: "travel_time_min"}))
        print(f"  origins {start + len(chunk)}/{len(origins)} done")
    reach_df = pd.concat(parts, ignore_index=True)

    origin_xy = origins.set_index("id")
    reach_df["hav_km"] = haversine_m(origin_xy.geometry.y.loc[reach_df.from_id].to_numpy(),
                                     origin_xy.geometry.x.loc[reach_df.from_id].to_numpy(),
                                     venues_df[VENUE_LAT_COL].to_numpy()[reach_df.to_id - len(origins)],
                                     venues_df[VENUE_LON_COL].to_numpy()[reach_df.to_id - len(origins)]) / M_PER_KM
    reach_df = reach_df.merge(origins.drop(columns="geometry").rename(columns={"id": "from_id"}), on="from_id")
    reach_df["place_id"] = venues_df[VENUE_ID_COL].to_numpy()[reach_df.to_id - len(origins)]
    reach_df.to_csv(reach_path, index=False)
    return reach_df


def main():
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
    run_date = datetime.date.today().strftime("%Y%m%d")
    saved = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_reach.csv"))
    if saved:
        reach_path = saved[-1]
        print(f"reusing saved reach table {reach_path.name} (date in its name)")
        reach_df = pd.read_csv(reach_path)
    else:
        reach_df = build_reach_table(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_reach.csv")

    is_artefact = (reach_df.travel_time_min == 0) & (reach_df.hav_km > ARTEFACT_MIN_KM)
    valid_df = reach_df[~is_artefact]
    longest_km = valid_df.hav_km.max()
    verdict = "SUPPORTED" if longest_km <= PREFILTER_KM else "NOT SUPPORTED"

    per_origin_df = (valid_df.groupby(["from_id", "feed", "stop_name"]).hav_km.max()
                     .rename("max_reach_km").reset_index().sort_values("max_reach_km", ascending=False))
    lines = [f"{NAME} {run_date}: {verdict}",
             f"in-window pairs {len(reach_df):,} from {reach_df.from_id.nunique()} origins; "
             f"artefacts (0 min, > {ARTEFACT_MIN_KM} km) {int(is_artefact.sum())}",
             f"longest in-window haversine {longest_km:.1f} km (rule: <= {PREFILTER_KM} km); "
             f"99.9th pct {valid_df.hav_km.quantile(0.999):.1f} km",
             "longest pairs:",
             valid_df.nlargest(N_TOP_PAIRS, "hav_km")[["stop_name", "feed", "place_id", "travel_time_min",
                                                        "hav_km"]].round(1).to_string(index=False),
             "artefacts:",
             reach_df[is_artefact][["stop_name", "feed", "place_id", "hav_km"]].round(1).to_string(index=False)]
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8")
    per_origin_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_per_origin.csv", index=False)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for feed, feed_df in per_origin_df.groupby("feed"):
        ax.hist(feed_df.max_reach_km, bins=np.arange(0, PREFILTER_KM + 6, 1), alpha=0.6, label=feed)
    ax.axvline(PREFILTER_KM, color="black", linestyle="--", label=f"prefilter {PREFILTER_KM} km")
    ax.set_xlabel(f"longest haversine reached within {WINDOW_MIN} min (km)")
    ax.set_ylabel("origins")
    ax.set_title(f"Transit reach per origin stop, fastest over {WINDOW_HOURS[0]:02d}-{WINDOW_HOURS[1]:02d}, "
                 f"{WINDOW_DATE}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(DIAGNOSTIC_IMG_DIR / f"{NAME}_{run_date}_per_origin.png", dpi=120)


if __name__ == "__main__":
    main()
