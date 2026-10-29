# Framing and audiences

**Purpose and scope.** What the project is, what it claims and doesn't, who it is for, and the framing
commitments the write-up must keep. Not the scoring rule (`scoring.md`), outputs (`reachability.md`)
or any model's limitations (each concept doc), nor who to approach and how (`outreach.md`).
**Stages.** None directly; governs every stage's write-up.
**Last reviewed.** 2026-10-12, 18b261d
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/framing.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **FRM-1.** PLATICA is a geospatial model of the competitive value of reputation for urban
  restaurants. Subject: [subject] Brunswick East (`-37.7687014, 144.9719611`, hex 0).
  Evidence: none (definition). rev4 L60-61; DESIGN "What the project is".
- **FRM-2.** Causal chain: reputation → platform visibility → competitive advantage. Food quality is
  deliberately outside it.
  Evidence: none (definition). rev4 L60-63.
- **FRM-3.** Core framing: "Spatial elements set the grounds and the rules; reputation is the game."
  Neither half is interesting alone. That is about research novelty; for use (studying Melbourne, a
  business decision), the catchment model stands on its own (user, 2026-10-14).
  Evidence: none (framing). rev4 L33-36.
- **FRM-4.** Presentation order: the multi-modal catchment model leads as the contribution;
  reputational competition is the worked application and is not demoted to an example (it turns a
  routing exercise into a competition model). The catchment model is the stronger, reusable part;
  the reputation application still gets finished.
  Evidence: none (framing). rev4 L38-49; DESIGN_pre_spine "Settled in chat" (Framing and credit).
- **FRM-5.** The unvalidated conversion from reputation to advantage ("arrow 2": tier threshold, m,
  fill order) sits in the application section, never under the headline.
  Evidence: none (structural choice). rev4 L46-48.
- **FRM-6.** Purpose, stated modestly: the model says what is available to an operator and what each
  lever is worth (rating, mode, siting), not what will happen. "A 20-minute drive reaches N people"
  needs no validated arrow. Prep time is not a lever in the model: it is one only under the delivery
  reading, dropped because delivery has no link to the platform studied (Google). Kept as a note (Notes).
  Evidence: none (framing). rev4 L51-56, L294-300; `hex_block_Sep_27` L184-185. Settled by the user 2026-10-12.
- **FRM-7.** Google's view, throughout. "Reputation" = Google's displayed rating and review count only
  (a platform artefact with its own solicitation dynamics and display precision, not reputation in
  general). "Reachability" = travel time as Google presents it, not real-world travel. The write-up
  states both definitions outright.
  Evidence: none (user definition). rev4 L65-67; `fractional_hexes_Sep_29` L7, L11.
- **FRM-8.** The competitor set is venues Google tags as restaurant, not what businesses actually are;
  the write-up says so rather than claim "restaurants".
  Evidence: none (definition). DESIGN_pre_spine "Settled in chat" (Reachability and scoring).
- **FRM-9.** The tool doesn't give owners answers. It shows where a venue stands on ratings against
  competitors and how many potential customers that comparison reaches; owners get the curve over
  N, not a single-N answer (owner instinct is where the bias lives).
  Evidence: none (framing). DESIGN_pre_spine "Settled in chat"; `ideas_textsearch_relevance_Sep_24` L108-111.
- **FRM-10.** Audiences: academics (methodology, spatial extent of reputation); data analysts
  (portfolio; the rejection list shows judgement); small business owners and franchisees
  (cannibalisation, siting).
  Evidence: none. rev4 L72-74.
- **FRM-11.** The contribution is conceptual, not empirical. Luca (2011) measures ownership with brand
  recognition as the mechanism; the two diverge for small local operators.
  Evidence: none (literature reading). rev4 L1442-1453.
- **FRM-12.** Predictions are written down before scoring output is seen. Anecdotes (e.g. Melbourne
  Central) are explicitly not evidence.
  Evidence: none (process commitment). rev4 L1480-1489.
- **FRM-13.** Credit: the drive graph is the project's own work and is credited as such; the r5py pivot
  for transit was partly practical (PT was the persistent sore spot). The walk graph: see Notes.
  Evidence: none. DESIGN_pre_spine "Settled in chat" (Framing and credit).
- **FRM-14.** Scope is discovery: the model covers people who search Google to find a place, not
  walk-ins, bar hopping or food-court browsing. The write-up says so up front.
  Evidence: none (scope definition). `outreach` L29. (user, Oct 10)
- **FRM-15.** The model isn't neutral, and the write-up leads with that: here is what it assumes
  (nearby venues are rivals, only the top N count, Google's tags define the set), here is what it
  shows, the reader decides whether the assumptions fit.
  Evidence: none (framing). `outreach` L30. (user, Oct 10)
- **FRM-16.** No claim that Google *forms* people's expectations; the project doesn't test that. Say
  "what the platform shows people" and leave the behavioural link open (researchers with real travel
  data could measure how far Google's estimates diverge from actual travel).
  Evidence: none (framing). `outreach` L24. (user, Oct 7)
- **FRM-17.** AI disclosure is specific: what was the author's own design and judgement, what AI
  implemented, where AI challenged and where the author overruled it. Every stage defensible live.
  Evidence: none (process commitment). `outreach` L26. (user, Oct 7)
- **FRM-18.** The model is an attempt, likely not an accurate representation of reality. Every
  presentation, to any audience, states this before the results; questions from academics are
  answered limitations first. When a reader gets excited about a result, remind them what it assumes:
  visibility unconfirmed (DESIGN.md Q19), Top-N all-or-nothing (`scoring.md` Limitations), the
  reputation rule (rating to advantage) unvalidated (FRM-5). Wording: "an attempt to show what each
  lever could be worth", never "what will happen".
  Evidence: none (framing). (user, 2026-10-13)

- **FRM-19.** Population scope (user, 2026-10-14): the core is residents and workers, each its own
  denominator (CEN-1). Commuters passing by are the only candidate third layer ("at most"). Tourists,
  shoppers and other trip attractors, and students are future work, named in the write-up as
  limitations and future applications, not built. Why: each extra population brings its own score and
  levers, and too many blur the core idea; the extensions reuse the core method with new population
  data. The write-up and literature review start after the core.
  Commuter detour layer revised 2026-10-20 (user): a time-only detour (o->v + v->d minus o->d) needs only
  the time check, which passes; no path test. Gates left: the residence x place-of-work cross-tab's 41k
  gap, RCH-19's 30-min cap, and detours amplifying time error. Framing rule (user, 2026-10-18): detour
  bands are not a stand-in for foot traffic, said unambiguously (FRM-20).
  Presentation, three parts (decided 2026-10-22, user; Claude's structure): ordered by the assumptions each adds,
  confidence falling and potential rising, each part's disclaimer growing to match (FRM-18), never treated as
  peers. (1) The measurement: workers and residents, two denominators side by side, never blended (demographics,
  FRM-22, hang here). (2) Applications with no new assumption (reruns of part 1): counterfactuals (SCR-6),
  cannibalisation. (3) Showcase, people on the move: detour (times, which the model is validated on), foot
  traffic (paths, which it is not: TRN-12), anchor (one illustrative setting, FRM-23). Option: part 3 as a
  separate applications companion. Detour design (user, from musings 2026-10-14/16; leanings, in scope): bands of detour tolerance by
  mode, drive 5 / 10 min (no tight band; stops planned, not whims), walk 3 / 5 min, transit only at boarding,
  alighting and transfer stops; detour via v = t(o->v) + t(v->d) - t(o->d), three matrix lookups; framed as
  detour cost, never traffic or uptake (no stop-propensity weight); hexes at the trip ends duplicate the fixed
  layers (a weighting question, not an automatic exclusion). Detours difference two times, so random error does
  not cancel: short-trip time accuracy is the check.
  Checked 2026-10-22 (report only, Claude's rule: band supportable if detour noise SD <= half the band): drive
  (2tier test half) 10 min band supportable for legs up to ~15 min (SD 2.5-4.2 min), 5 min marginal, long legs (15,
  15, 25) ~5.4 min; transit (10, 10, 15) ~3.5 min: 3 min band mostly noise, 5 min marginal; walk short legs within
  1 min on ~90%. Shared-end error correlation small (ICC 0.05-0.10). `drive_detour_error_scope.py`,
  `detour_error_scope.py`.
  Split 2026-10-20 (user): foot traffic FRM-20, census years FRM-21, demographic showcase FRM-22,
  purchase journeys FRM-23 (earlier citations of FRM-19 for these resolve there). Evidence: none (scope).
- **FRM-20.** Foot traffic (split from FRM-19, 2026-10-20): exposure along predicted paths, by walk as
  well as transit, not only commuters' detours (user, 2026-10-20). Future work since 2026-10-18 (user):
  R5's transit walking overlaps Google's 0.338 against a 0.90 bar (TRN-12); feasible with resources, but
  it needs a match to Google's path preference (many paid calls) and ground truth across the study area
  (the City of Melbourne counters cover mostly the CBD). Reconsidered 2026-10-19 (user leaning, not a
  decision): a rank-weighted spread over R5's top routes, read as totals per stop cluster, with a
  footnote (TRN-12); no paid calls; a totals check first. Extensions absorbed 2026-10-20 (Notes): who the
  foot traffic is; travel mode to filter commuters. Drive paths (2026-10-14, 3,998 training pairs): every
  drive model misses 0.345-0.386 of Google's route length, bimodal (a third near-exact, a third a whole other
  route), so drive stays detour-only. Evidence: `transit_walk_overlap.py` (TRN-12),
  `route_match_vs_google.py` (drive).
  2026-10-22 (69th; matching Google's walk pattern dropped, user; TRN-12): per trip R5 misses Google's stops, and
  that is not tunable. In aggregate (report only): R5's walking totals agree with Google's at 500 m cells (weighted
  Jaccard 0.571, top-decile 0.756) and stop clusters (0.578 / 0.726), far above the split-half floors (~0.4);
  not at street / hex scale (0.405); agreement grows slowly with pairs; R5 walks ~1.5x Google's volume.
  Implication (user asked; Claude's wording): foot traffic, if revived, is R5 fastest-path exposure, never tuned
  toward Google; read at neighbourhood or stop-cluster scale, not per street; the volume lean stated or scaled;
  Google recommends and does not observe, so pedestrian counts stay the outside check. `transit_walk_aggregate.py`.
- **FRM-21.** Census years (future application; user, 2026-10-19, discussion; split from FRM-19): run the
  model on 2016, 2021 and 2026 census inputs against observed restaurant outcomes, measuring COVID's
  impact including its policies (lockdowns, 5 km limit, dine-in ban are the treatment): shock (2016-21),
  what remains (2016-26), recovery (2021-26). 2016 is a pre-COVID baseline, not a no-COVID
  counterfactual. All three fall on an August Tuesday. Outcome sources unchecked (ABS Counts of
  Australian Businesses, CLUE, card spending). Later: a neutral policy cost simulator validated against
  the 2021 bundle, in dollars only with spending data; health benefits out of scope. Secondary: travel
  tolerance from commute lengths. 2016 tables not fetched (user); 2026 POW output ~late 2027 (unchecked).
  Detail: snapshot, FRM-19. Evidence: none (scope).
- **FRM-22.** Demographic showcase (user, 2026-10-19, discussion; split from FRM-19): a small profile of who
  is reached, to show the research can be done: at most 6 metrics per side, one variable per table unless
  asked, read at face value. Workers (DZN by place of work, TableBuilder 2021): sex x age x marital status
  (15-18 / 19-33 / 34-53 / 54+), birthplace at 2-digit level, personal income, student status, travel mode
  (15 modes), hours worked. Residents (SA2 by usual residence): the same six with 10-year ages, plus
  household type x cars per dwelling; SA2 shares spread onto hexes by SA1 head counts. Why marital status
  x sex x age: eating to one's own taste or the household's (user's research experience, not tested).
  Limitations as in the snapshot (no vehicle count for persons; employed residents only for mode and
  hours; ABS perturbs every cell; 2021 lockdown, borders closed). Absorbed caveats: Notes. Files:
  `inputs/README.md`. Presentation (user, 2026-10-22): light, a complement to the presentation layer: per band,
  the top three groups per dimension (e.g. sex x age, birthplace), descriptive only; no claims comparing groups;
  the full ranking on request. Areas, not people (ecological fallacy): read as an opportunity, never
  profiling. Evidence: none (scope).
- **FRM-23.** Purchase journey scenarios (user, 2026-10-20, discussion; split from FRM-19): a
  low-conviction demonstration that the method applies beyond fixed residences and workplaces, for future
  work, not measurement. One worked example, subject only: students walking from a campus to the subject
  (shortest OSM walk); the competitors along it, inside a brush, by detour band x rating tier x price
  level x cuisine, cheaper or similar-cuisine rows flagged; a table, never one combined score. Never
  stated as interception or uptake (user). The route is an assumption (TRN-12). Answers the archive's
  rejection of corridor interception (rev4 L1249-1252) by being a scenario, not a population layer. Free
  checks first: shares of venues with a price level (VEN-3) and a cuisine tag (VEN-8). Origins: university
  / TAFE campuses. Detail and disclaimers: snapshot, FRM-19. Evidence: none (scope).
  Path implication (2026-10-22, 69th; TRN-12): walk-only legs are R5's best case (~0.63-0.74 of walk metres within
  25 m of Google's) but R5 zigzags where Google takes a Z, so one shortest path with a thin brush misplaces
  competitors. Claude's proposal (not decided): define "along the way" by walk detour time (o->v + v->d - o->d within
  the 3 / 5 min bands), which needs times only (validated); else a brush of at least a block (100-200 m).
  Free checks run 2026-10-22: inside 7 km price level on 0.42-0.44 of venues, a cuisine tag on 0.60-0.65 (some are
  meal formats: breakfast, brunch, hamburger); beyond 7 km no cuisine tags (VEN-8). A campus within ~5 km works with
  a "price unknown" row. `diagnostics/venue_anchor_tag_coverage.py`.
- **FRM-24.** What a transit time claims (user, 2026-10-23, 80th): times consistent with the faster end of the routes
  Google recommends, so reasonable but optimistic travel. Google's list is already filtered for reasonableness (no
  impossible speeds or connections); R5 picks its own fastest route under realistic rules (fitted walk speed, Google's
  boarding conventions, timetabled vehicles). The evidence is at the level of times (scored against Google's range,
  TRN-13 k = 2), not routes (TRN-12): never "picks one of Google's routes". A known-sign bias (optimistic; larger where
  alternatives are many), stated, not a failure (transit.md Limitations). Not claimed: what diners see or take; that
  Google's top recommendation shapes perception is the user's hunch, a reason for a target, not a finding.
  Migration to "Google's top recommendation" is open (DESIGN Q27). Evidence: TRN-13, TRN-16 (P5 / P6).
- **FRM-25.** Location decides the field; reputation is the game we chose to play within it (user, 2026-10-23, 84th
  discussion). The catchment (who can reach whom, within which tolerance) is the backbone: calibrated against Google
  and expensive to change (routing passes of hours). The reputation rules (share rule, q, tiers, ties; `scoring.md`)
  are a representation chosen on principle, not a model of diners: no evidence, not meant to be exact, low conviction,
  swapped on request or on new evidence ("you want another rule? we can run it"). Presenting them as sure-fire is the
  error to avoid; so is searching for the right one. Cheap to swap because they run on saved reachability draws, so
  reachability outputs never bake scoring in. Evidence: none (framing); cost contrast: subject transit pass ~8.3 h vs
  scoring rerun on saved draws.
- **FRM-26.** Presentation order by audience (user, 2026-10-23, 87th discussion). Same material, different order.
  Academic and technical audiences: setup first; the dashboard faded (low opacity) beside the catchment map as a
  cover illustration, to raise interest without front-loading arguments; then question, method, results,
  limitations (FRM-18). The catchment leads as the calibrated part (FRM-4, FRM-25). q is not asked: a q slider for
  sensitivity, with the 0.7 convention and reference marks on the curve (`scoring.md` SCR-16) and d(share)/dq
  (SCR-3). Why (user): a critical crowd is annoyed by assumptions and questions front-loaded without setup.
  Business audiences, pilot (user, 2026-10-26, 118th discussion): a human hook (one diner deciding where to eat;
  "we measure two of the factors": reach and ratings next to alternatives), a zoom out to the owner's market, then
  in medias res: the audience guesses k from three precomputed options and the headline map follows; then layers
  (reach, choice, population, demographics), the rating lever as a bookend. The hook's "we measure two" states the
  limits before any result, which meets FRM-18. Structure: `docs/presentation/pilot/structure.txt`.
  Evidence: none (presentation choice).
- **FRM-27.** The flagship measures potential; Google is read as opinion, not recommendation (user, 2026-10-25,
  107th discussion). Diners who have been around compare new venues with ones they know through what other diners
  say (ratings), whether or not they use Google's list. The catchment is the market a venue can keep: fixed origins
  (residents and workers) within tolerance once discovery has run its course, its long-run limit. Google's nearby
  list is first exposure: distance from the map's anchor leads, Huff-like (DESIGN Q19); a conventional Huff lens
  covers it as an extension (`scoring.md` Notes), reported beside the flagship, never added. Not modelled: repeat
  loyalty, visitors, the mix between channels (no anchor). Evidence: the screens (Q19); the break-even judges (Q31)
  for the comparison step. Cost: q's story retired (DESIGN Q32).

## Not adopted
- Reputation-first presentation (original conception): the spatial half holds the measurements. rev4 L38-41.
- Stating the model as predicting what will happen: replaced by what each lever is worth. rev4 L51-53.
- Foot traffic (e.g. random-walk betweenness as proxy): out of scope. rev4 L1590-1592. Revisited
  2026-10-14 as a commuter-flow layer from census journey-to-work data: parked, FRM-19. Dropped from
  the core 2026-10-18 (user): transit path fails (TRN-12); future work (FRM-20). For the write-up:
  considered three times, dropped each time.
- Our own graph tuned to reproduce Google's routes (user, 2026-10-18): likely conflicts with Google Maps
  Platform terms on using its results to build map data (Claude, clause not checked); too close to Google.
- Station-exit proximity weighted by station patronage as a stand-in for foot traffic (Claude, 2026-10-18):
  needs a distance decay or cutoff nothing pins down; exits are unequal and per-exit use is unmeasured (user).
- Seeking [subject]'s own sales or branch data for validation: one owner-selected sample. DESIGN_pre_spine "Settled in chat".
- Reverse-engineering Google's relevance ranking: at most, confirm that reputation helps exposure (e.g. ~60 manual searches across devices and locations). DESIGN_pre_spine "Settled in chat" (Oct 6).
  2026-10-20 (user): the confirmation, with location added, is a rank-correlation diagnostic on Text Search
  IDs-only result order (DESIGN Q19 (b)); inside this carve-out, not reverse-engineering. It replaces the
  manual searches (one device and account: one viewport, one personalisation).
  2026-10-25 (user, 103rd): both confirmations (Q19 (a), (b)) gate presentation; the diagnostic must weigh
  left-out venues, open status and sponsored placement, and starts with a screen-matching test (the user's
  Google Maps screen against the same API call). Design and owed proposals: DESIGN Q19.
  2026-10-25 (105th build): no API order matched the screen (25 Text Search and Nearby settings), so the
  confirmation runs on the user's own screens (n = 1 user, stated), still a confirmation, not a ranking model.
  The model claims diners travel by catchment, not that Google's list does; if Google's list accounts for travel
  time even slightly, that is a bonus, not a requirement (user). Results: DESIGN Q19.

## Limitations
- Arrow 2 (reputation → advantage) is unvalidated: threshold, m and fill order are stated judgements. rev4 L46-48.
- Rivalry only: clustered venues can help each other (bar hopping, food courts, malls); the model has
  only the "hurts" direction. Stated, not fixed. `outreach` L31, L52. (Oct 10)
- Travel cost only: a stop's full cost is detour + service + dwell, so the detour and foot traffic layers mean most
  for quick service; venues sort into formats by their location's flow, so no claim that exposure causes advantage.
  (musings 2026-10-16)

## Notes
- Draft blurb for the write-up (user approved the wording, 2026-10-13; "many people" until a usage
  source for Google's share exists): "Most accessibility models measure what people can physically
  reach: travel times modelled on roads and timetables as they really run. This project measures
  something different — the catchment as presented by Google Maps, the platform many people use to
  find a place to eat. It is an attempt to show what that presented catchment means for competition
  between restaurants: how many people a venue can reach on walk, transit and drive within the times
  the platform shows, how much of that reach comes from the network rather than population density,
  and how a venue's rating might turn reach into custom. It doesn't claim that people perceive travel
  exactly as Google shows it, or that the model reproduces what diners actually do; it asks what
  follows if the platform's view is the one that counts."
- Literature to read after initial outputs, before any novelty claim (user, 2026-10-13): Huff and
  gravity models (expect "why not Huff?"; answer on record in `scoring.md` Not adopted, no measured
  decay rate), 2SFCA, cumulative-opportunity accessibility, perceived accessibility. Hunch to check:
  the novelty is the platform as the source of perceived catchment, not catchments as such.
- Write-up framing for owners (user, 2026-10-14; extends FRM-6, FRM-9): the output is *potential*,
  not predicted sales; a gap between potential and what an owner sees is information, not model
  failure. It supports a pilot, not a prescription: the model gives who is reachable, from which
  population and how contested; the owner brings conversion, margins, costs and strategy. The band
  and layer profile reads as a strategy guide (strong far band, weak near bands: destination play;
  strong near band: passing-trade play; workers above residents: weekday lunch). Examples: staff
  discounts for a large nearby employer; a promotion aimed at an origin area with high potential and
  few customers.
- Literature search scope (2026-10-14, after the core per FRM-19): Huff models with online ratings as
  attractiveness; counterfactual decompositions of accessibility; catchments split by population
  type. Novelty, if any, is likely in the combination (SCR-6 four corners per venue), not the parts.
- The project's own walk graph was very good and was superseded by r5py, not found wanting; worth a
  side note in the credits. `walk.md` WLK-5. (user, 2026-10-13)
- Prep-time angle (musing, not a model claim): if a customer's tolerance is total elapsed time,
  kitchen prep subtracts from drive time, and reachable area grows roughly with the square of the
  time left, so cutting prep could multiply the catchment. Usable loosely with less rigour-oriented
  readers (e.g. an owner worried about a weak position in the close bands). Worth pursuing in future
  with better data and a delivery platform. rev4 L294-300. (user, 2026-10-12)
- The author works for and personally knows the owner of [subject], who has already acted on the idea. (2026-10-12)
- Correction on record (Oct 10): the owner's sensitivity to ratings, his testimony that Brunswick East
  customers find [subject] through Google, and [subject]'s heavy investment in ratings all **predate** the
  project; he didn't act on the project's premise. The Melbourne Central ratings push may have been
  prompted partly by an early rough "4.5 Melbourne average" the author mentioned (later 4.2 from the
  data): plausible, not established. Melbourne Central is footfall- and worker-driven and its customers
  mostly reported social media, so it is background (FRM-12); Brunswick East carries the argument. [subject]
  actively pursues reviews, so its rating partly measures solicitation effort (FRM-7). `outreach` L56-61.
- Precinct idea (parked extension, not promised): people may choose a hot street first and a venue
  second; whether neighbours help or hurt may depend on density. 100 m hexes are probably too fine for
  it. `outreach` L53, L124. (Oct 10)
- Supporting angle (Claude, no reference given): people who take Google's times at face value are
  those unfamiliar with the area, and the most swayed by ratings ("Luca's quality-uncertainty
  mechanism"). Needs a citation before use. `fractional_hexes_Sep_29` L11. (Sep 29)
- Absorbed 2026-10-20 from `incoming_absorbed/20261019_foot_traffic_demographics.md` (W6; proposals, not built):
  (FRM-20) break foot traffic down by who it is (religion, occupation, family size; e.g. what a halal or
  vegan option could unlock), future work; the user's [subject] halal / vegan story is illustration, not
  evidence; religion proxies halal demand, it doesn't measure it; fine variables need coarser categories
  or larger zones against ABS cell noise (zone size open). Travel mode (DZN x MTWP) would keep only walk
  and transit commuters in a transit-fed layer; free check: walk / transit shares per DZN. Bridging 2021
  to 2026: not on the pedestrian sensors (user: CBD-centred placement); a recovery factor per area type
  from PTV station patronage (Claude, unchecked). The DNZ POW total check passed (3,163,746).
- Absorbed 2026-10-20 from `incoming_absorbed/20261019_census_profile_musings.md` (W6): (FRM-22) a lead,
  from a hunch, not evidence (user): Melbourne's Chinese and Indian communities behave differently, young
  Chinese especially, which is why birthplace is kept. Hunches: platforms steer taste along cultural lines
  (Douyin and Xiaohongshu vs Instagram); couples eat out where they live, so marital status describes
  lifestyle on the worker side and the couple effect sits with residents (Claude). Caveats: 2021
  undercounts Chinese international students (borders closed on census night); venues popular on
  Xiaohongshu may have few Google reviews, so Google-based venue data under-reads that demand; birthplace
  misses the second generation (language at home, downloaded, partly catches it). Open: the size of the
  2021 student gap by area. Checks (not run): Xiaohongshu mentions vs Google reviews by area; China-born
  19-33 by SA2, 2016 vs 2021.
- Planned human review: an operator on whether outputs mean anything to a business; a
  transport-modelling reviewer on wait and pooling logic. rev4 L1964-1967. (~Sep 21)
- Defensibility (user, 2026-10-24, 96th): conventions and reasonable assumptions are not evidence; what makes
  the scoring defensible is its low conviction (FRM-25). Challenged on a rule: "that's possible; want to try
  yours?", and ask what would be more defensible. A rule's results are never offered as support for it.

## Open questions
- Migrate the transit claim to Google's top recommendation (DESIGN Q27).

## Changes
- Changes to 2026-10-20 (FRM-1 to FRM-19): snapshot, "Changes".
- 2026-10-22 · FRM-19 / FRM-20 / FRM-23 (69th): walk-pattern matching dropped (user); aggregate foot-traffic check, path implications, anchor free checks, detour noise (drive, transit, walk) recorded
- 2026-10-20 · FRM-19 split into FRM-19..23; commuter detour layer revised (time-only); inbox notes absorbed (Notes)
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
- 2026-10-22 · FRM-19 three-part presentation and detour design (user); FRM-20 drive path evidence; FRM-22
  presentation (top three per dimension, user); venue-format limitation; from the musings review
- 2026-10-23 · FRM-24 (80th): transit time claim framed as the faster end of Google's recommended routes (user); migration to top recommendation open (DESIGN Q27)
- 2026-10-23 · FRM-25 (84th discussion, user): location decides the field, reputation is the chosen game; scoring rules low-conviction and interchangeable
- 2026-10-23 · FRM-26 (87th discussion, user): presentation order by audience (academic recorded; business order pending)
- 2026-10-26 · FRM-26 (118th discussion, user): business pilot order (human hook, audience guesses k, headline map, layers)
- 2026-10-24 · Notes: defensibility from low conviction (96th, user)
- 2026-10-25 · Not adopted (relevance ranking): Q19 (a) and (b) gate presentation; left-out, open-status and sponsorship cover; screen-matching test first (103rd discussion, user)
- 2026-10-25 · FRM-27 (107th discussion, user): flagship measures potential; Google as opinion, not recommendation; first exposure a Huff extension
- 2026-10-25 · Not adopted (relevance ranking): API order doesn't match the screen, the test runs on screens; Google using catchment is a bonus, not a requirement (105th build, user)
