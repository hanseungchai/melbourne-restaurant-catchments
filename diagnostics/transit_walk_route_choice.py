"""Would a walk-averse route choice put R5's walks where Google's are? (endpoint matching, report only)

Question (user, 2026-10-22, autonomous 69th: "what could we do to match Google's walk pattern more closely"):
transit_walk_shape.py found that on both-transit pairs only 0.180 of R5's walk metres lie on legs with the same
endpoints as a Google walk leg, and those sit 0.823 on Google's leg at 25 m; the rest sit 0.360. So street choice
can add at most ~0.03 to the pooled share; route choice (which stops) is the lever. This asks how far a walk weight
w (transit_preference_arms.py's re-rank: walk at WALK_SPEED_KMH / w, least slowed time, ties to fewer rides) moves
R5's walk legs onto Google's stops. Context: Q22 closed 2026-10-20 (user: no preference model, path dropped,
re-rank parked); this is a feasibility look for the path output (FRM-20), never the frozen time model.

Method (saved data only; no R5, no JVM, no API calls): per training pair in transit_walk_overlap's scored set,
R5's choice at each w in the arms file (copied selection rule: least of the slowed route times and w x walk-only
seconds); its walk legs' endpoints from the R5 stop table; Google default route's walk legs cut from its polyline
(copied cut), with endpoints from the ride stops' coordinates. A Google leg is matched when an R5 leg's endpoints
both lie within MATCH_M (50 m) of it. Measure: the share of Google's walk metres on matched legs, and the
predicted pooled length share at 25 m, R5 on Google = 0.823 x matched + 0.360 x unmatched (transit_walk_shape's
two rates, weighted by Google metres: a proxy, not a routed result). R5's access + egress seconds from the arms are
the slowed walk (speed / w), so not comparable across w; reported as a sanity column only.
Reading (Claude's, written before the run): worth routing for real if the best w raises the matched share of
Google's walk metres by >= 0.10 over w = 1 (predicted pooled share +0.05 or more); else not worth pursuing.

Conclusion (run 2026-10-22, autonomous 69th): NOT WORTH PURSUING by the pre-written rule. Matched share of
  Google's walk metres (1,246 pairs, 982 km): w 1.00 0.536, 1.25 0.547 (best, +0.011), 1.50 0.532, 1.75 0.513, 2.00
  0.472, 3.00 0.423; both-transit pairs alike (0.536 -> 0.417). A walk weight over R5's own candidates (caps 1, 2, 8)
  shifts R5 to routes that walk less but to other stops than Google's; it does not find Google's stops. The proxy
  column is miscalibrated: stop-coordinate matching here (0.536) is looser than transit_walk_shape's geometry-end
  matching (0.180 of R5 metres), so its predicted 0.608 at w = 1 overshoots the measured 0.444; only the trend
  across w is read. With street choice capped at ~+0.03 (transit_walk_shape decomposition) and this at +0.01, the
  remaining gap is route choice that R5's candidates (fastest per ride cap) do not reproduce, not a walk tunable.

Inputs (read only): transit_preference_arms_20261017_{routes, walk}.csv, transit_stop_match_20261018_r5_stops.csv,
transit_walk_overlap_20261018_pairs.csv, the pairs file, the raw Google answers. Self-contained (CLAUDE.md D1).
Usage: `python transit_walk_route_choice.py`.
"""
import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
PAIRS_PATH = SUBJECT_DIR / f"transit_pairs_{FILE_TAG}.csv"
GOOGLE_RAW_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
ARMS_ROUTES_PATH = DIAGNOSTIC_DATA_DIR / "transit_preference_arms_20261017_routes.csv"
ARMS_WALK_PATH = DIAGNOSTIC_DATA_DIR / "transit_preference_arms_20261017_walk.csv"
R5_STOPS_PATH = DIAGNOSTIC_DATA_DIR / "transit_stop_match_20261018_r5_stops.csv"
OVERLAP_PAIRS_PATH = DIAGNOSTIC_DATA_DIR / "transit_walk_overlap_20261018_pairs.csv"
NAME = "transit_walk_route_choice"

# --- values ----------------------------------------------------------------------------------------
DEFAULT_LABEL = "DEFAULT_ROUTE"
GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:7855"
POLYLINE_PRECISION = 1e5
MIN_LEG_M = 1.0
RIDE_CAPS = [1, 2, 8]
TIE_S_PER_RIDE = 1e-6                           # as transit_preference_arms.py
MATCH_M = 50.0
MATCHED_RATE = 0.823                            # transit_walk_shape 20261022: matched legs, R5 on Google at 25 m
UNMATCHED_RATE = 0.360                          # ... the rest
READING_GAIN = 0.10


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


def google_walk_legs(pairs_df, to_metric):
    """Per pair: [(start xy, end xy, metres)] of the default route's walk legs; ends at origin / ride stops / dest,
    metres from the polyline cut (as transit_walk_overlap.google_walks)."""
    from shapely.geometry import LineString, Point
    from shapely.ops import substring
    legs = {}
    with open(GOOGLE_RAW_PATH, encoding="utf-8") as raw_file:
        for line in raw_file:
            answer = json.loads(line)
            draw_no = answer["draw_no"]
            if draw_no not in pairs_df.index:
                continue
            for route in answer["resp"].get("routes", []):
                if DEFAULT_LABEL not in route.get("routeLabels", []):
                    continue
                route_line = LineString([to_metric(lon, lat) for lon, lat in decode_polyline(route["polyline"]["encodedPolyline"])])
                rides = [step["transitDetails"]["stopDetails"] for leg in route.get("legs", [])
                         for step in leg.get("steps", []) if "transitDetails" in step]
                pair = pairs_df.loc[draw_no]
                ends = [to_metric(pair.origin_lon, pair.origin_lat)]
                cuts, position = [0.0], 0.0
                for stops in rides:
                    for end in ("departureStop", "arrivalStop"):
                        lat_lng = stops[end]["location"]["latLng"]
                        xy = to_metric(lat_lng["longitude"], lat_lng["latitude"])
                        ends.append(xy)
                        rest = substring(route_line, position, route_line.length)
                        position += rest.project(Point(xy)) if rest.length > 0 else 0.0
                        cuts.append(position)
                ends.append(to_metric(pair.dest_lon, pair.dest_lat))
                cuts.append(route_line.length)
                legs[draw_no] = [(np.asarray(a), np.asarray(b), stop - start)
                                 for a, b, start, stop in zip(ends[0::2], ends[1::2], cuts[0::2], cuts[1::2])
                                 if stop - start >= MIN_LEG_M]
    return legs


def choice_at(pair_routes_df, walk_s, weight):
    """R5's pick at walk weight w (transit_preference_arms arm rule, ties to fewer rides): route_id, '' = walk."""
    best = ("", weight * walk_s)
    for cap in RIDE_CAPS:
        row = pair_routes_df[pair_routes_df.cap == cap]
        if row.empty or np.isnan(row.transit_s.iloc[0]):
            continue
        row = row.iloc[0]
        time_s = row.transit_s - row.request_s + row.dep_s + row.rides * TIE_S_PER_RIDE
        if time_s < best[1]:
            best = (row.route_id, time_s)
    return best[0]


def r5_leg_ends(pair, route_id, stops_df, to_metric):
    points = [to_metric(pair.origin_lon, pair.origin_lat)]
    if route_id:
        _, boards, alights = (part.split("+") for part in route_id.split("|"))
        for board, alight in zip(boards, alights):
            for stop in (board, alight):
                points.append(to_metric(stops_df.loc[int(stop)].lon, stops_df.loc[int(stop)].lat))
    points.append(to_metric(pair.dest_lon, pair.dest_lat))
    return [(np.asarray(a), np.asarray(b)) for a, b in zip(points[0::2], points[1::2])]


def matched_metres(google_legs, r5_ends):
    total = 0.0
    for g_start, g_end, metres in google_legs:
        if any(np.hypot(*(g_start - a)) <= MATCH_M and np.hypot(*(g_end - b)) <= MATCH_M for a, b in r5_ends):
            total += metres
    return total


def main():
    from pyproj import Transformer
    run_date = datetime.date.today().strftime("%Y%m%d")
    transformer = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
    to_metric = lambda lon, lat: transformer.transform(lon, lat)   # noqa: E731
    overlap_df = pd.read_csv(OVERLAP_PAIRS_PATH).set_index("draw_no")
    pairs_df = pd.read_csv(PAIRS_PATH).set_index("draw_no").loc[overlap_df.index]
    arms_df = pd.read_csv(ARMS_ROUTES_PATH)
    walk_s = pd.read_csv(ARMS_WALK_PATH).set_index("draw_no").walk_s
    stops_df = pd.read_csv(R5_STOPS_PATH).set_index("stop")
    google_legs = google_walk_legs(pairs_df, to_metric)
    weights = sorted(arms_df.walk_weight.unique())
    lines = [f"{NAME} run {run_date}: {len(pairs_df)} scored training pairs (transit_walk_overlap's set); Google walk "
             f"legs {sum(len(v) for v in google_legs.values())}, {sum(m for v in google_legs.values() for *_, m in v) / 1000:.0f} km"]
    records = []
    for weight in weights:
        w_df = arms_df[arms_df.walk_weight == weight]
        for draw_no, pair_routes_df in w_df.groupby("draw_no"):
            if draw_no not in pairs_df.index:
                continue
            route_id = choice_at(pair_routes_df, float(walk_s.get(draw_no, np.inf)), weight)
            legs = google_legs.get(draw_no, [])
            row = pair_routes_df[pair_routes_df.route_id == route_id]
            records.append({"walk_weight": weight, "draw_no": draw_no, "route_id": route_id,
                            "group": overlap_df.loc[draw_no, "group"],
                            "is_walk": route_id == "", "google_m": sum(m for *_, m in legs),
                            "matched_m": matched_metres(legs, r5_leg_ends(pairs_df.loc[draw_no], route_id, stops_df, to_metric)),
                            "r5_walk_s": (float(walk_s.get(draw_no, np.nan)) if route_id == "" else
                                          float(row.access_s.iloc[0] + row.egress_s.iloc[0]) if len(row) else np.nan)})
    result_df = pd.DataFrame(records)
    result_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_choices.csv", index=False)
    base = result_df[result_df.walk_weight == weights[0]].set_index("draw_no").route_id
    lines += ["", "w      matched share of Google walk m   predicted share at 25 m   pairs changed vs w=1   walk-only picks   "
              "R5 slowed access+egress s (median, transit picks; not comparable across w)"]
    for weight, w_df in result_df.groupby("walk_weight"):
        share = w_df.matched_m.sum() / w_df.google_m.sum()
        changed = int((w_df.set_index("draw_no").route_id != base.reindex(w_df.draw_no).to_numpy()).sum())
        lines.append(f"{weight:4.2f}   {share:30.3f}   {MATCHED_RATE * share + UNMATCHED_RATE * (1 - share):23.3f}   "
                     f"{changed:20d}   {int(w_df.is_walk.sum()):15d}   {w_df[~w_df.is_walk].r5_walk_s.median():.0f}")
    for group in ("both transit",):
        g_df = result_df[result_df.group == group]
        lines += ["", f"{group} only:"]
        for weight, w_df in g_df.groupby("walk_weight"):
            lines.append(f"  w {weight:4.2f}: matched share {w_df.matched_m.sum() / w_df.google_m.sum():.3f}")
    shares = result_df.groupby("walk_weight").apply(lambda df: df.matched_m.sum() / df.google_m.sum(), include_groups=False)
    gain = shares.max() - shares.iloc[0]
    lines += ["", f"best w {shares.idxmax():.2f}: matched share gain {gain:+.3f} over w = 1 -> "
              + ("worth routing for real" if gain >= READING_GAIN else "not worth pursuing")
              + " (Claude's rule, not user-approved)"]
    summary = "\n".join(lines)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main()
