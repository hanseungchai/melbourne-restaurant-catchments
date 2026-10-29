# Hex grid and allocation

**Purpose and scope.** The population grid: geometry, extent, subject pin and stencil, per-layer
tables, venue assignment, the empty-hex filter and fractional hexes. Not census sources or attrition
(`census.md`), the venue scan's search lattice and packing (`venues.md`), hex → road node snaps
(graph doc), nor the edge flag's use in scoring (DESIGN.md Q5, reachability doc).
**Stages.** `construct_hex_tiles` (`hex_tile_construction.py`; config "Hex grid" group).
**Last reviewed.** 2026-10-13, 24d69e4
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/hexes.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **HEX-1.** Flat-top hexes, 100 m vertex to vertex (`HEX_DIAMETER_M`), axial (q, r) coordinates
  counted from hex 0, the subject's hex. Hex IDs number ring by ring, so a larger radius only appends IDs.
  Evidence: none (definition). Code: `generate_hex_grid`. rev4 L85; `hex_block_Sep_27` L52-53.
- **HEX-2.** Grid reach 100 km from the subject (`HEX_GRID_RADIUS_M`), spherical haversine
  (R = 6,371 km). Reason: competitors need their own reach horizons, so outer venues need hexes.
  Evidence: none (user decision, Sep 27). `hex_block_Sep_27` L14-16; supersedes the 20 km grid.
- **HEX-3.** Ring count derived from the radius: `N_RINGS = ceil(HEX_RING_MARGIN · radius / (1.5 ·
  circumradius)) + 1`, margin 1.01; `build_hex_grid` asserts no retained hex sits on the last ring
  (the outermost retained ring was 1,336 of 1,348).
  Evidence: the assert in code. `hex_block_Sep_27` L45-51.
- **HEX-4.** Subject chosen by coordinates: default from `frozen_inputs/manual_inputs/`
  (`-37.7687014, 144.9719611`), others from `inputs/alt_subjects/<name>.txt`. Every grid snaps to one
  stencil, the lattice laid from the default subject; hex 0 is the stencil hex the subject falls in,
  so grids of different subjects share identical hexes where they overlap (their hex IDs differ, being
  counted from each subject's hex 0). Files go in a `<lat>_<lon>` subfolder and carry that tag.
  Evidence: none (user decisions 2026-10-08). DESIGN_pre_spine "Data layers"; code: `snap_to_stencil`.
- **HEX-5.** Built per data layer: residents, workers and venue counts each get their own table
  (`hex_id` + the layer's columns, every hex of the bare grid), tagged by the layer's date
  (`res<year>`, `wrk<year>`, `ven<date>`), built only when missing or `should_rebuild_hex_layers` is on.
  `assemble_hex_layers` joins them, asserting each covers the bare grid's hexes, then filters.
  Evidence: none (user decision 2026-10-08). DESIGN_pre_spine "Data layers".
- **HEX-6.** Venues go to the nearest hex centroid (KD-tree, metric CRS); venues farther than 50 m
  from every centroid (`VENUE_HEX_MATCH_RADIUS_M`) are dropped and counted, so out-of-grid venues are
  not pulled onto edge hexes. `venue_count` counts all venue types in the table picked by
  `HEX_VENUES_DATE`. 18,498 venues assigned (output check 2026-10-13).
  Evidence: printed by the stage. Closes the "no miss report" item, `census_and_pipeline_order_Sep_26` L51-52.
- **HEX-7.** Empty-hex filter: keep `residents > 0 OR workers > 0 OR venue_count > 0`. The threshold is
  > 0, not ≥ 1: area-proportional allocation gives every interior hex of a zone the same share, so a
  ≥ 1 rule would drop whole sparse zones (~200 k rural residents), not a rounding remainder. The
  subject's hex must survive (asserted).
  Evidence: none (reasoning). Code: `filter_empty_hexes` docstring. rev4 L91-95; `hex_block_Sep_27` L119-122.
- **HEX-8.** Counts (default subject, 2021 census, venues 20260925; output check 2026-10-13): 4,847,791
  generated, 4,078,906 retained, 768,885 dropped. Of those retained: 4,078,606 have workers > 0 (300
  don't), 3,903,901 have residents > 0, 175,002 are worker-only, 3 survive on venues alone, 8,959 hold
  a venue. The dropped hexes include some uninhabited land, not only water (user, Google Maps, Sep 28).
  Evidence: output check 2026-10-13 on `hex_grid_with_population_res2021_wrk2021_ven20260925_*.gpkg`;
  no saved diagnostic. Corrects `hex_block_Sep_27` L116-117 ("0 land hexes dropped").
- **HEX-9.** Fractional hexes: no action. 3,585,855 retained hexes (88%) hold under one person in both
  columns and no venue (202,505 residents, 121,691 workers); all are kept.
  Evidence: output check 2026-10-13 (count); `fractional_hexes_Sep_29` §2 (decision).
- **HEX-10.** Coverage check (user, 2026-10-08): a warning before the grid is built, never a stop. A hex
  at the edge of the subject's 20-min drive band is contested by competitors up to 20 min from it, so
  competitors within 40 min of the subject matter; very worst case, cars fly straight at 110 km/h
  (`MAX_DRIVE_SPEED_KMH`): a 73.3 km disc. The stage reports the share of that disc outside the venue
  scan and outside the road extract box, worded by tier: ≤ 10% likely not an issue; ≤ 30% low chance
  marginal venues are missed; ≤ 50% reasonable chance; above, very probable.
  Evidence: code (`hex_tile_construction.check_subject_coverage`); config "Coverage check".

## Not adopted
- Fixed "+2 rings": truncates the grid at 100 km (1,336 rings generated, survivors on ring 1,336). `hex_block_Sep_27` L47-49.
- Correcting `METRES_PER_DEGREE_LAT = 111_320` (hexes ~0.16% small in true metres): would move every hex boundary. `hex_block_Sep_27` L54-56.
- Matching the haversine disc to the true ellipsoid (~99.8 km N-S to ~100.24 km E-W): ±200 m on 100 km, and it would change the retained edge set. `hex_block_Sep_27` L28-31.
- ≥ 1 empty-hex rule, and a mass-coverage filter (keep hexes holding 99.9% of people): both drop whole sparse zones. HEX-7; `graph_rebuild_Sep_29` L110-115.
- An "active hex" filter on origins: drops nothing, every retained hex is active. `graph_rebuild_Sep_29` L107-109.
- Coarsening by one coarse hex size everywhere; nearest/farthest-point region interpolation (distance order isn't travel-time order); greedy or periphery-seeded merging (order-dependent, seams); distance-from-subject coarsening (competitors need their own horizons). `fractional_hexes_Sep_29` §4.
- Per-stage venue/hex outputs: one in-place venue/hex file kept for now (user, Sep 27). `hex_block_Sep_27` L109-112.

## Limitations
- The 100 km line cuts towns: Ballarat (~-37.56, 143.87; CBD ~102 km out) loses catchment west of the
  line, so its competitors look weaker; same for any town the line crosses. Cost not measured; the
  edge flag handles it (decided 2026-10-23, DESIGN.md Q5). `hex_block_Sep_27` L26-27; `road_density_speed_Sep_29` L10.
- Fractional population on empty land (parkland, bayside, industrial, fringe) appears in unweighted hex
  counts; report weighted shares (CEN-7). rev4 L101-105.
- The empty-hex filter drops uninhabited land as well as water; `_cov` = 0 does not mean water.
  Hypothesis (unverified): zero-population zones were lost in census preprocessing. `rating_rule_and_visualisation_Sep_28` L155-162.

## Notes
- Hunch (user, unverified): fractional hexes are already merged in practice, since reachability
  resolves per node and sparse fringe hexes share nodes. Cheap check if ever needed: unique nodes vs
  hexes on the fringe. `fractional_hexes_Sep_29` §2. (Sep 29)
- Stencil method, parked "if coarsening is ever needed": coarse cells group existing hex IDs (never a
  new tiling); a fixed aperture-7 stencil anchored at hex 0; a flower merges only if all seven members
  qualify; at most two levels (49 hexes, ~700 m); the "under one person" cut-off is arbitrary, so run a
  sensitivity at 1 / 2 / 5 if adopted. `fractional_hexes_Sep_29` §3. (Sep 29)
  Revived for band-3 transit origins only (2026-10-26, `reachability.md` RCH-27): members below a persons threshold
  merge (heavy members route alone), routed from the persons-weighted centroid; the grid itself is unchanged.
- Zero drift on the 100 km extension: the old 20 km hexes reproduce exactly (Sep 27; detail and the
  `legacy_evidence` grid it was checked against: snapshot, Notes).
- Old 20 km grid, for reading older docs: 193,883 generated, 174,817 retained, 4,264 with restaurants.
  rev4 L85.
- HEX-6's 18,498 matches the venue table (`venues.md` VEN-4).
- Older docs use `population`, `population_cov`, `restaurant_count`; renamed `residents`,
  `residents_cov`, `venue_count` in pass B (user, 2026-10-08). Legacy reference files keep the old names.

## Open questions
- DESIGN.md Q5 (edge flag): decided 2026-10-23 (user); threshold 1 km from the drive graph's outer boundary (82nd, DESIGN.md Q5).

## Changes
- Changes to 2026-10-20 (HEX-1 to HEX-10): snapshot, "Changes".
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
- 2026-10-23 · Q5 edge flag decided (pointer wording only)
- 2026-10-26 · Notes: stencil revived for band-3 transit origins (RCH-27, 111th)
