# Drive model

**Purpose and scope.** What a modelled drive time is made of: base edge speeds, the density tier of
an edge, signals and β, ALPHA, the routing engine, the variants built, and why no speed table or
outside engine sets speeds. Not how parameters are fitted, how models are compared or the results
(drive calibration doc, DCL), nor the graph, split and snap (`graph.md`), the density measure
(`density.md`) or the validation pairs (`od-sampling.md`).
**Stages.** `build_speed_graphs` (`speed_graphs.py`; STATUS cleaned); routing inside
`calibrate_pathing_agent` (`pathing_calibration.py`, `functions/drive_routing.py`; STATUS todo).
**Last reviewed.** 2026-10-13, 56a5493
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/drive-model.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **DRV-1.** The selected model is **2tier** (the fitted density model; user, 2026-10-12): edge time =
  blind time (DRV-2) × m on every edge whose start node is at density level 15, motorways included
  (`DRIVE_FIT_EDGE_SET = "all"`), blind time elsewhere; plus β per signalised head node; predicted =
  ALPHA × routed time. Fitted on the whole training half: m 1.396 (so tagged non-motorway streets run
  at 0.57 × posted, motorways at 0.72 × posted), β 16.1 s, ALPHA 1.197; the five CV folds agree
  (m 1.38-1.42, β 15.7-16.5, ALPHA 1.19-1.20; fold 3 unconverged, K3). How it was fitted and chosen: DCL.
  Evidence: `outputs/pathing_calibration/fit/<subject>/20261012/test/2tier_all_training_params.json`,
  `20261011/all/2tier_fold*_params.json`; DESIGN_pre_spine "Drive model selection".
- **DRV-2.** Base speeds (`blind`, M0; every model scales these): a tagged edge runs at its posted
  limit × 0.8 (`POSTED_SPEED_FACTOR`, OSRM `car.lua`'s speed reduction: a stated convention, not
  measured); motorway, trunk and their links at the posted limit (`UNREDUCED_HIGHWAY_TYPES`); an
  untagged edge at its class's `car.lua` default (`DEFAULT_SPEED_KMH_BY_HIGHWAY`; links fall to the
  parent class, unlisted types to `service`, 15 km/h). `maxspeed` is read with a km/h unit as well as
  a bare integer (the legacy parser's gap: DEPRECATED.md, snapshot). `osmtable` ignores `maxspeed`.
  Evidence: code (`speed_graphs._assign_speeds`); `diagnostics/drive_speed_limits.py`.
- **DRV-3.** An edge's density tier is its **start** node's level, as in Valhalla (`graphenhancer.cc`;
  the "end node" comment in `speed_assigner.h` is wrong). Every node gets a level from the raster
  (DEN-4); nodes outside it get level 0. The fitted model and every variant use this rule.
  Evidence: Valhalla source, read Sep 29 (`road_density_speed_Sep_29` L70); code. No diagnostic.
- **DRV-4.** Signals: nodes tagged `highway=traffic_signals` in the graph's own extract (asserted).
  Sep 29 build: 12,975 in the PBF, 12,696 (97.8%) on graph nodes; the 279
  missing are unverified. Split nodes never carry a signal. Stop signs are collected and printed,
  never costed. Pedestrian crossings tagged only `crossing=traffic_signals` are not collected.
  Evidence: enrich printout (run output only: D1 gap); `probe_router_Sep_30` L42-49.
- **DRV-5.** β is charged once per signalised node a route arrives at (the edge's head node,
  `apply_signal_penalty`); the start node is never charged (`count_signals` counts `path[1:]`), so
  signal time = β × count and the fit's regressor matches the router. Endpoint effect ≤ 2 s per trip
  at β = 2. β is baked into the routing bundle as `time_total_s_b<β>`.
  Evidence: code; `probe_router_Sep_30` L56-63; `sampler_and_fetch_Oct_1` L58-62.
- **DRV-6.** Signals are the headline drive finding: a cost that does not scale with distance. What is
  identified is the term's presence more than its value: distance-only predictors cluster within
  0.011 AUC (haversine 0.837, Google route distance 0.826, graph distance 0.829) while the
  time-weighted model with β reached 0.910; β 2 → 12 bought ~3.8 pp MedAPE and 0.029 AUC; β 10-20
  could not be told apart on 537 pairs. The fitted value (~16 s) sits inside the 10-20 s literature
  range; Google's own time carries ~22 s per signal (static; 24 s traffic-aware).
  β means signal delay; fitted, it also absorbs junction friction at signals (user, 2026-10-13; D4).
  Evidence: rev4 L527-556, L1197-1216 (Sep 19-21 tables, no files; old 537 pairs, M0 family);
  `diagnostics/google_slowdown_by_density.py` (`detour_junctions_google_density_Oct_8` L148-151).
- **DRV-7.** ALPHA scales routed graph time to Google time. It is a stated correction factor that
  absorbs unmodelled duration (turns, trip ends, the overall traffic level), reported as such, not
  engineered away. Every ALPHA (fitted model, blind, Valhalla) is fitted by the robust loss on
  log(predicted / Google), jointly with m and β where they exist (the legacy median ratio: snapshot).
  Evidence: code (`_fit_params`, `_fit_alpha`); rev4 L518-525; `session_findings_Sep_17` L124-126.
- **DRV-8.** The model is departure-time-blind and fitted to Google's traffic-aware `duration` (not
  `staticDuration`, though both are stored). Time of day enters later, per venue, in the reachability
  pass (DESIGN Q17), not in the drive model.
  Evidence: code (`GOOGLE_DURATION_COL`); DESIGN_pre_spine "Settled in chat" (Oct 1); Q17.
- **DRV-9.** No turn delays or penalties: not feasible at this scale; fitted speeds and ALPHA absorb
  turn cost, accepted because the goal is classification at the cut, not physically exact speeds.
  Evidence: none (decision). DESIGN_pre_spine "Settled in chat"; rev4 L1540-1541; `polyline_regression_idea_Oct_3` L203-205.
- **DRV-10.** Routing: own drive graph, scipy `csgraph.dijkstra` on CSR arrays (one bundle per timed
  graph and β set, memory-mapped, shared by 8 workers; more gave no gain), one multi-source search per weight with a cost
  cut-off; ~14× faster than networkx (19 s vs ~264 s per 200 draws); routes equal networkx's (200-pair
  check; a 20-pair parity check runs at every bundle build). A trip starts on any of its end's
  eligible snap nodes (1 m tie window, GRF-4) and connectors cost nothing (GRF-7).
  Evidence: code (`_check_bundle_parity`); `sampler_and_fetch_Oct_1` L63-77; DESIGN_pre_spine "Drive layer".
- **DRV-11.** Not an outside engine. Valhalla: the pipeline keys every output on node IDs it owns
  (hex snaps to graph nodes); opaque (six-plus Sep failures caught only by reading its code);
  reachability needs stored one-to-many costs so each counterfactual is a re-threshold, which its
  matrix and isochrones don't give; its junction costs would make signals unidentifiable. Measured:
  close to the fitted models, not better (training half 0.9040 vs 2tier 0.9255, gap CI −2.9 to −1.4 pp).
  OSRM: contraction hierarchies fix weights at build time (a β sweep re-preprocesses) and a node signal
  penalty isn't expressible per edge in Lua; its `car.lua` speeds are kept as a published input; the
  costing is in-house because it is the research object.
  Evidence: `valhalla_position_Sep_21` §4, §7 (L61-126, L184-209); `diagnostics/valhalla_vs_google_drive.py`.
- **DRV-12.** No speed table sets the model's speeds. Trace-derived tables (OpenStreetMapSpeeds AU-VIC)
  average signal stops into a per-km speed, so adopting one pushes β to 0 and the signal finding
  becomes unidentifiable; also method and sample size unpublished, values noisy (secondary above
  primary), traces of unknown hours, file dated early 2022. On Sep 19, swapping it for `car.lua`
  defaults (×0.5 dense tier held) moved AUC and ALPHA essentially not at all. The table survives only
  as the `osmtable` control (β 0 or 2, never fitted) and inside Valhalla's density-aware control.
  Evidence: `STALE_critique_and_speed_table_retirement_Sep_18` L45-74; `valhalla_position_Sep_21`
  L40-59; rev4 L1663-1665 (no file).
- **DRV-13.** `build_speed_graphs` writes four timed graphs: `blind` (convention control at β 2; the
  base the fit scales, `DRIVE_FIT_BASE_VARIANT`), `osmtable` (speed-table control), `dense` and
  `dense_fringe` (legacy M2 variants: tagged non-motorway edges × 0.5 at level 15; dense_fringe adds
  × 0.92 on levels 12-14, `FRINGE_FACTOR`, hand-set). `DRIVE_RUN_BETAS` routes all four; the fitted
  models route on blind's bundle with their own weights. Edge tier labels (`density_tier`, from the
  start node): `dense_urban` (15), `fringe_urban` (12-14, dense_fringe), `below_dense_urban` (0-14),
  `below_fringe_urban` (0-11, dense_fringe); `osmtable` keeps Valhalla's `rural` / `suburban` / `urban`.
  Evidence: code; config "Build speed graphs", "Routing runs".

## Not adopted
- Valhalla or OSRM as the engine: DRV-11.
- Any speed table as the model's speeds (AU-VIC, Valhalla's hardcoded urban table with US mph conversions, 89 km/h = 55 mph): DRV-12. `valhalla_position_Sep_21` L54-56.
- A per-edge Google speed table (one Routes request per sampled edge, class × density tercile): wrong-carriageway snaps, junction delay leaking into edge times, selection toward long control-free edges, rounding (~±7% on 100 m). `STALE_google_speed_table_rejected_and_eta_metadata` L26-41.
- Google aware/unaware ratio as speed or density factors: `TRAFFIC_UNAWARE` is time-independent average traffic, not free flow; the ratio is mostly time of day. `departure_noise_floor_Oct_4` L14-20.
- A density factor derived from TomTom (0.8 × 1/1.529): 0.8 is itself unverified; congestion 52.9% is a loose external comparison only. rev4 L656-657; `speed_variants_pending_Sep_26` L29-31.
- The ×0.5 factor network-wide (worse on every metric); VIC arterial ratios as speed factors (double-count signals with β); `valhalla3`, `hybrid_sliding`, `hybrid_calibrated` variants (dropped Sep 29). rev4 L616-618; `drive_rerun_handover_Oct_1` L94-99; `rerun_design_Sep_29` L28-32.
- Per-road factors (thousands of parameters from ~4,000 trips) and a flat per-junction delay (Oct 8 test: pre-registered C1-C3 all fail). `polyline_regression_idea_Oct_3` L154-155; `detour_junctions_google_density_Oct_8` L78-92.
- Charging the start node for signals: a model change, not a logging fix. `probe_router_Sep_30` L63.
- A per-trip intercept in the model: "M2 + intercept" (~250 s) was never pre-registered; the Sep 22 M1 intercept was unstable across folds (+113 s / +49 s). Google's own per-trip overhead is ~150 s static. DESIGN_pre_spine "Settled in chat"; `s4_verdict_Sep_22` L28-29; `detour_junctions_google_density_Oct_8` L154-155.

## Limitations
- One density factor for every road class: Google's dense slowdown is ~1.5× on motorways, ~2-3× on arterials, ~1.2× on residential (DESIGN Q15, first answer 2026-10-12). Not yet acted on.
- Route choice: our routes leave ~38% of Google's length off our route under every variant, though Google's polyline lies on our graph for 99.4% of its length; fitted variants over-use motorways. Times may be right on the wrong roads. DESIGN Q16. Not
  ours alone (2026-10-14): 11 models miss 34.5-38.6% of Google's length, Valhalla defaults best,
  2tier/3tier/4tier worst, and per trip it is the same route or a whole different one.
  `diagnostics/route_match_vs_google.py`.
- Google is the target, not ground truth: a point estimate with unmeasured spread (465-1,021 s within one 1 km band); error is agreement with Google. rev4 L1375-1379.
- Google picks fast routes, so anything fitted to its routes describes the best of each cell. `polyline_regression_idea_Oct_3` L159-162.
- 279 PBF signals not on graph nodes, and signal-crossing tagging, unverified (DRV-4).

## Notes
- Lineage, Sep 16 to Oct 12 (`car.lua` model, CBD box, M2, connector fix, dense_fringe, Valhalla
  tests, fitted round): snapshot, Notes. No position rests on those figures.
- Melbourne grid argument (Sep 17): delay sits at intersections, so an explicit signal count is the
  instrument; European centres would favour speed tables. `session_findings_Sep_17` L157-163.
- User's experience (Oct 1): inner-ring speed is capped by signals; a flat β already gives a
  spacing-driven cap (average speed = L / (L/v + β)). User expects the true density curve to be convex
  (congestion compounding with density); no evidence. Tram arterials as non-signal friction
  (Claude's idea), untested. `drive_rerun_handover_Oct_1` L84-93; `speed_variants_pending_Sep_26` L37-39.
- Valhalla's own junction charge is small (signalised mean 1.34 s, median 0.04 s); within Valhalla,
  junctions per km, not area density or motorway share, drives the remaining distance bias. Exploratory,
  nothing carried to our model. `diagnostics/valhalla_vs_google_drive.py` (steps 4a-4c); `valhalla_road_mix_Oct_8`.
- Victorian AADT and SCATS traffic data exist; not used (`density.md` Notes).

## Open questions
- DESIGN.md Q15 (class split inside a tier), Q16 (route-choice gap), Q17 (per-venue time-of-day factor).
- D1-D5 answered by the user 2026-10-13 (full answers: snapshot, Open questions):
  **D1** ALPHA fitted by the log-ratio loss (DCL-3); **D2** DESIGN follows the code;
  **D3** the write-up name is `2tier` ("the M2 fitted model" in conversation; "M2" in docs = `dense_fringe`);
  **D4** β is signal delay and, fitted, junction friction at signals (DRV-6; D1 gap: the "β turn-friction
  check" in DESIGN Q16 is planned, not run); **D5** `dense`, `dense_fringe`, `osmtable` kept as routed,
  unscored references, not controls (DCL-6).

## Changes
- Changes to 2026-10-20 (DRV-1 to DRV-13): snapshot, "Changes".
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
