---
id: "ragnell-and-alondite"
title: "Ragnell and Alondite"
description: "The twin blessed swords of Ike and the Black Knight, and Ashnard's Gurgurant, as the game data defines them"
games: ["path-of-radiance"]
section: "systems"
article_type: "reference"
tags: ["Items","Combat"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/ragnell-and-alondite.md"
---
# Ragnell and Alondite

*The twin blessed swords of Ike and the Black Knight, and Ashnard's Gurgurant, as the game data defines them*

Ragnell and Alondite are the same weapon in the data, apart from who may wield them and one property. Gurgurant, Ashnard's sword, follows the same pattern with heavier numbers. <span class="confidence confidence--confirmed">data</span>

## The numbers

<div class="table-wrap">
<table class="tight"><thead><tr><th>Sword</th><th class="num">Mt</th><th class="num">Hit</th><th class="num">Crit</th><th class="num">Wt</th><th class="num">Range</th><th>Bonus</th><th>Wielder</th></tr></thead><tbody>
    <tr><td>Ragnell</td><td class="num">18</td><td class="num">80</td><td class="num">5</td><td class="num">20</td><td class="num">1–2</td><td>Def +5</td><td>a unit with Ike's hero trait (<code>SID_HERO</code>)</td></tr>
    <tr><td>Alondite</td><td class="num">18</td><td class="num">80</td><td class="num">5</td><td class="num">20</td><td class="num">1–2</td><td>Def +5</td><td>the Black Knight's class (<code>JID_BKNIGHT</code>)</td></tr>
    <tr><td>Gurgurant</td><td class="num">20</td><td class="num">90</td><td class="num">0</td><td class="num">25</td><td class="num">1–2</td><td>—</td><td>a unit with the final-boss trait (<code>SID_FINAL</code>, Ashnard)</td></tr>
  </tbody></table>
</div>

  None of the three needs a weapon rank: the wielder test replaces it. All three show 20 uses but never lose any.

## What they share

- **Unbreakable** (`infinity`): uses never go down.
- **Cannot be critted** (`sealcrit`): the wielder takes no critical hits.
- **Range 1–2**, with the sword-wave battle animation at range (`stormsw`): the swing sends a shock wave instead of the wielder running in. Each has its own wave effect (`EID_REPPU1`, `2`, `3`).
- **`valuable`**, a property carried by the game's unique and legendary items whose exact effect is not traced. <span class="confidence confidence--open">open</span>

## What sets Ragnell apart

  Only Ragnell has `weakA`, the property that lets a weapon damage the blessed-armour units. Alondite does not have it, so against the Black Knight's blessed armour Ragnell is the sword that works (see [Combat Mechanics](./combat-mechanics.md)). Their attack-trail colours also differ: teal for Ragnell, red for Alondite, black for Gurgurant. <span class="confidence confidence--confirmed">data</span>

## Related pages

[Swords](./weapons-swords.md) lists every sword; [Items & Weapons](./items-weapons.md) explains the item record and every property.
