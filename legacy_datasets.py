"""Rebuild the legacy venue datasets from frozen inputs.

One pipeline, run by rebuild_legacy_datasets(): it recreates every dataset the legacy code
produced between the 2026-06-29 scan and the expanded venue table. It reads only from
frozen_inputs/ and writes only to outputs/legacy_rebuilds/; nothing here calls an API.
Each output matches the legacy file it replaces (see the "legacy:" comments in config.py).
The opening-hours histogram is opening_hours.py.
"""
import json

import numpy as np
import pandas as pd

import config
from functions.geometry import haversine_m
from functions.input_helper import read_subject_location

SCAN_FILE_PATTERN = "*.json"          # Nearby scan: one output_<radius m>.json per search radius
DETAILS_FILE_PATTERN = "*.json"       # Places Details: one <place_id>.json per venue
OPERATIONAL_STATUS = "OPERATIONAL"    # Places business_status of an open venue
TYPE_SEPARATOR = "|"                  # joins a venue's Places types into one text column
LEGACY_SCAN_RUN_ID = "old_legacy"     # run_id given to pre-expansion venues in the expanded table


def rebuild_legacy_datasets():
    """Rebuild every legacy venue dataset, in dependency order."""
    rebuild_nearby_scan_20260629()            # scan files -> merged scan JSON
    build_nearby_scan_20260629_operational()  # merged scan -> scan table, OPERATIONAL only
    build_places_details_20260704_table()     # Details JSONs -> Details table
    build_venues_20260629_pre_expansion()     # Details + scan tables -> pre-expansion venue table
    build_venues_20260925_expanded()          # + repair/outer runs -> expanded venue table


# ---------------------------------------------------------------------------
# Steps, in the order rebuild_legacy_datasets() runs them
# ---------------------------------------------------------------------------

def rebuild_nearby_scan_20260629():
    """Merge the 2026-06-29 Legacy Nearby scan into one file, keeping the first result per place_id.

    Inputs:  the scan files in config.NEARBY_SCAN_20260629_DIR, then those in
             config.NEARBY_SCAN_20260629_UPDATE_DIR; each is {"results": [Places result dict, ...]}.
    Output:  config.NEARBY_SCAN_20260629_MERGED_PATH,
             {"collection_timestamp": "2026-06-29", "results": [Places result dict, ...]}.
    Replaces hex_search.truncate (git tag legacy-final).
    """
    scan_file_paths = (_list_scan_files(config.NEARBY_SCAN_20260629_DIR)
                       + _list_scan_files(config.NEARBY_SCAN_20260629_UPDATE_DIR))
    merged_scan = {
        "collection_timestamp": config.NEARBY_SCAN_20260629_COLLECTION_DATE,
        "results": _merge_first_per_place_id(scan_file_paths),  # list of Places result dicts
    }
    config.NEARBY_SCAN_REBUILD_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.NEARBY_SCAN_20260629_MERGED_PATH, "w", encoding="utf-8") as merged_file:
        json.dump(merged_scan, merged_file, indent=2, ensure_ascii=False)
    print(f"{config.NEARBY_SCAN_20260629_MERGED_PATH.name}: {len(merged_scan['results']):,} venues")


def build_nearby_scan_20260629_operational():
    """Flatten the merged scan into a table of OPERATIONAL venues.

    Input:  config.NEARBY_SCAN_20260629_MERGED_PATH, {"results": [Places (Legacy) result dict, ...]}.
    Output: config.NEARBY_SCAN_20260629_OPERATIONAL_PATH, one row per venue: place_id, name, lat,
            lng, rating, user_ratings_total, price_level, international_phone_number.
    Replaces compiler.legacy_place_api_to_csv.
    """
    merged_scan = json.loads(config.NEARBY_SCAN_20260629_MERGED_PATH.read_text(encoding="utf-8"))
    scan_df = pd.DataFrame([_scan_result_to_row(result) for result in merged_scan["results"]])
    is_operational = scan_df["business_status"] == OPERATIONAL_STATUS
    operational_df = scan_df[is_operational].drop(columns=["business_status"])
    _write_table(operational_df, config.NEARBY_SCAN_20260629_OPERATIONAL_PATH)


def build_places_details_20260704_table():
    """Flatten the 2026-07-04 Places Details files into a table.

    Input:  config.PLACES_DETAILS_20260704_DIR, one Places (New) Details JSON per venue.
    Output: config.PLACES_DETAILS_20260704_TABLE_PATH, one row per file: place_id,
            types ("|"-joined), formattedAddress.
    Replaces compiler.new_place_api_to_csv.
    """
    # Case-insensitive name order: the order Windows listed them in, so rows match the legacy file.
    details_file_paths = sorted(config.PLACES_DETAILS_20260704_DIR.glob(DETAILS_FILE_PATTERN),
                                key=lambda details_path: details_path.name.upper())
    details_rows = [_details_to_row(json.loads(details_path.read_text(encoding="utf-8")))
                    for details_path in details_file_paths]
    _write_table(pd.DataFrame(details_rows), config.PLACES_DETAILS_20260704_TABLE_PATH)


def build_venues_20260629_pre_expansion():
    """Join each Details row to its scan row; drop the hand-confirmed duplicates.

    Inputs: config.PLACES_DETAILS_20260704_TABLE_PATH (left side: one row per Details file) and
            config.NEARBY_SCAN_20260629_OPERATIONAL_PATH.
    Output: config.VENUES_20260629_PRE_EXPANSION_PATH: Details columns, then the scan columns.
    Replaces compiler.merge_place_api_to_csv.
    """
    details_df = pd.read_csv(config.PLACES_DETAILS_20260704_TABLE_PATH)
    scan_df = pd.read_csv(config.NEARBY_SCAN_20260629_OPERATIONAL_PATH)
    venues_df = details_df.merge(scan_df, on="place_id", how="left")
    _write_table(_drop_manual_duplicates(venues_df), config.VENUES_20260629_PRE_EXPANSION_PATH)


def build_venues_20260925_expanded():
    """Add the repair/outer-run venues and let them replace the old scan beyond the sound disc.

    Inputs: config.NEARBY_REPAIR_20260925_PATH, config.VENUES_20260629_PRE_EXPANSION_PATH and the
            legacy scan centre (config.LEGACY_SCAN_CENTRE_COORD_PATH; fixed, not the chosen subject).
    Output: config.VENUES_20260925_EXPANDED_PATH, one row per place_id:
            - repair/outer venues at or beyond config.SOUND_DISC_RADIUS_M (newest record wins);
            - pre-expansion venues (run_id "old_legacy") inside it.
    Replaces compiler.merge_expansion_fix_to_csv.
    """
    scan_centre_lat, scan_centre_lng = read_subject_location(config.LEGACY_SCAN_CENTRE_COORD_PATH)

    repair_df = _load_repair_venues()  # OPERATIONAL results, newest record per place_id
    repair_distance_m = haversine_m(scan_centre_lat, scan_centre_lng, repair_df["lat"].values, repair_df["lng"].values)
    repair_df = repair_df[repair_distance_m >= config.SOUND_DISC_RADIUS_M]

    pre_expansion_df = pd.read_csv(config.VENUES_20260629_PRE_EXPANSION_PATH)
    pre_expansion_df["ts"] = np.nan
    pre_expansion_df["run_id"] = LEGACY_SCAN_RUN_ID

    venues_df = _keep_newest_per_place_id(pd.concat([repair_df, pre_expansion_df]))
    venues_df = _drop_manual_duplicates(venues_df)

    # Beyond the sound disc, the repair/outer runs replace the old scan's venues.
    venue_distance_m = haversine_m(scan_centre_lat, scan_centre_lng, venues_df["lat"].values, venues_df["lng"].values)
    is_replaced_old_venue = (venues_df["run_id"] == LEGACY_SCAN_RUN_ID) & (venue_distance_m >= config.SOUND_DISC_RADIUS_M)
    _write_table(venues_df[~is_replaced_old_venue], config.VENUES_20260925_EXPANDED_PATH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_scan_files(scan_dir):
    """Return the scan files directly inside scan_dir, sorted by file name.

    Order matters: when a place_id appears in several files, the first file read wins. Name order
    (output_100, output_200, output_400, output_50, output_800) is the order the legacy merge read
    them in, so sorting by name reproduces the legacy file exactly.
    """
    return sorted(scan_dir.glob(SCAN_FILE_PATTERN))


def _merge_first_per_place_id(scan_file_paths):
    """Concatenate the results of every scan file in order, skipping place_ids already seen.

    Input:  list of Paths to scan files, each {"results": [Places result dict, ...]}.
    Output: list of Places result dicts, one per place_id, in first-seen order.
    """
    merged_results = []
    seen_place_ids = set()
    for scan_file_path in scan_file_paths:
        scan = json.loads(scan_file_path.read_text(encoding="utf-8"))  # dict: {"results": [...]}
        for result in scan["results"]:
            if result["place_id"] not in seen_place_ids:
                merged_results.append(result)
                seen_place_ids.add(result["place_id"])
    return merged_results


def _scan_result_to_row(result):
    """Return one flat row dict from a Places (Legacy) result dict.

    A venue with no rating gets rating None and user_ratings_total 0, as in the legacy code.
    """
    is_rated = "rating" in result
    location = result["geometry"]["location"]  # dict: {"lat": float, "lng": float}
    return {
        "place_id": result["place_id"],
        "name": result["name"],
        "business_status": result["business_status"],
        "lat": location["lat"],
        "lng": location["lng"],
        "rating": result["rating"] if is_rated else None,
        "user_ratings_total": result["user_ratings_total"] if is_rated else 0,
        "price_level": result.get("price_level"),
        "international_phone_number": result.get("international_phone_number"),
    }


def _details_to_row(details):
    """Return one flat row dict from a Places (New) Details dict."""
    return {
        "place_id": details.get("id"),
        "types": TYPE_SEPARATOR.join(details.get("types", [])),
        "formattedAddress": details.get("formattedAddress"),
    }


def _load_repair_venues():
    """Return the OPERATIONAL venues of the repair/outer runs, newest record per place_id.

    Input:  config.NEARBY_REPAIR_20260925_PATH, one JSON record per request:
            {"run_id": str, "ts": str, "results": [Places (Legacy) result dict, ...], ...}.
    Output: DataFrame with run_id, place_id, types, name, lat, lng, rating, user_ratings_total,
            price_level, international_phone_number, ts, formattedAddress (empty: the Legacy
            API has no formatted address).
    """
    repair_rows = []
    with open(config.NEARBY_REPAIR_20260925_PATH, encoding="utf-8") as repair_file:
        for line in repair_file:
            if not line.strip():
                continue
            request_record = json.loads(line)
            for result in request_record["results"]:
                if result.get("business_status") == OPERATIONAL_STATUS:
                    repair_rows.append(_repair_result_to_row(result, request_record["run_id"], request_record["ts"]))
    repair_df = _keep_newest_per_place_id(pd.DataFrame(repair_rows))
    repair_df["formattedAddress"] = np.nan
    return repair_df


def _repair_result_to_row(result, run_id, request_ts):
    """Return one flat row dict from a repair/outer-run result; missing fields as in the legacy code."""
    location = result["geometry"]["location"]  # dict: {"lat": float, "lng": float}
    return {
        "run_id": run_id,
        "place_id": result["place_id"],
        "types": TYPE_SEPARATOR.join(result["types"]),
        "name": result["name"],
        "lat": location["lat"],
        "lng": location["lng"],
        "rating": result.get("rating", np.nan),
        "user_ratings_total": result.get("user_ratings_total", 0),
        "price_level": result.get("price_level", np.nan),
        "international_phone_number": result.get("international_phone_number", np.nan),
        "ts": request_ts,
    }


def _keep_newest_per_place_id(venues_df):
    """Return one row per place_id: the one with the latest ts (rows without ts sort last)."""
    newest_first_df = venues_df.sort_values(by=["ts"], ascending=False, kind="stable")
    return newest_first_df.drop_duplicates("place_id", keep="first")


def _drop_manual_duplicates(venues_df):
    """Drop the hand-confirmed duplicate venues (config.MANUAL_DUPLICATE_PLACE_IDS)."""
    return venues_df[~venues_df["place_id"].isin(config.MANUAL_DUPLICATE_PLACE_IDS)]


def _write_table(table_df, output_path):
    """Write table_df to output_path as CSV (creating its folder) and print its row count."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table_df.to_csv(output_path, index=False)
    print(f"{output_path.name}: {len(table_df):,} rows")
