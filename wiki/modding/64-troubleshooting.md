---
id: "modding-troubleshooting"
title: "Troubleshoot crashes, missing data, and bad builds"
description: "A symptom-led method for isolating Tellius mod failures without destroying evidence"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "test-and-release"
tutorial_stage: "draft"
prerequisites: ["modding-known-limits", "modding-check-project", "modding-dolphin-setup"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Troubleshooting", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/64-troubleshooting.md"
---
# Troubleshoot crashes, missing data, and bad builds

**Route:** Tools → Check; Home → Disc & Patch; the editor that owns the failing resource

## What you will make

You will make a reproducible failure report, isolate its smallest responsible edit, repair the owning resource, and prove the repair with both a negative and positive check. The method applies to extraction, validation, build, boot, chapter-load, and runtime failures.

## Before you begin

Preserve the failing project. Do not re-extract, restore originals, delete records, or overwrite the only failing build yet: those actions erase evidence. Copy the project folder or create a version-control checkpoint, note the exact build name and save file, and retain a known-good checkpoint if one exists.

Record five facts: last known-good revision; first bad revision; exact action before failure; exact screen, turn, or phase where it occurs; and whether a fresh save reproduces it. Capture an assertion or log line verbatim, but treat its path or identifier as a clue rather than proof of the cause.

## How the editor fits together

A failure crosses ownership boundaries. `FE8Data.bin` owns shared characters, classes, items, skills, and ChapterData links. Chapter scripts call dialogue, deployment sections, flags, and functions by exact identity. Map folders own `map.cmp` and `dispos.cmp`. Models and battle tables own presentation. The build step packs the current extracted tree; Dolphin then loads that built image plus persistent save state.

Therefore a visible symptom is often downstream. A missing PID shown in a deployment is repaired in the deployment if the reference is wrong, or in the character table if the record was accidentally removed. Creating a duplicate PID merely hides the broken ownership decision.

## Guided walkthrough

1. Reproduce once from a written starting state. Record project revision, output image, save, chapter, difficulty, phase, and inputs. If it cannot be repeated, compare the state that changed instead of editing blindly.
2. Open **Tools → Check → Run check**. Save the error/warning counts and first relevant row. Double-click a navigable row. Errors are structural hazards; warnings require judgment and may describe unreachable retail data or conservative script-string matches.
3. Compare against a clean extracted project or last known-good checkpoint. If the clean project fails identically, the problem may be setup, unsupported input, or a baseline warning rather than the recent edit.
4. Bisect the edit set. Revert half the suspect changes in a disposable copy, save, rebuild, and repeat the same reproduction. Keep narrowing the half that retains the failure until one resource or coupled group remains.
5. Inspect the owner and its callers together. For a chapter-load crash, compare ChapterData names with `Scripts/<name>.cmb`, `Mess/<name>.m`, and `zmap/<map>/map.cmp` plus `dispos.cmp`. For a missing unit, compare the script's section string, exact deployment section, difficulty file, and every PID/JID.
6. Make one repair. Save the owning editor, rerun **Check**, build under a new output identity, and launch with the controlled save state.
7. Prove causality: the repaired copy must pass, while a disposable copy with the suspect condition restored must fail in the same way.

## Understand every choice

| Symptom boundary | First comparison | High-value owners |
| --- | --- | --- |
| Only Home and Disc & Patch appear | extraction completion and game selection | source image, extracted folder, project metadata |
| Check names a missing ID | row's file/area and record search | deployment, shop, support, script, FE8Data table |
| Crash before a chapter appears | ChapterData resource names versus files | script, message, map and deployment archives |
| Crash when a section loads | section spelling and difficulty variant | script caller and `dispos_*.bin` section |
| Invisible battle unit or weapon | map visibility versus battle visibility | battle-weapon table, model and texture resolution |
| Event never fires | condition, phase/turn, and guard state | script and chapter/campaign flags |
| Event repeats | whether guard is tested and set after success | script control flow and persistent flag |
| Build boots with old content | editor save, build timestamp, output selected | owning file, `system.cmp` synchronization, output image |
| Dolphin differs from a new game | fresh save versus existing save | recruited units, flags, clear history, cached progression |
| Model distorts after import | pristine export versus imported set | scale, weights, anchor bones, alpha/material modes |

## Interactions and precedence

The newest edit does not automatically win. A field not committed before Save can leave the old value. Unsaved shared-data changes are absent from `FE8Data.bin`; an older built image is unaffected by later saves. Build synchronization can copy messages, fonts, or shared data into `system.cmp`, so inspecting only the loose source is incomplete. Finally, save data can override the apparent starting state of units and events.

When several errors share one missing ID, repair the deleted or renamed owner first and rerun the checker; dependent rows may disappear. Do not change every caller before learning whether the shared record should exist.

## Test matrix

| Test | Expected evidence |
| --- | --- |
| Known-good project + controlled save | symptom absent |
| Failing project + same save/action | symptom repeats |
| Failing project + fresh save | distinguishes persistent-state effects |
| One repaired owner + Run check | relevant issue removed without new errors |
| Rebuilt image with unique name/time | repaired behavior present |
| Suspect condition restored in disposable copy | original symptom returns |

## Troubleshooting

If **Run check** itself fails, preserve its message and verify that extraction contains the expected game-data file. If the checker is clean but runtime fails, prioritize semantics it cannot prove: correct section called at the correct time, valid coordinates, event convergence, model compatibility, and save-state effects. If a build exceeds the original disc capacity, remove or replace large movies, streams, or textures; a warning is not evidence that hardware will accept the image.

For a distorted model, restore the original in a copy, export the exact resource set again, and change one import variable at a time. Preview success does not prove rigged animation or in-game rendering.

## Save, build, and revert

Keep the failing artifact, diagnostic notes, and fixed artifact under different names. Save the owning editor, rerun **Check**, then build. Reverting should restore the smallest known-good resource or checkpoint, not re-extract the entire project. Re-extraction overwrites the extracted working files from the source disc.

## Limits and confidence

The symptom-to-owner method, checker categories, build boundaries, and extraction behavior are source-reviewed. The checker cannot execute game logic, prove visual assets render on every path, or certify oversized images for hardware. Some edited CMB scripts may not round-trip all constructs. Runtime conclusions remain **unknown** until repeated in Dolphin, and hardware claims require hardware testing.

## Related tutorials and references

- [Check a project and fix problems](05-check-project.md)
- [Set up Dolphin and build the game](04-dolphin-setup.md)
- [Know the current limits](63-known-limits.md)
- [Crash Assertions Diagnostics](../systems/crash-assertions-diagnostics.md)
- [Disc Layout](../meta/disc-layout.md)

---

[← Previous: Know the current limits](63-known-limits.md) · [All tutorials](index.md)
