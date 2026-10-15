---
id: "thp-format"
title: "THP"
description: "Nintendo's cutscene video codec — near-standard JPEG frames plus DSP-ADPCM audio"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Video","Editable"]
aliases: ["tellius_archive.html#/thp-format"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/thp-format.md"
---
# THP

*Nintendo's cutscene video codec — near-standard JPEG frames plus DSP-ADPCM audio*

Cutscenes use Nintendo's THP format: frames are near-standard JPEGs, while audio reuses the same [DSP-ADPCM codec](./stm-format.md) as music but packages samples per video frame. THP's JPEG payload omits the usual escape byte after literal `0xFF` values in entropy-coded data. Encoded frames are padded to 32-byte boundaries, and per-frame audio sample counts are multiples of 14 except for the last frame.

## How a movie advances

The header describes components and the first frame. Each frame supplies video plus its matching audio slice and points indirectly to the next frame's total size. The player decodes the image, queues the associated samples, carries the next size forward, and repeats at the declared frame rate.

## Example: following the frame chain

To reach frame 2, read frame 0 using the header's first size, obtain frame 1's size from frame 0, then obtain frame 2's size from frame 1. Treating each frame's `next_total_size` as its own current size shifts boundaries and corrupts the stream.

!!! info "Frame sizes form a linked chain"
    The main header gives frame 0's size. Inside frame N, `next_total_size` describes frame N+1, while `prev_total_size` describes frame N−1. A reader must therefore carry the next size forward rather than treating it as the current frame's length.

  A THP stream can be constructed from a sequence of image frames plus optional PCM audio, provided component tables, frame-chain sizes, alignment, and per-frame audio boundaries are rebuilt consistently.

  See [Cutscenes](../systems/cutscenes.md) for how a script actually triggers a video — a literal path string, simpler than [music's](../systems/music-system.md) name→table lookup.
