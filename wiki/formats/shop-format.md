---
id: "shop-format"
title: "Shop Format"
description: "Per-difficulty armory, vendor and forge inventories, one section set per chapter"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Economy","Editable"]
aliases: ["tellius_archive.html#/shop-format"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/shop-format.md"
---
# Shop Format

*Per-difficulty armory, vendor and forge inventories, one section set per chapter*

Shop data uses the [Labeled Section Format](./labeled-section.md). One file exists per difficulty: `shopitem_n.bin` serves Normal and Easy, `shopitem_h.bin` Hard and `shopitem_m.bin` Maniac. Each holds 96 sections named `<W|I|F>SHOP_ITEMS_C<nn>`: an armory, a vendor and a forge for each chapter number 00&ndash;31. <span class="confidence confidence--confirmed">confirmed</span>

## How a chapter receives shop stock

When a base shop opens, the game builds the section name from the current chapter number (`"WSHOP_ITEMS_C%02d"`) and looks that section up by name. The chapter number is the chapter's disc file number &mdash; the Prologue is 01, Chapter 1 is 02 &mdash; so `WSHOP_ITEMS_C05` is the armory of the chapter whose files are `bmap05`, in-game Chapter 4. A chapter number with no section gets an empty armory and vendor and a built-in default forge list. <span class="confidence confidence--confirmed">confirmed</span>

## Sections

<div class="table-wrap">
<table><thead><tr><th>Letter</th><th>Shop</th><th>Holds</th></tr></thead><tbody>
    <tr><td><code>W</code></td><td>Armory</td><td>A list of <code>IID_</code> weapon pointers ended by a zero word, in display order</td></tr>
    <tr><td><code>I</code></td><td>Vendor</td><td>A list of <code>IID_</code> staves and consumables ended by a zero word</td></tr>
    <tr><td><code>F</code></td><td>Forge</td><td>A fixed grid of 45 (item, base) pointer pairs: 5 rows &amp;times; 9 base columns, no terminator</td></tr>
  </tbody></table>
</div>

  Each `IID_` resolves to the global [FE8Data.bin](./fe8data.md) item definition; the shop file stores no price or stats. An item's price is its cost per use &times; its uses.

## The forge grid

The base column is the same in every forge section: `MDV_IRN`, `MDV_SLM`, `MDV_STL`, `MDV_SLV`, `MDV_HND`, `MDV_FI`, `MDV_TH`, `MDV_WD`, `MDV_LIT` &mdash; Iron, Slim, Steel, Silver, Thrown, Fire, Thunder, Wind and Light, the base weapon the player picks before forging. Each row is a weapon family (swords, lances, axes, bows, tomes in vanilla), and each cell names the weapon forged from that base, or 0 when the row doesn't offer it.

## Example

The early-game sword row reads Iron Sword/`MDV_IRN`, Slim Sword/`MDV_SLM`, Steel Sword/`MDV_STL`, then zero for Silver and the magic bases; later chapters fill Silver Sword/`MDV_SLV`. The tome row leaves the physical bases empty and fills Fire, Thunder, Wind and Light.

## The sell shop

The base also has a sell shop (`SSHOP`, the `_SSHOP_` dialogue tag). It lists the player's own items, so it has no inventory section; its messages include refusing to buy a valuable item. <span class="confidence confidence--confirmed">confirmed</span>

## File layout

After the 0x20-byte header come two pointers to the file's build timestamp and author strings, then every armory section, every vendor section and every forge section in chapter order, the label pool, the relocation table, and the section table sorted by name.
