---
id: "skill-miracle"
title: "Miracle / Pray"
description: "A lethal-hit safeguard represented internally as SID_PRAY"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Combat"]
aliases: ["tellius_archive.html#/skill-miracle"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-miracle.md"
---
# Miracle / Pray

*A lethal-hit safeguard represented internally as SID_PRAY*

Miracle is a lethal-hit safeguard. It is consulted only when an incoming strike would otherwise reduce the defender to zero HP; successful activation changes that result so the defender survives.

## Example

A unit at 7 HP is about to take 12 damage. Without Miracle it reaches zero. If Miracle activates, the lethal result is reduced to a surviving result. A 5-damage hit against the same unit is nonlethal and follows ordinary damage handling without needing Miracle.

## Do not confuse survival with immunity

[Wing Guard](./skill-wing-guard.md) replaces incoming damage with zero. Miracle instead guards the lethal boundary, so it should not be modeled as universal damage negation.

## Definition and limits

The internal record is `SID_PRAY`, index 46, parameters `(5, 5, 1)`, taught by its own scroll and carrying no restriction list. The exact surviving-HP result and final probability formula require further mapping.
