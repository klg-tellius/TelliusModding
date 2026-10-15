---
id: "input-menus-and-options"
title: "Input, Menus & Options"
description: "How controller state becomes focused menu actions, lists, options, dialogs, file selection, and pause flow"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["UI", "Input", "Options"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "path-of-radiance-us-manual"]
cms_collection: "systems"
source_path: "systems/input-menus-and-options.md"
system_entries: ["FE9-SYS-333", "FE9-SYS-334", "FE9-SYS-335", "FE9-SYS-336", "FE9-SYS-341", "FE9-SYS-345", "FE9-SYS-346", "FE9-SYS-347", "FE9-SYS-348"]
system_reviewed: ["FE9-SYS-333", "FE9-SYS-334", "FE9-SYS-335", "FE9-SYS-336", "FE9-SYS-341", "FE9-SYS-345", "FE9-SYS-346", "FE9-SYS-347", "FE9-SYS-348"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Input, Menus & Options

Input passes through layers: the controller decoder creates button/stick state, focus routes it to one active widget or scene, and that owner requests a game action. A pressed A button has no universal meaning without context, and a menu preview is not authority to mutate gameplay until confirmation commits it.

## Mental model and worked example

Think of UI as a stack of focused transactions. The map owns input; opening Pause gives focus to a menu; choosing Suspend gives focus to a confirmation dialog; confirming gives focus to save/card progress; completion either exits or unwinds to the map. Each child returns one result and restores the parent exactly once.

If the memory card reports an error, the dialog must not leave both itself and the Pause menu responding to the same button. Retry continues the suspended transaction, Cancel unwinds without creating a suspend record, and returning to the map restores its prior focus/camera rather than interpreting the cancel press as another command.

## FE9-SYS-333 and FE9-SYS-334 — Controller and focus

<span id="fe9-sys-333"></span> **Controller mapping.** The GameCube PAD callback receives `PADStatus`, rejects error/disconnect state before dispatch, calibrates stick/substick origins, and clamps signed stick and unsigned trigger ranges. Analog L/R values at or above 170 also set their digital button bits. The focused context then maps normalized state to cursor/select, cancel, unit cycle, status, zoom/camera, display hiding, message acceleration, or skip.

<span id="fe9-sys-334"></span> **Input focus and repeat.** Input state distinguishes edge-triggered presses from held controls; list and continuous widgets translate a sustained direction into delayed, frame-based repeats. Only the top focused process consumes that state: modal dialogs outrank parents and scripted scenes can lock ordinary input. Closing a child restores parent focus and cursor memory after the closing edge has been consumed, preventing the same press from firing twice.

## FE9-SYS-335 and FE9-SYS-336 — Title and files

<span id="fe9-sys-335"></span> **Title/main menu.** The production title derives Continue/File availability from validated save data and derives Extras and other conditional entries from system unlock state. It owns title presentation, BGM, focus, transitions, and return from errors, then delegates the chosen route to file, new-game, options, or extras owners. Campaign initialization begins only after that child has a valid selection. The dormant development title remains a separate debug route.

<span id="fe9-sys-336"></span> **File select.** File UI enumerates the save system's validated slot and checkpoint blocks, renders kind/slot/sequence/chapter/play-time metadata, and chooses the newest valid sequence when replicated data compete. It dispatches new/load/copy/delete/format or error flows, with confirmation around destructive choices. Every card mutation returns through success, retry, or cancel and forces a fresh enumeration, so removal, corruption, capacity, or write-protection errors cannot leave stale rows selectable.

## FE9-SYS-341 — Lists and sorting

<span id="fe9-sys-341"></span> A reusable list enumerates rows from an owner, filters eligibility, optionally sorts with a context comparator, stores cursor/scroll/page state, draws visible rows, and returns a selection. Refresh after mutation must preserve identity where possible rather than blindly reuse an invalid numeric index.

Empty lists require an explicit unavailable/empty state. Sorting compares configured keys while preserving original enumeration order for equal results, giving stable identity and deterministic display. Page/wrap rules and remembered sorting can differ by unit, item, skill, shop, tutorial, or records context; the shared lifecycle does not imply one universal comparator.

## FE9-SYS-345 and FE9-SYS-346 — Options and calibration

<span id="fe9-sys-345"></span> **Options.** The party record stores twelve option bytes beginning at `party_data+0x9C`; the option table maps each row to its byte and allowed choices, including Unit Facing and Bonus Exp Display. Defaults include unit speed `0x14`, brightness `0x40`, zero screen X/Y offsets, and music/effect volumes of 100. A row may preview immediately, but confirm/apply and save ownership determine persistence; Cancel restores the prior effective value.

<span id="fe9-sys-346"></span> **Screen calibration.** Calibration edits signed screen X/Y offsets and the brightness byte with a live rendering preview. Accepted values are mirrored in the replicated system-data region beginning at `SYSF+0x40` as well as the active option state; defaults are X 0, Y 0, and brightness `0x40`. Cancel restores the prior bytes. These settings shift presentation only, never tactical coordinates.

## FE9-SYS-347 — Confirmation and error dialogs

<span id="fe9-sys-347"></span> Dialogs are modal result producers. Script commands `Dialog2Items`, `Dialog3Items`, and `Dialog4Items` suspend their caller while the dialog owns focus; `DialogSetDefault` supplies the low-byte initial choice. The answer is returned through a separate signed-byte result read by `DialogResult`, where `-1` means unset. Error dialogs reuse the same ownership for Retry/Cancel or acknowledgement, so nesting cannot overwrite the transaction being answered.

## FE9-SYS-348 — Pause and suspend

<span id="fe9-sys-348"></span> Pause suppresses tactical input and offers commands legal for the current map/scene. Suspend confirmation requests save kind 3 with resume point 8 and records the owning visible slot. Only a successful checkpoint transaction returns to the title route; failure or cancellation returns to the same map context without marking the action complete, advancing phase/events, or leaving a usable suspend record.

Suspend is broader than a menu screenshot: unit, tile, event, and turn state belong to save systems, while pause UI owns focus and presentation. RNG is an explicit exception: neither the gameplay nor visual stream is serialized, so a same-session load continues the current RAM stream and a fresh executable boot reseeds it. Transient processes need a stable freeze/reconstruction rule so audio, camera, range overlays, and pending commands do not duplicate after load.

## Rules, lifecycle, and interactions

The common lifecycle is decode input → resolve active focus → update cursor/repeat → preview → confirm/cancel → delegate the requested operation → receive success/failure → refresh/unwind. Only the delegated owner commits gameplay or persistent data. Every asynchronous operation must keep its parent disabled until one terminal result arrives.

These systems interact with [Save System](./save-system.md), [Tactical Map Interface](./tactical-interface.md), [Graphics & Images](./graphics-system.md), [Extras & Unlocks](./extras-and-unlocks.md), [Music System](./music-system.md), and memory-card/platform services.

## Review boundary

All nine systems are reviewed without a blocking research gap. The SDK decoder, focus ownership, save validation, stable list behavior, option storage/defaults, screen-calibration bytes, dialog result ABI, and Suspend transaction establish the required contracts. Individual menu timing and visual layout remain presentation tuning. These systems share focus, transaction, and restoration machinery, so no new primary article is needed.
