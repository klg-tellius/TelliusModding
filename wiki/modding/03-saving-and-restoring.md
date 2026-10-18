---
id: "modding-saving-and-restoring"
title: "Save changes and restore originals"
description: "Understand field commit, Apply, file saves, original snapshots, backups, and safe recovery"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "start-safely"
tutorial_stage: "draft"
prerequisites: ["modding-workspace-tour"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Saving", "Backups", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/03-saving-and-restoring.md"
---
# Save changes and restore originals

**Route:** Any editor with Apply/Save; resource actions → Restore original

## What you will make

You will perform a harmless text change, prove each persistence boundary, close and reopen the project, then restore the exact resource. The result is a recovery checklist that distinguishes field commit, editor state, file save, build output, original snapshots, and full project backup.

## Before you begin

Work in the disposable practice project. Make a full folder copy or version-control checkpoint first. Choose a reversible, visible field such as a copied message entry; do not experiment on the only copy of a campaign.

## How the editor fits together

Persistence has four gates. First, a widget must commit its current text, commonly when you press `Tab`/`Enter` or leave the field. Second, **Apply** may transfer a form or modal value into the editor's in-memory document. Third, **Save** serializes the owner file. Fourth, **Build disc** packs saved extracted files into a new image.

Several Game Data editors share one in-memory `FE8Data.bin` session. Saving that shared session can include changes made on another table. Chapter editors may own separate script, message, deployment, or map files. “Saved” therefore means saved to a named owner, not saved everywhere.

## Guided walkthrough

1. Record the chosen resource's path/identity and original value. Create a project checkpoint.
2. Change the field, press `Tab`, and observe whether the page marks it dirty. If the editor uses **Apply**, select it and verify the enclosing view reflects the value.
3. Navigate away and back without saving. Record whether the in-memory value remains; this is not proof of disk persistence.
4. Use the page's **Save** action. Read the confirmation/status text and any list of unsaved resources. For shared Game Data, confirm the save target is `FE8Data.bin`.
5. Close the project completely, reopen it, and inspect the same identity. The edited value must remain.
6. Build only after the reopen proof if you need an in-game check. Use a newly named output so an earlier image cannot be mistaken for the new one.
7. Invoke **Restore original** for the exact supported resource. Read the target shown by the action, confirm, reopen it, and compare against the value recorded in step 1.
8. Run **Tools → Check**. A successful restore should not create missing references.

## Understand every control

| Boundary/control | Writes where | Typical misconception |
| --- | --- | --- |
| `Tab`, `Enter`, focus change | widget → form/editor memory | typing alone always commits |
| Apply | modal/form → owning document in memory | Apply writes the project file |
| Save | owning document → extracted file | one Save covers every open resource |
| Save shared data | current FE8Data session → `FE8Data.bin` | only the visible table is included |
| Build disc | extracted tree → output image | an old output updates itself |
| Restore original | preserved pristine bytes → selected resource | it is multi-level undo |
| Project backup | whole selected project state | `originals` is a complete backup |

## Interactions and precedence

An uncommitted widget may lose to the previously stored form value. An unapplied modal may lose to the editor document. An unsaved editor loses to the file after restart. A saved project file still loses to an older disc image if no new build was made. During build, some shared messages/fonts/data are synchronized into `system.cmp`, so the build boundary matters.

Original snapshots are created by supported project writes and preserve pristine resource bytes, not every intermediate edit. They do not replace dated project backups or version history.

### Which save belongs to this change

Save the resource that owns the edited value. Character, class, item, skill, support, terrain, and other shared-table changes belong to the shared `FE8Data.bin` session. Dialogue/messages, scripts, deployments, maps, models, and media have their own resource saves. If one task changes several owners, save each one and record the set; no single button should be assumed to commit the entire project.

## Test matrix

| State | Reopen editor | Old build | New build |
| --- | --- | --- | --- |
| typed, not committed | may show old value | old | old |
| applied, not saved | may persist only in session | old | old |
| saved to owner | new value | old | new value after rebuild |
| restored original and saved | original value | unchanged | original after rebuild |

## Troubleshooting

If a change vanishes immediately, commit the field and use **Apply** where present. If it vanishes after restart, the owning file was not saved. If the editor reopens correctly but the game is old, verify build time/name and launch the new image. If **Restore original** is unavailable, that resource may have no preserved snapshot or may not support restoration; restore from your project checkpoint instead.

Before saving shared Game Data, inspect the unsaved-resource indicator because unrelated table edits may be included. Never “repair” uncertain state with re-extraction unless discarding the entire extracted edit set is intentional.

## Save, build, and revert

Adopt this sequence: commit field → Apply → Save owner → close/reopen → Check → build uniquely named output → runtime check. Before risky or multi-file work, make a full project checkpoint. Use **Restore original** for a known resource and your checkpoint for coordinated multi-file rollback.

## Limits and confidence

The persistence layers, shared FE8Data session, build boundary, and original-snapshot behavior are source-reviewed. Individual editors can have specialized save semantics; follow their status text. Restoration does not promise save-file compatibility or undo changes made by external programs.

## Related tutorials and references

- [Tour the workspace](02-workspace-tour.md)
- [Set up Dolphin and build the game](04-dolphin-setup.md)
- [Check a project and fix problems](05-check-project.md)

---

[← Previous: Tour the workspace](02-workspace-tour.md) · [All tutorials](index.md) · [Next: Set up Dolphin and build the game →](04-dolphin-setup.md)
