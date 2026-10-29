"""Band-3 transit targeting (RCH-27, RCH-20 (2)): which minutes to read and from which points to route.

Hybrid windows: the whole-read day types' windows in the subject pass's chunks (each 30-min slot its own field); every
other span of the subject's hours is read by one random-start window, whose field stands for every slot of the span.

Flower origins: aperture-7 flowers on the axial hex grid (q, r). v = (q + 3r) mod 7 colours a hex and its six
neighbours distinctly; flower centres have v == 0, and TO_CENTRE steps every other colour to its centre. Per stage band
b with threshold T_b: a populated hex with persons >= T_b is its own point; its flower's populated members below T_b form
one group, routed from their persons-weighted centroid. Identical groups of two bands share one point.
"""
import datetime

import numpy as np
import pandas as pd

TO_CENTRE = {1: (-1, 0), 6: (1, 0), 3: (0, -1), 4: (0, 1), 5: (-1, 1), 2: (1, -1)}   # v -> step to the centre
FLOWER_COLOURS = 7
FLOWER_Q_SPAN = 100_000                   # flower key = centre q x this + centre r (|r| far below it)
CLOCK_FORMAT = "%H:%M"
SECONDS_PER_MIN = 60
POINT_COLUMNS = ["point_id", "centroid_lat", "centroid_lon", "persons", "n_members", "max_band"]
MEMBER_COLUMNS = ["hex_id", "band", "point_id"]


def flower_keys(q, r):
    """Each hex's flower: its centre's (q, r) as one integer key."""
    q, r = np.asarray(q, np.int64), np.asarray(r, np.int64)
    colour = (q + 3 * r) % FLOWER_COLOURS
    centre_q, centre_r = q.copy(), r.copy()
    for value, (step_q, step_r) in TO_CENTRE.items():
        is_value = colour == value
        centre_q[is_value] += step_q
        centre_r[is_value] += step_r
    assert ((centre_q + 3 * centre_r) % FLOWER_COLOURS == 0).all(), "a flower centre off colour 0"
    return centre_q * FLOWER_Q_SPAN + centre_r


def merged_points(origins_df, thresholds):
    """Points to route and each hex's point per stage band. origins_df: hex_id, q, r, centroid_lat, centroid_lon,
    persons (populated hexes only). thresholds: {band: T}. Own points keep the hex id; groups get negative ids, one
    per distinct member set. Returns (points_df: POINT_COLUMNS, max_band = the outermost band using the point;
    members_df: MEMBER_COLUMNS)."""
    origins_df = origins_df.assign(flower=flower_keys(origins_df.q, origins_df.r)).sort_values("hex_id")
    points, members, group_ids = {}, [], {}
    for band, threshold in sorted(thresholds.items()):
        is_own = origins_df.persons >= threshold
        for row in origins_df[is_own].itertuples():
            points.setdefault(row.hex_id, [row.hex_id, row.centroid_lat, row.centroid_lon, row.persons, 1, band])
            points[row.hex_id][-1] = max(points[row.hex_id][-1], band)
            members.append((row.hex_id, band, row.hex_id))
        for _, group in origins_df[~is_own].groupby("flower", sort=True):
            member_ids = tuple(group.hex_id)
            if member_ids not in group_ids:
                group_ids[member_ids] = -(len(group_ids) + 1)
                weights = group.persons.to_numpy()
                points[group_ids[member_ids]] = [group_ids[member_ids],
                                                 float(np.average(group.centroid_lat, weights=weights)),
                                                 float(np.average(group.centroid_lon, weights=weights)),
                                                 float(weights.sum()), len(member_ids), band]
            point_id = group_ids[member_ids]
            points[point_id][-1] = max(points[point_id][-1], band)
            members += [(hex_id, band, point_id) for hex_id in member_ids]
    points_df = pd.DataFrame(list(points.values()), columns=POINT_COLUMNS).sort_values("point_id", ignore_index=True)
    members_df = pd.DataFrame(members, columns=MEMBER_COLUMNS)
    return points_df, members_df


def clock_datetime(day, clock):
    return datetime.datetime.combine(day, datetime.datetime.strptime(clock, CLOCK_FORMAT).time())


def slot_label(day_type, moment):
    return f"{day_type}_{moment:%H%M}"


def hybrid_windows(subject_windows, whole_day_types, span_breaks, window_min, chunk_max_min, slot_min, seed):
    """Windows to route and the field each slot reads. Returns (windows: dicts with day_type, start (datetime),
    minutes, span; fields: one dict per slot with slot (label "<day type>_<HHMM>"), window (index into windows),
    first_minute (the field's first minute column in that window) and field (the field's label; a random window's
    slots share one))."""
    windows, fields = [], []
    rng_span = 0
    for day_type, (day, day_windows) in subject_windows.items():
        for first, last in day_windows:
            start, end = clock_datetime(day, first), clock_datetime(day, last)
            breaks = [clock_datetime(day, clock) for clock in span_breaks.get(day_type, []) if start
                      < clock_datetime(day, clock) < end]
            for span_start, span_end in zip([start, *breaks], [*breaks, end]):
                span_min = int((span_end - span_start).total_seconds()) // SECONDS_PER_MIN
                assert span_min % slot_min == 0, f"{day_type} span {span_start:%H:%M} not whole slots"
                span = f"{day_type}_{span_start:%H%M}-{span_end:%H%M}"
                slots = [span_start + datetime.timedelta(minutes=offset) for offset in range(0, span_min, slot_min)]
                if day_type in whole_day_types:
                    offset = 0
                    while offset < span_min:
                        minutes = min(chunk_max_min, span_min - offset)
                        windows.append({"day_type": day_type, "start": span_start + datetime.timedelta(minutes=offset),
                                        "minutes": minutes, "span": span})
                        for first_minute in range(0, minutes, slot_min):
                            moment = windows[-1]["start"] + datetime.timedelta(minutes=first_minute)
                            fields.append({"slot": slot_label(day_type, moment), "window": len(windows) - 1,
                                           "first_minute": first_minute, "field": slot_label(day_type, moment)})
                        offset += minutes
                else:
                    rng = np.random.default_rng([seed, rng_span])
                    start_min = int(rng.integers(0, span_min - window_min + 1))
                    window_start = span_start + datetime.timedelta(minutes=start_min)
                    windows.append({"day_type": day_type, "start": window_start, "minutes": window_min, "span": span})
                    label = f"{day_type}_{window_start:%H%M}w"
                    fields += [{"slot": slot_label(day_type, moment), "window": len(windows) - 1, "first_minute": 0,
                                "field": label} for moment in slots]
                rng_span += 1
    return windows, pd.DataFrame(fields)


def covering_chunks(window, chunks):
    """The subject pass's chunks (day type, date, start, minutes) holding the window's minutes, each with the window's
    first minute column in it and the number of minutes it holds: [(chunk index, first column, minutes)]; None if a
    minute of the window lies in no chunk."""
    out, moment, left = [], window["start"], window["minutes"]
    while left > 0:
        for index, (day_type, _, start, minutes) in enumerate(chunks):
            end = start + datetime.timedelta(minutes=minutes)
            if day_type == window["day_type"] and start <= moment < end:
                held = min(left, int((end - moment).total_seconds()) // SECONDS_PER_MIN)
                out.append((index, int((moment - start).total_seconds()) // SECONDS_PER_MIN, held))
                moment += datetime.timedelta(minutes=held)
                left -= held
                break
        else:
            return None
    return out
