---
id: "staves"
title: "Staves"
description: "Player and AI rules for healing, status, movement, repair, vision, and unlocking staves"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Items", "Combat", "Status"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/staves.md"
system_entries: ["FE9-SYS-221", "FE9-SYS-222", "FE9-SYS-223", "FE9-SYS-224", "FE9-SYS-225", "FE9-SYS-226", "FE9-SYS-227", "FE9-SYS-228", "FE9-SYS-229"]
system_reviewed: ["FE9-SYS-221", "FE9-SYS-222", "FE9-SYS-223", "FE9-SYS-224", "FE9-SYS-225", "FE9-SYS-226", "FE9-SYS-227", "FE9-SYS-228", "FE9-SYS-229"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Staves

Staves share inventory, rank, range, use, animation, WEXP, and EXP plumbing, but each effect owns different target and consequence rules. A staff command is legal only when the caster can use the item, is not silenced, has an eligible target/destination, and satisfies range.

## Mental model and worked example

A staff action is common plumbing around an effect-specific middle. The menu validates caster and item, builds targets, confirms one action, resolves the selected effect, spends durability and awards progression, then schedules presentation and commits acted state. For a status staff used at distance 6 by a caster with 18 Magic and 20 Skill against 12 Resistance, accuracy is `30 + (18 - 12) × 5 + 20 - 6 × 2 = 68`; the final value is already within the 0–100 clamp. A successful roll then applies the staff's status and duration. Restore reverses the status-state portion on an eligible ally but does not use this hostile accuracy roll.

This shared wrapper does not make effects interchangeable. Healing needs a wounded ally and HP formula, Warp needs a unit and destination, Hammerne needs an eligible item instance, and Unlock needs a live map object and event path.

## Rules and lifecycle

Command construction first checks staff rank, silence and other action restrictions, remaining uses, range, and whether at least one effect-specific target exists. Selection may add a second destination or item choice. Confirmation revalidates mutable conditions before resolution. A successful or attempted resolution follows that staff family's rules, updates target state, then handles durability, WEXP/EXP, animation, numbers/effects, map refresh, and action completion. AI uses the same legal effects but owns separate target scoring and minimum-value thresholds.

Invalid conditions fail before action commitment: a full-HP healing target, status-free Restore target, occupied relocation destination, full-use Hammerne target, expired door object, or caster silenced after menu opening cannot begin an attempt. Once a hostile staff attempt reaches resolution, its hit or miss completes through the same durability/progression wrapper; only the status consequence is conditional on the roll.

## Healing and accuracy

<span id="fe9-sys-221"></span> **FE9-SYS-221 — Healing staff resolution.** Heal/Mend/Recover target one wounded ally; Physic uses extended range; Fortify enumerates every qualifying ally in its area. The item/effect record chooses fixed-plus-Magic or full-heal behavior and carries progression values. Confirmation snapshots targets, applies each heal in deterministic enumeration order with a maximum-HP clamp, then the shared staff wrapper commits one use, EXP/WEXP, UI refresh, and presentation. AI reuses legality but scores need separately.

<span id="fe9-sys-222"></span> **FE9-SYS-222 — Status staff accuracy.** The confirmed targeting calculation is `30 + (Magic − target Resistance) × 5 + Skill − distance × 2`, clamped to 0–100. Resolution consumes the shared RNG once against that value; success applies the configured status/duration, while both hit and miss complete the attempted staff action through the common durability/progression wrapper. Forecast, AI scoring, and resolution read the same current distance and effective Resistance.

<span id="fe9-sys-223"></span> **FE9-SYS-223 — Restore.** Restore's effect predicate exposes only allies whose active condition is in the removable negative-status family. Commit clears that shared status/duration field and refreshes legality/UI; it neither heals HP nor removes unrelated beneficial temporary fields. AI selects the highest-effective-level eligible target and shares the same final predicate.

<span id="fe9-sys-224"></span> **FE9-SYS-224 — Ward, Barrier, and Pure Water.** These entry paths write the same temporary-Resistance field rather than the permanent stat. The current value is used by effective Resistance and status-staff accuracy, saved with the unit, and stepped by the shared phase temporary-state handler until cleared. Reapplication replaces/refreshes that field according to the effect value; the consumer never stacks a second hidden Resistance stat.

## Relocation and utility

<span id="fe9-sys-225"></span> **FE9-SYS-225 — Rescue staff.** Rescue selects a same-side eligible unit within staff range, excluding invalid carried/inactive states, then uses deterministic adjacent-tile enumeration around the caster. Occupancy, bounds, map links, impassable/object terrain, and footprints reject destinations. Revalidation failure leaves both units in place and does not partially commit relocation; success updates occupancy before presentation/action completion.

<span id="fe9-sys-226"></span> **FE9-SYS-226 — Warp.** Warp selects an eligible ally and a free, passable, in-bounds destination; dynamic range uses Magic/2 clamped to 5–15. Player and AI share destination legality. Retail AI chooses the highest-effective-level unacted ally, finds the phase side's last valid unit and path-nearest hostile, then keeps the first lowest-threat legal destination in range and rebuilds the deciding unit's threat map on every exit.

<span id="fe9-sys-227"></span> **FE9-SYS-227 — Hammerne.** Hammerne enumerates owned inventory instances in slot order and accepts a breakable, permitted item below its definition's maximum uses. Commit restores that instance to maximum durability, spends one Hammerne use, awards the configured staff progression, and refreshes equipment if necessary. Unbreakable, full-use, forbidden, or invalidated instances never enter the commit path; retail AI's routine is a no-op.

<span id="fe9-sys-228"></span> **FE9-SYS-228 — Torch and vision effects.** Torch writes value 4 into the unit's saved temporary vision-bonus bits (`+0x1A6` bits 2–4), replacing the current bonus. `get_unit_vision_range` adds it to class vision and `compute_map_range_overlay` exposes the result as a Manhattan radius before visibility redraw. The shared temporary-state/phase lifecycle owns later stepping or clearing; Torch never modifies terrain or chapter fog. Retail AI's routine returns failure.

<span id="fe9-sys-229"></span> **FE9-SYS-229 — Unlock staff or skill.** Unlock target construction filters live door/chest map objects by the effect's range and the same event/object eligibility used by ordinary Open/Chest actions. The staff/skill grants remote access but delegates commitment to that map action, which writes persistent tile state, runs rewards/events, refreshes the map, and only then completes item/action cost. Retail AI's Unlock staff routine is a no-op.

## AI and edge cases

AI walks staff slots 0–3 and lets the last successful staff at an equal-or-higher rank win within healing or non-healing families, with healing taking priority. Healing targets use the needs-healing flag; Fortify requires at least three. Hostile status staves require hit above 4. Ward selects the lowest-Resistance ally and the last equal candidate. Torch, Hammerne, and Unlock routines return failure. Silence removes staff use entirely.

## Interactions and limits

All nine staff systems are reviewed without a blocking research gap. The common attempt/commit wrapper, effect-owned target predicates, accuracy roll, shared temporary-state storage, deterministic relocation, repair, vision, object delegation, and AI no-op branches establish the lifecycle. Per-item power/progression values and individual map object records remain data, not missing system rules. No new primary article is needed.

