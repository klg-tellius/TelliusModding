---
id: "fe8data"
title: "FE8Data.bin"
description: "The shared definitions from which characters, classes, items, and skills are built"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Core data","Balance"]
aliases: ["tellius_archive.html#/fe8data"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/fe8data.md"
---
# FE8Data.bin

*The shared definitions from which characters, classes, items, and skills are built*

**FE8Data.bin is the game's catalog of reusable definitions.** It answers questions such as “What are Ike's personal growths?”, “What can a Ranger equip?”, “How much might does an Iron Sword have?”, and “Which parameters belong to Sol?” It does not store the current HP of the Ike in a save or where an enemy stands in a chapter; those are mutable runtime and deployment data.

## How the four main tables work together

  Four tables hold the cast and its equipment:

- A **character** record identifies a person and links to a starting class, portrait, personal skills, bonuses, and growths.
- A **class** record defines shared movement, weapon access, caps, innate skills, and promotion relationships.
- An **item** record defines a weapon or usable item's identity and mechanical properties.
- A **skill** record defines a skill identifier, display/help keys, restrictions, and behavior parameters.

  The records refer to one another through labels such as `PID_IKE`, `JID_RANGER`, `IID_IRONSWORD`, and `SID_SUNTRICK`. A stored pointer leads into the file's label pool; the readable label is the stable identity used across other files.

## Example — resolving Ike

1. Read the first character record and resolve its `PID_` pointer to `PID_IKE`.
2. Resolve its `JID_` pointer to `JID_RANGER`.
3. Use the class table to find Ranger's movement, weapon ranks, caps, and innate skills.
4. Resolve personal `SID_` pointers through the skill table.
5. When a chapter deploys `PID_IKE`, the engine combines these definitions with that chapter's inventory and position and the save's mutable progression.

!!! info "Do not treat FE8Data.bin as a save file"
    The file defines templates shared by every new game and chapter. Current HP, gained experience, consumed durability, temporary status, and chapter position belong to runtime/save structures.

## Physical layout

  `FE8Data.bin` is uncompressed and sits directly under `files/`; there is no LZ10 or [pack](./pack-archive.md) layer. “FE8” is an internal filename retained by the released game. The offsets below apply to the US release.

<div class="table-wrap">
<table><thead><tr><th>Table</th><th>Start</th><th>Record size</th><th>Count</th><th>Detail article</th></tr></thead><tbody>
    <tr><td>Characters</td><td><code>0x30</code></td><td><code>0x54</code> (84B)</td><td class="num">340</td><td><a class="wl" href="../../systems/characters/">Characters</a></td></tr>
    <tr><td>Classes</td><td><code>0x6FC4</code></td><td><code>0x64</code> (100B)</td><td class="num">115</td><td><a class="wl" href="../../systems/classes/">Classes</a></td></tr>
    <tr><td>Items</td><td><code>0x9CB4</code></td><td><code>0x60</code> (96B)</td><td class="num">189</td><td><a class="wl" href="../../systems/items-weapons/">Items &amp; Weapons</a></td></tr>
    <tr><td>Skills</td><td><code>0xE398</code></td><td><code>0x28</code> (40B)</td><td class="num">98</td><td><a class="wl" href="../../systems/skills/">Skills</a></td></tr>
    <tr><td>Terrain types</td><td>symbol <code>TerrainData</code> + 4</td><td><code>0x0C</code> (12B)</td><td class="num">77</td><td>below</td></tr>
  </tbody></table>
</div>

  The file is a named-section container: after the `0x20`-byte header (file size, data size, pointer count, symbol count) come the data, the list of every pointer field, and a table naming each section. A table's name points at a 4-byte record count; the records follow it. <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table class="tight"><thead><tr><th>Section</th><th>Holds</th></tr></thead><tbody>
    <tr><td><code>DatabaseHead</code></td><td>The build time (<code>2005/06/29 10:11:21</code>) and author (<code>金子</code>, Kaneko), printed to the debug console at boot</td></tr>
    <tr><td><code>PersonData</code>, <code>JobData</code>, <code>ItemData</code>, <code>SkillData</code></td><td>Characters, classes, items, skills; each skill's scroll and restriction lists follow the skill records</td></tr>
    <tr><td><code>DivineData</code>, <code>RelianceData</code>, <code>KiznaData</code></td><td>Affinity bonuses, support lists and bonds (<a class="wl" href="../../systems/support-system/">Support System</a>)</td></tr>
    <tr><td><code>GameData</code></td><td>Seven difficulty constants, below</td></tr>
    <tr><td><code>TerrainData</code></td><td>Terrain types and their stats blocks, below</td></tr>
    <tr><td><code>BattleTerrData</code>, <code>BattleSkyData</code></td><td>Battle backdrops, below</td></tr>
    <tr><td><code>ChapterData</code></td><td>One record per chapter (<a class="wl" href="../../systems/chapters/">Chapters</a>)</td></tr>
    <tr><td><code>GroupData</code></td><td>The army names (<a class="wl" href="../../systems/armies-allegiance/">Armies &amp; Allegiance</a>)</td></tr>
  </tbody></table>
</div>

## Address convention

  Record offsets and pointers use a base immediately after the 0x20-byte file header. To convert a documented header-relative position to an absolute file offset, add `0x20`. Multi-byte values are big-endian. Every eight-value stat block—growths, caps, and base/personal stats—uses **HP, Str, Mag, Skl, Spd, Lck, Def, Res** order.

## Terrain types

  The `TerrainData` table lists the 77 terrain types a map tile can have. Each record holds the Japanese name that [a map's tile records](./map-format.md) point to (`平地`), the message key of the name shown in the terrain window (`MT_平地`, “Plain”), and a pointer to a 24-byte stats block shared by similar types. The game finds a tile's type by matching its name against this table, then reads the block for the unit standing there. <span class="confidence confidence--confirmed">engine + in game</span>

<div class="table-wrap">
<table class="tight"><thead><tr><th>Block bytes</th><th>Meaning</th></tr></thead><tbody>
    <tr><td class="num">0, 1, 2</td><td>Avoid, defence, resistance bonus <span class="badge confirmed">in game</span></td></tr>
    <tr><td class="num">3, 4, 5</td><td>The same bonuses for units with a particular movement trait (plausibly fliers) <span class="badge strong">engine</span></td></tr>
    <tr><td class="num">6</td><td>HP healed at the start of each turn, as a percentage of max HP: 10 on Heal, Healhedge, Throne, Castle and Fort <span class="badge confirmed">engine</span></td></tr>
    <tr><td class="num">7</td><td>Object tile — roofs, trees, fences, small objects, buildings, holes, sandbags: the game never picks such a tile when it looks for the nearest free place to put a unit, and the AI's <a class="wl" href="../cp-data-format/">threat map</a> treats it as a tile no unit can stop on <span class="badge strong">engine</span></td></tr>
    <tr><td class="num">8&amp;ndash;22</td><td>Movement cost for each of 15 movement types; 255 = impassable <span class="badge confirmed">in game</span></td></tr>
  </tbody></table>
</div>

  A class's movement type — one byte of its record — picks which of the 15 cost columns its units use. <span class="confidence confidence--confirmed">engine</span> The 77 terrain types share only 13 stat blocks, so the plain-floor types, for example, all read the same one. Two more well-formed blocks sit in the file with no terrain type pointing at them.

<div class="table-wrap">
<table class="tight"><thead><tr><th>Type</th><th>Classes</th><th>Different from foot soldiers</th></tr></thead><tbody>
    <tr><td class="num">0&amp;ndash;2</td><td>Ike's Ranger and Hero; unpromoted and promoted infantry and archers</td><td>—</td></tr>
    <tr><td class="num">3, 4</td><td>Knight; General and Black Knight</td><td>Slower in desert and on shores and trails</td></tr>
    <tr><td class="num">5, 6</td><td>Mages and priests; sages and bishops</td><td>Desert costs 1</td></tr>
    <tr><td class="num">7, 8</td><td>Cavaliers; Paladins</td><td>Slower in thickets, desert and marsh</td></tr>
    <tr><td class="num">9</td><td>Pegasus, Falcon and Wyvern knights, bird laguz</td><td>Every terrain costs 1, water, cliffs and trees included</td></tr>
    <tr><td class="num">10, 11</td><td>Thieves; bandits and berserkers</td><td>Desert costs 1; bandits cross rivers and sea at 2</td></tr>
    <tr><td class="num">12, 13</td><td>Lion, Tiger and Cat; the three dragon tribes</td><td>Thickets cost 1; desert costs 1</td></tr>
    <tr><td class="num">14</td><td>The other laguz tiers, citizens, children</td><td>—</td></tr>
  </tbody></table>
</div>

  Painted onto the Prologue, Thicket gave avoid 10 and defence 1 at a movement cost of 2; Talisman defence 3 and resistance 3; Heal and Trail avoid 10 and defence 1. The type named “Fort” (`砦`) has no bonus and blocks every unit: in Path of Radiance it is a building units cannot enter (152 tiles on chapters 6 and 9), while the healing tile is Heal (`回復`). Several types share a display name (`平地`, `平地２`... are all “Plain”). The Gate and the breakable door are looked up as the ordinary Door, and five types (Objective, Target, Sanctuary, Defend, Visit) mark chapter goals.

## Difficulty constants

  `GameData` holds seven rows of four bytes, one per difficulty (Normal, Hard, Maniac, Easy). <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table class="tight"><thead><tr><th>Row</th><th>N / H / M / E</th></tr></thead><tbody>
    <tr><td>Battle EXP mode bonus</td><td>20 / 15 / 30 / 30</td></tr>
    <tr><td>Battle EXP level constant</td><td>20 / 20 / 30 / 30</td></tr>
    <tr><td>Promoted effective-level bonus</td><td>0 / 0 / 0 / 0</td></tr>
    <tr><td>Boss EXP bonus</td><td>30 / 25 / 40 / 40</td></tr>
    <tr><td>Thief EXP bonus</td><td>20 / 20 / 30 / 30</td></tr>
    <tr><td>Transformed laguz growth bonus</td><td>10 / 13 / 10 / 10</td></tr>
    <tr><td>Class critical bonus</td><td>15 / 15 / 15 / 15</td></tr>
  </tbody></table>
</div>

  See [Combat Resolution](../systems/combat-mechanics.md) for how these enter the EXP formula.

## Battle backdrops

  The scene behind a battle depends on the map and on the terrain the fight takes place on. `BattleTerrData` has one row per map (`bmap01`&hellip;`bmap31`, the trial maps, the tutorial and three alternate maps) and, in each row, one battle-scene name per terrain type (`map01_woods`, `map04_ship`, `garia_woods`&hellip;). A map without a matching row uses the first row, `Map6`. An empty terrain entry uses the first terrain entry in the selected row. `BattleSkyData` names the sky for each map weather (`sky_01`, `cloudy_01`, `night_01`, `sunset_01`, `sandstorm_01`&hellip;). <span class="confidence confidence--confirmed">engine</span>

## What to read next

  Use [Characters](../systems/characters.md) for the character-to-runtime-unit lifecycle, [Classes](../systems/classes.md) for class capabilities and promotion, [Items & Weapons](../systems/items-weapons.md) for item mechanics, and [Skills](../systems/skills.md) for ownership and native behavior. Those pages explain meaning; this page provides the shared binary map.

!!! warning "Known limits"
    Every byte has a known role. A few fields hold values the game never reads: one character word (always empty), two class bytes, a skill flag set on exactly the skills that have a scroll, three reserved skill bytes, and one header word. The class's menu name key is the only field whose use is inferred rather than traced. `system.cmp` also contains a copy of this file; the game loads that archive at boot and its file lookup searches loaded archives first, so the copy inside `system.cmp` is the one read. <span class="confidence confidence--strong">engine</span>
