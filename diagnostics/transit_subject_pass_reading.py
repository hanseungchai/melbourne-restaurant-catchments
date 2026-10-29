"""Transit subject pass reading: what the subject's exact pass says about hybrid targeting, time and shape.

Claims (where the pipeline relies on them):
  (1) Hybrid targeting (RCH-20 (2), DESIGN Q25) is the standing scheme for repeated transit passes: the heavy-weight
      span (Mon-Thu evening) read whole, one random-start 30-min P8r window per other span, a span flagged by the
      GTFS trip-count step read whole. Its error (~1-2%, <= 2.9% upper) was estimated on the 80th's dense reference
      (8 venues, 6 departures per slot, 500 origins each, ad hoc scripts). The subject's pass (RCH-21, 85th) reads
      every minute of every open window over the whole envelope, so the scheme's error on the subject is exact here.
  (2) One 30-min window has no internal check (RCH-20 limits); the trip-count flag and the within-window trend are
      meant to catch the silent failure. Read here: the within-window trend and per-minute spread, and whether the
      trip-count flag marks the spans where reach changes.
  (3) The user's prediction (85th, from the handoff, not recorded verbatim): the subject's catchment runs along its
      tram corridor (Lygon St). Read here as corridor vs across shape.

Method (free: reads the saved pass, no JVM, no API):
  Pass: outputs/reachability/<subject>/transit_86cb259c15/ (16 chunks of <= 90 min, P8r draws: travel seconds per
    origin, destination and departure minute; envelope origins only). Subject = dest_hex 0 (the subject's venue hex).
  Bands (SCR-10: seconds rounded to whole minutes, then cut): band 2 = <= 20 min (<= 1,229 s), the band the 81st's
    figures used; 30 min (<= 1,829 s, RCH-19's cap) reported beside it.
  Readings per departure minute t: persons P(t) = sum of persons_h (residents + workers) over origins h reaching the
    subject within the band; flat share F(t) = sum persons_h / K_h(t), K_h(t) = venues (not hexes) h reaches within
    the band at t (as transit_departure_sampling.py, SCR-3's N -> infinity limit, a share proxy; Claude's).
  Week headline: minute-weighted mean over day types, each minute weighted by its day type's days (Mon-Thu 4, Fri /
    Sat / Sun 1), as the 81st's scripts (H = sum_d w_d sum_t x_t / sum_d w_d M_d).
  Spans (the 81st's, transit_departure_sampling.span_of on the subject's hours): Mon-Thu evening, Fri evening,
    Sat / Sun lunch (before 16:00), Sat dinner (17:00-20:30), Sat late (20:30-21:30), Sun dinner.
  Scheme errors (exact: every minute is read, no departure noise): a scheme replaces a span's mean by an estimate;
    week relative RMS error = sqrt(sum_s c_s^2 MSE_s) / H, c_s = w_d n_s / W (n_s span minutes, W = sum_d w_d M_d),
    draws independent across spans. MSE_s of one 30-min window = mean over every minute start that fits in the span
    of (window mean - span mean)^2 ("random start"); "aligned" = starts on 30-min slot edges only (the 81st's
    definition). Schemes: hybrid (Mon-Thu whole, one window per other span); hybrid + flag (flagged spans whole);
    one window per span (Mon-Thu too); one random single departure per 30-min slot (42 a week, the Q25 plan; MSE per
    slot = the slot's minute variance).
  Trend (claim 2): per open window (day type x opening): change from first to last third, OLS slope (% of the window
    mean per hour), per-minute CV, lag-1 autocorrelation of the minute series.
  Trip-count flag (RCH-20 (2)): stops of the three feeds within STOP_RADIUS_M of an envelope hex centroid (union of
    the day type's chunk envelopes); stop events (departures in stop_times) per 30-min slot on the day type's date,
    services from calendar + calendar_dates. Step = largest |adjacent slot ratio - 1| within a span.
  Corridor (claim 3): tram routes with a stop within CORRIDOR_STOP_RADIUS_M of the subject; corridor = hexes within
    CORRIDOR_BUFFER_M of those routes' shapes. Reach weight per origin = persons x week-weighted share of open minutes
    within the band. Measures: corridor share of the reach weight vs the same share for all populated hexes within
    the reach's 90th-percentile distance (disc baseline: what a shapeless catchment of that size would hold);
    principal axis of the reach weight (axis ratio, bearing) vs the corridor shapes' axis within the same radius.

Reading rules (written before any results; Claude's, confirmed by the user after the run, 2026-10-23, 86th; report only):
  (1) Hybrid holds on the subject if its week relative RMS error (random start) is <= 2.9% (the 81st's upper bound)
      for band-2 persons and flat share.
  (2) Trend: a window "drifts" if |first-to-last-third change| > 10%. The trip-count flag "fires" on a span if its
      stop-event step > TRIP_STEP_FLAG (20%). The flag "tracks reach" if every span whose band-2 persons slot means
      step by > 10% is flagged; spans flagged without a reach step are reported as false alarms.
  (3) Corridor shape holds if the corridor share of the reach weight is >= 1.5x the disc baseline and the principal
      axis is within 20 degrees of the corridor axis (band 2 and 30 min reported, band 2 decides).

Conclusion (run 2026-10-23, 86th; facts; whole envelope, every open minute; week headline band 2: 66.9k persons,
  30 min: 234.7k):
  (1) Rule HOLDS. Hybrid (~23 singles) band 2: 0.71% persons / 0.72% flat share (aligned starts 0.68 / 0.78); 30 min
  1.92 / 1.36%. One window per span (16) 1.85 / 1.59% (30 min 4.67 / 3.03%); one single per slot (42) 2.86 / 3.14%
  (30 min 3.65 / 3.85%; the 80th's dense estimate for the subject was 3.7 / 4.2%, other origins and definition); the
  pass itself ~58 singles. One random 30-min window misses its span mean by 1-3.7% RMS (band 2; worst start 2-10.5%);
  Sat lunch steadiest (~1%).
  (2) No window drifts at band 2 (first-to-last third -0.5 to +2.8%; per-minute CV 12-17%, lag-1 autocorrelation
  0.26-0.54). At 30 min reach rises through the evening (+15 to +22% on Mon-Thu, Fri, Sat and Sun evenings; Mon-Thu
  slot means 211k at 17:30 to 271k at 20:00) with origins within 30 min near flat (3.9-4.6k): heavier hexes come into
  reach later (unexplained here). Stop events near the envelope fall through every evening (Mon-Thu 7.6k to 4.1k
  per slot) and the flag (step > 20%) fires on no span; no span's band-2 slot means step > 10% (largest 8.1% Fri), so
  the flag "tracks reach" vacuously: nothing to catch on the subject, no test of its power. Steps per slot are
  smooth declines (max 14.5%), not steps.
  (3) Corridor shape HOLDS (routes 1 and 6): band 2 67% of reach weight within 500 m of the routes vs 28% for a
  shapeless disc of the same size (2.4x), axis ratio 2.1, bearing 4 deg vs corridor 6 deg; 30 min 53% vs 23% (2.3x),
  ratio 2.0, gap 1.7 deg.

Inputs (read only): the pass folder, the hex nodes table, venues with hex, the 20261016 GTFS network zips the pass
used. Self-contained (CLAUDE.md D1). No API calls.
Usage: `python transit_subject_pass_reading.py` (computes the per-minute tables once, then reuses them).
"""
import datetime
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "-37.76870_144.97196"
SUBJECT_LAT, SUBJECT_LON = -37.7687014, 144.9719611
FILE_TAG = f"res2021_wrk2021_ven20260925_{SUBJECT}"
NAME = "transit_subject_pass_reading"
PASS_DIR = PROJECT_ROOT / "outputs" / "reachability" / SUBJECT / "transit_86cb259c15"
HEX_NODES_PATH = PROJECT_ROOT / "outputs" / "routing_graph" / SUBJECT / f"hex_population_and_nodes_{FILE_TAG}.gpkg"
VENUES_WITH_HEX_PATH = PROJECT_ROOT / "outputs" / "hex_grid" / SUBJECT / f"venues_with_hex_ven20260925_{SUBJECT}.csv"
NETWORK_DIR = PROJECT_ROOT / "outputs" / "reachability" / "network" / "20261016"
FEED_PATHS = {"train": NETWORK_DIR / "ptv_metro_train_reach_20261016_moved.zip",
              "tram": NETWORK_DIR / "ptv_tram_reach_20261016.zip",
              "bus": NETWORK_DIR / "ptv_metro_bus_reach_20261016.zip"}
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"

# --- pass ------------------------------------------------------------------------------------------
SUBJECT_HEX = 0
DEST_COL, ORIGIN_COL = "dest_hex", "origin_hex"
BAND_CUTS_S = {"b20": 1229, "b30": 1829}         # SCR-10: rounded minutes <= 20 / <= 30
DECIDING_BAND = "b20"
DAY_DATES = {"Mon-Thu": datetime.date(2026, 10, 28), "Fri": datetime.date(2026, 10, 30),
             "Sat": datetime.date(2026, 10, 31), "Sun": datetime.date(2026, 11, 1)}   # the pass's dates (config)
DAYS_PER_TYPE = {"Mon-Thu": 4, "Fri": 1, "Sat": 1, "Sun": 1}
DAY_ORDER = list(DAYS_PER_TYPE)

# --- schemes ---------------------------------------------------------------------------------------
SLOT_MIN = 30
WINDOW_MIN = 30
HEAVY_SPANS = ["Mon-Thu evening"]
LUNCH_END_MIN = 16 * 60
SAT_LATE_START_MIN = 20 * 60 + 30
COST_PTS = [(1, 1.0), (30, 2.3), (60, 3.6), (120, 5.9), (210, 9.4)]   # P8r timing: window minutes -> singles
UPPER_BOUND_81ST_PCT = 2.9

# --- trend and flag --------------------------------------------------------------------------------
DRIFT_PCT = 10.0
TRIP_STEP_FLAG = 0.20
REACH_STEP = 0.10
STOP_RADIUS_M = 400

# --- corridor --------------------------------------------------------------------------------------
TRAM_MODE = "tram"
TRAM_ROUTE_TYPE = 0
CORRIDOR_STOP_RADIUS_M = 400
CORRIDOR_BUFFER_M = 500
SHAPE_STEP_M = 25                                 # shapes densified to this spacing for the distance search
DISC_QUANTILE = 0.9
CORRIDOR_SHARE_RATIO = 1.5
AXIS_TOLERANCE_DEG = 20.0
EARTH_RADIUS_M = 6_371_000.0


def run_date():
    return datetime.date.today().strftime("%Y%m%d")


def data_path(kind):
    """Saved per-minute and per-origin tables (computed once from the pass, reused; never overwritten)."""
    found = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NAME}_*_{kind}.parquet"))
    return found[-1] if found else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_{kind}.parquet"


def to_metres(lat, lon):
    """Equirectangular metres around the subject (fine at < 30 km)."""
    x = np.radians(np.asarray(lon) - SUBJECT_LON) * EARTH_RADIUS_M * np.cos(np.radians(SUBJECT_LAT))
    y = np.radians(np.asarray(lat) - SUBJECT_LAT) * EARTH_RADIUS_M
    return x, y


def hex_table():
    import pyogrio
    hex_df = pyogrio.read_dataframe(HEX_NODES_PATH, read_geometry=False,
                                    columns=["hex_id", "centroid_lat", "centroid_lon", "residents", "workers"])
    hex_df["persons"] = hex_df.residents.fillna(0) + hex_df.workers.fillna(0)
    hex_df["x"], hex_df["y"] = to_metres(hex_df.centroid_lat, hex_df.centroid_lon)
    return hex_df.set_index("hex_id")


def chunk_dirs():
    return sorted(p for p in PASS_DIR.iterdir() if p.is_dir())


def chunk_clock(chunk_dir):
    """Day type, first minute of the chunk (minutes after midnight), length."""
    day, start, minutes = chunk_dir.name.split("_")
    return day, int(start[:2]) * 60 + int(start[2:]), int(minutes.removesuffix("min"))


# --- compute: per-minute and per-origin tables from the pass --------------------------------------------
def file_readings(path, persons, venue_counts):
    """One times file: per band, per minute persons / flat share / origins reaching the subject, and per origin the
    minutes within and the summed flat-share weight."""
    import pyarrow.parquet as pq
    table = pq.read_table(path)
    origins = table.column(ORIGIN_COL).to_numpy()
    dests = table.column(DEST_COL).to_numpy()
    minute_cols = [c for c in table.column_names if c.startswith("m")]
    times = np.column_stack([table.column(c).to_numpy() for c in minute_cols])
    assert np.all(np.diff(origins) >= 0), f"{path.name}: origins not grouped"
    group_origins, starts = np.unique(origins, return_index=True)
    dest_venues = venue_counts.reindex(dests, fill_value=0).to_numpy(np.float32)
    is_subject = dests == SUBJECT_HEX
    subject_origins = origins[is_subject]
    subject_group = np.searchsorted(group_origins, subject_origins)
    weight = persons.reindex(subject_origins, fill_value=0.0).to_numpy()
    minute_out, origin_out = {}, {}
    for band, cut_s in BAND_CUTS_S.items():
        within = times <= cut_s
        venues_k = np.add.reduceat(within * dest_venues[:, None], starts, axis=0)      # origins x minutes
        subject_within = within[is_subject]
        k_subject = venues_k[subject_group]
        assert np.all(k_subject[subject_within] >= 1), "subject reached but K = 0"
        flat = np.where(subject_within, weight[:, None] / np.maximum(k_subject, 1), 0.0)
        minute_out[f"persons_{band}"] = (subject_within * weight[:, None]).sum(axis=0)
        minute_out[f"flat_{band}"] = flat.sum(axis=0)
        minute_out[f"origins_{band}"] = subject_within.sum(axis=0)
        origin_out[f"minutes_{band}"] = subject_within.sum(axis=1)
        origin_out[f"flat_{band}"] = flat.sum(axis=1)
    return len(minute_cols), minute_out, pd.DataFrame({ORIGIN_COL: subject_origins, **origin_out})


def compute(hex_df):
    venue_counts = pd.read_csv(VENUES_WITH_HEX_PATH, usecols=["place_id", "hex_id"]).dropna(subset=["hex_id"]) \
        .hex_id.astype(np.int64).value_counts()
    persons = hex_df.persons
    minute_rows, origin_parts = [], []
    for chunk_dir in chunk_dirs():
        day, start_min, length = chunk_clock(chunk_dir)
        totals = None
        for path in sorted(chunk_dir.glob("times_*.parquet")):
            n_minutes, minute_out, origin_df = file_readings(path, persons, venue_counts)
            assert n_minutes == length, f"{path}: {n_minutes} minute columns, chunk says {length}"
            totals = minute_out if totals is None else {k: totals[k] + v for k, v in minute_out.items()}
            origin_parts.append(origin_df.assign(chunk=chunk_dir.name))
        minute_rows.append(pd.DataFrame({"chunk": chunk_dir.name, "day_type": day,
                                         "clock_min": start_min + np.arange(length), **totals}))
        print(f"{chunk_dir.name}: {totals['origins_b30'].mean():,.0f} origins within 30 min per minute", flush=True)
    minutes_df = pd.concat(minute_rows, ignore_index=True)
    origins_df = pd.concat(origin_parts, ignore_index=True)
    minutes_df.to_parquet(data_path("minutes"), index=False)
    origins_df.to_parquet(data_path("origins"), index=False)
    return minutes_df, origins_df


def load_or_compute(hex_df):
    minutes_path, origins_path = data_path("minutes"), data_path("origins")
    if minutes_path.exists() and origins_path.exists():
        print(f"reusing saved tables of {minutes_path.name.split('_')[-2]} ({minutes_path.name}, {origins_path.name})")
        return pd.read_parquet(minutes_path), pd.read_parquet(origins_path)
    print("computing per-minute tables from the pass (no saved tables)")
    return compute(hex_df)


# --- spans and scheme errors ------------------------------------------------------------------------------
def span_of(day, clock_min):
    if day in ("Mon-Thu", "Fri"):
        return f"{day} evening"
    if clock_min < LUNCH_END_MIN:
        return f"{day} lunch"
    if day == "Sat" and clock_min >= SAT_LATE_START_MIN:
        return f"{day} late"
    return f"{day} dinner"


def cost(minutes):
    xs, ys = zip(*COST_PTS)
    if minutes <= xs[-1]:
        return float(np.interp(minutes, xs, ys))
    return ys[-1] + (minutes - xs[-1]) * (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])


def window_mse(values, aligned):
    """MSE of one 30-min window's mean against the span mean, over every start that fits (minute or slot edges)."""
    n = len(values)
    if n <= WINDOW_MIN:
        return 0.0
    step = SLOT_MIN if aligned else 1
    means = np.array([values[s:s + WINDOW_MIN].mean() for s in range(0, n - WINDOW_MIN + 1, step)])
    return float(np.mean((means - values.mean()) ** 2))


def scheme_errors(minutes_df, element, flagged):
    """Week relative RMS error (%) and cost (singles) per scheme for one element, plus per-span detail."""
    week_w = minutes_df.day_type.map(DAYS_PER_TYPE)
    total_w = float(week_w.sum())
    headline = float((week_w * minutes_df[element]).sum() / total_w)
    spans = []
    for (day, span), span_df in minutes_df.sort_values(["day_type", "clock_min"]).groupby(["day_type", "span"],
                                                                                          sort=False):
        values = span_df[element].to_numpy()
        slot_var = span_df.groupby(span_df.clock_min // SLOT_MIN)[element].var(ddof=0)
        coef = DAYS_PER_TYPE[day] * len(values) / total_w
        slot_coef = DAYS_PER_TYPE[day] * SLOT_MIN / total_w
        spans.append(dict(span=span, minutes=len(values), coef=coef, mean=values.mean(),
                          mse_random=window_mse(values, aligned=False), mse_aligned=window_mse(values, aligned=True),
                          single_mse=float((slot_coef ** 2 * slot_var).sum()), slots=len(slot_var),
                          window_err_pct=100 * np.sqrt(window_mse(values, aligned=False)) / values.mean(),
                          worst_start_pct=100 * max(abs(values[s:s + WINDOW_MIN].mean() / values.mean() - 1)
                                                    for s in range(max(len(values) - WINDOW_MIN, 0) + 1))))
    span_df = pd.DataFrame(spans)

    def week(read_whole, kind):
        whole = span_df.span.isin(read_whole) | (span_df.minutes <= WINDOW_MIN)
        mse = float((span_df.coef[~whole] ** 2 * span_df[kind][~whole]).sum())
        spend = sum(cost(m) for m in span_df.minutes[whole]) + cost(WINDOW_MIN) * int((~whole).sum())
        return 100 * np.sqrt(mse) / headline, spend

    rows = {}
    for scheme, read_whole in (("hybrid", HEAVY_SPANS), ("hybrid + flag", HEAVY_SPANS + list(flagged)),
                               ("one window per span", [])):
        err_r, spend = week(read_whole, "mse_random")
        err_a, _ = week(read_whole, "mse_aligned")
        rows[scheme] = dict(err_random_pct=err_r, err_aligned_pct=err_a, cost_singles=spend)
    rows["one single per slot"] = dict(err_random_pct=100 * np.sqrt(span_df.single_mse.sum()) / headline,
                                       err_aligned_pct=np.nan, cost_singles=float(span_df.slots.sum()))
    rows["whole windows (the pass)"] = dict(err_random_pct=0.0, err_aligned_pct=0.0,
                                            cost_singles=sum(cost(m) for m in span_df.minutes))
    return headline, pd.DataFrame(rows).T, span_df


# --- trend ---------------------------------------------------------------------------------------------------
def open_windows(minutes_df):
    """Contiguous open windows per day type (a gap of more than one minute starts a new window)."""
    out = []
    for day, day_df in minutes_df.sort_values("clock_min").groupby("day_type", sort=False):
        breaks = np.flatnonzero(np.diff(day_df.clock_min.to_numpy()) > 1) + 1
        for part in np.split(np.arange(len(day_df)), breaks):
            window_df = day_df.iloc[part]
            first = window_df.clock_min.iloc[0]
            out.append((f"{day} {first // 60:02d}:{first % 60:02d}-{(window_df.clock_min.iloc[-1] + 1) // 60:02d}:"
                        f"{(window_df.clock_min.iloc[-1] + 1) % 60:02d}", window_df))
    return out


def trend_table(minutes_df, element):
    rows = []
    for label, window_df in open_windows(minutes_df):
        values = window_df[element].to_numpy()
        third = len(values) // 3
        hours = np.arange(len(values)) / 60
        slope = np.polyfit(hours, values, 1)[0]
        rows.append(dict(window=label, minutes=len(values), mean=round(values.mean()),
                         first_to_last_third_pct=100 * (values[-third:].mean() / values[:third].mean() - 1),
                         slope_pct_per_h=100 * slope / values.mean(),
                         per_minute_cv_pct=100 * values.std() / values.mean(),
                         lag1_autocorr=float(np.corrcoef(values[:-1], values[1:])[0, 1])))
    return pd.DataFrame(rows)


# --- trip-count flag -------------------------------------------------------------------------------------------
def read_feed_table(archive, name, columns, keep=None):
    """A GTFS table as strings; `keep` = (column, values) filters rows in arrow before pandas (stop_times is large)."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.csv as pacsv
    with archive.open(name) as handle:
        raw = handle.read()
    options = pacsv.ConvertOptions(include_columns=columns, column_types={c: pa.string() for c in columns})
    table = pacsv.read_csv(io.BytesIO(raw.removeprefix(b"\xef\xbb\xbf")), convert_options=options)
    if keep is not None:
        column, values = keep
        table = table.filter(pc.is_in(table.column(column), value_set=pa.array(sorted(values), pa.string())))
    return table.to_pandas()


def active_services(archive, date):
    calendar_df = read_feed_table(archive, "calendar.txt", ["service_id", date.strftime("%A").lower(),
                                                            "start_date", "end_date"])
    stamp = date.strftime("%Y%m%d")
    weekday = date.strftime("%A").lower()
    active = set(calendar_df.service_id[(calendar_df[weekday] == "1") & (calendar_df.start_date <= stamp)
                                        & (calendar_df.end_date >= stamp)])
    dates_df = read_feed_table(archive, "calendar_dates.txt", ["service_id", "date", "exception_type"])
    dates_df = dates_df[dates_df.date == stamp]
    active |= set(dates_df.service_id[dates_df.exception_type == "1"])
    active -= set(dates_df.service_id[dates_df.exception_type == "2"])
    return active


def gtfs_seconds(text):
    parts = text.str.split(":", expand=True).astype(int)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def stop_events(hex_df, minutes_df):
    """Stop events per day type, 30-min slot and mode at stops near the day type's envelope hexes."""
    from scipy.spatial import cKDTree
    envelopes = {}
    for chunk_dir in chunk_dirs():
        day = chunk_clock(chunk_dir)[0]
        envelopes.setdefault(day, set()).update(pd.read_csv(chunk_dir / "envelope.csv", usecols=["hex_id"]).hex_id)
    slots_by_day = {day: sorted(set(c // SLOT_MIN)) for day, c in minutes_df.groupby("day_type").clock_min}
    rows = []
    for mode, feed_path in FEED_PATHS.items():
        with zipfile.ZipFile(feed_path) as archive:
            stops_df = read_feed_table(archive, "stops.txt", ["stop_id", "stop_lat", "stop_lon"])
            trips_df = read_feed_table(archive, "trips.txt", ["trip_id", "service_id"])
            services = {day: active_services(archive, date) for day, date in DAY_DATES.items()}
            any_day_trips = set(trips_df.trip_id[trips_df.service_id.isin(set().union(*services.values()))])
            times_df = read_feed_table(archive, "stop_times.txt", ["trip_id", "departure_time", "stop_id"],
                                       keep=("trip_id", any_day_trips))
        stops_df["x"], stops_df["y"] = to_metres(stops_df.stop_lat.astype(float), stops_df.stop_lon.astype(float))
        times_df["slot"] = gtfs_seconds(times_df.departure_time) // (SLOT_MIN * 60)
        for day, envelope in envelopes.items():
            envelope_xy = hex_df.loc[sorted(envelope), ["x", "y"]].to_numpy()
            distance_m, _ = cKDTree(envelope_xy).query(stops_df[["x", "y"]].to_numpy())
            near_stops = set(stops_df.stop_id[distance_m <= STOP_RADIUS_M])
            day_trips = set(trips_df.trip_id[trips_df.service_id.isin(services[day])])
            day_df = times_df[times_df.trip_id.isin(day_trips) & times_df.stop_id.isin(near_stops)
                              & times_df.slot.isin(slots_by_day[day])]
            counts = day_df.groupby("slot").size().reindex(slots_by_day[day], fill_value=0)
            rows += [dict(day_type=day, mode=mode, slot=slot, events=int(n), stops=len(near_stops))
                     for slot, n in counts.items()]
        print(f"stop events: {mode} read", flush=True)
    return pd.DataFrame(rows)


def flag_table(events_df, minutes_df, element):
    """Per span: largest adjacent-slot step in stop events (all modes) and in the element's slot means."""
    events = events_df.groupby(["day_type", "slot"]).events.sum()
    slot_means = minutes_df.groupby(["day_type", minutes_df.clock_min // SLOT_MIN])[element].mean()
    rows = []
    for (day, span), span_df in minutes_df.groupby(["day_type", "span"]):
        slots = sorted(set(span_df.clock_min // SLOT_MIN))
        trip = events.loc[day].reindex(slots).to_numpy(float)
        reach = slot_means.loc[day].reindex(slots).to_numpy()
        trip_steps = np.abs(trip[1:] / trip[:-1] - 1) if len(slots) > 1 else np.array([0.0])
        reach_steps = np.abs(reach[1:] / reach[:-1] - 1) if len(slots) > 1 else np.array([0.0])
        rows.append(dict(span=span, slots=len(slots), trip_step_pct=100 * trip_steps.max(),
                         reach_step_pct=100 * reach_steps.max(), is_flagged=trip_steps.max() > TRIP_STEP_FLAG,
                         has_reach_step=reach_steps.max() > REACH_STEP,
                         trip_profile="/".join(str(int(t)) for t in trip)))
    return pd.DataFrame(rows)


# --- corridor --------------------------------------------------------------------------------------------------
def corridor_points():
    """Densified shape points of the tram routes with a stop near the subject; their route names."""
    from scipy.spatial import cKDTree
    with zipfile.ZipFile(FEED_PATHS[TRAM_MODE]) as archive:
        stops_df = read_feed_table(archive, "stops.txt", ["stop_id", "stop_lat", "stop_lon"])
        routes_df = read_feed_table(archive, "routes.txt", ["route_id", "route_short_name", "route_type"])
        trips_df = read_feed_table(archive, "trips.txt", ["trip_id", "route_id", "shape_id"])
        times_df = read_feed_table(archive, "stop_times.txt", ["trip_id", "stop_id"])
        shapes_df = read_feed_table(archive, "shapes.txt", ["shape_id", "shape_pt_lat", "shape_pt_lon",
                                                            "shape_pt_sequence"])
    stop_x, stop_y = to_metres(stops_df.stop_lat.astype(float), stops_df.stop_lon.astype(float))
    near = set(stops_df.stop_id[np.hypot(stop_x, stop_y) <= CORRIDOR_STOP_RADIUS_M])
    tram_routes = set(routes_df.route_id[routes_df.route_type.astype(int) == TRAM_ROUTE_TYPE])
    near_trips = set(times_df.trip_id[times_df.stop_id.isin(near)])
    route_trips = trips_df[trips_df.trip_id.isin(near_trips) & trips_df.route_id.isin(tram_routes)]
    names = sorted(set(routes_df.set_index("route_id").route_short_name.reindex(route_trips.route_id)))
    shapes_df = shapes_df[shapes_df.shape_id.isin(set(route_trips.shape_id))].copy()
    shapes_df["seq"] = shapes_df.shape_pt_sequence.astype(int)
    points = []
    for _, shape_df in shapes_df.sort_values("seq").groupby("shape_id"):
        x, y = to_metres(shape_df.shape_pt_lat.astype(float), shape_df.shape_pt_lon.astype(float))
        for x0, y0, x1, y1 in zip(x[:-1], y[:-1], x[1:], y[1:]):
            steps = max(int(np.hypot(x1 - x0, y1 - y0) // SHAPE_STEP_M), 1)
            fractions = np.arange(steps) / steps
            points.append(np.column_stack([x0 + fractions * (x1 - x0), y0 + fractions * (y1 - y0)]))
    return np.vstack(points), names, cKDTree


def principal_axis(x, y, weight):
    """Axis ratio (sqrt of eigenvalue ratio) and bearing of the major axis, degrees from north in [0, 180)."""
    mx, my = np.average(x, weights=weight), np.average(y, weights=weight)
    cov = np.cov(np.vstack([x - mx, y - my]), aweights=weight)
    values, vectors = np.linalg.eigh(cov)
    major = vectors[:, 1]
    return float(np.sqrt(values[1] / values[0])), float(np.degrees(np.arctan2(major[0], major[1])) % 180)


def corridor_table(origins_df, minutes_df, hex_df):
    shape_xy, names, tree_class = corridor_points()
    tree = tree_class(shape_xy)
    week_w = {day: w for day, w in DAYS_PER_TYPE.items()}
    chunk_day = minutes_df.groupby("chunk").day_type.first()
    total_minutes_w = float(minutes_df.day_type.map(week_w).sum())
    populated = hex_df[hex_df.persons > 0]
    populated_on = tree.query(populated[["x", "y"]].to_numpy())[0] <= CORRIDOR_BUFFER_M
    populated_dist = np.hypot(populated.x, populated.y)
    rows = []
    for band in BAND_CUTS_S:
        share = (origins_df[f"minutes_{band}"] * origins_df.chunk.map(chunk_day).map(week_w)) \
            .groupby(origins_df[ORIGIN_COL]).sum() / total_minutes_w
        share = share[share > 0]
        reach_df = hex_df.loc[share.index, ["x", "y", "persons"]].assign(share=share)
        reach_df["weight"] = reach_df.persons * reach_df.share
        reach_df = reach_df[reach_df.weight > 0]
        dist = np.hypot(reach_df.x, reach_df.y)
        order = np.argsort(dist.to_numpy())
        cum = np.cumsum(reach_df.weight.to_numpy()[order]) / reach_df.weight.sum()
        radius_m = float(dist.to_numpy()[order][np.searchsorted(cum, DISC_QUANTILE)])
        on = tree.query(reach_df[["x", "y"]].to_numpy())[0] <= CORRIDOR_BUFFER_M
        in_disc = populated_dist <= radius_m
        disc_share = float(populated.persons[in_disc & populated_on].sum() / populated.persons[in_disc].sum())
        reach_share = float(reach_df.weight[on].sum() / reach_df.weight.sum())
        ratio, bearing = principal_axis(reach_df.x.to_numpy(), reach_df.y.to_numpy(), reach_df.weight.to_numpy())
        near_shape = shape_xy[np.hypot(shape_xy[:, 0], shape_xy[:, 1]) <= radius_m]
        _, corridor_bearing = principal_axis(near_shape[:, 0], near_shape[:, 1], np.ones(len(near_shape)))
        gap = abs(bearing - corridor_bearing)
        gap = min(gap, 180 - gap)
        rows.append(dict(band=band, reach_weight_persons=round(reach_df.weight.sum()), radius_p90_km=radius_m / 1000,
                         corridor_share_reach=reach_share, corridor_share_disc=disc_share,
                         share_ratio=reach_share / disc_share, axis_ratio=ratio, axis_bearing_deg=bearing,
                         corridor_bearing_deg=corridor_bearing, bearing_gap_deg=gap,
                         holds=bool(reach_share >= CORRIDOR_SHARE_RATIO * disc_share and gap <= AXIS_TOLERANCE_DEG)))
    return pd.DataFrame(rows), names, shape_xy


# --- figures ---------------------------------------------------------------------------------------------------
def plot_minutes(minutes_df, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(DAY_ORDER), 1, figsize=(10, 11), sharex=True)
    for ax, day in zip(axes, DAY_ORDER):
        day_df = minutes_df[minutes_df.day_type == day].sort_values("clock_min")
        for _, window_df in open_windows(day_df):
            hours = window_df.clock_min / 60
            ax.plot(hours, window_df.persons_b20 / 1000, color="tab:blue", lw=0.9,
                    label="persons, band 2 (<= 20 min)")
            ax.plot(hours, window_df.persons_b30 / 1000, color="tab:orange", lw=0.9, label="persons, <= 30 min")
            slot_mean = window_df.groupby(window_df.clock_min // SLOT_MIN).persons_b20.transform("mean")
            ax.plot(hours, slot_mean / 1000, color="tab:blue", lw=1.8, alpha=0.5, label="band 2, 30-min slot mean")
        ax.set_title(day, loc="left", fontsize=10)
        ax.set_ylabel("persons (k)")
        ax.grid(alpha=0.3)
    handles, labels = axes[0].get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    axes[0].legend(unique.values(), unique.keys(), fontsize=8, loc="upper left")
    axes[-1].set_xlabel("departure clock time (h)")
    fig.suptitle("Subject transit pass: persons reaching the subject, every departure minute")
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_map(origins_df, minutes_df, hex_df, shape_xy, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    chunk_day = minutes_df.groupby("chunk").day_type.first()
    week_w = origins_df.chunk.map(chunk_day).map(DAYS_PER_TYPE)
    share = (origins_df.minutes_b20 * week_w).groupby(origins_df[ORIGIN_COL]).sum() \
        / float(minutes_df.day_type.map(DAYS_PER_TYPE).sum())
    share = share[share > 0]
    xy = hex_df.loc[share.index, ["x", "y"]] / 1000
    fig, ax = plt.subplots(figsize=(8, 9))
    ax.scatter(shape_xy[:, 0] / 1000, shape_xy[:, 1] / 1000, s=0.3, color="0.6", label="subject's tram routes")
    points = ax.scatter(xy.x, xy.y, c=share, s=5, cmap="viridis")
    ax.plot(0, 0, marker="*", color="red", markersize=14)
    reach = xy.abs().max().max() * 1.1
    ax.set_xlim(-reach, reach)
    ax.set_ylim(-reach, reach)
    ax.set_aspect(1)
    ax.set_xlabel("km east of the subject")
    ax.set_ylabel("km north of the subject")
    ax.legend(loc="lower left", fontsize=8, markerscale=10)
    fig.colorbar(points, ax=ax, shrink=0.7, label="week-weighted share of open minutes within band 2")
    ax.set_title("Subject transit pass: band-2 reach by origin hex")
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


# --- main ------------------------------------------------------------------------------------------------------
def main():
    hex_df = hex_table()
    minutes_df, origins_df = load_or_compute(hex_df)
    minutes_df["span"] = [span_of(d, c) for d, c in zip(minutes_df.day_type, minutes_df.clock_min)]
    prefix = f"{NAME}_{run_date()}"
    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 60)
    pd.set_option("display.float_format", lambda v: f"{v:,.2f}")

    events_df = stop_events(hex_df, minutes_df)
    events_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{prefix}_stop_events.csv", index=False)
    flag_df = flag_table(events_df, minutes_df, f"persons_{DECIDING_BAND}")
    flagged = list(flag_df.span[flag_df.is_flagged])
    print("\n== (2b) trip-count flag per span (stop events all modes; reach = band-2 persons slot means) ==")
    print(flag_df.to_string(index=False))
    missed = flag_df.span[flag_df.has_reach_step & ~flag_df.is_flagged].tolist()
    false_alarms = flag_df.span[flag_df.is_flagged & ~flag_df.has_reach_step].tolist()
    print(f"flag tracks reach: {'yes' if not missed else 'NO'}; reach steps missed: {missed}; "
          f"false alarms: {false_alarms}")
    print(events_df.groupby(["day_type", "mode"]).agg(stops=("stops", "first"), events=("events", "sum"))
          .to_string())

    scheme_parts, span_parts = [], []
    print("\n== (1) scheme errors on the week headline, relative RMS % (random start; aligned starts beside) ==")
    for band in BAND_CUTS_S:
        for element in ("persons", "flat"):
            column = f"{element}_{band}"
            headline, scheme_df, span_df = scheme_errors(minutes_df, column, flagged)
            scheme_parts.append(scheme_df.assign(element=column, headline=headline))
            span_parts.append(span_df.assign(element=column))
            print(f"\n-- {column}: week headline {headline:,.0f} --")
            print(scheme_df.to_string())
    scheme_all = pd.concat(scheme_parts).rename_axis("scheme").reset_index()
    span_all = pd.concat(span_parts, ignore_index=True)
    scheme_all.to_csv(DIAGNOSTIC_DATA_DIR / f"{prefix}_schemes.csv", index=False)
    span_all.to_csv(DIAGNOSTIC_DATA_DIR / f"{prefix}_spans.csv", index=False)
    print("\n-- per span, band 2: one random-start 30-min window's relative RMS and worst start (% of span mean) --")
    print(span_all[span_all.element.str.endswith(DECIDING_BAND)]
          .pivot_table(index="span", columns="element", values=["window_err_pct", "worst_start_pct"]).to_string())
    deciding = scheme_all[(scheme_all.scheme == "hybrid") & scheme_all.element.str.endswith(DECIDING_BAND)]
    is_hybrid_ok = bool((deciding.err_random_pct <= UPPER_BOUND_81ST_PCT).all())
    print(f"rule (1): hybrid band-2 errors {deciding.err_random_pct.round(2).tolist()} (persons, flat) vs "
          f"<= {UPPER_BOUND_81ST_PCT}%: {'HOLDS' if is_hybrid_ok else 'FAILS'}")

    print("\n== (2a) within-window trend, band-2 and 30-min persons ==")
    trend_parts = []
    for column in ("persons_b20", "persons_b30", "flat_b20"):
        trend_df = trend_table(minutes_df, column).assign(element=column)
        trend_parts.append(trend_df)
        print(f"-- {column} --")
        print(trend_df.drop(columns="element").to_string(index=False))
    trend_all = pd.concat(trend_parts, ignore_index=True)
    trend_all.to_csv(DIAGNOSTIC_DATA_DIR / f"{prefix}_trend.csv", index=False)
    drifting = trend_all[(trend_all.element == "persons_b20")
                         & (trend_all.first_to_last_third_pct.abs() > DRIFT_PCT)].window.tolist()
    print(f"windows drifting > {DRIFT_PCT:.0f}% (band-2 persons): {drifting}")

    print("\n== (3) corridor vs across ==")
    corridor_df, route_names, shape_xy = corridor_table(origins_df, minutes_df, hex_df)
    corridor_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{prefix}_corridor.csv", index=False)
    print(f"tram routes with a stop within {CORRIDOR_STOP_RADIUS_M} m of the subject: {route_names}")
    print(corridor_df.to_string(index=False))

    plot_minutes(minutes_df, DIAGNOSTIC_IMG_DIR / f"{prefix}_minutes.png")
    plot_map(origins_df, minutes_df, hex_df, shape_xy, DIAGNOSTIC_IMG_DIR / f"{prefix}_map.png")
    print(f"\nsaved: {prefix}_* in diagnostic_data (csv) and diagnostic_img (png)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(f"usage: python {Path(__file__).name}")
    main()
