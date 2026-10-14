---
id: "items-weapons"
title: "Items & Weapons"
description: "How an item definition becomes inventory, equipment, combat statistics, and durability"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Balance","Economy"]
aliases: ["tellius_archive.html#/items-weapons"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/items-weapons.md"
---
# Items & Weapons

*How an item definition becomes inventory, equipment, combat statistics, and durability*

An item definition describes what a weapon or usable object is. A deployment or save places an instance of that item in a unit's inventory, and runtime state tracks mutable values such as remaining durability and whether the item is equipped. Combat then combines the equipped weapon's properties with the unit's effective stats.

## From item definition to combat

1. An `IID_` selects a reusable item record in [FE8Data.bin](../formats/fe8data.md).
2. [Deployment](../formats/dispo-format.md) or save data puts an instance in a unit inventory.
3. The unit equips one legal weapon according to [class weapon access](./classes.md) and any skill restrictions.
4. [Combat](./combat-mechanics.md) reads might, hit, range/type flags, effectiveness, and special weapon behavior.
5. After use, runtime durability decreases; reaching zero removes or breaks the instance rather than changing the global item definition.

!!! info "Do not confuse an item record with an inventory instance"
    `IID_IRONSWORD` defines the shared Iron Sword properties. The Iron Sword carried by a particular unit has its own remaining durability. Changing the definition affects newly interpreted instances; consuming durability does not rewrite `FE8Data.bin`.

## Example — Iron, Steel, and Silver swords

  The numeric fields of each 0x60-byte item record control durability, power, accuracy, weight, and critical rate. The common sword progression shows the trade-offs:

<div class="table-wrap">
<table class="tight"><thead><tr><th>Field</th><th>Iron</th><th>Steel</th><th>Silver</th><th>Reading</th></tr></thead><tbody>
    <tr><td><code>uses</code></td><td class="num">46</td><td class="num">35</td><td class="num">25</td><td>Durability — descending <span class="badge confirmed"></span></td></tr>
    <tr><td><code>might</code></td><td class="num">5</td><td class="num">8</td><td class="num">13</td><td>Power — ascending <span class="badge confirmed"></span></td></tr>
    <tr><td><code>hit</code></td><td class="num">90</td><td class="num">75</td><td class="num">80</td><td>Accuracy <span class="badge confirmed"></span></td></tr>
    <tr><td><code>weight</code></td><td class="num">7</td><td class="num">12</td><td class="num">11</td><td>Item weight <span class="badge confirmed"></span></td></tr>
    <tr><td><code>rank</code></td><td>E</td><td>D</td><td>A</td><td>Letter token, turned into a minimum weapon EXP (E 1, D 31, C 71, B 121, A 181, S 251) <span class="badge confirmed"></span></td></tr>
    <tr><td><code>cost</code></td><td class="num">10</td><td class="num">20</td><td class="num">75</td><td>Price per use: shop price = cost &amp;times; uses <span class="badge confirmed"></span></td></tr>
  </tbody></table>
</div>

## The whole item record

  Every byte of the record is known. The game's loader reads it field by field into a smaller runtime item; several fields are short *token strings* the loader compares by name rather than numbers.

<div class="table-wrap">
<table class="tight"><thead><tr><th>Offset</th><th>Field</th><th>Meaning</th></tr></thead><tbody>
    <tr><td><code>0x00</code>&amp;ndash;<code>0x08</code></td><td>IID, name key, description key</td><td><code>IID_</code>, <code>MIID_</code>, <code>MH_I_</code> labels</td></tr>
    <tr><td><code>0x0C</code></td><td>Weapon type</td><td>Token <code>sword lance axe bow flame thunder wind rod knife fang item acc</code>: the rank trained and who can equip it</td></tr>
    <tr><td><code>0x10</code></td><td>Attack type</td><td>Same tokens; <code>flame thunder wind rod</code> make the attack use Magic against Resistance (the Runesword is <code>sword</code>/<code>rod</code>)</td></tr>
    <tr><td><code>0x14</code></td><td>Rank</td><td>Token <code>E</code>&amp;ndash;<code>S</code>, or <code>N</code>/none</td></tr>
    <tr><td><code>0x18</code>&amp;ndash;<code>0x2C</code></td><td>Six properties</td><td>Tokens such as <code>twice</code> (brave), <code>infinity</code> (unbreakable), <code>poison</code>, <code>crit0</code>, <code>magsw</code>, <code>heroonly</code>, <code>sfxseal</code>; 36 are recognised, unknown ones are ignored</td></tr>
    <tr><td><code>0x30</code>, <code>0x34</code></td><td>Two categories</td><td>What the weapon is effective against: <code>fly</code> on bows and wind, <code>beast</code> on fire, <code>dragon</code> on thunder, <code>armor</code>, <code>knight</code>, <code>alize</code> (laguz)&amp;hellip; and <code>doorbreak</code> on axes</td></tr>
    <tr><td><code>0x38</code>, <code>0x3C</code></td><td>Effects</td><td><code>EID_</code> use/spell effect and weapon effect</td></tr>
    <tr><td><code>0x40</code></td><td>Cost</td><td>16-bit price per use</td></tr>
    <tr><td><code>0x42</code>&amp;ndash;<code>0x48</code></td><td>Uses, might, hit, weight, crit, min range, max range</td><td>Max range 255 = Magic / 2</td></tr>
    <tr><td><code>0x49</code></td><td>Icon</td><td>Item icon number <em>n</em>: cell 96 + <em>n</em> of the 24×24 item sheet in <code>window/icon.tpl</code> (Iron Sword 0, the coin 186). Items may share an icon</td></tr>
    <tr><td><code>0x4A</code></td><td>Weapon EXP</td><td>Weapon experience per use</td></tr>
    <tr><td><code>0x4B</code>&amp;ndash;<code>0x54</code></td><td>Stat bonuses</td><td>Signed HP, Str, Mag, Skl, Spd, Lck, Def, Res, Mov, Con while equipped (Ragnell Def +5); permanent on stat boosters</td></tr>
    <tr><td><code>0x55</code>&amp;ndash;<code>0x5C</code></td><td>Growth modifiers</td><td>Signed growth-rate changes while equipped (Iron Sword Str &amp;minus;5, Skl +5, Spd +5, Res &amp;minus;5)</td></tr>
    <tr><td><code>0x5D</code></td><td>Trail colour</td><td>One of nine attack-trail colours (poison weapons are purple)</td></tr>
    <tr><td><code>0x5E</code>&amp;ndash;<code>0x5F</code></td><td>Padding</td><td>Never read</td></tr>
  </tbody></table>
</div>

## Which half of the inventory an item goes to

  A unit carries eight items: slots 0–3 hold weapons, tomes and staves, slots 4–7 everything else. When an item is loaded the game derives a few capability bits from its weapon type: physical weapons (sword, lance, axe, bow, knife and laguz strikes) are marked as weapons, fire, thunder and wind as magic weapons, a `rod` item with might as a light tome and one without might as a staff, `item` as a consumable and `acc` as an accessory. Giving an item (in a script, or as a reward) puts weapons, tomes and staves in the first free slot of the first half and the rest in the second half; when that half is full the item is not added. <span class="confidence confidence--confirmed">confirmed</span>

## How weapon properties enter combat

- **Might** contributes to Attack before defense is subtracted.
- **Type** also selects which pair of stats the attack uses at all: most values compare Strength against Defense, while a specific small range of values switches the whole exchange to Magic against Resistance.
- **Hit** contributes to the displayed hit rate used by the two-roll hit test.
- **Weight** participates in the effective-Speed side of doubling rather than directly scheduling strikes.
- **Rank** becomes a minimum weapon EXP that the unit's weapon experience in that type must reach.
- **Effectiveness** compares the categories of the equipped weapon and item with the categories of the target's class and can double the weapon's Might (see [Combat Resolution](./combat-mechanics.md)).
- **Special flags** can create Brave-style extra strikes or suppress effectiveness.

  The same table includes `IID_RAGNELL` and `IID_ALONDITE`, while siege-weapon actions identify placed weapons such as `IID_ONAGER`. See [Map Actions](./map-actions.md) for ballista/Shoot behavior.

## Forged weapon instances

  A forged weapon is an ordinary item instance plus a 1-based index into the runtime forge-record pool. The pool has 48 slots, each 0x18 bytes. The record stores a custom name, signed stat-adjustment steps, and the weapon's own attack-trail colour (four RGBA bytes, grey `80 80 80 FF` by default, picked by the player in the forge menu) used instead of the item's trail colour. While the player edits a forge, the game works on a temporary record; confirming copies it into a free slot and frees the temporary one. A free record has allocation marker 0; an allocated record has marker 1.

<div class="table-wrap">
<table><thead><tr><th>Forge field</th><th>Combat interpretation</th></tr></thead><tbody>
    <tr><td>Might step</td><td><code>max(1, base_might + step)</code></td></tr>
    <tr><td>Hit step</td><td><code>max(1, base_hit + 5 * step)</code></td></tr>
    <tr><td>Critical step</td><td><code>max(0, base_critical + 3 * step)</code></td></tr>
    <tr><td>Weight-reduction step</td><td><code>max(1, base_weight - step)</code></td></tr>
  </tbody></table>
</div>

  The getters clamp only the lower bound and then return an 8-bit result; they do not perform an additional upper saturation to 255. The normal forge UI may still restrict which step values a player can enter. Applying a forge result replaces the stored four step values rather than adding to any previous adjustment.

!!! note "Forge inventories are a grid"
    Each chapter's [forge section](../formats/shop-format.md) is a grid of 5 weapon families by 9 bases (`MDV_IRN` Iron, `MDV_SLM` Slim, `MDV_STL` Steel, `MDV_SLV` Silver, `MDV_HND` Thrown, and the four tome elements); each cell names the weapon forged from that base, for example `IID_IRONSWORD`/`MDV_IRN`. <span class="confidence confidence--confirmed">confirmed</span>

## How a weapon gets its battle model

  A weapon's 3D model is not referenced by the item record. When a battle starts, the game takes the equipped item's ID without its `IID_` prefix (`IRONSWORD`) and opens the table `xwp/IRONSWORD.dbx` inside [zdbx.cmp](../formats/zdbx.md). The table's `Model` block names a folder and model (`xwp/IRONSWORD`, `IRONSWORD`), and the game loads that pack: `xwp/ironsword/ironsword.cmp`, holding a skeleton, a mesh and a texture. The table's `Weapon` block gives the kind (0 sword, 3 bow, 4 magic, 9 arrow) and whether it flies as a missile; a tome's table has only this block and its spell effect. <span class="confidence confidence--confirmed">confirmed</span>

  If the table is missing, no weapon is made for the battle. In the shipped game this happens to the Devil Axe, whose model folder exists without a table, and to the four ballistae. A forged weapon's preview in the forge uses `xwp/forge/<name>_b.cmp` instead; 16 weapons have one. Bows are the only weapons drawn with bending (skinned) geometry, so the string can be drawn back.

## Where item information lives

<div class="table-wrap">
<table><thead><tr><th>Information</th><th>Location</th></tr></thead><tbody><tr><td>Definition and combat properties</td><td><a class="wl" href="../../formats/fe8data/">FE8Data.bin</a> item table</td></tr><tr><td>Chapter inventory</td><td><a class="wl" href="../../formats/dispo-format/">dispos.cmp</a> item slots</td></tr><tr><td>Shop availability</td><td><a class="wl" href="../../formats/shop-format/">shop inventory sections</a></td></tr><tr><td>Item icon</td><td><code>window/icon.tpl</code>, first image, cell 96 + icon (see <a class="wl" href="../graphics-system/">Graphics &amp; Images</a>)</td></tr><tr><td>Battle model</td><td><a class="wl" href="../../formats/zdbx/"><code>xwp/&lt;NAME&gt;.dbx</code></a> in <code>zdbx.cmp</code>, which names the pack <code>xwp/&lt;folder&gt;/&lt;model&gt;.cmp</code></td></tr><tr><td>Current durability</td><td>Runtime/save inventory instance</td></tr></tbody></table>
</div>

## Special properties

<div class="table-wrap">
<table><thead><tr><th>Property</th><th>Carried by</th><th>Effect</th></tr></thead><tbody>
    <tr><td><code>sealcrit</code></td><td>Alondite, Ragnell, Gurgurant, Lion's claws, kings' beaks</td><td>Its wielder cannot be critted</td></tr>
    <tr><td><code>weakA</code></td><td>Ragnell, Lion's claws, dragon breaths, kings' beaks</td><td>Can damage the blessed-armour units (see <a class="wl" href="../combat-mechanics/">Combat Resolution</a>)</td></tr>
    <tr><td><code>stormsw</code></td><td>Alondite, Ragnell, Gurgurant</td><td>Plays the ranged sword-wave battle animation</td></tr>
    <tr><td><code>flutter</code></td><td>Vortex</td><td>Plays the Vortex animation; treated as a long-range attack in battle</td></tr>
    <tr><td><code>valuable</code></td><td>Unique and legendary weapons, Knight Ring</td><td>Cannot be sold or discarded</td></tr>
    <tr><td><code>JH</code></td><td>Demi Band</td><td>Halves the laguz transformation bonus to Str, Mag, Skl, Spd, Def and Res</td></tr>
    <tr><td><code>noneart</code></td><td>Boots</td><td>No effect found in the executable <span class="badge open">open</span></td></tr>
  </tbody></table>
</div>
