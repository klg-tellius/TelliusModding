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
last_reviewed: "2026-10-17"
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

Apply the main boundaries:

| Area | Boundary | Design response |
| --- | --- | --- |
| campaign | added story slots 33–89 with retail exceptions; clear history 40 | reserve slots/history; test native route |
| chapter 27 | slots 28/29 hard-coded continuous transition | do not treat as ordinary independent chapters |
| skills | 98 indexed positions; effects tied to index/code | edit/redistribute existing or create reviewed code patch |
| terrain | 77 fixed types | reuse/edit; do not append |
| screens | no new world-map/base structure | reuse existing structure or redesign |
| models | material subset, no ordinary skinned-bow import, budgets | begin from export; obey slot contract |
| presentation | app omits trails/particle color and native timing | use preview for staging, Dolphin for conclusion |
| audio/video | local preview omits MusyX/game lifecycle details | test groups, loops, tails, skips, memory, disc size |
| executable | only catalog/reviewed revision sites supported | no guessed offsets; document patch state |
| saves | numeric table positions and limited decoded fields | freeze tables or declare incompatibility |

Review the ledger at design freeze and again before release. Carry unresolved entries into release notes rather than silently upgrading confidence.

## Understand every choice

- **Proceed:** evidence covers intended scope and fallback.
- **Prototype first:** core dependency is source-reviewed/unverified.
- **Redesign:** supported existing structure can express the goal.
- **Engine-work track:** requires separate code research/patch validation.
- **Reject/defer:** failure would invalidate too much downstream content.
- **Declare incompatibility:** acceptable only when explicit and versioned.

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

- [Campaign limits](09-campaign-limits.md)
- [Uncovered Systems Roadmap](../meta/uncovered-systems-roadmap.md)
- [FE8Data](../formats/fe8data.md)

---

[← Previous: Build a three-chapter mini-campaign](62-mini-campaign.md) · [All tutorials](index.md) · [Next: Troubleshoot builds and crashes →](64-troubleshooting.md)
