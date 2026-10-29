"""r5py window for the transit pair draw (TRN-10): each candidate's fastest transit time over a weekday.

Worker processes each load the r5py network once; the calling process never starts a JVM. r5py reads its
JVM settings from the command line when it is imported, so each worker sets them before its first import.
Candidates are routed in chunks: one r5py call per chunk, from its unique origin hexes to its unique
venues, then only the candidates' own (origin, venue) cells are kept.
"""
import sys
from datetime import datetime, time as dtime, timedelta
from multiprocessing import get_context

import geopandas as gpd
import pandas as pd

from functions.pt_network import check_r5py_working_copies

# Candidate columns read here, and the column written.
DRAW_NO_COL, ORIGIN_HEX_COL, PLACE_ID_COL = "draw_no", "origin_hex", "place_id"
ORIGIN_LAT_COL, ORIGIN_LON_COL, DEST_LAT_COL, DEST_LON_COL = "origin_lat", "origin_lon", "dest_lat", "dest_lon"
FASTEST_MIN_COL = "r5py_fastest_min"
R5PY_ID_COL, R5PY_FROM_COL, R5PY_TO_COL = "id", "from_id", "to_id"
GEOGRAPHIC_CRS = "EPSG:4326"

_network = None                      # per worker process: the r5py TransportNetwork


def _init_worker(max_memory, pbf_path, gtfs_paths):
    """Per worker: JVM heap on the command line, stale-copy guard (TRN-2), then the network."""
    global _network
    sys.argv = sys.argv[:1] + ["--max-memory", max_memory]
    from r5py import TransportNetwork
    from r5py.util import Config as R5pyConfig
    check_r5py_working_copies([pbf_path, *gtfs_paths], R5pyConfig().CACHE_DIR)
    _network = TransportNetwork(pbf_path, gtfs_paths)


def _fastest_chunk(task):
    """One chunk's candidates -> draw_no and fastest minutes (NaN: over max_time or no route)."""
    from r5py import TransportMode, TravelTimeMatrix
    chunk_df, departure, window, percentile, max_time, speed_walking_kmh = task
    origins_df = chunk_df.drop_duplicates(ORIGIN_HEX_COL)
    venues_df = chunk_df.drop_duplicates(PLACE_ID_COL).reset_index(drop=True)
    # r5py returns 0 min wherever from_id == to_id, so venue ids start above every origin id.
    venue_ids = origins_df[ORIGIN_HEX_COL].max() + 1 + venues_df.index.to_numpy()
    venue_id_of = pd.Series(venue_ids, index=venues_df[PLACE_ID_COL])
    origins = gpd.GeoDataFrame({R5PY_ID_COL: origins_df[ORIGIN_HEX_COL].to_numpy()}, crs=GEOGRAPHIC_CRS,
                               geometry=gpd.points_from_xy(origins_df[ORIGIN_LON_COL], origins_df[ORIGIN_LAT_COL]))
    destinations = gpd.GeoDataFrame({R5PY_ID_COL: venue_ids}, crs=GEOGRAPHIC_CRS,
                                    geometry=gpd.points_from_xy(venues_df[DEST_LON_COL], venues_df[DEST_LAT_COL]))
    matrix_df = pd.DataFrame(TravelTimeMatrix(
        _network, origins=origins, destinations=destinations, departure=departure,
        departure_time_window=window, percentiles=[percentile],
        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK], max_time=max_time,
        speed_walking=speed_walking_kmh))
    matrix_df = matrix_df.rename(columns={f"travel_time_p{percentile}": FASTEST_MIN_COL})
    cells_df = chunk_df[[DRAW_NO_COL, ORIGIN_HEX_COL]].assign(
        **{R5PY_TO_COL: venue_id_of.loc[chunk_df[PLACE_ID_COL]].to_numpy()})
    cells_df = cells_df.merge(matrix_df, left_on=[ORIGIN_HEX_COL, R5PY_TO_COL],
                              right_on=[R5PY_FROM_COL, R5PY_TO_COL], how="left", validate="many_to_one")
    return cells_df[[DRAW_NO_COL, FASTEST_MIN_COL]]


class TransitWindowPool:
    """n_processes r5py workers, each holding the network; use as a context manager."""

    def __init__(self, n_processes, max_memory, pbf_path, gtfs_paths):
        self._pool = get_context("spawn").Pool(n_processes, initializer=_init_worker,
                                               initargs=(max_memory, pbf_path, list(gtfs_paths)))

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self._pool.close()
        self._pool.join()

    def fastest_minutes(self, candidates_df, window_date, window_hours, percentile, max_time_s, chunk_size,
                        speed_walking_kmh):
        """draw_no and fastest transit minutes over window_hours (local [start, end)) on window_date, at
        the given r5py percentile and walking speed, for every candidate; NaN where over max_time_s or unroutable.
        Chunks of chunk_size unique origins go to the workers."""
        departure = datetime.combine(window_date, dtime(window_hours[0]))
        window = timedelta(hours=window_hours[1] - window_hours[0])
        max_time = timedelta(seconds=max_time_s)
        origin_hexes = candidates_df[ORIGIN_HEX_COL].unique()
        tasks = [(candidates_df[candidates_df[ORIGIN_HEX_COL].isin(origin_hexes[start:start + chunk_size])],
                  departure, window, percentile, max_time, speed_walking_kmh)
                 for start in range(0, len(origin_hexes), chunk_size)]
        parts = []
        for i, part_df in enumerate(self._pool.imap(_fastest_chunk, tasks), start=1):
            parts.append(part_df)
            print(f"    window chunk {i}/{len(tasks)} done")
        return pd.concat(parts, ignore_index=True)
