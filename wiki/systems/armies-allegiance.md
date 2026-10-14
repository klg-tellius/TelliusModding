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
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/armies-allegiance.md"
---
# Armies & Allegiance

*Which side a unit is on isn't a stored label — it's which of eight runtime lists that unit currently belongs to*

Every unit slot in the game belongs, at any moment, to exactly one of eight runtime lists. Which list a unit is in is not a side-effect of some other stored value — it *is* the unit's current allegiance. Moving a unit to a different army means physically relinking it into a different list, not flipping a byte read elsewhere.

## The four armies a player actually sees

<div class="table-wrap">
<table><thead><tr><th>List</th><th>Meaning</th></tr></thead><tbody>
    <tr><td>Player</td><td>The deployed, player-controlled roster</td></tr>
    <tr><td>Enemy</td><td>Ordinary hostile units</td></tr>
    <tr><td>Ally / orderable</td><td>Shown in a distinct color, and directly commandable through Ike's Order action rather than acting on its own initiative</td></tr>
    <tr><td>Other</td><td>A fourth army — neither player, enemy, nor orderable ally — used for green-flagged neutral or story-scripted units</td></tr>
  </tbody></table>
</div>

## Who plays each phase

  Each of the four armies has one byte in the party data saying who plays its phase: 0 no phase, 1 the player, 2 the computer. Chapter start writes 1 for the player army and 2 for the other three; no retail script changes them. Only the developer menu edits them (see [Developer & Debug Tools](./developer-debug-tools.md)). <span class="confidence confidence--confirmed">engine</span>

## Four more states that aren't "armies" at all

  Four further list ids exist purely as bookkeeping states rather than battlefield sides: a shared pool holding every currently-unused unit slot, the player's reserve/deployment-select pool before a chapter starts, an inactive/flagged state, and a further hidden/removed state. A unit sitting in one of these is not on the map as any army — it is waiting, benched, or cleared.

!!! info "Mental model: allegiance is where you're linked in, not what you're labeled"
    Asking "what army is this unit" is really asking "which list is this unit's node currently part of." Recruiting an enemy into the player's army, or benching a player unit to the reserve pool, is the same underlying operation either way: unlink from the old list, link into the new one.

## Comparing two units' allegiance

  Combat and AI reduce a pair of lists to one of three relation outcomes rather than comparing raw list identities for every decision: *same side* (identical list), *opposing* (either side is the enemy list), or *other* (any other differing pair, such as ally vs. green). This third case is what lets an orderable ally and a neutral green unit coexist without either automatically reading as the other's enemy.

## Example — recruiting a unit into the player's army

  A story event that recruits a unit performs one operation: move that unit's slot from its current list into the player list. Nothing about the unit's stats, inventory, or position changes — only which of the eight lists it's linked into, which is also what the map immediately uses to redraw its color and to decide who controls its turn.

## Named armies within a side

  On top of its side, every unit carries an **army name**: one of 30 entries such as Crimean Army, Daein Army, Bandits, Pirates or Greil Mercenaries, listed in [FE8Data.bin](../formats/fe8data.md). A unit gets it from the [deployment group](../formats/dispo-format.md) that places it, and a script can change it. The side decides who fights whom; the army name is what the map's army list groups units under. Each army can have a **commander**, the unit its deployment record marks as such (Ike on the player side, each chapter's boss on the enemy side). A commander with Charisma lifts nearby units of its own army. When a script moves a unit to another side, the unit also takes that side's army name.

  A closely related but distinct per-unit tag marks finer control nuances — precisely which ostensibly same-side units the player can actually issue orders to — and is not yet fully mapped.
