# Making a new campaign

This guide follows a modder building a new campaign for *Path of Radiance* (US, PAL or JP disc), step by step, and says where each step happens in the app. The pages themselves are described in [Workspace and features](workspace-and-features.md); this file is the order to use them in.

What has been checked: every step marked **verified** below was run on a fresh US extraction (the files the step writes, the Check, a build, and the chapter played in the app's simulator). Nothing here has been played in Dolphin yet; the [campaign plan](campaign-plan.md) lists what still needs the emulator.

## 1. Set up the project

1. **New project** in the launcher, then **Disc & Patch › choose the disc › Extract**. The app keeps the extracted files under the project's `extracted/` folder and builds from them; there is no separate apply step.
2. **Settings › Preferences › Emulator**: point it at `Dolphin.exe` if it is not in Program Files, `%LOCALAPPDATA%` or your user folder (a portable Dolphin unzipped elsewhere is not found by itself).
3. **Mod details** (Disc & Patch): author, version and credits. They go into every `.tpatch` you make.

An untouched extraction gives **0 errors** in **Tools › Check** (verified). It shows 4 warnings that come from the retail data itself (two promoted female classes linked back to classes that do not exist, two `Map6` deployment sections nobody deploys); you can ignore them.

## 2. Make the cast

- **Characters › New character…**, or several at once in **Chapters › New campaign…** (below). A new character is a copy of an existing one under a new `PID_` ID; give it a name and the app writes its `MPID_` text in `Mess/common.m` (verified).
- Classes, items and skills: **Game Data**. New classes and items are copies of existing records (verified: a class copied from a Soldier, two weapons). Skills cannot be added (the game refers to them by position); edit the existing ones.
- Portraits: **Assets › Portraits**. A new portrait must use the palette of the character's existing one; a free-form palette cannot be imported yet.
- Models: **Assets › 3D Models** imports static glTF meshes only. Animated (rigged) models are not supported yet.

## 3. Add the chapters

**Chapters › New campaign…** adds several chapters in one go, in story order, plus the characters (verified with 3 chapters and 4 characters after chapter 31):

- each chapter is a copy of a chapter you pick (its maps, script, dialogue and shops); the map size and tileset are the template's, so pick the template by the map you want;
- tick **Empty** to remove the copied units except the player's army (the deployment sections whose name contains `mikata`, which place the party); the enemies and other units are gone, the sections stay so the script still finds them;
- the new chapters take free numbers from 33 up and are chained: the chapter you chose leads to the first new one, the last new one leads where that chapter used to go.

One chapter at a time: **Add chapter…** on the Chapters page does the same for a single chapter.

A copied chapter keeps parts of its template you have to change yourself: the flags and message IDs in its script, and the objectives, music and backgrounds in **Game Data › Chapters**. A script that loads another chapter's map keeps loading that map (chapters 03 and 05 both run a shared event on `bmap06_2`).

Note on "after chapter 31": chapter 31's script plays the game's ending events before it finishes, so new chapters placed after it come after that ending. Put new chapters earlier, or rewrite chapter 31's end, if that matters to your story.

## 4. Build each chapter

On the chapter's page:

- **Build** — terrain, props, heights and units on the map; **Place unit** puts any character with any class on any difficulty file (verified: a boss and generics placed in a new chapter with new characters).
- **Deployment** — every unit's 48 fields, if the Build tab does not show what you need.
- **Dialogue** — the chapter's messages with a live preview.
- **Script** — the events, in the `.fe9s` language: intro and ending scenes, a recruitment (`@on_talk`), a choice dialog, reinforcements (`@on_phase`). Start with the [script tutorial](script-tutorial.md); the [function reference](script-call-reference.md) lists every call.
- **Shops** — the base shops for each difficulty.
- Enemy behaviour: **Game Data › AI (CP)**, see [AI scripts](ai-scripts.md).

## 5. Put the story in order

**Chapters › Story order…** sets the whole order at once (verified: three new chapters reordered, and the build's `main.dol` carries the new order). Each chapter page's **Overview › Story flow** shows what leads to it and sets its **Next chapter** one link at a time. The order is a patch in `main.dol`; the save menu accepts an added chapter once it is in the order.

## 6. Test

1. **Tools › Check** — broken IDs (a deleted or renamed class, character, item or skill), missing chapter files, deployments naming records that do not exist, chapters nothing leads to. Double-click a row to open the place to fix it (verified for characters, classes, chapters and deployments; rows of a renamed class are grouped per file).
2. **Play...** (on a chapter's Build tab) — plays the chapter in the app on its map: deployments, events, the enemy AI and combat, step by step, on every difficulty (verified on the new chapters). **Skip the opening** (on by default) starts at your first turn. It is an approximation; see its limits below.
3. **Disc & Patch › Build and play in Dolphin** — builds the image and starts it in Dolphin (not verified yet).

Simulator limits: fog shows class vision only; Preparations only chooses among the placed units; a choice dialog takes the first answer unless you set a plan; camera, screen effects and `MapLoad` are skipped (a deployment from the loaded map is reported as "not found").

## 7. Share

**Disc & Patch › Create patch…** makes a `.tpatch` with your mod details; others apply it to their own disc with **Apply patch…** (no project needed: **File › Apply patch to a disc…**). An unedited project builds an image whose files are byte-identical to the disc's (verified; only the file table's offsets move).

## Known limits

- Story slots: chapters 33–89 can be added; 51, 52, 58 and 80–82 are taken by retail records, 90 and up are trial maps. The save's clear history holds 40 chapters, so the war record of a longer story loses its last ones.
- Chapters 28 and 29 are the two halves of Ch.27 (no save menu between them).
- New world map or base screen: not supported.
- Sound: **New track** (Assets › Music) writes a `.stm` file and a `BGM_` cue for it; name the cue as a chapter's map music or in `BGMPlay`. Added sound effects play in Dolphin; an added music cue is not checked in Dolphin yet.
- Portraits: **New portrait…** (Assets › Portraits) makes a new small and large face pair with its own colours; set it as the character's portrait. Not checked in Dolphin yet.
- Skills: the table holds exactly 98 skills. The engine finds each skill's effect by its position in the table (466 hard-coded checks) and about 30 loops stop at 98, so a new skill cannot be added; edit an existing one or give its effect to other units. New skill effects need a code mod.
- Opening movies: an added chapter shows its own title card; a full-screen movie needs a `MoviePlay("Movie/<file>.thp")` call in its script.
