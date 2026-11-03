---
id: "disc-layout"
title: "Disc & File Layout"
description: "What's actually inside the disc image, folder by folder"
games: ["path-of-radiance"]
section: "meta"
article_type: "portal"
tags: ["Portal","Structure"]
aliases: ["tellius_archive.html#/disc-layout"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "meta"
source_path: "meta/disc-layout.md"
---
# Disc & File Layout

*What's actually inside the disc image, folder by folder*

Pulling the game's own filesystem off the disc produces one flat `files/` tree — the same shape for both the GameCube original and the Wii sequel's disc, since both extract through the same tool. Nothing under it is compressed at the filesystem level; individual files inside it use their own container formats (most commonly [LZ10](../formats/lz10.md) compression wrapping a [pack archive](../formats/pack-archive.md)).

## How to navigate from path to mechanic

Use the top-level folder to identify the asset family, peel off any compression and archive layers, then follow the payload article to the system that consumes it. The filesystem organizes resources; it does not itself define chapter, combat, or media behavior.

## Example

`zmap/bmap01/map.cmp` means chapter-map family, LZ10 wrapper, pack archive, then `map.bin` plus models. `FE8Data.bin` sits directly under `files/` and needs no wrapper removal before its global tables are read.

<div class="table-wrap">
<table><thead><tr><th>Path</th><th>What's there</th></tr></thead><tbody>
    <tr><td><code>Mess/</code></td><td><a class="wl" href="../../formats/message-format/">Chapter dialogue</a> — one <code>cNN.m</code> file per chapter, plus a shared <code>common.m</code> for skill/menu help text</td></tr>
    <tr><td><code>Scripts/</code></td><td><a class="wl" href="../../formats/event-script/">Compiled event bytecode</a> — one <code>CNN.cmb</code> per chapter</td></tr>
    <tr><td><code>zmap/bmapNN/</code></td><td>Per-chapter <a class="wl" href="../../formats/map-format/">terrain and placement data</a> (<code>map.cmp</code>) and <a class="wl" href="../../formats/dispo-format/">unit deployment</a> (<code>dispos.cmp</code>)</td></tr>
    <tr><td><code>shop/</code></td><td><a class="wl" href="../../formats/shop-format/">Per-difficulty shop inventories</a> — armory, vendor, and forge stock for each chapter number</td></tr>
    <tr><td><code>ymu/&lt;class&gt;/</code></td><td>Per-class map model: <a class="wl" href="../../formats/model-formats/">skeleton, mesh, and animation clips</a> — one folder per playable/enemy class</td></tr>
    <tr><td><code>zbg/&lt;name&gt;/</code></td><td>Battle scenery model sets (static 3D backdrops used in combat scenes)</td></tr>
    <tr><td><code>s/</code></td><td>Flat background images (<a class="wl" href="../../formats/tpl-texture/">TPL</a>) shown behind dialogue and menu scenes</td></tr>
    <tr><td><code>Face/</code></td><td>Character portraits (<a class="wl" href="../../formats/tpl-texture/">TPL</a>, LZ10-compressed), several variants per character</td></tr>
    <tr><td><code>illust/</code>, <code>ending/</code></td><td>Full-screen CG illustration art and ending-sequence art</td></tr>
    <tr><td><code>window/</code>, <code>etc/</code>, <code>gmap/</code></td><td>UI chrome, miscellaneous graphics, and the world-map screen's own art — plus <code>window/</code>'s <code>RectBases.bin</code>/<code>RectDesc.bin</code>/<code>RectUnitList.bin</code> UI-layout tables (<a class="wl" href="../../formats/labeled-section/">Labeled Section Format</a>)</td></tr>
    <tr><td><code>zu/&lt;code&gt;/</code></td><td>Battle models: one uncompressed <a class="wl" href="../../formats/model-formats/">mesh, skeleton and animation</a> pack per weapon type, plus texture variants. The <code>zu/</code> tables inside <code>zdbx.cmp</code> name their animations and textures and hold their tuning</td></tr>
    <tr><td><code>Sound/</code></td><td><a class="wl" href="../../formats/stm-format/">Music tracks</a> (<code>.stm</code>), <a class="wl" href="../../formats/gcfesnd/"><code>gcfesnd.bin</code></a>, and <a class="wl" href="../../formats/musyx/">MusyX sample resources</a></td></tr>
    <tr><td><code>Movie/</code></td><td><a class="wl" href="../../formats/thp-format/">Cutscene video</a> (<code>.thp</code>)</td></tr>
    <tr><td><code>Fonts/</code></td><td><a class="wl" href="../../formats/font-format/">The five bitmap fonts</a> (<code>.gcf</code>, and the compressed <code>system.cms</code>)</td></tr>
    <tr><td><code>FE8Data.bin</code></td><td><a class="wl" href="../../formats/fe8data/">Characters, classes, items, and skills</a> — one uncompressed file, no container layer</td></tr>
    <tr><td><code>FE8Anim.bin</code></td><td><a class="wl" href="../../formats/fe8anim/">The map-model registry</a> tying each animation ID to its folder, weapon type, per-army textures and actions</td></tr>
    <tr><td><code>FE8Effect.bin</code></td><td><a class="wl" href="../../formats/fe8effect/">The visual-effect registry</a> for spell and skill particle effects</td></tr>
    <tr><td><code>title.cmp</code></td><td>The title screen's two textures, <code>window/title.tpl</code> and <code>s/qig</code>, in a <a class="wl" href="../../formats/pack-archive/">pack</a></td></tr>
    <tr><td><code>system.cmp</code></td><td>Loaded at boot: the common message text (skill and menu help) plus copies of <code>FE8Data.bin</code>, <code>FE8Anim.bin</code>, <code>FE8Effect.bin</code> and 13 other loose files. The game's file lookup searches loaded archives before the disc, so these copies are the ones it reads <span class="badge strong">engine</span></td></tr>
    <tr><td><a class="wl" href="../../formats/zdbx/"><code>zdbx.cmp</code></a></td><td>The battle engine's text tables: the class-to-model job list and hundreds of plain-text parameter files for class models, weapons, scenery, and camera scripts</td></tr>
    <tr><td><a class="wl" href="../../formats/sound-room/"><code>soundroom.bin</code></a></td><td>The Sound Room's picture list: which full-screen illustrations it cycles through behind the track menu, and where each sits on screen</td></tr>
    <tr><td><code>tut_data.bin</code> / <code>tut_data_en.bin</code></td><td>The <a class="wl" href="../../systems/tutorial-browser/">tutorial/glossary browser</a> and tutorial-popup system's per-chapter trigger and topic tables</td></tr>
    <tr><td><code>client.bin</code></td><td>A Game Boy Advance program, sent to a GBA plugged into a controller port by the title menu's "Connect GBA" to check which Fire Emblem cartridge it holds</td></tr>
  </tbody></table>
</div>

  Two whole-game tables sit alongside these per-folder assets: [`s/rect.bin`](../formats/rect-format.md), the table of full-screen image resources, and [`cp_data.bin`](../formats/cp-data-format.md), the computer player's data (AI scripts, movement weights, heal thresholds, thief steal list), unrelated to character supports.
