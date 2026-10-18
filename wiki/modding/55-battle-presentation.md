---
id: "modding-battle-presentation"
title: "Edit battle presentation"
description: "A deep workflow for battle weapon resources, scenery, cameras, unit staging parameters, HUD DBX layout, effects, controlled rendering, engine verification, and rollback"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Battle", "Cameras", "DBX"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/55-battle-presentation.md"
tutorial_kind: "task"
tutorial_track: "models-and-battle-presentation"
tutorial_stage: "draft"
prerequisites: ["modding-model-budgets", "modding-battle-simulator"]
verification: ["source-reviewed", "unknown"]
---
# Edit battle presentation

**Route:** Assets → Battle Weapons / Sceneries / Cameras / Unit Parameters / DBX Files

## What you will make

You will alter one presentation parameter at a time in a frozen fight: weapon visual/flight, scenery, camera, actor range/speed/blending, or HUD layout. You will prove that the strike log remains unchanged while framing, motion, and UI change.

## Before you begin

Create and record a deterministic Battle Simulator case. Capture the forecast, strike order, actors, weapon categories, range, scenery, camera, hit/miss, skill, and death outcome. Keep a baseline render/video and back up every DBX/resource you touch.

## How the editor fits together

Combat mechanics create the authoritative strike log first. Battle presentation then resolves `jobList.dbx` actors, `xwp/` weapon assets, `zbg/` scenery, `xcam` camera data, unit parameters, animations/events, effects, music/SFX, and HUD DBX/layout. These are consumers of the result.

DBX **Form** edits decoded fields. **Layout** visualizes draggable screen rectangles for supported HUD widgets. Camera and actor parameters share world-space assumptions; tuning either in isolation can break their composition.

## Guided walkthrough

Render the untouched fight and note camera cuts, actor positions, weapon release, impact, HP display, and teardown. Change only one field family.

For weapons, resolve the IID's battle model/effect and compare melee versus thrown/ranged behavior. For scenery, verify floor height, scale, background, and camera obstruction. For cameras, change one key/target/FOV-related value and replay every cut. For unit parameters, change only one of approach range, speed, blend durations, jump/knockback, flying, or large-unit behavior.

In DBX Form, record raw/decoded old and new values. In Layout, move one HUD widget and check its parent/siblings, screen edges, number width, long names, both actor sides, and HP animation. Save the owning editor, then render the identical fight and compare against baseline.

Expand to melee, ranged, miss/dodge, critical/skill, double, damage, death, large/flying unit, and mirrored sides. Finish in Dolphin because the app does not render weapon trails or particle color curves and some DBX list-table consumers remain uncertain.

## Understand every control

- **Battle Weapons:** model, attachment/flight, trail/effect references owned by weapon presentation.
- **Sceneries:** stage resources and parameters used by full battle.
- **Cameras:** named rigs/keys that frame roles and transitions.
- **Unit Parameters:** approach, speed, range, blend, jump, flying/large flags.
- **DBX Form:** structured values; unknown fields remain evidence-sensitive.
- **Layout:** screen rectangles, not tactical/world coordinates.
- **Render fight:** deterministic staging comparison; not full engine parity.

## Interactions and precedence

Actor selection precedes animation/camera staging. Animation events trigger release/impact/effects; camera changes cannot repair a missing marker. HUD reads prepared combat values and must not become their authority. Map battle and full battle consume the same consequence log through different assets.

## Test matrix

| Scenario | Presentation checks |
| --- | --- |
| melee hit/miss | contact, dodge, framing, HUD |
| ranged/thrown | release, flight, target framing |
| critical/skill | special camera/effect and recovery |
| double/follow-up | continuity between roles |
| damage/death | reaction, fade, teardown |
| large/flier | bounds, ground/height, camera clipping |
| mirrored sides | labels, anchors, HUD placement |
| long names/large numbers | no clipping or overlap |
| skip/animation off | identical final gameplay state |

## Troubleshooting

**Mechanics changed.** Recheck the simulator inputs; presentation edits should not alter the strike log.

**Projectile is hidden.** Inspect release event, attachment anchor, flight asset, camera, and scenery occlusion in that order.

**HUD looks right at rest but overlaps in motion.** Test damage interpolation, long labels, and both sides throughout the clip.

**App and Dolphin differ.** Consult renderer limits before compensating with incorrect game data.

## Save, build, and revert

Save each owning resource separately and log old/new values. Run checks, render the fixed case, build, and execute the matrix in Dolphin. Revert one field family at a time or restore complete original DBX/assets when relationships are unclear.

## Limits and confidence

Selection/staging ownership, state-machine roles, HUD consumption, camera/unit parameters, and skip convergence are source-reviewed. App rendering omits trails and some particle behavior; several low-level DBX fields remain uncertain and require built-game observation.

## Related tutorials and references

- [Simulate and render a fight](56-battle-simulator.md)
- [Combat & Battle Animation](../systems/combat-animation.md)
- [Battle Staging](../systems/battle-staging.md)

---

[← Previous: Edit weapon and scenery models within budgets](54-model-budgets.md) · [All tutorials](index.md) · [Next: Simulate and render a fight →](56-battle-simulator.md)
