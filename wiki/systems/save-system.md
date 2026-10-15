---
id: "save-system"
title: "Save, Load & Resume System"
description: "How Path of Radiance turns runtime state into Memory Card blocks and reconstructs the correct scene"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Saves", "Engine", "Compatibility"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source", "path-of-radiance-us-manual"]
cms_collection: "systems"
source_path: "systems/save-system.md"
system_entries: ["FE9-SYS-349", "FE9-SYS-350", "FE9-SYS-351", "FE9-SYS-352", "FE9-SYS-353", "FE9-SYS-354", "FE9-SYS-355", "FE9-SYS-356", "FE9-SYS-357", "FE9-SYS-358", "FE9-SYS-359"]
system_reviewed: ["FE9-SYS-349", "FE9-SYS-350", "FE9-SYS-351", "FE9-SYS-352", "FE9-SYS-353", "FE9-SYS-354", "FE9-SYS-355", "FE9-SYS-356", "FE9-SYS-357", "FE9-SYS-358", "FE9-SYS-359"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Save, Load & Resume System

The [save format](../formats/save-format.md) explains bytes; this page explains behavior. A save is a reconstruction recipe: it records the persistent parts of the current playthrough plus a **resume point** telling the campaign controller which scene should rebuild them. It does not freeze every object in memory, and it does not copy immutable character/item definitions.

## Card and block ownership

<span id="fe9-sys-349"></span> **FE9-SYS-349 — Memory Card file management.** The US game uses one 19-block GameCube Memory Card file. Updates are copy-on-write at the internal block level: a new save takes a free block and receives a sequence number one greater than the highest valid block already present. Boot validation selects the newest valid copy, so an interrupted write leaves the previous block available. Card presence, free-space/format checks, directory metadata, banner/icon data, and platform errors wrap this block transaction rather than changing its ordering rule.

<span id="fe9-sys-350"></span> **FE9-SYS-350 — Save-block system.** Six shared 0x4000-byte file blocks serve five visible slots, and two 0x6000-byte blocks hold checkpoints. Header byte `+0x62` assigns a normal block to visible slot 0–4; checkpoint byte `+0x63` records its owner slot. Save kind 2 is a file save, kind 3 a checkpoint, and kind 1 a consumed copy that validation discards. For each visible slot the loader keeps the highest-sequence valid normal block, keeps only the newest valid checkpoint globally, and frees superseded blocks. Header summaries expose chapter, difficulty, time, and other selection facts without reconstructing the state stream.

<span id="fe9-sys-354"></span> **FE9-SYS-354 — System-data replication.** Every save block carries a 0x48-byte `SYSF` snapshot at `+0x70`: magic, version `0x20050201`, 64-bit system id, unlock bits, thirty completed-playthrough ids, the 128-bit met-character mask, screen calibration, console byte, and last-used file slot. After CRC/kind filtering, boot takes `SYSF` from the newest remaining block that carries it; if none exists it creates fresh system data. Equal sequence cannot produce two winners in normal output because writers allocate monotonically, while corrupt/missing candidates have already been removed by validation.

## Rules and lifecycle — writing and reading runtime state

<span id="fe9-sys-351"></span> **FE9-SYS-351 — Save serialization.** The state stream writes tagged chunks in a fixed order: party/chapter state (`BMST`), map display (`MDST`), variable-size unit slots (`UNIP`), convoy (`SOKO`), forge records (`FWEP`), and persistent tile objects (`T  T`). Definitions such as Iron Sword might are not copied; an item instance stores its table number, uses, equip/drop flags, and forge reference.

<span id="fe9-sys-352"></span> **FE9-SYS-352 — Load reconstruction.** Loading first removes bad-CRC and consumed blocks, selects one winning block, verifies its system identity/version and ordered stream tags, then reads the resume point. It loads the appropriate common/chapter resources and reconstructs party, units, inventories, flags, AI progress, map objects, weather/fog/camera, and scene state. Character/class/item numbers resolve through the current core database; absent or structurally inconsistent required data rejects that candidate rather than inventing definitions. Presentation-only actors are recreated by the destination scene instead of deserialized byte-for-byte.

<span id="fe9-sys-353"></span> **FE9-SYS-353 — Save integrity and versioning.** Header `+0x50` is standard CRC-32 over bytes `+0x70` through the end of the block. A mismatch makes the block empty; save kind 1 is discarded, while sentinel checksum `0x12345678` is the explicit unchecked construction case. The `SYSF` magic, version `0x20050201`, 64-bit system id, save kind, slot range, resume point, and fixed stream-tag order provide the remaining structural gates. Because chunks lack general lengths, a bad fixed size or variable-unit count shifts later tags and fails structural reading rather than being silently realigned.

## Save types and resume points

<span id="fe9-sys-355"></span> **FE9-SYS-355 — Autosave/chapter-clear save.** A post-victory block intentionally straddles two moments: it writes the next chapter identity while retaining the map identity just cleared, then routes through the appropriate chapter-start resume point. Resume points 3/4 represent new-game/chapter-start initialization and 10 the trial route; unlike live-map resumes they discard stale chapter-local flags before entering the new chapter. This ordering prevents the clear map from reopening or its one-shot flags leaking forward.

<span id="fe9-sys-356"></span> **FE9-SYS-356 — Map/checkpoint save.** Tagged chunks `BMST`, `MDST`, `UNIP`, `SOKO`, `FWEP`, and the tile-state stream preserve battle/map state, units, convoy, forge data, and changed objects. The reconstructed state includes turn and active army; cursor/camera display; unit position, HP, status, inventory, and acted state; flags and AI interpreter progress; and doors, chests, wall HP, or ballista uses. Active processes and camera interpolation are not serialized: resume point 8 rebuilds presenters around the restored data without replaying one-time map initialization.

<span id="fe9-sys-357"></span> **FE9-SYS-357 — Base/preparation save.** Resume points 1 and 2 route to base and preparations. Party/options, roster units, inventory/convoy, forge pool, funds/resources, support/progression state, and deployment selection/surplus persist, while transient menu processes are rebuilt. The base-opening event uses the dedicated `party+0x55` completion byte to avoid replay; unit serialization also masks runtime faction presentation so reconstruction applies the destination context correctly.

<span id="fe9-sys-358"></span> **FE9-SYS-358 — Suspend save.** Suspend writes save kind 3 with resume point 8 into one of the two checkpoint blocks and records the owning visible slot at header `+0x63`. Boot retains only the newest valid checkpoint. Resume reconstructs the tactical continuation, then consumption changes the old copy to kind 1; only its initial 0x2000 bytes need be rewritten, CRC validation is skipped for that consumed form, and future scans discard/free it. Copying ordinary file slots therefore does not duplicate a live checkpoint accidentally.

## Compatibility and modding

<span id="fe9-sys-359"></span> **FE9-SYS-359 — Save compatibility.** Several references are table positions: character, class, and item numbers count from the core database. Reordering those tables can turn a valid old value into a different definition. Expanding unit records, changing chunk sizes, exceeding fixed convoy/forge/tile capacities, or changing assumptions about flags can misalign or truncate the stream.

A safer content mod preserves table order and serialized sizes, appends within confirmed engine capacity, and tests four routes: New Game, base/preparation save, live-map/suspend save, and chapter-clear transition. When compatibility cannot be preserved, the release must say which old saves are unsafe and why.

## Worked example

Suppose a unit carries a forged sword while standing beside an opened chest in fog. The save stores the unit's character/class indices, mutable stats, tile, status, skills, item instance, and forge-pool reference; the forge record stores its name/stat steps/trail color; the tile table stores that the chest is open; map state stores fog/camera. On load, current database definitions supply the base sword/class/character, saved overlays restore progression and forge changes, and the map scene rebuilds visuals from the reconstructed state.

## Review boundary

All save systems on this page are closed at executable and format level. Copy-on-write sequencing, allocation, CRC/structural rejection, reconstruction ownership, replicated system data, chapter-clear identity ordering, live-map chunks, base/preparation routes, and Suspend consumption/reuse are explicit. Byte-level field tables remain on the linked format/research pages; no new primary article is required.

