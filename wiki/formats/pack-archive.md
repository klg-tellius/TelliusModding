---
id: "pack-archive"
title: "Pack Archive"
description: "A small, purpose-built ZIP-alike with no compression of its own"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Container"]
aliases: ["tellius_archive.html#/pack-archive"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/pack-archive.md"
---
# Pack Archive

*A small, purpose-built ZIP-alike with no compression of its own*

Many `.cmp` files, once passed through [LZ10](./lz10.md), turn out to hold not raw data but a second, small archive format beginning with the literal bytes `pack`. It holds a table of name/offset/length entries followed by the actual file contents, each entry padded out to a 32-byte boundary — nothing more sophisticated than that; whatever compression already happened one layer up is the only compression involved.

  Three real bundling patterns use it: a chapter's [deployment data](./dispo-format.md) packs its four unit files (`dispos_c.bin`, `_n`, `_h`, `_m`) into one archive; a chapter's [map data](./map-format.md) packs `map.bin` alongside that same chapter's 3D scenery models, traveling together because the map references them by name; and a character or object's [skeleton/mesh/animation trio](./model-formats.md) (`skeleton.g`, `body.gs`, one `.ga` per battle animation) packs into a single `pack.cmp` per class.

  Each directory entry preserves the filename, content offset, and content length. Payload starts are padded to 32-byte boundaries; padding is not part of the recorded file length.

## How extraction works

After LZ10 is removed, verify the `pack` magic, read the directory, resolve every payload from its recorded offset and length, and ignore alignment bytes between entries. The filename describes the child resource but does not change its format.

## Worked example

For `dispos.cmp`, LZ10 produces one pack whose entries are the four unit files. Reading a unit group means opening one of them, such as `dispos_n.bin`, and then parsing that child as [labeled sections](./labeled-section.md); reading the outer archive alone reveals filenames, not units.

## Do not confuse layers

Pack performs grouping, LZ10 performs compression, and the child file supplies semantics. Rebuilding one layer requires updating that layer's lengths and alignments before applying the outer layer again.
