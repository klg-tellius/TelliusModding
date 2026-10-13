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
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/posing.md"
---
# Skeleton Posing & Skinning

*How skeleton, animation curves, and weighted mesh vertices combine into a moving model*

A moving battle model combines three data sets: a `.g` skeleton holding each bone's transform values, `.ga` curves that overwrite some of those values over time, and a `.gs` mesh whose vertices carry bone indices and weights.

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
