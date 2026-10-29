"""Does stock R5 walk where Google's default route walks? (painted-area overlap of the walking parts)

Claim under test (concepts/transit.md TRN-12, T7 i; DESIGN.md Q22): path, for the foot-traffic output, is
predicted by stock R5. The user's measure (2026-10-18): only the walking matters (access, transfer and egress
walks, or the whole walk on walk-only trips); stations count only through the walks that start or end there.
Paint each route's walking with a brush of width BRUSH_WIDTH_M and compare the painted areas. Where the
pipeline would rely on it: the path output (foot traffic on streets), not yet built.

Measure (user, 2026-10-18): overlap = area painted by both / area painted by either, pooled over pairs (sum of
intersections / sum of unions, so long walks weigh more). Judged at brush width 100 m (user: twice the hex
radius, HEX_DIAMETER_M 100 -> radius 50 m -> 100 m); also reported at 10, 25 and 50 m (user: all ranges,
none is supported yet). Rule (user, 2026-10-18): stock R5's path is good enough if the pooled overlap at
100 m is >= 0.90. Also reported, no verdict: per-pair median, share of pairs >= 0.90, by group (both walk only,
both transit, walk-or-transit disagree).

Geometry. Google: the steps carry no polylines (field mask), so the default route's polyline is cut at each
ride's board and alight stop (located along the line in order, after the previous cut); walking = the parts
outside the rides. Check: cut walking length vs the route table's walk_m (pooled ratio, median per pair).
R5: stock R5's choice (arm B of diagnostics/transit_preference_arms.py, w = 1: walk only or caps 1, 2, 8 by
arrival, ties to fewer rides) gives its stops; each walk leg (origin -> first board stop, alight -> next board
stop if different, last alight stop -> destination; or origin -> destination when walking) is routed walk-only
in r5py (DetailedItineraries, pairwise, WALK_SPEED_KMH) for its street geometry. R5's own access/egress inside
the transit search may link to the street differently; stated, not corrected. Areas in EPSG:7855 (GDA2020 MGA 55).

Conclusion (run 2026-10-18; 1,246 scored pairs, 2,831 R5 walk legs all routed): FAILS the user's rule.
Pooled overlap at 100 m 0.338 (per pair median 0.381; 0.6% of pairs >= 0.90); 50 m 0.272, 25 m 0.215,
10 m 0.144. By group at 100 m: both transit 0.359, both walk only 0.507, walk-or-transit disagree 0.100.
Check: Google's walking cut from the polyline is 1.040x the route table's walk_m pooled (median 1.029, 78%
within 10%). R5 walks 1.50x Google's metres pooled (median per pair 1,010 vs 702 m): Google's preference for
less walking (T7 h) shows here. Even walk-only pairs, where lengths agree, overlap only ~0.5 at 100 m: on a
street grid many near-equal paths exist and the two routers take different streets (Hausdorff 90-260 m on
the pairs read), so the 90% rule may be out of reach for any router that is not Google's own.

Inputs (read only): raw Google answers, route table and split in outputs/transit_validation/; saved data of
transit_preference_arms (routes, walk-only seconds) and transit_stop_match (R5 stop table); pairs file; the
cleaned GTFS copies and OSM extract (one r5py network). Self-contained (CLAUDE.md D1). No paid API calls. Saved
data (R5 walk-leg geometries) is reused if it exists and says so. The test half is not read.
"""
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
GTFS_CLEANED_DIR = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
GOOGLE_ROUTES_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv"
GOOGLE_RAW_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
ARMS_ROUTES_PATH = DIAGNOSTIC_DATA_DIR / "transit_preference_arms_20261017_routes.csv"
ARMS_WALK_PATH = DIAGNOSTIC_DATA_DIR / "transit_preference_arms_20261017_walk.csv"
R5_STOPS_PATH = DIAGNOSTIC_DATA_DIR / "transit_stop_match_20261018_r5_stops.csv"
NAME = "transit_walk_overlap"
R5_WALKS_SUFFIX = "_r5_walks.csv"               # saved data: R5 walk-leg geometries (WKT, EPSG:4326)

# --- values ----------------------------------------------------------------------------------------
R5_MAX_MEMORY = "7G"
WINDOW_DATE = datetime.date(2026, 10, 21)       # config.TRANSIT_WINDOW_DATE
WALK_ONLY_HOUR = 12                             # walk-only departure hour (time does not matter)
WALK_SPEED_KMH = 4.16                           # config.WALK_SPEED_KMH (WLK-1)
MAX_TIME_MIN = 180                              # walk legs up to ~12 km
TRAIN_HALF = "train"
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]   # TRN-11
DEFAULT_LABEL = "DEFAULT_ROUTE"
STOCK_W = 1.0
RIDE_CAPS = [1, 2, 8]
TIE_S_PER_RIDE = 1e-6                           # as transit_preference_arms.py
GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:7855"                        # GDA2020 / MGA zone 55
POLYLINE_PRECISION = 1e5                        # Google's encoded polyline
HEX_DIAMETER_M = 100                            # config.HEX_DIAMETER_M (vertex to vertex)
JUDGED_WIDTH_M = HEX_DIAMETER_M                 # user: twice the hex radius
BRUSH_WIDTHS_M = [10, 25, 50, JUDGED_WIDTH_M]
OVERLAP_RULE = 0.90                             # user, 2026-10-18
MIN_LEG_M = 1.0                                 # walk legs shorter than this are skipped (same point)

sys.argv += ["--max-memory", R5_MAX_MEMORY]     # r5py reads its JVM settings at import


def newest(suffix):
    files = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*{suffix}"))
    return files[-1] if files else None


def decode_polyline(encoded):
    """Google's encoded polyline -> list of (lon, lat)."""
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


# === Google: walking parts of the default route ====================================================
def google_walks(draw_nos, to_metric):
    """Per pair: list of walking LineStrings (metric) cut from the default route's polyline."""
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


# === R5: stock choice and its walk legs ============================================================
def stock_choice(pair_routes_df, walk_s):
    """Stock R5's pick among walk only and caps 1, 2, 8 at w = 1 (arm B): route_id, '' for walk only."""
    best = ("", walk_s)
    for cap in RIDE_CAPS:
        row = pair_routes_df[pair_routes_df.cap == cap]
        if row.empty or np.isnan(row.transit_s.iloc[0]):
            continue
        row = row.iloc[0]
        time_s = row.transit_s - row.request_s + row.dep_s + row.rides * TIE_S_PER_RIDE
        if time_s < best[1]:
            best = (row.route_id, time_s)
    return best[0]


def r5_walk_legs(pairs_df, choices, stops_df):
    """Walk legs (leg id, draw_no, from lat/lon, to lat/lon) for each pair's stock choice."""
    legs = []
    for pair in pairs_df.itertuples(index=False):
        route_id = choices.get(pair.draw_no)
        if route_id is None:
            continue
        points = [(pair.origin_lat, pair.origin_lon)]
        if route_id:
            _, boards, alights = (part.split("+") for part in route_id.split("|"))
            for board, alight in zip(boards, alights):
                points += [(stops_df.loc[int(board)].lat, stops_df.loc[int(board)].lon),
                           (stops_df.loc[int(alight)].lat, stops_df.loc[int(alight)].lon)]
        points.append((pair.dest_lat, pair.dest_lon))
        for k, (start, stop) in enumerate(zip(points[0::2], points[1::2])):   # walk legs between rides
            if start != stop:
                legs.append({"leg_id": f"{pair.draw_no}_{k}", "draw_no": pair.draw_no,
                             "from_lat": start[0], "from_lon": start[1], "to_lat": stop[0], "to_lon": stop[1]})
    return pd.DataFrame(legs)


def route_walk_legs(legs_df, out_path):
    """Walk-only geometry per leg from r5py DetailedItineraries (pairwise); saved as WKT."""
    import geopandas as gpd
    from r5py import DetailedItineraries, TransportMode, TransportNetwork
    network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
    origins = gpd.GeoDataFrame({"id": legs_df.leg_id.values}, crs=GEOGRAPHIC_CRS,
                               geometry=gpd.points_from_xy(legs_df.from_lon, legs_df.from_lat))
    destinations = gpd.GeoDataFrame({"id": legs_df.leg_id.values}, crs=GEOGRAPHIC_CRS,
                                    geometry=gpd.points_from_xy(legs_df.to_lon, legs_df.to_lat))
    departure = datetime.datetime.combine(WINDOW_DATE, datetime.time(WALK_ONLY_HOUR))
    di_gdf = DetailedItineraries(network, origins=origins, destinations=destinations, departure=departure,
                                 transport_modes=[TransportMode.WALK], speed_walking=WALK_SPEED_KMH,
                                 max_time=datetime.timedelta(minutes=MAX_TIME_MIN))
    di_gdf = di_gdf[di_gdf.geometry.notna() & ~di_gdf.geometry.is_empty]
    pd.DataFrame({"leg_id": di_gdf.from_id.values, "geometry_wkt": di_gdf.geometry.to_wkt().values}).to_csv(out_path, index=False)


# === painting ======================================================================================
def overlap_areas(google_lines, r5_lines, width_m):
    """(intersection, union, Google area, R5 area) of the two brushes, m2."""
    from shapely.ops import unary_union
    google_paint = unary_union([line.buffer(width_m / 2) for line in google_lines]) if google_lines else None
    r5_paint = unary_union([line.buffer(width_m / 2) for line in r5_lines]) if r5_lines else None
    if google_paint is None and r5_paint is None:
        return 0.0, 0.0, 0.0, 0.0
    if google_paint is None or r5_paint is None:
        paint = google_paint or r5_paint
        return 0.0, paint.area, (google_paint.area if google_paint else 0.0), (r5_paint.area if r5_paint else 0.0)
    return (google_paint.intersection(r5_paint).area, google_paint.union(r5_paint).area,
            google_paint.area, r5_paint.area)


def main():
    from pyproj import Transformer
    from shapely import wkt
    from shapely.ops import transform
    run_date = datetime.date.today().strftime("%Y%m%d")
    out_prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}"
    lines = [f"{NAME} run {run_date}"]
    transformer = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)

    split_df = pd.read_csv(SPLIT_PATH)
    train_nos = set(split_df[split_df.half == TRAIN_HALF].draw_no)
    pairs_df = pd.read_csv(PAIRS_PATH)
    pairs_df = pairs_df[pairs_df.draw_no.isin(train_nos)].sort_values("draw_no")
    google_df = pd.read_csv(GOOGLE_ROUTES_PATH)
    default_df = google_df[google_df.is_default & google_df.draw_no.isin(train_nos)].set_index("draw_no")
    arms_df = pd.read_csv(ARMS_ROUTES_PATH)
    stock_df = arms_df[arms_df.walk_weight == STOCK_W]
    walk_s = pd.read_csv(ARMS_WALK_PATH).set_index("draw_no").walk_s
    stops_df = pd.read_csv(R5_STOPS_PATH).set_index("stop")

    # scored pairs: as the arms run (default in scope, R5 present)
    choices = {}
    for draw_no, pair_routes_df in stock_df.groupby("draw_no"):
        if draw_no in default_df.index and default_df.loc[draw_no, "route_scope"] in GOOGLE_SCOPES:
            choice = stock_choice(pair_routes_df, float(walk_s.get(draw_no, np.inf)))
            if choice != "" or np.isfinite(walk_s.get(draw_no, np.inf)):
                choices[draw_no] = choice
    lines.append(f"scored training pairs: {len(choices)}")

    walks_path = newest(R5_WALKS_SUFFIX)
    legs_df = r5_walk_legs(pairs_df, choices, stops_df)
    if walks_path is None:
        walks_path = Path(f"{out_prefix}{R5_WALKS_SUFFIX}")
        route_walk_legs(legs_df, walks_path)
    else:
        lines.append(f"reusing R5 walk legs {walks_path.name}")
    r5_walks_df = pd.read_csv(walks_path).merge(legs_df[["leg_id", "draw_no"]], on="leg_id")
    lines.append(f"R5 walk legs: {len(legs_df)} wanted, {r5_walks_df.leg_id.nunique()} routed")
    to_metric_geom = lambda geom: transform(transformer.transform, geom)   # noqa: E731
    r5_lines = {draw_no: [to_metric_geom(wkt.loads(text)) for text in group.geometry_wkt]
                for draw_no, group in r5_walks_df.groupby("draw_no")}

    google_lines = google_walks(set(choices), lambda lon, lat: transformer.transform(lon, lat))

    # check: Google's cut walking length vs the route table's walk_m
    cut_m = pd.Series({d: sum(line.length for line in google_lines.get(d, [])) for d in choices})
    table_m = default_df.walk_m.reindex(cut_m.index)
    ratio = cut_m / table_m.replace(0, np.nan)
    lines.append(f"check, Google walking length cut from the polyline / route table walk_m: pooled "
                 f"{cut_m.sum() / table_m.sum():.3f}, median per pair {ratio.median():.3f}, within 10% "
                 f"{((ratio - 1).abs() <= 0.10).mean():.3f}")
    r5_m = pd.Series({d: sum(line.length for line in r5_lines.get(d, [])) for d in choices})
    lines.append(f"walking metres, pooled: Google {cut_m.sum() / 1000:.0f} km, R5 {r5_m.sum() / 1000:.0f} km "
                 f"(ratio {r5_m.sum() / cut_m.sum():.3f}); median per pair Google {cut_m.median():.0f} m, R5 {r5_m.median():.0f} m")

    records = []
    for draw_no, choice in choices.items():
        record = {"draw_no": draw_no, "google_walk_only": bool(default_df.loc[draw_no, "is_walk_only"]),
                  "r5_walk_only": choice == "", "google_walk_m": cut_m[draw_no], "r5_walk_m": r5_m[draw_no]}
        for width_m in BRUSH_WIDTHS_M:
            inter, union, google_area, r5_area = overlap_areas(google_lines.get(draw_no, []), r5_lines.get(draw_no, []), width_m)
            record.update({f"inter_{width_m}": inter, f"union_{width_m}": union,
                           f"overlap_{width_m}": inter / union if union > 0 else np.nan})
        records.append(record)
    result_df = pd.DataFrame(records)
    result_df["group"] = np.select(
        [result_df.google_walk_only & result_df.r5_walk_only, ~result_df.google_walk_only & ~result_df.r5_walk_only],
        ["both walk only", "both transit"], "walk-or-transit disagree")
    result_df.to_csv(f"{out_prefix}_pairs.csv", index=False)

    lines += ["", "overlap = painted by both / painted by either (pooled = sum over pairs)"]
    for width_m in BRUSH_WIDTHS_M:
        pooled = result_df[f"inter_{width_m}"].sum() / result_df[f"union_{width_m}"].sum()
        per_pair = result_df[f"overlap_{width_m}"]
        lines.append(f"brush {width_m:>3} m: pooled {pooled:.3f}; per pair median {per_pair.median():.3f}, "
                     f"mean {per_pair.mean():.3f}, share >= {OVERLAP_RULE:.2f} {(per_pair >= OVERLAP_RULE).mean():.3f}")
        for group, group_df in result_df.groupby("group"):
            lines.append(f"    {group} ({len(group_df)}): pooled "
                         f"{group_df[f'inter_{width_m}'].sum() / group_df[f'union_{width_m}'].sum():.3f}, "
                         f"median {group_df[f'overlap_{width_m}'].median():.3f}")
    judged = result_df[f"inter_{JUDGED_WIDTH_M}"].sum() / result_df[f"union_{JUDGED_WIDTH_M}"].sum()
    lines += ["", f"user's rule (pooled overlap at {JUDGED_WIDTH_M} m >= {OVERLAP_RULE:.2f}): "
              + ("PASSES" if judged >= OVERLAP_RULE else "FAILS") + f" ({judged:.3f})"]
    summary = "\n".join(lines)
    Path(f"{out_prefix}_summary.txt").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
