"""How closely do Google's route polylines lie on our drive graph? Sets the matching threshold for the
Google regression (DESIGN.md Q14; "Drive model selection", item 4, "Matching").

Claim to settle: a distance threshold, plus a heading check, separates polyline stretches that run on a
road in our graph from stretches on a road we do not have (or on the other carriageway). The Google
regression puts matched length into road class x density cells and unmatched length into a dummy pace
per tier, so the threshold decides what the dummy absorbs. DESIGN_pre_spine expected the knee at 10-20 m and
says 1-3 m is too tight (encoding alone is 1e-5 deg ~ 1.1 m; Google's geometry is its own digitisation
and is simplified). The data decides; this diagnostic recommends, the user chooses.

Method (no API calls; polylines are in the saved Routes responses of both draws, 8,000 pairs):
- Each polyline is cut into pieces of at most PIECE_M; each piece is one point (its midpoint) carrying
  the piece's length and heading (direction of travel).
- Graph: the pipeline's timed blind graph (straight segments between nodes), two-way pairs merged.
  For each point, every segment within SEARCH_M: distance, and heading difference (two-way: either
  direction; one-way: its direction of travel, so the other carriageway of a dual road scores ~180).
  d_any = nearest segment at any heading; d_ok<tol> = nearest segment with heading difference <= tol.
- Knee of the d_ok distribution (Kneedle on the length-weighted CDF over 0..range, several ranges).
- At candidate thresholds: unmatched share of polyline length, per pair and pooled, by density tier
  (the point's level on the road-density raster, the 4-tier structure), by road class (of the nearest
  segment at any heading: for an unmatched point this is the nearest road, not the road driven), and
  at trip ends (first/last END_M of the polyline) vs the middle.
- Whether high-share trips are a distinct kind of trip: Spearman of the pair's unmatched share against
  blind beta = 2's log error vs Google (window draw time blind_b2_raw_s, median-centred, i.e. ALPHA
  fitted on all pairs), and error by share bin.

Conclusion (run 2026-10-11, 8,000 pairs, 137,040 km of polyline, 14.3M points; threshold not yet
chosen, user's decision): Google's polylines lie much closer to our graph than DESIGN_pre_spine expected.
Length-weighted distance to the nearest same-heading (<= 45 deg) segment: median 1.0 m, p90 3.2 m, p95
4.3 m, p99 8.0 m; within 5 m 96.7%, 10 m 99.4%, 15 m 99.6%, 20 m 99.7%. The Kneedle knee is at 4-6 m
(by range), not 10-20 m; it marks the end of the digitisation-noise body, and beyond ~10 m the
unmatched share is a flat tail (0.6% at 10 m, 0.4% at 15 m, 0.3% at 20 m). The heading check changes
little (0.4% vs 0.6% unmatched at 10 m, any heading vs <= 45; 30/45/60 deg nearly identical). The tail
sits at trip ends: at 10 m, 3.9% of the length within 200 m of either end is unmatched vs 0.6% of the
rest; by nearest road, service 6.4%, unclassified 3.4%, residential 1.8%, trunk/primary ~0.1%; by
tier, rural 1.0% vs dense 0.3%. That is Q12's map-inventory mismatch (car parks, access lanes).
Per pair at 10 m: 52% have none, mean 0.6%, 0.6% of pairs over 10%. High-share trips are not a
distinct kind: Spearman of share vs blind beta = 2 |log error| is -0.02 to -0.09 at every threshold.
Read: a threshold anywhere in 7.5-15 m puts 0.4-1.1% of length in the dummy; 5 m (the knee) would
push ~3% of length, mostly digitisation noise, into it.

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
"""

import datetime
import pickle
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from scipy.stats import spearmanr

DIAGNOSTIC_NAME = "google_polyline_match"
RUN_DATE = datetime.date.today().strftime("%Y%m%d")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
SUBJECT_DIR_NAME = "-37.76870_144.97196"
DRAW1_DIR = PROJECT_ROOT / "frozen_inputs" / "routes_drive_eta_20260930"
DRAW1_PAIRS_PATH = DRAW1_DIR / "od_sample_pairs.csv"
DRAW1_ETA_PATH = DRAW1_DIR / "od_sample_pairs_google_estimates.csv"
CALIBRATION_DIR = PROJECT_ROOT / "outputs" / "pathing_calibration" / SUBJECT_DIR_NAME
DRAW2_PAIRS_PATH = CALIBRATION_DIR / f"od_sample_pairs_draw2_{SUBJECT_TAG}.csv"
DRAW2_ETA_PATH = CALIBRATION_DIR / f"routes_drive_eta_draw2_{SUBJECT_TAG}.csv"
TIMED_GRAPH_PATH = (PROJECT_ROOT / "outputs" / "speed_graphs" / SUBJECT_DIR_NAME
                    / f"split_drive_edges_timed_blind_{SUBJECT_TAG}.pkl")
DENSITY_RASTER_PATH = PROJECT_ROOT / "outputs" / "road_density" / "road_density_raster.npz"

DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
PREFIX = f"{DIAGNOSTIC_NAME}_{RUN_DATE}"
SEGMENTS_GLOB = f"{DIAGNOSTIC_NAME}_*_segments.npz"     # graph extract, reused if present
POINTS_GLOB = f"{DIAGNOSTIC_NAME}_*_points.npz"         # per-point match results, reused if present
SEGMENTS_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_segments.npz"
POINTS_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_points.npz"
PAIRS_OUT_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_pairs.csv"
SUMMARY_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_summary.csv"
LOG_PATH = DIAGNOSTIC_DATA_DIR / f"{PREFIX}_log.txt"
DISTANCE_FIGURE_PATH = DIAGNOSTIC_IMG_DIR / f"{PREFIX}_distance.png"
SHARE_FIGURE_PATH = DIAGNOSTIC_IMG_DIR / f"{PREFIX}_unmatched_share.png"

GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:7855"                        # GDA2020 / MGA 55, metres (also the raster's CRS)
HTTP_OK = 200
POLYLINE_PRECISION = 1e5                        # Google encoded polyline: 5 decimal places
NODE_LON_ATTR, NODE_LAT_ATTR = "x", "y"
EDGE_HIGHWAY_ATTR = "highway"
LINK_SUFFIX = "_link"

PIECE_M = 10.0                                  # polyline cut into pieces of at most this length
SEARCH_M = 40.0                                 # segments farther than this are never a match
NEAREST_MAX_M = 200.0                           # d_any is measured up to here (knee ranges)
POINT_CHUNK = 200_000                           # points per spatial-query chunk (memory)
HEADING_TOLS_DEG = (30, 45, 60)                 # heading checks reported
MAIN_HEADING_TOL_DEG = 45                       # the one used in the per-tier / per-class tables
THRESHOLDS_M = (3, 5, 7.5, 10, 12.5, 15, 20, 25, 30)
KNEE_RANGES_M = (30, 50, 100)
CDF_GRID_M = np.round(np.arange(0.0, NEAREST_MAX_M + 0.05, 0.1), 1)
END_M = 200                                     # polyline within this of either end counts as trip end

# Density levels: as road_density (level = round(km/km2 * 0.7), half up, capped at 15).
DENSITY_LEVEL_SCALE = 0.7
HALF_UP = 0.5
MAX_LEVEL = 15
TIERS = (("dense", 15, 15), ("fringe", 11, 14), ("suburban", 6, 10), ("rural", 0, 5))  # DESIGN_pre_spine 4-tier
OUTSIDE_RASTER_LEVEL = 0                        # as speed_graphs: points off the raster are rural

ROAD_CLASSES = {                                # highway -> reported class (links fold into parent)
    "motorway": "motorway", "trunk": "trunk", "primary": "primary", "secondary": "secondary",
    "tertiary": "tertiary", "unclassified": "unclassified", "residential": "residential",
    "living_street": "residential", "service": "service"}
OTHER_CLASS = "other"

SHARE_BINS = (-0.001, 0.0, 0.01, 0.03, 0.10, 1.0)   # pair unmatched share bins (first bin = exactly 0)
SHARE_BIN_LABELS = ("0", "0-1%", "1-3%", "3-10%", ">10%")
QUANTILES = (0.5, 0.75, 0.9, 0.95, 0.99)


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


def latest_ok(eta_df):
    """One row per draw_no: the HTTP 200 row if any, else the last attempt."""
    eta_df = eta_df.assign(is_ok=eta_df.http_status == HTTP_OK)
    return eta_df.sort_values("is_ok", kind="stable").drop_duplicates("draw_no", keep="last").drop(columns="is_ok")


def load_pairs():
    """Both draws joined to their Google responses; pairs with a polyline and a Google duration."""
    frames = []
    for draw, (pairs_path, eta_path) in {1: (DRAW1_PAIRS_PATH, DRAW1_ETA_PATH),
                                         2: (DRAW2_PAIRS_PATH, DRAW2_ETA_PATH)}.items():
        draws_df = pd.read_csv(pairs_path)
        eta_df = latest_ok(pd.read_csv(eta_path))
        joined_df = draws_df.merge(eta_df, on="draw_no", how="inner", validate="one_to_one").assign(draw=draw)
        frames.append(joined_df)
    pairs_df = pd.concat(frames, ignore_index=True)
    is_kept = ((pairs_df.http_status == HTTP_OK) & pairs_df.polyline.notna()
               & (pairs_df.google_drive_duration_sec > 0) & pairs_df.blind_b2_raw_s.notna())
    print(f"pairs: {len(pairs_df):,} joined, {is_kept.sum():,} with a polyline, Google time and blind time")
    return pairs_df[is_kept].reset_index(drop=True)


def latest_saved(pattern):
    """Newest saved file matching pattern in the data folder, or None."""
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def bearing_deg(dx, dy):
    """Compass-free bearing in degrees, 0..360, measured from +x counter-clockwise."""
    return np.degrees(np.arctan2(dy, dx)) % 360


def load_segments(to_metric):
    """Graph segments, two-way pairs merged: endpoint coordinates (metres), road class, whether two-way,
    and the bearing of the (one-way) direction of travel. Cached in the data folder."""
    saved = latest_saved(SEGMENTS_GLOB)
    if saved is not None:
        print(f"reusing graph segments from {saved.name}")
        with np.load(saved, allow_pickle=False) as data:
            return {key: data[key] for key in data.files}
    print(f"loading {TIMED_GRAPH_PATH.name} ...")
    with open(TIMED_GRAPH_PATH, "rb") as f:
        graph = pickle.load(f)
    print(f"  {graph.number_of_nodes():,} nodes, {graph.number_of_edges():,} edges")
    nodes = np.fromiter(graph.nodes, dtype=np.int64, count=graph.number_of_nodes())
    index = {node: i for i, node in enumerate(nodes)}
    lon = np.array([graph.nodes[node][NODE_LON_ATTR] for node in nodes])
    lat = np.array([graph.nodes[node][NODE_LAT_ATTR] for node in nodes])
    class_names = sorted(set(ROAD_CLASSES.values()) | {OTHER_CLASS})
    class_code = {name: i for i, name in enumerate(class_names)}
    tails, heads, classes = [], [], []
    for tail, head, data in graph.edges(data=True):
        highway = data.get(EDGE_HIGHWAY_ATTR)
        highway = highway[0] if isinstance(highway, list) else str(highway)
        tails.append(index[tail])
        heads.append(index[head])
        classes.append(class_code[ROAD_CLASSES.get(highway.removesuffix(LINK_SUFFIX), OTHER_CLASS)])
    del graph, index
    tails, heads, classes = np.array(tails), np.array(heads), np.array(classes, dtype=np.int8)
    lo, hi = np.minimum(tails, heads), np.maximum(tails, heads)
    key = lo.astype(np.int64) * len(nodes) + hi
    order = np.argsort(key, kind="stable")
    unique_key, first, counts = np.unique(key[order], return_index=True, return_counts=True)
    keep = order[first]                                 # one directed edge per node pair
    is_two_way = counts > 1
    x, y = to_metric.transform(lon, lat)
    segments = dict(ax=x[tails[keep]], ay=y[tails[keep]], bx=x[heads[keep]], by=y[heads[keep]],
                    road_class=classes[keep], is_two_way=is_two_way, class_names=np.array(class_names))
    segments["bearing"] = bearing_deg(segments["bx"] - segments["ax"], segments["by"] - segments["ay"])
    print(f"  segments: {len(keep):,} ({is_two_way.mean():.1%} two-way)")
    np.savez(SEGMENTS_PATH, **segments)
    return segments


def polyline_points(pairs_df, to_metric):
    """Every polyline cut into pieces of at most PIECE_M: per piece its midpoint, length, heading,
    pair row, and whether it lies within END_M of either end of the route."""
    rows, xs, ys, lengths, headings, is_end = [], [], [], [], [], []
    for row_ix, encoded in enumerate(pairs_df.polyline):
        lat_lon = decode_polyline(encoded)
        x, y = to_metric.transform(lat_lon[:, 1], lat_lon[:, 0])
        dx, dy = np.diff(x), np.diff(y)
        seg_len = np.hypot(dx, dy)
        is_real = seg_len > 0
        x0, y0, dx, dy, seg_len = x[:-1][is_real], y[:-1][is_real], dx[is_real], dy[is_real], seg_len[is_real]
        n_pieces = np.maximum(np.ceil(seg_len / PIECE_M).astype(int), 1)
        seg_ix = np.repeat(np.arange(len(seg_len)), n_pieces)
        piece_ix = np.arange(len(seg_ix)) - np.repeat(np.cumsum(n_pieces) - n_pieces, n_pieces)
        fraction = (piece_ix + 0.5) / n_pieces[seg_ix]
        piece_len = seg_len[seg_ix] / n_pieces[seg_ix]
        along = np.cumsum(piece_len) - piece_len / 2
        total = along[-1] + piece_len[-1] / 2 if len(along) else 0.0
        rows.append(np.full(len(seg_ix), row_ix, dtype=np.int32))
        xs.append(x0[seg_ix] + fraction * dx[seg_ix])
        ys.append(y0[seg_ix] + fraction * dy[seg_ix])
        lengths.append(piece_len)
        headings.append(bearing_deg(dx, dy)[seg_ix])
        is_end.append((along <= END_M) | (along >= total - END_M))
    return dict(pair_row=np.concatenate(rows), x=np.concatenate(xs), y=np.concatenate(ys),
                length=np.concatenate(lengths), heading=np.concatenate(headings), is_end=np.concatenate(is_end))


def heading_difference(point_heading, seg_bearing, is_two_way):
    """Angle between travel direction and segment, 0..180; a two-way segment matches either way."""
    diff = np.abs((point_heading - seg_bearing + 180) % 360 - 180)
    return np.where(is_two_way, np.minimum(diff, 180 - diff), diff)


def match_points(points, segments):
    """Per point: d_any (nearest segment, up to NEAREST_MAX_M, else inf), the nearest segment's road
    class, and d_ok<tol> (nearest segment within SEARCH_M whose heading difference <= tol, else inf)."""
    geoms = shapely.linestrings(np.stack([np.column_stack([segments["ax"], segments["ay"]]),
                                          np.column_stack([segments["bx"], segments["by"]])], axis=1))
    tree = shapely.STRtree(geoms)
    n_points = len(points["x"])
    d_any = np.full(n_points, np.inf)
    nearest_class = np.full(n_points, -1, dtype=np.int8)
    d_ok = {tol: np.full(n_points, np.inf) for tol in HEADING_TOLS_DEG}
    for start in range(0, n_points, POINT_CHUNK):
        stop = min(start + POINT_CHUNK, n_points)
        point_geoms = shapely.points(points["x"][start:stop], points["y"][start:stop])
        (point_ix, seg_ix), dist = tree.query_nearest(point_geoms, max_distance=NEAREST_MAX_M,
                                                      return_distance=True, all_matches=False)
        d_any[start + point_ix] = dist
        nearest_class[start + point_ix] = segments["road_class"][seg_ix]

        point_ix, seg_ix = tree.query(point_geoms, predicate="dwithin", distance=SEARCH_M)
        dist = shapely.distance(point_geoms[point_ix], geoms[seg_ix])
        diff = heading_difference(points["heading"][start + point_ix], segments["bearing"][seg_ix],
                                  segments["is_two_way"][seg_ix])
        for tol, values in d_ok.items():
            is_aligned = diff <= tol
            np.minimum.at(values, start + point_ix[is_aligned], dist[is_aligned])
        print(f"  matched {stop:,} / {n_points:,} points")
    return d_any, nearest_class, d_ok


def point_levels(points):
    """Road-density level under each point (raster rule as road_density); off-raster -> level 0."""
    with np.load(DENSITY_RASTER_PATH) as raster:
        density = raster["density"]
        x0, y0, cell_m = float(raster["x0"]), float(raster["y0"]), float(raster["cell_m"])
        assert str(raster["crs"]) == METRIC_CRS, raster["crs"]
    ix = np.floor((points["x"] - x0) / cell_m).astype(int)
    iy = np.floor((points["y"] - y0) / cell_m).astype(int)
    is_inside = (ix >= 0) & (ix < density.shape[0]) & (iy >= 0) & (iy < density.shape[1])
    level = np.full(len(ix), float(OUTSIDE_RASTER_LEVEL))
    sampled = density[ix[is_inside], iy[is_inside]]
    level[is_inside] = np.where(np.isnan(sampled), OUTSIDE_RASTER_LEVEL,
                                np.minimum(np.floor(sampled * DENSITY_LEVEL_SCALE + HALF_UP), MAX_LEVEL))
    return level


def tier_names(level):
    names = np.empty(len(level), dtype=object)
    for name, low, high in TIERS:
        names[(level >= low) & (level <= high)] = name
    return names


def weighted_cdf(distance, weight):
    """Length-weighted share of points with distance <= each value of CDF_GRID_M."""
    order = np.argsort(distance)
    cum = np.cumsum(weight[order]) / weight.sum()
    pos = np.searchsorted(distance[order], CDF_GRID_M, side="right")
    return np.where(pos > 0, cum[np.maximum(pos - 1, 0)], 0.0)


def kneedle(cdf, range_m):
    """Knee of a concave CDF on [0, range_m]: the grid value farthest above the chord."""
    is_in = CDF_GRID_M <= range_m
    grid, values = CDF_GRID_M[is_in], cdf[is_in]
    chord = values[0] + (values[-1] - values[0]) * grid / range_m
    return float(grid[np.argmax(values - chord)])


def share_table(unmatched_len, length, groups):
    """Unmatched share of length per group (dict of label -> boolean mask)."""
    return {label: unmatched_len[mask].sum() / length[mask].sum() if mask.any() else np.nan
            for label, mask in groups.items()}


def main():
    tee = Tee()
    sys.stdout = tee
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"{DIAGNOSTIC_NAME}  run {RUN_DATE}")
    to_metric = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)

    pairs_df = load_pairs()
    segments = load_segments(to_metric)
    class_names = segments["class_names"]

    saved = latest_saved(POINTS_GLOB)
    if saved is not None:
        print(f"reusing per-point matches from {saved.name}")
        with np.load(saved, allow_pickle=False) as data:
            points = {key: data[key] for key in data.files}
        assert points["n_pairs"] == len(pairs_df), "saved points are for a different pair set"
    else:
        points = polyline_points(pairs_df, to_metric)
        print(f"polyline points: {len(points['x']):,} (pieces <= {PIECE_M:g} m), "
              f"{points['length'].sum() / 1000:,.0f} km of route")
        d_any, nearest_class, d_ok = match_points(points, segments)
        points.update(d_any=d_any, nearest_class=nearest_class, level=point_levels(points),
                      n_pairs=np.array(len(pairs_df)),
                      **{f"d_ok{tol}": values for tol, values in d_ok.items()})
        np.savez(POINTS_PATH, **points)

    length, pair_row = points["length"], points["pair_row"]
    tiers = tier_names(points["level"])
    road_class = np.where(points["nearest_class"] >= 0, class_names[np.maximum(points["nearest_class"], 0)],
                          "none within 200 m")
    is_end = points["is_end"].astype(bool)
    distances = {"any heading": points["d_any"],
                 **{f"heading <= {tol}": points[f"d_ok{tol}"] for tol in HEADING_TOLS_DEG}}

    # --- distance distribution and knee ---
    print("\n=== distance from polyline to nearest graph segment (length-weighted) ===")
    print(f"{'measure':<16}" + "".join(f"{'p' + str(int(q * 100)):>9}" for q in QUANTILES)
          + "".join(f"{'<=' + format(t, 'g') + 'm':>9}" for t in THRESHOLDS_M))
    cdfs, summary_rows = {}, []
    for label, dist in distances.items():
        cdf = weighted_cdf(np.minimum(dist, 1e9), length)
        cdfs[label] = cdf
        quantile_m = [CDF_GRID_M[min(np.searchsorted(cdf, q), len(CDF_GRID_M) - 1)] for q in QUANTILES]
        within = [cdf[np.searchsorted(CDF_GRID_M, t)] for t in THRESHOLDS_M]
        print(f"{label:<16}" + "".join(f"{q:>9.1f}" for q in quantile_m) + "".join(f"{w:>9.1%}" for w in within))
        summary_rows += [dict(table="cdf", measure=label, key=f"<= {t:g} m", value=w)
                         for t, w in zip(THRESHOLDS_M, within)]
    print("\nknee (Kneedle on the CDF, by range):")
    for label, cdf in cdfs.items():
        knees = {range_m: kneedle(cdf, range_m) for range_m in KNEE_RANGES_M}
        print(f"  {label:<16}" + "  ".join(f"0-{r} m: {k:.1f} m" for r, k in knees.items()))
        summary_rows += [dict(table="knee", measure=label, key=f"0-{r} m", value=k) for r, k in knees.items()]

    # --- unmatched share at candidate thresholds ---
    print(f"\n=== unmatched share of route length at each threshold (heading <= {MAIN_HEADING_TOL_DEG} deg) ===")
    main_dist = points[f"d_ok{MAIN_HEADING_TOL_DEG}"]
    groups = {"all": np.ones(len(length), bool), "trip ends (<=200 m)": is_end, "middle": ~is_end,
              **{f"tier {name}": tiers == name for name, _, _ in TIERS},
              **{f"nearest {name}": road_class == name for name in [*class_names, "none within 200 m"]}}
    group_km = {label: length[mask].sum() / 1000 for label, mask in groups.items()}
    print(f"{'group':<30}{'km':>9}" + "".join(f"{format(t, 'g') + 'm':>8}" for t in THRESHOLDS_M))
    shares_by_threshold = {t: share_table(length * (main_dist > t), length, groups) for t in THRESHOLDS_M}
    for label in groups:
        print(f"{label:<30}{group_km[label]:>9,.0f}"
              + "".join(f"{shares_by_threshold[t][label]:>8.1%}" for t in THRESHOLDS_M))
        summary_rows += [dict(table=f"unmatched_share_h{MAIN_HEADING_TOL_DEG}", measure=label, key=f"{t:g} m",
                              value=shares_by_threshold[t][label]) for t in THRESHOLDS_M]
    print("\nsame, other heading checks (all points):")
    for label, dist in distances.items():
        print(f"  {label:<16}" + "".join(f"{format(t, 'g') + 'm':>7} {np.sum(length * (dist > t)) / length.sum():>5.1%}"
                                         for t in THRESHOLDS_M))

    # --- per pair: unmatched share, and blind beta = 2 error ---
    pairs_out_df = pairs_df[["draw_no", "draw", "dest_hex", "google_drive_duration_sec", "blind_b2_raw_s",
                             "dep_min_of_day"]].copy()
    log_ratio = np.log(pairs_out_df.blind_b2_raw_s / pairs_out_df.google_drive_duration_sec)
    pairs_out_df["blind_b2_log_err"] = log_ratio - np.median(log_ratio)       # ALPHA median-centred
    route_len = np.bincount(pair_row, weights=length, minlength=len(pairs_df))
    pairs_out_df["polyline_km"] = route_len / 1000
    for t in THRESHOLDS_M:
        pairs_out_df[f"unmatched_share_{t:g}m"] = np.bincount(pair_row, weights=length * (main_dist > t),
                                                              minlength=len(pairs_df)) / route_len
        pairs_out_df[f"unmatched_mid_share_{t:g}m"] = np.bincount(
            pair_row, weights=length * (main_dist > t) * ~is_end, minlength=len(pairs_df)) / route_len
    pairs_out_df.to_csv(PAIRS_OUT_PATH, index=False)

    print(f"\n=== per pair (heading <= {MAIN_HEADING_TOL_DEG} deg) ===")
    print(f"{'threshold':>10}{'mean':>8}{'median':>8}{'p90':>8}{'p99':>8}{'=0':>8}{'>10%':>8}"
          f"{'rho err':>9}{'rho |err|':>10}{'rho |err| mid':>14}")
    for t in THRESHOLDS_M:
        share = pairs_out_df[f"unmatched_share_{t:g}m"]
        mid_share = pairs_out_df[f"unmatched_mid_share_{t:g}m"]
        rho = spearmanr(share, pairs_out_df.blind_b2_log_err).statistic
        rho_abs = spearmanr(share, pairs_out_df.blind_b2_log_err.abs()).statistic
        rho_abs_mid = spearmanr(mid_share, pairs_out_df.blind_b2_log_err.abs()).statistic
        print(f"{format(t, 'g') + ' m':>10}{share.mean():>8.1%}{share.median():>8.1%}{share.quantile(0.9):>8.1%}"
              f"{share.quantile(0.99):>8.1%}{(share == 0).mean():>8.1%}{(share > 0.1).mean():>8.1%}"
              f"{rho:>+9.3f}{rho_abs:>+10.3f}{rho_abs_mid:>+14.3f}")
        summary_rows += [dict(table="pair", measure=f"{t:g} m", key=key, value=value) for key, value in
                         (("mean share", share.mean()), ("rho share vs log err", rho),
                          ("rho share vs |log err|", rho_abs), ("rho mid share vs |log err|", rho_abs_mid))]

    for t in (10, 15, 20):
        share = pairs_out_df[f"unmatched_share_{t:g}m"]
        bins = pd.cut(share, SHARE_BINS, labels=SHARE_BIN_LABELS)
        table = pairs_out_df.groupby(bins, observed=False).agg(
            pairs=("draw_no", "size"), median_err=("blind_b2_log_err", "median"),
            median_abs_err=("blind_b2_log_err", lambda e: e.abs().median()),
            median_google_min=("google_drive_duration_sec", lambda s: s.median() / 60))
        print(f"\nblind beta=2 log error by pair unmatched share, threshold {t} m "
              f"(exp(log err) - 1 ~ % error):")
        print(table.to_string(float_format=lambda v: f"{v:.3f}"))

    pd.DataFrame(summary_rows).to_csv(SUMMARY_PATH, index=False)

    # --- figures ---
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    bins = np.logspace(-1, np.log10(NEAREST_MAX_M), 120)
    for label, dist in distances.items():
        is_finite = np.isfinite(dist)
        axes[0].hist(np.maximum(dist[is_finite], 0.1), bins=bins, weights=length[is_finite] / length.sum(),
                     histtype="step", label=label)
        axes[1].plot(CDF_GRID_M, cdfs[label], label=label)
    axes[0].set_xscale("log")
    axes[0].set_xlabel("distance to nearest segment, m (log)")
    axes[0].set_ylabel("share of route length")
    axes[0].legend(fontsize=8)
    axes[1].set_xlim(0, 50)
    axes[1].set_xlabel("threshold, m")
    axes[1].set_ylabel("share of route length matched")
    axes[1].grid(alpha=0.3)
    for t in (10, 15, 20):
        axes[1].axvline(t, color="grey", lw=0.5)
    fig.suptitle(f"Google polylines vs drive graph, {len(pairs_df):,} pairs ({RUN_DATE})")
    fig.tight_layout()
    fig.savefig(DISTANCE_FIGURE_PATH, dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    for label in ["all", "trip ends (<=200 m)", "middle", *[f"tier {name}" for name, _, _ in TIERS]]:
        ax.plot(THRESHOLDS_M, [shares_by_threshold[t][label] for t in THRESHOLDS_M], marker="o", label=label)
    ax.set_yscale("log")
    ax.set_xlabel("threshold, m")
    ax.set_ylabel(f"unmatched share of length (heading <= {MAIN_HEADING_TOL_DEG} deg)")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(SHARE_FIGURE_PATH, dpi=130)
    plt.close(fig)

    sys.stdout = tee.stdout
    LOG_PATH.write_text("".join(tee.lines), encoding="utf-8")
    print(f"saved {LOG_PATH.name}, {SUMMARY_PATH.name}, {PAIRS_OUT_PATH.name}, figures")


if __name__ == "__main__":
    main()
