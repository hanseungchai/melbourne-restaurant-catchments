"""Google transit fetch stage (TRN-8): Google's transit answer for the transit pairs, to validate r5py.

1. Fetch (fetch_transit_google): PAID, Routes Essentials, one request per pair, through the API ledger.
   Transit is schedule-based: the request carries no routingPreference (traffic-aware routing would
   bill Routes Pro), and _check_request refuses any body that does. Alternatives are requested (TRN-8
   hedge). Each pair's departure is its drawn weekday and minute on a date of its release
   (assign_departures); the release is stored as text with each row. Google's answer is kept whole in
   the .raw.jsonl next to the output file, so scope rules (TRN-11) are read later without paying again.
   A stopped run resumes: pairs already answered with HTTP 200 are skipped.
   After the run, the route table (build_route_table, free) is rebuilt from all raw answers: one row per
   route with leave, arrival and arrival from the requested departure, and its scope (TRN-11).
2. Summary (summarise_routes): free; one dict per route Google returned: duration, distance, walk-only
   or not, vehicle types and lines. No scope decision yet: the smoke test shows what Google sends.
3. Smoke test (smoke_test_transit_fetch): PAID, a handful of calls gating the fetch: ordinary and short
   exploration pairs and r5py over-window pairs, written apart from the fetch file.
"""
import csv
import json
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import api_ledger
import config
from functions.google_places import read_google_api_key
from functions.google_routes import HTTP_OK, post_compute_routes
from functions.pt_network import read_feed_routes_df
from functions.subject_paths import subject_layers_file

LOCAL_TZ = ZoneInfo(config.LOCAL_TIMEZONE)
ROUTES_SKU = "routes_essentials"
ROUTES_ENDPOINT = "routes/computeRoutes"
TRANSIT_TRAVEL_MODE = "TRANSIT"
ALLOWED_TRAVEL_MODES = {"TRANSIT", "WALK"}   # modes this module may send; both bill Essentials (TRN-8)
FORBIDDEN_BODY_KEYS = {"routingPreference"}  # traffic-aware routing bills Routes Pro; transit takes none
TRANSIT_FIELD_MASK = ",".join([
    "routes.duration",
    "routes.distanceMeters",
    "routes.routeLabels",                  # DEFAULT_ROUTE vs alternates
    "routes.polyline.encodedPolyline",
    "routes.legs.startLocation",           # where Google snapped the origin
    "routes.legs.endLocation",             # ... and the destination
    "routes.legs.steps.travelMode",        # WALK or TRANSIT
    "routes.legs.steps.distanceMeters",
    "routes.legs.steps.staticDuration",
    "routes.legs.steps.transitDetails",    # line (agency, names, vehicle), stops and their times, headsign
    "routes.warnings",
])
DEFAULT_ROUTE_LABEL = "DEFAULT_ROUTE"
STEP_MODE_TRANSIT = "TRANSIT"
STEP_MODE_WALK = "WALK"
LIST_SEPARATOR = "|"                         # joins vehicle types and lines in one CSV cell
UTC_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
MIN_PER_HOUR = 60
DATE_STREAM = 3                              # under TRANSIT_DEPARTURE_SEED, after transit_samples' cell (1), minute (2)
DRAW_NO_COL = "draw_no"
HTTP_STATUS_COL = "http_status"
RELEASE_COL = "window_release"               # PTV export date, kept as text ("20261009")
SMOKE_RUN_ID = "transit_smoke"
FETCH_RUN_ID = "transit_fetch"
RAW_SUFFIX = ".raw.jsonl"                    # Google's whole answers, next to each fetch file
ROUTES_SUFFIX = ".routes.csv"                # the route table built from them (build_route_table)
# GTFS route_type of each cleaned feed -> the Google vehicle types that can stand for it (TRN-11)
GTFS_ROUTE_TYPE_VEHICLES = {
    "400": ("HEAVY_RAIL", "COMMUTER_TRAIN", "METRO_RAIL", "SUBWAY", "RAIL"),   # metro train (urban railway)
    "0": ("TRAM", "LIGHT_RAIL"),
    "3": ("BUS",),
}
SCOPE_IN, SCOPE_NAME_MISMATCH, SCOPE_OUT = "in_scope", "name_mismatch", "out_of_scope"
FETCH_PROGRESS_EVERY = 100
ISO_DATE_LEN = 10                            # "YYYY-MM-DD" prefix of an ISO timestamp
DATE_LABEL_FORMAT = "%a %Y-%m-%d"


# --- Request ------------------------------------------------------------------------------------------

def transit_request_body(origin_lat, origin_lon, dest_lat, dest_lon, departure_time_iso,
                         travel_mode=TRANSIT_TRAVEL_MODE):
    """computeRoutes body for one pair: alternatives on, no routingPreference."""
    return {
        "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lon}}},
        "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lon}}},
        "travelMode": travel_mode,
        "departureTime": departure_time_iso,
        "computeAlternativeRoutes": True,
    }


def _check_request(body, sku):
    """Refuse a request that could bill above Essentials or isn't a transit / walk request."""
    if sku != ROUTES_SKU:
        raise ValueError(f"SKU {sku!r}: this module sends {ROUTES_SKU!r} only")
    if body.get("travelMode") not in ALLOWED_TRAVEL_MODES:
        raise ValueError(f"travelMode {body.get('travelMode')!r} not in {sorted(ALLOWED_TRAVEL_MODES)}")
    forbidden = FORBIDDEN_BODY_KEYS & set(body)
    if forbidden:
        raise ValueError(f"forbidden request keys {sorted(forbidden)} (traffic-aware routing bills Routes Pro)")


# --- Departures ----------------------------------------------------------------------------------------

def assign_departures(pairs_df, release, now_utc, first_fetch_date=None):
    """Departure per pair (TRN-7): a seeded uniform pick among the release's fetch dates on the pair's
    weekday (dep_day, 1 = Mon), at its drawn minute (dep_min_of_day); first_fetch_date, if given, drops
    the release's earlier dates. Raises if any departure is not in the future: Google refuses or answers
    differently for past times."""
    first_date, last_date = config.TRANSIT_RELEASE_FETCH_DATES[release]
    if first_fetch_date is not None:
        first_date = max(first_date, first_fetch_date)
    fetch_dates = [first_date + timedelta(days=k) for k in range((last_date - first_date).days + 1)]
    departures_utc, departures_local = [], []
    for row in pairs_df.itertuples():
        weekday_dates = [d for d in fetch_dates if d.isoweekday() == int(row.dep_day)]
        if not weekday_dates:
            raise ValueError(f"draw_no {row.draw_no}: release {release} has no fetch date on weekday {row.dep_day}")
        pick = np.random.default_rng([config.TRANSIT_DEPARTURE_SEED, DATE_STREAM, int(row.draw_no)]).integers(
            len(weekday_dates))
        minute = int(row.dep_min_of_day)
        local = datetime.combine(weekday_dates[pick], dtime(minute // MIN_PER_HOUR, minute % MIN_PER_HOUR),
                                 tzinfo=LOCAL_TZ)
        if local <= now_utc:
            raise ValueError(f"draw_no {row.draw_no}: departure {local.isoformat()} is not in the future")
        departures_utc.append(local.astimezone(timezone.utc).strftime(UTC_ISO_FORMAT))
        departures_local.append(local.isoformat())
    return pairs_df.assign(departure_utc=departures_utc, departure_local=departures_local)


# --- Summary (free) ------------------------------------------------------------------------------------

def _seconds(duration):
    return int(duration.rstrip("s")) if duration else None


def summarise_routes(response_json):
    """One dict per route in a computeRoutes answer, in Google's order."""
    summaries = []
    for route in (response_json or {}).get("routes", []):
        steps = [step for leg in route.get("legs", []) for step in leg.get("steps", [])]
        transit_steps = [step for step in steps if step.get("travelMode") == STEP_MODE_TRANSIT]
        lines = [step.get("transitDetails", {}).get("transitLine", {}) for step in transit_steps]
        first_stop_times = (transit_steps[0].get("transitDetails", {}).get("stopDetails", {})
                            if transit_steps else {})
        summaries.append(dict(
            is_default=DEFAULT_ROUTE_LABEL in route.get("routeLabels", []),
            duration_s=_seconds(route.get("duration")),
            distance_m=route.get("distanceMeters"),
            is_walk_only=not transit_steps,
            n_transit_steps=len(transit_steps),
            walk_m=sum(step.get("distanceMeters", 0) for step in steps if step.get("travelMode") == STEP_MODE_WALK),
            vehicle_types=LIST_SEPARATOR.join(line.get("vehicle", {}).get("type", "") for line in lines),
            lines=LIST_SEPARATOR.join(
                f"{(line.get('agencies') or [{}])[0].get('name', '')}:{line.get('nameShort') or line.get('name', '')}"
                for line in lines),
            first_board_time=first_stop_times.get("departureTime"),
        ))
    return summaries


# --- Route table (free) --------------------------------------------------------------------------------

def _utc(timestamp):
    """Google's RFC 3339 time ("...Z") as an aware UTC datetime."""
    return datetime.fromisoformat(timestamp).astimezone(timezone.utc)


def _step_seconds(steps):
    return sum(_seconds(step.get("staticDuration")) or 0 for step in steps)


def route_times(route, requested_utc):
    """Leave and arrival (UTC) of one Google route. A transit route leaves when its walk reaches the first
    boarding just in time and arrives after the walk from the last alighting; a walk-only route leaves at
    the requested departure. Google's duration runs from leave to arrival (smoke test, TRN-8)."""
    # evidence: diagnostics/transit_google_duration.py (duration = arrival - leave, initial wait excluded)
    steps = [step for leg in route.get("legs", []) for step in leg.get("steps", [])]
    transit_ix = [i for i, step in enumerate(steps) if step.get("travelMode") == STEP_MODE_TRANSIT]
    if not transit_ix:
        leave = requested_utc
        return leave, leave + timedelta(seconds=_seconds(route.get("duration")) or 0)
    first, last = transit_ix[0], transit_ix[-1]
    first_board = _utc(steps[first]["transitDetails"]["stopDetails"]["departureTime"])
    last_alight = _utc(steps[last]["transitDetails"]["stopDetails"]["arrivalTime"])
    return (first_board - timedelta(seconds=_step_seconds(steps[:first])),
            last_alight + timedelta(seconds=_step_seconds(steps[last + 1:])))


def in_scope_lines(gtfs_paths):
    """The feed's in-scope lines (TRN-11) as {(Google vehicle type, line short name): {long names}}, read
    from the cleaned feeds (route type 701 already dropped)."""
    lines = {}
    for gtfs_path in gtfs_paths:
        routes_df = read_feed_routes_df(gtfs_path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
        for row in routes_df.itertuples():
            for vehicle_type in GTFS_ROUTE_TYPE_VEHICLES.get(row.route_type, ()):
                lines.setdefault((vehicle_type, row.route_short_name), set()).add(row.route_long_name)
    return lines


def line_scope(transit_line, scope_lines):
    """Scope of one Google transitLine (TRN-11): in_scope if its vehicle type and short name are a feed
    line and its long name is that line's (or either side gives none); name_mismatch if only the short name
    matches (review: a regional service may share a metro number); out_of_scope otherwise."""
    key = (transit_line.get("vehicle", {}).get("type", ""), transit_line.get("nameShort", ""))
    if key not in scope_lines:
        return SCOPE_OUT
    long_name = transit_line.get("name")
    feed_long_names = scope_lines[key] - {""}           # the metro train feed leaves its lines' long names empty
    return SCOPE_IN if not long_name or not feed_long_names or long_name in feed_long_names else SCOPE_NAME_MISMATCH


def route_rows(record, scope_lines):
    """One row per route of one raw answer: Google's order and default label, times from the requested
    departure (so any T7 (f) fit target can be computed), and the route's scope."""
    requested_utc = _utc(record["request"]["departureTime"])
    rows = []
    for route_ix, (route, summary) in enumerate(zip(record["resp"].get("routes", []),
                                                    summarise_routes(record["resp"]))):
        leave_utc, arrival_utc = route_times(route, requested_utc)
        transit_lines = [step["transitDetails"].get("transitLine", {})
                         for leg in route.get("legs", []) for step in leg.get("steps", [])
                         if step.get("travelMode") == STEP_MODE_TRANSIT]
        scopes = [line_scope(line, scope_lines) for line in transit_lines]
        route_scope = (SCOPE_OUT if SCOPE_OUT in scopes else SCOPE_NAME_MISMATCH if SCOPE_NAME_MISMATCH in scopes
                       else SCOPE_IN)
        rows.append({DRAW_NO_COL: record[DRAW_NO_COL], RELEASE_COL: record[RELEASE_COL], "route_ix": route_ix,
                     **summary,
                     "requested_utc": requested_utc.strftime(UTC_ISO_FORMAT),
                     "leave_utc": leave_utc.strftime(UTC_ISO_FORMAT),
                     "arrival_utc": arrival_utc.strftime(UTC_ISO_FORMAT),
                     "leave_wait_s": int((leave_utc - requested_utc).total_seconds()),
                     "arrival_from_request_s": int((arrival_utc - requested_utc).total_seconds()),
                     "duration_gap_s": int((arrival_utc - leave_utc).total_seconds()) - (summary["duration_s"] or 0),
                     "line_scopes": LIST_SEPARATOR.join(scopes), "route_scope": route_scope})
    return rows


def build_route_table(fetch_path):
    """Free: one row per Google route for every answer in fetch_path's .raw.jsonl, written next to it
    (ROUTES_SUFFIX). Rebuilt in full on every call; the raw answers are the record."""
    fetch_path = Path(fetch_path)
    scope_lines = in_scope_lines([config.PT_GTFS_CLEANED_DIR / f"{name}.zip" for name in config.PT_GTFS_SOURCE_PATHS])
    with open(fetch_path.with_suffix(RAW_SUFFIX)) as raw_file:
        routes_df = pd.DataFrame([row for record in map(json.loads, raw_file) for row in route_rows(record, scope_lines)])
    routes_df.to_csv(fetch_path.with_suffix(ROUTES_SUFFIX), index=False)
    return routes_df


# --- Fetch (PAID) --------------------------------------------------------------------------------------

def fetch_transit_google(pairs_df, release, out_path, run_id, api_key=None, first_fetch_date=None):
    """WARNING: SPENDS API CALLS (Routes Essentials). Google transit answers for pairs_df under release.

    pairs_df needs draw_no, origin/dest lat/lon, dep_day and dep_min_of_day. Appends one row per pair to
    out_path, raw answers to its .raw.jsonl; skips pairs already answered with HTTP 200. first_fetch_date:
    as assign_departures.
    """
    out_path = Path(out_path)
    done = set()
    if out_path.exists():
        fetched_df = pd.read_csv(out_path, usecols=[DRAW_NO_COL, HTTP_STATUS_COL])
        done = set(fetched_df.loc[fetched_df[HTTP_STATUS_COL] == HTTP_OK, DRAW_NO_COL])
    todo_df = assign_departures(pairs_df[~pairs_df[DRAW_NO_COL].isin(done)].sort_values(DRAW_NO_COL),
                                release, datetime.now(timezone.utc), first_fetch_date)
    print(f"{len(done)} done, {len(todo_df)} to fetch (release {release})")
    if todo_df.empty:
        return
    for row in todo_df.itertuples():                       # every body checked before the first send
        _check_request(transit_request_body(row.origin_lat, row.origin_lon, row.dest_lat, row.dest_lon,
                                            row.departure_utc), ROUTES_SKU)
    api_ledger.check(ROUTES_SKU, len(todo_df))             # batch guard before any send
    if api_key is None:
        api_key = read_google_api_key()                    # at call time, never at import (CLAUDE.md S3)

    should_write_header = not out_path.exists()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "a", newline="") as out_file, open(out_path.with_suffix(RAW_SUFFIX), "a") as raw_file:
        writer = None
        for i, row in enumerate(todo_df.itertuples()):
            draw_no = int(row.draw_no)
            body = transit_request_body(row.origin_lat, row.origin_lon, row.dest_lat, row.dest_lon, row.departure_utc)
            _check_request(body, ROUTES_SKU)
            collected_at = datetime.now(timezone.utc)
            http_status, response_json, req_id = post_compute_routes(
                body, TRANSIT_FIELD_MASK, api_key,
                before_send=lambda: api_ledger.record_send(ROUTES_SKU, endpoint=ROUTES_ENDPOINT, run_id=run_id,
                                                           meta={DRAW_NO_COL: draw_no}))
            routes = summarise_routes(response_json)
            api_ledger.record_result(req_id, status=http_status, n_results=len(routes))
            if response_json is not None:
                raw_file.write(json.dumps({DRAW_NO_COL: draw_no, RELEASE_COL: release, "request": body,
                                           "resp": response_json}) + "\n")
                raw_file.flush()
            primary = next((route for route in routes if route["is_default"]), routes[0] if routes else {})
            record = {DRAW_NO_COL: draw_no, RELEASE_COL: release, HTTP_STATUS_COL: http_status,
                      "departure_utc": row.departure_utc, "departure_local": row.departure_local,
                      "n_routes": len(routes),
                      "google_duration_s": primary.get("duration_s"), "google_distance_m": primary.get("distance_m"),
                      "is_walk_only": primary.get("is_walk_only"), "n_transit_steps": primary.get("n_transit_steps"),
                      "walk_m": primary.get("walk_m"), "vehicle_types": primary.get("vehicle_types"),
                      "lines": primary.get("lines"), "first_board_time": primary.get("first_board_time"),
                      "collected_at_utc": collected_at.strftime(UTC_ISO_FORMAT), "run_id": run_id}
            if writer is None:
                writer = csv.DictWriter(out_file, fieldnames=list(record))
                if should_write_header:
                    writer.writeheader()
            writer.writerow(record)
            out_file.flush()
            if i % FETCH_PROGRESS_EVERY == 0:
                print(f"  {i}/{len(todo_df)}  last status {http_status}")
            time.sleep(config.ROUTES_REQUEST_DELAY_S)
    routes_df = build_route_table(out_path)
    print(f"route table: {len(routes_df)} routes, scope {routes_df.route_scope.value_counts().to_dict()}")


def fetch_transit_pairs(subject_lat, subject_lon):
    """WARNING: SPENDS API CALLS (Routes Essentials, one per pair: 2,500 in-window + 125 smoke-test).
    Fetches the whole draw (not the checkpoint's reserve) under the draw's release into
    config.TRANSIT_GOOGLE_PATH. The smoke test's answers stay in their own file; those pairs are
    fetched again here so every pair has one answer from one run."""
    pairs_df = pd.read_csv(subject_layers_file(config.TRANSIT_PAIRS_PATH, subject_lat, subject_lon),
                           dtype={RELEASE_COL: str})
    out_path = subject_layers_file(config.TRANSIT_GOOGLE_PATH, subject_lat, subject_lon)
    fetch_transit_google(pairs_df, config.TRANSIT_DRAW_RELEASE, out_path, FETCH_RUN_ID)


# --- Smoke test (PAID)---------------------------------------------------------------------------------

def smoke_test_pairs(subject_lat, subject_lon):
    """The smoke-test pairs, lowest draw_no first in each group: ordinary and short exploration pairs
    (training half only) and r5py over-window pairs (T5). Adds a smoke_group column."""
    pairs_df = pd.read_csv(subject_layers_file(config.TRANSIT_PAIRS_PATH, subject_lat, subject_lon),
                           dtype={RELEASE_COL: str})
    split_df = pd.read_csv(subject_layers_file(config.TRANSIT_SPLIT_PATH, subject_lat, subject_lon),
                           usecols=[DRAW_NO_COL, "is_exploration"])
    pairs_df = pairs_df.merge(split_df, on=DRAW_NO_COL).sort_values(DRAW_NO_COL)
    exploration_df = pairs_df[pairs_df.is_exploration]
    short_min_m, short_max_m = config.TRANSIT_SMOKE_SHORT_M
    is_short = exploration_df.haversine_m.between(short_min_m, short_max_m, inclusive="left")
    groups = {"ordinary": exploration_df[exploration_df.haversine_m >= short_max_m].head(config.TRANSIT_SMOKE_N_ORDINARY),
              "short": exploration_df[is_short].head(config.TRANSIT_SMOKE_N_SHORT),
              "over_window": pairs_df[pairs_df.is_smoke_test].head(config.TRANSIT_SMOKE_N_OVER_WINDOW)}
    return pd.concat([group_df.assign(smoke_group=name) for name, group_df in groups.items()], ignore_index=True)


def smoke_test_transit_fetch(subject_lat, subject_lon):
    """WARNING: SPENDS API CALLS (Routes Essentials, a handful). Fetches the smoke-test pairs under the
    draw's release into config.TRANSIT_GOOGLE_SMOKE_PATH and prints each pair's routes."""
    pairs_df = smoke_test_pairs(subject_lat, subject_lon)
    out_path = subject_layers_file(config.TRANSIT_GOOGLE_SMOKE_PATH, subject_lat, subject_lon)
    fetch_transit_google(pairs_df, config.TRANSIT_DRAW_RELEASE, out_path, SMOKE_RUN_ID)
    with open(Path(out_path).with_suffix(RAW_SUFFIX)) as raw_file:
        answers = {record[DRAW_NO_COL]: record["resp"] for record in map(json.loads, raw_file)}
    for row in pairs_df.itertuples():
        print(f"\n{row.smoke_group} draw_no {row.draw_no}: {row.haversine_m:,.0f} m, r5py {row.r5py_fastest_min} min, "
              f"{row.dep_day_name} {int(row.dep_min_of_day) // MIN_PER_HOUR:02d}:{int(row.dep_min_of_day) % MIN_PER_HOUR:02d}")
        for route in summarise_routes(answers.get(row.draw_no)):
            print(f"    {route}")


# --- Later sets on the next release: reserve (TRN-10), test-half extension (TRN-15), fresh holdout --------

class FetchSet(NamedTuple):
    """A pair set fetched on its own after the draw, into its own files."""
    pairs_path: Path               # the set's pairs (transit_samples.STREAM_SETS)
    google_path: Path              # Google's answers for it
    run_id: str                    # the API ledger's run ID; never change one already used
    first_fetch_date: date | None  # first departure date; None = the release's first date


FETCH_SETS = {
    "reserve": FetchSet(config.TRANSIT_RESERVE_PAIRS_PATH, config.TRANSIT_GOOGLE_RESERVE_PATH,
                        "transit_fetch_reserve", None),
    "test_ext": FetchSet(config.TRANSIT_TEST_EXT_PAIRS_PATH, config.TRANSIT_GOOGLE_TEST_EXT_PATH,
                         "transit_fetch_test_ext", config.TRANSIT_TEST_EXT_FIRST_FETCH_DATE),
    "holdout": FetchSet(config.TRANSIT_HOLDOUT_PAIRS_PATH, config.TRANSIT_GOOGLE_HOLDOUT_PATH,
                        "transit_fetch_holdout", config.TRANSIT_HOLDOUT_FIRST_FETCH_DATE),
}


def read_set_pairs(set_name, subject_lat, subject_lon):
    """A later set's pairs, window_release read as text."""
    return pd.read_csv(subject_layers_file(FETCH_SETS[set_name].pairs_path, subject_lat, subject_lon),
                       dtype={RELEASE_COL: str})


def check_set_fetch(set_name, subject_lat, subject_lon):
    """Free dry run of fetch_set: departures on config.TRANSIT_SECOND_RELEASE from the set's first fetch
    date, every body through _check_request, the ledger guard for the whole set. Nothing is sent."""
    return _check_fetch(read_set_pairs(set_name, subject_lat, subject_lon), config.TRANSIT_SECOND_RELEASE,
                        FETCH_SETS[set_name].first_fetch_date)


def _check_fetch(pairs_df, release, first_fetch_date=None):
    """Free dry run: departures on release, every body through _check_request, the ledger guard for the
    whole batch. Nothing is sent."""
    todo_df = assign_departures(pairs_df, release, datetime.now(timezone.utc), first_fetch_date)
    for row in todo_df.itertuples():
        _check_request(transit_request_body(row.origin_lat, row.origin_lon, row.dest_lat, row.dest_lon,
                                            row.departure_utc), ROUTES_SKU)
    api_ledger.check(ROUTES_SKU, len(todo_df))
    dates = pd.to_datetime(todo_df.departure_local.str[:ISO_DATE_LEN])
    print(f"dry run passed: {len(todo_df):,} bodies checked, ledger allows them; departures "
          f"{todo_df.departure_local.min()} to {todo_df.departure_local.max()}")
    print(dates.dt.strftime(DATE_LABEL_FORMAT).value_counts().sort_index().to_string())
    return todo_df


def fetch_set(set_name, subject_lat, subject_lon):
    """WARNING: SPENDS API CALLS (Routes Essentials, one per pair of the set). A later set under
    config.TRANSIT_SECOND_RELEASE, departures from its first fetch date, into its google_path, through
    fetch_transit_google in chunks of config.TRANSIT_SET_FETCH_CHUNK; stops if a chunk's non-200 share
    exceeds config.TRANSIT_FETCH_MAX_FAIL_SHARE. Resumes like fetch_transit_google."""
    fetch_set_spec = FETCH_SETS[set_name]
    out_path = subject_layers_file(fetch_set_spec.google_path, subject_lat, subject_lon)
    _fetch_in_chunks(read_set_pairs(set_name, subject_lat, subject_lon), config.TRANSIT_SECOND_RELEASE, out_path,
                     fetch_set_spec.run_id, fetch_set_spec.first_fetch_date)


def _fetch_in_chunks(pairs_df, release, out_path, run_id, first_fetch_date=None):
    """WARNING: SPENDS API CALLS. fetch_transit_google in chunks of config.TRANSIT_SET_FETCH_CHUNK pairs
    (by draw_no); stops if a chunk's non-200 share exceeds config.TRANSIT_FETCH_MAX_FAIL_SHARE."""
    pairs_df = pairs_df.sort_values(DRAW_NO_COL, ignore_index=True)
    for start in range(0, len(pairs_df), config.TRANSIT_SET_FETCH_CHUNK):
        chunk_df = pairs_df.iloc[start:start + config.TRANSIT_SET_FETCH_CHUNK]
        fetch_transit_google(chunk_df, release, out_path, run_id, first_fetch_date=first_fetch_date)
        fetched_df = pd.read_csv(out_path, usecols=[DRAW_NO_COL, HTTP_STATUS_COL])
        chunk_status = fetched_df[fetched_df[DRAW_NO_COL].isin(chunk_df[DRAW_NO_COL])].drop_duplicates(
            DRAW_NO_COL, keep="last")[HTTP_STATUS_COL]
        fail_share = (chunk_status != HTTP_OK).mean()
        print(f"chunk {start // config.TRANSIT_SET_FETCH_CHUNK + 1}: {len(chunk_status)} answered, "
              f"statuses {chunk_status.value_counts().to_dict()}")
        if fail_share > config.TRANSIT_FETCH_MAX_FAIL_SHARE:
            raise RuntimeError(f"chunk non-200 share {fail_share:.1%} > {config.TRANSIT_FETCH_MAX_FAIL_SHARE:.0%}: stopped")


# --- Boundary top-up (TRN-14) ---------------------------------------------------------------------------

TOPUP_PILOT_RUN_ID = "transit_topup_pilot"
TOPUP_RUN_ID = "transit_topup"
SCORED_SCOPES = (SCOPE_IN, SCOPE_NAME_MISMATCH)  # TRN-11: default routes R5 is scored against
NO_ZONE = 0                                      # scored but in neither zone, or not scorable
SECONDS_PER_MIN = 60
RANGE_COL_FORMAT = "in_range_{}"                 # as transit_samples writes the top-up pairs
SENT_FOR_COL, CHUNK_COL = "sent_for_range", "chunk"
PILOT_CHUNK = 0
TRAIN_HALF = "train"
MISS_MINUTE_BINS = [-1, 6, 13, 16, 23, 30, np.inf]
MISS_MINUTE_LABELS = ["0-6", "7-13", "14-16", "17-23", "24-30", "31+"]


def google_zones(routes_df, draw_nos):
    """Zone per draw_no from Google's answer only (TRN-13 (1)): the default route's arrival from the
    requested departure in rounded minutes (SCR-10; np.round as diagnostics/transit_time_bands.py), in a
    zone only if the route is in scope. draw_nos without an answer get NO_ZONE and is_scored False."""
    default_df = (routes_df[routes_df.is_default].drop_duplicates(DRAW_NO_COL).set_index(DRAW_NO_COL)
                  .reindex(list(draw_nos)))
    google_min = np.round(default_df.arrival_from_request_s.to_numpy(float) / SECONDS_PER_MIN)
    is_scored = default_df.route_scope.isin(SCORED_SCOPES).to_numpy() & ~np.isnan(google_min)
    zone = np.full(len(default_df), NO_ZONE)
    for zone_no, (low_min, high_min) in config.TRANSIT_ZONES_MIN.items():
        zone[is_scored & (google_min >= low_min) & (google_min <= high_min)] = zone_no
    return pd.DataFrame({DRAW_NO_COL: default_df.index, "google_min": google_min, "is_scored": is_scored,
                         "zone": zone})


def _topup_files(subject_lat, subject_lon):
    pairs_df = pd.read_csv(subject_layers_file(config.TRANSIT_TOPUP_PAIRS_PATH, subject_lat, subject_lon),
                           dtype={RELEASE_COL: str})
    out_path = Path(subject_layers_file(config.TRANSIT_GOOGLE_TOPUP_PATH, subject_lat, subject_lon))
    selection_path = Path(subject_layers_file(config.TRANSIT_TOPUP_SELECTION_PATH, subject_lat, subject_lon))
    selection_df = (pd.read_csv(selection_path) if selection_path.exists()
                    else pd.DataFrame(columns=[DRAW_NO_COL, SENT_FOR_COL, CHUNK_COL]))
    return pairs_df, out_path, selection_path, selection_df


def _next_selection(pairs_df, selection_df, open_zones, n_per_range, chunk_no):
    """The next n_per_range unsent pairs of each open zone's range, in draw_no order (the draw's random
    order); a pair listed in both ranges is sent once, for the first range that reaches it."""
    sent = set(selection_df[DRAW_NO_COL])
    rows = []
    for zone_no in open_zones:
        range_df = pairs_df[pairs_df[RANGE_COL_FORMAT.format(zone_no)] & ~pairs_df[DRAW_NO_COL].isin(sent)]
        picked = range_df.sort_values(DRAW_NO_COL)[DRAW_NO_COL].head(n_per_range).tolist()
        if len(picked) < n_per_range:
            raise RuntimeError(f"range {zone_no} ran out of candidates: raise config.TRANSIT_TOPUP_N_PER_RANGE "
                               "and redraw (only the unsent tail changes)")
        sent.update(picked)
        rows += [{DRAW_NO_COL: draw_no, SENT_FOR_COL: zone_no, CHUNK_COL: chunk_no} for draw_no in picked]
    return pd.DataFrame(rows)


def _check_topup_bodies(pairs_df, draw_nos, n_calls):
    """Departures, body checks and the ledger guard for draw_nos; returns the departures. Nothing sent."""
    todo_df = assign_departures(pairs_df[pairs_df[DRAW_NO_COL].isin(draw_nos)], config.TRANSIT_TOPUP_RELEASE,
                                datetime.now(timezone.utc))
    for row in todo_df.itertuples():
        _check_request(transit_request_body(row.origin_lat, row.origin_lon, row.dest_lat, row.dest_lon,
                                            row.departure_utc), ROUTES_SKU)
    api_ledger.check(ROUTES_SKU, n_calls)
    return todo_df


def _send_topup(pairs_df, selection_df, out_path, run_id):
    """WARNING: SPENDS API CALLS. Fetch every selected pair not yet answered with HTTP 200, then stop if
    the non-200 share among the selection exceeds config.TRANSIT_FETCH_MAX_FAIL_SHARE."""
    fetch_transit_google(pairs_df[pairs_df[DRAW_NO_COL].isin(selection_df[DRAW_NO_COL])],
                         config.TRANSIT_TOPUP_RELEASE, out_path, run_id)
    fetched_df = pd.read_csv(out_path, usecols=[DRAW_NO_COL, HTTP_STATUS_COL])
    status = fetched_df[fetched_df[DRAW_NO_COL].isin(selection_df[DRAW_NO_COL])].drop_duplicates(
        DRAW_NO_COL, keep="last")[HTTP_STATUS_COL]
    fail_share = (status != HTTP_OK).mean()
    if fail_share > config.TRANSIT_FETCH_MAX_FAIL_SHARE:
        raise RuntimeError(f"non-200 share {fail_share:.1%} > {config.TRANSIT_FETCH_MAX_FAIL_SHARE:.0%}: stopped")


def _earlier_zone_counts(subject_lat, subject_lon):
    """Zone pairs already fetched that count toward the target when config.TRANSIT_TOPUP_COUNTS_EARLIER:
    the first fetch's training half and the whole second batch. The test half is not read."""
    if not config.TRANSIT_TOPUP_COUNTS_EARLIER:
        return {zone_no: 0 for zone_no in config.TRANSIT_ZONES_MIN}
    split_df = pd.read_csv(subject_layers_file(config.TRANSIT_SPLIT_PATH, subject_lat, subject_lon),
                           usecols=[DRAW_NO_COL, "half"])
    reserve_df = pd.read_csv(subject_layers_file(config.TRANSIT_RESERVE_PAIRS_PATH, subject_lat, subject_lon),
                             usecols=[DRAW_NO_COL])
    sources = [(config.TRANSIT_GOOGLE_PATH, split_df.loc[split_df.half == TRAIN_HALF, DRAW_NO_COL]),
               (config.TRANSIT_GOOGLE_RESERVE_PATH, reserve_df[DRAW_NO_COL])]
    zones = pd.concat([google_zones(pd.read_csv(Path(subject_layers_file(path, subject_lat, subject_lon))
                                                .with_suffix(ROUTES_SUFFIX)), draw_nos).zone
                       for path, draw_nos in sources])
    return {zone_no: int((zones == zone_no).sum()) for zone_no in config.TRANSIT_ZONES_MIN}


def _topup_zones(selection_df, out_path):
    """Zone of every sent pair (TRN-13 (1)), with the range it was sent for."""
    routes_path = out_path.with_suffix(ROUTES_SUFFIX)
    routes_df = pd.read_csv(routes_path) if routes_path.exists() else pd.DataFrame(
        columns=[DRAW_NO_COL, "is_default", "arrival_from_request_s", "route_scope"])
    return selection_df.merge(google_zones(routes_df, selection_df[DRAW_NO_COL]), on=DRAW_NO_COL)


def report_topup(subject_lat, subject_lon):
    """Free: yield per call by range, where misses landed, zone totals and projected calls to the target
    (TRN-14 (2)). Reads the fetch's route table only; no R5 result is read (TRN-14). Returns zone counts."""
    _, out_path, _, selection_df = _topup_files(subject_lat, subject_lon)
    zones_df = _topup_zones(selection_df, out_path)
    target = config.TRANSIT_TOPUP_TARGET_PER_ZONE
    earlier = _earlier_zone_counts(subject_lat, subject_lon)
    topup_counts = {zone_no: int((zones_df.zone == zone_no).sum()) for zone_no in config.TRANSIT_ZONES_MIN}
    zone_counts = {zone_no: earlier[zone_no] + topup_counts[zone_no] for zone_no in config.TRANSIT_ZONES_MIN}
    print(f"top-up: {len(zones_df):,} calls; zone pairs {topup_counts} from the top-up, {earlier} earlier, "
          f"{zone_counts} in all (target {target} each); not scorable {(~zones_df.is_scored).sum()}")
    yields = {}
    for zone_no, range_df in zones_df.groupby(SENT_FOR_COL):
        yields[zone_no] = {other: (range_df.zone == other).mean() for other in config.TRANSIT_ZONES_MIN}
        misses = pd.cut(range_df.loc[range_df.is_scored & (range_df.zone == NO_ZONE), "google_min"],
                        MISS_MINUTE_BINS, labels=MISS_MINUTE_LABELS).value_counts().sort_index()
        print(f"  range {zone_no} {config.TRANSIT_TOPUP_RANGES_M[zone_no]}: {len(range_df)} calls; per call "
              + ", ".join(f"zone {other} {share:.2f}" for other, share in yields[zone_no].items())
              + f"; misses by Google minute {misses[misses > 0].to_dict()}")
    for zone_no, count in zone_counts.items():
        n_missing = max(target - count, 0)
        own_yield = yields.get(zone_no, {}).get(zone_no, 0)
        print(f"  zone {zone_no}: {n_missing} to go; ~{n_missing / own_yield:,.0f} calls from its own range alone"
              if own_yield else f"  zone {zone_no}: {n_missing} to go; no yield measured yet")
    return zone_counts


def check_transit_topup_fetch(subject_lat, subject_lon):
    """Free dry run of the pilot (TRN-14 (2)): the pilot's pairs, their departures, every body through
    _check_request, the ledger guard for the pilot (and for config.TRANSIT_TOPUP_MAX_CALLS if set).
    Nothing is sent and nothing is written."""
    pairs_df, _, _, selection_df = _topup_files(subject_lat, subject_lon)
    pilot_df = (selection_df[selection_df[CHUNK_COL] == PILOT_CHUNK] if len(selection_df) else
                _next_selection(pairs_df, selection_df, config.TRANSIT_ZONES_MIN, config.TRANSIT_TOPUP_PILOT_PER_RANGE,
                                PILOT_CHUNK))
    todo_df = _check_topup_bodies(pairs_df, pilot_df[DRAW_NO_COL], len(pilot_df))
    if config.TRANSIT_TOPUP_MAX_CALLS is not None:
        api_ledger.check(ROUTES_SKU, config.TRANSIT_TOPUP_MAX_CALLS)
    todo_df = todo_df.merge(pilot_df, on=DRAW_NO_COL)
    print(f"dry run passed: {len(todo_df)} pilot bodies checked ({todo_df[SENT_FOR_COL].value_counts().to_dict()} "
          f"by range), ledger allows them; departures {todo_df.departure_local.min()} to {todo_df.departure_local.max()}")
    print(pd.to_datetime(todo_df.departure_local.str[:ISO_DATE_LEN]).dt.strftime(DATE_LABEL_FORMAT)
          .value_counts().sort_index().to_string())
    print(f"haversine m by range: {todo_df.groupby(SENT_FOR_COL).haversine_m.describe().round(0).to_dict('index')}")
    return todo_df


def fetch_transit_topup_pilot(subject_lat, subject_lon):
    """WARNING: SPENDS API CALLS (Routes Essentials, config.TRANSIT_TOPUP_PILOT_PER_RANGE per range).
    The pilot (TRN-14 (2)): the first pairs of each range, recorded in the selection file before sending,
    then report_topup. A rerun sends only pilot pairs not yet answered with HTTP 200."""
    pairs_df, out_path, selection_path, selection_df = _topup_files(subject_lat, subject_lon)
    if not len(selection_df):
        selection_df = _next_selection(pairs_df, selection_df, config.TRANSIT_ZONES_MIN,
                                       config.TRANSIT_TOPUP_PILOT_PER_RANGE, PILOT_CHUNK)
        _check_topup_bodies(pairs_df, selection_df[DRAW_NO_COL], len(selection_df))
        selection_path.parent.mkdir(parents=True, exist_ok=True)
        selection_df.to_csv(selection_path, index=False)
    _send_topup(pairs_df, selection_df[selection_df[CHUNK_COL] == PILOT_CHUNK], out_path, TOPUP_PILOT_RUN_ID)
    return report_topup(subject_lat, subject_lon)


def fetch_transit_topup(subject_lat, subject_lon):
    """WARNING: SPENDS API CALLS (Routes Essentials, up to config.TRANSIT_TOPUP_MAX_CALLS in all, pilot
    included). After the pilot and the user's commit (TRN-14 (3)): chunks of
    config.TRANSIT_TOPUP_CHUNK_PER_RANGE from each range whose zone is under
    config.TRANSIT_TOPUP_TARGET_PER_ZONE (earlier zone pairs included if config.TRANSIT_TOPUP_COUNTS_EARLIER),
    zones recounted after each chunk from Google's answers only; a pair
    landing in the other zone counts there. Stops when both zones are full, or before a chunk would pass
    the ceiling (stop and ask). Each chunk is recorded in the selection file before it is sent, so a rerun
    first finishes it."""
    if config.TRANSIT_TOPUP_MAX_CALLS is None:
        raise RuntimeError("config.TRANSIT_TOPUP_MAX_CALLS is not set: the ceiling is set at the user's commit")
    pairs_df, out_path, selection_path, selection_df = _topup_files(subject_lat, subject_lon)
    if not (selection_df[CHUNK_COL] == PILOT_CHUNK).any():
        raise RuntimeError("run the pilot first (fetch_transit_topup_pilot)")
    _send_topup(pairs_df, selection_df, out_path, TOPUP_RUN_ID)      # finish any chunk a stop left unsent
    earlier = _earlier_zone_counts(subject_lat, subject_lon)
    while True:
        zones_df = _topup_zones(selection_df, out_path)
        open_zones = [zone_no for zone_no in config.TRANSIT_ZONES_MIN
                      if earlier[zone_no] + (zones_df.zone == zone_no).sum() < config.TRANSIT_TOPUP_TARGET_PER_ZONE]
        if not open_zones:
            print("both zones hold the target")
            break
        n_next = len(open_zones) * config.TRANSIT_TOPUP_CHUNK_PER_RANGE
        if len(selection_df) + n_next > config.TRANSIT_TOPUP_MAX_CALLS:
            print(f"stopped: {len(selection_df):,} calls sent, the next chunk ({n_next}) would pass the ceiling "
                  f"{config.TRANSIT_TOPUP_MAX_CALLS:,}; ask the user")
            break
        chunk_df = _next_selection(pairs_df, selection_df, open_zones, config.TRANSIT_TOPUP_CHUNK_PER_RANGE,
                                   int(selection_df[CHUNK_COL].max()) + 1)
        _check_topup_bodies(pairs_df, chunk_df[DRAW_NO_COL], len(chunk_df))
        selection_df = pd.concat([selection_df, chunk_df], ignore_index=True)
        selection_df.to_csv(selection_path, index=False)
        _send_topup(pairs_df, chunk_df, out_path, TOPUP_RUN_ID)
        print(f"chunk {int(chunk_df[CHUNK_COL].iloc[0])}: {len(chunk_df)} sent for ranges {open_zones}")
    return report_topup(subject_lat, subject_lon)
