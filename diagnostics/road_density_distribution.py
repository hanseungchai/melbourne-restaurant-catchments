"""How is road density spread over the hex grid, and does every hex get it from a full disk?

Claim: every hex gets its road density from a full ROAD_DENSITY_RADIUS_M disk inside the road
extract: no hex lies outside the density raster and none has a disk clipped by the extract's edge,
so no density reads low for lack of mapped roads.
Where the pipeline relies on it: road_density.assign_road_density (density_disk_clipped column);
later stages read each hex's density level and tier (DESIGN_pre_spine "Road density"; drive speed models).
Test: count hexes with NaN density and with density_disk_clipped. Descriptive: density quantiles
weighted by hex, residents and workers; density-class shares under each weight; the share within
+-1 km/km² of the urban cutoff (15 km/km²); CBD (Melbourne GPO) density as a sanity check. Figures:
histogram of density under each weight, and its cumulative share with Valhalla's tier cutoffs;
map of hex centroids coloured by density class (full grid, and ZOOM_RADIUS_M around the subject).
Conclusion (run 2026-10-09): SUPPORTED. All 4,078,906 hexes have a density, none with a clipped
disk (the 100 km grid sits well inside the extract). Density is near zero for most hexes (median
0.95 km/km²; 92% rural) but not for people: median 12.5 km/km² for residents and 13.8 for workers.
By class, residents are 18% rural, 61% suburban, 21% urban (4.1% dense); workers 15% / 47% / 38%
(20.9% dense). 17% of residents and 15% of workers sit within +-1 km/km² of the urban cutoff, so
tier assignment is sensitive there. CBD (GPO) reads 26.1 km/km², urban.

Input: the map_construction stage's road-density hex table for the subject below
(outputs/road_density/) and its raster (outputs/road_density/road_density_raster.npz). Before
reading, the run asserts that the subject is still the default subject and that the table's hex 0
sits on it; if the subject changed, this conclusion is about a different place and must be redone.

Self-contained: imports nothing from functions/, config.py or the pipeline (CLAUDE.md D1).
"""
import datetime
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio
from pyproj import Transformer

# ---------------------------------------------------------------------------
# Paths and run naming
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_COORD_PATH = PROJECT_ROOT / "frozen_inputs" / "manual_inputs" / "subject_business_coord.txt"
SUBJECT_LAT = -37.7687014       # the subject this diagnostic's conclusion is about
SUBJECT_LON = 144.9719611
SUBJECT_TAG = "-37.76870_144.97196"
LAYER_TAGS = "res2021_wrk2021_ven20260925"   # census years and venue table of the grid read
ROAD_DENSITY_DIR = PROJECT_ROOT / "outputs" / "road_density"
ROAD_DENSITY_HEX_PATH = ROAD_DENSITY_DIR / SUBJECT_TAG / f"road_density_hex_{LAYER_TAGS}_{SUBJECT_TAG}.gpkg"
ROAD_DENSITY_RASTER_PATH = ROAD_DENSITY_DIR / "road_density_raster.npz"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"

DIAGNOSTIC_NAME = "road_density_distribution"
RUN_PREFIX = f"{DIAGNOSTIC_NAME}_{datetime.datetime.now():%Y%m%d}"   # one run per day: a same-day rerun replaces that day's files (D1)
FILE_SUFFIX = f"{LAYER_TAGS}_{SUBJECT_TAG}"
HISTOGRAM_PATH = DIAGNOSTIC_IMG_DIR / f"{RUN_PREFIX}_histogram_{FILE_SUFFIX}.png"
MAP_PATH = DIAGNOSTIC_IMG_DIR / f"{RUN_PREFIX}_map_{FILE_SUFFIX}.png"
CDF_PATH = DIAGNOSTIC_IMG_DIR / f"{RUN_PREFIX}_cdf_{FILE_SUFFIX}.png"
CLASS_SHARE_TABLE_PATH = DIAGNOSTIC_DATA_DIR / f"{RUN_PREFIX}_class_shares_{FILE_SUFFIX}.csv"

# ---------------------------------------------------------------------------
# Density rule (copies of config.py "Road density") and figure parameters
# ---------------------------------------------------------------------------
ROAD_DENSITY_RADIUS_M = 2_000
LEVEL_SCALE = 0.7               # level = round(km/km² * 0.7)
MAX_LEVEL = 15
MIN_SUBURBAN_LEVEL = 5
MAX_SUBURBAN_LEVEL = 10
MARGINAL_URBAN_LEVEL = 11
HALF_UP = 0.5
# Density (km/km²) where the level steps up past each boundary level: (level + 0.5) / 0.7.
TIER_CUTOFFS_KM_KM2 = {name: (level + HALF_UP) / LEVEL_SCALE for name, level in
                       [("suburban", MIN_SUBURBAN_LEVEL), ("urban", MAX_SUBURBAN_LEVEL),
                        ("mid urban", MARGINAL_URBAN_LEVEL), ("dense urban", MAX_LEVEL - 1)]}
URBAN_CUTOFF_KM_KM2 = TIER_CUTOFFS_KM_KM2["urban"]
NEAR_CUTOFF_KM_KM2 = 1.0        # "near the urban cutoff" = within this of it
SUMMARY_QUANTILES = [0.05, 0.25, 0.50, 0.75, 0.95]
HISTOGRAM_BIN_COUNT = 60
HISTOGRAM_MIN_TOP_KM_KM2 = 30.0  # histogram x range reaches at least this
CDF_GRID_POINTS = 1001
HISTOGRAM_SIZE_IN = (9, 10)
CDF_SIZE_IN = (9, 5)
MAP_SIZE_IN = (16, 8)
ZOOM_RADIUS_M = 20_000          # right panel's box half-width around the subject
METRES_PER_DEGREE_LAT = 111_320
FULL_MARKER_SIZE = 1.0          # scatter marker area (pt²): full grid (one pixel is ~2 hexes here)
ZOOM_MARKER_SIZE = 1.5          # zoom panel: about one hex across
MAP_DPI = 120
# density class -> colour, drawn in this order (densest on top)
CLASS_COLOURS = {"rural": "#e0e0e0", "suburban": "#fed976", "marginal_urban": "#fd8d3c",
                 "mid_urban": "#e31a1c", "dense_urban": "#800026"}
CUTOFF_LINE_STYLE = {"color": "grey", "lw": 0.8, "ls": ":"}
CUTOFF_LABEL_Y = 1.01           # cutoff labels sit above the curves
CUTOFF_LABEL_STAGGER = 0.05
CDF_Y_TOP = 1.1
FIGURE_DPI = 150

CBD_CHECK_LAT = -37.8136        # Melbourne GPO: should read urban
CBD_CHECK_LON = 144.9631
GEOGRAPHIC_CRS = "EPSG:4326"

HEX_RADIUS_M = 50               # hex circumradius (100 m vertex to vertex)
EARTH_RADIUS_M = 6_371_000

HEX_ID_COL = "hex_id"
CENTROID_LAT_COL = "centroid_lat"
CENTROID_LON_COL = "centroid_lon"
RESIDENTS_COL = "residents"
WORKERS_COL = "workers"
ROAD_DENSITY_COL = "road_density_km_km2"
DENSITY_CLASS_COL = "density_class"
DISK_CLIPPED_COL = "density_disk_clipped"
DENSITY_AXIS_LABEL = f"road density (km/km²), {ROAD_DENSITY_RADIUS_M // 1000} km disk"


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi, d_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def check_subject():
    """Stop if the default subject moved or the table isn't this subject's: the numbers would
    then describe a different place than the conclusion above."""
    first_line = SUBJECT_COORD_PATH.read_text(encoding="utf-8").splitlines()[0]
    current_lat, current_lon = (float(text) for text in first_line.split(","))
    assert (current_lat, current_lon) == (SUBJECT_LAT, SUBJECT_LON), (
        f"default subject is now ({current_lat}, {current_lon}), but this diagnostic is about "
        f"({SUBJECT_LAT}, {SUBJECT_LON}): update the subject constants and redo the conclusion")
    assert ROAD_DENSITY_HEX_PATH.exists(), f"no density table for this subject: {ROAD_DENSITY_HEX_PATH}"
    hex0_df = pyogrio.read_dataframe(ROAD_DENSITY_HEX_PATH, where=f"{HEX_ID_COL} = 0", read_geometry=False,
                                     columns=[CENTROID_LAT_COL, CENTROID_LON_COL])
    hex0_distance_m = haversine_m(SUBJECT_LAT, SUBJECT_LON,
                                  hex0_df[CENTROID_LAT_COL].iloc[0], hex0_df[CENTROID_LON_COL].iloc[0])
    assert hex0_distance_m <= HEX_RADIUS_M, (
        f"table's hex 0 is {hex0_distance_m:.1f} m from the subject (max {HEX_RADIUS_M} m): "
        f"{ROAD_DENSITY_HEX_PATH.name} was built for a different subject")
    print(f"Subject check passed: ({SUBJECT_LAT}, {SUBJECT_LON}), hex 0 {hex0_distance_m:.1f} m away")


def weighted_quantiles(values, weights, quantiles):
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    return np.interp(np.asarray(quantiles) * cumulative[-1], cumulative, values[order])


def cbd_density():
    """Density of the raster cell under the CBD check point, and its tier."""
    with np.load(ROAD_DENSITY_RASTER_PATH) as raster:
        density, x0, y0, cell_m = raster["density"], float(raster["x0"]), float(raster["y0"]), float(raster["cell_m"])
        metric_crs = str(raster["crs"])
    x, y = Transformer.from_crs(GEOGRAPHIC_CRS, metric_crs, always_xy=True).transform(CBD_CHECK_LON, CBD_CHECK_LAT)
    value = density[int(math.floor((x - x0) / cell_m)), int(math.floor((y - y0) / cell_m))]
    level = min(math.floor(value * LEVEL_SCALE + HALF_UP), MAX_LEVEL)
    tier = "urban" if level > MAX_SUBURBAN_LEVEL else "suburban" if level > MIN_SUBURBAN_LEVEL else "rural"
    return value, tier


def draw_class_map(hexes_df):
    """Hex centroids coloured by density class: the full grid, and a zoom box around the subject."""
    d_lat = ZOOM_RADIUS_M / METRES_PER_DEGREE_LAT
    d_lon = ZOOM_RADIUS_M / (METRES_PER_DEGREE_LAT * math.cos(math.radians(SUBJECT_LAT)))
    zoom_box = (SUBJECT_LON - d_lon, SUBJECT_LON + d_lon, SUBJECT_LAT - d_lat, SUBJECT_LAT + d_lat)
    is_in_zoom = hexes_df[CENTROID_LON_COL].between(zoom_box[0], zoom_box[1])         & hexes_df[CENTROID_LAT_COL].between(zoom_box[2], zoom_box[3])
    fig, axes = plt.subplots(1, 2, figsize=MAP_SIZE_IN)
    for ax, panel_df, marker_size, title in [
            (axes[0], hexes_df, FULL_MARKER_SIZE, "Density class per hex, full grid"),
            (axes[1], hexes_df[is_in_zoom], ZOOM_MARKER_SIZE, f"Zoom: {ZOOM_RADIUS_M // 1000} km around subject")]:
        for density_class, colour in CLASS_COLOURS.items():
            class_df = panel_df[panel_df[DENSITY_CLASS_COL] == density_class]
            ax.scatter(class_df[CENTROID_LON_COL], class_df[CENTROID_LAT_COL], s=marker_size, c=colour,
                       marker="s", linewidths=0, rasterized=True)
        ax.plot(SUBJECT_LON, SUBJECT_LAT, marker="*", color="cyan", markersize=12, markeredgecolor="black")
        ax.set_aspect(1 / math.cos(math.radians(SUBJECT_LAT)))
        ax.set_title(title)
        ax.set_axis_off()
    axes[1].set_xlim(zoom_box[0], zoom_box[1])
    axes[1].set_ylim(zoom_box[2], zoom_box[3])
    handles = [plt.Line2D([], [], marker="s", linestyle="", color=colour, markersize=10, label=name.replace("_", " "))
               for name, colour in CLASS_COLOURS.items()]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(MAP_PATH, dpi=MAP_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {MAP_PATH}")


def main():
    check_subject()
    hexes_df = pyogrio.read_dataframe(ROAD_DENSITY_HEX_PATH, read_geometry=False,
                                      columns=[CENTROID_LAT_COL, CENTROID_LON_COL, ROAD_DENSITY_COL,
                                               DISK_CLIPPED_COL, RESIDENTS_COL,
                                               WORKERS_COL, DENSITY_CLASS_COL])
    n_hexes = len(hexes_df)
    n_no_density = int(hexes_df[ROAD_DENSITY_COL].isna().sum())
    n_clipped = int(hexes_df[DISK_CLIPPED_COL].astype(bool).sum())
    print(f"Hexes: {n_hexes:,}; no density (outside raster): {n_no_density:,}; disk clipped by the extract: {n_clipped:,}")

    full_df = hexes_df[~hexes_df[DISK_CLIPPED_COL].astype(bool) & hexes_df[ROAD_DENSITY_COL].notna()]
    density = full_df[ROAD_DENSITY_COL].to_numpy(dtype=float)
    weights = {"hex": np.ones(len(full_df)),
               "residents": full_df[RESIDENTS_COL].fillna(0).to_numpy(dtype=float),
               "workers": full_df[WORKERS_COL].fillna(0).to_numpy(dtype=float)}
    print(f"Hexes with zero density: {(density == 0).sum():,}")

    quantile_labels = "/".join(f"p{q * 100:g}" for q in SUMMARY_QUANTILES)
    print(f"\nDensity (km/km²) {quantile_labels}, by weight:")
    for name, weight in weights.items():
        print(f"  {name:>9}: {weighted_quantiles(density, weight, SUMMARY_QUANTILES).round(2)}")

    shares_df = pd.DataFrame({name: pd.Series(weight, index=full_df.index).groupby(full_df[DENSITY_CLASS_COL]).sum()
                              / weight.sum() for name, weight in weights.items()})
    print("\nDensity-class share, by weight:")
    print(shares_df.round(3).to_string())
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    shares_df.to_csv(CLASS_SHARE_TABLE_PATH)
    print(f"Saved {CLASS_SHARE_TABLE_PATH}")

    is_near_cutoff = np.abs(density - URBAN_CUTOFF_KM_KM2) <= NEAR_CUTOFF_KM_KM2
    print(f"\nWithin +-{NEAR_CUTOFF_KM_KM2:g} km/km² of the urban cutoff ({URBAN_CUTOFF_KM_KM2:g}):")
    for name, weight in weights.items():
        print(f"  {name:>9}: {weight[is_near_cutoff].sum() / weight.sum():.1%}")

    cbd_value, cbd_tier = cbd_density()
    print(f"\nCBD (Melbourne GPO) density: {cbd_value:.1f} km/km² -> {cbd_tier}")

    cutoffs = list(TIER_CUTOFFS_KM_KM2.values())
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
    bins = np.linspace(0, max(HISTOGRAM_MIN_TOP_KM_KM2, np.ceil(density.max())), HISTOGRAM_BIN_COUNT + 1)
    fig, axes = plt.subplots(len(weights), 1, figsize=HISTOGRAM_SIZE_IN, sharex=True)
    for ax, (name, weight) in zip(axes, weights.items()):
        ax.hist(density, bins=bins, weights=weight, histtype="step")
        for cutoff in cutoffs:
            ax.axvline(cutoff, **CUTOFF_LINE_STYLE)
        ax.set_ylabel(f"{name} per bin")
    axes[0].set_title("Road density per hex, weighted by hex, residents and workers (dotted: tier cutoffs)")
    axes[-1].set_xlabel(DENSITY_AXIS_LABEL)
    fig.tight_layout()
    fig.savefig(HISTOGRAM_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {HISTOGRAM_PATH}")

    order = np.argsort(density)
    sorted_density = density[order]
    grid = np.linspace(0, np.ceil(sorted_density.max()), CDF_GRID_POINTS)
    count_at_or_below = np.searchsorted(sorted_density, grid, side="right")
    fig, ax = plt.subplots(figsize=CDF_SIZE_IN)
    print("\nShare strictly below each tier cutoff, by weight:")
    for name, weight in weights.items():
        cumulative = np.concatenate([[0.0], np.cumsum(weight[order])]) / weight.sum()
        ax.plot(grid, cumulative[count_at_or_below], label=name)
        below = {f"{cutoff:.1f}": round(float(cumulative[np.searchsorted(sorted_density, cutoff, side="left")]), 3)
                 for cutoff in cutoffs}
        print(f"  {name:>9}: {below}")
    for i, (tier_name, cutoff) in enumerate(TIER_CUTOFFS_KM_KM2.items()):
        ax.axvline(cutoff, **CUTOFF_LINE_STYLE)
        label_y = CUTOFF_LABEL_Y + (i % 2) * CUTOFF_LABEL_STAGGER   # alternate heights: 15.0 and 16.4 sit close
        ax.text(cutoff, label_y, f"{tier_name} {cutoff:.1f}", ha="center", va="bottom", fontsize=7)
    ax.set_ylim(0, CDF_Y_TOP)
    ax.set_xlabel(DENSITY_AXIS_LABEL)
    ax.set_ylabel("cumulative share")
    ax.legend(loc="lower right")
    ax.grid(True, lw=0.3, alpha=0.5)
    fig.tight_layout()
    fig.savefig(CDF_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {CDF_PATH}")

    draw_class_map(hexes_df)

    verdict = "SUPPORTED" if n_no_density == 0 and n_clipped == 0 else \
        f"NOT SUPPORTED ({n_no_density:,} hexes without density, {n_clipped:,} with a clipped disk)"
    print(f"\nClaim (every hex's density comes from a full {ROAD_DENSITY_RADIUS_M // 1000} km disk inside the extract): {verdict}")


if __name__ == "__main__":
    main()
