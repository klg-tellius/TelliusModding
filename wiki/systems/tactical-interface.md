---
id: "tactical-interface"
title: "Tactical Map Interface"
description: "How cursor focus, range overlays, HUD windows, and commands expose authoritative tactical state"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["UI", "Maps", "Units"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "path-of-radiance-us-manual"]
cms_collection: "systems"
source_path: "systems/tactical-interface.md"
system_entries: ["FE9-SYS-062", "FE9-SYS-063", "FE9-SYS-064", "FE9-SYS-065", "FE9-SYS-337", "FE9-SYS-338", "FE9-SYS-339", "FE9-SYS-340", "FE9-SYS-342"]
system_reviewed: ["FE9-SYS-062", "FE9-SYS-063", "FE9-SYS-064", "FE9-SYS-065", "FE9-SYS-337", "FE9-SYS-338", "FE9-SYS-339", "FE9-SYS-340", "FE9-SYS-342"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Tactical Map Interface

The tactical interface is a view and controller over authoritative map state. It can ask movement, item, targeting, objective, and unit systems for candidates and show them as overlays or windows, but moving the cursor or previewing an action does not itself move a unit, consume an item, roll combat, or advance a phase.

## Mental model and worked example

Think of the interface as a stack of temporary questions. Hover asks “what is on this tile?” Selecting a unit asks “where may it move?” Picking a destination asks “which commands are legal here?” Choosing Attack asks “which weapons and targets are legal?” Confirming hands one validated request to the action executor. Cancel removes only the top question and restores the previous focus.

For example, selecting a cavalry unit runs movement search from its real tile using remaining movement, terrain costs, occupancy, and movement traits. Blue tiles display legal destinations. Moving the cursor to one destination builds commands but does not commit the move. Choosing Attack combines that candidate tile with each usable weapon's range and target filters; the resulting red tiles are attackable targets. Cancelling Attack returns to the command list, cancelling again returns to movement selection, and cancelling again returns the unit to ordinary map focus without changing authoritative position.

## FE9-SYS-062 — Movement-range display

<span id="fe9-sys-062"></span> Movement range consumes the weighted search and candidate-cost buffer produced by [Maps](./maps-system.md). Terrain cost, movement type, remaining allowance, directional links, occupancy, and caller-specific pass/stop rules determine candidate tiles; the interface merely colors those candidates and associates route previews with cursor focus. Canto reruns the same search from the action endpoint with remaining movement and its reduced command policy. Overlay color is presentation, while the candidate set is revalidated at commitment.

Selecting a destination adds context without mutating the unit. Canto or other post-action movement repeats the model from the action endpoint with a reduced allowance and stricter command choices. Fog and roofs can hide units or scenery without changing the underlying cost grid. A redraw is required after displacement, a door/bridge change, death/removal, status or movement changes, or any event that changes occupancy or terrain.

## FE9-SYS-063 — Attack and staff range display

<span id="fe9-sys-063"></span> Attack/staff range begins with a candidate origin, resolves each usable item's stored or dynamic minimum/maximum distance, and unions its reachable tiles. Target builders then apply effect-specific predicates: weapons require a legal hostile target, while staves share rank, silence, uses, and distance gates before healing, hostile-status, relocation, repair, or object rules specialize the result. Changing item narrows the union to that item's mask.

The visible overlay is therefore a preview of legal targeting, not a promise that every colored tile contains a target. Weapon choice can narrow the union, and final confirmation must revalidate inventory, status, target state, distance, and occupancy. Forecast consumes the selected actor/item/target tuple; it does not derive authority from pixel color.

## FE9-SYS-064 — Threat-range display

<span id="fe9-sys-064"></span> Threat display runs a non-committing enemy reach query: its movement search uses the map-link threat direction bits and threat-specific edge costs, combines candidate destinations with usable attack ranges, and aggregates the masks for one enemy or the danger view. It never advances AI, scores a target, chooses an action, or consumes RNG. The result is legal geometric reach from current state, so healing, escape policy, scripted activation, and AI preferences can still produce different behavior.

Fog and hidden-state rules constrain what the player may inspect. A hidden enemy must not leak its exact reach through the overlay unless the same state is otherwise visible. Changes to weapons, silence, transformation, movement, terrain, occupancy, allegiance, or activation require recomputation rather than recoloring stale data.

## FE9-SYS-065 — Map cursor

<span id="fe9-sys-065"></span> The cursor owns tactical tile focus and drives contextual inspection. Its current tile selects terrain, map objects, visible units, help, route previews, and destination candidates. Selection creates a focus stack—map, unit, destination, command, item, target, forecast—and cancel unwinds that stack without applying the previewed mutation.

Unit cycling and camera centering are cursor-navigation helpers, not unit-state operations. Hover respects fog, roof, and hidden-unit filters. Event scripts and presentation scenes can temporarily suppress or reposition cursor control, after which ordinary map focus is reconstructed. The transient focus stack is not serialized as authoritative gameplay state: checkpoint load restores cursor/map state and rebuilds legal UI from units, tiles, and scene ownership.

## Rules and lifecycle

1. Map focus reads cursor coordinates and builds safe terrain/unit/object windows.
2. Selecting a legal unit requests movement candidates from map search.
3. Cursor movement previews routes and destinations without committing them.
4. A destination requests a context-sensitive command list.
5. A command may request item, target, forecast, or secondary-destination state.
6. Confirmation revalidates mutable conditions and submits an action.
7. Completion refreshes authoritative state and all affected overlays/windows.
8. Cancellation discards only preview state; scene exit disposes all UI-owned state.

No preview should consume RNG, uses, actions, event flags, or turn count. Conversely, UI caches must be invalidated when a script mutates the map underneath them. If a target dies, an item breaks, or a door opens between menu creation and confirmation, execution must reject or rebuild the stale choice.

## HUD, status, commands, and help

<span id="fe9-sys-337"></span> **Map HUD.** Cursor tile, terrain, hovered visible unit, turn/phase, objective, contextual panels, and ranges are read-only views over current state. Window priority follows the active focus stack—modal child, command/target context, then ordinary map panels—rather than one static global ordering. Committed state changes invalidate affected panels.

<span id="fe9-sys-338"></span> **Unit status.** Status pages resolve effective current stats through gameplay getters and read equipment, ranks, skills, supports, biorhythm, condition, and biography/help from the same runtime/save owners used by forecast and commands. Paging and viewing are non-mutating; the screen does not recalculate by writing derived values back to the unit.

<span id="fe9-sys-339"></span> **Map command menu.** With map focus, entry objects dynamically gate Unit, Status, Objective, Guide, Options, Suspend, End, and context-specific commands against scene and progression state. A selected entry delegates to its child process; the menu regains focus and refreshes only when that child returns.

<span id="fe9-sys-340"></span> **Unit command menu.** From a candidate destination the menu queries command classes for availability, then opens their item, target, or secondary-destination children as required. Confirmation revalidates and hands a command/action identity plus its selected operands to the shared executor; cancellation discards only preview state.

<span id="fe9-sys-342"></span> **Help text.** Focus resolves a stat, item, skill, terrain, objective, command, or option to a message key and presents the resolved message modally or contextually. Missing or unresolved keys fall back safely instead of changing the underlying selection. Closing help returns focus to the exact requesting widget; help explains mechanics but never owns them.

## Interactions, edge cases, and implementation trail

The interface depends on movement/pathfinding, occupancy, item usability, combat forecast, staves, map objects, visibility, objectives, action menus, camera, and save/resume. The relevant evidence trail follows cursor/map-input handlers into movement search and target builders, then into overlay draw processes and command-menu entry classes. Comparing the player preview with AI range masks and final action validation is useful for detecting divergent copies of a rule.

Important tests include zero-move units; impassable or occupied endpoints; hidden enemies; roofs; dynamic-range items; siege objects; post-action movement; allegiance changes; weapon breakage; status changes while a menu is open; and suspend/reload at each focus level. Pixel colors and input timing are presentation details, while candidate sets and cancellation behavior are mechanical contracts.

## Review boundary

All nine tactical-interface systems are reviewed without a blocking research gap. Executable paths establish overlay inputs, Canto reuse, item-range unions, threat-search differences, transient cursor focus, window priority, getter-owned status values, command delegation, help fallback, and reconstruction after Suspend. Pixel placement, color tuning, and per-screen command ordering remain implementation detail rather than missing system contracts. No new article is needed.
