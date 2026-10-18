---
id: "modding-campaign-limits"
title: "Plan around campaign limits"
description: "Budget chapter slots, clear history, flags, resources, saves, and unsupported campaign structures"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "campaign-foundations"
tutorial_stage: "draft"
prerequisites: ["modding-chapter-ids-and-story-flow"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Campaign", "Limits", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/09-campaign-limits.md"
---
# Plan around campaign limits

**Route:** Planning worksheet; Chapters → Story order; Tools → Check; Home → Disc & Patch

## What you will make

You will make a campaign capacity ledger before generating content. It budgets internal chapter slots, story position, parts, persistent flags, clear-history entries, shared IDs, large assets, and save compatibility, with an explicit confidence level for every boundary.

## Before you begin

Inventory the existing project rather than assuming unused-looking numbers are free. Export or record ChapterData slots, current story order, planned parts, recurring state, new PIDs/JIDs/IIDs/SIDs, and estimated large media. Keep the clean baseline and intended target environment: Dolphin only, or also physical hardware.

## How the editor fits together

Campaign capacity is distributed. ChapterData supplies records and file identities; executable story flow supplies reachability; scripts and deployments consume flags and IDs; the save format stores progression and a 40-entry clear history; the disc image has a fixed original capacity; world-map/base structures and new skill effects are not created merely by adding records.

The editor can allocate ordinary added story slots from 33 through 89 while excluding occupied/retail-reserved records such as 51, 52, 58, and 80–82. Slots 90+ are special/trial territory, not ordinary campaign expansion space.

## Guided walkthrough

1. Create a ledger with columns: story index, internal slot, displayed title, template, part/phase structure, script, message, map, next target, clear-history index, persistent flags, shared IDs, large assets, and verification state.
2. Populate every retail/added record already present. Mark slots 32 (ending), 51/52/58 and 80–82 (existing special/leftover records), 90+ (special), and 28/29 (special native relationship).
3. Assign planned chapters only to slots the app reports free. Do not reserve by filename appearance. Keep each internal slot unique and each story-order entry present once.
4. Count normal cleared chapters along the reachable route. At 41 or more, mark the ending War Record limitation: only 40 clear-history entries are retained.
5. For every planned multi-part chapter, record whether it uses ordinary parts, a `Complete18`-style transition, or the special 28→29 behavior. Do not generalize one mechanism to the others.
6. Allocate unique campaign/chapter flags and IDs. Record owner, writer, readers, reset lifetime, and collision check. Copied scripts retain copied flag numbers and must be audited.
7. Budget videos, audio streams, and textures against the 1,459,978,240-byte original disc capacity, leaving headroom for later growth.
8. Mark architectural requests separately: new world-map/base structures and genuinely new skill effects require executable/system work beyond record creation.
9. Run **Check** after creating the skeleton, then execute natural transitions and save/reload points from a fresh save.

## Understand every choice

| Budget | Hard/soft boundary | Planning response |
| --- | --- | --- |
| Ordinary added slots | 33–89 minus occupied/reserved records | allocate from app-reported free list |
| Ending slot | 32 | do not use as an ordinary chapter |
| Special records | 51, 52, 58, 80–82 and 90+ | preserve unless specialized evidence supports use |
| Clear history | 40 clears | plan War Record expectations separately from playability |
| Story entry | unique reachable slot | verify next links and ending |
| Flags | shared finite identities/lifetimes | maintain owner/read/write ledger |
| Shared record IDs | exact PID/JID/IID/SID uniqueness | reserve and search before creation |
| Disc capacity | 1,459,978,240 bytes | budget large media with headroom |
| Save compatibility | not guaranteed across structural changes | version saves and use fresh-game tests |

## Interactions and precedence

A free ChapterData slot is useless without story reachability and complete resources. Reachability is insufficient if the source chapter never satisfies its clear logic. A route beyond 40 clears may remain playable while the ending omits later history. Copied flag and function identities can collide across otherwise distinct slots. Larger assets can build and emulate yet exceed physical-disc constraints.

Changing records after a campaign has begun can leave old units, flags, or progress in the save; fresh-save evidence takes precedence for initialization behavior.

## Test matrix

| Boundary test | Evidence required |
| --- | --- |
| Lowest/highest planned added slot | record, resources, Check, load |
| Every insertion junction | natural source clear → destination load |
| Each part mechanism | entry, completion, next part, reload |
| Flag reuse audit | unique owner and intended lifetime |
| 40th/41st clear if applicable | gameplay plus ending War Record observation |
| Largest projected build | exact size, emulator boot, hardware test if claimed |
| Existing save versus fresh save | documented compatibility difference |

## Troubleshooting

If a supposedly free slot collides, trust the actual ChapterData inventory and app allocation. If an added chapter is unreachable, repair story flow rather than relabeling it. If copied events trigger unexpectedly, compare flag/function IDs across templates. If the campaign plays but War Record entries disappear, count clears against the 40-entry save boundary. If a requested structure has no editor owner, classify it as executable research instead of inventing data fields.

## Save, build, and revert

Version the ledger with the project. Checkpoint before slot allocation, story-flow changes, or bulk generation. Save all owners, run Check, build under a versioned name, and archive compatible fresh saves with that version. Revert route, data, scripts, messages, and generated files together.

## Limits and confidence

Slot ranges/exclusions, ending and clear-history boundaries, disc capacity, and checker behavior are source-reviewed. The practical maximum campaign length depends on design, save expectations, executable patches, and resource budgets. New world-map/base structures and new engine-level skill behavior are outside ordinary record editing. Hardware and long-route claims remain **unknown** without execution.

## Related tutorials and references

- [Create a campaign skeleton](08-new-campaign-wizard.md)
- [Use chapter and campaign flags](34-event-flags.md)
- [Test a multi-chapter campaign](62-mini-campaign.md)
- [Know the current limits](63-known-limits.md)

---

[← Previous: Create a campaign skeleton](08-new-campaign-wizard.md) · [All tutorials](index.md) · [Next: Create a character →](10-create-character.md)
