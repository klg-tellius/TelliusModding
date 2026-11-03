---
id: "biorhythm"
title: "Biorhythm"
description: "A fully-functioning cyclical stat mechanic that computes correctly on every stat check and has never once changed a stat's value"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Balance"]
aliases: ["tellius_archive.html#/biorhythm"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/biorhythm.md"
system_entries: ["FE9-SYS-126", "FE9-SYS-187"]
system_reviewed: ["FE9-SYS-126", "FE9-SYS-187"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-13"
system_known_gaps: []
system_gap_work: []
---
# Biorhythm

*A fully-functioning cyclical stat mechanic that computes correctly on every stat check and has never once changed a stat's value*

Path of Radiance computes a genuine, correctly-cycling Biorhythm value — the wave-shaped stat fluctuation more commonly associated with this game's sequel and earlier series entries — every single time it evaluates one of four core stats. It has never once changed the value of any of them in the retail game.

## Biorhythm combat modifier

<span id="fe9-sys-126"></span> The reviewed conclusion is deliberately narrower than the familiar series description: Path of Radiance owns and advances a per-unit rhythm cycle, but the confirmed retail stat consumers receive zero from it. Documentation and tools must preserve that distinction. Showing the phase or editing the counter is valid; claiming a live Hit/Avoid bonus in this game is not supported by the executable path.

!!! info "Mental model: an active calculator connected to zero-valued inputs"
    The mechanic is not absent or skipped. Battles advance a phase, the phase selects a wave band, status effects can alter the band's strength, and stat getters consult the selected row. The final contribution is nevertheless zero because the getters read row positions whose value is zero in every band.

## How the cycle works

  Each unit carries its own phase counter, which increments by exactly 1 for *both* participants every time a battle is resolved — not once per turn. That counter is combined with a fixed per-unit cycle length of 30 and a small per-chapter offset (so units don't all start a chapter synced to the same point in the wave), fed through a real sine function, and bucketed into one of five bands along the wave: two "good" bands, a neutral middle band, and two "bad" bands. A unit's active status effects can double or halve the swing between bands.

## Biorhythm progression

<span id="fe9-sys-187"></span> Progression is the live part of the mechanic even though its retail stat output is zero. Construction supplies the pattern and phase seed, saved unit state owns the mutable battle counter, each resolved battle advances both participants by one, and the next query combines that counter with the fixed 30-step cycle and chapter offset. The sine result selects one of five bands; status can scale the selected row before a consumer reads it. Save/load preserves the counter, so reloading does not restart every character at the beginning of the wave.

For example, two characters who begin a chapter with different offsets can enter different bands after the same number of combats. A battle involving both advances both counters, including the defender's, while an uninvolved unit does not advance through this confirmed path. The selected phase is meaningful for display, debugging, and any modded consumer even though the retail Strength, Magic, Defense, and Resistance getters read only zero-valued columns.

## What each band actually contains

  Each band returns a fixed row of five values. Across every real band, the row is:

<div class="table-wrap">
<table><thead><tr><th>Band</th><th>Row</th></tr></thead><tbody>
    <tr><td>Good (×2)</td><td><code>0, 0, +5, +5, 0</code></td></tr>
    <tr><td>Good</td><td><code>0, 0, +5, +5, 0</code></td></tr>
    <tr><td>Neutral</td><td><code>0, 0, 0, 0, 0</code></td></tr>
    <tr><td>Bad</td><td><code>0, 0, -5, -5, 0</code></td></tr>
    <tr><td>Bad (×2)</td><td><code>0, 0, -5, -5, 0</code></td></tr>
  </tbody></table>
</div>

  Strength and Magic both read the row's first position; Defense and Resistance both read the row's second position. Skill and Speed never consult Biorhythm's table at all. The two positions that ever actually swing — the third and fourth — sit unread by every one of the four stats that do check Biorhythm.

!!! note "Live, but silent"
    The phase genuinely advances, the sine wave genuinely runs, the correct band genuinely gets selected and its whole five-value row genuinely gets copied out with any status-effect doubling/halving correctly applied to all five values — and then the one value each stat actually reads out of that row is always exactly zero, in every band, every time. <span class="confidence confidence--confirmed">confirmed</span>

## Worked example

  Suppose a unit reaches a “Good” band. The selected row is `0, 0, +5, +5, 0`. Strength and Magic both request position 0, receiving 0; Defense and Resistance request position 1, also receiving 0. The visible +5 entries are real data but are not read by those four stat calculations, while Skill and Speed do not query this table. The unit's displayed combat values therefore remain unchanged.

## What remains separate

  This page describes the runtime stat path. It does not establish whether unused row positions were intended for Hit, Avoid, or another abandoned consumer, and it should not be used to infer Radiant Dawn's implemented biorhythm behavior.

## Inputs, lifecycle, outputs, and limits

Inputs are the unit's saved battle counter, its character-derived pattern/phase data, current chapter number, and the status-driven amplitude adjustment. A zero pattern is replaced by a randomized pattern at construction, while a zero phase seed becomes 30; every vanilla character record uses phase 30. Combat resolution advances the mutable counter for both participants, so the next stat query can land in a different band. Saves preserve the counter and therefore preserve cycle position across reload.

The calculator converts the counter and chapter offset into a sine phase, buckets it into one of five bands, and copies the corresponding five-value row with the amplitude modifier. Strength/Magic request row position 0 and Defense/Resistance position 1; Skill and Speed never call this table. Since positions 0 and 1 are zero in every band, the observable contribution to those stats is always zero. The nonzero third and fourth positions are computed and copied but have no confirmed retail consumer.

This is not a research gap that blocks FE9-SYS-126: the ownership, update boundary, formula shape, table contents, consumer indices, live-memory counter change, and final zero result are established. What the unused positions were once intended to mean is historical intent, not missing behavior in the shipped system. A mod can deliberately connect them to Hit/Avoid or other stats, but that would be a new mechanic and should be documented as such rather than presented as restoration of proven retail behavior.
