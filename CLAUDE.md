# PLATICA — rules for Claude Code

Rule IDs are stable: a letter for the section plus a number. Never renumber; a new rule takes the next free number in its section; a deleted rule's ID is never reused. Cite rules by ID (e.g. "CLAUDE.md S5"), DESIGN.md open questions by Q-number (e.g. "DESIGN.md Q9"), concept-doc positions by ID (e.g. "VEN-8"), and sections of DESIGN.md and INDEX.md by heading name, not number.

## Safety
- **S1.** Never delete files or folders. If something looks unnecessary, flag it; I decide.
- **S2.** Read-only: frozen_inputs/ (except its README.md, which Claude keeps up to date). Don't change, move or delete anything in it. (Also enforced by deny rules in .claude/settings.json.) The legacy data/ and backup/ were moved out of the project on 2026-10-16 (docs/legacy_archive.md): never write to them wherever they are; read them only when an evidence pointer leads there and frozen_inputs/legacy_evidence/ doesn't hold the file.
- **S3.** Never open or read data/google_map_api.txt (now a placeholder in the legacy archive). Never read, print or log the GOOGLE_API_KEY environment variable (a Windows user variable); checking whether it is set is fine. config.py holds only the variable's name; only the function that calls the API reads os.environ, at call time (never at import).
- **S4.** No git commit, push, reset, checkout, restore or clean unless I ask. "close" (E2) counts as asking for a commit, never for a push. Read-only git (status, diff, log) is fine.
- **S5.** Never call a paid API (Google) unless I explicitly ask in that session. Never call one to test.

## Working style
- **W1.** Small steps. After each change, stop and report what changed and why. Concept before code, pitched at intermediate Python.
- **W2.** Project docs: docs/DESIGN.md is the current method and intent, as a spine that points to docs/concepts/, where the current positions live; read it before design-related work. Find anything else through docs/INDEX.md and open a doc only when the index points to it for the task at hand; prefer searching for a term or reading one section by line range over reading a whole doc. docs/stale_project_mds/ (the archive: pre-reorg session docs and DESIGN_pre_spine) and docs in the legacy archive (docs/legacy_archive.md) are out of date: never treat them as the current design; open them only as evidence a concept doc points to; ask me for the current position. docs/context_snapshot/ holds full-context copies of earlier docs: open one only when a live doc points to it for the detail at hand; never treat it as the current position. When a doc and the code disagree, report it: the code shows what is, the doc what was intended.
- **W3.** When this session is getting long, warn the user, write docs/HANDOFF.md (W4) and suggest "close" (E2).
- **W4.** docs/HANDOFF.md is the one handoff file, overwritten each time (git keeps history). Sections: current task and next step; in-flight runs with log and output paths; uncommitted changes with suggested commit messages; what the user owes (confirmations, deletions); open flags. Before overwriting, move anything durable out of it: decisions to DESIGN.md, ways of working to memory. Read it only at session start or after /clear, and resume from it.
- **W5.** Discussion sessions. Design ideas are discussed here, not in a separate chat. A session is either discussion or build, never both: in a discussion session Claude reads (by section, W2), checks claims against code and outputs, and talks, but edits nothing until I say "record it". Recording means: the decision or open question goes into DESIGN.md and the concept doc in the same step (F1), then Claude suggests "close" (E2). In a discussion session, "close" includes "record it". Several points per message keep turns, and so cost, down.
- **W6.** docs/incoming_doc/ is an inbox for ideas worked out outside this repo (phone chats, chats in other projects, W7). One note per file, named `YYYYMMDD_<topic>.md`. Its contents are proposals, never current design. When asked to absorb a note, Claude reports each point as new, already covered (with ID), or in conflict, waits for my OK, records the approved points (W5), then moves the note to docs/stale_project_mds/incoming_absorbed/ (moved, never deleted, S1).
- **W7.** Casual mode, when I'm away from the desk (walking, the dog, on the phone), started by "casual", in Claude Code or any other chat:
   - Talk only: short, plain, spoken-style replies; no tables, code or formulas unless I ask; no file edits; read a doc only when a point depends on it.
   - Dictated input may be garbled: if a term is unclear, say how you read it rather than guess.
   - Nothing decided casually is a decision. Ideas stay tentative until absorbed at the desk (W6).
   - On "wrap up", write a capture note: date; topic; ideas, each with the concept IDs or Q-numbers it touches; tentative leanings; open questions; anything to check in code or data. In Claude Code, add it as a dated entry to docs/musings.md (its entry format); elsewhere, output it for me to paste into docs/incoming_doc/ (W6). "close" (E2) does the same for any musing or casual thread in the session not yet captured.
- **W8.** Musing mode, started by "musing": exploration, not proof. It can run at the desk or combined with casual (W7).
   - Focus on ideas and feasibility: what the idea would change in the output, rough effort, what data it needs and whether we have it, what would kill it.
   - Suggest evidence and tests ("how we'd check this"), but don't run, build or write them; D1 and P3 apply only once an idea leaves musing.
   - Label what is established (cite the ID or Q-number) apart from hunches, and say when a hunch conflicts with a current position.
   - Claude brings its own rough ideas unprompted, not only refinements of mine: what it would try if the project were its own, reframings, ideas that question a current position. Half-formed and possibly wrong is fine; W1's small steps and staying on the asked task don't hold them back here. Each is marked as Claude's idea; I decide what survives.
   - No file edits. On "wrap up", write a capture note as in W7, adding the suggested tests; "record it" instead applies W5.
- **W9.** Batched records. In a build session, design and progress updates (decisions, positions, status in DESIGN.md and concept docs) are not written as they come up: Claude keeps a "to record" list in the session and writes each section once, in its final form. Exception: record at once when a later step in the same session depends on the written text. If the session runs long (W3) before the batch is written, the list goes into HANDOFF.md. The closing order is (1) write all records (design decisions and progress) from the "to record" list; (2) write HANDOFF.md (W4); (3) commit; (4) /clear. "close" (E2) runs (1) to (3); whenever Claude suggests a commit or /clear without it, it reminds the user of this order.

## Delegation
- **A1.** Three tiers. The main session (Opus) faces the user; it delegates to save usage.
   - `scout` (Haiku, read-only, .claude/agents/scout.md): inventories, grep and reference sweeps, summarising one doc or log into a given template, watching runs.
   - `worker` (Sonnet, .claude/agents/worker.md): specified edits with a pass/fail check: one-file edits, DEPRECATED/README/INDEX rows, a diagnostic built from a docstring the main session wrote, P3 comparison scripts, approved config moves.
   - Main session: design and statistics decisions, claims and pre-registered rules, P3 verdicts, reviewing every agent's result, everything said to the user.
- **A2.** Delegate without asking when the spec plus its acceptance check fits in about 15 lines. Don't delegate an edit in a file the main session already has open, or work that needs much of this session's context; a cold start costs more.
- **A3.** Every spec states: the goal; the files the agent may read and may edit; the CLAUDE.md rules that apply; the acceptance check; the return format, with a line cap.
- **A4.** Never delegated: anything near a paid API or the ledger (S5), git writes (S4), P3 verdicts, DESIGN.md decisions. Agents never run long jobs (graph builds, routing runs) unless the spec says so.
- **A5.** An agent's result is evidence, not a verdict: the main session reads the diff or checks the claims before reporting them, and says in one line what was delegated to which tier.

## Folders
- **F1.** Folder roles:
   - data/ and backup/: legacy archive and test reference, moved out of the project on 2026-10-16 to an external drive; docs/legacy_archive.md says where, and docs/legacy_archive_manifest.csv lists every file. Nothing reads them.
   - frozen_inputs/: legacy external inputs: API pulls and downloaded datasets (census, OSM, etc.) as they stood at the cleanup. Data files git-ignored; README tracked, with one entry per file:
     - API pulls: original data/ path; the git tag or commit of the code that produced it (default: legacy-final); the producing script and function, or, if that code no longer exists, a short description of how the file was made.
     - Downloads: source, download link, download date, and version or release.
     - Hand-made: what it is, how it was made, and the date it was last edited.
     A file frozen without a current use says so ("no use yet") and why it was kept.
     - Legacy evidence (legacy_evidence/): legacy local files a concept doc cites as evidence, not inputs: original path, how it was made, date, and the citing position.
     Data files in frozen_inputs/ always go in a subfolder (the deny rule protects subfolders only).
     Only I add files here. A newer version of a file is added alongside the old one, never replacing it.
   - inputs/: newer, non-legacy external inputs, used by stages that can update themselves (e.g. a newer census year). Not tracked by git at all, README included. Only I add files; a newer version goes alongside the old one; data files always go in a subfolder. inputs/README.md (Claude may edit) holds the expected folder layout and exact file names, and one entry per file: source, link, download date, version. Folder names are prefixed by dataset (abs_2026/, dzn_2026/) so no two folders share a name (N1).
   - outputs/: everything cleaned code writes. The only folder the pipeline writes to, apart from api_usage/. Git-ignored.
   - api_usage/: api_ledger.jsonl, the append-only record of every API request and the budget guard's state. Written only by api_ledger.py; never edited by hand; not regenerable. api_ledger_backup/ inside it holds manual copies for testing. Claude may read both, never edit them. Git-ignored.
   - output_backup/: backups of post-legacy outputs that are costly to regenerate, in API calls or run time (legacy inputs go in frozen_inputs/). The pipeline never reads or writes it. One subfolder per dataset, named differently from its outputs/ original (N1); a newer version gets its own folder, never overwriting. Data files git-ignored and edit-protected (deny rule); README tracked, Claude keeps it up to date, with one entry per subfolder: original outputs/ path, what it is, how it was made (stage, function, commit), cost to regenerate, date copied.
   - functions/: all reusable functions, in modules split by purpose (e.g. geometry, file I/O). No catch-all modules.
   - diagnostics/: evidence for claims and decisions made in the pipeline (D1). Never imported by the pipeline.
   - images/: presentation material: figures (PNG) and tables (CSV) made from outputs/ for the decks in docs/presentation/. Never read by the pipeline. Files git-ignored (large maps); README tracked. images/README.md holds one entry per file: what it shows, the script and the outputs/ folder it was made from, the commit, the date.
   - docs/: project documentation. Tracked.
     - DESIGN.md: current method and intent, as a spine (per stage: decision, pointers, status; open questions). When a decision changes, update it and the concept doc in the same step.
     - INDEX.md: maps pipeline stages to concept docs, registers concept ID prefixes, and holds the archive finder. Add a row when a doc is added.
     - DEPRECATED.md: one row per removed item, added in the same step as the removal.
     - HANDOFF.md: session-to-session handoff (W4); not a design record.
     - incoming_doc/: inbox of unabsorbed idea notes (W6); proposals, never current design.
     - presentation/: the decks, one subfolder per audience (pilot/, business/, analyst/, research/): outline, speaker notes, slide text. Figures and tables come from images/, never made here.
     - concepts/: one doc per concept, current positions with stable IDs (never renumbered; a deleted ID is never reused). A position entry stays short (about 10 lines): the position, its status, a one-line why, its cost and its evidence; how it was reached goes to the next context snapshot. stale_project_mds/: archive, outdated.
     - context_snapshot/: dated full copies of docs/, one subfolder per snapshot named by its UTC time and mirroring docs/, made by me before a compaction. Correct as of their date, not stale; the live doc wins where they differ. Claude never edits them (deny rule).
- **F2.** Snapshots: data that can't be re-made (API responses, downloads the source no longer serves, the API ledger, a test half opened once). Copy each to output_backup/ with a README entry in the session that makes it. At E1, Claude checks only what this session made (fetches, downloads, the ledger after paid calls), from the conversation and memory, never a project scan, and adds each new snapshot, with the date it was added, to a "Pending archive" line under "Owed by the user" in HANDOFF.md. At session start Claude reports the line with the age of its oldest item. That line is carried over at every overwrite until I make a dated .7z of output_backup/ on the external drive (output_backup/README.md) and Claude checks it against the folder; then I retire the raw copies. Replicable outputs get a local output_backup/ copy only, if costly to rerun.

## Code organisation
- **O1.** main.py and stage scripts say *what* runs; functions/ holds *how*.
- **O2.** Retired 2026-10-26 (user): functions/scratch.py, the pending drawer, was never used and is deleted. Quick code lives outside the pipeline (Claude's scratchpad, git-ignored runner folders in outputs/); anything the pipeline relies on goes straight into a functions/ module or a diagnostic (D1).

## Naming
- **N1.** No magic numbers or strings inline; every threshold, radius, weight, column name and path gets a named variable. No single-letter names except loop indices (i, j) and standard maths (x, y, lat, lon). Conventions:
    - snake_case variables and functions; UPPER_SNAKE_CASE constants; PascalCase classes.
    - Units in names: radius_m, distance_km, duration_min.
    - Booleans start with is_ / has_ / should_.
    - DataFrames end in _df; GeoDataFrames in _gdf; paths in _PATH (files) or _DIR (folders).
    - Name what it is, not how it was made: restaurants_df, not df2.
    - No two folders share a name anywhere in the project.

## config.py
- **C1.** All paths, tunable parameters and random seeds live in config.py; no other file defines them. Use pathlib relative to PROJECT_ROOT; no absolute paths. Group entries by pipeline stage, in pipeline order.
- **C2.** Comments: one line per constant by default (its meaning, plus unit if not in the name). A short paragraph only when a value has a story worth knowing. Shared context goes once, at the top of each stage group. Every migrated path carries `# legacy: <old path>`.
- **C3.** Moving hardcoded values into config.py is a refactor: one script at a time. List the values and proposed names first and wait for my OK. Don't change any value while moving it, except paths being migrated.

## Pipeline and testing
- **P1.** main.py is the tracker. A stage block carries `# STATUS: todo | paths-migrated` until it is cleaned, then the line is removed; deprecated stages are listed in one comment. Work strictly in pipeline order: the next stage is the first block with a STATUS line. Never skip ahead. Update the status in the same step as the work, and suggest a commit message: "<stage>: paths migrated" or "<stage>: cleaned".
- **P2.** Two passes per stage, never combined: (a) migrate paths only, without changing logic, and verify; (b) clean the code, and verify again.
- **P3.** Verify = outputs match the reference in content: same columns, dtypes, row count and values. Row order and float noise below a fixed tolerance don't count. Seeds fixed. Uncleaned downstream stages switched off. API stages are tested only from frozen_inputs/; values may differ, structure must match exactly. Report a verification as a one-line summary only when it passes a check that has passed before with the same definition (same quantities compared, same tolerance); a changed check counts as first-time. Show full detail (every compared quantity, counts, differences, tolerance used) on any failure and on any first-time check.
- **P4.** Cleaned code must keep working. If a change breaks it, undo the change; never fix it by deleting or commenting out the code that broke. Uncleaned downstream stages may break; when they do, report which and why.

## End of session
- **E1.** Review the session's changes (git diff) against these rules. Confirm outputs still match. Write the "to record" list (W9), then docs/HANDOFF.md (W4). Report; I commit, or say "close" (E2) to have Claude commit.
- **E2.** "close" runs the closing protocol in one go, without stopping between steps: (1) E1's review: git diff against these rules, outputs still matching; (2) write every decided item on the "to record" list (W9); anything still awaiting my decision goes under "Owed by the user" in HANDOFF.md instead of being recorded; (3) write HANDOFF.md (W4) and update the project-status memory; (4) commit the session's changes with a message Claude writes (S4), staging named files only, never the whole repo; (5) check whether any in-flight run would die with the session, then report in a few lines: what was recorded, the commit hash, what I owe, and "safe to /clear" (or why not). If the review finds a rule breach, outputs no longer match, or an item needs my decision before it can be recorded, stop before the commit and report instead. Nothing is pushed; I type /clear myself. Each step can also be run alone: "record" (step 2; "record it" in W5 is the same), "handoff" (step 3), "commit" (step 4, with step 1's review first). A single step does only that step and reports; it doesn't run the later ones.

## Diagnostics
- **D1.** Every claim the pipeline relies on without immediate proof points to a diagnostic. Layout: scripts in diagnostics/, data in diagnostics/diagnostic_data/ (git-ignored), figures in diagnostics/diagnostic_img/ (tracked). Each diagnostic:
    - starts with a docstring stating the claim, where the pipeline relies on it, and the conclusion;
    - is self-contained: it never imports from functions/, so pipeline cleanup can't silently break it;
    - names every file it saves with its own name and the run date as a prefix, e.g. google_connector_cost_20261005_*.csv;
    - reuses saved data if it exists, and says so with the data's date; if not, asks me before any API call (S5);
    - keeps one run per day: results (figures, summary tables, logs) carry the run date only, and a same-day rerun replaces
      that day's results; earlier days are kept. Saved data a diagnostic reuses (API pulls, routing tiles and routes) is
      never overwritten.
    The claim's location in code or config.py cites it: `# evidence: diagnostics/<name>.py`.