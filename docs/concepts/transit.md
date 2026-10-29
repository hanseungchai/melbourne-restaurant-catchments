# Transit

**Purpose and scope.** Bands 1–2 routing: the r5py (R5) network, the GTFS feeds, transit timing, time
resolution against Google, departures and validation. Not the walking speed or the point-to-street
link (`walk.md`), band edges (`scoring.md` S1), the reachability pass itself (`reachability.md`), nor
the weekday-only scope's reasoning (`od-sampling.md` Limitations).
**Stages.** `construct_pt_graph` (`r5py_pt_graph.py`; STATUS paths-migrated; config group "PT network").
**Last reviewed.** 2026-10-20, compacted (3b16cfc)
**Full context.** Compacted 2026-10-20. The full text, with how each position was reached, intermediate
results, superseded steps and the change log to 2026-10-20, is the snapshot
`docs/context_snapshot/2026-10-20_02-48-00Z/concepts/transit.md` ("snapshot" below). Every ID and sub-label is
kept here so citations resolve; where an entry is shortened, its detail is in the snapshot under the
same label. This doc wins where the two differ.

## Current position
- **TRN-1.** Transit runs on r5py: a TransportNetwork from the OSM extract plus three PTV GTFS feeds
  (metro train, tram, metro bus), downloaded 2026-10-13 (`inputs/gtfs_ptv_20261013`, service
  2026-10-08 to 2026-12-31). Switched 2026-10-14 from the frozen 2026-09-21 feeds
  (`frozen_inputs/gtfs_ptv/`), which end before the TRN-7 window does and run thinner bus service in
  November (TRN-3). The site serves only the current timetable.
  Regional train, coach, regional bus, interstate and airport bus feeds are not used; the regional
  town buses PTV ships inside the metro bus feed (route_type 701) are dropped at the copy step
  (TRN-11). The project's own transit graph is dead (r5py pivot, decided Sep 19).
  Evidence: none (decision). `inputs/README.md` (gtfs_ptv_20261013); `frozen_inputs/README.md` (gtfs_ptv); rev4 L1053-1057; DESIGN_pre_spine "Data layers".
- **TRN-2.** Status (2026-10-14): cleaned (P2b; verified against the live-extract build: cleaned zips
  byte-identical, same 398 unlinked stops, same build summary), then two logic steps, each verified:
  route_type 701 dropped (TRN-11), then the 2026-10-13 feed (TRN-1). Validation against Google: TRN-8,
  TRN-13. The script runs on its own (the main.py block is a `pass`): R5's log reaches the checks only
  through a redirect of the script's output. r5py builds from copies of its inputs in its cache
  folder, made only when no file of that name is there (Windows), so a changed input under an old name
  was silently ignored and the old network loaded; the build now stops if a cached copy differs
  (`pt_network.check_r5py_working_copies`; Notes).
  Evidence: code; `outputs/pt_graph/r5_build.log` (2026-10-14 build); references in
  `diagnostics/diagnostic_data/pt_graph_reference_{20261013,701dropped_20261014}/`.
- **TRN-3.** Current build (2026-10-14: live extract, 2026-10-13 feed, route_type 701 dropped):
  0 GTFS errors; 23,553 stops (train 2,859, tram 1,623, bus 19,071), 0 outside the extent, 0
  unlinked; trips 40,556 / 55,599 / 195,369; zero-duration hops 0 / 303,902 / 1,716,792. Frozen vs
  new feed, trips on Wed 2026-11-04: train and tram the same; bus 15,555 vs 20,088 (64 routes and
  5,001 trips only in the new feed).
  Rolling validity (established 2026-10-14): PTV's dataset page (read by the user) says each export
  holds "a rolling 30 days of data from the date of export", some routes may be incomplete within it,
  and the feed is updated weekly. Release timing (2026-10-17, hunch on two exports): both exports held
  are Fridays (2026-08-28, 2026-10-09), and "weekly" may not hold. The window depends on the zip's
  content, not the page date. The 2026-10-13 download is the release exported 2026-10-09 (file dates
  inside the zips), so it is valid to ~2026-11-08. Data past that is partial: whole route_id groups
  are cancelled by calendar_dates removals with no replacement (e.g. bus prefix 42, north, 34 routes;
  53, inner west; 36, outer west), and a group's horizon moves with each release: a publication gap,
  not a network change. Within Nov 4 to Dec 17 the counts are steady but missing ~62 routes (~4,100
  trips per weekday) throughout.
  Earlier builds (Sep 21 build, 2026-10-13 live-extract rebuild, unlinked-stop clusters at the
  extract's edge): snapshot.
  Evidence: build log, `unlinked_stops.csv` (`frozen_inputs/legacy_evidence/`, from `data/GTFS_r5/`);
  the cause analysis, legacy `diagnose_unlinked_stops.py`, was never kept (D1 gap);
  `2026-09-21_r5py-network-build`.
- **TRN-4.** Timing: raw published durations, zero-duration hops included (from minute rounding;
  build log 2026-10-14: 1,716,792 bus; 0 and 303,902 for the other two feeds, which is which unconfirmed); no floor, imputation, dwell model or repair. R5
  keeps 0 s hops and prices a ride as arrival at B − departure at A, never summing hops, so a ride's
  error stays under 60 s. Google answers from the same feed, so the zero-hop bias is shared with the
  target: fidelity, not validation error. Impossible speeds checked 2026-10-16 on the 2026-10-09
  release: train and tram none; bus 629 spans on 193 of ~195,000 trips over 120 km/h (routes 788,
  887, 479 for 95%), no times going backwards; accepted as published (Limitations).
  Evidence: `zero_duration_hops_Sep_21` (R5 source read Sep 21; Routes test `zero_hop_google_check_20260921.csv`);
  `diagnostics/transit_hop_speed.py`.
- **TRN-5.** R5 conventions to state, not measured: a 60 s minimum board wait at every boarding
  (`MINIMUM_BOARD_WAIT`); route_type 300–499 read as rail (so PTV's type 400 is safe); PTV publishes
  transfers only as type 4 (in-seat continuation), with no `min_transfer_time`.
  The board wait measured 2026-10-17 (T7 e): moves band shares by <= 1.76 pp, kept as a stated bias;
  the first board's slack is removed in the model of record (TRN-13).
  Evidence: R5 source reading (`zero_duration_hops_Sep_21` L48-63); rev4 L1573-1577; jar bytecode and
  `diagnostics/transit_board_slack.py` (board wait).
- **TRN-6.** Time resolution: `TravelTimeMatrix` truncates to whole minutes (percentiles taken in
  seconds, then truncated), so model times read 0–59 s short, ~30 s on average; accepted for the bulk
  pass and stated. Google transit durations are differences of whole-minute clock times. Comparing
  with Google: Google's seconds rounded to the nearest minute (SCR-10, since 2026-10-16; the scorers
  use np.round; the earlier "floor Google first" survives only in `transit_board_slack.py` and
  `transit_di_raw_states.py`, no band verdict), so recorded comparisons carry ~30 s toward R5 early.
  The seconds are lost in R5's Java, before r5py's `_parse_results`; correction plan: DESIGN Q24.
  Decided 2026-10-17 (user): times from TravelTimeMatrix at a 1-min window at Google's minute, tested
  sound (T7 e); not r5py's 10-min default, which costs ~1.8 min mean abs (centred) or ~2.8 min
  (starting at t). Boardings from the ride caps (T7 e).
  DetailedItineraries (DI): through r5py it fails at 1 min (heap error: R5's departure sampler steps
  0 s) and keeps one result per sampled departure second, often not the fastest; its walk legs' clock
  times are unusable (r5py's per-stop cache); rides usable. The DI-TTM gap is DI's egress walk (r5py's
  reverse egress search); with TTM's egress, DI = TTM on 29 of 29. Arrivals: last ride departure + ride
  + egress − origin departure, never from walk-leg clock times. DI's role decided 2026-10-17 (user):
  measure Google's preference for transit and for transfers between modes (T7), from R5's full lists
  with TTM's egress; durations and boardings only. DI's window open. Bands use TTM, not DI.
  Evidence: `time_resolution_Sep_21` (R5 source, derived); T7 (e). Band edges: `scoring.md` S1.
- **TRN-7.** Departures (decided 2026-10-13; replaces the one-Wednesday pin, 2026-09-09).
  Day and slot as drive (ODS-5): weekday 30-min slots, 80% open-share hours / 20% flat over
  06:00-24:00, then a uniform minute; the hours rule is the mean of the two drive draws' rules (the
  2026-09-02 and 2026-10-10 hours), which is what the pooled drive sample follows; `dep_p` stored.
  Low-service slots are kept on purpose: thin late service is part of the story. Date: a seeded
  uniform pick among the window's dates on the drawn weekday. Every request must be in the future at
  fetch time (Google refuses or answers differently for past times) and inside the release's valid
  period, so the fetch runs before the window's dates.
  Window per release (decided 2026-10-14, user; step (5) dropped 2026-10-18, user): the weekdays that
  are (1) after the fetch day (Melbourne time); (2) within 30 days of the release's export date;
  (3) before the first date any in-scope route_id group drops out; (4) minus public holidays (e.g.
  Melbourne Cup, Nov 3). Week-to-week timetable noise is part of what the sample should carry, so a
  date is not removed for being off its weekday's median. (The diagnostic's code and pre-registered
  verdict still apply step 5: to update.) Computed per release by `diagnostics/transit_release_window.py`.
  Windows: 2026-10-09 release, fetch on or before Oct 18: Oct 19-23, one date per weekday; 2026-10-16
  release (`inputs/gtfs_ptv_20261018/`), fetch on Oct 18: Oct 19 - Nov 2 (11 weekdays; cut at Nov 4 by
  bus group 53; Nov 3 removed). Pair, weekday and minute are drawn up front; the date is assigned when
  the pair's release is known (TRN-10). r5py is departure-aware (`departure` +
  `departure_time_window`, default 10 min, percentiles over the window's minutes).
  Draw details (decided 2026-10-13): (A) "mean of the two rules" is the equal-weight mean of the two
  slot-probability vectors, each from `functions/pair_sampling.departure_probabilities` on its own hours histogram (a
  count-weighted mixture would differ slightly: stated). (B) Weekday first, then date, so dates of a
  weekday with more dates in the window weigh a little less; intended. (C) Night slots after midnight
  ride the previous service day (e.g. Cup night, reduced): accepted and stated, not excluded. (D) Own
  seed (`TRANSIT_DEPARTURE_SEED`, config) with child streams for cell, minute and date, as drive;
  drawn per pair inside the pair stage, so departures don't depend on T4. (E) Validation routes r5py
  at the drawn minute with a 1-min `departure_time_window`, not the 10-min default (like-for-like with
  Google's single departure).
  Evidence: `diagnostics/transit_window_trip_counts.py` (2026-10-14); `diagnostics/transit_release_window.py`
  (2026-10-16, SUPPORTED: window and route-group horizons; closes the D1 gap). DESIGN Q18.
- **TRN-8.** Validation: r5py against Google transit pairs fetched like the drive set (same weekday
  and departure protocol, or catchments aren't comparable). Assumed (user, 2026-10-13, ~95%
  confident): Google answers from the same PTV timetable as our feed; a diagnostic may test it later.
  Transit is schedule-based (no traffic-aware request). When transit offers nothing useful, Google
  returns a walking route, not nothing; it refuses only outside the published timetable.
  Scope (TRN-11): a pair is scored only if Google's default route is in scope; a pair whose default
  rides a non-scope service is excluded, even when an in-scope alternative exists (`transit_fetch.py`
  `google_zones`). Alternatives (`computeAlternativeRoutes`) feed Google's range, in scope only.
  Reworded 2026-10-20 to match the code (user; the earlier text used the best in-scope alternative):
  21 of 4,833 non-test pairs (0.4%), 18 with an in-scope alternative (decided 2026-10-13, user; bias
  accepted, Limitations).
  SKU: transit requests bill Routes Essentials (Google SKU page read 2026-10-13: no Pro or Enterprise
  trigger applies), 10,000 free calls a month; `api_ledger` SKU `routes_essentials`. So the fetch sets
  no `routingPreference` (the drive fetch's TRAFFIC_AWARE is a Pro trigger) and asks for no polyline
  traffic fields.
  Built 2026-10-16 (`transit_fetch.py`): Routes Essentials through the ledger; a guard refuses any
  body with `routingPreference`, a mode other than TRANSIT / WALK, or another SKU; alternatives on;
  Google's whole answer kept per pair (`.raw.jsonl`), so scope and target rules are applied later
  without new calls; release stored as text.
  Fetched 2026-10-17 (`transit_fetch.fetch_transit_pairs`, run_id `transit_fetch`): 2,625 pairs, all
  HTTP 200; 2,501 with 6 routes; 2 empty, both T5 pairs r5py can't route either; 116 walk-only
  defaults; route table 15,268 routes (14,581 in scope, 562 name mismatch, 125 out). Snapshot:
  `output_backup/transit_google_20261017_backup/`. Later fetches: TRN-10 (second batch), TRN-14,
  TRN-15.
  Route table (`transit_fetch.build_route_table`; `.routes.csv` next to each fetch file): per route
  leave, arrival, leave wait, arrival from the requested departure, duration gap, per-line and route
  scope (TRN-11). Leave = first boarding minus the walk before it; arrival = last alighting plus the
  walk after it; walk-only routes leave at the request.
  Google's answers (smoke test 2026-10-16, 5 calls): `duration` excludes the wait before boarding
  (tested SUPPORTED, `diagnostics/transit_google_duration.py`); up to 6 routes per pair; the default
  route is not always the earliest arrival; walk-only routes come back as alternatives; durations in
  seconds; every line's agency is "Transport Victoria". Snapshot:
  `output_backup/transit_google_smoke_20261016_backup/`.
  Evidence: `diagnostics/transit_google_duration.py`. `departure_noise_floor_Oct_4` L56-64; rev4 L1140-1142;
  developers.google.com/maps/billing-and-pricing/sku-details, …/routes/transit-route.
- **TRN-11.** Scope: Myki metro fares only (decided 2026-10-13, user): metro train, tram and
  route_type 3 metro buses. Out: V/Line train and coach, SkyBus, and the regional town buses
  (route_type 701, 204 routes / 26,477 trips) that PTV ships inside the metro bus feed (Geelong,
  Bendigo, Latrobe Valley, Warragul/Drouin, Bacchus Marsh, Wallan, Lara). Reason: riding regional
  services to eat out is not normal access; destination-pull venues that draw long-range travel are
  later work, with a separate reputation measure. Built 2026-10-14: the GTFS copy step drops their
  routes, trips, stop_times and the stops only they use (`config.PT_EXCLUDED_ROUTE_TYPES`); no such
  stop is shared with route_type 3. Shapes and calendars only they use stay (R5 ignores them).
  Validation side: TRN-8. Google's routes are matched to scope by line name and vehicle type
  against the feed's in-scope routes, not by operator: Google names every line's agency "Transport
  Victoria" (decided 2026-10-16, user). Matcher (`transit_fetch.line_scope`): vehicle type (feed
  route_type 400 train, 0 tram, 3 bus) plus line short name against the cleaned feeds' routes; long
  name checked where both sides have one (the metro train feed has none), a mismatch flagged
  `name_mismatch`. No regional (701) bus shares a short name with a metro bus.
  Evidence: none (decision). Route types from the frozen bus feed's routes.txt (session check
  2026-10-13).
- **TRN-9.** Walking inside transit trips uses the r5py walk-only speed (WLK-1, 4.16 km/h), passed
  into R5; walk legs are not recomputed afterwards (WLK-2). Whether R5 charges the point-to-street
  link: WLK-3.
  Evidence: see `walk.md`.
- **TRN-10.** Transit pairs (decided 2026-10-13; built 2026-10-15): drawn like drive (ODS-2: hex →
  venue, origin pool residents / workers at p = 0.5, venue uniform over place IDs, no quotas). Window:
  the uncalibrated r5py model, as drive used blind (ODS-3), with two safeguards, because here the
  window model is the model under validation and selecting on it hides pairs r5py wrongly calls
  unreachable. (a) Wide: the top transit band × 2, i.e. r5py's fastest weekday time ≤ 2,400 s (40 min;
  decided 2026-10-13, user, before any Google result). (b) Departure-independent: a pair passes on
  r5py's fastest time over the weekday (a low percentile over 06-24), and its departure is drawn
  afterwards, independently, as drive does; a filter at the drawn departure would keep only walkable
  pairs at night (re-examined and kept 2026-10-16, user).
  Built (`transit_samples.py`, `functions/transit_window.py`): fastest = r5py percentile 1 over 06-24
  on Wed 2026-10-21, cap 40 min, stock r5py 3.6 km/h; candidates more than 35 km apart (haversine)
  skip r5py and are rejected (worst-case in-window reach 31.3 km). T5 pairs are drawn from r5py's own
  rejections. r5py runs in 2 worker processes (4 GB heap each), checkpointed per batch, resume refused
  if the window settings or release changed. The split stratifies the halves by origin pool.
  `haversine_kmh` is stored, descriptive only.
  Split and size (decided 2026-10-13 / 14, user): train / test split at the draw (T3), 2,500 drawn
  (T4): 1,252 training / 1,248 test, plus a separate 125-pair out-of-window smoke-test set (T5), in
  neither half; 500 exploration pairs from the training half (never the test half). CV folds: 5,
  written at the draw (T3, user 2026-10-15).
  Releases (decided 2026-10-14, user): all pairs drawn on the 2026-10-09 release, the window filter
  run at a date every in-scope route group serves (Wed 2026-10-21). Each pair carries the release it is
  fetched under and is routed on that release's network (one r5py network per release; no GTFS merge,
  which would need per-release calendar trimming and ID prefixes and risks double or lost trips).
  Fetch (decided 2026-10-17, user): the whole draw (2,500 + 125 T5) fetched at once on the 2026-10-09
  release, Oct 19-23, one date per weekday (TRN-8). Cost: every pair on five dates, so a disrupted
  date weighs on a fifth of the sample.
  Second batch (fetched 2026-10-18, user's go): 2,000 reserve pairs, the first 2,000 in-window pairs
  past the draw by draw_no (27,795-51,844) from the checkpoint, screened on the 2026-10-09 release at
  3.6 km/h, not re-screened (user: both batches pass one gate, and the 40 min screen absorbs small
  changes in the new release); fetched under the 2026-10-16 release, Oct 19 - Nov 2; 2,000/2,000 HTTP
  200 (`transit_samples.draw_transit_reserve`, `transit_fetch.fetch_transit_reserve`; files
  `transit_pairs_reserve.csv`, `transit_google_20261016.csv`); outside the split; scored with the
  training half in TRN-13. Snapshot `output_backup/transit_google_reserve_20261018_backup/`.
  Evidence: `diagnostics/transit_window_reach.py` (SUPPORTED 2026-10-15). Decision: user 2026-10-13, 2026-10-14.
- **TRN-12.** Time and path are predicted separately (decided 2026-10-18, user, discussion). Time
  feeds the reachability bands (TRN-13). Path (where people walk, for a foot-traffic layer) was
  measured 2026-10-18 (T7 j): walk overlap 0.338 at a 100 m brush against a 0.90 bar, FAILS.
  Path dropped 2026-10-18 (user, discussion): foot traffic leaves the core (framing.md FRM-20), so
  transit is predicted for time only. Reasons: effort against gain (user); 0.338 is far from 0.90; the
  pedestrian counters, the only outside check, sit mostly in the CBD (density.md, Not adopted); matching
  Google's preference would take many more paid calls with no guarantee (T7 h). The ceiling check was
  never run (0.90's fairness untested).
  Evidence: diagnostics/transit_time_bands.py, diagnostics/transit_walk_overlap.py,
  diagnostics/transit_stop_match.py (2026-10-18).
  Foot traffic reconsidered 2026-10-19 (user leaning, not a decision; FRM-20): from the path baseline's rank
  table (TRN-13), the share of trips on Google's route falls from rank 1, and R5's top 10 hold ~0.62. A layer
  that spreads each trip over R5's top routes with rank weights calibrated on Google, read as totals per stop
  cluster at the resolution of the interpolated origins, is a reasonable estimate with a footnote (user):
  single trips often take a neighbouring stop or line. Established: the rank decay. Untested (Claude): that the
  errors cancel in totals; a systematic mode lean (R5 trains where Google takes trams or buses) would not.
  Check before any build (Claude, not run): boardings / alightings per stop cluster (station or 200 m),
  rank-weighted R5 vs Google, weights fitted on one part of the pairs and scored on the rest, against rank 1 only
  (ties split) as the plain model; R5's default suboptimalMinutes; enough pairs per cluster (all scored pairs,
  ~3.5 h). Open: cluster size; which tie reading sets the weights; whether weights fitted on Google answers fall
  under the Google Maps terms concern noted in framing.md Not adopted (clause not checked).
  Matching Google's walk pattern dropped 2026-10-22 (user, 69th: "pretty fruitless"). Why: the gap is route
  choice, not streets. Both-transit pairs: 0.444 of R5's walk metres lie within 25 m of Google's walk; legs with
  Google's endpoints hold only 0.180 of R5's metres and already sit 0.823 on Google's leg, so street choice could add
  ~0.03 at most; a walk-weight re-rank over R5's own candidates moves R5 off Google's stops (matched share 0.536 at
  w = 1, best +0.011, 0.423 at w = 3). Shape (report only): Google is turn-averse (a Z, ~1 fewer turn than R5's
  staircase), nearer the L than the straight line; main-road share +0.05, no clear pattern. Scale does not rescue
  single trips (hexes 0.327). In aggregate (FRM-20): R5 places walking like Google at 500 m cells (weighted Jaccard
  0.571) and stop clusters (0.578), not at hex scale (0.405); R5 walks ~1.5x Google's volume.
  Evidence: `diagnostics/transit_walk_shape.py`, `transit_walk_route_choice.py`, `transit_walk_aggregate.py`.
- **TRN-13.** Band metric for transit time, bands 1-2 (decided 2026-10-18, user, discussion), and the
  transit model of record (model fitting closed 2026-10-20, user, discussion). Overall band agreement
  flatters (a trivial "> 20" scores 0.854 against 0.965) and a short-trip miss would be silent in
  reachability. The training results have been seen, so the test changes rather than its bar being
  lowered, and no new bar is set from those numbers (user).
  **Model of record:** the no-wait model at plain cuts 10 / 20 on the v2 pathways network ((f) below),
  scored against Google's range at k = 2 ((b) below); hard misses and the whole-minute truncation
  (TRN-6) are stated costs. No-wait = stock R5 at 4.16 km/h with the first board's 60 s slack removed
  (T7 e): TTM from t - 1 min, minus 1; r5py always adds a direct walk, so the shifted run gives
  H = min(W, Tns + 1); N = H - 1 if H < W, else W (W walk-only time; stock S only settles ties
  S = W - 1, H = W: 33 pairs, 3 band calls; user OK). Walk-only trips gain nothing from the shift; a
  transit trip can gain a whole headway, catching a vehicle stock just misses (median 4, max 11 min on the
  subject's catchment, `transit_catchment_sensitivity.py`).
  Chosen 2026-10-18 after the run, not blind (scored after the 9 / 19 result), but consistent with the
  plan: model 1 of the comparison, nothing fitted; the test half stays the final check. Good enough as
  is (user, 2026-10-19): chasing the remaining misses is indefensible or impractical; the model's target
  is Google, not the timetable (user).
  (1) Zones, coin tosses (user): Google time within +-3 min of a cutoff: zone 1 = 7-13 min (cut 10),
  zone 2 = 17-23 min (cut 20). Per zone: recall = of zone pairs Google puts below the cut, the share
  R5 also puts there; precision = of zone pairs R5 puts below the cut, the share Google agrees with
  (zone chosen on Google's time, so R5 calls on pairs outside it fall to the hard misses).
  (2) Zone gate (user): (a) floor: the lower end of each score's sampling range above 0.6 (chance
  ~0.5); (b) unbiased-noise bar: R5's error measured on pairs away from the cutoffs (Google 0-6, 14-16,
  24-30 min, centred to median 0, 2,000 simulations), zones simulated with that error and no bias; the
  zone scores must reach it within their sampling range (no extra lag at the cutoffs); (c) balance:
  misses not one-sided (two-sided sign test p >= 0.05) and |recall - precision| <= 0.10. Wilson 95%
  intervals; R5 below when N <= cut (ties as N_hi).
  (3) Hard misses: replaced by the per-cut shares of Plan (b) below. Count ratio (R5's band count /
  Google's) kept as a bias check, bar 0.90-1.10; hard misses and count ratio on the random sets only.
  (4) Reported, not gating: full-band recall and precision; strata (distance, time of day, inner /
  middle / outer).
  (5) Data: training half plus the second batch (TRN-10) and the boundary top-up (TRN-14), each set
  routed on the network of the release its Google answers came from (user): training half on
  2026-10-09, second batch and top-up on 2026-10-16; R5 on Wed 2026-10-21 (Open below). The test half
  only for the final evaluation, opened once (user).
  Decided 2026-10-18 (user, discussion), after the first hard-miss read:
  (a) Framing: a transit tolerance is the expected time from a random moment, trip plus typical wait,
  over a departure window (convention, as Conveyal; assumes nothing about the traveller's context or
  preference, user). Waiting is part of how Google presents a trip. The no-wait model stays as a
  component, not the answer (user, after close); the window value is not built (wait modelling off the
  table, below).
  (b) Reference range: catchment means reasonable effort, not possible at a sprint (user). Google's
  recommended trip (which may wait) and its faster but harder alternative both count: the Google time is
  a range from the earliest arrival among Google's first 2 routes to Google's default. 2 is the user's
  choice from the phone app's first screen (a cautious pick; one is too narrow), not evidence; assumed
  (unverified) that the API's route order is the app's. R5 agrees when its band call lies within the
  bands the range covers (a range spanning a cut agrees either way); zones stay defined on Google's
  default, a zone pair agreeing if R5's side of the cut matches either end. R5 faster than every Google
  route stays a miss (R5 minimises time with no effort cost). Widened after a failure, for the framing,
  not the numbers; the training result is not blind there; the test half stays the clean check.
  (c) Tests: stage 1 (free) against the range, gating on 2 routes (1, 3 and all returned reported
  beside it); stage 1b (free, reported) how often Google's default trails its own earliest route;
  stage 2 (free, reported) R5's value over a departure window; stage 3 (paid, optional, user's go):
  Google at several departures for a subsample (e.g. 100 pairs x 5 = 500 calls), R5's window value
  against Google's, bars set before the fetch. Stage 3 undecided (Claude: not warranted, it reopens
  fitting for ~3.8% of band calls). Skipped (user, 2026-10-20).
  (d) Stop linking (free check, not run): R5 v7.5.1 (jar) links each GTFS stop at its point by a
  straight connector to the nearest walkable edge (300 m search, then up to 1,600 m; beyond, unlinked),
  after pruning walk islands under 40 vertices. Stretch goal only (Plan (a)).
  (e) Station entrances: R5 gives each platform one link and reads no pathways.txt; superseded by the
  pathways check and network ((f) below).
  Plan and hard-miss bar decided 2026-10-18 (user, discussion; DESIGN Q23):
  (a) Order: stage 1; then the hard misses that survive the range; stages 1b and 2; stage 3 (paid) only
  as a fallback. The stop-linking and entrance checks are a stretch goal, done only if what is left
  points to a cheap, clear fix; otherwise R5's network limits are accepted and stated (user).
  (b) Hard misses per cut. For each cut c (10, 20 min), on Google's default with R5 agreeing if its
  side matches either end of the range: lost reach = of pairs with Google c-10 to c-3 min, the share R5
  puts over c; false reach = of pairs with Google c+3 to c+10 min, the share R5 puts at or under c.
  Four shares, equal 3-10 min windows (width Claude's choice, not tuned); a pair may sit in both cuts'
  tests; pairs outside every window are not tested here (full-band scores only). Bar: each share's
  Wilson 95% upper bound <= 5%, the bar proposed before results; 10% with balanced error was discussed
  and declined as rule-shopping (user). Lost reach at 10 report-only (user, 2026-10-18).
  (c) A fail is acceptable (user): recorded as an accepted cost, with its size, direction and location
  (strata), and the model may still go into reachability.
  (d) Stop condition decided 2026-10-18 (user, before stage 1; Claude's proposal): a hard-miss fail bars
  the model from transit reachability if any per-cut share's Wilson upper > 10% (severe), or >= 2/3 of a
  failing share's misses (>= 5 misses, Claude) sit in one stratum holding < 1/3 of that test's tested
  pairs (concentrated); otherwise a recorded cost. Strata: service density (user's idea; Claude's
  measure, approved as built 2026-10-18): distinct trips departing within +-30 min of the pair's minute
  from any stop within 700 m (haversine) of the origin, on the pair's release; thirds of the scored
  random pairs (0-36, 36-130, 130-807 trips).
  (e) Stages 1, 1b, 2 run 2026-10-18 (`diagnostics/transit_hard_miss_range.py`,
  `transit_google_preference.py`, `transit_window_value.py`): stock R5 4.16 BARRED (severe: lost reach at
  20 upper 0.131); no-wait at plain cuts: zones pass, hard misses fail, not severe or concentrated;
  no-wait at transit cuts 9 / 19 over-corrects against the range. Stage 1b: the default is Google's
  earliest on 0.784, else trails by median 2.7 min, buying less walking with home wait. Stage 2: window
  medians move ~3.8% of band calls. Late misses are knife-edge boardings at street tram / bus stops (a
  single-moment artefact); early misses ride trains from CBD / underground stations (Google's in-station
  walk), trams R5 rides faster, Google waiting at home, R5 walking where Google rides.
  (f) Pathways implemented (user, 2026-10-19), on principle, not on the score: R5 reads no
  pathways.txt, so it skips in-station time that people really walk; a fidelity fix, kept on whether
  the data matches reality, not on the score (user). Check (`transit_pathway_check.py`, rule >= 2/3
  within +-1 min of Google's walk, set before the run): 0.777 (Wilson 0.754-0.800), data accepted (R5
  as now 0.676). Network of record v2 (`transit_pathway_network_v2.py`): per train station, OSM footway
  spurs (tunnel=yes) from each feed entrance to each platform hub, length = shortest pathway time
  (elevators kept) at 4.16 km/h; each hub ends in a 2 m stub pointed away from every linkable way and
  the platform stop moved to the stub's end in a renamed feed copy; validated on every station, both
  releases. Stage 1 on v2 (no-wait plain, k 2): zone checks pass; false 10 4/294, lost 20 8/248 (upper
  0.062), false 20 19/503 (0.058): fail, not severe, not concentrated, a recorded cost.
  Performance review 2026-10-19 (random sets, 3,239 scored pairs, no-wait plain on v2): 3-band
  accuracy 0.964 against Google's default (0.970 against the range; trivial "> 20" 0.860), kappa 0.861,
  macro-F1 0.898; band 1 recall / precision 0.903 / 0.830, band 2 0.872 / 0.816, band 3 0.978 / 0.990;
  reach <= 20 recall 0.941, precision 0.877, count ratio 1.073 (default); 0.848 accuracy inside the +-3
  min zones, 0.990 outside. Controls: no-wait at transit cuts 9 / 19 0.965 / kappa 0.861; stock R5 4.16
  0.960 / 0.840; r5py as shipped (old network) 0.949 / 0.777. In-sample: these pairs chose the model,
  the range and the stop condition; the test half is the honest figure.
  Net reach 2026-10-19 (`transit_net_reach.py`): overall unbiased at 10 and 20 (at 20 only just: +0.46
  pp of pairs); the high service-density third leans over at 20 (+1.30 pp), low and mid within noise
  (Limitations). Leading candidate cause, not pursued: departure-minute sensitivity.
  Considered and not pursued (detail in the snapshot): a scalar on R5's outputs (no-wait x s = a 1-min
  transit cut shift); a 30 s edge shift (between cuts 10 / 20 and 9 / 19, gains likely cancel, user);
  a dense-area ride stretch (Google rides the timetable, `transit_invehicle_stretch.py`); a re-rank of
  R5's options (parked, user: the top ranks are near-ties a preference rule cannot separate); wait
  modelling (below); transfer waits and DI's 30 s shift (parked). See Not adopted.
  **Wait modelling off the table (user, 2026-10-20; fitting could still reopen, the test half being
  unopened).** The departure profile with Google's wait preference as oracle is not built. Adding it can
  only make predictions later (the no-wait time is a floor) and so can only fix early misses: Google
  waiting at home explains 6 of the 24 false-reach-at-20 misses; fixing all 6 leaves 18 / 503 (3.6%),
  still near the 5% bar, and pushing borderline pairs later risks new lost-reach misses. Stated
  limitation: the model ignores the home wait Google sometimes recommends to walk less (stage 1b).
  Open (user, 2026-10-20): R5 is scored at each pair's drawn minute but always on Wed 2026-10-21, while
  Google answered on the pair's own weekday (TRN-7). Checked 2026-10-20 (free;
  `diagnostics/transit_scoring_weekday.py`; bar Claude's, set before results: < 1% and <= 0.5 pp): all
  1,252 training pairs re-routed on Google's own date; Wednesday reproduced exactly (260 / 260); Mon-Thu
  0 band calls change; Friday 4 / 250; overall 4 / 1,252 (0.32%), agreement with the range +0.16 pp:
  Wednesday scoring stands on Claude's bar. Decided 2026-10-20 (user): each pair is scored on its own
  date (Google's departure date), not Wednesday. Before the test half is opened, the second batch and the
  top-up are routed on their own dates too (the check covered the training half only) and the official
  stage 1 scoring (zones, hard misses, count ratio) is re-run on all random sets; free, R5 only. The test
  half is scored the same way. Done 2026-10-20: all 3,462 random and top-up pairs routed on their own
  dates (2026-10-21 pairs reproduce the Wednesday tables exactly; own-date service counts equal the
  Wednesday table on all 481 pairs dated 2026-10-21); model 3 on uniquely named feed copies. Stage 1 on own
  dates (no-wait plain, k 2) vs Wednesday: every verdict unchanged; z1 floor 0.735 -> 0.737, z2 floor
  0.812 -> 0.826, false 10 4/294, lost 20 8/248 (upper 0.062), false 20 19 -> 18/503 (upper 0.056): fail,
  not severe, a recorded cost; count ratio <= 10 / 20 1.097 / 1.073. Stock R5 lost 20 22 -> 20/248, still
  barred (severe).
  Station fidelity check (decided 2026-10-20, user; done 2026-10-20, `transit_station_fidelity.py`): at
  Melbourne Central, Richmond, Middle Footscray and Patterson (97 sides) R5 uses everything the feed holds
  (one-way vs two-way spur time within 15 s; Google's walks pass the feed's own entrances; no Google walk on
  ways R5 cannot walk): no GTFS-faithful fix, the misses are feed-vs-Google time disagreements. All
  stations (1,240 sides, 167 stations): Google follows PTV's pathway times at most (station |Google - feed|
  quartiles 11 / 19 / 30 s; with pathways 0.790 within 60 s vs 0.675 without); 11 of 79 judged stations
  differ by > 60 s (106 sides; 3 hard-miss sides of 30): Patterson, Balaclava, Town Hall, Footscray,
  Gardenvale, Middle Footscray, Carnegie, Windsor, Dandenong, Anzac, Jolimont-MCG; at five Google acts as
  if it had no pathways, at Town Hall and Anzac it charges more. Bad feed data, an older feed version and
  time-of-day effects ruled out; Google's value there is static (sd 3-4 s) from a source we cannot see.
  A stated cost (user, 2026-10-20; Limitations); no per-station offset or blend (Not adopted).
  Evidence: `diagnostics/transit_band_metric.py`, `transit_model_compare.py`, `transit_hard_miss_range.py`,
  `transit_pathway_check.py`, `transit_pathway_network_v2.py`, `transit_net_reach.py`,
  `transit_scoring_weekday.py`, `transit_station_fidelity.py`.
- **TRN-14.** Boundary top-up (decided 2026-10-18, user, discussion; built and fetched 2026-10-18).
  Target 200 pairs per TRN-13 zone, zone membership from Google's answer only. Not circular: pairs are
  selected on haversine distance only, R5 is never consulted during the draw or fetch, and no R5 result
  is looked at until the fetch ends. Zone time (user OK): Google's default route, arrival from the
  requested departure, rounded minutes (SCR-10), scored only if in scope (TRN-11).
  (1) Ranges: one haversine range per zone, holding ~95% of that zone's pairs among Google answers
  already fetched (training half and second batch only): zone 1 350-1,650 m (gap 3.8%), zone 2
  850-4,700 m (gap 4.7%) (config.TRANSIT_TOPUP_RANGES_M). Evidence: diagnostics/transit_zone_ranges.py.
  (2) Pilot (paid, 60 calls, 30 per range; pilot pairs count toward the 200): range 1 lands 0.33 in zone
  1 and 0.33 in zone 2 per call; range 2 lands 0.03 (without the r5py window, uniform pairs in range 2
  sit at its far end, where Google mostly says > 30 min): not worth drawing from as it stands.
  (3) Fetch: random draw within each range, a pair landing in the other zone counts there; call ceiling
  400 (user); 150 more calls, all from range 1: 210 calls in all, all HTTP 200. Earlier zone pairs count
  toward the 200 (user): zone 1 49 top-up + 157 earlier = 206, zone 2 67 + 298 = 365. Pairs outside both
  zones are kept (hard misses, counts). Files: config.TRANSIT_TOPUP_PAIRS_PATH, TRANSIT_GOOGLE_TOPUP_PATH,
  TRANSIT_TOPUP_SELECTION_PATH.
  (4) Rules as TRN-10 (pair rule, departure rule, date coverage, ledger), minus the r5py <= 40 min
  window; 2026-10-16 release, Oct 19 - Nov 2.
  Open: whether "200 per zone" meant new top-up pairs only (user): if so, ~560 more range-1 calls with
  TRANSIT_TOPUP_COUNTS_EARLIER off. Google against itself (~100 zone pairs re-asked on another weekday,
  ~100 calls) as a ceiling for reading a fail, not a gate; user unsure.
- **TRN-15.** Test-half extension (decided 2026-10-20, user; fetched 2026-10-20). The test half (1,248
  pairs) is thin in TRN-13's cells: estimated from the training half's counts, without opening it, zone
  1 ~67 and zone 2 ~119 pairs; lost reach at 10 (~19 pairs) cannot clear the 5% bar even at 0 misses,
  and small cells make the balance and noise-bar checks lenient.
  Decided (user: better testing, no rollbacks, keep the course): more pairs by the same method as the
  draw and the second batch (TRN-10: reserve replayed from the checkpoint, r5py <= 40 min gate at 3.6
  km/h, no re-screen), all added to the test half; none to training (fitting is closed and nothing is
  fitted). Not targeted: TRN-14's boundary draw yields ~6x more zone-1 pairs per call, but it scores
  only near the cuts; a random test scores the model on the output's own trip mix, with one estimator
  and no weights. Size 4,000; departures Oct 21 - Nov 2 (each pair a seeded pick among its weekday's
  dates, TRN-7), on the 2026-10-16 release; the test is scored pooled and per release, each set on its
  own network. Past the checkpoint's end the stream is screened on the 2026-10-16 release (stock r5py,
  3.6 km/h, Wed 2026-10-21), not on 2026-10-09; each pair's `window_release` says which release screened
  it.
  Built (`transit_samples.extend_transit_checkpoint_release`, own checkpoint `.evaluated_20261016.csv`,
  feeds in `outputs/pt_graph/gtfs_cleaned_20261016/`; `draw_transit_test_extension`, replay of both
  checkpoints, draw and reserve reproduced exactly; `transit_fetch.fetch_transit_test_ext`). Fetched
  2026-10-20: 4,000 pairs, draw_no 51,848-99,801, 1,660 screened on 2026-10-09 and 2,340 on 2026-10-16;
  4,000 of 4,000 HTTP 200 (`config.TRANSIT_GOOGLE_TEST_EXT_PATH`; backed up in
  `output_backup/transit_google_test_ext_20261020_backup/`). October Essentials after it: 8,841 of
  10,000.
  Nothing read from the answers. Scoring date: each pair's own date (TRN-13, 2026-10-20).
  Test reading rule decided 2026-10-20 (user, at the desk; Claude's proposal; (2), (5)-(9) revised the
  same day, before opening): (1) zones on TRN-13's bars (floor, noise bar, balance); the noise bar's
  error is measured on the test's own pairs away from the cuts (the training procedure on the new
  data). (2) Hard misses on the training bar unchanged: same windows, each share's Wilson upper <= 5%,
  a fail a recorded cost, barred if severe or concentrated (TRN-13 Plan (b)-(d)); Claude's earlier
  "worse than the training rate" criterion dropped (set after training results; it treated the training
  share as exact). (3) Lost reach at 10 report-only. (4) The "severe" stop rule applies only to tests
  with n >= 35, the smallest n at which 0 misses has a Wilson upper <= 10% (1 miss needs 53; 0 / 19
  gives 0.17); smaller tests are reported. (5) The pooled test is the verdict; per release is reported,
  the severe rule applying per release at n >= 35. (6) Count ratio bar 0.90-1.10 unchanged (training
  <= 10 at 1.097); a fail is a recorded cost, never a bar on its own; no bar moved after results
  (user). (7) Service-density thirds fixed at the training cuts (0-36, 36-130, 130-807 trips), not
  re-cut on the test; they gate through the "concentrated" rule; the halves come from one pool (user).
  (8) Means reported with medians (the 29-pair tail, R5 > 20 min off Google). (9) Destination overlap:
  the second batch, top-up and extension were not grouped by destination hex (T3 grouped only the two
  halves; 0 shared between them): 3,884 of the 5,248 test pairs share a destination hex with a training
  set. The full test is the gate; the 2,045 unseen-destination pairs (dest hex in no fetched training pair;
  user, 2026-10-21, 66th; was 1,364) are scored report-only. Removing
  shared pairs as the gate was considered and not adopted (user's idea, Claude's check on r5py screening
  times, no Google answer read): the subset keeps 6% CBD destinations (full 45% shared side) and ~42
  near-10 pairs (thin cells again; not the output's trip mix). Stated limitation (Limitations).
  Order before opening: Claude writes predicted test results (zones, hard-miss shares, with ranges);
  the test scorer reproduces the own-date training tables exactly; then the test is opened once.
  Opened only after the own-date re-scoring and the station fidelity check (TRN-13), both done.
  **Result (opened once 2026-10-20; concluded, user).** Predictions first (`transit_test_predictions.py`),
  scorer check PASS (`transit_test_score.py check`: 3,448 / 3,448 pairs, every table value), then `test`.
  Pooled (5,234 scored): z1 0.870 / 0.892 floor 0.799, z2 0.922 / 0.869 floor 0.828, noise bars pass;
  z2 balance FAIL (43e / 24l, p 0.027); false 10 4/514, lost 20 11/417 (upper 0.047) pass; false 20
  34/792 (upper 0.059) FAIL, not severe, not concentrated: a recorded cost; lost 10 0/83 (report-only);
  count ratio 1.011 / 1.084. Every prediction inside its 90% range. Per release: 2026-10-09 test half
  false 20 14/190 (upper 0.120, severe under (5)); 2026-10-16 extension fails lost / false 20, not
  severe. Ruled after results (user, Claude's reading): (5)'s per-release clause catches a release that
  breaks; the same release's training half ran 4.2% (train 8/192, second 10/311, test 14/190, extension
  20/602): not barred; stated as a post-result reading. Misses: false 20 mostly borderline (R5 19-20 on
  23 of 34, median 5 min under Google's default; 13 Google home waits of 5.5-14.6 min); lost 20 median 7
  min late, knife-edge boardings (`transit_lost_reach_sweep.py`: leaving 2 min early catches the vehicle
  on 7 of 11, 3 min on 10). Model of record kept, no backtracking (user); the 30 s edge shift is parked
  for any future fresh test. Unseen-destination definition settled (user, 66th): 2,045, the scorer's count
  (dest hex in no fetched train / second / top-up pair); the 1,364 counted all 3,659 top-up candidates,
  though unfetched candidates had no Google answer and no part in fitting (traced 65th).
  Retrospective (user, 2026-10-20): a ~100-pair pilot under the 40 min gate before the training fetch
  would have shown the thin cells near the cuts and allowed better targeting; still, the
  representative, no-peek protocol was the safer choice, since an accidental peek that biases the
  sample is the worse failure.
- **TRN-16.** R5 patches (decided 2026-10-21, user, discussion; P1 and P3 built and tested on 100 pairs). Where R5's convention
  differs from the target's, the fix goes into R5's Java source, not around it (graph stubs, snapping,
  cut shifts): defensible as a readable diff, customisable, no per-run network cost. Rules: (1) conventions
  only (how time is reported, what is charged, known bugs), never parameters fitted to Google (revised 2026-10-21,
  user, 61st: Google is the fit target; a parameter may be fitted to Google on training pairs only, declared as
  fitted, with the unopened holdout as its check; the opened test half validates nothing fitted after it); (2) a patch
  register here: convention, why, evidence diagnostic, equivalence test; (3) each patched class is first
  recompiled unchanged and matched to the running jar's bytecode; off = stock exactly, on = only the
  intended quantity moves, by the predicted amount; (4) the r5py screen and every draw stay on stock r5py,
  drawn sets are never re-gated with a patched model; (5) between two mechanisms for one convention (Q24
  stubs vs patch) the choice is made on training-pair equivalence before any holdout is scored. Original
  jar and source in `inputs/r5py/` untouched, patched jars in outputs/; class swaps, a Gradle-built fork
  once the patch set is frozen (user, 2026-10-21, 58th; was: from 3+ patches). Register (user, 2026-10-21, 53rd; none built): P1 seconds out (`convertToMinutes`
  returns seconds, read as `travel_time_s`, rounding (SCR-10) in Python; test: patched // 60 = stock, every
  pair); P2 no connector charge (Q24 (1)); P3 board wait by round (redefined 2026-10-21, user, 55th: 0 s at the
  first boarding, 200 s at transfers, both Google's conventions; replaces "board wait 0 at every boarding");
  after a source read, stop-link connectors and per-edge rounding of walk
  seconds (maybe the ~26 s per walk-only trip); a per-pair leg breakdown (tooling, no time moves). Parked:
  `setOrigin` swap (DI only). Each step on one seeded, stratified 100-pair training set (~20 walk-only, 40
  one boarding, 30 transfers, 10 near `max_time`) vs the previous step; verdict and (5) on one full training
  run. Should-not-differ: < 1% of pairs differing is a flagged minor deviation, >= 1% fails; expected
  changes: any mismatch flagged and examined (user). Pathways stay map data. Cost:
  upgrades re-apply and re-test patches; patches kept small, explained in Python terms (user reviews no Java).
  Checked 2026-10-21: `inputs/r5py/r5-7.5.1` `TravelTimeReducer` recompiles to the jar's bytecode (0 diffs).
  P1 built and tested 2026-10-21 (54th; 100 pairs, 4.143 km/h; jars in outputs/r5_patches/): off = stock and
  patched // 60 = stock, 600 / 600 values; vs Q24 stubs 3 / 100 pairs differ (FAIL on the 1% line), all from the
  stubs (2 pushed past max_time, 1 a 29 s stub). Stubs (5) or patch: user's call, owed. Prior-work search done
  (55th; T7). Google's rules (55th, training routes, `transit_google_transfer_buffer.py`): no first-boarding wait
  (median 1 s); at every transfer listed walk + ~200 s (none in (0, 200 s] of 8,156; floor flat by walk length and
  mode pair; not in PTV's transfers.txt); a slower hidden walk and per-mode board / alight charges both tested,
  not supported (nothing at trip ends; split not identifiable). P3 built 2026-10-21 (55th) on P1's jar,
  `FastRaptorWorker.boardWaitSec` (round 1 = input state with no previous): B1 recompile = jar; off (60 / 60) =
  P1 and walk unchanged, every value; 0 / 60 = the model of record's 1-min shift on all 81 transit-won pairs (the
  shift can retire); 0 / 200 never earlier; changes 21 / 100 pairs; in-sample error to Google (arrival - request)
  median -31 -> -8 s, transfers -49 -> -1 s, mean abs 333 -> 290 s. Full training run (57th, 3,448 pairs, F1 / F2
  exact): IMPROVES (hard misses 25 -> 23, no test worse; mean error to range -2.53 -> -1.66 min; 2+ boardings median
  -113 -> -20 s); adopted (user, 58th). (5) evidence: patch 1 vs stubs 34 pairs differ, hard misses equal; decided:
  patch 1 (user, 58th), stubs only as a check. R5's
  transfer walk vs Google's listed (8,159 transfers, `transit_r5_transfer_walk.py`): median +9 s, mean abs 44 s, 76%
  within 60 s (rail wider): the buffer stays 200 s; a residual bias is the walk model's (user agreed).
  Candidate (user leaning to test, 2026-10-21, 56th discussion): a transfer-only walk speed in `doTransfers`
  (access, egress, walk-only untouched; usable only after alighting). Read-only check: ~4.5-4.6 km/h centres the
  median (+12 -> ~0 s) but mean abs only 43 -> 39 s, p10-p90 ~130 s: bias, not scatter (paths, station layouts).
  Parked (user, 58th); policy question settled by (1)'s revision (61st): allowed as a declared fitted value.
  `diagnostics/transit_r5_patch_board_wait.py`. P2 built 2026-10-21 (58th) on P3's jar: `StreetRouter.setOrigin` and
  `LinkedPointSet` (timeToPoint, eval's same-edge branch, distanceToPoint for egress) through one private helper per
  class (serialVersionUID unchanged); B1 recompile = jar, off = P3 exactly; on 100 pairs drawn points vs snapped 5
  pairs 1-2 s apart, all snapping's rounding (`why` mode). Full training run: hard misses 23 both, 35 / 3,424 pairs'
  seconds and 3 pairs' minutes differ, 0 band calls; adopted (user): points routed as drawn. Connector cost (100
  pairs): walk median 15 s, transit 8 s. R5 caches egress tables per JVM: one patch state per process.
  `diagnostics/transit_r5_patch_connector.py`. Per-edge rounding (59th): R5 charges each walked edge
  ceil(length / speed); confirmed on 2,212 training walks (every edge increment matches, no other charge; 0.48 s per
  edge, R^2 0.986; edges median 11.5 m, so walk-only excess median 50 s, Google-walk pairs 12 s).
  `diagnostics/transit_r5_edge_rounding.py`. P4 built on P2 (`EdgeStore.Edge.traverse`: a walk edge costs the step in
  round(cumulative path distance / speed); 1 s minimum kept): B1-B3, equivalence and path rebuild exact; walks now
  path / speed (median -1.2 s). Full training run: WORSENS (hard misses 23 -> 27, false reach up; zone 2 balance
  fails; count ratio <= 10 0.981 -> 1.068) although 0-boarding error +16 -> -1 s: R5 transit was already early and the
  ceiling's access walk partly offset it. Not adopted for now, jar kept (Claude's recommendation; user moved on to
  stop-link connectors, 59th): retest after the transit early bias is understood. `diagnostics/transit_r5_patch_walk_path.py`.
  Stop links (60th): not a suspect (one straight LINK edge pair per stop, H-walk median 2.0 / 0.0 m; only adds time).
  Leg-by-leg error (60th, training pairs, R5's own TTM paths, F1-F3 exact): same-line pairs unbiased (median +2 s,
  mean abs 68 s; access +13 / wait0 -14 s mirror, ride and transfer 0); early mean = route choice (other-line pairs
  mean -167 s, mean abs 263 s; tail < -5 min carries it all; Google never returns R5's lines on 53% of the tail's,
  later on 17%, earlier than its default on 30%) plus 129 pairs where Google answers 5-6 h and R5 walks. Not a
  patchable convention (Claude's reading); next: what never-returned combinations share. `diagnostics/transit_leg_error.py`.
  61st (training pairs, `transit_leg_error.py` combos / railtram, rules set before results): never-returned (a) vs
  returned tail pairs: R5 walks beyond every Google route's walk on 0.40 vs 0.19 (W1 fails the 0.5 line), above
  Google's p99 single walk (1,974 m) 0.05 vs 0.02: no walk cap; boardings and vehicles differ little. Decided (user):
  the early tail is a stated limitation for now (R5 = fastest feasible trip). Tail route choice is mostly the same
  boarding count on other lines (196 / 326; R5 skips a transfer 81, adds one 49); top pattern R5 train vs Google tram
  (71). On the 37 of those Google returns: no station time (ends +19 s, S fails), timed alike (total -6 s, P holds).
  On class (c) (33) Google's own train route arrives 452 s earlier but walks 1,191 s at its ends vs the tram's 430 s:
  walk reluctance on Google's own routes (a walk minute > ~1.6 arrival minutes; T7 (h) found w ~2). Mixed modes:
  weak lean only (class c R5 mixed 0.24 vs default 0.16). Model overview (training, same scorer): hard misses 30 (old
  record) -> 25 (P1) -> 23 (P3, P2) -> 27 (P4); 3-band accuracy 0.960 -> 0.965. Preference fitting now in scope
  ((1) revised): via DI's full lists or a TTM workaround (user's idea), not decided; T7 (h)-(i): slowed walking
  missed vehicles Google catches, so a weight must not slow the walk itself.
  62nd (`transit_walk_weight.py`, 3,340 training pairs, rule OK'd before results): Google ranks as if cost = arrival
  + (w - 1) x walk time with w 1.70 (bootstrap 1.55-1.95; default picked 0.720 -> 0.853), stable on all three sets;
  with a transfer penalty, w 1.95 and tau 450 s pick 0.942. How to apply it is open (user's call).
  63rd (discussion, plan agreed with the user, not built): P5 transfer penalty: a cost must not move R5's clock
  (a penalty at boarding or alighting is a minimum wait, which only punishes tight transfers); instead, at
  FastRaptorWorker's result (`finalRoundState`, ~line 402), per stop pick the round r minimising
  `scheduleState[r].bestNonTransferTimes[stop]` + tau x (r - 1), report its real time (r* kept in a second array),
  paths from `scheduleState[r*]`; exact, as rounds are RAPTOR's transfer criterion; egress commutes. P6 walk-weight
  pick: walk is no RAPTOR criterion, so two runs (default; walk / w), both with P5; slowed path re-timed at real
  speed; default kept only if time saved > (w - 1) x extra walk (no new parameter). Python comparison first, Java
  only if two runs cost too much. Which w and tau (1.70 alone or 1.95 with 450 s) is the free check's to show.
  With seconds out, a cap loses t in [cap, cap + 29 s]: route at cap + 1 min, cut after rounding (Claude's,
  at RCH-19). `diagnostics/transit_r5_patch_seconds.py`.
  64th (build; free check, rule OK'd by the user before the run): P6 at w 1.70 0.800 vs ideal 0.853 (G1 fails), P5
  + P6 at (1.95, 450 s) 0.813 vs 0.942 (G2 fails); the slowed walk eats the wait (default catchable 0.555), so the
  access walk is never charged. P5 and P6 not adopted (Not adopted); the walk weight a finding about Google's ranking
  (Limitations; DESIGN "Future work"). `diagnostics/transit_walk_pick_check.py`.
  65th (build; user's idea): walk charge after routing, transit = R5's time + (s - 1) x its route's walk, walk-only
  uncharged, search untouched. Patch rule PASS at s 1.10 (pooled hard misses 23 -> 19, second batch 15 -> 14) but a
  blanket shift: agree 1,492 -> 760, 1-boarding median -7 -> +54 s, zone 1 / 2 noise bar and zone 2 balance fail.
  Not adopted (Not adopted). `diagnostics/transit_walk_charge.py`.
  66th (build; decided, user): the patch rule gains a zone gate: a fitted candidate passes only if every TRN-13 zone
  check passing on the model of record still passes (closes the gap the walk charge showed). Order: holdout fetch
  first, then the buffer sweep, then the freeze record; the holdout stays sealed (no comparison with R5) until the
  freeze record and its reading rule are written. Holdout fetched 2026-10-21: 4,000 pairs, all HTTP 200, release
  20261016, departures Oct 22 - Nov 2 (`transit_fetch.fetch_transit_holdout`; 2,841 paid calls, ~US$14.21, under a
  one-run ledger extension, removed). P3 buffer sweep (170-230 s by 10, rule OK'd before the run: pick on the
  training half, ties nearest 200 then smaller; V1 second batch not WORSENS, V2 pooled IMPROVES, zone gate) built,
  B1 PASS on all jars, F1 exact. Flat: every buffer gives the same hard misses in every test (train 8, second 15,
  pooled 23), no band call or zone check changes; mean error to range -1.85 (170) to -1.55 (230) min. 200 stays (rule,
  all tied). `diagnostics/transit_buffer_sweep.py`.
  67th (build; user OK): **model frozen 2026-10-22**, before any holdout answer met R5. Frozen: R5 + P1 + P3 (200 s) +
  P2, jar `r5-v7.5.1-r5py-all_transit_r5_patch_connector_p2.jar` (sha256 62a8f6c1...8eb3, checked on every run),
  4.143 km/h, v2 pathways, 1-min window, p49, max 90 min, min(transit, walk) rounded half up, cuts 10 / 20, k = 2.
  A change after this is a new model needing a new holdout. Holdout reading rule = TRN-15's test rule (pooled =
  the holdout, one release), tail counted not excluded, medians beside means; report-only: unseen-destination
  subsets, mode and boarding breakdowns (the pathways reading). Scorer check exact (training 23 hard misses, ratios
  0.981 / 1.042). Seen pairs (report-only, user: pooled since all are seen): old test re-routed on the frozen jar,
  hard misses 49 -> 31 on the same 5,234 pairs (false 20 34 -> 18), every check passes pooled; all seen (8,473 random)
  PASS every check. User's prediction: holdout like the seen pairs, maybe more hard misses (transfer work targeted).
  Claude's predicted ranges saved before opening. `diagnostics/transit_holdout_score.py`.
  **Verdict (user, 2026-10-22, 73rd): holdout accepted**; the model stands for bands 1-2, lost 20 a recorded cost.
  69th (autonomous; facts): holdout opened once 2026-10-22, check PASS the same day.
  3,995 of 4,000 scored. Zones pass (z1 recall / precision 0.844 / 0.890, z2 0.868 / 0.897); false 10 1/365, false
  20 15/603 ok; lost 20 9/272 (rate 0.033, upper 0.062) fails the 5% line, not severe, not concentrated (thirds 2 /
  4 / 3): a recorded cost by the rule (training failed the same line, 7/248); at 272 pairs at most 6 misses could
  pass. Ratios 0.986 / 1.044; tail 42 (1.06%). Every figure inside Claude's predicted ranges. 3-band accuracy 0.969
  (training 0.971), <= 10 recall / precision 0.892 / 0.904, <= 20 0.939 / 0.900, MAE 3.00 min, median |error| 1 min.
  `diagnostics/transit_holdout_metrics.py`.
  P7 in-seat continuations (77th built, 78th run; user asked; a measurement, the frozen model untouched; named p5 in
  its diagnostic's tables, P5 being the transfer penalty; jars renamed p7_in_seat 2026-10-23): PTV's train transfers.txt is all type 4 (in-seat,
  trip to trip at Flinders Street / Town Hall; TRN-5), which R5 skips, so a rider staying on board is routed as a
  transfer. Patch: loader keeps the rows, TransitLayer maps them, FastRaptorWorker rides a continuation as one ride (up
  to 4 hops, no board wait). B1 PASS; off = frozen on 12,696 of 12,696 pairs, p5 never slower. p5 faster on 177
  pairs (1.4%), all frozen pair time > 21 min (median 44), gain median 4.4 min (~10%); no band call flips at 10 / 20;
  every TRN-13 / TRN-15 check unchanged. On the 177: Google rides a train on 111 (frozen +4.0 min median -> 0.0),
  tram on 59 (-3 -> -7). Not adopted (Not adopted); a stated limitation. `diagnostics/transit_r5_patch_in_seat.py`.
  **To be adopted on principle** once a budget for a fresh test-sample fetch opens, scored then (user, 2026-10-23,
  80th: a fidelity fix, even where the score worsens).
  P8r reporting patch (user, 2026-10-23, 80th: reporting, not the frozen model, so the freeze does not bar it): a
  departure window reports per pair the number of its minutes within a cut ("reach") or the times at fixed minutes
  ("draws", iteration i = minute W - 1 - i) instead of percentiles; off unless the JVM property `platica.report` is
  set. B1 PASS, B2 additions only; off = frozen on 30,428 pairs; reach counts = the 30 single departures' counts on
  every pair (cuts 629 / 1,229 s); draws = single departures exactly. A window costs 2.3 single departures at 30 min,
  9.4 at 210 (1,000 origins). Built and tested. **Adopted (user, 2026-10-23, 81st)** for the reachability pass with
  the Q25 scheme (RCH-20), in draws mode (joint per-minute draws for SCR-12); a per-minute within-cut bitmask is
  deferred (plain draws ~1 GB per day type for the subject, inside Q21's budget).
  82nd (2026-10-23, facts): draws mode as built reports at most 5 minutes per call (R5's
  `AnalysisWorkerTask.MAX_PERCENTILES` = 5; r5py asserts the same; placeholder values must be 1-99, ascending), so a
  whole window is not read in one call. **P8r extended (user, 82nd):** the cap lifted; a window read in chunks of
  <= 90 min (three 30-min slots), one draw index per minute; retest B1 / B2 / T1-T3 plus T4 (90 drawn minutes = 90
  single departures). Jar name proposed `..._p8-r_draws.jar` (Claude's; the 80th's p8-r_reach jar untouched).
  Built 2026-10-23 (83rd): cap lifted in `AnalysisWorkerTask.validatePercentiles` only while `platica.report` is
  set; r5py's assertion bypassed at run time; B1 / B2, T0-T4 pass (T4: every minute of a 90-min window = its single
  departure, 0 of 1.6 M values differ). Jar `r5-v7.5.1-r5py-all_p8-r_draws.jar` (name confirmed by the user, 2026-10-23, 86th).
  `diagnostics/transit_r5_patch_reach.py`.
  Naming (user, 2026-10-23): P<n> for a patch that changes the model, P<n>r for one that changes only what R5
  reports; jars `r5-v7.5.1-r5py-all_p<n>[-r]_<one-two-word description>.jar` (p7_in_seat, p8-r_reach renamed or
  built so). P1 (seconds out) is reporting-type: p1-r_seconds. The frozen chain's jars keep their old names until
  renamed with every diagnostic that names them (owed).

## Not adopted
- Walk charge after routing (2026-10-21, 65th, user): R5's reported transit time + (s - 1) x its route's walk
  seconds. Passes the patch rule on hard misses (s 1.10, 23 -> 19) but moves nearly every transit pair about a
  minute later (2,797 pairs' minutes change; agree labels halve; three TRN-13 zone checks fail): walk time does
  not single out R5's wrong-route pairs. Use elsewhere (Claude's reading): a perceived-time measure (walk minutes
  weighed, as in appraisal), mean-based or false-reach-averse outputs. `diagnostics/transit_walk_charge.py`.
- P5 (transfer penalty by round) and P6 (two-run walk-weight pick) (2026-10-21, 64th, user): the free check failed
  (P6 0.800 vs ideal 0.853; P5 + P6 0.813 vs 0.942). R5's search ranks only arrival time and rounds; a cost added
  from outside moves the clock or filters what the search already dropped, so Google's walk-light route is often
  not there to pick. A walk weight needs a cost criterion in the search (McRaptor; too costly, 63rd).
  `transit_walk_pick_check.py`.
- A 190 s transfer buffer to absorb R5's ~10 s longer transfer walk (2026-10-21, user agreed with Claude): not
  Google's rule (no Google slack in (180, 200 s]) and a fit to Google's error (TRN-16 (1)); the walk model owns it.
  Rechecked 2026-10-21 (61st, after (1)'s revision): on same-line 2+ boarding pairs R5's transfer leg - Google's
  median 0 s, mean +3 s (316 pairs); 190 s would put them ~10 s early. A free sweep (170-230 s) offered, not run.
- A patch counting time from leaving home rather than from the requested departure (2026-10-21, user):
  practically the same as the no-wait reading already done in Python (TRN-13, RCH-13); more footnotes, no
  output gain.
- The project's own transit graph (Sep 19 pivot), and its machinery: empirical wait model and wait censor (1,200 s, from the band structure), stop pooling, the LP timing repair and speed envelope, cross-platform stop merging, boarding and transfer penalties fitted against Google. r5py handles these its own way (TRN-5). Code retired in reorg step 8 (`construct_map.py`, `map_pathing.py`; DEPRECATED.md). rev4 §6.4-6.5; STALE rev3.6-3.16 deltas.
- A kinematic run-time model (cruise speed, acceleration, knot, dwell): not identifiable from a 60 s-quantised feed; hinge dwell bounds unstable. STALE rev3.14, rev3.15.
- Filling zero hops: 15 s floor (manufactured ~135k unpublished seconds), median-speed imputation, cross-trip averaging (72% of arcs have IQR exactly 0), push-back (+82% on a 9-hop tram trip), historical feed pooling, any fill outside the published minute. `zero_duration_hops_Sep_21`; STALE rev3.8, rev3.15.
- Distance repair of corrupt segments (e.g. the tram hop at 4,977.92 m, decimal inflation; Google confirmed its 120 s): distance only ever condemns a duration, and none was condemned. STALE rev3.9.
- Recomputing the access walk while keeping R5's wait (double counts), or changing walk legs after routing (pairs walk times with a missed vehicle). `time_resolution_Sep_21` L65-77.
- Removing transit from band 1 on fare grounds: fares are outside the model, and band 1 measures as walking anyway (Notes). rev4 L1525-1532.
- Route-preference arms in R5 (2026-10-17, T7 h): OpenTripPlanner's defaults (walk weight 2) and walk weight plus boarding / transfer penalties fitted on Google's choices both fail against stock R5; slowed walking misses vehicles Google catches. Generalised-cost routing (OTP2) not pursued (user). `diagnostics/transit_preference_arms.py`.
- A time scalar on R5's outputs (T7 g, s = 1.01; TRN-13, s = 1.0247 = a 1-min transit cut shift) and a 30 s edge shift (TRN-13): no gain over the model of record.
- DetailedItineraries for second-level band times (2026-10-21, user): its seconds sit in the walk legs, its unreliable part (per-stop cache, egress bug), it is far slower in bulk (unmeasured) and would need its own validation; ride match with TTM only 29 of 29. The 30 s destination offset was chosen instead (DESIGN Q24).
- A dense-area stretch of tram and bus rides (2026-10-19): Google rides the timetable (factors 1.001-1.007), so the inner-city lean comes from R5's choice of trips, not slower rides. `transit_invehicle_stretch.py`.
- Path prediction and a re-rank of R5's options to pick Google's route (TRN-12, TRN-13, 2026-10-18 / 19): parked; if reopened, suboptimalMinutes 5 suffices. `transit_rerank_ceiling.py`.
- Wait modelling via a departure profile with Google's wait preference (TRN-13, 2026-10-20): can only fix a few early misses.
- A per-station offset fitted to Google's errors at the weak stations (Claude's idea, 2026-10-20): fitting to Google, not fidelity to the feed; only GTFS-faithful fixes are made (TRN-13, station fidelity check).
- A weighted blend of pathway times toward Google's share of stations with and without pathways (user's idea, 2026-10-20, not adopted by the user): fits to Google with no evidence which is right, and would move the ~156 agreeing stations off to target 11. A Google-fitted station-swap network as a sensitivity bound on the reachability output (Claude's, RCH-13): possible, not planned, same objection (user). `transit_station_fidelity.py`.
- Step shortcut for the profile (one query per vehicle) and R5's `includePathResults` per-minute output (not exposed by r5py): not needed while wait modelling is off. Snapshot, TRN-13.
- P7 in-seat continuations (2026-10-22, 78th, user): measured, not adopted; the frozen model stays frozen and no band
  call at 10 / 20 changes (TRN-16). If ever adopted, RCH-26's oracle must ride continuations as one ride too.
  Revised 2026-10-23 (user): to be adopted once a test-fetch budget opens (TRN-16).

## Limitations
- R5 reports the fastest feasible trip; Google's default weighs a walking minute ~1.7x (TRN-16, 62nd), so on
  pairs where Google trades time for less walking, R5 reads earlier. Stated, not modelled (P5 / P6 not adopted).
  Framing (user, 2026-10-23): the output is the faster end of Google's recommended routes, reasonable but optimistic
  (FRM-24); the tilt is larger where alternatives are many (trams, buses), so it can lean inner vs outer comparisons.
- In-seat continuations (TRN-5): PTV publishes cross-city through-running (Flinders Street, Town Hall) as in-seat
  continuations (GTFS transfer type 4). R5 ignores them, so a rider who stays on board is modelled as getting off and
  catching a later train. Measured with a test patch (P7, not adopted; frozen model kept) on 12,696 validation pairs:
  1.4% get faster when continuations are ridden (median 4.4 min, about 10% of the trip), all over 20 min, so no 10-
  or 20-min band call changes; where Google's route rides the train, the frozen model reads those trips ~4 min late.
  `diagnostics/transit_r5_patch_in_seat.py`.
- Whole-minute truncation: transit times read ~30 s short on average. `time_resolution_Sep_21`.
  Plan to correct it with a 30 s destination offset: DESIGN Q24.
- Access walk (WLK-6, 2026-10-20): R5 walks to Google's first stop +17 s median (1.055x), mostly the
  charged connector (WLK-3), and longer in late-miss pairs. A stated cost until DESIGN Q24 is run.
- Zero-duration runs over km-scale hops give a free ride; accepted risk, kept as published. `zero_duration_hops_Sep_21` L189-192.
- GTFS is a published plan, not observed running; crowding and capacity (failed boardings) are not modelled, as in Google's target. rev4 L1407-1409, L1430-1431.
  Timetable optimism (user, 2026-10-22, 76th: a disclaimer, the metric kept): irregularity (bunching), in-vehicle
  congestion and disruptions (incidents, protests; one stopped tram holds every tram behind it) make real transit
  reach smaller than timetabled, most on tram and bus corridors through the centre. Google's target shares it: our
  answers are future-departure plans (timetable only), not the live plans people use. Not measurable with our data
  (no historical incident or vehicle-position record); a disruption simulation is future work (musings 2026-10-22).
- Regional feeds excluded and the extract cut: outer corridors near the cut (Pakenham/Officer, Bacchus Marsh, Wallan) have unusable stops and truncated walk access, so their accessibility is biased low. Cost not measured. `2026-09-21_r5py-network-build` L79 (TRN-3).
- Validation departures cover a few weeks of late-spring weekdays, within one or two releases' valid
  periods (TRN-7): no holidays, no school break, no autumn or winter timetable; weekday only by
  scope (`od-sampling.md`).
- A release is complete only for 30 days from export, and some routes may be incomplete even
  within it (TRN-3); routes PTV hasn't yet published for a date are missing from that date.
- Pairs whose Google default rides an out-of-scope service are excluded (TRN-8, TRN-11; 0.4% of
  non-test pairs), so the sample under-represents trips best made by V/Line, coach or SkyBus;
  accepted (user, 2026-10-13; wording to the code 2026-10-20).
- In-station walking at 11 train stations (TRN-13, station fidelity check): the model follows PTV's
  pathway times, Google differs by > 1 min there (static, cause unknown, its data not available to us).
  The cost on the scored sample is small (3 hard-miss sides of 30); on the reachability output it is
  unknown, and could concentrate where routes lean on one of those hubs (Footscray, Town Hall). Stated,
  not fixed (user, 2026-10-20). `transit_station_fidelity.py`.
  Google offers at most 3 alternatives, so an in-scope route may exist yet go unseen.
- Pairs are windowed by r5py itself (TRN-10): pairs r5py places far beyond the top band are not
  tested unless T5 is adopted. The window is stock r5py's, for every set, and stays so under R5
  patches (TRN-16 (4)): a pair Google finds quick but stock R5 does not can be screened out.
- Kept pairs lean to worker origins (T6, settled 2026-10-16, user): 1,790 worker / 835 resident of
  2,625 (68%), though origins are drawn 50/50; workers sit where transit is dense, so validation
  tests r5py mostly on well-served trips. No quotas (ODS-2 kept); r5py's error is reported per
  origin pool as well as overall (388 / 387 resident pairs in the training / test half).
- Feed timing errors are routed as published (TRN-4): 629 bus spans on 193 trips (routes 788,
  887, 479 for 95%) imply over 120 km/h; accepted 2026-10-16 (user): dropping them changes every
  trip that connects with them, and no defensible repair exists.
  `diagnostics/transit_hop_speed.py` (run 2026-10-16).
- Phantom or missing services in the feed can't be detected or removed defensibly (Google likely shares
  the source; a per-trip check is far over budget): accepted 2026-10-19 (user, TRN-13).
- Inner-city reach at 20 min runs ~1.3 pp of pairs (about 5% in count) more generous than Google's range
  in the high service-density third (TRN-13, net reach 2026-10-19); accepted; a dense-area ride stretch
  was tested and dropped (Google rides the timetable; TRN-13, 2026-10-19).
- Hard misses fail the 5% per-cut bar (TRN-13): late misses are knife-edge boardings, early misses
  cluster at CBD / underground train stations and short tram rides; a located bias, recorded with its
  size and direction. The model ignores the home wait Google sometimes recommends to walk less.
- Test result (TRN-15, 2026-10-20): near 20 min R5 leans early (false reach ~4%, z2 balance fails,
  count at <= 20 +8%), typically 4-5 min under Google, often where Google waits before leaving; it
  misses a ride now and then (lost reach ~3%, median 7 min late: ~1-2 min slower to the boarding, then
  the next vehicle). Accepted as a recorded cost (user).
- R5's 60 s board slack at transfers is kept (TRN-5); only the first board's slack is removed.
- Test and training share destinations (TRN-15 (9)): 3,884 of 5,248 test pairs end in a hex some
  training set holds (second batch, top-up, extension drawn without T3's grouping). Nothing is fitted,
  so the scores are not inflated by fitting; model choices were made on training, but none is tied to
  a place. Shared destinations make test pairs less independent, so the Wilson intervals run somewhat
  narrow, mattering most for shares near the 5% bar. Checked report-only on the 2,045 unseen-destination
  pairs (mostly suburban). Stated (user, 2026-10-20); the drive layer's split does not have this gap.

## Notes
- r5py sets the travel time to 0 wherever `from_id == to_id` (`r5py/r5/travel_time_matrix.py`
  L156-161, v1.1.7: it assumes origins and destinations are one set). With separate origin and
  destination sets, keep their ids disjoint, or unrelated pairs read 0 min (found 2026-10-15: 376
  false zeros at 49-190 km in `transit_window_reach`, one per origin; fixed there and in
  `functions/transit_window.py`). Not a timetable or mode effect.
- Whole-minute output: a walk under ~40 s reads 0 min (36 stop-venue pairs 0-51 m apart; 1-min pairs
  62-112 m). Same-hex pairs are rejected in the draw, so it doesn't arise there.
- Findings from the custom-graph era, pre-rebuild; re-run on r5py before citing (rev4 L2011-2014):
  within-band transit anisotropy (max/min duration) 3.2–4.5, 11.1 at 6–8 km, against drive 2.1–3.2;
  walk/transit switchover ~600–700 m (walk-only fallbacks 63% → 13% → 3% over 300–1,200 m); band 1 is
  walking for almost everyone (four confirmations; subject 98th percentile at band 1, 77th at band 2);
  node counts overstate transit's reach; Google prefers fewer legs at ~191 s per leg avoided (n = 29);
  population-weighted wait 533 s per resident, 269 s per worker. rev4 L1252-1326.
- The old Google sample (rev4 §7): transit 360 + transit short 180 calls, 487 of 540 usable (53
  walk-only fallbacks). Its file was not found in `data/` or `frozen_inputs/` (searched 2026-10-13).
- The custom graph's long history (zero hops, type-4 welding, quantisation, the 4,977.92 m arc) is in
  the STALE rev3.6–3.16 deltas; it explains several conventions above but is not current.
- Running r5py: R5 downloads before the build (minutes of silence are normal); copy GTFS once, cap the
  JVM memory, pilot 10 calls first. `urban_factor_and_r5py_pivot_Sep_19`; `TEMP_workplan_Sep_22`.
- r5py caches a built network by its inputs' contents: an unchanged rebuild loads it and the log has
  no build messages. To force a real build (e.g. a P3 check), point `LOCALAPPDATA` at an empty
  folder for that one run, with the R5 jar copied in (done 2026-10-14).
- r5py copies each input to `%LOCALAPPDATA%/r5py/<file name>` only if no file of that name is there
  (`r5py/util/working_copy.py`, v1.1.7) and never refreshes it: same-named feeds of another release or
  variant silently load the old copy, and the network cache is keyed on that stale copy. Give every feed a
  unique name per release / variant and check the cached copy's digest (`transit_pathway_network_v2.py`,
  found 2026-10-19). Effect on recorded results: 1 pair of 2,210 by 1 min, no band call.
- DI's departure sampler (R5 jar r5-v7.5.1-r5py, bytecode): step = W // D, half = step // 2, redrawn
  until exactly D draws, no attempt limit; at a 1-min window with 60 draws every step is 0 s (the heap
  error); 1-10 draws run at 1 min. r5py's egress search swaps the split edge's start vertices but not
  their costs (DI's egress off by +-(d0 - d1)). Detail: T7 (e).

## Open questions
- DESIGN.md Q7 (r5py rebuild), Q18 (transit departures), Q22 (route preference), Q23 (band metric, top-up).
- **T1.** ~~Transit direction~~ Settled (user, 2026-10-13): hex → venue, like drive (ODS-2).
- **T2.** The old transit sample's file: unseen (flag). The user will look for it; not needed for
  validation, which uses a new fetch under the Q18 protocol.
- **T3.** ~~Train / test or validation only?~~ Settled 2026-10-13 (user): split at the draw like
  ODS-9 (seeded, grouped by destination hex, written once), even if nothing is fitted; splitting after
  results would be peeking.
- **T4.** ~~Sample size~~ Settled 2026-10-14 (user): 1,000 / 1,000 usable pairs, ~2,500 drawn to
  absorb exclusions, plus the T5 smoke test. Extended for the test half by TRN-15.
- **T5.** ~~Out-of-window share?~~ Settled 2026-10-13 (user): ~5% of pairs drawn outside the r5py
  window (flagged), a smoke test of r5py's "unreachable", separate from training and test.
- **T6.** ~~Worker tilt: limitation or quotas?~~ Settled 2026-10-16 (user): stated as a limitation, no
  quotas, error reported per pool (Limitations).
- **T7.** ~~Route preference~~ Closed 2026-10-20 with DESIGN Q22 (user); opened 2026-10-16. Google's planner trades time for less
  walking and fewer boardings; r5py's TravelTimeMatrix returns the fastest trip. We match Google, not
  real behaviour. Outcome so far: stock R5 stands for time (TRN-13); path dropped (TRN-12). Sub-items,
  shortened (full text in the snapshot):
  (a) Method: ride caps (`max_public_transport_rides`), route at k = 0..3 and choose the k with the
  least T_k + α·k. (b) Parameters: one α or two, grid fit on the training half. (c) Independent check:
  Google's primary vs alternatives give inequalities on α. (d) Adopt only if r5py's gap to Google grows
  with the number of legs, judged by the effect on reachability. None of (a)-(d) adopted (see (h)).
  (e) Preconditions and r5py checks (2026-10-16 / 17): ride-cap matrices ~1 s each, boardings from the
  caps; DI's heap error and one-result-per-departure collapse explained (Notes; TRN-6); TTM at a 1-min
  window SOUND (`transit_narrow_window_soundness.py`, 594 of 600 exact); the DI-TTM gap is DI's egress
  walk (`transit_router_egress.py`); walk speed is part of the TTM-Google gap (`transit_walk_speed_lead.py`,
  WLK-1); R5's 60 s board slack measured SMALL (`transit_board_slack.py`, band 2 +1.76 pp), stock R5
  kept, the first-board removal is the no-wait correction (TRN-13).
  (f) Fit target (confirmed 2026-10-17, user): Google's default route's arrival from the requested
  departure; for TRN-13's test revised to the range (TRN-13 (b)).
  (g) Fit sequence (decided 2026-10-17, user): slack, default-route diagnostic, walk speed (4.16 km/h
  from Google's walk-only answers, WLK-1), penalty, scalar. Scalar s = 1.01, gain +0.02 min: s = 1
  stands (`transit_time_scalar.py`).
  (h) Default-route diagnostic (`transit_default_route.py`): earliest arrival picks Google's default on
  0.734; a walk weight w 2.0 with small boarding / transfer penalties explains 0.945: Google trades time
  mainly for less walking. Preference arms (`transit_preference_arms.py`): C (OTP defaults) and F
  (fitted) FAIL against stock R5 B; stock R5 stands; generalised cost not pursued (user).
  (i) Why C and F failed: slowed walking misses vehicles Google catches. OpenTripPlanner 2 not pursued
  (user). Candidates-then-rerank and the walk-or-transit switch-point fit closed with path (TRN-12).
  (j) Time and path measured on stock R5 (2026-10-18, training half): time band agreement 0.965 at 4.16
  km/h (`transit_time_bands.py`); path stop match 0.375 (`transit_stop_match.py`), walk overlap 0.338
  (`transit_walk_overlap.py`). Path closed 2026-10-18 (TRN-12).
  Prior art (from memory, unverified): generalized-cost routing with skimmed components (EMME, VISUM);
  RAPTOR rounds (Delling, Pajor, Werneck ~2012); fares in R5 (Conway, Stewart ~2019); transfer
  penalty estimates (Iseki, Taylor; Guo, Wilson; Wardman). No known study calibrating a router to
  Google with a fitted transfer penalty; search before claiming novelty. Searched 2026-10-21 (cursory, free web
  search, 55th): none found calibrating or patching R5 / r5py / OTP to Google; nearest Lahoorpoor & Levinson 2019
  (Sydney preprint: OTP ~2.8 min slower than Google's API, comparison only) and a 2026 Yamagata study (OTP, R5 vs
  a Japanese route service, ~70% match, walk-to-stop definitions the main cause). Not a Scholar search.
- **T8.** ~~Training size for α~~ Closed 2026-10-20 (user): moot, no α was adopted (T7 h); TRN-15's
  extension went to the test half only. (Opened 2026-10-16: a top-up to the training half if α needed
  more pairs.)

## Changes
- 2026-10-22 · TRN-16 / TRN-12 (69th, autonomous): holdout opened (facts recorded, reading owed); walk-pattern matching dropped (user), path-shape and aggregate results
- 2026-10-22 · TRN-16 holdout verdict (73rd, user): accepted; lost 20 a recorded cost
- 2026-10-22 · code cleanup (68th): later sets (reserve, test extension, holdout) screened, drawn and fetched by set name, run from `transit_collection.py`; outputs byte-identical; no position changed
- 2026-10-21 · TRN-16 / TRN-15 (66th): unseen destinations = 2,045 (user); patch rule zone gate; holdout fetched (4,000, sealed); buffer sweep flat, 200 stays
- 2026-10-21 · TRN-16 (65th): walk charge after routing tested, rule PASS but blanket shift (zones fail), not adopted; TRN-15 (9) unseen count traced (definition owed)
- 2026-10-21 · TRN-16 (64th): free check fails (P6 0.800, P5 + P6 0.813); P5 and P6 not adopted; walk weight a finding and a limitation; next freeze
- 2026-10-21 · TRN-16 (63rd): application planned: P5 exact transfer penalty (pick the round per stop), P6 two-run walk-weight pick; free check next
- 2026-10-21 · TRN-16 (62nd): Google's walk weight estimated, w 1.70 (1.55-1.95), stable; transfer penalty ~450 s report only; application open
- 2026-10-21 · TRN-16 (61st): (1) revised (user: Google is the fit target, training pairs, holdout checks); combos (no walk cap) and railtram (train vs tram is walk reluctance, no station time); early tail a stated limitation; 190 s buffer rechecked
- 2026-10-21 · TRN-16 (60th): stop links set aside; leg-by-leg error: same-line pairs unbiased, early bias is route choice (Google alternatives check); next: never-returned combinations
- 2026-10-21 · TRN-16 (59th): per-edge rounding confirmed (0.48 s per edge); P4 built, full training run WORSENS (23 -> 27), not adopted for now; next stop-link connectors
- 2026-10-21 · TRN-16 (58th): P3 adopted, patch 1 chosen over stubs, transfer speed parked, fork once frozen (user); P2 built, full training run equal to snapping (23 hard misses), adopted (user)
- 2026-10-21 · TRN-16 (57th): P3 full training run, IMPROVES (25 -> 23 hard misses); adoption and stubs vs patch owed
- 2026-10-21 · TRN-16 (56th, discussion): transfer-only walk speed recorded as a candidate (user leaning to test); policy status open
- 2026-10-21 · TRN-16 (55th): prior-work search (T7); Google's boarding rules measured (0 s first, ~200 s at transfers); P3 redefined (user), built and tested on 100 pairs (all equivalence checks pass); R5 transfer walk vs Google's; 190 s buffer Not adopted
- Changes to 2026-10-20 (TRN-1 to TRN-15, T1-T8): snapshot, "Changes".
- 2026-10-21 · TRN-16 P1 built and tested (54th): equivalence exact, stub comparison 3 / 100 (stub cause); stubs 29 s on 41 / 262 TTM calls; prior-work search and Google zero-wait transfer check added before P2 / P3 (user); per-edge rounding test; cap + 1 min flag
- 2026-10-21 · TRN-16 patch register and test plan (user, 53rd): seconds out instead of rounding in R5, no connector charge, board wait 0, three candidates; 100-pair steps, full training verdict, 1% minor-deviation flag; origin-wait patch Not adopted
- 2026-10-21 · TRN-16 added: R5 patch policy (user, discussion); screening window limitation extended to patches
- 2026-10-21 · TRN-6 comparison rule corrected to rounding (SCR-10; the floor line was stale); DI for second-level times added to Not adopted; offset route chosen (DESIGN Q24)
- 2026-10-21 · Limitations: access walk (WLK-6) added; truncation entry points to the DESIGN Q24 plan
- 2026-10-20 · TRN-13 no-wait gain clarified: up to a headway on transit trips, not 1 min (catchment sensitivity, RCH-13)
- 2026-10-20 · TRN-15 test opened once and concluded (user): pooled fail on z2 balance and false 20, a recorded cost; per-release severe flag on the test half ruled not a release failure (post-result reading); model of record kept; 30 s shift parked; Limitations entry added; unseen-subset count owed
- 2026-10-20 · TRN-13 own-date scoring done (verdicts unchanged) and station fidelity check done (no fix, stated cost; all-stations read-out); TRN-11 scope text reworded to the code (user); Not adopted and Limitations entries added
- 2026-10-20 · TRN-15 test reading rule revised before opening (user): hard misses on the training bar, Claude's comparison criterion dropped; pooled verdict, count ratio and thirds fixed, noise bar on the test's own pairs, medians; destination overlap stated (Limitations), unseen-destination subset report-only; order: predictions, scorer check, open
- 2026-10-20 · compacted: history, superseded steps and intermediate results moved to the snapshot; IDs and cited sub-labels kept; dropped options gathered under Not adopted (no position changed); T7 closed with DESIGN Q22, T8 closed as moot (user)
- 2026-10-22 · TRN-16 P7 in-seat continuations (77th built, 78th run): measured, not adopted; no band flips; Limitations entry (user OK)
- 2026-10-23 · TRN-16 (80th): P7 to be adopted once a test-fetch budget opens (user); P8r reporting patch built and tested; patch and jar naming (user); route-choice framing in Limitations (FRM-24)
- 2026-10-23 · TRN-16 (81st discussion): P8r adopted for the reachability pass (draws mode; bitmask deferred)
- 2026-10-23 · TRN-16 (82nd discussion): draws mode capped at 5 minutes per call (found); P8r extension decided (cap lifted, <= 90-min chunks)
- 2026-10-23 · TRN-16 (83rd build): P8r draws extension built and tested
- 2026-10-23 · TRN-16 (86th): production jar name `r5-v7.5.1-r5py-all_p8-r_draws.jar` confirmed (user)
