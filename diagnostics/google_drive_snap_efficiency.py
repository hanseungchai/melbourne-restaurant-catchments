"""Does Google pick its start/end road for route efficiency? (DESIGN.md Q12, exploratory)

Claim tested (user's idea, 2026-10-10): where Google's start (end) road differs from the requested
point's nearest road, Google picked the road that makes the route faster, by some weighting not known
to us. The alternative is Q12's map-inventory mismatch: Google snaps to the nearest road in its own map,
which carries no preference for route time. Where it matters: DESIGN.md Q12 explains the ~18% of ends
on a different road as a map-inventory mismatch, and config.CANDIDATE_TIE_WINDOW_M (1 m) lets routing pick
the cheaper of two candidates only when they are nearly tied. If Google trades distance for route time,
a wider window would model it better.

Method (no API calls): the frozen 2026-09-30 Routes responses give Google's snapped start and end points
for 4,000 pairs. On the pipeline's timed graph (SPEED_VARIANT, edge weight time_raw_s, no penalties),
the pipeline position is the requested point projected onto its nearest segment (motorways excluded),
Google's position is Google's point matched to a segment as in google_drive_snap_time_cost.py. Only ends
where the two positions are on different links are judged, one end at a time, the other end on
Google's road:
- origin differs: shortest path from each start position to Google's destination position. The two
  paths share a tail; each side's time is from its start to the node where the paths merge.
- destination differs: shortest path from Google's origin position to each end position. The paths
  share a head; each side's time is from the node where they part to its end.
Only that differing part is compared, never the whole trip. diff_s = pipeline part - Google part:
positive means Google's road is faster. If the paths never merge (different first or last node),
the whole times are compared and the end is flagged.

Pre-registered (fixed before the first run, 2026-10-10): over judged ends with |diff_s| > TIE_TOL_S,
let share = fraction where Google's part is faster. Efficiency is SUPPORTED if share >= SUPPORT_SHARE
and the 95% Wilson interval's lower bound is above 0.5; NOT SUPPORTED if share <= NULL_MAX_SHARE (no
better than the inventory-mismatch null of about 0.5); MIXED otherwise.
Caveat: times are the model's, not Google's; Google's own speeds may rank the two parts differently.

Conclusion (run 2026-10-10, 1,451 differing ends, all judged; 5 never merged): efficiency SUPPORTED
by the pre-registered rule. Google's road gives the faster differing part in 79.9% of non-tied ends
(748 of 936, 95% CI 77.2-82.4%; origin 77.3%, destination 81.8%); 515 ends tie within 1 s. Median
diff +0.8 s (origin), +1.7 s (destination): the parts are short, so the gain per end is seconds.
Confound, read before using this: the strongest group is nearest = service road, Google = street
(90.3%, 411 decided). A service road is often a dead end feeding the street, so the street is faster
whatever the reason Google is on it, and a road missing from Google's map would give the same result.
The clean group, street -> street (both public, both likely in Google's map), is 70.0% (177 of 253,
CI 64.0-75.3%): above the 50% null, below the 75% bar. Ends where Google's road is under 2 m farther
than the nearest: 72.2%. So Google does show a preference for the faster road beyond the inventory
mismatch, weaker than the headline share; the two explanations overlap and this test cannot split
the service-road cases.

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
"""

import datetime
import math
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

DIAGNOSTIC_NAME = "google_drive_snap_efficiency"
RUN_DATE = datetime.date.today().strftime("%Y%m%d")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTES_DIR = PROJECT_ROOT / "frozen_inputs" / "routes_drive_eta_20260930"
DRAWS_PATH = ROUTES_DIR / "od_sample_pairs.csv"
ETA_PATH = ROUTES_DIR / "od_sample_pairs_google_estimates.csv"
SPEED_VARIANT = "blind"
SPEED_GRAPHS_SUBJECT_DIR = PROJECT_ROOT / "outputs" / "speed_graphs" / "-37.76870_144.97196"
TIMED_GRAPH_PATH = (SPEED_GRAPHS_SUBJECT_DIR / f"split_drive_edges_timed_{SPEED_VARIANT}_res2021_wrk2021_"
                    f"ven20260925_-37.76870_144.97196.pkl")
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
PREFIX = f"{DIAGNOSTIC_NAME}_{RUN_DATE}"
ENDS_DATA_GLOB = f"{DIAGNOSTIC_NAME}_*_ends.csv"          # saved routing results, reused if present
ENDS_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_ends.csv"
LOG_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_log.txt"
FIGURE_PATH = DIAGNOSTIC_IMG_DIR / f"{PREFIX}_diff.png"

GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:7855"                        # GDA2020 / MGA 55, metres
HTTP_OK = 200
POLYLINE_PRECISION = 1e5                        # Google encoded polyline: 5 decimal places
NODE_LON_ATTR, NODE_LAT_ATTR = "x", "y"
EDGE_TIME_ATTR = "time_raw_s"
EDGE_HIGHWAY_ATTR = "highway"
EXCLUDED_HIGHWAY_TYPES = {"motorway", "motorway_link"}   # as config.CANDIDATE_EXCLUDED_HIGHWAY_TYPES
SERVICE_HIGHWAY = "service"
MIN_EDGE_TIME_S = 1e-6                          # scipy drops zero weights; none expected, guard anyway

SEARCH_RADIUS_M = 300                           # nearest segment to the requested point within this
UNMATCHED_M = 15                                # as google_drive_snap_side.py
AMBIGUOUS_M = 3
POLYLINE_PROBE_M = (5, 10, 15, 20)
POLYLINE_SEPARATION_M = 2
PROBE_RADIUS_M = 60
SEARCH_LIMIT_FACTOR = 3                         # shortest-path search stops at this x Google's duration
N_WORKERS = 8
NO_PREDECESSOR = -9999                          # scipy's predecessor value for "none"

TIE_TOL_S = 1.0                                 # |diff_s| at or below this counts as a tie, not judged
SUPPORT_SHARE = 0.75                            # pre-registered: SUPPORTED at or above this share
NULL_MAX_SHARE = 0.60                           # pre-registered: NOT SUPPORTED at or below this share
WILSON_Z = 1.96
EXTRA_GAP_BANDS_M = (0, 2, 5, 10, np.inf)       # how much farther Google's point is from the request
DIFF_CLIP_S = 60                                # figure: diffs clipped to +-this
QUANTILES = (0.1, 0.25, 0.5, 0.75, 0.9)

ENDS = ("origin", "dest")


class Tee:
    """Print to the console and keep every line for the run log."""

    def __init__(self):
        self.stdout = sys.stdout
        self.lines = []

    def write(self, text):
        self.stdout.write(text)
        self.lines.append(text)

    def flush(self):
        self.stdout.flush()


def decode_polyline(encoded):
    """Google encoded polyline -> array of (lat, lon)."""
    coords, index, lat, lon = [], 0, 0, 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift, result = 0, 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lat / POLYLINE_PRECISION, lon / POLYLINE_PRECISION))
    return np.array(coords)


def load_pairs(to_metric):
    """One row per pair: requested and Google points for both ends (metres), the route polyline and
    Google's durations."""
    draws_df = pd.read_csv(DRAWS_PATH)
    eta_df = pd.read_csv(ETA_PATH)
    pairs_df = draws_df.merge(eta_df, on="draw_no", how="inner", validate="one_to_one")
    pairs_df = pairs_df[(pairs_df.http_status == HTTP_OK) & pairs_df.g_o_lat.notna()
                        & pairs_df.g_d_lat.notna() & pairs_df.polyline.notna()].reset_index(drop=True)
    print(f"pairs: {len(draws_df):,} draws, {len(pairs_df):,} with Google points and a polyline")
    columns = dict(origin_req=("origin_lat", "origin_lon"), dest_req=("dest_lat", "dest_lon"),
                   origin_g=("g_o_lat", "g_o_lon"), dest_g=("g_d_lat", "g_d_lon"))
    for name, (lat_col, lon_col) in columns.items():
        pairs_df[f"{name}_x"], pairs_df[f"{name}_y"] = to_metric.transform(pairs_df[lon_col].to_numpy(),
                                                                           pairs_df[lat_col].to_numpy())
    route_xy = []
    for encoded in pairs_df.polyline:
        lat_lon = decode_polyline(encoded)
        x, y = to_metric.transform(lat_lon[:, 1], lat_lon[:, 0])
        route_xy.append(np.column_stack([x, y]))
    pairs_df["route_xy"] = route_xy
    pairs_df["google_static_s"] = pairs_df.static_duration_sec.fillna(pairs_df.google_drive_duration_sec)
    return pairs_df


def link_finder(undirected):
    """Maps a segment (a, b) to its link: the chain of segments through degree-2 nodes, named by the
    chain's two end nodes."""
    cache = {}

    def walk(prev, node):
        while undirected.degree(node) == 2:
            nxt = next(n for n in undirected.neighbors(node) if n != prev)
            if (node, nxt) in cache or nxt == prev:
                break
            prev, node = node, nxt
        return node

    def find(segment):
        if segment in cache:
            return cache[segment]
        a, b = segment
        link = tuple(sorted((walk(b, a), walk(a, b))))
        cache[segment] = link
        return link

    return find


def load_graph(to_metric):
    """The timed graph as a CSR matrix plus one row per two-way-merged segment: node indices, the time
    each way (nan if one-way), highway, link and geometry (metres)."""
    print(f"loading {TIMED_GRAPH_PATH.name} ...")
    with open(TIMED_GRAPH_PATH, "rb") as f:
        graph = pickle.load(f)
    print(f"  {graph.number_of_nodes():,} nodes, {graph.number_of_edges():,} edges, "
          f"component {graph.graph.get('component')}, variant {graph.graph.get('variant')}")
    nodes = list(graph.nodes)
    index = {node: i for i, node in enumerate(nodes)}
    u, v, time_s = [], [], []
    for a, b, data in graph.edges(data=True):
        u.append(index[a])
        v.append(index[b])
        time_s.append(data[EDGE_TIME_ATTR])
    time_s = np.maximum(np.array(time_s), MIN_EDGE_TIME_S)
    adjacency = csr_matrix((time_s, (u, v)), shape=(len(nodes), len(nodes)))

    find_link = link_finder(graph.to_undirected(as_view=True))
    seen, rows = set(), []
    for a, b, data in graph.edges(data=True):
        key = (min(a, b), max(a, b), )
        if key in seen:
            continue
        seen.add(key)
        lo, hi = key
        time_lo_hi = graph.edges[lo, hi][EDGE_TIME_ATTR] if graph.has_edge(lo, hi) else np.nan
        time_hi_lo = graph.edges[hi, lo][EDGE_TIME_ATTR] if graph.has_edge(hi, lo) else np.nan
        highway = data.get(EDGE_HIGHWAY_ATTR)
        highway = ",".join(map(str, highway)) if isinstance(highway, list) else highway
        link = find_link(key)
        rows.append((index[lo], index[hi], time_lo_hi, time_hi_lo, highway, f"{link[0]}_{link[1]}"))
    segments_df = pd.DataFrame(rows, columns=["a", "b", "time_ab_s", "time_ba_s", "highway", "link"])
    x = np.array([graph.nodes[node][NODE_LON_ATTR] for node in nodes])
    y = np.array([graph.nodes[node][NODE_LAT_ATTR] for node in nodes])
    del graph
    mx, my = to_metric.transform(x, y)
    a, b = segments_df.a.to_numpy(), segments_df.b.to_numpy()
    coords = np.stack([np.column_stack([mx[a], my[a]]), np.column_stack([mx[b], my[b]])], axis=1)
    segments_df["geometry"] = shapely.linestrings(coords)
    segments_df["is_candidate"] = ~segments_df.highway.isin(EXCLUDED_HIGHWAY_TYPES)
    print(f"  segments: {len(segments_df):,}, links: {segments_df.link.nunique():,}")
    return adjacency, segments_df


def point_along(route_xy, distance_m):
    """The point distance_m along the route from its first vertex, or None if the route is shorter."""
    along = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(route_xy, axis=0).T))])
    if along[-1] < distance_m:
        return None
    return np.array([np.interp(distance_m, along, route_xy[:, 0]), np.interp(distance_m, along, route_xy[:, 1])])


def nearest_segment(point, tree, geoms, mask, radius_m):
    """Index of the nearest segment to point within radius_m among segments where mask is True."""
    seg_ix = tree.query(point, predicate="dwithin", distance=radius_m)
    seg_ix = seg_ix[mask[seg_ix]]
    if len(seg_ix) == 0:
        return None
    return seg_ix[np.argmin(shapely.distance(point, geoms[seg_ix]))]


def google_segment(point, route_xy, tree, geoms, links):
    """(segment index, status) for Google's point: the nearest segment, with the polyline deciding
    between links within AMBIGUOUS_M of each other."""
    seg_ix = tree.query(point, predicate="dwithin", distance=UNMATCHED_M + AMBIGUOUS_M)
    if len(seg_ix) == 0:
        return None, "unmatched"
    dist_m = shapely.distance(point, geoms[seg_ix])
    order = np.argsort(dist_m, kind="stable")
    seg_ix, dist_m = seg_ix[order], dist_m[order]
    if dist_m[0] > UNMATCHED_M:
        return None, "unmatched"
    contender_links = pd.unique(links[seg_ix[dist_m <= dist_m[0] + AMBIGUOUS_M]])
    if len(contender_links) == 1:
        return seg_ix[0], "matched"
    probes = [point_along(route_xy, d) for d in POLYLINE_PROBE_M]
    if any(p is None for p in probes):
        return None, "ambiguous"
    probe_points = shapely.points(np.array(probes))
    means = []
    for link in contender_links:
        link_ix = seg_ix[links[seg_ix] == link]
        geom = shapely.union_all(geoms[link_ix])
        means.append(np.minimum(shapely.distance(probe_points, geom), PROBE_RADIUS_M).mean())
    order = np.argsort(means, kind="stable")
    if means[order[1]] - means[order[0]] < POLYLINE_SEPARATION_M:
        return None, "ambiguous"
    best_link = contender_links[order[0]]
    link_ix = seg_ix[links[seg_ix] == best_link]
    return link_ix[0], "matched"           # seg_ix is nearest first


def position(point, seg, segments_df, geoms):
    """Where a trip starts or ends on segment seg: (entries, exits). Entries: (node, seconds from the
    point to the node). Exits: (node, seconds from the node to the point). Along-edge time is
    proportional to length."""
    fraction = shapely.line_locate_point(geoms[seg], point, normalized=True)
    row = segments_df.iloc[seg]
    entries, exits = [], []
    if not np.isnan(row.time_ab_s):                # a -> b exists
        entries.append((int(row.b), (1 - fraction) * row.time_ab_s))
        exits.append((int(row.a), fraction * row.time_ab_s))
    if not np.isnan(row.time_ba_s):                # b -> a exists
        entries.append((int(row.a), fraction * row.time_ba_s))
        exits.append((int(row.b), (1 - fraction) * row.time_ba_s))
    return entries, exits


def snapped_gap_m(point, seg, geoms):
    """Distance from a point to where it lands on segment seg."""
    return float(shapely.distance(point, geoms[seg]))


_ADJACENCY = None


def init_worker(adjacency):
    global _ADJACENCY
    _ADJACENCY = adjacency


def walk_back(predecessors, row, target):
    """Node path from the search source of predecessors[row] to target."""
    path = [target]
    while predecessors[row, path[-1]] != NO_PREDECESSOR:
        path.append(int(predecessors[row, path[-1]]))
    return path[::-1]


def best_route(dist, row_of, entries, exits):
    """(total s, entry offset s, entry node, exit node, exit offset s) of the cheapest combination."""
    options = [(off_o + dist[row_of[node_o], node_d] + off_d, off_o, node_o, node_d, off_d)
               for node_o, off_o in entries for node_d, off_d in exits]
    return min(options)


def end_task(task):
    """Times of the differing part for one end. task: (end, starts, ends, limit_s), where starts and
    ends hold the positions; the end being judged has a "p" and a "g" side, the other end only "g"."""
    end, starts, ends, limit_s = task
    sources = sorted({node for side in starts.values() for node, _ in side})
    dist, predecessors = dijkstra(_ADJACENCY, indices=sources, limit=limit_s, return_predecessors=True)
    row_of = {node: i for i, node in enumerate(sources)}
    routes = {}
    for side in ("p", "g"):
        o_side, d_side = (side, "g") if end == "origin" else ("g", side)
        total_s, off_o, node_o, node_d, off_d = best_route(dist, row_of, starts[o_side], ends[d_side])
        if not np.isfinite(total_s):
            return dict(status="unreached")
        path = walk_back(predecessors, row_of[node_o], node_d)
        routes[side] = dict(total_s=total_s, off_o=off_o, off_d=off_d, node_o=node_o, path=path)
    p_route, g_route = routes["p"], routes["g"]
    out = dict(status="judged", total_p_s=p_route["total_s"], total_g_s=g_route["total_s"])
    if end == "origin":
        # shared tail: walk both paths back from the end while they agree
        p_path, g_path = p_route["path"], g_route["path"]
        n_shared = 0
        while (n_shared < min(len(p_path), len(g_path))
               and p_path[-1 - n_shared] == g_path[-1 - n_shared]):
            n_shared += 1
        if n_shared == 0:
            out.update(part_p_s=p_route["total_s"], part_g_s=g_route["total_s"], is_merged=False)
        else:
            merge = p_path[-n_shared]
            out.update(part_p_s=p_route["off_o"] + dist[row_of[p_route["node_o"]], merge],
                       part_g_s=g_route["off_o"] + dist[row_of[g_route["node_o"]], merge],
                       is_merged=True)
    else:
        # shared head: same start node, walk forward while the paths agree
        p_path, g_path = p_route["path"], g_route["path"]
        n_shared = 0
        while (n_shared < min(len(p_path), len(g_path))
               and p_path[n_shared] == g_path[n_shared]):
            n_shared += 1
        if n_shared == 0:
            out.update(part_p_s=p_route["total_s"], part_g_s=g_route["total_s"], is_merged=False)
        else:
            split = p_path[n_shared - 1]
            head_s = dist[row_of[p_route["node_o"]], split]
            out.update(part_p_s=p_route["total_s"] - p_route["off_o"] - head_s,
                       part_g_s=g_route["total_s"] - g_route["off_o"] - head_s,
                       is_merged=True)
    out["n_shared_nodes"] = n_shared
    return out


def build_tasks(pairs_df, segments_df):
    """One task per end whose pipeline and Google positions lie on different links."""
    geoms = segments_df.geometry.to_numpy()
    links = segments_df.link.to_numpy()
    is_candidate = segments_df.is_candidate.to_numpy()
    highways = segments_df.highway.to_numpy()
    tree = shapely.STRtree(geoms)
    rows, tasks, n_status = [], [], {}
    for pair in pairs_df.itertuples(index=False):
        positions, info, is_ok = {}, {}, True
        for end in ENDS:
            req = shapely.points(getattr(pair, f"{end}_req_x"), getattr(pair, f"{end}_req_y"))
            google = shapely.points(getattr(pair, f"{end}_g_x"), getattr(pair, f"{end}_g_y"))
            route_xy = pair.route_xy if end == "origin" else pair.route_xy[::-1]
            p_seg = nearest_segment(req, tree, geoms, is_candidate, SEARCH_RADIUS_M)
            g_seg, status = google_segment(google, route_xy, tree, geoms, links)
            status = status if p_seg is not None else "no_pipeline_road"
            n_status[(end, status)] = n_status.get((end, status), 0) + 1
            if p_seg is None or g_seg is None:
                is_ok = False
                continue
            pick = 0 if end == "origin" else 1     # entries for the origin, exits for the destination
            positions[end] = dict(p=position(req, p_seg, segments_df, geoms)[pick],
                                  g=position(google, g_seg, segments_df, geoms)[pick])
            p_gap_m = snapped_gap_m(req, p_seg, geoms)
            g_gap_m = snapped_gap_m(req, g_seg, geoms)
            info[end] = dict(is_same_link=links[p_seg] == links[g_seg], pipeline_highway=highways[p_seg],
                             google_highway=highways[g_seg], pipeline_gap_m=p_gap_m, google_gap_m=g_gap_m,
                             extra_gap_m=g_gap_m - p_gap_m)
        if not is_ok:
            continue
        for end in ENDS:
            if info[end]["is_same_link"]:
                continue
            starts = positions["origin"] if end == "origin" else {"g": positions["origin"]["g"]}
            ends = positions["dest"] if end == "dest" else {"g": positions["dest"]["g"]}
            rows.append(dict(draw_no=pair.draw_no, end=end, google_static_s=pair.google_static_s,
                             **{k: v for k, v in info[end].items() if k != "is_same_link"}))
            tasks.append((end, starts, ends, SEARCH_LIMIT_FACTOR * pair.google_static_s))
    for end in ENDS:
        print(f"{end} status: " + ", ".join(f"{s} {n:,}" for (e, s), n in sorted(n_status.items()) if e == end))
    return pd.DataFrame(rows), tasks


def wilson(k, n):
    """95% Wilson score interval for k successes out of n."""
    if n == 0:
        return math.nan, math.nan
    p = k / n
    centre = (p + WILSON_Z ** 2 / (2 * n)) / (1 + WILSON_Z ** 2 / n)
    half = WILSON_Z * math.sqrt(p * (1 - p) / n + WILSON_Z ** 2 / (4 * n ** 2)) / (1 + WILSON_Z ** 2 / n)
    return centre - half, centre + half


def share_line(sub):
    """Google-faster share among non-tied ends, with its interval."""
    decided = sub[sub.diff_s.abs() > TIE_TOL_S]
    k, n = int((decided.diff_s > 0).sum()), len(decided)
    lo, hi = wilson(k, n)
    share = k / n if n else math.nan
    return (f"{len(sub):,} ends, ties {len(sub) - n:,}; Google faster {k:,} of {n:,} = {share:.1%} "
            f"(95% CI {lo:.1%}-{hi:.1%})"), share, lo


def report(ends_df):
    judged_df = ends_df[ends_df.status == "judged"].copy()
    print(f"\nEnds on different links: {len(ends_df):,}; unreached {int((ends_df.status == 'unreached').sum()):,}; "
          f"judged {len(judged_df):,} (paths never merged: {int((~judged_df.is_merged.astype(bool)).sum()):,}, "
          f"whole times used).")
    judged_df["diff_s"] = judged_df.part_p_s - judged_df.part_g_s
    judged_df["diff_rel"] = judged_df.diff_s / judged_df[["part_p_s", "part_g_s"]].max(axis=1)
    print(f"diff_s = pipeline part - Google part (positive: Google's road faster). Ties: |diff_s| <= {TIE_TOL_S:g} s.")

    print("\nDiffering part, model seconds:")
    for end in ENDS:
        sub = judged_df[judged_df.end == end]
        print(f"  {end}: pipeline part " + ", ".join(f"p{int(q * 100)} {sub.part_p_s.quantile(q):.0f}" for q in QUANTILES)
              + "; Google part " + ", ".join(f"p{int(q * 100)} {sub.part_g_s.quantile(q):.0f}" for q in QUANTILES))
        print(f"     diff_s " + ", ".join(f"p{int(q * 100)} {sub.diff_s.quantile(q):+.1f}" for q in QUANTILES)
              + "; diff / longer part " + ", ".join(f"p{int(q * 100)} {sub.diff_rel.quantile(q):+.2f}" for q in QUANTILES))

    print("\nShare where Google's road is faster:")
    line, share, lower = share_line(judged_df)
    print(f"  all:    {line}")
    for end in ENDS:
        print(f"  {end}: {share_line(judged_df[judged_df.end == end])[0]}")

    print("\nBy road class (pipeline's nearest -> Google's):")
    judged_df["classes"] = (np.where(judged_df.pipeline_highway.eq(SERVICE_HIGHWAY), "service", "street") + " -> "
                            + np.where(judged_df.google_highway.eq(SERVICE_HIGHWAY), "service", "street"))
    for name, sub in judged_df.groupby("classes"):
        print(f"  {name:20s} {share_line(sub)[0]}")

    print("\nBy how much farther Google's road is from the requested point (m):")
    judged_df["extra_gap_band"] = pd.cut(judged_df.extra_gap_m, EXTRA_GAP_BANDS_M, right=False)
    for band, sub in judged_df.groupby("extra_gap_band", observed=True):
        print(f"  {str(band):14s} {share_line(sub)[0]}")

    if share >= SUPPORT_SHARE and lower > 0.5:
        verdict = "SUPPORTED"
    elif share <= NULL_MAX_SHARE:
        verdict = "NOT SUPPORTED"
    else:
        verdict = "MIXED"
    print(f"\nCriterion: share {share:.1%} (SUPPORTED if >= {SUPPORT_SHARE:.0%} with CI lower bound > 50%; "
          f"NOT SUPPORTED if <= {NULL_MAX_SHARE:.0%}) -> efficiency {verdict}")
    return judged_df


def plot(judged_df):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    bins = np.arange(-DIFF_CLIP_S, DIFF_CLIP_S + 2, 2)
    for ax, end in zip(axes, ENDS):
        sub = judged_df[judged_df.end == end]
        ax.hist(sub.diff_s.clip(-DIFF_CLIP_S, DIFF_CLIP_S), bins=bins, color="0.55")
        ax.axvline(0, color="black", lw=0.8)
        decided = sub[sub.diff_s.abs() > TIE_TOL_S]
        ax.set_title(f"{end}: {len(sub):,} ends on a different road; Google faster in "
                     f"{(decided.diff_s > 0).mean():.0%} of non-ties", fontsize=10)
        ax.set_xlabel(f"pipeline part - Google part, model s (clipped to +-{DIFF_CLIP_S}); right = Google faster")
    axes[0].set_ylabel("ends")
    fig.suptitle("Google's start/end road vs the nearest road: time of the differing part of the route")
    fig.tight_layout()
    fig.savefig(FIGURE_PATH, dpi=150)
    plt.close(fig)
    print(f"Saved {FIGURE_PATH}")


def main():
    tee = Tee()
    sys.stdout = tee
    try:
        print(f"{DIAGNOSTIC_NAME}, run {RUN_DATE}. Reads frozen Routes responses and the timed graph; no API calls.")
        saved = sorted(DIAGNOSTIC_DATA_DIR.glob(ENDS_DATA_GLOB))
        if saved:
            ends_path = saved[-1]
            print(f"Reusing saved routing results {ends_path.name} (dated {ends_path.name.split('_')[-2]}).")
            ends_df = pd.read_csv(ends_path)
        else:
            to_metric = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
            pairs_df = load_pairs(to_metric)
            adjacency, segments_df = load_graph(to_metric)
            ends_df, tasks = build_tasks(pairs_df, segments_df)
            del segments_df
            print(f"routing {len(tasks):,} differing ends on {N_WORKERS} workers ...")
            with Pool(N_WORKERS, initializer=init_worker, initargs=(adjacency,)) as pool:
                results = pool.map(end_task, tasks, chunksize=8)
            ends_df = pd.concat([ends_df, pd.DataFrame(results)], axis=1)
            ends_df.to_csv(ENDS_PATH, index=False)
            print(f"Saved {ENDS_PATH}")
        judged_df = report(ends_df)
        plot(judged_df)
    finally:
        sys.stdout = tee.stdout
        LOG_PATH.write_text("".join(tee.lines), encoding="utf-8")
        print(f"Saved {LOG_PATH}")


if __name__ == "__main__":
    main()
