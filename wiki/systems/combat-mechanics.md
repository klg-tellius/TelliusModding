---
id: "combat-mechanics"
title: "Combat Resolution"
description: "How an exchange of blows and its experience award are calculated"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Balance","Combat"]
aliases: ["tellius_archive.html#/combat-mechanics"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/combat-mechanics.md"
system_entries: ["FE9-SYS-117", "FE9-SYS-118", "FE9-SYS-119", "FE9-SYS-120", "FE9-SYS-121", "FE9-SYS-122", "FE9-SYS-123", "FE9-SYS-124", "FE9-SYS-125", "FE9-SYS-126", "FE9-SYS-127", "FE9-SYS-128", "FE9-SYS-129", "FE9-SYS-130", "FE9-SYS-131", "FE9-SYS-132", "FE9-SYS-133", "FE9-SYS-134", "FE9-SYS-135", "FE9-SYS-136", "FE9-SYS-137", "FE9-SYS-138", "FE9-SYS-139", "FE9-SYS-140", "FE9-SYS-141", "FE9-SYS-142", "FE9-SYS-143", "FE9-SYS-144", "FE9-SYS-145", "FE9-SYS-146", "FE9-SYS-147", "FE9-SYS-148", "FE9-SYS-149", "FE9-SYS-150", "FE9-SYS-151", "FE9-SYS-152", "FE9-SYS-153", "FE9-SYS-154"]
system_reviewed: ["FE9-SYS-117", "FE9-SYS-118", "FE9-SYS-119", "FE9-SYS-120", "FE9-SYS-121", "FE9-SYS-122", "FE9-SYS-123", "FE9-SYS-125", "FE9-SYS-127", "FE9-SYS-128", "FE9-SYS-129", "FE9-SYS-130", "FE9-SYS-131", "FE9-SYS-132", "FE9-SYS-133", "FE9-SYS-134", "FE9-SYS-135", "FE9-SYS-136", "FE9-SYS-137", "FE9-SYS-138", "FE9-SYS-139", "FE9-SYS-140", "FE9-SYS-141", "FE9-SYS-142", "FE9-SYS-143", "FE9-SYS-149", "FE9-SYS-150", "FE9-SYS-151", "FE9-SYS-152", "FE9-SYS-153", "FE9-SYS-154"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Combat Resolution

*How an exchange of blows and its experience award are calculated*

A battle between two units is a sequence of **exchanges**, and each exchange can itself contain more than one **strike** — two separate places extra hits can come from, confirmed to sit in structurally distinct parts of the combat pipeline rather than one conflated mechanism.

## Mental model

!!! info "Mental model: order, quantity, then outcome"
    Combat answers three questions in order: **who acts next** (exchange order and counters), **how many strikes that action contains** (ordinary, Brave, or skill-added strikes), and **what each strike does** (hit, critical, effectiveness, damage, and post-hit effects). Keeping those layers separate prevents “double attack,” “Brave,” and “critical” from being treated as versions of the same mechanic.

## FE9-SYS-117 — Attack Speed

<span id="fe9-sys-117"></span> Attack Speed is the unit's Speed after uncompensated weapon weight: `AS = Speed - max(0, weapon Weight - Strength)`. The equipped instance can modify effective stats, and forged weight changes the weapon term. AS feeds Avoid and the follow-up scheduler; a side at least 4 AS faster receives another exchange if still able. It is recalculated for forecast and resolution rather than saved as independent state.

For example, 12 Speed and 8 Strength with a weight-11 weapon gives AS 9. Raising Strength to 11 removes the penalty and restores AS 12. The calculation never grants bonus AS for Strength exceeding weight. Switching weapons can therefore change both damage and strike count before combat begins.

## FE9-SYS-118–119 — Weapon triangles

<span id="fe9-sys-118"></span> The physical table is sword over axe, axe over lance, and lance over sword. Advantage adds 10 Hit and 1 Attack; disadvantage subtracts the same values. <span id="fe9-sys-119"></span> The magic table is Fire over Wind, Wind over Thunder, and Thunder over Fire, using the same modifiers. Light/Staff and other item types are outside these twelve directed rows.

`build_strike_forecast_log` walks a signed four-byte row table containing attacker type, defender type, Hit, and Attack. A reaver property reverses the signs. The result is stored on each combat actor and is already reflected in forecast and later strikes. Triangle Attack is a separate skill/event mechanic despite the similar English phrase.

## FE9-SYS-120 — Weapon rank and access

<span id="fe9-sys-120"></span> Legality requires an inventory instance with uses, an item type the unit's class/skills permit, and enough WEXP for the definition's rank. Thresholds are E 1, D 31, C 71, B 121, A 181, and S 251. Units store WEXP separately for sword, lance, axe, bow, fire, thunder, wind, and staff. Promotion can add a weapon type and initialize/refresh its access without replacing progress in existing types.

Rank is only one gate. Character/story locks, Silence, transformed laguz weapon rules, special properties, and scripted equipment can still reject an item. The UI, AI, forecast, counter selection, and final resolver call the same composed legality predicates; displaying an equipped bit or sufficient WEXP cannot override another restriction. Named item, class, status, and story exceptions remain inputs owned by those systems.

## FE9-SYS-121 — Range

<span id="fe9-sys-121"></span> Every item definition stores minimum and maximum Manhattan range. Ordinary weapons use those bytes directly: a 1-range sword cannot target distance 2, and a 2-range-only weapon cannot hit adjacent. A maximum value of 255 selects dynamic `Magic / 2`, clamped to 5–15, for configured long-range magic/staff behavior. Range is measured from the committed attack tile, not necessarily the unit's starting tile.

The same interval drives player target lists, defender counters, AI candidate masks, threat overlays, forecast, and resolution. Ballistae add placed-object/operator rules around their weapon range; staves add effect-specific targets and destination legality. Those overlays delegate to their effect owners without changing the common distance predicate.

## FE9-SYS-122 — Effectiveness

<span id="fe9-sys-122"></span> A weapon/item supplies up to two category words and the target class supplies its categories. A matching bit doubles weapon Might before defense rather than doubling final damage. Examples include flying, beast, dragon, armor, knight, and laguz. `boss` and `final` test runtime traits directly, although no vanilla weapon uses those two categories.

Full Guard's `sfxseal` suppresses all effectiveness; related properties remove only flying or laguz matches. Because the multiplier applies to Might, Strength/Magic, triangle, defense, and later critical multiplication retain their own ordering. Forecast and actual combat share this branch.

## FE9-SYS-123 — Blessed armor

<span id="fe9-sys-123"></span> The Black Knight's and mounted Ashnard's classes carry the blessed-armor trait. Against it, a weapon without `weakA` has Attack forced to zero. Vanilla allowed weapons include Ragnell, lion claws, dragon breaths, and the kings' beaks. This is a late protection override rather than enormous Defense, so changing stats cannot bypass it.

The same protection prevents Counter from reflecting damage onto these actors. A modded weapon intended to work must carry the property; merely copying Ragnell's might, model, or name is insufficient. Conversely, adding `weakA` broadly changes access to this protection wherever the class trait is present.

## FE9-SYS-125 — Terrain combat bonuses

<span id="fe9-sys-125"></span> The standing tile's terrain type selects a stats block containing Avoid, Defense, and Resistance. Forecast copies those values into the combat actor and adds them to the relevant defensive calculations. Confirmed examples include Thicket 10 Avoid/1 Defense, Talisman 3 Defense/3 Resistance, and Heal/Trail 10 Avoid/1 Defense. The terrain name shown in UI resolves through the same runtime type grid.

Terrain bonuses belong to the unit's committed battle tile. Movement preview may inspect candidate tiles, but combat must use the final position. Parity suppresses the defined terrain/support/skill contributions for the affected battle. Changing only the visible model or texture does not change these bonuses; edit the tile's terrain type or its shared `TerrainData` stats.

## FE9-SYS-127 — Status and temporary-stat modifiers

<span id="fe9-sys-127"></span> Combat reads temporary Resistance, Resolve/Wrath conditions, and other stat modifiers through the effective-unit getters, while Silence, Sleep, Berserk, Poison, and related state contribute action-legality or phase consequences through the shared status owner. Forecast and final resolution query the same current state; application, duration, replacement, and expiry are documented in [Status Effects & Temporary Bonuses](./status-effects.md).

## FE9-SYS-128–129 — RNG and Two-RN

<span id="fe9-sys-128"></span> Combat, skill activation, and growth systems draw from a shared advancing three-word shift-register RNG state. Request order is therefore observable: inserting one random call changes all later results. The generator is seeded from system ticks at game start and its percentage helpers transform the shared sequence rather than owning independent per-system streams.

<span id="fe9-sys-129"></span> A normal hit test advances the generator twice, averages the two results, and compares that average with final Hit. Critical uses one result. This Two-RN/“True Hit” rule bends real hit probability toward the extremes while leaving displayed critical a flat single-roll percentage. Forecast must not consume either roll; confirmation and strike resolution do. Script-forced outcomes can bypass an ordinary roll without changing the formulas used by unforced strikes.

## FE9-SYS-130–132 — Exchange order, follow-ups, and Brave strikes

<span id="fe9-sys-130"></span> The exchange builder starts with the initiator, schedules an ordinary defender counter only if legal, and then adds speed follow-ups. Vantage changes the opening exchange order; Cancel suppresses the affected counter step. At every scheduled step, survival, weapon, range, status, and remaining-use legality are revalidated, so a mid-log invalidation removes that step instead of rebuilding an already resolved exchange.

<span id="fe9-sys-131"></span> Follow-up doubling is a second exchange granted when one combatant's AS is at least 4 greater than the other's. It can belong to attacker or defender and is independent of who initiated. <span id="fe9-sys-132"></span> Brave behavior instead doubles strikes *inside each exchange*. Thus a fast Brave user can receive two exchanges of two strikes; skill-added strikes can stack again within the exchange path.

## FE9-SYS-133–135 — Hit, Avoid, and Critical

<span id="fe9-sys-133"></span><span id="fe9-sys-134"></span><span id="fe9-sys-135"></span> Hit, Avoid, Critical, and Crit Avoid are built from effective unit getters and item Hit/Critical, then apply triangle, terrain, support, commander/Horror, status, class, and skill modifiers before their final clamps. Overrides such as Deadeye, Gamble, status-target Hit 100, crit sealing, and Parity operate at their documented layer. Forecast and resolution consume the same finalized values; individual coefficients and regional class bonuses remain owner data rather than a second combat formula.

## FE9-SYS-136–140 — Damage selection and floor

<span id="fe9-sys-136"></span> A successful ordinary critical multiplies resolved damage by 3. <span id="fe9-sys-137"></span> Physical attack uses Strength plus the weapon-might path against Defense. <span id="fe9-sys-138"></span> Magical attack uses Magic against Resistance. <span id="fe9-sys-139"></span> The item definition's attack type—not the displayed weapon family—selects that pair, allowing a sword such as a magic weapon to use Magic/Resistance while retaining sword access and animation behavior.

Triangle and effectiveness alter the attack side before defense; terrain and other bonuses alter the appropriate side; skill/script flags can replace or further modify the result. <span id="fe9-sys-140"></span> Negative damage is floored to zero. A zero-damage hit can still be a hit for presentation, but “did damage” gates—such as the normal EXP minimum path and some after-hit effects—observe that no HP was lost.

## FE9-SYS-141 — Counterattack eligibility

<span id="fe9-sys-141"></span> A defender counter requires survival, an unsuppressed counter step, and a currently usable equipped/fallback weapon whose range covers the actual distance. Sleep/Silence or other legality state can remove access; breakage during an earlier strike can remove a later step. Vantage changes order but does not create range, Cancel can remove a scheduled response, and an explicit scripted no-counter rule takes precedence. The resolver revalidates these conditions when the counter step is reached.

## FE9-SYS-142 — Durability consumption and breakage

<span id="fe9-sys-142"></span> Uses belong to the inventory instance. A qualifying weapon action decrements them; at exhaustion the instance is removed/broken, equipped state is repaired, and a later strike or future action must find another legal weapon. The `infinity` property bypasses ordinary use loss. Corrosion can reduce the opponent's equipped instance separately, and ballista ammunition lives in its map tile record rather than a unit slot.

Saves preserve remaining uses and equip flags. Editing the shared item definition changes maximum/default context but does not refill existing instances. Each action handler records consumption at its defined successful commit point; the common break path removes a zero-use instance and invokes deterministic equipment refresh. Miss, multi-strike, staff, siege, and scripted variants therefore follow their handler rather than a second global decrement rule.

## FE9-SYS-143 — On-hit weapon properties

<span id="fe9-sys-143"></span> Item property tokens can enable poison/status application, drain-like effects, Brave strikes, crit suppression, unbreakable durability, effectiveness suppression, magic-stat selection, and other branches. Several individual paths are traced, but no complete ordered dispatcher table yet states proc chance, immunity, damage dependency, stacking, durability, presentation, cure, or save behavior for every recognized token. Keep this entry pending and expand Items & Weapons plus this resolver section; no new article is needed.

## Exchanges — how many times the two units trade

  A skill/flag check can reverse the normal order before anything else happens — the shape of a Vantage-style "counter before being hit" effect. Otherwise the attacker strikes, then the defender counters if still able. After that base pair, two *independent* checks each compare the two units' effective Speed (the same weight-adjusted value [combat forecasting](./combat-animation.md) uses, not raw Speed) — if either side's is at least **4** higher than their opponent's, that side gets a whole additional exchange. This is the game's Speed-based double attack, confirmed at exactly the series' well-known +4 threshold, and it can trigger for either side independently.

## Strikes — how many hits land within one exchange

  A single exchange starts at one strike. A flag on the attacker's own **equipped weapon** can unconditionally double it — a Brave weapon's signature behavior, entirely independent of Speed. On top of whatever the weapon already granted, a proc skill can add further strikes via the same skill-check mechanism described below — a Brave weapon and a proc skill genuinely stack within the same exchange rather than being alternate paths.

## Hit, miss, and critical — the "True Hit" system

  A strike's outcome is decided by two separate rolls of the same random-number generator (a three-word chained shift-register generator, XORed against the requested percentage): the **Hit** roll advances the generator *twice* and averages the two results before comparing against the attacker's Hit-rate forecast stat, while the **Critical** roll uses a single roll compared against the Crit-rate forecast stat. The generator is seeded once when the game boots, from the console's running timer, so resetting gives a different sequence of rolls. Averaging two rolls for Hit but using one for Crit is exactly the series' well-known "True Hit" design — hit rates cluster more tightly around their displayed value than a flat single roll would, while crit rates stay a flat percentage. A confirmed critical hit applies a flat **×3** damage multiplier.

  The Japanese release has no class-level critical bonus at all; in the other releases crit rate can also receive a flat class-level bonus: a specific class trait adds a flat **+15** to Crit in the same forecast step that applies the ordinary Skill-based term, on top of any other active bonus. Separately, an unrelated weapon-side flag can force Crit to **0** outright for that weapon, overriding every other bonus in play.

## Proc skills — the actual check

  See [Skills](./skills.md) for the mechanism (a per-actor bitmask checked by raw table position, rolled against the same shared RNG) and for which specific skills have a confirmed real effect once they trigger.

## Status effects and how long they last

  Each status is a small counter of phases on the unit, shown as a number on its status panel. At the start of a side's phase every counter of that side's units drops by one; when one would reach zero the unit first plays the "status cured" animation. 

| Status | Set by | Starting value | Effect |
|---|---|---|---|
| Poison | a poisoned weapon | 5 | damage at the start of each own phase |
| Sleep | the Sleep staff, Deadeye | 5 | cannot act |
| Silence | the Silence staff | 5 | cannot use tomes or staves |
| Shock | Stun | 2 | Move is 0 |
| Ward | the Ward staff | 7 | Resistance + the counter: +7, then +6, +5... as it runs down |
| Torch | the Torch staff (on the user) | 4 | vision in fog + the counter |
| Paralyse | falling into a pit, being shoved | 1 | cannot act; runs out at the end of the unit's own phase |

A status staff cast on the enemy's phase therefore costs the target four of its own phases: the counter reaches zero at the start of the fifth and the unit acts normally. Sleep, Silence and the combat procs fail against bosses and the final boss. <span class="confidence confidence--confirmed">confirmed</span>

The Berserk staff rolls its hit chance and plays its animation, but the unit has no counter for a Berserk ("Confuse") status, so a hit changes nothing. It has no effect in this game. <span class="confidence confidence--confirmed">confirmed</span>

## Weapon triangle and magic trinity

  Before a strike is forecast, the game looks up the two combatants' weapon types in one small table of 4-byte rows: attacker type, defender type, Hit bonus, Atk bonus. The table holds both triangles <span class="confidence confidence--confirmed">confirmed</span>:

<table><thead><tr><th>Attacker</th><th>Beats</th><th>Loses to</th></tr></thead><tbody>
<tr><td>Sword</td><td>Axe</td><td>Lance</td></tr>
<tr><td>Lance</td><td>Sword</td><td>Axe</td></tr>
<tr><td>Axe</td><td>Lance</td><td>Sword</td></tr>
<tr><td>Fire</td><td>Wind</td><td>Thunder</td></tr>
<tr><td>Thunder</td><td>Fire</td><td>Wind</td></tr>
<tr><td>Wind</td><td>Thunder</td><td>Fire</td></tr>
</tbody></table>

  Advantage gives **+10 Hit and +1 Atk**, disadvantage **−10 Hit and −1 Atk**; the opponent gets the mirrored row. Bows, staves, light magic, knives and laguz strikes have no rows, so they are never in a triangle. A weapon with the reaver flag negates both units' triangle bonuses, which turns an advantage into a disadvantage; the flag is the `revatr` item property, and no retail weapon carries it. The bonus is stored on each combatant and added to Atk and Hit in the forecast.

## Weapon effectiveness — bonus damage against certain enemy types

  Before any of that, the equipped weapon's own type value already decided which pair of stats is even being compared: most weapon types weigh Strength against the target's Defense, but a specific small range of type values switches the whole calculation to Magic against Resistance instead.

  Before computing base Attack, the game runs a dedicated effectiveness check. The attacker's "effective against" mask is the combination of its equipped weapon's and its equipped item's category words; it is tested against the categories of the defender's *class*. If the two share a bit, the weapon's Might is doubled — the mechanism behind every effectiveness pairing in the game (bows vs. flying units, Fire vs. beast-type laguz, and so on). Two categories work differently: `boss` is effective against any unit carrying the boss flag and `final` against the final boss, whatever their class; no vanilla weapon has either. <span class="confidence confidence--confirmed">confirmed</span>

## Hit, Critical and Attack overrides

- Deadeye doubles the final Hit; Gamble halves the final Hit and doubles the final Critical.
- Attacking a unit under a status condition makes the final Hit 100.
- A unit wielding Alondite, Ragnell, Gurgurant, the Lion's claws or the kings' beaks cannot be critted (property `sealcrit`).
- The Black Knight and Ashnard on Rajaion wear blessed armour (an internal skill flag on their classes): any weapon without the `weakA` property — Ragnell, the Lion's claws, the dragon breaths, the kings' beaks — has its Attack set to 0 against them, and Counter does not reflect damage onto them.

  On disk, a weapon names its targets with two category words in its [item record](./items-weapons.md) (`fly`, `beast`, `dragon`, `armor`, `knight`, `alize`&hellip;), the same words a class uses to describe itself. The *Full Guard* property removes every effectiveness bonus against its holder; two more properties remove only the anti-flier or only the anti-laguz bonus.

## Battle experience — two level comparisons, then modifiers

  Battle EXP is assembled from two components. The first is a halved level-difference term with a minimum of 1. The second adds difficulty, promoted-level, boss, and thief adjustments with a minimum of 0. The game uses two related definitions of effective level: the base term treats a promoted unit as `level + 20`, while the extra term uses `level + 20 + promotionBase[difficulty]`.

```text
base = max(1, (levelConstant[difficulty]
               + defeatedBaseLevel - winnerBaseLevel + 1) / 2)

extra = max(0, modeBonus[difficulty]
                + defeatedPromotedLevel - winnerPromotedLevel
                + bossBonus(defeated) + thiefBonus(defeated))

raw EXP = base + extra
```

  Three gates come first: fighting the final boss gives no EXP; a unit that never did damage in the exchange gets exactly 1; and the `extra` term only counts when the opponent died. Boss and thief properties are tested independently, so their bonuses can stack on the same defeated unit. After the raw award is calculated, the Elite skill doubles it and the Frac90 skill reduces it to 70%, preserving a minimum of 1. The same adjustment is applied to growth rates at level-up (see [Level-Up Growth](./level-up-growth.md)). The award is capped at 100 and is also constrained by a separate helper that considers current level, current EXP, promotion eligibility, and party state.

!!! info "Mental model: GameData supplies constants, native code supplies the formula"
    Seven difficulty-indexed rows are read through a named runtime resource. They hold the mode bonus, level constant, promotion-base bonus, boss bonus, thief bonus, transformed/Laguz growth bonus, and the Berserker/Sniper/Swordmaster critical bonus. The transformed/Laguz row is consumed by a linked-class stat-growth routine, not by the battle-EXP calculator.

## FE9-SYS-149 — Death resolution

<span id="fe9-sys-149"></span> After survival effects finish, zero HP produces a death result record and marks the unit's runtime state. Presentation can fade or animate the actor, but the consequence layer owns Die/LocalDie event dispatch, item drops, force removal or persistent retreat, kill counters, and objective checks. A named story unit may retreat and remain available later even though the combat result removed it from this map; that policy is authored, not inferred from the HP calculation.

The victor's counters and any drop commit before the chapter evaluates Rout/boss/protect conditions. Event skip may suppress visual death motion but must not suppress the state change. Character-specific retreat, dialogue, and later availability are authored consequence policy; they enter the same queue after the death result rather than changing zero-HP resolution.

## FE9-SYS-150 — Dropped-item transfer

<span id="fe9-sys-150"></span> An inventory instance can carry drop bit `0x40`; deployment may mark one item. When its holder is defeated, the award flow transfers that instance to the eligible victor and displays the force-appropriate obtained/lost message. For a player/reserve recipient whose relevant inventory half is full, the `_gi` flow opens the convoy-or-discard process rather than silently overwriting another item.

The shared delivery transaction validates the recipient and personal slot, then offers an available convoy/discard/failure route without overwriting an instance. Non-player victors and protected items follow the caller's delivery policy. The death/drop result and receiving inventory or convoy commit atomically enough that checkpoint/reload cannot award the same instance twice.

## FE9-SYS-151 — Combat statistics tracking

<span id="fe9-sys-151"></span> On a kill, the surviving unit increments lifetime kills (`+0x22A`) and kills on the current map (`+0x22C`) and records the current chapter in its last-kill field (`+0x234`). Map kills reset when the unit is initialized for deployment; lifetime kills persist and feed ending/records displays. The biorhythm battle counter is another per-unit combat-written field, while chapter clear history separately records chapter, part, turns, and elapsed time.

These fields are saved with the unit or party and read by reports, trial scoring, endings, and debug views. Each counter is updated by its committed action owner and reset only by its documented chapter/report lifecycle; unknown neighboring fields must be preserved by editors, but do not change ownership of the traced statistics.

## FE9-SYS-152 — Battle EXP

<span id="fe9-sys-152"></span> The formula above is the reviewed implementation: base and kill-only extra terms use two effective-level definitions and difficulty `GameData`; boss/thief bonuses stack; no-damage combat yields exactly 1; the final boss yields none; Paragon doubles, Blossom multiplies by 70% with minimum 1; the result is capped at 100 and then constrained by level/promotion state. The award is numerical state before the EXP bar presents it.

## FE9-SYS-153 — EXP bar and level transition

<span id="fe9-sys-153"></span> The result log carries prior EXP and earned EXP to the presentation process. The authoritative award is committed first; each threshold crossing delegates to [Level-Up Growth](./level-up-growth.md), and a promotion boundary delegates to the class-change path. Cap/no-growth results are still valid committed levels. Skipped or disabled animation consumes the same result without changing state, and save occurs only after the pending level/promotion consequence is resolved.

## FE9-SYS-154 — Battle-result handoff

<span id="fe9-sys-154"></span> Numerical resolution emits a result-record stream describing setup, hit/miss/critical, damage/heal, deaths, skill messages, EXP, and stat gains. Map animation or full 3D battle consumes that log; neither presentation path recalculates who hit. After playback, authoritative unit/item state feeds EXP/level processing, death/retreat and drops, dialogue/events, objective polling, acted/Canto state, and script continuation.

This boundary lets animation options change presentation without changing outcomes and lets scripted waits resume only after consequences are ready. The consequence queue completes the resolved strike, HP/death and survival effects, break/drop transfer, EXP and level/promotion work, objective/event polling, and presentation/script continuation in that ownership order; scene-specific dialogue is an authored entry in the queue.

## After the numbers: presentation is a separate step

  Once damage and any experience award are fully calculated, the game hands off to a separate, scheduled presentation step — the EXP bar animation, boss or player-death consequences, any post-battle dialogue, and victory recognition all run there rather than inline with the combat calculation itself. This separation is why a battle's numerical outcome and its on-screen consequences are handled as two distinct stages rather than one.

## Worked example

  An attacker with 14 effective Speed fights a defender with 9. The +5 advantage clears the +4 threshold, so the attacker receives a second exchange if both units survive. If the attacker uses a Brave weapon, each attacker exchange contains two strikes: two before the counter and two in the follow-up, for as many as four attacker strikes. Each strike still rolls Hit separately, then Critical if it hits; Brave does not guarantee four successful hits and the Speed advantage does not multiply critical damage.

## Interactions and limits

Forecast, AI prediction, and resolution must agree on legal equipment, AS, triangle, range, effectiveness, and blessed protection, but only resolution spends durability and RNG. Parity, status, skills, terrain, supports, biorhythm, scripted-combat flags, and death can add later gates or overrides. A scheduled follow-up disappears if its actor dies or loses the ability to strike; a broken weapon can change later strike availability without retroactively changing an already resolved hit.

## Interactions and review boundary

All combat-mechanics systems on this page are reviewed without a blocking research gap. Legality, range, effective-stat construction, exchange ordering, Hit/Avoid/Critical calculation, durability, on-hit dispatch, death/drop/stat consequences, EXP handoff, and presentation separation form one ordered resolver. Per-weapon, skill, support, and chapter overrides remain data or delegated predicates documented by their owning systems, not missing combat ownership. No new primary article is needed.
