"""Transit reach by whole departure windows (RCH-20, RCH-21; TRN-16 P8r, draws mode): every minute of a window read
as its own departure, from each origin hex to every venue hex, in one R5 call per origin.

The frozen model's times (TRN-16, P1-P3) through the P8r draws jar: with the JVM property `platica.report` set to
"draws:0,1,...,W-1", R5 reports the travel time of every iteration of a W-minute window instead of percentiles
(iteration i is minute W - 1 - i: range RAPTOR runs backwards; the column order is reversed here so column m is
minute m). The jar lifts R5's 5-percentile cap while a report is set; r5py's own assertion is lifted at run time
(lift_r5py_percentile_cap). r5py's TravelTimeMatrix is not used: it keeps every origin x destination x minute as
floats before anything is dropped (~58 GB for ~9k origins at 90 minutes); here each origin's result arrays are read
from R5 directly and only destinations reached in some minute are kept.
evidence: diagnostics/transit_r5_patch_reach.py (B1, B2, T0-T4)
"""
import copy
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPORT_PROPERTY = "platica.report"
DRAWS_MODE = "draws"
R5_UNREACHED = 2_147_483_647              # R5's NULL (MAX_INT32)
STORED_UNREACHED = np.iinfo(np.uint16).max
SELF_PAIR_S = 0                           # r5py's convention: a hex reaches itself at 0 s
GUARD_CLASSES = ["com.conveyal.r5.analyst.TravelTimeReducer", "com.conveyal.r5.analyst.cluster.AnalysisWorkerTask",
                 "com.conveyal.r5.profile.FastRaptorWorker"]
ORIGIN_COL, DEST_COL = "origin_hex", "dest_hex"
MINUTE_COL = "m{:02d}"                    # column per window minute: travel seconds (STORED_UNREACHED = not reached)


def file_sha256(path):
    with open(path, "rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def start_jvm(jar_path, jar_sha256, max_memory):
    """Start r5py's JVM on the given jar (hash checked), check the patched classes load from it; returns jpype."""
    assert file_sha256(jar_path) == jar_sha256, f"{jar_path.name}: sha256 differs from config"
    sys.argv += ["--max-memory", max_memory, "--r5-classpath", str(jar_path)]   # r5py reads these at import
    import jpype
    import r5py  # noqa: F401  (starts the JVM)
    for name in GUARD_CLASSES:
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == Path(jar_path).resolve(), f"{name} from {location}"
    lift_r5py_percentile_cap()
    return jpype


def lift_r5py_percentile_cap():
    """Replace r5py's `RegionalTask.percentiles` setter with one without its `len <= 5` assertion."""
    from r5py.r5.regional_task import RegionalTask

    def set_percentiles(self, percentiles):
        self._percentiles = percentiles
        self._regional_task.percentiles = percentiles

    RegionalTask.percentiles = RegionalTask.percentiles.setter(set_percentiles)


def draws_task(network, destinations_gdf, departure, window_min, max_time_min, walk_speed_kmh):
    """An r5py RegionalTask for one window: placeholder percentiles 1..W, transit + walk, the frozen walk speed."""
    from r5py import RegionalTask, TransportMode
    return RegionalTask(network, origin=None, destinations=destinations_gdf, departure=departure,
                        departure_time_window=datetime.timedelta(minutes=window_min),
                        percentiles=list(range(1, window_min + 1)),
                        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
                        max_time=datetime.timedelta(minutes=max_time_min), speed_walking=walk_speed_kmh)


def set_report(jpype, window_min):
    jpype.JClass("java.lang.System").setProperty(REPORT_PROPERTY,
                                                 f"{DRAWS_MODE}:" + ",".join(map(str, range(window_min))))


def clear_report(jpype):
    jpype.JClass("java.lang.System").setProperty(REPORT_PROPERTY, "")


def origin_minutes(network, task, origin_point, window_min):
    """One origin: (W x destinations) int array of travel seconds, column order = R5's iterations (reversed)."""
    import com.conveyal.r5
    request = copy.copy(task)
    request.origin = origin_point
    results = com.conveyal.r5.analyst.TravelTimeComputer(request, network).computeTravelTimes()
    values = results.travelTimes.getValues()
    assert len(values) == window_min, f"R5 returned {len(values)} rows for a {window_min}-min window"
    return np.stack([np.asarray(values[k]) for k in range(window_min)])


def origin_rows(minutes_by_iteration, origin_hex, dest_hexes):
    """The reached destinations of one origin as a frame: origin, destination, one uint16 column per minute (minute
    m = iteration W - 1 - m). Self pairs set to SELF_PAIR_S."""
    by_minute = minutes_by_iteration[::-1].T                      # destinations x minutes, minute order
    is_self = dest_hexes == origin_hex
    by_minute[is_self] = SELF_PAIR_S
    is_reached = (by_minute != R5_UNREACHED).any(axis=1)
    kept = by_minute[is_reached]
    assert kept[kept != R5_UNREACHED].max(initial=0) < STORED_UNREACHED, "travel time past uint16"
    kept = np.where(kept == R5_UNREACHED, STORED_UNREACHED, kept).astype(np.uint16)
    frame = pd.DataFrame(kept, columns=[MINUTE_COL.format(m) for m in range(kept.shape[1])])
    frame.insert(0, DEST_COL, dest_hexes[is_reached].astype(np.int32))
    frame.insert(0, ORIGIN_COL, np.int32(origin_hex))
    return frame
