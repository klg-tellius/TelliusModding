---
id: "skill-luna"
title: "Luna"
description: "A chance-based combat skill that halves the target's effective defense"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Combat"]
aliases: ["tellius_archive.html#/skill-luna"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-luna.md"
---
# Luna

*A chance-based combat skill that halves the target's effective defense*

Luna is a chance-based offensive skill that weakens the defensive value used for one attack. It changes an input to the damage formula rather than multiplying the finished damage.

## How it works

The attacker must own Luna in consolidated runtime skill state. The shared proc mechanism tests its activation; on success, physical damage uses half the target's effective Defense and magical damage uses half effective Resistance before subtraction from Attack.

## Example

Against 16 effective Defense, an attack value of 24 normally produces 8 damage. Luna changes the defensive term to 8, producing 16 damage before any later caps or strike effects. It does not simply double the original 8 damage—even though this particular example reaches the same number.

## Definition and ownership

Luna is `SID_MOONTRICK`, table index 48, with parameters `(10, 20, 1)`. Its restriction list names the Halberdier classes and the General. See [Skills](./skills.md) for how definitions become personal, class, or deployment-granted runtime skills.

## Relationships and limits

[Aether](./skill-aether.md) combines Luna's defense treatment with [Sol](./skill-sol.md) healing. Its stored 20 is its capacity cost; how its activation chance is computed remains open.
