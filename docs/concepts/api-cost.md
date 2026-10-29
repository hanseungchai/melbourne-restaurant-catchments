# API cost, ledger and terms

**Purpose and scope.** Paid Google calls: the ledger and budget guard, SKUs and free allowances,
quotas, what each request records, the API key, and the Maps Platform terms. Not what each fetch
samples or why (venue scan: `venues.md`; drive pairs: OD sampling doc; hours: venues doc).
**Stages.** Every paid stage: `fetch_enterprise_hours` (`places_details.py`), `sample_drive_pairs`
(`drive_samples.py`). Module: `api_ledger.py`; usage summary: `main.print_api_usage`. The legacy
Nearby repair (`functions/legacy_functions.py`) was retired in reorg step 8 (DEPRECATED.md).
**Last reviewed.** 2026-10-13, 0c7369e
**Full context.** Compacted 2026-10-20. The full text, with how positions were reached and the change
log to 2026-10-20, is the snapshot `docs/context_snapshot/2026-10-20_02-48-00Z/concepts/api-cost.md` ("snapshot" below).
Every ID is kept so citations resolve. This doc wins where the two differ.

## Current position
- **API-1.** Every paid call goes through `api_ledger`: `check(sku, n)` before a batch and
  `record_send` before each HTTP attempt (retries included). Never bypassed; if the guard refuses,
  stop and report, never raise allowances, edit the ledger or call the API directly (CLAUDE.md S5;
  memory `never-bypass-api-ledger`).
  Evidence: call sites in `drive_samples.py`, `places_details.py` (and, until reorg step 8,
  `functions/legacy_functions.py`). User, 2026-10-10.
- **API-2.** The ledger (`api_usage/api_ledger.jsonl`) is append-only JSONL, one `sent` line per HTTP
  request written before the request (it can overcount a failed call, never undercount a billed one),
  then a result line. Keyed by (billing month, SKU); the billing month runs on US Pacific time. Never
  edited by hand; not regenerable (CLAUDE.md F1). Single writing process (threads fine via a lock).
  Evidence: `api_ledger.py` docstring; offline tests `test_api_ledger.py` (Sep 24). `hole_probe_Sep_24` L123-138.
- **API-3.** Guard: `check` raises `BudgetExceeded` when a batch would pass the allowance less
  `MARGIN` (now 0); a capped SKU with no `SEED_USED` entry for the current month is refused, since an
  unknown start means an unknown balance. Each new month needs a seed line read off Billing → Reports.
  Evidence: `api_ledger.py`. `hole_probe_Sep_24` L128-131; `sampler_and_fetch_Oct_1` L140-144.
- **API-4.** Allowances in the ledger (per month): `routes_pro` 5,000, `place_details_enterprise`
  1,000, `legacy_nearby` 5,000 (not free: each legacy request also bills Basic, Contact and
  Atmosphere, with no field-mask opt-out), `text_search_ids_only` uncapped.
  Evidence: `config.API_FREE_ALLOWANCE`; Billing → Reports, Sep 30 (`sampling_delta_Sep_30` L123-137).
  Not checked against the pricing page.
- **API-5.** Two Routes limits, both real: the monthly free allowance (5,000 Compute Routes Pro,
  guarded by the ledger) and the Console's daily quota (5,000/day, read by the user; not guarded by
  the ledger, so 429s near the end are picked up by resuming).
  Evidence: user read Console (memory `never-bypass-api-ledger`); `sampler_and_fetch_Oct_1` L143-144.
  Resolves the "per month vs per day" flag: they are different limits. Supersedes 4,000/day (Sep 30).
- **API-6.** Drive calls are TRAFFIC_AWARE, which bills Compute Routes Pro (one SKU per request, at its
  highest tier). Polyline geometry doesn't raise the tier; `extraComputations` TRAFFIC_ON_POLYLINE
  (Enterprise) is not requested. Alternatives are free information (billing is per request).
  Evidence: Google SKU page (cited, not in repo). `sampling_rethink_Sep_27` L125-140; `sampler_and_fetch_Oct_1`.
- **API-7.** Fetches are resumable and lose at most what's in flight: one row flushed per call, resume
  by draw number, only HTTP 200 counts as done.
  Evidence: none (code). `sampler_and_fetch_Oct_1` L133-138.
- **API-8.** The key is the Windows user variable `GOOGLE_API_KEY`, read only at call time; config
  holds only its name; `data/google_map_api.txt` is never opened (CLAUDE.md S3); since 2026-10-16 it
  holds a placeholder, not the key, and sits in the legacy archive (`docs/legacy_archive.md`). The key
  was never in git history (2026-10-16: the file was never committed; `git log --all -S` on the key
  string, run by the user, found no commit). APIs are never called to test; API stages are tested
  from `frozen_inputs/` (CLAUDE.md S5, P3).
  Evidence: CLAUDE.md S3, S5. Supersedes `cleanup-workflow` L28 ("move to an env var later").
- **API-9.** Terms: fitting to and storing Google content (directions, ratings) conflicts with Maps
  Platform terms §3.2.3 (no caching or bulk download; no training or validating models on Maps
  content). The user accepted the conflict for own non-commercial research, knowing that does not make
  it permitted (Sep 27). Write-up: say "widely done in the literature", never "allowed for research";
  M2-vs-Google comparisons need §3.2.4 replication disclosure; a qualified legal read before publishing.
  Evidence: none (terms text, last modified 2026-08-26). `sampling_rethink_Sep_27` L156-168;
  `polyline_regression_idea_Oct_3` L182-198. Settled (user, 2026-10-13): supersedes the Sep 17 principle.

## Not adopted
- "No reverse engineering Google; Google ETAs only as an evaluation target" (Sep 17, with the Google-derived speed table rejected on terms grounds): superseded by API-9 (user, 2026-10-13); the Google polyline regression fits to Google outputs as a comparator. `STALE_google_speed_table_rejected_and_eta_metadata` L9, L44-64.
- A colleague's API key: terms §1.2, §3.1, §3.2.1(c)(ii); moot given own allowance (user, Sep 27). `sampling_rethink_Sep_27` L156-159.
- Legacy Nearby as the hours source: returns only `open_now`. `sampling_delta_Sep_30` L137.
- Anonymising venue names as a fix for the terms issue: protects businesses in the write-up but doesn't resolve terms; location plus rating identifies most venues. rev4 L1186-1188.
- Subsampling when a needed fetch is large: pay for the calls instead. `OD_resample_Sep_26` L122-125.

## Limitations
- ~3,900 Text Search calls in September bypassed the ledger (ledger 16,849 vs billing 20,768) by an
  unknown code path, never found. Text Search is uncapped in the ledger, so the guard wouldn't have
  stopped them anyway. `sampling_delta_Sep_30` L161-162.
- The `legacy_nearby` guard uses 5,000, but the binding cap is the smallest of its four billed SKUs
  (Atmosphere first). `sampling_delta_Sep_30` L159-160.
- The old walk and transit Routes fetches (`map_pathing.collect_eta` → `get_google_eta`, last code
  `03f9aec`) never went through the ledger: no `check` or `record_send` call. Retired in reorg step 8
  (2026-10-13); a new transit fetch (TRN-8) follows `drive_samples`' guarded request instead.
- Billing reports lag up to a day, so seeds read near a month boundary can be stale. `sampling_delta_Sep_30` L165-166.
- Raw responses can't be kept indefinitely (only Place IDs may be cached); the publishable record is
  the request log plus summary results. Ratings refreshed monthly are stored Google content.
  `STALE_google_speed_table_rejected_and_eta_metadata` L55, L97; `polyline_regression_idea_Oct_3` L195-197.

## Notes
- Spend record (Sep 2026): legacy Nearby 2,548 billed (~$17, Atmosphere $10.76, Contact $6.46: the
  expansion run); Place Details Enterprise 950; Text Search IDs-only 20,768; Routes Pro 544; Routes
  Essentials 1,150 (presumed walk). Repair run ~1,081 sends, +3.5% over plan. `sampling_delta_Sep_30`
  L123-134; `repair_run_Sep_25` L204-212.
- Console daily caps are the backstop against a runaway loop (raised for a run, set back after).
  `repair_run_Sep_25` L37; `verify_and_outer_run_Sep_25` L116-121.
- Request metadata: the Sep 17 15-field schema (product, SKU, field mask, coordinates as sent,
  request id, terms version, code version; query and collection time) was written for §3.2.4
  replication. How much of it the current fetchers record isn't checked here. `STALE_google_speed_table_rejected_and_eta_metadata` L79-94.
- The budget constants (`API_FREE_ALLOWANCE`, `API_SEED_USED`, `API_PAID_EXTENSION`, `API_MARGIN`,
  `API_BILLING_TIMEZONE`) live at the **top** of config.py in a highlighted "API BUDGET GUARD" block,
  ahead of the stage groups (user, 2026-10-13: an agreed exception to C1's pipeline order); moved
  from `api_ledger.py` 2026-10-22 (C3, values unchanged; guard probe identical). Only `api_ledger.py`
  reads them.
- Disclosure rule, not decided (rev4): open disclosure of all Google content (leaning) vs a necessity
  rule (Google content only where the question needs it, e.g. ratings). rev4 L1174-1182.
- Unaware (static) Routes requests may be a separate SKU; if `staticDuration` comes inside the aware
  response no extra call is needed (user-reported, unconfirmed). `departure_noise_floor_Oct_4` L50-52.

## Open questions
- None open.

## Changes
- Changes to 2026-10-20 (API-1 to API-9): snapshot, "Changes".
- 2026-10-22 · budget constants moved from `api_ledger.py` to the top of config.py (C1 flag closed); no position changed
- 2026-10-20 · compacted: history and superseded detail moved to the snapshot; IDs kept (no position changed)
