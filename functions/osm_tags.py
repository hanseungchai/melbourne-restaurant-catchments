"""Parsers for OpenStreetMap tag values."""

import config

KMH_UNIT_SUFFIXES = ("km/h", "kmh")   # accepted after the number, with or without a space


# evidence: diagnostics/drive_speed_limits.py (unit-suffixed values occur; none fail this rule)
def parse_maxspeed(raw):
    """Return a maxspeed tag as an int in km/h, or None if it can't be read as one.

    Accepts a bare integer ("60") or one with a km/h unit ("60kmh", "50 km/h"). Anything else
    (mph, "none", "signals", out of range) returns None so the caller falls back to a class default.
    """
    if raw is None:
        return None
    text = str(raw).strip().lower()
    for suffix in KMH_UNIT_SUFFIXES:
        if text.endswith(suffix):
            text = text[:-len(suffix)].strip()
            break
    try:
        value = int(text)
    except ValueError:
        return None
    return value if config.MIN_VALID_SPEED_LIMIT_KMH <= value <= config.MAX_VALID_SPEED_LIMIT_KMH else None
