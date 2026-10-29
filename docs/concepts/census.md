# Census and population

**Purpose and scope.** The two population denominators (residents, workers): sources, census year,
attrition from the raw tables, and how counts are shared onto hexes. Not the grid itself or venue
assignment (`hexes.md`), nor how population is scored (`scoring.md`).
**Stages.** `pre_process_census`; the residents and workers layers of `construct_hex_tiles`.
**Last reviewed.** 2026-10-13, ff0457a
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/census.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **CEN-1.** Two denominators, never blended: residents (ABS 2021 Census DataPack G01, persons by usual
  residence, by SA1) and workers (ABS 2021 place of work by Destination Zone, persons 15+, TableBuilder
  Pro export). Each is reported on its own.
  Evidence: none (definition). DESIGN_pre_spine "Data layers"; rev4 L86-87; `snapshot_dates_Sep_25` L83-84.
- **CEN-2.** `pre_process_census` keeps all of Victoria and never needs a rerun for extent; clipping to
  the study area happens at hex assignment.
  Evidence: none. `census_and_pipeline_order_Sep_26` L78-80. Code: `abs_census.build_census_2021`.
- **CEN-3.** Census attrition (2021). Residents: 15,478 SA1s kept, 6,494,200 persons; 4 SA1s with null
  geometry (9,124 persons) dropped; gap to the ABS total 6,503,491 after that drop is −167 (0.003%),
  ABS perturbation. Workers: 3,011 zones kept, 3,026,180 workers; 11 non-zone rows and 2 mesh
  null-geometry rows dropped; 194 migratory and 137,478 no-fixed-address workers excluded; ledger
  closes to the ABS total 3,163,746 within +106 (0.003%), perturbation.
  Evidence: run printout only (`abs_census.py` prints every drop); no saved diagnostic.
  `census_and_pipeline_order_Sep_26` L103-121.
- **CEN-4.** Zone counts are shared to hexes area-proportionally (overlap area / full zone area); each
  layer also stores `<col>_cov`, the share of the hex's area covered by census zones.
  Evidence: vectorised version matched the old code (sum 2,425,634.49 on 174,817 old hex IDs),
  `hex_block_Sep_27` L63-73; no saved diagnostic. Code: `hex_tile_construction.py`.
- **CEN-5.** Placed on the grid: residents 5,426,837 of 6,494,200 (83.6%); workers 2,569,313 of
  3,026,180 (84.9%). Worker-only hexes (175,002; 12,583 within 20 km) are kept as genuine.
  Evidence: none saved. `hex_block_Sep_27` L77-82; `rating_rule_and_visualisation_Sep_28` L146-147.
- **CEN-6.** Census year is set per layer by hand (`config.CENSUS_RESIDENTS_YEAR`,
  `CENSUS_WORKERS_YEAR`), both 2021 now. The project leans towards one year for both; mixed years are
  allowed but warned: the hex stage warns and the write-up states it as a limitation. Newer years are built from `inputs/census/`
  (`abs_<year>/`, `dzn_<year>/`) by `abs_census.build_census_update`.
  Evidence: none (user decisions 2026-10-08, 2026-10-13). DESIGN_pre_spine "Data layers"; supersedes `snapshot_dates_Sep_25`
  L108-122 (swap both together, never residents alone).
- **CEN-7.** Reports use population-weighted shares, never unweighted hex counts: hex counts overstate
  exposure to any hex-level defect.
  Evidence: none. rev4 L1421-1423.
- **CEN-8.** Daytime presence (attention exposure, work from home) is kept apart from residential
  population in the write-up.
  Evidence: none. `snapshot_dates_Sep_25` L95-97.

## Not adopted
- OSM building-footprint weighting for allocation: accuracy finer than the bands; needs rent data; 8.9% imputation noise. rev4 L97-99.
- Rescaling residents alone to ABS ERP 2024-25 (SA2 scaling): mismatched denominator dates, and workers have no annual estimate. `snapshot_dates_Sep_25` L99-112, L121-122.
- ABS Mesh Block counts for residents (finer than SA1): not adopted by the user 2026-10-13. `hex_block_Sep_27` L181-182.
- SEIFA as the income measure: SA1 median household income instead (see Notes, income profile). rev4 L2104-2105.
- `skipfooter=` when reading the TableBuilder export: breaks silently if a re-export changes the footer; rows are matched by pattern and drops printed. `census_and_pipeline_order_Sep_26` L125-126.

## Limitations
- Worker allocation was never checked after vectorising (max |Δ|, sums, worker-only count back to 12,583); residents passed. Accepted unverified by the user 2026-10-13; flagged in case it surfaces. `hex_block_Sep_27` L172-173.
- 2021 Census night fell in lockdown with borders closed: inner-city residents (international students, migrants) and office-zone workers likely undercounted; reach near the CBD likely understated. Cost not measured. `snapshot_dates_Sep_25` L87-94, L126-130.
- Growth since 2021 is uneven (inner city and fringe corridors change most), so 2021 counts are not a uniform bias. Cost not measured. `snapshot_dates_Sep_25` L91-94.
- 137,478 no-fixed-address workers (4.3% of Victoria's workforce) are excluded, probably not at random (mobile workers eat out at work). `census_and_pipeline_order_Sep_26` L132-135.
- The worker layer is visibly coarser than residents (DZN median 0.53 km², 25-50 hexes per zone, flat patches). Area-proportional allocation judged adequate for workers. rev4 L87, L97-98, L1418-1420.

## Notes
- Shares of Victoria quoted in rev4 (37% of residents, 50% of workers "in the disc") are for the old
  20 km disc. The worker figure is 50% of 3.03 M placed workers, i.e. 48% of 3.16 M; any sentence
  quoting it must say which. `census_and_pipeline_order_Sep_26` L136-137. (Sep 26)
- Income profile (musing, not planned; user 2026-10-13): compare reachable vs won population on SA1
  median household income, population-weighted across overlapping SA1s; the direction of the gap is
  the point. Pursue only if reliable data, a study or a method turns up. rev4 L2102-2109.
- ABS release plan: 2026 Census night 11 Aug 2026; residents June 2027; workers Oct 2027; other topics
  early 2028. `snapshot_dates_Sep_25` L116-119 (verified Sep 25).
- Planned limitation analysis (free, not blocking): ABS ERP 2021 vs 2025 per SA2, ratio against
  distance from the CBD and the subject, with a map (confirm ASGS 2021 edition); a sensitivity rerun of
  reach with residents rescaled to 2025 (headline stays 2021); once released, compare 2021 with the
  2026 Census directly. Workers can't be checked before Oct 2027. `snapshot_dates_Sep_25` L143-161.
- The 2021 workers export was downloaded ~Aug 2026 but describes Census night Aug 2021. `snapshot_dates_Sep_25` L84-85.

## Open questions
- None.

## Changes
- Changes to 2026-10-20 (CEN-1 to CEN-8): snapshot, "Changes".
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
