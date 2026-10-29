"""Are the drive graph's posted speed limits clean, and how much of the network carries one?

Claim: every raw maxspeed tag on the drive graph is a km/h integer between 1 and 130, written bare
("60") or with a km/h unit ("60kmh", "50 km/h"), so the unit-aware parser reads every tagged edge
and none silently falls through to its class default.
Where the pipeline relies on it: functions/osm_tags.parse_maxspeed (unit-aware). The legacy
construct_map.parse_maxspeed read bare integers only ("Every value in this extract is a bare
integer in km/h"); construct_map adopts the unit-aware parser when its stage is cleaned. Untagged
edges take a default by highway class there.
Test: every distinct raw maxspeed value parsed with both rules (copies below); values that fail
either rule are listed. Per highway class: street segments, tagged share, median tagged limit
(saved as CSV). Figure: the drive network, line width stepped by posted limit (SPEED_WIDTH_STEPS),
fastest drawn last; an untagged segment takes the median tagged limit of its class and is drawn
fainter. Two panels: VIEW_RADIUS_M and ZOOM_RADIUS_M around the subject.
Conclusion (run 2026-10-09; same as 2026-10-08): SUPPORTED for the unit-aware rule: all 24 distinct raw values
(832,690 tagged street segments) parse. NOT SUPPORTED for the legacy bare-integer rule: 6,861
segments (0.8% of tagged) carry a unit suffix ("50kmh" 6,138, "60kmh" 640, "80kmh" 46, "50 km/h"
15, "100kmh" 13, "70kmh" 8, "40kmh" 1) and fell to their class default; hence the unit-aware parser.
Coverage: 31.1% of 2,679,547 street segments tagged; motorway 99.9%, trunk 94.6%, primary 87.2%,
secondary 63.5%, tertiary 46.5%, residential 34.6%, unclassified 12.2%, service 3.6%. Every class
has tagged edges (class medians in the CSV), so no segment is left without a drawn limit.

Input: the map_construction stage's drive graph (outputs/road_graphs/drive_graph.gpickle). Street
segments = drive edges with the two directions of a two-way street counted once.

Self-contained: imports nothing from functions/, config.py or the pipeline (CLAUDE.md D1).
"""
import datetime
import math
import pickle
from pathlib import Path

import contextily as cx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

# ---------------------------------------------------------------------------
# Paths and run naming
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DRIVE_GRAPH_PATH = PROJECT_ROOT / "outputs" / "road_graphs" / "drive_graph.gpickle"
SUBJECT_COORD_PATH = PROJECT_ROOT / "frozen_inputs" / "manual_inputs" / "subject_business_coord.txt"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"

DIAGNOSTIC_NAME = "drive_speed_limits"
RUN_PREFIX = f"{DIAGNOSTIC_NAME}_{datetime.datetime.now():%Y%m%d}"   # one run per day: a same-day rerun replaces that day's files (D1)
FIGURE_PATH = DIAGNOSTIC_IMG_DIR / f"{RUN_PREFIX}_map.png"
CLASS_TABLE_PATH = DIAGNOSTIC_DATA_DIR / f"{RUN_PREFIX}_by_highway_class.csv"

# ---------------------------------------------------------------------------
# Parsing rules (copies of functions/osm_tags.parse_maxspeed and the legacy construct_map one)
# ---------------------------------------------------------------------------
MIN_VALID_LIMIT_KMH = 1
MAX_VALID_LIMIT_KMH = 130
KMH_UNIT_SUFFIXES = ("km/h", "kmh")

# ---------------------------------------------------------------------------
# Figure parameters
# ---------------------------------------------------------------------------
# (upper bound km/h, line width pt): a segment takes the first step whose bound its limit doesn't exceed.
# Victorian limits come in fixed values; width roughly doubles per step from 50 to 80.
SPEED_WIDTH_STEPS = [
    (40, 0.05),    # lanes, school and shopping zones, living streets
    (50, 0.10),    # built-up default: most residential streets
    (60, 0.20),    # collectors, arterials
    (80, 0.40),    # main arterials, outer suburbs
    (100, 0.70),   # rural highways, urban freeways
    (130, 1.00),   # rural freeways (110)
]
SPEED_STEP_LABELS = ["≤ 40", "50", "60", "70–80", "90–100", "110"]
TAGGED_ALPHA = 0.9             # segment with its own maxspeed tag
INFERRED_ALPHA = 0.35          # segment given its class's median tagged limit
NO_LIMIT_WIDTH = 0.05          # segment whose class has no tagged edge at all
NO_LIMIT_COLOUR = "#999999"
DRIVE_COLOUR = "#08306b"
VIEW_RADIUS_M = 100_000        # full panel: box half-width around the subject
ZOOM_RADIUS_M = 10_000         # zoom panel
METRES_PER_DEGREE_LAT = 111_320
FIGURE_SIZE_IN = (24, 12)
FIGURE_DPI = 200
SHOULD_ADD_BASEMAP = True      # free Esri grey canvas tiles (network fetch, no API key)
LEGEND_LINE_SCALE = 4          # legend lines drawn this many times wider, so the thin steps show
LEGEND_FREE_RECT = (0, 0.05, 1, 1)   # panels fill the figure above the bottom 5%, where the legend sits

NODE_LON_ATTR = "x"
NODE_LAT_ATTR = "y"
EDGE_HIGHWAY_ATTR = "highway"
EDGE_MAXSPEED_ATTR = "maxspeed"


def parse_maxspeed_bare(raw):
    """Legacy rule (construct_map.parse_maxspeed): bare integer km/h in range, else None."""
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except ValueError:
        return None
    return value if MIN_VALID_LIMIT_KMH <= value <= MAX_VALID_LIMIT_KMH else None


def parse_maxspeed(raw):
    """Unit-aware rule (functions/osm_tags.parse_maxspeed): bare or km/h-suffixed integer in range."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    for suffix in KMH_UNIT_SUFFIXES:
        if text.endswith(suffix):
            text = text[:-len(suffix)].strip()
            break
    try:
        value = int(text)
    except ValueError:
        return None
    return value if MIN_VALID_LIMIT_KMH <= value <= MAX_VALID_LIMIT_KMH else None


def read_subject_location():
    first_line = SUBJECT_COORD_PATH.read_text(encoding="utf-8").splitlines()[0]
    lat_text, lon_text = first_line.split(",")
    return float(lat_text), float(lon_text)


def load_street_segments():
    """One row per street segment: end coordinates, highway class, raw maxspeed."""
    print(f"Loading {DRIVE_GRAPH_PATH} ...")
    with open(DRIVE_GRAPH_PATH, "rb") as f:
        drive_graph = pickle.load(f)
    print(f"Drive graph: {drive_graph.number_of_nodes():,} nodes, {drive_graph.number_of_edges():,} directed edges")
    rows = []
    for u, v, data in drive_graph.edges(data=True):
        if u > v and drive_graph.has_edge(v, u):
            continue   # two-way street: keep one direction
        node_u, node_v = drive_graph.nodes[u], drive_graph.nodes[v]
        rows.append((node_u[NODE_LON_ATTR], node_u[NODE_LAT_ATTR], node_v[NODE_LON_ATTR], node_v[NODE_LAT_ATTR],
                     data.get(EDGE_HIGHWAY_ATTR), data.get(EDGE_MAXSPEED_ATTR)))
    del drive_graph
    segments_df = pd.DataFrame(rows, columns=["lon_a", "lat_a", "lon_b", "lat_b", "highway", "maxspeed_raw"])
    print(f"Street segments: {len(segments_df):,}")
    return segments_df


def check_raw_values(segments_df):
    """Print the raw maxspeed values each rule fails on; return the unit-aware rule's failing count."""
    raw_counts = segments_df["maxspeed_raw"].dropna().value_counts()
    print(f"\nDistinct raw maxspeed values: {len(raw_counts)}")
    print(f"Segments with a raw maxspeed tag: {raw_counts.sum():,} of {len(segments_df):,}")
    failing_count = 0
    for rule_name, rule in [("legacy bare-integer rule", parse_maxspeed_bare), ("unit-aware rule", parse_maxspeed)]:
        failing = raw_counts[[rule(raw) is None for raw in raw_counts.index]]
        if failing.empty:
            print(f"Values failing the {rule_name}: none")
        else:
            print(f"Values failing the {rule_name}: {len(failing)} distinct, {failing.sum():,} segments")
            print(failing.to_string())
        failing_count = int(failing.sum())
    return failing_count


def class_table(segments_df):
    """Per highway class: segments, tagged share, median tagged limit."""
    table_df = segments_df.groupby("highway").agg(
        segments=("limit_kmh", "size"),
        tagged=("limit_kmh", "count"),
        median_tagged_limit_kmh=("limit_kmh", "median"),
    )
    table_df["tagged_share"] = table_df["tagged"] / table_df["segments"]
    return table_df.sort_values("segments", ascending=False)


def width_for_limit(limits_kmh):
    """Stepped line width for each limit (NaN -> NO_LIMIT_WIDTH)."""
    widths = np.full(len(limits_kmh), NO_LIMIT_WIDTH)
    assigned = np.isnan(limits_kmh)
    for upper_kmh, width in SPEED_WIDTH_STEPS:
        in_step = ~assigned & (limits_kmh <= upper_kmh)
        widths[in_step] = width
        assigned |= in_step
    return widths


def view_box(subject_lat, subject_lon, radius_m):
    d_lat = radius_m / METRES_PER_DEGREE_LAT
    d_lon = radius_m / (METRES_PER_DEGREE_LAT * math.cos(math.radians(subject_lat)))
    return subject_lon - d_lon, subject_lon + d_lon, subject_lat - d_lat, subject_lat + d_lat


def draw_panel(ax, segments_df, subject_lat, subject_lon, radius_m, title):
    lon_min, lon_max, lat_min, lat_max = view_box(subject_lat, subject_lon, radius_m)
    in_view = (segments_df[["lon_a", "lon_b"]].min(axis=1) <= lon_max) & (segments_df[["lon_a", "lon_b"]].max(axis=1) >= lon_min) \
        & (segments_df[["lat_a", "lat_b"]].min(axis=1) <= lat_max) & (segments_df[["lat_a", "lat_b"]].max(axis=1) >= lat_min)
    view_df = segments_df[in_view].sort_values("width")   # fastest drawn last, on top
    print(f"{title}: {len(view_df):,} segments in view")
    for is_tagged, has_limit, colour, alpha in [(False, False, NO_LIMIT_COLOUR, INFERRED_ALPHA),
                                                (False, True, DRIVE_COLOUR, INFERRED_ALPHA),
                                                (True, True, DRIVE_COLOUR, TAGGED_ALPHA)]:
        part_df = view_df[(view_df["is_tagged"] == is_tagged) & (view_df["draw_limit_kmh"].notna() == has_limit)]
        lines = np.stack([part_df[["lon_a", "lat_a"]].to_numpy(), part_df[["lon_b", "lat_b"]].to_numpy()], axis=1)
        ax.add_collection(LineCollection(lines, linewidths=part_df["width"].to_numpy(),
                                         colors=colour, alpha=alpha, capstyle="round"))
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_aspect(1 / math.cos(math.radians(subject_lat)))
    if SHOULD_ADD_BASEMAP:
        cx.add_basemap(ax, crs="EPSG:4326", source=cx.providers.Esri.WorldGrayCanvas, attribution_size=6)
    ax.plot(subject_lon, subject_lat, marker="*", color="red", markersize=12, markeredgecolor="black", zorder=5)
    ax.set_title(title)
    ax.set_axis_off()


def main():
    subject_lat, subject_lon = read_subject_location()
    segments_df = load_street_segments()
    n_failing = check_raw_values(segments_df)

    segments_df["limit_kmh"] = [parse_maxspeed(raw) for raw in segments_df["maxspeed_raw"]]
    segments_df["limit_kmh"] = segments_df["limit_kmh"].astype(float)
    segments_df["is_tagged"] = segments_df["limit_kmh"].notna()
    table_df = class_table(segments_df)
    print(f"\nTagged share overall: {segments_df['is_tagged'].mean():.1%}")
    print(table_df.to_string(float_format=lambda x: f"{x:.3f}"))
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    table_df.to_csv(CLASS_TABLE_PATH)
    print(f"Saved {CLASS_TABLE_PATH}")

    class_medians = table_df["median_tagged_limit_kmh"]
    segments_df["draw_limit_kmh"] = segments_df["limit_kmh"].fillna(segments_df["highway"].map(class_medians))
    segments_df["width"] = width_for_limit(segments_df["draw_limit_kmh"].to_numpy())
    no_limit = segments_df["draw_limit_kmh"].isna().sum()
    print(f"Segments drawn with an inferred limit: {(~segments_df['is_tagged']).sum() - no_limit:,}; "
          f"in a class with no tagged edge (grey): {no_limit:,}")

    fig, axes = plt.subplots(1, 2, figsize=FIGURE_SIZE_IN)
    draw_panel(axes[0], segments_df, subject_lat, subject_lon, VIEW_RADIUS_M,
               f"Drive network by posted speed limit ({VIEW_RADIUS_M // 1000} km around subject)")
    draw_panel(axes[1], segments_df, subject_lat, subject_lon, ZOOM_RADIUS_M,
               f"Zoom: {ZOOM_RADIUS_M // 1000} km around subject")
    handles = [Line2D([], [], color=DRIVE_COLOUR, linewidth=width * LEGEND_LINE_SCALE, label=f"{label} km/h")
               for (_, width), label in zip(SPEED_WIDTH_STEPS, SPEED_STEP_LABELS)]
    handles += [Line2D([], [], color=DRIVE_COLOUR, alpha=INFERRED_ALPHA, linewidth=2, label="limit inferred (class median)"),
                Line2D([], [], color=NO_LIMIT_COLOUR, linewidth=2, label="no tagged edge in class")]
    fig.tight_layout(rect=LEGEND_FREE_RECT)
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False,
               title=f"Line width = posted limit (legend widths x{LEGEND_LINE_SCALE})")
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    print(f"Saved {FIGURE_PATH}")

    verdict = "SUPPORTED" if n_failing == 0 else f"NOT SUPPORTED ({n_failing:,} segments fail the parse rule)"
    print(f"\nClaim (every raw maxspeed parses as 1-130 km/h, bare or km/h unit): {verdict}")


if __name__ == "__main__":
    main()
