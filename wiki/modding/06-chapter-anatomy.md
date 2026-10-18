---
id: "modding-chapter-anatomy"
title: "Understand a chapter's parts"
description: "Trace a chapter slot through its record, parts, script, messages, deployments, and map resources"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "campaign-foundations"
tutorial_stage: "draft"
prerequisites: ["modding-check-project"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Chapters", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/06-chapter-anatomy.md"
---
# Understand a chapter's parts

**Route:** Chapters → select chapter → Overview, Dialogue, Script, Deployment, Build

## What you will make

You will make a resource map for one retail chapter and one of its parts/phases. The map will connect the numeric chapter slot to its ChapterData record, message/script names, map folder, deployment variants, and callers.

## Before you begin

Use the clean practice project and choose an ordinary retail chapter. Record the chapter as both its displayed title and two-digit internal slot. Do not copy or rename files during this trace.

## How the editor fits together

The chapter list starts from ChapterData records in shared game data. A record associates a numeric slot with resource names: chapter script, message file, map folder, title key, and other header properties. The chapter workspace groups files reached through those names.

**Overview** exposes record identity and links. **Dialogue** edits message/scene material. **Script** owns event code and calls deployment sections, dialogue, flags, and functions. **Deployment** edits difficulty archives, named sections, and unit rows. **Build** works on map geometry, terrain, height, props, and settings. Part/phase selection changes which resource set is active; it is not merely a visual filter.

## Guided walkthrough

1. Select a chapter and open **Overview**. Record slot, title key/title, script name, message name, and map name exactly, including case.
2. In **Script**, identify the entry functions and one call that shows dialogue or loads a deployment section. Copy the called identity exactly.
3. In **Dialogue**, locate the called message/scene. Record whether the visible text is stored here or in a shared message resource.
4. In **Deployment**, select the same part/phase and each available difficulty. Find the called section, then record one unit's PID, JID, position, and inventory IID.
5. In **Build**, inspect the map dimensions and the tile at that coordinate. This connects the deployment's logical position to map data; visible scenery is a separate layer.
6. Change the part/phase selector and repeat the script/deployment/map-name comparison. Note which resources change and which remain shared.
7. Run **Tools → Check** and match its chapter-file rules to your resource map: script, message, `map.cmp`, `dispos.cmp`, and title.

## Understand every control

| Identity/control | Owns or selects | Failure if mismatched |
| --- | --- | --- |
| Chapter slot | ChapterData identity/story target | wrong record or route |
| Title key | lookup into message text | blank/incorrect displayed title |
| Script name | `Scripts/<name>.cmb` | missing-file error or load failure |
| Message name | `Mess/<name>.m` | missing text/dialogue resource |
| Map name | `zmap/<name>/` | missing map/deployment files |
| Part/phase | active subchapter resource context | edits or calls land in another part |
| Difficulty | deployment binary variant | behavior differs by mode |
| Section name | exact script-to-deployment link | intended units never load |

## Interactions and precedence

The numeric slot is not necessarily present in every filename. ChapterData names the resources; the script then names sections and messages. A deployment can override character/class information for the spawned unit. Map coordinates require compatible terrain/height, while props do not automatically define pathing. Shared messages or records can affect multiple chapters even when reached from one workspace.

Copying only the script, only the map folder, or only ChapterData does not create a complete chapter. A coherent copy requires the record and every named resource plus corrected internal callers.

## Test matrix

| Trace | Expected agreement |
| --- | --- |
| ChapterData → script | named `.cmb` exists |
| ChapterData → message | named `.m` exists |
| ChapterData → map | folder contains map and deployment archives |
| Script → deployment | exact section exists in intended variant |
| Deployment → shared data | every PID/JID/IID resolves |
| Deployment coordinate → map | coordinate is valid for intended placement |
| Part/difficulty switch | selected resource context is documented |

## Troubleshooting

If a tab appears empty, verify the selected part/phase and the resource name on Overview. If units are absent on only one difficulty, compare the correct `dispos_*.bin` variant. If Check reports a missing file, repair the ChapterData name or restore the expected file; inventing a second near-duplicate creates ambiguity. If a section exists but never appears, inspect its script caller and exact spelling.

## Save, build, and revert

This trace needs no edits. If you later change multiple chapter parts, save each owning editor and note its file. Run Check after every coordinated resource rename. Restore/copy resources as a set from a checkpoint rather than mixing a record from one revision with files from another.

## Limits and confidence

Chapter ownership, named-file checks, deployment variants, and workspace grouping are source-reviewed. The checker proves existence and supported references, not script execution order, coordinate safety, or visual correctness. Special chapters can use atypical routing and must be studied separately.

## Related tutorials and references

- [Work with chapter IDs and story order](07-chapter-ids-and-story-flow.md)
- [Edit deployment units and difficulty variants](30-deployment-by-difficulty.md)
- [Edit chapter scripts](33-script-editor.md)
- [Disc Layout](../meta/disc-layout.md)

---

[← Previous: Check a project and fix problems](05-check-project.md) · [All tutorials](index.md) · [Next: Work with chapter IDs and story order →](07-chapter-ids-and-story-flow.md)
