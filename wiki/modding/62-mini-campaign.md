---
id: "modding-mini-campaign"
title: "Build a three-chapter mini-campaign"
description: "An integration project joining chapter slots, story routing, characters, deployments, recruitment, reinforcement, shops, flags, supports, boss logic, save boundaries, Dolphin testing, and release packaging"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Campaign", "Integration", "Testing"]
aliases: []
status: "draft"
last_reviewed: "2026-10-21"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/62-mini-campaign.md"
tutorial_kind: "task"
tutorial_track: "test-and-release"
tutorial_stage: "draft"
prerequisites: ["modding-new-campaign-wizard", "modding-event-recipes", "modding-share-a-patch"]
verification: ["source-reviewed", "app-tested", "unknown"]
---
# Build a three-chapter mini-campaign

**Route:** Chapters → **New campaign…**; then each chapter's **Build**, **Dialogue** and **Script**; Tools → **Check**; Disc & Patch

## What you will make

You will build a three-chapter campaign played after Endgame: *Border Watch* (33), where a new character, the Scout, joins when Ike talks to it; *The Ford* (34), where an enemy wave arrives on turn 3, once; *Old Fort* (35), whose boss holds his tile; then the ending. Every ID below is the one used when this build was run with the app. At the end you have a checklist that ties lessons 07–46 together and a campaign ready for a Dolphin playthrough and a patch.

## Before you begin

- The lessons this build uses: [Create a campaign skeleton](08-new-campaign-wizard.md), [Recruit by talk and make a boss](14-recruitment-and-bosses.md), [Add and verify a reinforcement wave](32-reinforcements.md), [Design, register, and test event flags](34-event-flags.md), [Package and share a mod](61-share-a-patch.md).
- A copy of the project folder, and a worksheet for the IDs.

## How the editor fits together

The worksheet for this build:

| Chapter | Number | Template | Map folder | New content | Lesson |
| --- | --- | --- | --- | --- | --- |
| Border Watch | 33 | Ch.1 (02) | `bmap33` | `PID_TUTORIAL_SCOUT` in place of a bandit; talk event `ScoutTalk`, flag `SCOUT_JOINED`, message `MS_33_TK_SCOUT` | 14 |
| The Ford | 34 | Ch.2 (03) | `bmap34` | sections `bmap34_wave_n`, `_h`, `_m` (3 enemies each); event `FordWave` on turn 3, enemy phase | 32 |
| Old Fort | 35 | Ch.3 (04) | `bmap35` | the copied boss `PID_HIBUCCHI` with **Hold position** | 14 |
| Story | | | | 31 → 33 → 34 → 35 → 32 (ending) | 07 |

Each copied chapter keeps its template's events, messages and flags: 33 still has Ch.1's seize goal at (8, 5) and the Boyd and Oscar talks; 34 still brings Titania on turn 3 and fights Ch.2's boss; 35 still has Ch.3's boss quotes and Marcia's talk. Read each copied script before adding to it.

## Guided walkthrough

### 1. The skeleton

1. **Chapters › New campaign…**: **Played after** *31 · Endgame: Repatriation*; chapter rows *Border Watch* copy of 02, *The Ford* copy of 03, *Old Fort* copy of 04 (all with **Empty** off); character row `PID_TUTORIAL_SCOUT`, *Scout*, copy of Boyd. **Create campaign**.
2. Check the flow on each Overview: 31 → 33 → 34 → 35 → *32 · Ending*.
3. **Tools › Check**: the baseline (0 errors, 4 warnings on a US disc).

### 2. Chapter 33: the recruit

1. **Build**, *Normal*: select the bandit at tile 3, 12 in `bmap33_first_n`, set **Character** `PID_TUTORIAL_SCOUT`, **Apply**. Do the same on *Maniac*. On *Hard* that bandit is elsewhere: pick a `PID_BANDIT_MOU` of `bmap33_first_h`. **Save Chapter**.
2. **Dialogue**: **New…** `MS_33_TK_SCOUT`, two lines between Ike and the Scout, **Save Chapter**.
3. **Script**: in `Startup`, before `RegistLocationFlags()`, add `regist("SCOUT_JOINED")`; at the end add:

    ```python
    @on_talk(pid1="PID_IKE", pid2="PID_TUTORIAL_SCOUT", flag=0, name="SCOUT_JOINED")
    def ScoutTalk():
        TalkEvent("MS_33_TK_SCOUT")
        UnitTransferToForceByPID("PID_TUTORIAL_SCOUT", 0)
        set("SCOUT_JOINED")
    ```

    **Check**, **Save**.

### 3. Chapter 34: the wave

1. **Build**, *Normal*: **Add section** `bmap34_wave_n` and add three enemies at the map's edge ([Add and verify a reinforcement wave](32-reinforcements.md); the build log copied three soldiers of `bmap34_first_n`). Repeat on *Hard* (`bmap34_wave_h`) and *Maniac* (`bmap34_wave_m`). **Save Chapter**.
2. **Script**, at the end:

    ```python
    @before_phase(turn_from=3, turn_to=3, phase="enemy")
    def FordWave():
        DisposSetMode("bmap34_wave_n", "bmap34_wave_h", "bmap34_wave_m")
    ```

    `turn_from=3, turn_to=3` runs it on turn 3 only, so it needs no flag. **Check**, **Save**.

### 4. Chapter 35: the boss

**Build**, each difficulty: select `PID_HIBUCCHI` in `bmap35_first_n` (`_h`, `_m`), tick **Hold position**, **Apply**; **Save Chapter**. His quotes (`@on_battle`) and death event (`@on_death`) come with the copied script.

### 5. Check, play, ship

1. **Tools › Check**: back to the baseline, 0 errors. A missing message or a misspelled section name is not checked: the playthrough finds those.
2. Play each chapter in the app ([Play and rewind a chapter in the app](58-play-chapter.md)) and with **F5** in Dolphin.
3. Build, and play from a save made in Endgame: win it, save at the save menu, play 33 (talk to the Scout), save, play 34 (the wave on turn 3), save, play 35, reach the ending. Reload each save once.
4. Make the patch and apply it to a clean disc ([Package and share a mod](61-share-a-patch.md)); boot the result and repeat a short check.

## Understand every choice

| Choice | Why this build makes it | Alternative |
| --- | --- | --- |
| After Endgame | Keeps the retail story reachable for testing | **Played after** the Prologue to replace it |
| Copies, not **Empty** | Each chapter works at once; you change one thing at a time | **Empty** chapters and your own units |
| Chapter flag for the recruit | The talk only matters in 33 | `global("…")` in `startup.cmb` to remember it later ([Design, register, and test event flags](34-event-flags.md)) |
| Turn-limited trigger for the wave | `turn_from` = `turn_to` already runs once | A flag, for waves that a condition triggers |
| **Hold position** for the boss | One deployment flag, no script | An AI order ([Create common AI orders](44-common-ai-orders.md)) |

## Things to try next

1. **Remember the recruit.** Make `SCOUT_JOINED` a campaign flag and change a line in 35 when it is set.
2. **A conditional ending.** In 35's victory function, play a different message when `UnitCheckExistsByPID("PID_TUTORIAL_SCOUT")`.
3. **Shops.** Give 34 its own armory ([Edit armory, vendor, forge, and gold](46-shops.md)).

## Interactions and precedence

- The copied scripts and messages are the templates'; your additions run alongside them.
- The story table, the records and the files must agree: **Check** proves the files and records, the playthrough proves the rest.
- Save states taken in an older build carry old data: test from saves made in the game's own save menu.

## Test matrix

| Boundary | Expected evidence |
| --- | --- |
| Skeleton | 31 → 33 → 34 → 35 → ending; Check at baseline |
| 33 recruit | Talk only from Ike; once; the Scout is blue after it |
| 33 → 34 save and reload | The Scout is in the army |
| 34 wave | Three enemies in turn 3's enemy phase, on every difficulty; none on turn 4 |
| 35 boss | Never moves; quotes; death event |
| 35 → ending | The ending plays |
| Patch | Applied to a clean disc, the same playthrough passes |

## Troubleshooting

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| No **Talk** with the Scout | Not deployed on that difficulty, or the flag is already set | **Appearances**; a new save |
| The talk shows an empty box | `MS_33_TK_SCOUT` not saved in `c33.m` | Save the Dialogue tab |
| No wave | Section names differ from the call | Compare the section names on **Build** with the script |
| A wave every turn | `turn_to` larger than `turn_from` | Set both to 3 |
| A Ch.1 cutscene plays in 33 | The copied script | Remove or edit the copied event |

## Save, build, and revert

Copy the project after the skeleton and after each chapter; restore only to a copy that passed its checks. Freeze, check, build, play from a fresh save, create and apply the patch, and keep the worksheet with the project.

## Limits and confidence

- The skeleton, the three edits, the compiles and the check were run on a US disc with the app's own code (the wizard, the deployment and script writers, the validator), then reverted: 0 errors and the 4 retail warnings (app-tested). The steps above make the same edits through the pages.
- The playthrough and the patch of this campaign were not run in Dolphin (unknown). The app cannot create new world-map or base-screen structures.

## Related tutorials and references

- Before: [Package and share a mod](61-share-a-patch.md)
- Also: [Understand a chapter's parts](06-chapter-anatomy.md), [Build reliable chapter events](35-event-recipes.md)

---

[← Previous: Package and share a mod](61-share-a-patch.md) · [All tutorials](index.md) · [Next: Know the current limits →](63-known-limits.md)
