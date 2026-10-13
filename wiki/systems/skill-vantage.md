---
id: "skill-vantage"
title: "Vantage"
description: "A combat-order skill that lets the defender act before the initiator"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Combat"]
aliases: ["tellius_archive.html#/skill-vantage"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-vantage.md"
---
# Vantage

*A combat-order skill that lets the defender act before the initiator*

Vantage changes who strikes first when its owner is attacked. It reverses the opening order; it does not grant an extra strike by itself.

## Example

Unit A initiates combat against Unit B, who owns Vantage. The ordinary opening order would be A then B. Vantage can make B's response resolve before A's initiating strike. If B defeats A, the later strike may never occur because combat state is re-evaluated after the first result.

## What remains unchanged

After order is selected, Speed follow-ups, Brave strikes, skill-added strikes, Hit, Critical, and damage use their normal [combat-resolution](./combat-mechanics.md) rules.

## Definition and limits

Vantage is `SID_AMBUSH`, index 41, parameters `(1, 10, 1)`. The ordering effect is confirmed; the complete activation-condition formula is not.
