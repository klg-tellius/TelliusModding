---
id: "support-system"
title: "Support System"
description: "Relationship progression, persistent ranks, affinity bonuses, and the boundaries of the current specification"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Balance","Open questions"]
aliases: ["tellius_archive.html#/support-system"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/support-system.md"
---
# Support System

*Relationship progression, persistent ranks, affinity bonuses, and the boundaries of the current specification*

Supports are persistent relationships whose rank can grant battle modifiers when the paired characters meet the game's proximity and availability rules. The archive can describe the likely character-side growth data and the boundaries of the system, but not yet the final affinity bonus table.

## How the system is expected to divide responsibility

Character definitions provide relationship-growth inputs, save data must preserve accumulated relationship state and ranks, and combat-stat code applies bonuses derived from rank and elemental affinity. These are separate layers; an eight-byte character block cannot by itself contain every partner, rank, and runtime bonus.

## Example

If two characters gain enough relationship progress to increase rank, the save must retain that rank. During battle, the system can then combine the rank with each character's affinity to produce applicable bonuses. The exact numerical affinity table and proximity consumer remain open, so no values should be inferred from the candidate growth block alone.

!!! info "A real, plausible lead"
    [Every character record's](./characters.md) second 8-value block, immediately after confirmed growths, is overwhelmingly quantized to multiples of 5 and is independently labeled `supportgrowth` by another format description. This supports a growth-related interpretation but does not establish its runtime consumer. <span class="confidence confidence--strong">strong evidence</span>

!!! warning "Data that belongs to another system"
    `cp_data.bin` is not support data: it is the computer player's data &mdash; AI scripts, movement-scoring weights, heal thresholds and the thief steal list. See [cp_data.bin](../formats/cp-data-format.md). <span class="confidence confidence--open">ruled out</span>

## Confirmed: rank thresholds and progress

  Independent of the unresolved bonus table, the progression mechanics themselves are fully confirmed. Each unit can hold at most **5** concurrent supports; a sixth partner simply cannot begin building rank until one of the existing five is somehow freed. Each support pairing stores its own C/B/A progress thresholds, and a unit's current rank with that partner is just a comparison of accumulated progress against those threshold values. Progress itself increases by a flat **+1** for each qualifying conversation and is capped one point above the A threshold, so continuing to trigger a maxed-out support's conversations cannot overflow or wrap its stored progress.

  The Hit/Avoid/Critical values per support rank are not identified. Because bonuses scale by elemental affinity rather than by a unique character pair, the missing representation is expected to be affinity-indexed (Fire, Wind, Thunder, Light, Dark, Earth, Water, Heaven), not a table keyed by character labels.

  Confirming whether `support_growth` drives accumulation requires correlating the field with changing relationship state at runtime.
