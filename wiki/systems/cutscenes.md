---
id: "cutscenes"
title: "Cutscenes"
description: "How the game decides which video to play — a literal path string, simpler than music's name→table lookup"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Video"]
aliases: ["tellius_archive.html#/cutscenes"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/cutscenes.md"
---
# Cutscenes

*How the game decides which video to play — a literal path string, simpler than music's name→table lookup*

Where [music](./music-system.md) resolves a name through a shared hash table and an intermediate record, cutscene selection has no indirection at all. Chapter [scripts](../formats/event-script.md) trigger a cutscene two ways, both confirmed by parsing all 43 real scripts: `externCall(MoviePlay, "Movie/s06_M.thp")` — the literal path string sits right in the script's own bytecode — and `externCall(ChapterMoviePlay, N)`, a plain numeric literal for the recurring chapter-opening cutscene, one call per chapter.

## How a cutscene reaches the decoder

An event trigger runs bytecode, `MoviePlay` supplies a literal filesystem path, the disc filesystem returns that THP resource, and the movie player advances its linked video/audio frames. `ChapterMoviePlay` performs chapter-based selection before entering the same playback domain.

## Example

`MoviePlay("Movie/s06_M.thp")` directly identifies the asset. Replacing that string changes the requested movie; replacing the THP at the same path changes its contents without changing script logic.

  Two real scripts even branch between an E3-demo path and the normal one this way, selected by an `IsE3Version` check — a small window into build/debug scaffolding left in the shipped game.

!!! note "Because it's a literal string, a new cutscene slot is directly addressable"
    A `MoviePlay` call's operand is the plain path string itself, sitting in the script's own string pool — nothing about locating or rewriting the target it points at needs an intermediate name→id table the way [music](./music-system.md) does. <span class="confidence confidence--confirmed">confirmed</span>

  Two mechanically similar "trigger a media asset by name" problems end up solved two different ways: cutscenes by a literal string in plain sight, music by a shared runtime hash table over a table of records in `Sound/gcfesnd.bin` — both fully addressable, but only one needs no indirection at all.
