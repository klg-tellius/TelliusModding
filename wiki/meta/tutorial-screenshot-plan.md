---
id: "tutorial-screenshot-plan"
title: "Tutorial screenshot capture plan"
description: "An executable capture checklist for real Tellius Modding screenshots across all 64 tutorials"
games: ["path-of-radiance"]
section: "meta"
article_type: "guide"
tags: ["Guide", "Contributing", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-15"
sources: ["telliusmodding-source"]
cms_collection: "meta"
source_path: "meta/tutorial-screenshot-plan.md"
---
# Tutorial screenshot capture plan

**Capture status: in progress.** The app-only frames are taken by `App/tools/capture_tutorial_screenshots.py` and listed, with the frames still to take, in the [capture log](tutorial-capture-log.md). Frames that need Dolphin, Blender or sample media are still pending. SVG diagrams are explanatory illustrations and do not count as captures. This is a handoff for an agent or person operating the real desktop app, with Dolphin and Blender where explicitly required.

The objective is to show a reader **where to act, what to enter, and what a successful result looks like**. Capture the specific lesson state below, not merely an empty editor or a generic application window.

## Prepare one reproducible capture project

1. Record the app version/build or source commit, disc region/revision, Windows display scaling, app theme, and window size. If the running app differs from the source used by the tutorial, reconcile the labels before annotating screenshots.
2. Use a disposable project copy named **Tutorial Practice** with a working extracted disc and a known-good baseline build. Keep the user's working project and saves untouched. Do not re-extract over edited files to reset a lesson.
3. Choose one working chapter with a short opening and ordinary deployment. Record its **actual slot, displayed title, part/phase, map folder, and difficulty**. Never infer the disc slot from the displayed chapter number. Use the same chapter for related lessons unless a feature requires another template.
4. Choose one working character/class/item combination. Create `PID_TUTORIAL_GUARD` only if unused. For any example message, section, cue, or flag, record the actual ID created and use it consistently across the editor, script, captions, and result.
5. Save checkpoints after extraction, the baseline build, character placement, terrain editing, reinforcement setup, dialogue editing, and the release candidate. Use copies of the correct checkpoint for destructive or incompatible exercises such as record removal, rig replacement, and save editing.
6. Prepare permitted sample art, WAV/video, a compatible glTF export, a font, and copied `.gci` files only for lessons that need them. Record missing dependencies as **blocked**, rather than substituting unrelated content or simulating a successful result.

## File names, placement, and evidence

Store accepted PNGs under `wiki/assets/images/tutorials/screenshots/`.

- Each numbered row requires two files: **`NN-a-setup.png`** and **`NN-b-result.png`**, where `NN` is the two-digit lesson number. Together the checklist defines **128 required captures**.
- Extra frames use a descriptive suffix, for example `32-c-repeat-check.png`. Extra-frame requirements are listed after the tables.
- Preserve the raw capture. If annotations are helpful, save a separate `NN-a-setup-annotated.png`; do not replace the raw file. Add numbered callouts beside controls without obscuring labels, values, warnings, or preview content. No reconstructed controls or generated screenshots.
- Insert **A** beside the matching setup/action step in the lesson's **Guided walkthrough**. Insert **B** beside the result test. Extra frames belong beside the exact intermediate step they explain. Replace an interface schematic once its real capture is accepted; retain a conceptual diagram only if it explains something the screenshot cannot.
- Do not add Markdown image links until the files exist. `capture_tutorial_screenshots.py --insert` adds only logged frames, setup frames at the start of the lesson's **Guided walkthrough** and result frames at its end; move a figure beside its exact step by hand when a lesson is rewritten (the `<!-- screenshot … -->` marker keeps it recognised).
- Record each file in the capture log (`screenshots/capture_log.json`, published as the [capture log](tutorial-capture-log.md)) with: lesson and step, checkpoint, actual record IDs, app/build version, chapter/part/difficulty, actions performed, observed result, capture date, raw/annotated paths, draft caption, alt text, and status. Allowed statuses: **pending**, **captured**, **accepted**, **blocked**. A successful screenshot API response alone does not make a capture accepted.

Use this log entry for every frame:

```text
Capture: 32-b-result.png
Lesson/step: 32, step 5 — first reinforcement arrival
Checkpoint and app build:
Actual chapter / part / difficulty:
Actual section / PID / flag:
Actions performed:
Observed result:
Caption:
Alt text:
Status and remaining issue:
```

## Framing and acceptance

Keep enough application context to identify the editor, selected record, and active variant. Prefer a readable app-window capture at a consistent size, around 1440 × 900 where practical. Capture dialogs with their parent context when that helps locate the action. Avoid the unrelated desktop, notifications, account details, personal file paths, and other applications.

Move the pointer away from important text. Wait for rendering/imports to finish. Keep relevant warnings visible. If the whole window makes text too small at article width, add a detail crop while preserving the full contextual capture. Inspect the final PNG in the built wiki, not only at native resolution.

Captions must explain the action and observation. For example: **“In Start as a copy of, choose the working template. The new ID identifies the copy; its name key is still inherited.”** Alt text should describe the relevant controls/state without repeating every visible label.

For before/after comparisons, keep the same record, zoom, camera, and test conditions unless the lesson explicitly changes one. A still image cannot prove an event fires once, a loop plays correctly, or a save reloads: perform those tests and log the result. Use the additional frames below as evidence. A failed test is useful evidence for troubleshooting, but must not be captioned as success.

## Capture order

First complete lessons **01–05, 10, 21–22, 29–33, 37, 58, and 61**. These establish the beginner workflow and provide context reusable by later captures. Then capture characters/shared data, remaining map/event features, media, models, and advanced testing.

Open the linked lesson for its route and prerequisites. Within each row, A describes the exact state to prepare and frame; B describes the action to execute and the result to show. The visible values and identities must agree between both frames.

## Setup and campaign planning

| Lesson | A — setup/action view | B — result view |
| --- | --- | --- |
| [01 · Install/create](../modding/01-install-create-project.md) | Open **New Project**. Select Path of Radiance, enter Tutorial Practice, choose the capture-project parent folder. Frame Game, Project name, Create in, path preview, and Create Project. | Complete extraction and open Home. Show the project identity and unlocked workspace sections. Use extra extraction frame below to connect these states. |
| [02 · Workspace](../modding/02-workspace-tour.md) | Open an extracted project's Home; show navigation, breadcrumbs, search, and status bar. | Press Ctrl+K, search for the chosen template character, and frame the populated results with the intended record identified. |
| [03 · Saving](../modding/03-saving-and-restoring.md) | Change one personal bonus on the test character. Show that value, **Apply**, and **Save FE8Data.bin** before applying/saving. | Apply, save, leave, and reopen the same record. Show the persisted value and identity. Log the reopen; the screenshot alone cannot establish persistence. |
| [04 · Dolphin/build](../modding/04-dolphin-setup.md) | Open Preferences. Show **Dolphin location (Dolphin.exe)** with a valid executable selected and discovery status, using a non-personal capture path. | Build and launch the output in Dolphin. Show the baseline game's title screen and record which built image launched. Add the Build card frame below. |
| [05 · Check](../modding/05-check-project.md) | In a disposable copy, introduce one missing reference and run **Tools → Check → Run check**. Frame Severity, Area, File, and the readable Problem row. | Follow the owning record, repair and save the reference, rerun Check. Show the error removed; retain legitimate baseline warnings. |
| [06 · Chapter anatomy](../modding/06-chapter-anatomy.md) | Open chapter Overview with the resource header and Part/Phase selector visible. | Open the matching Build/deployment view. Show the same chapter/part identity and the units/map named by the Overview resources. |
| [07 · Story order](../modding/07-chapter-ids-and-story-flow.md) | Open **Story order…** on a copy. Frame slot identities, titles, and the boundary to change. | Apply the intended order and open the source chapter's Story flow. Show its resulting successor. Caption as editor state, not proof of a Dolphin transition. |
| [08 · Campaign wizard](../modding/08-new-campaign-wizard.md) | Open **New campaign…** with the selected template, reserved slots, and cast/options visible before creation. | Create the skeleton. Frame the new sequence in Chapters and its actual slot identities. Log the initial Check result. |
| [09 · Campaign limits](../modding/09-campaign-limits.md) | Show the actual chapter/slot list used to check availability for the three planned slots. | Show the reserved sequence in Story order after creation. Caption the mapping from reserved slot to title; keep the 40-entry history limit in prose unless an actual UI exposes it. |

## Characters and shared game data

| Lesson | A — setup/action view | B — result view |
| --- | --- | --- |
| [10 · Character](../modding/10-create-character.md) | Open **New character…** with ID `PID_TUTORIAL_GUARD` and **Start as a copy of** pointing to the recorded template. Show Create and the copied-key explanation. | Place the saved copy, restart Play, select it, and show identity, class, inventory, and stats. Add the intermediate Stats and Deployment frames below. |
| [11 · Portrait](../modding/11-portraits.md) | Open **New portrait…** with permitted sample pieces loaded and a unique FID. Show fitted body/eyes/mouth, identity, and relevant controls. | Save and assign the face; open the character's portrait view and show the resolved small/large faces. Label app preview as such. |
| [12 · Model slot](../modding/12-character-model-slot.md) | Open **New slot…** from the selected model. Show new identity, intended character, and promotion-state restriction. | Open **Model tables…** after creation. Show the target resolving to the new slot and capture/log the source still resolving to its original slot. |
| [13 · Supports](../modding/13-supports.md) | In Supports → By character, show the chosen pair and increasing C/B/A thresholds. | Open **Conversation C** with its actual MYELL ID and scene preview. Save both message and FE8Data; log inspection from the partner's view. |
| [14 · Recruit/boss](../modding/14-recruitment-and-bosses.md) | Show the talk event's speaker/target trigger, Join call, and guard using the deployed recruit's PID. Keep enough code visible to read the identities. | Execute the talk in Play; show the recruit's changed allegiance and relevant log/flag. Capture the repeat attempt and boss AI separately as listed below. |
| [15 · Remove records](../modding/15-remove-records.md) | On a checkpoint copy, attempt removal of a referenced test record. Capture the real blocking-reference message. | Repair owners, save, remove, and run Check. Show no remaining dangling-reference error; caption explicitly that this does not prove old-save compatibility. |
| [16 · Class](../modding/16-classes.md) | Show the copied class's JID, bases, and promotes-to link. Include enough context to identify its promoted partner. | In Battle Simulator, show the test unit after promotion with resulting class/stats. Record the same unit's pre-promotion state for comparison. |
| [17 · Item/weapon](../modding/17-items-and-weapons.md) | Show the new item ID, changed might, weapon type/rank/range, and save control. | Render a fight with that item visibly equipped. Include the actual weapon model; add its Battle Weapons table frame below. |
| [18 · Skills](../modding/18-skills.md) | Show an existing skill's SID, capacity, restrictions, and presentation fields. Do not imply a newly appended effect. | Assign it to the test unit and show its skill list/capacity in Play. Log an activation and non-activation case; a skill icon alone is insufficient evidence of its effect. |
| [19 · Terrain definitions](../modding/19-terrain-types.md) | Select the terrain type and show shared-stat information, **Give this type its own stats** where available, and movement-type costs. | Save and paint the type on a short test strip. In Play show the selected unit's reachable tiles and the terrain identity. Add a second movement-type frame for comparison. |
| [20 · Difficulty/armies](../modding/20-difficulty-and-armies.md) | Show the specific General difficulty constant or appended army row, with its mode/index visible. | Play the recorded difficulty and inspect a representative affected unit's level/army. Log the unchanged comparison difficulty or existing army. |

## Map editing

| Lesson | A — setup/action view | B — result view |
| --- | --- | --- |
| [21 · Build basics](../modding/21-map-build-basics.md) | Open the chosen map in Build with phase, difficulty, layers, grid, Save Chapter, Undo/Redo, and Play visible. | Make one reversible tile/placement change, save, and reopen. Frame the same map region and changed location; log Undo/Redo behavior. |
| [22 · Terrain/blocking](../modding/22-paint-terrain-and-blocking.md) | Select **Paint terrain**. Show Terrain type, Fill a rectangle, grid, and the actual prop footprint before painting. | Paint/save the footprint and launch Play. Show a nearby unit's movement range excluding the intended blocked tiles. Add the painted-terrain and second-movement-type frames below. |
| [23 · Heights](../modding/23-tile-heights.md) | Open **Tile heights…** for a selected tile. Frame layer, all four corner values, neighbors, and any edge warning. | Save the intended slope and show a unit crossing/standing on that edge in Play. Keep the tile coordinates consistent and log both directions of traversal. |
| [24 · Props](../modding/24-map-props.md) | Show **Place prop** with chosen prop, angle, target tile, and Add from another map/Import controls. | Place/rotate/save the prop, reopen the map, and show its footprint with terrain/grid visible. Log movement testing under it. |
| [25 · Terrain mesh](../modding/25-terrain-mesh.md) | Import the edited exported set. Show **Keep map texturing**, height/prop/grid options, and actual warnings before writing. | Show the imported surface in Build with the grid and road/shoreline texturing visible. Log walkability; the image must not imply visual sub-tile detail changes movement. |
| [26 · Water](../modding/26-water.md) | Open **Water flow…** after importing the plane. Show both textures' U/V speeds and the visible shoreline. | Show the resulting water preview and import report with terrain mismatches resolved. Log observed scrolling direction; a still cannot prove animation. |
| [27 · Map/chapter settings](../modding/27-map-settings.md) | Open **Map settings & chapter…**, Map tab. Frame fog/lighting/border and Apply. | Open the Chapter tab with actual objective keys and difficulty overrides. Add the in-game objective text/border frame below. |
| [28 · Battle scenes](../modding/28-battle-backgrounds.md) | Show the map's Battle scenes row, chosen terrain/scenery assignment, and a deliberate fallback blank. | Render the same fight using that map/terrain and show the resolved scenery. Log a second render of the fallback terrain. |

## Deployment and event scripting

| Lesson | A — setup/action view | B — result view |
| --- | --- | --- |
| [29 · Sections](../modding/29-deployment-sections.md) | Open Deployment with Difficulty variant, Sections / Units, and **Edit Section...** showing the chosen header. | Start Play with the opening enabled. Show the expected starting group and log that the reinforcement/scene-only groups are absent. Add the Add section dialog frame below; use lesson 30 for placement destinations. |
| [30 · Difficulty placement](../modding/30-deployment-by-difficulty.md) | Show the test unit's Normal placement with starting/arrival coordinates and level fields. | Show its deliberately different Hard placement in the same map region. Log a Play start on both; add Maniac if edited. Never use an unlabeled cropped map. |
| [31 · Drops/flags](../modding/31-unit-inventory-and-flags.md) | Select one enemy's deployment fields. Show its item slots and exactly which slot has a drop flag; include relevant decoded flags. | Defeat that unit in Play and show the obtained item in the log/inventory. The item identity must match the flagged slot in A. |
| [32 · Reinforcements](../modding/32-reinforcements.md) | Show the separate section, exact name, selected difficulty, and one unit's arrival tile. | Advance across the recorded turn/phase in Play. Show the arrived unit, phase/turn, load log, and guard flag where readable. Add trigger and repeat-check frames below. |
| [33 · Script editor](../modding/33-script-editor.md) | Show File, selected Function, Code, and Trigger and description with Apply to code. Select the actual working event used by the exercise. | Check and Save, then show the saved filename/status and changed message reference. Add Insert call help and the triggered message frames below. |
| [34 · Flags](../modding/34-event-flags.md) | Open Flags with the selected flag's scope, users, and remaining-room indicator visible. | Run its event in Play and show the flag after success. Log a repeated-trigger attempt; for campaign scope also perform a chapter boundary and save/reload. |
| [35 · Event recipes](../modding/35-event-recipes.md) | Show one complete village/talk/phase recipe: trigger, guard, action, and completion flag in readable source. | Execute that specific recipe and show its reward/recruit/wave plus state. Capture alternate/repeated branch evidence below instead of claiming all recipes were tested. |
| [36 · Shared scripts](../modding/36-shared-scripts.md) | Select startup.cmb and show the exported helper's name/signature and save status. | Open a chapter caller and show its matching call with a successful check. For the ending subsection, use the extra actual finale-transition frame below. |

## Dialogue and text

| Lesson | A — setup/action view | B — result view |
| --- | --- | --- |
| [37 · Dialogue](../modding/37-dialogue-editor.md) | Select the working Message ID. Show the text editor, highlighted actions, Actions/Layout controls, portrait seats, Live Preview, and Save Chapter. | Save the line “The road ahead is clear.” and trigger the message in Play. Show the visible phrase, speaker, and scene context. Add the caller and parse-error captures below. |
| [38 · Background](../modding/38-backgrounds.md) | Open the generated RID record after Add New Background. Show layers, brightness/fade, preview, and save control. | Execute the actual RectBuild/calling scene and show that background behind its message. Record the exact RID in the caption. |
| [39 · Inline codes](../modding/39-inline-text-and-fonts.md) | Show one line with the inserted font/timing action and the insertion control used. Keep the following ordinary line visible. | Preview both lines, showing the intended glyphs and restored ordinary formatting. Log timing/page behavior and any unsupported-glyph warnings. |
| [40 · Base/narration](../modding/40-base-and-world-map-text.md) | Open the chosen existing base/support or narration message with ID and owning file context visible. | Reach that route in the built game and show the changed text with preceding scene context intact. Do not substitute a standalone message preview for a base-route test. |
| [41 · Title/movie](../modding/41-chapter-opening-movies.md) | Show the opening's actual ChapterMoviePlay slot or MoviePlay path. State which branch of the lesson is being illustrated. | Trigger it in Dolphin and capture the actual title card/video. Log completion and skip resumption; mark added-chapter behavior blocked if it fails. |
| [42 · Font import](../modding/42-font-translation.md) | Open font import with source font, target font, character selection, and size/offset/spacing before/after preview visible. | Show a real menu or dialogue containing the sample glyphs and a long line without clipping. Log retained kana/kanji and unsupported-character behavior. |

## AI, shops, and media

| Lesson | A — setup/action view | B — result view |
| --- | --- | --- |
| [43 · AI language](../modding/43-ai-language.md) | Show the copied Attack/Move script, unique SEQ, readable code, and Apply control. | Show the deployed unit's new assignment and its action in Play's AI panel/log. Log the original template unit still using its old policy. |
| [44 · AI orders](../modding/44-common-ai-orders.md) | Show the stationary boss's Attack and Move choices with the hold rule readable. | Play an enemy turn with a target outside the post. Show the boss remaining at its recorded tile; add an in-range attack frame below. |
| [45 · AI decisions](../modding/45-inspect-ai-decisions.md) | Pause before one enemy acts with two plausible targets visible. Record HP, equipment, positions, and terrain. | Step that AI unit and expand **how the target was chosen**. Frame readable candidate eligibility/scores and the chosen action; use a detail crop if needed. |
| [46 · Shops](../modding/46-shops.md) | Show the selected difficulty's Armory/Vendor stock, Forge grid, Copy to other difficulties, and Save Shops. | Visit the actual shop on that difficulty in the built game. Show the added item and price. Log stock on the other supported modes. |
| [47 · Music](../modding/47-music.md) | Show the track and actual BGM cue mapping after import, including New track/Music cues context where available. | Show the chapter/caller using that same cue. Log Dolphin playback through a loop or tail; do not caption a static cue assignment as proof of audio. |
| [48 · SFX](../modding/48-sound-effects.md) | Show the selected/imported WAV cue with SFX identity and volume/pan/range/group controls. | Show the actual scene/caller using the cue. Log audible playback in context and overlap/tail behavior; a preview button alone is not verification. |
| [49 · Video](../modding/49-videos.md) | Show the imported encoded video in Assets → Videos with resource path and preview. | Show actual playback in Dolphin. Record build size, sync, final audio, and skip resumption; add the build-warning frame only if a real warning occurs. |
| [50 · Graphics](../modding/50-graphics.md) | Show the original exported sheet/cell in its specialized viewer with dimensions and selected resource visible. | Import the single-cell change and show the same sheet framing. Add the real consumer screen for placement/transparency; use separate captures if illustrating credits or Sound Room. |

## Models and battle presentation

| Lesson | A — setup/action view | B — result view |
| --- | --- | --- |
| [51 · Blender round trip](../modding/51-blender-round-trip.md) | In Blender, show the exact exported set with the small geometry edit, armature, and relevant material settings. Record exporter settings in the log. | In Tellius, show the import review with triangles/shapes/bones/warnings and posed preview before writing. Add the final render below; this remains an app-level result until Dolphin testing. |
| [52 · Rig fitting](../modding/52-replace-rig.md) | Open Fit new rig with the actual proposed joint mapping, including left/right limbs and anchors. | Show the fitted rig in an attack pose with weapon attachment and required-event review. Log all clips and Dolphin result; an idle pose alone is insufficient. |
| [53 · Animation events](../modding/53-animation-import.md) | Open Events for the selected clip. Show clip/set identity and readable hit/release/sound event timing. | Preview or render the strike at the synchronization point, with the weapon and target visible. Log recovery/completion to establish the fight does not hang. |
| [54 · Budgets](../modding/54-model-budgets.md) | Show the weapon/scenery import review with actual budget figures and warnings. | Render the same asset from a representative far or oblique camera, showing attachment/textures without clipping. Log near/far checks; no unsupported bow example. |
| [55 · Presentation](../modding/55-battle-presentation.md) | Show the actual camera/unit-parameter or DBX Layout edit with selected resource identity. | Render the fixed test fight after the edit and show readable HUD/framing. Add separate DBX and ranged views if the lesson covers those actions. |

## Testing and release

| Lesson | A — setup/action view | B — result view |
| --- | --- | --- |
| [56 · Battle Simulator](../modding/56-battle-simulator.md) | Show attacker/defender, levels, equipment, distance, scenery, forecast, and deterministic roll/outcome log. | Use Render fight for that exact setup and show a representative strike. Log matching strike order; do not change equipment between captures. |
| [57 · Game Code](../modding/57-game-code.md) | Show recognized executable identity and one catalog option with its original value. | Reopen after saving and show the new value/site. Log focused Dolphin behavior and the unaffected comparison; label untested entries honestly. |
| [58 · Play/rewind](../modding/58-play-chapter.md) | Show Play startup's difficulty and opening choice for the recorded test. | Show the live map, transport controls, current turn/phase, and relevant script/flag/log pane. Add rewind comparison below. |
| [59 · Saves](../modding/59-save-editor.md) | Open a copied GCI with the correct save block selected, one supported field, and Save as/Play in Dolphin controls visible. | Load the separately saved output in Dolphin and show the actual edited state. Mark blocked if loading fails; do not replace with a second editor screenshot labeled “loaded.” |
| [60 · Debug menus](../modding/60-debug-menus.md) | Show the exact Developer tools option enabled for the dedicated test build. | Open that menu in the built game. Log disabling the patch and retesting the release build; do not depict debug state as normal progression. |
| [61 · Patch release](../modding/61-share-a-patch.md) | Show Mod details with example name/author/version and the Disc & Patch Create patch control. | Apply the created patch to a clean matching disc and show the patcher's actual completion/output. Add a smoke-test frame from that output below. |
| [62 · Mini-campaign](../modding/62-mini-campaign.md) | Show the actual three-chapter Story order and slot/title mapping. | Reach the ending in Dolphin from the full campaign run. Log both intermediate save/reload boundaries and retained roster/flag state; add boundary frames below. |
| [63 · Limits](../modding/63-known-limits.md) | Show one actual constrained editor, such as an existing skill slot and its available controls. Caption only what the UI establishes. | Show one real import/capacity/unsupported-operation message encountered in the capture fixture. Do not fabricate a warning to illustrate a documented limit. If no safe reproducible message exists, mark this frame blocked. |
| [64 · Troubleshooting](../modding/64-troubleshooting.md) | Capture a reproducible error from the disposable broken checkpoint, including full problem text and owning resource identity. | Apply the smallest repair, restart the same test, and show the corrected result. Log two clean-launch reproductions and the precise fix. |

## Required intermediate and comparison frames

These frames fill gaps that two stills cannot teach. Keep the same naming and capture-log rules.

| Filename | Exact capture requirement | Insert beside |
| --- | --- | --- |
| `01-c-extract.png` | Disc & Patch with chosen Source disc and enabled Extract; show where to select the image before extraction. | Lesson 01, disc selection/extraction |
| `04-c-build.png` | Build card with Build disc, Build and play in Dolphin, and output location. | Lesson 04, first build |
| `10-c-stats.png` | New PID selected, personal bonus increased by 1, class unchanged, Apply and Save FE8Data.bin visible. | Lesson 10, step 3 |
| `10-d-deployment.png` | Test unit's character field points to that PID; variant, section, item, and Save visible. | Lesson 10, step 4 |
| `14-c-repeat.png` | After recruitment, show guard state/log on a repeated opportunity; record absence of another Join action. | Lesson 14, once-only test |
| `14-d-boss.png` | Boss deployment and actual hold-position AI assignment; include or separately crop the move policy. | Lesson 14, boss setup |
| `17-c-weapon-table.png` | New item's Battle Weapons table resolving its model and normal/forged variants. | Lesson 17, presentation assignment |
| `19-c-movement-type.png` | Second movement type on the same painted strip with reachable tiles visible. | Lesson 19, movement comparison |
| `22-c-painted.png` | Same prop/grid framing as A after painting, with terrain overlay and save control. | Lesson 22, step 3 |
| `22-d-second-unit.png` | Second movement type's actual range around the same footprint; log intended exception if it can cross. | Lesson 22, step 3 |
| `27-c-objective.png` | Built game's objective text and playable border for the recorded difficulty. | Lesson 27, result check |
| `29-c-add-section.png` | Add section dialog with Name, section header, and difficulty-suffix explanation. | Lesson 29, step 3 |
| `30-c-add-to.png` | Build's unit-placement panel with Add to, Common file/Difficulty files choices, checked variants, and Section. | Lesson 30, step 1 |
| `32-c-trigger.png` | Exact section-loading call, configured turn/phase, and guard/set logic in Script. | Lesson 32, step 3 |
| `32-d-before.png` | Play immediately before the trigger; phase/turn and intended empty arrival tile visible. | Lesson 32, step 5 |
| `32-e-repeat.png` | Later eligible phase with guard set and no duplicate wave; log unit count/load count. | Lesson 32, step 5 |
| `33-c-call-help.png` | Insert call dialog with an actual function selected, purpose and numbered argument help readable. | Lesson 33, step 2 |
| `33-d-triggered.png` | Actual edited message reached through the unchanged test trigger. | Lesson 33, step 4 |
| `35-c-alternate.png` | Alternate or repeated branch of the recipe shown in A/B; log why the reward/action does not repeat. | Lesson 35, branch tests |
| `36-c-ending.png` | Actual last-chapter-to-ending transition in the built game. | Lesson 36, finale test |
| `37-c-caller.png` | Script call with exactly the Message ID edited in Dialogue. | Lesson 37, step 4 |
| `37-d-parse-error.png` | Deliberately invalid action in a disposable message, visible parser error, and last-valid-preview notice; restore afterward. | Lesson 37, step 2 warning |
| `44-c-in-range.png` | Same stationary boss attacking an eligible in-range target without abandoning its post. | Lesson 44, role comparison |
| `50-c-consumer.png` | Replaced graphic in the actual game screen that consumes it. | Lesson 50, result check |
| `51-c-render.png` | Imported edited model in Render fight, clearly showing the small geometric change and attachment. | Lesson 51, contextual test |
| `55-c-layout.png` | DBX Layout with the selected HUD widget and its changed placement. | Lesson 55, HUD editing |
| `55-d-ranged.png` | Ranged render using the edited presentation, with projectile and fighters in frame. | Lesson 55, coverage check |
| `58-c-rewind.png` | Same run rewound to the earlier decision; show the history position and relevant state. Log the alternative choice. | Lesson 58, step 4 |
| `61-c-clean-result.png` | Edited content visible in Dolphin launched from the clean patch-application output. | Lesson 61, recipient test |
| `62-c-boundary-one.png` | After chapter 1 save/reload, show chapter 2 and the retained recruit/campaign state. | Lesson 62, first boundary |
| `62-d-boundary-two.png` | After chapter 2 save/reload, show chapter 3 and expected persistent state. | Lesson 62, second boundary |

## Final delivery checks

- Every accepted frame has a raw PNG, a capture-log entry, readable caption/alt text, and an insertion point in the correct lesson.
- The screenshot and prose use the same actual control labels and identities. Correct prose when the running app disproves an instruction.
- No image or caption claims to prove animation, persistence, audio, or once-only behavior without the corresponding performed test in the log.
- Features previously marked untested retain that status unless the relevant engine test was actually completed and documented.
- Image links resolve in the built site. Check both article-width readability and full-size opening. Run the wiki source validator, strict build, and built-site link checker after integration.
- Leave a short handoff of accepted and blocked capture IDs. Do not mark this checklist complete because some generic application screenshots were collected.
