---
id: "script-functions"
title: "Script Functions"
description: "Every function an event script can call — what it does, its arguments and what it returns"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure"]
aliases: ["tellius_archive.html#/script-functions"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/script-functions.md"
system_entries: ["FE9-SYS-041"]
---
# Script Functions

*Every function an event script can call — what it does, its arguments and what it returns*

Every `externCall` target the game's event scripts can use, with what it does in the US game. There are 406 **native** functions, built into `main.dol`, and 89 **helper** functions written in script inside `startup.cmb`, which every chapter can call; helpers are marked *startup.cmb*. <span class="confidence confidence--confirmed">confirmed</span>

!!! info "Rules shared by every function"
    **Arguments are positional** and each function always takes exactly its listed number. **Units** are numeric handles, not character IDs; 0 means no unit. **Forces**: 0 player, 1 enemy, 2 allied (orderable), 3 other (green), 4 free pool, 5 player reserve, 6 dead/inactive, 7 special. **Tiles** count from the map's border. **Durations** named *ms* are milliseconds, converted to 60 Hz frames. **Skipping**: while the player skips an event, calls that would animate or wait apply their end state at once (and usually return 0), and music and sound calls are ignored. A call that shows something the event must wait for (a conversation, a movement, a door, a movie) pauses the script by itself unless its description says it does not wait.

## Music and sound

  Four music channels (0 is the map music), the ambient-sound level and one-shot sound effects. Every millisecond duration is converted to 60 Hz frames.

  `BgmChangeEvt_MapToEvt1(bgm_id, duration_ms)` *(startup.cmb)* — Calls BGMMute(0, duration), waits the full duration with WaitM, then BGMPlay(1, bgm_id).

- `bgm_id`: Existing BGM_... track ID; not an audio filename.
- `duration_ms`: Duration in milliseconds. Use the matching completion wait when synchronizing animation.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `BgmChangeEvt_MapToEvt2(bgm_id, duration_ms)` *(startup.cmb)* — Calls BGMMute(0, duration), waits duration >> 1 with WaitM, then BGMPlay(1, bgm_id).

- `bgm_id`: Existing BGM_... track ID; not an audio filename.
- `duration_ms`: Duration in milliseconds. Use the matching completion wait when synchronizing animation.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `BgmChangeEvt_MapToEvt3(bgm_id, duration_ms)` *(startup.cmb)* — Calls BGMMute(0, duration), waits no time, then BGMPlay(1, bgm_id).

- `bgm_id`: Existing BGM_... track ID; not an audio filename.
- `duration_ms`: Duration in milliseconds. Use the matching completion wait when synchronizing animation.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `BGMCont(channel, duration_ms)` — Resumes a channel paused by BGMMute and fades it back to its remembered volume.

- `channel`: Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks.
- `duration_ms`: Fade-in time in milliseconds.
- *Returns*: 1.
- On channel 0 it also clears the 'map music stopped' mark and fades the channel's volume to 100, so the map music returns even if it was only muted.

  `BgmContEvt_EvtToMap1(fade_duration, resume_duration)` *(startup.cmb)* — Calls BGMFadeOut(1, fade_duration), waits the full fade_duration with WaitM, then BGMCont(0, resume_duration).

- `fade_duration`: Milliseconds passed to BGMFadeOut and the helper's wait.
- `resume_duration`: Transition duration passed to BGMCont.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `BgmContEvt_EvtToMap2(fade_duration, resume_duration)` *(startup.cmb)* — Calls BGMFadeOut(1, fade_duration), waits fade_duration >> 1 with WaitM, then BGMCont(0, resume_duration).

- `fade_duration`: Milliseconds passed to BGMFadeOut and the helper's wait.
- `resume_duration`: Transition duration passed to BGMCont.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `BgmContEvt_EvtToMap3(fade_duration, resume_duration)` *(startup.cmb)* — Calls BGMFadeOut(1, fade_duration), waits no time, then BGMCont(0, resume_duration).

- `fade_duration`: Milliseconds passed to BGMFadeOut and the helper's wait.
- `resume_duration`: Transition duration passed to BGMCont.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `BGMFadeIn(channel, bgm_id, duration_ms)` — Starts a track on a music channel, fading it in from silence to full volume. If any channel is already playing this same track, nothing changes.

- `channel`: Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks.
- `bgm_id`: BGM_... track name from the sound data.
- `duration_ms`: Fade-in time in milliseconds (vanilla uses 500–1500).
- *Returns*: 1; 0 only if bgm_id is not a valid string.
- While the event is being skipped or a conversation skip, no music starts. Channel 0 clears the 'map music stopped' mark.

  `BGMFadeOut(channel, duration_ms)` — Fades a playing channel to silence and stops it.

- `channel`: Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks.
- `duration_ms`: Fade time in milliseconds; 0 or less stops the track at once.
- *Returns*: 1.
- Does nothing on a silent channel, and does not restart a fade-out already running. On channel 0 it marks the map music as stopped by the event, so the map's own music does not come back until a channel-0 play or BGMCont.

  `BGMMute(channel, duration_ms)` — Fades a playing channel to silence and pauses it, remembering its volume and position so BGMCont can bring it back.

- `channel`: Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks.
- `duration_ms`: Fade time in milliseconds; 0 or less pauses at once.
- *Returns*: 1.
- Used to hold the map music while an event track plays (see BgmChangeEvt_MapToEvt1). On channel 0 it also marks the map music as stopped by the event.

  `BGMPlay(channel, bgm_id)` — Starts a track on a music channel at full volume. If any channel is already playing this same track, nothing changes. The channel's previous track is stopped.

- `channel`: Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks.
- `bgm_id`: BGM_... track name from the sound data.
- *Returns*: 1; 0 only if bgm_id is not a valid string.
- While the event is being skipped, or while a conversation is being skipped, no music starts. Starting a track on channel 0 clears the 'map music stopped by the event' mark that BGMStop/BGMFadeOut/BGMMute set.

  `BGMPlayVol(channel, bgm_id, volume)` — Starts a track on a music channel at the given volume.

- `channel`: Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks.
- `bgm_id`: BGM_... track name from the sound data.
- `volume`: Volume 0–100 (100 = full). Vanilla ambient tracks use 60–85.
- *Returns*: 1; 0 only if bgm_id is not a valid string.
- Same duplicate-track, skip and channel-0 rules as BGMPlay.

  `BGMQuietOff(channel)` — Ends the music 'quiet' state started by BGMQuietOn, restoring the level over about a quarter of a second.

- `channel`: Ignored.
- *Returns*: 1.

  `BGMQuietOn(channel)` — Starts lowering the music for a dialogue box or a reward window (the game's music 'quiet' state), over about a quarter of a second.

- `channel`: Ignored: the quiet state applies to the music as a whole.
- *Returns*: 1.
- Pair with BGMQuietOff. UnitGetItemShowingSub wraps an item reward in this pair.

  `BGMResume()` — Restores map-music channel 0 to volume 100 over 200 ms and starts a 200 ms countdown on active event-music channels 1–3.

- *Returns*: 1.
- Use when leaving an event-music sequence and returning to the map soundtrack.

  `BGMSetVol(channel, volume, duration_ms)` — Changes a channel's volume gradually.

- `channel`: Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks.
- `volume`: Target volume 0–100.
- `duration_ms`: Transition time in milliseconds; at least one frame.
- *Returns*: 1.
- Works on any channel, playing or not; it only changes the channel's volume level.

  `BGMStop(channel)` — Stops a playing channel almost immediately (a one-millisecond fade).

- `channel`: Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks.
- *Returns*: 1.
- Same channel-0 rule as BGMFadeOut. Does nothing on a silent channel.

  `ENVNoisyOff()` — Returns the ambient sound from the 'noisy' level to normal, over 15 frames (a quarter of a second).

- *Returns*: 1.
- Each ENV call cancels any ambient-level change still in progress. The ambient level is separate from the music channel volumes.

  `ENVNoisyOn()` — Raises the ambient (environment) sound to its 'noisy' level, over 15 frames (a quarter of a second).

- *Returns*: 1.
- Each ENV call cancels any ambient-level change still in progress. The ambient level is separate from the music channel volumes.

  `ENVNoisyOn_WhenNotEvtSkip()` *(startup.cmb)* — Calls ENVNoisyOn only when (GCST() & 1) is zero.

- *Returns*: 0 (implicit return); do not interpret this as failure.
- This documents the exact guard, not the complete GCST bitfield.

  `ENVQuietOff()` — Returns the ambient sound from the 'quiet' level to normal, over 15 frames (a quarter of a second).

- *Returns*: 1.
- Each ENV call cancels any ambient-level change still in progress. The ambient level is separate from the music channel volumes.

  `ENVQuietOn()` — Lowers the ambient sound to its 'quiet' level, over 15 frames (a quarter of a second).

- *Returns*: 1.
- Each ENV call cancels any ambient-level change still in progress. The ambient level is separate from the music channel volumes.

  `ENVSilentOff()` — Brings back ambient sound silenced by ENVSilentOn, over 15 frames (a quarter of a second).

- *Returns*: 1.
- Each ENV call cancels any ambient-level change still in progress. The ambient level is separate from the music channel volumes.

  `ENVSilentOff_WhenNotEvtSkip()` *(startup.cmb)* — Calls ENVSilentOff only when (GCST() & 1) is zero.

- *Returns*: 0 (implicit return); do not interpret this as failure.
- This documents the exact guard, not the complete GCST bitfield.

  `ENVSilentOn(frames)` — Silences the ambient (environment) sound.

- `frames`: Fade time in frames (60 per second): vanilla uses 15–90. 0 silences instantly; negative values count as 0.
- *Returns*: 1.
- Undo with ENVSilentOff. Cancels any ambient-level change still in progress.

  `LocalDieTalkWithBgmChange(flag_name, message_id)` *(startup.cmb)* — Disables skip. If flag_name is nonempty and set, calls DefaultDieTalk. Otherwise mutes map music, fades event music over 500 ms, waits 500 ms, plays BGM_DEAD1 and the supplied message. Surrounds that custom branch with environment silence when GetBattleType has bit 0x80000000. Re-enables skip.

- `flag_name`: Empty string forces custom dialogue; otherwise a set registered flag selects DefaultDieTalk.
- `message_id`: Message ID in a currently loaded message resource; not literal dialogue text.
- *Returns*: 0 (implicit return); do not interpret this as failure.
- It does not set the supplied flag or explicitly restore the previous BGM itself.

  `SFXPlay(sfx_id)` — Plays a sound effect once at full volume.

- `sfx_id`: SFX_... sound-effect name.
- *Returns*: 1; 0 only if sfx_id is not a valid string.
- While the event is being skipped, or while a conversation is being skipped, no sound is played.

  `SoundBossTalkEnd()` *(startup.cmb)* — Under the same battle-type bit guard, restores environment, fades channel 1 over 750 and continues channel 0 over 750.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `SoundBossTalkStart(bgm_id)` *(startup.cmb)* — Only when GetBattleType() has bit 0x80000000: silences environment with parameter 30, mutes channel 0 over 750, and plays the supplied track on channel 1.

- `bgm_id`: Existing BGM_... track ID; not an audio filename.
- *Returns*: 0 (implicit return); do not interpret this as failure.

## Screen transitions, images and captions

  Fades, wipes and flashes, full-screen images (RID_ rectangles), world-map views, location captions and highlight frames.

  `CreateNoticeFrame(x, y, width, height)` — Creates or updates an animated rectangular highlight around a screen area.

- `x`: Screen-space left edge.
- `y`: Screen-space top edge.
- `width`: Width in screen coordinates.
- `height`: Height in screen coordinates.
- *Returns*: 0.
- Remove it with DeleteNoticeFrame. Coordinates are not map tiles.

  `CreateNoticeLFrame(x, y, width_1, width_2, height_1, height_2, orientation)` — Creates or updates an animated six-edge L-shaped screen highlight.

- `x`: Left edge of the complete shape.
- `y`: Top edge of the complete shape.
- `width_1`: First horizontal segment length.
- `width_2`: Additional horizontal segment length; total width is width_1 + width_2.
- `height_1`: First vertical segment length.
- `height_2`: Additional vertical segment length; total height is height_1 + height_2.
- `orientation`: 0 cuts out the bottom-left part; nonzero cuts out the top-right part.
- *Returns*: 0.
- All six numeric dimensions are screen coordinates. The fifth and sixth arguments are lengths, not RGBA colors. Remove with DeleteNoticeFrame.

  `DeleteNoticeFrame()` — Removes the active E_NoticeFrame highlight frame.

- *Returns*: 0.

  `Fade(mode, duration_ms)` — Starts a screen transition.

- `mode`: 0 = clear screen immediately; 1 = solid black; 2 = fade in from black; 3 = fade out to black; 4 = solid white; 5 = fade in from white; 6 = fade out to white; 7 = captured-screen transition.
- `duration_ms`: Duration in milliseconds; negative uses 500 ms.
- *Returns*: 1.
- Use FadeWait before starting another transition. During event skipping, transitions go directly to their final state.

  `FadeWait()` *(startup.cmb)* — Yields repeatedly while isFading() is nonzero.

- *Returns*: 0 (implicit return); do not interpret this as failure.
- No timeout and no extra frame after the predicate becomes false.

  `Flash(red, green, blue, appear_ms, disappear_ms)` — Starts a colored screen flash.

- `red`: Red component; clamped to 0–255.
- `green`: Green component; clamped to 0–255.
- `blue`: Blue component; clamped to 0–255.
- `appear_ms`: Appearance duration; negative uses 500 ms.
- `disappear_ms`: Disappearance duration; negative uses 500 ms.
- *Returns*: 1.
- Use FlashWait to wait for the transition.

  `FlashWait()` — Suspends the script while the screen flash is transitioning.

- *Returns*: 1.

  `GetFukiPosX()` — Reads the X coordinate of the active tutorial speech-bubble display.

- *Returns*: Signed X coordinate; 0 if the display process is absent.
- Useful for positioning tutorial graphics around the active bubble; 0 is also a valid position.

  `GetFukiPosY()` — Reads the Y coordinate of the active tutorial speech-bubble display.

- *Returns*: Signed Y coordinate; 0 if the display process is absent.
- Useful for positioning tutorial graphics around the active bubble; 0 is also a valid position.

  `GMapFlagMarkOff(map_id, index)` — Turns off the selected flag marker on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `index`: Index of the flag marker in this world-map resource; not a chapter number.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapFlagMarkOffAll(map_id)` — Removes all flag markers on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapFlagMarkOn(map_id, index, x, y, style)` — Creates or resets a flag marker on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `index`: Flag-marker slot to use; reuse the same slot to replace its marker.
- `x`: X in world-map image coordinates.
- `y`: Y in world-map image coordinates.
- `style`: Marker style byte. Use an available style from the matching map scene.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapPenDarkOnOff(map_id, sequence, enabled)` — Changes the dark-display flag for one world-map pen sequence.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `sequence`: Pen sequence index in the loaded resource.
- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapPenDispOnOff(map_id, enabled)` — Shows or hides the world-map pen overlay.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapPenDraw1Seq(map_id, index)` — Starts drawing the selected pen sequence on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `index`: Index of the pen sequence in this world-map resource; not a chapter number.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapPenDrawWait(map_id)` — Suspends this script until the world-map pen drawing operation completes.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapPenReset(map_id, index)` — Resets the selected pen sequence on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `index`: Index of the pen sequence in this world-map resource; not a chapter number.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapPointOff(map_id, index)` — Starts removal of the selected point marker on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `index`: Index of the point marker in this world-map resource; not a chapter number.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapPointOffAll(map_id)` — Removes all point markers on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapPointOn(map_id, index, x, y, scale_percent, rgb)` — Creates a colored point marker on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `index`: Point-marker slot to use.
- `x`: X in world-map image coordinates.
- `y`: Y in world-map image coordinates.
- `scale_percent`: Marker scale; 100 = normal size.
- `rgb`: Packed RGB integer, for example 0xFF0000 for red. Alpha is fixed to 255.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapRegionFlashOnce(map_id, index)` — Requests a single flash of the selected region overlay on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `index`: Index of the region overlay in this world-map resource; not a chapter number.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapRegionFlashOnOff(map_id, region, enabled)` — Enables or disables the flashing flag for a world-map region.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `region`: Region index in the loaded resource.
- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapRegionOff(map_id, index)` — Turns off the selected region overlay on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `index`: Index of the region overlay in this world-map resource; not a chapter number.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapRegionOffAll(map_id)` — Turns off all region overlays on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapRegionOn(map_id, index)` — Turns on the selected region overlay on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `index`: Index of the region overlay in this world-map resource; not a chapter number.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `GMapRegionOnSkipFlash(map_id, index)` — Turns on without its initial flash the selected region overlay on a world-map image.

- `map_id`: RID_GMAP_... resource ID of a world-map image already built for this scene.
- `index`: Index of the region overlay in this world-map resource; not a chapter number.
- *Returns*: 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

  `HidePrim2D(hidden)` — Starts or ends the scene process that hides 2D primitives.

- `hidden`: Nonzero starts hiding; 0 removes the hiding process.
- *Returns*: 1.

  `isFading()` — Tests whether a screen fade started by Fade is still running.

- *Returns*: 1 while fading; 0 otherwise.
- FadeWait loops on this.

  `isFlash()` — Tests whether the screen flash is in either transition phase.

- *Returns*: 1 while transitioning; 0 otherwise.

  `isWipe()` — Tests whether a wipe-in or wipe-out transition is active.

- *Returns*: 1 while transitioning; 0 otherwise.

  `JyokyoMapCapture()` — Captures the status-map display and suspends the script while capture completes.

- *Returns*: 1.

  `JyokyoMapDelete()` — Deletes the status-map display.

- *Returns*: 1.

  `JyokyoMapEnemyOn()` — Enables enemy markers on the status map.

- *Returns*: 1.

  `JyokyoMapHide()` — Hides the status-map display.

- *Returns*: 1.

  `JyokyoMapPlayerOn()` — Enables player markers on the status map.

- *Returns*: 1.

  `JyokyoMapShow()` — Starts the status-map display.

- *Returns*: 1.

  `RectAdjustBoundary(rect_id, alignment)` — Aligns a rectangle’s source image inside the 608 × 448 layout area.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `alignment`: Numeric-keypad layout: 7/8/9 top left/center/right, 4/5/6 middle, 1/2/3 bottom. Other values leave position unchanged.
- *Returns*: 1 if the rectangle exists; 0 otherwise.
- Uses the image’s unscaled bounds; this is an alignment selector, not a pixel offset.

  `RectBuild(rect_id)` — Creates an image (rectangle) from its RID definition, attached to the current event. RID_GMAP_... names create a world-map view.

- `rect_id`: RID_... image definition name.
- *Returns*: 0.
- Remove it with RectKill or RectFadeOutDelete.

  `RectFadeIn(rect_id, frames)` — Fades in a rectangle.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `frames`: Duration in frames. Ordinary rectangles keep only the low byte: use 1–255. World-map fade-in/out uses a signed 16-bit duration, with a minimum of 1.
- *Returns*: 1 if the rectangle exists; 0 otherwise.
- Starts the animation without waiting. RectFadeOutDelete uses the ordinary-rectangle path.

  `RectFadeOut(rect_id, frames)` — Fades out a rectangle.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `frames`: Duration in frames. Ordinary rectangles keep only the low byte: use 1–255. World-map fade-in/out uses a signed 16-bit duration, with a minimum of 1.
- *Returns*: 1 if the rectangle exists; 0 otherwise.
- Starts the animation without waiting. RectFadeOutDelete uses the ordinary-rectangle path.

  `RectFadeOutDelete(rect_id, frames)` — Fades out and then deletes a rectangle.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `frames`: Duration in frames. Ordinary rectangles keep only the low byte: use 1–255. World-map fade-in/out uses a signed 16-bit duration, with a minimum of 1.
- *Returns*: 1 if the rectangle exists; 0 otherwise.
- Starts the animation without waiting. RectFadeOutDelete uses the ordinary-rectangle path.

  `RectGet(rect_id, property)` — Reads a rectangle property and truncates it to an integer.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `property`: 0 = X; 1 = Y; 2 = Z offset; 3/4 = pivot X/Y; 5 = horizontal scale; 6 = vertical scale; 7 also reads horizontal scale; 8 = rotation; 9 = opacity byte; 10 = brightness byte. Other properties depend on the rectangle type.
- *Returns*: Property value, or 0 if the rectangle is absent. Scale is the raw factor: 100% reads as 1, and 50% truncates to 0.
- RectSet takes scale percentages, while RectGet returns the raw factor. Do not round-trip percentage values through this getter.

  `RectKill(rect_id)` — Removes an image created by RectBuild or RectLeave.

- `rect_id`: RID_... name.
- *Returns*: 0.

  `RectLeave(rect_id)` — Creates a rectangle/world-map image without attaching it to the current event as its parent.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- *Returns*: 0.
- Unlike RectBuild, it passes no event parent. Explicitly remove it with RectKill when it is no longer needed; it is not a synonym for deleting the rectangle.

  `RectMove(rect_id, focus_x, focus_y, scale_percent, frames, curve)` — Animates a rectangle/world-map image so a source point is centered at (304, 240) at the requested scale.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `focus_x`: Source-image X coordinate to center.
- `focus_y`: Source-image Y coordinate to center.
- `scale_percent`: Uniform scale; 100 = normal size.
- `frames`: Duration in frames; values below 1 become 1.
- `curve`: 0 linear; 1 quadratic ease-in; 2 cubic ease-in; 3 quartic ease-in; 4 quadratic ease-out; 5 cubic ease-out; 6 quartic ease-out; 7–9 oscillating/bouncing curves; 10 cosine ease-in/out; 11 sine ease-out; 12 cosine ease-in.
- *Returns*: 1 if the target exists; 0 otherwise.
- Final position is (304 − focus_x × scale/100, 240 − focus_y × scale/100). This starts animation; it does not wait.

  `RectMoveOffset(rect_id, x, y, frames, curve)` — Animates a rectangle/world-map image to an explicit offset and restores its scale to 100%.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `x`: Final layout-space X offset.
- `y`: Final layout-space Y offset.
- `frames`: Duration in frames; values below 1 become 1.
- `curve`: 0 linear; 1 quadratic ease-in; 2 cubic ease-in; 3 quartic ease-in; 4 quadratic ease-out; 5 cubic ease-out; 6 quartic ease-out; 7–9 oscillating/bouncing curves; 10 cosine ease-in/out; 11 sine ease-out; 12 cosine ease-in.
- *Returns*: 1 if the target exists; 0 otherwise.

  `RectPreLoad(rect_id)` — Starts loading the image files of a RID definition, so a later RectBuild shows it without delay.

- `rect_id`: RID_... image definition name.
- *Returns*: No meaningful value; call it for its effect.
- Wait with PreLoadWait if the images must be ready.

  `RectSet(rect_id, property, value)` — Sets a rectangle property immediately.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `property`: 0 = X; 1 = Y; 2 = Z offset; 3/4 = pivot X/Y, the origin of scale and rotation (default half the first image’s size); 5 = horizontal scale; 6 = vertical scale; 7 = both scales; 8 = rotation in degrees; 9 = fade/opacity byte; 10 = brightness byte (128 = normal). Keep other selectors from the matching resource’s existing sequence.
- `value`: Position in layout coordinates; scale in percent (100 = normal size); opacity 0–255. Byte properties wrap rather than clamp.
- *Returns*: 1 if the rectangle exists; 0 otherwise.

  `RectSetCurve(rect_id, property, curve, start, end, frames)` — Animates one rectangle property between two values.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `property`: Same selector as RectSet.
- `curve`: 0 linear; 1 quadratic ease-in; 2 cubic ease-in; 3 quartic ease-in; 4 quadratic ease-out; 5 cubic ease-out; 6 quartic ease-out; 7–9 oscillating/bouncing curves; 10 cosine ease-in/out; 11 sine ease-out; 12 cosine ease-in.
- `start`: Starting value; 123456789 means use the current value. Scale properties use percentages.
- `end`: Final value in the same units as start.
- `frames`: Duration in frames, not milliseconds. Use a positive count.
- *Returns*: 1 if the rectangle exists; 0 otherwise.
- Equal endpoints set immediately. Event skipping applies the final value immediately. This starts animation without waiting for it.

  `RectSetPos(rect_id, x, y)` — Sets a rectangle or world-map image’s position immediately.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `x`: Layout-space X coordinate, not map tile X.
- `y`: Layout-space Y coordinate.
- *Returns*: 1 if the rectangle/map exists; 0 otherwise.

  `RemoveBackdrop()` — Removes the backdrop process.

- *Returns*: 1.

  `SetSepia(enabled)` — Changes the sepia scene effect setting.

- `enabled`: Use 1 to start the sepia effect; 0 to remove it. Other values also take the removal branch.
- *Returns*: 1.

  `SetWhiteBackdrop()` — Starts the solid-white backdrop process.

- *Returns*: 1.

  `TimeiShow(x, y, message_id, appear_ms, hold_ms, disappear_ms)` — Shows a timed location-name caption.

- `x`: Screen-space caption X coordinate.
- `y`: Screen-space caption Y coordinate.
- `message_id`: Message ID in a loaded message resource.
- `appear_ms`: Appearance duration in milliseconds.
- `hold_ms`: Time fully displayed, in milliseconds.
- `disappear_ms`: Disappearance duration in milliseconds.
- *Returns*: 1 when accepted; 0 for an invalid message argument.
- Timing is converted to 60 Hz frames. This schedules the caption without waiting through its whole lifetime.

  `TimeiShowGMap(x, y, extra_width, message_id, appear_ms, hold_ms, disappear_ms)` — Shows a timed location caption using the world-map caption style.

- `x`: Screen-space caption X coordinate.
- `y`: Screen-space caption Y coordinate.
- `extra_width`: Additional width added to the caption’s text-sized background, in screen coordinates. Use 0 for the normal width.
- `message_id`: Message ID in a loaded message resource.
- `appear_ms`: Appearance duration in milliseconds.
- `hold_ms`: Time fully displayed, in milliseconds.
- `disappear_ms`: Disappearance duration in milliseconds.
- *Returns*: 1 when accepted; 0 for invalid message.
- The caption is positioned in screen coordinates; this call does not take a map ID.

  `TimeiShowHold(caption_id, x, y, message_id, appear_ms)` — Shows a location-name caption that stays visible until explicitly released.

- `caption_id`: Byte slot ID for later TimeiShowHoldOff; avoid 255, which is used as the all-captions selector.
- `x`: Screen-space caption X coordinate.
- `y`: Screen-space caption Y coordinate.
- `message_id`: Message ID in a loaded message resource.
- `appear_ms`: Appearance duration in milliseconds.
- *Returns*: 1 when accepted; 0 for invalid message.

  `TimeiShowHoldGMap(caption_id, x, y, extra_width, message_id, appear_ms)` — Shows a held location caption using the world-map caption style.

- `caption_id`: Byte ID used by TimeiShowHoldOff; avoid 255.
- `x`: Screen-space caption X coordinate.
- `y`: Screen-space caption Y coordinate.
- `extra_width`: Additional width added to the caption’s text-sized background, in screen coordinates. Use 0 for the normal width.
- `message_id`: Message ID in a loaded message resource.
- `appear_ms`: Appearance duration in milliseconds.
- *Returns*: 1 when accepted; 0 for invalid message.

  `TimeiShowHoldOff(caption_id, disappear_ms)` — Starts disappearance of the held caption with this ID.

- `caption_id`: ID passed to TimeiShowHold or TimeiShowHoldGMap.
- `disappear_ms`: Disappearance duration in milliseconds.
- *Returns*: 1.

  `TimeiShowHoldOffAll(disappear_ms)` — Starts disappearance of every held caption.

- `disappear_ms`: Disappearance duration in milliseconds.
- *Returns*: 1.

  `Tut3SArrowABAnim(rect_id, period_ms, amplitude)` — Continuously oscillates a tutorial arrow rectangle along its positive diagonal axis.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `period_ms`: Positive oscillation period in milliseconds. Zero causes division by zero; do not pass 0.
- `amplitude`: Movement amplitude in screen coordinates; use a small positive value such as 4 or 6.
- *Returns*: No useful script result; call for its side effect.
- The rectangle must exist first. The animation is attached to it and restores the original position when cleaned up; remove the rectangle to end the display.

  `Tut3SArrowBCAnim(rect_id, period_ms, amplitude)` — Continuously oscillates a tutorial arrow rectangle along its horizontal axis.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `period_ms`: Positive oscillation period in milliseconds. Zero causes division by zero; do not pass 0.
- `amplitude`: Movement amplitude in screen coordinates; use a small positive value such as 4 or 6.
- *Returns*: No useful script result; call for its side effect.
- The rectangle must exist first. The animation is attached to it and restores the original position when cleaned up; remove the rectangle to end the display.

  `Tut3SArrowCAAnim(rect_id, period_ms, amplitude)` — Continuously oscillates a tutorial arrow rectangle along its negative diagonal axis.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `period_ms`: Positive oscillation period in milliseconds. Zero causes division by zero; do not pass 0.
- `amplitude`: Movement amplitude in screen coordinates; use a small positive value such as 4 or 6.
- *Returns*: No useful script result; call for its side effect.
- The rectangle must exist first. The animation is attached to it and restores the original position when cleaned up; remove the rectangle to end the display.

  `Tut3SArrowDAnim(rect_id, period_ms, amplitude)` — Continuously oscillates a tutorial arrow rectangle along its downward vertical axis.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `period_ms`: Positive oscillation period in milliseconds. Zero causes division by zero; do not pass 0.
- `amplitude`: Movement amplitude in screen coordinates; use a small positive value such as 4 or 6.
- *Returns*: No useful script result; call for its side effect.
- The rectangle must exist first. The animation is attached to it and restores the original position when cleaned up; remove the rectangle to end the display.

  `Tut3SArrowUAnim(rect_id, period_ms, amplitude)` — Continuously oscillates a tutorial arrow rectangle along its upward vertical axis.

- `rect_id`: RID_... identifier of an existing rectangle/UI resource.
- `period_ms`: Positive oscillation period in milliseconds. Zero causes division by zero; do not pass 0.
- `amplitude`: Movement amplitude in screen coordinates; use a small positive value such as 4 or 6.
- *Returns*: No useful script result; call for its side effect.
- The rectangle must exist first. The animation is attached to it and restores the original position when cleaned up; remove the rectangle to end the display.

  `Tutorial_FadeIn()` *(startup.cmb)* — Disables skip, builds RID_MASK, sets property 9 to 0 and property 2 to -835, then RectSetCurve("RID_MASK",9,0,0,128,100).

- *Returns*: 0 (implicit return); do not interpret this as failure.
- The exact rectangle property/curve enum meanings are not all established. Preserve the sequence.

  `Tutorial_FadeOut()` *(startup.cmb)* — Calls RectSetCurve("RID_MASK",9,0,160,0,100), kills RID_MASK, then enables skip.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutShow(text_resource)` — Starts a tutorial text display.

- `text_resource`: Text resource expected by the existing tutorial display sequence.
- *Returns*: 1.

  `TutShowKari(x, y, message_id, fade_ms, hold_ms)` — Shows a temporary tutorial caption with matching appearance and disappearance durations.

- `x`: Screen-space caption X coordinate.
- `y`: Screen-space caption Y coordinate.
- `message_id`: Message ID in a loaded message resource.
- `fade_ms`: Duration of each fade, in milliseconds.
- `hold_ms`: Fully visible time in milliseconds.
- *Returns*: 1 when accepted; 0 for invalid message.

  `WipeEnd()` — Resets the screen-wipe state to idle.

- *Returns*: 1.

  `WipeIn(duration_ms)` — Starts a screen wipe in.

- `duration_ms`: Duration in milliseconds; a negative value uses 2000 ms.
- *Returns*: 1.
- Use WipeWait before work that requires the transition to finish.

  `WipeOut(duration_ms)` — Starts a screen wipe out.

- `duration_ms`: Duration in milliseconds; a negative value uses 2000 ms.
- *Returns*: 1.
- Use WipeWait before work that requires the transition to finish.

  `WipeWait()` — Suspends the script while a wipe-in or wipe-out transition is active.

- *Returns*: 1.

## Camera

  The map camera keeps a point it looks at plus a yaw, a pitch (both in degrees) and a distance in tiles. The event camera plays a path of keyframes.

  `CopyMapCamera()` — Saves the map camera's angles and distance so PastMapCamera can return to them.

- *Returns*: 1.
- Saves angles and distance only, not the point looked at. One saved state; a new copy replaces it.

  `CreateEventCamera()` — Creates an empty event-camera path. Fill it with SetEventCameraAt and SetEventCameraRot keyframes, then play it with StartEventCamera.

- *Returns*: 1.
- Holds up to 256 keyframes. Remove it with DeleteEventCamera when the scene ends.

  `DeleteEventCamera()` — Removes the event camera and gives control back to the normal map camera.

- *Returns*: 1.

  `EventArrowFocus(arrow_id, enabled)` — Changes the arrow’s focus-following flag.

- `arrow_id`: Arrow slot index. Use a slot supported by the existing scene; this index is not bounds-checked.
- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1.

  `EventCameraWait()` — Waits until the event-camera path has finished playing.

- *Returns*: 1.
- Returns at once if no path is playing.

  `Focus(x, y)` — Moves the map camera smoothly so it looks at the centre of a tile.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 0.
- Does not wait: follow with FocusWait. While the event is being skipped the camera jumps there at once.

  `FocusBetweenAB(pid_a, pid_b, offset_x, offset_y, instant)` *(startup.cmb)* — Requires both PIDs to be deployed, copies the current map camera, computes their tile midpoint using a right shift by 1, adds offsets and calls Focus or InstantFocus.

- `pid_a`: First deployed actor PID.
- `pid_b`: Second deployed actor PID.
- `offset_x`: Tiles added to the midpoint X.
- `offset_y`: Tiles added to the midpoint Y.
- `instant`: Nonzero uses InstantFocus; zero uses Focus.
- *Returns*: 0 if either actor is unavailable; 1 after scheduling focus.
- Does not restore the copied camera or wait for focus itself.

  `FocusHardWait()` — Like FocusWait, but waits until the camera is within 0.1 tile of its target point and 1 unit of its target angles and distance.

- *Returns*: 1 if it had to wait; 0 if the camera was already there, or during an event skip.

  `FocusWait()` — Waits until the map camera has nearly reached its target.

- *Returns*: 1 if it had to wait; 0 if the camera was already there, or during an event skip (the camera jumps to its target).
- 'Nearly': within 1 tile of the target point and 10 units of the target angles and distance. FocusHardWait waits for a closer match.

  `InstantFocus(x, y)` — Points the map camera at the centre of a tile at once.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 0.

  `InstantPastMapCamera()` — Restores the angles and distance saved by CopyMapCamera at once.

- *Returns*: 1.
- Does nothing if nothing was saved.

  `InstantSetMapCamera(yaw, pitch, distance)` — Sets the map camera's angles and distance at once.

- `yaw`: Horizontal camera angle in degrees.
- `pitch`: Vertical camera angle in degrees (vanilla uses 40–63).
- `distance`: Distance from the looked-at point, in tiles (vanilla uses 10–45).
- *Returns*: 1.

  `InstantUnitFocusByPID(pid)` *(startup.cmb)* — Resolves a deployed actor, reads its tile, then calls InstantFocus.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: 0 if unavailable; 1 after focus call.
- Does not copy/restore the previous map camera itself.

  `InstantUnitFocusOffsetByPID(pid, offset_x, offset_y)` *(startup.cmb)* — Resolves a deployed actor, reads its tile and adds X/Y offsets, then calls InstantFocus.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `offset_x`: Tiles added to actor X.
- `offset_y`: Tiles added to actor Y.
- *Returns*: 0 if unavailable; 1 after focus call.
- Does not copy/restore the previous map camera itself.

  `PastMapCamera()` — Turns the camera smoothly back to the angles and distance saved by CopyMapCamera.

- *Returns*: 1.
- Does nothing if nothing was saved. While the event is being skipped it jumps there at once.

  `SetEventCameraAt(time_ms, x, y, height)` — Adds a keyframe for the point the event camera looks at.

- `time_ms`: Time of the keyframe from the start of the path, in milliseconds.
- `x`: X in tiles divided by the SetEventCameraPrec divisor; the camera looks at the tile centre (0.5 is added).
- `y`: Y in tiles, same rule as x.
- `height`: Height divided by the same divisor (no 0.5 added).
- *Returns*: 1.

  `SetEventCameraPrec(precision)` — Sets the divisor applied to later SetEventCameraAt coordinates, allowing positions finer than a tile.

- `precision`: Divisor: 1 means coordinates are tiles; 10 means tenths of a tile; 100 hundredths. Vanilla uses 1, 10 and 100.
- *Returns*: 1.
- The setting stays until changed. The default is 1.

  `SetEventCameraRot(time_ms, yaw, pitch, distance)` — Adds a keyframe for the event camera's angles and distance.

- `time_ms`: Time of the keyframe from the start of the path, in milliseconds.
- `yaw`: Horizontal camera angle in degrees.
- `pitch`: Vertical camera angle in degrees (vanilla uses 40–63).
- `distance`: Distance from the looked-at point, in tiles (vanilla uses 10–45).
- *Returns*: 1.
- Not affected by SetEventCameraPrec.

  `SetMapCamera(yaw, pitch, distance)` — Turns the map camera smoothly to new angles and distance; the point it looks at does not change.

- `yaw`: Horizontal camera angle in degrees.
- `pitch`: Vertical camera angle in degrees (vanilla uses 40–63).
- `distance`: Distance from the looked-at point, in tiles (vanilla uses 10–45).
- *Returns*: 1.

  `SetOnBtFocus(enabled)` — Enables or disables automatic battle-focus behavior.

- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1.

  `StartEventCamera(easing)` — Plays the event-camera path. Keyframes are joined with a smooth curve; if the path has no keyframe at time 0, the camera's current state is added as the first one.

- `easing`: How time advances along the path: 0 even speed, 1 starts slowly, 2 ends slowly, 3 starts and ends slowly.
- *Returns*: 1.
- Does not wait: use EventCameraWait. During an event skip the path ends at once.

  `UnitFocus(unit)` — Moves the map camera smoothly towards a unit's tile.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: 1, even for an invalid unit (which leaves the camera alone).
- Does not wait: follow with FocusWait.

  `UnitFocusByPID(pid)` *(startup.cmb)* — Resolves a deployed actor, reads its tile, then calls Focus.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: 0 if unavailable; 1 after focus call.
- Does not copy/restore the previous map camera itself.

  `UnitFocusOff()` — Stops the camera from following units during later scripted movement.

- *Returns*: 1.

  `UnitFocusOffsetByPID(pid, offset_x, offset_y)` *(startup.cmb)* — Resolves a deployed actor, reads its tile and adds X/Y offsets, then calls Focus.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `offset_x`: Tiles added to actor X.
- `offset_y`: Tiles added to actor Y.
- *Returns*: 0 if unavailable; 1 after focus call.
- Does not copy/restore the previous map camera itself.

  `UnitFocusOn()` — Makes the camera follow units during later scripted movement (the default).

- *Returns*: 1.

## Conversations, dialogs and movies

  Message windows, choice dialogs, cutscene movies and the ending screens.

  `BeginFinale()` — Enables finale mode and its input mask for A/B/X/Y/Z/L/R/Start.

- *Returns*: 1.
- Pair BeginFinale and EndFinale around ending sequences; neither call starts the credits by itself.

  `ChapterMoviePlay(chapter)` — Plays the movie of a chapter and pauses the script until it ends.

- `chapter`: Chapter number whose movie is played. It does not change the current chapter.
- *Returns*: 1; 0 during an event skip (nothing is played).

  `Check()` — Tests whether a base-conversation event is being evaluated for availability rather than being played.

- *Returns*: 1 during the availability check; 0 while playing the conversation.
- In an availability check, return the condition and avoid dialogue, rewards, or other lasting changes. Use inside a base-conversation event.

  `DefaultDieTalk()` — Looks up and starts the defeated unit’s default death message when that message exists. For player or inactive units it also selects death music.

- *Returns*: 1 when a matching message exists; 0 otherwise.
- Requires a current defeated-unit context. It can reuse an existing talk process.

  `DefaultEscapeTalk()` — Looks up and starts the current acting unit’s default escape message when available.

- *Returns*: 0, including when a message was started.
- Requires a current acting-unit context. Follow the usual talk completion sequence.

  `Dialog(message_id)` — Opens a message dialog and suspends this script until the dialog process releases it.

- `message_id`: Message ID in a loaded message resource.
- *Returns*: 0; this is not a failure indication.
- Read DialogResult afterwards if the message presents a choice. DialogDirect uses the same opening behavior as Dialog in this build.

  `Dialog2Items(choice_1, choice_2)` — Opens a choice dialog with 2 entries and suspends the calling script.

- `choice_1`: Message ID for choice 1, in display order.
- `choice_2`: Message ID for choice 2, in display order.
- *Returns*: 1 when accepted; 0 for an invalid message argument.
- Read DialogResult after the dialog closes; the opening call does not return the choice.

  `Dialog3Items(choice_1, choice_2, choice_3)` — Opens a choice dialog with 3 entries and suspends the calling script.

- `choice_1`: Message ID for choice 1, in display order.
- `choice_2`: Message ID for choice 2, in display order.
- `choice_3`: Message ID for choice 3, in display order.
- *Returns*: 1 when accepted; 0 for an invalid message argument.
- Read DialogResult after the dialog closes; the opening call does not return the choice.

  `Dialog4Items(choice_1, choice_2, choice_3, choice_4)` — Opens a choice dialog with 4 entries and suspends the calling script.

- `choice_1`: Message ID for choice 1, in display order.
- `choice_2`: Message ID for choice 2, in display order.
- `choice_3`: Message ID for choice 3, in display order.
- `choice_4`: Message ID for choice 4, in display order.
- *Returns*: 1 when accepted; 0 for an invalid message argument.
- Read DialogResult after the dialog closes; the opening call does not return the choice.

  `DialogDirect(message_id)` — Opens a message dialog and suspends this script until the dialog process releases it.

- `message_id`: Message ID in a loaded message resource.
- *Returns*: 0; this is not a failure indication.
- Read DialogResult afterwards if the message presents a choice. DialogDirect uses the same opening behavior as Dialog in this build.

  `DialogGetRes()` — Reads the last dialog result.

- *Returns*: Signed result byte: -1 before a result is selected; otherwise the dialog’s selected entry value.
- Read only after the dialog completes. Do not treat -1 as “yes” because it is nonzero; retain the choice mapping of the dialog you use.

  `DialogResult()` — Reads the last dialog result.

- *Returns*: Signed result byte: -1 before a result is selected; otherwise the dialog’s selected entry value.
- Read only after the dialog completes. Do not treat -1 as “yes” because it is nonzero; retain the choice mapping of the dialog you use.

  `DialogSetDefault(selection)` — Sets the default selection byte used by dialogs.

- `selection`: Default choice value for the dialog being opened; only the low byte is retained.
- *Returns*: No useful script result; call for its side effect.
- Set before opening the dialog. Use the same entry numbering as that dialog.

  `DialogTutorial(message_id)` — Opens a tutorial dialog and suspends this script until the dialog process releases it.

- `message_id`: Message ID in a loaded message resource.
- *Returns*: 0; this is not a failure indication.
- Read DialogResult afterwards if the message presents a choice. DialogDirect uses the same opening behavior as Dialog in this build.

  `EndFinale()` — Disables finale mode and its input mask for A/B/X/Y/Z/L/R/Start.

- *Returns*: 1.
- Pair BeginFinale and EndFinale around ending sequences; neither call starts the credits by itself.

  `IndividualWarRecord(duration_ms)` — Starts the individual war-record display and suspends the calling script.

- `duration_ms`: Duration in milliseconds. Conversion to 60 Hz frames truncates fractional frames.
- *Returns*: 1.
- Intended for ending sequences with the corresponding display resources loaded.

  `MoviePlay(path)` — Plays a movie file and pauses the script until it ends.

- `path`: Path of a THP file on the disc, such as "movie/s01.thp".
- *Returns*: 1; 0 during an event skip (nothing is played) or for an invalid string.
- A missing file plays the placeholder movie/dummy.thp. The sound channels are faded out.

  `StaffRoll(duration_ms)` — Starts the staff credits and suspends the calling script.

- `duration_ms`: Duration in milliseconds. Conversion to 60 Hz frames truncates fractional frames.
- *Returns*: 1.
- Intended for ending sequences with the corresponding display resources loaded.

  `TalkEvent(message_id)` — Opens the conversation window with a message and pauses the script until the conversation ends or reaches a $H hold point.

- `message_id`: Message ID in a loaded message file, not literal text.
- *Returns*: 1.
- If a conversation window is already open, the new message plays in it. After a $H hold, continue with TalkResume. During a skip the text is processed at once without being shown.

  `TalkEventDirect(message_id)` — Starts the supplied event message, or passes it to the existing conversation process.

- `message_id`: Message ID in a loaded message resource.
- *Returns*: 1.
- Does not itself wait until every line has finished; use the normal TalkExist/TalkResume flow.

  `TalkExist()` — Tests whether a conversation is still running.

- *Returns*: 1 while a conversation window is open and not finished; 0 otherwise.

  `TalkResume()` — Continues a conversation stopped at a $H hold point and pauses the script again until it ends or reaches the next hold.

- *Returns*: 1.
- Only call it while a conversation is held.

  `WaitPressAnyKey()` — Suspends the calling script until the input-wait process completes after a key press.

- *Returns*: 1.

  `WarRecord(duration_ms)` — Starts the war-record display and suspends the calling script.

- `duration_ms`: Duration in milliseconds. Conversion to 60 Hz frames truncates fractional frames.
- *Returns*: 1.
- Intended for ending sequences with the corresponding display resources loaded.

## Units

  A unit is addressed by a small numeric handle (from UnitGetByPID and similar lookups); 0 means no unit. The *ByPID helpers of startup.cmb look the unit up first.

  `CheckAttackable(unit)` — Tests whether this unit can reach a position from which its equipped weapon can attack an eligible enemy.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- *Returns*: 1 if an attack opportunity exists; 0 otherwise, including missing unit, no weapon, or disqualifying status.
- Includes movement and weapon range; this is not a test of a particular target.

  `EnemyDeadCheck()` — Tests whether the enemy force is empty.

- *Returns*: 1 if no unit is left in force 1; 0 otherwise.

  `EnemyMonkCheck()` — Counts enemy-force actors with class JID_PRIEST, JID_BISHOP, or JID_BISHOP_F.

- *Returns*: Number of matching enemies.

  `EnemySelfDefenceCheck()` — Counts enemy-force actors with PID PID_12_SELFDEFENCE.

- *Returns*: Number of matching enemies.

  `EnemyTigerCheck()` — Counts enemy-force actors with class JID_TIGER.

- *Returns*: Number of matching enemies.

  `EnemyUnitCheckByPID(pid)` — Counts actors with the specified PID in the enemy force.

- `pid`: Exact PID_... character ID string.
- *Returns*: Count, not a boolean.

  `GetDiedPlayerCount()` — Counts actors in force 6 whose death-record flag is set.

- *Returns*: Number of matching actors; can exceed 1.

  `InstantUnitTransform(unit, transformed)` — Changes a unit to the requested transformed/untransformed state immediately and refreshes its display.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `transformed`: 0 requests untransformed; nonzero requests transformed. This is a desired state, not a toggle.
- *Returns*: 1 if the state changes; 0 for invalid unit or already matching state.
- Use only on a compatible laguz unit.

  `MindGetMe()` — Returns the unit performing the current action (the unit that visited, talked, opened a chest, etc.).

- *Returns*: Unit handle; 0 if there is none.
- Only meaningful in events started by a unit action.

  `MindGetMind()` — Reads the current map-action ID.

- *Returns*: Action ID byte.
- Requires the event’s map-action context; this does not identify the acting unit.

  `MindGetTarget()` — Returns the target of the current action (the unit talked to or fought).

- *Returns*: Unit handle; 0 if there is none.
- Only meaningful in talk and battle events.

  `PersonGetYellLevel(pid1, pid2)` — Returns the support rank between two characters.

- `pid1`: First character's PID.
- `pid2`: Second character's PID.
- *Returns*: 0 none, 1 C, 2 B, 3 A; -1 if either character has no unit or they are not listed as support partners of each other.

  `PersonSetYellLevel(pid1, pid2, stage)` — Sets two support partners' support points to the threshold of a rank.

- `pid1`: First character's PID.
- `pid2`: Second character's PID.
- `stage`: 0 = C threshold (C conversation becomes available); 1 = B threshold; 2 = A threshold; 3 = A threshold + 1 (A conversation done).
- *Returns*: The support points written; -1 if either character has no unit or they are not partners.
- Writes the same value on both characters. The thresholds come from the first character's support list. Other stage values leave the points unchanged.

  `PIDisAlive(pid)` — Looks up a character’s current actor and checks that its dead flag is clear.

- `pid`: Exact PID_... character ID string.
- *Returns*: 0 if no actor exists or it is dead; 1 otherwise.
- An unused character definition alone is not a living actor.

  `PlayerDeadCheck()` — Tests whether the inactive force list is empty.

- *Returns*: 1 if force 6 is empty; 0 otherwise.
- This does not mean “a player died.” Use GetDiedPlayerCount for the death-flagged count.

  `PlayerEscapeCheck()` — Tests whether every existing actor in player force 0 or reserve force 5 has the escaped flag.

- *Returns*: 1 if all match, including when there are no matching actors; 0 if any has not escaped.

  `PlayerEscapeCount()` — Counts escaped actors in player force 0 and reserve force 5.

- *Returns*: Number of escaped actors.

  `UnitAnim(unit, animation)` — Loads and plays a unit animation with the default blend length of 16, replacing an existing scripted animation for that unit.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `animation`: Animation selector supported by this unit’s model/animation set. Use a selector from a matching unit; different models need not support the same animations.
- *Returns*: 1 when scheduled; 0 for an invalid unit or during skipping. The skip path still applies the animation immediately.
- Use UnitMoveWait to synchronize with the scene’s motion/animation processes.

  `UnitAnimByPID(pid, animation)` *(startup.cmb)* — Resolves a deployed actor and calls UnitAnim. Missing actor exits without animation.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `animation`: Native animation selector.
- *Returns*: 0 even when the call succeeds; native result is discarded.

  `UnitAnimF(unit, animation, blend_duration)` — Loads and plays a unit animation with a chosen transition length, replacing an existing scripted animation for that unit.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `animation`: Animation selector supported by this unit’s model/animation set. Use a selector from a matching unit; different models need not support the same animations.
- `blend_duration`: Animation transition/blending length; UnitAnim uses 16. Zero requests an immediate switch once loaded; negative applies the animation immediately without the normal loading/wait process. This is not the length of the entire animation.
- *Returns*: 1 when scheduled; 0 for invalid unit, event skipping, or a negative blend duration. The latter two cases still apply the animation immediately.
- The engine can increase the blend length for some current-animation categories, and can fall back to an immediate switch when too many animation layers exist.

  `UnitAnimFByPID(pid, animation, blend_duration)` *(startup.cmb)* — Resolves a deployed actor and calls UnitAnimF. Missing actor exits without animation.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `animation`: Native animation selector.
- `blend_duration`: Animation transition/blending length; UnitAnim uses 16. Zero requests an immediate switch once loaded; negative applies the animation immediately without the normal loading/wait process. This is not the length of the entire animation.
- *Returns*: 0 even when the call succeeds; native result is discarded.

  `UnitBreakup(unit)` — Separates a carrying pair: the carried unit is put back on the map on the carrier's tile. Either unit of the pair can be given.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: 1 for a valid unit; 0 otherwise.
- Both units are marked as not having acted. Only call it on a unit that is carrying or carried (status 0x2 or 0x4), as UnitCheckLinked_Breakup does.

  `UnitCheckDeadHere(unit)` *(startup.cmb)* — Returns true exactly when the non-null unit's status has bit 0x8000 set.

- `unit`: Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check.
- *Returns*: 0 for null/bit clear; 1 for bit set.

  `UnitCheckDeadHereByPID(pid)` *(startup.cmb)* — Looks up the PID and calls UnitCheckDeadHere; a missing actor returns 0.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: 0 or 1.

  `UnitCheckExists(unit)` *(startup.cmb)* — Checks non-null actor membership in force 0, 1, 2 or 3. It reads status but does not use that value in the decision.

- `unit`: Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check.
- *Returns*: 1 for one of those active forces; 0 otherwise.

  `UnitCheckExistsByPID(pid)` *(startup.cmb)* — Looks up the actor and forwards to UnitCheckExists.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: 0 or 1; not an actor reference.

  `UnitCheckExistsByPID2(pid)` *(startup.cmb)* — Looks up the actor and checks UnitCheckExists.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: The actor reference if deployed in force 0–3; 0 otherwise. Unlike UnitCheckExistsByPID, success is not normalized to 1.

  `UnitCheckLinked_Breakup(unit)` *(startup.cmb)* — Returns early for null; otherwise calls UnitBreakup only if status & 0x06 is nonzero.

- `unit`: Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check.
- *Returns*: 0 for null; 1 otherwise, including when no breakup was needed.

  `UnitCheckLinked_BreakupByPID(pid)` *(startup.cmb)* — Resolves a deployed actor and forwards to UnitCheckLinked_Breakup.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: 0 if unavailable; otherwise the linked-check helper result.

  `UnitCheckLiveByPID(pid)` *(startup.cmb)* — Looks up the PID, then returns false for a null actor, status bit 0x08, or force 6; true otherwise. This is not a deployed-on-map test.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: 0 or 1.

  `UnitClassChange(unit)` — Plays the class-change (promotion) scene for a unit and promotes it, and waits for it.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: 1; 0 for an invalid unit or a unit without the SID_EVENTCC skill.
- Only works on units that have SID_EVENTCC. The new class is the class's promotion class.

  `UnitClrStatus(unit, mask)` — Clears state flags on a unit.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `mask`: Bits to clear; see UnitGetStatus.
- *Returns*: The unit's new flag word; 0 for an invalid unit.

  `UnitDead(unit)` — Plays the death fade-out of a unit's map model (with its sound) and waits for it.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: 1; 0 for an invalid unit or during an event skip (nothing is played).
- Visual only: the unit is hidden but stays in its force. Remove it with UnitEscape or UnitTransferToForce if needed.

  `UnitEscape(unit, unused)` — Takes a unit off the map: a carried unit is dropped first; a player unit goes to the reserve marked as escaped; a unit of any other force is deleted.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `unused`: Ignored; the shared helper passes 0.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- The map is refreshed afterwards.

  `UnitEscapeByPID(pid)` *(startup.cmb)* — Requires a deployed actor, then calls UnitEscape(actor, 0).

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: 0 if unavailable; 1 after the call.

  `UnitFadeIn()` — Makes later scripted movement fade units in (they appear as they move).

- *Returns*: 1.
- A scene setting used by Dispos and UnitMove* calls; turn it off with UnitFadeOff.

  `UnitFadeOff()` — Ends UnitFadeIn/UnitFadeOut: later movement shows units normally.

- *Returns*: 1.

  `UnitFadeOut()` — Makes later scripted movement fade units out (they disappear as they move).

- *Returns*: 1.
- Turn it off with UnitFadeOff.

  `UnitGet(unit, field)` — Reads a selected property of a runtime unit.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `field`: 1 = next unit handle in force list; 2 = previous handle; 4 = carried/linked unit handle; 5 = force; 6 = level; 7 = experience; 8 = transform gauge (adds 100 while transformed); 9/10 = tile X/Y; 11 = biorhythm phase × 100; 12/13 = maximum/current HP; 14–20 = strength, magic, skill, speed, luck, defense, resistance; 21 = build; 22 = movement; 23 = terrain avoid bonus; 24 = biorhythm battle counter; 35 = AI behavior type; 36/37 = character/class index; 38 = group id (army-name index into GroupData); 39–46 = HP/strength/magic/skill/speed/luck/defense/resistance caps.
- *Returns*: Selected value; 0 for an invalid unit or unsupported selector.
- Use the listed selectors. Some additional engine selectors are not suitable for general authoring yet. Coordinates and stats can be signed; missing linked-unit handles are 0.

  `UnitGetByPID(pid)` — Finds the current runtime actor for a character ID.

- `pid`: Exact PID_... character ID string.
- *Returns*: Numeric unit handle, or 0 if absent.
- A character can exist in the data without a current actor. Check the result before passing it to other calls.

  `UnitGetByPos(x, y)` — Finds an eligible visible actor occupying a map tile.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- *Returns*: Numeric unit handle, or 0 if none is found.
- Filters force membership and actor state; this is not a scan of every allocated actor.

  `UnitGetForce(unit)` — Returns a unit's force.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: Force ID 0–7; 0 for an invalid unit (indistinguishable from force 0).

  `UnitGetHP(unit)` — Returns a unit's current HP.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: Current HP; 0 for handle 0.

  `UnitGetMaxHP(unit)` — Returns a unit's maximum HP, including the bonus of the equipped weapon and item, capped by the class.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: Maximum HP; 0 for handle 0.

  `UnitGetMoveCost(unit, terrain_index)` — Reads this unit’s movement cost for a terrain-table entry.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `terrain_index`: Index in the movement-cost table for the unit’s class; not a map X or Y coordinate.
- *Returns*: Movement cost; -1 when the terrain cost exceeds 30000 (impassable); 0 for invalid unit.
- No terrain-index bounds check; use a valid terrain entry.

  `UnitGetNext(unit)` — Returns the next unit in the same force.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: Unit handle; 0 at the end of the force or for a null unit.
- Moving units between forces while walking a force changes the order.

  `UnitGetRace(unit)` — Reports the unit’s beorc/laguz transformation category.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- *Returns*: 0 for beorc or an invalid unit; 1 for untransformed laguz; 2 for transformed laguz.

  `UnitGetStatus(unit)` — Returns a unit's state flags.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: Bit flags: 0x1 has acted this turn; 0x2 carrying a unit; 0x4 carried; 0x8 dead/inactive; 0x10 in the reserve; 0x20 off screen; 0x40 hidden by fog; 0x80 under a roof; 0x100 group commander; 0x4000 escaped; 0x8000 died this chapter; 0x10000 mandatory in preparations; 0x20000 position locked in preparations; 0x100000 cannot Give or Drop a carried unit; 0x200000 cannot be picked for the second team; 0x400000 picked for the second team. 0 for an invalid unit.

  `UnitGetX(unit)` — Returns a unit's tile X.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: Tile X; 0 for handle 0.
- Does not check that the slot holds a character.

  `UnitGetXByPID(pid)` *(startup.cmb)* — Resolves a deployed actor and reads UnitGetX.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: Map X coordinate, or -1 if unavailable.

  `UnitGetY(unit)` — Returns a unit's tile Y.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: Tile Y; 0 for handle 0.
- Does not check that the slot holds a character.

  `UnitGetYByPID(pid)` *(startup.cmb)* — Resolves a deployed actor and reads UnitGetY.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: Map Y coordinate, or -1 if unavailable.

  `UnitMoveDir(unit, path)` — Walks a unit along a list of steps, ignoring terrain and other units.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `path`: One character per step: 2 down, 4 left, 6 right, 8 up. The letters L, R, U and D make the unit face left, right, up or down at the end. Example: "6662L".
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- Does not wait: use UnitMoveWait. The unit's tile changes to the end of the path at once. While the event is being skipped it appears there directly.

  `UnitMoveDirByPID(pid, path)` *(startup.cmb)* — Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitMoveDir with the remaining arguments.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `path`: Native direction-command string.
- *Returns*: Actor reference if scheduled; 0 if unavailable.
- Does not wait: use UnitMoveWait.

  `UnitMovePos(unit, x, y)` — Walks a unit to a tile along a real path. If the tile is taken, the nearest free tile the unit can reach is used.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- Does not wait: use UnitMoveWait. If no tile is reachable, the unit does not move. While the event is being skipped the unit appears there at once. Speed, fading and camera follow come from the UnitWalkSlow/UnitFade*/UnitFocus* settings.

  `UnitMovePosByPID(pid, x, y)` *(startup.cmb)* — Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitMovePos with the remaining arguments.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `x`: Map-grid X coordinate, including the map's border.
- `y`: Map-grid Y coordinate, including the map's border.
- *Returns*: Actor reference if scheduled; 0 if unavailable.
- Does not wait: use UnitMoveWait.

  `UnitMoveToUnit(destination_unit, moving_unit)` *(startup.cmb)* — Requires both actors to be deployed. Reads the FIRST actor's X/Y and moves the SECOND actor toward that tile.

- `destination_unit`: Actor whose tile is the destination.
- `moving_unit`: Actor to move; argument order is significant.
- *Returns*: 0 for absent/nondeployed actor; 1 after calling UnitMovePos.

  `UnitMoveToUnitByPID(destination_pid, moving_pid)` *(startup.cmb)* — Resolves both PIDs and calls UnitMoveToUnit(destination, mover). Discards that helper's result.

- `destination_pid`: PID whose tile is the destination.
- `moving_pid`: PID to move.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `UnitMoveWait()` — Waits until every unit movement, turn and death/warp animation started by the event has finished.

- *Returns*: 1.
- Returns immediately if nothing is moving. UnitMovePos, UnitMoveDir, UnitRotate, Dispos and the other staging calls do not wait by themselves.

  `UnitPairup(carrier, carried)` — Links two actors using the game’s carrying/pairing operation, first moving the second actor to the tile right of the first.

- `carrier`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `carried`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- *Returns*: 1 for two valid actors; 0 otherwise.
- Changes positions and refreshes movement ranges. This is the FE9 carry relationship, not a later game’s Pair Up combat system.

  `UnitQueryJID(unit, jid)` — Tests whether a unit has a given class.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `jid`: Exact JID_... class ID.
- *Returns*: 1 if it is that exact class; 0 otherwise or for handle 0.
- The match is exact: a promoted or female variant is a different JID.

  `UnitQueryJIDByPID(pid, class_id)` *(startup.cmb)* — Looks up the actor; if present, returns UnitQueryJID(actor, class_id).

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `class_id`: JID_... class ID.
- *Returns*: 0 for missing actor, otherwise the native class-test result.

  `UnitQueryPID(unit, pid)` — Tests whether a unit is a given character.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `pid`: Exact PID_... character ID string.
- *Returns*: 1 if it is; 0 otherwise or for handle 0.

  `UnitRotate(unit, direction, duration_ms)` — Turns a unit to face a direction.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `direction`: 1 left, 2 right, 4 down, 8 up; add two for a diagonal (5 down-left, 6 down-right, 9 up-left, 10 up-right).
- `duration_ms`: Turning time in milliseconds; 0 turns at once.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- Does not wait: use UnitMoveWait. While the event is being skipped the unit turns at once.

  `UnitRotateByPID(pid, direction, duration_ms)` *(startup.cmb)* — Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitRotate with the remaining arguments.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `direction`: Facing: 1 left (−X), 2 right (+X), 4 down (+Y), 8 up (−Y); add two for a diagonal (5, 6, 9, 10).
- `duration_ms`: Duration in milliseconds. Use the matching completion wait when synchronizing animation.
- *Returns*: Actor reference if scheduled; 0 if unavailable.
- Does not wait: use UnitMoveWait.

  `UnitRotateToPos(unit, x, y, duration_ms)` *(startup.cmb)* — Requires a deployed actor, compares its tile to the target tile and chooses an eight-direction facing using the original axis/diagonal threshold branches, then calls UnitRotate.

- `unit`: Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check.
- `x`: Map-grid X coordinate, including the map's border.
- `y`: Map-grid Y coordinate, including the map's border.
- `duration_ms`: Duration in milliseconds. Use the matching completion wait when synchronizing animation.
- *Returns*: 0 (implicit return); do not interpret this as failure.
- No success return is emitted: success also returns 0. This is discrete facing selection, not an exact continuous-angle look-at.

  `UnitRotateToPosByPID(pid, x, y, duration_ms)` *(startup.cmb)* — Resolves a deployed actor and forwards to UnitRotateToPos.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `x`: Map-grid X coordinate, including the map's border.
- `y`: Map-grid Y coordinate, including the map's border.
- `duration_ms`: Duration in milliseconds. Use the matching completion wait when synchronizing animation.
- *Returns*: 0, including on successful scheduling.

  `UnitRotateToUnit(rotating_unit, target_unit, duration_ms)` *(startup.cmb)* — Requires both actors deployed, reads the target actor's tile and rotates the first actor toward it using UnitRotateToPos.

- `rotating_unit`: Actor whose facing changes.
- `target_unit`: Actor whose tile supplies the target.
- `duration_ms`: Duration in milliseconds. Use the matching completion wait when synchronizing animation.
- *Returns*: 0, including on successful scheduling.

  `UnitRotateToUnitByPID(rotating_pid, target_pid, duration_ms)` *(startup.cmb)* — Resolves both deployed actors and forwards to UnitRotateToUnit.

- `rotating_pid`: PID whose facing changes.
- `target_pid`: PID to face.
- `duration_ms`: Duration in milliseconds. Use the matching completion wait when synchronizing animation.
- *Returns*: 0, including on successful scheduling.

  `UnitSet(unit, field, value)` — Writes one of the supported mutable unit fields.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `field`: 6 = level; 7 = experience; 8 = raw transformation gauge; 13 = current HP; 24 = biorhythm battle counter; 38 = group id (army-name index into GroupData; 0 leaves it unchanged). Other selectors do not write a field.
- `value`: New value. Level/gauge use a byte; counter uses 16 bits. HP is clamped by the unit HP setter.
- *Returns*: Supplied value for a valid unit, even for an unsupported selector; 0 for invalid unit or selector 0.
- This is not a general stat editor: use dedicated stat calls for strength, magic, etc. UnitGet supports more fields than UnitSet.

  `UnitSetEXP(unit, exp)` — Sets a unit's experience.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `exp`: 0–100, or 255 for 'cannot gain experience'. Other values are ignored.
- *Returns*: 0.
- No level-up happens, even at 100.

  `UnitSetFixed(unit, enabled)` — Sets or clears the unit’s fixed-state flag.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1 for a valid unit; 0 if the handle is zero or its slot has no character.

  `UnitSetHold(enabled)` — Changes the shared scene unit-hold setting.

- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1.
- Applies to scene state, not one unit. Restore 0 when the hold sequence ends.

  `UnitSetHP(unit, hp)` — Sets a unit's current HP.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `hp`: New HP; kept between 0 and the unit's maximum HP.
- *Returns*: 0.
- Setting 0 does not kill the unit or start a death event.

  `UnitSetPos(unit, x, y)` — Places a unit on a tile at once. If the tile is taken, the nearest free tile is used.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- Unlike UnitMovePos, the unit's movement range is not considered.

  `UnitSetPosDir(unit, x, y, direction)` *(startup.cmb)* — For a non-null actor, sets its tile then immediately rotates it unless direction is -1.

- `unit`: Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check.
- `x`: Map-grid X coordinate, including the map's border.
- `y`: Map-grid Y coordinate, including the map's border.
- `direction`: Engine facing code; -1 preserves facing. Other values are passed to UnitRotate with duration 0.
- *Returns*: 0 for null; 1 after applying the calls.

  `UnitSetPosDirByPID(pid, x, y, direction)` *(startup.cmb)* — Resolves a deployed actor, sets its tile, and immediately rotates unless direction is -1.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `x`: Map-grid X coordinate, including the map's border.
- `y`: Map-grid Y coordinate, including the map's border.
- `direction`: Facing code; -1 leaves facing unchanged.
- *Returns*: Actor reference on success; 0 if unavailable.

  `UnitSetPosDirByPos(source_x, source_y, destination_x, destination_y, direction)` *(startup.cmb)* — Finds the actor at the source tile, moves it to the destination, and immediately rotates unless direction is -1.

- `source_x`: Source map X.
- `source_y`: Source map Y.
- `destination_x`: Destination map X.
- `destination_y`: Destination map Y.
- `direction`: Facing code; -1 preserves facing.
- *Returns*: Actor reference on success; 0 if the source tile has no actor.

  `UnitSetStatus(unit, mask)` — Sets state flags on a unit.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `mask`: Bits to set; see UnitGetStatus.
- *Returns*: The unit's new flag word; 0 for an invalid unit.
- Vanilla scripts set 0x100000, 0x200000, 0x400000 and 0x1. Setting bookkeeping bits such as 0x2, 0x4 or 0x8 by hand desynchronises the unit.

  `UnitTackle(acting_unit, target_unit, distance)` — Moves the target away from the acting unit and starts shove/smite motion.

- `acting_unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `target_unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `distance`: Positive displacement in tiles; normally 1 for shove, 2 for smite. Use aligned adjacent units.
- *Returns*: 1 if motion is started; 0 for invalid units or the skip path. The skip path still moves the target immediately.
- Does not itself validate that the destination is legal. Use the scene’s unit-motion wait before dependent actions.

  `UnitTransferToForce(unit, force)` — Moves a unit to another force, for example to recruit it (force 0) or turn it into an ally (2).

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `force`: Force ID: 0 player, 1 enemy, 2 allied (orderable), 3 other (green), 4 free pool, 5 player reserve, 6 dead/inactive, 7 special inactive.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- The unit takes the army group of the destination force's first group commander, if there is one. Moving to the player, allied or other force clears its item-drop marks. Its map model is reloaded in the new army colour.

  `UnitTransferToForceByPID(pid, force)` *(startup.cmb)* — Resolves the actor, applies the UnitCheckLiveByPID-equivalent null/status-0x08/force-6 test, then calls UnitTransferToForce.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `force`: Runtime force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 player reserve, 6 inactive/death-flagged, 7 special inactive. Not a phase number.
- *Returns*: 0 if missing/not live under that test; 1 after transfer.
- Unlike the movement helpers, it does not require the unit to be in forces 0–3: a living reserve unit passes.

  `UnitTransform(unit, transformed)` — Changes a unit to the requested transformed/untransformed state with its transformation animation.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `transformed`: 0 requests untransformed; nonzero requests transformed. This is a desired state, not a toggle.
- *Returns*: 1 if an animation is scheduled; 0 for invalid unit or already matching state; the skip path applies the change immediately but returns 0.
- Use only on a compatible laguz unit. Synchronize with the scene’s unit-motion wait.

  `UnitWalkDir(direction)` — Sets the direction bits used by subsequent scene walking.

- `direction`: Low four direction bits: 1 negative X, 2 positive X, 4 positive Y, 8 negative Y. Other bits are discarded.
- *Returns*: 1.
- Shared movement setting, not the direction of a unit passed to this call.

  `UnitWalkSlow(enabled)` — Enables or disables slow walking for subsequent scene movement.

- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1.
- This is shared scene state. Restore 0 when the slow-walk sequence ends.

  `UnitWarpOut(unit)` — Plays the Warp effect on a unit and waits for it.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: 1; 0 for an invalid unit or during an event skip (nothing is played).
- Visual only: the unit's force and tile do not change. Remove or move it separately.

## Inventory, skills and AI

  Eight inventory slots per unit: 0–3 weapons, 4–7 items. Skills by SID_, AI scripts by SEQ_ and MTYPE_ names.

  `_gi(unit, item_id)` — Gives an item to a unit and shows the result window (the step behind UnitGetItemShowing).

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `item_id`: IID_... item ID.
- *Returns*: 1; 0 for an invalid unit.
- A player unit shows 'got item'; an enemy unit shows 'item taken' and the item is marked as its drop. When a player or reserve unit's inventory is full, the game opens the window to send an item to the convoy or discard one. The script waits for the window.

  `CpClrNoMoveFlag(unit)` — Clears the two no-move control bits from a unit’s AI state.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- *Returns*: Updated AI control word; 0 for an invalid unit. A zero result can also mean all bits are now clear.

  `ItemGetIndex(iid)` — Resolves an item ID to its numeric item index.

- `iid`: Existing IID_... item ID string.
- *Returns*: Item index; 0 if the item ID is not found.

  `MindGetItem(item_id)` *(startup.cmb)* — Calls UnitGetItemShowing(MindGetMe(), item_id).

- `item_id`: IID_... reward item.
- *Returns*: 0 (implicit return); do not interpret this as failure.
- Recipient is the current acting unit; inappropriate context may provide no valid recipient.

  `MindGetMoney(amount)` — Adds gold to the party and starts a reward notification associated with the current acting unit.

- `amount`: Gold amount added to the current total.
- *Returns*: 0; not a failure code.
- Use in an event with a valid acting-unit context.

  `UnitAddItem(unit, item_id)` — Puts an item in a unit's inventory, silently: depending on the item type it goes to the first free weapon slot (0–3) or the first free item slot (4–7).

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `item_id`: IID_... item ID.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- If those slots are full, the item is not added, but the call still returns 1. To show the 'got item' window, use UnitGetItemShowing.

  `UnitAddSkill(unit, skill_id)` — Gives a unit a skill.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `skill_id`: SID_... skill ID.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- Adds it to the unit's runtime skill set; skill capacity is not checked. An unknown SID does nothing.

  `UnitCanUseIt(unit, slot)` — Checks whether the unit can use the item in the specified inventory slot.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `slot`: Inventory index: 0–3 weapon slots, 4–7 item/accessory slots. Never pass an index outside 0–7.
- *Returns*: Use predicate; 0 for an invalid unit or an empty slot.

  `UnitClrSkill(unit, skill_id)` — Removes a skill from a unit.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `skill_id`: SID_... skill ID.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- Removes it from the unit's runtime skill set.

  `UnitDelItem(unit, slot)` — Removes the item in an inventory slot and closes the gap.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `slot`: Inventory slot: 0–3 are the four weapon slots, 4–7 the four item slots.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

  `UnitGetEquipAccI(unit)` — Gets the active accessory slot in the combined inventory numbering.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- *Returns*: Accessory slot index 4–7, or -1 when none is active; 0 for an invalid unit.

  `UnitGetEquipWepI(unit)` — Gets the active equipped-weapon slot index.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- *Returns*: Weapon slot index, or -1 when none is active; 0 for an invalid unit.
- Validate the unit first because 0 is also a valid slot.

  `UnitGetItemCount(unit)` — Counts the items a unit carries, weapons included.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: 0–8; 0 for an invalid unit.

  `UnitGetItemShowing(unit, item_id)` *(startup.cmb)* — Disables skip; if Comeback() is nonzero, starts Fade(2,166) and waits. Calls _gi(unit,item_id), yields once, then enables skip.

- `unit`: Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check.
- `item_id`: IID_... reward item.
- *Returns*: 0 (implicit return); do not interpret this as failure.
- No null check. _gi shows the item window and handles a full inventory (convoy/discard choice for player units).

  `UnitGetItemShowingSub(unit, item_id)` *(startup.cmb)* — Quiets music channel 0, externally calls UnitGetItemShowing(unit,item_id), then restores channel quiet state.

- `unit`: Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check.
- `item_id`: IID_... reward item.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `UnitGetWeaponCount(unit)` — Counts the weapons a unit carries (its four weapon slots).

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: 0–4; 0 for an invalid unit.

  `UnitItemGetValuation(unit, slot)` — Returns a value score for an inventory item, used to pick which item to send away.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `slot`: Inventory slot: 0–3 are the four weapon slots, 4–7 the four item slots.
- *Returns*: Item price multiplied by its remaining uses, plus fixed bonuses for special items (character- or class-locked weapons add 50,000); 0 for an empty slot or invalid unit.
- Only meaningful for comparing items, as UnitItemSendToHouseByPID does.

  `UnitItemSendToHouseByPID(pid)` *(startup.cmb)* — Requires an existing actor with exactly four weapons. Compares valuations for indices 0–3, then sends one entry to storage.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: -1 if missing or weapon count is not 4; otherwise 0.
- Do not simplify this to 'always sends the cheapest': the index-2 branch checks v4 <= v2, v4 <= v3, but v3 <= v5 (not v4 <= v5). Tie order prefers earlier branches. Preserve the actual logic.

  `UnitItemSendtoWarehouse(unit, slot)` — Sends one inventory item to the convoy.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `slot`: Inventory slot: 0–3 are the four weapon slots, 4–7 the four item slots.
- *Returns*: 1 if sent; 0 for an invalid unit, an empty slot, or before the convoy is available (internal chapter numbers 1–8, Prologue to Chapter 7).
- If the convoy is full, its least valuable item is deleted to make room.

  `UnitItemSendtoWarehouseAll(unit)` — Transfers all eight of a unit’s inventory slots to storage, clears the original slots, and compacts the inventory.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- *Returns*: 1 for a valid unit; 0 if the handle is zero or its slot has no character.
- The two function names are aliases. The original slot is cleared after each transfer attempt; make sure storage has enough capacity before using this on valuable items.

  `UnitItemSetDrop(unit, slot)` — Marks one inventory item as dropped when the unit is defeated.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `slot`: Inventory slot: 0–3 are the four weapon slots, 4–7 the four item slots.
- *Returns*: 1 if marked; 0 if the unit already has a dropped item, the slot is empty or the unit is invalid.
- Only one item per unit can be marked.

  `UnitPutToWarehouse(unit)` — Transfers all eight of a unit’s inventory slots to storage, clears the original slots, and compacts the inventory.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- *Returns*: 1 for a valid unit; 0 if the handle is zero or its slot has no character.
- The two function names are aliases. The original slot is cleared after each transfer attempt; make sure storage has enough capacity before using this on valuable items.

  `UnitQueryEquip(unit, slot)` — Tests the equipped bit of an inventory slot.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `slot`: Inventory index: 0–3 weapon slots, 4–7 item/accessory slots. Never pass an index outside 0–7.
- *Returns*: 1 if the slot’s equipped bit is set; 0 otherwise or for an invalid unit.

  `UnitReplaceItem(unit, slot, iid)` — Replaces the selected inventory slot using an item ID.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address.
- `slot`: Inventory index: 0–3 weapon slots, 4–7 item/accessory slots. Never pass an index outside 0–7.
- `iid`: Existing IID_... item definition.
- *Returns*: 1 for a valid unit; 0 if the handle is zero or its slot has no character.
- Provide a valid slot and item ID; this is not an “add to first empty slot” operation.

  `UnitSearchItem(unit, item_id)` — Finds an item in a unit's inventory.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `item_id`: IID_... item ID.
- *Returns*: Slot 0–7 of the first copy; -1 if the unit does not carry it; 0 for an invalid unit.
- 0 is also a valid slot, so check the unit first.

  `UnitSetAccAway(unit)` — Unequips the unit's equipped item (band or ring).

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: The item slot 4–7 that was equipped; -1 if none was; 0 for an invalid unit.

  `UnitSetCpAttackSeq(unit, sequence)` — Changes the attack AI script of a unit.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `sequence`: SEQ_... AI script name from the AI data.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- The script restarts from its first step. An unknown name leaves the old script in place.

  `UnitSetCpHealSeq(unit, record)` — Changes the healing AI record of a unit.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `record`: Name of a healing record in the AI data.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- An unknown name leaves the old setting in place.

  `UnitSetCpMoveSeq(unit, sequence)` — Changes the movement AI script of a unit.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `sequence`: SEQ_... AI script name from the AI data.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- The script restarts from its first step. An unknown name leaves the old script in place.

  `UnitSetCpMTypeID(unit, table)` — Changes the MTYPE AI table of a unit (how it values targets).

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `table`: MTYPE_... table name from the AI data.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- An unknown name leaves the old table in place.

  `UnitSetCpTypeByPID(pid, attack_sequence, move_sequence)` *(startup.cmb)* — Resolves a deployed actor, then sets its attack sequence followed by its movement sequence.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `attack_sequence`: SEQ_... passed to UnitSetCpAttackSeq.
- `move_sequence`: SEQ_... passed to UnitSetCpMoveSeq.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `UnitSetEquip(unit, slot)` — Equips an inventory item.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `slot`: 0–3 equips that weapon; -1 equips the first weapon the unit can use; 4–7 equips that item if it is equippable (bands, rings).
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- The other slots of the same half are unequipped first, so a slot the unit cannot use leaves it with nothing equipped there. Laguz units are not changed. Equipping a weapon updates the weapon held by the map model.

  `UnitSetWeaponAway(unit)` — Unequips the unit's weapon.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: The weapon slot 0–3 that was equipped; -1 if none was equipped or the unit is a laguz; 0 for an invalid unit.
- The map model is updated to hold no weapon.

  `UnitSetWeaponAwayByPID(pid)` *(startup.cmb)* — Resolves a deployed actor and returns UnitSetWeaponAway(actor).

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: -2 if the character has no unit; otherwise UnitSetWeaponAway's result (the slot that was equipped, or -1).

  `UnitTstSkill(unit, skill_id)` — Tests whether a unit holds a skill.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `skill_id`: SID_... skill ID.
- *Returns*: 1 if the unit holds it; 0 otherwise or for an invalid unit.

## Deployment and preparations

  Placing deployment groups from the chapter's dispos file, the preparation screen and whole-army save/restore.

  `AllPop()` — Restores the game state saved by AllPush and frees the buffer.

- *Returns*: 1.
- Chapter flags set during the tutorial are cleared first. Map and models are not reloaded: TutorialResumeOut follows it with MapReload and UnitDispReload.

  `AllPush()` — Saves the whole game state into the temporary buffer (party data, camera, every unit, convoy, forge records and map state), then resets units, chapter flags, map state, convoy and forge records.

- *Returns*: 1.
- Used by TutorialIn so a tutorial can run in a clean state. Same shared buffer as UnitsPush.

  `AllUnitEscape()` — Removes every unit of forces 0–3 from the map: carried units are dropped first, player units go to the reserve marked as escaped, all other units are deleted.

- *Returns*: 1.
- The map is refreshed afterwards.

  `AllUnitsBreakup()` *(startup.cmb)* — Walks force 0 only, bounded by ForceGetCount(0), and calls UnitCheckLinked_Breakup for each actor until count exhaustion or a null next actor.

- *Returns*: 0 (implicit return); do not interpret this as failure.
- Despite the name, it does not traverse all eight forces.

  `DispFreeWholeForce(force)` — Releases display resources for every actor in a force list.

- `force`: Force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 reserve, 6 inactive, 7 special inactive.
- *Returns*: 1.
- Does not change force membership or remove the actors.

  `DispLoadWholeForce(force)` — Loads display resources for every actor in a force list.

- `force`: Force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 reserve, 6 inactive, 7 special inactive.
- *Returns*: 1.
- Does not change force membership or remove the actors.

  `Dispos(group)` — Deploys a group: creates each listed unit that is not on the map yet (or reuses the existing one) and animates the units into place. The script waits for the movement.

- `group`: Name of a deployment group in the chapter's dispos file.
- *Returns*: 1.
- Each unit of the group goes to the free tile nearest its listed position; a character that already has a unit reuses it. Movement follows the UnitWalk*/UnitFade*/UnitFocus* scene settings. During an event skip the units appear at once.

  `Dispos_ForEvent(pid, class_id, matching_group, other_group, instant)` *(startup.cmb)* — If class_id is empty, uses matching_group without testing the actor. Otherwise tests UnitQueryJIDByPID and chooses matching_group or other_group. Uses InstantDispos when instant is nonzero, otherwise Dispos.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- `class_id`: JID to test, or empty string to bypass the class test.
- `matching_group`: Group for empty class or successful class match.
- `other_group`: Group for failed class match.
- `instant`: Nonzero = immediate placement; zero = ordinary deployment.
- *Returns*: 1 after the selected call, not proof the native deployment succeeded.

  `Dispos_ForEventSenerio(mage_group, other_group, instant)` *(startup.cmb)* — Calls Dispos_ForEvent for PID_SENERIO and JID_MAGE.

- `mage_group`: Group when Soren matches JID_MAGE.
- `other_group`: Group otherwise.
- `instant`: Nonzero = InstantDispos; zero = Dispos.
- *Returns*: 1.

  `Dispos_ForEventTiamat(group, instant)` *(startup.cmb)* — Calls Dispos_ForEvent("PID_TIAMAT", "", group, group, instant); the empty class bypasses the actor/class check.

- `group`: Existing named deployment section. This call does not create the section or its unit records.
- `instant`: Nonzero = InstantDispos; zero = Dispos.
- *Returns*: 1.

  `DisposAsynchronous(group)` — Same as Dispos, but the script continues while the units move.

- `group`: Name of a deployment group in the chapter's dispos file.
- *Returns*: 1.
- Use UnitMoveWait when later steps need the units in place.

  `DisposAuxiliary(group)` — Deploys the units the player picked for the second team (SelectAuxiliary) onto the group's tiles and moves them from the reserve to the player force.

- `group`: Deployment group that holds the second team's positions.
- *Returns*: 1.
- Does nothing when no unit was picked. The script waits for the movement.

  `DisposContinue(group)` — Moves the units of a group that already exist to the group's positions, and waits for the movement. It never creates units.

- `group`: Name of a deployment group in the chapter's dispos file.
- *Returns*: 1.
- Units that have acted, are carried, dead, in the reserve or under a roof are skipped. Each unit of the group goes to the free tile nearest its listed position; a character that already has a unit reuses it.

  `DisposContinueSetMode(normal_group, hard_group, fallback_group)` *(startup.cmb)* — Calls DisposContinue(normal_group) if NormalOnly(), otherwise DisposContinue(hard_group) if Hard(), otherwise DisposContinue(fallback_group).

- `normal_group`: First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name.
- `hard_group`: Group selected when Hard() is true.
- `fallback_group`: Group selected otherwise; do not infer a menu difficulty solely from a filename suffix.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `DisposFirst(group)` — Deploys a group onto its exact listed tiles, without searching for a free tile, and waits for the movement.

- `group`: Name of a deployment group in the chapter's dispos file.
- *Returns*: 1.
- Meant for the first placement of a chapter, when the listed tiles are known to be empty.

  `DisposFirstSetMode(normal_group, hard_group, fallback_group)` *(startup.cmb)* — Calls DisposFirst(normal_group) if NormalOnly(), otherwise DisposFirst(hard_group) if Hard(), otherwise DisposFirst(fallback_group).

- `normal_group`: First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name.
- `hard_group`: Group selected when Hard() is true.
- `fallback_group`: Group selected otherwise; do not infer a menu difficulty solely from a filename suffix.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `DisposGetGroupCenter(group, out_x, out_y)` — Computes the center of a named deployment group and writes its coordinates into two variables.

- `group`: Existing deployment group name.
- `out_x`: Address of an integer local, written with the group-center X.
- `out_y`: Address of an integer local, written with the group-center Y.
- *Returns*: 0; read the output variables.

  `DisposSetMode(normal_group, hard_group, fallback_group)` *(startup.cmb)* — Calls Dispos(normal_group) if NormalOnly(), otherwise Dispos(hard_group) if Hard(), otherwise Dispos(fallback_group).

- `normal_group`: First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name.
- `hard_group`: Group selected when Hard() is true.
- `fallback_group`: Group selected otherwise; do not infer a menu difficulty solely from a filename suffix.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `DisposWarp(group)` — Deploys a named reinforcement group using the warp deployment mode and suspends for active deployment motion.

- `group`: Existing deployment group; create its records in the deployment data first.
- *Returns*: 1.

  `DispPreLoadWholeForce(force)` — Queues battle-animation assets for every actor in a force list.

- `force`: Force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 reserve, 6 inactive, 7 special inactive.
- *Returns*: 1.
- Does not change force membership or remove the actors.

  `ForceCheckAnyoneDead()` *(startup.cmb)* — Walks force 6 and tests status bit 0x8000 on each actor.

- *Returns*: 1 if any scanned actor has that bit; 0 otherwise.

  `ForceGetCount(force)` — Counts the units in a force.

- `force`: Force ID: 0 player, 1 enemy, 2 allied (orderable), 3 other (green), 4 free pool, 5 player reserve, 6 dead/inactive, 7 special inactive.
- *Returns*: Number of units in that force.
- No range check: use 0–7.

  `ForceGetFirst(force)` — Returns the first unit of a force, to walk it with UnitGetNext.

- `force`: Force ID: 0 player, 1 enemy, 2 allied (orderable), 3 other (green), 4 free pool, 5 player reserve, 6 dead/inactive, 7 special inactive.
- *Returns*: Unit handle; 0 if the force is empty.
- No range check: use 0–7.

  `InstantDispos(group)` — Same as Dispos, but places every unit at once without animation.

- `group`: Name of a deployment group in the chapter's dispos file.
- *Returns*: 1.

  `InstantDisposContinue(group)` — Same as DisposContinue, without animation.

- `group`: Name of a deployment group in the chapter's dispos file.
- *Returns*: 1.

  `InstantDisposContinueSetMode(normal_group, hard_group, fallback_group)` *(startup.cmb)* — Calls InstantDisposContinue(normal_group) if NormalOnly(), otherwise InstantDisposContinue(hard_group) if Hard(), otherwise InstantDisposContinue(fallback_group).

- `normal_group`: First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name.
- `hard_group`: Group selected when Hard() is true.
- `fallback_group`: Group selected otherwise; do not infer a menu difficulty solely from a filename suffix.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `InstantDisposFirst(group)` — Same as DisposFirst, without animation.

- `group`: Name of a deployment group in the chapter's dispos file.
- *Returns*: 1.

  `InstantDisposFirstSetMode(normal_group, hard_group, fallback_group)` *(startup.cmb)* — Calls InstantDisposFirst(normal_group) if NormalOnly(), otherwise InstantDisposFirst(hard_group) if Hard(), otherwise InstantDisposFirst(fallback_group).

- `normal_group`: First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name.
- `hard_group`: Group selected when Hard() is true.
- `fallback_group`: Group selected otherwise; do not infer a menu difficulty solely from a filename suffix.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `InstantDisposRank(group)` — Deploys the difficulty variant of a group at once: adds "_n" to the name on Normal, "_h" on Hard and "_m" on Maniac or Easy, then works like InstantDispos.

- `group`: Group name without the difficulty suffix.
- *Returns*: 1.
- The finished name must exist for each difficulty you support.

  `InstantDisposSetMode(normal_group, hard_group, fallback_group)` *(startup.cmb)* — Calls InstantDispos(normal_group) if NormalOnly(), otherwise InstantDispos(hard_group) if Hard(), otherwise InstantDispos(fallback_group).

- `normal_group`: First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name.
- `hard_group`: Group selected when Hard() is true.
- `fallback_group`: Group selected otherwise; do not infer a menu difficulty solely from a filename suffix.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `Join(group)` — Adds the characters of a deployment group to the player's reserve (force 5), off the map. Characters that already have a unit keep it.

- `group`: Name of a deployment group in the chapter's dispos file.
- *Returns*: 1; 0 if group is not a valid string.
- Used to recruit characters between chapters, for example the always_T_* groups added by TrialAddUnit.

  `SallyAddByGroup(group)` — Adds the tiles of a group to the preparation screen's deployment tiles.

- `group`: Name of a deployment group in the chapter's dispos file.
- *Returns*: 1.

  `SallyAddByPos(x, y)` — Appends a deployment-selection position.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- *Returns*: 1.

  `SallyGetSurplus()` — Reads the deployment surplus recorded when the deployment-selection flow finishes.

- *Returns*: Surplus byte; initialized to 0 at chapter start.
- The stored value is the greater of the selection flow’s minimum and (deployment allowance − selected player count). Read after selection completes, not while editing the selection.

  `SallySetByGroup(group)` — Replaces the preparation screen's deployment tiles with the tiles of a group.

- `group`: Name of a deployment group in the chapter's dispos file.
- *Returns*: 1.
- Each record of the group gives one deployment tile; the units in the records are not created.

  `SallySetByPos(x, y)` — Clears the deployment-selection position list, then adds this position.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- *Returns*: 1.
- Repeated calls replace the list; use SallyAddByPos to append additional positions.

  `SelectAuxiliary(group)` — Starts the auxiliary-unit selection flow for a deployment group and suspends the calling script.

- `group`: Existing deployment group name.
- *Returns*: 1 when accepted; 0 for an invalid group argument.

  `SysGetRound()` — Reads the playthrough ordinal from the clear-data record.

- *Returns*: 1 plus the number of consecutive occupied clear-data slots, from 1 to 31.
- Used by trial-map unlock helpers; not the current map turn.

  `TrialAddUnit()` *(startup.cmb)* — Reads SysGetRound and calls Join for always_T_03 at >=4, always_T_05 at >=6, always_T_07 at >=8, always_T_10 at >=11, and always_T_15 at >=16. These are independent tests: higher counts call all qualifying groups.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `UnitDispReload()` — Unloads and reloads the map models of every unit in forces 0–3, then refreshes their positions.

- *Returns*: 1.

  `UnitDontMoveSally(unit)` — Locks a unit's starting tile in the preparations: the player cannot swap its position.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- Only applies to units of the player force or the reserve. UnitDontMoveSallyByPID also makes the unit mandatory.

  `UnitDontMoveSallyByPID(pid)` *(startup.cmb)* — Requires a deployed actor, calls BOTH UnitForcedSally and UnitDontMoveSally.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: 0 if unavailable; 1 after both calls.

  `UnitForcedSally(unit)` — Makes a unit mandatory in the preparations: the player cannot remove it from the deployment.

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- *Returns*: 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.
- Only applies to units of the player force or the reserve.

  `UnitForcedSallyByPID(pid)` *(startup.cmb)* — Requires a deployed actor and calls UnitForcedSally.

- `pid`: Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.
- *Returns*: 0 if unavailable; 1 after the call.

  `UnitsInitialize()` — Removes every unit: all forces are emptied and all unit slots freed.

- *Returns*: 1.
- Also frees the unit models and clears the battle state. Not a chapter reset: flags, money and map state are kept.

  `UnitsPop()` — Restores the units saved by UnitsPush, refreshes the map and reloads the unit models. Frees the buffer.

- *Returns*: 1.
- Units created since the push are discarded.

  `UnitsPopWithoutMap()` — Same as UnitsPop, without the map refresh.

- *Returns*: 1.
- Call MapUpdate afterwards.

  `UnitsPush()` — Saves every unit (and the forge records) into a temporary buffer, then empties the forces.

- *Returns*: 1.
- One buffer is shared by UnitsPush, UnitsPush_Uninitialize and AllPush; a second push before the matching pop loses the first.

  `UnitsPush_Uninitialize()` — Saves every unit (and the forge records) into the temporary buffer, leaving the units in place.

- *Returns*: 1.
- Same shared buffer as UnitsPush.

## Map objects and terrain

  Doors, roofs, chests, villages and props (their state is kept in saves), special terrain such as ballistae, rocks and pits, and map loading.

  `_mf1()` — First step of MapFree: releases the map's objects if a map is loaded.

- *Returns*: 1 if a map was loaded; 0 otherwise.

  `_mf2()` — Second step of MapFree: frees the current map.

- *Returns*: 1.

  `AddTT(x, y, type, subtype, value_1, value_2)` — Adds a raw entry to the map's special-terrain list.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- `type`: Entry type: 4 breakable wall, 7 ballista, 9 pit, 10 rolling rock. Prefer SetFragile, SetShooter, SetPit and SetRock.
- `subtype`: Type-specific byte.
- `value_1`: First type-specific state byte.
- `value_2`: Second type-specific state byte.
- *Returns*: 1.
- Low-level: the dedicated calls fill the fields correctly. It does not change the map's look.

  `BeginMapHoldCursor()` — Starts the map cursor-hold process.

- *Returns*: 0.

  `BuildDestruction(x, y)` — Destroys the village or house at a tile: the camera moves to it, the ruin animation plays and the script waits for it.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 after the animation; 0 if none is found, or during an event skip (the building turns into ruins at once).
- The tile may be the building or a tile next to it. A destroyed village can no longer be visited. The change is recorded in the map state, so it is kept in saves.

  `BuildInstAnim(x, y, mode)` — Plays or sets the two-state animation of an animated map prop at a tile.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- `mode`: 0 plays forward and keeps the end state; 1 plays backward and keeps the start state; 2 plays once without changing the kept state; 3 jumps to the start state; 4 jumps to the end state.
- *Returns*: 1; 0 if no animated prop is at the tile, or for mode 2 during an event skip.
- Modes 0 and 1 do not wait. While the event is being skipped modes 0 and 1 jump to their final state. The kept state is recorded in the map state.

  `BuildInstHide(x, y)` — Hides a hideable map prop at a tile.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 if one was found; 0 otherwise.
- The change is recorded in the map state, so it is kept in saves.

  `BuildInstShow(x, y)` — Shows a hideable map prop at a tile.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 if one was found; 0 otherwise.
- The change is recorded in the map state, so it is kept in saves.

  `DoorClose(x, y)` — Closes the door at a tile with its animation and waits for it.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 after the animation; 0 if there is no door there, or during an event skip (the door closes at once).
- The change is recorded in the map state, so it is kept in saves. The door's hit points are restored to full.

  `DoorOpen(x, y)` — Opens the door at a tile with its animation and waits for it. The door stops blocking movement.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 after the animation; 0 if there is no door there, or during an event skip (the door opens at once).
- The change is recorded in the map state, so it is kept in saves.

  `EndMapHoldCursor()` — Ends the map cursor-hold process.

- *Returns*: 0.

  `EventGetX()` — Returns the X coordinate of the tile that started the current location event (visit, area, chest, door).

- *Returns*: Map tile X.
- Only meaningful inside an event started by a tile.

  `EventGetY()` — Returns the Y coordinate of the tile that started the current location event.

- *Returns*: Map tile Y.
- Only meaningful inside an event started by a tile.

  `GetMapHeight(x, y)` — Samples the alternate terrain-surface height at the supplied map coordinates.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- *Returns*: Sampled height multiplied by the event-camera precision factor, then truncated to an integer. Precision defaults to 1.
- Use with event-camera coordinates; this is a height value, not a flattened tile index.

  `GetMapHeightBase(x, y)` — Samples the base terrain height at the supplied map coordinates.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- *Returns*: Sampled height multiplied by the event-camera precision factor, then truncated to an integer. Precision defaults to 1.
- Use with event-camera coordinates; this is a height value, not a flattened tile index.

  `HideMapCursor()` — Removes every map cursor shown by ShowMapCursor.

- *Returns*: 1.

  `InstantDoorClose(x, y)` — Closes the door at a tile without animation and restores its hit points.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 if a door was found; 0 otherwise.
- The change is recorded in the map state, so it is kept in saves.

  `InstantDoorOpen(x, y)` — Opens the door at a tile without animation.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 if a door was found; 0 otherwise.
- The change is recorded in the map state, so it is kept in saves.

  `InstantRoofClose(x, y)` — Puts back the roof at a tile without animation.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 if a roof was found; 0 otherwise.
- The change is recorded in the map state, so it is kept in saves.

  `InstantRoofOpen(x, y)` — Lifts the roof at a tile without animation.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 if a roof was found; 0 otherwise.
- The change is recorded in the map state, so it is kept in saves.

  `MapFree()` *(startup.cmb)* — Calls _mf1(), yields once, then calls _mf2().

- *Returns*: 0 (implicit return); do not interpret this as failure.
- Two-stage native map release; removing the yield changes the sequence.

  `MapGetSight(x, y)` — Reads the visibility-grid byte at a tile.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- *Returns*: Stored visibility value.
- Use valid map coordinates and the chapter’s existing visibility comparisons; this does not recalculate sight.

  `MapGetTerrain(x, y)` — Reads the terrain ID stored at a map tile.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- *Returns*: Terrain ID byte.
- Use coordinates inside the allocated map grid; there is no coordinate bounds check.

  `MapGetUnit(x, y)` — Reads the occupancy-grid unit handle at a tile.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- *Returns*: Unit handle byte; 0 for an empty cell.
- This reads the occupancy grid directly. Use valid map coordinates.

  `MapLoad(map_name)` — Loads a map by name and makes it the current map.

- `map_name`: Map folder name, such as bmap02 or bmap06_2.
- *Returns*: 1.
- Only loads the map: it places no units and runs no chapter setup. The script yields once.

  `MapReload()` — Reloads the current chapter's map, reapplies its recorded map state (opened doors, visited villages, ...) and points the camera at the saved cursor tile.

- *Returns*: 1.
- Used when coming back from a tutorial (TutorialResumeOut).

  `MapUpdate()` — Recalculates the map's occupancy, movement ranges and danger areas after units or terrain changed.

- *Returns*: No meaningful value; call it for its effect.

  `RoofClose(x, y)` — Puts back the roof at a tile with its animation and waits for it.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 after the animation; 0 if there is no roof there, or during an event skip.
- The change is recorded in the map state, so it is kept in saves.

  `RoofOpen(x, y)` — Lifts the roof at a tile with its animation, revealing the building's inside, and waits for it.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 after the animation; 0 if there is no roof there, or during an event skip (the roof lifts at once).
- The change is recorded in the map state, so it is kept in saves.

  `SetAmbient(red, green, blue)` — Sets map ambient lighting color, refreshes the map and yields the script.

- `red`: Red component, 0–255.
- `green`: Green component, 0–255.
- `blue`: Blue component, 0–255.
- *Returns*: 1.
- Components are truncated to bytes, not clamped. Alpha is fixed to 255.

  `SetCamSuspend(enabled)` — Sets the camera-suspension flag for map scenes.

- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1.

  `SetCircle(enabled)` — Enables or disables the scene’s unit-circle display setting.

- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1.

  `SetDiffuse(red, green, blue)` — Sets map diffuse lighting color, refreshes the map and yields the script.

- `red`: Red component, 0–255.
- `green`: Green component, 0–255.
- `blue`: Blue component, 0–255.
- *Returns*: 1.
- Components are truncated to bytes, not clamped. Alpha is fixed to 255.

  `SetFog(fog_type, start_distance, end_distance, red, green, blue)` — Sets the map’s rendering fog and refreshes its render state.

- `fog_type`: 0 disables fog; 1 is perspective-linear, 2 exponential, 3 exponential-squared, 4 reverse-exponential, and 5 reverse-exponential-squared.
- `start_distance`: Signed-byte fog start distance in map units; converted by 5 × map scale for rendering.
- `end_distance`: Signed-byte fog end distance in the same units.
- `red`: Fog color red, 0–255.
- `green`: Fog color green, 0–255.
- `blue`: Fog color blue, 0–255.
- *Returns*: 1.
- This changes visual distance fog, not which tiles units can see. Use SetSight for gameplay visibility.

  `SetFragile(x, y, hp)` — Adds a breakable terrain entry with the requested HP.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- `hp`: Initial and current HP, stored as a byte (0–255).
- *Returns*: 1.

  `SetGrid(percent)` — Sets the map-grid display intensity or restores the value saved when scene settings were created.

- `percent`: 0–100 grid intensity; values above 100 become 100. A negative value restores the saved grid setting if scene settings exist.
- *Returns*: 1.

  `SetOutLink(enabled)` — Enables or disables the outer-link portion of the map-link grid and rebuilds that grid.

- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1.
- Shared scene setting. Restore the chapter’s setting after staged movement that changes it.

  `SetPit(x, y)` — Adds a pit terrain entry at the given tile.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- *Returns*: 1.

  `SetPullCursor(enabled)` — Enables or disables automatic cursor pulling.

- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1.

  `SetRock(x, y, direction, path_index)` — Adds a rolling-rock terrain entry connected to a registered motion path.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- `direction`: Initial direction code used by the matching rock setup.
- `path_index`: Slot returned by TTPMEntry, 0–31. Register the path first.
- *Returns*: 1.
- The map needs compatible rock geometry. This registers the terrain entry; it does not immediately roll the rock.

  `SetRoofEnable(x, y, enabled)` — Changes the enabled state of the roof section found at the supplied map position and refreshes the map.

- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- `enabled`: 0 disables; nonzero enables.
- *Returns*: 1 if a roof entry is found; 0 otherwise.

  `SetShooter(x, y, facing, iid)` — Places a ballista on a tile.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- `facing`: Direction the ballista points: 1 left, 2 right, 4 down, 8 up.
- `iid`: Ballista item: IID_LONGARCH, IID_IRONARCH, IID_KILLERARCH or IID_ONAGER.
- *Returns*: 1.
- The ballista starts with the item's full uses. The map needs a ballista model at that tile. The change is recorded in the map state, so it is kept in saves.

  `SetSight(mode, unused)` — Sets the fog-of-war/sight mode, recalculates map ranges and refreshes the map.

- `mode`: Sight-mode byte; internal difficulty other than 1 forces this to 0. Preserve the chapter’s supported mode values.
- `unused`: Ignored by this US implementation; pass 0 when creating a new call.
- *Returns*: 1.
- The signature still requires two arguments even though the second is ignored. This controls gameplay visibility, unlike SetFog’s rendering effect.

  `SetTerrain(x, y, terrain)` — Changes the terrain type of one tile.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- `terrain`: Terrain ID (index into the terrain table).
- *Returns*: 0.
- Writes the terrain grid only: the map's look does not change, and movement ranges update at the next map refresh (MapUpdate). No coordinate check.

  `SetWeather(weather)` — Changes the map weather byte and refreshes weather, lighting and visibility rendering.

- `weather`: Weather ID supported by the loaded chapter. Preserve the matching map’s existing IDs when adding effects.
- *Returns*: 1.
- The script yields after refreshing. Weather effects depend on the map’s resources.

  `ShooterBulletCheck()` — Counts the ballista shots spent on the map.

- *Returns*: Sum, over every ballista on the map, of 5 minus its remaining shots.
- Assumes five shots per ballista; a ballista with more shots adds a negative amount.

  `ShowMapCursor(x, y)` — Shows the blinking map cursor on a tile.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1.
- Remove it with HideMapCursor.

  `TBoxOpen(x, y)` — Plays the opening of the chest at a tile and waits for it, and marks the chest as opened.

- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 if a chest was found; 0 otherwise.
- Gives no item: the chest event gives it separately (MindGetItem or UnitGetItemShowing). The change is recorded in the map state, so it is kept in saves.

  `TTPMEntry(path)` — Stores a path for a rolling rock in the first free path slot.

- `path`: Direction string: 2 down, 4 left, 6 right, 8 up, one tile per character, for example "66222". Kept by reference, not copied.
- *Returns*: Slot 0–31; -1 if all 32 slots are used.
- Give the slot to SetRock. Use a string literal so it stays valid.

  `TTPMInit()` — Clears the 32 registered terrain-motion path slots.

- *Returns*: 1.
- Call before registering rock-motion paths for a chapter. Existing rocks referring to these slots need their paths registered again.

  `VisitIn(unit, x, y)` — Does nothing (kept for the visit-event scripts).

- `unit`: Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.
- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1.
- Its arguments are ignored. Vanilla visit events call it with MindGetMe(), EventGetX() and EventGetY().

  `VisitOut(unit, x, y)` — Closes the village at a tile after a visit: plays its closing animation, waits for it and marks the village as visited.

- `unit`: Ignored; vanilla passes the visiting unit.
- `x`: Map tile X, including the map border.
- `y`: Map tile Y, including the map border.
- *Returns*: 1 after the animation; 0 if no village is found, or during an event skip (the village closes at once).
- The tile may be the village itself or a tile next to it. The change is recorded in the map state, so it is kept in saves.

## Scripted battles and effects

  Battles with forced results, map effects, event arrows and screen shakes.

  `EffectPlay(effect_id, x, y)` — Loads and spawns a named scene effect at the supplied position.

- `effect_id`: Existing EID_... effect resource.
- `x`: Map tile X for a map-space effect; direct effect-space X for effects configured in another coordinate mode.
- `y`: Map tile Y for a map-space effect; direct effect-space Y for effects configured in another coordinate mode.
- *Returns*: 1 when scheduled; 0 during event skipping.
- Map-space effects use the tile center and terrain height. The resource determines coordinate mode. The script waits for the loading/spawn process, not necessarily the full effect lifetime.

  `EffectWait()` — Waits for the effect started by EffectPlay to finish.

- *Returns*: 1; 0 while the event is being skipped.
- While the event is being skipped it removes the effect at once instead of waiting.

  `EventArrowAppend(arrow_id, time_ms, x, y, height)` — Adds a timed waypoint to a map-event arrow’s path.

- `arrow_id`: Arrow slot index. Use a slot supported by the existing scene; this index is not bounds-checked.
- `time_ms`: Waypoint time in milliseconds, converted to frames and sorted into the path.
- `x`: Map tile X coordinate, including the border; passed as a signed byte.
- `y`: Map tile Y coordinate, including the border; passed as a signed byte.
- `height`: Map-space height. A value below -999 samples the terrain at the tile center, subtracts 1, and truncates to an integer.
- *Returns*: 1.
- X/Y are centered on the tile by adding 0.5. Build the path before EventArrowStart; use an existing path’s slot and waypoint limits.

  `EventArrowColor(arrow_id, red, green, blue, alpha)` — Sets the arrow’s RGBA color.

- `arrow_id`: Arrow slot index. Use a slot supported by the existing scene; this index is not bounds-checked.
- `red`: 0–255.
- `green`: 0–255.
- `blue`: 0–255.
- `alpha`: 0 transparent; 255 opaque.
- *Returns*: 1.
- Values are stored as bytes; they wrap rather than clamp.

  `EventArrowDelete()` — Deletes the map-event arrow process and all of its arrows.

- *Returns*: 1.

  `EventArrowFadeOut(arrow_id)` — Requests fade-out of the selected map-event arrow.

- `arrow_id`: Arrow slot index. Use a slot supported by the existing scene; this index is not bounds-checked.
- *Returns*: 1.

  `EventArrowStart(arrow_id, duration_ms)` — Starts an arrow path transition from its current progress using the supplied time.

- `arrow_id`: Arrow slot index. Use a slot supported by the existing scene; this index is not bounds-checked.
- `duration_ms`: Duration in milliseconds. Conversion to 60 Hz frames truncates fractional frames.
- *Returns*: 1.
- Configure waypoints first; use EventArrowWait before dependent work.

  `EventArrowWait()` — Suspends the script while map-event arrows are animating.

- *Returns*: 1 in ordinary playback; 0 during event skipping.

  `EventQuake(strength, period_ms, cycles)` — Starts a repeating camera shake.

- `strength`: Shake intensity; 0 produces no sustained shake.
- `period_ms`: Length of one shake cycle in milliseconds, truncated to frames; a converted value of 0 becomes one frame.
- `cycles`: Positive number of cycles; 0 or negative repeats until stopped.
- *Returns*: 1.
- The second argument is one cycle’s duration, not the total duration. EventQuakeStop ends a repeating shake.

  `EventQuakeStop()` — Requests the active camera shake to stop.

- *Returns*: 1.

  `FRAME2MSEC(frames)` — Converts a 60 Hz frame count to milliseconds.

- `frames`: Frame count, typically nonnegative.
- *Returns*: frames × 16.666666, truncated to an integer.

  `GetBattleType()` — Returns the flag word of the current or most recent battle.

- *Returns*: Bit flags. Bit 0x80000000 is set when the battle was started by NetuzoBattle with its event_battle argument; the shared boss and death-talk helpers test it. Other bits are internal battle state.

  `intplGetValue(curve, start, end, progress, total)` — Computes one interpolated value without starting an animation.

- `curve`: 0 linear; 1 quadratic ease-in; 2 cubic ease-in; 3 quartic ease-in; 4 quadratic ease-out; 5 cubic ease-out; 6 quartic ease-out; 7–9 oscillating/bouncing curves; 10 cosine ease-in/out; 11 sine ease-out; 12 cosine ease-in.
- `start`: Value at progress 0.
- `end`: Value at progress total.
- `progress`: Current progress; use the same units as total, normally within 0–total.
- `total`: Total progress span. Zero returns end.
- *Returns*: Interpolated value truncated to an integer; unsupported curve gives 0 when total is nonzero.
- Does not clamp progress. Oscillating modes 8–9 also depend on the absolute time scale.

  `MSEC2FRAME(duration_ms)` — Converts milliseconds to 60 Hz frames.

- `duration_ms`: Duration in milliseconds. Conversion to 60 Hz frames truncates fractional frames.
- *Returns*: duration_ms ÷ 16.666666, truncated to an integer.

  `NetuzoBattle(attacker, defender, event_battle)` — Resolves and starts a scripted combat exchange between two actors, then suspends the script for the battle process.

- `attacker`: Valid attacker unit handle; no null-unit guard.
- `defender`: Valid defender unit handle; no null-unit guard.
- `event_battle`: 0 clears the event-battle flag; nonzero sets it. Shared battle/death dialogue helpers test this flag to choose their event behavior.
- *Returns*: 1.
- Use NetuzoInit and NetuzoSet first when forcing strikes. Requires valid combatants and battle resources. This changes combat state; it is not a visual-only preview.

  `NetuzoInit()` — Clears all 32 scripted-strike override slots and resets the scripted-battle counters.

- *Returns*: 1.
- Call before configuring a new scripted battle; prevents stale overrides from the preceding sequence.

  `NetuzoSet(strike_index, outcome_flags, effect_flags)` — Configures outcome and combat-effect overrides for one scripted strike.

- `strike_index`: Zero-based strike slot, 0–31. No bounds check.
- `outcome_flags`: 0 uses normal hit/critical resolution; bit 1 forces a hit, bit 2 a critical, bit 4 a miss. Hit takes precedence over critical, which takes precedence over miss.
- `effect_flags`: Combat-effect bitmask, not damage. 0 = no forced effects; 0x0001 halves damage rounded up; 0x0002 heals attacker by damage; 0x0004 uses half defender defense; 0x0010 forces lethal-strength damage; 0x0080 prevents counter; 0x0100 sets damage to zero; 0x0200 sets damage to half defender HP; 0x0400 prevents this strike killing the defender. Additional special-skill flags should be retained from the matching battle.
- *Returns*: 1.
- Combine effects only deliberately; later damage modifiers can change earlier ones. Set the combatants’ stats/equipment to control ordinary damage.

  `SetEventBattle(enabled)` — Selects the special event presentation branch when the next battle animation is initialized.

- `enabled`: 0 uses the ordinary presentation selection; nonzero overrides it with event presentation mode.
- *Returns*: 1.
- This is a shared scene setting, not a call that starts combat or forces damage. Set before NetuzoBattle and restore 0 after the staged battle.

## Chapter state, flags and difficulty

  Turn, phase, money, difficulty, named flags, chapter results and the event system's own state.

  `_intr()` — Runs the chapter-checkpoint save sequence and suspends the calling script until it finishes.

- *Returns*: 1 when scheduled; read MCResult for the card-operation status.
- Opens the memory card, writes the chapter checkpoint if opening succeeded, then closes it. Use only at a valid chapter save point; this is not a harmless pause.

  `AchieveSet(message_id, amount)` — Records one line of the chapter's bonus-experience results: a label and an amount. Used inside achievement (type 12) functions, which the game runs at chapter end; each function that runs fills the next line.

- `message_id`: Message ID of the line's label, such as Ms_ach_02_turn.
- `amount`: Bonus experience for this line.
- *Returns*: 1.
- The amount is halved on Maniac and multiplied by 1.5 on Easy (rounded down). This is not gold; use BMSetMoney for money.

  `BMGetChapter()` — Returns the current chapter number.

- *Returns*: Chapter number (Prologue = 1, the internal file number).

  `BMGetMoney()` — Returns the party's gold.

- *Returns*: Gold amount.

  `BMGetPhase()` — Returns whose phase it is.

- *Returns*: Phase force: 0 player, 1 enemy, 2 allied, 3 other.

  `BMGetTurn()` — Returns the turn number.

- *Returns*: Current turn (1 on the first turn).

  `BMGetValue(field_index)` — Reads a signed 16-bit field from battle-map state.

- `field_index`: Halfword index in battle-map state. Use an index from an existing matching chapter; this is not a named flag slot.
- *Returns*: Signed value from -32768 through 32767.
- Advanced raw accessor; no bounds check. Prefer a dedicated accessor when available.

  `BMSetMoney(value)` — Sets the party's gold.

- `value`: New gold amount; anything above 9,999,999 is stored as 9,999,999.
- *Returns*: The value passed in (before the cap).
- The difference is also added to the game's lifetime 'gold earned' or 'gold spent' totals.

  `BMSetPhase(force)` — Overwrites the current-phase value.

- `force`: Phase force 0–3.
- *Returns*: No meaningful value; call it for its effect.
- Only changes the stored value: no phase change, phase banner or phase events happen.

  `BMSetTanto(player_control, enemy_control, force_2_control, force_3_control)` — Sets who controls each of the four active map forces.

- `player_control`: Control mode: 0 none, 1 player control, 2 computer control.
- `enemy_control`: Control mode: 0 none, 1 player control, 2 computer control.
- `force_2_control`: Control mode: 0 none, 1 player control, 2 computer control.
- `force_3_control`: Control mode: 0 none, 1 player control, 2 computer control.
- *Returns*: 1.
- Changes shared phase/control state. Restore all four values for the chapter when leaving a staged sequence.

  `BMSetTerm(term_index, text)` — Replaces one battle-map term string.

- `term_index`: Term slot from the original chapter; slots hold 12 bytes each.
- `text`: At most 11 encoded bytes plus the string terminator. Null leaves the term unchanged.
- *Returns*: 1.
- Copies without a length check. Use short ASCII text or count encoded bytes, not Unicode characters.

  `BMSetTurn(turn)` — Overwrites the turn counter.

- `turn`: New turn number (kept as a 16-bit value).
- *Returns*: No meaningful value; call it for its effect.
- Turn-based events are checked against the new value from the next turn change; none fire immediately.

  `BMSetValue(field_index, value)` — Writes a 16-bit field in battle-map state.

- `field_index`: Same halfword index used by BMGetValue; not bounds-checked.
- `value`: Value to store. Only the low 16 bits are retained.
- *Returns*: The supplied value, before truncation.
- Do not invent indices. This edits shared chapter state.

  `clr(flag_name)` — Clears a flag.

- `flag_name`: Registered flag name.
- *Returns*: 0.
- An unregistered name does nothing.

  `Complete18(part)` — Ends a multipart chapter segment and selects its next chapter-flow state.

- `part`: 1 selects continuation state 5; 2 selects 6; 3 selects 7. Other values select 0.
- *Returns*: 1.
- Special-purpose chapter 18 flow; not a general victory replacement.

  `Easy()` *(not registered)* — Always returns 0 in this US build; do not use this as a working difficulty test.

- *Returns*: 0, always.
- Use GetRank or a supported difficulty helper instead.

  `GCST()` — Returns the event system's state flags.

- *Returns*: Bit flags: 0x1 the current event is being skipped; 0x2 the current conversation is being skipped; 0x4 skipping is disabled; 0x10 the event is suspended (SuspendEvent or a tutorial dialog); 0x1000 outer link enabled (SetOutLink); 0x2000 finale mode (BeginFinale). Other bits belong to the tutorial and menu code.
- Scripts normally test only bit 0x1, as the shared *_WhenNotEvtSkip helpers do.

  `get(flag_name)` — Reads a flag.

- `flag_name`: Registered flag name.
- *Returns*: 1 if set; 0 if clear or not registered.

  `GetLanguage()` — Returns the language ID. The US build has no language setting.

- *Returns*: 1, always.

  `GetRank()` — Returns the difficulty.

- *Returns*: 0 Normal, 1 Hard, 2 Maniac, 3 Easy (US build).

  `GetRnd(exclusive_max)` — Draws a random integer using the game random-number generator.

- `exclusive_max`: Positive upper bound; the result is smaller than this value.
- *Returns*: Integer from 0 through exclusive_max - 1.
- Consumes random state. Do not use zero or negative bounds.

  `GetTutorial()` — Reads whether tutorial help is enabled in configuration.

- *Returns*: 1 when enabled; 0 when disabled.

  `global(flag_name)` — Registers a campaign flag in the lowest free slot of the flag table and clears its bit. The game registers its campaign flags once at boot.

- `flag_name`: Flag name; any string.
- *Returns*: 1.
- Keep the registration order for save compatibility.

  `Hard()` — Tests for Hard difficulty.

- *Returns*: 1 on Hard (1); 0 otherwise.

  `IsE3Version()` — Tests the E3/demo-build condition in this US executable.

- *Returns*: 0, always.

  `Maniac()` — Tests for Maniac difficulty.

- *Returns*: 1 on Maniac (2); 0 otherwise.

  `MCResult()` — Reads the last memory-card operation status.

- *Returns*: Memory-card status code; it is not a boolean.
- Use only in a matching save/load workflow after its asynchronous operation completes. This call does not start a save.

  `Normal()` — Tests for Normal or Easy difficulty.

- *Returns*: 1 on Normal (0) or Easy (3); 0 otherwise.

  `NormalOnly()` *(not registered)* — Always returns 0 in this US build; do not use this as a working difficulty test.

- *Returns*: 0, always.
- Use GetRank or a supported difficulty helper instead.

  `regist(flag_name)` — Registers a chapter flag in the highest free slot of the 96-slot flag table. The slot's bit is left as it is (chapter start clears these slots).

- `flag_name`: Flag name; any string.
- *Returns*: 1.
- Saves store flag bits by slot, not by name, so keep the registration order when editing a chapter's Startup.

  `RegistGlobalFlags()` *(startup.cmb)* — Calls the native global registration operation 22 times in fixed order for the original campaign flag list, including repeated reserved names.

- *Returns*: 0 (implicit return); do not interpret this as failure.
- Boot-time setup, not a per-turn reset. Reordering changes saved-bit interpretation; see named flags.

  `set(flag_name)` — Sets a flag.

- `flag_name`: Registered flag name.
- *Returns*: 0.
- An unregistered name does nothing.

## Waiting, skipping and script control

  Waits, the player's event skip, engine processes and script files.

  `_pldone()` — Tests whether files queued for loading (RectPreLoad, PreLoad) are ready.

- *Returns*: 1 when nothing is still loading; 0 otherwise.
- PreLoadWait loops on this.

  `ArcFree(resource_path)` — Releases one reference to a relocatable game resource.

- `resource_path`: Game resource path, for example "mess/tut.m". Use lowercase and the same path for its matching load/release.
- *Returns*: 1.
- Keep load and release ownership balanced. ArcFree may lowercase the supplied path in place. Do not release a resource while another sequence still uses it.

  `ArcLoad(resource_path)` — Loads a relocatable game resource.

- `resource_path`: Game resource path, for example "mess/tut.m". Use lowercase and the same path for its matching load/release.
- *Returns*: 1.
- Keep load and release ownership balanced. ArcFree may lowercase the supplied path in place. Do not release a resource while another sequence still uses it.

  `CmFreeScript()` — Unloads the most recently loaded script file and removes its named functions.

- *Returns*: 1; 0 if no script is loaded.
- Always the last one loaded: there is no name argument.

  `CmLoadScript(script_path)` — Loads a CMB script module and makes its exported functions available.

- `script_path`: Existing game resource path to a .cmb module. Use the path form already used by the project’s module-loading sequence.
- *Returns*: 1.
- Load before calling its exports; free modules in reverse load order with CmFreeScript.

  `CmSleepScript(module_name)` — Suspends a module’s event enumeration and temporarily removes its exported functions.

- `module_name`: Name stored in the loaded CMB header. Empty string or 0 selects the last-loaded module.
- *Returns*: 1 when a module is found; 0 if a named module is absent.
- The module stays allocated. CmWakeupScripts restores sleeping modules and their exports.

  `CmWakeupScripts()` — Wakes every script file put to sleep by CmSleepScript and makes its named functions callable again.

- *Returns*: No meaningful value; call it for its effect.

  `DisableSkip()` — Stops the player from skipping the current event until EnableSkip is called.

- *Returns*: 1.
- Death events and other critical scenes set the same flag. Always pair it with EnableSkip.

  `EnableSkip()` — Lets the player skip the current event again.

- *Returns*: 1.
- Undoes DisableSkip. It does not start a skip.

  `PreLoadWait()` *(startup.cmb)* — Yields repeatedly while _pldone() equals zero.

- *Returns*: 0 (implicit return); do not interpret this as failure.
- Exact resource coverage belongs to _pldone's native implementation.

  `ProcExists(process_name)` — Tests whether an engine process with a given name is running.

- `process_name`: Process name such as E_PadActor or E_TurnToken (not a script function).
- *Returns*: Nonzero if one is running; 0 otherwise.

  `ProcKill(process_name)` — Stops every engine process with a given name.

- `process_name`: Process name such as E_Popup.
- *Returns*: 0.
- Stopping a process the game still needs can break the scene.

  `ResumeEvent()` — Continues the event frozen by SuspendEvent.

- *Returns*: No meaningful value; call it for its effect.

  `SuspendEvent()` — Freezes the running event so another script (a tutorial) can run, saving the event's state.

- *Returns*: No meaningful value; call it for its effect.
- Pair it with ResumeEvent. The camera is protected from map input while suspended.

  `WaitF(frames)` — Pauses the script for a number of frames (60 per second).

- `frames`: Frame count. 1 or less waits until the next frame.
- *Returns*: 1; 0 while the event is being skipped.
- While the event is being skipped it does not wait.

  `WaitM(duration_ms)` — Pauses the script for a time in milliseconds.

- `duration_ms`: Milliseconds; converted to frames by dividing by 16.67 and rounding down. Under 34 ms waits a single frame.
- *Returns*: 1; 0 while the event is being skipped.
- While the event is being skipped it does not wait.

## Tutorials

  The tutorial player: freezing the game, scripted controller input, tutorial dialogs and settings.

  `_bmsini()` — Resets the chapter for a tutorial: chapter number 0 (so the convoy is available), turn 1, the player controls force 0 and the computer forces 1–3, 1,000 gold, chapter flags and gf_complete/gf_gameover cleared, no units, empty convoy, no forge records, map state cleared.

- *Returns*: 1.
- Called by TutorialInit after _seqini.

  `_cmb_mess_load(script_path, message_path)` — Loads a script file and a message file together (the step behind TutEntryCommon).

- `script_path`: Path of the .cmb file, such as scripts/c80.cmb.
- `message_path`: Path of the message file; the helper passes mess/tut.m.
- *Returns*: 1.

  `_pa(command)` — Plays a scripted controller input (the 'pad actor' that moves the cursor and presses buttons in tutorials). Each character is one step: a one-frame press, then a pause until the next step.

- `command`: Step characters: 1–4 and 6–9 press the control stick and D-pad in the numeric-keypad direction (8 up, 2 down, 4 left, 6 right, 7/9/1/3 diagonals); A, B, X, Y, Z, L, R press that button; S presses Start; any other character (such as 5 or a space) presses nothing. < halves and > doubles the step length (16 frames at first) without using a step.
- *Returns*: 1.
- The player's real input is ignored while it plays. TutPadActor calls this and waits while E_PadActor runs. Example: "66A" moves right twice, then presses A, one step (16 frames) apart.

  `_seqini()` — Clears the map for a tutorial: removes conversations, images, scripted input, the preparations, AI phase and phase banner, the notice frame and the unit models.

- *Returns*: 1.
- First step of TutorialInit.

  `_tr()` — Continues a held tutorial conversation (the step behind TutTalkResume).

- *Returns*: 1.
- Unlike TalkResume it does not pause the script: the helper waits with TalkExist.

  `_tt(message_id)` — Starts a tutorial conversation with a message (the step behind TutTalkEvent).

- `message_id`: Message ID in a loaded message file, not literal text.
- *Returns*: 1.
- Unlike TalkEvent it does not pause the script: the helper waits with TalkExist.

  `Comeback()` — Consumes the current event skip/cancel state and performs its cleanup.

- *Returns*: 1 when skip/cancel cleanup ran; 0 when there was nothing to consume.
- This changes state. Do not replace it with a read-only condition or call repeatedly to “peek.”

  `ComebackFunc()` *(startup.cmb)* — SuspendEvent; yield; MapFree; yield; external Startup; TutorialResume.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `Config_TutGet_sfx_vol()` — Reads the stored tutorial sound-effect volume byte.

- *Returns*: Stored volume value.

  `Config_Tutorial()` — Resets the tutorial configuration block to defaults, including internal difficulty ID 1.

- *Returns*: No useful script result; call for its side effect.
- This is not a “show tutorial” toggle. It also overwrites difficulty and other settings; use the individual setters for a small change.

  `Config_TutSet_otheridoshowing(enabled)` — Sets the tutorial setting for other-unit movement display.

- `enabled`: Exactly 1 enables it; every other value disables it.
- *Returns*: No useful script result; call for its side effect.

  `Config_TutSet_sfx_vol(volume)` — Stores the tutorial sound-effect volume and applies the settings.

- `volume`: Volume byte; use the configuration’s existing range. Values are truncated to 8 bits.
- *Returns*: No useful script result; call for its side effect.

  `Config_TutSet_terInfo(enabled)` — Sets the tutorial setting for terrain information.

- `enabled`: Exactly 1 enables it; every other value disables it.
- *Returns*: No useful script result; call for its side effect.

  `Config_TutSet_unitInfo(enabled)` — Sets the tutorial setting for unit information.

- `enabled`: Exactly 1 enables it; every other value disables it.
- *Returns*: No useful script result; call for its side effect.

  `Config_TutSet_XinfoPage(page)` — Sets the tutorial information-page selection.

- `page`: Page index stored as an 8-bit value; use a page available in this tutorial.
- *Returns*: No useful script result; call for its side effect.

  `GameBind()` — Freezes the map's normal game flow (phases, cursor, menus) while the script works.

- *Returns*: 1.
- Undo with GameUnbind. The tutorial helpers wrap their steps in this pair.

  `GameUnbind()` — Lets the map's game flow continue after GameBind.

- *Returns*: 1.

  `PadResetMask(buttons)` — Removes buttons from the input mask.

- `buttons`: Case-sensitive string: A B X Y Z L R are buttons, S is Start; 4/6/8/2 are left/right/up/down. Concatenate characters, e.g. "AB8". "*" selects every bit; other characters are ignored.
- *Returns*: 0.

  `PadSetMask(buttons)` — Adds buttons to the input mask used by event/tutorial control.

- `buttons`: Case-sensitive string: A B X Y Z L R are buttons, S is Start; 4/6/8/2 are left/right/up/down. Concatenate characters, e.g. "AB8". "*" selects every bit; other characters are ignored.
- *Returns*: 0.
- Pair with PadResetMask to restore those buttons when the sequence ends.

  `QueryLesson(lesson_name)` — Tests whether the active lesson has the given name.

- `lesson_name`: Exact name of the active tutorial lesson.
- *Returns*: 1 on a match; 0 if no matching lesson is active.

  `taikitk()` — Starts a waiting token that lasts until a unit's next Wait command (E_TaikiToken).

- *Returns*: 1.
- The tutorial helpers TutWaitForNextTaiki, TutWaitForNextTurn and TutWaitForNextTurnAfter call it and wait while the token exists.

  `td(message_id)` — Opens a tutorial dialog with a message and pauses the script until it closes.

- `message_id`: Message ID in a loaded message file, not literal text.
- *Returns*: 0.
- A message with a line break uses the two-line layout. TutorialDialog calls this, yields once, then calls tde.

  `tde()` — Sets the 'event suspended' state flag again after a tutorial dialog cleared it (the last step of TutorialDialog).

- *Returns*: 1.

  `turnatk()` — Starts a waiting token that lasts until the next end of turn (E_TurnAToken).

- *Returns*: 1.
- The tutorial helpers TutWaitForNextTaiki, TutWaitForNextTurn and TutWaitForNextTurnAfter call it and wait while the token exists.

  `turntk()` — Starts a waiting token that lasts until the next turn change (E_TurnToken).

- *Returns*: 1.
- The tutorial helpers TutWaitForNextTaiki, TutWaitForNextTurn and TutWaitForNextTurnAfter call it and wait while the token exists.

  `TutBasesCreate()` *(startup.cmb)* — Yields until "E_BMapPlph" exists, calls TutorialBasesCreate, then yields while "E_BasesToken" exists.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutBasesDelete()` *(startup.cmb)* — Calls TutorialBasesDelete.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutEntryCommon(script_path, entry_name)` *(startup.cmb)* — Sleeps the tail module with CmSleepScript(""), calls _cmb_mess_load(script_path,"mess/tut.m"), then TutorialCall(entry_name).

- `script_path`: Tutorial CMB resource path, such as scripts/c80.cmb.
- `entry_name`: Named tutorial entry function in the loaded module.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutorialBasesCreate()` — Opens the base menu inside a tutorial.

- *Returns*: 1.

  `TutorialBasesDelete()` — Closes the base menu opened by TutorialBasesCreate.

- *Returns*: 1.

  `TutorialCall(entry_name)` — Starts a named function of a loaded tutorial script and stops the AI phase.

- `entry_name`: Name of a function in a loaded script, such as tut_02_Visit.
- *Returns*: 1 if the function exists; 0 otherwise.

  `TutorialDialog(message_id)` *(startup.cmb)* — Calls td(message_id), yields once, then tde().

- `message_id`: Message ID in a currently loaded message resource; not literal dialogue text.
- *Returns*: 0 (implicit return); do not interpret this as failure.
- td pauses the script until the dialog closes; tde then marks the event as suspended.

  `TutorialForget(tutorial_id)` — Clears a tutorial’s learned mark.

- `tutorial_id`: Bit index of an existing tutorial entry; use its numeric ID, not its script export name.
- *Returns*: 1.
- Learned status and unlocked status are separate.

  `TutorialIn(script_path, entry_name)` *(startup.cmb)* — Fades with mode 3 for 266 and waits; AllPush; MapFree; TutEntryCommon; SuspendEvent; yields once.

- `script_path`: Tutorial CMB path forwarded to TutEntryCommon.
- `entry_name`: Tutorial entry name forwarded to TutEntryCommon.
- *Returns*: 0 (implicit return); do not interpret this as failure.
- Use with the matching exit/restoration flow; it changes module and map ownership.

  `TutorialInit()` *(startup.cmb)* — Enables skip, calls _seqini, kills "E_Popup", calls _bmsini, then external Startup and RegistLocationTT.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutorialInitialize()` — Starts tutorial initialization and suspends the calling script until it completes.

- *Returns*: 1.

  `TutorialLearn(tutorial_id)` — Marks a tutorial as learned.

- `tutorial_id`: Bit index of an existing tutorial entry; use its numeric ID, not its script export name.
- *Returns*: 1.
- Learned status and unlocked status are separate.

  `TutorialLock(tutorial_id)` — Locks a tutorial.

- `tutorial_id`: Bit index of an existing tutorial entry; use its numeric ID, not its script export name.
- *Returns*: 1.
- Learned status and unlocked status are separate.

  `TutorialOut()` *(startup.cmb)* — Frees "mess/tut.m", frees the last-loaded script, wakes sleeping scripts and resumes the suspended event.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutorialResume()` — Returns to the tutorial menu after a tutorial ends (the last step of ComebackFunc).

- *Returns*: No meaningful value; call it for its effect.

  `TutorialResumeOut()` *(startup.cmb)* — MapFree; yield; AllPop; MapReload; UnitDispReload; external Startup; MapUpdate; Fade(2,266); FadeWait.

- *Returns*: 0 (implicit return); do not interpret this as failure.
- Runs the chapter's Startup again, so flag registration order must stay stable.

  `TutorialSallyCreate()` — Opens the preparations screen inside a tutorial.

- *Returns*: 1.

  `TutorialSallyDelete()` — Closes the preparations screen opened by TutorialSallyCreate.

- *Returns*: 1.

  `TutorialUnlock(tutorial_id)` — Unlocks a tutorial.

- `tutorial_id`: Bit index of an existing tutorial entry; use its numeric ID, not its script export name.
- *Returns*: 1.
- Learned status and unlocked status are separate.

  `TutPadActor(command)` *(startup.cmb)* — Calls _pa(action), then yields while process "E_PadActor" exists.

- `command`: Scripted input string passed to _pa; see _pa for its characters.
- *Returns*: 0 (implicit return); do not interpret this as failure.
- The command string is passed to _pa unchanged; use strings from the vanilla tutorial scripts.

  `TutPreLoadWait()` *(startup.cmb)* — Calls GameBind, externally invokes PreLoadWait, then GameUnbind.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutSallyCreate()` *(startup.cmb)* — Yields until "E_BMapPlph" exists, calls TutorialSallyCreate, then yields while "E_SallyToken" exists.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutSallyDelete()` *(startup.cmb)* — Calls TutorialSallyDelete.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutTalkEvent(message_id)` *(startup.cmb)* — Calls GameBind, _tt(message_id), yields while TalkExist(), then GameUnbind.

- `message_id`: Message ID in a currently loaded message resource; not literal dialogue text.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutTalkResume()` *(startup.cmb)* — Calls GameBind, _tr(), yields while TalkExist(), then GameUnbind.

- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutWaitF(frames)` *(startup.cmb)* — Calls GameBind, yields once per loop iteration until the counter reaches frames, then GameUnbind.

- `frames`: Loop/yield count. Nonpositive values produce no loop iterations.
- *Returns*: 0 (implicit return); do not interpret this as failure.

  `TutWaitForNextTaiki()` *(startup.cmb)* — Calls taikitk(), then yields while process "E_TaikiToken" exists.

- *Returns*: 0 (implicit return); do not interpret this as failure.
- The token ends at the player's next Wait command.

  `TutWaitForNextTurn()` *(startup.cmb)* — Calls turntk(), then yields while process "E_TurnToken" exists.

- *Returns*: 0 (implicit return); do not interpret this as failure.
- The token ends at the next turn change.

  `TutWaitForNextTurnAfter()` *(startup.cmb)* — Calls turnatk(), then yields while process "E_TurnAToken" exists.

- *Returns*: 0 (implicit return); do not interpret this as failure.
- The token ends at the next end of turn.

  `TutWaitM(duration_ms)` *(startup.cmb)* — Calls GameBind, computes duration_ms * 60 / 1000 with integer arithmetic, yields that many iterations, then GameUnbind.

- `duration_ms`: Milliseconds, converted with the fixed factor 60/1000 (one yield per frame).
- *Returns*: 0 (implicit return); do not interpret this as failure.
- duration_ms × 60 / 1000 yields, one frame each.

## Debug and leftovers

  Developer output and functions that do nothing in the retail game.

  `ArenaDump()` — Prints memory-arena usage to debug output.

- *Returns*: No useful script result; call for its side effect.
- Useful for debugging resource-heavy scripts; it does not display an in-game menu.

  `dump()` — Prints all eight force lists and their units to debug output.

- *Returns*: No useful script result; call for its side effect.
- Useful for checking unit membership; no gameplay changes.

  `report(text)` — Writes text to the game’s debug-report output.

- `text`: Plain diagnostic string. Avoid printf format placeholders because no additional formatting arguments can be supplied.
- *Returns*: 1 for an accepted string; 0 otherwise.
- Does not show an in-game dialogue box.
