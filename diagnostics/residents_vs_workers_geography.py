"""Do residents and workers sit in different places on the hex grid?

Claim: residents and workers are different geographies, so one cannot stand in for the other and
the two denominators are kept separate.
Where the pipeline relies on it: DESIGN_pre_spine "Output" (population in two denominators, never
blended); the hex stage carries residents and workers as separate columns
(hex_tile_construction.build_residents_layer / build_workers_layer).
Test: a 2x2 figure on one shared log colour scale. Top row: the full 100 km grid (hex centroids).
Bottom row: 20 km around the subject (hex polygons), where the contrast is visible. Hexes with
0 < value < 1 are grey, so sparse land reads as sparse, not missing.
Conclusion (run 2026-10-09; same as 2026-10-08): SUPPORTED. Residents: 420,606 of 3,903,901
non-zero hexes at >= 1, 5,426,837 total; workers: 346,350 of 4,078,606, 2,569,313 total (same as
the Sep 28 notes, 3a). In the 20 km zoom, workers peak in the CBD (~10^3 per hex) and along a few
corridors, while residents spread evenly across the suburbs at ~10-100 per hex. Large flat worker
patches are area-proportional allocation over big DZNs, not real uniform density.

Input: the hex stage's filled grid for the subject below (outputs/hex_grid/). Before plotting, the
run asserts that the subject is still the default subject and that the grid's hex 0 sits on it;
if the subject changed, this conclusion is about a different place and must be redone.

Self-contained: imports nothing from functions/, config.py or the pipeline (CLAUDE.md D1).
"""
import datetime
import math
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pyogrio
from matplotlib.colors import LogNorm
from shapely.geometry import Point

# ---------------------------------------------------------------------------
# Paths and run naming
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_COORD_PATH = PROJECT_ROOT / "frozen_inputs" / "manual_inputs" / "subject_business_coord.txt"
SUBJECT_LAT = -37.7687014       # the subject this diagnostic's conclusion is about
SUBJECT_LON = 144.9719611
SUBJECT_TAG = "-37.76870_144.97196"
LAYER_TAGS = "res2021_wrk2021_ven20260925"   # census years and venue table of the grid read
HEX_GRID_POP_PATH = (PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT_TAG
                     / f"hex_grid_with_population_{LAYER_TAGS}_{SUBJECT_TAG}.gpkg")
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"

DIAGNOSTIC_NAME = "residents_vs_workers_geography"
RUN_PREFIX = f"{DIAGNOSTIC_NAME}_{datetime.datetime.now():%Y%m%d}"   # one run per day: a same-day rerun replaces that day's files (D1)
FIGURE_PATH = DIAGNOSTIC_IMG_DIR / f"{RUN_PREFIX}_{LAYER_TAGS}_{SUBJECT_TAG}.png"

# ---------------------------------------------------------------------------
# Grid and figure parameters
# ---------------------------------------------------------------------------
HEX_RADIUS_M = 50               # hex circumradius (100 m vertex to vertex)
GRID_RADIUS_M = 100_000         # grid reach from the subject
ZOOM_RADIUS_M = 20_000          # bottom row's window around the subject
EARTH_RADIUS_M = 6_371_000
METRIC_CRS = "EPSG:7855"        # GDA2020 / MGA zone 55, for the disc outlines
DISC_RESOLUTION = 128           # buffer segments per quarter circle
VIEW_PAD_SHARE = 0.02           # margin around each panel's disc, share of its width
SUBLEVEL_COLOUR = "#d9d9d9"     # hexes with 0 < value < 1
CENTROID_MARKER_SIZE = 0.1
COLOURBAR_SHRINK = 0.6
FIGURE_SIZE_IN = (22, 22)
FIGURE_DPI = 150
SUMMARY_QUANTILES = [0.5, 0.9, 0.99]   # per-hex quantiles printed for each layer
METRES_PER_KM = 1000

HEX_ID_COL = "hex_id"
CENTROID_LAT_COL = "centroid_lat"
CENTROID_LON_COL = "centroid_lon"
RESIDENTS_COL = "residents"
WORKERS_COL = "workers"
PANEL_LAYERS = [(RESIDENTS_COL, "Residents"), (WORKERS_COL, "Workers")]


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi, d_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def check_subject():
    """Stop if the default subject moved or the grid isn't this subject's: the figure would
    then show a different place than the conclusion above describes."""
    first_line = SUBJECT_COORD_PATH.read_text(encoding="utf-8").splitlines()[0]
    current_lat, current_lon = (float(text) for text in first_line.split(","))
    assert (current_lat, current_lon) == (SUBJECT_LAT, SUBJECT_LON), (
        f"default subject is now ({current_lat}, {current_lon}), but this diagnostic is about "
        f"({SUBJECT_LAT}, {SUBJECT_LON}): update the subject constants and redo the conclusion")
    assert HEX_GRID_POP_PATH.exists(), f"no hex grid for this subject: {HEX_GRID_POP_PATH}"
    hex0_df = pyogrio.read_dataframe(HEX_GRID_POP_PATH, where=f"{HEX_ID_COL} = 0", read_geometry=False,
                                     columns=[CENTROID_LAT_COL, CENTROID_LON_COL])
    hex0_distance_m = haversine_m(SUBJECT_LAT, SUBJECT_LON,
                                  hex0_df[CENTROID_LAT_COL].iloc[0], hex0_df[CENTROID_LON_COL].iloc[0])
    assert hex0_distance_m <= HEX_RADIUS_M, (
        f"grid's hex 0 is {hex0_distance_m:.1f} m from the subject (max {HEX_RADIUS_M} m): "
        f"{HEX_GRID_POP_PATH.name} was built for a different subject")
    print(f"Subject check passed: ({SUBJECT_LAT}, {SUBJECT_LON}), hex 0 {hex0_distance_m:.1f} m away")


def disc(radius_m, grid_crs):
    """Circle of radius_m around the subject, in the grid's CRS."""
    centre = gpd.GeoSeries([Point(SUBJECT_LON, SUBJECT_LAT)], crs=grid_crs).to_crs(METRIC_CRS)
    return gpd.GeoSeries([centre.iloc[0].buffer(radius_m, resolution=DISC_RESOLUTION)],
                         crs=METRIC_CRS).to_crs(grid_crs)


def set_view(ax, disc_gs):
    """Same limits for both panels in a row (so the geography lines up), true aspect at this
    latitude, no axes."""
    minx, miny, maxx, maxy = disc_gs.total_bounds
    pad = VIEW_PAD_SHARE * (maxx - minx)
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_aspect(1 / math.cos(math.radians(SUBJECT_LAT)))
    ax.set_axis_off()


def print_layer_summary(values, label):
    """Total, non-zero and >= 1 hex counts, and per-hex quantiles over hexes with >= 1."""
    at_least_one = values[values >= 1]
    quantiles = at_least_one.quantile(SUMMARY_QUANTILES)
    quantile_text = ", ".join(f"p{q * 100:g} {value:,.1f}" for q, value in quantiles.items())
    print(f"{label}: total {values.sum():,.0f}; non-zero hexes {(values > 0).sum():,}; hexes >= 1 {len(at_least_one):,}")
    print(f"  per hex (hexes >= 1): {quantile_text}, max {at_least_one.max():,.1f}")


def main():
    check_subject()
    grid_crs = pyogrio.read_info(HEX_GRID_POP_PATH)["crs"]
    full_disc = disc(GRID_RADIUS_M, grid_crs)
    zoom_disc = disc(ZOOM_RADIUS_M, grid_crs)

    # Full grid without polygons: ~4M rows of numbers fit in memory, ~4M polygons don't.
    counts_df = pyogrio.read_dataframe(HEX_GRID_POP_PATH, read_geometry=False,
                                       columns=[CENTROID_LAT_COL, CENTROID_LON_COL, RESIDENTS_COL, WORKERS_COL])
    # Polygons only inside the zoom window.
    zoom_gdf = gpd.read_file(HEX_GRID_POP_PATH, bbox=tuple(zoom_disc.total_bounds),
                             columns=[RESIDENTS_COL, WORKERS_COL])
    print(f"Read {len(counts_df):,} hexes; {len(zoom_gdf):,} in the {ZOOM_RADIUS_M / METRES_PER_KM:.0f} km window")
    for col, label in PANEL_LAYERS:
        print_layer_summary(counts_df[col], label)

    cmap = plt.get_cmap("viridis")
    norm = LogNorm(vmin=1, vmax=max(counts_df[RESIDENTS_COL].max(), counts_df[WORKERS_COL].max()))

    fig, axes = plt.subplots(2, 2, figsize=FIGURE_SIZE_IN, layout="constrained")
    for col_idx, (col, label) in enumerate(PANEL_LAYERS):
        legend_kwds = {"label": f"{label} per hex (log)", "shrink": COLOURBAR_SHRINK}

        ax = axes[0, col_idx]
        sublevel_df = counts_df[(counts_df[col] > 0) & (counts_df[col] < 1)]
        coloured_df = counts_df[counts_df[col] >= 1].sort_values(col)
        ax.scatter(sublevel_df[CENTROID_LON_COL], sublevel_df[CENTROID_LAT_COL],
                   s=CENTROID_MARKER_SIZE, color=SUBLEVEL_COLOUR, linewidths=0)
        points = ax.scatter(coloured_df[CENTROID_LON_COL], coloured_df[CENTROID_LAT_COL], c=coloured_df[col],
                            cmap=cmap, norm=norm, s=CENTROID_MARKER_SIZE, linewidths=0)
        fig.colorbar(points, ax=ax, **legend_kwds)
        full_disc.boundary.plot(ax=ax, color="black", linewidth=0.8)
        set_view(ax, full_disc)
        n_nonzero = int((counts_df[col] > 0).sum())
        ax.set_title(f"{label}: {len(coloured_df):,} of {n_nonzero:,} non-zero hexes coloured, "
                     f"{counts_df[col].sum():,.0f} total\n"
                     f"grey = under 1 per hex; outline = {GRID_RADIUS_M / METRES_PER_KM:.0f} km")

        ax = axes[1, col_idx]
        zoom_gdf[(zoom_gdf[col] > 0) & (zoom_gdf[col] < 1)].plot(color=SUBLEVEL_COLOUR, linewidth=0, ax=ax)
        zoom_gdf[zoom_gdf[col] >= 1].plot(column=col, cmap=cmap, norm=norm, linewidth=0, ax=ax,
                                          legend=True, legend_kwds=legend_kwds)
        set_view(ax, zoom_disc)
        ax.set_title(f"{label}: {ZOOM_RADIUS_M / METRES_PER_KM:.0f} km around subject")

    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    print(f"Saved {FIGURE_PATH}")


if __name__ == "__main__":
    main()
