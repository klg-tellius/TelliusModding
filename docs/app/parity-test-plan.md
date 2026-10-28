# PoR / RD parity: in-game test plan

Branch `claude/parity-phase9-closure` (Phases 0-8 of `workspace/por-rd-parity-plan.md`, PRs #109, #110,
#112, #113, #114). Every check below passed its unit tests and a scripted GUI run; none has been
played in Dolphin yet. About 2 hours over both games; each section can be done on its own.
Tick each box; for a failure, note the step number and take a screenshot.

## 0. Setup (10 min)

- [ ] Run the app from this branch: `cd <worktree>\App` then `python -m fe_modding`.
- [ ] Make a **disposable copy** of each project (or a checkpoint): one Path of Radiance project
      (for example a copy of `G:\FE9Mod\DemoMod`) and one Radiant Dawn project (a copy of
      `G:\FE10Mod\RadiantDawnMod`). Every step below writes to the copy only.
- [ ] **Settings → Preferences**: Dolphin is found.
- [ ] For the save steps, back up Dolphin's Radiant Dawn save folder first:
      `%APPDATA%\Dolphin Emulator\Wii\title\00010000\52464545\data`.

A step marked **Play** means: on the chapter page, **Play in Dolphin…**, pick the chapter and
difficulty, and let it boot into the chapter.

## 1. Radiant Dawn: maps (Phase 2, 15 min)

- [ ] **Chapters → 1-1 → Build**: move Micaiah two tiles, change one grass tile next to her to forest.
      Save.
- [ ] **Play** 1-1 (Normal).
      Expect: Micaiah starts on the new tile; the forest tile shows as forest in the terrain window
      (Def / Avoid bonus) and costs extra movement.
- [ ] **Map settings** tab of 1-1: it opens with the retail values and no warning.

## 2. Radiant Dawn: story flow and Add chapter (Phase 3, 20 min)

- [ ] **Chapters → Overview**: on 1-2, set the next chapter to 1-4 (skip 1-3). Save.
- [ ] Play 1-2 to victory (or use **Play** on 1-2 with a quick seize/rout).
      Expect: the game goes to 1-4, not 1-3.
- [ ] Set 1-2's next chapter back to 1-3, then **Add chapter…** copying 1-1. Put it after 1-1.
      Expect: a new chapter `05NN` (custom number 56-79) with its own map folder, script and messages.
- [ ] Play 1-1 to victory.
      Expect: the added chapter loads, with 1-1's map, units and title card, then the game goes on to 1-2.
- [ ] Not testable yet: the army combo (stays disabled until army switching is confirmed; `ARMY_RUNTIME_READY`).

## 3. Both games: Chapter data and battle scenes (Phase 4, 20 min)

- [ ] **Radiant Dawn → Chapters → 1-1 → Chapter data**: change the objective text and the weather. Save. **Play** 1-1.
      Expect: the new objective in the chapter's goal window; the weather changes.
- [ ] **Radiant Dawn → 1-1 → Battle scenes → Give this map its own row**, then set plains to
      `bg汎用01草原1`. Save. **Play** 1-1, fight on plains with animations on.
      Expect: the battle shows the generic plains backdrop. Other terrain types look as before.
- [ ] **Path of Radiance → Chapters → 1 → Chapter data**: change the map music. **Play** chapter 1.
      Expect: the new music on the map.

## 4. Both games: characters and Game Data (Phases 5-6, 20 min)

- [ ] **Radiant Dawn → Game Data → Characters → Export Excel…**. In Excel, give Micaiah +5 base
      Magic, save, **Import Excel…**. Save.
- [ ] **Play** 1-1.
      Expect: Micaiah's Magic is 5 higher than retail.
- [ ] **Radiant Dawn → Characters → Ike → Supports**: add a partner, Save. Load a Part 3 or later
      save (or play a chapter where both are deployed).
      Expect: the pair can build support points (the Support command appears after enough turns adjacent).
- [ ] **Path of Radiance → Game Data → Battle scenery**: the table is the same one as
      Chapter → Battle scenes (an edit in one shows in the other). No game check needed.

## 5. Both games: assets (Phase 7, 20 min)

- [ ] **Radiant Dawn → Assets → Battle Weapons**: set the Iron Sword's weapon effect to
      `EID_K_FIRE`. Save. **Play** 1-1 (or any chapter with an Iron Sword user), fight with animations on.
      Expect: the Iron Sword's swing shows the fire effect.
- [ ] **Radiant Dawn → Assets → Tutorials → List: Normal, English**: change the first entry's text. Start a
      new game on Normal and play until the first tutorial window.
      Expect: the new text. Note which of Slot 1-4 the entry uses, and on which difficulty it showed,
      to name the four slots.
- [ ] **Path of Radiance → Assets → Animation Data → Edit…** on a class: change one army's texture
      number to another army's. **Play** a chapter with that class on that army.
      Expect: the unit uses the other army's colours on the map and in battle.
- [ ] **Path of Radiance → Assets → Visual Effects**: add an effect, then **Remove added effect**.
      Save, build, **Play** chapter 1.
      Expect: the game boots and battles play normally (FE8Effect.bin is byte-identical to before).

## 6. Radiant Dawn: tools (Phase 8, 15 min)

- [ ] **Tools → Game Code → Skill activation**: pick a skill one of your units has in a chapter you
      can play (the grid lists Astra, Aether, Adept, Luna, Sol, Colossus, Corrosion, Counter, Miracle,
      Cancel, Deadeye, Pavise) and set its multiplier to 4x, bonus 0. Save, build, **Play** that
      chapter and attack a few times.
      Expect: the skill activates far more often than retail (capped at 100%).
- [ ] **Tools → Game Code → Level-up growth**: set HP gain per success to 3. Level a unit up.
      Expect: HP rises by 3 (or 0) on a level-up.
- [ ] **Tools → Saves → Open NAND folder…** on the backed-up save folder copy: on the Convoy tab,
      set an empty slot to item number 3 (`IID_IRONSWORD`), Save. Load that save in the game.
      Expect: the convoy holds an Iron Sword; the save loads with no corruption message.
- [ ] To decode the Units and Flags tabs: make a save **later** in the game with at least one beorc
      and one laguz unit, and put a copy of `FE10_US.dat` somewhere the app can read
      (`research/rd/SAVE_NOTES.md` lists what is needed).

## Results

Write each section's result, date and project copy here, and update the matching rows of
`workspace/por-rd-parity-audit.md` ("Not checked in Dolphin" → checked, or the failure).
