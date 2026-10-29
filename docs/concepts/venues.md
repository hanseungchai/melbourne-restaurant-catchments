# Venues

**Purpose and scope.** The venue layer: how the venue table was collected and merged ("dataset one"),
its counts, dates, tags and competitor definition, the planned fresh fetch track, and opening hours
(pulls, histogram, per-venue hours). Not venue → hex assignment (`hexes.md` HEX-6), API budgets and
the ledger (`api-cost.md`), departure draws that use the hours (`od-sampling.md` ODS-5), nor how
venues are ranked (`scoring.md`).
**Stages.** `rebuild_legacy_datasets` (`legacy_datasets.py`), `fetch_enterprise_hours` and
`build_opening_hours` (`places_details.py`, `opening_hours.py`); config groups "Legacy datasets",
"Enterprise hours fetch", "Opening hours".
**Last reviewed.** 2026-10-13, 71808ec
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/venues.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **VEN-1.** Dataset one = three Legacy Nearby collections around the legacy scan centre (the default
  subject; fixed, never follows the chosen subject): the 2026-06-29 recursive hex scan (inner disc
  plus its 20 km extension), the 2026-09-25 repair ring (7–20 km) and outer ring (20–100 km); plus a
  2026-07-04 Places (New) Details pull for the June venues' type tags and addresses. Rebuilt from
  frozen inputs, no API. The patch history lives only in this legacy track.
  Evidence: code (`rebuild_legacy_datasets`). `verification_merge_Sep_25`; DESIGN_pre_spine "Cleanup intent".
- **VEN-2.** The June scan has a hole: every saturated 800 m hex at ~7.5–20 km was dropped, the rest
  collected normally (exact zeros, e.g. St Kilda 0 → 47, Balaclava 0 → 40 after repair). The disc
  under 7 km (`SOUND_DISC_RADIUS_M`) is sound and kept; the repair re-fetched the whole 7–20 km ring.
  Evidence: `hole_probe_Sep_24` §1 (`hole_diagnostic()`, legacy code); smoke test 5 (46 of 60 new,
  `frozen_inputs/legacy_evidence/test5_saturation.json`). No diagnostic in `diagnostics/` (D1 gap).
- **VEN-3.** Merge rules (`build_venues_20260925_expanded`): OPERATIONAL results only (scan and ring
  runs); newest record per `place_id`; at or beyond 7 km the ring venues replace the June scan's, inside
  7 km the June scan (`run_id` `old_legacy`) stands; the 3 hand-confirmed duplicates
  (`MANUAL_DUPLICATE_PLACE_IDS`) dropped; no other de-duplication; missing rating, price level and phone
  are NaN, never −1. The table is not cut at 100 km (the hex stage drops off-grid venues, HEX-6).
  Evidence: code. `verification_merge_Sep_25` §5–6; DESIGN_pre_spine "Venue cleaning" (user, 2026-10-06).
- **VEN-4.** Counts (output check 2026-10-13): 19,030 venues, `place_id` unique (outer 8,889, repair
  5,650, old_legacy 4,491); 18,498 within 100 km of the scan centre, 532 beyond; 18,213 rated, 817
  unrated. Same ID set as the legacy `data/expanded_place_api.csv`. Older figures (19,029 / 18,497 /
  530) are a Sep 27 count error that matches no file (snapshot).
  Evidence: output check 2026-10-13 on `venues_20260925_expanded.csv`; no saved diagnostic.
- **VEN-5.** Snapshot dates: inside 7 km, 2026-06-29 (`collection_timestamp`); 7–100 km, 2026-09-24/25.
  No refresh: venues are assumed in steady state over the gap, stated as a limitation.
  Evidence: the legacy JSON timestamp (`verification_merge_Sep_25` §4, replaces "~Mar 2026");
  `snapshot_dates_Sep_25`. The steady-state test (V3) was never run.
- **VEN-6.** Ring fetches verified: repair 821 circles / 1,081 pages / 9 saturated; outer 1,073 /
  1,460 / 18; ledger reconciles (2,541 + 10 smoke-test pages = 2,551); 27 of 27 saturated circles hold
  60 results and none unflagged does; no planned circle missing; 26 missing children all wholly
  beyond 100 km. An empty circle can't be a silent failure (requests return only on OK / ZERO_RESULTS).
  Evidence: `verify_and_outer_run_Sep_25`, `verification_merge_Sep_25` §8 (legacy `manual_diagnostic.py`).
- **VEN-7.** The competitor set is what Legacy Nearby returns for `type=restaurant`: Google's tag, not
  what businesses are (FRM-8). Readers may exclude tags from their own competitors' tag pool, chosen
  before results and without weights; tags are labelled ("mixed-use: check"), never recommended for
  exclusion (DESIGN Q17, user 2026-10-12).
  Evidence: `diagnostics/tag_primary_type.py` (pool 95% food-primary; only gas_station, atm, finance mixed-use).
- **VEN-8.** Two type vocabularies in one table. Every row has tags, but old_legacy rows carry
  Places (New) Details types (252 distinct, ~6 a row, incl. cuisines and `coffee_shop`,
  `fast_food_restaurant`) and addresses, while ring rows carry Legacy Nearby types (59 distinct, ~5 a
  row; no cuisines, `coffee_shop` and `fast_food_restaurant` 0%) and no `formattedAddress`. Coarse
  tags shared by both (`restaurant`, `cafe`, `bar`, `meal_takeaway`, `bakery`) are safe to use; a
  fine-grained tag would filter the inner 7 km and silently miss the ring. An Essentials Details pull
  must put the ring on the new vocabulary before any use of fine types or addresses (DESIGN Q9, not
  built); hours imputation does not need it (coarse tags 2.57 vs 2.51 pp).
  Evidence: output check 2026-10-13 on `venues_20260925_expanded.csv` (no saved diagnostic);
  `diagnostics/venue_hours_imputation.py`.
- **VEN-9.** Fresh fetch track (planned, not built; decided 2026-10-06): probe (free Text Search
  IDs-only, five passes) → calibrate k → pack hex circles (k_cost × expected ≤ 50) → Legacy Nearby with
  recursion → save raw with provenance. Probe: a quadtree of square cells splits where a pass returns
  ≥ 50 or the union exceeds 20, down to a 25 m floor. Calibrate: k50 (`k_cost`) and k99 with a bootstrap
  95% CI against the rebuilt table as oracle, else a stored k recalibrated after every paid fetch (median
  per-cell distinct Nearby ÷ probe union); k = 1.13 by convention, steering cost only (recursion
  guarantees coverage). Save: per-request and per-run provenance records; output is a new dated
  dataset, frozen afterwards, never merged with legacy data (the first fixed collection is a new baseline).
  Evidence: DESIGN_pre_spine "Cleanup intent" (Chao2 pilot 2026-10-06).
- **VEN-10.** Probe properties: ≤ 60 IDs per query, nondeterministic (6.5% of venues flip between
  identical runs); single query `restaurant` recall 65%, five passes 85.1%; strict and loose type
  filtering equal; undercount k50 1.13, k90 1.47, k99 2.20 (246 cells), the tail from food hubs; it
  never over-counts. Recall does not depend on box size.
  Evidence: `venue_scan_findings_Sep_23` §2 (`frozen_inputs/legacy_evidence/probe_compare/`); `packing_Sep_24` (97-parent test). DESIGN Q8 (k drift).
- **VEN-11.** Opening hours histogram: weekday open share per 30-min slot from the pull named by
  `OPENING_HOURS_PULL_DATE` (20261010: uniform draw of 900, seed 20261010, plus the 2 [subject] venues
  fetched outside the draw and left out; 845 usable). Rules: `regularOpeningHours` only; open iff
  open ≤ t < close; past-midnight closes spill into the next day; 24 h venues open every slot;
  counted if OPERATIONAL with flag ok or 24h; day 0 = Sunday. A 404 is permanent (not-found list).
  Evidence: `opening_hours_20261010_meta.json`; `hours_check_Sep_30` (rules).
- **VEN-12.** The hours hold over time: the fresh60 check (60 venues: 50 by API, 10 by hand; 2026-09-30) AGREES with the
  2026-09-02 histogram at 12:00, 19:00, 22:00 and the median close; the 2026-10-10 pull agrees with the
  2026-09-02 one within 95% intervals and shows no hours churn in the 43 shared venues. The replacement
  doesn't invalidate outputs built from the old histogram. Pooling the two pulls: rejected (below).
  Evidence: `diagnostics/hours_check_fresh60.py`, `diagnostics/enterprise_hours_old_vs_new.py`.
- **VEN-13.** Per-venue hours (Q17 factor): the venue's own Enterprise hours where pulled (2026-10-10,
  else 2026-09-02), otherwise imputed from tags by backoff: most specific tag combination confident at
  that hour (vs random venue groups of the same size), else smaller subsets, else the overall average;
  tags never averaged. Beats no factor, modestly (MAE 2.51 vs 2.80 pp; 75% of venue-hours back off to
  the generic bucket).
  Revised for scoring (user, 2026-10-23, 90th): at 30-min slots x day types (SCR-13) open shares are near 0 or 1,
  so spread = p(1 - p) is set by the mean and the confidence test trusts extreme groups, not different ones (cafes
  0.32 open at Fri 19:30, imputed 0.73). Replaced by partial pooling along a greedy tag chain (the venue's most
  carried tag, then the tag keeping the most, ...; each step (n mean + M parent) / (n + M), M = 5): leave-one-out
  Brier at the subject's slots 0.168 vs spread 0.185, a mean test 0.170, pooled 0.204, all open 0.314. Tags help
  at weekday dinner, hardly at weekend lunch. Venues a pull found closed are imputed (snapshot, VEN-14). Built:
  `functions/hours_imputation.py`, `scoring.build_venue_open_shares`. The drive-factor validation above stands.
  Evidence: `diagnostics/venue_hours_imputation.py`; side note `2026-10-05_side-note_hours-imputation`;
  slots: `diagnostics/venue_hours_slot_imputation.py`.
- **VEN-14.** Closed venues stay in the table: no refresh removes them. The hours pulls found 23 of
  900 closed on 2026-09-02 (15 permanently) and 11 of 899 on 2026-10-10 (7 permanently), plus one 404
  ("Creative Galleries", outer ring, tagged restaurant). Kept (V1).
  Evidence: output check 2026-10-13 (`opening_hours_*_venue_log.csv`, not-found list).
- **VEN-15.** Data refreshes (planned with ODS-11, not built; after outputs). Hours: a new pull is a
  new random sample from the current venue table, made before a drive top-up draws its departures,
  plus a fixed panel of earlier-pulled venues to measure drift, as the [subject] venues are now (chance
  overlap is small: 43 venues between the 2026-09-02 and 2026-10-10 pulls, VEN-12). Venues: "update"
  means a VEN-9 fresh fetch replacing the legacy table as the new baseline (no merge). Existing drive
  pairs stay valid training data (a venue only supplies a destination point); the change shows in hex
  venue counts, later draws' destination pool and the outputs. Code today reads one hours pull
  (`OPENING_HOURS_PULL_DATE`) and reuses an existing draw, never extends it. Pulls are never targeted
  (user and Claude, 2026-10-23, 89th): each draws uniformly from venues never pulled, the [subject] venues
  fixed; no pull of a subject's near competitors (pulled vs imputed precision would track distance to the
  subject, and the imputation's training set would lean to one area). Next: one 1,000-call pull after
  the November allowance resets (~8.5% of venues pulled now, ~14% after).
  Evidence: none (decisions, user 2026-10-13, 2026-10-23).

## Not adopted
- Text Search as a competition layer (restaurant-qualified or niche-tag queries): "who competes" stays fuzzy and query wording is arbitrary; ranked order defining membership is circular. DESIGN Q10; `ideas_textsearch_relevance_Sep_24`.
- Probe to per-venue isolation (~50 m cells): hundreds of thousands of calls, and rebuilds the paid location field from a free SKU. `TEMP_workplan_Sep_23` L148-153.
- Circle `locationBias` or Nearby (New) as the probe: rectangle restriction only; Nearby (New) is Pro, 20 results, no paging. `TEMP_workplan_Sep_23` L45-52.
- Capture–recapture (Chao2) for probe totals: −7.7% median error vs union × 1.13 +1.7%; the misses are structural. DESIGN_pre_spine "Cleanup intent".
- Packing target from k99 (27 per cell), and "drop empty children": replaced by the expected-count fit and full coverage. `venue_scan_findings_Sep_23` §3.
- Flat +10 m search-radius buffer: nearly doubles the area at 25 m (user). `legacy_smoke_tests_Sep_24`.
- `make_outer_plan` inside the pipeline: would overwrite the gated plan; plans are built and gated by hand. `verify_and_outer_run_Sep_25`.
- Outer ring fetched in October: budget; fetched in September. `verify_and_outer_run_Sep_25`.
- Duplicate detection by distance, types, phone or scoring: food courts share phones, chains share call centres. `verification_merge_Sep_25` §7.
- −1 sentinels for missing values: contaminate the rating distributions. `verification_merge_Sep_25` §6.
- Hours: `regularSecondaryOpeningHours` (biases closes early); `weekdayDescriptions` for day indexing (Monday first); medians from rounded values. `hours_check_Sep_30`.
- Pooling the 2026-09-02 and 2026-10-10 hours pulls: the old sample under-covers the outer ring (40 of 8,889) and would need weights. DESIGN_pre_spine "Opening hours".
- Hours imputation: Popular Times demand weights (circular: peaks are partly the competition measured); tag blending or precision weighting; TF-IDF tag selection; a hand-picked variance threshold; neural or embedding models. Side note L23-27.

## Limitations
- Date split: June inside 7 km, September outside; ratings and openings drift across the seam
  (sound-disc churn ~3.3% new IDs over ~3 months; ~2.5% of old ring venues gone). Dated, venue-specific
  claims need a roster from that date. `snapshot_dates_Sep_25`; `verification_merge_Sep_25` §4-5.
- Empty circles may be real recall misses for `type=restaurant` (suburban, e.g. near Highett; 109 repair
  and 204 outer circles empty). Unmeasured. `verify_and_outer_run_Sep_25` L157-161.
- Stale duplicate listings are removed only where known (3). `verification_merge_Sep_25` §7.
- Hours are Google's listed, owner-entered hours (advertised competition), may lag reality, and every
  open hour weighs the same. Side note L20, L30; `hours_check_Sep_30` L116-117.
- The outer ring spends pages beyond any reachability envelope; that data may go unused. `verify_and_outer_run_Sep_25` L74-76.

## Notes
- The hole's mechanism is an inference: the child lattices probably covered only ~8.5 km when the June
  update ran and were regenerated to 20 km later (`0_cent_rad_800.txt` missing). The effect is
  confirmed by data. `venue_scan_findings_Sep_23` L65-77. (Sep 23)
- Food hubs (inside buildings: MCG, shopping centres, CBD towers) drive the probe's undercount tail;
  predictable from OSM shopping-centre and stadium polygons. (Sep 23)
- Ring saturation came in below the Monte Carlo forecast (9 vs ~19.5; 18 vs 22.1); k = 1.13 was measured
  on the dense sound disc. Musing, untested. DESIGN Q8. (Sep 25)
- Text Search ledger gap (16,849 vs 20,768 requests) unexplained. `hours_check_Sep_30` L138.
- Six centroid files in `pre_processing/` (~40 MB) were committed as provenance of the June search
  circles (Oct 2); removed from git in a3cf307, and the empty folder deleted by the user (2026-10-20). They
  survive in git history.
- [subject] Melbourne Central's ratings changed since the June scan; a manual dated override was planned. (Sep 25)
- Seasonality musing: lean seasons may close between services; composition is the rival explanation.
  Clean test: re-fetch a panel of 100–200 of the old 900. `hours_check_Sep_30` L114-119. (Sep 30)
- Creative Galleries (VEN-14's 404): place ID retired from Google, not marked closed; cause unknown;
  still among the 19,030. (user, 2026-10-13)
- Further dated notes (the old 900-sample's universe, Sep 30): snapshot, Notes.
- Planned after cleanup: monthly `update_venues` on the free allowance for a year of temporal data
  (survival analysis of rating and review velocity against closures; closures are noisy). Parked:
  staleness-based refresh of whole regions (~3 months), which needs users. DESIGN_pre_spine "Planned after cleanup".

## Open questions
- DESIGN.md Q8 (k drift), Q9 (enrichment), Q10 (parked ideas), Q17 (per-venue hours), Q20 (top-up scheme details).
- **V1.** Settled (user, 2026-10-13): keep closed venues (VEN-14); dropping them by judgement would make
  the snapshot unrepresentative.
- **V2.** Closed (user, 2026-10-13) with DESIGN Q4: the legacy 50 m snap filter is HEX-6's rule; inside
  the grid no venue is dropped.
- **V3.** Steady-state test (rating and review-count distributions, sound disc vs ring inner edge
  ~7–9 km; free) never run; the hours-pull overlap shows hours stability only. **To test** (user,
  2026-10-13: the design needs to be stable): build it as a diagnostic (free).

## Changes
- Changes to 2026-10-20 (VEN-1 to VEN-15): snapshot, "Changes".
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
- 2026-10-23 · VEN-13 revised for scoring slots (90th, user): partial pooling along a tag chain (M = 5) replaces the spread test there; closed venues imputed (snapshot)
