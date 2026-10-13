---
id: "format-coverage"
title: "File Format Index"
description: "Every identified file family on the disc and how completely it is understood"
games: ["path-of-radiance"]
section: "meta"
article_type: "portal"
tags: ["Portal","File Formats"]
aliases: ["tellius_archive.html#/format-coverage"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "meta"
source_path: "meta/format-coverage.md"
---
# File Format Index

*Every identified file family on the disc and how completely it is understood*

This index separates container layers from their payloads. For example, `dispos.cmp` is not one opaque format: it is LZ10 wrapping a pack archive whose entries use the labeled-section layout and 0x6C-byte deployment records.

## How to use the index

Start with a path or extension, read its layers from outside inward, and open the linked article for each layer. “Complete” applies only to the named layer; a complete compression decoder does not imply that the decompressed payload's fields are understood.

## Example

For `Face/IKE.cms`, first remove LZ10, then parse the resulting TPL, then apply the portrait system's shared-palette rules. For `zmap/bmap01/dispos.cmp`, remove LZ10, open the pack, choose a difficulty child, then parse labeled sections and deployment records.

<div class="table-wrap">
<table><thead><tr><th>File family</th><th>Location/example</th><th>Layers or purpose</th><th>Status</th></tr></thead><tbody>
    <tr><td><a class="wl" href="../../formats/iso-fst/">Disc/FST</a></td><td>Disc system area</td><td>Boot metadata, DOL, filesystem index</td><td><span class="badge confirmed">complete overview</span></td></tr>
    <tr><td><a class="wl" href="../../formats/main-dol/">main.dol</a></td><td><code>sys/main.dol</code></td><td>PowerPC executable</td><td><span class="badge strong">behavior mapped, not exhaustive</span></td></tr>
    <tr><td><a class="wl" href="../../formats/lz10/">LZ10</a></td><td><code>.cmp</code>, <code>.cms</code></td><td>Compression wrapper</td><td><span class="badge confirmed">complete</span></td></tr>
    <tr><td><a class="wl" href="../../formats/pack-archive/">Pack Archive</a></td><td>Inside many <code>.cmp</code> files</td><td>Named-file archive</td><td><span class="badge confirmed">complete</span></td></tr>
    <tr><td><a class="wl" href="../../formats/labeled-section/">Labeled Section Format</a></td><td>Maps, deployment, shops, UI</td><td>Labels, relocations, named sections</td><td><span class="badge confirmed">container complete</span></td></tr>
    <tr><td><a class="wl" href="../../formats/fe8data/">FE8Data.bin</a></td><td><code>FE8Data.bin</code></td><td>Characters, classes, items, skills, chapters, terrain, battle scenes, supports</td><td><span class="badge confirmed">every byte accounted for</span></td></tr>
    <tr><td><a class="wl" href="../../formats/dispo-format/">Dispo Format</a></td><td><code>zmap/*/dispos.cmp</code></td><td>Unit deployment, shared and per difficulty</td><td><span class="badge confirmed"></span></td></tr>
    <tr><td><a class="wl" href="../../formats/map-format/">Map File Format</a></td><td><code>zmap/*/map.cmp</code></td><td>Terrain, panels, objects, lighting</td><td><span class="badge strong">partial fields</span></td></tr>
    <tr><td><a class="wl" href="../../formats/event-script/">Event Script</a></td><td><code>Scripts/*.cmb</code></td><td>Compiled chapter bytecode</td><td><span class="badge confirmed">layout and instructions complete</span></td></tr>
    <tr><td><a class="wl" href="../../formats/message-format/">Message Format</a></td><td><code>Mess/*.m</code></td><td>Text and inline presentation codes</td><td><span class="badge confirmed">complete</span></td></tr>
    <tr><td><a class="wl" href="../../formats/tpl-texture/">TPL Texture</a></td><td><code>.tpl</code>, compressed <code>.cms</code></td><td>GX textures and palettes</td><td><span class="badge confirmed">used formats complete</span></td></tr>
    <tr><td><a class="wl" href="../../formats/model-formats/">.g / .gs / .ga</a></td><td><code>.g/.gs/.ga</code></td><td>Skeleton, mesh, animation</td><td><span class="badge strong">partial unknown fields</span></td></tr>
    <tr><td><a class="wl" href="../../formats/stm-format/">STM &amp; DSP-ADPCM</a></td><td><code>Sound/*.stm</code></td><td>Streamed DSP-ADPCM music</td><td><span class="badge confirmed">complete</span></td></tr>
    <tr><td><a class="wl" href="../../formats/thp-format/">THP</a></td><td><code>Movie/*.thp</code></td><td>JPEG-like video and DSP audio</td><td><span class="badge confirmed">complete overview</span></td></tr>
    <tr><td><a class="wl" href="../../formats/gcfesnd/">gcfesnd.bin</a></td><td><code>Sound/gcfesnd.bin</code></td><td>Sound cue catalog</td><td><span class="badge strong">runtime mapping partial</span></td></tr>
    <tr><td><a class="wl" href="../../formats/musyx/">MusyX Audio Resources</a></td><td><code>.sdir/.samp</code></td><td>Sample directory and bank</td><td><span class="badge strong">identified</span></td></tr>
    <tr><td><a class="wl" href="../../formats/zdbx/">ZDBX &amp; DBX</a></td><td><code>zdbx.cmp</code>, loose <code>.dbx</code></td><td>Text design tables and parameters</td><td><span class="badge strong">cataloged, fields partial</span></td></tr>
    <tr><td><a class="wl" href="../../formats/font-format/">Font</a></td><td><code>Fonts/*.gcf</code>, <code>Fonts/system.cms</code></td><td>Bitmap fonts: glyph table and I4 sheets</td><td><span class="badge confirmed">layout complete; per-screen font use open</span></td></tr>
    <tr><td><a class="wl" href="../../formats/save-format/">GameCube Save (.gci)</a></td><td>Memory-card <code>.gci</code></td><td>CRC-checked save blocks and tagged state chunks</td><td><span class="badge confirmed">every chunk decoded</span></td></tr>
    <tr><td><a class="wl" href="../../formats/sound-room/">soundroom.bin</a></td><td>Filesystem root</td><td>Sound Room slideshow: picture names and screen offsets</td><td><span class="badge confirmed">complete</span></td></tr>
    <tr><td><code>tut_data*.bin</code></td><td>Filesystem root</td><td>Tutorial trigger/topic tables</td><td><span class="badge plausible">identified, partial</span></td></tr>
    <tr><td><code>client.bin</code></td><td>Filesystem root</td><td>Region/save-related metadata</td><td><span class="badge open">unidentified payload</span></td></tr>
  </tbody></table>
</div>
