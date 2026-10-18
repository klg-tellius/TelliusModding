---
id: "modding-workspace-tour"
title: "Tour the workspace"
description: "Navigate records, trace references, and identify which editor owns each change"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "start-safely"
tutorial_stage: "draft"
prerequisites: ["modding-install-create-project"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/02-workspace-tour.md"
---
# Tour the workspace

**Route:** Workspace sidebar; Search (`Ctrl+K`); breadcrumb and navigation history

## What you will make

You will create a written ownership trace for one real unit: character record → class record → referring deployment → chapter resources. You will also return to each surface using search, breadcrumbs, and Back without changing data.

## Before you begin

Use the clean extracted practice project from lesson 01. Do not edit values during this tour. Choose a recognizable retail character and write down its PID and JID; internal IDs are the stable links, while displayed names come from text keys and may be shared.

## How the editor fits together

**Home** reports project identity and exposes disc work. **Chapters** groups chapter-local script, dialogue, deployment, and map/build resources. **Characters** opens shared character records. **Game Data** contains shared classes, items, skills, terrain, armies, supports, and related tables. **Assets** exposes presentation resources. **Tools** contains validation and specialized workflows.

A breadcrumb describes the current ownership path. Back/Forward (`Alt+Left`/`Alt+Right`) traverses visit history, not data history. Search (`Ctrl+K`) resolves known names and internal IDs to destinations; it does not replace reference analysis. The session change log/status area reports actions from the current session and is not a permanent audit trail.

## Guided walkthrough

1. Open **Characters** and select a retail unit. Record its displayed name, PID, linked JID, and any visible portrait/model identifiers.
2. Select or search the JID to open **Game Data → Classes**. Compare the class identity, movement type, weapon access, and model-related fields with the character record. This establishes that character and class contribute different layers.
3. Press `Ctrl+K`, search the PID, and inspect the destinations. Open a chapter deployment that uses it. Record chapter, part/phase, difficulty file, section, and row.
4. Use the chapter breadcrumb to return to the chapter, then visit **Script**, **Dialogue**, **Deployment**, and **Build**. Note that these tabs edit different files even though they share a chapter context.
5. Press `Alt+Left` until you return to the character, then `Alt+Right` to revisit the deployment. Confirm navigation changes location only.
6. Search an IID from that deployment's inventory, open its shared item record, and return. You have now traced chapter-local use to shared data twice.
7. Check the status/change-log area. With no writes performed, there should be no saved change to use as evidence.

## Understand every control

| Surface/control | What it answers | What it does not prove |
| --- | --- | --- |
| Sidebar | broad owner/category | which caller uses a record |
| Breadcrumb | current hierarchy and parent route | edit history |
| Back/Forward | prior/next visited route | undo/redo |
| `Ctrl+K` search | direct navigation by indexed label or ID | runtime reachability |
| Record list | records owned by the current table | references hidden in scripts |
| Chapter tabs | resources grouped under one chapter | that all names/files agree |
| Status/change log | actions reported this app session | durable version history |

## Interactions and precedence

Shared records affect every caller: changing one class can alter many characters and deployments. Chapter-local resources affect one chapter or part, but their callers use exact strings. Character overrides can take precedence over class defaults in model resolution; deployment rows can override character/class values for the spawned unit. Search finds identities, while **Tools → Check** finds supported broken references.

## Test matrix

| Navigation test | Expected result |
| --- | --- |
| PID search | opens the intended character or relevant destination |
| JID search | opens the linked class, not a similarly named label |
| IID search | opens the shared item record |
| Deployment trace | records chapter, variant, section, and unit row |
| Back then Forward | restores visited routes without changing data |
| Reopen project | no edits were introduced by navigation |

## Troubleshooting

If a display name yields several results, search the exact `PID_`, `JID_`, `IID_`, or `SID_`. If a link seems wrong, compare the stored ID rather than the localized label. If a page is missing, confirm extraction completed and that the game profile supports it. If Back does not undo an edit, that is expected: navigation history is not edit history.

## Save, build, and revert

This lesson intentionally makes no writes. If a field changed accidentally, leave the editor without saving or restore the practice project from its clean checkpoint. Do not build solely to verify navigation; reopen the affected record and compare it with the checkpoint.

## Limits and confidence

Routes, navigation keys, sidebar ownership, and session-history behavior are source-reviewed. Search coverage is index-dependent and cannot guarantee that opaque script data contains no reference. Runtime precedence must be confirmed in the specialized tutorial for that system.

## Related tutorials and references

- [Install the app and create a project](01-install-create-project.md)
- [Save changes and restore originals](03-saving-and-restoring.md)
- [Check a project and fix problems](05-check-project.md)

---

[← Previous: Install the app and create a project](01-install-create-project.md) · [All tutorials](index.md) · [Next: Save changes and restore originals →](03-saving-and-restoring.md)
