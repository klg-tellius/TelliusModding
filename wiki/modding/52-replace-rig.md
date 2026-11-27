---
id: "modding-replace-rig"
title: "Replace or fit a humanoid rig"
description: "A deep guide to rig kits, compatible replacement, automatic fitting, bone and anchor contracts, mappings, weights, complete animation sets, import review, testing, and rollback"
games: ["path-of-radiance", "radiant-dawn"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Models", "Rigging", "Blender"]
aliases: []
status: "draft"
last_reviewed: "2026-10-21"
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

**Route:** Assets → 3D Models → Skeleton › Export skeleton template / Skeleton › Replace skeleton and all animations / Replace with my character

**Shortcut:** **Duplicate as new model** with **Put my character (.glb) on the copy** ticked does the copy and **Replace with my character** in one go: it makes the copy for the character or class you pick, asks for the rigged model, then opens the joint mapping on the copy.

!!! warning "Untested rig writer in game"
    Rig replacement/fitting is source-reviewed but has not completed Dolphin verification. Work on a disposable project copy and retain every generated/replaced file.

## What you will make

You will export the selected set's rig kit, classify an incoming character as a compatible replacement or a genuinely new humanoid, preserve attachment anchors, review/edit a joint mapping, generate a fitted glTF, and inspect the complete proposed skeleton/body/animation transaction before writing it.

## Before you begin

Complete a static/body round trip first. Select one exact `ymu/` map-character set or `zu/` battle set and record its folder, skeleton bones, texture variants, weapon packs, every animation filename, and representative idle/move/attack/damage/death clips.

Export **Skeleton › Export skeleton template** and keep its model, skeleton, animation names, and checklist together. In Blender, apply object transforms, keep one armature, remove accidental helper joints, use stable unique names, and normalize vertex weights. Do not rename or delete underscore/socket bones such as hand, weapon, arrow, camera, root, or effect anchors.

## How the editor fits together

**Skeleton › Replace skeleton and all animations** imports an armature/body already compatible with the selected set. A map rig requires every class animation in the glTF, named like its `.ga` file. Battle replacement can import named clips and retarget missing clips by bone name when enough body bones remain; a substantially new rig needs complete/fallback-compatible animation coverage.

**Replace with my character** instead reads your rigged model and the game's rig kit, guesses body-chain correspondences, lets you edit model-joint → game-bone mappings, then mathematically fits the game motion onto your skeleton. It preserves weapon-anchor responsibilities separately from ordinary body-chain mapping.

Both produce an **Import Review** with current/imported figures, proposed files, warnings, and joint mapping. Nothing is written until **Write files**.

## Guided walkthrough

### Export and classify

Export the Rig kit for the exact selected set. If most incoming body bones deliberately retain the game's names/hierarchy and every required animation is authored for them, choose **Skeleton › Replace skeleton and all animations**. If the model has its own humanoid hierarchy, choose **Replace with my character**. Do not select replacement merely because both rigs look human.

### Preserve the non-body contract

Compare the kit's anchor list with the incoming armature. Anchors attach real weapons and presentation objects; geometry should not be accidentally weighted to hidden-placeholder/socket bones. The importer refuses missing required old anchors because a visually plausible torso cannot substitute for a weapon or release socket.

For battle sets, remember that the same body/skeleton participates in multiple weapon packs. One idle pose is not the contract; every pack's attack, critical, dodge, damage, death, and combined/follow-up roles matter.

### Review a Fit mapping

Open **Replace with my character** and select the rigged model. The dialog *Fit new rig - zu/&lt;code&gt;* explains: *Each model joint turns like the game bone it follows. Blank: the joint follows its parent (fingers, hair...). The pelvis must be the one mapped joint all the others hang from.* The table lists model joints (indented by depth) and the guessed game bone of each. Check root/pelvis first, then spine/chest/neck/head, shoulders/arms/hands, hips/legs/feet, and any tails/wings. Detect mirrored left/right matches and mappings that cross body chains.

Next to the table, both skeletons are drawn from the front (the character's left on your right). Click a model joint in the drawing or the list: it turns orange, and so does the game bone it follows. Click a bone of the game drawing to make the selected joint follow it; **Clear joint** blanks it. Blue joints follow a game bone, grey ones their parent; a red joint carries part of the mesh while nothing above it is mapped, so it would stay frozen. **Mirror left to right** copies the left side's mapping onto the right (and **Mirror right to left** the reverse): joints are paired by name (`Left`/`Right`, `L_`/`R_`, `.L`/`.R`, `hidari`/`migi`) or, failing that, by mirrored position; the message lists the joints it could not pair.

Two options sit under the table. **Lowest vertex on the ground** is the default height. **Feet: ankle at the game ankle's height** puts the lowest mapped joint at the height of the game bone it follows: use it when the mesh stops at the ankles or wears thick soles, which otherwise make the head sink or float. **Draw both sides of faces** (on by default) draws every face from both sides, as most retail capes, hair and cloth are: a downloaded model often has faces pointing inward, which vanish when drawn one-sided (holes, a cape seen through the face). Untick it for a model that already carries an inside copy of its faces.

Blank means a joint is not driven by a mapped game bone; it may remain in bind pose. Many model joints mapped to one game bone can be intentional for twist/deformation, but test them. Use **Save mapping...** (*Save the joint mapping*, a `.json` file) to keep the reviewed table and **Load mapping...** (*Load a joint mapping*) to reuse it on the next export of the same model. **Fit** builds the fitted model; **Cancel** stops. If offered mesh reduction, set a budget deliberately; locked weapon joints are preserved but silhouette and weights still need review.

Keep the generated fitted glTF. Open it in Blender and inspect bind pose and several animation frames before accepting the game-file transaction.

### Add anchors and check the rig

**Skeleton › Add anchor bones** adds the bones the engine finds by name. Type one in (name, the bone it goes under, an offset from that bone) or pick another set under **Copy the anchors of** and press **Copy**: every anchor that set has and this one lacks is listed under the matching bone (same name, else the bone the comparison of the two bodies pairs it with) at the same place, scaled to this set's height. Check each bone and offset (select a row, change it, **Update selected**), then **Add anchors**. Example: a map model fitted on a sword class has no `_ex1_`/`_ex2_`, so its spells show no effect; copy them from `ymu/sene` (the Sage) before giving it the Sage's spell clips. The anchors have no animation track: they follow their bone in every clip. The change goes through **Skeleton › Replace skeleton and all animations** and its review.

**Skeleton › Check skeleton** lists what the skeleton lacks: the anchors every map model (`_s1_`, `_s2_`) or battle model (`_r_hand_`, `_l_hand_`, `_root_`, `_cam_`) has; on a map model, the trail anchors its clips start (event `0x18` needs `_ex1_`/`_ex2_`, `0x14` `_sw1_`/`_sw2_`, `0x16` `_ax1_`/`_ax2_`...); the anchors the vanilla set had; bone and triangle counts above the disc's largest models; and map vertices blended between bones (every retail map model has one bone per vertex). The fit review repeats its problems. The Skeleton tab names what each anchor does.

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
- **Mirror left to right / right to left:** copies one side's mapping onto the other.
- **Feet / Draw both sides of faces:** height from the ankles instead of the lowest vertex; faces drawn from both sides.
- **Add anchor bones…:** engine anchors typed in or copied from another set.
- **Check rig…:** what the skeleton lacks for the engine and the set's clips.
- **Generated fitted glTF:** review artifact and future source, not proof of in-game success.
- **Import Review → Bones:** shows each joint, destination bone, and matching method.
- **Warnings:** texture-variant loss, dropped tracks, bind-pose bones, reused clips, visibility/range concerns.
- **Write files:** commits the whole proposed output through project backup handling.

## Things to try next

1. **Keep a mapping.** Save the mapping of a first fit, change one joint, fit again from **Load mapping...**, and compare.
2. **A blank joint.** Leave a tail joint blank and watch it follow its parent through an attack.
3. **Coverage report.** On **Skeleton › Replace skeleton and all animations**, read which battle animations were retargeted and which were reused from another clip.

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

**A spell or a weapon trail shows no effect on a map model.** Run **Skeleton › Check skeleton**: the clip starts a trail whose anchors the skeleton lacks. Add them with **Skeleton › Add anchor bones** (copy `_ex1_`/`_ex2_` from the Sage, `ymu/sene`).

**The head sinks into the floor or the model floats.** Fit again with **Feet: ankle at the game ankle's height**.

**Holes in the model, or a cape seen through the face.** Fit again with **Draw both sides of faces** ticked.

**Weapon floats or follows the torso.** Restore/check required anchors and hand mapping. Do not weight visible body geometry to socket-only bones.

**One side bends backward.** Correct left/right or chain-crossing mappings and regenerate; pose-level fixes in one clip will not repair the whole rig.

**Only idle looks correct.** Inspect weight normalization, rest pose, root/pivot, and full animation coverage.

**All army colors disappeared.** The imported image did not match an existing variant, so every variant was replaced. Reimport without a new texture or plan the variants separately.

## Save, build, and revert

Write only after saving the mapping and fitted/source glTF. Run project checks, reopen the set, preview the full matrix, build, and test in Dolphin with a disposable save.

Use **Revert to original** for the model folder or restore every proposed output as one transaction. Skeleton, body, animations, and texture variants must remain mutually compatible; partial rollback is unsafe.

## Radiant Dawn

Radiant Dawn's map units (`ymu/<set>/`) work the same way, with these differences:

- **Bones.** Many of their bones are placed by a translation and a joint orient (bone flags `0x67`), not by a pivot. The rig kit is written with the rest pose as its bind pose, so in Blender the body, the joints and the anchors are where the game draws them.
- **Same rig.** When the armature comes back with the class's own bones, the import keeps the game's skeleton unchanged, then rebuilds the body onto it.
- **Animations.** In each animation, a bone that moves as in the game keeps the game's own keys, and only edited bones get new ones. A clip you did not touch is written back byte for byte.
- **Paired models.** A model of two characters (`sothe1_mikaya2`, Sothe carrying Micaiah) repeats each bone name once per character. In the kit the second copy is named `hand_l~2`; the import gives the game's names back.
- **Textures.** A unit's `.tpl` can hold several images: the archer's has the body and the bow. A body using two of them imports, and textures that match the class's keep its army-colour variants.
- **A different armature.** A different armature, or another humanoid fitted with **Fit a rig**, gets a new skeleton, and every animation of the set is retargeted onto it. Checked in Dolphin with Greil's map model fitted onto Micaiah's set: on the Prologue map he stands and plays her idle. Poses a clip doesn't cover well (Micaiah's kneeling event clips) follow only roughly; check them in the preview.
- **Several textures.** Outside Radiant Dawn's map units, **Fit a rig** bakes a model with several textures into one atlas instead of refusing it.

## Limits and confidence

Rig checks, anchor preservation, animation completeness, name-based retargeting, automatic fitting, mapping persistence, texture behavior, event validation, and review/write boundaries are source-reviewed. Automatic humanoid mapping is heuristic, and neither fitted nor replaced rigs have curriculum-level Dolphin confirmation.

On Radiant Dawn, Micaiah's map model was sent through the rig kit, Blender (5.2) and the import, then played in Dolphin: on the Prologue map she stands and moves as in the unmodified game. The archer and the paired Sothe and Micaiah model were checked through Blender on the files only. Their animated poses are within 0.03 units of the game's on average. Blender resamples a few frames, which can move a vertex by up to half a unit.

## Related tutorials and references

- [Round-trip a model through Blender safely](51-blender-round-trip.md)
- [Import animations and edit events](53-animation-import.md)
- [Combat & Battle Animation](../systems/combat-animation.md)
- [Model formats](../formats/model-formats.md)

---

[← Previous: Round-trip a model through Blender](51-blender-round-trip.md) · [All tutorials](index.md) · [Next: Import animations and edit events →](53-animation-import.md)
