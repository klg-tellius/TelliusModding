"""Behaviour of the remaining native script functions, read from their US handlers.

Each entry was written from the decompiled native handler and the engine code it
calls (see research/SCRIPT_NATIVE_CONTRACTS.md, "Full behaviour pass").
It is applied after script_native_contracts.py, so an entry here replaces the
usage-based summary in script_reference_details.py.
"""

BEHAVIOUR = {}


def define(name, behavior, args=(), returns="1.", notes=""):
    BEHAVIOUR[name] = dict(behavior=behavior, args=list(args), returns=returns, notes=notes,
                           evidence="Confirmed engine behavior",
                           source="../../research/SCRIPT_NATIVE_CONTRACTS.md")


U = ("unit", "Numeric unit handle from UnitGetByPID or another unit lookup. 0 means no unit.")
P = ("pid", "Exact PID_... character ID string.")
X = ("x", "Map tile X, including the map border.")
Y = ("y", "Map tile Y, including the map border.")
MS = ("message_id", "Message ID in a loaded message file, not literal text.")
GROUP = ("group", "Name of a deployment group in the chapter's dispos file.")
VALID = "1 for a valid unit; 0 if the handle is 0 or the slot holds no character."
NONE = "No meaningful value; call it for its effect."
SKIP = "While the event is being skipped"
SLOT = ("slot", "Inventory slot: 0–3 are the four weapon slots, 4–7 the four item slots.")
CHANNEL = ("channel", "Music channel 0–3. Channel 0 is the map music; the shared helpers use 1 for event music and 2–3 for ambient tracks.")
BGM = ("bgm_id", "BGM_... track name from the sound data.")
FORCE = ("force", "Force ID: 0 player, 1 enemy, 2 allied (orderable), 3 other (green), 4 free pool, 5 player reserve, 6 dead/inactive, 7 special inactive.")

# ---------------------------------------------------------------- music and sound
define("BGMPlay", "Starts a track on a music channel at full volume. If any channel is already playing this same track, nothing changes. The channel's previous track is stopped.",
       [CHANNEL, BGM], "1; 0 only if bgm_id is not a valid string.",
       f"{SKIP}, or while a conversation is being skipped, no music starts. Starting a track on channel 0 clears the 'map music stopped by the event' mark that BGMStop/BGMFadeOut/BGMMute set.")
define("BGMFadeIn", "Starts a track on a music channel, fading it in from silence to full volume. If any channel is already playing this same track, nothing changes.",
       [CHANNEL, BGM, ("duration_ms", "Fade-in time in milliseconds (vanilla uses 500–1500).")], "1; 0 only if bgm_id is not a valid string.",
       f"{SKIP} or a conversation skip, no music starts. Channel 0 clears the 'map music stopped' mark.")
define("BGMPlayVol", "Starts a track on a music channel at the given volume.",
       [CHANNEL, BGM, ("volume", "Volume 0–100 (100 = full). Vanilla ambient tracks use 60–85.")], "1; 0 only if bgm_id is not a valid string.",
       "Same duplicate-track, skip and channel-0 rules as BGMPlay.")
define("BGMSetVol", "Changes a channel's volume gradually.",
       [CHANNEL, ("volume", "Target volume 0–100."), ("duration_ms", "Transition time in milliseconds; at least one frame.")],
       notes="Works on any channel, playing or not; it only changes the channel's volume level.")
define("BGMFadeOut", "Fades a playing channel to silence and stops it.",
       [CHANNEL, ("duration_ms", "Fade time in milliseconds; 0 or less stops the track at once.")],
       notes="Does nothing on a silent channel, and does not restart a fade-out already running. On channel 0 it marks the map music as stopped by the event, so the map's own music does not come back until a channel-0 play or BGMCont.")
define("BGMStop", "Stops a playing channel almost immediately (a one-millisecond fade).", [CHANNEL],
       notes="Same channel-0 rule as BGMFadeOut. Does nothing on a silent channel.")
define("BGMMute", "Fades a playing channel to silence and pauses it, remembering its volume and position so BGMCont can bring it back.",
       [CHANNEL, ("duration_ms", "Fade time in milliseconds; 0 or less pauses at once.")],
       notes="Used to hold the map music while an event track plays (see BgmChangeEvt_MapToEvt1). On channel 0 it also marks the map music as stopped by the event.")
define("BGMCont", "Resumes a channel paused by BGMMute and fades it back to its remembered volume.",
       [CHANNEL, ("duration_ms", "Fade-in time in milliseconds.")],
       notes="On channel 0 it also clears the 'map music stopped' mark and fades the channel's volume to 100, so the map music returns even if it was only muted.")
define("BGMQuietOn", "Starts lowering the music for a dialogue box or a reward window (the game's music 'quiet' state), over about a quarter of a second.",
       [("channel", "Ignored: the quiet state applies to the music as a whole.")],
       notes="Pair with BGMQuietOff. UnitGetItemShowingSub wraps an item reward in this pair.")
define("BGMQuietOff", "Ends the music 'quiet' state started by BGMQuietOn, restoring the level over about a quarter of a second.",
       [("channel", "Ignored.")])
define("SFXPlay", "Plays a sound effect once at full volume.",
       [("sfx_id", "SFX_... sound-effect name.")], "1; 0 only if sfx_id is not a valid string.",
       f"{SKIP}, or while a conversation is being skipped, no sound is played.")
for name, verb in [("ENVNoisyOn", "Raises the ambient (environment) sound to its 'noisy' level"),
                   ("ENVNoisyOff", "Returns the ambient sound from the 'noisy' level to normal"),
                   ("ENVQuietOn", "Lowers the ambient sound to its 'quiet' level"),
                   ("ENVQuietOff", "Returns the ambient sound from the 'quiet' level to normal"),
                   ("ENVSilentOff", "Brings back ambient sound silenced by ENVSilentOn")]:
    define(name, verb + ", over 15 frames (a quarter of a second).",
           notes="Each ENV call cancels any ambient-level change still in progress. The ambient level is separate from the music channel volumes.")
define("ENVSilentOn", "Silences the ambient (environment) sound.",
       [("frames", "Fade time in frames (60 per second): vanilla uses 15–90. 0 silences instantly; negative values count as 0.")],
       notes="Undo with ENVSilentOff. Cancels any ambient-level change still in progress.")

# ---------------------------------------------------------------- chapter and battle-map state
define("BMGetChapter", "Returns the current chapter number.", returns="Chapter number (Prologue = 1, the internal file number).")
define("BMGetMoney", "Returns the party's gold.", returns="Gold amount.")
define("BMSetMoney", "Sets the party's gold.", [("value", "New gold amount; anything above 9,999,999 is stored as 9,999,999.")],
       "The value passed in (before the cap).",
       "The difference is also added to the game's lifetime 'gold earned' or 'gold spent' totals.")
define("BMGetPhase", "Returns whose phase it is.", returns="Phase force: 0 player, 1 enemy, 2 allied, 3 other.")
define("BMSetPhase", "Overwrites the current-phase value.", [("force", "Phase force 0–3.")], NONE,
       "Only changes the stored value: no phase change, phase banner or phase events happen.")
define("BMGetTurn", "Returns the turn number.", returns="Current turn (1 on the first turn).")
define("BMSetTurn", "Overwrites the turn counter.", [("turn", "New turn number (kept as a 16-bit value).")], NONE,
       "Turn-based events are checked against the new value from the next turn change; none fire immediately.")
define("GetRank", "Returns the difficulty.", returns="0 Normal, 1 Hard, 2 Maniac, 3 Easy (US build).")
define("Normal", "Tests for Normal or Easy difficulty.", returns="1 on Normal (0) or Easy (3); 0 otherwise.")
define("Hard", "Tests for Hard difficulty.", returns="1 on Hard (1); 0 otherwise.")
define("Maniac", "Tests for Maniac difficulty.", returns="1 on Maniac (2); 0 otherwise.")
define("GetLanguage", "Returns the language ID. The US build has no language setting.", returns="1, always.")
define("GCST", "Returns the event system's state flags.",
       returns="Bit flags: 0x1 the current event is being skipped; 0x2 the current conversation is being skipped; 0x4 skipping is disabled; 0x10 the event is suspended (SuspendEvent or a tutorial dialog); 0x1000 outer link enabled (SetOutLink); 0x2000 finale mode (BeginFinale). Other bits belong to the tutorial and menu code.",
       notes="Scripts normally test only bit 0x1, as the shared *_WhenNotEvtSkip helpers do.")
define("GetBattleType", "Returns the flag word of the current or most recent battle.",
       returns="Bit flags. Bit 0x80000000 is set when the battle was started by NetuzoBattle with its event_battle argument; the shared boss and death-talk helpers test it. Other bits are internal battle state.")
define("EnableSkip", "Lets the player skip the current event again.", notes="Undoes DisableSkip. It does not start a skip.")
define("DisableSkip", "Stops the player from skipping the current event until EnableSkip is called.",
       notes="Death events and other critical scenes set the same flag. Always pair it with EnableSkip.")
define("AchieveSet", "Records one line of the chapter's bonus-experience results: a label and an amount. Used inside achievement (type 12) functions, which the game runs at chapter end; each function that runs fills the next line.",
       [("message_id", "Message ID of the line's label, such as Ms_ach_02_turn."),
        ("amount", "Bonus experience for this line.")],
       notes="The amount is halved on Maniac and multiplied by 1.5 on Easy (rounded down). This is not gold; use BMSetMoney for money.")
define("EnemyDeadCheck", "Tests whether the enemy force is empty.", returns="1 if no unit is left in force 1; 0 otherwise.")
define("ShooterBulletCheck", "Counts the ballista shots spent on the map.",
       returns="Sum, over every ballista on the map, of 5 minus its remaining shots.",
       notes="Assumes five shots per ballista; a ballista with more shots adds a negative amount.")
define("EventGetX", "Returns the X coordinate of the tile that started the current location event (visit, area, chest, door).",
       returns="Map tile X.", notes="Only meaningful inside an event started by a tile.")
define("EventGetY", "Returns the Y coordinate of the tile that started the current location event.",
       returns="Map tile Y.", notes="Only meaningful inside an event started by a tile.")
define("MindGetMe", "Returns the unit performing the current action (the unit that visited, talked, opened a chest, etc.).",
       returns="Unit handle; 0 if there is none.", notes="Only meaningful in events started by a unit action.")
define("MindGetTarget", "Returns the target of the current action (the unit talked to or fought).",
       returns="Unit handle; 0 if there is none.", notes="Only meaningful in talk and battle events.")
define("PersonGetYellLevel", "Returns the support rank between two characters.",
       [("pid1", "First character's PID."), ("pid2", "Second character's PID.")],
       "0 none, 1 C, 2 B, 3 A; -1 if either character has no unit or they are not listed as support partners of each other.")
define("PersonSetYellLevel", "Sets two support partners' support points to the threshold of a rank.",
       [("pid1", "First character's PID."), ("pid2", "Second character's PID."),
        ("stage", "0 = C threshold (C conversation becomes available); 1 = B threshold; 2 = A threshold; 3 = A threshold + 1 (A conversation done).")],
       "The support points written; -1 if either character has no unit or they are not partners.",
       "Writes the same value on both characters. The thresholds come from the first character's support list. Other stage values leave the points unchanged.")

# ---------------------------------------------------------------- flags
define("regist", "Registers a chapter flag in the highest free slot of the 96-slot flag table. The slot's bit is left as it is (chapter start clears these slots).",
       [("flag_name", "Flag name; any string.")], notes="Saves store flag bits by slot, not by name, so keep the registration order when editing a chapter's Startup.")
define("global", "Registers a campaign flag in the lowest free slot of the flag table and clears its bit. The game registers its campaign flags once at boot.",
       [("flag_name", "Flag name; any string.")], notes='global is a .fe9s keyword: call it as extern("global", "name"). Keep the registration order for save compatibility.')
define("get", "Reads a flag.", [("flag_name", "Registered flag name.")], "1 if set; 0 if clear or not registered.")
define("set", "Sets a flag.", [("flag_name", "Registered flag name.")], "0.", "An unregistered name does nothing.")
define("clr", "Clears a flag.", [("flag_name", "Registered flag name.")], "0.", "An unregistered name does nothing.")

# ---------------------------------------------------------------- waits
define("WaitF", "Pauses the script for a number of frames (60 per second).",
       [("frames", "Frame count. 1 or less waits until the next frame.")],
       "1; 0 while the event is being skipped.", f"{SKIP} it does not wait.")
define("WaitM", "Pauses the script for a time in milliseconds.",
       [("duration_ms", "Milliseconds; converted to frames by dividing by 16.67 and rounding down. Under 34 ms waits a single frame.")],
       "1; 0 while the event is being skipped.", f"{SKIP} it does not wait.")
define("isFading", "Tests whether a screen fade started by Fade is still running.", returns="1 while fading; 0 otherwise.",
       notes="FadeWait loops on this.")
define("EffectWait", "Waits for the effect started by EffectPlay to finish.",
       returns="1; 0 while the event is being skipped.",
       notes=f"{SKIP} it removes the effect at once instead of waiting.")
define("UnitMoveWait", "Waits until every unit movement, turn and death/warp animation started by the event has finished.",
       notes="Returns immediately if nothing is moving. UnitMovePos, UnitMoveDir, UnitRotate, Dispos and the other staging calls do not wait by themselves.")

# ---------------------------------------------------------------- camera
CAM = [("yaw", "Horizontal camera angle in degrees."), ("pitch", "Vertical camera angle in degrees (vanilla uses 40–63)."),
       ("distance", "Distance from the looked-at point, in tiles (vanilla uses 10–45).")]
define("Focus", "Moves the map camera smoothly so it looks at the centre of a tile.", [X, Y], "0.",
       f"Does not wait: follow with FocusWait. {SKIP} the camera jumps there at once.")
define("InstantFocus", "Points the map camera at the centre of a tile at once.", [X, Y], "0.")
define("UnitFocus", "Moves the map camera smoothly towards a unit's tile.", [U], "1, even for an invalid unit (which leaves the camera alone).",
       "Does not wait: follow with FocusWait.")
define("FocusWait", "Waits until the map camera has nearly reached its target.",
       returns="1 if it had to wait; 0 if the camera was already there, or during an event skip (the camera jumps to its target).",
       notes="'Nearly': within 1 tile of the target point and 10 units of the target angles and distance. FocusHardWait waits for a closer match.")
define("FocusHardWait", "Like FocusWait, but waits until the camera is within 0.1 tile of its target point and 1 unit of its target angles and distance.",
       returns="1 if it had to wait; 0 if the camera was already there, or during an event skip.")
define("SetMapCamera", "Turns the map camera smoothly to new angles and distance; the point it looks at does not change.", CAM)
define("InstantSetMapCamera", "Sets the map camera's angles and distance at once.", CAM)
define("CopyMapCamera", "Saves the map camera's angles and distance so PastMapCamera can return to them.",
       notes="Saves angles and distance only, not the point looked at. One saved state; a new copy replaces it.")
define("PastMapCamera", "Turns the camera smoothly back to the angles and distance saved by CopyMapCamera.",
       notes=f"Does nothing if nothing was saved. {SKIP} it jumps there at once.")
define("InstantPastMapCamera", "Restores the angles and distance saved by CopyMapCamera at once.", notes="Does nothing if nothing was saved.")
define("CreateEventCamera", "Creates an empty event-camera path. Fill it with SetEventCameraAt and SetEventCameraRot keyframes, then play it with StartEventCamera.",
       notes="Holds up to 256 keyframes. Remove it with DeleteEventCamera when the scene ends.")
define("SetEventCameraPrec", "Sets the divisor applied to later SetEventCameraAt coordinates, allowing positions finer than a tile.",
       [("precision", "Divisor: 1 means coordinates are tiles; 10 means tenths of a tile; 100 hundredths. Vanilla uses 1, 10 and 100.")],
       notes="The setting stays until changed. The default is 1.")
define("SetEventCameraAt", "Adds a keyframe for the point the event camera looks at.",
       [("time_ms", "Time of the keyframe from the start of the path, in milliseconds."),
        ("x", "X in tiles divided by the SetEventCameraPrec divisor; the camera looks at the tile centre (0.5 is added)."),
        ("y", "Y in tiles, same rule as x."),
        ("height", "Height divided by the same divisor (no 0.5 added).")])
define("SetEventCameraRot", "Adds a keyframe for the event camera's angles and distance.",
       [("time_ms", "Time of the keyframe from the start of the path, in milliseconds.")] + CAM,
       notes="Not affected by SetEventCameraPrec.")
define("StartEventCamera", "Plays the event-camera path. Keyframes are joined with a smooth curve; if the path has no keyframe at time 0, the camera's current state is added as the first one.",
       [("easing", "How time advances along the path: 0 even speed, 1 starts slowly, 2 ends slowly, 3 starts and ends slowly.")],
       notes="Does not wait: use EventCameraWait. During an event skip the path ends at once.")
define("EventCameraWait", "Waits until the event-camera path has finished playing.", notes="Returns at once if no path is playing.")
define("DeleteEventCamera", "Removes the event camera and gives control back to the normal map camera.")

# ---------------------------------------------------------------- map objects
OBJ_NOTE = "The change is recorded in the map state, so it is kept in saves."
define("DoorOpen", "Opens the door at a tile with its animation and waits for it. The door stops blocking movement.",
       [X, Y], "1 after the animation; 0 if there is no door there, or during an event skip (the door opens at once).", OBJ_NOTE)
define("DoorClose", "Closes the door at a tile with its animation and waits for it.",
       [X, Y], "1 after the animation; 0 if there is no door there, or during an event skip (the door closes at once).",
       OBJ_NOTE + " The door's hit points are restored to full.")
define("InstantDoorOpen", "Opens the door at a tile without animation.", [X, Y], "1 if a door was found; 0 otherwise.", OBJ_NOTE)
define("InstantDoorClose", "Closes the door at a tile without animation and restores its hit points.", [X, Y], "1 if a door was found; 0 otherwise.", OBJ_NOTE)
define("RoofOpen", "Lifts the roof at a tile with its animation, revealing the building's inside, and waits for it.",
       [X, Y], "1 after the animation; 0 if there is no roof there, or during an event skip (the roof lifts at once).", OBJ_NOTE)
define("RoofClose", "Puts back the roof at a tile with its animation and waits for it.",
       [X, Y], "1 after the animation; 0 if there is no roof there, or during an event skip.", OBJ_NOTE)
define("InstantRoofOpen", "Lifts the roof at a tile without animation.", [X, Y], "1 if a roof was found; 0 otherwise.", OBJ_NOTE)
define("InstantRoofClose", "Puts back the roof at a tile without animation.", [X, Y], "1 if a roof was found; 0 otherwise.", OBJ_NOTE)
define("TBoxOpen", "Plays the opening of the chest at a tile and waits for it, and marks the chest as opened.",
       [X, Y], "1 if a chest was found; 0 otherwise.", "Gives no item: the chest event gives it separately (MindGetItem or UnitGetItemShowing). " + OBJ_NOTE)
define("VisitIn", "Does nothing (kept for the visit-event scripts).",
       [U, X, Y], "1.", "Its arguments are ignored. Vanilla visit events call it with MindGetMe(), EventGetX() and EventGetY().")
define("VisitOut", "Closes the village at a tile after a visit: plays its closing animation, waits for it and marks the village as visited.",
       [("unit", "Ignored; vanilla passes the visiting unit."), X, Y],
       "1 after the animation; 0 if no village is found, or during an event skip (the village closes at once).",
       "The tile may be the village itself or a tile next to it. " + OBJ_NOTE)
define("BuildDestruction", "Destroys the village or house at a tile: the camera moves to it, the ruin animation plays and the script waits for it.",
       [X, Y], "1 after the animation; 0 if none is found, or during an event skip (the building turns into ruins at once).",
       "The tile may be the building or a tile next to it. A destroyed village can no longer be visited. " + OBJ_NOTE)
define("BuildInstShow", "Shows a hideable map prop at a tile.", [X, Y], "1 if one was found; 0 otherwise.", OBJ_NOTE)
define("BuildInstHide", "Hides a hideable map prop at a tile.", [X, Y], "1 if one was found; 0 otherwise.", OBJ_NOTE)
define("BuildInstAnim", "Plays or sets the two-state animation of an animated map prop at a tile.",
       [X, Y, ("mode", "0 plays forward and keeps the end state; 1 plays backward and keeps the start state; 2 plays once without changing the kept state; 3 jumps to the start state; 4 jumps to the end state.")],
       "1; 0 if no animated prop is at the tile, or for mode 2 during an event skip.",
       f"Modes 0 and 1 do not wait. {SKIP} modes 0 and 1 jump to their final state. The kept state is recorded in the map state.")
define("SetTerrain", "Changes the terrain type of one tile.", [X, Y, ("terrain", "Terrain ID (index into the terrain table).")], "0.",
       "Writes the terrain grid only: the map's look does not change, and movement ranges update at the next map refresh (MapUpdate). No coordinate check.")
define("SetShooter", "Places a ballista on a tile.",
       [X, Y, ("facing", "Direction the ballista points: 1 left, 2 right, 4 down, 8 up."),
        ("iid", "Ballista item: IID_LONGARCH, IID_IRONARCH, IID_KILLERARCH or IID_ONAGER.")],
       notes="The ballista starts with the item's full uses. The map needs a ballista model at that tile. " + OBJ_NOTE)
define("ShowMapCursor", "Shows the blinking map cursor on a tile.", [X, Y], notes="Remove it with HideMapCursor.")
define("HideMapCursor", "Removes every map cursor shown by ShowMapCursor.")
define("MapUpdate", "Recalculates the map's occupancy, movement ranges and danger areas after units or terrain changed.", returns=NONE)
define("MapLoad", "Loads a map by name and makes it the current map.", [("map_name", "Map folder name, such as bmap02 or bmap06_2.")],
       notes="Only loads the map: it places no units and runs no chapter setup. The script yields once.")
define("MapReload", "Reloads the current chapter's map, reapplies its recorded map state (opened doors, visited villages, ...) and points the camera at the saved cursor tile.",
       notes="Used when coming back from a tutorial (TutorialResumeOut).")
define("TTPMEntry", "Stores a path for a rolling rock in the first free path slot.",
       [("path", "Direction string: 2 down, 4 left, 6 right, 8 up, one tile per character, for example \"66222\". Kept by reference, not copied.")],
       "Slot 0–31; -1 if all 32 slots are used.", "Give the slot to SetRock. Use a string literal so it stays valid.")
define("AddTT", "Adds a raw entry to the map's special-terrain list.",
       [X, Y, ("type", "Entry type: 4 breakable wall, 7 ballista, 9 pit, 10 rolling rock. Prefer SetFragile, SetShooter, SetPit and SetRock."),
        ("subtype", "Type-specific byte."), ("value_1", "First type-specific state byte."), ("value_2", "Second type-specific state byte.")],
       notes="Low-level: the dedicated calls fill the fields correctly. It does not change the map's look.")

# ---------------------------------------------------------------- deployment
DISPOS_NOTE = "Each unit of the group goes to the free tile nearest its listed position; a character that already has a unit reuses it."
define("Dispos", "Deploys a group: creates each listed unit that is not on the map yet (or reuses the existing one) and animates the units into place. The script waits for the movement.",
       [GROUP], notes=DISPOS_NOTE + " Movement follows the UnitWalk*/UnitFade*/UnitFocus* scene settings. During an event skip the units appear at once.")
define("DisposAsynchronous", "Same as Dispos, but the script continues while the units move.", [GROUP],
       notes="Use UnitMoveWait when later steps need the units in place.")
define("InstantDispos", "Same as Dispos, but places every unit at once without animation.", [GROUP])
define("DisposFirst", "Deploys a group onto its exact listed tiles, without searching for a free tile, and waits for the movement.", [GROUP],
       notes="Meant for the first placement of a chapter, when the listed tiles are known to be empty.")
define("InstantDisposFirst", "Same as DisposFirst, without animation.", [GROUP])
define("DisposContinue", "Moves the units of a group that already exist to the group's positions, and waits for the movement. It never creates units.",
       [GROUP], notes="Units that have acted, are carried, dead, in the reserve or under a roof are skipped. " + DISPOS_NOTE)
define("InstantDisposContinue", "Same as DisposContinue, without animation.", [GROUP])
define("InstantDisposRank", "Deploys the difficulty variant of a group at once: adds \"_n\" to the name on Normal, \"_h\" on Hard and \"_m\" on Maniac or Easy, then works like InstantDispos.",
       [("group", "Group name without the difficulty suffix.")], notes="The finished name must exist for each difficulty you support.")
define("DisposAuxiliary", "Deploys the units the player picked for the second team (SelectAuxiliary) onto the group's tiles and moves them from the reserve to the player force.",
       [("group", "Deployment group that holds the second team's positions.")],
       notes="Does nothing when no unit was picked. The script waits for the movement.")
define("Join", "Adds the characters of a deployment group to the player's reserve (force 5), off the map. Characters that already have a unit keep it.",
       [GROUP], "1; 0 if group is not a valid string.",
       "Used to recruit characters between chapters, for example the always_T_* groups added by TrialAddUnit.")
define("SallySetByGroup", "Replaces the preparation screen's deployment tiles with the tiles of a group.", [GROUP],
       notes="Each record of the group gives one deployment tile; the units in the records are not created.")
define("SallyAddByGroup", "Adds the tiles of a group to the preparation screen's deployment tiles.", [GROUP])
define("UnitForcedSally", "Makes a unit mandatory in the preparations: the player cannot remove it from the deployment.", [U], VALID,
       "Only applies to units of the player force or the reserve.")
define("UnitDontMoveSally", "Locks a unit's starting tile in the preparations: the player cannot swap its position.", [U], VALID,
       "Only applies to units of the player force or the reserve. UnitDontMoveSallyByPID also makes the unit mandatory.")

# ---------------------------------------------------------------- whole-army state
define("UnitsInitialize", "Removes every unit: all forces are emptied and all unit slots freed.",
       notes="Also frees the unit models and clears the battle state. Not a chapter reset: flags, money and map state are kept.")
define("UnitsPush", "Saves every unit (and the forge records) into a temporary buffer, then empties the forces.",
       notes="One buffer is shared by UnitsPush, UnitsPush_Uninitialize and AllPush; a second push before the matching pop loses the first.")
define("UnitsPush_Uninitialize", "Saves every unit (and the forge records) into the temporary buffer, leaving the units in place.",
       notes="Same shared buffer as UnitsPush.")
define("UnitsPop", "Restores the units saved by UnitsPush, refreshes the map and reloads the unit models. Frees the buffer.",
       notes="Units created since the push are discarded.")
define("UnitsPopWithoutMap", "Same as UnitsPop, without the map refresh.", notes="Call MapUpdate afterwards.")
define("AllPush", "Saves the whole game state into the temporary buffer (party data, camera, every unit, convoy, forge records and map state), then resets units, chapter flags, map state, convoy and forge records.",
       notes="Used by TutorialIn so a tutorial can run in a clean state. Same shared buffer as UnitsPush.")
define("AllPop", "Restores the game state saved by AllPush and frees the buffer.",
       notes="Chapter flags set during the tutorial are cleared first. Map and models are not reloaded: TutorialResumeOut follows it with MapReload and UnitDispReload.")
define("UnitDispReload", "Unloads and reloads the map models of every unit in forces 0–3, then refreshes their positions.")
define("AllUnitEscape", "Removes every unit of forces 0–3 from the map: carried units are dropped first, player units go to the reserve marked as escaped, all other units are deleted.",
       notes="The map is refreshed afterwards.")
define("ForceGetCount", "Counts the units in a force.", [FORCE], "Number of units in that force.",
       "No range check: use 0–7.")
define("ForceGetFirst", "Returns the first unit of a force, to walk it with UnitGetNext.", [FORCE],
       "Unit handle; 0 if the force is empty.", "No range check: use 0–7.")

# ---------------------------------------------------------------- one unit
define("UnitGetNext", "Returns the next unit in the same force.", [U], "Unit handle; 0 at the end of the force or for a null unit.",
       "Moving units between forces while walking a force changes the order.")
define("UnitGetForce", "Returns a unit's force.", [U], "Force ID 0–7; 0 for an invalid unit (indistinguishable from force 0).")
define("UnitGetX", "Returns a unit's tile X.", [U], "Tile X; 0 for handle 0.", "Does not check that the slot holds a character.")
define("UnitGetY", "Returns a unit's tile Y.", [U], "Tile Y; 0 for handle 0.", "Does not check that the slot holds a character.")
define("UnitGetHP", "Returns a unit's current HP.", [U], "Current HP; 0 for handle 0.")
define("UnitGetMaxHP", "Returns a unit's maximum HP, including the bonus of the equipped weapon and item, capped by the class.", [U], "Maximum HP; 0 for handle 0.")
define("UnitSetHP", "Sets a unit's current HP.", [U, ("hp", "New HP; kept between 0 and the unit's maximum HP.")], "0.",
       "Setting 0 does not kill the unit or start a death event.")
define("UnitSetEXP", "Sets a unit's experience.", [U, ("exp", "0–100, or 255 for 'cannot gain experience'. Other values are ignored.")], "0.",
       "No level-up happens, even at 100.")
define("UnitGetStatus", "Returns a unit's state flags.", [U],
       "Bit flags: 0x1 has acted this turn; 0x2 carrying a unit; 0x4 carried; 0x8 dead/inactive; 0x10 in the reserve; 0x20 off screen; 0x40 hidden by fog; 0x80 under a roof; 0x100 group commander; 0x4000 escaped; 0x8000 died this chapter; 0x10000 mandatory in preparations; 0x20000 position locked in preparations; 0x100000 cannot Give or Drop a carried unit; 0x200000 cannot be picked for the second team; 0x400000 picked for the second team. 0 for an invalid unit.")
define("UnitSetStatus", "Sets state flags on a unit.", [U, ("mask", "Bits to set; see UnitGetStatus.")],
       "The unit's new flag word; 0 for an invalid unit.",
       "Vanilla scripts set 0x100000, 0x200000, 0x400000 and 0x1. Setting bookkeeping bits such as 0x2, 0x4 or 0x8 by hand desynchronises the unit.")
define("UnitClrStatus", "Clears state flags on a unit.", [U, ("mask", "Bits to clear; see UnitGetStatus.")],
       "The unit's new flag word; 0 for an invalid unit.")
define("UnitQueryPID", "Tests whether a unit is a given character.", [U, P], "1 if it is; 0 otherwise or for handle 0.")
define("UnitQueryJID", "Tests whether a unit has a given class.", [U, ("jid", "Exact JID_... class ID.")],
       "1 if it is that exact class; 0 otherwise or for handle 0.", "The match is exact: a promoted or female variant is a different JID.")
define("UnitTransferToForce", "Moves a unit to another force, for example to recruit it (force 0) or turn it into an ally (2).",
       [U, FORCE], VALID,
       "The unit takes the army group of the destination force's first group commander, if there is one. Moving to the player, allied or other force clears its item-drop marks. Its map model is reloaded in the new army colour.")
define("UnitEscape", "Takes a unit off the map: a carried unit is dropped first; a player unit goes to the reserve marked as escaped; a unit of any other force is deleted.",
       [U, ("unused", "Ignored; the shared helper passes 0.")], VALID, "The map is refreshed afterwards.")
define("UnitDead", "Plays the death fade-out of a unit's map model (with its sound) and waits for it.",
       [U], "1; 0 for an invalid unit or during an event skip (nothing is played).",
       "Visual only: the unit is hidden but stays in its force. Remove it with UnitEscape or UnitTransferToForce if needed.")
define("UnitWarpOut", "Plays the Warp effect on a unit and waits for it.",
       [U], "1; 0 for an invalid unit or during an event skip (nothing is played).",
       "Visual only: the unit's force and tile do not change. Remove or move it separately.")
define("UnitBreakup", "Separates a carrying pair: the carried unit is put back on the map on the carrier's tile. Either unit of the pair can be given.",
       [U], "1 for a valid unit; 0 otherwise.",
       "Both units are marked as not having acted. Only call it on a unit that is carrying or carried (status 0x2 or 0x4), as UnitCheckLinked_Breakup does.")
define("UnitClassChange", "Plays the class-change (promotion) scene for a unit and promotes it, and waits for it.",
       [U], "1; 0 for an invalid unit or a unit without the SID_EVENTCC skill.",
       "Only works on units that have SID_EVENTCC. The new class is the class's promotion class.")
define("UnitFadeIn", "Makes later scripted movement fade units in (they appear as they move).",
       notes="A scene setting used by Dispos and UnitMove* calls; turn it off with UnitFadeOff.")
define("UnitFadeOut", "Makes later scripted movement fade units out (they disappear as they move).", notes="Turn it off with UnitFadeOff.")
define("UnitFadeOff", "Ends UnitFadeIn/UnitFadeOut: later movement shows units normally.")
define("UnitFocusOn", "Makes the camera follow units during later scripted movement (the default).")
define("UnitFocusOff", "Stops the camera from following units during later scripted movement.")
define("UnitMovePos", "Walks a unit to a tile along a real path. If the tile is taken, the nearest free tile the unit can reach is used.",
       [U, X, Y], VALID,
       f"Does not wait: use UnitMoveWait. If no tile is reachable, the unit does not move. {SKIP} the unit appears there at once. Speed, fading and camera follow come from the UnitWalkSlow/UnitFade*/UnitFocus* settings.")
define("UnitMoveDir", "Walks a unit along a list of steps, ignoring terrain and other units.",
       [U, ("path", "One character per step: 2 down, 4 left, 6 right, 8 up. The letters L, R, U and D make the unit face left, right, up or down at the end. Example: \"6662L\".")],
       VALID,
       f"Does not wait: use UnitMoveWait. The unit's tile changes to the end of the path at once. {SKIP} it appears there directly.")
define("UnitSetPos", "Places a unit on a tile at once. If the tile is taken, the nearest free tile is used.", [U, X, Y], VALID,
       "Unlike UnitMovePos, the unit's movement range is not considered.")
define("UnitRotate", "Turns a unit to face a direction.",
       [U, ("direction", "1 left, 2 right, 4 down, 8 up; add two for a diagonal (5 down-left, 6 down-right, 9 up-left, 10 up-right)."),
        ("duration_ms", "Turning time in milliseconds; 0 turns at once.")],
       VALID, f"Does not wait: use UnitMoveWait. {SKIP} the unit turns at once.")
define("UnitAddItem", "Puts an item in a unit's inventory, silently: weapons, tomes and staves go to the first free weapon slot (0–3), items and accessories to the first free item slot (4–7).",
       [U, ("item_id", "IID_... item ID.")], VALID,
       "If those slots are full, the item is not added, but the call still returns 1. To show the 'got item' window, use UnitGetItemShowing.")
define("UnitDelItem", "Removes the item in an inventory slot and closes the gap.", [U, SLOT], VALID)
define("UnitSearchItem", "Finds an item in a unit's inventory.", [U, ("item_id", "IID_... item ID.")],
       "Slot 0–7 of the first copy; -1 if the unit does not carry it; 0 for an invalid unit.",
       "0 is also a valid slot, so check the unit first.")
define("UnitGetItemCount", "Counts the items a unit carries, weapons included.", [U], "0–8; 0 for an invalid unit.")
define("UnitGetWeaponCount", "Counts the weapons a unit carries (its four weapon slots).", [U], "0–4; 0 for an invalid unit.")
define("UnitItemGetValuation", "Returns a value score for an inventory item, used to pick which item to send away.",
       [U, SLOT], "Item price multiplied by its remaining uses, plus fixed bonuses for special items (character- or class-locked weapons add 50,000); 0 for an empty slot or invalid unit.",
       "Only meaningful for comparing items, as UnitItemSendToHouseByPID does.")
define("UnitItemSendtoWarehouse", "Sends one inventory item to the convoy.", [U, SLOT],
       "1 if sent; 0 for an invalid unit, an empty slot, or before the convoy is available (internal chapter numbers 1–8, Prologue to Chapter 7).",
       "If the convoy is full, its least valuable item is deleted to make room.")
define("UnitItemSetDrop", "Marks one inventory item as dropped when the unit is defeated.", [U, SLOT],
       "1 if marked; 0 if the unit already has a dropped item, the slot is empty or the unit is invalid.",
       "Only one item per unit can be marked.")
define("UnitSetEquip", "Equips an inventory item.",
       [U, ("slot", "0–3 equips that weapon; -1 equips the first weapon the unit can use; 4–7 equips that item if it is equippable (bands, rings).")],
       VALID,
       "The other slots of the same half are unequipped first, so a slot the unit cannot use leaves it with nothing equipped there. Laguz units are not changed. Equipping a weapon updates the weapon held by the map model.")
define("UnitSetWeaponAway", "Unequips the unit's weapon.", [U],
       "The weapon slot 0–3 that was equipped; -1 if none was equipped or the unit is a laguz; 0 for an invalid unit.",
       "The map model is updated to hold no weapon.")
define("UnitSetAccAway", "Unequips the unit's equipped item (band or ring).", [U],
       "The item slot 4–7 that was equipped; -1 if none was; 0 for an invalid unit.")
define("UnitAddSkill", "Gives a unit a skill.", [U, ("skill_id", "SID_... skill ID.")], VALID,
       "Adds it to the unit's runtime skill set; skill capacity is not checked. An unknown SID does nothing.")
define("UnitClrSkill", "Removes a skill from a unit.", [U, ("skill_id", "SID_... skill ID.")], VALID,
       "Removes it from the unit's runtime skill set.")
define("UnitTstSkill", "Tests whether a unit holds a skill.", [U, ("skill_id", "SID_... skill ID.")],
       "1 if the unit holds it; 0 otherwise or for an invalid unit.")
define("UnitSetCpAttackSeq", "Changes the attack AI script of a unit.", [U, ("sequence", "SEQ_... AI script name from the AI data.")], VALID,
       "The script restarts from its first step. An unknown name leaves the old script in place.")
define("UnitSetCpMoveSeq", "Changes the movement AI script of a unit.", [U, ("sequence", "SEQ_... AI script name from the AI data.")], VALID,
       "The script restarts from its first step. An unknown name leaves the old script in place.")
define("UnitSetCpHealSeq", "Changes the healing AI record of a unit.", [U, ("record", "Name of a healing record in the AI data.")], VALID,
       "An unknown name leaves the old setting in place.")
define("UnitSetCpMTypeID", "Changes the MTYPE AI table of a unit (how it values targets).", [U, ("table", "MTYPE_... table name from the AI data.")], VALID,
       "An unknown name leaves the old table in place.")

# ---------------------------------------------------------------- conversations and screens
define("TalkEvent", "Opens the conversation window with a message and pauses the script until the conversation ends or reaches a $H hold point.",
       [MS], notes="If a conversation window is already open, the new message plays in it. After a $H hold, continue with TalkResume. During a skip the text is processed at once without being shown.")
define("TalkResume", "Continues a conversation stopped at a $H hold point and pauses the script again until it ends or reaches the next hold.",
       notes="Only call it while a conversation is held.")
define("TalkExist", "Tests whether a conversation is still running.", returns="1 while a conversation window is open and not finished; 0 otherwise.")
define("MoviePlay", "Plays a movie file and pauses the script until it ends.",
       [("path", "Path of a THP file on the disc, such as \"movie/s01.thp\".")],
       "1; 0 during an event skip (nothing is played) or for an invalid string.",
       "A missing file plays the placeholder movie/dummy.thp. The sound channels are faded out.")
define("ChapterMoviePlay", "Plays the movie of a chapter and pauses the script until it ends.",
       [("chapter", "Chapter number whose movie is played. It does not change the current chapter.")],
       "1; 0 during an event skip (nothing is played).")
define("ProcExists", "Tests whether an engine process with a given name is running.",
       [("process_name", "Process name such as E_PadActor or E_TurnToken (not a script function).")],
       "Nonzero if one is running; 0 otherwise.")
define("ProcKill", "Stops every engine process with a given name.", [("process_name", "Process name such as E_Popup.")], "0.",
       "Stopping a process the game still needs can break the scene.")
define("RectBuild", "Creates an image (rectangle) from its RID definition, attached to the current event. RID_GMAP_... names create a world-map view.",
       [("rect_id", "RID_... image definition name.")], "0.", "Remove it with RectKill or RectFadeOutDelete.")
define("RectKill", "Removes an image created by RectBuild or RectLeave.", [("rect_id", "RID_... name.")], "0.")
define("RectPreLoad", "Starts loading the image files of a RID definition, so a later RectBuild shows it without delay.",
       [("rect_id", "RID_... image definition name.")], NONE, "Wait with PreLoadWait if the images must be ready.")

# ---------------------------------------------------------------- scripts and event flow
define("CmFreeScript", "Unloads the most recently loaded script file and removes its named functions.",
       returns="1; 0 if no script is loaded.", notes="Always the last one loaded: there is no name argument.")
define("CmWakeupScripts", "Wakes every script file put to sleep by CmSleepScript and makes its named functions callable again.", returns=NONE)
define("SuspendEvent", "Freezes the running event so another script (a tutorial) can run, saving the event's state.", returns=NONE,
       notes="Pair it with ResumeEvent. The camera is protected from map input while suspended.")
define("ResumeEvent", "Continues the event frozen by SuspendEvent.", returns=NONE)
define("GameBind", "Freezes the map's normal game flow (phases, cursor, menus) while the script works.",
       notes="Undo with GameUnbind. The tutorial helpers wrap their steps in this pair.")
define("GameUnbind", "Lets the map's game flow continue after GameBind.")
define("TutorialCall", "Starts a named function of a loaded tutorial script and stops the AI phase.",
       [("entry_name", "Name of a function in a loaded script, such as tut_02_Visit.")], "1 if the function exists; 0 otherwise.")
define("TutorialResume", "Returns to the tutorial menu after a tutorial ends (the last step of ComebackFunc).", returns=NONE)
define("TutorialBasesCreate", "Opens the base menu inside a tutorial.")
define("TutorialBasesDelete", "Closes the base menu opened by TutorialBasesCreate.")
define("TutorialSallyCreate", "Opens the preparations screen inside a tutorial.")
define("TutorialSallyDelete", "Closes the preparations screen opened by TutorialSallyCreate.")

# ---------------------------------------------------------------- startup.cmb internals
define("_gi", "Gives an item to a unit and shows the result window (the step behind UnitGetItemShowing).",
       [U, ("item_id", "IID_... item ID.")], "1; 0 for an invalid unit.",
       "A player unit shows 'got item'; an enemy unit shows 'item taken' and the item is marked as its drop. When a player or reserve unit's inventory is full, the game opens the window to send an item to the convoy or discard one. The script waits for the window.")
define("td", "Opens a tutorial dialog with a message and pauses the script until it closes.",
       [MS], "0.", "A message with a line break uses the two-line layout. TutorialDialog calls this, yields once, then calls tde.")
define("tde", "Sets the 'event suspended' state flag again after a tutorial dialog cleared it (the last step of TutorialDialog).")
define("_tt", "Starts a tutorial conversation with a message (the step behind TutTalkEvent).", [MS],
       notes="Unlike TalkEvent it does not pause the script: the helper waits with TalkExist.")
define("_tr", "Continues a held tutorial conversation (the step behind TutTalkResume).",
       notes="Unlike TalkResume it does not pause the script: the helper waits with TalkExist.")
define("_pa", "Plays a scripted controller input (the 'pad actor' that moves the cursor and presses buttons in tutorials). Each character is one step: a one-frame press, then a pause until the next step.",
       [("command", "Step characters: 1–4 and 6–9 press the control stick and D-pad in the numeric-keypad direction (8 up, 2 down, 4 left, 6 right, 7/9/1/3 diagonals); A, B, X, Y, Z, L, R press that button; S presses Start; any other character (such as 5 or a space) presses nothing. < halves and > doubles the step length (16 frames at first) without using a step.")],
       notes="The player's real input is ignored while it plays. TutPadActor calls this and waits while E_PadActor runs. Example: \"66A\" moves right twice, then presses A, one step (16 frames) apart.")
define("_cmb_mess_load", "Loads a script file and a message file together (the step behind TutEntryCommon).",
       [("script_path", "Path of the .cmb file, such as scripts/c80.cmb."), ("message_path", "Path of the message file; the helper passes mess/tut.m.")])
define("_mf1", "First step of MapFree: releases the map's objects if a map is loaded.", returns="1 if a map was loaded; 0 otherwise.")
define("_mf2", "Second step of MapFree: frees the current map.")
define("_pldone", "Tests whether files queued for loading (RectPreLoad, PreLoad) are ready.",
       returns="1 when nothing is still loading; 0 otherwise.", notes="PreLoadWait loops on this.")
define("_seqini", "Clears the map for a tutorial: removes conversations, images, scripted input, the preparations, AI phase and phase banner, the notice frame and the unit models.",
       notes="First step of TutorialInit.")
define("_bmsini", "Resets the chapter for a tutorial: chapter number 0 (so the convoy is available), turn 1, the player controls force 0 and the computer forces 1–3, 1,000 gold, chapter flags and gf_complete/gf_gameover cleared, no units, empty convoy, no forge records, map state cleared.",
       notes="Called by TutorialInit after _seqini.")
for name, what in [("taikitk", "a unit's next Wait command (E_TaikiToken)"),
                   ("turntk", "the next turn change (E_TurnToken)"),
                   ("turnatk", "the next end of turn (E_TurnAToken)")]:
    define(name, f"Starts a waiting token that lasts until {what}.",
           notes="The tutorial helpers TutWaitForNextTaiki, TutWaitForNextTurn and TutWaitForNextTurnAfter call it and wait while the token exists.")


# Corrections to startup.cmb helper entries, from the native calls they wrap.
HELPER_NOTES = {
    "TutPadActor": dict(notes="The command string is passed to _pa unchanged; use strings from the vanilla tutorial scripts."),
    "TutWaitForNextTaiki": dict(notes="The token ends at the player's next Wait command."),
    "TutWaitForNextTurn": dict(notes="The token ends at the next turn change."),
    "TutWaitForNextTurnAfter": dict(notes="The token ends at the next end of turn."),
    "TutWaitM": dict(notes="duration_ms × 60 / 1000 yields, one frame each."),
    "TutorialResumeOut": dict(notes="Runs the chapter's Startup again, so flag registration order must stay stable."),
    "UnitGetItemShowing": dict(notes="No null check. _gi shows the item window and handles a full inventory (convoy/discard choice for player units)."),
    "UnitSetWeaponAwayByPID": dict(returns="-2 if the character has no unit; otherwise UnitSetWeaponAway's result (the slot that was equipped, or -1)."),
    "UnitTransferToForceByPID": dict(notes="Unlike the movement helpers, it does not require the unit to be in forces 0–3: a living reserve unit passes."),
    "UnitMoveDirByPID": dict(notes="Does not wait: use UnitMoveWait."),
    "UnitMovePosByPID": dict(notes="Does not wait: use UnitMoveWait."),
    "UnitRotateByPID": dict(notes="Does not wait: use UnitMoveWait."),
    "TutorialDialog": dict(notes="td pauses the script until the dialog closes; tde then marks the event as suspended."),
}
