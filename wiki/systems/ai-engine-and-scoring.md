---
id: "ai-engine-and-scoring"
title: "AI Engine, Targeting & Scoring"
description: "How AI phases interpret behavior programs, enumerate candidates, score attacks and movement, and resolve ties"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["AI", "Maps", "Combat"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/ai-engine-and-scoring.md"
system_entries: ["FE9-SYS-251", "FE9-SYS-252", "FE9-SYS-253", "FE9-SYS-254", "FE9-SYS-255", "FE9-SYS-256", "FE9-SYS-257", "FE9-SYS-258", "FE9-SYS-273"]
system_reviewed: ["FE9-SYS-251", "FE9-SYS-252", "FE9-SYS-253", "FE9-SYS-254", "FE9-SYS-255", "FE9-SYS-256", "FE9-SYS-257", "FE9-SYS-258", "FE9-SYS-273"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# AI Engine, Targeting & Scoring

AI is a pipeline, not one intelligence value: the phase scheduler chooses a unit, its behavior program selects steps, the engine enumerates legal candidates, scoring ranks them, and deterministic tie rules choose one action.

## Scheduling and programs

<span id="fe9-sys-251"></span> **AI phase scheduler.** Phase start builds one deterministic turn-order list from the active army. Its base key is `(signed ai_turn_order + 128) << 16`, adjusted by movement, the phase threat at the unit's tile, and item/skill terms. The decision process walks that sorted list, skipping dead, carried, hidden, reserve, escaped, or acted units; recovery and special dispatch run before the unit's ordinary attack/move script, then action completion returns to the next list entry.

<span id="fe9-sys-252"></span> **AI bytecode/interpreter.** `cp_data.bin` scripts are 28-byte, seven-word entries. Attack and move counters select a step, and the opcode is binary-searched in the identical 52-handler US/PAL/JP table. Action handlers register a candidate and later actions overwrite it, which is why retail scripts branch on `JUMP_IF_FOUND`; unknown opcodes or empty candidates cannot commit an action. Unit script names, counters, flags, and route/try state persist across a map save.

<span id="fe9-sys-253"></span> **AI group/order assignment.** Deployment resolves named attack, move, heal, and movement-type sections from the same registered CP database and associates them with the unit/group/commander. Script setters replace only the named sequences they receive; a null retains the existing sequence, while a changed running sequence resets its counter and terminates the current run. Replacing both attack and move also clears escape and resets try/route state, giving script replacement explicit priority over deployment defaults.

## Candidates and scores

<span id="fe9-sys-254"></span> **Target enumeration.** Each operation builds its own candidate family and then applies common legality. CP attack opcodes use `e=0` for hostiles, a named PID list with `d=0` for members regardless of side, or `d!=0` for hostile units excluded by the list; single-PID and JID variants are explicit. Healing, items, terrain, escape, and skills use their own builders. Range, path, occupancy, status, item use, and operation predicates reject candidates before scoring.

<span id="fe9-sys-255"></span> **Attack scoring.** Candidate target/weapon/tile records combine forecast damage/hit, kill and counter terms, target attributes, adjacent-unit weights, and operation parameters. Chance fields on action opcodes use `roll_random_int(100) <= percent`, so even zero has the executable's inclusive 1% edge. Comparison chooses deterministically, but the selected battle later performs ordinary authoritative hit/critical/proc rolls; the score never substitutes for resolution.

<span id="fe9-sys-256"></span> **Movement scoring.** Movement operations enumerate reachable free tiles, apply object/special-terrain exclusions, compare path/destination distance and the active threat limit, then use operation-specific tile scores. Under-limit tiles are preferred; an over-limit tile is considered only when the opcode enables fallback. `move_nearest` selects the closest legal destination, while raw-threat refuge movement selects the first minimum-threat tile. The operation comparator, not one universal formation coefficient, defines ties.

## Danger maps

<span id="fe9-sys-257"></span> **Per-unit threat map.** For the deciding unit, each hostile contributes its best usable close weapon (highest might, first tie) and ranged weapon (longest range, then might). Value is `max(0, Atk−Def) × Hit/100`; when AS is at least four higher it becomes `2 × damage × (1−(1−Hit/100)^2)`, truncated and capped at 255. Reachable strike masks exclude occupied/object tiles and designated ally-phase special terrain; hostile contributions add with a 255 cap.

<span id="fe9-sys-258"></span> **Phase danger map.** Before turn ordering, the phase builder paints every hostile weapon's might plus Strength, or Magic for magic weapons, over its reachable strike area and sums to 255. Turn priority reads this phase map. Before each unit's script runs, the decision process clears/replaces it with that unit's forecast-derived hostile map; Warp temporarily builds another faction view and restores the deciding unit's map on every return branch. Consumers therefore have an explicit construction point, not ambiguous shared state.

<span id="fe9-sys-273"></span> **Tie-breaking and scan order.** Tie behavior belongs to each comparator. Staff target scans walk Y then X and use `<=`, so the last equal target wins; movement tile selection often uses strict improvement, so the first equal tile wins; staff slots use equal-or-higher replacement, while best-weapon scans retain the first equal item. The documented opcode/operation comparator is authoritative—there is no missing engine-wide tie rule.

## Mental model and worked trace

For one enemy, record behavior step, legal weapons, reachable tiles, enumerated targets, each score component, danger value, and final tie. Then compare the committed move/attack and later RNG result. The decoded 52-opcode table, phase priority key, two threat-map formulas, and comparator-local tie rules make this trace reproducible across all retail builds.

## Rules and lifecycle

At phase start the scheduler selects the next eligible unit from the active non-player force. Saved behavior/interpreter state chooses an operation. That operation enumerates only its relevant candidates, runs common legality filters, and scores each legal target/action/tile combination. Deterministic comparison selects the best candidate; execution revalidates it, commits movement or action through ordinary map/combat systems, updates interpreter and acted state, and returns control to the scheduler. When no candidate survives, the operation follows its program's fallback or advances without inventing an illegal action.

Prediction and execution are deliberately separate. Attack scoring may estimate damage, hit, doubling, and counter risk, but the committed battle still consumes the shared RNG and authoritative combat rules. Movement scoring can use danger estimates without modifying the real threat or HP state. Saving midphase must retain the active unit's program position and already-acted units so reload cannot repeat or skip decisions.

Failure behavior matters for modding. An unknown opcode, missing destination, empty candidate set, unreachable target, or malformed weight must not be treated as permission to attack anything. Candidate arrays and danger maps are transient and should be rebuilt from saved units/map state; interpreter choices and progress are persistent where the save format records them.

## Interactions and limits

All nine AI engine/scoring systems are reviewed without a blocking research gap. Scheduling, all 52 opcode dispatches, script replacement, target-filter modes, movement limits, per-unit/phase threat construction, and comparator-specific ties establish the scheduler→program→enumeration→score→commit pipeline. Per-script weights and PID/route tables remain authored CP data, not unknown engine rules. No new primary article is needed.

