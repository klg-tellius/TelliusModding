---
id: "dialogue-engine"
title: "Dialogue & Conversation Engine"
description: "How message keys, control codes, layouts, portraits, input, and scene contexts produce conversations"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Dialogue", "Events", "UI"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/dialogue-engine.md"
system_entries: ["FE9-SYS-288", "FE9-SYS-289", "FE9-SYS-290", "FE9-SYS-291", "FE9-SYS-292", "FE9-SYS-293", "FE9-SYS-294", "FE9-SYS-295", "FE9-SYS-296", "FE9-SYS-297"]
system_reviewed: ["FE9-SYS-288", "FE9-SYS-289", "FE9-SYS-290", "FE9-SYS-291", "FE9-SYS-292", "FE9-SYS-293", "FE9-SYS-294", "FE9-SYS-295", "FE9-SYS-296", "FE9-SYS-297"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Dialogue & Conversation Engine

A conversation is not one string. It is a collaboration among an event script, a message resource, a scene context, portrait assets, UI layout, font/glyph data, input, audio, and scheduled timing. The event asks for a message by key; control codes inside that message direct a conversation renderer; when the renderer completes, the script continues.

## Finding and decoding text

<span id="fe9-sys-288"></span> **FE9-SYS-288 — Message lookup and localization.** Chapter dialogue lives in chapter message files while shared menu/help text lives in common resources. Loading a `.m` file registers each exported ID/text pair in the global 509-bucket name table. Lookup uses two rolling hashes (×37 for the bucket and ×31 for equality), not file order or a byte offset; the earlier registered entry wins a collision. No retail IDs collide. Text beginning with `@` can expand numbered substitution slots after resolution.

<span id="fe9-sys-289"></span> **FE9-SYS-289 — Text decoding and control codes.** The text stream mixes CP437/Shift-JIS glyph input with `$` commands for layout, lines/pages, waits, names, colors, portrait seats/expressions, sound, and skip control. Commands consume their own delimited or fixed arguments before glyph decoding resumes. `$SD` disables whole-conversation B-skip and `$SE` re-enables it; portrait commands select up to nine seats and update the active face rather than printing bytes. Unknown or malformed commands are authoring errors, not text to display.

## Rules and lifecycle — building the scene

<span id="fe9-sys-290"></span> **FE9-SYS-290 — Conversation scene system.** `TalkEvent` resolves the message and starts the message-window process (or the map-effect variant when an `E_Talk` handle is active). The scene establishes layout, background, seats, text boxes, camera mode, and resources, then yields the event VM while commands execute. End-of-message, skip, or failure tears down the child and returns one completion result; the renderer owns visible dialogue state while the VM owns story mutations.

<span id="fe9-sys-291"></span> **FE9-SYS-291 — Conversation context and inheritance.** A message can finish while retaining its windows and portraits, allowing the next `TalkEvent` to continue the same context. Explicit commands replace only their component—background, layout, seat, face, expression, or speaker—while untouched components persist. A fresh entry or explicit initial context seeds all required state; isolated previews therefore reconstruct the script path rather than guessing defaults.

<span id="fe9-sys-292"></span> **FE9-SYS-292 — Portrait selection and animation.** `FID_` identity selects one of the 358 face-data records and its shared-palette portrait images; seat records provide signed center/bottom coordinates and facing. Eye commands choose defined open/half/closed states, mouth/eye pieces use face metadata, and portrait fades take eight frames. Missing optional pieces leave that layer absent; a missing required face/resource rejects that presentation instead of borrowing unrelated art.

<span id="fe9-sys-293"></span> **FE9-SYS-293 — Dialogue text-box layout.** Rect/layout textbox records store window/panel/marker resources, text and marker origins, width, shadow/outline, line height/count, speed, and seat. Font metrics supply signed advances. Dynamic window width scans the upcoming line and clamps `max_future_line_width + 224` to 368–560 pixels; page scrolling moves pending lines by the configured line height and speed. Visual validation is therefore authoritative for translated text.

## Advancing and branching

<span id="fe9-sys-294"></span> **FE9-SYS-294 — Dialogue input and auto-advance.** Each textbox counts its reveal delay down per frame; confirm completes or advances text, held input accelerates, and `$K` waits for input. Scheduled portrait/page motion is serialized with the next text tick. A permitted B-skip starts the conversation skip process; disabled regions ignore it. Both ordinary end and skip release the textbox wait and return control to the VM exactly once.

<span id="fe9-sys-295"></span> **FE9-SYS-295 — Choice and branching dialogue.** A choice presents ordered labels, owns modal focus, and returns the confirmed selection to the waiting script branch. Retail messages disable whole-conversation skip before a choice and re-enable it in each branch, so skip cannot fabricate an answer. Cancel/disabled behavior is defined by the invoking choice widget; the dialogue renderer only returns its explicit result. Reordering labels without matching indices inverts story behavior.

## Context-specific entry paths

<span id="fe9-sys-296"></span> **FE9-SYS-296 — Map dialogue.** Tactical dialogue runs over or alongside the map scene. It can lock input, pan/focus the camera, show/hide units, change music, and resume a trigger after completion. Unit/map state remains authoritative beneath the overlay.

<span id="fe9-sys-297"></span> **FE9-SYS-297 — Base, support, and death-quote dialogue.** These conversations enter through different registries or events but reuse message/layout/portrait systems. Base Info and support conversations need availability/completion state; death quotes are selected from defeat context and must return to death/objective processing. A shared renderer does not imply shared eligibility rules.

## Example — worked path

A talk event becomes available for two adjacent units. Choosing Talk fires the matching event entry. The script focuses actors, selects a conversation context, and requests a message key. Lookup retrieves encoded text; commands place portraits and pages into the active layout. Player input advances until the renderer signals completion. The script changes allegiance/flags, releases the camera/UI lock, and returns to the unit-action consequence queue.

## Edge cases and modding checks

- Preview with the same inherited context the retail script supplies.
- Test every page for glyph coverage, wrapping, cursor position, and portrait overlap.
- Preserve choice indices and control-code parameter widths.
- Distinguish message identity from displayed English text; duplicate prose can have different keys and consequences.
- Confirm skip/fast-forward lands after all required script-side mutations.
- Test regional fonts and layouts rather than assuming US line lengths fit PAL/Japanese resources.

## Review boundary

All ten dialogue systems are reviewed without a blocking research gap. The executable and full message corpus establish lookup/collision behavior, command parsing, inherited context, portrait/layout timing, input/skip, choice ownership, tactical handoff, and context-specific entry routes. A catalogue of unused command combinations or region-specific pixel tuning would be useful format-reference work, but it does not leave a system contract unresolved and does not require a new article.

