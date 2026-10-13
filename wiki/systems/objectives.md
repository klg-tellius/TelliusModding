---
id: "objectives"
title: "Objectives"
description: "How a chapter knows it's been won or lost"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure"]
aliases: ["tellius_archive.html#/objectives"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/objectives.md"
---
# Objectives

*How a chapter knows it's been won or lost*

Two layers combine to decide when a chapter ends and how: a pair of engine-level flags that actually end the chapter, and a per-chapter set of invisible marker objects that describe what condition the chapter is built around.

## How an objective becomes completion

  Map data describes objective-related locations or markers, gameplay changes unit and map state, script triggers test the relevant condition, and the successful event sets `gf_complete` or `gf_gameover`. The flag—not the marker or displayed objective text—is the final chapter-ending signal.

## The flags that end a chapter

  [Event script](../formats/event-script.md) functions can be one of two specific trigger types whose sole parameter resolves, with zero exceptions across every real script checked, to one of two literal engine flags: `gf_complete` (the chapter is won) and `gf_gameover` (the chapter is lost). Setting one of these is the actual mechanism that ends a chapter — everything else in a chapter's script exists to decide *when* to do that.

## Battle-goal markers

  Separately, a chapter's own [map data](./map-objects.md) can include invisible, non-rendering objects carrying a confirmed 3-bit "battle goal" type field. These markers are consistently named after their own condition — recognizable real objective types recur across dozens of chapters sharing the same bit pattern, with names like `defense_01`, `attainment_01`, `secession_01`, and `visit_01` turning up on markers using exactly that objective's own type value. This is a real, structurally confirmed 3-bit enum — not a guess from a single chapter's data — though the exact player-facing meaning of each of its 8 possible values isn't independently confirmed beyond what the marker's own name implies. <span class="confidence confidence--strong">strong evidence</span>

## Objective text

  The goal and defeat lines shown to the player come from the chapter's record in [FE8Data.bin](../formats/fe8data.md): four text slots (the goal, an unused slot, the defeat condition and a second goal line), with separate goal texts for Hard and Maniac where they differ — a longer turn limit, for instance. Easy uses the Normal texts. <span class="confidence confidence--confirmed">engine</span>

## Trial map grades

  A trial map is graded A to E on three counts, each against four limits stored in its chapter record: the turns taken, the units lost, and the enemies killed. Each unit counts its kills on the current map (reset when it is deployed); the game sums them over the player's army, and more kills give a better grade. The final grade averages the three. <span class="confidence confidence--confirmed">engine</span>

## How they connect

  A chapter's script is what actually reads the game state and fires `gf_complete`/`gf_gameover` — commonly gated by [turn/phase triggers](./events-scripting.md) (a defend-for-N-turns condition) or by a specific unit's state (a rout condition, checked per-enemy). The precise script-level check that reads a battle-goal marker's own state, connecting the marker to the flag it presumably drives, has not itself been isolated — the marker's role is inferred from its name and its consistent recurrence, not from tracing the exact code path that consumes it. <span class="confidence confidence--open">open</span>
