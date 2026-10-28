# Path of Radiance script function reference

Companion to the [Python-style scripting tutorial](script-tutorial.md). These calls are for US Path of Radiance.

## Calling functions

Arguments are positional: write them in the order shown. The names in signatures explain their purpose; keyword arguments are not supported. Calls are case-sensitive.

A return value is not necessarily a success code. Some calls return a unit handle, an index, a count, or a sentinel such as -1. Calls that start animations may return before the animation finishes; use the matching wait call.

## Shared conventions

- **Units:** use the numeric handle returned by UnitGetByPID or another unit lookup. A handle is neither a PID string nor a memory address. Zero means no unit. Do not invent handles or keep them after their unit has been removed.
- **Force IDs:** 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 player reserve, 6 inactive/death-flagged, 7 special inactive. These are different from phase IDs.
- **Coordinates:** map-grid coordinates include borders. Screen and world-map coordinates follow their own conventions.
- **Output arguments:** pass &variable where a call writes a result into a local variable. Reserve each output before calling.
- **Flags:** register before use and preserve registration order for save compatibility. See the tutorial’s named-flag lesson.

## Function index

| Function | Purpose |
|---|---|
| [AchieveSet](#call-achieveset) | Records one line of the chapter's bonus-experience results: a label and an amount. Used inside achievement (type 12) functions, which the game runs at chapter end; each function that runs fills the next line. |
| [AddTT](#call-addtt) | Adds a raw entry to the map's special-terrain list. |
| [AllPop](#call-allpop) | Restores the game state saved by AllPush and frees the buffer. |
| [AllPush](#call-allpush) | Saves the whole game state into the temporary buffer (party data, camera, every unit, convoy, forge records and map state), then resets units, chapter flags, map state, convoy and forge records. |
| [AllUnitEscape](#call-allunitescape) | Removes every unit of forces 0–3 from the map: carried units are dropped first, player units go to the reserve marked as escaped, all other units are deleted. |
| [AllUnitsBreakup](#call-allunitsbreakup) | Walks force 0 only, bounded by ForceGetCount(0), and calls UnitCheckLinked_Breakup for each actor until count exhaustion or a null next actor. |
| [ArcFree](#call-arcfree) | Releases one reference to a relocatable game resource. |
| [ArcLoad](#call-arcload) | Loads a relocatable game resource. |
| [ArenaDump](#call-arenadump) | Prints memory-arena usage to debug output. |
| [BGMCont](#call-bgmcont) | Resumes a channel paused by BGMMute and fades it back to its remembered volume. |
| [BGMFadeIn](#call-bgmfadein) | Starts a track on a music channel, fading it in from silence to full volume. If any channel is already playing this same track, nothing changes. |
| [BGMFadeOut](#call-bgmfadeout) | Fades a playing channel to silence and stops it. |
| [BGMMute](#call-bgmmute) | Fades a playing channel to silence and pauses it, remembering its volume and position so BGMCont can bring it back. |
| [BGMPlay](#call-bgmplay) | Starts a track on a music channel at full volume. If any channel is already playing this same track, nothing changes. The channel's previous track is stopped. |
| [BGMPlayVol](#call-bgmplayvol) | Starts a track on a music channel at the given volume. |
| [BGMQuietOff](#call-bgmquietoff) | Ends the music 'quiet' state started by BGMQuietOn, restoring the level over about a quarter of a second. |
| [BGMQuietOn](#call-bgmquieton) | Starts lowering the music for a dialogue box or a reward window (the game's music 'quiet' state), over about a quarter of a second. |
| [BGMResume](#call-bgmresume) | Restores map-music channel 0 to volume 100 over 200 ms and starts a 200 ms countdown on active event-music channels 1–3. |
| [BGMSetVol](#call-bgmsetvol) | Changes a channel's volume gradually. |
| [BGMStop](#call-bgmstop) | Stops a playing channel almost immediately (a one-millisecond fade). |
| [BMGetChapter](#call-bmgetchapter) | Returns the current chapter number. |
| [BMGetMoney](#call-bmgetmoney) | Returns the party's gold. |
| [BMGetPhase](#call-bmgetphase) | Returns whose phase it is. |
| [BMGetTurn](#call-bmgetturn) | Returns the turn number. |
| [BMGetValue](#call-bmgetvalue) | Reads a signed 16-bit field from battle-map state. |
| [BMSetMoney](#call-bmsetmoney) | Sets the party's gold. |
| [BMSetPhase](#call-bmsetphase) | Overwrites the current-phase value. |
| [BMSetTanto](#call-bmsettanto) | Sets who controls each of the four active map forces. |
| [BMSetTerm](#call-bmsetterm) | Replaces one battle-map term string. |
| [BMSetTurn](#call-bmsetturn) | Overwrites the turn counter. |
| [BMSetValue](#call-bmsetvalue) | Writes a 16-bit field in battle-map state. |
| [BeginFinale](#call-beginfinale) | Enables finale mode and its input mask for A/B/X/Y/Z/L/R/Start. |
| [BeginMapHoldCursor](#call-beginmapholdcursor) | Starts the map cursor-hold process. |
| [BgmChangeEvt_MapToEvt1](#call-bgmchangeevt-maptoevt1) | Calls BGMMute(0, duration), waits the full duration with WaitM, then BGMPlay(1, bgm_id). |
| [BgmChangeEvt_MapToEvt2](#call-bgmchangeevt-maptoevt2) | Calls BGMMute(0, duration), waits duration >> 1 with WaitM, then BGMPlay(1, bgm_id). |
| [BgmChangeEvt_MapToEvt3](#call-bgmchangeevt-maptoevt3) | Calls BGMMute(0, duration), waits no time, then BGMPlay(1, bgm_id). |
| [BgmContEvt_EvtToMap1](#call-bgmcontevt-evttomap1) | Calls BGMFadeOut(1, fade_duration), waits the full fade_duration with WaitM, then BGMCont(0, resume_duration). |
| [BgmContEvt_EvtToMap2](#call-bgmcontevt-evttomap2) | Calls BGMFadeOut(1, fade_duration), waits fade_duration >> 1 with WaitM, then BGMCont(0, resume_duration). |
| [BgmContEvt_EvtToMap3](#call-bgmcontevt-evttomap3) | Calls BGMFadeOut(1, fade_duration), waits no time, then BGMCont(0, resume_duration). |
| [BuildDestruction](#call-builddestruction) | Destroys the village or house at a tile: the camera moves to it, the ruin animation plays and the script waits for it. |
| [BuildInstAnim](#call-buildinstanim) | Plays or sets the two-state animation of an animated map prop at a tile. |
| [BuildInstHide](#call-buildinsthide) | Hides a hideable map prop at a tile. |
| [BuildInstShow](#call-buildinstshow) | Shows a hideable map prop at a tile. |
| [ChapterMoviePlay](#call-chaptermovieplay) | Plays the movie of a chapter and pauses the script until it ends. |
| [Check](#call-check) | Tests whether a base-conversation event is being evaluated for availability rather than being played. |
| [CheckAttackable](#call-checkattackable) | Tests whether this unit can reach a position from which its equipped weapon can attack an eligible enemy. |
| [CmFreeScript](#call-cmfreescript) | Unloads the most recently loaded script file and removes its named functions. |
| [CmLoadScript](#call-cmloadscript) | Loads a CMB script module and makes its exported functions available. |
| [CmSleepScript](#call-cmsleepscript) | Suspends a module’s event enumeration and temporarily removes its exported functions. |
| [CmWakeupScripts](#call-cmwakeupscripts) | Wakes every script file put to sleep by CmSleepScript and makes its named functions callable again. |
| [Comeback](#call-comeback) | Consumes the current event skip/cancel state and performs its cleanup. |
| [ComebackFunc](#call-comebackfunc) | SuspendEvent; yield; MapFree; yield; external Startup; TutorialResume. |
| [Complete18](#call-complete18) | Ends a multipart chapter segment and selects its next chapter-flow state. |
| [Config_TutGet_sfx_vol](#call-config-tutget-sfx-vol) | Reads the stored tutorial sound-effect volume byte. |
| [Config_TutSet_XinfoPage](#call-config-tutset-xinfopage) | Sets the tutorial information-page selection. |
| [Config_TutSet_otheridoshowing](#call-config-tutset-otheridoshowing) | Sets the tutorial setting for other-unit movement display. |
| [Config_TutSet_sfx_vol](#call-config-tutset-sfx-vol) | Stores the tutorial sound-effect volume and applies the settings. |
| [Config_TutSet_terInfo](#call-config-tutset-terinfo) | Sets the tutorial setting for terrain information. |
| [Config_TutSet_unitInfo](#call-config-tutset-unitinfo) | Sets the tutorial setting for unit information. |
| [Config_Tutorial](#call-config-tutorial) | Resets the tutorial configuration block to defaults, including internal difficulty ID 1. |
| [CopyMapCamera](#call-copymapcamera) | Saves the map camera's angles and distance so PastMapCamera can return to them. |
| [CpClrNoMoveFlag](#call-cpclrnomoveflag) | Clears the two no-move control bits from a unit’s AI state. |
| [CreateEventCamera](#call-createeventcamera) | Creates an empty event-camera path. Fill it with SetEventCameraAt and SetEventCameraRot keyframes, then play it with StartEventCamera. |
| [CreateNoticeFrame](#call-createnoticeframe) | Creates or updates an animated rectangular highlight around a screen area. |
| [CreateNoticeLFrame](#call-createnoticelframe) | Creates or updates an animated six-edge L-shaped screen highlight. |
| [DefaultDieTalk](#call-defaultdietalk) | Looks up and starts the defeated unit’s default death message when that message exists. For player or inactive units it also selects death music. |
| [DefaultEscapeTalk](#call-defaultescapetalk) | Looks up and starts the current acting unit’s default escape message when available. |
| [DeleteEventCamera](#call-deleteeventcamera) | Removes the event camera and gives control back to the normal map camera. |
| [DeleteNoticeFrame](#call-deletenoticeframe) | Removes the active E_NoticeFrame highlight frame. |
| [Dialog](#call-dialog) | Opens a message dialog and suspends this script until the dialog process releases it. |
| [Dialog2Items](#call-dialog2items) | Opens a choice dialog with 2 entries and suspends the calling script. |
| [Dialog3Items](#call-dialog3items) | Opens a choice dialog with 3 entries and suspends the calling script. |
| [Dialog4Items](#call-dialog4items) | Opens a choice dialog with 4 entries and suspends the calling script. |
| [DialogDirect](#call-dialogdirect) | Opens a message dialog and suspends this script until the dialog process releases it. |
| [DialogGetRes](#call-dialoggetres) | Reads the last dialog result. |
| [DialogResult](#call-dialogresult) | Reads the last dialog result. |
| [DialogSetDefault](#call-dialogsetdefault) | Sets the default selection byte used by dialogs. |
| [DialogTutorial](#call-dialogtutorial) | Opens a tutorial dialog and suspends this script until the dialog process releases it. |
| [DisableSkip](#call-disableskip) | Stops the player from skipping the current event until EnableSkip is called. |
| [DispFreeWholeForce](#call-dispfreewholeforce) | Releases display resources for every actor in a force list. |
| [DispLoadWholeForce](#call-disploadwholeforce) | Loads display resources for every actor in a force list. |
| [DispPreLoadWholeForce](#call-disppreloadwholeforce) | Queues battle-animation assets for every actor in a force list. |
| [Dispos](#call-dispos) | Deploys a group: creates each listed unit that is not on the map yet (or reuses the existing one) and animates the units into place. The script waits for the movement. |
| [DisposAsynchronous](#call-disposasynchronous) | Same as Dispos, but the script continues while the units move. |
| [DisposAuxiliary](#call-disposauxiliary) | Deploys the units the player picked for the second team (SelectAuxiliary) onto the group's tiles and moves them from the reserve to the player force. |
| [DisposContinue](#call-disposcontinue) | Moves the units of a group that already exist to the group's positions, and waits for the movement. It never creates units. |
| [DisposContinueSetMode](#call-disposcontinuesetmode) | Calls DisposContinue(normal_group) if NormalOnly(), otherwise DisposContinue(hard_group) if Hard(), otherwise DisposContinue(fallback_group). |
| [DisposFirst](#call-disposfirst) | Deploys a group onto its exact listed tiles, without searching for a free tile, and waits for the movement. |
| [DisposFirstSetMode](#call-disposfirstsetmode) | Calls DisposFirst(normal_group) if NormalOnly(), otherwise DisposFirst(hard_group) if Hard(), otherwise DisposFirst(fallback_group). |
| [DisposGetGroupCenter](#call-disposgetgroupcenter) | Computes the center of a named deployment group and writes its coordinates into two variables. |
| [DisposSetMode](#call-dispossetmode) | Calls Dispos(normal_group) if NormalOnly(), otherwise Dispos(hard_group) if Hard(), otherwise Dispos(fallback_group). |
| [DisposWarp](#call-disposwarp) | Deploys a named reinforcement group using the warp deployment mode and suspends for active deployment motion. |
| [Dispos_ForEvent](#call-dispos-forevent) | If class_id is empty, uses matching_group without testing the actor. Otherwise tests UnitQueryJIDByPID and chooses matching_group or other_group. Uses InstantDispos when instant is nonzero, otherwise Dispos. |
| [Dispos_ForEventSenerio](#call-dispos-foreventsenerio) | Calls Dispos_ForEvent for PID_SENERIO and JID_MAGE. |
| [Dispos_ForEventTiamat](#call-dispos-foreventtiamat) | Calls Dispos_ForEvent("PID_TIAMAT", "", group, group, instant); the empty class bypasses the actor/class check. |
| [DoorClose](#call-doorclose) | Closes the door at a tile with its animation and waits for it. |
| [DoorOpen](#call-dooropen) | Opens the door at a tile with its animation and waits for it. The door stops blocking movement. |
| [ENVNoisyOff](#call-envnoisyoff) | Returns the ambient sound from the 'noisy' level to normal, over 15 frames (a quarter of a second). |
| [ENVNoisyOn](#call-envnoisyon) | Raises the ambient (environment) sound to its 'noisy' level, over 15 frames (a quarter of a second). |
| [ENVNoisyOn_WhenNotEvtSkip](#call-envnoisyon-whennotevtskip) | Calls ENVNoisyOn only when (GCST() & 1) is zero. |
| [ENVQuietOff](#call-envquietoff) | Returns the ambient sound from the 'quiet' level to normal, over 15 frames (a quarter of a second). |
| [ENVQuietOn](#call-envquieton) | Lowers the ambient sound to its 'quiet' level, over 15 frames (a quarter of a second). |
| [ENVSilentOff](#call-envsilentoff) | Brings back ambient sound silenced by ENVSilentOn, over 15 frames (a quarter of a second). |
| [ENVSilentOff_WhenNotEvtSkip](#call-envsilentoff-whennotevtskip) | Calls ENVSilentOff only when (GCST() & 1) is zero. |
| [ENVSilentOn](#call-envsilenton) | Silences the ambient (environment) sound. |
| [Easy](#call-easy) | Always returns 0 in this US build; do not use this as a working difficulty test. |
| [EffectPlay](#call-effectplay) | Loads and spawns a named scene effect at the supplied position. |
| [EffectWait](#call-effectwait) | Waits for the effect started by EffectPlay to finish. |
| [EnableSkip](#call-enableskip) | Lets the player skip the current event again. |
| [EndFinale](#call-endfinale) | Disables finale mode and its input mask for A/B/X/Y/Z/L/R/Start. |
| [EndMapHoldCursor](#call-endmapholdcursor) | Ends the map cursor-hold process. |
| [EnemyDeadCheck](#call-enemydeadcheck) | Tests whether the enemy force is empty. |
| [EnemyMonkCheck](#call-enemymonkcheck) | Counts enemy-force actors with class JID_PRIEST, JID_BISHOP, or JID_BISHOP_F. |
| [EnemySelfDefenceCheck](#call-enemyselfdefencecheck) | Counts enemy-force actors with PID PID_12_SELFDEFENCE. |
| [EnemyTigerCheck](#call-enemytigercheck) | Counts enemy-force actors with class JID_TIGER. |
| [EnemyUnitCheckByPID](#call-enemyunitcheckbypid) | Counts actors with the specified PID in the enemy force. |
| [EventArrowAppend](#call-eventarrowappend) | Adds a timed waypoint to a map-event arrow’s path. |
| [EventArrowColor](#call-eventarrowcolor) | Sets the arrow’s RGBA color. |
| [EventArrowDelete](#call-eventarrowdelete) | Deletes the map-event arrow process and all of its arrows. |
| [EventArrowFadeOut](#call-eventarrowfadeout) | Requests fade-out of the selected map-event arrow. |
| [EventArrowFocus](#call-eventarrowfocus) | Changes the arrow’s focus-following flag. |
| [EventArrowStart](#call-eventarrowstart) | Starts an arrow path transition from its current progress using the supplied time. |
| [EventArrowWait](#call-eventarrowwait) | Suspends the script while map-event arrows are animating. |
| [EventCameraWait](#call-eventcamerawait) | Waits until the event-camera path has finished playing. |
| [EventGetX](#call-eventgetx) | Returns the X coordinate of the tile that started the current location event (visit, area, chest, door). |
| [EventGetY](#call-eventgety) | Returns the Y coordinate of the tile that started the current location event. |
| [EventQuake](#call-eventquake) | Starts a repeating camera shake. |
| [EventQuakeStop](#call-eventquakestop) | Requests the active camera shake to stop. |
| [FRAME2MSEC](#call-frame2msec) | Converts a 60 Hz frame count to milliseconds. |
| [Fade](#call-fade) | Starts a screen transition. |
| [FadeWait](#call-fadewait) | Yields repeatedly while isFading() is nonzero. |
| [Flash](#call-flash) | Starts a colored screen flash. |
| [FlashWait](#call-flashwait) | Suspends the script while the screen flash is transitioning. |
| [Focus](#call-focus) | Moves the map camera smoothly so it looks at the centre of a tile. |
| [FocusBetweenAB](#call-focusbetweenab) | Requires both PIDs to be deployed, copies the current map camera, computes their tile midpoint using a right shift by 1, adds offsets and calls Focus or InstantFocus. |
| [FocusHardWait](#call-focushardwait) | Like FocusWait, but waits until the camera is within 0.1 tile of its target point and 1 unit of its target angles and distance. |
| [FocusWait](#call-focuswait) | Waits until the map camera has nearly reached its target. |
| [ForceCheckAnyoneDead](#call-forcecheckanyonedead) | Walks force 6 and tests status bit 0x8000 on each actor. |
| [ForceGetCount](#call-forcegetcount) | Counts the units in a force. |
| [ForceGetFirst](#call-forcegetfirst) | Returns the first unit of a force, to walk it with UnitGetNext. |
| [GCST](#call-gcst) | Returns the event system's state flags. |
| [GMapFlagMarkOff](#call-gmapflagmarkoff) | Turns off the selected flag marker on a world-map image. |
| [GMapFlagMarkOffAll](#call-gmapflagmarkoffall) | Removes all flag markers on a world-map image. |
| [GMapFlagMarkOn](#call-gmapflagmarkon) | Creates or resets a flag marker on a world-map image. |
| [GMapPenDarkOnOff](#call-gmappendarkonoff) | Changes the dark-display flag for one world-map pen sequence. |
| [GMapPenDispOnOff](#call-gmappendisponoff) | Shows or hides the world-map pen overlay. |
| [GMapPenDraw1Seq](#call-gmappendraw1seq) | Starts drawing the selected pen sequence on a world-map image. |
| [GMapPenDrawWait](#call-gmappendrawwait) | Suspends this script until the world-map pen drawing operation completes. |
| [GMapPenReset](#call-gmappenreset) | Resets the selected pen sequence on a world-map image. |
| [GMapPointOff](#call-gmappointoff) | Starts removal of the selected point marker on a world-map image. |
| [GMapPointOffAll](#call-gmappointoffall) | Removes all point markers on a world-map image. |
| [GMapPointOn](#call-gmappointon) | Creates a colored point marker on a world-map image. |
| [GMapRegionFlashOnOff](#call-gmapregionflashonoff) | Enables or disables the flashing flag for a world-map region. |
| [GMapRegionFlashOnce](#call-gmapregionflashonce) | Requests a single flash of the selected region overlay on a world-map image. |
| [GMapRegionOff](#call-gmapregionoff) | Turns off the selected region overlay on a world-map image. |
| [GMapRegionOffAll](#call-gmapregionoffall) | Turns off all region overlays on a world-map image. |
| [GMapRegionOn](#call-gmapregionon) | Turns on the selected region overlay on a world-map image. |
| [GMapRegionOnSkipFlash](#call-gmapregiononskipflash) | Turns on without its initial flash the selected region overlay on a world-map image. |
| [GameBind](#call-gamebind) | Freezes the map's normal game flow (phases, cursor, menus) while the script works. |
| [GameUnbind](#call-gameunbind) | Lets the map's game flow continue after GameBind. |
| [GetBattleType](#call-getbattletype) | Returns the flag word of the current or most recent battle. |
| [GetDiedPlayerCount](#call-getdiedplayercount) | Counts actors in force 6 whose death-record flag is set. |
| [GetFukiPosX](#call-getfukiposx) | Reads the X coordinate of the active tutorial speech-bubble display. |
| [GetFukiPosY](#call-getfukiposy) | Reads the Y coordinate of the active tutorial speech-bubble display. |
| [GetLanguage](#call-getlanguage) | Returns the language ID. The US build has no language setting. |
| [GetMapHeight](#call-getmapheight) | Samples the alternate terrain-surface height at the supplied map coordinates. |
| [GetMapHeightBase](#call-getmapheightbase) | Samples the base terrain height at the supplied map coordinates. |
| [GetRank](#call-getrank) | Returns the difficulty. |
| [GetRnd](#call-getrnd) | Draws a random integer using the game random-number generator. |
| [GetTutorial](#call-gettutorial) | Reads whether tutorial help is enabled in configuration. |
| [Hard](#call-hard) | Tests for Hard difficulty. |
| [HideMapCursor](#call-hidemapcursor) | Removes every map cursor shown by ShowMapCursor. |
| [HidePrim2D](#call-hideprim2d) | Starts or ends the scene process that hides 2D primitives. |
| [IndividualWarRecord](#call-individualwarrecord) | Starts the individual war-record display and suspends the calling script. |
| [InstantDispos](#call-instantdispos) | Same as Dispos, but places every unit at once without animation. |
| [InstantDisposContinue](#call-instantdisposcontinue) | Same as DisposContinue, without animation. |
| [InstantDisposContinueSetMode](#call-instantdisposcontinuesetmode) | Calls InstantDisposContinue(normal_group) if NormalOnly(), otherwise InstantDisposContinue(hard_group) if Hard(), otherwise InstantDisposContinue(fallback_group). |
| [InstantDisposFirst](#call-instantdisposfirst) | Same as DisposFirst, without animation. |
| [InstantDisposFirstSetMode](#call-instantdisposfirstsetmode) | Calls InstantDisposFirst(normal_group) if NormalOnly(), otherwise InstantDisposFirst(hard_group) if Hard(), otherwise InstantDisposFirst(fallback_group). |
| [InstantDisposRank](#call-instantdisposrank) | Deploys the difficulty variant of a group at once: adds "_n" to the name on Normal, "_h" on Hard and "_m" on Maniac or Easy, then works like InstantDispos. |
| [InstantDisposSetMode](#call-instantdispossetmode) | Calls InstantDispos(normal_group) if NormalOnly(), otherwise InstantDispos(hard_group) if Hard(), otherwise InstantDispos(fallback_group). |
| [InstantDoorClose](#call-instantdoorclose) | Closes the door at a tile without animation and restores its hit points. |
| [InstantDoorOpen](#call-instantdooropen) | Opens the door at a tile without animation. |
| [InstantFocus](#call-instantfocus) | Points the map camera at the centre of a tile at once. |
| [InstantPastMapCamera](#call-instantpastmapcamera) | Restores the angles and distance saved by CopyMapCamera at once. |
| [InstantRoofClose](#call-instantroofclose) | Puts back the roof at a tile without animation. |
| [InstantRoofOpen](#call-instantroofopen) | Lifts the roof at a tile without animation. |
| [InstantSetMapCamera](#call-instantsetmapcamera) | Sets the map camera's angles and distance at once. |
| [InstantUnitFocusByPID](#call-instantunitfocusbypid) | Resolves a deployed actor, reads its tile, then calls InstantFocus. |
| [InstantUnitFocusOffsetByPID](#call-instantunitfocusoffsetbypid) | Resolves a deployed actor, reads its tile and adds X/Y offsets, then calls InstantFocus. |
| [InstantUnitTransform](#call-instantunittransform) | Changes a unit to the requested transformed/untransformed state immediately and refreshes its display. |
| [IsE3Version](#call-ise3version) | Tests the E3/demo-build condition in this US executable. |
| [ItemGetIndex](#call-itemgetindex) | Resolves an item ID to its numeric item index. |
| [Join](#call-join) | Adds the characters of a deployment group to the player's reserve (force 5), off the map. Characters that already have a unit keep it. |
| [JyokyoMapCapture](#call-jyokyomapcapture) | Captures the status-map display and suspends the script while capture completes. |
| [JyokyoMapDelete](#call-jyokyomapdelete) | Deletes the status-map display. |
| [JyokyoMapEnemyOn](#call-jyokyomapenemyon) | Enables enemy markers on the status map. |
| [JyokyoMapHide](#call-jyokyomaphide) | Hides the status-map display. |
| [JyokyoMapPlayerOn](#call-jyokyomapplayeron) | Enables player markers on the status map. |
| [JyokyoMapShow](#call-jyokyomapshow) | Starts the status-map display. |
| [LocalDieTalkWithBgmChange](#call-localdietalkwithbgmchange) | Disables skip. If flag_name is nonempty and set, calls DefaultDieTalk. Otherwise mutes map music, fades event music over 500 ms, waits 500 ms, plays BGM_DEAD1 and the supplied message. Surrounds that custom branch with environment silence when GetBattleType has bit 0x80000000. Re-enables skip. |
| [MCResult](#call-mcresult) | Reads the last memory-card operation status. |
| [MSEC2FRAME](#call-msec2frame) | Converts milliseconds to 60 Hz frames. |
| [Maniac](#call-maniac) | Tests for Maniac difficulty. |
| [MapFree](#call-mapfree) | Calls _mf1(), yields once, then calls _mf2(). |
| [MapGetSight](#call-mapgetsight) | Reads the visibility-grid byte at a tile. |
| [MapGetTerrain](#call-mapgetterrain) | Reads the terrain ID stored at a map tile. |
| [MapGetUnit](#call-mapgetunit) | Reads the occupancy-grid unit handle at a tile. |
| [MapLoad](#call-mapload) | Loads a map by name and makes it the current map. |
| [MapReload](#call-mapreload) | Reloads the current chapter's map, reapplies its recorded map state (opened doors, visited villages, ...) and points the camera at the saved cursor tile. |
| [MapUpdate](#call-mapupdate) | Recalculates the map's occupancy, movement ranges and danger areas after units or terrain changed. |
| [MindGetItem](#call-mindgetitem) | Calls UnitGetItemShowing(MindGetMe(), item_id). |
| [MindGetMe](#call-mindgetme) | Returns the unit performing the current action (the unit that visited, talked, opened a chest, etc.). |
| [MindGetMind](#call-mindgetmind) | Reads the current map-action ID. |
| [MindGetMoney](#call-mindgetmoney) | Adds gold to the party and starts a reward notification associated with the current acting unit. |
| [MindGetTarget](#call-mindgettarget) | Returns the target of the current action (the unit talked to or fought). |
| [MoviePlay](#call-movieplay) | Plays a movie file and pauses the script until it ends. |
| [NetuzoBattle](#call-netuzobattle) | Resolves and starts a scripted combat exchange between two actors, then suspends the script for the battle process. |
| [NetuzoInit](#call-netuzoinit) | Clears all 32 scripted-strike override slots and resets the scripted-battle counters. |
| [NetuzoSet](#call-netuzoset) | Configures outcome and combat-effect overrides for one scripted strike. |
| [Normal](#call-normal) | Tests for Normal or Easy difficulty. |
| [NormalOnly](#call-normalonly) | Always returns 0 in this US build; do not use this as a working difficulty test. |
| [PIDisAlive](#call-pidisalive) | Looks up a character’s current actor and checks that its dead flag is clear. |
| [PadResetMask](#call-padresetmask) | Removes buttons from the input mask. |
| [PadSetMask](#call-padsetmask) | Adds buttons to the input mask used by event/tutorial control. |
| [PastMapCamera](#call-pastmapcamera) | Turns the camera smoothly back to the angles and distance saved by CopyMapCamera. |
| [PersonGetYellLevel](#call-persongetyelllevel) | Returns the support rank between two characters. |
| [PersonSetYellLevel](#call-personsetyelllevel) | Sets two support partners' support points to the threshold of a rank. |
| [PlayerDeadCheck](#call-playerdeadcheck) | Tests whether the inactive force list is empty. |
| [PlayerEscapeCheck](#call-playerescapecheck) | Tests whether every existing actor in player force 0 or reserve force 5 has the escaped flag. |
| [PlayerEscapeCount](#call-playerescapecount) | Counts escaped actors in player force 0 and reserve force 5. |
| [PreLoadWait](#call-preloadwait) | Yields repeatedly while _pldone() equals zero. |
| [ProcExists](#call-procexists) | Tests whether an engine process with a given name is running. |
| [ProcKill](#call-prockill) | Stops every engine process with a given name. |
| [QueryLesson](#call-querylesson) | Tests whether the active lesson has the given name. |
| [RectAdjustBoundary](#call-rectadjustboundary) | Aligns a rectangle’s source image inside the 608 × 448 layout area. |
| [RectBuild](#call-rectbuild) | Creates an image (rectangle) from its RID definition, attached to the current event. RID_GMAP_... names create a world-map view. |
| [RectFadeIn](#call-rectfadein) | Fades in a rectangle. |
| [RectFadeOut](#call-rectfadeout) | Fades out a rectangle. |
| [RectFadeOutDelete](#call-rectfadeoutdelete) | Fades out and then deletes a rectangle. |
| [RectGet](#call-rectget) | Reads a rectangle property and truncates it to an integer. |
| [RectKill](#call-rectkill) | Removes an image created by RectBuild or RectLeave. |
| [RectLeave](#call-rectleave) | Creates a rectangle/world-map image without attaching it to the current event as its parent. |
| [RectMove](#call-rectmove) | Animates a rectangle/world-map image so a source point is centered at (304, 240) at the requested scale. |
| [RectMoveOffset](#call-rectmoveoffset) | Animates a rectangle/world-map image to an explicit offset and restores its scale to 100%. |
| [RectPreLoad](#call-rectpreload) | Starts loading the image files of a RID definition, so a later RectBuild shows it without delay. |
| [RectSet](#call-rectset) | Sets a rectangle property immediately. |
| [RectSetCurve](#call-rectsetcurve) | Animates one rectangle property between two values. |
| [RectSetPos](#call-rectsetpos) | Sets a rectangle or world-map image’s position immediately. |
| [RegistGlobalFlags](#call-registglobalflags) | Calls the native global registration operation 22 times in fixed order for the original campaign flag list, including repeated reserved names. |
| [RemoveBackdrop](#call-removebackdrop) | Removes the backdrop process. |
| [ResumeEvent](#call-resumeevent) | Continues the event frozen by SuspendEvent. |
| [RoofClose](#call-roofclose) | Puts back the roof at a tile with its animation and waits for it. |
| [RoofOpen](#call-roofopen) | Lifts the roof at a tile with its animation, revealing the building's inside, and waits for it. |
| [SFXPlay](#call-sfxplay) | Plays a sound effect once at full volume. |
| [SallyAddByGroup](#call-sallyaddbygroup) | Adds the tiles of a group to the preparation screen's deployment tiles. |
| [SallyAddByPos](#call-sallyaddbypos) | Appends a deployment-selection position. |
| [SallyGetSurplus](#call-sallygetsurplus) | Reads the deployment surplus recorded when the deployment-selection flow finishes. |
| [SallySetByGroup](#call-sallysetbygroup) | Replaces the preparation screen's deployment tiles with the tiles of a group. |
| [SallySetByPos](#call-sallysetbypos) | Clears the deployment-selection position list, then adds this position. |
| [SelectAuxiliary](#call-selectauxiliary) | Starts the auxiliary-unit selection flow for a deployment group and suspends the calling script. |
| [SetAmbient](#call-setambient) | Sets map ambient lighting color, refreshes the map and yields the script. |
| [SetCamSuspend](#call-setcamsuspend) | Sets the camera-suspension flag for map scenes. |
| [SetCircle](#call-setcircle) | Enables or disables the scene’s unit-circle display setting. |
| [SetDiffuse](#call-setdiffuse) | Sets map diffuse lighting color, refreshes the map and yields the script. |
| [SetEventBattle](#call-seteventbattle) | Selects the special event presentation branch when the next battle animation is initialized. |
| [SetEventCameraAt](#call-seteventcameraat) | Adds a keyframe for the point the event camera looks at. |
| [SetEventCameraPrec](#call-seteventcameraprec) | Sets the divisor applied to later SetEventCameraAt coordinates, allowing positions finer than a tile. |
| [SetEventCameraRot](#call-seteventcamerarot) | Adds a keyframe for the event camera's angles and distance. |
| [SetFog](#call-setfog) | Sets the map’s rendering fog and refreshes its render state. |
| [SetFragile](#call-setfragile) | Adds a breakable terrain entry with the requested HP. |
| [SetGrid](#call-setgrid) | Sets the map-grid display intensity or restores the value saved when scene settings were created. |
| [SetMapCamera](#call-setmapcamera) | Turns the map camera smoothly to new angles and distance; the point it looks at does not change. |
| [SetOnBtFocus](#call-setonbtfocus) | Enables or disables automatic battle-focus behavior. |
| [SetOutLink](#call-setoutlink) | Enables or disables the outer-link portion of the map-link grid and rebuilds that grid. |
| [SetPit](#call-setpit) | Adds a pit terrain entry at the given tile. |
| [SetPullCursor](#call-setpullcursor) | Enables or disables automatic cursor pulling. |
| [SetRock](#call-setrock) | Adds a rolling-rock terrain entry connected to a registered motion path. |
| [SetRoofEnable](#call-setroofenable) | Changes the enabled state of the roof section found at the supplied map position and refreshes the map. |
| [SetSepia](#call-setsepia) | Changes the sepia scene effect setting. |
| [SetShooter](#call-setshooter) | Places a ballista on a tile. |
| [SetSight](#call-setsight) | Sets the fog-of-war/sight mode, recalculates map ranges and refreshes the map. |
| [SetTerrain](#call-setterrain) | Changes the terrain type of one tile. |
| [SetWeather](#call-setweather) | Changes the map weather byte and refreshes weather, lighting and visibility rendering. |
| [SetWhiteBackdrop](#call-setwhitebackdrop) | Starts the solid-white backdrop process. |
| [ShooterBulletCheck](#call-shooterbulletcheck) | Counts the ballista shots spent on the map. |
| [ShowMapCursor](#call-showmapcursor) | Shows the blinking map cursor on a tile. |
| [SoundBossTalkEnd](#call-soundbosstalkend) | Under the same battle-type bit guard, restores environment, fades channel 1 over 750 and continues channel 0 over 750. |
| [SoundBossTalkStart](#call-soundbosstalkstart) | Only when GetBattleType() has bit 0x80000000: silences environment with parameter 30, mutes channel 0 over 750, and plays the supplied track on channel 1. |
| [StaffRoll](#call-staffroll) | Starts the staff credits and suspends the calling script. |
| [StartEventCamera](#call-starteventcamera) | Plays the event-camera path. Keyframes are joined with a smooth curve; if the path has no keyframe at time 0, the camera's current state is added as the first one. |
| [SuspendEvent](#call-suspendevent) | Freezes the running event so another script (a tutorial) can run, saving the event's state. |
| [SysGetRound](#call-sysgetround) | Reads the playthrough ordinal from the clear-data record. |
| [TBoxOpen](#call-tboxopen) | Plays the opening of the chest at a tile and waits for it, and marks the chest as opened. |
| [TTPMEntry](#call-ttpmentry) | Stores a path for a rolling rock in the first free path slot. |
| [TTPMInit](#call-ttpminit) | Clears the 32 registered terrain-motion path slots. |
| [TalkEvent](#call-talkevent) | Opens the conversation window with a message and pauses the script until the conversation ends or reaches a $H hold point. |
| [TalkEventDirect](#call-talkeventdirect) | Starts the supplied event message, or passes it to the existing conversation process. |
| [TalkExist](#call-talkexist) | Tests whether a conversation is still running. |
| [TalkResume](#call-talkresume) | Continues a conversation stopped at a $H hold point and pauses the script again until it ends or reaches the next hold. |
| [TimeiShow](#call-timeishow) | Shows a timed location-name caption. |
| [TimeiShowGMap](#call-timeishowgmap) | Shows a timed location caption using the world-map caption style. |
| [TimeiShowHold](#call-timeishowhold) | Shows a location-name caption that stays visible until explicitly released. |
| [TimeiShowHoldGMap](#call-timeishowholdgmap) | Shows a held location caption using the world-map caption style. |
| [TimeiShowHoldOff](#call-timeishowholdoff) | Starts disappearance of the held caption with this ID. |
| [TimeiShowHoldOffAll](#call-timeishowholdoffall) | Starts disappearance of every held caption. |
| [TrialAddUnit](#call-trialaddunit) | Reads SysGetRound and calls Join for always_T_03 at >=4, always_T_05 at >=6, always_T_07 at >=8, always_T_10 at >=11, and always_T_15 at >=16. These are independent tests: higher counts call all qualifying groups. |
| [Tut3SArrowABAnim](#call-tut3sarrowabanim) | Continuously oscillates a tutorial arrow rectangle along its positive diagonal axis. |
| [Tut3SArrowBCAnim](#call-tut3sarrowbcanim) | Continuously oscillates a tutorial arrow rectangle along its horizontal axis. |
| [Tut3SArrowCAAnim](#call-tut3sarrowcaanim) | Continuously oscillates a tutorial arrow rectangle along its negative diagonal axis. |
| [Tut3SArrowDAnim](#call-tut3sarrowdanim) | Continuously oscillates a tutorial arrow rectangle along its downward vertical axis. |
| [Tut3SArrowUAnim](#call-tut3sarrowuanim) | Continuously oscillates a tutorial arrow rectangle along its upward vertical axis. |
| [TutBasesCreate](#call-tutbasescreate) | Yields until "E_BMapPlph" exists, calls TutorialBasesCreate, then yields while "E_BasesToken" exists. |
| [TutBasesDelete](#call-tutbasesdelete) | Calls TutorialBasesDelete. |
| [TutEntryCommon](#call-tutentrycommon) | Sleeps the tail module with CmSleepScript(""), calls _cmb_mess_load(script_path,"mess/tut.m"), then TutorialCall(entry_name). |
| [TutPadActor](#call-tutpadactor) | Calls _pa(action), then yields while process "E_PadActor" exists. |
| [TutPreLoadWait](#call-tutpreloadwait) | Calls GameBind, externally invokes PreLoadWait, then GameUnbind. |
| [TutSallyCreate](#call-tutsallycreate) | Yields until "E_BMapPlph" exists, calls TutorialSallyCreate, then yields while "E_SallyToken" exists. |
| [TutSallyDelete](#call-tutsallydelete) | Calls TutorialSallyDelete. |
| [TutShow](#call-tutshow) | Starts a tutorial text display. |
| [TutShowKari](#call-tutshowkari) | Shows a temporary tutorial caption with matching appearance and disappearance durations. |
| [TutTalkEvent](#call-tuttalkevent) | Calls GameBind, _tt(message_id), yields while TalkExist(), then GameUnbind. |
| [TutTalkResume](#call-tuttalkresume) | Calls GameBind, _tr(), yields while TalkExist(), then GameUnbind. |
| [TutWaitF](#call-tutwaitf) | Calls GameBind, yields once per loop iteration until the counter reaches frames, then GameUnbind. |
| [TutWaitForNextTaiki](#call-tutwaitfornexttaiki) | Calls taikitk(), then yields while process "E_TaikiToken" exists. |
| [TutWaitForNextTurn](#call-tutwaitfornextturn) | Calls turntk(), then yields while process "E_TurnToken" exists. |
| [TutWaitForNextTurnAfter](#call-tutwaitfornextturnafter) | Calls turnatk(), then yields while process "E_TurnAToken" exists. |
| [TutWaitM](#call-tutwaitm) | Calls GameBind, computes duration_ms * 60 / 1000 with integer arithmetic, yields that many iterations, then GameUnbind. |
| [TutorialBasesCreate](#call-tutorialbasescreate) | Opens the base menu inside a tutorial. |
| [TutorialBasesDelete](#call-tutorialbasesdelete) | Closes the base menu opened by TutorialBasesCreate. |
| [TutorialCall](#call-tutorialcall) | Starts a named function of a loaded tutorial script and stops the AI phase. |
| [TutorialDialog](#call-tutorialdialog) | Calls td(message_id), yields once, then tde(). |
| [TutorialForget](#call-tutorialforget) | Clears a tutorial’s learned mark. |
| [TutorialIn](#call-tutorialin) | Fades with mode 3 for 266 and waits; AllPush; MapFree; TutEntryCommon; SuspendEvent; yields once. |
| [TutorialInit](#call-tutorialinit) | Enables skip, calls _seqini, kills "E_Popup", calls _bmsini, then external Startup and RegistLocationTT. |
| [TutorialInitialize](#call-tutorialinitialize) | Starts tutorial initialization and suspends the calling script until it completes. |
| [TutorialLearn](#call-tutoriallearn) | Marks a tutorial as learned. |
| [TutorialLock](#call-tutoriallock) | Locks a tutorial. |
| [TutorialOut](#call-tutorialout) | Frees "mess/tut.m", frees the last-loaded script, wakes sleeping scripts and resumes the suspended event. |
| [TutorialResume](#call-tutorialresume) | Returns to the tutorial menu after a tutorial ends (the last step of ComebackFunc). |
| [TutorialResumeOut](#call-tutorialresumeout) | MapFree; yield; AllPop; MapReload; UnitDispReload; external Startup; MapUpdate; Fade(2,266); FadeWait. |
| [TutorialSallyCreate](#call-tutorialsallycreate) | Opens the preparations screen inside a tutorial. |
| [TutorialSallyDelete](#call-tutorialsallydelete) | Closes the preparations screen opened by TutorialSallyCreate. |
| [TutorialUnlock](#call-tutorialunlock) | Unlocks a tutorial. |
| [Tutorial_FadeIn](#call-tutorial-fadein) | Disables skip, builds RID_MASK, sets property 9 to 0 and property 2 to -835, then RectSetCurve("RID_MASK",9,0,0,128,100). |
| [Tutorial_FadeOut](#call-tutorial-fadeout) | Calls RectSetCurve("RID_MASK",9,0,160,0,100), kills RID_MASK, then enables skip. |
| [UnitAddItem](#call-unitadditem) | Puts an item in a unit's inventory, silently: weapons, tomes and staves go to the first free weapon slot (0–3), items and accessories to the first free item slot (4–7). |
| [UnitAddSkill](#call-unitaddskill) | Gives a unit a skill. |
| [UnitAnim](#call-unitanim) | Loads and plays a unit animation with the default blend length of 16, replacing an existing scripted animation for that unit. |
| [UnitAnimByPID](#call-unitanimbypid) | Resolves a deployed actor and calls UnitAnim. Missing actor exits without animation. |
| [UnitAnimF](#call-unitanimf) | Loads and plays a unit animation with a chosen transition length, replacing an existing scripted animation for that unit. |
| [UnitAnimFByPID](#call-unitanimfbypid) | Resolves a deployed actor and calls UnitAnimF. Missing actor exits without animation. |
| [UnitBreakup](#call-unitbreakup) | Separates a carrying pair: the carried unit is put back on the map on the carrier's tile. Either unit of the pair can be given. |
| [UnitCanUseIt](#call-unitcanuseit) | Checks whether the unit can use the item in the specified inventory slot. |
| [UnitCheckDeadHere](#call-unitcheckdeadhere) | Returns true exactly when the non-null unit's status has bit 0x8000 set. |
| [UnitCheckDeadHereByPID](#call-unitcheckdeadherebypid) | Looks up the PID and calls UnitCheckDeadHere; a missing actor returns 0. |
| [UnitCheckExists](#call-unitcheckexists) | Checks non-null actor membership in force 0, 1, 2 or 3. It reads status but does not use that value in the decision. |
| [UnitCheckExistsByPID](#call-unitcheckexistsbypid) | Looks up the actor and forwards to UnitCheckExists. |
| [UnitCheckExistsByPID2](#call-unitcheckexistsbypid2) | Looks up the actor and checks UnitCheckExists. |
| [UnitCheckLinked_Breakup](#call-unitchecklinked-breakup) | Returns early for null; otherwise calls UnitBreakup only if status & 0x06 is nonzero. |
| [UnitCheckLinked_BreakupByPID](#call-unitchecklinked-breakupbypid) | Resolves a deployed actor and forwards to UnitCheckLinked_Breakup. |
| [UnitCheckLiveByPID](#call-unitchecklivebypid) | Looks up the PID, then returns false for a null actor, status bit 0x08, or force 6; true otherwise. This is not a deployed-on-map test. |
| [UnitClassChange](#call-unitclasschange) | Plays the class-change (promotion) scene for a unit and promotes it, and waits for it. |
| [UnitClrSkill](#call-unitclrskill) | Removes a skill from a unit. |
| [UnitClrStatus](#call-unitclrstatus) | Clears state flags on a unit. |
| [UnitDead](#call-unitdead) | Plays the death fade-out of a unit's map model (with its sound) and waits for it. |
| [UnitDelItem](#call-unitdelitem) | Removes the item in an inventory slot and closes the gap. |
| [UnitDispReload](#call-unitdispreload) | Unloads and reloads the map models of every unit in forces 0–3, then refreshes their positions. |
| [UnitDontMoveSally](#call-unitdontmovesally) | Locks a unit's starting tile in the preparations: the player cannot swap its position. |
| [UnitDontMoveSallyByPID](#call-unitdontmovesallybypid) | Requires a deployed actor, calls BOTH UnitForcedSally and UnitDontMoveSally. |
| [UnitEscape](#call-unitescape) | Takes a unit off the map: a carried unit is dropped first; a player unit goes to the reserve marked as escaped; a unit of any other force is deleted. |
| [UnitEscapeByPID](#call-unitescapebypid) | Requires a deployed actor, then calls UnitEscape(actor, 0). |
| [UnitFadeIn](#call-unitfadein) | Makes later scripted movement fade units in (they appear as they move). |
| [UnitFadeOff](#call-unitfadeoff) | Ends UnitFadeIn/UnitFadeOut: later movement shows units normally. |
| [UnitFadeOut](#call-unitfadeout) | Makes later scripted movement fade units out (they disappear as they move). |
| [UnitFocus](#call-unitfocus) | Moves the map camera smoothly towards a unit's tile. |
| [UnitFocusByPID](#call-unitfocusbypid) | Resolves a deployed actor, reads its tile, then calls Focus. |
| [UnitFocusOff](#call-unitfocusoff) | Stops the camera from following units during later scripted movement. |
| [UnitFocusOffsetByPID](#call-unitfocusoffsetbypid) | Resolves a deployed actor, reads its tile and adds X/Y offsets, then calls Focus. |
| [UnitFocusOn](#call-unitfocuson) | Makes the camera follow units during later scripted movement (the default). |
| [UnitForcedSally](#call-unitforcedsally) | Makes a unit mandatory in the preparations: the player cannot remove it from the deployment. |
| [UnitForcedSallyByPID](#call-unitforcedsallybypid) | Requires a deployed actor and calls UnitForcedSally. |
| [UnitGet](#call-unitget) | Reads a selected property of a runtime unit. |
| [UnitGetByPID](#call-unitgetbypid) | Finds the current runtime actor for a character ID. |
| [UnitGetByPos](#call-unitgetbypos) | Finds an eligible visible actor occupying a map tile. |
| [UnitGetEquipAccI](#call-unitgetequipacci) | Gets the active accessory slot in the combined inventory numbering. |
| [UnitGetEquipWepI](#call-unitgetequipwepi) | Gets the active equipped-weapon slot index. |
| [UnitGetForce](#call-unitgetforce) | Returns a unit's force. |
| [UnitGetHP](#call-unitgethp) | Returns a unit's current HP. |
| [UnitGetItemCount](#call-unitgetitemcount) | Counts the items a unit carries, weapons included. |
| [UnitGetItemShowing](#call-unitgetitemshowing) | Disables skip; if Comeback() is nonzero, starts Fade(2,166) and waits. Calls _gi(unit,item_id), yields once, then enables skip. |
| [UnitGetItemShowingSub](#call-unitgetitemshowingsub) | Quiets music channel 0, externally calls UnitGetItemShowing(unit,item_id), then restores channel quiet state. |
| [UnitGetMaxHP](#call-unitgetmaxhp) | Returns a unit's maximum HP, including the bonus of the equipped weapon and item, capped by the class. |
| [UnitGetMoveCost](#call-unitgetmovecost) | Reads this unit’s movement cost for a terrain-table entry. |
| [UnitGetNext](#call-unitgetnext) | Returns the next unit in the same force. |
| [UnitGetRace](#call-unitgetrace) | Reports the unit’s beorc/laguz transformation category. |
| [UnitGetStatus](#call-unitgetstatus) | Returns a unit's state flags. |
| [UnitGetWeaponCount](#call-unitgetweaponcount) | Counts the weapons a unit carries (its four weapon slots). |
| [UnitGetX](#call-unitgetx) | Returns a unit's tile X. |
| [UnitGetXByPID](#call-unitgetxbypid) | Resolves a deployed actor and reads UnitGetX. |
| [UnitGetY](#call-unitgety) | Returns a unit's tile Y. |
| [UnitGetYByPID](#call-unitgetybypid) | Resolves a deployed actor and reads UnitGetY. |
| [UnitItemGetValuation](#call-unititemgetvaluation) | Returns a value score for an inventory item, used to pick which item to send away. |
| [UnitItemSendToHouseByPID](#call-unititemsendtohousebypid) | Requires an existing actor with exactly four weapons. Compares valuations for indices 0–3, then sends one entry to storage. |
| [UnitItemSendtoWarehouse](#call-unititemsendtowarehouse) | Sends one inventory item to the convoy. |
| [UnitItemSendtoWarehouseAll](#call-unititemsendtowarehouseall) | Transfers all eight of a unit’s inventory slots to storage, clears the original slots, and compacts the inventory. |
| [UnitItemSetDrop](#call-unititemsetdrop) | Marks one inventory item as dropped when the unit is defeated. |
| [UnitMoveDir](#call-unitmovedir) | Walks a unit along a list of steps, ignoring terrain and other units. |
| [UnitMoveDirByPID](#call-unitmovedirbypid) | Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitMoveDir with the remaining arguments. |
| [UnitMovePos](#call-unitmovepos) | Walks a unit to a tile along a real path. If the tile is taken, the nearest free tile the unit can reach is used. |
| [UnitMovePosByPID](#call-unitmoveposbypid) | Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitMovePos with the remaining arguments. |
| [UnitMoveToUnit](#call-unitmovetounit) | Requires both actors to be deployed. Reads the FIRST actor's X/Y and moves the SECOND actor toward that tile. |
| [UnitMoveToUnitByPID](#call-unitmovetounitbypid) | Resolves both PIDs and calls UnitMoveToUnit(destination, mover). Discards that helper's result. |
| [UnitMoveWait](#call-unitmovewait) | Waits until every unit movement, turn and death/warp animation started by the event has finished. |
| [UnitPairup](#call-unitpairup) | Links two actors using the game’s carrying/pairing operation, first moving the second actor to the tile right of the first. |
| [UnitPutToWarehouse](#call-unitputtowarehouse) | Transfers all eight of a unit’s inventory slots to storage, clears the original slots, and compacts the inventory. |
| [UnitQueryEquip](#call-unitqueryequip) | Tests the equipped bit of an inventory slot. |
| [UnitQueryJID](#call-unitqueryjid) | Tests whether a unit has a given class. |
| [UnitQueryJIDByPID](#call-unitqueryjidbypid) | Looks up the actor; if present, returns UnitQueryJID(actor, class_id). |
| [UnitQueryPID](#call-unitquerypid) | Tests whether a unit is a given character. |
| [UnitReplaceItem](#call-unitreplaceitem) | Replaces the selected inventory slot using an item ID. |
| [UnitRotate](#call-unitrotate) | Turns a unit to face a direction. |
| [UnitRotateByPID](#call-unitrotatebypid) | Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitRotate with the remaining arguments. |
| [UnitRotateToPos](#call-unitrotatetopos) | Requires a deployed actor, compares its tile to the target tile and chooses an eight-direction facing using the original axis/diagonal threshold branches, then calls UnitRotate. |
| [UnitRotateToPosByPID](#call-unitrotatetoposbypid) | Resolves a deployed actor and forwards to UnitRotateToPos. |
| [UnitRotateToUnit](#call-unitrotatetounit) | Requires both actors deployed, reads the target actor's tile and rotates the first actor toward it using UnitRotateToPos. |
| [UnitRotateToUnitByPID](#call-unitrotatetounitbypid) | Resolves both deployed actors and forwards to UnitRotateToUnit. |
| [UnitSearchItem](#call-unitsearchitem) | Finds an item in a unit's inventory. |
| [UnitSet](#call-unitset) | Writes one of the supported mutable unit fields. |
| [UnitSetAccAway](#call-unitsetaccaway) | Unequips the unit's equipped item (band or ring). |
| [UnitSetCpAttackSeq](#call-unitsetcpattackseq) | Changes the attack AI script of a unit. |
| [UnitSetCpHealSeq](#call-unitsetcphealseq) | Changes the healing AI record of a unit. |
| [UnitSetCpMTypeID](#call-unitsetcpmtypeid) | Changes the MTYPE AI table of a unit (how it values targets). |
| [UnitSetCpMoveSeq](#call-unitsetcpmoveseq) | Changes the movement AI script of a unit. |
| [UnitSetCpTypeByPID](#call-unitsetcptypebypid) | Resolves a deployed actor, then sets its attack sequence followed by its movement sequence. |
| [UnitSetEXP](#call-unitsetexp) | Sets a unit's experience. |
| [UnitSetEquip](#call-unitsetequip) | Equips an inventory item. |
| [UnitSetFixed](#call-unitsetfixed) | Sets or clears the unit’s fixed-state flag. |
| [UnitSetHP](#call-unitsethp) | Sets a unit's current HP. |
| [UnitSetHold](#call-unitsethold) | Changes the shared scene unit-hold setting. |
| [UnitSetPos](#call-unitsetpos) | Places a unit on a tile at once. If the tile is taken, the nearest free tile is used. |
| [UnitSetPosDir](#call-unitsetposdir) | For a non-null actor, sets its tile then immediately rotates it unless direction is -1. |
| [UnitSetPosDirByPID](#call-unitsetposdirbypid) | Resolves a deployed actor, sets its tile, and immediately rotates unless direction is -1. |
| [UnitSetPosDirByPos](#call-unitsetposdirbypos) | Finds the actor at the source tile, moves it to the destination, and immediately rotates unless direction is -1. |
| [UnitSetStatus](#call-unitsetstatus) | Sets state flags on a unit. |
| [UnitSetWeaponAway](#call-unitsetweaponaway) | Unequips the unit's weapon. |
| [UnitSetWeaponAwayByPID](#call-unitsetweaponawaybypid) | Resolves a deployed actor and returns UnitSetWeaponAway(actor). |
| [UnitTackle](#call-unittackle) | Moves the target away from the acting unit and starts shove/smite motion. |
| [UnitTransferToForce](#call-unittransfertoforce) | Moves a unit to another force, for example to recruit it (force 0) or turn it into an ally (2). |
| [UnitTransferToForceByPID](#call-unittransfertoforcebypid) | Resolves the actor, applies the UnitCheckLiveByPID-equivalent null/status-0x08/force-6 test, then calls UnitTransferToForce. |
| [UnitTransform](#call-unittransform) | Changes a unit to the requested transformed/untransformed state with its transformation animation. |
| [UnitTstSkill](#call-unittstskill) | Tests whether a unit holds a skill. |
| [UnitWalkDir](#call-unitwalkdir) | Sets the direction bits used by subsequent scene walking. |
| [UnitWalkSlow](#call-unitwalkslow) | Enables or disables slow walking for subsequent scene movement. |
| [UnitWarpOut](#call-unitwarpout) | Plays the Warp effect on a unit and waits for it. |
| [UnitsInitialize](#call-unitsinitialize) | Removes every unit: all forces are emptied and all unit slots freed. |
| [UnitsPop](#call-unitspop) | Restores the units saved by UnitsPush, refreshes the map and reloads the unit models. Frees the buffer. |
| [UnitsPopWithoutMap](#call-unitspopwithoutmap) | Same as UnitsPop, without the map refresh. |
| [UnitsPush](#call-unitspush) | Saves every unit (and the forge records) into a temporary buffer, then empties the forces. |
| [UnitsPush_Uninitialize](#call-unitspush-uninitialize) | Saves every unit (and the forge records) into the temporary buffer, leaving the units in place. |
| [VisitIn](#call-visitin) | Does nothing (kept for the visit-event scripts). |
| [VisitOut](#call-visitout) | Closes the village at a tile after a visit: plays its closing animation, waits for it and marks the village as visited. |
| [WaitF](#call-waitf) | Pauses the script for a number of frames (60 per second). |
| [WaitM](#call-waitm) | Pauses the script for a time in milliseconds. |
| [WaitPressAnyKey](#call-waitpressanykey) | Suspends the calling script until the input-wait process completes after a key press. |
| [WarRecord](#call-warrecord) | Starts the war-record display and suspends the calling script. |
| [WipeEnd](#call-wipeend) | Resets the screen-wipe state to idle. |
| [WipeIn](#call-wipein) | Starts a screen wipe in. |
| [WipeOut](#call-wipeout) | Starts a screen wipe out. |
| [WipeWait](#call-wipewait) | Suspends the script while a wipe-in or wipe-out transition is active. |
| [_bmsini](#call--bmsini) | Resets the chapter for a tutorial: chapter number 0 (so the convoy is available), turn 1, the player controls force 0 and the computer forces 1–3, 1,000 gold, chapter flags and gf_complete/gf_gameover cleared, no units, empty convoy, no forge records, map state cleared. |
| [_cmb_mess_load](#call--cmb-mess-load) | Loads a script file and a message file together (the step behind TutEntryCommon). |
| [_gi](#call--gi) | Gives an item to a unit and shows the result window (the step behind UnitGetItemShowing). |
| [_intr](#call--intr) | Runs the chapter-checkpoint save sequence and suspends the calling script until it finishes. |
| [_mf1](#call--mf1) | First step of MapFree: releases the map's objects if a map is loaded. |
| [_mf2](#call--mf2) | Second step of MapFree: frees the current map. |
| [_pa](#call--pa) | Plays a scripted controller input (the 'pad actor' that moves the cursor and presses buttons in tutorials). Each character is one step: a one-frame press, then a pause until the next step. |
| [_pldone](#call--pldone) | Tests whether files queued for loading (RectPreLoad, PreLoad) are ready. |
| [_seqini](#call--seqini) | Clears the map for a tutorial: removes conversations, images, scripted input, the preparations, AI phase and phase banner, the notice frame and the unit models. |
| [_tr](#call--tr) | Continues a held tutorial conversation (the step behind TutTalkResume). |
| [_tt](#call--tt) | Starts a tutorial conversation with a message (the step behind TutTalkEvent). |
| [clr](#call-clr) | Clears a flag. |
| [dump](#call-dump) | Prints all eight force lists and their units to debug output. |
| [get](#call-get) | Reads a flag. |
| [global](#call-global) | Registers a campaign flag in the lowest free slot of the flag table and clears its bit. The game registers its campaign flags once at boot. |
| [intplGetValue](#call-intplgetvalue) | Computes one interpolated value without starting an animation. |
| [isFading](#call-isfading) | Tests whether a screen fade started by Fade is still running. |
| [isFlash](#call-isflash) | Tests whether the screen flash is in either transition phase. |
| [isWipe](#call-iswipe) | Tests whether a wipe-in or wipe-out transition is active. |
| [regist](#call-regist) | Registers a chapter flag in the highest free slot of the 96-slot flag table. The slot's bit is left as it is (chapter start clears these slots). |
| [report](#call-report) | Writes text to the game’s debug-report output. |
| [set](#call-set) | Sets a flag. |
| [taikitk](#call-taikitk) | Starts a waiting token that lasts until a unit's next Wait command (E_TaikiToken). |
| [td](#call-td) | Opens a tutorial dialog with a message and pauses the script until it closes. |
| [tde](#call-tde) | Sets the 'event suspended' state flag again after a tutorial dialog cleared it (the last step of TutorialDialog). |
| [turnatk](#call-turnatk) | Starts a waiting token that lasts until the next end of turn (E_TurnAToken). |
| [turntk](#call-turntk) | Starts a waiting token that lasts until the next turn change (E_TurnToken). |

## Detailed entries

<a id="call-achieveset"></a>
### AchieveSet

`AchieveSet(message_id, amount)`

Records one line of the chapter's bonus-experience results: a label and an amount. Used inside achievement (type 12) functions, which the game runs at chapter end; each function that runs fills the next line.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID of the line's label, such as Ms_ach_02_turn. |
| `amount` | Bonus experience for this line. |

**Returns:** 1.

**Usage:** The amount is halved on Maniac and multiplied by 1.5 on Easy (rounded down). This is not gold; use BMSetMoney for money.

[Back to index](#function-index)

<a id="call-addtt"></a>
### AddTT

`AddTT(x, y, type, subtype, value_1, value_2)`

Adds a raw entry to the map's special-terrain list.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |
| `type` | Entry type: 4 breakable wall, 7 ballista, 9 pit, 10 rolling rock. Prefer SetFragile, SetShooter, SetPit and SetRock. |
| `subtype` | Type-specific byte. |
| `value_1` | First type-specific state byte. |
| `value_2` | Second type-specific state byte. |

**Returns:** 1.

**Usage:** Low-level: the dedicated calls fill the fields correctly. It does not change the map's look.

[Back to index](#function-index)

<a id="call-allpop"></a>
### AllPop

`AllPop()`

Restores the game state saved by AllPush and frees the buffer.

**Arguments:** none.

**Returns:** 1.

**Usage:** Chapter flags set during the tutorial are cleared first. Map and models are not reloaded: TutorialResumeOut follows it with MapReload and UnitDispReload.

[Back to index](#function-index)

<a id="call-allpush"></a>
### AllPush

`AllPush()`

Saves the whole game state into the temporary buffer (party data, camera, every unit, convoy, forge records and map state), then resets units, chapter flags, map state, convoy and forge records.

**Arguments:** none.

**Returns:** 1.

**Usage:** Used by TutorialIn so a tutorial can run in a clean state. Same shared buffer as UnitsPush.

[Back to index](#function-index)

<a id="call-allunitescape"></a>
### AllUnitEscape

`AllUnitEscape()`

Removes every unit of forces 0–3 from the map: carried units are dropped first, player units go to the reserve marked as escaped, all other units are deleted.

**Arguments:** none.

**Returns:** 1.

**Usage:** The map is refreshed afterwards.

[Back to index](#function-index)

<a id="call-allunitsbreakup"></a>
### AllUnitsBreakup

`AllUnitsBreakup()`

Walks force 0 only, bounded by ForceGetCount(0), and calls UnitCheckLinked_Breakup for each actor until count exhaustion or a null next actor.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** Despite the name, it does not traverse all eight forces.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-arcfree"></a>
### ArcFree

`ArcFree(resource_path)`

Releases one reference to a relocatable game resource.

| Argument | Meaning and restrictions |
|---|---|
| `resource_path` | Game resource path, for example "mess/tut.m". Use lowercase and the same path for its matching load/release. |

**Returns:** 1.

**Usage:** Keep load and release ownership balanced. ArcFree may lowercase the supplied path in place. Do not release a resource while another sequence still uses it.

[Back to index](#function-index)

<a id="call-arcload"></a>
### ArcLoad

`ArcLoad(resource_path)`

Loads a relocatable game resource.

| Argument | Meaning and restrictions |
|---|---|
| `resource_path` | Game resource path, for example "mess/tut.m". Use lowercase and the same path for its matching load/release. |

**Returns:** 1.

**Usage:** Keep load and release ownership balanced. ArcFree may lowercase the supplied path in place. Do not release a resource while another sequence still uses it.

[Back to index](#function-index)

<a id="call-arenadump"></a>
### ArenaDump

`ArenaDump()`

Prints memory-arena usage to debug output.

**Arguments:** none.

**Returns:** No useful script result; call for its side effect.

**Usage:** Useful for debugging resource-heavy scripts; it does not display an in-game menu.

[Back to index](#function-index)

<a id="call-bgmcont"></a>
### BGMCont

`BGMCont(channel, duration_ms)`

Resumes a channel paused by BGMMute and fades it back to its remembered volume.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks. |
| `duration_ms` | Fade-in time in milliseconds. |

**Returns:** 1.

**Usage:** On channel 0 it also clears the 'map music stopped' mark and fades the channel's volume to 100, so the map music returns even if it was only muted.

[Back to index](#function-index)

<a id="call-bgmfadein"></a>
### BGMFadeIn

`BGMFadeIn(channel, bgm_id, duration_ms)`

Starts a track on a music channel, fading it in from silence to full volume. If any channel is already playing this same track, nothing changes.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks. |
| `bgm_id` | BGM_... track name from the sound data. |
| `duration_ms` | Fade-in time in milliseconds (vanilla uses 500–1500). |

**Returns:** 1; 0 only if bgm_id is not a valid string.

**Usage:** While the event is being skipped or a conversation skip, no music starts. Channel 0 clears the 'map music stopped' mark.

[Back to index](#function-index)

<a id="call-bgmfadeout"></a>
### BGMFadeOut

`BGMFadeOut(channel, duration_ms)`

Fades a playing channel to silence and stops it.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks. |
| `duration_ms` | Fade time in milliseconds; 0 or less stops the track at once. |

**Returns:** 1.

**Usage:** Does nothing on a silent channel, and does not restart a fade-out already running. On channel 0 it marks the map music as stopped by the event, so the map's own music does not come back until a channel-0 play or BGMCont.

[Back to index](#function-index)

<a id="call-bgmmute"></a>
### BGMMute

`BGMMute(channel, duration_ms)`

Fades a playing channel to silence and pauses it, remembering its volume and position so BGMCont can bring it back.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks. |
| `duration_ms` | Fade time in milliseconds; 0 or less pauses at once. |

**Returns:** 1.

**Usage:** Used to hold the map music while an event track plays (see BgmChangeEvt_MapToEvt1). On channel 0 it also marks the map music as stopped by the event.

[Back to index](#function-index)

<a id="call-bgmplay"></a>
### BGMPlay

`BGMPlay(channel, bgm_id)`

Starts a track on a music channel at full volume. If any channel is already playing this same track, nothing changes. The channel's previous track is stopped.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks. |
| `bgm_id` | BGM_... track name from the sound data. |

**Returns:** 1; 0 only if bgm_id is not a valid string.

**Usage:** While the event is being skipped, or while a conversation is being skipped, no music starts. Starting a track on channel 0 clears the 'map music stopped by the event' mark that BGMStop/BGMFadeOut/BGMMute set.

[Back to index](#function-index)

<a id="call-bgmplayvol"></a>
### BGMPlayVol

`BGMPlayVol(channel, bgm_id, volume)`

Starts a track on a music channel at the given volume.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks. |
| `bgm_id` | BGM_... track name from the sound data. |
| `volume` | Volume 0–100 (100 = full). Vanilla ambient tracks use 60–85. |

**Returns:** 1; 0 only if bgm_id is not a valid string.

**Usage:** Same duplicate-track, skip and channel-0 rules as BGMPlay.

[Back to index](#function-index)

<a id="call-bgmquietoff"></a>
### BGMQuietOff

`BGMQuietOff(channel)`

Ends the music 'quiet' state started by BGMQuietOn, restoring the level over about a quarter of a second.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Ignored. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-bgmquieton"></a>
### BGMQuietOn

`BGMQuietOn(channel)`

Starts lowering the music for a dialogue box or a reward window (the game's music 'quiet' state), over about a quarter of a second.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Ignored: the quiet state applies to the music as a whole. |

**Returns:** 1.

**Usage:** Pair with BGMQuietOff. UnitGetItemShowingSub wraps an item reward in this pair.

[Back to index](#function-index)

<a id="call-bgmresume"></a>
### BGMResume

`BGMResume()`

Restores map-music channel 0 to volume 100 over 200 ms and starts a 200 ms countdown on active event-music channels 1–3.

**Arguments:** none.

**Returns:** 1.

**Usage:** Use when leaving an event-music sequence and returning to the map soundtrack.

[Back to index](#function-index)

<a id="call-bgmsetvol"></a>
### BGMSetVol

`BGMSetVol(channel, volume, duration_ms)`

Changes a channel's volume gradually.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks. |
| `volume` | Target volume 0–100. |
| `duration_ms` | Transition time in milliseconds; at least one frame. |

**Returns:** 1.

**Usage:** Works on any channel, playing or not; it only changes the channel's volume level.

[Back to index](#function-index)

<a id="call-bgmstop"></a>
### BGMStop

`BGMStop(channel)`

Stops a playing channel almost immediately (a one-millisecond fade).

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks. |

**Returns:** 1.

**Usage:** Same channel-0 rule as BGMFadeOut. Does nothing on a silent channel.

[Back to index](#function-index)

<a id="call-bmgetchapter"></a>
### BMGetChapter

`BMGetChapter()`

Returns the current chapter number.

**Arguments:** none.

**Returns:** Chapter number (Prologue = 1, the internal file number).

[Back to index](#function-index)

<a id="call-bmgetmoney"></a>
### BMGetMoney

`BMGetMoney()`

Returns the party's gold.

**Arguments:** none.

**Returns:** Gold amount.

[Back to index](#function-index)

<a id="call-bmgetphase"></a>
### BMGetPhase

`BMGetPhase()`

Returns whose phase it is.

**Arguments:** none.

**Returns:** Phase force: 0 player, 1 enemy, 2 allied, 3 other.

[Back to index](#function-index)

<a id="call-bmgetturn"></a>
### BMGetTurn

`BMGetTurn()`

Returns the turn number.

**Arguments:** none.

**Returns:** Current turn (1 on the first turn).

[Back to index](#function-index)

<a id="call-bmgetvalue"></a>
### BMGetValue

`BMGetValue(field_index)`

Reads a signed 16-bit field from battle-map state.

| Argument | Meaning and restrictions |
|---|---|
| `field_index` | Halfword index in battle-map state. Use an index from an existing matching chapter; this is not a named flag slot. |

**Returns:** Signed value from -32768 through 32767.

**Usage:** Advanced raw accessor; no bounds check. Prefer a dedicated accessor when available.

[Back to index](#function-index)

<a id="call-bmsetmoney"></a>
### BMSetMoney

`BMSetMoney(value)`

Sets the party's gold.

| Argument | Meaning and restrictions |
|---|---|
| `value` | New gold amount; anything above 9,999,999 is stored as 9,999,999. |

**Returns:** The value passed in (before the cap).

**Usage:** The difference is also added to the game's lifetime 'gold earned' or 'gold spent' totals.

[Back to index](#function-index)

<a id="call-bmsetphase"></a>
### BMSetPhase

`BMSetPhase(force)`

Overwrites the current-phase value.

| Argument | Meaning and restrictions |
|---|---|
| `force` | Phase force 0–3. |

**Returns:** No meaningful value; call it for its effect.

**Usage:** Only changes the stored value: no phase change, phase banner or phase events happen.

[Back to index](#function-index)

<a id="call-bmsettanto"></a>
### BMSetTanto

`BMSetTanto(player_control, enemy_control, force_2_control, force_3_control)`

Sets who controls each of the four active map forces.

| Argument | Meaning and restrictions |
|---|---|
| `player_control` | Control mode: 0 none, 1 player control, 2 computer control. |
| `enemy_control` | Control mode: 0 none, 1 player control, 2 computer control. |
| `force_2_control` | Control mode: 0 none, 1 player control, 2 computer control. |
| `force_3_control` | Control mode: 0 none, 1 player control, 2 computer control. |

**Returns:** 1.

**Usage:** Changes shared phase/control state. Restore all four values for the chapter when leaving a staged sequence.

[Back to index](#function-index)

<a id="call-bmsetterm"></a>
### BMSetTerm

`BMSetTerm(term_index, text)`

Replaces one battle-map term string.

| Argument | Meaning and restrictions |
|---|---|
| `term_index` | Term slot from the original chapter; slots hold 12 bytes each. |
| `text` | At most 11 encoded bytes plus the string terminator. Null leaves the term unchanged. |

**Returns:** 1.

**Usage:** Copies without a length check. Use short ASCII text or count encoded bytes, not Unicode characters.

[Back to index](#function-index)

<a id="call-bmsetturn"></a>
### BMSetTurn

`BMSetTurn(turn)`

Overwrites the turn counter.

| Argument | Meaning and restrictions |
|---|---|
| `turn` | New turn number (kept as a 16-bit value). |

**Returns:** No meaningful value; call it for its effect.

**Usage:** Turn-based events are checked against the new value from the next turn change; none fire immediately.

[Back to index](#function-index)

<a id="call-bmsetvalue"></a>
### BMSetValue

`BMSetValue(field_index, value)`

Writes a 16-bit field in battle-map state.

| Argument | Meaning and restrictions |
|---|---|
| `field_index` | Same halfword index used by BMGetValue; not bounds-checked. |
| `value` | Value to store. Only the low 16 bits are retained. |

**Returns:** The supplied value, before truncation.

**Usage:** Do not invent indices. This edits shared chapter state.

[Back to index](#function-index)

<a id="call-beginfinale"></a>
### BeginFinale

`BeginFinale()`

Enables finale mode and its input mask for A/B/X/Y/Z/L/R/Start.

**Arguments:** none.

**Returns:** 1.

**Usage:** Pair BeginFinale and EndFinale around ending sequences; neither call starts the credits by itself.

[Back to index](#function-index)

<a id="call-beginmapholdcursor"></a>
### BeginMapHoldCursor

`BeginMapHoldCursor()`

Starts the map cursor-hold process.

**Arguments:** none.

**Returns:** 0.

[Back to index](#function-index)

<a id="call-bgmchangeevt-maptoevt1"></a>
### BgmChangeEvt_MapToEvt1

`BgmChangeEvt_MapToEvt1(bgm_id, duration_ms)`

Calls BGMMute(0, duration), waits the full duration with WaitM, then BGMPlay(1, bgm_id).

| Argument | Meaning and restrictions |
|---|---|
| `bgm_id` | Existing BGM_... track ID; not an audio filename. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-bgmchangeevt-maptoevt2"></a>
### BgmChangeEvt_MapToEvt2

`BgmChangeEvt_MapToEvt2(bgm_id, duration_ms)`

Calls BGMMute(0, duration), waits duration >> 1 with WaitM, then BGMPlay(1, bgm_id).

| Argument | Meaning and restrictions |
|---|---|
| `bgm_id` | Existing BGM_... track ID; not an audio filename. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-bgmchangeevt-maptoevt3"></a>
### BgmChangeEvt_MapToEvt3

`BgmChangeEvt_MapToEvt3(bgm_id, duration_ms)`

Calls BGMMute(0, duration), waits no time, then BGMPlay(1, bgm_id).

| Argument | Meaning and restrictions |
|---|---|
| `bgm_id` | Existing BGM_... track ID; not an audio filename. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-bgmcontevt-evttomap1"></a>
### BgmContEvt_EvtToMap1

`BgmContEvt_EvtToMap1(fade_duration, resume_duration)`

Calls BGMFadeOut(1, fade_duration), waits the full fade_duration with WaitM, then BGMCont(0, resume_duration).

| Argument | Meaning and restrictions |
|---|---|
| `fade_duration` | Milliseconds passed to BGMFadeOut and the helper's wait. |
| `resume_duration` | Transition duration passed to BGMCont. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-bgmcontevt-evttomap2"></a>
### BgmContEvt_EvtToMap2

`BgmContEvt_EvtToMap2(fade_duration, resume_duration)`

Calls BGMFadeOut(1, fade_duration), waits fade_duration >> 1 with WaitM, then BGMCont(0, resume_duration).

| Argument | Meaning and restrictions |
|---|---|
| `fade_duration` | Milliseconds passed to BGMFadeOut and the helper's wait. |
| `resume_duration` | Transition duration passed to BGMCont. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-bgmcontevt-evttomap3"></a>
### BgmContEvt_EvtToMap3

`BgmContEvt_EvtToMap3(fade_duration, resume_duration)`

Calls BGMFadeOut(1, fade_duration), waits no time, then BGMCont(0, resume_duration).

| Argument | Meaning and restrictions |
|---|---|
| `fade_duration` | Milliseconds passed to BGMFadeOut and the helper's wait. |
| `resume_duration` | Transition duration passed to BGMCont. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-builddestruction"></a>
### BuildDestruction

`BuildDestruction(x, y)`

Destroys the village or house at a tile: the camera moves to it, the ruin animation plays and the script waits for it.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 after the animation; 0 if none is found, or during an event skip (the building turns into ruins at once).

**Usage:** The tile may be the building or a tile next to it. A destroyed village can no longer be visited. The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-buildinstanim"></a>
### BuildInstAnim

`BuildInstAnim(x, y, mode)`

Plays or sets the two-state animation of an animated map prop at a tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |
| `mode` | 0 plays forward and keeps the end state; 1 plays backward and keeps the start state; 2 plays once without changing the kept state; 3 jumps to the start state; 4 jumps to the end state. |

**Returns:** 1; 0 if no animated prop is at the tile, or for mode 2 during an event skip.

**Usage:** Modes 0 and 1 do not wait. While the event is being skipped modes 0 and 1 jump to their final state. The kept state is recorded in the map state.

[Back to index](#function-index)

<a id="call-buildinsthide"></a>
### BuildInstHide

`BuildInstHide(x, y)`

Hides a hideable map prop at a tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 if one was found; 0 otherwise.

**Usage:** The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-buildinstshow"></a>
### BuildInstShow

`BuildInstShow(x, y)`

Shows a hideable map prop at a tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 if one was found; 0 otherwise.

**Usage:** The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-chaptermovieplay"></a>
### ChapterMoviePlay

`ChapterMoviePlay(chapter)`

Plays the movie of a chapter and pauses the script until it ends.

| Argument | Meaning and restrictions |
|---|---|
| `chapter` | Chapter number whose movie is played. It does not change the current chapter. |

**Returns:** 1; 0 during an event skip (nothing is played).

[Back to index](#function-index)

<a id="call-check"></a>
### Check

`Check()`

Tests whether a base-conversation event is being evaluated for availability rather than being played.

**Arguments:** none.

**Returns:** 1 during the availability check; 0 while playing the conversation.

**Usage:** In an availability check, return the condition and avoid dialogue, rewards, or other lasting changes. Use inside a base-conversation event.

[Back to index](#function-index)

<a id="call-checkattackable"></a>
### CheckAttackable

`CheckAttackable(unit)`

Tests whether this unit can reach a position from which its equipped weapon can attack an eligible enemy.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |

**Returns:** 1 if an attack opportunity exists; 0 otherwise, including missing unit, no weapon, or disqualifying status.

**Usage:** Includes movement and weapon range; this is not a test of a particular target.

[Back to index](#function-index)

<a id="call-cmfreescript"></a>
### CmFreeScript

`CmFreeScript()`

Unloads the most recently loaded script file and removes its named functions.

**Arguments:** none.

**Returns:** 1; 0 if no script is loaded.

**Usage:** Always the last one loaded: there is no name argument.

[Back to index](#function-index)

<a id="call-cmloadscript"></a>
### CmLoadScript

`CmLoadScript(script_path)`

Loads a CMB script module and makes its exported functions available.

| Argument | Meaning and restrictions |
|---|---|
| `script_path` | Existing game resource path to a .cmb module. Use the path form already used by the project’s module-loading sequence. |

**Returns:** 1.

**Usage:** Load before calling its exports; free modules in reverse load order with CmFreeScript. This loads a compiled game resource, not a .fe9s editor file.

[Back to index](#function-index)

<a id="call-cmsleepscript"></a>
### CmSleepScript

`CmSleepScript(module_name)`

Suspends a module’s event enumeration and temporarily removes its exported functions.

| Argument | Meaning and restrictions |
|---|---|
| `module_name` | Name stored in the loaded CMB header. Empty string or 0 selects the last-loaded module. |

**Returns:** 1 when a module is found; 0 if a named module is absent.

**Usage:** The module stays allocated. CmWakeupScripts restores sleeping modules and their exports.

[Back to index](#function-index)

<a id="call-cmwakeupscripts"></a>
### CmWakeupScripts

`CmWakeupScripts()`

Wakes every script file put to sleep by CmSleepScript and makes its named functions callable again.

**Arguments:** none.

**Returns:** No meaningful value; call it for its effect.

[Back to index](#function-index)

<a id="call-comeback"></a>
### Comeback

`Comeback()`

Consumes the current event skip/cancel state and performs its cleanup.

**Arguments:** none.

**Returns:** 1 when skip/cancel cleanup ran; 0 when there was nothing to consume.

**Usage:** This changes state. Do not replace it with a read-only condition or call repeatedly to “peek.”

[Back to index](#function-index)

<a id="call-comebackfunc"></a>
### ComebackFunc

`ComebackFunc()`

SuspendEvent; yield; MapFree; yield; external Startup; TutorialResume.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-complete18"></a>
### Complete18

`Complete18(part)`

Ends a multipart chapter segment and selects its next chapter-flow state.

| Argument | Meaning and restrictions |
|---|---|
| `part` | 1 selects continuation state 5; 2 selects 6; 3 selects 7. Other values select 0. |

**Returns:** 1.

**Usage:** Special-purpose chapter 18 flow; not a general victory replacement.

[Back to index](#function-index)

<a id="call-config-tutget-sfx-vol"></a>
### Config_TutGet_sfx_vol

`Config_TutGet_sfx_vol()`

Reads the stored tutorial sound-effect volume byte.

**Arguments:** none.

**Returns:** Stored volume value.

[Back to index](#function-index)

<a id="call-config-tutset-xinfopage"></a>
### Config_TutSet_XinfoPage

`Config_TutSet_XinfoPage(page)`

Sets the tutorial information-page selection.

| Argument | Meaning and restrictions |
|---|---|
| `page` | Page index stored as an 8-bit value; use a page available in this tutorial. |

**Returns:** No useful script result; call for its side effect.

[Back to index](#function-index)

<a id="call-config-tutset-otheridoshowing"></a>
### Config_TutSet_otheridoshowing

`Config_TutSet_otheridoshowing(enabled)`

Sets the tutorial setting for other-unit movement display.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | Exactly 1 enables it; every other value disables it. |

**Returns:** No useful script result; call for its side effect.

[Back to index](#function-index)

<a id="call-config-tutset-sfx-vol"></a>
### Config_TutSet_sfx_vol

`Config_TutSet_sfx_vol(volume)`

Stores the tutorial sound-effect volume and applies the settings.

| Argument | Meaning and restrictions |
|---|---|
| `volume` | Volume byte; use the configuration’s existing range. Values are truncated to 8 bits. |

**Returns:** No useful script result; call for its side effect.

[Back to index](#function-index)

<a id="call-config-tutset-terinfo"></a>
### Config_TutSet_terInfo

`Config_TutSet_terInfo(enabled)`

Sets the tutorial setting for terrain information.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | Exactly 1 enables it; every other value disables it. |

**Returns:** No useful script result; call for its side effect.

[Back to index](#function-index)

<a id="call-config-tutset-unitinfo"></a>
### Config_TutSet_unitInfo

`Config_TutSet_unitInfo(enabled)`

Sets the tutorial setting for unit information.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | Exactly 1 enables it; every other value disables it. |

**Returns:** No useful script result; call for its side effect.

[Back to index](#function-index)

<a id="call-config-tutorial"></a>
### Config_Tutorial

`Config_Tutorial()`

Resets the tutorial configuration block to defaults, including internal difficulty ID 1.

**Arguments:** none.

**Returns:** No useful script result; call for its side effect.

**Usage:** This is not a “show tutorial” toggle. It also overwrites difficulty and other settings; use the individual setters for a small change.

[Back to index](#function-index)

<a id="call-copymapcamera"></a>
### CopyMapCamera

`CopyMapCamera()`

Saves the map camera's angles and distance so PastMapCamera can return to them.

**Arguments:** none.

**Returns:** 1.

**Usage:** Saves angles and distance only, not the point looked at. One saved state; a new copy replaces it.

[Back to index](#function-index)

<a id="call-cpclrnomoveflag"></a>
### CpClrNoMoveFlag

`CpClrNoMoveFlag(unit)`

Clears the two no-move control bits from a unit’s AI state.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |

**Returns:** Updated AI control word; 0 for an invalid unit. A zero result can also mean all bits are now clear.

[Back to index](#function-index)

<a id="call-createeventcamera"></a>
### CreateEventCamera

`CreateEventCamera()`

Creates an empty event-camera path. Fill it with SetEventCameraAt and SetEventCameraRot keyframes, then play it with StartEventCamera.

**Arguments:** none.

**Returns:** 1.

**Usage:** Holds up to 256 keyframes. Remove it with DeleteEventCamera when the scene ends.

[Back to index](#function-index)

<a id="call-createnoticeframe"></a>
### CreateNoticeFrame

`CreateNoticeFrame(x, y, width, height)`

Creates or updates an animated rectangular highlight around a screen area.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Screen-space left edge. |
| `y` | Screen-space top edge. |
| `width` | Width in screen coordinates. |
| `height` | Height in screen coordinates. |

**Returns:** 0.

**Usage:** Remove it with DeleteNoticeFrame. Coordinates are not map tiles.

[Back to index](#function-index)

<a id="call-createnoticelframe"></a>
### CreateNoticeLFrame

`CreateNoticeLFrame(x, y, width_1, width_2, height_1, height_2, orientation)`

Creates or updates an animated six-edge L-shaped screen highlight.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Left edge of the complete shape. |
| `y` | Top edge of the complete shape. |
| `width_1` | First horizontal segment length. |
| `width_2` | Additional horizontal segment length; total width is width_1 + width_2. |
| `height_1` | First vertical segment length. |
| `height_2` | Additional vertical segment length; total height is height_1 + height_2. |
| `orientation` | 0 cuts out the bottom-left part; nonzero cuts out the top-right part. |

**Returns:** 0.

**Usage:** All six numeric dimensions are screen coordinates. The fifth and sixth arguments are lengths, not RGBA colors. Remove with DeleteNoticeFrame.

[Back to index](#function-index)

<a id="call-defaultdietalk"></a>
### DefaultDieTalk

`DefaultDieTalk()`

Looks up and starts the defeated unit’s default death message when that message exists. For player or inactive units it also selects death music.

**Arguments:** none.

**Returns:** 1 when a matching message exists; 0 otherwise.

**Usage:** Requires a current defeated-unit context. It can reuse an existing talk process.

[Back to index](#function-index)

<a id="call-defaultescapetalk"></a>
### DefaultEscapeTalk

`DefaultEscapeTalk()`

Looks up and starts the current acting unit’s default escape message when available.

**Arguments:** none.

**Returns:** 0, including when a message was started.

**Usage:** Requires a current acting-unit context. Follow the usual talk completion sequence.

[Back to index](#function-index)

<a id="call-deleteeventcamera"></a>
### DeleteEventCamera

`DeleteEventCamera()`

Removes the event camera and gives control back to the normal map camera.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-deletenoticeframe"></a>
### DeleteNoticeFrame

`DeleteNoticeFrame()`

Removes the active E_NoticeFrame highlight frame.

**Arguments:** none.

**Returns:** 0.

[Back to index](#function-index)

<a id="call-dialog"></a>
### Dialog

`Dialog(message_id)`

Opens a message dialog and suspends this script until the dialog process releases it.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a loaded message resource. |

**Returns:** 0; this is not a failure indication.

**Usage:** Read DialogResult afterwards if the message presents a choice. DialogDirect uses the same opening behavior as Dialog in this build.

[Back to index](#function-index)

<a id="call-dialog2items"></a>
### Dialog2Items

`Dialog2Items(choice_1, choice_2)`

Opens a choice dialog with 2 entries and suspends the calling script.

| Argument | Meaning and restrictions |
|---|---|
| `choice_1` | Message ID for choice 1, in display order. |
| `choice_2` | Message ID for choice 2, in display order. |

**Returns:** 1 when accepted; 0 for an invalid message argument.

**Usage:** Read DialogResult after the dialog closes; the opening call does not return the choice.

[Back to index](#function-index)

<a id="call-dialog3items"></a>
### Dialog3Items

`Dialog3Items(choice_1, choice_2, choice_3)`

Opens a choice dialog with 3 entries and suspends the calling script.

| Argument | Meaning and restrictions |
|---|---|
| `choice_1` | Message ID for choice 1, in display order. |
| `choice_2` | Message ID for choice 2, in display order. |
| `choice_3` | Message ID for choice 3, in display order. |

**Returns:** 1 when accepted; 0 for an invalid message argument.

**Usage:** Read DialogResult after the dialog closes; the opening call does not return the choice.

[Back to index](#function-index)

<a id="call-dialog4items"></a>
### Dialog4Items

`Dialog4Items(choice_1, choice_2, choice_3, choice_4)`

Opens a choice dialog with 4 entries and suspends the calling script.

| Argument | Meaning and restrictions |
|---|---|
| `choice_1` | Message ID for choice 1, in display order. |
| `choice_2` | Message ID for choice 2, in display order. |
| `choice_3` | Message ID for choice 3, in display order. |
| `choice_4` | Message ID for choice 4, in display order. |

**Returns:** 1 when accepted; 0 for an invalid message argument.

**Usage:** Read DialogResult after the dialog closes; the opening call does not return the choice.

[Back to index](#function-index)

<a id="call-dialogdirect"></a>
### DialogDirect

`DialogDirect(message_id)`

Opens a message dialog and suspends this script until the dialog process releases it.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a loaded message resource. |

**Returns:** 0; this is not a failure indication.

**Usage:** Read DialogResult afterwards if the message presents a choice. DialogDirect uses the same opening behavior as Dialog in this build.

[Back to index](#function-index)

<a id="call-dialoggetres"></a>
### DialogGetRes

`DialogGetRes()`

Reads the last dialog result.

**Arguments:** none.

**Returns:** Signed result byte: -1 before a result is selected; otherwise the dialog’s selected entry value.

**Usage:** Read only after the dialog completes. Do not treat -1 as “yes” because it is nonzero; retain the choice mapping of the dialog you use.

[Back to index](#function-index)

<a id="call-dialogresult"></a>
### DialogResult

`DialogResult()`

Reads the last dialog result.

**Arguments:** none.

**Returns:** Signed result byte: -1 before a result is selected; otherwise the dialog’s selected entry value.

**Usage:** Read only after the dialog completes. Do not treat -1 as “yes” because it is nonzero; retain the choice mapping of the dialog you use.

[Back to index](#function-index)

<a id="call-dialogsetdefault"></a>
### DialogSetDefault

`DialogSetDefault(selection)`

Sets the default selection byte used by dialogs.

| Argument | Meaning and restrictions |
|---|---|
| `selection` | Default choice value for the dialog being opened; only the low byte is retained. |

**Returns:** No useful script result; call for its side effect.

**Usage:** Set before opening the dialog. Use the same entry numbering as that dialog.

[Back to index](#function-index)

<a id="call-dialogtutorial"></a>
### DialogTutorial

`DialogTutorial(message_id)`

Opens a tutorial dialog and suspends this script until the dialog process releases it.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a loaded message resource. |

**Returns:** 0; this is not a failure indication.

**Usage:** Read DialogResult afterwards if the message presents a choice. DialogDirect uses the same opening behavior as Dialog in this build.

[Back to index](#function-index)

<a id="call-disableskip"></a>
### DisableSkip

`DisableSkip()`

Stops the player from skipping the current event until EnableSkip is called.

**Arguments:** none.

**Returns:** 1.

**Usage:** Death events and other critical scenes set the same flag. Always pair it with EnableSkip.

[Back to index](#function-index)

<a id="call-dispfreewholeforce"></a>
### DispFreeWholeForce

`DispFreeWholeForce(force)`

Releases display resources for every actor in a force list.

| Argument | Meaning and restrictions |
|---|---|
| `force` | Force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 reserve, 6 inactive, 7 special inactive. |

**Returns:** 1.

**Usage:** Does not change force membership or remove the actors.

[Back to index](#function-index)

<a id="call-disploadwholeforce"></a>
### DispLoadWholeForce

`DispLoadWholeForce(force)`

Loads display resources for every actor in a force list.

| Argument | Meaning and restrictions |
|---|---|
| `force` | Force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 reserve, 6 inactive, 7 special inactive. |

**Returns:** 1.

**Usage:** Does not change force membership or remove the actors.

[Back to index](#function-index)

<a id="call-disppreloadwholeforce"></a>
### DispPreLoadWholeForce

`DispPreLoadWholeForce(force)`

Queues battle-animation assets for every actor in a force list.

| Argument | Meaning and restrictions |
|---|---|
| `force` | Force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 reserve, 6 inactive, 7 special inactive. |

**Returns:** 1.

**Usage:** Does not change force membership or remove the actors.

[Back to index](#function-index)

<a id="call-dispos"></a>
### Dispos

`Dispos(group)`

Deploys a group: creates each listed unit that is not on the map yet (or reuses the existing one) and animates the units into place. The script waits for the movement.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Name of a deployment group in the chapter's dispos file. |

**Returns:** 1.

**Usage:** Each unit of the group goes to the free tile nearest its listed position; a character that already has a unit reuses it. Movement follows the UnitWalk*/UnitFade*/UnitFocus* scene settings. During an event skip the units appear at once.

[Back to index](#function-index)

<a id="call-disposasynchronous"></a>
### DisposAsynchronous

`DisposAsynchronous(group)`

Same as Dispos, but the script continues while the units move.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Name of a deployment group in the chapter's dispos file. |

**Returns:** 1.

**Usage:** Use UnitMoveWait when later steps need the units in place.

[Back to index](#function-index)

<a id="call-disposauxiliary"></a>
### DisposAuxiliary

`DisposAuxiliary(group)`

Deploys the units the player picked for the second team (SelectAuxiliary) onto the group's tiles and moves them from the reserve to the player force.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Deployment group that holds the second team's positions. |

**Returns:** 1.

**Usage:** Does nothing when no unit was picked. The script waits for the movement.

[Back to index](#function-index)

<a id="call-disposcontinue"></a>
### DisposContinue

`DisposContinue(group)`

Moves the units of a group that already exist to the group's positions, and waits for the movement. It never creates units.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Name of a deployment group in the chapter's dispos file. |

**Returns:** 1.

**Usage:** Units that have acted, are carried, dead, in the reserve or under a roof are skipped. Each unit of the group goes to the free tile nearest its listed position; a character that already has a unit reuses it.

[Back to index](#function-index)

<a id="call-disposcontinuesetmode"></a>
### DisposContinueSetMode

`DisposContinueSetMode(normal_group, hard_group, fallback_group)`

Calls DisposContinue(normal_group) if NormalOnly(), otherwise DisposContinue(hard_group) if Hard(), otherwise DisposContinue(fallback_group).

| Argument | Meaning and restrictions |
|---|---|
| `normal_group` | First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name. |
| `hard_group` | Group selected when Hard() is true. |
| `fallback_group` | Group selected otherwise; do not infer a menu difficulty solely from a filename suffix. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-disposfirst"></a>
### DisposFirst

`DisposFirst(group)`

Deploys a group onto its exact listed tiles, without searching for a free tile, and waits for the movement.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Name of a deployment group in the chapter's dispos file. |

**Returns:** 1.

**Usage:** Meant for the first placement of a chapter, when the listed tiles are known to be empty.

[Back to index](#function-index)

<a id="call-disposfirstsetmode"></a>
### DisposFirstSetMode

`DisposFirstSetMode(normal_group, hard_group, fallback_group)`

Calls DisposFirst(normal_group) if NormalOnly(), otherwise DisposFirst(hard_group) if Hard(), otherwise DisposFirst(fallback_group).

| Argument | Meaning and restrictions |
|---|---|
| `normal_group` | First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name. |
| `hard_group` | Group selected when Hard() is true. |
| `fallback_group` | Group selected otherwise; do not infer a menu difficulty solely from a filename suffix. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-disposgetgroupcenter"></a>
### DisposGetGroupCenter

`DisposGetGroupCenter(group, out_x, out_y)`

Computes the center of a named deployment group and writes its coordinates into two variables.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing deployment group name. |
| `out_x` | Address of an integer local, written with the group-center X. |
| `out_y` | Address of an integer local, written with the group-center Y. |

**Returns:** 0; read the output variables.

```fe9s
def example_disposgetgroupcenter():
    center_x = 0
    center_y = 0
    DisposGetGroupCenter("enemy", &center_x, &center_y)
```

[Back to index](#function-index)

<a id="call-dispossetmode"></a>
### DisposSetMode

`DisposSetMode(normal_group, hard_group, fallback_group)`

Calls Dispos(normal_group) if NormalOnly(), otherwise Dispos(hard_group) if Hard(), otherwise Dispos(fallback_group).

| Argument | Meaning and restrictions |
|---|---|
| `normal_group` | First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name. |
| `hard_group` | Group selected when Hard() is true. |
| `fallback_group` | Group selected otherwise; do not infer a menu difficulty solely from a filename suffix. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-disposwarp"></a>
### DisposWarp

`DisposWarp(group)`

Deploys a named reinforcement group using the warp deployment mode and suspends for active deployment motion.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing deployment group; create its records in the deployment data first. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-dispos-forevent"></a>
### Dispos_ForEvent

`Dispos_ForEvent(pid, class_id, matching_group, other_group, instant)`

If class_id is empty, uses matching_group without testing the actor. Otherwise tests UnitQueryJIDByPID and chooses matching_group or other_group. Uses InstantDispos when instant is nonzero, otherwise Dispos.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `class_id` | JID to test, or empty string to bypass the class test. |
| `matching_group` | Group for empty class or successful class match. |
| `other_group` | Group for failed class match. |
| `instant` | Nonzero = immediate placement; zero = ordinary deployment. |

**Returns:** 1 after the selected call, not proof the native deployment succeeded.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-dispos-foreventsenerio"></a>
### Dispos_ForEventSenerio

`Dispos_ForEventSenerio(mage_group, other_group, instant)`

Calls Dispos_ForEvent for PID_SENERIO and JID_MAGE.

| Argument | Meaning and restrictions |
|---|---|
| `mage_group` | Group when Soren matches JID_MAGE. |
| `other_group` | Group otherwise. |
| `instant` | Nonzero = InstantDispos; zero = Dispos. |

**Returns:** 1.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-dispos-foreventtiamat"></a>
### Dispos_ForEventTiamat

`Dispos_ForEventTiamat(group, instant)`

Calls Dispos_ForEvent("PID_TIAMAT", "", group, group, instant); the empty class bypasses the actor/class check.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |
| `instant` | Nonzero = InstantDispos; zero = Dispos. |

**Returns:** 1.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-doorclose"></a>
### DoorClose

`DoorClose(x, y)`

Closes the door at a tile with its animation and waits for it.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 after the animation; 0 if there is no door there, or during an event skip (the door closes at once).

**Usage:** The change is recorded in the map state, so it is kept in saves. The door's hit points are restored to full.

[Back to index](#function-index)

<a id="call-dooropen"></a>
### DoorOpen

`DoorOpen(x, y)`

Opens the door at a tile with its animation and waits for it. The door stops blocking movement.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 after the animation; 0 if there is no door there, or during an event skip (the door opens at once).

**Usage:** The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-envnoisyoff"></a>
### ENVNoisyOff

`ENVNoisyOff()`

Returns the ambient sound from the 'noisy' level to normal, over 15 frames (a quarter of a second).

**Arguments:** none.

**Returns:** 1.

**Usage:** Each ENV call cancels any ambient-level change still in progress. The ambient level is separate from the music channel volumes.

[Back to index](#function-index)

<a id="call-envnoisyon"></a>
### ENVNoisyOn

`ENVNoisyOn()`

Raises the ambient (environment) sound to its 'noisy' level, over 15 frames (a quarter of a second).

**Arguments:** none.

**Returns:** 1.

**Usage:** Each ENV call cancels any ambient-level change still in progress. The ambient level is separate from the music channel volumes.

[Back to index](#function-index)

<a id="call-envnoisyon-whennotevtskip"></a>
### ENVNoisyOn_WhenNotEvtSkip

`ENVNoisyOn_WhenNotEvtSkip()`

Calls ENVNoisyOn only when (GCST() & 1) is zero.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** This documents the exact guard, not the complete GCST bitfield.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-envquietoff"></a>
### ENVQuietOff

`ENVQuietOff()`

Returns the ambient sound from the 'quiet' level to normal, over 15 frames (a quarter of a second).

**Arguments:** none.

**Returns:** 1.

**Usage:** Each ENV call cancels any ambient-level change still in progress. The ambient level is separate from the music channel volumes.

[Back to index](#function-index)

<a id="call-envquieton"></a>
### ENVQuietOn

`ENVQuietOn()`

Lowers the ambient sound to its 'quiet' level, over 15 frames (a quarter of a second).

**Arguments:** none.

**Returns:** 1.

**Usage:** Each ENV call cancels any ambient-level change still in progress. The ambient level is separate from the music channel volumes.

[Back to index](#function-index)

<a id="call-envsilentoff"></a>
### ENVSilentOff

`ENVSilentOff()`

Brings back ambient sound silenced by ENVSilentOn, over 15 frames (a quarter of a second).

**Arguments:** none.

**Returns:** 1.

**Usage:** Each ENV call cancels any ambient-level change still in progress. The ambient level is separate from the music channel volumes.

[Back to index](#function-index)

<a id="call-envsilentoff-whennotevtskip"></a>
### ENVSilentOff_WhenNotEvtSkip

`ENVSilentOff_WhenNotEvtSkip()`

Calls ENVSilentOff only when (GCST() & 1) is zero.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** This documents the exact guard, not the complete GCST bitfield.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-envsilenton"></a>
### ENVSilentOn

`ENVSilentOn(frames)`

Silences the ambient (environment) sound.

| Argument | Meaning and restrictions |
|---|---|
| `frames` | Fade time in frames (60 per second): vanilla uses 15–90. 0 silences instantly; negative values count as 0. |

**Returns:** 1.

**Usage:** Undo with ENVSilentOff. Cancels any ambient-level change still in progress.

[Back to index](#function-index)

<a id="call-easy"></a>
### Easy

`Easy()`

Always returns 0 in this US build; do not use this as a working difficulty test.

**Arguments:** none.

**Returns:** 0, always.

**Usage:** Use GetRank or a supported difficulty helper instead.

[Back to index](#function-index)

<a id="call-effectplay"></a>
### EffectPlay

`EffectPlay(effect_id, x, y)`

Loads and spawns a named scene effect at the supplied position.

| Argument | Meaning and restrictions |
|---|---|
| `effect_id` | Existing EID_... effect resource. |
| `x` | Map tile X for a map-space effect; direct effect-space X for effects configured in another coordinate mode. |
| `y` | Map tile Y for a map-space effect; direct effect-space Y for effects configured in another coordinate mode. |

**Returns:** 1 when scheduled; 0 during event skipping.

**Usage:** Map-space effects use the tile center and terrain height. The resource determines coordinate mode. The script waits for the loading/spawn process, not necessarily the full effect lifetime.

[Back to index](#function-index)

<a id="call-effectwait"></a>
### EffectWait

`EffectWait()`

Waits for the effect started by EffectPlay to finish.

**Arguments:** none.

**Returns:** 1; 0 while the event is being skipped.

**Usage:** While the event is being skipped it removes the effect at once instead of waiting.

[Back to index](#function-index)

<a id="call-enableskip"></a>
### EnableSkip

`EnableSkip()`

Lets the player skip the current event again.

**Arguments:** none.

**Returns:** 1.

**Usage:** Undoes DisableSkip. It does not start a skip.

[Back to index](#function-index)

<a id="call-endfinale"></a>
### EndFinale

`EndFinale()`

Disables finale mode and its input mask for A/B/X/Y/Z/L/R/Start.

**Arguments:** none.

**Returns:** 1.

**Usage:** Pair BeginFinale and EndFinale around ending sequences; neither call starts the credits by itself.

[Back to index](#function-index)

<a id="call-endmapholdcursor"></a>
### EndMapHoldCursor

`EndMapHoldCursor()`

Ends the map cursor-hold process.

**Arguments:** none.

**Returns:** 0.

[Back to index](#function-index)

<a id="call-enemydeadcheck"></a>
### EnemyDeadCheck

`EnemyDeadCheck()`

Tests whether the enemy force is empty.

**Arguments:** none.

**Returns:** 1 if no unit is left in force 1; 0 otherwise.

[Back to index](#function-index)

<a id="call-enemymonkcheck"></a>
### EnemyMonkCheck

`EnemyMonkCheck()`

Counts enemy-force actors with class JID_PRIEST, JID_BISHOP, or JID_BISHOP_F.

**Arguments:** none.

**Returns:** Number of matching enemies.

[Back to index](#function-index)

<a id="call-enemyselfdefencecheck"></a>
### EnemySelfDefenceCheck

`EnemySelfDefenceCheck()`

Counts enemy-force actors with PID PID_12_SELFDEFENCE.

**Arguments:** none.

**Returns:** Number of matching enemies.

[Back to index](#function-index)

<a id="call-enemytigercheck"></a>
### EnemyTigerCheck

`EnemyTigerCheck()`

Counts enemy-force actors with class JID_TIGER.

**Arguments:** none.

**Returns:** Number of matching enemies.

[Back to index](#function-index)

<a id="call-enemyunitcheckbypid"></a>
### EnemyUnitCheckByPID

`EnemyUnitCheckByPID(pid)`

Counts actors with the specified PID in the enemy force.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Exact PID_... character ID string. |

**Returns:** Count, not a boolean.

[Back to index](#function-index)

<a id="call-eventarrowappend"></a>
### EventArrowAppend

`EventArrowAppend(arrow_id, time_ms, x, y, height)`

Adds a timed waypoint to a map-event arrow’s path.

| Argument | Meaning and restrictions |
|---|---|
| `arrow_id` | Arrow slot index. Use a slot supported by the existing scene; this index is not bounds-checked. |
| `time_ms` | Waypoint time in milliseconds, converted to frames and sorted into the path. |
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |
| `height` | Map-space height. A value below -999 samples the terrain at the tile center, subtracts 1, and truncates to an integer. |

**Returns:** 1.

**Usage:** X/Y are centered on the tile by adding 0.5. Build the path before EventArrowStart; use an existing path’s slot and waypoint limits.

[Back to index](#function-index)

<a id="call-eventarrowcolor"></a>
### EventArrowColor

`EventArrowColor(arrow_id, red, green, blue, alpha)`

Sets the arrow’s RGBA color.

| Argument | Meaning and restrictions |
|---|---|
| `arrow_id` | Arrow slot index. Use a slot supported by the existing scene; this index is not bounds-checked. |
| `red` | 0–255. |
| `green` | 0–255. |
| `blue` | 0–255. |
| `alpha` | 0 transparent; 255 opaque. |

**Returns:** 1.

**Usage:** Values are stored as bytes; they wrap rather than clamp.

[Back to index](#function-index)

<a id="call-eventarrowdelete"></a>
### EventArrowDelete

`EventArrowDelete()`

Deletes the map-event arrow process and all of its arrows.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-eventarrowfadeout"></a>
### EventArrowFadeOut

`EventArrowFadeOut(arrow_id)`

Requests fade-out of the selected map-event arrow.

| Argument | Meaning and restrictions |
|---|---|
| `arrow_id` | Arrow slot index. Use a slot supported by the existing scene; this index is not bounds-checked. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-eventarrowfocus"></a>
### EventArrowFocus

`EventArrowFocus(arrow_id, enabled)`

Changes the arrow’s focus-following flag.

| Argument | Meaning and restrictions |
|---|---|
| `arrow_id` | Arrow slot index. Use a slot supported by the existing scene; this index is not bounds-checked. |
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-eventarrowstart"></a>
### EventArrowStart

`EventArrowStart(arrow_id, duration_ms)`

Starts an arrow path transition from its current progress using the supplied time.

| Argument | Meaning and restrictions |
|---|---|
| `arrow_id` | Arrow slot index. Use a slot supported by the existing scene; this index is not bounds-checked. |
| `duration_ms` | Duration in milliseconds. Conversion to 60 Hz frames truncates fractional frames. |

**Returns:** 1.

**Usage:** Configure waypoints first; use EventArrowWait before dependent work.

[Back to index](#function-index)

<a id="call-eventarrowwait"></a>
### EventArrowWait

`EventArrowWait()`

Suspends the script while map-event arrows are animating.

**Arguments:** none.

**Returns:** 1 in ordinary playback; 0 during event skipping.

[Back to index](#function-index)

<a id="call-eventcamerawait"></a>
### EventCameraWait

`EventCameraWait()`

Waits until the event-camera path has finished playing.

**Arguments:** none.

**Returns:** 1.

**Usage:** Returns at once if no path is playing.

[Back to index](#function-index)

<a id="call-eventgetx"></a>
### EventGetX

`EventGetX()`

Returns the X coordinate of the tile that started the current location event (visit, area, chest, door).

**Arguments:** none.

**Returns:** Map tile X.

**Usage:** Only meaningful inside an event started by a tile.

[Back to index](#function-index)

<a id="call-eventgety"></a>
### EventGetY

`EventGetY()`

Returns the Y coordinate of the tile that started the current location event.

**Arguments:** none.

**Returns:** Map tile Y.

**Usage:** Only meaningful inside an event started by a tile.

[Back to index](#function-index)

<a id="call-eventquake"></a>
### EventQuake

`EventQuake(strength, period_ms, cycles)`

Starts a repeating camera shake.

| Argument | Meaning and restrictions |
|---|---|
| `strength` | Shake intensity; 0 produces no sustained shake. |
| `period_ms` | Length of one shake cycle in milliseconds, truncated to frames; a converted value of 0 becomes one frame. |
| `cycles` | Positive number of cycles; 0 or negative repeats until stopped. |

**Returns:** 1.

**Usage:** The second argument is one cycle’s duration, not the total duration. EventQuakeStop ends a repeating shake.

[Back to index](#function-index)

<a id="call-eventquakestop"></a>
### EventQuakeStop

`EventQuakeStop()`

Requests the active camera shake to stop.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-frame2msec"></a>
### FRAME2MSEC

`FRAME2MSEC(frames)`

Converts a 60 Hz frame count to milliseconds.

| Argument | Meaning and restrictions |
|---|---|
| `frames` | Frame count, typically nonnegative. |

**Returns:** frames × 16.666666, truncated to an integer.

[Back to index](#function-index)

<a id="call-fade"></a>
### Fade

`Fade(mode, duration_ms)`

Starts a screen transition.

| Argument | Meaning and restrictions |
|---|---|
| `mode` | 0 = clear screen immediately; 1 = solid black; 2 = fade in from black; 3 = fade out to black; 4 = solid white; 5 = fade in from white; 6 = fade out to white; 7 = captured-screen transition. |
| `duration_ms` | Duration in milliseconds; negative uses 500 ms. |

**Returns:** 1.

**Usage:** Use FadeWait before starting another transition. During event skipping, transitions go directly to their final state.

[Back to index](#function-index)

<a id="call-fadewait"></a>
### FadeWait

`FadeWait()`

Yields repeatedly while isFading() is nonzero.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** No timeout and no extra frame after the predicate becomes false.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-flash"></a>
### Flash

`Flash(red, green, blue, appear_ms, disappear_ms)`

Starts a colored screen flash.

| Argument | Meaning and restrictions |
|---|---|
| `red` | Red component; clamped to 0–255. |
| `green` | Green component; clamped to 0–255. |
| `blue` | Blue component; clamped to 0–255. |
| `appear_ms` | Appearance duration; negative uses 500 ms. |
| `disappear_ms` | Disappearance duration; negative uses 500 ms. |

**Returns:** 1.

**Usage:** Use FlashWait to wait for the transition.

[Back to index](#function-index)

<a id="call-flashwait"></a>
### FlashWait

`FlashWait()`

Suspends the script while the screen flash is transitioning.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-focus"></a>
### Focus

`Focus(x, y)`

Moves the map camera smoothly so it looks at the centre of a tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 0.

**Usage:** Does not wait: follow with FocusWait. While the event is being skipped the camera jumps there at once.

[Back to index](#function-index)

<a id="call-focusbetweenab"></a>
### FocusBetweenAB

`FocusBetweenAB(pid_a, pid_b, offset_x, offset_y, instant)`

Requires both PIDs to be deployed, copies the current map camera, computes their tile midpoint using a right shift by 1, adds offsets and calls Focus or InstantFocus.

| Argument | Meaning and restrictions |
|---|---|
| `pid_a` | First deployed actor PID. |
| `pid_b` | Second deployed actor PID. |
| `offset_x` | Tiles added to the midpoint X. |
| `offset_y` | Tiles added to the midpoint Y. |
| `instant` | Nonzero uses InstantFocus; zero uses Focus. |

**Returns:** 0 if either actor is unavailable; 1 after scheduling focus.

**Usage:** Does not restore the copied camera or wait for focus itself.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-focushardwait"></a>
### FocusHardWait

`FocusHardWait()`

Like FocusWait, but waits until the camera is within 0.1 tile of its target point and 1 unit of its target angles and distance.

**Arguments:** none.

**Returns:** 1 if it had to wait; 0 if the camera was already there, or during an event skip.

[Back to index](#function-index)

<a id="call-focuswait"></a>
### FocusWait

`FocusWait()`

Waits until the map camera has nearly reached its target.

**Arguments:** none.

**Returns:** 1 if it had to wait; 0 if the camera was already there, or during an event skip (the camera jumps to its target).

**Usage:** 'Nearly': within 1 tile of the target point and 10 units of the target angles and distance. FocusHardWait waits for a closer match.

[Back to index](#function-index)

<a id="call-forcecheckanyonedead"></a>
### ForceCheckAnyoneDead

`ForceCheckAnyoneDead()`

Walks force 6 and tests status bit 0x8000 on each actor.

**Arguments:** none.

**Returns:** 1 if any scanned actor has that bit; 0 otherwise.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-forcegetcount"></a>
### ForceGetCount

`ForceGetCount(force)`

Counts the units in a force.

| Argument | Meaning and restrictions |
|---|---|
| `force` | Force ID: 0 player, 1 enemy, 2 allied (orderable), 3 other (green), 4 free pool, 5 player reserve, 6 dead/inactive, 7 special inactive. |

**Returns:** Number of units in that force.

**Usage:** No range check: use 0–7.

[Back to index](#function-index)

<a id="call-forcegetfirst"></a>
### ForceGetFirst

`ForceGetFirst(force)`

Returns the first unit of a force, to walk it with UnitGetNext.

| Argument | Meaning and restrictions |
|---|---|
| `force` | Force ID: 0 player, 1 enemy, 2 allied (orderable), 3 other (green), 4 free pool, 5 player reserve, 6 dead/inactive, 7 special inactive. |

**Returns:** Unit handle; 0 if the force is empty.

**Usage:** No range check: use 0–7.

[Back to index](#function-index)

<a id="call-gcst"></a>
### GCST

`GCST()`

Returns the event system's state flags.

**Arguments:** none.

**Returns:** Bit flags: 0x1 the current event is being skipped; 0x2 the current conversation is being skipped; 0x4 skipping is disabled; 0x10 the event is suspended (SuspendEvent or a tutorial dialog); 0x1000 outer link enabled (SetOutLink); 0x2000 finale mode (BeginFinale). Other bits belong to the tutorial and menu code.

**Usage:** Scripts normally test only bit 0x1, as the shared *_WhenNotEvtSkip helpers do.

[Back to index](#function-index)

<a id="call-gmapflagmarkoff"></a>
### GMapFlagMarkOff

`GMapFlagMarkOff(map_id, index)`

Turns off the selected flag marker on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `index` | Index of the flag marker in this world-map resource; not a chapter number. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmapflagmarkoffall"></a>
### GMapFlagMarkOffAll

`GMapFlagMarkOffAll(map_id)`

Removes all flag markers on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmapflagmarkon"></a>
### GMapFlagMarkOn

`GMapFlagMarkOn(map_id, index, x, y, style)`

Creates or resets a flag marker on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `index` | Flag-marker slot to use; reuse the same slot to replace its marker. |
| `x` | X in world-map image coordinates. |
| `y` | Y in world-map image coordinates. |
| `style` | Marker style byte. Use an available style from the matching map scene. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmappendarkonoff"></a>
### GMapPenDarkOnOff

`GMapPenDarkOnOff(map_id, sequence, enabled)`

Changes the dark-display flag for one world-map pen sequence.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `sequence` | Pen sequence index in the loaded resource. |
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmappendisponoff"></a>
### GMapPenDispOnOff

`GMapPenDispOnOff(map_id, enabled)`

Shows or hides the world-map pen overlay.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmappendraw1seq"></a>
### GMapPenDraw1Seq

`GMapPenDraw1Seq(map_id, index)`

Starts drawing the selected pen sequence on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `index` | Index of the pen sequence in this world-map resource; not a chapter number. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmappendrawwait"></a>
### GMapPenDrawWait

`GMapPenDrawWait(map_id)`

Suspends this script until the world-map pen drawing operation completes.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmappenreset"></a>
### GMapPenReset

`GMapPenReset(map_id, index)`

Resets the selected pen sequence on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `index` | Index of the pen sequence in this world-map resource; not a chapter number. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmappointoff"></a>
### GMapPointOff

`GMapPointOff(map_id, index)`

Starts removal of the selected point marker on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `index` | Index of the point marker in this world-map resource; not a chapter number. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmappointoffall"></a>
### GMapPointOffAll

`GMapPointOffAll(map_id)`

Removes all point markers on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmappointon"></a>
### GMapPointOn

`GMapPointOn(map_id, index, x, y, scale_percent, rgb)`

Creates a colored point marker on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `index` | Point-marker slot to use. |
| `x` | X in world-map image coordinates. |
| `y` | Y in world-map image coordinates. |
| `scale_percent` | Marker scale; 100 = normal size. |
| `rgb` | Packed RGB integer, for example 0xFF0000 for red. Alpha is fixed to 255. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmapregionflashonoff"></a>
### GMapRegionFlashOnOff

`GMapRegionFlashOnOff(map_id, region, enabled)`

Enables or disables the flashing flag for a world-map region.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `region` | Region index in the loaded resource. |
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmapregionflashonce"></a>
### GMapRegionFlashOnce

`GMapRegionFlashOnce(map_id, index)`

Requests a single flash of the selected region overlay on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `index` | Index of the region overlay in this world-map resource; not a chapter number. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmapregionoff"></a>
### GMapRegionOff

`GMapRegionOff(map_id, index)`

Turns off the selected region overlay on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `index` | Index of the region overlay in this world-map resource; not a chapter number. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmapregionoffall"></a>
### GMapRegionOffAll

`GMapRegionOffAll(map_id)`

Turns off all region overlays on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmapregionon"></a>
### GMapRegionOn

`GMapRegionOn(map_id, index)`

Turns on the selected region overlay on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `index` | Index of the region overlay in this world-map resource; not a chapter number. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gmapregiononskipflash"></a>
### GMapRegionOnSkipFlash

`GMapRegionOnSkipFlash(map_id, index)`

Turns on without its initial flash the selected region overlay on a world-map image.

| Argument | Meaning and restrictions |
|---|---|
| `map_id` | RID_GMAP_... resource ID of a world-map image already built for this scene. |
| `index` | Index of the region overlay in this world-map resource; not a chapter number. |

**Returns:** 1 when the loaded map accepts the operation; 0 if the map is missing, the argument is invalid, or the event is being skipped.

[Back to index](#function-index)

<a id="call-gamebind"></a>
### GameBind

`GameBind()`

Freezes the map's normal game flow (phases, cursor, menus) while the script works.

**Arguments:** none.

**Returns:** 1.

**Usage:** Undo with GameUnbind. The tutorial helpers wrap their steps in this pair.

[Back to index](#function-index)

<a id="call-gameunbind"></a>
### GameUnbind

`GameUnbind()`

Lets the map's game flow continue after GameBind.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-getbattletype"></a>
### GetBattleType

`GetBattleType()`

Returns the flag word of the current or most recent battle.

**Arguments:** none.

**Returns:** Bit flags. Bit 0x80000000 is set when the battle was started by NetuzoBattle with its event_battle argument; the shared boss and death-talk helpers test it. Other bits are internal battle state.

[Back to index](#function-index)

<a id="call-getdiedplayercount"></a>
### GetDiedPlayerCount

`GetDiedPlayerCount()`

Counts actors in force 6 whose death-record flag is set.

**Arguments:** none.

**Returns:** Number of matching actors; can exceed 1.

[Back to index](#function-index)

<a id="call-getfukiposx"></a>
### GetFukiPosX

`GetFukiPosX()`

Reads the X coordinate of the active tutorial speech-bubble display.

**Arguments:** none.

**Returns:** Signed X coordinate; 0 if the display process is absent.

**Usage:** Useful for positioning tutorial graphics around the active bubble; 0 is also a valid position.

[Back to index](#function-index)

<a id="call-getfukiposy"></a>
### GetFukiPosY

`GetFukiPosY()`

Reads the Y coordinate of the active tutorial speech-bubble display.

**Arguments:** none.

**Returns:** Signed Y coordinate; 0 if the display process is absent.

**Usage:** Useful for positioning tutorial graphics around the active bubble; 0 is also a valid position.

[Back to index](#function-index)

<a id="call-getlanguage"></a>
### GetLanguage

`GetLanguage()`

Returns the language ID. The US build has no language setting.

**Arguments:** none.

**Returns:** 1, always.

[Back to index](#function-index)

<a id="call-getmapheight"></a>
### GetMapHeight

`GetMapHeight(x, y)`

Samples the alternate terrain-surface height at the supplied map coordinates.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |

**Returns:** Sampled height multiplied by the event-camera precision factor, then truncated to an integer. Precision defaults to 1.

**Usage:** Use with event-camera coordinates; this is a height value, not a flattened tile index.

[Back to index](#function-index)

<a id="call-getmapheightbase"></a>
### GetMapHeightBase

`GetMapHeightBase(x, y)`

Samples the base terrain height at the supplied map coordinates.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |

**Returns:** Sampled height multiplied by the event-camera precision factor, then truncated to an integer. Precision defaults to 1.

**Usage:** Use with event-camera coordinates; this is a height value, not a flattened tile index.

[Back to index](#function-index)

<a id="call-getrank"></a>
### GetRank

`GetRank()`

Returns the difficulty.

**Arguments:** none.

**Returns:** 0 Normal, 1 Hard, 2 Maniac, 3 Easy (US build).

[Back to index](#function-index)

<a id="call-getrnd"></a>
### GetRnd

`GetRnd(exclusive_max)`

Draws a random integer using the game random-number generator.

| Argument | Meaning and restrictions |
|---|---|
| `exclusive_max` | Positive upper bound; the result is smaller than this value. |

**Returns:** Integer from 0 through exclusive_max - 1.

**Usage:** Consumes random state. Do not use zero or negative bounds.

[Back to index](#function-index)

<a id="call-gettutorial"></a>
### GetTutorial

`GetTutorial()`

Reads whether tutorial help is enabled in configuration.

**Arguments:** none.

**Returns:** 1 when enabled; 0 when disabled.

[Back to index](#function-index)

<a id="call-hard"></a>
### Hard

`Hard()`

Tests for Hard difficulty.

**Arguments:** none.

**Returns:** 1 on Hard (1); 0 otherwise.

[Back to index](#function-index)

<a id="call-hidemapcursor"></a>
### HideMapCursor

`HideMapCursor()`

Removes every map cursor shown by ShowMapCursor.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-hideprim2d"></a>
### HidePrim2D

`HidePrim2D(hidden)`

Starts or ends the scene process that hides 2D primitives.

| Argument | Meaning and restrictions |
|---|---|
| `hidden` | Nonzero starts hiding; 0 removes the hiding process. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-individualwarrecord"></a>
### IndividualWarRecord

`IndividualWarRecord(duration_ms)`

Starts the individual war-record display and suspends the calling script.

| Argument | Meaning and restrictions |
|---|---|
| `duration_ms` | Duration in milliseconds. Conversion to 60 Hz frames truncates fractional frames. |

**Returns:** 1.

**Usage:** Intended for ending sequences with the corresponding display resources loaded.

[Back to index](#function-index)

<a id="call-instantdispos"></a>
### InstantDispos

`InstantDispos(group)`

Same as Dispos, but places every unit at once without animation.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Name of a deployment group in the chapter's dispos file. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-instantdisposcontinue"></a>
### InstantDisposContinue

`InstantDisposContinue(group)`

Same as DisposContinue, without animation.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Name of a deployment group in the chapter's dispos file. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-instantdisposcontinuesetmode"></a>
### InstantDisposContinueSetMode

`InstantDisposContinueSetMode(normal_group, hard_group, fallback_group)`

Calls InstantDisposContinue(normal_group) if NormalOnly(), otherwise InstantDisposContinue(hard_group) if Hard(), otherwise InstantDisposContinue(fallback_group).

| Argument | Meaning and restrictions |
|---|---|
| `normal_group` | First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name. |
| `hard_group` | Group selected when Hard() is true. |
| `fallback_group` | Group selected otherwise; do not infer a menu difficulty solely from a filename suffix. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-instantdisposfirst"></a>
### InstantDisposFirst

`InstantDisposFirst(group)`

Same as DisposFirst, without animation.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Name of a deployment group in the chapter's dispos file. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-instantdisposfirstsetmode"></a>
### InstantDisposFirstSetMode

`InstantDisposFirstSetMode(normal_group, hard_group, fallback_group)`

Calls InstantDisposFirst(normal_group) if NormalOnly(), otherwise InstantDisposFirst(hard_group) if Hard(), otherwise InstantDisposFirst(fallback_group).

| Argument | Meaning and restrictions |
|---|---|
| `normal_group` | First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name. |
| `hard_group` | Group selected when Hard() is true. |
| `fallback_group` | Group selected otherwise; do not infer a menu difficulty solely from a filename suffix. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-instantdisposrank"></a>
### InstantDisposRank

`InstantDisposRank(group)`

Deploys the difficulty variant of a group at once: adds "_n" to the name on Normal, "_h" on Hard and "_m" on Maniac or Easy, then works like InstantDispos.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Group name without the difficulty suffix. |

**Returns:** 1.

**Usage:** The finished name must exist for each difficulty you support.

[Back to index](#function-index)

<a id="call-instantdispossetmode"></a>
### InstantDisposSetMode

`InstantDisposSetMode(normal_group, hard_group, fallback_group)`

Calls InstantDispos(normal_group) if NormalOnly(), otherwise InstantDispos(hard_group) if Hard(), otherwise InstantDispos(fallback_group).

| Argument | Meaning and restrictions |
|---|---|
| `normal_group` | First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name. |
| `hard_group` | Group selected when Hard() is true. |
| `fallback_group` | Group selected otherwise; do not infer a menu difficulty solely from a filename suffix. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-instantdoorclose"></a>
### InstantDoorClose

`InstantDoorClose(x, y)`

Closes the door at a tile without animation and restores its hit points.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 if a door was found; 0 otherwise.

**Usage:** The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-instantdooropen"></a>
### InstantDoorOpen

`InstantDoorOpen(x, y)`

Opens the door at a tile without animation.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 if a door was found; 0 otherwise.

**Usage:** The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-instantfocus"></a>
### InstantFocus

`InstantFocus(x, y)`

Points the map camera at the centre of a tile at once.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 0.

[Back to index](#function-index)

<a id="call-instantpastmapcamera"></a>
### InstantPastMapCamera

`InstantPastMapCamera()`

Restores the angles and distance saved by CopyMapCamera at once.

**Arguments:** none.

**Returns:** 1.

**Usage:** Does nothing if nothing was saved.

[Back to index](#function-index)

<a id="call-instantroofclose"></a>
### InstantRoofClose

`InstantRoofClose(x, y)`

Puts back the roof at a tile without animation.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 if a roof was found; 0 otherwise.

**Usage:** The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-instantroofopen"></a>
### InstantRoofOpen

`InstantRoofOpen(x, y)`

Lifts the roof at a tile without animation.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 if a roof was found; 0 otherwise.

**Usage:** The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-instantsetmapcamera"></a>
### InstantSetMapCamera

`InstantSetMapCamera(yaw, pitch, distance)`

Sets the map camera's angles and distance at once.

| Argument | Meaning and restrictions |
|---|---|
| `yaw` | Horizontal camera angle in degrees. |
| `pitch` | Vertical camera angle in degrees (vanilla uses 40–63). |
| `distance` | Distance from the looked-at point, in tiles (vanilla uses 10–45). |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-instantunitfocusbypid"></a>
### InstantUnitFocusByPID

`InstantUnitFocusByPID(pid)`

Resolves a deployed actor, reads its tile, then calls InstantFocus.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** 0 if unavailable; 1 after focus call.

**Usage:** Does not copy/restore the previous map camera itself.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-instantunitfocusoffsetbypid"></a>
### InstantUnitFocusOffsetByPID

`InstantUnitFocusOffsetByPID(pid, offset_x, offset_y)`

Resolves a deployed actor, reads its tile and adds X/Y offsets, then calls InstantFocus.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `offset_x` | Tiles added to actor X. |
| `offset_y` | Tiles added to actor Y. |

**Returns:** 0 if unavailable; 1 after focus call.

**Usage:** Does not copy/restore the previous map camera itself.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-instantunittransform"></a>
### InstantUnitTransform

`InstantUnitTransform(unit, transformed)`

Changes a unit to the requested transformed/untransformed state immediately and refreshes its display.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `transformed` | 0 requests untransformed; nonzero requests transformed. This is a desired state, not a toggle. |

**Returns:** 1 if the state changes; 0 for invalid unit or already matching state.

**Usage:** Use only on a compatible laguz unit.

[Back to index](#function-index)

<a id="call-ise3version"></a>
### IsE3Version

`IsE3Version()`

Tests the E3/demo-build condition in this US executable.

**Arguments:** none.

**Returns:** 0, always.

[Back to index](#function-index)

<a id="call-itemgetindex"></a>
### ItemGetIndex

`ItemGetIndex(iid)`

Resolves an item ID to its numeric item index.

| Argument | Meaning and restrictions |
|---|---|
| `iid` | Existing IID_... item ID string. |

**Returns:** Item index; 0 if the item ID is not found.

[Back to index](#function-index)

<a id="call-join"></a>
### Join

`Join(group)`

Adds the characters of a deployment group to the player's reserve (force 5), off the map. Characters that already have a unit keep it.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Name of a deployment group in the chapter's dispos file. |

**Returns:** 1; 0 if group is not a valid string.

**Usage:** Used to recruit characters between chapters, for example the always_T_* groups added by TrialAddUnit.

[Back to index](#function-index)

<a id="call-jyokyomapcapture"></a>
### JyokyoMapCapture

`JyokyoMapCapture()`

Captures the status-map display and suspends the script while capture completes.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-jyokyomapdelete"></a>
### JyokyoMapDelete

`JyokyoMapDelete()`

Deletes the status-map display.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-jyokyomapenemyon"></a>
### JyokyoMapEnemyOn

`JyokyoMapEnemyOn()`

Enables enemy markers on the status map.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-jyokyomaphide"></a>
### JyokyoMapHide

`JyokyoMapHide()`

Hides the status-map display.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-jyokyomapplayeron"></a>
### JyokyoMapPlayerOn

`JyokyoMapPlayerOn()`

Enables player markers on the status map.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-jyokyomapshow"></a>
### JyokyoMapShow

`JyokyoMapShow()`

Starts the status-map display.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-localdietalkwithbgmchange"></a>
### LocalDieTalkWithBgmChange

`LocalDieTalkWithBgmChange(flag_name, message_id)`

Disables skip. If flag_name is nonempty and set, calls DefaultDieTalk. Otherwise mutes map music, fades event music over 500 ms, waits 500 ms, plays BGM_DEAD1 and the supplied message. Surrounds that custom branch with environment silence when GetBattleType has bit 0x80000000. Re-enables skip.

| Argument | Meaning and restrictions |
|---|---|
| `flag_name` | Empty string forces custom dialogue; otherwise a set registered flag selects DefaultDieTalk. |
| `message_id` | Message ID in a currently loaded message resource; not literal dialogue text. |

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** It does not set the supplied flag or explicitly restore the previous BGM itself.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-mcresult"></a>
### MCResult

`MCResult()`

Reads the last memory-card operation status.

**Arguments:** none.

**Returns:** Memory-card status code; it is not a boolean.

**Usage:** Use only in a matching save/load workflow after its asynchronous operation completes. This call does not start a save.

[Back to index](#function-index)

<a id="call-msec2frame"></a>
### MSEC2FRAME

`MSEC2FRAME(duration_ms)`

Converts milliseconds to 60 Hz frames.

| Argument | Meaning and restrictions |
|---|---|
| `duration_ms` | Duration in milliseconds. Conversion to 60 Hz frames truncates fractional frames. |

**Returns:** duration_ms ÷ 16.666666, truncated to an integer.

[Back to index](#function-index)

<a id="call-maniac"></a>
### Maniac

`Maniac()`

Tests for Maniac difficulty.

**Arguments:** none.

**Returns:** 1 on Maniac (2); 0 otherwise.

[Back to index](#function-index)

<a id="call-mapfree"></a>
### MapFree

`MapFree()`

Calls _mf1(), yields once, then calls _mf2().

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** Two-stage native map release; removing the yield changes the sequence.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-mapgetsight"></a>
### MapGetSight

`MapGetSight(x, y)`

Reads the visibility-grid byte at a tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |

**Returns:** Stored visibility value.

**Usage:** Use valid map coordinates and the chapter’s existing visibility comparisons; this does not recalculate sight.

[Back to index](#function-index)

<a id="call-mapgetterrain"></a>
### MapGetTerrain

`MapGetTerrain(x, y)`

Reads the terrain ID stored at a map tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |

**Returns:** Terrain ID byte.

**Usage:** Use coordinates inside the allocated map grid; there is no coordinate bounds check.

[Back to index](#function-index)

<a id="call-mapgetunit"></a>
### MapGetUnit

`MapGetUnit(x, y)`

Reads the occupancy-grid unit handle at a tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |

**Returns:** Unit handle byte; 0 for an empty cell.

**Usage:** This reads the occupancy grid directly. Use valid map coordinates.

[Back to index](#function-index)

<a id="call-mapload"></a>
### MapLoad

`MapLoad(map_name)`

Loads a map by name and makes it the current map.

| Argument | Meaning and restrictions |
|---|---|
| `map_name` | Map folder name, such as bmap02 or bmap06_2. |

**Returns:** 1.

**Usage:** Only loads the map: it places no units and runs no chapter setup. The script yields once.

[Back to index](#function-index)

<a id="call-mapreload"></a>
### MapReload

`MapReload()`

Reloads the current chapter's map, reapplies its recorded map state (opened doors, visited villages, ...) and points the camera at the saved cursor tile.

**Arguments:** none.

**Returns:** 1.

**Usage:** Used when coming back from a tutorial (TutorialResumeOut).

[Back to index](#function-index)

<a id="call-mapupdate"></a>
### MapUpdate

`MapUpdate()`

Recalculates the map's occupancy, movement ranges and danger areas after units or terrain changed.

**Arguments:** none.

**Returns:** No meaningful value; call it for its effect.

[Back to index](#function-index)

<a id="call-mindgetitem"></a>
### MindGetItem

`MindGetItem(item_id)`

Calls UnitGetItemShowing(MindGetMe(), item_id).

| Argument | Meaning and restrictions |
|---|---|
| `item_id` | IID_... reward item. |

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** Recipient is the current acting unit; inappropriate context may provide no valid recipient.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-mindgetme"></a>
### MindGetMe

`MindGetMe()`

Returns the unit performing the current action (the unit that visited, talked, opened a chest, etc.).

**Arguments:** none.

**Returns:** Unit handle; 0 if there is none.

**Usage:** Only meaningful in events started by a unit action.

[Back to index](#function-index)

<a id="call-mindgetmind"></a>
### MindGetMind

`MindGetMind()`

Reads the current map-action ID.

**Arguments:** none.

**Returns:** Action ID byte.

**Usage:** Requires the event’s map-action context; this does not identify the acting unit.

[Back to index](#function-index)

<a id="call-mindgetmoney"></a>
### MindGetMoney

`MindGetMoney(amount)`

Adds gold to the party and starts a reward notification associated with the current acting unit.

| Argument | Meaning and restrictions |
|---|---|
| `amount` | Gold amount added to the current total. |

**Returns:** 0; not a failure code.

**Usage:** Use in an event with a valid acting-unit context.

[Back to index](#function-index)

<a id="call-mindgettarget"></a>
### MindGetTarget

`MindGetTarget()`

Returns the target of the current action (the unit talked to or fought).

**Arguments:** none.

**Returns:** Unit handle; 0 if there is none.

**Usage:** Only meaningful in talk and battle events.

[Back to index](#function-index)

<a id="call-movieplay"></a>
### MoviePlay

`MoviePlay(path)`

Plays a movie file and pauses the script until it ends.

| Argument | Meaning and restrictions |
|---|---|
| `path` | Path of a THP file on the disc, such as "movie/s01.thp". |

**Returns:** 1; 0 during an event skip (nothing is played) or for an invalid string.

**Usage:** A missing file plays the placeholder movie/dummy.thp. The sound channels are faded out.

[Back to index](#function-index)

<a id="call-netuzobattle"></a>
### NetuzoBattle

`NetuzoBattle(attacker, defender, event_battle)`

Resolves and starts a scripted combat exchange between two actors, then suspends the script for the battle process.

| Argument | Meaning and restrictions |
|---|---|
| `attacker` | Valid attacker unit handle; no null-unit guard. |
| `defender` | Valid defender unit handle; no null-unit guard. |
| `event_battle` | 0 clears the event-battle flag; nonzero sets it. Shared battle/death dialogue helpers test this flag to choose their event behavior. |

**Returns:** 1.

**Usage:** Use NetuzoInit and NetuzoSet first when forcing strikes. Requires valid combatants and battle resources. This changes combat state; it is not a visual-only preview.

[Back to index](#function-index)

<a id="call-netuzoinit"></a>
### NetuzoInit

`NetuzoInit()`

Clears all 32 scripted-strike override slots and resets the scripted-battle counters.

**Arguments:** none.

**Returns:** 1.

**Usage:** Call before configuring a new scripted battle; prevents stale overrides from the preceding sequence.

[Back to index](#function-index)

<a id="call-netuzoset"></a>
### NetuzoSet

`NetuzoSet(strike_index, outcome_flags, effect_flags)`

Configures outcome and combat-effect overrides for one scripted strike.

| Argument | Meaning and restrictions |
|---|---|
| `strike_index` | Zero-based strike slot, 0–31. No bounds check. |
| `outcome_flags` | 0 uses normal hit/critical resolution; bit 1 forces a hit, bit 2 a critical, bit 4 a miss. Hit takes precedence over critical, which takes precedence over miss. |
| `effect_flags` | Combat-effect bitmask, not damage. 0 = no forced effects; 0x0001 halves damage rounded up; 0x0002 heals attacker by damage; 0x0004 uses half defender defense; 0x0010 forces lethal-strength damage; 0x0080 prevents counter; 0x0100 sets damage to zero; 0x0200 sets damage to half defender HP; 0x0400 prevents this strike killing the defender. Additional special-skill flags should be retained from the matching battle. |

**Returns:** 1.

**Usage:** Combine effects only deliberately; later damage modifiers can change earlier ones. Set the combatants’ stats/equipment to control ordinary damage.

[Back to index](#function-index)

<a id="call-normal"></a>
### Normal

`Normal()`

Tests for Normal or Easy difficulty.

**Arguments:** none.

**Returns:** 1 on Normal (0) or Easy (3); 0 otherwise.

[Back to index](#function-index)

<a id="call-normalonly"></a>
### NormalOnly

`NormalOnly()`

Always returns 0 in this US build; do not use this as a working difficulty test.

**Arguments:** none.

**Returns:** 0, always.

**Usage:** Use GetRank or a supported difficulty helper instead.

[Back to index](#function-index)

<a id="call-pidisalive"></a>
### PIDisAlive

`PIDisAlive(pid)`

Looks up a character’s current actor and checks that its dead flag is clear.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Exact PID_... character ID string. |

**Returns:** 0 if no actor exists or it is dead; 1 otherwise.

**Usage:** An unused character definition alone is not a living actor.

[Back to index](#function-index)

<a id="call-padresetmask"></a>
### PadResetMask

`PadResetMask(buttons)`

Removes buttons from the input mask.

| Argument | Meaning and restrictions |
|---|---|
| `buttons` | Case-sensitive string: A B X Y Z L R are buttons, S is Start; 4/6/8/2 are left/right/up/down. Concatenate characters, e.g. "AB8". "*" selects every bit; other characters are ignored. |

**Returns:** 0.

[Back to index](#function-index)

<a id="call-padsetmask"></a>
### PadSetMask

`PadSetMask(buttons)`

Adds buttons to the input mask used by event/tutorial control.

| Argument | Meaning and restrictions |
|---|---|
| `buttons` | Case-sensitive string: A B X Y Z L R are buttons, S is Start; 4/6/8/2 are left/right/up/down. Concatenate characters, e.g. "AB8". "*" selects every bit; other characters are ignored. |

**Returns:** 0.

**Usage:** Pair with PadResetMask to restore those buttons when the sequence ends.

[Back to index](#function-index)

<a id="call-pastmapcamera"></a>
### PastMapCamera

`PastMapCamera()`

Turns the camera smoothly back to the angles and distance saved by CopyMapCamera.

**Arguments:** none.

**Returns:** 1.

**Usage:** Does nothing if nothing was saved. While the event is being skipped it jumps there at once.

[Back to index](#function-index)

<a id="call-persongetyelllevel"></a>
### PersonGetYellLevel

`PersonGetYellLevel(pid1, pid2)`

Returns the support rank between two characters.

| Argument | Meaning and restrictions |
|---|---|
| `pid1` | First character's PID. |
| `pid2` | Second character's PID. |

**Returns:** 0 none, 1 C, 2 B, 3 A; -1 if either character has no unit or they are not listed as support partners of each other.

[Back to index](#function-index)

<a id="call-personsetyelllevel"></a>
### PersonSetYellLevel

`PersonSetYellLevel(pid1, pid2, stage)`

Sets two support partners' support points to the threshold of a rank.

| Argument | Meaning and restrictions |
|---|---|
| `pid1` | First character's PID. |
| `pid2` | Second character's PID. |
| `stage` | 0 = C threshold (C conversation becomes available); 1 = B threshold; 2 = A threshold; 3 = A threshold + 1 (A conversation done). |

**Returns:** The support points written; -1 if either character has no unit or they are not partners.

**Usage:** Writes the same value on both characters. The thresholds come from the first character's support list. Other stage values leave the points unchanged.

[Back to index](#function-index)

<a id="call-playerdeadcheck"></a>
### PlayerDeadCheck

`PlayerDeadCheck()`

Tests whether the inactive force list is empty.

**Arguments:** none.

**Returns:** 1 if force 6 is empty; 0 otherwise.

**Usage:** This does not mean “a player died.” Use GetDiedPlayerCount for the death-flagged count.

[Back to index](#function-index)

<a id="call-playerescapecheck"></a>
### PlayerEscapeCheck

`PlayerEscapeCheck()`

Tests whether every existing actor in player force 0 or reserve force 5 has the escaped flag.

**Arguments:** none.

**Returns:** 1 if all match, including when there are no matching actors; 0 if any has not escaped.

[Back to index](#function-index)

<a id="call-playerescapecount"></a>
### PlayerEscapeCount

`PlayerEscapeCount()`

Counts escaped actors in player force 0 and reserve force 5.

**Arguments:** none.

**Returns:** Number of escaped actors.

[Back to index](#function-index)

<a id="call-preloadwait"></a>
### PreLoadWait

`PreLoadWait()`

Yields repeatedly while _pldone() equals zero.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** Exact resource coverage belongs to _pldone's native implementation.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-procexists"></a>
### ProcExists

`ProcExists(process_name)`

Tests whether an engine process with a given name is running.

| Argument | Meaning and restrictions |
|---|---|
| `process_name` | Process name such as E_PadActor or E_TurnToken (not a script function). |

**Returns:** Nonzero if one is running; 0 otherwise.

[Back to index](#function-index)

<a id="call-prockill"></a>
### ProcKill

`ProcKill(process_name)`

Stops every engine process with a given name.

| Argument | Meaning and restrictions |
|---|---|
| `process_name` | Process name such as E_Popup. |

**Returns:** 0.

**Usage:** Stopping a process the game still needs can break the scene.

[Back to index](#function-index)

<a id="call-querylesson"></a>
### QueryLesson

`QueryLesson(lesson_name)`

Tests whether the active lesson has the given name.

| Argument | Meaning and restrictions |
|---|---|
| `lesson_name` | Exact name of the active tutorial lesson. |

**Returns:** 1 on a match; 0 if no matching lesson is active.

[Back to index](#function-index)

<a id="call-rectadjustboundary"></a>
### RectAdjustBoundary

`RectAdjustBoundary(rect_id, alignment)`

Aligns a rectangle’s source image inside the 608 × 448 layout area.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `alignment` | Numeric-keypad layout: 7/8/9 top left/center/right, 4/5/6 middle, 1/2/3 bottom. Other values leave position unchanged. |

**Returns:** 1 if the rectangle exists; 0 otherwise.

**Usage:** Uses the image’s unscaled bounds; this is an alignment selector, not a pixel offset.

[Back to index](#function-index)

<a id="call-rectbuild"></a>
### RectBuild

`RectBuild(rect_id)`

Creates an image (rectangle) from its RID definition, attached to the current event. RID_GMAP_... names create a world-map view.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... image definition name. |

**Returns:** 0.

**Usage:** Remove it with RectKill or RectFadeOutDelete.

[Back to index](#function-index)

<a id="call-rectfadein"></a>
### RectFadeIn

`RectFadeIn(rect_id, frames)`

Fades in a rectangle.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `frames` | Duration in frames. Ordinary rectangles keep only the low byte: use 1–255. World-map fade-in/out uses a signed 16-bit duration, with a minimum of 1. |

**Returns:** 1 if the rectangle exists; 0 otherwise.

**Usage:** Starts the animation without waiting. RectFadeOutDelete uses the ordinary-rectangle path.

[Back to index](#function-index)

<a id="call-rectfadeout"></a>
### RectFadeOut

`RectFadeOut(rect_id, frames)`

Fades out a rectangle.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `frames` | Duration in frames. Ordinary rectangles keep only the low byte: use 1–255. World-map fade-in/out uses a signed 16-bit duration, with a minimum of 1. |

**Returns:** 1 if the rectangle exists; 0 otherwise.

**Usage:** Starts the animation without waiting. RectFadeOutDelete uses the ordinary-rectangle path.

[Back to index](#function-index)

<a id="call-rectfadeoutdelete"></a>
### RectFadeOutDelete

`RectFadeOutDelete(rect_id, frames)`

Fades out and then deletes a rectangle.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `frames` | Duration in frames. Ordinary rectangles keep only the low byte: use 1–255. World-map fade-in/out uses a signed 16-bit duration, with a minimum of 1. |

**Returns:** 1 if the rectangle exists; 0 otherwise.

**Usage:** Starts the animation without waiting. RectFadeOutDelete uses the ordinary-rectangle path.

[Back to index](#function-index)

<a id="call-rectget"></a>
### RectGet

`RectGet(rect_id, property)`

Reads a rectangle property and truncates it to an integer.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `property` | 0 = X; 1 = Y; 2 = Z offset; 3/4 = pivot X/Y; 5 = horizontal scale; 6 = vertical scale; 7 also reads horizontal scale; 8 = rotation; 9 = opacity byte; 10 = brightness byte. Other properties depend on the rectangle type. |

**Returns:** Property value, or 0 if the rectangle is absent. Scale is the raw factor: 100% reads as 1, and 50% truncates to 0.

**Usage:** RectSet takes scale percentages, while RectGet returns the raw factor. Do not round-trip percentage values through this getter.

[Back to index](#function-index)

<a id="call-rectkill"></a>
### RectKill

`RectKill(rect_id)`

Removes an image created by RectBuild or RectLeave.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... name. |

**Returns:** 0.

[Back to index](#function-index)

<a id="call-rectleave"></a>
### RectLeave

`RectLeave(rect_id)`

Creates a rectangle/world-map image without attaching it to the current event as its parent.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |

**Returns:** 0.

**Usage:** Unlike RectBuild, it passes no event parent. Explicitly remove it with RectKill when it is no longer needed; it is not a synonym for deleting the rectangle.

[Back to index](#function-index)

<a id="call-rectmove"></a>
### RectMove

`RectMove(rect_id, focus_x, focus_y, scale_percent, frames, curve)`

Animates a rectangle/world-map image so a source point is centered at (304, 240) at the requested scale.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `focus_x` | Source-image X coordinate to center. |
| `focus_y` | Source-image Y coordinate to center. |
| `scale_percent` | Uniform scale; 100 = normal size. |
| `frames` | Duration in frames; values below 1 become 1. |
| `curve` | 0 linear; 1 quadratic ease-in; 2 cubic ease-in; 3 quartic ease-in; 4 quadratic ease-out; 5 cubic ease-out; 6 quartic ease-out; 7–9 oscillating/bouncing curves; 10 cosine ease-in/out; 11 sine ease-out; 12 cosine ease-in. |

**Returns:** 1 if the target exists; 0 otherwise.

**Usage:** Final position is (304 − focus_x × scale/100, 240 − focus_y × scale/100). This starts animation; it does not wait.

[Back to index](#function-index)

<a id="call-rectmoveoffset"></a>
### RectMoveOffset

`RectMoveOffset(rect_id, x, y, frames, curve)`

Animates a rectangle/world-map image to an explicit offset and restores its scale to 100%.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `x` | Final layout-space X offset. |
| `y` | Final layout-space Y offset. |
| `frames` | Duration in frames; values below 1 become 1. |
| `curve` | 0 linear; 1 quadratic ease-in; 2 cubic ease-in; 3 quartic ease-in; 4 quadratic ease-out; 5 cubic ease-out; 6 quartic ease-out; 7–9 oscillating/bouncing curves; 10 cosine ease-in/out; 11 sine ease-out; 12 cosine ease-in. |

**Returns:** 1 if the target exists; 0 otherwise.

[Back to index](#function-index)

<a id="call-rectpreload"></a>
### RectPreLoad

`RectPreLoad(rect_id)`

Starts loading the image files of a RID definition, so a later RectBuild shows it without delay.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... image definition name. |

**Returns:** No meaningful value; call it for its effect.

**Usage:** Wait with PreLoadWait if the images must be ready.

[Back to index](#function-index)

<a id="call-rectset"></a>
### RectSet

`RectSet(rect_id, property, value)`

Sets a rectangle property immediately.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `property` | 0 = X; 1 = Y; 2 = Z offset; 3/4 = pivot X/Y, the origin of scale and rotation (default half the first image’s size); 5 = horizontal scale; 6 = vertical scale; 7 = both scales; 8 = rotation in degrees; 9 = fade/opacity byte; 10 = brightness byte (128 = normal). Keep other selectors from the matching resource’s existing sequence. |
| `value` | Position in layout coordinates; scale in percent (100 = normal size); opacity 0–255. Byte properties wrap rather than clamp. |

**Returns:** 1 if the rectangle exists; 0 otherwise.

[Back to index](#function-index)

<a id="call-rectsetcurve"></a>
### RectSetCurve

`RectSetCurve(rect_id, property, curve, start, end, frames)`

Animates one rectangle property between two values.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `property` | Same selector as RectSet. |
| `curve` | 0 linear; 1 quadratic ease-in; 2 cubic ease-in; 3 quartic ease-in; 4 quadratic ease-out; 5 cubic ease-out; 6 quartic ease-out; 7–9 oscillating/bouncing curves; 10 cosine ease-in/out; 11 sine ease-out; 12 cosine ease-in. |
| `start` | Starting value; 123456789 means use the current value. Scale properties use percentages. |
| `end` | Final value in the same units as start. |
| `frames` | Duration in frames, not milliseconds. Use a positive count. |

**Returns:** 1 if the rectangle exists; 0 otherwise.

**Usage:** Equal endpoints set immediately. Event skipping applies the final value immediately. This starts animation without waiting for it.

[Back to index](#function-index)

<a id="call-rectsetpos"></a>
### RectSetPos

`RectSetPos(rect_id, x, y)`

Sets a rectangle or world-map image’s position immediately.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `x` | Layout-space X coordinate, not map tile X. |
| `y` | Layout-space Y coordinate. |

**Returns:** 1 if the rectangle/map exists; 0 otherwise.

[Back to index](#function-index)

<a id="call-registglobalflags"></a>
### RegistGlobalFlags

`RegistGlobalFlags()`

Calls the native global registration operation 22 times in fixed order for the original campaign flag list, including repeated reserved names.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** Boot-time setup, not a per-turn reset. Reordering changes saved-bit interpretation; see named flags.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-removebackdrop"></a>
### RemoveBackdrop

`RemoveBackdrop()`

Removes the backdrop process.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-resumeevent"></a>
### ResumeEvent

`ResumeEvent()`

Continues the event frozen by SuspendEvent.

**Arguments:** none.

**Returns:** No meaningful value; call it for its effect.

[Back to index](#function-index)

<a id="call-roofclose"></a>
### RoofClose

`RoofClose(x, y)`

Puts back the roof at a tile with its animation and waits for it.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 after the animation; 0 if there is no roof there, or during an event skip.

**Usage:** The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-roofopen"></a>
### RoofOpen

`RoofOpen(x, y)`

Lifts the roof at a tile with its animation, revealing the building's inside, and waits for it.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 after the animation; 0 if there is no roof there, or during an event skip (the roof lifts at once).

**Usage:** The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-sfxplay"></a>
### SFXPlay

`SFXPlay(sfx_id)`

Plays a sound effect once at full volume.

| Argument | Meaning and restrictions |
|---|---|
| `sfx_id` | SFX_... sound-effect name. |

**Returns:** 1; 0 only if sfx_id is not a valid string.

**Usage:** While the event is being skipped, or while a conversation is being skipped, no sound is played.

[Back to index](#function-index)

<a id="call-sallyaddbygroup"></a>
### SallyAddByGroup

`SallyAddByGroup(group)`

Adds the tiles of a group to the preparation screen's deployment tiles.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Name of a deployment group in the chapter's dispos file. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-sallyaddbypos"></a>
### SallyAddByPos

`SallyAddByPos(x, y)`

Appends a deployment-selection position.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-sallygetsurplus"></a>
### SallyGetSurplus

`SallyGetSurplus()`

Reads the deployment surplus recorded when the deployment-selection flow finishes.

**Arguments:** none.

**Returns:** Surplus byte; initialized to 0 at chapter start.

**Usage:** The stored value is the greater of the selection flow’s minimum and (deployment allowance − selected player count). Read after selection completes, not while editing the selection.

[Back to index](#function-index)

<a id="call-sallysetbygroup"></a>
### SallySetByGroup

`SallySetByGroup(group)`

Replaces the preparation screen's deployment tiles with the tiles of a group.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Name of a deployment group in the chapter's dispos file. |

**Returns:** 1.

**Usage:** Each record of the group gives one deployment tile; the units in the records are not created.

[Back to index](#function-index)

<a id="call-sallysetbypos"></a>
### SallySetByPos

`SallySetByPos(x, y)`

Clears the deployment-selection position list, then adds this position.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |

**Returns:** 1.

**Usage:** Repeated calls replace the list; use SallyAddByPos to append additional positions.

[Back to index](#function-index)

<a id="call-selectauxiliary"></a>
### SelectAuxiliary

`SelectAuxiliary(group)`

Starts the auxiliary-unit selection flow for a deployment group and suspends the calling script.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing deployment group name. |

**Returns:** 1 when accepted; 0 for an invalid group argument.

[Back to index](#function-index)

<a id="call-setambient"></a>
### SetAmbient

`SetAmbient(red, green, blue)`

Sets map ambient lighting color, refreshes the map and yields the script.

| Argument | Meaning and restrictions |
|---|---|
| `red` | Red component, 0–255. |
| `green` | Green component, 0–255. |
| `blue` | Blue component, 0–255. |

**Returns:** 1.

**Usage:** Components are truncated to bytes, not clamped. Alpha is fixed to 255.

[Back to index](#function-index)

<a id="call-setcamsuspend"></a>
### SetCamSuspend

`SetCamSuspend(enabled)`

Sets the camera-suspension flag for map scenes.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-setcircle"></a>
### SetCircle

`SetCircle(enabled)`

Enables or disables the scene’s unit-circle display setting.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-setdiffuse"></a>
### SetDiffuse

`SetDiffuse(red, green, blue)`

Sets map diffuse lighting color, refreshes the map and yields the script.

| Argument | Meaning and restrictions |
|---|---|
| `red` | Red component, 0–255. |
| `green` | Green component, 0–255. |
| `blue` | Blue component, 0–255. |

**Returns:** 1.

**Usage:** Components are truncated to bytes, not clamped. Alpha is fixed to 255.

[Back to index](#function-index)

<a id="call-seteventbattle"></a>
### SetEventBattle

`SetEventBattle(enabled)`

Selects the special event presentation branch when the next battle animation is initialized.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | 0 uses the ordinary presentation selection; nonzero overrides it with event presentation mode. |

**Returns:** 1.

**Usage:** This is a shared scene setting, not a call that starts combat or forces damage. Set before NetuzoBattle and restore 0 after the staged battle.

[Back to index](#function-index)

<a id="call-seteventcameraat"></a>
### SetEventCameraAt

`SetEventCameraAt(time_ms, x, y, height)`

Adds a keyframe for the point the event camera looks at.

| Argument | Meaning and restrictions |
|---|---|
| `time_ms` | Time of the keyframe from the start of the path, in milliseconds. |
| `x` | X in tiles divided by the SetEventCameraPrec divisor; the camera looks at the tile centre (0.5 is added). |
| `y` | Y in tiles, same rule as x. |
| `height` | Height divided by the same divisor (no 0.5 added). |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-seteventcameraprec"></a>
### SetEventCameraPrec

`SetEventCameraPrec(precision)`

Sets the divisor applied to later SetEventCameraAt coordinates, allowing positions finer than a tile.

| Argument | Meaning and restrictions |
|---|---|
| `precision` | Divisor: 1 means coordinates are tiles; 10 means tenths of a tile; 100 hundredths. Vanilla uses 1, 10 and 100. |

**Returns:** 1.

**Usage:** The setting stays until changed. The default is 1.

[Back to index](#function-index)

<a id="call-seteventcamerarot"></a>
### SetEventCameraRot

`SetEventCameraRot(time_ms, yaw, pitch, distance)`

Adds a keyframe for the event camera's angles and distance.

| Argument | Meaning and restrictions |
|---|---|
| `time_ms` | Time of the keyframe from the start of the path, in milliseconds. |
| `yaw` | Horizontal camera angle in degrees. |
| `pitch` | Vertical camera angle in degrees (vanilla uses 40–63). |
| `distance` | Distance from the looked-at point, in tiles (vanilla uses 10–45). |

**Returns:** 1.

**Usage:** Not affected by SetEventCameraPrec.

[Back to index](#function-index)

<a id="call-setfog"></a>
### SetFog

`SetFog(fog_type, start_distance, end_distance, red, green, blue)`

Sets the map’s rendering fog and refreshes its render state.

| Argument | Meaning and restrictions |
|---|---|
| `fog_type` | Rendering fog mode byte. Use the map’s existing supported mode; 0 disables fog. |
| `start_distance` | Signed-byte fog start distance in map units; converted by 5 × map scale for rendering. |
| `end_distance` | Signed-byte fog end distance in the same units. |
| `red` | Fog color red, 0–255. |
| `green` | Fog color green, 0–255. |
| `blue` | Fog color blue, 0–255. |

**Returns:** 1.

**Usage:** This changes visual distance fog, not which tiles units can see. Use SetSight for gameplay visibility.

[Back to index](#function-index)

<a id="call-setfragile"></a>
### SetFragile

`SetFragile(x, y, hp)`

Adds a breakable terrain entry with the requested HP.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |
| `hp` | Initial and current HP, stored as a byte (0–255). |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-setgrid"></a>
### SetGrid

`SetGrid(percent)`

Sets the map-grid display intensity or restores the value saved when scene settings were created.

| Argument | Meaning and restrictions |
|---|---|
| `percent` | 0–100 grid intensity; values above 100 become 100. A negative value restores the saved grid setting if scene settings exist. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-setmapcamera"></a>
### SetMapCamera

`SetMapCamera(yaw, pitch, distance)`

Turns the map camera smoothly to new angles and distance; the point it looks at does not change.

| Argument | Meaning and restrictions |
|---|---|
| `yaw` | Horizontal camera angle in degrees. |
| `pitch` | Vertical camera angle in degrees (vanilla uses 40–63). |
| `distance` | Distance from the looked-at point, in tiles (vanilla uses 10–45). |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-setonbtfocus"></a>
### SetOnBtFocus

`SetOnBtFocus(enabled)`

Enables or disables automatic battle-focus behavior.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-setoutlink"></a>
### SetOutLink

`SetOutLink(enabled)`

Enables or disables the outer-link portion of the map-link grid and rebuilds that grid.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1.

**Usage:** Shared scene setting. Restore the chapter’s setting after staged movement that changes it.

[Back to index](#function-index)

<a id="call-setpit"></a>
### SetPit

`SetPit(x, y)`

Adds a pit terrain entry at the given tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-setpullcursor"></a>
### SetPullCursor

`SetPullCursor(enabled)`

Enables or disables automatic cursor pulling.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-setrock"></a>
### SetRock

`SetRock(x, y, direction, path_index)`

Adds a rolling-rock terrain entry connected to a registered motion path.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |
| `direction` | Initial direction code used by the matching rock setup. |
| `path_index` | Slot returned by TTPMEntry, 0–31. Register the path first. |

**Returns:** 1.

**Usage:** The map needs compatible rock geometry. This registers the terrain entry; it does not immediately roll the rock.

[Back to index](#function-index)

<a id="call-setroofenable"></a>
### SetRoofEnable

`SetRoofEnable(x, y, enabled)`

Changes the enabled state of the roof section found at the supplied map position and refreshes the map.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1 if a roof entry is found; 0 otherwise.

[Back to index](#function-index)

<a id="call-setsepia"></a>
### SetSepia

`SetSepia(enabled)`

Changes the sepia scene effect setting.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | Use 1 to start the sepia effect; 0 to remove it. Other values also take the removal branch. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-setshooter"></a>
### SetShooter

`SetShooter(x, y, facing, iid)`

Places a ballista on a tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |
| `facing` | Direction the ballista points: 1 left, 2 right, 4 down, 8 up. |
| `iid` | Ballista item: IID_LONGARCH, IID_IRONARCH, IID_KILLERARCH or IID_ONAGER. |

**Returns:** 1.

**Usage:** The ballista starts with the item's full uses. The map needs a ballista model at that tile. The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-setsight"></a>
### SetSight

`SetSight(mode, unused)`

Sets the fog-of-war/sight mode, recalculates map ranges and refreshes the map.

| Argument | Meaning and restrictions |
|---|---|
| `mode` | Sight-mode byte; internal difficulty other than 1 forces this to 0. Preserve the chapter’s supported mode values. |
| `unused` | Ignored by this US implementation; pass 0 when creating a new call. |

**Returns:** 1.

**Usage:** The signature still requires two arguments even though the second is ignored. This controls gameplay visibility, unlike SetFog’s rendering effect.

[Back to index](#function-index)

<a id="call-setterrain"></a>
### SetTerrain

`SetTerrain(x, y, terrain)`

Changes the terrain type of one tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |
| `terrain` | Terrain ID (index into the terrain table). |

**Returns:** 0.

**Usage:** Writes the terrain grid only: the map's look does not change, and movement ranges update at the next map refresh (MapUpdate). No coordinate check.

[Back to index](#function-index)

<a id="call-setweather"></a>
### SetWeather

`SetWeather(weather)`

Changes the map weather byte and refreshes weather, lighting and visibility rendering.

| Argument | Meaning and restrictions |
|---|---|
| `weather` | Weather ID supported by the loaded chapter. Preserve the matching map’s existing IDs when adding effects. |

**Returns:** 1.

**Usage:** The script yields after refreshing. Weather effects depend on the map’s resources.

[Back to index](#function-index)

<a id="call-setwhitebackdrop"></a>
### SetWhiteBackdrop

`SetWhiteBackdrop()`

Starts the solid-white backdrop process.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-shooterbulletcheck"></a>
### ShooterBulletCheck

`ShooterBulletCheck()`

Counts the ballista shots spent on the map.

**Arguments:** none.

**Returns:** Sum, over every ballista on the map, of 5 minus its remaining shots.

**Usage:** Assumes five shots per ballista; a ballista with more shots adds a negative amount.

[Back to index](#function-index)

<a id="call-showmapcursor"></a>
### ShowMapCursor

`ShowMapCursor(x, y)`

Shows the blinking map cursor on a tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1.

**Usage:** Remove it with HideMapCursor.

[Back to index](#function-index)

<a id="call-soundbosstalkend"></a>
### SoundBossTalkEnd

`SoundBossTalkEnd()`

Under the same battle-type bit guard, restores environment, fades channel 1 over 750 and continues channel 0 over 750.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-soundbosstalkstart"></a>
### SoundBossTalkStart

`SoundBossTalkStart(bgm_id)`

Only when GetBattleType() has bit 0x80000000: silences environment with parameter 30, mutes channel 0 over 750, and plays the supplied track on channel 1.

| Argument | Meaning and restrictions |
|---|---|
| `bgm_id` | Existing BGM_... track ID; not an audio filename. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-staffroll"></a>
### StaffRoll

`StaffRoll(duration_ms)`

Starts the staff credits and suspends the calling script.

| Argument | Meaning and restrictions |
|---|---|
| `duration_ms` | Duration in milliseconds. Conversion to 60 Hz frames truncates fractional frames. |

**Returns:** 1.

**Usage:** Intended for ending sequences with the corresponding display resources loaded.

[Back to index](#function-index)

<a id="call-starteventcamera"></a>
### StartEventCamera

`StartEventCamera(easing)`

Plays the event-camera path. Keyframes are joined with a smooth curve; if the path has no keyframe at time 0, the camera's current state is added as the first one.

| Argument | Meaning and restrictions |
|---|---|
| `easing` | How time advances along the path: 0 even speed, 1 starts slowly, 2 ends slowly, 3 starts and ends slowly. |

**Returns:** 1.

**Usage:** Does not wait: use EventCameraWait. During an event skip the path ends at once.

[Back to index](#function-index)

<a id="call-suspendevent"></a>
### SuspendEvent

`SuspendEvent()`

Freezes the running event so another script (a tutorial) can run, saving the event's state.

**Arguments:** none.

**Returns:** No meaningful value; call it for its effect.

**Usage:** Pair it with ResumeEvent. The camera is protected from map input while suspended.

[Back to index](#function-index)

<a id="call-sysgetround"></a>
### SysGetRound

`SysGetRound()`

Reads the playthrough ordinal from the clear-data record.

**Arguments:** none.

**Returns:** 1 plus the number of consecutive occupied clear-data slots, from 1 to 31.

**Usage:** Used by trial-map unlock helpers; not the current map turn.

[Back to index](#function-index)

<a id="call-tboxopen"></a>
### TBoxOpen

`TBoxOpen(x, y)`

Plays the opening of the chest at a tile and waits for it, and marks the chest as opened.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 if a chest was found; 0 otherwise.

**Usage:** Gives no item: the chest event gives it separately (MindGetItem or UnitGetItemShowing). The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-ttpmentry"></a>
### TTPMEntry

`TTPMEntry(path)`

Stores a path for a rolling rock in the first free path slot.

| Argument | Meaning and restrictions |
|---|---|
| `path` | Direction string: 2 down, 4 left, 6 right, 8 up, one tile per character, for example "66222". Kept by reference, not copied. |

**Returns:** Slot 0–31; -1 if all 32 slots are used.

**Usage:** Give the slot to SetRock. Use a string literal so it stays valid.

[Back to index](#function-index)

<a id="call-ttpminit"></a>
### TTPMInit

`TTPMInit()`

Clears the 32 registered terrain-motion path slots.

**Arguments:** none.

**Returns:** 1.

**Usage:** Call before registering rock-motion paths for a chapter. Existing rocks referring to these slots need their paths registered again.

[Back to index](#function-index)

<a id="call-talkevent"></a>
### TalkEvent

`TalkEvent(message_id)`

Opens the conversation window with a message and pauses the script until the conversation ends or reaches a $H hold point.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a loaded message file, not literal text. |

**Returns:** 1.

**Usage:** If a conversation window is already open, the new message plays in it. After a $H hold, continue with TalkResume. During a skip the text is processed at once without being shown.

[Back to index](#function-index)

<a id="call-talkeventdirect"></a>
### TalkEventDirect

`TalkEventDirect(message_id)`

Starts the supplied event message, or passes it to the existing conversation process.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a loaded message resource. |

**Returns:** 1.

**Usage:** Does not itself wait until every line has finished; use the normal TalkExist/TalkResume flow.

[Back to index](#function-index)

<a id="call-talkexist"></a>
### TalkExist

`TalkExist()`

Tests whether a conversation is still running.

**Arguments:** none.

**Returns:** 1 while a conversation window is open and not finished; 0 otherwise.

[Back to index](#function-index)

<a id="call-talkresume"></a>
### TalkResume

`TalkResume()`

Continues a conversation stopped at a $H hold point and pauses the script again until it ends or reaches the next hold.

**Arguments:** none.

**Returns:** 1.

**Usage:** Only call it while a conversation is held.

[Back to index](#function-index)

<a id="call-timeishow"></a>
### TimeiShow

`TimeiShow(x, y, message_id, appear_ms, hold_ms, disappear_ms)`

Shows a timed location-name caption.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Screen-space caption X coordinate. |
| `y` | Screen-space caption Y coordinate. |
| `message_id` | Message ID in a loaded message resource. |
| `appear_ms` | Appearance duration in milliseconds. |
| `hold_ms` | Time fully displayed, in milliseconds. |
| `disappear_ms` | Disappearance duration in milliseconds. |

**Returns:** 1 when accepted; 0 for an invalid message argument.

**Usage:** Timing is converted to 60 Hz frames. This schedules the caption without waiting through its whole lifetime.

[Back to index](#function-index)

<a id="call-timeishowgmap"></a>
### TimeiShowGMap

`TimeiShowGMap(x, y, extra_width, message_id, appear_ms, hold_ms, disappear_ms)`

Shows a timed location caption using the world-map caption style.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Screen-space caption X coordinate. |
| `y` | Screen-space caption Y coordinate. |
| `extra_width` | Additional width added to the caption’s text-sized background, in screen coordinates. Use 0 for the normal width. |
| `message_id` | Message ID in a loaded message resource. |
| `appear_ms` | Appearance duration in milliseconds. |
| `hold_ms` | Time fully displayed, in milliseconds. |
| `disappear_ms` | Disappearance duration in milliseconds. |

**Returns:** 1 when accepted; 0 for invalid message.

**Usage:** The caption is positioned in screen coordinates; this call does not take a map ID.

[Back to index](#function-index)

<a id="call-timeishowhold"></a>
### TimeiShowHold

`TimeiShowHold(caption_id, x, y, message_id, appear_ms)`

Shows a location-name caption that stays visible until explicitly released.

| Argument | Meaning and restrictions |
|---|---|
| `caption_id` | Byte slot ID for later TimeiShowHoldOff; avoid 255, which is used as the all-captions selector. |
| `x` | Screen-space caption X coordinate. |
| `y` | Screen-space caption Y coordinate. |
| `message_id` | Message ID in a loaded message resource. |
| `appear_ms` | Appearance duration in milliseconds. |

**Returns:** 1 when accepted; 0 for invalid message.

[Back to index](#function-index)

<a id="call-timeishowholdgmap"></a>
### TimeiShowHoldGMap

`TimeiShowHoldGMap(caption_id, x, y, extra_width, message_id, appear_ms)`

Shows a held location caption using the world-map caption style.

| Argument | Meaning and restrictions |
|---|---|
| `caption_id` | Byte ID used by TimeiShowHoldOff; avoid 255. |
| `x` | Screen-space caption X coordinate. |
| `y` | Screen-space caption Y coordinate. |
| `extra_width` | Additional width added to the caption’s text-sized background, in screen coordinates. Use 0 for the normal width. |
| `message_id` | Message ID in a loaded message resource. |
| `appear_ms` | Appearance duration in milliseconds. |

**Returns:** 1 when accepted; 0 for invalid message.

[Back to index](#function-index)

<a id="call-timeishowholdoff"></a>
### TimeiShowHoldOff

`TimeiShowHoldOff(caption_id, disappear_ms)`

Starts disappearance of the held caption with this ID.

| Argument | Meaning and restrictions |
|---|---|
| `caption_id` | ID passed to TimeiShowHold or TimeiShowHoldGMap. |
| `disappear_ms` | Disappearance duration in milliseconds. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-timeishowholdoffall"></a>
### TimeiShowHoldOffAll

`TimeiShowHoldOffAll(disappear_ms)`

Starts disappearance of every held caption.

| Argument | Meaning and restrictions |
|---|---|
| `disappear_ms` | Disappearance duration in milliseconds. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-trialaddunit"></a>
### TrialAddUnit

`TrialAddUnit()`

Reads SysGetRound and calls Join for always_T_03 at >=4, always_T_05 at >=6, always_T_07 at >=8, always_T_10 at >=11, and always_T_15 at >=16. These are independent tests: higher counts call all qualifying groups.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tut3sarrowabanim"></a>
### Tut3SArrowABAnim

`Tut3SArrowABAnim(rect_id, period_ms, amplitude)`

Continuously oscillates a tutorial arrow rectangle along its positive diagonal axis.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `period_ms` | Positive oscillation period in milliseconds. Zero causes division by zero; do not pass 0. |
| `amplitude` | Movement amplitude in screen coordinates; use a small positive value such as 4 or 6. |

**Returns:** No useful script result; call for its side effect.

**Usage:** The rectangle must exist first. The animation is attached to it and restores the original position when cleaned up; remove the rectangle to end the display.

[Back to index](#function-index)

<a id="call-tut3sarrowbcanim"></a>
### Tut3SArrowBCAnim

`Tut3SArrowBCAnim(rect_id, period_ms, amplitude)`

Continuously oscillates a tutorial arrow rectangle along its horizontal axis.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `period_ms` | Positive oscillation period in milliseconds. Zero causes division by zero; do not pass 0. |
| `amplitude` | Movement amplitude in screen coordinates; use a small positive value such as 4 or 6. |

**Returns:** No useful script result; call for its side effect.

**Usage:** The rectangle must exist first. The animation is attached to it and restores the original position when cleaned up; remove the rectangle to end the display.

[Back to index](#function-index)

<a id="call-tut3sarrowcaanim"></a>
### Tut3SArrowCAAnim

`Tut3SArrowCAAnim(rect_id, period_ms, amplitude)`

Continuously oscillates a tutorial arrow rectangle along its negative diagonal axis.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `period_ms` | Positive oscillation period in milliseconds. Zero causes division by zero; do not pass 0. |
| `amplitude` | Movement amplitude in screen coordinates; use a small positive value such as 4 or 6. |

**Returns:** No useful script result; call for its side effect.

**Usage:** The rectangle must exist first. The animation is attached to it and restores the original position when cleaned up; remove the rectangle to end the display.

[Back to index](#function-index)

<a id="call-tut3sarrowdanim"></a>
### Tut3SArrowDAnim

`Tut3SArrowDAnim(rect_id, period_ms, amplitude)`

Continuously oscillates a tutorial arrow rectangle along its downward vertical axis.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `period_ms` | Positive oscillation period in milliseconds. Zero causes division by zero; do not pass 0. |
| `amplitude` | Movement amplitude in screen coordinates; use a small positive value such as 4 or 6. |

**Returns:** No useful script result; call for its side effect.

**Usage:** The rectangle must exist first. The animation is attached to it and restores the original position when cleaned up; remove the rectangle to end the display.

[Back to index](#function-index)

<a id="call-tut3sarrowuanim"></a>
### Tut3SArrowUAnim

`Tut3SArrowUAnim(rect_id, period_ms, amplitude)`

Continuously oscillates a tutorial arrow rectangle along its upward vertical axis.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `period_ms` | Positive oscillation period in milliseconds. Zero causes division by zero; do not pass 0. |
| `amplitude` | Movement amplitude in screen coordinates; use a small positive value such as 4 or 6. |

**Returns:** No useful script result; call for its side effect.

**Usage:** The rectangle must exist first. The animation is attached to it and restores the original position when cleaned up; remove the rectangle to end the display.

[Back to index](#function-index)

<a id="call-tutbasescreate"></a>
### TutBasesCreate

`TutBasesCreate()`

Yields until "E_BMapPlph" exists, calls TutorialBasesCreate, then yields while "E_BasesToken" exists.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutbasesdelete"></a>
### TutBasesDelete

`TutBasesDelete()`

Calls TutorialBasesDelete.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutentrycommon"></a>
### TutEntryCommon

`TutEntryCommon(script_path, entry_name)`

Sleeps the tail module with CmSleepScript(""), calls _cmb_mess_load(script_path,"mess/tut.m"), then TutorialCall(entry_name).

| Argument | Meaning and restrictions |
|---|---|
| `script_path` | Tutorial CMB resource path, such as scripts/c80.cmb. |
| `entry_name` | Named tutorial entry function in the loaded module. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutpadactor"></a>
### TutPadActor

`TutPadActor(command)`

Calls _pa(action), then yields while process "E_PadActor" exists.

| Argument | Meaning and restrictions |
|---|---|
| `command` | Scripted input string passed to _pa; see _pa for its characters. |

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** The command string is passed to _pa unchanged; use strings from the vanilla tutorial scripts.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutpreloadwait"></a>
### TutPreLoadWait

`TutPreLoadWait()`

Calls GameBind, externally invokes PreLoadWait, then GameUnbind.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutsallycreate"></a>
### TutSallyCreate

`TutSallyCreate()`

Yields until "E_BMapPlph" exists, calls TutorialSallyCreate, then yields while "E_SallyToken" exists.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutsallydelete"></a>
### TutSallyDelete

`TutSallyDelete()`

Calls TutorialSallyDelete.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutshow"></a>
### TutShow

`TutShow(text_resource)`

Starts a tutorial text display.

| Argument | Meaning and restrictions |
|---|---|
| `text_resource` | Text resource expected by the existing tutorial display sequence. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-tutshowkari"></a>
### TutShowKari

`TutShowKari(x, y, message_id, fade_ms, hold_ms)`

Shows a temporary tutorial caption with matching appearance and disappearance durations.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Screen-space caption X coordinate. |
| `y` | Screen-space caption Y coordinate. |
| `message_id` | Message ID in a loaded message resource. |
| `fade_ms` | Duration of each fade, in milliseconds. |
| `hold_ms` | Fully visible time in milliseconds. |

**Returns:** 1 when accepted; 0 for invalid message.

[Back to index](#function-index)

<a id="call-tuttalkevent"></a>
### TutTalkEvent

`TutTalkEvent(message_id)`

Calls GameBind, _tt(message_id), yields while TalkExist(), then GameUnbind.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a currently loaded message resource; not literal dialogue text. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tuttalkresume"></a>
### TutTalkResume

`TutTalkResume()`

Calls GameBind, _tr(), yields while TalkExist(), then GameUnbind.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutwaitf"></a>
### TutWaitF

`TutWaitF(frames)`

Calls GameBind, yields once per loop iteration until the counter reaches frames, then GameUnbind.

| Argument | Meaning and restrictions |
|---|---|
| `frames` | Loop/yield count. Nonpositive values produce no loop iterations. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutwaitfornexttaiki"></a>
### TutWaitForNextTaiki

`TutWaitForNextTaiki()`

Calls taikitk(), then yields while process "E_TaikiToken" exists.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** The token ends at the player's next Wait command.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutwaitfornextturn"></a>
### TutWaitForNextTurn

`TutWaitForNextTurn()`

Calls turntk(), then yields while process "E_TurnToken" exists.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** The token ends at the next turn change.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutwaitfornextturnafter"></a>
### TutWaitForNextTurnAfter

`TutWaitForNextTurnAfter()`

Calls turnatk(), then yields while process "E_TurnAToken" exists.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** The token ends at the next end of turn.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutwaitm"></a>
### TutWaitM

`TutWaitM(duration_ms)`

Calls GameBind, computes duration_ms * 60 / 1000 with integer arithmetic, yields that many iterations, then GameUnbind.

| Argument | Meaning and restrictions |
|---|---|
| `duration_ms` | Milliseconds, converted with the fixed factor 60/1000 (one yield per frame). |

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** duration_ms × 60 / 1000 yields, one frame each.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutorialbasescreate"></a>
### TutorialBasesCreate

`TutorialBasesCreate()`

Opens the base menu inside a tutorial.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-tutorialbasesdelete"></a>
### TutorialBasesDelete

`TutorialBasesDelete()`

Closes the base menu opened by TutorialBasesCreate.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-tutorialcall"></a>
### TutorialCall

`TutorialCall(entry_name)`

Starts a named function of a loaded tutorial script and stops the AI phase.

| Argument | Meaning and restrictions |
|---|---|
| `entry_name` | Name of a function in a loaded script, such as tut_02_Visit. |

**Returns:** 1 if the function exists; 0 otherwise.

[Back to index](#function-index)

<a id="call-tutorialdialog"></a>
### TutorialDialog

`TutorialDialog(message_id)`

Calls td(message_id), yields once, then tde().

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a currently loaded message resource; not literal dialogue text. |

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** td pauses the script until the dialog closes; tde then marks the event as suspended.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutorialforget"></a>
### TutorialForget

`TutorialForget(tutorial_id)`

Clears a tutorial’s learned mark.

| Argument | Meaning and restrictions |
|---|---|
| `tutorial_id` | Bit index of an existing tutorial entry; use its numeric ID, not its script export name. |

**Returns:** 1.

**Usage:** Learned status and unlocked status are separate.

[Back to index](#function-index)

<a id="call-tutorialin"></a>
### TutorialIn

`TutorialIn(script_path, entry_name)`

Fades with mode 3 for 266 and waits; AllPush; MapFree; TutEntryCommon; SuspendEvent; yields once.

| Argument | Meaning and restrictions |
|---|---|
| `script_path` | Tutorial CMB path forwarded to TutEntryCommon. |
| `entry_name` | Tutorial entry name forwarded to TutEntryCommon. |

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** Use with the matching exit/restoration flow; it changes module and map ownership.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutorialinit"></a>
### TutorialInit

`TutorialInit()`

Enables skip, calls _seqini, kills "E_Popup", calls _bmsini, then external Startup and RegistLocationTT.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutorialinitialize"></a>
### TutorialInitialize

`TutorialInitialize()`

Starts tutorial initialization and suspends the calling script until it completes.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-tutoriallearn"></a>
### TutorialLearn

`TutorialLearn(tutorial_id)`

Marks a tutorial as learned.

| Argument | Meaning and restrictions |
|---|---|
| `tutorial_id` | Bit index of an existing tutorial entry; use its numeric ID, not its script export name. |

**Returns:** 1.

**Usage:** Learned status and unlocked status are separate.

[Back to index](#function-index)

<a id="call-tutoriallock"></a>
### TutorialLock

`TutorialLock(tutorial_id)`

Locks a tutorial.

| Argument | Meaning and restrictions |
|---|---|
| `tutorial_id` | Bit index of an existing tutorial entry; use its numeric ID, not its script export name. |

**Returns:** 1.

**Usage:** Learned status and unlocked status are separate.

[Back to index](#function-index)

<a id="call-tutorialout"></a>
### TutorialOut

`TutorialOut()`

Frees "mess/tut.m", frees the last-loaded script, wakes sleeping scripts and resumes the suspended event.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutorialresume"></a>
### TutorialResume

`TutorialResume()`

Returns to the tutorial menu after a tutorial ends (the last step of ComebackFunc).

**Arguments:** none.

**Returns:** No meaningful value; call it for its effect.

[Back to index](#function-index)

<a id="call-tutorialresumeout"></a>
### TutorialResumeOut

`TutorialResumeOut()`

MapFree; yield; AllPop; MapReload; UnitDispReload; external Startup; MapUpdate; Fade(2,266); FadeWait.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** Runs the chapter's Startup again, so flag registration order must stay stable.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutorialsallycreate"></a>
### TutorialSallyCreate

`TutorialSallyCreate()`

Opens the preparations screen inside a tutorial.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-tutorialsallydelete"></a>
### TutorialSallyDelete

`TutorialSallyDelete()`

Closes the preparations screen opened by TutorialSallyCreate.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-tutorialunlock"></a>
### TutorialUnlock

`TutorialUnlock(tutorial_id)`

Unlocks a tutorial.

| Argument | Meaning and restrictions |
|---|---|
| `tutorial_id` | Bit index of an existing tutorial entry; use its numeric ID, not its script export name. |

**Returns:** 1.

**Usage:** Learned status and unlocked status are separate.

[Back to index](#function-index)

<a id="call-tutorial-fadein"></a>
### Tutorial_FadeIn

`Tutorial_FadeIn()`

Disables skip, builds RID_MASK, sets property 9 to 0 and property 2 to -835, then RectSetCurve("RID_MASK",9,0,0,128,100).

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** The exact rectangle property/curve enum meanings are not all established. Preserve the sequence.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutorial-fadeout"></a>
### Tutorial_FadeOut

`Tutorial_FadeOut()`

Calls RectSetCurve("RID_MASK",9,0,160,0,100), kills RID_MASK, then enables skip.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitadditem"></a>
### UnitAddItem

`UnitAddItem(unit, item_id)`

Puts an item in a unit's inventory, silently: weapons, tomes and staves go to the first free weapon slot (0–3), items and accessories to the first free item slot (4–7).

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `item_id` | IID_... item ID. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** If those slots are full, the item is not added, but the call still returns 1. To show the 'got item' window, use UnitGetItemShowing.

[Back to index](#function-index)

<a id="call-unitaddskill"></a>
### UnitAddSkill

`UnitAddSkill(unit, skill_id)`

Gives a unit a skill.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `skill_id` | SID_... skill ID. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** Adds it to the unit's runtime skill set; skill capacity is not checked. An unknown SID does nothing.

[Back to index](#function-index)

<a id="call-unitanim"></a>
### UnitAnim

`UnitAnim(unit, animation)`

Loads and plays a unit animation with the default blend length of 16, replacing an existing scripted animation for that unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `animation` | Animation selector supported by this unit’s model/animation set. Use a selector from a matching unit; different models need not support the same animations. |

**Returns:** 1 when scheduled; 0 for an invalid unit or during skipping. The skip path still applies the animation immediately.

**Usage:** Use UnitMoveWait to synchronize with the scene’s motion/animation processes.

[Back to index](#function-index)

<a id="call-unitanimbypid"></a>
### UnitAnimByPID

`UnitAnimByPID(pid, animation)`

Resolves a deployed actor and calls UnitAnim. Missing actor exits without animation.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `animation` | Native animation selector. |

**Returns:** 0 even when the call succeeds; native result is discarded.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitanimf"></a>
### UnitAnimF

`UnitAnimF(unit, animation, blend_duration)`

Loads and plays a unit animation with a chosen transition length, replacing an existing scripted animation for that unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `animation` | Animation selector supported by this unit’s model/animation set. Use a selector from a matching unit; different models need not support the same animations. |
| `blend_duration` | Animation transition/blending length; UnitAnim uses 16. Zero requests an immediate switch once loaded; negative applies the animation immediately without the normal loading/wait process. This is not the length of the entire animation. |

**Returns:** 1 when scheduled; 0 for invalid unit, event skipping, or a negative blend duration. The latter two cases still apply the animation immediately.

**Usage:** The engine can increase the blend length for some current-animation categories, and can fall back to an immediate switch when too many animation layers exist.

[Back to index](#function-index)

<a id="call-unitanimfbypid"></a>
### UnitAnimFByPID

`UnitAnimFByPID(pid, animation, blend_duration)`

Resolves a deployed actor and calls UnitAnimF. Missing actor exits without animation.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `animation` | Native animation selector. |
| `blend_duration` | Animation transition/blending length; UnitAnim uses 16. Zero requests an immediate switch once loaded; negative applies the animation immediately without the normal loading/wait process. This is not the length of the entire animation. |

**Returns:** 0 even when the call succeeds; native result is discarded.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitbreakup"></a>
### UnitBreakup

`UnitBreakup(unit)`

Separates a carrying pair: the carried unit is put back on the map on the carrier's tile. Either unit of the pair can be given.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** 1 for a valid unit; 0 otherwise.

**Usage:** Both units are marked as not having acted. Only call it on a unit that is carrying or carried (status 0x2 or 0x4), as UnitCheckLinked_Breakup does.

[Back to index](#function-index)

<a id="call-unitcanuseit"></a>
### UnitCanUseIt

`UnitCanUseIt(unit, slot)`

Checks whether the unit can use the item in the specified inventory slot.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `slot` | Inventory index: 0–3 weapon slots, 4–7 item/accessory slots. Never pass an index outside 0–7. |

**Returns:** Use predicate; 0 for an invalid unit or an empty slot.

[Back to index](#function-index)

<a id="call-unitcheckdeadhere"></a>
### UnitCheckDeadHere

`UnitCheckDeadHere(unit)`

Returns true exactly when the non-null unit's status has bit 0x8000 set.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** 0 for null/bit clear; 1 for bit set.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitcheckdeadherebypid"></a>
### UnitCheckDeadHereByPID

`UnitCheckDeadHereByPID(pid)`

Looks up the PID and calls UnitCheckDeadHere; a missing actor returns 0.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** 0 or 1.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitcheckexists"></a>
### UnitCheckExists

`UnitCheckExists(unit)`

Checks non-null actor membership in force 0, 1, 2 or 3. It reads status but does not use that value in the decision.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** 1 for one of those active forces; 0 otherwise.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitcheckexistsbypid"></a>
### UnitCheckExistsByPID

`UnitCheckExistsByPID(pid)`

Looks up the actor and forwards to UnitCheckExists.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** 0 or 1; not an actor reference.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitcheckexistsbypid2"></a>
### UnitCheckExistsByPID2

`UnitCheckExistsByPID2(pid)`

Looks up the actor and checks UnitCheckExists.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** The actor reference if deployed in force 0–3; 0 otherwise. Unlike UnitCheckExistsByPID, success is not normalized to 1.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitchecklinked-breakup"></a>
### UnitCheckLinked_Breakup

`UnitCheckLinked_Breakup(unit)`

Returns early for null; otherwise calls UnitBreakup only if status & 0x06 is nonzero.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** 0 for null; 1 otherwise, including when no breakup was needed.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitchecklinked-breakupbypid"></a>
### UnitCheckLinked_BreakupByPID

`UnitCheckLinked_BreakupByPID(pid)`

Resolves a deployed actor and forwards to UnitCheckLinked_Breakup.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** 0 if unavailable; otherwise the linked-check helper result.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitchecklivebypid"></a>
### UnitCheckLiveByPID

`UnitCheckLiveByPID(pid)`

Looks up the PID, then returns false for a null actor, status bit 0x08, or force 6; true otherwise. This is not a deployed-on-map test.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** 0 or 1.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitclasschange"></a>
### UnitClassChange

`UnitClassChange(unit)`

Plays the class-change (promotion) scene for a unit and promotes it, and waits for it.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** 1; 0 for an invalid unit or a unit without the SID_EVENTCC skill.

**Usage:** Only works on units that have SID_EVENTCC. The new class is the class's promotion class.

[Back to index](#function-index)

<a id="call-unitclrskill"></a>
### UnitClrSkill

`UnitClrSkill(unit, skill_id)`

Removes a skill from a unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `skill_id` | SID_... skill ID. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** Removes it from the unit's runtime skill set.

[Back to index](#function-index)

<a id="call-unitclrstatus"></a>
### UnitClrStatus

`UnitClrStatus(unit, mask)`

Clears state flags on a unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `mask` | Bits to clear; see UnitGetStatus. |

**Returns:** The unit's new flag word; 0 for an invalid unit.

[Back to index](#function-index)

<a id="call-unitdead"></a>
### UnitDead

`UnitDead(unit)`

Plays the death fade-out of a unit's map model (with its sound) and waits for it.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** 1; 0 for an invalid unit or during an event skip (nothing is played).

**Usage:** Visual only: the unit is hidden but stays in its force. Remove it with UnitEscape or UnitTransferToForce if needed.

[Back to index](#function-index)

<a id="call-unitdelitem"></a>
### UnitDelItem

`UnitDelItem(unit, slot)`

Removes the item in an inventory slot and closes the gap.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `slot` | Inventory slot: 0–3 are the four weapon slots, 4–7 the four item slots. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

[Back to index](#function-index)

<a id="call-unitdispreload"></a>
### UnitDispReload

`UnitDispReload()`

Unloads and reloads the map models of every unit in forces 0–3, then refreshes their positions.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-unitdontmovesally"></a>
### UnitDontMoveSally

`UnitDontMoveSally(unit)`

Locks a unit's starting tile in the preparations: the player cannot swap its position.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** Only applies to units of the player force or the reserve. UnitDontMoveSallyByPID also makes the unit mandatory.

[Back to index](#function-index)

<a id="call-unitdontmovesallybypid"></a>
### UnitDontMoveSallyByPID

`UnitDontMoveSallyByPID(pid)`

Requires a deployed actor, calls BOTH UnitForcedSally and UnitDontMoveSally.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** 0 if unavailable; 1 after both calls.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitescape"></a>
### UnitEscape

`UnitEscape(unit, unused)`

Takes a unit off the map: a carried unit is dropped first; a player unit goes to the reserve marked as escaped; a unit of any other force is deleted.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `unused` | Ignored; the shared helper passes 0. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** The map is refreshed afterwards.

[Back to index](#function-index)

<a id="call-unitescapebypid"></a>
### UnitEscapeByPID

`UnitEscapeByPID(pid)`

Requires a deployed actor, then calls UnitEscape(actor, 0).

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** 0 if unavailable; 1 after the call.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitfadein"></a>
### UnitFadeIn

`UnitFadeIn()`

Makes later scripted movement fade units in (they appear as they move).

**Arguments:** none.

**Returns:** 1.

**Usage:** A scene setting used by Dispos and UnitMove* calls; turn it off with UnitFadeOff.

[Back to index](#function-index)

<a id="call-unitfadeoff"></a>
### UnitFadeOff

`UnitFadeOff()`

Ends UnitFadeIn/UnitFadeOut: later movement shows units normally.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-unitfadeout"></a>
### UnitFadeOut

`UnitFadeOut()`

Makes later scripted movement fade units out (they disappear as they move).

**Arguments:** none.

**Returns:** 1.

**Usage:** Turn it off with UnitFadeOff.

[Back to index](#function-index)

<a id="call-unitfocus"></a>
### UnitFocus

`UnitFocus(unit)`

Moves the map camera smoothly towards a unit's tile.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** 1, even for an invalid unit (which leaves the camera alone).

**Usage:** Does not wait: follow with FocusWait.

[Back to index](#function-index)

<a id="call-unitfocusbypid"></a>
### UnitFocusByPID

`UnitFocusByPID(pid)`

Resolves a deployed actor, reads its tile, then calls Focus.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** 0 if unavailable; 1 after focus call.

**Usage:** Does not copy/restore the previous map camera itself.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitfocusoff"></a>
### UnitFocusOff

`UnitFocusOff()`

Stops the camera from following units during later scripted movement.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-unitfocusoffsetbypid"></a>
### UnitFocusOffsetByPID

`UnitFocusOffsetByPID(pid, offset_x, offset_y)`

Resolves a deployed actor, reads its tile and adds X/Y offsets, then calls Focus.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `offset_x` | Tiles added to actor X. |
| `offset_y` | Tiles added to actor Y. |

**Returns:** 0 if unavailable; 1 after focus call.

**Usage:** Does not copy/restore the previous map camera itself.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitfocuson"></a>
### UnitFocusOn

`UnitFocusOn()`

Makes the camera follow units during later scripted movement (the default).

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-unitforcedsally"></a>
### UnitForcedSally

`UnitForcedSally(unit)`

Makes a unit mandatory in the preparations: the player cannot remove it from the deployment.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** Only applies to units of the player force or the reserve.

[Back to index](#function-index)

<a id="call-unitforcedsallybypid"></a>
### UnitForcedSallyByPID

`UnitForcedSallyByPID(pid)`

Requires a deployed actor and calls UnitForcedSally.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** 0 if unavailable; 1 after the call.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitget"></a>
### UnitGet

`UnitGet(unit, field)`

Reads a selected property of a runtime unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `field` | 1 = next unit handle in force list; 2 = previous handle; 4 = carried/linked unit handle; 5 = force; 6 = level; 7 = experience; 8 = transform gauge (adds 100 while transformed); 9/10 = tile X/Y; 11 = biorhythm phase × 100; 12/13 = maximum/current HP; 14–20 = strength, magic, skill, speed, luck, defense, resistance; 21 = build; 22 = movement; 23 = terrain avoid bonus; 24 = biorhythm battle counter; 35 = AI behavior type; 36/37 = character/class index; 38 = group id (army-name index into GroupData); 39–46 = HP/strength/magic/skill/speed/luck/defense/resistance caps. |

**Returns:** Selected value; 0 for an invalid unit or unsupported selector.

**Usage:** Use the listed selectors. Some additional engine selectors are not suitable for general authoring yet. Coordinates and stats can be signed; missing linked-unit handles are 0.

```fe9s
def example_unitget():
    unit = UnitGetByPID("PID_IKE")
    if unit != 0:
        UnitSet(unit, 13, UnitGet(unit, 12))
```

[Back to index](#function-index)

<a id="call-unitgetbypid"></a>
### UnitGetByPID

`UnitGetByPID(pid)`

Finds the current runtime actor for a character ID.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Exact PID_... character ID string. |

**Returns:** Numeric unit handle, or 0 if absent.

**Usage:** A character can exist in the data without a current actor. Check the result before passing it to other calls.

[Back to index](#function-index)

<a id="call-unitgetbypos"></a>
### UnitGetByPos

`UnitGetByPos(x, y)`

Finds an eligible visible actor occupying a map tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |

**Returns:** Numeric unit handle, or 0 if none is found.

**Usage:** Filters force membership and actor state; this is not a scan of every allocated actor.

[Back to index](#function-index)

<a id="call-unitgetequipacci"></a>
### UnitGetEquipAccI

`UnitGetEquipAccI(unit)`

Gets the active accessory slot in the combined inventory numbering.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |

**Returns:** Accessory slot index 4–7, or -1 when none is active; 0 for an invalid unit.

[Back to index](#function-index)

<a id="call-unitgetequipwepi"></a>
### UnitGetEquipWepI

`UnitGetEquipWepI(unit)`

Gets the active equipped-weapon slot index.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |

**Returns:** Weapon slot index, or -1 when none is active; 0 for an invalid unit.

**Usage:** Validate the unit first because 0 is also a valid slot.

[Back to index](#function-index)

<a id="call-unitgetforce"></a>
### UnitGetForce

`UnitGetForce(unit)`

Returns a unit's force.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** Force ID 0–7; 0 for an invalid unit (indistinguishable from force 0).

[Back to index](#function-index)

<a id="call-unitgethp"></a>
### UnitGetHP

`UnitGetHP(unit)`

Returns a unit's current HP.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** Current HP; 0 for handle 0.

[Back to index](#function-index)

<a id="call-unitgetitemcount"></a>
### UnitGetItemCount

`UnitGetItemCount(unit)`

Counts the items a unit carries, weapons included.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** 0–8; 0 for an invalid unit.

[Back to index](#function-index)

<a id="call-unitgetitemshowing"></a>
### UnitGetItemShowing

`UnitGetItemShowing(unit, item_id)`

Disables skip; if Comeback() is nonzero, starts Fade(2,166) and waits. Calls _gi(unit,item_id), yields once, then enables skip.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `item_id` | IID_... reward item. |

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** No null check. _gi shows the item window and handles a full inventory (convoy/discard choice for player units).

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitgetitemshowingsub"></a>
### UnitGetItemShowingSub

`UnitGetItemShowingSub(unit, item_id)`

Quiets music channel 0, externally calls UnitGetItemShowing(unit,item_id), then restores channel quiet state.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `item_id` | IID_... reward item. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitgetmaxhp"></a>
### UnitGetMaxHP

`UnitGetMaxHP(unit)`

Returns a unit's maximum HP, including the bonus of the equipped weapon and item, capped by the class.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** Maximum HP; 0 for handle 0.

[Back to index](#function-index)

<a id="call-unitgetmovecost"></a>
### UnitGetMoveCost

`UnitGetMoveCost(unit, terrain_index)`

Reads this unit’s movement cost for a terrain-table entry.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `terrain_index` | Index in the movement-cost table for the unit’s class; not a map X or Y coordinate. |

**Returns:** Movement cost; -1 when the terrain cost exceeds 30000 (impassable); 0 for invalid unit.

**Usage:** No terrain-index bounds check; use a valid terrain entry.

[Back to index](#function-index)

<a id="call-unitgetnext"></a>
### UnitGetNext

`UnitGetNext(unit)`

Returns the next unit in the same force.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** Unit handle; 0 at the end of the force or for a null unit.

**Usage:** Moving units between forces while walking a force changes the order.

[Back to index](#function-index)

<a id="call-unitgetrace"></a>
### UnitGetRace

`UnitGetRace(unit)`

Reports the unit’s beorc/laguz transformation category.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |

**Returns:** 0 for beorc or an invalid unit; 1 for untransformed laguz; 2 for transformed laguz.

[Back to index](#function-index)

<a id="call-unitgetstatus"></a>
### UnitGetStatus

`UnitGetStatus(unit)`

Returns a unit's state flags.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** Bit flags: 0x1 has acted this turn; 0x2 carrying a unit; 0x4 carried; 0x8 dead/inactive; 0x10 in the reserve; 0x20 off screen; 0x40 hidden by fog; 0x80 under a roof; 0x100 group commander; 0x4000 escaped; 0x8000 died this chapter; 0x10000 mandatory in preparations; 0x20000 position locked in preparations; 0x100000 cannot Give or Drop a carried unit; 0x200000 cannot be picked for the second team; 0x400000 picked for the second team. 0 for an invalid unit.

[Back to index](#function-index)

<a id="call-unitgetweaponcount"></a>
### UnitGetWeaponCount

`UnitGetWeaponCount(unit)`

Counts the weapons a unit carries (its four weapon slots).

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** 0–4; 0 for an invalid unit.

[Back to index](#function-index)

<a id="call-unitgetx"></a>
### UnitGetX

`UnitGetX(unit)`

Returns a unit's tile X.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** Tile X; 0 for handle 0.

**Usage:** Does not check that the slot holds a character.

[Back to index](#function-index)

<a id="call-unitgetxbypid"></a>
### UnitGetXByPID

`UnitGetXByPID(pid)`

Resolves a deployed actor and reads UnitGetX.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** Map X coordinate, or -1 if unavailable.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitgety"></a>
### UnitGetY

`UnitGetY(unit)`

Returns a unit's tile Y.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** Tile Y; 0 for handle 0.

**Usage:** Does not check that the slot holds a character.

[Back to index](#function-index)

<a id="call-unitgetybypid"></a>
### UnitGetYByPID

`UnitGetYByPID(pid)`

Resolves a deployed actor and reads UnitGetY.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** Map Y coordinate, or -1 if unavailable.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unititemgetvaluation"></a>
### UnitItemGetValuation

`UnitItemGetValuation(unit, slot)`

Returns a value score for an inventory item, used to pick which item to send away.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `slot` | Inventory slot: 0–3 are the four weapon slots, 4–7 the four item slots. |

**Returns:** Item price multiplied by its remaining uses, plus fixed bonuses for special items (character- or class-locked weapons add 50,000); 0 for an empty slot or invalid unit.

**Usage:** Only meaningful for comparing items, as UnitItemSendToHouseByPID does.

[Back to index](#function-index)

<a id="call-unititemsendtohousebypid"></a>
### UnitItemSendToHouseByPID

`UnitItemSendToHouseByPID(pid)`

Requires an existing actor with exactly four weapons. Compares valuations for indices 0–3, then sends one entry to storage.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** -1 if missing or weapon count is not 4; otherwise 0.

**Usage:** Do not simplify this to 'always sends the cheapest': the index-2 branch checks v4 <= v2, v4 <= v3, but v3 <= v5 (not v4 <= v5). Tie order prefers earlier branches. Preserve the actual logic.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unititemsendtowarehouse"></a>
### UnitItemSendtoWarehouse

`UnitItemSendtoWarehouse(unit, slot)`

Sends one inventory item to the convoy.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `slot` | Inventory slot: 0–3 are the four weapon slots, 4–7 the four item slots. |

**Returns:** 1 if sent; 0 for an invalid unit, an empty slot, or before the convoy is available (internal chapter numbers 1–8, Prologue to Chapter 7).

**Usage:** If the convoy is full, its least valuable item is deleted to make room.

[Back to index](#function-index)

<a id="call-unititemsendtowarehouseall"></a>
### UnitItemSendtoWarehouseAll

`UnitItemSendtoWarehouseAll(unit)`

Transfers all eight of a unit’s inventory slots to storage, clears the original slots, and compacts the inventory.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |

**Returns:** 1 for a valid unit; 0 if the handle is zero or its slot has no character.

**Usage:** The two function names are aliases. The original slot is cleared after each transfer attempt; make sure storage has enough capacity before using this on valuable items.

[Back to index](#function-index)

<a id="call-unititemsetdrop"></a>
### UnitItemSetDrop

`UnitItemSetDrop(unit, slot)`

Marks one inventory item as dropped when the unit is defeated.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `slot` | Inventory slot: 0–3 are the four weapon slots, 4–7 the four item slots. |

**Returns:** 1 if marked; 0 if the unit already has a dropped item, the slot is empty or the unit is invalid.

**Usage:** Only one item per unit can be marked.

[Back to index](#function-index)

<a id="call-unitmovedir"></a>
### UnitMoveDir

`UnitMoveDir(unit, path)`

Walks a unit along a list of steps, ignoring terrain and other units.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `path` | One character per step: 2 down, 4 left, 6 right, 8 up. The letters L, R, U and D make the unit face left, right, up or down at the end. Example: "6662L". |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** Does not wait: use UnitMoveWait. The unit's tile changes to the end of the path at once. While the event is being skipped it appears there directly.

[Back to index](#function-index)

<a id="call-unitmovedirbypid"></a>
### UnitMoveDirByPID

`UnitMoveDirByPID(pid, path)`

Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitMoveDir with the remaining arguments.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `path` | Native direction-command string. |

**Returns:** Actor reference if scheduled; 0 if unavailable.

**Usage:** Does not wait: use UnitMoveWait.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitmovepos"></a>
### UnitMovePos

`UnitMovePos(unit, x, y)`

Walks a unit to a tile along a real path. If the tile is taken, the nearest free tile the unit can reach is used.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** Does not wait: use UnitMoveWait. If no tile is reachable, the unit does not move. While the event is being skipped the unit appears there at once. Speed, fading and camera follow come from the UnitWalkSlow/UnitFade*/UnitFocus* settings.

[Back to index](#function-index)

<a id="call-unitmoveposbypid"></a>
### UnitMovePosByPID

`UnitMovePosByPID(pid, x, y)`

Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitMovePos with the remaining arguments.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Actor reference if scheduled; 0 if unavailable.

**Usage:** Does not wait: use UnitMoveWait.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitmovetounit"></a>
### UnitMoveToUnit

`UnitMoveToUnit(destination_unit, moving_unit)`

Requires both actors to be deployed. Reads the FIRST actor's X/Y and moves the SECOND actor toward that tile.

| Argument | Meaning and restrictions |
|---|---|
| `destination_unit` | Actor whose tile is the destination. |
| `moving_unit` | Actor to move; argument order is significant. |

**Returns:** 0 for absent/nondeployed actor; 1 after calling UnitMovePos.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitmovetounitbypid"></a>
### UnitMoveToUnitByPID

`UnitMoveToUnitByPID(destination_pid, moving_pid)`

Resolves both PIDs and calls UnitMoveToUnit(destination, mover). Discards that helper's result.

| Argument | Meaning and restrictions |
|---|---|
| `destination_pid` | PID whose tile is the destination. |
| `moving_pid` | PID to move. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitmovewait"></a>
### UnitMoveWait

`UnitMoveWait()`

Waits until every unit movement, turn and death/warp animation started by the event has finished.

**Arguments:** none.

**Returns:** 1.

**Usage:** Returns immediately if nothing is moving. UnitMovePos, UnitMoveDir, UnitRotate, Dispos and the other staging calls do not wait by themselves.

[Back to index](#function-index)

<a id="call-unitpairup"></a>
### UnitPairup

`UnitPairup(carrier, carried)`

Links two actors using the game’s carrying/pairing operation, first moving the second actor to the tile right of the first.

| Argument | Meaning and restrictions |
|---|---|
| `carrier` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `carried` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |

**Returns:** 1 for two valid actors; 0 otherwise.

**Usage:** Changes positions and refreshes movement ranges. This is the FE9 carry relationship, not a later game’s Pair Up combat system.

[Back to index](#function-index)

<a id="call-unitputtowarehouse"></a>
### UnitPutToWarehouse

`UnitPutToWarehouse(unit)`

Transfers all eight of a unit’s inventory slots to storage, clears the original slots, and compacts the inventory.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |

**Returns:** 1 for a valid unit; 0 if the handle is zero or its slot has no character.

**Usage:** The two function names are aliases. The original slot is cleared after each transfer attempt; make sure storage has enough capacity before using this on valuable items.

[Back to index](#function-index)

<a id="call-unitqueryequip"></a>
### UnitQueryEquip

`UnitQueryEquip(unit, slot)`

Tests the equipped bit of an inventory slot.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `slot` | Inventory index: 0–3 weapon slots, 4–7 item/accessory slots. Never pass an index outside 0–7. |

**Returns:** 1 if the slot’s equipped bit is set; 0 otherwise or for an invalid unit.

[Back to index](#function-index)

<a id="call-unitqueryjid"></a>
### UnitQueryJID

`UnitQueryJID(unit, jid)`

Tests whether a unit has a given class.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `jid` | Exact JID_... class ID. |

**Returns:** 1 if it is that exact class; 0 otherwise or for handle 0.

**Usage:** The match is exact: a promoted or female variant is a different JID.

[Back to index](#function-index)

<a id="call-unitqueryjidbypid"></a>
### UnitQueryJIDByPID

`UnitQueryJIDByPID(pid, class_id)`

Looks up the actor; if present, returns UnitQueryJID(actor, class_id).

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `class_id` | JID_... class ID. |

**Returns:** 0 for missing actor, otherwise the native class-test result.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitquerypid"></a>
### UnitQueryPID

`UnitQueryPID(unit, pid)`

Tests whether a unit is a given character.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `pid` | Exact PID_... character ID string. |

**Returns:** 1 if it is; 0 otherwise or for handle 0.

[Back to index](#function-index)

<a id="call-unitreplaceitem"></a>
### UnitReplaceItem

`UnitReplaceItem(unit, slot, iid)`

Replaces the selected inventory slot using an item ID.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `slot` | Inventory index: 0–3 weapon slots, 4–7 item/accessory slots. Never pass an index outside 0–7. |
| `iid` | Existing IID_... item definition. |

**Returns:** 1 for a valid unit; 0 if the handle is zero or its slot has no character.

**Usage:** Provide a valid slot and item ID; this is not an “add to first empty slot” operation.

[Back to index](#function-index)

<a id="call-unitrotate"></a>
### UnitRotate

`UnitRotate(unit, direction, duration_ms)`

Turns a unit to face a direction.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `direction` | 1 left, 2 right, 4 down, 8 up; add two for a diagonal (5 down-left, 6 down-right, 9 up-left, 10 up-right). |
| `duration_ms` | Turning time in milliseconds; 0 turns at once. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** Does not wait: use UnitMoveWait. While the event is being skipped the unit turns at once.

[Back to index](#function-index)

<a id="call-unitrotatebypid"></a>
### UnitRotateByPID

`UnitRotateByPID(pid, direction, duration_ms)`

Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitRotate with the remaining arguments.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `direction` | Facing: 1 left (−X), 2 right (+X), 4 down (+Y), 8 up (−Y); add two for a diagonal (5, 6, 9, 10). |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** Actor reference if scheduled; 0 if unavailable.

**Usage:** Does not wait: use UnitMoveWait.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitrotatetopos"></a>
### UnitRotateToPos

`UnitRotateToPos(unit, x, y, duration_ms)`

Requires a deployed actor, compares its tile to the target tile and chooses an eight-direction facing using the original axis/diagonal threshold branches, then calls UnitRotate.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** No success return is emitted: success also returns 0. This is discrete facing selection, not an exact continuous-angle look-at.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitrotatetoposbypid"></a>
### UnitRotateToPosByPID

`UnitRotateToPosByPID(pid, x, y, duration_ms)`

Resolves a deployed actor and forwards to UnitRotateToPos.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** 0, including on successful scheduling.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitrotatetounit"></a>
### UnitRotateToUnit

`UnitRotateToUnit(rotating_unit, target_unit, duration_ms)`

Requires both actors deployed, reads the target actor's tile and rotates the first actor toward it using UnitRotateToPos.

| Argument | Meaning and restrictions |
|---|---|
| `rotating_unit` | Actor whose facing changes. |
| `target_unit` | Actor whose tile supplies the target. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** 0, including on successful scheduling.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitrotatetounitbypid"></a>
### UnitRotateToUnitByPID

`UnitRotateToUnitByPID(rotating_pid, target_pid, duration_ms)`

Resolves both deployed actors and forwards to UnitRotateToUnit.

| Argument | Meaning and restrictions |
|---|---|
| `rotating_pid` | PID whose facing changes. |
| `target_pid` | PID to face. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** 0, including on successful scheduling.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitsearchitem"></a>
### UnitSearchItem

`UnitSearchItem(unit, item_id)`

Finds an item in a unit's inventory.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `item_id` | IID_... item ID. |

**Returns:** Slot 0–7 of the first copy; -1 if the unit does not carry it; 0 for an invalid unit.

**Usage:** 0 is also a valid slot, so check the unit first.

[Back to index](#function-index)

<a id="call-unitset"></a>
### UnitSet

`UnitSet(unit, field, value)`

Writes one of the supported mutable unit fields.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `field` | 6 = level; 7 = experience; 8 = raw transformation gauge; 13 = current HP; 24 = biorhythm battle counter; 38 = group id (army-name index into GroupData; 0 leaves it unchanged). Other selectors do not write a field. |
| `value` | New value. Level/gauge use a byte; counter uses 16 bits. HP is clamped by the unit HP setter. |

**Returns:** Supplied value for a valid unit, even for an unsupported selector; 0 for invalid unit or selector 0.

**Usage:** This is not a general stat editor: use dedicated stat calls for strength, magic, etc. UnitGet supports more fields than UnitSet.

[Back to index](#function-index)

<a id="call-unitsetaccaway"></a>
### UnitSetAccAway

`UnitSetAccAway(unit)`

Unequips the unit's equipped item (band or ring).

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** The item slot 4–7 that was equipped; -1 if none was; 0 for an invalid unit.

[Back to index](#function-index)

<a id="call-unitsetcpattackseq"></a>
### UnitSetCpAttackSeq

`UnitSetCpAttackSeq(unit, sequence)`

Changes the attack AI script of a unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `sequence` | SEQ_... AI script name from the AI data. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** The script restarts from its first step. An unknown name leaves the old script in place.

[Back to index](#function-index)

<a id="call-unitsetcphealseq"></a>
### UnitSetCpHealSeq

`UnitSetCpHealSeq(unit, record)`

Changes the healing AI record of a unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `record` | Name of a healing record in the AI data. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** An unknown name leaves the old setting in place.

[Back to index](#function-index)

<a id="call-unitsetcpmtypeid"></a>
### UnitSetCpMTypeID

`UnitSetCpMTypeID(unit, table)`

Changes the MTYPE AI table of a unit (how it values targets).

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `table` | MTYPE_... table name from the AI data. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** An unknown name leaves the old table in place.

[Back to index](#function-index)

<a id="call-unitsetcpmoveseq"></a>
### UnitSetCpMoveSeq

`UnitSetCpMoveSeq(unit, sequence)`

Changes the movement AI script of a unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `sequence` | SEQ_... AI script name from the AI data. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** The script restarts from its first step. An unknown name leaves the old script in place.

[Back to index](#function-index)

<a id="call-unitsetcptypebypid"></a>
### UnitSetCpTypeByPID

`UnitSetCpTypeByPID(pid, attack_sequence, move_sequence)`

Resolves a deployed actor, then sets its attack sequence followed by its movement sequence.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `attack_sequence` | SEQ_... passed to UnitSetCpAttackSeq. |
| `move_sequence` | SEQ_... passed to UnitSetCpMoveSeq. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitsetexp"></a>
### UnitSetEXP

`UnitSetEXP(unit, exp)`

Sets a unit's experience.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `exp` | 0–100, or 255 for 'cannot gain experience'. Other values are ignored. |

**Returns:** 0.

**Usage:** No level-up happens, even at 100.

[Back to index](#function-index)

<a id="call-unitsetequip"></a>
### UnitSetEquip

`UnitSetEquip(unit, slot)`

Equips an inventory item.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `slot` | 0–3 equips that weapon; -1 equips the first weapon the unit can use; 4–7 equips that item if it is equippable (bands, rings). |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** The other slots of the same half are unequipped first, so a slot the unit cannot use leaves it with nothing equipped there. Laguz units are not changed. Equipping a weapon updates the weapon held by the map model.

[Back to index](#function-index)

<a id="call-unitsetfixed"></a>
### UnitSetFixed

`UnitSetFixed(unit, enabled)`

Sets or clears the unit’s fixed-state flag.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1 for a valid unit; 0 if the handle is zero or its slot has no character.

[Back to index](#function-index)

<a id="call-unitsethp"></a>
### UnitSetHP

`UnitSetHP(unit, hp)`

Sets a unit's current HP.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `hp` | New HP; kept between 0 and the unit's maximum HP. |

**Returns:** 0.

**Usage:** Setting 0 does not kill the unit or start a death event.

[Back to index](#function-index)

<a id="call-unitsethold"></a>
### UnitSetHold

`UnitSetHold(enabled)`

Changes the shared scene unit-hold setting.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1.

**Usage:** Applies to scene state, not one unit. Restore 0 when the hold sequence ends.

[Back to index](#function-index)

<a id="call-unitsetpos"></a>
### UnitSetPos

`UnitSetPos(unit, x, y)`

Places a unit on a tile at once. If the tile is taken, the nearest free tile is used.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** Unlike UnitMovePos, the unit's movement range is not considered.

[Back to index](#function-index)

<a id="call-unitsetposdir"></a>
### UnitSetPosDir

`UnitSetPosDir(unit, x, y, direction)`

For a non-null actor, sets its tile then immediately rotates it unless direction is -1.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |
| `direction` | Engine facing code; -1 preserves facing. Other values are passed to UnitRotate with duration 0. |

**Returns:** 0 for null; 1 after applying the calls.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitsetposdirbypid"></a>
### UnitSetPosDirByPID

`UnitSetPosDirByPID(pid, x, y, direction)`

Resolves a deployed actor, sets its tile, and immediately rotates unless direction is -1.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |
| `direction` | Facing code; -1 leaves facing unchanged. |

**Returns:** Actor reference on success; 0 if unavailable.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitsetposdirbypos"></a>
### UnitSetPosDirByPos

`UnitSetPosDirByPos(source_x, source_y, destination_x, destination_y, direction)`

Finds the actor at the source tile, moves it to the destination, and immediately rotates unless direction is -1.

| Argument | Meaning and restrictions |
|---|---|
| `source_x` | Source map X. |
| `source_y` | Source map Y. |
| `destination_x` | Destination map X. |
| `destination_y` | Destination map Y. |
| `direction` | Facing code; -1 preserves facing. |

**Returns:** Actor reference on success; 0 if the source tile has no actor.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitsetstatus"></a>
### UnitSetStatus

`UnitSetStatus(unit, mask)`

Sets state flags on a unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `mask` | Bits to set; see UnitGetStatus. |

**Returns:** The unit's new flag word; 0 for an invalid unit.

**Usage:** Vanilla scripts set 0x100000, 0x200000, 0x400000 and 0x1. Setting bookkeeping bits such as 0x2, 0x4 or 0x8 by hand desynchronises the unit.

[Back to index](#function-index)

<a id="call-unitsetweaponaway"></a>
### UnitSetWeaponAway

`UnitSetWeaponAway(unit)`

Unequips the unit's weapon.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** The weapon slot 0–3 that was equipped; -1 if none was equipped or the unit is a laguz; 0 for an invalid unit.

**Usage:** The map model is updated to hold no weapon.

[Back to index](#function-index)

<a id="call-unitsetweaponawaybypid"></a>
### UnitSetWeaponAwayByPID

`UnitSetWeaponAwayByPID(pid)`

Resolves a deployed actor and returns UnitSetWeaponAway(actor).

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** -2 if the character has no unit; otherwise UnitSetWeaponAway's result (the slot that was equipped, or -1).

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unittackle"></a>
### UnitTackle

`UnitTackle(acting_unit, target_unit, distance)`

Moves the target away from the acting unit and starts shove/smite motion.

| Argument | Meaning and restrictions |
|---|---|
| `acting_unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `target_unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `distance` | Positive displacement in tiles; normally 1 for shove, 2 for smite. Use aligned adjacent units. |

**Returns:** 1 if motion is started; 0 for invalid units or the skip path. The skip path still moves the target immediately.

**Usage:** Does not itself validate that the destination is legal. Use the scene’s unit-motion wait before dependent actions.

[Back to index](#function-index)

<a id="call-unittransfertoforce"></a>
### UnitTransferToForce

`UnitTransferToForce(unit, force)`

Moves a unit to another force, for example to recruit it (force 0) or turn it into an ally (2).

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `force` | Force ID: 0 player, 1 enemy, 2 allied (orderable), 3 other (green), 4 free pool, 5 player reserve, 6 dead/inactive, 7 special inactive. |

**Returns:** 1 for a valid unit; 0 if the handle is 0 or the slot holds no character.

**Usage:** The unit takes the army group of the destination force's first group commander, if there is one. Moving to the player, allied or other force clears its item-drop marks. Its map model is reloaded in the new army colour.

[Back to index](#function-index)

<a id="call-unittransfertoforcebypid"></a>
### UnitTransferToForceByPID

`UnitTransferToForceByPID(pid, force)`

Resolves the actor, applies the UnitCheckLiveByPID-equivalent null/status-0x08/force-6 test, then calls UnitTransferToForce.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `force` | Runtime force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 player reserve, 6 inactive/death-flagged, 7 special inactive. Not a phase number. |

**Returns:** 0 if missing/not live under that test; 1 after transfer.

**Usage:** Unlike the movement helpers, it does not require the unit to be in forces 0–3: a living reserve unit passes.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unittransform"></a>
### UnitTransform

`UnitTransform(unit, transformed)`

Changes a unit to the requested transformed/untransformed state with its transformation animation.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `transformed` | 0 requests untransformed; nonzero requests transformed. This is a desired state, not a toggle. |

**Returns:** 1 if an animation is scheduled; 0 for invalid unit or already matching state; the skip path applies the change immediately but returns 0.

**Usage:** Use only on a compatible laguz unit. Synchronize with the scene’s unit-motion wait.

[Back to index](#function-index)

<a id="call-unittstskill"></a>
### UnitTstSkill

`UnitTstSkill(unit, skill_id)`

Tests whether a unit holds a skill.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `skill_id` | SID_... skill ID. |

**Returns:** 1 if the unit holds it; 0 otherwise or for an invalid unit.

[Back to index](#function-index)

<a id="call-unitwalkdir"></a>
### UnitWalkDir

`UnitWalkDir(direction)`

Sets the direction bits used by subsequent scene walking.

| Argument | Meaning and restrictions |
|---|---|
| `direction` | Low four direction bits: 1 negative X, 2 positive X, 4 positive Y, 8 negative Y. Other bits are discarded. |

**Returns:** 1.

**Usage:** Shared movement setting, not the direction of a unit passed to this call.

[Back to index](#function-index)

<a id="call-unitwalkslow"></a>
### UnitWalkSlow

`UnitWalkSlow(enabled)`

Enables or disables slow walking for subsequent scene movement.

| Argument | Meaning and restrictions |
|---|---|
| `enabled` | 0 disables; nonzero enables. |

**Returns:** 1.

**Usage:** This is shared scene state. Restore 0 when the slow-walk sequence ends.

[Back to index](#function-index)

<a id="call-unitwarpout"></a>
### UnitWarpOut

`UnitWarpOut(unit)`

Plays the Warp effect on a unit and waits for it.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |

**Returns:** 1; 0 for an invalid unit or during an event skip (nothing is played).

**Usage:** Visual only: the unit's force and tile do not change. Remove or move it separately.

[Back to index](#function-index)

<a id="call-unitsinitialize"></a>
### UnitsInitialize

`UnitsInitialize()`

Removes every unit: all forces are emptied and all unit slots freed.

**Arguments:** none.

**Returns:** 1.

**Usage:** Also frees the unit models and clears the battle state. Not a chapter reset: flags, money and map state are kept.

[Back to index](#function-index)

<a id="call-unitspop"></a>
### UnitsPop

`UnitsPop()`

Restores the units saved by UnitsPush, refreshes the map and reloads the unit models. Frees the buffer.

**Arguments:** none.

**Returns:** 1.

**Usage:** Units created since the push are discarded.

[Back to index](#function-index)

<a id="call-unitspopwithoutmap"></a>
### UnitsPopWithoutMap

`UnitsPopWithoutMap()`

Same as UnitsPop, without the map refresh.

**Arguments:** none.

**Returns:** 1.

**Usage:** Call MapUpdate afterwards.

[Back to index](#function-index)

<a id="call-unitspush"></a>
### UnitsPush

`UnitsPush()`

Saves every unit (and the forge records) into a temporary buffer, then empties the forces.

**Arguments:** none.

**Returns:** 1.

**Usage:** One buffer is shared by UnitsPush, UnitsPush_Uninitialize and AllPush; a second push before the matching pop loses the first.

[Back to index](#function-index)

<a id="call-unitspush-uninitialize"></a>
### UnitsPush_Uninitialize

`UnitsPush_Uninitialize()`

Saves every unit (and the forge records) into the temporary buffer, leaving the units in place.

**Arguments:** none.

**Returns:** 1.

**Usage:** Same shared buffer as UnitsPush.

[Back to index](#function-index)

<a id="call-visitin"></a>
### VisitIn

`VisitIn(unit, x, y)`

Does nothing (kept for the visit-event scripts).

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1.

**Usage:** Its arguments are ignored. Vanilla visit events call it with MindGetMe(), EventGetX() and EventGetY().

[Back to index](#function-index)

<a id="call-visitout"></a>
### VisitOut

`VisitOut(unit, x, y)`

Closes the village at a tile after a visit: plays its closing animation, waits for it and marks the village as visited.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Ignored; vanilla passes the visiting unit. |
| `x` | Map tile X, including the map border. |
| `y` | Map tile Y, including the map border. |

**Returns:** 1 after the animation; 0 if no village is found, or during an event skip (the village closes at once).

**Usage:** The tile may be the village itself or a tile next to it. The change is recorded in the map state, so it is kept in saves.

[Back to index](#function-index)

<a id="call-waitf"></a>
### WaitF

`WaitF(frames)`

Pauses the script for a number of frames (60 per second).

| Argument | Meaning and restrictions |
|---|---|
| `frames` | Frame count. 1 or less waits until the next frame. |

**Returns:** 1; 0 while the event is being skipped.

**Usage:** While the event is being skipped it does not wait.

[Back to index](#function-index)

<a id="call-waitm"></a>
### WaitM

`WaitM(duration_ms)`

Pauses the script for a time in milliseconds.

| Argument | Meaning and restrictions |
|---|---|
| `duration_ms` | Milliseconds; converted to frames by dividing by 16.67 and rounding down. Under 34 ms waits a single frame. |

**Returns:** 1; 0 while the event is being skipped.

**Usage:** While the event is being skipped it does not wait.

[Back to index](#function-index)

<a id="call-waitpressanykey"></a>
### WaitPressAnyKey

`WaitPressAnyKey()`

Suspends the calling script until the input-wait process completes after a key press.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-warrecord"></a>
### WarRecord

`WarRecord(duration_ms)`

Starts the war-record display and suspends the calling script.

| Argument | Meaning and restrictions |
|---|---|
| `duration_ms` | Duration in milliseconds. Conversion to 60 Hz frames truncates fractional frames. |

**Returns:** 1.

**Usage:** Intended for ending sequences with the corresponding display resources loaded.

[Back to index](#function-index)

<a id="call-wipeend"></a>
### WipeEnd

`WipeEnd()`

Resets the screen-wipe state to idle.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-wipein"></a>
### WipeIn

`WipeIn(duration_ms)`

Starts a screen wipe in.

| Argument | Meaning and restrictions |
|---|---|
| `duration_ms` | Duration in milliseconds; a negative value uses 2000 ms. |

**Returns:** 1.

**Usage:** Use WipeWait before work that requires the transition to finish.

[Back to index](#function-index)

<a id="call-wipeout"></a>
### WipeOut

`WipeOut(duration_ms)`

Starts a screen wipe out.

| Argument | Meaning and restrictions |
|---|---|
| `duration_ms` | Duration in milliseconds; a negative value uses 2000 ms. |

**Returns:** 1.

**Usage:** Use WipeWait before work that requires the transition to finish.

[Back to index](#function-index)

<a id="call-wipewait"></a>
### WipeWait

`WipeWait()`

Suspends the script while a wipe-in or wipe-out transition is active.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call--bmsini"></a>
### _bmsini

`_bmsini()`

Resets the chapter for a tutorial: chapter number 0 (so the convoy is available), turn 1, the player controls force 0 and the computer forces 1–3, 1,000 gold, chapter flags and gf_complete/gf_gameover cleared, no units, empty convoy, no forge records, map state cleared.

**Arguments:** none.

**Returns:** 1.

**Usage:** Called by TutorialInit after _seqini.

[Back to index](#function-index)

<a id="call--cmb-mess-load"></a>
### _cmb_mess_load

`_cmb_mess_load(script_path, message_path)`

Loads a script file and a message file together (the step behind TutEntryCommon).

| Argument | Meaning and restrictions |
|---|---|
| `script_path` | Path of the .cmb file, such as scripts/c80.cmb. |
| `message_path` | Path of the message file; the helper passes mess/tut.m. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call--gi"></a>
### _gi

`_gi(unit, item_id)`

Gives an item to a unit and shows the result window (the step behind UnitGetItemShowing).

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit. |
| `item_id` | IID_... item ID. |

**Returns:** 1; 0 for an invalid unit.

**Usage:** A player unit shows 'got item'; an enemy unit shows 'item taken' and the item is marked as its drop. When a player or reserve unit's inventory is full, the game opens the window to send an item to the convoy or discard one. The script waits for the window.

[Back to index](#function-index)

<a id="call--intr"></a>
### _intr

`_intr()`

Runs the chapter-checkpoint save sequence and suspends the calling script until it finishes.

**Arguments:** none.

**Returns:** 1 when scheduled; read MCResult for the card-operation status.

**Usage:** Opens the memory card, writes the chapter checkpoint if opening succeeded, then closes it. Use only at a valid chapter save point; this is not a harmless pause.

[Back to index](#function-index)

<a id="call--mf1"></a>
### _mf1

`_mf1()`

First step of MapFree: releases the map's objects if a map is loaded.

**Arguments:** none.

**Returns:** 1 if a map was loaded; 0 otherwise.

[Back to index](#function-index)

<a id="call--mf2"></a>
### _mf2

`_mf2()`

Second step of MapFree: frees the current map.

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call--pa"></a>
### _pa

`_pa(command)`

Plays a scripted controller input (the 'pad actor' that moves the cursor and presses buttons in tutorials). Each character is one step: a one-frame press, then a pause until the next step.

| Argument | Meaning and restrictions |
|---|---|
| `command` | Step characters: 1–4 and 6–9 press the control stick and D-pad in the numeric-keypad direction (8 up, 2 down, 4 left, 6 right, 7/9/1/3 diagonals); A, B, X, Y, Z, L, R press that button; S presses Start; any other character (such as 5 or a space) presses nothing. < halves and > doubles the step length (16 frames at first) without using a step. |

**Returns:** 1.

**Usage:** The player's real input is ignored while it plays. TutPadActor calls this and waits while E_PadActor runs. Example: "66A" moves right twice, then presses A, one step (16 frames) apart.

[Back to index](#function-index)

<a id="call--pldone"></a>
### _pldone

`_pldone()`

Tests whether files queued for loading (RectPreLoad, PreLoad) are ready.

**Arguments:** none.

**Returns:** 1 when nothing is still loading; 0 otherwise.

**Usage:** PreLoadWait loops on this.

[Back to index](#function-index)

<a id="call--seqini"></a>
### _seqini

`_seqini()`

Clears the map for a tutorial: removes conversations, images, scripted input, the preparations, AI phase and phase banner, the notice frame and the unit models.

**Arguments:** none.

**Returns:** 1.

**Usage:** First step of TutorialInit.

[Back to index](#function-index)

<a id="call--tr"></a>
### _tr

`_tr()`

Continues a held tutorial conversation (the step behind TutTalkResume).

**Arguments:** none.

**Returns:** 1.

**Usage:** Unlike TalkResume it does not pause the script: the helper waits with TalkExist.

[Back to index](#function-index)

<a id="call--tt"></a>
### _tt

`_tt(message_id)`

Starts a tutorial conversation with a message (the step behind TutTalkEvent).

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a loaded message file, not literal text. |

**Returns:** 1.

**Usage:** Unlike TalkEvent it does not pause the script: the helper waits with TalkExist.

[Back to index](#function-index)

<a id="call-clr"></a>
### clr

`clr(flag_name)`

Clears a flag.

| Argument | Meaning and restrictions |
|---|---|
| `flag_name` | Registered flag name. |

**Returns:** 0.

**Usage:** An unregistered name does nothing.

[Back to index](#function-index)

<a id="call-dump"></a>
### dump

`dump()`

Prints all eight force lists and their units to debug output.

**Arguments:** none.

**Returns:** No useful script result; call for its side effect.

**Usage:** Useful for checking unit membership; no gameplay changes.

[Back to index](#function-index)

<a id="call-get"></a>
### get

`get(flag_name)`

Reads a flag.

| Argument | Meaning and restrictions |
|---|---|
| `flag_name` | Registered flag name. |

**Returns:** 1 if set; 0 if clear or not registered.

[Back to index](#function-index)

<a id="call-global"></a>
### global

`global(flag_name)`

Registers a campaign flag in the lowest free slot of the flag table and clears its bit. The game registers its campaign flags once at boot.

| Argument | Meaning and restrictions |
|---|---|
| `flag_name` | Flag name; any string. |

**Returns:** 1.

**Usage:** global is a .fe9s keyword: call it as extern("global", "name"). Keep the registration order for save compatibility.

[Back to index](#function-index)

<a id="call-intplgetvalue"></a>
### intplGetValue

`intplGetValue(curve, start, end, progress, total)`

Computes one interpolated value without starting an animation.

| Argument | Meaning and restrictions |
|---|---|
| `curve` | 0 linear; 1 quadratic ease-in; 2 cubic ease-in; 3 quartic ease-in; 4 quadratic ease-out; 5 cubic ease-out; 6 quartic ease-out; 7–9 oscillating/bouncing curves; 10 cosine ease-in/out; 11 sine ease-out; 12 cosine ease-in. |
| `start` | Value at progress 0. |
| `end` | Value at progress total. |
| `progress` | Current progress; use the same units as total, normally within 0–total. |
| `total` | Total progress span. Zero returns end. |

**Returns:** Interpolated value truncated to an integer; unsupported curve gives 0 when total is nonzero.

**Usage:** Does not clamp progress. Oscillating modes 8–9 also depend on the absolute time scale.

```fe9s
def example_intplgetvalue():
    halfway = intplGetValue(0, 0, 100, 50, 100)
    # halfway is 50
```

[Back to index](#function-index)

<a id="call-isfading"></a>
### isFading

`isFading()`

Tests whether a screen fade started by Fade is still running.

**Arguments:** none.

**Returns:** 1 while fading; 0 otherwise.

**Usage:** FadeWait loops on this.

[Back to index](#function-index)

<a id="call-isflash"></a>
### isFlash

`isFlash()`

Tests whether the screen flash is in either transition phase.

**Arguments:** none.

**Returns:** 1 while transitioning; 0 otherwise.

[Back to index](#function-index)

<a id="call-iswipe"></a>
### isWipe

`isWipe()`

Tests whether a wipe-in or wipe-out transition is active.

**Arguments:** none.

**Returns:** 1 while transitioning; 0 otherwise.

[Back to index](#function-index)

<a id="call-regist"></a>
### regist

`regist(flag_name)`

Registers a chapter flag in the highest free slot of the 96-slot flag table. The slot's bit is left as it is (chapter start clears these slots).

| Argument | Meaning and restrictions |
|---|---|
| `flag_name` | Flag name; any string. |

**Returns:** 1.

**Usage:** Saves store flag bits by slot, not by name, so keep the registration order when editing a chapter's Startup.

[Back to index](#function-index)

<a id="call-report"></a>
### report

`report(text)`

Writes text to the game’s debug-report output.

| Argument | Meaning and restrictions |
|---|---|
| `text` | Plain diagnostic string. Avoid printf format placeholders because no additional formatting arguments can be supplied. |

**Returns:** 1 for an accepted string; 0 otherwise.

**Usage:** Does not show an in-game dialogue box.

[Back to index](#function-index)

<a id="call-set"></a>
### set

`set(flag_name)`

Sets a flag.

| Argument | Meaning and restrictions |
|---|---|
| `flag_name` | Registered flag name. |

**Returns:** 0.

**Usage:** An unregistered name does nothing.

[Back to index](#function-index)

<a id="call-taikitk"></a>
### taikitk

`taikitk()`

Starts a waiting token that lasts until a unit's next Wait command (E_TaikiToken).

**Arguments:** none.

**Returns:** 1.

**Usage:** The tutorial helpers TutWaitForNextTaiki, TutWaitForNextTurn and TutWaitForNextTurnAfter call it and wait while the token exists.

[Back to index](#function-index)

<a id="call-td"></a>
### td

`td(message_id)`

Opens a tutorial dialog with a message and pauses the script until it closes.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a loaded message file, not literal text. |

**Returns:** 0.

**Usage:** A message with a line break uses the two-line layout. TutorialDialog calls this, yields once, then calls tde.

[Back to index](#function-index)

<a id="call-tde"></a>
### tde

`tde()`

Sets the 'event suspended' state flag again after a tutorial dialog cleared it (the last step of TutorialDialog).

**Arguments:** none.

**Returns:** 1.

[Back to index](#function-index)

<a id="call-turnatk"></a>
### turnatk

`turnatk()`

Starts a waiting token that lasts until the next end of turn (E_TurnAToken).

**Arguments:** none.

**Returns:** 1.

**Usage:** The tutorial helpers TutWaitForNextTaiki, TutWaitForNextTurn and TutWaitForNextTurnAfter call it and wait while the token exists.

[Back to index](#function-index)

<a id="call-turntk"></a>
### turntk

`turntk()`

Starts a waiting token that lasts until the next turn change (E_TurnToken).

**Arguments:** none.

**Returns:** 1.

**Usage:** The tutorial helpers TutWaitForNextTaiki, TutWaitForNextTurn and TutWaitForNextTurnAfter call it and wait while the token exists.

[Back to index](#function-index)
