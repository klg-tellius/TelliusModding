---
id: "skill-wing-guard"
title: "Wing Guard"
description: "A defensive skill whose block path nullifies incoming damage"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Combat"]
aliases: ["tellius_archive.html#/skill-wing-guard"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-wing-guard.md"
---
# Wing Guard

*A defensive skill whose block path nullifies incoming damage*

Wing Guard is a defensive proc whose successful block replaces an incoming strike's damage with zero. It changes the strike result after the attack exists rather than removing the strike from the schedule.

## Example

If a strike would deal 18 damage and Wing Guard blocks it, the HP loss becomes zero. Hit and attack presentation can still occur; the protected result is the damage value.

## Related protections

[Miracle](./skill-miracle.md) applies only at the lethal boundary and preserves survival rather than guaranteeing zero damage. `SID_GODDESSBLESS` reaches an equivalent full-block path without the ordinary percentage-roll call, making it the guaranteed form of this protection.

## Definition and limits

Wing Guard is `SID_WINGSHIELD`, index 45, parameters `(38, 20, 1)`, restricted to the hawk laguz classes. Its zero-damage path is confirmed; its exact activation probability is not.
