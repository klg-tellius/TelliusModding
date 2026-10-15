---
id: "posing"
title: "Skeleton Posing & Skinning"
description: "How skeleton, animation curves, and weighted mesh vertices combine into a moving model"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Graphics","Animation"]
aliases: ["tellius_archive.html#/posing"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/posing.md"
system_entries: ["FE9-SYS-312", "FE9-SYS-313", "FE9-SYS-317"]
system_reviewed: ["FE9-SYS-312", "FE9-SYS-313", "FE9-SYS-317"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Skeleton Posing & Skinning

*How skeleton, animation curves, and weighted mesh vertices combine into a moving model*

A moving battle model combines three data sets: a `.g` skeleton holding each bone's transform values, `.ga` curves that overwrite some of those values over time, and a `.gs` mesh whose vertices carry bone indices and weights.

## FE9-SYS-312 — Skeleton and skinning

<span id="fe9-sys-312"></span> The skeleton is a child/sibling hierarchy of local transforms. Every frame, local matrices chain into world matrices. Rigid shapes reference one bone or a subset loaded into up to ten GameCube matrix slots; blended vertices instead combine up to four `world × skin` matrices on the CPU using weights stored in 256ths. Positions and normals follow the same bone ownership, with normals excluding translation.

## FE9-SYS-313 — Animation-track evaluation

<span id="fe9-sys-313"></span> A `.ga` clip supplies keyed value curves for selected bones. At frame *t*, each driven channel linearly interpolates between neighboring keys and overwrites the corresponding translation, rotation, or scale value. The engine rebuilds the local matrix with Maya-style pivots and X→Y→Z Euler order, then chains the hierarchy. Undriven bones retain their seed values, which is why incomplete clips still depend on the model's base skeleton.

## How one vertex reaches its animated position

  Each frame, every bone the animation drives gets a fresh local matrix from its values; the others keep their seed matrix. World matrices are chained from the root down, and a vertex is drawn through its bone's world matrix times the bone's skinning matrix. <span class="confidence confidence--confirmed">confirmed</span>

## Animation

  At a requested frame, each curve's value is interpolated linearly between its neighboring keys and written into the bone's value block. The bone's matrix is then built Maya-style: translation, a rotation about the bone's rotate pivot (Euler angles applied X, then Y, then Z), and a scale about its scale pivot. Because the pivot is the joint's position, a character's limbs turn about their joints while their vertices stay stored in model space. <span class="confidence confidence--confirmed">confirmed</span>

  The chained seed matrices are not the poses battle bodies are normally drawn in: battle animation clips rebuild the driven locals each frame from curve values. The seed matrix matters for bones the clip does not drive and for static single-bone geometry.

## How the engine builds bone matrices

  Each frame the engine walks the skeleton tree (first child, then next sibling) and chains every bone's local matrix onto its parent's, giving one world matrix per bone. A draw call that follows a single bone loads that bone's world matrix; a draw call with a bone subset loads, for each of its up to 10 bones, the world matrix multiplied by the bone's stored skinning matrix into one of the GameCube's 10 hardware matrix slots, and each vertex names its slot. Blended vertices are instead skinned on the CPU from the same matrices. <span class="confidence confidence--confirmed">confirmed</span>

## Skinning

  For each mesh vertex, the game transforms the stored position by every influencing bone and blends the results using the stored weights; normals use the rotational part of the same transforms. <span class="confidence confidence--confirmed">confirmed</span>

  Blending happens on the CPU and uses the same matrices as the hardware path: a vertex weighted to bones *b*<sub>i</sub> is drawn at `Σ wi · world[bi] × skin_matrix[bi] × vertex`, with at most four bones and weights in 256ths. The result is stored at the fixed-point scale of the mesh's blended-vertex buffer, so an animation that carries a model far from its origin (battle clips with root motion move vertices up to about five times the body's rest size) needs a coarser scale. <span class="confidence confidence--confirmed">confirmed</span>

  Character rigs mostly use identity skinning matrices and store body vertices in model space, with bone pivots placed at the joints. Static models are different: a single-bone shape stores vertices in that bone's local space, so its apparent world placement comes from the bone chain. Multi-matrix shapes draw through `world[bone] × skin_matrix[bone] × vertex`; on nearly all character classes this keeps triangles rigid under animation, with a few dragon variants as the known exceptions.

## Worked example

Consider an elbow vertex weighted 75% to the upper-arm bone and 25% to the forearm. The clip interpolates both bones' rotation curves at the requested frame, constructs their local matrices around joint pivots, chains each through the shoulder and root, multiplies by each skinning matrix, transforms the stored vertex twice, and blends the results 0.75/0.25. A rigid glove vertex can instead name one loaded matrix slot and avoid CPU blending.

## Interactions and limits

Animation evaluation supplies transforms; battle/map/cutscene controllers choose clips, time, looping, transitions, and event markers. Materials and textures are separate draw inputs. Fixed hardware matrix slots require shapes to declare subsets, while CPU-blended buffers require a scale large enough for root motion. Malformed bone indices, non-normalized weights, missing channels, incompatible pivots, or too-fine fixed-point scale can deform geometry even when each file parses.

FE9-SYS-312 and FE9-SYS-313 define format-to-runtime evaluation. For FE9-SYS-317, the scene controller owns actor slots and authored root coordinates; the actor owns skeleton/clip evaluation; attachments inherit a named bone matrix plus their local transform. Visibility/fades are presenter state. Normal completion and skip drive actors to an endpoint, release attachments and actor resources, and signal the same scene wait. A missing required model rejects that actor instead of creating persistent campaign state.

## Review boundary

All three posing systems are reviewed without a blocking research gap. Scene ownership, root placement, clip evaluation, bone-local attachments, visibility, skip convergence, and failure teardown are established. Individual slot numbers, authored coordinate values, and prop offsets belong to each scene/resource rather than a universal posing rule. No new primary article is required.
