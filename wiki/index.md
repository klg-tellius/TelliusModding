---
id: "main"
title: "Main Page"
description: "A field reference to how Fire Emblem: Path of Radiance stores itself"
games: ["path-of-radiance","radiant-dawn"]
section: "meta"
article_type: "portal"
tags: ["Portal"]
aliases: ["tellius_archive.html#/main"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "pages"
source_path: "index.md"
---
# Main Page

*A field reference to how Fire Emblem: Path of Radiance stores itself*

The **Tellius Archive** documents, at the byte level, how *Fire Emblem: Path of Radiance* (GameCube, 2005) stores its data and how the systems built from that data work: how a chapter script decides when a cutscene plays, how a class's promotion bonus is computed, and how a battle animation is selected for a given weapon.

  Two kinds of article make up the archive. **File format** articles describe a container or record layout byte-for-byte — offsets, field widths, what a pointer resolves to. **Game system** articles describe a mechanic in play — classes, skills, chapters, music — and link back down to whichever files implement it. Most systems draw on more than one format at once; most formats serve more than one system.

  Start with [Disc & File Layout](./meta/disc-layout.md) for a tour of the extracted game, [File Format Index](./meta/format-coverage.md) for a completeness-oriented catalog, or [Documentation Conventions](./meta/sources.md) for identifiers, offsets, and confidence labels.

## How to use this archive

  Begin with the player-facing system you want to understand, follow its links down to the formats that supply data, then return through related-system links to see where those values are consumed. Use the format index instead when starting from an unknown file.

## File formats

## Game systems

!!! warning "Scope"
    Offsets and record sizes in this archive target the **US release of Path of Radiance**. Radiant Dawn shares the engine, but its layouts and mechanics require separate documentation: what is known so far is collected on [Radiant Dawn](./meta/radiant-dawn.md).

## Explore the archive

- [Browse file formats](meta/format-coverage.md)
- [Browse game systems](systems/chapters.md)
- [Follow a learning path](guides/learning-paths.md)
- [See every topic and its status](meta/topic-registry.md)

