---
id: "skill-steal"
title: "Steal"
description: "A map-action skill that exposes eligible enemy inventory items as targets"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Map Actions","Items"]
aliases: ["tellius_archive.html#/skill-steal"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-steal.md"
---
# Steal

*A map-action skill that exposes eligible enemy inventory items as targets*

Steal is a map command that exposes eligible items in a nearby enemy's inventory. It is selected before combat and therefore belongs to the [map-action system](./map-actions.md), not the combat-proc pipeline.

## Availability flow

The acting unit must own `SID_STEAL`. The checker scans nearby enemies, examines as many as eight runtime item slots per unit, and tests each item against the stealability table. At least one legal unit/item pair must exist before the menu can register Steal.

## Example

If an adjacent enemy carries three items but only its Vulnerary passes the stealability rule, the action is available with that item as a candidate. An empty inventory or only prohibited items produces no legal Steal target.

## Shared inventory machinery

Taking an item from an ally uses the same underlying target search. Steal broadens the eligible allegiance to enemies and adds stealing restrictions. The definition is table index 60 with parameters `(35, 0, 0)`.

## How an AI thief chooses

An AI thief only considers units it is strictly faster than, takes from each the first item in slot order that the steal list names and that it can carry (weight below its Strength), and prefers the item listed earliest in `TBL_STEALITEMS`. The details are in [cp_data.bin](../formats/cp-data-format.md). <span class="confidence confidence--confirmed">engine</span>
