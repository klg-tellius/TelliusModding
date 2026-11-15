---
id: "support-system"
title: "Support System"
description: "Relationship progression, persistent ranks, affinity bonuses, and the boundaries of the current specification"
games: ["path-of-radiance", "radiant-dawn"]
section: "systems"
article_type: "system-reference"
tags: ["Balance","Combat"]
aliases: ["tellius_archive.html#/support-system"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/support-system.md"
system_entries: ["FE9-SYS-124", "FE9-SYS-183", "FE9-SYS-184", "FE9-SYS-185", "FE9-SYS-186"]
system_reviewed: ["FE9-SYS-124", "FE9-SYS-183", "FE9-SYS-184", "FE9-SYS-185", "FE9-SYS-186"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Support System

*Relationship progression, persistent ranks, affinity bonuses, and the boundaries of the current specification*

## Mental model and example

Supports combine four decoded `FE8Data.bin` inputs: each character's affinity, `DivineData` affinity rows, reciprocal `RelianceData` partner/threshold lists, and `KiznaData` fixed bonds. Mutable support points belong to unit instances and are saved; rank is derived from those points rather than stored as a separate letter.

!!! warning "Do not use the character growth accumulator as support data"
    Character bytes previously labelled `supportgrowth` are the starting accumulators for fixed-growth level ups. `cp_data.bin` is AI data. Neither participates in supports.

## Support progression lifecycle

<span id="fe9-sys-184"></span> Each `RelianceData` slot names a reciprocal partner and C/B/A thresholds. A unit stores one progress byte per slot at `unit+0x214` (ten saved bytes). At chapter end, `process_support_relationships` adds one when both partners remain in the player army, both have fewer than five total support stars, and the pair is not already waiting at its next threshold. Chapter file 29 and intermediate `Complete18` parts 1–3 skip this award. Permanent death clears the relationship points on both sides.

Rank comparison is threshold-gated: points up to C are unranked, up to B are C, up to A are B, and values above A are A. Progress waits exactly on a threshold until its conversation is viewed; the accepted conversation increments both units by one, crossing the threshold, and progress saturates at A+1. The five-star ceiling counts C/B/A as 1/2/3; it is not a five-partner storage limit. `RelianceData` can define up to ten usable saved slots, although vanilla's longest lists contain eight.

## Support conversation availability

<span id="fe9-sys-185"></span> The base offers a partner when the pair is reciprocal, both units exist in player or reserve state, both are below the five-star ceiling, and the caller's points equal the next threshold. Available rows sort before unavailable rows, then by higher rank and higher point byte. Selection computes the C/B/A code, prefers a matching type-13 `@on_support` event in either character order, otherwise plays `MYELL_<X>_<Y>_<R>` from `Mess/yell.m`. Only after the event/dialogue completes does `execute_support_relationship_update` increment both sides and refresh the menu; cancellation does not consume it.

## Proximity support bonuses

<span id="fe9-sys-124"></span><span id="fe9-sys-186"></span> `apply_support_combat_bonus` runs while building forecast/combat actors. A partner must exist in the same army and be within Manhattan distance 3. For every qualifying partner, the system adds `rank × affinity row` for both characters into a six-value vector—Attack, Defence, Hit, Avoid, Critical, and Critical avoid—then halves the combined vector once with an arithmetic right shift. Multiple partners therefore stack before rounding:

`bonus = floor(sum(rank × (unit affinity row + partner affinity row)) / 2)`

`DivineData` stores doubled per-rank rows: Fire `Atk 1, Hit 5`; Thunder `Def 1, Avoid 5`; Wind `Hit 5, Avoid 5`; Water `Atk 1, Def 1`; Dark `Atk 1, Avoid 5`; Light `Def 1, Hit 5`; Heaven `Hit 10`; Earth `Avoid 10`. Parity on the attacker skips support bonuses for both sides. Forecast, the status summary, and resolution use the same construction; reading it never changes progress.

For example, Ike (Earth) and Titania (Light) at A yield Defence `floor(3×1/2)=1`, Hit `floor(3×5/2)=7`, and Avoid `floor(3×10/2)=15`.

## Bond system

<span id="fe9-sys-183"></span> `KiznaData` holds 36 fixed 12-byte pair records independent of support progress. Both kinds require same-army adjacency at Manhattan distance 1. Kind 1 adds its signed value—vanilla uses 5 or 10—to Critical for every qualifying pair and stacks by summation. Kind 2 is directional protection: when PID 1 is adjacent to PID 2, attacks against PID 2 have Critical forced to zero; its stored value is unused. Bonds are definition data, not saved pair progress, and their consumers run after ordinary forecast construction at the named critical/finalization sites.

## Editing and failure boundaries

- Add or remove pairs reciprocally with identical thresholds; a one-sided entry can write before the partner's point array during rank-up.
- Preserve slot indices for existing saves, preferably by reusing vanilla empty slots instead of compacting lists.
- Keep at most ten slots because only ten point bytes are serialized.
- Edit affinities through the character affinity pointer and the fixed nine-row `DivineData` table; new affinity indices require executable changes.
- Edit fixed bonds through `KiznaData`; they do not unlock conversations or consume support stars.

## Radiant Dawn

Radiant Dawn keeps the same idea, with its own tables. <span class="confidence confidence--confirmed">engine</span>

- **Who supports whom.** `RelianceData` lists every supporting character against all of them, themselves included. Each 8-byte entry holds the partner, a marker byte (0 or 255) that no game code reads, and a support speed from 0 to 4.
- **Points.** `RelianceParam` gives the gains: 15 at each map start (30 in Part IV), 3 per phase next to the partner, 5 while carrying it, 4 per staff, 1 per Shove and 2 per Smite. The pair's speed adds +2, +1, 0, -1 or -2 to every gain. Only units of the same force with entries for each other gain points.
- **Ranks.** C, B and A open at 50, 100 and 150 points. Points stop at the next threshold until the support menu's conversation raises the rank, which adds one point; a unit at 51 or more is at C, 101 B, 151 A.
- **Bonds.** `KiznaData` pairs two characters with a kind and a signed bonus. Kind 1 adds the bonus to Critical and to Critical avoid when the two stand next to each other on the same side. The `AddKizna` script function makes temporary bonds, which the save keeps.
- **The save** holds, per unit, one points byte per `RelianceData` partner, the one active partner, and three bit sets recording which C, B and A conversations it has seen.

See [Radiant Dawn](../meta/radiant-dawn.md#supports) for the retail values.

## Interactions and review boundary

All five support systems are reviewed without a blocking research gap. The affinity table, exact proximity and rounding formula, multi-partner stacking, Parity suppression, reciprocal point lifecycle, chapter-end scheduler, base enumeration/dialogue commit, and both bond kinds are source-traced. Individual retail pair thresholds, conversation text, and bond rows are authored content documented in the data reference. No new primary article is required.
