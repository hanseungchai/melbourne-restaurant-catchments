# Future work

Studies worth doing that sit outside PLATICA's scope: not planned, not part of the build. In-scope ideas not yet
tested live in `musings.md`; decisions live in `concepts/`. Opened only when a task points here (INDEX.md).
Each entry: date and origin, the question, why it matters, what it needs, how it reuses PLATICA's infrastructure.
Moved out of DESIGN.md's "Future work" section 2026-10-22 (user); out-of-scope musings moved in the same day.

- **Whose walk does Google assume?** (2026-10-21, user.) Google's default transit route behaves as if a walking
  minute costs ~1.7 arrival minutes (TRN-16, `transit_walk_weight.py`), and a single weight explains at most 96% of
  its choices: a deliberate assumption about walking ability and tolerance. As a de facto standard, whom does its
  average represent, who is misled or under-served when it does not match their ability (older people, disabled
  people, anyone who can't walk far or fast), and how should such a person read and adapt Google's predictions?
  Side project on the same infrastructure (2026-10-21, user and Claude, 64th; not a decision). Not that Google is
  wrong (it needs a standard), but where it draws the line and how many fall outside it; accessibility is a
  policy and political question too (Australia: Disability Standards for Accessible Public Transport 2002).
  - Where the line is, in Google's own numbers (stored answers, free): its walk pace (listed durations / distances),
    walk weight (~1.7x), transfer slack (~200 s).
  - What a slower walker catches: leaving when Google says (no wait at home), walking at a slower sourced speed (e.g.
    crossing-design speeds for slower pedestrians), share of Google's default trips still catchable, by speed (a
    curve); where it breaks (first boarding vs transfer); cost of a miss from the timetable (R5 or next departure,
    free); how much earlier to leave to catch Google's trip (the adaptation).
  - Who is affected: census need-for-assistance and age by small area, mapped as where Google's times run optimistic.
  - Compounding: slower walk, then missed transfer, then failed boarding; report the per-trip total, not each step.
  - Limits: speed is one dimension (stairs, lifts, kerbs not in the data); crowding and failed boardings not
    modelled (transit.md Limitations; agencies' passenger counts would be the follow-on); census disability is broad;
    Google's own less-walking and wheelchair options need paid calls before any claim it ignores these users.
  Framing (Claude's): the social model of disability, environments designed around an assumed typical body; a
  trip planner makes that assumption at scale. The user's account of a wheelchair user failing to board a packed
  bus in New York is illustration, not evidence.
  Related (musings 2026-10-20, user's ideas, Claude's notes): how much of impaired transit access is decided by the
  walk alone, by profile (mobility, vision, stamina, cognitive), split by two scenarios (perfect stations + impaired
  walking, and the reverse); walk reach scales with speed squared; barriers cut links rather than slow them. Needs
  OSM accessibility tags (steps, incline, kerb, surface, wheelchair) with a coverage check by area first, GTFS
  wheelchair flags (unchecked), and barriers as walk-network edits (as for pathways).

- **Accessibility budget** (2026-10-20, user; musing). Elevator replacement vs an accessible carriage vs fixing key
  pedestrian streets: one measure, catchment gain per dollar per profile. Claude: elevators are valued by
  reliability (an outage removes the station), a carriage buys capacity (needs load data), streets enter on every
  trip, twice. Needs real cost figures. Reuses the catchment search per walking profile.

- **Emergency response** (2026-10-20, user; musing). Fire / ambulance budget: more vehicles or better streets.
  Claude: the same search reversed (from station to hexes); vehicles fix availability (queueing), streets fix travel
  time, siting is the classic third option; standards are tail percentiles; sirens and time of day break a
  Google-calibrated, time-blind drive model.

- **Transit frequency as a policy lever** (2026-10-20, user; musing). For a city of ~20-25 min trips, more frequent
  trams cut the cost of a missed one. Claude: a miss costs a headway and the expected wait is half one, so halving
  headway halves both; bunching and signal priority decide whether timetable frequency survives on the street.
  Check: the catchment sensitivity run (RCH-13) with tram headways scaled down in a copy of the feed.

- **Other populations** (FRM-19: future applications of the core method). Data to check, none fetched:
  tourists (City of Melbourne CLUE accommodation by block, Tourism Research Australia visitor nights, BITRE airport
  counts, attraction visit numbers; harder: trip chains); shoppers and trip attractors (centre visit counts from
  owners such as Vicinity, Scentre, Gandel, or floor area; open: visits into diners without double counting);
  students (enrolments by campus, Department of Education; the census counts them at home).

- **Brand vs own reputation** (2026-10-16, user and Claude; musing). When is a venue sensitive to its Google
  reviews rather than its brand? Big chains carry a brand-wide modifier (weak players in the rating game: out of
  the reputation analysis, kept as competitors). A rating is worth the uncertainty it removes: uncertainty about
  one branch ~ sqrt(tau^2 + SE^2), tau = real between-branch quality spread (rating points), SE = standard error of
  the brand mean (~0 for a big chain), so tau remains when SE vanishes; customers penalise inconsistency. Measures
  from held data: branch counts by name matching; tau per chain or cuisine by a random-effects estimate. Gate: a
  real demand outcome. Literature unsearched (store format and location; chains and consumer information).
