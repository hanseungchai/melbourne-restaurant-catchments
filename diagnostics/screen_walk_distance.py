"""Walking distance from the phone screen's position to every candidate venue (DESIGN.md Q19 (b) extension).

Claim (user, 2026-10-25): whether the app's list follows walking distance or straight-line distance may
matter; screen_rank_drivers.py fits both and compares. This script only makes the distances. Nothing in
the pipeline relies on it.

Method: R5 walk-only DetailedItineraries (r5py), one origin (the phone position, trilaterated from card
distances) to every venue in the venue table within CANDIDATE_RADIUS_M straight-line, pairwise; path length
summed over legs. Walk speed 4.16 km/h (WLK-1; length barely depends on it). OSM extract as
walk_only_speed_fit.py; no GTFS (walk only). No API calls.

Screens (--screen, default phone): phone (the user's, 105th) and partner_phone (the user's partner's, 106th;
position from screen_position.py). Each screen has its own centre and candidate radius.

Saved data (reused, never overwritten): diagnostic_data/screen_walk_distance_<run date>[_<screen>]_walk.csv
(no suffix for phone, the 105th's name)
  place_id, straight_m, walk_m, walk_s

Conclusion: data only; see screen_rank_drivers.py.
"""

import argparse
import datetime
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NAME = "screen_walk_distance"
RUN_DATE = datetime.date.today().strftime("%Y%m%d")
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
VENUES_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"

# per screen: phone position (lat, lng) and candidate radius (farthest non-sponsored card, m)
SCREENS = {
    "phone": {"centre": (-37.810112, 144.951035), "candidate_radius_m": 1400, "suffix": ""},
    "partner_phone": {"centre": (-37.809748, 144.951763), "candidate_radius_m": 1300, "suffix": "_partner_phone"},
}
WALK_SPEED_KMH = 4.16                     # WLK-1
R5_MAX_MEMORY = "7G"                      # as walk_only_speed_fit.py
DEPARTURE = datetime.datetime(2026, 10, 25, 12)   # walk only: time does not matter
EARTH_RADIUS_M = 6_371_000

_parser = argparse.ArgumentParser()
_parser.add_argument("--screen", default="phone", choices=sorted(SCREENS))
SCREEN = SCREENS[_parser.parse_args().screen]
PHONE_CENTRE = SCREEN["centre"]
CANDIDATE_RADIUS_M = SCREEN["candidate_radius_m"]
WALK_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}{SCREEN['suffix']}_walk.csv"

sys.argv = sys.argv[:1] + ["--max-memory", R5_MAX_MEMORY]    # r5py reads its JVM settings at import

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
from r5py import DetailedItineraries, TransportMode, TransportNetwork  # noqa: E402


def haversine_m(lat1, lng1, lat2, lng2):
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin(np.radians(lat2 - lat1) / 2) ** 2
         + np.cos(phi1) * np.cos(phi2) * np.sin(np.radians(lng2 - lng1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def main():
    if WALK_PATH.exists():
        print(f"saved data exists ({WALK_PATH.name}); reused, nothing routed")
        return
    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "lat", "lng"]).drop_duplicates("place_id")
    venues_df["straight_m"] = haversine_m(*PHONE_CENTRE, venues_df["lat"], venues_df["lng"])
    venues_df = venues_df[venues_df["straight_m"] <= CANDIDATE_RADIUS_M].reset_index(drop=True)
    ids = np.arange(len(venues_df))
    origins = gpd.GeoDataFrame({"id": ids}, crs="EPSG:4326",
                               geometry=gpd.points_from_xy(np.full(len(ids), PHONE_CENTRE[1]),
                                                           np.full(len(ids), PHONE_CENTRE[0])))
    destinations = gpd.GeoDataFrame({"id": ids}, crs="EPSG:4326",
                                    geometry=gpd.points_from_xy(venues_df["lng"], venues_df["lat"]))
    started = time.monotonic()
    network = TransportNetwork(PBF_PATH, [])
    print(f"network built in {time.monotonic() - started:.0f} s; routing {len(ids)} pairs", flush=True)
    di_df = pd.DataFrame(DetailedItineraries(network, origins=origins, destinations=destinations, departure=DEPARTURE,
                                             transport_modes=[TransportMode.WALK], speed_walking=WALK_SPEED_KMH))
    walk_df = di_df.groupby("to_id").agg(walk_m=("distance", "sum"), walk_s=("travel_time", "sum")).reset_index()
    walk_df["walk_s"] = walk_df["walk_s"].dt.total_seconds()
    out_df = venues_df.join(walk_df.set_index("to_id"))[["place_id", "straight_m", "walk_m", "walk_s"]]
    out_df.to_csv(WALK_PATH, index=False)
    print(f"{out_df['walk_m'].notna().sum()} of {len(out_df)} routed in {time.monotonic() - started:.0f} s; "
          f"median walk / straight {(out_df['walk_m'] / out_df['straight_m']).median():.2f}")


if __name__ == "__main__":
    main()
