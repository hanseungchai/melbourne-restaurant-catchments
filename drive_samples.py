"""Sample drive pairs stage: origin-destination draws, their Google drive times, the join the
routing runs read, and the train / test split.

1. Draw (random_sampling, free): origin hex weighted by residents or workers (p = 0.5), destination a
   venue drawn uniformly; a pair is kept only if it is reachable within config.ROUTES_DRIVE_WINDOW_S on
   the window graph (blind, β = config.ROUTES_DRIVE_WINDOW_BETA_S). Weekday departure times from the
   open-share histogram plus a flat floor (config.ROUTES_DRIVE_DEPARTURE_*). The 2026-09-30 draw is
   frozen (config.ROUTES_DRIVE_DRAWS_PATH); a redraw only checks it reproduces. draw_second_drive_set
   makes the second draw (new seed, new draw_no range, no hex pair of the first).
2. Google times (fetch_drive_eta, PAID): one Compute Routes Pro request per pair, TRAFFIC_AWARE, every
   raw response saved; ledger-guarded (api_ledger) and resumable.
3. Join (join_drive_sets): draws + Google times + each end's snap nodes from the hex nodes table;
   the calibrate_pathing_agent stage routes this file.
4. Split (split_drive_pairs): train / test halves and CV folds, written once.
"""
import csv
import itertools
import json
import time
from collections import Counter
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import pyogrio
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra as cs_dijkstra
from sklearn.model_selection import StratifiedGroupKFold

import api_ledger
import config
from functions.drive_routing import (DRIVE_NODE_COLS, DRIVE_ROAD_DIST_COLS, LEN_ATTR, MIN_CSR_WEIGHT,
                                     PAIR_ID_COL, TIME_ATTR, VARIANT_KEY, eligible_nodes,
                                     load_penalised_graph, penalised_time_attr)
from functions.geometry import haversine_m
from functions.google_places import read_google_api_key
from functions.google_routes import HTTP_OK, post_compute_routes
from functions.output_helper import is_already_built
from functions.pair_sampling import assign_venue_hex, departure_probabilities
from functions.subject_paths import subject_layers_file, timed_graph_path

LOCAL_TZ = ZoneInfo(config.LOCAL_TIMEZONE)

# Hex nodes table and venue table columns read here.
HEX_ID_COL = "hex_id"
RESIDENTS_COL, WORKERS_COL, VENUE_COUNT_COL = "residents", "workers", "venue_count"
CENTROID_LAT_COL, CENTROID_LON_COL = "centroid_lat", "centroid_lon"
DRIVE_NODE_DIST_COLS = ("drive_node_dist_1_m", "drive_node_dist_2_m")
PLACE_ID_COL, VENUE_LAT_COL, VENUE_LON_COL = "place_id", "lat", "lng"

# Draw and fetch columns.
DRAW_NO_COL = "draw_no"
DRAW_COL = "draw"                     # joined pairs: which draw a pair came from (1, 2)
HTTP_STATUS_COL = "http_status"
GOOGLE_DURATION_COL = "google_drive_duration_sec"

# Graph node attributes, as speed_graphs.enrich writes them.
NODE_LAT_ATTR, NODE_LON_ATTR = "y", "x"

# Opening-hours histogram (opening_hours.build_opening_hours).
HOURS_WEEKDAY_COL, HOURS_DAY_COL, HOURS_DAY_NAME_COL = "weekday", "day", "day_name"
HOURS_MINUTE_OF_WEEK_COL, HOURS_OPEN_COL = "minute_of_week", "n_open"
GOOGLE_WEEKDAYS = [1, 2, 3, 4, 5]  # Google's day index: 1 = Mon ... 5 = Fri
MIN_PER_HOUR = 60
DAYS_PER_WEEK = 7
SLOTS_PER_DAY = 24 * MIN_PER_HOUR // config.HOURS_SLOT_MIN

# Random streams under one seed: pairs use the seed itself, these are child streams.
DEPARTURE_STREAM, HEX_PAIR_U_STREAM, WEEK_OFFSET_STREAM = 1, 2, 3
ORIGIN_POOLS = np.array(["resident", "worker"])


# Window gate internals.
SINK_NODE = "__sink__"             # temporary node joining the destination candidates (networkx check)
N_PARITY_CHECKS = 20               # first draws also routed with networkx; must agree
PARITY_TOL_S = 1e-3
N_EDGES_ATTR_CHECK = 1000          # edges sampled to confirm the penalised weight exists
MS_TO_KMH = 3.6
M_PER_KM = 1000

# Google Routes, Compute Routes Pro (TRAFFIC_AWARE bills there, not Essentials: the target is what
# Google tells travellers, and the consumer app is traffic-aware).
ROUTES_SKU = "routes_pro"
ROUTES_ENDPOINT = "routes/computeRoutes"
ROUTES_TRAVEL_MODE = "DRIVE"
ROUTES_ROUTING_PREFERENCE = "TRAFFIC_AWARE"
DRIVE_FIELD_MASK = ",".join([
    "routes.duration",
    "routes.staticDuration",          # traffic-free duration
    "routes.distanceMeters",
    "routes.polyline.encodedPolyline",
    "routes.routeLabels",             # DEFAULT_ROUTE vs alternates
    "routes.legs.startLocation",      # where Google snapped the origin
    "routes.legs.endLocation",        # ... and the destination
    "routes.description",             # e.g. "Monash Fwy"
    "routes.warnings",
])
DEFAULT_ROUTE_LABEL = "DEFAULT_ROUTE"
UTC_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DRAW2_FETCH_RUN_ID = "drive_eta_draw2"

# Progress printing.
DRAW_PROGRESS_EVERY = 200
KEPT_PROGRESS_EVERY = 250
FETCH_PROGRESS_EVERY = 100


# --- Google Routes fetch -----------------------------------------------------------------------------

def _parse_drive_routes(routes):
    """Fields kept from a Routes response: Google's default route (else the first), its durations,
    distance, polyline and description, the route count and where Google snapped both ends."""
    route = next((r for r in routes if DEFAULT_ROUTE_LABEL in r.get("routeLabels", [])), routes[0])
    leg = (route.get("legs") or [{}])[0]
    static_duration = route.get("staticDuration")
    lat_lng = lambda key: leg.get(key, {}).get("latLng", {})
    duration, distance_m = route.get("duration"), route.get("distanceMeters")
    return dict(duration_sec=int(duration.rstrip("s")) if duration else None,
                distance_m=distance_m,
                static_duration_sec=int(static_duration.rstrip("s")) if static_duration else None,
                polyline=route.get("polyline", {}).get("encodedPolyline"),
                description=route.get("description"),
                n_routes=len(routes),
                g_o_lat=lat_lng("startLocation").get("latitude"), g_o_lon=lat_lng("startLocation").get("longitude"),
                g_d_lat=lat_lng("endLocation").get("latitude"), g_d_lon=lat_lng("endLocation").get("longitude"))


def request_drive_route(origin_lat, origin_lon, dest_lat, dest_lon, api_key, departure_time_iso,
                        before_send, raw_sink):
    """One Compute Routes Pro request, retried on 429 / 5xx / network errors (post_compute_routes).

    before_send runs before every attempt (the ledger records each one); raw_sink gets every 200
    response untouched. Returns the parsed fields plus http_status; http_status None after the last
    retry fails.
    """
    body = {
        "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lon}}},
        "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lon}}},
        "travelMode": ROUTES_TRAVEL_MODE,
        "routingPreference": ROUTES_ROUTING_PREFERENCE,
        "departureTime": departure_time_iso,
        "computeAlternativeRoutes": True,
    }
    http_status, response_json, _ = post_compute_routes(body, DRIVE_FIELD_MASK, api_key, before_send)
    if http_status != HTTP_OK:
        return {"http_status": http_status}
    raw_sink(response_json)
    routes = response_json.get("routes")
    if not routes:
        return {"http_status": HTTP_OK}            # no route, not an error
    return {"http_status": HTTP_OK, **_parse_drive_routes(routes)}


def _departure(dep_day, dep_min, now_utc, min_date=None):
    """Next local date strictly after today, not before min_date, on the drawn weekday, at dep_min
    minutes after midnight. dep_day is Google's index (1 = Mon ... 5 = Fri). Returns (UTC ISO, local)."""
    departure_date = now_utc.astimezone(LOCAL_TZ).date() + timedelta(days=1)
    if min_date is not None:
        departure_date = max(departure_date, min_date)
    departure_date += timedelta(days=(int(dep_day) - 1 - departure_date.weekday()) % DAYS_PER_WEEK)
    local = datetime.combine(departure_date,
                             dtime(int(dep_min) // MIN_PER_HOUR, int(dep_min) % MIN_PER_HOUR), tzinfo=LOCAL_TZ)
    return local.astimezone(timezone.utc).strftime(UTC_ISO_FORMAT), local


def fetch_drive_eta(od_path, out_path, run_id, limit, min_date=None, api_key=None):
    """WARNING: SPENDS API CALLS (Compute Routes Pro). Google drive times for the pairs in od_path.

    Appends one row per pair to out_path (raw responses to its .raw.jsonl) and skips pairs already
    fetched with HTTP 200, so a stopped run resumes. limit: pairs this run (None = all remaining).
    Each departure goes 0 to config.ROUTES_DRIVE_DEPARTURE_HORIZON_WEEKS weeks ahead (per-pair stream).
    """
    if api_key is None:
        api_key = read_google_api_key()        # at call time, never at import (CLAUDE.md S3)
    out_path = Path(out_path)
    pairs_df = pd.read_csv(od_path).sort_values(DRAW_NO_COL)
    done = set()
    if out_path.exists():
        fetched_df = pd.read_csv(out_path, usecols=[DRAW_NO_COL, HTTP_STATUS_COL])
        done = set(fetched_df.loc[fetched_df[HTTP_STATUS_COL] == HTTP_OK, DRAW_NO_COL])
    todo_df = pairs_df[~pairs_df[DRAW_NO_COL].isin(done)]
    if limit is not None:
        todo_df = todo_df.head(limit)
    print(f"{len(done)} done, {len(todo_df)} to fetch")
    api_ledger.check(ROUTES_SKU, len(todo_df))            # batch guard before any send

    should_write_header = not out_path.exists()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "a", newline="") as out_file, open(out_path.with_suffix(".raw.jsonl"), "a") as raw_file:
        writer = None
        for i, row in enumerate(todo_df.itertuples()):
            draw_no = int(row.draw_no)
            now = datetime.now(timezone.utc)
            week_offset = np.random.default_rng([config.ROUTES_DRIVE_SEED, WEEK_OFFSET_STREAM, draw_no]).integers(
                0, config.ROUTES_DRIVE_DEPARTURE_HORIZON_WEEKS)
            dep_iso, dep_local = _departure(row.dep_day, row.dep_min_of_day, now,
                                            (min_date or now.astimezone(LOCAL_TZ).date())
                                            + timedelta(weeks=int(week_offset)))
            result = request_drive_route(
                row.origin_lat, row.origin_lon, row.dest_lat, row.dest_lon, api_key=api_key,
                departure_time_iso=dep_iso,
                before_send=lambda: api_ledger.record_send(ROUTES_SKU, endpoint=ROUTES_ENDPOINT, run_id=run_id,
                                                           meta={DRAW_NO_COL: draw_no}),
                raw_sink=lambda response_json: (raw_file.write(json.dumps({DRAW_NO_COL: draw_no,
                                                                           "resp": response_json}) + "\n"),
                                                raw_file.flush()))
            record = dict(draw_no=draw_no,
                          google_drive_duration_sec=result.get("duration_sec"),
                          google_drive_distance_m=result.get("distance_m"),
                          http_status=result["http_status"],
                          departure_time_utc=dep_iso,
                          departure_local=dep_local.isoformat(),
                          collected_at_utc=now.strftime(UTC_ISO_FORMAT),
                          run_id=run_id,
                          static_duration_sec=result.get("static_duration_sec"),
                          polyline=result.get("polyline"), description=result.get("description"),
                          n_routes=result.get("n_routes"),
                          g_o_lat=result.get("g_o_lat"), g_o_lon=result.get("g_o_lon"),
                          g_d_lat=result.get("g_d_lat"), g_d_lon=result.get("g_d_lon"))
            if writer is None:
                writer = csv.DictWriter(out_file, fieldnames=list(record))
                if should_write_header:
                    writer.writeheader()
            writer.writerow(record)
            out_file.flush()
            if i % FETCH_PROGRESS_EVERY == 0:
                print(f"  {i}/{len(todo_df)}  last status {result['http_status']}")
            time.sleep(config.ROUTES_REQUEST_DELAY_S)


def fetch_second_drive_set(subject_lat, subject_lon, limit):
    """WARNING: SPENDS API CALLS (Compute Routes Pro). Google drive times for the second draw."""
    fetch_drive_eta(od_path=subject_layers_file(config.ROUTES_DRIVE_DRAW2_PATH, subject_lat, subject_lon),
                    out_path=subject_layers_file(config.ROUTES_DRIVE_DRAW2_ETA_PATH, subject_lat, subject_lon),
                    run_id=DRAW2_FETCH_RUN_ID, limit=limit)


# --- Draw --------------------------------------------------------------------------------------------

def _max_speed_ms(graph):
    """Fastest edge in the graph, metres per second (bounds how far the window can reach)."""
    return max(data[LEN_ATTR] / data[TIME_ATTR]
               for _, _, data in graph.edges(data=True) if data.get(TIME_ATTR, 0) > 0)


def _to_csr(graph, weight_attr):
    """The graph as a scipy CSR matrix under weight_attr (cheapest of parallel edges, as networkx),
    plus the node array and node -> row index."""
    nodes = np.fromiter(graph.nodes, dtype=np.int64, count=graph.number_of_nodes())
    node_ix = {node: i for i, node in enumerate(nodes)}
    edges_df = pd.DataFrame(((node_ix[u], node_ix[v], data[weight_attr]) for u, v, data in graph.edges(data=True)),
                            columns=["u", "v", "w"])
    edges_df = edges_df.groupby(["u", "v"], as_index=False).w.min()
    weights = np.maximum(edges_df.w.to_numpy(float), MIN_CSR_WEIGHT)
    adjacency = csr_matrix((weights, (edges_df.u.to_numpy(), edges_df.v.to_numpy())), shape=(len(nodes),) * 2)
    return adjacency, nodes, node_ix


def _route_window_csr(adjacency, nodes, node_ix, origin_cands, dest_cands, cutoff_s):
    """Cheapest route from any origin candidate to any destination candidate within cutoff_s.
    Returns (seconds, origin node used, destination node reached); raises NetworkXNoPath if over."""
    dist_s, _, sources = cs_dijkstra(adjacency, directed=True, indices=[node_ix[o] for o in origin_cands],
                                     min_only=True, limit=cutoff_s, return_predecessors=True)
    dest_ix = [node_ix[d] for d in dest_cands]
    best = int(np.argmin(dist_s[dest_ix]))
    if not np.isfinite(dist_s[dest_ix[best]]):
        raise nx.NetworkXNoPath
    return float(dist_s[dest_ix[best]]), int(nodes[sources[dest_ix[best]]]), int(nodes[dest_ix[best]])


def _route_window_networkx(graph, origin_cands, dest_cands, weight_attr, cutoff_s):
    """The same search in networkx, for the parity check. Raises NetworkXNoPath if over."""
    for dest in dest_cands:
        graph.add_edge(dest, SINK_NODE, **{weight_attr: 0.0})
    try:
        time_s, path = nx.multi_source_dijkstra(graph, set(origin_cands), target=SINK_NODE,
                                                cutoff=cutoff_s, weight=weight_attr)
        return time_s, path[0], path[-2]
    finally:
        graph.remove_node(SINK_NODE)


def random_sampling(subject_lat, subject_lon, hex_nodes_path=None,
                    venues_path=config.VENUE_TABLES[config.HEX_VENUES_DATE], window_graph_path=None,
                    hours_hist_path=config.OPENING_HOURS_HIST_PATH, out_path=None, log_path=None,
                    seed=config.ROUTES_DRIVE_SEED, exclude_pairs_path=None, draw_no_offset=0):
    """Draw config.ROUTES_DRIVE_N_PAIRS pairs on the subject's graphs (module docstring, step 1).

    None paths resolve to the subject's files in config. seed: seeds the pair, departure-time and
    per-hex-pair streams. exclude_pairs_path: earlier draws; a candidate whose (origin_hex, dest_hex)
    appears there is rejected (log: old_hex_pair). draw_no_offset: added to draw_no, so pooled draws
    keep unique ids. The defaults reproduce the 2026-09-30 draw (on its 2026-09-02 hours).
    Writes the draw, its .kept.pkl checkpoint and the rejection counts (log_path).
    """
    hex_nodes_path = hex_nodes_path or subject_layers_file(config.HEX_NODES_PATH, subject_lat, subject_lon)
    window_graph_path = window_graph_path or timed_graph_path(config.ROUTES_DRIVE_WINDOW_VARIANT,
                                                              subject_lat, subject_lon)
    out_path = Path(out_path or subject_layers_file(config.ROUTES_DRIVE_REDRAW_PATH, subject_lat, subject_lon))
    log_path = log_path or subject_layers_file(config.ROUTES_DRIVE_SAMPLE_LOG_PATH, subject_lat, subject_lon)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    hexes_df = gpd.read_file(hex_nodes_path)
    hexes_df = hexes_df[[HEX_ID_COL, RESIDENTS_COL, WORKERS_COL, VENUE_COUNT_COL,
                         CENTROID_LAT_COL, CENTROID_LON_COL,
                         DRIVE_NODE_COLS[0], DRIVE_ROAD_DIST_COLS[0],
                         DRIVE_NODE_COLS[1], DRIVE_ROAD_DIST_COLS[1]]].reset_index(drop=True)
    candidates_df = (hexes_df[[HEX_ID_COL, DRIVE_NODE_COLS[0], DRIVE_ROAD_DIST_COLS[0],
                               DRIVE_NODE_COLS[1], DRIVE_ROAD_DIST_COLS[1]]]
                     .add_prefix("hex_").rename(columns={f"hex_{HEX_ID_COL}": HEX_ID_COL}))
    cands_of_hex = {row.hex_id: tuple(int(node) for node in eligible_nodes(row, "hex"))
                    for row in candidates_df.itertuples(index=False)}

    seen, kept, counts = set(), [], Counter()
    excluded_hex_pairs = set()
    if exclude_pairs_path is not None:
        excluded_df = pd.read_csv(exclude_pairs_path, usecols=["origin_hex", "dest_hex"])
        excluded_hex_pairs = set(zip(excluded_df.origin_hex, excluded_df.dest_hex))
        print(f"excluding {len(excluded_hex_pairs):,} hex pairs from {Path(exclude_pairs_path).name}")
    counts["hex_two_cands"] = sum(len(cands) == 2 for cands in cands_of_hex.values())
    print(f"candidates built: {counts['hex_two_cands']:,} two-candidate hexes "
          f"({counts['hex_two_cands'] / len(cands_of_hex):.1%})")
    t_start = datetime.now()

    venues_df = pd.read_csv(venues_path)
    n_raw = len(venues_df)
    venues_df = venues_df.drop_duplicates(PLACE_ID_COL)
    n_unique = len(venues_df)
    venues_df, n_off_grid = assign_venue_hex(venues_df, hexes_df)
    assert venues_df[HEX_ID_COL].isin(cands_of_hex).all(), "venue hex without drive candidates"
    counts["venue_dup_rows"], counts["venue_off_grid"] = n_raw - n_unique, n_off_grid
    print(f"Loaded {len(hexes_df)} hexes, {len(venues_df)} venues ({n_raw - n_unique} dup rows, "
          f"{n_off_grid} beyond {config.VENUE_HEX_MATCH_RADIUS_M} m of any centroid)")

    # independent check: must reproduce the grid's venue_count
    venues_per_hex = venues_df[HEX_ID_COL].value_counts()
    grid_counts = hexes_df.set_index(HEX_ID_COL)[VENUE_COUNT_COL].fillna(0).astype(int)
    grid_counts = grid_counts[grid_counts > 0]
    n_mismatched = int((venues_per_hex.reindex(grid_counts.index, fill_value=0) != grid_counts).sum())
    n_extra = len(venues_per_hex.index.difference(grid_counts.index))
    print(f"venue_count check: {n_mismatched} hexes mismatched, {n_extra} venue hexes not counted in grid")
    assert n_mismatched == 0 and n_extra == 0, "venue assignment disagrees with the grid — stop and diff"

    p_residents = hexes_df[RESIDENTS_COL].fillna(0).to_numpy(float, copy=True)
    p_residents /= p_residents.sum()
    p_workers = hexes_df[WORKERS_COL].fillna(0).to_numpy(float, copy=True)
    p_workers /= p_workers.sum()

    graph = load_penalised_graph(window_graph_path, (config.ROUTES_DRIVE_WINDOW_BETA_S,))
    assert graph.graph.get(VARIANT_KEY) == config.ROUTES_DRIVE_WINDOW_VARIANT, graph.graph.get(VARIANT_KEY)
    weight_attr = penalised_time_attr(config.ROUTES_DRIVE_WINDOW_BETA_S)
    assert all(weight_attr in data for _, _, data in itertools.islice(graph.edges(data=True), N_EDGES_ATTR_CHECK)), \
        f"{weight_attr} missing"

    adjacency, csr_nodes, csr_node_ix = _to_csr(graph, weight_attr)
    print(f"CSR built: {adjacency.shape[0]:,} nodes, {adjacency.nnz:,} edges")

    max_speed_ms = _max_speed_ms(graph)
    reach_m = max_speed_ms * config.ROUTES_DRIVE_WINDOW_S
    print(f"Max graph speed {max_speed_ms * MS_TO_KMH:.1f} km/h -> prefilter {reach_m / M_PER_KM:.1f} km")

    while len(kept) < config.ROUTES_DRIVE_N_PAIRS:
        pool = rng.choice(ORIGIN_POOLS, size=config.ROUTES_DRIVE_DRAW_BATCH)
        origin_by_residents = rng.choice(len(hexes_df), size=config.ROUTES_DRIVE_DRAW_BATCH, p=p_residents)
        origin_by_workers = rng.choice(len(hexes_df), size=config.ROUTES_DRIVE_DRAW_BATCH, p=p_workers)
        origin_ix = np.where(pool == ORIGIN_POOLS[0], origin_by_residents, origin_by_workers)
        venue_ix = rng.integers(len(venues_df), size=config.ROUTES_DRIVE_DRAW_BATCH)

        for pool_name, oi, vi in zip(pool, origin_ix, venue_ix):
            counts["drawn"] += 1
            if counts["drawn"] % DRAW_PROGRESS_EVERY == 0:
                elapsed_s = (datetime.now() - t_start).total_seconds()
                print(f"  {elapsed_s:6.0f}s  drawn {counts['drawn']}  kept {len(kept)}  "
                      f"over_window {counts['over_window']}  prefilter {counts['prefilter']}")
            origin_hex = hexes_df[HEX_ID_COL].iat[oi]
            venue = venues_df.iloc[vi]
            dest_hex = venue[HEX_ID_COL]
            pair_key = (origin_hex, venue[PLACE_ID_COL])

            if origin_hex == dest_hex:
                counts["same_hex"] += 1
                continue
            if (origin_hex, dest_hex) in excluded_hex_pairs:
                counts["old_hex_pair"] += 1
                continue
            if pair_key in seen:
                counts["duplicate_pair"] += 1
                continue

            origin_cands, dest_cands = cands_of_hex[origin_hex], cands_of_hex[dest_hex]
            if set(origin_cands) & set(dest_cands):
                counts["same_node"] += 1
                continue

            if min(haversine_m(graph.nodes[a][NODE_LAT_ATTR], graph.nodes[a][NODE_LON_ATTR],
                               graph.nodes[b][NODE_LAT_ATTR], graph.nodes[b][NODE_LON_ATTR])
                   for a in origin_cands for b in dest_cands) > reach_m:
                counts["prefilter"] += 1
                continue

            try:
                window_s, origin_node, dest_node = _route_window_csr(
                    adjacency, csr_nodes, csr_node_ix, origin_cands, dest_cands, config.ROUTES_DRIVE_WINDOW_S)
                is_within_window = True
            except nx.NetworkXNoPath:
                is_within_window = False
            if counts["cs_checked"] < N_PARITY_CHECKS:
                counts["cs_checked"] += 1
                try:
                    networkx_s = _route_window_networkx(graph, origin_cands, dest_cands, weight_attr,
                                                        config.ROUTES_DRIVE_WINDOW_S)[0]
                except nx.NetworkXNoPath:
                    networkx_s = None
                assert (networkx_s is None) == (not is_within_window), "accept/reject disagrees with networkx"
                assert networkx_s is None or abs(networkx_s - window_s) < PARITY_TOL_S, (networkx_s, window_s)
            if not is_within_window:
                counts["over_window"] += 1
                continue

            seen.add(pair_key)
            kept.append(dict(
                draw_no=counts["drawn"] + draw_no_offset, pool=pool_name,
                origin_hex=origin_hex,
                origin_lat=hexes_df[CENTROID_LAT_COL].iat[oi], origin_lon=hexes_df[CENTROID_LON_COL].iat[oi],
                place_id=venue[PLACE_ID_COL], dest_hex=dest_hex,
                dest_lat=venue[VENUE_LAT_COL], dest_lon=venue[VENUE_LON_COL],
                o_node=origin_node, d_node=dest_node,
                o_cands=origin_cands, d_cands=dest_cands,
                blind_b2_raw_s=window_s,
            ))
            if len(kept) % KEPT_PROGRESS_EVERY == 0:
                print(f"  kept {len(kept)} / drawn {counts['drawn']}")
            if len(kept) == config.ROUTES_DRIVE_N_PAIRS:
                break

        pd.DataFrame(kept).to_pickle(out_path.with_suffix(".kept.pkl"))

    draws_df = pd.DataFrame(kept)
    hours_df = pd.read_csv(hours_hist_path)
    weekday_hours_df = hours_df[hours_df[HOURS_WEEKDAY_COL]].sort_values(HOURS_MINUTE_OF_WEEK_COL)
    assert (list(weekday_hours_df[HOURS_DAY_COL].unique()) == GOOGLE_WEEKDAYS
            and len(weekday_hours_df) == len(GOOGLE_WEEKDAYS) * SLOTS_PER_DAY), "expected Mon–Fri × 48 slots"
    hist = weekday_hours_df[HOURS_OPEN_COL].to_numpy(float).reshape(len(GOOGLE_WEEKDAYS), SLOTS_PER_DAY)  # row 0 = Mon

    p_departure = departure_probabilities(hist)
    rng_departure = np.random.default_rng([seed, DEPARTURE_STREAM])
    cell = rng_departure.choice(p_departure.size, size=len(draws_df), p=p_departure)
    draws_df["dep_day"] = cell // SLOTS_PER_DAY + 1                     # Google index: 1 = Mon … 5 = Fri
    draws_df["dep_day_name"] = weekday_hours_df[HOURS_DAY_NAME_COL].to_numpy()[cell]
    draws_df["dep_slot_min"] = (cell % SLOTS_PER_DAY) * config.HOURS_SLOT_MIN   # slot start, min after midnight
    draws_df["dep_min_of_day"] = draws_df.dep_slot_min + rng_departure.integers(0, config.HOURS_SLOT_MIN,
                                                                              size=len(draws_df))
    draws_df["dep_p"] = p_departure[cell]

    draws_df["haversine_m"] = haversine_m(draws_df["origin_lat"], draws_df["origin_lon"],
                                          draws_df["dest_lat"], draws_df["dest_lon"])

    draws_df["grp"] = draws_df.groupby(["origin_hex", "dest_hex"]).ngroup()
    u_per_hex_pair = np.random.default_rng([seed, HEX_PAIR_U_STREAM]).random(draws_df.grp.max() + 1)
    draws_df["u_grp"] = u_per_hex_pair[draws_df.grp]                    # one U(0,1) per hex pair

    counts["shared_hex_pair"] = len(draws_df) - draws_df[["origin_hex", "dest_hex"]].drop_duplicates().shape[0]
    counts["kept"] = len(draws_df)
    counts["accept_rate"] = len(draws_df) / counts["drawn"]
    print("\nSampling log:", dict(counts))
    print(draws_df.head())

    draws_df.to_csv(out_path, index=False)
    with open(log_path, "w") as f:
        json.dump({key: float(value) for key, value in counts.items()}, f, indent=2)
    print(f"\nSaved to {out_path}")
    return draws_df


def draw_second_drive_set(subject_lat, subject_lon, should_rebuild=False):
    """Second drive draw (config ROUTES_DRIVE_DRAW2_*): new seed and draw_no range, no hex pair of the
    2026-09-30 draws, departure times from the hours named by config.OPENING_HOURS_PULL_DATE.

    Skipped if the draw exists: its paid Google times are keyed to it by draw_no, and a redraw on
    other hours would give the same pairs different departure times.
    """
    out_path = subject_layers_file(config.ROUTES_DRIVE_DRAW2_PATH, subject_lat, subject_lon)
    log_path = subject_layers_file(config.ROUTES_DRIVE_DRAW2_LOG_PATH, subject_lat, subject_lon)
    if is_already_built([out_path, log_path], should_rebuild):
        return pd.read_csv(out_path)
    return random_sampling(subject_lat, subject_lon, out_path=out_path, log_path=log_path,
                           seed=config.ROUTES_DRIVE_DRAW2_SEED, exclude_pairs_path=config.ROUTES_DRIVE_DRAWS_PATH,
                           draw_no_offset=config.ROUTES_DRIVE_DRAW2_DRAW_NO_OFFSET)


# --- Join --------------------------------------------------------------------------------------------

def attach_drive_snap_nodes(pairs_df, hex_nodes_df):
    """Attach each end's drive snap columns (node, road distance, node distance; candidates 1 and 2)
    by origin_hex_id / dest_hex_id. Raises if any end has no snap node."""
    pairs_df = pairs_df.copy()

    # haversine_m was computed when the draw was made; only recompute if absent
    if "haversine_m" not in pairs_df.columns:
        print("  haversine_m missing, computing")
        pairs_df["haversine_m"] = haversine_m(pairs_df["origin_lat"], pairs_df["origin_lon"],
                                              pairs_df["dest_lat"], pairs_df["dest_lon"])

    snap_cols = [HEX_ID_COL,
                 DRIVE_NODE_COLS[0], DRIVE_ROAD_DIST_COLS[0], DRIVE_NODE_DIST_COLS[0],
                 DRIVE_NODE_COLS[1], DRIVE_ROAD_DIST_COLS[1], DRIVE_NODE_DIST_COLS[1]]
    snaps_df = hex_nodes_df[snap_cols].copy()
    snaps_df[HEX_ID_COL] = snaps_df[HEX_ID_COL].astype("int64")
    pairs_df["origin_hex_id"] = pairs_df["origin_hex_id"].astype("int64")
    pairs_df["dest_hex_id"] = pairs_df["dest_hex_id"].astype("int64")

    n_before = len(pairs_df)
    pairs_df = pairs_df.merge(snaps_df.add_prefix("origin_"), on="origin_hex_id", how="left", validate="many_to_one")
    pairs_df = pairs_df.merge(snaps_df.add_prefix("dest_"), on="dest_hex_id", how="left", validate="many_to_one")
    assert len(pairs_df) == n_before, "row count changed during merge"

    n_origin_unmatched = pairs_df[f"origin_{DRIVE_NODE_COLS[0]}"].isna().sum()
    n_dest_unmatched = pairs_df[f"dest_{DRIVE_NODE_COLS[0]}"].isna().sum()
    print(f"  unmatched origins: {n_origin_unmatched}, destinations: {n_dest_unmatched}")
    if n_origin_unmatched or n_dest_unmatched:
        raise ValueError(f"{n_origin_unmatched} origins / {n_dest_unmatched} destinations unmatched — "
                         "OD sample and hex grid are out of sync (stale numbering?)")
    return pairs_df


def default_drive_sets(subject_lat, subject_lon):
    """{draw: (draw_path, google_path)}: the frozen 2026-09-30 draw and the subject's second draw."""
    return {1: (config.ROUTES_DRIVE_DRAWS_PATH, config.ROUTES_DRIVE_ETA_PATH),
            2: (subject_layers_file(config.ROUTES_DRIVE_DRAW2_PATH, subject_lat, subject_lon),
                subject_layers_file(config.ROUTES_DRIVE_DRAW2_ETA_PATH, subject_lat, subject_lon))}


def _latest_fetch_per_pair(google_df):
    """One row per draw_no: its HTTP 200 row if it has one, else its last attempt. A resumed fetch
    appends a new row for every pair that failed before, so a pair can have several rows."""
    google_df = google_df.assign(is_ok=google_df[HTTP_STATUS_COL] == HTTP_OK)
    google_df = google_df.sort_values("is_ok", kind="stable").drop_duplicates(DRAW_NO_COL, keep="last")
    return google_df.drop(columns="is_ok").sort_index()


def join_drive_sets(subject_lat, subject_lon, drive_sets=None, out_path=None, hex_nodes_path=None):
    """Join each draw to its Google times (failed fetches dropped) and each end's snap nodes, pooled
    over drive_sets ({draw: (draw_path, google_path)}; None = default_drive_sets) with a draw column;
    the routing runs' input. None paths resolve to the subject's files in config."""
    out_path = Path(out_path or subject_layers_file(config.ROUTES_DRIVE_ENRICHED_PATH, subject_lat, subject_lon))
    hex_nodes_path = hex_nodes_path or subject_layers_file(config.HEX_NODES_PATH, subject_lat, subject_lon)
    drive_sets = drive_sets or default_drive_sets(subject_lat, subject_lon)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    set_dfs = []
    for draw, (draw_path, google_path) in drive_sets.items():
        draws_df = pd.read_csv(draw_path)
        google_df = pd.read_csv(google_path)
        latest_df = _latest_fetch_per_pair(google_df)
        set_df = draws_df.merge(latest_df, on=DRAW_NO_COL, how="inner", validate="one_to_one")
        print(f"draw {draw}: draws {len(draws_df):,}  google {len(google_df):,} "
              f"(repeat attempts dropped {len(google_df) - len(latest_df):,})  merged {len(set_df):,}")
        set_dfs.append(set_df.assign(**{DRAW_COL: draw}))
    pairs_df = pd.concat(set_dfs, ignore_index=True)
    assert pairs_df[DRAW_NO_COL].is_unique, "draw_no repeats across draws"

    print("http_status:", pairs_df[HTTP_STATUS_COL].value_counts(dropna=False).to_dict())
    is_fetched = pairs_df[GOOGLE_DURATION_COL].notna() & (pairs_df[GOOGLE_DURATION_COL] > 0)
    print(f"dropped failed fetches: {(~is_fetched).sum():,}")
    pairs_df = pairs_df[is_fetched].copy()
    pairs_df = pairs_df.rename(columns={"origin_hex": "origin_hex_id", "dest_hex": "dest_hex_id"})

    snap_cols = [HEX_ID_COL, *DRIVE_NODE_COLS, *DRIVE_ROAD_DIST_COLS, *DRIVE_NODE_DIST_COLS]
    hex_nodes_df = pyogrio.read_dataframe(hex_nodes_path, columns=snap_cols, read_geometry=False)
    pairs_df = attach_drive_snap_nodes(pairs_df, hex_nodes_df)

    # do the snaps agree with the ones the window draw used?
    for end, node_col in (("origin", "o_node"), ("dest", "d_node")):
        share_node_1 = (pairs_df[f"{end}_{DRIVE_NODE_COLS[0]}"] == pairs_df[node_col]).mean()
        share_either = ((pairs_df[f"{end}_{DRIVE_NODE_COLS[0]}"] == pairs_df[node_col])
                        | (pairs_df[f"{end}_{DRIVE_NODE_COLS[1]}"] == pairs_df[node_col])).mean()
        print(f"{end}: matches node_1 {share_node_1:.1%}, either {share_either:.1%}")

    pairs_df[PAIR_ID_COL] = pairs_df[DRAW_NO_COL]
    print("origin pool:", pairs_df["pool"].value_counts().to_dict())
    pairs_df.to_csv(out_path, index=False)
    print(f"saved {len(pairs_df):,} pairs to {out_path}")
    return pairs_df


# --- Train / test split ------------------------------------------------------------------------------

def split_drive_pairs(subject_lat, subject_lon, drive_sets=None, should_rebuild=False):
    """Split the pooled pairs (every draw's pairs with a Google time, as join_drive_sets keeps)
    once into a training and a test half, stratified by draw and grouped by destination hex, then the
    training half into config.DRIVE_CV_FOLDS folds by the same rule. Writes config.DRIVE_SPLIT_PATH:
    draw_no, draw, dest_hex_id, half ("train" / "test"), fold (1..k, training half only).
    Skipped if the file exists: the test half must stay the same pairs."""
    out_path = subject_layers_file(config.DRIVE_SPLIT_PATH, subject_lat, subject_lon)
    if is_already_built([out_path], should_rebuild):
        return pd.read_csv(out_path)
    drive_sets = drive_sets or default_drive_sets(subject_lat, subject_lon)
    set_dfs = []
    for draw, (draw_path, google_path) in drive_sets.items():
        draws_df = pd.read_csv(draw_path, usecols=[DRAW_NO_COL, "dest_hex"])
        latest_df = _latest_fetch_per_pair(pd.read_csv(google_path, usecols=[DRAW_NO_COL, HTTP_STATUS_COL,
                                                                             GOOGLE_DURATION_COL]))
        set_df = draws_df.merge(latest_df, on=DRAW_NO_COL, how="inner", validate="one_to_one")
        set_dfs.append(set_df.assign(**{DRAW_COL: draw}))
    pairs_df = pd.concat(set_dfs, ignore_index=True).rename(columns={"dest_hex": "dest_hex_id"})
    is_fetched = pairs_df[GOOGLE_DURATION_COL].notna() & (pairs_df[GOOGLE_DURATION_COL] > 0)
    pairs_df = pairs_df.loc[is_fetched, [DRAW_NO_COL, DRAW_COL, "dest_hex_id"]].reset_index(drop=True)

    halves = StratifiedGroupKFold(n_splits=config.DRIVE_SPLIT_N_HALVES, shuffle=True,
                                  random_state=config.DRIVE_SPLIT_SEED)
    _, test_ix = next(halves.split(pairs_df, pairs_df[DRAW_COL], pairs_df.dest_hex_id))
    pairs_df["half"] = "train"
    pairs_df.loc[test_ix, "half"] = "test"

    train_df = pairs_df[pairs_df.half == "train"]
    folds = StratifiedGroupKFold(n_splits=config.DRIVE_CV_FOLDS, shuffle=True, random_state=config.DRIVE_SPLIT_SEED)
    pairs_df["fold"] = pd.NA
    for fold, (_, fold_ix) in enumerate(folds.split(train_df, train_df[DRAW_COL], train_df.dest_hex_id), start=1):
        pairs_df.loc[train_df.index[fold_ix], "fold"] = fold
    pairs_df["fold"] = pairs_df["fold"].astype("Int64")

    train_hexes = set(pairs_df.loc[pairs_df.half == "train", "dest_hex_id"])
    assert not train_hexes & set(pairs_df.loc[pairs_df.half == "test", "dest_hex_id"]), "a hex is in both halves"
    print(pd.crosstab(pairs_df.half, pairs_df[DRAW_COL], margins=True))
    print(pd.crosstab(pairs_df.fold, pairs_df[DRAW_COL], margins=True))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pairs_df.to_csv(out_path, index=False)
    print(f"saved {len(pairs_df):,} pairs to {out_path}")
    return pairs_df
