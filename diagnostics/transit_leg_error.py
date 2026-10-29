"""Where does R5's early bias on transit pairs come from? The error to Google split leg by leg.

Claim under test (concepts/transit.md TRN-16; DESIGN.md Q24; HANDOFF 2026-10-21): on the model of record (R5 + P1 + P3
+ P2 at 4.143 km/h on the pathways v2 network, points as drawn) R5 arrives early against Google on transit pairs
(seconds error by Google's boardings, median (mean): 1 boarding -7 (-101) s, 2+ -20 (-207) s; 0 boardings +16 (+15) s),
while its walk to the first stop runs longer than Google's (WLK-6: x1.055, +17 s median). So the early part sits in
waits, rides, transfers or route choice, not in the walks; this test says which. Stop links were the first suspect and
are set aside on existing evidence (source read 2026-10-21: StreetLayer.createAndLinkVertex links each stop by one
straight LINK edge pair walked at walk speed; H-walk measured LINK metres median 2.0 m street, 0.0 m train, and a link
can only add time). Where the pipeline would rely on it: which R5 convention, if any, is the next TRN-16 patch
candidate before transit bands 1-2 (SCR-1, RCH-1); or a stated limitation if the cause is route choice.

Pairs: every scored training pair (v2's range results: train half, second batch, top-up; the test half stays closed,
its Google lines skipped unread). Departure t = the pair's own date and minute, as the scorers.

R5: the model of record's jar (P2's jar: P1 + P3 + P2), drawn points, v2 network of the pair's release, 4.143 km/h,
transit at t, 1-min window (one iteration: t), max_time MAX_TIME_MIN. Paths from the same router as the scored times
(FastRaptorWorker with retainPaths, through TravelTimeComputer with includePathResults; r5py does not expose it, so the
task is built and run directly). Per pair from PathResult's iteration and StopSequence (source: transit/path/Path.java,
StopSequence.java, analyst/cluster/PathResult.java): access.time, waitTimes (one per boarding; the first is the wait at
the first stop, P3's 0 s slack included), rideTimesSeconds, egress.time, totalTime, and transfer = R5's remainder
(totalTime - access - egress - waits - rides: the stop-to-stop transfer walks); each ride's route (short name, else
long name) and board / alight stop. Not DetailedItineraries (McRaptor, its egress fault, transit_router_egress.py).
Google: the default route (route 0's raw record, as transit_access_walk.py reads it). Request time t; the transit
steps' departure and arrival times (stopDetails); walk steps' staticDuration; arrival = GOOGLE_COL + t.

Legs, both sides in seconds (Δ = R5 - Google; negative = R5 earlier):
  access    walk to the first boarding stop. Google: staticDuration of the steps before the first transit step.
  wait0     first boarding time - t - access (the home wait). R5: waitTimes[0].
  ride      in-vehicle seconds summed over boardings. Google: arrival - departure of each transit step.
  transfer  walk + wait between vehicles, summed. Google: next departure - previous arrival. R5: transfer walks +
            waitTimes[1:].
  egress    last arrival to the destination. Google: arrival - last transit step's arrival. R5: egress.time.
  So error = Δaccess + Δwait0 + Δride + Δtransfer + Δegress, on both sides exactly the trip's seconds.
Groups by route choice (lines as transit_stop_match.py: Google's nameShort, else name; R5's short, else long name;
train lines without " line"):
  same      both board, same number of boardings, same lines in order: leg Δs are like-for-like.
  other     both board, different lines or a different number of boardings: route choice.
  mode      one side walks (Google's default has no transit step, or R5's walk call beats its transit call): left out
            of the legs, counted.

Steps (one JVM per process, P2's jar at JVM start, guarded as transit_r5_patch_walk_path.py):
  probe <release>  10 pairs of the release (first 10 by draw_no in the training table): paths out, checks F1-F3 below,
      one line per pair printed. Stop on any failure.
  route_train <release>  every training pair of the release; a row per ride and a row per pair (legs, totals),
      appended per pair; a rerun resumes.
  extract  Google's legs per scored pair from the raw records (no JVM).
  score  checks, then the report and the reading.

Checks, before any reading (stop on failure):
  (F1) R5's path totalTime = P2's saved full-run transit seconds (transit_r5_patch_connector.py route_train p2orig) on
       every pair where both have a value. The scored times are the ones decomposed.
  (F2) R5 transfer >= 0 on every pair, and = 0 on every 1-boarding path (transfer is a remainder; this is its test).
  (F3) Google's legs add up to GOOGLE_COL on every pair (seconds, exact), and Google's egress = staticDuration of the
       steps after the last transit step within GOOGLE_STEP_TOLERANCE_S (reported where not).
  Google wait0 < 0 (its walk staticDuration longer than the schedule allows) counted and reported, kept.

Report (no verdict): by group and by Google's boardings (1 / 2+): n; per leg Δ median and mean with a bootstrap 95% CI
(pairs resampled, BOOTSTRAP_REPS, fixed seed); the error's median and mean. Ride Δ also per mode (train / tram / bus by
the first vehicle). The tail: pairs with error < TAIL_S, each labelled "route choice" (group other) or by the leg with
the most negative Δ (group same); counts per label, and the tail's share of the pooled mean error. The P4 pair whose
minutes moved -46 (transit_r5_patch_walk_path_20261021_train_scored.csv, p4orig_min - p2orig_min), read alone: both
sides' legs and lines.

Reading (Claude's rule, written before any result):
  (R1) Median: in group same, a leg carries the early bias if its median Δ < 0 and its 95% CI excludes 0. If several,
       the most negative is named first. If none, the median bias is not in the legs of like-for-like pairs.
  (R2) Mean / tail: the label holding the most tail pairs names the next suspect; route choice if it is "route choice".
       Reported with the share of the pooled mean error the tail carries.
Predictions (Claude's, before any result): F1 exact (same router, same iteration); F2 holds; F3 exact on most pairs,
  Google's egress steps within a few seconds. Group same ~60% of transit pairs. Δaccess and Δegress positive (~+15-25 s
  each; WLK-6); Δride ~0 (same timetable, minute times both sides); Δwait0 negative where R5 reaches the stop at the
  second Google rounds to its minute (small); Δtransfer small (P3 matched Google's 200 s). So (R1) may name no leg, or
  wait0. Tail: mostly route choice (TRN-13: R5 rides trains from CBD stations where Google rides trams or a later
  train), so (R2) names route choice.

Conclusion (run 2026-10-21, 3,448 training pairs; rules above written before any result): F1 PASS (TTM = saved
  p2orig on 3,424 of 3,424 valued pairs, path total = TTM on 3,416 with a path; 8 street-only, no stop reached; 24
  unreached both), F2 PASS (0 negative, 0 of 2,305 one-boarding paths with a transfer), F3 PASS (0 of 3,275; Google's
  egress steps = its arrival gap on every pair; 1 negative Google wait0). Groups: same 1,754, other 1,368 (same share
  0.562), mode 326 (Google walks 173; R5 walks where Google boards 153).
  Group same: error median +2, mean -15 s. Legs (median Δ, 95% CI): access +13 (+11 to +15), wait0 -14 (-16 to -12),
  ride 0 (0 to 0; mean -11, every vehicle type alike), transfer 0, egress +5 (+4 to +7). (R1): carried by wait0.
  Group other: error median -92, mean -167 s; R5 walks more (access +150, egress +41 median), rides less (-300), waits
  less (-84), and on Google's 2+ pairs boards once where Google transfers (transfer -360 median).
  Tail (< -300 s): 394 of 3,122 both-board pairs, labels route choice 326, wait0 36, egress 12, access 10, transfer 7,
  ride 3; it carries 1.03 of the both-board error sum (mean -81 s; +3 s without it). (R2): route choice.
  Reported beside (not in the rule): the mode pairs where R5 walks and Google boards (129 valued) carry 0.42 of the
  error sum over all boarding pairs (other 0.52, same 0.06): median -147, mean -1,440 s, from Google answers of 5-6 h
  (home waits up to 20,000 s) where R5 walks about an hour. P4 pair 16425: group same (line 782), R5 and Google both
  wait ~46 min at the first stop (2,760 / 2,714 s); P4's shorter access caught the bus before, a knife-edge, not an
  artefact.
  Prediction check: checks as predicted; same share 0.56 (~0.60 predicted); access +13 and egress +5 (lower than the
  predicted +15-25 each); ride and transfer 0 as predicted; R1 named wait0 (one of the two predicted outcomes); tail
  route choice as predicted. Not predicted: the mode group's share of the mean.
  Reading (Claude's): on like-for-like pairs R5 is unbiased (median +2 s); R1's wait0 is the mirror of access (same
  vehicle: a longer walk is a shorter wait), so it is no R5 convention to patch. The early mean comes from route
  choice (R5 walks further to ride less or skip a transfer, combinations Google's default does not take) and from a
  few pairs where Google has only a very late service and R5 walks. Neither is a walk, wait or ride convention.

Follow-up, `alternatives` (no JVM; rule and predictions written 2026-10-21 before any result): does Google return
R5's line combination on the route-choice pairs (group other)? Google's routes: every route of the pair in the
routes table (default and alternatives; lines as agency:name, the name compared as norm_line). A Google route matches
when its line sequence equals R5's. Per pair, the matching route that arrives first (GOOGLE_COL) is kept.
  Classes: (a) not offered: no Google route matches; (b) offered, slower by Google's clock: the match arrives later
  than Google's default (or at the same second); (c) offered and faster by Google's clock: the match arrives earlier
  than the default, yet Google ranks the default first (a preference).
  For (b) and (c): R5's arrival - the match's arrival (s), median and mean; for (b) also the match - the default.
  Reported for all group-other pairs and for the tail's route-choice pairs, by Google's boardings (1 / 2+).
  Reading (Claude's rule): the class holding the most tail route-choice pairs names the cause: (a) Google does not
  find or keep R5's combination (its network, timetable or pruning); (b) Google times the same lines slower than R5
  (leg comparison on the matched route next); (c) Google prefers a later-arriving route (walk or transfer
  reluctance).
  Predictions (Claude's): Google's alternatives are mostly the same lines at later departures, so (a) is the largest
  class (~50%), (b) ~35%, (c) ~15%; in the tail (a) larger still; (b)'s R5 - match median within a minute.
  Conclusion (run 2026-10-21; rule above written before any result): Google returns 5.8 routes per pair (median 6).
  Group other (1,368): (a) 636, (b) 376, (c) 356. Tail route choice (326): (a) 172, (b) 55, (c) 99 -> reading (a).
  (c): R5 - match median -1 s (tail -16): R5 and Google time R5's combination alike, and Google's own clock has it
  152 s (tail 419 s) earlier than the default it ranks first. (b): R5 - match median -29 s overall, but -1,208 s in
  the tail, where the match is mostly a later departure of the same lines (match - default +488 s), so tail (b) is
  close to (a) at the requested time. No group-other pair matched Google's default (assert).
  Prediction check: (a) 46% (~50% predicted), (b) 27% (~35%), (c) 26% (~15%, under-predicted); tail (a) 53%, larger
  as predicted; (b) within a minute overall, not in the tail.
  Reading (Claude's): about half of the early tail is combinations Google does not return at all, a further ~1 in 6
  is the same lines Google only offers later, and ~3 in 10 are combinations Google returns, times as R5 does and
  ranks below a slower default (preference). The k = 2 range (TRN-13) already credits 43 of the 99 tail (c) pairs
  (R5's minute >= low_2; (a) 8 of 172, (b) 2 of 55; checked 2026-10-21 against v2's range results).

Follow-up, `combos` (no JVM; rule and predictions written 2026-10-21 before any result): what do the class (a) pairs
share, the combinations Google never returns? Question: does Google seem to apply a walk limit or walk reluctance?
  Pairs: the tail route-choice pairs (alternatives table), class (a) against (b) + (c) together; all group-other pairs
  reported beside, same split. Walks in metres on both sides (Google's own walk speed differs from R5's 4.143 km/h).
  R5: access, egress and transfer walks (transfer_walk_s, summed over transfers) as metres = s x SPEED_KMH / 3.6; this
  overstates by R5's per-edge ceil (~0.48 s per ~11.5 m edge: ~5%), so the margin below is 10%. R5's longest walk =
  the largest of the three; total walk = their sum; boardings; vehicle types (route_type: 0 tram, 2 rail, 3 bus).
  Google: every transit route of the pair in its raw record (test lines skipped unread, as extract): walk steps before
  the first transit step (access), after the last (egress), and between two transit steps (each transfer);
  distanceMeters. Per pair the envelope = the longest single walk and the longest total walk over Google's transit
  routes. Global: Google's longest single walk on any transit route of any scored training pair, p99 and max.
  Measures, (a) against (b) + (c): share where R5's longest walk > EXCEED_RATIO x the pair's single-walk envelope
  ("beyond Google's walks"); the same for total walk; share above Google's global p99 single walk; medians of R5's
  walks and Google's envelope; R5 boardings - Google default boardings; R5 vehicle mix.
  Reading (Claude's rule): (W1) walk reluctance or limit is consistent if in (a) the share beyond Google's walks (longest
  or total) >= 0.5 and >= 0.2 above (b) + (c)'s. (W2) a global cap if, in addition, >= 0.3 of (a) is above Google's
  global p99 and <= 0.05 of (b) + (c) is; else pair-relative (reluctance or ranking), not a cap. If W1 fails, no walk
  reading; the largest (a) vs (b) + (c) difference among the other measures is reported, no verdict.
  Predictions (Claude's): R5 beyond Google's walks in ~60% of (a), ~30% of (b) + (c): W1 holds; Google walks long
  somewhere (global p99 > 1.5 km), so W2 fails: reluctance, not a cap. (a) boards fewer than Google's default.
  Conclusion (run 2026-10-21; rule above written before any result): Google's transit routes (19,336 on 3,327 pairs):
  longest single walk median 489 m, p99 1,974 m, max 12,061 m. Tail route choice: beyond Google's walks (a) 0.40 vs
  (b) + (c) 0.19 (gap 0.21 passes, share fails the 0.5 line) -> W1: no walk reading; above global p99 (a) 0.05 vs
  0.02 -> not a cap. R5's longest walk / Google's envelope median 0.90 in (a), 0.86 in (b) + (c): R5's walks mostly
  sit inside what Google walks on the same pair. Other measures differ little: boards one fewer than Google's default
  (a) 0.30 vs 0.22, one more 0.20 vs 0.16; trams in (a) slightly more often. On all group-other pairs the walk gap is
  wider ((a) 0.53 vs 0.18).
  Prediction check: (a) 0.40 (~0.60 predicted), (b) + (c) 0.19 (~0.30); W1 predicted to hold, failed; W2 failed as
  predicted (p99 1,974 m); (a) boarding fewer: partly (0.30), not the rule.
  Reading (Claude's): a walk beyond Google's own explains at most ~2 in 5 of the never-returned tail; there is no hard
  walk cap, and the rest is not walk length, boardings or vehicle type. What remains looks like Google's search or
  pruning not reaching R5's combination: a stated limitation (R5 = fastest feasible trip), not an R5 convention.

Follow-up, `railtram` (no JVM; rule and predictions written 2026-10-21 before any result; user OK to start here):
the tail's most common route-choice pattern is R5 riding a train where Google's default rides a tram (71 of 326 by a
quick count). Station time or preference? Google charges more in-station time than the feed at some stations
(TRN-13 station fidelity), or Google prefers the tram (ranking).
  Pairs: tail route-choice pairs (combos table) with R5 vehicles = rail only and Google's default = tram only
  (set RT); reported beside: R5 rides rail and Google's default no rail (set RX, RT included).
  Per pair: does Google return R5's lines (alternatives class, (a) not)? does it return any route with a train
  (vehicle_types holds HEAVY_RAIL)? For the match (the first-arriving Google route with R5's lines, as alternatives),
  Google's legs from its raw record as extract (access, wait0, ride, transfer, egress), against R5's legs:
  delta = R5 - Google match, in seconds; R5's train walks include v2's in-station pathway spurs, so both sides count
  station time.
  Reading (Claude's rule), on RT's matched pairs (classes b and c):
    (S) station time: median delta(access + egress) <= -STATION_DELTA_S with its bootstrap 95% CI below 0: Google
        charges more walking at the train's ends than R5.
    (T) timing elsewhere: |median total delta (R5 - match arrival)| > STATION_DELTA_S and S fails: the leg with the
        largest |median delta| is named.
    (P) preference: |median total delta| <= STATION_DELTA_S: Google times R5's train trip as R5 does; picking the
        tram is ranking. S and P can both hold (station time offset elsewhere).
  Unmatched RT pairs (class a): share with any Google train route, and that route's arrival vs R5's (reported).
  Predictions (Claude's): about half of RT matched; S holds (Google's train-end walks ~60-120 s longer, CBD
  stations); total delta median about -1 min in class b and ~0 in class c, so P holds in class c only.
  Conclusion (run 2026-10-21; rule above written before any result): check PASS (matched legs sum to the arrival).
  RT 71: classes (a) 34, (b) 4, (c) 33; a Google train route of some kind on 0.90 (on 27 unmatched, R5 is 491 s
  earlier than Google's first train route, median). Matched 37: access +7, wait0 -30, ride 0, transfer 0, egress +8,
  ends +19 (CI -16 to +46), total -6 s (-20 to +12) -> S fails, P holds: Google times R5's train trip as R5 does and
  charges no extra station time. RX 144 the same (ends +1, total -19).
  Reported after the rule (not in it): on RT class (c) (33), Google's own train route arrives 452 s earlier than its
  tram default (median; quartiles 354-525) but walks 1,191 s at its ends against the tram's 430 s (median): Google gives
  up ~7.5 min of arrival to walk ~12.7 min less.
  Prediction check: matched 37 of 71 (about half, as predicted); S predicted to hold, failed; P held in class c, as
  predicted, and pooled too.
  Reading (Claude's): no station time. "Train vs tram" is Google's ranking trading arrival time for less walking
  (walk reluctance, revealed on Google's own routes); combos missed it because the train route's walk sits inside
  Google's own envelope by construction. A rough bound, not fitted: picking the tram means a walk minute costs Google
  more than ~1.6 minutes of arrival on these pairs (452 / 761 s, medians).

Inputs (read only): P2's jar and saved full training run, v2 networks and feeds, v2's range results, Google's raw
records and route tables in outputs/transit_validation/. Writes tables to diagnostics/diagnostic_data/. Self-contained
(CLAUDE.md D1). No paid API calls. Usage: `python transit_leg_error.py probe <release>`, `... route_train <release>`,
`... extract`, `... score`.
"""
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
PATCH_DIR = PROJECT_ROOT / "outputs" / "r5_patches"
P2_NAME = "transit_r5_patch_connector"
JAR_PATH = PATCH_DIR / f"r5-v7.5.1-r5py-all_{P2_NAME}_p2.jar"   # the model of record (P1 + P3 + P2)
P2_TRAIN_GLOB = f"{P2_NAME}_2*_trainroutes_p2orig_{{release}}.csv"
V2_NAME = "transit_pathway_network_v2"
RANGE_RESULTS_GLOB = f"{V2_NAME}_2*_range_owndate_results.csv"
NAME = "transit_leg_error"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
GOOGLE_RAW_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl",        # holds the test half too: skipped
                    "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.raw.jsonl",
                    "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.raw.jsonl"}
GOOGLE_ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",
                       "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                       "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
GOOGLE_COL = "arrival_from_request_s"          # the scorers' Google quantity (transit_fetch.py google_min)

# --- routing (as transit_r5_patch_connector.py's training run) ---------------------------------------
GUARD_CLASSES = ["com.conveyal.r5.streets.EdgeStore$Edge", "com.conveyal.r5.streets.StreetRouter",
                 "com.conveyal.r5.streets.LinkedPointSet", "com.conveyal.r5.profile.FastRaptorWorker",
                 "com.conveyal.r5.analyst.TravelTimeComputer"]
RELEASES = ["20261009", "20261016"]
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
TRAIN_FEED = "ptv_metro_train"
SPEED_KMH = 4.143                              # Q24 (2) median; user 2026-10-21
MAX_TIME_MIN = 90
WINDOW_MIN = 1
SINGLE_PERCENTILE = 49
R5_MAX_MEMORY = "7G"
R5_UNREACHED = 2 ** 31 - 1                     # R5's Integer.MAX_VALUE for no path
PROBE_N_PAIRS = 10
STREET_ONLY = -1                               # n_templates when R5 reached no stop (no PathResult entry)
PROGRESS_EVERY = 250

# --- legs ------------------------------------------------------------------------------------------
TAIL_S = -300                                  # the early tail: error below -5 min (user OK 2026-10-21)
BOOTSTRAP_REPS = 2000
BOOTSTRAP_SEED = 20261021
GOOGLE_STEP_TOLERANCE_S = 2                    # (F3) Google's egress steps vs its arrival gap
LEGS = ["access", "wait0", "ride", "transfer", "egress"]
LINE_SUFFIX = " line"
EXCEED_RATIO = 1.10                            # (combos) R5 walk beyond Google's envelope: covers R5's ~5% edge ceil
W1_SHARE, W1_GAP = 0.5, 0.2                    # (combos) W1: share in (a), and its lead over (b) + (c)
W2_SHARE_A, W2_SHARE_REST = 0.3, 0.05          # (combos) W2: shares above Google's global p99 single walk
GLOBAL_QUANTILE = 0.99
R5_VEHICLES = {0: "tram", 2: "rail", 3: "bus", 400: "rail"}  # GTFS route_type (400: extended, urban railway)
GOOGLE_VEHICLES = {"TRAM": "tram", "BUS": "bus", "HEAVY_RAIL": "rail"}
GOOGLE_RAIL = "HEAVY_RAIL"
STATION_DELTA_S = 60                           # (railtram) S and P threshold on median deltas
P4_PAIR = 16425                                # P4's -46 min pair (transit_r5_patch_walk_path_20261021_train_scored.csv)


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def training_pairs(release):
    pairs_df = pd.read_csv(newest(RANGE_RESULTS_GLOB))
    pairs_df = pairs_df[pairs_df.is_scored.astype(bool) & (pairs_df.release.astype(str) == release)]
    return pairs_df.sort_values("draw_no")


# --- R5 paths --------------------------------------------------------------------------------------
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
    """Start the JVM on the model of record's jar (guarded), load the release's v2 network; returns path_of(origin,
    destination, departure) -> (pair legs dict, ride rows)."""
    assert JAR_PATH.exists(), f"{JAR_PATH.name} missing (transit_r5_patch_connector.py build)"
    sys.argv += ["--max-memory", R5_MAX_MEMORY, "--r5-classpath", str(JAR_PATH)]   # r5py reads these at import
    import geopandas as gpd
    import jpype
    import shapely
    from r5py import RegionalTask, TransportMode, TransportNetwork
    import com.conveyal.r5  # noqa: F401  (importable once r5py has started the JVM)
    for name in GUARD_CLASSES:
        location = str(jpype.JClass(name).class_.getProtectionDomain().getCodeSource().getLocation().toURI())
        assert Path(location.removeprefix("file:/")).resolve() == JAR_PATH.resolve(), f"{name} loaded from {location}"
    print(f"{', '.join(c.rsplit('.', 1)[1] for c in GUARD_CLASSES)} from {JAR_PATH.name}", flush=True)
    pbf_path, gtfs = network_paths(release)
    assert pbf_path.exists() and all(p.exists() for p in gtfs), "transit_pathway_network_v2 build / feeds first"
    check_working_copies([pbf_path] + gtfs)
    print(f"reusing {pbf_path.name} and {[p.name for p in gtfs]}", flush=True)
    network = TransportNetwork(pbf_path, gtfs)
    transit_layer = network._transport_network.transitLayer
    computer_class = jpype.JClass("com.conveyal.r5.analyst.TravelTimeComputer")

    def route_name(route_ix):
        route = transit_layer.routes.get(route_ix)
        short = str(route.route_short_name) if route.route_short_name is not None else ""
        return (short if short else str(route.route_long_name or "")), int(route.route_type)

    def path_of(origin, destination, departure):
        """One TTM call as the scored run's transit call (r5py's TravelTimeMatrix settings), paths kept."""
        destinations = gpd.GeoDataFrame({"id": [1]}, crs="EPSG:4326",
                                        geometry=gpd.points_from_xy([destination[1]], [destination[0]]))
        request = RegionalTask(
            network, origin=shapely.Point(origin[1], origin[0]), destinations=destinations, departure=departure,
            departure_time_window=datetime.timedelta(minutes=WINDOW_MIN), percentiles=[SINGLE_PERCENTILE],
            transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
            max_time=datetime.timedelta(minutes=MAX_TIME_MIN), speed_walking=SPEED_KMH)
        request._regional_task.includePathResults = True
        result = computer_class(request, network).computeTravelTimes()
        ttm_s = int(result.travelTimes.getValues()[0][0])
        templates = result.paths.iterationsForPathTemplates[0]
        rides = []
        if templates is None:   # no stop reached: R5's street-only branch records no path (a direct walk, or unreached)
            return {"ttm_s": np.nan if ttm_s == R5_UNREACHED else ttm_s, "n_templates": STREET_ONLY,
                    "n_boardings": 0}, rides
        legs = {"ttm_s": np.nan if ttm_s == R5_UNREACHED else ttm_s, "n_templates": int(templates.size())}
        if templates.size() != 1:
            return legs, rides
        entry = list(templates.entries())[0]
        sequence, iteration = entry.getKey(), entry.getValue()
        stops = sequence.stopSequence
        legs.update({"iteration_s": int(iteration.totalTime), "iteration_departure": int(iteration.departureTime)})
        if stops.rideTimesSeconds is None:                     # no transit: the direct walk won
            legs["n_boardings"] = 0
            return legs, rides
        waits = [int(w) for w in iteration.waitTimes.toArray()]
        ride_s = [int(r) for r in stops.rideTimesSeconds.toArray()]
        legs.update({"n_boardings": len(ride_s), "access_s": int(stops.access.time), "egress_s": int(stops.egress.time),
                     "wait0_s": waits[0], "waits_rest_s": sum(waits[1:]), "ride_s": sum(ride_s)})
        legs["transfer_walk_s"] = (legs["iteration_s"] - legs["access_s"] - legs["egress_s"] - sum(waits) - sum(ride_s))
        for k in range(len(ride_s)):
            line, route_type = route_name(sequence.routes.get(k))
            board, alight = stops.boardStops.get(k), stops.alightStops.get(k)
            rides.append({"ride_no": k, "line": line, "route_type": route_type, "wait_s": waits[k], "ride_s": ride_s[k],
                          "board_stop": str(transit_layer.stopNames.get(board)),
                          "alight_stop": str(transit_layer.stopNames.get(alight))})
        return legs, rides

    return path_of


def departure_of(pair):
    return (datetime.datetime.combine(datetime.date.fromisoformat(str(pair.own_date)), datetime.time())
            + datetime.timedelta(minutes=int(pair.dep_min_of_day)))


def r5_checks(legs_df, release):
    """(F1) path total = TTM value = P2's saved full-run transit seconds; (F2) transfer walk >= 0, 0 on 1 boarding."""
    saved_df = pd.read_csv(newest(P2_TRAIN_GLOB.format(release=release)))[["draw_no", "transit"]]
    merged = legs_df.merge(saved_df, on="draw_no", how="left", validate="one_to_one")
    has_value = merged.transit.notna() | merged.ttm_s.notna()
    has_path = has_value & (merged.n_templates != STREET_ONLY)
    f1_ttm = (merged.ttm_s[has_value] == merged.transit[has_value])
    f1_iter = (merged.iteration_s[has_path] == merged.ttm_s[has_path])
    boarded = merged[merged.n_boardings.fillna(0) > 0]
    f2_neg = int((boarded.transfer_walk_s < 0).sum())
    f2_one = int((boarded[boarded.n_boardings == 1].transfer_walk_s != 0).sum())
    lines = [f"(F1) TTM value = saved p2orig transit: {int(f1_ttm.sum())}/{len(f1_ttm)} "
             f"({'PASS' if f1_ttm.all() else 'FAIL'}); path total = TTM value: {int(f1_iter.sum())}/{len(f1_iter)} "
             f"({'PASS' if f1_iter.all() else 'FAIL'}); reached pairs without exactly one path: "
             f"{int((merged.n_templates[has_path] != 1).sum())}; street-only (no stop reached): "
             f"{int((merged.n_templates[has_value] == STREET_ONLY).sum())}; unreached (both NaN): {int((~has_value).sum())}",
             f"(F2) transfer walk < 0: {f2_neg}; != 0 on 1-boarding paths: {f2_one} of "
             f"{int((boarded.n_boardings == 1).sum())} ({'PASS' if f2_neg == 0 and f2_one == 0 else 'FAIL'})"]
    is_ok = f1_ttm.all() and f1_iter.all() and (merged.n_templates[has_path] == 1).all() and f2_neg == 0 and f2_one == 0
    return lines, is_ok


def probe(release):
    """10 pairs: paths out, F1 and F2, one line per pair (docstring)."""
    assert release in RELEASES
    pairs_df = training_pairs(release).head(PROBE_N_PAIRS)
    path_of = open_network(release)
    rows = []
    for pair in pairs_df.itertuples():
        legs, rides = path_of((pair.origin_lat, pair.origin_lon), (pair.dest_lat, pair.dest_lon), departure_of(pair))
        rows.append({"draw_no": pair.draw_no, **legs})
        print(f"  {pair.draw_no}: {legs}; lines {[r['line'] for r in rides]}", flush=True)
    lines, is_ok = r5_checks(pd.DataFrame(rows), release)
    text = "\n".join([f"{NAME} {run_date()} probe {release}: {len(rows)} pairs, jar {JAR_PATH.name}"] + lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_probe_{release}.txt").write_text(text + "\n", encoding="utf-8",
                                                                                   newline="\n")
    assert is_ok, "probe check failed: stop"


# --- Google legs (no JVM) --------------------------------------------------------------------------
def seconds_of(duration):
    return int(duration.rstrip("s"))


def utc_of(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def extract():
    """Google's default route per scored training pair, leg by leg (docstring); test-half lines skipped unread."""
    saved = newest(f"{NAME}_2*_googlelegs.csv")
    if saved is not None:
        print(f"reusing {saved.name} ({datetime.date.fromtimestamp(saved.stat().st_mtime)})")
        return
    pairs_df = pd.read_csv(newest(RANGE_RESULTS_GLOB))
    pairs_df = pairs_df[pairs_df.is_scored.astype(bool)].set_index("draw_no")
    legs_rows, ride_rows = [], []
    for set_name, raw_path in GOOGLE_RAW_PATHS.items():
        routes_df = pd.read_csv(GOOGLE_ROUTES_PATHS[set_name])
        default_df = routes_df[routes_df.is_default].drop_duplicates("draw_no").set_index("draw_no")
        wanted = set(pairs_df.index[pairs_df.set_name == set_name])
        with open(raw_path, encoding="utf-8") as file:
            for line in file:
                draw_no = int(line[line.index(":") + 1:line.index(",")])   # read the id before parsing: test lines skipped
                if draw_no not in wanted:
                    continue
                record = json.loads(line)
                assert record["draw_no"] == draw_no
                default = default_df.loc[draw_no]
                requested = utc_of(record["request"]["departureTime"])
                steps = record["resp"]["routes"][int(default.route_ix)]["legs"][0]["steps"]
                transit_ix = [i for i, step in enumerate(steps) if step["travelMode"] == "TRANSIT"]
                row = {"draw_no": draw_no, "set_name": set_name, "g_total_s": float(default[GOOGLE_COL]),
                       "g_n_boardings": len(transit_ix)}
                if transit_ix:
                    rides = []
                    for k, i in enumerate(transit_ix):
                        details = steps[i]["transitDetails"]
                        transit_line = details["transitLine"]
                        stop_details = details["stopDetails"]
                        rides.append({"draw_no": draw_no, "ride_no": k,
                                      "line": transit_line.get("nameShort") or transit_line.get("name", ""),
                                      "vehicle": transit_line.get("vehicle", {}).get("type", ""),
                                      "board_stop": stop_details["departureStop"].get("name", ""),
                                      "alight_stop": stop_details["arrivalStop"].get("name", ""),
                                      "departure_s": (utc_of(stop_details["departureTime"]) - requested).total_seconds(),
                                      "arrival_s": (utc_of(stop_details["arrivalTime"]) - requested).total_seconds()})
                    access_s = sum(seconds_of(step["staticDuration"]) for step in steps[:transit_ix[0]])
                    row.update({"g_access_s": access_s, "g_wait0_s": rides[0]["departure_s"] - access_s,
                                "g_ride_s": sum(r["arrival_s"] - r["departure_s"] for r in rides),
                                "g_transfer_s": sum(b["departure_s"] - a["arrival_s"] for a, b in zip(rides, rides[1:])),
                                "g_egress_s": row["g_total_s"] - rides[-1]["arrival_s"],
                                "g_egress_steps_s": sum(seconds_of(step["staticDuration"]) for step in steps[transit_ix[-1] + 1:])})
                    ride_rows += rides
                legs_rows.append(row)
    legs_df = pd.DataFrame(legs_rows)
    missing = len(pairs_df) - len(legs_df)
    assert missing == 0, f"{missing} scored pairs without a Google answer"
    path = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_googlelegs.csv"
    legs_df.to_csv(path, index=False)
    pd.DataFrame(ride_rows).to_csv(path.with_name(path.name.replace("_googlelegs", "_googlerides")), index=False)
    print(f"{len(legs_df)} pairs -> {path.name}; boardings {legs_df.g_n_boardings.value_counts().sort_index().to_dict()}")


def route_train(release):
    """Every training pair of the release: a row per pair (legs) and per ride, appended per pair; resumes."""
    assert release in RELEASES
    pairs_df = training_pairs(release)
    saved = newest(f"{NAME}_2*_trainlegs_{release}.csv")
    legs_path = saved if saved is not None else DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_trainlegs_{release}.csv"
    rides_path = legs_path.with_name(legs_path.name.replace("_trainlegs_", "_trainrides_"))
    done = set(pd.read_csv(legs_path).draw_no) if legs_path.exists() else set()
    if rides_path.exists():   # a stopped run can leave rides of a pair whose legs row was not written: drop them
        rides_df = pd.read_csv(rides_path)
        rides_df[rides_df.draw_no.isin(done)].to_csv(rides_path, index=False)
    todo_df = pairs_df[~pairs_df.draw_no.isin(done)]
    print(f"{release}: {len(pairs_df)} pairs, {len(done)} done, {len(todo_df)} to route -> {legs_path.name}", flush=True)
    path_of = open_network(release)
    legs_columns = ["draw_no", "release", "ttm_s", "n_templates", "iteration_s", "iteration_departure", "n_boardings",
                    "access_s", "egress_s", "wait0_s", "waits_rest_s", "ride_s", "transfer_walk_s"]
    started = datetime.datetime.now()
    for i, pair in enumerate(todo_df.itertuples()):
        legs, rides = path_of((pair.origin_lat, pair.origin_lon), (pair.dest_lat, pair.dest_lon), departure_of(pair))
        if rides:   # rides first: a pair counts as done only once its legs row is written
            pd.DataFrame([{"draw_no": pair.draw_no, **ride} for ride in rides]).to_csv(
                rides_path, mode="a", header=not rides_path.exists(), index=False)
        pd.DataFrame([{"draw_no": pair.draw_no, "release": release, **legs}], columns=legs_columns).to_csv(
            legs_path, mode="a", header=not legs_path.exists(), index=False)
        if i % PROGRESS_EVERY == 0:
            print(f"  {i + 1}/{len(todo_df)} after {datetime.datetime.now() - started}", flush=True)
    print(f"done: {len(todo_df)} pairs in {datetime.datetime.now() - started}", flush=True)
    lines, is_ok = r5_checks(pd.read_csv(legs_path), release)
    print("\n".join(lines), flush=True)


# --- score -----------------------------------------------------------------------------------------
def norm_line(line):
    """Lines as transit_stop_match.py: train lines without " line"; case and spaces ignored."""
    text = str(line).strip().lower()
    return text[:-len(LINE_SUFFIX)] if text.endswith(LINE_SUFFIX) else text


def line_sequences(rides_df):
    return rides_df.sort_values(["draw_no", "ride_no"]).groupby("draw_no").line.agg(
        lambda lines: "|".join(norm_line(x) for x in lines))


def bootstrap_ci(values, statistic, rng):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return np.nan, np.nan
    draws = rng.integers(0, len(values), size=(BOOTSTRAP_REPS, len(values)))
    stats = statistic(values[draws], axis=1)
    return tuple(np.quantile(stats, [0.025, 0.975]))


def leg_lines(frame, label, rng):
    lines = [f"  {label}: n {len(frame)}; error median {frame.error_s.median():+.0f}, mean {frame.error_s.mean():+.1f} s"]
    for leg in LEGS:
        delta = frame[f"d_{leg}"]
        lo_med, hi_med = bootstrap_ci(delta, np.median, rng)
        lo_mean, hi_mean = bootstrap_ci(delta, np.mean, rng)
        lines.append(f"    {leg:9s} median {delta.median():+6.0f} (95% {lo_med:+.0f} to {hi_med:+.0f}), mean {delta.mean():+7.1f} "
                     f"(95% {lo_mean:+.1f} to {hi_mean:+.1f}); R5 median {frame[f'r_{leg}'].median():.0f}, "
                     f"Google {frame[f'g_{leg}'].median():.0f}")
    return lines


def score():
    """Checks, report and reading (docstring)."""
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    lines = [f"{NAME} {run_date()}: leg-by-leg error to Google (rules in the docstring, set before results)"]
    legs_parts, rides_parts, is_ok = [], [], True
    for release in RELEASES:
        legs_path = newest(f"{NAME}_2*_trainlegs_{release}.csv")
        release_df = pd.read_csv(legs_path)
        assert len(release_df) == len(training_pairs(release)), f"{release}: route_train not finished"
        check_lines, release_ok = r5_checks(release_df, release)
        lines += [f"{release} ({legs_path.name}):"] + ["  " + line for line in check_lines]
        is_ok &= release_ok
        walk_df = pd.read_csv(newest(P2_TRAIN_GLOB.format(release=release)))[["draw_no", "walk"]]
        legs_parts.append(release_df.merge(walk_df, on="draw_no", validate="one_to_one"))
        rides_parts.append(pd.read_csv(legs_path.with_name(legs_path.name.replace("_trainlegs_", "_trainrides_"))))
    r5_df = pd.concat(legs_parts, ignore_index=True)
    r5_rides_df = pd.concat(rides_parts, ignore_index=True)
    google_path = newest(f"{NAME}_2*_googlelegs.csv")
    google_df = pd.read_csv(google_path)
    google_rides_df = pd.read_csv(google_path.with_name(google_path.name.replace("_googlelegs", "_googlerides")))
    lines.append(f"reusing {google_path.name}")

    # (F3) Google's legs
    boards_df = google_df[google_df.g_n_boardings > 0]
    leg_sum = boards_df[[f"g_{leg}_s" for leg in LEGS]].sum(axis=1)
    f3_sum = int((leg_sum != boards_df.g_total_s).sum())
    egress_gap = (boards_df.g_egress_s - boards_df.g_egress_steps_s).abs()
    f3_steps = int((egress_gap > GOOGLE_STEP_TOLERANCE_S).sum())
    lines.append(f"(F3) Google legs sum != {GOOGLE_COL}: {f3_sum} of {len(boards_df)} ({'PASS' if f3_sum == 0 else 'FAIL'}); "
                 f"egress gap vs its steps > {GOOGLE_STEP_TOLERANCE_S} s: {f3_steps} (reported; median "
                 f"{egress_gap.median():.0f} s, max {egress_gap.max():.0f} s); Google wait0 < 0: "
                 f"{int((boards_df.g_wait0_s < 0).sum())} (kept)")
    is_ok &= f3_sum == 0
    if not is_ok:
        print("\n".join(lines))
        raise SystemExit("a check failed: stop")

    # groups
    df = r5_df.merge(google_df, on="draw_no", validate="one_to_one")
    df["r_total_s"] = df[["ttm_s", "walk"]].min(axis=1)
    is_r5_transit = df.n_boardings.fillna(0).gt(0) & (df.walk.isna() | (df.ttm_s < df.walk))
    df["group"] = np.where(~is_r5_transit | (df.g_n_boardings == 0), "mode", "other")
    df["r_lines"] = df.draw_no.map(line_sequences(r5_rides_df))
    df["g_lines"] = df.draw_no.map(line_sequences(google_rides_df))
    df.loc[(df.group == "other") & (df.r_lines == df.g_lines), "group"] = "same"
    df["error_s"] = df.r_total_s - df.g_total_s
    df["r_access"], df["r_wait0"], df["r_ride"] = df.access_s, df.wait0_s, df.ride_s
    df["r_transfer"], df["r_egress"] = df.transfer_walk_s + df.waits_rest_s, df.egress_s
    for leg in LEGS:
        df[f"g_{leg}"] = df[f"g_{leg}_s"]
        df[f"d_{leg}"] = df[f"r_{leg}"] - df[f"g_{leg}"]
    df["boardings"] = np.where(df.g_n_boardings >= 2, "2+", df.g_n_boardings.astype(str))
    first_vehicle = google_rides_df[google_rides_df.ride_no == 0].set_index("draw_no").vehicle
    df["first_vehicle"] = df.draw_no.map(first_vehicle)

    transit_df = df[df.group != "mode"]
    mode_df = df[df.group == "mode"]
    lines.append(f"pairs {len(df)}: groups {df.group.value_counts().to_dict()}; same share of both-board pairs "
                 f"{(transit_df.group == 'same').mean():.3f}")
    lines.append(f"  mode group: Google walks {int((mode_df.g_n_boardings == 0).sum())}, R5 walks where Google boards "
                 f"{int(((mode_df.g_n_boardings > 0)).sum())} (error median "
                 f"{mode_df[mode_df.g_n_boardings > 0].error_s.median():+.0f}, mean "
                 f"{mode_df[mode_df.g_n_boardings > 0].error_s.mean():+.1f} s)")
    check_df = df[df.g_n_boardings > 0]
    lines.append("  check, seconds error by Google's boardings (all pairs with a model value, as P4's score_train): "
                 + "; ".join(f"{b} median {g.error_s.median():+.0f} mean {g.error_s.mean():+.1f}"
                             for b, g in check_df.groupby("boardings")))

    lines.append("legs, delta = R5 - Google (s), bootstrap 95% CIs:")
    for group in ["same", "other"]:
        group_df = transit_df[transit_df.group == group]
        lines += leg_lines(group_df, f"{group}, pooled", rng)
        for boardings, sub in group_df.groupby("boardings"):
            lines += leg_lines(sub, f"{group}, Google boardings {boardings}", rng)
    lines.append("ride delta by Google's first vehicle (group same):")
    for vehicle, sub in transit_df[transit_df.group == "same"].groupby("first_vehicle"):
        lines.append(f"  {vehicle}: n {len(sub)}, median {sub.d_ride.median():+.0f}, mean {sub.d_ride.mean():+.1f} s")

    # tail
    tail_df = transit_df[transit_df.error_s < TAIL_S].copy()
    deltas = tail_df[[f"d_{leg}" for leg in LEGS]]
    tail_df["label"] = np.where(tail_df.group == "other", "route choice", deltas.idxmin(axis=1).str[2:])
    tail_share = tail_df.error_s.sum() / transit_df.error_s.sum()
    lines.append(f"tail (error < {TAIL_S} s): n {len(tail_df)} of {len(transit_df)}; labels "
                 f"{tail_df.label.value_counts().to_dict()}; share of the both-board error sum {tail_share:.3f} "
                 f"(both-board mean {transit_df.error_s.mean():+.1f}, without the tail "
                 f"{transit_df[transit_df.error_s >= TAIL_S].error_s.mean():+.1f} s)")
    lines.append(f"  tail by Google's boardings: {tail_df.boardings.value_counts().to_dict()}; by group "
                 f"{tail_df.group.value_counts().to_dict()}")

    # the P4 pair, read alone
    pair = df[df.draw_no == P4_PAIR]
    if len(pair):
        row = pair.iloc[0]
        lines.append(f"P4 pair {P4_PAIR}: group {row.group}; R5 transit {row.ttm_s} s, walk {row.walk} s; Google "
                     f"{row.g_total_s:.0f} s; R5 lines {row.r_lines}; Google lines {row.g_lines}; "
                     + ", ".join(f"{leg} R5 {row[f'r_{leg}']} / G {row[f'g_{leg}']}" for leg in LEGS))

    # reading
    same_df = transit_df[transit_df.group == "same"]
    carriers = []
    for leg in LEGS:
        lo, hi = bootstrap_ci(same_df[f"d_{leg}"], np.median, np.random.default_rng(BOOTSTRAP_SEED))
        if same_df[f"d_{leg}"].median() < 0 and hi < 0:
            carriers.append((same_df[f"d_{leg}"].median(), leg))
    lines.append("READING (R1, group same, median): " + (
        "carried by " + ", ".join(f"{leg} ({m:+.0f} s)" for m, leg in sorted(carriers)) if carriers
        else "no leg carries the median early bias"))
    top = tail_df.label.value_counts()
    lines.append(f"READING (R2, tail): next suspect {top.index[0] if len(top) else 'none'} "
                 f"({top.iloc[0] if len(top) else 0} of {len(tail_df)}); tail share of the error sum {tail_share:.3f}")

    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_score.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_scored.csv", index=False)


def google_line_sequence(lines):
    """A routes-table `lines` cell (agency:name|...) as norm_line names joined by |; '' for a walk-only route."""
    if not isinstance(lines, str) or not lines:
        return ""
    return "|".join(norm_line(item.split(":", 1)[-1]) for item in lines.split("|"))


def alternatives():
    """Does Google return R5's line combination on the route-choice pairs? (docstring, follow-up)"""
    scored_path = newest(f"{NAME}_2*_scored.csv")
    df = pd.read_csv(scored_path)
    lines = [f"{NAME} {run_date()} alternatives: reusing {scored_path.name}"]
    routes_df = pd.concat([pd.read_csv(path) for path in GOOGLE_ROUTES_PATHS.values()], ignore_index=True)
    routes_df = routes_df[routes_df.draw_no.isin(set(df.draw_no))].copy()
    routes_df["seq"] = routes_df.lines.map(google_line_sequence)
    lines.append(f"Google routes per pair: {routes_df.groupby('draw_no').size().describe()[['mean', '50%']].round(2).to_dict()}")
    other_df = df[df.group == "other"].copy()
    tail_ids = set(other_df.draw_no[other_df.error_s < TAIL_S])
    matched = routes_df.merge(other_df[["draw_no", "r_lines"]], on="draw_no")
    matched = matched[matched.seq == matched.r_lines]
    first_match = matched.groupby("draw_no")[GOOGLE_COL].min()
    n_matching_routes = matched.groupby("draw_no").size()
    other_df["match_s"] = other_df.draw_no.map(first_match)
    other_df["match_is_default"] = other_df.draw_no.map(
        matched[matched.is_default].drop_duplicates("draw_no").set_index("draw_no").is_default).fillna(False)
    other_df["cls"] = np.where(other_df.match_s.isna(), "a not offered",
                               np.where(other_df.match_s >= other_df.g_total_s, "b offered, slower", "c offered, faster"))
    other_df["r5_minus_match"] = other_df.r_total_s - other_df.match_s
    other_df["match_minus_default"] = other_df.match_s - other_df.g_total_s
    assert not other_df.match_is_default.any(), "a group-other pair matched Google's default: grouping differs"
    for label, sub in [("group other, all", other_df), ("tail route choice", other_df[other_df.draw_no.isin(tail_ids)])]:
        lines.append(f"{label}: n {len(sub)}; classes {sub.cls.value_counts().sort_index().to_dict()}")
        for boardings, part in sub.groupby("boardings"):
            lines.append(f"  Google boardings {boardings}: n {len(part)}; {part.cls.value_counts().sort_index().to_dict()}")
        for cls, part in sub[sub.cls != "a not offered"].groupby("cls"):
            lines.append(f"  {cls}: R5 - match median {part.r5_minus_match.median():+.0f}, mean "
                         f"{part.r5_minus_match.mean():+.1f} s; match - default median {part.match_minus_default.median():+.0f}, "
                         f"mean {part.match_minus_default.mean():+.1f} s; matching Google routes per pair median "
                         f"{part.draw_no.map(n_matching_routes).median():.0f}")
    tail_counts = other_df[other_df.draw_no.isin(tail_ids)].cls.value_counts()
    lines.append(f"READING (tail route choice): {tail_counts.index[0]} ({tail_counts.iloc[0]} of {tail_counts.sum()})")
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_alternatives.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    other_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_alternatives.csv", index=False)


def google_walks(wanted):
    """Per scored pair, per Google transit route: access, egress, longest transfer and total walk (m), from raw records."""
    rows = []
    for raw_path in GOOGLE_RAW_PATHS.values():
        with open(raw_path, encoding="utf-8") as file:
            for line in file:
                draw_no = int(line[line.index(":") + 1:line.index(",")])   # read the id before parsing: test lines skipped
                if draw_no not in wanted:
                    continue
                record = json.loads(line)
                for route_ix, route in enumerate(record["resp"].get("routes", [])):
                    steps = route["legs"][0]["steps"]
                    transit_ix = [i for i, step in enumerate(steps) if step["travelMode"] == "TRANSIT"]
                    if not transit_ix:
                        continue
                    walk_m = [step.get("distanceMeters", 0) if step["travelMode"] == "WALK" else 0 for step in steps]
                    transfers = [sum(walk_m[a + 1:b]) for a, b in zip(transit_ix, transit_ix[1:])]
                    rows.append({"draw_no": draw_no, "route_ix": route_ix, "n_boardings": len(transit_ix),
                                 "access_m": sum(walk_m[:transit_ix[0]]), "egress_m": sum(walk_m[transit_ix[-1] + 1:]),
                                 "transfer_max_m": max(transfers, default=0), "total_m": sum(walk_m)})
    walks_df = pd.DataFrame(rows)
    walks_df["longest_m"] = walks_df[["access_m", "egress_m", "transfer_max_m"]].max(axis=1)
    return walks_df


def combos():
    """What do the never-returned combinations share? (docstring, follow-up `combos`)"""
    alt_path = newest(f"{NAME}_2*_alternatives.csv")
    other_df = pd.read_csv(alt_path)
    scored_df = pd.read_csv(newest(f"{NAME}_2*_scored.csv"))
    lines = [f"{NAME} {run_date()} combos: reusing {alt_path.name}"]
    walks_df = google_walks(set(scored_df.draw_no))
    envelope_df = walks_df.groupby("draw_no").agg(g_env_longest_m=("longest_m", "max"), g_env_total_m=("total_m", "max"))
    global_p99 = walks_df.longest_m.quantile(GLOBAL_QUANTILE)
    lines.append(f"Google transit routes read: {len(walks_df)} on {walks_df.draw_no.nunique()} pairs; longest single walk "
                 f"median {walks_df.longest_m.median():.0f} m, p99 {global_p99:.0f} m, max {walks_df.longest_m.max():.0f} m")
    metres_per_s = SPEED_KMH / 3.6
    other_df["r_access_m"] = other_df.access_s * metres_per_s
    other_df["r_egress_m"] = other_df.egress_s * metres_per_s
    other_df["r_transfer_m"] = other_df.transfer_walk_s * metres_per_s
    other_df["r_longest_m"] = other_df[["r_access_m", "r_egress_m", "r_transfer_m"]].max(axis=1)
    other_df["r_total_m"] = other_df[["r_access_m", "r_egress_m", "r_transfer_m"]].sum(axis=1)
    other_df = other_df.join(envelope_df, on="draw_no")
    other_df["is_beyond_longest"] = other_df.r_longest_m > EXCEED_RATIO * other_df.g_env_longest_m
    other_df["is_beyond_total"] = other_df.r_total_m > EXCEED_RATIO * other_df.g_env_total_m
    other_df["is_beyond"] = other_df.is_beyond_longest | other_df.is_beyond_total
    other_df["is_above_global"] = other_df.r_longest_m > global_p99
    other_df["boardings_minus_default"] = other_df.n_boardings - other_df.g_n_boardings
    rides_df = pd.concat([pd.read_csv(newest(f"{NAME}_2*_trainrides_{release}.csv")) for release in RELEASES])
    mix = rides_df.groupby("draw_no").route_type.agg(lambda types: "+".join(sorted({R5_VEHICLES.get(t, str(t)) for t in types})))
    other_df["r_vehicles"] = other_df.draw_no.map(mix)
    other_df["side"] = np.where(other_df.cls.str.startswith("a"), "a", "b+c")
    tail_df = other_df[other_df.error_s < TAIL_S]
    measures = {}
    for label, sub in [("tail route choice", tail_df), ("group other, all", other_df)]:
        lines.append(f"{label}:")
        for side, part in sub.groupby("side"):
            shares = {key: part[key].mean() for key in ["is_beyond_longest", "is_beyond_total", "is_beyond", "is_above_global"]}
            if label == "tail route choice":
                measures[side] = shares
            lines.append(f"  ({side}) n {len(part)}: beyond Google's walks longest {shares['is_beyond_longest']:.2f}, total "
                         f"{shares['is_beyond_total']:.2f}, either {shares['is_beyond']:.2f}; above global p99 "
                         f"{shares['is_above_global']:.2f}")
            lines.append(f"      R5 median m: access {part.r_access_m.median():.0f}, egress {part.r_egress_m.median():.0f}, "
                         f"transfer {part.r_transfer_m.median():.0f}, longest {part.r_longest_m.median():.0f}, total "
                         f"{part.r_total_m.median():.0f}; Google envelope longest {part.g_env_longest_m.median():.0f}, total "
                         f"{part.g_env_total_m.median():.0f}; R5 / envelope longest median "
                         f"{(part.r_longest_m / part.g_env_longest_m).median():.2f}")
            lines.append(f"      boardings R5 - Google default {part.boardings_minus_default.value_counts().sort_index().to_dict()}; "
                         f"R5 vehicles {part.r_vehicles.value_counts().head(5).to_dict()}; error median "
                         f"{part.error_s.median():+.0f} s")
    a, rest = measures["a"], measures["b+c"]
    w1 = a["is_beyond"] >= W1_SHARE and a["is_beyond"] - rest["is_beyond"] >= W1_GAP
    w2 = w1 and a["is_above_global"] >= W2_SHARE_A and rest["is_above_global"] <= W2_SHARE_REST
    lines.append(f"READING (W1, tail): beyond Google's walks (a) {a['is_beyond']:.2f} vs (b)+(c) {rest['is_beyond']:.2f}: "
                 + ("walk reluctance or limit consistent" if w1 else "no walk reading"))
    lines.append(f"READING (W2): above global p99 (a) {a['is_above_global']:.2f} vs (b)+(c) {rest['is_above_global']:.2f}: "
                 + ("a global cap" if w2 else "not a cap" + (" (pair-relative: reluctance or ranking)" if w1 else "")))
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_combos.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    other_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_combos.csv", index=False)


def google_route_legs(route_of):
    """Google's legs (as extract) for one chosen route per pair: route_of = {draw_no: (route_ix, arrival_s)}."""
    rows = []
    for raw_path in GOOGLE_RAW_PATHS.values():
        with open(raw_path, encoding="utf-8") as file:
            for line in file:
                draw_no = int(line[line.index(":") + 1:line.index(",")])   # read the id before parsing: test lines skipped
                if draw_no not in route_of:
                    continue
                record = json.loads(line)
                route_ix, total_s = route_of[draw_no]
                requested = utc_of(record["request"]["departureTime"])
                steps = record["resp"]["routes"][route_ix]["legs"][0]["steps"]
                transit_ix = [i for i, step in enumerate(steps) if step["travelMode"] == "TRANSIT"]
                stops = [steps[i]["transitDetails"]["stopDetails"] for i in transit_ix]
                times = [((utc_of(stop["departureTime"]) - requested).total_seconds(),
                          (utc_of(stop["arrivalTime"]) - requested).total_seconds()) for stop in stops]
                access_s = sum(seconds_of(step["staticDuration"]) for step in steps[:transit_ix[0]])
                rows.append({"draw_no": draw_no, "m_access": access_s, "m_wait0": times[0][0] - access_s,
                             "m_ride": sum(b - a for a, b in times),
                             "m_transfer": sum(nxt[0] - prev[1] for prev, nxt in zip(times, times[1:])),
                             "m_egress": total_s - times[-1][1], "m_total": total_s})
    return pd.DataFrame(rows)


def railtram():
    """R5 rides a train where Google's default rides a tram: station time or preference? (docstring, `railtram`)"""
    combos_path = newest(f"{NAME}_2*_combos.csv")
    df = pd.read_csv(combos_path)
    lines = [f"{NAME} {run_date()} railtram: reusing {combos_path.name}"]
    google_rides_df = pd.read_csv(newest(f"{NAME}_2*_googlerides.csv"))
    g_mix = google_rides_df.groupby("draw_no").vehicle.agg(
        lambda types: "+".join(sorted({GOOGLE_VEHICLES.get(t, t.lower()) for t in types})))
    df["g_vehicles"] = df.draw_no.map(g_mix)
    df = df[df.error_s < TAIL_S]
    rx_df = df[df.r_vehicles.str.contains("rail", na=False) & ~df.g_vehicles.str.contains("rail", na=False)].copy()
    rt_ids = set(rx_df.draw_no[(rx_df.r_vehicles == "rail") & (rx_df.g_vehicles == "tram")])
    routes_df = pd.concat([pd.read_csv(path) for path in GOOGLE_ROUTES_PATHS.values()], ignore_index=True)
    routes_df = routes_df[routes_df.draw_no.isin(set(rx_df.draw_no))].copy()
    routes_df["seq"] = routes_df.lines.map(google_line_sequence)
    has_rail = routes_df[routes_df.vehicle_types.fillna("").str.contains(GOOGLE_RAIL)]
    first_rail = has_rail.sort_values(GOOGLE_COL).drop_duplicates("draw_no").set_index("draw_no")[GOOGLE_COL]
    rx_df["rail_s"] = rx_df.draw_no.map(first_rail)
    matched = routes_df.merge(rx_df[["draw_no", "r_lines"]], on="draw_no")
    matched = matched[matched.seq == matched.r_lines].sort_values(GOOGLE_COL).drop_duplicates("draw_no")
    assert (matched.set_index("draw_no")[GOOGLE_COL] == rx_df.set_index("draw_no").match_s.reindex(matched.draw_no)).all()
    legs_df = google_route_legs({row.draw_no: (int(row.route_ix), float(row[GOOGLE_COL])) for _, row in matched.iterrows()})
    rx_df = rx_df.merge(legs_df, on="draw_no", how="left")
    for leg in LEGS:
        rx_df[f"dm_{leg}"] = rx_df[f"r_{leg}"] - rx_df[f"m_{leg}"]
    rx_df["dm_ends"] = rx_df.dm_access + rx_df.dm_egress
    rx_df["dm_total"] = rx_df.r_total_s - rx_df.m_total
    leg_sum = rx_df[[f"m_{leg}" for leg in LEGS]].sum(axis=1)
    off = int((rx_df.m_total.notna() & (leg_sum != rx_df.m_total)).sum())
    lines.append(f"check: matched Google legs sum to its arrival on every pair: {'PASS' if off == 0 else f'FAIL ({off})'}")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    verdict = None
    for label, sub in [("RT (R5 rail only, Google tram only)", rx_df[rx_df.draw_no.isin(rt_ids)]), ("RX (R5 rail, Google no rail)", rx_df)]:
        lines.append(f"{label}: n {len(sub)}; classes {sub.cls.value_counts().sort_index().to_dict()}; any Google train "
                     f"route {sub.rail_s.notna().mean():.2f}")
        unmatched = sub[sub.cls.str.startswith("a") & sub.rail_s.notna()]
        lines.append(f"  unmatched with a Google train route: {len(unmatched)}; R5 - that route median "
                     f"{(unmatched.r_total_s - unmatched.rail_s).median():+.0f} s")
        for part_label, part in [("matched (b + c)", sub[~sub.cls.str.startswith("a")])] + [
                (cls, p) for cls, p in sub[~sub.cls.str.startswith("a")].groupby("cls")]:
            text = [f"  {part_label}: n {len(part)}"]
            for key in ["dm_access", "dm_wait0", "dm_ride", "dm_transfer", "dm_egress", "dm_ends", "dm_total"]:
                lo, hi = bootstrap_ci(part[key], np.median, rng)
                text.append(f"{key[3:]} {part[key].median():+.0f} ({lo:+.0f} to {hi:+.0f})")
            lines.append("; ".join(text))
        if label.startswith("RT"):
            part = sub[~sub.cls.str.startswith("a")]
            lo, hi = bootstrap_ci(part.dm_ends, np.median, np.random.default_rng(BOOTSTRAP_SEED))
            is_s = part.dm_ends.median() <= -STATION_DELTA_S and hi < 0
            total = part.dm_total.median()
            is_p = abs(total) <= STATION_DELTA_S
            named = max(LEGS, key=lambda leg: abs(part[f"dm_{leg}"].median()))
            verdict = (f"READING (RT matched, n {len(part)}): S {'holds' if is_s else 'fails'} (ends median "
                       f"{part.dm_ends.median():+.0f}, CI to {hi:+.0f}); P {'holds' if is_p else 'fails'} (total median "
                       f"{total:+.0f})" + ("" if is_s or is_p else f"; T: largest leg {named}"))
    lines.append(verdict)
    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_railtram.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    rx_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_railtram.csv", index=False)


if __name__ == "__main__":
    MODES = {"probe": probe, "route_train": route_train, "extract": extract, "score": score,
             "alternatives": alternatives, "combos": combos, "railtram": railtram}
    MODES[sys.argv[1]](*sys.argv[2:])
