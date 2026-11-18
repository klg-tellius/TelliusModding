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

## European subtitles

Only the European disc (`GFEP01`) subtitles its movies. `MovieCaptionData.bin`, at the root of `files/`, is a [labeled-section](./labeled-section.md) file with no sections: a count of movies, then for each a pointer to its path (`movie/s01.thp`) and a pointer to its list of lines. A line is 16 bytes: a pointer to its message key (`MMC_SCENE01_01`, whose text is in each language's message files), the time it appears and the time it disappears, in milliseconds from the start of the movie, and a placement word (0 puts the text at the bottom, raised by its number of lines; the last line of `s08.thp` uses 1, a fixed height). A zero word ends each list. The player (`0x802070EC` in `GFEP01`'s `main.dol`) turns the times into frames of the current video mode, 50 or 60 Hz. The app reads and rebuilds the file (`formats/por_captions.py`); it has no editor for it yet. <span class="confidence confidence--confirmed">confirmed</span>

## Example: following the frame chain

To reach frame 2, read frame 0 using the header's first size, obtain frame 1's size from frame 0, then obtain frame 2's size from frame 1. Treating each frame's `next_total_size` as its own current size shifts boundaries and corrupts the stream.

!!! info "Frame sizes form a linked chain"
    The main header gives frame 0's size. Inside frame N, `next_total_size` describes frame N+1, while `prev_total_size` describes frame N−1. A reader must therefore carry the next size forward rather than treating it as the current frame's length.

  A THP stream can be constructed from a sequence of image frames plus optional PCM audio, provided component tables, frame-chain sizes, alignment, and per-frame audio boundaries are rebuilt consistently.

  See [Cutscenes](../systems/cutscenes.md) for how a script actually triggers a video — a literal path string, simpler than [music's](../systems/music-system.md) name→table lookup.
