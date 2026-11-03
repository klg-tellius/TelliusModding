---
id: "skill-corrosion"
title: "Corrosion"
description: "A combat proc that damages the opponent's equipped weapon"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Combat","Weapons"]
aliases: ["tellius_archive.html#/skill-corrosion"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-corrosion.md"
---
# Corrosion

*A combat proc that damages the opponent's equipped weapon*

Corrosion attacks equipment durability instead of directly changing the target's HP. On activation it damages the opponent's currently equipped weapon in addition to the weapon's ordinary use consumption.

## Lifecycle of the effect

The attacker owns Corrosion, combat resolves its proc, the effect locates the defender's runtime equipped-item instance, and that instance loses uses. The global [item definition](./items-weapons.md) supplies the weapon type and maximum-use context, while the inventory instance supplies the current durability that can actually change.

## Example

A defender carrying a 30-use weapon at 12 uses can lose extra uses to Corrosion even though that defender did not initiate an attack. This loss is separate from any one-use cost charged when the weapon itself strikes.

## Definition and limits

Corrosion is `SID_WEAPONDESTROY`, index 52, parameters `(16, 10, 1)`, taught by its own scroll and carrying no restriction list. The existence, target, and durability mutation are confirmed; the exact amount formula is not yet completely documented.
