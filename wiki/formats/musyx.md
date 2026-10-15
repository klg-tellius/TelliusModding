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
last_reviewed: "2026-10-15"
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

## How a sound effect plays

A sound effect cue names an entry of a group's effect table, which names a *macro*: a short program of 8-byte commands. A typical effect macro sets a note, starts one sample, waits until the sample ends and stops. <span class="confidence confidence--confirmed">confirmed</span>

- **Pitch.** A sample plays at its recorded rate when the note equals the sample's base key. Most effect samples have base key 60 while their macro sets note 48, so they play an octave below their stored rate. <span class="confidence confidence--confirmed">confirmed</span>
- **Random note.** About a hundred effects (hits, scratches, footsteps, body blows) choose a note at random between two bounds, typically 46–49, each time they play, so the same cue varies by a few semitones from one play to the next. <span class="confidence confidence--confirmed">confirmed</span>
- **Layers.** An effect can name a *layer* instead of a macro: a list of macros started together, each with a key range, a transpose, a volume and a pan. Most layers are a left/right pair (pan 0 and 127) making a stereo sound; the menu jingles (item get, level up, game start) are layered. <span class="confidence confidence--confirmed">confirmed</span>
- **Delayed starts.** A macro can wait a fixed time (100 ms to 1.2 s) before starting its sample; about forty battle and event effects do, so they sound that much after the moment they are triggered. <span class="confidence confidence--confirmed">confirmed</span>
- **Echo.** Very short menu blips carry a faint echo, about 35 dB below the sound, for a few tenths of a second. <span class="confidence confidence--open">open</span>
- **Looping effects.** Sixteen movement and footstep effects loop inside their macro, and a few more use a looping sample (wing flaps, rain); they keep sounding until the game stops them. <span class="confidence confidence--confirmed">confirmed</span>
- **Envelopes.** Weather, ambience and event sounds shape their volume with an attack–decay–sustain–release envelope and fade out on key-off rather than at the end of the sample. <span class="confidence confidence--confirmed">engine</span>
- **Battle-only banks.** The `SFX_ARAM_*` cues, most of them in the magic bank, are only in sound memory during battles; played elsewhere they are silent. <span class="confidence confidence--confirmed">confirmed</span>

## Adding and replacing effects

A new effect (one sample, one macro, one effect-table entry and a new `SFX_*` cue) and a replaced one (an existing cue pointed at a new effect entry) both play in the game, alone and together; untouched cues are unaffected. A new sound must go in a group that is loaded where the cue is played; the system-sound group is always loaded. <span class="confidence confidence--confirmed">confirmed</span>
