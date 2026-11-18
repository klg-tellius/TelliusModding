---
id: "what-you-can-edit"
title: "What You Can Edit"
description: "Which parts of Path of Radiance and Radiant Dawn the Tellius Modding app edits in version 1.0, which discs it reads, and its known limits"
games: ["path-of-radiance", "radiant-dawn"]
section: "meta"
article_type: "portal"
tags: ["Portal", "Modding app", "Limits", "Radiant Dawn"]
aliases: []
status: "published"
last_reviewed: "2026-11-18"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "meta"
source_path: "meta/what-you-can-edit.md"
---
# What You Can Edit

*Which parts of each game the Tellius Modding app edits in version 1.0, which discs it reads, and what it does not do yet*

Tellius Modding 1.0 edits both Tellius games: *Fire Emblem: Path of Radiance* (GameCube, 2005) and *Fire Emblem: Radiant Dawn* (Wii, 2007). Both games open in the same workspace, with the same pages and the same buttons. This page says, area by area, what each game lets you change, and lists the limits you should know before planning a mod.

The tutorials in [Modding Path of Radiance](../modding/index.md) are written on Path of Radiance. Most of them apply to Radiant Dawn as well: where a page or a field works differently, the tutorial has an **On Radiant Dawn** section or says so in **Limits and confidence**. The file formats of Radiant Dawn are collected on [Radiant Dawn](radiant-dawn.md).

## Supported discs

| | Path of Radiance | Radiant Dawn |
| --- | --- | --- |
| Console | GameCube | Wii |
| Regions | US (`GFEE01`), Europe (`GFEP01`), Japan (`GFEJ01`) | US (`RFEE01`), Europe (`RFEP01`), Japan (`RFEJ01`) |
| Disc images read | `.iso`, `.gcm`, `.ciso`, `.wdf`, `.wia`, `.rvz` | `.iso`, `.wbfs`, `.ciso`, `.wdf`, `.wia`, `.rvz` |
| Built image | `build/<project>.ciso` | `build/<project>.wbfs` |
| Ways to share a mod | `.tpatch` patch | `.tpatch` patch, or a Riivolution folder played from an unmodified disc |

An `.rvz` image is converted with DolphinTool, which comes with Dolphin: set Dolphin's path in **Settings** first. You need your own copy of the game; the app never includes or downloads game data. The project records where your disc image is and does not copy it.

Offsets and examples in the archive are given for the US release unless a page says otherwise. The European and Japanese discs are read and built the same way; their text and a few tables differ (see [Regional Releases](../systems/regional-releases.md)).

## What each game lets you edit

**Yes** means the app reads and writes it. **View** means the app shows it but does not change it. A dash means the game has nothing of that kind, or the page is not offered for that game.

### Characters and game data

| Area | Path of Radiance | Radiant Dawn | Where |
| --- | --- | --- | --- |
| Characters: stats, growths, class, skills, portrait, models | Yes | Yes | Characters, [Create a character](../modding/10-create-character.md) |
| Classes, items and weapons, skills, terrain | Yes | Yes | Game Data, [Classes](../modding/16-classes.md), [Items](../modding/17-items-and-weapons.md), [Skills](../modding/18-skills.md), [Terrain](../modding/19-terrain-types.md) |
| Growth tables (`FE10Growth`) | — | Yes | Game Data |
| Supports: partners, thresholds, conversations | Yes | Yes (partners, bonds and affinities) | [Supports](../modding/13-supports.md) |
| Difficulty constants and army groups | Yes | Yes | Game Data › General, [Difficulty and armies](../modding/20-difficulty-and-armies.md) |
| Excel export and import of the tables | Yes | Yes | Game Data, [Bulk edit](../modding/67-bulk-edit.md) |
| Colour variants of a character or class | Yes | Yes | **Colour variant…** |
| Shops and forge | Yes | Yes | [Shops](../modding/46-shops.md) |
| AI scripts (`cp_data`) | Yes | Yes | [AI language](../modding/43-ai-language.md) |
| Event and campaign flags | Yes | Yes | [Event flags](../modding/34-event-flags.md) |
| Extended flags (more flags than the game has) | Yes | — | Game Code |

### Chapters and maps

| Area | Path of Radiance | Radiant Dawn | Where |
| --- | --- | --- | --- |
| Chapter data: objectives, music, backgrounds, weather | Yes | Yes | Chapter › Chapter data |
| Story order and **Add chapter** | Yes | Yes | [Chapter IDs and story flow](../modding/07-chapter-ids-and-story-flow.md) |
| New campaign (several chapters at once) | Yes | Yes | [New campaign wizard](../modding/08-new-campaign-wizard.md) |
| Hub chapters | Yes | Yes | [Hub chapters](../modding/hub-chapters.md) |
| Part 4 army switching (which army a chapter plays) | — | Yes | Chapters › Overview, [Chapter IDs and story flow](../modding/07-chapter-ids-and-story-flow.md) |
| Chapter parts and phases (several maps in one chapter) | Yes | — (each map is its own chapter record) | [Chapter parts and phases](../modding/65-chapter-parts-and-phases.md) |
| Map terrain, heights, props, settings | Yes | Yes | [Build tab](../modding/21-map-build-basics.md) |
| Deployments by difficulty, reinforcements | Yes | Yes | [Deployment](../modding/29-deployment-sections.md) |
| Event scripts | Yes | Yes | [Script editor](../modding/33-script-editor.md) |
| Dialogue and conversations | Yes | Yes (preview less exact) | [Dialogue editor](../modding/37-dialogue-editor.md) |
| Fonts | Yes | Yes | [Inline text and fonts](../modding/39-inline-text-and-fonts.md) |

### Assets and battle presentation

| Area | Path of Radiance | Radiant Dawn | Where |
| --- | --- | --- | --- |
| Portraits | Yes | Yes (4:3 and 16:9 sets) | [Portraits](../modding/11-portraits.md) |
| 3D models: import, export, new slots | Yes | Yes | [Blender round trip](../modding/51-blender-round-trip.md) |
| Map model registry | Yes | View, plus a model's variant | Assets › Animation Data |
| Battle data, battle cameras | Yes | Yes | [Battle cameras](../modding/70-battle-cameras.md) |
| Battle weapons, sceneries, unit parameters | Yes | Yes | [Battle presentation](../modding/55-battle-presentation.md) |
| Battle backgrounds | Yes | Yes (with the sky backdrops) | [Battle backgrounds](../modding/28-battle-backgrounds.md) |
| Visual effects and particles | Yes | Yes | [Visual effects](../modding/69-visual-effects.md) |
| Icons and textures | Yes | Yes | [Graphics](../modding/50-graphics.md) |
| Music and sound effects | Yes | Yes | [Music](../modding/47-music.md), [Sound effects](../modding/48-sound-effects.md) |
| Videos | Yes | Yes | [Videos](../modding/49-videos.md) |
| Tutorials, staff credits, Sound Room | Yes | Yes | [Sound Room, credits and tutorials](../modding/73-sound-room-credits-tutorials.md) |
| Ending illustrations | Yes | — | Assets |

### Tools

| Area | Path of Radiance | Radiant Dawn | Where |
| --- | --- | --- | --- |
| Game Code (engine tweaks in `main.dol`) | Yes, US, Europe and Japan | Yes, US, Europe and Japan | [Game Code](../modding/57-game-code.md) |
| Save editor: units, convoy, flags | Yes (memory-card `.gci`) | Yes (`FE10_US.dat`, `FE10_EU.dat` or `FE10_JP.dat` from Dolphin's Wii memory) | [Save editor](../modding/59-save-editor.md) |
| Check | Yes | Yes | [Check a project](../modding/05-check-project.md) |
| Play a chapter in the app, battle simulator | Yes | Yes | [Play a chapter](../modding/58-play-chapter.md), [Battle simulator](../modding/56-battle-simulator.md) |
| Play in Dolphin, jump to a chapter | Yes | Yes | [Dolphin setup](../modding/04-dolphin-setup.md) |
| Patches (`.tpatch`) and Tellius Patcher | Yes | Yes | [Share a patch](../modding/61-share-a-patch.md) |
| Export for Riivolution | — | Yes | [Share a patch](../modding/61-share-a-patch.md) |
| Export as text (for version control) | Yes | Yes | Disc & Patch |

## Not in version 1.0

- **The Wii HOME Menu** (`system/HomeButton/` on the Radiant Dawn disc). It is Nintendo's HOME button library, the same on every Wii game, not game data. The app copies it unchanged.
- **`client.bin`**, the Game Boy Advance program that the GameCube sends over the link cable (Path of Radiance; Radiant Dawn carries an unused copy). It is identified but not disassembled, and the app copies it unchanged.
- **Encrypted Wii saves.** The save editor reads the unencrypted save from Dolphin's Wii memory. A `data.bin` copied from a Wii's Data Management screen can't be opened.

## Known limits

Read [Know the current limits](../modding/63-known-limits.md) for the engine's fixed sizes (chapter numbers, flags, skills, terrain types, model budgets) and how to plan around them. The points below are the ones that most often surprise a first-time user.

### Both games

- **A preview is not the game.** The in-app playthrough, battle simulator, conversation preview and model viewer reproduce the game closely but not exactly: fog is class vision only, the AI's choice is scored like the game's but not every term is simulated, effects have no trails, and timing is approximate. Test every chapter in Dolphin before release.
- **Check does not read script logic.** It finds broken records, files, IDs and some engine limits, not a missing message ID or a script that never sets its flag ([Check a project](../modding/05-check-project.md)).
- **Records are referenced by number.** Saves and scripts store characters, classes and items by their table position: add new records at the end, and only remove the last record of a released mod ([Remove records](../modding/15-remove-records.md)).
- **Game Code changes only known builds.** An executable that the app does not recognise is shown read-only; every change is checked against the original bytes before it is written.
- **Some edits are not yet tested in the game.** Each tutorial's **Limits and confidence** says what was played in Dolphin and what was only checked in the app. Treat the second kind as a prototype.

### Path of Radiance

- A build larger than a GameCube disc (1,459,978,240 bytes) is still written: it runs in Dolphin but not on a console or a loader that checks the size. Large replacement videos are the usual cause ([Videos](../modding/49-videos.md)).
- Chapters 28 and 29 are the two halves of chapter 27 and stay linked; the war record holds 40 chapters ([Campaign limits](../modding/09-campaign-limits.md)).

### Radiant Dawn

- The conversation preview has not been compared with the game the way Path of Radiance's was: check the timing and the portraits' places in Dolphin.
- Some save fields are still unnamed (a few words of the `FGPT`, `T  T` and `RELD` sections): the editor keeps them as they are.
- Some bytes of the battle tables and of the animation files have a known size but no known meaning; the app keeps them unchanged. The open items are listed in the [Radiant Dawn undecoded inventory](https://github.com/klg-tellius/TelliusModding/blob/main/App/docs/RD_UNDECODED_INVENTORY.md).
- The Riivolution export is checked on generated files; play it in Dolphin before sharing it.

## Related pages

- [Install the app and create a project](../modding/01-install-create-project.md)
- [Troubleshoot builds and crashes](../modding/64-troubleshooting.md)
- [Radiant Dawn](radiant-dawn.md)
- [File Format Index](format-coverage.md)
