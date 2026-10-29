import subprocess
import sys

# Venue layer
import legacy_datasets
import places_details
import opening_hours

# Census and hex grid
import abs_census
import hex_tile_construction
import road_density
from functions.input_helper import read_subject_location, subject_coord_path

# Road graphs and drive routing
import road_graphs
import speed_graphs
import routing_graph
import drive_samples
import pathing_calibration
import transit_samples
import transit_fetch
import reachability
import scoring
import transit_band3
import scoring_report

# API budget guard
import api_ledger

# Config
from config import *

def main():
    print_api_usage()  # this billing month's API calls per SKU: used / free allowance / left

    # Stage switches, in pipeline order.
    rebuild_legacy_datasets = False
    fetch_enterprise_hours = False         # PAID: Places Enterprise pull
    enterprise_hours_fetch_limit = 1       # venues this run; 1 = test call, None = all remaining
    build_opening_hours = False            # hours histogram from config.OPENING_HOURS_PULL_DATE
    pre_process_census = False
    should_update_census = False           # also build one layer from a newer year in inputs/census/
    census_update_layer = "abs"            # "abs" (SA1 residents) or "dzn" (DZN workers)
    census_update_year = None              # e.g. 2026; None = newest complete year
    construct_hex_tiles = False
    subject_name = None                    # None = default subject; else a file name (no .txt) in inputs/alt_subjects/
    should_rebuild_hex_layers = False
    map_construction = False
    should_rebuild_road_graphs = False
    should_rebuild_road_density = False
    open_snapshot_review = False           # data-layer diagnostics' latest results and figures
    is_snapshot_verbose = False            # also print file paths and run notices
    construct_graph = False
    should_rebuild_routing_graph = False
    build_speed_graphs = False
    should_rebuild_speed_graphs = False
    sample_drive_pairs = False
    should_redraw_first_drive_set = False   # check: reproduces the 2026-09-30 set only with OPENING_HOURS_PULL_DATE = "20260902"
    should_draw_second_drive_set = False    # skipped if the draw exists
    should_rebuild_second_drive_set = False # only before its Google times are fetched
    should_fetch_second_drive_set = False   # PAID: Compute Routes Pro; quota 5,000/day
    second_drive_set_fetch_limit = 1        # pairs this run; 1 = test call, None = all remaining
    should_join_drive_sets = False          # pool both draws with Google times (the routing input)
    should_split_drive_sets = False         # train/test halves and CV folds; skipped if the split exists
    calibrate_pathing_agent = False
    should_refit_drive_model = False        # ~25 min: training half, then all pairs
    sample_transit_pairs = False            # draw ~10 h on 2 r5py workers; resumes from its checkpoint
    should_rebuild_transit_draw = False     # only before any Google fetch
    should_split_transit_pairs = False      # train/test halves, CV folds, exploration set; skipped if it exists
    should_smoke_test_transit_fetch = False  # PAID: Routes Essentials, 5 calls (TRN-8 gate)
    should_fetch_transit_google = False     # PAID: Routes Essentials, 2,625 calls; before the release's first date
    run_reachability = False
    should_run_drive_reach = False          # band 3, every venue hex (~20 min, ~45 GB); never beside a JVM run
    drive_reach_hex_limit = None            # first n venue hexes only (a check run, own folder); None = all
    should_build_transit_network = False    # newest GTFS release + pathways network (config.REACH_GTFS_RELEASE)
    should_rebuild_transit_network = False
    should_run_transit_reach = False        # bands 1-2, subject's hours (P8r draws; ~5 h, one JVM, resumable)
    transit_reach_chunk_limit = None        # chunks this run; 1 = the timing run, None = all
    run_scoring = False
    should_build_reach_table = False        # per band, slot and contestable hex, each venue hex's chance (~minutes, free)
    should_run_band3_transit = False        # RCH-27: band-3 diners' transit fields (~4 h, one JVM, resumable; free)
    should_build_band3_table = False        # the band-3 pass read into the reach table's folder (~minutes, free)
    should_build_venue_open_shares = False  # every venue's open share per slot and day type (own hours or imputed; free)
    should_build_shares = False             # SCR-19: subject's share per hex, headlines, credits (~1 h, free)
    should_build_staged_shares = False      # SCR-23: the same under staged best-of-K, bands 1-3 (free; band 3 needs the band-3 table)
    should_report_shares = False            # headline, slider, band-3 unlock, denials and contention CSV (~1 min)
    should_profile_shares = False           # census profile of captured and reached persons per band (~2 min)
    share_report_rule = "q"                 # the report's share rule: "q" (SCR-15) or "staged" (SCR-23)

    subject_lat, subject_lon = read_subject_location(subject_coord_path(subject_name))

    # Deprecated stages (docs/DEPRECATED.md): update_google_data_legacy, compile_legacy_google_to_csv,
    # compile_new_google_to_csv, update_google_data_new, update_google_data_expanded,
    # google_enterprise, basic_stats.

    # Legacy venue datasets rebuilt from frozen inputs.
    if rebuild_legacy_datasets:
        legacy_datasets.rebuild_legacy_datasets()

    # Places Enterprise opening hours: draw, fetch, weekday histogram.
    if fetch_enterprise_hours:
        places_details.draw_enterprise_hours_sample()
        places_details.fetch_enterprise_hours(limit=enterprise_hours_fetch_limit)
    if build_opening_hours:
        opening_hours.build_opening_hours()

    # Census tables (2021, plus an optional newer year).
    if pre_process_census:
        abs_census.build_census_2021()
        if should_update_census:
            abs_census.build_census_update(census_update_layer, census_update_year)

    # Hex grid and its layers: residents, workers, venue counts.
    if construct_hex_tiles:
        hex_tile_construction.build_hex_grid(subject_lat, subject_lon, should_rebuild_hex_layers)
        hex_tile_construction.build_residents_layer(subject_lat, subject_lon, should_rebuild_hex_layers)
        hex_tile_construction.build_workers_layer(subject_lat, subject_lon, should_rebuild_hex_layers)
        hex_tile_construction.build_venue_counts_layer(subject_lat, subject_lon, should_rebuild_hex_layers)
        hex_tile_construction.assemble_hex_layers(subject_lat, subject_lon)

    # Drive graph from OSM, road density raster and per-hex table.
    if map_construction:
        road_graphs.build_road_graphs(should_rebuild_road_graphs)
        road_density.assign_road_density(subject_lat, subject_lon, should_rebuild_road_density)

    # Review of the data layers.
    if open_snapshot_review:
        verbose_args = [SNAPSHOT_VERBOSE_FLAG] if is_snapshot_verbose else []
        subprocess.run([sys.executable, str(SNAPSHOT_REPORT_PATH), *verbose_args], check=True)  # run as a script, not imported (F1)

    # Routing graph: reduced, split, hex centroids assigned to nodes.
    if construct_graph:
        routing_graph.reduce_isolated_edges(should_rebuild_routing_graph)
        routing_graph.find_split_candidate_edges(subject_lat=subject_lat, subject_lon=subject_lon,
                                                 should_rebuild=should_rebuild_routing_graph)
        routing_graph.split_edges(subject_lat=subject_lat, subject_lon=subject_lon,
                                  should_rebuild=should_rebuild_routing_graph)
        routing_graph.centroid_node_assignment(subject_lat=subject_lat, subject_lon=subject_lon,
                                               should_rebuild=should_rebuild_routing_graph)

    # Timed speed graphs, one per drive model variant.
    if build_speed_graphs:
        speed_graphs.enrich(subject_lat, subject_lon, should_rebuild=should_rebuild_speed_graphs)

    # Drive pairs: draws, Google drive times, join, train/test split.
    if sample_drive_pairs:
        if should_redraw_first_drive_set:
            drive_samples.random_sampling(subject_lat, subject_lon)
        if should_draw_second_drive_set:
            drive_samples.draw_second_drive_set(subject_lat, subject_lon,
                                                should_rebuild=should_rebuild_second_drive_set)
        if should_fetch_second_drive_set:
            drive_samples.fetch_second_drive_set(subject_lat, subject_lon, limit=second_drive_set_fetch_limit)
        if should_join_drive_sets:
            drive_samples.join_drive_sets(subject_lat, subject_lon)
        if should_split_drive_sets:
            drive_samples.split_drive_pairs(subject_lat, subject_lon)

    # Drive model calibration: the selected model fitted on the training half and on all pairs.
    if calibrate_pathing_agent:
        pathing_calibration.calibrate_pathing_agent(subject_lat, subject_lon, should_refit=should_refit_drive_model)

    # PT network (r5py), stage construct_pt_graph: run r5py_pt_graph.py directly; only its own run config
    # saves the build log.

    # Transit pairs: draw on the r5py window, then train/test split.
    if sample_transit_pairs:
        transit_samples.draw_transit_pairs(subject_lat, subject_lon, should_rebuild=should_rebuild_transit_draw)
        if should_split_transit_pairs:
            transit_samples.split_transit_pairs(subject_lat, subject_lon)

    # Google transit times (TRN-8): smoke test first, then the whole draw on TRN-7's per-release dates.
    if should_smoke_test_transit_fetch:
        transit_fetch.smoke_test_transit_fetch(subject_lat, subject_lon)
    if should_fetch_transit_google:
        transit_fetch.fetch_transit_pairs(subject_lat, subject_lon)
    # Later collection sets (reserve, top-up, test-half extension, holdout) and the checkpoint extensions:
    # transit_collection.py, run by set and step.

    # Reachability pass (RCH-1..26): drive band 3 for every venue hex; transit bands 1-2 for the subject's envelope.
    if run_reachability:
        if should_run_drive_reach:
            reachability.drive_pass(subject_lat, subject_lon, hex_limit=drive_reach_hex_limit)
        if should_build_transit_network:
            reachability.build_transit_network(should_rebuild=should_rebuild_transit_network)
        if should_run_transit_reach:
            reachability.transit_subject_pass(subject_lat, subject_lon, chunk_limit=transit_reach_chunk_limit)

    # Scoring (SCR-1..23): first the reach table (SCR-11, SCR-12, RCH-23) from the saved passes, then band-3 diners' own
    # transit fields (RCH-27), which need the table's band-3 hexes.
    if run_scoring:
        if should_build_reach_table:
            scoring.build_reach_table(subject_lat, subject_lon)
        if should_run_band3_transit:
            transit_band3.band3_pass(subject_lat, subject_lon)
        if should_build_band3_table:
            scoring.build_band3_table(subject_lat, subject_lon)
        if should_build_venue_open_shares:
            scoring.build_venue_open_shares()
        if should_build_shares:
            scoring.build_shares(subject_lat, subject_lon)
        if should_build_staged_shares:
            scoring.build_staged_shares(subject_lat, subject_lon)
        if should_report_shares:
            scoring_report.report_shares(subject_lat, subject_lon, share_report_rule)
        if should_profile_shares:
            scoring_report.profile_shares(subject_lat, subject_lon, share_report_rule)


def print_api_usage():
    """Print this billing month's Google API usage per SKU, read from the API ledger.

    Covers every SKU in config.API_FREE_ALLOWANCE, so a new SKU appears without changes here.
    Prints "uncapped" for SKUs with no free allowance (allowance is None).
    """
    usage_by_sku = api_ledger.summary()  # dict: sku -> {"used": int, "allowance": int | None, "remaining": int | None}
    divider = "-" * 20
    print(f"{divider} API usage, billing month {api_ledger.billing_month()} {divider}")
    for sku, usage in usage_by_sku.items():
        if usage["allowance"] is None:
            print(f"{sku}: used {usage['used']} (uncapped)")
        else:
            print(f"{sku}: used {usage['used']} of {usage['allowance']}, {usage['remaining']} left")
    print()


if __name__ == "__main__":
    main()
