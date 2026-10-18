---
id: "modding-check-project"
title: "Check a project and fix problems"
description: "Interpret every checker category, navigate to owners, and prove a repair without hiding warnings"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "start-safely"
tutorial_stage: "draft"
prerequisites: ["modding-dolphin-setup"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Validation", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/05-check-project.md"
---
# Check a project and fix problems

**Route:** Tools → Check

## What you will make

You will save a baseline report, induce one harmless broken reference in a disposable copy, navigate from the report to its owner, repair it, and rerun the checker. You will also classify warnings the checker cannot resolve automatically.

## Before you begin

Use an extracted project with a checkpoint. Save all intended editor changes first: the checker reads project files, not unsaved widgets. Run the checker on the untouched baseline and preserve its results so retail exceptions are not mistaken for your regressions.

## How the editor fits together

**Run check** validates cross-file structure without running the game. Results have **Severity**, **Area**, **File**, and **Problem** columns. Double-click or press Enter on a row with a route to open the likely owner.

Checks cover duplicate and missing PIDs/JIDs/IIDs/SIDs, class promotion and innate-weapon links, skills/supports, ChapterData and required chapter files, titles and reachability, deployment identities, script ID strings and global-slot pressure, and shop items. Path of Radiance retail exceptions can be warnings when the bad data is known to be unreachable.

## Guided walkthrough

1. Save all owners, open **Tools → Check**, and select **Run check**. Record total errors/warnings plus every baseline warning.
2. Read each row as a claim: severity says urgency, area gives the consumer context, file names the evidence source, and problem states the violated rule.
3. In a disposable checkpoint, choose one deployment unit and temporarily replace its PID with a clearly nonexistent `PID_TUTORIAL_MISSING`. Save the deployment.
4. Rerun the check. Find the new error naming the deployment archive, section/row context, and missing PID. Double-click it to navigate.
5. Restore the original PID in that row and save. Do not create a character named `PID_TUTORIAL_MISSING`; the deployment reference is the deliberate defect.
6. Rerun. Confirm the induced row disappears and the report returns exactly to baseline.
7. For each remaining warning, record one disposition: accepted retail baseline; unreachable/dead data; conservative string match; deferred with runtime test; or real issue scheduled for repair. Never silently ignore it.

## Understand every control

| Result/control | Meaning | Response |
| --- | --- | --- |
| Run check | validates the current saved extracted project | run after coordinated edits and before builds |
| Error | known structural condition likely unsafe | repair before release/build testing |
| Warning | uncertainty, reachability, or risky inconsistency | investigate and document disposition |
| Area | logical consumer such as Classes or Chapter 07 | identify impact scope |
| File | physical/shared owner used as evidence | inspect this and its caller |
| Problem | exact failed invariant | repair the invariant, not just the wording |
| Double-click/Enter | opens stored route when available | verify it reached the true owner |

## Interactions and precedence

One missing shared ID can create many dependent rows. Repair the owner or intentional rename first, rerun, then address survivors. Duplicate IDs are not a valid fix: the game may find only one record. Script scanning conservatively recognizes ID-shaped strings, so a warning can be dead text; runtime reachability must decide. Story-flow availability controls unreachable-chapter analysis.

The checker reports saved bytes. A correct unsaved form cannot cancel an error in the file, and a clean report cannot make an older build current.

## Test matrix

| Case | Expected report |
| --- | --- |
| untouched extracted baseline | saved reference result |
| missing deployment PID | error naming missing PID and deployment context |
| restored PID | induced error gone |
| duplicate table ID | error that ID is used by more than one record |
| unreachable added chapter | warning when story flow can be inspected |
| script with unknown ID-shaped text | warning requiring caller/reachability review |

## Troubleshooting

If the check says the project has no game-data file, extraction is incomplete. If the check itself reports a read failure, preserve the resource and restore that exact file from a checkpoint. If a row does not navigate, use **Area**, **File**, and exact ID to locate it manually. If an error remains after repair, confirm the correct difficulty/part/resource was saved and rerun rather than relying on the old list.

## Save, build, and revert

Run the checker only after saving relevant owners. Preserve baseline and post-change reports with the project revision. Revert the induced defect from the checkpoint or by restoring its exact original value, rerun, then build. A clean check is a gate, not a runtime test.

## Limits and confidence

The listed validation categories and navigation behavior are source-reviewed. The checker does not execute scripts, validate every coordinate/visual asset, prove an event converges, or establish hardware compatibility. Script-string results are conservative. Those gaps retain **unknown** runtime confidence until exercised.

## Related tutorials and references

- [Set up Dolphin and build the game](04-dolphin-setup.md)
- [Understand a chapter's parts](06-chapter-anatomy.md)
- [Troubleshoot crashes, missing data, and bad builds](64-troubleshooting.md)

---

[← Previous: Set up Dolphin and build the game](04-dolphin-setup.md) · [All tutorials](index.md) · [Next: Understand a chapter's parts →](06-chapter-anatomy.md)
