---
id: "level-up-growth"
title: "Level-Up Growth"
description: "How a level-up turns growth rates into stat gains: a random roll per stat, or fixed accumulation"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Balance","Characters"]
aliases: ["tellius_archive.html#/level-up-growth"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/level-up-growth.md"
---
# Level-Up Growth

*How a level-up turns growth rates into stat gains: a random roll per stat, or fixed accumulation*

Every character has eight growth rates (in percent), set in the [character record](../formats/fe8data.md) and optionally added to by the unit's linked class. A level-up converts them into stat gains in one of two ways, selected by one flag stored in the save's party record. <span class="confidence confidence--confirmed">engine</span>

## Random growth

  For each stat the game takes the rate, awards 1 point for every full 100% it contains, then rolls the remainder once against the shared random-number generator for one more point. A unit with the Frac90 skill gets a second chance at that roll. The gains are written to eight pending bytes on the unit and then trimmed against the stat caps of the unit and its class before the level-up screen shows them.

## Fixed growth

  Each stat keeps a hidden counter. A level-up adds the growth rate to it; whenever the counter reaches the threshold (100) the stat gains a point and the threshold is subtracted. Units with the Frac90 skill use a threshold of 90 instead. A 40% growth therefore pays a point at levels 3, 5 and 8 and so on, with no randomness. The counters are halved when a unit promotes.

!!! info "Which mode is in force"
    The flag is set when a playthrough starts and read through a single accessor used by both level-up paths and the debug menu; the debug menu has an entry that flips it.

## Skills that touch it

  The same helper that scales battle EXP scales growth rates for Elite (doubled) and Frac90 (70%), with an upper limit of 100 on the result.

  See [Combat Resolution](./combat-mechanics.md) for the EXP side of the same adjustment.
