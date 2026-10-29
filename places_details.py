"""Fresh Places Details (Enterprise fields) pulls: draw the venues, then fetch them.

Two steps, run in order by main.py's fetch_enterprise_hours block:
- draw_enterprise_hours_sample(): free. A uniform random draw of config.ENTERPRISE_HOURS_SAMPLE_SIZE
  venues from the current venue table, plus config.ENTERPRISE_HOURS_FIXED_PLACE_IDS listed first.
  Saved once to config.ENTERPRISE_HOURS_DRAW_PATH; an existing draw is reused, never redrawn, so
  the sample stays fixed across restarts.
- fetch_enterprise_hours(): paid. One Place Details request per drawn venue, in draw order,
  saved as <place_id>.json in config.ENTERPRISE_HOURS_PULL_DIR. A 404 (place id no longer valid)
  goes on the pull's not-found list, config.ENTERPRISE_HOURS_NOT_FOUND_PATH, instead. Venues saved
  or on that list are skipped, so a restart never pays twice. Every attempt is recorded in
  api_ledger before it is sent.

The saved JSON is the API response plus "fetched_date" and "is_fixed", the same shape as the
2026-09-02 pull, so the opening-hours histogram code can read either.
"""
import json
import time
from datetime import date

import pandas as pd

import api_ledger
import config
from functions.google_places import PlaceNotFoundError, fetch_place, read_google_api_key

LEDGER_SKU = "place_details_enterprise"
LEDGER_ENDPOINT = "places/details"   # as recorded by the earlier Enterprise fetches
LEDGER_STATUS_OK = "ok"
LEDGER_STATUS_FAILED = "failed"
LEDGER_STATUS_NOT_FOUND = "not_found"

PLACE_ID_COL = "place_id"
NAME_COL = "name"
RING_COL = "run_id"                  # venue table's collection ring: old_legacy, repair_ring, outer_ring
IS_FIXED_COL = "is_fixed"
DRAW_ORDER_COL = "draw_order"
DRAW_COLS = [DRAW_ORDER_COL, PLACE_ID_COL, NAME_COL, RING_COL, IS_FIXED_COL]

HTTP_STATUS_COL = "http_status"
ERROR_MESSAGE_COL = "error_message"
CHECKED_DATE_COL = "checked_date"
NOT_FOUND_COLS = [PLACE_ID_COL, HTTP_STATUS_COL, ERROR_MESSAGE_COL, CHECKED_DATE_COL]

FETCHED_DATE_KEY = "fetched_date"    # added to each saved JSON, as in the 2026-09-02 pull
IS_FIXED_KEY = "is_fixed"            # added to each saved JSON: fixed venue, not part of the draw
JSON_SUFFIX = ".json"
TEMP_SUFFIX = ".tmp"


def draw_enterprise_hours_sample():
    """Draw the venues for this pull, or reuse the saved draw. Returns the draw DataFrame.

    Fixed venues come first (is_fixed True), then the random draw in sampled order. The random
    draw excludes the fixed venues, so each venue appears once.
    """
    draw_path = config.ENTERPRISE_HOURS_DRAW_PATH
    if draw_path.exists():
        draw_df = pd.read_csv(draw_path)
        print(f"draw exists, reused: {draw_path.name} ({len(draw_df)} venues, "
              f"{int(draw_df[IS_FIXED_COL].sum())} fixed)")
        return draw_df

    venues_df = pd.read_csv(config.VENUE_TABLES[config.HEX_VENUES_DATE])
    fixed_ids = config.ENTERPRISE_HOURS_FIXED_PLACE_IDS
    missing_fixed_ids = set(fixed_ids) - set(venues_df[PLACE_ID_COL])
    if missing_fixed_ids:
        raise ValueError(f"fixed place ids not in the venue table: {sorted(missing_fixed_ids)}")

    fixed_df = venues_df.set_index(PLACE_ID_COL).loc[fixed_ids].reset_index()
    fixed_df[IS_FIXED_COL] = True
    pool_df = venues_df[~venues_df[PLACE_ID_COL].isin(fixed_ids)]
    random_df = pool_df.sample(n=config.ENTERPRISE_HOURS_SAMPLE_SIZE,
                               random_state=config.ENTERPRISE_HOURS_SEED)
    random_df = random_df.assign(**{IS_FIXED_COL: False})

    draw_df = pd.concat([fixed_df, random_df], ignore_index=True)
    draw_df[DRAW_ORDER_COL] = range(1, len(draw_df) + 1)
    draw_df = draw_df[DRAW_COLS]

    draw_path.parent.mkdir(parents=True, exist_ok=True)
    draw_df.to_csv(draw_path, index=False)
    print(f"drew {len(random_df)} of {len(pool_df)} venues (seed {config.ENTERPRISE_HOURS_SEED}) "
          f"+ {len(fixed_df)} fixed -> {draw_path.name}")
    print(draw_df.loc[~draw_df[IS_FIXED_COL], RING_COL].value_counts().to_string())
    return draw_df


def fetch_enterprise_hours(limit=None):
    """Fetch Place Details for the drawn venues not yet saved, in draw order. Paid.

    limit: at most this many venues this run (e.g. 1 for a test call); None = all remaining.
    Checks the whole run against the monthly allowance before the first call. Retries inside
    fetch_place count as calls, so a run can use more calls than venues; the ledger refuses any
    call past the allowance.
    """
    draw_df = draw_enterprise_hours_sample()
    pull_dir = config.ENTERPRISE_HOURS_PULL_DIR
    pull_dir.mkdir(parents=True, exist_ok=True)

    is_saved = draw_df[PLACE_ID_COL].map(lambda place_id: _json_path(place_id).exists())
    is_not_found = draw_df[PLACE_ID_COL].isin(_read_not_found()[PLACE_ID_COL])
    to_fetch_df = draw_df[~is_saved & ~is_not_found]
    if limit is not None:
        to_fetch_df = to_fetch_df.head(limit)
    print(f"{int(is_saved.sum())} of {len(draw_df)} already saved, {int(is_not_found.sum())} "
          f"not found (skipped); fetching {len(to_fetch_df)}")
    if to_fetch_df.empty:
        return

    api_ledger.check(LEDGER_SKU, n=len(to_fetch_df))
    api_key = read_google_api_key()
    run_id = f"enterprise_hours_{config.ENTERPRISE_HOURS_PULL_DATE}"
    fetched_date = date.today().isoformat()

    failed_ids = []
    not_found_ids = []
    last_send_s = [None]   # monotonic time of the last request sent, shared across venues
    for venue in to_fetch_df.itertuples(index=False):
        place_id = getattr(venue, PLACE_ID_COL)
        sent_req_ids = []

        def record_attempt():
            _wait_for_request_slot(last_send_s)
            last_send_s[0] = time.monotonic()
            sent_req_ids.append(api_ledger.record_send(
                LEDGER_SKU, endpoint=LEDGER_ENDPOINT, run_id=run_id,
                meta={"place_id": place_id, "draw_order": int(getattr(venue, DRAW_ORDER_COL)),
                      "attempt": len(sent_req_ids) + 1}))

        try:
            record = fetch_place(api_key, place_id, before_send=record_attempt)
        except PlaceNotFoundError as error:
            api_ledger.record_result(sent_req_ids[-1], status=LEDGER_STATUS_NOT_FOUND)
            record_not_found(place_id, error.http_status, error.error_message, fetched_date)
            not_found_ids.append(place_id)
            continue
        status = LEDGER_STATUS_OK if record is not None else LEDGER_STATUS_FAILED
        if sent_req_ids:
            api_ledger.record_result(sent_req_ids[-1], status=status)
        if record is None:
            failed_ids.append(place_id)
            continue

        record[FETCHED_DATE_KEY] = fetched_date
        record[IS_FIXED_KEY] = bool(getattr(venue, IS_FIXED_COL))
        _write_json(record, _json_path(place_id))

    n_saved = len(list(pull_dir.glob(f"*{JSON_SUFFIX}")))
    n_fetched = len(to_fetch_df) - len(failed_ids) - len(not_found_ids)
    print(f"fetched {n_fetched}, failed {len(failed_ids)}, not found {len(not_found_ids)}; "
          f"{n_saved} of {len(draw_df)} saved in {pull_dir.name}")
    if failed_ids:
        print("failed (no file saved; a rerun retries them): " + ", ".join(failed_ids))
    if not_found_ids:
        print(f"not found (listed in {config.ENTERPRISE_HOURS_NOT_FOUND_PATH.name}; a rerun skips them): "
              + ", ".join(not_found_ids))
    print(f"{LEDGER_SKU}: {api_ledger.remaining(LEDGER_SKU)} calls left this month")


def record_not_found(place_id, http_status, error_message, checked_date):
    """Add one venue to this pull's not-found list (config.ENTERPRISE_HOURS_NOT_FOUND_PATH), once.

    checked_date: ISO date of the call that got the 404.
    """
    not_found_df = _read_not_found()
    if place_id in set(not_found_df[PLACE_ID_COL]):
        return
    new_row_df = pd.DataFrame([[place_id, http_status, error_message, checked_date]], columns=NOT_FOUND_COLS)
    not_found_df = pd.concat([not_found_df, new_row_df], ignore_index=True)
    path = config.ENTERPRISE_HOURS_NOT_FOUND_PATH
    temp_path = path.with_suffix(TEMP_SUFFIX)
    not_found_df.to_csv(temp_path, index=False)
    temp_path.replace(path)


def _read_not_found():
    """This pull's not-found list; empty, with its columns, if there is none yet."""
    path = config.ENTERPRISE_HOURS_NOT_FOUND_PATH
    if not path.exists():
        return pd.DataFrame(columns=NOT_FOUND_COLS)
    return pd.read_csv(path)


def _wait_for_request_slot(last_send_s):
    """Sleep until config.PLACES_MIN_REQUEST_INTERVAL_S has passed since the last request sent."""
    if last_send_s[0] is None:
        return
    wait_s = config.PLACES_MIN_REQUEST_INTERVAL_S - (time.monotonic() - last_send_s[0])
    if wait_s > 0:
        time.sleep(wait_s)


def _json_path(place_id):
    """Saved JSON for one venue of this pull."""
    return config.ENTERPRISE_HOURS_PULL_DIR / f"{place_id}{JSON_SUFFIX}"


def _write_json(record, path):
    """Write via a temp file, so an interrupted write never leaves a partial file that counts as saved."""
    temp_path = path.with_suffix(TEMP_SUFFIX)
    temp_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)
