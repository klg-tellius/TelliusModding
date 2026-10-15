---
id: "status-effects"
title: "Status Effects & Temporary Bonuses"
description: "How poison, sleep, silence, berserk, temporary Resistance, and terrain healing are stored and advanced"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Status", "Turns", "Combat"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/status-effects.md"
system_entries: ["FE9-SYS-230", "FE9-SYS-231", "FE9-SYS-232", "FE9-SYS-233", "FE9-SYS-234", "FE9-SYS-235"]
system_reviewed: ["FE9-SYS-230", "FE9-SYS-231", "FE9-SYS-232", "FE9-SYS-233", "FE9-SYS-234", "FE9-SYS-235"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Status Effects & Temporary Bonuses

A status is mutable unit state with an application rule, gameplay effect, duration, tick boundary, display, cure path, and save representation. Those parts must be documented together: knowing that Sleep disables actions is incomplete if reload or phase timing changes how long it lasts.

## Mental model and example

Treat a status as a small saved state machine, not a label painted over a unit. Application validates the target and writes type plus duration or amount. While active, command builders, combat legality, AI, stat getters, and phase consequences consult it. A phase boundary can apply a periodic effect and decrement duration; reaching zero clears the state and refreshes capabilities. Restore is an alternate transition to the same cleared state.

For example, a silenced unit may still have a tome marked equipped in its serialized inventory, but player command construction and AI scanning must reject magic/staff use while the status is active. When Silence expires or Restore clears it, legality is rebuilt from the unchanged inventory; the status does not need to destroy or unequip the item permanently.

## Individual negative statuses

<span id="fe9-sys-230"></span> **FE9-SYS-230 — Poison.** A successful weapon/effect handler writes Poison plus its duration into the unit's temporary-status field. The phase-status handler computes and applies its configured periodic HP loss, routes zero HP through ordinary death processing, decrements/clears duration, and refreshes display. Restore reaches the same clear transition. Terrain healing is a separate phase consequence, so neither silently cancels the other's stored state.

<span id="fe9-sys-231"></span> **FE9-SYS-231 — Sleep.** Sleep removes ordinary player/AI action eligibility while preserving force, occupancy, targeting, rescue/carry state, and scripted-unit identity. Refresh cannot clear the condition or make an ordinary action legal. Its saved duration is stepped by the status owner; expiry or Restore clears it and rebuilds availability before the unit may be scheduled again.

<span id="fe9-sys-232"></span> **FE9-SYS-232 — Silence.** Silence filters tome and staff use at command construction, AI inventory scanning, target building, and counter scheduling. Inventory/equip identity remains serialized but cannot bypass the final usability check. Non-magical items and script operations use their own legality rather than force-changing equipment. Expiry or Restore removes the filter and triggers normal command/equipment refresh.

<span id="fe9-sys-233"></span> **FE9-SYS-233 — Berserk.** Berserk temporarily routes the affected unit through hostile-target AI policy during its action while leaving the stored force/army identity unchanged. Consequently occupancy, Talk/support identity, commander auras, objective ownership, and kill/stat attribution still use the real force. Candidate legality applies the temporary targeting policy; expiry or Restore returns control without transferring the unit between army lists.

## Rules and lifecycle — shared temporary state

<span id="fe9-sys-234"></span> **FE9-SYS-234 — Temporary status lifecycle.** Unit save state contains temporary status/bonus fields. Application validates immunity/current state and stores type plus duration/amount. Phase initialization applies periodic consequences and/or decrements duration, then clears expired state and refreshes UI/action legality. Restore and chapter transitions provide alternate removal paths.

Replacement and stacking are effect-handler decisions before that shared write: a rejected immune/incompatible target leaves current state unchanged, while an accepted refresh/replacement produces one authoritative type/value. Phase consumers dispatch by that type rather than running every possible status. Periodic HP changes complete death checks before later action scheduling; save/load restores the fields, not an in-progress status animation.

Temporary Resistance from Ward/Barrier/Pure Water belongs to this lifecycle even though it is beneficial. Correct ordering matters when a status staff attacks on the same boundary that a bonus decays.

## Implementation trail and controlled phase test

The reproducible trail begins at weapon properties and hostile-staff resolution, follows successful application into the unit's serialized status/duration fields, then enumerates every reader: player commands, AI selection, combat/item legality, icons/help, phase initialization, Restore/cure, and save/load. Consequences must be separated from presentation so suppressing animation cannot suppress damage, expiry, or restored action eligibility.

A controlled test creates otherwise identical saves immediately before each army phase. Give separate subjects Poison, Sleep, Silence, Berserk, and temporary Resistance; place the poisoned subject on healing terrain. Advance exactly one phase with animations enabled and disabled, then compare HP, status identity/duration, action state, allegiance/AI policy, Resistance, event flags, and objectives. Repeat at duration one, with Restore before the tick, lethal poison HP, rescue/carry, refresh, scripted actions, and suspend/reload. This isolates phase ownership and ordering.

Replacement needs its own single-variable tests: reapply the same effect, apply a different effect, target an immune unit, and cure immediately. Record whether duration replaces, extends, stacks, or rejects; whether item use commits; and when UI/AI refresh occurs. Regional and difficulty comparisons must hold unit, item, map, and phase constant.

Application must distinguish immunity, replacement, and coexistence. The currently documented representation stores temporary state on the mutable unit and survives save/load. Phase initialization owns periodic consequences and duration changes, while command and forecast consumers read the current value between boundaries. Expiry or cure clears the relevant field, removes its icon/effect, rebuilds command legality and derived values, and must not erase unrelated permanent stats or inventory state.

<span id="fe9-sys-232-detail"></span> **Silence in that lifecycle.** Silence is a legality filter rather than an allegiance or inventory mutation. It suppresses applicable tome and staff choices for player and AI, and final resolution revalidates it if status changes after a menu was opened. Scripted operations remain governed by their own explicit predicates instead of an implicit exception matrix.

<span id="fe9-sys-235"></span> **FE9-SYS-235 — Terrain healing.** Terrain records carry a percentage-of-max-HP heal value. The phase consequence reads the unit's current tile and effective maximum HP, applies integer recovery capped at maximum, and schedules its presentation. It does not create a saved status. Poison and terrain remain separate ordered phase handlers, and death/objective/event checks observe the HP produced by the consequence that just completed.

## Interactions and limits

All six status systems are reviewed without a blocking research gap. Application predicates, single authoritative temporary state, saved duration/value, per-type phase dispatch, legality/control consumers, cure/expiry, terrain recovery, and downstream death/objective checks establish the system boundary. Item-specific duration/damage values and chapter terrain percentages remain data tables. These effects belong in this shared lifecycle article; no new primary article is needed.

