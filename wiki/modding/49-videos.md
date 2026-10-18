---
id: "modding-videos"
title: "Replace a video and manage disc size"
description: "A complete THP workflow covering slot replacement, new literal paths, dimensions, frame rate, audio, encoding, preview, script waits and skips, disc-size budgeting, testing, and rollback"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Video", "THP", "Cutscenes"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/49-videos.md"
tutorial_kind: "task"
tutorial_track: "ai-economy-and-media"
tutorial_stage: "draft"
prerequisites: ["modding-chapter-opening-movies", "modding-script-editor"]
verification: ["source-reviewed", "unknown"]
---
# Replace a video and manage disc size

**Route:** Assets → Videos; Chapter → Scripts

## What you will make

You will replace one existing THP while inheriting its playback contract, then add a short new THP and call its literal path with `MoviePlay`. You will inspect encoded frames and audio, test normal completion plus several skip timings, and compare rebuilt disc size before deciding whether the media is release-safe.

## Before you begin

Identify the exact `Movie/*.thp` path and every caller. Unlike music, video has no cue alias table: scripts name a literal path. Export or preserve the original file and record width, height, frame rate, frame count, duration, audio channel count, and frequency.

Prepare a progressive source video with a short controlled duration. Replacement is scaled/letterboxed into the selected slot's dimensions. New-video dimensions must each be multiples of 16 and remain within the editor's THP width limit. Keep important imagery inside a safe center area.

## How the editor fits together

The viewer parses the THP header and linked frame chain, decodes its JPEG-like picture and per-frame DSP-ADPCM audio, and previews sequentially. Frame 0 size comes from the main header; each frame stores the next frame's size. Audio duration comes from decoded sample counts, not padding bytes.

**Import Replacement Video…** inherits the existing THP's width, height, frame rate, audio frequency, and channel contract. **New video…** asks for dimensions/rate because no slot exists to inherit. Both use FFmpeg to decode source frames/audio and the app to encode THP.

## Guided walkthrough

### Establish the baseline

Select the source THP. Scrub the first, middle, and last frames; play it; export audio when present. Record metadata and file size. Follow the caller: `MoviePlay` uses the literal path, while chapter-opening wrappers may select a movie ID/path through chapter data.

### Replace an existing slot

Choose **Import Replacement Video…** and select a format FFmpeg can decode. The dialog states the inherited dimensions and that the image will be scaled/letterboxed. The app decodes every frame at the existing rate, decodes audio to the existing sample rate/channel count, estimates/encodes, and writes the destination only on success.

After import, reselect the THP and inspect beginning, scene cuts, middle, penultimate, and final frames. Export its encoded audio rather than trusting the source file. Verify lip/action synchronization and the final tail; audio longer than video is dropped and shorter audio leaves silence in trailing frames.

### Add a new literal identity

Choose **New video…**, provide a unique safe filename, then dimensions and frame rate. Use a known retail slot's values unless you have a reason to diverge. The new THP does not receive a registry record. Edit the event to call `Movie/<name>.thp` exactly and compile/save it.

### Test completion and skip convergence

Build and enter the exact scene. Test natural completion, skip immediately, skip during active audio, and skip one or two frames before the end. In every case the waiting script must resume exactly once, background audio/display/input ownership must return, and the next event action must occur.

Finally compare full rebuilt image size with the clean baseline and the target physical-media capacity. A file can be valid and boot in Dolphin while producing an image too large for intended hardware/disc distribution.

## Understand every control

- **New video… / Delete:** manages project-added literal files; deleting requires callers to be updated first.
- **Frame slider/navigation:** decodes specific encoded frames and exposes frame-chain corruption.
- **Play / Stop:** local sequential preview; it does not reproduce game skip/input restoration.
- **Export Audio as WAV…:** checks the audio actually encoded in the THP.
- **Import Replacement Video…:** inherits the selected slot contract.
- **New-video dimensions/rate:** defines a new contract; dimensions are multiples of 16.
- **Progress/status:** FFmpeg decoding and JPEG/DSP encoding can take several minutes for long movies.

## Interactions and precedence

The THP owns media timing; the event owns why it plays and what happens afterward. Skip must converge on the same single completion signal as natural end. Story flags, rewards, and routing must not depend on seeing an intermediate frame.

The player allocates buffers from header maxima and trusts consistent component counts, dimensions, offsets, and frame sizes. Preview success across the entire file is more meaningful than a correct first frame.

## Test matrix

| Case | Expected result |
| --- | --- |
| first/middle/last frame | image decodes with stable dimensions |
| exported encoded audio | intended channels/rate/tail and no drift |
| natural completion | following script action executes once |
| immediate/middle/late skip | same continuation and restored input/display/audio |
| missing/wrong literal path | controlled failure, never an endless scene wait |
| chapter wrapper | intended movie slot/path selected |
| clean rebuild | new/replaced file present at exact case-sensitive path |
| disc budget | output fits intended distribution medium |

## Troubleshooting

**Source plays but encoded preview fails late.** Inspect the reported frame and re-encode; a valid header/first frame does not prove the full chain.

**Audio drifts.** Match authored frame rate and inspect sample counts. Container padding is not duration.

**The event hangs after playback.** Confirm the caller, path, and both completion/skip routes; do not add a second story consequence as a workaround.

**Image is stretched or cropped.** Replacement preserves slot dimensions. Letterbox/crop the source intentionally before import.

**The disc is oversized.** Shorten/lower-complexity media or remove unused project-added assets with references already redirected. Dolphin boot is not a capacity guarantee.

## Save, build, and revert

Media import writes the THP; save/compile callers separately. Run checks, inspect project changes, build, and test all completion cases. Preserve the original THP and caller source.

To revert a replacement, restore the original THP. To remove an addition, redirect every literal caller first, then delete the project-added file. Rebuild and verify both the scene path and total size.

## Limits and confidence

THP parsing/encoding, frame-chain rules, per-frame audio packing, input conversion, and player completion ownership are source-reviewed. Local preview cannot validate GameCube decoder timing, input skip, scene teardown, or physical-disc tolerance. New/re-encoded videos therefore retain unknown built-game verification until the full matrix passes in Dolphin/hardware.

## Related tutorials and references

- [Configure chapter-opening movies](41-chapter-opening-movies.md)
- [Edit, compile, and test event scripts](33-script-editor.md)
- [THP Video Playback](../systems/video-system.md)
- [THP format](../formats/thp-format.md)

---

[← Previous: Add or replace sound effects](48-sound-effects.md) · [All tutorials](index.md) · [Next: Replace 2D graphics →](50-graphics.md)
