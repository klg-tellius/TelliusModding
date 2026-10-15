---
id: "dialogue-and-scripting"
title: "Dialogue and scripting learning path"
description: "Author dialogue, triggers, movement, cameras, flags, and chapter events"
games: ["path-of-radiance", "radiant-dawn"]
section: "guides"
article_type: "learning-path"
tags: ["Guide", "Scripting", "Text"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["telliusmodding-source"]
cms_collection: "guides"
source_path: "guides/dialogue-and-scripting.md"
---
# Dialogue and scripting learning path

Separate what is said from when and how it appears: messages store presentation commands, while event scripts choose the moment and game state.

## Route

1. [Events & Scripting](../systems/events-scripting.md)
2. [Event Script](../formats/event-script.md) and [Script Functions](../systems/script-functions.md)
3. [Event Flags](../systems/event-flags.md)
4. [Message Format](../formats/message-format.md), [Face Data](../formats/face-data.md), and [Font](../formats/font-format.md)
5. [Cutscenes](../systems/cutscenes.md), [Music](../systems/music-system.md), and camera staging

Use readable `.fe9s` source when possible, keep flag registration order stable, and let validation catch stale message or unit references.
