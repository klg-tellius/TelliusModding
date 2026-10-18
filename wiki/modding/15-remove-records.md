---
id: "modding-remove-records"
title: "Remove records without corrupting saves"
description: "Audit every supported reference, replace callers intentionally, and handle table-number save incompatibility"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "characters-and-game-data"
tutorial_stage: "draft"
prerequisites: ["modding-recruitment-and-bosses", "modding-check-project"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Records", "Save compatibility", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/15-remove-records.md"
---
# Remove records without corrupting saves

**Route:** Character or Game Data record → Remove

## What you will make

You will produce a reference audit for one disposable appended record, replace or remove every intentional caller, delete the record, and verify the project from a fresh save. You will also make an explicit release decision about older-save compatibility.

## Before you begin

Back up the complete project and save all open editors so the scan reads current files. Choose a mod-added record, preferably the last table entry created for practice. Never learn deletion on a retail record or a record named by `main.dol`. Decide whether supporting saves created before this change is mandatory.

## How the editor fits together

Records refer to each other by PID/JID/IID/SID strings, and external files can contain the same identities. **Remove** scans pointer fields in FE8Data, support/bond/skill lists, scripts, compressed deployments, shops, battle-model data, map-model registry, and `main.dol` string literals. If a supported reference remains, deletion is blocked and the dialog lists owners.

Characters, classes, and items are also stored in saves by 1-based table position. Removing a non-final entry shifts every later record number. No string-reference scan can repair an old save that now maps those numbers to different records.

## Guided walkthrough

1. Record candidate kind, ID, table index, whether it is last, and all intended consumers. Save and run Check for a baseline.
2. Select **Remove** without confirming anything destructive. If blocked, copy every displayed reference; the dialog shows up to 14 and reports additional count.
3. Classify each owner. Repoint an erroneous caller to the exact intended replacement; delete a caller only when its behavior is no longer wanted. Audit FE8Data links, supports/bonds, deployments, scripts, shops, battle tables, map models, and any executable literal.
4. Save every owner, rerun Check, and retry **Remove**. Repeat until the scan returns no supported references.
5. Read the confirmation. If later records will move, record the count. For character/class/item removal, declare pre-change saves incompatible unless the record is final and your compatibility analysis proves no numeric shift or other state dependency.
6. Confirm deletion. The shared FE8Data session is now dirty; select **Save FE8Data.bin**.
7. Close/reopen, search the removed ID, rerun Check, inspect the records immediately before/after its old position, build, and start a new game.

## Understand every choice

| Scan/choice | Coverage or consequence |
| --- | --- |
| FE8Data pointers | record fields, support lists, bonds, skill lists and other named sections |
| Scripts | NUL-terminated ID strings in CMB files |
| Deployments | IDs inside compressed `dispos.cmp` archives |
| Shops | item identities in shop binaries |
| Battle/map model data | assignments in battle data and `FE8Anim.bin` |
| `main.dol` | engine string literals; usually a strong reason not to remove |
| Repoint caller | preserves caller with deliberate replacement semantics |
| Delete caller | removes that gameplay path; must be tested |
| Remove final entry | avoids shifting later table entries, but still affects references/state |
| Remove middle entry | shifts all later indices; old saves can load wrong records |

## Interactions and precedence

The deletion guard sees supported textual references, not semantic numeric state in saves and not every opaque/custom binary. A clean Check after deletion proves supported project links, not old-save compatibility. Renaming and deleting are similarly dangerous because callers may remain in executable or unsupported resources. Chapter-record removal has special risk: scripts changing to its numeric chapter ID can still target the now-missing slot even though record-reference removal does not scan chapter IDs.

## Test matrix

| Test | Expected result |
| --- | --- |
| Removal with known caller | blocked with owner listed |
| Repoint one caller | feature now uses deliberate replacement |
| Remove all supported callers | confirmation becomes available |
| Reopen/search | removed identity absent |
| Check | no dangling supported IDs |
| Neighbor records | identities/data intact after any shift |
| Fresh new game | affected chapters/features load correctly |
| Pre-change save | treated incompatible unless separately proven |

## Troubleshooting

If removal stays blocked, save the edited owner and rerun; the scan reads files/shared-session bytes, not an unapplied field. If the dialog reports `main.dol`, reconsider deletion instead of patching blindly. If Check is clean but runtime fails, search custom/opaque resources and numeric chapter transitions. If an old save loads the wrong unit/item/class, restore the table layout or require a new game.

## Save, build, and revert

Make the checkpoint before repointing callers. After removal, save FE8Data, run Check, rebuild, and test from a fresh save. Revert the full checkpoint if behavior is uncertain; reinserting a similar record at the end does not restore the removed numeric position.

## Limits and confidence

The reference-scan coverage, deletion blocking, table shifting, and number-based save warning are source-reviewed. The scan cannot prove absence from every unsupported/opaque file and cannot rewrite old saves safely. Compatibility remains **unknown** unless explicitly tested and should default to “new game required” after shifting character/class/item tables.

## Related tutorials and references

- [Check a project and fix problems](05-check-project.md)
- [Create a character](10-create-character.md)
- [Save Format](../formats/save-format.md)
- [Fe8Data](../formats/fe8data.md)

---

[← Previous: Recruit by talk and make a boss](14-recruitment-and-bosses.md) · [All tutorials](index.md) · [Next: Create and link a class →](16-classes.md)
