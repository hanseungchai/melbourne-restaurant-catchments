"""How much does Google slow down with road density, relative to the sparsest roads?

Claim under test: Google's drive times slow down with road density, within the same road class,
by an amount that can be measured from route totals alone. Google returns no per-road times
(only each route's traffic-aware duration, no-traffic staticDuration, distance and polyline),
so the per-density slowdown is inferred across the 4,000 validation routes: each Google
polyline is map-matched onto Valhalla's road graph (road class, signals), the project's
continuous road-density raster (km of road per km2 within 2 km; Valhalla's formula before
its rounding to levels 0-15) is sampled along it, and Google's time is regressed on
kilometres per (density bin x road class) cell.
Where the pipeline relies on it: nowhere yet. Context: M2's tier speed factors (DESIGN_pre_spine
"Drive model": x0.8 default, x0.736 fringe, x0.5 urban). This describes Google only; M2's
residuals are not opened (DESIGN.md Q2).
Conclusion (run 2026-10-08, 3,793 of 4,000 pairs within 2% of Google's length): yes, within
each road class, mostly in Google's no-traffic time, not congestion. With a signal term
(about 22 s per signal, static), primary roads run 1.4-1.8x slower above 13 km/km2 than in
the sparsest bin (0-11), secondary/tertiary 1.2-2.0x, local 1.3-1.6x (wide CIs), motorway/trunk
1.0-1.45x. Not monotonic bin to bin. Congestion (traffic minus static) explains little
(R2 0.06). The sparsest bin is not rural: 0-11 km/km2 reaches about Valhalla level 8, and
five sixths of the km lie above it. The trend cross-check has no signal term and is not reliable as run.

Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No paid API calls.
Run with the PyCharm interpreter, which has pyvalhalla installed.
"""

import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.optimize import lsq_linear
from valhalla import Actor, ValhallaError

# --- paths -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOOGLE_ETA_CSV_PATH = (PROJECT_ROOT / "frozen_inputs" / "routes_drive_eta_20260930"
                       / "od_sample_pairs_google_estimates.csv")
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
# Valhalla tiles built by diagnostics/valhalla_vs_google_drive.py (speed_table variant). Used
# only for map matching, road class and signals; Valhalla's speeds and density are not used.
VALHALLA_CONFIG_PATH = (DIAGNOSTIC_DATA_DIR / "valhalla_vs_google_drive_20261007_2343_speed_table_tiles"
                        / "valhalla_config.json")
# Continuous road density (km/km2 within 2 km, 100 m cells), made by construct_map for M2's
# tiers. Read from the road_density stage's output, byte-identical to the legacy file (checked
# 2026-10-16, before data/ was archived); legacy: data/hex_grid/road_density_raster.npz
ROAD_DENSITY_RASTER_PATH = PROJECT_ROOT / "outputs" / "road_density" / "road_density_raster.npz"

DIAGNOSTIC_NAME = "google_slowdown_by_density"
RUN_START = datetime.datetime.now()
RUN_DATE = RUN_START.strftime("%Y%m%d")
RUN_TIME = RUN_START.strftime("%H%M")

# --- map matching (step 1) ---------------------------------------------------------------
PAIRS_FILE_SUFFIX = "_pairs.csv"            # one row per pair: lengths, signals, match status
CELL_KM_FILE_SUFFIX = "_cell_km.csv"        # km per pair x road class x density (DENSITY_STEP grid)
PAIR_ID_COL = "draw_no"
POLYLINE_COL = "polyline"
GOOGLE_TRAFFIC_COL = "google_drive_duration_sec"   # traffic-aware duration
GOOGLE_STATIC_COL = "static_duration_sec"          # Google's no-traffic duration
GOOGLE_DISTANCE_COL = "google_drive_distance_m"
GOOGLE_POLYLINE_PRECISION = 1e5     # Google encoded polylines: 5 decimal places
VALHALLA_POLYLINE_PRECISION = 1e6   # Valhalla's returned shape: 6 decimal places
VALHALLA_COSTING = "auto"
VALHALLA_UNITS = "kilometers"
# Google's polyline is not Valhalla's road geometry, so it is map-matched, not edge-walked.
TRACE_SHAPE_MATCH = "map_snap"
TRACE_ATTRIBUTES = ["edge.length", "edge.road_class", "edge.traffic_signal",
                    "edge.begin_shape_index", "edge.end_shape_index", "shape"]
EARTH_RADIUS_M = 6_371_008.8
METRES_PER_KM = 1000
# Density is stored per pair on a grid of this step (km/km2), so the bins can be re-cut later
# without re-matching.
DENSITY_STEP = 0.1
PROGRESS_EVERY_N_PAIRS = 500
MATCHED_KM_COL = "matched_km"
GOOGLE_KM_COL = "google_km"
N_SIGNALS_COL = "n_signals"            # matched edges with a traffic signal at their end
OUTSIDE_RASTER_KM_COL = "outside_raster_km"
MATCH_ERROR_COL = "match_error"        # empty when the polyline matched
ROAD_CLASS_COL = "road_class"
DENSITY_COL = "density_km_per_km2"
KM_COL = "km"

# --- regression (step 2) -----------------------------------------------------------------
# Pairs kept only if the matched length agrees with Google's distance within this fraction.
MAX_LENGTH_MISMATCH_FRACTION = 0.02
# Density bins: km-weighted quantiles of the continuous density over all kept km, so each bin
# holds about the same road length. Cut points are fractional (chosen 2026-10-08 with Ciara).
N_DENSITY_BINS = 6
# Road-class groups: Valhalla classes pooled so that every density bin keeps enough km.
ROAD_CLASS_GROUPS = {
    "motorway": "motorway_trunk", "trunk": "motorway_trunk",
    "primary": "primary",
    "secondary": "secondary_tertiary", "tertiary": "secondary_tertiary",
    "unclassified": "local", "residential": "local", "service_other": "local",
}
CLASS_GROUP_ORDER = ["motorway_trunk", "primary", "secondary_tertiary", "local"]
# Cells thinner than this are flagged in the output (not merged): their estimates are noisy.
MIN_CELL_KM = 200.0
MIN_CELL_PAIRS = 100
# Fits: Google seconds = intercept (per-trip overhead, free sign) + sum over cells of
# seconds-per-km x cell km [+ seconds per signal x signals]; per-km and signal terms >= 0.
CONGESTION_COL = "congestion_sec"      # traffic-aware minus static
TARGETS = [GOOGLE_STATIC_COL, GOOGLE_TRAFFIC_COL, CONGESTION_COL]
N_BOOT = 1000
BOOT_SEED = 20261008
SECONDS_PER_HOUR = 3600
# Output files.
CELLS_FILE_SUFFIX = "_cells.csv"           # km and pair counts per cell
BIN_FIT_FILE_SUFFIX = "_bin_fit.csv"       # seconds per km per cell, ratio to the sparsest bin
TREND_FIT_FILE_SUFFIX = "_trend_fit.csv"   # cross-check: density as a linear trend per class


# --- step 1: map matching ----------------------------------------------------------------
def decode_polyline(encoded, precision):
    """Decode an encoded polyline into an array of (lat, lon)."""
    coords, index, lat, lon = [], 0, 0, 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift, result = 0, 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lat / precision, lon / precision))
    return np.array(coords)


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def load_density_raster():
    """Return a function mapping (lat, lon) arrays to continuous density (NaN outside)."""
    with np.load(ROAD_DENSITY_RASTER_PATH) as raster:
        density, x0, y0 = raster["density"], float(raster["x0"]), float(raster["y0"])
        cell_m, crs = float(raster["cell_m"]), str(raster["crs"])
    to_raster = Transformer.from_crs("EPSG:4326", crs, always_xy=True)

    def sample(lat, lon):
        x, y = to_raster.transform(lon, lat)
        ix = np.floor((x - x0) / cell_m).astype(int)    # first raster axis is x (construct_map)
        iy = np.floor((y - y0) / cell_m).astype(int)
        is_inside = (ix >= 0) & (ix < density.shape[0]) & (iy >= 0) & (iy < density.shape[1])
        values = np.full(len(x), np.nan)
        values[is_inside] = density[ix[is_inside], iy[is_inside]]
        return values
    return sample


def match_one_route(actor, sample_density, encoded_polyline):
    """Map-match one Google polyline; return (summary dict, segments DataFrame, error)."""
    google_points = decode_polyline(encoded_polyline, GOOGLE_POLYLINE_PRECISION)
    trace_request = {
        "shape": [{"lat": lat, "lon": lon} for lat, lon in google_points],
        "shape_match": TRACE_SHAPE_MATCH,
        "costing": VALHALLA_COSTING,
        "units": VALHALLA_UNITS,
        "filters": {"action": "include", "attributes": TRACE_ATTRIBUTES},
    }
    try:
        trace = actor.trace_attributes(trace_request)
    except ValhallaError as error:
        return {}, None, str(error)
    shape = decode_polyline(trace["shape"], VALHALLA_POLYLINE_PRECISION)
    segment_rows = []
    for edge in trace["edges"]:
        begin, end = edge["begin_shape_index"], edge["end_shape_index"]
        if end > begin:
            segment_rows.append((shape[begin:end], shape[begin + 1:end + 1], edge["road_class"]))
    starts = np.concatenate([row[0] for row in segment_rows])
    ends = np.concatenate([row[1] for row in segment_rows])
    road_classes = np.concatenate([[row[2]] * len(row[0]) for row in segment_rows])
    segment_km = haversine_m(starts[:, 0], starts[:, 1], ends[:, 0], ends[:, 1]) / METRES_PER_KM
    # Each shape segment takes the density at its midpoint, so long edges are split by density.
    density = sample_density((starts[:, 0] + ends[:, 0]) / 2, (starts[:, 1] + ends[:, 1]) / 2)
    segments_df = pd.DataFrame({ROAD_CLASS_COL: road_classes, DENSITY_COL: density, KM_COL: segment_km})
    summary = {
        MATCHED_KM_COL: segment_km.sum(),
        N_SIGNALS_COL: sum(bool(edge["traffic_signal"]) for edge in trace["edges"][:-1]),
        OUTSIDE_RASTER_KM_COL: segment_km[np.isnan(density)].sum(),
    }
    return summary, segments_df, ""


def find_existing_match_prefix():
    """Return the file prefix of the newest saved matching run, or None."""
    candidates = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{DIAGNOSTIC_NAME}_*{CELL_KM_FILE_SUFFIX}"))
    if not candidates:
        return None
    return candidates[-1].name[:-len(CELL_KM_FILE_SUFFIX)]


def match_all_routes():
    """Step 1: map-match every Google polyline. Reuses a saved run; never overwrites one.

    Returns (pairs DataFrame, cell-km DataFrame in long form).
    """
    existing_prefix = find_existing_match_prefix()
    if existing_prefix is not None:
        run_date = existing_prefix[len(DIAGNOSTIC_NAME) + 1:].split("_")[0]
        print(f"reusing map matching made {run_date}: {existing_prefix}")
        return (pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{existing_prefix}{PAIRS_FILE_SUFFIX}",
                            keep_default_na=False),
                pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{existing_prefix}{CELL_KM_FILE_SUFFIX}"))

    google_df = pd.read_csv(GOOGLE_ETA_CSV_PATH)
    actor = Actor(str(VALHALLA_CONFIG_PATH))
    sample_density = load_density_raster()
    pair_rows, cell_dfs = [], []
    for i, pair in enumerate(google_df.itertuples(index=False)):
        pair_id = getattr(pair, PAIR_ID_COL)
        summary, segments_df, error_message = match_one_route(
            actor, sample_density, getattr(pair, POLYLINE_COL))
        pair_rows.append({PAIR_ID_COL: pair_id, **summary, MATCH_ERROR_COL: error_message})
        if segments_df is not None:
            segments_df = segments_df.dropna(subset=[DENSITY_COL])
            segments_df[DENSITY_COL] = (np.floor(segments_df[DENSITY_COL] / DENSITY_STEP)
                                        * DENSITY_STEP).round(1)
            cell_df = segments_df.groupby([ROAD_CLASS_COL, DENSITY_COL], as_index=False)[KM_COL].sum()
            cell_dfs.append(cell_df.assign(**{PAIR_ID_COL: pair_id}))
        if (i + 1) % PROGRESS_EVERY_N_PAIRS == 0:
            print(f"  matched {i + 1} / {len(google_df)}")

    pairs_df = pd.DataFrame(pair_rows)
    cell_km_df = pd.concat(cell_dfs, ignore_index=True)
    file_prefix = f"{DIAGNOSTIC_NAME}_{RUN_DATE}_{RUN_TIME}"
    pairs_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{PAIRS_FILE_SUFFIX}", index=False)
    cell_km_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{CELL_KM_FILE_SUFFIX}", index=False)
    n_failed = (pairs_df[MATCH_ERROR_COL] != "").sum()
    print(f"matched {len(pairs_df) - n_failed} of {len(pairs_df)} polylines ({n_failed} failed) "
          f"-> {file_prefix}{PAIRS_FILE_SUFFIX}")
    return pairs_df, cell_km_df


# --- step 2: regression ------------------------------------------------------------------
def keep_well_matched_pairs(pairs_df):
    """Join Google times; keep pairs whose matched length agrees with Google's distance."""
    google_df = pd.read_csv(GOOGLE_ETA_CSV_PATH, usecols=[PAIR_ID_COL, GOOGLE_TRAFFIC_COL,
                                                           GOOGLE_STATIC_COL, GOOGLE_DISTANCE_COL])
    matched_df = pairs_df[pairs_df[MATCH_ERROR_COL] == ""].drop(columns=[MATCH_ERROR_COL])
    matched_df = matched_df.apply(pd.to_numeric).merge(google_df, on=PAIR_ID_COL, validate="one_to_one")
    matched_df[GOOGLE_KM_COL] = matched_df[GOOGLE_DISTANCE_COL] / METRES_PER_KM
    mismatch = (matched_df[MATCHED_KM_COL] - matched_df[GOOGLE_KM_COL]).abs() / matched_df[GOOGLE_KM_COL]
    print(f"\nMatch quality ({len(matched_df)} matched of {len(pairs_df)}): |matched - Google| / Google km")
    print(mismatch.describe(percentiles=[0.5, 0.9, 0.95, 0.99]).round(4).to_string())
    kept_df = matched_df[mismatch <= MAX_LENGTH_MISMATCH_FRACTION].copy()
    print(f"kept {len(kept_df)} pairs within {MAX_LENGTH_MISMATCH_FRACTION:.0%}; "
          f"km outside the density raster in kept pairs: {kept_df[OUTSIDE_RASTER_KM_COL].sum():.1f}")
    kept_df[CONGESTION_COL] = kept_df[GOOGLE_TRAFFIC_COL] - kept_df[GOOGLE_STATIC_COL]
    return kept_df


def km_weighted_quantile_edges(cell_km_df):
    """Fractional density cut points giving N_DENSITY_BINS bins of about equal km."""
    by_density = cell_km_df.groupby(DENSITY_COL)[KM_COL].sum().sort_index()
    cumulative_share = by_density.cumsum() / by_density.sum()
    inner_edges = [by_density.index[np.searchsorted(cumulative_share.to_numpy(), q)] + DENSITY_STEP
                   for q in np.arange(1, N_DENSITY_BINS) / N_DENSITY_BINS]
    return [0.0] + [round(edge, 1) for edge in inner_edges] + [np.inf]


def build_design(kept_df, cell_km_df, bin_edges):
    """Per-pair km in each (density bin x class group) cell, plus the trend-model columns."""
    cell_km_df = cell_km_df[cell_km_df[PAIR_ID_COL].isin(kept_df[PAIR_ID_COL])].copy()
    cell_km_df["class_group"] = cell_km_df[ROAD_CLASS_COL].map(ROAD_CLASS_GROUPS)
    unknown = cell_km_df.loc[cell_km_df["class_group"].isna(), ROAD_CLASS_COL].unique()
    if len(unknown):
        raise ValueError(f"road classes not in ROAD_CLASS_GROUPS: {unknown}")
    # Bin by the grid value's midpoint, so a grid step never straddles a cut point.
    bin_labels = [f"{low:g}-{high:g}" for low, high in zip(bin_edges[:-1], bin_edges[1:])]
    cell_km_df["density_bin"] = pd.cut(cell_km_df[DENSITY_COL] + DENSITY_STEP / 2, bin_edges,
                                       labels=bin_labels, right=False)
    cell_km_df["cell"] = cell_km_df["class_group"] + "|" + cell_km_df["density_bin"].astype(str)
    cell_order = [f"{group}|{label}" for group in CLASS_GROUP_ORDER for label in bin_labels]
    design_df = (cell_km_df.pivot_table(index=PAIR_ID_COL, columns="cell", values=KM_COL,
                                        aggfunc="sum", fill_value=0.0)
                 .reindex(columns=cell_order, fill_value=0.0))
    # Trend cross-check: per class group, km and km x density (so sec/km = a + b x density).
    cell_km_df["km_x_density"] = cell_km_df[KM_COL] * (cell_km_df[DENSITY_COL] + DENSITY_STEP / 2)
    trend_df = cell_km_df.pivot_table(index=PAIR_ID_COL, columns="class_group",
                                      values=[KM_COL, "km_x_density"], aggfunc="sum", fill_value=0.0)
    trend_df.columns = [f"{group}|{value}" for value, group in trend_df.columns]
    trend_cols = [f"{group}|{value}" for group in CLASS_GROUP_ORDER for value in (KM_COL, "km_x_density")]
    trend_df = trend_df.reindex(columns=trend_cols, fill_value=0.0)
    pairs_df = kept_df.set_index(PAIR_ID_COL).join([design_df, trend_df], how="inner")
    cells_df = pd.DataFrame({"cell": cell_order,
                             "total_km": design_df.sum().to_numpy(),
                             "n_pairs": (design_df > 0).sum().to_numpy()})
    cells_df["is_thin"] = (cells_df["total_km"] < MIN_CELL_KM) | (cells_df["n_pairs"] < MIN_CELL_PAIRS)
    return pairs_df, cell_order, trend_cols, bin_labels, cells_df


def fit_bounded(design, target, n_free):
    """Least squares; the first n_free coefficients are unbounded, the rest >= 0."""
    lower = np.r_[np.full(n_free, -np.inf), np.zeros(design.shape[1] - n_free)]
    return lsq_linear(design, target, bounds=(lower, np.full(design.shape[1], np.inf))).x


def fit_bins(pairs_df, cell_order, bin_labels, boot_index):
    """Seconds per km per cell, for each target, with and without a signal term."""
    rows = []
    for target_col in TARGETS:
        target = pairs_df[target_col].to_numpy(float)
        for has_signals in (False, True):
            predictor_cols = cell_order + ([N_SIGNALS_COL] if has_signals else [])
            design = np.column_stack([np.ones(len(pairs_df)), pairs_df[predictor_cols].to_numpy(float)])
            # Congestion can be negative per km where Google's traffic time beats its static time.
            n_free = design.shape[1] if target_col == CONGESTION_COL else 1
            coefs = fit_bounded(design, target, n_free)
            boot_coefs = np.array([fit_bounded(design[i], target[i], n_free) for i in boot_index])
            residual = target - design @ coefs
            r_squared = 1 - residual @ residual / np.sum((target - target.mean()) ** 2)
            names = ["intercept"] + predictor_cols
            for k, name in enumerate(names):
                row = {"target": target_col, "has_signals": has_signals, "term": name,
                       "coef": coefs[k], "ci_low": np.percentile(boot_coefs[:, k], 2.5),
                       "ci_high": np.percentile(boot_coefs[:, k], 97.5), "r_squared": r_squared}
                if name in cell_order:
                    # Ratio to the same class's sparsest bin: Google's relative slowdown.
                    group = name.split("|")[0]
                    base_k = names.index(f"{group}|{bin_labels[0]}")
                    with np.errstate(divide="ignore", invalid="ignore"):
                        boot_ratio = boot_coefs[:, k] / boot_coefs[:, base_k]
                        row["ratio_to_sparsest"] = coefs[k] / coefs[base_k]
                    row["ratio_ci_low"], row["ratio_ci_high"] = np.nanpercentile(boot_ratio, [2.5, 97.5])
                    if target_col != CONGESTION_COL and coefs[k] > 0:
                        row["implied_kmh"] = SECONDS_PER_HOUR / coefs[k]
                rows.append(row)
    return pd.DataFrame(rows)


def fit_trend(pairs_df, trend_cols, boot_index):
    """Cross-check: per class, sec/km = a + b x density. Reports b / a (slowdown per km/km2)."""
    rows = []
    for target_col in (GOOGLE_STATIC_COL, GOOGLE_TRAFFIC_COL):
        target = pairs_df[target_col].to_numpy(float)
        design = np.column_stack([np.ones(len(pairs_df)), pairs_df[trend_cols].to_numpy(float)])
        coefs = np.linalg.lstsq(design, target, rcond=None)[0]
        boot_coefs = np.array([np.linalg.lstsq(design[i], target[i], rcond=None)[0] for i in boot_index])
        for g, group in enumerate(CLASS_GROUP_ORDER):
            a_k, b_k = 1 + 2 * g, 2 + 2 * g
            boot_slope = boot_coefs[:, b_k] / boot_coefs[:, a_k]
            rows.append({"target": target_col, "class_group": group,
                         "sec_per_km_at_density_0": coefs[a_k],
                         "extra_sec_per_km_per_unit_density": coefs[b_k],
                         "relative_slowdown_per_unit_density": coefs[b_k] / coefs[a_k],
                         "slowdown_ci_low": np.percentile(boot_slope, 2.5),
                         "slowdown_ci_high": np.percentile(boot_slope, 97.5)})
    return pd.DataFrame(rows)


def analyse(pairs_df, cell_km_df):
    """Step 2: bins, cells, bin fit and trend fit; saves dated CSVs."""
    kept_df = keep_well_matched_pairs(pairs_df)
    kept_cell_km_df = cell_km_df[cell_km_df[PAIR_ID_COL].isin(kept_df[PAIR_ID_COL])]
    bin_edges = km_weighted_quantile_edges(kept_cell_km_df)
    print(f"\nDensity bin edges (km/km2, km-weighted quantiles): {bin_edges}")
    design_pairs_df, cell_order, trend_cols, bin_labels, cells_df = build_design(
        kept_df, kept_cell_km_df, bin_edges)
    boot_index = np.random.default_rng(BOOT_SEED).integers(
        0, len(design_pairs_df), size=(N_BOOT, len(design_pairs_df)))
    bin_fit_df = fit_bins(design_pairs_df, cell_order, bin_labels, boot_index)
    trend_fit_df = fit_trend(design_pairs_df, trend_cols, boot_index)

    file_prefix = f"{DIAGNOSTIC_NAME}_{RUN_DATE}_{RUN_TIME}"
    cells_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{CELLS_FILE_SUFFIX}", index=False)
    bin_fit_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{BIN_FIT_FILE_SUFFIX}", index=False)
    trend_fit_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{file_prefix}{TREND_FIT_FILE_SUFFIX}", index=False)
    with pd.option_context("display.width", 220, "display.max_columns", 20, "display.max_rows", 300):
        print(f"\nPairs in the fit: {len(design_pairs_df)}")
        print("\nCells (km and pairs per class group x density bin):")
        print(cells_df.round(1).to_string(index=False))
        print("\nBin fit (sec per km; ratio to the same class's sparsest bin):")
        print(bin_fit_df.round(3).to_string(index=False))
        print("\nTrend fit (relative slowdown per +1 km/km2 of road density):")
        print(trend_fit_df.round(4).to_string(index=False))
    print(f"Saved {file_prefix}{CELLS_FILE_SUFFIX}, {BIN_FIT_FILE_SUFFIX}, {TREND_FIT_FILE_SUFFIX}")


if __name__ == "__main__":
    analyse(*match_all_routes())
