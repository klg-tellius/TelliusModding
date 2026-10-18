---
id: "modding-sound-effects"
title: "Add or replace sound effects"
description: "A complete MusyX sound-effect workflow covering cue identity, groups, banks, samples, macros, replacement versus addition, volume, pan, range, ARAM cost, contextual testing, and rollback"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Sound effects", "MusyX", "Audio"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/48-sound-effects.md"
tutorial_kind: "task"
tutorial_track: "ai-economy-and-media"
tutorial_stage: "draft"
prerequisites: ["modding-music", "modding-script-editor"]
verification: ["source-reviewed", "unknown"]
---
# Add or replace sound effects

**Route:** Assets → Sound Effects

## What you will make

You will replace the audio reached by one existing `SFX_*` cue while preserving its callers, then add a separate cue with explicit group, volume, pan, and range settings. You will inspect the read-only macro, estimate sound-memory cost, call the cue in its real context, and test repetition, overlap, interruption, and scene teardown.

## Before you begin

Prepare a short mono source you may distribute. WAV is direct; MP3, OGG, FLAC, M4A, AAC, and WMA require FFmpeg conversion. Trim unwanted silence, remove clipping, and keep the first exercise below ten seconds and roughly 256 KiB encoded.

Find the exact existing cue and caller. Record its cue name, sound ID, group, volume, pan, flags, range, sharing count, and macro listing. Exported source audio is not the only behavior: pitch, delay, layers, looping, and envelopes can come from the macro.

!!! warning "Experimental write path"
    Added and replaced effects are supported by the editor's writers, but the curriculum still marks built-game compatibility unknown. Keep the project originals and finish in Dolphin.

## How the editor fits together

The playback chain is `SFX_* cue → sound ID → loaded FX group → effect entry → macro/layer → sample`. `gcfesnd.bin` owns readable cue names and defaults. MusyX `.proj`, `.pool`, `.sdir`, and `.samp` files own groups, macros, sample metadata, and encoded payloads.

**Replace audio…** keeps the selected cue name but appends a new sample, macro, and FX entry, then repoints that cue's sound ID. Other cues that previously shared the old sound ID remain unchanged. **Add sound effect…** creates all those resources plus a new `SFX_*` record.

A group is a load boundary. A sound is available only while its group is resident. The system/menu group is the safest default for a broadly used new cue; battle-only groups can be silent on maps or menus.

## Guided walkthrough

### Inspect before replacing

Search by cue text or numeric sound ID and optionally filter **Group**. Select the cue. Read its sharing count: several names can resolve to the same original sound. Double-click or press **Play**, then read **Sound macro** from top to bottom. Look for note changes, random note, waits, sample start/stop, layers, ADSR, and loops.

Local playback follows samples, layers, note changes, fixed waits, and linear ADSR. It omits panning, reverb, and macro-variable behavior, so stateful or spatial effects are only approximate.

### Replace while keeping callers

Press **Replace audio…**, choose the source, and confirm the reported sample rate, duration, mono conversion, and estimated encoded size. Keep the old group unless you have proven the caller loads another group. Press **Replace** and wait for DSP-ADPCM encoding.

Reselect the cue. Its name and caller identity remain stable, but its sound ID may now point to the newly appended effect entry. Preview it, then trigger every known caller. Because the replacement gets a simple generated macro, elaborate original randomization, layers, delay, or looping are not automatically reproduced.

### Add a distinct cue

Choose **Add sound effect…** and enter a unique uppercase ASCII `SFX_*` name. Select a group that is loaded in the target scene. Set:

- **Volume** `0–127`: cue default gain; begin near a comparable retail sound.
- **Pan** `0–127`: 0 left, 64 center, 127 right. Local preview does not prove it.
- **Range**: an inferred distance-like field read by engine accessors; copy a comparable cue unless you have a controlled spatial test.

The import is mono. For authored stereo width or layered behavior, a one-sample generated cue is not equivalent to a retail layer macro. Add it, then update the intended script/data caller to the exact `SFX_*` identity and compile/save that owner.

### Test in context

Trigger the cue beside music, voice, and other effects. Compare loudness, timing, panning/attenuation, and priority. Repeat rapidly to expose voice stealing or overlap. Leave or skip the scene while it plays and verify the voice stops. For battle-only use, test both map and full-battle presentation if either can call it.

## Understand every control

- **Search / Group:** filters the cue table; it changes no resource.
- **Cue, Sound ID, Volume, Pan, Flags, Range:** decoded `gcfesnd.bin` fields. Flags/Range are partly inferred and should be copied from a close analogue.
- **Play / Stop:** approximate local render through the decoded banks.
- **Sound macro:** read-only command listing; it explains behavior but cannot be edited here.
- **Replace audio…:** preserves the cue name and writes a new backing effect.
- **Add sound effect…:** adds a new cue and backing effect with simple generated macro.
- **Delete:** removes only a project-added cue; its appended bank content remains, and retail cues cannot be deleted.

## Interactions and precedence

The cue's default volume/pan combines with macro/layer controls, gameplay-supplied spatial parameters, bus volume, and mixer state. Group residency precedes all of them: an unloaded group makes a valid cue silent. The allocator has finite voices; priority and age decide which sound is replaced under load.

Long or large samples consume scarce ARAM while their group is loaded. A successful write proves structural encoding, not that every scene can afford the enlarged group.

## Test matrix

| Case | Expected evidence |
| --- | --- |
| isolated preview | sample decodes, duration and pitch are plausible |
| original caller | replaced cue plays without caller edits |
| shared old sound ID | untargeted alias retains original audio |
| new caller | exact new `SFX_*` resolves in intended scene |
| wrong/unloaded group | silence demonstrates load-boundary dependency |
| rapid repetition | acceptable overlap and voice allocation |
| music + voice | useful loudness without clipping/masking |
| positional call | in-game pan/range behaves like analogue cue |
| skip/scene exit | voice is released, including loops/tails |
| clean rebuild | cue and bank resources still resolve |

## Troubleshooting

**Preview works but the game is silent.** Check exact cue spelling, caller compilation, and group residency. Preview can load banks the current game scene does not.

**Pitch or timing differs from the original.** The original macro may change note or delay sample start. Replacement generates a simpler path.

**The effect is centered in preview.** Panning is deliberately omitted locally; judge it in game.

**Another cue did not change.** Replacement repoints only the selected cue, even if it shared the old sound ID.

**A scene becomes unstable after a large import.** Restore the originals and use a shorter/lower-rate source or a more suitable group. Treat ARAM warnings as capacity warnings, not cosmetic messages.

## Save, build, and revert

The import writes all generated bank/catalog outputs only after construction succeeds and keeps project originals. Save/compile the caller separately, run checks, build, and test in Dolphin.

To revert, restore the affected `Sound` originals together. Removing a project-added cue does not compact appended sample/macro content. For a replacement, restoring only `gcfesnd.bin` without matching banks can create mismatched IDs; restore the transaction's file set as a unit.

## Limits and confidence

Cue decoding, group ownership, sample/macro structure, write transaction, generated replacement behavior, and preview omissions are source-reviewed. Flags and range retain inferred semantics. Appended-bank compatibility and real hardware/Dolphin memory behavior remain unverified for this curriculum, so the page remains a draft with `unknown` game verification.

## Related tutorials and references

- [Replace or add music](47-music.md)
- [Edit, compile, and test event scripts](33-script-editor.md)
- [MusyX Audio Resources](../formats/musyx.md)
- [Music System](../systems/music-system.md)

---

[← Previous: Replace or add music](47-music.md) · [All tutorials](index.md) · [Next: Replace a video and manage disc size →](49-videos.md)
