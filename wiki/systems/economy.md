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
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/economy.md"
system_entries: ["FE9-SYS-193", "FE9-SYS-197", "FE9-SYS-198", "FE9-SYS-199", "FE9-SYS-200", "FE9-SYS-201", "FE9-SYS-202", "FE9-SYS-203", "FE9-SYS-204", "FE9-SYS-205", "FE9-SYS-206", "FE9-SYS-207", "FE9-SYS-214", "FE9-SYS-215"]
system_reviewed: ["FE9-SYS-193", "FE9-SYS-197", "FE9-SYS-198", "FE9-SYS-199", "FE9-SYS-200", "FE9-SYS-201", "FE9-SYS-202", "FE9-SYS-203", "FE9-SYS-204", "FE9-SYS-205", "FE9-SYS-206", "FE9-SYS-207", "FE9-SYS-214", "FE9-SYS-215"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Economy

*Gold, shops, and forging — how the game tracks and spends the party's money*

The party's current gold lives as a single field on the game's central party-data struct. Changing it is never a plain overwrite: the function that sets a new amount also adjusts two chapter-report counters — gold earned and gold spent — by however much the requested change actually moved the total up or down, before finally clamping the new balance to a hard cap of **9,999,999**. <span class="confidence confidence--confirmed">confirmed</span>

  The earned and spent counters feed Soren's report before the next base. They are reset after that report and remain separate from the party's current balance.

## Example: earning and spending

  If the party gains 1,000 gold, current gold and the report's Earned counter rise by 1,000 unless the current balance hits the cap first. Spending 300 then lowers current gold and raises the report's Spent counter by 300; it does not erase Earned.

## Gold accounting rules

<span id="fe9-sys-197"></span> Gold is persistent party state with a saturating upper limit, not an unsigned field that callers may wrap. The setter measures the actual accepted delta after clamping: accepted positive movement increases the earned counter, accepted negative movement increases the spent counter. A request to add 1,000 while only 100 below the cap therefore records 100 earned, not the rejected 900. Purchases must validate affordability before committing the negative delta; failed transactions must leave balance and report counters unchanged.

## Convoy and warehouse

<span id="fe9-sys-193"></span> The convoy is a party-owned array of 200 item instances, separate from every unit's eight slots. Deposits and withdrawals transfer instance identity, remaining uses, flags, and forge references rather than creating a fresh definition. Purchases and completed forges can deliver directly when access is enabled. Early chapters gate the facility, while base and preparation contexts later expose it. The shared transfer transaction validates capacity before commit, uses the caller's prompt/failure route when full, and compacts removals in deterministic slot order; individual chapter access gates are authored policy.

## Shops and forging

  Gold is spent through [per-chapter shop inventories](../formats/shop-format.md): an armory, a vendor, and a forge. The forge is a genuine weapon-upgrading mechanic — its stock is a grid of weapon families by base weapon (see [Items & Weapons](./items-weapons.md) for how a forged weapon's stats are adjusted). Only one weapon can be forged per chapter: a flag in the party data is set when the forged weapon is delivered, the base menu's Forge entry is unavailable while it is set, and it clears when the chapter ends. The flag is saved. <span class="confidence confidence--confirmed">confirmed</span>

## Shop transaction families

<span id="fe9-sys-198"></span> **Armory.** The chapter-selected armory list supplies weapon stock. Selection validates stock and affordability, confirmation creates an item instance and routes it to a legal unit/convoy destination, then the gold setter records the accepted debit and report spending. Cancellation and failed delivery leave both inventory and gold unchanged. Quantities and row order come from the authored catalog, while a full destination uses the shared delivery prompt/failure policy.

<span id="fe9-sys-199"></span> **Vendor.** Vendor stock uses the same validate–deliver–debit transaction for staves and consumables, while its chapter catalog and item-category filters differ from the armory. It shares destination, cancellation, reporting, and persistence boundaries. Catalog rows, quantities, and category flags are authored shop data rather than independent transaction rules.

<span id="fe9-sys-200"></span> **Sell shop.** The menu enumerates eligible owned instances and excludes protected items such as those carrying the `valuable` property. Confirmation prices the definition plus any supported instance overlay, removes and compacts that exact instance, repairs equipment if necessary, credits gold through the clamped setter, and records only the accepted increase. Cancellation leaves the instance untouched. Sellability and price inputs are item/forge data consumed by this transaction.

<span id="fe9-sys-201"></span> **Per-chapter stock.** [Shop data](../formats/shop-format.md) separates Normal/Easy, Hard, and Maniac sections. Campaign chapter and difficulty select the facility section before the shop scene enumerates its authored rows; reload reproduces that selection. A missing section takes the facility's explicit fallback or unavailable path instead of borrowing arbitrary stock.

## Forge lifecycle

<span id="fe9-sys-202"></span> **Availability.** The base menu first requires forge stock and an unused chapter flag. Editing takes place in a temporary record; successful delivery commits the forge and sets the saved used flag. Missing chapter forge data can fall back to default stock. Cancellation must not set the flag. Campaign chapter initialization resets the per-chapter flag; individual stock and fallback rows are authored data. This one-per-chapter rule, together with the finite retail campaign, is the only reason an unmodified playthrough cannot exhaust all 48 records; it is not a pool-capacity check.

<span id="fe9-sys-203"></span> **Stat customization.** Four signed step bytes modify Might directly, Hit in five-point increments, Critical in three-point increments, and Weight downward. The editor stores current, minimum, and maximum steps for each row and accepts a change only when both the row bound and resulting stat are valid. Might and Hit cannot be reduced below 2 in the editor, Critical cannot be reduced below 1, and Weight reduction cannot take final Weight below 2; the maximum-step guard also prevents signed-byte wrap. Runtime getters remain defensive and clamp Might/Hit/Weight to at least 1 and Critical to at least 0 before returning an eight-bit value. Price display recomputes from accepted steps, but its arithmetic belongs to FE9-SYS-205 rather than the definition of customization state.

<span id="fe9-sys-204"></span> **Appearance customization.** The persistent 0x18-byte forge record stores the custom name and four RGBA trail-color bytes. Battle rendering uses that instance color instead of the definition's default trail color. These fields affect presentation, not weapon identity, rank, or base definition.

<span id="fe9-sys-205"></span> **Price calculation.** A forge begins from a base weapon and accumulates each accepted upgrade step through its authored price inputs into the displayed quote. That quote is the confirmation authority. Confirmation revalidates current gold, but the result handler debits gold before applying the four forge-record setters. Normal cancellation leaves state unchanged; record-pool exhaustion is an unchecked exceptional path rather than a rejected transaction.

<span id="fe9-sys-206"></span> **Record pool.** The party owns 48 persistent 0x18-byte forge records. Allocation marker 0 is free and 1 is occupied; the inventory instance carries a one-based six-bit link. Editing uses a temporary record and confirmation normally copies it into a free persistent slot. Records are released when their owning item instance is reset or destroyed and retain stable indices rather than being compacted behind live links.

There is no full-pool guard. `allocate_free_forge_result_slot` returns index 0 after scanning all 48 records, and every name/stat/copy wrapper passes that zero to helpers whose address formula is `pool + (index - 1) * 0x18`. They consequently write the 24 bytes immediately before the pool: convoy slots 198–200. The new weapon retains forge index 0 and is therefore plain/unforged; the confirmation path has already begun committing the transaction. This cannot occur in the retail campaign because only one forge is allowed per chapter, but a repeatable-forge patch or a malformed full-pool save can reach it. The Saves validator reports a completely occupied pool before play. Orphaned edited references are separate validation errors.

## Reward routing

<span id="fe9-sys-207"></span> Rewards originate from scripts, chests, drops, visits, shops/forge, and chapter clear, then delegate by reward type to item delivery, gold accounting, BEXP, or another explicit owner. Item rewards preserve instance fields and first use the caller's eligible active-unit destination, then its personal-inventory/convoy/prompt/failure policy. The source marker commits only after accepted delivery; gold and BEXP use their clamped persistent setters and reporting counters. This connects Economy, Map Actions, Combat Resolution, and Events without needing a separate primary page.

## Report counters

<span id="fe9-sys-214"></span> Soren's Battle Report presents four signed counters for the reporting period: gold earned, gold spent, combat EXP, and Bonus EXP. It reads summaries rather than recomputing them from current balances. Current gold and BEXP can therefore be high while the report displays only changes from the just-finished period.

<span id="fe9-sys-215"></span> Counter lifecycle is update, present, then reset. Gold writes record the actual clamped positive or negative delta; committed EXP and BEXP award entry points update their own report counters. The base report reads the four values and its completion path resets them without changing current gold, BEXP, unit EXP, or levels; skipped presentation reaches the same completion/reset path.

## Convoy

  Beyond what a unit personally carries, the party has one shared storage array — the convoy — holding up to **200** items independently of any unit's own inventory. A shop purchase can be sent straight to the convoy instead of to a unit on the field, without needing to route through anyone's personal inventory first.

  Convoy access itself is chapter-gated: it is unavailable during the game's early chapters, and becomes available again from partway through the game onward, plus during the base/preparation screens that sit outside normal chapter numbering.

  A forged weapon goes either to the unit or, when the convoy is available, into the convoy.

## Interactions and review boundary

All economy systems on this page are reviewed without a blocking research gap. Convoy capacity, shop stock selection, buy/sell delivery, clamped gold/report accounting, forge gating/pricing/allocation, reward routing, and transaction rollback establish the complete ownership lifecycle. Individual chapter catalogs, price inputs, and prompt text remain authored tables and presentation content. No new primary article is needed.
