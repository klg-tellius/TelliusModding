# Tellius Modding app

The app is a Windows Python/Tkinter desktop application for modifying *Fire Emblem: Path of Radiance* (GameCube) and *Fire Emblem: Radiant Dawn* (Wii). It organizes work into projects, extracts a source disc, exposes supported game data through editors and viewers, and rebuilds a playable disc image.

The application source is under `App/`.

## Commands

Run these commands from `App/`:

```bash
python main.py
python -m unittest discover -s tests -v
```

## Architecture

The app has four main layers:

1. **Project and game layer** — `fe_modding/project.py`, `games.py`, `config.py` and `patch.py` define projects, supported games, recent projects and settings, the extract/build lifecycle, and `.tpatch` mod patches.
2. **Desktop workspace** — `fe_modding/gui/` contains the launcher, the workspace shell (top-bar sections, Disc & Patch button, breadcrumbs, back/forward, Ctrl+K search, status bar), the pages (`gui/pages/`: Home, Chapters, a page per chapter, Characters, a page per character, Game Data (a tile per section: Classes … Supports, Flags, AI), Assets (with Map Objects), Tools (Battle Simulator, Saves, Game Code), Disc & Patch), the Settings and Apply-patch dialogs, the editors and viewers they embed, the theme (`gui/theme.py`, Sun Valley light/dark) and the in-session change log. `fe_modding/project_index.py` joins the formats (characters, deployments, messages, scripts) for the chapter and character pages. `fe_modding/script_sources.py` loads and saves event scripts as source for the Script tab and the Flags tab.
3. **Game-data layer** — `fe_modding/formats/` reads and, where supported, writes the binary, image, audio, video, script, map, and model formats used by the games.
   `fe_modding/battle_sim/` is the battle simulator's rules engine (Path of Radiance forecast, strike order, skills, seeded or fixed rolls; units levelled and promoted with the fixed growth mode in `units.py`), with no Tk code, plus the engine's battle staging (`staging.py`: `zdbx/param.dbx` and `_prm.dbx` values; `timeline.py`: each strike tick by tick as `main.dol` stages it; `camera.py`: the `xcam/` scripts, tweens, mirroring and shake) and the battle-asset lookup; `formats/battle_terrain.py` places a `zbg/` backdrop. Tools › Battle Simulator (`gui/battle_simulator.py`) drives it; **Render fight** opens `gui/battle_window.py`, which plays the fight in real time with the battle models (`gui/battle_stage.py`, also used by the playthrough's battle window).
   `fe_modding/playthrough/` plays a chapter without the game, also without Tk code. It covers movement, the player's actions (Attack, Staff, Shove, Talk, Visit and the other tile actions, Canto) and fights through `battle_sim`. A `.cmb` interpreter (`event_vm.py`, natives in `natives.py`) runs the event triggers, a `cp_data.bin` interpreter (`ai_vm.py`) runs the enemy phase in turn order, and messages show one page at a time. Every step is one script instruction, message page or AI entry. The whole state is plain data, so `simulation.py` keeps a snapshot per step for going back, going forward and branching. The Build tab's **Play...** button opens `gui/playthrough_window.py`, with optional battle animations (`gui/playthrough_battle.py`). Some of it is approximate:
   - autolevelled stats use average growths;
   - the AI picks targets and tiles with its own score built from the MTYPE weights;
   - natives and AI ops that aren't modelled are logged and return 0;
   - fog is a view only (`playthrough/fog.py`: tiles within the class's vision of a player unit; no torches, roofs or line of sight) and does not limit the AI; there is no base screen, and the preparations are reduced to choosing which units are placed (when the opening deploys nobody);
   - choice dialogs take the first entry unless the window's **Choices...** plan names another (`GameState.choice_plan`).
4. **External-tool layer** — `fe_modding/tools.py` invokes WIT and FFmpeg from developer-provided `tools/` binaries or the per-user tool cache for disc operations and general video decoding. `fe_modding/emulator.py` finds and starts Dolphin on a built image; a chapter page's **Play in Dolphin...** button (also **Play > Play chapter in Dolphin...**, F5, which asks for the chapter when no chapter page is open; Ctrl+F5 builds and plays the disc) skips the build: it copies `extracted/sys` into `build/dolphin_run/` with a `main.dol` that boots straight into that chapter on the chosen difficulty with a fresh army (`game_code/chapter_jump.py`), links `files` there as a directory junction to `extracted/files`, and has Dolphin boot that folder's `sys/main.dol` (Dolphin plays an extracted disc tree directly). The project's own `main.dol` is never patched for it.

Editors operate directly on files in a project's `extracted/` directory. Building a project packages the current contents of that directory; there is no separate apply or staging step.

The two games share the architecture, but game-specific disc formats and build outputs are centralized in `fe_modding/games.py`. Path of Radiance builds to CISO and Radiant Dawn builds to WBFS. Disc images can also be `.rvz`: WIT cannot read that format, so `tools.extract_disc` converts it to a temporary ISO with `DolphinTool` (found next to the configured `Dolphin.exe`) and extracts that. A Wii disc is extracted from its DATA partition and the result must hold `sys/`, `files/`, `disc/`, `ticket.bin`, `tmd.bin` and `cert.bin`.

Everything that differs per game goes through a `GameProfile` (`fe_modding/game_profile.py`, reached as `project.profile` or `games.profile(game)`) instead of `if game ==` checks. It holds the logical-to-physical file map (`game_data` is `FE8Data.bin` on Path of Radiance and the LZ10-compressed `FE10Data.cms` on Radiant Dawn; likewise `anim_data`, `battle_data`, `ai_data`...), the chapter id scheme and file templates (`C05.cmb` / `C0101.cmb`, `dispos.cmp` / `dispos_<n|h|c>.bin`, `shop/` / `Shop/`), the difficulty letters, and the set of **features** that have a decoder for the game. `project.read_logical(name)` / `write_logical(name, data)` read and write a logical file with the LZ10 layer handled. A screen whose feature the profile does not list shows "... is not available for Radiant Dawn yet" (`profile.unavailable(feature)`) instead of reading a layout it does not understand; switching a feature on in the Radiant Dawn profile is how a new decoder is released. Radiant Dawn's database is `FE10Data.cms`, decoded by `fe_modding/formats/fe10data.py`: the character, class, item and skill tables, whose records are variable-size (a count byte says how many label pointers follow), so an edit that grows or shrinks a record moves every pointer, pointer target and symbol after it. The fixed-size tables are decoded too: chapters, terrain (with its shared stats blocks), supports, army groups, bonds, affinities, affinity pairs, the weapon triangle, the difficulty constants, the battle scenery per map and terrain type and the biorhythm rows; `formats/fe10growth.py` reads `FE10Growth.cms`, the absolute stats of each character at every internal level. Its Game Data page (`Fe10GameDataPage`, the `data_tables` feature) edits all of them in `gui/fe10_data_editor.py`, adds a record as a copy of another and removes one (`fe10data.add_record` / `remove_record`). The project check runs `validator_fe10.py` on Radiant Dawn projects. The disc ID in `sys/boot.bin` (`GFE*` / `RFE*`) identifies the game (`games.detect_from_extracted`); choosing or extracting a disc of the other game warns. The desktop distribution currently targets Windows x64. Portable releases include Python and its dependencies; the first-run setup downloads WIT and optional FFmpeg. See [Windows releases](docs/app/windows-release.md).

Radiant Dawn text (the `dialogue` and `fonts` features, `GameProfile.message_dialect == "fe10"`): the Mess container is Path of Radiance's, but message text is a byte-code instead of `$` commands. `formats/fe10_message.py` tokenizes it losslessly, shows it in a `<...>` notation (`<speaker:04>`, `<show:4D>`, `<w2>`, `<R:上下会話>`, `<FL|PUGO|IKE>`, `<wait>`) and groups it into steps; `message.read_text_order` / `write_messages(..., text_order)` keep a file's text-blob order so an unedited file is rebuilt byte for byte. The Dialogue tab uses `gui/fe10_step_editor.py` and the preview `gui/fe10_conversation_preview.py`, which replays a message per `<wait>` (`formats/fe10_conversation.py`) and draws it (`fe10_conversation_render.py`) from the layout seats and boxes of `window/RectDesc*.bin` (`formats/fe10_rect.py`, including the speech-balloon geometry of the game), the portraits of `Face/facedata.bin` (`formats/fe10_faces.py`), the backgrounds of `s/rect.bin` and the talk font, in 4:3 or 16:9. While Radiant Dawn has no chapter pages, Assets › Conversations opens every Mess file in place. `formats/fe10_conversation_data.py` and Assets › Conversation Lists edit `FE10Conversation.cms` (base Info conversations, found by the symbol `CONV_INFO_DATA_<chapter>_<event>`; the Conversation Room's Path of Radiance supports; support chat lines). The Fonts page lists the profile's `font_files` (eleven LZ10 GCF fonts on Radiant Dawn). `chapters.chapter_titles` reads Radiant Dawn titles from the ChapterData title keys, and the Game Data Chapters tab draws a chapter's `window/title/e_ch<id>.cms` title card (`chapter_images.fe10_title_card`). The engine's name hash has `GameProfile.name_hash_buckets` buckets (509 / 2027), which the Dialogue tab's ID check uses. European text files (`d_ f_ s_ i_`) use single-byte tables that are not decoded yet.

Radiant Dawn event scripts (the `scripts` feature, `GameProfile.script_dialect == "fe10"`): the `.cmb` layout is Path of Radiance's, and `formats/cmb` handles both bytecodes through a `Dialect` (`model.FE9` / `model.FE10`, read from the compiler build stamp at header +0x18). Radiant Dawn's `localCall` index is one or two bytes, and its compiler emits six more instructions (`inc`, `dec`, `dup`, `ret0`, `ret1`, `assign`); the compiler reproduces its idioms (assignments without `pop`, `return 0/1` as `ret0/ret1`, `ret0` epilogues for callable functions, `switch`/`case` chains, `x++`), so every vanilla script decompiles and compiles back byte for byte. The language gains `switch` and `++`/`--`, which compile only for Radiant Dawn. `catalog.load_externs(dialect)` and `catalog.triggers(dialect)` give each game's natives (`externs_fe10.json`: 656 natives, each described, plus startup.cmb's helpers) and trigger kinds (Radiant Dawn adds rescue, give/take, move-through and epilogue triggers and changes the base-conversation one), and `event_flags.flag_table(dialect)` the flag table (128 slots). While Radiant Dawn has no chapter pages, Assets › Scripts opens every script in the script editor, and Game Data › Flags shows its campaign and chapter flags (no save tab: Radiant Dawn saves are not decoded yet).

## Path of Radiance chapter objectives

The **Chapter data** tab edits the chapter's `FE8Data.bin` record. Its Normal objective slots are:

| Slot | Label | Text key prefix |
| --- | --- | --- |
| 0 | Goal | `MW_` |
| 1 | Goal second line | `MW_` |
| 2 | Defeat condition | `ML_` |
| 3 | Defeat second line | `ML_` |

Hard and Maniac each store three overrides: fields 0, 1 and 2 replace Normal slots 0, 1 and 3. Normal slot 2 is the shared defeat condition. An empty override keeps the Normal text. The music and background fields open their selected cue or resource in Assets › Music or Assets › Backgrounds. Save chapter data with **Save FE8Data.bin**.

## Chapter dialogue, scenery and forge controls

In Path of Radiance's Dialogue tab, the layout picker shows English names. The editor converts the chosen name back to the game's layout ID when saving; a raw ID can still be entered for an unknown layout. The compact layout and background dropdowns on the two toolbar rows update their matching actions in the message; a missing action is added at the start. **Search…** opens a visual background picker. The step form and preview's initial context offer the same background choices. The Actions menu is one searchable list.

On **Battle scenes**, the first `BattleTerrData` row is a shared fallback. In retail data that row is named `Map6`; this is its stored map name, not a separate mode. A map with no row uses it for every terrain type, and an empty cell in a custom map row inherits that terrain type's entry from the first row. Editing the shared row affects every map that relies on it.

On **Shops**, the forge grid has five weapon-family rows and nine fixed base columns. Each cell selects the item offered for that family and base on the selected chapter and difficulty; **(none)** removes that option. Changing a cell does not change the item's stats or price. **Save Shops** writes the selected difficulty's shop file.

## Detailed references

This file is the required high-level app overview. Agents should read the following files only when the task involves that part of the application:

- [Project lifecycle](docs/app/project-lifecycle.md) — project layout, supported disc inputs, extraction, and building.
- [Workspace and features](docs/app/workspace-and-features.md) — navigation, chapter handling, editors, viewers, and known user-facing limitations.
- [Script language](docs/app/script-language.md) — the `.fe9s` event-script language, the Scripts tab and the script command line.
- [Script modding tutorial](docs/app/script-tutorial.md) — progressive `.fe9s` lessons, from a first event to a chapter overhaul.
- [AI scripts](docs/app/ai-scripts.md) — Game Data › AI (CP): how a unit's turn runs, the readable AI code (`formats/cp_ai_lang.py`, opcodes in `formats/cp_ops.py`), the raw view and the other `cp_data.bin` tabs.
- [Campaign-modding plan](docs/app/campaign-plan.md) — state of the work on supporting a full new campaign, and the checklist to run with a disc.
- [Making a new campaign](docs/app/modder-guide.md) — a modder's workflow and where each step happens in the app.
- [Formats and tools](docs/app/formats-and-tools.md) — format-module responsibilities, write-support boundaries, bundled tools, and test coverage.
- [Known bugs](docs/app/known-bugs.md) — confirmed but unfixed app defects.

Research history, reverse-engineering evidence, and unresolved game-format investigation belong in `research.md` and the relevant research notes, not in this app overview.
