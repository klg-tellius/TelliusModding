---
id: "combat-animation"
title: "Combat & Battle Animation"
description: "How a class, a weapon, and a character combine into the animation actually shown in battle"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Graphics","Animation"]
aliases: ["tellius_archive.html#/combat-animation"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/combat-animation.md"
---
# Combat & Battle Animation

*How a class, a weapon, and a character combine into the animation actually shown in battle*

A map-model animation is a pipeline across four formats. [A class](./classes.md) selects the `ymu/<class>/` folder holding its map model's [skeleton, mesh, and animation clips](../formats/model-formats.md). [FE8Anim.bin](../formats/fe8anim.md) names each `.ga` clip and tags it with a weapon type, using the same category enum as the class's weapon-rank string.

## Map models and battle models

This registry drives the **map models** (`ymu/`): the units seen on the map and the combat played there. The battle scene uses a separate, detailed **battle model** from `zu/<code>/`, chosen through `jobList.dbx` by animation ID, character or class (see [ZDBX & DBX](../formats/zdbx.md)). Its animations sit in one pack per weapon type and are named by action and weapon — `fig1_at1_ax.ga` (first axe attack), `_at2_` (second attack), `_cr1_`/`_cr2_` (criticals), `_dog_` (dodge), `_dam_` (damage), `_ded_` (death), plus combined clips such as `_cr1_ax_dog`. <span class="confidence confidence--confirmed">confirmed in game</span> See [model formats](../formats/model-formats.md).

## How the visible battle is assembled

Class chooses the model family, weapon context chooses a compatible animation category, character tags may select an override, the `.ga` clip poses the model, and `EID_` chains add spell or skill visuals. Combat mechanics separately decide hits and damage.

## Example

A Knight using a sword resolves a sword-compatible `AID_` into the Knight folder, loads its skeleton and mesh, and plays the selected clip. If the unit has a character-tagged override, that clip can change pose without changing the unit's class stats or weapon definition.

  A subset of animations are further overridden per *character*, not just per class: a 2-letter tag embedded in the animation's own name (`AID_KNIGHT_KE_N` for Kieran) lets a specific named unit get a custom weapon-holding pose distinct from the rest of their class. This is the mechanism behind, for instance, a named Knight-class character visibly carrying their weapon differently from a generic Knight enemy.

  Spell and skill effects layer on top of a unit's own animation via [FE8Effect.bin](../formats/fe8effect.md)'s `EID_` registry — a tiered spell like Fire4 doesn't just play one effect, it chains through up to three stages before landing on its final visual, each stage a separate registry entry.

  Weapon trails and attachment points depend on anchor bones in the class rig. Every character rig supplies `_s1_` and `_s2_`; weapon-specific pairs appear only on classes that need them, such as sword, spear, hand-axe, axe, bow, javelin, and effect anchors. Hand anchors are named separately with `r_hand` and `l_hand`. How the visible weapon model is attached to those hand anchors is still not fully traced.

!!! info "What's actually confirmed vs. inferred"
    The name→folder→weapon-type chain is confirmed with zero exceptions (508/508 records). The character-tag override mechanism is strong circumstantial evidence, not fully closed. For battle models, which clip plays for which action (attack, critical, dodge, death...) comes from the model's `zu/<code>.dbx` role table; the order of a strike and its timing are described in [Battle Staging & Camera](./battle-staging.md).
