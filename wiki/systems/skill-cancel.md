---
id: "skill-cancel"
title: "Cancel"
description: "A combat proc that prevents the defender's counterattack"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Combat"]
aliases: ["tellius_archive.html#/skill-cancel"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-cancel.md"
---
# Cancel

*A combat proc that prevents the defender's counterattack*

Cancel is an attacker-side proc that removes the defender's ordinary counterattack from the combat schedule. It prevents a strike from being created; it does not block damage from a strike that already exists.

## Example

An attacker engages an enemy at a range where both weapons can respond. Normally the schedule begins attacker strike, then defender counter. If Cancel activates, the counter step is skipped. Speed follow-ups and other independently added strikes still follow their own rules.

## Where it acts

The skill check occurs while [the exchange builder](./combat-mechanics.md) is deciding order and quantity, before Hit, Critical, and damage are rolled for the removed counter.

## Definition and limits

Cancel is `SID_DEFENCE`, index 44, parameters `(4, 10, 1)`. The scheduling effect is confirmed; the exact stored-parameter-to-probability formula remains open.
