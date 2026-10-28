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

  Each `ChapterData` record has a number byte at +0x84 (0-55 for the story, 80-83 for the four tutorials stored after `CFINAL`). Nearly everything that needs a chapter's record, including setting the current chapter, searches the table for that number. Moving to the next chapter is the exception: it reads records by position, starting one past the current number, skips each record whose +0x8D byte is set unless the party's route matches it (the attached `C0401a`/`C0401b` records have 128 there), and sets the first one it keeps. Retail numbers equal positions, so this works on the unmodified disc. <span class="confidence confidence--confirmed">engine</span>

  A chapter played on several maps is several records, one per map, in a row (`C0407a` to `C0407e`, and `C0401a`/`C0401b` on `lmap01`/`lmap02`). No chapter changes battle map mid-chapter the way Path of Radiance's numbered parts do. A script ends a branching chapter with `CompleteSubChapter(route)`. <span class="confidence confidence--confirmed">files</span>

## Battle backdrops

  `FE10Data.cms` gives each map a row of `BattleTerrIndex`: one backdrop number per terrain type, an index into the list `BattleTerrName` (`bg0101街`...). An empty cell (0xFFFF) uses the row's first cell. A map with no row of its own fights in front of `bg魔法` on every terrain type. Path of Radiance instead falls back to its first row. `BattleTerrName` has no count: the game reads entry *n* directly, so names can be appended. <span class="confidence confidence--confirmed">engine</span>

  The name is a record of `FE10Battle.cms`'s `FE10BMapData`, whose first `FE10BMapModel` names the scenery folder in `zbg/` (`bg0101街` is `zbg/bg0101twn`). Of its 119 backdrops, 13 are missing from the retail `BattleTerrName`, so no row can name them yet, among them the generic `bg汎用01草原1`-`3` (plains), `bg汎用02森林` (forest) and `bg魔法` itself. <span class="confidence confidence--confirmed">files</span>

## Battle weapons

  Path of Radiance gives each weapon a `xwp/<NAME>.dbx` table in `zdbx.cmp`. Radiant Dawn has one `FE10BWeapon` row per weapon in `FE10Battle.cms` (192 rows, 36 bytes each). Its string fields are, in order: a Japanese name, the weapon key (`IRONSWORD`; an arrow names its bow), the model (`xwp/<model>/`), the hit and critical-hit effects (`EID_K_ATTK1`, `EID_K_CRIT1`), the weapon's own effect (`EID_K_FIRE`), the effect on the target (`EID_K_HEAD_FIRE`), and on a few rows a magic class name. Byte +0x20 indexes `FE10BWeaponType`: no, sw, sp, ax, kn, ja (thrown lance), ha (hand axe), kt (thrown knife), ms (magic sword), mg (magic), bw (bow), bg (bowgun), cr (claw), br (breath), rd (staff), ar (arrow). <span class="confidence confidence--confirmed">files</span>

## Tutorials

  The tutorial lists use Path of Radiance's `tut_data` layout, one file per difficulty set: `Tutorial/tut_data_n_en.bin` and `tut_data_h_en.bin`, plus the Japanese `tut_data_n.bin` and `tut_data_h.bin`. Each entry has the same four start-flag slots as Path of Radiance's. Which difficulty each slot stands for has not been checked. <span class="confidence confidence--confirmed">files</span>

## Saves

  A save record is a stream of tagged sections: `ITBL`, `BMST`, `MDST`, `UNIP`, `SOKO`, `FGPT`, `T  T`, `RELD`, `KZND` and `DEBU`. `ITBL` holds eight name lists (characters, classes, items, skills, then the AI's attack, move and heal sequences and move types), each a count followed by the names without their `PID_`, `JID_`... prefix. The other sections name a record by its number in these lists, so the save carries its own copy of the names. Characters, classes and items count from 1, skills from 0. <span class="confidence confidence--confirmed">engine</span>

  `UNIP` has 254 unit slots, `SOKO` the convoy's 316 items. An item is its number and a state word; a forged item adds its name and eight more bytes. The 128 script flags are in `BMST`. <span class="confidence confidence--confirmed">engine</span>

## Articles

- [Message Format (Radiant Dawn)](../formats/rd-message-format.md): the byte-code that replaced the `$` commands, layouts and speech balloons.
- [Portraits (Radiant Dawn)](../formats/rd-portraits.md): the face table and how a portrait is assembled.
- [FE10Conversation.cms](../formats/rd-conversation-data.md): base Info conversations, the Conversation Room and support chat lines.
- [Event Scripts (Radiant Dawn)](../formats/rd-event-scripts.md): the chapter scripts, their new instructions and triggers, and the flag table.
- [Script Functions (Radiant Dawn)](../systems/rd-script-functions.md): every native function a script can call.
