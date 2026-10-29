"""Station fidelity check: at the four weak stations, does R5 use everything the train feed holds?

Claim under test (concepts/transit.md TRN-13, station fidelity check, decided 2026-10-20, user; before the test half
is opened): at Melbourne Central, Richmond, Middle Footscray and Patterson the pathways network (v2,
transit_pathway_network_v2.py) misses Google's walks more than elsewhere (transit_pathway_check 2026-10-18: match
0.64, 0.46, 0/7, 0/5; elsewhere mostly >= 0.75). A feed fact R5 misses is fixed on principle, as pathways; no
per-station offset fitted to Google's errors. If R5 already uses all the feed holds, the misses stay a stated cost.
Where the pipeline would rely on it: the pathways network behind transit bands 1-2 (SCR-1, RCH-1).

Method (Claude's, user OK 2026-10-20). Sides: every scored side of transit_pathway_check (status ok) at the four
stations. Per side:
  Google's walk: the default route's encoded polyline (the raw answers keep no per-step geometry), cut at the
    vertex nearest Google's train stop: start -> stop for boarding, stop -> end for alighting. Time: Google's walk
    steps (google_walk_s of the check).
  R5's walk: r5py DetailedItineraries, walk-only, WALK_SPEED_KMH, on v2's network of the side's release (derived
    extract and moved train feed), end <-> the platform stop as v2 placed it (its stub's far end). R5's entrance:
    the feed entrance nearest the first point of R5's route that lies on an added (pathway) way.
  Google's entrance: the feed entrance of the station nearest Google's walk polyline (segment distance).
  Feed times: shortest pathways time in the side's direction (entrance -> platform boarding, platform -> entrance
    alighting) beside v2's spur time (mean of both directions, shortest over the hub's platforms).
  OSM: Google's walk within STATION_ZONE_M of the station, resampled every RESAMPLE_M, each point labelled by the
    nearest OSM way within OSM_NEAR_M: R5-walkable (WALKABLE_HIGHWAYS, access allowed), other (any other way with
    a highway, indoor or platform tag: indoor corridors, private or no-foot ways, platforms) or none.
    Approximate: R5's own permission labeller is not called.
Rules (Claude's, written before any result; diff = R5 walk - Google walk):
  match: |diff| <= MATCH_TOLERANCE_S (as transit_pathway_check). Each non-match gets the first class that fits:
  (a) direction: R5's entrance -> platform feed time in the side's direction differs from v2's two-way mean by
      > DIRECTION_GAP_S: R5 misreads a feed fact (one-way escalators, fare gates). Fixable on principle.
  (b) feed gap: Google's walk passes no feed entrance within ENTRANCE_NEAR_M: Google uses a way in the feed doesn't
      list. (b1) if >= OTHER_RUN_M of Google's walk in the zone lies near only "other" OSM ways (a path OSM holds
      that R5 does not walk: a candidate fix, checked by eye on the map); else (b2) (not in OSM either: a cost).
  (c) same entrance as R5: the feed's time and Google's disagree (a cost).
  (d) different feed entrance than R5: Google picks an entrance the feed's times rank lower (a cost), or R5's
      street walk to it differs (reported: feed time and R5 walk via Google's entrance).
  Google's entrance is "ambiguous" when the second-nearest entrance is within AMBIGUOUS_GAP_M of the nearest.
Caveat: Google's polyline is simplified; Google may itself read this feed's pathways.

Conclusion (run 2026-10-20): R5 already uses everything the feed holds at the four stations; no GTFS-faithful fix
  exists, so their misses stay a stated cost. 97 sides (50 / 35 / 7 / 5), all routed; match 33 / 12 / 0 / 0.
  (a) direction 0: v2's two-way spur time is within 15 s of the one-way feed time on every side.
  (b) feed gap 0: Google's walk passes a feed entrance at ~0 m median at every station (Google uses the feed's
      entrance points); no Google walk runs on OSM ways R5 cannot walk (no mall or indoor shortcut at these four).
  (c) / (d) only: the feed's in-station times and Google's disagree. Split at the entrance, Google's in-station time
      (medians) vs the feed's: Middle Footscray 60 vs 156 s, Patterson ~0 vs 138 s, Richmond 131 vs 174 s; at these
      three Google's time is closer to its straight in-station line at walking speed (|Google - line| 26 / 75 / 23 s)
      than to the feed (96 / 143 / 45 s). Melbourne Central the other way: Google 191 s vs feed 120 s, closer to the
      feed (26 s) than to the line (108 s). Richmond's (d): Google boards via EN1 (south), R5 via EN4, the feed
      ranking EN1 dearer. Reading (hunch): Google does not take the feed's traversal times at surface stations;
      at Melbourne Central it charges more than the feed. Small n at Middle Footscray / Patterson; the split rests
      on Google's simplified polyline and on 4.16 km/h for Google's street part (Patterson's negative times show
      its limit).

All stations (user, 2026-10-20: "a full minute is no joke"; `all` mode): every station with scored sides in
transit_pathway_check (167 stations, 1,249 sides), no new routing: per side the in-station split above, against
Google's nearest feed entrance (sides whose walk passes no entrance within ENTRANCE_NEAR_M are counted apart).
Station type from the feed: multi-level if any of its pathways is an escalator or a lift (MULTI_LEVEL_MODES), else
surface (a proxy: a surface station with a lift to an overpass counts as multi-level). Hard misses: the own-date
stage 1 misses of the reported model whose pair has a side at the station.
Rules (Claude's, user OK in outline, written before any result):
  disagreeing station: n >= MIN_STATION_N sides and median |Google - feed| in-station time > MATCH_TOLERANCE_S.
  The pattern (Google follows the straight line at surface stations, the feed at multi-level ones) holds if, pooled
  over each type, Google is closer to the line than to the feed on >= PATTERN_SHARE of surface sides and closer to
  the feed on >= PATTERN_SHARE of multi-level sides.
  Read-out only: no fix follows from it (GTFS-faithful rule, TRN-13); Google is not ground truth.
Conclusion, all stations (run 2026-10-20): Google mostly agrees with the feed; the minute is a station-specific
  exception, not a pattern. 1,249 sides at 167 stations, 1,240 usable. Google - feed in-station: median -10 s,
  quartiles -28 / +7 s, |gap| median 19 s, |gap| > 60 s on 0.147 of sides. Many stations agree to a few seconds
  (Glenferrie 112 vs 114 s, Essendon 137 vs 138, Burnley 140 vs 144), so Google very likely reads PTV's pathways.
  Pattern (Claude's hunch): multi-level closer to the feed on 0.698 (holds); surface closer to the line on only
  0.395: does not hold (surface stations also follow the feed). Judged stations (n >= 5): 79; station medians of
  |gap| quartiles 11 / 19 / 30 s; disagreeing 11 (106 sides): Patterson, Balaclava, Town Hall, Footscray,
  Gardenvale, Middle Footscray, Carnegie, Windsor, Dandenong, Anzac, Jolimont-MCG; Google shorter than the feed at 9,
  longer at Town Hall and Anzac (Metro Tunnel). Richmond (45 s) and Melbourne Central (26 s) are under the bar.
  Output effect: 5 of the reported model's 30 own-date hard misses have a side at any train station with Google
  data; 3 of those sides are at disagreeing stations.

Why does Google drop or replace pathways at some stations? (`why` mode; user 2026-10-20: Google's rule is unknown,
user's hunch: historical data.) Groups: "no-pathway" stations (disagreeing, Google closer to R5 without pathways
than with: median |diff_no_path_s| < median |diff_s| in transit_pathway_check), other disagreeing, and agreeing.
Three free tests, reading rules Claude's, written before any result:
  (1) implausible data: per station, the feed's implied speed (straight entrance -> platform metres / one-way time,
      median over entrance-platform pairs). Supports "Google rejects it" if every no-pathway station lies below the
      SLOW_PERCENTILE of the agreeing stations' speeds.
  (2) feed version: the 2026-08-28 PTV train feed (frozen_inputs/gtfs_ptv/metro_train). Supports "Google is on
      another version" if at a no-pathway station the older feed has no pathways, or its time to the used platform
      is within MATCH_TOLERANCE_S of Google's in-station time where the current feed is not.
  (3) time of day: Google's in-station time per (station, platform, entrance, side) group with >= MIN_GROUP_N sides:
      spread (sd) and peak minus off-peak median (PEAK_WINDOWS_MIN). Time-varying (live or time-dependent observed
      data) if the median group sd at disagreeing stations exceeds VARYING_SD_S or peak - off-peak exceeds it.
      Limit: a static value learned from history would also be constant, so (3) can only rule out time-varying use.
Conclusion, why (run 2026-10-20): none of the three explains it; what Google does at the 11 is static and
  station-specific, from a source we cannot see. No-pathway: Balaclava, Carnegie, Middle Footscray, Patterson, Windsor.
  (1) not supported: their implied speeds (0.30-0.88 m/s) sit in the agreeing range (median 0.53, 10th pct 0.32);
      the slowest feed data (Town Hall 0.21, Anzac 0.23) is where Google charges more than the feed, not less.
  (2) not supported: the 2026-08-28 feed has the same times at all 11 stations.
  (3) not time-varying: Google's in-station time within a (station, platform, entrance, side) group has median sd
      3-4 s at the disagreeing stations (11 s at agreeing ones), peak minus off-peak +0 s in every group. A static
      override (Google's own station data, or a value learned once from history) stays possible and untestable here.

Inputs (read only): transit_pathway_check's table (newest), transit_hard_miss_range's results (newest; default_ix),
the Google raw answers (train, second batch and top-up only: never the test half), v2's derived extracts, moved
feeds, hubs and spurs tables, the cleaned 2026-10-09 train feed and the frozen OSM extract. Self-contained (D1).
No API calls. Saved data (reused if present, with its date): sides (extract), OSM ways (osm), R5 routes (route).
Usage: `python transit_station_fidelity.py extract`, `... osm`, `... route 20261009`, `... route 20261016` (one
network per process), then `... report`.
"""
import datetime
import heapq
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PBF_PATH = PROJECT_ROOT / "frozen_inputs" / "osm_extract" / "planet_143.599,-38.893_146.327,-36.735.osm.pbf"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
NAME = "transit_station_fidelity"
V2_NAME = "transit_pathway_network_v2"
PATHWAY_CHECK_NAME = "transit_pathway_check"
RANGE_NAME = "transit_hard_miss_range"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
CLEANED_TRAIN_PATHS = {"20261009": PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned" / f"{TRAIN_FEED}.zip",
                       "20261016": DIAGNOSTIC_DATA_DIR / "transit_band_metric_gtfs_cleaned_20261016" / f"{TRAIN_FEED}.zip"}
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
RAW_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl",
             "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.raw.jsonl",
             "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.raw.jsonl"}

# --- stations and rules ----------------------------------------------------------------------------
STATIONS = {"Melbourne Central": "vic:rail:MCE", "Richmond": "vic:rail:RMD",
            "Middle Footscray": "vic:rail:MFY", "Patterson": "vic:rail:PAT"}
MATCH_TOLERANCE_S = 60                 # as transit_pathway_check (user: +-1 min)
DIRECTION_GAP_S = 30                   # (a): one-way feed time vs v2's two-way mean
ENTRANCE_NEAR_M = 30                   # (b): Google's walk passes a feed entrance within this
AMBIGUOUS_GAP_M = 10                   # second-nearest entrance this close to the nearest: ambiguous
STATION_ZONE_M = 250                   # Google's walk looked at within this of the parent station
RESAMPLE_M = 5
OSM_NEAR_M = 10                        # a walk point is "on" a way within this
OTHER_RUN_M = 20                       # (b1): Google's walk near only "other" ways for at least this
OLD_TRAIN_PATH = PROJECT_ROOT / "frozen_inputs" / "gtfs_ptv" / "metro_train" / "google_transit.zip"   # 2026-08-28 feed
SLOW_PERCENTILE = 10                   # why (1)
MIN_GROUP_N = 3                        # why (3)
VARYING_SD_S = 30                      # why (3)
PEAK_WINDOWS_MIN = [(420, 570), (960, 1140)]   # why (3): weekday peaks 07:00-09:30 and 16:00-19:00, minutes of day
MIN_STATION_N = 5                     # all mode: a station is judged with at least this many sides
PATTERN_SHARE = 2 / 3                  # all mode: share of sides for the surface / multi-level pattern
MULTI_LEVEL_MODES = {"4", "5"}         # escalator, elevator (GTFS pathway_mode)
REPORTED_MODEL = "no-wait plain (reported)"
OWN_DATE_MISSES_PATTERN = f"{V2_NAME}_2*_range_owndate_misses.csv"
FETCH_M = 600                         # OSM ways fetched within this of a station
HUB_MATCH_DEG = 2e-7                   # v2 hub keys are 7-decimal strings; float rounding can move the last digit

# --- r5py and geometry -----------------------------------------------------------------------------
R5_MAX_MEMORY = "7G"
WINDOW_DATE = datetime.date(2026, 10, 21)
WALK_SPEED_KMH = 4.16
KMH_PER_MS = 3.6
WALK_SPEED_MS = WALK_SPEED_KMH / KMH_PER_MS
WALKABLE_HIGHWAYS = {"footway", "path", "pedestrian", "steps", "living_street", "residential", "service",
                     "unclassified", "tertiary", "tertiary_link", "secondary", "secondary_link", "primary",
                     "primary_link", "trunk", "trunk_link", "track", "cycleway", "road", "corridor"}   # as v2
NO_ACCESS = {"no", "private"}
FOOT_ALLOWED = {"yes", "designated", "permissive"}
OTHER_KEYS = ["highway", "indoor", "railway", "public_transport"]   # an "other" way carries one of these
TAG_SOURCE = ("platica", "pathway")
ENTRANCE_TYPE, STATION_TYPE = "2", "1"
NON_PLATFORM_TYPES = [ENTRANCE_TYPE, STATION_TYPE, "3", "4"]   # entrance, station, generic node, boarding area
ON_ADDED_WAY_M = 1.0                   # a route point lies on an added (pathway) way within this
ZERO_LENGTH_GUARD = 1e-12              # squared segment length used for zero-length segments
ELEVATOR_MODE = "5"
HEAVY_RAIL = "HEAVY_RAIL"
GTFS_ENCODING = "utf-8-sig"
METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON_EQUATOR = 111_320.0
POLYLINE_PRECISION = 1e5
ZOOM_M = 220                           # map half-width
GREY, ORANGE, RED, BLUE, GREEN, INK = "#9a9a9a", "#e08a00", "#d62728", "#1f5fbf", "#2ca02c", "#222222"
FIGURE_SIZE_IN = (8, 8)
DPI = 150


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def reuse(pattern):
    saved = newest(pattern)
    if saved:
        print(f"reusing {saved.name} ({datetime.date.fromtimestamp(saved.stat().st_mtime)})", flush=True)
    return saved


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def local_xy(lat, lon, lat0, lon0):
    return ((np.asarray(lon, dtype=float) - lon0) * METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0)),
            (np.asarray(lat, dtype=float) - lat0) * METRES_PER_DEG_LAT)


def parse_coords(text):
    return np.array([float(value) for value in str(text).split()])


def decode_polyline(encoded):
    """Google's encoded polyline -> (lats, lons)."""
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
    return np.array([c[0] for c in coords]), np.array([c[1] for c in coords])


def point_polyline_m(px, py, xs, ys):
    """Distance from each point (px, py) to the polyline (xs, ys), all in metres."""
    px, py = np.atleast_1d(px), np.atleast_1d(py)
    if len(xs) == 1:
        return np.hypot(px - xs[0], py - ys[0])
    ax, ay, bx, by = xs[:-1], ys[:-1], xs[1:], ys[1:]
    dx, dy = bx - ax, by - ay
    seg_sq = np.where(dx * dx + dy * dy == 0, ZERO_LENGTH_GUARD, dx * dx + dy * dy)
    t = np.clip(((px[:, None] - ax) * dx + (py[:, None] - ay) * dy) / seg_sq, 0, 1)
    return np.hypot(px[:, None] - (ax + t * dx), py[:, None] - (ay + t * dy)).min(axis=1)


def resample(xs, ys, step_m):
    lengths = np.hypot(np.diff(xs), np.diff(ys))
    cumulative = np.concatenate([[0], np.cumsum(lengths)])
    if cumulative[-1] == 0:
        return xs[:1], ys[:1]
    at = np.arange(0, cumulative[-1] + step_m / 2, step_m)
    return np.interp(at, cumulative, xs), np.interp(at, cumulative, ys)


# --- feed ------------------------------------------------------------------------------------------
def shortest_from(edges, source):
    best = {source: 0.0}
    queue = [(0.0, source)]
    while queue:
        cost, node = heapq.heappop(queue)
        if cost > best[node]:
            continue
        for neighbour, time_s in edges.get(node, []):
            if neighbour not in best or cost + time_s < best[neighbour]:
                best[neighbour] = cost + time_s
                heapq.heappush(queue, (cost + time_s, neighbour))
    return best


def feed_tables(release, station_ids=None):
    """Stops of the stations (default: the four) and directional pathway times entrance <-> platform (with / without
    elevators)."""
    with zipfile.ZipFile(CLEANED_TRAIN_PATHS[release]) as gtfs_zip:
        stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype=str, encoding=GTFS_ENCODING)
        pathways_df = pd.read_csv(gtfs_zip.open("pathways.txt"), dtype=str, encoding=GTFS_ENCODING)
    stops_df["stop_lat"] = stops_df.stop_lat.astype(float)
    stops_df["stop_lon"] = stops_df.stop_lon.astype(float)
    station_ids = set(STATIONS.values()) if station_ids is None else set(station_ids)
    stops_df = stops_df[stops_df.stop_id.isin(station_ids) | stops_df.parent_station.isin(station_ids)].copy()
    stops_df["station_id"] = np.where(stops_df.stop_id.isin(station_ids), stops_df.stop_id, stops_df.parent_station)
    rows = []
    for is_no_elevator in (False, True):
        forward, backward = {}, {}
        for row in pathways_df.itertuples():
            if is_no_elevator and row.pathway_mode == ELEVATOR_MODE:
                continue
            pairs = [(row.from_stop_id, row.to_stop_id)] + ([(row.to_stop_id, row.from_stop_id)] if row.is_bidirectional == "1" else [])
            for start, end in pairs:
                forward.setdefault(start, []).append((end, float(row.traversal_time)))
                backward.setdefault(end, []).append((start, float(row.traversal_time)))
        platforms = stops_df[~stops_df.location_type.fillna("0").isin(NON_PLATFORM_TYPES)]
        for platform in platforms.itertuples():
            out_s = shortest_from(forward, platform.stop_id)
            in_s = shortest_from(backward, platform.stop_id)
            for entrance in stops_df[(stops_df.location_type == ENTRANCE_TYPE) & (stops_df.station_id == platform.station_id)].itertuples():
                rows.append({"is_no_elevator": is_no_elevator, "platform_id": platform.stop_id, "entrance_id": entrance.stop_id,
                             "in_s": in_s.get(entrance.stop_id, np.nan), "out_s": out_s.get(entrance.stop_id, np.nan)})
    return stops_df, pd.DataFrame(rows)


# --- extract ---------------------------------------------------------------------------------------
def extract(is_all=False):
    """Sides at the four stations (or every station: is_all) with Google's walk geometry cut from the default route's
    polyline (saved)."""
    suffix = "sides_all" if is_all else "sides"
    if reuse(f"{NAME}_*_{suffix}.csv"):
        return
    check_df = pd.read_csv(newest(f"{PATHWAY_CHECK_NAME}_2*_table.csv"), dtype={"platform_id": str, "entrance_id": str})
    sides_df = check_df[(check_df.status == "ok") & (is_all | check_df.stop_name.isin(STATIONS))].reset_index(drop=True)
    results_df = pd.read_csv(newest(f"{RANGE_NAME}_2*_results.csv"), usecols=["set_name", "draw_no", "default_ix"])
    sides_df = sides_df.merge(results_df, on=["set_name", "draw_no"], how="left", validate="many_to_one")
    wanted = set(zip(sides_df.set_name, sides_df.draw_no))
    geometry = {}
    for set_name, path in RAW_PATHS.items():
        with open(path, encoding="utf-8") as file:
            for line in file:
                record = json.loads(line)
                if (set_name, record["draw_no"]) not in wanted:
                    continue
                ix = int(sides_df.default_ix[(sides_df.set_name == set_name) & (sides_df.draw_no == record["draw_no"])].iloc[0])
                route = record["resp"]["routes"][ix]
                lats, lons = decode_polyline(route["polyline"]["encodedPolyline"])
                steps = route["legs"][0]["steps"]
                transit = [step for step in steps if step.get("travelMode") == "TRANSIT"]
                for side, step, stop_key in [("board", transit[0], "departureStop"), ("alight", transit[-1], "arrivalStop")]:
                    location = step["transitDetails"]["stopDetails"][stop_key]["location"]["latLng"]
                    xs, ys = local_xy(lats, lons, location["latitude"], location["longitude"])
                    cut = int(np.argmin(np.hypot(xs, ys)))
                    part = slice(0, cut + 1) if side == "board" else slice(cut, len(lats))
                    geometry[(set_name, record["draw_no"], side)] = (" ".join(f"{v:.6f}" for v in lats[part]),
                                                                     " ".join(f"{v:.6f}" for v in lons[part]))
    keys = list(zip(sides_df.set_name, sides_df.draw_no, sides_df.side))
    sides_df["google_lats"] = [geometry.get(key, ("", ""))[0] for key in keys]
    sides_df["google_lons"] = [geometry.get(key, ("", ""))[1] for key in keys]
    print(f"{len(sides_df)} sides; Google geometry for {int((sides_df.google_lats != '').sum())}", flush=True)
    sides_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_{suffix}.csv", index=False)


# --- OSM -------------------------------------------------------------------------------------------
def is_r5_walkable(tags):
    if tags.get("highway") not in WALKABLE_HIGHWAYS or tags.get("area") == "yes":
        return False
    if tags.get("foot") in NO_ACCESS:
        return False
    return not (tags.get("access") in NO_ACCESS and tags.get("foot") not in FOOT_ALLOWED)


def osm():
    """Ways near the four stations: frozen extract (all tags) plus v2's added pathway ways, both releases (saved)."""
    if reuse(f"{NAME}_*_ways.csv"):
        return
    import osmium
    stops_df, _ = feed_tables("20261009")
    centres = stops_df[stops_df.location_type == STATION_TYPE][["stop_lat", "stop_lon"]].to_numpy()
    lat_pad = FETCH_M / METRES_PER_DEG_LAT

    def is_near(lats, lons):
        for lat0, lon0 in centres:
            lon_pad = FETCH_M / (METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0)))
            if any(abs(lat - lat0) <= lat_pad and abs(lon - lon0) <= lon_pad for lat, lon in zip(lats, lons)):
                return True
        return False

    rows = []
    sources = [("frozen", PBF_PATH)] + [(f"added_{release}", DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{release}.osm.pbf")
                                        for release in CLEANED_TRAIN_PATHS]
    for source, path in sources:
        for obj in osmium.FileProcessor(str(path)).with_locations():
            if not obj.is_way():
                continue
            tags = dict(obj.tags)
            is_added = tags.get(TAG_SOURCE[0]) == TAG_SOURCE[1]
            if source == "frozen" and not any(key in tags for key in OTHER_KEYS):
                continue
            if source != "frozen" and not is_added:
                continue
            if not all(node.location.valid() for node in obj.nodes):
                continue
            lats = [node.lat for node in obj.nodes]
            lons = [node.lon for node in obj.nodes]
            if not is_near(lats, lons):
                continue
            rows.append({"source": source, "way_id": obj.id, "is_r5_walkable": is_r5_walkable(tags) or is_added,
                         "tags": json.dumps(tags), "lats": " ".join(f"{v:.7f}" for v in lats),
                         "lons": " ".join(f"{v:.7f}" for v in lons)})
        print(f"{source}: {sum(row['source'] == source for row in rows)} ways", flush=True)
    pd.DataFrame(rows).to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_ways.csv", index=False)


# --- R5 routes -------------------------------------------------------------------------------------
def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (as transit_pathway_network_v2)."""
    import hashlib
    from r5py.util.config import Config
    for path in paths:
        cached = Path(Config().CACHE_DIR) / Path(path).name
        if not cached.exists():
            continue
        digests = []
        for candidate in (path, cached):
            with open(candidate, "rb") as file:
                digests.append(hashlib.file_digest(file, "blake2s").hexdigest())
        assert digests[0] == digests[1], f"r5py's cached {cached} differs from {path}: stale working copy"


def moved_stop(sides_df, release):
    """v2's platform stop position (its stub's far end) for each side's feed platform."""
    hubs_df = pd.read_csv(newest(f"{V2_NAME}_2*_hubs_{release}.csv")).set_index("hub")
    hub = sides_df.platform_lat.round(7).astype(str) + "," + sides_df.platform_lon.round(7).astype(str)
    assert hub.isin(hubs_df.index).all(), f"platforms without a v2 hub: {sorted(set(hub[~hub.isin(hubs_df.index)]))}"
    return hubs_df.loc[hub, "stop_lat"].to_numpy(), hubs_df.loc[hub, "stop_lon"].to_numpy()


def route(release):
    """R5 walk-only route end <-> v2 platform stop, per side of this release (saved, one file per release)."""
    if reuse(f"{NAME}_*_routes_{release}.csv"):
        return
    sides_df = pd.read_csv(newest(f"{NAME}_2*_sides.csv"))
    sides_df = sides_df[sides_df.release.astype(str) == release].reset_index(drop=True)
    stop_lat, stop_lon = moved_stop(sides_df, release)
    sys.argv += ["--max-memory", R5_MAX_MEMORY]
    import geopandas as gpd
    from r5py import DetailedItineraries, TransportMode, TransportNetwork
    gtfs_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{release}"
    paths = [gtfs_dir / (f"{name}_{V2_NAME}_{release}_moved.zip" if name == TRAIN_FEED else f"{name}_{V2_NAME}_{release}.zip")
             for name in FEED_NAMES]
    pbf_path = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{release}.osm.pbf"
    assert pbf_path.exists() and all(path.exists() for path in paths)
    check_working_copies([pbf_path] + paths)
    network = TransportNetwork(pbf_path, paths)
    is_board = (sides_df.side == "board").to_numpy()
    origins = gpd.GeoDataFrame({"id": sides_df.index}, crs="EPSG:4326", geometry=gpd.points_from_xy(
        np.where(is_board, sides_df.end_lon, stop_lon), np.where(is_board, sides_df.end_lat, stop_lat)))
    destinations = gpd.GeoDataFrame({"id": sides_df.index}, crs="EPSG:4326", geometry=gpd.points_from_xy(
        np.where(is_board, stop_lon, sides_df.end_lon), np.where(is_board, stop_lat, sides_df.end_lat)))
    di_df = pd.DataFrame(DetailedItineraries(network, origins=origins, destinations=destinations,
                                             departure=datetime.datetime.combine(WINDOW_DATE, datetime.time(12)),
                                             transport_modes=[TransportMode.WALK], speed_walking=WALK_SPEED_KMH))
    di_df = di_df[di_df.from_id == di_df.to_id]
    rows = []
    for side_ix, group in di_df.groupby("from_id"):
        group = group[group.option == group.option.min()].sort_values("segment")
        lats, lons = [], []
        for geometry in group.geometry:
            for part in getattr(geometry, "geoms", [geometry]):   # r5py returns MultiLineString for some legs
                lons += [point[0] for point in part.coords]
                lats += [point[1] for point in part.coords]
        rows.append({"set_name": sides_df.set_name[side_ix], "draw_no": sides_df.draw_no[side_ix], "side": sides_df.side[side_ix],
                     "r5_s": group.travel_time.dt.total_seconds().sum(), "r5_m": group.distance.sum(),
                     "stop_lat": stop_lat[side_ix], "stop_lon": stop_lon[side_ix],
                     "r5_lats": " ".join(f"{v:.7f}" for v in lats), "r5_lons": " ".join(f"{v:.7f}" for v in lons)})
    out_df = pd.DataFrame(rows)
    print(f"release {release}: {len(out_df)} / {len(sides_df)} sides routed", flush=True)
    out_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_routes_{release}.csv", index=False)


# --- report ----------------------------------------------------------------------------------------
def entrance_distances(lats, lons, entrances_df, lat0, lon0):
    xs, ys = local_xy(lats, lons, lat0, lon0)
    ex, ey = local_xy(entrances_df.stop_lat, entrances_df.stop_lon, lat0, lon0)
    return pd.Series(point_polyline_m(ex, ey, xs, ys), index=entrances_df.stop_id).sort_values()


def r5_entrance(lats, lons, added_ways, entrances_df, lat0, lon0, is_board):
    """Feed entrance nearest the first point (from the street end) of R5's route lying on an added way."""
    xs, ys = local_xy(lats, lons, lat0, lon0)
    order = range(len(xs)) if is_board else range(len(xs) - 1, -1, -1)
    for i in order:
        if min(point_polyline_m(xs[i], ys[i], wx, wy)[0] for wx, wy in added_ways) <= ON_ADDED_WAY_M:
            ex, ey = local_xy(entrances_df.stop_lat, entrances_df.stop_lon, lat0, lon0)
            distances = np.hypot(ex - xs[i], ey - ys[i])
            return entrances_df.stop_id.iloc[int(np.argmin(distances))], float(distances.min())
    return "", np.nan


def zone_cover(lats, lons, ways, lat0, lon0):
    """Metres of Google's walk within STATION_ZONE_M by nearest-way label (r5 / other / none), and the longest 'other' run."""
    xs, ys = local_xy(lats, lons, lat0, lon0)
    px, py = resample(xs, ys, RESAMPLE_M)
    is_zone = np.hypot(px, py) <= STATION_ZONE_M
    px, py = px[is_zone], py[is_zone]
    if not len(px):
        return {"zone_m": 0.0, "on_r5_m": 0.0, "on_other_m": 0.0, "on_none_m": 0.0, "other_run_m": 0.0}
    near_r5 = np.full(len(px), np.inf)
    near_other = np.full(len(px), np.inf)
    for wx, wy, is_walk in ways:
        distances = np.array([point_polyline_m(x, y, wx, wy)[0] for x, y in zip(px, py)])
        if is_walk:
            near_r5 = np.minimum(near_r5, distances)
        else:
            near_other = np.minimum(near_other, distances)
    label = np.where(near_r5 <= OSM_NEAR_M, "r5", np.where(near_other <= OSM_NEAR_M, "other", "none"))
    run, longest = 0, 0
    for value in label:
        run = run + 1 if value == "other" else 0
        longest = max(longest, run)
    return {"zone_m": len(px) * RESAMPLE_M, "on_r5_m": float((label == "r5").sum() * RESAMPLE_M),
            "on_other_m": float((label == "other").sum() * RESAMPLE_M), "on_none_m": float((label == "none").sum() * RESAMPLE_M),
            "other_run_m": float(longest * RESAMPLE_M)}


def classify(row):
    if abs(row.diff_s) <= MATCH_TOLERANCE_S:
        return "match"
    if abs(row.direction_gap_s) > DIRECTION_GAP_S:
        return "a direction"
    if row.google_entrance_m > ENTRANCE_NEAR_M:
        return "b1 OSM-only path" if row.other_run_m >= OTHER_RUN_M else "b2 not in feed or OSM"
    if row.google_entrance == row.r5_entrance:
        return "c same entrance, time differs"
    return "d different entrance"


def report():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sides_df = pd.read_csv(newest(f"{NAME}_2*_sides.csv"), dtype={"platform_id": str, "entrance_id": str})
    routes_df = pd.concat([pd.read_csv(newest(f"{NAME}_2*_routes_{release}.csv")) for release in CLEANED_TRAIN_PATHS])
    sides_df = sides_df.merge(routes_df, on=["set_name", "draw_no", "side"], how="left", validate="one_to_one")
    ways_df = pd.read_csv(newest(f"{NAME}_2*_ways.csv"))
    lines, rows = [], []
    for station, station_id in STATIONS.items():
        station_sides = sides_df[sides_df.station_id == station_id]
        for release in sorted(station_sides.release.astype(str).unique()):
            stops_df, times_df = feed_tables(release)
            spurs_df = pd.read_csv(newest(f"{V2_NAME}_2*_spurs_{release}.csv"))
            spurs_df = spurs_df[spurs_df.kind == "entrance"].copy()
            spurs_df[["end_lat", "end_lon"]] = spurs_df.end.str.split(",", expand=True).astype(float)
            parent = stops_df[stops_df.stop_id == station_id].iloc[0]
            lat0, lon0 = parent.stop_lat, parent.stop_lon
            entrances_df = stops_df[(stops_df.location_type == ENTRANCE_TYPE) & (stops_df.station_id == station_id)]
            source = f"added_{release}"
            near_ways_df = ways_df[ways_df.source.isin(["frozen", source])]
            ways = []
            for way in near_ways_df.itertuples():
                wx, wy = local_xy(parse_coords(way.lats), parse_coords(way.lons), lat0, lon0)
                if np.hypot(wx, wy).min() <= STATION_ZONE_M + FETCH_M / 2:
                    ways.append((wx, wy, bool(way.is_r5_walkable), way.source == source))
            added = [(wx, wy) for wx, wy, _, is_added in ways if is_added]
            for side in station_sides[station_sides.release.astype(str) == release].itertuples():
                is_board = side.side == "board"
                g_lats, g_lons = parse_coords(side.google_lats), parse_coords(side.google_lons)
                g_dist = entrance_distances(g_lats, g_lons, entrances_df, lat0, lon0)
                r_entrance, r_entrance_m = r5_entrance(parse_coords(side.r5_lats), parse_coords(side.r5_lons), added,
                                                       entrances_df, lat0, lon0, is_board)
                direction = "in_s" if is_board else "out_s"
                feed = times_df[~times_df.is_no_elevator & (times_df.platform_id == side.platform_id)].set_index("entrance_id")
                is_hub = ((spurs_df.end_lat - side.platform_lat).abs() < HUB_MATCH_DEG) & ((spurs_df.end_lon - side.platform_lon).abs() < HUB_MATCH_DEG)
                spur = spurs_df[is_hub].set_index("start").time_s
                cover = zone_cover(g_lats, g_lons, [(wx, wy, is_walk) for wx, wy, is_walk, _ in ways], lat0, lon0)
                google_entrance = g_dist.index[0]
                entrance = entrances_df.set_index("stop_id").loc[google_entrance]
                gx, gy = local_xy(g_lats, g_lons, entrance.stop_lat, entrance.stop_lon)
                cut = int(np.argmin(np.hypot(gx, gy)))
                steps_m = np.hypot(np.diff(gx), np.diff(gy))
                street_m, inside_m = (steps_m[:cut].sum(), steps_m[cut:].sum()) if is_board else (steps_m[cut:].sum(), steps_m[:cut].sum())
                rows.append({"station": station, "set_name": side.set_name, "draw_no": side.draw_no, "release": release,
                             "side": side.side, "platform_id": side.platform_id, "google_walk_s": side.google_walk_s,
                             "google_walk_m": side.google_walk_m, "r5_s": side.r5_s, "r5_m": side.r5_m,
                             "diff_s": side.r5_s - side.google_walk_s, "check_diff_s": side.diff_s,
                             "google_entrance": google_entrance, "google_entrance_m": g_dist.iloc[0],
                             "is_ambiguous": len(g_dist) > 1 and g_dist.iloc[1] - g_dist.iloc[0] <= AMBIGUOUS_GAP_M,
                             "r5_entrance": r_entrance, "r5_entrance_m": r_entrance_m,
                             "feed_r5_entrance_s": feed[direction].get(r_entrance, np.nan),
                             "spur_r5_entrance_s": spur.get(r_entrance, np.nan),
                             "direction_gap_s": feed[direction].get(r_entrance, np.nan) - spur.get(r_entrance, np.nan),
                             "feed_google_entrance_s": feed[direction].get(google_entrance, np.nan),
                             "spur_google_entrance_s": spur.get(google_entrance, np.nan),
                             "google_street_m": street_m, "google_inside_m": inside_m,
                             "google_inside_s": side.google_walk_s - street_m / WALK_SPEED_MS,
                             "inside_at_walk_s": inside_m / WALK_SPEED_MS, **cover})
            draw_map(plt, station, release, station_sides[station_sides.release.astype(str) == release], ways,
                     stops_df[stops_df.station_id == station_id], lat0, lon0)
    table_df = pd.DataFrame(rows)
    table_df["direction_gap_s"] = table_df.direction_gap_s.fillna(0)
    table_df["class"] = table_df.apply(classify, axis=1)
    table_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_table.csv", index=False)
    lines.append(f"Station fidelity check, run {run_date()} (rules in the docstring, set before results)")
    lines.append(f"sides {len(table_df)}; routed {int(table_df.r5_s.notna().sum())}")
    for station, group in table_df.groupby("station", sort=False):
        lines.append(f"\n== {station}: {len(group)} sides; match {int((group['class'] == 'match').sum())}; "
                     f"diff median {group.diff_s.median():+.0f} s (check {group.check_diff_s.median():+.0f} s)")
        lines.append("  classes: " + ", ".join(f"{k} {v}" for k, v in group["class"].value_counts().items()))
        for side_name, part in group.groupby("side"):
            lines.append(f"  {side_name}: n {len(part)}, diff median {part.diff_s.median():+.0f} s, "
                         f"Google entrances {part.google_entrance.value_counts().to_dict()}, "
                         f"R5 entrances {part.r5_entrance.value_counts().to_dict()}, "
                         f"Google entrance m median {part.google_entrance_m.median():.0f}, ambiguous {int(part.is_ambiguous.sum())}")
        lines.append(f"  in-station (Google's walk split at its entrance; Google's time = its walk - street part at walking speed), "
                     f"medians: Google {group.google_inside_s.median():.0f} s, its in-station line at walking speed "
                     f"{group.inside_at_walk_s.median():.0f} s, feed {group.feed_google_entrance_s.median():.0f} s; "
                     f"|Google - line| {(group.google_inside_s - group.inside_at_walk_s).abs().median():.0f} s, "
                     f"|Google - feed| {(group.google_inside_s - group.feed_google_entrance_s).abs().median():.0f} s")
        lines.append(f"  zone metres of Google's walk: r5 {group.on_r5_m.sum():.0f}, other {group.on_other_m.sum():.0f}, "
                     f"none {group.on_none_m.sum():.0f}; direction gap > {DIRECTION_GAP_S} s on {int((group.direction_gap_s.abs() > DIRECTION_GAP_S).sum())}")
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_summary.txt").write_text(summary + "\n", encoding="utf-8", newline="\n")


def draw_map(plt, station, release, sides_df, ways, station_stops_df, lat0, lon0):
    figure, axis = plt.subplots(figsize=FIGURE_SIZE_IN)
    for wx, wy, is_walk, is_added in ways:
        if np.hypot(wx, wy).min() > ZOOM_M * 1.5:
            continue
        colour, width = (RED, 1.6) if is_added else (GREY, 0.8) if is_walk else (ORANGE, 1.0)
        axis.plot(wx, wy, color=colour, linewidth=width, zorder=1)
    for side in sides_df.itertuples():
        gx, gy = local_xy(parse_coords(side.google_lats), parse_coords(side.google_lons), lat0, lon0)
        axis.plot(gx, gy, color=GREEN, linewidth=1.2, alpha=0.6, zorder=2)
        if isinstance(side.r5_lats, str):
            rx, ry = local_xy(parse_coords(side.r5_lats), parse_coords(side.r5_lons), lat0, lon0)
            axis.plot(rx, ry, color=BLUE, linewidth=1.0, alpha=0.5, linestyle="--", zorder=3)
    entrances = station_stops_df[station_stops_df.location_type == ENTRANCE_TYPE]
    ex, ey = local_xy(entrances.stop_lat, entrances.stop_lon, lat0, lon0)
    axis.scatter(ex, ey, color=RED, s=30, zorder=4)
    for name, x, y in zip(entrances.stop_id, ex, ey):
        axis.annotate(name.split("_")[-1], (x, y), fontsize=7, xytext=(3, 3), textcoords="offset points")
    platforms = station_stops_df[~station_stops_df.location_type.fillna("0").isin(NON_PLATFORM_TYPES)]
    px, py = local_xy(platforms.stop_lat, platforms.stop_lon, lat0, lon0)
    axis.scatter(px, py, color=INK, marker="s", s=22, zorder=4)
    axis.scatter([0], [0], color=INK, marker="*", s=90, zorder=5)
    axis.set_xlim(-ZOOM_M, ZOOM_M)
    axis.set_ylim(-ZOOM_M, ZOOM_M)
    axis.set_aspect("equal")
    axis.set_title(f"{station} ({release}): Google walks green, R5 v2 blue dashed;\n"
                   f"grey R5-walkable OSM, orange other OSM, red pathway spurs; squares platforms, dots entrances", fontsize=8)
    axis.set_xlabel("m east")
    axis.set_ylabel("m north")
    DIAGNOSTIC_IMG_DIR.mkdir(exist_ok=True)
    slug = station.lower().replace(" ", "_")
    figure.savefig(DIAGNOSTIC_IMG_DIR / f"{NAME}_{run_date()}_{slug}_{release}.png", dpi=DPI, bbox_inches="tight")
    plt.close(figure)


def station_types(release):
    """station_id -> 'multi-level' if any of its pathways is an escalator or a lift, else 'surface'."""
    with zipfile.ZipFile(CLEANED_TRAIN_PATHS[release]) as gtfs_zip:
        stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype=str, encoding=GTFS_ENCODING)
        pathways_df = pd.read_csv(gtfs_zip.open("pathways.txt"), dtype=str, encoding=GTFS_ENCODING)
    station_of = stops_df.set_index("stop_id").parent_station
    multi_df = pathways_df[pathways_df.pathway_mode.isin(MULTI_LEVEL_MODES)]
    multi_stations = set(station_of.reindex(multi_df.from_stop_id).dropna()) | set(station_of.reindex(multi_df.to_stop_id).dropna())
    return {station: "multi-level" if station in multi_stations else "surface" for station in set(station_of.dropna())}


def report_all():
    """Every station with Google data: in-station split, feed vs Google vs straight line, station type, hard misses."""
    sides_df = pd.read_csv(newest(f"{NAME}_2*_sides_all.csv"), dtype={"platform_id": str, "entrance_id": str})
    misses_df = pd.read_csv(newest(OWN_DATE_MISSES_PATTERN))
    misses_df = misses_df[misses_df.model == REPORTED_MODEL]
    missed = set(zip(misses_df.set_name, misses_df.draw_no))
    rows = []
    for release in sorted(sides_df.release.astype(str).unique()):
        release_df = sides_df[sides_df.release.astype(str) == release]
        stops_df, times_df = feed_tables(release, release_df.station_id.unique())
        times_df = times_df[~times_df.is_no_elevator].set_index(["platform_id", "entrance_id"])
        types = station_types(release)
        entrances_all = stops_df[stops_df.location_type == ENTRANCE_TYPE]
        for side in release_df.itertuples():
            entrances_df = entrances_all[entrances_all.station_id == side.station_id]
            g_lats, g_lons = parse_coords(side.google_lats), parse_coords(side.google_lons)
            is_board = side.side == "board"
            g_dist = entrance_distances(g_lats, g_lons, entrances_df, side.platform_lat, side.platform_lon)
            google_entrance = g_dist.index[0]
            entrance = entrances_df.set_index("stop_id").loc[google_entrance]
            gx, gy = local_xy(g_lats, g_lons, entrance.stop_lat, entrance.stop_lon)
            cut = int(np.argmin(np.hypot(gx, gy)))
            steps_m = np.hypot(np.diff(gx), np.diff(gy))
            street_m, inside_m = (steps_m[:cut].sum(), steps_m[cut:].sum()) if is_board else (steps_m[cut:].sum(), steps_m[:cut].sum())
            key = (side.platform_id, google_entrance)
            feed_s = times_df.loc[key, "in_s" if is_board else "out_s"] if key in times_df.index else np.nan
            rows.append({"station": side.stop_name, "station_id": side.station_id, "release": release,
                         "type": types.get(side.station_id, "surface"), "set_name": side.set_name, "draw_no": side.draw_no,
                         "side": side.side, "platform_id": side.platform_id, "diff_s": side.diff_s, "is_match": side.is_match,
                         "is_hard_miss": (side.set_name, side.draw_no) in missed, "google_entrance": google_entrance,
                         "google_entrance_m": g_dist.iloc[0], "google_inside_s": side.google_walk_s - street_m / WALK_SPEED_MS,
                         "inside_at_walk_s": inside_m / WALK_SPEED_MS, "feed_s": feed_s})
    table_df = pd.DataFrame(rows)
    table_df["google_minus_feed_s"] = table_df.google_inside_s - table_df.feed_s
    table_df["is_closer_to_line"] = ((table_df.google_inside_s - table_df.inside_at_walk_s).abs()
                                     < (table_df.google_inside_s - table_df.feed_s).abs())
    table_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_table_all.csv", index=False)
    usable_df = table_df[(table_df.google_entrance_m <= ENTRANCE_NEAR_M) & table_df.feed_s.notna()]
    n_miss_pairs = table_df[table_df.is_hard_miss][["set_name", "draw_no"]].drop_duplicates().shape[0]
    lines = [f"Station fidelity, all stations, run {run_date()} (rules in the docstring, set before results)",
             f"sides {len(table_df)} at {table_df.station_id.nunique()} stations; usable (Google within {ENTRANCE_NEAR_M} m of a "
             f"feed entrance, feed time found) {len(usable_df)}; hard misses (reported model, own date) with a side: "
             f"{n_miss_pairs} of {len(missed)}"]
    gap = usable_df.google_minus_feed_s
    lines.append(f"Google - feed in-station, usable sides: median {gap.median():+.0f} s, quartiles {gap.quantile(0.25):+.0f} / "
                 f"{gap.quantile(0.75):+.0f}, |gap| median {gap.abs().median():.0f} s, |gap| > {MATCH_TOLERANCE_S} s on "
                 f"{(gap.abs() > MATCH_TOLERANCE_S).mean():.3f}")
    for station_type, part in usable_df.groupby("type"):
        share_line = part.is_closer_to_line.mean()
        wanted = share_line if station_type == "surface" else 1 - share_line
        lines.append(f"  {station_type}: sides {len(part)} at {part.station_id.nunique()} stations; Google - feed median "
                     f"{part.google_minus_feed_s.median():+.0f} s, |gap| median {part.google_minus_feed_s.abs().median():.0f} s; "
                     f"closer to the line {share_line:.3f}; pattern share {wanted:.3f} (bar {PATTERN_SHARE:.3f}) -> "
                     f"{'holds' if wanted >= PATTERN_SHARE else 'does not hold'}")
    station_df = usable_df.groupby(["station", "type"]).agg(
        n=("diff_s", "size"), match=("is_match", "mean"), check_diff_s=("diff_s", "median"),
        google_s=("google_inside_s", "median"), feed_s=("feed_s", "median"), line_s=("inside_at_walk_s", "median"),
        gap_s=("google_minus_feed_s", "median"), abs_gap_s=("google_minus_feed_s", lambda values: values.abs().median()),
        closer_line=("is_closer_to_line", "mean"), hard_misses=("is_hard_miss", "sum")).reset_index()
    station_df["is_disagreeing"] = (station_df.n >= MIN_STATION_N) & (station_df.abs_gap_s > MATCH_TOLERANCE_S)
    station_df = station_df.sort_values("abs_gap_s", ascending=False)
    station_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_stations_all.csv", index=False)
    judged_df = station_df[station_df.n >= MIN_STATION_N]
    disagreeing_df = judged_df[judged_df.is_disagreeing]
    lines.append(f"stations judged (n >= {MIN_STATION_N}): {len(judged_df)}; disagreeing: {len(disagreeing_df)} "
                 f"({int(disagreeing_df.n.sum())} sides, {int(disagreeing_df.hard_misses.sum())} hard-miss sides)")
    lines.append(f"station medians of |Google - feed| (judged): quartiles {judged_df.abs_gap_s.quantile(0.25):.0f} / "
                 f"{judged_df.abs_gap_s.median():.0f} / {judged_df.abs_gap_s.quantile(0.75):.0f} s")
    lines.append("\njudged stations, by |Google - feed| (times in s, medians):")
    lines.append(judged_df.round(2).to_string(index=False))
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_summary_all.txt").write_text(summary + "\n", encoding="utf-8", newline="\n")


def pathway_times(zip_path, station_ids):
    """One-way shortest pathway times entrance -> platform (in_s) and back (out_s), with straight metres, for the stations."""
    with zipfile.ZipFile(zip_path) as gtfs_zip:
        stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype=str, encoding=GTFS_ENCODING)
        names = gtfs_zip.namelist()
        pathways_df = (pd.read_csv(gtfs_zip.open("pathways.txt"), dtype=str, encoding=GTFS_ENCODING) if "pathways.txt" in names
                       else pd.DataFrame(columns=["from_stop_id", "to_stop_id", "is_bidirectional", "traversal_time"]))
    stops_df["stop_lat"] = stops_df.stop_lat.astype(float)
    stops_df["stop_lon"] = stops_df.stop_lon.astype(float)
    forward, backward = {}, {}
    for row in pathways_df.itertuples():
        pairs = [(row.from_stop_id, row.to_stop_id)] + ([(row.to_stop_id, row.from_stop_id)] if row.is_bidirectional == "1" else [])
        for start, end in pairs:
            forward.setdefault(start, []).append((end, float(row.traversal_time)))
            backward.setdefault(end, []).append((start, float(row.traversal_time)))
    located = stops_df.set_index("stop_id")
    rows = []
    for station_id in station_ids:
        kids = stops_df[stops_df.parent_station == station_id]
        entrances = kids[kids.location_type == ENTRANCE_TYPE]
        platforms = kids[kids.location_type.fillna("0").isin(["0", ""])]
        for platform in platforms.itertuples():
            out_s, in_s = shortest_from(forward, platform.stop_id), shortest_from(backward, platform.stop_id)
            for entrance in entrances.itertuples():
                x, y = local_xy(entrance.stop_lat, entrance.stop_lon, platform.stop_lat, platform.stop_lon)
                rows.append({"station_id": station_id, "platform_id": platform.stop_id, "entrance_id": entrance.stop_id,
                             "in_s": in_s.get(entrance.stop_id, np.nan), "out_s": out_s.get(entrance.stop_id, np.nan),
                             "straight_m": float(np.hypot(x, y))})
    out_df = pd.DataFrame(rows, columns=["station_id", "platform_id", "entrance_id", "in_s", "out_s", "straight_m"])
    return out_df, {station_id: int(located.index.isin(set(pathways_df.from_stop_id) | set(pathways_df.to_stop_id))
                                    [(stops_df.set_index("stop_id").parent_station == station_id).to_numpy()].sum())
                    for station_id in station_ids}


def why():
    """Three free tests of why Google drops or replaces pathways at the disagreeing stations (rules in the docstring)."""
    check_df = pd.read_csv(newest(f"{PATHWAY_CHECK_NAME}_2*_table.csv"), dtype={"platform_id": str, "entrance_id": str})
    check_df = check_df[check_df.status == "ok"]
    table_df = pd.read_csv(newest(f"{NAME}_2*_table_all.csv"), dtype={"platform_id": str})
    stations_df = pd.read_csv(newest(f"{NAME}_2*_stations_all.csv"))
    disagreeing = set(stations_df.station[stations_df.is_disagreeing])
    judged = set(stations_df.station[stations_df.n >= MIN_STATION_N])
    fit_df = check_df.groupby("stop_name").agg(with_s=("diff_s", lambda v: v.abs().median()),
                                               without_s=("diff_no_path_s", lambda v: v.abs().median()))
    no_pathway = {name for name in disagreeing if fit_df.without_s[name] < fit_df.with_s[name]}
    group_of = {name: ("no-pathway" if name in no_pathway else "other disagreeing" if name in disagreeing else "agreeing")
                for name in judged}
    ids = check_df.drop_duplicates("stop_name").set_index("stop_name").station_id
    lines = [f"Why Google drops or replaces pathways, run {run_date()} (rules in the docstring, set before results)",
             f"no-pathway stations: {sorted(no_pathway)}; other disagreeing: {sorted(disagreeing - no_pathway)}; "
             f"agreeing (judged): {len(judged - disagreeing)}"]
    # (1) implied speed
    now_df, _ = pathway_times(CLEANED_TRAIN_PATHS["20261009"], [ids[name] for name in judged])
    now_df["speed_ms"] = now_df.straight_m / now_df[["in_s", "out_s"]].min(axis=1)
    speed = now_df.groupby("station_id").speed_ms.median()
    speed_df = pd.DataFrame({"station": sorted(judged)})
    speed_df["group"] = speed_df.station.map(group_of)
    speed_df["speed_ms"] = speed_df.station.map(ids).map(speed)
    slow_bar = np.nanpercentile(speed_df.speed_ms[speed_df.group == "agreeing"], SLOW_PERCENTILE)
    lines.append(f"\n(1) implied speed (straight metres / one-way feed time), agreeing stations: median "
                 f"{speed_df.speed_ms[speed_df.group == 'agreeing'].median():.2f} m/s, {SLOW_PERCENTILE}th percentile {slow_bar:.2f}")
    for row in speed_df[speed_df.group != "agreeing"].sort_values("speed_ms").itertuples():
        lines.append(f"  {row.station:18s} {row.group:18s} {row.speed_ms:.2f} m/s{'  (below)' if row.speed_ms < slow_bar else ''}")
    is_supported = bool((speed_df.speed_ms[speed_df.group == "no-pathway"] < slow_bar).all())
    lines.append(f"  -> every no-pathway station below the {SLOW_PERCENTILE}th percentile: {'yes (supports)' if is_supported else 'no'}")
    # (2) older feed
    old_df, old_counts = pathway_times(OLD_TRAIN_PATH, [ids[name] for name in disagreeing])
    lines.append("\n(2) 2026-08-28 feed vs current, disagreeing stations (stops with pathways old / Google vs old / Google vs now):")
    usable_df = table_df[(table_df.google_entrance_m <= ENTRANCE_NEAR_M) & table_df.feed_s.notna()]
    old_lookup = old_df.set_index(["platform_id", "entrance_id"])
    for name in sorted(disagreeing):
        part = usable_df[usable_df.station == name]
        keys = list(zip(part.platform_id, part.google_entrance))
        old_s = np.array([old_lookup.loc[key, "in_s" if side == "board" else "out_s"] if key in old_lookup.index else np.nan
                          for key, side in zip(keys, part.side)])
        gap_old = np.nanmedian(np.abs(part.google_inside_s.to_numpy() - old_s)) if np.isfinite(old_s).any() else np.nan
        is_changed = np.isfinite(old_s).any() and not np.allclose(old_s[np.isfinite(old_s)], part.feed_s.to_numpy()[np.isfinite(old_s)])
        lines.append(f"  {name:18s} {group_of[name]:18s} stops with pathways in old feed {old_counts[ids[name]]:3d}; "
                     f"|Google - old| {gap_old:.0f} s vs |Google - now| {part.google_minus_feed_s.abs().median():.0f} s; "
                     f"times changed since Aug: {'yes' if is_changed else 'no'}")
    # (3) time of day
    clock = check_df.set_index(["set_name", "draw_no", "side"]).clock_min
    usable_df = usable_df.copy()
    usable_df["clock_min"] = [clock.get(key, np.nan) for key in zip(usable_df.set_name, usable_df.draw_no, usable_df.side)]
    usable_df["is_peak"] = np.any([(usable_df.clock_min >= low) & (usable_df.clock_min < high) for low, high in PEAK_WINDOWS_MIN], axis=0)
    usable_df["group"] = usable_df.station.map(group_of).fillna("not judged")
    keys = ["station", "release", "platform_id", "google_entrance", "side"]
    spread_df = usable_df.groupby(keys).agg(group=("group", "first"), n=("google_inside_s", "size"),
                                            sd_s=("google_inside_s", "std"), feed_sd_s=("feed_s", "std")).reset_index()
    spread_df = spread_df[spread_df.n >= MIN_GROUP_N]
    lines.append(f"\n(3) Google's in-station time within (station, platform, entrance, side) groups with >= {MIN_GROUP_N} sides:")
    for group_name, part in spread_df.groupby("group"):
        lines.append(f"  {group_name:18s} groups {len(part):3d}; median sd {part.sd_s.median():.0f} s (feed sd {part.feed_sd_s.median():.0f})")
    peak_rows = []
    for group_name, part in usable_df[usable_df.group != "not judged"].groupby("group"):
        residual = part.google_inside_s - part.groupby(keys).google_inside_s.transform("median")
        peak_rows.append((group_name, residual[part.is_peak].median(), residual[~part.is_peak].median(),
                          int(part.is_peak.sum()), int((~part.is_peak).sum())))
    for group_name, peak, off, n_peak, n_off in peak_rows:
        lines.append(f"  {group_name:18s} peak - off-peak (residual to group median): {peak - off:+.0f} s (n {n_peak} / {n_off})")
    disagreeing_sd = spread_df.sd_s[spread_df.group != "agreeing"].median()
    peak_gap = max(abs(peak - off) for group_name, peak, off, _, _ in peak_rows if group_name != "agreeing")
    lines.append(f"  -> time-varying at disagreeing stations (sd {disagreeing_sd:.0f} s, peak gap {peak_gap:.0f} s, bar "
                 f"{VARYING_SD_S} s): {'yes' if disagreeing_sd > VARYING_SD_S or peak_gap > VARYING_SD_S else 'no'}")
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_summary_why.txt").write_text(summary + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "extract":
        extract()
    elif command == "osm":
        osm()
    elif command == "route":
        route(sys.argv[2])
    elif command == "report":
        report()
    elif command == "all":
        extract(is_all=True)
        report_all()
    elif command == "why":
        why()
