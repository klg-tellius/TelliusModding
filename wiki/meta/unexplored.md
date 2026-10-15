---
id: "unexplored"
title: "Open Questions"
description: "Known limits in the current description of formats and mechanics"
games: ["path-of-radiance"]
section: "meta"
article_type: "portal"
tags: ["Portal","Open questions"]
aliases: ["tellius_archive.html#/unexplored"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "meta"
source_path: "meta/unexplored.md"
---
# Open Questions

*Known limits in the current description of formats and mechanics*

This page records the boundaries of the current game description. An open item means the archive can identify the containing format or subsystem but cannot yet assign a reliable meaning to the listed fields or behavior.

## What an open question means

  These entries are boundaries, not invitations to guess. A reader can rely on the documented container, location, and observed structure, but should avoid assigning gameplay meaning beyond the stated confidence. Follow the linked article for the established surrounding model.

## Payloads not decoded field-by-field

- `zbg/`'s 3D battle scenery: each `map.bin` holds `mapcapacityB`, `mapbuilddescB`, `mapbuildinstB`, `maplightB`, `mapfogB` and `mapextraB` (no panel or link layers), read by the same code and in the same layouts as a chapter map's sections (see [Map File Format](../formats/map-format.md)), so they share the chapter maps' few open flag bits (where its models stand is in [Battle Staging & Camera](../systems/battle-staging.md)).
- Whether the battle tool's button `current` has a visible effect, whether two unused-looking `ztool/` layouts can be loaded dynamically, and the visual meaning of the lens flare's EFB threshold. Their DBX blocks, fields, and main dialog callbacks are catalogued in [ZDBX & DBX](../formats/zdbx.md).

## Partially described formats

- `tut_data.bin` / `tut_data_en.bin` — the same labeled-section container; per-chapter trigger data and the [tutorial browser](../systems/tutorial-browser.md) topic/list ownership are identified, but several record fields still need names.

## The GBA link program

  `client.bin` is a Game Boy Advance program: it opens with a GBA cartridge header (ARM branch, Nintendo logo, title `FIREEMBLEM6`, code `AFEJ01`) followed by about 18 KB of GBA code. The title menu's **Connect GBA** sends it to a Game Boy Advance plugged into a controller port; it reports which cartridge is inserted, and a *Fire Emblem* or *Fire Emblem: The Sacred Stones* cartridge unlocks bonus content and is remembered in the system data (see [Save format](../formats/save-format.md)). <span class="confidence confidence--confirmed">engine</span> The GBA code itself has not been disassembled, and how the transfer to the GBA runs is not traced. <span class="confidence confidence--open">open</span>

## Open mechanical questions

<div class="table-wrap">
<table><thead><tr><th>Question</th><th>Status</th><th>Article</th></tr></thead><tbody>
    <tr><td>What are the actual support-bonus numbers?</td><td><span class="badge open">open</span></td><td><a class="wl" href="../../systems/support-system/">Support System</a></td></tr>
    <tr><td>Exactly what script code reads a battle-goal marker's state?</td><td><span class="badge open">open</span></td><td><a class="wl" href="../../systems/objectives/">Objectives</a></td></tr>
    <tr><td>What does the Boots' item property <code>noneart</code> change in play?</td><td><span class="badge open">open</span></td><td><a class="wl" href="../../systems/items-weapons/">Items &amp; Weapons</a></td></tr>
    <tr><td>Which battle-event code triggers the hit and damage number, and what do the codes from 1,000 up play?</td><td><span class="badge plausible">partial</span></td><td><a class="wl" href="../../formats/model-formats/">.g / .gs / .ga</a></td></tr>
    <tr><td>What is the second, greyscale texture the Prologue scenery's materials point to, and what do shape flags <code>0x8</code> and <code>0x200</code> do?</td><td><span class="badge open">open</span></td><td><a class="wl" href="../../formats/model-formats/">.g / .gs / .ga</a></td></tr>
    <tr><td>What do map-model registry bytes <code>0x09</code> and <code>0x0B</code> mean, and which class field supplies the animation ID of a unit whose character has none?</td><td><span class="badge open">open</span></td><td><a class="wl" href="../../formats/fe8anim/">FE8Anim.bin</a></td></tr>
  </tbody></table>
</div>

## Radiant Dawn

  Radiant Dawn, the Wii sequel, runs on the same engine but changes many layouts. Its text, portraits, fonts, conversation lists and event scripts are described on [Radiant Dawn](./radiant-dawn.md); the rest of the archive still describes Path of Radiance only. For Radiant Dawn, open items include its European single-byte text tables, the composition of its dialogue window art, and every system not yet listed on that page.
