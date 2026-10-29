"""Which road does Google start and end a drive trip on? (DESIGN.md Q12)

Claim: Google starts (and ends) a drive trip on the road nearest the requested point that can reach
the destination, not on the most efficient road nearby.
Where the pipeline relies on it: config.CANDIDATE_TIE_WINDOW_M = 1 (routing_graph keeps a hex's second
candidate road only within 1 m of its nearest) and routing's tie rule, the same value (routing uses the second
candidate only within 1 m). DESIGN_pre_spine "Drive layer" (Graph) and Q12.

Method (no API calls): the frozen 2026-09-30 Routes responses carry Google's snapped start and end
points and the route polyline for 4,000 pairs (origin = hex centroid, destination = venue). For each
of the 8,000 endpoints:
1. Roads are links, as routing_graph defines them: a chain of OSM segments through degree-2 nodes
   (one street between junctions). Built here from the unsplit drive graph
   (outputs/road_graphs/drive_graph.gpickle), not from construct_graph's split graph, whose candidates
   come from the rule under test.
2. Google's link: the link nearest Google's snapped point. When a second link is within AMBIGUOUS_M
   of that point (a junction), the polyline's first (last, for destinations) POLYLINE_PROBE_M decides;
   if it can't separate them by POLYLINE_SEPARATION_M, the endpoint is "ambiguous". No link within
   UNMATCHED_M: "unmatched" (OSM and Google geometry disagree).
3. Rank of Google's link among links ranked by distance from the requested point, in two universes:
   "pipeline" (the drive graph's largest strongly connected component, motorways excluded, as
   routing_graph) and "all" (every drive road). Gap = distance to Google's link minus distance to the
   nearest link. "covered" = rank 1, or rank 2 with gap <= TIE_WINDOW_M (the pipeline keeps it).
Pre-registered criterion (fixed before the first run, 2026-10-09): the claim holds if >= PASS_SHARE of
matched, unambiguous endpoints are rank 1 in the pipeline universe. If rank-2 picks cluster at gaps
above TIE_WINDOW_M, the tie window needs widening. Sensitivity: AMBIGUOUS_M and UNMATCHED_M grids.

Conclusion (run 2026-10-09, 8,000 endpoints): the claim FAILS the pre-registered bar. Of 7,154 matched,
unambiguous endpoints, 81.6% start/end on the pipeline's nearest link (95% needed); 85.8% are covered by
the 1 m tie window. Widening the window helps little: rank >= 2 gaps have median 3.1 m, upper quartile
9.6 m. Stable across thresholds (rank-1 share 77.8-81.8%). 719 endpoints unmatched (Google's point
> 15 m from any OSM link), 127 ambiguous. Not pre-registered, exploratory: in 64% of the misses the
nearest link is a service road (car park aisles, driveways); Google uses the public road. Other misses:
Google's point at a junction on the next link of the same street, or the far carriageway of a dual
road. A miss is a different start link, not necessarily a different trip time.
Exploratory follow-up (2026-10-09, universe pipeline_no_service: service roads also excluded): worse
overall, rank-1 share 66.5%, covered 69.7%. Google's own road is a service road for 1,785 endpoints
(1,195 destinations), which that universe can never match; on the 5,234 endpoints where Google uses a
public road, rank 1 rises from 83.2% to 90.9%. Profiled further in google_drive_snap_profile.py.

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
"""

import datetime
import pickle
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

DIAGNOSTIC_NAME = "google_drive_snap_side"
RUN_DATE = datetime.date.today().strftime("%Y%m%d")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTES_DIR = PROJECT_ROOT / "frozen_inputs" / "routes_drive_eta_20260930"
DRAWS_PATH = ROUTES_DIR / "od_sample_pairs.csv"
ETA_PATH = ROUTES_DIR / "od_sample_pairs_google_estimates.csv"
DRIVE_GRAPH_PATH = PROJECT_ROOT / "outputs" / "road_graphs" / "drive_graph.gpickle"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
PREFIX = f"{DIAGNOSTIC_NAME}_{RUN_DATE}"
ENDPOINTS_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_endpoints.csv"
SUMMARY_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_summary.csv"
SENSITIVITY_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_sensitivity.csv"
LOG_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_log.txt"
CLASSES_FIG_PATH = DIAGNOSTIC_IMG_DIR / f"{PREFIX}_classes.png"
GAP_FIG_PATH = DIAGNOSTIC_IMG_DIR / f"{PREFIX}_gap.png"
EXAMPLES_FIG_PATH = DIAGNOSTIC_IMG_DIR / f"{PREFIX}_examples.png"

GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:7855"                        # GDA2020 / MGA 55, metres
EXCLUDED_HIGHWAY_TYPES = {"motorway", "motorway_link"}   # as config.CANDIDATE_EXCLUDED_HIGHWAY_TYPES
SERVICE_HIGHWAY_TYPES = {"service"}   # exploratory: also excluded in the pipeline_no_service universe
HTTP_OK = 200

SEARCH_RADIUS_M = 300           # links ranked around each requested point
AMBIGUOUS_M = 3                 # second link this close to Google's point -> polyline decides
UNMATCHED_M = 15                # no link this close to Google's point -> unmatched
AMBIGUOUS_GRID_M = (3, 5, 10)
UNMATCHED_GRID_M = (10, 15, 25)
POLYLINE_PROBE_M = (5, 10, 15, 20)   # distances along the route at which the polyline is sampled
POLYLINE_SEPARATION_M = 2       # the chosen link's mean probe distance must beat the next by this
PROBE_RADIUS_M = 60             # probe search radius; a probe farther from a link counts as this
TIE_WINDOW_M = 1                # as config.CANDIDATE_TIE_WINDOW_M (candidates and routing)
PASS_SHARE = 0.95               # pre-registered: share of rank-1 endpoints for the claim to hold
POLYLINE_PRECISION = 1e5        # Google encoded polyline: 5 decimal places
N_EXAMPLES = 6
EXAMPLE_HALF_WIDTH_M = 60
FIGURE_DPI = 150

UNIVERSES = ("pipeline", "pipeline_no_service", "all")
RESTRICTED_UNIVERSES = ("pipeline", "pipeline_no_service")   # Google's link may fall outside these
ENDS = ("origin", "dest")
CLASS_ORDER = ["rank_1", "rank_2_in_window", "rank_2", "rank_3_plus", "outside_universe",
               "ambiguous", "unmatched"]


class Tee:
    """Print to the console and keep every line for the run log."""

    def __init__(self):
        self.lines = []
        self.stdout = sys.stdout

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


def load_endpoints(to_metric):
    """One row per (draw, end): requested point, Google's snapped point and the route polyline (metres)."""
    draws_df = pd.read_csv(DRAWS_PATH)
    eta_df = pd.read_csv(ETA_PATH)
    pairs_df = draws_df.merge(eta_df, on="draw_no", how="inner", validate="one_to_one")
    pairs_df = pairs_df[(pairs_df.http_status == HTTP_OK) & pairs_df.g_o_lat.notna()
                        & pairs_df.g_d_lat.notna() & pairs_df.polyline.notna()]
    print(f"pairs: {len(draws_df):,} draws, {len(pairs_df):,} with Google points and a polyline")

    rows = []
    for pair in pairs_df.itertuples(index=False):
        lat_lon = decode_polyline(pair.polyline)
        line_x, line_y = to_metric.transform(lat_lon[:, 1], lat_lon[:, 0])
        line_xy = np.column_stack([line_x, line_y])
        for end in ENDS:
            if end == "origin":
                req_lat, req_lon, g_lat, g_lon = pair.origin_lat, pair.origin_lon, pair.g_o_lat, pair.g_o_lon
                route_xy = line_xy
            else:
                req_lat, req_lon, g_lat, g_lon = pair.dest_lat, pair.dest_lon, pair.g_d_lat, pair.g_d_lon
                route_xy = line_xy[::-1]          # walk back from the end
            rows.append(dict(draw_no=pair.draw_no, end=end, req_lat=req_lat, req_lon=req_lon,
                             g_lat=g_lat, g_lon=g_lon, route_xy=route_xy))
    endpoints_df = pd.DataFrame(rows)
    endpoints_df["req_x"], endpoints_df["req_y"] = to_metric.transform(endpoints_df.req_lon.to_numpy(),
                                                                       endpoints_df.req_lat.to_numpy())
    endpoints_df["g_x"], endpoints_df["g_y"] = to_metric.transform(endpoints_df.g_lon.to_numpy(),
                                                                   endpoints_df.g_lat.to_numpy())
    return endpoints_df


def link_finder(undirected):
    """Function road (u, v sorted) -> link id: a chain of roads through degree-2 nodes, named by its
    smallest road key (own copy of routing_graph's rule)."""
    parent = {}

    def find(road):
        parent.setdefault(road, road)
        while parent[road] != road:
            parent[road] = parent[parent[road]]
            road = parent[road]
        return road

    for node in undirected.nodes:
        neighbours = [other for other in undirected.neighbors(node) if other != node]
        if len(neighbours) == 2:
            root_1 = find(tuple(sorted((node, neighbours[0]))))
            root_2 = find(tuple(sorted((node, neighbours[1]))))
            if root_1 != root_2:
                parent[max(root_1, root_2)] = min(root_1, root_2)
    return find


def load_segments(to_metric):
    """One row per two-way-merged OSM segment: geometry (metres), link id, highway, one-way flag and
    whether it lies in the pipeline universe (largest SCC, motorways excluded)."""
    print(f"loading {DRIVE_GRAPH_PATH.name} ...")
    with open(DRIVE_GRAPH_PATH, "rb") as f:
        drive_graph = pickle.load(f)
    print(f"  {drive_graph.number_of_nodes():,} nodes, {drive_graph.number_of_edges():,} edges")
    largest_scc = max(nx.strongly_connected_components(drive_graph), key=len)
    print(f"  largest strongly connected component: {len(largest_scc):,} nodes")

    seen, rows = set(), []
    for u, v, data in drive_graph.edges(data=True):
        key = (min(u, v), max(u, v))
        if key in seen:
            continue
        seen.add(key)
        highway = data.get("highway")
        highway = ",".join(map(str, highway)) if isinstance(highway, list) else highway
        is_two_way = drive_graph.has_edge(v, u)
        in_scc = u in largest_scc and v in largest_scc     # the SCC subgraph keeps every edge between its nodes
        is_service = bool(set(highway.split(",")) & SERVICE_HIGHWAY_TYPES) if highway else False
        rows.append((key[0], key[1], highway, not is_two_way, in_scc, is_service))
    segments_df = pd.DataFrame(rows, columns=["a", "b", "highway", "is_oneway", "in_scc", "is_service"])

    find_link = link_finder(drive_graph.to_undirected(as_view=True))
    links = [find_link((a, b)) for a, b in zip(segments_df.a, segments_df.b)]
    segments_df["link"] = [f"{a}_{b}" for a, b in links]
    segments_df["in_pipeline"] = segments_df.in_scc & ~segments_df.highway.isin(EXCLUDED_HIGHWAY_TYPES)
    segments_df["in_pipeline_no_service"] = segments_df.in_pipeline & ~segments_df.is_service

    node_x = {node: data["x"] for node, data in drive_graph.nodes(data=True)}
    node_y = {node: data["y"] for node, data in drive_graph.nodes(data=True)}
    del drive_graph
    ax, ay = to_metric.transform(segments_df.a.map(node_x).to_numpy(), segments_df.a.map(node_y).to_numpy())
    bx, by = to_metric.transform(segments_df.b.map(node_x).to_numpy(), segments_df.b.map(node_y).to_numpy())
    coords = np.stack([np.column_stack([ax, ay]), np.column_stack([bx, by])], axis=1)
    segments_df["geometry"] = shapely.linestrings(coords)
    print(f"  segments: {len(segments_df):,} ({segments_df.in_pipeline.mean():.1%} in the pipeline universe), "
          f"links: {segments_df.link.nunique():,}")
    return segments_df


def near_links(points, tree, segments_df, radius_m):
    """Every link within radius_m of each point, nearest first: DataFrame ep, link, dist_m."""
    ep_ix, seg_ix = tree.query(points, predicate="dwithin", distance=radius_m)
    dist_m = shapely.distance(points[ep_ix], segments_df.geometry.to_numpy()[seg_ix])
    near_df = pd.DataFrame({"ep": ep_ix, "link": segments_df.link.to_numpy()[seg_ix], "dist_m": dist_m})
    return (near_df.groupby(["ep", "link"], as_index=False).dist_m.min()
            .sort_values(["ep", "dist_m", "link"], kind="stable").reset_index(drop=True))


def split_by_endpoint(near_df, n_endpoints, columns):
    """Per endpoint, the rows of near_df (sorted by ep) as a tuple of arrays, one per column."""
    bounds = np.searchsorted(near_df.ep.to_numpy(), np.arange(n_endpoints + 1))
    arrays = [near_df[col].to_numpy() for col in columns]
    return [tuple(arr[bounds[i]:bounds[i + 1]] for arr in arrays) for i in range(n_endpoints)]


def route_probes(endpoints_df):
    """Points POLYLINE_PROBE_M along each route from its first vertex: (endpoint, probe) array;
    a row of None for a route shorter than the last probe."""
    probes = np.full((len(endpoints_df), len(POLYLINE_PROBE_M)), None, dtype=object)
    for i, route_xy in enumerate(endpoints_df.route_xy):
        steps = np.hypot(*np.diff(route_xy, axis=0).T)
        along = np.concatenate([[0.0], np.cumsum(steps)])
        if along[-1] < max(POLYLINE_PROBE_M):
            continue
        x = np.interp(POLYLINE_PROBE_M, along, route_xy[:, 0])
        y = np.interp(POLYLINE_PROBE_M, along, route_xy[:, 1])
        probes[i] = shapely.points(x, y)
    return probes


def probe_means(endpoints_df, tree, segments_df):
    """Mean distance from each route's probes to each nearby link: dict (ep, link) -> metres. A probe
    with no segment of the link within PROBE_RADIUS_M counts as PROBE_RADIUS_M."""
    probes = route_probes(endpoints_df)
    has_probes = np.array([p is not None for p in probes[:, 0]])
    n_probes = len(POLYLINE_PROBE_M)
    probe_ep = np.repeat(np.flatnonzero(has_probes), n_probes)
    points = probes[has_probes].ravel().astype(object)
    probe_ix, seg_ix = tree.query(points, predicate="dwithin", distance=PROBE_RADIUS_M)
    dist_m = shapely.distance(points[probe_ix], segments_df.geometry.to_numpy()[seg_ix])
    per_probe = (pd.DataFrame({"ep": probe_ep[probe_ix], "probe": probe_ix,
                               "link": segments_df.link.to_numpy()[seg_ix], "dist_m": dist_m})
                 .groupby(["ep", "link", "probe"]).dist_m.min())
    grouped = per_probe.groupby(level=["ep", "link"])
    mean_m = (grouped.sum() + (n_probes - grouped.count()) * PROBE_RADIUS_M) / n_probes
    print(f"  routes with probes: {has_probes.sum():,} / {len(has_probes):,}")
    return mean_m.to_dict()


def prepare(endpoints_df, segments_df, tree):
    """Everything classify needs that does not depend on the thresholds, computed once."""
    n = len(endpoints_df)
    req_points = shapely.points(endpoints_df.req_x.to_numpy(), endpoints_df.req_y.to_numpy())
    g_points = shapely.points(endpoints_df.g_x.to_numpy(), endpoints_df.g_y.to_numpy())
    req_df = near_links(req_points, tree, segments_df, SEARCH_RADIUS_M)
    g_df = near_links(g_points, tree, segments_df, max(UNMATCHED_GRID_M) + max(AMBIGUOUS_GRID_M))
    needed = pd.unique(np.concatenate([req_df.link.to_numpy(), g_df.link.to_numpy()]))
    link_attrs = (segments_df[segments_df.link.isin(needed)].groupby("link")
                  .agg(highway=("highway", "first"), is_oneway=("is_oneway", "all"),
                       in_pipeline=("in_pipeline", "all"),
                       in_pipeline_no_service=("in_pipeline_no_service", "all")))
    for universe in RESTRICTED_UNIVERSES:
        req_df[f"in_{universe}"] = req_df.link.map(link_attrs[f"in_{universe}"]).to_numpy(bool)
    print(f"  links near requested points: {len(req_df):,}; near Google's points: {len(g_df):,}")
    return dict(req=split_by_endpoint(req_df, n, ["link", "dist_m"]
                                      + [f"in_{universe}" for universe in RESTRICTED_UNIVERSES]),
                google=split_by_endpoint(g_df, n, ["link", "dist_m"]),
                probe_mean=probe_means(endpoints_df, tree, segments_df),
                highway=link_attrs.highway.to_dict(), is_oneway=link_attrs.is_oneway.to_dict(),
                **{f"in_{universe}": link_attrs[f"in_{universe}"].to_dict() for universe in RESTRICTED_UNIVERSES})


def google_link(i, prepared, ambiguous_m, unmatched_m):
    """(link, offset_m, status) for Google's snapped point; status matched / ambiguous / unmatched."""
    links, dist_m = prepared["google"][i]
    if len(links) == 0 or dist_m[0] > unmatched_m:
        return None, (dist_m[0] if len(links) else np.nan), "unmatched"
    is_contender = dist_m <= dist_m[0] + ambiguous_m
    if is_contender.sum() == 1:
        return links[0], dist_m[0], "matched"
    means = [prepared["probe_mean"].get((i, link)) for link in links[is_contender]]
    if any(mean is None for mean in means):            # route too short to probe
        return None, dist_m[0], "ambiguous"
    order = np.argsort(means, kind="stable")
    if means[order[1]] - means[order[0]] < POLYLINE_SEPARATION_M:
        return None, dist_m[0], "ambiguous"
    return links[is_contender][order[0]], dist_m[is_contender][order[0]], "matched"


def classify(endpoints_df, prepared, ambiguous_m, unmatched_m, keep_detail=False):
    """Per endpoint and universe: class, rank, gap and the nearest link's attributes."""
    rows = []
    for i, (draw_no, end) in enumerate(zip(endpoints_df.draw_no, endpoints_df.end)):
        link, offset_m, status = google_link(i, prepared, ambiguous_m, unmatched_m)
        req_links, req_dist_m, *req_in_restricted = prepared["req"][i]
        req_in_universe = dict(zip(RESTRICTED_UNIVERSES, req_in_restricted))
        for universe in UNIVERSES:
            out = dict(draw_no=draw_no, end=end, universe=universe, google_offset_m=offset_m)
            if status != "matched":
                out["cls"] = status
                rows.append(out)
                continue
            in_universe = req_in_universe.get(universe, np.ones(len(req_links), bool))
            u_links, u_dist_m = req_links[in_universe], req_dist_m[in_universe]
            google_match = req_dist_m[req_links == link]
            google_dist_m = google_match[0] if len(google_match) else np.nan
            out.update(google_link=link, google_dist_m=google_dist_m,
                       nearest_link=u_links[0] if len(u_links) else None,
                       nearest_dist_m=u_dist_m[0] if len(u_links) else np.nan)
            if universe in RESTRICTED_UNIVERSES and not prepared[f"in_{universe}"].get(link, False):
                out["cls"], out["rank"] = "outside_universe", np.nan
            elif np.isnan(google_dist_m):                 # beyond SEARCH_RADIUS_M of the requested point
                out["cls"], out["rank"], out["gap_m"] = "rank_3_plus", np.inf, np.nan
            else:
                rank = int((u_dist_m < google_dist_m).sum()) + 1
                gap_m = google_dist_m - u_dist_m[0]
                out["rank"], out["gap_m"] = rank, gap_m
                out["cls"] = ("rank_1" if rank == 1 else
                              ("rank_2_in_window" if gap_m <= TIE_WINDOW_M else "rank_2") if rank == 2 else
                              "rank_3_plus")
            if keep_detail and out["nearest_link"] is not None and out["cls"] != "rank_1":
                out["nearest_highway"] = prepared["highway"].get(out["nearest_link"])
                out["nearest_is_oneway"] = prepared["is_oneway"].get(out["nearest_link"])
                out["google_highway"] = prepared["highway"].get(link)
            rows.append(out)
    return pd.DataFrame(rows)


def class_shares(results_df):
    """Share of each class per universe and end (all endpoints), plus the criterion share."""
    table = (results_df.groupby(["universe", "end"]).cls.value_counts().unstack(fill_value=0)
             .reindex(columns=CLASS_ORDER, fill_value=0))
    for universe in UNIVERSES:
        table.loc[(universe, "both"), :] = table.loc[universe].sum()
    table = table.sort_index()
    judged = table.drop(columns=["ambiguous", "unmatched"]).sum(axis=1)
    table["n"] = table[CLASS_ORDER].sum(axis=1)
    table["rank_1_share"] = table.rank_1 / judged
    table["covered_share"] = (table.rank_1 + table.rank_2_in_window) / judged
    return table


def plot_classes(table):
    fig, axes = plt.subplots(1, len(UNIVERSES), figsize=(6 * len(UNIVERSES), 4), sharey=True)
    colours = plt.get_cmap("tab10").colors
    for ax, universe in zip(axes, UNIVERSES):
        sub = table.loc[universe, CLASS_ORDER]
        shares = sub.div(sub.sum(axis=1), axis=0)
        left = np.zeros(len(shares))
        for k, cls in enumerate(CLASS_ORDER):
            ax.barh(shares.index, shares[cls], left=left, color=colours[k], label=cls)
            left += shares[cls].to_numpy()
        ax.set_title(f"{universe} universe")
        ax.set_xlabel("share of endpoints")
    axes[-1].legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    fig.suptitle(f"Google's start/end link vs the requested point's nearest link "
                 f"(ambiguous {AMBIGUOUS_M} m, unmatched {UNMATCHED_M} m)")
    fig.tight_layout()
    fig.savefig(CLASSES_FIG_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {CLASSES_FIG_PATH}")


def plot_gaps(results_df):
    sub = results_df[(results_df.universe == "pipeline") & results_df["rank"].ge(2)]
    fig, ax = plt.subplots(figsize=(7, 4))
    bins = np.logspace(-2, np.log10(SEARCH_RADIUS_M), 40)
    for end in ENDS:
        ax.hist(sub.loc[sub.end == end, "gap_m"].clip(lower=bins[0]), bins=bins, alpha=0.6, label=end)
    ax.axvline(TIE_WINDOW_M, color="k", ls="--", label=f"tie window {TIE_WINDOW_M} m")
    ax.set_xscale("log")
    ax.set_xlabel("gap: distance to Google's link - distance to nearest link (m)")
    ax.set_ylabel("endpoints (rank >= 2, pipeline universe)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(GAP_FIG_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {GAP_FIG_PATH}")


def plot_examples(results_df, endpoints_df, segments_df, tree):
    misses = results_df[(results_df.universe == "pipeline") & results_df.cls.isin(["rank_2", "rank_3_plus"])]
    if misses.empty:
        print("no rank >= 2 endpoints to draw")
        return
    picks = misses.sample(min(N_EXAMPLES, len(misses)), random_state=0)
    fig, axes = plt.subplots(2, (len(picks) + 1) // 2, figsize=(5 * ((len(picks) + 1) // 2), 10), squeeze=False)
    endpoint_by_key = endpoints_df.set_index(["draw_no", "end"])
    for ax, pick in zip(axes.flat, picks.itertuples(index=False)):
        ep = endpoint_by_key.loc[(pick.draw_no, pick.end)]
        box = shapely.box(ep.req_x - EXAMPLE_HALF_WIDTH_M, ep.req_y - EXAMPLE_HALF_WIDTH_M,
                          ep.req_x + EXAMPLE_HALF_WIDTH_M, ep.req_y + EXAMPLE_HALF_WIDTH_M)
        for seg in segments_df.iloc[tree.query(box)].itertuples(index=False):
            x, y = shapely.get_coordinates(seg.geometry).T
            colour = ("tab:red" if seg.link == pick.google_link else
                      "tab:blue" if seg.link == pick.nearest_link else
                      "0.6" if seg.in_pipeline else "0.85")
            ax.plot(x, y, color=colour, lw=2.5 if colour.startswith("tab") else 1)
        route = ep.route_xy[:40]
        ax.plot(route[:, 0], route[:, 1], "r--", lw=1)
        ax.plot(ep.req_x, ep.req_y, "kx", ms=9)
        ax.plot(ep.g_x, ep.g_y, "o", color="tab:red", ms=5)
        ax.set_xlim(ep.req_x - EXAMPLE_HALF_WIDTH_M, ep.req_x + EXAMPLE_HALF_WIDTH_M)
        ax.set_ylim(ep.req_y - EXAMPLE_HALF_WIDTH_M, ep.req_y + EXAMPLE_HALF_WIDTH_M)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"draw {pick.draw_no} {pick.end}: rank {pick.rank:.0f}, gap {pick.gap_m:.1f} m\n"
                     f"nearest {pick.nearest_highway}{' (one-way)' if pick.nearest_is_oneway else ''}, "
                     f"Google {pick.google_highway}", fontsize=9)
    for ax in list(axes.flat)[len(picks):]:
        ax.axis("off")
    fig.suptitle("x requested point, red dot Google's point, red Google's link, blue nearest link, "
                 "dashed Google's route", fontsize=10)
    fig.tight_layout()
    fig.savefig(EXAMPLES_FIG_PATH, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {EXAMPLES_FIG_PATH}")


def main():
    tee = Tee()
    sys.stdout = tee
    try:
        print(f"{DIAGNOSTIC_NAME}, run {RUN_DATE}. Reads frozen Routes responses only; no API calls.")
        to_metric = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
        endpoints_df = load_endpoints(to_metric)
        segments_df = load_segments(to_metric)
        tree = shapely.STRtree(segments_df.geometry.to_numpy())
        print("distances from every point to its nearby links ...")
        prepared = prepare(endpoints_df, segments_df, tree)

        results_df = classify(endpoints_df, prepared, AMBIGUOUS_M, UNMATCHED_M, keep_detail=True)
        results_df.to_csv(ENDPOINTS_PATH, index=False)
        print(f"Saved {ENDPOINTS_PATH}")

        table = class_shares(results_df)
        table.to_csv(SUMMARY_PATH)
        print(f"Saved {SUMMARY_PATH}")
        with pd.option_context("display.width", 200, "display.max_columns", 20, "display.precision", 3):
            print(f"\nClasses (ambiguous {AMBIGUOUS_M} m, unmatched {UNMATCHED_M} m); shares over matched, "
                  f"unambiguous endpoints:\n{table}")

        pipeline_both = table.loc[("pipeline", "both")]
        verdict = "HOLDS" if pipeline_both.rank_1_share >= PASS_SHARE else "FAILS"
        print(f"\nCriterion: rank-1 share (pipeline universe, both ends) {pipeline_both.rank_1_share:.1%} "
              f"vs {PASS_SHARE:.0%} -> claim {verdict}; covered by the {TIE_WINDOW_M} m window: "
              f"{pipeline_both.covered_share:.1%}")
        no_service_both = table.loc[("pipeline_no_service", "both")]
        print(f"Exploratory, service roads also excluded: rank-1 share {no_service_both.rank_1_share:.1%}; "
              f"covered {no_service_both.covered_share:.1%}")

        for universe in RESTRICTED_UNIVERSES:
            misses = results_df[(results_df.universe == universe) & results_df["rank"].ge(2)]
            if len(misses):
                print(f"\nrank >= 2 ({universe} universe), {len(misses):,} endpoints: gap quantiles (m) "
                      f"{misses.gap_m.quantile([0.1, 0.25, 0.5, 0.75, 0.9]).round(2).to_dict()}")
                print(f"  nearest link highway: {misses.nearest_highway.value_counts().head(8).to_dict()}")
                print(f"  nearest link one-way: {misses.nearest_is_oneway.mean():.1%}")
                print(f"  Google link highway: {misses.google_highway.value_counts().head(8).to_dict()}")
            outside = results_df[(results_df.universe == universe) & (results_df.cls == "outside_universe")]
            if len(outside):
                print(f"outside the {universe} universe: {len(outside):,} ({outside.end.value_counts().to_dict()}); "
                      f"Google link highway {outside.google_highway.value_counts().head(5).to_dict()}")

        sensitivity = []
        for ambiguous_m in AMBIGUOUS_GRID_M:
            for unmatched_m in UNMATCHED_GRID_M:
                grid_table = class_shares(classify(endpoints_df, prepared, ambiguous_m, unmatched_m))
                row = grid_table.loc[("pipeline", "both")]
                sensitivity.append(dict(ambiguous_m=ambiguous_m, unmatched_m=unmatched_m,
                                        ambiguous=int(row.ambiguous), unmatched=int(row.unmatched),
                                        rank_1_share=row.rank_1_share, covered_share=row.covered_share))
        sensitivity_df = pd.DataFrame(sensitivity)
        sensitivity_df.to_csv(SENSITIVITY_PATH, index=False)
        print(f"\nSensitivity (pipeline universe, both ends):\n{sensitivity_df.round(4).to_string(index=False)}")
        print(f"Saved {SENSITIVITY_PATH}")

        plot_classes(table)
        plot_gaps(results_df)
        plot_examples(results_df, endpoints_df, segments_df, tree)
    finally:
        sys.stdout = tee.stdout
        LOG_PATH.write_text("".join(tee.lines), encoding="utf-8")
        print(f"Saved {LOG_PATH}")


if __name__ == "__main__":
    main()
