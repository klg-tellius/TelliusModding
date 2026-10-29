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
