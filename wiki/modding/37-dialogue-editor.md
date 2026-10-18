---
id: "modding-dialogue-editor"
title: "Author and connect a dialogue scene"
description: "A complete workflow for message IDs, scene layouts, backgrounds, portrait seats, speakers, actions, inherited context, preview playback, script calls, and testing"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Dialogue", "Cutscenes", "Messages"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/37-dialogue-editor.md"
tutorial_kind: "task"
tutorial_track: "dialogue-and-text"
tutorial_stage: "draft"
prerequisites: ["modding-script-editor", "modding-event-recipes"]
verification: ["source-reviewed", "unknown"]
---
# Author and connect a dialogue scene

**Routes:** Chapter → Dialogue; Chapter → Script

## What you will make

You will create a two-speaker chapter scene from a built-in template, give it a unique Message ID, choose a layout and background, load two portraits into seats, alternate speakers, add a page clear and controlled pause, and connect the message to a disposable script event. You will also test the scene both with a clean initial context and with state inherited from a preceding message.

The finished scene is deliberately short. The depth comes from understanding how readable notation becomes the original message byte dialect, how seats and textboxes preserve state, and why a correct Live Preview is only one layer of verification.

## Before you begin

Complete [Edit and compile event scripts](33-script-editor.md) and [Build reliable chapter events](35-event-recipes.md). Choose a chapter with a working short dialogue event and record:

- the caller function and its exact dialogue native/helper;
- the current Message ID;
- the owning chapter message file;
- the scene immediately before it, if any;
- the baseline layout, background, seats, and box state;
- the script and Dialogue **Check/save** state.

Write a six-line exchange with two known portraits already used by the chapter. Keep each spoken line short enough to fit one box. Choose an unused ID following the chapter's existing convention, such as `MS_05_TEST_01`; search both the Message ID list and script source before committing it.

Back up the chapter message file and script. A new message is inert until a script calls its ID, but renaming or deleting an existing ID can break every caller immediately.

## How the editor fits together

Messages are addressed by string ID, not by row number. A script call such as a chapter's existing `TalkEvent` family resolves the ID through the game's name table. The editor keeps messages sorted by encoded ID for consistency, but changing their displayed order does not retarget a caller.

The Dialogue page has four synchronized views:

1. **Message ID and management** choose the record.
2. The **text editor** shows spoken text plus highlighted `<actions>`.
3. The **stage/seat panel** interprets state at the cursor or playback position.
4. **Live Preview** renders and plays the interpreted scene.

```text
readable dialogue + actions → parsed scene → encoded message file
             ↓                    ↓
       stage at cursor       Live Preview
             ↓
script caller by Message ID → runtime scene in game
```

Layout, background, portraits, selected speaker/textbox, typing sound, waits, and transitions are stateful operations. A message may establish them itself or inherit them from earlier messages. Preview's **Inherit from message** and **Initial scene context** controls exist because selecting a message alone does not recreate an entire chapter cutscene history.

If notation is invalid, the editor underlines the error and Live Preview retains the last valid parsed text. A pretty preview during an error is stale evidence; resolve the red error before saving.

## Guided walkthrough

### 1. Audit a working message and caller

Open **Chapter → Dialogue**. In **Message ID**, type part of the working ID and press Enter, or open the list. Read the scene from beginning to end and click several highlighted actions. Observe the stage panel as the cursor crosses layout, background, portrait, speaker, line, wait, and clear operations.

Open **Script**, search the exact ID, and identify the call that reaches it. Use **Insert call...** to inspect that call's argument help. Return to Dialogue without changing the original.

### 2. Create from a template

Choose **New...**, enter the unused test ID, and select **Two-box talk** or **Background scene** as the starting template. Templates provide a valid scene skeleton; their placeholder portraits, seats, and text are not design defaults.

The new message stays in the current chapter's message file. It does not automatically gain a trigger or script caller. Confirm the ID appears in the selector and that the notation-error line is empty.

### 3. Choose layout before placing portraits

Use the **Layout** selector and **Examples...**. Examples show where textboxes and portrait seats belong for each layout. Choose one with at least two portrait seats and suitable boxes, then let the control insert/replace the `<Layout:...>` action.

Changing layout can change seat and box interpretation. Establish it before detailed portrait blocking. After choosing, click at the end of the message and confirm the stage reports the intended layout.

### 4. Choose and verify the background

Use the **Background** selector or **Search...** to choose an existing resource. This inserts/replaces the `<Background:...>` action near the scene start, after layout where applicable.

Select an RID/background already proven in the same chapter for the first test. A resource name in the list proves the app found its assets; it does not prove an arbitrary script/load context displays it identically in-game.

### 5. Load portraits into seats

In the stage panel, click an empty seat and choose the first portrait. Click another empty seat for the second. Alternatively, put the cursor at the correct point and use **Portrait** with the searchable picker.

Portrait load and speaker selection are separate actions. Loading Ike into seat 0 does not make seat 0 speak every following line. Right-click a portrait for supported seat actions such as changing/removing it, and watch the generated action in the text.

Keep both portraits visible for the first exchange. Avoid expression, blink, mouth-set, movement, or attachment changes until basic seat/speaker behavior passes.

### 6. Assign speakers and write lines

Place the cursor before the first line and click the first portrait/seat to speak from it, or use **Speaker**. Replace the placeholder text with line 1. Before line 2, select the other seat as speaker and write the reply.

Continue alternating seats. The editor's selected speaker/box determines where line text is presented; the portrait loaded into that seat provides the face. Use the stage-at-cursor view to verify each transition rather than judging only the final frame.

Keep ordinary text outside angle-bracket actions. To enter literal `<` or `>`, use the documented byte actions rather than creating a tag-shaped fragment.

### 7. Add pacing and page behavior

Use **Pause** to insert a pause-power action. Power `n` waits `2^n` frames: for example, power 4 is 16 frames. This is different from **Wait**, which represents a scene wait action rather than inline typing cadence.

Use **Clear** to clear/new-page the active box where the second page should begin. Then reselect the intended speaker if the copied scene convention requires it. Avoid stacking several waits around the same transition until one known reference has been tested.

Use **Actions...** to browse other decoded operations. Hover/read their descriptions and confidence. Insert one only when its effect and required fields are understood; unknown/raw actions should be preserved when editing a vanilla scene, not rewritten speculatively.

### 8. Validate the text representation

Use **Undo**, **Redo**, and **Find / Replace** as needed. Double-click a highlighted action to edit its fields instead of hand-editing raw values. Check:

- no notation error is displayed;
- every action remains highlighted as one complete token;
- stage state advances logically at each action;
- the final line does not inherit an unintended speaker/font/box;
- the ID remains unique.

Preview playback is driven by the current valid parse. If an error appears, fix it before using playback results.

### 9. Exercise Live Preview deliberately

Use **Play**, then **Previous/Next** step controls to inspect transitions. Toggle **Auto-advance** and test Slow, Normal, Fast, and Max **Message speed** only to distinguish authored waits from player text speed. Use **Reload assets** after changing a portrait/background/font outside Dialogue.

First run with reset context. Then set **Inherit from message** to the actual preceding message and choose **Apply**, or choose **Auto** to let the editor resolve a likely caller/preceding context. Expand **Initial scene context** to inspect/override layout, background, and seats; use **Apply context** and **Reset context** to compare.

Inheritance is test setup, not a new action saved into the message. If the scene only works with manually supplied state, either document its required predecessor or add explicit setup actions.

### 10. Save and connect the script caller

Choose **Save Chapter**. Read the status, switch to another ID, return to the new one, and verify the exact content. For bulk backup/review, **Export chapter...** writes all messages in readable UTF-8 sections; **Import chapter...** replaces matching IDs and adds new IDs while keeping unlisted messages.

Open Script. Duplicate the disposable caller event or use an existing controlled trigger. With **Insert call...**, select the same dialogue function as the working reference and supply the new Message ID. Run **Check**, save Script, then save the chapter.

### 11. Test integration

Start from before the trigger. Confirm:

- the caller fires once under the intended conditions;
- the new ID resolves rather than showing old/missing text;
- layout, background, portraits, boxes, and speaker order are correct;
- input/waits do not hang;
- event skip reaches the same post-dialogue state;
- control returns to the map/event sequence.

Repeat once with the true preceding scene intact. Finish with Dolphin for final timing, transitions, audio, and skip behavior.

## Understand every control

### Message management

- **Message ID** searches/chooses a record; typing a partial ID plus Enter searches.
- **New...** creates a unique ID from a template.
- **Duplicate** copies content under a new ID; callers remain on the old ID.
- **Rename...** changes identity and requires every caller to be updated.
- **Delete** removes the message but cannot remove script references automatically.
- **Save Chapter** rebuilds/saves the owning message file.
- **Export chapter... / Import chapter...** provide whole-file readable review and merge-by-ID behavior.

### Editing toolbar

- **Layout** inserts/replaces the scene layout action; **Examples...** visualizes choices.
- **Speaker** selects a seat/box for following line content.
- **Portrait** loads/replaces a face resource.
- **Wait** inserts an explicit scene wait.
- **Pause** inserts an exponential inline pause (`2^n` frames).
- **Clear** clears the active box/starts page behavior represented by the dialect.
- **Actions...** exposes all decoded action kinds and their fields.
- **Background / Search...** inserts/replaces the scene background resource.

### Stage and seats

The stage is evaluated at the cursor/playback byte position. Clicking an empty seat loads a portrait; clicking a portrait selects it to speak where supported; right-click exposes more actions. Seat availability and box style come from the active layout.

### Preview controls

- **Play** runs/pauses the interpreted sequence.
- Step controls move through actions without waiting for full playback.
- **Auto-advance** continues through boxes automatically for inspection.
- **Message speed** simulates user setting, not authored pause removal.
- **Reload assets** refreshes changed external resources.
- **Inherit from message** reconstructs state after a chosen predecessor.
- **Auto** searches known context/call relationships.
- **Initial scene context** manually supplies layout/background/seats for testing.

## Interactions and precedence

- A script resolves the exact Message ID string; file order does not retarget it.
- Layout determines seat/box interpretation, so late layout changes can invalidate blocking.
- Loading a portrait and selecting a speaker are independent.
- Explicit actions in the message modify inherited context; absent actions leave inherited state in force.
- Preview manual context affects preview only, not saved message data.
- Invalid current notation leaves Preview on the last valid parse.
- Text speed and authored pause/wait are separate timing inputs.
- Duplicating a message does not duplicate/update its caller.
- Renaming an ID without updating scripts creates a broken integration even if Preview works.
- Saving Dialogue does not save Script, and saving Script does not save Dialogue.

## Test matrix

| Case | Setup | Pass condition |
| --- | --- | --- |
| Parse | current editor text | no notation error; all actions recognized |
| Reset preview | empty initial context | explicit setup produces intended stage |
| Inherited preview | real predecessor selected | continuity is correct with no duplicate setup artifacts |
| Each speaker | step through lines | correct seat/portrait owns each line |
| Page clear | advance across clear | new page/box starts correctly |
| Text speeds | Slow and Max | authored pauses remain distinguishable and sequence completes |
| Caller | fresh pre-trigger state | exact new ID plays once |
| Skip | skip during scene | caller reaches same post-scene state |
| Reload | save/reopen Dialogue and Script | content, ID, and call round-trip |
| Dolphin | built project | timing, transitions, audio, and controls match intent |

## Troubleshooting

### Preview still shows an older version

Read the notation-error line. The current text did not parse, so Preview retained the last valid document. Fix the underlined action before reloading assets or changing context.

### The game shows old or missing text

Search the script caller's exact ID, confirm **Save Chapter** wrote the intended message file, and check for duplicate/hash-conflicting loaded IDs. A new record is never called automatically.

### The wrong portrait speaks

Inspect both portrait-load and speaker/seat actions at the line's byte position. The visible portrait can occupy one seat while a different box/seat remains selected.

### A background or portrait appears unexpectedly

Reset preview context, then preview with the actual predecessor. Determine whether the state is inherited or explicitly introduced in this message before adding a duplicate action.

### Text waits forever or advances too quickly

Separate inline pause power, explicit Wait, line-end/page behavior, Auto-advance, and simulated Message speed. Compare the exact sequence with a working message using the same layout.

### The message works alone but breaks in the event

The caller may establish event mode, camera, resources, or inherited context differently. Test the real preceding sequence and preserve the working dialogue helper's setup/cleanup calls.

## Save, build, and revert

Save Dialogue first, reopen the ID, then Check/save the changed Script caller. Save the chapter and build only after both resources round-trip.

To revert, restore the chapter message file and script together. If you created a new ID, remove its caller before deleting the message. If you renamed an ID, restore both identity and every call site. **Export chapter...** is a readable content backup but not a substitute for the project's original binary restore.

## Limits and confidence

Message identity, editor controls, notation parsing, stale-preview behavior, templates, seat/context mechanics, and script-call integration are source-reviewed. The preview interprets the known dialogue dialect but is not the complete event VM; unusual/raw descriptors and some runtime transitions remain approximate.

Asset availability, exact timing, input, voice/typing audio, and event skip must be verified in Dolphin. Preserve unknown vanilla actions unless an isolated test establishes their meaning.

## Things to try

- Duplicate the scene and remove explicit background setup; compare reset versus inherited context.
- Use three speakers in a layout with enough seats and track every speaker transition.
- Insert pause powers 1 through 6 into one test line and compare their doubling durations.
- Change layout after blocking, observe which seats/boxes become invalid, then restore it.
- Export the chapter, make one readable text-only change, import, and verify unlisted messages remain.
- Add a controlled portrait expression/blink change and inspect stage state before and after it.

## Related tutorials and references

- [Build reliable chapter events](35-event-recipes.md)
- [Add and show a background](38-backgrounds.md)
- [Use inline codes and Tellius fonts](39-inline-text-and-fonts.md)
- [Dialogue engine](../systems/dialogue-engine.md)
- [Message format](../formats/message-format.md)
- [Event script format](../formats/event-script.md)

---

[← Previous: Edit shared startup helpers and endings](36-shared-scripts.md) · [All tutorials](index.md) · [Next: Add and show a background →](38-backgrounds.md)
