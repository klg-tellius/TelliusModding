---
id: "modding-backgrounds"
title: "Create and display dialogue backgrounds"
description: "An in-depth workflow for background TPL images, RID resources, layers, cross-fades, brightness, overlays, script calls, dialogue context, and runtime verification"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Backgrounds", "Dialogue", "Graphics"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/38-backgrounds.md"
tutorial_kind: "task"
tutorial_track: "dialogue-and-text"
tutorial_stage: "draft"
prerequisites: ["modding-dialogue-editor", "modding-script-editor"]
verification: ["source-reviewed", "unknown"]
---
# Create and display dialogue backgrounds

**Routes:** Assets → Backgrounds; Chapter → Dialogue; Chapter → Script

## What you will make

You will add a new static dialogue background from one image, inspect the generated TPL and `RID_` resource, display it in the Dialogue preview, then call it from a controlled chapter event. After the static version works, you will add a second same-size image as a cross-faded layer test and compare timing, brightness, and overlay behavior.

The key distinction is between pixels and composition:

- the file under `files/s/` stores one or more encoded TPL images;
- `files/s/rect.bin` stores the named `RID_` resource that refers to those images and describes how they are drawn;
- dialogue notation or a script call selects the RID by name.

Replacing a TPL does not create a new resource name, and creating an RID does not make any event execute it.

## Before you begin

Complete [Author and connect a dialogue scene](37-dialogue-editor.md). Choose a short dialogue event whose current background is known and whose script caller can be triggered repeatedly.

Prepare one source image you have permission to use. Use an aspect ratio close to the existing full-scene backgrounds and avoid vital details at extreme edges until the in-game crop is known. For the later cross-fade test, prepare a second image at the same dimensions—such as a darker version of the same scene.

Record:

- the current background resource name and source filename;
- its image dimensions/count;
- RID layer mode, period, brightness, and overlay;
- the dialogue layout and inherited context;
- the caller's existing transitions/waits.

Choose a unique resource name beginning with the project's normal `RID_` convention. Search Backgrounds, Dialogue, and Script to avoid collisions. Back up `files/s/rect.bin`, the relevant `files/s/` images, the chapter message file, and script.

## How the editor fits together

**Assets → Backgrounds** lists standalone scene-art files under `files/s/` except `rect.bin`. A file can contain multiple TPL images. The right panel shows each image, its dimensions/format, and every Rect resource that uses that file.

The **Rect resource (`s/rect.bin`)** panel selects one named resource and exposes:

- layer mode;
- period in seconds;
- brightness from 0 through 255, where 255 is unchanged;
- optional overlay/effect;
- layer count, resource size, and texture indices.

**Add New Background...** accepts one or several ordinary images. Several inputs become same-size layers/images for cross-fading; if dimensions differ, the importer resizes later images to the first image's size. It writes the image asset and adds the named resource to `rect.bin`.

The Dialogue Background control inserts a background action into the message. A script can construct a resource directly with the catalogued `RectBuild` call. Which route to use depends on the working scene: preserve the existing presentation pattern instead of building the same background twice.

## Guided walkthrough

### 1. Inspect a working resource end to end

Open **Assets → Backgrounds** and search the current RID or filename. Select the file. If it contains several images, click every thumbnail and record its dimensions and encoding information.

In **Rect resource**, select the RID used by the dialogue. Read the summary: number of layers, output size, and texture indices. Record **Layers**, **Period**, **Brightness**, and **Overlay** without changing them.

Open the dialogue message and find its `<Background:...>` action, or open Script and find the `RectBuild` call. This establishes the complete path from consumer name to rect record to TPL image.

### 2. Add a single-image static background

Choose **Add New Background...** and select only the first source image. Enter the unique RID name. The app converts the image to RGB, creates the TPL in `files/s/`, appends the new resource to `rect.bin`, and reports the exact call name.

Search for the new RID immediately. Select its file and image thumbnail. Confirm the preview, dimensions, and resource association. If the resource/file is not present, do not add it again under another name; resolve the reported write/import error.

### 3. Establish neutral RID settings

In the new RID's resource panel:

- choose the static/single-layer mode produced by the importer;
- keep a harmless period value even though one image cannot visibly cross-fade;
- set **Brightness** to 255;
- set **Overlay** to none.

Choose **Save Resource**. This writes `rect.bin`; it is separate from **Save**, which writes a replacement image file staged through **Import Replacement Image...**.

Switch to another asset and back. Verify that the RID settings persisted.

### 4. Preview it through Dialogue

Open the test message in **Chapter → Dialogue**. Use **Background → Search...** and choose the new RID. This inserts or replaces the message's background action.

Reset **Initial scene context** so the preview is proving this message's explicit background rather than an inherited one. Play from the beginning and inspect the first frame, text readability, portrait contrast, and transition into/out of the next message.

If the scene's established script uses `RectBuild` outside the message instead, restore the message action and follow that script pattern. Do not leave both paths active simply because both preview separately.

### 5. Connect a script call when the reference requires it

Open the event in Script and use **Insert call...** to find `RectBuild`. Supply the exact new RID from the picker/help. Copy the working reference's surrounding fade, wait, event-mode, and cleanup sequence.

Run **Check** and save Script. A valid signature proves only that the call is shaped correctly; it cannot verify RID spelling or the asset's visual result.

### 6. Test the static version in context

Save the Dialogue message if it changed, reopen it, then start the event from a clean state. Confirm:

- the old background is gone at the intended transition;
- the new background appears once;
- it remains behind the correct text/portraits;
- no previous background flashes through unexpectedly;
- the following scene inherits or replaces it as designed;
- skip reaches the same following state.

Resolve this baseline before adding animation, brightness, or weather.

### 7. Add and test multiple images

For the cleanest animation experiment, add a second new background resource using both prepared images in one **Add New Background...** operation. The first image establishes dimensions; the app resizes other inputs to match if needed. Prefer pre-sizing them yourself so composition does not shift.

Select the resulting resource and choose its multi-layer/cross-fade mode. Set **Period** to an obvious value such as 2.0 seconds. Keep brightness 255 and overlay none. Save Resource, then preview long enough to observe a full cycle.

Test periods 0.5, 2.0, and 8.0 seconds one at a time. Record whether period represents the transition/cycle behavior expected by the chosen mode rather than assuming a universal animation definition.

### 8. Isolate brightness and overlay

Return period to the chosen value. Compare brightness 255 with a lower controlled value such as 160. Brightness changes the composed resource; it is not an image-editor exposure correction. Confirm portraits/text remain readable.

Restore 255 before testing one documented Overlay option. Observe the app preview and then Dolphin. Weather/effect overlays can depend on engine/runtime presentation and should not be approved from a thumbnail alone.

## Understand every control

### Background list and images

- The search field matches filename or associated RID name.
- **Add New Background...** creates a new TPL plus Rect resource.
- **Images in this file** selects individual TPL images when a file holds several.
- **Import Replacement Image...** replaces only the selected image while retaining its file/resource identity.
- **Save** writes pending replacement-image bytes.

A replacement image is resized/encoded into the existing slot contract; check its reported dimensions and visual crop. Adding a resource and replacing a file are different operations.

### Rect resource selector

One TPL file may be used by several RIDs. Select the exact consumer you intend to edit. Changing shared resource/image data can affect every scene that selects it.

### Layers

The mode tells the engine how the resource's layers/images are combined over time. Use the displayed named choices and copy an existing resource with the desired behavior. “Several images” does not automatically mean a particular fade direction or loop semantics.

### Period

Period is stored in seconds and accepts 0.1 through 60 in this editor. It controls layer cross-fade timing for applicable modes. Static single-image output will not demonstrate it.

### Brightness

Brightness is 0–255; 255 leaves the resource unchanged. Lower values darken the composed presentation. Test with actual text/portraits rather than tuning the empty background alone.

### Overlay

Overlay selects an optional known effect such as weather behavior exposed by the resource format. It is part of resource composition and may be animated/runtime-dependent.

### Save Resource versus Save

**Save Resource** writes `rect.bin` settings. **Save** writes a staged replacement image. **Add New Background...** writes both new pieces during the add workflow. Always re-open both RID and image after saving.

## Interactions and precedence

- The consumer uses the RID string; the RID points to layer files/texture indices.
- Replacing a file changes every RID layer that references that file.
- Editing one RID's mode/brightness/overlay does not rewrite the source pixels.
- Dialogue explicit background actions override inherited scene state at their action point.
- Manually supplied Preview context is not saved and can hide a missing background action.
- Calling `RectBuild` and inserting the same Dialogue background action can create redundant transitions/state.
- Layer period matters only for a mode with multiple applicable layers.
- Later images are resized to the first during multi-image creation; prepare equal dimensions to retain framing.
- Saving rect settings, image bytes, Dialogue, and Script are separate operations.

## Test matrix

| Case | Setup | Pass condition |
| --- | --- | --- |
| Asset reopen | new RID/file | name, image, dimensions, and association persist |
| Neutral static | one image, brightness 255, no overlay | exact source composition appears |
| Reset preview | no inherited background | explicit message/script setup still works |
| Inherited preview | real preceding message | no flash or duplicate transition |
| Script caller | fresh pre-event state | exact RID builds once |
| Cross-fade | two equal-size images, 2 s | complete intended cycle observed |
| Brightness | 255 versus 160 | controlled darkening with readable foreground |
| Overlay | none versus one effect | only intended overlay changes |
| Skip | skip background scene | next event state remains correct |
| Dolphin | built project | crop, timing, overlay, and transitions match intent |

## Troubleshooting

### The RID exists but nothing appears

Check the exact RID passed by Dialogue/Script, whether the call/action executes, whether the RID has valid layers, and whether a later action immediately replaces it. Do not call the TPL filename where an RID is expected.

### The wrong scene changes after replacing an image

The TPL is shared by multiple RIDs. Inspect every resource in the selector that uses the file. Create a new file/resource for an independent visual rather than replacing shared pixels.

### The animation jumps or shifts

Source images had different dimensions/framing and were resized to the first. Pre-size and align them identically, then recreate or replace the layers.

### Preview works but the game flashes the old background

Inspect the true preceding context and the reference fade/wait sequence. Preview may begin after state that the runtime establishes visibly.

### Brightness or overlay has no visible effect

Confirm you saved the selected RID rather than another resource using the same file, and that the mode/effect is applicable. Finish the check in Dolphin.

### Image changes disappear after switching files

Replacement edits were pending and **Save** was not used. Rect settings use **Save Resource**; each has an independent save path.

## Save, build, and revert

Save the new/edited TPL, save `rect.bin` through **Save Resource**, save Dialogue, then Check/save Script. Reopen each resource before building.

To revert a new background, remove/restore the consumer references first, then restore `rect.bin` and remove/restore the generated TPL through the project backup. To revert a replacement, use the project's original-file restore for that TPL and restore any RID settings separately. Never delete a shared file before auditing all RIDs that use it.

## Limits and confidence

File/RID relationships, controls, ranges, image creation/resizing, and save separation are source-reviewed. Named layer modes and effects are decoded, but unusual multi-layer runtime composition can differ from the illustrative preview.

Large assets consume game memory and unusual dimensions/layouts can behave differently in-engine. Cross-fades, overlays, event transitions, and skip paths require Dolphin verification.

## Things to try

- Create day/night images with identical framing and compare three period values.
- Reuse one TPL in two copied RIDs with different brightness to demonstrate resource-versus-pixel separation.
- Replace one image in a multi-image TPL and audit every RID that references it.
- Start the dialogue with inherited background, then add an explicit switch halfway through.
- Compare a Dialogue background action with the chapter's existing script-side `RectBuild` sequence.

## Related tutorials and references

- [Author and connect a dialogue scene](37-dialogue-editor.md)
- [Use inline codes and Tellius fonts](39-inline-text-and-fonts.md)
- [Rect format](../formats/rect-format.md)
- [Dialogue engine](../systems/dialogue-engine.md)
- [Message format](../formats/message-format.md)

---

[← Previous: Author and connect a dialogue scene](37-dialogue-editor.md) · [All tutorials](index.md) · [Next: Use inline codes and Tellius fonts →](39-inline-text-and-fonts.md)
