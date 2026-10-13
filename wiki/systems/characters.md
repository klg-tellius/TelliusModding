---
id: "characters"
title: "Characters"
description: "How identity, class, chapter placement, and mutable state combine into a unit"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Balance","Cast"]
aliases: ["tellius_archive.html#/characters"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/characters.md"
---
# Characters

*How identity, class, chapter placement, and mutable state combine into a unit*

A character is the persistent identity behind a unit: Ike remains Ike when his class changes, when a chapter gives him different equipment, or when his HP changes during battle. The game represents those layers separately. The character record supplies identity and personal tendencies; the class supplies shared capabilities; deployment data describes one chapter appearance; runtime state records what is currently happening to that unit.

## The four layers of a unit

<div class="table-wrap">
<table><thead><tr><th>Layer</th><th>Examples</th><th>Lifetime</th></tr></thead><tbody><tr><td><strong>Character</strong></td><td>Name identity, portrait, personal growths, personal skills</td><td>Shared wherever that character appears</td></tr><tr><td><strong>Class</strong></td><td>Movement, weapon ranks, stat caps, innate skills, model family</td><td>Shared by all units of that class</td></tr><tr><td><strong>Deployment</strong></td><td>Chapter inventory, starting tile, AI, bonus skill</td><td>One chapter or reinforcement group</td></tr><tr><td><strong>Runtime unit</strong></td><td>Current HP, current stats, statuses, equipped item, action state</td><td>The active battle/save state</td></tr></tbody></table>
</div>

!!! info "Do not confuse a character with a runtime unit"
    `PID_IKE` identifies Ike's database entry. The Ike currently standing on a map is a mutable runtime unit built from that entry, a class, deployment data, and saved progression. Editing a character's starting data does not mean every mutable value in an existing save is recalculated from scratch.

## Example — how Ike becomes a chapter unit

1. The character table resolves `PID_IKE`, `FID_IKE`, and starting class `JID_RANGER`.
2. The Ranger [class record](./classes.md) contributes movement, weapon access, caps, innate traits, and a battle-model family.
3. A chapter's [deployment record](../formats/dispo-format.md) names `PID_IKE` and supplies that appearance's level, army, inventory, stat bonuses, position, and optional bonus skills.
4. The engine creates a runtime unit carrying current HP, gained levels, temporary modifiers, status, and action state.
5. Combat getters combine runtime values with character and class data when the game needs an effective stat.

## What the character record contributes

  Each character is one 0x54-byte record in [FE8Data.bin](../formats/fe8data.md). It ties together a character identifier (`PID_`), a name key (`MPID_`), portrait identifier (`FID_`), initial class (`JID_`), an [affinity](./support-system.md), personal weapon ranks, up to three personal skills, two animation identifiers, a [Biorhythm](./biorhythm.md) pattern and phase, a recruitment order, a starting transform gauge, starting level, build, weight, eight personal stat bonuses, eight growth rates, and eight fixed-growth starting values. Every eight-stat block uses **HP, Str, Mag, Skl, Spd, Lck, Def, Res** order.

  The personal stat bonuses are signed bytes, so a bonus can lower a stat: Mist's Strength bonus is −1 (Cleric base 2, so she starts with 1), and Rhys's Defense bonus is −1. The personal stat block is added to class-derived limits by native stat getters. Growth values are the character-specific rates used when progression tests whether each stat increases on level-up. Class data remains separate, allowing two characters in the same class to have different growths and personal bonuses.

## How growth is tested at level-up

  Whether those growth rates are used directly, or something else entirely, depends on one global game-state flag that can be toggled on for an entire playthrough. In the default mode, each of the eight stats is rolled independently against its own stored growth percentage — a genuinely random pass/fail check per stat, per level. An alternate fixed-growth mode instead gives every stat its own hidden accumulator: each level adds a fixed amount to that accumulator (a slightly larger amount under one specific runtime condition), and a stat only actually increases once its accumulator crosses a full point. Fixed growth trades randomness for predictability — the same characters gain the same stats at the same levels every time — without changing the stored growth rates themselves, which both modes read from the same character data.

## Identity links

- `PID_` is the stable person/character identity used by deployment and scripts.
- `FID_` selects portrait resources from `Face/`.
- `JID_` selects the initial [class](./classes.md).
- `SID_` pointers grant personal [skills or traits](./skills.md).
- Animation identifiers and class/model tables help select the battle appearance described by [Combat & Battle Animation](./combat-animation.md).
- Which army a unit currently belongs to is tracked separately at runtime — see [Armies & Allegiance](./armies-allegiance.md).

  The eight bytes after the growth rates are the starting values of the fixed-growth accumulators: a unit begins with them when it is deployed, and the fixed mode adds to them from there. <span class="confidence confidence--confirmed">engine</span>

## Personal weapon ranks

  A character record carries its own nine-character weapon-rank string, in the same format as the class one (Ike `D--------`, Titania `-CA------`): the ranks the unit starts with. <span class="confidence confidence--confirmed">engine</span>

## Reference and open questions

  The exact field offsets belong in [the format article](../formats/fe8data.md); this page explains their role in the unit model. The record also holds a recruitment order, which the unit lists use as their default sort (Ike 1, Titania 2, Oscar 3&hellip;), and a laguz's starting transform gauge; one word is always empty and never read. <span class="confidence confidence--confirmed">engine</span> Generic enemy identities also require a dedicated explanation because many deployments combine reusable character templates with class and AI data rather than a unique story character.
