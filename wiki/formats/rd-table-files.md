---
id: "rd-table-files"
title: "Glossary, endings and other table files (Radiant Dawn)"
description: "dictionary.bin, dictionaryF.bin, conversationroom.bin, FE10Epilogue.bin, FE10Intro.bin and Movie/caption_data.bin"
games: ["radiant-dawn"]
section: "formats"
article_type: "format-reference"
tags: ["Text","Radiant Dawn"]
aliases: []
status: "published"
last_reviewed: "2026-11-15"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/rd-table-files.md"
---
# Glossary, endings and other table files (Radiant Dawn)

*dictionary.bin, dictionaryF.bin, conversationroom.bin, FE10Epilogue.bin, FE10Intro.bin and Movie/caption_data.bin*

Six small files in the root of Radiant Dawn's disc hold the Info glossary, the Conversation Room lists, the endings, the class introductions and the movie subtitles. All six use the [labeled-section container](./labeled-section.md) in the same way, which lets one writer rebuild them. The app edits each one on its own Assets page. <span class="confidence confidence--confirmed">engine + files</span>

## Shared layout

  The data area starts with the tables: each is a count followed by fixed-size records, packed back to back. After the last table comes the string pool: every distinct string once, sorted by its Shift-JIS bytes, each ending in a NUL, padded with zeros to four bytes. Every pointer field is in the relocation list, which is sorted by field offset. Apart from `caption_data.bin`, no pointer targets the tables themselves, so rebuilding a file means laying the tables out, sorting the strings again and rewriting the pointers. All six rebuild byte for byte on the US, European and Japanese discs. <span class="confidence confidence--confirmed">files</span>

## dictionary.bin: the glossary

  The loader reads five tables in a row, then a `0xFFFFFFFF` word. Its keys are messages in `Mess/e_dic.m` (`dic.m` on the Japanese disc). <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table><thead><tr><th>Table</th><th>Record</th><th>Fields</th></tr></thead><tbody>
    <tr><td>Categories</td><td>8 bytes</td><td>The tab label (<code>MDIK_PERSON</code>, <code>MDIK_WORD</code>), a zero word. The menu draws exactly two tabs.</td></tr>
    <tr><td>People</td><td>20 bytes</td><td>PID; nation key (<code>MDICN_</code>) or none; description key (<code>MDIC_</code>); s16 x and y on the relation chart (<code>-1000</code> keeps the person off it); a word that draws the chart portrait faded when non-zero, set on the characters who are dead by Radiant Dawn (Ashnard, Elena, Greil and others)</td></tr>
    <tr><td>Relations</td><td>24 bytes (20 in Japan)</td><td>The chart line image, drawn as <code>RID_&lt;name&gt;</code> from <code>window/RectRelationLine*</code>, and its s16 x, y; the label key (<code>MDIL_</code>); the label colour (1 and 2 pick two text colours, anything else a third); the point the label is centred on. The US and European records keep the Japanese label point before the translated one, and the game reads only the second.</td></tr>
    <tr><td>Affiliations</td><td>16 bytes</td><td>The frame image (<code>RID_&lt;name&gt;</code>; Daein's and Goldoa's frames use a <code>2</code> variant until a story flag is set) and its s16 x, y; the banner image and label key (<code>旗国名&lt;nation&gt;</code> for nations, <code>MDIB_</code> for groups such as the Greil Mercenaries) and the point it is centred on</td></tr>
    <tr><td>Terms</td><td>16 bytes</td><td>Name (<code>MDIN_</code>), reading (<code>MDIR_</code>) and description (<code>MDIC_</code>) keys, and a picture name on the nine nation terms (no reader of it was found)</td></tr>
  </tbody></table>
</div>

  Records with the same PID in a row form one entry: the list keeps the last unlocked one, which is how an entry can grow as the story moves on. <span class="confidence confidence--confirmed">engine</span>

## dictionaryF.bin: unlock flags

  Four tables of `(bit, flag name)` pairs. Entry *n* of a table unlocks record *n* of the matching glossary table: people, relations, affiliations and terms, in that order. Event scripts set an entry by its name; the name's prefix picks the bit array in the save's system record. <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table><thead><tr><th>Prefix</th><th>Table</th><th>Bits in the system record</th></tr></thead><tbody>
    <tr><td><code>DF_人物</code></td><td>People</td><td>+0x18B4 (160 bits)</td></tr>
    <tr><td><code>DF_関係</code></td><td>Relations</td><td>+0x18C8 (96 bits)</td></tr>
    <tr><td><code>DF_国</code>, <code>DF_所属</code></td><td>Affiliations</td><td>+0x18D4 (96 bits)</td></tr>
    <tr><td><code>DF_用語</code></td><td>Terms</td><td>+0x18E0 (80 bits)</td></tr>
  </tbody></table>
</div>

  An added entry needs a flag in the same position of its table, on a bit no other flag of that table uses, and a script that sets it. The Glossary page adds both together and checks the rest before saving. <span class="confidence confidence--confirmed">engine</span>

## conversationroom.bin: Conversation Room lists

  Two lists of name pointers, each after a count: 35 chapter IDs (`C0105` to `C0407e`) and 69 PIDs closed by `OTHER`. The Conversation Room loads them next to the conversation list of [FE10Conversation.cms](./rd-conversation-data.md), whose records name each conversation's chapter and speakers. They match the room's two orders, by chapter and by character; the menu code that walks them was not traced. <span class="confidence confidence--strong">engine + files</span>

## FE10Epilogue.bin: endings

  Data offsets 0 and 4 point at the build time and author. The symbol `EPILOGUE_DATA` is a count and 44-byte records, one per character in the order the epilogue shows them, with texts from `Mess/e_epilogue.m`: <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Field</th></tr></thead><tbody>
    <tr><td>+0x00</td><td>PID</td></tr>
    <tr><td>+0x04</td><td>Ending when the unit survived (<code>MEP_ALIVE_...</code>)</td></tr>
    <tr><td>+0x08</td><td>Line when the unit was lost but only wounded (<code>MEP_PARTY_COMMON</code>)</td></tr>
    <tr><td>+0x0C</td><td>Line when the unit was killed (<code>MEP_DEAD_COMMON</code>)</td></tr>
    <tr><td>+0x10, +0x14</td><td>A PID and the ending used instead when that unit is the active support partner at rank A</td></tr>
    <tr><td>+0x18, +0x1C</td><td>A PID and the ending used instead when that unit is alive (Micaiah's mentions King Pelleas)</td></tr>
    <tr><td>+0x20, +0x24</td><td>A PID and the ending used instead when that unit was killed</td></tr>
    <tr><td>+0x28</td><td>Non-zero lists the entry even when the unit is not in the army (zero on every retail record)</td></tr>
  </tbody></table>
</div>

  The three alternatives are tried in that order; the first that matches replaces the ending. <span class="confidence confidence--confirmed">engine</span>

## FE10Intro.bin: class introductions

  The symbol `FE10Intro` is a u16 count, two zero bytes and 64-byte records. Each record stages one class in battle beside its picture and description: <span class="confidence confidence--confirmed">engine + files</span>

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Field</th></tr></thead><tbody>
    <tr><td>+0x00</td><td>List group 0–6 (a byte, then three zero bytes); the scene starts at the first record of the chosen group</td></tr>
    <tr><td>+0x04</td><td>The battle unit shown (<code>剣士一般</code>, <code>光の賢者ミカヤ</code>...)</td></tr>
    <tr><td>+0x08</td><td>Class JID</td></tr>
    <tr><td>+0x0C, +0x10</td><td>Battle backdrop (<code>bg0104平地2</code>) and sky (<code>曇り</code>)</td></tr>
    <tr><td>+0x14</td><td>Camera distance: close, or close from above for fliers</td></tr>
    <tr><td>+0x18</td><td>Picture: <code>intro/&lt;name&gt;.cms</code>, an LZ10-compressed TPL</td></tr>
    <tr><td>+0x1C</td><td>Description (<code>MS_INTRO_...</code> in <code>intro.m</code>)</td></tr>
    <tr><td>+0x20, +0x24</td><td><code>兵種紹介</code> on every record; the weapon by its Japanese name (<code>なし</code> for none)</td></tr>
    <tr><td>+0x28</td><td>300 on every record, not traced</td></tr>
    <tr><td>+0x2C</td><td>Up to five motions played in turn (<code>攻撃１</code>, <code>構え</code>...), zero after the last</td></tr>
  </tbody></table>
</div>

## Movie/caption_data.bin: movie subtitles

  The US and European discs subtitle seven story movies with pictures instead of text. When a movie starts, the player looks its file name up in `CAPTION_DATA` (a count, then movie-name and caption-block pointer pairs), loads `/Movie/Caption/<language prefix><picture file>` (`e_s1.cms`, an LZ10 TPL with one image per caption) and steps through the captions. A caption block holds the folder, the picture file, then 20-byte captions ending in a `-1` word. <span class="confidence confidence--confirmed">engine</span>

  A caption is five numbers: the picture's index in the TPL, then the wait before it, its fade-in, how long it stays and its fade-out, all in milliseconds counted from the end of the previous caption. Each picture is drawn centred at the bottom of the screen. The opening's first line appears 9.04 seconds in. The Japanese disc has no subtitles. <span class="confidence confidence--confirmed">engine + files</span>
