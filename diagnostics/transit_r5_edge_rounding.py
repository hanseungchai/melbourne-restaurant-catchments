"""R5 per-edge rounding (TRN-16 candidate): how much of R5's walk-only time beyond path / speed is each edge's ceiling.

Claim under test (concepts/transit.md TRN-16; walk.md WLK-1 caveat; DESIGN.md Q24 (2)): R5 walks a street edge in
`ceil(length / speed)` whole seconds (BasicTraversalTimeCalculator.traversalTimeSeconds; +1 s if that is 0,
EdgeStore.traverse), so a walk-only trip runs ~0.5 s per edge longer than its path length / speed, and nothing else
on the path adds time. Source read 2026-10-21 (inputs/r5py/r5-7.5.1, never edited), walk-only TTM on the current jar
(P1 + P3 + P2: connectors not charged), forward search:
  origin end    StreetRouter.setOrigin: (int) ((distance_mm / 1000) / speed), whole metres then whole seconds, floored;
  edges         EdgeStore.traverse: ceil(getLengthM() / speed) each, walk turn cost 0;
  destination   LinkedPointSet.timeToPoint: min over the edge's two vertices of vertex time + distance_mm / speed_mm_s
                (integers: floored, and speed_mm_s = (int) (walkSpeed * 1000), 1150 at 4.143 km/h); same edge as the
                origin (eval): |d0 origin - d0 dest| / speed_mm_s.
Where the pipeline would rely on it: Q24 (2) fits the walk speed as R5 street path / Google seconds, which assumes R5
walks a path in path / speed; a per-edge excess makes every R5 walk slower than the fitted speed (and the access walk
to stops too). A patch (round per path, not per edge) is the TRN-16 candidate this test sizes.

Steps (one JVM per process, P2's jar from outputs/r5_patches/, chosen at JVM start through r5py's `--r5-classpath`):
  route <release>  Every scored training pair of the release (as transit_r5_patch_connector.py route_train) whose
      walk-only TTM seconds (its p2orig training table) are finite: StreetRouter as TravelTimeComputer sets it for a
      walk-only search (WALK, DURATION_SECONDS, time limit MAX_TIME_MIN), from the drawn origin; the destination's
      split; R5's time rebuilt as above; the path unwound from the chosen vertex (backState chain). Per pair: edges,
      path length, each part's seconds beside its exact value (distance / speed at SPEED_KMH), each edge's charged
      increment checked against Python's ceil.
  score  Rules (Claude's, written before any result):
      (F1) Rebuilt R5 seconds = the saved TTM walk seconds on every pair. Any difference: stop, the rebuild is not
           TTM's path.
      (F2) Every edge's increment = max(1, ceil(length_m / speed)) in R5's float arithmetic. Any difference: some
           other per-edge charge exists; listed, and the claim fails.
      Excess = R5 - path / speed (s), split exactly into origin part + edge part + destination part.
      (C) Claim CONFIRMED if F2 passes, the pooled edge excess per edge is in EDGE_EXCESS_RANGE_S and the ends'
          median |origin + destination part| <= END_TOLERANCE_S; else FAILS, with the part that broke it.
      Reported, no verdict: excess, edge part and edges per path (median, mean, p90) for all pairs and the pairs whose
      Google default walks (0 boardings); fit excess ~ edges (slope, intercept, R^2); excess per edge by edge length
      (bins EDGE_LENGTH_BINS_M). Output effect, an under-estimate since transit access walks are not rebuilt: R5 walk
      minus the edge part, against Google's seconds on pairs whose Google default walks (0 boardings): median and mean
      error before / after; model minutes (min(transit, walk), half up, SCR-10) and band calls changed (cuts 10, 20 min).
  Predictions (Claude's, before any result): F1 and F2 pass. Excess per edge ~0.5 s (pooled 0.45-0.55); the ends
  together ~-1 s median (three floors). Walk-only paths ~30-60 edges, edge part median ~15-30 s (the WLK-1 caveat's
  ~26 s came before P2 and included connectors). Google-walk pairs: median error moves ~-20 s toward Google's;
  model minutes change on ~10-20% of walk-winning pairs, band calls on a handful.
  Group fix before any result: the training table's `stratum` is stop density, not walk_only; the walk group is
  defined from P2's scored table (Google default with 0 boardings).

Conclusion (run 2026-10-21, 2,212 training pairs with a finite walk-only time; rules above written before any result):
  F1 PASS (rebuilt = TTM on every pair). F2 PASS (0 of 244,054 edge increments differ from max(1, ceil)): no other
  per-edge charge. (C) CONFIRMED: pooled edge excess 0.482 s per edge, ends median |origin + destination| 1.42 s
  (origin -1.0, destination -0.5 median). Fit excess ~ edges: slope 0.486 s per edge, intercept -1.80 s, R^2 0.986.
  Edges are short (median 11.5 m; 46% under 10 m), so the excess is large: all pairs median 108 edges, excess median
  50 s (mean 52, p90 89) on a median 3.4 km path; Google-walk pairs (173) median 29 edges, excess 12 s (mean 16, p90
  30). Excess per edge flat by length (0.48-0.50 s in every bin). Output effect (walk call only): Google-walk pairs'
  R5 - Google median 18.0 -> 3.8 s, mean 38.6 -> 20.7 s; model minutes change on 138 of 3,448 pairs, band calls 11.
  Prediction check: F1, F2, per-edge ~0.5 and ends right; walk paths' edges (29) and edge part (14 s) just under the
  predicted ranges; the median error moved -14 s, not -20; minutes changed on 138 pairs, far more than the
  predicted 10-20% of walk wins (a ~25 s shift crosses a half-minute line on ~40% of values; Claude's prediction
  ignored that). Transit access walks (StreetRouter, same ceiling) are not rebuilt here: the effect on transit
  pairs is unmeasured.

Inputs (read only): P2's jar, v2 networks and feeds, the connector diagnostic's p2orig training tables and scored
table, the training pairs (diagnostic_data/). Writes tables to diagnostics/diagnostic_data/. Self-contained (CLAUDE.md
D1). No paid API calls. Usage: `python transit_r5_edge_rounding.py route <release>`, `... score`.
"""
import datetime
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
PATCH_DIR = PROJECT_ROOT / "outputs" / "r5_patches"
P2_NAME = "transit_r5_patch_connector"
JAR_PATH = PATCH_DIR / f"r5-v7.5.1-r5py-all_{P2_NAME}_p2.jar"
P2_ROUTES_DATE = "20261021"
P2_SCORED_PATH = DIAGNOSTIC_DATA_DIR / f"{P2_NAME}_{P2_ROUTES_DATE}_train_scored.csv"
V2_NAME = "transit_pathway_network_v2"
RANGE_RESULTS_GLOB = f"{V2_NAME}_2*_range_owndate_results.csv"
NAME = "transit_r5_edge_rounding"

# --- values copied from transit_r5_patch_connector.py ----------------------------------------------
GUARD_CLASSES = ["com.conveyal.r5.streets.StreetRouter", "com.conveyal.r5.streets.LinkedPointSet",
                 "com.conveyal.r5.streets.BasicTraversalTimeCalculator", "com.conveyal.r5.streets.EdgeStore"]
RELEASES = ["20261009", "20261016"]
R5_MAX_MEMORY = "7G"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
SPEED_KMH = 4.143                              # Q24 (2) median; user 2026-10-21
MAX_TIME_MIN = 90
SPLIT_RADIUS_M = 1600                          # R5's StreetLayer.LINK_RADIUS_METERS
MM_PER_M = 1000
SECONDS_PER_MIN = 60
SECONDS_PER_HOUR = 3600
CUTS_MIN = [10, 20]
WALK_GROUP = "0"                               # boardings of Google's default: walks
PROGRESS_EVERY = 500

# --- this test -------------------------------------------------------------------------------------
MIN_EDGE_INCREMENT_S = 1                       # EdgeStore.traverse: a state never keeps the same time
EDGE_EXCESS_RANGE_S = (0.40, 0.60)             # (C) pooled edge excess per edge (uniform fraction: 0.5)
END_TOLERANCE_S = 2.0                          # (C) median |origin + destination part|
EDGE_LENGTH_BINS_M = [0, 10, 25, 50, 100, 200, np.inf]
P90 = 90


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def network_paths(release):
    """The pathways v2 network of a release, as transit_q24_combined.network_paths (unique file names)."""
    feed_dir = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_gtfs_{release}"
    pbf_path = DIAGNOSTIC_DATA_DIR / f"{V2_NAME}_osm_{release}.osm.pbf"
    gtfs = [feed_dir / (f"{name}_{V2_NAME}_{release}_moved.zip" if name == TRAIN_FEED else f"{name}_{V2_NAME}_{release}.zip")
            for name in FEED_NAMES]
    return pbf_path, gtfs


def check_working_copies(paths):
    """Stop if r5py's cached working copy of an input differs from the file given (memory r5py-working-copy-cache)."""
    import hashlib
    from r5py.util.config import Config
    for path in paths:
        cached = Path(Config().CACHE_DIR) / Path(path).name
        if not cached.exists():
            continue
        digests = []
        for candidate in (path, cached):
            with open(candidate, "rb") as file:
                digests.append(hashlib.file_digest(file, "blake2s").hexdigest())
        assert digests[0] == digests[1], f"r5py's cached {cached} differs from {path}: stale working copy"


def open_network(release):
    """Start the JVM on P2's jar (guarded), load the release's v2 network; returns r5py's TransportNetwork."""
    assert JAR_PATH.exists(), "transit_r5_patch_connector.py build first"
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(JAR_PATH)]   # r5py reads these at import
    import jpype
    from r5py import TransportNetwork
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    for name in GUARD_CLASSES:
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == JAR_PATH.resolve(), f"{name} loaded from {location}"
    print(f"{', '.join(c.rsplit('.', 1)[1] for c in GUARD_CLASSES)} from {JAR_PATH.name}", flush=True)
    pbf_path, gtfs = network_paths(release)
    assert pbf_path.exists() and all(p.exists() for p in gtfs), "transit_pathway_network_v2 build / feeds first"
    check_working_copies([pbf_path] + gtfs)
    print(f"reusing {pbf_path.name} and {[p.name for p in gtfs]}", flush=True)
    return TransportNetwork(pbf_path, gtfs)


def training_pairs():
    pairs_df = pd.read_csv(newest(RANGE_RESULTS_GLOB))
    return pairs_df[pairs_df.is_scored.astype(bool)]


# --- route -----------------------------------------------------------------------------------------
def walk_speeds():
    """R5's speeds: walkSpeed as a Java float (m/s), the destination's integer mm/s, and the exact m/s."""
    exact_m_s = SPEED_KMH * MM_PER_M / SECONDS_PER_HOUR
    float_m_s = np.float32(exact_m_s)
    speed_mm_s = int(float_m_s * np.float32(MM_PER_M))
    return float(float_m_s), speed_mm_s, exact_m_s


def decompose(street_layer, router_class, request, routing_variable, walk_mode, origin, destination):
    """One walk-only search, rebuilt as TTM's: R5 seconds, its three parts beside their exact values, the path's edges."""
    float_m_s, speed_mm_s, exact_m_s = walk_speeds()
    router = router_class(street_layer)
    router.profileRequest = request
    router.streetMode = walk_mode
    router.timeLimitSeconds = MAX_TIME_MIN * SECONDS_PER_MIN
    router.quantityToMinimize = routing_variable
    if not router.setOrigin(float(origin[0]), float(origin[1])):
        return None
    router.route()
    origin_split = router.getOriginSplit()
    dest_split = street_layer.findSplit(float(destination[0]), float(destination[1]), float(SPLIT_RADIUS_M), walk_mode)
    if dest_split is None:
        return None
    row = {}
    if int(origin_split.edge) == int(dest_split.edge):
        along_mm = abs(int(origin_split.distance0_mm) - int(dest_split.distance0_mm))
        row.update(r5_s=along_mm // speed_mm_s, n_edges=0, path_mm=along_mm, origin_s=0, origin_exact_s=0.0,
                   edge_s=0, edge_exact_s=0.0, dest_s=along_mm // speed_mm_s, dest_exact_s=along_mm / MM_PER_M / exact_m_s,
                   n_increment_off=0, edge_lengths_mm="")
        return row
    ends = []
    for vertex, dest_mm in [(dest_split.vertex0, dest_split.distance0_mm), (dest_split.vertex1, dest_split.distance1_mm)]:
        vertex_s = int(router.getTravelTimeToVertex(int(vertex)))
        if vertex_s != np.iinfo(np.int32).max:
            ends.append((vertex_s + int(dest_mm) // speed_mm_s, int(vertex), int(dest_mm)))
    if not ends:
        return None
    r5_s, vertex, dest_mm = min(ends)
    states = []
    state = router.getStateAtVertex(vertex)
    while state is not None:
        states.append(state)
        state = state.backState
    states.reverse()
    start = states[0]
    edge_cursor = street_layer.edgeStore.getCursor()
    lengths_mm, n_increment_off, edge_s = [], 0, 0
    for before, after in zip(states, states[1:]):
        edge_cursor.seek(int(after.backEdge))
        length_mm = int(edge_cursor.getLengthMm())
        increment_s = int(after.getDurationSeconds()) - int(before.getDurationSeconds())
        expected_s = max(MIN_EDGE_INCREMENT_S, math.ceil(float(edge_cursor.getLengthM()) / float_m_s))
        n_increment_off += increment_s != expected_s
        lengths_mm.append(length_mm)
        edge_s += increment_s
    start_mm = int(start.distance)
    row.update(r5_s=r5_s, n_edges=len(lengths_mm), path_mm=start_mm + sum(lengths_mm) + dest_mm,
               origin_s=int(start.getDurationSeconds()), origin_exact_s=start_mm / MM_PER_M / exact_m_s,
               edge_s=edge_s, edge_exact_s=sum(lengths_mm) / MM_PER_M / exact_m_s,
               dest_s=dest_mm // speed_mm_s, dest_exact_s=dest_mm / MM_PER_M / exact_m_s,
               n_increment_off=n_increment_off, edge_lengths_mm=" ".join(map(str, lengths_mm)))
    return row


def route(release):
    assert release in RELEASES
    routes_df = pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{P2_NAME}_{P2_ROUTES_DATE}_trainroutes_p2orig_{release}.csv")
    pairs_df = training_pairs()
    pairs_df = pairs_df[pairs_df.release.astype(str) == release].merge(routes_df[["draw_no", "walk"]], on="draw_no")
    pairs_df = pairs_df[np.isfinite(pairs_df.walk)]
    network = open_network(release)
    import jpype
    from com.conveyal.r5.profile import ProfileRequest, StreetMode
    from com.conveyal.r5.streets import StreetRouter
    routing_variable = jpype.JClass("com.conveyal.r5.streets.StreetRouter$State$RoutingVariable").DURATION_SECONDS
    request = ProfileRequest()
    request.walkSpeed = walk_speeds()[0]
    street_layer = network._transport_network.streetLayer
    print(f"{release}: {len(pairs_df)} pairs with a finite walk-only time", flush=True)
    rows = []
    started = datetime.datetime.now()
    for i, pair in enumerate(pairs_df.itertuples()):
        row = decompose(street_layer, StreetRouter, request, routing_variable, StreetMode.WALK,
                        (pair.origin_lat, pair.origin_lon), (pair.dest_lat, pair.dest_lon))
        rows.append({"draw_no": pair.draw_no, "release": release, "stratum": pair.stratum, "ttm_s": pair.walk,
                     **(row if row is not None else {"r5_s": np.nan})})
        if i % PROGRESS_EVERY == 0:
            print(f"  {i + 1}/{len(pairs_df)} after {datetime.datetime.now() - started}", flush=True)
    out_path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_paths_{release}.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"done: {len(rows)} pairs in {datetime.datetime.now() - started} -> {out_path.name}", flush=True)


# --- score -----------------------------------------------------------------------------------------
def summary(label, values):
    values = pd.Series(values).dropna()
    return (f"{label}: n {len(values)}, median {values.median():.1f}, mean {values.mean():.2f}, "
            f"p90 {np.percentile(values, P90):.1f}")


def rounded_min(seconds):
    """Half up to the nearest minute (SCR-10), NaN kept."""
    return np.floor(np.asarray(seconds, dtype=float) / SECONDS_PER_MIN + 0.5)


def band_of(minutes):
    return np.digitize(minutes, CUTS_MIN, right=True)


def score():
    frames = []
    for release in RELEASES:
        path = newest(f"{NAME}_2*_paths_{release}.csv")
        assert path is not None, f"route {release} first"
        frames.append(pd.read_csv(path, dtype={"edge_lengths_mm": str}))
    paths_df = pd.concat(frames, ignore_index=True)
    lines = [f"{NAME} {run_date()} score ({len(paths_df)} pairs)"]

    n_unrebuilt = int(paths_df.r5_s.isna().sum())
    is_off = paths_df.r5_s.notna() & (paths_df.r5_s != paths_df.ttm_s)
    lines.append(f"(F1) rebuilt = TTM walk seconds: {int(is_off.sum())} differ, {n_unrebuilt} not rebuilt "
                 f"-> {'PASS' if not is_off.any() and n_unrebuilt == 0 else 'FAIL'}")
    if is_off.any() or n_unrebuilt:
        lines.append(paths_df[is_off | paths_df.r5_s.isna()][["draw_no", "release", "ttm_s", "r5_s", "n_edges"]]
                     .head(20).to_string(index=False))
        text = "\n".join(lines)
        print(text)
        (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_score.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
        return
    n_increment_off = int(paths_df.n_increment_off.sum())
    lines.append(f"(F2) edge increments = max(1, ceil(length / speed)): {n_increment_off} of {int(paths_df.n_edges.sum())} "
                 f"edges differ -> {'PASS' if n_increment_off == 0 else 'FAIL'}")

    paths_df["origin_part_s"] = paths_df.origin_s - paths_df.origin_exact_s
    paths_df["edge_part_s"] = paths_df.edge_s - paths_df.edge_exact_s
    paths_df["dest_part_s"] = paths_df.dest_s - paths_df.dest_exact_s
    paths_df["ends_part_s"] = paths_df.origin_part_s + paths_df.dest_part_s
    paths_df["excess_s"] = paths_df.r5_s - paths_df.path_mm / MM_PER_M / (SPEED_KMH * MM_PER_M / SECONDS_PER_HOUR)
    gap = (paths_df.excess_s - paths_df.origin_part_s - paths_df.edge_part_s - paths_df.dest_part_s).abs().max()
    lines.append(f"parts sum to the excess: max gap {gap:.2e} s")

    per_edge_s = paths_df.edge_part_s.sum() / paths_df.n_edges.sum()
    ends_median_s = paths_df.ends_part_s.abs().median()
    is_edge_ok = EDGE_EXCESS_RANGE_S[0] <= per_edge_s <= EDGE_EXCESS_RANGE_S[1]
    is_ends_ok = ends_median_s <= END_TOLERANCE_S
    broke = [name for name, is_ok in [("F2", n_increment_off == 0), ("edge excess", is_edge_ok), ("ends", is_ends_ok)]
             if not is_ok]
    lines.append(f"(C) pooled edge excess {per_edge_s:.3f} s per edge (range {EDGE_EXCESS_RANGE_S}); ends median "
                 f"|origin + destination| {ends_median_s:.2f} s (<= {END_TOLERANCE_S}) -> "
                 f"{'CONFIRMED' if not broke else 'FAILS on ' + ', '.join(broke)}")

    scored_df = pd.read_csv(P2_SCORED_PATH, dtype={"boardings": str, "release": str})
    paths_df["release"] = paths_df.release.astype(str)
    paths_df = paths_df.merge(scored_df[["draw_no", "release", "boardings"]], on=["draw_no", "release"], how="left")
    for label, frame in [("all", paths_df), ("Google walks", paths_df[paths_df.boardings == WALK_GROUP])]:
        lines.append(f"{label}:")
        for column in ["excess_s", "edge_part_s", "origin_part_s", "dest_part_s", "n_edges"]:
            lines.append("    " + summary(column, frame[column]))
        lines.append("    " + summary("path_m", frame.path_mm / MM_PER_M))
    slope, intercept = np.polyfit(paths_df.n_edges, paths_df.excess_s, 1)
    r_squared = np.corrcoef(paths_df.n_edges, paths_df.excess_s)[0, 1] ** 2
    lines.append(f"fit excess ~ edges: slope {slope:.3f} s per edge, intercept {intercept:.2f} s, R^2 {r_squared:.3f}")

    lengths_m = np.concatenate([np.array(s.split(), dtype=float) / MM_PER_M
                                for s in paths_df.edge_lengths_mm.dropna() if s.strip()])
    float_m_s = walk_speeds()[0]
    edge_excess_s = np.maximum(MIN_EDGE_INCREMENT_S, np.ceil(lengths_m / float_m_s)) - lengths_m / (
        SPEED_KMH * MM_PER_M / SECONDS_PER_HOUR)
    lines.append(f"edges by length (m): {len(lengths_m)} edges, median {np.median(lengths_m):.1f} m")
    bins = pd.cut(lengths_m, EDGE_LENGTH_BINS_M, right=False)
    for interval, group in pd.Series(edge_excess_s).groupby(bins, observed=True):
        lines.append(f"    {interval}: n {len(group)}, excess per edge mean {group.mean():.3f} s")

    lines.append("output effect (walk only; transit access walks not rebuilt, an under-estimate):")
    merged_df = scored_df.merge(paths_df[["draw_no", "release", "ttm_s", "edge_part_s"]], on=["draw_no", "release"],
                                how="left")
    routes = pd.concat([pd.read_csv(DIAGNOSTIC_DATA_DIR / f"{P2_NAME}_{P2_ROUTES_DATE}_trainroutes_p2orig_{r}.csv")
                        .assign(release=r) for r in RELEASES])
    merged_df = merged_df.merge(routes[["draw_no", "release", "transit"]], on=["draw_no", "release"], how="left")
    walk_after_s = merged_df.ttm_s - merged_df.edge_part_s
    is_walk_group = (merged_df.boardings == WALK_GROUP) & merged_df.ttm_s.notna()
    for label, walk_s in [("before", merged_df.ttm_s), ("after", walk_after_s)]:
        error_s = (walk_s - merged_df.google_s)[is_walk_group]
        lines.append(f"    Google-walk pairs ({int(is_walk_group.sum())}), R5 walk - Google {label}: "
                     f"median {error_s.median():.1f} s, mean {error_s.mean():.2f} s")
    model_before_s = np.fmin(merged_df.transit, merged_df.ttm_s)
    model_after_s = np.fmin(merged_df.transit, walk_after_s)
    assert (model_before_s.fillna(np.inf) == merged_df.p2orig_s.fillna(np.inf)).all(), (
        "model seconds differ from P2's scored (unreached: inf there, NaN here)")
    is_known = merged_df.google_min.notna()
    minutes_before, minutes_after = rounded_min(model_before_s), rounded_min(model_after_s)
    n_minutes = int(((minutes_before != minutes_after) & is_known).sum())
    n_bands = int(((band_of(minutes_before) != band_of(minutes_after)) & is_known).sum())
    n_walk_wins = int(((merged_df.ttm_s <= merged_df.transit.fillna(np.inf)) & is_known).sum())
    lines.append(f"    model minutes changed on {n_minutes} of {int(is_known.sum())} pairs ({n_walk_wins} won by walk); "
                 f"band calls changed {n_bands}")

    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_score.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    paths_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_scored.csv", index=False)


if __name__ == "__main__":
    {"route": route, "score": score}[sys.argv[1]](*sys.argv[2:])
