---
id: "rd-conversation-data"
title: "FE10Conversation.cms"
description: "Base Info conversations, the Conversation Room and support chat lines"
games: ["radiant-dawn"]
section: "formats"
article_type: "format-reference"
tags: ["Text","Radiant Dawn"]
aliases: ["tellius_archive.html#/rd-conversation-data"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/rd-conversation-data.md"
---
# FE10Conversation.cms

*Base Info conversations, the Conversation Room and support chat lines*

`FE10Conversation.cms` lists conversations that are not tied to one chapter script: the Info conversations of the base, the Path of Radiance supports replayed in the Extras menu, and the short support chats between units. The game loads it at boot. <span class="confidence confidence--confirmed">engine</span>

## Info conversations (CONV_INFO_DATA)

  A count, then 48-byte records: the chapter (`C0105`), the title key (`MID_0105_街の中で`, "In Town" in `common.m`), the message played from the chapter's message file, the flag that marks it seen, up to seven characters shown in the menu, and a number from 1 to 3 not yet identified. Each record also carries its own symbol, `CONV_INFO_DATA_C0105_街の中で`. The base menu builds that name from the chapter and the name of each base event the chapter script registered, and lists the record it finds; a record whose symbol no script names never appears in a base. The Extras Conversation Room lists every record and shows the ones whose flag is set. <span class="confidence confidence--confirmed">engine</span>

## Room supports (CONVERSATION_FE8_YELL_DATA)

  A count, then 44-byte records: the two characters' name keys, three conversation IDs (each followed by an empty word) and their three flags. The texts are in `Mess/e_yell_fe8.m`. <span class="confidence confidence--confirmed">engine + files</span>

## Support chat lines (CONVERSATION_MINI_YELL_DATA)

  A count of characters; for each, its ID, a partner count, the message file holding its lines (`Mess/yell_mini_1.m`, to which the game adds the language prefix) and, per partner, the partner's ID, the line it says and the line it answers. Every one of the 71 characters has an entry for all 71 partners. <span class="confidence confidence--confirmed">engine + files</span>
