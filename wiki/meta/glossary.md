---
id: "glossary"
title: "Glossary"
description: "Plain-language definitions for identifiers, containers, scripts, and runtime concepts used throughout the archive"
games: ["path-of-radiance", "radiant-dawn"]
section: "meta"
article_type: "reference"
tags: ["Portal", "Reference", "Terminology"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "meta"
source_path: "meta/glossary.md"
---
# Glossary

These are the terms most likely to block a new reader. File-format articles may give a narrower definition when a term has a special meaning in that format.

## Identifiers

**PID**
: A character identifier, such as `PID_IKE`. It names the character definition, not necessarily a living unit currently loaded on a map.

**JID**
: A class or job identifier. A runtime unit combines character data with a class and mutable progression.

**IID**
: An item identifier. Individual inventory instances also carry mutable information such as remaining uses or forge data.

**MID, SID, AID, EID and RID**
: Common prefixes for message, skill, animation, effect, and resource identifiers. Treat the prefix as a namespace hint, not as part of the binary format itself.

## Files and containers

**Archive**
: A file that contains other named files or resources. In this project, “the Archive” with a capital A means this documentation site.

**CMP**
: A conventional `.cmp` filename. It normally means an LZ10-compressed payload, often a pack archive after decompression.

**CMB**
: Compiled event-script bytecode. TelliusModding can represent supported scripts as readable `.fe9s` source.

**Pointer**
: A stored value that refers to another location. Some Tellius formats store offsets relative to a header rather than absolute memory addresses.

**Relocation table**
: A list of locations that contain pointers. If records or strings move, both their pointers and the relocation entries may need rebuilding.

**String pool**
: A shared region containing labels or text referenced by pointer, avoiding repeated copies of the same string.

## Runtime and project concepts

**Runtime unit**
: The mutable actor currently used by the game. It combines character, class, deployment, inventory, skills, and saved progression.

**Extracted project**
: A TelliusModding workspace created from a user-supplied game disc. It contains editable extracted files and project metadata; game files are never distributed with the application.

**Originals**
: The project's preserved copies of files before their first edit. Restore operations use these copies.

**Confirmed / Strong evidence / Plausible / Open question**
: Claim-level evidence labels. They describe how well a specific statement is supported, not the reliability of an entire article.

## See also

- [Documentation Conventions](sources.md)
- [Every topic and its status](topic-registry.md)
- [Learning paths](../guides/learning-paths.md)
