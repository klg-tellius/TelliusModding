---
id: "modding-play-chapter"
title: "Play and rewind a chapter in the app"
description: "A deep Play workflow covering initialization, difficulty, commands, transport granularity, history snapshots, scripts, flags, AI, messages, unsupported systems, fresh-run reloads, and Dolphin handoff"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Play", "Testing", "Debugging"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/58-play-chapter.md"
tutorial_kind: "task"
tutorial_track: "test-and-release"
tutorial_stage: "draft"
prerequisites: ["modding-script-editor", "modding-event-flags", "modding-common-ai-orders"]
verification: ["source-reviewed", "unknown"]
---
# Play and rewind a chapter in the app

**Route:** Chapter → Build → Play…

## What you will make

You will create a reproducible chapter test, step across one event/AI boundary at the correct granularity, inspect state and traces, rewind to compare an alternative choice, restart after project edits, and hand the remaining engine-only checks to Dolphin.

## Before you begin

Save all chapter resources. Write one falsifiable expectation, such as “on enemy phase of turn 3, section X loads once, flag Y becomes set, and it does not load again.” Record chapter part, difficulty, opening choice, roster, flags, inventories, positions, and project revision.

## How the editor fits together

Play loads a snapshot of project data into a simulation world. History entries hold deep state snapshots and outputs; rewind restores them. Panels expose selected unit, pending queue, event script/call stack/source, flags, AI interpreter/ranking, messages, and log.

It approximates the turn/phase/action and event systems, not the entire GameCube runtime. Fog presentation, preparations, choices, cameras, `MapLoad`, some skills/AI/effects, and other native behavior can be absent or simplified.

## Guided walkthrough

Start Play with the intended difficulty. Keep the opening when it creates units, registers events, sets flags, or establishes variables. Skip it only after proving the target state is identical.

Pause immediately before the boundary. Use the smallest transport step that answers the question: script line/message for dialogue logic, action for commands, AI unit for target choice, phase/turn for reinforcements. Inspect the relevant panel before and after, and capture the log/output.

For a one-time event, continue through the next possible trigger and prove its guard. For recruitment, verify faction, control, inventory, actor state, flags, and persistence. For AI, read active sequence and eligibility/ranking before judging the chosen action.

Rewind to the pre-boundary snapshot and make one different in-simulation choice. Compare outcomes. After editing project files, close/restart Play; rewind never reloads new bytes.

Complete the objective and inspect transition/state. Then build and reproduce the supported claim plus all documented gaps in Dolphin.

## Understand every control

- **Difficulty/opening options:** choose loaded variants and initialization path.
- **Map/unit actions:** manipulate simulated tactical state under supported rules.
- **Transport granularity:** line, message, action, AI unit, phase, or player turn.
- **History/rewind:** branches within loaded state; not project-data reload.
- **Unit/script/flag/AI/message/log panels:** evidence for different owners.
- **Follow activity:** tracks current work; disable when examining earlier context.

## Interactions and precedence

Initialization creates the state later tests consume. Event queue order, flag guards, action completion, AI scheduler, and phase/turn transitions can alter later eligibility. Comparing different starts or letting extra actions occur invalidates a causal comparison.

## Test matrix

| System | Success, boundary, repeat/failure |
| --- | --- |
| deployment | correct difficulty/section; absent counterpart |
| event | condition false/true; guard prevents repeat |
| recruitment | wrong/right actor; save-like persistence state |
| reinforcement | before/exact/after turn and blocked tiles |
| AI | eligible/ineligible targets and recovery pre-emption |
| objective | incomplete/complete/defeat and transition |
| rewind | alternative choice from identical snapshot |
| fresh run | saved project edit appears only after restart |

## Troubleshooting

**Expected event never runs.** Inspect initialization, queue, function, condition, flag, phase/turn, and deployment owner.

**Rewind ignores an edit.** Restart Play; snapshots retain the loaded resources.

**Play passes but Dolphin fails.** Locate the feature in the limits list and test its native owner rather than weakening correct authored data.

## Save, build, and revert

Play state is disposable. Save fixes in their owning editors, restart and reproduce, run checks, build, and perform a fresh Dolphin run. Preserve the expectation, starting-state checklist, and observed logs.

## Limits and confidence

Supported simulator state/trace behavior is source-reviewed, but Play is deliberately not full emulation. A passing test narrows authored logic errors; it does not establish graphics, native code, timing, save, or unsupported-system parity.

## Related tutorials and references

- [Inspect why AI chose a target](45-inspect-ai-decisions.md)
- [Turn, Phase & Action Cycle](../systems/turn-phase-action-cycle.md)
- [Events & Scripting](../systems/events-scripting.md)

---

[← Previous: Apply engine tweaks](57-game-code.md) · [All tutorials](index.md) · [Next: Edit and test a save →](59-save-editor.md)
