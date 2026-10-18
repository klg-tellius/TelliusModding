---
id: "modding-mini-campaign"
title: "Build a three-chapter mini-campaign"
description: "An integration project joining chapter slots, story routing, characters, deployments, recruitment, reinforcement, shops, flags, supports, boss logic, save boundaries, Dolphin testing, and release packaging"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Campaign", "Integration", "Testing"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/62-mini-campaign.md"
tutorial_kind: "task"
tutorial_track: "test-and-release"
tutorial_stage: "draft"
prerequisites: ["modding-new-campaign-wizard", "modding-event-recipes", "modding-share-a-patch"]
verification: ["source-reviewed", "unknown"]
---
# Build a three-chapter mini-campaign

**Route:** Chapters → New campaign…

## What you will make

You will build a minimal three-chapter route: chapter 1 recruits a unit, chapter 2 loads a one-time reinforcement and reacts to a campaign flag, chapter 3 presents a stationary boss and routes to an ending. You will verify roster, inventory, flags, supports, and history across two native save boundaries before packaging a clean-room patch.

## Before you begin

Complete the focused character, deployment, event, dialogue, flag, shop, AI, Play, and patch lessons. Reserve three legal free slots and unique PID/JID/AID/IID/message/flag identities in a worksheet. Avoid slots with documented special behavior and keep clear-history capacity within 40 entries.

## How the editor fits together

The campaign wizard creates/copies a skeleton; it does not infer your story contract. Chapter records, story order, maps, deployments by difficulty, events, messages, shops, flags, supports, AI, ending, and save state remain distinct owners. Integration succeeds only when identities and transitions connect them.

## Guided walkthrough

Write each chapter's slot, display title, template, objective, roster, boss, recruit/wave, local flags, campaign flags, rewards, shops, and next route. Create the three skeleton chapters and immediately set story order `1 → 2 → 3 → ending`. Run Check before content.

Chapter 1: create a small player/enemy/NPC setup, opening dialogue, and guarded talk recruitment. The event must validate actors, show dialogue, join/change faction through the supported action, set a chapter flag, and refuse repeat. Add only the support content needed for one visible threshold.

Chapter 2: create difficulty-specific placements and one reinforcement section. Trigger on an exact phase/turn with a local one-time flag. Use the campaign flag from chapter 1 to alter a line, unit, or reward. Author concise Armory/Vendor/Forge stock per difficulty.

Chapter 3: assemble a boss from character/class/stats/equipment, hold Attack and Move AI, battle/death dialogue, objective condition, defeat condition, and guarded victory. Add a recruited-character conditional scene and route final victory to the ending.

At every milestone run Check and Play the chapter independently. Then run all three in sequence. Finally build and start a fresh Dolphin save; save/reload after chapters 1 and 2 and verify the final ending. Create/apply a `.tpatch` to a clean base and smoke-test that output.

## Understand every choice

- **Slot/template:** resource namespace and copied assumptions, not visible story order.
- **Story order:** normal transition graph; chapter jumps do not validate it.
- **Chapter versus campaign flags:** local one-map guards versus cross-boundary state.
- **Difficulty variants:** independent deployments/shops with explicit sharing only.
- **Objective/victory/defeat:** authoritative completion routes, not test-turn shortcuts.
- **Ending route:** final transition and presentation owner.

## Interactions and precedence

Copied templates can retain flags, functions, message keys, deployments, shops, or transitions. Unique identity and reference review precede content polish. Recruitment must converge roster/faction/actor state; reinforcement must converge section load/guard; native chapter clear/save owns persistent transition.

## Test matrix

| Boundary | Evidence |
| --- | --- |
| chapter 1 recruit | wrong/right actor, no repeat, roster after clear |
| 1 → 2 save/load | recruit, items, support, campaign flag persist |
| chapter 2 wave | before/exact/after timing, one-time guard, all difficulties |
| 2 → 3 save/load | persistent state and local-flag reset semantics |
| chapter 3 boss | hold, quote, death, objective and defeat |
| conditional ending | flag/recruit absent versus present |
| full route | fresh save reaches ending without jumps |
| patch output | clean-applied build reproduces smoke path |

## Troubleshooting

**Later chapter fails.** Return to the last passing save boundary and compare carried roster/flags/items/routes.

**Copied content fires unexpectedly.** Search template flags, functions, groups, and message identities before inventing another guard.

**Independent chapters pass but sequence fails.** Test story-order and native save transition; Play/jumps can bypass ownership.

## Save, build, and revert

Checkpoint after skeleton and after each chapter. Restore only to a known passing boundary and keep the worksheet authoritative. Freeze, check, build, fresh-save test, create/apply patch, and archive source plus matrix.

## Limits and confidence

All component editors are source-reviewed, but added chapters/story flow and several flagged systems still require Dolphin confirmation. The app cannot create new world-map/base-screen structures; reuse supported structures and disclose remaining gaps.

## Related tutorials and references

- [Understand a chapter's parts](06-chapter-anatomy.md)
- [Build event recipes](35-event-recipes.md)
- [Package and share a mod](61-share-a-patch.md)

---

[← Previous: Package and share a mod](61-share-a-patch.md) · [All tutorials](index.md) · [Next: Know the current limits →](63-known-limits.md)
