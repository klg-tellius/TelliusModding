---
id: "fe8anim"
title: "FE8Anim.bin"
description: "The map-model registry: each animation ID's folder, weapon, textures and actions"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Graphics","Animation","Registry"]
aliases: ["tellius_archive.html#/fe8anim"]
status: "published"
last_reviewed: "2026-10-27"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/fe8anim.md"
---
# FE8Anim.bin

*The map-model registry: each animation ID's folder, weapon, textures and actions*

A `.ga` [animation](./model-formats.md) file has no embedded name or identity. **FE8Anim.bin** maps a symbolic `AID_` animation name to the `ymu/` folder holding the map model, the weapon it is for, the texture each army uses and the actions the folder has.

## How a unit finds its map model

A character record holds an unpromoted and a promoted base animation ID (`AID_FIGHTER_BO`, Boyd's); a unit without one uses its class's. The engine appends the weapon suffix (`AID_FIGHTER_BO_AX`), finds that record, and loads `ymu/<folder>/pack.cmp`, the action's `.ga` and the army's texture. A missing record or pack falls back to `AID_DUMMY_N`. The engine registers every record by name at boot, so the record order does not matter, and a record added to the file works like a vanilla one. <span class="confidence confidence--confirmed">engine + in game</span> Battle-scene models are found through `jobList.dbx` instead (see [ZDBX & DBX](./zdbx.md)).

## Example

An `AID_..._SW` entry resolves to a class folder and weapon enum 1, so it is eligible for the sword presentation of that class. A tagged form such as `AID_KNIGHT_KE_N` can select Kieran-specific unarmed or neutral presentation without changing the Knight class definition.

!!! note "Container, shared with FE8Effect.bin"
    The standard `0x20`-byte header (file size, data size, pointer count, symbol count), a data section, the list of every pointer field's offset, and one symbol, `AnimData`. The data section starts with the record count (508), then the records, then the pool of every name they point to, sorted and without duplicates. <span class="confidence confidence--confirmed">confirmed</span>

  Every one of the 508 records resolves cleanly to an `(AID_ name, folder)` pair — 508/508, zero exceptions.

<div class="table-wrap">
<table class="tight"><thead><tr><th>Offset</th><th>Meaning</th></tr></thead><tbody>
    <tr><td class="num">0x00</td><td>Pointer to the record's <code>AID_</code> name: a base animation ID plus the weapon suffix (<code>AID_KNIGHT_SW</code>)</td></tr>
    <tr><td class="num">0x04</td><td>Pointer to the <code>ymu/</code> folder name, always ending <code>/</code></td></tr>
    <tr><td class="num">0x08</td><td>Weapon type, see below</td></tr>
    <tr><td class="num">0x09</td><td>Blend weight: when the unit switches animation on the map, the old and new animations cross-fade over 16 frames for a weight of 20 or less, rising evenly to 32 frames at 40 and above. Most classes use 20, armoured units and lions 40, dragons 60 <span class="badge confirmed">engine</span></td></tr>
    <tr><td class="num">0x0B</td><td>A signed byte, nearly one value per folder (negative on most humans, zero on children and dragons, positive on fliers); nothing in the map-animation code reads it <span class="badge open">open</span></td></tr>
    <tr><td class="num">0x0C</td><td>Four texture numbers, one per army (player, enemy, other, ally): the unit's texture is <code>tex_&lt;n&gt;.tpl</code> in the folder. Generic fighters use 32, 97, 162 and 227 (four army colours); Boyd's records repeat 4. Every number names an existing file <span class="badge confirmed">engine + in game</span></td></tr>
    <tr><td class="num">0x10</td><td>Action mask: bit <em>n</em> is set when the folder has action <em>n</em> for this weapon — <code>wait</code>, <code>move</code>, <code>atk1</code>, <code>atk2</code>, <code>crit</code>, <code>rod</code>, <code>tackle</code>, <code>escape</code>, <code>ready</code>, <code>damage</code>, <code>trans</code>, <code>dead</code>, <code>magic1</code>, <code>magic2</code>, <code>crit2</code>, <code>move2</code>, <code>event</code>. An action whose bit is clear plays <code>tackle</code>. Every set bit has its file; 33 animation files on the disc have no bit and are never played <span class="badge confirmed">engine + files</span></td></tr>
  </tbody></table>
</div>

  The weapon type is the index into the engine's suffix table, confirmed with zero exceptions by cross-checking every `AID_` name's trailing suffix against its own byte value across all 86 real class folders:

<div class="table-wrap">
<table class="tight"><thead><tr><th>Suffix</th><th>Value</th><th>Weapon</th></tr></thead><tbody>
    <tr><td><code>N</code></td><td class="num">0</td><td>Unarmed</td></tr><tr><td><code>SW</code></td><td class="num">1</td><td>Sword</td></tr>
    <tr><td><code>AX</code></td><td class="num">2</td><td>Axe</td></tr><tr><td><code>HA</code></td><td class="num">3</td><td>Hand axe</td></tr>
    <tr><td><code>SP</code></td><td class="num">4</td><td>Spear</td></tr><tr><td><code>JA</code></td><td class="num">5</td><td>Javelin</td></tr>
    <tr><td><code>BW</code></td><td class="num">6</td><td>Bow</td></tr>
  </tbody></table>
</div>

  A character with no animation ID of its own uses its class's: the class record names one (the Ranger `AID_LORD`, the Fighter `AID_FIGHTER`). A name that finds no record, or an empty one, gives `AID_DUMMY_N`, a black stand-in. <span class="confidence confidence--confirmed">engine + in game</span>

  A texture can live inside the folder's `pack.cmp` (`tex_4.tpl` of `armor/`, the named characters' colours) or loose beside it (the generic army colours). A recolour gets an unused number as a loose `tex_<n>.tpl` and the record's texture number pointed at it; the app's colour variants do this. <span class="confidence confidence--strong">files + engine path; not yet seen in game</span>

  A new map model can be given to one character without touching the rest of its class: records copied under a new base ID and pointing at a copied folder, and the character's animation ID pointed at that new name. In the Prologue, Boyd (`PID_BOLE_MAP1`) was given `AID_FIGHTER_BOX` with a recoloured copy of his texture, and the game drew it on the map. <span class="confidence confidence--confirmed">in game</span>

  Many `AID_` names carry a two-letter tag between class and weapon suffix (`AID_KNIGHT_KE_N`), consistent with a character-specific override. About 29 tags occur, including unambiguous cast initials such as `IK` (Ike), `BO` (Boyd), `OS` (Oscar), `KE` (Kieran), and `TA` (Titania). <span class="confidence confidence--strong">strong evidence</span> A complete tag-to-character table remains open.
