---
id: "laguz-transformation"
title: "Laguz Transformation"
description: "A hidden 0–20 gauge that charges in human form and drains in beast form, not a simple timer"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Balance","Combat"]
aliases: ["tellius_archive.html#/laguz-transformation"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/laguz-transformation.md"
---
# Laguz Transformation

*A hidden 0–20 gauge that charges in human form and drains in beast form, not a simple timer*

Laguz units carry a hidden stat alongside their normal battle stats: a transformation gauge. It behaves like a resource meter rather than a toggle or a countdown — it climbs while the unit is untransformed and drains while transformed, and either end of its range is a meaningful boundary rather than a fixed timer length.

## Starting value

  A unit's gauge on deployment comes from its character record: 16 for Giffca, Lethe, Tibarn, Janaff and Naesala, 10 for Ranulf, 5 for Mordecai, Ena, Nasir and Ulki, 0 for everyone else. A class with the always-transformed trait starts at the full 20 instead, and [deployment records](../formats/dispo-format.md) carry a starting-gauge field of their own. <span class="confidence confidence--confirmed">engine</span>

## The gauge step

  While untransformed, an eligible unit gains 2 points per step. While transformed, the same unit instead loses 1 point per step. The step runs from the map's action flow, once for the acting unit and once for its target when the action ends, and seen in game after each combat involving a laguz; when it crosses a boundary, the transformation (or reversion) animation plays. The gauge is clamped to its 0–20 range in both directions — a unit at 0 cannot drain further, and one at 20 cannot gain further, which is also the signal used elsewhere to mean "fully charged" or "exhausted."

!!! info "Asymmetric by design"
    Draining costs a third of what gaining takes to replace — 10 steps to fully charge from empty, versus 20 steps to fully drain. Transformation is the expensive, temporary state; walking around human is the default.

## When the unit is damaged

  Taking damage also moves the gauge, through a second routine run by the damage event: an untransformed Laguz gains 4 points, a transformed one loses 3, again clamped to 0–20. A transformed state is simply the presence of the Lycanthrope status flag (skill 9) on the unit; a separate always-beast flag (skill 10) exempts a unit from both routines. <span class="confidence confidence--strong">engine</span>

## Forced full charge

  One runtime condition can override the stored value entirely and report the gauge as permanently full regardless of what's actually stored — a way to grant unlimited transformation to a specific unit or state without changing the normal accounting for every other laguz.

  Open: whether a turn change also runs the step has not been checked in game with an ordinary laguz.
