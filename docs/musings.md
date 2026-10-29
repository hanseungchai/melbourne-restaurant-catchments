# Musings

Speculative ideas in PLATICA's scope, parked for possible extensions. Not current design, not proposals
under review. Deliberately not linked from INDEX.md or DESIGN.md, so agents don't load it by default. Out-of-scope studies: future_work.md.
Each entry: date, idea, why it might matter, what it needs, what would kill it, how we'd check.
Reviewed 2026-10-22 (user): entries promoted to framing.md (FRM-19, FRM-20, FRM-22, Limitations), future_work.md, or retired as covered (RCH-13, FRM-19, FRM-22); the full text is in git before that date.

---

## 2026-10-20 — Anchor path tree: who passes whom

**Status:** hunches from a musing thread at the desk (user); nothing built or tested. Extends FRM-19's
purchase journey scenarios (a showcase of applicability, not validity; loosened discipline, user).
Anecdotes are illustrations, never evidence.

**Idea (user).**
- Exposure on foot is sequential (user's story: a group heading for [subject] with low conviction passes a
  cheaper place, checks its Google rating, walks on; then switches on a whim to a cheaper, better-rated
  Mexican place). The order doesn't matter to the owner; the counts do.
- Strict rule (user): exposure only if the venue is *on the way*; any detour, no exposure.
- One anchor (e.g. a campus gate), shortest walking paths to the subject and to every competitor in the
  anchor's catchment. All paths from one origin form one tree, so one run answers both directions:
  - competitors beyond the subject on its branch: their customers walk past the subject (it can catch them);
  - competitors between the anchor and the subject: they can catch the subject's customers.
  "Passes" means the path goes past the venue's frontage, not that two paths share streets.
- The planned destination can be any venue the group would return from: a closer, roughly equal venue
  saves the walk both ways (substitute); a better one is superior.

**What it shows.**
- Closer to the anchor means fewer competitors in front and more behind: the old "first one they see"
  instinct falls out of the tree (face validity, not proof).
- Beyond commonsense: *which branch*. A venue near the anchor on a side street catches little; one on the
  main drag before a cluster of popular places catches a lot.
- Levers are a re-score, not a re-route: the tree doesn't depend on the subject's attributes, so price or
  menu changes only move which passing venues it beats. Which lever defends best depends on who stands in
  front (same-cuisine-and-cheaper: price; cheaper-but-lower-rated: already safe; better-rated: price
  won't save you). Reading of the story: price decides whether you get tested, reputation whether you
  survive it.
- The owner's instinct supplies the volume ("most students eat at that taqueria"); the tool supplies the
  geometry. No invented student counts: the honest unit is trips, not people.
- Anchors match the venue's crowd: campus gates, station exits (known precisely from the pathways work),
  theatres, hotels, schools. The census layer could suggest anchors (FRM-19 showcase, show feasibility).
  Office towers were dropped from FRM-19 (user, 2026-10-20, 35th): revisit at the desk if they return.
- Showcase anchor (user): Brunswick East Primary School gate, ~15 min walk from [subject]. Not [subject]'s market;
  the write-up says it was picked for the mechanics. Plausible story: family dinner or an after-pickup
  treat. The anchor is a setting, not code.

**Leanings (user, not decisions).**
- Cuisine tag dropped: what counts as interchangeable is unclear, and Google's type tags are coarse (a
  menu extension such as seafood or Mexican liquor doesn't change the tag).
- Price kept: clear, but sparse. User: fill missing price with the mode. Claude's caution: missing price
  is likely not random, and a mode fill ties exactly with a subject at the mode; fill by type and area,
  flag filled venues, report both bounds (treat as cheaper / dearer).
- Google's price level has four steps, so a 10% student discount is below its resolution; levers work in
  whole steps unless richer price data comes.
- Shopfront placement (pin on the building, not the frontage) is a limitation to live with (user).
- Later, if the demo gets interest: an enterprise Place Details call for the tree's competitors only (a
  few dozen; price range, service flags), and a local presence refresh (Text Search IDs only, Details on
  the differences only; a missing ID is not a closure). Paid: explicit go per session (S5). Belongs with
  the parked data top-ups (VEN-15), after the core outputs.

**What it needs.** A walk graph for one shortest-path run per anchor (our OSM walk network, not r5py),
plus one reverse run per competitor for the range below; venue prices (VEN-3 coverage check, owed).

**What would kill it.**
- Ties: where two streets are equally short, the path is a coin toss and decides exposure. Report "on
  the single shortest path" with "on any near-shortest path" (a segment is on one if dist(anchor, start)
  + length + dist(end, venue) <= shortest + slack); a wide gap is itself the finding.
- Real paths differ: R5's walks matched Google's on 0.338 (TRN-12). Phone-guided students walk Google's
  route; Google walking routes for a few hundred trips would be the sharper version (paid, its own go).
- Price coverage too low for the price lever (VEN-3).
- The substitute rules (rating margin, price step) are guesses at how people choose; the showcase shows
  how sensitive the lever answer is to them.

**How we'd check.** One anchor, the VEN-3 coverage check first, then the tree counts in both directions
and the single-path vs near-shortest range; read them against what the user knows of the street.

Outreach paragraph: covered by outreach.md and api-cost.md (API-9); text in git.

---

## 2026-10-20 — Why the 20-minute band is the sensitive one; frequency as the lever

**Status:** casual thoughts during the H-walk build (user's ideas unless marked Claude's). Not decisions.

**Idea.**
- The 20-minute band sits where transit starts to matter but alternatives (other routes, waiting
  options) are still few, so catching or missing one tram is decisive (user). At 30-40 min one missed
  vehicle is a smaller share; at 10 min most trips are walks.
- Transit-only pairs inside 10 min may be the most extreme (user). Exploratory look (Claude, session
  only, no script; model of record vs Google's k = 2 range, scored pairs): median relative error on
  transit defaults 12% at <= 10 min (n 46), 8% at 10-15, 5% at 15-20, 4% at 20-30, 3% at 30-40;
  walk-only defaults 0% at <= 10 (n 77). Absolute error flat (~1.2-1.5 min) to 25 min, then grows.
  Claude's reading: the 20 cut is sensitive because ~500 transit pairs sit within 5 min of it, so a
  1-2 min error or one missed headway (median 4 min) flips many calls; the 10 band is stable because
  walks dominate it.

**What it needs.** The scored tables (have). Frequency as a policy lever: future_work.md.

**What would kill it.** Relative error at the 20 cut no higher than elsewhere once pairs near the cut
are weighted.

**How we'd check.** A band-flip rate by distance to the cut, transit vs walk pairs.

---

## 2026-10-22 — Paths in aggregate: Google's walking shape, a tie-breaker, foot traffic as a bracket

**Status:** desk musing during the holdout routing (user's ideas unless marked Claude's). Not decisions. The
path-shape check below is planned for the next autonomous run (HANDOFF); results decide what gets promoted.
Run 2026-10-22 (69th): results and the user's call (walk-pattern matching dropped) promoted to TRN-12, FRM-20,
FRM-23; the tie-break and turn-cost ideas are answered there (Google is turn-averse, not straight-line; not worth it).

**Idea.**
- Foot traffic in aggregate, never per trip (user): overclaiming to model individual trips; in aggregate the
  picture is informative, with a disclaimer that errors are systematic and that weighted models were tried.
  Same-line routes 51% (1,754 / 3,448), other lines 40%, other mode 9% (TRN-16 leg trace): semi-misses still
  carry signal, since people also take the fastest path; complete misses say little. Claude: the edge-level
  number is the walk overlap, 0.338 at 100 m (TRN-12), lower than the route-level match.
- Google recommends, it does not observe (user): R5 (fastest) and Google (walk-averse, ~1.7x; TRN-16) are two
  plausible rules. Claude: report foot traffic as a bracket, w = 1.0 and w = 1.7; where they agree the picture is
  robust, where they differ is the stated uncertainty. The walk-weight re-rank (default match 0.720 -> 0.853 on
  training, `transit_walk_weight.py`) was not adopted for time but may suit paths; route match need not lift
  street overlap. R5 walks 1.50x Google's metres (TRN-12): the bias in totals can be sized.
- Grid ties (user): on a street grid many equal-length paths exist; Google keeps a "middle" pattern, roughly along
  the straight line, neither the fewest turns (one L) nor a zigzag (user's experience, illustration). Claude's
  candidate causes: ties broken toward the straight line (A*-like), a main-road preference (arterials several
  blocks apart), or both. Walk-only pairs already fit tie-breaking: lengths agree yet overlap ~0.5 at 100 m,
  Hausdorff 90-260 m (TRN-12).
- Fix routes (Claude, after the user's synthetic-edge idea: a slight bonus on merged straight runs): that is a
  turn penalty in disguise, O(n^2) edges per street. R5's street search is edge-based and already has a turn hook,
  `BasicTraversalTimeCalculator.turnTimeSeconds`, cars only, walk returns 0: a small source patch (whole seconds,
  so 1 s per turn at least). But a turn penalty pushes toward the L, the extreme the user says Google avoids; a
  tie-break toward the straight line or a main-road discount fits the "middle" better. Paths only: a separate jar,
  never the frozen time model.
- Earlier leanings carried from the 2026-10-14 entry (retired): the claim is "assuming people follow recommended
  routes"; walk and transit access legs only; station exits are the most reliable part; frontage by distance to
  high-flow segments (Places pins may be coarse); a pedestrian-counter test (City of Melbourne, CBD) before building.

**What it needs.** Saved geometry only: `transit_walk_overlap_20261018_r5_walks.csv` (2,831 R5 walk legs, training
half) and Google's walking cut from its polylines (same diagnostic); OSM road classes for the main-road share.

**What would kill it.** Google's walks clearly longer than R5's on the same legs (a real preference, not ties) with
no road-class pattern; or overlap still low at block and hex scale, so aggregation does not rescue it.

**How we'd check.** On legs where R5 and Google differ: turns over 27 deg (R5's straight-on threshold) placed between
the fewest and most possible; mean and max distance from the straight line; length ratio; overlap at ~150-200 m and
hex scale; then the main-road share from OSM. Walk-only and transit walk legs reported apart. Report only, no
pass/fail.

## 2026-10-22 — Timetables as policy: does transit shape a city's hours?

**Status:** a passing thought from the user during the 71st autonomous run; nothing built. Anecdotes are
illustrations, never evidence.

**Idea (user).** In Shanghai and Seoul (user's experience) transit is less sparse early and late than Melbourne's.
Melbourne has a looser work culture and shops close early (penalty rates make late hours costly). Maybe transit
timetables are part of the policy mix that shapes work and life conventions, not only a response to them.
- Claude: likely both directions: operators schedule to demand, early closing lowers evening demand, thin evening
  service makes late outings harder, which keeps demand low. Touches RCH-20 / DESIGN Q25: the subject's dinner hours
  sit where Melbourne's service falls from 0.66 to 0.23 of peak (`gtfs_service_profile.py`), which is why weekday
  evenings cluster with the weekend, not the working day.

**Why it might matter.** Framing only: evening transit catchments are a city-specific constraint on dinner venues;
a comparison would say how much of an evening catchment gap is timetable.

**What it needs.** GTFS feeds of other cities (public), the same service profile per hour; for causation, far more
(policy history, labour rules): out of scope.

**What would kill it.** Comparable cities with equally thin evening service and late-trading cultures.

**How we'd check.** Run the service profile on two or three other cities' feeds and compare the evening share of
peak; descriptive only.

## 2026-10-22 — Transit reliability, disability and who an "improvement" helps

**Status:** musing threads from the user during the 76th autonomous run; nothing built or tested. Anecdotes are
illustrations, never evidence. Touches RCH-7 (R̄), RCH-26, transit.md Limitations (timetable optimism, decided as a
disclaimer the same day).

**Ideas.**
- R̄ from the oracle instead of routing (user; user leaned no, Claude agreed): the oracle's errors all lean one way
  (zero waits, fastest trip, free link) and lean most where service is sparse, so they add up rather than cancel;
  a silent, place-dependent bias in the yardstick. Claude's alternative: oracle as a control variate for the routed
  venue sample (R̄ = mean oracle over all venues + mean(R5 - oracle) on the routed sample): unbiased, maybe fewer
  routed venues. Only if Q26's sample size hurts.
- Disruption simulation (user): incidents block a corridor, agents re-route or wait for late trams. Needs historical
  incident and vehicle-position data, likely not public (PTV's real-time feed is live; archiving would start now).
  Cheapest first step if data appears: a per-corridor penalty on tram segments scaled by incident rates.
- Disruptions cost disabled people more (user): recovery means walking to another stop or line; reachable
  alternatives grow with the square of walk radius and shrink to step-free stops, so a slower walker keeps a
  fraction of the network's slack. Redundancy is designed for the average walker.
- Positional disadvantage (user): a policy that raises average reach but excludes a group (inaccessible buses)
  widens the gap; judged comparatively (an employer), the excluded group ends worse off, and the adaptation (not
  relying on trams) reads as poor commitment. A mean (R̄ is one) hides it; report the gap beside the average.
- Paratransit / subsidised taxis (user): cost-inefficient by average benefit, justified by the gap. In a model:
  another mode for eligible people, near the drive model plus booking lead time.

**Why it might matter.** Framing of transit reach (optimistic, unevenly so) and a possible accessibility layer
whose output is a gap, not an average.

**What it needs.** GTFS `wheelchair_boarding` per stop (check whether PTV fills it), a slower walk speed, line
redundancy counts within a walk budget; incident data for anything about disruption.

**What would kill it.** `wheelchair_boarding` empty or unreliable in PTV's feed; redundancy differences too small to
show at hex scale.

**How we'd check.** Per origin hex: distinct lines reachable within a walk budget at able-bodied speed vs step-free
stops at a slower speed; map the ratio. Check the GTFS field first; verify Victoria's taxi subsidy programme and
current punctuality figures before citing either.

## 2026-10-22 — Disability reach gap: walk baseline, then transit, then each addition

**Status:** musing from the user while the 77th session waited on a run; nothing built or tested. Extends the entry
above (disability and redundancy, positional disadvantage). Touches RCH-7 (R̄, a mean that hides gaps), TRN-6 (walk
legs), transit.md Limitations.

**Ideas.**
- Policy ladder (user): (1) walk only, no transit: reach within 30 min for an able-bodied walker vs a mobility-
  impaired one (slower speed, typical age); the gap is the "default state". (2) Add transit, with the agent barred
  from what it can't use (a tram or stop without step-free access is removed for the impaired agent only). (3) Add
  later transit (new lines, upgrades) step by step: does each narrow the gap or widen it? User leans: transit narrows
  it at step (2); open whether later additions keep narrowing it.
- The answer depends on the gap measure (Claude's): ratio (impaired reach / able reach) and difference (able minus
  impaired, in persons or venues) can move opposite ways. Transit that lifts both groups can shrink the ratio gap and
  still widen the absolute one. Report both, or pre-register one before looking.
- Why the walk gap is large and transit could shrink it (Claude's hunch): walk-only reach is roughly area, so it
  scales with speed squared (0.8 x speed gives ~0.64 x the area); with transit, walking is only the access and egress
  legs, so speed matters less, if stops near the origin are step-free. If they aren't, the impaired agent's nearest
  usable stop moves away and the gap can widen instead: step-free stop density is the swing factor.
- Both ends must be step-free (Claude's): boarding stop, vehicle (trip-level `wheelchair_accessible`) and alighting
  stop; a step-free route with one inaccessible transfer is unusable. Boarding time penalty (bus ramp deployment) and a
  longer transfer charge than the frozen model's 200 s are plausible extras.
- Step (3) via history (Claude's): successive GTFS releases (or PTV's level-access stop rollout dates) as natural
  increments, instead of invented lines; the order additions arrive in changes each one's marginal effect, so
  history avoids picking an order.
- Network history from opening dates (user): GTFS archives don't reach far back, but line and extension opening
  years are public; peel today's feed back by removing lines opened after year Y. A rough idea only: today's
  frequencies, crowding and fleet stay in. Claude's notes: it answers "what did each addition do for today's people
  and venues" (population held fixed), a clean attribution rather than a reconstruction; closed lines (absent from
  today's feed) can't be put back; Melbourne's rail and tram lines are mostly old, so few line openings fall in any
  window where access standards existed; the access timeline (low-floor fleet, level-access stops, station lifts) may
  move the gap more than new lines. Two timelines, crossed: lines opened x access upgrades. Dates to verify.
- Footpaths matter too (Claude's): kerb ramps, steps and slope (OSM `kerb`, `incline`, `highway=steps`) bar or slow
  the impaired walk; OSM coverage is likely patchy, so a speed-only model flatters the impaired reach.

**Why it might matter.** Turns "transit improves access" into who it improves it for, a gap with a direction; fits the
positional-disadvantage thread (report the gap beside R̄).

**What it needs.** An impaired walk speed (and maybe age profile) from the literature; GTFS `wheelchair_boarding`
(stops) and `wheelchair_accessible` (trips) filled in PTV's feed; R5 can drop trips and stops per run (a filtered GTFS
copy per agent, unique file names: r5py caches by name); persons per hex (have); older GTFS releases for step (3)
(have two recent ones only). User expects ample public evidence on line openings and access upgrades if the direction is pursued (not looked for yet); gaps could be filled by a data request to PTV or the operators, given institutional backing.

**What would kill it.** Wheelchair fields empty or mostly "unknown" in PTV's feed; no ground truth for impaired travel
times (our fit target, Google, routes able-bodied agents; check whether Google offers a wheelchair-accessible transit
option at all before assuming it does); older GTFS releases unobtainable, which kills step (3) but not (1)-(2).

**Checked (77th, `inputs/gtfs_ptv_20261018`, counts only).** Train: stops `wheelchair_boarding` filled (1739
accessible, 11 not; blanks are station nodes), every trip accessible, and full station interiors in `pathways.txt`
(3838 links: walkways, 454 stairs, 299 lifts, 120 escalators, gates, with traversal times). Tram: every stop 0 (no
information, so level-access stops are not in the feed), trips split 16.5k accessible (low-floor) / 20.9k not. Bus:
every stop 0, trips 99.4% accessible. So trams, the mode the question turns on, need stop access from another source
(PTV or Yarra Trams level-access lists; to find); whether R5 reads `pathways.txt` is unchecked.

**How we'd check.** Then
for a few origin hexes: 30-min reach in persons for walk at two speeds, then walk + full transit vs walk + step-free
transit at the slower speed; ratio and difference side by side. Verify the impaired walk speed and PTV's level-access
figures from sources before citing either.

## 2026-10-22 — Rural vs urban: how much does the car equalise?

**Status:** musing from the user in the 77th session, same vein as the disability gap entry above; nothing built or
looked up. Touches RCH-7 (R̄), the drive model (fit in metro Melbourne), transit.md Limitations.

**Ideas.**
- The question (user): many rural communities can't live without cars, so anti-car arguments made on climate grounds
  can ring hollow there. Compare reach for rural vs urban residents by public transport only, then with a car: how much
  of the gap does the car close?
- Same machinery as the disability gap (Claude's): reach ratio and difference, walk + transit vs drive, per place
  type; report both measures.
- Destinations, not persons (Claude's): rural reach measured in persons reachable mostly measures emptiness; the
  sharper yardstick is essential destinations (supermarket, GP, pharmacy, school, hospital) within a time budget,
  and the time to the nearest one. Our venue data (restaurants, metro Places pulls) doesn't serve that; OSM POIs
  might.
- Hunch (Claude's): the car may close most of the gap to the nearest essential service but not the gap in choice
  (how many supermarkets within 30 min); urban walk + transit may beat rural driving on choice.
- Non-drivers (Claude's, links to the disability entry): the car equalises only for those who can drive and afford
  one. Rural non-drivers (young, elderly, disabled, low income) are the group where the gap is widest; the
  car-equalised average hides them, the same positional point as before.
- Cheap first look inside our scope (Claude's): a gradient within metro Melbourne (inner vs outer growth suburbs),
  using the data we have, before going rural at all.

**Why it might matter.** Puts numbers on a political argument (car dependence is structural, not a preference) and
on who is left out when the car is the equaliser.

**What it needs.** Regional GTFS (V/Line, regional buses; out of current scope, flagged earlier for Geelong); a drive
model valid on rural roads (ours is fit to Google in metro); essential-destination POIs; census rurality classes
(ABS remoteness areas) and car ownership by area (census has it).

**What would kill it.** Rural timetables too sparse to route meaningfully (still a finding: reach ~ walk only);
destination data too patchy outside metro; the drive model's metro fit not transferring (could be checked against a
small Google sample, paid, only if asked).

**How we'd check.** Start with the metro gradient: for a handful of inner and outer origin hexes, walk + transit vs
drive reach in venues, ratio and difference. Then one regional town with its own feed, if the regional GTFS exists.

## 2026-10-23 — Allies at a comfortable distance; q as search

**Status:** hunches from the 87th discussion (user's ideas, Claude's additions marked); nothing built or tested.
Anecdotes (grand strategy games, the Taiwanese / Japanese restaurant moment) are illustrations, never evidence.

**Idea (user).**
- Allies' sweet spot: "if you're a similar business and not a complementary one, the comfortable distance you want
  with your allies is far enough to not be a threat, but close enough to be useful." Next door = rival on every
  diner; far = nothing to trade; middle = each reaches people the other doesn't, with a shared strip between.
- Complementary pairs (a bar beside a kitchen, [subject]'s neighbour) don't follow the distance rule the same way.
- q as how diners search: groceries get picked top or nearest; restaurants depend on past experience, preference,
  whether tried before, so people scroll until something vaguely clicks and then latch on ("actually I do feel
  Japanese"). Behind the user's 0.8 (SCR-16).

**Claude's additions.**
- In model terms an ally has low denial of the subject (SCR-14), a large reach the subject lacks, and a non-empty
  shared border. An "allies" list could sit beside the rivals list, read from the same draws.
- The type pairing may matter more than distance; the sweet spot is a curve per pairing, not one curve.
- Challenge (from memory, unchecked): agglomeration; clusters can draw more diners than venues alone, so next door
  can mean a bigger pie, not only a split one.
- Secretary problem (user's link) fits poorly: Google's list is sorted and going back is free, so it predicts q ~ 0.
  Closer: search with a cost per look (Weitzman's Pandora's box) and satisficing (Simon): q is high when tastes vary
  and looking is cheap; in a cascade q ≈ the chance an option doesn't click (scoring.md Notes, plain-words q).
  Preferences may form on seeing the option, so the list shapes what diners want.

**Why it might matter.** Turns the competitor display from "who hurts you" into "who could carry you further";
gives the owner a plain meaning for q.

**What it needs.** A partner's reach beyond the subject's catchment: drive pass covers every hex (hunch: readable
from saved data, unchecked); transit needs a pass per candidate partner (~4.5 h each, hybrid).

**What would kill it.** Owners having no realistic way to collaborate with a venue 2 km away (a curiosity, not a
feature); allies indistinguishable from "venues far enough to be irrelevant".

**How we'd check.** On the drive band, for the subject: each venue's overlap with the subject's catchment
(person-weighted), its denial, and its unique reach; see whether a middle group stands out at all.

## 2026-10-26 — Knees, leagues and the owner's picture

**Status:** hunches from the 112th (user at the desk while the staged run went; Claude's additions marked);
readings from band 1 only (the 110th's staged run vs q's run of record). Sports analogies are illustrations, never
evidence.

**Idea (user).**
- Band 1 under staged best-of-K: a higher rating pays little in absolute terms because the pool is small (786 per
  open slot at 4.8 vs q's 1,270; the slider a ramp, x11 from 3.5 to 5.0, q x560).
- Knees: relative advantage starts to matter once a venue clears the average (~4.2: "faster than the average
  sprinter"); the second milestone is the top of whatever pool you meet ("wins amateur tournaments comfortably").
  Finding the knees was the project's original value proposition: between two knees a step may not pay; just
  above one, a nudge back costs a lot.
- Bands as leagues: band 1 amateur, band 2 minor, band 3 major. Is the major league's prize worth it? Band 3 looks
  big, but how many of its residents have a car?
- The owner's picture: gain (the slider steps per band), difficulty (the rarity line, SCR-22: "1 in N among your
  review-count peers"), risk (the step back). Recommendations allowed, as one well-supported argument among
  several, never the answer; the decision is the owner's.
- Density (user, then the user's own counter): in a dense area search is cheaper and passive exposure larger; but
  attention is limited, exposure is not consideration, and comparing ratings needs looking each venue up. Kept a =
  0 (recorded in SCR-23 Notes 112th); density-scaled search to future work.

**Claude's additions.**
- Knee positions come from where rivals sit, heights from k: at k 2.5 / 3.33 / 5 the ramp starts at 4.2 -> 4.3 and
  the biggest step is 4.8 -> 4.9 (+204 / +374 / +764), so positions can be shown without knowing k.
- Each search is a heat of ~k venues; a venue beating a share p of rivals wins a heat with chance ~p^(k-1): flat
  below the median, steepest near the top. The two milestones are what a heat model predicts.
- Under best-of-K the best venue's prize per hex is ~k / M of it: a crowded field dilutes even the best (q gave the
  top a fixed 1 - q of each hex). A CBD's bigger pool may not mean a bigger prize per step.
- The first knee sits near C = 4.24, the shrinkage prior's centre, where low-review rivals pile up: market or prior?
- Density may shape which venues get looked up (an exposure-weighted encounter, Q32's unbuilt variant), not how many.

**Why it might matter.** Knees per band, with the distance to the next one and the drop below, is a product an
owner can act on, and it is robust to the unknown k.

**What it needs.** Bands 2-3 under staged best-of-K (the run, owed); rival counts per key tenth; census car access
by SA2 for band 3 (a weighting, the user's decision); a CBD subject for the density question (~8 h pass, free).

**What would kill it.** Knees that are artefacts of the shrinkage prior (they vanish among well-reviewed rivals);
band 2's knees not matching band 1's; steps so flat everywhere that no knee stands out.

**How we'd check.** Per band: step gains at each k mark; rivals per tenth of key, persons-weighted, split into
well-reviewed and pulled-toward-C; band 3 with and without car weighting.

## 2026-10-29 — Spin-off: El paso (slow walkers vs Google's default pace)

**Status:** discussion in the 123rd (user, on a break from PLATICA); a separate project, not a PLATICA extension.
Scoping note at a separate project (not public). Builds on the
2026-10-22 entries "Transit reliability, disability and who an "improvement" helps" and "Disability reach gap".

**Idea (user).** Take Google's default time as the assumed walker's (PLATICA's fit: 4.143 km/h, WLK); compare slow
walkers (age, need for assistance; speeds from the literature, stairs as a swept scalar, boarding the same) across
destination scenarios (pharmacy / GP, hospital, school, a friend's home, work via place-of-work tables). A plain
area-level OLS (SA2) of the access gap on age, assistance, Indigenous status, English, car access and one
socioeconomic measure. Aims: capability, interest, research discipline; replication is fine, novelty not needed.
User's reading: more defensible than PLATICA (one assumption, literature-anchored parameters).

**What it needs from PLATICA.** Copies (not links) of the R5 setup and patches, GTFS handling, census and hex code,
and the walk / transit validation diagnostics. Owed check (Claude): which PLATICA diagnostics show walk speed's
outsized effect on transit times, before the scoping note cites it.
