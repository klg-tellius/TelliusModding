---
id: "skill-deadeye"
title: "Deadeye"
description: "The Sniper skill: doubled hit rate, and a chance to put the target to sleep"
games: ["path-of-radiance"]
section: "systems"
article_type: "reference"
tags: ["Skills","Combat"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-deadeye.md"
---
# Deadeye

*The Sniper skill: doubled hit rate, and a chance to put the target to sleep*

Deadeye has two parts: a permanent hit-rate boost, and a chance on each hit to put the target to sleep.

## How it works

- **Hit.** The owner's final hit rate is doubled when the forecast is built, before the cap at 100. <span class="confidence confidence--confirmed">engine</span>
- **Sleep.** On each strike that hits, the owner rolls **Skill / 2** percent. On success the target falls asleep for **5 phases**, as if struck by the Sleep staff: a sleeping unit cannot act. Bosses are immune (units with the boss or final-boss trait). The roll is skipped in battles whose strikes are set by an event script. <span class="confidence confidence--confirmed">engine</span>

## Example

A Sniper with 80 hit against a target with 45 avoid has 35 % before Deadeye and 70 % with it. With 28 Skill, each hit has a 14 % chance to put the target to sleep for its next five phases.

## Definition and ownership

Deadeye is `SID_SNIPE` (狙撃, "sniping"), table index 53, with parameters `(25, 20, 1)`; 20 is its capacity cost. Its restriction list names the Sniper class, and the Occult scroll (`IID_ESOTERIC`) teaches it to Snipers. See [Skills](./skills.md) for how skills are owned and taught.

## Relationships and limits

The sleep chance is one of the activation-rate skills the Game Code tab can retune. Status durations and how they count down are described in [Combat Mechanics](./combat-mechanics.md).
