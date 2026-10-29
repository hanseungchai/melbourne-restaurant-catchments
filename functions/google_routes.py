"""Google Routes API (computeRoutes) requests.

post_compute_routes: one request with a given body and field mask, retried on network errors, 429 and
5xx. Callers build the body, record each attempt in the API ledger (before_send) and keep the raw
answer. Used by transit_fetch and drive_samples (request_drive_route).
"""
import random
import time

import requests

import config

API_KEY_HEADER = "X-Goog-Api-Key"
FIELD_MASK_HEADER = "X-Goog-FieldMask"
HTTP_OK = 200
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR_MIN = 500           # 5xx: retried, like 429
ERROR_TEXT_MAX_CHARS = 200            # response text shown for a non-retried error


def _backoff_s(attempt):
    return config.ROUTES_BACKOFF_BASE_S ** attempt + random.uniform(0, config.ROUTES_BACKOFF_JITTER_MAX_S)


def post_compute_routes(body, field_mask, api_key, before_send):
    """One computeRoutes request. before_send() runs before every attempt, retries included, and
    returns that attempt's ledger id. Returns (http_status, response JSON or None, last ledger id);
    http_status None after the last retry fails."""
    headers = {"Content-Type": "application/json", API_KEY_HEADER: api_key, FIELD_MASK_HEADER: field_mask}
    req_id = None
    for attempt in range(1, config.ROUTES_MAX_RETRIES + 1):
        req_id = before_send()
        try:
            response = requests.post(config.ROUTES_API_URL, headers=headers, json=body,
                                     timeout=config.ROUTES_REQUEST_TIMEOUT_S)
        except requests.exceptions.RequestException as error:
            wait_s = _backoff_s(attempt)
            print(f"    network error ({error}), retry in {wait_s:.1f}s")
            time.sleep(wait_s)
            continue

        if response.status_code == HTTP_OK:
            return HTTP_OK, response.json(), req_id
        if response.status_code == HTTP_TOO_MANY_REQUESTS or response.status_code >= HTTP_SERVER_ERROR_MIN:
            wait_s = _backoff_s(attempt)
            print(f"    HTTP {response.status_code}, retry in {wait_s:.1f}s")
            time.sleep(wait_s)
            continue
        print(f"    HTTP {response.status_code}: {response.text[:ERROR_TEXT_MAX_CHARS]}")
        return response.status_code, None, req_id

    print(f"    failed after {config.ROUTES_MAX_RETRIES} retries")
    return None, None, req_id
