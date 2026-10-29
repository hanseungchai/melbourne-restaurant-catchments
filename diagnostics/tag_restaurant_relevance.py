"""How restaurant-like is a Google place type? Probe against probe.

Claim (proposed, user 2026-10-12; DESIGN.md Q17, presentation of tag exclusions): a tag's general
relevance to restaurants can be measured as the share of places carrying that tag that the
restaurant probe also returns. Tags with low relevance are listed first and highlighted when readers
choose exclusions. Nothing in the pipeline relies on it yet.

Method (like for like, user's position: both sides fetched by the same method, noise included):
  restaurant side  the 2026-09-24 Text Search probe (IDs only, includedType restaurant, strict, five
                   query passes), frozen_inputs/places_text_probe_20260924: every ID any pass
                   returned, moved IDs mapped to their new ID.
  tag side         the same probe method with includedType = the tag, strict: same root box and
                   centre, same 100 km extent, same split rules (a pass returning >= SPLIT_AT, or the
                   cell's union exceeding T_SPLIT, splits the cell, down to MIN_EDGE_M), up to 3 pages
                   of 20, IDs-only field mask (free SKU), every request through api_ledger.
  relevance        r = |tag IDs in the restaurant union| / |tag IDs|, Wilson 95% interval.

Caveats stated up front: the two sides are fetched weeks apart; the restaurant probe misses ~10% of
what Nearby finds (DESIGN_pre_spine, probe) and some of its cells were capped at 60, both of which lower r.
Side check, not the figure: how many tag places the rebuilt Nearby venue table holds, and how many of
those the restaurant probe found (the probe's recall for this type).

Saved data (reused, never overwritten; a rerun with --fetch resumes an incomplete pull):
  diagnostic_data/tag_restaurant_relevance_<fetch date>_<tag>_raw.jsonl   one line per (cell, query)
Results (one run per day): diagnostic_data/tag_restaurant_relevance_<run date>_<tag>_{ids.csv,log.txt}

Without saved data the script prints the plan and stops; --fetch sends requests (user's OK first, S5).

Conclusion: not fetched. Built 2026-10-12 for gas_station, then set aside the same day: the free
primaryType check (diagnostics/tag_primary_type.py) answers the ordering question for venues in the
pool, which is what readers choose from; r would describe a type in general.
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

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import api_ledger  # noqa: E402  the budget ledger; every request is recorded (never bypassed)

NAME = "tag_restaurant_relevance"
RUN_DATE = date.today().strftime("%Y%m%d")

RESTAURANT_PROBE_DIR = PROJECT_ROOT / "frozen_inputs" / "places_text_probe_20260924"
CENTRE_PATH = PROJECT_ROOT / "frozen_inputs" / "manual_inputs" / "subject_business_coord.txt"
VENUES_PATH = PROJECT_ROOT / "outputs" / "legacy_rebuilds" / "venues" / "venues_20260925_expanded.csv"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"

# Tag probed and its query passes (the restaurant probe used five; strict type does the filtering).
TAG_QUERIES = {"gas_station": ("gas station", "petrol station")}

# Probe method, as hex_search_expanded at legacy-final.
ROOT_EDGE_M = 800 * 2 ** 8          # 204.8 km root cell centred on the scan centre
EXTENT_R_M = 100_000                # cells wholly beyond this distance are not probed
MIN_EDGE_M = 25                     # smallest cell edge
SPLIT_AT = 50                       # a pass returning this many IDs splits the cell
T_SPLIT = 20                        # a cell whose union exceeds this splits
CAP = 60                            # Text Search returns at most 3 pages of 20
PAGE_SIZE = 20
MAX_PAGES = 3
METRES_PER_DEG_LAT = 111_320
EARTH_RADIUS_M = 6_371_000

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.movedPlace,places.movedPlaceId,nextPageToken"
ID_ONLY_FIELDS = {"places.attributions", "places.id", "places.consumerAlert", "places.name",
                  "nextPageToken", "places.movedPlace", "places.movedPlaceId"}
SKU = "text_search_ids_only"
API_KEY_ENV_VAR = "GOOGLE_API_KEY"
REQUESTS_PER_MIN = 500
REQUEST_TIMEOUT_S = 15
MAX_RETRIES = 5
RETRYABLE_STATUS = (429, 500, 502, 503)

WILSON_Z = 1.96
TAG_SEPARATOR = "|"


def check_mask():
    extra = set(FIELD_MASK.split(",")) - ID_ONLY_FIELDS
    if extra:
        raise RuntimeError(f"field mask leaves the free IDs-only SKU: {sorted(extra)}")


check_mask()   # fail at import, before any request can be sent


# ---------- geometry (legacy functions.root_box / split_box / box_dist_range) ----------

def haversine_m(lat1, lng1, lat2, lng2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_centre():
    lat, lng = CENTRE_PATH.read_text().splitlines()[0].split(",")
    return float(lat), float(lng)


def root_box(lat, lng):
    dlat = ROOT_EDGE_M / 2 / METRES_PER_DEG_LAT
    dlng = ROOT_EDGE_M / 2 / (METRES_PER_DEG_LAT * math.cos(math.radians(lat)))
    return (lat - dlat, lng - dlng, lat + dlat, lng + dlng)


def split_box(box):
    """Children keyed SW=0, SE=1, NW=2, NE=3, as the restaurant probe's quadkeys."""
    lo_lat, lo_lng, hi_lat, hi_lng = box
    mid_lat, mid_lng = (lo_lat + hi_lat) / 2, (lo_lng + hi_lng) / 2
    return [("0", (lo_lat, lo_lng, mid_lat, mid_lng)), ("1", (lo_lat, mid_lng, mid_lat, hi_lng)),
            ("2", (mid_lat, lo_lng, hi_lat, mid_lng)), ("3", (mid_lat, mid_lng, hi_lat, hi_lng))]


def nearest_m(lat, lng, box):
    lo_lat, lo_lng, hi_lat, hi_lng = box
    return haversine_m(lat, lng, min(max(lat, lo_lat), hi_lat), min(max(lng, lo_lng), hi_lng))


# ---------- restaurant side ----------

def restaurant_union():
    """Every ID the restaurant probe returned (moved IDs mapped), and the share of capped records."""
    ids, moved, n_records, n_capped = set(), {}, 0, 0
    for path in RESTAURANT_PROBE_DIR.rglob("*.jsonl"):
        with path.open(encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                ids.update(rec["ids"])
                moved.update(rec.get("moved") or {})
                n_records += 1
                n_capped += bool(rec["capped"])
    return {moved.get(i, i) for i in ids} | set(moved.values()), n_records, n_capped


# ---------- tag side: fetch ----------

class Throttle:
    def __init__(self, per_min):
        self.gap_s, self.last = 60 / per_min, 0.0

    def wait(self):
        dt = time.monotonic() - self.last
        if dt < self.gap_s:
            time.sleep(self.gap_s - dt)
        self.last = time.monotonic()


def search_page(session, body, throttle, run_id):
    api_key = os.environ[API_KEY_ENV_VAR]   # read at call time only (CLAUDE.md S3)
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK}
    meta = {"page_token": "pageToken" in body, "text_query": body["textQuery"],
            "included_type": body["includedType"], "rect": body["locationRestriction"]["rectangle"]}
    last = None
    for attempt in range(MAX_RETRIES):
        throttle.wait()
        req_id = api_ledger.record_send(SKU, endpoint="searchText", run_id=run_id, meta={**meta, "attempt": attempt})
        try:
            resp = session.post(TEXT_SEARCH_URL, json=body, headers=headers, timeout=REQUEST_TIMEOUT_S)
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
        if not (resp.status_code in RETRYABLE_STATUS or (resp.status_code == 400 and "pageToken" in body)):
            raise RuntimeError(last)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"max retries reached: {last}")


def probe_cell(session, box, text_query, tag, throttle, run_id):
    lo_lat, lo_lng, hi_lat, hi_lng = box
    body = {"textQuery": text_query, "includedType": tag, "strictTypeFiltering": True, "pageSize": PAGE_SIZE,
            "locationRestriction": {"rectangle": {"low": {"latitude": lo_lat, "longitude": lo_lng},
                                                  "high": {"latitude": hi_lat, "longitude": hi_lng}}}}
    ids, moved, pages = [], {}, 0
    while True:
        data = search_page(session, body, throttle, run_id)
        pages += 1
        for place in data.get("places", []):
            ids.append(place["id"])
            if "movedPlaceId" in place:
                moved[place["id"]] = place["movedPlaceId"]
        token = data.get("nextPageToken")
        if not token or pages >= MAX_PAGES:
            return list(dict.fromkeys(ids)), moved, pages
        body = {**body, "pageToken": token}


def raw_paths(tag):
    return sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_{tag}_raw.jsonl"))


def load_raw(path):
    with path.open(encoding="utf-8") as f:
        return {(r["quadkey"], r["text_query"]): r for r in map(json.loads, f) if r}


def walk(tag, done, centre, fetch=None):
    """Depth-first over the quadtree. Cells answered in `done` are reused; others are fetched with
    `fetch(quadkey, box, query)` or, without it, counted as pending. Returns (records, pending)."""
    lat, lng = centre
    stack, records, pending = [("R", root_box(lat, lng))], [], []
    while stack:
        key, box = stack.pop()
        if nearest_m(lat, lng, box) > EXTENT_R_M:
            continue
        cell, missing = [], False
        for query in TAG_QUERIES[tag]:
            rec = done.get((key, query))
            if rec is None and fetch is not None:
                rec = fetch(key, box, query)
            if rec is None:
                missing = True
                continue
            cell.append(rec)
        if missing:
            pending.append(key)
            continue
        records.extend(cell)
        union = set().union(*(r["ids"] for r in cell))
        edge_m = ROOT_EDGE_M / 2 ** (len(key) - 1)
        can_split = edge_m / 2 >= MIN_EDGE_M
        if can_split and (any(r["n_ids"] >= SPLIT_AT for r in cell) or len(union) > T_SPLIT):
            stack.extend((key + q, child) for q, child in split_box(box))
    return records, pending


def run_fetch(tag, centre):
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = raw_paths(tag)
    path = existing[-1] if existing else DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_{tag}_raw.jsonl"
    done = load_raw(path) if path.exists() else {}
    run_id = f"{NAME}_{tag}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
    api_ledger.check(SKU)
    session, throttle = requests.Session(), Throttle(REQUESTS_PER_MIN)
    out = path.open("a", encoding="utf-8")
    n_sent = [0]

    def fetch(key, box, query):
        ids, moved, pages = probe_cell(session, box, query, tag, throttle, run_id)
        rec = dict(quadkey=key, depth=len(key) - 1, text_query=query, included_type=tag, strict_type=True,
                   n_ids=len(ids), capped=len(ids) >= CAP, pages=pages, ids=ids, moved=moved,
                   field_mask=FIELD_MASK, collection_datetime_utc=datetime.now(timezone.utc).isoformat(),
                   run_id=run_id, record_id=uuid.uuid4().hex)
        out.write(json.dumps(rec) + "\n")
        out.flush()
        n_sent[0] += 1
        print(f"{key} d{rec['depth']} '{query}': {len(ids)} ids, {pages} page(s)")
        return rec

    try:
        walk(tag, done, centre, fetch)
    finally:
        out.close()
    print(f"fetched {n_sent[0]} cell-queries into {path.name}")
    return path


# ---------- report ----------

def wilson(k, n):
    if n == 0:
        return float("nan"), float("nan")
    p, z2 = k / n, WILSON_Z ** 2
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = WILSON_Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return centre - half, centre + half


def report(tag, path, centre):
    lines = []

    def say(text=""):
        print(text)
        lines.append(text + "\n")

    records, pending = walk(tag, load_raw(path), centre)
    moved = {k: v for r in records for k, v in r["moved"].items()}
    tag_ids = {moved.get(i, i) for r in records for i in r["ids"]}
    union, n_rest_records, n_rest_capped = restaurant_union()
    in_union = tag_ids & union
    lo, hi = wilson(len(in_union), len(tag_ids))
    say(f"{NAME}, run {RUN_DATE}; tag data {path.name} (reused)")
    say(f"tag {tag}: {len(records)} cell-queries, {len({r['quadkey'] for r in records})} cells, "
        f"{sum(r['capped'] for r in records)} capped, {len(pending)} cells pending")
    say(f"restaurant probe: {len(union)} IDs from {n_rest_records} cell-queries "
        f"({n_rest_capped} capped), collected 2026-09-23/24")
    say(f"relevance r = {len(in_union)} / {len(tag_ids)} = {len(in_union) / max(len(tag_ids), 1):.1%} "
        f"(Wilson 95% {lo:.1%} to {hi:.1%})")

    venues_df = pd.read_csv(VENUES_PATH, usecols=["place_id", "types", "name"]).drop_duplicates("place_id")
    is_tagged = venues_df["types"].fillna("").str.split(TAG_SEPARATOR).apply(lambda tags: tag in tags)
    table_ids = set(venues_df.loc[is_tagged, "place_id"])
    say(f"side check (not the figure): Nearby venue table has {len(table_ids)} {tag} venues; "
        f"{len(table_ids & tag_ids)} found by the {tag} probe; {len(table_ids & union)} by the restaurant probe")

    names = venues_df.set_index("place_id")["name"]
    ids_df = pd.DataFrame({"place_id": sorted(tag_ids)})
    ids_df["in_restaurant_probe"] = ids_df["place_id"].isin(union)
    ids_df["in_venue_table"] = ids_df["place_id"].isin(set(venues_df["place_id"]))
    ids_df["name_from_venue_table"] = ids_df["place_id"].map(names)
    say(f"\n{tag} places the restaurant probe also returned ({len(in_union)}; names where the venue table has them):")
    for row in ids_df[ids_df["in_restaurant_probe"]].itertuples():
        say(f"  {row.place_id}  {row.name_from_venue_table if isinstance(row.name_from_venue_table, str) else '-'}")

    stem = DIAGNOSTIC_DATA_DIR / f"{NAME}_{RUN_DATE}_{tag}"
    ids_df.to_csv(f"{stem}_ids.csv", index=False)
    Path(f"{stem}_log.txt").write_text("".join(lines), encoding="utf-8")
    print(f"saved {Path(f'{stem}_ids.csv').name}, {Path(f'{stem}_log.txt').name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=next(iter(TAG_QUERIES)), choices=sorted(TAG_QUERIES))
    parser.add_argument("--fetch", action="store_true", help="send requests (free IDs-only SKU, via api_ledger)")
    args = parser.parse_args()
    centre = load_centre()

    existing = raw_paths(args.tag)
    if args.fetch:
        path = run_fetch(args.tag, centre)
    elif existing:
        path = existing[-1]
    else:
        _, pending = walk(args.tag, {}, centre)
        print(f"no saved {args.tag} data. Plan: start at the root cell with queries {TAG_QUERIES[args.tag]}, "
              f"{len(pending)} cell(s) to probe before splits; IDs-only SKU (free, uncapped in api_ledger), "
              f"<= {MAX_PAGES} requests per cell-query, {REQUESTS_PER_MIN}/min.")
        print("Rerun with --fetch once the user has OKed the calls (CLAUDE.md S5).")
        return
    report(args.tag, path, centre)


if __name__ == "__main__":
    main()
