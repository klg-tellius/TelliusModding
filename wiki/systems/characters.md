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
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/characters.md"
system_entries: ["FE9-SYS-016", "FE9-SYS-018", "FE9-SYS-019", "FE9-SYS-020", "FE9-SYS-024"]
system_reviewed: ["FE9-SYS-016", "FE9-SYS-018", "FE9-SYS-019", "FE9-SYS-020", "FE9-SYS-024"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
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

## FE9-SYS-016 — Character definition system

<span id="fe9-sys-016"></span>

  Each character is one 0x54-byte record in [FE8Data.bin](../formats/fe8data.md). It ties together a character identifier (`PID_`), a name key (`MPID_`), portrait identifier (`FID_`), initial class (`JID_`), an [affinity](./support-system.md), personal weapon ranks, up to three personal skills, two animation identifiers, a [Biorhythm](./biorhythm.md) pattern and phase, a recruitment order, a starting transform gauge, starting level, build, weight, eight personal stat bonuses, eight growth rates, and eight fixed-growth starting values. Every eight-stat block uses **HP, Str, Mag, Skl, Spd, Lck, Def, Res** order.

  The personal stat bonuses are signed bytes, so a bonus can lower a stat: Mist's Strength bonus is −1 (Cleric base 2, so she starts with 1), and Rhys's Defense bonus is −1. The personal stat block is added to class-derived limits by native stat getters. Growth values are the character-specific rates used when progression tests whether each stat increases on level-up. Class data remains separate, allowing two characters in the same class to have different growths and personal bonuses.

The definition is immutable shared input, not the party member itself. Scripts and deployment files normally name the `PID_`; the boot-loaded database registry resolves it to this record. Saves instead serialize the character's table number, so renaming a label can break external references while reordering the character table can reinterpret existing saves. Adding or changing a character must therefore preserve both kinds of identity.

## FE9-SYS-018 — Runtime unit construction

<span id="fe9-sys-018"></span> Construction joins definitions with mutable input. A fresh chapter deployment resolves its `PID_` and optional `JID_`, allocates or reuses a unit slot, applies the requested level/autolevel and signed deployment bonuses, creates item instances with their own uses and flags, adds deployment skills and AI, assigns force and named army, and places the actor on its spawn and destination tiles. A returning party member instead brings forward saved stats, level, EXP, skills, inventory, weapon experience, supports, bonuses, and other mutable fields; the definitions still supply shared properties and caps.

The important precedence rule is conceptual: the character and class are definitions, the deployment is chapter-authored input, and the unit slot is authoritative mutable state. Effective-stat getters combine those layers when needed. They do not rewrite the database record, and loading a definition does not by itself create a map actor. A script lookup can therefore resolve a valid `PID_` while finding no deployed unit.

Construction can also fail or be skipped at its boundaries. A deployment record outside the map is skipped; an absent character/class label cannot produce a valid actor; occupied destinations are resolved through the placement rules; and an old save whose table numbers now name different definitions can construct the wrong unit even though the bytes still parse.

## FE9-SYS-019 — Unit slots and army lists

<span id="fe9-sys-019"></span> The runtime has 159 serializable unit slots. The slot number is a stable handle within the current state and is also how records link to the previous/next member of a force and to a carried unit. Empty slots serialize only an empty character/class pair; occupied slots serialize a 143-byte unit payload. This is why unit count changes the position of later save chunks.

Each occupied slot belongs to one of eight doubly linked force lists: player, enemy, allied/orderable, other/green, free, player reserve, inactive, or specially removed. Iteration follows the next link until the end of that force. Recruitment, deployment selection, death/inactivation, and cleanup move or release slots rather than changing the character definition. `UnitsInitialize` is the full reset boundary: it empties every force and frees every slot.

Code that mutates a force while iterating it must preserve the next handle first, because relinking changes traversal order. Code must also distinguish “known character” from “allocated slot” and “allocated slot” from “present on the map.” Those are three different states.

## FE9-SYS-020 — Unit-state flags

<span id="fe9-sys-020"></span> A unit's state word is a compact set of lifecycle and map-control facts. Confirmed bits include acted this turn, carrying/carried, dead or inactive, reserve, off-screen, hidden by fog, under a roof, group commander, escaped, died this chapter, mandatory or position-locked in preparations, restrictions on Give/Drop, and second-team selection. Menus, scripts, AI, map drawing, preparation, and save/load all consume subsets of this word.

Treat these as owned state, not a bag of independent cheats. `UnitSetStatus` can set a mask, but manually setting bookkeeping bits such as carrying, carried, or inactive without performing the corresponding list, occupancy, or carry operation desynchronizes the unit. Normal lifecycle code owns the paired mutations; scripts in the retail data directly set only a smaller set of control bits. Temporary status conditions and bonuses occupy separate serialized fields and should not be confused with this lifecycle word.

## FE9-SYS-024 — Mutable party state

<span id="fe9-sys-024"></span> The save's `UNIP` record is the durable party member. It stores character and class indices, force links, deployment group, level and EXP, transform gauge, tile, state words, current HP, permanent build/movement bonuses, eight personal stat values above class base, fixed-growth accumulators, learned skills, eight item instances, weapon experience, battle counters, support points, and AI state. Definitions such as a class cap or Iron Sword might remain in the database and are looked up again.

This split explains several common modding results. A character growth edit affects future gains but does not retroactively reroll stored stats. A stat booster changes the unit's saved bonus, not the shared character record. Promotion changes class, level/EXP, class-granted skills, fixed-growth progress, and HP constraints while preserving the person's identity and other applicable mutable state. A chapter transition resets chapter-local state but does not rebuild the party from its original deployments.

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

## Interactions and review boundary

All character systems on this page are reviewed without a blocking research gap. Character/class/deployment definitions construct one runtime unit, fixed army-slot storage owns mutable state, script lookup/transfer APIs mutate that object, and save serialization preserves the documented persistent fields. Slot exhaustion and malformed edited links are validation/failure cases; field offsets remain in the format references. No new primary article is needed.
