---
id: "modding-new-campaign-wizard"
title: "Create a campaign skeleton"
description: "Use every campaign-wizard choice, inspect generated resources, and replace copied assumptions safely"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "campaign-foundations"
tutorial_stage: "draft"
prerequisites: ["modding-chapter-ids-and-story-flow"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Campaign", "Chapters", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/08-new-campaign-wizard.md"
---
# Create a campaign skeleton

**Route:** Chapters → New campaign

## What you will make

You will generate a two-chapter disposable campaign after a chosen existing chapter, add one copied starter character, and audit every generated record and file before authoring content. The skeleton is scaffolding, not a finished campaign.

## Before you begin

Checkpoint the full project. Plan two short ASCII chapter titles, one unused PID of the form `PID_[A-Z0-9_]+`, and templates whose map size, objective, scene structure, and player-army setup resemble your intended chapters. Confirm there are free supported chapter slots.

## How the editor fits together

The wizard chains existing lower-level operations. Each chapter row copies the selected chapter's maps, script, dialogue, shops, and associated resources into the next free slot, then links the rows in order after **Played after**. Each character row copies an existing character's class, stats, portrait, and model references into a new FE8Data record.

**Empty** removes units from copied deployment sections except sections whose name contains `mikata`, which represent the player's army. It keeps section headers so existing script calls still resolve. It does not blank scripts, dialogue, shops, map objects, flags, objectives, or copied story assumptions.

## Guided walkthrough

1. Open **New campaign** and set **Played after** to the existing chapter that should lead into this skeleton. Record its current successor; the generated chain is inserted after it.
2. In chapter row 1, enter a short ASCII title and select a structurally similar template. Leave **Empty** off once so the audit shows what a full copy contains.
3. Select **Add chapter row**. Give row 2 a different template and enable **Empty**. Rows are created in displayed order. Remove an accidental row with its `✕`.
4. Under **Characters**, add a row. Enter a unique uppercase PID, an optional ASCII **Name in game**, and a **Copy of** character with the desired baseline class/stats/assets.
5. Select **Create campaign**. Read all preflight failures before retrying. The preflight checks available slot count, insertion chapter, template/script existence, ASCII titles/names, PID syntax/uniqueness, and character template existence.
6. Record the allocated chapter slots and new PID. Open Story order and confirm source → chapter 1 → chapter 2 → former successor.
7. Audit each generated chapter's Overview, script, dialogue, deployments on every difficulty, map/build settings, shops, flags, and objectives. Compare the Empty chapter: non-player units should be gone while sections and player-army content remain.
8. Open the new character. Replace shared name/assets only when intentional; an empty name field deliberately retains the copied character's name key.
9. Save shared data, run **Check**, and resolve generated warnings before authoring further changes.

## Understand every control

| Control | Exact effect | Required follow-up |
| --- | --- | --- |
| Played after | insertion point for generated chain | inspect former successor and natural transition |
| Chapter title | new displayed title text, ASCII-limited | check title key/display |
| Copy of | chooses all copied chapter resources | remove template-specific assumptions |
| Empty | clears non-`mikata` deployment units | rewrite scripts and sections/objective as needed |
| Add chapter row | appends another chapter to chain | confirm row order |
| `✕` | removes row before generation | ensure no intended row was removed |
| Character ID | unique internal PID | search all references before use |
| Name in game | creates new MPID text when nonempty | confirm `common.m`; empty shares template name |
| Character Copy of | duplicates class/stats/portrait/models | audit every inherited field |

## Interactions and precedence

The wizard allocates free slots rather than using displayed titles as identities. Earlier generated chapters remain if a later chapter fails during writing, although FE8Data is not written by the core operation at that failure point; inspect the reported completed slots and restore the checkpoint before retrying. Character name text may be written to `Mess/common.m` separately, so multi-file rollback matters.

Emptying deployments preserves callers but can leave scripts waiting for removed enemies, bosses, coordinates, or flags. A copied chapter can pass file-existence checks and still implement the template's objective.

## Test matrix

| Inspection | Full-copy row | Empty row |
| --- | --- | --- |
| Story order | linked in displayed order | linked after prior row |
| Required files | all copied resources exist | all copied resources exist |
| Player-army sections | preserved | preserved |
| Other deployed units | copied | removed |
| Script/dialogue/shops | copied | still copied |
| New character | PID resolves and inherited fields reviewed | same |
| Natural transitions | source→1 and 1→2 | 2→former successor |

## Troubleshooting

If creation is rejected, correct every preflight line rather than changing unrelated data. If a title/name is rejected, use plain ASCII. If the PID exists, choose a genuinely unused identity; do not overwrite. If a later row fails after earlier files were added, stop and restore the full checkpoint before a clean retry. If Empty leaves unexpected units, inspect section names and difficulty variants.

## Save, build, and revert

Treat creation as a transaction spanning chapter files, shared data, common messages, and story flow. Save, run Check, then close/reopen and audit before building. Revert from the full pre-wizard checkpoint; deleting only the ChapterData rows can orphan copied files and text.

## Limits and confidence

Wizard controls, preflight rules, allocation sequence, copied resources, and Empty semantics are source-reviewed. A generated skeleton has not been gameplay-verified. Added story-flow support, unusual templates, objectives, special slots, and natural transitions remain **unknown** until tested from a fresh save.

## Related tutorials and references

- [Work with chapter IDs and story order](07-chapter-ids-and-story-flow.md)
- [Plan around campaign limits](09-campaign-limits.md)
- [Test a multi-chapter campaign](62-mini-campaign.md)

---

[← Previous: Work with chapter IDs and story order](07-chapter-ids-and-story-flow.md) · [All tutorials](index.md) · [Next: Plan around campaign limits →](09-campaign-limits.md)
