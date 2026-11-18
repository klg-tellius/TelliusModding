---
id: "main"
title: "Main Page"
description: "A field reference to how Fire Emblem: Path of Radiance and Radiant Dawn store themselves, and a guide to modding them"
games: ["path-of-radiance","radiant-dawn"]
section: "meta"
article_type: "portal"
tags: ["Portal"]
aliases: ["tellius_archive.html#/main"]
status: "published"
last_reviewed: "2026-11-18"
sources: ["tellius-archive-research"]
cms_collection: "pages"
source_path: "index.md"
---
# Main Page

*A field reference to how Fire Emblem: Path of Radiance and Radiant Dawn store themselves*

The **Tellius Archive** is the documentation of the Tellius Modding app. It documents, at the byte level, how *Fire Emblem: Path of Radiance* (GameCube, 2005) and *Fire Emblem: Radiant Dawn* (Wii, 2007) store their data and how the systems built from that data work: how a chapter script decides when a cutscene plays, how a class's promotion bonus is computed, and how a battle animation is selected for a given weapon.

  Two kinds of article make up the archive. **File format** articles describe a container or record layout byte-for-byte — offsets, field widths, what a pointer resolves to. **Game system** articles describe a mechanic in play — classes, skills, chapters, music — and link back down to whichever files implement it. Most systems draw on more than one format at once; most formats serve more than one system.

  Start with [Disc & File Layout](./meta/disc-layout.md) for a tour of the extracted game, [File Format Index](./meta/format-coverage.md) for a completeness-oriented catalog, or [Documentation Conventions](./meta/sources.md) for identifiers, offsets, and confidence labels.

## Start here

  New to the app? [Install it and create a project](modding/01-install-create-project.md), then read [What You Can Edit](meta/what-you-can-edit.md): it lists, for each game, which parts the app changes, which discs it reads and the known limits of version 1.0.

## How to use this archive

  To learn the editor through practical exercises, start with [Modding Path of Radiance](modding/index.md). Its illustrated tutorials explain what to open, what to change, how to save, and how to check the result, from your first project through a three-chapter campaign.

  Begin with the player-facing system you want to understand, follow its links down to the formats that supply data, then return through related-system links to see where those values are consumed. Use the format index instead when starting from an unknown file.

## File formats

## Game systems

!!! warning "Scope"
    Offsets and record sizes in this archive target the **US release of Path of Radiance** unless a page says otherwise. Radiant Dawn shares the engine, but most of its record layouts changed: they are collected on [Radiant Dawn](./meta/radiant-dawn.md) and its own format pages. The tutorials use Path of Radiance and say where Radiant Dawn differs.

## Explore the archive

- [See what you can edit in each game](meta/what-you-can-edit.md)
- [Follow the illustrated modding tutorials](modding/index.md)
- [Browse file formats](meta/format-coverage.md)
- [Browse game systems](systems/chapters.md)
- [Follow a learning path](guides/learning-paths.md)
- [See every topic and its status](meta/topic-registry.md)
- [Inventory every engine and gameplay system](meta/game-systems-inventory.md)
- [Review system documentation coverage](meta/system-review.md)
- [Plan the uncovered-system articles](meta/uncovered-systems-roadmap.md)

