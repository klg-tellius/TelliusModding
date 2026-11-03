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

  Every disc carries the Japanese text in plain files (`Mess/c0101.m`). The game picks a variant by prefix at run time: `e_` English, `d_` German, `f_` French, `s_` Spanish, `i_` Italian. The US disc holds the Japanese and English files, the European disc all six. English and Japanese text is Shift-JIS; the other European languages use their own single-byte tables (ß is `0xBF` in German text), not yet mapped. <span class="confidence confidence--confirmed">engine + files</span>

## Fonts

  A table in the executable pairs each font number with a 4:3 and a 16:9 file: 0 system, 1 fe_font (the Tellius alphabet), 2 talk (dialogue), 3 bigkana, 4 alpha, each with a `_w` twin for widescreen consoles, and 5 ruby (furigana), one file for both. `Fonts/debug.cms` is on the disc but in no table. The widescreen fonts have the same glyphs drawn narrower, because the console stretches the 640-pixel-wide picture to 16:9. <span class="confidence confidence--confirmed">engine + files</span>

## Chapter titles and title cards

  A chapter's title is the message named by its `ChapterData` record (`MCT0102`, "I:1-Maiden of Miracles": part, chapter, name). The card shown when a chapter starts is a picture, `window/title/e_ch0102.cms` (`ch0102.cms` for Japanese): one 480&times;160 RGB5A3 image with two centred lines, "Ch 1" (or "Prologue", "Endgame") and the chapter's name, in green-grey serif lettering with a dark drop shadow. The lettering is pre-drawn art; no font on the disc contains it. <span class="confidence confidence--confirmed">files</span>

## Chapter order

  Each `ChapterData` record has a number byte at +0x84 (0-55 for the story, 80-83 for the four tutorials stored after `CFINAL`). Nearly everything that needs a chapter's record, including setting the current chapter, searches the table for that number. Moving to the next chapter is the exception: it reads records by position, starting one past the current number, skips each record whose +0x8D byte is set unless the bit for the current difficulty is set in it (1 Easy, 2 Normal, 4 Hard, 8 Maniac), and sets the first one it keeps. The attached `C0401a`/`C0401b` records have 128 there, which no difficulty matches: the step never enters them, a script sends the player there. Retail numbers equal positions, so this works on the unmodified disc. <span class="confidence confidence--confirmed">engine</span>

  A chapter played on several maps is several records, one per map, in a row (`C0407a` to `C0407e`, and `C0401a`/`C0401b` on `lmap01`/`lmap02`). No chapter changes battle map mid-chapter the way Path of Radiance's numbered parts do. A script ends a branching chapter with `CompleteSubChapter(route)`. <span class="confidence confidence--confirmed">files</span>

## Part 4 armies

  Switching armies in Part 4 is done by the scripts, not the engine. Units belong to numbered forces: 0 is on the map, 5 is the army being played, and 8, 9 and 10 store Micaiah's, Ike's and Tibarn's armies. The deployment step only places characters that are in force 0 or 5, so a stored army stays off the map. <span class="confidence confidence--confirmed">engine</span>

  4-P splits the army with `DivideForce` and brings Micaiah's army (force 8) into force 5. Each later Part 4 chapter calls its own `startup.cmb` function `TEAM_<chapter>_ED` when it ends, which puts force 5 back into its store and brings out the next chapter's army: `TEAM_0402_ED` moves 5 to 9 and 10 to 5. The Endgame's `TEAM_0407a_OP` merges the three stores back into force 5. ChapterData +0x8F and the lord at +0xA4 name the army for the chapter: 18 and Micaiah, 19 and Ike, 20 and Tibarn. <span class="confidence confidence--confirmed">files</span>

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

  The flag is 255 on 151 pairs and 0 on the others, always the same in both characters' lists. No game code reads it. <span class="confidence confidence--probable">engine</span>

## Battle backdrops

  `FE10Data.cms` gives each map a row of `BattleTerrIndex`: one backdrop number per terrain type, an index into the list `BattleTerrName` (`bg0101街`...). An empty cell (0xFFFF) uses the row's first cell. A map with no row of its own fights in front of `bg魔法` on every terrain type. Path of Radiance instead falls back to its first row. `BattleTerrName` has no count: the game reads entry *n* directly, so names can be appended. <span class="confidence confidence--confirmed">engine</span>

  The name is a record of `FE10Battle.cms`'s `FE10BMapData`, whose first `FE10BMapModel` names the scenery folder in `zbg/` (`bg0101街` is `zbg/bg0101twn`). Of its 119 backdrops, 13 are missing from the retail `BattleTerrName`, so no row can name them yet, among them the generic `bg汎用01草原1`-`3` (plains), `bg汎用02森林` (forest) and `bg魔法` itself. <span class="confidence confidence--confirmed">files</span>

## Battle weapons

  Path of Radiance gives each weapon a `xwp/<NAME>.dbx` table in `zdbx.cmp`. Radiant Dawn has one `FE10BWeapon` row per weapon in `FE10Battle.cms` (192 rows, 36 bytes each). Its string fields are, in order: a Japanese name, the weapon key (`IRONSWORD`; an arrow names its bow), the model (`xwp/<model>/`), the hit and critical-hit effects (`EID_K_ATTK1`, `EID_K_CRIT1`), the weapon's own effect (`EID_K_FIRE`), the effect on the target (`EID_K_HEAD_FIRE`), and on a few rows a magic class name. Byte +0x20 indexes `FE10BWeaponType`: no, sw, sp, ax, kn, ja (thrown lance), ha (hand axe), kt (thrown knife), ms (magic sword), mg (magic), bw (bow), bg (bowgun), cr (claw), br (breath), rd (staff), ar (arrow). <span class="confidence confidence--confirmed">files</span>

## Tutorials

  The tutorial lists use Path of Radiance's `tut_data` layout, one file per difficulty set: `Tutorial/tut_data_n_en.bin` and `tut_data_h_en.bin`, plus the Japanese `tut_data_n.bin` and `tut_data_h.bin`. Each entry has the same four start-flag slots as Path of Radiance's; retail English entries are 0, 2, 2, 0 (only slots 2 and 3 unlocked). Which game each slot stands for has not been checked in game. <span class="confidence confidence--confirmed">files</span>

## Saves

  `FE10_US.dat` holds a system record, six files and six checkpoints. Each file is a record of its own: its header holds the file number, the difficulty and the chapter number the file menu shows, which `BMST` repeats. <span class="confidence confidence--confirmed">files</span>

  A save record is a stream of tagged sections: `ITBL`, `BMST`, `MDST`, `UNIP`, `SOKO`, `FGPT`, `T  T`, `RELD`, `KZND` and `DEBU`. `ITBL` holds eight name lists (characters, classes, items, skills, then the AI's attack, move and heal sequences and move types), each a count followed by the names without their `PID_`, `JID_`... prefix. The other sections name a record by its number in these lists, so the save carries its own copy of the names. Characters, classes and items count from 1, skills from 0. <span class="confidence confidence--confirmed">engine</span>

  `UNIP` has 254 unit slots, `SOKO` the convoy's 316 items. An item is its number and a state word; a forged item adds its name and eight more bytes. The 128 script flags are in `BMST`. <span class="confidence confidence--confirmed">engine</span>

## Map and battle textures

  A map animation ID (`FE10AnimHeader` in `FE10Anim.cms`) names one texture and one model folder: `AID_MIKAYA1` draws `ymu/mikaya1/mikaya1.tpl`. Map colours belong to the ID, not to an army: `AID_SOLDIER` (Begnion) is `soldier1_b`, `AID_SOLDIER_De` (Daein) is `soldier1_d`. A character's IDs are its `aid_1` to `aid_4`, one per tier. <span class="confidence confidence--confirmed">engine</span>

  In battle, an `FE10BAnimData` row of `FE10Battle.cms` picks the battle unit by animation ID, then PID and class. Each `FE10BUnit` owns a run of `FE10BTex` rows, one per army or per character, naming a loose `zu/<model>/<texture>.tpl`. `PID_ISAIYA` → `ISAIYA` gives one character her own look on a shared model. <span class="confidence confidence--confirmed">engine</span>

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

## Articles

- [Message Format (Radiant Dawn)](../formats/rd-message-format.md): the byte-code that replaced the `$` commands, layouts and speech balloons.
- [Portraits (Radiant Dawn)](../formats/rd-portraits.md): the face table and how a portrait is assembled.
- [FE10Conversation.cms](../formats/rd-conversation-data.md): base Info conversations, the Conversation Room and support chat lines.
- [Event Scripts (Radiant Dawn)](../formats/rd-event-scripts.md): the chapter scripts, their new instructions and triggers, and the flag table.
- [Script Functions (Radiant Dawn)](../systems/rd-script-functions.md): every native function a script can call.
