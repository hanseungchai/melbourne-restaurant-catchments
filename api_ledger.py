"""Append-only ledger of Google Places API requests, with a budget guard.

One line per HTTP request. Each results page is its own request, so each page gets a line.
A request is counted when it is SENT, whether or not it succeeds. That is conservative:
it can overcount a failed call but never undercount a billed one.

Usage (inside the request function, immediately before the HTTP call):

    req_id = ledger.record_send("legacy_nearby", endpoint="nearbysearch",
                                run_id=RUN_ID, meta={"lat": lat, "lng": lng, "radius": r})
    resp = requests.get(...)
    ledger.record_result(req_id, status=status, n_results=len(results))

Assumes a single writing process. Threads are fine because of the lock; separate
processes are not, since the in-memory counts would diverge.
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config

BILLING_TZ = ZoneInfo(config.API_BILLING_TIMEZONE)
# Budget constants (allowance, seeds, paid extensions, margin) live in config.py's API BUDGET GUARD block.


class BudgetExceeded(RuntimeError):
    pass


_lock = threading.RLock()   # re-entrant: record_send holds it while check() -> used() takes it again
_counts = None   # {(month, sku): n_sent}, built lazily from the file


def billing_month(ts=None):
    ts = ts or datetime.now(timezone.utc)
    return ts.astimezone(BILLING_TZ).strftime("%Y-%m")


def _load_counts():
    global _counts
    _counts = {}
    if config.API_LEDGER_PATH.exists():
        with config.API_LEDGER_PATH.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                if r["kind"] == "sent":
                    key = (r["month"], r["sku"])
                    _counts[key] = _counts.get(key, 0) + 1


def _append(rec):
    config.API_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with config.API_LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()


def used(sku, month=None):
    """Calls sent this billing month, including the pre-ledger seed."""
    month = month or billing_month()
    with _lock:
        if _counts is None:
            _load_counts()
        return config.API_SEED_USED.get((month, sku), 0) + _counts.get((month, sku), 0)


def remaining(sku, month=None):
    """Calls left this month (free plus any approved paid extension) before the margin. None if uncapped."""
    cap = config.API_FREE_ALLOWANCE[sku]
    if cap is None:
        return None
    month = month or billing_month()
    return cap + config.API_PAID_EXTENSION.get((month, sku), 0) - config.API_MARGIN - used(sku, month)


def check(sku, n=1):
    """Raise unless n more calls fit inside the allowance. Use before a batch run."""
    if sku not in config.API_FREE_ALLOWANCE:
        raise KeyError(f"Unknown SKU {sku!r}; add it to config.API_FREE_ALLOWANCE first.")
    if config.API_FREE_ALLOWANCE[sku] is None:
        return
    month = billing_month()
    if (month, sku) not in config.API_SEED_USED:
        raise BudgetExceeded(
            f"No config.API_SEED_USED entry for ({month!r}, {sku!r}). "
            "Read this month's usage from Billing -> Reports and add it.")
    left = remaining(sku, month)
    if n > left:
        raise BudgetExceeded(f"{sku}: {n} calls requested, {left} left in {month} "
                             f"(allowance {config.API_FREE_ALLOWANCE[sku]}, paid extension {config.API_PAID_EXTENSION.get((month, sku), 0)}, "
                             f"margin {config.API_MARGIN}).")


def record_send(sku, endpoint, run_id, meta=None):
    """Guard, then log one request as sent. Call immediately before the HTTP request."""
    ts = datetime.now(timezone.utc)
    req_id = uuid.uuid4().hex
    rec = {
        "kind": "sent", "req_id": req_id, "ts_utc": ts.isoformat(),
        "month": billing_month(ts), "sku": sku, "endpoint": endpoint,
        "run_id": run_id, "meta": meta or {},
    }
    # Check and increment under one lock, so two threads can't both take the last call.
    with _lock:
        check(sku, 1)
        if _counts is None:
            _load_counts()
        _append(rec)
        key = (rec["month"], sku)
        _counts[key] = _counts.get(key, 0) + 1
    return req_id


def record_result(req_id, status, n_results=None):
    """Log the outcome of a sent request. Not counted towards usage."""
    rec = {"kind": "result", "req_id": req_id,
           "ts_utc": datetime.now(timezone.utc).isoformat(),
           "status": status, "n_results": n_results}
    with _lock:
        _append(rec)


def summary(month=None):
    """Usage and remaining allowance per SKU for a billing month."""
    month = month or billing_month()
    return {sku: {"used": used(sku, month), "allowance": cap,
                  "remaining": remaining(sku, month)}
            for sku, cap in config.API_FREE_ALLOWANCE.items()}