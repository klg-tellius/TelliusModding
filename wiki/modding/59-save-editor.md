---
id: "modding-save-editor"
title: "Edit and test a save"
description: "A deep save workflow covering GCI copies, block selection, sequence freshness, party and unit records, flags, inventories, checksums, Save as, temporary Dolphin cards, chapter jumps, testing, and rollback"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Saves", "GCI", "Testing"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/59-save-editor.md"
tutorial_kind: "task"
tutorial_track: "test-and-release"
tutorial_stage: "draft"
prerequisites: ["modding-play-chapter", "modding-event-flags"]
verification: ["source-reviewed", "unknown"]
---
# Edit and test a save

**Route:** Tools → Saves

!!! warning "Edited-save launch needs final game verification"
    Parsing/writing is source-reviewed, but edited saves and save-based Dolphin launch remain curriculum-level unknown.

## What you will make

You will open a copied `.gci`, identify the live file-save block, change one visible unit field and one flag, write a separate output with repaired checksums, reopen it, and test ordinary load versus an optional chapter-start jump without risking the original memory card.

## Before you begin

Copy the `.gci` outside the project and record game region, disc/project revision, file slot, displayed chapter/play time, roster, gold, and the exact change. Table identities must match the build that will load the save; removed/reordered character/class/item records can reinterpret numeric references.

## How the editor fits together

A card file can contain several save blocks, checkpoints, or consumed/older copies. Sequence/freshness metadata identifies the newest usable copy. The editor exposes block header, party, faction commands, options, map state, cleared history, roster units, stats, growth points, weapon EXP, item instances, supports, skills, flags, and advanced links; undecoded fields remain numeric.

**Save as…** rebuilds a distinct GCI and checksums. **Play in Dolphin…** creates/uses a temporary card and can load the saved state or alter a copied state for a chapter-start jump. A jump bypasses normal campaign initialization and is diagnostic, not progression proof.

## Guided walkthrough

Open the copy and select the block whose sequence, chapter, roster, and play time match the intended file. Inspect before editing. Choose a unit and change one bounded field such as current HP, inventory uses, or gold/flag through the decoded owner. Preserve equipped/drop/forge bits and linked instance identity when editing items.

Change one registered flag whose project meaning is known. Do not guess raw flag numbers from another revision. Use **Save as…** to create a new filename, close it, reopen that output, reselect the block, and verify both edits plus all untouched baseline fields.

Load the output normally in Dolphin using a disposable card. Confirm the game lists the correct slot and loads it without corruption. Exercise the changed field, save again in game, restart, and reload. Separately test a chapter jump only if needed; record it as a different experiment and verify that normal story progression independently reaches a coherent state.

## Understand every control

- **Open/block list:** selects among physical/logical copies; title/play time alone may not prove freshness.
- **Party/map/unit tabs:** decoded owners of persistent state.
- **Items:** exact instances with uses and packed equipped/drop/forge-link bits.
- **Flags:** registered campaign/chapter state; scope still follows project tables.
- **Raw/advanced fields:** visible for evidence, not automatically safe to mutate.
- **Save as…:** permanent separate output and checksum rebuild.
- **Play in Dolphin…:** temporary-card test; as-saved or copied chapter jump.

## Interactions and precedence

The save stores numeric table positions and named/registered state expected by its executable/data revision. A valid checksum cannot make incompatible tables safe. Chapter-start jumps construct/bypass state differently from ordinary transitions. In-game saving becomes a second writer and is the strongest persistence check.

## Test matrix

| Case | Expected evidence |
| --- | --- |
| reopen output | edits and checksum parse; baseline fields unchanged |
| wrong/older block | deliberately rejected before editing |
| normal Dolphin load | correct slot, chapter, roster and values |
| use changed item/unit | behavior matches instance/field |
| in-game save/reload | edit survives a native write cycle |
| flag false/true | intended event branch only |
| chapter jump | target opens, explicitly not progression evidence |
| original GCI | remains byte-for-byte outside output path |

## Troubleshooting

**Dolphin shows old data.** Check selected block, output card path, Dolphin card configuration, and whether a newer block supersedes it.

**Items/units resolve incorrectly.** The save and project tables are incompatible; restore matching data rather than repairing symptoms.

**Jump works but normal transition fails.** Diagnose campaign routing/initialization; the jump bypassed it.

## Save, build, and revert

Always use **Save as…** and a temporary Dolphin card. Keep the untouched GCI read-only. Revert by discarding the output/temporary card and returning to the copy; never overwrite the only real card while verification is unknown.

## Limits and confidence

Block parsing, decoded fields, output/checksum construction, and temporary launch preparation are source-reviewed. Unknown raw fields, cross-revision compatibility, native load, and chapter-jump behavior require Dolphin confirmation.

## Related tutorials and references

- [Play and rewind a chapter in the app](58-play-chapter.md)
- [Save format](../formats/save-format.md)
- [Save System](../systems/save-system.md)

---

[← Previous: Play and rewind a chapter in the app](58-play-chapter.md) · [All tutorials](index.md) · [Next: Use the game's debug menus →](60-debug-menus.md)
