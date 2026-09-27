"""The chapter map's working copy (``zmap/bmapNN/map.cmp`` - see
:mod:`fe_modding.formats.map_file`) and the actions on it.

It has no tab of its own: the chapter page's **Build** tab
(``map_builder.py``) shows and edits the map, and its windows
(``map_windows.py``: objects, map settings, 3D view) edit it through this
panel's API - ``edit_map()``, ``edit_pack()``, ``paint_terrain()``,
``snapshot()``/``restore()`` (undo) and the prop and water actions. The
chapter page keeps it among its panels for the unsaved-changes check.

Same ``.cmp`` -> ``pack`` -> ``map.bin`` pipeline as the deployment editor:
decompress and unpack on chapter select, edit, repack and recompress the
whole archive on save (the chapter's models are carried through unchanged).
Saving keeps the extracted ``map.cmp`` in the project's ``originals/``
folder.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from .. import map_props
from ..formats import fe8data, lz10, map_file, pak
from ..project import ModProject
from . import map_scene
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .model_viewer import (
    ModelPreviewDialog,
    _ImportReviewDialog,
    _TerrainImportOptions,
    _unpack,
    export_map_terrain_glb,
    load_named_model_set,
    map_terrain_name,
    replace_map_terrain_with_glb,
    terrain_mask_image,
)


class MapEditor(EditorPanel):
    display_name = "Map"

    def __init__(self, parent, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._current_path: Path | None = None
        self._pak_entries: list[pak.PakEntry] = []
        self._pak_contents: dict[str, bytes] = {}
        self._pak_reserved: dict[str, int] = {}
        self._map_bin_name = "map.bin"
        self._map_data: map_file.MapData | None = None
        self._terrain_grid = None
        self._dirty = False
        self._listeners: list = []
        self._load_terrain_catalog()
        self._load_chapter_list()

    # -- loading ----------------------------------------------------------------------
    def _load_chapter_list(self) -> None:
        self._chapter_paths = sorted(self._project.extracted_dir.glob("**/zmap/*/map.cmp"))

    def refresh_chapter_list(self) -> None:
        """Re-glob for chapter files - see dialogue_editor.py's version of
        this method for why it's needed."""
        self._load_chapter_list()

    def select_chapter(self, path: Path | None) -> None:
        if path is None or path not in self._chapter_paths:
            return
        if not self.confirm_navigate_away():
            return
        try:
            decompressed = lz10.decompress(path.read_bytes())
            entries = pak.read_pak_entries(decompressed)
            contents = {e.name: pak.read_pak_file_content(decompressed, e) for e in entries}
            if "map.bin" not in contents:
                raise map_file.MapFileError("The archive has no map.bin.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read chapter map", str(exc), parent=self)
            return
        self._current_path = path
        self._pak_entries = entries
        self._pak_contents = contents
        self._pak_reserved = {e.name: e.reserved for e in entries}
        self._dirty = False
        self._reparse()

    def _reparse(self) -> None:
        self._map_data = map_file.read_map_bytes(self._pak_contents[self._map_bin_name])
        self._terrain_grid = map_file.terrain_grid(self._pak_contents[self._map_bin_name])
        for callback in list(self._listeners):
            callback()

    def _changed(self, log_text: str | None) -> None:
        self._dirty = True
        self._reparse()
        if log_text:
            self._changelog.append(self.map_name, log_text)

    # -- shared API --------------------------------------------------------------------
    @property
    def map_data(self) -> map_file.MapData | None:
        return self._map_data

    @property
    def pak_contents(self) -> dict[str, bytes]:
        return self._pak_contents

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    @property
    def map_name(self) -> str:
        return self._current_path.parent.name if self._current_path is not None else ""

    @property
    def terrain_grid(self):
        """Each tile's terrain-type name, ``[x][y]`` (``map_file.terrain_grid``)."""
        return self._terrain_grid

    @property
    def terrain_types(self) -> list[fe8data.TerrainType]:
        return self._terrain_types

    def terrain_label(self, name: str) -> str:
        return self._terrain_labels.get(name, name)

    def terrain_choice_text(self, t: fe8data.TerrainType) -> str:
        label = self._terrain_labels.get(t.name, t.name)
        if t.impassable:
            stats = "impassable"
        else:
            stats = f"Avo {t.avoid} Def {t.defense} Res {t.resistance}" + (f" Heal {t.heal}%" if t.heal else "")
        return f"{label} [{t.name}] {stats}"

    def add_listener(self, callback) -> None:
        """``callback()`` runs after every change to the map (and after a
        chapter loads or saves)."""
        self._listeners.append(callback)

    def remove_listener(self, callback) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def edit_map(self, edit, log_text: str | None) -> None:
        """Run ``edit(files)`` on the chapter's files, where ``files["map.bin"]``
        is the working map.bin (the ``map_props`` convention), and keep the
        new map.bin. Raises what ``edit`` raises, leaving the map as it was."""
        files = {**self._pak_contents, "map.bin": self._pak_contents[self._map_bin_name]}
        edit(files)
        self._pak_contents[self._map_bin_name] = files["map.bin"]
        self._changed(log_text)

    def edit_pack(self, edit, log_text: str | None) -> None:
        """Run ``edit(entries, files)`` on copies of the chapter's pack entries
        and files (``files["map.bin"]`` is the working map.bin) and keep every
        file it adds or changes. Raises what ``edit`` raises, changing nothing."""
        entries = list(self._pak_entries)
        files = dict(self._pak_contents)
        files["map.bin"] = self._pak_contents[self._map_bin_name]
        edit(entries, files)
        self._pak_contents[self._map_bin_name] = files.pop("map.bin")
        self._pak_contents.update(files)
        for entry in entries[len(self._pak_entries):]:
            self._pak_reserved[entry.name] = 0
        self._pak_entries = entries
        self._changed(log_text)

    def paint_terrain(self, tiles, name: str) -> int:
        """Set ``tiles`` to terrain type ``name``; returns how many changed."""
        grid = self._terrain_grid
        changed = {tile: name for tile in tiles if grid is not None and grid[tile[0]][tile[1]] != name}
        if changed:
            self._pak_contents[self._map_bin_name] = map_file.set_tile_terrains(self._pak_contents[self._map_bin_name], changed)
            self._changed(f"Set {len(changed)} tiles to {self.terrain_label(name)} ({name})")
        return len(changed)

    def snapshot(self) -> tuple | None:
        """The map's files as they are now, for :meth:`restore` (undo)."""
        if self._current_path is None:
            return None
        return dict(self._pak_contents), list(self._pak_entries)

    def restore(self, state: tuple) -> None:
        contents, entries = state
        self._pak_contents = dict(contents)
        self._pak_entries = list(entries)
        for entry in entries:
            self._pak_reserved.setdefault(entry.name, 0)
        self._changed(None)

    def save(self) -> bool:
        return self._save()

    # -- props -------------------------------------------------------------------------
    def copy_prop(self, source_files: dict[str, bytes], source_name: str, name: str, source_label: str) -> str:
        """Copy a prop of another map in (``map_props.copy_prop``)."""
        text = f"Added prop {name} from {source_label}" + (f" ({source_name})" if name != source_name else "")
        self.edit_pack(lambda entries, files: map_props.copy_prop(source_files, source_name, entries, files, name), text)
        return name

    def view_model(self, parent, base_name: str) -> None:
        loaded = load_named_model_set(
            self._pak_contents,
            base_name,
            label=f"{self.map_name}/{base_name}",
            map_projection=map_scene.compute_map_texture_projection(base_name, self._map_data),
        )
        if loaded is None:
            messagebox.showinfo(
                "No 3D model",
                f"No .g/.gs/.ga files found for '{base_name}' in this chapter's map.cmp - "
                "it's likely an invisible logic-only marker, not a real placed model.",
                parent=parent,
            )
            return
        ModelPreviewDialog(parent, title=f"3D Model: {base_name}", loaded=loaded)

    def export_prop(self, parent, name: str) -> None:
        if f"{name}.gs" not in self._pak_contents:
            messagebox.showinfo("Export prop", f"{name} has no model.", parent=parent)
            return
        target = filedialog.asksaveasfilename(title="Export prop as glTF", defaultextension=".glb",
                                              initialfile=f"{name}.glb", filetypes=[("glTF binary", "*.glb")], parent=parent)
        if not target:
            return
        try:
            obj = next(o for o in self._map_data.build_desc if o.filename == name)
            if map_file.is_base_terrain_object(obj) and name not in self.water_names():
                raise ValueError("Export the terrain from the 3D Models panel (zmap/<map>).")
            Path(target).write_bytes(map_props.export_prop_glb(self._pak_contents, name))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not export", str(exc), parent=parent)

    def import_prop(self, parent, name: str | None = None) -> str | None:
        """Ask for a glTF and a name and import it as a prop (a new name adds
        an object, an existing one replaces its model). Returns the name."""
        if self._map_data is None:
            return None
        chosen = filedialog.askopenfilename(title="Import a prop", filetypes=[("glTF", "*.glb *.gltf"), ("All files", "*.*")],
                                            parent=parent)
        if not chosen:
            return None
        default = name or "".join(c if c.isalnum() else "_" for c in Path(chosen).stem)
        name = simpledialog.askstring("Prop name", "Object name (an existing name replaces its model):", initialvalue=default,
                                      parent=parent)
        if not name:
            return None
        gltf_data = Path(chosen).read_bytes()
        loop = True
        if map_props._has_skin_and_animation(gltf_data, Path(chosen).parent):
            loop = messagebox.askyesno("Animated prop", "The glTF is animated. Loop the animation (No: play it once)?", parent=parent)
        warnings = []
        try:
            self.edit_pack(
                lambda entries, files: warnings.extend(
                    map_props.import_prop(entries, files, gltf_data, name, Path(chosen).parent, loop=loop)),
                f"Imported prop {name} from {Path(chosen).name}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not import prop", str(exc), parent=parent)
            return None
        if warnings:
            messagebox.showinfo("Prop imported", "\n".join(warnings), parent=parent)
        return name

    # -- water -------------------------------------------------------------------------
    def water_names(self) -> list[str]:
        return map_props.water_names(self._pak_contents, self._map_data) if self._map_data is not None else []

    def _choose_water(self, parent, title: str):
        """The water object to act on: the map's only one, one the user
        names when there are several, None when there is none, False when
        the user cancels."""
        waters = self.water_names()
        if len(waters) <= 1:
            return waters[0] if waters else None
        name = simpledialog.askstring(title, "This map has several water objects: " + ", ".join(waters) + "\nWhich one?",
                                      initialvalue=waters[0], parent=parent)
        if not name:
            return False
        if name not in waters:
            messagebox.showerror(title, f"{name} is not one of this map's water objects.", parent=parent)
            return False
        return name

    def import_water(self, parent) -> None:
        if self._map_data is None:
            return
        chosen = filedialog.askopenfilename(title="Import a water surface", filetypes=[("glTF", "*.glb *.gltf"), ("All files", "*.*")],
                                            parent=parent)
        if not chosen:
            return
        name = self._choose_water(parent, "Import water")
        if name is False:
            return
        donor = None
        if name is None:
            wet = []
            for path in self._chapter_paths:
                if path == self._current_path:
                    continue
                try:
                    _entries, contents = map_props.read_map_container(path)
                    if map_props.water_names(contents, map_file.read_map_bytes(contents["map.bin"])):
                        wet.append(path.parent.name)
                except Exception:  # noqa: BLE001 - an unreadable chapter just isn't offered
                    continue
            source = simpledialog.askstring(
                "Add water", "This map has no water. Copy the water animation and textures from which map?\n"
                + ", ".join(wet), initialvalue=wet[0] if wet else "", parent=parent)
            if not source:
                return
            path = next((p for p in self._chapter_paths if p.parent.name == source), None)
            if path is None:
                messagebox.showerror("Add water", f"No map {source!r}.", parent=parent)
                return
            _entries, donor = map_props.read_map_container(path)
        warnings = []
        gltf_data = Path(chosen).read_bytes()
        try:
            self.edit_pack(
                lambda entries, files: warnings.extend(
                    map_props.import_water(entries, files, gltf_data, name, Path(chosen).parent, donor=donor)),
                f"Imported water from {Path(chosen).name}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not import water", str(exc), parent=parent)
            return
        if warnings:
            messagebox.showinfo("Water imported", "\n".join(warnings), parent=parent)

    def water_flow(self, parent) -> None:
        if self._map_data is None:
            return
        name = self._choose_water(parent, "Water flow")
        if name is False:
            return
        ga = self._pak_contents.get(f"{name}.ga") if name else None
        current = map_props.water_scroll(ga) if ga else None
        if current is None:
            messagebox.showinfo("Water flow", "This map has no water with a scroll table.", parent=parent)
            return
        answer = simpledialog.askstring(
            "Water flow",
            f"{name}: scroll speeds of the two water textures, u1 v1 u2 v2\n"
            "(the game multiplies them by the map's clock; negative runs the other way):",
            initialvalue=" ".join(f"{v:g}" for v in current), parent=parent)
        if not answer:
            return
        try:
            values = tuple(float(v) for v in answer.split())
            if len(values) != 4:
                raise ValueError("Give four numbers: u1 v1 u2 v2.")
            ga_bytes = map_props.set_water_scroll(ga, values)
        except ValueError as exc:
            messagebox.showerror("Water flow", str(exc), parent=parent)
            return
        self.edit_pack(lambda _entries, files: files.__setitem__(f"{name}.ga", ga_bytes), f"Water flow of {name} set to {values}")

    # -- terrain model (the same data as Assets > 3D Models, zmap/<map>) -----------------
    @property
    def models_label(self) -> str:
        """The map's set in Assets > 3D Models."""
        return f"zmap/{self.map_name}"

    def export_terrain(self, parent) -> None:
        """Export the land terrain as it is now (unsaved edits included), and
        its road/shore mask next to it, as the 3D Models panel does."""
        if self._map_data is None:
            return
        target = filedialog.asksaveasfilename(
            title="Export the terrain as glTF", defaultextension=".glb", initialfile=f"zmap_{self.map_name}.glb",
            filetypes=[("glTF binary", "*.glb")], parent=parent)
        if not target:
            return
        files = self._pak_contents
        written = [target]
        try:
            Path(target).write_bytes(export_map_terrain_glb(self._current_path, files))
            mask = terrain_mask_image(files, map_terrain_name(files, self._map_data, self.map_name))
            if mask is not None:
                mask_path = Path(target).with_name(Path(target).stem + "_mask.png")
                mask.convert("L").save(mask_path)
                written.append(str(mask_path))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not export the terrain", str(exc), parent=parent)
            return
        note = ""
        if len(written) > 1:
            note = ("\n\nThe mask covers 640 x 640 units (128 tiles) from the terrain's corner, x to the right and z "
                    "downwards: black shows the atlas through the first UV set, white through the second (roads, shores).")
        messagebox.showinfo("Exported", "Wrote " + "\n".join(written) + note, parent=parent)

    def import_terrain(self, parent) -> None:
        """Replace the land terrain with a glTF (``replace_map_terrain_with_glb``
        on the open map, unsaved edits included). The review dialog shows the
        change; applying it is a map edit like any other: Undo takes it back
        and Save Chapter writes it."""
        if self._map_data is None:
            return
        chosen = filedialog.askopenfilename(
            title=f"Replace the {self.models_label} terrain with a glTF model",
            filetypes=[("glTF", "*.glb *.gltf"), ("All files", "*.*")], parent=parent)
        if not chosen:
            return
        top = parent.winfo_toplevel()
        try:
            from ..formats import gltf_import

            has_map_base = any(m.name in gltf_import.UV2_MATERIALS
                               for m in gltf_import.read_gltf(Path(chosen).read_bytes(), Path(chosen).parent).materials)
            options = _TerrainImportOptions(parent, has_map_base)
            parent.wait_window(options)
            if options.result is None:
                return
            follow, conform, texturing, mask, keep_light = options.result
            top.config(cursor="watch")
            top.update_idletasks()
            try:
                result = replace_map_terrain_with_glb(
                    self._current_path, Path(chosen), follow, conform, texturing, mask, keep_light,
                    contents=(self._pak_entries, self._pak_contents))
            finally:
                top.config(cursor="")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not import the terrain", str(exc), parent=parent)
            return
        dialog = _ImportReviewDialog(
            parent, f"Replace the {self.models_label} terrain", self.models_label, self._current_path, result,
            accept_text="Apply to the map",
            footnote="Current: the saved map. Applied to the open map: Undo takes it back, Save Chapter writes it.")
        parent.wait_window(dialog)
        if not dialog.result:
            return
        entries, files = _unpack(self._current_path, result.outputs[self._current_path])
        self._set_pack(entries, files, f"Replaced the terrain with {Path(chosen).name}")

    def has_kept_original(self) -> bool:
        return self._current_path is not None and self._project.kept_original(self._current_path) is not None

    def restore_original(self, parent) -> None:
        """Load the map as extracted (the copy kept by the first save or
        import) in place of the open one, as an undoable edit."""
        original = self._project.kept_original(self._current_path) if self._current_path is not None else None
        if original is None:
            messagebox.showinfo("Restore original", "This map is still as extracted: nothing was saved over it.", parent=parent)
            return
        if not messagebox.askyesno(
                "Restore original map?",
                f"Put back {self.map_name}'s map as it was extracted: terrain, props, water, tile heights and terrain "
                "types? Undo takes it back; Save Chapter writes it.", parent=parent):
            return
        try:
            entries, files = _unpack(self._current_path, original.read_bytes())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not restore", str(exc), parent=parent)
            return
        self._set_pack(entries, files, "Restored the map as extracted")

    def _set_pack(self, entries: list[pak.PakEntry], files: dict[str, bytes], log_text: str) -> None:
        self._pak_entries = list(entries)
        self._pak_contents = dict(files)
        for entry in entries:
            self._pak_reserved[entry.name] = entry.reserved
        self._changed(log_text)

    # -- terrain types (painted from the Build tab) --------------------------------------
    def _load_terrain_catalog(self) -> None:
        files = self._project.extracted_dir / "files"
        self._terrain_types: list[fe8data.TerrainType] = []
        self._terrain_labels: dict[str, str] = {}
        try:
            self._terrain_types = fe8data.read_terrain_types((files / "FE8Data.bin").read_bytes())
            texts = fe8data.read_message_texts(files / "system.cmp") if (files / "system.cmp").is_file() else {}
        except Exception:  # noqa: BLE001 - the Build tab then lists names as stored
            texts = {}
        for t in self._terrain_types:
            self._terrain_labels[t.name] = texts.get(t.name_key) or t.name

    # -- save/dirty ----------------------------------------------------------------------
    def _save(self) -> bool:
        if self._current_path is None:
            return False
        try:
            files = [(entry.name, self._pak_contents[entry.name]) for entry in self._pak_entries]
            reserved = [self._pak_reserved[entry.name] for entry in self._pak_entries]
            new_compressed = lz10.compress(pak.pack_pak(files, reserved))
            self._project.write_keeping_original(self._current_path, new_compressed)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save chapter map", str(exc), parent=self)
            return False
        self._dirty = False
        self._changelog.append(self.map_name, "Saved map")
        for callback in list(self._listeners):
            callback()
        return True

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Discard changes?", "This chapter map has unsaved changes. Discard them?", parent=self)
