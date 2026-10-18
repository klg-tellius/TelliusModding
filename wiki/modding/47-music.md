---
id: "modding-music"
title: "Replace or add music"
description: "A complete STM music workflow covering replacement versus new identity, cue-to-track resolution, input conversion, channels, sample rate, loops, encoding, assignment, transitions, Sound Room scope, testing, and rollback"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Music", "Audio", "STM"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/47-music.md"
tutorial_kind: "task"
tutorial_track: "ai-economy-and-media"
tutorial_stage: "draft"
prerequisites: ["modding-script-editor", "modding-chapter-anatomy"]
verification: ["source-reviewed", "unknown"]
---
# Replace or add music

**Route:** Assets → Music; Game Data → Chapters; Chapter → Scripts

!!! warning "New-cue game compatibility still needs confirmation"
    The editor's STM and `gcfesnd.bin` writers are source-reviewed, but an added BGM cue has not yet completed the curriculum's Dolphin verification. Treat replacement of an existing track/cue as the conservative release path until your own built-game test passes.

## What you will make

You will first replace one existing `.stm` stream while keeping every existing `BGM_*` caller intact. Then you will add a distinct track and cue, assign it to a chapter or `BGMPlay`, and test start, loop, interruption, fade/return, and end behavior.

The exercise teaches the essential two-step identity chain:

```text
chapter or script names BGM_CUE
        → Sound/gcfesnd.bin record names sound/track
        → Sound/track.stm contains encoded audio and loop state
```

## Before you begin

Use audio you are licensed to distribute. Prepare a clean master with no unintended silence or clipping. Mono and stereo are supported; surround/multichannel input is not. Non-WAV sources require the bundled FFmpeg setup and are converted to 16-bit PCM WAV before STM encoding.

Choose one short looping retail track for the replacement exercise and export it with **Export WAV…**. Record its sample rate, channel count, duration, loop start, track filename, and every cue listed under **Music cues**. Also identify a chapter/script that calls one of those cues.

## How the editor fits together

The track list shows files in `Sound/*.stm`. Selecting one decodes it and reports sample rate, channel count, duration, and loop time. **Play** listens to a temporary decoded WAV; **Import Replacement Audio…** encodes over the selected STM. Neither control by itself changes which scenes request the track.

The **Music cues** row reads `Sound/gcfesnd.bin`. Multiple `BGM_*` cues may point to one STM. The game registers cues by symbolic name at boot; chapters, event scripts, phase code, and the Sound Room request those names, never raw list positions.

Up to four BGM channels can coexist. Scene/phase callers start, stop, and fade their own cues. A cue record resolves identity but does not decide which context outranks another or when map music returns after a story/battle interruption.

## Guided walkthrough

### 1. Replace an existing stream without changing callers

Select the target track and press **Export WAV…** to keep an audible reference. Press **Import Replacement Audio…** and choose WAV, MP3, OGG, FLAC, M4A, AAC, or WMA. For a non-WAV source, the app first asks FFmpeg to create a scratch WAV.

If the original track loops, the editor asks whether the replacement should loop. Enter the loop start in seconds. The time is rounded to a sample index and must be before the end. Choose a zero-crossing or musically continuous boundary; STM stores codec history for the boundary, but it cannot repair mismatched waveforms or reverb tails.

Read the encode confirmation. DSP-ADPCM coefficient fitting is real background work: measured expectation is roughly 1.5–2× realtime per channel, so stereo can take 3–4× the song duration. Do not close the project while the progress indicator is active.

After completion, reselect/play the track. Confirm reported duration, channel count, and loop time. Because the filename and cue records did not change, every existing caller now reaches the replacement.

### 2. Add a separate track and cue

Press **New track…**. Enter a unique lowercase filename stem containing only ASCII letters, digits, and `_`, for example `tutorial_theme_32k`. Choose the source and decide whether it loops. The editor writes `Sound/tutorial_theme_32k.stm` and normally proposes/creates `BGM_TUTORIAL_THEME` (suffixes such as `_32K` and `_LP` are removed from the suggested cue).

Cue names must start with `BGM_`, use uppercase ASCII letters/digits/underscore, and remain within the editor's length limit. The cue record points to the filename stem without `.stm`. Select the new track and confirm **Music cues** lists the new identity; “none: the game cannot play this track yet” means the stream exists but has no callable record.

Use **New cue…** only when another symbolic identity should share this stream. Multiple aliases are useful when separate callers must keep stable names, but they do not create separate audio or loop data.

### 3. Assign the cue, not the filename

For chapter map music, open **Game Data → Chapters** and select `BGM_TUTORIAL_THEME`. For event music, edit/compile the `BGMPlay` call with that exact cue. Do not pass `tutorial_theme_32k`, `.stm`, or a filesystem path to a BGM caller.

If the cue is intended for the Extras Sound Room, edit the separate fixed 64-entry **Sound Room Tracks** list under the appropriate asset surface. Adding a cue does not automatically place it in that menu, and Sound Room background illustrations are owned by another file.

### 4. Test the boundaries that reveal audio defects

Restart Play for project-data changes, then build and use Dolphin for final audio. Listen from start through at least two loop crossings. Trigger a battle, event, phase change, pause, or child scene that interrupts/fades the cue, then return to the map. Confirm the owning context restores the intended music and no stale channel continues underneath.

For one-shot music, listen through its final sample and the following scene action. Check stereo balance, clipping, unexpectedly low volume, audible loop click, encoder noise on quiet tails, and whether a skipped event releases the cue.

## Understand every control

- **Search:** filters filenames; it does not search cue aliases.
- **New track…:** creates an STM and attempts to add its initial `BGM_*` cue.
- **Delete:** only for project-added tracks; reports cue users and can remove added cues. References in chapters/scripts must still be changed first.
- **Play / Stop:** decodes to temporary WAV for local listening. This preview does not exercise game channel/fade logic.
- **Export WAV…:** writes decoded PCM for backup or analysis; it does not preserve an editable source project.
- **Import Replacement Audio…:** overwrites the selected STM while preserving filename/cue routing.
- **Music cues:** lists every BGM record whose path points at the selected stem.
- **New cue…:** appends another callable BGM record.
- **Remove cue:** removes a project-added cue; callers naming it become silent/unresolved.

## Interactions and precedence

Replacing an STM changes all cues that point to it. Adding an alias changes no audio. Reassigning a chapter changes only that chapter field, while editing a shared script/cue caller can affect many scenes.

Loop behavior belongs to STM metadata and codec state. Start/stop/fade/restore belongs to callers and the four BGM channels. Persistent option volume is another layer; it combines with per-cue and per-voice controls rather than rewriting the stream.

The global name registry has a finite capacity shared with many resource types. A few cues are harmless; mass-generating aliases is not. Prefer one stable cue per meaningful identity.

## Test matrix

| Case | Expected result |
| --- | --- |
| local preview | correct duration/channels and no obvious decode defect |
| existing replacement | all old cue callers play new audio without script edits |
| new chapter cue | chapter resolves exact `BGM_*` name to new STM |
| new script cue | compiled `BGMPlay` starts it at intended instruction |
| loop crossing ×2 | seamless timing and stable stereo image |
| one-shot ending | clean tail; following event continues |
| phase/battle interruption | caller fades/stops correct cue and restores map owner |
| pause/skip/scene exit | no orphaned layer continues |
| Sound Room | entry exists only when separately listed and plays same cue |
| clean rebuild/reopen | track and cue remain resolvable after restart |

## Troubleshooting

**The track previews but the scene is silent.** Check the selected track's cue list and the caller's exact `BGM_*` spelling. A stream with no cue is not registered for playback.

**The old music still plays.** You may have replaced a similarly named STM that the cue does not point to. Resolve cue → path from **Music cues**, then restart/rebuild.

**The loop clicks.** Move the boundary to a waveform-compatible point and include/reconcile musical tails. Codec loop history prevents decoder discontinuity, not composition discontinuity.

**A replacement changed several scenes.** Those scenes share the same cue or multiple cues share that STM. Add a distinct track/cue and reassign only the intended caller.

**Encoding takes a long time.** This is expected for stereo DSP-ADPCM. Wait for completion; a partial file is not a valid result.

**Music does not return after an event.** Inspect the event's stop/fade and restoration calls. The cue table resolves names but does not restore context automatically.

## Save, build, and revert

Track/cue edits write their asset files when the operation completes. Save chapter fields or compile/save scripts separately. Run checks, build, and retain the original STM plus `gcfesnd.bin` together.

To revert a replacement, import/restore the original STM under the same filename. To revert an addition, first replace all chapter/script/Sound Room callers, remove its project-added cues, then delete the project-added track. Restoring only the stream while leaving a removed cue cannot repair callers.

## Limits and confidence

STM decoding/encoding, channel/loop fields, cue parsing/writing, name rules, and cue-to-stream architecture are source-reviewed. Local playback deliberately omits MusyX channel allocation, fades, option mixing, and scene ownership. New tracks and appended cue records remain curriculum-level **unknown** until verified in Dolphin; this page labels that gap instead of presenting preview success as game compatibility.

## Related tutorials and references

- [Edit event scripts safely](33-script-editor.md)
- [Replace chapter-opening movies](41-chapter-opening-movies.md)
- [Add or replace sound effects](48-sound-effects.md)
- [Music System](../systems/music-system.md)
- [STM & DSP-ADPCM](../formats/stm-format.md)
- [MusyX](../formats/musyx.md)

---

[← Previous: Edit armory, vendor, forge, and gold](46-shops.md) · [All tutorials](index.md) · [Next: Add or replace sound effects →](48-sound-effects.md)
