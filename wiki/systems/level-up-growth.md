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
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/level-up-growth.md"
system_entries: ["FE9-SYS-169", "FE9-SYS-170", "FE9-SYS-171", "FE9-SYS-172"]
system_reviewed: ["FE9-SYS-169", "FE9-SYS-170", "FE9-SYS-171", "FE9-SYS-172"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Level-Up Growth

*How a level-up turns growth rates into stat gains: a random roll per stat, or fixed accumulation*

Every character has eight growth rates (in percent), set in the [character record](../formats/fe8data.md) and optionally added to by the unit's linked class. A level-up converts them into stat gains in one of two ways, selected by one flag stored in the save's party record. <span class="confidence confidence--confirmed">engine</span>

## Mental model and worked example

Treat EXP, level, and stat growth as three connected but distinct steps. Combat awards EXP to mutable unit state. Crossing the threshold requests a level-up. The selected growth mode then produces eight pending gains, which are capped before the result is committed and shown. A 140% Strength growth in random mode always contributes one point and rolls the remaining 40% for a second; in fixed mode it adds 140 to the hidden Strength counter, pays one point at 100, and carries 40 forward. If the class cap permits only one more point, the pending result is trimmed even if the growth procedure produced two.

## FE9-SYS-169 — Level and EXP progression

<span id="fe9-sys-169"></span> Current level and EXP belong to the mutable unit rather than to its character or class definition. An eligible combat result adds EXP; reaching the level threshold hands control to one of the two growth paths below, commits allowed gains, increments level, and retains the post-threshold remainder according to the result path. Promotion is a different transition: it replaces the class, resets level to 1 and EXP to 0, swaps class-granted capabilities, halves fixed-growth counters, and clamps HP to the new bounds. The detailed combat EXP formula is documented in [Combat Resolution](./combat-mechanics.md).

The presentation is downstream state, not the authority. The EXP bar and level-up panel animate values that have already been calculated. Disabling or skipping that display does not avoid the level, stat, or promotion state changes. Repeated threshold crossings commit one level result at a time, delegate a promotion boundary to the class-change path, and finish pending state before save or the next presentation step.

## FE9-SYS-170 — Random level-up growth

<span id="fe9-sys-170"></span> Random mode processes HP, Strength, Magic, Skill, Speed, Luck, Defense, and Resistance independently. For each effective growth rate it first extracts guaranteed full hundreds, then consumes a random check for the remainder. Blossom (`Frac90`) grants the documented second chance on that remainder through the same growth path. Results enter pending gain bytes and are trimmed against the applicable stat limits before the UI consumes them.

This ordering matters for deterministic testing. Two units with the same displayed growths can diverge if another system has advanced the shared RNG before the level-up. A capped stat also creates an important research question: the visible gain is zero, but the precise question is whether its otherwise-required random call is still consumed. Save-state comparison around forced level-ups is the appropriate test; changing the UI animation is not.

## Rules and lifecycle — random growth

  For each stat the game takes the rate, awards 1 point for every full 100% it contains, then rolls the remainder once against the shared random-number generator for one more point. A unit with the Frac90 skill gets a second chance at that roll. The gains are written to eight pending bytes on the unit and then trimmed against the stat caps of the unit and its class before the level-up screen shows them.

## Fixed growth

  Each stat keeps a hidden counter. A level-up adds the growth rate to it; whenever the counter reaches the threshold (100) the stat gains a point and the threshold is subtracted. Units with the Frac90 skill use a threshold of 90 instead. A 40% growth therefore pays a point at levels 3, 5 and 8 and so on, with no randomness. The counters are halved when a unit promotes.

## FE9-SYS-171 — Fixed growth mode

<span id="fe9-sys-171"></span> Fixed mode replaces the remainder roll with persistent accumulation. Each stat owns a counter, adds its effective growth on level-up, awards a point whenever the threshold is crossed, subtracts the threshold, and retains the remainder. Large rates can therefore generate a guaranteed point and preserve progress toward another. Blossom changes the threshold to 90 while its separate growth-rate adjustment still applies through the shared scaling helper.

Because the counters persist, fixed growth crosses the serialization boundary in a way random rolls do not. Promotion halves them, so a mod that changes promotion without updating these counters changes future stat timing even if the visible promotion bonuses look correct. Constructors and recruitment seed the mutable counters from the unit's authored/new-unit state, while loading restores their serialized values; the system does not require one universal seed for every unit.

## FE9-SYS-172 — Stat caps

<span id="fe9-sys-172"></span> A generated gain is not automatically legal. The unit's current effective stat, mutable permanent delta, and current class limit define how much room remains; pending gains are reduced to that room before commitment. This prevents a high growth or guaranteed hundred from pushing a stat past its class cap. Promotion changes the applicable class record, so a value legal in one class must be reinterpreted under the replacement class, with current HP specifically clamped back into range.

For modding, growth rates and caps must therefore be tested together. Raising a growth without raising a cap changes how quickly a unit reaches the ceiling, not the ceiling itself. Lowering a cap can make existing saves contain values that require repair or clamping. The common human promotion cap pattern is described in [Classes](./classes.md); unusual transformations and edited class pairs still require a full transition matrix.

!!! info "Which mode is in force"
    The flag is set when a playthrough starts and read through a single accessor used by both level-up paths and the debug menu; the debug menu has an entry that flips it.

## Skills that touch it

  The same helper that scales battle EXP scales growth rates for Elite (doubled) and Frac90 (70%), with an upper limit of 100 on the result.

  See [Combat Resolution](./combat-mechanics.md) for the EXP side of the same adjustment.

## Interactions and review boundary

All four growth systems are reviewed without a blocking research gap. EXP thresholding, random guaranteed-hundreds plus remainder rolls, fixed persistent counters, Blossom scaling, caps, promotion resets/counter halving, and result-first presentation define the lifecycle. Unit-specific seed/counter values and class limits are saved or authored inputs rather than missing growth algorithms. No new primary article is needed.
