---
id: "save-format"
title: "GameCube Save (.gci)"
description: "Memory-card container, CRC-checked save blocks, the shared system data and the tagged chapter-state stream"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Save Data","Container"]
aliases: ["tellius_archive.html#/save-format"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/save-format.md"
---
# GameCube Save (.gci)

*Memory-card container, CRC-checked save blocks, the shared system data and the tagged chapter-state stream*

A `.gci` file is a single GameCube memory-card entry: a 0x40-byte directory header followed by the game's payload. The header holds the game and company identifiers (`GFEE`, `01`), the internal filename `FIREEMBLEM8J`, timestamps, permissions, icon and banner metadata, and the number of card blocks used (19). There is no file-level checksum.

## Body layout

  After 0x2000 bytes of banner and icon images, the payload holds eight save blocks. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Body offset</th><th>Size</th><th>Use</th></tr></thead><tbody>
    <tr><td><code>0x2000</code> + <em>i</em> × <code>0x4000</code>, <em>i</em> = 0–5</td><td><code>0x4000</code> each</td><td>File blocks</td></tr>
    <tr><td><code>0x1A000</code>, <code>0x20000</code></td><td><code>0x6000</code> each</td><td>Checkpoint (suspend) blocks</td></tr>
  </tbody></table>
</div>

  Each file block names its file slot (0–4) in its header; the six blocks are shared by up to five slots. When the card is read at boot, the game discards every block whose checksum fails, keeps only the newest block (highest sequence number) of each slot and only the newer checkpoint, and frees the rest. A new save goes into a free block, and its sequence number is one more than the highest on the card. An interrupted save therefore leaves the slot's previous block in place. <span class="confidence confidence--confirmed">confirmed</span>

## Block header

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Size</th><th>Meaning</th></tr></thead><tbody>
    <tr><td><code>+0x00</code></td><td>64</td><td>Title and date text shown by the memory-card screen</td></tr>
    <tr><td><code>+0x40</code></td><td>4</td><td>Magic <code>"FE8J"</code></td></tr>
    <tr><td><code>+0x44</code></td><td>4</td><td>Version stamp <code>0x20050201</code></td></tr>
    <tr><td><code>+0x48</code></td><td>4</td><td>Sequence number</td></tr>
    <tr><td><code>+0x4C</code></td><td>4</td><td>Block size</td></tr>
    <tr><td><code>+0x50</code></td><td>4</td><td>CRC-32 of the block from <code>+0x70</code> to its end</td></tr>
    <tr><td><code>+0x58</code></td><td>8</td><td>Play time in console timer ticks (40.5 million per second)</td></tr>
    <tr><td><code>+0x60</code></td><td>1</td><td>Save kind: 2 file save, 3 checkpoint, 1 a consumed copy (half-written, never loaded)</td></tr>
    <tr><td><code>+0x61</code></td><td>1</td><td>Playthrough id, recorded in the system data when the game is finished</td></tr>
    <tr><td><code>+0x62</code></td><td>1</td><td>File slot 0–4</td></tr>
    <tr><td><code>+0x63</code></td><td>1</td><td>For a checkpoint, the file slot it suspends</td></tr>
    <tr><td><code>+0x64</code></td><td>1</td><td>Chapter number</td></tr>
    <tr><td><code>+0x65</code></td><td>1</td><td>Resume point (below)</td></tr>
    <tr><td><code>+0x66</code></td><td>1</td><td>Difficulty: 0 Normal, 1 Hard, 2 Maniac, 3 Easy</td></tr>
    <tr><td><code>+0x70</code></td><td>0x48</td><td>System data (below)</td></tr>
    <tr><td><code>+0xB8</code></td><td>rest</td><td>Tagged chapter-state stream</td></tr>
  </tbody></table>
</div>

  The checksum is standard CRC-32 (the same polynomial as ZIP and PNG). A block whose checksum doesn't match is treated as empty, so changing any byte from `+0x70` onward requires recomputing it. A stored checksum of `0x12345678` and save kind 1 skip the check. <span class="confidence confidence--confirmed">confirmed</span>

  The resume point decides where loading the block leads (see [Chapters](../systems/chapters.md)): <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table><thead><tr><th>Value</th><th>Saved from</th><th>Loading it</th></tr></thead><tbody>
    <tr><td>1</td><td>The base menu</td><td>Reloads the map and returns to the base</td></tr>
    <tr><td>2</td><td>Battle preparations</td><td>Reloads the map and returns to preparations</td></tr>
    <tr><td>3</td><td>New Game</td><td>Starts the first chapter</td></tr>
    <tr><td>4</td><td>The save after a victory</td><td>Starts the next chapter from its opening</td></tr>
    <tr><td>5, 6, 7</td><td>The end of part 1, 2 or 3 of a multi-part chapter</td><td>Continues with the next part</td></tr>
    <tr><td>8</td><td>A checkpoint (suspend)</td><td>Resumes the battle where it stopped</td></tr>
    <tr><td>10</td><td>A trial map</td><td>Starts that trial map</td></tr>
  </tbody></table>
</div>

## System data

  Header `+0x70` is a copy of the console-wide system data, written into every block. At boot the game takes it from the newest block that carries it. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Size</th><th>Meaning</th></tr></thead><tbody>
    <tr><td><code>+0x00</code></td><td>8</td><td><code>"SYSF"</code> and the version stamp</td></tr>
    <tr><td><code>+0x08</code></td><td>8</td><td>Random system id made with the data; a save is only written over data with the same id</td></tr>
    <tr><td><code>+0x10</code></td><td>2</td><td>Unlocks: bit 0 game finished (clear records, trial map 1), bits 1 and 2 trial maps 2 and 3, bits 4 and 5 trial maps 4–6. Finishing on Normal or Easy sets bit 0, Hard bits 0–1, Maniac bits 0–2.</td></tr>
    <tr><td><code>+0x12</code></td><td>30</td><td>Ids of the playthroughs that reached the ending; their count + 1 is the playthrough number shown on a new file</td></tr>
    <tr><td><code>+0x30</code></td><td>16</td><td>Characters met: one bit per character number below 128, set whenever a unit is deployed</td></tr>
    <tr><td><code>+0x40</code></td><td>3</td><td>Screen position X and Y and brightness (the Screen menu)</td></tr>
    <tr><td><code>+0x47</code></td><td>1</td><td>Last file slot used</td></tr>
  </tbody></table>
</div>

## The state stream

  From `+0xB8` the block is a sequence of four-character tags, each followed by the record its serializer writes. There are no length fields. Every record has a fixed size except `UNIP`, which takes 2 bytes per empty unit slot and 143 per used one, so the chunks after it move as the army grows. The rest of the block is zero. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Tag</th><th>Size</th><th>Contents</th></tr></thead><tbody>
    <tr><td><code>BMST</code></td><td><code>0x214</code></td><td>Party and chapter state, including the <a class="wl" href="../../systems/event-flags/">event flags</a></td></tr>
    <tr><td><code>MDST</code></td><td><code>0x20</code></td><td>Map display state (sight mode, weather, fog) and camera</td></tr>
    <tr><td><code>UNIP</code></td><td>159 slots</td><td>Every unit slot, player and enemy</td></tr>
    <tr><td><code>SOKO</code></td><td><code>0x320</code></td><td>The convoy: 200 item slots</td></tr>
    <tr><td><code>FWEP</code></td><td><code>0x480</code></td><td>The forged-weapon pool</td></tr>
    <tr><td><code>T  T</code></td><td><code>0x204</code></td><td>The map's tile records: doors, chests, villages, walls, ballistae</td></tr>
  </tbody></table>
</div>

## BMST — party and chapter state

<div class="table-wrap">
<table><thead><tr><th>Offset after tag</th><th>Size</th><th>Meaning</th></tr></thead><tbody>
    <tr><td><code>0x10</code></td><td>1</td><td>Chapter number</td></tr>
    <tr><td><code>0x11</code>, <code>0x12</code></td><td>1, 2</td><td>Army whose phase it is, turn number</td></tr>
    <tr><td><code>0x18</code>, <code>0x1C</code></td><td>4, 4</td><td>Gold, bonus experience</td></tr>
    <tr><td><code>0x20</code></td><td>0x30</td><td>The chapter's four objective text keys</td></tr>
    <tr><td><code>0x52</code>, <code>0x53</code></td><td>1, 1</td><td>Map cursor tile</td></tr>
    <tr><td><code>0x54</code></td><td>1</td><td>Resume point</td></tr>
    <tr><td><code>0x55</code></td><td>1</td><td>The base's opening event already ran</td></tr>
    <tr><td><code>0x56</code>, <code>0x57</code></td><td>1, 1</td><td>Deployment surplus, playthrough number</td></tr>
    <tr><td><code>0x58</code>, <code>0x60</code></td><td>8, 8</td><td>Play-time tick counters</td></tr>
    <tr><td><code>0x68</code>–<code>0x73</code></td><td>12</td><td>Soren's chapter report: gold earned, gold spent, Combat Exp, Bonus Exp (four signed 16-bit counters)</td></tr>
    <tr><td><code>0x74</code>, <code>0x84</code></td><td>16, 16</td><td>Tutorials unlocked and tutorials read (one bit each)</td></tr>
    <tr><td><code>0x9C</code></td><td>12</td><td>Options: four bytes of menu switches (every row of the Options menu, plus fixed growths, trial map and "show other units' moves"), grid thickness, brightness, screen position, music and sound volume, difficulty</td></tr>
    <tr><td><code>0xA8</code></td><td>12</td><td>The 96 event flag bits</td></tr>
    <tr><td><code>0xB4</code></td><td>0x140</td><td>Clear history: 40 entries of chapter, part flag, turns and play time in seconds</td></tr>
    <tr><td><code>0x1F4</code></td><td>0x18</td><td>Map name, <code>bmap02</code> or <code>trial_05</code></td></tr>
  </tbody></table>
</div>

  In a save made after a victory, the chapter number already points at the next chapter while the map name is still the map just won. Loading such a save starts the next chapter, which clears every chapter-local flag, so the chapter flag bits stored in it are leftovers. In base, preparation, part and checkpoint saves every bit is live. <span class="confidence confidence--confirmed">confirmed</span>

## UNIP — units

  A unit's position in the 159-slot unit table is its slot number, which the records use to link units together. Characters, classes and items are stored as their position in [FE8Data](./fe8data.md)'s tables, counting from 1, so a mod that reorders those tables changes what existing saves contain. A used slot holds: <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Size</th><th>Meaning</th></tr></thead><tbody>
    <tr><td><code>0</code>, <code>2</code></td><td>2, 2</td><td>Character and class numbers (0 = empty slot, 2 bytes only)</td></tr>
    <tr><td><code>4</code></td><td>1</td><td>Army: 0 player, 1 enemy, 2 ally, 3 other, 4 free, 5 reserve, 6 inactive, 7 removed</td></tr>
    <tr><td><code>5</code>–<code>7</code></td><td>3</td><td>Previous and next unit of the same army, carried unit</td></tr>
    <tr><td><code>8</code>–<code>14</code></td><td>7</td><td>Deployment group, level, experience (255 = none), laguz gauge, a 0–100 value, tile X and Y</td></tr>
    <tr><td><code>15</code>, <code>19</code></td><td>4, 4</td><td>State bits; temporary status and bonuses</td></tr>
    <tr><td><code>23</code>–<code>25</code></td><td>3</td><td>Current HP, build bonus, movement bonus</td></tr>
    <tr><td><code>26</code></td><td>8</td><td>HP, Str, Mag, Skl, Spd, Lck, Def, Res held on top of the class base</td></tr>
    <tr><td><code>34</code></td><td>8</td><td>Fixed-growth accumulators</td></tr>
    <tr><td><code>42</code></td><td>16</td><td>Skills: one bit per skill table index</td></tr>
    <tr><td><code>58</code></td><td>32</td><td>Eight item slots</td></tr>
    <tr><td><code>90</code></td><td>8</td><td>Weapon experience for sword, lance, axe, bow, fire, thunder, wind and staff (E 1, D 31, C 71, B 121, A 181, S 251)</td></tr>
    <tr><td><code>98</code></td><td>14</td><td>Battles, lifetime kills, kills on this map, tiles moved, two more counters, chapter of the last kill</td></tr>
    <tr><td><code>112</code></td><td>10</td><td><a class="wl" href="../../systems/support-system/">Support</a> points, one per support-list slot</td></tr>
    <tr><td><code>122</code></td><td>15</td><td><a class="wl" href="../cp-data-format/">AI</a> script choices, steps, flags and turn order</td></tr>
    <tr><td><code>137</code></td><td>6</td><td>One more value and padding</td></tr>
  </tbody></table>
</div>

  An item slot, in a unit or in the convoy, is the item number (2 bytes), its remaining uses, and a flag byte: `0x80` equipped, `0x40` dropped when its holder is defeated, and the low six bits the forge record (1–48) of a forged weapon. <span class="confidence confidence--confirmed">confirmed</span>

## FWEP — forge record pool

  The forged-weapon pool is copied as raw bytes: 48 records at a stride of `0x18`.

<div class="table-wrap">
<table><thead><tr><th>Record offset</th><th>Meaning</th></tr></thead><tbody>
    <tr><td><code>+0x00</code></td><td>Allocation marker, 0 free and 1 allocated</td></tr>
    <tr><td><code>+0x01..0x0F</code></td><td>Custom weapon name; first byte zero means no custom name</td></tr>
    <tr><td><code>+0x10</code></td><td>Signed might steps</td></tr>
    <tr><td><code>+0x11</code></td><td>Signed hit steps; each step is worth 5 hit</td></tr>
    <tr><td><code>+0x12</code></td><td>Signed critical steps; each step is worth 3 critical</td></tr>
    <tr><td><code>+0x13</code></td><td>Signed weight-reduction steps</td></tr>
    <tr><td><code>+0x14..0x17</code></td><td>Attack-trail colour (RGBA) picked in the forge, <code>80 80 80 FF</code> by default</td></tr>
  </tbody></table>
</div>

## T  T — map tile records

  64 records of 8 bytes and a count. Each record names a tile (X, Y), a type, a subtype and four value bytes; the chapter scripts fill the table when the map starts, and the map updates it as things happen. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Type</th><th>Meaning</th></tr></thead><tbody>
    <tr><td>4</td><td>Breakable wall (current and maximum HP)</td></tr>
    <tr><td>7</td><td>Ballista (item and uses)</td></tr>
    <tr><td>9, 10</td><td>Pit, rolling rock</td></tr>
    <tr><td><code>0x21</code>–<code>0x25</code></td><td>Door opened, roof opened, chest opened, village visited, building destroyed</td></tr>
  </tbody></table>
</div>

## What remains unknown

  Every byte is stored and restored as listed, but a few have no known gameplay meaning yet: the first 16 bytes of `BMST`, its bytes `0x50`, `0x51` and `0x94`–`0x9B`, three saved option bits that have no menu row, three unit counters, and two system-data bytes. <span class="confidence confidence--open">open</span>
