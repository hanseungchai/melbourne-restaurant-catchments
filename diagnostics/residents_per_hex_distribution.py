"""How are residents spread across hexes?

Claim: residents per hex are strongly right-skewed: most populated hexes hold a few residents and
a thin tail holds many, so per-hex resident counts are read on a log scale.
Where the pipeline relies on it: the hex stage's residents column
(hex_tile_construction.build_residents_layer); the log colour scales of the hex figures. No rule
downstream depends on its shape yet.
Test: hexes with >= 1 resident. Histogram of the bulk (<= 100 residents, linear) and of the full
range (log-spaced bins, log x); map of hex centroids coloured by residents (log).
Conclusion (run 2026-10-09; same as 2026-10-08): SUPPORTED, with a nuance. 420,606 hexes hold >= 1
resident: median 10.6, max 1,147, 99.9% hold <= 100. On log x the shape is not a simple decay: a
flat shoulder from 1 to ~8 residents, a peak at ~15-25 (typical suburban density), and a thin
tail to ~10^3 (towers). The tail spans three orders of magnitude, which is why the figures use
log colour scales.

Input: the hex stage's filled grid for the subject below (outputs/hex_grid/). Before plotting, the
run asserts that the subject is still the default subject and that the grid's hex 0 sits on it;
if the subject changed, this conclusion is about a different place and must be redone.

Self-contained: imports nothing from functions/, config.py or the pipeline (CLAUDE.md D1).
"""
import datetime
import math
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pyogrio
from matplotlib.colors import LogNorm

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

DIAGNOSTIC_NAME = "residents_per_hex_distribution"
RUN_PREFIX = f"{DIAGNOSTIC_NAME}_{datetime.datetime.now():%Y%m%d}"   # one run per day: a same-day rerun replaces that day's files (D1)
FIGURE_SUFFIX = f"{LAYER_TAGS}_{SUBJECT_TAG}.png"
HISTOGRAM_PATH = DIAGNOSTIC_IMG_DIR / f"{RUN_PREFIX}_histogram_{FIGURE_SUFFIX}"
HEATMAP_PATH = DIAGNOSTIC_IMG_DIR / f"{RUN_PREFIX}_heatmap_{FIGURE_SUFFIX}"

# ---------------------------------------------------------------------------
# Grid and figure parameters
# ---------------------------------------------------------------------------
HEX_RADIUS_M = 50               # hex circumradius (100 m vertex to vertex)
EARTH_RADIUS_M = 6_371_000
BULK_MAX_RESIDENTS = 100        # left panel's upper limit (the main bulk)
HISTOGRAM_BINS = 50
HISTOGRAM_SIZE_IN = (16, 6)
HEATMAP_SIZE_IN = (12, 12)
HEATMAP_COLOURS = ["#d62728", "#ffff66", "#2ca02c"]   # red -> yellow -> green
CENTROID_MARKER_SIZE = 0.1
COLOURBAR_SHRINK = 0.6
FIGURE_DPI = 150

HEX_ID_COL = "hex_id"
CENTROID_LAT_COL = "centroid_lat"
CENTROID_LON_COL = "centroid_lon"
RESIDENTS_COL = "residents"


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi, d_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def check_subject():
    """Stop if the default subject moved or the grid isn't this subject's: the figures would
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


def main():
    check_subject()
    hexes_df = pyogrio.read_dataframe(HEX_GRID_POP_PATH, read_geometry=False,
                                      columns=[CENTROID_LAT_COL, CENTROID_LON_COL, RESIDENTS_COL])
    populated_df = hexes_df[hexes_df[RESIDENTS_COL] >= 1]
    residents = populated_df[RESIDENTS_COL]
    print(f"Hexes with >= 1 resident: {len(populated_df):,} of {len(hexes_df):,}")
    print(f"Residents per such hex: median {residents.median():.1f}, max {residents.max():,.0f}; "
          f"{(residents <= BULK_MAX_RESIDENTS).mean():.1%} hold <= {BULK_MAX_RESIDENTS}")
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=HISTOGRAM_SIZE_IN)
    axes[0].hist(residents[residents <= BULK_MAX_RESIDENTS], bins=HISTOGRAM_BINS,
                 edgecolor="black", color="#1f77b4")
    axes[0].set_title(f"Residents per hex: 1-{BULK_MAX_RESIDENTS} (zoomed, main bulk)")
    axes[0].set_xlabel("Residents")
    axes[1].hist(residents, bins=np.logspace(np.log10(residents.min()), np.log10(residents.max()), HISTOGRAM_BINS),
                 edgecolor="black", color="#d62728")
    axes[1].set_xscale("log")
    axes[1].set_title("Residents per hex: full range (log-scale x-axis)")
    axes[1].set_xlabel("Residents (log scale)")
    for ax in axes:
        ax.set_ylabel("Count of hexes")
        ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(HISTOGRAM_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    print(f"Saved {HISTOGRAM_PATH}")

    # Centroid scatter, not polygons: ~400k polygons are sub-pixel at this extent anyway.
    cmap = mcolors.LinearSegmentedColormap.from_list("red_yellow_green", HEATMAP_COLOURS)
    ordered_df = populated_df.sort_values(RESIDENTS_COL)
    fig, ax = plt.subplots(figsize=HEATMAP_SIZE_IN)
    points = ax.scatter(ordered_df[CENTROID_LON_COL], ordered_df[CENTROID_LAT_COL], c=ordered_df[RESIDENTS_COL],
                        cmap=cmap, norm=LogNorm(vmin=1, vmax=residents.max()),
                        s=CENTROID_MARKER_SIZE, linewidths=0)
    fig.colorbar(points, ax=ax, shrink=COLOURBAR_SHRINK, label="Residents (log scale)")
    ax.set_aspect(1 / math.cos(math.radians(SUBJECT_LAT)))
    ax.set_title("Hex residents map (log scale)")
    ax.set_axis_off()
    fig.savefig(HEATMAP_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    print(f"Saved {HEATMAP_PATH}")


if __name__ == "__main__":
    main()
