---
id: "classes"
title: "Classes"
description: "The shared rules that give a unit movement, weapon access, caps, traits, and a battle model"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Balance"]
aliases: ["tellius_archive.html#/classes"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/classes.md"
system_entries: ["FE9-SYS-017", "FE9-SYS-173", "FE9-SYS-174", "FE9-SYS-175", "FE9-SYS-176", "FE9-SYS-177"]
system_reviewed: ["FE9-SYS-017", "FE9-SYS-173", "FE9-SYS-174", "FE9-SYS-175", "FE9-SYS-176", "FE9-SYS-177"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Classes

*The shared rules that give a unit movement, weapon access, caps, traits, and a battle model*

A class supplies the abilities shared by a kind of unit. Two characters in the same class may have different personal growths and skills, but they inherit the same movement rules, weapon access, stat caps, class traits, and model family. Changing class therefore changes what a character can do without changing who that character is.

## FE9-SYS-017 — Class definition system

<span id="fe9-sys-017"></span>

<div class="table-wrap">
<table><thead><tr><th>Capability</th><th>Effect</th></tr></thead><tbody><tr><td>Movement</td><td>How far the unit can travel and which movement rules apply</td></tr><tr><td>Weapon ranks</td><td>Which weapon families and rank levels the unit may use</td></tr><tr><td>Base values and caps</td><td>Class contribution to stats and the maximum effective values</td></tr><tr><td>Innate skills</td><td>Up to five traits present on every unit of the class</td></tr><tr><td>Linked class</td><td>Promotion partner or transformation counterpart</td></tr><tr><td>Graphics identity</td><td>Default battle-model and animation family, with possible character overrides</td></tr></tbody></table>
</div>

!!! info "Do not confuse class data with character data"
    A class does not contain Ike's identity, portrait, personal growth rates, current HP, or chapter inventory. Those come from [character](./characters.md), runtime/save, and [deployment](../formats/dispo-format.md) data.

## Example — Ranger to Hero

  Ike's character definition initially points to `JID_RANGER`. Ranger supplies his early movement, weapon permissions, caps, innate traits, and battle-model family. At promotion the linked class is `JID_HERO`. The character remains `PID_IKE`, while the new class changes shared capabilities and the applicable limits.

## Rules and lifecycle — promotion and transformation links

  Each class is a 0x64-byte record in [FE8Data.bin](../formats/fe8data.md). Its linked-class pointer is bidirectional: an unpromoted human class points to its promoted counterpart, and the promoted class points back. Of 115 records, 108 participate in linked same-species pairs. Laguz and related transformation tiers use the same structural relationship, but transformation is not a human promotion and does not imply the same stat changes — see [Laguz Transformation](./laguz-transformation.md) for the gauge that governs it.

!!! info "Promotion bonuses are record differences"
    Across human promotion pairs, movement increases by **+1** and the HP cap changes from **40 to 60**. Laguz, dragon, and bird transformation pairs also gain movement but retain the same HP cap, reflecting the different role of transformation. <span class="confidence confidence--confirmed">confirmed</span>

  The moment a promotion actually happens, more changes than the class pointer: the unit's class-granted skills swap to the new class's set, level resets to **1** and EXP resets to **0**, any accumulated fixed-growth progress (see [Characters](./characters.md)) is halved rather than carried over in full, and current HP is clamped back within the new class's range rather than left however it stood before promotion.

  Eligibility has its own ceiling, separate from ordinary leveling: most units simply level up to 20 and stop, but an unpromoted unit at level 10 or higher with a valid promotion partner can instead keep gaining EXP up to a second, higher ceiling reserved for reaching a promotion.

## FE9-SYS-173 through FE9-SYS-177 — Derived stats and promotion

<span id="fe9-sys-173"></span> **Derived-stat system.** Effective getters begin from definition/class base plus serialized personal and permanent gains, then apply the consumer's form, equipment, status, and skill modifiers before the documented cap/clamp layer. Movement, combat, rescue, growth, fog vision, AI, and UI call those getters rather than reading a second stored “final stat.” This ordering prevents a temporary bonus from being saved as permanent growth; individual modifier values remain owned by their source definitions.

<span id="fe9-sys-174"></span> **Promotion eligibility.** The generic check used by Master Seals and automatic class change rejects units with `SID_HIGHER` (already promoted), `SID_ANIMALIZE` (laguz transformation), or `SID_EVENTCC` (story-class-change ownership). It then requires a non-null linked promoted class and level 10 or higher. The EXP ceiling uses the same exclusions: an eligible unit may accumulate the extra level beyond level 20 that triggers automatic promotion, while an ineligible unit stops at the ordinary cap. `SID_EVENTCC` units do not pass this generic route; FE9-SYS-176's `UnitClassChange` handler is their explicit, separately gated path.

<span id="fe9-sys-175"></span> **Promotion execution.** `promote_unit_to_linked_class` first removes the old class's four skill-bit words, resolves the linked promoted class, installs its four skill-bit words, and clears the dependent skill bit when its prerequisite is absent. It then raises each of the eight mutable weapon-proficiency bytes to at least the promoted class's starting byte, resets level to 1 and EXP to 0, halves all eight fixed-growth accumulators, clears the promotion-pending state bit, and clamps current HP to the newly computed maximum. Before the live unit is changed, `compute_promotion_stat_gain_records` performs the same transition on a copy and emits ten displayed deltas in HP, Str, Mag, Skl, Spd, Lck, Def, Res, Move, Build order. Map-model replacement and visibility refresh happen after the state commit, so presentation never owns the result.

<span id="fe9-sys-176"></span> **Story promotion.** The event native `UnitClassChange` is the authored route. It resolves the numeric unit handle and only accepts a live unit carrying `SID_EVENTCC` (skill id `0x4D`, Ike's story-class-change marker); it therefore bypasses the generic level/Master Seal menu without becoming an unrestricted class setter. The watched route starts the blocking class-change process, while the skip route applies the same linked-class transition and map-model refresh immediately. Invalid or unmarked units return failure without changing state. Both routes converge on the same unit fields described above, which are then serialized normally with the party.

<span id="fe9-sys-177"></span> **Promotion weapon choice.** The class-change result checks nine weapon columns and offers only columns whose post-promotion proficiency is still below the selectable threshold. The picker labels are `MCA_SW`, `MCA_LA`, `MCA_AX`, `MCA_BW`, `MCA_FI`, `MCA_TH`, `MCA_WD`, `MCA_RD`, and `MCA_KN`; the chosen byte is stored in `pending_action_param8`. At cleanup, values 0–3 grant the sword/lance/axe/bow permission bits `0x24`–`0x27`, value 7 grants staff permission `0x28`, and value 8 grants light permission `0x22`, followed by proficiency/cap refresh. A cancelled or absent choice leaves the sentinel `0xFF` and grants nothing. The picker changes access state only: it creates no weapon and equips nothing.

## Weapon access

  Every class carries a nine-character **weapon-rank string**, one position per weapon family:

<div class="table-wrap">
<table class="tight"><thead><tr><th>0</th><th>1</th><th>2</th><th>3</th><th>4</th><th>5</th><th>6</th><th>7</th><th>8</th></tr></thead><tbody>
    <tr><td>Sword</td><td>Lance</td><td>Axe</td><td>Bow</td><td>Fire</td><td>Thunder</td><td>Wind</td><td>Staff <span>(weaker)</span></td><td>Light <span>(weakest)</span></td></tr>
  </tbody></table>
</div>

  A `-` forbids that family; E through S express proficiency; `*` grants use without a fixed rank. For example, Fighter enables only the Axe position, while elemental mage variants enable their corresponding Fire, Thunder, or Wind position.

## Innate skills and models

  Up to five class skill pointers grant [traits](./skills.md) to every unit of the class. Some are visible abilities; others are internal properties such as transformation or equipment permissions. The class also names a default animation ID — the Ranger's is `AID_LORD` — which picks the map model of every unit whose character has none, and [jobList.dbx](../formats/zdbx.md) picks the battle model by class, with character-specific overrides. <span class="confidence confidence--confirmed">engine + in game</span>

## Occult mastery is linked from the skill table

  A class's Occult result is not one of its five innate skills. Each mastery skill names the Occult scroll as its teaching item and lists the class IDs allowed to learn it; the scroll searches those lists using the unit's current class. Thus Hero maps to Aether while Swordmaster maps to Astra. Change this relationship with **Game Data → Classes → Occult scroll**, or edit the same restriction lists directly in the Skills tab. See [Skills](./skills.md) for the complete mapping and selection process.

## Other class fields

  Besides its IDs, a class record points at a description text key and three plain category words (`human`, `armor`, `fly`...) that the game turns into equipment and ability flags. <span class="confidence confidence--strong">engine</span>

<div class="table-wrap">
<table class="tight"><thead><tr><th>Field</th><th>Effect</th></tr></thead><tbody>
    <tr><td>Innate weapon</td><td>An item on laguz classes (the hawk king's beak). A unit that fights with its natural weapon has its item slots cleared and this weapon equipped; a class without one uses its linked class's <span class="badge confirmed">engine</span></td></tr>
    <tr><td>Build and weight</td><td>Added to the character's own build and weight <span class="badge confirmed">engine</span></td></tr>
    <tr><td>Skill capacity</td><td>How many capacity points of skills a unit of the class can hold: 0 for citizens, 15&amp;ndash;20 unpromoted, 25 promoted, 40 for the Black Knight and royal laguz <span class="badge confirmed">engine</span></td></tr>
    <tr><td>Vision</td><td>How far the unit sees in fog: 3 for most classes, 5 for thieves, assassins and beast laguz. A Torch adds 4 <span class="badge confirmed">engine</span></td></tr>
    <tr><td>Growth modifiers</td><td>Eight signed values added to the unit's growth rates, like a held item's (Swordmaster HP &amp;minus;5, Skl +5, Lck +5, Def &amp;minus;5) <span class="badge confirmed">engine</span></td></tr>
  </tbody></table>
</div>

## Stats and movement type

  After the movement byte, a class record holds its movement type — the column of terrain movement costs its units use (see [FE8Data.bin](../formats/fe8data.md)) — then eight base stats added to each unit's own, eight caps, and eight class growth rates (the Ranger's HP growth is 90). The game's loader skips the class Luck base and cap. <span class="confidence confidence--confirmed">engine</span>

## Interactions, edge cases, and limits

  Two class bytes are copied when the game loads but never read: one ranging from 1 to 4 (4 on transformed beasts, dragons and birds), and a movement category (foot, armour, cavalry, pegasus, wyvern, Valkyrie, beast, dragon, bird). Changing them has no effect. Weapon-rank strings may be shared by multiple records, so the pointer relationship matters independently of the visible nine characters.

The 0x64-byte record layout, all gameplay-facing class inputs above, linked-class behavior, ordered stat getters, weapon permissions, movement-type selection, and skill/model connections have implementation trails in [FE8Data.bin](../formats/fe8data.md), [Characters](./characters.md), [Skills](./skills.md), and [ZDBX & DBX](../formats/zdbx.md). Promotion eligibility, execution, the `UnitClassChange` story route, and the secondary-weapon picker are closed at executable level.

## Interactions and review boundary

All class systems are reviewed without a blocking research gap. The decoded class record, ordered effective-stat getters, caps, movement type/cost, weapon permissions, innate traits, model identity, promotion eligibility/execution, story route, and secondary-weapon picker define class ownership end to end. Unread class bytes remain explicitly non-behavioral. No new primary article is needed.
