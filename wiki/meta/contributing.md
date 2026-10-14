---
id: "contributing"
title: "Contributing to Tellius Archive"
description: "How trusted editors publish and how other readers propose corrections through the wiki editor"
games: ["path-of-radiance", "radiant-dawn"]
section: "meta"
article_type: "guide"
tags: ["Contributing", "Reference"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["telliusmodding-source"]
cms_collection: "meta"
source_path: "meta/contributing.md"
---
# Contributing to Tellius Archive

Every article has an **Edit in wiki** action. Sign in with GitHub, make the smallest change that explains the evidence clearly, preview it, and save.

## Publication paths

- Trusted repository collaborators save commits directly to `main`; successful validation publishes the new site.
- Other GitHub users work in a fork through Decap Open Authoring and submit a pull request for review.
- Anyone may use **Report an error** without editing an article.

If validation fails, the existing live deployment remains in place. Fix the reported article metadata or link error and save again. Revert an incorrect published edit with Git rather than erasing its history.

## Article standard

A published article should move from accessible explanation to precise reference:

1. Explain what the subject is and why a modder cares.
2. Give a mental model or concrete example.
3. Describe safe, practical edits and the relevant TelliusModding workflow.
4. State risks, compatibility limits, and assumptions.
5. Put byte layouts, formulas, and engine details after the explanation.
6. Cite evidence, preserve confidence labels, and name remaining questions.
7. Link to related concepts instead of repeating their full reference material.

Do not publish game-derived files, long copyrighted text, private credentials, research process diaries, or speculation presented as fact.

## System coverage review

Every Path of Radiance system has a stable `FE9-SYS-NNN` identity in the [Complete Game Systems Inventory](game-systems-inventory.md). A system article lists the entries it intends to explain in `system_entries`; this is an ownership claim, not proof that the page is complete. A reviewer moves an ID into `system_reviewed` only after applying the full [Game System Documentation Review](system-review.md) rubric.

If a system is understood except for a genuine research boundary, use the reviewed-with-gaps path: state the gap precisely, document the work already attempted, and explain the next useful test. If the inventory itself is missing a system, submit a supported System proposal instead of renumbering or silently inserting entries.

## Metadata

Keep an article's `id` stable after publication. Use `aliases` when a route changes. Choose one of `published`, `draft`, `stub`, or `research-needed`; only `published` pages must satisfy the complete teaching standard.

See the [glossary](glossary.md), [source policy](sources.md), and [topic registry](topic-registry.md).
