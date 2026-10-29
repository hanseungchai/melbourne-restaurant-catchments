# Walk

**Purpose and scope.** Walking speed, how walking time is charged, and the project's own walk graph.
Not the bands 1-2 routing itself (r5py network, GTFS, transit timing: `transit.md`), nor the drive
graph (`graph.md`).
**Stages.** `map_construction` (walk graph); walk-speed fit (no stage yet; waits on the r5py rebuild).
**Last reviewed.** 2026-10-13, 9752c8f
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/walk.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **WLK-1.** Walking speed 4.16 km/h (`WALK_SPEED_KMH`; user, 2026-10-17) for walk-only bands and for
  walking inside transit: the median of R5 walk-only path / Google walk-only time on the 217 training pairs
  with a Google walk-only route. R5's walk-only path is Google's length (median 0.99), so effective ≈ pure
  speed (Google's own 4.24); chosen over 4.2 (the lead: Google's measured walk speed, Notes) as fitted to
  R5's paths, < 1% apart. R5's access walk to stops (1.14x Google's) and its 60 s board slack stay
  separate biases (T7 e, T7 g in transit.md). Caveat: R5 adds ~26 s per walk-only trip beyond path / speed
  (intercept fit 4.21 km/h + 25 s); cause found 2026-10-21: per-edge ceil, 0.48 s per edge (TRN-16; patch P4 not
  adopted for now). Model of record's speed: 4.143 km/h, Q24 (2) median (user, 2026-10-21, final). The transit draw (TRN-10) and reserve ran at r5py's 3.6 km/h and stand
  (negligible for the 40-min window); the checkpoint guard includes the speed. Replaces the legacy 4.077.
  How it was reached (the lead, the 4.2 / 5.0 tests, the matched-leg design it superseded): snapshot.
  Evidence: `diagnostics/walk_only_speed_fit.py`; lead `transit_walk_speed_lead.py`, `transit_router_egress.py`. Open: DESIGN.md Q7. Closed Q3 (user, 2026-10-09).
- **WLK-2.** The fitted speed is passed into R5; walk legs are not recomputed afterwards, because R5
  chooses paths and vehicles with its own walk speed. R5 walking is distance / constant speed with no
  elevation, the same form as the project's walk model.
  Evidence: none (R5 behaviour taken from its documentation, not checked). `time_resolution_Sep_21` L71-77.
- **WLK-3.** Google's view: the walk from a point to the street (connector) is not charged. Before
  fitting, check whether R5 charges it. **Checked 2026-10-20: R5 charges it**, at both ends at walk
  speed: its walk search starts with the along-edge part plus the off-street distance (every one of 3,267
  pairs); the destination's link is charged by TTM. Median off-street 8.1 m at each end. Whether to drop it
  in the model: DESIGN Q24 (plan, user 2026-10-21). Dropped inside R5 by patch P2 (TRN-16; adopted 2026-10-21).
  Evidence: `diagnostics/transit_access_walk.py` (run 1 check, run 2). DESIGN "What the project is";
  DESIGN_pre_spine "Walk and transit layer".
- **WLK-4.** Google's displayed walk durations round to the nearest minute (10 of 10 sampled pairs;
  round-up and round-down each fail 5). This explains "a 50 m walk shows 1 min" (~40 s rounds to 1);
  there is no minimum-one-minute rule. API seconds match the web display. The rounding is display only:
  the Routes API returns seconds (TRN-8 smoke test, 2026-10-16); the outputs round as displayed (SCR-10).
  Evidence: `od_walk_with_eta.csv` (10 pairs, 21 Sep); no diagnostic (D1 gap). `time_resolution_Sep_21` L7-19.
- **WLK-5.** The project's own walk graph is not in use: superseded by r5py, not found wanting. Kept
  as a keepsake and a possible robustness check of the r5py speed; the code that built it survives in
  git, and the speed fit on it is parked in `docs/parked_code/walk_speed_calibration.md`. `construct_graph` is drive-only: its walk branches (reduce, split, hex → walk node) are retired.
  Evidence: none. User, 2026-10-13; DESIGN_pre_spine "Walk and transit layer"; `graph_rebuild_Sep_29` §4.
  Code still differs: see W3.
- **WLK-6.** Access walk to the first stop (H-walk, measured 2026-10-20; a finding, no position change): R5's
  walk to Google's first boarding stop is a median 1.055x Google's first walk (95% 1.050-1.060, 3,171 pairs;
  train 1.060, tram 1.072, bus 1.038), +17 s median at 4.16 km/h, 16% of pairs > 60 s longer. Most of the
  street-stop excess is the connector (WLK-3; without it 1.020). Linked to late misses: late pairs 1.109 vs
  agreeing 1.058 (difference +0.051, CI +0.030 to +0.075); 31% of late pairs > 60 s longer vs 15%. Dropping
  the connector at both ends alone (4.16 km/h): hard misses 30 -> 32, late 450 -> 365, early 1,867 -> 2,081
  (the model leans early), walk-only mean error +0.05 -> -0.19 min (median 0). Small on average, decisive
  at a knife-edge boarding. Next: DESIGN Q24. Rules: Claude's additions (docstring), approved by the user 2026-10-21.
  Evidence: `diagnostics/transit_access_walk.py`.

## Not adopted
- Own walk graph as the speed-calibration network: r5py walk-only chosen so the speed matches the network that scores. DESIGN Q3.
- Round-up or round-down as Google's display rule: each fails 5 of 10 pairs. `time_resolution_Sep_21` L13-14.
- Walk bands in metres: bands are in seconds (graph cost), accepting that peripheral competitor sets shrink. rev4 L213-215.
- Gap cap or exclusion set to fix walk fragments; stitching beyond the 41 drive-oracle bridges: fragments conceded. `STALE_handover_rev3_16_delta` L151-172.

## Limitations
- Walk-fragment concession (old walk graph): beyond 300 m of a walk node lay 0.09% of residents, 0.77% of workers and 5 restaurants. Moot for bands 1-2 once r5py scores them; kept for the record. rev4 L1400-1405.

## Notes
- The walk graph was very good; it was superseded by the r5py plans, not by a flaw. (user, 2026-10-13)
- Legacy calibration on the own walk graph (~Sep 21: 1.1325 m/s, later 4.074 km/h) and the old
  `walk_dist_m` access item (now WLK-3): snapshot, Notes.
- Walk barrier cases: 5 Google pairs with routed/straight-line ratio > 3 (worst 6.8×, 1,873 m straight,
  12,657 m walked, near Maribyrnong). A ready test set for whether a walk network has the same barriers.
  rev4 L1275-1279.
- The 600-700 m walk/transit switchover is a spatial measurement worth reporting. rev4 L40-41.
- Google's walk-only alternatives in the TRN-8 smoke test (2026-10-16, n = 3): 4.03, 4.14, 4.20 km/h
  (route distance / duration), in line with the legacy 4.07. Musing (user, not adopted): Google may
  absorb crossings and lights into a slower average speed; testable on legacy residuals against
  crossings per km, walks over 10 min. Not worth reopening walk routing.
- Google's walk speed in the 2026-10-17 transit fetch (free, stored answers; default route's walk
  distance / walk time, steps with a distance only): 4.21 km/h median on 2,283 transit routes with
  >= 300 m of walk (p10 3.86, p90 4.55), 4.24 on 105 walk-only routes (3.94-4.50). Google states
  5 km/h publicly; its answers walk at ~4.2. Computed in session (no script kept); the WLK-1 lead.
- Untested display cases: a walk under 30 s showing 0, and a remainder of exactly 30 s (judged irrelevant
  at project scales). `time_resolution_Sep_21` L16-18.

## Open questions
- DESIGN.md Q7 (r5py rebuild).
- ~~**W3 (code).**~~ Closed 2026-10-13: walk graph build parked (`docs/parked_code/walk_graph.md`);
  `pt_stop_walk_access` still reads the walk graph built 2026-10-09, left in place.

## Changes
- Changes to 2026-10-20 (WLK-1 to WLK-5): snapshot, "Changes".
- 2026-10-21 · WLK-3 checked (R5 charges the connector, both ends); WLK-6 added (H-walk access-walk finding); plan in DESIGN Q24
- 2026-10-21 · WLK-6 H-walk readings approved by the user (65th)
- 2026-10-21 · WLK-3: connector dropped inside R5 by P2 (TRN-16, adopted)
- 2026-10-21 · WLK-1: ~26 s caveat explained (per-edge ceil, TRN-16); 4.143 km/h median final (user)
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
