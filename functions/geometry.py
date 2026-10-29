"""Geometry helpers: pure maths, no project knowledge."""
import math

import numpy as np
import shapely

EARTH_RADIUS_M = 6_371_000  # mean Earth radius; the value every legacy haversine used
METRES_PER_DEGREE_LAT = 111_320  # flat-earth conversion in metres_to_latlon_offset
HEX_SIDES = 6


def haversine_m(lat1, lng1, lat2, lng2, earth_radius_m=EARTH_RADIUS_M):
    """Return the great-circle distance in metres between points given in degrees.

    Vectorised: each argument may be a scalar or a numpy array. Same formula and order of
    operations as the legacy hex_lattice.haversine_np, so results are bit-for-bit identical.
    """
    lat1_rad, lat2_rad = np.radians(lat1), np.radians(lat2)
    half_chord_squared = (np.sin((lat2_rad - lat1_rad) / 2) ** 2
                          + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(np.radians(lng2 - lng1) / 2) ** 2)
    return 2 * earth_radius_m * np.arcsin(np.sqrt(half_chord_squared))


def axial_to_pixel(q, r, size):
    """Flat-top hex axial coordinates -> pixel (metre) offsets from origin."""
    x = size * (3 / 2 * q)
    y = size * (math.sqrt(3) / 2 * q + math.sqrt(3) * r)
    return x, y


def metres_to_latlon_offset(dx, dy, ref_lat):
    """Convert a local metre offset to a lat/lon offset, using a flat-earth
    approximation -- valid at this scale (city-sized extent, 100m hexes)."""
    d_lat = dy / METRES_PER_DEGREE_LAT
    d_lon = dx / (METRES_PER_DEGREE_LAT * math.cos(math.radians(ref_lat)))
    return d_lat, d_lon


def latlon_to_metres_offset(d_lat, d_lon, ref_lat):
    """Inverse of metres_to_latlon_offset: a lat/lon offset -> local metre offset (dx, dy)."""
    dy = d_lat * METRES_PER_DEGREE_LAT
    dx = d_lon * (METRES_PER_DEGREE_LAT * math.cos(math.radians(ref_lat)))
    return dx, dy


def pixel_to_axial(x, y, size):
    """Inverse of axial_to_pixel: metre offsets -> fractional flat-top axial (q, r)."""
    q = x / (3 / 2 * size)
    r = y / (math.sqrt(3) * size) - q / 2
    return q, r


def round_axial(q, r):
    """Fractional axial (q, r) -> the axial coordinates of the hex containing that point
    (cube rounding: round all three cube coordinates, then fix the one that moved most)."""
    s = -q - r
    rounded_q, rounded_r, rounded_s = round(q), round(r), round(s)
    q_shift, r_shift, s_shift = abs(rounded_q - q), abs(rounded_r - r), abs(rounded_s - s)
    if q_shift > r_shift and q_shift > s_shift:
        rounded_q = -rounded_r - rounded_s
    elif r_shift > s_shift:
        rounded_r = -rounded_q - rounded_s
    return int(rounded_q), int(rounded_r)


def hex_polygons(center_lats, center_lons, size, ref_lat):
    """Flat-top hexagons (vertices at 0, 60, 120, ... degrees) around arrays of centre points,
    all converted at one reference latitude. Returns an array of shapely Polygons."""
    vertex_d_lats, vertex_d_lons = [], []
    for i in range(HEX_SIDES):
        angle_rad = math.radians(60 * i)
        vx = size * math.cos(angle_rad)
        vy = size * math.sin(angle_rad)
        d_lat, d_lon = metres_to_latlon_offset(vx, vy, ref_lat)
        vertex_d_lats.append(d_lat)
        vertex_d_lons.append(d_lon)
    vertex_lons = np.asarray(center_lons)[:, None] + np.array(vertex_d_lons)
    vertex_lats = np.asarray(center_lats)[:, None] + np.array(vertex_d_lats)
    return shapely.polygons(np.stack([vertex_lons, vertex_lats], axis=-1))


def axial_ring_coords(n_rings):
    """(q, r) arrays of axial coordinates for hex 0,0 plus all rings out to n_rings, in ring
    order: ring k starts at (-k, k) and walks the six directions, k steps each. hex_id is the
    position in this order, so hex 0 is the subject by construction -- a convention the rest of
    the pipeline relies on."""
    directions = np.array([(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)])
    # Corner each side starts from, in units of the ring number.
    side_start_offsets = np.vstack([[0, 0], np.cumsum(directions, axis=0)[:-1]])

    ring_numbers = np.arange(1, n_rings + 1)
    ring_sizes = HEX_SIDES * ring_numbers
    ring = np.repeat(ring_numbers, ring_sizes)
    position_in_ring = np.arange(len(ring)) - np.repeat(np.cumsum(ring_sizes) - ring_sizes, ring_sizes)
    side, step = np.divmod(position_in_ring, ring)

    q = -ring + ring * side_start_offsets[side, 0] + step * directions[side, 0]
    r = ring + ring * side_start_offsets[side, 1] + step * directions[side, 1]
    return np.concatenate([[0], q]), np.concatenate([[0], r])
