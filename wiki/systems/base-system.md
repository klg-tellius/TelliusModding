---
id: "base-system"
title: "The Base"
description: "How the between-chapter hub gates conversations, army management, shops, forge, and warehouse"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Base", "Economy", "Progression"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "path-of-radiance-us-manual"]
cms_collection: "systems"
source_path: "systems/base-system.md"
system_entries: ["FE9-SYS-274", "FE9-SYS-275", "FE9-SYS-276", "FE9-SYS-277", "FE9-SYS-279", "FE9-SYS-280", "FE9-SYS-281"]
system_reviewed: ["FE9-SYS-274", "FE9-SYS-275", "FE9-SYS-276", "FE9-SYS-277", "FE9-SYS-279", "FE9-SYS-280", "FE9-SYS-281"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# The Base

The base is a campaign hub over persistent party state, not a tactical map. It opens from Chapter 8 where permitted and lets story, progression, inventory, and economy systems run before preparation.

## Mental model and example

The base is an orchestrator over saved campaign data. Entering it can run one opening event, then constructs menu entries from chapter and flags. Choosing Manage edits units and inventory directly; choosing Info runs a one-time script; choosing Forge performs a transaction; leaving routes to story or preparation. None of those choices consumes a tactical unit action because no army phase is active.

For example, forging must coordinate five owners: chapter stock selects the base, the forge editor creates temporary customization, Economy validates and spends gold, the forge pool allocates a persistent record, and Warehouse or a unit inventory receives the item. Only after successful delivery may the one-per-chapter flag be set. Cancelling before confirmation must leave every owner unchanged.

<span id="fe9-sys-274"></span> **Base menu state.** Campaign routing enters the base, runs its opening event once, builds available facilities from chapter/flags, and remembers the correct exit. A saved byte prevents the opening from replaying after reload.

<span id="fe9-sys-275"></span> **Base Info conversations.** Chapter scripts register available conversations; the menu resolves titles/participants and completion flags. Selecting one runs its event and persists rewards or story changes.

<span id="fe9-sys-276"></span> **Support menu.** Eligible pairs appear when progression, rank threshold, survival/availability, and one-time conditions agree. Completion advances rank/progress and changes later combat bonuses.

<span id="fe9-sys-277"></span> **Manage/army organization.** Roster/status, inventory, skills, supports, and BEXP operate directly on persistent unit/party state without consuming a tactical action.

<span id="fe9-sys-279"></span> **Base shops.** Armory/vendor select chapter+difficulty stock; sell lists owned items. Purchases route to a unit or the convoy and gold setters update report spending/earning.

<span id="fe9-sys-280"></span> **Base forge.** The player selects a permitted base weapon, adjusts stats, name, and trail color, pays the price, allocates a forge record, and receives the item. A saved flag limits delivery to once per chapter.

<span id="fe9-sys-281"></span> **Base warehouse.** The 200-slot convoy exchanges items with unit inventories and receives purchases/rewards where allowed.

## Rules and lifecycle

Campaign routing enters the base only where chapter state permits it. Initialization checks the saved opening-event byte, runs the opening script once when needed, then builds facilities from chapter resources and flags. Each facility works on persistent party/unit state and returns to a menu that must refresh after story, roster, inventory, gold, BEXP, support, or forge changes. Save and exit preserve the resulting state and select the correct continuation.

Info conversations are registered content: labels and participants identify an entry, selection runs its event, and a completion flag prevents replay. Manage is a collection of persistent editors rather than one formula, but they share cancel/commit and refresh boundaries. Warehouse transfers item instances between the 200-slot party array and eight-slot unit inventories. Forge performs base selection, stat/name/color editing, price confirmation, allocation, item delivery, gold debit, and used-flag commit as one transaction.

<span id="fe9-sys-276-detail"></span> The Support menu's base-system boundary is reviewed: it queries the support owner for available rows, launches the selected conversation, and refreshes the hub afterward. The underlying conversation scheduler and affinity bonus consumer remain explicitly tracked in [Support System](./support-system.md), not as a base-hub gap. <span id="fe9-sys-279-detail"></span> Base shops delegate stock, buy/sell, delivery, cancellation, and report accounting to the reviewed transaction lifecycle in [Economy](./economy.md).

## Interactions and edge cases

An Info event can add/remove a unit or alter flags, so the menu and every facility must rebuild stale lists on return. A full inventory/convoy, insufficient gold, exhausted forge pool, invalid support pair, capped unit, or missing shop resource must fail without partial state. Reload after the opening event must not replay it; reload after a committed transaction must not duplicate delivery. Exit routing must not accidentally start a tactical phase before preparation commits deployment.

## Interactions and review boundary

All base systems on this page are reviewed without a blocking research gap. Entry/opening-event state, dynamically gated facilities, Info/support/management handoffs, shop/forge/warehouse transactions, refresh after child mutation, save, and exit routing form one hub transaction. Chapter menu rows, conversation schedules, and stock lists remain authored data delegated to their primary systems. No new primary article is needed.

