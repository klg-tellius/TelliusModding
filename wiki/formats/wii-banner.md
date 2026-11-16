---
id: "wii-banner"
title: "Wii disc banner (opening.bnr)"
description: "The channel title and animated banner the Wii Menu shows for the disc"
games: ["radiant-dawn"]
section: "formats"
article_type: "format-reference"
tags: ["Images","Radiant Dawn"]
aliases: []
status: "published"
last_reviewed: "2026-11-15"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/wii-banner.md"
---
# Wii disc banner (opening.bnr)

*The channel title and animated banner the Wii Menu shows for the disc*

`opening.bnr` is what the Wii Menu shows for the disc: the channel title, an animated banner, an icon and a short sound. The game itself never reads it. Radiant Dawn's follows the standard Wii layout. Path of Radiance has the GameCube's simpler `BNR1` banner instead. <span class="confidence confidence--confirmed">files</span>

## Layout

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Content</th></tr></thead><tbody>
    <tr><td>0x00</td><td>64 zero bytes</td></tr>
    <tr><td>0x40</td><td><code>IMET</code>, the header size (0x600), 3, the unpacked sizes of <code>icon.bin</code>, <code>banner.bin</code> and <code>sound.bin</code>, a zero word</td></tr>
    <tr><td>0x5C</td><td>Ten channel titles (Japanese, English, German, French, Spanish, Italian, Dutch, simplified Chinese, traditional Chinese, Korean), each two lines of 21 UTF-16 characters</td></tr>
    <tr><td>0x5F0</td><td>MD5 of bytes 0–0x5FF, taken with these 16 bytes zeroed</td></tr>
    <tr><td>0x600</td><td>A U8 archive: <code>meta/icon.bin</code>, <code>meta/banner.bin</code>, <code>meta/sound.bin</code></td></tr>
  </tbody></table>
</div>

  Each of the three parts starts with an `IMD5` header: the magic, the payload size, eight zero bytes and the payload's MD5. The icon and banner payloads are `LZ77` followed by an [LZ10](./lz10.md) stream of another U8 archive holding a layout (`arc/blyt/*.brlyt`), an animation (`arc/anim/*.brlan`) and the pictures (`arc/timg/*.tpl`, [TPL](./tpl-texture.md) textures). The sound is a `BNS` stream. <span class="confidence confidence--confirmed">files</span>

  U8 archives align each file's data to 32 bytes but do not pad the last file. Radiant Dawn's banner holds 13 pictures in the US and European versions and 9 in the Japanese one (the logo and the Dolby, Nintendo and Intelligent Systems marks); the US and European icons hold three 128 × 96 frames and the small `back` and `subtitle` pictures. <span class="confidence confidence--confirmed">files</span>

## Editing

  Changing a title only rewrites the header and its MD5. Replacing a picture rebuilds that part's archive, compresses it again, and updates its `IMD5` hash, the outer archive and the unpacked size in the header. The Wii Banner page on Assets does both and leaves every other byte as it was. <span class="confidence confidence--confirmed">files</span>
