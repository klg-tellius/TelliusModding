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
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/laguz-transformation.md"
system_entries: ["FE9-SYS-188", "FE9-SYS-189"]
system_reviewed: ["FE9-SYS-188", "FE9-SYS-189"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Laguz Transformation

*A hidden 0–20 gauge that charges in human form and drains in beast form, not a simple timer*

Laguz units carry a hidden stat alongside their normal battle stats: a transformation gauge. It behaves like a resource meter rather than a toggle or a countdown — it climbs while the unit is untransformed and drains while transformed, and either end of its range is a meaningful boundary rather than a fixed timer length.

## Mental model and example

Think of the gauge as a bounded resource with two rates. An ordinary untransformed unit at 16 gains 2 on each confirmed action step: 18, then 20, where transformation can occur. Once transformed, the same steps subtract 1: 19, 18, and so on until 0 requests reversion. If the transformed unit takes damage at 18, the damage path subtracts 3 and stores 15. Neither path can write below 0 or above 20.

The model also explains why the gauge is not simply “turns remaining.” Actions involving the unit and damage events can move it, always-transformed units bypass normal accounting, and one runtime condition reports a permanent full value independently of the stored byte.

## Gauge rules and lifecycle

<span id="fe9-sys-188"></span> Deployment chooses an initial value from character data, a deployment override, or the always-transformed class rule. While the unit is on the map, confirmed action steps add 2 in human form or subtract 1 in transformed form. A separate damage consequence adds 4 in human form or subtracts 3 in transformed form. Every write clamps to 0–20. Reaching the upper boundary requests transformation; reaching the lower boundary requests reversion, with the corresponding model/animation change presented after the authoritative state change.

The transformed state is represented by the Lycanthrope trait supplied by the unit's current linked class, while the fixed-beast trait excludes a unit from both ordinary adjustment routines and makes the gauge reader report 20. Editors must preserve the distinction between raw gauge, reported gauge, and form: writing 20 to the raw byte does not itself toggle the class.

## Starting value

  A unit's gauge on deployment comes from its character record: 16 for Giffca, Lethe, Tibarn, Janaff and Naesala, 10 for Ranulf, 5 for Mordecai, Ena, Nasir and Ulki, 0 for everyone else. A class with the always-transformed trait starts at the full 20 instead, and [deployment records](../formats/dispo-format.md) carry a starting-gauge field of their own. <span class="confidence confidence--confirmed">engine</span>

## The gauge step

  While untransformed, an eligible unit gains 2 points per step. While transformed, the same unit instead loses 1 point per step. The executable has exactly two direct callers of `update_laguz_transform_gauge_step`: controller conditions for the acting unit and `pending_action_target_unit`. Both occur in the committed action sequence, check that the unit is alive, and start `E_MuTransform` when the step reaches an endpoint. A complete scan finds no phase/turn caller and no raw function-pointer reference to the step routine, so an idle phase change does not advance the FE9 gauge. The gauge is clamped to 0–20 in both directions.

!!! info "Asymmetric by design"
    Draining costs a third of what gaining takes to replace — 10 steps to fully charge from empty, versus 20 steps to fully drain. Transformation is the expensive, temporary state; walking around human is the default.

## When the unit is damaged

  Taking damage also moves the gauge, through a second routine run by the damage event: an untransformed Laguz gains 4 points, a transformed one loses 3, again clamped to 0–20. A transformed state is simply the presence of the Lycanthrope status flag (skill 9) on the unit; a separate always-beast flag (skill 10) exempts a unit from both routines. <span class="confidence confidence--strong">engine</span>

## Forced full charge

  The fixed-beast trait makes `get_effective_transform_gauge` return 20 regardless of the stored byte and excludes the unit from action and damage adjustment. This is a class/form rule, not a periodic refill.

## Scripted transformation and persistence

`UnitTransform(unit, transformed)` validates the requested state and, during visible event playback, schedules the paired-class change and transformation motion. In skip/immediate event mode it applies the same class change synchronously and refreshes the unit model/cache. `InstantUnitTransform` always uses the synchronous path. A request for the form already active is a no-op.

The shared class-change routine removes the old class's traits, follows its bidirectional linked-class pointer, installs the new class and traits, clears a transient state bit, and then writes the raw gauge from the resulting form: 20 when the new class supplies Lycanthrope, otherwise 0. Scripted transformation at an intermediate gauge therefore **does reset the saved gauge to the matching endpoint**. This corrects the earlier assumption that scripts changed presentation without touching the gauge.

Saves serialize both the one-based current class number and the raw transform-gauge byte, so map save, Suspend, and ordinary reconstruction restore the paired form and its gauge rather than recomputing them from the character's initial value. Character/deployment initialization applies only when constructing a fresh unit or starting the corresponding new chapter state.

## Transformed stats and presentation

<span id="fe9-sys-189"></span> Transformation replaces `linked_class_data` with the current class's bidirectional partner. Character identity, permanent unit bonuses, level, EXP, and current HP stay in the unit instance; every class-backed consumer immediately sees the other class record. This includes class traits and permissions, base/cap contributions, Build, Weight, Movement, vision, capacity, categories, innate weapon definition, animation ID, and growth modifiers.

Strength, Magic, Skill, Speed, Defense, and Resistance use the new class base through their ordinary effective getters. When the Demi Band's equipped `JH` property is present, each of those six getters subtracts half of `(current class base − linked class base)`, leaving half the authored transformation delta. Luck has no class base and receives no transformation delta. HP is not part of the Demi Band adjustment: maximum HP uses the active class's HP base and cap, while the class-toggle routine does not write or clamp current HP. Vanilla Laguz pairs share their HP cap; a mod that gives a pair different HP bases/caps must handle a possible current-HP-above-maximum edge itself. Build, Weight, Movement, vision, and capacity likewise follow the active class without Demi Band halving.

Actor construction calls `equip_innate_laguz_weapon` once: it clears the ordinary weapon slots, resolves the class innate `IID_` (falling back through the linked class), creates/equips it in slot 0, and marks the slot with the innate `0x80` flag. Neither scripted nor gauge-driven transformation calls that installer or edits the item instance. Form changes therefore preserve the same slot, uses, flags, and save identity; combat legality merely exposes the natural strike while transformed. Ordinary equip helpers deliberately leave `SID_ANIMALIZE` units alone, preventing a form toggle from replacing their fixed weapon.

After the class toggle, map presentation refreshes and resolves the active class/character animation ID through `FE8Anim.bin`; a missing record or pack falls back to `AID_DUMMY_N`. Full battle resolves the active animation ID, `(JID, PID)`, then JID through `jobList.dbx`; missing required full-battle assets reject that presenter and fall back to map combat. Normal, scripted, and skipped transforms all reach the same active class and refresh path.

The difficulty-indexed `GameData` Laguz row has one executable caller: the auto-level/stat-growth application routine. For its restricted linked-class path it contributes to generated permanent stats before randomized rounding. It is not read by transformation, any live stat getter, or battle EXP; changing difficulty never scales the reversible transformation delta at runtime.

## Interactions and review boundary

Both Laguz systems are reviewed without a blocking research gap. The complete executable caller census assigns gauge changes to post-action and damage paths, with no idle phase tick; scripted and automatic transforms converge on the same paired-class routine and endpoint gauge; saves preserve both class and raw gauge; all class-backed getters and the Demi Band exception are bounded; the innate weapon remains one persistent instance; and the existing map/full-battle fallback rules cover form presentation. Per-class values and animation assets are authored data rather than missing system behavior. No new primary article is needed.
