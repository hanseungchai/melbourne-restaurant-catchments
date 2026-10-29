# PLATICA — Design spine

The current method and intent in one place: per stage, the decision in brief, a pointer to where the
detail lives, and its status. Detail, evidence and history live in the concept docs
(`docs/concepts/`, found through `docs/INDEX.md`); cite positions by ID (e.g. DRV-1).

- **Status:** spine rewritten 2026-10-13 (reorg step 5) from the 2026-10-06 draft and the 14 concept
  docs. The full pre-spine text is archived at `docs/stale_project_mds/DESIGN_pre_spine_20261013.md`
  (history and detail only; not the current design, W2). Compacted 2026-10-20: the full pre-compaction
  text, with each open question's session-by-session history, is in
  `docs/context_snapshot/2026-10-20_02-48-00Z/DESIGN.md` (correct as of its date; this file wins).
- **Upkeep:** when a decision changes, update the concept doc and the line here in the same step
  (CLAUDE.md F1). Q-numbers live here, are never renumbered and never reused.
- **Precedence:** where this disagrees with the code, the code shows what is; report the conflict.

---

## What the project is

**A geospatial model of the competitive value of reputation for urban restaurants.** Subject:
**[subject] Brunswick East** (`-37.7687014, 144.9719611`, hex 0). Causal chain: reputation → platform
visibility → competitive advantage; food quality sits outside it. (FRM-1, FRM-2)

- **Framing:** "Spatial elements set the grounds and the rules; reputation is the game." The
  multi-modal catchment model leads as the contribution; reputational competition is the worked
  application. (FRM-3, FRM-4)
- **Purpose, stated modestly:** what is available to an operator and what each lever is worth
  (rating, mode, siting), not what will happen. (FRM-6)
- **An attempt, not a picture of reality:** limitations come before results for every audience;
  excited readers are reminded what the model assumes (Q19, Top-N, the unvalidated reputation
  rule). (FRM-18)
- **Google's view, throughout:** reputation = Google's displayed rating and review count; reachability
  = travel time as Google presents it (connectors not charged). (FRM-7, GRF-7, WLK-3)
- **Output:** population in two denominators, **never blended**: reachable residents and reachable
  workers; reported as population-weighted shares. (CEN-1, CEN-7)
- **Scope is discovery:** people who search Google to find a place, not walk-ins or browsing; the
  write-up leads with the model's assumptions (rivals, top N, Google's tags). (FRM-14, FRM-15)
- **Population scope (2026-10-14):** the core is residents and workers; commuters passing by (census
  journey-to-work flows, routed) are the only candidate third layer, parked until path and flow tests
  pass. Presentation (2026-10-22, user): three parts by assumptions added, disclaimers growing:
  (1) workers and residents; (2) counterfactuals, cannibalisation; (3) showcase: detour, foot traffic,
  anchor (FRM-19). Tourists, shoppers and other trip attractors, and students are future work, named as
  limitations, not built. The write-up and literature review start once the core is done. Future
  application (2026-10-19, user): 2016 / 2021 / 2026 census runs against restaurant outcomes (COVID's
  impact including its policies), then a neutral policy cost simulator. Demographic showcase (2026-10-19,
  user): at most 6 census metrics per side (workers by DZN, residents by SA2 plus cars per dwelling), to
  show it can be done; no deep analysis unless asked. Purchase journey scenarios (2026-10-20, user): one
  low-conviction demonstration that the method generalises: students walking from a campus to the subject,
  with the competitors along the way by detour band x rating x price x cuisine; never called interception.
  Commuter detour layer: time-only detours need only the time check (revised 2026-10-20, user); foot
  traffic covers walk-bys too. (FRM-19 to FRM-23)
- **Audiences:** academics, data analysts, small business owners and franchisees (FRM-10); who to
  approach and how is in `outreach.md` (OUT, parked until delivery). Order by audience (2026-10-23, user):
  academics get setup first, a faded dashboard and the catchment map as cover, q as a sensitivity slider (FRM-26).
  Business pilot (2026-10-26, user): human hook, the audience guesses k, headline map, then layers; best-of-K
  only; PPTX; `docs/presentation/pilot/` (FRM-26).

## Pipeline spine (stages in `main.py` order)

Status: `main.py` STATUS · design (**settled** / **open** with Q-number / **planned**).

| Stage | Current decision | Pointers | Status |
|---|---|---|---|
| `rebuild_legacy_datasets` | "Dataset one" rebuilt from frozen inputs, no API: June 2026 scan (with its 7.5–20 km hole) + Sep repair and outer rings → `venues_20260925_expanded.csv`, 19,030 venues (18,498 on the grid). Closed venues stay. | VEN-1..5, VEN-14 | cleaned · settled |
| `fetch_enterprise_hours` | Paid, ledger-guarded Places Enterprise pull: uniform draw of 900 venues + the two [subject] venues; a 404 is permanent. | VEN-11, VEN-13, API-1 | cleaned · settled |
| `build_opening_hours` | Weekday 30-min open-share histogram from the pull named by `OPENING_HOURS_PULL_DATE` (2026-10-10, replaced 2026-09-02; pooling rejected). | VEN-11, VEN-12 | cleaned · settled |
| `pre_process_census` | Statewide ABS 2021: residents (G01, SA1) and workers (DZN), never blended; census year set per layer by hand. | CEN-1..3, CEN-6 | cleaned · settled |
| `construct_hex_tiles` | 100 m flat-top hexes to 100 km of the subject; census shared area-proportionally; venues to the nearest centroid (50 m cap); empty hexes dropped; coverage check warns only. | HEX-1..10, CEN-4, CEN-5 | cleaned · settled · Q5 open |
| `map_construction` | Drive graph from the one frozen BBBike extract (walk graph build parked, WLK-5); Valhalla's road-density rule on a 100 m raster, read per hex, node and route point. | GRF-1, GRF-2, DEN-1..7 | cleaned · settled |
| `open_snapshot_review` | Review of the data layers: the diagnostics' latest statistics and figures (`diagnostics/snapshot_report.py`); writes no pipeline data. | — | no STATUS line |
| `construct_graph` | Drive only. Largest strongly connected component; candidate roads cut into equal ≤ 50 m pieces; each hex to its nearest piece node (1 m tie window); connectors free. | GRF-3..8, WLK-5 | cleaned · settled · Q12 open |
| `build_speed_graphs` | Signal flags and edge times, one timed graph per variant: `blind` (base and control), `osmtable`, `dense`, `dense_fringe` (references). | DRV-2..5, DRV-13 | cleaned · settled |
| `sample_drive_pairs` | Two pooled draws of 4,000 hex → venue pairs (25-min blind window, 80/20 hours departures), Google traffic-aware times (paid, ledger), joined, split once 4,000 / 4,000 grouped by destination hex. The old 540 pairs are set aside, not routed. | ODS-1..10 | cleaned · settled · Q10 |
| `calibrate_pathing_agent` | **Selected model: `2tier`** (fitted density factor at level 15 vs 0-14, on every edge, + β per signal + ALPHA; time-blind). Chosen on out-of-fold accuracy at the 20-min cut with bias, drift and density guards; test half opened once (accuracy 0.9233; rural +13.8%, a stated limitation); rescored at SCR-10's 1,229 s cut 2026-10-18: holds (0.9188, DCL-9). Production fit refitted on all pairs (no held-out score). | DRV-1, DRV-6..12, DCL-1..14 | cleaned · selected · Q15, Q16 |
| `construct_pt_graph` | r5py TransportNetwork: OSM extract + three PTV GTFS feeds; raw published durations; walking speed fitted in r5py walk-only (4.16 km/h). Cleaned 2026-10-14 (P2b) on the live extract (Q7) and the 2026-10-13 PTV feed (TRN-1, TRN-3); route_type 701 buses dropped (TRN-11); 0 unlinked stops; build guarded against r5py's stale input copies (TRN-2). Band model of record: no-wait model, plain cuts 10 / 20, on the v2 pathways network (a diagnostic build, not yet in the stage; TRN-13). | TRN-1..15, WLK-1..4 | cleaned · Q7 validation (test half unopened), Q23 |
| `sample_transit_pairs` | Hex → venue pairs drawn like drive, windowed by uncalibrated r5py (fastest over 06-24 on Wed 2026-10-21 ≤ 40 min) on the 2026-10-09 release; 35 km haversine prefilter (worst case 31.3 km); 2,500 kept + 125 smoke-test pairs from r5py's rejects; weekday and minute per pair, date per fetch release; split once (halves grouped by destination hex, 5 folds, 500 exploration pairs). Built 2026-10-15; reserve, test-half extension and holdout replayed from the checkpoints (TRN-10, TRN-15), one code path keyed by set name (`STREAM_SETS`), run from `transit_collection.py` (2026-10-22). | TRN-7, TRN-10, TRN-15, T3-T6 | built · T6 settled |
| `transit_fetch` | Google transit answers per pair (Routes Essentials via the ledger; no `routingPreference`, guarded; alternatives on; raw answers kept; release per row); fetch dates from TRN-7's per-release window; route table written after each fetch; scope matcher by line and vehicle type. Fetched: whole draw 2026-10-17 (2,625), second batch 2026-10-18 (2,000), boundary top-up 2026-10-18 (210 calls), test-half extension 2026-10-20 (4,000), holdout 2026-10-21 (4,000, sealed); all HTTP 200. Later sets fetched by set name (`FETCH_SETS`) from `transit_collection.py <set> <step> [--paid]`. | TRN-8, TRN-10, TRN-11, TRN-14, TRN-15 | built · fetched · Q18 |
| *Venue fetch track* (planned) | Probe (free Text Search) → calibrate k → pack circles → Legacy Nearby with recursion → save raw with provenance; never merged with legacy data. | VEN-9, VEN-10 | planned · Q8 |
| *Venue enrichment* (planned) | Places Details Essentials pull for the 14,539 ring rows (Legacy Nearby tags, no addresses) before anything uses fine-grained venue types or addresses. | VEN-8 | planned · Q9 |
| *Reachability pass* (planned) | One single-source search per venue node with a cutoff; store costs, not booleans; guards before the pass; every venue in the grid gets its own horizon; per-venue time-of-day factor. Drive slice first: one reversed-graph search per venue hex (8,959), node-level integer costs, build stamp; storage to 2.5x (Q21, 2026-10-23); newest GTFS release; edge venues out of R̄ and percentiles (Q5). Transit subject-scoped (subject envelope, subject's hours; sibling for cannibalisation only, RCH-21; whole P8r windows for the subject, hybrid targeting for repeated passes, RCH-20; oracle origin search with a 10-min margin plus outer-ring self-check; graph oracle RCH-26: span oracles per day type x 30-min slot pass the superset test at cuts 30 / 40 for caps 20 / 30, full band included; 30-min slot bin kept; production cut 30 for band 2 with its uncertainty, user); P̄ from a venue sample; uncertainty function built (`functions/trip_uncertainty.py`, night group); weekend checks run, weekend and night labels. | RCH-1..6, RCH-13..26 | drive pass and subject transit pass run (2026-10-23); scoring and report not built · Q5, Q17, Q21, Q25, Q26 |
| *Data top-ups* (planned, after outputs) | Long-term maintenance, for more samples or data added by others: hours refresh (new random sample + fixed drift panel) before a drive top-up; each new drive fetch is the next test set, everything earlier joins training; a venue update replaces the table (VEN-9). Code today handles two drive draws and one hours pull. | ODS-11, DCL-15, VEN-15 | planned · Q20 |
| *Scoring* (planned) | Chosen representation, low conviction, interchangeable (FRM-25). Three bands; headline share rule diner persistence q (rank r weighs q^(r-1) among the venues that entered, ties averaged; convention q = 0.7, curve over q, owner states a guess first; 2026-10-23, 83rd), Top-N kept as a considered variant (top N take 1/N, or all K in reach 1/K when K <= N); q's story retired (107th); best-of-K replaces q as the headline (SCR-23, Q32, 108th: geometric K per diner, mean k the owner's guess, stages by band; not built); contestable hex = inside a venue's catchment, by reach probability; reach by draws, Top-N among the venues that entered each draw; per 30-min slot, headline the mean over the subject's open slots; hours by donor schedules of pulled venues (SCR-13); headline population residents + workers (SCR-18); competitor measures denial and immediate rivals (contention; SCR-14) (2026-10-23; named 94th); a SWOT appendix for owners with recommended opening hours among slots where >= 50% of tag peers are open (SCR-21, 94th); within a band, every venue by a shrunk rating, for ordering only and never shown (no review threshold, no tiers; m 15 and C 4.25 fitted; SCR-20, 2026-10-24, 92nd-93rd), a displayed 5.0 read as 4.975 and 1.0 as 1.025 (S*', Q29 closed 97th; m open, Q31); four-corner counterfactuals; owner figures as percentiles; the owner's rating slider shows each step's rarity among venues within ±2.5 review-count percentile points ("1 in N show this or higher"; SCR-22, 99th, built 100th; the cliff at 4.9 read as the slider's fixed n, not the rule); idea, not planned: competitor pool weighted by hours overlap (scoring.md Notes, 95th). | SCR-1..23, RCH-7..12, VEN-13 | reach table built (2026-10-23, 88th); venue open shares built (90th); donor hours and share step built (SCR-13, SCR-19, 91st); rating rule decided (SCR-20, 92nd), m and C fitted (diagnostic, 93rd); key cells and immediate rivals built, first full run done, report and census profile built (`scoring_report.py`, 94th); rating-key variants run (96th); key S*' decided (97th), code default since the 98th; slider 3.5-5.0 and per-rating hex shares (98th); rarity line decided (99th), built in the report and rating maps (100th); full run, report and profile end to end, Q31 m reruns, break-even pairs (101st) · S1, Q19, Q30, Q31, Q32 |

Removed in the cleanup (`docs/DEPRECATED.md`): `generate_centroids`, `update_google_data_legacy`,
`update_google_data_new`, `update_google_data_expanded`, `compile_legacy_google_to_csv`,
`compile_new_google_to_csv`, `google_enterprise`, `basic_stats`.

## Cross-cutting positions

- **Bands:** 1 = walk + PT ≤ 600 s; 2 = walk + PT ≤ 1,200 s; 3 = drive ≤ 20 min predicted. Each band
  is a diner travel tolerance, not a prediction of what Google shows (the viewport shifts and the
  ranking is a black box); band 1's match with the ~1 km search radius is a side note only; reported
  per band, never summed across bands. (SCR-1, SCR-2, RCH-1, Q19)
- **Top-N and who wins a slot:** each hex's population divides among the top N venues in reach, or
  equally among all K in reach when K <= N (N swept 1-3; N -> infinity is flat reputation); uncertain
  reach enters by draws, Top-N dividing among the venues that entered (SCR-11, SCR-12);
  lexicographic, no trading rating against distance (ties share, no proximity tie-break, 2026-10-23); threshold,
  m and fill order are judgements. Headline rule is persistence q (SCR-15); Top-N a considered variant. (SCR-2..5)
- **Counterfactuals:** population real/flat × accessibility real/flat (flat = common radius R̄);
  reputation flat in the accessibility comparison; owner outputs: reputational advantage and the
  siting tool. (SCR-6, SCR-8, SCR-9, RCH-7..12)
- **Every output carries its uncertainty:** an interval for each measurable source, the rest listed
  as limitations; drive error propagated by simulation from the test-half residuals. (RCH-13)
- **Time of day:** the drive model is time-blind, by decision; time of day enters only as the
  per-venue factor in the reachability pass, without rerouting. Departure-time-aware routing is not
  adopted. (DRV-8, RCH-14, Q17)
- **Paid APIs:** every call through the `api_ledger` guard; Routes free allowance 5,000 a month.
  (API-1..9; CLAUDE.md S5)
- **Pre-registration:** pass rules and predictions written before results are read; any later change
  is stated as a deviation. (DCL-12, FRM-12)
- **Competitor set:** venues Google tags as restaurant, not what businesses are. (FRM-8, VEN-7)

## Ways of working

- **Baseline:** the cleanup reproduces the existing outputs (P3); a change that alters an output is a
  design decision, not cleanup: stop and bring it to the user.
- **Every step is a script** reading and writing files; no hand steps. **Fetch is split from
  processing:** fetches save raw responses untouched; everything downstream reruns identically.
- **One fetch method per API:** keep only the latest, most efficient pass; older methods are removed
  and logged in `docs/DEPRECATED.md` (recoverable at `legacy-final`).
- **If another drive approach is added, the code is rebuilt first.**
- **Learning project:** understanding before speed; explain concepts before code.

## Open questions

Open questions keep a short statement and a pointer; closed ones keep one line saying where they closed.

- **Q1.** ~~M2 verdict under the Oct 4 rules.~~ Closed, then superseded 2026-10-11 by the fitted round (DCL Notes).
- **Q2.** ~~Train / test scheme.~~ Closed 2026-10-11: 4,000 / 4,000 holdout, grouped CV inside the training half (ODS-9, DCL-2).
- **Q3.** ~~Walking-speed calibration network.~~ Closed 2026-10-09: r5py walk-only (WLK-1).
- **Q4.** ~~50 m snap filter on the merged venue file.~~ Closed 2026-10-13: same rule as HEX-6, drops nothing in the grid (`venues.md` V2).
- **Q5.** Edge flag (decided 2026-10-23, user): exclude venues whose cost horizon reaches the grid or extract edge from R̄ and owner percentiles. Threshold (user, 82nd, general rule): the 2.5x drive horizon reaches a node within 1 km of the drive graph's outer boundary; the first pass writes the flag to its manifest only. (HEX and RCH limitations)
- **Q6.** ~~Downstream use of `adjusted_rating` / C / m.~~ Closed 2026-10-08: none (DEPRECATED `basic_stats`).
- **Q7.** r5py rebuild on the live extract: **done 2026-10-13** (all metro stops linked; 398 regional-bus
  stops unlinked at the edge, gone once route_type 701 was dropped 2026-10-14). Still open: validation against Google transit pairs. (TRN-2, TRN-3, TRN-8)
- **Q8.** Venue probe k drift (median 1.18 / max 8.5 recomputed vs documented 1.13 / 2.71): per-run
  calibration and post-fetch recalibration address it; not blocking, since k affects cost only. (VEN-9, VEN-10)
- **Q9.** Venue enrichment: the 14,539 ring rows carry Legacy Nearby tags (coarser vocabulary) and no
  addresses; a ledger-aware
  Essentials pull is needed before any stage that uses them. Needs the SKU's allowance in the ledger
  and the user's go-ahead (S5). Not needed for Q17. (VEN-8)
- **Q10.** Parked ideas, not adopted: the departure-time noise floor; Text Search relevance; dropping
  the 80/20 departure floor in a future draw (decide before that draw, not after a result). (ODS-5, DCL limitations)
- **Q11.** ~~Post-cleanup M2 vs osmtable re-test.~~ Closed 2026-10-11: absorbed into the density-share guard (DCL-7).
- **Q12.** Nearest-road snapping holds only in part: Google starts or ends on the nearest road 81.6%
  of the time (map-inventory mismatch on service roads; partly efficiency); effect seconds per trip.
  A wider tie window is a possible later experiment. (GRF-4, graph limitations)
- **Q13.** ~~Night departures.~~ Closed 2026-10-11: kept, no time-of-day term in the fit (ODS-5).
- **Q14.** ~~Polyline matching threshold.~~ Closed 2026-10-11: 10 m, heading within 45° (DCL-10).
- **Q15.** Density slowdown by road class: yes, Google's dense slowdown is ~1.5× on motorways, ~2-3×
  on arterials, ~1.2× on residential (2026-10-12). A class split inside a tier is a possible further
  nested structure; not yet acted on. (DRV limitations)
- **Q16.** Route-choice gap: ~38% of Google's length is off our route; fitted variants over-use
  motorways. Diagnosis only, no new parameters; the planned β turn-friction check was never run. 2026-10-14: the
  gap is the same for every model (11 tested, Valhalla included: 34.5-38.6% missed; per trip, either the
  same route or a whole different one), `diagnostics/route_match_vs_google.py`. Fitting to route match
  parked as a later todo. (DRV limitations, DCL-5)
- **Q17.** Per-venue time-of-day factor: **adopted 2026-10-12**, to be built in the reachability pass
  (RCH-14); hours per venue, pulled or imputed (VEN-13); tag-based exclusions are the reader's choice,
  made before results (VEN-7). Hours pulls: random draws from never-pulled venues, never targeted by
  distance to a subject (2026-10-23, VEN-15). Scoring uses hours per 30-min slot (SCR-13): VEN-13 revised there to
  partial pooling along a tag chain (2026-10-23, 90th).
- **Q18.** Transit departures and pairs: **protocol decided 2026-10-13, window and releases revised
  2026-10-14; built and fetched.** Departures as drive (weekday 30-min slots, the mean of the two drive
  draws' 80/20 hours rules, low-service slots kept), future at fetch time, the date assigned per release
  from a window computed per release (after the fetch day, within the 30-day validity, before any
  in-scope route group drops out, no holidays; the 2% steadiness step dropped 2026-10-18, user; TRN-7).
  Pairs drawn like drive, windowed by uncalibrated r5py (fastest weekday time <= 40 min, 2x the top
  band, departure-independent), each routed on its own release's network, no GTFS merge (TRN-10). Myki
  metro scope, out-of-scope Google routes excluded, hedged with alternatives (TRN-8, TRN-11). Split at
  the draw (T3); 2,500 drawn plus 125 smoke-test pairs (T4, T5); worker lean stated (T6). Fetched:
  whole draw 2026-10-17 (2,625, 2026-10-09 release, Oct 19-23), second batch 2026-10-18 (2,000 reserve
  pairs, 2026-10-16 release, Oct 19 - Nov 2), test-half extension 2026-10-20 (4,000, TRN-15).
  (TRN-3, TRN-7, TRN-8, TRN-10, TRN-11, TRN-15, T3-T6)
- **Q19.** Google's black box, two confirmations needed (user, 2026-10-13); planned diagnostic,
  within limited means: confirm, not reverse-engineer (framing.md Not adopted). The tolerance framing
  and Top-N rest on both; until run, SCR-1, SCR-2 and SCR-4 carry no evidence for them.
  (a) Reachability: does Google treat a venue across a barrier (resident on one side of a river with
  no crossing, venue straight across) as a candidate, i.e. is candidacy straight-line or
  travel-based? Candidate test sites: the 5 walk barrier pairs (WLK limitations).
  (b) Reputation: within reach, do better-rated venues get shown first or more often, distance held
  roughly equal?
  Possible check: ~60 manual searches across devices and locations (no API, S5). (SCR-1, SCR limitations)
  **Method for (b) changed (user, 2026-10-20; not built):** a diagnostic (D1), rank correlation of Google's
  restaurant result order against rating, review count and distance to the search point (location added),
  within each search; Text Search (New), IDs-only field mask (free SKU, through the ledger), joined to the
  venue table; first look for saved page order in the 2026-09-24 probe (free). It confirms; it does not
  model Google's ranking (inside framing.md's carve-out, user). Replaces the manual searches: one
  person's device is one viewport and one personalisation, so n = 1 user. Stated: API order is a
  non-personalised baseline (no sponsored pins). (framing.md Not adopted)
  **Gate treated as cleared for the business pilot (user, 2026-10-26, 118th):** both parts ran (105th-107th);
  Google read as opinion, not recommendation (FRM-27).
  **Gates presentation (user, 2026-10-25, 103rd):** (a) and (b) both run before any audience sees results; (a)
  tests a core premise. No free route: the 2026-09-24 probe saved IDs sorted (all 9,835 multi-ID responses), so
  page order is lost and new IDs-only calls are needed. Must cover (user): left-out venues (a passed-over
  candidate is evidence, most of it for (a)); open status and sponsored placement (Google favours both on
  screen; API behaviour unknown). Radius: 1 km is closer to the user's laptop and phone; device viewports differ
  by unknown factors. First step (user): a screen-matching test, the user's Google Maps "restaurants nearby"
  screen (URL `@lat,lon,zoom`, full list and labels, clock time, signed-in state) against the same API call
  (viewport restriction, viewport bias, 1 km circle; with and without `openNow`), to set the main fetch's search
  area and open-status handling. Claude's proposals (owed, HANDOFF): candidates = table venues within the
  farthest result's distance, restaurant-typed for the headline; rank-ordered (Plackett-Luce) logit headline,
  inclusion and order as checks; a detour-ratio term for (a); radius 0.5 / 1 / 2 km; pass rules rating
  coefficient > 0 (b), detour coefficient < 0 (a), 95% intervals excluding 0 at every radius.
  **Screens taken (user, 2026-10-25, 104th):** phone app (107 cards, 12:06-12:12, distance per card) and laptop
  browser (29 cards, 12:19-12:21, URL `@-37.817501,144.9501715,2982m`), query "Restaurants"; no Sponsored label
  on either; one phone repeat (Number 12 Thai, two distances). Transcribed to
  `diagnostics/diagnostic_data/screen_match_20261025_*` (provenance: `inputs/README.md`). 28 venues on both;
  Spearman 0.84 on them (looked at, not a test). API side run in the 105th (below).
  **Screen test run (105th build, 2026-10-25; no pass rule applied, the proposals above still owed):**
  (1) No API order stands in for the screen: 25 settings sent 20-45 min after the screens (Text Search IDs-only:
  viewport restriction / bias, 1 km circle, each +- openNow, distance rank, 300 m, typed; Nearby (New) popularity
  500 m to 1.5 km), best phone top-10 overlap 3 of 10 (`diagnostics/screen_match_compare.py`). The Places FAQ says
  results are cut at the top 60 by prominence before any distance sort; venues 150-250 m away were left out.
  So (b) runs on screens, not API order: n = 1 user, stated. (2) The browser list centred on the user's
  location, not the URL map centre (phone-centred Nearby 500 m shares 5 of the browser's top 20; URL-centred 0).
  (3) (b), phone screen, 97 cards matched (the list never ends: "shown" = in the first 107)
  (`diagnostics/screen_rank_drivers.py`), per 1 SD: order (Plackett-Luce) log distance -0.69 [-0.95, -0.44],
  rating +0.36 [+0.14, +0.58], log reviews +0.02 [-0.21, +0.25]; in the first 107 of 1,253 table venues within
  1.4 km: distance -0.54, rating +0.64 [+0.27, +1.02], reviews +0.63 [+0.36, +0.90]. About one star offsets a
  doubling of distance in the order. First evidence for (b), one screen. (4) Distance kind: walking (R5, median
  1.29x straight-line) and straight-line fit alike; minutes saved by transit add nothing (order -0.05
  [-0.29, +0.19]), but transit saves at most 6 min within the list's 1.4 km here, so little power.
  **Position (user, 2026-10-25):** the model claims diners travel by catchment, not that Google's list does;
  Google accounting for travel time, even slightly, would be a bonus, not a requirement. Next (user): the
  partner's phone (a second user, correlated by shared places and habits: stated limit); hub screens at spots
  the user picks when convenient (Claude's R5 pre-check options: Flinders St, North Melbourne station). (a)
  still needs a barrier site.
  **More screens (106th build, 2026-10-25; no pass rule applied):** (1) The partner's phone (iPhone, Chinese
  interface, her account, same house, 13:34; `screen_match_20261025_partner_phone.csv`): same direction as the
  user's (order, per 1 SD: distance -0.61 [-1.24, +0.02], rating +2.19 [+0.28, +4.10]; n = 17, too few to read
  the size); 5 Sponsored cards (none on the user's own account). (2) Same place, within minutes, the list barely
  depends on who asks (user's phone 14:50-14:53 signed out and on an NYU account; the partner's 14:58-14:59 account
  and incognito, her own transcription, unchecked): regular cards' top 20 share 17-18 venues, Spearman 0.96-0.98,
  across person, device, language and account; the only personal trace seen is a saved place ~25th. Ads differ
  (2-5 per list signed out, incognito or on another account). So a common list exists and one shared Top-N stands
  for it (first evidence: one site, one afternoon). (3) The user's own account at 12:06 vs signed out at 14:50:
  same venues reordered; venues closing within the hour dropped 10-14 places (KOME, Myth Cafe, Bite Club): open
  status or time to closing may enter the order (Claude's hunch, untested). (4) Spencer St hub, incognito,
  standing still (user): zoomed-out and zoomed-in searches list nearly the same venues; displayed distances
  jumped up to ~110 m between them (GPS); a search re-run on a moved map changes the list (the partner's 13:36
  search). (5) `diagnostics/screen_position.py` trilaterates a phone from card distances (reproduces the 105th's
  ad hoc position to 1 m); the screen scripts take `--screen`. Frame: Google's named local-ranking factors are
  relevance, distance, prominence (source page unchecked). Next (user): gauge which metrics correlate with rank,
  time to closing included.
  **Card metrics, Melbourne Central, distance sort (107th, 2026-10-25; build then discussion, user):** (1) Six
  transcribed screens, card values, sponsored and repeat cards dropped (`diagnostics/screen_rank_metrics.py`):
  joint Plackett-Luce on the two distinct sessions (user 12:06, partner 13:34; 120 cards), per 1 SD: log distance
  -1.11 [-1.42, -0.79], rating +0.78 [+0.51, +1.04], open now +0.47 [+0.25, +0.68], log hours to closing +0.21
  [-0.27, +0.69], log reviews -0.04 [-0.22, +0.15]; price no effect where distance is known. Open counts like being
  1.6x closer, +0.1 star like 12% closer; per log metre lambda ~ 2.1 (1.5 in the 105th phone fit): Huff's form and
  size. (2) The card's distance is straight-line from the device, rounded to 10 m below ~300 m, 50 m to 1 km, 0.1 km
  above (ad hoc, scratchpad, not kept: card vs haversine median gap 11 / 5 m, vs walking 172 / 124 m; card over
  straight-line uncorrelated with the venue's detour ratio, 0.09 / 0.02). (3) No "can you make it" filter: KOME,
  1.4 km and closing in 1-2 min, still 11th-12th (partner 14:58). (4) Zoom at a fixed centre changes only the
  sponsored cards (user's test, not transcribed). (5) Melbourne Central, incognito, 15:49 (user's chat uploads,
  not in inputs/): device trilaterated at Melbourne Central (16 cards, residuals <= 44 m), map centred near the
  user's house; the regular cards (450 m to 1.4 km) sit ~1 km SW of the device, 0.8 km from the house; 99 table
  venues within 450 m rated >= 4.5 with >= 500 reviews were passed over; "Search this area" on screen. So the order
  runs from the search anchor (the map), not the device, which sets only the displayed distance. (6) Distance
  sort near [subject], 16:21-16:24: two inversions (Sultan's 1.3 km before Zia Teresa 850 m; Docks 1.1 km before
  Ancient Memories 950 m, both open); R5 from [subject] (ad hoc): the second of each pair is nearer by walk (12-13 vs
  23-26 min) and transit (8-10 vs 20-22), so not travel time; Claude's guess: results sorted one page at a time.
  (7) Home-hex check (ad hoc; the 105th's stock-R5 tables, not the reach model): against the phone screen,
  Spearman of a Huff order 0.57 / 0.61 (bands 1 / 2), distance 0.46 / 0.47, S*' 0.15 / 0.32 (in-sample). Under q
  over a Huff order a pool beyond band 1 adds nothing; under a Huff split the outer ring keeps ~1/3 (lambda ~ 2 is
  borderline in two dimensions).
  **Reading (user, 107th discussion):** Google's nearby list is first exposure, Huff-like, from wherever the map
  points; the flagship does not model it (framing.md FRM-27). (b) now serves the first-exposure lens (scoring.md
  Notes), not the flagship's share rule. Next tests: a detour-site screen (does the order use travel time?), a
  cuisine query, page breaks in the distance sort (where drops fall; distances restarting); poll additions: places
  checked before deciding (casual / special occasion: K), a "can't tell" option (just-noticeable difference).
- **Q20.** Top-up scheme details, to settle before the first top-up (planned, after outputs): minimum
  size for a fetch to count as a test set (else it goes straight to training; at accuracy ~0.92 the
  standard error is ~0.004 at 4,000 pairs, ~0.009 at 1,000, before hex clustering); size of the fixed
  hours drift panel; whether the rolling test drops grouping by destination hex (Claude: drop it,
  grouped CV inside training carries that check). (ODS-11, DCL-15, VEN-15)
- **Q21.** Reachability storage cutoff (drive): RCH-4's 2.5x the band cutoff (~2,500 s routed) on a
  4.08 M-hex grid may be far more than needed; set after the ~100-hex pilot reports rows per search,
  run time and disk size. Floor: room for the RCH-14 factor and the RCH-13 error draws. (RCH-17)
  Pilot run 2026-10-22 (69th, autonomous; facts, cutoff still the user's): 102 venue hexes; 0.13 s per search at
  2.5x, ~20 min for all 8,959; disk node-level 6.0 GB at 1x, 16.6 GB at 1.5x, 44.8 GB at 2.5x; per populated hex
  1.2 / 3.5 / 9.5 GB. Claude's reading: re-routing is cheap, so storing near the cut plus the margins may do.
  (`reachability_drive_pilot.py`; transit timing: `reachability_transit_pilot.py`, RCH-19)
  **Decided 2026-10-23 (user, 79th):** store to RCH-4's 2.5x (~45 GB), within a 200 GB disk budget; bloat flagged
  in the run report for the user to prune. (RCH-17)
- **Q22.** ~~Transit route preference.~~ Closed 2026-10-20 (user): no preference model; stock R5 for time, path dropped, re-rank parked. Opened 2026-10-16. Google trades time for less
  walking and fewer boardings, r5py returns the fastest. Outcome so far: Google's default is its earliest
  arrival on 0.734 of pairs; a walk weight ~2 explains 0.945 of its choices (T7 h); preference arms in R5
  (OpenTripPlanner's defaults, weights fitted on Google's choices) FAIL against stock R5, so no preference
  model (2026-10-17); scalar s = 1 stands (T7 g); walk speed 4.16 km/h from Google's walk-only answers
  (WLK-1); R5's 60 s board slack measured small and removed only at the first board in the model of
  record (T7 e, TRN-13); TravelTimeMatrix at a 1-min window for times, DI only for itinerary detail
  (TRN-6). Path (where people walk) dropped with foot traffic 2026-10-18 (TRN-12); a re-rank of R5's
  options parked 2026-10-19 (TRN-13). Matching Google's walk pattern dropped 2026-10-22 (user): the gap is route
  choice; street choice could add ~0.03, a walk-weight re-rank ~0.01 (TRN-12). (TRN-6, T7, T8, TRN-12, TRN-13)
- **Q23.** Transit band metric and boundary top-up: **decided 2026-10-18 (user, discussion); model fitting
  closed 2026-10-20 (user).** Bands 1-2 are judged on +-3 min zones around the 10 and 20 min cutoffs
  (recall and precision per zone; lower end of the sampling range above 0.6; an unbiased-noise bar from
  R5's error away from the cutoffs; misses not one-sided), hard misses per cut (lost / false reach in
  3-10 min windows, each Wilson upper <= 5%; a fail is a recorded cost unless severe, > 10%, or
  concentrated in one service-density third) and the count ratio (0.90-1.10); Google's time is a range
  from the earliest of its first 2 routes to its default (user). Replaces TRN-12's 0.90 band agreement
  for bands 1-2. Data: training half, second batch and the boundary top-up (TRN-14: zone 1 206, zone 2
  365 pairs); the test half for the final evaluation only, opened once.
  **Model of record (user):** the no-wait model (stock R5 at 4.16 km/h, first board's slack removed) at
  plain cuts 10 / 20 on the v2 pathways network; zones pass, hard misses fail but neither severe nor
  concentrated: an accepted, located cost (knife-edge late misses at street stops; early misses at CBD /
  underground train stations and on short tram rides). In-sample 3-band accuracy 0.964, kappa 0.861.
  Considered and not pursued: a scalar / 1-min cut shift, a 30 s edge shift, a dense-area ride stretch,
  a re-rank of R5's options, wait modelling (TRN-13; transit.md Not adopted).
  Test half: extended by 4,000 pairs (TRN-15), fetched 2026-10-20. Scoring-date check
  (2026-10-20): 4 of 1,252 training band calls change on the pairs' own dates, all Friday. Decided
  2026-10-20 (user): score on each pair's own date; the second batch and top-up are re-routed and the
  official scoring re-run first (free). Test reading rule decided (TRN-15; revised 2026-10-20 before
  opening, user): zones on the training bars (noise bar from the test's own off-cut pairs); hard misses
  and count ratio on the training bars unchanged (fail a recorded cost; barred only if severe or
  concentrated, thirds fixed at the training cuts); lost reach at 10 report-only; "severe" only at
  n >= 35; pooled is the verdict, per release reported; medians beside means. The 3,884 test pairs
  sharing a destination hex with a training set stay in the gate (stated limitation); the 2,045
  unseen-destination pairs (fetched training pairs only; user, 66th) are scored report-only. Before opening: Claude's predicted results, then the
  test scorer reproducing the training tables. Stage 3
  (paid window value) skipped (user). Own-date re-scoring done 2026-10-20: every verdict unchanged (false
  20 19 -> 18 / 503). Station fidelity check done 2026-10-20: R5 uses all the feed holds at the weak
  stations, no GTFS-faithful fix; Google follows PTV's pathways at most stations, differs by > 1 min at 11
  (static, cause unknown): a stated limitation, effect on the output unknown (user; no blend or offset).
  Scope wording (TRN-11) aligned to the code: a pair is excluded when Google's default is out of scope.
  **Test opened once 2026-10-20 (TRN-15 result; concluded, user):** 5,234 of 5,248 pairs scored, scorer
  first reproducing the training tables exactly. Pooled verdict: zone floors 0.799 / 0.828 and noise bars
  pass; z2 balance fails (R5 early 43 vs late 24); false reach at 20 fails (34 / 792, upper 0.059), not
  severe, not concentrated: a recorded cost; lost reach at 20 passes (11 / 417); count ratios 1.011 / 1.084.
  The 2026-10-09 test half alone trips the per-release severe clause (false 20, 14 / 190, upper 0.120);
  ruled by the user after results: the clause catches a release that breaks, and the same release's
  training half ran 4.2% (all four sets 52 / 1,295 = 4.0%), so not barred; stated plainly as a post-result
  reading. Model of record kept as is, no backtracking (user): R5 leans early near 20 min, misses a ride
  now and then (~1-2 min slower to the boarding, then the next vehicle). Every predicted quantity fell
  inside Claude's pre-registered ranges. 30 s edge shift parked for any future fresh test.
  Catchment sensitivity done 2026-10-20 (RCH-13): stock vs no-wait moves the subject's catchment by about
  a tenth (residents +10% within 20 min); band-2 totals carry about +-10% from the transit model (a
  stated limitation). Access walk vs Google's done 2026-10-20 (WLK-6): +17 s median, linked to late
  misses; next: Q24.
  (TRN-13, TRN-14, TRN-15, RCH-13)
- **Q24.** Principled timing corrections (plan, user 2026-10-21; run on training pairs 2026-10-21; adopted for now, user, 2026-10-21): three fixes
  together, each matching how Google reports time rather than tuning to it: (1) drop the connector at
  both ends (snap origin and destination to the street; WLK-3); (2) refit walking speed on Google's
  walk-only routes without connectors, in seconds (R5 street path / Google seconds per pair; mean and
  median, 3 decimals; training half, second batch, top-up); (3) read R5's truncated minutes as rounded
  by a 30 s offset at the destination end (after the last vehicle, so no catch changes; via a destination
  placed 30 s of walking off the street, once a probe confirms the link's charge rate). Dropping (1)
  alone made hard misses 30 -> 32 (R5 earlier; WLK-6); (3) pushes the other way (truncation ~30 s
  early, transit Limitations). Scored on the training data with a reading rule written before results;
  the test half cannot validate it (opened). If worth freezing: a fresh holdout from the free October
  calls (~1,159 left) plus a paid top-up (user floated ~$10; needs an explicit budget, S5). Reopens the
  30 s edge shift parked in Q23.
  Route to second-level times chosen 2026-10-21 (user, discussion): the offset (3), exact per pair, not
  only on average (a constant 30 s on the destination's last link moves every path and percentile
  equally, so floor(t + 30) = round(t)), if the free probe passes. The seconds are lost inside R5
  (`TravelTimeReducer.convertToMinutes`), before r5py's `_parse_results`, which only copies minutes.
  Fallback if the probe fails: read the R5 jar's `TravelTimeReducer` before deciding on a patched jar
  (JPype implements Java interfaces, likely cannot subclass: Claude's hunch, unchecked). DI not used for
  seconds (TRN-6 Not adopted). Validation so far set R5's truncated minutes against Google's rounded
  ones (SCR-10), so recorded verdicts carry ~30 s toward "R5 early". The probe's pass / fail rule is to
  be written before it runs. (WLK-1, WLK-3, WLK-6, TRN-6, TRN-13, SCR-10)
  Run 2026-10-21 (autonomous, `diagnostics/transit_q24_combined.py`): the moved-destination probe FAILED
  (a point 35 m off its street keeps its edge on 3.9%: dense walkable edges), so (3) was built instead as
  destination stubs (user: "similar to our pathway"): per destination and speed a 30 s dead-end footway
  (tunnel=yes body, 1 m linkable tip) from R5's own split point in the v2 derived extract, the destination at
  the tip; checks pass (no stop, origin or destination on a stub; every stub charged exactly 30 s once drawn
  on R5's sphere). (2) speeds: median 4.143, mean 4.135 km/h (barely below 4.16). Hard misses vs the model of
  record's 30: (1) 32, (1)+(3) 28, (1)+(2) 31, all three 25 (either speed; IMPROVES on the pre-set rule);
  error to Google's range median -1.0 -> 0.0; zone 2 balance now passes, zone 1 noise bar now fails (recall
  0.862 -> 0.793). In-sample. Adoption and the fresh holdout's fetch (4,000 pairs drawn past the test
  extension, `transit_samples.draw_transit_holdout`) are the user's call. Production would need stubs for
  every destination and origins snapped on a stub-free network.
  R5 patch route decided 2026-10-21 (user, discussion; TRN-16): (3) as a one-line patch of
  `TravelTimeReducer.convertToMinutes` (floor -> round to the nearest minute), and later (1) as a patch,
  instead of stubs and snapping; conventions only, an equivalence test per patch, sampling on stock r5py.
  Stubs vs patch chosen on pair-by-pair training equivalence before the holdout is scored; the test also
  covers pairs near r5py's `max_time` (rounding can lift 59.5 min onto the cut).
  Revised 2026-10-21 (user, 53rd, discussion): (3) as seconds out of R5, not rounding inside it
  (`convertToMinutes` returns seconds; rounding in Python, SCR-10); then (1) as a no-connector patch, then a
  zero board wait; order, candidates and tests in TRN-16. Q24 adopted for now; walk speed (4.143 median or
  4.135 mean) still to choose; holdout fetch agreed for now, cap and timing owed (S5). Claude's check
  revisions in `transit_q24_combined.py` accepted (user). Next (build): patch 1 on the 100-pair set.
  2026-10-21 (54th, build): walk speed 4.143 (median) for now (user). Patch 1 built: exact equivalence with stock;
  against the stubs 3 / 100 pairs differ, all from the stubs (TRN-16). Correction to run 3's "every stub charged
  exactly 30 s": that holds for R5's street router; inside TTM a stub adds 29 s on 41 of 262 calls (edges round up,
  a destination's last partial edge and transit egress distances round down; source read, counts match).
  Stubs or patch for (3) owed (user). Next: prior-work search, then P2. (`transit_r5_patch_seconds.py`)
  2026-10-21 (55th, build): prior-work search done (nothing found; transit.md T7). P3 redefined (user): board wait 0 s at
  the first boarding, 200 s at transfers, Google's own rules measured on the training routes
  (`transit_google_transfer_buffer.py`); built on P1, equivalence exact, replaces the model of record's 1-min shift
  exactly; in-sample on 100 pairs error to Google median -31 -> -8 s (TRN-16). R5's transfer walk is ~9 s longer
  than Google's listed (median): buffer kept at 200 s. Next: P3 verdict on a full training run, then P2.
  (`transit_r5_patch_board_wait.py`, `transit_r5_transfer_walk.py`)
  2026-10-21 (56th, discussion): transfer-only walk speed candidate (user leaning to test; TRN-16): centres R5's
  transfer walk on Google's (~4.5 km/h) without narrowing the scatter; whether a Google-fitted transfer speed is a
  TRN-16 (1) breach or a second Q24 (2) parameter is open (user). After P3's full training run.
  2026-10-21 (57th, build): P3 full training run (3,448 pairs, rule OK'd before the run): IMPROVES over the model of
  record on patch 1 (hard misses 25 -> 23, false 20 upper 0.051 -> 0.046; mean error to range -2.53 -> -1.66 min;
  2+ boardings median -113 -> -20 s; zones pass for both; 4 band calls change). Adoption owed (user). Stubs vs
  patch 1 for (3): 34 pairs differ, hard misses equal, zone 1 noise bar passes on patch 1 only (TRN-16 (5) evidence;
  choice owed). Transfer walk speed: Claude leans park (small prize after P3), else (2) as a slot (default = walk
  speed) with a declared fitted value. Next: P2. (`transit_r5_patch_board_wait.py` score_train)
  2026-10-21 (58th, build): decided (user): P3 adopted (retires the 1-min shift); (3) by patch 1, stubs kept only as
  a check; transfer-only walk speed parked. P2 (no connector charge, Q24 (1)) built on P3: R5 charges the connector at
  three places on TTM's path (origin start states, walk-only destination, egress tables), zeroed by one helper per
  class; B1-B3 and the exact checks pass; on the drawn points it equals snapping except snapping's own rounding
  (a snapped point re-splits 11-22 mm along or onto the next edge; 1-2 s). Full training run (3,448 pairs, rule set
  before): hard misses 23 both (MIXED, equal), seconds differ on 35 pairs, minutes on 3, band calls 0. P2 adopted
  (user): production routes origins and destinations as drawn, no snapping, no stubs. Model of record: R5 with P1 +
  P3 + P2 at 4.143 km/h on v2. Next: per-edge rounding test. (`transit_r5_patch_connector.py`)
  2026-10-21 (59th, build): decided (user): walk speed 4.143 km/h (median), final; holdout fetch deferred (later, not
  scheduled). Per-edge rounding confirmed: R5 ceils each walked edge (0.48 s per edge, edges median 11.5 m; walk-only
  excess median 50 s). P4 (round once per path) built, all checks exact; full training run WORSENS (hard misses
  23 -> 27, zone 2 balance fails) though Google walks now match (0 boardings +16 -> -1 s): R5's transit is early and
  the ceiling partly hid it. P4 not adopted for now (Claude's recommendation; user moved on), jar kept for a retest.
  Model of record unchanged. Next: stop-link connectors (TRN-16). (`transit_r5_edge_rounding.py`,
  `transit_r5_patch_walk_path.py`)
  2026-10-21 (60th, build): stop links set aside on existing evidence (source read: one straight LINK edge pair per
  stop, walked at walk speed; H-walk LINK metres median 2.0 m street, 0.0 m train; a link only adds time). Leg-by-leg
  error to Google on 3,448 training pairs from R5's own paths (TTM with path results; F1 path = scored seconds on
  every pair): same-line pairs (56% of both-board) unbiased, median +2 s, mean abs 68 s (access +13 s mirrored by
  wait0 -14 s; ride and transfer 0). The early mean is route choice (R5 walks further to ride less or skip a transfer;
  other-line pairs mean -167 s, mean abs 263 s; tail < -5 min carries all of it) and 129 pairs where Google gives a
  5-6 h answer and R5 walks (mean -1,440 s). Of the tail's route-choice pairs Google never returns R5's lines on 53%,
  returns them later on 17%, returns them earlier than its default on 30% (preference). No R5 convention left to
  patch (Claude's reading). Next (user agreed): what the never-returned combinations share (long walks, walked
  transfers, stops), then likely a stated limitation; walk reluctance in R5 not favoured (TRN-16 (1)).
  (`transit_leg_error.py`)
  2026-10-21 (61st, build): decided (user): Google is the fit target; parameters may be fitted to Google on
  training pairs, declared, with the unopened holdout as the check (TRN-16 (1) revised). The early tail stays a
  stated limitation for now (R5 = fastest feasible trip). Never-returned combinations: no walk cap, R5 beyond
  Google's walks on 0.40 of them (rule's 0.5 line failed). R5-train vs Google-tram pairs (71, the tail's top
  pattern): no station time; where Google returns the train it arrives ~7.5 min earlier but walks ~12.7 min more
  (walk reluctance, as T7 (h)'s w ~2). 190 s transfer buffer rechecked: 200 s matches Google (same-line transfers
  median 0 s). Next: the user's choice between estimating Google's walk weight on training pairs (free) and
  freezing the model (fork, production release, then holdout). (`transit_leg_error.py` combos, railtram)
  2026-10-21 (62nd, build): Google's walk weight estimated on 3,340 training pairs with 2+ routes (rule OK'd by the
  user before the run): cost = arrival + (w - 1) x walk time; w = 1 picks Google's default on 0.720, best w 1.70 on
  0.853 (within 1 pp 1.55-2.05; bootstrap 1.55-1.95). Google has a walk weight (R1) and it is stable across training
  half, second batch and top-up (R2). Report only: with a transfer penalty, tau 450 s and w 1.95 pick 0.942 (as
  T7 (h)); a single w explains at most 0.962. Application not decided (user): Claude leans pick among R5's own
  option lists by the weighted cost and score that option's real arrival (never slowing the walk, T7 (i)); else
  freeze and state the weight as a finding. (`transit_walk_weight.py`)
  2026-10-21 (63rd, discussion): application planned (user), not built: the weight picks the route, the reported
  time stays the route's real time. P5 (transfer penalty, exact): R5 keeps one state per round (r boardings,
  `scheduleState[r]`) but returns only the last; per stop pick the round minimising real time + tau x (r - 1) and
  report that round's real time (paths from the same round). P6 (walk-weight pick): two TTM runs, default and walk
  slowed by w, both with P5; the slowed run's path re-timed at real speed (its vehicles stay catchable); take the
  default only if its time saved > (w - 1) x the walk it adds, else the slowed route. Comparison in Python first; one
  route per pair already (1-min window at Google's minute, TRN-6). The slowed walk only picks (T7 (i) holds for
  reported times). Next: free check on Google's training candidates (slowed walk keeps Google's default catchable;
  P6 pick vs 0.853; P5 vs 0.942), pass rule before the run; else freeze. Details TRN-16.
  2026-10-21 (64th, build): free check run (rule OK'd by the user before the run): P6 at w 1.70 picks Google's
  default on 0.800 (ideal 0.853; G1 fails, 0.053 below), P5 + P6 at (1.95, 450 s) 0.813 (ideal 0.942; G2 fails).
  Slowing the walk in a timed search does not price it: a slower access walk only uses up the wait (Google's default
  stays catchable on 0.555 at 1.70), so neither run charges the access walk where Google's preference sits; P5 alone
  lowers the share (post-hoc). Decided (user): P5 and P6 not adopted, nothing built; R5 can price only time and
  transfers, and a walk weight needs a cost criterion inside the search (McRaptor, priced too costly in the 63rd).
  R5 reports the fastest feasible trip; the walk weight stays a finding about Google's ranking, not a model
  parameter. A slower-walker scenario band dropped (user). Next: freeze (fork, RCH-18, holdout).
  (`transit_walk_pick_check.py`)
  2026-10-21 (65th, discussion then build): walk charge after routing (user's idea; R5's transit time + (s - 1) x
  its route's walk, walk-only uncharged): patch rule PASS at s 1.10 (hard misses 23 -> 19) but a blanket ~1 min
  shift (agree 1,492 -> 760; three zone checks fail); not adopted (user), TRN-16. Decided (user): the P3 buffer
  sweep (170-230 s) runs before the freeze; holdout fetch capped at US$20 (timing open, departures by Nov 2); H-walk
  readings (WLK-6) and the catchment reading (RCH-13) approved. Next: buffer sweep, freeze record with the holdout
  rule, holdout fetch. (`transit_walk_charge.py`)
  2026-10-21 (66th, build): decided (user): unseen-destination subset = 2,045 (TRN-15 (9)); the patch rule gains a
  zone gate (zone checks passing on the model of record must still pass); order changed: holdout fetch first, sealed
  until the freeze record and its reading rule. Holdout fetched: 4,000 pairs, all HTTP 200 (~US$14.21). P3 buffer
  sweep (170-230 s): flat, every buffer the same hard misses (23 pooled), no band call or zone change; 200 stays.
  Next: freeze record with the holdout reading rule, then open the holdout. (`transit_buffer_sweep.py`)
  2026-10-22 (67th, build): **model frozen** (R5 + P1 + P3 + P2 at 4.143 km/h on v2, jar hash in TRN-16); holdout
  reading rule = TRN-15's test rule, report-only extras in TRN-16. Seen pairs, report-only: old test hard misses 49 ->
  31 on the same pairs under the frozen model; all seen pooled passes every check. Predictions saved; holdout opened
  once by an autonomous run (user: blind). (`transit_holdout_score.py`)
  2026-10-22 (73rd): **verdict (user): holdout accepted**; the frozen model stands for bands 1-2, lost 20 a recorded
  cost.
  2026-10-22 (69th, autonomous): **holdout opened**; facts in TRN-16. Zones pass;
  lost 20 9/272 (upper 0.062) fails the 5% line, not severe or concentrated, a recorded cost by the rule; other hard
  lines and ratios pass; every figure inside the predicted ranges; 3-band accuracy 0.969, MAE 3.00 min.
  (`transit_holdout_score.py`, `transit_holdout_metrics.py`)
- **Q25.** Transit departure schedule for bands 1-2 (user, 2026-10-22, 70th discussion; decided 2026-10-23, 81st): coarsest schedule the
  data allows, unit the 30-min slot, competitors only in slots overlapping the subject's; spans clustered from routed
  results on a 60-origin week scan plus a GTFS service profile, schedule picked from its cost / error table (user).
  R5 departure-window percentiles not pursued (model change). Run (71st, facts): within-hour departure noise ~ the
  difference between hours; 6 spans at 1.0x the floor; subject's hours 2 spans (~9 h) to hourly every day (~166 h).
  Open: weekend scope, random weekday, repeats per span. (RCH-20)
  2026-10-22 (72nd discussion): the pass is subject-scoped (RCH-21), so a departure costs minutes, not ~4.6 h; the
  schedule covers the union of the subject's and its sibling venues' hours. Weekends: still open; user and Claude lean
  to inclusion, labelled, but weekends differ in where service runs, not only how often, so no free test validates it
  fully. Decided by the free checks of RCH-25 (error by ETA and per-hour service level; a network-wide weekend
  coverage map per GTFS release, any subject a readout); a small weekend Google sample is the paid option (S5).
  Trackwork stays a limitation. Uncertainty function planned (RCH-23).
  2026-10-22 (73rd, build): departure step deferred until its cost is weighed (user). Claude's rough cost for one
  subject (both venues' hours, 0.032 s per origin): ~30-45 min per departure with the 10-min oracle margin (RCH-22;
  envelope size unmeasured); 2 spans ~1-1.5 h, 2 spans x 5 repeats or hourly Mon-Fri as one ~5-7 h, hourly every day
  ~35-50 h, 10-min steps one weekday ~30-45 h. Weekend checks run (RCH-25 facts): thinness does not widen the error;
  weekend reach labelled "thinner service on weekends; not tested" and a night disclaimer for subjects open 00-07
  (user); inclusion still open. Uncertainty function built with a night group (RCH-23).
  2026-10-22 (74th discussion): Stage A's oracle redesigned (RCH-26): reverse Dijkstra on a two-layer walk +
  synthetic-ride graph, always generous (user), cut 30 + 10 min to start; superset check against the frozen model
  next; if it holds, the venue -> hex oracle, its margin and the self-check lapse (RCH-21, RCH-22), and the cost
  table above falls with the envelope.
  2026-10-22 (75th): the oracle runs 0.1-0.3 s per venue (build ~3 s), so Stage A is free. Decided (user): pass /
  fail by expected persons missed <= 1% of the band's expected persons, cut <= 55 min, staged caps 20 then 30; span
  oracles per day type (Mon-Thu, Fri, Sat, Sun) x 30-min slot, whole network, per GTFS release. Superset test next
  (RCH-26).
  2026-10-22 (76th, autonomous): graph oracle superset test on the sample passes at cuts 30 / 40 (caps 20 / 30); a 30-min
  slot oracle covers every departure minute at +1.5% set size; clock-hour bin +0.2-1.2% (AM shoulder +8%), choice owed
  (user leans 1 h). Transit timetable-optimism disclaimer (user; transit.md Limitations). (RCH-26)
  2026-10-22 (77th): shelf line at the 5% level and the night error group for night slots (user); bin and production
  cuts after the full-band check, whose first report has a bug (other-venue oracle rows unsaved). (RCH-26)
  2026-10-22 (78th): bug fixed; full band for Mon-Thu 12:00 passes at the start cuts 30 / 40, 0 pairs outside the set;
  all 192 span graphs ~200 MB per release. Decided (user): the 30-min slot bin stays (clock hour adds ~1-2% routing,
  +11% in the AM shoulder; disk is cheap, time is not); production cut 30 by default, serving band 2 with its
  uncertainty (cut 40 only if times to 30 min are ever needed; ~2.3x the routing). (RCH-26, RCH-19)
  2026-10-23 (79th, user): **subject pass schedule decided:** one departure per 30-min slot at a random minute in
  the slot (k = 1; repeats later), over the union of the subject's and branch's hours, four day types (Mon-Thu,
  Fri, Sat, Sun) on one fixed date each inside the newest GTFS release's window (RCH-18); weekends included,
  labelled. Departures for the 60-venue transit sample deferred (Q26). (RCH-20)
  2026-10-23 (80th, autonomous; facts): dense reference (8 venues x 4 day types x 6 departures per slot, band 2):
  departure noise 16-40% of persons (central venues 4-8%) dominates slot differences (3-14%); one departure per slot
  gives the subject's week headline +-3.7%; day types differ, slots within a day type look alike. **Spans as the unit
  (user):** ~27 random departures across spans match one-per-slot's error (42). P8r (TRN-16, reporting) reads a whole
  span window exactly: ~57 single-departure equivalents for the subject's week, no departure noise. Open: random
  spans vs span windows (draws mode for Top-N), the span boundaries (Claude's: weekday evening; weekend lunch /
  dinner; Sat late). (RCH-20)
  2026-10-23 (81st discussion): **decided (user):** the subject pass reads whole P8r windows (draws mode) over the
  subject's own hours, four day types, exact (~4 h); hybrid targeting is the standing scheme for repeated passes and a
  sibling's optional base (heavy-weight Mon-Thu span whole, one random-start 30-min window per other span, spans
  flagged by a GTFS trip-count step read whole): ~23 singles per venue, every one of the 8 venues <= ~1-2% (upper
  <= 2.9%) vs one per slot up to 6.7 / 8.0%. Sibling envelope out of the subject pass (cannibalisation only, inside the
  subject's envelope); P8r adopted. Post hoc checks: trip-count flag on the 8 dense venues, within-window trend.
  ETA ~4.5 h per pass (~6.5 h with the sibling's base). Finer oracle bins not pursued. (RCH-20, RCH-21, RCH-26, TRN-16)
  2026-10-23 (82nd discussion): draws mode reports at most 5 minutes per call (R5's percentile cap); **decided (user):**
  P8r extended (cap lifted, windows read in <= 90-min chunks); production recomputes everything, earlier diagnostic
  data only as checks (RCH-18). ETA revised (Claude's): ~3 h build + ~5-5.5 h runs. (TRN-16, RCH-18, RCH-21)
  2026-10-23 (83rd, autonomous build; facts): P8r draws extension built and tested (T0-T4 pass); production network,
  drive pass (45.7 GB) and envelopes built and checked against the diagnostics; timing run (chunk 1 of 16): 0.20 s per
  origin per 90-min chunk, envelopes 8.6k-11.7k origins (164k origin-chunks), so the subject pass is **~8.3 h**, past
  the 6 h stop line: not launched (user's hold). Choice owed: run it as is overnight, or trim. (RCH-21)
  2026-10-23 (86th, facts): on the subject's exact pass hybrid targeting errs 0.71 / 0.72% (band 2, persons / flat
  share; 30 min 1.92 / 1.36%), inside the 81st's bound; the trip-count flag had nothing to catch (untested). (RCH-20)
- **Q26.** Venue sample for P̄ (user and Claude, 2026-10-22; open): sample size and ring strata for RCH-24, set from
  the target interval on P̄ once envelope sizes are known (RCH-21). (RCH-24)
  2026-10-23 (79th): 60 venues (user), field-wide; drive P̄ from the full pass, no sample; transit sample deferred
  (~4 h per departure for 60, rough); how to sample its departures decided later (user).
  2026-10-23 (80th, facts): noise is independent across venues, so R-bar needs few departures: 0.53% at one per slot,
  0.95% at one random departure per span (7 per venue, ~80% fewer); departure noise is ~0.06% of the spread between
  venues (log), so percentiles barely move. Proposal (Claude's): one random departure per span per venue.
  2026-10-23 (81st): **departures decided (user):** one random single per span per venue (R-bar ~0.95%); windows
  (0.49% at ~2.3x the cost) not needed. Transit sample run still deferred. (RCH-20)
- **Q27.** Transit claim target (user, 2026-10-23, 80th discussion; open): migrate from "the faster end of Google's
  recommended routes" (FRM-24, now) to "the time of Google's top recommendation" once a route-attractiveness model
  predicts Google's default, validated on a fresh holdout scored against the default alone, with a bar set before
  it opens. The fast-end model stays as the optimistic bound (bracket, not average: no defensible weight between the
  two). Routes: candidates plus a choice model fitted on Google's saved alternatives (cheapest), or McRaptor (slow).
  First, free: split the early bias into route choice (R5 ~ Google's fastest alternative) vs network / timetable.
  Ties to the test-fetch budget with P7 (and Claude's proposal: P4 + P7 scored together). (FRM-24, TRN-16)
- **Q28.** ~~Knock-ons of the persistence rule.~~ Closed 2026-10-23 (87th discussion, user, on Claude's leans): ties
  share (proximity tie-break dropped); low-evidence tier below every rated venue; contention = adjacent ranks, swap
  credit; reputation dependence d(share)/dq; SCR-1 wording; reference marks Claude 0.6, user (analyst) 0.8. Positions in
  SCR-1, SCR-3..5, SCR-14, SCR-16. Opened as: (SCR-15; user and Claude, 2026-10-23, 83rd): (a) SCR-4's proximity
  tie-break goes (ties share weights), which also settles SCR-2 / SCR-4's contradiction on ties; (b) SCR-5's
  low-evidence tier under rank weights (kept below every rated venue, or shrunk ratings ranked with them; S3's m);
  (c) SCR-14's contention ("the last Top-N slot") redefined for weights (e.g. venues one rating step either side);
  (d) SCR-3's reputation dependence read as d(share)/dq; (e) SCR-1's wording: q reads Google as a ranked list in
  rating order (a stylised diner, not Google's ranking); (f) Claude's guess of q for the owner display (Claude: ~0.6,
  Google's local results show ~3 places up front). Settle lightly, as conventions (FRM-25; user, 84th). (SCR-15, SCR-16)
- **Q29.** ~~Rating-rule challengers.~~ Closed 2026-10-24 (97th discussion, user): S*' is the key (S* with a displayed
  5.0 read as 4.975, 1.0 as 1.025), m 15 the headline (m reopened as Q31). Why (user): closest to the user's own
  judgement in blind pairs (weak evidence), and shrinkage is a convention where percentile is not. P not adopted;
  B, B~, R out of scope (96th). Opened as (user, 2026-10-24, 94th): controls (user): the flat displayed rating (F, ties
  within 0.1, no inference of ours) and shrinkage at m 15 (S*, the convention, SCR-20 as built). Challengers, each
  reading a displayed 5.0 as 4.975: S*', the shrunk key rounded to 0.1 (B) and smoothed (B~), percentile within
  review count (P), a prior varying with log count (R). Graded against R1-R15 (scoring.md Notes "Rating-rule grade
  sheet"): a grade argued over, not a hard bar (user). Steps: a free disagreement test with blind pairs the user
  judges (R15), then band 1-2 reruns (~30 min each) for survivors, judged by band flips. Why: thin ratings are
  inflated (median 4.7 at <= 5 reviews vs 4.4), not only noisy; near-equal well-reviewed venues may be ties.
  First runs and blind pairs (96th): scoring.md Notes "Rating-rule and pool runs" (blind pairs: S*' 21 / 30, S* 19,
  P 10, F 7). (SCR-20)
- **Q30.** Band 3's headline (user, 2026-10-24, 94th; open): the unlock rating, the lowest slider rating at which the
  drive band yields a meaningful share (user: you must be exceptional to pull people from afar). The answer is a step:
  at q 0.7, 4.8 → 0.8 persons, 4.9 → 6,696 (0.69% of reached), 5.0 → 259,950 (27%), so a threshold only picks 4.9 or
  5.0. Claude's lean: report "opens between 4.9 and 5.0" with both values; else a threshold the user states first
  (report default: 1% of reached, Claude's). Relates to the band-3 role question (91st, owed). (SCR-1, SCR-16)
  107th (user): band 3's diner is the special-occasion diner, the bands 1-2 ruler applied to a wider field with more
  search; under best-of-K (Q32) K grows with search effort, so the unlock rating falls out of the rule. The owner is
  asked whether a 20-min drive to the venue is plausible (a fast-food owner may set the band aside). The field is
  every restaurant, not peers by format (Q9; out of scope for now).
  108th (user): per-band K is replaced by Q32's stages: the band-3 diner searches three stages of k looks over nested
  fields, so the unlock rating is read off the staged rule's band-3 run.
- **Q31.** m for the shrunk key (user, 2026-10-24, 97th discussion; open; m 15 stays the headline meanwhile). With σ
  at the scale ceiling, 15 is the most an independent-reviews reading allows (τ 0.40). Cases (Claude's, discussed,
  not decided): larger, ~34-48 (the free fit's m 33-59), if the free fit's σ 2.3-2.8 above the ceiling is read as
  correlated reviews (launch friends, gating, filtering: fewer effective reviews); the 93rd read the same excess
  as survivorship (weak venues close before collecting reviews), which doesn't argue for a larger m; smaller, ~9,
  if real review spread is ~1.2. The original hand-picked 60 has no derivation found. Diner trust doesn't decide it
  (92nd). 101st: reruns done (the 4.8 headline b1 / b2 1,270 / 960 at m 15, 1,959 / 2,958 at 35, 2,495 / 4,443
  at 48; m 9 within 25%), so it doesn't close itself. The 60's origin (user): the user's partner's trust floor
  ("not below 60 reviews"). Her break-even pairs fit no m (count-led on both sides; she says not universal);
  rating + β ln n fits them (Claude's, fitted after). User: a high count is also proof of demand and resilience,
  not only a clearer signal. Open, more judges first (user): shrinkage vs a count-as-demand rule; diner types as
  a mix (Claude's idea); whether diner trust decides it after all. 102nd (discussion, user): m 15 is a placeholder,
  not definitive. Name the route before the number (user agreed): statistical (15 is the most independent reviews
  allow; higher needs correlated reviews shown, not survivorship) or behavioural (m models diners, from people's
  answers). Next evidence: real people, not LLMs. The [subject] owner answers as a seller (label him, or ask him to
  predict his customers); his customers already chose a 4.8 on 1,664 (label them). Judges so far: the user (not
  blind) m 14-17, 5.0s taken from 80 reviews; the partner 132+; nine coherent LLMs 28-60 (illustration only): the
  two humans sit either side of the models. The 60 works as a threshold for both (partner: trust floor; user: a 5.0
  past ~60 is worth a look), not a weight (Claude's reading); threshold plus a small m is a third rule option
  (Claude's idea). 106th: the user's sister (Korean translation; 22 picks, 2 "same") took the larger count
  every time: m 141+ (20 / 22), β ln n from 0.11; her reason: many reviews stop attracting at a low rating (count
  helps above a pivot, hurts below: a rating x count interaction, Claude's form, untested). Two count-led people
  near β 0.11-0.14, the user near m 15. (SCR-20; scoring.md Notes, the fits, m reruns and break-even pairs)

- **Q32.** Share rule: does best-of-K replace q? (user and Claude, 2026-10-25, 107th discussion; open, candidate.)
  q's story is retired: q^(r-1) assumes the diner meets venues in rating order, while Google's list is distance-led
  and diners look venues up one by one (FRM-27). Candidate: the diner looks at K venues in random order among those
  in reach (draws, SCR-12) and takes the best by the S*' key; with M in reach, rank r's share is
  C(M-r, K-1) / C(M, K) (equal encounter; a Google-ordered encounter, Huff weights, is the variant). K = 1 is flat,
  large K best-takes-all; the top venue holds at most K/M, so in dense fields reputation multiplies a fair share
  rather than taking the hex. K grows with search effort by band (band 3, Q30). Owed: scoring against C1-C9 (C2
  partly; C4 fails, a worse entrant can help a mid incumbent: principle or preference?); K's source (owner's guess
  first, a curve; the poll question); near-ties (just-noticeable difference) vs the unbinned key. Rebuild and
  illustrations: next session (user). (SCR-15, SCR-2)
  Decided 2026-10-25 (108th discussion, user; built: not yet): best-of-K replaces q as the headline (SCR-23), in
  closed form, not simulated. (1) K per diner geometric with mean k (stop chance 1/k after each look: constant
  patience; keeps q's depth, q = 1 - 1/k), one draw per diner, Poisson the sensitivity. (2) k: the owner's guess
  pins the headline (the 87th scroll-depth question asks for k directly); reference marks from q's 0.6 / 0.7 / 0.8
  = 2.5 / 3.3 / 5; soft outside anchor: grocery consideration sets of 3.3-4.0 (unverified, `literature.md`); no
  restaurant source found; the 3.3 mark is 1 / (1 - 0.7) = 3.33 exactly. (3) Story: vibe sets when to stop, rating picks among the venues seen (recall allowed);
  satisficing (stop at the first above a bar) the alternative. (4) Stages by band: one universal k; a band-b diner
  searches b stages, each drawing k looks at random from that stage's whole field (inner venues again, minus those
  seen); the best of the pool wins. Why (user): a diner who accepts a longer trip makes the most of it (commitment,
  not occasion), and search spreads outward from where the diner is. Proximity comes from nesting, with diminishing
  returns set by density, no decay rate. (5) k doesn't grow with M (attention is limited); K = k(M / M_ref)^a an
  unbuilt sensitivity (Claude's). (6) Pool uniform within a stage: a choice made from limitation (exposure per venue
  can't be measured; Manzini-Mariotti form in scoring.md Notes). (7) Ties: the unbinned S*' key, exact ties split
  equally; near-ties left to shrinkage (cheap here: neighbouring ranks get almost equal shares). (8) Criteria: C4's
  failure accepted as principle (a worse entrant takes a look a better rival would have had); C1 holds within a
  ring only; C6 reads "no continuous distance effect; nesting only". (9) Presentation: in one stage the top venue
  gets k x fair share, the bottom (1/k) x (geometric), so nobody gets zero (user: even the worst-rated get some
  diners). Owed (build): best-of-K beside q; checks K = 1 flat, K = M top-1, one hex by hand, staged vs flat pool;
  how often a transit-field venue is outside the drive field (band 3 nesting); reruns bands 1-3 judged by band flips;
  remake the 98th rating maps and slider / rarity figures.
  Build (2026-10-26, 109th, autonomous; status, not a decision): staged best-of-K built for bands 1-2
  (`functions/share_staged.py`, `scoring.build_staged_shares`; the reach table now keeps band-1 rows on band-2
  hexes; q band 1 reproduces the run of record exactly). Checks (`diagnostics/best_of_k_checks.py`): K = 1 flat,
  K = M top-1, one stage = the formula, Monte Carlo of the process, contention: pass. Claude's build choices (not
  user-approved): stages independent (a later stage may look again at an inner venue, not "minus those seen" as in
  (4): ~100x cheaper; the subject's share moves by a median of ~0.1%, at most 1.2%); one K per stage; ties within a
  cell split by each member's chance of being seen (exact for one ring; credits within a 0.02 cell approximate).
  Nesting (`diagnostics/band3_nesting.py`): 0% of band 1's and 0.28% of band 2's transit field lies outside the
  drive field. Band 3 not built: its stages need transit fields on ~68,700 drive hexes; the pass has ~9,800 origins
  (a free R5 run, ~20 h and ~40 GB at current settings; owed). Run time: staged band 1 ~110 s per slot (q ~6 s);
  bands 1-2 need a speed-up before the full run (next session).
  Speed-up (2026-10-26, 110th build; status): h(x, F) in a compiled, threaded loop (numba), the whole k grid in one
  pass over the looks, units in 4 worker processes; outputs equal the old code to 1e-14. Staged band 1 (0.5% target)
  ~1 h -> ~2 min; band 2 estimated 10-20 min. Staged runs donor hours only; all_open deferred (user: a known
  sensitivity, a later pass). Precision pilot (band 1, 0.5% vs 1% stop target): 1% takes 2.3x fewer draws, the
  band total moves -0.77%, within MC noise; every slot shares hours draw d, so slot errors move together and the
  report's MC error (slots summed as independent) is ~3x too small (0.12% reported vs ~0.4% at 0.5%; ~1% at 1%).
  Target: undecided (Claude: keep 0.5%). Detail: scoring.md Notes "Best-of-K" 110th line.
  Limitation (user, 110th): how diners' search effort grows with the catchment is unknown and untestable here; one
  universal k topped up per band is a stated convention (scoring.md Limitations).
  Band 3 routing (user, 2026-10-26, 111th; decided, not built): the 109th's owed band-3 question answered by routing,
  not a proxy: band-3 diners' transit fields by hybrid targeting from merged origins, heavy hexes (persons >= T) on
  their own route, lighter flower members from their persons-weighted centroid (`reachability.md` RCH-27). ~1.2-1.6
  h instead of ~22 h. Threshold T open; next: pilot of short (~11 min) searches for a finer 10-min stage (RCH-27).
  Band 3 built (2026-10-26, 112th, autonomous then at the desk; status): T 20 for band 1's field and 80 for band
  2's (user), the band-3 pass and table, staged band-3 units per slot (`reachability.md` RCH-27, `scoring.md` SCR-23
  Notes 112th). MC: target 0.5% (user); the report's band error now from per-draw band totals (user: yes). Speed:
  rows where the subject isn't entered are skipped (exact), smaller blocks, 2 workers: ~370 s per band-3 unit. Not
  run to the end: Mon-Thu units hit the 400-draw cap (~80 min each in band 3) because the stop check counts the
  weekday gap the 4-day draw cycle cancels; two runs halted (user). Next: a stratified stop check (~4 h for band 3),
  then the run, report and figures; a GPU port after (Claude's proposal). Band 1 vs q (110th staged run): 786 vs
  1,270 at 4.8; the slider a ramp (x11 over 3.5-5.0, q x560). (5) kept (user, 112th): a = 0; density-scaled search
  and an exposure-weighted encounter to future work.
  Speed-up review (2026-10-26, 113th discussion; user): every band-3 speed-up so far is accepted, including Claude's
  109th choice of independent stages (now user-approved) and RCH-27's 16-min band-1 searches and exact-route reuse;
  the stratified stop check is approved to build; the MC target stays 0.5% (112th); the parent-side hours-draw
  precompute is dropped. GPU port: a pilot before any build, since the gain is unknown: (A) a CPU phase profile of
  band-3 unit Fri_1730 over 8 draws (random draws, fields, count products, numba kernels, credit products); stop if
  the GPU-friendly phases are a small share; (B) a CuPy copy of the unit in a runner (same unit and draws; numpy's
  draws copied over vs drawn on the GPU): setup, per-draw and per-phase times, agreement with the CPU. Go only if one
  GPU process runs a unit in <= ~90 s (half the 2-worker CPU's ~185 s effective) and per-draw subject persons agree
  within 1e-4 relative (Claude's thresholds, to confirm); worth it only if band-3-sized runs recur (owed).
  GPU pilot (2026-10-26, 114th, autonomous; status; runner and logs in git-ignored
  `outputs/scoring/<subject>/staged_113th/`): (A) 87% of the CPU time of band-3 unit Fri_1730 is GPU-friendly (fields
  42%, random draws 17%, count / credit / contention products 27%), so B ran. (B) the best CuPy variant (uniforms
  drawn on the GPU, float32 `rings`) takes 1.84 s per draw vs the CPU's 11.55 s (6.3x); numpy's uniforms copied over
  give 1.9-3x. Same draws: per-draw subject persons and rows kept equal the CPU's in all 8 draws (denial gap ~1e-8,
  float32 sums); GPU draws: 8-draw mean 2,059 vs 2,068 (~0.3 SE). Misses the go rule: ~150 s per unit (~60 draws plus
  37 s levels build) vs ~90 s; still ~2.5x the 2-worker CPU (band 3 ~1.8 h vs ~4.2 h). Found: `np.diff(field,
  prepend=0)` in `staged_unit` promotes `rings` to float64 (GPU products ~20x slower; on the CPU a float32 zero alone
  is slower, mixed dtypes). Next options (Claude's, untested): the numba share kernels as a CuPy RawKernel (~1.4 s per
  draw still on the CPU); levels built ahead or reused across slots.
  GPU port decided (2026-10-26, 116th; user): port despite the missed go rule, since the project shifts and rescoring
  is likely (each rerun gains, not only band 3). Compare (`gpu_pilot_compare.py`, run 116th): same draws, credits and
  contention within ~1e-7 relative of the CPU, hex share sums and per-draw persons equal; GPU draws -0.33 SE. GPU runs
  use the GPU's own seeded uniforms (CuPy XORWOW, same seed list; repeatable on the GPU, comparable to CPU runs in mean
  only; Claude's recommendation, user OK); the CPU path stays as fallback and reference; backend in the output stamp.
  Plan (Claude's, user OK; steps in HANDOFF): array-module-agnostic share functions with a CuPy h kernel in float64;
  a GPU path in `staged_unit` behind a config switch; verify same-draw and GPU-draw; then levels built ahead.
  GPU port built; staged run of record (2026-10-26, 117th, autonomous; status): `share_staged` runs on NumPy or CuPy
  (h's numba loop has a CUDA twin, float64); `staged_unit` one loop for both (GPU: own seeded uniforms, float32 rings
  and credit / contention products, float64 shares); each unit's device fixed by band (`SCORING_BACKEND_BY_BAND`:
  bands 1-2 CPU, 3 GPU) so reruns repeat; the GPU process builds the next band-3 unit's levels on a CPU thread. The
  stratified stop check is built (Mon-Thu: within-day variance). Workers read their own transit rows (the parent held
  ~3 GB). Memory (16 GB, ~1 GB headroom, user): CPU pool then GPU (`SCORING_GPU_OVERLAP` False), 3 CPU workers.
  Checks (Claude's tolerances): CPU path identical to the old; same draws GPU vs CPU, one unit per band, persons
  rel <= 2.5e-15, credits / contention <= 7.6e-8; GPU draws z -0.01. Run: 76 min (bands 1-2 22 min CPU, band 3 53 min
  GPU vs ~4.2 h est. on 2 CPU workers), every band-3 unit MC <= 0.50%. Headline at 4.8, k 3.33 (persons per open
  slot): 786 / 1,443 / 2,360 (q 0.7: 1,270 / 960 / 1.0). Runners and logs in git-ignored `staged_117th/`; figures in
  `staged_112th/`. D1 diagnostic for GPU = CPU not made (user: fine for now).

## Future work

Studies outside the build, not planned: `future_work.md` (moved there 2026-10-22, user).

## Glossary

| Term | Meaning |
|---|---|
| `2tier` | The selected drive model: a fitted density factor on level-15 edges vs levels 0-14, plus β and ALPHA. "The M2 fitted model" in conversation (DRV D3) |
| ALPHA | Scale from routed graph time to Google time; fitted by the robust loss (median-centred before 2026-10-11) |
| β (beta) | Seconds charged per signalised head node: signal delay; when fitted it also absorbs junction friction at signals |
| M0 / `blind` | Convention speeds, no density treatment; the base the fit scales and the convention control |
| M2 (legacy) | The Oct 1 density variants `dense` and `dense_fringe`; `dense_fringe` at β 10 was the flagship frozen Oct 4, superseded by `2tier` |
| `osmtable` | Reference model using the OpenStreetMapSpeeds AU-VIC speed table |
| Density level / tier | Valhalla road-density level (0-15) per node; tiers rural / suburban / urban |
| Hex 0 | The subject's hex |
| Sound disc | Inner < ~7 km of the June scan, unaffected by the hole |
| Repair ring / outer ring | Sep re-fetches for 7–20 km and 20–100 km |
| Dataset one | The current venue dataset: June scan + Sep patch |
| fresh60 | 60-venue opening-hours check (50 API, 10 manual) |
| OD pair | Origin hex → destination venue, timed by the model and by Google |
| R̄ | Common radius used in the flat-accessibility counterfactual |
| Band 1 / 2 / 3 | 600 s walk+PT / 1200 s walk+PT / 20 min drive |
| Top N | Each hex's population split among the N winning venues in reach (all K equally when K <= N) |
| Contestable hex | A hex inside a venue's catchment for a band and slot, weighted by its reach probability (SCR-11) |
