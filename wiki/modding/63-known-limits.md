---
id: "modding-known-limits"
title: "Know the current limits"
description: "A design-gate workflow for classifying supported, source-reviewed, simulated, unverified, code-only, and unsupported features before committing content or release promises"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Limits", "Planning", "Verification"]
aliases: []
status: "draft"
last_reviewed: "2026-10-21"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/63-known-limits.md"
tutorial_kind: "task"
tutorial_track: "test-and-release"
tutorial_stage: "draft"
prerequisites: ["modding-campaign-limits", "modding-check-project"]
verification: ["source-reviewed", "unknown"]
---
# Know the current limits

**Route:** Read before committing to a design

## What you will make

You will turn a feature wish list into a verification ledger. Every dependency receives an owner, support/confidence class, smallest prototype, app check, Dolphin check, fallback, save/release consequence, and decision to proceed, redesign, or reject.

## Before you begin

List mechanics, chapters/screens, data additions, assets, executable changes, saves, and distribution requirements. Separate “assign an existing identity” from “create a new engine behavior.” A visible raw field or writable byte is not a support promise.

## How the editor fits together

Use these evidence classes consistently:

| Class | Meaning |
| --- | --- |
| supported/verified | documented writer plus executed game test for claimed path |
| source-reviewed | ownership/format established; game matrix may remain incomplete |
| simulated | Play/renderer models relevant subset, not native parity |
| unknown/unverified | writer or behavior exists but lacks required Dolphin evidence |
| code-only | requires reviewed executable work, not table renaming |
| unsupported | writer refuses or engine/resource contract is outside scope |

## Guided walkthrough

For each desired feature, trace caller → identity/table → resource/runtime owner → persistence → release. Link the exact system/format/tutorial evidence. Mark every inference.

Prototype the highest-risk dependency first in a disposable project with one success, boundary, failure, save/reload, and clean-rebuild case. Record app and Dolphin results separately with disc revision. If it fails, use the planned fallback before producing dependent content.

Apply the main boundaries. Each row links the lesson that shows it in the app:

| Area | Boundary | Design response | Lesson |
| --- | --- | --- | --- |
| Story | Added chapters take numbers 33–89 (minus retail records); the Prologue starts every game; 32 is the ending | Reserve numbers in the worksheet | [Work with chapter IDs and story order](07-chapter-ids-and-story-flow.md) |
| Story | A chapter with no next-chapter row goes to its number + 1; **Check** errors when that chapter does not exist | Set **Next chapter:** on every added chapter | [Work with chapter IDs and story order](07-chapter-ids-and-story-flow.md) |
| Story | The clear history holds 40 chapters (the ending's war record) | Keep the story under 40 clears, or accept missing rows | [Plan around campaign limits](09-campaign-limits.md) |
| Chapter parts | At most 4 playable parts (`Opening18_2`–`_4`); 28 → 29 is a hard-coded two-part chapter | Parts for extra battles, **second part** for a two-record chapter | [Manage chapter parts and phases](65-chapter-parts-and-phases.md) |
| Flags | 96 event slots shared by campaign (from 0) and chapter flags (from 95); saves store bits by slot | Append, never reorder | [Design, register, and test event flags](34-event-flags.md) |
| Records | Saves store characters, classes and items by table number | Append; remove only the last record of a released mod | [Remove records without corrupting saves](15-remove-records.md) |
| Supports | 10 partners per character; 5 support stars per unit (C 1, B 2, A 3) | Plan pairs per character | [Create supports and conversations](13-supports.md) |
| Skills | 98 skills; effects tied to the skill's code | Edit or redistribute existing ones, or a reviewed code patch | [Understand, assign, and rebalance skills](18-skills.md) |
| Terrain | 77 fixed terrain types | Reuse and edit; do not append | [Edit terrain rules and movement costs](19-terrain-types.md) |
| Screens | No new world-map or base-screen structure | Reuse the existing structure | [Edit support, base, and world-map conversations](40-base-and-world-map-text.md) |
| Map models | Retail map bodies: median 444 triangles, at most 853; no blended vertices | **Reduce** on import, or a simpler model | [Edit weapon and scenery models within budgets](54-model-budgets.md) |
| Battle models | Largest retail: 8,840 triangles, 113 bones, 5,800 blended vertices | Stay near a retail model of the same kind | [Edit weapon and scenery models within budgets](54-model-budgets.md) |
| Models | The importer's material subset; no skinned-bow import | Start from an export of the slot | [Round-trip a model through Blender safely](51-blender-round-trip.md) |
| Presentation | The app's previews omit trails, particle colour and native timing | Preview for staging, Dolphin for the result | [Edit visual effects and particles](69-visual-effects.md) |
| Sound Room | 64 tracks; their names share 979 bytes in `main.dol` | Repeat names, keep them short | [Edit the Sound Room, credits and in-game tutorials](73-sound-room-credits-tutorials.md) |
| Tutorials | Ids 0–127 (bits of the save's masks) | Duplicate retail entries | [Edit the Sound Room, credits and in-game tutorials](73-sound-room-credits-tutorials.md) |
| Audio and video | Local previews omit MusyX groups and the game's playback life cycle; new sound effects are experimental | Test groups, loops, tails and skips in Dolphin | [Add or replace sound effects](48-sound-effects.md) |
| Disc | A GameCube disc holds 1,459,978,240 bytes; a bigger image only runs in Dolphin | Watch the build's size warning | [Replace a video and manage disc size](49-videos.md) |
| Executable | Only **Game Code** catalog entries for the US, PAL and JP `main.dol` | No guessed offsets; record which entries are on | [Apply engine tweaks](57-game-code.md) |
| Checks | **Check** sees records, files, IDs and a few engine limits, not script logic, missing message IDs or section names a script calls | Play every chapter in the app and in Dolphin | [Check a project and fix problems](05-check-project.md) |

Review the ledger at design freeze and again before release. Carry unresolved entries into release notes rather than silently upgrading confidence.

## Understand every choice

- **Proceed:** evidence covers intended scope and fallback.
- **Prototype first:** core dependency is source-reviewed/unverified.
- **Redesign:** supported existing structure can express the goal.
- **Engine-work track:** requires separate code research/patch validation.
- **Reject/defer:** failure would invalidate too much downstream content.
- **Declare incompatibility:** acceptable only when explicit and versioned.

## Things to try next

1. **Ledger a feature.** Write the row for "a laguz unit of my own" from the table above and [Create, understand, and test a class](16-classes.md): which rows apply, which lesson proves each.
2. **Find the next limit.** Pick a lesson's **Limits and confidence** and add its boundary to your ledger.
3. **Re-check after an app update.** Compare this table with the release notes of a new app version.

## Interactions and precedence

Limits compound. A new chapter with new rig, cue, code patch, and save migration has multiple independent failure boundaries; one successful preview proves none of the others. Shared identities, fixed indexes, archive precedence, memory/disc budgets, and persistence often turn a local edit into a global compatibility decision.

## Test matrix

| Dependency | Required columns |
| --- | --- |
| identity/data | owner, capacity/index, references, deletion/rename impact |
| runtime | direct, boundary, failure, interaction, cleanup |
| persistence | save/reload, transition, old-save policy |
| presentation | app preview gap, Dolphin/hardware evidence |
| distribution | clean patch apply, base revision, permissions, size |
| fallback | tested alternative and trigger for using it |

## Troubleshooting

**A control exists, so why is it unverified?** Writing/previewing bytes and native runtime compatibility are separate claims.

**One example worked.** Narrow the claim to that configuration or expand the matrix before generalizing.

**Documentation conflicts.** Prefer the owning source/system evidence, log the discrepancy, and keep uncertainty explicit.

## Save, build, and revert

Store the ledger beside release notes and project version. Prototype in recoverable copies, checkpoint before risky global/index/code changes, and record exact restoration sets. A rejected prototype should leave no hidden dependency in the release project.

## Limits and confidence

This inventory summarizes current source-reviewed boundaries; it is not immutable. Promote a limit only with reproducible evidence and update the owning system/format/tutorial together. “Unknown” means evidence is missing, not that success or failure is assumed.

## Related tutorials and references

- [Plan around campaign limits](09-campaign-limits.md)
- [Uncovered Systems Roadmap](../meta/uncovered-systems-roadmap.md)
- [FE8Data](../formats/fe8data.md)

---

[← Previous: Build a three-chapter mini-campaign](62-mini-campaign.md) · [All tutorials](index.md) · [Next: Troubleshoot builds and crashes →](64-troubleshooting.md)
