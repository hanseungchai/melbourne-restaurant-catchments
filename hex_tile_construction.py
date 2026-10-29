import math
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

import config
from functions.geometry import (axial_ring_coords, axial_to_pixel, haversine_m, hex_polygons,
                                latlon_to_metres_offset, metres_to_latlon_offset, pixel_to_axial,
                                round_axial)
from functions.input_helper import read_subject_location
from functions.output_helper import is_already_built
from functions.subject_paths import (all_layers_tags, residents_tags, resolve_subject, subject_dir,
                                     subject_file, venues_tags, workers_tags)

HEX_RADIUS_M = config.HEX_DIAMETER_M / 2  # circumradius (centre to vertex)
# Flat-top hexes: ring k's nearest centre is 1.5 * k radii from hex 0.
N_RINGS = math.ceil(config.HEX_RING_MARGIN * config.HEX_GRID_RADIUS_M / (1.5 * HEX_RADIUS_M)) + 1
GPKG_DRIVER = "GPKG"
MINUTES_PER_HOUR = 60
METRES_PER_KM = 1000

# Hex grid columns.
HEX_ID_COL = "hex_id"
AXIAL_Q_COL = "q"
AXIAL_R_COL = "r"
CENTROID_LAT_COL = "centroid_lat"
CENTROID_LON_COL = "centroid_lon"
GEOMETRY_COL = "geometry"
HEX_RESIDENTS_COL = "residents"            # residents allocated from SA1s
HEX_WORKERS_COL = "workers"                # workers allocated from DZNs
HEX_VENUE_COUNT_COL = "venue_count"        # venues assigned to the hex (all venue types)
ZONE_COVERAGE_SUFFIX = "_cov"              # share of the hex's area covered by census zones
PAIR_OVERLAP_M2_COL = "overlap_m2"         # scratch column in allocate_zone_counts_to_hexes
RESIDENTS_LAYER_COLS = [HEX_RESIDENTS_COL, f"{HEX_RESIDENTS_COL}{ZONE_COVERAGE_SUFFIX}"]
WORKERS_LAYER_COLS = [HEX_WORKERS_COL, f"{HEX_WORKERS_COL}{ZONE_COVERAGE_SUFFIX}"]

# Census count columns (same as abs_census.py).
CENSUS_RESIDENTS_COL = "Tot_P_P"
CENSUS_WORKERS_COL = "Tot_W_P"

# Venue table columns.
VENUE_LAT_COL = "lat"
VENUE_LON_COL = "lng"
DISTANCE_TO_CENTROID_COL = "distance_to_hex_centroid_m"

# Data-layer tags in output file names.

# Printed checks only; they don't change what is kept.
VENUE_DISTANCE_REPORT_QUANTILES = [0.95, 0.99, 0.999]


def snap_to_stencil(subject_lat, subject_lon, hex_radius_m):
    """The stencil origin (config.HEX_STENCIL_ORIGIN_COORD_PATH) and the axial (q, r), counted
    from that origin, of the stencil hex the subject falls in."""
    origin_lat, origin_lon = read_subject_location(config.HEX_STENCIL_ORIGIN_COORD_PATH)
    dx, dy = latlon_to_metres_offset(subject_lat - origin_lat, subject_lon - origin_lon, origin_lat)
    subject_hex_q, subject_hex_r = round_axial(*pixel_to_axial(dx, dy, hex_radius_m))
    return origin_lat, origin_lon, subject_hex_q, subject_hex_r


def generate_hex_grid(subject_lat, subject_lon, n_rings, hex_radius_m,
                      max_distance_m=None):
    """Rings of stencil hexes around the subject's hex (hex 0). Centroids and polygons are laid
    from the stencil origin, so grids of different subjects share hexes exactly; q and r are
    counted from hex 0. max_distance_m filters on distance from the subject."""
    origin_lat, origin_lon, subject_hex_q, subject_hex_r = snap_to_stencil(subject_lat, subject_lon,
                                                                           hex_radius_m)
    q, r = axial_ring_coords(n_rings)
    hex_id = np.arange(len(q))
    dx, dy = axial_to_pixel(subject_hex_q + q, subject_hex_r + r, hex_radius_m)
    d_lat, d_lon = metres_to_latlon_offset(dx, dy, origin_lat)
    centroid_lat = origin_lat + d_lat
    centroid_lon = origin_lon + d_lon

    if max_distance_m is not None:
        is_within = haversine_m(subject_lat, subject_lon, centroid_lat, centroid_lon) <= max_distance_m
        hex_id, q, r = hex_id[is_within], q[is_within], r[is_within]
        centroid_lat, centroid_lon = centroid_lat[is_within], centroid_lon[is_within]

    return gpd.GeoDataFrame({
        HEX_ID_COL: hex_id,
        AXIAL_Q_COL: q,
        AXIAL_R_COL: r,
        CENTROID_LAT_COL: centroid_lat,
        CENTROID_LON_COL: centroid_lon,
        GEOMETRY_COL: hex_polygons(centroid_lat, centroid_lon, hex_radius_m, origin_lat),
    }, geometry=GEOMETRY_COL, crs=config.GEOGRAPHIC_CRS)


def coverage_gap_note(uncovered_share, missing_what, data_name):
    """Plain-language reading of an uncovered share, using the config.COVERAGE_GAP_* tiers."""
    if uncovered_share <= config.COVERAGE_GAP_MINOR_MAX:
        return "This is likely not an issue."
    if uncovered_share <= config.COVERAGE_GAP_LOW_CHANCE_MAX:
        return f"In this worst case, there is a low chance that marginal {missing_what}."
    if uncovered_share <= config.COVERAGE_GAP_REASONABLE_CHANCE_MAX:
        return f"In this worst case, there is a reasonable chance that marginal {missing_what}."
    return (f"It is very probable that marginal {missing_what}. Update the {data_name} "
            f"and take the results with a grain of salt.")


def check_subject_coverage(subject_lat, subject_lon):
    """Warn when the subject's very-worst-case competition reach leaves the venue scan or the
    road extract (reasoning in config.py "Coverage check"). Measures the uncovered share of the
    reach disc on a point lattice; warns only, never stops the stage."""
    reach_m = (2 * config.DRIVE_BAND_DURATION_MIN / MINUTES_PER_HOUR
               * config.MAX_DRIVE_SPEED_KMH * METRES_PER_KM)

    lattice_offsets_m = np.arange(-reach_m, reach_m + config.COVERAGE_SAMPLE_SPACING_M,
                                  config.COVERAGE_SAMPLE_SPACING_M)
    dx_m, dy_m = (offset.ravel() for offset in np.meshgrid(lattice_offsets_m, lattice_offsets_m))
    d_lat, d_lon = metres_to_latlon_offset(dx_m, dy_m, subject_lat)
    sample_lat, sample_lon = subject_lat + d_lat, subject_lon + d_lon
    is_in_reach = haversine_m(subject_lat, subject_lon, sample_lat, sample_lon) <= reach_m
    sample_lat, sample_lon = sample_lat[is_in_reach], sample_lon[is_in_reach]

    scan_lat, scan_lon = read_subject_location(config.LEGACY_SCAN_CENTRE_COORD_PATH)
    is_venue_covered = haversine_m(scan_lat, scan_lon, sample_lat, sample_lon) <= config.VENUE_SCAN_RADIUS_M
    min_lon, min_lat, max_lon, max_lat = config.ROAD_EXTRACT_BOUNDS
    is_road_covered = ((sample_lon >= min_lon) & (sample_lon <= max_lon)
                       & (sample_lat >= min_lat) & (sample_lat <= max_lat))

    coverages = [
        ("the venue scan", is_venue_covered, "venues are not covered", "venue data"),
        ("the road extract", is_road_covered, "venues' routes are cut off", "road extract"),
    ]
    for coverage_name, is_covered, missing_what, data_name in coverages:
        uncovered_share = 1 - is_covered.mean()
        if uncovered_share == 0:
            continue
        warnings.warn(
            f"Coverage check (very worst case: cars flying straight at {config.MAX_DRIVE_SPEED_KMH} km/h "
            f"for 2 x {config.DRIVE_BAND_DURATION_MIN} min = {reach_m / METRES_PER_KM:.1f} km): "
            f"{uncovered_share:.1%} of that disc around the subject lies outside {coverage_name}. "
            f"Real reach is much smaller than this imagined worst case. "
            + coverage_gap_note(uncovered_share, missing_what, data_name))


def build_hex_grid(subject_lat=None, subject_lon=None, should_rebuild=False):
    subject_lat, subject_lon = resolve_subject(subject_lat, subject_lon)
    hex_grid_path = subject_file(config.HEX_GRID_PATH, subject_lat, subject_lon)
    if is_already_built([hex_grid_path], should_rebuild):
        return
    check_subject_coverage(subject_lat, subject_lon)
    hex_grid_gdf = generate_hex_grid(subject_lat, subject_lon, N_RINGS, HEX_RADIUS_M,
                                     max_distance_m=config.HEX_GRID_RADIUS_M)
    print(f"Generated {len(hex_grid_gdf):,} hex tiles within {config.HEX_GRID_RADIUS_M}m of the subject")

    subject_hex_row = hex_grid_gdf[hex_grid_gdf[HEX_ID_COL] == 0].iloc[0]
    print(f"Hex 0 centroid: ({subject_hex_row[CENTROID_LAT_COL]}, {subject_hex_row[CENTROID_LON_COL]})")
    subject_to_hex_0_m = haversine_m(subject_lat, subject_lon,
                                     subject_hex_row[CENTROID_LAT_COL], subject_hex_row[CENTROID_LON_COL])
    print(f"Subject coord:  ({subject_lat}, {subject_lon}), "
          f"{subject_to_hex_0_m:.1f} m from the hex 0 centroid (stencil snap)")
    assert hex_grid_gdf[HEX_ID_COL].iloc[0] == 0, "hex 0 must be the subject"

    axial_q, axial_r = hex_grid_gdf[AXIAL_Q_COL], hex_grid_gdf[AXIAL_R_COL]
    hex_ring_number = (axial_q.abs() + axial_r.abs() + (axial_q + axial_r).abs()) // 2
    assert hex_ring_number.max() < N_RINGS, (
        f"hexes survive in the outermost ring ({N_RINGS}) -- grid truncated "
        "before the distance filter; raise N_RINGS")
    print(f"outermost retained ring: {hex_ring_number.max()} of {N_RINGS}")

    subject_dir(config.HEX_GRID_DIR, subject_lat, subject_lon).mkdir(parents=True, exist_ok=True)
    hex_grid_gdf.to_file(hex_grid_path, driver=GPKG_DRIVER)
    print(f"Saved to {hex_grid_path}")


def allocate_zone_counts_to_hexes(hex_grid_gdf, zones_gdf, zone_count_col, hex_count_col):
    """Share each zone's count among the hexes it overlaps, by overlap area / full zone area.

    Adds hex_count_col and hex_count_col + ZONE_COVERAGE_SUFFIX (share of the hex's area
    covered by zones); hexes no zone touches get 0 in both.
    """
    hex_coverage_col = f"{hex_count_col}{ZONE_COVERAGE_SUFFIX}"
    hex_grid_metric_gdf = hex_grid_gdf[[HEX_ID_COL, GEOMETRY_COL]].to_crs(config.METRIC_CRS)
    zones_metric_gdf = (zones_gdf[[zone_count_col, GEOMETRY_COL]].to_crs(config.METRIC_CRS)
                        .reset_index(drop=True))
    zones_metric_gdf[GEOMETRY_COL] = shapely.make_valid(zones_metric_gdf.geometry.values)

    hex_polygons, zone_polygons = hex_grid_metric_gdf.geometry.values, zones_metric_gdf.geometry.values
    hex_area_m2, zone_full_area_m2 = shapely.area(hex_polygons), shapely.area(zone_polygons)

    # One entry per hex-zone pair whose polygons intersect: positions into the two arrays.
    pair_hex_pos, pair_zone_pos = zones_metric_gdf.sindex.query(hex_polygons, predicate='intersects')
    shapely.prepare(zone_polygons)
    is_hex_inside_zone = shapely.contains_properly(zone_polygons[pair_zone_pos],
                                                   hex_polygons[pair_hex_pos])

    pair_overlap_m2 = np.where(is_hex_inside_zone, hex_area_m2[pair_hex_pos], 0.0)
    is_hex_on_zone_edge = ~is_hex_inside_zone              # only these need an intersection
    pair_overlap_m2[is_hex_on_zone_edge] = shapely.area(shapely.intersection(
        hex_polygons[pair_hex_pos[is_hex_on_zone_edge]],
        zone_polygons[pair_zone_pos[is_hex_on_zone_edge]]))

    pair_allocated_count = (pair_overlap_m2 / zone_full_area_m2[pair_zone_pos]
                            * zones_metric_gdf[zone_count_col].to_numpy()[pair_zone_pos])
    allocated_by_hex_df = (pd.DataFrame({HEX_ID_COL: hex_grid_metric_gdf[HEX_ID_COL].to_numpy()[pair_hex_pos],
                                         hex_count_col: pair_allocated_count,
                                         PAIR_OVERLAP_M2_COL: pair_overlap_m2})
                           .groupby(HEX_ID_COL).sum())
    hex_area_by_id_m2 = pd.Series(hex_area_m2, index=hex_grid_metric_gdf[HEX_ID_COL])
    allocated_by_hex_df[hex_coverage_col] = (allocated_by_hex_df[PAIR_OVERLAP_M2_COL]
                                             / hex_area_by_id_m2.reindex(allocated_by_hex_df.index))

    hex_grid_with_counts_gdf = hex_grid_gdf.merge(
        allocated_by_hex_df.drop(columns=PAIR_OVERLAP_M2_COL).reset_index(), on=HEX_ID_COL, how='left')
    new_cols = [hex_count_col, hex_coverage_col]
    hex_grid_with_counts_gdf[new_cols] = hex_grid_with_counts_gdf[new_cols].fillna(0)
    return hex_grid_with_counts_gdf


def build_residents_layer(subject_lat=None, subject_lon=None, should_rebuild=False):
    """Residents per hex from SA1s: hex_id, residents, residents_cov for every hex of the bare grid."""
    subject_lat, subject_lon = resolve_subject(subject_lat, subject_lon)
    residents_layer_path = subject_file(config.HEX_RESIDENTS_LAYER_PATH, subject_lat, subject_lon, residents_tags())
    if is_already_built([residents_layer_path], should_rebuild):
        return
    hex_grid_gdf = gpd.read_file(subject_file(config.HEX_GRID_PATH, subject_lat, subject_lon),
                                 columns=[HEX_ID_COL])
    sa1_residents_gdf = gpd.read_file(config.SA1_RESIDENTS_GPKG_PATH)

    print(f"Hex tiles: {len(hex_grid_gdf):,}   SA1 zones: {len(sa1_residents_gdf):,}")

    hex_grid_gdf = allocate_zone_counts_to_hexes(hex_grid_gdf, sa1_residents_gdf,
                                                 CENSUS_RESIDENTS_COL, HEX_RESIDENTS_COL)

    print(f"Residents allocated: {hex_grid_gdf[HEX_RESIDENTS_COL].sum():,.0f} "
          f"of {sa1_residents_gdf[CENSUS_RESIDENTS_COL].sum():,.0f} statewide")
    print(hex_grid_gdf[HEX_RESIDENTS_COL].describe())

    residents_layer_df = pd.DataFrame(hex_grid_gdf[[HEX_ID_COL, *RESIDENTS_LAYER_COLS]])
    residents_layer_df.to_parquet(residents_layer_path, index=False)
    print(f"Saved to {residents_layer_path}")


def build_workers_layer(subject_lat=None, subject_lon=None, should_rebuild=False):
    """Workers per hex from Destination Zones: hex_id, workers, workers_cov for every hex of the
    bare grid.

    Kept as a separate column from residents and never blended -- combining
    them needs a rate nobody has measured. DZNs are sized by employment
    density, so they resolve finely in the CBD and coarsely at the fringe;
    the worker layer is therefore coarser than the SA1-derived resident layer.
    """
    subject_lat, subject_lon = resolve_subject(subject_lat, subject_lon)
    workers_layer_path = subject_file(config.HEX_WORKERS_LAYER_PATH, subject_lat, subject_lon, workers_tags())
    if is_already_built([workers_layer_path], should_rebuild):
        return
    hex_grid_gdf = gpd.read_file(subject_file(config.HEX_GRID_PATH, subject_lat, subject_lon),
                                 columns=[HEX_ID_COL])
    dzn_workers_gdf = gpd.read_file(config.DZN_WORKERS_GPKG_PATH)

    print(f"Hex tiles: {len(hex_grid_gdf):,}   DZN zones: {len(dzn_workers_gdf):,}")

    hex_grid_gdf = allocate_zone_counts_to_hexes(hex_grid_gdf, dzn_workers_gdf,
                                                 CENSUS_WORKERS_COL, HEX_WORKERS_COL)

    print(f"Workers allocated: {hex_grid_gdf[HEX_WORKERS_COL].sum():,.0f} "
          f"of {dzn_workers_gdf[CENSUS_WORKERS_COL].sum():,.0f} statewide")
    print(hex_grid_gdf[HEX_WORKERS_COL].describe())

    workers_layer_df = pd.DataFrame(hex_grid_gdf[[HEX_ID_COL, *WORKERS_LAYER_COLS]])
    workers_layer_df.to_parquet(workers_layer_path, index=False)
    print(f"Saved to {workers_layer_path}")


def build_venue_counts_layer(subject_lat=None, subject_lon=None, should_rebuild=False):
    """Venues to their nearest hex centroid: venue_count for every hex of the bare grid, plus the
    venue table with each venue's hex_id and distance to that centroid."""
    subject_lat, subject_lon = resolve_subject(subject_lat, subject_lon)
    venue_counts_layer_path = subject_file(config.HEX_VENUE_COUNTS_LAYER_PATH, subject_lat, subject_lon,
                                           venues_tags())
    venues_with_hex_path = subject_file(config.VENUES_WITH_HEX_PATH, subject_lat, subject_lon, venues_tags())
    if is_already_built([venue_counts_layer_path, venues_with_hex_path], should_rebuild):
        return
    venues_df = pd.read_csv(config.VENUE_TABLES[config.HEX_VENUES_DATE])
    hex_grid_df = gpd.read_file(subject_file(config.HEX_GRID_PATH, subject_lat, subject_lon),
                                columns=[HEX_ID_COL, CENTROID_LAT_COL, CENTROID_LON_COL], ignore_geometry=True)

    print(f"Venues: {len(venues_df):,}   Hex tiles: {len(hex_grid_df):,}")

    venue_points_metric_gdf = gpd.GeoDataFrame(
        venues_df,
        geometry=gpd.points_from_xy(venues_df[VENUE_LON_COL], venues_df[VENUE_LAT_COL]),
        crs=config.GEOGRAPHIC_CRS,
    ).to_crs(config.METRIC_CRS)

    hex_centroids_metric_gdf = gpd.GeoDataFrame(
        hex_grid_df[[HEX_ID_COL]],
        geometry=gpd.points_from_xy(hex_grid_df[CENTROID_LON_COL], hex_grid_df[CENTROID_LAT_COL]),
        crs=config.GEOGRAPHIC_CRS,
    ).to_crs(config.METRIC_CRS)

    hex_centroid_kdtree = cKDTree(list(zip(hex_centroids_metric_gdf.geometry.x,
                                           hex_centroids_metric_gdf.geometry.y)))
    nearest_centroid_distance_m, nearest_centroid_pos = hex_centroid_kdtree.query(
        list(zip(venue_points_metric_gdf.geometry.x, venue_points_metric_gdf.geometry.y)), k=1)

    venues_df[HEX_ID_COL] = hex_centroids_metric_gdf.iloc[nearest_centroid_pos][HEX_ID_COL].values
    venues_df[DISTANCE_TO_CENTROID_COL] = nearest_centroid_distance_m

    print(f"Mean distance to assigned centroid: "
          f"{venues_df[DISTANCE_TO_CENTROID_COL].mean():.1f}m")
    print(venues_df[DISTANCE_TO_CENTROID_COL].quantile(VENUE_DISTANCE_REPORT_QUANTILES))

    # venues outside the grid's true coverage get snapped to an edge hex by
    # cKDTree regardless of distance -- drop those rather than inflate boundary hexes
    n_venues_before = len(venues_df)
    venues_df = venues_df[venues_df[DISTANCE_TO_CENTROID_COL]
                          <= config.VENUE_HEX_MATCH_RADIUS_M].copy()
    print(f"Dropped {n_venues_before - len(venues_df)} venues beyond "
          f"{config.VENUE_HEX_MATCH_RADIUS_M}m of any "
          f"centroid; {len(venues_df):,} retained")

    venues_df.to_csv(venues_with_hex_path, index=False)
    print(f"Saved venue-to-hex assignments to {venues_with_hex_path}")

    venue_count_by_hex_df = venues_df.groupby(HEX_ID_COL).size().reset_index(name=HEX_VENUE_COUNT_COL)
    venue_counts_layer_df = hex_grid_df[[HEX_ID_COL]].merge(venue_count_by_hex_df, on=HEX_ID_COL, how='left')
    venue_counts_layer_df[HEX_VENUE_COUNT_COL] = venue_counts_layer_df[HEX_VENUE_COUNT_COL].fillna(0).astype(int)

    venue_counts_layer_df.to_parquet(venue_counts_layer_path, index=False)
    print(f"Saved to {venue_counts_layer_path}")


def filter_empty_hexes(hex_grid_gdf):
    """Drop hexes with no allocated residents, no allocated workers, and no
    venue.

    The threshold is > 0, not >= 1. Area-proportional allocation gives every
    interior hex of a zone an identical share, so a sparse zone's share can
    fall below one person -- and a >= 1 rule would then drop the entire zone,
    not a rounding remainder. Whether the sub-1 hexes are worth keeping is a
    separate decision; reachability drops hexes with no residents and no
    reachable competitors regardless.

    Runs on the assembled grid: all three layers must be joined before the filter can see them.
    """
    n_hexes_before = len(hex_grid_gdf)
    residents_coverage_col = f"{HEX_RESIDENTS_COL}{ZONE_COVERAGE_SUFFIX}"
    workers_coverage_col = f"{HEX_WORKERS_COL}{ZONE_COVERAGE_SUFFIX}"

    is_nonempty = ((hex_grid_gdf[HEX_RESIDENTS_COL] > 0)
                   | (hex_grid_gdf[HEX_WORKERS_COL] > 0)
                   | (hex_grid_gdf[HEX_VENUE_COUNT_COL] > 0))

    empty_hexes_gdf = hex_grid_gdf[~is_nonempty]
    print(f"Dropping {len(empty_hexes_gdf):,} empty hexes")

    is_uncovered = ((empty_hexes_gdf[residents_coverage_col] < config.UNCOVERED_COVERAGE_MAX)
                    & (empty_hexes_gdf[workers_coverage_col] < config.UNCOVERED_COVERAGE_MAX)
                    & (empty_hexes_gdf[HEX_VENUE_COUNT_COL] == 0))
    print(f"  outside census coverage (water etc.): {is_uncovered.sum():,}   "
          f"covered land with zero in all: {(~is_uncovered).sum():,}")

    hex_grid_gdf = hex_grid_gdf[is_nonempty].copy()
    print(f"Filtered {n_hexes_before:,} -> {len(hex_grid_gdf):,} hexes")

    under_one_person_gdf = hex_grid_gdf[(hex_grid_gdf[HEX_RESIDENTS_COL] < 1)
                                        & (hex_grid_gdf[HEX_WORKERS_COL] < 1)
                                        & (hex_grid_gdf[HEX_VENUE_COUNT_COL] == 0)]
    print(f"of which {len(under_one_person_gdf):,} hold under one person in both columns "
          f"({under_one_person_gdf[HEX_RESIDENTS_COL].sum():,.0f} residents, "
          f"{under_one_person_gdf[HEX_WORKERS_COL].sum():,.0f} workers)")

    is_kept_by_trace_coverage = (
        (hex_grid_gdf[[residents_coverage_col, workers_coverage_col]].max(axis=1) < config.TRACE_COVERAGE_MAX)
        & (hex_grid_gdf[HEX_VENUE_COUNT_COL] == 0))
    print(f"kept on coverage < {config.TRACE_COVERAGE_MAX} alone: {is_kept_by_trace_coverage.sum():,}")

    assert (hex_grid_gdf[HEX_ID_COL] == 0).any(), "subject hex was filtered out"
    return hex_grid_gdf


def assemble_hex_layers(subject_lat=None, subject_lon=None):
    """Join the three layer tables onto the bare grid, drop empty hexes, save the filled grid.
    Always runs: it is cheap next to the layers, and any layer may have just been rebuilt."""
    if config.CENSUS_RESIDENTS_YEAR != config.CENSUS_WORKERS_YEAR:
        warnings.warn(f"Census years differ: residents {config.CENSUS_RESIDENTS_YEAR}, "
                      f"workers {config.CENSUS_WORKERS_YEAR}. Allowed, but state it as a limitation "
                      f"(DESIGN_pre_spine \"Data layers\").")
    subject_lat, subject_lon = resolve_subject(subject_lat, subject_lon)
    hex_grid_pop_path = subject_file(config.HEX_GRID_POP_PATH, subject_lat, subject_lon, all_layers_tags())
    hex_grid_gdf = gpd.read_file(subject_file(config.HEX_GRID_PATH, subject_lat, subject_lon))
    layers = [
        (config.HEX_RESIDENTS_LAYER_PATH, residents_tags()),
        (config.HEX_WORKERS_LAYER_PATH, workers_tags()),
        (config.HEX_VENUE_COUNTS_LAYER_PATH, venues_tags()),
    ]
    for layer_path, layer_tags in layers:
        layer_df = pd.read_parquet(subject_file(layer_path, subject_lat, subject_lon, layer_tags))
        # A layer built on an older bare grid (e.g. another radius) would otherwise join with gaps.
        is_same_hexes = (len(layer_df) == len(hex_grid_gdf)
                         and layer_df[HEX_ID_COL].isin(hex_grid_gdf[HEX_ID_COL]).all())
        assert is_same_hexes, (f"{layer_path.stem} doesn't cover the bare grid's hexes; rebuild it "
                               f"(main.py should_rebuild_hex_layers)")
        hex_grid_gdf = hex_grid_gdf.merge(layer_df, on=HEX_ID_COL, how='left')

    has_workers_only = (hex_grid_gdf[HEX_WORKERS_COL] > 0) & (hex_grid_gdf[HEX_RESIDENTS_COL] == 0)
    print(f"hexes with workers > 0 but residents == 0: {has_workers_only.sum():,}")

    hex_grid_gdf = filter_empty_hexes(hex_grid_gdf)
    hex_grid_gdf.to_file(hex_grid_pop_path, driver=GPKG_DRIVER)
    print(f"Saved to {hex_grid_pop_path}")
