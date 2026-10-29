"""Road density per hex and raster (map_construction stage; was construct_density_drive).

Valhalla's road-density rule (config "Road density"): road km per km² within ROAD_DENSITY_RADIUS_M of
every raster cell, counting the OSM ways Valhalla counts. Each hex reads the cell under its centroid
and gets a level (0-15), a tier (rural / suburban / urban) and an urban sub-tier.
The raster depends on the road extract only, so it is built once and reused by every subject; the
hex table is per subject. Statistics and figures: diagnostics/road_density_distribution.py.
"""
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy.signal import fftconvolve
from shapely.geometry import box

import config
from functions.density_levels import HALF_UP, sample_density, valhalla_tier
from functions.output_helper import is_already_built
from functions.subject_paths import all_layers_tags, resolve_subject, subject_dir, subject_file

METRES_PER_KM = 1000
GPKG_DRIVER = "GPKG"

# OSM extract, read through GDAL's OSM driver.
OSM_LINES_LAYER = "lines"
OSM_HIGHWAY_FILTER = "highway IS NOT NULL"
HIGHWAY_COL = "highway"
OTHER_TAGS_COL = "other_tags"
SERVICE_TAG_PATTERN = re.compile(r'"service"=>"([^"]*)"')   # the service=* value inside other_tags
SERVICE_HIGHWAY = "service"

# Way table columns and classes.
ROAD_CLASS_COL = "cls"
COUNTED_CLASS = "count"
EXCLUDED_CLASS = "exclude"
LENGTH_KM_COL = "len_km"

# Hex grid input columns.
CENTROID_LAT_COL = "centroid_lat"
CENTROID_LON_COL = "centroid_lon"

# Hex table output columns.
ROAD_DENSITY_COL = "road_density_km_km2"             # road km per km² in the disk around the centroid
DENSITY_LEVEL_COL = "valhalla_density"                # level 0-15 (capped)
UNCAPPED_LEVEL_COL = "valhalla_density_uncapped"      # level without the cap; description only
DENSITY_TIER_COL = "density_tier"                     # rural / suburban / urban
URBAN_SUBTIER_COL = "urban_subtier"                   # marginal / mid / dense urban; None outside urban
DENSITY_CLASS_COL = "density_class"                   # sub-tier where there is one, else tier: for maps and route exposure
DISK_CLIPPED_COL = "density_disk_clipped"             # True when the disk reaches past the extract (density reads low)

# Tier and sub-tier labels.
MARGINAL_URBAN_SUBTIER = "marginal_urban"
MID_URBAN_SUBTIER = "mid_urban"
DENSE_URBAN_SUBTIER = "dense_urban"


def classify_way(highway, service):
    """COUNTED_CLASS if Valhalla counts the way toward density, else EXCLUDED_CLASS."""
    if highway in config.ROAD_DENSITY_HIGHWAY_TYPES or highway in config.ROAD_DENSITY_RAMP_HIGHWAY_TYPES:
        return COUNTED_CLASS
    if highway == SERVICE_HIGHWAY:
        # alley / emergency_access / untagged / unlisted -> counted by Valhalla
        return EXCLUDED_CLASS if service in config.ROAD_DENSITY_EXCLUDED_SERVICE_VALUES else COUNTED_CLASS
    return EXCLUDED_CLASS   # track, living_street, footways, construction, ...


def service_tag(other_tags):
    """The service=* value from GDAL's other_tags text, or None."""
    if not isinstance(other_tags, str):
        return None
    match = SERVICE_TAG_PATTERN.search(other_tags)
    return match.group(1) if match else None


def load_counted_roads(pbf_path=config.ROAD_EXTRACT_PBF_PATH):
    """Ways Valhalla counts toward road density, in config.METRIC_CRS. One row per way."""
    lines_gdf = gpd.read_file(pbf_path, layer=OSM_LINES_LAYER, where=OSM_HIGHWAY_FILTER)
    service = lines_gdf[OTHER_TAGS_COL].map(service_tag)
    lines_gdf[ROAD_CLASS_COL] = [classify_way(highway, value) for highway, value in zip(lines_gdf[HIGHWAY_COL], service)]
    lines_gdf = lines_gdf.to_crs(config.METRIC_CRS)
    lines_gdf[LENGTH_KM_COL] = lines_gdf.length / METRES_PER_KM

    share = lines_gdf.groupby(ROAD_CLASS_COL)[LENGTH_KM_COL].sum()
    share = (share / share[share.index != EXCLUDED_CLASS].sum()).sort_values(ascending=False)
    print("length share of non-excluded classes:\n", share.drop(EXCLUDED_CLASS, errors="ignore").round(3))

    # Valhalla also excludes main-road ways tagged service=driveway/parking_aisle/other;
    # checked Sep 2026: 13.5 km, 0.02% of counted length -- ignored
    main_road_types = config.ROAD_DENSITY_HIGHWAY_TYPES | config.ROAD_DENSITY_RAMP_HIGHWAY_TYPES
    is_main_with_service = lines_gdf[HIGHWAY_COL].isin(main_road_types) & service.notna()
    if is_main_with_service.any():
        tagged_df = lines_gdf.loc[is_main_with_service, [HIGHWAY_COL, LENGTH_KM_COL]].assign(
            service=service[is_main_with_service])
        print(f"main-road ways with a service tag: {is_main_with_service.sum():,} "
              f"({tagged_df[LENGTH_KM_COL].sum():,.1f} km)")
        print(tagged_df.groupby("service")[LENGTH_KM_COL].agg(ways="size", km="sum")
              .sort_values("km", ascending=False).round(1))
        dropped_km = tagged_df.loc[~tagged_df["service"].isin(config.ROAD_DENSITY_COUNTED_SERVICE_VALUES),
                                   LENGTH_KM_COL].sum()
        counted_km = lines_gdf.loc[lines_gdf[ROAD_CLASS_COL].eq(COUNTED_CLASS), LENGTH_KM_COL].sum()
        print(f"Valhalla would not count {dropped_km:,.1f} km "
              f"= {dropped_km / counted_km:.2%} of counted length")
    else:
        print("main-road ways with a service tag: 0")

    return lines_gdf.loc[lines_gdf[ROAD_CLASS_COL].eq(COUNTED_CLASS),
                         [HIGHWAY_COL, ROAD_CLASS_COL, LENGTH_KM_COL, "geometry"]]


def road_density_raster(roads_gdf, bounds):
    """Road km per km² within ROAD_DENSITY_RADIUS_M of every cell; returns (density, x0, y0)."""
    cell_m = config.ROAD_DENSITY_CELL_M
    x_min, y_min, x_max, y_max = (gpd.GeoSeries([box(*bounds)], crs=config.GEOGRAPHIC_CRS)
                                  .to_crs(config.METRIC_CRS).total_bounds)
    x0, y0 = np.floor(x_min / cell_m) * cell_m, np.floor(y_min / cell_m) * cell_m
    x1, y1 = np.ceil(x_max / cell_m) * cell_m, np.ceil(y_max / cell_m) * cell_m
    x_edges = np.arange(x0, x1 + cell_m, cell_m)
    y_edges = np.arange(y0, y1 + cell_m, cell_m)

    # densify, then give each short piece's length to the cell holding its midpoint
    geoms = shapely.segmentize(roads_gdf.geometry.explode(index_parts=False).to_numpy(), config.ROAD_DENSITY_SEGMENT_M)
    coords, way_index = shapely.get_coordinates(geoms, return_index=True)
    is_same_way = way_index[1:] == way_index[:-1]          # don't join the end of one way to the next
    piece_start, piece_end = coords[:-1][is_same_way], coords[1:][is_same_way]
    piece_km = np.hypot(*(piece_end - piece_start).T) / METRES_PER_KM
    piece_mid = (piece_start + piece_end) / 2
    length_km, _, _ = np.histogram2d(piece_mid[:, 0], piece_mid[:, 1],
                                     bins=[x_edges, y_edges], weights=piece_km)

    print(f"road km rasterised: {length_km.sum():,.0f} of {roads_gdf[LENGTH_KM_COL].sum():,.0f}")

    radius_cells = int(config.ROAD_DENSITY_RADIUS_M // cell_m)
    offsets_m = np.arange(-radius_cells, radius_cells + 1) * cell_m
    dx, dy = np.meshgrid(offsets_m, offsets_m, indexing="ij")
    disk_kernel = (np.hypot(dx, dy) <= config.ROAD_DENSITY_RADIUS_M).astype(float)
    disk_km2 = disk_kernel.sum() * (cell_m / METRES_PER_KM) ** 2
    exact_disk_km2 = np.pi * (config.ROAD_DENSITY_RADIUS_M / METRES_PER_KM) ** 2
    print(f"discrete disk area: {disk_km2:.3f} km² (exact {exact_disk_km2:.3f})")

    road_km = np.clip(fftconvolve(length_km, disk_kernel, mode="same"), 0, None)  # clip FFT noise below 0
    return road_km / disk_km2, x0, y0


def build_density_raster(should_rebuild):
    """The density raster: loaded if it exists (unless should_rebuild), else built from the extract and saved."""
    raster_path = config.ROAD_DENSITY_RASTER_PATH
    if is_already_built([raster_path], should_rebuild):
        with np.load(raster_path) as raster:
            assert float(raster["cell_m"]) == config.ROAD_DENSITY_CELL_M, "saved raster has a different cell size"
            assert str(raster["crs"]) == config.METRIC_CRS, "saved raster has a different CRS"
            return raster["density"], float(raster["x0"]), float(raster["y0"])

    density, x0, y0 = road_density_raster(load_counted_roads(), config.ROAD_EXTRACT_BOUNDS)
    raster_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(raster_path, density=density, x0=x0, y0=y0,
                        cell_m=config.ROAD_DENSITY_CELL_M, crs=str(config.METRIC_CRS))  # reused for route sampling
    print(f"saved {raster_path}")
    return density, x0, y0


def urban_subtier(level):
    """Split urban (levels 11-15) on native levels: 11 marginal / 12-14 mid / 15 (cap) dense."""
    subtier = np.select(
        [level >= config.ROAD_DENSITY_MAX_LEVEL,
         level > config.ROAD_DENSITY_MARGINAL_URBAN_LEVEL,
         level == config.ROAD_DENSITY_MARGINAL_URBAN_LEVEL],
        [DENSE_URBAN_SUBTIER, MID_URBAN_SUBTIER, MARGINAL_URBAN_SUBTIER],
        default=None,
    ).astype(object)
    subtier[np.isnan(level)] = None
    return subtier


def road_density_hex_path(subject_lat, subject_lon):
    """The subject's density table, tagged with the filled grid's data layers."""
    return subject_file(config.ROAD_DENSITY_HEX_PATH, subject_lat, subject_lon, all_layers_tags())


def assign_road_density(subject_lat=None, subject_lon=None, should_rebuild=False):
    """Write the subject's filled hex grid with density columns; skipped if it exists (unless should_rebuild).

    The raster is reused when it exists; should_rebuild rebuilds it too.
    """
    subject_lat, subject_lon = resolve_subject(subject_lat, subject_lon)
    density, x0, y0 = build_density_raster(should_rebuild)
    out_path = road_density_hex_path(subject_lat, subject_lon)
    if is_already_built([out_path], should_rebuild):
        return
    hex_grid_gdf = gpd.read_file(subject_file(config.HEX_GRID_POP_PATH, subject_lat, subject_lon, all_layers_tags()))

    centroids = gpd.GeoSeries(
        gpd.points_from_xy(hex_grid_gdf[CENTROID_LON_COL], hex_grid_gdf[CENTROID_LAT_COL]),
        crs=config.GEOGRAPHIC_CRS, index=hex_grid_gdf.index).to_crs(config.METRIC_CRS)
    density_km_km2 = sample_density(density, x0, y0, np.column_stack([centroids.x.to_numpy(), centroids.y.to_numpy()]))

    # hexes whose disk extends past the extract read too low
    # evidence: diagnostics/road_density_distribution.py (no hex is clipped)
    extract_outline = (gpd.GeoSeries([box(*config.ROAD_EXTRACT_BOUNDS).segmentize(config.ROAD_EXTRACT_OUTLINE_STEP_DEG)],
                                     crs=config.GEOGRAPHIC_CRS).to_crs(config.METRIC_CRS).iloc[0])
    is_full_disk = centroids.within(extract_outline) \
        & (centroids.distance(extract_outline.boundary) >= config.ROAD_DENSITY_RADIUS_M)

    level, tier = valhalla_tier(density_km_km2)
    subtier = urban_subtier(level)

    hex_grid_gdf[ROAD_DENSITY_COL] = density_km_km2
    hex_grid_gdf[DENSITY_LEVEL_COL] = level
    hex_grid_gdf[UNCAPPED_LEVEL_COL] = np.floor(density_km_km2 * config.ROAD_DENSITY_LEVEL_SCALE + HALF_UP)
    hex_grid_gdf[DENSITY_TIER_COL] = tier
    hex_grid_gdf[URBAN_SUBTIER_COL] = subtier
    hex_grid_gdf[DENSITY_CLASS_COL] = np.where(pd.notna(subtier), subtier, tier)
    hex_grid_gdf[DISK_CLIPPED_COL] = ~is_full_disk.to_numpy()

    print(f"no density (outside raster): {np.isnan(density_km_km2).sum():,} of {len(density_km_km2):,}")
    print(f"clipped disk: {hex_grid_gdf[DISK_CLIPPED_COL].sum():,}")

    subject_dir(config.ROAD_DENSITY_DIR, subject_lat, subject_lon).mkdir(parents=True, exist_ok=True)
    hex_grid_gdf.to_file(out_path, driver=GPKG_DRIVER)
    print(f"saved {len(hex_grid_gdf):,} hexes to {out_path}")
