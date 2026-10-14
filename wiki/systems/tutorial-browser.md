---
id: "tutorial-browser"
title: "Tutorial Popups & Guide Browser"
description: "How tutorial topics unlock, interrupt play, group into the Guide, render pages, and persist"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure", "UI", "Tutorials"]
aliases: ["tellius_archive.html#/tutorial-browser"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "path-of-radiance-us-manual"]
cms_collection: "systems"
source_path: "systems/tutorial-browser.md"
system_entries: ["FE9-SYS-343", "FE9-SYS-344"]
system_reviewed: ["FE9-SYS-343", "FE9-SYS-344"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Tutorial Popups & Guide Browser

FE9 teaches through two related surfaces. A tutorial popup interrupts the current scene when an authored condition requests a lesson; the Guide browser later exposes unlocked topics as a grouped reference list. Both consume tutorial data and persistent availability, but only the popup participates in live event/action flow.

## Mental model and worked example

Think of each lesson as content plus state. Content defines its category, labels, pages, and presentation. State says whether the topic is available and whether a one-time popup has already been handled. Triggering a lesson should not copy its pages into the save; browsing it should not replay the gameplay event that originally unlocked it.

For example, a chapter event can request a combat lesson before the player acts. If allowed, the popup takes modal focus, renders its pages, waits for navigation/close, marks the appropriate seen/unlocked state, then restores the map event at the same continuation. Later the Guide enumerates the same topic under its category from persistent availability. Closing the Guide changes no tactical state.

## FE9-SYS-343 — Tutorial popup system

<span id="fe9-sys-343"></span> A popup request supplies or resolves a topic from script/scene context. Eligibility checks tutorial settings, difficulty/chapter state, unlocked/seen facts, and whether another modal or non-interruptible process owns focus. Accepted requests suspend the parent, build the tutorial page presenter, give it input, and wait for one completion result.

Completion can record availability/seen state and must restore parent focus, input, audio/presentation, and event/action continuation. Repeated or suppressed requests must take an explicit path—ignore, queue, or reopen—without double-advancing the VM. Debug unlock-all changes availability for testing; it does not prove which retail trigger normally grants a topic.

Trigger priority is therefore caller/focus ownership, not a global topic scheduler: an authored script requests one topic, the current modal-safety and option/difficulty checks either create one child or return a suppressed result, and the seen/unlocked masks decide subsequent one-time versus browser access. Close/skip writes only the accepted topic state, releases the child, and resumes the exact waiting action/event once. Reload reconstructs availability from saved masks rather than a suspended popup process.

## FE9-SYS-344 — Tutorial and Guide browser

<span id="fe9-sys-344"></span> The Guide is initialized from four named sections: `TUT_CHAPTER`, `TUT_CATEGORY`, `TUT_INITIAL`, and `TUT_DATA`. `TUT_DATA` begins with a count followed by 24-byte records. Each record stores topic ID at `+0`, category key at `+1`, chapter key at `+2`, display-order byte at `+3`, initial-selection key at `+4`, four per-difficulty start-flag bytes at `+5..+8` (Normal, Hard, Maniac, Easy), title-message pointer at `+0x0C`, script pointer at `+0x10`, and function pointer at `+0x14`. Category/chapter/initial group builders use keys starting at 1, and the visible records are merge-sorted by the display-order byte.

The browser filters by persistent availability rather than chapter scripts currently loaded. During new-game party initialization, each topic's byte for the selected difficulty seeds two independent masks: bit 1 grants its topic ID in the unlocked mask at party offset `+0x74`, while bit 0 grants it in the learned mask at `+0x84`. Runtime state then groups visible records, owns category/topic cursor and scroll state, and invokes the selected record's content pointers. A topic record is therefore content plus grouping/default metadata, not by itself a guarantee of visibility.

## Rules and lifecycle

For popups:

1. A script or scene requests a topic.
2. Eligibility checks context, settings, availability/seen state, and modal safety.
3. The parent suspends input/progression and creates the page presenter.
4. The presenter resolves text/images and handles page navigation.
5. Close/skip reaches one completion result and updates only the intended tutorial state.
6. Resources and modal focus are released; the parent resumes exactly once.

For the Guide:

1. Load and validate the four named sections and topic count.
2. Join records to category/chapter/initial labels and persistent availability.
3. Build deterministic groups and the visible topic list.
4. Restore a valid cursor/page or choose a legal initial entry.
5. Render pages while list/category focus is suspended.
6. Unwind to the list or exit without mutating gameplay.

Malformed counts, bad label references, empty categories, missing page messages/images, unavailable initial entries, and a list that changes while open need safe fallbacks. Cursor identity should follow the topic, not a stale row index after filtering.

## Inputs, outputs, and implementation trail

Inputs include tutorial table sections, message/image resources, script/scene requests, chapter/difficulty/options context, persistent unlocked/seen state, and controller focus. Outputs are modal completion, saved tutorial facts, and the Guide's rendered/grouped UI. They do not include gameplay rewards or objective changes unless the surrounding event separately performs them.

The trail starts at tutorial script/native calls and the `TUT_*` section loader, follows record parsing into runtime groups, then traces popup/browser menu processes, resource lookup, focus/input, state writes, save serialization, completion, and teardown. Controlled tests should request the same topic before/after seen, under different tutorial settings/difficulties, during a blocked scene, after reload, and through debug unlock-all.

The systems interact with [Events & Scripting](./events-scripting.md), [Input, Menus & Options](./input-menus-and-options.md), [Graphics & Images](./graphics-system.md), [Dialogue & Message Presentation](./dialogue-engine.md), and [Save System](./save-system.md).

## Interactions and limits

Both tutorial systems are reviewed without a blocking research gap. FE9-SYS-343 is closed at the request/eligibility/modal-child/state-write/resume boundary; individual retail trigger sites are authored content. FE9-SYS-344 is closed by the complete `TUT_DATA` row, difficulty-seeded masks, group keys, and display-order sort. Popup and browser share topic data and persistence, so no new primary article is needed.
