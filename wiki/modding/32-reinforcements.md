---
id: "modding-reinforcements"
title: "Add and verify a reinforcement wave"
description: "A complete workflow for defining reinforcement units, scheduling them with an on-phase trigger, selecting a deployment call, preventing repeats, and testing edge cases"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Deployment", "Events", "Reinforcements"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/32-reinforcements.md"
tutorial_kind: "task"
tutorial_track: "units-and-events"
tutorial_stage: "draft"
prerequisites: ["modding-deployment-sections", "modding-deployment-by-difficulty", "modding-script-editor", "modding-event-flags"]
verification: ["source-reviewed", "unknown"]
---
# Add and verify a reinforcement wave

**Routes:** Chapter → Deployment; Chapter → Script

## What you will make

You will create a one-enemy reinforcement wave that appears during the enemy phase of turn 3. The unit will live in a dedicated deployment section and remain absent at chapter start. A script function will listen for the selected turn/phase, call the chapter's appropriate deployment loader, and—where the trigger design can be entered more than once—use a chapter flag to prevent duplicate loading.

The finished result has three independently testable parts:

1. a valid unit record in every supported difficulty file;
2. a valid event trigger with an exact turn window and phase;
3. a deployment call whose argument and loading behavior match the chapter's existing conventions.

## Before you begin

Complete [Design and connect deployment sections](29-deployment-sections.md), [Place and tune units by difficulty](30-deployment-by-difficulty.md), and [Edit and compile event scripts](33-script-editor.md). Read [Use campaign and chapter flags](34-event-flags.md) before adding a repeat guard.

Choose a chapter that already contains a working reinforcement or mid-chapter deployment event. That event is your reference for the actual function name, argument shape, animation style, and section-name convention. Do not paste a guessed `Dispos*` call: `Dispos*` is shorthand for a family of native calls, not a literal callable function.

Write a small specification before editing:

| Decision | Test value |
| --- | --- |
| Trigger | enemy phase, turn 3 only |
| Difficulties | Normal, Hard, Maniac |
| Section base name | a new chapter-local reinforcement name |
| Unit | one known enemy PID/class combination |
| Spawn tile | one empty, valid edge tile |
| Destination | same tile for the first test |
| Repeat policy | load once |
| Arrival style | copy the chosen vanilla reference |

Save a chapter backup. Record the opening deployment sections and the selected event file's current compile/check result so the new work has a known baseline.

## How the editor fits together

A deployment section is data, not a timer. It describes which records a loader can create. A script trigger is a timer/condition, not a unit definition. It decides when code runs. The deployment call joins them by asking the engine to load the chosen section.

```text
Deployment section ── defines PID/JID/items/AI/tiles ──┐
                                                       ├─ deployment call → units enter
Script trigger ───── decides turn/phase/conditions ────┘
```

The chapter can have four deployment files: common plus Normal, Hard, and Maniac. Difficulty-specific counterparts conventionally use related `_n`, `_h`, and `_m` names. Some deployment calls accept an exact section name; others use a rank/difficulty-aware naming convention. The Script editor's **Insert Call...** catalog and a working chapter event are the authority for which form your chapter uses.

The script trigger editor exposes `on_phase` fields such as **turn from**, **turn to**, and **phase**. Editing those controls does not change source until **Apply to code** is used. Conversely, editing the decorator/source directly does not guarantee the form displays unsaved intentions. Re-open the function after applying and check both views.

## Guided walkthrough

### 1. Create dedicated difficulty sections

Open **Deployment**. Add one reinforcement section for Normal, one for Hard, and one for Maniac, following the chapter's existing suffix convention. Use the same base name and parallel record order. Do not append the reinforcement to a section that the opening event already loads.

Set the section army to the same side used by comparable enemy reinforcement groups. Remember that the header army groups the section, while the unit's **Faction** sets that individual record's allegiance.

If the wave is intentionally identical on every difficulty, a common section may be possible, but it changes naming and loader expectations. Use three explicit difficulty sections for this exercise so you can prove each path independently.

### 2. Add one complete unit per supported difficulty

Add one matched enemy unit across Normal, Hard, and Maniac. Give it:

- a known PID and compatible class;
- Enemy faction;
- one usable weapon;
- AI copied from a nearby working reinforcement;
- a clear spawn tile and the same destination tile;
- no drop, optional skill, special flag, or gauge override for the first test;
- a clearly recorded level for each difficulty.

Save deployment. Switch through all three files and confirm the section exists, contains exactly one unit, and uses the intended coordinates.

### 3. Prove the wave is not loaded at chapter start

Start the chapter from a clean pre-battle state before adding the new trigger. The new PID must be absent. If it is already present, inspect the opening event's deployment calls and section naming. A section accidentally included by a prefix/rank loader must be renamed or disconnected before the timing test is meaningful.

This negative checkpoint is essential: seeing the enemy on turn 3 does not prove the new trigger worked if the opening already created it.

### 4. Duplicate a working reinforcement function

Open **Script** and select the file containing the chapter's comparable reinforcement logic. Duplicate the smallest function that already loads one section during a phase, or create a new function using that one as a structural reference.

Rename it with a unique, chapter-local function name. Remove unrelated dialogue, camera movement, rewards, and victory-condition logic. Keep only the trigger structure and the deployment-loading sequence needed for the test.

Do not copy a function from a different chapter without replacing its section argument, flags, PIDs, and helper calls. Native function availability may be shared, but chapter-local data is not.

### 5. Configure an exact turn/phase window

Select the function and open **Trigger and description**. Choose the `on_phase` trigger. Set:

- **turn from** = 3;
- **turn to** = 3;
- **phase** = Enemy.

Use **Apply to code**. Inspect the generated decorator/source and confirm both endpoints are 3 and the phase is the intended engine value. Then switch to another function and back to ensure the trigger panel reloads the saved source values.

An exact one-turn window is already bounded. A separate flag is still useful when the body can be invoked from another path, when a wider phase range is later introduced, or when the copied reference explicitly guards one-time execution. Do not invent flag syntax from memory; use the chapter's established check/set calls and the flag lesson.

### 6. Insert the correct deployment call

Place the cursor in the function body and choose **Insert Call...**. Search the deployment function family and read the catalog help. Compare the available choice with the working event you copied.

The useful distinctions are:

- an exact-name loader versus a difficulty/rank-aware loader;
- an animated/normal arrival versus an instant variant;
- a loader that creates a group versus a continuation form that acts on an already established deployment sequence.

Select the same semantic family as the reference. Supply the exact argument style it expects: either the full difficulty section name or the shared base/prefix used by a rank-aware function. The editor can help with the signature, but only the chapter's real section list proves the string is correct.

Keep the inserted statement as generated, then replace only the argument values required by your new section. Run **Check** immediately. A clean syntax check proves the call is shaped correctly; it does not prove the named section exists.

### 7. Add a one-time guard when the design requires it

If the reference event uses a chapter flag, create a free chapter-local flag and copy the reference's control-flow pattern:

1. return/skip when the flag is already set;
2. execute the deployment call;
3. set the flag only after the load sequence has been started successfully.

Use **Insert Call...** for the project's actual flag test and set functions. The flags tutorial explains scope and collision checking. Do not substitute a campaign flag for a chapter-local event merely because its number is available.

For the exact turn-3-only exercise, you may first test without the extra flag, then add it and prove it changes no normal-path behavior. Retain the guard if another call path or future widened trigger could re-enter the function.

### 8. Check and save both resources

In Script, run **Check** and resolve every reported source error. Save the script. Return to Deployment, save the placement, then save the chapter.

Close and reopen both editors. Confirm the three sections still exist and the function still shows turn 3 through 3 on Enemy phase with the chosen deployment call and optional guard. A successful script save cannot recover an unsaved deployment section; a valid deployment file cannot schedule itself.

### 9. Test the complete timeline

Start from a save before chapter initialization or a fresh chapter entry. Observe:

1. after opening deployment: reinforcement absent;
2. player phase of turn 3: still absent;
3. start of enemy phase turn 3: appears once at the specified tile;
4. enemy phase of turn 4: no duplicate;
5. chapter reload from a fresh state: behavior repeats consistently.

Repeat on Normal, Hard, and Maniac. Then occupy the spawn tile before the trigger and record the actual engine behavior. Do not promise that the game will relocate, delay, stack, or reject the unit without observing that call variant in this chapter.

## Understand every choice

### Dedicated section versus opening section

A dedicated section makes timing observable and prevents the opening loader from creating the wave early. It also gives script calls a narrow target. Reusing the opening section couples two load moments and can recreate records that were never meant to return.

### Exact name versus rank-aware name

An exact loader points to one section string. A rank-aware loader selects a difficulty counterpart according to its documented naming behavior. Mixing the two models can make one difficulty work while another silently finds no section. Follow the selected call's catalog help and the chapter's vanilla example.

### Spawn versus destination

Spawn is the creation tile. Destination participates in applicable arrival/movement behavior. Keeping them equal removes a variable during the first test. Once loading works, copy an existing moving reinforcement if you want an entrance path.

### Turn window and phase

`turn_from = 3` and `turn_to = 3` describe a closed single-turn window. A range such as 3–5 can make the function eligible on multiple turns and therefore needs explicit one-time reasoning. The phase determines whose phase boundary is observed; it is not the unit's faction.

### Animated, instant, and continuation calls

These call families are not interchangeable presentation options. They can participate in different engine sequences and may expect different state. Copy the family used by a nearby working event before experimenting. In particular, a continuation/existing-only form is not a substitute for the initial group creation call.

### Guard scope

A trigger constraint controls eligibility; a flag records history. Use a chapter flag for chapter-local history unless the design intentionally persists across chapters. Set it after the relevant action, not before code that might branch away.

## Interactions and precedence

- The opening loader wins the timing race: if it already loads the section, the reinforcement is present before the new trigger.
- The script call must name data that exists in the active deployment file or follow the rank-aware convention exactly.
- Unit **Faction** controls allegiance; trigger **phase** controls when the function runs. They need not have the same label, although enemy reinforcements commonly arrive on Enemy phase.
- A one-turn trigger limits normal eligibility, while a flag protects against re-entry through broader or additional call paths.
- Saving Script and saving Deployment are separate operations; both must be committed to the chapter.
- A valid script compile does not validate section spelling, occupied tiles, class/model compatibility, or cross-difficulty completeness.
- Reinforcement AI, inventory, and flags take effect after the unit is created; they cannot cause a missing loader call to run.
- If a rank-aware loader selects difficulty data, adding only the Normal section is not enough for Hard and Maniac.

## Test matrix

| Case | Preparation | Pass condition |
| --- | --- | --- |
| Before trigger | fresh start, turn 1–2 | unit is absent |
| Wrong phase same turn | player phase, turn 3 | unit remains absent |
| Exact trigger | enemy phase, turn 3 | one unit appears at the recorded spawn |
| Following turn | enemy phase, turn 4 | no second copy appears |
| Normal | Normal deployment file | Normal counterpart loads with its level |
| Hard | Hard deployment file | Hard counterpart loads with its level |
| Maniac | Maniac deployment file | Maniac counterpart loads with its level |
| Occupied spawn | place a unit on arrival tile | observed behavior is safe and documented, or tile/design is changed |
| Saved mid-chapter | load a save made before the trigger | eligibility and guard state behave consistently |
| Script reload | close/reopen editor, run **Check** | trigger and call remain intact |

For changes meant for release, repeat the core timeline in Dolphin after the application's fast Play check. Emulator testing is where timing, animations, sound, and engine-only edge cases are established.

## Troubleshooting

### Nothing appears

Check in this order:

1. the function is in the script file actually used by the chapter;
2. `on_phase` shows turn 3–3 and the intended phase after **Apply to code**;
3. the guard flag is initially clear;
4. the selected call is the initial-load form rather than a continuation form;
5. its exact section or base name exists in the active difficulty file;
6. Deployment and Script were both saved.

### It appears at chapter start

Search the opening event for a call that already includes the section, base name, or prefix. Move the unit to a dedicated section outside that opening selection and retest from a fresh start.

### It works only on one difficulty

Compare suffixes/base names, section presence, unit count, and the loader's exact-versus-rank behavior. A call can compile even when the Hard or Maniac counterpart is absent or misnamed.

### It loads more than once

Inspect the turn range and every place that invokes the function. Confirm the guard checks the same flag it sets, that the flag has chapter scope, and that the set happens after the load path rather than in an unreachable branch.

### The unit appears but does nothing useful

Loading succeeded; inspect the record next. Check faction, usable weapon, attack/move AI, **Hold position**, destination, and terrain reachability using [Set unit inventory, drops, skills, AI, and flags](31-unit-inventory-and-flags.md).

### The script checks but the game hangs or behaves strangely

Return to the exact vanilla call sequence you used as a reference. Verify whether the chosen family requires animation setup, waits, a follow-up/continuation call, or other surrounding state. Syntax validation cannot establish native runtime preconditions.

## Save, build, and revert

Save Deployment, run Script **Check**, save Script, then save the chapter. Reopen both resources before building. Build the ISO only after the complete turn-3 timeline passes in the editor.

To revert cleanly, restore both sides of the change: remove/restore the reinforcement function and guard in Script, and remove/restore all difficulty sections in Deployment. Leaving either half creates dead data or a call to missing data. Restore any newly reserved flag to the project's free pool only after confirming no other event references it.

## Limits and confidence

The editor flow, `on_phase` fields, **Apply to code**, deployment-file structure, and catalog distinctions are source-reviewed. Exact native engine effects of every deployment call variant remain dependent on the selected function and chapter context. This lesson therefore requires a working in-chapter reference instead of claiming one universal `Dispos` recipe.

Occupied-tile resolution, entrance animation timing, and save/load behavior are runtime concerns. Record the result for the exact call family you use and verify it in Dolphin before release.

## Things to try

- Move the trigger from enemy phase to player phase while keeping the unit faction Enemy; observe timing separately from allegiance.
- Expand the window to turns 3–5, keep the one-time flag, and prove the wave still enters once.
- Add a second unit with a different destination and compare simultaneous arrival behavior.
- Compare the chapter's normal and instant deployment variants using disposable copies.
- Make Hard/Maniac levels differ while keeping shared inventory and AI identical.
- Deliberately misspell the section string, observe that source checking can still pass, then restore it and document the runtime failure mode.

## Related tutorials and references

- [Design and connect deployment sections](29-deployment-sections.md)
- [Place and tune units by difficulty](30-deployment-by-difficulty.md)
- [Set unit inventory, drops, skills, AI, and flags](31-unit-inventory-and-flags.md)
- [Edit and compile event scripts](33-script-editor.md)
- [Use campaign and chapter flags](34-event-flags.md)
- [Events and scripting](../systems/events-scripting.md)
- [Dispo format](../formats/dispo-format.md)

---

[← Previous: Set unit inventory, drops, skills, AI, and flags](31-unit-inventory-and-flags.md) · [All tutorials](index.md) · [Next: Edit and compile event scripts →](33-script-editor.md)
