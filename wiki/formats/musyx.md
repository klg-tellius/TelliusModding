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
- **Envelopes.** River, forest and weather ambience, bird wing flaps, horse hooves in battle and a few battle and event sounds shape their volume with one of five attack–decay–sustain–release envelopes (below) and fade out on key-off rather than at the end of the sample. <span class="confidence confidence--confirmed">engine</span>
- **Battle-only banks.** The `SFX_ARAM_*` cues, most of them in the magic bank, are only in sound memory during battles; played elsewhere they are silent. <span class="confidence confidence--confirmed">confirmed</span>

## Sound macro commands

A macro command is 8 bytes: two big-endian words. The opcode is the low 7 bits of the first word; the other bytes are the command's fields. The game's interpreter runs up to 32 commands per call and has the full MusyX 2.0 set of 84 commands; any other opcode is skipped. <span class="confidence confidence--confirmed">confirmed</span>

The shipped banks use 21 of them:

<div class="table-wrap">
<table class="wikitable"><tr><th>Opcode</th><th>Command</th><th>What it does</th></tr>
  <tr><td>0x00</td><td>end</td><td>Ends the macro and frees the voice</td></tr>
  <tr><td>0x06</td><td>goto</td><td>Continues at a command of a macro (the movement loops)</td></tr>
  <tr><td>0x07</td><td>wait (ms)</td><td>Waits a time in milliseconds, or until key-off and/or the end of the sample (time 0xFFFF)</td></tr>
  <tr><td>0x0C</td><td>set ADSR</td><td>Volume envelope from a curve table (below)</td></tr>
  <tr><td>0x10</td><td>start sample</td><td>Starts a sample (id in bits 8–23 of the first word) at an offset</td></tr>
  <tr><td>0x11</td><td>stop sample</td><td>Stops the sample at once</td></tr>
  <tr><td>0x12</td><td>key off</td><td>Starts the envelope release</td></tr>
  <tr><td>0x13</td><td>if random</td><td>Jumps unless a random byte is below a threshold</td></tr>
  <tr><td>0x17</td><td>random note</td><td>Picks a note between two bounds</td></tr>
  <tr><td>0x18</td><td>add to note</td><td>Adds a signed number of semitones to the current or the played note</td></tr>
  <tr><td>0x19</td><td>set note</td><td>Sets the note</td></tr>
  <tr><td>0x31, 0x38</td><td>age counter</td><td>Voice age and ageing speed (which voice is stolen first when all are busy)</td></tr>
  <tr><td>0x33</td><td>pitch-wheel range</td><td>Semitones up and down for a full pitch bend (default 2)</td></tr>
  <tr><td>0x41, 0x42, 0x47</td><td>panning / pitch-wheel / surround select</td><td>Route a MIDI controller or a macro variable into panning, the pitch wheel or front/back panning; up to four sources combined by replace, add, multiply or subtract</td></tr>
  <tr><td>0x60, 0x64</td><td>add variables / add value</td><td>Variable arithmetic, clamped to 16 bits</td></tr>
  <tr><td>0x65</td><td>set variable</td><td>Stores a value in a variable</td></tr>
  <tr><td>0x70</td><td>if equal</td><td>Jumps within the macro when two variables are equal</td></tr></table>
</div>

Variables 0–15 belong to the voice, 16–31 are shared by every voice. <span class="confidence confidence--confirmed">confirmed</span>

## Envelopes

The curve tables of the pool hold the envelopes of the set-ADSR command: four little-endian 16-bit values, attack and decay in milliseconds, sustain level (0x1000 = full volume) and release in milliseconds. The engine steps the envelope once per millisecond: linear attack from silence, linear decay to the sustain level, then linear release from key-off. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table class="wikitable"><tr><th>Table</th><th>Attack</th><th>Decay</th><th>Sustain</th><th>Release</th><th>Used by</th></tr>
  <tr><td>0</td><td>514 ms</td><td>1000 ms</td><td>full</td><td>303 ms</td><td>no cue (one macro no effect or song reaches)</td></tr>
  <tr><td>1</td><td>500 ms</td><td>1000 ms</td><td>full</td><td>1003 ms</td><td>river, forest and weather ambience (map and battle), four song instruments</td></tr>
  <tr><td>2</td><td>1000 ms</td><td>1000 ms</td><td>full</td><td>1003 ms</td><td>no cue (four macros no effect or song reaches)</td></tr>
  <tr><td>3</td><td>0</td><td>1000 ms</td><td>full</td><td>303 ms</td><td>bird wing flaps, event EXP allotment, battle action sounds 434–438</td></tr>
  <tr><td>4</td><td>0</td><td>1000 ms</td><td>full</td><td>319 ms</td><td>horse hooves in battle</td></tr></table>
</div>

## Effects that remember earlier plays

Three groups of effects keep state in the shared variables:

- **Dragon wings** (`SFX_BMP_MOVE_DRAGON1`) step through a fixed sequence of sixteen wing-beat samples (four distinct recordings), one step per play, and start over after the sixteenth. <span class="confidence confidence--confirmed">confirmed</span>
- **Triangle attack** (`SFX_BMP_SPECIAL_TRIATTACK1`) plays a different one of three samples on each of its three plays, then resets. <span class="confidence confidence--confirmed">confirmed</span>
- **Bonus EXP allotment** (`SFX_SYS_CAPACITY_UP1`, `_DOWN1`, `_RESET1`): up adds 10 to a shared variable and down subtracts 10, reset clears it, and the variable drives the pitch wheel (range 12 semitones), so the tick sound moves in pitch as points are moved. <span class="confidence confidence--confirmed">engine</span>

## Songs: pitch bend

Each song pattern can point at a pitch-bend stream and a modulation stream: delta-coded events, a tick delta (one byte, or two with the top bit set) followed by a signed value delta (7 bits in one byte, or 15 bits in two), ended by `80 00`. The bend starts at the centre (0x2000) when the pattern starts. 151 patterns carry a pitch-bend stream (the ambience loops and some special attacks); none uses modulation. A full bend moves the note by the voice's pitch-wheel range. <span class="confidence confidence--confirmed">confirmed</span>

## File layout details

- **`.sdir` sample info.** Each sample's 0x28-byte ADPCM block holds the coefficient count (8), the initial predictor/scale (the first byte of the sample data), the loop predictor/scale and the two history samples at the loop start, then the 16 coefficients. Every sample is DSP-ADPCM. <span class="confidence confidence--confirmed">confirmed</span>
- **`.proj` id lists.** Each group lists the macros, samples, curve tables, keymaps and layers it loads: 16-bit ids ended by 0xFFFF, where an id with the top bit set starts an inclusive range closed by the next value. Layer lists store the layer number without its 0x8000 flag. <span class="confidence confidence--confirmed">confirmed</span>
- **`.pool`.** Four chains (macros, curve tables, keymaps, layers), each of `size, id, padding` entries ended by 0xFFFFFFFF. The keymap chain is empty in this game. <span class="confidence confidence--confirmed">confirmed</span>

In the editor, the Sound Effects page lists the macro of the selected cue command by command.

## Adding and replacing effects

A new effect (one sample, one macro, one effect-table entry and a new `SFX_*` cue) and a replaced one (an existing cue pointed at a new effect entry) both play in the game, alone and together; untouched cues are unaffected. A new sound must go in a group that is loaded where the cue is played; the system-sound group is always loaded. <span class="confidence confidence--confirmed">confirmed</span>
