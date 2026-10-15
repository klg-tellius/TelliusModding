---
id: "extras-and-unlocks"
title: "Extras, Unlocks & GBA Link"
description: "How clear data unlocks trial maps, theaters, galleries, records, linked rewards, and post-clear options"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Unlocks", "Extras", "Records"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "path-of-radiance-us-manual"]
cms_collection: "systems"
source_path: "systems/extras-and-unlocks.md"
system_entries: ["FE9-SYS-360", "FE9-SYS-361", "FE9-SYS-362", "FE9-SYS-363", "FE9-SYS-364", "FE9-SYS-365", "FE9-SYS-366", "FE9-SYS-367", "FE9-SYS-368", "FE9-SYS-369", "FE9-SYS-370"]
system_reviewed: ["FE9-SYS-360", "FE9-SYS-361", "FE9-SYS-362", "FE9-SYS-363", "FE9-SYS-364", "FE9-SYS-365", "FE9-SYS-366", "FE9-SYS-367", "FE9-SYS-368", "FE9-SYS-369", "FE9-SYS-370"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Extras, Unlocks & GBA Link

Extras are driven primarily by console-wide system data replicated into save blocks, so rewards and availability can outlive the playthrough that earned them. Individual viewers remain consumers: opening a gallery or Records page should not invent a clear, meeting, or reward.

## Mental model and worked example

Think of system data as an account-wide ledger and each campaign as a run ledger. Completing a run writes eligible facts into the system ledger; Extras menus filter content using those facts; starting another game reads allowed account facts while reinitializing campaign state.

For example, completing a harder difficulty can set a clear/unlock bit and append a completed-run identity. The next title session exposes Extras and an additional Trial Map or post-clear choice. Deleting one campaign file should not necessarily erase a console-wide unlock already merged into system data. Replaying a movie changes neither ledger.

## FE9-SYS-360 and FE9-SYS-361 — Clear data and playthroughs

<span id="fe9-sys-360"></span> **Clear/unlock flags.** Completion writes bits representing a finished game and difficulty-dependent access. Normal/Easy establishes the base clear state; higher difficulties can add bits. System data is replicated with saves so title/Extras/new-game consumers can recover it, with a defined merge priority needed when copies disagree.

<span id="fe9-sys-361"></span> **Playthrough number.** System data retains identifiers/count for runs that reached the ending; count plus one supplies the next displayed playthrough number. The value is a completion record, not the current chapter counter.

## FE9-SYS-362 and FE9-SYS-363 — Trial Maps and Extras hub

<span id="fe9-sys-362"></span> **Trial Map unlocks.** Clear/difficulty state gates the six Trial Map chapter records. Launch uses a separate trial route and resume identity, constructs an appropriate party context, preserves relevant options/difficulty, evaluates trial grading inputs, and returns to Extras without advancing the story campaign.

<span id="fe9-sys-363"></span> **Extras hub.** The title exposes Extras from persistent system unlock state, then the hub enumerates Trial Maps, Movie Theater, Gallery, Records, and GBA-link child surfaces in its authored menu order. Availability filters rows before focus is assigned; an unavailable feature is absent/disabled according to its entry callback rather than launched optimistically. The hub preserves a valid row identity, suspends while one child owns input, and rebuilds the list from current unlock state when that child returns.

## FE9-SYS-364 and FE9-SYS-365 — Theater and gallery

<span id="fe9-sys-364"></span> **Movie Theater.** Its authored records join unlock/seen facts to a label and literal THP resource identity; table order supplies deterministic display order. Selection delegates full-screen/audio/input ownership to the common THP player. Normal end, skip, or failed media open returns one child result and restores the theater list without replaying story scripts or granting campaign effects. Regional names/assets are content-table variants, not a second theater lifecycle.

<span id="fe9-sys-365"></span> **Illustration/character gallery.** Authored gallery records consume clear/unlock and normalized character-met facts, then resolve illustration, portrait, or ending resources in table order. The viewer owns list/detail focus, navigation, zoom, variant selection, and teardown but never writes eligibility. Missing optional art yields an unavailable/failed detail and returns to the list; merely placing an asset on disc cannot unlock it.

## FE9-SYS-366 — Records viewer

<span id="fe9-sys-366"></span> Records reads completion flags, playthrough identity, chapter-clear history, roster/survival/met facts, and per-unit statistics. Stored facts and display-derived values must be distinguished. The viewer is read-only and must handle empty, capped, multi-part, trial, dead/absent, and overflow states safely.

## FE9-SYS-367 and FE9-SYS-368 — GBA link

<span id="fe9-sys-367"></span> **Link protocol.** The connection flow acquires the GameCube serial interface, detects/handshakes with a supported GBA title/save, exchanges and verifies data, handles timeout/retry/cancel/disconnect, and releases the port/UI transaction. No reward commits before verification.

<span id="fe9-sys-368"></span> **Link rewards.** A verified result is mapped to specific persistent rewards/unlocks and saved atomically. Repeating the same valid transfer must follow explicit duplicate/idempotence rules; a failed save or full destination must not mark a reward delivered when it was not.

## FE9-SYS-369 — Character-met tracking

<span id="fe9-sys-369"></span> Character-met state records campaign encounters or qualifying recruitment for gallery/Records/ending consumers. It is separate from the current living roster: a character can be met and later die, retreat, or depart. Alternate forms/PIDs and duplicate appearances require normalization to the intended gallery identity.

## FE9-SYS-370 — New Game after clear

<span id="fe9-sys-370"></span> A post-clear new-game route consumes clear, difficulty, playthrough, and unlock state to offer eligible choices. Confirmation enters ordinary campaign initialization with selected modifiers, inherits only intended system facts, and resets party/chapter/runtime state. Cancel returns to title without incrementing a run or creating a partial save.

## Rules and lifecycle

1. Gameplay/link/ending code produces a candidate fact or reward.
2. Eligibility and duplication rules validate it.
3. The correct run-level or system-level owner commits it atomically.
4. Save/system replication preserves or merges the state.
5. Title/Extras enumerates entries from current authoritative unlock state.
6. A child viewer/launcher consumes the state and returns a result.
7. The hub refreshes without rewriting unrelated unlocks.

Copy/delete/corrupt save operations, multiple completed files, regional data, full rewards, interrupted link transfers, and repeated clears are the critical merge/idempotence edges. Editors should preserve unknown bits and never infer unlocked content from assets alone.

## Implementation trail and interactions

Trace ending completion into system/save fields, then follow title/Extras menu gates and each child list. For Trial Maps follow special campaign entry/resume/return. For GBA link follow serial acquisition through verified reply, reward commit, save, and cleanup. For viewers map every row to its stored or derived source.

These systems interact with [Endgame & Ending Cards](./endings.md), [Campaign Flow](./campaign-flow.md), [Save System](./save-system.md), [Battle Reports & Performance Records](./battle-reports-records.md), [THP Video Playback](./video-system.md), and [Input, Menus & Options](./input-menus-and-options.md).

## Interactions and review boundary

All eleven Extras systems are reviewed without a blocking research gap. Clear/playthrough facts, Trial routing, hub/viewers, Records, verified link transaction/reward commit, normalized character-met state, and post-clear New Game inheritance/reset form one system-data-to-consumer lifecycle. Regional tables, individual unlock bits, reward rows, and viewer ordering remain versioned content data rather than missing ownership or transaction rules. No new primary article is needed.
