---
id: "battle-reports-records"
title: "Battle Reports & Performance Records"
description: "How chapter activity becomes Soren's report, MVP, unit statistics, clear history, and completion records"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Records", "Base", "Research needed"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/battle-reports-records.md"
system_entries: ["FE9-SYS-216", "FE9-SYS-217", "FE9-SYS-218", "FE9-SYS-219", "FE9-SYS-220", "FE9-SYS-282"]
system_reviewed: ["FE9-SYS-216", "FE9-SYS-217", "FE9-SYS-218", "FE9-SYS-219", "FE9-SYS-220", "FE9-SYS-282"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Battle Reports & Performance Records

FE9 records performance at three scales: counters for the most recent reporting period, lifetime statistics attached to units, and a playthrough history of cleared chapters. Soren's base report is presentation over this state, not the owner of every statistic.

## Mental model and example

Think of the records system as three notebooks written at different times. A unit notebook accumulates battles, kills, and movement across actions. A chapter-clear notebook appends the identity, part, turns, and elapsed time when a map ends. A short-period report notebook accumulates gold and EXP changes until Soren presents and resets it. If a unit earns a kill on turn 8, that action can update the unit notebook immediately; clearing the map later records turn 8 in history; neither write is reconstructed from the later report screen.

This distinction is essential for save editing. Changing a report counter does not create a lifetime kill, and changing a unit's lifetime kills does not rewrite a past chapter entry. Viewers should consume the appropriate owner instead of silently copying values among them.

## FE9-SYS-217 — Per-unit records

<span id="fe9-sys-217"></span> Each serialized unit has counters for battles, lifetime kills, kills on the current map, tiles moved, chapter of last kill, and two fields not yet fully named. Combat and movement update them at the action/consequence stage. A carried, scripted, or event battle must be tested before assuming it counts like an ordinary player command.

The mutable unit is the owner, so changing deployment or presentation does not by itself create a statistic. Battle counters update from committed exchanges, kills from confirmed death consequences, and distance from committed movement rather than cursor preview. Map-local kill counts reset at the chapter/deployment boundary while lifetime totals persist. The two unnamed neighboring fields must be preserved by editors until identified, but they do not change ownership of the named counters.

## FE9-SYS-218 and FE9-SYS-219 — Clear history and time

<span id="fe9-sys-218"></span> Party state contains forty clear-history entries with chapter, part flag, turns, and elapsed seconds. Multi-part chapters need the part discriminator so identical chapter identity does not collapse separate maps.

<span id="fe9-sys-219"></span> Play time is tracked by runtime tick counters and copied into clear history. It is independent of turn count: pausing, dialogue, base management, and battle animation can affect real time without advancing a tactical turn. Suspend/resume must avoid double-counting or losing the saved interval.

## Rules and lifecycle — action, clear, and display

During a map, committed actions update unit-owned counters and the live time service advances independently of tactical turns. Victory freezes or samples the map's final turn and elapsed interval, then appends one clear-history record using both chapter identity and part. Save serialization preserves unit records, history entries, and current time ownership. Records menus and ending/report presentation read these values later; opening a viewer must not increment, normalize, or recompute them.

The forty-entry capacity is a hard research boundary. A safe editor must preserve array order and part identity and should reject an out-of-range count until the retail overflow policy is known. Likewise, a suspended session must restore the accumulated base tick exactly once before new ticks are added.

## FE9-SYS-282 — Base report presentation

<span id="fe9-sys-282"></span> Soren's report reads four signed 16-bit counters: gold earned, gold spent, Combat Exp, and Bonus Exp. Gold setters update earned/spent by actual clamped balance movement. EXP/BEXP award paths update their corresponding counters. Presentation occurs in the base, then the reporting counters reset for the next period while current gold/BEXP and unit progression remain.

## FE9-SYS-216 — MVP selection

<span id="fe9-sys-216"></span> MVP is a selected unit in the chapter report, not one of the four signed period totals. The traced selector iterates eligible campaign units and chooses the maximum current-map kill field at unit offset `+0x22C`; the iteration/comparator supplies deterministic tie behavior. It runs after chapter activity has populated unit state and before the report panel renders the chosen identity alongside joined/dead information, and it does not mutate any counter.

## FE9-SYS-220 — Completion records

<span id="fe9-sys-220"></span> Postgame Records combines persistent clear history, difficulty/clear/playthrough flags, roster and survival facts, and per-unit statistics into viewable completion records. The viewer is a read-only consumer: opening it does not create clears, rewrite history, or normalize unit counters. Stored facts remain owned by save/unit records; labels, ordering, unlock visibility, and empty-state formatting are derived presentation tables.

## Interactions and review boundary

All record systems are reviewed without a blocking research gap. Committed actions update unit counters, chapter clear appends keyed history, elapsed time has one service owner, MVP selection consumes current-map performance, Soren's four signed period counters reset independently of persistent balances, and postgame Records is read-only. Labels and per-screen ordering are presentation tables rather than missing persistence rules. No new primary article is needed.

