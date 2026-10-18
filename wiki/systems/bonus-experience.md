---
id: "bonus-experience"
title: "Bonus Experience"
description: "How chapter performance becomes a persistent BEXP pool and is distributed at the base"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Progression", "Chapters", "Research needed"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "path-of-radiance-us-manual"]
cms_collection: "systems"
source_path: "systems/bonus-experience.md"
system_entries: ["FE9-SYS-208", "FE9-SYS-209", "FE9-SYS-210", "FE9-SYS-211", "FE9-SYS-212", "FE9-SYS-213", "FE9-SYS-278"]
system_reviewed: ["FE9-SYS-208", "FE9-SYS-209", "FE9-SYS-210", "FE9-SYS-211", "FE9-SYS-212", "FE9-SYS-213", "FE9-SYS-278"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Bonus Experience

Bonus Experience (BEXP) separates **how well a chapter was completed** from **which unit receives the growth**. Chapter-clear logic awards points to one party pool; later, the base lets the player spend that pool on chosen units. It is independent of ordinary combat EXP: unused battle EXP is not automatically converted into BEXP.

## Mental model and example

Treat BEXP as a bank account with two independent ledgers. If clear processing awards 500, the persistent pool rises by 500 and the current report-period counter records the award. Spending 120 at the base lowers the pool to 380 and advances the selected unit toward its next level; it does not retroactively change the chapter's award criteria. When the report counter later resets, the 380 unspent points remain available because the pool and report are different fields.

## Award calculation

<span id="fe9-sys-208"></span> Each chapter defines relevant performance conditions. Clear processing evaluates them after victory, combines their awards, and adds the result to the persistent pool. Common inputs include turns and optional objectives, but the system is chapter-specific rather than one universal formula.

The save confirms a 32-bit BEXP balance and a separate signed report counter. Scripts/flags can represent optional accomplishments, while native clear processing can apply chapter, difficulty, and display rules. Until the complete consumer is traced, individual chapter tables should be documented as evidence, not generalized beyond their observed maps.

## Turn-efficiency component

<span id="fe9-sys-209"></span> Many chapters reward faster completion. The likely shape is a chapter-authored threshold or decay schedule using the final turn count. Correct research must test boundary turns on each difficulty; observing “fewer turns gives more” does not identify rounding, floor, maximum, or whether multi-part chapters count separately.

## Objective component

<span id="fe9-sys-210"></span> Optional conditions can reward protecting NPCs, escaping additional units, avoiding prohibited actions, or satisfying chapter-specific goals. These are naturally represented by event flags/counters set during play and read at clear. The article should name the exact flag/script path for each confirmed objective.

## Rules and lifecycle — pool accounting

<span id="fe9-sys-211"></span> The party stores current BEXP separately from gold and report totals. Clear awards increase the pool; base spending decreases it. The report's Bonus Exp counter describes the reporting period and can reset without erasing unspent pool balance. Save/load must preserve both meanings.

Pool accounting has three authoritative boundaries. Chapter-clear award logic requests a nonnegative addition. Base distribution validates that the requested spend does not exceed the current balance before subtracting it. Save/load serializes the resulting 32-bit party value. Presentation—including the clear breakdown, base total, and Soren's report—must read the appropriate stored result and must not independently mutate or recompute the pool.

This separation also defines failure behavior. Cancelling a unit selection or allocation leaves the pool unchanged. A failed or ineligible level-up must not spend points. Resetting the report period leaves the pool untouched. Modders adding a new award should use the same accounting entry point so the pool and report counter remain synchronized rather than writing one field directly.

## Distribution at the base

<span id="fe9-sys-212"></span><span id="fe9-sys-278"></span> The base BEXP menu selects an eligible unit and spends points toward the next 100-EXP level. Crossing the threshold invokes the active level-up mode, stat caps, and promotion rules; the menu must update pool, unit EXP/level, and any promotion transition atomically. Eligibility excludes units that cannot gain EXP or level further under current rules.

BEXP changes *where* EXP came from, not the definition of a level. Random/fixed growth, equipped growth modifiers, repeated threshold crossings, caps, and the level-20 promotion boundary all use the ordinary reviewed level-up path; BEXP has no independent growth formula.

## Breakdown display

<span id="fe9-sys-213"></span> After the relevant clear unlock, an option can show the chapter-end BEXP breakdown. This presentation should consume the same component results as accounting; it must not recalculate from already-reset flags or counters. The breakdown is distinct from Soren's later Battle Report.

## Interactions and review boundary

All BEXP systems are reviewed without a blocking research gap. Chapter-clear evaluation produces authored component awards, accounting updates the persistent pool and separate report counter, base distribution delegates to ordinary level-up/cap/promotion handling, and the breakdown reads the same component results. Chapter thresholds and optional-condition amounts are authored award data rather than an unknown BEXP engine formula. No new primary article is needed.

