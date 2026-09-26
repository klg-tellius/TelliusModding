"""Reviewed prose for the generated scripting reference (not compiler metadata).

Each argument is (name, meaning). Unspecified native return contracts stay unknown.
Script-body descriptions establish wrapper control flow, not native internals.
"""

DETAILS = {}
ENGINE = "../../research/MAIN_DOL_NOTES.md#event-script-runtime"
FLAGS = "../../research/EVENT_SCRIPT_GUIDE.md#named-flags"
SUPPORT = "../../research/SUPPORT_NOTES.md"
CHAPTER = "../../research/CHAPTER_DATA_NOTES.md"
UNIT = ("unit", "Numeric runtime unit handle, such as the result of UnitGetByPID; not a PID string. Supply a valid actor unless this entry explicitly documents a null check.")
PID = ("pid", "Character ID string (PID_...). A character definition alone does not guarantee a loaded/deployed actor.")
X = ("x", "Map-grid X coordinate, including the map's border.")
Y = ("y", "Map-grid Y coordinate, including the map's border.")
MS = ("message_id", "Message ID in a currently loaded message resource; not literal dialogue text.")
GROUP = ("group", "Existing named deployment section. This call does not create the section or its unit records.")
TIME = ("duration_ms", "Duration in milliseconds. Use the matching completion wait when synchronizing animation.")
FORCE = ("force", "Runtime force ID: 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 player reserve, 6 inactive/death-flagged, 7 special inactive (less precisely decoded). Not a phase enum.")
DIR = ("direction", "Engine direction code; retain a tested value. The rotation helper maps toward negative X to 1, positive X to 2, positive Y to 4 and negative Y to 8, combining bits for diagonals.")
BGM = ("bgm_id", "Existing BGM_... track ID; not an audio filename.")
CHANNEL = ("channel", "Music channel. Shared helpers use 0 for map music and 1 for event music; do not assume an unlimited channel range.")
FLAG = ("flag_name", "Exact registered flag name. Prefixes such as G_ do not themselves allocate global storage.")


def add(name, behavior, args=(), returns=None, notes="", evidence="Observed usage", source=ENGINE):
    assert name not in DETAILS, name
    DETAILS[name] = dict(behavior=behavior, args=list(args), returns=returns or "Not specified; do not use this result as a condition.", notes=notes, evidence=evidence, source=source)


def helper(name, behavior, args=(), returns="0 (implicit return); do not interpret this as failure.", notes=""):
    add(name, behavior, args, returns, notes, "Confirmed shared-script control flow", "startup.cmb")


# Contracts already established in the system notes.
add("regist", "Registers a chapter flag in the highest empty slot of the shared 96-slot flag table. It leaves that slot's bit unchanged.", [FLAG], notes="Append registrations after existing ones: saves store bits by slot, not names. Keep one empty slot for cleanup. Register during chapter setup, not each turn.", evidence="Confirmed engine behavior", source=FLAGS)
add("global", "Registers a campaign flag in the lowest empty flag-table slot and clears its bit. Original global registration occurs at boot.", [FLAG], notes='Call from .fe9s as extern("global", "name") because global is a language keyword. This named flag API is distinct from global name @ slot (VM word storage). Preserve registration order for save compatibility.', evidence="Confirmed engine behavior", source=FLAGS)
add("get", "Looks up a registered named flag and reads its bit.", [FLAG], "0 if clear or unregistered; nonzero if set.", evidence="Confirmed engine behavior", source=FLAGS)
for name, action in [("set", "sets"), ("clr", "clears")]:
    add(name, f"Looks up a registered named flag and {action} its bit. An unregistered name is a silent no-op.", [FLAG], notes="Does not register or allocate the flag.", evidence="Confirmed engine behavior", source=FLAGS)
add("CmLoadScript", "Loads a CMB module, appends it to the loaded-module list, fixes offsets and registers its named exports.", [("script_resource", "Script resource argument passed to the loader. Path/resource representation and failure contract require further verification; the catalog's int is only a fallback hint.")], notes="Exports exist only while their module remains registered. Pair module ownership with last-loaded-first-freed ordering.", evidence="Confirmed loader lifecycle")
add("CmFreeScript", "Unregisters and frees the last-loaded module, then unlinks it from the module list.", notes="No name argument: this is LIFO removal, not removal of an arbitrary script.", evidence="Confirmed engine behavior")
add("CmSleepScript", "Marks the selected module sleeping, excludes it from event enumeration and unregisters its named exports.", [("script_name", "Module name; the shared tutorial entry passes an empty string to target the current tail module.")], notes="Sleeping is not freeing. Custom empty/null argument differences are not established beyond the observed empty-string pattern.", evidence="Confirmed lifecycle; empty-string use observed")
add("CmWakeupScripts", "Walks sleeping modules, restores their active marker and re-registers named exports.", evidence="Confirmed engine behavior")
add("GetLanguage", "Returns a hardcoded value in the US executable; it does not read a language setting.", returns="1, always, in this US build.", evidence="Confirmed engine behavior", source="../../research/MAIN_DOL_NOTES.md#language-setting-pal-sram-setter-lead-resolved-as-inert-in-ntsc-u")
for name, value, meaning in [("Normal", "0 or 3", "Normal or Easy"), ("Hard", "1", "Hard"), ("Maniac", "2", "Maniac")]:
    add(name, f"Tests the internal difficulty ID for {meaning} (ID {value}).", returns="Boolean predicate.", notes="Internal labels must not be assumed to match every region's menu labels. NormalOnly and Easy are separate unregistered names.", evidence="Confirmed engine behavior", source="../../research/MAIN_DOL_NOTES.md#current_difficulty_id--fully-resolved-cross-region")
add("GetRank", "Reads the internal difficulty ID.", returns="Internal difficulty value; see Normal/Hard/Maniac for the difficulty mapping.", evidence="Existing accessor research", source="../../research/MAIN_DOL_NOTES.md#current_difficulty_id--fully-resolved-cross-region")
add("UnitTransferToForce", "Moves an actor to the specified runtime force list. The destination changes runtime membership; a persistent recruitment may need additional chapter/story setup.", [UNIT, FORCE], evidence="Confirmed engine behavior", source="../../research/MAIN_DOL_NOTES.md")
add("UnitGetForce", "Reads the actor's runtime force-list ID.", [UNIT], "Force ID; see UnitTransferToForce's force argument.", evidence="Confirmed engine behavior", source="../../research/MAIN_DOL_NOTES.md")
add("PersonGetYellLevel", "Gets the support rank for a mutually registered support pair.", [("pid1", "First partner's PID."), ("pid2", "Second partner's PID.")], "0–3 support rank; -1 if they are not registered partners on both sides.", evidence="Confirmed engine behavior", source=SUPPORT)
add("PersonSetYellLevel", "Sets both partners' support points to a selected threshold. This is not simply 'set displayed rank to n'.", [("pid1", "First partner's PID."), ("pid2", "Second partner's PID."), ("stage", "0 = C threshold (C conversation available); 1 = B threshold; 2 = A threshold; 3 = A threshold + 1 (completed A rank).")], notes="Pair eligibility and support limits still matter; do not use a nonexistent pair.", evidence="Confirmed engine behavior", source=SUPPORT)

# Core scene APIs: useful meanings supported by original call patterns, without
# inventing numeric modes or claiming unexamined native return/null contracts.
add("TalkEvent", "Plays an event message from the loaded message resources. Message commands can suspend dialogue for event-script work.", [MS], notes="A message containing $H needs a matching TalkResume sequence. A message ID does not supply portraits or continuation state by itself.", source="../../research/CONVERSATION_RENDERING.md")
add("TalkResume", "Resumes the current suspended event conversation rather than starting a new message.", notes="Use only with an active continuation; preserve the corresponding $H points in message text.", source="../../research/CONVERSATION_RENDERING.md")
add("TalkExist", "Queries whether a conversation remains active; tutorial helpers yield while this is true.", returns="Predicate consumed by wait loops.")
for name, action in [("DisableSkip", "Disables"), ("EnableSkip", "Enables")]:
    add(name, f"{action} event skipping for the active scene flow.", notes="A state change, not a scoped Python context manager. Preserve restoration on every scene exit.")
add("WaitM", "Delays event sequencing for a millisecond duration in ordinary scene code.", [TIME], notes="Timing/skip behavior is native; use an operation-specific wait for completion of movement or fades.")
add("WaitF", "Delays event sequencing by a frame count.", [("frames", "Number of frames, not milliseconds.")], notes="Do not assume the operation also waits for an unrelated movement/camera process.")
add("Fade", "Starts a screen-fade operation selected by a mode code.", [("mode", "Fade mode code. Original scripts use values such as 0–7; the exact complete mode table is not established here. Copy a matching scene pattern."), TIME], notes="Use FadeWait to synchronize. Do not label all modes as a simple black fade-in/out.")
add("isFading", "Reports the screen-fade busy state consumed by FadeWait.", returns="Nonzero while the helper should keep yielding.")
add("Focus", "Moves map-camera focus toward a map-grid location.", [X, Y], notes="Use the chapter's matching FocusWait/FocusHardWait pattern before dependent scene work.")
add("InstantFocus", "Sets map-camera focus to a map-grid location using the immediate-focus operation.", [X, Y])
for name, desc in [("FocusWait", "Waits for the native focus operation's completion condition."), ("FocusHardWait", "Uses the stronger focus-wait operation used by scenes before dependent movement/dialogue."), ("UnitMoveWait", "Waits for the native unit-motion completion condition."), ("EventCameraWait", "Waits for the active event-camera sequence."), ("EffectWait", "Waits for the native effect-completion condition.")]:
    add(name, desc, notes="Exact process coverage, event-skip paths and timeout behavior are not fully documented; no timeout argument is exposed.")
for name, desc in [("CopyMapCamera", "Saves the current map-camera state for a later PastMapCamera restoration."), ("PastMapCamera", "Restores the previously copied map-camera state through the normal camera transition."), ("InstantPastMapCamera", "Uses the immediate restoration of the previously copied map-camera state."), ("CreateEventCamera", "Creates/prepares event-camera sequence state before keyframe calls."), ("DeleteEventCamera", "Deletes event-camera state when returning to normal map-camera control.")]:
    add(name, desc, notes="Preserve the full create/copy/start/wait/restore lifecycle from a matching scene.")
for name in ["SetMapCamera", "InstantSetMapCamera"]:
    add(name, ("Immediately sets" if name.startswith("Instant") else "Transitions") + " the map camera using its three native camera parameters.", [("camera_a", "First camera parameter; exact axis/angle convention not verified."), ("camera_b", "Second camera parameter; exact axis/angle convention not verified."), ("camera_c", "Third camera parameter; exact distance/scale convention not verified.")], notes="These are camera parameters, not three map-tile coordinates.")
add("SetEventCameraPrec", "Selects event-camera coordinate precision used by subsequent keyframes.", [("precision", "Precision/scaling mode. Original scene code commonly switches between 1 and 100; full conversion formula is not established here.")])
for name, kind in [("SetEventCameraAt", "target/position"), ("SetEventCameraRot", "rotation")]:
    add(name, f"Adds or configures an event-camera {kind} keyframe.", [("time", "Keyframe timing parameter, conventionally milliseconds in scene sequences; preserve ordering."), ("a", f"First {kind} component; depends on camera precision/convention."), ("b", f"Second {kind} component; axis semantics not established here."), ("c", f"Third {kind} component; do not equate these blindly to tile X/Y/Z.")])
add("StartEventCamera", "Starts the configured event-camera sequence.", [("mode", "Playback mode; values such as 0, 2 and 3 occur. Their complete behavior table remains unresolved.")], notes="Schedule keyframes first, then use EventCameraWait where the scene needs completion.")
for name, desc, args in [
    ("BGMPlay", "Starts a named track on a music channel.", [CHANNEL, BGM]),
    ("BGMFadeIn", "Starts/fades in a named track on a music channel.", [CHANNEL, BGM, TIME]),
    ("BGMFadeOut", "Fades out a music channel.", [CHANNEL, TIME]),
    ("BGMMute", "Mutes a channel over a transition duration; shared helpers use this while temporarily switching to event music.", [CHANNEL, TIME]),
    ("BGMCont", "Continues/restores a channel after a temporary event-music interruption.", [CHANNEL, TIME]),
    ("BGMStop", "Requests a stop for a music channel.", [CHANNEL]),
    ("BGMQuietOn", "Enables the channel's quiet/ducking state around dialogue or rewards.", [CHANNEL]),
    ("BGMQuietOff", "Clears the channel's quiet/ducking state.", [CHANNEL]),
    ("BGMPlayVol", "Starts a named track with an explicit volume parameter.", [CHANNEL, BGM, ("volume", "Native volume value; valid range/scale not decoded here.")]),
    ("BGMSetVol", "Changes a channel's volume over a transition.", [CHANNEL, ("volume", "Native target volume; range/scale not decoded here."), TIME]),
    ("SFXPlay", "Plays a named sound effect.", [("sfx_id", "Existing sound-effect ID, commonly SFX_...; not a BGM channel or audio filename.")]),
]:
    add(name, desc, args, notes="Track ownership, interruption and exact native return behavior are not implied by the call's name.", source="../../research/MUSIC_NOTES.md")
for name, desc in [("ENVNoisyOn", "Enables the environmental noisy state."), ("ENVNoisyOff", "Disables the environmental noisy state."), ("ENVQuietOn", "Enables the environmental quiet state."), ("ENVQuietOff", "Disables the environmental quiet state."), ("ENVSilentOff", "Restores environment sound after ENVSilentOn.")]:
    add(name, desc, notes="Use the corresponding pair from a tested scene; exact mixing levels are not decoded.")
add("ENVSilentOn", "Enables environmental silence with a transition parameter.", [("transition", "Native transition value, often 0, 30, 45, 60 or 90. Do not assume WaitM's units apply; exact units are not established here.")])

add("UnitGetByPID", "Looks up the runtime actor for a character ID; shared wrappers explicitly test the result before use.", [PID], "Unit reference, or 0 when lookup fails.")
add("UnitGetByPos", "Looks up the runtime unit at a map position.", [X, Y], "Unit reference; shared positional wrappers treat 0 as no unit.")
add("ForceGetFirst", "Returns the head used to iterate a runtime force list.", [FORCE], "First unit reference, or 0 for no accessible head. Iterate with UnitGetNext.")
add("ForceGetCount", "Counts units in a runtime force list.", [FORCE], "Unit count for that list, not automatically the number alive/deployed in the entire chapter.")
add("UnitGetNext", "Advances from a unit to the next member in the current list iteration.", [UNIT], "Next unit reference; loops check for 0.", notes="Mutating force membership while iterating can change traversal; do not assume the previous next pointer remains valid.")
for name, prop in [("UnitGetX", "map-grid X coordinate"), ("UnitGetY", "map-grid Y coordinate"), ("UnitGetHP", "current HP"), ("UnitGetMaxHP", "maximum HP"), ("UnitGetStatus", "status bitmask"), ("UnitGetWeaponCount", "weapon inventory count"), ("UnitGetItemCount", "item inventory count")]:
    add(name, f"Reads the unit's {prop}.", [UNIT], f"The {prop}; null-input behavior and numeric bounds are not established here.")
for name, desc in [("UnitSetHP", "Sets current HP; clamping and death dispatch are not established, so this is not documented as equivalent to killing the unit."), ("UnitSetEXP", "Sets the unit's experience value; automatic level-up behavior is not established."), ("UnitSetStatus", "Applies status-mask bits to a unit."), ("UnitClrStatus", "Clears selected status-mask bits from a unit.")]:
    add(name, desc, [UNIT, ("value" if name in ("UnitSetHP", "UnitSetEXP") else "mask", "HP/EXP value or status bitmask as appropriate. Use decoded bits; an arbitrary integer is not a named status.")])
for name, desc in [("UnitSetPos", "Positions an actor on the map."), ("UnitMovePos", "Schedules actor movement toward a map position.")]:
    add(name, desc, [UNIT, X, Y], notes="Existing handler research identifies an unoccupied-tile search: the final tile may differ when the requested destination is occupied. Movement completion is separate; use UnitMoveWait.")
add("UnitMoveDir", "Schedules movement using a direction-command string.", [UNIT, ("path", "Direction-command string, for example repeated numeric codes. It is not a coordinate tuple; preserve a verified path syntax.")], notes="Use UnitMoveWait when dependent scene work must follow arrival.")
add("UnitRotate", "Requests a unit facing/rotation change.", [UNIT, DIR, TIME], notes="Shared UnitSetPosDir passes duration 0 for an immediate facing change.")
add("UnitAnim", "Requests a unit animation by native animation selector.", [UNIT, ("animation", "Animation code for the actor/rig. Values such as 0, 3, 8 and 9 occur; the full mapping is not established here.")])
add("UnitAnimF", "Requests the extended unit-animation operation.", [UNIT, ("animation", "Animation selector forwarded by UnitAnimFByPID."), ("extra", "Third native animation parameter; exact frame/flag semantics unresolved.")])
add("UnitEscape", "Removes/escapes a unit through the native escape operation.", [UNIT, ("mode", "Escape-operation mode. The shared UnitEscapeByPID helper always passes 0; other meanings remain unresolved.")], notes="Do not assume escape means permanent death or removal from the campaign roster.")
add("UnitFocus", "Focuses the camera on a runtime unit.", [UNIT], notes="UnitFocusByPID instead computes the deployed unit's tile and invokes Focus.")
for name, desc in [("UnitForcedSally", "Marks a unit for forced deployment."), ("UnitDontMoveSally", "Applies the fixed-deployment-position operation during preparations."), ("UnitBreakup", "Breaks a unit's linked/pair relationship through the native operation."), ("UnitSetWeaponAway", "Requests the weapon-away state used by scene helpers."), ("UnitSetAccAway", "Requests the accessory-away state."), ("UnitWarpOut", "Runs the native warp-out operation for a unit."), ("UnitDead", "Runs the native death operation; its complete consequences and trigger ordering require verification."), ("UnitClassChange", "Runs the unit's class-change operation using its existing class/promotion data.")]:
    add(name, desc, [UNIT], notes="Do not infer a full persistent roster or item-data change from a visual scene operation.")
for name, desc in [("UnitAddSkill", "Adds the indicated skill through the runtime unit API."), ("UnitClrSkill", "Clears the indicated skill through the runtime unit API."), ("UnitTstSkill", "Tests the indicated skill on the unit.")]:
    add(name, desc, [UNIT, ("skill_id", "Existing SID_... skill ID; not a raw status mask.")], "Predicate for UnitTstSkill; mutation return semantics not established." if name == "UnitTstSkill" else None)
for name, prefix, desc in [("UnitQueryJID", "JID", "Tests the actor against a class ID."), ("UnitQueryPID", "PID", "Tests the actor against a character ID.")]:
    add(name, desc, [UNIT, ("id", f"Existing {prefix}_... ID string.")], "Predicate used by script conditions; exact treatment of aliases/subclasses is not established.")
for name, desc in [("UnitSetCpAttackSeq", "Sets the actor's attack AI sequence."), ("UnitSetCpMoveSeq", "Sets the actor's movement AI sequence.")]:
    add(name, desc, [UNIT, ("sequence", "Existing SEQ_... behavior symbol. Defining a new string does not implement a new AI algorithm.")])
add("UnitAddItem", "Adds an item through the native inventory operation.", [UNIT, ("item_id", "Existing IID_... item ID.")], notes="Capacity handling, result code and whether a popup appears must not be inferred; UnitGetItemShowing is the separate presentation helper.")
for name, desc in [("UnitDelItem", "Deletes an inventory entry selected by the native index."), ("UnitSetEquip", "Selects an inventory entry for equipping."), ("UnitItemGetValuation", "Returns the valuation used by the shared inventory-to-storage selection helper."), ("UnitItemSendtoWarehouse", "Transfers a selected inventory entry to storage."), ("UnitItemSetDrop", "Marks an inventory entry for dropping through the native item API.")]:
    add(name, desc, [UNIT, ("item_index", "Native inventory index. The shared four-weapon storage helper passes 0–3; do not assume these are IID strings or every inventory family's valid range.")], "Valuation number used for comparisons." if name == "UnitItemGetValuation" else None)
add("UnitSearchItem", "Searches a unit's inventory for an item ID.", [UNIT, ("item_id", "IID_... string to find.")], notes="Exact not-found sentinel and index encoding are not established here.")
for name in ["UnitItemSendtoWarehouseAll", "UnitPutToWarehouse"]:
    add(name, "Calls the same registered native handler as the other all-items-to-storage alias (both are 0x800BBFD0).", [UNIT], notes="Handler identity is confirmed by the registration table; exact selection/capacity semantics still require inspection.", evidence="Confirmed alias; behavioral name inference")

for name in ["Dispos", "InstantDispos", "DisposAsynchronous", "DisposContinue", "InstantDisposContinue", "DisposFirst", "InstantDisposFirst", "InstantDisposRank", "DisposAuxiliary"]:
    desc = {"Dispos": "Deploys a named group through the ordinary staged deployment operation.", "InstantDispos": "Deploys a named group through the immediate placement operation.", "DisposAsynchronous": "Starts the asynchronous deployment variant for a named group.", "InstantDisposRank": "Uses the difficulty/rank-selecting immediate-deployment variant for a group prefix."}.get(name, f"Invokes the {name} deployment variant on the supplied group. Its precise difference from ordinary Dispos is not yet fully documented.")
    add(name, desc, [GROUP], notes="Requires matching deployment data, legal positions and valid actor/item references. Group suffix and difficulty selection depend on the actual helper/native path.", source=CHAPTER)
for name, desc in [("SallySetByGroup", "Sets preparation/deployment placement from a group."), ("SallyAddByGroup", "Adds preparation/deployment placement from a group."), ("Join", "Processes a named join/deployment group, such as the always_T_... groups used by TrialAddUnit.")]:
    add(name, desc, [GROUP], notes="This takes a section/group name, not a PID. Persistent roster effects depend on the group's records and surrounding flow.", source=CHAPTER)
add("MapLoad", "Loads the named map resources for the scene.", [("map_name", "Map resource name such as bmap02 or bmap06_2, not a displayed chapter title.")], notes="Loading a map does not by itself perform all deployment, camera, preparation and objective initialization.", source=CHAPTER)
for name, desc in [("MapReload", "Reloads the map during restoration after a temporary scene/tutorial."), ("MapUpdate", "Requests a map-state update after changes/restoration."), ("UnitDispReload", "Reloads unit display resources during scene restoration."), ("AllUnitEscape", "Runs the all-units escape operation used while tearing down scene actors."), ("UnitsInitialize", "Initializes the runtime unit state used by chapter/scene setup.")]:
    add(name, desc, notes="Keep the original lifecycle around this call; it is not a stand-alone chapter reset.")
for name, desc in [("UnitsPush", "Pushes unit state for later restoration."), ("UnitsPush_Uninitialize", "Pushes unit state and performs the uninitializing variant for a temporary scene."), ("UnitsPop", "Restores the pushed unit state."), ("UnitsPopWithoutMap", "Uses the unit-state restoration variant without the normal map operation."), ("AllPush", "Pushes the broader scene/game state used by TutorialIn."), ("AllPop", "Restores the broader state pushed before entering a tutorial.")]:
    add(name, desc, notes="Exact contents/depth of the save stack are not fully decoded. Preserve matched push/pop ownership.")
for name, desc in [("BuildDestruction", "Destroys the building at a map location."), ("BuildInstHide", "Hides a map building/prop instance at a location."), ("BuildInstShow", "Shows a map building/prop instance at a location."), ("DoorOpen", "Runs the door-opening operation at a location."), ("DoorClose", "Runs the door-closing operation at a location."), ("InstantDoorOpen", "Applies the immediate door-open operation."), ("InstantDoorClose", "Applies the immediate door-close operation."), ("RoofOpen", "Runs the roof-opening operation at a location."), ("RoofClose", "Runs the roof-closing operation at a location."), ("InstantRoofOpen", "Applies the immediate roof-open operation."), ("InstantRoofClose", "Applies the immediate roof-close operation."), ("TBoxOpen", "Runs the treasure-box opening operation at a location.")]:
    add(name, desc, [X, Y], notes="Requires corresponding map objects. Do not assume this grants a reward or sets the event's used flag.", source=CHAPTER)
for name in ["VisitIn", "VisitOut"]:
    add(name, f"Runs the {name} unit/building transition used by location events.", [UNIT, X, Y], notes="Original visits preserve the actor from MindGetMe and pass EventGetX/Y. This is not the reward call.")
for name, desc in [("EventGetX", "Reads the current map event's X coordinate."), ("EventGetY", "Reads the current map event's Y coordinate."), ("MindGetMe", "Reads the current action/event's acting unit."), ("MindGetTarget", "Reads the current action/event's target unit.")]:
    add(name, desc, returns="Map coordinate for EventGetX/Y; unit reference for MindGetMe/Target.", notes="Meaning depends on an active event/action context. Do not assume a turn event provides the same actor/target as a talk, combat or visit.")
for name, prop in [("BMGetTurn", "current turn number"), ("BMGetChapter", "internal chapter file number (Prologue is 1)"), ("BMGetPhase", "current phase identifier"), ("BMGetMoney", "current money amount")]:
    add(name, f"Reads the {prop}.", returns=prop.capitalize() + ".", source=CHAPTER)
for name, prop in [("BMSetTurn", "turn counter"), ("BMSetPhase", "phase field"), ("BMSetMoney", "money amount")]:
    add(name, f"Sets the {prop} through the script API.", [("value", f"New {prop}. Setting a field is not proof that the associated phase/turn transition events execute.")], notes="Clamping and full event-transition consequences are not established here.")
add("AchieveSet", "Submits a named achievement/result reward entry from scenario-end logic.", [("message_id", "Reward/result label ID, such as Ms_ach_02_turn."), ("amount", "Reward value calculated by the chapter's result function.")], notes="Preserve the scenario-end function's return value and one-time dispatch; do not equate this with BMSetMoney.")
add("ChapterMoviePlay", "Plays the opening movie selected for an internal chapter number.", [("chapter", "Internal file/chapter number. This is not a request to progress to that chapter.")], source="../../research/CUTSCENE_VIDEO_NOTES.md")
add("MoviePlay", "Plays a named movie resource.", [("movie", "Movie resource string used by the existing game's movie loader; use a verified resource name.")], source="../../research/CUTSCENE_VIDEO_NOTES.md")
add("ProcExists", "Queries existence of a named engine process; tutorial helpers use this to wait for tokens/actors.", [("process_name", "Exact engine process name, for example E_PadActor or E_TurnToken.")], "Predicate used in yield loops.", notes="A process name is not a .fe9s function name.")
add("ProcKill", "Requests termination of a named engine process.", [("process_name", "Exact process name, for example E_Popup in TutorialInit.")], notes="Destroying a process can invalidate a wait or scene lifecycle; use only with an understood owner.")
for name, desc in [("GameBind", "Binds gameplay while tutorial-specific work runs."), ("GameUnbind", "Releases the gameplay binding used by tutorial wrappers."), ("SuspendEvent", "Suspends the current event flow for tutorial/scene transfer."), ("ResumeEvent", "Resumes the previously suspended event flow.")]:
    add(name, desc, notes="Exact nesting/scheduling semantics remain native. Follow the complete shared helper sequence, not an isolated call.")

# Every shared startup export receives a control-flow description and returns.
for prefix in ["Dispos", "InstantDispos", "DisposFirst", "InstantDisposFirst", "DisposContinue", "InstantDisposContinue"]:
    helper(prefix + "SetMode", f"Calls {prefix}(normal_group) if NormalOnly(), otherwise {prefix}(hard_group) if Hard(), otherwise {prefix}(fallback_group).", [("normal_group", "First deployment group; its branch is unreachable with the researched US unregistered NormalOnly name."), ("hard_group", "Group selected when Hard() is true."), ("fallback_group", "Group selected otherwise; do not infer a menu difficulty solely from a filename suffix.")])
helper("UnitCheckLiveByPID", "Looks up the PID, then returns false for a null actor, status bit 0x08, or force 6; true otherwise. This is not a deployed-on-map test.", [PID], "0 or 1.")
helper("UnitCheckDeadHere", "Returns true exactly when the non-null unit's status has bit 0x8000 set.", [UNIT], "0 for null/bit clear; 1 for bit set.")
helper("UnitCheckDeadHereByPID", "Looks up the PID and calls UnitCheckDeadHere; a missing actor returns 0.", [PID], "0 or 1.")
helper("UnitCheckExists", "Checks non-null actor membership in force 0, 1, 2 or 3. It reads status but does not use that value in the decision.", [UNIT], "1 for one of those active forces; 0 otherwise.")
helper("UnitCheckExistsByPID", "Looks up the actor and forwards to UnitCheckExists.", [PID], "0 or 1; not an actor reference.")
helper("UnitCheckExistsByPID2", "Looks up the actor and checks UnitCheckExists.", [PID], "The actor reference if deployed in force 0–3; 0 otherwise. Unlike UnitCheckExistsByPID, success is not normalized to 1.")
helper("UnitQueryJIDByPID", "Looks up the actor; if present, returns UnitQueryJID(actor, class_id).", [PID, ("class_id", "JID_... class ID.")], "0 for missing actor, otherwise the native class-test result.")
helper("FocusBetweenAB", "Requires both PIDs to be deployed, copies the current map camera, computes their tile midpoint using a right shift by 1, adds offsets and calls Focus or InstantFocus.", [("pid_a", "First deployed actor PID."), ("pid_b", "Second deployed actor PID."), ("offset_x", "Tiles added to the midpoint X."), ("offset_y", "Tiles added to the midpoint Y."), ("instant", "Nonzero uses InstantFocus; zero uses Focus.")], "0 if either actor is unavailable; 1 after scheduling focus.", "Does not restore the copied camera or wait for focus itself.")
helper("UnitMoveToUnit", "Requires both actors to be deployed. Reads the FIRST actor's X/Y and moves the SECOND actor toward that tile.", [("destination_unit", "Actor whose tile is the destination."), ("moving_unit", "Actor to move; argument order is significant.")], "0 for absent/nondeployed actor; 1 after calling UnitMovePos.")
helper("UnitMoveToUnitByPID", "Resolves both PIDs and calls UnitMoveToUnit(destination, mover). Discards that helper's result.", [("destination_pid", "PID whose tile is the destination."), ("moving_pid", "PID to move.")])
helper("UnitRotateToPos", "Requires a deployed actor, compares its tile to the target tile and chooses an eight-direction facing using the original axis/diagonal threshold branches, then calls UnitRotate.", [UNIT, X, Y, TIME], notes="No success return is emitted: success also returns 0. This is discrete facing selection, not an exact continuous-angle look-at.")
helper("UnitRotateToPosByPID", "Resolves a deployed actor and forwards to UnitRotateToPos.", [PID, X, Y, TIME], "0, including on successful scheduling.")
helper("UnitRotateToUnit", "Requires both actors deployed, reads the target actor's tile and rotates the first actor toward it using UnitRotateToPos.", [("rotating_unit", "Actor whose facing changes."), ("target_unit", "Actor whose tile supplies the target."), TIME], "0, including on successful scheduling.")
helper("UnitRotateToUnitByPID", "Resolves both deployed actors and forwards to UnitRotateToUnit.", [("rotating_pid", "PID whose facing changes."), ("target_pid", "PID to face."), TIME], "0, including on successful scheduling.")
helper("UnitSetPosDir", "For a non-null actor, sets its tile then immediately rotates it unless direction is -1.", [UNIT, X, Y, ("direction", "Engine facing code; -1 preserves facing. Other values are passed to UnitRotate with duration 0.")], "0 for null; 1 after applying the calls.")
helper("UnitSetPosDirByPID", "Resolves a deployed actor, sets its tile, and immediately rotates unless direction is -1.", [PID, X, Y, ("direction", "Facing code; -1 leaves facing unchanged.")], "Actor reference on success; 0 if unavailable.")
helper("UnitSetPosDirByPos", "Finds the actor at the source tile, moves it to the destination, and immediately rotates unless direction is -1.", [("source_x", "Source map X."), ("source_y", "Source map Y."), ("destination_x", "Destination map X."), ("destination_y", "Destination map Y."), ("direction", "Facing code; -1 preserves facing.")], "Actor reference on success; 0 if the source tile has no actor.")
helper("UnitTransferToForceByPID", "Resolves the actor, applies the UnitCheckLiveByPID-equivalent null/status-0x08/force-6 test, then calls UnitTransferToForce.", [PID, FORCE], "0 if missing/not live under that test; 1 after transfer.", "Unlike movement wrappers, does not require current force 0–3; live reserve actors can pass.")
helper("UnitForcedSallyByPID", "Requires a deployed actor and calls UnitForcedSally.", [PID], "0 if unavailable; 1 after the call.")
helper("UnitDontMoveSallyByPID", "Requires a deployed actor, calls BOTH UnitForcedSally and UnitDontMoveSally.", [PID], "0 if unavailable; 1 after both calls.")
helper("UnitEscapeByPID", "Requires a deployed actor, then calls UnitEscape(actor, 0).", [PID], "0 if unavailable; 1 after the call.")
helper("Dispos_ForEvent", "If class_id is empty, uses matching_group without testing the actor. Otherwise tests UnitQueryJIDByPID and chooses matching_group or other_group. Uses InstantDispos when instant is nonzero, otherwise Dispos.", [PID, ("class_id", "JID to test, or empty string to bypass the class test."), ("matching_group", "Group for empty class or successful class match."), ("other_group", "Group for failed class match."), ("instant", "Nonzero = immediate placement; zero = ordinary deployment.")], "1 after the selected call, not proof the native deployment succeeded.")
helper("Dispos_ForEventTiamat", 'Calls Dispos_ForEvent("PID_TIAMAT", "", group, group, instant); the empty class bypasses the actor/class check.', [GROUP, ("instant", "Nonzero = InstantDispos; zero = Dispos.")], "1.")
helper("Dispos_ForEventSenerio", 'Calls Dispos_ForEvent for PID_SENERIO and JID_MAGE.', [("mage_group", "Group when Soren matches JID_MAGE."), ("other_group", "Group otherwise."), ("instant", "Nonzero = InstantDispos; zero = Dispos.")], "1.")
for name, native, args in [("UnitMovePosByPID", "UnitMovePos", [PID, X, Y]), ("UnitMoveDirByPID", "UnitMoveDir", [PID, ("path", "Native direction-command string.")]), ("UnitRotateByPID", "UnitRotate", [PID, DIR, TIME])]:
    helper(name, f"Resolves a deployed actor using UnitCheckExistsByPID2, then calls {native} with the remaining arguments.", args, "Actor reference if scheduled; 0 if unavailable.", "Does not wait for completion; use the appropriate movement wait.")
for axis in ["X", "Y"]:
    helper("UnitGet" + axis + "ByPID", f"Resolves a deployed actor and reads UnitGet{axis}.", [PID], f"Map {axis} coordinate, or -1 if unavailable.")
for suffix, args in [("", [PID, ("animation", "Native animation selector.")]), ("F", [PID, ("animation", "Native animation selector."), ("extra", "Extra UnitAnimF parameter; precise meaning unresolved.")])]:
    helper("UnitAnim" + suffix + "ByPID", f"Resolves a deployed actor and calls UnitAnim{suffix}. Missing actor exits without animation.", args, "0 even when the call succeeds; native result is discarded.")
for name in ["UnitFocusByPID", "UnitFocusOffsetByPID", "InstantUnitFocusByPID", "InstantUnitFocusOffsetByPID"]:
    offset = "Offset" in name
    native = "InstantFocus" if name.startswith("Instant") else "Focus"
    helper(name, f"Resolves a deployed actor, reads its tile{' and adds X/Y offsets' if offset else ''}, then calls {native}.", [PID] + ([("offset_x", "Tiles added to actor X."), ("offset_y", "Tiles added to actor Y.")] if offset else []), "0 if unavailable; 1 after focus call.", "Does not copy/restore the previous map camera itself.")
helper("UnitSetCpTypeByPID", "Resolves a deployed actor, then sets its attack sequence followed by its movement sequence.", [PID, ("attack_sequence", "SEQ_... passed to UnitSetCpAttackSeq."), ("move_sequence", "SEQ_... passed to UnitSetCpMoveSeq.")])
helper("UnitSetWeaponAwayByPID", "Resolves a deployed actor and returns UnitSetWeaponAway(actor).", [PID], "-2 if unavailable; otherwise the native result (not decoded here).")
helper("UnitCheckLinked_Breakup", "Returns early for null; otherwise calls UnitBreakup only if status & 0x06 is nonzero.", [UNIT], "0 for null; 1 otherwise, including when no breakup was needed.")
helper("UnitCheckLinked_BreakupByPID", "Resolves a deployed actor and forwards to UnitCheckLinked_Breakup.", [PID], "0 if unavailable; otherwise the linked-check helper result.")
helper("AllUnitsBreakup", "Walks force 0 only, bounded by ForceGetCount(0), and calls UnitCheckLinked_Breakup for each actor until count exhaustion or a null next actor.", notes="Despite the name, it does not traverse all eight forces.")
helper("ForceCheckAnyoneDead", "Walks force 6 and tests status bit 0x8000 on each actor.", returns="1 if any scanned actor has that bit; 0 otherwise.")
helper("UnitItemSendToHouseByPID", "Requires an existing actor with exactly four weapons. Compares valuations for indices 0–3, then sends one entry to storage.", [PID], "-1 if missing or weapon count is not 4; otherwise 0.", "Do not simplify this to 'always sends the cheapest': the index-2 branch checks v4 <= v2, v4 <= v3, but v3 <= v5 (not v4 <= v5). Tie order prefers earlier branches. Preserve the actual logic.")
for i, wait in [(1, "the full duration"), (2, "duration >> 1"), (3, "no time")]:
    helper(f"BgmChangeEvt_MapToEvt{i}", f"Calls BGMMute(0, duration), waits {wait}{' with WaitM' if i != 3 else ''}, then BGMPlay(1, bgm_id).", [BGM, TIME])
    helper(f"BgmContEvt_EvtToMap{i}", f"Calls BGMFadeOut(1, fade_duration), waits {wait.replace('duration', 'fade_duration')}{' with WaitM' if i != 3 else ''}, then BGMCont(0, resume_duration).", [("fade_duration", "Milliseconds passed to BGMFadeOut and the helper's wait."), ("resume_duration", "Transition duration passed to BGMCont.")])
for name, native in [("ENVNoisyOn_WhenNotEvtSkip", "ENVNoisyOn"), ("ENVSilentOff_WhenNotEvtSkip", "ENVSilentOff")]:
    helper(name, f"Calls {native} only when (GCST() & 1) is zero.", notes="This documents the exact guard, not the complete GCST bitfield.")
helper("LocalDieTalkWithBgmChange", 'Disables skip. If flag_name is nonempty and set, calls DefaultDieTalk. Otherwise mutes map music, fades event music over 500 ms, waits 500 ms, plays BGM_DEAD1 and the supplied message. Surrounds that custom branch with environment silence when GetBattleType has bit 0x80000000. Re-enables skip.', [("flag_name", "Empty string forces custom dialogue; otherwise a set registered flag selects DefaultDieTalk."), MS], notes="It does not set the supplied flag or explicitly restore the previous BGM itself.")
helper("SoundBossTalkStart", "Only when GetBattleType() has bit 0x80000000: silences environment with parameter 30, mutes channel 0 over 750, and plays the supplied track on channel 1.", [BGM])
helper("SoundBossTalkEnd", "Under the same battle-type bit guard, restores environment, fades channel 1 over 750 and continues channel 0 over 750.")
helper("FadeWait", "Yields repeatedly while isFading() is nonzero.", notes="No timeout and no extra frame after the predicate becomes false.")
helper("PreLoadWait", "Yields repeatedly while _pldone() equals zero.", notes="Exact resource coverage belongs to _pldone's native implementation.")
helper("MapFree", "Calls _mf1(), yields once, then calls _mf2().", notes="Two-stage native map release; removing the yield changes the sequence.")
helper("UnitGetItemShowing", "Disables skip; if Comeback() is nonzero, starts Fade(2,166) and waits. Calls _gi(unit,item_id), yields once, then enables skip.", [UNIT, ("item_id", "IID_... reward item.")], notes="No explicit null check in this helper. Native _gi handles the reward operation; full-inventory behavior/return contract is not decoded by the wrapper.")
helper("UnitGetItemShowingSub", 'Quiets music channel 0, externally calls UnitGetItemShowing(unit,item_id), then restores channel quiet state.', [UNIT, ("item_id", "IID_... reward item.")])
helper("MindGetItem", "Calls UnitGetItemShowing(MindGetMe(), item_id).", [("item_id", "IID_... reward item.")], notes="Recipient is the current acting unit; inappropriate context may provide no valid recipient.")
helper("RegistGlobalFlags", "Calls the native global registration operation 22 times in fixed order for the original campaign flag list, including repeated reserved names.", notes="Boot-time setup, not a per-turn reset. Reordering changes saved-bit interpretation; see named flags.")
helper("TutWaitF", "Calls GameBind, yields once per loop iteration until the counter reaches frames, then GameUnbind.", [("frames", "Loop/yield count. Nonpositive values produce no loop iterations.")])
helper("TutWaitM", "Calls GameBind, computes duration_ms * 60 / 1000 with integer arithmetic, yields that many iterations, then GameUnbind.", [("duration_ms", "Milliseconds converted using the helper's fixed factor 60/1000; this is not inferred from emulator frame rate.")])
helper("TutPreLoadWait", "Calls GameBind, externally invokes PreLoadWait, then GameUnbind.")
helper("TutPadActor", 'Calls _pa(action), then yields while process "E_PadActor" exists.', [("action", "Tutorial input/action string passed unchanged to _pa; its command grammar is not fully decoded.")])
helper("TutorialDialog", "Calls td(message_id), yields once, then tde().", [MS], notes="The wrapper does not explicitly poll for a result; do not infer td/tde internals from this sequence.")
helper("TutTalkEvent", "Calls GameBind, _tt(message_id), yields while TalkExist(), then GameUnbind.", [MS])
helper("TutTalkResume", "Calls GameBind, _tr(), yields while TalkExist(), then GameUnbind.")
for kind, token in [("Bases", "E_BasesToken"), ("Sally", "E_SallyToken")]:
    helper("Tut" + kind + "Create", f'Yields until "E_BMapPlph" exists, calls Tutorial{kind}Create, then yields while "{token}" exists.')
    helper("Tut" + kind + "Delete", f"Calls Tutorial{kind}Delete.")
for name, native, token in [("TutWaitForNextTaiki", "taikitk", "E_TaikiToken"), ("TutWaitForNextTurn", "turntk", "E_TurnToken"), ("TutWaitForNextTurnAfter", "turnatk", "E_TurnAToken")]:
    helper(name, f'Calls {native}(), then yields while process "{token}" exists.', notes="Exact token event semantics remain in the native routine; the helper's polling sequence is confirmed.")
helper("TutEntryCommon", 'Sleeps the tail module with CmSleepScript(""), calls _cmb_mess_load(script_path,"mess/tut.m"), then TutorialCall(entry_name).', [("script_path", "Tutorial CMB resource path, such as scripts/c80.cmb."), ("entry_name", "Named tutorial entry function in the loaded module.")])
helper("TutorialIn", "Fades with mode 3 for 266 and waits; AllPush; MapFree; TutEntryCommon; SuspendEvent; yields once.", [("script_path", "Tutorial CMB path forwarded to TutEntryCommon."), ("entry_name", "Tutorial entry name forwarded to TutEntryCommon.")], notes="Use with the matching exit/restoration flow; it changes module and map ownership.")
helper("TutorialOut", 'Frees "mess/tut.m", frees the last-loaded script, wakes sleeping scripts and resumes the suspended event.')
helper("TutorialResumeOut", "MapFree; yield; AllPop; MapReload; UnitDispReload; external Startup; MapUpdate; Fade(2,266); FadeWait.", notes="Re-enters chapter Startup during restoration, so flag registration order must remain stable.")
helper("ComebackFunc", "SuspendEvent; yield; MapFree; yield; external Startup; TutorialResume.")
helper("TutorialInit", 'Enables skip, calls _seqini, kills "E_Popup", calls _bmsini, then external Startup and RegistLocationTT.')
helper("Tutorial_FadeIn", 'Disables skip, builds RID_MASK, sets property 9 to 0 and property 2 to -835, then RectSetCurve("RID_MASK",9,0,0,128,100).', notes="The exact rectangle property/curve enum meanings are not all established. Preserve the sequence.")
helper("Tutorial_FadeOut", 'Calls RectSetCurve("RID_MASK",9,0,160,0,100), kills RID_MASK, then enables skip.')
helper("TrialAddUnit", 'Reads SysGetRound and calls Join for always_T_03 at >=4, always_T_05 at >=6, always_T_07 at >=8, always_T_10 at >=11, and always_T_15 at >=16. These are independent tests: higher counts call all qualifying groups.')

for name in ["Easy", "NormalOnly"]:
    add(name, "Always returns 0 in this US build; do not use this as a working difficulty test.", returns="0, always.", evidence="Confirmed registration/VM behavior", notes="Use GetRank or a supported difficulty helper instead.")

# Private natives with caller-established roles; not a claim to have decoded
# their bodies. The wrappers above specify the exact surrounding sequence.
for name, desc, args, notes in [
    ("_gi", "Native operation invoked by UnitGetItemShowing to deliver/show an item reward.", [UNIT, ("item_id", "IID item ID forwarded unchanged from the reward helper.")], "The caller establishes recipient/item roles. Inventory overflow, popup lifetime and native result remain undecoded."),
    ("td", "Starts the native tutorial-dialog step used by TutorialDialog.", [MS], "The helper yields once after this call and then calls tde; exact native scheduling/result semantics remain undecoded."),
    ("tde", "Final native step called by TutorialDialog after td and one yield.", [], "Whether this closes, joins or otherwise finalizes the dialog is not proven by the caller alone."),
    ("_mf1", "First native stage of MapFree, before its mandatory yield.", [], "The precise resource subset released by this stage is not decoded."),
    ("_mf2", "Second native stage of MapFree, after its yield.", [], "Use MapFree for the established two-stage sequence."),
    ("_pldone", "Readiness predicate used by PreLoadWait; a zero result keeps the helper yielding.", [], "Which resource queues this covers is not established."),
    ("_tt", "Starts the tutorial conversation operation used inside GameBind/GameUnbind by TutTalkEvent.", [MS], "The helper waits on TalkExist afterward; do not assume equivalence to ordinary TalkEvent on all skip paths."),
    ("_tr", "Resumes the tutorial conversation operation used by TutTalkResume.", [], "The helper wraps it in GameBind/GameUnbind and waits on TalkExist."),
    ("_pa", "Starts the tutorial actor/input operation whose E_PadActor process is polled by TutPadActor.", [("action", "Command string from TutPadActor; command grammar remains unresolved.")], "Use the wrapper if you need its explicit process wait."),
    ("_cmb_mess_load", "Loads the script/message pair used by the common tutorial-entry sequence.", [("script_path", "Tutorial CMB path forwarded from TutEntryCommon."), ("message_path", "Message resource path; the shared helper supplies mess/tut.m.")], "Underlying ownership and error behavior still require native inspection."),
    ("taikitk", "Starts the native step whose E_TaikiToken process is polled by TutWaitForNextTaiki.", [], "Exact triggering event belongs to the native token implementation."),
    ("turntk", "Starts the native step whose E_TurnToken process is polled by TutWaitForNextTurn.", [], "Exact triggering event belongs to the native token implementation."),
    ("turnatk", "Starts the native step whose E_TurnAToken process is polled by TutWaitForNextTurnAfter.", [], "Exact triggering event belongs to the native token implementation."),
    ("TutorialCall", "Invokes the named tutorial entry in the shared tutorial-load sequence.", [("entry_name", "Function name in the loaded tutorial module; for example tut_02_Visit.")], "The module must already be loaded; this is not a Python callable object."),
]:
    add(name, desc, args, notes=notes, evidence="Role established by shared-script caller; native internals unresolved", source="startup.cmb")

for name, description in [
    ("TutorialBasesCreate", "Called by TutBasesCreate after E_BMapPlph appears, followed by a wait on E_BasesToken."),
    ("TutorialBasesDelete", "Native teardown called directly by TutBasesDelete."),
    ("TutorialSallyCreate", "Called by TutSallyCreate after E_BMapPlph appears, followed by a wait on E_SallyToken."),
    ("TutorialSallyDelete", "Native teardown called directly by TutSallyDelete."),
    ("TutorialResume", "Final native step in ComebackFunc, after event suspension, map teardown and external Startup."),
    ("_seqini", "Tutorial sequence initialization step called by TutorialInit before killing E_Popup."),
    ("_bmsini", "Tutorial state initialization step called by TutorialInit after killing E_Popup and before Startup."),
]:
    add(name, description, notes="The caller sequence is established; full native side effects remain unresolved.", evidence="Role established by shared-script caller; native internals unresolved", source="startup.cmb")

# Rendering/data selector calls retain unknown enum meanings rather than assign
# plausible but unverified property names to raw values.
RECT = ("rect_id", "Existing RID_... rectangle/UI resource identifier; must be built or otherwise available for mutation.")
for name, desc in [("RectBuild", "Builds the named rectangle/UI resource used for scene overlays."), ("RectKill", "Kills/removes the named rectangle/UI instance."), ("RectPreLoad", "Preloads a named rectangle/UI resource before use.")]:
    add(name, desc, [RECT], notes="Resource lifecycle and child ownership require the matching original scene pattern.", source="../../research/CONVERSATION_RENDERING.md")
add("RectSet", "Sets a selected property of a named rectangle/UI instance.", [RECT, ("property", "Numeric property selector. The complete enum is unresolved; do not infer it from the value alone."), ("value", "Property-specific value; may encode flags, color or a numeric field.")], notes="For example, Tutorial_FadeIn writes selector 9 = 0 and selector 2 = -835; preserve these as raw values until their fields are decoded.")
add("RectSetCurve", "Configures a property interpolation/curve on a named rectangle/UI instance.", [RECT, ("property", "Numeric property selector, not a time."), ("curve_mode", "Curve/interpolation selector; full enum unresolved."), ("start_value", "Starting property value in the observed curve pattern."), ("end_value", "Ending property value in the observed curve pattern."), ("timing", "Curve timing parameter; exact units/skip handling are not established here.")], notes="The tutorial-mask helper uses property 9 with values 0 to 128; this alone does not prove every property has the same range.")
add("RectSetPos", "Sets the position of a named rectangle/UI instance.", [RECT, ("x", "UI/screen-space X, not map tile X."), ("y", "UI/screen-space Y, not map tile Y.")])
for name, action in [("RectFadeIn", "Fades in"), ("RectFadeOut", "Fades out"), ("RectFadeOutDelete", "Fades out and deletes")]:
    add(name, f"{action} a named rectangle/UI instance.", [RECT, ("duration", "Native fade timing parameter; preserve an observed value until units are verified.")])
add("TimeiShow", "Shows the scene's location-name caption using a message ID and three timing parameters.", [("screen_x", "Horizontal caption position in screen/UI space."), ("screen_y", "Vertical caption position in screen/UI space."), MS, ("appear_time", "Caption appearance timing; inferred from repeated scene patterns."), ("hold_time", "Caption hold timing; inferred from repeated scene patterns."), ("disappear_time", "Caption disappearance timing; inferred from repeated scene patterns.")], notes="The timing interpretation is an observed-use inference, not a verified native field contract. Common patterns are 300,2500,300 or 300,1500,300.")
for name, desc in [("ShowMapCursor", "Shows the map cursor at a tile."), ("SetPit", "Configures a pit location on the map."), ("MapGetTerrain", "Reads terrain information at a map tile."), ("MapGetUnit", "Queries unit occupancy through the map's native accessor."), ("MapGetSight", "Queries sight/visibility information at a tile.")]:
    add(name, desc, [X, Y], notes="Return encodings for map queries and full state-change side effects are not decoded here.")
add("HideMapCursor", "Hides the map cursor shown by scene code.")
add("SetTerrain", "Writes terrain at a map tile through the runtime terrain API.", [X, Y, ("terrain", "Terrain selector/code. Match a decoded terrain type; this does not rebuild map geometry.")])
add("BuildInstAnim", "Requests an animation for the map building/prop instance at a tile.", [X, Y, ("animation", "Prop-specific animation selector; the valid mapping depends on the instance.")])
for name, desc in [("SetGrid", "Changes map-grid display mode."), ("SetCircle", "Changes unit-circle display mode."), ("UnitWalkDir", "Changes the movement/direction setup used by later deployment and movement calls."), ("UnitWalkSlow", "Changes the slow-walk setting used by subsequent movement."), ("SetOutLink", "Changes the map/scene out-link setting.")]:
    add(name, desc, [("mode", "Native setting/mode value; preserve the original matching scene's value. Full enum, scope and reset semantics are not decoded.")], notes="This affects shared scene state rather than a unit passed as an argument. Restore it as in the original scene.")
for name, desc in [("UnitFadeIn", "Enables the unit fade-in setting used around subsequent placement/movement."), ("UnitFadeOut", "Enables the unit fade-out setting used around subsequent movement/escape."), ("UnitFadeOff", "Clears the shared unit-fade setting."), ("UnitFocusOn", "Enables the native automatic unit-focus setting."), ("UnitFocusOff", "Disables the native automatic unit-focus setting.")]:
    add(name, desc, notes="These are shared scene settings with no unit argument; preserve the matching restore call.")
add("GetBattleType", "Reads the battle-type/status bitfield used by scene helpers.", returns="Bitmask; shared boss/death-talk helpers test bit 0x80000000.", notes="The entire bitfield is not decoded here. Do not treat the result as a boolean or a single enum.")
add("GCST", "Reads the event/game-controller state flags used by shared and chapter scripts.", returns="Bitmask; shared environment helpers test bit 0x01.", notes="Only the observed bit tests are documented; other bits and their transitions remain unresolved.")

# More precise executable-derived contracts override earlier usage summaries.
from script_native_contracts import CONTRACTS
DETAILS.update(CONTRACTS)

# Constant results checked against the executable handler bodies.
RETURN_CONTRACTS = {'regist': '1.', 'global': '1.', 'set': '0.', 'clr': '0.', 'CmLoadScript': '1.', 'TalkEvent': '1.', 'TalkResume': '1.', 'DisableSkip': '1.', 'EnableSkip': '1.', 'Fade': '1.', 'Focus': '0.', 'InstantFocus': '0.', 'UnitMoveWait': '1.', 'EventCameraWait': '1.', 'CopyMapCamera': '1.', 'PastMapCamera': '1.', 'InstantPastMapCamera': '1.', 'CreateEventCamera': '1.', 'DeleteEventCamera': '1.', 'SetMapCamera': '1.', 'InstantSetMapCamera': '1.', 'SetEventCameraPrec': '1.', 'SetEventCameraAt': '1.', 'SetEventCameraRot': '1.', 'StartEventCamera': '1.', 'BGMFadeOut': '1.', 'BGMMute': '1.', 'BGMCont': '1.', 'BGMStop': '1.', 'BGMQuietOn': '1.', 'BGMQuietOff': '1.', 'BGMSetVol': '1.', 'ENVNoisyOn': '1.', 'ENVNoisyOff': '1.', 'ENVQuietOn': '1.', 'ENVQuietOff': '1.', 'ENVSilentOff': '1.', 'ENVSilentOn': '1.', 'UnitSetHP': '0.', 'UnitSetEXP': '0.', 'UnitFocus': '1.', 'Dispos': '1.', 'InstantDispos': '1.', 'DisposAsynchronous': '1.', 'DisposContinue': '1.', 'InstantDisposContinue': '1.', 'DisposFirst': '1.', 'InstantDisposFirst': '1.', 'InstantDisposRank': '1.', 'DisposAuxiliary': '1.', 'SallySetByGroup': '1.', 'SallyAddByGroup': '1.', 'MapLoad': '1.', 'MapReload': '1.', 'UnitDispReload': '1.', 'AllUnitEscape': '1.', 'UnitsInitialize': '1.', 'UnitsPush': '1.', 'UnitsPush_Uninitialize': '1.', 'UnitsPop': '1.', 'UnitsPopWithoutMap': '1.', 'AllPush': '1.', 'AllPop': '1.', 'VisitIn': '1.', 'AchieveSet': '1.', 'ProcKill': '0.', 'GameBind': '1.', 'GameUnbind': '1.', 'td': '0.', 'tde': '1.', '_mf2': '1.', '_tt': '1.', '_tr': '1.', '_pa': '1.', '_cmb_mess_load': '1.', 'taikitk': '1.', 'turntk': '1.', 'turnatk': '1.', 'TutorialBasesCreate': '1.', 'TutorialBasesDelete': '1.', 'TutorialSallyCreate': '1.', 'TutorialSallyDelete': '1.', '_seqini': '1.', '_bmsini': '1.', 'RectBuild': '0.', 'RectKill': '0.', 'ShowMapCursor': '1.', 'HideMapCursor': '1.', 'SetTerrain': '0.', 'SetGrid': '1.', 'SetCircle': '1.', 'UnitWalkDir': '1.', 'UnitWalkSlow': '1.', 'SetOutLink': '1.', 'UnitFadeIn': '1.', 'UnitFadeOut': '1.', 'UnitFadeOff': '1.', 'UnitFocusOn': '1.', 'UnitFocusOff': '1.'}
for _name, _result in RETURN_CONTRACTS.items():
    DETAILS[_name]["returns"] = _result

# Shared wrapper forwards the same transition parameter.
DETAILS["UnitAnimFByPID"]["args"][2] = CONTRACTS["UnitAnimF"]["args"][2]
