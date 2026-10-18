---
id: "music-system"
title: "Music System"
description: "How the game decides which track to play, by name, through a generic engine-wide lookup mechanism"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Audio"]
aliases: ["tellius_archive.html#/music-system"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/music-system.md"
system_entries: ["FE9-SYS-323", "FE9-SYS-324", "FE9-SYS-325", "FE9-SYS-326", "FE9-SYS-327", "FE9-SYS-328", "FE9-SYS-329", "FE9-SYS-330", "FE9-SYS-332"]
system_reviewed: ["FE9-SYS-323", "FE9-SYS-324", "FE9-SYS-325", "FE9-SYS-326", "FE9-SYS-327", "FE9-SYS-328", "FE9-SYS-329", "FE9-SYS-330", "FE9-SYS-332"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Music System

*How the game decides which track to play, by name, through a generic engine-wide lookup mechanism*

Chapter [event scripts](../formats/event-script.md) trigger music by a *symbolic name*, never a raw track index — confirmed by parsing all 43 real chapter scripts: `externCall(BGMPlay, "BGM_EVT_IKE1")` and siblings, 76 distinct `BGM_*` names in use across the game.

## Rules and lifecycle — how a script request becomes playback

The script supplies a `BGM_*` cue, native code hashes the name into a global runtime registry, the resolved entry points at a record inside `Sound/gcfesnd.bin`, and MusyX starts the streamed track that record names. Symbolic identity is therefore separate from the `.stm` filename and codec.

## Example — one phase cue

A request for `BGM_PHASE_PL1` resolves the cue record by name, starts its target stream on one of four channels, and can fade against the enemy-phase counterpart when control changes. Renaming only the `.stm` file breaks the record path; repointing the cue record preserves script identity while changing the streamed asset.

!!! info "A single generic hash table backs every named lookup in the engine, not just music"
    The name is resolved through one general-purpose string→pointer hash table (509 buckets, chained, double-hashed) that the engine reuses for far more than music — the same mechanism backs [externCall dispatch](./events-scripting.md) itself, scene names, and other named resources throughout the game. The function that actually plays a track calls this lookup directly with the literal name string — `PlayBGM(slot, "BGM_MAP_WIN1", volume, loop)` — the same shape confirmed for scene lookups elsewhere in the engine. <span class="confidence confidence--confirmed">confirmed</span>

## The name→track table

  `Sound/gcfesnd.bin` is a proprietary, game-specific resource database sitting alongside the real MusyX sound-engine files: it holds all 142 `BGM_*` cue names, ~1,150 `SFX_*` cue names, and all 80 real [`.stm`](../formats/stm-format.md) filenames as plain strings. Its first 111 records are the `BGM_*` cues themselves, each a fixed 12-byte entry: the cue's own name, a one-byte "has a real track" flag alongside a per-cue volume-like value, and the target `.stm` path (minus its extension). At boot, every one of these records is registered by name into the same engine-wide hash table an `externCall(BGMPlay, ...)` looks up — closing the loop between a script's symbolic cue and the actual stream MusyX plays. 31 of the 76 script-referenced names match a real track exactly under simple normalization; the other 45 have naming drift a plain convention can't resolve.

  Of those 111 built-in cues, **24 are unused** in the retail game: registered names (`BGM_DUMMY_69` through `_74`, several unused `BGM_OPENING*`/`BGM_PRO0*`/`BGM_COLOSSEUM_*` slots, and a few unused event stingers) that all share one placeholder path with no backing file anywhere on the disc. They resolve by name exactly like any real cue; they simply have nothing to actually stream if ever triggered unmodified.

  Every cue name is registered at boot in the game's single by-name table, the same one that holds data records and named script functions. That table has a fixed 10,240 entries; RAM snapshots show about 6,600–6,800 in use, so roughly 3,400 names are left for everything a mod adds. Running out would hang the game while it registers names. <span class="confidence confidence--confirmed">engine</span>

## Four BGM channels, crossfaded by name

  Starting a new track doesn't simply cut off whatever was playing. The engine tracks up to **four simultaneous BGM channels** at once, each an independent playback slot. Stopping or changing a track works by name, not by slot number: given a cue name, the engine hashes it the same way as above, then checks each of the four channels' own currently-playing name (hashed the same way) to find which one, if any, is already playing that exact cue — then either cuts it immediately or runs a real per-frame volume fade-out over a caller-specified duration (every observed case fades over 100–500 ms).

  This four-channel design is what makes layered battle music possible: `BGM_PHASE_PL1`/`PL2` (a player-phase variant) and `BGM_PHASE_CP1`/`CP2` (its CPU/enemy-phase counterpart) are faded against each other through this exact mechanism as control passes between phases, rather than being spliced into one track file or hard-cut at the phase boundary.

## Selection to stream

<span id="fe9-sys-323"></span> **Music selection.** Scripts and native scene/phase code request symbolic `BGM_*` cues. The shared 509-bucket registry resolves the name to a `gcfesnd.bin` record, whose path selects the stream. Context priority belongs to the active scene caller: story/battle/victory code explicitly starts or fades its cue and the returning owner explicitly restores its map/phase context. The registry resolves identity but never decides which gameplay context outranks another.

<span id="fe9-sys-324"></span> **Transitions.** Up to four BGM channels coexist. Stop/change resolves the requested cue and each channel's current name, then cuts immediately for a duration below 1 or fades per frame for a positive duration; observed callers use 100–500 ms. Phase pairs crossfade by issuing operations for their separate channels. Pause, child-scene interruption, and restoration are caller-owned requests against those same channel objects.

<span id="fe9-sys-326"></span> **Streamed audio.** Cue records ultimately name one of 80 registered STM resources. MusyX owns buffer refill, ADPCM progress, authored looping, active-channel mixing, and release. The [STM format](../formats/stm-format.md) owns codec/block details; this system's contract is cue-to-stream lifetime. Exhausted or failed data terminates that voice and returns the channel rather than blocking its gameplay caller.

## Sequenced audio, effects, voices, and mixing

<span id="fe9-sys-325"></span> **MusyX sequence/sample system.** At boot the sound loader registers project, pool, directory, sample, library, sequence-table, and effect-table resources. Track events resolve bank patches, allocate channel/voice slots, advance controllers/envelopes/loops, mix into AX/DSP state, and release voices. Those proprietary tables are audio-engine data; gameplay only requests named cues and observes completion/stop.

<span id="fe9-sys-327"></span> **Sound-effect banks.** The registered `SFX_*` cue namespace resolves authored requests into sound records and bank/sample playback. Gameplay/UI callers supply identity and parameters; the sound engine owns voice start, priority, update, stop, and cleanup without owning the gameplay event.

The game-level SFX allocator has 28 slots arranged as four groups of seven. `play_sound_effect_by_name` resolves roughly 1,150 registered `SFX_*` identities, claims a free/replaceable slot, and stores volume, pan, priority, and lifetime state. Failure to allocate or resolve yields no sound; it never retries the gameplay action that requested it.

<span id="fe9-sys-328"></span> **Positional/attached sound.** A world or actor cue stores X/Y/Z or an attachment and updates it against the camera/listener each audio frame. The sequencer converts distance, pan, and Doppler state into channel controls including MIDI-style CC7 volume and CC10 pan. Removal, scene exit, or effect completion releases the source handle so a stale actor cannot keep a voice alive.

<span id="fe9-sys-329"></span> **Voice/utterance system.** Scene and actor context build or choose a registered utterance cue, whose bank/project determines the language/variant resource. It uses the same voice allocation and stop ownership as other sample cues. Missing/unregistered variants are silent, while presentation timing continues; interruption and skip release the voice without changing subtitle/dialogue completion.

<span id="fe9-sys-330"></span> **Mixer and options.** Persistent music and effect-volume bytes default to 100 and feed their respective playback paths; voice/sample routing remains cue/project owned. The sequencer combines that bus control with authored per-cue volume, per-voice ramps, pan, pitch, reverb/chorus sends, and DSP mixing. Pause/scene changes modify active owners and ramps, not the stored option bytes, so restoration does not compound volume.

!!! note "The built-in table already carries spare cue slots"
    Because 24 registered cue names already exist with no backing file, pointing one at a real `.stm` path (and flipping its "has a real track" byte) makes that name resolve to a real stream exactly the way any retail cue does — without growing the table itself, as long as each repointed slot gets its own path string rather than sharing the original placeholder with the other 23. <span class="confidence confidence--confirmed">confirmed</span>

## The Sound Room

<span id="fe9-sys-332"></span> The extras menu's Sound Room plays from a fixed table of 64 `BGM_` names in the executable, through the same name lookup as any other cue. The illustrations behind its menu are a separate slideshow listed in [soundroom.bin](../formats/sound-room.md). <span class="confidence confidence--confirmed">confirmed</span>

  Contrast with [Cutscenes](./cutscenes.md), where a video is instead referenced by a literal path string with no hash lookup or intermediate table at all — a mechanically simpler, if less flexible, solution to the same "trigger a media asset by name" problem.

## Interactions and limits

All audio entries on this page are reviewed without a blocking research gap. Name resolution, caller-owned context priority, four-channel fades, sequence/stream lifetimes, SFX allocation, positional controls, voice fallback, and option-to-mixer ownership establish the cue-to-output lifecycle. Proprietary bank bytes, exact attenuation coefficients, and hardware buffer sizes are lower-level tuning/format details rather than missing game-system behavior. No new primary article is needed.
