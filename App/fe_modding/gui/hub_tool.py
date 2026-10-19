"""The hub chapter's own controls: its links to other chapters, placed on the Build tab's map.

A hub is an ordinary chapter (map, units, terrain, script, dialogue: every tab
works on it) with one more tool on the Build tab. Each link is an action tile
(Arrive enters the chapter, Visit shows its description) and the return point
the avatar comes back to after that chapter. The links are kept in a draft
(``hub_draft.json``) until Install writes the hub's events, flags and routing.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import chapters, hub
from ..formats import fe8data
from ..game_code.chapter_flow import GAME_CLEARED
from ..hub_creation import MAX_SIZE, MIN_SIZE
from .widgets import info, tip

LINK_COLOR = "#7bb85c"
RETURN_COLOR = "#5fb3e6"


class HubTool(ttk.Frame):
    """The Build tab's Hub tool, shown on the hub chapter only."""

    def __init__(self, parent, builder) -> None:
        super().__init__(parent)
        self._builder = builder
        self.data: dict | None = None  # the working setup (hub.working_setup)
        self.current: int | None = None  # selected link
        self.placing: str | None = None  # "action" | "return": the next map click places it
        self._titles: dict[str, str] = {}
        self._choices: dict[str, int] = {}
        self._description_after = None

        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text="Hub", font=("Segoe UI", 11, "bold")).pack(side="left")
        info(head, "This chapter is the campaign's hub: the avatar walks between action tiles, one per linked "
                   "chapter. Arrive on a tile enters that chapter; Visit shows its description and stays. After "
                   "the chapter the game comes back here and the avatar stands on the link's return point.\n\n"
                   "Everything else is an ordinary chapter: paint terrain, place props and decoration units, "
                   "write events in the Script tab. The player army must stay the avatar alone.").pack(
            side="left", padx=(6, 0))
        self._status = ttk.Label(head, text="", style="Muted.TLabel")
        self._status.pack(side="right")

        storage_row = ttk.Frame(self)
        storage_row.pack(fill="x", pady=(8, 0))
        ttk.Label(storage_row, text="Flag storage").pack(side="left")
        self._storage = tk.StringVar(value="Extended")
        self._storage_box = ttk.Combobox(storage_row, textvariable=self._storage,
                                       values=("Extended", "Vanilla"), state="readonly", width=12)
        self._storage_box.pack(side="left", padx=(6, 0))
        self._storage_box.bind("<<ComboboxSelected>>", lambda e: self._storage_changed())
        info(storage_row, "Extended gives the hub its own saved storage and frees vanilla flag slots. "
                         "Initial installation or migration requires a fresh playthrough. Existing saves "
                         "are not converted. Extended installation remains unavailable until regional "
                         "in-game validation passes.").pack(side="left", padx=(6, 0))

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(8, 0))
        tip(ttk.Label(row, text="Opens after"),
            "The hub opens once this chapter is won, the first time only. From then on every chapter "
            "ends back in the hub, until a story event clears the HUB_ACTIVE flag.").pack(side="left")
        self._activation = tk.StringVar()
        self._activation_box = ttk.Combobox(row, textvariable=self._activation, state="readonly", width=30)
        self._activation_box.pack(side="left", padx=(6, 0))
        self._activation_box.bind("<<ComboboxSelected>>", lambda e: self._activation_changed())
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(4, 0))
        tip(ttk.Label(row, text="Avatar"),
            "The character the player walks around the hub. It starts on its unit's tile in the player army "
            "(move it with the Select tool) and must not appear in any other chapter.").pack(side="left")
        self._avatar = ttk.Label(row, text="", style="Muted.TLabel")
        self._avatar.pack(side="left", padx=(6, 0))

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(4, 0))
        tip(ttk.Label(row, text="Ground"),
            "Change the solid color or image of a hub created with Blank map. Other map edits are preserved.").pack(
            side="left")
        ttk.Button(row, text="Edit ground…", command=self._edit_ground).pack(side="left", padx=(6, 0))

        tip(ttk.Label(self, text="Chapter links"),
            "Green square: the action tile. Blue circle: where the avatar stands when it comes back from that "
            "chapter. Drag either one to move it. Applying hub setup places a visible Arrive marker "
            "on each action tile in game.").pack(anchor="w", pady=(10, 2))
        self._list = tk.Listbox(self, height=7, exportselection=False, activestyle="none")
        self._list.pack(fill="x")
        self._list.bind("<<ListboxSelect>>", lambda e: self._list_selected())
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(4, 0))
        self._new_link = tk.StringVar()
        self._new_box = ttk.Combobox(row, textvariable=self._new_link, state="readonly", width=30)
        self._new_box.pack(side="left", fill="x", expand=True)
        tip(ttk.Button(row, text="Add link", command=self._add), "Then click its action tile, then its return "
                                                                  "point on the map.").pack(side="left", padx=(6, 0))

        self._link = ttk.Frame(self)
        grid = ttk.Frame(self._link)
        grid.pack(fill="x")
        self._place_labels = {}
        for r, (which, label, help_text) in enumerate((
                ("action", "Action tile", "Arrive and Visit commands on this tile."),
                ("return", "Return point", "The avatar's tile when it comes back from the chapter."))):
            tip(ttk.Label(grid, text=label), help_text).grid(row=r, column=0, sticky="w", pady=1)
            value = ttk.Label(grid, text="", width=10)
            value.grid(row=r, column=1, sticky="w", padx=(6, 0))
            self._place_labels[which] = value
            ttk.Button(grid, text="Place", command=lambda w=which: self._start_placing(w)).grid(
                row=r, column=2, sticky="w", padx=(6, 0))
        tip(ttk.Label(self._link, text="Description"),
            "Shown by Visit (one line or two, 240 characters at most). Empty: no Visit command.").pack(
            anchor="w", pady=(6, 0))
        self._description = tk.Text(self._link, height=3, width=36, wrap="word", undo=True)
        self._description.pack(fill="x")
        self._description.bind("<<Modified>>", lambda e: self._description_modified())
        ttk.Button(self._link, text="Remove link", command=self._remove).pack(anchor="w", pady=(6, 0))
        self._hint = ttk.Label(self, text="", style="Muted.TLabel", wraplength=300, justify="left")
        self._hint.pack(anchor="w", pady=(6, 0))

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(10, 0))
        tip(ttk.Button(row, text="Install hub", style="Accent.TButton", command=self._install),
            "Writes the hub's events in this chapter's script, the Visit texts, the hub flags in startup.cmb, "
            "the 'opens after' event and the executable's chapter routing. Run it again after changing the "
            "links.").pack(side="left")

    # -- loading -----------------------------------------------------------------------------
    def load(self, chapter_id: str | None) -> bool:
        """Show ``chapter_id``'s hub setup; False when that chapter isn't the hub."""
        project = self._builder.project
        data = hub.working_setup(project) if chapter_id and chapter_id.isdigit() else None
        if data is None or data["chapter"] != int(chapter_id):
            self.data = None
            return False
        self.data = data
        installed = hub.saved_setup(project)
        storage = data.get("storage") or (installed.get("storage", "vanilla") if installed else "extended")
        if installed and installed.get("storage") == "extended":
            storage = "extended"
        self.data["storage"] = storage
        self._storage.set(storage.title())
        self._storage_box.configure(values=("Extended",) if installed and installed.get("storage") == "extended"
                                    else ("Extended", "Vanilla"))
        self.data.setdefault("destinations", [])
        self.current = None
        self.placing = None
        self._titles = chapters.chapter_titles(project)
        ids = chapters.list_chapter_ids(project)
        session = self._builder.fe8_session
        records = ({r.chapter_id for r in fe8data.read_chapter_data(session.data)}
                   if session is not None and getattr(session, "available", False) else None)
        playable = [cid for cid in ids if cid.isdigit() and int(cid) != data["chapter"]
                    and (records is None or int(cid) in records)]
        activation = {self._label(cid): int(cid) for cid in playable if int(cid) != GAME_CLEARED}
        self._activation_choices = activation
        self._activation_box.configure(values=list(activation))
        self._activation.set(next((label for label, n in activation.items() if n == data["activation_chapter"]),
                                  ""))
        self._choices = {}
        for cid in playable:
            if int(cid) in (29, GAME_CLEARED):
                continue
            paths = chapters.chapter_paths(project, cid)
            if paths.script is not None and paths.map is not None and paths.deployment is not None:
                self._choices[self._label(cid)] = int(cid)
        self._avatar.configure(text=f"{self._builder.character_name(data['avatar_pid'])} ({data['avatar_pid']})")
        self._fill()
        return True

    def _label(self, cid) -> str:
        cid = f"{int(cid):02d}"
        return f"{cid} · {chapters.chapter_display_title(cid, self._titles)}"

    def _fill(self) -> None:
        self._list.delete(0, "end")
        for d in self.data["destinations"]:
            self._list.insert("end", self._row(d))
        used = {d["chapter"] for d in self.data["destinations"]}
        free = [label for label, n in self._choices.items() if n not in used]
        self._new_box.configure(values=free)
        if self._new_link.get() not in free:
            self._new_link.set(free[0] if free else "")
        if self.current is not None:
            self._list.selection_set(self.current)
        self._show_link()
        self._update_status()

    def _row(self, d: dict) -> str:
        where = "click the map to place" if d.get("x") is None else f"({d['x']}, {d['y']})"
        return f"{self._label(d['chapter'])} — {where}"

    def _update_status(self) -> None:
        project = self._builder.project
        configuration = hub.saved_setup(project)
        installed = configuration is not None
        text = ("Changes not installed" if hub.draft_path(project).is_file() and installed else
                "Installed" if installed else "Not installed yet")
        if installed and configuration.get("storage") == "extended":
            from ..game_code.extended_flag_installation import inspect_project, RuntimeState
            status = inspect_project(project)
            text = (text + " · verified extended" if status.state == RuntimeState.MATCHING else
                    "Extended: " + status.state.value)
        self._status.configure(text=text)

    # -- editing ------------------------------------------------------------------------------
    def _storage_changed(self):
        if self.data is not None:
            self.data["storage"] = self._storage.get().lower()
            self._save()

    def _save(self) -> None:
        hub.save_draft(self._builder.project, self.data)
        self._update_status()

    def _activation_changed(self) -> None:
        chapter = self._activation_choices.get(self._activation.get())
        if chapter is not None and chapter != self.data["activation_chapter"]:
            self.data["activation_chapter"] = chapter
            self._save()

    def _edit_ground(self) -> None:
        from .hub_dialog import EditHubGroundDialog
        replace_custom = False
        try:
            appearance = self._builder.hub_ground_appearance()
        except Exception as exc:  # noqa: BLE001 - format and archive errors are presented together
            if not messagebox.askyesno(
                    "Replace 3D terrain?",
                    f"{exc}\n\nReplace this terrain model with a flat image plane? This permanently removes "
                    "the terrain geometry when the chapter is saved. Tactical tiles and hub links are preserved, "
                    "but height-shaped props may float or intersect the new plane.",
                    icon="warning", parent=self):
                return
            from ..hub_creation import DEFAULT_GROUND_COLOR, GroundAppearance
            appearance = GroundAppearance(DEFAULT_GROUND_COLOR, None, False)
            replace_custom = True
        dialog = EditHubGroundDialog(self, appearance, initial_mode="image" if replace_custom else None)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        color, image_path, tiled, use_image = dialog.result
        try:
            self._builder.edit_hub_ground(color, image_path, tiled, use_image, replace_custom)
        except Exception as exc:  # noqa: BLE001 - Pillow and map-format errors are presented together
            messagebox.showerror("Could not edit hub ground", str(exc), parent=self)

    def _add(self) -> None:
        chapter = self._choices.get(self._new_link.get())
        if chapter is None:
            return
        self.data["destinations"].append({"chapter": chapter, "x": None, "y": None, "return_x": None,
                                          "return_y": None, "description": ""})
        self.current = len(self.data["destinations"]) - 1
        self._save()
        self._fill()
        self._start_placing("action")

    def _remove(self) -> None:
        if self.current is None:
            return
        self.data["destinations"].pop(self.current)
        self.current = None
        self.placing = None
        self._save()
        self._fill()
        self._builder.hub_changed()

    def _list_selected(self) -> None:
        selected = self._list.curselection()
        self.select(selected[0] if selected else None)

    def select(self, index: int | None) -> None:
        self.current = index
        self.placing = None
        self._list.selection_clear(0, "end")
        if index is not None:
            self._list.selection_set(index)
            self._list.see(index)
        self._show_link()
        self._builder.hub_changed()

    def _show_link(self) -> None:
        if self.current is None or self.current >= len(self.data["destinations"]):
            self.current = None
            self._link.pack_forget()
            self._hint.configure(text="Select a link, or add one.")
            return
        d = self.data["destinations"][self.current]
        for which, (kx, ky) in (("action", ("x", "y")), ("return", ("return_x", "return_y"))):
            self._place_labels[which].configure(text="not placed" if d.get(kx) is None else f"({d[kx]}, {d[ky]})")
        self._link.pack(fill="x", pady=(8, 0), before=self._hint)
        self._description.edit_modified(False)
        if self._description.get("1.0", "end-1c") != d.get("description", ""):
            self._description.delete("1.0", "end")
            self._description.insert("1.0", d.get("description", ""))
            self._description.edit_modified(False)
        self._hint.configure(text=self._placing_text())

    def _placing_text(self) -> str:
        if self.placing == "action":
            return "Click the map: the link's action tile."
        if self.placing == "return":
            return "Click the map: where the avatar comes back."
        return ""

    def _description_modified(self) -> None:
        if not self._description.edit_modified() or self.current is None:
            return
        self._description.edit_modified(False)
        self.data["destinations"][self.current]["description"] = " ".join(
            self._description.get("1.0", "end-1c").split("\n"))
        if self._description_after is not None:
            self.after_cancel(self._description_after)
        self._description_after = self.after(400, self._save)

    def _start_placing(self, which: str) -> None:
        if self.current is None:
            return
        self.placing = which
        self._hint.configure(text=self._placing_text())

    # -- the map -------------------------------------------------------------------------------
    def marks(self) -> list[dict]:
        """The links drawn on the canvas."""
        if self.data is None:
            return []
        out = []
        for i, d in enumerate(self.data["destinations"]):
            out.append({"chapter": d["chapter"], "selected": i == self.current,
                        "action": None if d.get("x") is None else (d["x"], d["y"]),
                        "return": None if d.get("return_x") is None else (d["return_x"], d["return_y"])})
        return out

    def mark_at(self, tile) -> tuple[int, str] | None:
        for i, d in reversed(list(enumerate(self.data["destinations"]))):
            if (d.get("x"), d.get("y")) == tuple(tile):
                return i, "action"
            if (d.get("return_x"), d.get("return_y")) == tuple(tile):
                return i, "return"
        return None

    def press(self, tile) -> dict | None:
        """A click on the map with the Hub tool: place what is waiting, or pick a link's
        tile (returned as a drag state)."""
        if self.placing is not None and self.current is not None:
            which = self.placing
            if self.place(self.current, which, tile):
                d = self.data["destinations"][self.current]
                self.placing = "return" if which == "action" and d.get("return_x") is None else None
                self._show_link()
            return None
        found = self.mark_at(tile)
        if found is None:
            return None
        self.select(found[0])
        return {"kind": "hub", "index": found[0], "which": found[1], "start": tile}

    def place(self, index: int, which: str, tile) -> bool:
        d = self.data["destinations"][index]
        keys = ("x", "y") if which == "action" else ("return_x", "return_y")
        if which == "action":
            other = next((o for j, o in enumerate(self.data["destinations"])
                          if j != index and (o.get("x"), o.get("y")) == tuple(tile)), None)
            if other is not None:
                self._hint.configure(text=f"Chapter {other['chapter']:02d}'s link already uses that tile.")
                return False
        d[keys[0]], d[keys[1]] = tile
        self._save()
        self._list.delete(index)
        self._list.insert(index, self._row(d))
        if index == self.current:
            self._list.selection_set(index)
        self._builder.hub_changed()
        return True

    # -- install --------------------------------------------------------------------------------
    def _install(self) -> None:
        data = self.data
        problems = []
        if not data["destinations"]:
            problems.append("Add at least one chapter link.")
        missing = [f"{d['chapter']:02d}" for d in data["destinations"]
                   if d.get("x") is None or d.get("return_x") is None]
        if missing:
            problems.append(f"Place the action tile and return point of chapter {', '.join(missing)}.")
        size = self._builder.map_size()
        if size is not None and not (MIN_SIZE <= min(size) and max(size) <= MAX_SIZE + 1):
            problems.append(f"Hub tiles are byte-sized: the map must be at most {MAX_SIZE + 1} tiles per side.")
        if problems:
            messagebox.showerror("Install hub", "\n".join(problems), parent=self)
            return
        try:
            setup = hub.setup_from({**data, "start_x": None, "start_y": None})
        except (KeyError, TypeError) as exc:
            messagebox.showerror("Install hub", f"The hub setup is incomplete: {exc}", parent=self)
            return
        if self._builder.install_hub(setup, storage=self._storage.get().lower()):
            self.load(f"{data['chapter']:02d}")
            self._builder.hub_changed()
