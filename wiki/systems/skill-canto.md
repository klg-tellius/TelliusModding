---
id: "skill-canto"
title: "Canto"
description: "A mounted-unit trait that preserves a second movement opportunity after acting"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Movement","Map Actions"]
aliases: ["tellius_archive.html#/skill-canto"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-canto.md"
---
# Canto

*A mounted-unit trait that preserves a second movement opportunity after acting*

Canto preserves a second movement opportunity after an eligible mounted unit acts. It is a persistent capability flag, not a percentage-based combat proc.

## Action lifecycle

The unit spends part of its movement, performs an action, and—when Canto is present—returns to movement state with only the remaining allowance. The second route still obeys map bounds, terrain cost, passability, and occupancy.

## Example

A mounted unit with 8 movement spends 5 tiles reaching an enemy and attacks. If the action leaves 3 movement available, Canto can permit up to 3 further movement-cost units; it does not refill the unit to 8 or create another attack action.

## Definition and limits

Canto is represented by `SID_TWICE` at table index 3 and has no proc parameters. The capability interpretation is strong; the exact map-state transition and every action that preserves or consumes Canto remain to be enumerated.
