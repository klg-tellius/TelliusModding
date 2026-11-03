---
id: "skill-chant"
title: "Chant"
description: "A nearby-ally command backed by one base skill and eight stat variants"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Map Actions"]
aliases: ["tellius_archive.html#/skill-chant"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-chant.md"
---
# Chant

*A nearby-ally command backed by one base skill and eight stat variants*

Chant is a nearby-ally map command represented by one learnable base skill and eight internal stat variants. Ownership answers whether a unit can Chant; table position identifies which stat-specific effect is being evaluated.

## Family structure

`SID_CHANT` is index 24. Indices 25–32, `SID_CHANTHP` through `SID_CHANTMDEF`, correspond to HP, Strength, Magic, Skill, Speed, Luck, Defense, and Resistance—the standard eight-stat order. The variants omit normal help text and parameters because they are implementation members of the family, not independently learned skills.

## Example

A unit owns base Chant and stands near several allies. The action checker pairs compatible stat variants with each nearby target, scores the legal combinations, and registers the highest-priority target/effect. The player-facing command therefore arises from a search over internal variants rather than a direct reference to one variant record.

## Definition and limits

The base parameters are `(13, 20, 1)`. Character and class records grant the base skill, not the variants. The exact scoring formula and the full mapping from each variant to its applied runtime modifier remain provisional.
