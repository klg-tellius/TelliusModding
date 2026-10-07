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
2. **Desktop workspace** — `fe_modding/gui/` contains the launcher, the workspace shell (top-bar sections, Disc & Patch button, breadcrumbs, back/forward, Ctrl+K search, status bar), the pages (`gui/pages/`: Home, Chapters, a page per chapter, Characters, a page per character, Game Data (with the Flags tab), Assets (with Map Objects), Tools (Battle Simulator, Saves, Game Code), Disc & Patch), the Settings and Apply-patch dialogs, the editors and viewers they embed, the theme (`gui/theme.py`, Sun Valley light/dark) and the in-session change log. `fe_modding/project_index.py` joins the formats (characters, deployments, messages, scripts) for the chapter and character pages. `fe_modding/script_sources.py` loads and saves event scripts as source for the Script tab and the Flags tab.
3. **Game-data layer** — `fe_modding/formats/` reads and, where supported, writes the binary, image, audio, video, script, map, and model formats used by the games.
   `fe_modding/battle_sim/` is the battle simulator's rules engine (Path of Radiance forecast, strike order, skills, seeded or fixed rolls), with no Tk code, plus the fight timeline and the battle-asset lookup; Assets › Battle Simulator (`gui/battle_simulator.py`) drives it and plays the fight with the battle models in `gui/battle_stage.py`.
   `fe_modding/playthrough/` plays a chapter without the game, also without Tk code. It covers movement, the player's actions (Attack, Staff, Shove, Talk, Visit and the other tile actions, Canto) and fights through `battle_sim`. A `.cmb` interpreter (`event_vm.py`, natives in `natives.py`) runs the event triggers, a `cp_data.bin` interpreter (`ai_vm.py`) runs the enemy phase in turn order, and messages show one page at a time. Every step is one script instruction, message page or AI entry. The whole state is plain data, so `simulation.py` keeps a snapshot per step for going back, going forward and branching. The Build tab's **Play...** button opens `gui/playthrough_window.py`, with optional battle animations (`gui/playthrough_battle.py`). Some of it is approximate:
   - autolevelled stats use average growths;
   - the AI picks targets and tiles with its own score built from the MTYPE weights;
   - natives and AI ops that aren't modelled are logged and return 0;
   - fog is a view only (`playthrough/fog.py`: tiles within the class's vision of a player unit; no torches, roofs or line of sight) and does not limit the AI; there is no base screen, and the preparations are reduced to choosing which units are placed (when the opening deploys nobody);
   - choice dialogs take the first entry unless the window's **Choices...** plan names another (`GameState.choice_plan`).
4. **External-tool layer** — `fe_modding/tools.py` invokes WIT and FFmpeg from developer-provided `tools/` binaries or the per-user tool cache for disc operations and general video decoding. `fe_modding/emulator.py` finds and starts Dolphin on a built image; a chapter page's **Play in Dolphin...** button skips the build: it copies `extracted/sys` into `build/dolphin_run/` with a `main.dol` that boots straight into that chapter on the chosen difficulty with a fresh army (`game_code/chapter_jump.py`), links `files` there as a directory junction to `extracted/files`, and has Dolphin boot that folder's `sys/main.dol` (Dolphin plays an extracted disc tree directly). The project's own `main.dol` is never patched for it.

Editors operate directly on files in a project's `extracted/` directory. Building a project packages the current contents of that directory; there is no separate apply or staging step.

The two games share the architecture, but game-specific disc formats and build outputs are centralized in `fe_modding/games.py`. Path of Radiance builds to CISO and Radiant Dawn builds to WBFS. The desktop distribution currently targets Windows x64. Portable releases include Python and its dependencies; the first-run setup downloads WIT and optional FFmpeg. See [Windows releases](docs/app/windows-release.md).

## Detailed references

This file is the required high-level app overview. Agents should read the following files only when the task involves that part of the application:

- [Project lifecycle](docs/app/project-lifecycle.md) — project layout, supported disc inputs, extraction, and building.
- [Workspace and features](docs/app/workspace-and-features.md) — navigation, chapter handling, editors, viewers, and known user-facing limitations.
- [Script language](docs/app/script-language.md) — the `.fe9s` event-script language, the Scripts tab and the script command line.
- Script modding tutorial (`docs/app/script-tutorial.md`) — not written yet: progressive `.fe9s` lessons and the native/helper call index.
- AI scripts (`docs/app/ai-scripts.md`) — not written yet: Game Data › AI (CP) readable AI code (`formats/cp_ai_lang.py`, opcodes in `formats/cp_ops.py`), the raw view and the other `cp_data.bin` tabs.
- [Campaign-modding plan](docs/app/campaign-plan.md) — state of the work on supporting a full new campaign, and the checklist to run with a disc.
- [Making a new campaign](docs/app/modder-guide.md) — a modder's workflow and where each step happens in the app.
- [Formats and tools](docs/app/formats-and-tools.md) — format-module responsibilities, write-support boundaries, bundled tools, and test coverage.
- [Known bugs](docs/app/known-bugs.md) — confirmed but unfixed app defects.

Research history, reverse-engineering evidence, and unresolved game-format investigation belong in `research.md` and the relevant research notes, not in this app overview.
