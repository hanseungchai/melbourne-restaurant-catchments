"""How are venues spread over the hex grid?

Claim: venues are sparse and concentrated on the grid: few hexes hold any, and counts per hex
(hexes with at least one venue) fall off geometrically.
Where the pipeline relies on it: the hex stage's venue_count column
(hex_tile_construction.build_venue_counts_layer); no rule downstream depends on its shape yet.
Test: zero-venue hexes counted and printed, not histogrammed. Two figures of hexes with >= 1
venue: histogram (linear and log y; geometric decay is a straight line on log y) and a map of hex
centroids coloured by count (log).
Conclusion (run 2026-10-09; same as 2026-10-08): SUPPORTED. 8,959 of 4,078,906 hexes hold >= 1 venue
(0.2%; 18,498 venues; max 26 in one hex, misread as 27 on 2026-10-08). On the log-y histogram
the counts fall on a near-straight line from 1 to ~18 venues (geometric decay); above that only a
handful of hexes remain.

Input: the hex stage's filled grid for the subject below (outputs/hex_grid/). Before plotting, the
run asserts that the subject is still the default subject and that the grid's hex 0 sits on it;
if the subject changed, this conclusion is about a different place and must be redone.

Self-contained: imports nothing from functions/, config.py or the pipeline (CLAUDE.md D1).
"""
import datetime
import math
from pathlib import Path

import matplotlib.pyplot as plt
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

DIAGNOSTIC_NAME = "venue_count_distribution"
RUN_PREFIX = f"{DIAGNOSTIC_NAME}_{datetime.datetime.now():%Y%m%d}"   # one run per day: a same-day rerun replaces that day's files (D1)
FIGURE_SUFFIX = f"{LAYER_TAGS}_{SUBJECT_TAG}.png"
HISTOGRAM_PATH = DIAGNOSTIC_IMG_DIR / f"{RUN_PREFIX}_histogram_{FIGURE_SUFFIX}"
HEATMAP_PATH = DIAGNOSTIC_IMG_DIR / f"{RUN_PREFIX}_heatmap_{FIGURE_SUFFIX}"

# ---------------------------------------------------------------------------
# Grid and figure parameters
# ---------------------------------------------------------------------------
HEX_RADIUS_M = 50               # hex circumradius (100 m vertex to vertex)
EARTH_RADIUS_M = 6_371_000
HISTOGRAM_SIZE_IN = (16, 6)
HEATMAP_SIZE_IN = (12, 12)
CENTROID_MARKER_SIZE = 2
COLOURBAR_SHRINK = 0.6
FIGURE_DPI = 150
SUMMARY_QUANTILES = [0.5, 0.9]   # per-hex quantiles printed for hexes with >= 1 venue

HEX_ID_COL = "hex_id"
CENTROID_LAT_COL = "centroid_lat"
CENTROID_LON_COL = "centroid_lon"
VENUE_COUNT_COL = "venue_count"


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
                                      columns=[CENTROID_LAT_COL, CENTROID_LON_COL, VENUE_COUNT_COL])
    nonzero_df = hexes_df[hexes_df[VENUE_COUNT_COL] > 0]
    counts = nonzero_df[VENUE_COUNT_COL]
    print(f"Total hexes: {len(hexes_df):,}")
    print(f"Hexes with at least 1 venue: {len(nonzero_df):,}")
    print(f"Hexes with 0 venues: {len(hexes_df) - len(nonzero_df):,}")
    quantile_text = ", ".join(f"p{q * 100:g} {value:g}" for q, value in counts.quantile(SUMMARY_QUANTILES).items())
    print(f"Venues assigned: {counts.sum():,}; per hex (hexes >= 1): {quantile_text}, max {counts.max()}")
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)

    bins = range(1, int(counts.max()) + 2)
    fig, axes = plt.subplots(1, 2, figsize=HISTOGRAM_SIZE_IN)
    for ax, colour, is_log_y in [(axes[0], "#1f77b4", False), (axes[1], "#d62728", True)]:
        ax.hist(counts, bins=bins, edgecolor="black", color=colour)
        if is_log_y:
            ax.set_yscale("log")
        scale_label = "log-scale y-axis" if is_log_y else "linear scale"
        ax.set_title(f"Venue count per hex ({scale_label}, hexes with ≥1)")
        ax.set_xlabel("Venues per hex")
        ax.set_ylabel("Count of hexes (log scale)" if is_log_y else "Count of hexes")
        ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(HISTOGRAM_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    print(f"Saved {HISTOGRAM_PATH}")

    fig, ax = plt.subplots(figsize=HEATMAP_SIZE_IN)
    ordered_df = nonzero_df.sort_values(VENUE_COUNT_COL)   # densest hexes drawn last, on top
    points = ax.scatter(ordered_df[CENTROID_LON_COL], ordered_df[CENTROID_LAT_COL], c=ordered_df[VENUE_COUNT_COL],
                        cmap="viridis", norm=LogNorm(vmin=1, vmax=counts.max()),
                        s=CENTROID_MARKER_SIZE, linewidths=0)
    fig.colorbar(points, ax=ax, shrink=COLOURBAR_SHRINK, label="Venue count (log scale)")
    ax.set_aspect(1 / math.cos(math.radians(SUBJECT_LAT)))
    ax.set_title("Hex venue count map (log scale)")
    ax.set_axis_off()
    fig.savefig(HEATMAP_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    print(f"Saved {HEATMAP_PATH}")


if __name__ == "__main__":
    main()
