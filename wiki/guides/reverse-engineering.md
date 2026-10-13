---
id: "reverse-engineering"
title: "Reverse engineering learning path"
description: "How to move from an unknown file or behavior to a reproducible, confidence-labelled archive claim"
games: ["path-of-radiance", "radiant-dawn"]
section: "guides"
article_type: "learning-path"
tags: ["Guide", "Research", "Open questions"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "guides"
source_path: "guides/reverse-engineering.md"
---
# Reverse engineering learning path

The goal is a claim another researcher can reproduce, not merely a plausible field name.

## Route

1. Start with [Documentation Conventions](../meta/sources.md) and the [Glossary](../meta/glossary.md).
2. Locate the resource through [Disc & File Layout](../meta/disc-layout.md) and [File Format Index](../meta/format-coverage.md).
3. Separate container facts from payload interpretation using LZ10, pack, and labeled-section references.
4. Compare every occurrence, seek an independent source, and test behavior in the game where feasible.
5. Publish the narrowest supported statement with a claim-level confidence label.
6. Record counterexamples and unresolved meaning in [Open Questions](../meta/unexplored.md).

Never publish extracted game data merely to make a claim easier to inspect. Prefer schemas, small identifiers, aggregate results, and reproduction steps.
