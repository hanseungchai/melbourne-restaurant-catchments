# Road graph

**Purpose and scope.** The drive graph built from OSM: extract, which ways enter, direction and access,
the strong-component cut, candidate roads per hex, the 50 m split, hex → node snapping, and the
connector convention. Not edge speeds, signals or density tiers on edges (drive model doc), the road
density surface (`density.md`), the walk graph (`walk.md`, WLK-5, W3), transit (transit doc), or how
Google snaps its own trip ends beyond what fixes the tie window (DESIGN.md Q12).
**Stages.** `map_construction` (`road_graphs.build_road_graphs`, cleaned), `construct_graph`
(`routing_graph.py`, cleaned).
**Last reviewed.** 2026-10-13, ee0fc18
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/graph.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **GRF-1.** One extract: BBBike `planet_143.599,-38.893_146.327,-36.735` (data 2026-09-23), frozen in
  `frozen_inputs/osm_extract/`; edges ~115 km N, 125 km S, 121 km W, 119 km E of the subject, so the
  100 km grid is covered. Each graph is stamped with its source PBF and build time. The older
  northern-cap limitation (old extract's edge at −37.598) is retired: true then, superseded.
  Evidence: config `ROAD_EXTRACT_PBF_PATH`; frozen_inputs/README.md. `hex_block_Sep_27` L17-20;
  `graph_extent_plots_Sep_21` L81-116.
- **GRF-2.** Drive graph: a networkx DiGraph, one edge per consecutive OSM node pair (so straight
  edges are exact; no geometry needed), length by haversine, `highway` and the raw `maxspeed` tag kept.
  Ways: `config.DRIVE_HIGHWAY_TYPES`, every `service` way included (driveways and parking aisles too);
  areas never. Access: the mode tag first (`motor_vehicle`, else `vehicle`), general `access` only as
  fallback; `no` / `private` exclude. One-way: explicit tag wins (`-1` reversed); untagged roundabouts,
  circular junctions and motorways are one-way; untagged `motorway_link` stays two-way, and
  `oneway=reversible` / `alternating` ways are built two-way.
  Evidence: code (`road_graphs.NetworkBuilder`). `graph_rebuild_Sep_29` L18-29.
- **GRF-3.** Cut to the largest strongly connected component, so every kept node can be reached and
  left by car and routing never needs a fallback. Sep 29 build: 2,523,400 nodes → 2,503,854 (19.5 k
  dropped, 0.77%; the weak component alone would have kept ~4.3 k one-way traps). Replaces the
  third-candidate fix floated for dead-end one-way stubs.
  Evidence: run printout only (`graph_rebuild_Sep_29` L35-36, L65-66); the reduced graph stamps both
  counts. DESIGN_pre_spine "Drive layer" (Graph); `drive_fallback_observation_Sep_23`.
- **GRF-4.** Candidates: per hex, the nearest road plus any other road within 1 m of it
  (`CANDIDATE_TIE_WINDOW_M`), at most 2, deduplicated by link (a chain of roads through degree-2
  nodes, so two pieces of one street are one candidate); motorway and motorway_link excluded; no
  distance cap (the 5 km cap was removed, user 2026-09-29). Both directions of a two-way road are one
  candidate.
  Evidence: code (`_nearest_roads_per_hex`, `_link_finder`). DESIGN_pre_spine "Drive layer"; `split_rebuild_Sep_22` L158-189.
- **GRF-5.** Split: each candidate road is cut into equal pieces of at most 50 m; both directions of a
  two-way road share the split nodes; new node ids start at 900,000,000,000; pieces must add up to the
  original length (checked). Fixed at source and re-split on 2026-09-22, replacing a split that put
  nodes on one direction only (~90% of old chains affected, pre-fix results superseded).
  Equal pieces rather than an exact node per hex, so nearby hexes share nodes and fewer shortest-path
  searches are needed (user, 2026-10-09); how often hexes share is not measured (HEX Notes hunch).
  Evidence: code (`_split_roads`, `_check_split`). `split_rebuild_Sep_22` L49-58, L104-113.
- **GRF-6.** Snap: each hex centroid is projected onto each candidate road and rounded to the nearest
  piece node (up to ~25 m along the road). A trip may start or end on node 1, or node 2 when its road
  is within 1 m and it is a different node (`drive_routing.eligible_nodes`, shared by the sampler,
  calibration routing and the pass). Default subject: 74,152 hexes store a node 2; 40,151 of them the
  same node as node 1; 34,001 (0.8%) have two eligible nodes. Both trip ends use the hex's node,
  venues included (a venue is reached at its hex's node; venue to centroid ≤ 50 m).
  Evidence: `hex_population_and_nodes` (checked 2026-10-13). DESIGN Q12 (tie window, 25 m → 1 m,
  user 2026-10-09); `probe_router_Sep_30` L20-23.
- **GRF-7.** Connectors are free: the straight line from the hex centroid to its road, and the on-road
  part up to the piece node, are not charged at either end. Google charges only the network segment:
  in a 4-call test, moving the origin ~110 m and ~130 m off-road changed Google's time and distance by
  exactly 0. The reachability pass uses the same convention (RCH-2).
  Evidence: manual tests, no file (`TEMP_workplan_Sep_22` L31-34; `connector_convention_Sep_21` L13-22).
- **GRF-8.** Snap distance (default subject, 4,078,906 hexes): median 317 m by hex, 20 m weighted by
  residents; p90 1,341 m, p99 5,202 m, max 11,191 m (far cluster probably forest or park SA1s,
  unverified). Beyond 300 m: 1.5% of residents, 3.0% of workers, 16 venues; beyond 1 km: 0.17%,
  0.40%, 1. These people reach the network at no cost (GRF-7).
  Evidence: `hex_population_and_nodes` (checked 2026-10-13); no diagnostic. `graph_rebuild_Sep_29` L96-101.

## Not adopted
- Patching the old split in place to keep node ids: replaced by a source fix and a full re-split. `split_rebuild_Sep_22` L104-105.
- Road-level candidate dedup: replaced by link-level. Merging parallel roads: both stay candidates. A 150° angle cut at junctions: an un-derived constant. `split_rebuild_Sep_22` L145-176.
- Charging connectors at walking or driving speed: Google doesn't, and the model is calibrated to Google. `connector_convention_Sep_21`.
- A third candidate road for one-way stubs: replaced by the strong component. DESIGN_pre_spine "Drive layer".
- A 5 km snap cap: filtering belongs at origin selection, not the graph. `graph_rebuild_Sep_29` L87-88.
- The 25 m candidate window: Google does not pick the most efficient entry (Q12); at 25 m, 643,127 hexes stored a node 2 routing never used. config `CANDIDATE_TIE_WINDOW_M`.
- A trimmed graph for the sampler's window routing: full-graph routing gave identical times on 540 pairs and was faster. `trim_check_and_sample_plan_Sep_30` L17-33.

## Limitations
- Connector straight lines ignore barriers (e.g. across Jacksons Creek) and their length is free; most matters for the 1.5% of residents and 3.0% of workers > 300 m from a road (GRF-8). `connector_convention_Sep_21` L40-41, L159-161.
- Up to ~25 m of on-road driving per trip end is free (rounding to a piece node). `split_rebuild_Sep_22` L193-194.
- OSM vs Google map inventory: on minor service roads they agree only about half the time, which caps start/end-road agreement at ~82-86% (Q12; seconds per trip).
- Google's trip ends are not ours: Google snaps the requested point (hex centroid or venue) to its own nearest road; our trip ends at the hex's piece node. Snap sensitivity is a noise source in Google's short trips, not removable by calibration. `TEMP_workplan_Sep_22` L35-39; ODS limitations.
- One DiGraph edge per node pair: a second way between the same two OSM nodes overwrites the first's attributes (not measured; expected rare).

## Notes
- Graph sizes are run printouts, not diagnostics (D1 gap): Sep 29 drive 2,523,400 nodes / 4,612,011
  edges, split 3,067,942 / 5,667,219 (274,058 roads split, before the 1 m window, which split fewer
  roads); walk 4,944,588 / 5,495,751. Older counts (2,213,723 walk nodes, 1,977 components, 41
  bridges) predate two rebuilds: never quote them. Re-derive from the stamped artefacts before quoting.
- Settled, not to be re-investigated: long straight edges are real arterials and pedestrian ways (Sep 21
  extent plots, `graph_extent_plots_Sep_21` L43-65); the Sep 23 one-way-stub hypothesis is moot (snapshot).
- The drive graph is the project's own work and is credited as such (DESIGN_pre_spine "Settled in chat").
- Lesson (Sep 21): bounds written in prose go stale when an extract is replaced; the per-artefact
  stamp (source PBF, build time) is the guard (RCH-5).

## Open questions
- DESIGN.md Q12 (snapping; a wider tie window is a possible later experiment).

## Changes
- Changes to 2026-10-20 (GRF-1 to GRF-8): snapshot, "Changes".
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
