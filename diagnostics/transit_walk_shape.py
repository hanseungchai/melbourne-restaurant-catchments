"""Where R5 and Google walk different streets, what shape is Google's walk? (turns, distance from the straight line)

Claim explored (docs/musings.md 2026-10-22 "Paths in aggregate"; concepts/transit.md TRN-12): on a street grid many
near-equal walks exist and the two routers break ties differently; Google is said to keep a "middle" pattern
(user's experience, illustration), neither the fewest turns (one L) nor a zigzag. Candidate causes (Claude's): ties
broken toward the straight line, a main-road preference, or arbitrary ties. Where the pipeline would rely on it: the
path output (foot traffic, FRM-20), not built. Report only, no pass/fail: Claude's rule, not user-approved.

Data (saved geometry only; no R5, no JVM, no API calls): transit_walk_overlap's R5 walk legs (stock R5, arm B at
w = 1, routed walk-only by r5py DetailedItineraries at 4.16 km/h; training half, 1,246 scored pairs, 2,831 legs) and
its pair table; Google's default route polyline cut into walking parts at each ride's stops (copied from
transit_walk_overlap.py). The R5 legs are stock R5's choice, not the frozen model's (P1-P3 change stops and waits,
not street geometry); stated, not redone.

Legs compared: a Google walk leg and an R5 walk leg of the same pair whose start points and end points both lie
within MATCH_M (50 m, the hex radius) of each other: same endpoints, so differences are street choice, not route
choice. Leg type from Google's position (walk only / access / transfer / egress). "Differ" = Hausdorff distance >
DIFFER_M (25 m). Grid angle: the mode of segment bearings mod 90 over all R5 legs (length-weighted, 1 degree bins);
coordinates rotated by it so dx, dy run along the street grid.
Measures per leg: length, ratio Google / R5; detour (length / chord); turns > TURN_DEG (27, R5's straight-on
threshold) after simplifying at 5 m and 10 m; fewest possible turns (1 if both grid components > AXIS_MIN_M, else
0); max and mean distance from the chord, and the L position p = max distance / (|dx| |dy| / chord), the max
distance of the one-turn L (0 = on the straight line, 1 = the L), on diagonal legs only. Per pair: painted overlap
at 100 m (F1: reproduces transit_walk_overlap's 0.338), 150 and 200 m; hex scale: Jaccard of the project hexes
the walks pass through (points every HEX_STEP_M to the nearest hex centroid), pooled.
Readings, written before the run (Claude's): on diagonal legs that differ,
  tie toward the straight line: Google's median p at least 0.10 below R5's, with Google's turns >= R5's;
  main-road preference: Google's turns fewer than R5's and its p not lower, its walk longer (median ratio > 1.03);
  arbitrary ties: median p within 0.10 and turns within 0.5 of each other, ratio within 3%.
  Mixed readings are reported as mixed.
Added after the first run (2026-10-22, Claude's, written before these results): (a) R5 is ~25 m longer than Google
on matched legs at every leg length (median 27 m under 100 m legs, 27 m at 400-800 m): an end effect (R5's
point-to-street connectors in its geometry, Google's cut at the stop's projection), so the length ratio cannot carry
the main-road criterion; turns, chord distances and p are also reported with TRIMS_M (30 m) cut from each end of
both lines (detour is not meaningful once trimmed). (b) Main-road share: the share of a leg's points (every
ROAD_STEP_M, ends trimmed 30 m) within MAIN_NEAR_M (15 m, covering separately mapped sidewalks) of an OSM way tagged
trunk / primary / secondary / tertiary (or their links). Reading: main-road preference if, on diagonal legs that
differ, Google's mean share exceeds R5's by >= ROAD_SHARE_GAP (0.10); within 0.05 = no road-class pattern.
Checks: (F1) the pooled 100 m overlap equals transit_walk_overlap's 0.338 (3 decimals); (F2) every R5 leg id in
the saved file parses to a scored pair.

Conclusion (run 2026-10-22, autonomous 69th; report only, Claude's rules): F1 PASS (0.338), F2 2,831 / 2,831.
  Scale does not rescue overlap: pooled 100 m 0.338, 150 m 0.385, 200 m 0.422; hexes 0.327 (both transit 0.348,
  walk only 0.498, walk-or-transit disagree 0.096). Same-endpoint legs: 732 of 2,766 Google walk legs match an R5
  leg (egress 369, access 268, transfer 64, walk only 31); 519 differ (Hausdorff > 25 m; median 42 m). 287 R5 legs
  multi-part, 83 left out (parts do not chain).
  Shape, diagonal legs that differ, ends trimmed 30 m (283): Google takes fewer turns (above the fewest possible:
  Google 1.37, R5 2.38 at 10 m; Google fewer on 0.61 of legs, equal 0.22, more 0.17) and sits nearer the L than R5
  (p median 0.69 vs 0.61; Google nearer the straight line on 0.37 of legs). Baseline on legs where both take the same
  streets: R5 +0.25 turns (OSM geometry: sidewalks, crossing jogs), so about 0.6 of R5's excess is street choice.
  Walk only (29) the strongest: turns 2.9 vs 5.4, p 0.82 vs 0.54. Transfers (22) the exception (Google p lower).
  Length: R5 longer by a roughly constant 25-30 m at every leg length (end effect), so the length ratio (0.93) is
  not read. Main-road share (diagonal, 283): Google 0.523, R5 0.476, gap +0.047 (Google higher on 0.50, lower on
  0.34): inside the 0.05 "no road-class pattern" band, at its edge; walk only +0.127 (n 29).
  Readings by the pre-written rules: shape "mixed" (not toward the straight line; main-road rule unreadable on
  length; not arbitrary: turn gap -1.0); road class "no pattern" (borderline). Descriptive (Claude's): Google is
  turn-averse, typically a Z (median 2 turns) between the one-turn L and R5's staircase (median 3-4); the straight-
  line tie-break candidate is contradicted (R5 is the one nearer the straight line). A small walk turn cost (the
  musing's patch idea) fits this better than a straight-line tie-break; untested.
  Length share (asked by the user during the run; walking only, rides excluded; share of one router's walk metres
  within d of the other's walk, pooled): both transit (1,126 pairs; R5 1,219 km, Google 855 km) R5 on Google 0.340 /
  0.444 / 0.526 at 10 / 25 / 50 m, Google on R5 0.454 / 0.566 / 0.641; per pair at 25 m median 0.482, 0.485 of pairs
  >= 0.5, 0.099 >= 0.9. Walk only (64) 0.634 / 0.642 at 25 m (median 0.744); walk-or-transit disagree (56) 0.096 / 0.262.

Inputs (read only): transit_walk_overlap_20261018_{r5_walks, pairs}.csv, the raw Google answers, the hex grid.
Self-contained (CLAUDE.md D1). Usage: `python transit_walk_shape.py`.
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
GOOGLE_RAW_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl"
HEX_GRID_PATH = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT / f"hex_grid_{SUBJECT}.gpkg"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
R5_WALKS_PATH = DIAGNOSTIC_DATA_DIR / "transit_walk_overlap_20261018_r5_walks.csv"
OVERLAP_PAIRS_PATH = DIAGNOSTIC_DATA_DIR / "transit_walk_overlap_20261018_pairs.csv"
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
NAME = "transit_walk_shape"

# --- values ----------------------------------------------------------------------------------------
DEFAULT_LABEL = "DEFAULT_ROUTE"
GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:7855"                        # GDA2020 / MGA zone 55
POLYLINE_PRECISION = 1e5                        # Google's encoded polyline
MIN_LEG_M = 1.0                                 # as transit_walk_overlap.py
F1_BRUSH_M = 100
F1_EXPECTED = 0.338                             # transit_walk_overlap 20261018, pooled at 100 m
BRUSH_WIDTHS_M = [F1_BRUSH_M, 150, 200]
MATCH_M = 50.0                                  # both ends within this: the same leg (hex radius)
DIFFER_M = 25.0                                 # Hausdorff above this: the two take different streets
TURN_DEG = 27.0                                 # R5's straight-on threshold
SIMPLIFY_TOLERANCES_M = [5.0, 10.0]
AXIS_MIN_M = 50.0                               # a grid component above this needs a turn
MIN_SEGMENT_M = 20.0                            # segments counted toward the grid angle
CHORD_STEP_M = 5.0                              # sampling step for distances from the chord
SHARE_STEP_M = 5.0                              # sampling step for the length share on the other's path
DECOMPOSITION_TOLERANCE_M = 25
SHARE_TOLERANCES_M = [10, 25, 50]               # a walk metre counts as shared within this of the other's walk
HEX_STEP_M = 10.0                               # sampling step for the hexes a walk passes through
HEX_PAD_DEG = 0.01                              # bbox pad when reading hex centroids
READING_P_GAP = 0.10
READING_TURN_GAP = 0.5
READING_RATIO = 0.03
TRIMS_M = [0.0, 30.0]                           # metres cut from each end of both lines (added after the first run)
MAIN_HIGHWAYS = {"trunk", "primary", "secondary", "tertiary", "trunk_link", "primary_link", "secondary_link",
                 "tertiary_link"}
MAIN_NEAR_M = 15.0
ROAD_STEP_M = 10.0
ROAD_SHARE_GAP = 0.10
ROAD_SHARE_NONE = 0.05
ROAD_TRIM_M = 30.0
CHAIN_GAP_M = 1.0                               # multi-part R5 legs whose parts chain within this are joined


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


def google_walks(draw_nos, to_metric):
    """Per pair: walking LineStrings (metric) cut from the default route's polyline (from transit_walk_overlap.py)."""
    from shapely.geometry import LineString, Point
    from shapely.ops import substring
    walks = {}
    with open(GOOGLE_RAW_PATH, encoding="utf-8") as raw_file:
        for line in raw_file:
            answer = json.loads(line)
            if answer["draw_no"] not in draw_nos:
                continue
            for route in answer["resp"].get("routes", []):
                if DEFAULT_LABEL not in route.get("routeLabels", []):
                    continue
                coords = [to_metric(lon, lat) for lon, lat in decode_polyline(route["polyline"]["encodedPolyline"])]
                route_line = LineString(coords)
                rides = [step["transitDetails"]["stopDetails"] for leg in route.get("legs", [])
                         for step in leg.get("steps", []) if "transitDetails" in step]
                cuts, position = [0.0], 0.0
                for stops in rides:
                    for end in ("departureStop", "arrivalStop"):
                        lat_lng = stops[end]["location"]["latLng"]
                        point = Point(to_metric(lat_lng["longitude"], lat_lng["latitude"]))
                        rest = substring(route_line, position, route_line.length)
                        located = position + (rest.project(point) if rest.length > 0 else 0.0)
                        cuts.append(located)
                        position = located
                cuts.append(route_line.length)
                walk_lines = []
                for start, stop in zip(cuts[0::2], cuts[1::2]):     # walk, ride, walk, ride, ..., walk
                    if stop - start >= MIN_LEG_M:
                        walk_lines.append(substring(route_line, start, stop))
                walks[answer["draw_no"]] = walk_lines
    return walks


def overlap_areas(google_lines, r5_lines, width_m):
    """(intersection, union) of the two brushes, m2 (as transit_walk_overlap.py)."""
    from shapely.ops import unary_union
    google_paint = unary_union([line.buffer(width_m / 2) for line in google_lines]) if google_lines else None
    r5_paint = unary_union([line.buffer(width_m / 2) for line in r5_lines]) if r5_lines else None
    if google_paint is None and r5_paint is None:
        return 0.0, 0.0
    if google_paint is None or r5_paint is None:
        return 0.0, (google_paint or r5_paint).area
    return google_paint.intersection(r5_paint).area, google_paint.union(r5_paint).area


# === shape ==========================================================================================
def as_single_line(geometry):
    """A LineString for shape measures: zero-length parts dropped, parts joined in order if they chain within
    CHAIN_GAP_M; None if they do not (such legs are left out of the leg measures, counted)."""
    from shapely.geometry import LineString
    if geometry.geom_type == "LineString":
        return geometry
    parts = [part for part in geometry.geoms if part.length > 0]
    coords = list(parts[0].coords)
    for part in parts[1:]:
        if np.hypot(coords[-1][0] - part.coords[0][0], coords[-1][1] - part.coords[0][1]) > CHAIN_GAP_M:
            return None
        coords += list(part.coords)[1:]
    return LineString(coords)


def grid_angle_deg(lines):
    """Mode of segment bearings mod 90 (length-weighted, 1 degree bins) over the given lines."""
    weights = np.zeros(90)
    for line in lines:
        xy = np.asarray(line.simplify(SIMPLIFY_TOLERANCES_M[0]).coords)
        d = np.diff(xy, axis=0)
        lengths = np.hypot(d[:, 0], d[:, 1])
        keep = lengths >= MIN_SEGMENT_M
        bearings = np.degrees(np.arctan2(d[keep, 1], d[keep, 0])) % 90
        np.add.at(weights, bearings.astype(int) % 90, lengths[keep])
    return float(np.argmax(weights)) + 0.5


def turn_count(line, tolerance_m):
    xy = np.asarray(line.simplify(tolerance_m).coords)
    d = np.diff(xy, axis=0)
    d = d[np.hypot(d[:, 0], d[:, 1]) > 0]
    if len(d) < 2:
        return 0
    headings = np.arctan2(d[:, 1], d[:, 0])
    change = np.degrees(np.abs((np.diff(headings) + np.pi) % (2 * np.pi) - np.pi))
    return int((change > TURN_DEG).sum())


def chord_distances(line, start, end):
    """(max, mean) distance of points along the line from the chord start -> end, m."""
    from shapely.geometry import LineString
    chord = LineString([start, end])
    steps = np.arange(0, line.length + CHORD_STEP_M, CHORD_STEP_M).clip(max=line.length)
    points = [line.interpolate(s) for s in steps]
    dists = np.array([chord.distance(p) for p in points])
    return float(dists.max()), float(dists.mean())


def trimmed(line, trim_m):
    """The line without trim_m at each end (R5's point-to-street connectors); None if too short."""
    from shapely.ops import substring
    if trim_m == 0:
        return line
    return substring(line, trim_m, line.length - trim_m) if line.length > 2 * trim_m + MIN_SEGMENT_M else None


def leg_shape(line, start, end, cos_a, sin_a):
    chord_m = float(np.hypot(end[0] - start[0], end[1] - start[1]))
    dx, dy = end[0] - start[0], end[1] - start[1]
    grid_x, grid_y = abs(dx * cos_a + dy * sin_a), abs(-dx * sin_a + dy * cos_a)
    is_diagonal = min(grid_x, grid_y) > AXIS_MIN_M
    l_max = grid_x * grid_y / chord_m if chord_m > 0 else np.nan
    max_m, mean_m = chord_distances(line, start, end)
    record = {"length_m": line.length, "chord_m": chord_m, "detour": line.length / chord_m if chord_m > 0 else np.nan,
              "max_dev_m": max_m, "mean_dev_m": mean_m, "is_diagonal": is_diagonal, "min_turns": int(is_diagonal),
              "p_l": max_m / l_max if is_diagonal else np.nan}
    for tolerance in SIMPLIFY_TOLERANCES_M:
        record[f"turns_{tolerance:.0f}"] = turn_count(line, tolerance)
    return record


def leg_type(k, n_legs, is_walk_only):
    if is_walk_only:
        return "walk only"
    return "access" if k == 0 else "egress" if k == n_legs - 1 else "transfer"


def match_legs(google_lines, r5_lines):
    """[(google index, r5 line)] where both ends of an R5 leg lie within MATCH_M of the Google leg's ends."""
    pairs = []
    for i, g_line in enumerate(google_lines):
        g_start, g_end = np.asarray(g_line.coords[0]), np.asarray(g_line.coords[-1])
        best = None
        for r_line in r5_lines:
            off = max(np.hypot(*(np.asarray(r_line.coords[0]) - g_start)), np.hypot(*(np.asarray(r_line.coords[-1]) - g_end)))
            if off <= MATCH_M and (best is None or off < best[0]):
                best = (off, r_line)
        if best is not None:
            pairs.append((i, best[1]))
    return pairs


# === length share =================================================================================
def length_within(lines_a, lines_b, tolerance_m):
    """(metres of lines_a within tolerance_m of lines_b, metres of lines_a), sampled every SHARE_STEP_M."""
    from shapely.ops import unary_union
    total_m = sum(line.length for line in lines_a)
    if not lines_a or not lines_b:
        return 0.0, total_m
    zone = unary_union([line.buffer(tolerance_m) for line in lines_b])
    within_m = 0.0
    for line in [part for line in lines_a for part in getattr(line, "geoms", [line])]:
        n_steps = max(int(np.ceil(line.length / SHARE_STEP_M)), 1)
        midpoints = [line.interpolate((k + 0.5) * line.length / n_steps) for k in range(n_steps)]
        within_m += line.length * np.mean([zone.contains(point) for point in midpoints])
    return within_m, total_m


# === hexes =========================================================================================
def hex_lookup(all_lines, to_geographic):
    """KD-tree over the hex centroids (metric) inside the lines' bbox; returns (tree, hex ids)."""
    import pyogrio
    from scipy.spatial import cKDTree
    from pyproj import Transformer
    xs = np.concatenate([np.asarray(line.coords)[:, 0] for line in all_lines])
    ys = np.concatenate([np.asarray(line.coords)[:, 1] for line in all_lines])
    lon_min, lat_min = to_geographic(xs.min(), ys.min())
    lon_max, lat_max = to_geographic(xs.max(), ys.max())
    bbox = (lon_min - HEX_PAD_DEG, lat_min - HEX_PAD_DEG, lon_max + HEX_PAD_DEG, lat_max + HEX_PAD_DEG)
    hex_df = pyogrio.read_dataframe(HEX_GRID_PATH, columns=["hex_id", "centroid_lat", "centroid_lon"],
                                    bbox=bbox, read_geometry=False)
    transformer = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
    hx, hy = transformer.transform(hex_df.centroid_lon.to_numpy(), hex_df.centroid_lat.to_numpy())
    return cKDTree(np.column_stack([hx, hy])), hex_df.hex_id.to_numpy()


def hexes_of(lines, tree, hex_ids):
    points = []
    for line in [part for line in lines for part in getattr(line, "geoms", [line])]:
        for s in np.arange(0, line.length + HEX_STEP_M, HEX_STEP_M).clip(max=line.length):
            point = line.interpolate(s)
            points.append((point.x, point.y))
    if not points:
        return set()
    _, index = tree.query(np.asarray(points))
    return set(hex_ids[index])


# === road class ====================================================================================
def main_road_tree(lines, to_geographic, to_metric):
    """STRtree over OSM main-road ways (metric) inside the lines' bbox."""
    import pyogrio
    from shapely import STRtree
    from shapely.ops import transform
    xs = np.concatenate([np.asarray(line.coords)[:, 0] for line in lines])
    ys = np.concatenate([np.asarray(line.coords)[:, 1] for line in lines])
    lon_min, lat_min = to_geographic(xs.min(), ys.min())
    lon_max, lat_max = to_geographic(xs.max(), ys.max())
    bbox = (lon_min - HEX_PAD_DEG, lat_min - HEX_PAD_DEG, lon_max + HEX_PAD_DEG, lat_max + HEX_PAD_DEG)
    names = ", ".join(f"'{name}'" for name in sorted(MAIN_HIGHWAYS))
    roads_gdf = pyogrio.read_dataframe(PBF_PATH, layer="lines", columns=["highway"], bbox=bbox,
                                       where=f"highway IN ({names})")
    return STRtree([transform(to_metric, geom) for geom in roads_gdf.geometry]), len(roads_gdf)


def main_road_share(line, tree):
    steps = np.arange(0, line.length + ROAD_STEP_M, ROAD_STEP_M).clip(max=line.length)
    points = [line.interpolate(step) for step in steps]
    near = tree.query(points, predicate="dwithin", distance=MAIN_NEAR_M)
    return len(set(near[0])) / len(points) if points else np.nan


# === report =========================================================================================
def describe(legs_df, label):
    """Google beside R5 on one leg subset; the reading by the pre-written rule on its diagonal legs."""
    if legs_df.empty:
        return [f"  {label}: none"]
    diagonal = legs_df[legs_df.is_diagonal]
    ratio = legs_df.g_length_m / legs_df.r_length_m
    lines = [f"  {label}: legs {len(legs_df)} (diagonal {len(diagonal)}); length Google / R5 pooled "
             f"{legs_df.g_length_m.sum() / legs_df.r_length_m.sum():.3f}, median {ratio.median():.3f}; "
             f"median length G {legs_df.g_length_m.median():.0f} / R {legs_df.r_length_m.median():.0f} m; "
             f"Hausdorff median {legs_df.hausdorff_m.median():.0f} m"]
    for side, name in (("g", "Google"), ("r", "R5")):
        lines.append(f"    {name:6}: detour median {legs_df[f'{side}_detour'].median():.3f}; turns (5 m / 10 m) mean "
                     f"{legs_df[f'{side}_turns_5'].mean():.2f} / {legs_df[f'{side}_turns_10'].mean():.2f}, median "
                     f"{legs_df[f'{side}_turns_5'].median():.0f} / {legs_df[f'{side}_turns_10'].median():.0f}; "
                     f"max dev median {legs_df[f'{side}_max_dev_m'].median():.0f} m, mean dev median "
                     f"{legs_df[f'{side}_mean_dev_m'].median():.0f} m; L position p (diagonal) median "
                     f"{diagonal[f'{side}_p_l'].median():.2f}, quartiles {diagonal[f'{side}_p_l'].quantile(0.25):.2f}-"
                     f"{diagonal[f'{side}_p_l'].quantile(0.75):.2f}")
    if len(diagonal):
        excess_g = (diagonal.g_turns_10 - diagonal.min_turns).mean()
        excess_r = (diagonal.r_turns_10 - diagonal.min_turns).mean()
        p_gap = diagonal.g_p_l.median() - diagonal.r_p_l.median()
        turn_gap = diagonal.g_turns_10.mean() - diagonal.r_turns_10.mean()
        ratio_d = (diagonal.g_length_m / diagonal.r_length_m).median()
        closer = (diagonal.g_max_dev_m < diagonal.r_max_dev_m).mean()
        if p_gap <= -READING_P_GAP and turn_gap >= 0:
            reading = "tie toward the straight line"
        elif turn_gap < 0 and p_gap > -READING_P_GAP and ratio_d > 1 + READING_RATIO:
            reading = "main-road preference"
        elif abs(p_gap) < READING_P_GAP and abs(turn_gap) < READING_TURN_GAP and abs(ratio_d - 1) <= READING_RATIO:
            reading = "arbitrary ties"
        else:
            reading = "mixed"
        lines.append(f"    diagonal: turns above the fewest (10 m) G {excess_g:.2f} / R {excess_r:.2f}; p gap G - R "
                     f"{p_gap:+.2f}; turn gap {turn_gap:+.2f}; median ratio {ratio_d:.3f}; Google closer to the "
                     f"straight line on {closer:.2f} of legs -> reading: {reading}")
    return lines


def main():
    from pyproj import Transformer
    from shapely import wkt
    from shapely.ops import transform
    run_date = datetime.date.today().strftime("%Y%m%d")
    out_prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}"
    to_metric_t = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
    to_geo_t = Transformer.from_crs(METRIC_CRS, GEOGRAPHIC_CRS, always_xy=True)
    pairs_df = pd.read_csv(OVERLAP_PAIRS_PATH).set_index("draw_no")
    r5_df = pd.read_csv(R5_WALKS_PATH)
    r5_df["draw_no"] = r5_df.leg_id.str.split("_").str[0].astype(int)
    r5_df["k"] = r5_df.leg_id.str.split("_").str[1].astype(int)
    lines = [f"{NAME} run {run_date}: saved data {R5_WALKS_PATH.name}, {OVERLAP_PAIRS_PATH.name} (2026-10-18)",
             f"(F2) R5 legs {len(r5_df)}; on scored pairs {int(r5_df.draw_no.isin(pairs_df.index).sum())}"]
    r5_lines = {draw_no: [transform(to_metric_t.transform, wkt.loads(text)) for text in group.sort_values("k").geometry_wkt]
                for draw_no, group in r5_df.groupby("draw_no")}
    google_lines = google_walks(set(pairs_df.index), lambda lon, lat: to_metric_t.transform(lon, lat))

    pair_records = []
    for draw_no in pairs_df.index:
        record = {"draw_no": draw_no, "group": pairs_df.loc[draw_no, "group"]}
        for width_m in BRUSH_WIDTHS_M:
            record[f"inter_{width_m}"], record[f"union_{width_m}"] = overlap_areas(
                google_lines.get(draw_no, []), r5_lines.get(draw_no, []), width_m)
        pair_records.append(record)
    pair_df = pd.DataFrame(pair_records)
    f1 = pair_df[f"inter_{F1_BRUSH_M}"].sum() / pair_df[f"union_{F1_BRUSH_M}"].sum()
    lines.append(f"(F1) pooled overlap at {F1_BRUSH_M} m {f1:.3f} vs {F1_EXPECTED:.3f}: "
                 + ("PASS" if round(f1, 3) == F1_EXPECTED else "FAIL"))

    r5_single = {draw_no: [as_single_line(line) for line in group] for draw_no, group in r5_lines.items()}
    n_unchained = sum(line is None for group in r5_single.values() for line in group)
    r5_single = {draw_no: [line for line in group if line is not None] for draw_no, group in r5_single.items()}
    lines.append(f"R5 legs multi-part {sum(line.geom_type != 'LineString' for group in r5_lines.values() for line in group)}; "
                 f"parts not chaining within {CHAIN_GAP_M:.0f} m (left out of the leg measures) {n_unchained}")
    all_r5 = [line for group in r5_single.values() for line in group]
    angle = grid_angle_deg(all_r5)
    cos_a, sin_a = np.cos(np.radians(angle)), np.sin(np.radians(angle))
    lines.append(f"grid angle (mode of R5 segment bearings mod 90): {angle:.1f} deg from east")

    tree, hex_ids = hex_lookup(all_r5 + [line for group in google_lines.values() for line in group],
                               lambda x, y: to_geo_t.transform(x, y))
    hex_inter, hex_union = [], []
    for draw_no in pairs_df.index:
        g_hexes = hexes_of(google_lines.get(draw_no, []), tree, hex_ids)
        r_hexes = hexes_of(r5_lines.get(draw_no, []), tree, hex_ids)
        hex_inter.append(len(g_hexes & r_hexes))
        hex_union.append(len(g_hexes | r_hexes))
    pair_df["hex_inter"], pair_df["hex_union"] = hex_inter, hex_union

    for tolerance in SHARE_TOLERANCES_M:
        shares = [length_within(r5_lines.get(d, []), google_lines.get(d, []), tolerance) +
                  length_within(google_lines.get(d, []), r5_lines.get(d, []), tolerance) for d in pairs_df.index]
        pair_df[[f"r_on_g_{tolerance}", "r_walk_m", f"g_on_r_{tolerance}", "g_walk_m"]] = np.array(shares)

    lines += ["", "pair level, pooled over pairs (sum of intersections / sum of unions):"]
    for label, part_df in [("all", pair_df)] + list(pair_df.groupby("group")):
        parts = [f"{width_m} m {part_df[f'inter_{width_m}'].sum() / part_df[f'union_{width_m}'].sum():.3f}"
                 for width_m in BRUSH_WIDTHS_M]
        lines.append(f"  {label} ({len(part_df)}): " + ", ".join(parts)
                     + f"; hexes {part_df.hex_inter.sum() / part_df.hex_union.sum():.3f}")
    lines += ["", "length share (walking only, rides excluded): share of one router's walk metres within d of the other's "
              "walk, pooled over pairs"]
    for label, part_df in [("all", pair_df)] + list(pair_df.groupby("group")):
        parts = [f"{tolerance} m: R5 on Google {part_df[f'r_on_g_{tolerance}'].sum() / part_df.r_walk_m.sum():.3f}, "
                 f"Google on R5 {part_df[f'g_on_r_{tolerance}'].sum() / part_df.g_walk_m.sum():.3f}"
                 for tolerance in SHARE_TOLERANCES_M]
        lines.append(f"  {label} ({len(part_df)}; walk km R5 {part_df.r_walk_m.sum() / 1000:.0f}, Google "
                     f"{part_df.g_walk_m.sum() / 1000:.0f}): " + "; ".join(parts))
        per_pair = part_df.r_on_g_25 / part_df.r_walk_m.replace(0, np.nan)
        lines.append(f"      per pair at 25 m, R5 on Google: median {per_pair.median():.3f}, share of pairs >= 0.5 "
                     f"{(per_pair >= 0.5).mean():.3f}, >= 0.9 {(per_pair >= 0.9).mean():.3f}")

    leg_records, g_by_leg, r_by_leg = [], {}, {}
    n_google_legs = 0
    for draw_no in pairs_df.index:
        g_list = google_lines.get(draw_no, [])
        n_google_legs += len(g_list)
        is_walk_only = bool(pairs_df.loc[draw_no, "google_walk_only"])
        for i, r_line in match_legs(g_list, r5_single.get(draw_no, [])):
            g_line = g_list[i]
            leg_key = f"{draw_no}_{i}"
            g_by_leg[leg_key], r_by_leg[leg_key] = g_line, r_line
            start = tuple((np.asarray(g_line.coords[0]) + np.asarray(r_line.coords[0])) / 2)
            end = tuple((np.asarray(g_line.coords[-1]) + np.asarray(r_line.coords[-1])) / 2)
            for trim_m in TRIMS_M:
                g_cut, r_cut = trimmed(g_line, trim_m), trimmed(r_line, trim_m)
                if g_cut is None or r_cut is None:
                    continue
                record = {"draw_no": draw_no, "leg_key": leg_key, "trim_m": trim_m, "leg_type": leg_type(i, len(g_list), is_walk_only),
                          "hausdorff_m": g_line.hausdorff_distance(r_line)}
                g_shape, r_shape = leg_shape(g_cut, start, end, cos_a, sin_a), leg_shape(r_cut, start, end, cos_a, sin_a)
                record["is_diagonal"], record["min_turns"] = g_shape["is_diagonal"], g_shape["min_turns"]
                for key in ("length_m", "detour", "max_dev_m", "mean_dev_m", "p_l", "turns_5", "turns_10"):
                    record[f"g_{key}"], record[f"r_{key}"] = g_shape[key], r_shape[key]
                leg_records.append(record)
    legs_df = pd.DataFrame(leg_records)
    legs_df["differ"] = legs_df.hausdorff_m > DIFFER_M
    legs_df.to_csv(f"{out_prefix}_legs.csv", index=False)
    pair_df.to_csv(f"{out_prefix}_pairs.csv", index=False)
    all_df = legs_df[legs_df.trim_m == 0]
    lines += ["", f"legs: Google walk legs {n_google_legs}; matched to an R5 leg (both ends within {MATCH_M:.0f} m) "
              f"{len(all_df)} ({all_df.leg_type.value_counts().to_dict()}); differ (Hausdorff > {DIFFER_M:.0f} m) "
              f"{int(all_df.differ.sum())}"]
    # decomposition (both transit): R5 walk metres on Google's walk, split by whether the leg has a same-endpoint match
    transit_nos = set(pairs_df.index[pairs_df.group == "both transit"])
    matched_r5 = {key: r_by_leg[key] for key in r_by_leg if int(key.split("_")[0]) in transit_nos}
    on_m, matched_m = 0.0, 0.0
    for key, r_line in matched_r5.items():
        within_m, total_m = length_within([r_line], [g_by_leg[key]], DECOMPOSITION_TOLERANCE_M)
        on_m, matched_m = on_m + within_m, matched_m + total_m
    transit_df = pair_df[pair_df.group == "both transit"]
    all_on_m = transit_df[f"r_on_g_{DECOMPOSITION_TOLERANCE_M}"].sum()
    all_m = transit_df.r_walk_m.sum()
    lines += ["", f"decomposition, both transit, R5 walk metres within {DECOMPOSITION_TOLERANCE_M} m of Google's walk: "
              f"all {all_on_m / all_m:.3f} of {all_m / 1000:.0f} km; legs with a same-endpoint Google leg "
              f"{len(matched_r5)} hold {matched_m / all_m:.3f} of R5's metres, share on Google's matched leg "
              f"{on_m / matched_m:.3f}; the rest (other stops) {(all_on_m - on_m) / (all_m - matched_m):.3f} on any of "
              f"Google's walk"]

    differ_road_df = legs_df[(legs_df.trim_m == ROAD_TRIM_M) & legs_df.differ].copy()
    tree, n_roads = main_road_tree(list(r_by_leg.values()) + list(g_by_leg.values()),
                                   lambda x, y: to_geo_t.transform(x, y), to_metric_t.transform)
    differ_road_df["g_main"] = [main_road_share(trimmed(g_by_leg[key], ROAD_TRIM_M), tree) for key in differ_road_df.leg_key]
    differ_road_df["r_main"] = [main_road_share(trimmed(r_by_leg[key], ROAD_TRIM_M), tree) for key in differ_road_df.leg_key]
    lines += ["", f"main-road share (OSM ways {sorted(MAIN_HIGHWAYS)[:4]}... within {MAIN_NEAR_M:.0f} m; {n_roads} ways read), "
              f"legs that differ, ends trimmed {ROAD_TRIM_M:.0f} m:"]
    for label, part_df in [("all", differ_road_df), ("diagonal", differ_road_df[differ_road_df.is_diagonal])] +             [(kind, differ_road_df[differ_road_df.leg_type == kind]) for kind in ("walk only", "access", "transfer", "egress")]:
        gap = part_df.g_main.mean() - part_df.r_main.mean()
        lines.append(f"  {label} ({len(part_df)}): Google {part_df.g_main.mean():.3f}, R5 {part_df.r_main.mean():.3f}, "
                     f"gap {gap:+.3f}; Google higher on {(part_df.g_main > part_df.r_main).mean():.2f}, lower on "
                     f"{(part_df.g_main < part_df.r_main).mean():.2f}")
    diagonal_gap = (differ_road_df[differ_road_df.is_diagonal].g_main.mean()
                    - differ_road_df[differ_road_df.is_diagonal].r_main.mean())
    lines.append("  reading (diagonal): " + ("main-road preference" if diagonal_gap >= ROAD_SHARE_GAP else
                 "no road-class pattern" if abs(diagonal_gap) <= ROAD_SHARE_NONE else "weak / mixed"))
    legs_df = legs_df.merge(differ_road_df[["leg_key", "trim_m", "g_main", "r_main"]], on=["leg_key", "trim_m"], how="left")
    legs_df.to_csv(f"{out_prefix}_legs.csv", index=False)
    for trim_m in TRIMS_M:
        trim_df = legs_df[legs_df.trim_m == trim_m]
        lines += ["", f"===== ends trimmed {trim_m:.0f} m (legs long enough: {len(trim_df)}) =====",
                  "matched legs, all:"] + describe(trim_df, "all matched")
        lines += [f"matched legs that differ (Hausdorff > {DIFFER_M:.0f} m), by type:"]
        differ_df = trim_df[trim_df.differ]
        lines += describe(differ_df, "all that differ")
        lines += describe(differ_df[differ_df.leg_type == "walk only"], "walk only")
        lines += describe(differ_df[differ_df.leg_type != "walk only"], "transit walk legs (access / transfer / egress)")
        for leg_kind in ("access", "transfer", "egress"):
            lines += describe(differ_df[differ_df.leg_type == leg_kind], leg_kind)
    summary = "\n".join(lines)
    Path(f"{out_prefix}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main()
