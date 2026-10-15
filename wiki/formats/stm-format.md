---
id: "stm-format"
title: "STM & DSP-ADPCM"
description: "Nintendo's real GameCube audio codec, wrapped in an engine-specific container"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Audio","Editable"]
aliases: ["tellius_archive.html#/stm-format"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/stm-format.md"
---
# STM & DSP-ADPCM

*Nintendo's real GameCube audio codec, wrapped in an engine-specific container*

Background music tracks use Nintendo's DSP-ADPCM codec, a standard GameCube/Wii predictor-based format. Audio is divided into 14-sample frames. Each frame selects one of the channel's stored predictor coefficient pairs and a scale, then reconstructs samples from 4-bit residual values and the two preceding decoded samples.

## How playback is reconstructed

The STM header identifies stream properties and channel regions. For each channel, the decoder restores every 14-sample frame from its predictor, scale, residual nibbles, and two-sample history, then interleaves channels for playback. Loop state restores the predictor history at the loop boundary.

## Example: looping stereo

A stereo track carries two DSP headers and two back-to-back encoded streams. At the loop point, playback must resume each channel with its own recorded history; jumping only to the byte offset without restoring that state causes an audible discontinuity.

  The `.stm` wrapper is engine-specific: a small stream header, one standard 0x60-byte DSP header per channel, then each channel's complete ADPCM stream stored back-to-back. The wrapper repeats each channel's encoded byte length and loop-point byte offset three times. Loop state in the DSP header lets playback resume with the correct predictor history.

  Encoding chooses predictor coefficients through an iterative statistical fit, making it substantially more expensive than decoding. A 60-second stereo track typically requires roughly 100–200 seconds to encode on the measured reference system.

  See [Music System](../systems/music-system.md) for how the game actually picks which track to play — a separate question from the codec itself, resolved through a name→track table rather than anything in the `.stm` format.
