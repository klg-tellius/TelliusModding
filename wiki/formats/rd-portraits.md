---
id: "rd-portraits"
title: "Portraits (Radiant Dawn)"
description: "The face table and the fifteen images of a portrait"
games: ["radiant-dawn"]
section: "formats"
article_type: "format-reference"
tags: ["Graphics","Radiant Dawn"]
aliases: ["tellius_archive.html#/rd-portraits"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/rd-portraits.md"
---
# Portraits (Radiant Dawn)

*The face table and the fifteen images of a portrait*

Every portrait has one record in `Face/facedata.bin` and one image file. Unlike Path of Radiance ([Face Data](./face-data.md)), one record serves both portrait sizes: the small one shown in speech balloons and the large one of background scenes. <span class="confidence confidence--confirmed">files</span>

## Record

<div class="table-wrap">
<table class="tight"><thead><tr><th>Offset</th><th>Field</th></tr></thead><tbody>
    <tr><td>0x00</td><td>Small portrait ID (<code>FID_IKE</code>)</td></tr>
    <tr><td>0x04</td><td>Large portrait ID (<code>FID_L_IKE</code>)</td></tr>
    <tr><td>0x08</td><td>Name key (<code>MPID_IKE</code>)</td></tr>
    <tr><td>0x0C</td><td>Image file name (<code>IKE.cms</code>)</td></tr>
    <tr><td>0x10&amp;ndash;0x1B</td><td>Top-left corner of eye A, eye B and the mouth on the large picture (&amp;minus;1 for faces without moving parts)</td></tr>
    <tr><td>0x1C</td><td>Where the small picture is cut from the large one</td></tr>
    <tr><td>0x20&amp;ndash;0x2F</td><td>Eight more values, not identified <span class="badge open">open</span></td></tr>
  </tbody></table>
</div>

## The images

  The file decompresses to a TPL of 15 images: 0 the small portrait (192&times;128), 1 the large portrait (336&times;336), 2&ndash;7 six mouth frames, 8&ndash;10 and 11&ndash;13 three frames of each eye, 14 a 64&times;64 face for menus. The two pictures have transparent holes where the eyes and mouth go; the frames are drawn behind them at the record's points. The small picture is exactly the large one cropped at the record's cut point: for Ike, 192&times;128 pixels from (83, 78). <span class="confidence confidence--confirmed">files</span>

## Facing

  The art faces left. A layout seat marked as mirrored flips it, and a show command can force left or right. The 16:9 files in `Face/wide/` hold the same portraits drawn narrower, for the stretched widescreen picture.
