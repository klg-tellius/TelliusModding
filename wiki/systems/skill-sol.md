---
id: "skill-sol"
title: "Sol"
description: "How a successful strike becomes healing for its attacker"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Combat"]
aliases: ["tellius_archive.html#/skill-sol"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-sol.md"
---
# Sol

*How a successful strike becomes healing for its attacker*

Sol is a combat skill that heals its user when an attack deals damage. The healing is based on the strike's final damage—not the attacker's displayed Attack, weapon might, or damage before defense.

## Example

  A unit has 14 of 30 HP. Its Sol strike deals 12 damage after Defense, effectiveness, critical, and other modifiers have been resolved. Sol attempts to restore 12 HP, leaving the unit at 26 HP. If the unit had started at 25 HP, the same strike would stop at the 30-HP maximum.

!!! info "Zero damage means zero healing"
    Because healing follows damage actually dealt, a strike reduced to zero does not produce healing from the attack's earlier raw power.

## When Sol is checked

1. The combat exchange creates a strike for the attacker.
2. The attacker must own Sol in runtime skill state.
3. The chance-bearing skill path performs its activation test.
4. The normal hit and damage pipeline determines how much HP the target loses.
5. At the end of the damage path, that final loss becomes healing for the attacker, capped by maximum HP.

## How the game represents Sol

<div class="table-wrap">
<table><thead><tr><th>Part</th><th>Representation</th></tr></thead><tbody><tr><td>Definition</td><td><a class="wl" href="../../formats/fe8data/">FE8Data.bin</a> skill record 47, restricted to the paladins, Valkyrie and Titania and taught by the Occult scroll</td></tr><tr><td>Internal identity</td><td><code>SID_SUNTRICK</code> (“Sun”)</td></tr><tr><td>Runtime ownership</td><td>Skill bit 47 in the combatant's consolidated skill state</td></tr><tr><td>Parameters</td><td>Icon 9, capacity cost 20 (<code>param2=1</code>: taught by a scroll)</td></tr><tr><td>Name/help keys</td><td>The skill record points to message keys resolved in <code>system.cmp/mess/common.m</code></td></tr><tr><td>Icon</td><td>Skill icon 9: the ninth 32×32 cell of <code>window/icon.tpl</code>'s skill sheet</td></tr><tr><td>Trigger effect</td><td><code>EID_SP_SUN</code></td></tr></tbody></table>
</div>

## Relationships and edge cases

  [Aether](./skill-aether.md) reuses Sol's healing behavior while also applying [Luna](./skill-luna.md)'s defensive reduction. Sol does not itself create an extra strike, guarantee a hit, or change attack order; those decisions belong to the wider [combat pipeline](./combat-mechanics.md).

## Open questions

  The stored 20 is Sol's capacity cost, not its chance. How the game computes Sol's activation chance (and any Skill-stat contribution) has not been documented completely.
