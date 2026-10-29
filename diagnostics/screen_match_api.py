"""Does the API order match what Google Maps shows on screen? (DESIGN.md Q19, screen-matching test)

Claim (planned, 103rd): Text Search (New) with an IDs-only field mask reproduces the order of the
"Restaurants" list the user saw on screen closely enough to stand in for it; which search area and
open-status setting gets closest sets the main fetch's search area and open-status handling (Q19).
Nothing in the pipeline relies on it yet.

Screens (inputs/manual_map_test/, transcribed in diagnostics/diagnostic_data/screen_match_20261025_*.csv):
  browser  Chrome, URL @-37.817501,144.9501715,2982m, 12:19-12:21. Viewport read off 1.png: scale bar
           ~2.2 m/px; the map canvas spans the full 1920 px window width with the URL centre at its
           middle (x 960, y 645 between the toolbar and the taskbar); the list panel hides x < 610, so
           the visible map runs from -350 px to +960 px east of centre and +-495 px north/south.
  phone    Android app, 12:06-12:12, distances from the blue dot; centre given on the command line.
Arms per screen: viewport restriction, viewport bias, 1 km circle bias, each with openNow off and on;
query "Restaurants" (as typed), no includedType, up to 3 pages of 20, IDs-only (free SKU), every
request through api_ledger. Calls are made after the screens (open status has moved).

Saved data (never overwritten; a rerun skips arms already saved):
  diagnostic_data/screen_match_api_<fetch date>_raw.jsonl   one line per (screen, arm), IDs in API order

Conclusion: pending.
"""

import argparse
import json
import math
import os
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import api_ledger  # noqa: E402  the budget ledger; every request is recorded (never bypassed)

NAME = "screen_match_api"
RUN_DATE = date.today().strftime("%Y%m%d")
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
RAW_PATH = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_raw.jsonl"

TEXT_QUERY = "Restaurants"
BROWSER_CENTRE = (-37.817501, 144.9501715)   # from the browser URL
BROWSER_M_PER_PX = 2.2                       # read off the 200 m scale bar in 1.png
BROWSER_WEST_PX = -350                       # visible map edge west of the URL centre (panel covers the rest)
BROWSER_EAST_PX = 960
BROWSER_HALF_HEIGHT_PX = 495
CIRCLE_RADIUS_M = 1000
TIGHT_RADIUS_M = 300                         # extra arm: tight circle
METRES_PER_DEG_LAT = 111_320

PAGE_SIZE = 20
MAX_PAGES = 3
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,nextPageToken"
ID_ONLY_FIELDS = {"places.attributions", "places.id", "places.consumerAlert", "places.name",
                  "nextPageToken", "places.movedPlace", "places.movedPlaceId"}
SKU = "text_search_ids_only"
NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
NEARBY_FIELD_MASK = "places.id"             # Nearby has no page token
NEARBY_SKU = "nearby_pro"                    # paid SKU inside the 5,000/month free cap (user's go, 2026-10-25)
NEARBY_MAX_RESULTS = 20                      # Nearby Search (New) returns at most 20, no further pages
NEARBY_RADII_M = (500, 1000, 1500)
NEARBY_TYPE_KEYS = ("includedTypes", "includedPrimaryTypes")
API_KEY_ENV_VAR = "GOOGLE_API_KEY"
REQUEST_TIMEOUT_S = 15
MAX_RETRIES = 5
RETRYABLE_STATUS = (429, 500, 502, 503)
PAGE_TOKEN_WAIT_S = 2


def check_mask():
    extra = set(FIELD_MASK.split(",")) - ID_ONLY_FIELDS
    if extra:
        raise RuntimeError(f"field mask leaves the free IDs-only SKU: {sorted(extra)}")


check_mask()   # fail at import, before any request can be sent


def offset_deg(lat, north_m, east_m):
    return north_m / METRES_PER_DEG_LAT, east_m / (METRES_PER_DEG_LAT * math.cos(math.radians(lat)))


def rectangle(centre, south_m, west_m, north_m, east_m):
    lat, lng = centre
    lo_lat, lo_lng = offset_deg(lat, -south_m, -west_m)
    hi_lat, hi_lng = offset_deg(lat, north_m, east_m)
    return {"rectangle": {"low": {"latitude": lat + lo_lat, "longitude": lng + lo_lng},
                          "high": {"latitude": lat + hi_lat, "longitude": lng + hi_lng}}}


def circle(centre, radius_m):
    return {"circle": {"center": {"latitude": centre[0], "longitude": centre[1]}, "radius": radius_m}}


def browser_viewport():
    half_h_m = BROWSER_HALF_HEIGHT_PX * BROWSER_M_PER_PX
    return rectangle(BROWSER_CENTRE, half_h_m, -BROWSER_WEST_PX * BROWSER_M_PER_PX,
                     half_h_m, BROWSER_EAST_PX * BROWSER_M_PER_PX)


def arms(screen, centre, viewport):
    """(arm name, body) for each search area x openNow setting."""
    areas = [("circle_1km", "locationBias", circle(centre, CIRCLE_RADIUS_M))]
    if viewport is not None:
        areas = [("viewport_restrict", "locationRestriction", viewport),
                 ("viewport_bias", "locationBias", viewport)] + areas
    out = []
    for area_name, key, area in areas:
        for is_open_now in (False, True):
            body = {"textQuery": TEXT_QUERY, "pageSize": PAGE_SIZE, key: area}
            if is_open_now:
                body["openNow"] = True
            out.append((f"{screen}_{area_name}_open{int(is_open_now)}", body))
    return out


def extra_arms(screen, centre):
    """Added after the first comparison (screen top 10 nearly absent from the 1 km arms): distance ranking,
    a tight circle, strict restaurant type. Sent ~45 min after the screens."""
    base = {"textQuery": TEXT_QUERY, "pageSize": PAGE_SIZE}
    return [
        (f"{screen}_circle_1km_rankdist_open0", {**base, "locationBias": circle(centre, CIRCLE_RADIUS_M),
                                                  "rankPreference": "DISTANCE"}),
        (f"{screen}_circle_1km_rankdist_open1", {**base, "locationBias": circle(centre, CIRCLE_RADIUS_M),
                                                  "rankPreference": "DISTANCE", "openNow": True}),
        (f"{screen}_circle_300m_open0", {**base, "locationBias": circle(centre, TIGHT_RADIUS_M)}),
        (f"{screen}_circle_1km_typed_open0", {**base, "locationBias": circle(centre, CIRCLE_RADIUS_M),
                                              "includedType": "restaurant", "strictTypeFiltering": True}),
    ]


def nearby_arms(screen, centre, type_keys):
    """Popularity-ranked Nearby Search (New): the documented prominence order (no openNow filter exists)."""
    out = []
    for type_key in type_keys:
        for radius_m in NEARBY_RADII_M:
            body = {type_key: ["restaurant"], "maxResultCount": NEARBY_MAX_RESULTS, "rankPreference": "POPULARITY",
                    "locationRestriction": circle(centre, radius_m)}
            tag = "primary" if type_key == "includedPrimaryTypes" else "typed"
            out.append((f"{screen}_nearby_pop_{tag}_{radius_m}m", body))
    return out


def search_page(session, body, run_id, arm, url=TEXT_SEARCH_URL, sku=SKU):
    api_key = os.environ[API_KEY_ENV_VAR]   # read at call time only (CLAUDE.md S3)
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": api_key, "X-Goog-FieldMask": NEARBY_FIELD_MASK if url == NEARBY_URL else FIELD_MASK}
    meta = {"arm": arm, "page_token": "pageToken" in body}
    last = None
    for attempt in range(MAX_RETRIES):
        req_id = api_ledger.record_send(sku, endpoint=url.rsplit(":", 1)[1], run_id=run_id, meta={**meta, "attempt": attempt})
        try:
            resp = session.post(url, json=body, headers=headers, timeout=REQUEST_TIMEOUT_S)
        except (requests.Timeout, requests.ConnectionError) as e:
            api_ledger.record_result(req_id, status=type(e).__name__)
            last = repr(e)
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 200:
            data = resp.json()
            api_ledger.record_result(req_id, status=200, n_results=len(data.get("places", [])))
            return data
        api_ledger.record_result(req_id, status=resp.status_code)
        last = f"HTTP {resp.status_code}: {resp.text[:300]}"
        if "per day" in resp.text:   # a daily quota won't clear by retrying
            raise RuntimeError(last)
        if not (resp.status_code in RETRYABLE_STATUS or (resp.status_code == 400 and "pageToken" in body)):
            raise RuntimeError(last)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"max retries reached: {last}")


def fetch_arm(session, body, run_id, arm):
    if "rankPreference" in body and "textQuery" not in body:   # Nearby: one page only
        data = search_page(session, body, run_id, arm, url=NEARBY_URL, sku=NEARBY_SKU)
        return [p["id"] for p in data.get("places", [])]
    ids, page_body = [], dict(body)
    for page in range(MAX_PAGES):
        data = search_page(session, page_body, run_id, arm)
        ids += [p["id"] for p in data.get("places", [])]
        token = data.get("nextPageToken")
        if not token:
            break
        time.sleep(PAGE_TOKEN_WAIT_S)
        page_body = {**body, "pageToken": token}
    return ids


def saved_arms():
    if not RAW_PATH.exists():
        return set()
    with RAW_PATH.open(encoding="utf-8") as f:
        return {json.loads(line)["arm"] for line in f}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--screen", choices=["browser", "phone"], required=True)
    parser.add_argument("--centre", help="lat,lng for the phone screen (blue dot)")
    parser.add_argument("--extra", action="store_true", help="the extra arms (distance rank, 300 m, typed)")
    parser.add_argument("--nearby", action="store_true", help="popularity-ranked Nearby Search (paid SKU, free cap)")
    parser.add_argument("--fetch", action="store_true", help="send requests (free IDs-only SKU, via api_ledger)")
    args = parser.parse_args()

    if args.screen == "browser":
        planned = arms("browser", BROWSER_CENTRE, browser_viewport())
    else:
        lat, lng = (float(v) for v in args.centre.split(","))
        planned = arms("phone", (lat, lng), None)
    if args.extra:
        planned = extra_arms(args.screen, (lat, lng) if args.screen == "phone" else BROWSER_CENTRE)
    if args.nearby:
        centre = BROWSER_CENTRE if args.screen == "browser" else (lat, lng)
        planned = nearby_arms(args.screen, centre, NEARBY_TYPE_KEYS if args.screen == "phone" else NEARBY_TYPE_KEYS[:1])
    pending = [(arm, body) for arm, body in planned if arm not in saved_arms()]
    for arm, body in planned:
        print(("todo " if (arm, body) in pending else "saved ") + arm, json.dumps({k: v for k, v in body.items() if k != "textQuery"}))
    if not args.fetch or not pending:
        return

    if args.nearby:
        api_ledger.check(NEARBY_SKU, n=len(pending))
    else:
        api_ledger.check(SKU, n=len(pending) * MAX_PAGES)
    run_id = f"{NAME}_{uuid.uuid4().hex[:8]}"
    session = requests.Session()
    for arm, body in pending:
        fetched_at = datetime.now(timezone.utc).isoformat()
        ids = fetch_arm(session, body, run_id, arm)
        with RAW_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"arm": arm, "fetched_at": fetched_at, "body": body, "ids": ids}) + "\n")
        print(f"{arm}: {len(ids)} IDs at {fetched_at}")


if __name__ == "__main__":
    main()
