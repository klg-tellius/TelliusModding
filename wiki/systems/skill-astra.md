---
id: "skill-astra"
title: "Astra"
description: "A chance-based combat skill that turns one strike into five half-damage strikes"
games: ["path-of-radiance"]
section: "systems"
article_type: "reference"
tags: ["Skills","Combat"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-astra.md"
---
# Astra

*A chance-based combat skill that turns one strike into five half-damage strikes*

Astra trades damage per hit for hit count: when it activates, one strike becomes a burst of five, each dealing half damage.

## How it works

Before an exchange is played out, the game walks the attacker's strikes. For each one, an attacker with Astra rolls its activation chance, **Skill / 2** percent. On success that strike and the four strike slots after it are marked as Astra strikes, so the attack becomes five strikes in a row. Each marked strike deals **half damage, rounded up**. Hit and critical are still rolled separately for every strike, so some of the five can miss and some can be critical. <span class="confidence confidence--confirmed">engine</span>

- Astra activates only when five free strike slots remain in the exchange; otherwise the strike stays a single normal strike.
- It never activates in a battle whose strikes are set by an event script (scripted battles).
- Once it has activated in an exchange, the rest of the attacker's strikes are not rolled again.

## Example

A Swordmaster with 26 Skill has a 13 % chance per strike. Against a target taking 9 damage per normal hit, an Astra burst deals 5 + 5 + 5 + 5 + 5 = 25 damage if every strike lands, against 9 for one ordinary strike; a critical strike in the burst triples its 5.

## Definition and ownership

Astra is `SID_STARTRICK` (流星, "shooting star"), table index 49, with parameters `(11, 20, 1)`; 20 is its capacity cost. Its restriction list names the Swordmaster classes (both genders), and the Occult scroll (`IID_ESOTERIC`) teaches it to them. See [Skills](./skills.md) for how skills are owned and taught.

## Relationships and limits

Astra is one of the activation-rate skills the Game Code tab can retune (multiplier and bonus). [Aether](./skill-aether.md), [Sol](./skill-sol.md) and [Luna](./skill-luna.md) change the damage of a single strike instead of the number of strikes.
