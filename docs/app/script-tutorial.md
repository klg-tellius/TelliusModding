# Modding chapter events with Python-style scripts

This course teaches the app's `.fe9s` language, from a first event to a coordinated chapter overhaul. It covers the known **US Path of Radiance** event system. `.fe9s` is compiled into the game's `.cmb` bytecode; the game does not execute Python. Radiant Dawn, other regions, and a completely new campaign require additional verification. The function reference explains the available authoring calls, including their argument order, results, and important restrictions.

Read the lessons in order the first time. Keep the [language reference](script-language.md), [function reference](script-call-reference.md), and [game-side script reference](https://klg-tellius.github.io/TelliusModding/#/events-scripting) alongside this guide. The code blocks tagged `fe9s` are compile-checked examples. Compilation proves syntax and encodability, not that a message, unit, map section, or event context exists at runtime.

## Contents

1. [Choose the right layer](#1-choose-the-right-layer)
2. [Prepare and make one small edit](#2-prepare-and-make-one-small-edit)
3. [Read a chapter](#3-read-a-chapter)
4. [Learn the language](#4-learn-the-language)
5. [Flags and one-time events](#5-flags-and-one-time-events)
6. [First playable exercise: an item on turn two](#6-first-playable-exercise-an-item-on-turn-two)
7. [Triggers](#7-triggers)
8. [Dialogue and scene timing](#8-dialogue-and-scene-timing)
9. [Reinforcements and deployment](#9-reinforcements-and-deployment)
10. [Movement, cameras, and sound](#10-movement-cameras-and-sound)
11. [Visits, chests, doors, and area events](#11-visits-chests-doors-and-area-events)
12. [Recruitment and unit state](#12-recruitment-and-unit-state)
13. [Objectives, defeat, and rewards](#13-objectives-defeat-and-rewards)
14. [Battle, death, support, and base conversations](#14-battle-death-support-and-base-conversations)
15. [Difficulty and branching scenes](#15-difficulty-and-branching-scenes)
16. [Shared functions and module lifetime](#16-shared-functions-and-module-lifetime)
17. [Advanced storage and assembly](#17-advanced-storage-and-assembly)
18. [Build a chapter overhaul](#18-build-a-chapter-overhaul)
19. [Validate and troubleshoot](#19-validate-and-troubleshoot)
20. [Command-line workflow](#20-command-line-workflow)
21. [Coverage and remaining limits](#21-coverage-and-remaining-limits)

## 1. Choose the right layer

An event script decides **when** something happens and invokes engine operations. Referenced data decides **what** exists. For example, `Dispos("some_group")` needs an actual deployment section; writing its name does not create soldiers.

| Desired change | What to edit with the script |
|---|---|
| Change a line or add a conversation | Message entry in `Mess/cNN.m`; portrait/name resources if needed |
| Place reinforcements or change enemies | A section in the chapter's `dispos.cmp`, its unit records, and referenced character/class/item data |
| Recruit a unit | Its actual actor and force/roster transitions; later deployment and story checks |
| Change a victory condition | Condition logic, displayed objective, completion scene, and competing old conditions |
| Add a visit, chest, door, or escape | Event coordinates, terrain/action availability, prop state, and reward logic |
| Change a map | Terrain, dimensions, heights, map models, props, deployment coordinates, and event coordinates |
| Add an item, skill, or class | `FE8Data.bin` and associated text/assets; native code if the behavior is new |
| Change combat formulas or invent a mechanic | Usually `main.dol`; no arbitrary Python execution inside the game |
| Change music or movies | Existing IDs and selection calls, plus audio/video assets for new content |
| Add a chapter beyond the campaign | Files plus native progression/loading changes; copying files alone is insufficient |

Use [workspace features](workspace-and-features.md) for editing tools and the [game-system index](https://klg-tellius.github.io/TelliusModding/#/main) for each format. Start by replacing content inside a reachable chapter. File 01 is the Prologue, file 02 is displayed Chapter 1; do not assume the displayed number is the filename number.

## 2. Prepare and make one small edit

1. Open a project for the intended game/build and extract it. Keep a known-good disc and a copy of the extracted files you will change.
2. Build and boot the unedited project once. This separates extraction/build problems from scripting problems.
3. Open the chapter's **Scripts** tab. Locate an existing `TalkEvent` call and inspect the corresponding message. Change one existing message ID to another valid message from that chapter, preferably one that initializes its own dialogue state.
4. Press **Check**. Read warnings as well as errors. A typo in a function name can compile but do nothing in game.
5. Press **Save**, build the project, and boot the rebuilt image in Dolphin. Enter the chapter from a save before its setup runs.
6. Confirm the new message appears. Restore the original call before continuing if it was only a test.

Saving writes the chapter's `Scripts/CNN.cmb` immediately in `extracted/files/`. The app also retains editable names/comments in `script_sources/CNN.fe9s`. A first script save backs up the original file. These mechanisms are useful, but a separate known-good copy is still needed for coordinated changes to several files.

The **Function** form edits the selected function's name, export and trigger metadata. **Apply to code** applies that form to the source. **New / Duplicate / Delete** modify source functions. **Bytecode** shows the compiled instructions. **Revert to file** discards unsaved source edits.

If another tool changes the `.cmb`, the app decompiles it again and preserves the previous source as `.fe9s.bak`; do not assume old source comments still describe the new binary.

## 3. Read a chapter

Before adding anything, make a short inventory:

| Find | Why it matters |
|---|---|
| `@export def Startup()` | Registers flags and performs chapter initialization |
| `Opening0`, `Opening2`, and other existing exports | Opening/preparation stages and engine callbacks; preserve the chapter's existing structure |
| `RegistLocationFlags`, `RegistLocationTT`, `FinalDisposition`, `RestoreSallyDisposition`, if present | Supporting setup callbacks; their mere presence in a chapter is not permission to remove them |
| `@before_phase`, `@on_phase`, `@after_action` | Turn schedule and repeated condition checks |
| `@on_location`, `@on_area`, `@on_talk` | Map interactions |
| `@on_complete`, `@on_gameover`, `@on_scenario_end` | Endings, defeat handling, and post-scenario results |
| `regist`, `get`, `set`, `clr` | Dependencies between events |
| `Dispos`, `InstantDispos`, difficulty helpers | Which deployment groups are actually loaded |

Functions without exports still have local source names such as `func_12`. Those names are editable conveniences. Their order becomes the binary function-table index. An export is a runtime name; other scripts or native code may depend on its exact spelling.

Do not replace a chapter file with one of this guide's small examples. Examples are additions or focused replacements inside a complete chapter. In particular, merge initialization into the existing `Startup`; never create a second export named `Startup`.

## 4. Learn the language

Use four spaces per indentation level and double-quoted strings. Function and variable names use letters, digits and underscores. This language supports only its documented grammar: Python imports, objects, dictionaries, comprehensions, `for`, exceptions and Python library calls are unavailable.

```fe9s
def reward_amount(turn):
    amount = 200
    if turn > 6:
        amount -= (turn - 6) * 10
    if amount < 0:
        amount = 0
    return amount

def example_total():
    total = 0
    i = 0
    while i < 3:
        total += reward_amount(i + 6)
        i += 1
    return total
```

Arguments occupy local slots, followed by local variables. An assignment can introduce a local. `var x = 7` is also supported, but reproduces an original-compiler pattern that leaves a temporary value on the evaluation stack until return. Use ordinary assignments inside loops to avoid accumulating those temporary values.

Values are VM words, not Python objects: arithmetic operates on 32-bit game values, `/` is integer division, and strings are references to encoded text. Do not rely on Python's arbitrary-size integers or floating-point division. Avoid division by zero and unverified overflow/shift behavior.

Use `streq(a, b)` or `strne(a, b)` for string contents. `==` compares word values and is not a content comparison for text. `and` and `or` short-circuit, but their short-circuit paths normalize to 0/1; do not use Python's operand-return idioms to choose an object or string. Write an `if` instead.

```fe9s
def choose_message(use_first):
    if use_first:
        return "MS_FIRST"
    return "MS_SECOND"

def bounded_loop():
    i = 0
    while True:
        i += 1
        if i == 2:
            continue
        if i >= 4:
            break
    return i
```

`MS_FIRST` and `MS_SECOND` above are demonstration strings, not supplied message entries. A compiled string is not proof of an asset's existence.

`return` without an expression returns 0. Ordinary functions also receive an implicit `return 0`. A call used as a statement discards its return value automatically. `yield` pauses the VM until the engine resumes it; it is not a Python generator and does not return data to Python.

Keep parentheses around mixed boolean, bitmask, and comparison expressions. The full precedence order and assignment operators are in the [language reference](script-language.md#expressions).

## 5. Flags and one-time events

A trigger determines when the engine may call a function. A flag makes your own logic remember whether work has happened. The game keeps flags in one table of 96 named bits; a name means nothing until it is registered, and `set`, `clr` and `get` on an unregistered name silently do nothing and read 0. The compiler warns about that case, so read its warnings. Use a distinctive name such as `mod_c02_reward_done`.

```fe9s
def register_mod_flags():
    regist("mod_c02_reward_done")
    regist("mod_c02_wave_done")

def example_flag_operations():
    if not get("mod_c02_reward_done"):
        set("mod_c02_reward_done")
    # Clearing permits the guarded work to run again.
    # Do not put this in a repeating event unless repetition is intended.
    clr("mod_c02_wave_done")
```

Add `register_mod_flags()` as the **last** line of the chapter's existing `Startup`, after every existing registration. This helper does not run merely because it is defined.

Set a flag before launching a long scene when it means “event has begun”; set it after the operation when it means “reward has been applied.” Choose deliberately and test skip/interruption paths. Registering or clearing flags every turn can undo your one-time guard.

How long a flag lasts depends only on how it is registered:

| Kind | Register with | Lives | Saved |
|---|---|---|---|
| Chapter flag | `regist("name")` in the chapter's `Startup` | Until the next chapter starts | Yes (a mid-chapter save keeps it) |
| Campaign flag | `global("name")` in `startup.cmb`'s `RegistGlobalFlags` | The whole playthrough | Yes |

A save keeps only the bits, not the names. When a save loads, the game runs the same registrations again and hands each saved bit back to whichever name now occupies its slot. Chapter flags take slots from the top in registration order, campaign flags from the bottom. Two consequences:

- Always add registrations **after** the existing ones. Inserting one earlier shifts every later flag of that chapter, and older saves then load with the wrong flags set.
- The table has 96 slots and needs at least one left free. Vanilla uses 30 for campaign flags and at most 58 for one chapter (file 18), so a chapter has room for about 7 more, fewer if you add campaign flags. The compiler warns when a chapter's `Startup` fills the table.

The **Flags** page does both without writing code: **Add campaign flag…** and **Add chapter flag…** append the registration in the right place, and the Chapter flags tab shows how many slots a chapter has left. To do it by hand, pick `startup.cmb` in the Script tab's **File** box and append to `RegistGlobalFlags` (it is decompiled as `extern("global", "...")`, because `global` is a language keyword):

This abbreviated fragment shows where to append the new registration. It is
not a replacement function: keep every existing registration in its original
order, including all lines represented by the comment.

```text
def RegistGlobalFlags():
    extern("global", "G_シノン死亡")
    # ... the other existing lines, unchanged ...
    extern("global", "DBG_最初からやってる")
    extern("global", "G_mod_spared_boss")
```

Any chapter can then `set("G_mod_spared_boss")` or test `get("G_mod_spared_boss")` without registering it. Three vanilla entries are unused placeholders named `G_リザーブド`; renaming one of them in place also works and keeps the slot count unchanged. Never call `global` from a chapter script: the name would point into a script the game unloads when the chapter ends. The script editor reads your project's `startup.cmb`, so its warnings know about the campaign flags you add.

To check a flag in a real save, open it in the Flags page's **Save file** tab: every flag is listed by name, and a double-click switches it (the save block's checksum is recomputed on save). The same is available from the command line: `python -m fe_modding.formats.event_flags <save.gci> --scripts <extracted Scripts folder> [--set NAME] [--clr NAME]`.

## 6. First playable exercise: an item on turn two

Use file 02 (displayed Chapter 1), where Ike is available. Append these functions, then call `mod_register_reward_flag()` at the end of the existing `Startup`:

```fe9s
def mod_register_reward_flag():
    regist("mod_c02_reward_done")

@on_phase(turn_from=2, turn_to=2, phase="player")
def mod_turn_two_reward():
    if get("mod_c02_reward_done"):
        return 0
    unit = UnitGetByPID("PID_IKE")
    if not unit:
        return 0
    UnitGetItemShowing(unit, "IID_HPDROP")
    set("mod_c02_reward_done")
```

`UnitGetByPID` returns a unit reference, not a character ID string. Check it before passing it to a call that expects a unit. `IID_HPDROP` is an existing item ID used by the chapter's original visit reward; confirm it in your project's data.

Build, enter the chapter before setup, and reach player turn two. Expected result: Ike receives the item through the existing showing/reward operation. Advance another turn to check that it does not repeat. Also test a full inventory; do not assume the item-disposal path behaves identically to an empty inventory.

If Ike is absent when the event runs, this example does nothing. Its exact-turn trigger does not promise a retry on turn three. To design retries, use an every-turn trigger plus a guard and define when retries should stop.

## 7. Triggers

Decorator parameters are compile-time constants, not expressions evaluated every turn. Supply them explicitly for new events; omitted parameters generally become zero, with special defaults for completion/gameover flags.

| Type | Decorator and parameters | Use and caveat |
|---|---|---|
| 0 | No trigger decorator | Called by another function or an engine-recognized exported name |
| 1 | `@on_complete(flag="gf_complete")` | Existing map-completion flow |
| 2 | `@on_gameover(flag="gf_gameover")` | Existing failure flow |
| 3 | `@before_phase(turn_from=3, turn_to=3, phase="player")` | Before the phase banner |
| 4 | `@on_area(x1=4, y1=5, x2=6, y2=7, side="player", name="mod_zone")` | A unit enters the configured zone |
| 5 | `@on_location(x=4, y=11, action="visit", name="mod_visit")` | An action on a tile; terrain/action availability must agree |
| 6 | `@on_phase(turn_from=3, turn_to=3, phase="enemy")` | After the phase banner |
| 7 | `@after_action` | Repeated check after actions; keep it cheap and guard one-time work |
| 8 | `@on_talk(pid1="PID_IKE", pid2="PID_TIAMAT", flag=1, name="mod_talk")` | Talk interaction; `flag=1` lets either unit start it, `flag=0` only `pid1`, talking to `pid2` |
| 9 | `@on_battle(pid1="PID_ZAWANAR", pid2="PID_IKE", flag=1, name="mod_battle")` | Combat conversation; `flag=1` whichever side attacks, `flag=0` only when `pid1` attacks `pid2`; `pid2=None` matches anyone |
| 10 | `@on_death_map(pid="PID_ZAWANAR")` | Death handled back on the map |
| 11 | `@on_death(pid="PID_ZAWANAR")` | Death handled in battle |
| 12 | `@on_scenario_end(name=None)` | Post-scenario processing; preserve expected return values |
| 13 | `@on_support(pid1="PID_IKE", pid2="PID_TIAMAT", level=1)` | Support event; use a verified level value from the original data |
| 14 | `@on_base_talk(flag="mod_info", mpid="MPID_IKE", stars=1)` | Base info entry; message-person IDs are distinct from unit IDs |
| 15 | `@on_select` | Selection-time check; guard to avoid repeated scenes |

For every turn, existing scripts use `turn_from=0, turn_to=0`. Phase values are player=0, enemy=1, partner=3; the app accepts all three names, but the documented corpus evidence for type 6 covers player/enemy. Test partner phase rather than treating parser acceptance as game proof. Area sides are a different enum: player=0, enemy=1.

Location actions are visit=9, door=11, chest=12, seize=13, escape=14, destroy_house=37, arrive=41, other=44. Neither phase numbers nor area-side numbers are a universal force-ID table.

The `flag` integer on talk/battle triggers is **not** your named one-time flag: it sets the direction. With `flag=0`, `pid1` must be the unit acting (the one choosing Talk, or the attacker) and `pid2` its target; with `flag=1` either unit can take either role. Vanilla uses both for talks (a recruitment usually needs a specific talker) and always 1 for battles. Likewise, `name` is not the actor's PID or player-facing text: it is a flag name. The engine skips a talk, battle or base-conversation event while the flag of that name is set, and the event body sets it to run only once. Register the name in `Startup` and `set` it in the body, as the original events do.

`pid2=None` occurs in broad battle handlers, but exact wildcard/priority behavior is not fully established. A chapter can have both a specific Ike-versus-boss event and a general boss event; the general body may explicitly exclude Ike. Preserve that exclusion.

`@trigger(type, p1, p2, ...)` is the raw form. Use it only when you understand that type's numeric and string-pool parameters. It does not unlock undocumented engine trigger types.

## 8. Dialogue and scene timing

First edit text in an existing message and leave its control commands intact. Then learn a self-contained message before creating continuations. For a new message, create the entry in the correct chapter/common message resource and pass its exact ID to `TalkEvent`.

```fe9s
def play_existing_c02_message():
    BGMQuietOn(0)
    TalkEvent("MS_02_VIL_02")
    BGMQuietOff(0)
```

This is a small excerpt of the visit pattern, not a complete visit handler. Run it only with the appropriate message resources loaded. A message ID from another chapter may be unavailable.

Dialogue has its own command interpreter. `$H` yields from the message to event logic; `TalkResume()` continues it. Moving or deleting a resume without examining the message can leave a scene stuck or omit dialogue. `$N` inserts a newline; `$K` waits without clearing retained text; `$P` flushes retained text. Portrait, expression and window context can carry between message segments. Consult [conversation rendering](https://klg-tellius.github.io/TelliusModding/#/message-format) before inventing markup.

The dialogue preview is a selected-message visualization, not execution of the whole event VM. A preview can look correct while the game's preceding event supplies different portraits or timing.

Movement, focus, fade and event-camera commands may schedule work that continues after the call returns. Preserve `UnitMoveWait`, `FocusWait`/`FocusHardWait`, `FadeWait`, and `EventCameraWait` where the original pattern needs them. A fixed delay can change pacing; it does not prove that an asynchronous operation has completed.

Avoid an infinite busy loop that waits for game state to change without yielding. The game needs a chance to update that state. Prefer an existing wait helper; use a yield loop only when the condition and resumption context are understood.

## 9. Reinforcements and deployment

1. Find a reinforcement in the chapter or a comparable original chapter. Follow its `Dispos`/helper call to the named deployment section.
2. Duplicate an appropriate group in deployment data. Give it a distinct section name and valid unit records: PID, class, items, spawn position, destination, and AI values.
3. Check every coordinate against the complete map grid, including borders. Check terrain access and occupied spawn tiles.
4. Register a new flag in `Startup` and add a phase or area-based event.
5. Test every intended difficulty and the next enemy phase, when the new units begin acting.

```fe9s
def mod_register_wave_flag():
    regist("mod_c02_wave_done")

@before_phase(turn_from=3, turn_to=3, phase="enemy")
def mod_reinforcement_wave():
    if not get("mod_c02_wave_done"):
        set("mod_c02_wave_done")
        Dispos("bmap02_mod_wave_c")
        UnitMoveWait()
```

Call `mod_register_wave_flag()` at the end of `Startup`. `bmap02_mod_wave_c` is a group **you must create**. This snippet alone cannot spawn it. Check the matching original pattern before deciding whether `Dispos`, `InstantDispos`, or a difficulty helper is appropriate. Instant placement and staged entrances are different operations.

The `_n/_h/_m` suffixes do not by themselves prove which US difficulty loads each group. `DisposSetMode` depends on the shared helper's actual branches; see lesson 15. Creating a group without adding a reachable call leaves it unused. Adding a call without creating the group leaves an unresolved content dependency.

For recurring waves, deliberately remove or change the one-time guard, define a bounded turn range, and ensure the game supports repeated use of that deployment group and its PIDs. Do not infer duplicate-actor behavior from successful compilation.

## 10. Movement, cameras, and sound

Start with a small movement in an already-loaded map:

```fe9s
def move_ike_on_c02():
    if UnitGetByPID("PID_IKE"):
        UnitMovePosByPID("PID_IKE", 10, 15)
        UnitMoveWait()
```

Confirm that tile is traversable and appropriate in your edited map. Positioning handlers may search for an unoccupied tile; an occupied destination need not produce the exact coordinate requested. Direction-string movement such as `UnitMoveDirByPID(..., "444")` uses engine-specific direction codes. Copy and test a known path rather than treating the digits as Cartesian coordinates.

For a camera-only event, preserve a known chapter pattern: copy the current map camera, focus on a present actor, wait for focus, run the scene, restore the camera, and wait again. Event-camera creation/precision/keyframes/start/wait/delete form a separate lifecycle. Do not mix raw event-camera coordinates with map tiles; original scripts change precision modes.

Audio calls include a channel or mode parameter as well as an asset ID. Preserve the original channel in your first edit. Replace an existing `BGM_...` or `SFX_...` ID with a verified ID, then test scene end, battle interruption, and skip. Pair quiet/silent operations with their matching restoration on every path.

Calls such as `GameBind`/`GameUnbind`, `DisableSkip`/`EnableSkip`, `UnitFadeIn`/`UnitFadeOff`, and map/unit push/pop operations change state beyond a single line. Copy the entire lifecycle when adapting a scene, including cleanup after branches. Their exact nesting and skip behavior are not established by the call index alone.

## 11. Visits, chests, doors, and area events

For a visit, use the chapter's existing visit handler as the starting point. File 02's visit at `(4,11)` is a useful example: it obtains `MindGetMe()`, runs the conversation, calls `VisitOut` with the event coordinates, handles the existing `Comeback()` branch, awards `IID_HPDROP`, and sets the visit flag. Its destroy-house handler sets the same flag. Copying only `TalkEvent` and the reward loses the shared visited/destroyed state and map transition.

`MindGetItem(item_id)` is a shared helper that calls `UnitGetItemShowing(MindGetMe(), item_id)`. It relies on an acting-unit context. For a turn event with no visitor, explicitly look up the recipient as in lesson 6.

To move a visit, update its trigger coordinates, the destroy-house counterpart, affected prop/terrain state and any explicit coordinate arguments in the body. Register its flag in the location-flag setup. Test visiting twice and destroying before visiting. Do the analogous work for a chest or door: the decorator does not create an action on arbitrary terrain or animate a missing prop.

A zone can enable a later phase event rather than immediately running a scene:

```fe9s
def mod_register_zone_flags():
    regist("mod_zone_entered")
    regist("mod_zone_done")

@on_area(x1=4, y1=5, x2=6, y2=7, side="player", name="mod_zone")
def mod_enter_zone():
    set("mod_zone_entered")

@before_phase(turn_from=0, turn_to=0, phase="enemy")
def mod_zone_followup():
    if get("mod_zone_entered") and not get("mod_zone_done"):
        set("mod_zone_done")
        Dispos("bmap02_mod_wave_c")
```

Call `mod_register_zone_flags()` at the end of `Startup`, and create the group. Test all four zone edges, movement through the zone, and leaving/re-entering; exact boundary/dispatch behavior deserves a runtime check after changing coordinates.

## 12. Recruitment and unit state

A recruitment involves more than a conversation. Separate these questions: does the character definition exist, is an actor currently loaded, which force contains it, is it in the persistent roster, can it deploy next chapter, and which story flags depend on joining?

Use a real recruitment as a template. Search decompiled source for `UnitTransferToForce`, `UnitTransferToForceByPID`, and associated roster/sally calls. Inspect the whole function and initialization, not just the transfer line. The API does **not** contain a generic `UnitJoin` call; inventing one only produces an unresolved extern returning 0.

Two concrete templates are file 08's Ike/Mia (`PID_WAYU`) talk and file 22's Ike/Tauroneo (`PID_TAURONEO`) talk. Both transfer the recruited actor with `UnitTransferToForceByPID(pid, 0)` in their own chapter context. Their trigger flags differ (1 versus 0), and Tauroneo's body sets additional battle-conversation flags. This demonstrates why copying only the transfer call or standardizing every talk flag is insufficient. File 08 also branches between two messages depending on an existing story flag, then restores camera and environmental sound after recruitment.

1. Copy a comparable talk-triggered recruitment and its registered flags.
2. Replace both participant PIDs, verifying which actor is speaking and which is transferred.
3. Preserve the transfer's verified force ID and associated roster/status operations from that recruitment context.
4. Ensure the recruited actor has valid inventory, class, model, and deployment data.
5. Test the talk in both relevant interaction orders, cancellation if applicable, repeat interaction, death before recruitment, and full inventory.
6. Finish the map, save/reload, and enter the next chapter's preparations. Check that the character remains available.

Do not substitute phase enum values for force IDs. A temporary event actor with a `_EV` PID can also be distinct from the persistent playable actor. Turning a scene actor blue is not proof of a complete recruitment.

For stats, skills, status masks, AI and class changes, distinguish calls that accept a unit handle from `...ByPID` wrappers accepting a string. Obtain handles with UnitGetByPID and check for 0 before using them. For bitmasks, combine only the bits documented for that specific argument.

## 13. Objectives, defeat, and rewards

The condition, its display text, and its completion scene are separate. For a seize objective, an existing location handler sets `gf_complete`; for a defeat-boss objective an existing death handler can set the same flag. Keep the chapter's completion handler to perform its ending and cleanup.

```fe9s
@on_location(x=8, y=5, action="seize", name=None)
def example_seize_completion():
    set("gf_complete")
```

This matches the simple file-02 pattern. Replace the relevant existing handler rather than adding a competing seize handler at the same tile.

For a survive-until-turn objective, evaluate the turn at the intended phase and set completion only then. Define whether “survive 5 turns” means the beginning of player turn 5, the end of enemy turn 5, or another boundary. A phase decorator makes this choice explicit. Remove or adjust any old seize, boss-death, rout or defeat conditions that would end the map earlier, and update objective text to match.

Do not infer “boss dead” merely from `UnitGetByPID` returning zero: absent, escaped, not spawned, and dead can differ. Prefer a known death-trigger path or a verified liveness helper with semantics matching your condition.

For a new defeat condition, follow an existing failure path that sets `gf_gameover` and preserve its handler. Test simultaneous success/failure, an objective actor escaping, and death during combat versus death processing on the map.

Money uses a read-modify-write pattern present in chapter endings:

```fe9s
def add_example_money_reward():
    current = BMGetMoney()
    BMSetMoney(current + 2500)
```

Put it behind a one-time guard or in the existing one-time result flow. The snippet does not establish the money cap. Scenario-end bonus rewards can use `AchieveSet(message_id, amount)` and return status values; copy a complete existing reward function so its condition, display ID, and return behavior remain consistent.

## 14. Battle, death, support, and base conversations

**Battle talk:** modify an existing pair-specific handler first. Preserve speaker/target checks, the trigger's direction flag, boss-music start/end operations, skip settings, and the flag set after the conversation. Test both attack directions and repeated encounters. A generic boss handler may intentionally exclude a character who has a special conversation.

**Death talk:** distinguish `@on_death` from `@on_death_map`. Do not duplicate the same reward, completion flag or dialogue in both. Check whether the old body marks campaign death state as well as showing a message. Test combat animations on/off and the transition back to the map.

**Support:** an `@on_support` function provides an event for a pair/level; it does not alone establish relationship eligibility or progression. Edit the associated support data and messages. Copy an existing level encoding instead of assuming the numeric value matches a displayed rank.

**Base conversation:** copy an existing `@on_base_talk` entry, its info flag registration, message, stars and rewards. `MPID_` is a message-person ID family; it is not interchangeable with `PID_`. Confirm the conversation appears in the base list, disappears or remains as intended after reading, awards only once, and behaves correctly after leaving and returning to base.

## 15. Difficulty and branching scenes

Do not translate native difficulty names directly into menu labels. In the documented US executable, `Normal()` also returns true on Easy. `NormalOnly` and `Easy` are called by original scripts but are not registered; unresolved calls return 0.

The shared `DisposSetMode(a, b, c)` tests `NormalOnly()`, then `Hard()`, then falls back to its third argument. That means the first branch is not taken in the documented US build. Changing only the `_n` group may have no effect at that call site. Inspect `startup.cmb` in the actual target project and test each menu difficulty independently.

For story branches, use explicit `if`/`elif`/`else` and existing liveness/flag helpers. Check every combination of optional actors: one available, both available, neither available. A scene that unconditionally moves an actor who can die may fail even if its dialogue has a dead-character branch.

Do not remove an apparently redundant original branch until you have checked its region/build assumptions and script dependencies. For a new mod, write the intended conditions explicitly and document which menu difficulty each test represents after validation.

## 16. Shared functions and module lifetime

Use ordinary local helpers for chapter-specific repeated logic:

```fe9s
def mod_reward(unit, item):
    if unit:
        UnitGetItemShowing(unit, item)

def mod_reward_ike():
    mod_reward(UnitGetByPID("PID_IKE"), "IID_HPDROP")
```

Use `@export` only when another module or the engine must call the function by name. `@export("RuntimeName")` can give a source helper a different runtime name. Keep required engine entry names intact, and avoid collisions with native functions or other loaded exports.

`extern("Name", args...)` forces an external name lookup when a local source function has the same name. The 89 helpers from `startup.cmb` are script functions using this same name-registration mechanism; they are not extra bytecode instructions.

Runtime module loading is a lifecycle: loaded exports enter the shared name table; sleeping a module removes its exports and excludes it from event enumeration; waking restores sleeping modules; freeing removes the last-loaded module. `CmFreeScript` uses LIFO ordering. Do not unload the script or dependencies of a running scene. Adding a file to `Scripts/` alone neither loads it nor makes its exports callable.

Treat custom module loading as advanced work requiring a matched load/call/cleanup template and runtime testing. The compiler's catalog can warn about your custom export even when it will be registered at runtime; resolve the dependency deliberately rather than ignoring all unknown-name warnings.

## 17. Advanced storage and assembly

Arrays reserve contiguous local slots and use zero-based indices:

```fe9s
def local_buffer_example():
    var values[3]
    values[0] = 10
    values[1] = 20
    values[2] = 30
    return values[0] + values[1] + values[2]
```

There is no Python list and no documented automatic bounds protection. Never access beyond reserved slots. `&x` passes the address of a local slot to a function that writes an output; use it only when that function's pointer contract is known. A local address is not persistent storage after the function returns.

`global name @ slot` names one of the engine's 32 global slots (0–31), shared by every loaded script: slot 3 is the same number in every chapter. The compiler sets the file's reservation to the highest declared slot + 1, which is all the engine needs; a slot outside 0–31 is a compile error because it would overwrite unrelated memory.

Globals are **scratch memory for one play session**:

- They are not saved. After loading a save they hold whatever was in memory, not what you stored.
- They are not cleared at power-on or between chapters. An unwritten slot holds leftover data, never a reliable 0.
- They do let two events of the same chapter share a number, such as a position captured in `@on_death` and used by the following `@after_action`, which is how the game uses them.

```fe9s
global boss_x @ 0
global boss_y @ 1

@export
def Startup():
    boss_x = 0   # never read a global you have not written
    boss_y = 0
```

For anything that must survive a save or a chapter change, use flags. A small number can be spread over several flags, one per bit.

Raw branches and assembly are available for unusual decompiled code:

```fe9s
def branch_example(value):
    goto finished unless value
    asm:
        push8 4
        pop
    finished:
    return 0
```

`@naked` suppresses the implicit return; you must then make every path terminate appropriately. Preserve `lit(...)` and `strofs(...)` in lossless decompiled code unless you understand the raw value. `strofs` is a raw pool offset, not a durable content name after pool restructuring.

Limits relevant to a growing chapter:

| Encoding | Practical limit |
|---|---|
| `localCall` signed byte | Nonnegative target index 0–127; later functions may exist but cannot be targeted by this instruction |
| Branch signed 16-bit displacement | −32768…32767 relative to opcode address + 1 |
| `externCall` signed 16-bit name offset | Name must be reachable within offsets 0…32767 in the string pool |
| `pushstr8/16/32` | String pushes can widen; this does not widen an extern name operand |
| Trigger parameters | Unsigned 16-bit fields, including label offsets |
| Function argument/trigger-param counts | Signed-byte fields in the format |
| Local-frame size | Signed 16-bit slot count in the format; runtime stack capacity is an additional constraint |

Avoid assuming that inserting functions is unlimited because source names are symbolic. Named source calls are rebuilt after reordering, but raw `localCall` numbers in assembly require review. Splitting a huge function can solve branch-distance problems; it does not automatically solve string-pool or runtime stack limits. An exported external call is a possible design for a helper beyond index 127 only if its runtime name is unique, registered, and within the extern operand's range.

## 18. Build a chapter overhaul

Use this sequence to keep the project playable at each step:

1. **Write the chapter specification.** Starting roster, map, enemies, objectives, failure conditions, reinforcements, interactions, rewards, opening, ending, and persistent decisions.
2. **Choose a reachable chapter template.** Prefer one with the same preparation and objective structure. Inventory its exports and flags before deleting events.
3. **Create the data dependencies.** Character/class/item records, deployment groups, terrain and props, messages, portraits, music and models. Keep an ID list shared with your script plan.
4. **Make setup playable.** Retain working loading/preparation flow, replace initial groups, verify legal positions, and reach player phase with the intended roster.
5. **Implement success and failure.** Adjust conditions and displayed objective; verify a complete chapter transition before adding elaborate scenes.
6. **Add events one at a time.** Turn events, area conditions, visits, recruitment, boss/death dialogue, then optional base/support content.
7. **Add presentation.** Movement, cameras, sound and longer conversations after the underlying state changes work.
8. **Validate persistence.** Save/reload, next chapter, optional deaths and skipped scenes. Test every target difficulty.
9. **Package and document.** Keep source, the edited-file list, required game/build, intended behavior and runtime test results together.

For a wider overhaul, use the linked system notes for [characters/classes/items/skills](https://klg-tellius.github.io/TelliusModding/#/fe8data), [shops](https://klg-tellius.github.io/TelliusModding/#/shop-format), [music](https://klg-tellius.github.io/TelliusModding/#/music-system), [movies](https://klg-tellius.github.io/TelliusModding/#/cutscenes), [graphics](https://klg-tellius.github.io/TelliusModding/#/graphics-system), [saves](https://klg-tellius.github.io/TelliusModding/#/save-format), and [native gameplay](https://klg-tellius.github.io/TelliusModding/#/main-dol). Script calls coordinate these systems; they do not replace their file formats or native implementations.

## 19. Validate and troubleshoot

Validation has four distinct levels: source compilation, binary serialization/round-trip, content dependency checks, and execution in the target game. Passing one does not imply the next. **Check** cannot prove actor availability, correct force IDs, asset existence, sane stack usage, persistence, or event ordering.

| Symptom | Check first |
|---|---|
| Event never runs | Correct rebuilt image, chapter file number, exported name/trigger, phase, coordinates, setup/flag registration, and guards |
| Call does nothing | Unknown-name warning; loaded export availability; exact case/spelling; correct asset/group ID |
| Reward repeats | Flag registration/reset, missing guard, another copy of the handler, repeated scenario processing |
| Script freezes | Busy loop without yield, wait for an operation never started, missing `TalkResume`, invalid actor context |
| Wrong unit gets reward | `MindGetMe` context versus explicit recipient handle |
| Reinforcement missing | Group exists, difficulty branch used, spawn terrain/occupancy, actor IDs, earlier flag already set |
| Talk overrides another talk | Pair-specific/general overlap, raw trigger flag, shared event names, missing exclusion |
| Camera/music remains altered | Missing restore on a return/branch/skip path |
| New text missing | Correct message resource and load context; actual ID exists; continuation setup |
| Change disappears after reload | Save predates setup change, loaded old state, temporary actor/flag, wrong rebuilt image |
| Serialization fails after growth | Local-call index, branch displacement, name-pool offset, Shift-JIS encoding, field widths |
| Chapter never completes | Old/new conditions conflict, `gf_complete` never set, ending wait or cleanup stuck |

Retail `printf` is inert, so it is not a usable on-screen debug log. Use a temporary known message/visible state change in a controlled event, or the project's debugger workflow for state inspection.

Minimum runtime matrix: normal play and skip; intended and unintended phase; actor present and absent/dead; reward inventory empty and full; each difficulty; repeat interaction; normal save/reload; chapter completion and next preparations. For movement/area events include occupied tiles and zone edges. Start from a save before initialization; a savestate taken after setup can retain old script/state assumptions.

Keep a short result sheet with the game/build, edited files, starting save, exact actions, expected result and observed result. Do not label a recipe “tested in game” solely because a different event using the same native call once worked.

## 20. Command-line workflow

Run from the repository's `App/` directory. Replace the example paths with your own project paths. Use a separate candidate output while experimenting:

```powershell
python -m fe_modding.formats.cmb decompile "D:\MyMod\extracted\files\Scripts\C02.cmb" -o "D:\MyMod\c02.fe9s"
python -m fe_modding.formats.cmb compile "D:\MyMod\c02.fe9s" -o "D:\MyMod\C02.candidate.cmb" --base "D:\MyMod\extracted\files\Scripts\C02.cmb"
python -m fe_modding.formats.cmb decompile "D:\MyMod\C02.candidate.cmb" -o "D:\MyMod\c02.candidate.fe9s"
python -m fe_modding.formats.cmb roundtrip "D:\MyMod\extracted\files\Scripts"
```

`--base` preserves the original header, pool order and compatible padding. Review the candidate's decompiled logic and warnings; then copy the intended candidate to the chapter's extracted script path, build, and test. Compilation without `--base` creates a generic header and loses preservation information.

The `roundtrip` command checks untouched reconstruction for files in the specified directory. Confirm that it prints actual filenames: an empty directory is not evidence of coverage. A binary diff after a real edit is expected because offsets and padding may move; review semantic changes through decompiled source as well.

For this documentation's examples, run from the repository root:

```powershell
python docs/app/check-script-examples.py
```

## 21. Coverage and remaining limits

The [function reference](script-call-reference.md) gives positional signatures, argument meanings, return values, and usage restrictions for all 497 catalogued names. Use it when adding a call or changing one of its arguments. Follow each entry’s restrictions: resource-specific modes and advanced engine operations can still require an existing scene as a template.

This course targets US Path of Radiance. A new chapter-selection system, new engine-level skill mechanics, or a Radiant Dawn port needs work beyond the script language. Start with a reachable chapter, satisfy the asset dependencies of each example, and test the complete scene in game.
