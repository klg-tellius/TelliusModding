---
id: "modding-replace-rig"
title: "Replace or fit a humanoid rig"
description: "A deep guide to rig kits, compatible replacement, automatic fitting, bone and anchor contracts, mappings, weights, complete animation sets, import review, testing, and rollback"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Models", "Rigging", "Blender"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/52-replace-rig.md"
tutorial_kind: "task"
tutorial_track: "models-and-battle-presentation"
tutorial_stage: "draft"
prerequisites: ["modding-blender-round-trip"]
verification: ["source-reviewed", "unknown"]
---
# Replace or fit a humanoid rig

**Route:** Assets → 3D Models → Rig kit… / Replace rig… / Fit new rig…

!!! warning "Untested rig writer in game"
    Rig replacement/fitting is source-reviewed but has not completed Dolphin verification. Work on a disposable project copy and retain every generated/replaced file.

## What you will make

You will export the selected set's rig kit, classify an incoming character as a compatible replacement or a genuinely new humanoid, preserve attachment anchors, review/edit a joint mapping, generate a fitted glTF, and inspect the complete proposed skeleton/body/animation transaction before writing it.

## Before you begin

Complete a static/body round trip first. Select one exact `ymu/` map-character set or `zu/` battle set and record its folder, skeleton bones, texture variants, weapon packs, every animation filename, and representative idle/move/attack/damage/death clips.

Export **Rig kit…** and keep its model, skeleton, animation names, and checklist together. In Blender, apply object transforms, keep one armature, remove accidental helper joints, use stable unique names, and normalize vertex weights. Do not rename or delete underscore/socket bones such as hand, weapon, arrow, camera, root, or effect anchors.

## How the editor fits together

**Replace rig…** imports an armature/body already compatible with the selected set. A map rig requires every class animation in the glTF, named like its `.ga` file. Battle replacement can import named clips and retarget missing clips by bone name when enough body bones remain; a substantially new rig needs complete/fallback-compatible animation coverage.

**Fit new rig…** instead reads your rigged model and the game's rig kit, guesses body-chain correspondences, lets you edit model-joint → game-bone mappings, then mathematically fits the game motion onto your skeleton. It preserves weapon-anchor responsibilities separately from ordinary body-chain mapping.

Both produce an **Import Review** with current/imported figures, proposed files, warnings, and joint mapping. Nothing is written until **Write files**.

## Guided walkthrough

### Export and classify

Export the Rig kit for the exact selected set. If most incoming body bones deliberately retain the game's names/hierarchy and every required animation is authored for them, choose **Replace rig…**. If the model has its own humanoid hierarchy, choose **Fit new rig…**. Do not select replacement merely because both rigs look human.

### Preserve the non-body contract

Compare the kit's anchor list with the incoming armature. Anchors attach real weapons and presentation objects; geometry should not be accidentally weighted to hidden-placeholder/socket bones. The importer refuses missing required old anchors because a visually plausible torso cannot substitute for a weapon or release socket.

For battle sets, remember that the same body/skeleton participates in multiple weapon packs. One idle pose is not the contract; every pack's attack, critical, dodge, damage, death, and combined/follow-up roles matter.

### Review a Fit mapping

Open **Fit new rig…** and select the rigged model. The mapping table lists model joints and guessed game bones. Check root/pelvis first, then spine/chest/neck/head, shoulders/arms/hands, hips/legs/feet, and any tails/wings. Detect mirrored left/right matches and mappings that cross body chains.

Blank means a joint is not driven by a mapped game bone; it may remain in bind pose. Many model joints mapped to one game bone can be intentional for twist/deformation, but test them. Use **Save mapping…** to keep reviewed JSON and **Load mapping…** for reproducibility. If offered mesh reduction, set a budget deliberately; locked weapon joints are preserved but silhouette and weights still need review.

Keep the generated fitted glTF. Open it in Blender and inspect bind pose and several animation frames before accepting the game-file transaction.

### Review Replace-rig coverage

For map rigs, ensure the glTF contains an animation whose name matches every packed or loose `.ga` target. Extra animations are ignored with a warning. Existing event tracks are retained unless the glTF carries events, but required-event validation can still reject the import.

For battle rigs, read the summary of animations imported from glTF versus retargeted by bone name, reused from another compatible clip, or missing. Dropped old-bone tracks and new bones remaining in bind pose are material warnings, not harmless noise.

### Inspect Import Review and write

Compare triangle/vertex/texture figures, proposed files, mapping method, and every warning. A new texture can replace all army/character `tex_N.tpl` variants, making every unit show the same colors. Cancel if that is not intended. Only press **Write files** when the output set is complete and explainable.

## Understand every choice

- **Rig kit…:** authoritative source contract for the selected slot.
- **Replace rig…:** new skeleton/body plus animation rebuild/retarget under preserved anchors.
- **Fit new rig…:** transfers the game's motion chains to a differently named humanoid rig.
- **Load/Save mapping:** reproducible mapping JSON; it does not modify game files.
- **Generated fitted glTF:** review artifact and future source, not proof of in-game success.
- **Import Review → Bones:** shows each joint, destination bone, and matching method.
- **Warnings:** texture-variant loss, dropped tracks, bind-pose bones, reused clips, visibility/range concerns.
- **Write files:** commits the whole proposed output through project backup handling.

## Interactions and precedence

Skeleton indices/names, mesh weights, animations, anchors, textures, and event markers form one contract. Old animation tracks cannot safely drive an unrelated skeleton. Required event markers coordinate combat presentation and can block import even when poses are valid.

Character/class model selection happens before loading the rig. A perfect imported set is invisible if the unit resolves another `AID_` or `jobList.dbx` row. Weapon actors attach through hand/family anchors and their local transforms.

## Test matrix

| Area | Required clips/checks |
| --- | --- |
| bind pose | no collapsed/exploded mesh, correct scale/orientation |
| locomotion | idle, move/run, ready; feet/root do not slide wildly |
| attacks | first/second, critical, thrown/ranged where supported |
| reactions | dodge, damage, death, return/recovery |
| weapons | both hands and every supported family/pack |
| events | impact/release/swing markers preserved and reached |
| variants | player/enemy/other/ally or character textures retained intentionally |
| visibility | hidden placeholders stay hidden; no socket-weighted body fragments |
| scene paths | map model and full battle where the set participates |
| rebuild/reload | all written files reopen and animate identically |

## Troubleshooting

**Import says animations are missing.** Supply clips named after every target listed by the Rig kit. A new map skeleton cannot reuse unrelated old tracks.

**Weapon floats or follows the torso.** Restore/check required anchors and hand mapping. Do not weight visible body geometry to socket-only bones.

**One side bends backward.** Correct left/right or chain-crossing mappings and regenerate; pose-level fixes in one clip will not repair the whole rig.

**Only idle looks correct.** Inspect weight normalization, rest pose, root/pivot, and full animation coverage.

**All army colors disappeared.** The imported image did not match an existing variant, so every variant was replaced. Reimport without a new texture or plan the variants separately.

## Save, build, and revert

Write only after saving the mapping and fitted/source glTF. Run project checks, reopen the set, preview the full matrix, build, and test in Dolphin with a disposable save.

Use **Restore original…** for the model folder or restore every proposed output as one transaction. Skeleton, body, animations, and texture variants must remain mutually compatible; partial rollback is unsafe.

## Limits and confidence

Rig checks, anchor preservation, animation completeness, name-based retargeting, automatic fitting, mapping persistence, texture behavior, event validation, and review/write boundaries are source-reviewed. Automatic humanoid mapping is heuristic, and neither fitted nor replaced rigs have curriculum-level Dolphin confirmation.

## Related tutorials and references

- [Round-trip a model through Blender safely](51-blender-round-trip.md)
- [Import animations and edit events](53-animation-import.md)
- [Combat & Battle Animation](../systems/combat-animation.md)
- [Model formats](../formats/model-formats.md)

---

[← Previous: Round-trip a model through Blender](51-blender-round-trip.md) · [All tutorials](index.md) · [Next: Import animations and edit events →](53-animation-import.md)
