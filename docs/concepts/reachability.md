# Reachability

**Purpose and scope.** The reachability pass: bands and cutoffs as thresholded, engine, storage,
guards, competitor horizons, and the flat-accessibility counterfactual (R̄) with the measures built on
it. Not the choice rule or the four-corner design itself (`scoring.md` SCR-2 to SCR-9), the drive
model behind band 3 (drive model / drive calibration docs), nor walk and transit routing (`walk.md`,
transit doc).
**Stages.** The reachability pass (not yet in `main.py`; next after `calibrate_pathing_agent`).
**Last reviewed.** 2026-10-13, a80e51b
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/reachability.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **RCH-1.** Three bands: 1 walk + public transport ≤ 600 s; 2 walk + public transport ≤ 1,200 s;
  3 drive, 20 min predicted. Band 3 claims nothing about delivery. Band edge convention open (SCR S1).
  Each band is a diner travel tolerance, not a prediction of what Google shows (`scoring.md` SCR-1).
  Evidence: none (definition). DESIGN_pre_spine "Scoring model"; rev4 §4.1, §4.4.
- **RCH-2.** Band 3 runs the selected fitted drive model (2tier) on the project's own drive graph, not
  Valhalla or any other contender. Dijkstra accumulates raw time; predicted = ALPHA × routed, so the
  cut is routed time ≤ 1,200 / ALPHA. Connectors (point to road) are free, as in calibration, so the
  pass thresholds the same network-only quantity the model was calibrated on.
  Evidence: DESIGN_pre_spine "Drive layer" (selection, user 2026-10-12; contenders confirmed by the user
  2026-10-13). rev4 L511-516; `connector_convention_Sep_21` L139-152; FRM / WLK-3 (Google's view).
- **RCH-3.** Bands 1-2 come from r5py on the OSM extract and the PTV feeds (`walk.md`, transit doc).
  Evidence: DESIGN_pre_spine "Walk and transit layer".
- **RCH-4.** One single-source search per venue node with a cutoff; store costs, not booleans, out to
  ~2.5× each band cutoff, so every counterfactual is a re-threshold, not a re-route. Stored at source-
  node level with a separate venue → node map (fan-out at scoring time); parquet written per batch.
  Engine: scipy `csgraph.dijkstra` on the timed CSR graph (the calibration engine). Not yet run.
  Evidence: none. DESIGN_pre_spine "Reachability pass and outputs"; rev4 L456-460, L2022-2027; `STALE_handover_rev3_7_delta` L226-234.
- **RCH-5.** Guards before the pass: assert node membership; hard-fail on skipped hexes; raise on
  missing attributes; record fallbacks separately; stamp a build record per artefact (graph path,
  mtime, source extract).
  Evidence: none. DESIGN_pre_spine "Reachability pass and outputs"; rev4 L2029-2035; `walk_highway_tags_Sep_21` L115-119.
- **RCH-6.** Every venue in the 100 km grid gets its own horizon; competitor sets are never truncated
  to the subject's reach (competitors need their own horizons).
  Evidence: none. rev4 L443-448; DESIGN_pre_spine "Settled in chat" (no clipping below 100 km); HEX-2.
- **RCH-7.** R̄ solve: P̄ = mean expected graph-reachable population per venue (each hex's population times the
  venue's band probability, RCH-23; wording 2026-10-23) (every venue weighted equally,
  outer venues included); bisect one haversine radius so mean disc population matches P̄; stop at ~1 m
  or 0.1% of P̄; boundary hexes weighted by area fraction. Solved independently per band (never scale
  one band's R̄ from another) and per denominator. Venues with zero reachable population are dropped
  and counted. P̄ estimated from a venue sample (RCH-24, plan).
  Evidence: none. rev4 L334-362; `STALE_handover_rev3_7_delta` L49-85; `OD_resample_Sep_26` L131-137.
- **RCH-8.** Never average an intermediate: mean speed fails (selection bias; no constant walk + PT
  speed), mean area closes the R² gap but not the density gap. R̄_area is a diagnostic only:
  R̄_pop / R̄_area is the density share of the catchment advantage.
  Evidence: none (reasoning). rev4 L344-357.
- **RCH-9.** R̄ equalises reach, not market: equal radii give equal area, and population still varies
  with density. The write-up says so.
  Evidence: none. rev4 L364-368.
- **RCH-10.** Accessibility advantage (primary): Default minus R̄ with reputation flat in both runs;
  repeated with reputation real, the gap being the interaction. It is relative (competitors gain too)
  and passes through the choice rule, so it is non-monotone in reach. Wording: "share of contested
  population a venue holds because of where the network puts it, relative to a field with no network
  advantage".
  Evidence: none. rev4 L377-395.
- **RCH-11.** Interaction residual = Real − flat-pop − flat-acc + both-flat. Positive: reach points at
  dense hexes; negative: good reach into empty hexes. Its sign is the franchisee-encroachment output.
  An upper bound, not a measurement: it absorbs all non-additivity, Top-N slot mechanics included.
  Evidence: none. rev4 L401-410.
- **RCH-12.** Flat population = mean population per contestable hex (SCR-11): a scalar for presentation only (puts
  runs in people, not hex counts); a scoring-time substitution, so only real and flat accessibility
  need reachability passes.
  Evidence: none. rev4 L325-330; `STALE_handover_rev3_7_delta` L29-30.
- **RCH-13.** Every output carries its uncertainty (user, 2026-10-12): an interval for each measurable
  source (drive-model error, the time-of-day factor, imputed hours, sampling noise), saying what it
  covers; sources that can't be measured (Google as ground truth, OSM completeness, the tag-based
  competitor set, the departure floor) are listed as limitations. Drive-model error is propagated by
  simulation: each trip's error drawn from the test-half residuals by tier (and band), reach recomputed
  per draw, reported as a median with an interval. The headline stays a clean Top-N at a stated
  confidence threshold, with the weighted numbers underneath. Bands 1-2: transit error drawn the same
  way from the transit test residuals (wording added 2026-10-20; implied before, not written). Listed
  limitation (user, 2026-10-20): location-specific transit error (e.g. weak stations, TRN-13) does not
  cancel across venues and can reorder competitors near those stations. Planned diagnostic after the
  transit test half (user, 2026-10-20; extra, not a gate): the subject's catchment totals (population,
  workers, venues within 10 / 20 min) under stock R5 vs the no-wait model, to size how much the transit
  model's misses matter to the output. Result (2026-10-20, census of 14,731 hexes within 5.5 km x 12
  departures from the week's open-share histogram, v2, release 20261016): no-wait over stock within 20 min
  residents +10.3% [9.6, 10.9], workers +16.4%, venues +16.6%; within 10 min residents +12.9%; worth about
  2 min of cut (+-1 min at 20: +4.1% / -6.0%). Reading (Claude's, untested; accepted by the user 2026-10-21): Google's catchment lies
  between the two (stock barred for lost reach, no-wait slightly generous, TRN-15), so band-2 totals carry
  about +-10% from the transit model (Limitations).
  Drive sensitivity (2026-10-22, report only; 102 venue hexes + the subject, ratio to the model of record): fit on
  the training half only 1.005; cut +-1 min 1.12 / 0.89 (~11% per minute, ranking unchanged); time of day at
  RCH-14 scale 1.34 (evening) / 0.87 (day); density factor off 1.04 [1.00-1.31]; signal penalty off 1.87; the
  selection control (blind_b2) 0.95 but [0.63-1.40] with venue ranking Spearman 0.73; uncalibrated speeds x3.0. The
  subject's worker catchment is the most fragile (CBD near 20 min). `diagnostics/reachability_drive_sensitivity.py`.
  Transit sensitivity (2026-10-22, report only; the subject's 5.5 km census, 5 departures inside its hours): frozen
  model within 20 min residents 35.8k (Sat 13:00) to 53.1k (Wed 19:00), Saturday ~25% lower; within 10 min x2
  between departures; cut +-1 min 0.93 / 1.13. Walk 3.6 km/h (r5py default) 0.86; stock R5 0.96 (10 min 1.11, part
  truncation vs half-up rounding); all defaults 0.77. Departure time moves bands 1-2 more than any model choice.
  `diagnostics/transit_catchment_variants.py`.
  Venue comparison (2026-10-22, report only; the subject, [subject] Melbourne Central, 6 random venue hexes in 3 rings;
  3 departures): drive residents within 20 min vary ~3x, transit ~16x (Melbourne Central 97k / 412k workers,
  subject 50k, outer ~6k); transit departure spread from 1.05x (Melbourne Central) to 2.6x (an inner venue); a
  Geelong venue is walk-only (regional buses not in the three feeds). The 5 km origin radius cut 5 of 8 venues
  (lower bounds). `diagnostics/reachability_venue_compare.py`.
  Evidence: decision none (DESIGN_pre_spine "Settled in chat"); catchment result
  `diagnostics/transit_catchment_sensitivity.py`.
- **RCH-14.** Per-venue time-of-day factor (DESIGN Q17; adopted by the user 2026-10-12, not built): the
  drive model stays time-blind (fitted on pooled hours); each venue's drive time is multiplied by
  exp(−f_venue), no rerouting. f_venue = mean a_band over the venue's open hours (VEN-13) minus the
  reference: mean a_band over the sample's own departures (both draws, weighted by `dep_p`), which
  cancels the 80/20 floor's level shift. a_band = the band's robust mean of log(predicted / Google)
  (positive: too slow). 2tier errs +21% at night (00-07), +13% evening, −5 to −8% day; a 5-band
  correction cuts out-of-fold loss (CI excludes 0); a density term adds nothing. Limitations: every open
  hour weighs the same (stated plainly, user 2026-10-22: per-hour congestion is averaged per venue, so a venue's
  quiet hours and its peak share one factor); night rests on 181 pairs; changes reach, not membership (gas stations −4%, ~1%).
  Evidence: `diagnostics/drive_time_of_day_factor.py`, `diagnostics/venue_hours_imputation.py`.
- **RCH-15.** Drive slice first (user, 2026-10-13: plan recorded, not built): band 3 alone, with the
  2tier all-pairs fit (`2tier_all_pairs_params.json`: the blind bundle, level-15 edges x m, + beta per
  signal), on the routed-time cut of RCH-2. Out of the slice: RCH-14, RCH-13, R̄ (RCH-7..12), the Q5
  flag (computable later from stored costs), bands 1-2. Code: stage script `reachability.py`, how in
  `functions/reachability_search.py`; its main.py block after `construct_pt_graph`.
  Evidence: none (plan).
- **RCH-16.** Source unit = venue hex, not venue: one multi-source search per venue hex from both its
  drive nodes, keeping the cheaper (calibration's best-node convention; check against
  `drive_routing.eligible_nodes`). 8,959 searches for 18,498 venues; venues in one hex share costs.
  Direction hex → venue (ODS-2, transit T1), so the search runs on the reversed graph.
  Evidence: counts from `venues_with_hex_ven20260925` (2026-10-13).
- **RCH-17.** Storage: costs per node, integer routed seconds, parquet per batch, with a venue → hex →
  node map; a hex's cost (min over its two nodes) is resolved at scoring time. The storage cutoff is
  set after a pilot of ~100 venue hexes (inner, mid, outer) reports rows per search, run time and disk
  size (DESIGN Q21); RCH-4's 2.5x (~2,500 s routed) is the starting point, and it must cover the RCH-14
  factor and the RCH-13 error draws.
  Evidence: none (plan). 4,078,906 grid hexes, the reason for node-level storage and the pilot.
  Pilot run 2026-10-22 (69th, autonomous; facts, the cutoff is the user's): 102 venue hexes, 34 per ring; 0.13 s
  per search at 2.5x (all 8,959 ~20 min, one process); node-level zstd parquet ~4.7 bytes per row: 6.0 GB at 1x,
  16.6 GB at 1.5x, 44.8 GB at 2.5x; per populated hex (>= 1 person, 521,044) 1.2 / 3.5 / 9.5 GB. Claude's reading:
  with searches this cheap a counterfactual can re-route, so RCH-4's 2.5x is not needed for speed.
  `diagnostics/reachability_drive_pilot.py`.
  **Decided (user, 2026-10-23, 79th; Q21):** store to RCH-4's 2.5x (~45 GB node-level) within a 200 GB disk
  budget; bloat is flagged in the run report for the user to prune.
  Run 2026-10-23 (83rd, production `reachability.drive_pass`): 8,959 venue hexes, 9.21 bn node rows, 45.7 GB at 2.5x
  (median 1.13 M rows per hex), ~45 min; edge flag (Q5; boundary = convex hull of the graph's nodes, Claude's reading
  of "outer boundary") on 16 venue hexes; the pilot's 102 hexes reproduced row for row
  (`diagnostics/reachability_production_checks.py`).
- **RCH-18.** Build stamp per run (RCH-5): bundle path and mtime, params file and its hash, commit,
  the config values used; a rerun reuses saved output only when the stamp matches (closes the
  stale-cache flag for this stage). Transit bands also stamp the GTFS release (export date), and
  their departure dates must fall inside that release's 30-day validity (TRN-3, TRN-7; user,
  2026-10-14). Production uses the newest GTFS release in inputs/ (user, 2026-10-23), the v2 pathways network
  rebuilt on it under a new r5py cache name.
  **No reuse of earlier data (user, 2026-10-23, 82nd):** production recomputes everything (network, oracle, drive
  pass); diagnostic and pilot outputs serve only as equivalence checks, since reusing them puts consistency in
  question. Reuse only inside production under a matching stamp: per-chunk checkpoints (resume), and the drive pass
  stamped apart from the GTFS release so a later transit pass keeps it.
  Built 2026-10-23 (83rd): `reachability.py` stamps each pass (inputs, config values, code hashes; commit recorded,
  not hashed); the production network on release 20261016 (`outputs/reachability/network/20261016/`) is byte-identical
  to the v2 diagnostic's (hubs, spurs, every feed table, the derived extract).
  Evidence: none (plan).
- **RCH-19.** Transit search cap for bands 1-2 (user, 2026-10-19; not built): r5py's max_time = 30 min, not
  the 20 min cut, so the uncertainty around the cut stays visible. On the 3,239 scored validation pairs (no-wait
  plain, v2), pairs Google reaches within 20 that the model puts over 20 sit at a median 22, p90 25, max 29 min;
  no pair over 30 is within 20 for Google (a 25 min cap would hide 2); 64% of those pairs lie beyond 30, the
  work saved. Also proposed for the pass (Claude, untested): one JVM fed large origin chunks (R5 threads a
  matrix over origins) rather than one JVM per worker process; timed on the pilot (Q21).
  Evidence: range results of diagnostics/transit_pathway_network_v2.py (2026-10-19), read in session; a
  diagnostic of its own is owed (D1) before the cap goes into code.
  2026-10-22 (78th, user): in the subject-scoped pass the cap stays R5's max time, but times in 20-30 min are
  complete only inside RCH-26's cut-30 set (enough for band 2's uncertainty; RCH-26).
  Timing pilot 2026-10-22 (69th, autonomous; frozen jar, v2 20261016, cap 30, one departure): 0.04-0.06 s per
  origin hex to all 8,959 venue hexes in 100-origin chunks; every populated hex ~5.5 h per departure time in one
  JVM, ~26 M rows <= 30 min. Each departure time multiplies it; outer origins reach almost nothing (median 3 venue
  hexes <= 20 min). The jar returns seconds. In 3,000-origin chunks 0.032 s per origin: ~4.6 h per departure for
  all populated hexes; a reach prefilter saves ~8% at most (5% of mid, 12% of outer origins reach nothing). The
  subject's hours at 10-min steps: 21 departures a weekday evening (~97 h), 187 a week (~860 h).
  `diagnostics/reachability_transit_pilot.py`.
  Cap diagnostic (2026-10-23, 83rd; frozen model, 12,677 scored pairs): of 1,936 pairs with Google <= 20 min, 4 have
  the model past 30 min (32-40; 0.21%), the tail RCH-26 prices as the shelf; Claude's zero-tolerance rule FAILs as
  written; cap kept at 30 (user's), stored to 31 min. `diagnostics/transit_search_cap.py`.
- **RCH-20.** Transit departure schedule for bands 1-2 (user, 2026-10-22, 70th discussion; decided 2026-10-23, DESIGN Q25): a 1-min
  departure scan is infeasible (~4.6 h per departure for all populated hexes, RCH-19), so the pass uses the coarsest
  schedule the data allows, leaning coarse, sensitivity kept light. Unit = the 30-min opening-hours slot
  (`HOURS_SLOT_MIN`); competitors' catchments only in slots overlapping the subject's (saves no compute: cost is
  origins x departures). Spans are defined from data: hours clustered by similarity of routed results on a small
  origin sample (hex -> venue; venues are destinations, never origins, user), with a GTFS service profile (vehicles
  in service, stop departures per hour) as a free companion; the schedule is picked from a cost / error table. Not
  pursued: R5's departure-window percentiles (a model change to the frozen 1-min window, TRN-6).
  Facts (71st, autonomous, report only): Mon-Thu timetables near identical (train Mon / Wed evenings and Friday
  after 18:00 differ); one 1-min departure varies within its hour as much as hours differ (noise floor 1.04 vs
  median hour distance 0.96 min), so the error is the single departure, not the span (per-origin reach <= 20 min
  ~17-23% median); at 1.0x the floor, 6 spans (weekday 06-20; weekday 21-23 with weekend day; night; 3 small);
  Claude's 1.5x rule merges nearly all. Subject's hours: 2 spans (~9 h) vs hourly every day 36 (~166 h); weekdays
  only, hourly, Mon-Fri as one 5 (~23 h). Open with Q25: weekend scope (od-sampling Limitations says weekday only),
  random weekday (user's idea), repeats per span (Claude's proposal).
  **Subject pass decided (user, 2026-10-23, 79th):** one departure per 30-min slot at a random minute in the slot
  (k = 1; repeats later), over the union of the subject's and branch's hours; four day types (Mon-Thu, Fri, Sat,
  Sun), one fixed date each inside the release's window; weekends included and labelled (DESIGN Q25).
  Departure sampling measured (80th, 2026-10-23, autonomous; facts, band 2, 8 venues x 4 day types x 6 departures per
  slot of the subject's hours): within-slot noise 16-40% of persons at most venues (4-8% central), slot means 3-14%;
  one departure per slot gives the subject's week headline +-3.7% (Neyman by day type 2.9%); slots look alike within
  noise, day types do not (Sat evening 3-20% below Wed); R-bar over 60 venues 0.53% at one per slot, 0.95% at one per
  span. **Spans as the unit (user, 80th: "that's the idea"):** departures drawn across spans, not one per slot;
  ~27 instead of 42 for the subject at equal error. Scheme still open (DESIGN Q25): random spans or span windows
  read exactly by P8r (TRN-16; ~57 single-departure equivalents for the subject's week, no departure noise). The
  "not pursued" line above is superseded for reporting: P8r changes what R5 reports, not the frozen times (user).
  **Scheme decided (user and Claude, 2026-10-23, 81st discussion):** (1) subject pass: whole P8r windows (draws
  mode) over the subject's own open hours, four day types, exact (~57 single-departure equivalents, ~4 h; RCH-21).
  (2) Hybrid targeting, the standing scheme for repeated passes (releases, sensitivity, other subjects) and a
  sibling's optional own base: the span(s) with the heavy week weight (Mon-Thu) read whole, one random-start 30-min
  window per other span, and any span flagged by a trip-count signal read whole (oracle set says where, GTFS trip
  departures per slot at its stops say how often; a step between a span's slots flags it; zero-wait oracle alone is
  fooled by one-off services). (3) R-bar sample: one random single per span (DESIGN Q26). Why: a window removes
  departure noise and cannot do worse in expectation than a single in the same slot, at any venue; what is left is
  between-slot variation in a span. Cost (week headline, band 2, persons / flat share, best estimate (upper)): hybrid
  ~23 singles, every venue <= 1.2 / 1.7% (<= 2.5 / 2.9%) vs one per slot (42) up to 6.7 / 8.0%, one 30-min window
  per span (16) up to 4.4% (<= 6.6%); two short windows beat one long. Limits: spans and rule read off the 8 venues;
  one 30-min window has no internal check (silent failure; the trip-count flag and the within-window trend answer
  it). Post hoc, not gates: the flag tested on the 8 dense venues, the within-window trend reading; dense reference on
  new venues optional. Figures from ad hoc scripts on the 80th's moments (`diagnostic_data/
  transit_departure_sampling_adhoc_20261023/`), to become a mode of `transit_departure_sampling.py` (D1, owed).
  On the subject's exact pass (86th, facts; Claude's pass line <= 2.9%, met; lines confirmed by the user): hybrid 0.71 / 0.72% (band 2, persons /
  flat share; 30 min 1.92 / 1.36%), one window per span 1.85 / 1.59%, one single per slot 2.86 / 3.14%. The trip-count
  flag fired on no span and no span's band-2 reach stepped > 10%: untested on the subject. No band-2 window drifts.
  Evidence: `diagnostics/transit_subject_pass_reading.py`, `diagnostics/gtfs_service_profile.py`, `diagnostics/transit_time_of_day_spans.py`,
  `diagnostics/transit_departure_sampling.py`, `diagnostics/transit_r5_patch_reach.py`.
- **RCH-21.** Subject-scoped transit pass (user, 2026-10-22, 72nd discussion; plan, not built): bands 1-2 route only the
  origin hexes that can reach the subject or its sibling venues (for [subject]: the Melbourne Central branch), to all venue
  hexes, so their shares are exact for the schedule and competitor sets stay whole (RCH-6). Any subject (user). Stage A, envelope: a forward search from each
  venue to all hexes at every scheduled departure (a cheap rough oracle; A -> B is not B -> A), cut at a liberal cap
  above the 30-min search cap (RCH-19), plus a ring buffer; margin set by the asymmetry check (RCH-22). Stage B: the
  envelope's origins to all venue hexes, cap 30 min; any outer-ring origin reaching either venue grows the envelope.
  Drive (band 3) needs no scheme: exact reversed search, full pass ~20 min (RCH-17). Schedule covers the union of
  both venues' hours (branch: 11:30-20:30, Fri / Sat to 21:30; pull 2026-10-10); cannibalisation read in hours both
  are open. Why: cost per departure falls from ~4.6 h (all populated hexes) to minutes (0.032 s per origin).
  74th: Stage A's oracle to be replaced by RCH-26's graph oracle if its superset check holds (margin and self-check
  then lapse).
  **Sibling scope narrowed (user, 2026-10-23, 81st):** a sibling (Melbourne Central) serves cannibalisation only, read
  inside the subject's envelope in hours both are open; its envelope leaves the subject pass and the schedule is the
  subject's own hours (halves the origins: ~9k vs ~17-20k at cut 30). Its own base (cannibalisation as a share of
  it) is optional: its other ~10k origins, overlap hours, hybrid targeting, ~1.7 h. Competitors: seen only from the
  subject's origins (cost is per origin, so all venue hexes come free); none dropped from the computation (SCR-14).
  ETA per pass (Claude's, 81st): timing run ~10 min, network + oracle ~10-20 min, subject ~4 h, drive ~20 min: ~4.5 h
  (~6.5 h with the sibling's base). Unmeasured: P8r past 210 min and at ~9k origins (timing run first).
  82nd (2026-10-23): the subject's windows are read in <= 90-min P8r chunks (TRN-16, draws cap), one envelope per
  chunk (oracle cut 30 in any of its slots); Claude's revised ETA ~3 h build + ~5-5.5 h runs (routing +15-30% for
  chunking, unmeasured).
  Built and timed 2026-10-23 (83rd): envelopes for the 16 chunks 8,591-11,652 origins (164,471 origin-chunks; per
  slot from the span oracle, saved with each slot's oracle seconds; equal to the saved oracle at Mon-Thu 19:30 and
  Fri 18:30); chunk 1 routed at 0.20 s per origin (90 min; ~0.4 GB per chunk); full subject pass ~8.3 h (not run).
  Run 2026-10-23 (85th, autonomous): all 16 chunks, folder `transit_86cb259c15` (5.4 GB), routing ~3.7 h with origins
  routed 12 at a time in one JVM (`REACH_TRANSIT_THREADS`; 3.1x serial, 8 threads 2.0x); threaded chunk 0 byte-identical
  to the serial run (5,968,414 rows, 0 differences). Readings (86th, facts): week headline 66.9k persons within
  band 2, 234.7k within 30 min; catchment along the tram corridor (routes 1, 6; user's prediction): 67% of band-2
  reach within 500 m of the routes vs 28% for a shapeless disc, axis ratio 2.1, 2 deg off the corridor. At 30 min reach
  rises 15-22% through every evening with origins near flat (heavier hexes later; unexplained). East-west, share
  falls off a cliff at ~1.6 km (walk to the frequent trams), then a bus-fed plateau (508, 506 every 18-30 min; ad hoc
  transect, Claude's reading).
  Evidence: `diagnostics/transit_subject_pass_reading.py`; timing RCH-19.
- **RCH-22.** Asymmetry check before Stage A's margin (user, 2026-10-22; planned diagnostic, D1): route a few hundred
  hexes both ways (venue -> hex, hex -> venue) at the same departures, transit and drive; the oracle margin is set from
  the upper tail of venue -> hex minus hex -> venue (the side that misses; first worded the other way round,
  corrected 73rd). Free (frozen model, own drive graph).
  Facts (73rd, 8 venues x 400 hexes, Wed 12:00 / 18:30, Sat 13:00): transit, among hex -> venue <= 30 min, venue ->
  hex is longer in 43%, q95 +8.0, q99 +14.2, max +23.4 min; missed hexes pooled / worst venue at margin 0 8.5% / 18%,
  5 min 2.9% / 8.6%, 10 min 0.9% / 3.4%, 20 min 0.06% / 0.5% (Claude's pre-set rule: 20). Saturday alike. Drive q99
  +3.2 min (rule: 3). **Decided (user, 2026-10-22): margin 10 min plus Stage B's outer-ring self-check** (~1.8x the
  30-min envelope area instead of ~2.8x at 20 min); whether the self-check recovers the misses is the next free test.
  Evidence: `diagnostics/reachability_asymmetry.py`.
- **RCH-23.** Uncertainty in the pass (user, 2026-10-22; plan; extends RCH-13): two sources, drawn apart so neither is
  counted twice. (a) Departure noise, measured against time: k repeat departures per span (RCH-20), spread reported.
  (b) Model error, measured against Google: residuals conditional on the predicted time (given an ETA, the error vs
  Google), drawn per trip by ETA bin from the test residuals. First numbers: transit SD ~1.4 min under 10 min, ~2.2 at
  10-20 (`diagnostics/detour_error_scope.py`). Stored times reach past the cut far enough for both (RCH-19 cap, Q21).
  (b) lives in one function in functions/ (user, 2026-10-22): inputs mode, predicted time, departure time, local
  service level (transit); returns the conditional error distribution (quantiles, draws) and the band probability
  (e.g. P(Google <= 20 | predicted 18.5)); model error only, (a) drawn apart. Service level per hour at the origin
  (departures within walk reach at that time), not the static `origin_trips` (flat across its quartiles on the
  holdout). Fit: a smooth model of log(model / Google) spread on ETA plus one or two inputs, checked out of fold;
  transit on test residuals, drive on test-half residuals by tier. Built after its diagnostic (RCH-25 order).
  Built (73rd): `functions/trip_uncertainty.py`: residuals log(Google / predicted) of the K = 400 fit pairs nearest
  in log(predicted), per group; transit departures before 07:00 their own group (user, 2026-10-22: the only group
  that mismatches badly), drive one group ("by tier" has no per-trip meaning: a trip crosses density tiers). Service
  level dropped as an input (spread flat across it, RCH-25 (1)). Out of fold: transit 50 / 80 / 90% coverage 0.52 /
  0.80 / 0.91 on the holdout, drive 0.45-0.53 / 0.78-0.82 / 0.88-0.91 over 5 folds; conditioning on ETA no better
  or worse than pooled (log scale). E.g. transit predicted 18.5 min: P(Google <= 20) 0.82; drive 20.0: 0.52.
  Evidence: `diagnostics/trip_error_conditional.py`; departure noise (a) not yet combined.
- **RCH-24.** P̄ from a venue sample (user and Claude, 2026-10-22; plan): R̄'s P̄ (RCH-7) estimated from a random venue
  sample, stratified by ring (transit reach spreads ~16x, RCH-13), with an interval; each sampled venue gets its own
  envelope (RCH-21), origins routed once in the union. With R̄, the flat-accessibility run is geometry (discs), so the
  accessibility advantage (RCH-10) is computable for the subject and the branch; the sample also estimates the
  subject's percentile (SCR-7) with an interval. Sample size and strata open (DESIGN Q26).
  2026-10-23 (79th): 60 venues (user); drive P̄ needs no sample (the full pass covers every venue); the transit
  sample is deferred: ~4 min per venue per departure (rough), so ~4 h per departure for 60; how to sample its
  departures is decided later (user).
  Evidence: none (plan).
- **RCH-25.** Weekend evidence for bands 1-2 (user, 2026-10-22; plan, free; weekend inclusion open, Q25): partial by
  design: weekends differ from weekdays in where service runs, not only how often (user); trackwork stays a
  limitation. (1) Error diagnostic: model vs Google by ETA and per-hour local service level, training + test pairs;
  reads weekday error at weekend-like service levels. (2) Network-wide weekend coverage check, once per GTFS release
  (user: applicable to any subject): per stop / 500 m cell, weekend vs matched weekday service, coverage loss (stops
  or routes with no weekend service); per populated hex and weekend hour, whether weekday pairs exist under similar
  conditions; any subject's covered share of weekend reach is a readout from the map. (3) Then the RCH-23 function.
  First look (72nd, holdout, descriptive): robust SD of model - Google 1.5-1.7 min across 07-24 h, 2.66 at 00-07
  (155 pairs); weekday 19-22 (service ~ weekend day) no worse.
  Facts (73rd): (1) 12,575 scored weekday pairs: at 10-30 min ETA, error spread at weekend-like service (< 0.6 of the
  origin's weekday peak) equals full service (ratio 0.87-1.13); 5-10 min 1.48 on ~75 pairs, not shown worse; spread
  grows with ETA (0.7 to 1.4 min); the model runs early, worst at 00-07 (mean -15.7 min, Google waiting for first
  service). Weekend at the same origins: median 0.56 (Sat) / 0.49 (Sun) of the weekday peak; 99% of weekend
  conditions covered by weekday pairs. (2) Both releases: tram fully served on weekends; bus Sun loses ~26% of routes,
  Sat ~15%; train 2 of 17-18 lines and 15-23% of stations without weekend service 11:00-21:30 (cause unchecked); of
  persons with weekday service, 1-2% lose all service at a weekend hour; 13% have none on a weekday within 700 m.
  **Labels (user, 2026-10-22):** weekend transit reach carries "thinner service on weekends; not tested"; a subject
  open at any time 00:00-07:00 carries a prominent night disclaimer (model ~16 min early there). Weekend inclusion
  itself still open (Q25).
  Evidence: `diagnostics/transit_error_by_service.py`, `diagnostics/transit_weekend_coverage.py`.
- **RCH-26.** Graph oracle for Stage A (user and Claude, 2026-10-22, 74th discussion; oracle built, superset check owed; replaces
  RCH-21's venue -> hex oracle and RCH-22's margin if it holds): one reverse Dijkstra from the venue hexes (subject and
  sibling) on a two-layer graph: walk graph and stops, each twice (took_transit no / yes). Walk edges keep the layer;
  ride edges for every stop pair (i, j) on a pattern, weighted by the shortest single-trip t_j - t_i over trips in the
  window (zeros kept; per-hop minima never summed); a ride from layer 0 enters layer 1 at no charge, a ride inside
  layer 1 adds 200 s (the frozen model's transfer charge, P3; first boarding 0 s); no edge back; waits 0; a hex's time
  is the smaller of its two copies. Rule (user): always generous, never slower than the frozen model; cut 30 + 10 min
  to start. Why: summed per-hop minima teleport on minute-rounded GTFS (0-s minimum hop on 37% of tram / 51% of bus /
  0% of train stop pairs; summed minima / medians 0.65 / 0.64 / 0.93; Claude's ad hoc check, 20261018 release, not a
  diagnostic); whole rides and the transfer charge follow R5's rules, so zero waits, the fastest trip per pair and the
  walk graph are the only gaps. Tighter alternative: reverse connection scan (real waits). Next: superset check.
  Facts (75th, oracle only, cut 40, Wed 12:00 / 18:30, Sat 13:00): graph from R5's own street layer (1.44 M vertices,
  3.84 M walk edges; 23,557 stops, 0 unlinked; 7 of 331,620 disc hexes unlinked); ~430k ride pairs per weekday
  departure (350k Sat); build ~3 s, reverse search 0.1-0.3 s per venue; sets 2.1k-41k hexes per venue. Rounding
  figures recomputed on the 40-min windows: 0-s minimum hop bus 24-28%, tram 11-18%, train 0%; summed hop minima /
  trip span median 0.89-1.0 (the 74th's whole-day ad hoc figures used another definition). Truth not routed yet.
  **Decided (user, 2026-10-22, 75th):** (1) pass / fail by expected persons missed, sum over hexes outside the set of
  P x persons over the sum over all hexes, <= 1% (a share, not a count: a fixed count is lax for small catchments and
  strict for large); P = band probability from `trip_uncertainty` (RCH-23); (2) the cut rises until that holds, max
  55 min; (3) staged caps, 20 then 30, R5 max time = the cut; (4) span oracles: one graph per day type (Mon-Thu, Fri,
  Sat, Sun) x 30-min slot, rides = fastest trip in [slot start, slot end + cut], whole network (any venue; clipping
  could cut out-and-back paths), built per GTFS release (ride edges ~1-4 GB per release if stored; Claude's estimate).
  Why the mass measure: P(Google <= cap | predicted) falls to 0.04-0.10 at cap + 2, then a flat 2-3% shelf (model
  error tail), so a 1% per-hex threshold needs a cut ~52 at cap 30 (Claude's ad hoc check, not a diagnostic). Open:
  shelf line (Claude: hexes past the 5% level counted apart as model error), night P group, slot tightness.
  Facts (76th, autonomous; span oracles, 7 slots incl. weekend and night, 8 venues, truth on a 3% sample at 2
  departures per slot; full bands cut for cost, user and Claude): oracle slower than the frozen model on 0 of ~44k
  routed pairs; shelf line cap 20 23.1 min, cap 30 31.9; expected persons missed (core, Claude's rule) 0 from cut 25
  (cap 20) / 35 (cap 30) for every venue and slot, so the start cuts 30 / 40 pass. Slot vs single departure +1.5%
  set size, day span +32%; ~1.7 MB of ride edges per graph. Bins (user's question): clock hour +0.2-1.2% persons
  (AM shoulder +8%), centred 2 h up to +13%, no misses to remove. **Decided (user, 77th):** shelf line at the 5% level;
  night slots use the night error group. Facts (78th, autonomous; report bug fixed: oracle times saved for every
  routed hex x venue): full band for Mon-Thu 12:00 (cuts 30 / 40) plus the sample elsewhere: start cuts 30 / 40 pass
  (Claude's rule), 0 routed pairs outside the cut-55 set; oracle > truth on 10 of 135k pairs by 0.07-1.4 s, walk-only
  hexes next to a venue, all inside the set (end rounding, P2's whole-metre floor; no membership change). Core +
  shelf missed at cap 30 cut 40: 0.3-0.4% day slots, 1.2% night (night group). Spans: 4 day types x 48 slots,
  <= 668k ride pairs and 1.76 MB per graph, < 1 s build; 202 / 217 MB per GTFS release at cuts 40 / 55. Clock hour
  vs slot: +0.2-1.9% hexes on six slots, +11% at Mon-Thu 07:30, routed (Stage B) time in proportion.
  **Decided (user, 2026-10-22, 78th):** the 30-min slot bin stays (disk is cheap, routing time is not); production
  cut 30 by default: the set serves band 2 (cap 20) with its uncertainty, which the cap-20 measure already weighs
  (P(Google <= 20 | model) ~0 by 30 min). Cut 40 (cap 30, RCH-19's times complete to 30 min) only if a later step
  needs those times; none known. Cost of the choice (median venue, one departure, 0.027 s per origin): cut 30 8.3k
  hexes ~3.8 min vs cut 40 19.7k ~8.8 min; at cut 30 band 2 misses 0 core persons, 0.06% with the shelf.
  Finer bins not pursued (user and Claude, 2026-10-23, 81st): rides may depart up to slot end + cut, so neighbouring
  bins share most of their trips at any bin size, and zero waits count one trip as full coverage; the trip-count flag
  (RCH-20) serves span targeting instead. A reverse profile connection scan (exact arrival vs departure time for all
  origins in one pass per venue) stays the candidate if passes ever repeat often; a second router to validate.
  Evidence: `diagnostics/reachability_graph_oracle.py`.
- **RCH-27.** Band-3 diners' transit fields (user, 2026-10-26, 111th; built 112th): staged best-of-K (SCR-23)
  needs each band-3 diner's own bands 1-2 transit field; 54,514 populated band-3 hexes lie outside every subject
  envelope (12,208 reused). Routed with hybrid targeting (RCH-20; never implemented, to build) from merged origins:
  a hex with persons >= T keeps its own route; its aperture-7 flower's lighter populated members merge into one
  group routed from their persons-weighted centroid (the parked stencil, `hexes.md` Notes, revived with a threshold).
  T open (Claude: 40; user floated 80 for the 20-min stage with a lower T, short searches, for the 10-min stage:
  pilot first). Why: no heavy hex is ever skipped (user), unlike random 1-in-5 sampling. Cost (ad hoc, Mon-Thu
  19:00, 200 flowers): field error 10 / 20 min T40 1.9 / 1.4%, T80 4.3 / 2.9%, all merged 22 / 9%; bias <= 0.1% at
  T40-80; routes T40 25% (~1.6 h hybrid), T80 18% (~1.2 h); exact all-origins ~22 h, ~39 GB. Weighting cuts bias
  (-4.5 -> -1.5% at 10 min, all merged), not scatter. Evidence: `diagnostics/diagnostic_data/band3_routing_adhoc_20261026/`
  (ad hoc; a D1 diagnostic comes with the build).
  Built (112th): T per stage band (user): 20 for band 1's field, 80 for band 2's; band-1 points routed to 16 min
  (Claude's: band-1 chance >= the 1% floor reaches 14.75 min; the user's cut + 1 = 11 would drop chances of 0.23),
  band-2 points to 31 (`config.REACH_BAND3_*`). Hybrid windows: Mon-Thu read whole in the subject pass's chunks;
  six other spans one random 30-min window each (seed 20261026): 13 fields, 42 slots. Hexes inside the subject
  pass's envelope for a whole window keep their exact routes. Pass `transit_band3_4b1d1bfb3f` (66,722 populated
  band-3 hexes; ~10.2-10.8k long and ~26.7-28.9k short points per window; 4.3 h, 1.6 GB). Field error at the
  chosen T: 0.09% / 2.9% of the field, bias +0.004% / -0.06% (`diagnostics/band3_flower_merge_error.py`).
  113th (user): the 16-min band-1 searches and the exact-route reuse approved (DESIGN Q32 "Speed-up review").

## Not adopted
- Per-venue radius R_i as the main line (reproduces each venue's own population): no field-level answer, non-reciprocal competitor sets, needs R̄ first. Optional further work. rev4 L370-375; `STALE_handover_rev3_7_delta` L102-116.
- Boolean reachability storage: every variant becomes a fresh drive run. rev4 L458-459.
- Charging walk snaps at both ends in the pass: thresholds a different quantity from the calibrated one. `connector_convention_Sep_21` L152-156.
- Envelope from contested hexes (60 min) as the scan region: superseded by the full 100 km grid. `TEMP_workplan_Sep_23` L163-172.
- An 80% similarity cutoff for trading overlap: an invented number on a steep part of the distribution. rev4 L2080-2082.
- MedAPE against Google as the target for more calibration: the wrong target; judge by effect on reachability output (memory `output-first`). rev4 L2041-2042.
- Fuel-price / service-station extension: pathing variance exceeds the dollar saving. rev4 L1521-1523.

## Limitations
- Venues near the 100 km line lack competitors and population beyond it (Ballarat is cut); the edge flag excludes them from R̄ and owner percentiles (decided 2026-10-23; DESIGN.md Q5, HEX limitations); flagged when the 2.5x drive horizon reaches a node within 1 km of the drive graph's outer boundary (general rule, user, 82nd). `hex_block_Sep_27` L14-27.
- Output is contestable population (SCR-11) under an assumed choice rule, validated on travel time only: arrow 1 has one falsifiable test, arrow 2 none. rev4 L1414-1417; FRM-5.
- No rent term, so siting readings inherit that caveat. Beyond a plausible consideration-set size, the N-sweep is a mechanical limit, not behaviour. `ideas_textsearch_relevance_Sep_24` L90-95.
- Transit bands: the choice between stock R5 and the no-wait model moves the subject's catchment by about
  a tenth (residents +10% within 20 min, workers and venues +16%), because catching or missing the first
  vehicle turns a minute into a headway; absolute band-1/2 totals carry about +-10% from the transit model.
  Uniform bias largely cancels between competitors; location-specific error does not (RCH-13).
  `diagnostics/transit_catchment_sensitivity.py`.
- A 20-min drive reaches ~7.1-7.3 km haversine at the edge, so x% time error ≈ 2x% reach area. `tilt_rederivation_Sep_21` L153-155 (pre-2tier models); `OD_resample_Sep_26` L131-137.

## Notes
- Cost of the pass: the user believes it isn't a bottleneck; measure on the full grid before relying
  on it. Old 20 km figures (own graph then): walk + PT ~4 min / ~5 M rows; drive ~35 min / ~145 M rows.
  rev4 L2022-2025; `fractional_hexes_Sep_29` L16.
- Cheap error sizing (optional): perturb outer drive times ±7% and ±15%, recompute P̄, R̄ and
  Default − R̄. `OD_resample_Sep_26` L148-152.
- Write the model's prediction for the Melbourne Central hex before looking at scored output.
  `2026-09-21_r5py-network-build` L92.
- Applications: cannibalisation is the strongest ([subject] siblings share price, format, cuisine, so
  homogeneity holds by construction); franchisee encroachment may be the stronger business case,
  cancelling the conversion factor only if conversion is spatially uniform. rev4 L1435-1460.
- Ideas, not planned: trading-overlap weight (continuous, normalised within the reachable set);
  uncertainty-weighted candidacy (designed, not built; premise weakened Sep 21); corridor interception
  (en-route population); a reputational barrier surface per hex. rev4 L1491-1510, L2070-2081.
- R̄ reference class: field-level first; subject-local deferred. `STALE_handover_rev3_7_delta` L247-254.

## Open questions
- DESIGN.md Q17 (per-venue time-of-day factor applied in this pass), Q26 (venue sample for P̄, RCH-24; departures
  decided 2026-10-23, run deferred); `scoring.md` S1 (band edge). Q25 decided 2026-10-23 (RCH-20).

## Changes
- Changes to 2026-10-20 (RCH-1 to RCH-19): snapshot, "Changes".
- 2026-10-22 · RCH-13 / RCH-17 / RCH-19 (69th, autonomous): drive storage pilot, transit timing pilot (chunked), drive and transit catchment sensitivity (facts; Q21 cutoff still open)
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
- 2026-10-23 · RCH-7, RCH-12 wording (79th discussion): P̄ as expected reachable population; "contested" hex now contestable (SCR-11); RCH-17 storage 2.5x (Q21), RCH-18 newest release, RCH-20 subject schedule, RCH-24 sample of 60 (transit deferred), Q5 decided
- 2026-10-20 · RCH-13 catchment sensitivity run (stock vs no-wait, sample then census, user): result and reading added; Limitations entry added
- 2026-10-21 · RCH-13 catchment reading accepted by the user (65th)
- 2026-10-22 · RCH-20 added (70th discussion): transit departure schedule, spans from data (plan, open Q25)
- 2026-10-22 · RCH-20 facts (71st, autonomous): service profile and span scan run; departure noise dominates; still open
- 2026-10-22 · RCH-22 / RCH-23 / RCH-25 facts (73rd, build): asymmetry margin 10 min + self-check (user, sign wording corrected), trip_uncertainty built with a night group (user), weekend error and coverage checks, weekend and night labels (user); Q25 step deferred (user)
- 2026-10-22 · RCH-21..24 added (72nd discussion): subject-scoped transit pass with oracle envelope, asymmetry check, uncertainty by departure and by ETA vs Google, P̄ from a venue sample (plans); RCH-7 pointer; RCH-21 generalised to any subject, RCH-23 uncertainty function, RCH-25 weekend evidence plan
- 2026-10-22 · RCH-26 added (74th discussion): graph oracle for Stage A (two-layer walk + synthetic-ride graph, always generous, cut 30 + 10 min); RCH-21 pointer
- 2026-10-22 · RCH-26 facts and decisions (75th): oracle built and run (cut 40); user: 1% expected-persons measure, max cut 55, staged caps, span oracles by day type x 30-min slot
- 2026-10-22 · RCH-26 facts (76th, autonomous): superset test on the sample passes at the start cuts, 0 generosity violations; bin variants measured; RCH-14 limitation worded plainly (user)
- 2026-10-22 · RCH-26 (77th): shelf line 5% and night error group decided (user); band report bug found, band result pending
- 2026-10-22 · RCH-26 (78th): band report fixed and read (start cuts pass, 0 violations); spans sized; 30-min slot bin kept and production cut 30 by default (user); RCH-19 note
- 2026-10-23 · RCH-20 (80th, autonomous): departure sampling measured (dense reference, 4 day types); spans as the unit (user); scheme open (random spans vs P8r span windows)
- 2026-10-23 · RCH-17, RCH-18, RCH-19, RCH-21 (83rd build): drive pass run, production network, cap diagnostic, envelopes and timing run (facts)
- 2026-10-23 · RCH-18, RCH-21, Limitations (82nd discussion): no reuse of earlier data (recompute; user); <= 90-min P8r chunks, ETA revised; edge-flag threshold 1 km (user)
- 2026-10-23 · RCH-20, RCH-21, RCH-26 (81st discussion): departure scheme decided (subject whole P8r windows; hybrid targeting for repeated passes; R-bar one single per span); sibling envelope out of the subject pass, subject's hours only; ETA ~4.5 h; finer oracle bins not pursued
- 2026-10-23 · RCH-21 (85th, autonomous): subject transit pass run (threaded, byte-identical check on chunk 0); facts
- 2026-10-23 · RCH-20, RCH-21 (86th build): subject-pass reading diagnostic: hybrid error on the exact pass, trend, flag, corridor shape (facts)
- 2026-10-26 · RCH-27 new (111th, user): band-3 diners' transit fields by hybrid targeting from threshold-then-weighted flower origins; T open; timing and field-error facts (ad hoc)
- 2026-10-26 · RCH-27 built (112th): T 20 / 80 per stage band (user), 16-min band-1 searches (Claude's), hybrid windows, the pass, D1 diagnostic
