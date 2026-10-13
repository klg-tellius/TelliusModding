---
id: "iso-fst"
title: "GameCube Disc & FST"
description: "How the disc identifies the game, boots main.dol, and maps paths to file data"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Container","Structure"]
aliases: ["tellius_archive.html#/iso-fst"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/iso-fst.md"
---
# GameCube Disc & FST

*How the disc identifies the game, boots main.dol, and maps paths to file data*

The disc image has two conceptual regions. The **system area** contains the boot metadata, apploader, executable, and filesystem index. The **game filesystem** contains the paths documented in [Disc & File Layout](../meta/disc-layout.md). Extractors commonly present these as `sys/` and `files/`, but those folders are an extraction convention: the original disc stores offsets and lengths rather than a desktop-style directory tree.

## How the game boots

1. `boot.bin` identifies the title and points to the executable and FST.
2. `bi2.bin` supplies additional boot configuration.
3. The apploader prepares memory and loads the executable sections.
4. [`main.dol`](./main-dol.md) starts the game and requests assets by path or through engine registries.

## File System Table

  The FST is the disc's directory. Directory entries describe hierarchy; file entries pair a name with the byte offset and length of its payload. Thus a path such as `zmap/bmap01/map.cmp` ultimately becomes an FST entry whose offset tells the drive where to read. The FST stores the names once; native code can receive an already-resolved map name and combine it with a fixed prefix such as `zmap/%s`.

## ISO, CISO, and extracted files

  `.iso` is a full disc image. `.ciso` is a compact representation of the same logical GameCube disc content. Neither changes the internal game formats: LZ10, pack archives, TPL textures, scripts, and messages remain byte-for-byte game resources after extraction.
