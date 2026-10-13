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
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/classes.md"
---
# Classes

*The shared rules that give a unit movement, weapon access, caps, traits, and a battle model*

A class supplies the abilities shared by a kind of unit. Two characters in the same class may have different personal growths and skills, but they inherit the same movement rules, weapon access, stat caps, class traits, and model family. Changing class therefore changes what a character can do without changing who that character is.

## What a class contributes

<div class="table-wrap">
<table><thead><tr><th>Capability</th><th>Effect</th></tr></thead><tbody><tr><td>Movement</td><td>How far the unit can travel and which movement rules apply</td></tr><tr><td>Weapon ranks</td><td>Which weapon families and rank levels the unit may use</td></tr><tr><td>Base values and caps</td><td>Class contribution to stats and the maximum effective values</td></tr><tr><td>Innate skills</td><td>Up to five traits present on every unit of the class</td></tr><tr><td>Linked class</td><td>Promotion partner or transformation counterpart</td></tr><tr><td>Graphics identity</td><td>Default battle-model and animation family, with possible character overrides</td></tr></tbody></table>
</div>

!!! info "Do not confuse class data with character data"
    A class does not contain Ike's identity, portrait, personal growth rates, current HP, or chapter inventory. Those come from [character](./characters.md), runtime/save, and [deployment](../formats/dispo-format.md) data.

## Example — Ranger to Hero

  Ike's character definition initially points to `JID_RANGER`. Ranger supplies his early movement, weapon permissions, caps, innate traits, and battle-model family. At promotion the linked class is `JID_HERO`. The character remains `PID_IKE`, while the new class changes shared capabilities and the applicable limits.

## Promotion and transformation links

  Each class is a 0x64-byte record in [FE8Data.bin](../formats/fe8data.md). Its linked-class pointer is bidirectional: an unpromoted human class points to its promoted counterpart, and the promoted class points back. Of 115 records, 108 participate in linked same-species pairs. Laguz and related transformation tiers use the same structural relationship, but transformation is not a human promotion and does not imply the same stat changes — see [Laguz Transformation](./laguz-transformation.md) for the gauge that governs it.

!!! info "Promotion bonuses are record differences"
    Across human promotion pairs, movement increases by **+1** and the HP cap changes from **40 to 60**. Laguz, dragon, and bird transformation pairs also gain movement but retain the same HP cap, reflecting the different role of transformation. <span class="confidence confidence--confirmed">confirmed</span>

  The moment a promotion actually happens, more changes than the class pointer: the unit's class-granted skills swap to the new class's set, level resets to **1** and EXP resets to **0**, any accumulated fixed-growth progress (see [Characters](./characters.md)) is halved rather than carried over in full, and current HP is clamped back within the new class's range rather than left however it stood before promotion.

  Eligibility has its own ceiling, separate from ordinary leveling: most units simply level up to 20 and stop, but an unpromoted unit at level 10 or higher with a valid promotion partner can instead keep gaining EXP up to a second, higher ceiling reserved for reaching a promotion. Reaching it starts the class-change scene, the same one a Master Seal plays.

  Both routes ask the same question <span class="confidence confidence--confirmed">confirmed</span>: the unit is not promoted yet, is not a laguz, is at least level 10, its class has a promoted class, and its class does **not** carry the hidden skill `SID_EVENTCC` ("event class change"). Two classes carry it: **Ranger** (Ike) and **Thief** (Volke and Sothe). That is why Ike and Volke stop at level 20 with 0 EXP and cannot use a Master Seal. Ike promotes only through the story: the script function `UnitClassChange` promotes a unit only when it *does* have `SID_EVENTCC`. Because the skill belongs to the class and not to the character, any unit placed in those classes behaves the same way.

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

## Open questions

  Two class bytes are copied when the game loads but never read: one ranging from 1 to 4 (4 on transformed beasts, dragons and birds), and a movement category (foot, armour, cavalry, pegasus, wyvern, Valkyrie, beast, dragon, bird). Changing them has no effect. Weapon-rank strings may be shared by multiple records, so the pointer relationship matters independently of the visible nine characters.
