---
id: "modding"
title: "Modding Path of Radiance"
description: "Task-first tutorials for building a Path of Radiance mod with the Tellius Modding app"
games: ["path-of-radiance"]
section: "modding"
article_type: "portal"
tags: ["Guide", "Portal", "Modding app"]
aliases: []
status: "published"
last_reviewed: "2026-10-15"
sources: ["telliusmodding-source"]
cms_collection: "modding"
source_path: "modding/index.md"
---
# Modding *Path of Radiance*

Learn the Tellius Modding app by making controlled changes you can explain, test, and reverse. The curriculum covers the original 64 topics, but you no longer have to read them as one long numbered sequence. Choose a track for the thing you want to build, follow its prerequisites, and use the field references when you need to understand every control.

!!! info "The tutorials are being deepened in phases"
    A deep tutorial explains exact UI actions, every relevant control, useful variations, interactions, failures, and a test matrix. Pages that still use the shorter format remain available while they are rewritten. The [coverage ledger](../meta/tutorial-coverage.md) records the migration state, and the [authoring standard](../meta/tutorial-authoring-standard.md) defines what “complete” means.

## Start with one working change

Use a practice project for your first pass. [Install and extract your disc](01-install-create-project.md), [learn where records live](02-workspace-tour.md), and [practice saving](03-saving-and-restoring.md). Then [build and boot the unmodified project](04-dolphin-setup.md) and [record your Check baseline](05-check-project.md). This gives you something known to work before you add content.

For your first visible exercise, [copy a character](10-create-character.md), [place the copy in a chapter](30-deployment-by-difficulty.md), and [Play that chapter](58-play-chapter.md). Confirm the new unit's identity, equipment, and position. Save, rebuild, and find the same unit in Dolphin. You have now completed the full edit → save → check → play → build loop.

## Choose a curriculum track

| Track | Start here | What you will be able to do |
| --- | --- | --- |
| Start safely | [Install and create a project](01-install-create-project.md) | Preserve a known-good baseline, understand save ownership, build, boot, and diagnose the project |
| Campaign foundations | [Understand chapter parts](06-chapter-anatomy.md) | Identify chapter resources, route story progression, and plan within engine limits |
| Characters and game data | [Create a character](10-create-character.md) | Build characters, classes, items, skills, supports, and shared movement rules |
| Maps | [Use the Build tab](21-map-build-basics.md) | Shape terrain, collision, height, props, settings, and battle scenery |
| Units and events | [Choose deployment sections](29-deployment-sections.md) | Place difficulty variants, author reinforcements, compile scripts, and manage flags |
| Dialogue and text | [Author dialogue](37-dialogue-editor.md) | Build scenes, messages, backgrounds, title presentation, and fonts |
| AI, economy, and media | [Read AI scripts](43-ai-language.md) | Control units, shops, music, sound, video, and graphics |
| Models and battle presentation | [Round-trip a model](51-blender-round-trip.md) | Work with models, rigs, animation, cameras, weapons, and scenery |
| Test and release | [Simulate a fight](56-battle-simulator.md) | Separate previews from game proof, diagnose failures, and ship a reproducible patch |

Each track begins with a guided route. A lesson's **Related tutorials and references** section names the minimum prerequisites and the next useful task. You can also jump directly to a field reference without pretending that it replaces the hands-on test.

## Choose your next project

| I want to… | Follow these lessons | Finish when… |
| --- | --- | --- |
| Add a playable character | [Character](10-create-character.md) → [Portrait](11-portraits.md) → [Deployment](29-deployment-sections.md) → [Recruitment](14-recruitment-and-bosses.md) | The intended talk recruits the correct unit once |
| Make a small battle map | [Build](21-map-build-basics.md) → [Terrain](22-paint-terrain-and-blocking.md) → [Props](24-map-props.md) → [Placements](30-deployment-by-difficulty.md) | Units can traverse the intended routes on each difficulty |
| Write an opening scene | [Script](33-script-editor.md) → [Dialogue](37-dialogue-editor.md) → [Background](38-backgrounds.md) | The opening reaches the message with the right scene context |
| Add a tactical surprise | [Sections](29-deployment-sections.md) → [Flags](34-event-flags.md) → [Reinforcements](32-reinforcements.md) → [AI](43-ai-language.md) | The wave arrives once and follows its intended orders |
| Replace art or sound | [Graphics](50-graphics.md), [models](51-blender-round-trip.md), or [music](47-music.md) | The resource works in its actual in-game context |
| Release a complete project | [Mini-campaign](62-mini-campaign.md) → [Troubleshooting](64-troubleshooting.md) → [Patch](61-share-a-patch.md) | A patch applied to a clean matching disc passes the release test |

## How to follow a deep lesson

Start with **What you will make** and create the named checkpoint in **Before you begin**. Follow the numbered **Guided walkthrough** without combining unrelated changes. Read **Understand every control** before designing your own variant, then complete the four-part **Test matrix**. **Save, build, and revert** tells you which action owns the change. **Limits and confidence** says whether the evidence comes from source, the app, a simulator, Dolphin, inference, or an unresolved question.

Older lessons retain their compact **Route**, **Steps at a glance**, and **Check your result** sections until their track is migrated. Treat those pages as an introduction rather than a complete editor reference.

Images are original explanatory diagrams, clearly labeled as such, rather than screenshots. Select one to enlarge it. Example IDs such as `PID_TUTORIAL_GUARD` are placeholders to create and check for uniqueness, not records guaranteed to exist in your disc. Features labeled **Untested in game** keep that status until verified in Dolphin; the app preview alone does not establish it.

### Terms you will encounter

| Term | What it means while editing |
| --- | --- |
| Record | One entry in a shared table, such as a character or item |
| ID/reference | The exact identity one record uses to find another; a similar displayed name is not interchangeable |
| PID / JID / IID / SID | Character / class / item / skill identifiers |
| Name key / Message ID | A reference to text; changing a shared text entry affects its other users |
| Section | A named group of deployed units, with its own header and loading role |
| Part/phase | The selected chapter/map portion; distinguish this from player/enemy turn phases |
| Apply | Transfer a form's changes into its editor/session; follow with the named Save action |
| Save | Write the owning resource; it does not rebuild a previously generated disc image |
| Build | Pack saved project files into a new playable image |

The [saving lesson](03-saving-and-restoring.md#which-save-belongs-to-this-change) identifies the save action for each major editor. Check it whenever a task touches more than one resource.

## Recommended route

[Getting started](01-install-create-project.md) → [Campaign planning](06-chapter-anatomy.md) → [Characters](10-create-character.md) → [Maps](21-map-build-basics.md) → [Deployment](29-deployment-sections.md) → [Events](33-script-editor.md) → [Dialogue](37-dialogue-editor.md) → [AI](43-ai-language.md) → [Testing](58-play-chapter.md) → [Sharing](61-share-a-patch.md) → [Mini-campaign](62-mini-campaign.md)

## All tutorials

### Set up and learn the workflow

1. [Install the app and create a project](01-install-create-project.md)
2. [Tour the workspace](02-workspace-tour.md)
3. [Save changes and restore originals](03-saving-and-restoring.md)
4. [Set up Dolphin and build the game](04-dolphin-setup.md)
5. [Check a project and fix problems](05-check-project.md)

### Plan a campaign

6. [Understand a chapter's parts](06-chapter-anatomy.md)
7. [Work with chapter IDs and story order](07-chapter-ids-and-story-flow.md)
8. [Create a campaign skeleton](08-new-campaign-wizard.md)
9. [Plan around campaign limits](09-campaign-limits.md)

### Build the cast and shared rules

10. [Create a character](10-create-character.md)
11. [Create and assign a portrait](11-portraits.md)
12. [Give a character unique models](12-character-model-slot.md)
13. [Create supports and conversations](13-supports.md)
14. [Recruit by talk and make a boss](14-recruitment-and-bosses.md)
15. [Remove records without corrupting saves](15-remove-records.md)
16. [Create and link a class](16-classes.md)
17. [Create an item or weapon](17-items-and-weapons.md)
18. [Edit and redistribute skills](18-skills.md)
19. [Edit terrain and movement costs](19-terrain-types.md)
20. [Tune difficulty and army groups](20-difficulty-and-armies.md)

### Shape the map

21. [Use the map Build tab](21-map-build-basics.md)
22. [Paint terrain and block movement](22-paint-terrain-and-blocking.md)
23. [Edit tile heights and slopes](23-tile-heights.md)
24. [Place, copy, and import props](24-map-props.md)
25. [Replace a terrain mesh](25-terrain-mesh.md)
26. [Import water and set its flow](26-water.md)
27. [Set fog, lighting, border, and objectives](27-map-settings.md)
28. [Assign battle backgrounds by terrain](28-battle-backgrounds.md)

### Place units and write events

29. [Choose deployment sections](29-deployment-sections.md)
30. [Place units for each difficulty](30-deployment-by-difficulty.md)
31. [Set inventory, drops, rings, and flags](31-unit-inventory-and-flags.md)
32. [Add a reinforcement wave](32-reinforcements.md)
33. [Edit and compile event scripts](33-script-editor.md)
34. [Use campaign and chapter flags](34-event-flags.md)
35. [Build common chapter events](35-event-recipes.md)
36. [Edit startup helpers and endings](36-shared-scripts.md)

### Tell the story

37. [Author dialogue and cutscenes](37-dialogue-editor.md)
38. [Add and show a background](38-backgrounds.md)
39. [Use inline codes and Tellius fonts](39-inline-text-and-fonts.md)
40. [Edit base conversations and narration](40-base-and-world-map-text.md)
41. [Set chapter title cards and movies](41-chapter-opening-movies.md)
42. [Import a translation font](42-font-translation.md)

### Tune behavior and resources

43. [Read and edit AI scripts](43-ai-language.md)
44. [Create common AI orders](44-common-ai-orders.md)
45. [Inspect why AI chose a target](45-inspect-ai-decisions.md)
46. [Edit armory, vendor, forge, and gold](46-shops.md)
47. [Replace or add music](47-music.md)
48. [Add or replace sound effects](48-sound-effects.md)
49. [Replace a video and manage disc size](49-videos.md)
50. [Replace 2D graphics](50-graphics.md)

### Work with models and battle presentation

51. [Round-trip a model through Blender](51-blender-round-trip.md)
52. [Replace or fit a humanoid rig](52-replace-rig.md)
53. [Import animations and edit events](53-animation-import.md)
54. [Edit weapon and scenery models within budgets](54-model-budgets.md)
55. [Edit battle presentation](55-battle-presentation.md)

### Test, troubleshoot, and release

56. [Simulate and render a fight](56-battle-simulator.md)
57. [Apply engine tweaks](57-game-code.md)
58. [Play and rewind a chapter in the app](58-play-chapter.md)
59. [Edit and test a save](59-save-editor.md)
60. [Use the game's debug menus](60-debug-menus.md)
61. [Package and share a mod](61-share-a-patch.md)
62. [Build a three-chapter mini-campaign](62-mini-campaign.md)
63. [Know the current limits](63-known-limits.md)
64. [Troubleshoot builds and crashes](64-troubleshooting.md)

## Screenshot work for contributors

Real app screenshots are still pending. The [capture checklist](../meta/tutorial-screenshot-plan.md) specifies setup and result frames for every lesson, additional intermediate states, filenames, captions, and acceptance checks. It is an authoring handoff, not evidence that those captures or gameplay tests have already been completed.
