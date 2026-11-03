---
id: "dispo-format"
title: "Dispo Format"
description: "Who spawns on a map, as what class, carrying what — the file to edit for chapter design"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Chapter data","Editable"]
aliases: ["tellius_archive.html#/dispo-format"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/dispo-format.md"
---
# Dispo Format

*Who spawns on a map, as what class, carrying what — the file to edit for chapter design*

Deployment data — who appears on a chapter's map, where, as what class, at what level, carrying what items, with what AI. Each `dispos.cmp` decompresses ([LZ10](./lz10.md)) to a [pack archive](./pack-archive.md) holding four [Labeled Section](./labeled-section.md) files, `dispos_c.bin`, `dispos_n.bin`, `dispos_h.bin` and `dispos_m.bin`, all loaded with the map. Their sections are named groups of units — `bmap02_mikata_c` (the player army), `bmap02_first_n` (the enemies at the start), `bmap02_z01_n` (a reinforcement wave) — each a list of fixed-size **0x6C-byte, 48-field** unit records.

## Which groups appear

Nothing appears by itself: the chapter's [event script](../systems/events-scripting.md) deploys a group by name. A `_c` group is called directly and appears on every difficulty; the `_n`, `_h` and `_m` versions of a group are passed together to a helper that picks one by difficulty. A group that no script names is never seen.

## How a record becomes a unit

The game reads each record into a runtime placement record, then creates the unit: it looks up the character and class by name, puts the unit in its army, sets its level, grows it to that level with the class's growth rates when the record asks for autolevelling, adds the record's stat bonuses, gives it the items and skills, and sets its AI. The unit appears on the spawn tile and walks to the destination tile (the nearest free tile from it) — the Prologue's Ike appears at (6, 7) and walks to (3, 9); a unit that stands still has both tiles equal. Tiles use the map's full [grid](../systems/map-grid.md), border included; a record whose tiles fall outside the map is skipped.

## Example: Chapter 1's boss

Zawanar's record names his character and class, sets level 4, army 1 (enemy), autolevel, a flag on his first item (the one he drops), and stat bonuses of HP &minus;11, Str +6, Skl +1, Spd &minus;2, Def +3 on top of what autolevelling gives him.

<div class="table-wrap">
<table class="tight"><thead><tr><th>Field</th><th>Name</th><th>Meaning</th><th></th></tr></thead><tbody>
    <tr><td class="num">0 / 1</td><td><code>pid</code> / <code>jid</code></td><td>Character and class; no class means the character's own</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">2</td><td>&amp;mdash;</td><td>Not read</td><td><span class="badge confirmed">unused</span></td></tr>
    <tr><td class="num">3&amp;ndash;10</td><td><code>item0..7</code></td><td>Inventory, up to eight items</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">11&amp;ndash;15</td><td><code>skill0..4</code></td><td>Skills added to the character's and class's own</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">16&amp;ndash;18</td><td>&amp;mdash;</td><td>Not read</td><td><span class="badge confirmed">unused</span></td></tr>
    <tr><td class="num">19&amp;ndash;26</td><td><code>bonus_hp..res</code></td><td>Signed stat bonuses: HP, Str, Mag, Skl, Spd, Lck, Def, Res</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">27</td><td><code>laguz_gauge</code></td><td>Starting laguz gauge (nonzero values below 20)</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">28&amp;ndash;30</td><td><code>seq_attack/move/heal</code></td><td>AI behavior scripts (<code>SEQ_*</code>, <a class="wl" href="../cp-data-format/">cp_data.bin</a>) — always <code>SEQ_NO*</code> on player units</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">31</td><td><code>mtype</code></td><td>Movement AI (<code>MTYPE_*</code>, <a class="wl" href="../cp-data-format/">cp_data.bin</a>)</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">32&amp;ndash;33</td><td><code>pos_x/y</code></td><td>Spawn tile</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">34&amp;ndash;35</td><td><code>pos2_x/y</code></td><td>Tile the unit walks to after appearing</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">36</td><td><code>level</code></td><td>Level; when the class is the character's own and the character's base level is higher, the base level wins</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">37</td><td><code>faction</code></td><td>Army: 0 player, 1 enemy, 2 ally/other</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">38</td><td><code>flags</code></td><td><code>0x01</code> autolevel; <code>0x02</code> hold position; <code>0x04</code> commander of its army; <code>0x08</code> a reinforcement appears even if the character isn't in play; <code>0x40</code> cannot enter bridge-cover tiles (see below)</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">39</td><td><code>ai_order</code></td><td>Enemy-phase turn order: lower acts first (0 on player units, 0&amp;ndash;81 on enemies)</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td class="num">40&amp;ndash;47</td><td><code>item0..7_flag</code></td><td>A flag per item — set on the items bosses drop</td><td><span class="badge strong"></span></td></tr>
  </tbody></table>
</div>

## Around the records

A section starts with a 4-byte header: its unit count, a mode byte (4), a byte that lets units appear on occupied tiles, and the group's army (see below). After the sections come the label pool — the `PID_`/`JID_`/`IID_`/`SID_`/`SEQ_`/`MTYPE_` strings the records point at — then a relocation list of every place that holds such a pointer, then the section table and names. The first section of every file, `<map>_date_<x>`, holds no units: it points at a date string. Because the game looks labels up by their text, a record can name any character, class, item or skill in [FE8Data.bin](./fe8data.md); adding one means growing the pool and the relocation list and updating the header's sizes together.

## The flags

<div class="table-wrap">
<table class="tight"><thead><tr><th>Bit</th><th>Effect</th><th>Used on</th></tr></thead><tbody>
    <tr><td class="num"><code>0x01</code></td><td>Autolevel: the unit grows from its base stats to its level with the class's growth rates</td><td>Most generic enemies</td></tr>
    <tr><td class="num"><code>0x02</code></td><td>Hold position: the AI never moves the unit. It still attacks, heals or uses items from the tile it stands on. The same AI check also covers some status conditions</td><td>Cutscene actors and a few stationary enemies (Chapter 1's Zawanar)</td></tr>
    <tr><td class="num"><code>0x04</code></td><td>Commander: the leader of the unit's army (see below)</td><td>Ike in every player group, each chapter's boss</td></tr>
    <tr><td class="num"><code>0x08</code></td><td>A reinforcement appears even when the character is not already in play</td><td>Reinforcements</td></tr>
    <tr><td class="num"><code>0x40</code></td><td>Bridge-cover barrier: movement onto terrain 55 (&amp;ldquo;bridge cover&amp;rdquo;, normally cost 1) costs 48, more than any unit has</td><td>Every unit except fliers (Chapter 23's dragon and pegasus knights, Jill) and a few cutscene actors</td></tr>
    <tr><td class="num"><code>0x10</code>, <code>0x20</code></td><td>Let the AI use a Door Key (<code>0x10</code>) or a Chest Key (<code>0x20</code>); no vanilla record sets them</td><td>&amp;mdash; <span class="badge confirmed"></span></td></tr>
  </tbody></table>
</div>

## Armies and commanders

The last byte of a group's header names its **army**: an index into the 30 army names in [FE8Data.bin](./fe8data.md) (`GroupData`). Every unit the group deploys joins that army; 0 leaves the unit's army unchanged.

<div class="table-wrap">
<table class="tight"><thead><tr><th>Id</th><th>Army</th><th>Id</th><th>Army</th><th>Id</th><th>Army</th></tr></thead><tbody>
    <tr><td class="num">1</td><td>Crimean Army</td><td class="num">11</td><td>Begnion Army</td><td class="num">21</td><td>Prisoners</td></tr>
    <tr><td class="num">2, 3</td><td>Daein Army</td><td class="num">12</td><td>Stray pegasus knights</td><td class="num">22</td><td>Begnion reinforcements</td></tr>
    <tr><td class="num">4</td><td>Gallia Army</td><td class="num">13</td><td>Merchant caravan</td><td class="num">23</td><td>Militia</td></tr>
    <tr><td class="num">5</td><td>Bandits</td><td class="num">14</td><td>Laguz Liberation Army</td><td class="num">24</td><td>Tanith's reinforcements</td></tr>
    <tr><td class="num">6</td><td>Pirates</td><td class="num">15</td><td>Duke Tanas's army</td><td class="num">25</td><td>Mysterious army</td></tr>
    <tr><td class="num">7</td><td>Elincia's reinforcements</td><td class="num">16</td><td>Thieves</td><td class="num">26</td><td>Daein remnants</td></tr>
    <tr><td class="num">8</td><td>Tanith's reinforcements</td><td class="num">17</td><td>Kilvas Army</td><td class="num">27</td><td>Mysterious force</td></tr>
    <tr><td class="num">9</td><td>Kariwa bandits</td><td class="num">18</td><td>Phoenicis Army</td><td class="num">28</td><td>Fighters</td></tr>
    <tr><td class="num">10</td><td>Greil Mercenaries</td><td class="num">19</td><td>Truly unaffiliated</td><td class="num">29</td><td>Heron clan</td></tr>
    <tr><td></td><td></td><td class="num">20</td><td>Palmeny monks</td><td class="num">30</td><td>Stray mercenaries</td></tr>
  </tbody></table>
</div>

  (Names translated from the Japanese keys; the game shows the text of its message files.) The map's army list sorts units by army, and the living unit flagged `0x04` is that army's commander. A commander with [Charisma](../systems/skills.md) gives the units of its own army within 3 tiles +5 Hit and +5 Avoid (never on the player side); each enemy with Horror within 3 tiles takes 5 off Hit and Critical. Player groups use 10 (Greil Mercenaries) early on, then 1 (Crimean Army). Event scripts read and change a unit's army with `UnitGet`/`UnitSet` field 38, and a unit moved to another side by `UnitTransferToForce` takes that side's army. <span class="confidence confidence--confirmed">engine</span>

## Enemy turn order

At the start of each AI phase the game scores every unit of the acting side and moves them lowest score first. Field 39 fills the top of the score, so it sets the order outright. Among units with the same value, faster units and units carrying staves or weaker weapons go earlier. Vanilla leaves most units at 0 and gives higher numbers to later waves and bosses, so reinforcements and commanders act after the front line.

  See [Chapters](../systems/chapters.md) for how this file fits together with the other three per-chapter files, and [Characters](../systems/characters.md)/[Skills](../systems/skills.md) for what a resolved `PID_`/`SID_` value means at the game-system level.
