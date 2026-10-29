"""How often does stock R5 take Google's default path (same stops and lines)?

Claim under test (concepts/transit.md TRN-12, T7 i; DESIGN.md Q22): time and path are predicted separately;
path (foot traffic) is scored on stop match with Google's default route. This measures stock R5's stop match
and whether Google's default is among R5's saved candidates (coverage), which decides whether a
candidates-then-rerank step is worth building (T7 i: rerank undecided, measure first). Where the pipeline
would rely on it: the path output (foot traffic at stops), not yet built.

R5's route per pair: stock R5 (arm B of diagnostics/transit_preference_arms.py, w = 1, no penalties) chooses
among walk only and the ride caps 1, 2, 8 by arrival, ties to fewer rides; read from that diagnostic's saved
routes (route_id = R5 route indices | board stop indices | alight stop indices) and walk-only seconds.
Google's default: its stops from the raw answers of the full fetch (2026-10-17), extracted here.
Scored pairs: training half, Google's default in scope (TRN-11), R5 result present (as the arms run).

Matching (set by Claude before looking at any match result, 2026-10-18, not user-approved): two stops match
if within STOP_MATCH_M (100 m) of each other (Google's stop names differ from GTFS names; platforms of one
station sit apart); sensitivity at 50 and 200 m. Lines match on the short name, case-insensitive (Google's
nameShort, else name; R5's route_short_name, else long name; train lines compared without " line").
Measures, no verdict: walk-or-transit agreement; among both-transit pairs, first boarding stop, last alighting
stop, ride count, lines, and the full path (same ride count, each ride's line, board and alight stop); path
agreement over all scored pairs (both walk only counts as a match). Coverage: Google's default (full path)
among R5's stock candidates (walk, caps 1, 2, 8 at w = 1) and among all saved candidates (every w and cap).
User's stop rule (2026-10-18): if path agreement passes 90%, the build session may stop there.

Conclusion (run 2026-10-18; 1,246 scored pairs; no verdict, measurement): stock R5 does NOT take Google's
default path. Walk-or-transit agrees on 0.955 (55 pairs Google rides and R5 walks, 1 the reverse). Both transit
(1,126): first boarding stop 0.591, last alighting 0.668, same ride count 0.750, same lines 0.462, full path
0.358 (one-ride defaults 0.474, two-ride 0.148). Path agreement over all scored pairs 0.375 (50 m 0.357,
200 m 0.384): the user's 90% stop rule is not met. Coverage: Google's default is among R5's stock candidates
(walk, caps 1, 2, 8) on 0.435 and among all saved candidates (every w and cap) on 0.671, so a rerank over
these candidates could reach at most ~0.67. Mismatches read as Google preferring trams and buses that run
closer to the endpoints (less walking) where R5 takes trains or another line arriving sooner.

Inputs (read only): raw Google answers and route table, pairs and split in outputs/transit_validation/;
transit_preference_arms' saved routes and walk-only seconds in diagnostics/diagnostic_data/; the cleaned GTFS
copies in outputs/pt_graph/gtfs_cleaned/ (2026-10-09 release) and the OSM extract (one network build, to read
R5's stop and route tables). Self-contained (CLAUDE.md D1). No paid API calls. Saved data (Google stop
extract, R5 stop and route tables) is reused if it exists and says so. The test half is not read.
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
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
GOOGLE_ROUTES_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv"
GOOGLE_RAW_PATH = SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
ARMS_ROUTES_PATH = DIAGNOSTIC_DATA_DIR / "transit_preference_arms_20261017_routes.csv"
ARMS_WALK_PATH = DIAGNOSTIC_DATA_DIR / "transit_preference_arms_20261017_walk.csv"
NAME = "transit_stop_match"
GOOGLE_STOPS_SUFFIX = "_google_stops.csv"       # saved data: Google's rides per route
R5_STOPS_SUFFIX = "_r5_stops.csv"               # saved data: R5 stop index -> id, name, lat, lon
R5_ROUTES_SUFFIX = "_r5_routes.csv"             # saved data: R5 route index -> GTFS route, short name

# --- values ----------------------------------------------------------------------------------------
R5_MAX_MEMORY = "7G"
TRAIN_HALF = "train"
GOOGLE_SCOPES = ["in_scope", "name_mismatch"]   # TRN-11
STOP_MATCH_M = 100                              # Claude's tolerance, set before the run
SENSITIVITY_M = [50, 200]
FIXED_DEGREES = 1e7                             # R5's fixed-point coordinates
EARTH_RADIUS_M = 6_371_000
DEFAULT_LABEL = "DEFAULT_ROUTE"
STOCK_W = 1.0
RIDE_CAPS = [1, 2, 8]
TIE_S_PER_RIDE = 1e-6                           # as transit_preference_arms.py: ties to fewer rides
TRAIN_LINE_SUFFIX = " line"
PATH_STOP_RULE = 0.90                           # user, 2026-10-18: stop the build session above this
N_EXAMPLES = 15                                 # mismatches printed for reading

sys.argv += ["--max-memory", R5_MAX_MEMORY]     # r5py reads its JVM settings at import


def newest(suffix):
    files = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*{suffix}"))
    return files[-1] if files else None


# === saved data ====================================================================================
def extract_google_stops(out_path):
    """One row per transit step of every Google route: line, board and alight stop (name, lat, lon)."""
    rows = []
    with open(GOOGLE_RAW_PATH, encoding="utf-8") as raw_file:
        for line in raw_file:
            answer = json.loads(line)
            for route_ix, route in enumerate(answer["resp"].get("routes", [])):
                is_default = DEFAULT_LABEL in route.get("routeLabels", [])
                ride_no = 0
                for leg in route.get("legs", []):
                    for step in leg.get("steps", []):
                        details = step.get("transitDetails")
                        if details is None:
                            continue
                        stops, transit_line = details["stopDetails"], details.get("transitLine", {})
                        board, alight = stops["departureStop"], stops["arrivalStop"]
                        rows.append({
                            "draw_no": answer["draw_no"], "route_ix": route_ix, "is_default": is_default,
                            "ride_no": ride_no, "line": transit_line.get("nameShort") or transit_line.get("name", ""),
                            "vehicle": transit_line.get("vehicle", {}).get("type", ""),
                            "board_name": board.get("name", ""), "board_lat": board["location"]["latLng"]["latitude"],
                            "board_lon": board["location"]["latLng"]["longitude"],
                            "alight_name": alight.get("name", ""), "alight_lat": alight["location"]["latLng"]["latitude"],
                            "alight_lon": alight["location"]["latLng"]["longitude"],
                            "board_time": stops.get("departureTime", ""), "alight_time": stops.get("arrivalTime", "")})
                        ride_no += 1
    pd.DataFrame(rows).to_csv(out_path, index=False)


def dump_r5_tables(stops_path, routes_path):
    """R5's stop and route tables from one network build (the arms run's network)."""
    from r5py import TransportNetwork
    network = TransportNetwork(PBF_PATH, [GTFS_CLEANED_DIR / f"{name}.zip" for name in FEED_NAMES])
    transit_layer = network._transport_network.transitLayer
    stop_rows = []
    for stop in range(transit_layer.getStopCount()):
        coordinate = transit_layer.getCoordinateForStopFixed(stop)
        stop_rows.append({"stop": stop, "full_id": str(transit_layer.stopIdForIndex.get(stop)),
                          "name": str(transit_layer.stopNames.get(stop)),
                          "lat": coordinate.y / FIXED_DEGREES, "lon": coordinate.x / FIXED_DEGREES})
    pd.DataFrame(stop_rows).to_csv(stops_path, index=False)
    route_rows = []
    for route_ix in range(transit_layer.routes.size()):
        route = transit_layer.routes.get(route_ix)
        route_rows.append({"route": route_ix, "route_id": str(route.route_id),
                           "short_name": str(route.route_short_name or ""),
                           "long_name": str(route.route_long_name or ""), "route_type": int(route.route_type)})
    pd.DataFrame(route_rows).to_csv(routes_path, index=False)


# === comparison ====================================================================================
def distance_m(lat1, lon1, lat2, lon2):
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin((phi2 - phi1) / 2) ** 2
         + np.cos(phi1) * np.cos(phi2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def norm_line(name):
    name = str(name).strip().lower()
    return name[: -len(TRAIN_LINE_SUFFIX)] if name.endswith(TRAIN_LINE_SUFFIX) else name


def r5_rides(route_id, stops_df, routes_df):
    """R5 route_id 'routes|boards|alights' -> list of rides (line, board lat/lon, alight lat/lon, names)."""
    if not isinstance(route_id, str) or not route_id:
        return []
    routes, boards, alights = (part.split("+") for part in route_id.split("|"))
    rides = []
    for route, board, alight in zip(routes, boards, alights):
        route_row, board_row, alight_row = routes_df.loc[int(route)], stops_df.loc[int(board)], stops_df.loc[int(alight)]
        rides.append({"line": norm_line(route_row.short_name if route_row.short_name not in ("", "nan") else route_row.long_name),
                      "board_lat": board_row.lat, "board_lon": board_row.lon, "board_name": board_row["name"],
                      "alight_lat": alight_row.lat, "alight_lon": alight_row.lon, "alight_name": alight_row["name"]})
    return rides


def compare(google_rides, r5_rides_list, tolerance_m):
    """Per-pair match flags for two ride lists (both non-empty)."""
    def near(a, b, end):
        return distance_m(a[f"{end}_lat"], a[f"{end}_lon"], b[f"{end}_lat"], b[f"{end}_lon"]) <= tolerance_m
    first_board = near(google_rides[0], r5_rides_list[0], "board")
    last_alight = near(google_rides[-1], r5_rides_list[-1], "alight")
    same_count = len(google_rides) == len(r5_rides_list)
    same_lines = same_count and all(g["line"] == r["line"] for g, r in zip(google_rides, r5_rides_list))
    same_stops = same_count and all(near(g, r, "board") and near(g, r, "alight")
                                    for g, r in zip(google_rides, r5_rides_list))
    return {"first_board": first_board, "last_alight": last_alight, "same_count": same_count,
            "same_lines": same_lines, "same_stops": same_stops, "full": same_lines and same_stops}


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


def main():
    run_date = datetime.date.today().strftime("%Y%m%d")
    out_prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}"
    lines = [f"{NAME} run {run_date}"]

    google_stops_path = newest(GOOGLE_STOPS_SUFFIX)
    if google_stops_path is None:
        google_stops_path = Path(f"{out_prefix}{GOOGLE_STOPS_SUFFIX}")
        extract_google_stops(google_stops_path)
    else:
        lines.append(f"reusing Google stop extract {google_stops_path.name}")
    r5_stops_path, r5_routes_path = newest(R5_STOPS_SUFFIX), newest(R5_ROUTES_SUFFIX)
    if r5_stops_path is None or r5_routes_path is None:
        r5_stops_path, r5_routes_path = Path(f"{out_prefix}{R5_STOPS_SUFFIX}"), Path(f"{out_prefix}{R5_ROUTES_SUFFIX}")
        dump_r5_tables(r5_stops_path, r5_routes_path)
    else:
        lines.append(f"reusing R5 tables {r5_stops_path.name}, {r5_routes_path.name}")

    stops_df = pd.read_csv(r5_stops_path).set_index("stop")
    routes_df = pd.read_csv(r5_routes_path, keep_default_na=False).set_index("route")
    google_stops_df = pd.read_csv(google_stops_path)
    google_stops_df["line"] = google_stops_df.line.map(norm_line)

    split_df = pd.read_csv(SPLIT_PATH)
    draw_nos = np.sort(split_df[split_df.half == TRAIN_HALF].draw_no.to_numpy())
    google_df = pd.read_csv(GOOGLE_ROUTES_PATH)
    google_df = google_df[google_df.draw_no.isin(draw_nos)]
    default_df = google_df[google_df.is_default].set_index("draw_no")

    # the extract's route_ix and default flag must agree with the route table's
    check_df = google_stops_df[google_stops_df.is_default & google_stops_df.draw_no.isin(draw_nos)].groupby("draw_no").route_ix.first()
    table_ix = default_df.route_ix.reindex(check_df.index)
    lines.append(f"extract vs route table: default route_ix agrees on {(check_df == table_ix).mean():.3f} "
                 f"of {len(check_df)} pairs with a transit default")

    arms_df = pd.read_csv(ARMS_ROUTES_PATH)
    walk_df = pd.read_csv(ARMS_WALK_PATH).set_index("draw_no")
    stock_df = arms_df[arms_df.walk_weight == STOCK_W]

    rides_by_route = {key: group.sort_values("ride_no").to_dict("records")
                      for key, group in google_stops_df.groupby(["draw_no", "route_ix"])}
    records = []
    for draw_no in draw_nos:
        if draw_no not in default_df.index or default_df.loc[draw_no, "route_scope"] not in GOOGLE_SCOPES:
            continue
        pair_routes_df = stock_df[stock_df.draw_no == draw_no]
        if pair_routes_df.empty:
            continue
        default = default_df.loc[draw_no]
        google_rides = [] if default.is_walk_only else rides_by_route.get((draw_no, int(default.route_ix)), [])
        r5_route = stock_choice(pair_routes_df, float(walk_df.walk_s.get(draw_no, np.inf)))
        r5_rides_list = r5_rides(r5_route, stops_df, routes_df)
        # candidates: stock (walk + caps at w = 1) and every saved (w, cap)
        stock_candidates = [r5_rides(rid, stops_df, routes_df) for rid in pair_routes_df.route_id.dropna().unique()]
        all_candidates = [r5_rides(rid, stops_df, routes_df)
                          for rid in arms_df[arms_df.draw_no == draw_no].route_id.dropna().unique()]
        record = {"draw_no": draw_no, "google_walk_only": not google_rides, "r5_walk_only": not r5_rides_list,
                  "google_rides": len(google_rides), "r5_rides": len(r5_rides_list),
                  "google_path": " > ".join(f"{g['line']}: {g['board_name']} - {g['alight_name']}" for g in google_rides),
                  "r5_path": " > ".join(f"{r['line']}: {r['board_name']} - {r['alight_name']}" for r in r5_rides_list)}
        for tolerance_m in [STOP_MATCH_M] + SENSITIVITY_M:
            suffix = "" if tolerance_m == STOP_MATCH_M else f"_{tolerance_m}"
            if google_rides and r5_rides_list:
                flags = compare(google_rides, r5_rides_list, tolerance_m)
            else:
                flags = dict.fromkeys(["first_board", "last_alight", "same_count", "same_lines", "same_stops", "full"],
                                      not google_rides and not r5_rides_list)
            record.update({f"{key}{suffix}": value for key, value in flags.items()})
            if not google_rides:
                in_stock = in_all = True          # walk only is always an R5 candidate
            else:
                in_stock = any(c and compare(google_rides, c, tolerance_m)["full"] for c in stock_candidates)
                in_all = any(c and compare(google_rides, c, tolerance_m)["full"] for c in all_candidates)
            record[f"covered_stock{suffix}"], record[f"covered_all{suffix}"] = in_stock, in_all
        records.append(record)
    result_df = pd.DataFrame(records)
    result_df.to_csv(f"{out_prefix}_pairs.csv", index=False)

    n = len(result_df)
    both_transit = ~result_df.google_walk_only & ~result_df.r5_walk_only
    lines += ["", f"scored training pairs: {n}",
              "walk-or-transit (rows Google, columns R5):",
              pd.crosstab(result_df.google_walk_only.map({True: "walk", False: "transit"}),
                          result_df.r5_walk_only.map({True: "walk", False: "transit"})).to_string(),
              f"walk-or-transit agreement: {(result_df.google_walk_only == result_df.r5_walk_only).mean():.3f}", ""]
    for tolerance_m in [STOP_MATCH_M] + SENSITIVITY_M:
        suffix = "" if tolerance_m == STOP_MATCH_M else f"_{tolerance_m}"
        sub = result_df[both_transit]
        lines.append(f"stop tolerance {tolerance_m} m; both transit ({len(sub)} pairs): first boarding "
                     f"{sub[f'first_board{suffix}'].mean():.3f}, last alighting {sub[f'last_alight{suffix}'].mean():.3f}, "
                     f"same ride count {sub[f'same_count{suffix}'].mean():.3f}, same lines {sub[f'same_lines{suffix}'].mean():.3f}, "
                     f"same stops {sub[f'same_stops{suffix}'].mean():.3f}, full path {sub[f'full{suffix}'].mean():.3f}")
        lines.append(f"  path agreement, all scored pairs (both walk only = match): {result_df[f'full{suffix}'].mean():.3f}; "
                     f"coverage of Google's default: stock candidates {result_df[f'covered_stock{suffix}'].mean():.3f}, "
                     f"all saved candidates {result_df[f'covered_all{suffix}'].mean():.3f}")
    by_rides = result_df[both_transit].groupby("google_rides").agg(pairs=("full", "size"), full=("full", "mean"),
                                                                  first_board=("first_board", "mean"))
    lines += ["", "both transit, by Google's ride count (100 m):", by_rides.round(3).to_string()]
    path_share = result_df.full.mean()
    lines += ["", f"user's stop rule (path agreement > {PATH_STOP_RULE:.0%}): "
                  + ("PASSES" if path_share > PATH_STOP_RULE else "not met") + f" ({path_share:.3f})", "",
              f"examples, both transit, full path not matched (first {N_EXAMPLES}):"]
    for row in result_df[both_transit & ~result_df.full].head(N_EXAMPLES).itertuples():
        lines += [f"  {row.draw_no}: Google {row.google_path}", f"  {' ' * len(str(row.draw_no))}  R5     {row.r5_path}"]
    summary = "\n".join(lines)
    Path(f"{out_prefix}_summary.txt").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
