---
id: "video-system"
title: "THP Video Playback"
description: "How scripts load, buffer, synchronize, display, skip, and finish pre-rendered movies"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Video", "Cutscenes", "Engine"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/video-system.md"
system_entries: ["FE9-SYS-331"]
system_reviewed: ["FE9-SYS-331"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-13"
system_known_gaps: []
system_gap_work: []
---
# THP Video Playback

The THP player converts a movie resource into synchronized full-screen video and audio, temporarily owns presentation and skip input, and signals the waiting scene when playback has either completed or safely skipped. The [THP format](../formats/thp-format.md) describes bytes; this page describes the runtime lifecycle.

## Mental model and worked example

Think of playback as a bounded producer/consumer pipeline. Disc/file I/O feeds compressed frames into buffers, video and audio decoders turn each frame into presentable data, a scheduler chooses when to display/play them, and the scene waits on one completion result. Skip changes how quickly the player reaches completion; it must not create a second continuation path.

For example, `MoviePlay("Movie/s06_M.thp")` passes a literal path from event bytecode. The player validates the THP header, allocates its working/buffer state, reads frame data, decodes the first picture and audio samples, then begins scheduled presentation. Pressing the allowed skip input stops further visible playback, drains or cancels pending work, restores the previous audio/display/input owners, signals completion once, and lets the event continue.

## FE9-SYS-331 — THP video decoder

<span id="fe9-sys-331"></span> A THP resource contains a timed sequence of frames. Each frame can carry JPEG-like video and DSP-ADPCM audio components plus sizes/timing information. Audio sample counts belong to synchronization; 32-byte padding is storage alignment and must not be decoded as additional picture or sound.

The runtime uses Nintendo's THP SDK module (release `0x2301`, identified by its embedded January 2004 SDK banner). It receives either a literal path or a resource selected by the chapter-movie wrapper, initializes the DMA/player configuration, and starts the named `E_THPP` process. Frame 0's size comes from the main header; frame *N* carries the total size of frame *N+1*, so the player must carry that value forward. It validates the container/component/header values, prepares decode state, and hands decoded video/audio to presentation. Header dimensions, frame rate/count, component layout, frame sizes, audio channels/frequency/sample counts, and offsets must agree with the payload.

## Inputs and ownership

Inputs are movie identity/path, file bytes, scene presentation context, audio/output devices, current timing, and skip policy. The player owns its file handle, read/decode buffers, decompressor state, decoded frame surfaces, audio blocks/voice, current frame/sample counters, and completion signal.

It does not own campaign consequences or the script's reason for showing the movie. Required story flags, rewards, chapter routing, and actor state remain in event/campaign systems. This separation is why a movie load failure must return an error/completion rather than leave the VM waiting forever.

## Rules and lifecycle

1. Resolve the path and open the movie.
2. Read and validate the global header, component records, first-frame offsets, and maximum sizes.
3. Allocate or acquire read, compressed, decoded-video, and decoded-audio storage.
4. Fill the initial frame buffers and initialize video/audio decoders.
5. Decode frame components and schedule them using authored rate/sample counts.
6. Present the picture and queue/play audio while subsequent frames are prepared.
7. Poll allowed input and scene cancellation; on skip, converge on the completion path.
8. Stop audio, release buffers/file/decoder/display/input ownership, and signal the waiting caller exactly once.

The exact implementation may overlap reading and decoding, but ownership rules do not change. No buffer can be reused while its consumer still needs it; no completion can fire while an asynchronous worker can still write into released state.

## Synchronization and failure behavior

Video timing comes from the authored frame rate while audio timing comes from each frame's decoded sample count. Padding and compressed byte size never contribute duration. Playback is sequential—there is no gameplay seek operation—and both script entry points suspend their caller until the player process reaches its one completion path.

Malformed dimensions, component counts, offsets, frame sizes, or audio metadata must fail before unsafe allocation/read. A truncated later frame requires full teardown. Missing audio may permit silent video only if the component layout says so; a missing required component is not the same case. Unsupported regional/revision assets should not be guessed from a filename alone.

Skip is also a failure-sensitive boundary. It must cancel or join outstanding reads/decode, stop the movie voice, restore background audio where the scene expects it, clear the full-screen surface/input lock, and report completion. A second skip/completion callback must be ignored after ownership has been released.

## Implementation trail and interactions

The trace starts at `MoviePlay` and `ChapterMoviePlay` native bridges, follows path/index resolution into the THP player, and then maps file open, allocation, header parsing, buffer fill, component decode, timing, display/audio submission, input polling, completion signal, and destructor/cleanup. Corrupt-file tests should vary one field at a time and log the first diagnostic/control outcome.

The system interacts with [Cutscenes & Credits](./cutscenes.md), [Events & Scripting](./events-scripting.md), [Input, Menus & Options](./input-menus-and-options.md), [Graphics & Images](./graphics-system.md), and [Music System](./music-system.md). Scene code selects and waits; THP playback decodes and presents.

## Review boundary

FE9-SYS-331 is reviewed without a blocking gap. The exact THP frame chain, video/audio codecs, alignment rules, timing inputs, SDK/player identity, process entry, sequential presentation, script wait, skip convergence, and teardown ownership are established. SDK-internal buffer dimensions and device-underflow policy are platform implementation details rather than unknown game-system behavior. No new primary article is needed.
