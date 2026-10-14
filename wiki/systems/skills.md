---
id: "skills"
title: "Skills"
description: "How units acquire abilities and how map, combat, and movement code apply them"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Balance","Combat","Map Actions"]
aliases: ["tellius_archive.html#/skills"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skills.md"
---
# Skills

*How units acquire abilities and how map, combat, and movement code apply them*

A skill is an ability or trait attached to a unit. Some skills add a command to the map menu, such as [Steal](./skill-steal.md) or [Chant](./skill-chant.md). Others alter combat, such as [Vantage](./skill-vantage.md), [Sol](./skill-sol.md), or [Cancel](./skill-cancel.md). A third group is never shown to the player: the engine uses skill-like flags to mark properties such as being a boss, flying, transforming, or being permitted to equip a weapon type.

## The life of a skill

!!! info "Definition → ownership → runtime check → effect"
    A record in [FE8Data.bin](../formats/fe8data.md) defines a `SID_`. A character, class, or chapter deployment grants that SID. When a unit is created, its abilities are represented in runtime state. Map-action and combat functions test the relevant skill bit, optionally perform an activation roll, and then change an action, strike, damage result, movement state, or unit property.

## What counts as a skill

<div class="table-wrap">
<table><thead><tr><th>Family</th><th>What it changes</th><th>Examples</th></tr></thead><tbody><tr><td>Combat proc</td><td>Activates during a strike or exchange, usually with a chance</td><td>Sol, Luna, Cancel, Counter</td></tr><tr><td>Passive combat modifier</td><td>Changes a calculation or condition while owned</td><td>Wrath, Resolve, weapon permissions</td></tr><tr><td>Map command</td><td>Makes an action available for a selected unit</td><td>Steal, Chant, Unlock, Shoot</td></tr><tr><td>Movement capability</td><td>Changes where or when the unit can move</td><td>Canto, Pass, flying traits</td></tr><tr><td>Engine trait</td><td>Marks identity or behavior without appearing as a learnable skill</td><td>Boss, female, final boss, <a class="wl" href="../laguz-transformation/">transformed laguz</a></td></tr></tbody></table>
</div>

  The table contains 98 records. Fifty-seven have player-facing help keys; the other 41 are internal traits and permissions. Thus “skill record” is an engine category broader than “skill shown on the Skills screen.”

  Internal traits the engine tests by number include: the **boss** flag (37 bosses: an EXP bonus when defeated), the **final boss** flag (Ashnard: no EXP for fighting him), the **laguz class** flag (every laguz class), and **blessed armour** (the Black Knight's class and Ashnard's mounted class: only Ragnell, the Lion's claws, the dragon breaths and the kings' beaks damage them). Some player-facing skills have internal ids that don't match their English names: Parity (`SID_FAIRNESS`, Lucia and Rikard: no support, terrain or skill bonuses in that unit's battles), Insight (`SID_TELEGNOSIS`, +20 Hit), Paragon (`SID_ELITE`), Blossom (`SID_FRAC90`), Resolve (`SID_BLAVE`), Colossus (`SID_RUMBLE`), Mantle (`SID_GODDESSBLESS`), Lethality (`SID_ASSASSINATE`), Shove and Smite (`SID_TACKLE`/`SID_TACKLE2`), Roar (`SID_SNARL`), Blessing and Boon (`SID_SKYBLESSING`/`SID_EARTHBLESSING`). Charisma gives the units of a commander's group within 3 tiles +5 Hit and +5 Avoid (enemy and other armies only, never the player's); each enemy with Horror within 3 tiles gives −5 Hit and −5 Critical. <span class="confidence confidence--confirmed">confirmed</span>

## How a unit acquires skills

- **Personal:** a [character record](./characters.md) contains up to three `SID_` pointers.
- **Class-innate:** a [class record](./classes.md) contains up to five traits granted to every unit of that class.
- **Chapter-specific:** a [deployment record](../formats/dispo-format.md) can grant up to five more skills for that appearance.
- **Runtime:** the active unit consolidates these capabilities into state that native map and combat code can query.

## How the Occult scroll chooses a mastery skill

  The Occult scroll does not contain a hard-coded “Lord gives Aether” switch, and the class record does not store an Occult-skill field. The item-selection code scans the skill table for a visible skill whose teaching-item list names `IID_ESOTERIC`, then requires that skill's restriction list to contain either the unit's character ID or current class ID. Capacity and duplicate-skill checks still apply. This is why promoted Ike receives Aether: `SID_SUNMOON` names the Occult scroll and permits `JID_HERO`/`JID_HERO_G`. Swordmasters instead match Astra's `SID_STARTRICK` restriction list. <span class="confidence confidence--confirmed">engine + data</span>

<div class="table-wrap">
<table class="tight"><thead><tr><th>Occult result</th><th>Allowed classes in the retail data</th></tr></thead><tbody><tr><td>Aether</td><td>Hero variants</td></tr><tr><td>Astra</td><td>Swordmaster variants</td></tr><tr><td>Sol</td><td>Paladin variants, Valkyrie and Titania's special class</td></tr><tr><td>Luna</td><td>Halberdier variants and General</td></tr><tr><td>Lethality</td><td>Assassin variants</td></tr><tr><td>Deadeye</td><td>Sniper</td></tr><tr><td>Colossus</td><td>Warrior and Berserker</td></tr><tr><td>Stun</td><td>Falcon Knight and Dragonmaster variants</td></tr><tr><td>Flare</td><td>Sage and Bishop variants</td></tr><tr><td>Roar</td><td>Beast laguz</td></tr><tr><td>Vortex</td><td>Raven classes</td></tr><tr><td>Boon</td><td>Dragon classes</td></tr><tr><td>Cancel</td><td>Hawk classes</td></tr><tr><td>Blessing</td><td>Heron classes</td></tr></tbody></table>
</div>

  Every visible mastery costs 20 capacity. The Game Data editor's **Classes → Occult scroll** selector changes these skill restriction lists, so it changes what that class learns without incorrectly adding the mastery as an innate class skill. The Skills tab exposes the same underlying teaching-item and restriction fields for advanced editing.

!!! info "Do not confuse three different numbers"
    The skill's **table index** selects its runtime bit. `param0` is the skill's **icon number**, 1–46 on the 51 skills that have one. `param1` is its **capacity cost**. None of them is a second skill ID.

## Example — Sol from definition to healing

1. The skill table defines `SID_SUNTRICK` at index 47 and links to its display/help keys.
2. A character or class grants that SID, so the created unit owns runtime skill bit 47.
3. During combat, the relevant path tests bit 47 and applies the shared chance mechanism.
4. If Sol activates and the strike deals 12 final damage, the attacker recovers 12 HP, capped at maximum HP.

## Where each part is stored

<div class="table-wrap">
<table><thead><tr><th>Part</th><th>Location</th></tr></thead><tbody><tr><td>Definition, SID, restrictions, parameters</td><td><a class="wl" href="../../formats/fe8data/"><code>FE8Data.bin</code></a> skill table at <code>0xE398</code></td></tr><tr><td>Short and long help keys</td><td>Offsets <code>0x0C</code> and <code>0x10</code> of the 0x28-byte record</td></tr><tr><td>Scroll that teaches it</td><td>Offset <code>0x20</code>: a one-item list (<code>IID_COUNTER</code> for Counter; every class mastery skill names the Occult scroll, <code>IID_ESOTERIC</code>)</td></tr><tr><td>Who may have it</td><td>Offset <code>0x24</code>: a list of classes or characters, <code>0x1C</code> entries long</td></tr><tr><td>Icon</td><td>Offset <code>0x19</code>: cell <em>n</em> − 1 of the second image of <code>window/icon.tpl</code></td></tr><tr><td>Capacity cost</td><td>Offset <code>0x1A</code></td></tr><tr><td>Trigger effect</td><td>Offset <code>0x14</code>: an <code>EID_</code> name</td></tr><tr><td>Displayed help text</td><td><code>system.cmp</code> → pack entry <code>mess/common.m</code>, using keys such as <code>Mess_Help_skill_Counter</code></td></tr><tr><td>Character-granted skills</td><td>Up to three <code>SID_</code> pointers in the character record</td></tr><tr><td>Class-granted skills</td><td>Up to five innate-skill pointers in the class record</td></tr><tr><td>Chapter-specific bonus skills</td><td><code>skill0</code>&amp;ndash;<code>skill4</code> in a <a class="wl" href="../../formats/dispo-format/">deployment record</a></td></tr></tbody></table>
</div>

## How the game checks a skill

  Native code passes the unit's runtime skill state and a raw table position to one shared bit-test function. If the bit is absent, the effect path stops. Chance-bearing skills then use the same random-number generator as hit and critical checks; guaranteed traits proceed without that roll. The caller determines *when* the check occurs: Vantage is checked while arranging exchange order, Cancel before a counterattack is scheduled, Sol after damage is known, and Steal while building the map-action menu.

  Twenty-two records carry a restriction list naming the classes or characters the skill belongs to: Sol the paladins, Valkyrie and Titania; Luna halberdiers and generals; Astra swordmasters; Lethality assassins; Deadeye snipers; Colossus warriors and berserkers; Stun falcon knights and dragonmasters; Roar beast laguz; Aether Ike's Hero classes; and single characters for the personal skills (Ulki, Janaff, Tanith, Sothe, Lehran). Fifty-one records carry three parameter bytes. `param0` is the icon: the Skills screen draws icon *n* from the *n*-th 32×32 cell of the skill icon sheet (see [Graphics & Images](./graphics-system.md)), and the nonzero values are exactly 1–46. A skill whose icon is 0 has none and never appears in the list of skills a unit can learn. `param1` is the capacity cost: the same screen prints it and greys the skill out when it exceeds the class's skill capacity minus what the unit's skills already use (Paragon 15, Counter 10, Nihil 5). `param2` is 1 on exactly the 42 skills a scroll teaches; the game never reads it. <span class="confidence confidence--confirmed">icon and capacity</span>

  Twenty-three skills also name the visual effect played when they trigger: Sol plays `EID_SP_SUN`, Counter `EID_COUNTER`, Vantage `EID_MACHIBUSE` (“ambush”), and the triangle attack `EID_TRIATTACK`. <span class="confidence confidence--confirmed">confirmed</span>

## Special family — Chant

  The eight records after base `SID_CHANT` correspond to HP, Strength, Magic, Skill, Speed, Luck, Defense, and Resistance. They are not granted directly and contain no separate stat field; their consecutive table positions encode the selected stat. See [Chant](./skill-chant.md).

!!! info "Skills with a mapped native effect"
    These table positions have a corresponding effect in native combat code:

    <div class="table-wrap">
    <table class="tight"><thead><tr><th>Skill</th><th>Real effect</th></tr></thead><tbody>
          <tr><td><a class="wl" href="../skill-sol/">Sol</a></td><td>Self-heal equal to the damage just dealt, applied at the very end of the damage pipeline</td></tr>
          <tr><td><a class="wl" href="../skill-luna/">Luna</a></td><td>Halves the target's effective Defense/Resistance directly inside the damage formula</td></tr>
          <tr><td><a class="wl" href="../skill-astra/">Astra</a></td><td>Turns one strike into five strikes at half damage (rounded up); hit and critical still rolled per strike</td></tr>
          <tr><td><a class="wl" href="../skill-aether/">Aether</a></td><td>Combines Sol's and Luna's effects in one activation</td></tr>
          <tr><td><a class="wl" href="../skill-counter/">Counter</a></td><td>Checked on the defending unit and can grant a bonus retaliation strike</td></tr>
          <tr><td><a class="wl" href="../skill-corrosion/">Corrosion</a></td><td>Reduces the target's equipped weapon durability</td></tr>
          <tr><td><a class="wl" href="../skill-cancel/">Cancel</a></td><td>Skips the defender's counter-attack step</td></tr>
          <tr><td><a class="wl" href="../skill-miracle/">Pray</a></td><td>On an otherwise lethal hit, reduces damage to a survivable amount</td></tr>
          <tr><td><a class="wl" href="../skill-wing-guard/">Wing Guard</a></td><td>Zeroes incoming damage on its confirmed block path</td></tr>
          <tr><td><a class="wl" href="../skill-vantage/">Vantage</a></td><td>Reverses the normal attacker-then-defender exchange order</td></tr>
          <tr><td><a class="wl" href="../skill-wrath/">Wrath</a></td><td>+50 critical rate at half HP or less; no activation roll</td></tr>
          <tr><td><a class="wl" href="../skill-deadeye/">Deadeye</a> (Snipe)</td><td>Doubles final hit; a hit can put the target to sleep for 5 phases (Skill / 2, bosses immune)</td></tr>
        </tbody></table>
    </div>

        Goddess's Blessing reaches the same full-damage-block result as Wing Guard without calling the percentage-roll function, making that protection guaranteed on its native path. <span class="confidence confidence--confirmed">confirmed</span>

## Detailed skill articles

  [Sol](./skill-sol.md) · [Luna](./skill-luna.md) · [Aether](./skill-aether.md) · [Counter](./skill-counter.md) · [Corrosion](./skill-corrosion.md) · [Cancel](./skill-cancel.md) · [Miracle / Pray](./skill-miracle.md) · [Wing Guard](./skill-wing-guard.md) · [Vantage](./skill-vantage.md) · [Steal](./skill-steal.md) · [Chant](./skill-chant.md) · [Canto](./skill-canto.md)

## Open questions

  Several player-facing skills have known identities and parameters but no fully mapped native effect. Activation chances are documented per skill where known.
