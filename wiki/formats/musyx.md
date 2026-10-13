---
id: "musyx"
title: "MusyX Audio Resources"
description: "Numeric sample directories and sample banks used by the GameCube sound engine"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Audio"]
aliases: ["tellius_archive.html#/musyx"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/musyx.md"
---
# MusyX Audio Resources

*Numeric sample directories and sample banks used by the GameCube sound engine*

MusyX is the sound engine used by the game. Its `.sdir` files are directories describing samples and their numeric identifiers; corresponding `.samp` files hold encoded sample payloads. These resources primarily serve effects and instrument/sample playback rather than long streamed music.

## How directory and bank cooperate

The directory provides metadata and numeric identity; the sample bank provides encoded waveform bytes. A consumer resolves an ID through the directory, locates the matching payload, and gives it to the MusyX playback engine.

## Example and boundary

A short sound effect can be addressed by numeric sample metadata and decoded from `.samp`. A chapter BGM cue follows a different route through [gcfesnd.bin](./gcfesnd.md) to a streamed [STM track](./stm-format.md); searching MusyX sample IDs alone will not explain that mapping.

  MusyX's core tables use numeric IDs, not the readable `BGM_*` and `SFX_*` strings used by game logic. [gcfesnd.bin](./gcfesnd.md) supplies that game-specific naming layer. Long background tracks use [STM containers](./stm-format.md), whose audio payload is GameCube DSP-ADPCM.
