# Melbourne restaurant catchments (PLATICA)

A self-directed geospatial model of the competitive value of reputation for urban restaurants in
Melbourne. For one subject venue, it estimates how many residents and workers can reach it within
set travel-time bands, on foot, by car and by public transport, and how that reach is shared with
competing venues once Google's displayed rating and review count are taken into account.

The catchment model is the main contribution; reputational competition is the worked application.
The project states its assumptions and limitations before its results.

## What is here

- `main.py`: the pipeline tracker, listing the stages in run order.
- Stage scripts at the root (`hex_tile_construction.py`, `reachability.py`, `scoring.py`, ...): what runs.
- `functions/`: how it runs, as reusable modules split by purpose.
- `config.py`: every path, parameter and random seed, grouped by stage.
- `diagnostics/`: one script per claim the pipeline relies on. Each states the claim, where the
  pipeline uses it and its conclusion. Figures are in `diagnostics/diagnostic_img/`.
- `docs/DESIGN.md`: the current method, stage by stage, with open questions (Q-numbers).
- `docs/concepts/`: one document per concept, holding positions with stable IDs (e.g. DRV-1),
  each with its evidence. `docs/INDEX.md` maps stages to concepts.
- `docs/literature.md`: sources and how each is used. `docs/musings.md` and `docs/future_work.md`:
  exploratory notes, not current design.
- `CLAUDE.md`: the working rules used while building the project with Claude Code (verification,
  naming, provenance, cost control on paid APIs).

## Data and reproducibility

The data is not included: census extracts (ABS 2021), OpenStreetMap and GTFS extracts, and paid
Google Places and Routes pulls. `frozen_inputs/README.md` and `output_backup/README.md` record where
each input came from and how it was made. All paid API calls go through an append-only ledger with a
budget guard (`api_ledger.py`).

This repository is a curated snapshot of a private working repository. Some documents point to
internal archives, handoff notes or an outreach list that are deliberately left out.

## Stack

Python: pandas, GeoPandas, Shapely, OSMnx/NetworkX, r5py (multimodal routing), matplotlib.
