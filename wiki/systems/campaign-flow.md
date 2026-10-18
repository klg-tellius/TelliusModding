---
id: "campaign-flow"
title: "New Game & Campaign Flow"
description: "How a new playthrough is initialized and routed through chapters, parts, bases, endings, and trial maps"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Chapters", "Campaign", "Saves"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source", "path-of-radiance-us-manual"]
cms_collection: "systems"
source_path: "systems/campaign-flow.md"
system_entries: ["FE9-SYS-026", "FE9-SYS-027"]
system_reviewed: ["FE9-SYS-026", "FE9-SYS-027"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# New Game & Campaign Flow

The campaign controller answers two deceptively large questions: “what state exists before the Prologue?” and “where does the game go after this scene or map?” It is useful to picture the campaign as a route through scene types rather than a simple numbered chapter list. A normal chapter may pass through story, base, more story, preparation, tactical battle, clear processing, report, save, and transition; multi-part chapters and the ending alter that route.

## New-game initialization

<span id="fe9-sys-026"></span> Starting New Game creates a playthrough inside an existing console-wide save file. System data—screen calibration, clear unlocks, completed-run identifiers, and last-used slot—belongs to the save as a whole. The new block receives party/chapter state, difficulty, options, playthrough number, time counters, flags, empty or initial unit slots, convoy/forge state, and the first resume destination.

Difficulty is not just a label. It selects deployment variants, shop tables, tutorials, battle-EXP constants, and sometimes native behavior. The US release offers Easy, Normal, and Hard; the Japanese release uses Maniac where the US disc uses Easy. Fixed growth mode and some display options are post-clear choices and must be copied into the playthrough state before units begin gaining levels.

Definitions are not duplicated into the save. The block stores character, class, and item table numbers plus mutable progression. When the game constructs the initial party, it resolves those numbers against the boot-loaded core database, applies authored starting state, and creates runtime units. This distinction is why reordering database records can make an old save refer to a different character or item.

Initialization then chooses a resume point and enters the first campaign scene. The Prologue does not use every later facility: base access, convoy availability, reports, shops, and other systems are gated by chapter or flags. A mod that jumps directly to a later chapter must provide the state that earlier chapters would have established or deliberately replace those assumptions.

The new-playthrough constructor owns the empty persistent containers, selected difficulty/options/growth mode, counters, and initial resume identity. The first chapter's `Startup` and difficulty-selected deployment data own creation of the first live roster. This is why roster membership is not a second hard-coded New Game table and why changing difficulty can change deployed actors without changing the save-block constructor.

## Campaign ordering

<span id="fe9-sys-027"></span> Campaign ordering is a state transition, not “current chapter + 1.” Chapter records and native routing identify map resources, while scripts and flags decide which scenes run and which continuation follows. The controller must handle:

- ordinary chapter-to-chapter transitions;
- a base inserted before battle preparation;
- chapters split across several maps or parts;
- checkpoints and preparation saves that resume inside the current chapter;
- scripted promotions or roster changes between maps;
- final chapter, endings, credits, and clear-data creation;
- trial maps that return to Extras instead of advancing the story.

The save makes this visible. After victory, the stored chapter number can already name the next chapter while the map-name field still names the map just cleared. Loading that block starts the next chapter and resets chapter-local flags. A checkpoint or preparation save instead preserves live flags, unit placement/state, and a resume point that re-enters the current chapter.

Ordinary victory advances to the next story identity; `Complete18` keeps the identity and selects part resume points 5–7; the Chapter 27 pair uses its native continuous exception; chapter 32 enters endings/clear recording; and identities 90 and above use resume point 10 and return to Extras. Base, preparation, checkpoint, and post-victory saves use their own resume keys. These routes are the campaign transition table—the per-chapter script decides which named opening exists, while the controller decides how that route is reconstructed.

## Worked example and lifecycle

For a typical midgame chapter, the previous clear transition selects the next chapter and runs its opening story. The controller opens the base if that chapter permits it, runs the base-opening event once, accepts management changes, then proceeds through any prebattle scene. Preparation constructs the map context and accepts deployment. Starting battle initializes the turn/phase loop. Victory schedules postbattle events, awards and records, advances campaign identity, and offers a chapter-clear save. The next load uses the stored resume route, not merely the map filename.

A multi-part chapter can preserve selected party and story state while replacing map, deployment, objective, local events, and camera. The part flag in clear history distinguishes these segments. Treating every part as a fully independent chapter risks resetting data that the original route intended to carry.

## Modding consequences and edge cases

- A new chapter needs a route into it and a route out; having valid map files is insufficient.
- Skipping an initialization scene can leave facilities, roster entries, items, flags, or support availability unset.
- A defeat/retry path must return to the correct story, preparation, checkpoint, or map state.
- Trial maps require a return destination and must not mutate main-campaign ordering accidentally.
- Structural database edits must be tested with both New Game and old saves.
- Chapter-local flags should reset only at a true chapter start, not at every scene or part transition.

## Interactions and review boundary

Both campaign systems are reviewed without a blocking research gap. New Game owns persistent-container initialization and selector state, while the first chapter's `Startup` and difficulty-selected deployment own live roster construction. Normal victory, bases, preparations, checkpoints, `Complete18`, the Chapter 27 pair, endings, and trial identities are distinguished by chapter identity plus resume route rather than a saved program counter. Individual chapter scripts, deployment rows, and initial random seeds are authored inputs, not missing campaign-controller behavior. No new primary article is needed.

