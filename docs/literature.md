# Literature

Every outside source the project cites, in one place (user, 2026-10-25, 108th). One entry per source: what it is,
what we take from it, where we use it (concept ID or Q-number), and how far it has been checked. Checked levels:
**memory** (Claude's recall, unverified), **secondary** (seen through another paper's summary or a search snippet),
**abstract** (the source's own abstract or landing page), **read** (the text itself). Nothing here is checked to
"read" yet; the citation check parked in `concepts/scoring.md` Notes still stands.

Citations in older docs that predate this file were not swept in (owed, HANDOFF).

## Choice and consideration sets
- **Manzini, P. & Mariotti, M. (2014).** Stochastic choice and consideration sets. *Econometrica* 82(3), 1153-1176,
  doi 10.3982/ECTA10575. Each option is considered with its own chance; the chooser takes the best considered.
  Use: the closest published form to best-of-K; the per-venue exposure variant (DESIGN Q32, SCR-23, scoring.md
  Notes "Best-of-K"). Checked: abstract.
  https://www.econometricsociety.org/publications/econometrica/2014/05/01/stochastic-choice-and-consideration-sets
- **Hauser, J. R. & Wernerfelt, B. (1990).** An evaluation cost model of consideration sets (title from memory).
  *Journal of Consumer Research* 16(4), 393-408. Mean consideration sets of ~3.3 (frozen dinners), 3.9 (deodorant), 4.0 (coffee); set
  size as a trade-off of decision cost and benefit. Use: soft anchor for k (Q32); C2 in the share-rule criteria.
  Checked: secondary (arXiv 2302.04354). https://ideas.repec.org/a/oup/jconrs/v16y1990i4p393-408.html
- **"Consider or Choose? The Role and Power of Consideration Sets" (arXiv 2302.04354).** Source of the Hauser &
  Wernerfelt set sizes above; reports consistent grocery results. Use: Q32. Checked: search snippet.
  https://arxiv.org/pdf/2302.04354
- **Ding, Gaskin & Hauser (2009).** Consideration review (Sawtooth). Consumers consider ~10% of available options in
  frequently bought categories. Use: the proportional-growth reading of K (scoring.md Notes). Checked: search
  snippet. https://stuff.mit.edu/~hauser/Papers/Ding_Gaskin_Hauser_Consideration_Review_Sawtooth_2009.pdf
- **Reutskaja, E., Nagel, R., Camerer, C. & Rangel, A. (2011).** Eye-tracking of choice from menus: the share of
  items viewed falls as the menu grows. Use: K doesn't grow in proportion to the field (Q32 (5)). Checked:
  secondary (arXiv 2110.10650).
- **"Attention Overload" (arXiv 2110.10650).** Adding rivals never raises an item's chance of being considered.
  Use: Q32 (5). Checked: search snippet. https://arxiv.org/pdf/2110.10650
- **"Random Utility and Limited Consideration" (arXiv 1812.09619).** Consideration widens as its cost falls. Use:
  Q32 (5). Checked: search snippet. https://arxiv.org/pdf/1812.09619
- **"Consumer Experience and Consideration Sets for Brands and Product Categories" (Columbia Business School).**
  Sets grow with consumer experience, not with the number of options. Use: Q32 (5), per-band effort. Checked:
  search snippet. https://business.columbia.edu/sites/default/files-efs/citation_file_upload/Consumer%20Experience%20and%20Consideration%20Sets%20for%20Brands%20and%20Product%20Categories.pdf
- **"Information, entropy and the paradox of choice" (arXiv 2412.12721).** More options raise cognitive cost.
  Use: background for Q32 (5). Checked: search snippet. https://arxiv.org/pdf/2412.12721
- **Alba, J. W., Hutchinson, J. W. & Lynch, J. G. (1991).** Memory-based consumer choice (evoked set). Use: the
  two-stage exposure / deliberation idea (scoring.md Notes "Best-of-K"). Checked: memory.
- **Manski, C. F. (1977).** Two-stage choice: choice-set generation, then choice. Use: Q32 framing. Checked: memory.
- **Goeree, M. S. (2008).** Limited information and advertising in the US personal computer industry
  (*Econometrica*). Per-product consideration chances in demand estimation. Use: Q32 (5). Checked: memory.
- **Huber, J., Payne, J. W. & Puto, C. (1982).** Attraction (decoy) effect, counter-evidence to regularity. Use: C4
  in the share-rule criteria; C4 accepted as failing under SCR-23. Checked: memory.

## Search
- **Stigler, G. J. (1961).** The economics of information: fixed-sample search. Use: Q32 (5). Checked: memory.
- **Weitzman, M. L. (1979).** Optimal search for the best alternative: search while the expected gain beats the
  cost. Use: Q32 (4)-(5), commitment justifies more search. Checked: memory.
- **Secretary problem** (classic optimal stopping, no recall). Use: contrast with best-of-K, where recall is
  allowed (Q32 (3)). Checked: memory.

## Spatial choice and trip distribution
- **Stouffer, S. A. (1940)** and **Schneider, M. (1959).** Intervening opportunities: destinations considered in
  order of distance; the count of opportunities in between, not distance itself, limits far ones. Use: precedent for
  SCR-23's stages (proximity from nesting). Checked: secondary (arXiv 1506.04889).
- **Simini, F., Gonzalez, M. C., Maritan, A. & Barabasi, A.-L. (2012).** A universal model for mobility and migration
  patterns (*Nature*). Radiation model: parameter-free, flows set by the population closer than the destination.
  Use: precedent for SCR-23's density-driven diminishing returns. Checked: abstract.
  https://alphaxiv.org/abs/1111.0586
- **Masucci et al. (arXiv 1206.4359).** The radiation model's finite-size error, worst for large cities. Use: caveat
  on the precedent above. Checked: search snippet. https://arxiv.org/abs/1206.4359v2
- **"Systematic comparison of trip distribution laws and models" (arXiv 1506.04889).** Review linking intervening
  opportunities and radiation. Use: as above. Checked: search snippet. https://ar5iv.labs.arxiv.org/html/1506.04889
- **Thill, J.-C. (1992).** Choice set formation for destination choice modelling. *Progress in Human Geography* 16,
  361-382. Use: Q32 framing (bands as travel-time-bounded choice sets). Checked: citation only.
- **Thill, J.-C. & Horowitz, J. L. (1997).** Travel-time constraints on destination-choice sets; two-stage choice
  (awareness, accessibility, salience, then choice). Use: as above. Checked: abstract.
  https://ideas.repec.org/h/spr/adspcp/978-3-662-03499-6_10.html
- **Pellegrini, P. A. (1995)** and **Miller (review).** Choice set definition as the hardest problem in spatial
  choice. Use: as above. Checked: search snippet. https://msaag.aag.org/wp-content/uploads/2013/04/18_Pellegrini.pdf
- **Tsoleridis, P., Choudhury, C. F. & Hess, S. (2023).** Probabilistic, latent choice set formation (Manski
  framework). Use: as above. Checked: abstract.
  https://ideas.repec.org/a/eee/jotrge/v108y2023ics096669232300039x.html
- **Huff, D. L.** Retail gravity model. Use: the first-exposure lens (scoring.md Notes; FRM-27). Checked: memory.

## Ratings, rankings and attention to lists
- **Luca, M. (2016).** Yelp ratings and revenue, ~5-9% per star within a restaurant over time. Use: C1 in the
  share-rule criteria. Checked: memory.
- **Anderson, M. & Magruder, J. (2012).** Reservations jump at Yelp's rounding thresholds. Use: C1. Checked: memory.
- **Joachims, T. et al. (2005).** Eye tracking: attention falls with list position. Use: C7 / C9. Checked: memory.
- **Craswell, N. et al. (2008).** Cascade click models. Use: C7 / C9, SCR-15's precedent. Checked: memory.
- **Moffat, A. & Zobel, J. (2008).** Rank-biased precision. Use: SCR-15's precedent. Checked: memory.
- **Powell, D. et al. (2017).** People prefer the more-reviewed product even when the less-reviewed one is likely
  better. Use: scoring.md Limitations (m vs diner trust). Checked: memory.

## Industry surveys
- **Little Dragon Media (Canada, n = 1,000), via Verdict Foodservice.** Picking among ten nearby restaurants, ~39%
  chose by online reviews, ~22% by proximity. Commissioned, methods thin. Use: background only (no k found).
  Checked: news summary. https://www.verdictfoodservice.com/news/restaurant-study-canada
