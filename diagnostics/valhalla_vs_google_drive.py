"""Valhalla vs Google drive times on the 4,000 validation pairs.

Claim: an off-the-shelf routing engine (Valhalla) does not clearly beat the project's custom
drive graph (M2) at predicting Google drive times.
Where the pipeline relies on it: DESIGN_pre_spine, the "Graph" line of the drive method (custom
DiGraph, "Not the Valhalla or OSRM engine"); the test is the one proposed in
docs/stale_project_mds/session_docs_to_20261013/claude_PLATICA_valhalla_position_Sep_21.md section 6.
Two Valhalla variants: "defaults" (out of the box: tagged maxspeeds as posted, a built-in
urban table for untagged roads) and "speed_table" (Valhalla's density-aware default speeds from
the OpenStreetMapSpeeds JSON, AU/VIC row). M2 is not recomputed here: its per-pair
times for these pairs exist (data/hex_grid/runs/20261001/od_dense_fringe_beta10.csv, flagship
beta = 10) but are not read; M2's recorded results (DESIGN_pre_spine "Drive model") are quoted for reference.
Conclusion (run 2026-10-07, 3,999 pairs, Google traffic-aware target): close to M2, not
better. defaults: 89.6% at the 20-min cut after scaling, rho +0.50 (40% faster than Google raw).
speed_table: 90.5% scaled (89.8% raw), rho +0.24. M2 (quoted): ~92%, rho ~+0.19. The claim
holds. Write-up: docs/stale_project_mds/session_docs_to_20261013/claude_PLATICA_valhalla_engine_test_Oct_7.md.

Step 4 (road mix, run 2026-10-08): what drives speed_table's remaining distance bias? Each
route re-read edge by edge (road class, density, junction time). Conclusion: junctions per km
(Spearman -0.39 with % error, negative in every distance band); jointly with road mix and
density, the distance coefficient reverses (+4.4 -> -2.5 pct points per SD). Not corridor
share, not density; Valhalla's own junction cost is small (median 2.8% of route time).
Write-up: docs/stale_project_mds/session_docs_to_20261013/claude_PLATICA_valhalla_road_mix_Oct_8.md.

Step 4c (junctions, run 2026-10-08, 3,958 trace-matched pairs): does Valhalla under-price
unsignalised junctions? Pre-registered criteria (see the step 4c constants) all fail for both
counts: unsignalised per km passes in 1 of 5 distance bands, likely give-way in 0 of 5; with tag
splits in the fit neither CI excludes 0; implied missing seconds per junction are negative
(-0.25 s, -5.3 s). No flat per-junction delay is proposed; the question closes. Not
pre-registered, exploratory only: signals (+7.7 s each beyond Valhalla's charge) and tag
splits per km (+2.1 s each; a stand-in for mapping detail / urban-ness) carry the effect.

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
Run with the PyCharm interpreter, which has pyvalhalla installed.
"""

import datetime
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import osmium
import pandas as pd
from scipy.stats import rankdata, spearmanr
from valhalla import PYVALHALLA_DIR, Actor, ValhallaError, get_config

# --- paths -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OSM_PBF_PATH = (PROJECT_ROOT / "frozen_inputs" / "osm_extract"
                / "planet_143.599,-38.893_146.327,-36.735.osm.pbf")
SPEED_TABLE_JSON_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_speeds" / "default_speeds.json"
GOOGLE_ETA_CSV_PATH = (PROJECT_ROOT / "frozen_inputs" / "routes_drive_eta_20260930"
                       / "od_sample_pairs_google_estimates.csv")
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"

DIAGNOSTIC_NAME = "valhalla_vs_google_drive"
RUN_START = datetime.datetime.now()
RUN_DATE = RUN_START.strftime("%Y%m%d")
RUN_TIME = RUN_START.strftime("%H%M")     # keeps same-day reruns in separate folders

# --- Valhalla variants -------------------------------------------------------------------
# Each variant gets its own tiles and routes. Value: path of Valhalla's default-speeds JSON,
# or None for the built-in speeds.
VARIANT_SPEED_TABLES = {
    "defaults": None,
    "speed_table": SPEED_TABLE_JSON_PATH,
}
# valhalla_build_tiles crashes (access violation, 0xC0000005) on the full 2,702-entry table
# but builds fine on its Australian entries alone (tested 2026-10-07). Valhalla only ever
# looks up the rows for the admin areas it finds (here AU and AU/VIC), so the build is
# given an AU-only copy, written into the variant's tiles folder.
SPEED_TABLE_COUNTRY_KEY = "iso3166-1"
SPEED_TABLE_COUNTRY = "AU"
SPEED_TABLE_COPY_FILENAME = "default_speeds_au_only.json"

# --- tile build (step 1) -----------------------------------------------------------------
# Everything one build writes lives in one dated folder: <name>_<date>_<time>_<variant>_tiles/
TILES_FOLDER_SUFFIX = "_tiles"
TILE_SUBDIR_NAME = "tiles"                 # Valhalla's graph tiles
ADMIN_DB_FILENAME = "admin.sqlite"         # country/state areas -> drive side, speed-table row
ADMIN_PBF_FILENAME = "drive_side_admin.osm.pbf"  # the hand-made boundaries below
CONFIG_FILENAME = "valhalla_config.json"
BUILD_LOG_FILENAME = "build_log.txt"
BUILD_DONE_FILENAME = "build_done.json"    # written only after both tools succeed
# Bumped whenever the build steps change, so builds made the old way are not reused.
# 1: admins from the extract (Australia clipped -> 0 admin areas -> drive on right).
# 2: admins from a hand-made drive-on-left Australia box.
# 3: adds a hand-made Victoria box (state), so the speed table can pick its AU/VIC row.
BUILD_RECIPE = 3
# The Valhalla executables shipped inside pyvalhalla. Called directly: pyvalhalla's own
# "python -m valhalla <tool>" launcher looks for the tool on PATH first and fails with
# "Can't find executable". Like that launcher, put the bundled DLL folder on PATH.
VALHALLA_BIN_DIR = Path(PYVALHALLA_DIR) / "bin"
VALHALLA_DLL_DIR = Path(PYVALHALLA_DIR).parent / "pyvalhalla.libs"

# --- hand-made admin boundaries ----------------------------------------------------------
# The extract is a box cut around Melbourne, so it holds only fragments of the Australia and
# Victoria boundaries; valhalla_build_admins skips both as "degenerate", inserts 0 admin
# areas, and Valhalla falls back to drive-on-right, mirroring its turn costs. Instead,
# admins are built from hand-made boundaries: two nested boxes around the extract, tagged as
# OSM tags Australia (country) and Victoria (state). Their only jobs: "this area drives on
# the left" and "this is AU/VIC" for the speed table. Both are true throughout the extract.
EXTRACT_BBOX_LON_LAT = (143.599, -38.893, 146.327, -36.735)  # min lon, min lat, max lon, max lat
COUNTRY_BOX_MARGIN_DEG = 0.2    # Australia box overhang beyond the extract on every side
STATE_BOX_MARGIN_DEG = 0.1      # Victoria box: smaller, so it lies strictly inside Australia
COUNTRY_BOUNDARY_TAGS = {
    "type": "boundary",
    "boundary": "administrative",
    "admin_level": "2",
    "name": "Australia",
    "name:en": "Australia",
    "ISO3166-1": "AU",
    "ISO3166-1:alpha2": "AU",
    "driving_side": "left",
}
STATE_BOUNDARY_TAGS = {
    "type": "boundary",
    "boundary": "administrative",
    "admin_level": "4",
    "name": "Victoria",
    "name:en": "Victoria",
    "ISO3166-2": "AU-VIC",
}

# --- routing (step 2) --------------------------------------------------------------------
ROUTES_FILE_SUFFIX = "_routes.csv"
VALHALLA_COSTING = "auto"            # Valhalla's car profile, default settings (off-the-shelf)
VALHALLA_UNITS = "kilometers"        # unit of the returned trip length
METRES_PER_KM = 1000
PROGRESS_EVERY_N_PAIRS = 1000
# Columns read from the Google CSV: the coordinates actually sent to Google.
PAIR_ID_COL = "draw_no"
ORIGIN_LAT_COL, ORIGIN_LON_COL = "g_o_lat", "g_o_lon"
DEST_LAT_COL, DEST_LON_COL = "g_d_lat", "g_d_lon"
# Columns written to the routes CSV.
VALHALLA_DURATION_COL = "valhalla_duration_sec"
VALHALLA_DISTANCE_COL = "valhalla_distance_m"
VALHALLA_ERROR_COL = "valhalla_error"      # empty when the pair routed
TILES_BUILD_COL = "tiles_build"            # tiles folder the routes came from

# --- comparison (step 3) -----------------------------------------------------------------
# Same measures as the Oct 4 M2 evaluation (map_pathing._eval_model; DESIGN_pre_spine "Drive model"):
# classification at the 20-min cut is the primary objective; rho and signed median % error
# guard against systematic bias.
METRICS_FILE_SUFFIX = "_metrics.csv"
BANDS_FILE_SUFFIX = "_bands.csv"
GOOGLE_TRAFFIC_COL = "google_drive_duration_sec"   # primary target (what M2 is judged on)
GOOGLE_STATIC_COL = "static_duration_sec"          # Google's no-traffic time, secondary
CUT_S = 1200.0                 # the 20-min reachability cut (map_pathing.BOUNDARY_S)
N_BOOT = 2000                  # bootstrap resamples for the rho CI (map_pathing.S4_N_BOOT)
BOOT_SEED = 20260922           # map_pathing.S4_SEED
EARTH_RADIUS_M = 6_371_008.8   # mean Earth radius, for straight-line (haversine) distance
PERCENT = 100
SECONDS_PER_MIN = 60
# Google-time bands for the signed median: around the 20-min cut, where errors flip
# classifications. Chosen here; the 4,000-pair run has no project band edges.
GOOGLE_TIME_BAND_EDGES_MIN = [0, 10, 15, 20, 25, 30, np.inf]
# M2's recorded results, quoted for reference only (not recomputed here). DESIGN_pre_spine
# "Drive model", Oct 4: flagship M2 dense_fringe at beta = 10, out-of-fold.
M2_REFERENCE_ACCURACY_AT_CUT = "~92%"
M2_REFERENCE_GLOBAL_RHO = "~+0.19"

# --- road mix (step 4) -------------------------------------------------------------------
# What drives speed_table's remaining distance bias (rho +0.24): corridor roads, area
# density, or junction costs? Each route is re-read edge by edge with trace_attributes
# ("edge_walk" follows the route's own shape exactly, no map matching).
ROUTE_MIX_VARIANT = "speed_table"
ROUTE_MIX_FILE_SUFFIX = "_route_mix.csv"
TRACE_SHAPE_MATCH = "edge_walk"
# edge_walk fails on a few routes ("failed to find exact route match"). Those fall back to
# map matching; the route-mix CSV records which one was used, so fallback pairs can be
# checked (trace time and length should still equal the route's) or left out.
TRACE_FALLBACK_SHAPE_MATCH = "walk_or_snap"
TRACE_ATTRIBUTES = ["edge.length", "edge.road_class", "edge.speed", "edge.density",
                    "node.elapsed_time", "node.transition_time"]
# Valhalla's road classes, in its own order; "service_other" covers service roads and the rest.
VALHALLA_ROAD_CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary",
                         "unclassified", "residential", "service_other"]
CORRIDOR_ROAD_CLASSES = ["motorway", "trunk", "primary"]   # the fast through-roads
SECONDS_PER_HOUR = 3600
# Columns written to the route-mix CSV (plus one length column per road class).
TRACE_TIME_COL = "trace_time_sec"                # last node's elapsed time; should equal the route time
EDGE_TIME_COL = "edge_time_sec"                  # sum of edge length / edge speed: time spent driving
TRANSITION_TIME_COL = "transition_time_sec"      # sum of node transition times: junction and turn costs
MEAN_DENSITY_COL = "mean_density"                # length-weighted mean of Valhalla's edge density (0-15)
CORRIDOR_SHARE_COL = "corridor_length_share"     # share of route length on CORRIDOR_ROAD_CLASSES
N_EDGES_COL = "n_edges"
SHAPE_MATCH_COL = "trace_shape_match"            # TRACE_SHAPE_MATCH, or the fallback when it failed
# Step 4b, the analysis. Target: signed % error of raw speed_table times vs Google
# traffic-aware duration (scaling changes no rank measure). Corridor share over motorway,
# trunk and primary is 89% of all route km (Melbourne's arterials are primary), so it barely
# varies between pairs; motorway share is the main corridor measure, motorway + trunk a variant.
ROUTE_MIX_SPEARMAN_FILE_SUFFIX = "_route_mix_spearman.csv"
ROUTE_MIX_OLS_FILE_SUFFIX = "_route_mix_ols.csv"
# In 41 pairs the trace's time differs from the route's by more than 1% (lengths always agree
# within 0.33%); left out of the main pair set, kept in the "all" sensitivity set.
MAX_TRACE_TIME_MISMATCH_FRACTION = 0.01
N_DISTANCE_BANDS = 5           # haversine-km quantile bands for the within-band correlations
MOTORWAY_CLASSES = ["motorway"]
MOTORWAY_TRUNK_CLASSES = ["motorway", "trunk"]
# Predictor columns derived per pair.
DISTANCE_KM_COL = "haversine_km"
MOTORWAY_SHARE_COL = "motorway_length_share"
MOTORWAY_TRUNK_SHARE_COL = "motorway_trunk_length_share"
EDGES_PER_KM_COL = "edges_per_km"                # junction frequency: a new edge starts at every node
TRANSITION_SHARE_COL = "transition_time_share"   # junction time / route time, Valhalla's own pricing
PCT_ERROR_COL = "pct_error"
MIX_PREDICTOR_COLS = [MOTORWAY_SHARE_COL, MEAN_DENSITY_COL, EDGES_PER_KM_COL, TRANSITION_SHARE_COL]
SPEARMAN_PREDICTOR_COLS = [DISTANCE_KM_COL, MOTORWAY_SHARE_COL, MOTORWAY_TRUNK_SHARE_COL,
                           MEAN_DENSITY_COL, EDGES_PER_KM_COL, TRANSITION_SHARE_COL]
# Joint fits on standardised predictors: does adding road mix, density and junctions pull
# the distance coefficient toward 0?
OLS_MODELS = {
    "distance_only": [DISTANCE_KM_COL],
    "mix_only": MIX_PREDICTOR_COLS,
    "distance_and_mix": [DISTANCE_KM_COL] + MIX_PREDICTOR_COLS,
    "distance_and_mix_motorway_trunk": [DISTANCE_KM_COL, MOTORWAY_TRUNK_SHARE_COL]
                                       + MIX_PREDICTOR_COLS[1:],
}
ROAD_CLASS_LENGTH_COL_PREFIX = "length_km_"

# --- junctions (step 4c) -----------------------------------------------------------------
# Step 4 found edges per km as the strongest predictor of the error, but an edge ends at
# every node, including nodes where only a tag changes. Step 4c counts real junctions (a
# drivable side road meets the route), splits them by type, and reads Valhalla's own charge
# per junction (node transition time).
#
# Pre-registration, written 2026-10-08 before the run. A flat per-junction delay earns a
# test on M2 (after the rebuild, once M2 residuals open; DESIGN.md Q2) only if ALL hold:
#   C1. Within the N_DISTANCE_BANDS haversine-km bands, the unsignalised junctions per km
#       (or the likely-give-way junctions per km) have a positive coefficient on the residual
#       (Google minus Valhalla, so positive = Valhalla too fast where junctions are frequent)
#       with a 95% bootstrap CI excluding 0, in at least MIN_BANDS_PASSING of the bands.
#   C2. The effect survives with real junction counts in place of edges per km, and with
#       tag splits per km in the same fit (so it isn't mapping detail): full-sample
#       coefficient positive, CI excluding 0.
#   C3. The implied missing seconds per junction, applied to a typical route near the cut
#       (Google time within NEAR_CUT_WINDOW_S of CUT_S), shifts its time by at least X%.
#       X not set before the run (Ciara to set); the shift is reported.
# Neither count (unsignalised or likely give-way) was named primary before the run; both are
# reported. If any criterion fails: record it, no junction delay is proposed, question closes.
# Valhalla charges here describe Valhalla's bias only, not M2's.
JUNCTION_COUNTS_FILE_SUFFIX = "_junction_counts.csv"   # one row per pair
JUNCTIONS_FILE_SUFFIX = "_junctions.csv"               # one row per real junction
JUNCTION_OLS_FILE_SUFFIX = "_junction_ols.csv"
JUNCTION_CHARGE_FILE_SUFFIX = "_junction_charge.csv"   # Valhalla's transition time by type
JUNCTION_TRACE_ATTRIBUTES = TRACE_ATTRIBUTES + [
    "edge.use", "edge.traffic_signal", "edge.roundabout", "edge.internal_intersection",
    "node.traffic_signal", "node.intersecting_edge.driveability",
    "node.intersecting_edge.use", "node.intersecting_edge.road_class"]
# A side road counts only if a car can drive on it and its use is not one of these. Side
# roads that are footways or crossings have no driveability and drop out on that alone.
EXCLUDED_SIDE_ROAD_USES = {"driveway", "alley", "parking_aisle", "drive_through",
                           "emergency_access", "service_road"}
# Side-road driveability is relative to the side road leaving the node: "forward" = away from
# the junction, "backward" = towards it (checked 2026-10-08 on motorway ramps: off-ramps
# "forward", median 7 deg from onward travel; on-ramps "backward", median 175 deg).
# Traffic that can arrive from a side road is what the route may have to give way to.
CONFLICTING_DRIVEABILITY = {"backward", "both"}
# Class ranking for the give-way proxy, highest class first (same order as Valhalla's).
ROAD_CLASS_RANK = {road_class: rank for rank, road_class in enumerate(VALHALLA_ROAD_CLASSES)}
# Signals: the edge flag (a signal at the end of that edge), not the node flag; in the
# probe route the edge flag marked 14 edges, the node flag 2 nodes. A junction counts as
# signalised if either flag is set on any of its nodes or edges.
# One junction can span several nodes: the two halves of a divided-road crossing (joined by
# internal_intersection edges), and every node around a roundabout. These merge into one.
# Junction types, first match wins:
JUNCTION_SIGNALISED = "signalised"
JUNCTION_ROUNDABOUT = "roundabout"
# Approach edge's class lower than the highest class among conflicting side roads and the
# edge the route leaves on: the route likely gives way (minor into major). Proxy only; the
# tiles have no stop / give-way tags. A right turn off a major road (giving way to oncoming
# traffic) lands in "priority", which biases the give-way vs priority gap towards 0.
JUNCTION_GIVE_WAY = "likely_give_way"
JUNCTION_PRIORITY = "likely_priority"         # major or equal class
JUNCTION_TYPES = [JUNCTION_SIGNALISED, JUNCTION_ROUNDABOUT, JUNCTION_GIVE_WAY, JUNCTION_PRIORITY]
UNSIGNALISED_TYPES = [JUNCTION_GIVE_WAY, JUNCTION_PRIORITY]   # roundabouts kept separate
TAG_SPLIT = "tag_split"                       # node with no counted side road; not a junction
N_JUNCTIONS_COL_PREFIX = "n_"                 # n_signalised, ..., n_tag_split per pair
PER_KM_COL_SUFFIX = "_per_km"
N_UNSIGNALISED_COL = "n_unsignalised"
RESIDUAL_PCT_COL = "residual_pct"             # 100 * (Google - Valhalla) / Google
RESIDUAL_SEC_COL = "residual_sec"             # Google - Valhalla, seconds
ROUTE_KM_COL = "route_km"
MOTORWAY_KM_COL = "motorway_km"
MIN_BANDS_PASSING = 3                         # C1: "a majority" of the 5 bands
NEAR_CUT_WINDOW_S = 120.0                     # C3: Google time within 2 min of the 20-min cut


# --- step 1: tiles -----------------------------------------------------------------------
def find_existing_tiles_dir(variant):
    """Return the newest tiles folder of this variant built with the current recipe, or None."""
    candidates = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{DIAGNOSTIC_NAME}_*{TILES_FOLDER_SUFFIX}"))
    finished = []
    for folder in candidates:
        done_path = folder / BUILD_DONE_FILENAME
        if not done_path.exists():
            continue
        build_done = json.loads(done_path.read_text())
        if build_done["recipe"] == BUILD_RECIPE and build_done.get("variant") == variant:
            finished.append(folder)
    return finished[-1] if finished else None


def box_corners(margin_deg):
    """Corners (lon, lat) of the extract's bounding box grown by margin_deg on every side."""
    min_lon, min_lat, max_lon, max_lat = EXTRACT_BBOX_LON_LAT
    return [(min_lon - margin_deg, min_lat - margin_deg),
            (max_lon + margin_deg, min_lat - margin_deg),
            (max_lon + margin_deg, max_lat + margin_deg),
            (min_lon - margin_deg, max_lat + margin_deg)]


def write_admin_pbf(pbf_path):
    """Write the hand-made OSM file: a Victoria box inside an Australia box, as boundary relations."""
    boundaries = [(COUNTRY_BOX_MARGIN_DEG, COUNTRY_BOUNDARY_TAGS),
                  (STATE_BOX_MARGIN_DEG, STATE_BOUNDARY_TAGS)]
    nodes, ways, relations = [], [], []
    next_node_id = 1
    for boundary_id, (margin_deg, tags) in enumerate(boundaries, start=1):
        node_ids = []
        for lon_lat in box_corners(margin_deg):
            nodes.append(osmium.osm.mutable.Node(id=next_node_id, location=lon_lat, tags={}))
            node_ids.append(next_node_id)
            next_node_id += 1
        # A closed ring repeats its first node at the end.
        ways.append(osmium.osm.mutable.Way(id=boundary_id, nodes=node_ids + node_ids[:1], tags={}))
        relations.append(osmium.osm.mutable.Relation(
            id=boundary_id, members=[("w", boundary_id, "outer")], tags=tags))
    # OSM files list all nodes, then ways, then relations.
    with osmium.SimpleWriter(str(pbf_path)) as writer:
        for node in nodes:
            writer.add_node(node)
        for way in ways:
            writer.add_way(way)
        for relation in relations:
            writer.add_relation(relation)


def run_valhalla_tool(tool_name, config_path, input_pbf_path, log_file):
    """Run one Valhalla executable (shipped inside pyvalhalla) on an OSM file."""
    command = [str(VALHALLA_BIN_DIR / f"{tool_name}.exe"),
               "-c", str(config_path), str(input_pbf_path)]
    env_with_dlls = dict(os.environ, PATH=str(VALHALLA_DLL_DIR) + os.pathsep + os.environ["PATH"])
    print(f"  running {tool_name} ...")
    subprocess.run(command, stdout=log_file, stderr=subprocess.STDOUT, env=env_with_dlls,
                   check=True)


def build_tiles(variant):
    """Step 1: build Valhalla's admin database and routing tiles for one variant.

    Admins come from the hand-made boundaries; tiles from the frozen OSM extract.
    Reuses an existing build of this variant and recipe if there is one; never overwrites one.
    Returns the path of the Valhalla config JSON that points at the tiles.
    """
    existing_dir = find_existing_tiles_dir(variant)
    if existing_dir is not None:
        build_date = existing_dir.name[len(DIAGNOSTIC_NAME) + 1:].split("_")[0]
        print(f"[{variant}] reusing tiles built {build_date}: {existing_dir.name}")
        return existing_dir / CONFIG_FILENAME

    tiles_root_dir = (DIAGNOSTIC_DATA_DIR
                      / f"{DIAGNOSTIC_NAME}_{RUN_DATE}_{RUN_TIME}_{variant}{TILES_FOLDER_SUFFIX}")
    tile_dir = tiles_root_dir / TILE_SUBDIR_NAME
    tile_dir.mkdir(parents=True, exist_ok=False)   # exist_ok=False: never overwrite a build
    print(f"[{variant}] building tiles in {tiles_root_dir.name}")

    admin_pbf_path = tiles_root_dir / ADMIN_PBF_FILENAME
    write_admin_pbf(admin_pbf_path)

    valhalla_config = get_config(tile_extract="", tile_dir=tile_dir, verbose=True)
    valhalla_config["mjolnir"]["admin"] = str(tiles_root_dir / ADMIN_DB_FILENAME)
    valhalla_config["mjolnir"]["timezone"] = ""         # not needed: no time-dependent speeds
    valhalla_config["mjolnir"]["traffic_extract"] = ""  # no traffic data: free-flow routing only
    speed_table_path = VARIANT_SPEED_TABLES[variant]
    if speed_table_path is not None:
        speed_table_entries = json.loads(speed_table_path.read_text())
        country_entries = [entry for entry in speed_table_entries
                           if entry.get(SPEED_TABLE_COUNTRY_KEY) == SPEED_TABLE_COUNTRY]
        speed_table_copy_path = tiles_root_dir / SPEED_TABLE_COPY_FILENAME
        speed_table_copy_path.write_text(json.dumps(country_entries, indent=1))
        valhalla_config["mjolnir"]["default_speeds_config"] = str(speed_table_copy_path)

    config_path = tiles_root_dir / CONFIG_FILENAME
    with open(config_path, "w") as config_file:
        json.dump(valhalla_config, config_file, indent=2)

    with open(tiles_root_dir / BUILD_LOG_FILENAME, "w") as log_file:
        run_valhalla_tool("valhalla_build_admins", config_path, admin_pbf_path, log_file)
        run_valhalla_tool("valhalla_build_tiles", config_path, OSM_PBF_PATH, log_file)

    n_tiles = sum(1 for _ in tile_dir.rglob("*.gph"))
    # The marker is what makes a build reusable, so an interrupted build is never picked up.
    build_done = {"recipe": BUILD_RECIPE, "variant": variant, "n_tiles": n_tiles}
    (tiles_root_dir / BUILD_DONE_FILENAME).write_text(json.dumps(build_done) + "\n")
    print(f"[{variant}] built {n_tiles} tiles")
    return config_path


# --- step 2: routes ----------------------------------------------------------------------
def find_existing_routes_path(tiles_build_name):
    """Return the newest routes CSV made from the given tiles build, or None."""
    candidates = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{DIAGNOSTIC_NAME}_*{ROUTES_FILE_SUFFIX}"))
    matching = [path for path in candidates
                if pd.read_csv(path, usecols=[TILES_BUILD_COL])[TILES_BUILD_COL].eq(tiles_build_name).all()]
    return matching[-1] if matching else None


def route_one_pair(actor, origin_lat, origin_lon, dest_lat, dest_lon):
    """Route one origin-destination pair; return (duration_sec, distance_m, error_message)."""
    request = {
        "locations": [{"lat": origin_lat, "lon": origin_lon},
                      {"lat": dest_lat, "lon": dest_lon}],
        "costing": VALHALLA_COSTING,
        "units": VALHALLA_UNITS,
        "directions_type": "none",     # times and distances only, no turn-by-turn text
    }
    try:
        summary = actor.route(request)["trip"]["summary"]
    except ValhallaError as error:
        return None, None, str(error)
    return summary["time"], summary["length"] * METRES_PER_KM, ""


def route_all_pairs(variant, config_path):
    """Step 2: route every Google validation pair through one Valhalla variant.

    Free-flow routing: Valhalla has no traffic data, so departure times are not sent.
    Unroutable pairs are kept, with the error message. Reuses an existing routes CSV made
    from the same tiles build; never overwrites one.
    Returns the routes DataFrame.
    """
    tiles_build_name = Path(config_path).parent.name
    existing_path = find_existing_routes_path(tiles_build_name)
    if existing_path is not None:
        print(f"[{variant}] reusing routes from {existing_path.name}")
        return pd.read_csv(existing_path, keep_default_na=False)

    pairs_df = pd.read_csv(GOOGLE_ETA_CSV_PATH)
    actor = Actor(str(config_path))
    route_rows = []
    for i, pair in enumerate(pairs_df.itertuples(index=False)):
        duration_sec, distance_m, error_message = route_one_pair(
            actor, getattr(pair, ORIGIN_LAT_COL), getattr(pair, ORIGIN_LON_COL),
            getattr(pair, DEST_LAT_COL), getattr(pair, DEST_LON_COL))
        route_rows.append({PAIR_ID_COL: getattr(pair, PAIR_ID_COL),
                           VALHALLA_DURATION_COL: duration_sec,
                           VALHALLA_DISTANCE_COL: distance_m,
                           VALHALLA_ERROR_COL: error_message,
                           TILES_BUILD_COL: tiles_build_name})
        if (i + 1) % PROGRESS_EVERY_N_PAIRS == 0:
            print(f"  routed {i + 1} / {len(pairs_df)}")

    routes_df = pd.DataFrame(route_rows)
    routes_path = (DIAGNOSTIC_DATA_DIR
                   / f"{DIAGNOSTIC_NAME}_{RUN_DATE}_{RUN_TIME}_{variant}{ROUTES_FILE_SUFFIX}")
    routes_df.to_csv(routes_path, index=False)
    n_failed = (routes_df[VALHALLA_ERROR_COL] != "").sum()
    print(f"[{variant}] routed {len(routes_df) - n_failed} of {len(routes_df)} pairs "
          f"({n_failed} failed) -> {routes_path.name}")
    return routes_df


# --- step 3: comparison ------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line distance in km between arrays of points (the distance rho is taken on)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a)) / METRES_PER_KM


def auc_at_cut(predicted_s, google_s):
    """AUC for 'Google says inside the cut', scored by shorter predicted time (rank formula)."""
    is_inside = google_s < CUT_S
    ranks = rankdata(-predicted_s)
    n_inside, n_outside = is_inside.sum(), (~is_inside).sum()
    return (ranks[is_inside].sum() - n_inside * (n_inside + 1) / 2) / (n_inside * n_outside)


def score_predictions(predicted_s, google_s, distance_km, boot_index):
    """All comparison measures for one set of predictions against one Google target."""
    pct_error = PERCENT * (predicted_s - google_s) / google_s
    rho = spearmanr(distance_km, pct_error).statistic
    boot_rhos = [spearmanr(distance_km[i], pct_error[i]).statistic for i in boot_index]
    rho_ci_low, rho_ci_high = np.percentile(boot_rhos, [2.5, 97.5])
    is_correct = (predicted_s < CUT_S) == (google_s < CUT_S)
    return {"accuracy_at_cut": is_correct.mean(),
            "auc_at_cut": auc_at_cut(predicted_s, google_s),
            "medape_pct": np.median(np.abs(pct_error)),
            "signed_median_pct": np.median(pct_error),
            "rho": rho, "rho_ci_low": rho_ci_low, "rho_ci_high": rho_ci_high}


def compare_to_google(routes_by_variant):
    """Step 3: score each Valhalla variant against Google, raw and scaled, on both targets.

    Scaled = Valhalla times x ALPHA, ALPHA = median(Google / Valhalla), M2's own scaling rule
    (map_pathing._fit_scale). Fitted in-sample on all routed pairs (one parameter on ~4,000
    pairs; M2's quoted numbers are out-of-fold over 2 folds). Scaling changes accuracy,
    MedAPE and the signed median, but not AUC or rho, which depend only on rank order.
    Pairs unroutable in any variant are left out of all, so variants share one pair set.
    Returns the metrics DataFrame.
    """
    pairs_df = pd.read_csv(GOOGLE_ETA_CSV_PATH)
    for variant, routes_df in routes_by_variant.items():
        variant_cols = routes_df[[PAIR_ID_COL, VALHALLA_DURATION_COL, VALHALLA_ERROR_COL]]
        pairs_df = pairs_df.merge(variant_cols.add_suffix(f"_{variant}").rename(
            columns={f"{PAIR_ID_COL}_{variant}": PAIR_ID_COL}), on=PAIR_ID_COL, validate="one_to_one")
    is_routed = np.logical_and.reduce(
        [pairs_df[f"{VALHALLA_ERROR_COL}_{variant}"] == "" for variant in routes_by_variant])
    print(f"Comparing {is_routed.sum()} pairs routed in every variant; {(~is_routed).sum()} left out: "
          f"{pairs_df.loc[~is_routed, PAIR_ID_COL].tolist()}")
    pairs_df = pairs_df[is_routed]

    distance_km = haversine_km(pairs_df[ORIGIN_LAT_COL].to_numpy(), pairs_df[ORIGIN_LON_COL].to_numpy(),
                               pairs_df[DEST_LAT_COL].to_numpy(), pairs_df[DEST_LON_COL].to_numpy())
    n_pairs = len(pairs_df)
    boot_index = np.random.default_rng(BOOT_SEED).integers(0, n_pairs, size=(N_BOOT, n_pairs))

    metric_rows, band_rows = [], []
    for variant in routes_by_variant:
        valhalla_s = pd.to_numeric(pairs_df[f"{VALHALLA_DURATION_COL}_{variant}"]).to_numpy(float)
        for target_col in (GOOGLE_TRAFFIC_COL, GOOGLE_STATIC_COL):
            google_s = pairs_df[target_col].to_numpy(float)
            alpha = float(np.median(google_s / valhalla_s))
            for scaling, predicted_s in (("raw", valhalla_s), ("scaled", alpha * valhalla_s)):
                metric_rows.append({"variant": variant, "target": target_col, "scaling": scaling,
                                    "alpha": alpha if scaling == "scaled" else 1.0,
                                    "n_pairs": n_pairs,
                                    **score_predictions(predicted_s, google_s, distance_km, boot_index)})
                if target_col == GOOGLE_TRAFFIC_COL and scaling == "scaled":
                    time_band = pd.cut(google_s / SECONDS_PER_MIN, GOOGLE_TIME_BAND_EDGES_MIN,
                                       right=False)
                    pct_error = pd.Series(PERCENT * (predicted_s - google_s) / google_s)
                    for band, band_errors in pct_error.groupby(time_band, observed=True):
                        band_rows.append({"variant": variant, "google_time_band_min": str(band),
                                          "n_pairs": len(band_errors),
                                          "signed_median_pct": band_errors.median()})

    metrics_df = pd.DataFrame(metric_rows)
    bands_df = pd.DataFrame(band_rows)
    file_prefix = f"{DIAGNOSTIC_NAME}_{RUN_DATE}_{RUN_TIME}"
    metrics_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{METRICS_FILE_SUFFIX}", index=False)
    bands_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{BANDS_FILE_SUFFIX}", index=False)
    with pd.option_context("display.width", 220, "display.max_columns", 20):
        print(metrics_df.round(4).to_string(index=False))
        print("\nSigned median % error, scaled, by Google traffic-aware time band:")
        print(bands_df.pivot(index="google_time_band_min", columns="variant",
                             values="signed_median_pct").round(2).to_string())
    print(f"\nM2 reference (DESIGN_pre_spine, out-of-fold): accuracy at cut {M2_REFERENCE_ACCURACY_AT_CUT}, "
          f"global rho {M2_REFERENCE_GLOBAL_RHO}")
    print(f"Saved {file_prefix}{METRICS_FILE_SUFFIX} and {file_prefix}{BANDS_FILE_SUFFIX}")
    return metrics_df


# --- step 4: road mix --------------------------------------------------------------------
def find_existing_route_mix_path(tiles_build_name):
    """Return the newest route-mix CSV made from the given tiles build, or None."""
    candidates = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{DIAGNOSTIC_NAME}_*{ROUTE_MIX_FILE_SUFFIX}"))
    matching = [path for path in candidates
                if pd.read_csv(path, usecols=[TILES_BUILD_COL])[TILES_BUILD_COL].eq(tiles_build_name).all()]
    return matching[-1] if matching else None


def describe_one_route(actor, origin_lat, origin_lon, dest_lat, dest_lon):
    """Route one pair, re-read its edges, and summarise its road mix, density and junction time.

    Returns (summary dict, error_message); the dict is empty when the pair does not route.
    """
    request = {
        "locations": [{"lat": origin_lat, "lon": origin_lon},
                      {"lat": dest_lat, "lon": dest_lon}],
        "costing": VALHALLA_COSTING,
        "units": VALHALLA_UNITS,
        "directions_type": "none",
    }
    try:
        trip = actor.route(request)["trip"]
    except ValhallaError as error:
        return {}, str(error)
    trace_request = {
        "encoded_polyline": trip["legs"][0]["shape"],
        "shape_match": TRACE_SHAPE_MATCH,
        "costing": VALHALLA_COSTING,
        "units": VALHALLA_UNITS,
        "filters": {"action": "include", "attributes": TRACE_ATTRIBUTES},
    }
    try:
        trace = actor.trace_attributes(trace_request)
    except ValhallaError:
        trace_request["shape_match"] = TRACE_FALLBACK_SHAPE_MATCH
        try:
            trace = actor.trace_attributes(trace_request)
        except ValhallaError as error:
            return {}, f"trace failed: {error}"
    edges_df = pd.DataFrame({
        "length_km": [edge["length"] for edge in trace["edges"]],
        "road_class": [edge["road_class"] for edge in trace["edges"]],
        "speed_kph": [edge["speed"] for edge in trace["edges"]],
        "density": [edge["density"] for edge in trace["edges"]],
        "transition_time_sec": [edge["end_node"]["transition_time"] for edge in trace["edges"]],
    })
    total_length_km = edges_df["length_km"].sum()
    length_by_class_km = edges_df.groupby("road_class")["length_km"].sum()
    summary = {
        VALHALLA_DURATION_COL: trip["summary"]["time"],
        VALHALLA_DISTANCE_COL: trip["summary"]["length"] * METRES_PER_KM,
        TRACE_TIME_COL: trace["edges"][-1]["end_node"]["elapsed_time"],
        EDGE_TIME_COL: (SECONDS_PER_HOUR * edges_df["length_km"] / edges_df["speed_kph"]).sum(),
        TRANSITION_TIME_COL: edges_df["transition_time_sec"].sum(),
        MEAN_DENSITY_COL: (edges_df["density"] * edges_df["length_km"]).sum() / total_length_km,
        CORRIDOR_SHARE_COL: length_by_class_km.reindex(CORRIDOR_ROAD_CLASSES, fill_value=0).sum()
                            / total_length_km,
        N_EDGES_COL: len(edges_df),
        SHAPE_MATCH_COL: trace_request["shape_match"],
    }
    for road_class in VALHALLA_ROAD_CLASSES:
        summary[ROAD_CLASS_LENGTH_COL_PREFIX + road_class] = length_by_class_km.get(road_class, 0.0)
    unknown_classes = set(length_by_class_km.index) - set(VALHALLA_ROAD_CLASSES)
    if unknown_classes:
        raise ValueError(f"road classes not in VALHALLA_ROAD_CLASSES: {unknown_classes}")
    return summary, ""


def describe_all_routes(variant, config_path):
    """Step 4a: road mix, density and junction time of every pair's route in one variant.

    Reuses an existing route-mix CSV made from the same tiles build; never overwrites one.
    Returns the route-mix DataFrame.
    """
    tiles_build_name = Path(config_path).parent.name
    existing_path = find_existing_route_mix_path(tiles_build_name)
    if existing_path is not None:
        run_date = existing_path.name[len(DIAGNOSTIC_NAME) + 1:].split("_")[0]
        print(f"[{variant}] reusing route mix made {run_date}: {existing_path.name}")
        return pd.read_csv(existing_path, keep_default_na=False)

    pairs_df = pd.read_csv(GOOGLE_ETA_CSV_PATH)
    actor = Actor(str(config_path))
    mix_rows = []
    for i, pair in enumerate(pairs_df.itertuples(index=False)):
        summary, error_message = describe_one_route(
            actor, getattr(pair, ORIGIN_LAT_COL), getattr(pair, ORIGIN_LON_COL),
            getattr(pair, DEST_LAT_COL), getattr(pair, DEST_LON_COL))
        mix_rows.append({PAIR_ID_COL: getattr(pair, PAIR_ID_COL), **summary,
                         VALHALLA_ERROR_COL: error_message, TILES_BUILD_COL: tiles_build_name})
        if (i + 1) % PROGRESS_EVERY_N_PAIRS == 0:
            print(f"  described {i + 1} / {len(pairs_df)}")

    route_mix_df = pd.DataFrame(mix_rows)
    route_mix_path = (DIAGNOSTIC_DATA_DIR
                      / f"{DIAGNOSTIC_NAME}_{RUN_DATE}_{RUN_TIME}_{variant}{ROUTE_MIX_FILE_SUFFIX}")
    route_mix_df.to_csv(route_mix_path, index=False)
    n_failed = (route_mix_df[VALHALLA_ERROR_COL] != "").sum()
    print(f"[{variant}] described {len(route_mix_df) - n_failed} of {len(route_mix_df)} routes "
          f"({n_failed} failed) -> {route_mix_path.name}")
    return route_mix_df


def build_route_mix_predictors(route_mix_df):
    """Join route mix to Google times; derive per-pair predictors and the signed % error.

    Returns (pairs DataFrame of routed pairs, boolean array: trace time matches route time).
    """
    pairs_df = pd.read_csv(GOOGLE_ETA_CSV_PATH)
    routed_df = route_mix_df[route_mix_df[VALHALLA_ERROR_COL] == ""].drop(
        columns=[VALHALLA_ERROR_COL, TILES_BUILD_COL, SHAPE_MATCH_COL])
    routed_df = routed_df.apply(pd.to_numeric)
    pairs_df = pairs_df[[PAIR_ID_COL, ORIGIN_LAT_COL, ORIGIN_LON_COL, DEST_LAT_COL, DEST_LON_COL,
                         GOOGLE_TRAFFIC_COL]].merge(routed_df, on=PAIR_ID_COL, validate="one_to_one")
    route_km = pairs_df[VALHALLA_DISTANCE_COL] / METRES_PER_KM

    def class_share(road_classes):
        return pairs_df[[ROAD_CLASS_LENGTH_COL_PREFIX + road_class for road_class in road_classes]].sum(axis=1) / route_km

    pairs_df[DISTANCE_KM_COL] = haversine_km(pairs_df[ORIGIN_LAT_COL], pairs_df[ORIGIN_LON_COL],
                                             pairs_df[DEST_LAT_COL], pairs_df[DEST_LON_COL])
    pairs_df[MOTORWAY_SHARE_COL] = class_share(MOTORWAY_CLASSES)
    pairs_df[MOTORWAY_TRUNK_SHARE_COL] = class_share(MOTORWAY_TRUNK_CLASSES)
    pairs_df[EDGES_PER_KM_COL] = pairs_df[N_EDGES_COL] / route_km
    pairs_df[TRANSITION_SHARE_COL] = pairs_df[TRANSITION_TIME_COL] / pairs_df[VALHALLA_DURATION_COL]
    pairs_df[PCT_ERROR_COL] = (PERCENT * (pairs_df[VALHALLA_DURATION_COL] - pairs_df[GOOGLE_TRAFFIC_COL])
                               / pairs_df[GOOGLE_TRAFFIC_COL])
    is_trace_matched = ((pairs_df[TRACE_TIME_COL] - pairs_df[VALHALLA_DURATION_COL]).abs()
                        <= MAX_TRACE_TIME_MISMATCH_FRACTION * pairs_df[VALHALLA_DURATION_COL]).to_numpy()
    return pairs_df, is_trace_matched


def spearman_by_distance_band(pairs_df):
    """Spearman of each predictor with % error: all pairs, then within haversine-km quantile bands."""
    distance_band = pd.qcut(pairs_df[DISTANCE_KM_COL], N_DISTANCE_BANDS)
    groups = [("all", pairs_df)] + [(str(band), band_df) for band, band_df
                                    in pairs_df.groupby(distance_band, observed=True)]
    rows = []
    for band_label, band_df in groups:
        row = {"distance_band_km": band_label, "n_pairs": len(band_df),
               "median_pct_error": band_df[PCT_ERROR_COL].median()}
        for predictor_col in SPEARMAN_PREDICTOR_COLS:
            row[predictor_col] = spearmanr(band_df[predictor_col], band_df[PCT_ERROR_COL]).statistic
        rows.append(row)
    return pd.DataFrame(rows)


def fit_standardised_ols(pairs_df, predictor_cols, boot_index):
    """OLS of % error on z-scored predictors; coefficients (pct points per SD) with bootstrap CIs."""
    predictors = pairs_df[predictor_cols].to_numpy(float)
    predictors = (predictors - predictors.mean(axis=0)) / predictors.std(axis=0)
    design = np.column_stack([np.ones(len(predictors)), predictors])
    target = pairs_df[PCT_ERROR_COL].to_numpy(float)
    coefs = np.linalg.lstsq(design, target, rcond=None)[0]
    r_squared = 1 - np.sum((target - design @ coefs) ** 2) / np.sum((target - target.mean()) ** 2)
    boot_coefs = np.array([np.linalg.lstsq(design[i], target[i], rcond=None)[0] for i in boot_index])
    ci_low, ci_high = np.percentile(boot_coefs, [2.5, 97.5], axis=0)
    return [{"predictor": predictor_col, "coef_pct_per_sd": coefs[k + 1],
             "ci_low": ci_low[k + 1], "ci_high": ci_high[k + 1], "r_squared": r_squared}
            for k, predictor_col in enumerate(predictor_cols)]


def analyse_route_mix(route_mix_df):
    """Step 4b: is speed_table's distance bias driven by road mix, density or junctions?

    Two pair sets: "trace_matched" (main) and "all" (sensitivity). Saves the within-band
    Spearman table and the OLS coefficients as dated CSVs.
    """
    all_pairs_df, is_trace_matched = build_route_mix_predictors(route_mix_df)
    pair_sets = {"trace_matched": all_pairs_df[is_trace_matched], "all": all_pairs_df}
    spearman_dfs, ols_rows = [], []
    for pair_set, pairs_df in pair_sets.items():
        spearman_df = spearman_by_distance_band(pairs_df)
        spearman_dfs.append(spearman_df.assign(pair_set=pair_set))
        n_pairs = len(pairs_df)
        boot_index = np.random.default_rng(BOOT_SEED).integers(0, n_pairs, size=(N_BOOT, n_pairs))
        for model_name, predictor_cols in OLS_MODELS.items():
            for row in fit_standardised_ols(pairs_df, predictor_cols, boot_index):
                ols_rows.append({"pair_set": pair_set, "n_pairs": n_pairs, "model": model_name, **row})

    spearman_df = pd.concat(spearman_dfs, ignore_index=True)
    ols_df = pd.DataFrame(ols_rows)
    file_prefix = f"{DIAGNOSTIC_NAME}_{RUN_DATE}_{RUN_TIME}"
    spearman_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{ROUTE_MIX_SPEARMAN_FILE_SUFFIX}", index=False)
    ols_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{ROUTE_MIX_OLS_FILE_SUFFIX}", index=False)
    with pd.option_context("display.width", 220, "display.max_columns", 20):
        print("\nPredictor summary (trace_matched pairs):")
        print(pair_sets["trace_matched"][SPEARMAN_PREDICTOR_COLS + [PCT_ERROR_COL]]
              .describe().round(3).to_string())
        print("\nSpearman with signed % error, overall and within haversine-km bands:")
        print(spearman_df.round(3).to_string(index=False))
        print("\nOLS on standardised predictors (pct points of error per SD):")
        print(ols_df.round(3).to_string(index=False))
    print(f"Saved {file_prefix}{ROUTE_MIX_SPEARMAN_FILE_SUFFIX} and {file_prefix}{ROUTE_MIX_OLS_FILE_SUFFIX}")
    return spearman_df, ols_df


# --- step 4c: junctions ------------------------------------------------------------------
def find_existing_junction_counts_path(tiles_build_name):
    """Return the newest junction-counts CSV made from this tiles build, or None."""
    candidates = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{DIAGNOSTIC_NAME}_*{JUNCTION_COUNTS_FILE_SUFFIX}"))
    matching = [path for path in candidates
                if pd.read_csv(path, usecols=[TILES_BUILD_COL])[TILES_BUILD_COL].eq(tiles_build_name).all()]
    return matching[-1] if matching else None


def merge_nodes_into_junctions(edges):
    """Group the route's nodes into junctions: index lists of nodes that form one junction.

    Node k is the end node of edge k; the destination (last node) is left out. A node joins
    the previous node's junction when the edge between them is internal to an intersection
    or part of a roundabout.
    """
    groups = []
    for k in range(len(edges) - 1):
        is_joined = k > 0 and (edges[k]["internal_intersection"] or edges[k]["roundabout"])
        if is_joined:
            groups[-1].append(k)
        else:
            groups.append([k])
    return groups


def classify_junction(edges, node_indices):
    """Type, side-road count and Valhalla's charge of one junction (a group of node indices)."""
    first, last = node_indices[0], node_indices[-1]
    approach_edge, leaving_edge = edges[first], edges[last + 1]
    side_roads = [side for k in node_indices
                  for side in edges[k]["end_node"].get("intersecting_edges", [])
                  if side.get("driveability") is not None
                  and side.get("use") not in EXCLUDED_SIDE_ROAD_USES]
    if not side_roads:
        junction_type = TAG_SPLIT
    elif any(edges[k]["traffic_signal"] or edges[k]["end_node"]["traffic_signal"] for k in node_indices):
        junction_type = JUNCTION_SIGNALISED
    elif any(edges[k]["roundabout"] for k in node_indices + [last + 1]):
        junction_type = JUNCTION_ROUNDABOUT
    else:
        competing_ranks = [ROAD_CLASS_RANK[side["road_class"]] for side in side_roads
                           if side["driveability"] in CONFLICTING_DRIVEABILITY]
        competing_ranks.append(ROAD_CLASS_RANK[leaving_edge["road_class"]])
        is_give_way = ROAD_CLASS_RANK[approach_edge["road_class"]] > min(competing_ranks)
        junction_type = JUNCTION_GIVE_WAY if is_give_way else JUNCTION_PRIORITY
    return {"junction_type": junction_type,
            "n_nodes": len(node_indices),
            "n_side_roads": len(side_roads),
            "approach_class": approach_edge["road_class"],
            "valhalla_transition_sec": sum(edges[k]["end_node"]["transition_time"] for k in node_indices)}


def describe_junctions_one_route(actor, origin_lat, origin_lon, dest_lat, dest_lon):
    """Route one pair, re-read it, and list its junctions.

    Returns (per-pair summary dict, list of per-junction dicts, error_message).
    """
    request = {
        "locations": [{"lat": origin_lat, "lon": origin_lon},
                      {"lat": dest_lat, "lon": dest_lon}],
        "costing": VALHALLA_COSTING,
        "units": VALHALLA_UNITS,
        "directions_type": "none",
    }
    try:
        trip = actor.route(request)["trip"]
    except ValhallaError as error:
        return {}, [], str(error)
    trace_request = {
        "encoded_polyline": trip["legs"][0]["shape"],
        "shape_match": TRACE_SHAPE_MATCH,
        "costing": VALHALLA_COSTING,
        "units": VALHALLA_UNITS,
        "filters": {"action": "include", "attributes": JUNCTION_TRACE_ATTRIBUTES},
    }
    try:
        trace = actor.trace_attributes(trace_request)
    except ValhallaError:
        trace_request["shape_match"] = TRACE_FALLBACK_SHAPE_MATCH
        try:
            trace = actor.trace_attributes(trace_request)
        except ValhallaError as error:
            return {}, [], f"trace failed: {error}"
    edges = trace["edges"]
    junctions = []
    edge_end_km = np.cumsum([edge["length"] for edge in edges])
    for node_indices in merge_nodes_into_junctions(edges):
        junction = classify_junction(edges, node_indices)
        junction["distance_along_km"] = edge_end_km[node_indices[0]]
        junctions.append(junction)
    type_counts = pd.Series([junction["junction_type"] for junction in junctions]).value_counts()
    summary = {
        VALHALLA_DURATION_COL: trip["summary"]["time"],
        TRACE_TIME_COL: edges[-1]["end_node"]["elapsed_time"],
        N_EDGES_COL: len(edges),
        SHAPE_MATCH_COL: trace_request["shape_match"],
    }
    for junction_type in JUNCTION_TYPES + [TAG_SPLIT]:
        summary[N_JUNCTIONS_COL_PREFIX + junction_type] = int(type_counts.get(junction_type, 0))
    return summary, junctions, ""


def describe_all_junctions(variant, config_path):
    """Step 4c (data): junction counts per pair and one row per junction.

    Reuses existing junction CSVs made from the same tiles build; never overwrites them.
    Returns (junction-counts DataFrame, junctions DataFrame).
    """
    tiles_build_name = Path(config_path).parent.name
    existing_path = find_existing_junction_counts_path(tiles_build_name)
    if existing_path is not None:
        file_prefix = existing_path.name[:-len(JUNCTION_COUNTS_FILE_SUFFIX) - len(variant) - 1]
        run_date = file_prefix[len(DIAGNOSTIC_NAME) + 1:].split("_")[0]
        print(f"[{variant}] reusing junctions made {run_date}: {existing_path.name}")
        return (pd.read_csv(existing_path, keep_default_na=False),
                pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}_{variant}{JUNCTIONS_FILE_SUFFIX}"))

    pairs_df = pd.read_csv(GOOGLE_ETA_CSV_PATH)
    actor = Actor(str(config_path))
    count_rows, junction_rows = [], []
    for i, pair in enumerate(pairs_df.itertuples(index=False)):
        pair_id = getattr(pair, PAIR_ID_COL)
        summary, junctions, error_message = describe_junctions_one_route(
            actor, getattr(pair, ORIGIN_LAT_COL), getattr(pair, ORIGIN_LON_COL),
            getattr(pair, DEST_LAT_COL), getattr(pair, DEST_LON_COL))
        count_rows.append({PAIR_ID_COL: pair_id, **summary,
                           VALHALLA_ERROR_COL: error_message, TILES_BUILD_COL: tiles_build_name})
        junction_rows.extend({PAIR_ID_COL: pair_id, **junction} for junction in junctions)
        if (i + 1) % PROGRESS_EVERY_N_PAIRS == 0:
            print(f"  described junctions {i + 1} / {len(pairs_df)}")

    counts_df = pd.DataFrame(count_rows)
    junctions_df = pd.DataFrame(junction_rows)
    file_prefix = f"{DIAGNOSTIC_NAME}_{RUN_DATE}_{RUN_TIME}_{variant}"
    counts_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{JUNCTION_COUNTS_FILE_SUFFIX}", index=False)
    junctions_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{JUNCTIONS_FILE_SUFFIX}", index=False)
    n_failed = (counts_df[VALHALLA_ERROR_COL] != "").sum()
    print(f"[{variant}] junctions for {len(counts_df) - n_failed} of {len(counts_df)} routes "
          f"({n_failed} failed) -> {file_prefix}{JUNCTION_COUNTS_FILE_SUFFIX}")
    return counts_df, junctions_df


def fit_ols_raw_units(pairs_df, predictor_cols, target_col, boot_index):
    """OLS in the predictors' own units; coefficients with 95% bootstrap CIs."""
    design = np.column_stack([np.ones(len(pairs_df)), pairs_df[predictor_cols].to_numpy(float)])
    target = pairs_df[target_col].to_numpy(float)
    coefs = np.linalg.lstsq(design, target, rcond=None)[0]
    r_squared = 1 - np.sum((target - design @ coefs) ** 2) / np.sum((target - target.mean()) ** 2)
    boot_coefs = np.array([np.linalg.lstsq(design[i], target[i], rcond=None)[0] for i in boot_index])
    ci_low, ci_high = np.percentile(boot_coefs, [2.5, 97.5], axis=0)
    return [{"predictor": predictor_col, "coef": coefs[k + 1], "ci_low": ci_low[k + 1],
             "ci_high": ci_high[k + 1], "r_squared": r_squared}
            for k, predictor_col in enumerate(predictor_cols)]


def per_km(col):
    return col + PER_KM_COL_SUFFIX


def analyse_junctions(route_mix_df, counts_df, junctions_df):
    """Step 4c (analysis): score the pre-registered criteria C1-C3 on trace-matched pairs."""
    mix_pairs_df, is_trace_matched = build_route_mix_predictors(route_mix_df)
    mix_pairs_df = mix_pairs_df[is_trace_matched]
    routed_counts_df = counts_df[counts_df[VALHALLA_ERROR_COL] == ""].drop(
        columns=[VALHALLA_ERROR_COL, TILES_BUILD_COL, SHAPE_MATCH_COL]).apply(pd.to_numeric)
    pairs_df = mix_pairs_df.merge(routed_counts_df, on=PAIR_ID_COL, suffixes=("", "_4c"),
                                  validate="one_to_one")
    # Same tiles, so the same routes as step 4a: edge counts and times must agree.
    n_edge_mismatch = (pairs_df[N_EDGES_COL] != pairs_df[N_EDGES_COL + "_4c"]).sum()
    n_time_mismatch = (pairs_df[VALHALLA_DURATION_COL] - pairs_df[VALHALLA_DURATION_COL + "_4c"]).abs().gt(0.01).sum()
    print(f"\nStep 4c: {len(pairs_df)} trace-matched pairs; route differs from step 4a in "
          f"{n_edge_mismatch} (edge count) / {n_time_mismatch} (time) pairs")

    count_cols = {junction_type: N_JUNCTIONS_COL_PREFIX + junction_type
                  for junction_type in JUNCTION_TYPES + [TAG_SPLIT]}
    pairs_df[N_UNSIGNALISED_COL] = pairs_df[[count_cols[t] for t in UNSIGNALISED_TYPES]].sum(axis=1)
    pairs_df[ROUTE_KM_COL] = pairs_df[VALHALLA_DISTANCE_COL] / METRES_PER_KM
    pairs_df[MOTORWAY_KM_COL] = pairs_df[MOTORWAY_SHARE_COL] * pairs_df[ROUTE_KM_COL]
    for col in list(count_cols.values()) + [N_UNSIGNALISED_COL]:
        pairs_df[per_km(col)] = pairs_df[col] / pairs_df[ROUTE_KM_COL]
    pairs_df[RESIDUAL_SEC_COL] = pairs_df[GOOGLE_TRAFFIC_COL] - pairs_df[VALHALLA_DURATION_COL]
    pairs_df[RESIDUAL_PCT_COL] = PERCENT * pairs_df[RESIDUAL_SEC_COL] / pairs_df[GOOGLE_TRAFFIC_COL]

    # What Valhalla charges per junction, by type (matched pairs only).
    matched_junctions_df = junctions_df[junctions_df[PAIR_ID_COL].isin(pairs_df[PAIR_ID_COL])]
    charge_df = (matched_junctions_df.groupby("junction_type")["valhalla_transition_sec"]
                 .agg(["count", "mean", "median"]).reset_index())
    charge_df["per_pair_mean"] = charge_df["count"] / len(pairs_df)

    controls = [DISTANCE_KM_COL, MOTORWAY_SHARE_COL, MEAN_DENSITY_COL, per_km(count_cols[JUNCTION_SIGNALISED]),
                per_km(count_cols[JUNCTION_ROUNDABOUT])]
    density_models = {
        "unsignalised": controls + [per_km(N_UNSIGNALISED_COL)],
        "give_way_priority": controls + [per_km(count_cols[JUNCTION_GIVE_WAY]),
                                         per_km(count_cols[JUNCTION_PRIORITY])],
    }
    tag_split_col = per_km(count_cols[TAG_SPLIT])
    # Seconds model: residual seconds on route length and junction counts -> seconds per junction.
    seconds_models = {
        "unsignalised_sec": [ROUTE_KM_COL, MOTORWAY_KM_COL, count_cols[JUNCTION_SIGNALISED],
                             count_cols[JUNCTION_ROUNDABOUT], N_UNSIGNALISED_COL, count_cols[TAG_SPLIT]],
        "give_way_priority_sec": [ROUTE_KM_COL, MOTORWAY_KM_COL, count_cols[JUNCTION_SIGNALISED],
                                  count_cols[JUNCTION_ROUNDABOUT], count_cols[JUNCTION_GIVE_WAY],
                                  count_cols[JUNCTION_PRIORITY], count_cols[TAG_SPLIT]],
    }
    rng = np.random.default_rng(BOOT_SEED)
    distance_band = pd.qcut(pairs_df[DISTANCE_KM_COL], N_DISTANCE_BANDS)
    ols_rows = []
    groups = [("all", pairs_df)] + [(str(band), band_df) for band, band_df
                                    in pairs_df.groupby(distance_band, observed=True)]
    for band_label, band_df in groups:
        boot_index = rng.integers(0, len(band_df), size=(N_BOOT, len(band_df)))
        fits = {name: (cols, RESIDUAL_PCT_COL) for name, cols in density_models.items()}
        if band_label == "all":       # C2 and C3 are full-sample fits
            fits.update({name + "_with_tag_splits": (cols + [tag_split_col], RESIDUAL_PCT_COL)
                         for name, cols in density_models.items()})
            fits.update({name: (cols, RESIDUAL_SEC_COL) for name, cols in seconds_models.items()})
        for model_name, (predictor_cols, target_col) in fits.items():
            for row in fit_ols_raw_units(band_df.reset_index(drop=True), predictor_cols, target_col, boot_index):
                ols_rows.append({"distance_band_km": band_label, "n_pairs": len(band_df),
                                 "model": model_name, "target": target_col, **row})
    ols_df = pd.DataFrame(ols_rows)

    def coef_row(band, model, predictor):
        return ols_df[(ols_df["distance_band_km"] == band) & (ols_df["model"] == model)
                      & (ols_df["predictor"] == predictor)].iloc[0]

    band_labels = [label for label, _ in groups[1:]]
    near_cut_df = pairs_df[(pairs_df[GOOGLE_TRAFFIC_COL] - CUT_S).abs() <= NEAR_CUT_WINDOW_S]
    verdicts = []
    for count_name, density_model, density_col, seconds_model, count_col in [
            ("unsignalised", "unsignalised", per_km(N_UNSIGNALISED_COL), "unsignalised_sec", N_UNSIGNALISED_COL),
            ("likely_give_way", "give_way_priority", per_km(count_cols[JUNCTION_GIVE_WAY]),
             "give_way_priority_sec", count_cols[JUNCTION_GIVE_WAY])]:
        n_bands_passing = sum(coef_row(band, density_model, density_col)["ci_low"] > 0 for band in band_labels)
        c2_row = coef_row("all", density_model + "_with_tag_splits", density_col)
        sec_row = coef_row("all", seconds_model, count_col)
        shift_pct = PERCENT * sec_row["coef"] * near_cut_df[count_col] / near_cut_df[VALHALLA_DURATION_COL]
        verdicts.append({"count": count_name,
                         "c1_bands_passing": n_bands_passing, "c1_pass": n_bands_passing >= MIN_BANDS_PASSING,
                         "c2_coef": c2_row["coef"], "c2_ci_low": c2_row["ci_low"], "c2_ci_high": c2_row["ci_high"],
                         "c2_pass": c2_row["ci_low"] > 0,
                         "c3_sec_per_junction": sec_row["coef"], "c3_ci_low": sec_row["ci_low"],
                         "c3_ci_high": sec_row["ci_high"], "c3_n_near_cut": len(near_cut_df),
                         "c3_median_count_near_cut": near_cut_df[count_col].median(),
                         "c3_median_shift_pct": shift_pct.median()})
    verdict_df = pd.DataFrame(verdicts)

    file_prefix = f"{DIAGNOSTIC_NAME}_{RUN_DATE}_{RUN_TIME}"
    ols_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{JUNCTION_OLS_FILE_SUFFIX}", index=False)
    charge_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{JUNCTION_CHARGE_FILE_SUFFIX}", index=False)
    with pd.option_context("display.width", 220, "display.max_columns", 30, "display.max_rows", 200):
        print("\nValhalla's charge per junction (transition time, s), and junctions per pair:")
        print(charge_df.round(3).to_string(index=False))
        print("\nCounts per km (trace-matched pairs):")
        print(pairs_df[[per_km(col) for col in count_cols.values()] + [EDGES_PER_KM_COL, RESIDUAL_PCT_COL]]
              .describe().round(3).to_string())
        print("\nOLS in raw units (target residual_pct per junction/km, or residual_sec per junction):")
        print(ols_df.round(3).to_string(index=False))
        print("\nPre-registered criteria:")
        print(verdict_df.round(3).T.to_string())
    print(f"Saved {file_prefix}{JUNCTION_OLS_FILE_SUFFIX} and {file_prefix}{JUNCTION_CHARGE_FILE_SUFFIX}")
    return ols_df, verdict_df


if __name__ == "__main__":
    valhalla_routes_by_variant = {}
    valhalla_config_paths = {}
    for valhalla_variant in VARIANT_SPEED_TABLES:
        valhalla_config_paths[valhalla_variant] = build_tiles(valhalla_variant)
        valhalla_routes_by_variant[valhalla_variant] = route_all_pairs(
            valhalla_variant, valhalla_config_paths[valhalla_variant])
    compare_to_google(valhalla_routes_by_variant)
    route_mix = describe_all_routes(ROUTE_MIX_VARIANT, valhalla_config_paths[ROUTE_MIX_VARIANT])
    analyse_route_mix(route_mix)
    analyse_junctions(route_mix, *describe_all_junctions(ROUTE_MIX_VARIANT,
                                                         valhalla_config_paths[ROUTE_MIX_VARIANT]))
