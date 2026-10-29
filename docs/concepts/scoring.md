# Scoring and ratings

**Purpose and scope.** How reachable population is turned into a competitive outcome: the bands, the
Top-N rule, who wins a slot, counterfactuals, and what owners are shown. Not how reach is computed or
its uncertainty (`reachability.md`), nor what the project claims overall (`framing.md`).
**Status of these rules.** A representation chosen on principle, low conviction, interchangeable (`framing.md` FRM-25):
none is a finding about diners; the catchment is the backbone.
**Stages.** Scoring (`scoring.py`, then the report `scoring_report.py`; main.py block `run_scoring`; last in pipeline order).
**Last reviewed.** 2026-10-23, 1d3ef1d
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/scoring.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **SCR-1.** Three bands: 1 = walk + public transport ≤ 600 s; 2 = walk + public transport ≤ 1200 s;
  3 = drive, 20 min predicted (routed time ≤ 1200 / ALPHA). Band 3 claims nothing about delivery.
  Each band stands for diners with that travel tolerance, all three the same kind of object: a venue
  in band k is within reach of a diner willing to travel that far by that mode, not a venue Google
  shows them. Why (user, 2026-10-13): in exploratory search Google's viewport keeps shifting and its
  recommendations come from an unknown ranking (reputation and distance play some part), so the model
  doesn't claim to predict exposure; it rests on travel time, which is calibrated against Google.
  Band 1's match with the search radius is a side note only (Notes). Under SCR-15, q read Google as a list in
  rating order browsed by a stylised diner (87th, DESIGN Q28 (e)); retired 2026-10-25: under SCR-23 each band adds
  a search stage over its field, the bands nested.
  Evidence: none (definition). DESIGN_pre_spine "Scoring model"; rev4 L201-211, L279-292.
- **SCR-2.** (Considered variant since 2026-10-23, 83rd: the headline rule is SCR-15; Top-N is reported beside it.)
  Top-N: each hex's population divides among the K venues in reach: when K > N the top N
  take 1/N each, when K <= N each takes 1/K, K = 0 claims nothing (revised 2026-10-23, user, 79th
  discussion; was exactly N slots, empty ones left empty). Ties into the last slot split
  proportionally. N swept over 1-3 and the range reported (N = 1 winner-take-all; N -> infinity is flat
  reputation: every venue in reach a candidate, 1/K each). Why 1/min(N, K) (user): with empty slots,
  raising N drains the claimed population to zero and breaks the flat-reputation limit; where only a
  few venues exist (rural), they are the whole shortlist. N is the size of a diner's shortlist within their tolerance, not what
  fits on screen; a mobile viewport showing 2-3 results only hints at its scale. Rationale: attention
  is a cost and Google shows only a few options; venues within N are equals because position effects
  are unknown.
  Evidence: none (stated convention). DESIGN_pre_spine "Scoring model", "Settled in chat" (Oct 6); rev4 L238-247.
- **SCR-3.** Top-N share is not monotone in N (a venue consistently 2nd gains, one consistently 1st
  loses), so N can't be gamed; d(share)/dN measures how much a venue depends on reputation. Where
  K <= N the share does not move with N, so few-option (rural) venues read as less reputation-dependent
  (2026-10-23, follows SCR-2's revision). Under SCR-15 (headline), reputation dependence is read as
  d(share)/dq: steep = lives on its rating, flat = lives on its location (2026-10-23, 87th, Q28 (d)).
  Evidence: none (reasoning). rev4 L252-255.
- **SCR-4.** Who wins a slot, within a band, lexicographically (no trading rating against distance):
  every venue in reach, ranked by its shrunk rating (SCR-20), unbinned; no review threshold, no tiers (revised
  2026-10-24, 92nd discussion, user; was: a rated tier of 10+ reviews by displayed rating at 0.1, the low-evidence
  tier below). Ties share (SCR-15: average weight of the ranks they occupy; SCR-2: split proportionally). The
  proximity tie-break is dropped: it broke the no-distance rule below (2026-10-23, 87th, Q28 (a)). Why (user): a
  sharp cut is the problem; the weight on a rating should fade with fewer reviews, not switch (band 1's top rival
  in the first run was a 5.0 on exactly 10 reviews).
  Core arrow-2 assumption under the tolerance framing (SCR-1): within a tolerance, distance doesn't
  matter to the diner (2 min and 19 min away are equals; rating decides).
  Evidence: none (stated judgement). **Unconfirmed:** the diner behaviour behind it is intuition and
  hearsay; no study found or checked (literature may exist; user, 2026-10-13).
  DESIGN_pre_spine "Scoring model"; `rating_rule_and_visualisation_Sep_28` L23-31.
- **SCR-5.** Retired 2026-10-24 (92nd discussion, user: no arbitrary walls). Was: a low-evidence tier (0-9 reviews,
  incl. 817 unrated) ranked below every rated venue, ordered within by shrunk rating, m unpicked. Now SCR-4 ranks
  every venue by SCR-20's shrunk rating, so a venue with no reviews sits at C by the same rule. If fewer than N
  venues are in reach, those in reach share the hex at 1/K (SCR-2). Full text: git history.
- **SCR-6.** Counterfactuals, four corners: population real/flat × accessibility real/flat; reputation
  real in all four. Flat accessibility = one haversine radius R̄, solved by bisection so the mean
  reachable population matches the graph's, per band and per denominator. Results as share of the
  contestable population (SCR-11) within each run. R̄ is a property of the field: never prominence-weighted (circular,
  double-counts proximity).
  Evidence: none. DESIGN_pre_spine "Scoring model"; rev4 §4.5; `hex_block_Sep_27` L135-146.
- **SCR-7.** Owner-facing figures are percentile positions among all venues (18,498 on the grid, `venues.md` VEN-4; ~9,400 in older docs; reach and
  reach-weighted density as separate percentiles), with people alongside percent; no self-comparison
  phrasing. Owners get the curve over N, not one answer (FRM-9).
  Evidence: none. rev4 L437-441; `STALE_handover_rev3_7_delta` L187-210.
- **SCR-8.** Reputational advantage for owners = (P_real − P_blind) / P_blind: a fifth run with every
  venue's rating set to C (P_blind = population won on location alone). People reported alongside the
  percent. Blows up when P_blind ≈ 0 (venues with closer competitors): cap it or report the count.
  Evidence: none. rev4 L418-435. Confirmed as planned by the user 2026-10-13.
- **SCR-9.** Siting tool: the owner gives a rating and review count; the model sweeps restaurant-bearing
  hexes and reports population won at each; the inverse gives the rating needed to win a hex. Supersedes
  the deferred relocation heatmap.
  Evidence: none. rev4 L1462-1468. Confirmed as planned by the user 2026-10-13.
- **SCR-10.** Times are judged as Google displays them: rounded to the nearest whole minute (WLK-4), in
  every band (walk + PT and drive), so a band of N min covers times up to N·60 + 29 s (~629 s, ~1,229 s;
  drive 20 min ~1,229 s). Reason: map users see whole minutes, never the seconds the API returns
  (decided 2026-10-16, user). Settles S1's convention; how r5py delivers it stays open (S1).
  Evidence: WLK-4 (display rounding, 10 walk pairs); the API returns seconds (TRN-8 smoke test,
  2026-10-16: walk-only 1,498 / 609 / 459 s).
- **SCR-11.** Contestable hex (user, 2026-10-23, 79th discussion): a hex inside a venue's catchment for
  a band and 30-min slot, weighted by the venue's chance of reaching it within the band (RCH-23). Every
  venue has its own set; how many venues reach it plays no part. A competitor of the subject is a venue,
  open in the slot, with some chance of reaching one of the subject's contestable hexes; "competitor
  hex" is a routing term only (a venue hex can hold several venues). Replaces the undefined "contested"
  (RCH-12, SCR-6); no field-wide "served" set is needed.
  Evidence: none (definition).
- **SCR-12.** Uncertain reach enters by draws (user and Claude, 2026-10-23): in each draw every venue
  reaches each hex or not, by its band probability (RCH-23); reachability decides who enters, then Top-N
  (SCR-2, SCR-4, SCR-5) divides the hex among the venues that entered (K counts only those); shares
  are averaged over draws. Fractional competitors fall out of this: a 10%-reach venue alone near a hex
  holds it in 10% of draws, so 10% of it; the rest is diners with nothing within tolerance. Why (user):
  reachability asks capability (does the venue enter at all), Top-N the candidate list (how entrants
  split it). An exact per-hex formula assuming independent reach (Claude's) is a check only: departure
  noise is shared by all venues seen from one hex, measured by RCH-23's draws.
  Evidence: none (reasoning).
- **SCR-13.** Opening hours (user, 2026-10-23): shares are computed per 30-min slot; a venue closed in a
  slot is not in it. Reach probabilities differ per slot and Top-N is nonlinear, so an hours fraction is
  never used as a competitor weight ("open x% of your hours" is a description only). Headline: the
  equal-weight mean over the subject's open slots; per-slot figures only for readers who ask (a per-slot
  headline is dubious presentation). Weighting slots by demand is out of scope (no defensible weight).
  Default and academic presentations: equal weights; a per-slot demand weight may become an owner-set
  option later (user, 2026-10-23, 88th; not a priority).
  Hours in the draws (user, 2026-10-23, 90th): a venue with its own pulled hours keeps them; any other venue, in
  each draw, adopts the whole weekly schedule of one pulled venue, a donor: a level of its shrinkage chain (VEN-13)
  picked by its weight, then a random pulled venue of that group. Why (user): an imputed share may describe no real
  venue; a donor's schedule always exists, and it keeps a venue's slots and days coherent. Mon-Thu: one day per
  draw, shared by all venues. Over draws a venue's open rate equals its imputed share (`venue_open_share_*.parquet`,
  the check). "All open" stays a switch for comparison. Hours were adopted without a sensitivity gate: at dinner
  15 / 18 / 19% of reach-weighted competitors (bands 1 / 2 / 3) carry daytime tags, 29% of pulled venues are shut
  at Wed 19:00. Evidence: `diagnostics/venue_hours_slot_imputation.py`; Step 0 count ad hoc (90th, not kept).
  Built (91st): `hours_imputation.DonorSampler`, `WeekDraws`, `scoring.venue_week_draws`; draws' expectation equals
  the open shares (max 3e-8), 1,000 draws within MC noise. Mon-Thu day stratified, draw d takes the (d mod 4)-th day
  (Claude, 91st; was random: Monday has 31% fewer pulled venues open at 19:00 than Thursday, and random days swamped
  band 3's MC error). Donors match held-out venues' joint structure, independent slots don't (open through Mon-Thu
  dinner: truth 0.52, donors 0.52, independent 0.08). Evidence: `diagnostics/venue_hours_donor_draws.py` (14 / 14).
- **SCR-14.** Two competitor measures, from the same draws as SCR-12 (user and Claude, 2026-10-23, 79th
  discussion). Ceiling: in every draw where the subject enters a hex it could have held all of it, so the
  ceiling is each contestable hex's population times the subject's reach probability. (1) **Denial
  (outclassed by):** each competitor present in those draws is credited with the share it holds there;
  the credits sum exactly to ceiling minus the subject's share. Structural: the best-rated venue nearby
  tops it. (2) **Contention (peers):** in those draws, the venues just above and just below the subject
  in the hex's ranking, each credited with the share that would move if the two swapped places (SCR-15;
  2026-10-23, 87th, Q28 (c); under the Top-N variant, the venue trading the last slot). Actionable (user): who a small rating change moves the subject past, the
  peers to study; ties to SCR-9's rating needed to win a hex. Occupancy, not "who would hand the share
  back": a venue beside the subject in the top N counts as denial though removing it frees nothing.
  Cutoff (user and Claude, 2026-10-23, 81st): competitors named in the output above a threshold (e.g. >= 1% of the
  subject's contestable persons; set at build), the rest grouped as "others". Never in the computation: dropping a
  venue that entered a hex inflates the subject's share there, one-sided over a long tail, and breaks the denial sum;
  it saves nothing, since all venue hexes come with each origin's search (RCH-21).
  Evidence: none (definition).
  Built (94th): contention shown as **immediate rivals** above and below (user's name, 94th). Under key cells (SCR-19)
  the rival is every venue in the nearest occupied cell above (below) the subject's, each credited an equal part of
  the share that would move if the subject swapped ranks: above (q^(A-1) − q^A)(1 − q)/(1 − q^K), below (q^A −
  q^(A+1))(1 − q)/(1 − q^K), A entrants above, K all; headline hours rule and q. User: reasonable under this scheme
  (94th). A list, not a sum: swaps don't add (band 1: rivals above 522, below 381 persons; 4.8 → 4.9 gains 1,865,
  passing 55 venues). Evidence: diagnostics/share_cells_exact.py (exact vs brute-force swaps).
- **SCR-15.** Headline share rule: diner persistence q (user, 2026-10-23, 83rd; supersedes Top-N as the headline,
  SCR-2 kept as a considered variant). In each draw the venues that entered a hex (SCR-12) are ranked from the top
  by displayed rating; rank r weighs q^(r-1), ties share the average weight of the ranks they occupy; the hex's
  persons split in proportion. q = the chance a diner looks one option further down; q -> 1 is flat reputation, q -> 0
  best-takes-all, Top-N the step-shaped member. Headline at the convention q = 0.7 (browsing models' middle; likely
  lower on Google, user), always with the curve over q. Properties we chose it to have (not findings, FRM-25): nobody
  gets zero (venues rarely get no customers, user's hunch), better never gets less, ties equal, a worse entrant never
  helps an incumbent; few options still favour the better venue (SCR-2's 1/K-in-rural case reversed, user). Stated
  arbitrary choices: rank only (rating gaps ignored); in dense fields the top venue holds at most ~1-q of a hex. Considered: linear rank from the bottom (fails the entrant
  test), top-P by count or rating bar, absolute floor, logit on rating (fails C9 as headline: a Yelp-sourced
  beta measures revenue without a choice set; kept as an optional demand lens, beta swept, Yelp a marked point, labelled
  share not demand; a logit fitted on choice-set data would be a fair challenger; user, 84th). Choice: Notes
  "Share-rule criteria". Precedent (Claude, from memory, verify): rank-biased precision (Moffat & Zobel), cascade click
  models. Cost: q has no anchor; reported as a curve. Evidence: none (convention).
  Story retired 2026-10-25 (107th discussion, user): q assumes diners meet venues in rating order; Google's list is
  distance-led (DESIGN Q19) and diners look venues up one by one. q stays the code's rule until DESIGN Q32 decides;
  best-of-K is the candidate (Notes). 108th: decided, SCR-23 replaces this rule once built.
- **SCR-16.** Owner presentation of q (user, 2026-10-23, 83rd; replaces the curve-over-N slider, SCR-7 / FRM-9):
  before any result, explain q in general terms (1 = scrolls forever, low = only the top few), state the 0.7
  convention and that Google's is likely lower, and give Claude's guess; the owner states a guess, saved with a
  timestamp; the headline is pinned at the owner's guess; the curve over q with a slider shows the rest, marking the
  owner's guess, the convention and Claude's; moving q shows "before seeing results you said ...". Why: q is the
  owner's assumption about their diners; updates after seeing results stay visible. Evidence: none (convention).
  Reference marks (2026-10-23, 87th, Q28 (f); before any scoring result): Claude 0.6 (Google shows ~3 places up
  front); the user, as analyst, 0.8 (restaurants are browsed for fit and mood, unlike uniform services such as
  dentists or tyre shops; earlier lean below 0.6 on mobile's short list). Only the owner's guess pins their headline.
  Owner screen (user, 87th): the subject's rating fixed by default, the q slider starting at the owner's guess;
  a second slider over the subject's rating with text markers where it passes each peer (contention, (2) of
  SCR-14), e.g. "at 4.6 you pass X: +N people"; names and ratings, no logos or photos (Place Photos is paid and
  Google's storage terms are unchecked). The owner states the guess, then takes the controls.
  The guess is asked as scroll depth, not q (user, 2026-10-23, 87th): "Think of someone near you opening Google
  Maps to find somewhere to eat, with no place in mind yet. On average, how many restaurants do they look at
  before choosing?" Asked about potential diners, not the owner's customers (those already found the venue: a
  selected group). The answer k (average places looked at, a count) gives q = 1 − 1/k (the cascade's mean depth
  is 1/(1 − q)); the owner sees "on average k, half stop by about the m-th" (m = the geometric median depth,
  ln 0.5 / ln q) and confirms or adjusts before any result. Academic audiences are not asked (framing.md FRM-26).
- **SCR-17.** Reach table (built 2026-10-23, 88th; user: 1% floor, every open slot): the scoring stage's first step
  (`scoring.py`, `functions/reach_table.py`). Rows: per band, 30-min slot (transit; drive slot-free) and hex where
  the subject's chance is >= 1%, each venue hex's chance of reaching that hex within the band (>= 1%), stored in
  steps of 1/255. Chance = P(Google's rounded minute <= cut | model time) (RCH-23 (b)); transit averages it over
  the slot's departure minutes (adds (a)). Passes found by their build stamps; the table has its own stamp. Subject:
  42 slots, transit 88 MB, drive 539 MB, 284 s, free. Floor cost: expected residents understated 1.1 / 0.8 / 0.3%
  (bands 1 / 2 / 3, Mon-Thu 19:00); rounding negligible; 10% hex and competitor sets unchanged. Venues are joined
  by venue hex and opening hours (VEN-13) applied at scoring time.
  Evidence: ad hoc acceptance check vs the 88th's catchment figure (not kept; failed its own 0.5% tolerance on bands
  1-2, cause the floor, accepted by the user).
- **SCR-18.** Headline population (user, 2026-10-23, 90th): residents + workers, with a disclaimer that the two
  eat out at different hours. The Brunswick owner is shown residents; workers as a sideshow, showing the method
  also serves Melbourne Central (the owner's current focus). Evidence: none (presentation choice).
- **SCR-19.** Share step design (user and Claude, 2026-10-23, 90th; built 91st, see the end of this entry). Under SCR-15 rank weights always
  sum to (1 - q^K) / (1 - q), so a venue's share needs only the entrants above it, tied with it and in total. Each
  draw keeps, per hex, open entrants counted by displayed rating (0.1 bins, rated tier) plus a low-evidence count:
  any focal rating (the owner's slider, SCR-16), any q, Top-N and each competitor's rank (SCR-14) are lookups. Reach
  drawn per venue hex (co-located venues share route noise); hours by donors (SCR-13); draws per band until the
  headline's Monte Carlo error is < 0.5% relative; the same random numbers across hours rules, slots and ratings.
  Every rule choice is a config switch. Field-wide scoring (SCR-6, SCR-7, SCR-9) needs reach tables for every venue,
  not new share code. Evidence: none (design).
  Built (91st; `scoring.build_shares`, `functions/share_draws.py`; switch `should_build_shares`). Changes from the
  design (Claude's): counts exact by dense matrix products (hex x venue hex entries @ venue hex x bin open counts,
  ~0.4 s per 8,192 hexes), no normal approximation; stop per reach unit at 0.5% relative or 1 person absolute (band
  3's headline is near zero at q 0.7: 42+ better-rated entrants in every sampled hex), 24-400 draws; the low-evidence
  tier is one tied bin (m of SCR-5 unpicked). Checks: denial sum <= 2e-7 in every unit; one hex by brute force; q -> 0
  equals Top-1. No full run kept (two stopped, 91st). Ordering key to change (92nd): SCR-20's unbinned shrunk
  rating replaces the 0.1 bins and the low-evidence bin; rebuild owed.
  Layout (user, 2026-10-24, 93rd build; not built yet): cells, not bins. One cell per slider value's exact key (the
  slider's displayed values shrunk at the subject's n) keeps the subject's share exact at every slider value in one
  run; credit edges every 0.02 from 4.0 (0.1 below; config SCORING_CREDIT_KEY_STEP, SCORING_CREDIT_FINE_FROM): rivals
  in one cell tie for credits only (their sum and the denial sum stay exact; ~117 venues per cell above 4.6).
  Credits at the subject's actual rating only. A rating off the slider grid, another review count for the subject,
  or credits at another rating need a rerun. ~96 columns vs 42: run time ~1.5-2x, timed on band 1 first.
  Layout built (94th, autonomous): 98 cells; first full run 86 min (bands 1 / 2 / 3: 3 / 24 / 54 min; band 3 stops at
  24 draws, ~135 s each, 2.5x the 91st). Checks (Claude's, before results): subject's share at every slider value =
  brute force on real keys; denial sum <= 1.2e-7 every unit; ceiling = draws' entered persons. First readings (q 0.7,
  donor, 4.8; persons per open slot): band 1 1,270 (all-open 794; 10.9% of the ceiling), band 2 951 (1.5%), band 3
  0.8; slider 4.9: 3,135 / 10,142 / 6,696. Report and census profile: `scoring_report.py` (Notes "Share report").
  Evidence: diagnostics/share_cells_exact.py.
- **SCR-20.** Shrunk rating, for ordering only (user, 2026-10-24, 92nd discussion). s = (n·r + m·C) / (n + m): r the
  displayed rating, n the review count, C the field mean of displayed ratings (4.25: each venue weighted n / (n + m), fixed point with m), m = σ² / τ² (the
  review count at which a venue's own rating and C weigh equally). Never shown: owners see Google's numbers only
  (the 4.749 objection, Not adopted); the subject's slider (SCR-16) maps each value through s at the subject's n.
  m is fitted, not a dial (user: too many dials; disclosed if asked): τ (spread of true ratings) ≈ 0.40 from
  venues with 300-900 reviews; σ (spread of one venue's reviews) set at the most the 1-5 scale allows at C,
  (C − 1)(5 − C) (Bhatia-Davis bound), as no data measure it: m ≈ 15, wrong toward scepticism if wrong. Prior
  global, never per hex. Chosen against R1-R11 (Notes). User's guess before the fit: a 5.0 on 10 at ~4.5 (m ≈ 19),
  the user's own scepticism, not assumed typical. Evidence: diagnostics/rating_shrinkage_m.py (93rd: τ 0.399, σ 1.56, m 15.3 → 15;
  config SCORING_SHRINK_M, SCORING_SHRINK_C).
  Key S*' (user, 2026-10-24, 97th discussion; DESIGN Q29 closed): before shrinking, a displayed 5.0 reads as 4.975
  and 1.0 as 1.025, the middle of their display ranges, as every other rating already sits. m 15 stays the
  headline while DESIGN Q31 (m) is open. Code default since the 98th (`shrunk_top`, both ends; band 1-2 rerun
  equals the 96th's S*' run exactly).
- **SCR-21.** SWOT appendix for the rating-competition model (user, 2026-10-24, 94th; not built): attached at the end of
  the presentation; the catchment model gets its own SWOT. Strength: what the subject holds at its current position
  (Claude's lean: captured persons, where and when it leads, its rating among review-count peers, not the catchment
  itself). Weakness: denial, phrased "who stands above you" (occupancy, not cause, SCR-14). Opportunity: the census
  profile of who is reached but not captured; gains from passing the immediate rivals above and from +0.1 displayed
  (kept apart: local swaps vs a jump; +0.1 costs 0-1,110 five-star reviews by where the true mean sits, which the
  owner's own star breakdown would pin); recommended opening hours (below). Threat: losses when immediate rivals below
  pass, with the prominent rivals and the five-star reviews each needs to pass; Claude adds rivals' longer hours
  (band 1 1,270 with real hours vs 794 all open) and a well-rated entrant. The threat numbers depend on the rating
  rule (Q29): under S* every rival below is a 4.8 with fewer reviews that passes with 15-35 five-star reviews and no
  change on display (R14); under F they tie. Footnote: a chosen representation (FRM-25), persons per open slot.
  Opening hours (user): the subject open in a slot it now closes, ranked by expected persons captured, candidates
  only where >= 50% of its tag peers (the VEN-13 chain's pooled open share) are open. Why (user): a sit-down venue
  isn't told to open at 1 am; peers' hours reveal the unseen cost of opening, below 50% it is a coin toss for similar
  businesses, above it the hour is plainly reasonable. Slots just above 50% flagged as near the line. Subject (Mon-Thu
  / Fri): shut at 12:00-14:00 where 70-80% of peers are open. Needs a subject-hours switch and transit reach for the
  candidate slots (~1 h routing; drive is slot-free). Uniform propensity across venue types stays a limitation; peer
  hours as a demand signal is Claude's hunch, used as a filter only. Evidence: none (presentation choice).
- **SCR-22.** Rarity line on the owner's rating slider (user and Claude, 2026-10-25, 99th discussion; built 100th):
  each slider step (SCR-16) says how rare that rating is among venues with a similar review count, e.g. "Venues with a
  similar review count: 1 in 59 show 4.9 or higher". Counts "or higher" (exact counts aren't monotone). Wording (user,
  100th): "N in 10" above a third of the comparison, "1 in N" below; the count itself under 5 venues ("2 of 200"); a
  denominator over 300 restated per 1,000 ("2 in 1,000"), per 10,000 and up while that rounds to 0 (near zero is not
  zero); "NONE of 883" in capitals when no peer holds it. Comparison: rated venues (rating, > 0 reviews) within ±2.5
  review-count percentile points of the subject (user), min(2.5, distance to the top), subject excluded, every tag,
  venue snapshot; [subject]: 883 venues, 1,315-2,385 reviews (the 99th's 912 / 1 in 61 not reproduced, ad hoc). Wording
  counts other venues, never the subject's odds. Replaces the in-a-row caption. Why: the slider holds n fixed, so its
  top steps are combinations the field barely holds (Notes "Rating maps and q sweep"). Cost: none measured. Built:
  `share_report.rarity_lines`, `report_rarity.csv` (report not yet run end to end), rating maps' caption.
- **SCR-23.** Headline share rule: staged best-of-K (user, 2026-10-25, 108th discussion; replaces SCR-15 once built;
  built for bands 1-2 2026-10-26, 109th, sped up 110th; band 3 built 112th (RCH-27 fields); run of record 117th
  (bands 1-3; GPU port, stratified stop; DESIGN Q32). Each diner draws K, geometric with mean k (Poisson the sensitivity), and searches in stages: a band-b
  diner draws k looks at random from band 1's field, then from band 2's whole field minus those seen, up to band b;
  the best by the S*' key among those seen wins, exact ties split. In one stage rank r of M gets
  sum_j p_j C(M-r, j-1) / C(M, j); stages stay closed form (counts of better venues per ring). k is the owner's guess
  (the 87th scroll-depth question), marks 2.5 / 3.3 / 5. Why: diners stop on vibe and pick by rating among what they
  saw; a longer trip earns a harder search; search spreads outward from home. Cost: C1 holds within a ring only, C4
  fails (accepted), k has no restaurant anchor; uniform pool within a stage by limitation. Evidence: none
  (convention); detail in DESIGN Q32 and Notes "Best-of-K".

## Not adopted
- Hours by a tag-closure rule (cafe, bakery, coffee, breakfast, brunch, sandwich and salad tags closed at dinner) and a
  5% sensitivity gate before imputing (90th): crude (closes a cafe-bar), dinner-only, a local tag list; the counts
  already justified imputing (SCR-13). User, 2026-10-23.
- Bands as a prediction of exposure (which venues Google shows a diner), including band 1 as a "visibility band" (rev4 L209-211): the viewport shifts during exploratory search and the ranking is a black box; replaced by travel tolerances (SCR-1). User, 2026-10-13.
- Bayesian shrinkage (m = 50, later 60; C = field mean) as the main rule: a Top-1 relic; no downstream use of `adjusted_rating`. DESIGN Q6; `rating_rule_and_visualisation_Sep_28` L10-13, L44. Revived 2026-10-24 for ordering only, for another reason (weight fades with review count): SCR-20.
- Lenient m (m = 10 floated), then round to 0.1: gives a value no platform shows (4.8 on 100 → 4.749 → 4.7); converges on raw rating + threshold, which was adopted (SCR-4; threshold retired 2026-10-24). `rating_rule_and_visualisation_Sep_28` L45-48. Ordering by the unbinned, never-shown value sidesteps it (SCR-20).
- Shrinkage choice by dominance test or empirical-Bayes m: overtaken by the tiered rule. rev4 L267-277; `STALE_critique_and_speed_table_retirement_Sep_18` L172-177. Empirical-Bayes m revived 2026-10-24 (SCR-20), tiers retired.
- Local priors for shrinkage: endogenous to the competitive set. rev4 L264.
- Percentile within review-count peers as the key (P, DESIGN Q29): our own construction, not a convention (user:
  shrinkage is easier to justify), with a free window (500 nearest by log count; 250 / 1,000 as sensitivity);
  second-lowest in the user's blind pairs (10 / 30). User, 2026-10-24, 97th.
- Rating-rule alternatives (92nd discussion; scored in Notes, R1-R11): a higher threshold, 25 or 50 (a cliff at another
  unanchored number; user: "50 sounds harsh"); more reviews wins near-ties (a step again: 4.9 on 11 beats 5.0 on 10);
  a lower confidence bound (Wilson / Dirichlet: ranks unknowns low, fails R5); the shrunk score binned at 0.1 (bin
  edges split the subject's 4.8 peers: 4.8 on 188 drops to 4.7 at m = 25); m as an owner dial (too many dials,
  user); trust draws (a venue trusted with chance n / (n + m), else at C: the best diner story, kept as a considered
  variant; extra Monte Carlo noise in bands 1-2, R10). User and Claude, 2026-10-24.
- Descending threshold (10 → 9 → 8 …): makes "rated" location-dependent. `rating_rule_and_visualisation_Sep_28` L49-52.
- Filling the low-evidence tier by review count first: ranks 3.2 on 9 reviews above 5.0 on 5. Same doc L53-54.
- Relaxing the win condition by ±0.2 instead of N = 3: 0.2 would be invented. rev4 L250-251.
- Trading reputation against distance, distance weighting or continuous decay: needs a rate nothing measures; perception is threshold-like. rev4 L260-261, L1511-1512. For first exposure a rate now exists (107th: Google's order, lambda ~ 1.5-2.1 per log metre, DESIGN Q19); kept out of the flagship, which reads Google as opinion, not recommendation (framing.md FRM-27); the conventional Huff lens is an idea in Notes.
- A 0-30 min walk band: duplicated band 2's mechanism. rev4 L207-208, L217-221.
- Citing Melbourne's 20-minute neighbourhood for band 2: it's a 20-min return walk (~800 m), supports band 1 if anything, and its definition drifts. rev4 L223-226.
- Delivery framing for business audiences: brings back uniform-propensity, platform-rating and availability assumptions. rev4 L287-288.
- Fixed N slots with empty slots left empty (SCR-5 to 2026-10-22): raising N drains the claimed population to zero, breaking the flat-reputation limit (SCR-2). User, 2026-10-23.
- Fractional competitors by normalised occupancy (slots filled with probability-weighted venues, hex split by occupancy): hands the unclaimed share to whoever is present (a lone 10%-reach venue takes the whole hex) and assumes the runner-up reaches exactly when the leader doesn't; replaced by draws (SCR-12). 2026-10-23.
- Weighting 30-min slots by demand: no defensible weight (SCR-13). User, 2026-10-23.
- R̄ from the subject's competitors, weighted by their chance of inclusion: R̄ becomes a local radius ("better connected than your neighbours"), against SCR-6; possible later as a separate figure. 2026-10-23.
- Competitor denial by remove-one reruns or Shapley values: many reruns, and remove-one denials don't add up (two venues both outranking the subject at N = 1 each free nothing alone); replaced by occupancy credits (SCR-14). User, 2026-10-23.
- Truncating competitor sets to the subject's reachable set: competitors need their own horizons. `STALE_handover_rev3_7_delta` L214-220; DESIGN_pre_spine "Settled in chat" (no clipping below 100 km).

## Limitations
- Arrow 2 (reputation → choice): tier threshold, within-tier ordering and fill order are judgements, not estimates; no test available here. `rating_rule_and_visualisation_Sep_28` L58-61; FRM-5.
- Bands are not calibrated to Google's viewport; the ~1 km radius is user-adjustable. rev4 L209-210, L228-229.
- Visibility is assumed, not modelled: for rating to decide within a tolerance, Google must actually
  show the diner the reachable, well-rated venues. First evidence, one phone screen (2026-10-25, 105th): with
  distance held, higher rating places a venue earlier and makes it likelier to be listed; one user (DESIGN.md Q19). 106th: at one place and time the list is near-common across
  two users, devices, languages and accounts (top-20 Spearman 0.96-0.98), so one shared Top-N stands for what
  diners see, ads aside (DESIGN.md Q19). 107th: the order runs from the map's search anchor, distance first
  (Huff-like), then rating and open status; the flagship no longer reads Google's list as its mechanism (framing.md
  FRM-27), so this bears on the first-exposure lens (Notes), not the share rule.
- Top-N is all-or-nothing: the top N by rating win and every other venue gets nothing. If Google only
  tilts the odds towards better-rated venues (Q19 b), Top-N overstates reputation's effect; the N-sweep
  softens the cutoff only in part. Accepted given the project's means (user, 2026-10-13).
- Bands are overlapping diner segments with no population weights (one person may walk one day and
  drive the next), so results are reported per band, never summed or weighted across bands.
- One travel tolerance for everyone, urban and rural: rural diners may tolerate longer trips (user recalls an article; illustration, not checked). Out of scope; separate bands soften it only in part. 2026-10-23.
- Slots count equally over the subject's open hours (SCR-13): busy and quiet slots weigh the same. 2026-10-23.
- Complementary neighbours (user, 2026-10-23, 87th): a venue next door ([subject]'s neighbouring bar) shares every
  hex, so it ranks as a prominent competitor whatever its rating (SCR-15 gives nobody zero). The model counts the
  food diners the two share; it can't see customers a neighbour sends over, drinks, or arrangements between them.
  The cost side is real (a small shop beside a Walmart); the benefit side is unseen. Stated as a disclaimer;
  weighing it is left to the owner (no partner-exclusion scenario, user).
- Discovery searches only (as framing.md FRM-14): shares are of diners searching without a place in mind;
  regulars returning to a known venue don't search (user, 2026-10-23, 87th).
- Accepted (R5): a zero-review venue sits at C, so an unknown venue outranks a known-poor one, since 2026-10-24 across
  the whole field (no tiers): no reviews 4.24 above 4.0 on 500; 3.2 on 9 ≈ 3.85 at m = 15. `rating_rule_and_visualisation_Sep_28` L34-36.
- m measures what a review count says statistically, not how much diners trust it (user, 2026-10-24, 92nd). Diners
  may weigh counts differently: Powell et al. (2017) found people prefer the more-reviewed product even when the
  less-reviewed one is likely better (Claude's memory, unverified; citation check parked). Fake reviews are not
  modelled: shrinkage discounts thin ratings only as noise. σ is set at its maximum on the 1-5 scale, not measured:
  our pulls hold no individual reviews or star histograms (SCR-20).
- Experience vs rating (user, 2026-10-25, 107th): the flagship's diner judges venues they know by experience and new
  ones by rating; the model judges both by rating, so it assumes the two agree on average. Best-of-K and the
  unbinned key treat any gap as decisive; a just-noticeable difference (~0.2-0.3 stars, Claude's guess) is untested.
- Band 3's field is every restaurant within the drive, not peers by format, cuisine or price (needs VEN-8, DESIGN
  Q9); out of scope for now (user, 107th). The owner is asked whether the band's trip is plausible for the venue.
- Searches start at the diner's own hex (SCR-23, user, 108th): a diner who searches a far-off area on purpose (a
  planned trip, a tourist) isn't modelled. The occasion (romantic, expensive) filters the field before rating does,
  and a price can draw a diner in; neither is modelled (no occasion fit per venue; price not in the key).
- Search effort across bands is unknown (user, 2026-10-26, 110th): how a diner's patience and number of candidates
  grow with the catchment they consider isn't known, and likely differs by occasion and context; no data here can
  test it. The bands are a stated convention: each represents a tolerance level, one universal k topped up per
  stage (SCR-23). Equal coverage under uniform speed would need ~3x the looks for band 2's ring (bands 10 / 20 min:
  ring area 3x band 1's; field ratio measured ~4.5x, ring ~3.5x); this shows what coverage would cost, not what
  diners do.

## Notes
- Side note, with caution (user, 2026-10-13): band 1's scale matches Google's ~1 km default mobile
  search radius (observed, no file), so band 1 is a close cousin of the viewport. Not true in all
  cases: a resident on one side of a river with no crossing, a venue straight across. Whether Google
  treats that venue as a candidate is unknown (straight-line vs travel-based candidacy) and untested
  (DESIGN.md Q19), which weakens the viewport argument. Corroborates band 1's scale only.
- Rating field (Sep 28, whole venue file, unweighted): mean 4.2377, median 4.4, IQR 4.0-4.6, skew −1.70,
  excess kurtosis 4.88; review counts median 212, mean 414, max 16,955. Subject 4.8 sits at the 90.5th
  percentile mid-rank (raw, 10+ reviews; ~7% tied at 4.8, so 87th to 94th). C = 4.2377 is provisional.
  `rating_rule_and_visualisation_Sep_28` L90-131.
- Pho A Gogo: ~4.9 on ~17,000 Google reviews vs 3.3 Tripadvisor / 3.5 Yelp; a reminder that reputation
  here is Google's (FRM-7). rev4 L1470-1478.
- Segment likely changes N and travel willingness (fast food reputation-insensitive, high N; fine dining
  low N); the choice is left to the owner. A new entrant can't win on reputation yet: run its expected
  trajectory (day 30 / 180 / 365), not one snapshot. `ideas_textsearch_relevance_Sep_24` L99-113. (idea, DESIGN Q10)
- Brand musings (idea, not planned): for chains, reputation sits with the brand; within-brand variation
  separates branch from brand, and N becomes a measured "revealed reputation sensitivity" ([subject] is a
  messy-middle case). Brand demand can't be measured by review counts (circular). A campaign that raises
  N is brand work; one that shifts only the level is a global multiplier. A spending decision needs the
  cost of a rating increment against spend per person reached; report a CI on N. Same doc L115-148.
- "Peers" in SCR-14 are similar in rank and reach only: cuisine, price or format need the venue enrichment
  pull (VEN-8, DESIGN Q9) before peers can be filtered by type (2026-10-23).
- Locational vs reputational quadrant map (musing): a low-reputation venue in a 4.9 field is a trap; no
  rent term; good sites select better operators. rev4 L1516-1520.
- Share-rule criteria (user and Claude, 2026-10-23, 84th discussion; illustrates how SCR-15 was chosen, FRM-25: the
  choice is defended, not the model). Criteria were drawn up alongside q, partly in reaction to Top-N's defects, not
  pre-registered. Pass ✓, fail ✗, partly ~ (Claude's scoring, user-reviewed in discussion):

  | Criterion | Top-N | Linear rank | Huff | Logit (Yelp beta) | Flat 1/K | Exposure | Persistence q |
  |---|---|---|---|---|---|---|---|
  | C1 better-rated never gets less | ✓ | ✓ | ✓ | ✓ | ✗ | — | ✓ |
  | C2 nobody in reach gets zero | ✗ | ✓ | ✓ | ✓ | ✓ | — | ✓ |
  | C3 ties equal | ✓ | ✓ | ✗ | ✓ | ✓ | — | ✓ |
  | C4 worse entrant never helps an incumbent | ✓ | ✗ | ✓ | ✓ | ✓ | — | ✓ |
  | C5 few options still favour the better | ✗ | ✓ | ✓ | ✓ | ✗ | — | ✓ |
  | C6 no distance effect within a band (SCR-4) | ✓ | ✓ | ✗ | ✓ | ✓ | — | ✓ |
  | C7 one guessable parameter, ends best-takes-all and flat | ✓ | ✗ | ✗ | ~ | ✗ | — | ✓ |
  | C8 computable from our data | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
  | C9 rule and parameter source model a split among a defined set | ~ | ✗ | ✗ | ✗ | ✗ | — | ✓ |

  Exposure = modelling what Google shows (Claude's reading; not computable, SCR-1). Top-P by rating bar and the
  absolute floor not scored (definitions not pinned). Logit fails on its beta's source, not its form (C9).
  Outside evidence per criterion, other fields, qualitative ("does this happen"); **all citations from Claude's
  memory, unverified (check owed)**: C1 Yelp revenue (Luca 2016, ~5-9% per star, within-restaurant over time) and
  reservations at rounding thresholds (Anderson & Magruder 2012); C2 random-utility / Luce choice (no option at zero),
  consideration sets (Hauser & Wernerfelt 1990); C4 regularity, counter-evidence the attraction / decoy effect (Huber,
  Payne & Puto 1982): C4 is our choice; C7 / C9 attention falls with list position (eye tracking, Joachims et al.
  2005; cascade click models, Craswell et al. 2008); C6 counter-evidence: gravity / Huff models find continuous
  distance decay (a framing choice, SCR-1 / SCR-4); C3, C5, C8 fairness or feasibility, no literature needed.
  Citation check parked (user, 2026-10-23, 87th) until a proper literature review; until then these read as our
  own reasoning, not as sourced.
- Rating-rule criteria (user and Claude, 2026-10-24, 92nd discussion; how SCR-20 was chosen, FRM-25). The function
  maps what a diner sees (displayed rating r, review count n) to a place in SCR-15's ranking. Pass ✓, fail ✗, partly ~
  (Claude's scoring; criteria "look ok", user). T = the retired tiers; S = shrunk score binned at 0.1; S* = unbinned
  (adopted, SCR-20); D = trust draws; L = lower confidence bound; E = more reviews wins near-ties.

  | Criterion | T | S | S* | D | L | E |
  |---|---|---|---|---|---|---|
  | R1 higher rating at the same count never ranks lower | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
  | R2 no wall: no count where one more review jumps a venue's standing | ✗ | ~ | ✓ | ✓ | ✓ | ~ |
  | R3 many reviews: position matches the displayed rating | ✓ | ~ | ✓ | ✓ | ~ | ✓ |
  | R4 zero reviews placed by the same rule, no separate tier | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ |
  | R5 thin evidence pulls toward the field mean, not to the bottom | ✗ | ✓ | ✓ | ✓ | ✗ | — |
  | R6 one parameter; ends m → 0 raw rating, m → ∞ ratings stop mattering | ✗ | ✓ | ✓ | ✓ | ~ | ✗ |
  | R7 parameter has a source (fitted, or an owner's plain-words guess) | ✗ | ✓ | ✓ | ✓ | ~ | ✗ |
  | R8 only Google's numbers are shown (ordering only) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
  | R9 inputs r, n and a global prior only (no prior per hex) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
  | R10 fits the share step's exact counts, no extra Monte Carlo noise | ✓ | ✓ | ~ | ✗ | ~ | ~ |
  | R11 a diner story: the rule describes something diners do | ~ | ~ | ~ | ✓ | ~ | ✓ |

  Anchors at m 15 (C 4.25, 93rd diagnostic): subject 4.8 on 1,664 → 4.79; 5.0 on 10 → 4.55; 5.0 on 42 (the 5.0 median) → 4.80,
  ties the subject; 4.9 on 132 → 4.83; 4.8 on 188 → 4.76; no reviews → 4.25.
  Fits (92nd ad hoc; recomputed by diagnostics/rating_shrinkage_m.py, 93rd; venue table,
  18,213 rated): (1) a free empirical-Bayes fit over the field, Var(r | n) = τ² + σ²/n, gives σ 2.3-2.8 stars at n ≥ 5 / 10 (1.5 with every count; 93rd),
  above the 2-star maximum on a 1-5 scale: spread falls faster with n than sampling noise allows (survivorship:
  weak venues close before collecting reviews) and rises again past ~900 reviews (chains, mean 4.18); its m (33-59)
  is not used. τ ≈ 0.40 from the 300-900 review groups holds. (2) dropped (user, 93rd): not reproducible (filter unrecorded), and 15 days of changes carry almost
  no sampling signal (of 442 venues with new reviews, 395 unchanged on display, 43 rounding flips; diagnostic
  docstring). The 92nd's reading: σ from rating changes between the venue table
  and the 2026-10-10 hours pull (drift is the term that doesn't fall with new reviews; mean shift ~0, user's point):
  71 usable venues, σ 1.65 (95% 0.70-2.31), drift sd 0.24, m ≈ 17: supports the scale-ceiling m, can't replace it;
  σ for 4.7-5.0 venues (1.5) exceeds their 0.62 bound, so other noise is in the changes (deletions, filtering).
  A 5.0 excess at low counts (fake-review signature) is not visible under a normal model, which is too crude to clear it.
  How others do it (Claude's memory, unverified, citation check parked): IMDb's weighted rating (m by hand); Wilson
  and Dirichlet lower bounds (Evan Miller); empirical Bayes (Efron and Morris; Robinson's prior varying with log
  count); Bühlmann credibility (k = within / between variance, from each unit's own history).
- Share report (94th; `scoring_report.py`, `functions/share_report.py`, `functions/census_profile.py`): headline in
  persons per open slot of the subject (sum over slots / sum of its open chance, SCR-13); competitor CSV, one row per
  band and venue: denial, immediate rivals above / below, named at >= 1% of the band's ceiling (SCR-14). Census profile
  of captured vs reached persons per band beside Greater Melbourne (DESIGN demographic showcase; residents by SA2,
  workers by DZN, each hex takes its area's mix). First reading: band 1 captures young (51% aged 20-39 vs 31%),
  low-car (20% no car vs 9%) residents; band 2 captures older, more car-owning residents than it reaches (it wins at
  the band's quieter edge); band 3's profile rests on ~1 person. 2021 was a lockdown census ("worked at home" 52%).
- Rating-rule grade sheet (94th, user and Claude; a grade argued over, not a hard bar, user): R1-R11 above, R3 to
  read "when both have many reviews and the gap is >= 0.2", plus R12 a lower displayed rating can overcome a higher
  one through review count (user: the review-count study finds diners credit a large count in itself); R13 thin-
  rating inflation corrected (a thin 5.0 placed within its review-count peers); R14 near-equals tie (same displayed
  rating, both well-reviewed); R15 blind plausibility (the user judges pairs the variants order differently, rules
  hidden). Output effects reported, not graded. Controls (user): F, the flat displayed rating, ties within 0.1, no
  inference of ours (the direct reading); S*, shrinkage at m 15 (the convention, SCR-20 as built). Challengers, each
  reading a displayed 5.0 as 4.975 (the middle of its 4.95-5.0 range; other ratings sit mid-range already; F needs
  no such reading, 5.0 is its top tie either way): S*' (S* with that reading), B (shrunk rounded to 0.1), B~
  (smoothed bins, weight shared within 0.1, fading), P (percentile among the 500 venues nearest in log count, ties
  midrank; 250 / 1,000 as sensitivity), R (shrink toward C(n), mean rating fitted on log count; Robinson). Facts
  behind it (venue table 2026-09-25): venues rated 5.0 have median 7 reviews (quartiles 2-34); 49% of venues with
  <= 5 reviews show 5.0, 0.2-0.4% above 500; median rating 4.7 at <= 5 reviews vs 4.3-4.4 from 11 up (inflated, not
  just noisy: shrinkage to one C assumes noise only; user's promotion / fake-review story). Rounding the shrunk key
  to 0.1 at m 15 keeps a displayed 4.8 only from ~150 reviews (4.9 ~180, 5.0 ~210; ~420 at 4.975): a count threshold
  with a cliff at the edge (R2). The subject's 4.8 on 1,664 tops 94% of venues with 1,000-2,500 reviews.
- q in plain words (Claude, 2026-10-23, 87th; proposed wording for the owner's first question): in a cascade, a
  diner takes an option if it clicks, else looks on, so q ≈ the chance an option doesn't click; 0.8 = a diner
  passes on about four in five places they look at. Satisficing and search theory are the framing (unchecked).
- Niche-tag standing (idea, user, 2026-10-23, 87th; not planned): the same share rule run on only the venues
  carrying a tag (taco, Mexican, seafood). Owner agency: Google categories partly follow the owner's Business
  Profile, so "if we add 'seafood', where would we stand?" is a cheap what-if (add the subject to the tag field).
  Reported as standing (rank, percentile, share of the niche field), never people: the share of diners searching
  by cuisine is unknown. Wording: "among venues Google tags X", not "among X searchers". Gate: ~14,500 ring rows
  carry only coarse Legacy tags, no cuisines (VEN-8), so it needs the tag enrichment (DESIGN Q9, paid, S5). A
  pilot preview could use only rows already tagged, after counting how many of the subject's competitors are.
- Hours-overlap competitor pool (idea, user, 2026-10-24, 95th; not planned; talked through in a build session): a
  competitor's weight in the pool is its hours overlap, on the competitor's side only: the share of its predicted open
  time (VEN-13 tag profile) inside the subject's profile, the subject's own hours blinded and predicted from its tags
  (real hours are de facto, not what venues like it target; user). The subject's side reads ~100% for anything open
  whenever the subject is, and a two-sided measure double-counts the slot filter (SCR-13). A weight, not a cutoff
  (user: demand is not exclusive; a cafe's lunch, a 24/7 forecourt pie or McDonald's partly substitutes). Applied as
  an in-pool chance, a third draw beside reach and hours (user: like catchment probabilities); Claude's lean: per venue
  per run (fits the open-count matrix C), per hex only if MC error demands it. The effect sits with venues ranked above
  the subject (venues below enter only through K; q^K ~ 0). Over niche tags: how close two tags are is measured by
  what venues do with their hours, not judged (user). Limits: a 24/7 McDonald's and a fuel station score alike;
  coarse Legacy-tag rows fall back to a generic profile (VEN-8 gap, accepted, user); the chance is unanchored
  (FRM-25). Free checks first: cafe vs 24/7 separation (a 7-15 cafe may score ~0.3, as 24/7 does); counts of
  near-24/7 and of high-rated low-overlap venues in the subject's reach. Kept out of Q29.
- Rating-rule and pool runs (96th, autonomous build; DESIGN Q29; first readings, not decisions):
  `build_shares(rating_key, pool)`. Bands 1-2, q 0.7, donor hours, subject at 4.8, persons per open slot (b1 / b2):
  S* 1,270 / 951 (equals the 94th run exactly); F 522 / 115; S*' 1,270 / 960; P 1,747 / 1,606; niche (strict
  mexican_restaurant, 85 venues) 8,881 / 26,236; overlap 1,647 / 1,961; every competitor at overlap's mean chance
  (Claude's control) 1,738 / 2,037. Ceilings hold (~11.6k / ~64k). Pairs: F and S* order 51% of thin-5.0 vs
  well-reviewed pairs differently; S*' vs S* 0.1% of all. Blind pairs (R15; user, 30 drawn from disagreements):
  S*' 21, S* 19, P 10, F 7; only F ties, the user tied 8 (same rating, counts within ~2x). Overlap chances are
  compressed (median 0.75; generic-tag venues 0.75, cafes 0.57, near-24/7 0.49): as built the pool thins evenly.
  Niche: in small pools the q rule gives low-rated rivals large shares; untagged Mexican-named venues (5 / 27 in
  bands 1 / 2) don't count: "few tagged on Google, not few in Melbourne" (user's disclaimer). If S*' is adopted,
  both ends read mid-range: 5.0 as 4.975, 1.0 as 1.025 (user). Report
  `outputs/scoring/-37.76870_144.97196/q29_96th/REPORT_20261024.md`; `diagnostics/rating_rule_disagreement.py`,
  `diagnostics/hours_overlap_pool_checks.py`.
- Catchment illustration (88th, ad hoc; script `outputs/reachability/logs/catchment_illustration.py`, git-ignored;
  figures `outputs/reachability/first_look/catchment_illustration_20261023_*`): a hex is painted in its fastest
  band with chance >= 10% (display only; SCR-12 uses the chance), no stacking; opacity by chance, or by decile of
  residents x chance within each panel; competitors = venues in view reaching a >= 10% subject hex in the same band
  (hours not applied). Residents only (user): Mon-Thu 19:00 and Sat 12:30; workers only for a weekday-lunch
  what-if on an owner's request (weekday jobs; the subject is closed weekday lunch). Readings: ~11k / 50k / 566k
  residents expected (bands 1 / 2 / 3, Mon-Thu 19:00), Sat lunch 9k / 43k (transit); competitors sit outside the
  bands (the CBD cluster reaches the subject's south arm); band 3's chance is near 1, so its value follows density.
- Rating maps and q sweep (98th, ad hoc, Claude's scripts in `outputs/scoring/-37.76870_144.97196/rating_maps_98th/`,
  git-ignored; user's request): the slider widened to 3.5-5.0 (user) and build_shares writes `hex_shares_focal`
  (share per hex at every slider rating, headline rule and q); run of record bands 1-2 only (`reach_table_893947a445/
  shares_fdddd5b96d`). Resident score maps in the catchment illustration's format (Mon-Thu 19:00, bands 1-2; opacity
  = residents x share in 10 log steps 0.01-30 per hex, one scale for all ratings; pooled deciles saturated); each map
  states the n 5- or 1-star reviews in a row to reach it (from 4.8 on 1,664; range for 4.75-4.85; the model holds n
  fixed). Residents captured (b1 / b2): 4.2 11 / 0; 4.5 98 / 4; 4.7 472 / 123; 4.8 1,127 / 788; 4.9 2,701 / 7,802;
  5.0 3,126 / 14,648. q sweep at 4.8 (persons per open slot): band 1 flat near its peak at 0.7 (~1,270), band 2 steep
  (q 0.6 ~590, 0.8 ~1,530, peak 0.9 ~2,030). The cliff's reading (99th discussion, user and Claude): a ramp, not a
  stair (per 0.1, b1 ~x2.1-2.4 from 4.5 to 4.9, b2 x5-10, both flat 4.9 -> 5.0); each step's size is q per rival
  passed (SCR-15, rank only). 4.8 -> 4.9 at n 1,664 passes 580 venues field-wide (455 displayed 4.9s on fewer
  reviews, median 169; 87 5.0s), 4.9 -> 5.0 only 77: the jump is the shrinkage claim (more reviews wins at the same
  display), not a perceived-decimal flip. User: a 4.9 on 1,664 is unrealistic (in 1,000-2,500 reviews 4.9 is 28 of
  1,694, 5.0 5), so the steep top is an artefact of the slider's fixed n, not of the rule; SCR-20's key S*' stays
  (the decimal flip covers how steps read, not rival order). Answer: SCR-22. The in-a-row captions are dropped.
- m reruns and break-even pairs (101st build, DESIGN Q31; runner and compare in `outputs/scoring/-37.76870_144.97196/
  q31_101st/`, git-ignored). Full default run (bands 1-3) rewrote `shares_fdddd5b96d`: bands 1-2 equal the run of
  record exactly (headline 59,136 rows, hex_shares_focal 2,837,584, max diff 0); report and profile end to end (band
  3 0.96 persons). m 9 / 15 / 35 / 48 (bands 1-2, S*', donor, q 0.7), the 4.8 headline in persons per open slot: b1
  1,226 / 1,270 / 1,959 / 2,495, b2 718 / 960 / 2,958 / 4,443. m moves 4.4-4.9 only (5.0 flat, b1 4.9 flat); a larger
  m lowers the 4.8 -> 4.9 step (b1 x2.5 -> x1.3, b2 x11.3 -> x3.1) and band 1's q peak (0.70-0.75 at 15, ~0.35 at 48);
  thin 4.9s drop below the subject (Ari.BKK, 94 reviews: 1,292 -> 470 denied). The 96th's blind pairs agree on 55%
  of decided pairs at m 9, 95% at 15, 91-95% from 15 to 120 (none tests a 4.9 on 100-400 vs a 4.8 on 1,000+).
  Break-even pairs (`diagnostics/rating_break_even_pairs.py`: 24 synthetic pairs, "where would you go"): first judge
  the user's partner (self-report: consciously count-led, not universal; her trust floor is the original 60): the
  larger count in 23 of 24 (exception 4.9 on 300 over 4.8 on 600); no m fits; rating + β ln n fits all 24 for β
  0.09-0.14, the user's 96th pairs for β > 0.15 (Claude's rule, fitted after the answers). More judges (user).
  102nd judges (best-fit m by a scan over 0-3,000, ad hoc script not kept): the user, not blind, 20 / 24 at m 14-17
  (5.0s declined at 15 and 40 reviews, taken at 80-250; 4.9s mixed at 150-220); the partner 20 / 24 at 132+.
  LLM judges, questionnaire text only (illustration, not evidence): without reasoning, coherent, Kimi 2.8, Gemini 3
  Flash, Opus (project context seen), Haiku m 48-60; reasoning, Gemini with thinking 38-47, Kimi 3.1, Sonnet, GPT-5.6
  Luna with thinking 28-37; DeepSeek with thinking named the test (shrinkage) and fit 14-17; GPT-5.6 Luna and
  DeepSeek without thinking answered A on 20 and 22 of 24, repeats disagreeing (position bias, dropped). Q8 and Q20
  (pairs below C, where shrinkage lifts the thin side) fit no judge but the user and DeepSeek with thinking. A
  rerun should swap sides per judge. Files `rating_break_even_pairs_20261025_judged_*.csv` (output_backup
  `break_even_judges_102nd_20261025`).
  106th judge, the user's sister (Korean translation of the sheet; file `_judged_sister.csv`, output_backup
  `break_even_judge_sister_20261025`): the larger count in all 22 decided pairs; m 141+ (20 / 22), β ln n fits
  all 22 from 0.11; "same" on Q19 (4.9 on 300 vs 4.8 on 600, a β of ~0.14) and Q20 (4.1 on 900 vs 4.0 on 25, no
  rule fits). Her reason: many reviews stop attracting at a low rating. The rescore gives the partner β 0.11-0.14,
  not 0.09-0.14 (method of the 101st's fit not kept).

- Flagship narrative (user, 2026-10-25, 107th discussion; framing.md FRM-27): diners who have been around use Google
  as opinion, not recommendation; ratings are a ruler calibrated by places they know ([subject] at 4.8 is "okay", so a 4.4
  reads "slightly less nice"), so comparison is by rank within reach. Bands 1-2: casual, few look-ups. Band 3: the
  special occasion, the same ruler on a wider field with more search; the same rating can earn a share in bands 1-2
  and nothing in band 3 (a 4.5 among 4.8s). Evidence for the comparison step: the break-even judges (DESIGN Q31),
  pairs shown by rating and count only; limits: pairs not sets, stated not revealed choices, few unsystematic
  judges, the LLM files illustration only.
- Best-of-K (candidate, DESIGN Q32; Claude's proposal, user agreed in discussion): rank r's share with equal
  encounter is C(M-r, K-1) / C(M, K). Example M 100, K 4: rank 1 4.0%, 10 3.0%, 25 1.7%, 50 0.5% (fair share 1%);
  q 0.7 gives rank 1 30%.
  108th (decided, SCR-23; worked examples, not runs). Random K: s_r = sum_j p_j C(M-r, j-1) / C(M, j), j = 1..M, K
  beyond M seeing all M. Geometric p_j = (1-p)^(j-1) p, p = 1/k (Poisson: K = 1 + X, X ~ Poisson(k-1)). M 5, k 2:
  geometric 0.388 / 0.225 / 0.163 / 0.125 / 0.100; Poisson 0.399 / 0.252 / 0.166 / 0.110 / 0.074; q 0.5
  0.516 / 0.258 / 0.129 / 0.065 / 0.032. M 100, k 3.3 vs q 0.7 (%): rank 1 3.33 vs 30.0, 10 2.25 vs 1.2, 50 0.71
  vs ~0, 100 0.30 vs ~0. Rank 1 gets E[K] / M for any shape; the bottom gets p_1 / M (geometric: 1/(kM)). Criteria
  (Claude's scoring, user accepted C4): C1 within a ring, C2 by random K, C3, C5, C7, C8 pass; C4 fails (a worse
  entrant helps rank r when rK > M + 1), accepted as principle; C6 nesting only; C9 partly (k from the owner).
  Stages (user's idea): a venue's chance of being seen is about the sum of k / M_b over the stages whose field holds
  it, so inner venues build up chances. Exposure per venue (Claude's idea, not adopted: unmeasurable): each venue in
  the pool with its own chance g_i, the best remembered wins, P(i) = g_i x product over better j of (1 - g_j)
  (Manzini-Mariotti); the "remembered nothing" mass would be a fresh, distance-led search (the Huff lens below).
  Growth with the field (Claude's, unbuilt sensitivity): K = k (M / M_ref)^a, a 0 fixed, 1 proportional.
  109th build (autonomous; DESIGN Q32 "Build"): closed form A(X) = product over stages of h(x_s, F_s),
  h(x, F) = sum_j p_j C(F - x, j) / C(F, j); a cell's group wins with A(cells above) - A(cells at or above), split
  within the cell by seen chance. Checks pass (`diagnostics/best_of_k_checks.py`); the 108th's Poisson rank 2 above
  is 0.2514 exact (0.252 a hand-rounding slip); the worked examples' "k 3.3" is 10/3. Independent stages vs "minus
  those seen": subject's share median ~0.1%, worst 1.2% apart. Config: SCORING_HEADLINE_K = 10/3, marks 2.5 / 3.33 /
  5, a k grid 1-10, geometric headline, Poisson the switch.
  110th speed-up (build; status): h runs in a numba loop (one element at a time, no array temporaries, 12 threads)
  over all k at once, since C(F - x, j) / C(F, j) doesn't depend on k; equal to the 109th code to 8e-16 on
  synthetic counts (both shapes, empty hexes, fields under L). Units run in worker processes (spawn pool, each
  rebuilds the setup in ~7 s; config SCORING_STAGED_WORKERS 4): band 1 at 1 / 3 / 4 / 6 workers 597 / 134 / 125 /
  119 s, outputs equal the serial run (credits within 1.4e-14: BLAS summation order). Each worker recomputes the
  shared hours draws (~5 s, ~320 MB at 400 draws): a parent-side precompute is parked (the user's idea; worth it
  past ~6 workers). Staged runs donor hours only (SCORING_STAGED_HOURS_RULES; all_open deferred, user).
  Precision pilot (band 1, k 3.33): 0.5% vs 1% stop target, 15,768 vs 6,792 draws, 599 vs 122 s; band total
  32,025 vs 31,778 persons (-0.77%), worst slot -2.2%; hex shares mean |diff| 0.0013 (mean 0.021). Hours draw d is
  shared by every unit, so slots err together: the first 64 draws sit 1.25 se below the rest in the band total
  (chance), and the report's band MC error (`share_report.headline_table`, slots summed as independent) is ~3x
  too small: ~39 persons reported vs ~133 from per-draw band totals at ~400 draws; ~329 (1.0%) at 64. The same
  holds for q. Rule comparisons gain: q and staged share the draws. Runners and logs:
  `outputs/scoring/-37.76870_144.97196/staged_110th/` (git-ignored).
  112th (autonomous build, then the user at the desk; status): band 3 built: `scoring.build_band3_table` (the
  band-3 pass's fields per slot, RCH-27), `band3_levels` (stages 1-2 from each hex's point, stage 3 the drive rows,
  fields nested by union: Claude's choice), staged units per slot for band 3. Report MC error from per-draw band
  totals (`share_report.band_mc_se`, user: yes; q's 4.8 b1 / b2 / b3 ±2.5 / 2.7 / 0.04 -> ±10.4 / 10.6 / 0.12).
  Speed (pilots, `outputs/.../staged_112th/`): a band-3 unit 68,697 hexes x 6,522 venue hexes, ~1,030 s and 8.3 GB
  at 56 draws; rows where the subject is not entered (and closed draws) skipped: outputs equal to 1e-15, 1.5x;
  block 2048 (`SCORING_HEX_CHUNK`): 4.4 GB, so 2 workers: ~370 s per unit. Stop rule: Mon-Thu units hit the 400 cap
  (band 3 ~80 min each, MC 0.70%) because draw d takes weekday d mod 4 (Monday ~30% below Thursday) and the stop
  check's spread includes that gap, which the cycle cancels; on band-1 draws the naive error is 1.3-1.4x the
  stratified one. Two runs halted (user) before band 3 finished; nothing written. Band 1 vs q 0.7 (110th staged
  run, 4.8): 786 vs 1,270 per open slot (0.60-0.64 in every slot); slider 3.5-5.0 x11 vs q's x560 (a ramp, not a
  cliff); k 1 / 3.33 / 8: 369 / 786 / 942 (q peaks at 0.70-0.75); knee positions (4.2 -> 4.3 start, 4.8 -> 4.9
  burst) the same at k 2.5 / 3.33 / 5, heights scale with k.
  Kept (user, 112th): a = 0 (k does not grow with the field): attention caps lookups, and exposure is not
  consideration; density-scaled search and an exposure-weighted encounter go to future work (unknown a, as Huff's λ).
  113th (discussion, user; DESIGN Q32 "Speed-up review"): independent stages (109th, Claude's) approved; the
  stratified stop check approved to build; the parent-side hours precompute dropped; the GPU port goes to a two-step
  pilot (CPU phase profile, then a CuPy copy of one band-3 unit) before any build.
  114th (pilot, autonomous; DESIGN Q32 "GPU pilot"): a CuPy copy of band-3 unit Fri_1730 runs 6.3x the CPU per draw
  (1.84 vs 11.55 s); the same draws give equal per-draw subject persons; ~150 s per unit misses the ~90 s go rule;
  `np.diff(..., prepend=0)` in `staged_unit` promotes `rings` to float64. Port or stop owed.
  116th (user; DESIGN Q32 "GPU port decided"): port, since rescoring is likely; GPU runs draw their own seeded
  uniforms (mean-comparable to CPU runs, not draw for draw); the CPU path stays as reference; not built.
  117th (autonomous build; DESIGN Q32 "GPU port built"): built and verified; staged run of record bands 1-3 (76 min).
  At 4.8, k 3.33: 786 / 1,443 / 2,360 persons per open slot (q 0.7: 1,270 / 960 / 1.0). Band 3 rises most: a far
  diner searches its own transit fields first, so the subject is no longer lost in the whole drive field. The slider
  flattens (4.9: band 3 3,932 vs q 12,799; 3.5: band 1 114 vs q 6). The k curve peaks near k 6-8 in bands 2-3 and
  then falls (more looks find more better venues). Top band-3 deniers change: nearer 4.9s lead, far 5.0s drop.
- First-exposure Huff lens (idea, user, 2026-10-25, 107th; an extension, not planned): newcomers (residents and
  workers who just moved in or started a job) use Google as an oracle. From each resident and worker hex, weight
  exp(beta_rating * rating - lambda * ln straight-line distance) over nearby venues, lambda ~ 2 (textbook; screens
  1.5-2.1), beta_rating from the screens; the venue's figure is its population-weighted share. Assumes newcomers
  are spread like the population and search centred where they live or work. Reported beside the flagship, never
  added; labelled first-exposure share, not demand; conventional, no novelty claimed; answers "why not Huff?".
  Cost: straight-line distances and one formula, no routing. Kept here, not in future_work.md (that file is for
  out-of-scope studies). Literature on online ratings as Huff's attractiveness: unchecked (framing.md Notes).

## Open questions
- DESIGN.md Q31 (m for the shrunk key: 15 a placeholder headline (102nd); reruns done 101st, m matters; shrinkage
  vs a count-as-demand rule vs a threshold plus small m; statistical or behavioural route; real people next). Q29
  closed 2026-10-24 (97th): S*' (SCR-20).
- DESIGN.md Q30 (band 3's headline: the unlock rating, user's lean; its threshold).
- DESIGN.md Q32 (decided 108th: staged best-of-K, SCR-23; open: the build, band 3 nesting check, reruns).
- DESIGN.md Q19 (planned diagnostic: (a) is Google's candidate set straight-line or travel-based;
  (b) does Google favour better-rated venues within reach). SCR-1, SCR-2 and SCR-4 rely on both.
- DESIGN.md Q5 (edge flag: venues whose cost horizon reaches the grid or extract edge are excluded from
  R̄ and owner percentiles; decided 2026-10-23, user; threshold set at build, `hex_block_Sep_27` §1).
- **S1 (merge).** Band edge convention: settled 2026-10-16 as SCR-10 (round to the nearest minute, as
  displayed); still open is how r5py delivers it. Google shows rounded minutes, so "Google shows ≤ N
  min" ends at ~N·60 + 30 s (~630 s, ~1,230 s). r5py's `TravelTimeMatrix` reports whole minutes rounded
  down, so the only edges it offers are < 600 s (≤ 9 min, misses 600-629 s) or < 660 s (≤ 10 min, adds
  630-659 s); 630 s needs second-resolution output (`DetailedItineraries`). Tested so far: Google's
  rounding on 10 walk pairs (WLK-4); r5py truncation read from R5 source only. Test before choosing.
  `time_resolution_Sep_21` L21-51.
- ~~**S3.**~~ Pick m for ordering inside the low-evidence tier. Closed 2026-10-24 (92nd discussion, user): the tiers
  are retired and m is fitted (SCR-20). `rating_rule_and_visualisation_Sep_28` §1b, §1e.

## Changes
- Changes to 2026-10-20 (SCR-1 to SCR-10): snapshot, "Changes".
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
- 2026-10-23 · SCR-2, SCR-3, SCR-5, SCR-6 revised; SCR-11 to SCR-13 added (79th discussion, user): contestable hexes, reach by draws, slot size 1/min(N, K), per-slot hours; SCR-14 (competitor measures); Q5 edge flag decided
- 2026-10-23 · SCR-14 (81st discussion): competitor cutoff for reporting only, never in the computation
- 2026-10-23 · SCR-15, SCR-16 added; SCR-2 demoted to a considered variant (83rd, user, discussed during a build session): persistence q headline at 0.7, owner pre-registration of q; knock-ons owed (DESIGN Q28)
- 2026-10-23 · header status line and SCR-15 wording (84th discussion, user): rules are a chosen representation, low conviction (FRM-25)
- 2026-10-23 · Notes "Share-rule criteria" (84th discussion, user): criteria x candidates matrix, C9; logit kept as a demand-lens variant (fails C9 as headline)
- 2026-10-23 · Q28 closed (87th discussion, user): SCR-1, SCR-3, SCR-4 (proximity tie-break dropped), SCR-5, SCR-14 contention, SCR-16 reference marks and owner screen; Limitations: complementary neighbours, discovery only; Notes: citation check parked, q in plain words; SCR-16 scroll-depth question (q = 1 − 1/k); Notes: niche-tag standing (idea)
- 2026-10-23 · SCR-17 reach table built (88th, user: 1% floor, every open slot); SCR-13 slot weights equal by default, owner option later; Notes: catchment illustration
- 2026-10-23 · SCR-13 hours by donor draws, SCR-18 headline population, SCR-19 share step design (90th, user); Not adopted: tag-closure rule
- 2026-10-24 · SCR-13 donor hours built, Mon-Thu day stratified; SCR-19 share step built, exact counts, absolute MC floor (91st, Claude's build choices)
- 2026-10-24 · SCR-4 revised, SCR-5 retired, SCR-20 added (92nd discussion, user): shrunk rating for ordering only, unbinned, no threshold or tiers, m fitted (≈ 15, σ at the scale ceiling); SCR-19 ordering key to rebuild; S3 closed; Not adopted: rating-rule alternatives, shrinkage entries revived; Limitations: statistical m vs diner trust, σ unmeasured; Notes: rating-rule criteria R1-R11, fits
- 2026-10-24 · SCR-20 C 4.25 (precision-weighted) and evidence diagnostic, m 15 (93rd build); SCR-19 cell layout (user); Notes: snapshot fit dropped (user), free-fit figures
- 2026-10-24 · SCR-21 SWOT appendix and opening-hours recommendation, 50% peer threshold (94th, user)
- 2026-10-24 · SCR-19 layout built, first full run; SCR-14 contention built as immediate rivals (user's name and OK); Notes: share report, rating-rule grade sheet with controls F and S* (user); open: Q29, Q30 (94th, autonomous build, user)
- 2026-10-24 · Notes: hours-overlap competitor pool idea (95th, user; not planned)
- 2026-10-24 · Notes: rating-rule and pool runs, blind pairs, S*' end readings (96th, autonomous build, user)
- 2026-10-24 · SCR-20 key S*' (5.0 as 4.975, 1.0 as 1.025), m 15 the headline; Q29 closed, DESIGN Q31 (m) opened; Not adopted: percentile key (97th discussion, user)
- 2026-10-24 · SCR-20 S*' the code default (both ends); SCR-16 slider 3.5-5.0 (user); Notes: rating maps and q sweep (98th build, user's request)
- 2026-10-25 · SCR-22 rarity line on the rating slider (replaces the in-a-row caption); Notes: cliff reading (fixed-n artefact, S*' stays) (99th discussion, user)
- 2026-10-25 · SCR-22 built (report, rating maps); wording: N in 10 above a third, per 1,000 above 300, NONE in capitals; 883 not 912 (100th build, user)
- 2026-10-25 · Notes: m reruns and break-even pairs (101st build; DESIGN Q31 evidence, the 60's origin, the user's count-as-demand point)
- 2026-10-25 · Notes: 102nd judges (the user, LLM illustration); Open questions Q31 line: m 15 a placeholder, routes, threshold option (102nd discussion, user)
- 2026-10-25 · Limitations (visibility): first evidence from one phone screen (105th build; DESIGN Q19)
- 2026-10-25 · Limitations (visibility): common list across users, devices, accounts; Notes: 106th judge (the user's sister) (106th build; DESIGN Q19, Q31)
- 2026-10-25 · SCR-15 story retired, best-of-K the candidate (DESIGN Q32); Not adopted (decay): an exposure rate exists, kept out; Limitations: visibility reading, experience vs rating, band-3 field; Notes: flagship narrative, best-of-K, first-exposure Huff lens (107th discussion, user)
- 2026-10-25 · SCR-23 staged best-of-K added (geometric K per diner, owner's k, stages by band, unbinned ties); SCR-15 to be replaced once built; SCR-1 q wording retired; Limitations: searches from home, occasion and price; Notes: best-of-K worked examples, criteria, exposure and field-growth ideas (108th discussion, user)
- 2026-10-26 · SCR-23 built for bands 1-2 (109th build, autonomous): status line; Notes "Best-of-K" 109th build line (checks, cost of independent stages, a worked-example slip)
- 2026-10-26 · SCR-23 sped up (110th build): status line; Notes "Best-of-K" 110th line (numba, workers, precision pilot, MC error understated); Limitations: search effort across bands unknown (user)
- 2026-10-26 · SCR-23 band 3 built (112th): status line; Notes "Best-of-K" 112th line (band-3 table and levels, band MC error, row skipping, Mon-Thu stop rule, band-1 readings vs q, a = 0 kept (user))
- 2026-10-26 · SCR-23 Notes "Best-of-K" 113th line: speed-up review (independent stages approved, stratified stop check OK, parent precompute dropped, GPU pilot first; user)
- 2026-10-26 · SCR-23 Notes "Best-of-K" 114th line: GPU pilot results (6.3x per draw, misses the go rule, float64 promotion found; port or stop owed)
- 2026-10-26 · SCR-23 Notes "Best-of-K" 116th line: GPU port decided (user), GPU-drawn uniforms, CPU path kept as reference
- 2026-10-26 · SCR-23 run of record (117th, autonomous): status line; Notes "Best-of-K" 117th line (GPU port built, headline vs q, readings)
