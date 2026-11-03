---
id: "first-mod"
title: "Make your first mod"
description: "A safe route from a user-supplied disc to one tested data change"
games: ["path-of-radiance"]
section: "guides"
article_type: "learning-path"
tags: ["Guide", "Getting started"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["telliusmodding-source"]
cms_collection: "guides"
source_path: "guides/first-mod.md"
---
# Make your first mod

Start with one reversible data edit. This proves extraction, editing, building, and testing before a larger project makes failures difficult to isolate.

## Route

1. Read [Disc & File Layout](../meta/disc-layout.md) to distinguish the disc, extracted files, and generated build.
2. Create a project from your own disc and leave its `originals/` copies intact.
3. Open [Characters](../systems/characters.md) and change one obvious starting value.
4. Build the project and address every validation error.
5. Test a new save in Dolphin; an existing save may retain runtime progression.
6. Restore the original or revert the project change to confirm recovery works.

## Next

Continue with [characters and balance](characters-and-balance.md), then review [documentation conventions](../meta/sources.md) before interpreting an uncertain field.
