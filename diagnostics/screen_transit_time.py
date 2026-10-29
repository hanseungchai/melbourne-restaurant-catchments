"""Walk + transit time from the phone screen's position to every candidate venue (DESIGN.md Q19 (b) extension).

Claim (user, 2026-10-25): the app's list might follow travel time by transit rather than distance (the CBD's
free tram zone makes a far venue on a tram line quicker than a nearer one off it); screen_rank_drivers.py
fits it beside straight-line and walking distance. This script only makes the times. Nothing in the
pipeline relies on it.

Method: R5 TravelTimeMatrix (r5py), one origin (the phone position) to every venue in the venue table within
CANDIDATE_RADIUS_M straight-line; modes transit + walk and walk only; departure the screen's time (Sunday
2026-10-25 12:08) over a WINDOW_MIN window, median; walk speed 4.16 km/h (WLK-1). Stock r5py, not the reach
model's calibrated transit (TRN), which is enough for a "does it matter at all" look. Feeds: the 2026-10-16
release (cleaned copies, unique names: they cover 2026-10-15 to 2026-12-31). Whole minutes. No API calls.

Screens (--screen, default phone): phone (the user's, 105th) and partner_phone (the user's partner's, 106th,
screens 13:34-13:35, departure 13:30; position from screen_position.py). Each has its own centre, radius, departure.

Saved data (reused, never overwritten): diagnostic_data/screen_transit_time_<run date>[_<screen>]_times.csv
(no suffix for phone, the 105th's name)
  place_id, straight_m, transit_min, walk_min

Conclusion: data only; see screen_rank_drivers.py.
"""

import argparse
import datetime
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NAME = "screen_transit_time"
RUN_DATE = datetime.date.today().strftime("%Y%m%d")
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
VENUES_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
GTFS_DIR = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned_20261016"
FEED_NAMES = ["ptv_metro_train_20261016", "ptv_tram_20261016", "ptv_metro_bus_20261016"]

# per screen: phone position (lat, lng), candidate radius (farthest non-sponsored card, m), window start
SCREENS = {
    "phone": {"centre": (-37.810112, 144.951035), "candidate_radius_m": 1400,
              "departure": datetime.datetime(2026, 10, 25, 12, 8), "suffix": ""},   # screens 12:06-12:12
    "partner_phone": {"centre": (-37.809748, 144.951763), "candidate_radius_m": 1300,
                      "departure": datetime.datetime(2026, 10, 25, 13, 30), "suffix": "_partner_phone"},
}
WALK_SPEED_KMH = 4.16                     # WLK-1
WINDOW_MIN = 10
SINGLE_PERCENTILE = 49                    # as walk_only_speed_fit.py (r5py renames a lone p50)
MAX_TIME_MIN = 60
R5_MAX_MEMORY = "7G"
EARTH_RADIUS_M = 6_371_000

_parser = argparse.ArgumentParser()
_parser.add_argument("--screen", default="phone", choices=sorted(SCREENS))
SCREEN = SCREENS[_parser.parse_args().screen]
PHONE_CENTRE = SCREEN["centre"]
CANDIDATE_RADIUS_M = SCREEN["candidate_radius_m"]
DEPARTURE = SCREEN["departure"]
TIMES_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}{SCREEN['suffix']}_times.csv"

sys.argv = sys.argv[:1] + ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
from r5py import TransportMode, TransportNetwork, TravelTimeMatrix  # noqa: E402


def haversine_m(lat1, lng1, lat2, lng2):
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin(np.radians(lat2 - lat1) / 2) ** 2
         + np.cos(phi1) * np.cos(phi2) * np.sin(np.radians(lng2 - lng1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def travel_minutes(network, origins, destinations, modes):
    matrix_df = pd.DataFrame(TravelTimeMatrix(
        network, origins=origins, destinations=destinations, departure=DEPARTURE,
        departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
        transport_modes=modes, max_time=datetime.timedelta(minutes=MAX_TIME_MIN), speed_walking=WALK_SPEED_KMH))
    return matrix_df.set_index("to_id")[f"travel_time_p{SINGLE_PERCENTILE}"]


def main():
    if TIMES_PATH.exists():
        print(f"saved data exists ({TIMES_PATH.name}); reused, nothing routed")
        return
    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "lat", "lng"]).drop_duplicates("place_id")
    venues_df["straight_m"] = haversine_m(*PHONE_CENTRE, venues_df["lat"], venues_df["lng"])
    venues_df = venues_df[venues_df["straight_m"] <= CANDIDATE_RADIUS_M].reset_index(drop=True)
    origins = gpd.GeoDataFrame({"id": [-1]}, crs="EPSG:4326",
                               geometry=gpd.points_from_xy([PHONE_CENTRE[1]], [PHONE_CENTRE[0]]))
    destinations = gpd.GeoDataFrame({"id": venues_df.index}, crs="EPSG:4326",
                                    geometry=gpd.points_from_xy(venues_df["lng"], venues_df["lat"]))
    started = time.monotonic()
    network = TransportNetwork(PBF_PATH, [GTFS_DIR / f"{name}.zip" for name in FEED_NAMES])
    print(f"network built in {time.monotonic() - started:.0f} s; {len(venues_df)} destinations", flush=True)
    venues_df["transit_min"] = travel_minutes(network, origins, destinations, [TransportMode.TRANSIT, TransportMode.WALK])
    venues_df["walk_min"] = travel_minutes(network, origins, destinations, [TransportMode.WALK])
    venues_df[["place_id", "straight_m", "transit_min", "walk_min"]].to_csv(TIMES_PATH, index=False)
    is_faster = venues_df["transit_min"] < venues_df["walk_min"]
    print(f"done in {time.monotonic() - started:.0f} s; transit faster than walking for {is_faster.sum()} of "
          f"{len(venues_df)} (median saving where faster {(venues_df['walk_min'] - venues_df['transit_min'])[is_faster].median()} min)")


if __name__ == "__main__":
    main()
