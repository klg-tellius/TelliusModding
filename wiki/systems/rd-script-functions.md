---
id: "rd-script-functions"
title: "Script Functions (Radiant Dawn)"
description: "Every native function a Radiant Dawn event script can call"
games: ["radiant-dawn"]
section: "systems"
article_type: "system-reference"
tags: ["Structure","Radiant Dawn"]
aliases: ["tellius_archive.html#/rd-script-functions"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/rd-script-functions.md"
---
# Script Functions (Radiant Dawn)

*Every native function a Radiant Dawn event script can call*

Every native function Radiant Dawn's event scripts can call, grouped by the part of the game that registers it, with what it does in the US game. There are 656 natives; `startup.cmb` adds 511 helper functions written in script. <span class="confidence confidence--confirmed">engine</span>

!!! info "Conventions"
    **Units** are numeric handles (the unit's slot + 1); 0 means no unit. **Forces** 0-10. **Difficulty**: 0 Normal, 1 Hard, 2 Maniac, 3 Easy. **Skipping**: while the player skips an event, calls that animate apply their end state at once and sound calls are ignored. A call that suspends the script resumes it when its process ends. Descriptions of functions that Path of Radiance also has follow [Script Functions](./script-functions.md) where the two games behave the same.

## General (279)

  Camera focus, flags, conversations, message arguments, images (rectangles), the world map, portraits outside conversations, fades, music, sound, voices, special terrain, deployment, script threads and version switches.

  `_gi(unit, item_id)` — Gives an item to a unit and shows the result window (the step behind UnitGetItemShowing).

  `_gs(unit, function)` — Starts a process that runs the named script function for the unit (the "go script" helper); 0 if the name is unknown.

  `_intr()` — Runs the chapter-checkpoint save sequence and suspends the calling script until it finishes.

  `_pldone()` — Tests whether files queued for loading (RectPreLoad, PreLoad) are ready.

  `AddKizna(pid1, pid2, amount)` — Adds amount (clamped to -128..127) to the bond between two characters; 0 if either PID is unknown.

  `AddTT(x, y, type, subtype, value_1, value_2)` — Adds a raw entry to the map's special-terrain list.

  `AllPop()` — Restores the game state saved by AllPush and frees the buffer.

  `AllPush()` — Saves the whole game state into the temporary buffer (party data, camera, every unit, convoy, forge records and map state), then resets units, chapter flags, map state, convoy and forge records.

  `AllUnitEscape()` — Removes every unit of forces 0–3 from the map: carried units are dropped first, player units go to the reserve marked as escaped, all other units are deleted.

  `ArenaDump()` — Debug stub: does nothing in Radiant Dawn.

  `BeginFinale()` — Enables finale mode and its input mask for A/B/X/Y/Z/L/R/Start.

  `BGMCont(channel, duration_ms)` — Resumes a channel paused by BGMMute and fades it back to its remembered volume.

  `BGMFadeIn(channel, bgm_id, duration_ms)` — Starts a track on a music channel, fading it in from silence to full volume. If any channel is already playing this same track, nothing changes.

  `BGMFadeOut(channel, duration_ms)` — Fades a playing channel to silence and stops it.

  `BGMMute(channel, duration_ms)` — Fades a playing channel to silence and pauses it, remembering its volume and position so BGMCont can bring it back.

  `BGMPlay(channel, bgm_id)` — Starts a track on a music channel at full volume. If any channel is already playing this same track, nothing changes. The channel's previous track is stopped.

  `BGMPlayAlways(channel, bgm_id)` — Plays a track on a channel even if it is already playing; channel 0 also marks the map music as started.

  `BGMPlayVol(channel, bgm_id, volume)` — Starts a track on a music channel at the given volume.

  `BGMQuietOff(channel)` — Ends the music 'quiet' state started by BGMQuietOn, restoring the level over about a quarter of a second.

  `BGMQuietOn(channel)` — Starts lowering the music for a dialogue box or a reward window (the game's music 'quiet' state), over about a quarter of a second.

  `BGMResume(duration_ms)` — Restores the music after an event: fades the volume back and resumes the paused channels (one argument in Radiant Dawn).

  `BGMSetVol(channel, volume, duration_ms)` — Changes a channel's volume gradually.

  `BGMSilentOff(duration_ms)` — Fades the music volume group back to full.

  `BGMSilentOn(duration_ms)` — Fades the music volume group to silence.

  `BGMStop(channel)` — Stops a playing channel almost immediately (a one-millisecond fade).

  `ChapterMoviePlay(chapter)` — Plays the movie of a chapter and pauses the script until it ends.

  `Check()` — Tests whether a base-conversation event is being evaluated for availability rather than being played.

  `CheckAttackable(unit)` — Tests whether this unit can reach a position from which its equipped weapon can attack an eligible enemy.

  `clr(flag_name)` — Clears a flag.

  `ClrTT(x, y, type)` — Removes the map trap/tile effect of that type at (x, y) (with a 60-frame fade).

  `Comeback()` — Consumes the current event skip/cancel state and performs its cleanup.

  `CompleteSubChapter(route)` — Ends a branching chapter; route 1, 2 or 3 picks continuation state 5, 6 or 7 (others 0) and sets matching route bits in the game state.

  `CreateVMCThread(function)` — Runs a script function by name in a new script thread (own 256-byte stack); returns the thread handle.

  `CreateVMCThread1(function, a)` — CreateVMCThread passing one argument.

  `CreateVMCThread2(function, a, b)` — CreateVMCThread passing two arguments.

  `CreateVMCThread3(function, a, b, c)` — CreateVMCThread passing three arguments.

  `CreateVMCThread4(function, a, b, c, d)` — CreateVMCThread passing four arguments.

  `DDExtraFlagAmlitaOn()` — Turns on Library extra entry 0x7F (Almedha).

  `DDFlagCheck(flag)` — Whether a Library (dictionary.bin) entry flag DF_... is on.

  `DDFlagOff(flag)` — Turns a Library entry flag off.

  `DDFlagOn(flag)` — Turns a Library entry flag on (unlocks the entry).

  `DebugDisplayCtrl(arg0, arg1)` — Debug stub; returns 1.

  `DefaultDieTalk()` — Looks up and starts the defeated unit’s default death message when that message exists. For player or inactive units it also selects death music.

  `DefaultEscapeTalk()` — Looks up and starts the current acting unit’s default escape message when available.

  `Dialog(message_id)` — Opens a message dialog and suspends this script until the dialog process releases it.

  `Dialog2Items(choice_1, choice_2)` — Opens a choice dialog with 2 entries and suspends the calling script.

  `Dialog3Items(choice_1, choice_2, choice_3)` — Opens a choice dialog with 3 entries and suspends the calling script.

  `Dialog3ItemsWithSt(choice_1, choice_2, choice_3, state_1, state_2, state_3)` — Three-choice dialog where each choice has a state 0-3 (enabled, greyed...); suspends the script; read DialogResult after.

  `Dialog4Items(choice_1, choice_2, choice_3, choice_4)` — Opens a choice dialog with 4 entries and suspends the calling script.

  `DialogDirect(message_id)` — Opens a message dialog and suspends this script until the dialog process releases it.

  `DialogGetRes()` — Reads the last dialog result.

  `DialogResult()` — Reads the last dialog result.

  `DialogSetDefault(selection)` — Sets the default selection byte used by dialogs.

  `DialogTutorial(message_id)` — Opens a tutorial dialog and suspends this script until the dialog process releases it.

  `DisableSkip()` — Stops the player from skipping the current event until EnableSkip is called.

  `DispFreeWholeForce(force)` — Releases display resources for every actor in a force list.

  `DispLoadWholeForce(force)` — Loads display resources for every actor in a force list.

  `DispPreLoadWholeForce(force)` — Queues battle-animation assets for every actor in a force list.

  `DivideForce()` — Opens the army-splitting screen (part 3 and 4 army assignment) and suspends the script.

  `DumpUnit()` — Debug stub, does nothing.

  `Easy()` — 1 on the difficulty whose setting byte is 3 (Easy), else 0.

  `EnableSkip()` — Lets the player skip the current event again.

  `EndFinale()` — Disables finale mode and its input mask for A/B/X/Y/Z/L/R/Start.

  `ENVNoisyOff(duration_ms)` — Fades the ambient group back to normal.

  `ENVNoisyOn(duration_ms)` — Fades the ambient group louder.

  `ENVPlay(sfx, volume)` — Starts an ambient loop; returns its channel, -1 when skipping or invalid.

  `ENVPlay3D(sfx, x, y, height, volume)` — Starts a positioned ambient loop at map tile (x, y); returns its channel or -1.

  `ENVQuietOff(duration_ms)` — Fades the ambient group back to full.

  `ENVQuietOn(duration_ms)` — Fades the ambient sound group to a low volume (one argument in Radiant Dawn).

  `ENVSetVol(channel, volume, duration_ms)` — Fades an ambient channel to volume (0-100).

  `ENVSilentOff(duration_ms)` — Fades the ambient group back to full after ENVSilentOn.

  `ENVSilentOn(frames)` — Silences the ambient (environment) sound.

  `ENVStop(channel, duration_ms)` — Fades out and stops an ambient channel.

  `FaceCreate(name, fid, x, y, fade_ms, flags)` — Shows a portrait outside a conversation (world map scenes); x is converted to 16:9 or world-map coordinates.

  `FaceDelete(name, fade_ms)` — Fades a FaceCreate portrait out and deletes it.

  `FaceDeleteImm(name)` — Deletes a FaceCreate portrait at once.

  `FaceDeleteImmAll()` — Deletes every FaceCreate portrait at once.

  `FaceMove(name, x, y, duration_ms, curve)` — Moves a FaceCreate portrait; curve 0 linear, 1 and 2 eased.

  `FacePreLoad(fid)` — Preloads a portrait for FaceCreate; ignored while skipping.

  `FaceSetBright(name, brightness, duration_ms)` — Fades a portrait's brightness.

  `Fade(mode, duration_ms)` — Starts a screen transition.

  `FadeIsBlackHolding()` — 1 while the screen is held black.

  `FadeIsWhiteHolding()` — 1 while the screen is held white.

  `FE8UnitCheckExistsByPID(pid)` — From the imported Path of Radiance clear data, the byte recorded for that character (0 when no data was imported or the character is not in it).

  `Flash(red, green, blue, appear_ms, disappear_ms)` — Starts a colored screen flash.

  `FlashWait()` — Suspends the script while the screen flash is transitioning.

  `Focus(x, y)` — Moves the map camera smoothly so it looks at the centre of a tile.

  `FocusHardWait()` — Like FocusWait, but waits until the camera is within 0.1 tile of its target point and 1 unit of its target angles and distance.

  `FocusWait()` — Waits until the map camera has nearly reached its target.

  `FRAME2MSEC(frames)` — Converts a 60 Hz frame count to milliseconds.

  `get(flag_name)` — Reads a flag.

  `GetButton(pad)` — Controller buttons held (pad driver call +0x34).

  `GetConfig(index)` — Option index 0 (two bits), 0 for other indexes.

  `GetFadeType()` — The current screen fade state (0 none, 2 and 5 are the black-out states REventStart tests).

  `GetFrame()` — The frame counter.

  `GetNumDiedBrothers()` — Number of allied units that died on this map.

  `GetNumDiedEnemies()` — Number of enemy units that died on this map.

  `GetNumDiedPlayers()` — Number of player units that died on this map.

  `GetNumDiedThirds()` — Number of other-army (third party) units that died on this map.

  `GetPress(pad)` — Controller buttons pressed this frame (call +0x48).

  `GetRank()` — The difficulty byte: 0 Normal, 1 Hard, 2 Maniac, 3 Easy (Radiant Dawn's numbering).

  `GetRelease(pad)` — Controller buttons released this frame (call +0x4C).

  `GetRepeat(pad)` — Controller buttons with auto-repeat (call +0x3C).

  `GetTime()` — The frame counter converted to milliseconds.

  `GetTT(x, y, type)` — The value of the tile effect of that type at (x, y), 0 if none.

  `GetTTCount(type)` — Number of tile effects of a type on the map.

  `global(flag)` — Registers a campaign flag in the lowest free slot of the 128-slot flag table and clears its bit.

  `GMapBGMPlay()` — Plays the world-map music of the current chapter (FUN_800684A0) on channel 0.

  `GMapBGMStop()` — Fades out the world-map music (1.5 s).

  `GMapBuild(gid)` — Opens a world map scene.

  `GMapCurveDarkOnOff(name, on)` — Darkens or restores a curve.

  `GMapCurveDispOnOff(name, on)` — Shows or hides a curve.

  `GMapCurveDraw(name)` — Draws a curve progressively; GMapCurveDrawWait waits for the end.

  `GMapCurveDrawInstant(name)` — Draws a curve at once.

  `GMapCurveDrawWait()` — Suspends the script until the current world map's curves finish drawing.

  `GMapCurveEntry(name)` — Registers a curve (an army's route line) on the current world map.

  `GMapCurveReset(name)` — Erases a drawn curve.

  `GMapFin(duration)` — Fades the world map in.

  `GMapFlagMarkOff(name)` — Hides a flag marker (one argument in Radiant Dawn).

  `GMapFlagMarkOffAll()` — Hides every flag marker (no argument in Radiant Dawn).

  `GMapFlagMarkOn(map_id, index, x, y, style)` — Creates or resets a flag marker on a world-map image.

  `GMapFout(duration)` — Fades the world map out.

  `GMapHazeOff(name)` — Hides a haze overlay.

  `GMapHazeOn(name)` — Shows a haze overlay on the world map.

  `GMapKill(gid)` — Closes the world map scene.

  `GMapMove(x, y, zoom_x, zoom_y, duration, curve)` — Scrolls the current world map so (x, y) is centred at the given zoom; instant while the event is skipped.

  `GMapMoveOffset(dx, dy, zoom_x, zoom_y, duration, curve)` — Scrolls the current world map by an offset.

  `GMapPointOff(name)` — Hides a point marker (one argument in Radiant Dawn).

  `GMapPointOffAll()` — Hides every point marker (no argument in Radiant Dawn).

  `GMapPointOn(name, x, y, size, color)` — Shows a named point marker on the world map (Path of Radiance took 6 arguments); ignored while skipping.

  `GMapPos(x, y)` — Sets the current world map's scroll position.

  `GMapRegionOff(name)` — Hides a region overlay (one argument in Radiant Dawn).

  `GMapRegionOffAll()` — Hides every region overlay (no argument in Radiant Dawn).

  `GMapRegionOn(map_id, index)` — Turns on the selected region overlay on a world-map image.

  `GMapSetCurrentGID(gid)` — Selects the world map (GID_...) the GMap* natives act on.

  `Hard()` — 1 on Hard (difficulty 1).

  `InitializeTT()` — Clears the map's tile-effect table (0x803CB770).

  `InstantFocus(x, y)` — Points the map camera at the centre of a tile at once.

  `intplGetValue(curve, start, end, progress, total)` — Computes one interpolated value without starting an animation.

  `IsConversationRoom()` — 1 while the conversation room (E_ConversationRoom) is running.

  `IsE3Version()` — Tests the E3/demo-build condition in this US executable.

  `IsExtraTutoIn()` — Always 0 in the retail game.

  `IsFaceEnable(name)` — Whether that FaceCreate portrait exists.

  `isFading()` — Tests whether a screen fade started by Fade is still running.

  `IsFinalVersion()` — Always 1 in the retail game.

  `isFlash()` — Tests whether the screen flash is in either transition phase.

  `IsGMapFlagMarkEnable(name)` — Whether a flag marker is shown.

  `IsGMapPointEnable(name)` — Whether a point marker is shown.

  `IsGMapRegionEnable(name)` — Whether a region overlay is shown.

  `IsInheritFE8Data()` — 1 when this game imported Path of Radiance clear data (game-state bit 0x1), else 0.

  `IsJPVersion()` — 0 on this (US) disc.

  `IsNOAVersion()` — 1 on this (US, Nintendo of America) disc.

  `IsNOEVersion()` — 0 on this (US) disc.

  `IsPrivateViewVersion()` — Always 0 in the retail game (a preview-build switch).

  `IsSFXPlay(sfx)` — Whether the sound effect is playing (0 while skipping).

  `IsShowVersion()` — Always 0 in the retail game (trade-show build switch).

  `IsVOICEPlay(voice)` — Whether the voice clip is playing (0 while skipping).

  `isWipe()` — Tests whether a wipe-in or wipe-out transition is active.

  `Join(pid, value)` — Adds the character to the party; the second argument (new in Radiant Dawn) is passed to the join routine FUN_8010C8EC.

  `JyokyoMapCapture()` — Captures the status-map display and suspends the script while capture completes.

  `JyokyoMapDelete()` — Deletes the status-map display.

  `JyokyoMapEnemyOn()` — Enables enemy markers on the status map.

  `JyokyoMapHide()` — Hides the status-map display.

  `JyokyoMapPlayerOn()` — Enables player markers on the status map.

  `JyokyoMapShow()` — Starts the status-map display.

  `KillVMCThread(thread)` — Stops a thread made by CreateVMCThread*; 0 for another handle.

  `Maniac()` — 1 on Maniac (difficulty 2).

  `MapEnvPause(name)` — Pauses a map environment animation (water, flags...).

  `MapEnvResume(name)` — Resumes a paused map environment animation.

  `MapUpdate()` — Recalculates the map's occupancy, movement ranges and danger areas after units or terrain changed.

  `MessSetIntArg(index, value)` — Sets numbered argument index of the next message to an integer.

  `MessSetPersonNameArg(index, unit)` — Sets numbered argument index of the next message to the unit's name.

  `MessSetStringArg(index, text)` — Sets numbered argument index of the next message to a string.

  `MindGetMoney(amount)` — Adds gold to the party and starts a reward notification associated with the current acting unit.

  `MoviePlay(path)` — Plays a movie file and pauses the script until it ends.

  `MSEC2FRAME(duration_ms)` — Converts milliseconds to 60 Hz frames.

  `MStoF(ms)` — Milliseconds to 60 Hz frames.

  `NetuzoBattle(attacker, defender, event_battle)` — Resolves and starts a scripted combat exchange between two actors, then suspends the script for the battle process.

  `NetuzoBG(name)` — Picks the scripted battle's background.

  `NetuzoDisableBGM()` — Keeps the scripted battle from changing the music.

  `NetuzoDisableFlatter()` — Turns off a flag (0x803C8E42) of the scripted battle.

  `NetuzoInit()` — Clears all 32 scripted-strike override slots and resets the scripted-battle counters.

  `NetuzoSet(slot, outcome, effect)` — Overrides one scripted strike of the next NetuzoBattle.

  `NetuzoSetD(slot, outcome, effect, damage)` — Like NetuzoSet for one scripted strike of a NetuzoBattle, with a forced damage value (12345 = none).

  `NetuzoSkill(on)` — Lets skills activate in the scripted battle.

  `NetuzoWeapon(slot, iid)` — Sets the weapon of a side in the scripted battle; 0 if the item is unknown.

  `NetuzoWeather(weather)` — Sets the scripted battle's weather.

  `Normal()` — 1 on Normal (difficulty 0) only; Radiant Dawn has a separate Easy().

  `PadResetMask(buttons)` — Removes buttons from the input mask.

  `PadSetMask(buttons)` — Adds buttons to the input mask used by event/tutorial control.

  `ProcExists(process_name)` — Tests whether an engine process with a given name is running.

  `ProcKill(process_name)` — Stops every engine process with a given name.

  `RectAdjustBoundary(rect_id, alignment)` — Aligns a rectangle’s source image inside the 608 × 448 layout area.

  `RectBuild(rect_id)` — Creates an image (rectangle) from its RID definition, attached to the current event. RID_GMAP_... names create a world-map view.

  `RectFadeIn(rect_id, frames)` — Fades in a rectangle.

  `RectFadeOut(rect_id, frames)` — Fades out a rectangle.

  `RectFadeOutDelete(rect_id, frames)` — Fades out and then deletes a rectangle.

  `RectGet(rect_id, property)` — Reads a rectangle property and truncates it to an integer.

  `RectGetDepth(rect)` — A rectangle's drawing depth, -1 if it does not exist.

  `RectKill(rect_id)` — Removes an image created by RectBuild or RectLeave.

  `RectKillAll()` — Deletes every rectangle (UI picture) the event created.

  `RectLeave(rect_id)` — Creates a rectangle/world-map image without attaching it to the current event as its parent.

  `RectMove(rect_id, focus_x, focus_y, scale_percent, frames, curve)` — Animates a rectangle/world-map image so a source point is centered at (304, 240) at the requested scale.

  `RectMoveOffset(rect_id, x, y, frames, curve)` — Animates a rectangle/world-map image to an explicit offset and restores its scale to 100%.

  `RectPreLoad(rect_id)` — Starts loading the image files of a RID definition, so a later RectBuild shows it without delay.

  `RectSet(rect_id, property, value)` — Sets a rectangle property immediately.

  `RectSetCurve(rect_id, property, curve, start, end, frames)` — Animates one rectangle property between two values.

  `RectSetDepth(rect, depth)` — Sets a rectangle's drawing depth; 0 if the rectangle does not exist.

  `RectSetPos(rect_id, x, y)` — Sets a rectangle or world-map image’s position immediately.

  `regist(flag)` — Registers a chapter flag in the highest free slot of the 128-slot flag table, leaving its bit as it is.

  `RemoveBackdrop()` — Removes the backdrop process.

  `RepairAllWeaponsWholeForce(force)` — Restores every weapon of a force's units to its full uses.

  `report(text)` — Writes text to the game’s debug-report output.

  `ResumeEvent()` — Continues the event frozen by SuspendEvent.

  `SallyAddByGroup(group)` — Adds the tiles of a group to the preparation screen's deployment tiles.

  `SallyAddByGroupRank(group)` — Adds deployment slots from a group, for the current difficulty.

  `SallyAddByPos(x, y)` — Appends a deployment-selection position.

  `SallyGetSurplus()` — Reads the deployment surplus recorded when the deployment-selection flow finishes.

  `SallySetByGroup(group)` — Replaces the preparation screen's deployment tiles with the tiles of a group.

  `SallySetByGroupRank(group)` — Sets the deployment slots from a deployment group, picking the group's entry for the current difficulty.

  `SallySetByPos(x, y)` — Clears the deployment-selection position list, then adds this position.

  `SaveMenu()` — Opens the save menu and suspends the script.

  `SelectAuxiliary(group)` — Starts the auxiliary-unit selection flow for a deployment group and suspends the calling script.

  `SelectAuxiliaryRank(group)` — Opens the auxiliary-unit selection for a group's entry on the current difficulty and suspends the script.

  `SelectSally()` — Opens the unit-selection (deployment) screen and suspends the script until it closes.

  `SelectSallyEx(mode)` — Opens the unit-selection screen in a mode and suspends the script.

  `set(flag_name)` — Sets a flag.

  `SetAvailableGrandOpening()` — Sets bit 0x20 of the system save state (unlocks the full opening movie).

  `SetBomber(x, y, value)` — Adds a bomber tile effect (type 0x0F).

  `SetClimb(x, y)` — Adds a climbable tile effect (type 0x0B: ladders/ropes).

  `SetConfig(index, value)` — Sets option index 0 (two bits of the play settings); other indexes do nothing.

  `SetFragile(x, y, hp)` — Adds a breakable terrain entry with the requested HP.

  `SetLava(x, y, a, b, c)` — Adds a lava tile effect (type 0x0E) with three parameters.

  `SetPit(x, y)` — Adds a pit terrain entry at the given tile.

  `SetPreSallyFlag(on)` — Sets or clears game-state bit 0x40 (the pre-deployment flag); 0 when no game state is loaded.

  `SetRock(x, y, direction, path_index)` — Adds a rolling-rock terrain entry connected to a registered motion path.

  `SetShooter(x, y, facing, iid)` — Places a ballista on a tile.

  `SetWhiteBackdrop()` — Starts the solid-white backdrop process.

  `SFXPlay(sfx_id)` — Plays a sound effect once at full volume.

  `SFXPlay3D(sfx, x, y, height)` — Plays a positioned sound effect at map tile (x, y) (height below -999 = the ground height there).

  `SFXStop(sfx)` — Stops a sound effect.

  `SuspendEvent()` — Freezes the running event so another script (a tutorial) can run, saving the event's state.

  `TalkEvent(message_id)` — Opens the conversation window with a message and pauses the script until the conversation ends or reaches a $H hold point.

  `TalkEventDirect(message_id)` — Starts the supplied event message, or passes it to the existing conversation process.

  `TalkExist()` — Tests whether a conversation is still running.

  `TalkLeave(message_id)` — Plays a message in a talk process that removes its speakers when done.

  `TalkResume()` — Continues a conversation stopped at a $H hold point and pauses the script again until it ends or reaches the next hold.

  `td(message_id)` — Opens a tutorial dialog with a message and pauses the script until it closes.

  `tde()` — Sets the 'event suspended' state flag again after a tutorial dialog cleared it (the last step of TutorialDialog).

  `TerInfoFadeIn()` — Fades the terrain-info window in.

  `TerInfoFadeOut()` — Fades the terrain-info window out.

  `TerInfoHide()` — Hides the terrain-info window.

  `TerInfoShow()` — Shows the terrain-info window.

  `TimeiShow(x, y, a, message_id, b, c, d)` — Shows a time/place caption (seven arguments in Radiant Dawn: Path of Radiance took six).

  `TimeiShowHold(caption_id, x, y, message_id, appear_ms)` — Shows a location-name caption that stays visible until explicitly released.

  `TimeiShowHoldOff(caption_id, disappear_ms)` — Starts disappearance of the held caption with this ID.

  `TimeiShowHoldOffAll(disappear_ms)` — Starts disappearance of every held caption.

  `TstConversationFlag(name)` — Whether a conversation flag of the system save is set (conversation room unlocks).

  `TutorialResume()` — Returns to the tutorial menu after a tutorial ends (the last step of ComebackFunc).

  `TutShowKari(x, y, message_id, fade_ms, hold_ms)` — Shows a temporary tutorial caption with matching appearance and disappearance durations.

  `UnitDispReload()` — Unloads and reloads the map models of every unit in forces 0–3, then refreshes their positions.

  `UnitEscape(unit)` — Removes the unit from the map as escaped (one argument in Radiant Dawn) and refreshes the map.

  `UnitFocus(unit)` — Moves the map camera smoothly towards a unit's tile.

  `UnitResetStatus(unit)` — Clears the unit's temporary status bits and status effects and recomputes its stats and HP display.

  `UnitResetStatusWholeForce(force)` — UnitResetStatus on every unit of a force.

  `UnitsInitialize()` — Removes every unit: all forces are emptied and all unit slots freed.

  `UnitsPop()` — Restores the units saved by UnitsPush, refreshes the map and reloads the unit models. Frees the buffer.

  `UnitsPopWithoutMap()` — Same as UnitsPop, without the map refresh.

  `UnitsPush()` — Saves every unit (and the forge records) into a temporary buffer, then empties the forces.

  `UnitsPush_Uninitialize()` — Saves every unit (and the forge records) into the temporary buffer, leaving the units in place.

  `VOICEAllStop()` — Stops every voice clip (registered with no argument; vanilla passes a fade time that the handler reads anyway).

  `VOICEPlay(voice)` — Plays a voice clip; returns its channel or -1.

  `VOICEStop(voice)` — Stops a voice clip.

  `WaitPressAnyKey()` — Suspends the calling script until the input-wait process completes after a key press.

  `Warning(text)` — Debug message, ignored in the retail game; returns 1.

  `WipeEnd()` — Resets the screen-wipe state to idle.

  `WipeIn(duration_ms)` — Starts a screen wipe in.

  `WipeOut(duration_ms)` — Starts a screen wipe out.

  `WipeWait()` — Suspends the script while a wipe-in or wipe-out transition is active.

## Map scenes (168)

  Moving, turning and animating units on the map, deployment groups, doors, roofs, torches and other map objects, light, weather, effects, cameras and full-screen post effects.

  `_dispos(group, mode)` — Deploys a deployment group with the animated deployment process.

  `_idispos(group, mode)` — Deploys a deployment group at once (no animation).

  `BuildDestruction(x, y)` — Destroys the village or house at a tile: the camera moves to it, the ruin animation plays and the script waits for it.

  `BuildInstAnim(x, y, mode)` — Plays or sets the two-state animation of an animated map prop at a tile.

  `BuildInstExtinction(x, y, duration_ms)` — Puts out the torch at (x, y).

  `BuildInstGetX(index, kind)` — X of a map object (the first argument back if not found).

  `BuildInstGetY(index, kind)` — Y of a map object (the second argument back if not found).

  `BuildInstHide(x, y)` — Hides a hideable map prop at a tile.

  `BuildInstReject(x, y, on)` — Blocks or unblocks the map object at (x, y) (objects with flag 0x80000: barricades, walls).

  `BuildInstRejectByName(name, on)` — Blocks or unblocks every map object of that name; returns how many.

  `BuildInstShow(x, y)` — Shows a hideable map prop at a tile.

  `BuildInstTorch(x, y, a, duration_ms)` — Lights the torch at (x, y), redrawing the fog; suspends the script during the animation.

  `ClearEventCamera()` — Releases the event camera.

  `CopyMapCamera()` — Saves the map camera's angles and distance so PastMapCamera can return to them.

  `CreateEventCamera()` — Creates an empty event-camera path. Fill it with SetEventCameraAt and SetEventCameraRot keyframes, then play it with StartEventCamera.

  `DeleteEventCamera()` — Removes the event camera and gives control back to the normal map camera.

  `DisposAuxiliary(group)` — Deploys the units the player picked for the second team (SelectAuxiliary) onto the group's tiles and moves them from the reserve to the player force.

  `DisposFree(file)` — Frees a loaded deployment file.

  `DisposGetCount()` — Number of units in the last deployment.

  `DisposGetGroupCenter(group, out_x, out_y)` — Computes the center of a named deployment group and writes its coordinates into two variables.

  `DisposGetRankGroup(group)` — The deployment group's entry name for the current difficulty.

  `DisposGetUnit(index)` — Unit handle of the index-th unit of the last deployment.

  `DisposLoad(file)` — Loads a deployment file (dispos_<difficulty>.bin).

  `DoorClose(x, y)` — Closes the door at a tile with its animation and waits for it.

  `DoorOpen(x, y)` — Opens the door at a tile with its animation and waits for it. The door stops blocking movement.

  `EffectCamera(effect, distance)` — Attaches an effect in front of the camera.

  `EffectCycle(effect, on)` — Turns an effect's cycling flag (0x2000) on or off.

  `EffectDelete(effect)` — Deletes an effect (-1: every event effect).

  `EffectDepth(effect, depth)` — Sets an effect's drawing depth.

  `EffectFadeOut(effect, duration_ms)` — Fades an effect out.

  `EffectLoop(effect, on)` — Makes an effect loop or play once.

  `EffectPlay(eid)` — Plays an effect (EID_...) and suspends the script one frame; returns its handle (one argument in Radiant Dawn); 0 while skipping.

  `EffectPlay2D(eid)` — Plays a screen-space effect; returns its handle.

  `EffectPos(effect, x, y)` — Moves an effect to map tile (x, y) at ground height.

  `EffectPreLoad(eid)` — Preloads an effect; ignored while skipping.

  `EffectPriority(effect, priority)` — Sets an effect's drawing priority (-1 = default 0x98).

  `EffectRotate(effect, x, y, z)` — Rotates an effect (degrees).

  `EffectScale(effect, percent)` — Scales an effect.

  `EffectSpeed(effect, speed)` — Sets an effect's playback speed.

  `EffectUnit(effect, unit, a, bone)` — Attaches an effect to a unit, at a bone or node of its model when bone names one.

  `EffectXYZ(effect, x, y, z)` — Moves an effect to a 3D position (z above the ground).

  `EventQuake(strength, period_ms, cycles)` — Starts a repeating camera shake.

  `EventQuakeStop()` — Requests the active camera shake to stop.

  `FileCameraPlay(name, x, y, z)` — Plays a camera animation file from map position (x, y) and height z.

  `GetFragileHP(x, y)` — Current HP of the breakable object at (x, y) (tile effect type 4), 0 if none.

  `GetFragileMaxHP(x, y)` — Maximum HP of the breakable object at (x, y).

  `GetFukiPosX()` — Reads the X coordinate of the active tutorial speech-bubble display.

  `GetFukiPosY()` — Reads the Y coordinate of the active tutorial speech-bubble display.

  `GetMapHeight(x, y)` — Samples the alternate terrain-surface height at the supplied map coordinates.

  `GetMapHeightBase(x, y)` — Samples the base terrain height at the supplied map coordinates.

  `GetWeather()` — The current weather byte.

  `HideMapCursor()` — Removes every map cursor shown by ShowMapCursor.

  `HidePoint(x, y)` — Removes the marker at (x, y).

  `HidePrim2D(hidden)` — Starts or ends the scene process that hides 2D primitives.

  `InstantDoorClose(x, y)` — Closes the door at a tile without animation and restores its hit points.

  `InstantDoorOpen(x, y)` — Opens the door at a tile without animation.

  `InstantPastMapCamera()` — Restores the angles and distance saved by CopyMapCamera at once.

  `InstantRoofClose(x, y)` — Puts back the roof at a tile without animation.

  `InstantRoofOpen(x, y)` — Lifts the roof at a tile without animation.

  `InstantSetMapCamera(yaw, pitch, distance)` — Sets the map camera's angles and distance at once.

  `InstantUnitTransform(unit, transformed)` — Changes a unit to the requested transformed/untransformed state immediately and refreshes its display.

  `IsDispos()` — 1 when the deployment list is empty (no deployment pending).

  `IsEffect(effect)` — 1 while the effect (or any event effect, for -1) exists; 0 while skipping.

  `IsEventCamera()` — 1 while the event camera is active.

  `IsFileCamera()` — 1 while a FileCameraPlay animation runs (skipping stops it).

  `IsUnitMove(unit)` — 1 while the unit (or any unit, for -1) is moving.

  `MapFree()` — Frees the current map and suspends the script until it is released.

  `MapHide(duration_ms)` — Fades the map out (hides it), suspending the script during the fade; instant when 0 or skipping.

  `MapLoad(map_name)` — Loads a map by name and makes it the current map.

  `MapReload()` — Reloads the current chapter's map, reapplies its recorded map state (opened doors, visited villages, ...) and points the camera at the saved cursor tile.

  `MapShow(duration_ms)` — Fades the map back in.

  `PastMapCamera()` — Turns the camera smoothly back to the angles and distance saved by CopyMapCamera.

  `PostEffectColor(effect, r, g, b)` — Sets a post effect's colour.

  `PostEffectStart(name, a, value, duration_ms)` — Starts a full-screen post effect (blur, colour filter...); returns its handle.

  `PostEffectStop(effect, duration_ms)` — Fades a post effect out (-1: every one).

  `RoofClose(x, y)` — Puts back the roof at a tile with its animation and waits for it.

  `RoofOpen(x, y)` — Lifts the roof at a tile with its animation, revealing the building's inside, and waits for it.

  `SetAmbient(light, r, g, b)` — Sets the colour of ambient light index light and suspends the script one frame (an index argument is new in Radiant Dawn).

  `SetCameraDisp(arg0)` — Debug stub; returns 0.

  `SetCamHold(on)` — Holds the map camera in place (flag 0x08 of 0x804CB838).

  `SetCamSuspend(enabled)` — Sets the camera-suspension flag for map scenes.

  `SetCircle(enabled)` — Enables or disables the scene’s unit-circle display setting.

  `SetDiffuse(light, r, g, b)` — Sets the colour of diffuse light index light and suspends the script one frame.

  `SetEventBattle(enabled)` — Selects the special event presentation branch when the next battle animation is initialized.

  `SetEventCameraAt(time_ms, x, y, height)` — Adds a keyframe for the point the event camera looks at.

  `SetEventCameraCurve(mode, curve)` — Sets the event camera easing curve.

  `SetEventCameraEye(mode, x, y, z)` — Points the event camera eye at a position (scaled by the event camera unit).

  `SetEventCameraPrec(precision)` — Sets the divisor applied to later SetEventCameraAt coordinates, allowing positions finer than a tile.

  `SetEventCameraRot(time_ms, yaw, pitch, distance)` — Adds a keyframe for the event camera's angles and distance.

  `SetEventCameraUnit(mode, unit)` — Makes the event camera follow a unit (-1: none).

  `SetFog(fog_type, start_distance, end_distance, red, green, blue)` — Sets the map’s rendering fog and refreshes its render state.

  `SetGrid(percent)` — Sets the map-grid display intensity or restores the value saved when scene settings were created.

  `SetLisner(x, y, z)` — Moves the sound listener (-1 keeps a coordinate).

  `SetMapCamera(yaw, pitch, distance)` — Turns the map camera smoothly to new angles and distance; the point it looks at does not change.

  `SetMapCameraWeight(weight)` — Sets the map camera's smoothing weight.

  `SetMapLamp(on)` — Turns every lamp object of the map (flag 0x10000000) on or off and relights the map.

  `SetOnBtFocus(enabled)` — Enables or disables automatic battle-focus behavior.

  `SetOutLink(enabled)` — Enables or disables the outer-link portion of the map-link grid and rebuilds that grid.

  `SetPullCursor(enabled)` — Enables or disables automatic cursor pulling.

  `SetRoofEnable(x, y, enabled)` — Changes the enabled state of the roof section found at the supplied map position and refreshes the map.

  `SetSight(radius)` — Sets the fog-of-war vision and redraws the fog (one argument in Radiant Dawn).

  `SetTerrData(x, y, terrain)` — Overrides tile (x, y)'s terrain (tile effect 0x11) and refreshes the map; an empty name removes it.

  `SetTerrName(x, y, name)` — Overrides the terrain name shown for tile (x, y) (tile effect 0x10); an empty name removes it.

  `SetTimeScale(percent)` — Slows down or speeds up the game clock (100 = normal).

  `SetUnitAlways(on)` — Turns the "units always shown" event flag on or off (0x804CB740).

  `SetUnitGauge(on)` — Shows or hides the map's unit HP gauges during events.

  `SetUnitIcon(on)` — Shows or hides the map's unit icons during events.

  `SetUnitMask(on)` — Turns the event unit mask flag on or off (0x804CB73F).

  `SetWeather(weather)` — Changes the map weather byte and refreshes weather, lighting and visibility rendering.

  `SetWeatherAlpha(a, b, duration_ms)` — Fades the weather effect's opacity.

  `ShowHealWindow(unit, amount)` — Shows the unit's HP window healing by amount and suspends the script until it closes.

  `ShowMapCursor(x, y)` — Shows the blinking map cursor on a tile.

  `ShowPoint(x, y, r, g, b)` — Shows a coloured marker on map tile (x, y); ignored while skipping.

  `StartEventCamera(easing)` — Plays the event-camera path. Keyframes are joined with a smooth curve; if the path has no keyframe at time 0, the camera's current state is added as the first one.

  `TBoxOpen(x, y)` — Plays the opening of the chest at a tile and waits for it, and marks the chest as opened.

  `UnitAngleRotate(unit, angle, frames)` — Turns the unit to an angle in degrees.

  `UnitAnim(unit, animation)` — Loads and plays a unit animation with the default blend length of 16, replacing an existing scripted animation for that unit.

  `UnitAnimEx(unit, animation, speed, blend_frames, flags)` — Plays a map animation on the unit (animation 0 = its idle; ids from 100); speed in percent (-1 = 100).

  `UnitAnimPreLoad(unit, animation)` — Preloads one of the unit's map animations.

  `UnitChildSend(unit, target)` — Unit gives the unit it carries to target (Give).

  `UnitDead(unit)` — Plays the death fade-out of a unit's map model (with its sound) and waits for it.

  `UnitDropOff(unit, direction)` — Unit drops the unit it carries on the side given by direction (1 left, 2 right, 4 down, 8 up; negative: the nearest free tile).

  `UnitFadeIn()` — Makes later scripted movement fade units in (they appear as they move).

  `UnitFadeOff()` — Ends UnitFadeIn/UnitFadeOut: later movement shows units normally.

  `UnitFadeOut()` — Makes later scripted movement fade units out (they disappear as they move).

  `UnitFocusOff()` — Stops the camera from following units during later scripted movement.

  `UnitFocusOn()` — Makes the camera follow units during later scripted movement (the default).

  `UnitGetDir(unit)` — The unit's facing direction.

  `UnitGetFumble(unit)` — Like UnitGetStrike for the animation's miss frame.

  `UnitGetStrike(unit)` — 1 when the unit's current animation has reached its hit frame (or the unit is not moving); 1 while skipping.

  `UnitHide(unit)` — Hides the unit's map model.

  `UnitLooksChange(unit, on)` — Gives or removes the SID_LOOKSCHANGE skill (alternate look) and reloads the unit's model.

  `UnitMoveDelete(unit)` — Stops the unit's scripted movement (-1: every unit's).

  `UnitMoveDir(unit, path)` — Walks a unit along a list of steps, ignoring terrain and other units.

  `UnitMovePos(unit, x, y)` — Walks a unit to a tile along a real path. If the tile is taken, the nearest free tile the unit can reach is used.

  `UnitMoveRoute(unit, route)` — Walks the unit along a route written as a string of coordinates; teleports it to the end while skipping.

  `UnitPosRotate(unit, x, y, frames)` — Turns the unit to face map position (x, y) (frames < 0: speed from the angle).

  `UnitPush(unit, direction, tiles)` — Slides the unit tiles squares; direction 1 left, 2 right, 4 down, 8 up.

  `UnitReplace(unit_a, unit_b)` — Swaps the positions and facings of two units.

  `UnitRescue(unit, target)` — Unit picks target up (rescue), animated unless skipping; both must be free (not carrying nor carried).

  `UnitRotate(unit, direction, duration_ms)` — Turns a unit to face a direction.

  `UnitRotateAnim(on)` — Units play a turning animation when scripted rotations turn them.

  `UnitRunAway(unit)` — Plays the unit fleeing off the map; while skipping it is removed at once.

  `UnitSetAID(unit, aid)` — Replaces the unit's map model by an animation ID (AID_...; "" restores its own); 0 if the AID is unknown.

  `UnitSetAnim(unit, animation)` — Overrides the unit's map animation by name ("" restores it).

  `UnitSetColor(unit, r, g, b, a)` — Tints the unit's map model.

  `UnitSetFixed(unit, enabled)` — Sets or clears the unit’s fixed-state flag.

  `UnitSetHand(unit, on)` — Turns the unit model's hand flag (0x800) on or off.

  `UnitSetOffset(unit, x, y, z)` — Offsets the unit's map model (in hundredths of a tile).

  `UnitSetPos(unit, x, y)` — Places a unit on a tile at once. If the tile is taken, the nearest free tile is used.

  `UnitSetScale(unit, scale)` — Sets the unit model's scale byte (+0xC6).

  `UnitSetScaleAll(scale)` — Default model scale for event units.

  `UnitShow(unit)` — Shows the unit's map model again.

  `UnitTackle(acting_unit, target_unit, distance)` — Moves the target away from the acting unit and starts shove/smite motion.

  `UnitTransform(unit, transformed)` — Changes a unit to the requested transformed/untransformed state with its transformation animation.

  `UnitWaitAnim(animation)` — Animation units play after next scripted moves ("" = default).

  `UnitWalkAnim(animation)` — Walking animation for next scripted moves ("" = default).

  `UnitWalkDir(direction)` — Sets the direction bits used by subsequent scene walking.

  `UnitWalkGround(on)` — Next scripted moves follow the ground height (walk flag 0x1000).

  `UnitWalkHold(on)` — Next scripted moves keep units in place facing the move (walk flag 0x100).

  `UnitWalkManual(on)` — Next scripted moves turn automatically (0) or keep the set facing (1) (walk flag 0x80, inverted).

  `UnitWalkPush(on)` — Next scripted moves push other units out of the way (walk flag 0x200).

  `UnitWalkReverse(on)` — Next scripted moves walk backwards (walk flag 0x800).

  `UnitWalkSpeed(speed)` — Walking speed for next scripted moves.

  `UnitWalkTime(frames)` — Duration of next scripted moves.

  `UnitWarpOut(unit)` — Plays the Warp effect on a unit and waits for it.

  `VisitIn(unit, x, y)` — Does nothing (kept for the visit-event scripts).

  `VisitOut(unit, x, y)` — Closes the village at a tile after a visit: plays its closing animation, waits for it and marks the village as visited.

## Units and the battle map (126)

  Reading and changing units, their items, skills, teams and AI flags, the per-army convoys, and battle-map values such as the turn, the score and the objective lines.

  `AddToCurrentWarehouseWhatever(iid)` — Adds a new item to the current army's convoy; 0 when there is none or the item cannot be stored.

  `AddToWarehouseWhatever(convoy, iid)` — Adds a new item to convoy 1-5.

  `BMAddForgeLevel(weapon_type)` — Raises the forge experience of weapon type 0-5 by 50 (capped at 4950).

  `BMGetChapter()` — Returns the current chapter number.

  `BMGetMoney()` — Returns the party's gold.

  `BMGetPhase()` — Returns whose phase it is.

  `BMGetScore()` — The battle-map score.

  `BMGetTanto(index)` — Byte index of the battle-map table at 0x803CAB4C ("tanto": in charge); meaning of the entries not checked.

  `BMGetTurn()` — Returns the turn number.

  `BMGetValue(field_index)` — Reads a signed 16-bit field from battle-map state.

  `BMSetChapter(chapter)` — Sets the battle map's chapter number byte.

  `BMSetLoseTerm(line, message_id)` — Sets defeat-condition line number line of the map's objective panel (vanilla counts lines with a variable: BMSetLoseTerm(n++, ...)).

  `BMSetMoney(value)` — Sets the party's gold.

  `BMSetPhase(force)` — Overwrites the current-phase value.

  `BMSetScore(value)` — Sets the battle-map score.

  `BMSetTanto(player_control, enemy_control, force_2_control, force_3_control)` — Sets who controls each of the four active map forces.

  `BMSetTurn(turn)` — Overwrites the turn counter.

  `BMSetValue(field_index, value)` — Writes a 16-bit field in battle-map state.

  `BMSetWinTerm(line, message_id)` — Sets victory-condition line number line (0, 1, ...) of the map's objective panel.

  `CpClrNoMoveFlag(unit)` — Clears the two no-move control bits from a unit’s AI state.

  `DelItemsFromCurrentWarehouse(iid)` — Deletes every copy of the item from the current army's convoy; 1 if any was deleted.

  `DelItemsFromForce(force, iid)` — Deletes every copy of the item from the units of a force; 1 if any was deleted.

  `EventGetX()` — Returns the X coordinate of the tile that started the current location event (visit, area, chest, door).

  `EventGetY()` — Returns the Y coordinate of the tile that started the current location event.

  `ForceGetCount(force)` — Number of units in force 0-10.

  `ForceGetFirst(force)` — First unit of force 0-10 (Radiant Dawn has eleven force lists), to walk it with UnitGetNext; 0 if empty or out of range.

  `ForceUnitGetByPID(force, pid)` — The unit with this PID in the given force's list, 0 if none.

  `GameGetRound()` — Byte +0x34 of the game state (FUN_8024BCA0); by its name the playthrough round, not checked in game.

  `GCST()` — Returns the event system's state flags.

  `GetBattleType()` — Returns the flag word of the current or most recent battle.

  `GetLanguage()` — The language byte of the system save (+0x1BC8; the index of the Mess/ file prefix table, -1 = the disc's default).

  `GetRnd(exclusive_max)` — Draws a random integer using the game random-number generator.

  `InstantUnitClassChange(unit)` — Promotes the unit at once if it has the SID_EVENT_CC skill and its class has a promotion; returns 1 if it did.

  `ItemGetIndex(iid)` — Resolves an item ID to its numeric item index.

  `MapGetSight(x, y)` — Reads the visibility-grid byte at a tile.

  `MapGetTerrain(x, y)` — Reads the terrain ID stored at a map tile.

  `MindGetMe()` — Returns the unit performing the current action (the unit that visited, talked, opened a chest, etc.).

  `MindGetMind()` — Reads the current map-action ID.

  `MindGetTarget()` — Returns the target of the current action (the unit talked to or fought).

  `MindSetMind(unit)` — Makes the unit the current acting unit ("Me" of the event context).

  `PersonGetYellLevel(pid1, pid2)` — Returns the support rank between two characters.

  `PersonSetYellLevel(pid1, pid2, stage)` — Sets two support partners' support points to the threshold of a rank.

  `PIDisAlive(pid)` — Looks up a character’s current actor and checks that its dead flag is clear.

  `strcmp(a, b)` — The C library strcmp of two strings (0 when equal).

  `SysGetEventFlag()` — Always 1 (debug stub).

  `SysGetRound()` — Reads the playthrough ordinal from the clear-data record.

  `UnitAddItem(unit, item_id)` — Puts an item in a unit's inventory, silently: depending on the item type it goes to the first free weapon slot (0–3) or the first free item slot (4–7).

  `UnitAddSkill(unit, skill_id)` — Gives a unit a skill.

  `UnitAddSkillWhatever(unit, sid)` — Adds the skill, then removes the unit's lowest-priority removable skills until the skills fit the capacity.

  `UnitBreakup(unit)` — Separates a carrying pair: the carried unit is put back on the map on the carrier's tile. Either unit of the pair can be given.

  `UnitCanParty(unit)` — 1 if the unit can join the party (deployable), else 0.

  `UnitCanUseIt(unit, slot)` — Checks whether the unit can use the item in the specified inventory slot.

  `UnitClassChange(unit)` — Plays the promotion scene and promotes the unit, suspending the script; only for a unit with the SID_EVENT_CC skill whose class can promote (instant while skipping).

  `UnitClrCpFlag(unit, mask)` — Clears mask from a non-player unit's AI flags; returns the new flags.

  `UnitClrSkill(unit, skill_id)` — Removes a skill from a unit.

  `UnitClrStatus(unit, mask)` — Clears state flags on a unit.

  `UnitDelAllItems(unit)` — Deletes the unit's seven items and refreshes its equipment.

  `UnitDelItem(unit, slot)` — Removes the item in an inventory slot and closes the gap.

  `UnitDontMoveSally(unit)` — Locks the starting tile of a unit of force 0, 5 or 7-10 in the preparations (status bit 0x20000); returns 1.

  `UnitForcedSally(unit)` — Makes a unit of force 0, 5 or 7-10 mandatory in the preparations (status bit 0x10000); returns 1.

  `UnitGet(unit, field)` — Reads a selected property of a runtime unit.

  `UnitGetBelongCount(group)` — Number of active, deployed units of the player-side forces whose belong group is group.

  `UnitGetByPID(pid)` — Finds the current runtime actor for a character ID.

  `UnitGetByPos(x, y)` — Finds an eligible visible actor occupying a map tile.

  `UnitGetChild(unit)` — The unit this one carries (the rescue partner while this unit is the carrier), else 0.

  `UnitGetDie()` — The unit that just died (the death context), 0 outside a death event.

  `UnitGetDispX(unit)` — The unit's displayed X position (model position, truncated), 0 for no unit.

  `UnitGetDispY(unit)` — The unit's displayed Y position (model position, truncated), 0 for no unit.

  `UnitGetEquipAccI(unit)` — Gets the active accessory slot in the combined inventory numbering.

  `UnitGetEquipWepI(unit)` — Gets the active equipped-weapon slot index.

  `UnitGetForce(unit)` — Returns a unit's force.

  `UnitGetHero()` — The army's hero unit (first lookup of force 0, else the fallback list), 0 if none.

  `UnitGetHP(unit)` — Returns a unit's current HP.

  `UnitGetItemCount(unit)` — Counts the items a unit carries, weapons included.

  `UnitGetMaxHP(unit)` — Returns a unit's maximum HP, including the bonus of the equipped weapon and item, capped by the class.

  `UnitGetMoveCost(unit, terrain_index)` — Reads this unit’s movement cost for a terrain-table entry.

  `UnitGetNext(unit)` — Returns the next unit in the same force.

  `UnitGetParent(unit)` — The unit carrying this one (the rescue partner while this unit is carried), else 0.

  `UnitGetRace(unit)` — Reports the unit’s beorc/laguz transformation category.

  `UnitGetStatus(unit)` — Returns a unit's state flags.

  `UnitGetTeam(unit)` — The unit's team byte (+0x117), used to group units for the AI.

  `UnitGetTeamCommander(team)` — The deployed, living unit that commands the team (status bits 0x4000000 set, 0x8 clear); -1 if none.

  `UnitGetTeamCount(team)` — Number of deployed, living units in the team (-1 for team 0 or less).

  `UnitGetWeaponCount(unit)` — Counts the weapons a unit carries (its four weapon slots).

  `UnitGetX(unit)` — Returns a unit's tile X.

  `UnitGetY(unit)` — Returns a unit's tile Y.

  `UnitItemClrAllSubItems(unit)` — Clears the "sub item" flag (0x08) of the unit's seven items.

  `UnitItemGetValuation(unit, slot)` — Returns a value score for an inventory item, used to pick which item to send away.

  `UnitItemSendtoCurrentWarehouse(unit, slot)` — Sends the item in that slot to the current army's convoy; 0 when there is no current convoy or the item cannot be stored.

  `UnitItemSendtoCurrentWarehouseAll(unit)` — Sends every item of the unit that may go to a convoy to the current army's convoy (others are deleted); refreshes the equipment.

  `UnitItemSendtoWarehouse(convoy, unit, slot)` — Like UnitItemSendtoCurrentWarehouse with convoy 1-5.

  `UnitItemSendtoWarehouseAll(convoy, unit)` — Like UnitItemSendtoCurrentWarehouseAll with convoy 1-5 (the per-army convoys); new first argument in Radiant Dawn.

  `UnitItemSetBless(unit, slot)` — Marks the item in slot 0-6 as blessed (flag 0x10) when the item can be blessed; 1 if it did.

  `UnitItemSetDrop(unit, slot)` — Marks one inventory item as dropped when the unit is defeated.

  `UnitItemSetEndurance(unit, slot, uses)` — Sets the remaining uses of the item in slot 0-6.

  `UnitItemSetSealSteal(unit, slot)` — Makes the item in that slot unstealable (item flag 0x04).

  `UnitNeverSally(unit)` — Marks a unit of force 0, 5 or 7-10 as never deployable (status bit 0x200000); returns 1.

  `UnitPairup(carrier, carried)` — Links two actors using the game’s carrying/pairing operation, first moving the second actor to the tile right of the first.

  `UnitQueryEquip(unit, slot)` — Tests the equipped bit of an inventory slot.

  `UnitQueryJID(unit, jid)` — Tests whether a unit has a given class.

  `UnitQueryPID(unit, pid)` — Tests whether a unit is a given character.

  `UnitReorderSkill(unit)` — Re-sorts the unit's skill list.

  `UnitReplaceItem(unit, slot, iid)` — Replaces the selected inventory slot using an item ID.

  `UnitSearchItem(unit, item_id)` — Finds an item in a unit's inventory.

  `UnitSet(unit, field, value)` — Writes one of the supported mutable unit fields.

  `UnitSetAccAway(unit)` — Unequips the unit's equipped item (band or ring).

  `UnitSetBelong(unit, group)` — Moves the unit into belong group group (+0xFD); 0 if the group does not exist.

  `UnitSetCpAttackSeq(unit, sequence)` — Changes the attack AI script of a unit.

  `UnitSetCpFlag(unit, mask)` — ORs mask into a non-player unit's AI flags (+0x3B4); returns the new flags.

  `UnitSetCpForceNoMoveFlag(unit, on)` — Sets or clears the AI "never move" flag (0x2000000 in the AI flags +0x3B4) of a non-player unit.

  `UnitSetCpHealSeq(unit, record)` — Changes the healing AI record of a unit.

  `UnitSetCpMoveSeq(unit, sequence)` — Changes the movement AI script of a unit.

  `UnitSetCpMTypeID(unit, table)` — Changes the MTYPE AI table of a unit (how it values targets).

  `UnitSetCpTwiceMoveSeq(unit, sequence)` — Sets the AI's second-move sequence of a non-player unit; 0 for player units.

  `UnitSetEquip(unit, slot)` — Equips an inventory item.

  `UnitSetEXP(unit, exp)` — Sets a unit's experience.

  `UnitSetHP(unit, hp)` — Sets a unit's current HP.

  `UnitSetLeader(unit, on)` — Sets or clears the unit's leader status bit (0x100).

  `UnitSetOrigin(unit, value)` — Sets the unit's origin byte (+0x380).

  `UnitSetStatus(unit, mask)` — Sets state flags on a unit.

  `UnitSetTeam(unit, team)` — Sets the unit's team.

  `UnitSetWeaponAway(unit)` — Unequips the unit's weapon and returns its slot; -1 for a laguz (SID_ANIMALIZE) or a unit without one.

  `UnitTransferToForce(unit, force)` — Moves a unit to another force, for example to recruit it (force 0) or turn it into an ally (2).

  `UnitTstCpFlag(unit, mask)` — A non-player unit's AI flags ANDed with mask.

  `UnitTstSkill(unit, skill_id)` — Tests whether a unit holds a skill.

  `UnitTstStatus(unit, mask)` — The unit's status word (+0x10C) ANDed with mask; 0 for no unit.

## Battle-map scenes and tutorials (52)

  Tutorial overlays and scripts, cursor holding and the tutorial settings.

  `_bmsini()` — Resets the chapter for a tutorial: chapter number 0 (so the convoy is available), turn 1, the player controls force 0 and the computer forces 1–3, 1,000 gold, chapter flags and gf_complete/gf_gameover cleared, no units, empty convoy, no forge records, map state cleared.

  `_pa(command)` — Plays a scripted controller input (the 'pad actor' that moves the cursor and presses buttons in tutorials). Each character is one step: a one-frame press, then a pause until the next step.

  `_seqini()` — Clears the map for a tutorial: removes conversations, images, scripted input, the preparations, AI phase and phase banner, the notice frame and the unit models.

  `_tr()` — Continues a held tutorial conversation (the step behind TutTalkResume).

  `_tt(message_id)` — Starts a tutorial conversation with a message (the step behind TutTalkEvent).

  `ArcFree(resource_path)` — Releases one reference to a relocatable game resource.

  `ArcLoad(resource_path)` — Loads a relocatable game resource.

  `BeginMapHoldCursor()` — Starts the map cursor-hold process.

  `CmbMessLoad(script, message_file)` — Loads a .cmb script and its message file Mess/<language prefix><message_file>.m (tutorial scripts).

  `CmbMessUnload(message_file)` — Frees the script and message file loaded by CmbMessLoad.

  `CmFreeScript()` — Unloads the most recently loaded script file and removes its named functions.

  `CmLoadScript(script_path)` — Loads a CMB script module and makes its exported functions available.

  `CmSleepScript(module_name)` — Suspends a module’s event enumeration and temporarily removes its exported functions.

  `CmWakeupScripts()` — Wakes every script file put to sleep by CmSleepScript and makes its named functions callable again.

  `Config_TutGet_sfx_vol()` — Reads the stored tutorial sound-effect volume byte.

  `Config_Tutorial()` — Resets the tutorial configuration block to defaults, including internal difficulty ID 1.

  `Config_TutSet_ctrlInfo(on)` — Option 1 turns the controls-help setting on (play settings bits 0x000C0000), any other value off.

  `Config_TutSet_otheridoshowing(enabled)` — Sets the tutorial setting for other-unit movement display.

  `Config_TutSet_sfx_vol(volume)` — Stores the tutorial sound-effect volume and applies the settings.

  `Config_TutSet_terInfo(enabled)` — Sets the tutorial setting for terrain information.

  `Config_TutSet_unitInfo(enabled)` — Sets the tutorial setting for unit information.

  `Config_TutSet_XinfoPage(page)` — Sets the tutorial information-page selection.

  `CreateNoticeFrame(x, y, width, height)` — Creates or updates an animated rectangular highlight around a screen area.

  `CreateNoticeLFrame(x, y, width_1, width_2, height_1, height_2, orientation)` — Creates or updates an animated six-edge L-shaped screen highlight.

  `DeleteNoticeFrame()` — Removes the active E_NoticeFrame highlight frame.

  `EndMapHoldCursor()` — Ends the map cursor-hold process.

  `GameBind()` — Freezes the map's normal game flow (phases, cursor, menus) while the script works.

  `GameUnbind()` — Lets the map's game flow continue after GameBind.

  `GetTutorial()` — Reads whether tutorial help is enabled in configuration.

  `QueryLesson(lesson_name)` — Tests whether the active lesson has the given name.

  `SetTutorial(on)` — 1 enables tutorials, anything else disables them (play settings bit 0x20000).

  `taikitk()` — Starts a waiting token that lasts until a unit's next Wait command (E_TaikiToken).

  `turnatk()` — Starts a waiting token that lasts until the next end of turn (E_TurnAToken).

  `turntk()` — Starts a waiting token that lasts until the next turn change (E_TurnToken).

  `Tut3SArrowABAnim(rect_id, period_ms, amplitude)` — Continuously oscillates a tutorial arrow rectangle along its positive diagonal axis.

  `Tut3SArrowBCAnim(rect_id, period_ms, amplitude)` — Continuously oscillates a tutorial arrow rectangle along its horizontal axis.

  `Tut3SArrowCAAnim(rect_id, period_ms, amplitude)` — Continuously oscillates a tutorial arrow rectangle along its negative diagonal axis.

  `Tut3SArrowDAnim(rect_id, period_ms, amplitude)` — Continuously oscillates a tutorial arrow rectangle along its downward vertical axis.

  `Tut3SArrowUAnim(rect_id, period_ms, amplitude)` — Continuously oscillates a tutorial arrow rectangle along its upward vertical axis.

  `TutMapFree()` — Frees the tutorial map overlay and suspends the script until it is released.

  `TutMapLoad(name)` — Loads a tutorial map overlay and suspends the script until it is loaded.

  `TutorialBaseCreate()` — Starts the base-tutorial overlay.

  `TutorialBaseDelete()` — Closes the base-tutorial overlay.

  `TutorialCall(entry_name)` — Starts a named function of a loaded tutorial script and stops the AI phase.

  `TutorialForget(tutorial_id)` — Clears a tutorial’s learned mark.

  `TutorialInitialize()` — Starts tutorial initialization and suspends the calling script until it completes.

  `TutorialLearn(tutorial_id)` — Marks a tutorial as learned.

  `TutorialLock(tutorial_id)` — Locks a tutorial.

  `TutorialSallyCreate()` — Opens the preparations screen inside a tutorial.

  `TutorialSallyDelete()` — Closes the preparations screen opened by TutorialSallyCreate.

  `TutorialUnlock(tutorial_id)` — Unlocks a tutorial.

  `TutShow(text_resource)` — Starts a tutorial text display.

## Chapter results (11)

  Bonus experience lines and the defeat and escape checks of a chapter.

  `AchieveSet(label, amount)` — Records one line of the chapter's bonus-experience results. Radiant Dawn halves the amount on difficulty 2 (Maniac) and adds half on difficulty 3 (Easy); a line of 0 or less is skipped.

  `EnemyDeadCheck()` — Tests whether the enemy force is empty.

  `EnemyMonkCheck()` — Counts enemy-force actors with class JID_PRIEST, JID_BISHOP, or JID_BISHOP_F.

  `EnemySelfDefenceCheck()` — Counts enemy-force actors with PID PID_12_SELFDEFENCE.

  `EnemyTigerCheck()` — Counts enemy-force actors with class JID_TIGER.

  `EnemyUnitCheckByPID(pid)` — Counts actors with the specified PID in the enemy force.

  `GetDiedPlayerCount()` — Counts actors in force 6 whose death-record flag is set.

  `PlayerDeadCheck()` — Tests whether the inactive force list is empty.

  `PlayerEscapeCheck()` — Tests whether every existing actor in player force 0 or reserve force 5 has the escaped flag.

  `PlayerEscapeCount()` — Counts escaped actors in player force 0 and reserve force 5.

  `ShooterBulletCheck()` — Counts the ballista shots spent on the map.

## Event arrows (7)

  Arrows drawn on the map during events.

  `EventArrowAppend(arrow_id, time_ms, x, y, height)` — Adds a timed waypoint to a map-event arrow’s path.

  `EventArrowColor(arrow_id, red, green, blue, alpha)` — Sets the arrow’s RGBA color.

  `EventArrowDelete()` — Deletes the map-event arrow process and all of its arrows.

  `EventArrowFadeOut(arrow_id)` — Requests fade-out of the selected map-event arrow.

  `EventArrowFocus(arrow_id, enabled)` — Changes the arrow’s focus-following flag.

  `EventArrowStart(arrow_id, duration_ms)` — Starts an arrow path transition from its current progress using the supplied time.

  `EventArrowWait()` — Suspends the script while map-event arrows are animating.

## Scripted 3D scenes (7)

  In-engine movie scenes built from model and animation files, and the text speed.

  `ScriptMovieEnd()` — Ends the scripted movie scene and restores the map and sound.

  `ScriptMoviePlay(name)` — Plays the scene's animation for name.

  `ScriptMoviePreLoad(name)` — Preloads a scene animation file.

  `ScriptMovieReference(name)` — Loads the scene's model, skeleton, animation and texture files for name and attaches them to the scene camera.

  `ScriptMovieStart()` — Starts a scripted 3D movie scene (map environment hidden, other sound muted) and suspends the script; ignored while skipping.

  `ScriptMovieWait()` — 1 while the scripted movie is still playing (use in a wait loop).

  `SetTalkTick(ticks)` — Sets the conversation text speed byte (+0x23 of the play settings).

## Ending (5)

  The epilogue, staff roll, war record and unit ranking screens.

  `Epilogue()` — Runs the epilogue (EpilogueProc, which fires the type-20 events per character) and suspends the script until it ends.

  `FinEffect()` — Starts the closing effect process and suspends the script.

  `StaffRoll()` — Runs the staff roll and suspends the script (no argument in Radiant Dawn; vanilla still passes a duration).

  `UnitRanking()` — Shows the unit ranking screen and suspends the script.

  `WarRecord()` — Shows the war record screen and suspends the script (no argument in Radiant Dawn; vanilla still passes one).

## Conversation signals (1)

  A flag a conversation raises for the script.

  `TFXTstSignal()` — 1 once when a conversation sends its TFX signal (message flag 0x800), then clears it.

## Called but not registered

  Vanilla scripts call `IndividualWarRecord`, `ScriptDbgMenu`, `ScriptDbgMenuResult`, which no part of the game registers: such a call does nothing and gives 0.
