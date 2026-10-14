---
id: "tutorial-browser"
title: "Tutorial Browser"
description: "The grouped glossary/tutorial list backed by TUT_CHAPTER, TUT_CATEGORY, TUT_INITIAL, and TUT_DATA"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure","UI"]
aliases: ["tellius_archive.html#/tutorial-browser"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/tutorial-browser.md"
---
# Tutorial Browser

*The grouped glossary/tutorial list backed by TUT_CHAPTER, TUT_CATEGORY, TUT_INITIAL, and TUT_DATA*

The tutorial browser is a grouped list interface for tutorial/glossary topics. It is initialized from four named sections: `TUT_CHAPTER`, `TUT_CATEGORY`, `TUT_INITIAL`, and `TUT_DATA`. The first three are label sections used by the browser; `TUT_DATA` begins with a count and then a table of 24-byte topic records.

## Runtime browser state

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Role</th></tr></thead><tbody>
    <tr><td><code>+0x30</code></td><td>Grouping mode, values 0/1/2</td></tr>
    <tr><td><code>+0x31</code></td><td>Focus: 0 for group list, 1 for entry list</td></tr>
    <tr><td><code>+0x32</code></td><td>Current group index</td></tr>
    <tr><td><code>+0x33</code></td><td>Current entry index</td></tr>
    <tr><td><code>+0x36/+0x38/+0x3A</code></td><td>Current scroll position, target, and step</td></tr>
    <tr><td><code>+0x44/+0x48/+0x4C</code></td><td>Pointers to chapter/category/initial label sections</td></tr>
    <tr><td><code>+0x50</code></td><td>Topic/list count</td></tr>
    <tr><td><code>+0x54/+0x58</code></td><td>List sentinel links; nodes use <code>+4</code> for next and <code>+8</code> for topic entry</td></tr>
    <tr><td><code>+0x5C/+0x60</code></td><td>Scrollbar and caption object pointers</td></tr>
  </tbody></table>
</div>

## Grouping behavior

  The three grouping modes compare different bytes in each 24-byte tutorial record: mode 0 uses record byte `+2`, mode 1 uses `+1`, and mode 2 uses `+4`. The group counter counts runs of consecutive equal keys in the current sorted/listed order, not global distinct values across the whole table. Rebuild routines insert group-header records into the visible list.

  The keys line up with the label sections exactly: mode 0 groups by **chapter** (`+2` indexes `TUT_CHAPTER`, so the Prologue's tutorials carry key 1, `MT_C00`), mode 1 by **category** (`+1` indexes `TUT_CATEGORY`) and mode 2 by **initial** (`+4` indexes `TUT_INITIAL`: letters in the English file, nine kana rows in the Japanese one). <span class="confidence confidence--strong">strong</span> The group builders count keys from 1, so entries whose key is 0 (the three opening tutorials have chapter and category 0) never form a group of their own. <span class="confidence confidence--confirmed">confirmed</span>

## The tutorial record

  `TUT_DATA` is a count followed by 24-byte records <span class="confidence confidence--confirmed">confirmed</span>:

<table><thead><tr><th>Offset</th><th>Meaning</th></tr></thead><tbody>
<tr><td><code>+0x00</code></td><td>Tutorial id: its bit in the party's 128-bit "unlocked" and "learned" masks</td></tr>
<tr><td><code>+0x01</code></td><td>Category key</td></tr>
<tr><td><code>+0x02</code></td><td>Chapter key</td></tr>
<tr><td><code>+0x03</code></td><td>Display order: the list is sorted on this signed byte before groups are inserted</td></tr>
<tr><td><code>+0x04</code></td><td>Initial key</td></tr>
<tr><td><code>+0x05..+0x08</code></td><td>Start flags, one byte per difficulty (Normal, Hard, Maniac, Easy): when a new game starts, bit 1 marks the tutorial unlocked and bit 0 marks it learned</td></tr>
<tr><td><code>+0x09..+0x0B</code></td><td>Zero</td></tr>
<tr><td><code>+0x0C</code></td><td>Pointer to the title message key (<code>MT_C01_s移動</code>)</td></tr>
<tr><td><code>+0x10</code></td><td>Pointer to the event script file that plays it (<code>Scripts/C80.cmb</code>)</td></tr>
<tr><td><code>+0x14</code></td><td>Pointer to the script function (<code>tut_01_Idou</code>)</td></tr>
</tbody></table>

  On Hard and Maniac every tutorial starts unlocked and learned, so no tutorial interrupts play; on Normal and Easy only the three opening ones start unlocked and the rest are unlocked by the chapters' scripts as they come up. `TutDataHead` holds a zero word, the file's build time and its author's name. The US game reads `tut_data_en.bin`; `tut_data.bin` is the Japanese list.

## Input and ownership

  The tutorial-browser input handler dispatches differently depending on whether the group list or entry list has focus. In group-focus mode it updates the grouped-list cursor and shows the associated tutorial hint. In entry-focus mode it updates the entry cursor. This pins the grouped-list widget to the tutorial browser rather than to the inventory or shop systems.
