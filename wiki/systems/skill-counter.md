---
id: "skill-counter"
title: "Counter"
description: "A defender-side proc that can add a retaliation strike"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Combat"]
aliases: ["tellius_archive.html#/skill-counter"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-counter.md"
---
# Counter

*A defender-side proc that can add a retaliation strike*

Counter is a defender-side proc that can schedule an additional retaliation strike. It is neither the ordinary weapon-range counterattack nor a Speed-based follow-up.

## How it enters combat

The defender must own Counter in runtime skill state. If its chance test succeeds and the attacker lacks the dedicated immunity flag, the exchange builder inserts another defender strike. Once inserted, that strike uses ordinary Hit, Critical, damage, effectiveness, and durability rules.

## Example

If an attacker initiates at valid counter range, the defender may already receive the normal counterattack. Counter can add a separate retaliation on top of that schedule; it does not merely make the normal counter more accurate or powerful.

## Definition and text

Counter is `SID_COUNTER`, index 55, parameters `(20, 10, 1)`. Its name and tooltip keys resolve through `system.cmp/mess/common.m`. The exact probability formula remains open; see [Skills](./skills.md).
