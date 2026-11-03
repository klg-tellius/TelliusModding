# Campaign test plan: simulator and Dolphin

The checks that are left to validate full-campaign support (items B1-B10 of the [campaign plan](campaign-plan.md)). Everything that could run without the emulator was done on 2026-10-06 (see the plan's "Results so far"); what is here needs your eyes, the app's windows or Dolphin.

Use the app from branch `claude/campaign-workflow` (worktree `.claude/worktrees/campaign-workflow`: `python App/main.py` from there), so the Check and "Empty" fixes are in.

For each test: tick it, and write **works**, **workaround** (say which) or **blocked** (say what you saw) on the *Result* line. For anything that fails in Dolphin, note the chapter, the difficulty, the turn and what was on screen; a screenshot or a Dolphin save state helps.

Simulator = **Play...** on a chapter's Build tab. Dolphin = **Disc & Patch (💿) › Build and play in Dolphin**, or open the built `.ciso` from the project's `build/` folder.

## 0. Setup (once)

- [X] **0.1 Test project.** Launcher › New project, choose the US disc, Extract. Name it e.g. `Campaign test`. Do every test below in it, never in `My Fire Emblem Mod`.
  Result: Worked
- [X] **0.2 Dolphin location.** ⚙ Settings › Preferences › Emulator: Browse… to `G:\Dolphin-x64\Dolphin.exe`. Expected: "Found: G:\Dolphin-x64\Dolphin.exe" under the box after reopening the dialog.
  Result: Worked
- [X] **0.3 Memory card.** In Dolphin, use a separate memory card (Config › GameCube › Slot A: a new GCI folder or a new `.raw`) so test saves never mix with your real ones. Do not use save states made with another build: `main.dol` differs between builds.
  Result: Worked
- [X] **0.4 Getting to a chapter quickly.** Tools › Game Code › Developer tools › **Development menu at startup** (on). Build and boot: the game starts on the developer title, whose chapter select starts any chapter. Expected: the menu shows; picking a retail chapter (e.g. Ch.5) starts it. *Also note whether the added chapters (33, 34, 35) are in that list* (the menu lists `ChapterData` records by position; nobody has checked how many it shows). "Production version" goes on to the normal file menu. Turn the patch off again before the B1 run in section 4 if you want a clean start screen.
  Result: Worked

## 1. App checks (no Dolphin)

- [X] **1.1 Check page.** Tools › Check › Run check on the fresh project. Expected: "0 errors, 4 warnings" (JID_ASSASSIN/F, JID_BISHOP/F, two Map6 sections). Double-click a Classes row: Game Data › Classes opens on that class.
  Result: Worked
- [X] **1.2 Mod details.** Disc & Patch › Mod details: set author, version, credits, Save. Reopen: the values are kept.
  Result: Worked
- [X] **1.3 Patch round trip.** Disc & Patch › Create patch… after one small edit (e.g. a character's name). Then **File › Apply patch to a disc…** with the patch and the clean disc. Expected: the patch dialog shows your mod details; the patched image has the edit (open it in a second new project, or boot it in 2.2).
  Result: worked
- [X] **1.4 New campaign dialog.** Chapters › **New campaign…**: Played after **Prologue (01)** (for quick testing; see 4.0), three chapters: `The New Dawn` copy of 05, `Twin Rivers` copy of 10, `Empty Fields` copy of 03 with **Empty** ticked; four characters: `PID_ROWAN` from `PID_OSCAR` "Rowan", `PID_VARGAS` from `PID_PRAGUE` "Vargas", `PID_RAIDER` from `PID_ZAKO` "Raider", `PID_GUARD` from `PID_ZAKO_2` "Guard". Expected: chapters 33, 34, 35 appear as cards with these titles; the Chapters page shows the story order 01 → 33 → 34 → 35 → 02; Check still 0 errors.
  Result: Worked
- [X] **1.5 Story order dialog.** Chapters › **Story order…**: move 34 before 33, OK. Expected: each chapter page's Overview › Story flow agrees (01 → 34 → 33 → 35 → 02). Put it back to 33, 34, 35 afterwards.
  Result: 
- [X] **1.6 Check catches mistakes.** Rename a class used by deployments (Game Data › Classes, e.g. `JID_SOLDIER` → `JID_SOLDIERX`), Run check: errors grouped "N units have class …" per file, and character rows; double-click opens the chapter / character. Undo the rename (Discard unsaved edits, or rename back) and check again: 0 errors.
  Result: Worked

## 2. Build, boot and launch (B2, B3)

- [X] **2.1 Untouched build boots.** In a second fresh project (no edits), Disc & Patch › Build disc, then boot it in Dolphin. Expected: title screen, New game, Prologue starts. (Files were already proven byte-identical to the disc's; only booting is left.)
  Result: Worked
- [X] **2.2 Build and play.** In the test project, Disc & Patch › **Build and play in Dolphin**. Expected: the app builds, then Dolphin opens straight into the game (no game list), and closing the game closes Dolphin. If Dolphin opens but doesn't start the game, or doesn't close, note it: the flags are in `emulator.command()`.
  Result: Worked
- [X] **2.3 Unsaved edits warning.** Edit something without saving, then Build and play: the app lists the unsaved editors and asks before building.
  Result: Worked

## 3. Author the mini-campaign (B1, in the app + simulator)

Do these in the test project after 1.4. After each chapter's edits: **Save Chapter**, run **Play...** on Normal, Hard and Maniac to its first player phase and **End phase** a few turns. Expected in the simulator: no red error in the log, the units you placed appear, the enemy moves. ("Not simulated: SetEventCamera…" lines and a "Deployment group 'bmap06_2_event00_c' not found" warning are known simulator limits, not problems.)

- [X] **3.1 Boss.** Ch.33 Build tab: put `PID_VARGAS` in the boss section (`bmap33_first_boss_n/h/m`, replacing Maizin) with **Same edit on every difficulty**. New: set Deployment file to `dispos_n.bin`, then **Add unit...** above the tools asks for the section too; drag the unit afterwards. Simulator: Vargas is on the map, named "Vargas".
  Result: Worked. 
- [X] **3.2 Generics and the new class.** Game Data › Classes: add a class copied from `JID_SOLDIER` (e.g. `JID_WARDEN`), raise one cap; Items: add two items copied from Steel Lance and Steel Sword; Skills: change one skill's capacity. Save FE8Data.bin. Place two `PID_RAIDER` and one `PID_GUARD` with class `JID_WARDEN` holding a new item in Ch.33. Simulator: they appear with that class and item; attacking one shows a forecast. Retry hints: click **Save FE8Data.bin** after adding the class and items (on 2026-10-07 the project had no `JID_WARDEN` and no new items); in the Build tab choose Deployment file `dispos_n.bin` (then h, m) and put the units in the section marked "battle start", not an "event scene only" one.
  Result: Worked.
- [-] **3.3 Recruitment (`@on_talk`).** Ch.34: place `PID_ROWAN` as an ally/other army unit; in the Script tab add a talk event from Ike to Rowan that moves Rowan to the player army (see the [script tutorial](script-tutorial.md), triggers and recruitment). Simulator: Ike's Talk action on Rowan runs the event and Rowan turns blue.
  Result: 
- [ ] **3.4 Choice dialog.** A choice in Ch.34's opening that branches on the answer. Simulator: **Choices...** set to the second answer, Restart: the second branch runs.
  Result: 
- [ ] **3.5 Reinforcements (`@on_phase`).** Ch.33: a new section with 2-3 enemies, deployed by an `@on_phase` event on enemy phase of turn 3. Simulator: they appear on turn 3.
  Result:
- [ ] **3.6 Cutscenes.** An intro conversation for Ch.33 (Dialogue tab, new message; called from the opening), a mid-chapter one (turn event) and an ending one (before the chapter completes). Simulator: the messages show in order (Auto-advance messages on).
  Result:
- [ ] **3.7 Shop.** Ch.33 Shops tab: add one new item to the Armory on every difficulty (Copy to other difficulties), Save Shops.
  Result:
- [ ] **3.8 Empty chapter.** Ch.35 (Empty): simulator shows only the player's army, no enemies. Note what the chapter's objective is (Game Data › Chapters; the copy of 03 is "rout"); place at least one enemy or change the objective, otherwise check in 4.4 what the game does.
  Result:
- [ ] **3.9 Fog and preparations in the simulator.** Ch.34: tick **Fog (approximate)**: only tiles in your units' vision are shown. **Preparations...**: untick one unit, Restart with these: it is not deployed.
  Result:
- [ ] **3.10 Check.** Run check: 0 errors (warnings only the retail 4, plus any you understand).
  Result:

## 4. Play the mini-campaign in Dolphin (B1, B4)

4.0 With the order 01 → 33 → 34 → 35 → 02 from 1.4, a New game reaches the new chapters right after the Prologue. Play each new chapter **from its start on Normal**, and spot-check Hard and Maniac (via New game on those difficulties, or the development chapter select if it lists them).

- [ ] **4.1 Flow.** Clear the Prologue. Expected: the next chapter is 33 "The New Dawn" (its title card and save-slot name show the new title, not a blank or the template's).
  Result:
- [ ] **4.2 Chapter 33.** Opening conversation, Vargas as boss with his name, the Raiders/Guard with the new class and item, reinforcements on turn 3, the base shop's new item, defeating the boss ends the chapter.
  Result:
- [ ] **4.3 Chapter 34.** Talk recruits Rowan (he stays in the army in the next chapter), the choice dialog branches, the map is the Ch.10 map.
  Result:
- [ ] **4.4 Chapter 35 (Empty).** Starts with the player's army only. Note how it ends (immediately, never, or after the objective you set in 3.8).
  Result:
- [ ] **4.5 Back to the story.** After 35 the game continues with chapter 02 (Ch.1 in the game's numbering).
  Result:
- [ ] **4.6 Save on an added chapter (B4).** In chapter 34's base / preparations, save. Expected: the save menu accepts it (retail refuses chapters above 31). Reset Dolphin, load it: it resumes in chapter 34 with the same army, gold and items.
  Result:
- [ ] **4.7 Mid-battle suspend.** Suspend (pause menu) during chapter 33, reset, continue: it resumes the battle on the same turn.
  Result:
- [ ] **4.8 Ending and trial maps (B4).** Story order: 01 → 35 → ending (put 35 straight after the Prologue, leading to the ending). New game, clear Prologue and 35: the ending plays and the clear is recorded (title screen / trial maps unlock as after a normal clear). Then put the order back.
  Result:
- [ ] **4.9 Chapters after 31.** Story order: 31 → 33 → 34 → 35 → ending. Reach chapter 31 with the development chapter select (0.4) or a save at chapter 31, clear it. Expected: chapter 33 follows (after the game's ending events of 31, which are in 31's script), then 34, 35 and the ending.
  Result:
- [ ] **4.10 Trial maps unaffected.** From the title, Extras › Trial maps: one trial map starts and plays as in retail.
  Result:

## 5. Assets (B5, B6, B7)

- [ ] **5.1 Portrait (B7).** Assets › Portraits: Import Replacement Image… on the portrait of a character who speaks in Ch.34 (Rowan is a copy of Oscar; check on his Character page › Portrait & models which face he uses). Expected in Dolphin: the new face in Ch.34's conversations and in the unit window; colours are matched to the existing palette, so note how far they are from your image.
  Result:
- [ ] **5.2 Static model (B6).** Assets › 3D Models: Import .glb… a static mesh over one map prop (or a weapon) used in Ch.33. Dolphin: it shows, at the right size and place, textured.
  Result:
- [ ] **5.3 Rigged model (B6, decision only).** Not built. After 4.x, decide whether a new animated character model is needed for your campaign; write what you would need (which unit, map or battle model).
  Result:
- [ ] **5.4 Sound effect (B5).** Assets › Sound effects: Add sound effect… (a short WAV) to a group used on maps, then play it from Ch.33's script (`SFXPlay`). Dolphin: it plays, correct pitch and speed, no crash. The dialog warns this is untested in game: this is the test.
  Result:
- [ ] **5.5 Music (B5).** Assets › Music: Replace audio… on the track Ch.33 uses (its BGM in Game Data › Chapters): Dolphin plays the new music, loops correctly. Then **New track**: note that nothing plays it yet (the game finds tracks by ID; wiring is not built).
  Result:

## 6. Simulator against the game (B9)

Play the first two turns of retail Ch.5 (`05`) on Normal in both, with the same moves. Use **Seed** 0, and **Force next battle...** before each fight to give it the hits, misses and crits that happened in Dolphin.

- [ ] **6.1 Deployment.** Same units at the same tiles at the start.
  Result:
- [ ] **6.2 Movement.** For 3 different units (foot, armour, mounted/flying if any): the blue range matches the game's.
  Result:
- [ ] **6.3 Forecast.** For 3 attacks: damage, hit and crit in the simulator's forecast match the game's battle forecast.
  Result:
- [ ] **6.4 Enemy AI.** Enemy phase of turn 1 and 2: which enemies move, where, and whom they attack. Note every difference (unit, tile, target).
  Result:
- [ ] **6.5 Events.** Turn-based events and conversations fire on the same turn and phase.
  Result:
- [ ] **6.6 Known gaps.** Confirm or refute: fog is class vision only; Preparations only chooses among placed units (no base screen); choices take the first answer unless planned; `MapLoad` and cameras are skipped.
  Result:

## 7. Docs (B10)

- [ ] **7.1 Modder guide.** While doing sections 1-5, read [modder-guide.md](modder-guide.md) and mark anything that differs from what you saw. Take screenshots of New campaign, Story order, Check and the Play window for it.
  Result:

## When done

Send me the filled-in file (or tell me "results are in campaign-test-plan.md"). I'll turn every *blocked* into a task, fix what can be fixed, and move the results into the campaign plan's section 3.
