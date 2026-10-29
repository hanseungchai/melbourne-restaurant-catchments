# Road density and urban class

**Purpose and scope.** How road density is measured (raster, counted road set, Valhalla's level and
tier rule), sampled at hexes, nodes and route points, and how it is spread over people. Not how
density changes drive speed or which tier structure the drive model fits (drive model / drive
calibration docs), nor the grid edge (`hexes.md`).
**Stages.** `map_construction` (density half: `road_density.py`; config "Road density" group). Read
by `build_speed_graphs` (`functions/density_levels.node_levels`) and `calibrate_pathing_agent`.
**Last reviewed.** 2026-10-13, f003897
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/density.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **DEN-1.** Urban class follows Valhalla's published road-density rule, not a census measure: road km
  per km² within a 2 km disk (`ROAD_DENSITY_RADIUS_M`), level = round(density × 0.7) (C++ rounding)
  capped at 15; tiers rural ≤ 5, suburban 6-10, urban 11-15 (undone: suburban from ~7.86, urban from
  15 km/km², level 15 from 20.7). Reason: a published definition with no census join.
  Evidence: Valhalla `graphenhancer.cc`, `speed_assigner.h` (read from source, Sep 18; config cites
  them). `valhalla_position_Sep_21` L28-31; rev4 L683-691.
- **DEN-2.** Counted road set matched to Valhalla's source: motorway to residential, `road`,
  `residential_link`, ramps and turn channels, and `highway=service` unless tagged `parking_aisle`,
  `driveway` or `drive-through` (so alleys, emergency access and untagged service count); tracks,
  living streets and paths don't. Main-road ways with a service tag (13.5 km, 0.02%) are ignored.
  Evidence: Valhalla `graphenhancer.cc`, `graph.lua` (settled from source); code `classify_way`.
  `road_density_speed_Sep_29` L29-35, L45. Supersedes the include-all set of Sep 18-21.
- **DEN-3.** One raster over the whole road extract (not the grid trim), 100 m cells: each way is cut
  into 10 m pieces, each piece's length goes to the cell under its midpoint, then convolved with the
  discrete 2 km disk (12.570 km² vs 12.566 exact). Stores continuous density (float km/km²); levels
  and tiers are applied after sampling. Depends on the extract only, so not tagged by subject.
  Evidence: the stage prints rasterised km and disk area. Code `road_density_raster`.
  rev4 L693-700; `road_density_speed_Sep_29` L14-15.
- **DEN-4.** Hexes, drive nodes and Google route points all read density from the raster at their own
  location through one function (`sample_density`, NaN off the raster) and one level rule
  (`valhalla_tier`). Drive nodes off the raster (outside the extract; asserted) get level 0, rural.
  Evidence: none (code). Replaces the nearest-hex lookup, which silently missed 438,765 nodes at
  20-35 km. `STALE_density_speed_variants_code_changes_Sep_18` L7-12; `road_density_speed_Sep_29` L93.
- **DEN-5.** Per-hex labels for maps and description: `density_tier` (rural / suburban / urban) and
  `urban_subtier` (11 marginal, 12-14 mid, 15 dense), combined in `density_class`; an uncapped level
  for description only. Drive models use their own tier labels (DESIGN_pre_spine "Drive layer", edge tier labels).
  Evidence: none (definition). Code `urban_subtier`. `STALE_road_density_and_extract_Sep_18` L44-64.
- **DEN-6.** Every hex reads density from a full 2 km disk inside the extract (none clipped, none NaN),
  so no hex reads low for lack of mapped roads.
  Evidence: `diagnostics/road_density_distribution.py` (run 2026-10-09, supported).
- **DEN-7.** Density over people, not hexes (2026-10-09, 4,078,906 hexes): median 0.95 km/km² per hex
  (92% rural) but 12.5 for residents and 13.8 for workers. Residents 18% rural / 61% suburban / 21%
  urban (4.1% dense); workers 15% / 47% / 38% (20.9% dense). 17% of residents and 15% of workers sit
  within ±1 km/km² of the urban cutoff, so tier assignment is sensitive there. GPO reads 26.1 km/km².
  Evidence: `diagnostics/road_density_distribution.py`. Supersedes the Sep 19 tier table (20 km grid,
  include-all set) and the Sep 29 shares.

## Not adopted
- ABS activity density (residents + workers in a 1 km² window) with ABS-style cutoffs: 200 persons/km² puts 94% of hexes in one class; ABS 200 separates town from country nationally, not dense from suburban; counts people twice and mixes day and night. `STALE_urban_classification_and_speed_spec_Sep_18`; `valhalla_position_Sep_21` L28-31.
- A foot-traffic model fitted to City of Melbourne pedestrian sensors: the sensors sit where traffic was already expected (mostly the city), so the fit would be biased in the areas being modelled. rev4 L1593-1595; user, 2026-10-13 (see Notes).
- Hand-drawn CBD box: replaced by the Valhalla level. `STALE_density_speed_variants_code_changes_Sep_18` L16-19.
- Percentile cutoffs, and any urban boundary above level 15: chosen cutoffs that move with the study-area trim. rev4 L738-741, L1608-1609.
- Continuous urban weight: needs a shape and endpoints nothing pins down. `STALE_urban_classification_and_speed_spec_Sep_18` L100-101.
- Include-all road set (+19% length over Valhalla's set, ~3 km/km² at urban densities, more than two levels; 101,088 km with all unverified roads, tracks alone 18.8%) and strict exclusion of all unverified roads (71,928 km; drops generic service roads). `road_density_speed_Sep_29` L37, L43; `valhalla_position_Sep_21` L34-38.
- Density from 300-500 m radii with tercile cuts: arbitrary scale. `STALE_google_speed_table_rejected_and_eta_metadata` L40.
- Carriageway-collapse test for divided roads: proposed, not adopted; double counting estimated second-order (~+0.3 km/km² against the 20.71 cut; only boundary hexes flip). `sampling_rethink_Sep_27` L9-23.

## Limitations
- Length is spread along each way's geometry; Valhalla puts edge length at nodes (~150 × 180 m cells). Kept as is; cost not measured. `road_density_speed_Sep_29` L47.
- Divided roads mapped as two ways count both carriageways (each two-way way counts once, as in Valhalla, which halves directed-edge length). Boundary hexes near level 15 may flip; second-order, not measured. `sampling_rethink_Sep_27` L9-19.
- Roughly a sixth of people sit within ±1 km/km² of the urban cutoff (DEN-7), so tier shares are sensitive to small density errors there.

## Notes
- Why Valhalla's measure (user, 2026-10-13): it replaced a foot-traffic model fitted to City of
  Melbourne's pedestrian sensors, which sit mostly in the city; Valhalla's density is computed everywhere
  from the same road data. History: snapshot, Notes.
- Version caveat (Sep 18): Valhalla's tier code was read from current master, the AU-VIC speed table
  is early 2022. Unsettled (`git log -S "kDensityRadius"` never run); matters only for `osmtable`.
  `STALE_critique_and_speed_table_retirement_Sep_18` L105-107.
- Optional: derive the km/km² cutoffs as (level + 0.5)/0.7 (stored 7.86 is 7.857; 0.001 share
  mismatch). `road_density_speed_Sep_29` L25.
- Residents peak at 13.5-14.5 km/km², just under the urban cutoff; workers are bimodal with a sharp
  CBD peak (24-27 km/km²), no sign of DZN smearing. `road_density_speed_Sep_29` L59-62. (Sep 29)
- Victorian AADT (freeways and arterials, 2020, COVID year) and SCATS (signals, arterials only) exist
  as traffic data; not used. `speed_variants_pending_Sep_26` L73-80.
- Ewing & Cervero 2010: verify the definition before citing. `STALE_urban_classification_and_speed_spec_Sep_18` L107-108.

## Open questions
- DESIGN.md Q15 (density slowdown by road class; drive model doc).

## Changes
- Changes to 2026-10-20 (DEN-1 to DEN-7): snapshot, "Changes".
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
