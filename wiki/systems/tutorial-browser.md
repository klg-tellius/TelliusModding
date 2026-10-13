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

  The exact mapping from the three grouping modes to the visible chapter/category/initial labels is still not fully closed. The initializer proves all three label sections are owned by this browser, but the renderer must be traced further before naming each mode with complete confidence.

## Input and ownership

  The tutorial-browser input handler dispatches differently depending on whether the group list or entry list has focus. In group-focus mode it updates the grouped-list cursor and shows the associated tutorial hint. In entry-focus mode it updates the entry cursor. This pins the grouped-list widget to the tutorial browser rather than to the inventory or shop systems.
