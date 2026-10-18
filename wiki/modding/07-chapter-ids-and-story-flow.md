---
id: "modding-chapter-ids-and-story-flow"
title: "Work with chapter IDs and story order"
description: "Separate internal slots, displayed chapter numbers, resources, transitions, and story-flow links"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "campaign-foundations"
tutorial_stage: "draft"
prerequisites: ["modding-chapter-anatomy"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Chapters", "Story flow", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/07-chapter-ids-and-story-flow.md"
---
# Work with chapter IDs and story order

**Route:** Chapters → Overview; Chapters → Story order

## What you will make

You will build a route ledger for three consecutive chapters and prove one natural transition from source clear to destination load. The ledger distinguishes internal slot, displayed title/number, resource names, story position, next target, and special handling.

## Before you begin

Use a checkpoint and a fresh game save for transition work. Choose an ordinary retail sequence first. Do not infer internal slot from the player's displayed chapter number: slot `01` is the prologue, and display naming is a text/presentation decision.

## How the editor fits together

ChapterData records give slots their resources. Story flow in executable data decides the next slot for a normal campaign transition. The **Story order** tool presents the new-game sequence: retail chapters 1–31 are locked in place, while added chapters above 31 can be reordered. Ending slot 32 terminates the normal story route.

Changing the displayed title does not change the slot or transition. Renaming a resource does not change story order. A debug jump proves that one chapter can load; it does not prove the preceding clear logic, save update, or next-link behavior.

## Guided walkthrough

1. For three consecutive retail chapters, record internal slot, displayed title, script/message/map names, and current next target.
2. Open **Story order**. Observe the locked retail entries. Do not apply if no change is intended.
3. For an added chapter in a disposable campaign, select it and use **Move up/Move down** only among movable added chapters. The tool prevents moving an added entry across locked retail entries.
4. Apply the order and reopen it. Confirm the stored order, then inspect the source chapter's next target and the destination's resources.
5. Save all affected data, run **Check**, and investigate unreachable-added-chapter warnings.
6. Build a uniquely named image. From a fresh save, play the source chapter through its actual clear path, save when prompted, and let the game load the destination naturally.
7. Reopen that save and confirm the destination/progression remains consistent. Compare with a direct jump only as a load-isolation test.

## Understand every choice

| Identity/choice | Meaning | Does not change |
| --- | --- | --- |
| Internal slot | numeric ChapterData/story target | displayed title automatically |
| Displayed title/number | message/presentation text | executable next link |
| Resource names | script/message/map files used by record | position in story |
| Story order | ordered route for a new game | content inside each chapter |
| Next target | successor after normal transition | whether source clear code actually completes |
| Move up/down | reorders movable added chapters | locked retail placement |
| Apply | writes a changed order | no-op order when unchanged |

Slots 28 and 29 have special native coupling and should not be treated as ordinary independent templates without specific testing. Slot 32 is the ending. Retail records 51, 52, 58, and 80–82 exist outside the ordinary story sequence and are not generally safe “free” slots.

## Interactions and precedence

Story flow determines reachability, then chapter clear code and save state determine whether the transition is reached and recorded. A chapter may load via debug but remain unreachable in a campaign. New story-flow editing depends on the applicable executable patch/support; resource existence alone cannot add a route.

The save's clear-history area holds 40 entries. A route longer than that may play while later clears are absent from the ending War Record.

## Test matrix

| Test | What it proves |
| --- | --- |
| Open destination directly | destination resources can load |
| Check story reachability | supported static next-link chain reaches it |
| Clear source naturally | source clear code reaches transition |
| Destination loads | next link and required resources cooperate |
| Save/reload at destination | persistent campaign state is viable |
| Ending War Record near boundary | clear-history behavior, not basic reachability |

## Troubleshooting

If the destination loads by jump but not by clear, inspect source clear conditions and the next target. If Check marks an added chapter unreachable, repair the story chain instead of merely changing its displayed number. If **Story order** is unavailable, preserve the reason shown for executable-flow support. If a route loops, compare every next link and ensure each slot appears once.

## Save, build, and revert

Checkpoint executable and shared data together before changing story order. Apply, save, rerun Check, rebuild, and use a fresh save. Revert the complete route change, not only the destination's files, because the executable link and ChapterData resources must agree.

## Limits and confidence

Story-order constraints, ending slot, special retail records, 40-entry clear history, and reachability checks are source-reviewed. Added-chapter patch behavior and special 28→29 handling require runtime verification for the exact route. Debug jumps never raise transition confidence above load-only evidence.

## Related tutorials and references

- [Understand a chapter's parts](06-chapter-anatomy.md)
- [Create a campaign skeleton](08-new-campaign-wizard.md)
- [Plan around campaign limits](09-campaign-limits.md)
- [Test a multi-chapter campaign](62-mini-campaign.md)

---

[← Previous: Understand a chapter's parts](06-chapter-anatomy.md) · [All tutorials](index.md) · [Next: Create a campaign skeleton →](08-new-campaign-wizard.md)
