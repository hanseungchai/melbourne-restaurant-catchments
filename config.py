"""Project configuration: every path and tunable parameter lives here.

No other file defines a path or parameter; scripts import them from this module.
All paths are pathlib.Path objects built relative to PROJECT_ROOT, so the project
runs from any working directory and contains no absolute paths.

This file is also the documentation:
- Every entry has a comment: meaning, unit if any, and why that value was chosen
  if it isn't obvious.
- Entries are grouped by pipeline stage, in pipeline order. Project-wide folders
  come first.
- Each migrated path carries a comment with its legacy path.
"""

from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------

# Folder containing this file, i.e. the project root.
PROJECT_ROOT = Path(__file__).resolve().parent

# Frozen external inputs (API pulls, etc.), copied from the legacy data/ (docs/legacy_archive.md). Read-only.
FROZEN_INPUTS_DIR = PROJECT_ROOT / "frozen_inputs"

# Newer, non-legacy external inputs, added by the user (e.g. a newer census year). Read-only.
INPUTS_DIR = PROJECT_ROOT / "inputs"

# Everything cleaned code writes. The only folder cleaned code writes to.
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# ---------------------------------------------------------------------------
# API access
# ---------------------------------------------------------------------------

# Name of the environment variable (a Windows user variable) that holds the Google Maps
# API key. Only the name lives here, never the key; it is read at call time by API stages.
GOOGLE_API_KEY_ENV_VAR = "GOOGLE_API_KEY"

# ===========================================================================
# !!! API BUDGET GUARD: read only by api_ledger.py. Changing these changes what may be spent (S5).
# !!! API_PAID_EXTENSION entries are per-run user approvals: add only on the user's go, remove after the run.
# ===========================================================================

API_BILLING_TIMEZONE = "America/Los_Angeles"   # Google's billing month runs on US Pacific time

# Free monthly allowance (except legacy_nearby, which is not free) per SKU. None means uncapped (no paid tier).
API_FREE_ALLOWANCE = {
    "text_search_ids_only": None,
    "legacy_nearby": 5000,
    "place_details_enterprise": 1000,
    "routes_pro": 5000,
    "routes_essentials": 10000,
    "nearby_pro": 5000,   # Nearby Search (New), IDs-only mask bills as Pro (added 2026-10-25, Q19 screen test)
}

# Calls made this billing month BEFORE the ledger existed, read off Billing -> Reports.
# A capped SKU with no seed for the current month is refused: an unknown starting point
# means an unknown remaining balance.
API_SEED_USED = {
    ("2026-09", "legacy_nearby"): 0,
    ("2026-09", "place_details_enterprise"): 950,
    ("2026-09", "routes_pro"): 544,
    ("2026-10", "place_details_enterprise"): 0,
    ("2026-10", "routes_pro"): 0,
    ("2026-10", "routes_essentials"): 0,
    ("2026-11", "routes_essentials"): 0,   # month not started when added; the ledger sees all of it
    ("2026-10", "nearby_pro"): 0,          # SKU first used 2026-10-25; the ledger has seen all of October
}

# Paid calls the user approved on top of the free allowance, per (billing month, SKU). TEMPORARY: each
# entry lives only for the run it was approved for and is removed when that run ends.
API_PAID_EXTENSION = {}

API_MARGIN = 0   # stop this many calls short of the allowance

# ===========================================================================

# API request ledger (written only by api_ledger.py; append-only, not regenerable).
API_USAGE_DIR = PROJECT_ROOT / "api_usage"
API_LEDGER_PATH = API_USAGE_DIR / "api_ledger.jsonl"   # legacy: api_usage/api_ledger.jsonl

# Place Details field mask for functions/google_places.fetch_place. Billed at the highest SKU
# in the mask: regularOpeningHours is Enterprise, so every Pro and Essentials field below comes
# at no extra cost. Deliberately excluded (Enterprise + Atmosphere, a tier up): reviews,
# delivery, dineIn, takeout, editorialSummary, reservable, serves*.
PLACES_ENTERPRISE_FIELD_MASK = ",".join([
    # Essentials
    "id", "types", "location", "formattedAddress", "shortFormattedAddress",
    # Pro
    "displayName", "primaryType", "primaryTypeDisplayName", "businessStatus",
    "containingPlaces", "openingDate", "utcOffsetMinutes",
    # Enterprise
    "regularOpeningHours", "regularSecondaryOpeningHours", "currentOpeningHours",
    "rating", "userRatingCount", "priceLevel", "priceRange", "websiteUri",
])

PLACES_MAX_RETRIES = 5             # attempts per place before giving up
PLACES_BACKOFF_BASE_S = 2          # retry wait = base ** attempt seconds, plus jitter
PLACES_BACKOFF_JITTER_MAX_S = 1    # random extra wait, uniform in [0, this]
PLACES_REQUEST_TIMEOUT_S = 10      # per-request timeout

# Minimum gap between Place Details requests (retries included): at most 300 per minute, half the
# project's GetPlace quota of 600 per minute (Console, read by the user 2026-10-10).
PLACES_MIN_REQUEST_INTERVAL_S = 0.2

# Google Routes computeRoutes (drive_samples.request_drive_route / fetch_drive_eta).
ROUTES_API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
ROUTES_MAX_RETRIES = 4             # attempts per request (429 and 5xx are retried)
ROUTES_BACKOFF_BASE_S = 2          # retry wait = base ** attempt seconds, plus jitter
ROUTES_BACKOFF_JITTER_MAX_S = 1    # random extra wait, uniform in [0, this]
ROUTES_REQUEST_DELAY_S = 0.2       # pause after each request
ROUTES_REQUEST_TIMEOUT_S = 20      # per-request timeout

# ---------------------------------------------------------------------------
# Legacy datasets: rebuilt from frozen inputs by legacy_datasets.py, never re-fetched.
# Folder and file suffixes are the collection date (YYYYMMDD).
# ---------------------------------------------------------------------------

# 2026-06-29 Legacy Nearby scan, one output_<radius m>.json per search radius.
# legacy: data/search_backup
NEARBY_SCAN_20260629_DIR = FROZEN_INPUTS_DIR / "places_nearby_scan_20260629"

# Collection date of the scan; stored in the merged file's "collection_timestamp" field.
# Evidence: frozen_inputs README (file dates) and verification_merge_Sep_25 §4.
NEARBY_SCAN_20260629_COLLECTION_DATE = "2026-06-29"

# Same scan, 20 km extension: output_<radius m>.json for the newly scanned area only.
# legacy: data/search_backup/_20km_update
NEARBY_SCAN_20260629_UPDATE_DIR = NEARBY_SCAN_20260629_DIR / "update_20km"

# Outputs of legacy_datasets.py: one subfolder per rebuilt dataset family.
LEGACY_REBUILDS_DIR = OUTPUTS_DIR / "legacy_rebuilds"

# Rebuilt Legacy Nearby scan files.
NEARBY_SCAN_REBUILD_DIR = LEGACY_REBUILDS_DIR / "nearby_scan"

# Both scan folders merged, first result kept per place_id.
# legacy: data/place_api_results.json (renamed by hand to data/legacy_place_api_results.json)
NEARBY_SCAN_20260629_MERGED_PATH = NEARBY_SCAN_REBUILD_DIR / "places_nearby_scan_20260629_merged.json"

# --- Venue tables rebuilt from the scans (legacy_datasets.py); files are <what>_<date>_<variant>,
# --- dated by the newest collection they contain.

# 2026-07-04 Places Details pull (Google "Places API (New)"), one <place_id>.json per scanned venue;
# used for type tags and formatted addresses.
# legacy: data/search_new_api_json
PLACES_DETAILS_20260704_DIR = FROZEN_INPUTS_DIR / "places_details_20260704"

# 2026-09-25 Legacy Nearby repair (7–20 km) and outer (20–100 km) runs, one JSON record per request.
# legacy: data/search_expanded/expanded_search.jsonl
NEARBY_REPAIR_20260925_PATH = FROZEN_INPUTS_DIR / "places_nearby_repair_20260925" / "expanded_search.jsonl"

# Default subject business location, one "lat, lon" line, entered by hand. Other subjects: see
# ALT_SUBJECTS_DIR (hex grid stage).
# legacy: data/subject_business_coord.txt
SUBJECT_COORD_PATH = FROZEN_INPUTS_DIR / "manual_inputs" / "subject_business_coord.txt"

# Centre of the legacy venue scans (June scan, sound disc, September repair/outer rings): the default
# subject's location when they were run. Fixed by the legacy data; never follows main.py's subject_name.
LEGACY_SCAN_CENTRE_COORD_PATH = SUBJECT_COORD_PATH

# Rebuilt venue tables.
VENUES_REBUILD_DIR = LEGACY_REBUILDS_DIR / "venues"

# Merged scan as a table: OPERATIONAL venues only, one row per place_id.
# legacy: data/legacy_data.csv
NEARBY_SCAN_20260629_OPERATIONAL_PATH = VENUES_REBUILD_DIR / "places_nearby_scan_20260629_operational.csv"

# Details pull as a table: place_id, types ("|"-joined), formattedAddress.
# legacy: data/new_place_api_results.csv
PLACES_DETAILS_20260704_TABLE_PATH = VENUES_REBUILD_DIR / "places_details_20260704.csv"

# Venue table before the repair: Details rows joined to the scan table.
# legacy: data/place_api.csv
VENUES_20260629_PRE_EXPANSION_PATH = VENUES_REBUILD_DIR / "venues_20260629_pre_expansion.csv"

# Venue table after the repair: repair/outer venues from SOUND_DISC_RADIUS_M outward replace the
# old scan's venues there. The venue layer every later stage starts from.
# legacy: data/expanded_place_api.csv
VENUES_20260925_EXPANDED_PATH = VENUES_REBUILD_DIR / "venues_20260925_expanded.csv"

# Inner disc kept from the June scan (sound, unaffected by the hole); the repair covers from here out.
SOUND_DISC_RADIUS_M = 7_000

# Three venues confirmed by hand as duplicates during the phone-number sanity check (e.g. one
# McDonald's listed under two place_ids after a name change, the old id never retired). Dropped
# individually; there is no systematic de-duplication: shared phone numbers are often genuine
# (chains routed through call centres, food courts), so Google data is otherwise used as is.
MANUAL_DUPLICATE_PLACE_IDS = [
    'ChIJOcwjEgBd1moR2jUFmHT1Nxo',
    'ChIJ0_e1eABN1moRx8KcNcQDwh4',
    'ChIJyaBkcVZb1moRxHsvQ9ndNNw',
]

# ---------------------------------------------------------------------------
# 2026-09-02 Places Enterprise hours pull (frozen). It fed the opening-hours histogram until the
# 2026-10-10 pull replaced it; kept as a choice in OPENING_HOURS_PULL_DIRS (see "Opening hours").
# The 2026-09-02 hours were checked as still current. # evidence: diagnostics/hours_check_fresh60.py
# ---------------------------------------------------------------------------

# 2026-09-02 Places Details (Enterprise fields) pull, one <place_id>.json per venue (900 venues).
# legacy: data/google_enterprise_fetch
PLACES_ENTERPRISE_HOURS_20260902_DIR = FROZEN_INPUTS_DIR / "places_enterprise_hours_20260902"

# ---------------------------------------------------------------------------
# Enterprise hours fetch (places_details.py): a fresh Places Details (Enterprise fields) pull for a
# uniform random draw from the current venue table, plus fixed venues fetched outside the draw.
# Replaces the 2026-09-02 pull's sample, which barely covers the outer ring (40 of 8,889 venues).
# Paid API: every attempt goes through api_ledger (SKU place_details_enterprise).
# ---------------------------------------------------------------------------

# Outputs of the pull: one folder of JSONs per pull, plus that pull's draw list.
ENTERPRISE_HOURS_DIR = OUTPUTS_DIR / "places_enterprise_hours"

# Pull date (YYYYMMDD); names the draw list and the JSON folder. A new pull gets a new date.
ENTERPRISE_HOURS_PULL_DATE = "20261010"

# Venues drawn uniformly at random from the venue table (fixed venues excluded from the draw).
ENTERPRISE_HOURS_SAMPLE_SIZE = 900

# Random seed for the draw.
ENTERPRISE_HOURS_SEED = 20261010

# Venues always fetched, outside the random draw and left out of the histogram: the subject venues
# ([subject] Brunswick East, [subject] Melbourne Central), kept up to date. Fetched first.
ENTERPRISE_HOURS_FIXED_PLACE_IDS = [
    "<place_id: subject, Brunswick East>",   # [subject] Brunswick East
    "<place_id: subject, Melbourne Central>",   # [subject] Melbourne Central
]

# Draw list: place_id, name, run_id (venue table ring), is_fixed, draw order.
ENTERPRISE_HOURS_DRAW_PATH = (ENTERPRISE_HOURS_DIR
                              / f"places_enterprise_hours_{ENTERPRISE_HOURS_PULL_DATE}_draw.csv")

# One <place_id>.json per fetched venue.
ENTERPRISE_HOURS_PULL_DIR = ENTERPRISE_HOURS_DIR / f"places_enterprise_hours_{ENTERPRISE_HOURS_PULL_DATE}"

# Venues this pull's fetch got HTTP 404 for (place id no longer valid): place_id, http_status,
# error_message, checked_date. Permanent, so a rerun skips them instead of paying again.
ENTERPRISE_HOURS_NOT_FOUND_PATH = (ENTERPRISE_HOURS_DIR
                                   / f"places_enterprise_hours_{ENTERPRISE_HOURS_PULL_DATE}_not_found.csv")

# ---------------------------------------------------------------------------
# Opening hours (opening_hours.build_opening_hours, fetch_enterprise_hours block): weekday open-share
# histogram from one Places Enterprise hours pull; no API. Used for departure-time weights.
# The 2026-10-10 pull replaced the 2026-09-02 one (user, 2026-10-10); both give the same histogram
# within 95% intervals, so outputs built from the old hours stay valid.
# evidence: diagnostics/enterprise_hours_old_vs_new.py
# ---------------------------------------------------------------------------

# Hours pulls the histogram can use, keyed by pull date (YYYYMMDD); the date names the outputs.
OPENING_HOURS_PULL_DIRS = {
    "20260902": PLACES_ENTERPRISE_HOURS_20260902_DIR,
    "20261010": ENTERPRISE_HOURS_PULL_DIR,
}

# Which pull the histogram uses. Set "20260902" to reproduce legacy results (e.g. the
# calibrate_pathing_agent pass A check against the frozen 2026-09-30 draws).
OPENING_HOURS_PULL_DATE = "20261010"

# legacy: data/google_enterprise_processed
OPENING_HOURS_DIR = OUTPUTS_DIR / "opening_hours"

# Histogram slot length; also part of the histogram file name.
HOURS_SLOT_MIN = 30

# Weekday slots whose mean open share the summary prints: the departure rule's slots
# (12:00, 19:00, 22:00) and the afternoon trough (15:30).
HOURS_CHECKPOINT_SLOTS = ["12:00", "15:30", "19:00", "22:00"]

# Share of included venues open at each slot of the week.
# legacy: data/google_enterprise_processed/hours_old_hist_30m.csv
OPENING_HOURS_HIST_PATH = (OPENING_HOURS_DIR
                           / f"opening_hours_{OPENING_HOURS_PULL_DATE}_hist_{HOURS_SLOT_MIN}min.csv")

# One row per venue: status, hours flag, whether it counts in the histogram.
# legacy: data/google_enterprise_processed/hours_old_venue_log.csv
OPENING_HOURS_VENUE_LOG_PATH = OPENING_HOURS_DIR / f"opening_hours_{OPENING_HOURS_PULL_DATE}_venue_log.csv"

# Last close per venue-day, in hours after that day's midnight.
# legacy: data/google_enterprise_processed/hours_old_closes.csv
OPENING_HOURS_CLOSES_PATH = OPENING_HOURS_DIR / f"opening_hours_{OPENING_HOURS_PULL_DATE}_closes.csv"

# Run metadata and the counting rules.
# legacy: data/google_enterprise_processed/hours_old_meta.json
OPENING_HOURS_META_PATH = OPENING_HOURS_DIR / f"opening_hours_{OPENING_HOURS_PULL_DATE}_meta.json"

# ---------------------------------------------------------------------------
# Census (abs_census.py): statewide Victoria residents by SA1 and workers by Destination Zone,
# joined to their boundaries. 2021 Census; both denominators should stay on one census year
# (mixed years allowed but warned; DESIGN_pre_spine "Data layers").
# ---------------------------------------------------------------------------

# Census year of the frozen inputs below (build_census_2021).
CENSUS_FROZEN_YEAR = 2021

# Census year the later stages read, one per layer. Changed by hand, after a newer year of that
# layer is built and checked. Same year by default; if they differ, the hex stage warns and the
# writeup states it as a limitation (DESIGN_pre_spine "Data layers").
CENSUS_RESIDENTS_YEAR = 2021   # abs: SA1 residents
CENSUS_WORKERS_YEAR = 2021     # dzn: DZN workers

# Census layers keep this state only (ASGS state name).
STATE_NAME = "Victoria"

# ASGS Edition 3 SA1 boundaries, all of Australia.
# legacy: data/sa1_data/SA1_2021_AUST_GDA2020.shp
SA1_BOUNDARIES_PATH = FROZEN_INPUTS_DIR / "abs_sa1_boundaries" / "SA1_2021_AUST_GDA2020.shp"

# Census DataPack G01 (persons by usual residence), Victoria, SA1 level.
# legacy: data/sa1_data/2021Census_G01_VIC_SA1.csv
CENSUS_G01_SA1_PATH = FROZEN_INPUTS_DIR / "abs_census_g01" / "2021Census_G01_VIC_SA1.csv"

# Destination Zone boundaries, all of Australia.
# legacy: data/ABS/DZN_2021_AUST_GDA2020.shp
DZN_BOUNDARIES_PATH = FROZEN_INPUTS_DIR / "abs_dzn_boundaries" / "DZN_2021_AUST_GDA2020.shp"

# TableBuilder Pro export: persons 15+ by DZN of place of work, Victoria.
# legacy: data/ABS/DNZ POW.xlsx
DZN_WORKERS_XLSX_PATH = FROZEN_INPUTS_DIR / "abs_tablebuilder" / "DNZ POW.xlsx"

# Newer census inputs (build_census_update). The two layers are released and updated separately,
# each in its own year folder: abs_<year>/ (residents) and dzn_<year>/ (workers), holding the
# files named below. A layer is built for a year only when both its files are there.
CENSUS_INPUTS_DIR = INPUTS_DIR / "census"
CENSUS_ABS_DIR_NAME = "abs_{year}"
CENSUS_ABS_INPUT_NAMES = [
    "SA1_{year}_AUST_GDA2020.shp",       # SA1 boundaries (with their .shx/.dbf/.prj)
    "{year}Census_G01_VIC_SA1.csv",      # DataPack G01, Victoria, SA1
]
CENSUS_DZN_DIR_NAME = "dzn_{year}"
CENSUS_DZN_INPUT_NAMES = [
    "DZN_{year}_AUST_GDA2020.shp",       # DZN boundaries (with their .shx/.dbf/.prj)
    "DNZ POW.xlsx",                      # TableBuilder Pro export, DZN (POW); same name as the 2021 file
]

# Outputs of abs_census, one file per layer and census year.
CENSUS_DIR = OUTPUTS_DIR / "census"
SA1_RESIDENTS_NAME = "sa1_residents_{year}.gpkg"     # SA1 polygons with resident counts (Tot_P_P)
DZN_WORKERS_NAME = "dzn_workers_{year}.gpkg"         # DZN polygons with worker counts (Tot_W_P)

# The layers the later stages read: CENSUS_RESIDENTS_YEAR and CENSUS_WORKERS_YEAR.
# legacy: data/sa1_data/sa1_reduced/sa1_victoria.gpkg
SA1_RESIDENTS_GPKG_PATH = CENSUS_DIR / SA1_RESIDENTS_NAME.format(year=CENSUS_RESIDENTS_YEAR)
# legacy: data/ABS/dzn_reduced/dzn_victoria.gpkg
DZN_WORKERS_GPKG_PATH = CENSUS_DIR / DZN_WORKERS_NAME.format(year=CENSUS_WORKERS_YEAR)

# ---------------------------------------------------------------------------
# Hex grid (hex_tile_construction.py, construct_hex_tiles block): 100 m hexes out to 100 km from
# the subject, filled with residents (SA1), workers (DZN) and venue counts; empty hexes dropped.
# Inputs: the subject's coordinates, the census layers above, the venue table picked by
# HEX_VENUES_DATE. Every file the stage writes goes in its subject's "<lat>_<lon>" subfolder of the
# folder below, with "_<lat>_<lon>" added to its name, so grids for different subjects never
# overwrite each other. Files built from data layers also carry the layers' dates before that:
# "res<year>_wrk<year>" (census) and/or "ven<date>" (venues).
# ---------------------------------------------------------------------------

# Extra subjects: one "<subject name>.txt" per subject, first line "lat, lon" (same format as
# SUBJECT_COORD_PATH). main.py's subject_name picks one by file name; None = SUBJECT_COORD_PATH.
ALT_SUBJECTS_DIR = INPUTS_DIR / "alt_subjects"
SUBJECT_COORD_SUFFIX = ".txt"

# Decimals of lat/lon in the subject tag (5 decimals ~ 1 m).
SUBJECT_TAG_DECIMALS = 5

# Origin of the hex stencil: every subject's grid snaps to the lattice of hexes laid from this
# point, so grids for different subjects share hexes where they overlap (user, 2026-10-08). The
# subject's hex is the stencil hex it falls in.
HEX_STENCIL_ORIGIN_COORD_PATH = SUBJECT_COORD_PATH

# Venue tables the hex stage can use, keyed by date (the newest collection each contains). The
# date goes into the names of the files built from it.
VENUE_TABLES = {
    "20260925": VENUES_20260925_EXPANDED_PATH,
}
HEX_VENUES_DATE = "20260925"    # which VENUE_TABLES entry the hex stage reads

HEX_DIAMETER_M = 100            # hex size, vertex to vertex
HEX_GRID_RADIUS_M = 100_000     # grid reach from the subject (haversine)
HEX_RING_MARGIN = 1.01          # extra rings so the disc isn't cut short; construct() asserts it isn't
VENUE_HEX_MATCH_RADIUS_M = 50   # venues farther than this from every hex centroid are dropped

# Coverage check (warning only, before the grid is built). A hex at the edge of the subject's drive
# band is contested by competitors up to one more band away, so competitors within 2 bands of the
# subject matter. Very worst case: cars fly straight at MAX_DRIVE_SPEED_KMH, giving a reach of
# 2 * 20 min at 110 km/h = 73.3 km. The stage warns when part of that disc lies outside the venue
# scan or the road extract, worded by the share left out (user, 2026-10-08; DESIGN_pre_spine "Data layers").
DRIVE_BAND_DURATION_MIN = 20     # band 3 drive cutoff (DESIGN_pre_spine "Scoring model")
MAX_DRIVE_SPEED_KMH = 110        # Victoria's highest freeway limit; deliberately conservative
VENUE_SCAN_RADIUS_M = 100_000    # legacy venue scan reach around LEGACY_SCAN_CENTRE_COORD_PATH
ROAD_EXTRACT_BOUNDS = (143.599, -38.893, 146.327, -36.735)  # BBBike extract: min lon, min lat, max lon, max lat
COVERAGE_SAMPLE_SPACING_M = 500  # spacing of the point lattice used to measure the uncovered share
COVERAGE_GAP_MINOR_MAX = 0.10            # up to this share uncovered: likely not an issue
COVERAGE_GAP_LOW_CHANCE_MAX = 0.30       # up to this: low chance marginal venues are missed
COVERAGE_GAP_REASONABLE_CHANCE_MAX = 0.50  # up to this: reasonable chance; above: very probable

# Census-coverage report on the empty-hex filter (printed only; doesn't change what is kept).
UNCOVERED_COVERAGE_MAX = 0.01   # dropped hex counts as outside census coverage below this share
TRACE_COVERAGE_MAX = 1e-6       # kept hex counts as kept on trace coverage alone below this share

HEX_GRID_DIR = OUTPUTS_DIR / "hex_grid"

# Bare grid: hex_id, axial q/r, centroid, polygon; hex 0 is the subject.
# legacy: data/hex_grid/hex_grid.gpkg
HEX_GRID_PATH = HEX_GRID_DIR / "hex_grid.gpkg"

# Grid with residents, workers and venue_count joined from the layer tables, empty hexes dropped.
# legacy: data/hex_grid/hex_grid_with_population.gpkg
HEX_GRID_POP_PATH = HEX_GRID_DIR / "hex_grid_with_population.gpkg"

# Per-layer tables: hex_id plus that layer's columns, for every hex of the bare grid. Each is built
# only when missing (or when main.py's should_rebuild_hex_layers is on), then joined into the grid below.
HEX_RESIDENTS_LAYER_PATH = HEX_GRID_DIR / "hex_residents.parquet"          # residents, residents_cov
HEX_WORKERS_LAYER_PATH = HEX_GRID_DIR / "hex_workers.parquet"              # workers, workers_cov
HEX_VENUE_COUNTS_LAYER_PATH = HEX_GRID_DIR / "hex_venue_counts.parquet"    # venue_count

# Venue table plus each venue's hex_id and distance to that hex's centroid.
# legacy: data/hex_grid/place_api_with_hex.csv
VENUES_WITH_HEX_PATH = HEX_GRID_DIR / "venues_with_hex.csv"

# ---------------------------------------------------------------------------
# Road graphs (road_graphs.py): the drive graph built from the OSM extract. The walk graph build and
# its entries are parked: docs/parked_code/walk_graph.md (concepts/walk.md WLK-5).
# ---------------------------------------------------------------------------

# BBBike OSM extract, data 2026-09-23 (frozen_inputs/README.md); its bounds are ROAD_EXTRACT_BOUNDS.
# legacy: data/bbbike/planet_143.599,-38.893_146.327,-36.735.osm.pbf
ROAD_EXTRACT_PBF_PATH = FROZEN_INPUTS_DIR / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"

ROAD_GRAPHS_DIR = OUTPUTS_DIR / "road_graphs"

# Directed drive graph (networkx DiGraph, respects oneway); edges carry length (m), highway, raw maxspeed.
# legacy: data/bbbike/drive_graph.gpickle
DRIVE_GRAPH_PATH = ROAD_GRAPHS_DIR / "drive_graph.gpickle"

# Which OSM ways enter the drive graph, by highway tag (graph_rebuild_Sep_29 §1-2; walk_highway_tags_Sep_21).
DRIVE_HIGHWAY_TYPES = {
    'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified',
    'residential', 'motorway_link', 'trunk_link', 'primary_link',
    'secondary_link', 'tertiary_link', 'living_street', 'service'
}
# Not usable by any mode; excluded entirely.
UNUSABLE_HIGHWAY_TYPES = {
    'construction', 'proposed', 'abandoned', 'razed',
    'raceway', 'busway', 'platform', 'traffic_island', 'services', 'rest_area'
}
NO_ACCESS_VALUES = ('no', 'private')  # motor_vehicle / vehicle / access values that exclude a way

# ---------------------------------------------------------------------------
# Road density (road_density.py): Valhalla-style road km per km² within 2 km, as a raster and per hex
# ---------------------------------------------------------------------------

ROAD_DENSITY_DIR = OUTPUTS_DIR / "road_density"

# Density raster (100 m cells) over the road extract; depends on the extract only, so not tagged by subject.
# legacy: data/hex_grid/road_density_raster.npz
ROAD_DENSITY_RASTER_PATH = ROAD_DENSITY_DIR / "road_density_raster.npz"

# Filled hex grid plus density columns; written per subject and data layers (functions/subject_paths.subject_file).
# legacy: data/hex_grid/road_density_hex.gpkg
ROAD_DENSITY_HEX_PATH = ROAD_DENSITY_DIR / "road_density_hex.gpkg"

# Valhalla's density rule (graphenhancer.cc / speed_assigner.h): road km per km² within the radius,
# turned into a level 0-15 and tiers rural (<= 5) / suburban (6-10) / urban (11-15).
ROAD_DENSITY_RADIUS_M = 2_000             # kDensityRadius = 2.0 km
ROAD_DENSITY_LEVEL_SCALE = 0.7            # level = round(km/km² * 0.7), C++ rounding (half away from zero)
ROAD_DENSITY_MAX_LEVEL = 15               # level cap (>= 20.7 km/km²); also the dense-urban level
ROAD_DENSITY_MIN_SUBURBAN_LEVEL = 5       # kMinSuburbanDensity: levels above it are suburban or urban
ROAD_DENSITY_MAX_SUBURBAN_LEVEL = 10      # kMaxSuburbanDensity: levels above it are urban
ROAD_DENSITY_MARGINAL_URBAN_LEVEL = 11    # urban sub-tier: 11 marginal, 12-14 mid, 15 dense (15.0-16.4 km/km² at 11)

ROAD_DENSITY_CELL_M = 100                 # raster cell size
ROAD_DENSITY_SEGMENT_M = 10               # roads are cut into pieces this long; each piece's length goes to one cell

# Which OSM ways count toward density, matched to Valhalla's source (valhalla_position_Sep_21 §2).
ROAD_DENSITY_HIGHWAY_TYPES = {"motorway", "trunk", "primary", "secondary", "tertiary",
                              "unclassified", "residential", "road", "residential_link"}
ROAD_DENSITY_RAMP_HIGHWAY_TYPES = {"motorway_link", "trunk_link", "primary_link",
                                   "secondary_link", "tertiary_link"}   # ramps and turn channels
ROAD_DENSITY_EXCLUDED_SERVICE_VALUES = {"parking_aisle", "driveway", "drive-through"}  # service ways not counted
ROAD_DENSITY_COUNTED_SERVICE_VALUES = {"alley", "emergency_access"}   # service tags Valhalla still counts on main roads

ROAD_EXTRACT_OUTLINE_STEP_DEG = 0.01      # extract outline densified to this step before projecting (full-disk test)

# ---------------------------------------------------------------------------
# Snapshot review: basic statistics and figures of the data layers before analysis alters them
# ---------------------------------------------------------------------------

# Runs or replays the data-layer diagnostics (default subject only); run as a script, never imported (F1).
SNAPSHOT_REPORT_PATH = PROJECT_ROOT / "diagnostics" / "snapshot_report.py"
SNAPSHOT_VERBOSE_FLAG = "--verbose"   # its command-line switch for full output (paths, run notices)

# ---------------------------------------------------------------------------
# Construct graph (routing_graph.py, construct_graph block): cut the drive graph to its largest
# strongly connected component, find each hex's nearest roads, split those roads into equal pieces,
# assign each hex a node.
# The reduced graph depends on the OSM extract only. Every later file depends on the hex centroids,
# so it goes in the subject's "<lat>_<lon>" subfolder, tagged with the filled grid's data layers.
# ---------------------------------------------------------------------------

ROUTING_GRAPH_DIR = OUTPUTS_DIR / "routing_graph"

# Drive graph cut to its largest strongly connected component.
# legacy: data/bbbike/drive_graph_reduced.gpickle
REDUCED_DRIVE_GRAPH_PATH = ROUTING_GRAPH_DIR / "drive_graph_reduced.gpickle"

# Per subject: candidate roads per hex (one row per hex and road).
# legacy: data/hex_grid/nearest_drive_edges.gpkg
NEAREST_DRIVE_EDGES_PATH = ROUTING_GRAPH_DIR / "nearest_drive_edges.gpkg"

# Per subject: reduced graph with candidate roads split, and each split road's new nodes in order.
# legacy: data/hex_grid/split_drive_edges.pkl
SPLIT_DRIVE_GRAPH_PATH = ROUTING_GRAPH_DIR / "split_drive_edges.pkl"
# legacy: data/hex_grid/split_drive_edges.chains.pkl
SPLIT_DRIVE_CHAINS_PATH = ROUTING_GRAPH_DIR / "split_drive_edges.chains.pkl"

# Per subject: filled hex grid plus each hex's assigned node(s) and snap distances.
# legacy: data/hex_grid/hex_population_and_nodes.gpkg
HEX_NODES_PATH = ROUTING_GRAPH_DIR / "hex_population_and_nodes.gpkg"

CANDIDATES_PER_HEX = 2           # nearest roads kept per hex (different streets)
CANDIDATE_EXCLUDED_HIGHWAY_TYPES = {'motorway', 'motorway_link'}   # roads a trip can't start or end on

# Window for the second candidate: roads within the nearest road's distance + this. Matches routing's
# tie rule (functions/drive_routing.eligible_nodes uses this value, DESIGN.md Q12). Was 25 m (older belief that Google picks the most
# efficient entry); at 25 m, 643,127 of 4,078,906 hexes (default subject) stored a candidate 2 routing
# never used, and 160,782 of 748,661 candidate roads were split only because of it (user, 2026-10-09).
CANDIDATE_TIE_WINDOW_M = 1

ROAD_PIECE_MAX_M = 50            # candidate roads are cut into equal pieces of at most this length
SPLIT_NODE_ID_START = 900_000_000_000   # first id for new split nodes; above every OSM node id

# ---------------------------------------------------------------------------
# Build speed graphs (speed_graphs.enrich, build_speed_graphs block): the subject's split drive graph
# with signal flags and edge times, one file per drive model variant (blind, dense, dense_fringe, osmtable).
# Each graph depends on the split graph, so it goes in the subject's "<lat>_<lon>" subfolder, tagged with
# the filled grid's data layers; the variant name follows the file stem.
# ---------------------------------------------------------------------------

# OpenStreetMapSpeeds speed table; the osmtable variant reads its AU/VIC entry.
# legacy: data/OSM/default_speeds.json
OSM_SPEED_TABLE_PATH = FROZEN_INPUTS_DIR / "osm_speeds" / "default_speeds.json"

SPEED_GRAPHS_DIR = OUTPUTS_DIR / "speed_graphs"

# Per subject and variant: split_drive_edges_timed_<variant>_<tags>_<lat>_<lon>.pkl
# legacy: data/hex_grid/split_drive_edges_timed_<variant>.pkl
TIMED_DRIVE_GRAPH_PATH = SPEED_GRAPHS_DIR / "split_drive_edges_timed.pkl"

SPEED_GRAPH_VARIANTS = ("blind", "dense", "dense_fringe", "osmtable")   # drive model variants enrich builds by default

OSM_SPEED_TABLE_COUNTRY = "AU"   # ISO 3166-1 code of the speed table entry osmtable reads
OSM_SPEED_TABLE_STATE = "VIC"    # ISO 3166-2 subdivision of that entry

# blind, dense and dense_fringe: an untagged edge takes its highway class's default speed; a tagged
# edge takes its posted limit times a factor that depends on the density tier of its start node.
DEFAULT_SPEED_KMH_BY_HIGHWAY = {
    'motorway': 90,  'motorway_link': 45,
    'trunk': 85,     'trunk_link': 40,
    'primary': 65,   'primary_link': 30,
    'secondary': 55, 'secondary_link': 25,
    'tertiary': 40,  'tertiary_link': 20,
    'unclassified': 25,
    'residential': 25,
    'living_street': 10,
    'service': 15,
}
FALLBACK_SPEED_KMH = 50          # untagged edge whose class (and parent class) is missing from a table without "service"
POSTED_SPEED_FACTOR = 0.8        # posted limit x this, outside the dense urban tier
URBAN_POSTED_SPEED_FACTOR = 0.5  # posted limit x this in the dense urban tier (dense, dense_fringe)
FRINGE_FACTOR = 0.92             # dense_fringe: fringe urban edges get POSTED_SPEED_FACTOR x this (0.736); hand-set, to be replaced by fitted tier factors (DESIGN_pre_spine "Drive model selection")
UNREDUCED_HIGHWAY_TYPES = {'motorway', 'motorway_link', 'trunk', 'trunk_link'}   # posted limit used as is
FRINGE_MIN_DENSITY_LEVEL = 12    # dense_fringe: levels 12-14 are fringe urban (road_density calls them mid_urban); 15 is dense urban
MIN_VALID_SPEED_LIMIT_KMH = 1    # maxspeed tags outside this range are unreadable: the edge takes its class default
MAX_VALID_SPEED_LIMIT_KMH = 130
FIRST_ROAD_CLASS_WITHOUT_LINK_SPEED = 5   # links of road class 5+ (unclassified, residential, other) take their parent class's way speed
ROUNDABOUT_SPEED_FACTOR = 0.5    # Valhalla's kRoundaboutFactor: untagged roundabout edges get the way speed x this
OUTSIDE_RASTER_DENSITY_LEVEL = 0.0   # density level of nodes outside the road density raster (rural)

# ---------------------------------------------------------------------------
# Sample drive pairs (drive_samples, sample_drive_pairs block): origin-destination draws, their Google
# drive times, the join with each end's snap nodes, and the train / test split. Inputs: HEX_NODES_PATH,
# TIMED_DRIVE_GRAPH_PATH, VENUE_TABLES[HEX_VENUES_DATE], OPENING_HOURS_HIST_PATH. Files built from a
# subject's graphs go in its "<lat>_<lon>" subfolder, tagged with the filled grid's data layers. Both
# this stage and calibrate_pathing_agent write to PATHING_CALIBRATION_DIR.
# ---------------------------------------------------------------------------

PATHING_CALIBRATION_DIR = OUTPUTS_DIR / "pathing_calibration"

# The 2026-09-30 draws and their Google Routes times (frozen_inputs/README.md), keyed by draw_no.
# legacy: data/map_pathing/od_sample_pairs.csv
ROUTES_DRIVE_DRAWS_PATH = FROZEN_INPUTS_DIR / "routes_drive_eta_20260930" / "od_sample_pairs.csv"
# legacy: data/map_pathing/od_sample_pairs_google_estimates.csv
ROUTES_DRIVE_ETA_PATH = FROZEN_INPUTS_DIR / "routes_drive_eta_20260930" / "od_sample_pairs_google_estimates.csv"

# Per subject: a fresh draw (random_sampling), only checked against ROUTES_DRIVE_DRAWS_PATH; its
# .kept.pkl checkpoint sits beside it.
# legacy: data/map_pathing/od_sample_pairs.csv
ROUTES_DRIVE_REDRAW_PATH = PATHING_CALIBRATION_DIR / "od_sample_pairs.csv"
# Per subject: the draw's rejection counts.
# legacy: data/hex_grid/fixed_od_sample_fetch/google_api_log.json
ROUTES_DRIVE_SAMPLE_LOG_PATH = PATHING_CALIBRATION_DIR / "od_sample_log.json"

# Per subject: frozen draws + Google times + each end's snap nodes (join_drive_sets).
# legacy: data/hex_grid/od_expanded_drive_enriched.csv
ROUTES_DRIVE_ENRICHED_PATH = PATHING_CALIBRATION_DIR / "od_expanded_drive_enriched.csv"

# Output of a new paid Routes fetch (fetch_drive_eta, off); never the frozen file.
# legacy: data/map_pathing/od_sample_pairs_google_estimates.csv
ROUTES_DRIVE_FETCH_PATH = PATHING_CALIBRATION_DIR / "routes_drive_eta.csv"

# The draw (random_sampling): origin hex weighted by residents or workers (p = 0.5), destination a
# venue drawn uniformly, kept only if reachable within the window on the window graph.
ROUTES_DRIVE_SEED = 20260930                 # first draw; also seeds the fetch's departure-week offset
ROUTES_DRIVE_N_PAIRS = 4000                  # pairs kept per draw
ROUTES_DRIVE_DRAW_BATCH = 2000               # candidates drawn per batch; part of the random stream
ROUTES_DRIVE_WINDOW_S = 25 * 60              # blind raw seconds (before ALPHA), per Sep 29 §2
ROUTES_DRIVE_WINDOW_BETA_S = 2               # signal penalty for the window: OSRM convention, not fitted
ROUTES_DRIVE_WINDOW_VARIANT = "blind"        # timed graph the window is routed on (M0)
# Departure times: weekday 30-min slots, (1 - floor share) from the open-share histogram, floor share
# flat over the floor hours. The fetch puts each date up to the horizon ahead.
ROUTES_DRIVE_DEPARTURE_FLOOR_SHARE = 0.2
ROUTES_DRIVE_DEPARTURE_FLOOR_HOURS = (6, 24)          # local hours [start, end)
ROUTES_DRIVE_DEPARTURE_HORIZON_WEEKS = 52

# Second drive draw (2026-10): 4,000 new pairs, pooled with the 2026-09-30 draws and split at random
# into train and test at fit time. Same sampler and departure-time rule (80% open-share histogram,
# 20% flat 06:00-24:00), on the hours named by OPENING_HOURS_PULL_DATE. No origin-hex/destination-hex
# combination of ROUTES_DRIVE_DRAWS_PATH is drawn again.
ROUTES_DRIVE_DRAW2_SEED = 20261010
ROUTES_DRIVE_DRAW2_DRAW_NO_OFFSET = 100_000      # draw_no = offset + draw count, unique across draws
# Per subject: the draw, its rejection counts, and its paid Routes times.
ROUTES_DRIVE_DRAW2_PATH = PATHING_CALIBRATION_DIR / "od_sample_pairs_draw2.csv"
ROUTES_DRIVE_DRAW2_LOG_PATH = PATHING_CALIBRATION_DIR / "od_sample_log_draw2.json"
ROUTES_DRIVE_DRAW2_ETA_PATH = PATHING_CALIBRATION_DIR / "routes_drive_eta_draw2.csv"

# Train / test split of the pooled pairs (split_drive_pairs; DESIGN_pre_spine "Train / test scheme"): halves
# stratified by draw and grouped by destination hex, then CV folds inside the training half, same rule.
DRIVE_SPLIT_SEED = 20261011
DRIVE_SPLIT_N_HALVES = 2                     # train / test, about equal
DRIVE_CV_FOLDS = 5                           # k for grouped CV inside the training half (user, 2026-10-11)
# Per subject: one row per pair (draw_no, draw, dest_hex_id, half, fold).
DRIVE_SPLIT_PATH = PATHING_CALIBRATION_DIR / "drive_split.csv"

# ---------------------------------------------------------------------------
# Calibrate pathing agent (pathing_calibration, calibrate_pathing_agent block): the selected drive model
# fitted on the blind routing bundle, on the training half and on all pairs (DCL-13).
# ---------------------------------------------------------------------------

# Routing bundles built by prep_graph: one folder per timed graph and beta set, the graph as CSR arrays
# (.npy) with length, raw time and one signal-penalised time per beta.
# legacy: data/hex_grid/split_drive_edges_timed_<variant>_prep_b<betas>.pkl
PREPARED_GRAPHS_DIR = PATHING_CALIBRATION_DIR / "prepared_graphs"

# Signal penalties β (s per signal) per variant, as the selection round's routing runs used them; a
# bundle's folder name carries its variant's betas, so the fit's bundle is found by these.
DRIVE_RUN_BETAS = {
    "blind":        (0.0, 2.0),
    "osmtable":     (0.0, 2.0),
    "dense_fringe": (2.0, 10.0, 12.0, 14.0),
    "dense":        (12.0,),
}

# Drive model fit (functions/drive_model_fit.py; DCL-1..3): edge time = blind time_raw_s x m_group + beta
# per signalised head node, predicted = ALPHA x routed time; per route the fit is linear in ALPHA,
# ALPHA x m_group and ALPHA x beta, iterated with rerouting until it settles. Scaled groups are
# density-level ranges; edges outside every group (and outside DRIVE_FIT_EDGE_SET) keep blind time (m = 1).
DRIVE_FIT_DIR = PATHING_CALIBRATION_DIR / "fit"     # also holds the parked selection round's run-date folders
DRIVE_FIT_EDGE_ATTRS_PATH = DRIVE_FIT_DIR / "edge_attrs.npz"   # per subject: level and road flags per edge, base bundle order
DRIVE_MODEL_DIR = DRIVE_FIT_DIR / "model"    # per subject: params JSON and history CSV per pair set
DRIVE_FIT_BASE_VARIANT = "blind"             # timed graph whose time_raw_s, signals and routing bundle the fit scales
DRIVE_MODEL_NAME = "2tier"                   # the selected model (CV round 2026-10-11/12, test half 2026-10-12)
DRIVE_MODEL_GROUPS = ((15, 15),)             # its scaled group as (lowest, highest) density level
                                             # evidence: diagnostics/drive_model_selection.py
# Edges a group's factor acts on: "tagged" (posted limit, not motorway/trunk), "not_fast" (+ untagged,
# not motorway/trunk), "not_motorway" (+ trunk), "all" (+ motorway). "all" since 2026-10-12 (was
# "not_motorway"): chosen by a pre-set fallback, not by fit; DESIGN_pre_spine "Drive model selection",
# item 1. evidence: diagnostics/drive_untagged_share.py, diagnostics/drive_fit_edge_set.py,
# diagnostics/drive_motorway_absorption.py
DRIVE_FIT_EDGE_SET = "all"
DRIVE_FIT_LOSS_SCALE = 0.1                   # soft_l1 scale on log(predicted / Google) (user, 2026-10-11)
DRIVE_FIT_TOL_ROUTE_SHARE = 0.005            # converged: under 0.5% of routes change ...
DRIVE_FIT_TOL_PARAM_REL = 0.005              # ... and every m and beta moves under 0.5%
DRIVE_FIT_MAX_ROUNDS = 15
DRIVE_FIT_START_M = 1.5                      # start multiplier on blind time, every group (dry run: 1.51)
DRIVE_FIT_START_BETA_S = 12.0                # start signal penalty (dense variant's beta)
DRIVE_FIT_START_ALPHA = 1.0                  # start overall scale on route cost
DRIVE_FIT_MIN_PARAM = 1e-6                   # lower bound on ALPHA, ALPHA x m and ALPHA x beta
DRIVE_FIT_TOL_BETA_FLOOR_S = 1.0             # beta's relative move is taken against max(beta, this)
DRIVE_FIT_ROUND0_LIMIT_WINDOW_FACTOR = 3     # first round's search limit, x ROUTES_DRIVE_WINDOW_S x the largest m; speed only (exact)
DRIVE_FIT_ROUND0_LIMIT_PER_BETA = 100        # ... plus beta x this many signals
DRIVE_FIT_N_JOBS = 8                         # joblib workers; they share the bundle's memory-mapped arrays
DRIVE_FIT_BATCH_SIZE = 20                    # pairs per joblib batch

# ---------------------------------------------------------------------------
# PT network (r5py_pt_graph.py, construct_pt_graph block): r5py TransportNetwork from an OSM extract
# and three PTV GTFS feeds (concepts/transit.md TRN-1..3).
# ---------------------------------------------------------------------------

# PTV GTFS feeds downloaded 2026-10-13, service 2026-10-08 to 2026-12-31 (inputs/README.md); they
# replace the frozen 2026-09-21 feeds (frozen_inputs/gtfs_ptv/, service to 2026-11-29), which end before
# the TRN-7 departure window does. Keys are r5py's feed names.
# legacy: data/GTFS_EXTRACT/gtfs/{2,3,4}/google_transit.zip
PT_GTFS_DIR = INPUTS_DIR / "gtfs_ptv_20261013"
PT_GTFS_SOURCE_PATHS = {
    "ptv_metro_train": PT_GTFS_DIR / "metro_train" / "google_transit.zip",
    "ptv_tram":        PT_GTFS_DIR / "tram" / "google_transit.zip",
    "ptv_metro_bus":   PT_GTFS_DIR / "metro_bus" / "google_transit.zip",
}
PT_GRAPH_DIR = OUTPUTS_DIR / "pt_graph"                          # legacy: data/GTFS_r5
PT_GTFS_CLEANED_DIR = PT_GRAPH_DIR / "gtfs_cleaned"              # feed copies with empty tables dropped; legacy: data/GTFS_r5
PT_BUILD_LOG_PATH = PT_GRAPH_DIR / "r5_build.log"                # R5's console output, redirected; legacy: data/GTFS_r5/r5_build.log
PT_UNLINKED_STOPS_PATH = PT_GRAPH_DIR / "unlinked_stops.csv"     # legacy: data/GTFS_r5/unlinked_stops.csv
# GTFS route types left out of the network (TRN-11, Myki metro scope): 701 = the regional town buses
# PTV ships inside the metro bus feed. Their routes, trips, stop_times and the stops only they use go.
PT_EXCLUDED_ROUTE_TYPES = [701]
PT_R5_MAX_MEMORY = "8G"                   # JVM heap for the R5 build; roughly 60-75% of RAM
# build check: the transit layer has service on each date; for now the draw's window date
# (= TRANSIT_WINDOW_DATE, defined below); the per-release departure window's ends once computed (TRN-7)
PT_COVERS_CHECK_DATES = [date(2026, 10, 21)]

# ---------------------------------------------------------------------------
# Sample transit pairs (transit validation pairs; concepts/transit.md TRN-7, TRN-10, T3-T5): hex → venue
# pairs drawn like drive, windowed by uncalibrated r5py on the PT network, split at the draw. Weekday and
# minute drawn now; each pair's date is assigned when its fetch release is known. Files go in the
# subject's "<lat>_<lon>" subfolder, as drive's.
# ---------------------------------------------------------------------------

TRANSIT_PAIRS_DIR = OUTPUTS_DIR / "transit_validation"
TRANSIT_PAIRS_PATH = TRANSIT_PAIRS_DIR / "transit_pairs.csv"          # the draw: in-window and smoke-test pairs
TRANSIT_PAIRS_LOG_PATH = TRANSIT_PAIRS_DIR / "transit_pairs_log.json"  # rejection counts
TRANSIT_SPLIT_PATH = TRANSIT_PAIRS_DIR / "transit_split.csv"          # half, fold, exploration and smoke-test flags
TRANSIT_DRAW_RELEASE = "20261009"            # PTV export date of the network the draw is windowed on (PT_GTFS_DIR)

TRANSIT_PAIRS_SEED = 20261015                # pair draw
TRANSIT_DEPARTURE_SEED = 20261016            # weekday, minute and date; child streams per pair (TRN-7 D)
TRANSIT_SPLIT_SEED = 20261017                # train / test halves, CV folds, exploration subset
TRANSIT_N_PAIRS = 2500                       # in-window pairs kept (T4: 1,000 / 1,000 usable)
TRANSIT_SMOKE_TEST_N = 125                   # out-of-window pairs, ~5% (T5); in neither half
TRANSIT_DRAW_BATCH = 2000                    # candidates drawn per batch; part of the random stream
TRANSIT_RESERVE_SCREEN_PAIRS = 3500          # extra in-window pairs the checkpoint extension routes for, past TRANSIT_N_PAIRS
# Window (TRN-10): r5py's fastest time over the weekday at a date every in-scope route group serves,
# taken as a low percentile over the hours; 2x the top transit band (SCR-1, 1,200 s).
TRANSIT_WINDOW_S = 40 * 60
# Walking speed for every r5py call (walk-only trips and walking inside transit; WLK-1): the median
# effective speed (R5 walk-only path / Google walk-only time) on 217 training pairs. The 2026-10-15/16
# draw ran at r5py's default 3.6 km/h; its kept pairs stand (TRN-10).
# evidence: diagnostics/walk_only_speed_fit.py
WALK_SPEED_KMH = 4.16
TRANSIT_WINDOW_DATE = date(2026, 10, 21)     # a Wednesday inside the 2026-10-09 release's full coverage
TRANSIT_WINDOW_HOURS = (6, 24)               # local hours [start, end) the fastest time is taken over
TRANSIT_WINDOW_PERCENTILE = 1                # r5py percentile over those departures; stands in for "fastest"
# Candidates farther apart than this (haversine) skip r5py and count as out of window: the longest
# in-window reach measured (28.1 km) x 1.25. Not used for T5, which tests r5py's own rejections.
# evidence: diagnostics/transit_window_reach.py
TRANSIT_PREFILTER_KM = 35
# Guard: a 0-min r5py time between points farther apart than this is an artefact; rejected and counted.
# Cause found 2026-10-15: r5py returns 0 wherever from_id == to_id (transit_window keeps the ids
# disjoint), so none is expected. evidence: diagnostics/transit_window_reach.py
TRANSIT_ZERO_TIME_MAX_M = 1000
TRANSIT_DRAW_CHUNK_ORIGINS = 50              # unique origins per r5py call
TRANSIT_DRAW_N_PROCESSES = 2                 # r5py worker processes for the window; RAM-bound (~3.5 GB each)
TRANSIT_DRAW_R5_MAX_MEMORY = "4G"            # JVM heap per draw worker; 4G ran as fast as 8G (2026-10-15)
# Departures (TRN-7 A): equal-weight mean of the two drive draws' slot-probability vectors, each from
# its own hours pull's histogram; floor share and hours are drive's (ROUTES_DRIVE_DEPARTURE_FLOOR_*).
TRANSIT_DEPARTURE_HOURS_PULLS = ["20260902", "20261010"]
TRANSIT_DEPARTURE_HIST_PATHS = [OPENING_HOURS_DIR / f"opening_hours_{pull}_hist_{HOURS_SLOT_MIN}min.csv"
                                for pull in TRANSIT_DEPARTURE_HOURS_PULLS]
TRANSIT_SPLIT_N_HALVES = 2                   # train / test (T3)
TRANSIT_CV_FOLDS = 5                         # grouped folds inside the training half, written at the draw
TRANSIT_EXPLORATION_N = 500                  # training-half pairs fetched first (TRN-10)
# evidence: diagnostics/transit_narrow_window_soundness.py (sound), diagnostics/transit_window_width_checks.py
TRANSIT_VALIDATION_WINDOW_MIN = 1            # r5py departure_time_window when validating (TRN-7 E)
# Google transit fetch (TRN-8): Routes Essentials, one request per pair, raw answers kept next to each
# fetch file (.raw.jsonl). Each pair's date is a seeded pick among its release's fetch dates on the
# drawn weekday (TRN-7).
TRANSIT_GOOGLE_PATH = TRANSIT_PAIRS_DIR / "transit_google.csv"              # one row per fetched pair
TRANSIT_GOOGLE_SMOKE_PATH = TRANSIT_PAIRS_DIR / "transit_google_smoke.csv"  # gating smoke-test calls, kept apart
# First and last departure date per release: TRN-7's per-release window, computed for a fetch on or
# before 2026-10-18 (bus group 42 stops from Oct 26). evidence: diagnostics/transit_release_window.py
# 20261016: steps (1)-(4) only (step 5 dropped, TRN-7), for a fetch on 2026-10-18; run through a scratchpad
# wrapper, files diagnostics/diagnostic_data/transit_release_window_20261018_*.
TRANSIT_RELEASE_FETCH_DATES = {"20261009": (date(2026, 10, 19), date(2026, 10, 23)),
                               "20261016": (date(2026, 10, 19), date(2026, 11, 2))}
# Second batch (TRN-10): the checkpoint's reserve, the first in-window pairs past the draw by draw_no
# (screened on TRANSIT_DRAW_RELEASE at 3.6 km/h), fetched on the next release. Own files, outside the split.
TRANSIT_RESERVE_N = 2000                     # reserve pairs taken
TRANSIT_RESERVE_PAIRS_PATH = TRANSIT_PAIRS_DIR / "transit_pairs_reserve.csv"
TRANSIT_SECOND_RELEASE = "20261016"          # PTV export date the reserve is fetched under (inputs/gtfs_ptv_20261018/)
TRANSIT_GOOGLE_RESERVE_PATH = TRANSIT_PAIRS_DIR / "transit_google_20261016.csv"
TRANSIT_SET_FETCH_CHUNK = 200                # pairs per fetch call; failures checked after each
TRANSIT_FETCH_MAX_FAIL_SHARE = 0.02          # stop if a chunk's non-200 share exceeds this
# Test-half extension (TRN-15): the next TRANSIT_TEST_EXT_N in-window pairs past the reserve, all to the test
# half. The checkpoint's last 1,660 come first; past its end the stream is screened on, by the same gate
# (stock r5py, TRANSIT_DRAW_WALK_SPEED_KMH) but on TRANSIT_SECOND_RELEASE's feeds (user, 2026-10-20), into
# a checkpoint of its own. Feeds cleaned as construct_pt_graph cleans them, named per release (r5py caches
# inputs by file name). Fetched on TRANSIT_SECOND_RELEASE from TRANSIT_TEST_EXT_FIRST_FETCH_DATE.
TRANSIT_DRAW_WALK_SPEED_KMH = 3.6            # r5py's default walk speed, the gate the checkpoint was screened at (TRN-10)
# in-window pairs past TRANSIT_N_PAIRS + TRANSIT_RESERVE_SCREEN_PAIRS (the screen's target: 8,500 in window in all);
# the checkpoint's last batch, routed whole, already holds 160 of them (1,660 past the reserve, 2026-10-20)
TRANSIT_TEST_EXT_SCREEN_PAIRS = 2500
TRANSIT_SECOND_GTFS_DIR = INPUTS_DIR / "gtfs_ptv_20261018"   # TRANSIT_SECOND_RELEASE's export
TRANSIT_SECOND_GTFS_SOURCE_PATHS = {
    "ptv_metro_train": TRANSIT_SECOND_GTFS_DIR / "metro_train" / "google_transit.zip",
    "ptv_tram":        TRANSIT_SECOND_GTFS_DIR / "tram" / "google_transit.zip",
    "ptv_metro_bus":   TRANSIT_SECOND_GTFS_DIR / "metro_bus" / "google_transit.zip",
}
TRANSIT_SECOND_GTFS_CLEANED_DIR = PT_GRAPH_DIR / "gtfs_cleaned_20261016"
TRANSIT_TEST_EXT_N = 4000                    # pairs added to the test half (user, 2026-10-20)
TRANSIT_TEST_EXT_PAIRS_PATH = TRANSIT_PAIRS_DIR / "transit_pairs_test_ext.csv"
TRANSIT_GOOGLE_TEST_EXT_PATH = TRANSIT_PAIRS_DIR / "transit_google_test_ext_20261016.csv"
# first departure date: the release window's start (Oct 19) had passed when fetched, so later dates only
TRANSIT_TEST_EXT_FIRST_FETCH_DATE = date(2026, 10, 21)
# Fresh holdout (user, 2026-10-21): the next TRANSIT_HOLDOUT_N in-window pairs past the test extension, same
# stream and gate (stock r5py at TRANSIT_DRAW_WALK_SPEED_KMH on TRANSIT_SECOND_RELEASE's feeds), screened into a
# checkpoint of its own. Fetched under TRANSIT_SECOND_RELEASE (user, 2026-10-21, cap US$20) and sealed: nothing
# compares it with R5 until the freeze record and the holdout reading rule are written.
TRANSIT_HOLDOUT_N = 4000                     # pairs in the fresh holdout (user, 2026-10-21)
TRANSIT_HOLDOUT_PAIRS_PATH = TRANSIT_PAIRS_DIR / "transit_pairs_holdout.csv"
TRANSIT_GOOGLE_HOLDOUT_PATH = TRANSIT_PAIRS_DIR / "transit_google_holdout_20261016.csv"
TRANSIT_HOLDOUT_FIRST_FETCH_DATE = date(2026, 10, 22)   # first departure date: Oct 21's departures partly past at the fetch
TRANSIT_SMOKE_N_ORDINARY = 2                 # exploration pairs, any length
TRANSIT_SMOKE_N_SHORT = 2                    # exploration pairs near the walk/transit switchover
TRANSIT_SMOKE_SHORT_M = (300, 600)           # haversine range [min, max) of a "short" pair (switchover ~600-700 m, Limitations)
TRANSIT_SMOKE_N_OVER_WINDOW = 1              # T5 smoke-test pairs (r5py: over the window)
# Boundary top-up (TRN-14) for the band metric's zones (TRN-13): pairs drawn by TRN-10's pair rule on
# haversine ranges only (no r5py window, R5 never consulted), fetched until each zone holds the target.
# Zone = Google's default in-scope route, arrival from the requested departure, rounded minutes (SCR-10).
TRANSIT_ZONES_MIN = {1: (7, 13), 2: (17, 23)}  # [low, high] Google minutes, +-3 around the 10 and 20 min cuts
# Haversine range per zone: 2.5th-97.5th percentile of the zone's pairs (training half + second batch),
# widened to 50 m; gaps 3.8% and 4.7% of zone pairs. evidence: diagnostics/transit_zone_ranges.py
TRANSIT_TOPUP_RANGES_M = {1: (350, 1650), 2: (850, 4700)}
TRANSIT_TOPUP_SEED = 20261018                # top-up candidate stream (own seed: no draw_no shared with the draw)
TRANSIT_TOPUP_FIRST_DRAW_NO = 1_000_001      # first top-up draw_no, far past the draw's checkpoint (72,000)
TRANSIT_TOPUP_N_PER_RANGE = 2000             # candidates listed per range; ~2x the calls projected for 200
TRANSIT_TOPUP_RELEASE = TRANSIT_SECOND_RELEASE  # fetched under the 2026-10-16 release (Oct 19 - Nov 2)
TRANSIT_TOPUP_TARGET_PER_ZONE = 200          # zone pairs wanted per zone (TRN-14)
TRANSIT_TOPUP_COUNTS_EARLIER = True          # training-half and second-batch zone pairs count toward it (user, 2026-10-18)
TRANSIT_TOPUP_PILOT_PER_RANGE = 30           # pilot calls per range (TRN-14 (2)); they count toward the target
TRANSIT_TOPUP_CHUNK_PER_RANGE = 25           # calls per open range between zone recounts
TRANSIT_TOPUP_MAX_CALLS = 400                # call ceiling for the whole top-up, pilot included: 200 per range (user, 2026-10-18)
TRANSIT_TOPUP_PAIRS_PATH = TRANSIT_PAIRS_DIR / "transit_pairs_topup.csv"
TRANSIT_GOOGLE_TOPUP_PATH = TRANSIT_PAIRS_DIR / "transit_google_topup.csv"
TRANSIT_TOPUP_SELECTION_PATH = TRANSIT_PAIRS_DIR / "transit_topup_selection.csv"  # draw_no, range it was sent for, chunk

# ---------------------------------------------------------------------------
# Reachability (planned; no stage yet): trip uncertainty (functions/trip_uncertainty.py, RCH-23 (b)).
# Google's time given the model's predicted time, drawn from fit pairs with similar predicted times.
# evidence: diagnostics/trip_error_conditional.py, diagnostics/transit_error_by_service.py
# ---------------------------------------------------------------------------
TRIP_ERROR_K_NEIGHBOURS = 400       # fit pairs nearest in log(predicted time) per query
TRIP_ERROR_MIN_MODEL_S = 30         # predicted seconds clipped below at this before the log ratio
TRIP_ERROR_NIGHT_END_MIN = 7 * 60   # transit departures before 07:00 (min of day) form their own group (user, 2026-10-22)
# Fit pairs. Transit as the 75th called the function: transit_holdout_score's scored seen + holdout pairs (frozen
# model vs Google's default); these live in diagnostics/diagnostic_data/ only, with no pipeline stage making them
# (flagged 2026-10-23, 88th). Drive: the 2tier test-half predictions of the pathing_calibration run below.
TRIP_ERROR_TRANSIT_FIT_PATHS = [PROJECT_ROOT / "diagnostics" / "diagnostic_data"
                                / f"transit_holdout_score_20261022_{part}_results.csv" for part in ("seen", "holdout")]
TRIP_ERROR_DRIVE_FIT_RUN = "20261012"                 # run-date folder under DRIVE_FIT_DIR/<subject>/
TRIP_ERROR_DRIVE_FIT_FILE = "test/test_predictions.csv"   # inside that folder

# ---------------------------------------------------------------------------
# Reachability pass (reachability.py, reachability block; RCH-1..26). Every run writes a build stamp (RCH-18) and
# reuses saved output only under a matching stamp; the drive pass is stamped apart from the GTFS release.
# ---------------------------------------------------------------------------
REACHABILITY_DIR = OUTPUTS_DIR / "reachability"      # per subject: one folder per pass, named by its stamp hash
REACH_STAMP_FILE = "stamp.json"
REACH_STAMP_HASH_CHARS = 10                          # stamp hash characters in a pass folder's name

# Drive, band 3 (RCH-2, RCH-15..17): reversed search per venue hex on the all-pairs fit; costs per node.
REACH_DRIVE_MODEL_PAIRS = "all_pairs"                # which fit of DRIVE_MODEL_NAME the pass runs (RCH-15)
REACH_DRIVE_STORAGE_FACTOR = 2.5                     # costs stored to this x the routed band cut (Q21, user 2026-10-23)
REACH_DRIVE_BATCH_HEXES = 250                        # venue hexes per parquet file (resume unit)
REACH_EDGE_FLAG_M = 1000                             # Q5: horizon reaching a node this close to the graph's outer boundary

# Transit network for bands 1-2 (RCH-18): the newest GTFS release in inputs/, cleaned as construct_pt_graph cleans
# (TRN-11), with the v2 pathways network (TRN-13 (f)): train station entrances spliced into the OSM extract, spurs
# drawn as tunnel footways timed by GTFS pathways.txt, each hub platform stop moved to the far end of a stub. Every
# feed and the derived extract carry the release in their file names (r5py caches inputs by name, TRN-2).
# evidence: diagnostics/transit_pathway_network_v2.py
REACH_GTFS_RELEASE = "20261016"                      # PTV export date of the release
REACH_GTFS_DIR = INPUTS_DIR / "gtfs_ptv_20261018"    # its download folder
REACH_GTFS_SOURCE_PATHS = {
    "ptv_metro_train": REACH_GTFS_DIR / "metro_train" / "google_transit.zip",
    "ptv_tram":        REACH_GTFS_DIR / "tram" / "google_transit.zip",
    "ptv_metro_bus":   REACH_GTFS_DIR / "metro_bus" / "google_transit.zip",
}
REACH_TRAIN_FEED = "ptv_metro_train"                 # the feed whose pathways are built
REACH_NETWORK_DIR = REACHABILITY_DIR / "network"     # per release: cleaned feeds, moved train feed, derived extract
PATHWAY_ENTRANCE_TYPE = "2"                          # GTFS location_type of a station entrance
PATHWAY_PLATFORM_TYPES = ["0", ""]                   # GTFS location_type of a platform stop
PATHWAY_LINK_RADIUS_M = 300                          # entrance -> street splice radius (R5's first stop-link radius)
PATHWAY_SNAP_M = 0.5                                 # reuse a street node this close instead of splicing
PATHWAY_STUB_M = 2.0                                 # stub length; the platform stop sits at its far end
PATHWAY_STUB_DIRECTIONS = 16                         # stub directions tried (the one furthest from any street wins)
PATHWAY_ZIGZAG_TOOTH_MIN_M = 20                      # spur drawn to its timed length: straight run per tooth at most ...
PATHWAY_ZIGZAG_AMPLITUDE_MAX_M = 30                  # ... and sideways reach at most this
PATHWAY_GRID_DEG = 0.004                             # candidate-street grid cell (~350-450 m)
PATHWAY_NEW_NODE_ID_BASE = 50_000_000_000            # above any OSM node id in the extract (checked at build)
PATHWAY_NEW_WAY_ID_BASE = 9_000_000_000
PATHWAY_TAG = ("platica", "pathway")                 # tag on every way the build adds
PATHWAY_WALK_SPEED_KMH = 4.16                        # spur metres = pathways.txt seconds x this (as v2, = WALK_SPEED_KMH)

# Transit routing, bands 1-2 (RCH-19..21, TRN-16): the frozen model through the P8r draws jar, whole windows of
# the subject's hours read in chunks of whole 30-min slots, one envelope per chunk from the span oracle (RCH-26).
REACH_TRANSIT_JAR_PATH = OUTPUTS_DIR / "r5_patches" / "r5-v7.5.1-r5py-all_p8-r_draws.jar"   # frozen P1-P3 + P8r draws
REACH_TRANSIT_JAR_SHA256 = "a4490e39d7aab425a790d3da1b7dd0e69be58850b0f077e89d41677c44c76656"
# evidence: diagnostics/transit_r5_patch_reach.py
REACH_TRANSIT_R5_MAX_MEMORY = "7G"                   # JVM heap (as the P8r tests)
REACH_TRANSIT_WALK_SPEED_KMH = 4.143                 # the frozen model's walk speed (TRN-16, DESIGN Q24)
REACH_TRANSIT_MAX_TIME_MIN = 31                      # R5 max time: cap 30 + 1, cut after rounding (RCH-19, SCR-10)
# evidence: diagnostics/transit_search_cap.py (4 of 1,936 band-2 pairs past 30 min: the tail RCH-26 prices)
REACH_TRANSIT_CHUNK_MAX_MIN = 90                     # minutes per draws call (P8r placeholders 1..90 within 1-99)
REACH_ORACLE_CUT_MIN = 30                            # envelope: oracle <= this in any slot of the chunk (RCH-26, 78th)
REACH_ORACLE_TRANSFER_CHARGE_S = 200                 # every ride after the first (the frozen model's P3)
REACH_ORACLE_SPLIT_RADIUS_M = 1600                   # R5's LINK_RADIUS_METERS for the oracle's point splits
REACH_POPULATED_MIN_PERSONS = 1.0                    # residents + workers for a hex to be an origin
REACH_ORIGINS_PER_FILE = 500                         # origins per parquet file of a chunk (resume unit)
REACH_TRANSIT_THREADS = 12                           # origins routed at once in the one JVM (shared network; not hashed)
# The subject's own open hours (Places pull 2026-10-10), one fixed date per day type inside the release's window
# (DESIGN Q25, RCH-20; user 2026-10-23): day type -> (date, [(first slot start, last slot end)]).
REACH_SUBJECT_WINDOWS = {
    "Mon-Thu": (date(2026, 10, 28), [("17:30", "21:00")]),
    "Fri":     (date(2026, 10, 30), [("17:30", "21:30")]),
    "Sat":     (date(2026, 10, 31), [("12:30", "15:00"), ("17:00", "21:30")]),
    "Sun":     (date(2026, 11, 1), [("12:30", "15:00"), ("17:00", "21:00")]),
}
# Span oracle dates per day type (RCH-26: rides over every date of the day type, week of 2026-10-26).
REACH_ORACLE_DAY_TYPE_DATES = {
    "Mon-Thu": [date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29)],
    "Fri":     [date(2026, 10, 30)],
    "Sat":     [date(2026, 10, 31)],
    "Sun":     [date(2026, 11, 1)],
}

# Band-3 diners' transit fields (RCH-27; built 2026-10-26, 112th): staged best-of-K (SCR-23) needs each band-3 diner's
# own bands 1-2 field. Hybrid targeting (RCH-20 (2)): the whole-read day types' windows as the subject pass chunks
# them, one random-start window per other span (the 81st's spans: the subject's windows, split at the breaks below).
# Origins merged per window and stage band by the threshold-then-weighted flower rule: a populated hex with persons
# >= T routes on its own; its aperture-7 flower's lighter populated members route from their persons-weighted centroid.
# A hex inside the subject pass's envelope for every minute of a window keeps that pass's exact route.
REACH_BAND3_DIR_NAME = "transit_band3"               # pass folder prefix under REACHABILITY_DIR (stamp hash appended)
REACH_BAND3_MERGE_PERSONS = {1: 20, 2: 80}           # T per stage band, persons (user, 2026-10-26, 112th)
# evidence: diagnostics/band3_flower_merge_error.py (field misplaced: T20 at 10 min 0.09%, T80 at 20 min 2.9%)
# R5 max time per stage band: the band's chance tail (>= REACH_TABLE_FLOOR_P) + 1, as 31 for band 2's 29.65 min;
# band 1's ends at 14.75 min (Claude's, 112th; the user's "cut + 1" = 11 would drop chances of 0.23 at 11 min);
# checked by an assert in scoring.build_band3_table
REACH_BAND3_MAX_TIME_MIN = {1: 16, 2: REACH_TRANSIT_MAX_TIME_MIN}
REACH_HYBRID_WHOLE_DAY_TYPES = ["Mon-Thu"]           # read whole: the heavy week weight (RCH-20 (2))
REACH_HYBRID_SPAN_BREAKS = {"Sat": ["20:30"]}        # span starts inside the subject's windows (Sat late, 81st)
REACH_HYBRID_WINDOW_MIN = 30                         # one random-start window per other span
REACH_HYBRID_SEED = 20261026

# ---------------------------------------------------------------------------
# Scoring (scoring.py, scoring block; SCR-1..17). First step, the reach table (SCR-11, SCR-12, RCH-23): per band,
# 30-min slot and contestable hex of the subject, every venue hex's chance of reaching the hex within the band, read
# from the saved passes. One folder per table, named by its stamp hash (as the passes, RCH-18).
# ---------------------------------------------------------------------------
SCORING_DIR = OUTPUTS_DIR / "scoring"                # per subject: one folder per reach table
BAND_CUTS_MIN = {1: 10, 2: 20, 3: DRIVE_BAND_DURATION_MIN}   # SCR-1: bands 1-2 walk + transit, band 3 drive
REACH_TABLE_FLOOR_P = 0.01        # rows kept where the chance is at least this, subject's and venue's (user, 2026-10-23)
REACH_TABLE_P_LEVELS = 255        # a chance is stored as round(P x this) in a uint8

# Venue hours (SCR-13, VEN-13): each venue's open share per 30-min slot and day type, its own pulled hours where it has
# them, otherwise imputed from its tags by partial pooling along a tag chain (functions/hours_imputation.py).
HOURS_IMPUTATION_PULLS = ["20260902", "20261010"]   # keys of OPENING_HOURS_PULL_DIRS; the newer fetch wins per venue
HOURS_DAY_TYPES = {"Mon-Thu": [1, 2, 3, 4], "Fri": [5], "Sat": [6], "Sun": [0]}   # Google day indices, 0 = Sunday
HOURS_IMPUTATION_MAX_TAGS = 10        # a venue's chain draws on its first this many tags (sorted), as VEN-13's backoff
# Pseudo-venues of the parent estimate at each chain step: M = 5 had the lowest leave-one-out Brier at the subject's
# slots on the grid 1-100 (0.1683; 2 and 10 within 0.001).
HOURS_IMPUTATION_SHRINK_M = 5         # evidence: diagnostics/venue_hours_slot_imputation.py
VENUE_OPEN_SHARE_PATH = (OPENING_HOURS_DIR / f"venue_open_share_ven{HEX_VENUES_DATE}_"
                         f"hrs{'-'.join(HOURS_IMPUTATION_PULLS)}_{HOURS_SLOT_MIN}min.parquet")

# Share step (SCR-19, SCR-15, SCR-2, SCR-13, SCR-14): draws of reach (per venue hex, shared by co-located venues) and
# hours (own, else a donor's week; one Mon-Thu day per draw), then the subject's share per hex and competitor credits.
# Donor weeks keep a venue's slots and days coherent; independent slots get every joint statistic wrong.
# evidence: diagnostics/venue_hours_donor_draws.py
SCORING_HOURS_RULES = ["donor", "all_open"]      # first = headline; "all_open" every venue open (comparison, SCR-13)
SCORING_RATING_STEP = 0.1                        # displayed rating resolution: the slider's step (SCR-16)
SCORING_RATING_RANGE = (1.0, 5.0)                # displayed ratings, lowest and highest
# Ordering key (SCR-4, SCR-20): shrunk rating s = (n·r + m·C) / (n + m), never shown. m = sigma^2 / tau^2: tau 0.40 from
# venues with 300-900 reviews, sigma at the 1-5 scale's ceiling at C (no data measure it; wrong toward scepticism).
# evidence: diagnostics/rating_shrinkage_m.py
SCORING_SHRINK_M = 15                            # review count at which a venue's own rating and C weigh equally
SCORING_SHRINK_C = 4.25                          # field mean of displayed ratings (precision-weighted), the shrink target
# Key cells (SCR-19 layout): one exact cell per slider value's key; rivals within one credit interval tie for credits only.
# evidence: diagnostics/share_cells_exact.py
SCORING_CREDIT_KEY_STEP = 0.02                   # credit cell width on the shrunk key from SCORING_CREDIT_FINE_FROM up
SCORING_CREDIT_FINE_FROM = 4.0                   # shrunk key where fine credit cells start
SCORING_CREDIT_COARSE_STEP = 0.1                 # credit cell width below SCORING_CREDIT_FINE_FROM
SCORING_KEY_TIE_TOL = 1e-9                       # keys this close tie exactly (float noise; equal (rating, reviews))
SCORING_FOCAL_RATING_RANGE = (3.5, 5.0)          # subject's rating slider (SCR-16): headlines per rating in this range
# Rating-rule variants (DESIGN Q29, closed 97th: S*'): build_shares(rating_key=...) runs one; the default is the
# headline's. "shrunk" S* (control), "flat" F (displayed rating, equal ratings tie; control), "shrunk_top" S*' (S* with a
# 5.0 read as 4.975 and a 1.0 as 1.025), "percentile" P (midrank among the venues nearest in log review count).
# evidence: diagnostics/rating_rule_disagreement.py
SCORING_RATING_KEYS = ["shrunk", "flat", "shrunk_top", "percentile"]
SCORING_RATING_KEY = "shrunk_top"                # the headline key (SCR-20, Q29)
SCORING_TOP_RATING = 5.0                         # displayed top rating ...
SCORING_TOP_READ = 4.975                         # ... read as the middle of 4.95-5.0 (shrunk_top)
SCORING_BOTTOM_RATING = 1.0                      # displayed bottom rating ...
SCORING_BOTTOM_READ = 1.025                      # ... read as the middle of 1.0-1.05 (shrunk_top)
SCORING_UNRATED_KEY = -1.0                       # flat and percentile: unrated venues below every rated one
SCORING_PERCENTILE_NEIGHBOURS = 500              # percentile: reference venues nearest in log review count
SCORING_PERCENTILE_COARSE_STEP = 0.05            # percentile credit cell width below SCORING_PERCENTILE_FINE_FROM
SCORING_PERCENTILE_FINE_FROM = 0.5
SCORING_PERCENTILE_FINE_STEP = 0.01
# Competitor pools (96th; ideas, not decided: scoring.md Notes "Niche-tag standing", "Hours-overlap competitor pool").
# Each competitor enters the pool with a chance per draw (venue-wide, the same draw in every reach unit): "all" 1;
# "niche" 1 if Google tags it SCORING_NICHE_TAG, else 0 (strict, owner's request); "overlap" the share of its
# tag-predicted open time (VEN-13 profile, day types weighted by days) inside the subject's tag-predicted hours, the
# slots where at least SCORING_OVERLAP_OPEN_MIN of its tag peers are open (subject's own hours blinded; Claude's rule);
# "overlap_flat" every competitor at the overlap pool's mean chance (control: thinning without the hours pattern).
# evidence: diagnostics/hours_overlap_pool_checks.py
SCORING_POOLS = ["all", "niche", "overlap", "overlap_flat"]
SCORING_POOL = "all"                             # the headline pool
SCORING_NICHE_TAG = "mexican_restaurant"         # the subject's cuisine tag
SCORING_OVERLAP_OPEN_MIN = 0.5                   # as SCR-21's >= 50% of tag peers open
SCORING_Q_GRID = [round(0.05 * k, 2) for k in range(1, 20)]   # diner persistence q, 0.05-0.95 (SCR-15)
SCORING_HEADLINE_Q = 0.7                         # SCR-15 convention; also the q of competitor credits (SCR-14)
SCORING_TOP_N = [1, 2, 3]                        # Top-N variant (SCR-2)
# Staged best-of-K (SCR-23, DESIGN Q32; built 2026-10-26, 109th): a band-b diner searches b stages, each K looks at
# random over that band's whole field (bands nested), K >= 1 with mean k; the best by the key among all seen wins.
# The k marks are q 0.6 / 0.7 / 0.8 as mean depth 1 / (1 - q); the owner's guess pins the headline (SCR-16).
SCORING_HEADLINE_K = 1 / (1 - 0.7)               # 3.33 looks per stage: the convention mark (q 0.7's mean depth)
SCORING_K_MARKS = [2.5, SCORING_HEADLINE_K, 5.0] # reference marks on the k curve (SCR-23)
SCORING_K_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, SCORING_HEADLINE_K, 4.0, 5.0, 6.0, 8.0, 10.0]   # mean looks per stage
SCORING_LOOK_SHAPES = ["geometric", "poisson"]   # K per stage: geometric (stop chance 1/k per look), 1 + Poisson(k - 1)
SCORING_LOOK_SHAPE = "geometric"                 # the headline shape; Poisson the sensitivity
SCORING_LOOK_TAIL_TOL = 1e-9                     # look counts summed until P(K > j) is below this (the rest at the end)
SCORING_STAGED_HOURS_RULES = SCORING_HOURS_RULES[:1]   # donor only; all_open deferred (user, 110th: known sensitivity)
SCORING_STAGED_WORKERS = 3                       # staged units in parallel processes (1: in this process); cores split among them
                                                 # 4 -> 3 (117th): bands 1-2 workers peak ~1.7 GB each; 3 keep ~1.5 GB free
# GPU port (DESIGN Q32, 116th-117th): each staged unit's device is fixed by its band (CPU and GPU draw different random
# numbers, so a free-worker choice would make reruns differ); "gpu" units run in one CuPy process beside the CPU pool,
# its next band-3 unit's levels built on the CPU while the GPU runs draws.
SCORING_BACKEND_BY_BAND = {1: "cpu", 2: "cpu", 3: "gpu"}   # "cpu" (numpy / numba) or "gpu" (CuPy)
SCORING_GPU_THREADS = 2                          # CPU threads of the GPU process (numba, BLAS; the levels build ahead)
SCORING_GPU_OVERLAP = False                      # GPU process beside the CPU pool (True) or after it; False fits 16 GB RAM
                                                 # (117th: the GPU process peaks 6.6 GB with the levels built ahead)
SCORING_MC_REL_SE = 0.005                        # draws per reach unit until the headline's MC error is below this
SCORING_MC_ABS_SE = 1.0                          # ... or below this many persons (a near-zero headline: band 3)
SCORING_MIN_DRAWS = 24                           # 6 Mon-Thu day cycles
SCORING_MAX_DRAWS = 400
SCORING_DRAW_BATCH = 8                           # draws between stop checks: whole Mon-Thu day cycles
SCORING_HEX_CHUNK = 2048                         # hexes per dense block (memory: chunk x venue hexes x 4 bytes;
                                                 # 8192 -> 2048 in the 112th: band-3 units peak 8.3 -> 4.4 GB)
SCORING_SEED = 20261024

# Share report (scoring_report.py; 94th): per band the headline in persons per open slot of the subject (sum over slots
# / sum of its open chance, SCR-13), the curve over q, the rating slider, the band-3 unlock, competitor denials and
# contention (SCR-14), and the census profile of the persons captured. Written into the shares folder.
SHARE_REPORT_HEADLINE_NAME = "report_headline_{metric}.csv"
SHARE_REPORT_COMPETITORS_NAME = "competitor_denials_{metric}_{rule}.csv"
SHARE_REPORT_PROFILE_NAME = "band_demographics_{metric}_{rule}.csv"
SHARE_REPORT_NAME_SHARE = 0.01      # competitor named at >= this share of its band's ceiling (SCR-14 cutoff)
SHARE_REPORT_UNLOCK_BAND = 3        # band whose unlock rating is reported (user's lean, 94th)
SHARE_REPORT_UNLOCK_SHARE = 0.01    # unlock: lowest slider rating capturing >= this share of reached persons (Claude's rule)
# Rarity line per slider rating (SCR-22): among rated venues within the window of the subject's review-count percentile
SHARE_REPORT_RARITY_NAME = "report_rarity.csv"
SHARE_REPORT_RARITY_HALF_WIDTH_PCT = 2.5   # window half-width in percentile points, cut to the distance to the top (user)
SHARE_REPORT_RARITY_COUNT_FLOOR = 5        # under this many venues at or above a rating, the line gives the count itself
SHARE_REPORT_RARITY_TENTHS_SHARE = 1 / 3  # above this share of the window, "N in 10" instead of "1 in N" (user)
SHARE_REPORT_RARITY_MAX_DENOMINATOR = 300  # a line's denominator above this is restated per SHARE_REPORT_RARITY_LARGE_BASE (user)
SHARE_REPORT_RARITY_LARGE_BASE = 1000     # "N in 1,000"

# Census profile of captured persons (DESIGN "Demographic showcase": <= 6 metrics per side). Residents by the SA2 of
# a hex's centroid, workers by its DZN; each hex takes its area's mix. Comparison: the GCC below.
PROFILE_YEAR = 2021
PROFILE_ABS_DIR = CENSUS_INPUTS_DIR / CENSUS_ABS_DIR_NAME.format(year=PROFILE_YEAR)
PROFILE_DZN_DIR = CENSUS_INPUTS_DIR / CENSUS_DZN_DIR_NAME.format(year=PROFILE_YEAR)
PROFILE_SA1_BOUNDARIES_PATH = PROFILE_ABS_DIR / f"SA1_{PROFILE_YEAR}_AUST_GDA2020.shp"
PROFILE_DZN_BOUNDARIES_PATH = PROFILE_DZN_DIR / f"DZN_{PROFILE_YEAR}_AUST_GDA2020.shp"
PROFILE_STATE = "Victoria"
PROFILE_COMPARISON_GCC = "Greater Melbourne"
PROFILE_TOP_OCCUPATIONS = 8         # occupations shown by name; the rest "Other"
PROFILE_TOP_INDUSTRIES = 7          # industries shown by name; the rest "Other"
PROFILE_INCOME = {
    "<$500/wk": ["Negative income", "Nil income", "$1-$149 ($1-$7,799)", "$150-$299 ($7,800-$15,599)",
                 "$300-$399 ($15,600-$20,799)", "$400-$499 ($20,800-$25,999)"],
    "$500-999": ["$500-$649 ($26,000-$33,799)", "$650-$799 ($33,800-$41,599)", "$800-$999 ($41,600-$51,999)"],
    "$1,000-1,749": ["$1,000-$1,249 ($52,000-$64,999)", "$1,250-$1,499 ($65,000-$77,999)",
                     "$1,500-$1,749 ($78,000-$90,999)"],
    "$1,750-2,999": ["$1,750-$1,999 ($91,000-$103,999)", "$2,000-$2,999 ($104,000-$155,999)"],
    "$3,000+": ["$3,000-$3,499 ($156,000-$181,999)", "$3,500 or more ($182,000 or more)"]}
PROFILE_BIRTHPLACE = {
    "Australia": ["Australia (includes External Territories)"],
    "NZ & Pacific": ["Oceania and Antarctica, nfd", "New Zealand", "Melanesia", "Micronesia", "Polynesia (excludes Hawaii)"],
    "UK & Ireland": ["United Kingdom, Channel Islands and Isle of Man", "Ireland"],
    "Other Europe": ["North-West Europe, nfd", "Western Europe", "Northern Europe", "Southern and Eastern Europe, nfd",
                     "Southern Europe", "South Eastern Europe", "Eastern Europe"],
    "Asia": ["South-East Asia, nfd", "Mainland South-East Asia", "Maritime South-East Asia", "North-East Asia, nfd",
             "Chinese Asia (includes Mongolia)", "Japan and the Koreas", "Southern and Central Asia, nfd", "Southern Asia",
             "Central Asia"],
    "Americas, Africa, Middle East": ["North Africa and the Middle East, nfd", "North Africa", "Middle East",
                                      "Americas, nfd", "Northern America", "South America", "Central America",
                                      "Caribbean", "Sub-Saharan Africa, nfd", "Central and West Africa",
                                      "Southern and East Africa"]}
PROFILE_TRAVEL_MODE = {      # 2021 was a lockdown census: "Worked at home" is inflated
    "Public transport": ["Train", "Bus", "Ferry", "Tram/light rail"],
    "Car": ["Car, as driver", "Car, as passenger", "Truck", "Motorbike/scooter", "Taxi/ride-share service"],
    "Walk or cycle": ["Walked only", "Bicycle"], "Worked at home": ["Worked at home"]}
PROFILE_RESIDENT_AGE = {
    "0-19": ["0-9 years", "10-19 years"], "20-29": ["20-29 years"], "30-39": ["30-39 years"], "40-49": ["40-49 years"],
    "50-59": ["50-59 years"], "60+": ["60-69 years", "70-79 years", "80-89 years", "90-99 years", "100 years and over"]}
PROFILE_WORKER_AGE = {
    "15-24": ["15-19 years", "20-24 years"], "25-34": ["25-29 years", "30-34 years"],
    "35-44": ["35-39 years", "40-44 years"], "45-54": ["45-49 years", "50-54 years"],
    "55-64": ["55-59 years", "60-64 years"],
    "65+": ["65-69 years", "70-74 years", "75-79 years", "80-84 years", "85-89 years", "90-94 years", "95-99 years",
            "100 years and over"]}
PROFILE_CARS = {"0 cars": ["No motor vehicles"], "1 car": ["One motor vehicle"], "2 cars": ["Two motor vehicles"],
                "3+ cars": ["Three motor vehicles", "Four or more motor vehicles"]}
PROFILE_STUDY = {"Full-time student": ["Full-time student"], "Part-time student": ["Part-time student"],
                 "Not studying": ["Not attending"]}
# Per side, metric: (TableBuilder file, header level to keep (None = single level), groups or a top-k count).
PROFILE_RESIDENT_TABLES = {
    "Age": (PROFILE_ABS_DIR / "SA2_SEX_AGE_MDCP_2021.csv", 1, PROFILE_RESIDENT_AGE),
    "Personal income (weekly)": (PROFILE_ABS_DIR / "SA2_INCP_2021.csv", None, PROFILE_INCOME),
    "Birthplace": (PROFILE_ABS_DIR / "SA2_BPLP_2-digit_2021.csv", None, PROFILE_BIRTHPLACE),
    "Cars per dwelling": (PROFILE_ABS_DIR / "SA2_EN_DWELLING_HCFMD_VEHRD_2021.csv", -1, PROFILE_CARS),
    "Travel to work": (PROFILE_ABS_DIR / "SA2_MTWP_2-digit_Level_2021.csv", None, PROFILE_TRAVEL_MODE),
    "Student status": (PROFILE_ABS_DIR / "SA2_STUP_2021.csv", None, PROFILE_STUDY)}
PROFILE_WORKER_TABLES = {
    "Age": (PROFILE_DZN_DIR / "DZN_AgeinFiveYearGroups_2021.csv", None, PROFILE_WORKER_AGE),
    "Personal income (weekly)": (PROFILE_DZN_DIR / "DZN_INCP_2021.csv", None, PROFILE_INCOME),
    "Birthplace": (PROFILE_DZN_DIR / "DZN_BPLP_2-digit_Level_2021.csv", None, PROFILE_BIRTHPLACE),
    "Occupation": (PROFILE_DZN_DIR / "DZN_OCCP_1-digit_2021.csv", None, PROFILE_TOP_OCCUPATIONS),
    "Industry": (PROFILE_DZN_DIR / "DZN_INDP_1-digit_Level_2021.csv", None, PROFILE_TOP_INDUSTRIES),
    "Travel to work": (PROFILE_DZN_DIR / "DZN_MTW15P_2021.csv", None, PROFILE_TRAVEL_MODE)}
PROFILE_EXCLUDED_CATEGORIES = ["Total", "Not stated", "Not applicable", "Inadequately described"]   # top-k metrics

# ---------------------------------------------------------------------------
# Global Constants
# ---------------------------------------------------------------------------

METRIC_CRS = "EPSG:7855"        # GDA2020 / MGA zone 55: metres, for areas and distances
GEOGRAPHIC_CRS = "EPSG:4326"    # WGS 84 lat/lon, as stored in every file
LOCAL_TIMEZONE = "Australia/Melbourne"   # departure times and dates are local

# Text Search query variants for update_google_data_expanded; moves to config.py with that stage.
PROBE_VARIANTS = ['restaurant', 'places to eat', 'takeaway', 'food', 'cafe']
