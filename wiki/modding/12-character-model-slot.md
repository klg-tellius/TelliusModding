---
id: "modding-character-model-slot"
title: "Give a character unique models"
description: "Trace map and battle model resolution, clone a slot, scope its assignment, and verify isolation"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "characters-and-game-data"
tutorial_stage: "draft"
prerequisites: ["modding-portraits"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Models", "Characters", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/12-character-model-slot.md"
---
# Give a character unique models

**Route:** Character → Portrait & models; Assets → 3D Models → New slot…; Model tables…

## What you will make

You will clone one known-working map or battle model into a unique slot, assign it only to the tutorial character and intended promotion state, prove the source character remains unchanged, then optionally replace geometry.

## Before you begin

Use a character/class combination that already renders on map and in battle. Record four resolved results from **Portrait & models**: unpromoted/promoted map model and unpromoted/promoted battle model. Check for separate story variants such as the Prologue Boyd PID.

## How the editor fits together

Map animation models use AIDs and `FE8Anim.bin`; a character AID override wins over the class default for its promotion state. Battle models resolve through class/character assignment tables in battle data and select model/texture resources. These paths are separate: changing an AID does not create a battle model, and a battle code does not select the map animation.

Slots may share underlying folders, packs, textures, or job-list lines. **New slot…** creates an isolated routing entry and copies supported resources; **Model tables…** reveals why a character resolves to a slot.

## Guided walkthrough

1. On the character's **Portrait & models** tab, write down each result and its “via” source. Open the source model in **3D Models**.
2. Choose **New slot…**. For a map slot, supply an unused AID and scope assignment to the tutorial PID plus unpromoted or promoted state. For a battle slot, supply an unused four-character code and the intended JID/PID constraints exposed by the dialog.
3. Before importing anything, reopen **Model tables…**. Resolve the tutorial character in both states and the source character. Only the intended row should choose the clone.
4. Save all table/FE8Data changes, reopen the character page, and confirm the displayed model names changed only where planned.
5. Test the copied asset unchanged on map and in Battle Simulator/Dolphin. This establishes routing and copied-resource viability.
6. Export the clone, make the smallest supported visual change, import into the cloned slot, read the import review, and repeat the same contexts.

## Understand every choice

| Choice | Meaning | Common hazard |
| --- | --- | --- |
| Map versus battle slot | selects separate resolution system | proving one and assuming the other |
| AID | map animation-set identity | character override unintentionally masks class |
| Four-character battle code | battle-model resource identity | collision or shared pack |
| PID constraint | limits assignment to character record | missing story-variant PID |
| JID constraint | limits by class | every user of class changes |
| Promotion state | selects unpromoted/promoted path | only one state receives model |
| Clone source | known-working resource baseline | source may already rely on shared variants |
| Model tables | displays assignment/resolution lines | routing success is not geometry success |

## Interactions and precedence

Character map AID overrides class AID; empty character fields fall back to class. Battle resolution uses its own ordered table conditions. Broad JID lines can match before/alongside character-specific intent depending on table structure, so inspect the resolved result, not merely the new row. Texture/model packs may remain shared unless the slot operation copied them.

## Test matrix

| Character/state | Map | Battle |
| --- | --- | --- |
| tutorial unpromoted | cloned only if targeted | cloned only if targeted |
| tutorial promoted | independent expected result | independent expected result |
| source character | original | original |
| same-class third character | original unless JID-scoped | original unless JID-scoped |
| story variant PID | explicitly tested | explicitly tested |
| unchanged clone then imported clone | both render | both render |

## Troubleshooting

If several units change, inspect JID scope and shared resources. If tables show the clone but the old model appears, verify promotion state, saved tables, build identity, and fresh initialization. If map works but battle fails, debug the battle table/resource path separately. If imported geometry distorts, restore the unchanged cloned baseline and audit rig, scale, weights, anchors, materials, and animation compatibility.

## Save, build, and revert

Checkpoint before slot creation. Save FE8Data and model tables/resources they own, run Check, and first build the unchanged clone. Revert assignment and copied resource together; deleting a slot while a table still selects it leaves a dangling presentation path.

## Limits and confidence

Resolution paths, character AID precedence, slot identifiers, and model-table inspection are source-reviewed. Rigged/blended import behavior and every battle animation remain **unknown** until Dolphin tests pass. A preview is not evidence for all map actions, promotion transitions, forged weapons, or combat animations.

## Related tutorials and references

- [Create and assign a portrait](11-portraits.md)
- [Export and import models safely](51-blender-round-trip.md)
- [Model Formats](../formats/model-formats.md)
- [Combat Animation](../systems/combat-animation.md)

---

[← Previous: Create and assign a portrait](11-portraits.md) · [All tutorials](index.md) · [Next: Create supports and conversations →](13-supports.md)
