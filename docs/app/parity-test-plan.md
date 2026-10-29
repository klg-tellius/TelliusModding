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

### 2026-10-28, unattended run

Run without a person: each edit was made on a copy of the clean disc through the app's own functions
(the same calls the editors make), then booted in Dolphin 2606a with the chapter jump, an isolated user
folder, a scripted pad, Dolphin's file log and screenshots. A test chapter that must be won gets an
automatic victory at its first enemy phase. Clean discs: `G:\ROM\rd_work\RFEE01`, `G:\ROM\por_work\GFEE01`.

| Check | Result | Evidence |
| --- | --- | --- |
| 1. RD map: unit moved | Partial | Micaiah starts elsewhere than in retail, but not on the tile set: the opening walks her, so her second position is not her turn-1 tile. |
| 1. RD map: terrain tile | **Not confirmed** | A one-tile change under the turn-1 cursor still reads Paving Stones; making all 960 tiles Forest crashes on map load (Unhandled Exception 3, LR 0x8029D824). Needs a look at which layer RFEE01 reads. |
| 2. RD story flow (1-1 → 1-3) | **Pass** | After 1-1's victory the game loads `C0103` / `bmap0103` and skips 1-2. Needed two fixes (below). |
| 2. RD Add chapter | **Partial** | The added chapter (`0501`, number 56) is reached after 1-1, with its own script and map, but hangs in its opening before any unit is placed, also when jumped into. Files equal 1-1's apart from the renamed names. It also shows 1-1's title card. |
| 3. RD Chapter data: goal | **Pass** | Hard goal reads "Victory: Defeat boss" on the map and the situation screen (retail: Rout enemy). |
| 3. RD Chapter data: weather | Not confirmed | Snow instead of cloudy: nothing visible on the map. |
| 3. RD Battle scenes | **Pass** | 1-1's battles load `zbg/bg0001grd` (generic plains, a name appended to `BattleTerrName`) instead of `bg0101twn`. |
| 3. PoR Chapter data: map music | **Pass** | Chapter 1 streams `gcfe_bgm_map04_32k.stm` instead of `gcfe_bgm_map00_cut03_32k.stm`. |
| 4. RD Excel import | **Pass** | Micaiah's status page shows Mag 12 (base 4 + 8; retail 7). Needed a fix (below). |
| 4. RD Supports | Not run | Needs a save from Part 3 or later. |
| 5. RD Battle Weapons | **Pass** | The Bronze Axe battle loads `yme/EID_K_FIRE.cmp` (not in the retail run). |
| 5. RD Tutorials | **Pass** | The Guide lists "The Map Menu" twice (entry 1 took entry 2's title), from `Tutorial/tut_data_h_en.bin`. Slot names not checked. |
| 5. PoR Animation Data | **Pass** | Enemy fighters load `ymu/fighter/tex_32.tpl` (the player number) instead of `tex_97.tpl`. |
| 5. PoR Visual Effects add + remove | No game check needed | The file is byte-identical to retail (unit test). |
| 6. RD Skill activation grid | **Pass** | Adept at bonus +100: `EID_K_ADEPT` twice and two Light hits; at x0: none. |
| 6. RD Level-up growth | Left to a person | Package test G1 (below). |
| 6. RD Saves: convoy | Not run | The convoy is not reachable at the start of Part 1, the only RD save here. |

App bugs found and fixed by this run:

- The RD chapter jump (**Play in Dolphin**) set game mode 1, a trial map: every chapter won then opened
  the trial result (GameController label 0x24, FUN_800437D0), which loads `window/achieve.cms`, absent
  from the retail disc, and hangs. It now sets mode 0, the story (`chapter_jump_fe10._STORY_MODE`).
- The RD story-order hook sat at 0x80001800, where Dolphin (cheats off) puts its HBReload stub and
  `STUBHAXX`: under Dolphin every chapter advance went there instead. Moved to 0x80001900.
- Excel import ignored shared strings (Excel saves text cells that way) and absolute sheet paths
  (`/xl/worksheets/...`, written by other tools): a sheet saved by Excel or openpyxl did not import.

Limits found: a chapter jump starts with an empty party, so on Radiant Dawn only 1-1 fields an army (any
later chapter is an immediate Game Over).

### Interactive tests

`workspace/parity-playtest` (built with `python -m tools.session_playtest.build --set parity ...`):
G1 (a level-up gives 3 per growth success) and A1 (optional, Adept seen in battle). Double-click
**Start-Session.cmd**; results go to its RESULTS.md.
