---
id: "battle-preparations"
title: "Battle Preparations"
description: "How the prebattle map selects a roster, starting positions, equipment, inspection state, and resume save"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Chapters", "Deployment", "UI"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "path-of-radiance-us-manual"]
cms_collection: "systems"
source_path: "systems/battle-preparations.md"
system_entries: ["FE9-SYS-283", "FE9-SYS-284", "FE9-SYS-285", "FE9-SYS-286", "FE9-SYS-287"]
system_reviewed: ["FE9-SYS-283", "FE9-SYS-284", "FE9-SYS-285", "FE9-SYS-286", "FE9-SYS-287"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Battle Preparations

Preparation is a provisional map scene: chapter resources and enemy deployment are visible, but player deployment and management can change until Battle Start commits them.

## Mental model and example

Preparation is a transaction over an initialized chapter. Enemy deployment, terrain, objectives, and player start slots exist so they can be inspected, but turn 1 has not begun. The player may edit persistent unit inventories and skills while separately editing a provisional selected roster and formation. Pressing Battle Start validates and commits the provisional portion, then hands off to opening events and the turn/phase cycle.

For example, trading a sword between two units changes their persistent inventory immediately, while swapping their blue start positions changes chapter formation state. Cancelling a formation swap should restore the prior slot assignment without undoing the valid inventory trade. Saving in preparation must preserve both kinds of state and resume in preparation rather than pretending the player already started the map.

## Rules and lifecycle

Entry initializes enough of the chapter to display map objects, terrain, enemy units, objectives, ranges, and legal player starting slots. The preparation controller builds its facilities and the selectable roster from campaign and chapter state. Roster selection enforces the chapter maximum plus mandatory, prohibited, unavailable, story-fixed, and surplus conditions. Formation assigns selected units to legal player slots subject to fixed/swap rules.

Management commands operate on persistent party and unit data: inventory, Trade, Supply, equipment, skills, and relevant options. Inspection is read-only with respect to tactical simulation: moving the cursor or viewing an enemy cannot advance AI, events, statuses, turn count, or RNG. Preparation Save serializes the provisional roster/formation and the persistent edits with a resume route back to this scene.

Battle Start revalidates selected count and required units, resolves formation into deployed player units, commits their start coordinates/order, and leaves preparation. Only then should map-start initialization, opening events, turn counter, and Player phase begin in their established order. A validation failure returns control without partially starting the battle.

<span id="fe9-sys-283"></span> **Combat preparation screen.** It combines roster selection, formation, inventory/trade/supply, skills, map/objective/enemy inspection, options, save, and start. Changes affect persistent units while formation belongs to the current chapter setup.

<span id="fe9-sys-284"></span> **Deployment limit and selection.** The chapter supplies a maximum plus mandatory, unavailable, prohibited, or story-fixed units. The screen tracks selected count and surplus; Battle Start rejects an invalid roster.

The selected count is not sufficient by itself: a roster at the numeric maximum can still be invalid if a mandatory unit is absent or a prohibited/unavailable unit remains selected. Conversely, story-fixed deployment can reserve a slot and constrain formation independently of the free choices. UI feedback must be derived from the same final validator used by Battle Start so the visible count cannot promise an illegal roster.

<span id="fe9-sys-285"></span> **Starting-position assignment.** Selected units occupy player start slots. Swapping is allowed only within chapter rules; mandatory/fixed slots and map occupancy must remain valid. Final slot order influences unit placement and can affect later deterministic enumeration.

<span id="fe9-sys-286"></span> **Preparation inspection.** The player can inspect terrain, enemies, inventories, ranges, and objectives without beginning turn 1. Displayed data comes from initialized chapter definitions/deployments but must not advance AI, events, RNG, or statuses.

<span id="fe9-sys-287"></span> **Preparation save.** It preserves management and selected formation plus a resume point that reconstructs preparation, not an already-started tactical phase. Battle Start then commits roster/slots, runs map-start initialization/events, and enters the turn/phase cycle.

## Interactions and edge cases

Roster changes must update formation without leaving duplicate units or occupied slots. Removing a selected unit may free its slot; adding one needs a legal free slot or explicit swap. Story events, death/retreat state, trial units, forced lords, and chapter variants can change eligibility. Full inventories and convoy access affect management but should not corrupt deployment. Reload must reconstruct the same provisional selection and not replay battle-start-only events.

## Interactions and review boundary

All preparation systems are reviewed without a blocking research gap. Entry creates provisional deployment state, roster filters and fixed-unit rules constrain selection, formation edits reserve legal tiles, management delegates persistent unit/item changes, and Battle Start validates then commits deployment before opening events and phase initialization. Chapter-specific mandatory/prohibited lists and formation coordinates remain authored data. No new primary article is needed.

