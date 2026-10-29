# <Concept name>

<!--
Template for concept docs (one doc per concept, not per session). Copy this file, delete these
comments. Required: Purpose and scope, Current position, Changes. Every other section is optional.
Aim for under ~200 lines; split the concept if it grows past that.
-->

**Purpose and scope.** 1–3 lines: what this covers, and what it doesn't (with a pointer to the doc that does).
**Stages.** The main.py switches this doc covers.
**Last reviewed.** <date>, <commit>

## Current position
<!--
Numbered with a stable ID: the concept's prefix (registered in INDEX.md) plus a number. Never
renumber; a deleted ID is never reused. Each position states what holds now, in 1–3 lines.
Every position carries an evidence pointer; "Evidence: none" flags a missing diagnostic (CLAUDE.md D1).
-->
- **XXX-1.** The position.
  Evidence: `diagnostics/<name>.py` · <commit> · <old doc §>. Open: DESIGN.md Q<n> (if any).

## Not adopted
<!-- Optional. What was rejected, the reason in one line, and a pointer. Stops it being proposed again. -->
- <Option>: <reason>. <pointer>

## Limitations
<!-- Optional. Known weaknesses we state rather than fix, each with its measured cost where we have one. -->
- <Limitation>: <cost>. <pointer>

## Notes
<!--
Optional. Context that isn't a position and doesn't fit elsewhere: background, history, reasoning,
hunches, personal context (not project work, but it matters), things worth knowing without evidence. Notes aren't cited as positions; if the pipeline
starts relying on a note, promote it to a position with evidence.
-->
- <Note> (<date>)

## Open questions
<!-- Pointers only; Q-numbers live in DESIGN.md. -->
- DESIGN.md Q<n>, Q<n>

## Changes
<!-- Newest first, one line each. -->
- <date> · <ID> <what changed>  (git log on this file gives the commit)
