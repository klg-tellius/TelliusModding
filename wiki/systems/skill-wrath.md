---
id: "skill-wrath"
title: "Wrath"
description: "A passive skill that adds 50 critical rate while its owner is at half HP or less"
games: ["path-of-radiance"]
section: "systems"
article_type: "reference"
tags: ["Skills","Combat"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-wrath.md"
---
# Wrath

*A passive skill that adds 50 critical rate while its owner is at half HP or less*

Wrath makes a wounded unit dangerous: below half health it becomes far more likely to land critical hits.

## How it works

When the battle forecast is built, a unit with Wrath whose current HP is **at most half its maximum HP** gets **+50** added to its critical rate. There is no activation roll: the bonus is either there or not, and it shows in the forecast. The final critical rate is still capped at 100. <span class="confidence confidence--confirmed">engine</span>

## Example

A unit with 40 maximum HP and a 12 % critical rate keeps 12 % at 21 HP and shows 62 % at 20 HP.

## Definition and ownership

Wrath is `SID_ANGER` (怒り, "anger"), table index 43, with parameters `(3, 10, 1)`; 10 is its capacity cost. It has no class restriction, and its scroll is the Wrath item (`IID_ANGER`). See [Skills](./skills.md) for how skills are owned and taught.

## Relationships and limits

The +50 is one of the Game Code tab's combat values (Wrath critical bonus). A critical hit triples damage (see [Combat Mechanics](./combat-mechanics.md)), so Wrath pairs with skills and weapons that raise critical rate.
