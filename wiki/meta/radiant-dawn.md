---
id: "radiant-dawn"
title: "Radiant Dawn"
description: "What carries over from Path of Radiance to its Wii sequel, and what changes"
games: ["radiant-dawn"]
section: "meta"
article_type: "portal"
tags: ["Portal","Radiant Dawn"]
aliases: ["tellius_archive.html#/radiant-dawn"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "meta"
source_path: "meta/radiant-dawn.md"
---
# Radiant Dawn

*What carries over from Path of Radiance to its Wii sequel, and what changes*

*Fire Emblem: Radiant Dawn* (Wii, 2007) is built on the Path of Radiance engine. Most containers are the same, but nearly every record layout on top of them changed. This page lists what is established for the US disc; articles about Path of Radiance do not apply to it unless a page here says so.

## What is the same

- The [labeled-section container](../formats/labeled-section.md) (header, data, pointer list, named symbols) under every data file, and [LZ10](../formats/lz10.md) compression: on Radiant Dawn almost every data file is an LZ10 `.cms` (`FE10Data.cms`, `FE10Conversation.cms`, portraits, fonts, cards).
- The message *file* layout of [Message Format](../formats/message-format.md): a header, the texts, a sorted table of (text, ID) pairs, the IDs. Only the text inside each message changed (see [Message Format (Radiant Dawn)](../formats/rd-message-format.md)).
- The [font format](../formats/font-format.md). All Radiant Dawn fonts are LZ10-wrapped copies of the same GCF layout.
- The [event-script](../formats/event-script.md) container and virtual machine, with six more instructions (see [Event Scripts (Radiant Dawn)](../formats/rd-event-scripts.md)).
- The engine's global name table (message IDs and data symbols are looked up by name), with 2,027 buckets instead of 509 and the *last* matching entry winning instead of the first. <span class="confidence confidence--confirmed">engine</span>

## Languages

  Every disc carries the Japanese text in plain files (`Mess/c0101.m`). The game picks a variant by prefix at run time: `e_` English, `d_` German, `f_` French, `s_` Spanish, `i_` Italian. The US disc holds the Japanese and English files, the European disc all six. The US game loads `Mess/e_c0101.m` for chapter 1-1, so on a US or European disc the modding app opens a chapter's `e_` file as its dialogue and lists the Japanese one with the other files; on the Japanese disc it opens the plain one. English and Japanese text is Shift-JIS. <span class="confidence confidence--confirmed">engine + files</span>

  The European disc's language files (`e_`, `d_`, `f_`, `s_`, `i_`) are Shift-JIS too, with one change: the single bytes 0xA1&ndash;0xDF, half-width katakana in Shift-JIS, are Latin letters drawn in the European fonts. Lower-case accented letters sit 0x20 below their Latin-1 code (é is 0xC9, ü is 0xDC) and capitals 0x40 below (É is 0xA9, Ü is 0xBC). The others are ß 0xBF, œ 0xBD, Œ 0xA5, ¡ 0xC3, ¿ 0xDF, ª 0xC5, ° 0xDD, « 0xC6, » 0xDE, and the quotes ‘ ’ “ ” at 0xB0, 0xB5, 0xB7 and 0xB8. Two-byte Shift-JIS characters such as the ellipsis still appear. The US and Japanese discs use the half-width katakana in this range as such (the US credits' ｢ ｣, the Japanese ･ ellipsis). <span class="confidence confidence--confirmed">files</span>

## Fonts

  A table in the executable pairs each font number with a 4:3 and a 16:9 file: 0 system, 1 fe_font (the Tellius alphabet), 2 talk (dialogue), 3 bigkana, 4 alpha, each with a `_w` twin for widescreen consoles, and 5 ruby (furigana), one file for both. `Fonts/debug.cms` is on the disc but in no table. The widescreen fonts have the same glyphs drawn narrower, because the console stretches the 640-pixel-wide picture to 16:9. <span class="confidence confidence--confirmed">engine + files</span>

## Chapter titles and title cards

  A chapter's title is the message named by its `ChapterData` record (`MCT0102`, "I:1-Maiden of Miracles": part, chapter, name). Five more messages hold its parts: `MCT0102_0` "Part I", `_0_2` "I", `_1` "Ch.1", `_2` "Maiden of Miracles" and `_3` "Ch.1" again. The game reads each by name, and the Conditions screen draws `_0`, `_1` and `_2`; without them it draws garbage there. The modding app writes all five for an added chapter, from a title in the "I:1-Name" form or, for any other title, the template chapter's part and the title as the name. <span class="confidence confidence--confirmed">in game</span>

  The card shown when a chapter starts is a picture, `window/title/e_ch0102.cms` (`ch0102.cms` for Japanese): one 480&times;160 RGB5A3 image with two centred lines, "Ch 1" (or "Prologue", "Endgame") and the chapter's name, in green-grey serif lettering with a dark drop shadow. The lettering is pre-drawn art; no font on the disc contains it. <span class="confidence confidence--confirmed">files</span>

## Chapter order

  Each `ChapterData` record has a number byte at +0x84 (0-55 for the story, 80-83 for the four tutorials stored after `CFINAL`). Nearly everything that needs a chapter's record, including setting the current chapter, searches the table for that number. Moving to the next chapter is the exception: it reads records by position, starting one past the current number, skips each record whose +0x8D byte is set unless the bit for the current difficulty is set in it (1 Easy, 2 Normal, 4 Hard, 8 Maniac), and sets the first one it keeps. The attached `C0401a`/`C0401b` records have 128 there, which no difficulty matches: the step never enters them, a script sends the player there. Retail numbers equal positions, so this works on the unmodified disc. <span class="confidence confidence--confirmed">engine</span>

  A chapter played on several maps is several records, one per map, in a row (`C0407a` to `C0407e`, and `C0401a`/`C0401b` on `lmap01`/`lmap02`). No chapter changes battle map mid-chapter the way Path of Radiance's numbered parts do. A script ends a branching chapter with `CompleteSubChapter(route)`. <span class="confidence confidence--confirmed">files</span>

  Setting `gf_complete` wins the map at the end of the next unit action, not at once: a turn-start event that sets it ends the chapter when the first unit waits. Every `on_complete` event of the script then runs, in order, so a second win event can be added beside the chapter's own. <span class="confidence confidence--confirmed">in game</span>

  A map that wraps (`bmap0201`, Part 2's map over moving clouds) moves one step at each phase change: its mapdata names the step and the duration, and the terrain under a unit moves with it (a tile reads Cloud, then Sky). <span class="confidence confidence--confirmed">in game</span>

  A hub chapter is an added chapter (56-79) outside the story order. Its state is in four registered global flags (active, started) and two whole flag bytes (the destination and the pending story chapter), which a save keeps. The modding app's router runs as the last step of its chapter advance: from the hub it goes to the chosen destination or, with none, back to the story; when any other chapter ends with the hub active it goes back to the hub, keeping the next story chapter pending. <span class="confidence confidence--confirmed">in game</span>

## Part 4 armies

  Switching armies in Part 4 is done by the scripts, not the engine. Units belong to numbered forces: 0 is on the map, 5 is the army being played, and 8, 9 and 10 store Micaiah's, Ike's and Tibarn's armies. The deployment step only places characters that are in force 0 or 5, so a stored army stays off the map. <span class="confidence confidence--confirmed">engine</span>

  4-P splits the army with `DivideForce` and brings Micaiah's army (force 8) into force 5. Each later Part 4 chapter calls its own `startup.cmb` function `TEAM_<chapter>_ED` when it ends, which puts force 5 back into its store and brings out the next chapter's army: `TEAM_0402_ED` moves 5 to 9 and 10 to 5. The Endgame's `TEAM_0407a_OP` merges the three stores back into force 5. ChapterData +0x8F and the lord at +0xA4 name the army for the chapter: 18 and Micaiah, 19 and Ike, 20 and Tibarn. <span class="confidence confidence--confirmed">files</span>

  A chapter's player deployment group (`<map>_mikata` in `dispos_n/h.bin`) is a ranked list of sortie slots that names the retail army, leader first: 4-1's names Ike and eleven of his army. A unit the group doesn't name is given a free slot in roster order, and the chapter's forced sortie of its lord (`UnitForcedSallyByPID`) only marks a unit that already has a slot. When another army plays the chapter, its leader must take the old leader's slot, or a full party leaves them behind. <span class="confidence confidence--confirmed">in game</span>

  Where a file resumes is kept at BMST +0x9B, mirrored in the record header at +0x37: 2 in a base or the preparations, 9 after a chapter's end, 0x0B after a chapter's opening event. A file at 9 offers Start Chapter and plays the next chapter's opening; a file at 2 reopens its preparations, whatever its chapter byte says. <span class="confidence confidence--confirmed">in game</span>

## Chapter rules

  Five bytes of each `ChapterData` record set rules for the whole chapter. <span class="confidence confidence--confirmed">engine</span>

- +0x8B: a signed change to the movement of mounted and beast units (the game adds it to their Mov, capped 0 to 20). Retail sets -2 on 1-4, 1-7, 1-E, 3-8, 3-13 and 4-4.
- +0x8C: the preparations screen. 0 means none, unless the chapter's script sets the flag `イベント進撃`; 1 is the usual screen. The endgame's parts use 2 and 5.
- +0x8D: which difficulties the next-chapter step may enter the record on (see Chapter order); 0 means all.
- +0x8E: the chapter's part, one bit each: 1 part I, 2 part II, 4 part III, 8 part IV, 16 the endgame. A defeated character whose own part bits include the chapter's withdraws instead of dying. Bit 128 (4-P, 4-1 and their attached records) turns on an extra map-drawing setup whose look has not been checked in game.
- +0x8F: the army the player's units belong to, by its `GroupData` number (1 Dawn Brigade, 15 Greil Mercenaries, 18 to 20 the three part IV armies, 27 the endgame). The chapter's lord (the label at +0xA4) gets the army's leader mark.

  +0x88 is 2 on every story record and 0 on the test map and `CFINAL`; its meaning is not known.

## Supports

  `RelianceData` lists every supporting character against all of them, themselves included. Each 8-byte entry holds the partner, a flag byte, a speed byte and two zero bytes. <span class="confidence confidence--confirmed">engine</span>

  The speed (0 to 4) picks one of five extra amounts in `RelianceParam` that the game adds to every support-point gain of the pair: +2, +1, 0, -1 and -2 in the retail data, so 0 is the fastest and 4 the slowest. The gains themselves are also in `RelianceParam`: 15 at each map start (30 in part IV), 3 per phase next to the partner, 5 while carrying it, 4 per staff, 1 per Shove and 2 per Smite. Ranks C, B and A open at 50, 100 and 150 points. Retail pairs mostly use speed 2.

  The flag is 255 on 151 pairs and 0 on the others, always the same in both characters' lists. No game code reads it: a read watchpoint on the whole loaded table during play caught only the partner and speed bytes. <span class="confidence confidence--confirmed">in game</span>

## Battle backdrops

  `FE10Data.cms` gives each map a row of `BattleTerrIndex`: one backdrop number per terrain type, an index into the list `BattleTerrName` (`bg0101街`...). An empty cell (0xFFFF) uses the row's first cell. A map with no row of its own fights in front of `bg魔法` on every terrain type. Path of Radiance instead falls back to its first row. `BattleTerrName` has no count: the game reads entry *n* directly, so names can be appended. <span class="confidence confidence--confirmed">engine</span>

  The name is a record of `FE10Battle.cms`'s `FE10BMapData`, whose first `FE10BMapModel` names the scenery folder in `zbg/` (`bg0101街` is `zbg/bg0101twn`). Of its 119 backdrops, 13 are missing from the retail `BattleTerrName`, so no row can name them yet, among them the generic `bg汎用01草原1`-`3` (plains), `bg汎用02森林` (forest) and `bg魔法` itself. <span class="confidence confidence--confirmed">files</span>

## Music and sound

  `Sound/sound_data_en.cms` holds 36-byte cue records (name, BRSAR sound name, seven more words), each exported under its cue name. The game finds a cue through that export: `0x80076F54` looks the name up in the global name hash that every loaded container's symbols go into, so a new cue needs only its own record and symbol. The `SND_*` tables in the same file are separate: `SND_BGM_DATA` counts the retail music records, and `SND_MAP_BGM_DATA` gives each chapter 0x34 bytes of cue-name pointers (the chapter, map music, player phase, enemy phase, the other two armies, preparations, base, select). <span class="confidence confidence--confirmed">engine</span>

  `Sound/sound_us.brsar` finds a sound by name with the name tree in its `SYMB` section. At an inner node, bit *b* of the name (most significant first; past the end of the name it is 0) goes right when set, else left, and a leaf holds the name's string and its id. A stream sound is a 0x2C INFO entry with a 12-byte stream info (start, channel count, track flags) and a 12-byte 3D block; its file entry names the external `strm/*.brstm`. Sound effects are embedded waves (RWSD) or sequences, never streams. <span class="confidence confidence--confirmed">engine</span>

  A stream sound and a cue added this way played in Dolphin: 1-1's player and enemy phase entries named the new cue, and the dumped audio was the new 440 Hz stream, looping. <span class="confidence confidence--confirmed">in game</span>

  An embedded RWSD's DATA section (references relative to DATA + 8) lists its entries. An entry references its wave sound info (0x20: pitch, pan, sends, then envelope and randomizer references), its track table (8-byte track infos, each with a table of 0x10-byte note events: position, length, note) and its note table (0x30-byte note infos: wave, ADSR, key, volume, pan, pitch, then LFO, envelope and randomizer references). A wave sound's 16-byte info gives the RWSD entry, the track allocation and the priorities; the file's position table gives the groups that load it. A new sound effect made as its own one-entry RWSD in `GROUP_STATIC` played in Dolphin through the menu sound cues. <span class="confidence confidence--confirmed">in game</span>

## Battle sceneries

  Path of Radiance gives each backdrop a `zbg/<scenery>/param.dbx` (indoor flag, footstep effect and sound). Radiant Dawn has one 24-byte `FE10BMapModel` row per placed backdrop model in `FE10Battle.cms` (146 rows); an `FE10BMapData` background picks up to five rows, its variants. <span class="confidence confidence--confirmed">engine</span>

  | Offset | Field |
  | --- | --- |
  | +0x00 | The `zbg/` folder of the model |
  | +0x04 | The map's sound group (`SND_GROUP_C0101`) |
  | +0x08 | Flags: 0x02 indoors (the chapter's battle weather and sky are not applied), 0x08 mirrored (X scale −1), 0x10 the fighters may run in (the `突撃` motion; variants 0 and 2 only), 0x20 mirror and 0x40 turn 180° when they run in. 0x01 and 0x04 are set on retail rows but have no reader. |
  | +0x09 | Flight height on the aerial variants 2 and 3; 0 uses FE10BSetup `上空高度` |
  | +0x0A, +0x0B | Move and camera limits; 0 uses FE10BSetup `移動限界` (50) and `カメラ限界` (40) |
  | +0x0C | The `FE10BFootEffect` row (none, dust, dust at night, water spray, snow spray, rain spray, coins) |
  | +0x0D | The footstep ground: the column of the fighter's `FE10BSFXList` row (plain, sand, water, snow, rain, floor, coins, floor) |
  | +0x0E-0x13 | Signed x, y, z position |
  | +0x14 | Signed Y rotation in degrees |
  | +0x16 | Signed scale in 1/256; 0 means 3.0 |

  RFEE01 reads these in `0x800AA548` (setup), `0x800AB310` and `0x80185D0C` (weather), `0x800A95F4` (flight height), `0x800ABA28` (the run-in) and `0x800BA2C8` (footsteps). <span class="confidence confidence--confirmed">engine</span>

## Battle unit parameters

  Path of Radiance tunes each battle model in `zu/<code>_prm.dbx`. Radiant Dawn has one 340-byte `FE10BUnit` row per battle model description (240 rows): +0x00 the description (`剣士一般`), +0x04 the model code (`swoL`), +0x10 a flag mask, +0x18 twenty signed 16-bit values in 1/256, +0x14C the footstep sound set (an `FE10BSFXList` row) and +0x14D the number of `FE10BTex` rows it owns. <span class="confidence confidence--confirmed">engine</span>

  The game reads a value or a flag by name. `0x800A7370` (row, name) finds the name among the 20 `FE10BParam` rows (`補間比率`, `間合い`, `命中高度`... `２Ｄスケール`) and returns value *i* / 256, or 0 for an unknown name. `0x800A7460` finds the name among the 18 `FE10BFlags` rows (`大型`, `飛行系`, `左利き`... `サウンド判定`) and tests bit *i* of the mask. <span class="confidence confidence--confirmed">engine</span>

## Battle weapons

  Path of Radiance gives each weapon a `xwp/<NAME>.dbx` table in `zdbx.cmp`. Radiant Dawn has one `FE10BWeapon` row per weapon in `FE10Battle.cms` (192 rows, 36 bytes each). Its string fields are, in order: a Japanese name, the weapon key (`IRONSWORD`; an arrow names its bow), the model (`xwp/<model>/`), the hit and critical-hit effects (`EID_K_ATTK1`, `EID_K_CRIT1`), the weapon's own effect (`EID_K_FIRE`), the effect on the target (`EID_K_HEAD_FIRE`), and on a few rows a magic class name. Byte +0x20 indexes `FE10BWeaponType`: no, sw, sp, ax, kn, ja (thrown lance), ha (hand axe), kt (thrown knife), ms (magic sword), mg (magic), bw (bow), bg (bowgun), cr (claw), br (breath), rd (staff), ar (arrow). <span class="confidence confidence--confirmed">files</span>

## Tutorials

  The tutorial lists use Path of Radiance's `tut_data` layout, one file per difficulty set: `Tutorial/tut_data_n_en.bin` and `tut_data_h_en.bin`, plus the Japanese `tut_data_n.bin` and `tut_data_h.bin`. Each entry has the same four start-flag slots as Path of Radiance's; retail English entries are 0, 2, 2, 0 (only slots 2 and 3 unlocked). Which game each slot stands for has not been checked in game. <span class="confidence confidence--confirmed">files</span>

  The game reads them through a 2 × 6 table of names (`0x8036DA88`): the row is BMST +0x11 of the running game (0 the `_n` files, 1 the `_h` files) and the column the language. Four functions load from it (`0x801B00C0`, `0x801B01E4`, `0x801B0304`, `0x801B3ACC`). Setting every tutorial learned in any of the four slots did not stop 1-1's tutorial offers, which come from the chapter script (`TutorialRunTypeA`). <span class="confidence confidence--confirmed">in game</span>

## Weather

  ChapterData +0x9C names the chapter's weather: one of 22 names (`晴れ` clear, `曇り` cloudy, `雪` snow, `夜` night, `室内` indoors, `なし` none, and others). `0x801347B0` turns the name into its number (21, `なし`, for an unknown name) and `0x80134624` turns it back. The only caller is the battle scene setup (`0x801861A0`), which reads the battle background at +0x98 and the weather at +0x9C together. On 1-1, snow in place of cloudy drew no snow on the map or in battle, but the bandit's displayed hit rate on Micaiah went from 54 to 69. <span class="confidence confidence--confirmed">in game</span>

## Saves

  The game saves `FE10_US.dat` on the US disc, `FE10_EU.dat` on the European one and `FE10_JP.dat` on the Japanese one, in the title's data folder (`Wii/title/00010000/52464545/data`, `.../52464550/data`, `.../5246454a/data`). The three use one layout, and the fifth byte of every record's magic names the region: `FE10ASYS` and `FE10ADAT` on the US file, `FE10E…` on the European one, `FE10J…` on the Japanese one. The Japanese file is 0xAC000 bytes, not 0x124000: the US layout cut after the first checkpoint record, so the system record, six file records and one checkpoint record at 0x94000. <span class="confidence confidence--confirmed">engine + files</span>

  A European and a Japanese file made in Dolphin from a new game confirm this: each game writes file slot 1 into record 0, and the Japanese file menu lists six slots. Both files, with Micaiah's level changed by the app, loaded in their game and showed the new level in 1-1's unit list. The Japanese checkpoint record has not been seen written. <span class="confidence confidence--confirmed">in game</span>

  `FE10_US.dat` holds a system record, six files and six checkpoints. Each file is a record of its own: its header holds the file number, the difficulty and the chapter number the file menu shows, which `BMST` repeats. <span class="confidence confidence--confirmed">files</span>

  A save record is a stream of tagged sections: `ITBL`, `BMST`, `MDST`, `UNIP`, `SOKO`, `FGPT`, `T  T`, `RELD`, `KZND` and `DEBU`. `ITBL` holds eight name lists (characters, classes, items, skills, then the AI's attack, move and heal sequences and move types), each a count followed by the names without their `PID_`, `JID_`... prefix. The other sections name a record by its number in these lists, so the save carries its own copy of the names. Characters, classes and items count from 1, skills from 0. <span class="confidence confidence--confirmed">engine</span>

  `UNIP` has 254 unit slots, `SOKO` the convoy's 316 items. An item is its number and a state word; a forged item adds its name and eight more bytes. The 128 script flags are in `BMST`. <span class="confidence confidence--confirmed">engine</span>

  An item's state word holds its uses in the high byte and flags in the low byte: 0x80 marks the equipped weapon, 0x20 a forged item. Each of a unit's skills carries a source byte: 0 for the character's own skills, 1 for the class's, 2 for a skill taught with a scroll. <span class="confidence confidence--confirmed">files</span>

  A unit whose character has supports saves its one active partner (the partner's number in the save's character list, 0 for none) and one points byte per `RelianceData` partner. A saved pair points at each other, and the partner's points are the ones past a `RelianceParam` threshold: 51 or more is C, 101 B, 151 A. Points held exactly at 50, 100 or 150 wait for the base Support screen's rank-up, which adds one. Three bit sets, one per rank, record which support conversations the unit has seen. <span class="confidence confidence--confirmed">files</span>

  `T  T` is the map's tile records, as on Path of Radiance: 128 records of a tile, a type, a subtype and four values, then the number of live records. A file saved on 4-7e holds eight range-overlay records (type 6) in a ring around one tile. <span class="confidence confidence--confirmed">files</span>

  The system record, shared by every file, is the RAM block at `0x80427820` as `0x80245888` writes it, ending at +0x3B4. Seven of its bit sets are kept in big-endian 32-bit words, so the game's bit *n* is bit *n* mod 32 of word *n* ÷ 32. The conversation bits are a byte array instead, lowest bit first. <span class="confidence confidence--confirmed">engine + files</span>

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Content</th></tr></thead><tbody>
    <tr><td>+0x1C</td><td>Clears and unlocks, 64 bits: bits 0–3 the game cleared on Easy, Normal, Hard and Maniac (set with each clear record; any of them adds choices to the Options menu; with all four set, Extras also shows Game Records, Sound Room, Theater and Replay Event, checked in the European game), bit 5 the full opening movie (<code>SetAvailableGrandOpening</code>). Bit 4 is set on cleared files, but nothing found reads it. Bit 49 makes a chapter load a debug deployment, <code>zmap/debug/dispos_c.bin</code>; no retail code sets it.</td></tr>
    <tr><td>+0x24</td><td>Characters met, 128 bits, one per character number (PersonData +0x1C). A bit is set whenever that character's unit is created.</td></tr>
    <tr><td>+0x34</td><td>Conversations seen, 768 bits. At start-up the game registers flag names in order: those of <code>CONV_INFO_DATA</code> in <a href="../../formats/rd-conversation-data/">FE10Conversation.cms</a>, then three per FE8 yell record. <code>TstConversationFlag</code> reads a bit by name. The names themselves are not saved.</td></tr>
    <tr><td>+0x94</td><td>Sound Room tracks, 128 bits, set when a track first plays. One code path sets all 128 at once.</td></tr>
    <tr><td>+0xA4, +0xB4, +0xBC, +0xC4</td><td>The glossary's unlock bits: people (128), relations, affiliations and terms (64 each); see <a href="../../formats/rd-table-files/">dictionaryF.bin</a>.</td></tr>
    <tr><td>+0xCC</td><td>Eight u16, where the glossary was left: tab, people cursor, term cursor, two chart scroll pairs and the chart zoom, 0xFFFF when unset. The game stores its first scroll pair twice and never the second.</td></tr>
    <tr><td>+0xDC</td><td>30 clear records of 24 bytes, one per finished playthrough, the oldest dropped when all are used: a 64-bit game ID (the one the file headers carry), the difficulty (0 Normal, 1 Hard, 2 Maniac, 3 Easy; −1 an empty slot), the playthrough byte, a character number, the total turns and a 64-bit total of the chapter times</td></tr>
    <tr><td>+0x3AC</td><td>Language: the index of the <code>Mess/</code> prefix (<code>GetLanguage</code>); 1 on US files</td></tr>
    <tr><td>+0x3AD</td><td>The file the chapter checkpoint (<code>_intr</code>) saves to, 0xFF on a new record</td></tr>
    <tr><td>+0x3AE, +0x3B0</td><td>Two bytes and a word with no reader found</td></tr>
  </tbody></table>
</div>

  The Saves page's System data tab names these parts, numbers the bits as the game does and lists the clear records. <span class="confidence confidence--confirmed">engine + files</span>

## Map and battle textures

  A map animation ID (`FE10AnimHeader` in `FE10Anim.cms`) names one texture and one model folder: `AID_MIKAYA1` draws `ymu/mikaya1/mikaya1.tpl`. Map colours belong to the ID, not to an army: `AID_SOLDIER` (Begnion) is `soldier1_b`, `AID_SOLDIER_De` (Daein) is `soldier1_d`. A character's IDs are its `aid_1` to `aid_4`, one per tier. <span class="confidence confidence--confirmed">engine</span>

  The animation ID a unit uses is the character's `aid_<tier>`, else the class's: the tier is 1-3 by the class's tier skill, or for a laguz by its level (`0x800F416C`). <span class="confidence confidence--confirmed">engine</span>

  In battle, `0x800A7770` picks an `FE10BAnimData` row (20 bytes: AID, PID, JID, then two `FE10BUnit` descriptions). It takes the first row whose AID is the unit's; else the first whose PID and JID both match; else the first whose PID matches; else the first whose JID matches, which may be a character's own row. +0x0C names the battle unit; +0x10, set on pegasus, wyvern and bird rows, names the one used in the air. Each `FE10BUnit` owns a run of `FE10BTex` rows, one per army or per character, naming a loose `zu/<model>/<texture>.tpl`. `PID_ISAIYA` → `ISAIYA` gives one character her own look on a shared model. <span class="confidence confidence--confirmed">engine</span>

## Game database

`FE10Data.cms` holds the same kinds of tables as Path of Radiance's `FE8Data.bin`, but character, class and item records are variable in size: a count byte in each record says how many skill, sound-class, attribute or effectiveness labels follow. About 99 % of its bytes have a known meaning; the rest are mostly single bytes in the character, class, item and chapter records. Fields that work differently from Path of Radiance: <span class="confidence confidence--confirmed">engine</span>

- A class has a base weight and two weight parts, each a kind and a signed weight (armour, horse, pegasus, wyvern, beast, dragon, bird). A unit's weight is the class weight plus its personal weight; the parts are added on top for its mounted total.
- A class's promotion level (21 on first- and second-tier classes) makes the level-up that would reach it promote the unit instead. The class base Luck in the file is ignored: the game sets it to 0.
- A character lists the Parts in which it withdraws instead of dying when defeated (royals, herons and the laguz kings in every Part; others only in some).
- On Easy and Normal, Yune's blessing in the Endgame adds +5 to every stat but HP for the player's army; the bonus is a table per difficulty.
- A chapter gives enemy units extra levels per difficulty (+2 on the US disc's Hard, which the game calls Maniac), can change the movement of some class types (−2 on six desert and snow maps), names the army group the player's units join, and can be skipped on some difficulties.

Tables that Path of Radiance does not have:

- `RelianceParam`, the support point rules: a pair needs 50, 100 and 150 points for C, B and A and stops at 151. Points never pass the next level's value until that level is reached. Six kinds of support event give 15 (30 while a game flag is set), 3, 5, 4, 1 and 2 points. The pair's support speed in `RelianceData` adds +2, +1, 0, −1 or −2 to every gain. <span class="confidence confidence--confirmed">engine</span>
- `BioParam`, the five biorhythm bands: a threshold on the curve (0.8, 0.4, 0, −0.4, −0.8) and five signed bonuses (+10 +10 0 +10 +20 in the best band, mirrored in the worst). Tempest doubles them and Serenity halves them. <span class="confidence confidence--confirmed">engine</span>
- `NOBTL_TABLE`, 22 lists, each naming a character and the characters it cannot attack: for example the Goldoan dragons cannot attack the herons, Ena or Kurthnaga, and several Part 3 characters cannot attack friends fighting on the other side. Each pair has a flag (unused in the retail data) that still lets the two fight in combat. <span class="confidence confidence--confirmed">engine</span>

The Game Data page of the app edits all three tables.

On the Japanese disc an item record has no English article and no padding after it: its fixed part is 16 bytes, not 20. A skill record keeps its 0x2C bytes but has no article either: number, capacity, icon and the two list counts each sit one byte earlier, and three padding bytes end it. The Japanese database has 293 items, not 296. Its chapter records name the chapter's `N` message key at +0x18 (`N0101`), which the US and European discs leave null. <span class="confidence confidence--confirmed">files</span>

## Regional builds

The European (`RFEP01`) and Japanese (`RFEJ01`) executables hold the same code as the US one (`RFEE01`), placed at other addresses: matching the three files instruction by instruction, with branch targets and data addresses masked, pairs about 80 % of the US code with the other build's. These differences matter to modding: <span class="confidence confidence--confirmed">engine</span>

- The European build registers ten script functions the others lack: `VIEnableDimming`, `UnitDispLoad`, `UnitDispFree`, `UnitDispUpdate`, `TutFrameCreate`, `TutFrameDelete`, `GetMessageWidth`, `GetMessageHeight`, `FileSweepMRAM` and `FileSweepERAM`. The trial maps size their message frames with `GetMessageWidth`, because the text length depends on the language, and the Endgame turns the Wii's screen dimming off with `VIEnableDimming`.
- The Japanese build lacks four US functions: `IsJPVersion`, `IsNOAVersion`, `IsNOEVersion` and `IsShowVersion`.
- Wrath's HP check differs on the Japanese build: it needs HP under 20 % of maximum HP, where the US and European builds allow up to and including 30 %.
- The Japanese disc has only the plain sound files (`Sound/sound.brsar`, `sound_data.cms`) and tutorial lists, and no widescreen fonts or portraits (no `_w` fonts, no `Face/wide`). Its title cards have no prefix (`window/title/ch0102.cms`), and its staff roll file has no title or copyright lines.
- The European disc's scene movies (`s1.thp` and the like) carry five audio tracks per frame, one per language, one after another after the picture. Its staff roll lists 421 lines in each language, against 358 on the US disc.
- Three files have no use of their own. `FE8Data.bin` is a copy of Path of Radiance's data tables with every symbol renamed (`PersonData8`, `SI8_` skills): the file menu's inherit option reads it to carry a Path of Radiance clear save over. `client.bin` is a Game Boy Advance program, like the one Path of Radiance sends to a linked GBA, but nothing in Radiant Dawn names it. `zzzzzzzz.zzz` is 32 KB of zeros that nothing names.

## Articles

- [Message Format (Radiant Dawn)](../formats/rd-message-format.md): the byte-code that replaced the `$` commands, layouts and speech balloons.
- [Portraits (Radiant Dawn)](../formats/rd-portraits.md): the face table and how a portrait is assembled.
- [FE10Conversation.cms](../formats/rd-conversation-data.md): base Info conversations, the Conversation Room and support chat lines.
- [Glossary, endings and other table files](../formats/rd-table-files.md): the Info glossary and its unlock flags, the Conversation Room lists, the endings, the class introductions and the movie subtitles.
- [World-map route lines](../formats/rd-world-map-routes.md): the curves an army's route is drawn along, and the line styles.
- [Wii disc banner](../formats/wii-banner.md): the channel title and animated banner the Wii Menu shows.
- [Event Scripts (Radiant Dawn)](../formats/rd-event-scripts.md): the chapter scripts, their new instructions and triggers, and the flag table.
- [Script Functions (Radiant Dawn)](../systems/rd-script-functions.md): every native function a script can call.
