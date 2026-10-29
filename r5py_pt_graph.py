"""Build the r5py PT network (construct_pt_graph) and check it against its build log.

Run this file directly with its output redirected to config.PT_BUILD_LOG_PATH: R5 writes its build log
to the console, and the checks read that log back. r5py caches a built network by its input files'
contents, so an unchanged rerun loads the cache and the log carries no build messages.
"""
import sys

import config

# r5py reads its JVM settings from the command line when it is imported, so these go first.
sys.argv += ["--max-memory", config.PT_R5_MAX_MEMORY]
sys.argv += ["--verbose"]            # R5 prints its build log; the checks below read it

from r5py import TransportNetwork  # noqa: E402
from r5py.util import Config as R5pyConfig  # noqa: E402

from functions import pt_network  # noqa: E402


def build_r5_network():
    """Copy the GTFS feeds without empty tables or excluded route types (TRN-11), build the network,
    save the unlinked stops and print checks."""
    config.PT_GTFS_CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    gtfs_paths = []
    for feed_name, src_path in config.PT_GTFS_SOURCE_PATHS.items():
        dst_path = config.PT_GTFS_CLEANED_DIR / f"{feed_name}.zip"
        rows_to_drop = pt_network.excluded_route_type_rows(src_path, config.PT_EXCLUDED_ROUTE_TYPES)
        dropped_tables = pt_network.copy_gtfs_dropping_empty(src_path, dst_path, rows_to_drop)
        if dropped_tables:
            print(f"{feed_name}: dropped empty tables {dropped_tables}")
        gtfs_paths.append(dst_path)

    pt_network.check_r5py_working_copies([config.ROAD_EXTRACT_PBF_PATH] + gtfs_paths, R5pyConfig().CACHE_DIR)
    network = TransportNetwork(config.ROAD_EXTRACT_PBF_PATH, gtfs_paths)   # the live extract (DESIGN Q7)
    print(network.timezone)        # expect Australia/Melbourne
    extent_bounds = network.extent.bounds   # the built street network's extent: (west, south, east, north)
    print(extent_bounds)
    for check_date in config.PT_COVERS_CHECK_DATES:
        print("covers", check_date, network.transit_layer.covers(check_date))

    log_lines = pt_network.read_log_lines(config.PT_BUILD_LOG_PATH)
    pt_network.print_log_summary(log_lines)
    unlinked_indices = pt_network.unlinked_stop_indices(log_lines)
    print("unique unlinked:", len(unlinked_indices))

    pt_network.print_stops_outside_extent(gtfs_paths, extent_bounds)

    unlinked_df = pt_network.unlinked_stops_df(network._transport_network.transitLayer, unlinked_indices)
    unlinked_df[["feed", "stop_id"]].to_csv(config.PT_UNLINKED_STOPS_PATH, index=False)
    pt_network.print_unlinked_inside_extent(unlinked_df, gtfs_paths, extent_bounds)


# Uncomment to run the build from this file, with its output redirected to the build log.
# build_r5_network()
