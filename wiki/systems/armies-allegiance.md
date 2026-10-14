---
id: "armies-allegiance"
title: "Armies & Allegiance"
description: "Which side a unit is on isn't a stored label — it's which of eight runtime lists that unit currently belongs to"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure","Combat"]
aliases: ["tellius_archive.html#/armies-allegiance"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/armies-allegiance.md"
system_entries: ["FE9-SYS-021", "FE9-SYS-022"]
system_reviewed: ["FE9-SYS-021", "FE9-SYS-022"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Armies & Allegiance

*Which side a unit is on isn't a stored label — it's which of eight runtime lists that unit currently belongs to*

Every unit slot in the game belongs, at any moment, to exactly one of eight runtime lists. Which list a unit is in is not a side-effect of some other stored value — it *is* the unit's current allegiance. Moving a unit to a different army means physically relinking it into a different list, not flipping a byte read elsewhere.

## FE9-SYS-021 — Army and allegiance system

<span id="fe9-sys-021"></span>

<div class="table-wrap">
<table><thead><tr><th>List</th><th>Meaning</th></tr></thead><tbody>
    <tr><td>Player</td><td>The deployed, player-controlled roster</td></tr>
    <tr><td>Enemy</td><td>Ordinary hostile units</td></tr>
    <tr><td>Ally / orderable</td><td>Shown in a distinct color, and directly commandable through Ike's Order action rather than acting on its own initiative</td></tr>
    <tr><td>Other</td><td>A fourth army — neither player, enemy, nor orderable ally — used for green-flagged neutral or story-scripted units</td></tr>
  </tbody></table>
</div>

## Rules and lifecycle — four more list states

  Four further list ids exist purely as bookkeeping states rather than battlefield sides: a shared pool holding every currently-unused unit slot, the player's reserve/deployment-select pool before a chapter starts, an inactive/flagged state, and a further hidden/removed state. A unit sitting in one of these is not on the map as any army — it is waiting, benched, or cleared.

!!! info "Mental model: allegiance is where you're linked in, not what you're labeled"
    Asking "what army is this unit" is really asking "which list is this unit's node currently part of." Recruiting an enemy into the player's army, or benching a player unit to the reserve pool, is the same underlying operation either way: unlink from the old list, link into the new one.

## Comparing two units' allegiance

  Combat and AI reduce a pair of lists to one of three relation outcomes rather than comparing raw list identities for every decision: *same side* (identical list), *opposing* (either side is the enemy list), or *other* (any other differing pair, such as ally vs. green). This third case is what lets an orderable ally and a neutral green unit coexist without either automatically reading as the other's enemy.

## Example — recruiting a unit into the player's army

  A story event that recruits a unit moves that unit's slot from its current list into the player list. The transfer preserves stats, inventory, and position, but it is not visually inert: it takes the destination force's first commander's named army when available, clears item-drop marks for a transfer to player/allied/other, and reloads the map model in the destination color. Control, target relationships, phase iteration, and map presentation then observe the new force.

## FE9-SYS-022 — Commander and group system

<span id="fe9-sys-022"></span>

  On top of its side, every unit carries an **army name**: one of 30 entries such as Crimean Army, Daein Army, Bandits, Pirates or Greil Mercenaries, listed in [FE8Data.bin](../formats/fe8data.md). A unit gets it from the [deployment group](../formats/dispo-format.md) that places it, and a script can change it. The side decides who fights whom; the army name groups units in the map's army list and scopes commander effects.

Each deployment group can mark a **commander** with flag `0x04`, reflected by the runtime unit-state bit `0x100`. Ike is normally the player commander and chapter bosses command enemy groups. A commander with Charisma gives units of its own named army within three tiles +5 Hit and +5 Avoid, except that this commander bonus is not applied on the player side. Transfer logic uses the first commander in the destination force as the source of the transferred unit's named army when one exists.

“First commander” means the first matching commander encountered in the destination force's linked-list traversal; multiple marked commanders therefore resolve deterministically by list order. Commander status is explicit state, not an elected office: removing a commander does not promote another unit automatically, and an empty/no-commander force supplies no inherited group. A script that needs a replacement must mark or deploy it deliberately.

This creates two nested identities. Force answers control and hostility: player, enemy, allied, or other. Named army and commander answer presentation and group-scoped effects. Two units can share a force but belong to different named armies; conversely, merely copying a named-army value does not move a unit to a different force or phase.

## Interactions, failure behavior, and evidence

The implementation trail crosses four independently decoded surfaces: deployment group headers select one of the 30 `GroupData` names; deployment records mark commanders; runtime unit slots store force, linked-list neighbors, group, and state; and `UnitTransferToForce` performs the relink and associated color/drop/group updates. `UnitGetNext` exposes same-force traversal, while saves preserve the eight-way force identity and links.

Invalid or partial edits fail by desynchronization rather than by a clean schema error. Changing the force byte without relinking the list can break iteration. Setting the commander bit without maintaining the group relationship can make effects disagree with the army list. Moving a unit during force traversal can reorder the list. A transfer to a force with no commander cannot inherit a commander group, so scripts that rely on that inheritance must establish the leader first.

## Interactions and review boundary

Both allegiance systems are reviewed without a blocking research gap. Force-list membership owns side, phase, hostility, and broad control; named army plus an explicit commander bit own grouping, display, transfer inheritance, and Charisma scope. The separate per-unit order-control tag is an input to partner command eligibility, not a third commander-selection system. Multiple, removed, or absent commanders follow deterministic list traversal and explicit script state. No new primary article is needed.
