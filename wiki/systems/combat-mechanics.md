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
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/combat-mechanics.md"
---
# Combat Resolution

*How an exchange of blows and its experience award are calculated*

A battle between two units is a sequence of **exchanges**, and each exchange can itself contain more than one **strike** — two separate places extra hits can come from, confirmed to sit in structurally distinct parts of the combat pipeline rather than one conflated mechanism.

!!! info "Mental model: order, quantity, then outcome"
    Combat answers three questions in order: **who acts next** (exchange order and counters), **how many strikes that action contains** (ordinary, Brave, or skill-added strikes), and **what each strike does** (hit, critical, effectiveness, damage, and post-hit effects). Keeping those layers separate prevents “double attack,” “Brave,” and “critical” from being treated as versions of the same mechanic.

## Exchanges — how many times the two units trade

  A skill/flag check can reverse the normal order before anything else happens — the shape of a Vantage-style "counter before being hit" effect. Otherwise the attacker strikes, then the defender counters if still able. After that base pair, two *independent* checks each compare the two units' effective Speed (the same weight-adjusted value [combat forecasting](./combat-animation.md) uses, not raw Speed) — if either side's is at least **4** higher than their opponent's, that side gets a whole additional exchange. This is the game's Speed-based double attack, confirmed at exactly the series' well-known +4 threshold, and it can trigger for either side independently.

## Strikes — how many hits land within one exchange

  A single exchange starts at one strike. A flag on the attacker's own **equipped weapon** can unconditionally double it — a Brave weapon's signature behavior, entirely independent of Speed. On top of whatever the weapon already granted, a proc skill can add further strikes via the same skill-check mechanism described below — a Brave weapon and a proc skill genuinely stack within the same exchange rather than being alternate paths.

## Hit, miss, and critical — the "True Hit" system

  A strike's outcome is decided by two separate rolls of the same random-number generator (a three-word chained shift-register generator, XORed against the requested percentage): the **Hit** roll advances the generator *twice* and averages the two results before comparing against the attacker's Hit-rate forecast stat, while the **Critical** roll uses a single roll compared against the Crit-rate forecast stat. Averaging two rolls for Hit but using one for Crit is exactly the series' well-known "True Hit" design — hit rates cluster more tightly around their displayed value than a flat single roll would, while crit rates stay a flat percentage. A confirmed critical hit applies a flat **×3** damage multiplier.

  The Japanese release has no class-level critical bonus at all; in the other releases crit rate can also receive a flat class-level bonus: a specific class trait adds a flat **+15** to Crit in the same forecast step that applies the ordinary Skill-based term, on top of any other active bonus. Separately, an unrelated weapon-side flag can force Crit to **0** outright for that weapon, overriding every other bonus in play.

## Proc skills — the actual check

  See [Skills](./skills.md) for the mechanism (a per-actor bitmask checked by raw table position, rolled against the same shared RNG) and for which specific skills have a confirmed real effect once they trigger.

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

## After the numbers: presentation is a separate step

  Once damage and any experience award are fully calculated, the game hands off to a separate, scheduled presentation step — the EXP bar animation, boss or player-death consequences, any post-battle dialogue, and victory recognition all run there rather than inline with the combat calculation itself. This separation is why a battle's numerical outcome and its on-screen consequences are handled as two distinct stages rather than one.

## Worked exchange

  An attacker with 14 effective Speed fights a defender with 9. The +5 advantage clears the +4 threshold, so the attacker receives a second exchange if both units survive. If the attacker uses a Brave weapon, each attacker exchange contains two strikes: two before the counter and two in the follow-up, for as many as four attacker strikes. Each strike still rolls Hit separately, then Critical if it hits; Brave does not guarantee four successful hits and the Speed advantage does not multiply critical damage.
