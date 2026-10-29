"""Does starting (ending) on a different road than Google change the trip time? (DESIGN.md Q12)

Claim: the map-inventory mismatch (DESIGN.md Q12: Google's start/end road differs from the pipeline's
nearest road for ~18% of endpoints) changes modelled trip times only a little, small next to the model's
own error against Google. Where the pipeline relies on it: routing starts and ends every drive trip on the
nearest candidate road (routing_graph, config.CANDIDATE_TIE_WINDOW_M, also routing's tie rule); Q12 states the
mismatch as a limitation, not something to fix.

Method (no API calls): the frozen 2026-09-30 Routes responses give Google's snapped start and end points
for 4,000 pairs (origin = hex centroid, destination = venue). Routing is on the pipeline's timed graph
(speed variant SPEED_VARIANT, edge weight time_raw_s, no signal or turn penalties):
1. Pipeline position: the requested point projected onto its nearest segment, motorways excluded (the
   candidate rule). The pipeline then rounds to a node at most ~25 m along that road; ignored here.
2. Google position: Google's point projected onto the graph segment nearest it, within UNMATCHED_M. When
   another link is within AMBIGUOUS_M, the polyline's first (last) POLYLINE_PROBE_M decide by
   POLYLINE_SEPARATION_M, as in google_drive_snap_side.py; otherwise the pair is skipped.
3. Per pair, four shortest times, starting and ending part-way along an edge: pipeline->pipeline (what
   the pipeline models), Google->Google (the same model on Google's roads), and one end swapped each way.
   Delta = pipeline->pipeline minus Google->Google; the origin's share is pipeline->Google minus
   Google->Google, the destination's Google->pipeline minus Google->Google.
4. Context: the model's own error, |pipeline->pipeline / Google's static duration - 1|.
Pre-registered (fixed before the first run, 2026-10-10): the claim holds if, over all judged pairs, the
median |delta| is at most HOLD_MEDIAN_REL of trip time and the 90th percentile of |delta| is below the
median model error.

Conclusion (run 2026-10-10, 3,137 judged pairs): the claim HOLDS. Median |delta| 0 s (0.0% of trip), p90
13 s (1.6%), p95 26 s (3.6%); 91.7% of pairs within 2%. Where at least one end is on a different road
(1,264 pairs): median 4 s, p90 32 s (4.6%). The model's own error is far larger: 36.9% median raw (blind
times run fast), 13.2% after one scale factor. Rule p (nearest road) and Google's own roads give the same
accuracy against Google (scaled median error 13.2% vs 13.2%, sd log ratio 0.215 vs 0.214). Exploratory:
excluding service roads (rule n) makes snapping worse (both ends on Google's road 40.6% vs 59.7%) and
trip times slightly worse (sd log ratio 0.222).

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
"""

import datetime
import math
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

DIAGNOSTIC_NAME = "google_drive_snap_time_cost"
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
PREFIX = f"{DIAGNOSTIC_NAME}_{RUN_DATE}"
PAIRS_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_pairs.csv"
LOG_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_log.txt"

GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:7855"                        # GDA2020 / MGA 55, metres
HTTP_OK = 200
POLYLINE_PRECISION = 1e5                        # Google encoded polyline: 5 decimal places
NODE_LON_ATTR, NODE_LAT_ATTR = "x", "y"
EDGE_TIME_ATTR = "time_raw_s"
EDGE_HIGHWAY_ATTR = "highway"
EXCLUDED_HIGHWAY_TYPES = {"motorway", "motorway_link"}   # as config.CANDIDATE_EXCLUDED_HIGHWAY_TYPES
SERVICE_HIGHWAY = "service"                     # exploratory rule n: service roads also excluded
MIN_EDGE_TIME_S = 1e-6                          # scipy drops zero weights; none expected, guard anyway

SEARCH_RADIUS_M = 300                           # nearest segment to the requested point within this
UNMATCHED_M = 15                                # as google_drive_snap_side.py
AMBIGUOUS_M = 3
POLYLINE_PROBE_M = (5, 10, 15, 20)
POLYLINE_SEPARATION_M = 2
PROBE_RADIUS_M = 60
SEARCH_LIMIT_FACTOR = 3                         # shortest-path search stops at this x Google's duration
N_WORKERS = 8
DELTA_THRESHOLDS_S = (5, 15, 30, 60)
REL_THRESHOLDS = (0.02, 0.05, 0.10)
QUANTILES = (0.5, 0.75, 0.9, 0.95)
HOLD_MEDIAN_REL = 0.02                          # pre-registered: median |delta| / trip time at most this

ENDS = ("origin", "dest")
VARIANTS = ("pp", "gg", "pg", "gp", "nn")       # origin side, destination side: p pipeline, g Google,
                                                # n pipeline without service roads (exploratory)


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
    segments_df["is_candidate_no_service"] = segments_df.is_candidate & (segments_df.highway != SERVICE_HIGHWAY)
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
        entries.append((row.b, (1 - fraction) * row.time_ab_s))
        exits.append((row.a, fraction * row.time_ab_s))
    if not np.isnan(row.time_ba_s):                # b -> a exists
        entries.append((row.a, fraction * row.time_ba_s))
        exits.append((row.b, (1 - fraction) * row.time_ba_s))
    return entries, exits


_ADJACENCY = None


def init_worker(adjacency):
    global _ADJACENCY
    _ADJACENCY = adjacency


def pair_times(task):
    """Shortest time for each (origin side, destination side) combination of one pair."""
    starts, ends, limit_s = task           # starts/ends: {"p": entries or exits, "g": ...}
    sources = sorted({node for side in starts.values() for node, _ in side})
    dist = dijkstra(_ADJACENCY, indices=sources, limit=limit_s)
    row_of = {node: i for i, node in enumerate(sources)}
    times = {}
    for o_side, entries in starts.items():
        for d_side, exits in ends.items():
            times[o_side + d_side] = min(
                (off_o + dist[row_of[node_o], node_d] + off_d
                 for node_o, off_o in entries for node_d, off_d in exits), default=np.inf)
    return times


def build_tasks(pairs_df, segments_df):
    geoms = segments_df.geometry.to_numpy()
    links = segments_df.link.to_numpy()
    is_candidate = segments_df.is_candidate.to_numpy()
    is_candidate_no_service = segments_df.is_candidate_no_service.to_numpy()
    highways = segments_df.highway.to_numpy()
    tree = shapely.STRtree(geoms)
    rows, tasks = [], []
    for pair in pairs_df.itertuples(index=False):
        row = dict(draw_no=pair.draw_no, google_static_s=pair.google_static_s)
        starts, ends, is_ok = {}, {}, True
        for end in ENDS:
            req = shapely.points(getattr(pair, f"{end}_req_x"), getattr(pair, f"{end}_req_y"))
            google = shapely.points(getattr(pair, f"{end}_g_x"), getattr(pair, f"{end}_g_y"))
            route_xy = pair.route_xy if end == "origin" else pair.route_xy[::-1]
            p_seg = nearest_segment(req, tree, geoms, is_candidate, SEARCH_RADIUS_M)
            n_seg = nearest_segment(req, tree, geoms, is_candidate_no_service, SEARCH_RADIUS_M)
            g_seg, status = google_segment(google, route_xy, tree, geoms, links)
            row[f"{end}_status"] = status if p_seg is not None and n_seg is not None else "no_pipeline_road"
            if p_seg is None or n_seg is None or g_seg is None:
                is_ok = False
                continue
            row[f"{end}_same_link"] = links[p_seg] == links[g_seg]
            row[f"{end}_pipeline_highway"] = highways[p_seg]
            row[f"{end}_google_highway"] = highways[g_seg]
            row[f"{end}_shift_m"] = shapely.distance(
                shapely.line_interpolate_point(geoms[p_seg], shapely.line_locate_point(geoms[p_seg], req)),
                shapely.line_interpolate_point(geoms[g_seg], shapely.line_locate_point(geoms[g_seg], google)))
            p_pos = position(req, p_seg, segments_df, geoms)
            g_pos = position(google, g_seg, segments_df, geoms)
            n_pos = position(req, n_seg, segments_df, geoms)
            row[f"{end}_n_same_link_as_google"] = links[n_seg] == links[g_seg]
            side = starts if end == "origin" else ends
            pick = 0 if end == "origin" else 1             # entries for the origin, exits for the destination
            side["p"], side["g"], side["n"] = p_pos[pick], g_pos[pick], n_pos[pick]
        row["is_judged"] = is_ok
        rows.append(row)
        if is_ok:
            tasks.append((starts, ends, SEARCH_LIMIT_FACTOR * pair.google_static_s))
    return pd.DataFrame(rows), tasks


def quantile_line(values, unit):
    return ", ".join(f"p{int(q * 100)} {values.quantile(q):.{0 if unit == 's' else 3}f}" for q in QUANTILES)


def report(judged_df):
    print(f"\nJudged pairs: {len(judged_df):,}. Times are the model's (variant {SPEED_VARIANT}, raw, no "
          f"penalties); delta = pipeline->pipeline - Google->Google.")
    judged_df = judged_df.assign(
        any_diff=~(judged_df.origin_same_link & judged_df.dest_same_link),
        abs_delta_s=judged_df.delta_s.abs(), abs_delta_rel=(judged_df.delta_s / judged_df.time_gg_s).abs(),
        model_error=(judged_df.time_pp_s / judged_df.google_static_s - 1).abs())
    groups = dict(all=judged_df, roads_differ=judged_df[judged_df.any_diff],
                  same_roads=judged_df[~judged_df.any_diff])
    for name, sub in groups.items():
        print(f"\n{name} ({len(sub):,} pairs):")
        print(f"  |delta| s:          {quantile_line(sub.abs_delta_s, 's')}")
        print(f"  |delta| / trip:     {quantile_line(sub.abs_delta_rel, 'rel')}")
        print(f"  signed delta s:     mean {sub.delta_s.mean():+.1f}, median {sub.delta_s.median():+.1f}")
        print("  share |delta| <= " + ", ".join(f"{t} s: {(sub.abs_delta_s <= t).mean():.1%}"
                                                for t in DELTA_THRESHOLDS_S))
        print("  share |delta|/trip <= " + ", ".join(f"{t:.0%}: {(sub.abs_delta_rel <= t).mean():.1%}"
                                                     for t in REL_THRESHOLDS))
    print(f"\nContext, model error |pipeline->pipeline / Google static - 1|: "
          f"{quantile_line(judged_df.model_error, 'rel')}")

    print("\nPer end (that end swapped, the other on Google's road), where the roads differ:")
    for end in ENDS:
        sub = judged_df[~judged_df[f"{end}_same_link"]]
        delta_s = sub[f"delta_{end}_s"]
        print(f"  {end} ({len(sub):,}): |delta| s {quantile_line(delta_s.abs(), 's')}; "
              f"signed median {delta_s.median():+.1f}")
        by_class = (sub.assign(abs_delta_s=delta_s.abs(),
                               google_service=sub[f"{end}_google_highway"].eq("service"),
                               pipeline_service=sub[f"{end}_pipeline_highway"].eq("service"))
                    .groupby(["pipeline_service", "google_service"]).abs_delta_s
                    .agg(["size", "median", lambda s: s.quantile(0.9)]).rename(columns={"<lambda_0>": "p90"}))
        print(by_class.round(1).to_string())

    print()
    print("=== Exploratory: start/end rule p (nearest road) vs n (nearest non-service road) ===")
    for rule in ("p", "n"):
        same = ((judged_df.origin_same_link & judged_df.dest_same_link) if rule == "p" else
                (judged_df.origin_n_same_link_as_google.astype(bool) & judged_df.dest_n_same_link_as_google.astype(bool)))
        time_s = judged_df[f"time_{rule}{rule}_s"]
        vs_google_road = (time_s / judged_df.time_gg_s - 1).abs()
        ratio = judged_df.google_static_s / time_s
        scaled_error = (time_s * ratio.median() / judged_df.google_static_s - 1).abs()
        log_error = np.log(time_s / judged_df.google_static_s)
        print(f"rule {rule}: both ends on Google's road {same.mean():.1%}; |time / Google-road time - 1| "
              f"{quantile_line(vs_google_road, 'rel')}")
        print(f"        vs Google's static duration, after one scale factor ({ratio.median():.3f}): "
              f"|error| {quantile_line(scaled_error, 'rel')}; sd log ratio {log_error.std():.4f}; "
              f"Spearman rho {time_s.corr(judged_df.google_static_s, method='spearman'):.4f}")
    gg_scale = (judged_df.google_static_s / judged_df.time_gg_s).median()
    gg_error = (judged_df.time_gg_s * gg_scale / judged_df.google_static_s - 1).abs()
    print(f"reference, Google's own roads (g): scaled |error| {quantile_line(gg_error, 'rel')}; sd log ratio "
          f"{np.log(judged_df.time_gg_s / judged_df.google_static_s).std():.4f}")

    median_rel = judged_df.abs_delta_rel.median()
    p90_abs_rel = judged_df.abs_delta_rel.quantile(0.9)
    median_model_error = judged_df.model_error.median()
    holds = median_rel <= HOLD_MEDIAN_REL and p90_abs_rel < median_model_error
    print(f"\nCriterion: median |delta|/trip {median_rel:.3f} (<= {HOLD_MEDIAN_REL}) and p90 {p90_abs_rel:.3f} "
          f"< median model error {median_model_error:.3f} -> claim {'HOLDS' if holds else 'FAILS'}")


def main():
    tee = Tee()
    sys.stdout = tee
    try:
        print(f"{DIAGNOSTIC_NAME}, run {RUN_DATE}. Reads frozen Routes responses and the timed graph; no API calls.")
        to_metric = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
        pairs_df = load_pairs(to_metric)
        adjacency, segments_df = load_graph(to_metric)
        results_df, tasks = build_tasks(pairs_df, segments_df)
        for end in ENDS:
            print(f"{end} status: {results_df[f'{end}_status'].value_counts().to_dict()}")
        print(f"routing {len(tasks):,} pairs on {N_WORKERS} workers ...")
        with Pool(N_WORKERS, initializer=init_worker, initargs=(adjacency,)) as pool:
            times = pool.map(pair_times, tasks, chunksize=16)
        judged_ix = results_df.index[results_df.is_judged]
        for variant in VARIANTS:
            results_df.loc[judged_ix, f"time_{variant}_s"] = [t[variant] for t in times]
        results_df["delta_s"] = results_df.time_pp_s - results_df.time_gg_s
        results_df["delta_origin_s"] = results_df.time_pg_s - results_df.time_gg_s
        results_df["delta_dest_s"] = results_df.time_gp_s - results_df.time_gg_s
        results_df.to_csv(PAIRS_PATH, index=False)
        print(f"Saved {PAIRS_PATH}")

        judged_df = results_df[results_df.is_judged].copy()
        time_cols = [f"time_{variant}_s" for variant in VARIANTS]
        is_unreached = ~np.isfinite(judged_df[time_cols]).all(axis=1)
        print(f"unreached within {SEARCH_LIMIT_FACTOR}x Google's duration: {is_unreached.sum():,} pairs, dropped")
        judged_df = judged_df[~is_unreached]
        for end in ENDS:
            judged_df[f"{end}_same_link"] = judged_df[f"{end}_same_link"].astype(bool)
        report(judged_df)
    finally:
        sys.stdout = tee.stdout
        LOG_PATH.write_text("".join(tee.lines), encoding="utf-8")
        print(f"Saved {LOG_PATH}")


if __name__ == "__main__":
    main()
