---
id: "face-data"
title: "Face Data"
description: "How each conversation portrait is assembled from its texture set, placed and layered"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Graphics","Text"]
aliases: ["tellius_archive.html#/face-data"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/face-data.md"
---
# Face Data

*How each conversation portrait is assembled from its texture set, placed and layered*

Every portrait the game can show has one record in the face table, keyed by its `FID_` ID (for example `FID_IKE` for the small portrait, `FID_L_IKE` for the large one). The record names the texture set, says where the eyes and mouth go on the base image, and how far back the character stands. <span class="confidence confidence--confirmed">confirmed</span>

## Record

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Field</th></tr></thead><tbody>
    <tr><td>0x00</td><td>Portrait ID (<code>FID_</code>)</td></tr>
    <tr><td>0x04</td><td>Display-name key (<code>MPID_</code>), shown on the nameplate</td></tr>
    <tr><td>0x08</td><td>Texture set file name (<code>.cms</code>)</td></tr>
    <tr><td>0x0C&amp;ndash;0x17</td><td>Top-left corner of the left eye, right eye and mouth on the base image (signed x, y pairs)</td></tr>
    <tr><td>0x18</td><td>Parts present: 1 eyes, 2 mouth</td></tr>
    <tr><td>0x1A</td><td>Texture number of the 64&amp;times;64 menu face, or <code>0xFFFF</code> for none</td></tr>
    <tr><td>0x1C</td><td>Mouth set picked automatically in some scenes</td></tr>
    <tr><td>0x1D</td><td>Depth: portraits with a higher value are drawn behind the others</td></tr>
    <tr><td>0x1E</td><td>Pixels the portrait is lowered when shown in a menu panel (signed)</td></tr>
  </tbody></table>
</div>

## Texture set

Texture 0 is the base picture. With both parts, textures 1&ndash;3 and 4&ndash;6 are the two mouth sets (3 and 6 are the closed mouths) and 7&ndash;9 and 10&ndash;12 the left and right eye frames. Without a mouth the eye numbers move down by six. Small portraits end with a 64&times;64 face used by menus, which is the texture field 0x1A points to; large portraits have none. When both eyes share the same position, only the right-eye overlay is drawn.

## Placement

A portrait is anchored by the middle of its bottom edge at its seat and is never resized. Facing the other way mirrors the whole picture. In conversations, the depth byte decides the layering: Titania (depth 54) appears in front of Greil (108) whatever their seat order. In menus such as the status screen and item lists, the large portrait sits at the bottom of a clipped panel, and tall characters are lowered by field 0x1E so their face stays visible: 3 px for Titania, 39 for Gort, 47 for Dheginsea.
