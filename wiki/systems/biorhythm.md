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
---
# Biorhythm

*A fully-functioning cyclical stat mechanic that computes correctly on every stat check and has never once changed a stat's value*

Path of Radiance computes a genuine, correctly-cycling Biorhythm value — the wave-shaped stat fluctuation more commonly associated with this game's sequel and earlier series entries — every single time it evaluates one of four core stats. It has never once changed the value of any of them in the retail game.

!!! info "Mental model: an active calculator connected to zero-valued inputs"
    The mechanic is not absent or skipped. Battles advance a phase, the phase selects a wave band, status effects can alter the band's strength, and stat getters consult the selected row. The final contribution is nevertheless zero because the getters read row positions whose value is zero in every band.

## How the cycle works

  Each unit carries its own phase counter, which increments by exactly 1 for *both* participants every time a battle is resolved — not once per turn. That counter is combined with a fixed per-unit cycle length of 30 and a small per-chapter offset (so units don't all start a chapter synced to the same point in the wave), fed through a real sine function, and bucketed into one of five bands along the wave: two "good" bands, a neutral middle band, and two "bad" bands. A unit's active status effects can double or halve the swing between bands.

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
