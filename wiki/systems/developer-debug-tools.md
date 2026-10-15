---
id: "developer-debug-tools"
title: "Developer & Debug Tools"
description: "A full set of internal testing menus and helpers, built into the shipped disc but never reachable through normal play"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure"]
aliases: ["tellius_archive.html#/developer-debug-tools"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/developer-debug-tools.md"
system_entries: ["FE9-SYS-014", "FE9-SYS-371", "FE9-SYS-372", "FE9-SYS-373", "FE9-SYS-374", "FE9-SYS-375", "FE9-SYS-376"]
system_reviewed: ["FE9-SYS-371", "FE9-SYS-372", "FE9-SYS-373", "FE9-SYS-374", "FE9-SYS-376"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Developer & Debug Tools

<span id="fe9-sys-014"></span> **FE9-SYS-014 — Crash, assertion, and debug output.** Retail code retains diagnostic strings, assertions, timestamps, author metadata, and console logging used to identify failed loads, invalid state, and development provenance. These diagnostics are evidence about the failing subsystem, not instructions to ignore validation: a missing resource, bad section, impossible script state, or failed platform operation should be traced back to its caller and inputs. Exact output destinations and which assertions remain active depend on build and runtime environment.

*A full set of internal testing menus and helpers, built into the shipped disc but never reachable through normal play*

The shipped disc's executable retains a substantial internal testing and debugging layer that ordinary play never reaches: three complete developer-menu trees, plus a scattering of standalone debug helpers wired into normal systems like the tactical map and the portrait renderer. None of this is corrupted or vestigial code — every piece described here is complete, functional, and would run correctly if invoked.

## Three named root menus

  Three separate top-level debug menus exist as complete, working menu trees, each built and registered when the game starts up rather than assembled on demand:

<div class="table-wrap">
<table><thead><tr><th>Menu</th><th>Covers</th></tr></thead><tbody>
    <tr><td>First root menu</td><td>The largest of the three, covering six full categories — System, Game state, Event, Visualize, Display, and Sound testing — plus memory-card file operations. Fully mapped; see below.</td></tr>
    <tr><td>Second root menu</td><td>Base/storage and tutorial-system testing: filling the party's shared storage with a stock item, testing the base-visit flow and its pre-visit report screen, forcing a specific reinforcement group, unlocking every tutorial message in the game at once, and a small text-rendering test tool (see below)</td></tr>
    <tr><td>Third root menu</td><td>Dialog-system testing: standalone two-option and three-option dialog boxes, a location-name display test, a tutorial-dialog test, and a flag that force-enables every "extra" scenario flag at once</td></tr>
  </tbody></table>
</div>

## One shared list, viewed through different windows

  The first menu's six categories are not six independent lists of entries. Underneath, a single flat list of menu records exists once; each category — and several sub-menus one level deeper, such as opening a specific unit's stat editor — simply points at a different starting position and length within that same list, the same way scrolling a long list to different starting points shows different but overlapping windows onto it. Two categories can genuinely show some of the exact same rows. This is confirmed directly: the row shown for "Game settings," for instance, does not lead to any settings of its own — it opens the same window that happens to also contain the entire System category underneath it.

## The first menu's six categories

<div class="table-wrap">
<table><thead><tr><th>Category</th><th>Real content</th></tr></thead><tbody>
    <tr><td>System</td><td>A memory-usage report, an event/chapter turn-boundary log dump, a support-pair ("Bond") list dump, a full army-roster dump, a convoy-reset action, a tool that identifies whatever building sits under the debug cursor and opens a submenu for it, a toggle for the game's Random-vs-Fixed growth-mode setting, and a counter tied to a multiple-playthrough/postgame-content slot list</td></tr>
    <tr><td>Game</td><td>Live status readouts (chapter, turn count, gold, a separate "event points" counter, difficulty rank), a convoy-size readout, a building-status readout, and the entry point into the per-unit stat editor described below</td></tr>
    <tr><td>Event</td><td>A skill/flag browser that can grant or remove any of the game's skills and status flags on the selected unit; a two-axis tool that warps the selected unit to any tile by resolving the destination tile object directly; and an editor for a small per-unit flag array tied to event conditions</td></tr>
    <tr><td>Visualize</td><td>A paginated map-marker toggle tool, 16 markers per page, with a real page-index/page-count display — this is the one category confirmed to have its own genuine scrolling state rather than just reusing another category's window</td></tr>
    <tr><td>Display</td><td>Ten independent on/off overlay toggles for renderer debug views: a process-tree view, a performance readout, a 2D-primitive overlay, a GPU performance readout, an in-game debug-info overlay, a broadcast-safe-area guide frame, a sound-test overlay, a "battle off" toggle, a visualizer for scenes where skipping is disallowed, plus toggles for the camera implementation, a debug console overlay, and a guide-window overlay</td></tr>
  </tbody></table>
</div>

## A complete per-unit stat editor

  Selecting a unit from the Game category opens a real, fully wired stat editor for that unit, reachable through several differently-labeled rows that all converge on the same tool: it directly reads and writes level (1&ndash;20), experience (0&ndash;99), transformation gauge, several other capped byte fields, and one unclamped field that changes every turn (see [Biorhythm](./biorhythm.md)). A separate row computes each stat's remaining "growth doping" headroom by comparing the unit's current stat against a stored cap. Another row is a genuine support-rank editor, raising or lowering the stored rank between the selected unit and a chosen partner. A further, unlabeled row cycles a small per-unit state value through three settings — its exact effect (most likely a deployment or roster status) is not confirmed.

## A working battle previewer

  A separate development menu entry starts a full battle previewer: a self-contained process that can display attacker/defender/support combat roles, actions, outcomes, and skill/effect names outside of an actual battle sequence — evidently built as a tool for checking combat presentation without having to trigger a real battle.

## Testing text width

  The second root menu's small text-rendering test tool displays the same short sentence three times, each with one word drawn at a different width (`#X3A` squeezed, `#X46` stretched, and unchanged) — a test of the horizontal text scale described in [the dialogue format](../formats/message-format.md). Selecting any of the three rows only displays the sample text; none of them has any further effect.

## Standalone debug helpers outside the menu system

  Beyond the three menu trees, several debug-only helpers are wired directly into normal gameplay systems:

- A tactical-map debug input handler that can select units, center the camera, and mark/unmark enemies on demand — reading the same debug-input state the menus use, but hooked directly into the ordinary map-input loop rather than gated behind a menu.
- A parallel debug harness built into the portrait rendering system, capable of spawning and stepping through a portrait's fade, slide, and zoom animations independently of any actual dialogue scene calling for them.
- A function that dumps the complete contents of every [army list](./armies-allegiance.md) at once — every unit's slot, position, state, and name, grouped by army — clearly meant as a debugging aid for the allegiance system rather than anything a player would ever see.
- Script-level calls that can directly read or write a unit's fields and push/pop entire unit rosters, exposed the same way ordinary script commands are, but intended for test scripts rather than chapter content.

## Why they stay hidden

  Two separate, dormant switches keep the menus out of normal play, and neither is a missing piece of code. The map pause menu walks a zero-terminated list of root menus; the list holds the ordinary pause menu first and then a zero, so the walk stops before it reaches the four developer roots stored behind it. Moving the roots in front of the zero shows all of them. Separately, the start-up process that launches the game controller runs the production title screen, while a complete development title screen (build information, memory-card import and export, the battle previewer, chapter and difficulty selection, and a "Production version" entry that continues to the normal file menu) sits in the executable with nothing pointing at it. <span class="confidence confidence--confirmed">engine</span>

## Example — starting a chapter directly

  The development title's chapter select hands each of its rows to one routine, which is all it takes to start any chapter. The row is a small menu record whose byte `+4` is a position in the [chapter table](./chapters.md) (`ChapterData`), not a chapter number; a position below 0 or past the last record finds nothing. The routine then: <span class="confidence confidence--confirmed">engine + in game</span>

1. resets the whole party as for a new game, with no units and a random game id from 1 to 30 (the same range a trial map uses);
2. keeps the difficulty byte (`0x803307AE` on the US disc: 0 Normal, 1 Hard, 2 Maniac, 3 Easy) as it was;
3. sets the current chapter number to that record's id;
4. tells the game controller to run its chapter-start step next, the same step a won chapter or a loaded save leads to.

  The chapter then loads and plays from its opening. Only the units the chapter itself deploys or recruits are present, since the army is empty. Any record in the table can be started this way, including records added after the retail ones. In the controller's process script, the title screen is one instruction of the boot step (US `0x802833E4`, a "start and wait" on the title script), and the file menu that follows is one call; the routine's effect survives as long as the file menu is not opened over it. After a game over, the controller goes back to its title step.

## Overlay switches

  The Display category's overlays are plain flag bytes read by the main loop every frame: process tree, performance meter, GPU performance meter, in-game debug information, safe-frame guide, sound-test overlay, 2D-primitive overlay, battle-display off and skip-block visualisation. They start at zero and nothing but the menu sets them. <span class="confidence confidence--confirmed">engine</span>

  None of the labels that resemble item, skill, weapon-rank, or status-condition list viewers lead to such a viewer in this build. The complete registered root/menu records instead route those fields through the shared per-unit editor, while `Glossary` and `Test` return an inert menu code. Unlabelled byte fields remain editor-data questions, not evidence of another resource-viewer system.

## FE9-SYS-371 through FE9-SYS-376 — Review boundaries

<span id="fe9-sys-371"></span> **Developer/debug menus.** The executable builds three root trees over shared record windows, complete callbacks, submenus, editors, toggles, and test dialogs. Dormant pause-menu and development-title routing—not missing implementations—keep them out of production play.

<span id="fe9-sys-372"></span> **Internal battle tool.** The battle previewer constructs attacker, defender, support roles, actions, outcomes, skill/effect names, and full battle presentation outside campaign encounter flow. It is a presentation/test harness, not an alternate authoritative campaign combat system.

<span id="fe9-sys-373"></span> **Chapter jump/test flow.** Development title selection indexes `ChapterData`, resets party state, preserves difficulty, assigns the chapter ID, and routes the ordinary controller to chapter start. Bounds and file-menu overwrite hazards are documented above.

<span id="fe9-sys-374"></span> **Resource viewers and harnesses.** The three registered root trees plus standalone hooks cover map markers/overlays, portraits, battle presentation, text width, process/GPU performance, rosters, memory, safe-frame/console/guide views, and scene debug state. Apparent item/skill/rank/status list labels route to field editors or inert callbacks; they do not identify missing viewer implementations in the retail executable.

<span id="fe9-sys-375"></span> **Logging and assertions.** Diagnostic strings and call sites prove logging/assertion infrastructure, but severity, sinks, retail activation, recovery, and representative failure paths are not catalogued. This remains revision-required together with FE9-SYS-014.

<span id="fe9-sys-376"></span> **Build timestamps and author metadata.** Executable/resource provenance strings preserve build dates, tool/author names, and diagnostic context. They are evidence for distinguishing builds and pipelines, not runtime gameplay settings.

## Rules and lifecycle — access and execution

Boot registers menu records and callbacks. A dormant root or development-title path must be made reachable, after which the ordinary menu framework owns focus and invokes the selected helper. Helpers read or mutate live state directly, display results, and return to their parent; chapter jump instead resets and hands off to the production controller. Tools that change units, flags, convoy, or support rank can affect later saves, so testing must isolate state rather than treating every menu as read-only.

## Interactions and limits

FE9-SYS-371–374 and FE9-SYS-376 are reviewed without blocking gaps. The full registered-menu census and standalone hooks close FE9-SYS-374; absent or inert labels are explicitly classified rather than assumed to hide tools. FE9-SYS-375 remains reviewed with gaps in [Crash, Assertions & Diagnostic Output](./crash-assertions-diagnostics.md), its primary article. This page remains the owner of interactive tools.
