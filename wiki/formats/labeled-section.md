---
id: "labeled-section"
title: "Labeled Section Format"
description: "The engine's own general-purpose container for named, string-labeled data"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Container"]
aliases: ["tellius_archive.html#/labeled-section"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/labeled-section.md"
---
# Labeled Section Format

*The engine's own general-purpose container for named, string-labeled data*

The game's own hand-rolled general-purpose container, reused for several kinds of data — chapter deployments, chapter maps, shop inventories — that otherwise share nothing in common. Once recognized, the shape is unmistakable everywhere it appears:

1. A 0x20-byte header: the file's exact size, the size of everything from `0x20` to the end of the *label pool*, the number of relocation entries, the number of sections, then an import count, an unused word and eight bytes the loader fills in memory (all zero on disc).
2. The format's own records, from `0x20`.
3. The label pool itself — plain, NUL-terminated ASCII strings: internal names for characters, classes, items, skills, AI behaviors, chapter identifiers. Almost every 4-byte value elsewhere in one of these files is a *pointer into this pool*, not a raw number.
4. A **relocation table** — an ascending list of every earlier position that points into the pool.
5. A **section table** — named regions of actual record data, one (address, name offset) pair per section, followed by the names.

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Size</th><th>Field</th><th>Meaning</th></tr></thead><tbody>
    <tr><td><code>0x00</code></td><td>4</td><td><code>filesize</code></td><td>Total file size</td></tr>
    <tr><td><code>0x04</code></td><td>4</td><td><code>data_size</code></td><td>Size from <code>0x20</code> to the end of the label pool</td></tr>
    <tr><td><code>0x08</code></td><td>4</td><td><code>relocation_count</code></td><td>Entries in the relocation table</td></tr>
    <tr><td><code>0x0C</code></td><td>4</td><td><code>section_count</code></td><td>Entries in the section table</td></tr>
    <tr><td><code>0x10</code></td><td>4</td><td><code>import_count</code></td><td>Entries of an extra 8-byte table before the names; 0 in every file</td></tr>
    <tr><td><code>0x14</code></td><td>4</td><td>&amp;mdash;</td><td>Zero, never read</td></tr>
    <tr><td><code>0x18</code></td><td>8</td><td>&amp;mdash;</td><td>Zero on disc. In memory the loader writes <code>HSDArc</code> at <code>0x18</code> once the pointers are relocated, and sets <code>0x1F</code> once the sections are registered by name</td></tr>
  </tbody></table>
</div>

!!! info "The relocation table, solved"
    The table is an ascending list of every 4-byte-aligned field position whose stored value resolves to a valid label. This rule reproduces each stored relocation entry exactly. When the file loads, the game adds the file's data address to every listed field, turning offsets into pointers; a field left off the list stays a raw offset. <span class="confidence confidence--confirmed">engine</span>

  The layout is HAL Laboratory's sysdolphin archive, the format behind Super Smash Bros. Melee's `.dat` files: the loader checks and stamps the signature `HSDArc`. [FE8Data.bin](./fe8data.md) and the message files use the same container. <span class="confidence confidence--confirmed">engine</span>

  Compare against [FE8Anim.bin and FE8Effect.bin](./fe8anim.md), which share the label-pool idea but start their data section with a record count.

## Mental model: records point to names

Most record fields do not embed `PID_IKE` or `IID_IRONSWORD`. They store an address into one shared string pool. The relocation table catalogs the locations of those address-bearing fields, while the section table says where groups of records begin.

## Worked edit

Replacing one pointer with another existing same-file label can preserve file size. Adding a new label grows the pool and moves the relocation and section tables; their addresses and any affected pointers must be rebuilt together. Copying a record to a new position likewise changes the set of pointer locations that belongs in the relocation table.

## Known limits

The container layout and relocation rule are confirmed. Individual section payloads still require their own format article; a valid labeled-section parse does not prove that every byte inside each record is understood.
