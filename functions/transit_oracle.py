"""Graph oracle for the transit envelope (RCH-26, RCH-21 Stage A): one reverse Dijkstra from a venue on a two-layer
graph built from R5's own street and transit layers (walk graph and stops, each twice: took_transit no / yes). Ride
edges join every stop pair (i, j) on a trip, weighted by the shortest single-trip t_j - t_i over trips departing i
inside the window and arriving at j by its end; the first ride is free to board, every ride inside layer 1 adds the
frozen model's transfer charge (P3); waits are 0. Never slower than the frozen model (superset test, 76th / 78th), so
{oracle <= cut} holds every hex the model reaches the venue from within the cut.
Ported from diagnostics/reachability_graph_oracle.py (span oracles: one graph per day type x 30-min slot, rides over
every date of the day type, each with its service day before and after)."""
import datetime

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

MM_PER_M = 1000
KMH_PER_MPS = 3.6
SECONDS_PER_MIN = 60
DAY_S = 86_400
DAY_OFFSETS = (-1, 0, 1)                 # service days before / after whose trips can fall in a window
LAYERS = 2                               # took_transit no / yes
ZERO_WEIGHT_S = 1e-3                     # stands in for 0 s (scipy reads stored zeros as no edge)
SPLIT_COLUMNS = ["edge", "v0", "v1", "d0_m", "d1_m"]


def as_numpy(trove_list):
    return np.asarray(trove_list.toArray(), dtype=np.int64)


def walk_edges(street_layer, jpype, walk_speed_kmh):
    """Directed pedestrian edges of R5's street layer: (from, to, seconds), and each edge pair's from-vertex."""
    edge_store = street_layer.edgeStore
    assert edge_store.edgeTraversalTimes is None and (edge_store.costFields is None or edge_store.costFields.size() == 0)
    from_pair, to_pair = as_numpy(edge_store.fromVertices), as_numpy(edge_store.toVertices)
    lengths_mm, flags = as_numpy(edge_store.lengths_mm), as_numpy(edge_store.flags)
    assert len(flags) == 2 * len(from_pair)
    pedestrian = int(jpype.JClass("com.conveyal.r5.streets.EdgeStore$EdgeFlag").ALLOWS_PEDESTRIAN.flag)
    edge = np.arange(len(flags))
    pair = edge >> 1
    is_forward = edge % 2 == 0
    source = np.where(is_forward, from_pair[pair], to_pair[pair])
    target = np.where(is_forward, to_pair[pair], from_pair[pair])
    keep = (flags & pedestrian) != 0
    seconds = lengths_mm[pair] / MM_PER_M / (walk_speed_kmh / KMH_PER_MPS)
    return (source[keep], target[keep], seconds[keep]), from_pair


def all_schedules(transit_layer):
    """Every scheduled trip once: [(stops, arrivals, departures)] and service codes; frequency trips are refused."""
    trips, codes = [], []
    for pattern in transit_layer.tripPatterns:
        stops = np.asarray(pattern.stops, dtype=np.int64)
        for schedule in pattern.tripSchedules:
            assert schedule.headwaySeconds is None, "frequency-based trip: the oracle reads scheduled trips only"
            trips.append((stops, np.asarray(schedule.arrivals, dtype=np.int64),
                          np.asarray(schedule.departures, dtype=np.int64)))
            codes.append(schedule.serviceCode)
    return trips, np.asarray(codes)


def service_mask(transit_layer, date, jpype):
    services = transit_layer.getActiveServicesForDate(
        jpype.JClass("java.time.LocalDate").of(date.year, date.month, date.day))
    return np.array([bool(services.get(i)) for i in range(transit_layer.services.size())])


def day_type_trips(transit_layer, jpype, schedules, dates):
    """Trips running on any of the dates, on one service day's clock: service day D + k's trips shifted by k days
    (k in DAY_OFFSETS); one copy per (trip, shift)."""
    trips, codes = schedules
    keys = set()
    for date in dates:
        for offset in DAY_OFFSETS:
            mask = service_mask(transit_layer, date + datetime.timedelta(days=offset), jpype)
            keys.update((int(k), offset) for k in np.flatnonzero(mask[codes]))
    return [(trips[k][0], trips[k][1] + offset * DAY_S, trips[k][2] + offset * DAY_S) for k, offset in sorted(keys)]


def ride_edges(trips, start_s, end_s):
    """Min single-trip time per stop pair (i before j on a trip, departs i >= start_s, arrives j <= end_s)."""
    from_stop, to_stop, seconds = [], [], []
    for stops, arrivals, departures in trips:
        first = np.searchsorted(departures, start_s)              # departures are non-decreasing along a trip
        last = np.searchsorted(arrivals, end_s, side="right")     # stops < last arrive by end_s
        if last - first < 2:
            continue
        i, j = np.triu_indices(last - first, k=1)
        from_stop.append(stops[first + i])
        to_stop.append(stops[first + j])
        seconds.append(arrivals[first + j] - departures[first + i])
    if not seconds:                                               # no service in the window
        return pd.DataFrame({"i": np.empty(0, np.int64), "j": np.empty(0, np.int64), "s": np.empty(0, np.int64)})
    rides_df = pd.DataFrame({"i": np.concatenate(from_stop), "j": np.concatenate(to_stop), "s": np.concatenate(seconds)})
    return rides_df.groupby(["i", "j"], as_index=False).s.min()


def reverse_graph(walk, rides_df, stop_vertex, n_vertices, transfer_charge_s):
    """CSR of the reversed two-layer graph (row = forward target), plus one empty last row for the venue super node."""
    source, target, seconds = walk
    linked = (stop_vertex[rides_df.i.to_numpy()] >= 0) & (stop_vertex[rides_df.j.to_numpy()] >= 0)
    vi, vj = stop_vertex[rides_df.i.to_numpy()[linked]], stop_vertex[rides_df.j.to_numpy()[linked]]
    ride_s = rides_df.s.to_numpy()[linked].astype(float)
    n = n_vertices
    forward_from = np.concatenate([source, source + n, vi, vi + n])
    forward_to = np.concatenate([target, target + n, vj + n, vj + n])
    weight = np.concatenate([seconds, seconds, ride_s, ride_s + transfer_charge_s])
    frame = pd.DataFrame({"r": forward_to, "c": forward_from, "w": np.maximum(weight, ZERO_WEIGHT_S)})
    frame = frame.groupby(["r", "c"], as_index=False).w.min()    # csr_matrix would sum duplicates
    size = LAYERS * n + 1
    return csr_matrix((frame.w.to_numpy(), (frame.r.to_numpy(), frame.c.to_numpy())), shape=(size, size))


def with_super_sources(graph, targets, offsets):
    """The graph with the super node's (last row) edges set to targets / offsets (seconds)."""
    indptr = graph.indptr.copy()
    indptr[-1] += len(targets)
    return csr_matrix((np.concatenate([graph.data, np.maximum(offsets, ZERO_WEIGHT_S)]),
                       np.concatenate([graph.indices, targets]), indptr), shape=graph.shape)


def splits(street_layer, lats, lons, jpype, radius_m):
    """R5's findSplit (WALK) per point: edge, vertex0, vertex1, along-edge metres to each (NaN if unlinked)."""
    walk_mode = jpype.JClass("com.conveyal.r5.profile.StreetMode").WALK
    out = np.full((len(lats), len(SPLIT_COLUMNS)), np.nan)
    for k, (lat, lon) in enumerate(zip(lats, lons)):
        split = street_layer.findSplit(float(lat), float(lon), float(radius_m), walk_mode)
        if split is not None:
            out[k] = (split.edge, split.vertex0, split.vertex1, split.distance0_mm / MM_PER_M,
                      split.distance1_mm / MM_PER_M)
    return pd.DataFrame(out, columns=SPLIT_COLUMNS)


class HexSplits:
    """The origin hexes' splits, arranged for venue_oracle."""

    def __init__(self, split_df, from_pair):
        self.split_df = split_df
        self.is_linked = split_df.edge.notna().to_numpy()
        self.v0 = np.where(self.is_linked, split_df.v0, 0).astype(np.int64)
        self.v1 = np.where(self.is_linked, split_df.v1, 0).astype(np.int64)
        self.pair = np.where(self.is_linked, split_df.edge, -2).astype(np.int64) >> 1
        # position along the pair's forward direction, for points on the same edge pair as the venue
        self.pos = np.where(self.v0 == from_pair[np.maximum(self.pair, 0)], split_df.d0_m, split_df.d1_m)
        self.d0_m, self.d1_m = split_df.d0_m.to_numpy(), split_df.d1_m.to_numpy()


def venue_oracle(graph, n_vertices, from_pair, hexes, venue_split, walk_speed_kmh, limit_s):
    """Oracle seconds venue <- every hex in hexes (inf if unlinked or past limit_s)."""
    speed_mps = walk_speed_kmh / KMH_PER_MPS
    super_node = graph.shape[0] - 1
    v0, v1 = int(venue_split.v0), int(venue_split.v1)
    targets = np.array([v0, v1, v0 + n_vertices, v1 + n_vertices])
    offsets = np.array([venue_split.d0_m, venue_split.d1_m, venue_split.d0_m, venue_split.d1_m]) / speed_mps
    dist = dijkstra(with_super_sources(graph, targets, offsets), directed=True, indices=super_node, limit=limit_s)
    oracle_s = np.minimum(dist[hexes.v0] + hexes.d0_m / speed_mps, dist[hexes.v1] + hexes.d1_m / speed_mps)
    venue_pair = int(venue_split.edge) >> 1
    venue_pos = venue_split.d0_m if v0 == from_pair[venue_pair] else venue_split.d1_m
    same_edge = hexes.pair == venue_pair
    oracle_s = np.where(same_edge, np.minimum(oracle_s, np.abs(hexes.pos - venue_pos) / speed_mps), oracle_s)
    return np.where(hexes.is_linked, oracle_s, np.inf)
