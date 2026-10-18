---
id: "modding-battle-simulator"
title: "Simulate and render a fight"
description: "A controlled Battle Simulator workflow for combatants, levels, promotion, equipment, range, terrain, deterministic rolls, forecasts, strike logs, rendering, comparisons, and engine parity"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Battle Simulator", "Testing", "Combat"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/56-battle-simulator.md"
tutorial_kind: "task"
tutorial_track: "test-and-release"
tutorial_stage: "draft"
prerequisites: ["modding-items-and-weapons", "modding-skills"]
verification: ["source-reviewed", "unknown"]
---
# Simulate and render a fight

**Route:** Tools → Battle Simulator

## What you will make

You will create a reproducible combat fixture, explain its forecast and strike sequence from inputs, compare one-variable variants under the same roll mode, and render the same resolved fight to separate mechanical validation from presentation validation.

## Before you begin

Choose known character/class records and valid equipment. Record levels, promoted state, stats/bonuses, skills, current/max HP, weapon instance/uses, range, terrain/scenery, and who initiates. Save all edited game data before opening/reloading the simulator.

## How the editor fits together

The simulator resolves definitions into temporary combatants, checks weapon/rank/range/status legality, builds the forecast, chooses deterministic or configured rolls, and produces a strike log. **Render fight** consumes that log with model, animation, camera, scenery, effect, and audio resources. A pretty render cannot validate formulas; a correct forecast cannot validate assets.

## Guided walkthrough

Build a baseline with no exotic skills. Confirm attack, hit, critical, attack speed/doubling, counter eligibility, damage, effectiveness, triangle/terrain modifiers, and durability assumptions. Run it and retain the roll/result log.

Duplicate the setup on paper and change one variable: weapon, distance, skill, level/promotion, terrain, or HP threshold. Predict which forecast term and strikes should change before rerunning. Keep the same roll mode/seed context when comparing probability-sensitive behavior.

Use boundary cases: one point below/at doubling threshold, minimum/maximum range, lethal versus one HP remaining, effective versus non-effective class category, full versus near-broken durability, and skill condition false/true.

Render the baseline and selected variant. Verify actor/model selection, weapon, strike order, hit/miss/damage/death roles, event timing, camera, scenery, and completion. Repeat final claims in Dolphin.

## Understand every control

- **Attacker/Defender:** record identities; class/character links resolve stats, skills, models.
- **Level/Promotion:** constructs the intended state; distinguish bases from gained stats.
- **Items/weapon:** definition plus usable instance/context.
- **Distance/terrain/scenery:** mechanics range/bonuses versus presentation stage.
- **Roll mode/log:** reproducibility evidence for hit/critical/skill outcomes.
- **Forecast:** pre-action values, not the final animation.
- **Simulate:** produces resolved strikes and consequences.
- **Render fight:** stages that result with known renderer limits.

## Interactions and precedence

Legality precedes forecast; forecast precedes rolls; strike resolution precedes presentation. Skills can alter any of those stages according to their owning system. Promotion/model selection and transformed/innate weapons may use special records rather than ordinary inventory assumptions.

## Test matrix

| Axis | Boundary cases |
| --- | --- |
| range | minimum, maximum, just outside; counter/no counter |
| speed | −1, exact, +1 around doubling threshold |
| damage | zero, nonlethal, exact lethal, effective |
| accuracy | low/high, deterministic hit and miss |
| skills | absent, equipped/inactive, trigger/non-trigger |
| durability | one use, break after strike, follow-up eligibility |
| promotion/form | before/after and model/weapon resolution |
| presentation | map/full, both sides, death and skip |

## Troubleshooting

**Runs differ unexpectedly.** Compare the complete fixture and roll mode, not only displayed characters.

**No counter/attack appears.** Check usable weapon, rank, range, status, and special form ownership before formulas.

**Forecast is right but render is wrong.** Diagnose models/animations/events/presentation, not combat stats.

**Dolphin differs.** Preserve the exact fixture and roll trace, then consult the system article for unimplemented/uncertain behavior.

## Save, build, and revert

The fixture itself need not write project data. Save intentional source edits in their owners, restart the simulator, record baseline/variant, run checks, build, and reproduce in Dolphin. Revert experimental definitions after the comparison.

## Limits and confidence

Core forecast/strike pipeline is source-reviewed, but the simulator is not a complete emulator of every skill/RNG/presentation path. Rendered particles, trails, color curves, and some timing are approximate. State claims with the tested boundary and engine evidence.

## Related tutorials and references

- [Edit battle presentation](55-battle-presentation.md)
- [Battle Forecast](../systems/battle-forecast.md)
- [Combat Mechanics](../systems/combat-mechanics.md)

---

[← Previous: Edit battle presentation](55-battle-presentation.md) · [All tutorials](index.md) · [Next: Apply engine tweaks →](57-game-code.md)
