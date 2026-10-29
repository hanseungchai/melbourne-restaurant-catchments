"""Google Places API (New) requests.

fetch_place: one Place Details request with the Enterprise field mask, used by
places_details.fetch_enterprise_hours. A 404 (place id no longer valid) raises PlaceNotFoundError,
since unlike the other failures it is permanent.
"""
import os
import random
import time

import requests

import config

PLACES_DETAILS_URL_TEMPLATE = "https://places.googleapis.com/v1/places/{place_id}"
API_KEY_HEADER = "X-Goog-Api-Key"
FIELD_MASK_HEADER = "X-Goog-FieldMask"
HTTP_OK = 200
HTTP_NOT_FOUND = 404                  # place id no longer valid: permanent, not retried
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR_MIN = 500           # 5xx: retried, like 429
ERROR_TEXT_MAX_CHARS = 200            # response text shown for a non-retried error


class PlaceNotFoundError(Exception):
    """Place Details returned 404: the place id is no longer valid. Carries the HTTP status and message."""

    def __init__(self, place_id, http_status, error_message):
        super().__init__(f"{place_id}: HTTP {http_status}: {error_message}")
        self.place_id = place_id
        self.http_status = http_status
        self.error_message = error_message


def read_google_api_key():
    """Google API key from the environment, read at call time (CLAUDE.md S3)."""
    return os.environ[config.GOOGLE_API_KEY_ENV_VAR]


def fetch_place(api_key, place_id, before_send=None):
    """Place Details for one place id with the Enterprise field mask; the JSON dict, or None on failure.

    Raises PlaceNotFoundError on 404. Retries network errors, 429 and 5xx with exponential backoff plus jitter. before_send, if
    given, is called before every attempt, retries included (the API ledger's record_send).
    """
    url = PLACES_DETAILS_URL_TEMPLATE.format(place_id=place_id)
    headers = {API_KEY_HEADER: api_key, FIELD_MASK_HEADER: config.PLACES_ENTERPRISE_FIELD_MASK}

    for attempt in range(1, config.PLACES_MAX_RETRIES + 1):
        if before_send is not None:
            before_send()
        try:
            response = requests.get(url, headers=headers, timeout=config.PLACES_REQUEST_TIMEOUT_S)
        except requests.exceptions.RequestException as error:
            wait_s = _backoff_s(attempt)
            print(f"  [{place_id}] network error ({error}), retry in {wait_s:.1f}s")
            time.sleep(wait_s)
            continue

        if response.status_code == HTTP_OK:
            return response.json()
        if response.status_code == HTTP_NOT_FOUND:
            raise PlaceNotFoundError(place_id, response.status_code,
                                     response.text[:ERROR_TEXT_MAX_CHARS])
        if (response.status_code == HTTP_TOO_MANY_REQUESTS
                or response.status_code >= HTTP_SERVER_ERROR_MIN):
            wait_s = _backoff_s(attempt)
            print(f"  [{place_id}] HTTP {response.status_code}, retry in {wait_s:.1f}s")
            time.sleep(wait_s)
            continue

        print(f"  [{place_id}] HTTP {response.status_code}: {response.text[:ERROR_TEXT_MAX_CHARS]}")
        return None

    print(f"  [{place_id}] failed after {config.PLACES_MAX_RETRIES} retries")
    return None


def _backoff_s(attempt):
    """Wait before the next attempt: base ** attempt seconds plus random jitter."""
    return config.PLACES_BACKOFF_BASE_S ** attempt + random.uniform(0, config.PLACES_BACKOFF_JITTER_MAX_S)
