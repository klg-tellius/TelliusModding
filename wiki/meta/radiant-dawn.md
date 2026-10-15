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

## Articles

- [Message Format (Radiant Dawn)](../formats/rd-message-format.md): the byte-code that replaced the `$` commands, layouts and speech balloons.
- [Portraits (Radiant Dawn)](../formats/rd-portraits.md): the face table and how a portrait is assembled.
- [FE10Conversation.cms](../formats/rd-conversation-data.md): base Info conversations, the Conversation Room and support chat lines.
- [Event Scripts (Radiant Dawn)](../formats/rd-event-scripts.md): the chapter scripts, their new instructions and triggers, and the flag table.
- [Script Functions (Radiant Dawn)](../systems/rd-script-functions.md): every native function a script can call.
