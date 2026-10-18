---
id: "tutorial-authoring-standard"
title: "Modding tutorial authoring standard"
description: "The research, writing, and verification contract for Tellius Modding tutorials"
games: ["path-of-radiance"]
section: "meta"
article_type: "policy"
tags: ["Guide", "Contributing", "Modding app"]
aliases: []
status: "published"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "meta"
source_path: "meta/tutorial-authoring-standard.md"
---
# Modding tutorial authoring standard

The modding curriculum must teach a reader to make, understand, test, and reverse a change. Naming an editor and listing fields is not a tutorial. A published deep tutorial must be executable by a reader who knows *Fire Emblem* but has not used Tellius Modding before.

## Required article contract

A task tutorial uses these sections, in this order, whenever they apply:

1. **What you will make** defines one visible, reproducible result.
2. **Before you begin** names prerequisites, the project state, required files, and a safe checkpoint.
3. **How the editor fits together** identifies the owning file or resource, references to it, and the save action.
4. **Guided walkthrough** gives numbered UI actions, literal example values, and an expected observation after each meaningful stage.
5. **Understand every control** accounts for every control used or exposed by the surface. Large surfaces may link to one companion field reference.
6. **Things to try next** gives at least three evidence-backed variations when the surface supports them.
7. **Interactions and precedence** explains shared records, overrides, linked resources, persistence, and ordering.
8. **Test matrix** covers an unchanged baseline, the intended change, one boundary, and one likely failure.
9. **Troubleshooting** maps symptoms to likely causes, inspection points, and corrective actions.
10. **Save, build, and revert** distinguishes Apply, editor save, project save, build, and restoration.
11. **Limits and confidence** separates source-confirmed, app-tested, simulator-tested, Dolphin-tested, inferred, and unknown behavior.
12. **Related tutorials and references** links prerequisites, natural follow-ups, and the deeper system and format explanations.

Setup or conceptual lessons may replace **Understand every control** with **Understand every choice**. They must still explain the consequences of each option they ask the reader to select.

Numbered curriculum pages use `tutorial_kind: "task"`. A companion field page uses `tutorial_kind: "reference"` and the sections **How this surface fits together**, **Control reference**, **Interactions and precedence**, **Failure modes**, **Limits and confidence**, and **Related tutorials and references**. Companion pages do not count toward the 64-topic migration total and must link back to every task that relies on them.

## Field and command coverage

Use this table shape for a field, command, mode, or option reference:

| Column | Requirement |
| --- | --- |
| Control | Exact label and its containing panel or tab |
| Input | Type, range, allowed choices, ID namespace, or file requirement |
| Meaning | The effect in plain language; distinguish stored data from derived behavior |
| How to choose | A rule for selecting or calculating a sensible value, not “as needed” |
| Interactions | Other fields, records, files, overrides, and engine rules that can change the result |
| Example | A before/after value used by the walkthrough |
| Failure | Behavior of missing, invalid, shared, extreme, or unsupported input |
| Verification | The exact UI, preview, simulator, log, or in-game observation that proves the claim |
| Confidence | Source-confirmed, app-tested, simulator-tested, Dolphin-tested, inferred, or unknown |

A field may be grouped with genuinely identical siblings, such as eight stats, but the prose must still explain any exception. Do not hide unexplained controls behind “advanced,” “usually unchanged,” or “copy a similar record.” If behavior is unknown, say precisely what is unknown and name the next useful test.

## Research procedure

Before drafting, create or update the lesson row in the [tutorial coverage ledger](tutorial-coverage.md):

1. Inventory the current UI from the source that creates its controls and tooltips.
2. Trace each write through the parser or writer and, where possible, to a runtime consumer or test.
3. Compare the related system and format articles. Tooltips and existing prose are claims to verify, not independent evidence.
4. Record contradictions in the ledger. Do not silently choose one account.
5. Select one disposable-project exercise that reaches the important controls without combining unrelated changes.
6. Decide which claims can be proven by source inspection, app reload, simulator/play preview, or Dolphin.

Game-derived dumps, disc contents, and private paths do not belong in the wiki. Summarize the supported finding and cite the declared source key.

## Writing rules

- Use the exact current UI label in bold and state where it is located.
- Give literal example IDs and values, and use the same values throughout the walkthrough and tests.
- Explain a concept before using its abbreviation. PID, JID, IID, SID, AID, and message keys are not interchangeable.
- Separate identity, mechanics, map presentation, battle presentation, and event wiring when different resources own them.
- Explain shared-data consequences before instructing the reader to edit a shared value.
- Do not say “adjust,” “configure,” “set appropriately,” or “test” without saying how to choose the value and what result to observe.
- Do not imply that a successful compile, import, preview, or simulation proves behavior in the built game.
- Label unsupported and untested behavior beside the relevant step, not only in a footer.
- Prefer a small controlled comparison: preserve a baseline, change one variable, observe, restore, then combine changes.

## Review gates

An article advances through the following `tutorial_stage` values:

`legacy`
: Existing short-form material. It remains readable during migration but is not accepted as a deep tutorial.

`inventory`
: UI/action coverage and evidence sources have been recorded.

`draft`
: The deep article is written but has not passed independent execution.

`verified`
: A separate reviewer followed the instructions and the required static checks pass.

`published`
: Verified, editorially reviewed, and suitable for the public curriculum.

The author cannot provide the only verification pass. The technical reviewer checks labels, ranges, signedness, ordering, sentinels, shared pointers, precedence, save ownership, and destructive consequences. The execution reviewer starts from the stated checkpoint and records the actual inputs, warnings, saves, and observations. The editorial reviewer checks that definitions precede jargon and that the task and reference layers remain navigable.

## Verification levels

- `source-reviewed` — current public source and tests support the statement.
- `app-tested` — save/reload or the relevant app workflow produced the stated result.
- `simulator-tested` — Battle Simulator or Play reproduced the mechanic it implements.
- `dolphin-tested` — a built image reproduced the behavior in the game engine.
- `inferred` — evidence supports the interpretation but does not close it.
- `unknown` — the behavior is not established; the article supplies a bounded next test.

The strongest available level belongs beside consequential claims. A lower level is acceptable when it is honest. Screenshots are helpful evidence and must follow the [capture plan](tutorial-screenshot-plan.md), but their absence does not block a text tutorial.

## Acceptance checklist

A tutorial is complete only when:

- Every visible control or required workflow action has one primary explanation in the ledger.
- The walkthrough has consistent example values and observable checkpoints.
- The field or choice reference covers meaning, input, selection guidance, interactions, failure behavior, and verification.
- The test matrix contains baseline, intended, boundary, and failure cases.
- Save ownership, build requirements, and reversal are explicit.
- Claims use the correct verification level and unresolved contradictions are disclosed.
- Prerequisite and related-page links resolve.
- `python App/tools/validate_wiki.py`, `mkdocs build --strict`, and `python App/tools/check_built_wiki.py` pass.
