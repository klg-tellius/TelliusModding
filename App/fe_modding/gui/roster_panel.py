"""Chapters › Roster (Path of Radiance): who plays the chapter and how the game picks them,
who else is set aside, and who joins or leaves the army when it ends
(:mod:`fe_modding.chapter_roster`). **Check turn 1** plays the opening in the playthrough
simulator with a new save and with a save holding the whole army."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from .. import chapter_roster as cr
from .widgets import ScrollFrame, info

MODE_HELP = {
    cr.ARMY: "Player's army: each listed tile takes the next unit of the army, in army order (Ike on his own "
             "tile). The listed characters only matter on a new save. Group name with _mikata_.",
    cr.FIXED: "Fixed team: exactly the listed characters, each on their tile, taken from the reserve or "
              "created. Group name with _avatar_ (renamed from _mikata_ on Apply, script calls included).",
}


class RosterPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, project, *, names: Callable[[], dict],
                 before_write: Callable[[], bool], after_write: Callable[[str], None]) -> None:
        super().__init__(parent)
        self.project = project
        self._names_provider = names
        self._before_write = before_write
        self._after_write = after_write
        self._chapter: Optional[str] = None
        self._roster: Optional[cr.ChapterRoster] = None
        self._loaded = False

        scroll = ScrollFrame(self, padding=(16, 12))
        scroll.pack(fill="both", expand=True)
        body = scroll.body
        top = ttk.Frame(body)
        top.pack(fill="x", anchor="w")
        ttk.Label(top, text="Roster", font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(top, text="Apply", style="Accent.TButton", command=self.apply).pack(side="left", padx=(12, 0))
        ttk.Button(top, text="Check turn 1", command=self.check).pack(side="left", padx=(6, 0))
        ttk.Button(top, text="Reload", command=self.reload).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(top, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))
        info(top, "Apply writes the team into the chapter's deployment (Build tab) and the generated "
                  "blocks into its script (Script tab, between '# >>> Roster tab' and '# <<< Roster tab'). "
                  "Unsaved Build or Script edits are saved first.").pack(side="left", padx=(6, 0))
        self._unsupported = ttk.Label(body, text="", style="Muted.TLabel", wraplength=720, justify="left")
        self._unsupported.pack(fill="x", anchor="w", pady=(6, 0))

        self._content = ttk.Frame(body)
        self._content.pack(fill="both", expand=True)
        team = ttk.LabelFrame(self._content, text="Team", padding=8)
        team.pack(fill="x", anchor="w", pady=(10, 0))
        self._mode = tk.StringVar(value=cr.ARMY)
        for mode, label in ((cr.ARMY, "Player's army"), (cr.FIXED, "Fixed team")):
            row = ttk.Frame(team)
            row.pack(fill="x", anchor="w")
            ttk.Radiobutton(row, text=label, value=mode, variable=self._mode,
                            command=self._mode_changed).pack(side="left")
            info(row, MODE_HELP[mode]).pack(side="left", padx=(4, 0))
        self._group = ttk.Label(team, text="", style="Muted.TLabel")
        self._group.pack(anchor="w", pady=(2, 6))

        self._tree = ttk.Treeview(team, columns=("name", "pid", "x", "y"), show="headings", height=8,
                                  selectmode="browse")
        for column, title, width in (("name", "Character", 180), ("pid", "PID", 180), ("x", "X", 50), ("y", "Y", 50)):
            self._tree.heading(column, text=title)
            self._tree.column(column, width=width, stretch=column == "name")
        self._tree.pack(fill="x", anchor="w")
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._selected())

        edit = ttk.Frame(team)
        edit.pack(fill="x", anchor="w", pady=(6, 0))
        self._character = tk.StringVar()
        self._character_box = ttk.Combobox(edit, textvariable=self._character, width=34)
        self._character_box.pack(side="left")
        self._x, self._y = tk.IntVar(value=0), tk.IntVar(value=0)
        for label, var in (("X", self._x), ("Y", self._y)):
            ttk.Label(edit, text=label).pack(side="left", padx=(8, 2))
            ttk.Spinbox(edit, from_=0, to=255, textvariable=var, width=5).pack(side="left")
        ttk.Button(edit, text="Add", command=self._add_member).pack(side="left", padx=(8, 0))
        ttk.Button(edit, text="Set tile", command=self._set_tile).pack(side="left", padx=(4, 0))
        ttk.Button(edit, text="Remove", command=self._remove_member).pack(side="left", padx=(4, 0))
        ttk.Button(edit, text="Move up", command=lambda: self._move(-1)).pack(side="left", padx=(8, 0))
        ttk.Button(edit, text="Move down", command=lambda: self._move(1)).pack(side="left", padx=(2, 0))

        aside = ttk.Frame(team)
        aside.pack(fill="x", anchor="w", pady=(8, 0))
        self._set_aside = tk.BooleanVar(value=False)
        self._set_aside_check = ttk.Checkbutton(aside, text="Set every other unit aside", variable=self._set_aside)
        self._set_aside_check.pack(side="left")
        info(aside, "Fixed team only. Right after the team is deployed, every other player unit on the map "
                    "goes back to the reserve, so nobody else plays this chapter. No script to write.").pack(
            side="left", padx=(4, 0))

        end = ttk.LabelFrame(self._content, text="End of chapter", padding=8)
        end.pack(fill="x", anchor="w", pady=(10, 0))
        info(end, "Runs when the map goal is achieved (the script's @on_complete function). Joining characters "
                  "enter the reserve from a generated group; leaving characters go to force 7 (out of the army, "
                  "as vanilla chapter 5 does with Oscar and Boyd) until a deployment names them.").pack(anchor="w")
        self._joins = self._pid_list(end, "Join the army")
        self._leaves = self._pid_list(end, "Leave the army")

        report = ttk.LabelFrame(self._content, text="Turn 1 check", padding=8)
        report.pack(fill="both", expand=True, anchor="w", pady=(10, 0))
        self._report = tk.Text(report, height=16, wrap="word", state="disabled", borderwidth=0)
        self._report.pack(fill="both", expand=True)

    # -- widgets ---------------------------------------------------------------------------------------
    def _pid_list(self, parent: tk.Misc, title: str) -> tk.Listbox:
        frame = ttk.Frame(parent)
        frame.pack(fill="x", anchor="w", pady=(6, 0))
        ttk.Label(frame, text=title, width=16).pack(side="left", anchor="n")
        listbox = tk.Listbox(frame, height=4, width=40, exportselection=False)
        listbox.pack(side="left")
        controls = ttk.Frame(frame)
        controls.pack(side="left", padx=(8, 0), anchor="n")
        var = tk.StringVar()
        box = ttk.Combobox(controls, textvariable=var, width=34)
        box.pack(anchor="w")
        listbox._choice_box = box  # refreshed with the character list

        def add() -> None:
            pid = self._pid_of(var.get())
            if pid and pid not in listbox.get(0, "end"):
                listbox.insert("end", pid)

        def remove() -> None:
            for index in reversed(listbox.curselection()):
                listbox.delete(index)

        buttons = ttk.Frame(controls)
        buttons.pack(anchor="w", pady=(4, 0))
        ttk.Button(buttons, text="Add", command=add).pack(side="left")
        ttk.Button(buttons, text="Remove", command=remove).pack(side="left", padx=(4, 0))
        return listbox

    def _choices(self) -> list:
        names = self._names_provider() or {}
        return [f"{name} ({pid})" for pid, name in sorted(names.items(), key=lambda item: (item[1], item[0]))]

    def _pid_of(self, text: str) -> str:
        text = text.strip()
        if text.endswith(")") and "(" in text:
            return text[text.rindex("(") + 1:-1].strip()
        return text

    def _name_of(self, pid: str) -> str:
        return (self._names_provider() or {}).get(pid, "")

    # -- loading ---------------------------------------------------------------------------------------
    def show_chapter(self, chapter_id: Optional[str]) -> None:
        """Remember the chapter; it is read when the tab is shown (:meth:`ensure_loaded`)."""
        self._chapter = chapter_id
        self._loaded = False

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        self._loaded = True
        self._roster = None
        self._write_report([])
        if not cr.is_supported(self.project):
            self._show_unsupported("The Roster tab is for Path of Radiance chapters. Radiant Dawn's armies "
                                   "are set in the Overview's story flow.")
            return
        if self._chapter is None:
            self._show_unsupported("No chapter.")
            return
        try:
            self._roster = cr.read_roster(self.project, self._chapter)
        except Exception as exc:  # noqa: BLE001 - a chapter without the files has no roster
            self._show_unsupported(f"No roster for this chapter: {exc}")
            return
        self._unsupported.configure(text="")
        self._content.pack(fill="both", expand=True)
        choices = self._choices()
        self._character_box.configure(values=choices)
        for listbox in (self._joins, self._leaves):
            listbox._choice_box.configure(values=choices)
        roster = self._roster
        if not roster.groups:
            self._group.configure(text="The script deploys no player group: add one in the Build tab, "
                                       "and its Dispos call in the Script tab.")
        self._mode.set(roster.mode)
        self._tree.delete(*self._tree.get_children())
        for member in roster.members:
            self._tree.insert("", "end", values=(self._name_of(member.pid), member.pid, member.x, member.y))
        self._set_aside.set(roster.set_aside)
        for listbox, pids in ((self._joins, roster.joins), (self._leaves, roster.leaves)):
            listbox.delete(0, "end")
            for pid in pids:
                listbox.insert("end", pid)
        self._mode_changed()
        self._status.configure(text="")

    def _show_unsupported(self, text: str) -> None:
        self._content.pack_forget()
        self._unsupported.configure(text=text)

    def _mode_changed(self) -> None:
        if self._roster is None:
            return
        fixed = self._mode.get() == cr.FIXED
        self._set_aside_check.configure(state="normal" if fixed else "disabled")
        if self._roster.groups:
            preview = cr.ChapterRoster(self._roster.chapter_id, self._roster.folder, list(self._roster.groups),
                                       mode=self._mode.get())
            renames = preview.renamed_groups()
            text = "Group: " + ", ".join(renames.get(g, g) for g in self._roster.groups)
            if renames:
                text += "  (renamed from " + ", ".join(renames) + " on Apply)"
            self._group.configure(text=text)

    # -- team edits -------------------------------------------------------------------------------------
    def _selected(self) -> None:
        item = self._tree.focus()
        if not item:
            return
        name, pid, x, y = self._tree.item(item, "values")
        self._character.set(f"{name} ({pid})" if name else pid)
        self._x.set(int(x))
        self._y.set(int(y))

    def _tile(self) -> tuple[int, int]:
        try:
            return int(self._x.get()), int(self._y.get())
        except (tk.TclError, ValueError):
            return 0, 0

    def _add_member(self) -> None:
        pid = self._pid_of(self._character.get())
        if not pid:
            return
        if any(self._tree.item(i, "values")[1] == pid for i in self._tree.get_children()):
            messagebox.showinfo("Roster", f"{pid} is already in the team.", parent=self)
            return
        self._tree.insert("", "end", values=(self._name_of(pid), pid, *self._tile()))

    def _set_tile(self) -> None:
        item = self._tree.focus()
        if item:
            name, pid, _x, _y = self._tree.item(item, "values")
            self._tree.item(item, values=(name, pid, *self._tile()))

    def _remove_member(self) -> None:
        item = self._tree.focus()
        if item:
            self._tree.delete(item)

    def _move(self, step: int) -> None:
        item = self._tree.focus()
        if item:
            index = self._tree.index(item) + step
            if 0 <= index < len(self._tree.get_children()):
                self._tree.move(item, "", index)

    # -- apply / check ----------------------------------------------------------------------------------
    def edited_roster(self) -> Optional[cr.ChapterRoster]:
        if self._roster is None:
            return None
        roster = cr.ChapterRoster(self._roster.chapter_id, self._roster.folder, list(self._roster.groups),
                                  mode=self._mode.get(), other_player_groups=list(self._roster.other_player_groups))
        for item in self._tree.get_children():
            _name, pid, x, y = self._tree.item(item, "values")
            roster.members.append(cr.Member(pid, int(x), int(y)))
        roster.set_aside = self._set_aside.get() and roster.mode == cr.FIXED
        roster.joins = list(self._joins.get(0, "end"))
        roster.leaves = list(self._leaves.get(0, "end"))
        return roster

    def apply(self) -> None:
        roster = self.edited_roster()
        if roster is None or self._chapter is None:
            return
        if not self._before_write():
            return
        try:
            plan = cr.apply_roster(self.project, roster)
        except Exception as exc:  # noqa: BLE001 - roster, codec and compile errors alike
            messagebox.showerror("Could not apply the roster", str(exc), parent=self)
            return
        self._after_write(f"Roster: {roster.mode} team of {len(roster.members)}")
        self.reload()
        self._status.configure(text=f"Applied to {plan.deployment_path.parent.name} and {plan.script_path.name}.")
        self.check()

    def check(self) -> None:
        roster = self.edited_roster()
        if roster is None or self._chapter is None:
            return
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            plan = cr.plan_roster(self.project, roster) if roster.groups else None
            report = cr.check_roster(self.project, self._chapter, plan)
        except Exception as exc:  # noqa: BLE001 - shown in the report
            self._write_report([f"Could not check: {exc}"])
            return
        finally:
            self.configure(cursor="")
        lines = []
        if report.warnings:
            lines.append("Warnings")
            lines += [f"  ⚠ {w}" for w in report.warnings]
            lines.append("")
        for scenario in report.scenarios:
            lines.append(scenario.title)
            if scenario.error:
                lines.append(f"  The opening stopped: {scenario.error}")
            for pid, x, y in scenario.on_map:
                name = self._name_of(pid)
                lines.append(f"  {name or pid} ({pid}) at {x}, {y}")
            if not scenario.on_map:
                lines.append("  No player unit on the map.")
            for note in scenario.log:
                lines.append(f"    · {note}")
            lines.append("")
        if plan is not None:
            lines.append("Checked the roster as edited here (not applied yet)." if not self._applied(roster)
                         else "Checked the applied roster.")
        self._write_report(lines)

    def _applied(self, roster: cr.ChapterRoster) -> bool:
        saved = self._roster
        return (saved is not None and saved.mode == roster.mode and saved.set_aside == roster.set_aside
                and [(m.pid, m.x, m.y) for m in saved.members] == [(m.pid, m.x, m.y) for m in roster.members]
                and saved.joins == roster.joins and saved.leaves == roster.leaves)

    def _write_report(self, lines: list) -> None:
        self._report.configure(state="normal")
        self._report.delete("1.0", "end")
        self._report.insert("end", "\n".join(lines))
        self._report.configure(state="disabled")
