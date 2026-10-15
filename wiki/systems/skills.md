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
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skills.md"
system_entries: ["FE9-SYS-144", "FE9-SYS-145", "FE9-SYS-146", "FE9-SYS-147", "FE9-SYS-148", "FE9-SYS-179", "FE9-SYS-180", "FE9-SYS-181", "FE9-SYS-236", "FE9-SYS-237", "FE9-SYS-238", "FE9-SYS-239", "FE9-SYS-240", "FE9-SYS-241", "FE9-SYS-242", "FE9-SYS-243", "FE9-SYS-244", "FE9-SYS-245", "FE9-SYS-246", "FE9-SYS-247", "FE9-SYS-248", "FE9-SYS-249", "FE9-SYS-250"]
system_reviewed: ["FE9-SYS-144", "FE9-SYS-145", "FE9-SYS-146", "FE9-SYS-147", "FE9-SYS-148", "FE9-SYS-179", "FE9-SYS-180", "FE9-SYS-181", "FE9-SYS-236", "FE9-SYS-237", "FE9-SYS-238", "FE9-SYS-239", "FE9-SYS-240", "FE9-SYS-241", "FE9-SYS-242", "FE9-SYS-243", "FE9-SYS-244", "FE9-SYS-245", "FE9-SYS-246", "FE9-SYS-247", "FE9-SYS-248", "FE9-SYS-249", "FE9-SYS-250"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
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

## FE9-SYS-179 — Skill capacity

<span id="fe9-sys-179"></span> The current class supplies a capacity ceiling and each visible learned skill supplies a cost in `param1`. The Skills screen totals the unit's applicable learned costs, compares the candidate against the remaining space, and rejects a teaching action that would exceed the ceiling. Changing class therefore changes available space without changing the cost stored on each skill. Internal traits and class-granted behavior must not be assumed to behave like removable learned skills merely because they share the skill table and runtime bitset.

For example, a promoted class with capacity 25 can hold Paragon (15) and Counter (10) exactly, but cannot add Nihil (5) until capacity is freed. The calculation is integer accounting, not an activation rule: a skill consumes its assigned capacity whether or not its battle condition triggers.

## FE9-SYS-180 — Scroll learning and removal

<span id="fe9-sys-180"></span> A learnable scroll points indirectly to its skill: the skill record names the teaching item, carries an icon so it can appear in the learning UI, and can restrict legal recipients by character or class. Selection checks that relationship, recipient restrictions, duplicate ownership, and remaining capacity before committing the skill to mutable unit state and consuming the item. The Occult scroll uses the same search but can match several mastery records, so the current class selects the result.

Removal operates only on mutable learned entries exposed by the Skills UI. Personal, class-innate, deployment, form, and hidden engine-trait sources remain because they are recomputed ownership rather than removable list entries. Removing a learned skill clears and compacts that entry, immediately releases its capacity, and does not recreate the consumed teaching item. Invalid edited ownership is filtered through the same source checks instead of turning an innate trait into a refundable scroll.

## FE9-SYS-181 — Occult and mastery assignment

<span id="fe9-sys-181"></span> Occult assignment is data-driven. The scroll is `IID_ESOTERIC`; each mastery skill names that item and lists the character or class IDs allowed to receive it. The selection code scans visible candidates and accepts the record whose restriction contains the unit's current identity. Capacity and duplicate checks then apply normally. This explains both the common mapping—Hero to Aether, Swordmaster to Astra, Paladin to Sol—and the correct way to mod it: edit the mastery restriction list, not the class's innate-skill slots.

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

## FE9-SYS-144 — Activation pipeline

<span id="fe9-sys-144"></span> Ownership is consolidated from character, class, deployment, and runtime sources into a bitset indexed by raw skill-table position. A subsystem asks for one bit at the stage it owns. Passive traits proceed immediately; chance-bearing effects consume the shared RNG; successful checks append or alter combat-log work and may request an `EID_` presentation. The caller—not the skill record—defines whether the check occurs during forecast adjustment, exchange construction, strike damage, post-hit consequences, or map command building.

Caller ownership is the priority rule: exchange-order skills run while the log is built, strike modifiers when that strike resolves, lethal protection before death commits, and post-damage healing/reflection after final damage exists. Suppression is tested at the relevant caller before its roll. There is no global activation pass whose missing total order must be reconstructed.

## FE9-SYS-145 — Offensive proc skills

<span id="fe9-sys-145"></span> Offensive procs modify different layers: Astra/Continue-style paths add strike work, Luna halves effective defense, Sol heals from final damage, Aether combines Luna and Sol, Lethality replaces the lethal outcome, and Stun/Roar/Vortex paths add status or map-action behavior. Each caller checks ownership, suppression/immunity, and its own chance before mutating that layer. Simultaneous effects therefore follow exchange construction → strike formula → damage → status/post-hit rather than a generic competing-proc priority.

## FE9-SYS-146 — Defensive and reactive skills

<span id="fe9-sys-146"></span> Reactive skills operate at ordered checkpoints. Vantage reverses the opening exchange; Cancel marks the defender's counter step to be skipped; Counter can append a retaliation exchange; Wing Guard/Goddess Blessing can replace incoming damage with zero; Miracle clamps an otherwise lethal result to survival before death. Later checkpoints observe the work left by earlier ones, so a removed counter cannot trigger its strike and zero/nonlethal damage reaches post-hit handling without premature death.

## FE9-SYS-147 — Conditional passive skills

<span id="fe9-sys-147"></span> Passive checks alter the getter/consumer that owns their formula: Gamble halves Hit and doubles Critical, Deadeye doubles Hit, Insight adds Hit, Parity suppresses exchange modifiers, and Resolve/Wrath read current HP at their stat/critical sites. Shade/Provoke alter AI desirability after legality. The owning getter recomputes on demand, so HP/status changes invalidate no separate cached passive state.

## FE9-SYS-148 — Post-hit healing and reflection

<span id="fe9-sys-148"></span> These effects require ordered resolved work. Protection first produces final damage; Miracle handles its lethal boundary; HP is applied; then Sol/Aether heal the attacker by final damage dealt up to maximum HP, while Counter's separately scheduled exchange resolves through the ordinary strike path. Weapon drain/property handlers consume finalized damage at their registered consequence stage. Death is committed after survival/protection for that hit, while healing cannot revive a target already resolved dead.

## FE9-SYS-236 through FE9-SYS-250 — Runtime skill systems

<span id="fe9-sys-236"></span> **Ownership bitset.** Runtime skill state is indexed by raw position in the 98-record skill table and fits within a 128-bit field. Character, class, deployment, learned, and engine-trait sources consolidate into that queryable representation. Native callers test a numeric bit; renumbering table records therefore changes behavior even if their `SID_` labels remain readable.

<span id="fe9-sys-237"></span> **Availability and restrictions.** A visible learned skill requires an icon/teaching relationship, recipient restriction match, no duplicate, and available class capacity. Personal, class-innate, deployment-only, form, item-granted, and hidden engine traits enter the runtime bitset from their own source and are not removable learned entries. Consumers may additionally require current form/equipment; failing that condition suppresses use without deleting ownership.

<span id="fe9-sys-238"></span> **Activation chance.** There is no universal “activate all skills” pass. Each caller tests its raw-index bit when its stage is reached, applies suppression/current-state gates, then performs that rule's shared-RNG roll if chance-bearing; deterministic traits make no roll. A failed or never-reached caller consumes no proc roll. Successful activation changes work at that stage and may append a message or `EID_`, making RNG order identical to executed caller order.

<span id="fe9-sys-239"></span> **Steal.** [Steal](./skill-steal.md) requires `SID_STEAL`, a strictly faster actor, free carrying capacity, an adjacent hostile, and a carryable non-equipped/non-protected item. Commit moves that instance atomically as action 17. AI scans victim slots 0–7 and `TBL_STEALITEMS`, choosing the lowest list index and first equal candidate; full capacity prevents registration rather than dropping an item.

<span id="fe9-sys-240"></span> **Chant.** [Chant](./skill-chant.md) scans the `SID_CHANT*` family and matching validator, considers compatible acted allies in the surrounding 3×3 neighborhood, and registers action 18 for the selected target/pattern. Resolution clears only eligible acted state covered by that variant, plays presentation, and commits the singer. AI invokes the same validator/action boundary before ordinary attack fallback.

<span id="fe9-sys-241"></span> **Canto.** [Canto](./skill-canto.md) is queried after the first command commits. When actor capability and action type permit continuation, the executor subtracts movement spent and reopens ordinary search from the endpoint with restricted commands. Cancel cannot undo the first action; interruption, death, or forced scene change terminates continuation and finalizes acted state. Otherwise the second endpoint closes the action normally.

<span id="fe9-sys-242"></span> **Shove and Smite.** Actions 19 and 20 validate actor/target physical constraints and direction, then every intervening/destination tile for bounds, occupancy, terrain, links, and objects; Smite repeats displacement for a second tile. `SID_IMPREGNABLE` can resist through its Strength-percent roll and fliers resist the ordinary push path. Landing on map-object kind 9 enters the pit action. Failure before displacement leaves occupancy unchanged.

<span id="fe9-sys-243"></span> **Blossom and Paragon.** Paragon scales awarded combat EXP at the EXP stage. Blossom (`Frac90`) changes growth processing and its documented growth/threshold behavior rather than merely editing displayed stats. Their effects occur in different stages and must not be combined into one generic multiplier; [Level-Up Growth](./level-up-growth.md) and [Combat Resolution](./combat-mechanics.md) own the formulas.

<span id="fe9-sys-244"></span> **Tempest and Serenity.** These skills change the amplitude applied after biorhythm's phase/band selection. They do not advance the phase counter or change its saved ownership. Retail stat consumers still read zero-valued positions, so amplitude changes the computed row without producing the commonly assumed Hit/Avoid bonus in this executable path.

<span id="fe9-sys-245"></span> **Parity and Nihil.** Parity establishes an exchange context in which terrain/support and applicable derived modifiers are skipped symmetrically. Nihil is tested by individual hostile proc callers before their roll/effect. Both are temporary gates: neither clears ownership, and forecast/resolution use the same exchange context. Effects whose callers do not opt into the relevant gate remain unaffected.

<span id="fe9-sys-246"></span> **Resolve and Wrath.** Their consumers test current HP at or below half maximum. Resolve feeds effective-stat getters; Wrath feeds the critical path/forecast flag. Both recompute after HP changes and combine at their separate formula stages rather than replacing one another. Regional presentation or balance data may vary, but ownership, threshold boundary, and recomputation order are explicit.

<span id="fe9-sys-247"></span> **Provoke and Shade.** These contribute desirability modifiers after AI attack legality and candidate enumeration; they do not change army relationship, visibility, reachability, or whether an attack is possible. Their configured weights enter the ordinary attack scorer, and equal final scores retain that scorer's deterministic candidate order. The numeric weights are AI balance data rather than a separate skill scheduler.

<span id="fe9-sys-248"></span> **Charisma and Horror.** Charisma grants units in an applicable non-player commander's group within three tiles +5 Hit and +5 Avoid. Each nearby hostile Horror source applies −5 Hit and −5 Critical. The local scan and side-specific ownership distinguish these auras from ordinary support rank.

<span id="fe9-sys-249"></span> **Blessing, Boon, and laguz support skills.** These register with their phase-adjacent skill handler, which checks owner form/state and scans targets using the effect's configured range and allegiance predicate before delegating healing or status removal. The handler commits consequences before presentation and before the phase scheduler advances; AI does not choose them as map commands. Individual ranges, amounts, cure masks, and effect resources are skill data consumed by that common path.

<span id="fe9-sys-250"></span> **Engine-trait skills.** Hidden table entries mark boss/final-boss identity, promoted class, laguz and transformed form, flight, blessed armor, sex, thief capability, weapon permissions, and other native properties. Their raw indices are queried like skills even when they have no icon, help text, scroll, capacity cost, or activation roll.

## Special family — Chant

  The eight records after base `SID_CHANT` correspond to HP, Strength, Magic, Skill, Speed, Luck, Defense, and Resistance. They are not granted directly and contain no separate stat field; their consecutive table positions encode the selected stat. See [Chant](./skill-chant.md).

!!! info "Skills with a mapped native effect"
    These table positions have a corresponding effect in native combat code:

    <div class="table-wrap">
    <table class="tight"><thead><tr><th>Skill</th><th>Real effect</th></tr></thead><tbody>
          <tr><td><a class="wl" href="../skill-sol/">Sol</a></td><td>Self-heal equal to the damage just dealt, applied at the very end of the damage pipeline</td></tr>
          <tr><td><a class="wl" href="../skill-luna/">Luna</a></td><td>Halves the target's effective Defense/Resistance directly inside the damage formula</td></tr>
          <tr><td>Astra</td><td>(effect not independently traced beyond the strike-count/damage pipeline it hooks into)</td></tr>
          <tr><td><a class="wl" href="../skill-aether/">Aether</a></td><td>Combines Sol's and Luna's effects in one activation</td></tr>
          <tr><td><a class="wl" href="../skill-counter/">Counter</a></td><td>Checked on the defending unit and can grant a bonus retaliation strike</td></tr>
          <tr><td><a class="wl" href="../skill-corrosion/">Corrosion</a></td><td>Reduces the target's equipped weapon durability</td></tr>
          <tr><td><a class="wl" href="../skill-cancel/">Cancel</a></td><td>Skips the defender's counter-attack step</td></tr>
          <tr><td><a class="wl" href="../skill-miracle/">Pray</a></td><td>On an otherwise lethal hit, reduces damage to a survivable amount</td></tr>
          <tr><td><a class="wl" href="../skill-wing-guard/">Wing Guard</a></td><td>Zeroes incoming damage on its confirmed block path</td></tr>
          <tr><td><a class="wl" href="../skill-vantage/">Vantage</a></td><td>Reverses the normal attacker-then-defender exchange order</td></tr>
          <tr><td>Wrath</td><td>(bit position confirmed; specific effect not independently traced)</td></tr>
          <tr><td>Snipe</td><td>(bit position confirmed; specific effect not independently traced)</td></tr>
        </tbody></table>
    </div>

        Goddess's Blessing reaches the same full-damage-block result as Wing Guard without calling the percentage-roll function, making that protection guaranteed on its native path. <span class="confidence confidence--confirmed">confirmed</span>

## Detailed skill articles

  [Sol](./skill-sol.md) · [Luna](./skill-luna.md) · [Aether](./skill-aether.md) · [Counter](./skill-counter.md) · [Corrosion](./skill-corrosion.md) · [Cancel](./skill-cancel.md) · [Miracle / Pray](./skill-miracle.md) · [Wing Guard](./skill-wing-guard.md) · [Vantage](./skill-vantage.md) · [Steal](./skill-steal.md) · [Chant](./skill-chant.md) · [Canto](./skill-canto.md)

## Interactions and review boundary

All skill systems on this page are reviewed without a blocking research gap. Ownership sources, capacity/learning, caller-owned activation stages, RNG/suppression, action commands, AI desirability modifiers, phase-adjacent laguz support handlers, and consequence ordering define the lifecycle. Per-skill coefficients, ranges, amounts, cure masks, and presentation resources are data consumed by those owners and remain appropriate for the detailed skill references. No new primary article is required.
