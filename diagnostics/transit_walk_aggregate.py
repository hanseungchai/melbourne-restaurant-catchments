"""In aggregate, does R5's walking land where Google's does? (foot-traffic totals, report only)

Question (user, 2026-10-22, autonomous 69th): per trip, R5's walks match Google's poorly (TRN-12: pooled overlap 0.338
at 100 m; transit_walk_shape: 0.44-0.57 of walk metres within 25 m, the gap mostly route choice), so matching paths is
dropped; but foot traffic would be reported in aggregate (FRM-20), never per trip. Do the summed totals agree?
Where the pipeline would rely on it: the foot-traffic showcase (FRM-19 part 3, FRM-20), not built.

Data (saved only; no R5, no JVM, no API calls): the 1,246 scored training pairs of transit_walk_overlap: R5's walk
legs (stock R5 at w = 1, routed walk-only, 2026-10-18) and Google's default route's walking cut from its polyline
(copied cut). Stops: R5's board / alight stops from its stock choice (transit_walk_route_choice's w = 1 choices),
Google's from its ride steps.
Units: walk metres per project hex (points every STEP_M to the nearest hex centroid, STEP_M metres each), per
CELL_M (500 m) square cell; boardings + alightings per stop cluster (stops greedily merged within CLUSTER_M, 200 m, of
a cluster's first stop). Measures per unit set: weighted Jaccard sum(min) / sum(max); Spearman over units either
router touches; top-decile agreement (share of Google's top 10% of units by total also in R5's top 10%). Noise
floor: pairs split at random into halves (SPLIT_SEED), Google half A vs Google half B and R5 A vs R5 B (different
trips, same router): how much a total can agree when only sampling differs. Walk-only pairs and both-transit pairs
are pooled (the foot-traffic total); group shares reported.
Reading (Claude's rule, not user-approved, written before the run): aggregation "works" at a unit if R5 vs Google
weighted Jaccard >= 0.5 and top-decile agreement >= 0.6; "limited by sample" if R5 vs Google is within 0.05 of the
Google split-half floor; else "aggregation does not rescue".

Conclusion (run 2026-10-22, autonomous 69th; report only, Claude's rule): 1,246 pairs, walk km R5 1,469 / Google 982.
  R5 vs Google (weighted Jaccard / top-decile agreement): hex (100 m, 14,269 units) 0.405 / 0.626 -> "does not
  rescue" (Jaccard under 0.5); 500 m cell (1,798) 0.571 / 0.756 -> "works"; stop cluster (200 m, 1,130) 0.578 /
  0.726 -> "works". Split-half floors (same router, other trips) far below: Google 0.221 / 0.370 / 0.400, R5 0.234 /
  0.378 / 0.418, so the agreement is real signal, not sampling. As shares of each router's own total (R5's 1.5x walk
  volume removed; it caps metre Jaccard at 0.668): hex 0.414, cell 0.626, stop 0.575. Agreement grows with pairs
  (hex 0.327 / 0.343 / 0.378 / 0.393 / 0.405 at 150 / 300 / 600 / 900 / 1,246; cell 0.498 -> 0.571): about +0.02-0.03
  per doubling, so street-level noise does average out; reaching 0.5 at hex scale would need several more
  doublings (unmeasured: R5 geometry exists for the training half only). Spearman is not read: units touched by one
  side only count as zeros (split-half values negative). Reading: in aggregate, R5's walking places foot traffic
  like Google's at neighbourhood (500 m) and stop-cluster scale; not at street / hex scale; and R5's totals run
  ~1.5x Google's volume (a level bias to state or scale). Next free step if wanted: route the second batch's walk
  legs (r5py, free, one JVM) to extend the curve to ~3,000 pairs.

Inputs (read only): transit_walk_overlap_20261018_{r5_walks, pairs}.csv, transit_walk_route_choice_20261022_choices.csv,
transit_stop_match_20261018_r5_stops.csv, the pairs file, the raw Google answers, the hex grid. Self-contained
(CLAUDE.md D1). Usage: `python transit_walk_aggregate.py`.
"""
import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "-37.76870_144.97196"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / SUBJECT
FILE_TAG = f"res2021_wrk2021_ven20260925_{SUBJECT}"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
GOOGLE_RAW_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl"
HEX_GRID_PATH = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT / f"hex_grid_{SUBJECT}.gpkg"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
R5_WALKS_PATH = DIAGNOSTIC_DATA_DIR / "transit_walk_overlap_20261018_r5_walks.csv"
OVERLAP_PAIRS_PATH = DIAGNOSTIC_DATA_DIR / "transit_walk_overlap_20261018_pairs.csv"
CHOICES_PATH = DIAGNOSTIC_DATA_DIR / "transit_walk_route_choice_20261022_choices.csv"
R5_STOPS_PATH = DIAGNOSTIC_DATA_DIR / "transit_stop_match_20261018_r5_stops.csv"
NAME = "transit_walk_aggregate"

# --- values ----------------------------------------------------------------------------------------
DEFAULT_LABEL = "DEFAULT_ROUTE"
GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:7855"
POLYLINE_PRECISION = 1e5
MIN_LEG_M = 1.0
STEP_M = 10.0
CELL_M = 500.0
CLUSTER_M = 200.0
HEX_PAD_DEG = 0.01
TOP_SHARE = 0.10
SPLIT_SEED = 20261022
STOCK_W = 1.0
CURVE_SIZES = [150, 300, 600, 900]             # pairs per random subset for the agreement-vs-sample curve
CURVE_REPEATS = 10
READING_JACCARD = 0.5
READING_TOP = 0.6
READING_FLOOR_GAP = 0.05


def decode_polyline(encoded):
    """Google's encoded polyline -> list of (lon, lat) (from transit_walk_overlap.py)."""
    coords, index, lat, lon = [], 0, 0, 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift, value = 0, 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                value |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(value >> 1) if value & 1 else value >> 1)
        lat, lon = lat + deltas[0], lon + deltas[1]
        coords.append((lon / POLYLINE_PRECISION, lat / POLYLINE_PRECISION))
    return coords


def google_walks_and_stops(draw_nos, to_metric):
    """Per pair: (walking LineStrings, ride stop points) of the default route (cut as transit_walk_overlap)."""
    from shapely.geometry import LineString, Point
    from shapely.ops import substring
    walks, stops_by_pair = {}, {}
    with open(GOOGLE_RAW_PATH, encoding="utf-8") as raw_file:
        for line in raw_file:
            answer = json.loads(line)
            if answer["draw_no"] not in draw_nos:
                continue
            for route in answer["resp"].get("routes", []):
                if DEFAULT_LABEL not in route.get("routeLabels", []):
                    continue
                route_line = LineString([to_metric(lon, lat) for lon, lat in decode_polyline(route["polyline"]["encodedPolyline"])])
                rides = [step["transitDetails"]["stopDetails"] for leg in route.get("legs", [])
                         for step in leg.get("steps", []) if "transitDetails" in step]
                cuts, position, points = [0.0], 0.0, []
                for stops in rides:
                    for end in ("departureStop", "arrivalStop"):
                        lat_lng = stops[end]["location"]["latLng"]
                        xy = to_metric(lat_lng["longitude"], lat_lng["latitude"])
                        points.append(xy)
                        rest = substring(route_line, position, route_line.length)
                        position += rest.project(Point(xy)) if rest.length > 0 else 0.0
                        cuts.append(position)
                cuts.append(route_line.length)
                walks[answer["draw_no"]] = [substring(route_line, a, b) for a, b in zip(cuts[0::2], cuts[1::2])
                                            if b - a >= MIN_LEG_M]
                stops_by_pair[answer["draw_no"]] = points
    return walks, stops_by_pair


def sample_points(lines):
    points = []
    for line in [part for line in lines for part in getattr(line, "geoms", [line])]:
        n_steps = max(int(np.ceil(line.length / STEP_M)), 1)
        for k in range(n_steps):
            point = line.interpolate((k + 0.5) * line.length / n_steps)
            points.append((point.x, point.y, line.length / n_steps))
    return np.asarray(points).reshape(-1, 3)


def hex_lookup(points_xy, to_geographic):
    import pyogrio
    from pyproj import Transformer
    from scipy.spatial import cKDTree
    lon_min, lat_min = to_geographic(points_xy[:, 0].min(), points_xy[:, 1].min())
    lon_max, lat_max = to_geographic(points_xy[:, 0].max(), points_xy[:, 1].max())
    hex_df = pyogrio.read_dataframe(HEX_GRID_PATH, columns=["hex_id", "centroid_lat", "centroid_lon"], read_geometry=False,
                                    bbox=(lon_min - HEX_PAD_DEG, lat_min - HEX_PAD_DEG, lon_max + HEX_PAD_DEG, lat_max + HEX_PAD_DEG))
    transformer = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
    hx, hy = transformer.transform(hex_df.centroid_lon.to_numpy(), hex_df.centroid_lat.to_numpy())
    return cKDTree(np.column_stack([hx, hy])), hex_df.hex_id.to_numpy()


def totals(points_by_pair, draw_nos, unit_of):
    """Sum of weights per unit over the given pairs; points_by_pair: draw_no -> (n, 3) x, y, weight."""
    frames = [points_by_pair[d] for d in draw_nos if d in points_by_pair and len(points_by_pair[d])]
    if not frames:
        return pd.Series(dtype=float)
    points = np.vstack(frames)
    return pd.Series(points[:, 2]).groupby(unit_of(points[:, :2])).sum()


def compare(a, b):
    """(weighted Jaccard, Spearman, top-decile agreement of a's top in b's top)."""
    both = pd.concat([a.rename("a"), b.rename("b")], axis=1).fillna(0.0)
    jaccard = np.minimum(both.a, both.b).sum() / np.maximum(both.a, both.b).sum()
    spearman = both.a.rank().corr(both.b.rank())
    k = max(int(round(TOP_SHARE * len(both))), 1)
    top_a, top_b = set(both.a.nlargest(k).index), set(both.b.nlargest(k).index)
    return jaccard, spearman, len(top_a & top_b) / k


def cluster_stops(points_xy):
    """Greedy clusters within CLUSTER_M of a cluster's first stop; returns a function xy -> cluster id."""
    from scipy.spatial import cKDTree
    unique = np.unique(np.round(points_xy, 1), axis=0)
    centres = []
    tree_points = cKDTree(unique)
    assigned = np.full(len(unique), -1)
    for i in range(len(unique)):
        if assigned[i] >= 0:
            continue
        members = [j for j in tree_points.query_ball_point(unique[i], CLUSTER_M) if assigned[j] < 0]
        assigned[members] = len(centres)
        centres.append(unique[i])
    tree = cKDTree(np.asarray(unique))
    return lambda xy: assigned[tree.query(np.round(xy, 1))[1]]


def main():
    from pyproj import Transformer
    from shapely import wkt
    from shapely.ops import transform
    run_date = datetime.date.today().strftime("%Y%m%d")
    to_metric_t = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
    to_geo_t = Transformer.from_crs(METRIC_CRS, GEOGRAPHIC_CRS, always_xy=True)
    pairs_df = pd.read_csv(OVERLAP_PAIRS_PATH).set_index("draw_no")
    draw_nos = list(pairs_df.index)
    r5_df = pd.read_csv(R5_WALKS_PATH)
    r5_df["draw_no"] = r5_df.leg_id.str.split("_").str[0].astype(int)
    r5_lines = {d: [transform(to_metric_t.transform, wkt.loads(text)) for text in g.geometry_wkt] for d, g in r5_df.groupby("draw_no")}
    google_lines, google_stops = google_walks_and_stops(set(draw_nos), lambda lon, lat: to_metric_t.transform(lon, lat))
    r5_points = {d: sample_points(lines) for d, lines in r5_lines.items()}
    google_points = {d: sample_points(lines) for d, lines in google_lines.items()}
    lines = [f"{NAME} run {run_date}: {len(draw_nos)} pairs ({pairs_df.group.value_counts().to_dict()}); walk km R5 "
             f"{sum(p[:, 2].sum() for p in r5_points.values()) / 1000:.0f}, Google {sum(p[:, 2].sum() for p in google_points.values()) / 1000:.0f}"]

    # stops: R5's stock choice (w = 1) and Google's ride stops, one point per board / alight, weight 1
    stops_df = pd.read_csv(R5_STOPS_PATH).set_index("stop")
    choices_df = pd.read_csv(CHOICES_PATH)
    choices_df = choices_df[choices_df.walk_weight == STOCK_W].set_index("draw_no").route_id.fillna("")
    r5_stop_points = {}
    for draw_no in draw_nos:
        route_id = choices_df.get(draw_no, "")
        xy = []
        if isinstance(route_id, str) and route_id:
            _, boards, alights = (part.split("+") for part in route_id.split("|"))
            for stop in boards + alights:
                xy.append(to_metric_t.transform(stops_df.loc[int(stop)].lon, stops_df.loc[int(stop)].lat))
        r5_stop_points[draw_no] = np.array([(x, y, 1.0) for x, y in xy]).reshape(-1, 3)
    google_stop_points = {d: np.array([(x, y, 1.0) for x, y in pts]).reshape(-1, 3) for d, pts in google_stops.items()}

    all_xy = np.vstack([p[:, :2] for p in list(r5_points.values()) + list(google_points.values()) if len(p)])
    tree, hex_ids = hex_lookup(all_xy, lambda x, y: to_geo_t.transform(x, y))
    all_stops = np.vstack([p[:, :2] for p in list(r5_stop_points.values()) + list(google_stop_points.values()) if len(p)])
    cluster_of = cluster_stops(all_stops)
    units = {"hex (100 m)": (lambda xy: hex_ids[tree.query(xy)[1]], r5_points, google_points),
             f"cell ({CELL_M:.0f} m)": (lambda xy: [f"{int(x // CELL_M)}_{int(y // CELL_M)}" for x, y in xy], r5_points, google_points),
             f"stop cluster ({CLUSTER_M:.0f} m)": (cluster_of, r5_stop_points, google_stop_points)}

    rng = np.random.default_rng(SPLIT_SEED)
    is_a = rng.random(len(draw_nos)) < 0.5
    half_a, half_b = [d for d, a in zip(draw_nos, is_a) if a], [d for d, a in zip(draw_nos, is_a) if not a]
    lines += ["", f"unit: R5 vs Google (same pairs, all) | Google A vs B | R5 A vs B (split-half floors, {len(half_a)} / "
              f"{len(half_b)} pairs); each: weighted Jaccard, Spearman, top-{TOP_SHARE:.0%} agreement"]
    records = []
    for unit, (unit_of, r5_set, google_set) in units.items():
        r5_total, google_total = totals(r5_set, draw_nos, unit_of), totals(google_set, draw_nos, unit_of)
        same = compare(google_total, r5_total)
        google_floor = compare(totals(google_set, half_a, unit_of), totals(google_set, half_b, unit_of))
        r5_floor = compare(totals(r5_set, half_a, unit_of), totals(r5_set, half_b, unit_of))
        half_same = compare(totals(google_set, half_a, unit_of), totals(r5_set, half_a, unit_of))
        n_units = len(set(r5_total.index) | set(google_total.index))
        share_same = compare(google_total / google_total.sum(), r5_total / r5_total.sum())
        if same[0] >= READING_JACCARD and same[2] >= READING_TOP:
            reading = "aggregation works"
        elif abs(same[0] - google_floor[0]) <= READING_FLOOR_GAP:
            reading = "limited by sample"
        else:
            reading = "aggregation does not rescue"
        fmt = lambda t: f"{t[0]:.3f} / {t[1]:.3f} / {t[2]:.3f}"   # noqa: E731
        lines.append(f"  {unit} ({n_units:,} units): {fmt(same)} | {fmt(google_floor)} | {fmt(r5_floor)}; R5 vs Google "
                     f"on half A {fmt(half_same)} -> {reading}; as shares of each router's own total (volume "
                     f"removed; cap on metres {min(r5_total.sum(), google_total.sum()) / max(r5_total.sum(), google_total.sum()):.3f}) "
                     f"{fmt(share_same)}")
        records.append({"unit": unit, "n_units": n_units, "jaccard": same[0], "spearman": same[1], "top": same[2],
                        "share_jaccard": share_same[0],
                        "google_floor_jaccard": google_floor[0], "r5_floor_jaccard": r5_floor[0], "reading": reading})
        if unit.startswith("hex"):
            hex_table = pd.concat([google_total.rename("google_m"), r5_total.rename("r5_m")], axis=1).fillna(0.0)
            hex_table.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_hex_totals.csv", index_label="hex_id")
    lines += ["", f"R5 vs Google weighted Jaccard by number of pairs (mean of {CURVE_REPEATS} random subsets; all "
              f"{len(draw_nos)} = the line above): rising = street-level noise averaging out, flat = systematic"]
    for unit, (unit_of, r5_set, google_set) in units.items():
        parts = []
        for size in CURVE_SIZES:
            values = []
            for _ in range(CURVE_REPEATS):
                subset = list(rng.choice(draw_nos, size=size, replace=False))
                values.append(compare(totals(google_set, subset, unit_of), totals(r5_set, subset, unit_of))[0])
            parts.append(f"{size} {np.mean(values):.3f}")
        lines.append(f"  {unit}: " + ", ".join(parts))
    pd.DataFrame(records).to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_table.csv", index=False)
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main()
