---
id: "modding-chapter-opening-movies"
title: "Set chapter title cards and full-screen movies"
description: "A complete guide to ChapterMoviePlay, title-card identities, THP files, replacement versus new video, dimensions, frame rate, audio, script calls, skip, and continuation"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Movies", "THP", "Chapter openings"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/41-chapter-opening-movies.md"
tutorial_kind: "task"
tutorial_track: "dialogue-and-text"
tutorial_stage: "draft"
prerequisites: ["modding-script-editor", "modding-base-and-world-map-text"]
verification: ["source-reviewed", "unknown"]
---
# Set chapter title cards and full-screen movies

**Routes:** Chapter → Script; Assets → Videos; chapter image/title tools

!!! warning "Added-chapter title cards still need Dolphin proof"
    The engine relationship between `ChapterMoviePlay(N)` and `window/chapter/chapN.cms` is confirmed, but the complete title-card/file-menu table work for arbitrary added chapter numbers is not automatically solved by changing this call. Keep added-chapter results explicitly unverified until tested in Dolphin.

## What you will make

You will perform two separate exercises:

1. verify that a chapter opening passes the intended numeric identity to `ChapterMoviePlay` and displays its existing title-card image;
2. create a short new THP file, call it by literal path with `MoviePlay`, and prove both natural completion and player skip return to the next script action.

This distinction matters: chapter title cards are images drawn over a shared chapter-opening movie, while full-screen cutscenes are independent `Movie/*.thp` files.

## Before you begin

Complete [Edit and compile event scripts](33-script-editor.md). Choose a chapter with a working title card/opening and a short full-screen movie call if possible.

Record the baseline:

- `ChapterMoviePlay` numeric argument;
- chapter identity/record and current title image path;
- any file-menu chapter strip associated with the chapter;
- full-screen THP path, dimensions, frame rate, frame count, duration, audio channels, and sample rate;
- script calls immediately before and after playback;
- watched and skipped runtime outcomes.

Prepare a 3–5 second source video with a visible first and final frame plus a short sound ending before the final frame. Use media you may redistribute. Back up the chapter script, affected title image(s), and `files/Movie/` target.

Encoding uses FFmpeg for source decoding and can take minutes for long video. The app reports an estimate before writing; keep the first test short.

## How the editor fits together

Path of Radiance has two confirmed movie calls:

- `ChapterMoviePlay(N)` plays the shared `movie/chapter.thp`; `N` selects the title card `window/chapter/chapN.cms` drawn over it.
- `MoviePlay("Movie/name.thp")` opens a literal THP path and waits until the player finishes or skips it.

The title card is a 480×160 image, not rendered from the chapter title text at runtime. Save-file chapter strips are separate 312×32 images under `window/chapter2/` and are selected through a fixed executable table. Editing the opening card alone does not update the file-menu strip or add a missing table entry.

**Assets → Videos** reads THP metadata, decodes frames for preview, optionally decodes audio to a temporary WAV, replaces an existing slot while preserving its dimensions/frame rate, or creates a new THP with explicitly chosen dimensions/frame rate.

New THP dimensions must both be multiples of 16; width must stay under the encoder's displayed maximum. New videos default to 32 kHz stereo when source audio exists. Replacement videos inherit the selected THP's width, height, FPS, sample rate, and channel layout.

## Guided walkthrough

### 1. Trace the chapter-title path

Open the chapter Script and search `ChapterMoviePlay`. Select the call and inspect it through **Insert call...**. Confirm the numeric argument equals the chapter identity intended for this opening, not the source chapter from which it was copied.

Find `window/chapter/chapN.cms` for that number in the chapter image/graphics tools. Preview it and record the exact title artwork. Separately inspect `window/chapter2/chapN.cms` or the actual strip/table mapping used by the file menu.

Do not substitute the FE8Data chapter title key for either image. The text key and image assets serve different consumers.

### 2. Make a reversible title-card test

Use the existing title-card image workflow to make one unmistakable but small visual change to the current chapter's 480×160 card. Preserve dimensions and encoding. Keep the numeric `ChapterMoviePlay` argument unchanged.

Build and play the chapter opening. Confirm the changed card appears over the shared animation and that skip/finish return to the same next script step. Then restore the original image before testing a different numeric argument; changing both at once cannot prove which identity was selected.

For an added chapter, ensure its call uses the new number and that both required images exist, then log the file-menu mapping/table status separately. Do not mark it verified solely because the app preview shows the generated image.

### 3. Inspect a working THP in Assets

Open **Assets → Videos** and select a short existing cutscene. Read the metadata line: width×height, FPS, frame count, duration, and audio details.

Use the frame slider to inspect first, middle, and final frames. Choose **Play/Pause** to review timing. If audio exists, use **Export Audio as WAV...** for waveform/listening inspection. The app's preview audio is prepared separately and may drift slightly over a long movie; it is an asset check, not final sync certification.

### 4. Replace an existing video safely

For the lowest-risk first conversion, select a disposable existing slot and choose **Import Replacement Video...**. The source is scaled and letterboxed to the slot's existing dimensions, resampled to its FPS, and audio is converted to its existing sample rate/channel count.

Review the decoded frame count, duration, and whether audio was found. Accept the explicit encode confirmation only after these match the plan. Encoding writes the selected THP directly when complete.

Reopen the file, inspect first/final frames, play from frame 0, scrub near the end, and export audio if needed. Confirm duration and metadata are plausible before launching the game.

### 5. Create a new video

Choose **New video...** and enter a plain unused filename without path separators or extension, following the game's naming convention. In **New video dimensions**, choose width and height divisible by 16 and a positive FPS. For a basic test, 640×480 at 30 FPS is conventional and easy to inspect.

Select the short source. The app decodes/scales/letterboxes frames, extracts stereo 32 kHz audio when present, shows the count/duration/estimate, then encodes the new THP.

After completion, the new item is selected and its status provides the literal call path. Record `Movie/<name>.thp` exactly, including case and extension.

### 6. Wire the literal movie call

Open the disposable chapter event. Use **Insert call...** to select `MoviePlay` and choose/type the new project movie path. Insert it where the working reference plays a full-screen cutscene.

Preserve the reference's surrounding fade, music, event-mode, and following action. `MoviePlay` itself waits until playback or skip returns. Do not add a guessed duration sleep after it.

Add a clearly observable next step—a short existing message or harmless effect—so continuation can be proven. Run **Check** and save Script.

### 7. Test natural completion

Start before the event. Let the movie finish without input. Verify:

- first frame appears correctly and is not cropped unexpectedly;
- video/audio start and remain acceptably synchronized;
- the final visual/audio ending completes;
- display/audio/input ownership returns;
- the observable next script step runs once.

Listen through the final frames. The current THP encoder has a known final-frame audio-tail limitation; ending audio slightly early avoids cutting a critical syllable or impact.

### 8. Test skip and failure boundaries

Restart from the same state and skip near the beginning, middle, and final second. Every skip point must restore display/audio/input and reach the same next script step exactly once.

In a disposable copy only, test a misspelled path to understand the failure signature, then restore it. A successful compile cannot prove the literal file exists.

## Understand every control

### Video list actions

- **New video...** creates a new THP and requires a filename, target dimensions, FPS, and source media.
- **Delete** is available for added videos through the project's guarded deletion flow; audit script references first.
- Selecting a video loads metadata and builds the frame-offset list.

### Preview controls

- The frame slider decodes an individual frame without playing.
- **Play** starts at the current slider frame; **Pause** stops preview/audio.
- Preview audio is decoded from the selected start frame to a temporary WAV.
- Long playback can drift because frame stepping does not continually resynchronize to wall-clock audio.

### Export Audio as WAV

This decodes the complete THP audio for inspection. It does not modify the THP. Use it to check channel count, sample rate, content, and tail before/after import.

### Import Replacement Video

Replacement inherits the selected slot's dimensions/FPS/audio target, minimizing script and renderer changes. Source frames are scaled/letterboxed, not simply copied. The operation is destructive to that extracted THP but recoverable through the project's original backup.

### New video dimensions

- Width and height: whole numbers divisible by 16.
- Width: no greater than the displayed THP encoder limit.
- FPS: positive number.

These are encoding validity rules, not artistic recommendations. Higher resolution/FPS/length increase file size, encoding time, decode load, and memory/streaming demands.

### Script calls

- `ChapterMoviePlay(chapter)` selects the shared opening animation plus numeric title card.
- `MoviePlay(path)` selects a literal full-screen THP path.
- Both suspend their script sequence until playback ends or skip returns control.

## Interactions and precedence

- `ChapterMoviePlay`'s number selects title art; it is not a literal THP filename.
- `MoviePlay` uses a literal path; creating a THP does not add a separate cue-table record.
- Replacing a THP changes every script call to that same path.
- A new THP is inert until a script calls its exact path.
- Opening title card, save-menu strip, FE8Data title text, and movie file are separate resources.
- The fixed file-menu strip table can exclude an arbitrary added chapter even when its opening card works.
- Replacement preserves a slot's target media contract; new video requires explicit contract choices.
- Preview playback can drift; Dolphin owns final synchronization/input verification.
- Movie skip and natural completion must converge before later story/flag actions.

## Test matrix

| Case | Setup | Pass condition |
| --- | --- | --- |
| Title identity | `ChapterMoviePlay(N)` | `chapN.cms` artwork appears |
| Title finish | no skip | next opening step runs once |
| Title skip | early/mid skip | same next state |
| THP metadata | reopen new/replaced file | dimensions/FPS/frames/audio persist |
| THP first/final frame | slider inspection | correct framing and complete visual ending |
| Movie finish | literal valid path | next message/action runs once |
| Movie skip | early, middle, late | display/audio/input restored; same continuation |
| No-audio source | new THP without audio | intentional silent playback and clean return |
| Bad path copy | disposable script | failure is identified, then path restored |
| Old save/fresh route | both entry states | event eligibility and movie playback remain consistent |

## Troubleshooting

### The wrong title card appears

Compare `ChapterMoviePlay` numeric argument with the actual chapter identity and card filename. Check whether a copied opening retained its source number. Title text keys do not select this image.

### The opening card works but the save slot is blank/wrong

The file-menu strip is a separate image and uses a fixed executable mapping. Inspect `chapter2` art and table support for the chapter number.

### The new video does not appear in game

Verify exact `Movie/<name>.thp` spelling/case, that the call executes, and that the file exists in the built project. Reopen it in Assets to prove the THP parses.

### The image is stretched or cropped

Replacement/new import scales and letterboxes to the target. Compare source aspect ratio with target dimensions and inspect decoded frames before rebuilding.

### Audio ends abruptly

Move important audio earlier than the final frame and re-encode. Inspect the exported WAV and runtime tail; document the known encoder limitation.

### The opening stops after playback or skip

Inspect the following script action and reference cleanup/fade/music sequence. Do not add arbitrary waits; prove the movie call returns, then restore the reference continuation.

### Encoding takes much longer than expected

Duration, FPS, resolution, JPEG frame encoding, and DSP-ADPCM audio all contribute. Test short media first and use the estimate before approving long encodes.

## Save, build, and revert

Video import writes the THP at successful completion. Save title art through its owning image workflow, then Check/save Script and build.

To revert a replacement, restore the original THP. To remove a new video, first remove/restore every `MoviePlay` caller, then use the guarded delete for that added file. Restore title card and file-menu strip separately. Re-check the chapter opening after any partial revert.

## Limits and confidence

Movie-call selection, title-card path, THP controls, replacement/new encoding contracts, script waiting, and skip convergence are source-reviewed. Added-chapter title-card/file-menu behavior remains explicitly unverified until the required image/table work is exercised in Dolphin.

The local preview is not a synchronized production player. Final audio/video synchronization, decoder performance, input/skip cleanup, file size, and end-frame behavior require Dolphin and target hardware testing where relevant.

## Things to try

- Replace a disposable THP with a silent 3-second colour-bar test and verify exact first/final frames.
- Start preview from the middle and compare its separate audio preparation with full playback.
- Create the same clip at 15 and 30 FPS, then compare size, encode time, and runtime motion.
- Give an added chapter distinct opening and file-menu images and audit both selector paths.
- Skip at three points while logging the first post-movie action.
- Export the original/replacement audio and compare duration before runtime testing.

## Related tutorials and references

- [Edit and compile event scripts](33-script-editor.md)
- [Edit support, base, and world-map conversations](40-base-and-world-map-text.md)
- [Cutscenes](../systems/cutscenes.md)
- [THP format](../formats/thp-format.md)
- [Video system](../systems/video-system.md)
- [Chapters](../systems/chapters.md)

---

[← Previous: Edit support, base, and world-map conversations](40-base-and-world-map-text.md) · [All tutorials](index.md) · [Next: Import a translation font →](42-font-translation.md)
