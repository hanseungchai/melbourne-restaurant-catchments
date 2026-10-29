# OD sampling and Google ETAs

**Purpose and scope.** How the drive validation pairs are drawn, how their Google times are fetched,
joined and split into train / test, and the older 1,680-call sample they replaced. Not what the pairs
are used for: fitting, guards and the test-half result (drive calibration doc), the speed models (drive
model doc), hex → node snapping (graph doc), transit and walk ETA protocol details (transit doc,
`walk.md`), allowances and the ledger (`api-cost.md`).
**Stages.** `sample_drive_pairs` (cleaned): `random_sampling`, `draw_second_drive_set`,
`fetch_second_drive_set`, `join_drive_sets`, `split_drive_pairs` in `drive_samples.py`.
**Last reviewed.** 2026-10-13, ee0fc18
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/od-sampling.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **ODS-1.** Two draws of 4,000 pairs each, pooled (8,000). Draw 1 (seed 20260930) is frozen in
  `frozen_inputs/routes_drive_eta_20260930/`; a redraw only checks it reproduces. Draw 2 (user,
  2026-10-10; seed 20261010) uses the same sampler, `draw_no` from 100,001, and rejects any
  origin-hex/destination-hex pair of draw 1. Pair count fixed before drawing, sized to the allowance
  (user, 2026-09-30).
  Evidence: config `ROUTES_DRIVE_*`, `ROUTES_DRIVE_DRAW2_*`; frozen_inputs/README.md. DESIGN_pre_spine "Drive
  layer" (Validation sample); `trim_check_and_sample_plan_Sep_30` L78.
- **ODS-2.** Direction hex → venue, as in the reachability pass (drive times are asymmetric). Origin:
  pool residents or workers with p = 0.5, then a hex weighted by that pool's count; pool stored per
  pair. Destination: a venue drawn uniformly over unique place IDs (= hexes weighted by venue count),
  from `VENUE_TABLES[HEX_VENUES_DATE]`; 532 venues beyond `VENUE_HEX_MATCH_RADIUS_M` of any centroid
  are not drawable. Ends drawn independently. Plain weighted draw: no stratification, no distance
  quotas, so the sample is self-weighting.
  Evidence: `drive_samples.random_sampling`; sample logs. `rerun_design_Sep_29` L72-92; `sampling_delta_Sep_30` L25-30.
- **ODS-3.** Window: a pair is kept only if reachable within 25 raw minutes on blind at β = 2 (the
  OSRM convention, not a model under calibration). Selecting on a model's predicted time is selection
  on the regressor: it does not bias the fit, but results describe the window only. ~25 raw min ≈
  40+ Google min on old data (blind raw ~1.7× faster).
  Evidence: none (reasoning; the 1.7× rests on the old 537 pairs). `rerun_design_Sep_29` L100-111;
  `sampling_rethink_Sep_27` L88-94.
- **ODS-4.** Rejections, in order (log key): same hex (`same_hex`); hex pair in an earlier draw
  (`old_hex_pair`); repeat (origin hex, place_id) (`duplicate_pair`); any shared eligible candidate
  node at both ends (`same_node`); nearest candidate-node pair farther than the graph's top speed ×
  window (`prefilter`; node coordinates, not centroids, which overstate by up to ~1.7 km); not reached
  in the window (`over_window`). Routing is multi-source over the origin candidates to the first
  destination candidate (1 m tie rule). The first 20 window searches are checked against networkx.
  Logged: draw 1 drew 10,617 (prefilter 3,034, over window 3,583; accept 37.7%); draw 2 drew 10,752
  (2,969; 3,781; 1 duplicate; 1 old hex pair; 37.2%). Same hex and same node: 0 in both.
  Evidence: `od_sample_log*.json` (outputs/pathing_calibration/<subject>/). `sampler_and_fetch_Oct_1` L43-57.
- **ODS-5.** Departures: weekday 30-minute slots, 80% from the open-share histogram, 20% flat over
  06:00-24:00; slot, then a uniform minute, on its own RNG stream; `dep_p` stored per pair for
  reweighting. Draw 1 used the 2026-09-02 hours, draw 2 the 2026-10-10 hours. The hour mix is supply
  (opening hours), a stated proxy for demand. Date: the next local date after the fetch day on the
  drawn weekday, plus a seeded week offset within 52 weeks (Routes refuses past departures for DRIVE).
  The 20% floor buys coverage of 06-09 and 21-24, where Google vs blind differs most from midday, at
  about 3% effective sample size if reweighted to the hours; its effect on a single-factor fit is ~0.4%
  of trip time. Pooled weights, if used: target hours ÷ the mean of the two draws' `dep_p` rules.
  Evidence: draw 1 fits the 80/20 rule (chi-square p = 0.27, 240 day × slot cells), DESIGN_pre_spine "Drive
  layer". `sampler_and_fetch_Oct_1` L82-88, L125-129. Open: DESIGN.md Q10 (drop the floor), Q13, Q17.
- **ODS-6.** Fetch: one Compute Routes Pro request per pair, `TRAFFIC_AWARE`, alternatives on, Google's
  default route kept; origin = hex centroid, destination = the venue's coordinates. Field mask keeps
  duration, staticDuration, distance, polyline, route labels, snapped leg start / end, description,
  warnings. Every raw response saved; ledger-guarded and resumable. Draw 1: 4,000 calls, all HTTP 200
  (2026-09-30 18:23-19:07 UTC, inside the September allowance).
  Evidence: `drive_samples.DRIVE_FIELD_MASK`, `fetch_drive_eta`; frozen_inputs/README.md.
- **ODS-7.** Target: Google's traffic-aware `duration`; `staticDuration` secondary (user, 2026-10-07).
  Evidence: none (definition). `valhalla_engine_test_Oct_7` L43.
- **ODS-8.** Join (`join_drive_sets`): each draw with its latest fetch per pair (HTTP 200 row if
  any), failed or zero durations dropped, each end's snap nodes attached from the hex nodes table; one
  column schema. Replaces the Oct 1 hand join and rename.
  Evidence: code. `od_sample_reproducibility_Oct_1` L44-52.
- **ODS-9.** Split (`split_drive_pairs`, seed 20261011): one train / test cut of the pooled pairs,
  stratified by draw and grouped by destination hex, then 5 grouped CV folds inside the training half;
  written once and never rebuilt (the test half must stay the same pairs). Result: 3,999 train /
  4,001 test. Grouping by destination hex also keeps every hex pair inside one half.
  Evidence: code; DESIGN_pre_spine "Drive layer" (Train / test scheme). DESIGN.md Q2 (closed).
- **ODS-10.** The old 540-pair drive set (and the 1,680-call collection it belonged to) is not pooled
  with the new draws, not routed, and not frozen; it is set aside for the diagnostics stage. Pooling
  would bring back its sampling flaw (origins at venues, distance quotas).
  Evidence: frozen_inputs/README.md (not frozen); DESIGN_pre_spine "Drive layer"; `hex_block_Sep_27` L253-264.
- **ODS-11.** Drive top-ups (planned, not built; long-term maintenance after outputs, for more pairs or
  data added by others). Rolling test: each new drive fetch becomes the test set; every earlier pair,
  the previous test set included, joins training. ODS-9's split stands until the first top-up. An hours
  refresh (VEN-15) comes before the draw it feeds; new draws exclude hex pairs of every earlier draw.
  Destination hexes may repeat (excluding them would push tests toward sparse hexes: 3,943 of 8,959
  venue hexes used by draws 1-2), so generalisation to unseen hexes rests on grouped CV inside training
  (DCL-15). Code handles exactly two draws: per-draw config, draw and fetch functions,
  `default_drive_sets`, the exclusion list in `random_sampling` and the write-once split need generalising.
  Evidence: none (decision, user 2026-10-13); hex counts from the split file and hex venue counts layer (output check 2026-10-13).

## Not adopted
- Density-stratified draw with inverse-probability weights, and the tier-count stopping rule (route-length weight w = L_T² / ((e·L)² + σ_c²)): a second stratification the within-band analyses don't absorb; superseded by the plain draw. `OD_density_sampling_Sep_27` L15-35, L72-107.
- Pilot fetch of 100-200 pairs: spends allowance to learn what local routing shows free. `OD_density_sampling_Sep_27` L30-32.
- Haversine-band quotas and the Sep 26 outer fetch / top-up: replaced by the self-weighting draw. `OD_resample_Sep_26` L29-124; `rerun_design_Sep_29` L72-74.
- Uniform OD: ~92% of hexes are rural but hold ~15-18% of residents and workers. `rerun_design_Sep_29` L89-92.
- Origin first, then a destination inside its reachable set: over-weights origins with few reachable venues. `rerun_design_Sep_29` L114-116.
- Topping up with old pairs when short of allowance: makes the sample's make-up data-dependent. `hex_block_Sep_27` L147-149.
- An A/B label at draw, or a stored U(0,1) cut fixed later: superseded by the grouped split (ODS-9). `trim_check_and_sample_plan_Sep_30` L85-87.
- Fetching one half per billing month: confounds halves with month. `trim_check_and_sample_plan_Sep_30` L92-93.
- Rural top-up draw after the rural guard failed: data massaging (DESIGN_pre_spine "Drive layer", 2tier's rural failure).
- Selecting pairs or sample size after seeing results: forking paths. `trim_check_and_sample_plan_Sep_30` L83-84.

## Limitations
- Results describe the 25-raw-minute window only; accuracy figures are not population-representative. `sampling_rethink_Sep_27` L92-94.
- Weekday only: weekend reach is not estimated rather than estimated badly (weekend transit is
  thinner, weekend demand plausibly higher, and the worker pool says where people work, not when).
  Drive follows transit's weekday so the bands describe one day. The open-hours histogram has
  weekend rows; the sampler drops them. Framing risk (user, 2026-10-13): weekdays
  are most days, so the insight should hold in general, but some venues' demand peaks outside them
  (weekend days, some weekday nights); present as a representative weekday. rev4 L1410-1413; `departure_noise_floor_Oct_4` L59-60.
- Departure hours are supply-based (opening hours), not demand; ALPHA averages over the sampled mix. Q17's factor references that mix. `sampling_delta_Sep_30` L65-66.
- Rural and fringe trips are sparse in proportion to their people and venues (pairs at least half rural: 40 of 1,228 near the cut). `rerun_design_Sep_29` L93-94; DESIGN_pre_spine "Drive layer".
- Same-node and same-hex pairs are excluded though they belong to the reachability population (0 rejected in both draws, so no cost here).
- Google's trip ends and ours differ: Google gets the venue's coordinates and snaps to its own nearest road; our route ends at the venue hex's snap node. Not measured as a separate error. DESIGN.md Q12; `polyline_regression_idea_Oct_3` L178-180.
- Google noise (snap sensitivity, traffic) dominates sampling error past a few thousand pairs. `trim_check_and_sample_plan_Sep_30` L82-83; `TEMP_workplan_Sep_22` L35-39.

## Notes
- The old collection (rev4 §7): 1,680 calls (drive 540, walk 600, transit 360, transit short 180),
  origins at venues, venue → people; set aside (ODS-10). Detail: snapshot, Notes; rev4 L1104-1131.
- Precision guide (residual SD ~15%): a 300-pair subgroup's median error ±2 pp, 100 pairs ±3.5 pp.
  Claude's rough figure, not a diagnostic. `trim_check_and_sample_plan_Sep_30` L80-81.
- The departure noise floor (Q10) can be computed free: `staticDuration` is in the field mask.
  `departure_noise_floor_Oct_4` L45-49.
- Two-candidate hexes: the log counts 34,001 (0.8%).

## Open questions
- DESIGN.md Q10 (drop the departure floor in a future draw), Q12 (snapping), Q17 (time-of-day factor),
  Q18 (transit departures and pairs, protocol decided 2026-10-13: TRN-7, TRN-10), Q20 (top-up scheme details).
- **O1.** `u_grp` (one U(0,1) per hex pair) is still written at draw but no longer read: the split
  uses destination-hex groups. Leave it (it is in the frozen draw 1 file) or drop it from new draws
  when `drive_samples.py` is next touched? Claude: leave it; dropping it changes draw 2's file.

## Changes
- Changes to 2026-10-20 (ODS-1 to ODS-11): snapshot, "Changes".
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
