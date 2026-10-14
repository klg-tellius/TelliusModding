---
id: "ai-activation-and-orders"
title: "AI Activation, Routes & Orders"
description: "How dormant, patrolling, defending, escaping, and partner-controlled units receive tactical policies"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["AI", "Events", "Objectives"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/ai-activation-and-orders.md"
system_entries: ["FE9-SYS-259", "FE9-SYS-260", "FE9-SYS-261", "FE9-SYS-262", "FE9-SYS-272"]
system_reviewed: ["FE9-SYS-259", "FE9-SYS-260", "FE9-SYS-261", "FE9-SYS-262", "FE9-SYS-272"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# AI Activation, Routes & Orders

These systems provide **policy** to the scoring engine: when a unit wakes, what destination matters, and which actions it may consider.

## Mental model and example

Policy narrows the AI engine without replacing it. A dormant enemy has a policy that offers no ordinary advance until its trigger is satisfied. After a player crosses an area boundary, the saved activation state changes; on the next eligible decision, the same unit can enumerate attacks and movement under its assigned program. A patrol policy contributes its next waypoint, a hold policy constrains destinations, and an escape policy contributes an exit. Common legality and scoring still decide among permitted actions.

This explains why changing a boss's class does not make it leave a throne: the restriction belongs to behavior state. Conversely, changing the behavior script can release the boss without touching movement type, stats, or terrain.

<span id="fe9-sys-259"></span> **FE9-SYS-259 — Aggro/activation zones.** Turn, area, damage, distance, flag, and event conditions are authored script/group inputs that converge by replacing or enabling the unit's CP sequence. The script setter resets a changed sequence counter and current run, so the latest executed setter wins; group scripts explicitly propagate when desired rather than through an implicit global wake. Resulting sequence/activation state is saved, so reload does not reapply deployment dormancy.

<span id="fe9-sys-260"></span> **FE9-SYS-260 — Route and patrol AI.** Opcode 216 reads a named route of packed `(x,y)` waypoints terminated by `0xFFFF0000`. The stored waypoint index supplies the current destination; ordinary search chooses the closest legal progress tile under the script's threat policy. A permitted attack registers before route movement and interrupts that turn only. Reaching a waypoint advances stored route state; no path yields the opcode's no-action/fallback path without skipping the waypoint.

<span id="fe9-sys-261"></span> **FE9-SYS-261 — Boss/hold-position AI.** `_IN_PLACE` attack/staff/steal/skill opcodes set CP flag bit 1 only around candidate construction, causing movement search to expose the unit's current tile alone. Legal in-range actions still register normally. Displacement does not rewrite the hold destination—the current occupied tile becomes the only candidate on the next decision—and a later script sequence replacement removes or changes the constraint explicitly.

<span id="fe9-sys-262"></span> **FE9-SYS-262 — Escape AI.** Opcode 211 chooses the nearest event-kind-44 escape point, paths toward it through ordinary safe movement, and registers action 44 when the unit reaches it. The unit's escape bit prevents ordinary reuse; optional-objective/BEXP consequences remain owned by the map event. Heal priority can pre-empt the move for that turn, while an unreachable/occupied goal produces movement fallback rather than teleportation.

<span id="fe9-sys-272"></span> **FE9-SYS-272 — Partner-unit orders.** The Order menu maps each visible choice to a stored yellow-army CP policy/parameter; choosing another entry replaces that policy for subsequent partner decisions and persists with map state. It never transfers force ownership or grants direct control. The partner phase rebuilds ordinary candidates, threat, movement, and actions under the selected policy; chapter/deployment reinitialization supplies its reset boundary.

## Rules and lifecycle

Deployment and group data assign an initial policy, destination, route, activation conditions, and recovery profile. Events or player partner commands may replace or parameterize that policy. At decision time, the policy exposes goals and permitted action families to the common AI engine. The engine enumerates legal choices, scores them, commits one, and updates route, activation, escape, or acted state. Save/load must preserve transitions that have already occurred.

Activation is generally one-way unless an authored script resets it: once a group wakes, reloading must not restore dormancy. Routes maintain which waypoint or destination is current. An attack may interrupt movement only when the operation permits it, after which the route can resume or advance. Hold-position behavior can attack in range while refusing destination tiles outside its constraint. Escape behavior commits through the map's escape action so unit removal and optional-objective flags remain synchronized.

Partner commands operate at a different input boundary. The player chooses a broad priority, then the yellow army's phase still owns target enumeration, danger, movement, and action commitment. “Direct,” “Halt,” or related visible choices must be mapped to the underlying policy fields before editors rename or reorder them.

## Interactions and edge cases

A blocked route, absent goal, dead commander, displaced boss, already-occupied exit, newly available lethal attack, or healing emergency can force a fallback. The policy must never bypass pathfinding, allegiance, occupancy, or action legality. Script changes made midphase also need a defined boundary: either the active decision completes under its snapshot or enumeration restarts under the new policy.

## Interactions and limits

For each policy, vary activation boundary, target availability, danger, blocked route, healing need, and save/reload. The decoded sequence setters, route opcode, in-place flag, escape action, and partner-policy handoff establish how those cases enter the common engine. Individual chapter activation expressions, waypoint lists, and menu labels are authored content. All five systems are reviewed without a blocking gap, and none needs a new primary article.

