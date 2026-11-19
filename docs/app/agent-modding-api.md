# Driving the app from code (guide for agents)

This guide is for an AI agent, or any script, that helps a modder change *Path of Radiance* (PoR) or *Radiant Dawn* (RD) without clicking through the app. It says which functions do each job the app's pages do, how to call them so that the result is the same as an edit made in the app, and what differs between the two games.

The pages of the app are thin layers over the modules named here. A change made through these functions shows up in the app when the project is opened, goes into a build and into a `.tpatch` like any other edit.

Read [app.md](../../app.md) first for the architecture. The user-facing description of each page is in [Workspace and features](workspace-and-features.md) and in the [modding tutorials](../../wiki/modding/index.md).

The examples marked `# example:` are run by `App/tests/test_agent_guide.py`. Without a disc that test checks that every example parses and that every function this page names exists. With `FE9_EXTRACTED` and `FE10_EXTRACTED` set (see [app.md](../../app.md), Tests), it runs each example on a throwaway project over the extracted disc.

## Ground rules

1. **Use a source checkout** (see *Run from source* in the [README](../../README.md); the Windows release bundles Python and cannot be imported). Run from `App/` (or put `App/` on `sys.path`) with the app's requirements installed (`python -m pip install -r requirements.txt`: Pillow, NumPy...). None of the modules below need a display. `fe_modding.gui.fe8_session` and `fe_modding.gui.changelog` live under `gui/` but do not import Tk.
2. **Work on a project, never on the extracted disc.** Every read and write of a game file goes through the project's file layer (`ModProject.files`). New projects use the input/output layout: the vanilla files stay read-only and the mod's files go to `<project>/output/`. Read with `project.files_root / "<path under files/>"` and write with `project.write_keeping_original(path, data)` (or `project.write_logical(name, data)` for a named file such as `game_data`).
3. **Edit the game database through a data session.** `FE8Data.bin` (PoR) and `FE10Data.cms` (RD) are shared by many pages. Load them with `Fe8DataSession` or `Fe10DataSession`, change `session.data`, call `session.changed()` then `session.save()`. The PoR save also installs or removes the item-restriction code in `main.dol` when the item rules need it; writing the file yourself skips that.
4. **Most game files are LZ10-compressed packs.** A `.cmp` file is `lz10.compress(pak.pack_pak(...))`. Use `formats.lz10` and `formats.pak` as in the deployment example below, and keep each entry's `reserved` value when you repack.
5. **PoR reads some files from `system.cmp`.** The game loads `FE8Data.bin`, `Mess/common.m`, the face table and a few more from the copies inside `system.cmp`. Edit the loose files; `project.build()`, a patch and Play in Dolphin copy them in (`project.sync_system_archive()`). RD has no such archive.
6. **Text is stored as the game's bytes.** `formats.message` gives each message's text as a cp437 string. Turn it into readable text and back with `formats.game_text` (PoR: `from_raw`, `to_raw`) or `formats.fe10_message` (RD: `to_display`, `to_raw`, which also handle RD's control bytes).
7. **Check before you build.** `validator.validate_project(project)` is the **Tools › Check** page. An empty error list does not prove the game runs: test the chapter in Dolphin.
8. **Ask the profile what a game supports.** `project.profile.supports(feature)` answers for every feature in `game_profile.py` (`SHOPS`, `HUB`, `EXTENDED_FLAGS`...). `project.profile.data_dialect` is `"fe8"` on PoR and `"fe10"` on RD.

## Open or create a project

```python
import sys
sys.path.insert(0, r"C:\path\to\TelliusModding\App")

from fe_modding.games import Game
from fe_modding.project import LAYOUT_OVERLAY, ModProject

project = ModProject.load(r"C:\mods\My Mod")      # a project made in the app

# or a new one over a disc the user already extracted (Dolphin's "Extract Entire Disc")
project = ModProject.create(r"C:\mods", "My Mod", Game.PATH_OF_RADIANCE, layout=LAYOUT_OVERLAY)
project.use_input_folder(r"G:\ROM\por_work\GFEE01")  # the folder holding sys/ and files/
```

`use_input_folder` registers the folder as the project's vanilla input and marks its files read-only. `project.set_source(image)` then `project.extract()` start from a disc image instead (they need WIT: the app downloads it on first launch, **Download missing tools**). `Game.RADIANT_DAWN` is the other game.

Chapter ids are page ids: two digits on PoR (`"01"`, `"33"`), four on RD (`"0101"`, `"0407a"`, `"final"`; added chapters are `"0501"` and up). `chapters.list_chapter_ids(project)` lists them.

## Where each job is done

Columns: the page of the app, then the functions for each game. "Shared" means one function serves both games.

### Game data: characters, classes, items, skills

| Job | In the app | Path of Radiance | Radiant Dawn |
| --- | --- | --- | --- |
| Load, save the database | (every data page) | `gui.fe8_session:Fe8DataSession` | `gui.fe8_session:Fe10DataSession` |
| List records, find one by id, add a copy | Game Data, Characters › New | Shared: `game_adapter:DataAdapter` (`session.adapter.records`, `index_of`, `add_record`) | same |
| Change one field | Characters › Stats, Game Data tables | `formats.fe8data:patch_character_field`, `patch_class_field`, `patch_item_field`, `patch_skill_field` (their docstrings list the field names) | `formats.fe10data:patch_field`, `set_list` (field names: `formats.fe10data:field_defs`) |
| Remove or reorder a record | Game Data › Remove | `formats.fe8data:remove_record`, `move_record` | `formats.fe10data:remove_record` |
| Add a character with its name | Characters › New character | `campaign:add_character` | `campaign:add_character_fe10` |
| Stats per level | Characters › Growth | (growth rates are record fields) | `formats.fe10growth:set_line` |
| Supports | Characters › Supports | `formats.supports:read_support_lists`, `set_pair`, `write_support_lists`; one view for both games: `supports_model:PorSupports` | `formats.fe10data:set_support`; `supports_model:RdSupports` |
| Who can use which item | Game Data › Items › Restrictions | `formats.item_rules:read_item_rules`, `write_item_rules` | not available |
| Terrain types | Game Data › Terrain | `formats.fe8data:patch_terrain_stats`, `patch_terrain_names` | `formats.fe10data:own_terrain_block`, then `patch_field` on kind `terrain` |
| Bulk edit in a spreadsheet | Game Data › Export/Import Excel | `excel_io:export_fe8`, `import_fe8` | `excel_io:export_fe10`, `import_fe10` |
| Colour variants of a character or class | Characters › Colour variant | Shared: `colour_variants:plan_character_variant`, `plan_class_variant`, `apply_variant` | same |

### Chapters, maps and deployments

| Job | In the app | Path of Radiance | Radiant Dawn |
| --- | --- | --- | --- |
| A chapter's files | Chapter page | Shared: `chapters:chapter_paths`, `chapter_phases`, `phase_paths`; `game_profile:chapter_mess_path` | same |
| Add a chapter (copy of another) | Chapters › Add chapter | Shared: `DataAdapter.add_story_chapter` (calls `chapters:add_story_chapter`) | same (calls `chapters_fe10:add_story_chapter`) |
| Several chapters and characters at once | Chapters › New campaign | Shared: `DataAdapter.add_campaign` (`campaign:add_campaign`) | same (`campaign:add_campaign_fe10`) |
| Delete an added chapter | Chapter page › Delete | `chapters:remove_story_chapter` | `chapters_fe10:remove_story_chapter` |
| Story order (which chapter follows which) | Chapters › Story flow | Shared: `game_code.story_flow:open_story_flow` (`set_next`, `insert_after`, `set_order`, `remove`) | same |
| Chapter record (goal, music, armies) | Chapter › Chapter data | Shared: `DataAdapter.chapter_sections`, `write_chapter_value` | same |
| Deployments: units, positions, items, AI | Chapter › Units | `formats.dispo:parse_dispo`, `build_dispo`, `add_unit`, `remove_unit`, `place_unit`, `move_unit` (inside `zmap/bmapNN/dispos.cmp`) | same functions, on the loose `zmap/bmapNNNN/dispos_<n/h/c>.bin` |
| Empty a chapter's enemies | New campaign option | `campaign:blank_chapter_units` | same |
| Terrain of each tile, map size | Chapter › Build › Terrain | `formats.map_file:terrain_grid`, `set_tile_terrains`, `resize_grid` | same |
| Props on the map (houses, rocks, a new model) | Chapter › Build › Props | `map_props:read_map_container`, `import_prop`, `copy_prop`, `place_prop`, `move_instance`, `remove_instance`, `write_map_container` | same |
| Paint the ground texture | Chapter › Build › Paint | `terrain_paint:compile_paint`, `build_atlas` (see [Paint terrain](../../wiki/modding/22-paint-terrain-and-blocking.md)) | not available |
| Water | Chapter › Build › Water | `map_props:import_water`, `remove_water` | same |
| Battle backgrounds per terrain | Chapter › Battle backgrounds | Shared: `DataAdapter.battle_scenery_rows`, `write_battle_scenery_rows` | same |
| A hub chapter (free roam with links) | Chapters › Create hub | `hub_creation:create_chapter`, then `hub:install` with a `hub:HubSetup` | `hub_creation_fe10:create_chapter`, then `hub_fe10:install` |
| Shops and forges | Chapter › Shops | `formats.shop:parse_shop`, `build_shop`, `add_chapter`, `set_forge_item` (`shop/shopitem_<n/h/m>.bin`) | same (`Shop/shopitem_<n/h/m>.bin`) |

### Events, text and AI

| Job | In the app | Path of Radiance | Radiant Dawn |
| --- | --- | --- | --- |
| Event scripts as source | Chapter › Script | Shared: `script_sources:chapter_script`, `load`, `save` (compiles `.fe9s`; see [Script language](script-language.md) and the [call index](script-call-reference.md)) | same |
| Compile or decompile one file | command line | Shared: `python -m fe_modding.formats.cmb decompile/compile`; `formats.cmb.compiler:compile_source`, `formats.cmb.decompiler:decompile` | same |
| Event flags | Game Data › Flags | Shared: `formats.event_flags:global_flags`, `flag_uses`, `remove_unused_registration` | same |
| Flags past the game's slots | Flags › Extended storage | `game_code.extended_flags` (see [EXTENDED_FLAGS.md](../../App/docs/EXTENDED_FLAGS.md)) | not available |
| Dialogue and every other text | Chapter › Dialogue, Text | Shared: `formats.message:read_messages_path`, `read_text_order_path`, `write_messages`, `Message`; `formats.game_text:from_raw`, `to_raw` | same reader and writer; `formats.fe10_message:to_display`, `to_raw`, `plain_text` |
| Dialogue scenes step by step | Dialogue editor | `formats.fe9_message_scene:decompile`, `compile_steps` | `formats.fe10_message:decompile`, `compile_steps` |
| Staff roll | Assets › Staff credits | `formats.staffroll:read_staffroll_path`, `build_staffroll` | `formats.fe10_staffroll:read_rd_staffroll`, `build_rd_staffroll` |
| Enemy AI scripts | Game Data › AI | Shared: `formats.cp_data:parse_cp_data`, `build_cp_data`; readable code: `formats.cp_ai_lang:decompile`, `compile_source` (see [AI scripts](ai-scripts.md)) | same |
| Tutorials | Assets › Tutorials | Shared: `formats.tut_data:read_tut_data`, `build_tut_data` | same |
| Fonts | Assets › Fonts | `formats.fe9_font:import_truetype`, `rebuild` | same |

### Graphics, models, sound and video

| Job | In the app | Path of Radiance | Radiant Dawn |
| --- | --- | --- | --- |
| Portraits | Assets › Portraits | `portraits:load_faces`, `add_portrait`, `update_face`, `remove_portrait` | `formats.fe10_faces:read_face_data`, `add_face_record`, `patch_face_record` |
| Any texture (`.tpl`) | Assets › Graphics | Shared: `formats.tpl:read_tpl_images`, `replace_image`, `build_tpl`, `append_images` | same |
| Item and skill icons | Assets › Icons | Shared: `formats.icons:read_icon_images`, `item_icon` | same |
| New battle or map model slot | Assets › Model slots | Shared: `model_slots:clone_battle_model`, `assign_battle_model`, `clone_map_model`, `assign_map_model` | same |
| Import a 3D model (glTF) | Assets › 3D Models | Shared: `formats.gltf_import:import_static_model`, `import_skinned_model`, `import_animation` | same |
| Battle tables (weapons, units, cameras) | Assets › Battle ... | `formats.zdbx:read_zdbx_archive`, `build_zdbx_archive`, `set_job_model` | `formats.fe10_battle:read_fe10_battle`, `build_fe10_battle`, `update_battle_record` |
| Particle effects | Assets › Effects | Shared: `formats.particle_editor:edit_emitter`, `add_emitter` (see [PARTICLE_EDITOR.md](../../App/docs/PARTICLE_EDITOR.md)) | same |
| Music | Assets › Music | `formats.stm:wav_path_to_stm_audio`, `write_stm` (replace a `Sound/*.stm` track) | `rd_music:add_track`, `add_cue`, `remove_track`; `formats.brstm:wav_path_to_brstm_audio`, `write_brstm` |
| Sound effects | Assets › Sound effects | (see [Sound effects](../../wiki/modding/48-sound-effects.md)) | `rd_music:add_sfx`, `remove_sfx` |
| Videos | Assets › Videos | Shared: `formats.thp:encode_thp`, `read_info` | same |

### Game code, saves, testing and sharing

| Job | In the app | Path of Radiance | Radiant Dawn |
| --- | --- | --- | --- |
| `main.dol` patches and tunables | Tools › Game Code | Shared: `game_code.editor:CodeEditor` (`set_patch`, `set_value`, `save`) | same |
| Check the project | Tools › Check | Shared: `validator:validate_project` | same |
| Play a chapter without the game | Chapter › Build › Play... | Shared: `playthrough.loader:load_world`, `playthrough.setup:initial_state`, `playthrough.simulation:Simulation` | same |
| Battle forecast and simulation | Tools › Battle Simulator | Shared: `battle_sim.engine:simulate` | same |
| Boot a chapter in Dolphin | Play in Dolphin (F5) | Shared: `emulator:prepare_chapter_run`, `emulator:launch`; unattended runs: `tools/chapter_sweep`, `tools/dolphin_input.py` (see [app.md](../../app.md)) | same |
| Save files | Tools › Saves | `formats.save_file` | `formats.save_file_fe10` |
| Build the disc image | Disc & Patch › Build | Shared: `ModProject.build` | same (needs WIT) |
| Make or apply a `.tpatch` | Disc & Patch › Create patch | Shared: `patch:create_project_patch`, `patch:apply_patch_to_disc` | same |
| Export the mod as text for version control | Disc & Patch › Export as text | Shared: `text_export:export_project` | same |

## Examples

Every example below starts from an open `project`. They are written to run on both games: `rd` picks the game.

### Change a character's level and stats

```python
# example: edit-character
from fe_modding.formats import fe8data, fe10data
from fe_modding.gui.changelog import ChangeLog
from fe_modding.gui.fe8_session import Fe8DataSession, Fe10DataSession

rd = project.profile.data_dialect == "fe10"
session = (Fe10DataSession if rd else Fe8DataSession)(project, ChangeLog())
index = session.adapter.index_of("character", "PID_MICAIAH" if rd else "PID_IKE")
if rd:
    session.data = fe10data.patch_field(session.data, "character", index, "level", 5)
    session.data = fe10data.patch_field(session.data, "character", index, "bonus_str", 3)
else:
    session.data = fe8data.patch_character_field(session.data, index, "level", 5)
    session.data = fe8data.patch_character_field(session.data, index, "stat_bonus1", 3)  # 0 HP, 1 Str...
session.changed()   # reparses session.fe8 / session.fe10
session.save()
```

After `changed()`, `session.fe8.characters[index]` (PoR) or `session.fe10.characters[index].values` (RD) shows the new values.

### Add a weapon and name it

```python
# example: add-item
from fe_modding.formats import fe8data, fe10data, message
from fe_modding.game_profile import message_prefix
from fe_modding.gui.changelog import ChangeLog
from fe_modding.gui.fe8_session import Fe8DataSession, Fe10DataSession

rd = project.profile.data_dialect == "fe10"
session = (Fe10DataSession if rd else Fe8DataSession)(project, ChangeLog())
template = session.adapter.index_of("item", "IID_IRONSWORD")
session.data, index = session.adapter.add_record("item", "IID_AGENTBLADE", template)
if rd:
    session.data = fe10data.patch_field(session.data, "item", index, "miid", "MIID_AGENTBLADE")
    session.data = fe10data.patch_field(session.data, "item", index, "might", 9)
else:
    session.data = fe8data.add_label(session.data, "MIID_AGENTBLADE")   # PoR item keys must be in the pool first
    session.data = fe8data.patch_item_field(session.data, index, "miid", "MIID_AGENTBLADE")
    session.data = fe8data.patch_item_field(session.data, index, "might", 9)
session.changed()
session.save()

# the name the game shows: a message in the common text file
path = project.files_root / "Mess" / f"{message_prefix(project)}common.m"
messages = [m for m in message.read_messages_path(path) if m.speaker != "MIID_AGENTBLADE"]
messages.append(message.Message("MIID_AGENTBLADE", "Agent Blade"))
project.write_keeping_original(path, message.write_messages(messages, message.read_text_order_path(path)))
```

A new record is always a copy, so it keeps the template's other fields (on RD, every new record must copy one). On RD, `campaign.add_character_fe10` also writes the name to the Japanese `common.m`; do the same when the mod targets both.

### Add a character

```python
# example: add-character
from fe_modding import campaign
from fe_modding.gui.changelog import ChangeLog
from fe_modding.gui.fe8_session import Fe8DataSession, Fe10DataSession

rd = project.profile.data_dialect == "fe10"
session = (Fe10DataSession if rd else Fe8DataSession)(project, ChangeLog())
warnings = []
if rd:
    spec = campaign.CharacterSpec("PID_AGENT", template="PID_MICAIAH", name="Agent")
    session.data = campaign.add_character_fe10(project, session.data, spec, warnings)
else:
    spec = campaign.CharacterSpec("PID_AGENT", template="PID_IKE", name="Agent")
    session.data = campaign.add_character(project, session.data, spec, warnings)
session.changed()
session.save()
```

The name goes into the common text file at once. Give the character a portrait (`fid` field) and put them in a deployment to see them in a chapter.

### Edit a line of dialogue

```python
# example: edit-dialogue
import dataclasses

from fe_modding.formats import fe10_message, game_text, message
from fe_modding.game_profile import chapter_mess_path

rd = project.profile.message_dialect == "fe10"
path = chapter_mess_path(project, "0101" if rd else "01")
messages = message.read_messages_path(path)
order = message.read_text_order_path(path)
first = messages[0]
if rd:
    readable = fe10_message.to_display(first.text)       # RD commands shown as <...> notation
    raw = fe10_message.to_raw(readable.replace("the", "THE", 1))
else:
    readable = game_text.from_raw(first.text)            # PoR $ commands stay as text
    raw = game_text.to_raw(readable.replace("the", "THE", 1))
messages[0] = dataclasses.replace(first, text=raw)      # a Message is frozen
project.write_keeping_original(path, message.write_messages(messages, order))
```

`message.speaker` is the message key (`MS_01_OP01`...). Scripts show a message by that key, so a new key also needs a script line that shows it. The `$` commands of PoR are described in [Inline text and fonts](../../wiki/modding/39-inline-text-and-fonts.md).

### Change a unit in a deployment

```python
# example: edit-deployment
from fe_modding.formats import dispo, lz10, pak

rd = project.profile.data_dialect == "fe10"
folder = project.files_root / "zmap" / ("bmap0101" if rd else "bmap01")

def edit(doc):
    section = next(s for s in doc.sections if not s.is_link and s.units)
    unit = section.units[0]
    unit[dispo.FIELD["level"]] = 10
    dispo.move_unit(unit, unit[dispo.FIELD["pos_x"]], unit[dispo.FIELD["pos_y"]])  # same tile: shows the call
    return doc

if rd:   # one loose file per difficulty
    path = folder / "dispos_n.bin"
    project.write_keeping_original(path, dispo.build_dispo(edit(dispo.parse_dispo(path.read_bytes()))))
else:    # every difficulty inside dispos.cmp
    path = folder / "dispos.cmp"
    unpacked = lz10.decompress(path.read_bytes())
    entries = pak.read_pak_entries(unpacked)
    files = []
    for entry in entries:
        content = pak.read_pak_file_content(unpacked, entry)
        if entry.name == "dispos_n.bin":
            content = dispo.build_dispo(edit(dispo.parse_dispo(content)))
        files.append((entry.name, content))
    project.write_keeping_original(path, lz10.compress(pak.pack_pak(files, [e.reserved for e in entries])))
```

Fields are named in `dispo.FIELD_NAMES` (`pid`, `jid`, `item0`..., `seq_attack`, `level`, `faction`...); pointer fields hold label strings, so any `PID_`, `JID_` or `IID_` can be written. A chapter with several maps has one folder per phase (`chapters.chapter_phases`).

### Put an item on sale

```python
# example: edit-shop
from fe_modding.formats import shop

path = project.profile.shop_path(project.files_root, "n")
doc = shop.parse_shop(path.read_bytes())
chapter = doc.chapters()[0]
armory = doc.shop("W", chapter)          # "W" armory, "I" vendor, "F" forge (shop.section_name)
armory.items.append("IID_STEELSWORD")
project.write_keeping_original(path, shop.build_shop(doc))
```

### Edit a chapter's event script

```python
# example: edit-script
from fe_modding import script_sources

path = script_sources.chapter_script(project, "0101" if project.profile.script_dialect == "fe10" else "01")
script = script_sources.load(project, path)
source = script.source.replace("\n", "\n# edited by an agent\n", 1)  # change the source text here
result = script_sources.save(project, script, source)              # raises CompileError with the line
```

`save` compiles the source onto the original file, writes the `.cmb` and keeps the source with its comments in `script_sources/`. The language is in [Script language](script-language.md), every game function in the [call index](script-call-reference.md), and recipes in [Event recipes](../../wiki/modding/35-event-recipes.md).

### Add a chapter to the story

```python
# example: add-chapter
from fe_modding.game_code.story_flow import open_story_flow
from fe_modding.gui.changelog import ChangeLog
from fe_modding.gui.fe8_session import Fe8DataSession, Fe10DataSession

rd = project.profile.data_dialect == "fe10"
session = (Fe10DataSession if rd else Fe8DataSession)(project, ChangeLog())
flow, why = open_story_flow(project)          # None and the reason when main.dol is not supported
new_id = session.adapter.free_chapters(project)[0]
source = session.adapter.chapter_templates(project)[0]
after = flow.order()[0]                       # the new chapter is played after this one
session.data, warnings = session.adapter.add_story_chapter(project, source, new_id, "Agent Test", after, flow)
session.changed()
session.save()
```

The new chapter is a copy of `source` (map, deployments, script and dialogue). Change it with the examples above. `flow.set_next`, `flow.insert_after` and `flow.set_order` change the order later and save `main.dol` at once.

### Check, build and share

```python
# example: check
from fe_modding import validator

report = validator.validate_project(project)
for issue in report.errors:   # report.issues also holds the warnings
    print(issue)           # "error: <file>: <what is wrong>"
```

```python
from fe_modding import patch

image = project.build()                                     # build/<name>.ciso (PoR) or .wbfs (RD)
patch.create_project_patch(project, project.directory / "my-mod.tpatch")
```

Building Radiant Dawn and extracting a disc image need WIT (the app's **Download missing tools**), so run them on the modder's Windows machine, where the app found its tools. To test a chapter, have the modder press **Play in Dolphin** on its page, or use the unattended tools listed in [app.md](../../app.md).

## Pitfalls

- **One session per database.** Two sessions on the same project each save their own copy: the last save wins. Keep one session for the whole job, and reload it (`session.load()`) when another tool wrote the file.
- **Labels must exist where the game looks them up.** A `PID_`, `JID_`, `IID_` or `SID_` in a deployment, shop or script must be a record of the database; an `MPID_`, `MIID_` or `MS_` key must be a message of a loaded text file. `validator.validate_project` reports the broken ones.
- **Copies keep the template's links.** A copied character keeps the template's portrait, animations and supports, and a copied chapter keeps its source's script events. Change what should differ.
- **Skills cannot be added on PoR** (the game refers to them by position); edit the existing ones.
- **RD chapter ids.** Retail RD chapters keep their place in the story; only added chapters (`0501` and up) can be deleted. Take a retail chapter out of the story with the story flow instead.
- **Regions.** The US discs (`GFEE01`, `RFEE01`) are the tested ones. The app reads the European and Japanese discs, but text files and some tables differ (`game_profile.message_prefix`, `fe10_message.encoding_for`).
- **Know what is decoded.** [What you can edit](../../wiki/meta/what-you-can-edit.md) lists the limits of version 1.0, [Known limits](../../wiki/modding/63-known-limits.md) the ones a modder meets, and [Known bugs](known-bugs.md) the open defects.
