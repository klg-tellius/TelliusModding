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
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/music-system.md"
---
# Music System

*How the game decides which track to play, by name, through a generic engine-wide lookup mechanism*

Chapter [event scripts](../formats/event-script.md) trigger music by a *symbolic name*, never a raw track index — confirmed by parsing all 43 real chapter scripts: `externCall(BGMPlay, "BGM_EVT_IKE1")` and siblings, 76 distinct `BGM_*` names in use across the game.

## How a script request becomes playback

The script supplies a `BGM_*` cue, native code hashes the name into a global runtime registry, the resolved entry points at a record inside `Sound/gcfesnd.bin`, and MusyX starts the streamed track that record names. Symbolic identity is therefore separate from the `.stm` filename and codec.

!!! info "A single generic hash table backs every named lookup in the engine, not just music"
    The name is resolved through one general-purpose string→pointer hash table (509 buckets, chained, double-hashed) that the engine reuses for far more than music — the same mechanism backs [externCall dispatch](./events-scripting.md) itself, scene names, and other named resources throughout the game. The function that actually plays a track calls this lookup directly with the literal name string — `PlayBGM(slot, "BGM_MAP_WIN1", volume, loop)` — the same shape confirmed for scene lookups elsewhere in the engine. <span class="confidence confidence--confirmed">confirmed</span>

## The name→track table

  `Sound/gcfesnd.bin` is a proprietary, game-specific resource database sitting alongside the real MusyX sound-engine files: it holds all 142 `BGM_*` cue names, ~1,150 `SFX_*` cue names, and all 80 real [`.stm`](../formats/stm-format.md) filenames as plain strings. Its first 111 records are the `BGM_*` cues themselves, each a fixed 12-byte entry: the cue's own name, a one-byte "has a real track" flag alongside a per-cue volume-like value, and the target `.stm` path (minus its extension). At boot, every one of these records is registered by name into the same engine-wide hash table an `externCall(BGMPlay, ...)` looks up — closing the loop between a script's symbolic cue and the actual stream MusyX plays. 31 of the 76 script-referenced names match a real track exactly under simple normalization; the other 45 have naming drift a plain convention can't resolve.

  Of those 111 built-in cues, **24 are unused** in the retail game: registered names (`BGM_DUMMY_69` through `_74`, several unused `BGM_OPENING*`/`BGM_PRO0*`/`BGM_COLOSSEUM_*` slots, and a few unused event stingers) that all share one placeholder path with no backing file anywhere on the disc. They resolve by name exactly like any real cue; they simply have nothing to actually stream if ever triggered unmodified.

## Four BGM channels, crossfaded by name

  Starting a new track doesn't simply cut off whatever was playing. The engine tracks up to **four simultaneous BGM channels** at once, each an independent playback slot. Stopping or changing a track works by name, not by slot number: given a cue name, the engine hashes it the same way as above, then checks each of the four channels' own currently-playing name (hashed the same way) to find which one, if any, is already playing that exact cue — then either cuts it immediately or runs a real per-frame volume fade-out over a caller-specified duration (every observed case fades over 100–500 ms).

  This four-channel design is what makes layered battle music possible: `BGM_PHASE_PL1`/`PL2` (a player-phase variant) and `BGM_PHASE_CP1`/`CP2` (its CPU/enemy-phase counterpart) are faded against each other through this exact mechanism as control passes between phases, rather than being spliced into one track file or hard-cut at the phase boundary.

!!! note "The built-in table already carries spare cue slots"
    Because 24 registered cue names already exist with no backing file, pointing one at a real `.stm` path (and flipping its "has a real track" byte) makes that name resolve to a real stream exactly the way any retail cue does — without growing the table itself, as long as each repointed slot gets its own path string rather than sharing the original placeholder with the other 23. <span class="confidence confidence--confirmed">confirmed</span>

## The Sound Room

  The extras menu's Sound Room plays from a fixed table of 64 `BGM_` names in the executable, through the same name lookup as any other cue. The illustrations behind its menu are a separate slideshow listed in [soundroom.bin](../formats/sound-room.md). <span class="confidence confidence--confirmed">confirmed</span>

  Contrast with [Cutscenes](./cutscenes.md), where a video is instead referenced by a literal path string with no hash lookup or intermediate table at all — a mechanically simpler, if less flexible, solution to the same "trigger a media asset by name" problem.
