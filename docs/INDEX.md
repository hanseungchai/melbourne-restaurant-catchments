# Docs index

Read this first; open a doc only when it is listed for the task at hand. Prefer searching a
doc for a term, or reading one section by line range, over reading it whole.

- `DESIGN.md`: the spine. Per stage, the current decision in a line or two, pointers and status;
  open questions Q1-Q23. Start here for design work.
- `concepts/`: one doc per concept, holding the current positions with stable IDs and evidence
  pointers (template: `doc_template.md`). Registered ID prefixes, never reused:
  FRM `framing.md` · SCR `scoring.md` · CEN `census.md` · HEX `hexes.md` · VEN `venues.md` ·
  GRF `graph.md` · DEN `density.md` · DRV `drive-model.md` · DCL `drive-calibration.md` ·
  ODS `od-sampling.md` · WLK `walk.md` · TRN `transit.md` · RCH `reachability.md` · API `api-cost.md` ·
  OUT `outreach.md`.
- `future_work.md`: studies outside PLATICA's scope, not planned (accessibility, policy, other populations,
  brand vs reputation). Open only when a task points there.
- `literature.md`: every outside source cited, with where it's used and how far it's checked (user, 2026-10-25).
  Add an entry whenever a source is cited.
- `DEPRECATED.md`: one row per removed item. `HANDOFF.md`: session handoff only, not a design record.
- `incoming_doc/`: inbox of idea notes from outside this repo or casual sessions, one per file
  (`YYYYMMDD_<topic>.md`). Proposals, never current design; absorbed notes move to
  `stale_project_mds/incoming_absorbed/` (CLAUDE.md W6, W7).
- `presentation/`: the decks, one subfolder per audience (`business/`, `analyst/`, `research/`); figures and
  tables they use live in the root `images/` (its README lists each file's source). `pilot/assets.md`: the pilot
  deck's asset checklist (made, stock, checks), with status. Order by audience: FRM-26;
  limitations before results: FRM-18.
- `parked_code/`: working code not in use, one file per block, copied verbatim with pointers
  (README.md there). Filled in reorg step 8.
- `legacy_archive.md`: where `data/` and `backup/` went (moved out 2026-10-16, external drive),
  with `legacy_archive_manifest.csv` listing every file. Open it when a `legacy:` path or an old
  evidence pointer names `data/` or `backup/`.
- `context_snapshot/`: dated full copies of `docs/` taken before a compaction, one subfolder per
  snapshot (UTC time), mirroring `docs/`. Correct as of their date, not stale; the live doc wins.
  Open one only when a live doc points to it (CLAUDE.md W2, F1). Snapshots: `2026-10-20_02-48-00Z/`
  (before compacting `concepts/transit.md` and DESIGN.md Q18, Q22, Q23); `2026-10-21_03-25-00Z/transit.md` (user, 2026-10-22,
  before the second transit.md compaction; transit.md only, at the folder's top level).
- `stale_project_mds/`: the archive. Never treat as current (CLAUDE.md W2); open it when a concept
  doc's evidence pointer sends you there. See "Archive finder" below.
- **`DESIGN_pre_spine "<section>"`** in any doc or code comment means that section of
  `stale_project_mds/DESIGN_pre_spine_20261013.md`, DESIGN.md as it stood before the spine rewrite
  (reorg step 5). Refs written before 2026-10-13 that say just "DESIGN.md" mean that copy too.
- **Code vs doc:** the code shows what is; a doc shows what was intended. Report conflicts.

## Lookup by pipeline stage

Stage names are the switches in `main.py`, in pipeline order.

| Stage | Concept docs |
|---|---|
| Whole project | `framing.md` (FRM) · `api-cost.md` (API, every paid stage) · `outreach.md` (OUT, delivery; parked) |
| `rebuild_legacy_datasets`, `fetch_enterprise_hours`, `build_opening_hours` | `venues.md` (VEN) |
| `pre_process_census` | `census.md` (CEN) · `inputs/README.md` (census update folders and file names; not tracked) |
| `construct_hex_tiles` | `hexes.md` (HEX) · `census.md` (residents and workers layers) |
| `map_construction` | `graph.md` (GRF) · `density.md` (DEN, road density) · `walk.md` (WLK, walk graph) |
| `construct_graph` | `graph.md` (GRF) |
| `build_speed_graphs` | `drive-model.md` (DRV) · `density.md` |
| `sample_drive_pairs` | `od-sampling.md` (ODS) |
| `calibrate_pathing_agent` | `drive-calibration.md` (DCL) · `drive-model.md` (DRV, routing) |
| `construct_pt_graph` | `transit.md` (TRN) |
| `sample_transit_pairs` | `transit.md` (TRN-7, TRN-10, TRN-15, T3-T6) |
| `transit_fetch` | `transit.md` (TRN-8, TRN-11, T7) |
| `transit_collection.py` (later transit sets by set and step, run directly; not a `main.py` stage) | `transit.md` (TRN-10, TRN-14, TRN-15) |
| Reachability pass (`reachability.py`; main.py block `run_reachability`) | `reachability.md` (RCH), `scoring.md` (SCR, downstream) |
| Scoring (`scoring.py`, report `scoring_report.py`; main.py block `run_scoring`) | `scoring.md` (SCR) |
| Cleanup process | root `CLAUDE.md` (in force) |

## Archive finder

Everything below is history, kept so evidence pointers can be followed. Session docs are in
`stale_project_mds/session_docs_to_20261013/` (the "active" docs until reorg step 6, 2026-10-13);
the step 3 read-through summaries, one per doc, are in `stale_project_mds/reorg_readthrough_20261013/`.
Older docs sit directly in `stale_project_mds/`. Two files share the name
`PLATICA_current_state_rev4.md`: the one in `session_docs_to_20261013/` (2,189 lines, mapped
below) is the later, longer one.

Kinds: **decision** (settles a position) · **delta** (dated session record: findings, code
changes, to-dos) · **handover** (agenda for the next session) · **idea** (parked, not adopted)
· **workplan** (temporary plan, meant to be folded into a delta) · **check** (one measured
question, with a verdict) · **process** (how the project is run).

### Session docs by stage

Newest docs last. Stage names as of 2026-10-13.

| Stage | Docs |
|---|---|
| Whole project | `chat_migrated_update_20261013/outreach` (user's chat notes, Oct 7 and 10; absorbed into `framing.md` and `outreach.md` 2026-10-13; cited as `outreach`) · `PLATICA_current_state_rev4` (rev 4.1, ~Sep 21; see section map below) · `claude_platica_cleanup_plan_2026-10-01` · `claude_PLATICA_census_and_pipeline_order_Sep_26` §1 (block order) |
| `generate_centroids`, `update_google_data_legacy` | `claude_PLATICA_venue_scan_findings_Sep_23` §0 (snapshot hole) · `claude_PLATICA_snapshot_dates_Sep_25` (scan date, 7 km date split) |
| `update_google_data_new` | none found |
| `update_google_data_expanded` | `claude_PLATICA_TEMP_workplan_Sep_23` · `claude_PLATICA_venue_scan_findings_Sep_23` · `claude_PLATICA_hole_probe_Sep_24` · `claude_PLATICA_packing_Sep_24` · `claude_PLATICA_legacy_smoke_tests_Sep_24` · `claude_PLATICA_repair_run_Sep_25` · `claude_PLATICA_verify_and_outer_run_Sep_25` · (idea) `claude_PLATICA_ideas_textsearch_relevance_Sep_24` |
| `google_enterprise` (deprecated; hours histogram now `opening_hours.py`, run in `fetch_enterprise_hours`) | `claude_PLATICA_sampling_delta_Sep_30` §3 · `claude_PLATICA_hours_check_Sep_30` · (idea) `claude_2026-10-05_side-note_hours-imputation` |
| `compile_legacy_google_to_csv`, `compile_new_google_to_csv` | `claude_PLATICA_verification_merge_Sep_25` §5 (merge → `expanded_place_api.csv`) |
| `pre_process_census` | `claude_PLATICA_census_and_pipeline_order_Sep_26` §2 · `claude_PLATICA_snapshot_dates_Sep_25` §8 (census date) · `inputs/README.md` (census update folders and exact file names; not tracked by git) |
| `construct_hex_tiles` | `claude_PLATICA_hex_block_Sep_27` · `claude_PLATICA_fractional_hexes_Sep_29` |
| `basic_stats` (deprecated) | `claude_PLATICA_rating_rule_and_visualisation_Sep_28` |
| `map_construction` | `PLATICA_graph_extent_plots_Sep_21` · `PLATICA_walk_highway_tags_Sep_21` · `claude_PLATICA_graph_rebuild_Sep_29` §1–2 |
| `construct_graph` | `claude_PLATICA_connector_convention_Sep_21` · `PLATICA_walk_dist_m_Sep_21` · `claude_PLATICA_split_rebuild_Sep_22` · `claude_PLATICA_drive_fallback_observation_Sep_23` · `claude_PLATICA_graph_rebuild_Sep_29` §3–5 · `claude_PLATICA_fractional_hexes_Sep_29` §1 |
| `map_construction` (road density; was `construct_density_drive`) | `claude_PLATICA_valhalla_position_Sep_21` · `claude_PLATICA_speed_variants_pending_Sep_26` · `claude_PLATICA_sampling_rethink_Sep_27` §1 · `claude_PLATICA_road_density_speed_Sep_29` · `claude_PLATICA_valhalla_engine_test_Oct_7` · `claude_PLATICA_valhalla_road_mix_Oct_8` · `claude_PLATICA_detour_junctions_google_density_Oct_8` |
| `build_speed_graphs` | `claude_PLATICA_rerun_design_Sep_29` §1 · `claude_PLATICA_road_density_speed_Sep_29` §6 |
| `sample_drive_pairs` (split out of `calibrate_pathing_agent` 2026-10-11; its docs are in the next row) | `claude_PLATICA_OD_resample_Sep_26` · `claude_PLATICA_OD_density_sampling_Sep_27` · `claude_PLATICA_sampling_rethink_Sep_27` · `claude_PLATICA_trim_check_and_sample_plan_Sep_30` · `claude_PLATICA_sampling_delta_Sep_30` · `claude_PLATICA_sampler_and_fetch_Oct_1` · `claude_PLATICA_od_sample_reproducibility_Oct_1` · (idea) `claude_PLATICA_departure_noise_floor_Oct_4` |
| `calibrate_pathing_agent` (drive) | `PLATICA_tilt_rederivation_Sep_21` · `claude_PLATICA_TEMP_workplan_Sep_22` · `claude_PLATICA_split_rebuild_Sep_22` §11 · `claude_PLATICA_drive_calibration_s4_Sep_22` · `PLATICA_s4_verdict_Sep_22` · `claude_PLATICA_OD_resample_Sep_26` · `claude_PLATICA_OD_density_sampling_Sep_27` · `claude_PLATICA_sampling_rethink_Sep_27` · `claude_PLATICA_rerun_design_Sep_29` · `claude_PLATICA_probe_router_Sep_30` · `claude_PLATICA_trim_check_and_sample_plan_Sep_30` · `claude_PLATICA_sampling_delta_Sep_30` · `claude_PLATICA_sampler_and_fetch_Oct_1` · `claude_PLATICA_od_sample_reproducibility_Oct_1` · `claude_PLATICA_drive_rerun_handover_Oct_1` · `claude_2026-10-04_M2_decision_rules` · (ideas) `claude_PLATICA_polyline_regression_idea_Oct_3`, `claude_PLATICA_departure_noise_floor_Oct_4` |
| `construct_pt_graph` (r5py transit) | `claude_PLATICA_zero_duration_hops_Sep_21` · `claude_PLATICA_time_resolution_Sep_21` · `2026-09-21_r5py-network-build` · `claude_PLATICA_departure_noise_floor_Oct_4` (transit fetch notes) |
| Cleanup process | root `CLAUDE.md` (in force) · `claude_platica_cleanup_plan_2026-10-01` · `claude_PLATICA_git_claude_code_setup_Oct_2` · `claude_cleanup-workflow` · `claude_CLAUDE.md` (superseded) |

### Doc table

| File (in `session_docs_to_20261013/`) | Date | Kind | Topic | Superseded by |
|---|---|---|---|---|
| `PLATICA_current_state_rev4.md` | ~Sep 21 | decision | Whole-project state, rev 4.1: framing, data, model design, mode layers, validation, limitations, rejected options, lessons, work remaining | Partly, by every later delta in its area |
| `claude_PLATICA_connector_convention_Sep_21.md` | Sep 21 | decision | Google doesn't charge snap connectors; drive router fix | rev4 §5.1, §6.1, §6.3 item 2 replaced by this; framing updated by `fractional_hexes_Sep_29` |
| `claude_PLATICA_valhalla_position_Sep_21.md` | Sep 21 | decision | Valhalla: density classifier adopted, speed tables rejected, engine not adopted; why not OSRM | — |
| `claude_PLATICA_zero_duration_hops_Sep_21.md` | Sep 21 | decision | Transit 0 s hops: keep raw published durations | — |
| `claude_PLATICA_time_resolution_Sep_21.md` | Sep 21 | decision | Google display rounds to minutes; r5py truncates; how to compare | — |
| `2026-09-21_r5py-network-build.md` | Sep 21 | delta | r5py TransportNetwork build; 6,195 unlinked stops = PBF boundary effect | — (built on the old PBF; extract since replaced, see `graph_rebuild_Sep_29`) |
| `PLATICA_graph_extent_plots_Sep_21.md` | Sep 21 | check | Graph extent plots; rev4 §5.5 resolved | — |
| `PLATICA_tilt_rederivation_Sep_21.md` | Sep 21 | check | Residual tilt by distance: M2 +0.116 pp/km vs M0 ~1.3. M2 figures pre-connector-fix | Next day: `claude_PLATICA_TEMP_workplan_Sep_22` L20-27 (`drive-calibration.md` Notes) |
| `PLATICA_walk_dist_m_Sep_21.md` | Sep 21 | check | `walk_dist_m` distribution; snap tail negligible | §5 framing → `fractional_hexes_Sep_29` |
| `PLATICA_walk_highway_tags_Sep_21.md` | Sep 21 | check | Walk graph highway tags; no motorways; fragments are missing links | — |
| `claude_PLATICA_TEMP_workplan_Sep_22.md` | Sep 22 | workplan | One-day plan: snapping patch, routing edits, pre-registered "satisfactory" test | Executed in `split_rebuild_Sep_22`, `drive_calibration_s4_Sep_22` |
| `claude_PLATICA_split_rebuild_Sep_22.md` | Sep 22 | delta | Re-split graph from source; hex→node; enrich; walk/drive routing | Graph parts redone in `graph_rebuild_Sep_29` |
| `claude_PLATICA_drive_calibration_s4_Sep_22.md` | Sep 22 | delta | Drive calibration (M2, dense, β=12); §4 criterion 1 | §5, §8 → `s4_verdict_Sep_22` |
| `PLATICA_s4_verdict_Sep_22.md` | Sep 22 | decision | §4 criteria 1–2 verdict: all three models fail criterion 2 | Model set later revised in `rerun_design_Sep_29` |
| `claude_PLATICA_TEMP_workplan_Sep_23.md` | Sep 23 | workplan | Venue scan expansion plan | §2.1, 2.2, 2.4, order → `venue_scan_findings_Sep_23`; to-dos → `hole_probe_Sep_24` |
| `claude_PLATICA_venue_scan_findings_Sep_23.md` | Sep 23 | delta | Legacy snapshot has a hole: saturated 800 m hexes 7.5–20 km dropped; Text Search probe method | §4 to-dos → `hole_probe_Sep_24` |
| `claude_PLATICA_drive_fallback_observation_Sep_23.md` | Sep 23 | idea | 3 fallback pairs: directed dead-end hypothesis (untested) | — `?` |
| `claude_PLATICA_hole_probe_Sep_24.md` | Sep 24 | delta | Hole confirmed by 5-pass probe; API ledger added | §2 cost, §4 packing → `packing_Sep_24` |
| `claude_PLATICA_packing_Sep_24.md` | Sep 24 | delta | Search lattice (`hex_lattice`), packing (`hex_pack`), repair price | §7 partly → `legacy_smoke_tests_Sep_24`, `repair_run_Sep_25` |
| `claude_PLATICA_ideas_textsearch_relevance_Sep_24.md` | Sep 24 | idea | Text Search as a relevance layer; Top-N properties | — |
| `claude_PLATICA_legacy_smoke_tests_Sep_24.md` | Sep 24 | delta | Legacy request layer wired to ledger; 6 smoke tests | §5 → `repair_run_Sep_25` |
| `claude_PLATICA_repair_run_Sep_25.md` | Sep 25 | delta | 7–20 km repair run: decisions, pilot, result | §8 → `verify_and_outer_run_Sep_25`; §10 headroom stale (`verification_merge_Sep_25`) |
| `claude_PLATICA_snapshot_dates_Sep_25.md` | Sep 25 | decision | No sound-disc refresh (state as limitation); census kept at 2021 | — |
| `claude_PLATICA_verify_and_outer_run_Sep_25.md` | Sep 25 | delta | Repair verified; outer ring fetched and verified | §7 to-dos → `verification_merge_Sep_25` |
| `claude_PLATICA_verification_merge_Sep_25.md` | Sep 25 | decision | Verification results; ledger is authoritative; merge → `expanded_place_api.csv`; scan date 29 Jun | — |
| `claude_PLATICA_census_and_pipeline_order_Sep_26.md` | Sep 26 | decision | Pipeline block order after the merge; `abs_census` review and fix | — |
| `claude_PLATICA_OD_resample_Sep_26.md` | Sep 26 | delta | Old Google OD sample doesn't cover the outer ring | Sampling chain → `OD_density_sampling_Sep_27` → `sampling_rethink_Sep_27` → `rerun_design_Sep_29` §2 → `sampling_delta_Sep_30` → `sampler_and_fetch_Oct_1` |
| `claude_PLATICA_speed_variants_pending_Sep_26.md` | Sep 26 | idea | Speed variants and external speed data, all pending | `?` partly by `road_density_speed_Sep_29` §6 |
| `claude_PLATICA_hex_block_Sep_27.md` | Sep 27 | decision | Hex block at 100 km: extent, subject pin, grid, census allocation, venue assignment, empty-hex filter | §11 OD items → sampling chain |
| `claude_PLATICA_OD_density_sampling_Sep_27.md` | Sep 27 | delta | OD sample size per density tier (proposed) | → `sampling_rethink_Sep_27` |
| `claude_PLATICA_sampling_rethink_Sep_27.md` | Sep 27 | delta | Divided-road double counting; Google path as measurement; Routes API facts; ToS | §4 → `rerun_design_Sep_29` §2 |
| `claude_PLATICA_rating_rule_and_visualisation_Sep_28.md` | Sep 28 | decision | Rating rule for Top N (shrinkage dropped); light analytics; hex figures | — |
| `claude_PLATICA_fractional_hexes_Sep_29.md` | Sep 29 | decision | Reachability = Google's view; connector not charged (walk and drive); fractional hexes: no action | — |
| `claude_PLATICA_graph_rebuild_Sep_29.md` | Sep 29 | delta | Graph rebuild on the 100 km extract; `reduce_isolated_edges` rewritten; walk graph role after r5py | — |
| `claude_PLATICA_road_density_speed_Sep_29.md` | Sep 29 | decision | New extract coverage; which roads count for density (from Valhalla source); `enrich` variants | — |
| `claude_PLATICA_rerun_design_Sep_29.md` | Sep 29 | decision | Drive rerun model set, β choices, resampling method | §2 → `sampling_delta_Sep_30` |
| `claude_PLATICA_probe_router_Sep_30.md` | Sep 30 | delta | Blind probe graph; window router; stale paths found | §9 to-dos → `trim_check_and_sample_plan_Sep_30` |
| `claude_PLATICA_trim_check_and_sample_plan_Sep_30.md` | Sep 30 | delta | `compare_trim` done; window W = 25 blind raw min; sample count and split | → `sampling_delta_Sep_30` |
| `claude_PLATICA_sampling_delta_Sep_30.md` | Sep 30 | decision | OD sampler spec; departure hours; 60-venue hours check plan; billing findings | Executed in `hours_check_Sep_30`, `sampler_and_fetch_Oct_1` |
| `claude_PLATICA_hours_check_Sep_30.md` | Sep 30 | decision | Hours histogram rebuilt from raw JSONs; 60-venue check verdict AGREE | — |
| `claude_PLATICA_sampler_and_fetch_Oct_1.md` | Oct 1 | delta | OD sampler (N = 4,000) and Routes fetch; old 540 used only for the blind probe | — |
| `claude_PLATICA_od_sample_reproducibility_Oct_1.md` | Oct 1 | delta | Reproducibility gap: blind probe calibrated on the old 540 | — |
| `claude_PLATICA_drive_rerun_handover_Oct_1.md` | Oct 1 | handover | Drive rerun launched; agenda: pass criteria first, then reorganise code | Pass criteria → `M2_decision_rules` |
| `claude_platica_cleanup_plan_2026-10-01.md` | Oct 1 | process | Why and how to clean up: scope, proportion, decisions, to-dos | Rules → root `CLAUDE.md` |
| `claude_PLATICA_git_claude_code_setup_Oct_2.md` | Oct 2 | process | Git, GitHub and Claude Code setup | §"CLAUDE.md (current content)" → root `CLAUDE.md` |
| `claude_PLATICA_polyline_regression_idea_Oct_3.md` | Oct 3 | idea | Fit drive speeds from Google polylines by regression (after cleanup) | — |
| `claude_2026-10-04_M2_decision_rules.md` | Oct 4 | decision | Pre-registered pass rules for the drive model comparison (M0, OSM table, M2) | — |
| `claude_PLATICA_departure_noise_floor_Oct_4.md` | Oct 4 | idea | Departure-time noise floor as a stopping rule for calibration | — |
| `claude_2026-10-05_side-note_hours-imputation.md` | Oct 5 | idea | Impute competitor hours from tags; use this month's Enterprise budget | — |
| `claude_PLATICA_valhalla_engine_test_Oct_7.md` | Oct 7 | check | Valhalla engine vs Google on the 4,000 pairs (defaults and speed table): close to M2, not better; Windows/pyvalhalla traps | — |
| `claude_PLATICA_valhalla_road_mix_Oct_8.md` | Oct 8 | check | Valhalla speed_table's remaining distance bias follows junctions per km, not road mix or density | — |
| `claude_PLATICA_detour_junctions_google_density_Oct_8.md` | Oct 8 | delta | Detour: Valhalla junction test (fails, closes); M2 per-pair file located; Google's slowdown by continuous road density from polylines (runs the Oct 3 polyline idea as description only) | — |
| `claude_cleanup-workflow.md` | ~Oct 2 | process | Cleanup how-to | Root `CLAUDE.md` wins where they differ (e.g. folder roles) |
| `claude_CLAUDE.md` | ~Oct 2 | process | Earlier copy of the Claude Code rules | Root `CLAUDE.md` (in force) |

### Section map: `PLATICA_current_state_rev4.md`

Read a section by line range. Rev 4.1 is ~Sep 21: check the stage table above for later deltas.

| Lines | Section |
|---|---|
| 1–28 | Header, supersession note |
| 29–77 | Part I — What the project is: §0 Framing (31), §1 Definition and audiences (58) |
| 78–194 | Part II — Data and infrastructure: §2 Layers (80), §3 Extracts, files and known traps (107; PBF 109, GTFS 128, file traps 151, key paths 179) |
| 195–498 | Part III — Model design: §4 Bands, scoring, counterfactuals (197; three bands 199, Top-N 236, decision rule and ratings 257, drivable band 279, four corners 302, drive metrics 462) |
| 499–787 | Part IV — Drive layer §5 (501; spec 503, β 527, M2 urban correction 599, road density 681, northern cap retired 749) |
| 788–1099 | Part IV — Walk and transit §6 (788; walk calibration 790, fragments 826, open walk checks 871, transit timing 948, wait model 1012, r5py pivot 1051, fragment count 1087) |
| 1100–1354 | Part V — Validation: §7 Google ETA collection (1102; replication 1149, ToS 1165), §8 ceiling finding (1190), §9 empirical findings (1250) |
| 1355–1971 | Part VI — Judgement: §10 limitations (1357), §11 applications (1433), §12 rejected (1497), §13 speed-table line retired (1613), §14 kinematic modelling closed (1681), §15 methodology lessons (1788) |
| 1972–2117 | Part VII — Work remaining: §16 immediate (1974), §17 drive (1997), §18 transit/r5py (2011), §19 reachability pass (2016), §20 after the table exists (2037) |
| 2118–end | Appendix — historical, resolved |
