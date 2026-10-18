---
id: "modding-create-character"
title: "Create a character"
description: "Create a character record, understand every field group, and prove its deployment behavior"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "characters-and-game-data"
tutorial_stage: "draft"
prerequisites: ["modding-campaign-limits"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Characters", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/10-create-character.md"
---
# Create a character

**Route:** Characters → New character… → Stats

## What you will make

You will append `PID_TUTORIAL_GUARD` as a copy of a compatible retail unit, give it an independent displayed name, make one measurable personal-stat change, deploy it in a disposable section, and verify its shared-data and chapter-local references.

## Before you begin

Checkpoint the project and choose a template with the class, weapon access, movement type, transform behavior, and model family you want. Choose a test chapter and difficulty. Search the proposed PID and MPID first; identities must be unique.

## How the editor fits together

The character is one `FE8Data.bin` record. Deployments and scripts find it by PID. MPID supplies displayed text, FID selects a portrait, JID supplies class bases and rules, SIDs add personal skills, and optional AIDs override class map models. The deployment supplies spawned allegiance, position, inventory, level/stat overrides, and AI. Creating the record neither recruits nor deploys it.

**Apply** writes the form to the shared in-memory FE8Data session. **Revert** reloads the record from that session. **Save FE8Data.bin** persists every dirty shared-data view.

## Guided walkthrough

1. Select the template and choose **New character…**. Enter `PID_TUTORIAL_GUARD`, retain the template under **Start as a copy of**, and select **Create**. Empty records are useful for format research, not this first working unit.
2. In **Identity**, keep the PID, choose **Create message…** from **Name key (MPID)**, and create a unique `MPID_TUTORIAL_GUARD`. Keep the copied FID/JID initially.
3. In **Skills**, inspect three personal SID slots, the read-only class innate skills, and the nine-character personal/class weapon-rank strings. Empty personal ranks defer to class behavior; incompatible ranks do not grant a class permission it lacks.
4. In **Map models**, leave unpromoted/promoted AID empty to inherit the class, or record the copied override. Do not make a unique asset until basic resolution works.
5. Under **Level, build and stats**, increase one **Personal bonus** by 1. Compare the read-only **Class base**. Keep growths and fixed-growth accumulators unchanged for this controlled check.
6. Select **Apply**, then **Save FE8Data.bin**. Close/reopen the character and confirm PID, MPID, class, and bonus.
7. In a disposable deployment row, assign the PID while retaining a compatible JID/inventory. Save the intended difficulty variant. Run **Check**, then compare template and copy in Play/Battle Simulator under identical conditions.

## Understand every control

| Control | Meaning |
| --- | --- |
| PID | stable character identity used by callers |
| MPID | displayed-name message key; copied keys remain shared |
| FID | portrait record identity |
| JID | class link supplying bases, growth row for autolevel, access and innate properties |
| SID slots 0–2 | personal skills in addition to class skills |
| Weapon ranks | nine-position personal string shown beside class ranks |
| Unpromoted/Promoted AID | optional character-specific map-model override; empty inherits class |
| Level | base level used by character/deployment systems |
| Build | personal constitution added to class value for rescue/weight checks |
| Weight | personal weight added to class value for rescue checks |
| Transform gauge | laguz deployment gauge, 0–20 |
| Roster order | default ordering in unit lists |
| Biorhythm / Phase | curve choice and starting point; pattern 0 selects a random curve, phase 0 corresponds to 30 |
| Personal bonus | added to class base for each of eight stats |
| Personal growth % | character level-up rates |
| Fixed growth start | accumulators used by Fraction/fixed level-up mode |

## Interactions and precedence

Final stats are not the personal row: class bases, personal bonuses, level/autolevel logic, and deployment overrides interact. Deployment JID can make a spawned instance differ from the character JID. A personal model AID overrides class map-model selection, while battle-model resolution follows separate tables. Shared MPID/FID/model resources change every consumer.

## Test matrix

| Test | Expected evidence |
| --- | --- |
| Reopen FE8Data | new PID and independent MPID persist |
| Check | PID/JID/SID/rank references valid |
| Same deployment conditions | copy differs only by planned personal bonus |
| Each difficulty variant | PID exists in the intended file only |
| Fresh save | new initialization is not masked by roster state |
| Remove test placement | record remains available but no longer spawns |

## Troubleshooting

If the original unit's name changes, both records share an MPID; create and assign a separate key. If the copy does not appear, inspect part, difficulty, section caller, and saved deployment. If stats differ by more than one, compare deployment overrides, class/JID, level, and autolevel behavior. If the map model is absent, clear a bad AID to test class inheritance.

## Save, build, and revert

Save the character through **Save FE8Data.bin** and the placement through the deployment editor. Run Check after both. To revert, restore the checkpoint or remove the appended record only after removing all references; appending preserves earlier record numbers.

## Limits and confidence

Character controls and field meanings above are source-reviewed. Exact runtime growth combination, biorhythm behavior, and all save interactions require game execution. Saves store characters/classes/items partly by table number, so structural deletion later can break compatibility.

## Related tutorials and references

- [Create and assign a portrait](11-portraits.md)
- [Give a character unique models](12-character-model-slot.md)
- [Characters](../systems/characters.md)
- [Level Up Growth](../systems/level-up-growth.md)

---

[← Previous: Plan around campaign limits](09-campaign-limits.md) · [All tutorials](index.md) · [Next: Create and assign a portrait →](11-portraits.md)
