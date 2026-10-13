---
id: "topic-registry"
title: "Master topic registry"
description: "The complete editorial map for published, planned, and research-dependent Tellius Archive coverage"
games: ["path-of-radiance", "radiant-dawn"]
section: "meta"
article_type: "portal"
tags: ["Portal", "Coverage", "Open questions"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "meta"
source_path: "meta/topic-registry.md"
---
# Master topic registry

This is the editorial map for Tellius Archive. A subject can be a focused article, an article series, or a portal. Existing migrated articles are **Published**. New subjects begin as **Draft**, **Stub**, or **Research needed** and should link to established surrounding knowledge rather than speculate.

| State | Meaning |
|---|---|
| **Published** | Reviewed public article meeting the teaching and evidence standard |
| **Draft** | Supported content is being organized or written |
| **Stub** | Useful boundary page exists, but full explanation is incomplete |
| **Research needed** | Evidence is insufficient for a reliable technical article |

The [File Format Index](format-coverage.md) and [Open Questions](unexplored.md) hold the current detailed coverage. The lists below define the intended complete information architecture.

## Orientation and modding workflow

- Tellius Archive overview; what Tellius modding can change
- Legal and ethical boundaries; required tools and terminology
- Dumping and extracting a disc
- Project structure, originals, workspace, and build output
- First safe edit; backup, restore, and recovery
- Building an ISO; creating and distributing patches
- Testing in the app and Dolphin
- Compatibility, game regions, and revisions
- Troubleshooting and known limitations
- Contributing, article style, citations, and confidence conventions

## Disc, executable, and containers

- GameCube disc structure and FST; `sys/` and `files/` directory map
- `main.dol`; DOL sections, addresses, hooks, and code caves
- LZ10 compression; pack/CMP archives; labeled-section containers
- Pointers, relocation tables, labels, and string pools
- TPL textures; regional/version differences
- Disc coverage index; file-format coverage index
- Unknown files and undecoded bytes

## Core game data

- `FE8Data.bin`
- Characters and runtime units; classes and class records
- Promotion paths, promotion bonuses, and base reclassing
- Items and weapons; ranks, usable-weapon rules, effectiveness, and restrictions
- Forging and forge records
- Skills, capacity, Occult scrolls, mastery mapping, and individual skill deep dives
- Level-up growth, fixed/random modes, stat caps, and derived statistics
- Laguz transformation and biorhythm
- Armies, allegiance, and forces
- Economy, gold, shops, and storage
- Supports, affinities, bonds, and support bonuses
- Tutorial data and tutorial browser

## Chapters, maps, and campaigns

- Chapter records, lifecycle, progression, and multi-part chapters
- Creating and replacing chapters; campaign ordering; hub chapters
- Objectives, victory, defeat, and escape
- Map file format; coordinate systems and grids
- Terrain types, movement costs, bonuses, and height
- Fog of war, sight, weather, lighting, and ambience
- Map objects, instances, props, animated props, buildings, roofs, doors, and rocks
- Water, flow, and map flags
- Deployment/disposition format; units, groups, inventories, and AI assignments
- Reinforcements and difficulty variants
- Battle scenery selection
- World-map scenes, markers, regions, and routes
- Chapter validation and campaign testing

## Events, dialogue, and narrative presentation

- Event-script bytecode and `.fe9s` source language
- Script compilation, decompilation, triggers, entry points, and complete function reference
- Global and chapter event flags; save persistence of flags
- Recruitment and unit-state changes
- Visits, villages, chests, doors, and area events
- Camera, movement, fades, sound, timing, event battles, and scripted combat
- Message format, message lookup, and dialogue control codes
- Conversation layouts, seats, portraits, text boxes, inheritance, and scene context
- Fonts, glyph coverage, inline icons, and text effects
- Base conversations, support conversations, and death quotes
- Cutscenes, movies, illustrations, endings, and staff credits

## Combat, skills, and AI

- Combat resolution; attack speed, doubling, damage, hit, avoid, critical, and accuracy
- Weapon triangle, weapon-type behavior, effective damage, battle order, and follow-up attacks
- Skill activation order and interactions
- Sol, Luna, Aether, Counter, Corrosion, Cancel, Miracle, Wing Guard, Vantage, Steal, Chant, and Canto
- Status effects; staves and healing; map actions
- Enemy AI overview and `cp_data.bin`
- AI script language and operations
- Attack scoring, target selection, movement weights, routes, and threat maps
- Healing, item use, stealing, and staff AI
- Battle simulator and game-parity testing

## Graphics, UI, models, and animation

- Graphics and image overview; TPL formats, palettes, mipmaps, and texture limits
- Portrait and face data; portrait animation
- Item, skill, status, and UI icons
- `Rect.bin`, UI layouts, backgrounds, gradients, text layers, and windows
- Font formats and replacement
- `.g`, `.gs`, and `.ga`; meshes, materials, blending, and shapes
- Skeletons, posing, skinning, animation tracks, interpolation, loops, and events
- `FE8Anim.bin`, `FE8Effect.bin`, and particle effects
- Map models, battle models, weapon models, and forged-weapon previews
- Battle staging, cameras, backgrounds, and lens flares
- Terrain texture blending, masks, roads, and shores
- Battle scenery and ZDBX/DBX parameters
- glTF export/import; rig replacement and animation retargeting
- Model slots, character overrides, texture variants, performance, and vanilla limits

## Audio and video

- Music system, MusyX resources, and song/sequence data
- `gcfesnd.bin`; sound effects and sound banks
- STM and DSP-ADPCM
- Importing and replacing music or sound effects
- Sound Room data
- THP video; replacing cutscene video
- Audio/video timing and encoder limitations

## Saves, unlocks, and internal systems

- GameCube `.gci`, save slots, and save blocks
- Character progression, inventory, support, flag, and forge save data
- System data, options, records, and unlocks
- Trial maps, bonus content, GBA link, and `client.bin`
- Developer/debug menus and internal battle tools
- Tutorial state and chapter-clear history
- Save compatibility after structural mods

## TelliusModding application guides

- Installation, project creation, workspace, and navigation
- Character, class, item, skill, and support editors
- Chapter settings, deployment, map builder, and terrain editor
- Dialogue, scene, script, and AI editors
- Shop, music, sound, video, font, portrait, icon, and particle tools
- Model viewer and 3D import tools; save editor
- Game-code patches and tunables; campaign simulator
- Validation, build, patch export, and release workflow
- Recovery, originals, change log, and known bugs

## Radiant Dawn roadmap

- Radiant Dawn portal and differences from Path of Radiance
- Disc/container survey; FE10 core data and growth data
- Message format, portraits, `FE10Conversation.cms`, and conversation rendering
- Event scripts, language differences, and script-function reference
- Character, class, item, skill, chapter, map, support, combat, AI, graphics, audio, save, and executable parity pages
- A parity matrix marking each Path of Radiance topic **verified**, **different**, **unknown**, or **not applicable** for Radiant Dawn

Path of Radiance completion takes priority. A Radiant Dawn page must identify which findings were checked directly rather than inheriting Path of Radiance assumptions.

## Research and project meta

- Documentation conventions and evidence methodology
- Source and attribution registry; terminology glossary
- File and system coverage dashboards
- Open questions and research-needed topics
- Reproduction steps for confirmed findings
- Regional comparison
- Changelog and recent discoveries
- Credits and contributor history
