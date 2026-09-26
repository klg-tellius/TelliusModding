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
| [AchieveSet](#call-achieveset) | Submits a named achievement/result reward entry from scenario-end logic. |
| [AddTT](#call-addtt) | Adds a raw temporary-terrain entry at a tile. |
| [AllPop](#call-allpop) | Restores the broader state pushed before entering a tutorial. |
| [AllPush](#call-allpush) | Pushes the broader scene/game state used by TutorialIn. |
| [AllUnitEscape](#call-allunitescape) | Runs the all-units escape operation used while tearing down scene actors. |
| [AllUnitsBreakup](#call-allunitsbreakup) | Walks force 0 only, bounded by ForceGetCount(0), and calls UnitCheckLinked_Breakup for each actor until count exhaustion or a null next actor. |
| [ArcFree](#call-arcfree) | Releases one reference to a relocatable game resource. |
| [ArcLoad](#call-arcload) | Loads a relocatable game resource. |
| [ArenaDump](#call-arenadump) | Prints memory-arena usage to debug output. |
| [BGMCont](#call-bgmcont) | Continues/restores a channel after a temporary event-music interruption. |
| [BGMFadeIn](#call-bgmfadein) | Starts/fades in a named track on a music channel. |
| [BGMFadeOut](#call-bgmfadeout) | Fades out a music channel. |
| [BGMMute](#call-bgmmute) | Mutes a channel over a transition duration; shared helpers use this while temporarily switching to event music. |
| [BGMPlay](#call-bgmplay) | Starts a named track on a music channel. |
| [BGMPlayVol](#call-bgmplayvol) | Starts a named track with an explicit volume parameter. |
| [BGMQuietOff](#call-bgmquietoff) | Clears the channel's quiet/ducking state. |
| [BGMQuietOn](#call-bgmquieton) | Enables the channel's quiet/ducking state around dialogue or rewards. |
| [BGMResume](#call-bgmresume) | Restores map-music channel 0 to volume 100 over 200 ms and starts a 200 ms countdown on active event-music channels 1–3. |
| [BGMSetVol](#call-bgmsetvol) | Changes a channel's volume over a transition. |
| [BGMStop](#call-bgmstop) | Requests a stop for a music channel. |
| [BMGetChapter](#call-bmgetchapter) | Reads the internal chapter file number (Prologue is 1). |
| [BMGetMoney](#call-bmgetmoney) | Reads the current money amount. |
| [BMGetPhase](#call-bmgetphase) | Reads the current phase identifier. |
| [BMGetTurn](#call-bmgetturn) | Reads the current turn number. |
| [BMGetValue](#call-bmgetvalue) | Reads a signed 16-bit field from battle-map state. |
| [BMSetMoney](#call-bmsetmoney) | Sets the money amount through the script API. |
| [BMSetPhase](#call-bmsetphase) | Sets the phase field through the script API. |
| [BMSetTanto](#call-bmsettanto) | Sets who controls each of the four active map forces. |
| [BMSetTerm](#call-bmsetterm) | Replaces one battle-map term string. |
| [BMSetTurn](#call-bmsetturn) | Sets the turn counter through the script API. |
| [BMSetValue](#call-bmsetvalue) | Writes a 16-bit field in battle-map state. |
| [BeginFinale](#call-beginfinale) | Enables finale mode and its input mask for A/B/X/Y/Z/L/R/Start. |
| [BeginMapHoldCursor](#call-beginmapholdcursor) | Starts the map cursor-hold process. |
| [BgmChangeEvt_MapToEvt1](#call-bgmchangeevt-maptoevt1) | Calls BGMMute(0, duration), waits the full duration with WaitM, then BGMPlay(1, bgm_id). |
| [BgmChangeEvt_MapToEvt2](#call-bgmchangeevt-maptoevt2) | Calls BGMMute(0, duration), waits duration >> 1 with WaitM, then BGMPlay(1, bgm_id). |
| [BgmChangeEvt_MapToEvt3](#call-bgmchangeevt-maptoevt3) | Calls BGMMute(0, duration), waits no time, then BGMPlay(1, bgm_id). |
| [BgmContEvt_EvtToMap1](#call-bgmcontevt-evttomap1) | Calls BGMFadeOut(1, fade_duration), waits the full fade_duration with WaitM, then BGMCont(0, resume_duration). |
| [BgmContEvt_EvtToMap2](#call-bgmcontevt-evttomap2) | Calls BGMFadeOut(1, fade_duration), waits fade_duration >> 1 with WaitM, then BGMCont(0, resume_duration). |
| [BgmContEvt_EvtToMap3](#call-bgmcontevt-evttomap3) | Calls BGMFadeOut(1, fade_duration), waits no time, then BGMCont(0, resume_duration). |
| [BuildDestruction](#call-builddestruction) | Destroys the building at a map location. |
| [BuildInstAnim](#call-buildinstanim) | Requests an animation for the map building/prop instance at a tile. |
| [BuildInstHide](#call-buildinsthide) | Hides a map building/prop instance at a location. |
| [BuildInstShow](#call-buildinstshow) | Shows a map building/prop instance at a location. |
| [ChapterMoviePlay](#call-chaptermovieplay) | Plays the opening movie selected for an internal chapter number. |
| [Check](#call-check) | Tests whether a base-conversation event is being evaluated for availability rather than being played. |
| [CheckAttackable](#call-checkattackable) | Tests whether this unit can reach a position from which its equipped weapon can attack an eligible enemy. |
| [CmFreeScript](#call-cmfreescript) | Unregisters and frees the last-loaded module, then unlinks it from the module list. |
| [CmLoadScript](#call-cmloadscript) | Loads a CMB script module and makes its exported functions available. |
| [CmSleepScript](#call-cmsleepscript) | Suspends a module’s event enumeration and temporarily removes its exported functions. |
| [CmWakeupScripts](#call-cmwakeupscripts) | Walks sleeping modules, restores their active marker and re-registers named exports. |
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
| [CopyMapCamera](#call-copymapcamera) | Saves the current map-camera state for a later PastMapCamera restoration. |
| [CpClrNoMoveFlag](#call-cpclrnomoveflag) | Clears the two no-move control bits from a unit’s AI state. |
| [CreateEventCamera](#call-createeventcamera) | Creates/prepares event-camera sequence state before keyframe calls. |
| [CreateNoticeFrame](#call-createnoticeframe) | Creates or updates an animated rectangular highlight around a screen area. |
| [CreateNoticeLFrame](#call-createnoticelframe) | Creates or updates an animated six-edge L-shaped screen highlight. |
| [DefaultDieTalk](#call-defaultdietalk) | Looks up and starts the defeated unit’s default death message when that message exists. For player or inactive units it also selects death music. |
| [DefaultEscapeTalk](#call-defaultescapetalk) | Looks up and starts the current acting unit’s default escape message when available. |
| [DeleteEventCamera](#call-deleteeventcamera) | Deletes event-camera state when returning to normal map-camera control. |
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
| [DisableSkip](#call-disableskip) | Disables event skipping for the active scene flow. |
| [DispFreeWholeForce](#call-dispfreewholeforce) | Releases display resources for every actor in a force list. |
| [DispLoadWholeForce](#call-disploadwholeforce) | Loads display resources for every actor in a force list. |
| [DispPreLoadWholeForce](#call-disppreloadwholeforce) | Queues battle-animation assets for every actor in a force list. |
| [Dispos](#call-dispos) | Deploys a named group through the ordinary staged deployment operation. |
| [DisposAsynchronous](#call-disposasynchronous) | Starts the asynchronous deployment variant for a named group. |
| [DisposAuxiliary](#call-disposauxiliary) | Invokes the DisposAuxiliary deployment variant on the supplied group. Its precise difference from ordinary Dispos is not yet fully documented. |
| [DisposContinue](#call-disposcontinue) | Invokes the DisposContinue deployment variant on the supplied group. Its precise difference from ordinary Dispos is not yet fully documented. |
| [DisposContinueSetMode](#call-disposcontinuesetmode) | Calls DisposContinue(normal_group) if NormalOnly(), otherwise DisposContinue(hard_group) if Hard(), otherwise DisposContinue(fallback_group). |
| [DisposFirst](#call-disposfirst) | Invokes the DisposFirst deployment variant on the supplied group. Its precise difference from ordinary Dispos is not yet fully documented. |
| [DisposFirstSetMode](#call-disposfirstsetmode) | Calls DisposFirst(normal_group) if NormalOnly(), otherwise DisposFirst(hard_group) if Hard(), otherwise DisposFirst(fallback_group). |
| [DisposGetGroupCenter](#call-disposgetgroupcenter) | Computes the center of a named deployment group and writes its coordinates into two variables. |
| [DisposSetMode](#call-dispossetmode) | Calls Dispos(normal_group) if NormalOnly(), otherwise Dispos(hard_group) if Hard(), otherwise Dispos(fallback_group). |
| [DisposWarp](#call-disposwarp) | Deploys a named reinforcement group using the warp deployment mode and suspends for active deployment motion. |
| [Dispos_ForEvent](#call-dispos-forevent) | If class_id is empty, uses matching_group without testing the actor. Otherwise tests UnitQueryJIDByPID and chooses matching_group or other_group. Uses InstantDispos when instant is nonzero, otherwise Dispos. |
| [Dispos_ForEventSenerio](#call-dispos-foreventsenerio) | Calls Dispos_ForEvent for PID_SENERIO and JID_MAGE. |
| [Dispos_ForEventTiamat](#call-dispos-foreventtiamat) | Calls Dispos_ForEvent("PID_TIAMAT", "", group, group, instant); the empty class bypasses the actor/class check. |
| [DoorClose](#call-doorclose) | Runs the door-closing operation at a location. |
| [DoorOpen](#call-dooropen) | Runs the door-opening operation at a location. |
| [ENVNoisyOff](#call-envnoisyoff) | Disables the environmental noisy state. |
| [ENVNoisyOn](#call-envnoisyon) | Enables the environmental noisy state. |
| [ENVNoisyOn_WhenNotEvtSkip](#call-envnoisyon-whennotevtskip) | Calls ENVNoisyOn only when (GCST() & 1) is zero. |
| [ENVQuietOff](#call-envquietoff) | Disables the environmental quiet state. |
| [ENVQuietOn](#call-envquieton) | Enables the environmental quiet state. |
| [ENVSilentOff](#call-envsilentoff) | Restores environment sound after ENVSilentOn. |
| [ENVSilentOff_WhenNotEvtSkip](#call-envsilentoff-whennotevtskip) | Calls ENVSilentOff only when (GCST() & 1) is zero. |
| [ENVSilentOn](#call-envsilenton) | Enables environmental silence with a transition parameter. |
| [Easy](#call-easy) | Always returns 0 in this US build; do not use this as a working difficulty test. |
| [EffectPlay](#call-effectplay) | Loads and spawns a named scene effect at the supplied position. |
| [EffectWait](#call-effectwait) | Waits for the native effect-completion condition. |
| [EnableSkip](#call-enableskip) | Enables event skipping for the active scene flow. |
| [EndFinale](#call-endfinale) | Disables finale mode and its input mask for A/B/X/Y/Z/L/R/Start. |
| [EndMapHoldCursor](#call-endmapholdcursor) | Ends the map cursor-hold process. |
| [EnemyDeadCheck](#call-enemydeadcheck) | Tests whether the enemy force list is empty. |
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
| [EventCameraWait](#call-eventcamerawait) | Waits for the active event-camera sequence. |
| [EventGetX](#call-eventgetx) | Reads the current map event's X coordinate. |
| [EventGetY](#call-eventgety) | Reads the current map event's Y coordinate. |
| [EventQuake](#call-eventquake) | Starts a repeating camera shake. |
| [EventQuakeStop](#call-eventquakestop) | Requests the active camera shake to stop. |
| [FRAME2MSEC](#call-frame2msec) | Converts a 60 Hz frame count to milliseconds. |
| [Fade](#call-fade) | Starts a screen transition. |
| [FadeWait](#call-fadewait) | Yields repeatedly while isFading() is nonzero. |
| [Flash](#call-flash) | Starts a colored screen flash. |
| [FlashWait](#call-flashwait) | Suspends the script while the screen flash is transitioning. |
| [Focus](#call-focus) | Moves map-camera focus toward a map-grid location. |
| [FocusBetweenAB](#call-focusbetweenab) | Requires both PIDs to be deployed, copies the current map camera, computes their tile midpoint using a right shift by 1, adds offsets and calls Focus or InstantFocus. |
| [FocusHardWait](#call-focushardwait) | Uses the stronger focus-wait operation used by scenes before dependent movement/dialogue. |
| [FocusWait](#call-focuswait) | Waits for the native focus operation's completion condition. |
| [ForceCheckAnyoneDead](#call-forcecheckanyonedead) | Walks force 6 and tests status bit 0x8000 on each actor. |
| [ForceGetCount](#call-forcegetcount) | Counts units in a runtime force list. |
| [ForceGetFirst](#call-forcegetfirst) | Returns the head used to iterate a runtime force list. |
| [GCST](#call-gcst) | Reads the event/game-controller state flags used by shared and chapter scripts. |
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
| [GameBind](#call-gamebind) | Binds gameplay while tutorial-specific work runs. |
| [GameUnbind](#call-gameunbind) | Releases the gameplay binding used by tutorial wrappers. |
| [GetBattleType](#call-getbattletype) | Reads the battle-type/status bitfield used by scene helpers. |
| [GetDiedPlayerCount](#call-getdiedplayercount) | Counts actors in force 6 whose death-record flag is set. |
| [GetFukiPosX](#call-getfukiposx) | Reads the X coordinate of the active tutorial speech-bubble display. |
| [GetFukiPosY](#call-getfukiposy) | Reads the Y coordinate of the active tutorial speech-bubble display. |
| [GetLanguage](#call-getlanguage) | Returns a hardcoded value in the US executable; it does not read a language setting. |
| [GetMapHeight](#call-getmapheight) | Samples the alternate terrain-surface height at the supplied map coordinates. |
| [GetMapHeightBase](#call-getmapheightbase) | Samples the base terrain height at the supplied map coordinates. |
| [GetRank](#call-getrank) | Reads the internal difficulty ID. |
| [GetRnd](#call-getrnd) | Draws a random integer using the game random-number generator. |
| [GetTutorial](#call-gettutorial) | Reads whether tutorial help is enabled in configuration. |
| [Hard](#call-hard) | Tests the internal difficulty ID for Hard (ID 1). |
| [HideMapCursor](#call-hidemapcursor) | Hides the map cursor shown by scene code. |
| [HidePrim2D](#call-hideprim2d) | Starts or ends the scene process that hides 2D primitives. |
| [IndividualWarRecord](#call-individualwarrecord) | Starts the individual war-record display and suspends the calling script. |
| [InstantDispos](#call-instantdispos) | Deploys a named group through the immediate placement operation. |
| [InstantDisposContinue](#call-instantdisposcontinue) | Invokes the InstantDisposContinue deployment variant on the supplied group. Its precise difference from ordinary Dispos is not yet fully documented. |
| [InstantDisposContinueSetMode](#call-instantdisposcontinuesetmode) | Calls InstantDisposContinue(normal_group) if NormalOnly(), otherwise InstantDisposContinue(hard_group) if Hard(), otherwise InstantDisposContinue(fallback_group). |
| [InstantDisposFirst](#call-instantdisposfirst) | Invokes the InstantDisposFirst deployment variant on the supplied group. Its precise difference from ordinary Dispos is not yet fully documented. |
| [InstantDisposFirstSetMode](#call-instantdisposfirstsetmode) | Calls InstantDisposFirst(normal_group) if NormalOnly(), otherwise InstantDisposFirst(hard_group) if Hard(), otherwise InstantDisposFirst(fallback_group). |
| [InstantDisposRank](#call-instantdisposrank) | Uses the difficulty/rank-selecting immediate-deployment variant for a group prefix. |
| [InstantDisposSetMode](#call-instantdispossetmode) | Calls InstantDispos(normal_group) if NormalOnly(), otherwise InstantDispos(hard_group) if Hard(), otherwise InstantDispos(fallback_group). |
| [InstantDoorClose](#call-instantdoorclose) | Applies the immediate door-close operation. |
| [InstantDoorOpen](#call-instantdooropen) | Applies the immediate door-open operation. |
| [InstantFocus](#call-instantfocus) | Sets map-camera focus to a map-grid location using the immediate-focus operation. |
| [InstantPastMapCamera](#call-instantpastmapcamera) | Uses the immediate restoration of the previously copied map-camera state. |
| [InstantRoofClose](#call-instantroofclose) | Applies the immediate roof-close operation. |
| [InstantRoofOpen](#call-instantroofopen) | Applies the immediate roof-open operation. |
| [InstantSetMapCamera](#call-instantsetmapcamera) | Immediately sets the map camera using its three native camera parameters. |
| [InstantUnitFocusByPID](#call-instantunitfocusbypid) | Resolves a deployed actor, reads its tile, then calls InstantFocus. |
| [InstantUnitFocusOffsetByPID](#call-instantunitfocusoffsetbypid) | Resolves a deployed actor, reads its tile and adds X/Y offsets, then calls InstantFocus. |
| [InstantUnitTransform](#call-instantunittransform) | Changes a unit to the requested transformed/untransformed state immediately and refreshes its display. |
| [IsE3Version](#call-ise3version) | Tests the E3/demo-build condition in this US executable. |
| [ItemGetIndex](#call-itemgetindex) | Resolves an item ID to its numeric item index. |
| [Join](#call-join) | Processes a named join/deployment group, such as the always_T_... groups used by TrialAddUnit. |
| [JyokyoMapCapture](#call-jyokyomapcapture) | Captures the status-map display and suspends the script while capture completes. |
| [JyokyoMapDelete](#call-jyokyomapdelete) | Deletes the status-map display. |
| [JyokyoMapEnemyOn](#call-jyokyomapenemyon) | Enables enemy markers on the status map. |
| [JyokyoMapHide](#call-jyokyomaphide) | Hides the status-map display. |
| [JyokyoMapPlayerOn](#call-jyokyomapplayeron) | Enables player markers on the status map. |
| [JyokyoMapShow](#call-jyokyomapshow) | Starts the status-map display. |
| [LocalDieTalkWithBgmChange](#call-localdietalkwithbgmchange) | Disables skip. If flag_name is nonempty and set, calls DefaultDieTalk. Otherwise mutes map music, fades event music over 500 ms, waits 500 ms, plays BGM_DEAD1 and the supplied message. Surrounds that custom branch with environment silence when GetBattleType has bit 0x80000000. Re-enables skip. |
| [MCResult](#call-mcresult) | Reads the last memory-card operation status. |
| [MSEC2FRAME](#call-msec2frame) | Converts milliseconds to 60 Hz frames. |
| [Maniac](#call-maniac) | Tests the internal difficulty ID for Maniac (ID 2). |
| [MapFree](#call-mapfree) | Calls _mf1(), yields once, then calls _mf2(). |
| [MapGetSight](#call-mapgetsight) | Reads the visibility-grid byte at a tile. |
| [MapGetTerrain](#call-mapgetterrain) | Reads the terrain ID stored at a map tile. |
| [MapGetUnit](#call-mapgetunit) | Reads the occupancy-grid unit handle at a tile. |
| [MapLoad](#call-mapload) | Loads the named map resources for the scene. |
| [MapReload](#call-mapreload) | Reloads the map during restoration after a temporary scene/tutorial. |
| [MapUpdate](#call-mapupdate) | Requests a map-state update after changes/restoration. |
| [MindGetItem](#call-mindgetitem) | Calls UnitGetItemShowing(MindGetMe(), item_id). |
| [MindGetMe](#call-mindgetme) | Reads the current action/event's acting unit. |
| [MindGetMind](#call-mindgetmind) | Reads the current map-action ID. |
| [MindGetMoney](#call-mindgetmoney) | Adds gold to the party and starts a reward notification associated with the current acting unit. |
| [MindGetTarget](#call-mindgettarget) | Reads the current action/event's target unit. |
| [MoviePlay](#call-movieplay) | Plays a named movie resource. |
| [NetuzoBattle](#call-netuzobattle) | Resolves and starts a scripted combat exchange between two actors, then suspends the script for the battle process. |
| [NetuzoInit](#call-netuzoinit) | Clears all 32 scripted-strike override slots and resets the scripted-battle counters. |
| [NetuzoSet](#call-netuzoset) | Configures outcome and combat-effect overrides for one scripted strike. |
| [Normal](#call-normal) | Tests the internal difficulty ID for Normal or Easy (ID 0 or 3). |
| [NormalOnly](#call-normalonly) | Always returns 0 in this US build; do not use this as a working difficulty test. |
| [PIDisAlive](#call-pidisalive) | Looks up a character’s current actor and checks that its dead flag is clear. |
| [PadResetMask](#call-padresetmask) | Removes buttons from the input mask. |
| [PadSetMask](#call-padsetmask) | Adds buttons to the input mask used by event/tutorial control. |
| [PastMapCamera](#call-pastmapcamera) | Restores the previously copied map-camera state through the normal camera transition. |
| [PersonGetYellLevel](#call-persongetyelllevel) | Gets the support rank for a mutually registered support pair. |
| [PersonSetYellLevel](#call-personsetyelllevel) | Sets both partners' support points to a selected threshold. This is not simply 'set displayed rank to n'. |
| [PlayerDeadCheck](#call-playerdeadcheck) | Tests whether the inactive force list is empty. |
| [PlayerEscapeCheck](#call-playerescapecheck) | Tests whether every existing actor in player force 0 or reserve force 5 has the escaped flag. |
| [PlayerEscapeCount](#call-playerescapecount) | Counts escaped actors in player force 0 and reserve force 5. |
| [PreLoadWait](#call-preloadwait) | Yields repeatedly while _pldone() equals zero. |
| [ProcExists](#call-procexists) | Queries existence of a named engine process; tutorial helpers use this to wait for tokens/actors. |
| [ProcKill](#call-prockill) | Requests termination of a named engine process. |
| [QueryLesson](#call-querylesson) | Tests whether the active lesson has the given name. |
| [RectAdjustBoundary](#call-rectadjustboundary) | Aligns a rectangle’s source image inside the 608 × 448 layout area. |
| [RectBuild](#call-rectbuild) | Builds the named rectangle/UI resource used for scene overlays. |
| [RectFadeIn](#call-rectfadein) | Fades in a rectangle. |
| [RectFadeOut](#call-rectfadeout) | Fades out a rectangle. |
| [RectFadeOutDelete](#call-rectfadeoutdelete) | Fades out and then deletes a rectangle. |
| [RectGet](#call-rectget) | Reads a rectangle property and truncates it to an integer. |
| [RectKill](#call-rectkill) | Kills/removes the named rectangle/UI instance. |
| [RectLeave](#call-rectleave) | Creates a rectangle/world-map image without attaching it to the current event as its parent. |
| [RectMove](#call-rectmove) | Animates a rectangle/world-map image so a source point is centered at (304, 240) at the requested scale. |
| [RectMoveOffset](#call-rectmoveoffset) | Animates a rectangle/world-map image to an explicit offset and restores its scale to 100%. |
| [RectPreLoad](#call-rectpreload) | Preloads a named rectangle/UI resource before use. |
| [RectSet](#call-rectset) | Sets a rectangle property immediately. |
| [RectSetCurve](#call-rectsetcurve) | Animates one rectangle property between two values. |
| [RectSetPos](#call-rectsetpos) | Sets a rectangle or world-map image’s position immediately. |
| [RegistGlobalFlags](#call-registglobalflags) | Calls the native global registration operation 22 times in fixed order for the original campaign flag list, including repeated reserved names. |
| [RemoveBackdrop](#call-removebackdrop) | Removes the backdrop process. |
| [ResumeEvent](#call-resumeevent) | Resumes the previously suspended event flow. |
| [RoofClose](#call-roofclose) | Runs the roof-closing operation at a location. |
| [RoofOpen](#call-roofopen) | Runs the roof-opening operation at a location. |
| [SFXPlay](#call-sfxplay) | Plays a named sound effect. |
| [SallyAddByGroup](#call-sallyaddbygroup) | Adds preparation/deployment placement from a group. |
| [SallyAddByPos](#call-sallyaddbypos) | Appends a deployment-selection position. |
| [SallyGetSurplus](#call-sallygetsurplus) | Reads the deployment surplus recorded when the deployment-selection flow finishes. |
| [SallySetByGroup](#call-sallysetbygroup) | Sets preparation/deployment placement from a group. |
| [SallySetByPos](#call-sallysetbypos) | Clears the deployment-selection position list, then adds this position. |
| [SelectAuxiliary](#call-selectauxiliary) | Starts the auxiliary-unit selection flow for a deployment group and suspends the calling script. |
| [SetAmbient](#call-setambient) | Sets map ambient lighting color, refreshes the map and yields the script. |
| [SetCamSuspend](#call-setcamsuspend) | Sets the camera-suspension flag for map scenes. |
| [SetCircle](#call-setcircle) | Enables or disables the scene’s unit-circle display setting. |
| [SetDiffuse](#call-setdiffuse) | Sets map diffuse lighting color, refreshes the map and yields the script. |
| [SetEventBattle](#call-seteventbattle) | Selects the special event presentation branch when the next battle animation is initialized. |
| [SetEventCameraAt](#call-seteventcameraat) | Adds or configures an event-camera target/position keyframe. |
| [SetEventCameraPrec](#call-seteventcameraprec) | Selects event-camera coordinate precision used by subsequent keyframes. |
| [SetEventCameraRot](#call-seteventcamerarot) | Adds or configures an event-camera rotation keyframe. |
| [SetFog](#call-setfog) | Sets the map’s rendering fog and refreshes its render state. |
| [SetFragile](#call-setfragile) | Adds a breakable terrain entry with the requested HP. |
| [SetGrid](#call-setgrid) | Sets the map-grid display intensity or restores the value saved when scene settings were created. |
| [SetMapCamera](#call-setmapcamera) | Transitions the map camera using its three native camera parameters. |
| [SetOnBtFocus](#call-setonbtfocus) | Enables or disables automatic battle-focus behavior. |
| [SetOutLink](#call-setoutlink) | Enables or disables the outer-link portion of the map-link grid and rebuilds that grid. |
| [SetPit](#call-setpit) | Adds a pit terrain entry at the given tile. |
| [SetPullCursor](#call-setpullcursor) | Enables or disables automatic cursor pulling. |
| [SetRock](#call-setrock) | Adds a rolling-rock terrain entry connected to a registered motion path. |
| [SetRoofEnable](#call-setroofenable) | Changes the enabled state of the roof section found at the supplied map position and refreshes the map. |
| [SetSepia](#call-setsepia) | Changes the sepia scene effect setting. |
| [SetShooter](#call-setshooter) | Adds a ballista/shooter terrain entry initialized from an item definition. |
| [SetSight](#call-setsight) | Sets the fog-of-war/sight mode, recalculates map ranges and refreshes the map. |
| [SetTerrain](#call-setterrain) | Writes terrain at a map tile through the runtime terrain API. |
| [SetWeather](#call-setweather) | Changes the map weather byte and refreshes weather, lighting and visibility rendering. |
| [SetWhiteBackdrop](#call-setwhitebackdrop) | Starts the solid-white backdrop process. |
| [ShooterBulletCheck](#call-shooterbulletcheck) | Totals spent ballista shots inside the active map bounds using five shots as the initial baseline. |
| [ShowMapCursor](#call-showmapcursor) | Shows the map cursor at a tile. |
| [SoundBossTalkEnd](#call-soundbosstalkend) | Under the same battle-type bit guard, restores environment, fades channel 1 over 750 and continues channel 0 over 750. |
| [SoundBossTalkStart](#call-soundbosstalkstart) | Only when GetBattleType() has bit 0x80000000: silences environment with parameter 30, mutes channel 0 over 750, and plays the supplied track on channel 1. |
| [StaffRoll](#call-staffroll) | Starts the staff credits and suspends the calling script. |
| [StartEventCamera](#call-starteventcamera) | Starts the configured event-camera sequence. |
| [SuspendEvent](#call-suspendevent) | Suspends the current event flow for tutorial/scene transfer. |
| [SysGetRound](#call-sysgetround) | Reads the playthrough ordinal from the clear-data record. |
| [TBoxOpen](#call-tboxopen) | Runs the treasure-box opening operation at a location. |
| [TTPMEntry](#call-ttpmentry) | Stores a terrain-motion path in the first free path slot. |
| [TTPMInit](#call-ttpminit) | Clears the 32 registered terrain-motion path slots. |
| [TalkEvent](#call-talkevent) | Plays an event message from the loaded message resources. Message commands can suspend dialogue for event-script work. |
| [TalkEventDirect](#call-talkeventdirect) | Starts the supplied event message, or passes it to the existing conversation process. |
| [TalkExist](#call-talkexist) | Queries whether a conversation remains active; tutorial helpers yield while this is true. |
| [TalkResume](#call-talkresume) | Resumes the current suspended event conversation rather than starting a new message. |
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
| [TutorialBasesCreate](#call-tutorialbasescreate) | Called by TutBasesCreate after E_BMapPlph appears, followed by a wait on E_BasesToken. |
| [TutorialBasesDelete](#call-tutorialbasesdelete) | Native teardown called directly by TutBasesDelete. |
| [TutorialCall](#call-tutorialcall) | Invokes the named tutorial entry in the shared tutorial-load sequence. |
| [TutorialDialog](#call-tutorialdialog) | Calls td(message_id), yields once, then tde(). |
| [TutorialForget](#call-tutorialforget) | Clears a tutorial’s learned mark. |
| [TutorialIn](#call-tutorialin) | Fades with mode 3 for 266 and waits; AllPush; MapFree; TutEntryCommon; SuspendEvent; yields once. |
| [TutorialInit](#call-tutorialinit) | Enables skip, calls _seqini, kills "E_Popup", calls _bmsini, then external Startup and RegistLocationTT. |
| [TutorialInitialize](#call-tutorialinitialize) | Starts tutorial initialization and suspends the calling script until it completes. |
| [TutorialLearn](#call-tutoriallearn) | Marks a tutorial as learned. |
| [TutorialLock](#call-tutoriallock) | Locks a tutorial. |
| [TutorialOut](#call-tutorialout) | Frees "mess/tut.m", frees the last-loaded script, wakes sleeping scripts and resumes the suspended event. |
| [TutorialResume](#call-tutorialresume) | Final native step in ComebackFunc, after event suspension, map teardown and external Startup. |
| [TutorialResumeOut](#call-tutorialresumeout) | MapFree; yield; AllPop; MapReload; UnitDispReload; external Startup; MapUpdate; Fade(2,266); FadeWait. |
| [TutorialSallyCreate](#call-tutorialsallycreate) | Called by TutSallyCreate after E_BMapPlph appears, followed by a wait on E_SallyToken. |
| [TutorialSallyDelete](#call-tutorialsallydelete) | Native teardown called directly by TutSallyDelete. |
| [TutorialUnlock](#call-tutorialunlock) | Unlocks a tutorial. |
| [Tutorial_FadeIn](#call-tutorial-fadein) | Disables skip, builds RID_MASK, sets property 9 to 0 and property 2 to -835, then RectSetCurve("RID_MASK",9,0,0,128,100). |
| [Tutorial_FadeOut](#call-tutorial-fadeout) | Calls RectSetCurve("RID_MASK",9,0,160,0,100), kills RID_MASK, then enables skip. |
| [UnitAddItem](#call-unitadditem) | Adds an item through the native inventory operation. |
| [UnitAddSkill](#call-unitaddskill) | Adds the indicated skill through the runtime unit API. |
| [UnitAnim](#call-unitanim) | Loads and plays a unit animation with the default blend length of 16, replacing an existing scripted animation for that unit. |
| [UnitAnimByPID](#call-unitanimbypid) | Resolves a deployed actor and calls UnitAnim. Missing actor exits without animation. |
| [UnitAnimF](#call-unitanimf) | Loads and plays a unit animation with a chosen transition length, replacing an existing scripted animation for that unit. |
| [UnitAnimFByPID](#call-unitanimfbypid) | Resolves a deployed actor and calls UnitAnimF. Missing actor exits without animation. |
| [UnitBreakup](#call-unitbreakup) | Breaks a unit's linked/pair relationship through the native operation. |
| [UnitCanUseIt](#call-unitcanuseit) | Checks whether the unit can use the item in the specified inventory slot. |
| [UnitCheckDeadHere](#call-unitcheckdeadhere) | Returns true exactly when the non-null unit's status has bit 0x8000 set. |
| [UnitCheckDeadHereByPID](#call-unitcheckdeadherebypid) | Looks up the PID and calls UnitCheckDeadHere; a missing actor returns 0. |
| [UnitCheckExists](#call-unitcheckexists) | Checks non-null actor membership in force 0, 1, 2 or 3. It reads status but does not use that value in the decision. |
| [UnitCheckExistsByPID](#call-unitcheckexistsbypid) | Looks up the actor and forwards to UnitCheckExists. |
| [UnitCheckExistsByPID2](#call-unitcheckexistsbypid2) | Looks up the actor and checks UnitCheckExists. |
| [UnitCheckLinked_Breakup](#call-unitchecklinked-breakup) | Returns early for null; otherwise calls UnitBreakup only if status & 0x06 is nonzero. |
| [UnitCheckLinked_BreakupByPID](#call-unitchecklinked-breakupbypid) | Resolves a deployed actor and forwards to UnitCheckLinked_Breakup. |
| [UnitCheckLiveByPID](#call-unitchecklivebypid) | Looks up the PID, then returns false for a null actor, status bit 0x08, or force 6; true otherwise. This is not a deployed-on-map test. |
| [UnitClassChange](#call-unitclasschange) | Runs the unit's class-change operation using its existing class/promotion data. |
| [UnitClrSkill](#call-unitclrskill) | Clears the indicated skill through the runtime unit API. |
| [UnitClrStatus](#call-unitclrstatus) | Clears selected status-mask bits from a unit. |
| [UnitDead](#call-unitdead) | Runs the native death operation; its complete consequences and trigger ordering require verification. |
| [UnitDelItem](#call-unitdelitem) | Deletes an inventory entry selected by the native index. |
| [UnitDispReload](#call-unitdispreload) | Reloads unit display resources during scene restoration. |
| [UnitDontMoveSally](#call-unitdontmovesally) | Applies the fixed-deployment-position operation during preparations. |
| [UnitDontMoveSallyByPID](#call-unitdontmovesallybypid) | Requires a deployed actor, calls BOTH UnitForcedSally and UnitDontMoveSally. |
| [UnitEscape](#call-unitescape) | Removes/escapes a unit through the native escape operation. |
| [UnitEscapeByPID](#call-unitescapebypid) | Requires a deployed actor, then calls UnitEscape(actor, 0). |
| [UnitFadeIn](#call-unitfadein) | Enables the unit fade-in setting used around subsequent placement/movement. |
| [UnitFadeOff](#call-unitfadeoff) | Clears the shared unit-fade setting. |
| [UnitFadeOut](#call-unitfadeout) | Enables the unit fade-out setting used around subsequent movement/escape. |
| [UnitFocus](#call-unitfocus) | Focuses the camera on a runtime unit. |
| [UnitFocusByPID](#call-unitfocusbypid) | Resolves a deployed actor, reads its tile, then calls Focus. |
| [UnitFocusOff](#call-unitfocusoff) | Disables the native automatic unit-focus setting. |
| [UnitFocusOffsetByPID](#call-unitfocusoffsetbypid) | Resolves a deployed actor, reads its tile and adds X/Y offsets, then calls Focus. |
| [UnitFocusOn](#call-unitfocuson) | Enables the native automatic unit-focus setting. |
| [UnitForcedSally](#call-unitforcedsally) | Marks a unit for forced deployment. |
| [UnitForcedSallyByPID](#call-unitforcedsallybypid) | Requires a deployed actor and calls UnitForcedSally. |
| [UnitGet](#call-unitget) | Reads a selected property of a runtime unit. |
| [UnitGetByPID](#call-unitgetbypid) | Finds the current runtime actor for a character ID. |
| [UnitGetByPos](#call-unitgetbypos) | Finds an eligible visible actor occupying a map tile. |
| [UnitGetEquipAccI](#call-unitgetequipacci) | Gets the active accessory slot in the combined inventory numbering. |
| [UnitGetEquipWepI](#call-unitgetequipwepi) | Gets the active equipped-weapon slot index. |
| [UnitGetForce](#call-unitgetforce) | Reads the actor's runtime force-list ID. |
| [UnitGetHP](#call-unitgethp) | Reads the unit's current HP. |
| [UnitGetItemCount](#call-unitgetitemcount) | Reads the unit's item inventory count. |
| [UnitGetItemShowing](#call-unitgetitemshowing) | Disables skip; if Comeback() is nonzero, starts Fade(2,166) and waits. Calls _gi(unit,item_id), yields once, then enables skip. |
| [UnitGetItemShowingSub](#call-unitgetitemshowingsub) | Quiets music channel 0, externally calls UnitGetItemShowing(unit,item_id), then restores channel quiet state. |
| [UnitGetMaxHP](#call-unitgetmaxhp) | Reads the unit's maximum HP. |
| [UnitGetMoveCost](#call-unitgetmovecost) | Reads this unit’s movement cost for a terrain-table entry. |
| [UnitGetNext](#call-unitgetnext) | Advances from a unit to the next member in the current list iteration. |
| [UnitGetRace](#call-unitgetrace) | Reports the unit’s beorc/laguz transformation category. |
| [UnitGetStatus](#call-unitgetstatus) | Reads the unit's status bitmask. |
| [UnitGetWeaponCount](#call-unitgetweaponcount) | Reads the unit's weapon inventory count. |
| [UnitGetX](#call-unitgetx) | Reads the unit's map-grid X coordinate. |
| [UnitGetXByPID](#call-unitgetxbypid) | Resolves a deployed actor and reads UnitGetX. |
| [UnitGetY](#call-unitgety) | Reads the unit's map-grid Y coordinate. |
| [UnitGetYByPID](#call-unitgetybypid) | Resolves a deployed actor and reads UnitGetY. |
| [UnitItemGetValuation](#call-unititemgetvaluation) | Returns the valuation used by the shared inventory-to-storage selection helper. |
| [UnitItemSendToHouseByPID](#call-unititemsendtohousebypid) | Requires an existing actor with exactly four weapons. Compares valuations for indices 0–3, then sends one entry to storage. |
| [UnitItemSendtoWarehouse](#call-unititemsendtowarehouse) | Transfers a selected inventory entry to storage. |
| [UnitItemSendtoWarehouseAll](#call-unititemsendtowarehouseall) | Transfers all eight of a unit’s inventory slots to storage, clears the original slots, and compacts the inventory. |
| [UnitItemSetDrop](#call-unititemsetdrop) | Marks an inventory entry for dropping through the native item API. |
| [UnitMoveDir](#call-unitmovedir) | Schedules movement using a direction-command string. |
| [UnitMoveDirByPID](#call-unitmovedirbypid) | Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitMoveDir with the remaining arguments. |
| [UnitMovePos](#call-unitmovepos) | Schedules actor movement toward a map position. |
| [UnitMovePosByPID](#call-unitmoveposbypid) | Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitMovePos with the remaining arguments. |
| [UnitMoveToUnit](#call-unitmovetounit) | Requires both actors to be deployed. Reads the FIRST actor's X/Y and moves the SECOND actor toward that tile. |
| [UnitMoveToUnitByPID](#call-unitmovetounitbypid) | Resolves both PIDs and calls UnitMoveToUnit(destination, mover). Discards that helper's result. |
| [UnitMoveWait](#call-unitmovewait) | Waits for the native unit-motion completion condition. |
| [UnitPairup](#call-unitpairup) | Links two actors using the game’s carrying/pairing operation, first moving the second actor to the tile right of the first. |
| [UnitPutToWarehouse](#call-unitputtowarehouse) | Transfers all eight of a unit’s inventory slots to storage, clears the original slots, and compacts the inventory. |
| [UnitQueryEquip](#call-unitqueryequip) | Tests the equipped bit of an inventory slot. |
| [UnitQueryJID](#call-unitqueryjid) | Tests the actor against a class ID. |
| [UnitQueryJIDByPID](#call-unitqueryjidbypid) | Looks up the actor; if present, returns UnitQueryJID(actor, class_id). |
| [UnitQueryPID](#call-unitquerypid) | Tests the actor against a character ID. |
| [UnitReplaceItem](#call-unitreplaceitem) | Replaces the selected inventory slot using an item ID. |
| [UnitRotate](#call-unitrotate) | Requests a unit facing/rotation change. |
| [UnitRotateByPID](#call-unitrotatebypid) | Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitRotate with the remaining arguments. |
| [UnitRotateToPos](#call-unitrotatetopos) | Requires a deployed actor, compares its tile to the target tile and chooses an eight-direction facing using the original axis/diagonal threshold branches, then calls UnitRotate. |
| [UnitRotateToPosByPID](#call-unitrotatetoposbypid) | Resolves a deployed actor and forwards to UnitRotateToPos. |
| [UnitRotateToUnit](#call-unitrotatetounit) | Requires both actors deployed, reads the target actor's tile and rotates the first actor toward it using UnitRotateToPos. |
| [UnitRotateToUnitByPID](#call-unitrotatetounitbypid) | Resolves both deployed actors and forwards to UnitRotateToUnit. |
| [UnitSearchItem](#call-unitsearchitem) | Searches a unit's inventory for an item ID. |
| [UnitSet](#call-unitset) | Writes one of the supported mutable unit fields. |
| [UnitSetAccAway](#call-unitsetaccaway) | Requests the accessory-away state. |
| [UnitSetCpAttackSeq](#call-unitsetcpattackseq) | Sets the actor's attack AI sequence. |
| [UnitSetCpHealSeq](#call-unitsetcphealseq) | Changes the unit’s healing AI sequence by resource name. |
| [UnitSetCpMTypeID](#call-unitsetcpmtypeid) | Changes the unit’s MTYPE AI table by resource name. |
| [UnitSetCpMoveSeq](#call-unitsetcpmoveseq) | Sets the actor's movement AI sequence. |
| [UnitSetCpTypeByPID](#call-unitsetcptypebypid) | Resolves a deployed actor, then sets its attack sequence followed by its movement sequence. |
| [UnitSetEXP](#call-unitsetexp) | Sets the unit's experience value; automatic level-up behavior is not established. |
| [UnitSetEquip](#call-unitsetequip) | Selects an inventory entry for equipping. |
| [UnitSetFixed](#call-unitsetfixed) | Sets or clears the unit’s fixed-state flag. |
| [UnitSetHP](#call-unitsethp) | Sets current HP; clamping and death dispatch are not established, so this is not documented as equivalent to killing the unit. |
| [UnitSetHold](#call-unitsethold) | Changes the shared scene unit-hold setting. |
| [UnitSetPos](#call-unitsetpos) | Positions an actor on the map. |
| [UnitSetPosDir](#call-unitsetposdir) | For a non-null actor, sets its tile then immediately rotates it unless direction is -1. |
| [UnitSetPosDirByPID](#call-unitsetposdirbypid) | Resolves a deployed actor, sets its tile, and immediately rotates unless direction is -1. |
| [UnitSetPosDirByPos](#call-unitsetposdirbypos) | Finds the actor at the source tile, moves it to the destination, and immediately rotates unless direction is -1. |
| [UnitSetStatus](#call-unitsetstatus) | Applies status-mask bits to a unit. |
| [UnitSetWeaponAway](#call-unitsetweaponaway) | Requests the weapon-away state used by scene helpers. |
| [UnitSetWeaponAwayByPID](#call-unitsetweaponawaybypid) | Resolves a deployed actor and returns UnitSetWeaponAway(actor). |
| [UnitTackle](#call-unittackle) | Moves the target away from the acting unit and starts shove/smite motion. |
| [UnitTransferToForce](#call-unittransfertoforce) | Moves an actor to the specified runtime force list. The destination changes runtime membership; a persistent recruitment may need additional chapter/story setup. |
| [UnitTransferToForceByPID](#call-unittransfertoforcebypid) | Resolves the actor, applies the UnitCheckLiveByPID-equivalent null/status-0x08/force-6 test, then calls UnitTransferToForce. |
| [UnitTransform](#call-unittransform) | Changes a unit to the requested transformed/untransformed state with its transformation animation. |
| [UnitTstSkill](#call-unittstskill) | Tests the indicated skill on the unit. |
| [UnitWalkDir](#call-unitwalkdir) | Sets the direction bits used by subsequent scene walking. |
| [UnitWalkSlow](#call-unitwalkslow) | Enables or disables slow walking for subsequent scene movement. |
| [UnitWarpOut](#call-unitwarpout) | Runs the native warp-out operation for a unit. |
| [UnitsInitialize](#call-unitsinitialize) | Initializes the runtime unit state used by chapter/scene setup. |
| [UnitsPop](#call-unitspop) | Restores the pushed unit state. |
| [UnitsPopWithoutMap](#call-unitspopwithoutmap) | Uses the unit-state restoration variant without the normal map operation. |
| [UnitsPush](#call-unitspush) | Pushes unit state for later restoration. |
| [UnitsPush_Uninitialize](#call-unitspush-uninitialize) | Pushes unit state and performs the uninitializing variant for a temporary scene. |
| [VisitIn](#call-visitin) | Runs the VisitIn unit/building transition used by location events. |
| [VisitOut](#call-visitout) | Runs the VisitOut unit/building transition used by location events. |
| [WaitF](#call-waitf) | Delays event sequencing by a frame count. |
| [WaitM](#call-waitm) | Delays event sequencing for a millisecond duration in ordinary scene code. |
| [WaitPressAnyKey](#call-waitpressanykey) | Suspends the calling script until the input-wait process completes after a key press. |
| [WarRecord](#call-warrecord) | Starts the war-record display and suspends the calling script. |
| [WipeEnd](#call-wipeend) | Resets the screen-wipe state to idle. |
| [WipeIn](#call-wipein) | Starts a screen wipe in. |
| [WipeOut](#call-wipeout) | Starts a screen wipe out. |
| [WipeWait](#call-wipewait) | Suspends the script while a wipe-in or wipe-out transition is active. |
| [_bmsini](#call--bmsini) | Tutorial state initialization step called by TutorialInit after killing E_Popup and before Startup. |
| [_cmb_mess_load](#call--cmb-mess-load) | Loads the script/message pair used by the common tutorial-entry sequence. |
| [_gi](#call--gi) | Native operation invoked by UnitGetItemShowing to deliver/show an item reward. |
| [_intr](#call--intr) | Runs the chapter-checkpoint save sequence and suspends the calling script until it finishes. |
| [_mf1](#call--mf1) | First native stage of MapFree, before its mandatory yield. |
| [_mf2](#call--mf2) | Second native stage of MapFree, after its yield. |
| [_pa](#call--pa) | Starts the tutorial actor/input operation whose E_PadActor process is polled by TutPadActor. |
| [_pldone](#call--pldone) | Readiness predicate used by PreLoadWait; a zero result keeps the helper yielding. |
| [_seqini](#call--seqini) | Tutorial sequence initialization step called by TutorialInit before killing E_Popup. |
| [_tr](#call--tr) | Resumes the tutorial conversation operation used by TutTalkResume. |
| [_tt](#call--tt) | Starts the tutorial conversation operation used inside GameBind/GameUnbind by TutTalkEvent. |
| [clr](#call-clr) | Looks up a registered named flag and clears its bit. An unregistered name is a silent no-op. |
| [dump](#call-dump) | Prints all eight force lists and their units to debug output. |
| [get](#call-get) | Looks up a registered named flag and reads its bit. |
| [global](#call-global) | Registers a campaign flag in the lowest empty flag-table slot and clears its bit. Original global registration occurs at boot. |
| [intplGetValue](#call-intplgetvalue) | Computes one interpolated value without starting an animation. |
| [isFading](#call-isfading) | Reports the screen-fade busy state consumed by FadeWait. |
| [isFlash](#call-isflash) | Tests whether the screen flash is in either transition phase. |
| [isWipe](#call-iswipe) | Tests whether a wipe-in or wipe-out transition is active. |
| [regist](#call-regist) | Registers a chapter flag in the highest empty slot of the shared 96-slot flag table. It leaves that slot's bit unchanged. |
| [report](#call-report) | Writes text to the game’s debug-report output. |
| [set](#call-set) | Looks up a registered named flag and sets its bit. An unregistered name is a silent no-op. |
| [taikitk](#call-taikitk) | Starts the native step whose E_TaikiToken process is polled by TutWaitForNextTaiki. |
| [td](#call-td) | Starts the native tutorial-dialog step used by TutorialDialog. |
| [tde](#call-tde) | Final native step called by TutorialDialog after td and one yield. |
| [turnatk](#call-turnatk) | Starts the native step whose E_TurnAToken process is polled by TutWaitForNextTurnAfter. |
| [turntk](#call-turntk) | Starts the native step whose E_TurnToken process is polled by TutWaitForNextTurn. |

## Detailed entries

<a id="call-achieveset"></a>
### AchieveSet

`AchieveSet(message_id, amount)`

Submits a named achievement/result reward entry from scenario-end logic.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Reward/result label ID, such as Ms_ach_02_turn. |
| `amount` | Reward value calculated by the chapter's result function. |

**Returns:** 1.

**Usage:** Preserve the scenario-end function's return value and one-time dispatch; do not equate this with BMSetMoney.

[Back to index](#function-index)

<a id="call-addtt"></a>
### AddTT

`AddTT(x, y, type, subtype, value_1, value_2)`

Adds a raw temporary-terrain entry at a tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |
| `type` | Terrain-entry type. Prefer SetFragile (4), SetShooter (7), SetRock (10), or SetPit when available. |
| `subtype` | Type-specific subtype byte. |
| `value_1` | First type-specific state byte. |
| `value_2` | Second type-specific state byte. |

**Returns:** 1.

**Usage:** Low-level operation: use the dedicated constructors for normal authoring. All four control/state values are bytes; two remaining state bytes are zeroed. It does not create map geometry.

[Back to index](#function-index)

<a id="call-allpop"></a>
### AllPop

`AllPop()`

Restores the broader state pushed before entering a tutorial.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact contents/depth of the save stack are not fully decoded. Preserve matched push/pop ownership.

[Back to index](#function-index)

<a id="call-allpush"></a>
### AllPush

`AllPush()`

Pushes the broader scene/game state used by TutorialIn.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact contents/depth of the save stack are not fully decoded. Preserve matched push/pop ownership.

[Back to index](#function-index)

<a id="call-allunitescape"></a>
### AllUnitEscape

`AllUnitEscape()`

Runs the all-units escape operation used while tearing down scene actors.

**Arguments:** none.

**Returns:** 1.

**Usage:** Keep the original lifecycle around this call; it is not a stand-alone chapter reset.

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

Continues/restores a channel after a temporary event-music interruption.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel. Shared helpers use 0 for map music and 1 for event music; do not assume an unlimited channel range. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** 1.

**Usage:** Track ownership, interruption and exact native return behavior are not implied by the call's name.

[Back to index](#function-index)

<a id="call-bgmfadein"></a>
### BGMFadeIn

`BGMFadeIn(channel, bgm_id, duration_ms)`

Starts/fades in a named track on a music channel.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel. Shared helpers use 0 for map music and 1 for event music; do not assume an unlimited channel range. |
| `bgm_id` | Existing BGM_... track ID; not an audio filename. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Track ownership, interruption and exact native return behavior are not implied by the call's name.

[Back to index](#function-index)

<a id="call-bgmfadeout"></a>
### BGMFadeOut

`BGMFadeOut(channel, duration_ms)`

Fades out a music channel.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel. Shared helpers use 0 for map music and 1 for event music; do not assume an unlimited channel range. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** 1.

**Usage:** Track ownership, interruption and exact native return behavior are not implied by the call's name.

[Back to index](#function-index)

<a id="call-bgmmute"></a>
### BGMMute

`BGMMute(channel, duration_ms)`

Mutes a channel over a transition duration; shared helpers use this while temporarily switching to event music.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel. Shared helpers use 0 for map music and 1 for event music; do not assume an unlimited channel range. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** 1.

**Usage:** Track ownership, interruption and exact native return behavior are not implied by the call's name.

[Back to index](#function-index)

<a id="call-bgmplay"></a>
### BGMPlay

`BGMPlay(channel, bgm_id)`

Starts a named track on a music channel.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel. Shared helpers use 0 for map music and 1 for event music; do not assume an unlimited channel range. |
| `bgm_id` | Existing BGM_... track ID; not an audio filename. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Track ownership, interruption and exact native return behavior are not implied by the call's name.

[Back to index](#function-index)

<a id="call-bgmplayvol"></a>
### BGMPlayVol

`BGMPlayVol(channel, bgm_id, volume)`

Starts a named track with an explicit volume parameter.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel. Shared helpers use 0 for map music and 1 for event music; do not assume an unlimited channel range. |
| `bgm_id` | Existing BGM_... track ID; not an audio filename. |
| `volume` | Native volume value; valid range/scale not decoded here. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Track ownership, interruption and exact native return behavior are not implied by the call's name.

[Back to index](#function-index)

<a id="call-bgmquietoff"></a>
### BGMQuietOff

`BGMQuietOff(channel)`

Clears the channel's quiet/ducking state.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel. Shared helpers use 0 for map music and 1 for event music; do not assume an unlimited channel range. |

**Returns:** 1.

**Usage:** Track ownership, interruption and exact native return behavior are not implied by the call's name.

[Back to index](#function-index)

<a id="call-bgmquieton"></a>
### BGMQuietOn

`BGMQuietOn(channel)`

Enables the channel's quiet/ducking state around dialogue or rewards.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel. Shared helpers use 0 for map music and 1 for event music; do not assume an unlimited channel range. |

**Returns:** 1.

**Usage:** Track ownership, interruption and exact native return behavior are not implied by the call's name.

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

Changes a channel's volume over a transition.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel. Shared helpers use 0 for map music and 1 for event music; do not assume an unlimited channel range. |
| `volume` | Native target volume; range/scale not decoded here. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** 1.

**Usage:** Track ownership, interruption and exact native return behavior are not implied by the call's name.

[Back to index](#function-index)

<a id="call-bgmstop"></a>
### BGMStop

`BGMStop(channel)`

Requests a stop for a music channel.

| Argument | Meaning and restrictions |
|---|---|
| `channel` | Music channel. Shared helpers use 0 for map music and 1 for event music; do not assume an unlimited channel range. |

**Returns:** 1.

**Usage:** Track ownership, interruption and exact native return behavior are not implied by the call's name.

[Back to index](#function-index)

<a id="call-bmgetchapter"></a>
### BMGetChapter

`BMGetChapter()`

Reads the internal chapter file number (Prologue is 1).

**Arguments:** none.

**Returns:** Internal chapter file number (prologue is 1).

[Back to index](#function-index)

<a id="call-bmgetmoney"></a>
### BMGetMoney

`BMGetMoney()`

Reads the current money amount.

**Arguments:** none.

**Returns:** Current money amount.

[Back to index](#function-index)

<a id="call-bmgetphase"></a>
### BMGetPhase

`BMGetPhase()`

Reads the current phase identifier.

**Arguments:** none.

**Returns:** Current phase identifier.

[Back to index](#function-index)

<a id="call-bmgetturn"></a>
### BMGetTurn

`BMGetTurn()`

Reads the current turn number.

**Arguments:** none.

**Returns:** Current turn number.

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

Sets the money amount through the script API.

| Argument | Meaning and restrictions |
|---|---|
| `value` | New money amount. Setting a field is not proof that the associated phase/turn transition events execute. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Clamping and full event-transition consequences are not established here.

[Back to index](#function-index)

<a id="call-bmsetphase"></a>
### BMSetPhase

`BMSetPhase(value)`

Sets the phase field through the script API.

| Argument | Meaning and restrictions |
|---|---|
| `value` | New phase field. Setting a field is not proof that the associated phase/turn transition events execute. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Clamping and full event-transition consequences are not established here.

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

`BMSetTurn(value)`

Sets the turn counter through the script API.

| Argument | Meaning and restrictions |
|---|---|
| `value` | New turn counter. Setting a field is not proof that the associated phase/turn transition events execute. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Clamping and full event-transition consequences are not established here.

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

Destroys the building at a map location.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-buildinstanim"></a>
### BuildInstAnim

`BuildInstAnim(x, y, animation)`

Requests an animation for the map building/prop instance at a tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |
| `animation` | Prop-specific animation selector; the valid mapping depends on the instance. |

**Returns:** Not specified; do not use this result as a condition.

[Back to index](#function-index)

<a id="call-buildinsthide"></a>
### BuildInstHide

`BuildInstHide(x, y)`

Hides a map building/prop instance at a location.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-buildinstshow"></a>
### BuildInstShow

`BuildInstShow(x, y)`

Shows a map building/prop instance at a location.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-chaptermovieplay"></a>
### ChapterMoviePlay

`ChapterMoviePlay(chapter)`

Plays the opening movie selected for an internal chapter number.

| Argument | Meaning and restrictions |
|---|---|
| `chapter` | Internal file/chapter number. This is not a request to progress to that chapter. |

**Returns:** Not specified; do not use this result as a condition.

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

Unregisters and frees the last-loaded module, then unlinks it from the module list.

**Arguments:** none.

**Returns:** Not specified; do not use this result as a condition.

**Usage:** No name argument: this is LIFO removal, not removal of an arbitrary script.

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

Walks sleeping modules, restores their active marker and re-registers named exports.

**Arguments:** none.

**Returns:** Not specified; do not use this result as a condition.

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

Saves the current map-camera state for a later PastMapCamera restoration.

**Arguments:** none.

**Returns:** 1.

**Usage:** Preserve the full create/copy/start/wait/restore lifecycle from a matching scene.

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

Creates/prepares event-camera sequence state before keyframe calls.

**Arguments:** none.

**Returns:** 1.

**Usage:** Preserve the full create/copy/start/wait/restore lifecycle from a matching scene.

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

Deletes event-camera state when returning to normal map-camera control.

**Arguments:** none.

**Returns:** 1.

**Usage:** Preserve the full create/copy/start/wait/restore lifecycle from a matching scene.

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

Disables event skipping for the active scene flow.

**Arguments:** none.

**Returns:** 1.

**Usage:** A state change, not a scoped Python context manager. Preserve restoration on every scene exit.

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

Deploys a named group through the ordinary staged deployment operation.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** 1.

**Usage:** Requires matching deployment data, legal positions and valid actor/item references. Group suffix and difficulty selection depend on the actual helper/native path.

[Back to index](#function-index)

<a id="call-disposasynchronous"></a>
### DisposAsynchronous

`DisposAsynchronous(group)`

Starts the asynchronous deployment variant for a named group.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** 1.

**Usage:** Requires matching deployment data, legal positions and valid actor/item references. Group suffix and difficulty selection depend on the actual helper/native path.

[Back to index](#function-index)

<a id="call-disposauxiliary"></a>
### DisposAuxiliary

`DisposAuxiliary(group)`

Invokes the DisposAuxiliary deployment variant on the supplied group. Its precise difference from ordinary Dispos is not yet fully documented.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** 1.

**Usage:** Requires matching deployment data, legal positions and valid actor/item references. Group suffix and difficulty selection depend on the actual helper/native path.

[Back to index](#function-index)

<a id="call-disposcontinue"></a>
### DisposContinue

`DisposContinue(group)`

Invokes the DisposContinue deployment variant on the supplied group. Its precise difference from ordinary Dispos is not yet fully documented.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** 1.

**Usage:** Requires matching deployment data, legal positions and valid actor/item references. Group suffix and difficulty selection depend on the actual helper/native path.

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

Invokes the DisposFirst deployment variant on the supplied group. Its precise difference from ordinary Dispos is not yet fully documented.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** 1.

**Usage:** Requires matching deployment data, legal positions and valid actor/item references. Group suffix and difficulty selection depend on the actual helper/native path.

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

Runs the door-closing operation at a location.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-dooropen"></a>
### DoorOpen

`DoorOpen(x, y)`

Runs the door-opening operation at a location.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-envnoisyoff"></a>
### ENVNoisyOff

`ENVNoisyOff()`

Disables the environmental noisy state.

**Arguments:** none.

**Returns:** 1.

**Usage:** Use the corresponding pair from a tested scene; exact mixing levels are not decoded.

[Back to index](#function-index)

<a id="call-envnoisyon"></a>
### ENVNoisyOn

`ENVNoisyOn()`

Enables the environmental noisy state.

**Arguments:** none.

**Returns:** 1.

**Usage:** Use the corresponding pair from a tested scene; exact mixing levels are not decoded.

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

Disables the environmental quiet state.

**Arguments:** none.

**Returns:** 1.

**Usage:** Use the corresponding pair from a tested scene; exact mixing levels are not decoded.

[Back to index](#function-index)

<a id="call-envquieton"></a>
### ENVQuietOn

`ENVQuietOn()`

Enables the environmental quiet state.

**Arguments:** none.

**Returns:** 1.

**Usage:** Use the corresponding pair from a tested scene; exact mixing levels are not decoded.

[Back to index](#function-index)

<a id="call-envsilentoff"></a>
### ENVSilentOff

`ENVSilentOff()`

Restores environment sound after ENVSilentOn.

**Arguments:** none.

**Returns:** 1.

**Usage:** Use the corresponding pair from a tested scene; exact mixing levels are not decoded.

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

`ENVSilentOn(transition)`

Enables environmental silence with a transition parameter.

| Argument | Meaning and restrictions |
|---|---|
| `transition` | Native transition value, often 0, 30, 45, 60 or 90. Do not assume WaitM's units apply; exact units are not established here. |

**Returns:** 1.

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

Waits for the native effect-completion condition.

**Arguments:** none.

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Exact process coverage, event-skip paths and timeout behavior are not fully documented; no timeout argument is exposed.

[Back to index](#function-index)

<a id="call-enableskip"></a>
### EnableSkip

`EnableSkip()`

Enables event skipping for the active scene flow.

**Arguments:** none.

**Returns:** 1.

**Usage:** A state change, not a scoped Python context manager. Preserve restoration on every scene exit.

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

Tests whether the enemy force list is empty.

**Arguments:** none.

**Returns:** 1 if empty; 0 if at least one enemy remains.

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

Waits for the active event-camera sequence.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact process coverage, event-skip paths and timeout behavior are not fully documented; no timeout argument is exposed.

[Back to index](#function-index)

<a id="call-eventgetx"></a>
### EventGetX

`EventGetX()`

Reads the current map event's X coordinate.

**Arguments:** none.

**Returns:** Map coordinate for EventGetX/Y; unit reference for MindGetMe/Target.

**Usage:** Meaning depends on an active event/action context. Do not assume a turn event provides the same actor/target as a talk, combat or visit.

[Back to index](#function-index)

<a id="call-eventgety"></a>
### EventGetY

`EventGetY()`

Reads the current map event's Y coordinate.

**Arguments:** none.

**Returns:** Map coordinate for EventGetX/Y; unit reference for MindGetMe/Target.

**Usage:** Meaning depends on an active event/action context. Do not assume a turn event provides the same actor/target as a talk, combat or visit.

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

Moves map-camera focus toward a map-grid location.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** 0.

**Usage:** Use the chapter's matching FocusWait/FocusHardWait pattern before dependent scene work.

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

Uses the stronger focus-wait operation used by scenes before dependent movement/dialogue.

**Arguments:** none.

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Exact process coverage, event-skip paths and timeout behavior are not fully documented; no timeout argument is exposed.

[Back to index](#function-index)

<a id="call-focuswait"></a>
### FocusWait

`FocusWait()`

Waits for the native focus operation's completion condition.

**Arguments:** none.

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Exact process coverage, event-skip paths and timeout behavior are not fully documented; no timeout argument is exposed.

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

Counts units in a runtime force list.

| Argument | Meaning and restrictions |
|---|---|
| `force` | Runtime force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 player reserve, 6 inactive/death-flagged, 7 special inactive (less precisely decoded). Not a phase enum. |

**Returns:** Unit count for that list, not automatically the number alive/deployed in the entire chapter.

[Back to index](#function-index)

<a id="call-forcegetfirst"></a>
### ForceGetFirst

`ForceGetFirst(force)`

Returns the head used to iterate a runtime force list.

| Argument | Meaning and restrictions |
|---|---|
| `force` | Runtime force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 player reserve, 6 inactive/death-flagged, 7 special inactive (less precisely decoded). Not a phase enum. |

**Returns:** First unit reference, or 0 for no accessible head. Iterate with UnitGetNext.

[Back to index](#function-index)

<a id="call-gcst"></a>
### GCST

`GCST()`

Reads the event/game-controller state flags used by shared and chapter scripts.

**Arguments:** none.

**Returns:** Bitmask; shared environment helpers test bit 0x01.

**Usage:** Only the observed bit tests are documented; other bits and their transitions remain unresolved.

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

Binds gameplay while tutorial-specific work runs.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact nesting/scheduling semantics remain native. Follow the complete shared helper sequence, not an isolated call.

[Back to index](#function-index)

<a id="call-gameunbind"></a>
### GameUnbind

`GameUnbind()`

Releases the gameplay binding used by tutorial wrappers.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact nesting/scheduling semantics remain native. Follow the complete shared helper sequence, not an isolated call.

[Back to index](#function-index)

<a id="call-getbattletype"></a>
### GetBattleType

`GetBattleType()`

Reads the battle-type/status bitfield used by scene helpers.

**Arguments:** none.

**Returns:** Bitmask; shared boss/death-talk helpers test bit 0x80000000.

**Usage:** The entire bitfield is not decoded here. Do not treat the result as a boolean or a single enum.

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

Returns a hardcoded value in the US executable; it does not read a language setting.

**Arguments:** none.

**Returns:** 1, always, in this US build.

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

Reads the internal difficulty ID.

**Arguments:** none.

**Returns:** Internal difficulty value; see Normal/Hard/Maniac for the difficulty mapping.

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

Tests the internal difficulty ID for Hard (ID 1).

**Arguments:** none.

**Returns:** Boolean predicate.

**Usage:** Internal labels must not be assumed to match every region's menu labels. NormalOnly and Easy are separate unregistered names.

[Back to index](#function-index)

<a id="call-hidemapcursor"></a>
### HideMapCursor

`HideMapCursor()`

Hides the map cursor shown by scene code.

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

Deploys a named group through the immediate placement operation.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** 1.

**Usage:** Requires matching deployment data, legal positions and valid actor/item references. Group suffix and difficulty selection depend on the actual helper/native path.

[Back to index](#function-index)

<a id="call-instantdisposcontinue"></a>
### InstantDisposContinue

`InstantDisposContinue(group)`

Invokes the InstantDisposContinue deployment variant on the supplied group. Its precise difference from ordinary Dispos is not yet fully documented.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** 1.

**Usage:** Requires matching deployment data, legal positions and valid actor/item references. Group suffix and difficulty selection depend on the actual helper/native path.

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

Invokes the InstantDisposFirst deployment variant on the supplied group. Its precise difference from ordinary Dispos is not yet fully documented.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** 1.

**Usage:** Requires matching deployment data, legal positions and valid actor/item references. Group suffix and difficulty selection depend on the actual helper/native path.

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

Uses the difficulty/rank-selecting immediate-deployment variant for a group prefix.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** 1.

**Usage:** Requires matching deployment data, legal positions and valid actor/item references. Group suffix and difficulty selection depend on the actual helper/native path.

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

Applies the immediate door-close operation.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-instantdooropen"></a>
### InstantDoorOpen

`InstantDoorOpen(x, y)`

Applies the immediate door-open operation.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-instantfocus"></a>
### InstantFocus

`InstantFocus(x, y)`

Sets map-camera focus to a map-grid location using the immediate-focus operation.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** 0.

[Back to index](#function-index)

<a id="call-instantpastmapcamera"></a>
### InstantPastMapCamera

`InstantPastMapCamera()`

Uses the immediate restoration of the previously copied map-camera state.

**Arguments:** none.

**Returns:** 1.

**Usage:** Preserve the full create/copy/start/wait/restore lifecycle from a matching scene.

[Back to index](#function-index)

<a id="call-instantroofclose"></a>
### InstantRoofClose

`InstantRoofClose(x, y)`

Applies the immediate roof-close operation.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-instantroofopen"></a>
### InstantRoofOpen

`InstantRoofOpen(x, y)`

Applies the immediate roof-open operation.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-instantsetmapcamera"></a>
### InstantSetMapCamera

`InstantSetMapCamera(camera_a, camera_b, camera_c)`

Immediately sets the map camera using its three native camera parameters.

| Argument | Meaning and restrictions |
|---|---|
| `camera_a` | First camera parameter; exact axis/angle convention not verified. |
| `camera_b` | Second camera parameter; exact axis/angle convention not verified. |
| `camera_c` | Third camera parameter; exact distance/scale convention not verified. |

**Returns:** 1.

**Usage:** These are camera parameters, not three map-tile coordinates.

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

Processes a named join/deployment group, such as the always_T_... groups used by TrialAddUnit.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** This takes a section/group name, not a PID. Persistent roster effects depend on the group's records and surrounding flow.

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

Tests the internal difficulty ID for Maniac (ID 2).

**Arguments:** none.

**Returns:** Boolean predicate.

**Usage:** Internal labels must not be assumed to match every region's menu labels. NormalOnly and Easy are separate unregistered names.

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

Loads the named map resources for the scene.

| Argument | Meaning and restrictions |
|---|---|
| `map_name` | Map resource name such as bmap02 or bmap06_2, not a displayed chapter title. |

**Returns:** 1.

**Usage:** Loading a map does not by itself perform all deployment, camera, preparation and objective initialization.

[Back to index](#function-index)

<a id="call-mapreload"></a>
### MapReload

`MapReload()`

Reloads the map during restoration after a temporary scene/tutorial.

**Arguments:** none.

**Returns:** 1.

**Usage:** Keep the original lifecycle around this call; it is not a stand-alone chapter reset.

[Back to index](#function-index)

<a id="call-mapupdate"></a>
### MapUpdate

`MapUpdate()`

Requests a map-state update after changes/restoration.

**Arguments:** none.

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Keep the original lifecycle around this call; it is not a stand-alone chapter reset.

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

Reads the current action/event's acting unit.

**Arguments:** none.

**Returns:** Map coordinate for EventGetX/Y; unit reference for MindGetMe/Target.

**Usage:** Meaning depends on an active event/action context. Do not assume a turn event provides the same actor/target as a talk, combat or visit.

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

Reads the current action/event's target unit.

**Arguments:** none.

**Returns:** Map coordinate for EventGetX/Y; unit reference for MindGetMe/Target.

**Usage:** Meaning depends on an active event/action context. Do not assume a turn event provides the same actor/target as a talk, combat or visit.

[Back to index](#function-index)

<a id="call-movieplay"></a>
### MoviePlay

`MoviePlay(movie)`

Plays a named movie resource.

| Argument | Meaning and restrictions |
|---|---|
| `movie` | Movie resource string used by the existing game's movie loader; use a verified resource name. |

**Returns:** Not specified; do not use this result as a condition.

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

Tests the internal difficulty ID for Normal or Easy (ID 0 or 3).

**Arguments:** none.

**Returns:** Boolean predicate.

**Usage:** Internal labels must not be assumed to match every region's menu labels. NormalOnly and Easy are separate unregistered names.

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

Restores the previously copied map-camera state through the normal camera transition.

**Arguments:** none.

**Returns:** 1.

**Usage:** Preserve the full create/copy/start/wait/restore lifecycle from a matching scene.

[Back to index](#function-index)

<a id="call-persongetyelllevel"></a>
### PersonGetYellLevel

`PersonGetYellLevel(pid1, pid2)`

Gets the support rank for a mutually registered support pair.

| Argument | Meaning and restrictions |
|---|---|
| `pid1` | First partner's PID. |
| `pid2` | Second partner's PID. |

**Returns:** 0–3 support rank; -1 if they are not registered partners on both sides.

[Back to index](#function-index)

<a id="call-personsetyelllevel"></a>
### PersonSetYellLevel

`PersonSetYellLevel(pid1, pid2, stage)`

Sets both partners' support points to a selected threshold. This is not simply 'set displayed rank to n'.

| Argument | Meaning and restrictions |
|---|---|
| `pid1` | First partner's PID. |
| `pid2` | Second partner's PID. |
| `stage` | 0 = C threshold (C conversation available); 1 = B threshold; 2 = A threshold; 3 = A threshold + 1 (completed A rank). |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Pair eligibility and support limits still matter; do not use a nonexistent pair.

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

Queries existence of a named engine process; tutorial helpers use this to wait for tokens/actors.

| Argument | Meaning and restrictions |
|---|---|
| `process_name` | Exact engine process name, for example E_PadActor or E_TurnToken. |

**Returns:** Predicate used in yield loops.

**Usage:** A process name is not a .fe9s function name.

[Back to index](#function-index)

<a id="call-prockill"></a>
### ProcKill

`ProcKill(process_name)`

Requests termination of a named engine process.

| Argument | Meaning and restrictions |
|---|---|
| `process_name` | Exact process name, for example E_Popup in TutorialInit. |

**Returns:** 0.

**Usage:** Destroying a process can invalidate a wait or scene lifecycle; use only with an understood owner.

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

Builds the named rectangle/UI resource used for scene overlays.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | Existing RID_... rectangle/UI resource identifier; must be built or otherwise available for mutation. |

**Returns:** 0.

**Usage:** Resource lifecycle and child ownership require the matching original scene pattern.

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
| `property` | 0 = X; 1 = Y; 5 = horizontal scale; 6 = vertical scale; 7 also reads horizontal scale. Other properties depend on the rectangle type. |

**Returns:** Property value, or 0 if the rectangle is absent. Scale is the raw factor: 100% reads as 1, and 50% truncates to 0.

**Usage:** RectSet takes scale percentages, while RectGet returns the raw factor. Do not round-trip percentage values through this getter.

[Back to index](#function-index)

<a id="call-rectkill"></a>
### RectKill

`RectKill(rect_id)`

Kills/removes the named rectangle/UI instance.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | Existing RID_... rectangle/UI resource identifier; must be built or otherwise available for mutation. |

**Returns:** 0.

**Usage:** Resource lifecycle and child ownership require the matching original scene pattern.

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

Preloads a named rectangle/UI resource before use.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | Existing RID_... rectangle/UI resource identifier; must be built or otherwise available for mutation. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Resource lifecycle and child ownership require the matching original scene pattern.

[Back to index](#function-index)

<a id="call-rectset"></a>
### RectSet

`RectSet(rect_id, property, value)`

Sets a rectangle property immediately.

| Argument | Meaning and restrictions |
|---|---|
| `rect_id` | RID_... identifier of an existing rectangle/UI resource. |
| `property` | 0 = X; 1 = Y; 5 = horizontal scale; 6 = vertical scale; 7 = both scales; 9 = fade/opacity byte. Keep other selectors from the matching resource’s existing sequence. |
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

Resumes the previously suspended event flow.

**Arguments:** none.

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Exact nesting/scheduling semantics remain native. Follow the complete shared helper sequence, not an isolated call.

[Back to index](#function-index)

<a id="call-roofclose"></a>
### RoofClose

`RoofClose(x, y)`

Runs the roof-closing operation at a location.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-roofopen"></a>
### RoofOpen

`RoofOpen(x, y)`

Runs the roof-opening operation at a location.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-sfxplay"></a>
### SFXPlay

`SFXPlay(sfx_id)`

Plays a named sound effect.

| Argument | Meaning and restrictions |
|---|---|
| `sfx_id` | Existing sound-effect ID, commonly SFX_...; not a BGM channel or audio filename. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Track ownership, interruption and exact native return behavior are not implied by the call's name.

[Back to index](#function-index)

<a id="call-sallyaddbygroup"></a>
### SallyAddByGroup

`SallyAddByGroup(group)`

Adds preparation/deployment placement from a group.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** 1.

**Usage:** This takes a section/group name, not a PID. Persistent roster effects depend on the group's records and surrounding flow.

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

Sets preparation/deployment placement from a group.

| Argument | Meaning and restrictions |
|---|---|
| `group` | Existing named deployment section. This call does not create the section or its unit records. |

**Returns:** 1.

**Usage:** This takes a section/group name, not a PID. Persistent roster effects depend on the group's records and surrounding flow.

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

`SetEventCameraAt(time, a, b, c)`

Adds or configures an event-camera target/position keyframe.

| Argument | Meaning and restrictions |
|---|---|
| `time` | Keyframe timing parameter, conventionally milliseconds in scene sequences; preserve ordering. |
| `a` | First target/position component; depends on camera precision/convention. |
| `b` | Second target/position component; axis semantics not established here. |
| `c` | Third target/position component; do not equate these blindly to tile X/Y/Z. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-seteventcameraprec"></a>
### SetEventCameraPrec

`SetEventCameraPrec(precision)`

Selects event-camera coordinate precision used by subsequent keyframes.

| Argument | Meaning and restrictions |
|---|---|
| `precision` | Precision/scaling mode. Original scene code commonly switches between 1 and 100; full conversion formula is not established here. |

**Returns:** 1.

[Back to index](#function-index)

<a id="call-seteventcamerarot"></a>
### SetEventCameraRot

`SetEventCameraRot(time, a, b, c)`

Adds or configures an event-camera rotation keyframe.

| Argument | Meaning and restrictions |
|---|---|
| `time` | Keyframe timing parameter, conventionally milliseconds in scene sequences; preserve ordering. |
| `a` | First rotation component; depends on camera precision/convention. |
| `b` | Second rotation component; axis semantics not established here. |
| `c` | Third rotation component; do not equate these blindly to tile X/Y/Z. |

**Returns:** 1.

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

`SetMapCamera(camera_a, camera_b, camera_c)`

Transitions the map camera using its three native camera parameters.

| Argument | Meaning and restrictions |
|---|---|
| `camera_a` | First camera parameter; exact axis/angle convention not verified. |
| `camera_b` | Second camera parameter; exact axis/angle convention not verified. |
| `camera_c` | Third camera parameter; exact distance/scale convention not verified. |

**Returns:** 1.

**Usage:** These are camera parameters, not three map-tile coordinates.

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

`SetShooter(x, y, variant, iid)`

Adds a ballista/shooter terrain entry initialized from an item definition.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map tile X coordinate, including the border; passed as a signed byte. |
| `y` | Map tile Y coordinate, including the border; passed as a signed byte. |
| `variant` | Shooter terrain subtype; preserve the variant used by the matching map object. |
| `iid` | Valid shooter IID_... item. Initializes the shooter’s item index and remaining uses. |

**Returns:** 1.

**Usage:** Requires matching map geometry. An invalid item name is unsafe.

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

Writes terrain at a map tile through the runtime terrain API.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |
| `terrain` | Terrain selector/code. Match a decoded terrain type; this does not rebuild map geometry. |

**Returns:** 0.

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

Totals spent ballista shots inside the active map bounds using five shots as the initial baseline.

**Arguments:** none.

**Returns:** Sum of (5 − remaining uses) for each shooter terrain entry.

**Usage:** This is spent ammunition, not remaining ammunition. Custom shooters with more than five uses can produce negative contributions.

[Back to index](#function-index)

<a id="call-showmapcursor"></a>
### ShowMapCursor

`ShowMapCursor(x, y)`

Shows the map cursor at a tile.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** 1.

**Usage:** Return encodings for map queries and full state-change side effects are not decoded here.

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

`StartEventCamera(mode)`

Starts the configured event-camera sequence.

| Argument | Meaning and restrictions |
|---|---|
| `mode` | Playback mode; values such as 0, 2 and 3 occur. Their complete behavior table remains unresolved. |

**Returns:** 1.

**Usage:** Schedule keyframes first, then use EventCameraWait where the scene needs completion.

[Back to index](#function-index)

<a id="call-suspendevent"></a>
### SuspendEvent

`SuspendEvent()`

Suspends the current event flow for tutorial/scene transfer.

**Arguments:** none.

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Exact nesting/scheduling semantics remain native. Follow the complete shared helper sequence, not an isolated call.

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

Runs the treasure-box opening operation at a location.

| Argument | Meaning and restrictions |
|---|---|
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.

[Back to index](#function-index)

<a id="call-ttpmentry"></a>
### TTPMEntry

`TTPMEntry(path)`

Stores a terrain-motion path in the first free path slot.

| Argument | Meaning and restrictions |
|---|---|
| `path` | Persistent direction string: 2 = down, 4 = left, 6 = right, 8 = up, one tile per character. Example: "66222". Stored by reference, not copied. |

**Returns:** Allocated slot index 0–31; -1 if the table is full.

**Usage:** Pass the returned slot to SetRock. Use a string literal that remains loaded while the rock exists.

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

Plays an event message from the loaded message resources. Message commands can suspend dialogue for event-script work.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a currently loaded message resource; not literal dialogue text. |

**Returns:** 1.

**Usage:** A message containing $H needs a matching TalkResume sequence. A message ID does not supply portraits or continuation state by itself.

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

Queries whether a conversation remains active; tutorial helpers yield while this is true.

**Arguments:** none.

**Returns:** Predicate consumed by wait loops.

[Back to index](#function-index)

<a id="call-talkresume"></a>
### TalkResume

`TalkResume()`

Resumes the current suspended event conversation rather than starting a new message.

**Arguments:** none.

**Returns:** 1.

**Usage:** Use only with an active continuation; preserve the corresponding $H points in message text.

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

`TutPadActor(action)`

Calls _pa(action), then yields while process "E_PadActor" exists.

| Argument | Meaning and restrictions |
|---|---|
| `action` | Tutorial input/action string passed unchanged to _pa; its command grammar is not fully decoded. |

**Returns:** 0 (implicit return); do not interpret this as failure.

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

**Usage:** Exact token event semantics remain in the native routine; the helper's polling sequence is confirmed.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutwaitfornextturn"></a>
### TutWaitForNextTurn

`TutWaitForNextTurn()`

Calls turntk(), then yields while process "E_TurnToken" exists.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** Exact token event semantics remain in the native routine; the helper's polling sequence is confirmed.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutwaitfornextturnafter"></a>
### TutWaitForNextTurnAfter

`TutWaitForNextTurnAfter()`

Calls turnatk(), then yields while process "E_TurnAToken" exists.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** Exact token event semantics remain in the native routine; the helper's polling sequence is confirmed.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutwaitm"></a>
### TutWaitM

`TutWaitM(duration_ms)`

Calls GameBind, computes duration_ms * 60 / 1000 with integer arithmetic, yields that many iterations, then GameUnbind.

| Argument | Meaning and restrictions |
|---|---|
| `duration_ms` | Milliseconds converted using the helper's fixed factor 60/1000; this is not inferred from emulator frame rate. |

**Returns:** 0 (implicit return); do not interpret this as failure.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutorialbasescreate"></a>
### TutorialBasesCreate

`TutorialBasesCreate()`

Called by TutBasesCreate after E_BMapPlph appears, followed by a wait on E_BasesToken.

**Arguments:** none.

**Returns:** 1.

**Usage:** The caller sequence is established; full native side effects remain unresolved.

[Back to index](#function-index)

<a id="call-tutorialbasesdelete"></a>
### TutorialBasesDelete

`TutorialBasesDelete()`

Native teardown called directly by TutBasesDelete.

**Arguments:** none.

**Returns:** 1.

**Usage:** The caller sequence is established; full native side effects remain unresolved.

[Back to index](#function-index)

<a id="call-tutorialcall"></a>
### TutorialCall

`TutorialCall(entry_name)`

Invokes the named tutorial entry in the shared tutorial-load sequence.

| Argument | Meaning and restrictions |
|---|---|
| `entry_name` | Function name in the loaded tutorial module; for example tut_02_Visit. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** The module must already be loaded; this is not a Python callable object.

[Back to index](#function-index)

<a id="call-tutorialdialog"></a>
### TutorialDialog

`TutorialDialog(message_id)`

Calls td(message_id), yields once, then tde().

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a currently loaded message resource; not literal dialogue text. |

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** The wrapper does not explicitly poll for a result; do not infer td/tde internals from this sequence.

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

Final native step in ComebackFunc, after event suspension, map teardown and external Startup.

**Arguments:** none.

**Returns:** Not specified; do not use this result as a condition.

**Usage:** The caller sequence is established; full native side effects remain unresolved.

[Back to index](#function-index)

<a id="call-tutorialresumeout"></a>
### TutorialResumeOut

`TutorialResumeOut()`

MapFree; yield; AllPop; MapReload; UnitDispReload; external Startup; MapUpdate; Fade(2,266); FadeWait.

**Arguments:** none.

**Returns:** 0 (implicit return); do not interpret this as failure.

**Usage:** Re-enters chapter Startup during restoration, so flag registration order must remain stable.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-tutorialsallycreate"></a>
### TutorialSallyCreate

`TutorialSallyCreate()`

Called by TutSallyCreate after E_BMapPlph appears, followed by a wait on E_SallyToken.

**Arguments:** none.

**Returns:** 1.

**Usage:** The caller sequence is established; full native side effects remain unresolved.

[Back to index](#function-index)

<a id="call-tutorialsallydelete"></a>
### TutorialSallyDelete

`TutorialSallyDelete()`

Native teardown called directly by TutSallyDelete.

**Arguments:** none.

**Returns:** 1.

**Usage:** The caller sequence is established; full native side effects remain unresolved.

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

Adds an item through the native inventory operation.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `item_id` | Existing IID_... item ID. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Capacity handling, result code and whether a popup appears must not be inferred; UnitGetItemShowing is the separate presentation helper.

[Back to index](#function-index)

<a id="call-unitaddskill"></a>
### UnitAddSkill

`UnitAddSkill(unit, skill_id)`

Adds the indicated skill through the runtime unit API.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `skill_id` | Existing SID_... skill ID; not a raw status mask. |

**Returns:** Not specified; do not use this result as a condition.

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

Breaks a unit's linked/pair relationship through the native operation.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Do not infer a full persistent roster or item-data change from a visual scene operation.

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

Runs the unit's class-change operation using its existing class/promotion data.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Do not infer a full persistent roster or item-data change from a visual scene operation.

[Back to index](#function-index)

<a id="call-unitclrskill"></a>
### UnitClrSkill

`UnitClrSkill(unit, skill_id)`

Clears the indicated skill through the runtime unit API.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `skill_id` | Existing SID_... skill ID; not a raw status mask. |

**Returns:** Not specified; do not use this result as a condition.

[Back to index](#function-index)

<a id="call-unitclrstatus"></a>
### UnitClrStatus

`UnitClrStatus(unit, mask)`

Clears selected status-mask bits from a unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `mask` | HP/EXP value or status bitmask as appropriate. Use decoded bits; an arbitrary integer is not a named status. |

**Returns:** Not specified; do not use this result as a condition.

[Back to index](#function-index)

<a id="call-unitdead"></a>
### UnitDead

`UnitDead(unit)`

Runs the native death operation; its complete consequences and trigger ordering require verification.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Do not infer a full persistent roster or item-data change from a visual scene operation.

[Back to index](#function-index)

<a id="call-unitdelitem"></a>
### UnitDelItem

`UnitDelItem(unit, item_index)`

Deletes an inventory entry selected by the native index.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `item_index` | Native inventory index. The shared four-weapon storage helper passes 0–3; do not assume these are IID strings or every inventory family's valid range. |

**Returns:** Not specified; do not use this result as a condition.

[Back to index](#function-index)

<a id="call-unitdispreload"></a>
### UnitDispReload

`UnitDispReload()`

Reloads unit display resources during scene restoration.

**Arguments:** none.

**Returns:** 1.

**Usage:** Keep the original lifecycle around this call; it is not a stand-alone chapter reset.

[Back to index](#function-index)

<a id="call-unitdontmovesally"></a>
### UnitDontMoveSally

`UnitDontMoveSally(unit)`

Applies the fixed-deployment-position operation during preparations.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Do not infer a full persistent roster or item-data change from a visual scene operation.

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

`UnitEscape(unit, mode)`

Removes/escapes a unit through the native escape operation.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `mode` | Escape-operation mode. The shared UnitEscapeByPID helper always passes 0; other meanings remain unresolved. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Do not assume escape means permanent death or removal from the campaign roster.

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

Enables the unit fade-in setting used around subsequent placement/movement.

**Arguments:** none.

**Returns:** 1.

**Usage:** These are shared scene settings with no unit argument; preserve the matching restore call.

[Back to index](#function-index)

<a id="call-unitfadeoff"></a>
### UnitFadeOff

`UnitFadeOff()`

Clears the shared unit-fade setting.

**Arguments:** none.

**Returns:** 1.

**Usage:** These are shared scene settings with no unit argument; preserve the matching restore call.

[Back to index](#function-index)

<a id="call-unitfadeout"></a>
### UnitFadeOut

`UnitFadeOut()`

Enables the unit fade-out setting used around subsequent movement/escape.

**Arguments:** none.

**Returns:** 1.

**Usage:** These are shared scene settings with no unit argument; preserve the matching restore call.

[Back to index](#function-index)

<a id="call-unitfocus"></a>
### UnitFocus

`UnitFocus(unit)`

Focuses the camera on a runtime unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** 1.

**Usage:** UnitFocusByPID instead computes the deployed unit's tile and invokes Focus.

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

Disables the native automatic unit-focus setting.

**Arguments:** none.

**Returns:** 1.

**Usage:** These are shared scene settings with no unit argument; preserve the matching restore call.

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

Enables the native automatic unit-focus setting.

**Arguments:** none.

**Returns:** 1.

**Usage:** These are shared scene settings with no unit argument; preserve the matching restore call.

[Back to index](#function-index)

<a id="call-unitforcedsally"></a>
### UnitForcedSally

`UnitForcedSally(unit)`

Marks a unit for forced deployment.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Do not infer a full persistent roster or item-data change from a visual scene operation.

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

Reads the actor's runtime force-list ID.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** Force ID; see UnitTransferToForce's force argument.

[Back to index](#function-index)

<a id="call-unitgethp"></a>
### UnitGetHP

`UnitGetHP(unit)`

Reads the unit's current HP.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** The current HP; null-input behavior and numeric bounds are not established here.

[Back to index](#function-index)

<a id="call-unitgetitemcount"></a>
### UnitGetItemCount

`UnitGetItemCount(unit)`

Reads the unit's item inventory count.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** The item inventory count; null-input behavior and numeric bounds are not established here.

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

**Usage:** No explicit null check in this helper. Native _gi handles the reward operation; full-inventory behavior/return contract is not decoded by the wrapper.

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

Reads the unit's maximum HP.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** The maximum HP; null-input behavior and numeric bounds are not established here.

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

Advances from a unit to the next member in the current list iteration.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** Next unit reference; loops check for 0.

**Usage:** Mutating force membership while iterating can change traversal; do not assume the previous next pointer remains valid.

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

Reads the unit's status bitmask.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** The status bitmask; null-input behavior and numeric bounds are not established here.

[Back to index](#function-index)

<a id="call-unitgetweaponcount"></a>
### UnitGetWeaponCount

`UnitGetWeaponCount(unit)`

Reads the unit's weapon inventory count.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** The weapon inventory count; null-input behavior and numeric bounds are not established here.

[Back to index](#function-index)

<a id="call-unitgetx"></a>
### UnitGetX

`UnitGetX(unit)`

Reads the unit's map-grid X coordinate.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** The map-grid X coordinate; null-input behavior and numeric bounds are not established here.

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

Reads the unit's map-grid Y coordinate.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** The map-grid Y coordinate; null-input behavior and numeric bounds are not established here.

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

`UnitItemGetValuation(unit, item_index)`

Returns the valuation used by the shared inventory-to-storage selection helper.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `item_index` | Native inventory index. The shared four-weapon storage helper passes 0–3; do not assume these are IID strings or every inventory family's valid range. |

**Returns:** Valuation number used for comparisons.

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

`UnitItemSendtoWarehouse(unit, item_index)`

Transfers a selected inventory entry to storage.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `item_index` | Native inventory index. The shared four-weapon storage helper passes 0–3; do not assume these are IID strings or every inventory family's valid range. |

**Returns:** Not specified; do not use this result as a condition.

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

`UnitItemSetDrop(unit, item_index)`

Marks an inventory entry for dropping through the native item API.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `item_index` | Native inventory index. The shared four-weapon storage helper passes 0–3; do not assume these are IID strings or every inventory family's valid range. |

**Returns:** Not specified; do not use this result as a condition.

[Back to index](#function-index)

<a id="call-unitmovedir"></a>
### UnitMoveDir

`UnitMoveDir(unit, path)`

Schedules movement using a direction-command string.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `path` | Direction-command string, for example repeated numeric codes. It is not a coordinate tuple; preserve a verified path syntax. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Use UnitMoveWait when dependent scene work must follow arrival.

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

**Usage:** Does not wait for completion; use the appropriate movement wait.

Requires the shared `startup.cmb` helpers to be loaded.

[Back to index](#function-index)

<a id="call-unitmovepos"></a>
### UnitMovePos

`UnitMovePos(unit, x, y)`

Schedules actor movement toward a map position.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Existing handler research identifies an unoccupied-tile search: the final tile may differ when the requested destination is occupied. Movement completion is separate; use UnitMoveWait.

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

**Usage:** Does not wait for completion; use the appropriate movement wait.

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

Waits for the native unit-motion completion condition.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact process coverage, event-skip paths and timeout behavior are not fully documented; no timeout argument is exposed.

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

`UnitQueryJID(unit, id)`

Tests the actor against a class ID.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `id` | Existing JID_... ID string. |

**Returns:** Predicate used by script conditions; exact treatment of aliases/subclasses is not established.

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

`UnitQueryPID(unit, id)`

Tests the actor against a character ID.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `id` | Existing PID_... ID string. |

**Returns:** Predicate used by script conditions; exact treatment of aliases/subclasses is not established.

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

Requests a unit facing/rotation change.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `direction` | Engine direction code; retain a tested value. The rotation helper maps toward negative X to 1, positive X to 2, positive Y to 4 and negative Y to 8, combining bits for diagonals. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Shared UnitSetPosDir passes duration 0 for an immediate facing change.

[Back to index](#function-index)

<a id="call-unitrotatebypid"></a>
### UnitRotateByPID

`UnitRotateByPID(pid, direction, duration_ms)`

Resolves a deployed actor using UnitCheckExistsByPID2, then calls UnitRotate with the remaining arguments.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `direction` | Engine direction code; retain a tested value. The rotation helper maps toward negative X to 1, positive X to 2, positive Y to 4 and negative Y to 8, combining bits for diagonals. |
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** Actor reference if scheduled; 0 if unavailable.

**Usage:** Does not wait for completion; use the appropriate movement wait.

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

Searches a unit's inventory for an item ID.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `item_id` | IID_... string to find. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Exact not-found sentinel and index encoding are not established here.

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

Requests the accessory-away state.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Do not infer a full persistent roster or item-data change from a visual scene operation.

[Back to index](#function-index)

<a id="call-unitsetcpattackseq"></a>
### UnitSetCpAttackSeq

`UnitSetCpAttackSeq(unit, sequence)`

Sets the actor's attack AI sequence.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `sequence` | Existing SEQ_... behavior symbol. Defining a new string does not implement a new AI algorithm. |

**Returns:** Not specified; do not use this result as a condition.

[Back to index](#function-index)

<a id="call-unitsetcphealseq"></a>
### UnitSetCpHealSeq

`UnitSetCpHealSeq(unit, resource_id)`

Changes the unit’s healing AI sequence by resource name.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `resource_id` | Existing name of a healing AI sequence resource. |

**Returns:** 1 for a valid unit; 0 if the handle is zero or its slot has no character.

**Usage:** If the resource name is not found, the old setting remains unchanged even though the call returns 1.

[Back to index](#function-index)

<a id="call-unitsetcpmtypeid"></a>
### UnitSetCpMTypeID

`UnitSetCpMTypeID(unit, resource_id)`

Changes the unit’s MTYPE AI table by resource name.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric unit handle from UnitGetByPID or another unit lookup. Zero means no unit; this is not a PID string or a memory address. |
| `resource_id` | Existing name of a MTYPE AI table resource. |

**Returns:** 1 for a valid unit; 0 if the handle is zero or its slot has no character.

**Usage:** If the resource name is not found, the old setting remains unchanged even though the call returns 1.

[Back to index](#function-index)

<a id="call-unitsetcpmoveseq"></a>
### UnitSetCpMoveSeq

`UnitSetCpMoveSeq(unit, sequence)`

Sets the actor's movement AI sequence.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `sequence` | Existing SEQ_... behavior symbol. Defining a new string does not implement a new AI algorithm. |

**Returns:** Not specified; do not use this result as a condition.

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

`UnitSetEXP(unit, value)`

Sets the unit's experience value; automatic level-up behavior is not established.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `value` | HP/EXP value or status bitmask as appropriate. Use decoded bits; an arbitrary integer is not a named status. |

**Returns:** 0.

[Back to index](#function-index)

<a id="call-unitsetequip"></a>
### UnitSetEquip

`UnitSetEquip(unit, item_index)`

Selects an inventory entry for equipping.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `item_index` | Native inventory index. The shared four-weapon storage helper passes 0–3; do not assume these are IID strings or every inventory family's valid range. |

**Returns:** Not specified; do not use this result as a condition.

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

`UnitSetHP(unit, value)`

Sets current HP; clamping and death dispatch are not established, so this is not documented as equivalent to killing the unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `value` | HP/EXP value or status bitmask as appropriate. Use decoded bits; an arbitrary integer is not a named status. |

**Returns:** 0.

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

Positions an actor on the map.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Existing handler research identifies an unoccupied-tile search: the final tile may differ when the requested destination is occupied. Movement completion is separate; use UnitMoveWait.

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

Applies status-mask bits to a unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `mask` | HP/EXP value or status bitmask as appropriate. Use decoded bits; an arbitrary integer is not a named status. |

**Returns:** Not specified; do not use this result as a condition.

[Back to index](#function-index)

<a id="call-unitsetweaponaway"></a>
### UnitSetWeaponAway

`UnitSetWeaponAway(unit)`

Requests the weapon-away state used by scene helpers.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Do not infer a full persistent roster or item-data change from a visual scene operation.

[Back to index](#function-index)

<a id="call-unitsetweaponawaybypid"></a>
### UnitSetWeaponAwayByPID

`UnitSetWeaponAwayByPID(pid)`

Resolves a deployed actor and returns UnitSetWeaponAway(actor).

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |

**Returns:** -2 if unavailable; otherwise the native result (not decoded here).

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

Moves an actor to the specified runtime force list. The destination changes runtime membership; a persistent recruitment may need additional chapter/story setup.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `force` | Runtime force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 player reserve, 6 inactive/death-flagged, 7 special inactive (less precisely decoded). Not a phase enum. |

**Returns:** Not specified; do not use this result as a condition.

[Back to index](#function-index)

<a id="call-unittransfertoforcebypid"></a>
### UnitTransferToForceByPID

`UnitTransferToForceByPID(pid, force)`

Resolves the actor, applies the UnitCheckLiveByPID-equivalent null/status-0x08/force-6 test, then calls UnitTransferToForce.

| Argument | Meaning and restrictions |
|---|---|
| `pid` | Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor. |
| `force` | Runtime force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 player reserve, 6 inactive/death-flagged, 7 special inactive (less precisely decoded). Not a phase enum. |

**Returns:** 0 if missing/not live under that test; 1 after transfer.

**Usage:** Unlike movement wrappers, does not require current force 0–3; live reserve actors can pass.

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

Tests the indicated skill on the unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `skill_id` | Existing SID_... skill ID; not a raw status mask. |

**Returns:** Predicate for UnitTstSkill; mutation return semantics not established.

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

Runs the native warp-out operation for a unit.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Do not infer a full persistent roster or item-data change from a visual scene operation.

[Back to index](#function-index)

<a id="call-unitsinitialize"></a>
### UnitsInitialize

`UnitsInitialize()`

Initializes the runtime unit state used by chapter/scene setup.

**Arguments:** none.

**Returns:** 1.

**Usage:** Keep the original lifecycle around this call; it is not a stand-alone chapter reset.

[Back to index](#function-index)

<a id="call-unitspop"></a>
### UnitsPop

`UnitsPop()`

Restores the pushed unit state.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact contents/depth of the save stack are not fully decoded. Preserve matched push/pop ownership.

[Back to index](#function-index)

<a id="call-unitspopwithoutmap"></a>
### UnitsPopWithoutMap

`UnitsPopWithoutMap()`

Uses the unit-state restoration variant without the normal map operation.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact contents/depth of the save stack are not fully decoded. Preserve matched push/pop ownership.

[Back to index](#function-index)

<a id="call-unitspush"></a>
### UnitsPush

`UnitsPush()`

Pushes unit state for later restoration.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact contents/depth of the save stack are not fully decoded. Preserve matched push/pop ownership.

[Back to index](#function-index)

<a id="call-unitspush-uninitialize"></a>
### UnitsPush_Uninitialize

`UnitsPush_Uninitialize()`

Pushes unit state and performs the uninitializing variant for a temporary scene.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact contents/depth of the save stack are not fully decoded. Preserve matched push/pop ownership.

[Back to index](#function-index)

<a id="call-visitin"></a>
### VisitIn

`VisitIn(unit, x, y)`

Runs the VisitIn unit/building transition used by location events.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** 1.

**Usage:** Original visits preserve the actor from MindGetMe and pass EventGetX/Y. This is not the reward call.

[Back to index](#function-index)

<a id="call-visitout"></a>
### VisitOut

`VisitOut(unit, x, y)`

Runs the VisitOut unit/building transition used by location events.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `x` | Map-grid X coordinate, including the map's border. |
| `y` | Map-grid Y coordinate, including the map's border. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Original visits preserve the actor from MindGetMe and pass EventGetX/Y. This is not the reward call.

[Back to index](#function-index)

<a id="call-waitf"></a>
### WaitF

`WaitF(frames)`

Delays event sequencing by a frame count.

| Argument | Meaning and restrictions |
|---|---|
| `frames` | Number of frames, not milliseconds. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Do not assume the operation also waits for an unrelated movement/camera process.

[Back to index](#function-index)

<a id="call-waitm"></a>
### WaitM

`WaitM(duration_ms)`

Delays event sequencing for a millisecond duration in ordinary scene code.

| Argument | Meaning and restrictions |
|---|---|
| `duration_ms` | Duration in milliseconds. Use the matching completion wait when synchronizing animation. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Timing/skip behavior is native; use an operation-specific wait for completion of movement or fades.

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

Tutorial state initialization step called by TutorialInit after killing E_Popup and before Startup.

**Arguments:** none.

**Returns:** 1.

**Usage:** The caller sequence is established; full native side effects remain unresolved.

[Back to index](#function-index)

<a id="call--cmb-mess-load"></a>
### _cmb_mess_load

`_cmb_mess_load(script_path, message_path)`

Loads the script/message pair used by the common tutorial-entry sequence.

| Argument | Meaning and restrictions |
|---|---|
| `script_path` | Tutorial CMB path forwarded from TutEntryCommon. |
| `message_path` | Message resource path; the shared helper supplies mess/tut.m. |

**Returns:** 1.

**Usage:** Underlying ownership and error behavior still require native inspection.

[Back to index](#function-index)

<a id="call--gi"></a>
### _gi

`_gi(unit, item_id)`

Native operation invoked by UnitGetItemShowing to deliver/show an item reward.

| Argument | Meaning and restrictions |
|---|---|
| `unit` | Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check. |
| `item_id` | IID item ID forwarded unchanged from the reward helper. |

**Returns:** Not specified; do not use this result as a condition.

**Usage:** The caller establishes recipient/item roles. Inventory overflow, popup lifetime and native result remain undecoded.

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

First native stage of MapFree, before its mandatory yield.

**Arguments:** none.

**Returns:** Not specified; do not use this result as a condition.

**Usage:** The precise resource subset released by this stage is not decoded.

[Back to index](#function-index)

<a id="call--mf2"></a>
### _mf2

`_mf2()`

Second native stage of MapFree, after its yield.

**Arguments:** none.

**Returns:** 1.

**Usage:** Use MapFree for the established two-stage sequence.

[Back to index](#function-index)

<a id="call--pa"></a>
### _pa

`_pa(action)`

Starts the tutorial actor/input operation whose E_PadActor process is polled by TutPadActor.

| Argument | Meaning and restrictions |
|---|---|
| `action` | Command string from TutPadActor; command grammar remains unresolved. |

**Returns:** 1.

**Usage:** Use the wrapper if you need its explicit process wait.

[Back to index](#function-index)

<a id="call--pldone"></a>
### _pldone

`_pldone()`

Readiness predicate used by PreLoadWait; a zero result keeps the helper yielding.

**Arguments:** none.

**Returns:** Not specified; do not use this result as a condition.

**Usage:** Which resource queues this covers is not established.

[Back to index](#function-index)

<a id="call--seqini"></a>
### _seqini

`_seqini()`

Tutorial sequence initialization step called by TutorialInit before killing E_Popup.

**Arguments:** none.

**Returns:** 1.

**Usage:** The caller sequence is established; full native side effects remain unresolved.

[Back to index](#function-index)

<a id="call--tr"></a>
### _tr

`_tr()`

Resumes the tutorial conversation operation used by TutTalkResume.

**Arguments:** none.

**Returns:** 1.

**Usage:** The helper wraps it in GameBind/GameUnbind and waits on TalkExist.

[Back to index](#function-index)

<a id="call--tt"></a>
### _tt

`_tt(message_id)`

Starts the tutorial conversation operation used inside GameBind/GameUnbind by TutTalkEvent.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a currently loaded message resource; not literal dialogue text. |

**Returns:** 1.

**Usage:** The helper waits on TalkExist afterward; do not assume equivalence to ordinary TalkEvent on all skip paths.

[Back to index](#function-index)

<a id="call-clr"></a>
### clr

`clr(flag_name)`

Looks up a registered named flag and clears its bit. An unregistered name is a silent no-op.

| Argument | Meaning and restrictions |
|---|---|
| `flag_name` | Exact registered flag name. Prefixes such as G_ do not themselves allocate global storage. |

**Returns:** 0.

**Usage:** Does not register or allocate the flag.

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

Looks up a registered named flag and reads its bit.

| Argument | Meaning and restrictions |
|---|---|
| `flag_name` | Exact registered flag name. Prefixes such as G_ do not themselves allocate global storage. |

**Returns:** 0 if clear or unregistered; nonzero if set.

[Back to index](#function-index)

<a id="call-global"></a>
### global

`global(flag_name)`

Registers a campaign flag in the lowest empty flag-table slot and clears its bit. Original global registration occurs at boot.

| Argument | Meaning and restrictions |
|---|---|
| `flag_name` | Exact registered flag name. Prefixes such as G_ do not themselves allocate global storage. |

**Returns:** 1.

**Usage:** Call from .fe9s as extern("global", "name") because global is a language keyword. This named flag API is distinct from global name @ slot (VM word storage). Preserve registration order for save compatibility.

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

Reports the screen-fade busy state consumed by FadeWait.

**Arguments:** none.

**Returns:** Nonzero while the helper should keep yielding.

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

Registers a chapter flag in the highest empty slot of the shared 96-slot flag table. It leaves that slot's bit unchanged.

| Argument | Meaning and restrictions |
|---|---|
| `flag_name` | Exact registered flag name. Prefixes such as G_ do not themselves allocate global storage. |

**Returns:** 1.

**Usage:** Append registrations after existing ones: saves store bits by slot, not names. Keep one empty slot for cleanup. Register during chapter setup, not each turn.

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

Looks up a registered named flag and sets its bit. An unregistered name is a silent no-op.

| Argument | Meaning and restrictions |
|---|---|
| `flag_name` | Exact registered flag name. Prefixes such as G_ do not themselves allocate global storage. |

**Returns:** 0.

**Usage:** Does not register or allocate the flag.

[Back to index](#function-index)

<a id="call-taikitk"></a>
### taikitk

`taikitk()`

Starts the native step whose E_TaikiToken process is polled by TutWaitForNextTaiki.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact triggering event belongs to the native token implementation.

[Back to index](#function-index)

<a id="call-td"></a>
### td

`td(message_id)`

Starts the native tutorial-dialog step used by TutorialDialog.

| Argument | Meaning and restrictions |
|---|---|
| `message_id` | Message ID in a currently loaded message resource; not literal dialogue text. |

**Returns:** 0.

**Usage:** The helper yields once after this call and then calls tde; exact native scheduling/result semantics remain undecoded.

[Back to index](#function-index)

<a id="call-tde"></a>
### tde

`tde()`

Final native step called by TutorialDialog after td and one yield.

**Arguments:** none.

**Returns:** 1.

**Usage:** Whether this closes, joins or otherwise finalizes the dialog is not proven by the caller alone.

[Back to index](#function-index)

<a id="call-turnatk"></a>
### turnatk

`turnatk()`

Starts the native step whose E_TurnAToken process is polled by TutWaitForNextTurnAfter.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact triggering event belongs to the native token implementation.

[Back to index](#function-index)

<a id="call-turntk"></a>
### turntk

`turntk()`

Starts the native step whose E_TurnToken process is polled by TutWaitForNextTurn.

**Arguments:** none.

**Returns:** 1.

**Usage:** Exact triggering event belongs to the native token implementation.

[Back to index](#function-index)
