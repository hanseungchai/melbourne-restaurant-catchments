"""Road density levels (Valhalla's rule) at points and graph nodes: the one rule the hex layer
(road_density), the speed graphs (speed_graphs) and the drive fit (drive_model_fit) share."""
import numpy as np
from pyproj import Transformer

import config
from config import ROAD_DENSITY_CELL_M as CELL_M, ROAD_EXTRACT_BOUNDS

HALF_UP = 0.5                      # floor(x + 0.5): C++ std::round for the non-negative densities here

# Valhalla's density tiers.
RURAL_TIER = "rural"
SUBURBAN_TIER = "suburban"
URBAN_TIER = "urban"

# Keys of the density raster file (road_density.build_density_raster).
RASTER_DENSITY_KEY = "density"
RASTER_X0_KEY = "x0"
RASTER_Y0_KEY = "y0"
RASTER_CRS_KEY = "crs"
RASTER_CELL_M_KEY = "cell_m"

# Node coordinate attributes of the drive graph.
NODE_LON_ATTR = "x"
NODE_LAT_ATTR = "y"


def sample_density(density, x0, y0, xy):
    """Density of the cell under each metric point; NaN outside the raster."""
    cell_m = config.ROAD_DENSITY_CELL_M
    ix = np.floor((xy[:, 0] - x0) / cell_m).astype(int)
    iy = np.floor((xy[:, 1] - y0) / cell_m).astype(int)
    is_inside = (ix >= 0) & (ix < density.shape[0]) & (iy >= 0) & (iy < density.shape[1])
    sampled = np.full(len(xy), np.nan)
    sampled[is_inside] = density[ix[is_inside], iy[is_inside]]
    return sampled


def valhalla_tier(density_km_km2):
    """Valhalla's level (capped) and tier for each density; tier None where density is NaN."""
    level = np.minimum(np.floor(density_km_km2 * config.ROAD_DENSITY_LEVEL_SCALE + HALF_UP),
                       config.ROAD_DENSITY_MAX_LEVEL)
    tier = np.where(level > config.ROAD_DENSITY_MAX_SUBURBAN_LEVEL, URBAN_TIER,
                    np.where(level > config.ROAD_DENSITY_MIN_SUBURBAN_LEVEL, SUBURBAN_TIER, RURAL_TIER)).astype(object)
    tier[np.isnan(density_km_km2)] = None
    return level, tier


def node_levels(drive_graph, density_raster_path=config.ROAD_DENSITY_RASTER_PATH):
    with np.load(density_raster_path) as raster:
        density = raster[RASTER_DENSITY_KEY]
        origin_x_m, origin_y_m = float(raster[RASTER_X0_KEY]), float(raster[RASTER_Y0_KEY])
        crs = str(raster[RASTER_CRS_KEY])
        assert float(raster[RASTER_CELL_M_KEY]) == CELL_M, "raster cell size differs from CELL_M"

    nodes = list(drive_graph.nodes)
    lon = np.array([drive_graph.nodes[node][NODE_LON_ATTR] for node in nodes])
    lat = np.array([drive_graph.nodes[node][NODE_LAT_ATTR] for node in nodes])
    x, y = Transformer.from_crs(config.GEOGRAPHIC_CRS, crs, always_xy=True).transform(lon, lat)

    node_density = sample_density(density, origin_x_m, origin_y_m, np.column_stack([x, y]))
    level, _ = valhalla_tier(node_density)  # same level rule as the hexes
    level = np.asarray(level, dtype=float)

    print(f"  nodes with a density level: {np.isfinite(level).sum():,} / {len(level):,}")

    outside = ~np.isfinite(level)
    if outside.any():
        min_lon, min_lat, max_lon, max_lat = ROAD_EXTRACT_BOUNDS
        outside_lon, outside_lat = lon[outside], lat[outside]
        inside = ((outside_lon > min_lon) & (outside_lon < max_lon)
                  & (outside_lat > min_lat) & (outside_lat < max_lat))
        assert not inside.any(), f"{inside.sum():,} level-less nodes lie inside the extract"
        print(f"  {outside.sum():,} nodes outside the raster -> level {config.OUTSIDE_RASTER_DENSITY_LEVEL:g} (rural)")
        level[outside] = config.OUTSIDE_RASTER_DENSITY_LEVEL

    return dict(zip(nodes, level))
