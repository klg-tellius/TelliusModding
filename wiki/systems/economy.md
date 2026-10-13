---
id: "economy"
title: "Economy"
description: "Gold, shops, and forging — how the game tracks and spends the party's money"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Economy"]
aliases: ["tellius_archive.html#/economy"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/economy.md"
---
# Economy

*Gold, shops, and forging — how the game tracks and spends the party's money*

The party's current gold lives as a single field on the game's central party-data struct. Changing it is never a plain overwrite: the function that sets a new amount also adjusts two chapter-report counters — gold earned and gold spent — by however much the requested change actually moved the total up or down, before finally clamping the new balance to a hard cap of **9,999,999**. <span class="confidence confidence--confirmed">confirmed</span>

  The earned and spent counters feed Soren's report before the next base. They are reset after that report and remain separate from the party's current balance.

## Example: earning and spending

  If the party gains 1,000 gold, current gold and the report's Earned counter rise by 1,000 unless the current balance hits the cap first. Spending 300 then lowers current gold and raises the report's Spent counter by 300; it does not erase Earned.

## Shops and forging

  Gold is spent through [per-chapter shop inventories](../formats/shop-format.md): an armory, a vendor, and a forge. The forge is a genuine weapon-upgrading mechanic — its stock is a grid of weapon families by base weapon (see [Items & Weapons](./items-weapons.md) for how a forged weapon's stats are adjusted). Only one weapon can be forged per chapter: a flag in the party data is set when the forged weapon is delivered, the base menu's Forge entry is unavailable while it is set, and it clears when the chapter ends. The flag is saved. <span class="confidence confidence--confirmed">confirmed</span>

## Convoy

  Beyond what a unit personally carries, the party has one shared storage array — the convoy — holding up to **200** items independently of any unit's own inventory. A shop purchase can be sent straight to the convoy instead of to a unit on the field, without needing to route through anyone's personal inventory first.

  Convoy access itself is chapter-gated: it is unavailable during the game's early chapters, and becomes available again from partway through the game onward, plus during the base/preparation screens that sit outside normal chapter numbering.

  A forged weapon goes either to the unit or, when the convoy is available, into the convoy.
