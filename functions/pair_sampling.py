"""Pair sampling rules shared by the drive and transit draws (drive_samples, transit_samples)."""
import geopandas as gpd
import numpy as np
from scipy.spatial import cKDTree

import config

MIN_PER_HOUR = 60
HEX_ID_COL = "hex_id"
CENTROID_LAT_COL, CENTROID_LON_COL = "centroid_lat", "centroid_lon"
VENUE_LAT_COL, VENUE_LON_COL = "lat", "lng"


def departure_probabilities(hist, floor_share=config.ROUTES_DRIVE_DEPARTURE_FLOOR_SHARE,
                            floor_hours=config.ROUTES_DRIVE_DEPARTURE_FLOOR_HOURS):
    """Probability of each weekday slot (day-major, flattened): (1 - floor_share) from the open-share
    histogram, floor_share flat over the floor hours."""
    floor_slots = range(floor_hours[0] * MIN_PER_HOUR // config.HOURS_SLOT_MIN,
                        floor_hours[1] * MIN_PER_HOUR // config.HOURS_SLOT_MIN)
    open_share = hist.astype(float)
    floor = np.zeros_like(open_share)
    floor[:, list(floor_slots)] = 1
    return ((1 - floor_share) * open_share / open_share.sum()
            + floor_share * floor / floor.sum()).ravel()


def assign_venue_hex(venues_df, hexes_df, max_m=config.VENUE_HEX_MATCH_RADIUS_M, crs=config.METRIC_CRS):
    """Nearest hex centroid, capped at max_m (same rule as the hex stage's venue assignment).
    Returns (venues within max_m with hex_id and hex_dist_m, count beyond max_m)."""
    centroids = gpd.GeoSeries(gpd.points_from_xy(hexes_df[CENTROID_LON_COL], hexes_df[CENTROID_LAT_COL]),
                              crs=config.GEOGRAPHIC_CRS).to_crs(crs)
    tree = cKDTree(np.c_[centroids.x.to_numpy(), centroids.y.to_numpy()])
    venue_points = gpd.GeoSeries(gpd.points_from_xy(venues_df[VENUE_LON_COL], venues_df[VENUE_LAT_COL]),
                                 crs=config.GEOGRAPHIC_CRS).to_crs(crs)
    dist_m, nearest_ix = tree.query(np.c_[venue_points.x.to_numpy(), venue_points.y.to_numpy()])
    assigned_df = venues_df.copy()
    assigned_df[HEX_ID_COL] = hexes_df[HEX_ID_COL].to_numpy()[nearest_ix]
    assigned_df["hex_dist_m"] = dist_m
    return assigned_df[assigned_df.hex_dist_m <= max_m].reset_index(drop=True), int((dist_m > max_m).sum())
