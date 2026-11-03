# Campaign-modding plan: state and next steps

Goal: make sure the app has everything a modder needs to build a completely new campaign for *Fire Emblem: Path of Radiance*, and adjust it where it does not. This file is the hand-off from the cloud session to the PC session (the PC has the game disc and Dolphin; the cloud did not).

Branch: `ccr-d4a33816-5wusnz`, merged into `main` as pull request #26 (`c186c20`).

## 1. What other communities do (research summary)

Sources were thin: feuniverse.us was blocked in the cloud sandbox, so this comes from search results plus the repo. Path of Radiance has almost no public tooling.

| Ecosystem | Typical workflow | Lesson for this app |
|---|---|---|
| GBA Fire Emblem (FEBuilderGBA, Event Assembler buildfiles, Tiled) | one all-in-one editor (maps, events, units, portraits, music) or text buildfiles; rebuild and test in an emulator | one place for everything; text/version-controllable project; fast rebuild-and-test |
| 3DS/Switch Fire Emblem (Paragon, Cobalt) | GUI over game data; runtime mod loader with mergeable, toggleable mods | safe editor with cross-references; modular, shareable mods |
| Smash Melee/Brawl (Melee Modding Wizard, BrawlCrate) | disc/file editor + model/texture importer + code injection, tested in Dolphin | edit, build, launch emulator, repeat |
| Skyrim Creation Kit | object window + cell/level editor + render view; no hot reload, test by launching | level editing wants a 3D view; one-click "build and run" |

Merged modder workflow: set up project (version control) → cast → assets → chapters (map, units, events, dialogue, AI, shops) → story order → playtest (simulator, then emulator) → validate → package and share.

## 2. Done in the cloud (group A, no disc needed)

| Item | What | Where |
|---|---|---|
| A1 | **Check** page: dangling PID/JID/IID/SID references, duplicate IDs, missing chapter files, bad deployments/shops, script strings naming missing records, unreachable chapters | `App/fe_modding/validator.py`, `gui/pages/check.py`, `tests/test_validator.py` |
| A2 | **Build and play in Dolphin** + Dolphin location setting | `App/fe_modding/emulator.py`, Disc & Patch page, Settings > Preferences, `tests/test_emulator.py` |
| A3 | Docs the app overview pointed at, plus a campaign workflow guide | `docs/app/*.md` |
| A4 | Author/version/credits in the project and in `.tpatch` manifests; Mod details dialog | `project.py`, `patch.py`, `gui/mod_details_dialog.py` |
| A5 | Playthrough: choice dialogs follow a plan, approximate fog view, choose placed units | `playthrough/fog.py`, `natives.py`, `setup.py`, `gui/playthrough_window.py` |
| A6 | **New campaign…** (several chapters + characters, in order) and **Story order…** | `App/fe_modding/campaign.py`, `gui/campaign_dialog.py`, Chapters page, `tests/test_campaign.py` |

`docs/app/script-tutorial.md` and `docs/app/ai-scripts.md` existed locally already (the cloud could not see them); `app.md` links them now. Not done from A4: optional text export of changed tables for version control.

Note: `docs/*` is gitignored, so the cloud session's `docs/app/*.md` (this file and `modder-guide.md`) were never pushed. This copy was pasted back by hand on 2026-10-06.

### Untested in the cloud
- Everything that opens a window (no Tkinter there): Check page, Mod details, Emulator settings, Build and play, New campaign, Story order, the play window's Fog / Choices… / Preparations… controls. They compile and pass pyflakes only.
- Everything that needs real game data: the validator on a real extraction (expect possible false positives), `add_story_chapter` inside New campaign (the cloud test uses a stand-in), Dolphin launch flags (`--exec=… --batch`, assumed correct).
- Tests that need Tkinter or `FE9_EXTRACTED_FILES` skip or error in the cloud (12 failures there, identical with and without these changes). Run the whole suite on the PC first.

## 3. To do on the PC (group B, needs the disc)

### Results so far (2026-10-06, PC with the disc, no Dolphin)

Branch `claude/campaign-workflow` (worktree `.claude/worktrees/campaign-workflow`). Full suite with `FE9_EXTRACTED_FILES` set: 663 tests, all pass (28 skipped). Scratch project used: a fresh extraction of the US disc in the session scratchpad, never the main project.

| Item | Status | What was found / done |
|---|---|---|
| Suite | done | 1 failure, Windows only: `test_emulator` compared `str(Path)` with a POSIX string. Fixed the test. |
| B8 Check on retail | **works** after fixes | Retail (US test disc and the main project's extraction) gave 7 errors + 6 warnings, all false positives. Now 0 errors + 4 explained warnings (see `validator.py` docstring): records 51/52/58/80-82 only checked when the flow reaches them; flow walk stops at 32 (it treated every id up to 89 as reachable); a promoted class's missing back-link is a warning (retail `JID_ASSASSIN/F`, `JID_BISHOP/F`); `Map6_mikata_h/_m` hold `PID_DUMMY3` but no script deploys them (deploying would crash: `init_actor_from_deployment_record` uses the PID lookup unchecked). Breaking on purpose (deleted `C34.cmb`, renamed `JID_SOLDIER`) is reported; a class rename went from 561 rows to 113 (grouped per file). Double-click checked in the app: character, class and chapter rows open their page (skill and support rows got routes too); `Map6` deployment rows have none (chapter 0 has no page). |
| B2 Round trip | **works** (data); boot not checked | Extract → build (no edits) → re-extract: 4,086 files, all byte-identical except `sys/fst.bin` (only the 4,077 file offsets moved; names, sizes, string table equal) and WIT's `align-files.txt`. Boot in Dolphin still to do. |
| B3 Dolphin | not run | Flags in `emulator.command()` match Dolphin's CLI (`--exec=`, `--batch`, `--save_state=`). Dolphin on this PC is `G:\Dolphin-x64\Dolphin.exe`, which auto-detection does not search: set it in Settings > Preferences. |
| B1 Mini-campaign (data + simulator) | **works**, one fix | Headless on the scratch project: New campaign after 31 with 3 chapters (templates 05, 10, 03 "Empty") and 4 characters with names → ids 33-35, titles in `common.m`, flow 31→33→34→35→ending; Story order once (31→34→33→35); new class (copy of Soldier), 2 items, 1 skill edit (`SID_TEMPER` capacity), boss + generics + new class placed in ch.33. Check: 0 errors. Build: no size warning, the built `main.dol` reads back with the flow applied and the new order; new files byte-identical in the image. Simulator (Play window, all three difficulties, 5 turns): ch.33 and ch.34 play like their templates with the new units. **Fixed:** "Empty" also emptied the `mikata` sections, so the chapter had no player army; it now keeps them. Not done: portraits, model, BGM/SFX, cutscenes, recruitment, choice, shop, reinforcements (script/asset work in the GUI), and everything in Dolphin. |
| B4 Chapter limit | static only | The build carries the flow hook and table. Saving / loading / ending flow need Dolphin. Note: chapter 31's script plays the game's ending events before it ends, so chapters "after 31" come after that ending; noted in the modder guide. |
| B9 Simulator | partial | New divergence found: `MapLoad` is not simulated, so a deployment from the loaded map is "not found" (chapters 03 and 05 run a shared `Comeback` event on `bmap06_2`). |
| B10 Docs | done (no screenshots) | `modder-guide.md` rewritten (the cloud copy was lost: `docs/*` is gitignored); `script-tutorial.md` and `ai-scripts.md` already existed locally and are now linked from `app.md`; `workspace-and-features.md` updated (navigation of #25, Check, New campaign, Story order, Build and play, Mod details, Emulator setting). |

The step-by-step checklist for what is left is [campaign-test-plan.md](campaign-test-plan.md).

Still for the user, in Dolphin: B2 boot, B3, the Dolphin half of B1, B4, B5, B7, B9. A ready image of the scratch mini-campaign was built (`proj/build/Scratch campaign.ciso` in the session scratchpad); rebuild it from the steps above if it is gone.

Set up first: `git fetch && git checkout main`, create the venv per the README, run `python -m unittest discover -s tests -v` from `App/`, then `python App/main.py`. Create a project, choose the disc, Extract. Set `FE9_EXTRACTED_FILES` to `<project>/extracted/files` to run the extraction-based tests (also `test_chapter_flow`).

Do these in order:

1. **B8 – Check on retail.** Open the **Check** page on the untouched extraction. Expected: no errors. Every error or warning is a false positive in `validator.py` (likely the script-string warnings, or title warnings): fix the rule, add a test. Then break something on purpose (delete a script, rename a class) and confirm it is reported and that double-click opens the right place.
2. **B2 – Round trip.** Extract → Build with no edits; confirm the image boots in Dolphin and that untouched files are byte-identical.
3. **B3 – Dolphin.** Settings > Preferences > Emulator finds `Dolphin.exe`; **Build and play in Dolphin** boots the image. If the flags are wrong, fix `emulator.command()` (Dolphin CLI: `-e/--exec`, `-b/--batch`, `-s/--save_state`). Then consider a save-state "jump to chapter".
4. **B1 – Mini-Campaign** (the main validation). Build a small campaign and log each item as *works / workaround / blocked*, in the simulator **and** in Dolphin:
   - 3 chapters with new maps of different sizes (Chapters > **New campaign…** after chapter 31, one chapter with "Empty" ticked)
   - 4 new characters (1 recruitable, 1 boss, 2 generics) with names, 1 new class, 2 items, 1 skill edit (skills are fixed-count)
   - custom portraits, one custom model (static glTF only), one BGM, one SFX
   - intro / mid / ending cutscenes, a recruitment (`@on_talk`), a choice dialog, a shop, reinforcements (`@on_phase`)
   - story order: new prologue → new chapters → ending; use **Story order…** once
   - run **Check**, **Build and play**, play each chapter from its start on every difficulty
5. **B4 – Chapter limit.** Put a chapter at id ≥ 33 in the flow and verify saving, loading the save, the chapter-select/ending flow and that trial maps are unaffected. (Cloud finding: ids 33–89 and the save-check hook already exist in `game_code/chapter_flow.py`; what is unverified is the behaviour in the real game.)
6. **B5 – Audio.** Add an SFX and a track; check them in Dolphin (the SFX dialog says "not verified in Dolphin"; "New track" is unwired).
7. **B7 – Portraits.** New portrait in dialogue (palette is shared with the character's existing one; free-form palette import not built).
8. **B6 – Models.** Rigged model import (glTF → `.g`/`.ga`) is not built; static meshes only. Decide from B1 whether it is needed, then design it with real files.
9. **B9 – Simulator vs game.** Compare movement, AI and damage with Dolphin for one chapter; note where the simulator diverges (fog is class-vision only, preparations only choose placed units, choices default to the first entry).
10. **B10 – Docs.** Re-read `docs/app/modder-guide.md` while doing B1 and correct anything that differs from reality; add screenshots; write the missing script tutorial and AI-script page.

## 4. Open gaps (from the first analysis) and their status

| Gap | Status |
|---|---|
| Story structure limit (slots 0–31, 32 = ending) | Partly addressed already (ids 33–89, save-check hook); needs B4 |
| No emulator launch | Built (A2); needs B3 |
| No project validator | Built (A1); needs B8 |
| Animated custom models | Open: static glTF only (A8). Decide after B1 |
| Portrait palette limit | Done 2026-10-15: new palette on replace, New portrait… (Assets › Portraits); not checked in Dolphin |
| New map from scratch (size/tileset/background) | Unknown: chapters are copies; check in B1 whether map size and tileset can be changed freely |
| New world map / base | Unknown; check in B1 |
| Sound/music unverified | B5. SFX add plays in Dolphin; new tracks get a `BGM_` cue (2026-10-15), not checked in Dolphin |
| Missing docs | Written; the tutorial and AI pages existed locally and are linked now |
| Packaging/sharing | Metadata added (A4); text export for version control built 2026-10-15 (Disc & Patch › Export as text…) |
| Radiant Dawn | Out of scope for this plan |

## 5. After B1: update this file

Replace section 3 with the results (works / workaround / blocked per item) and turn each *blocked* item into a task. Likely next builds, in order of value: fixes for whatever B1 blocks, rigged model import, free-form portraits, text export of tables for version control, fuller simulator (base screen, real fog rule), script tutorial.
