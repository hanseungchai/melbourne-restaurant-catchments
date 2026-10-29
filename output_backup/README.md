# output_backup

## What this folder is

A backup location for post-legacy datasets that are costly to regenerate, either in API calls
(paid) or in run time, and for post-legacy inputs that are snapshots (the API ledger, a GTFS
release PTV no longer serves). The originals live in `outputs/`, `inputs/` or `api_usage/`, where
the pipeline writes and may rebuild them; the copies here survive an accidental rebuild or
deletion of the original.

Legacy inputs are not kept here: they belong in `frozen_inputs/`.

- **Two kinds of backup:**
  - **Snapshots:** data that cannot be re-made, because the source has moved on (API responses,
    downloads no longer served, the ledger) or by design (a test half opened once). Losing one
    loses data, not time; these also go offsite (below).
  - **Replicable:** the same code and inputs give the same result, but a rerun is costly in run
    time. A local copy here is enough.
  Each entry says which kind it is.
- **Offsite archive:** the whole folder is compressed into one dated file,
  `output_backup_<YYYYMMDD>.7z`, tested (`7z t`) and copied to the external drive; a newer
  archive is added alongside the older ones, never replacing them. A new archive is made when a
  new snapshot is added. Once an archive is tested and checked identical to this folder, the raw
  subfolders it holds may be retired (removed by the user); their entries stay here, marked with
  the archive that holds them.
- **Archives made:**
  - `E:\platica_snapshots\20261016\output_backup.7z` (external drive; 272,594,494 bytes): every
    entry below. Made by the user 2026-10-16; `7z t` OK (1,101 files, 459,288,795 bytes); checked
    by Claude the same day: path, size and CRC32 of every file identical to `output_backup/`.
    Raw subfolders retired (deleted by the user) 2026-10-16: this archive is the only backup copy.
  - `E:\PLATICA_261018_backup.7z` (external drive; 4,363,147 bytes; 7 files, 78,347,546 bytes
    unpacked): `transit_google_smoke_20261016_backup/`, `api_usage_20261016b_backup/`,
    `transit_google_20261017_backup/`, `api_usage_20261017_backup/`. Made by the user 2026-10-18
    (file time 01:07); checked by the user; Claude listed its contents only (no `7z t`, no file-by-file
    check; user's call). Raw subfolders retired by the user by 2026-10-18: this archive is the only
    backup copy. Name and place differ from the `platica_snapshots\<date>\output_backup.7z` pattern.
  - `E:\PLATICA_261018_b_backup.7z` (external drive; 99,389,387 bytes; 8 files, 174,094,649 bytes
    unpacked): `gtfs_ptv_20261018_20261018_backup/`, `transit_google_reserve_20261018_backup/`,
    `api_usage_20261018_backup/`. Made by the user 2026-10-18 (file time 03:20); `7z t` OK; checked by
    Claude the same day: size and CRC32 of all 8 files identical to the originals in `inputs/`,
    `outputs/` and `api_usage/` (the raw subfolders were already retired by the user, so the check is
    against the originals, not the copies). This archive is the only backup copy. Same naming as the
    `PLATICA_261018_backup.7z` above, not the `platica_snapshots` pattern.
  - `E:\PLATICA_261020_backup.zip` (external drive; 9,420,968 bytes; 10 files, 94,688,780 bytes
    unpacked; zip, not 7z): `transit_google_topup_20261018_backup/`,
    `transit_google_test_ext_20261020_backup/`, `api_usage_20261020_backup/`. Made by the user 2026-10-20
    (file time 14:06); checked by Claude the same day: zip test OK, SHA-1 of all 10 files identical to the
    originals in `outputs/` and `api_usage/` (the raw subfolders were already retired by the user). This
    archive is the only backup copy. Same naming as the `PLATICA_261018_*` archives.
- **API test backups:** copies of `api_usage/` made while testing API calls go in
  `api_usage/api_ledger_backup/` (kept, even when empty, as the place for them); the backup of the
  whole `api_usage/` folder here carries that structure too.
- **Copies, not inputs:** the pipeline never reads from or writes to this folder. A copy is
  restored to its original folder by hand if the original is lost.
- **Layout:** every data file sits in a subfolder, one per backed-up dataset. Folder names differ
  from their `outputs/` originals (CLAUDE.md N1: no two folders share a name).
- **Never overwritten:** a newer version of a dataset gets its own folder alongside the old one.
  Copies keep the original modified dates.
- **Git:** only this README is tracked; data files are git-ignored (API terms restrict sharing
  stored results).

## Entries

One entry per subfolder: original path, what it is, kind (snapshot or replicable), how it was made
(stage, function, code commit), cost to regenerate, and the date copied.

### enterprise_hours_20261010_backup/

- **Original:** `outputs/places_enterprise_hours/places_enterprise_hours_20261010/` (901 JSONs)
  and `outputs/places_enterprise_hours/places_enterprise_hours_20261010_draw.csv` (draw list),
  and `outputs/places_enterprise_hours/places_enterprise_hours_20261010_not_found.csv`
  (not-found list, so a rerun of the fetch skips draw #390; copied 2026-10-10). The fetch predates
  the list, so its one row was added afterwards with `places_details.record_not_found`, from the
  fetch's console output (no API call).
- **What:** Places Details (Enterprise fields) responses for a uniform draw of 900 venues from
  `venues_20260925_expanded.csv` (seed 20261010) plus the two fixed [subject] venues; one
  `<place_id>.json` per venue (API response + `fetched_date`, `is_fixed`). 901 saved of 902
  requested: draw #390 (ChIJn76uA0Rt1moRdrjDM9_fIpA) returned 404 "Place ID no longer valid".
- **Made by:** `places_details.py` `draw_enterprise_hours_sample` and `fetch_enterprise_hours`,
  main.py block `fetch_enterprise_hours`, on 2026-10-10 (code uncommitted at the time; first
  commit containing `places_details.py` holds it).
- **Kind:** snapshot.
- **Cost to regenerate:** 902 paid Place Details Enterprise calls; and the hours are as of
  2026-10-10, so a re-pull is a different dataset.
- **Used for:** the opening-hours histogram (replaces the 2026-09-02 pull, decided 2026-10-10;
  evidence `diagnostics/enterprise_hours_old_vs_new.py`).
- **Copied:** 2026-10-10.
- **Offsite:** E:\platica_snapshots\20261016\output_backup.7z (checked identical 2026-10-16).

### routes_drive_eta_draw2_20261010_backup/

- **Original:** `outputs/pathing_calibration/-37.76870_144.97196/`:
  `routes_drive_eta_draw2_res2021_wrk2021_ven20260925_-37.76870_144.97196.csv` (one row per pair)
  and its `.raw.jsonl` (every raw response), plus the draw they are keyed to by `draw_no`:
  `od_sample_pairs_draw2_res2021_wrk2021_ven20260925_-37.76870_144.97196.csv`. Not copied: the
  draw's `.kept.pkl` (a resume checkpoint, not needed once the draw is complete) and its
  `od_sample_log_draw2_…json` (run summary).
- **What:** Google Routes `computeRoutes` drive times (TRAFFIC_AWARE, Compute Routes Pro) for the
  second drive draw: 4,000 pairs, draw_no 100,001-110,752, seed 20261010, no hex pair of the
  2026-09-30 draw, departure times from the 2026-10-10 opening hours (DESIGN_pre_spine "Validation
  sample"). 4,000 of 4,000 HTTP 200; every row has a duration, static duration, polyline and both
  snapped points. Departures 2026-10-12 to 2027-10-08, local time.
- **Made by:** `pathing_calibration.draw_second_drive_set` (draw) and `fetch_drive_eta_draw2`
  (fetch, run id `drive_eta_draw2`), stage `calibrate_pathing_agent`, on 2026-10-10: one test call,
  then the other 3,999 (code uncommitted at the time: pass B steps 1-4 on top of 87f3af7; the
  commit with calibrate_pathing_agent pass B holds it). Since 2026-10-11 the code lives in
  `drive_samples.py`, stage `sample_drive_pairs`. Ledger: 4,000 `routes_pro` sends, no retries.
- **Kind:** snapshot.
- **Cost to regenerate:** 4,000 paid Compute Routes Pro calls (October free allowance: 5,000);
  and Google's times depend on when they are fetched, so a re-fetch is a different dataset. The
  draw itself is free and reproducible (same seed, the 2026-10-10 hours), but the fetch is keyed
  to it, and redrawing gives the same pairs only while its inputs (timed graph, hex nodes,
  venues, hours) are unchanged, so the draw CSV is kept with the times.
- **Copied:** done, by the user (date not recorded; copies keep the original modified dates).
- **Offsite:** E:\platica_snapshots\20261016\output_backup.7z (checked identical 2026-10-16).

### drive_model_selection_20261012_backup/

- **Original:** `outputs/pathing_calibration/fit/-37.76870_144.97196/`: run folders
  `20261011/all/` and `20261011/not_motorway/` (fit_drive_models, one per edge set) and
  `20261012/compare/`, `20261012/google_regression/` and `20261012/test/`, plus the two input
  tables `edge_attrs_…npz` and `google_regression_inputs_…npz`. Not copied: `smoke/` (a smoke test).
  Same layout under the subject folder, so a restore is one copy.
- **What:** the drive model selection round (DCL in `docs/concepts/drive-calibration.md`): every
  fit structure's grouped-CV parameters, histories and out-of-fold predictions with `scores.csv`
  (training half); the Google regression contender; the comparison with the density-share guard
  and figures; and the one opening of the test half (`test/test_scores.csv`: 2tier accuracy
  0.9233), with `2tier_all_training_params.json`, the 2tier fit on the whole training half.
- **Made by:** stage `calibrate_pathing_agent`, `pathing_calibration.py`: `fit_drive_models`
  (commit 03f9aec, run 2026-10-11), `fit_google_regression` and `compare_drive_models` (9bc7f1b,
  d698eac), `route_valhalla` (875a510), `evaluate_test_half` (fd9e0fc), run 2026-10-12. The
  selection code is parked when the stage is cleaned (2026-10-13).
- **Kind:** snapshot (the test half, opened once by design); the fits alone would be replicable.
- **Cost to regenerate:** about 3 h for the fits, minutes for the rest; the test half cannot be
  reopened (`evaluate_test_half` refuses), so `test/` cannot be regenerated by design.
- **Copied:** 2026-10-13 (by Claude, `cp -p`; checked identical with `diff -rq` and `cmp`).
- **Offsite:** E:\platica_snapshots\20261016\output_backup.7z (checked identical 2026-10-16).

### transit_pairs_20261016_backup/

- **Original:** `outputs/transit_validation/-37.76870_144.97196/` (whole folder, same layout under
  the subject folder): `transit_pairs_res2021_wrk2021_ven20260925_-37.76870_144.97196.csv` (the
  draw), its `.evaluated.csv` (r5py checkpoint, one row per routed draw_no) and `.evaluated.json`
  (the checkpoint's settings), `transit_pairs_log_…json` (sampling counts) and
  `transit_split_…csv` (train / test / smoke-test halves, CV folds, exploration flag).
- **What:** the transit validation draw (TRN-10): 2,500 in-window hex → venue pairs plus 125
  smoke-test pairs (draw_no up to 27,793; 17,031 candidates routed by r5py on the 2026-10-09
  release, window Wed 2026-10-21 06-24, fastest ≤ 40 min), and their split (1,252 train /
  1,248 test / 125 smoke test; 500 exploration).
- **Made by:** `transit_samples.draw_transit_pairs` and `split_transit_pairs`, stage
  `sample_transit_pairs`, commit 9227c1c, run 2026-10-15 22:57 to 2026-10-16 04:22.
- **Kind:** replicable (same code, seed and release give the same draw).
- **Cost to regenerate:** about 5.4 h of r5py routing (free); the checkpoint makes a rebuild of the
  draw and split from it take minutes. Google times will be keyed to these draw_nos and halves.
- **Copied:** 2026-10-16, by the user; checked identical by Claude (MD5 of the three CSVs).
- **Offsite:** E:\platica_snapshots\20261016\output_backup.7z (checked identical 2026-10-16).

### api_usage_20261016_backup/

- **Original:** `api_usage/` (whole folder): `api_ledger.jsonl` and the empty
  `api_ledger_backup/` (kept as the place for copies made while testing API calls).
- **What:** the append-only record of every API request and the budget guard's state, through
  the last paid calls (2026-10-10: the second drive draw's Routes fetch and the Enterprise hours).
- **Kind:** snapshot (not regenerable; the legacy archive holds only the 2026-10-01 version).
- **Made by:** `api_ledger.py`, the only writer.
- **Cost to regenerate:** cannot be regenerated; without it the budget guard loses its count.
  Copy again after any session with paid calls.
- **Copied:** 2026-10-16, by the user.
- **Offsite:** E:\platica_snapshots\20261016\output_backup.7z (checked identical 2026-10-16).

### gtfs_ptv_20261013_20261016_backup/

- **Original:** `inputs/gtfs_ptv_20261013/`: `metro_train/`, `tram/`, `metro_bus/`, each
  `google_transit.zip` (bus 80,388,788 bytes).
- **What:** the PTV GTFS release exported 2026-10-09, downloaded 2026-10-13 (source and link in
  `inputs/README.md`); the network the transit draw is windowed on and the release its first
  pairs are routed on.
- **Kind:** snapshot (PTV serves only the current rolling export).
- **Made by:** download (user).
- **Cost to regenerate:** cannot be downloaded again once PTV replaces it.
- **Copied:** 2026-10-16, by the user.
- **Offsite:** E:\platica_snapshots\20261016\output_backup.7z (checked identical 2026-10-16).

### transit_google_smoke_20261016_backup/

- **Original:** `outputs/transit_validation/-37.76870_144.97196/transit_google_smoke_*.csv` and its
  `.raw.jsonl` (Google's full answers, with each request body).
- **What:** the TRN-8 gating smoke test: 5 Google transit requests (2 ordinary and 2 short
  exploration pairs, 1 over-window pair) under the 2026-10-09 release, departures 19-23 Oct 2026.
- **Kind:** snapshot (paid API answers; Google's timetable moves on).
- **Made by:** `transit_fetch.smoke_test_transit_fetch` (uncommitted code, 2026-10-16), run 2026-10-16.
- **Cost to regenerate:** 5 Routes Essentials calls, and only while those departures are in the future.
- **Copied:** 2026-10-16, by Claude.
- **Offsite:** E:\PLATICA_261018_backup.7z (checked by the user 2026-10-18).

### api_usage_20261016b_backup/

- **Original:** `api_usage/` (whole folder), as above.
- **What:** the ledger after the 5 transit smoke-test calls (first `routes_essentials` use).
- **Kind:** snapshot (not regenerable).
- **Made by:** `api_ledger.py`, the only writer.
- **Cost to regenerate:** cannot be regenerated.
- **Copied:** 2026-10-16, by Claude.
- **Offsite:** E:\PLATICA_261018_backup.7z (checked by the user 2026-10-18).

### transit_google_20261017_backup/

- **Original:** `outputs/transit_validation/-37.76870_144.97196/transit_google_*.csv`, its `.raw.jsonl`
  (Google's full answers, with each request body) and `.routes.csv` (route table, rebuildable free).
- **What:** the whole transit draw fetched from Google (TRN-8): 2,625 pairs (2,500 in-window + 125
  T5 smoke-test), all HTTP 200, alternatives on, under the 2026-10-09 release; departures 19-23 Oct
  2026, one date per weekday (TRN-7). 2 empty answers, both T5 pairs r5py also can't route.
- **Kind:** snapshot (paid API answers; Google's timetable moves on).
- **Made by:** `transit_fetch.fetch_transit_pairs` (uncommitted code, 2026-10-17), run 2026-10-17.
- **Cost to regenerate:** 2,625 Routes Essentials calls, and only while those departures are in the future.
- **Copied:** 2026-10-17, by Claude.
- **Offsite:** E:\PLATICA_261018_backup.7z (checked by the user 2026-10-18).

### api_usage_20261017_backup/

- **Original:** `api_usage/` (whole folder), as above.
- **What:** the ledger after the 2,625-pair transit fetch (2,626 sends: one network retry).
- **Kind:** snapshot (not regenerable).
- **Made by:** `api_ledger.py`, the only writer.
- **Cost to regenerate:** cannot be regenerated.
- **Copied:** 2026-10-17, by Claude.
- **Offsite:** E:\PLATICA_261018_backup.7z (checked by the user 2026-10-18).

### gtfs_ptv_20261018_20261018_backup/

- **Original:** `inputs/gtfs_ptv_20261018/`: `metro_train/`, `tram/`, `metro_bus/`, each
  `google_transit.zip` (bus 84,699,938 bytes).
- **What:** the PTV GTFS release exported 2026-10-16, downloaded 2026-10-18 (source, link and SHA-1s in
  `inputs/README.md`); candidate release for a second transit batch (TRN-10) and the production bands.
- **Kind:** snapshot (PTV serves only the current rolling export).
- **Made by:** download (user).
- **Cost to regenerate:** cannot be downloaded again once PTV replaces it.
- **Copied:** 2026-10-18, by Claude (`cp -p`, SHA-1 of all three identical to the originals).
- **Offsite:** E:\PLATICA_261018_b_backup.7z (checked identical 2026-10-18); raw copy retired by the user.

### transit_google_reserve_20261018_backup/

- **Original:** `outputs/transit_validation/-37.76870_144.97196/`: `transit_google_20261016_*.csv`,
  `.raw.jsonl`, `.routes.csv` (config.TRANSIT_GOOGLE_RELEASE2_PATH), and `transit_pairs_reserve_*.csv`
  (config.TRANSIT_RESERVE_PAIRS_PATH; free to rebuild, kept with the answers it keys).
- **What:** the second transit batch (TRN-10): 2,000 reserve pairs (draw_no 27,795-51,844, screened like
  the draw: 3.6 km/h, 2026-10-09 release), all HTTP 200, no empty answers, alternatives on, fetched under
  the 2026-10-16 release; departures 19 Oct - 2 Nov 2026 (11 weekdays, TRN-7).
- **Kind:** snapshot (paid API answers; Google's timetable moves on).
- **Made by:** `transit_samples.draw_transit_reserve`, then `transit_fetch.fetch_transit_reserve` (uncommitted
  code, 2026-10-18), run 2026-10-18 (Melbourne).
- **Cost to regenerate:** 2,000 Routes Essentials calls, and only while those departures are in the future.
- **Copied:** 2026-10-18, by Claude (`cp -p`; raw.jsonl SHA-1 identical to the original).
- **Offsite:** E:\PLATICA_261018_b_backup.7z (checked identical 2026-10-18); raw copy retired by the user.

### api_usage_20261018_backup/

- **Original:** `api_usage/` (whole folder).
- **What:** the ledger after the second transit batch (Routes Essentials October total 4,631 of 10,000).
- **Kind:** snapshot (not regenerable).
- **Made by:** `api_ledger.py`, the only writer.
- **Cost to regenerate:** cannot be regenerated.
- **Copied:** 2026-10-18, by Claude (`cp -rp`; ledger SHA-1 identical).
- **Offsite:** E:\PLATICA_261018_b_backup.7z (checked identical 2026-10-18); raw copy retired by the user.

### transit_google_topup_20261018_backup/

- **Original:** `outputs/transit_validation/-37.76870_144.97196/`: `transit_google_topup_*.csv`, `.raw.jsonl`,
  `.routes.csv`, and `transit_pairs_topup_*.csv` and `transit_topup_selection_*.csv` (free to rebuild, kept
  with the answers they key).
- **What:** the boundary top-up (TRN-14): 210 pairs (60-pair pilot, then 150 more from range 1) selected by
  haversine range only, no r5py screen, fetched under the 2026-10-16 release.
- **Kind:** snapshot (paid API answers; Google's timetable moves on).
- **Made by:** `transit_samples.draw_transit_topup`, then `transit_fetch` pilot and top-up fetch, run
  2026-10-18 (code committed in that session's close).
- **Cost to regenerate:** 210 Routes Essentials calls, and only while those departures are in the future.
- **Copied:** 2026-10-20, by Claude (`cp -p`; SHA-1 of all five identical). Owed since 2026-10-18 (Claude's
  copy was blocked by permissions then). The ledger after these calls is inside `api_usage_20261020_backup/`.
- **Offsite:** E:\PLATICA_261020_backup.zip (checked identical 2026-10-20); raw copy retired by the user.

### transit_google_test_ext_20261020_backup/

- **Original:** `outputs/transit_validation/-37.76870_144.97196/`: `transit_google_test_ext_20261016_*.csv`,
  `.raw.jsonl`, `.routes.csv` (config.TRANSIT_GOOGLE_TEST_EXT_PATH), and `transit_pairs_test_ext_*.csv`
  (config.TRANSIT_TEST_EXT_PAIRS_PATH; free to rebuild, kept with the answers it keys).
- **What:** the test-half extension (TRN-15): 4,000 pairs (draw_no 51,848-99,801; 1,660 screened on the
  2026-10-09 release, 2,340 on the 2026-10-16 release), all to the test half, all HTTP 200, alternatives on,
  fetched under the 2026-10-16 release; departures Wed 21 Oct - Mon 2 Nov 2026. Not read: the test half is
  opened once, under a reading rule still owed.
- **Kind:** snapshot (paid API answers; Google's timetable moves on; part of the test half).
- **Made by:** `transit_samples.extend_transit_checkpoint_release` (screen, 2026-10-20 01:13-07:50),
  `draw_transit_test_extension`, then `transit_fetch.fetch_transit_test_ext`, commit c12b975, run
  2026-10-20 (Melbourne).
- **Cost to regenerate:** 4,000 Routes Essentials calls, and only while those departures are in the future.
- **Copied:** 2026-10-20, by Claude (`cp -p`; SHA-1 of all four identical).
- **Offsite:** E:\PLATICA_261020_backup.zip (checked identical 2026-10-20); raw copy retired by the user.

### api_usage_20261020_backup/

- **Original:** `api_usage/` (whole folder).
- **What:** the ledger after the top-up (210) and the test-half extension (4,000 Routes Essentials calls,
  8,000 ledger lines on 2026-10-19/20 UTC).
- **Kind:** snapshot (not regenerable).
- **Made by:** `api_ledger.py`, the only writer.
- **Cost to regenerate:** cannot be regenerated.
- **Copied:** 2026-10-20, by Claude (`cp -rp`; ledger SHA-1 identical).
- **Offsite:** E:\PLATICA_261020_backup.zip (checked identical 2026-10-20); raw copy retired by the user.

### transit_google_holdout_20261021_backup/

- **Original:** `outputs/transit_validation/-37.76870_144.97196/`: `transit_google_holdout_20261016_*.csv`,
  `.raw.jsonl`, `.routes.csv`, `_fetch.log` (config.TRANSIT_GOOGLE_HOLDOUT_PATH), and
  `transit_pairs_holdout_*.csv` (config.TRANSIT_HOLDOUT_PAIRS_PATH; the pairs the answers key).
- **What:** the fresh holdout (TRN-16 (1)): 4,000 pairs (draw_no 99,806-147,078), all HTTP 200, alternatives on,
  fetched under the 2026-10-16 release; departures Thu 22 Oct - Mon 2 Nov 2026. Sealed: not compared with R5
  until the freeze record and the holdout reading rule are written.
- **Kind:** snapshot (paid API answers; Google's timetable moves on; the holdout).
- **Made by:** `transit_samples.draw_transit_holdout`, then `transit_fetch.fetch_transit_holdout` (uncommitted
  at the run; committed in the 66th session's close after 6d4b1e9), run 2026-10-21 11:21-12:07 UTC.
- **Cost to regenerate:** 4,000 Routes Essentials calls (2,841 of them paid, ~US$14.21 in October 2026), and
  only while those departures are in the future.
- **Copied:** 2026-10-21, by Claude (`cp -p`; SHA-1 of all five identical).
- **Offsite:** E:\PLATICA_261021_backup.zip (checked identical 2026-10-21, against the originals: the raw copy
  was already retired); raw copy retired by the user.

### api_usage_20261021_backup/

- **Original:** `api_usage/` (whole folder).
- **What:** the ledger after the holdout fetch (4,000 Routes Essentials calls on 2026-10-21 UTC; October total
  12,841, 2,841 over the free allowance under a one-run paid extension the user approved).
- **Kind:** snapshot (not regenerable).
- **Made by:** `api_ledger.py`, the only writer.
- **Cost to regenerate:** cannot be regenerated.
- **Copied:** 2026-10-21, by Claude (`cp -rp`; ledger SHA-1 identical).
- **Offsite:** E:\PLATICA_261021_backup.zip (checked identical 2026-10-21, against the originals: the raw copy
  was already retired); raw copy retired by the user.

### break_even_pairs_judged_20261025/

- **Original:** `diagnostics/diagnostic_data/rating_break_even_pairs_20261025_{judged_partner,sheet,ANSWER_KEY}.csv`.
- **What:** the 101st's break-even blind pairs (DESIGN Q31): 24 synthetic (rating, reviews) pairs, the answer key,
  and the first judge's answers (the user's partner; her self-report: consciously prefers review counts, not
  universal).
- **Kind:** snapshot (a person's answers can't be re-made; the sheet and key regenerate from the seeded script).
- **Made by:** `diagnostics/rating_break_even_pairs.py` (sheet, key; uncommitted at the run, committed at the 101st
  close); answers typed in by the user in chat, saved by Claude.
- **Cost to regenerate:** the answers cannot be regenerated.
- **Copied:** 2026-10-25, by Claude (Copy-Item; SHA-1 of all three identical).

### break_even_judges_102nd_20261025/

- **Original:** `diagnostics/diagnostic_data/rating_break_even_pairs_20261025_judged_<judge>.csv`, 12 files: `owner`
  (the user, not blind) and 11 LLM runs (`claude_opus`, `claude_sonnet`, `claude_haiku`, `gpt56_luna`,
  `gpt56_luna_think`, `gemini3_flash`, `gemini3_flash_think`, `deepseek_nothink`, `deepseek_think`, `kimi31_pro`,
  `kimi28_pro`).
- **What:** more judges on the 101st's break-even pairs (DESIGN Q31, 102nd discussion). LLM runs are illustration,
  not evidence; Opus answered with project context, the rest from the questionnaire text only.
- **Kind:** snapshot (the user's answers can't be re-made now the key is seen; LLM answers don't reproduce exactly).
- **Made by:** answers typed or pasted by the user in chat (Claude subagents for Sonnet and Haiku), saved by Claude in
  the judged-file format (sheet columns + judge, answer, judge_note).
- **Cost to regenerate:** the owner's answers cannot be regenerated; LLM runs only approximately.
- **Copied:** 2026-10-25, by Claude (cp -n).

### break_even_judge_sister_20261025/

- **Original:** `diagnostics/diagnostic_data/rating_break_even_pairs_20261025_judged_sister.csv`; the PDF is the
  user's upload in chat (106th), not kept elsewhere in the project.
- **What:** the user's sister's answers to the 101st's break-even pairs (DESIGN Q31), on a Korean translation of the
  sheet (pairs equal the sheet; 22 picks, 2 "same"). The PDF is her filled sheet as received.
- **Kind:** snapshot (a person's answers can't be re-made).
- **Made by:** answers transcribed from the PDF by Claude into the judged-file format (sheet columns + judge, answer,
  judge_note; "same" kept as `same`).
- **Cost to regenerate:** cannot be regenerated.
- **Copied:** 2026-10-25, by Claude (Copy-Item; SHA-1 of the CSV identical to the original).

### screen_match_partner_transcribed_20261025/

- **Original:** `diagnostics/diagnostic_data/screen_match_20261025_partner_phone_1336_1459_partner_transcribed.csv`;
  uploaded by the user in chat (106th).
- **What:** the user's partner's Google Maps "Restaurants" lists (DESIGN Q19), iPhone, Chinese interface, same
  house as the user: her account at 13:36 (a wider, moved map area) and 14:58-14:59, incognito at 14:58. One row
  per card: list group and position, sponsored flag, rating, reviews, price, cuisine (English and Chinese),
  status, hours, distance, saved list, notes.
- **Kind:** snapshot (the lists can't be retaken).
- **Made by:** the partner's side (by hand or a chat model reading her screenshots: unconfirmed); not checked
  against the screenshots, which are not in the project.
- **Cost to regenerate:** cannot be regenerated.
- **Copied:** 2026-10-25, by Claude (Copy-Item; SHA-1 identical to the upload).

### screen_match_api_20261025_backup/

- **Original:** `diagnostics/diagnostic_data/screen_match_api_20261025_raw.jsonl`.
- **What:** IDs-only Text Search (New) responses in API order for DESIGN Q19's screen-matching test, query
  "Restaurants": browser screen (URL centre, viewport restriction / viewport bias / 1 km circle, openNow off and on)
  and phone screen (1 km circle around the blue dot trilaterated from card distances, -37.810112,144.951035;
  openNow off and on). 8 arms, 60 IDs each, request body and fetch time per line.
- **Kind:** snapshot (results and open status move with time; sent 12:40-12:41 local, ~20-35 min after the screens).
- **Made by:** `diagnostics/screen_match_api.py --fetch` (uncommitted at copy time), 24 requests through api_ledger,
  free SKU `text_search_ids_only`.
- **Cost to regenerate:** cannot be regenerated as of that time; a rerun costs nothing but gives today's results.
- **Copied:** 2026-10-25, by Claude (cp -n).

### screen_match_api_20261025_full_backup/

- **Original:** `diagnostics/diagnostic_data/screen_match_api_20261025_raw.jsonl`, after the extra arms.
- **What:** the same file as `screen_match_api_20261025_backup/` (8 arms, 12:40-12:41) plus 8 extra arms sent
  12:44-12:45 local (`--extra`, browser URL centre and phone position each): 1 km circle ranked by DISTANCE (openNow
  off and on), 300 m circle, 1 km circle with includedType restaurant (strict). 16 arms, 60 IDs each. Supersedes the
  earlier folder (kept, S1).
- **Kind:** snapshot. **Made by:** `diagnostics/screen_match_api.py --extra --fetch`, 24 more requests through api_ledger,
  free SKU `text_search_ids_only`. **Cost to regenerate:** cannot be regenerated as of that time.
- **Copied:** 2026-10-25, by Claude (cp -n).

### screen_match_api_20261025_final_backup/

- **Original:** `diagnostics/diagnostic_data/screen_match_api_20261025_raw.jsonl`, final (25 arms).
- **What:** the 16 Text Search arms of `screen_match_api_20261025_full_backup/` plus 9 Nearby Search (New) arms
  sent 13:15 local (`--nearby`): popularity rank, includedTypes / includedPrimaryTypes restaurant, 500 m / 1 km /
  1.5 km circle restriction, phone position (6) and browser URL centre (typed only, 3); 20 IDs each. Supersedes
  both earlier folders (kept, S1).
- **Kind:** snapshot. **Made by:** `diagnostics/screen_match_api.py --nearby --fetch`, through api_ledger, SKU
  `nearby_pro` (paid SKU inside the 5,000/month free cap; user's go). **Cost to regenerate:** cannot be regenerated
  as of that time.
- **Copied:** 2026-10-25, by Claude (cp -n).
