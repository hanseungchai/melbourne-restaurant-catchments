# Drive calibration

**Purpose and scope.** How drive model parameters are fitted, how models are compared and chosen,
the guards and their definitions, the results (training half and test half), the rules for reading
residuals, and the earlier rounds they replaced. Not what a drive time is made of (`drive-model.md`),
nor how the pairs are drawn, fetched, joined and split (`od-sampling.md`, ODS-9 for the split).
**Stages.** `calibrate_pathing_agent` (`pathing_calibration.py`, `functions/drive_model_fit.py`,
`functions/routing_bundle.py`; cleaned): fits 2tier on the training half and on all pairs. The
selection round's code (routing runs, CV fits, β sweep, regression, Valhalla, comparison, test half)
is parked in `docs/parked_code/drive_model_selection.md`.
**Last reviewed.** 2026-10-13, 7083a8f
**Full context.** Compacted 2026-10-20. The full text, with how each position was reached, the earlier
rounds and the change log to 2026-10-20, is the snapshot
`docs/context_snapshot/2026-10-20_02-48-00Z/concepts/drive-calibration.md` ("snapshot" below). Every ID is
kept so citations resolve; where an entry is shortened, its detail is in the snapshot under the same ID.
This doc wins where the two differ.

## Current position
- **DCL-1.** Objective: classification at the 20-minute cut (`DRIVE_SCORE_CUT_S`) against Google's
  traffic-aware time is primary (Oct 4). Bias, drift and density guards protect against systematic
  error (20 min on a freeway ≠ 20 min in a dense centre), so long as they don't cost much
  classification. The reference is Google's view, not real-world travel (DRV limitations).
  Evidence: none (decision). DESIGN_pre_spine "Settled in chat" (Oct 4); `M2_decision_rules` L6-7.
- **DCL-2.** Design: every fit and every choice happens inside the training half (3,999 pairs) by 5
  grouped CV folds (ODS-9), scored on out-of-fold predictions only. The test half (4,001) is opened
  once, after the choice; `evaluate_test_half` refuses to run if a result exists. Intervals: paired
  bootstrap resampling destination hexes, 2,000 resamples, seed 20261011.
  Evidence: code; DESIGN_pre_spine "Train / test scheme" (Q2 closed).
- **DCL-3.** Fit (fitted density models): route the training pairs; record each route's raw time per
  scaled tier and its signal count; fit ALPHA, the tier multipliers and β jointly (on a fixed route,
  time is linear in them); reroute with the fitted values; repeat until under 0.5% of routes change
  and every parameter moves under 0.5% (cap 15 rounds). Loss: soft_l1 on log(predicted / Google),
  scale 0.1. β is free; a fixed-β sweep (0-24 s, grid set before any fit) runs alongside as a check,
  since β changes the routes and the fixed point need not be the loss minimum (dry run: agreed, β ≈ 17).
  Log-ratio loss: the conventional choice for a multiplicative error (user, 2026-10-13).
  Evidence: code (`fit_drive_model`, `_fit_params`); config "Drive model fit"; DESIGN_pre_spine "Drive model selection" item 1.
- **DCL-4.** Structures, nested on Valhalla's tiers plus the top level: 2tier (15 / 0-14), 3tier
  (15 / 11-14 / 0-10), 4tier (15 / 11-14 / 6-10 / 0-5). Rule: the simplest structure that passes the
  guards wins unless a more complex one beats it on out-of-fold loss **and** accuracy, each paired CI
  excluding 0. Result (2026-10-11): 3tier and 4tier beat 2tier on loss (CIs −0.00026 to −0.00008 and
  −0.00031 to −0.00011) but not on accuracy (CIs −0.0025 to +0.0041, −0.0023 to +0.0041), so **2tier**.
  Out-of-fold accuracy 0.9255 / 0.9262 / 0.9265; blind β 2 0.8997.
  Evidence: `diagnostics/drive_model_selection.py`; `output_backup/drive_model_selection_20261012_backup/<subject>/20261011/all/scores.csv`; DESIGN_pre_spine "Drive model selection" item 1.
- **DCL-5.** Edges a factor acts on: every edge in the tier, motorways included (`DRIVE_FIT_EDGE_SET =
  "all"`, user 2026-10-12). Sets C (all but motorway) and D (all) tie in CV; the pre-set fallback picks
  D (one rule for every road). Cost of the choice at the cut: 23 of 3,999 pairs classed differently,
  split 11 / 12. Reopen if a later check finds a motorway bias at the cut under D, if D fails a guard
  that C would pass, or for a wider band or a peripheral subject. Full record: DESIGN_pre_spine "Drive model
  selection" item 1; DESIGN Q16.
  Evidence: `diagnostics/drive_untagged_share.py`, `drive_fit_edge_set.py`, `drive_motorway_absorption.py`.
- **DCL-6.** Final comparison (out-of-fold, training half): the fitted winner (2tier), Google regression
  (DCL-10) and two controls with only ALPHA fitted: blind at β = 2 (convention) and Valhalla
  density-aware out of the box (its density-unaware "defaults" variant is not carried). Controls are conventions: blind the
  OSM baseline, Valhalla open-source routing; the regression is a second fitted model for testing.
  The legacy references (`dense`, `dense_fringe`, `osmtable`) are not controls, so they are routed
  but not scored here (user, 2026-10-13; DRV D5).
  Evidence: code (`compare_drive_models`); DESIGN_pre_spine "Drive model selection" item 2; `diagnostics/valhalla_vs_google_drive.py`.
- **DCL-7.** Guards, all out-of-fold:
  - Bias at the cut: median % error on pairs with Google time 15-25 min within ±5%.
  - Drift: slope of log(predicted / Google) on log2(Google time), Google 10-30 min; non-inferior to
    blind β 2: upper 95% CI of |model slope| − |blind slope| below +3% per doubling. Replaces the rho
    test (a correlation, not a size; covers trips that can't change a 20-min class; every model failed it).
  - Density share: log error regressed on the route's length share per tier (from Google's polyline
    over the raster, so the same for every model) plus log Google time; each tier's effect against the
    length-weighted average of all tiers: point within ±5%, 95% CI within ±10%.
  Evidence: code (`_score_metrics`, `score_drive_models`); config "Scoring"; DESIGN_pre_spine "Drive model selection" item 3.
- **DCL-8.** Training-half result (2026-10-12): accuracy 2tier 0.9255, Google regression 0.9220 (gap CI
  −0.0095 to +0.0026), blind 0.8997; Valhalla on every training pair 0.9040 (gap to 2tier −2.9 to
  −1.4 pp), bias +7.0% (fails). Density share: 2tier fails only rural (+8.3%, CI +4.1 to +12.0%); the
  regression fails only level 15 (−10.2%); blind fails three tiers; Valhalla fails 11-14 (+13%) and 15
  (−32%). No model passes every guard. **Selected (user, 2026-10-12): 2tier to the test half**: top
  accuracy, and its failing tier (rural) carries far fewer trips than the regression's (level 15).
  Evidence: `diagnostics/drive_model_selection.py`; `output_backup/drive_model_selection_20261012_backup/<subject>/20261012/compare/compare_scores.csv`, `compare_density_guard.csv`; DESIGN_pre_spine "Drive model selection" item 4.
- **DCL-9.** Test half (pre-registered 2026-10-12 before reading; opened once, 4,001 pairs). At SCR-10's
  cut (1,229 s; bias and drift windows +29 s; rescored 2026-10-18, user; a re-read, not a second opening;
  no refit): 2tier 0.9188 (regression 0.9150, Valhalla 0.8980, blind 0.8955), bias +3.9%; DCL-4 still
  picks 2tier; no guard flips. At the opening (1,200 s): 2tier 0.9233 (CI 0.9148-0.9313), bias +3.8%,
  drift −1.0% per doubling (passes); density share passes 6-10, 11-14, 15 (±2%), fails rural +13.8%
  (CI +10.5 to +17.3%; per draw +10% / +17%). User's prediction (out-of-fold inside the test CI, ranking
  holds): holds for accuracy, bias and loss; drift misses for 2tier, regression and Valhalla (every slope
  down 2.4-3.6 points, read as a property of the test pairs). The user reads the halves as agreeing.
  Evidence: `diagnostics/drive_model_selection.py`, `diagnostics/drive_rescore_scr10.py`;
  `output_backup/drive_model_selection_20261012_backup/<subject>/20261012/test/test_scores.csv`, `test_density_guard.csv`.
- **DCL-10.** Google regression (contender, not selected): Google's polyline matched to the drive graph
  (10 m, heading within 45°, Q14), length per road class × density level; log pace = class term +
  class × tier and class × level deviations, ridge-shrunk (penalty by inner CV per outer fold, no
  routing); classes: Valhalla's eight (links with their parent) plus motorway ramps. Unmatched length
  goes to a dummy pace per tier, never used for prediction; it absorbs trip-end overhead, so it overlaps
  a per-trip intercept: never fit both. β on matched signals; no ALPHA. Predictions route on our graph
  with the fitted table. Level-15 under-prediction (−12%) = −9% routing (its routes are cheaper under its
  own table than Google's path) and −4% paces.
  Evidence: code (`fit_google_regression`); `diagnostics/google_polyline_match.py`,
  `diagnostics/drive_regression_route_gap.py`.
- **DCL-11.** Reading residuals: error = (predicted − Google) / Google, so negative means the model is
  too fast. Don't bin residuals by Google duration to look for bias: Google is in the denominator and
  defines the bin, which manufactures a monotone gradient; duration bins are fine for accuracy and FP/FN. Distance
  (haversine) was the exogenous axis for tilt; the guards stay on Google's time (DCL-14).
  Evidence: rev4 L587-593, L674-676; `tilt_rederivation_Sep_21` L167-187 (backup `residuals_by_duration.csv`).
- **DCL-12.** Pre-registration practice: pass rules and predictions are written before results are
  read; any change after is stated as a deviation in the write-up, with its reason. Stated deviations
  in the current round: the guards were set knowing the legacy flagship fails the rho test; the
  density-share reference changed post hoc from rural to the average (rural result kept on record);
  the regression's penalty grid was extended below 0.3 after the first fold's inner CV chose the edge
  (before any out-of-fold score); the drift reading of the test half was made after the fact.
  Evidence: none (practice). DESIGN_pre_spine "Drive model selection" items 3-4.

- **DCL-13.** Production fit: 2tier refitted on all pairs, training and test halves (8,000), after the
  test half was opened; the reachability pass routes with these parameters. The test score (DCL-9)
  describes the training-half fit, not this one: same structure, more data, no held-out score.
  The train/test split file stays as the record. User, 2026-10-13. Built 2026-10-13: ALPHA 1.19929, m 1.39381, β 16.179 s, 4 rounds, converged
  (`fit/model/<subject>/2tier_all_pairs_params.json`).
  Evidence: none (decision).
- **DCL-14.** Guards are read against Google's time on purpose: Google is the reference, and the
  error a trip carries at its real (Google) time is what decides misclassification at the cut.
  Sorting pairs by the target tilts drift negative for any imperfect model (a time-blind model
  can't follow the trip-to-trip spread in Google's times), so a drift slope is read only relative to
  blind, never as the model's absolute drift. The test half's shared −2.4 to −3.6 point drift shift
  (DCL-9) fits this reading. Not re-scored on distance or blind time (K1 closed). User, 2026-10-13.
  Evidence: none (decision).
- **DCL-15.** Rolling test (planned with ODS-11, not built): after a top-up, the newest fetch is the
  test set, opened once; fits and choices use the training set (all earlier pairs) by grouped CV
  folds, redrawn to include the new pairs, so the selection round's out-of-fold scores (DCL-8) stay
  as a record but won't reproduce. Grouped CV carries the unseen-hex check; the rolling test asks
  how the model does on new pairs at a later date. Scoring an earlier fit on a newer test measures
  model error and drift in Google's times together, and is reported as such. DCL-2 and DCL-13 hold
  until the first top-up.
  Evidence: none (decision, user 2026-10-13).
## Not adopted
- Successive halving of entrants: saves ~1 h, makes early cuts on noisy 1,000-pair scores. DESIGN_pre_spine "Drive model selection".
- A rural top-up draw (500 Routes calls aimed at rural pairs) after the rural failure: adding data after seeing a failure, to fix it, is data massaging; a rural-weighted draw is sound only if designed before results. DESIGN_pre_spine "Drive model selection" item 4 (user, 2026-10-12).
- The rho test (|rho| or its CI within a band) as a guard: replaced by drift (DCL-7). Also rejected earlier: "CI includes zero" distance tests (thin cells pass by noise, so a noisier model wins) and a ±3% level margin (±5% kept). `M2_decision_rules` L12-16.
- MedAPE-optimal ALPHA (replaced by median-centred, then by the robust fit). `session_findings_Sep_17` L124-126.
- β chosen by route length (median len/G closest to 1; Sep 22): ill-conditioned (len/G 0.997-1.002 for β 0-12; β 6 beat β 10 in the fourth decimal). `drive_calibration_s4_Sep_22` L79-82.
- Regressing Google time on M2 per-tier time (Oct 8): dropped then to keep M2 residuals closed; superseded by the fitted round. `detour_junctions_google_density_Oct_8` L107-108.
- A manual 10-15 pair Google check to set the density range (Sep 29): replaced by the fitted round. `road_density_speed_Sep_29` L112.

## Limitations
- 2tier over-predicts rural roads: +8.3% against the average route out of fold, +13.8% on the test half (the figure to quote); pairs at least half rural are 40 of 1,228 near the cut (3%), so a few rural venues read slightly out of reach. Peripheral or rural subjects inherit it. DESIGN_pre_spine "Drive model selection" item 4.
- Departure-time noise (a time-blind model fitted to departure-specific Google times) widens every CI and sets a floor no time-blind model can beat; not measured (Q10 parked idea). `departure_noise_floor_Oct_4`.
- Every figure is agreement with Google, and Google's spread is unmeasured (DRV limitations).
- Fold 3 of the 2tier CV stopped at the round cap unconverged (DRV-1); accepted (K3).
- The production fit on all pairs (DCL-13) has no held-out score; 0.9233 is the training-half fit's.

## Notes
- Earlier rounds (Sep 19 to Oct 4, 537-540 pairs; M0 / M1 / M2, the flagship M2 dense_fringe β 10
  adopted on judgement): superseded 2026-10-11 by the fitted round, figures not to be cited as current.
  Detail and sources: snapshot, Notes. The Sep 22 §4 code is parked in
  `docs/parked_code/drive_model_evaluation_s4.md` (not the Oct 4 code, which is not in the repo).
- Old docs citing "DESIGN.md Q2" for keeping M2 residuals closed: moot (snapshot, Notes).
- Drive-model error enters the reachability pass by simulation from the test-half residuals by tier
  (`reachability.md`; DESIGN_pre_spine "Settled in chat").

## Open questions
- DESIGN.md Q10 (departure noise floor, parked), Q15, Q16, Q17, Q20 (top-up scheme details).
- **K1.** Closed 2026-10-13: drift is not re-scored on another axis (DCL-14); it would change no output.
- **K2.** Closed 2026-10-16 (user): dropped as obsolete (would score the superseded flagship).
- **K3.** Closed 2026-10-13: fold 3's unconverged CV fit accepted (parameters match the other folds).

## Changes
- Changes to 2026-10-20 (DCL-1 to DCL-15, K1-K3): snapshot, "Changes".
- 2026-10-20 · compacted: history, earlier rounds and intermediate figures moved to the snapshot; DCL-9, DCL-10 shortened; IDs kept (no position changed)
