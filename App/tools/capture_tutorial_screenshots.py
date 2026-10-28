"""Capture the modding tutorials' app screenshots from the real app, unattended.

Opens the Tk app on a disposable project, puts it in the state each tutorial
frame needs, and saves the window as a PNG under
``wiki/assets/images/tutorials/screenshots/``. Every capture is logged (lesson,
caption, alt text, status) in ``capture_log.json`` next to the PNGs; the wiki
capture log page is written from it.

    python App/tools/capture_tutorial_screenshots.py --project "G:/FE9Mod/Tutorial Practice" [--only 01 02-a] [--list]

``--create SOURCE_DISC`` makes the project first through the real New Project
dialog and Extract button (this is how lesson 01 is captured). The user's
recent-project list and settings file are never written: both are replaced by
in-memory copies while the tool runs. Frames that need Dolphin, Blender or
sample media are not here; they stay "blocked" in the log.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as _dt
import json
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Callable, Iterator, Optional
from unittest import mock
from fe_modding.game_profile import files_root_of

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "App"))
OUT = ROOT / "wiki" / "assets" / "images" / "tutorials" / "screenshots"
LOG = OUT / "capture_log.json"
SIZE = (1440, 900)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # real pixels for ImageGrab
except (AttributeError, OSError):
    pass

import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

from fe_modding import config  # noqa: E402

# -- keep the user's own config out of it --------------------------------------------------------
_settings = {}
_real_load_setting = config.load_setting


def _load_setting(key, default=None):
    return _settings[key] if key in _settings else _real_load_setting(key, default)


def _save_setting(key, value):
    _settings[key] = value


config.load_setting = _load_setting
config.save_setting = _save_setting
config.load_recent_projects = lambda: []
config.add_recent_project = lambda directory: None
config.remove_recent_project = lambda directory: None


# -- steps ------------------------------------------------------------------------------------------
class Step:
    def __init__(self, key: str, run: Callable[["Ctx"], Iterator], needs_project: bool):
        self.key, self.run, self.needs_project = key, run, needs_project


STEPS: list[Step] = []


def step(key: str, *, needs_project: bool = True):
    def wrap(fn):
        STEPS.append(Step(key, fn, needs_project))
        return fn
    return wrap


class Wait:
    """Yielded by a step: wait until ``until()`` is true (or ``ms`` passed)."""

    def __init__(self, ms: int = 0, until: Optional[Callable[[], bool]] = None, timeout: int = 120_000):
        self.ms, self.until, self.timeout = ms, until, timeout


class Ctx:
    def __init__(self, app, project_dir: Path, log: dict, source_disc: Optional[Path]):
        self.app = app
        self.project_dir = project_dir
        self.log = log
        self.source_disc = source_disc
        self.commit = _git_commit()

    # -- the app --
    @property
    def shell(self):
        return self.app._shell

    @property
    def project(self):
        return self.shell.project

    def later(self, fn: Callable, ms: int = 0) -> None:
        """Run ``fn`` from the event loop (use it for anything that opens a modal dialog)."""
        self.app.after(ms, fn)

    def go(self, *route) -> None:
        self.shell.navigate(tuple(route))

    def page(self, kind: str):
        return self.shell.page(kind)

    def toplevel(self, title: str) -> Optional[tk.Toplevel]:
        """The open Toplevel whose title contains ``title``."""
        found = []

        def walk(widget):
            for child in list(widget.children.values()):
                if isinstance(child, tk.Toplevel) and child.winfo_exists() and title.lower() in child.title().lower():
                    found.append(child)
                walk(child)
        walk(self.app)
        return found[-1] if found else None

    def close(self, title: str) -> None:
        top = self.toplevel(title)
        if top is not None:
            top.destroy()

    def find(self, root: tk.Misc, cls=None, text: Optional[str] = None) -> list:
        """Widgets under ``root`` of class ``cls`` whose ``text`` option equals/contains ``text``."""
        hits = []

        def walk(widget):
            for child in list(widget.children.values()):
                ok = cls is None or isinstance(child, cls)
                if ok and text is not None:
                    try:
                        ok = text in str(child.cget("text"))
                    except tk.TclError:
                        ok = False
                if ok:
                    hits.append(child)
                walk(child)
        walk(root)
        return hits

    def button(self, root: tk.Misc, text: str):
        hits = self.find(root, (ttk.Button, tk.Button), text)
        if not hits:
            raise LookupError(f"no button {text!r}")
        return hits[0]

    def select_row(self, root: tk.Misc, match: str, *, index: int = 0) -> bool:
        """Select (and scroll to) the first Listbox/Treeview row under ``root`` that contains ``match``,
        firing the widget's selection event. ``index`` skips that many matching widgets."""
        hits = 0
        for widget in self.find(root, (tk.Listbox, ttk.Treeview)):
            if isinstance(widget, tk.Listbox):
                rows = [r for r in range(widget.size()) if match in str(widget.get(r))]
                if not rows:
                    continue
                if hits == index:
                    widget.selection_clear(0, "end")
                    widget.selection_set(rows[0])
                    widget.activate(rows[0])
                    widget.see(rows[0])
                    widget.event_generate("<<ListboxSelect>>")
                    return True
            else:
                found = _tree_find(widget, match)
                if found is None:
                    continue
                if hits == index:
                    parent = widget.parent(found)
                    while parent:
                        widget.item(parent, open=True)
                        parent = widget.parent(parent)
                    widget.selection_set(found)
                    widget.focus(found)
                    widget.see(found)
                    widget.event_generate("<<TreeviewSelect>>")
                    return True
            hits += 1
        return False

    def tab(self, notebook: ttk.Notebook, label: str) -> None:
        for tab_id in notebook.tabs():
            if notebook.tab(tab_id, "text") == label:
                notebook.select(tab_id)
                return
        raise LookupError(f"no tab {label!r}")

    # -- capture --
    def grab(self, name: str, *, lesson, caption: str, alt: str, widget: Optional[tk.Misc] = None,
             over: tuple = (), status: str = "captured", notes: str = "") -> None:
        """Save ``widget``'s window (title bar and menus included) as ``name``; ``over`` are pop-ups
        (search palette, menus) kept above it in the picture."""
        widget = widget or self.app
        top = widget.winfo_toplevel()
        image = _grab_window(top, [w.winfo_toplevel() for w in over])
        w, h = image.size
        OUT.mkdir(parents=True, exist_ok=True)
        image.save(OUT / name, optimize=True)
        self.log[name] = {
            "file": name, "lesson": lesson, "caption": caption, "alt": alt, "status": status,
            "notes": notes, "size": [w, h], "captured": _dt.date.today().isoformat(),
            "app_commit": self.commit, "project": "Tutorial Practice (USA, fresh extraction)",
        }
        print(f"captured {name} ({w}x{h})", flush=True)


def _tree_find(tree: ttk.Treeview, match: str, parent: str = ""):
    for item in tree.get_children(parent):
        values = " ".join(str(v) for v in (tree.item(item, "text"), *tree.item(item, "values")))
        if match == item or match in values:
            return item
        deeper = _tree_find(tree, match, item)
        if deeper is not None:
            return deeper
    return None


def _grab_window(top: tk.Misc, over=()):
    """Picture of ``top`` (raised above every other window) with the pop-ups ``over`` above it."""
    stack = [top, *over]
    for window in stack:
        window.lift()
        window.attributes("-topmost", True)
    top.update()
    top.after(300)
    top.update()
    x, y, x2, y2 = _frame_bounds(top)
    image = ImageGrab.grab(bbox=(x, y, x2, y2), all_screens=True)
    for window in stack:
        window.attributes("-topmost", False)
    return image


def _frame_bounds(top: tk.Misc) -> tuple[int, int, int, int]:
    """Screen rectangle of the whole window without its invisible resize border (DWM bounds)."""
    hwnd = int(top.wm_frame(), 16)
    rect = (ctypes.c_long * 4)()
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
        if rect[2] > rect[0]:
            return rect[0], rect[1], rect[2], rect[3]
    except (AttributeError, OSError):
        pass
    x, y = top.winfo_rootx(), top.winfo_rooty()
    return x, y, x + top.winfo_width(), y + top.winfo_height()


def _git_commit() -> str:
    try:
        rev = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "App/fe_modding"],
                               capture_output=True, text=True).stdout.strip()
        return rev + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# -- runner -----------------------------------------------------------------------------------------
def run(steps: list[Step], project_dir: Path, source_disc: Optional[Path]) -> int:
    from fe_modding.gui.app import MainWindow

    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.is_file() else {}
    with mock.patch("tkinter.messagebox.askyesno", return_value=True), \
            mock.patch("tkinter.messagebox.askokcancel", return_value=True), \
            mock.patch("tkinter.messagebox.showinfo", side_effect=lambda *a, **k: print("info:", a[:2])), \
            mock.patch("tkinter.messagebox.showwarning", side_effect=lambda *a, **k: print("warning:", a[:2])), \
            mock.patch("tkinter.messagebox.showerror", side_effect=lambda *a, **k: print("ERROR:", a[:2])):
        app = MainWindow()
        app.state("normal")
        app.geometry(f"{SIZE[0]}x{SIZE[1]}+20+20")
        ctx = Ctx(app, project_dir, log, source_disc)
        failures: list[str] = []
        queue = list(steps)

        def save_log():
            OUT.mkdir(parents=True, exist_ok=True)
            LOG.write_text(json.dumps(dict(sorted(log.items())), indent=1, ensure_ascii=False) + "\n",
                           encoding="utf-8", newline="\n")

        def next_step():
            if not queue:
                save_log()
                app.after(200, app.destroy)
                return
            current = queue.pop(0)
            if current.needs_project and ctx.shell is None:
                app._load_project(project_dir)
            print(f"-- {current.key}", flush=True)
            drive(current, current.run(ctx), _dt.datetime.now())

        def drive(current: Step, gen, started, waiting: Optional[Wait] = None):
            try:
                if waiting is not None and waiting.until is not None and not waiting.until():
                    if (_dt.datetime.now() - started).total_seconds() * 1000 > waiting.timeout:
                        raise TimeoutError("condition not met")
                    app.after(250, lambda: drive(current, gen, started, waiting))
                    return
                value = next(gen)
            except StopIteration:
                save_log()
                app.after(100, next_step)
                return
            except Exception:  # noqa: BLE001 - one broken step must not stop the others
                traceback.print_exc()
                failures.append(current.key)
                for top in [w for w in list(app.children.values()) if isinstance(w, tk.Toplevel)]:
                    top.destroy()
                save_log()
                app.after(100, next_step)
                return
            wait = value if isinstance(value, Wait) else Wait(int(value or 0))
            app.after(max(wait.ms, 1), lambda: drive(current, gen, _dt.datetime.now() if wait.until else started,
                                                     wait if wait.until else None))

        # Overlays such as Discord's announce a new window with a toast for a few seconds: let it go.
        app.after(12_000, next_step)
        app.mainloop()
    if failures:
        print("FAILED:", ", ".join(failures))
    return 1 if failures else 0


# ===================================================================================================
# Lesson steps. Each yields waits (ms or Wait) and calls ctx.grab(); keys are "NN-x".
# ===================================================================================================

# -- 01 Install and create a project --
@step("01", needs_project=False)
def lesson_01(ctx: Ctx):
    if ctx.project_dir.is_dir():
        print("project exists: skipping creation frames 01-a/01-c")
        ctx.app._load_project(ctx.project_dir)
        yield 1500
    else:
        ctx.grab("01-launcher.png", lesson=1, caption="The launcher before a project is open: **New project…** "
                 "creates one, **Open project folder…** reopens an existing project folder.",
                 alt="Tellius Modding launcher with New project and Open project folder buttons.")
        ctx.later(ctx.app._new_project)
        yield Wait(until=lambda: ctx.toplevel("New Project") is not None, timeout=10_000)
        dialog = ctx.toplevel("New Project")
        dialog._name_var.set("Tutorial Practice")
        dialog._location_var.set(str(ctx.project_dir.parent))
        yield 400
        ctx.grab("01-a-setup.png", widget=dialog, lesson=1,
                 caption="**New Project** with Path of Radiance selected, the name *Tutorial Practice* and the parent "
                         "folder. The preview line shows the folder the app will create.",
                 alt="New Project dialog: game choice, project name, Create in folder with Browse, folder preview, "
                     "Create Project and Cancel buttons.")
        ctx.button(dialog, "Create Project").invoke()
        yield Wait(until=lambda: ctx.shell is not None, timeout=10_000)
        yield 800
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=str(ctx.source_disc)):
            ctx.shell.navigate(("disc",))
            yield 300
            ctx.shell.set_source()
        ctx.go("disc")
        yield 800
        ctx.grab("01-c-extract.png", lesson=1,
                 caption="**Disc & Patch** after **Choose disc image…**: the project has its own copy of the disc. "
                         "**Extract** unpacks it into the project's `extracted` folder.",
                 alt="Disc and Patch page with the chosen source disc, Choose disc image and Extract buttons, and "
                     "the build and patch cards.")
        ctx.shell.extract()
        yield Wait(until=lambda: ctx.shell.extracted and not ctx.shell._task_running, timeout=900_000)
        yield 1500
    ctx.go("home")
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=120_000)
    yield 2500
    ctx.grab("01-b-result.png", lesson=1,
             caption="Home after extraction: the project name and disc are shown and every workspace section is "
                     "unlocked.",
             alt="Home page of the Tutorial Practice project with section tiles and the recent changes list.")


# -- 01 extra frames on an existing practice project: tools dialog, launcher, an unextracted project --
@step("01x")
def lesson_01_extra(ctx: Ctx):
    import shutil
    from fe_modding.gui.tool_setup import ToolSetupDialog
    from fe_modding.project import ModProject
    from fe_modding.games import Game
    dialog = ToolSetupDialog(ctx.app)
    yield 800
    ctx.grab("01-d-tools.png", widget=dialog, lesson=1,
             caption="**Settings › Disc and media tools…** (offered at first start when WIT is missing): **Download "
                     "missing tools** fetches WIT, which extracts and builds discs, and, with **Include FFmpeg for "
                     "audio/video imports**, FFmpeg. Your game files are not downloaded or included.",
             alt="Set up disc and media tools dialog with the FFmpeg checkbox, Download missing tools and Later.")
    dialog.destroy()
    ctx.app._close_project()
    yield 1200
    ctx.grab("01-launcher.png", lesson=1,
             caption="The launcher when no project is open: **New project…** creates one, **Open project folder…** "
                     "opens an existing one, and **Recent projects** lists the last ones opened.",
             alt="Tellius Modding launcher with New project, Open project folder and the empty recent projects list.")
    scratch = ctx.project_dir.parent / "Tutorial Scratch"
    if not scratch.exists():
        project = ModProject.create(parent_directory=scratch.parent, name="Tutorial Scratch",
                                    game=Game.PATH_OF_RADIANCE)
        project.set_source(ctx.source_disc or (ctx.project_dir / "source" /
                                               "Fire Emblem - Path of Radiance (USA).ciso"))
    ctx.app._load_project(scratch)
    yield 1500
    ctx.go("disc")
    yield 1200
    ctx.grab("01-c-extract.png", lesson=1,
             caption="**Disc & Patch** after **Choose disc image…**: the image is copied into the project's "
                     "`source` folder and named on the **Source disc** card, *Not extracted yet*. **Extract** "
                     "unpacks it; until then only Home and Disc & Patch open.",
             alt="Disc and Patch page of an unextracted project with the source disc card, Choose disc image and "
                 "Extract, and the disabled build and patch buttons.")
    ctx.app._close_project()
    yield 500
    if scratch.name == "Tutorial Scratch":
        shutil.rmtree(scratch, ignore_errors=True)
    ctx.app._load_project(ctx.project_dir)
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=120_000)
    yield 2000
    ctx.go("home")
    yield 1200
    ctx.grab("01-b-result.png", lesson=1,
             caption="Home of the extracted project: its name, game, platform and folder, the six section cards "
                     "(Chapters lists 31 chapters, Characters 47 playable of 127) and **Changes this session**.",
             alt="Home page of Tutorial Practice with the Browse cards and the changes list.")


# -- 02 Workspace tour --
@step("02")
def lesson_02(ctx: Ctx):
    ctx.go("home")
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=120_000)
    yield 1500
    ctx.grab("02-a-setup.png", lesson=2,
             caption="The workspace: section bar along the top, breadcrumbs with Back/Forward under it, the page, and "
                     "the status bar with the unsaved count and **Changes this session**.",
             alt="Home page showing the top section bar, search box, breadcrumb bar and status bar.")
    ctx.shell.open_search()
    yield 400
    palette = ctx.shell._palette
    palette._query.set("Ike")
    yield 700
    ctx.grab("02-b-result.png", lesson=2, over=(palette,),
             caption="**Ctrl+K** search for *Ike*: one list finds characters, classes, items, chapters and messages. "
                     "Enter opens the selected result.",
             alt="Search palette over the workspace with the query Ike and matching results listed by kind.")
    palette.destroy()
    yield 200
    ctx.go("characters")
    yield 800
    ctx.go("character", "PID_IKE", "stats")
    yield 1200
    ctx.go("chapter", "01", "script")
    yield 2500
    ctx.grab("02-c-crumbs.png", lesson=2,
             caption="The breadcrumb bar after Characters → Ike → Prologue: **‹** goes back to Ike (Alt+Left), **›** "
                     "forward again (Alt+Right), and each crumb (*Chapters › Prologue: Mercenaries › Script*) is a "
                     "link. The section tab in the top bar shows where you are.",
             alt="Workspace on the Prologue Script tab with the breadcrumb bar and back and forward buttons.")
    ctx.shell.back()
    yield 1500
    ctx.grab("02-d-back.png", lesson=2,
             caption="**‹** returned to Ike's Stats tab, as it was: pages keep their state while you move around, "
                     "and unsaved edits stay in their editor.",
             alt="Ike's character page after pressing back, with the forward button now enabled.")


# -- 10 Create a character (runs before 03, which edits the record it makes) --
GUARD = "PID_TUTORIAL_GUARD"
TEMPLATE = "PID_BOLE"  # Boyd: a plain unpromoted Fighter


@step("10")
def lesson_10(ctx: Ctx):
    session = ctx.shell.session
    if session.character_index(GUARD) is None:
        ctx.go("characters")
        yield 800
        page = ctx.page("characters")
        ctx.later(page._new_character)
        yield Wait(until=lambda: ctx.toplevel("New character") is not None, timeout=10_000)
        dialog = ctx.toplevel("New character")
        dialog._id.set(GUARD)
        dialog._template.set(next(t for t in dialog._templates if t.startswith(TEMPLATE + " ")))
        yield 400
        ctx.grab("10-a-setup.png", widget=dialog, lesson=10,
                 caption="**Characters › New character…**: the new PID is `PID_TUTORIAL_GUARD` and **Start as a copy "
                         "of** is Boyd (`PID_BOLE`). The copy keeps Boyd's name key, portrait and class until you "
                         "change them.",
                 alt="New character dialog with the new ID field, the copy-from list set to PID_BOLE, Create and "
                     "Cancel.")
        ctx.button(dialog, "Create").invoke()
        yield Wait(until=lambda: session.character_index(GUARD) is not None, timeout=10_000)
        yield 1200
    # Start from the copy as New character… makes it: Boyd's name key and Boyd's HP bonus.
    from fe_modding.formats import fe8data
    index = session.character_index(GUARD)
    boyd = session.fe8.characters[session.character_index(TEMPLATE)]
    data = fe8data.patch_character_field(session.data, index, "mpid", boyd.mpid)
    if data != session.data:
        session.data = data
        session.changed(None)
    if session.dirty:
        session.save()
    yield from reindex(ctx)
    ctx.go("characters")
    yield 1500
    hub = ctx.page("characters")
    hub._category.set("all")
    hub._query.set("Boyd")
    yield 1500
    ctx.grab("10-e-hub.png", lesson=10,
             caption="**Characters**, **All**, *Boyd* in **Search name or PID**: one card, Boyd, *+3 copies*. Records that share a name key are shown as one: Boyd's two event records and the new `PID_TUTORIAL_GUARD`, which still uses `MPID_BOLE`.",
             alt="Characters page filtered on Boyd with the category chips, the count and the matching cards.")
    hub._query.set("")
    hub._category.set("playable")
    ctx.go("character", GUARD, "stats")
    yield 1500
    form = ctx.page("character")._form
    from fe_modding.gui import message_reference
    mpid_var = form._vars["mpid"]
    box = next(b for b in ctx.find(form, ttk.Combobox) if str(b.cget("textvariable")) == str(mpid_var))

    def ask_name():
        mpid_var.set(message_reference.CREATE_MESSAGE)
        box.event_generate("<<ComboboxSelected>>")
    ctx.later(ask_name)
    yield Wait(until=lambda: ctx.toplevel("Create message") is not None, timeout=10_000)
    dialog = ctx.toplevel("Create message")
    dialog._id_var.set("MPID_TUTORIAL_GUARD")
    dialog._text.delete("1.0", "end")
    dialog._text.insert("1.0", "Guard")
    yield 400
    ctx.grab("10-f-name.png", widget=dialog, lesson=10,
             caption="**Name key (MPID)** › **＋ Create new message…**: **Message ID** `MPID_TUTORIAL_GUARD`, "
                     "**Message text** *Guard*. **Create and assign** writes the text into `Mess/common.m` and points "
                     "the record at it; Boyd keeps `MPID_BOLE`.",
             alt="Create message dialog with the message ID, the message text, Create and assign and Cancel.")
    texts = message_reference.message_texts(ctx.project)
    if "MPID_TUTORIAL_GUARD" in texts:
        dialog.destroy()  # made by an earlier run
        mpid_var.set("MPID_TUTORIAL_GUARD")
    else:
        ctx.button(dialog, "Create and assign").invoke()
    yield 800
    form._vars["stat_bonus0"].set(str(boyd.stat_bonus[0] + 1))
    yield 300
    ctx.grab("10-c-stats.png", lesson=10,
             caption="The new record after **＋ Create new message…** and before **Apply**: **Name key (MPID)** reads `MPID_TUTORIAL_GUARD` (*Guard*), the HP **Personal bonus** is raised from 6 to 7. The header still says *Boyd* and lists the records sharing his name until the file is saved.",
             alt="Stats tab of PID_TUTORIAL_GUARD: identity, skills, map models, level row and the stat grid with "
                 "the edited HP bonus.")
    form._apply()
    yield 500
    if session.dirty:
        session.save()
    yield from reindex(ctx)
    ctx.go("home")
    yield 500
    ctx.go("character", GUARD, "stats")
    yield 1500
    ctx.grab("10-b-result.png", lesson=10,
             caption="After **Apply** and **Save FE8Data.bin**, reopening the record: the page is titled *Guard*, "
                     "**Save FE8Data.bin** is disabled and the HP bonus is kept. The record exists, but nothing "
                     "deploys it yet.",
             alt="Character page of PID_TUTORIAL_GUARD titled Guard after saving, with its saved stats.")
    ctx.go("character", GUARD, "appearances")
    yield 2000
    ctx.grab("10-g-unused.png", lesson=10,
             caption="**Appearances** of the new character: *Not found in any deployment file or chapter message.* "
                     "Creating a record neither deploys nor recruits it.",
             alt="Appearances tab of PID_TUTORIAL_GUARD with empty Deployed in and Dialogue tables.")
    builder = build_tab(ctx, "02")
    yield 3500
    set_variant(builder, "Normal")
    yield 2000
    builder._select(("unit", *find_unit(builder, "PID_BOLE")))
    yield 1200
    builder._form_vars["pid"].set_label(GUARD)
    yield 600
    ctx.grab("10-d-deployment.png", lesson=10,
             caption="Placing it: on Ch.1's **Build** tab (*Normal*), Boyd's slot in `bmap02_mikata_n` selected and "
                     "**Character** changed to `PID_TUTORIAL_GUARD`. **Apply**, then **Save Chapter**, writes the "
                     "deployment file; this capture stops before **Apply**.",
             alt="Build tab of Ch.1 with a player unit selected and PID_TUTORIAL_GUARD in its Character field.")
    builder._select(None)
    yield 500


# -- 03 Saving and restoring --
@step("03")
def lesson_03(ctx: Ctx):
    ctx.go("character", GUARD, "stats")
    yield 1200
    form = ctx.page("character")._form
    original = form._vars["stat_bonus1"].get()
    form._vars["stat_bonus1"].set(str(int(original) + 1))
    form._apply()
    yield 1500
    ctx.grab("03-a-setup.png", lesson=3,
             caption="An applied but unsaved edit: the form says **Unsaved changes in FE8Data.bin**, **Save "
                     "FE8Data.bin** is enabled, and the status bar names the unsaved file.",
             alt="Character Stats tab with the unsaved-changes warning beside Save FE8Data.bin and the unsaved "
                 "count in the status bar.")
    ctx.shell.session.save()
    yield 600
    ctx.go("home")
    yield 800
    ctx.go("character", GUARD, "stats")
    yield 1500
    ctx.grab("03-b-result.png", lesson=3,
             caption="After saving, leaving and reopening the record, the Strength bonus is still raised and **Save "
                     "FE8Data.bin** is disabled again: the file holds the value.",
             alt="Character Stats tab after reopening, with Save FE8Data.bin disabled and the raised Strength bonus.")
    form = ctx.page("character")._form
    form._vars["stat_bonus1"].set(original)
    form._apply()
    ctx.shell.session.save()
    yield 300
    if not ctx.shell._drawer_open:
        ctx.shell.toggle_activity()
    yield 1000
    ctx.grab("03-c-changes.png", lesson=3,
             caption="**Changes this session** (the counter at the bottom left, or **View › Changes this session**): "
                     "every save, import and restore of the session with its time and owner. It is not saved with "
                     "the project.",
             alt="Workspace with the Changes this session drawer open above the status bar, listing the saves.")
    ctx.shell.toggle_activity()
    yield 300


# -- 05 Check --
@step("05")
def lesson_05(ctx: Ctx):
    ctx.go("check")
    yield 600
    page = ctx.page("check")
    page.run()
    yield Wait(until=lambda: not page._running, timeout=600_000)
    yield 1500
    ctx.grab("05-a-setup.png", lesson=5,
             caption="**Tools › Check › Run check** on the unmodified project gives the baseline list. Note these "
                     "rows: after an edit, only new rows are yours to fix.",
             alt="Check page with the Run check button, the summary line and the results table.")
    message = files_root_of(ctx.project) / "Mess" / "c31.m"
    hidden = message.with_name("c31.m.tutorial-hidden")
    if hidden.exists() and not message.exists():
        hidden.rename(message)  # a previous run stopped half-way
    message.rename(hidden)
    try:
        page.run()
        yield Wait(until=lambda: not page._running, timeout=600_000)
        yield 1200
        ctx.select_row(page, "c31.m")
        yield 800
        ctx.grab("05-c-error.png", lesson=5,
                 caption="An induced failure: with `Mess/C31.m` moved away, **Run check** reports *1 error*: "
                         "**Severity** error, **Area** Chapter 31, **File** `Mess/C31.m`, *The chapter's message "
                         "file is missing.* Double-click the row to open the chapter it belongs to.",
                 alt="Check page with one error row for the missing message file of chapter 31 above the four "
                     "baseline warnings.")
    finally:
        if hidden.exists():
            hidden.rename(message)
    page.run()
    yield Wait(until=lambda: not page._running, timeout=600_000)
    yield 1200
    ctx.grab("05-b-result.png", lesson=5,
             caption="The file put back and **Run check** again: *0 errors, 4 warnings*, the baseline. The four "
                     "warnings are in the retail data, in places the game never reaches.",
             alt="Check page back to the four baseline warnings and no error.")


# -- putting the project back after steps that add chapters ----------------------------------------
class Snapshot:
    """The bytes of ``files`` and the contents of ``folders`` (paths relative to the project), put back
    by :meth:`restore`: files get their old bytes, and whatever is new in the folders is deleted."""

    def __init__(self, ctx: Ctx, files=(), folders=()):
        base = ctx.project_dir
        self.files = {base / f: ((base / f).read_bytes() if (base / f).is_file() else None) for f in files}
        self.folders = {base / d: set((base / d).rglob("*")) if (base / d).is_dir() else set() for d in folders}

    def restore(self) -> None:
        import shutil
        for folder, before in self.folders.items():
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*"), key=lambda p: -len(p.parts)):
                if path in before or not path.exists():
                    continue
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        for path, data in self.files.items():
            if data is None:
                path.unlink(missing_ok=True)
            elif not path.is_file() or path.read_bytes() != data:
                path.write_bytes(data)


#: What adding, deleting and story-order edits write.
CHAPTER_FILES = ["extracted/files/FE8Data.bin", "extracted/sys/main.dol", "extracted/files/Mess/common.m",
                 "extracted/files/Mess/ending.m",
                 "extracted/files/shop/shopitem_n.bin", "extracted/files/shop/shopitem_h.bin",
                 "extracted/files/shop/shopitem_m.bin"]
CHAPTER_FOLDERS = ["extracted/files/Mess", "extracted/files/Scripts", "extracted/files/zmap", "script_sources",
                   "extracted/files/window", "originals"]


def chapter_snapshot(ctx: Ctx) -> Snapshot:
    return Snapshot(ctx, CHAPTER_FILES, CHAPTER_FOLDERS)


def restore_chapters(ctx: Ctx, snapshot: Snapshot):
    """Put the chapter files back and make the app read them again."""
    ctx.go("home")
    yield 500
    snapshot.restore()
    ctx.shell.session.revert()
    page = ctx.shell.existing_page("chapter")
    if page is not None:
        page._chapter = None
        page.refresh_chapter_lists()
    yield from reindex(ctx)
    print("chapter files restored", flush=True)


def wait_route(ctx: Ctx, *route) -> Wait:
    return Wait(until=lambda: tuple(ctx.shell.route or ())[:len(route)] == route, timeout=60_000)


def wait_chapter_indexed(ctx: Ctx, chapter: str) -> Wait:
    return Wait(until=lambda: ctx.shell.index is not None and chapter in ctx.shell.index.by_chapter, timeout=180_000)


# -- 06 Chapter anatomy: Ch.5 Flight! (slot 06) has a battle map and a cutscene map phase --
@step("06")
def lesson_06(ctx: Ctx):
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=180_000)
    ctx.go("chapter", "06", "overview")
    yield 3000
    page = ctx.page("chapter")
    page._set_difficulty("n")
    yield 1500
    ctx.grab("06-a-setup.png", lesson=6,
             caption="The **Overview** of Ch.5: Flight! (slot 06). Under the title, the **Map phase** list (*Map "
                     "phase 1 · bmap06*) with **‹ Phase** / **Phase ›**, **+ Phase…** and **Remove phase…**; on the "
                     "right **▶ Play in Dolphin…**, **‹ Previous**, **Delete chapter…** and **Next ›**. The page lists "
                     "the story flow, then the cast of each section of the Normal deployment file, here the 22 "
                     "enemies of `bmap06_first_n` first.",
             alt="Overview of Ch.5 Flight! with the map phase controls under the title, the Story flow box and the "
                 "first section of the cast.")
    page._set_phase("bmap06_2")
    yield 800
    page._set_difficulty("c")
    yield 1500
    ctx.grab("06-c-phase.png", lesson=6,
             caption="**Map phase 2 · bmap06_2** with **Deployment file** *Common*: the map of the opening "
                     "cutscene. Its sections `bmap06_2_event00_c` and `bmap06_2_event_ged_c` are only placed by the "
                     "script; its Normal, Hard and Maniac files are empty.",
             alt="Overview of the second map phase of Ch.5 with the common deployment file's two event sections.")
    page._set_phase("bmap06")
    page._set_difficulty("n")
    yield 800
    ctx.go("chapter", "06", "chapter_data")
    yield 2500
    ctx.grab("06-e-record.png", lesson=6,
             caption="The **Chapter data** tab: chapter 06's record in `FE8Data.bin`. **Map** `bmap06`, **Script** "
                     "`C06`, **Message file** `C06` and the **Title key** `MCT06` are the names the other tabs "
                     "follow.",
             alt="Chapter data tab of Ch.5 with the record's title key, map, script and message names and its other "
                 "fields.")
    ctx.go("chapter", "06", "script", "func_10")
    yield 3000
    ctx.grab("06-d-script.png", lesson=6,
             caption="The **Script** tab on `func_10`, the opening scene: `MapLoad(\"bmap06_2\")` loads the "
                     "cutscene map, `InstantDispos(\"bmap06_2_event00_c\")` places its section, and `TalkEvent` "
                     "plays the messages `MS_06_OP_01` and `MS_06_OP_02` of `c06.m`.",
             alt="Script tab of Ch.5 with the function list and the opening function that loads bmap06_2.")
    builder = build_tab(ctx, "06")
    yield 3500
    set_variant(builder, "Normal")
    yield 2500
    ctx.grab("06-b-result.png", lesson=6,
             caption="Back on **Map phase 1 · bmap06**, the **Build** tab with the *Normal* file: the battle map "
                     "with the 8 player slots, the 22 enemies of `bmap06_first_n` and the 5 reinforcements of "
                     "`bmap06_zoen_n` on their tiles.",
             alt="Build tab of Ch.5 Flight! on the Normal deployment file with the unit markers on the map.")


# -- 07 Chapter IDs and story order: add a chapter, route it, take it out, delete it --
@step("07")
def lesson_07(ctx: Ctx):
    snapshot = chapter_snapshot(ctx)
    try:
        ctx.go("chapters")
        yield 1500
        ctx.grab("07-chapters.png", lesson=7,
                 caption="**Chapters**: the action cards (**Add chapter…**, **New campaign…**, **Story order…**, "
                         "**Create hub…**), then the story in play order with each chapter's place (*#1* to *#31*).",
                 alt="Chapters page with the action cards and the story chapter cards with order badges.")
        hub_page = ctx.page("chapters")
        ctx.later(hub_page._add_chapter)
        yield Wait(until=lambda: ctx.toplevel("Add Chapter") is not None, timeout=20_000)
        dialog = ctx.toplevel("Add Chapter")
        dialog._source_var.set(next(k for k in dialog._templates if k.endswith("(02)")))
        dialog._id_var.set("33")
        dialog._title_var.set("Tutorial: Side Path")
        dialog._after_var.set(next(k for k in dialog._after if k.startswith("02 ")))
        yield 600
        ctx.grab("07-a-setup.png", widget=dialog, lesson=7,
                 caption="**Add chapter…**: **Copy of** Ch.1 (02), **Chapter number** 33, **Title** *Tutorial: Side "
                         "Path*, **Played after** 02. The line under it says what changes: 02 will lead to 33, and "
                         "33 to 03.",
                 alt="Add Chapter dialog with Copy of, Chapter number, Title and Played after, the routing hint, "
                     "Add Chapter and Cancel.")
        ctx.button(dialog, "Add Chapter").invoke()
        yield wait_route(ctx, "chapter", "33")
        yield wait_chapter_indexed(ctx, "33")
        ctx.go("chapter", "33", "overview")
        yield 2500
        ctx.grab("07-c-flow.png", lesson=7,
                 caption="The new chapter 33's **Overview**: **Played after:** *02 · Ch.1: The Battle Begins*, "
                         "**Next chapter:** *03 · Ch.2: Rescue*, and **Take out of the story**, which only added "
                         "chapters have. The header shows **Delete chapter…** for every chapter but the Prologue.",
                 alt="Overview of the added chapter 33 with its Story flow box, the Take out of the story button "
                     "and the copied cast.")
        ctx.go("chapter", "02", "overview")
        yield 2500
        ctx.grab("07-b-result.png", lesson=7,
                 caption="Ch.1's **Story flow** after the add: its **Next chapter** is now *33 · Tutorial: Side "
                         "Path*. The change is in `main.dol`'s next-chapter table; only playing Ch.1 to its end in "
                         "Dolphin proves the transition.",
                 alt="Story flow box of Ch.1 with Next chapter set to 33 Tutorial: Side Path.")
        ctx.go("chapters")
        yield 1500
        ctx.later(ctx.page("chapters")._story_order)
        yield Wait(until=lambda: ctx.toplevel("Story order") is not None, timeout=10_000)
        order = ctx.toplevel("Story order")
        row = next(i for i in range(order._list.size()) if "Tutorial: Side Path" in order._list.get(i))
        order._list.selection_set(row)
        order._list.see(row)
        yield 400
        ctx.grab("07-d-order.png", widget=order, lesson=7,
                 caption="**Story order…**: retail chapters carry a lock and keep their place; the added chapter 33 "
                         "sits between 02 and 03. **Move up** / **Move down** swap it only with another added "
                         "chapter, so here they do nothing.",
                 alt="Story order dialog with locked retail chapters and the unlocked chapter 33 selected between "
                     "02 and 03.")
        order.destroy()
        ctx.go("chapter", "33", "overview")
        yield 2000
        page = ctx.page("chapter")
        page._remove_from_flow(33)
        yield 1500
        ctx.grab("07-e-out.png", lesson=7,
                 caption="After **Take out of the story**: *no chapter leads here: the game never reaches it*. Ch.1 "
                         "leads to 03 again; chapter 33 and its files are still there, listed under **Other "
                         "chapters**.",
                 alt="Overview of chapter 33 after Take out of the story, with the unreachable note.")
        ctx.later(page._delete_chapter)
        yield wait_route(ctx, "chapters")
        yield 1500
    finally:
        yield from restore_chapters(ctx, snapshot)


# -- 08 Campaign wizard: three chapters and one character, then everything put back --
@step("08")
def lesson_08(ctx: Ctx):
    snapshot = chapter_snapshot(ctx)
    try:
        ctx.go("chapters")
        yield 1500
        ctx.later(ctx.page("chapters")._new_campaign)
        yield Wait(until=lambda: ctx.toplevel("New campaign") is not None, timeout=20_000)
        dialog = ctx.toplevel("New campaign")
        dialog._add_chapter_row()
        dialog._add_chapter_row()
        plan = [("Tutorial: Border Watch", "(02)", False), ("Tutorial: The Ford", "(03)", True),
                ("Tutorial: Old Fort", "(04)", False)]
        for (_row, title, template, blank), (name, source, empty) in zip(dialog._chapter_rows, plan):
            title.set(name)
            template.set(next(k for k in dialog._templates if k.endswith(source)))
            blank.set(empty)
        dialog._add_cast_row()
        _row, pid, name, template = dialog._cast_rows[0]
        pid.set("PID_TUTORIAL_SCOUT")
        name.set("Scout")
        template.set(next(k for k in dialog._characters if "(PID_BOLE)" in k))
        yield 600
        ctx.grab("08-a-setup.png", widget=dialog, lesson=8,
                 caption="**New campaign…**: **Played after** the last story chapter (31, Endgame), three chapter "
                         "rows (copies of 02, 03 with **Empty** ticked, and 04) and one row under **Characters "
                         "(optional)**: `PID_TUTORIAL_SCOUT`, *Scout*, a copy of Boyd.",
                 alt="New campaign dialog with three filled chapter rows, one character row, Add chapter row, Add "
                     "character row, Create campaign and Cancel.")
        ctx.button(dialog, "Create campaign").invoke()
        yield wait_route(ctx, "chapter", "33")
        yield wait_chapter_indexed(ctx, "35")
        ctx.go("chapter", "33", "overview")
        yield 2500
        ctx.grab("08-c-first.png", lesson=8,
                 caption="The campaign's first chapter, 33 *Tutorial: Border Watch*, opens: **Played after** *31 · "
                         "Endgame: Repatriation*, **Next chapter** *34 · Tutorial: The Ford*. Endgame no longer "
                         "leads to the ending but to 33; 35 leads to the ending.",
                 alt="Overview of chapter 33 Tutorial: Border Watch with its story flow from 31 to 34.")
        ctx.go("chapter", "34", "overview")
        yield 2500
        ctx.grab("08-d-empty.png", lesson=8,
                 caption="Chapter 34, made with **Empty**: the cast keeps only the player sections (*Player "
                         "units*); the enemies of Ch.2 are gone, their sections kept empty so the copied script "
                         "still finds them.",
                 alt="Overview of chapter 34 Tutorial: The Ford whose cast shows only the player units.")
        ctx.go("chapters")
        yield 2000
        hub_page = ctx.page("chapters")
        hub_page._scroll.update_idletasks()
        hub_page._scroll._canvas.yview_moveto(1.0)
        yield 800
        ctx.grab("08-b-result.png", lesson=8,
                 caption="**Chapters** after **Create campaign**: the three new chapters close the story as *#32*, "
                         "*#33* and *#34*, after Endgame.",
                 alt="Chapters page scrolled to the end of the story with the three added chapter cards.")
        ctx.later(hub_page._story_order)
        yield Wait(until=lambda: ctx.toplevel("Story order") is not None, timeout=10_000)
        order = ctx.toplevel("Story order")
        row = next(i for i in range(order._list.size()) if "Tutorial: The Ford" in order._list.get(i))
        order._list.selection_set(row)
        order._move(1)
        yield 400
        ctx.grab("08-e-order.png", widget=order, lesson=8,
                 caption="**Story order…** after selecting 34 and **Move down**: the three added chapters can be "
                         "reordered among themselves (here 33, 35, 34). **Apply** would rewrite the links; this run "
                         "closes with **Cancel**.",
                 alt="Story order dialog with the three unlocked added chapters at the end, 34 moved below 35.")
        order.destroy()
        ctx.go("character", "PID_TUTORIAL_SCOUT", "stats")
        yield 2500
        ctx.grab("08-f-cast.png", lesson=8,
                 caption="The campaign's character `PID_TUTORIAL_SCOUT`: a copy of Boyd with its own name key "
                         "`MPID_TUTORIAL_SCOUT` (*Scout*). No chapter deploys it yet.",
                 alt="Character page of PID_TUTORIAL_SCOUT with Boyd's class and stats and the name Scout.")
    finally:
        yield from restore_chapters(ctx, snapshot)


def current_tab(notebook: ttk.Notebook) -> tk.Misc:
    return notebook.nametowidget(notebook.select())


def click_card(ctx: Ctx, root: tk.Misc, title: str) -> None:
    """Click the first hub/grid card whose title is ``title``."""
    from fe_modding.gui.widgets import Card
    for card in ctx.find(root, Card):
        if any(str(label.cget("text")) == title for label in ctx.find(card, tk.Label)):
            card._on_click()
            return
    raise LookupError(f"no card {title!r}")


def build_tab(ctx: Ctx, chapter: str = "01"):
    """Open a chapter's Build tab and return its MapBuilder."""
    ctx.go("chapter", chapter, "build")
    return ctx.page("chapter")._build


def reindex(ctx: Ctx):
    """Rebuild the project index (after adding files) and wait for it."""
    old = ctx.shell.index
    ctx.shell.rebuild_index()
    yield Wait(until=lambda: ctx.shell.index is not old, timeout=180_000)
    yield 800


def set_variant(builder, name: str) -> None:
    """Show one deployment file (Common, Normal, Hard, Maniac) on the Build tab."""
    builder._variant_var.set(name)
    builder._variant_changed()


def find_unit(builder, match: Optional[str] = None, *, enemy: bool = False) -> tuple[str, int]:
    """(section, index) of the first unit of the open deployment file whose fields contain ``match``;
    with ``enemy``, the first unit of the largest section that is not the player's (``mikata``)."""
    doc = builder._doc()
    sections = [s for s in doc.sections if not s.is_link and s.units]
    if enemy:
        sections = [s for s in sections if "mikata" not in s.name] or sections
    if match is None:
        largest = max(sections, key=lambda s: len(s.units))
        return largest.name, 0
    for section in sections:
        for index, unit in enumerate(section.units):
            if any(match in str(value) for value in unit):
                return section.name, index
    raise LookupError(f"no unit {match!r} in {[s.name for s in sections]}")


def set_layers(builder, **on) -> None:
    for key, value in on.items():
        builder._layer_vars[key].set(value)
    builder._layers_changed()


def sample_portrait(folder: Path) -> Path:
    """An original placeholder bust (helmeted guard, flat colours) for the portrait lesson."""
    from PIL import Image, ImageDraw
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "tutorial_guard_body.png"
    image = Image.new("RGBA", (192, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    d.polygon([(40, 128), (60, 92), (132, 92), (152, 128)], fill=(70, 86, 120, 255))      # shoulders
    d.rectangle([84, 78, 108, 96], fill=(222, 180, 150, 255))                            # neck
    d.ellipse([66, 26, 126, 90], fill=(232, 192, 160, 255))                              # face
    d.chord([62, 14, 130, 70], 180, 360, fill=(150, 156, 168, 255))                      # helmet
    d.rectangle([62, 40, 130, 46], fill=(120, 126, 140, 255))                            # brim
    d.ellipse([80, 54, 88, 62], fill=(40, 40, 50, 255))
    d.ellipse([104, 54, 112, 62], fill=(40, 40, 50, 255))                                # eyes
    d.line([(88, 76), (104, 76)], fill=(150, 80, 70, 255), width=2)                      # mouth
    image.save(path)
    return path


# -- 11 Portraits --
@step("11")
def lesson_11(ctx: Ctx):
    from fe_modding.gui.portrait_viewer import NewPortraitDialog
    ctx.go("asset", "portraits", "IKE")
    yield 2500
    viewer = ctx.page("asset")._panels["portraits"]
    ctx.grab("11-viewer.png", lesson=11,
             caption="**Assets › Portraits** with `FID_IKE` selected: the pictures as the game assembles them, "
                     "**Replace picture…**, and the **Face record (Face/facedata.bin)** with eye and mouth positions.",
             alt="Portraits page with the portrait list, the assembled face preview, replace controls and the face "
                 "record form.")
    body = sample_portrait(ctx.project_dir / "capture_samples")
    exists = (files_root_of(ctx.project) / "Face" / "TGUARD.cms").is_file()
    dialog = NewPortraitDialog(viewer, ctx.shell.session)
    dialog._face_name.set("TGUARD")
    dialog._name_key.set("MPID_TUTORIAL_GUARD")
    dialog._pid.set(GUARD)
    with mock.patch("tkinter.filedialog.askopenfilename", return_value=str(body)):
        ctx.find(dialog, ttk.Button, "Choose")[0].invoke()  # the small portrait's body picture
    yield 500
    print("body picture:", dialog._files.get("small_body"))
    if exists:
        ctx.grab("11-a-setup.png", widget=dialog, lesson=11,
                 caption="**New portrait…**: name `TGUARD` (makes `FID_TGUARD` and `FID_L_TGUARD`), the nameplate key, "
                         "**Use for character** `PID_TUTORIAL_GUARD`, and one body picture. Mouth and eye frames are "
                         "optional; without them the face does not animate.",
                 alt="New portrait dialog with name, name key and character fields, the small and large portrait "
                     "picture rows with Choose buttons, position spinboxes and the menu face row.")
        dialog.destroy()
    else:
        ctx.grab("11-a-setup.png", widget=dialog, lesson=11,
                 caption="**New portrait…**: name `TGUARD` (makes `FID_TGUARD` and `FID_L_TGUARD`), the nameplate key, "
                         "**Use for character** `PID_TUTORIAL_GUARD`, and one body picture. Mouth and eye frames are "
                         "optional; without them the face does not animate.",
                 alt="New portrait dialog with name, name key and character fields, the small and large portrait "
                     "picture rows with Choose buttons, position spinboxes and the menu face row.")
        dialog._create()
        yield 1500
    from fe_modding.formats import fe8data
    session = ctx.shell.session
    index = session.character_index(GUARD)
    if session.fe8.characters[index].fid != "FID_TGUARD":
        session.data = fe8data.patch_character_field(session.data, index, "fid", "FID_TGUARD")
        session.changed(None)
    if session.dirty:
        session.save()
    yield from reindex(ctx)  # the character page reads face files from the index
    ctx.go("character", GUARD, "look")
    yield 2500
    ctx.grab("11-b-result.png", lesson=11,
             caption="`PID_TUTORIAL_GUARD`'s **Portrait & models** tab after **Create** and saving FE8Data.bin: the "
                     "character resolves `FID_TGUARD`. This is the app's assembled preview, not the game.",
             alt="Portrait and models tab of PID_TUTORIAL_GUARD showing the new placeholder face and the model list.")


# -- 12 Character model slot --
@step("12")
def lesson_12(ctx: Ctx):
    snapshot = Snapshot(ctx, ["extracted/files/FE8Data.bin", "extracted/files/FE8Anim.bin", "extracted/files/zdbx.cmp"],
                        ["extracted/files/ymu", "extracted/files/zu", "originals"])
    try:
        ctx.go("character", GUARD, "look")
        yield 2000
        ctx.grab("12-look.png", lesson=12,
                 caption="**Portrait & models** answers which models a character gets: *Battle model* `zu/fig1` via "
                         "Fighter, *Map model* `ymu/fighter` via `AID_FIGHTER_BO`, and the promoted pair. Every Fighter "
                         "shares `zu/fig1`; Boyd and his copy share `AID_FIGHTER_BO`.",
                 alt="Portrait and models tab listing battle model, promoted battle model, map model and promoted map "
                     "model with their sources and Open in 3D Models buttons.")
        # a map model of its own
        ctx.go("asset", "models", "ymu/fighter")
        yield 3500
        viewer = ctx.page("asset")._panels["models"]
        ctx.later(viewer._new_slot)
        yield Wait(until=lambda: ctx.toplevel("New slot from") is not None, timeout=20_000)
        dialog = ctx.toplevel("New slot from")
        dialog._source_aid.set("AID_FIGHTER_BO")
        dialog._new_name.set("AID_TGUARD")
        dialog._folder.set("tguard")
        dialog._pid.set(GUARD)
        yield 500
        ctx.grab("12-a-setup.png", widget=dialog, lesson=12,
                 caption="**New slot…** on `ymu/fighter`: **Copy animation ID** `AID_FIGHTER_BO` (Boyd's), **New "
                         "animation ID** `AID_TGUARD`, **New folder** `tguard` (its own copy of the files), "
                         "**Character** `PID_TUTORIAL_GUARD`, **Promoted model** off.",
                 alt="New slot dialog for a map model with the copied animation ID, new ID, new folder, character "
                     "and promoted fields, Create and Cancel.")
        ctx.button(dialog, "Create").invoke()
        yield 2500
        # a battle model of its own
        ctx.go("asset", "models", "zu/fig1")
        yield 3500
        ctx.later(viewer._new_slot)
        yield Wait(until=lambda: ctx.toplevel("New slot from") is not None, timeout=20_000)
        dialog = ctx.toplevel("New slot from")
        dialog._new_name.set("tgd1")
        dialog._pid.set(GUARD)
        dialog._character_picked()
        yield 500
        ctx.grab("12-c-battle.png", widget=dialog, lesson=12,
                 caption="**New slot…** on `zu/fig1`: **New model code** `tgd1`, **Character** `PID_TUTORIAL_GUARD`, "
                         "**Class** `JID_FIGHTER` (filled from the character). **Create** copies the model and adds the "
                         "job-list line `JID_FIGHTER+PID_TUTORIAL_GUARD`.",
                 alt="New slot dialog for a battle model with the model code, character and class fields.")
        ctx.button(dialog, "Create").invoke()
        yield 2500
        ctx.later(viewer._model_tables)
        yield Wait(until=lambda: ctx.toplevel("Model tables") is not None, timeout=20_000)
        tables = ctx.toplevel("Model tables")
        tables._check_pid.set(GUARD)
        tables._check_character()
        ctx.select_row(tables, "PID_TUTORIAL_GUARD")
        yield 1200
        ctx.grab("12-b-result.png", widget=tables, lesson=12,
                 caption="**Model tables…**, **Battle job list**: the new line `JID_FIGHTER+PID_TUTORIAL_GUARD` → "
                         "`tgd1`. **Which models does a character get?** with `PID_TUTORIAL_GUARD`: battle `zu/tgd1`, "
                         "map from `AID_TGUARD`. Boyd still gets `zu/fig1` and `AID_FIGHTER_BO`.",
                 alt="Model tables dialog with the battle job list, the new character line selected and the result "
                     "of Which models does a character get.")
        tables.destroy()
        ctx.go("character", GUARD, "look")
        yield 2500
        ctx.grab("12-d-look.png", lesson=12,
                 caption="The Guard's **Portrait & models** after both slots: *Battle model* `zu/tgd1`, *Map model* "
                         "`ymu/tguard` via `AID_TGUARD`. The promoted rows are unchanged: the slots were made for the "
                         "unpromoted state only.",
                 alt="Portrait and models tab of the Guard with its own battle and map models.")
    finally:
        ctx.go("home")
        yield 500
        snapshot.restore()
        ctx.shell.session.revert()
        yield from reindex(ctx)
        print("model files restored", flush=True)


# -- 13 Supports --
@step("13")
def lesson_13(ctx: Ctx):
    ctx.go("character", "PID_IKE", "supports")
    yield 2000
    page = ctx.page("character")
    tab = current_tab(page._notebook)
    trees = ctx.find(tab, ttk.Treeview)
    tree = trees[0]
    first = tree.get_children()[0]
    tree.selection_set(first)
    tree.event_generate("<<TreeviewSelect>>")
    yield 800
    ctx.grab("13-a-setup.png", lesson=13,
             caption="Ike's **Supports** tab with a partner selected: the pair's C/B/A thresholds, the conversation "
                     "buttons and **Add bond with**. Both partners hold their own copy of the pair.",
             alt="Supports tab with the partner list, affinity, thresholds per rank, conversation buttons and the "
                 "bond section.")


@step("13-pair")
def lesson_13_pair(ctx: Ctx):
    snapshot = Snapshot(ctx, ["extracted/files/FE8Data.bin"], ["originals"])
    try:
        ctx.go("character", GUARD, "supports")
        yield 2500
        panel = ctx.page("character")._supports
        panel._add_partner.set("PID_OSCAR")
        panel._add_partner_pair()
        yield 1200
        for (var, _entry), value in zip(panel._thresholds, ("4", "10", "18")):
            var.set(value)
        panel._apply_thresholds()
        yield 1200
        ctx.grab("13-c-pair.png", lesson=13,
                 caption="The Guard's **Supports** after **Add partner** `PID_OSCAR` › **Add**: the pair starts at "
                         "*1 / 3 / 5*; here **C at** 4, **B at** 10, **A at** 18. **Conversation** offers **Create C**, "
                         "**Create B**, **Create A**: no `MYELL_` scene exists yet.",
                 alt="Supports tab of the Guard with Oscar as partner, the thresholds and the conversation buttons.")
        ctx.go("character", "PID_OSCAR", "supports")
        yield 2500
        ctx.select_row(ctx.page("character")._supports, "PID_TUTORIAL_GUARD")
        yield 1000
        ctx.grab("13-b-result.png", lesson=13,
                 caption="Oscar's **Supports**: the same pair, written to both lists with the same thresholds, in the first empty slot of Oscar's list (2). Its **Bonus at A (each unit)** is *Attack +1, Hit +7, Avoid +15* (Fire with Earth). **Remove partner** on either side removes both and leaves the slots empty.",
                 alt="Supports tab of Oscar with the new Guard pair selected among his partners.")
    finally:
        ctx.go("home")
        yield 500
        snapshot.restore()
        ctx.shell.session.revert()
        yield from reindex(ctx)


TALK_EVENT = """

@on_talk(pid1="PID_IKE", pid2="PID_TUTORIAL_GUARD", flag=0, name="TUTORIAL_GUARD_JOINED")
def TutorialGuardTalk():
    TalkEvent("MS_02_TK_GUARD")
    UnitTransferToForceByPID("PID_TUTORIAL_GUARD", 0)
    set("TUTORIAL_GUARD_JOINED")
"""


@step("14")
def lesson_14(ctx: Ctx):
    snapshot = Snapshot(ctx, ["extracted/files/Scripts/C02.cmb", "extracted/files/zmap/bmap02/dispos.cmp"],
                        ["originals", "script_sources"])
    try:
        yield Wait(until=lambda: ctx.shell.index is not None, timeout=180_000)
        builder = build_tab(ctx, "02")
        yield 4000
        set_variant(builder, "Normal")
        yield 2500
        builder._select(("unit", *find_unit(builder, "PID_ZAWANAR")))
        yield 1500
        ctx.grab("14-d-boss.png", lesson=14,
                 caption="Ch.1's boss, Zawana (`PID_ZAWANAR`, `bmap02_first_n`), selected on **Build** (*Normal*): "
                         "**Faction** *Enemy*, his flags and items, and his AI further down. Nothing in the record "
                         "says *boss*: his quotes and death event are in the script.",
                 alt="Build tab of Ch.1 with the boss selected and his deployment fields in the selection panel.")
        section, index = find_unit(builder, "PID_BANDIT_MOU")
        builder._select(("unit", section, index))
        yield 1200
        builder._form_vars["pid"].set_label(GUARD)
        yield 500
        ctx.grab("14-a-setup.png", lesson=14,
                 caption="One Ch.1 bandit (`bmap02_first_n`, *Normal*, tile 3, 12) turned into the Guard: **Character** `PID_TUTORIAL_GUARD`, **Faction** *Enemy*. **Class** stays *Myrmidon*: the deployment's class wins over the character's. **Apply**, then **Save Chapter**.",
                 alt="Build tab of Ch.1 with an enemy bandit selected and PID_TUTORIAL_GUARD in its Character field.")
        builder._apply_unit(section, index)
        yield 800
        builder.save_chapter()
        yield 1500
        ctx.go("chapter", "02", "script")
        yield 2500
        script = ctx.page("chapter")._script
        source = script.chapter_source()
        source = source.replace('    RegistLocationFlags()\n', '    regist("TUTORIAL_GUARD_JOINED")\n'
                                '    RegistLocationFlags()\n', 1) + TALK_EVENT
        script.edit_chapter_source(source, select="TutorialGuardTalk")
        yield 1500
        script._check()
        yield 1500
        ctx.grab("14-c-talk.png", lesson=14,
                 caption="The talk event at the end of `C02.cmb`, after **Check**: `@on_talk(pid1=\"PID_IKE\", "
                         "pid2=\"PID_TUTORIAL_GUARD\", flag=0, name=\"TUTORIAL_GUARD_JOINED\")` plays the message, "
                         "moves the Guard to the player army (force 0) and sets the one-time flag, registered in "
                         "`Startup`.",
                 alt="Script tab of Ch.1 with the new TutorialGuardTalk function and its on_talk trigger.")
        script.save()
        yield 1500
        yield from reindex(ctx)
        ctx.go("character", GUARD, "scripts")
        yield 3000
        ctx.grab("14-b-result.png", lesson=14,
                 caption="After **Save** and **Save Chapter**, the Guard's **Script references** lists Ch.1's `TutorialGuardTalk`, and **Appearances** lists its `bmap02_first_n` row: the script and the deployment now agree.",
                 alt="Script references tab of the Guard listing the Ch.1 talk function.")
    finally:
        ctx.go("home")
        yield 500
        snapshot.restore()
        page = ctx.shell.existing_page("chapter")
        if page is not None:
            page._chapter = None
            for panel in page.panels():
                panel._dirty = False
        yield from reindex(ctx)
        print("chapter 02 restored", flush=True)


# -- 15 Remove records: check references first --
@step("15")
def lesson_15(ctx: Ctx):
    ctx.go("character", "PID_BOLE", "appearances")
    yield 3000
    ctx.grab("15-a-setup.png", lesson=15,
             caption="Before removing a record, read its **Appearances**: every deployment row and message that "
                     "names Boyd. **Script references** lists the script functions.",
             alt="Appearances tab of Boyd with the Deployed in table and the Dialogue table.")
    ctx.go("character", "PID_BOLE", "scripts")
    yield 2500
    ctx.grab("15-b-result.png", lesson=15,
             caption="**Script references** for Boyd: the functions that move, talk to or recruit him. A record "
                     "with rows here or in Appearances is still in use.",
             alt="Script references tab listing chapter, function and the PID it uses.")


@step("15-remove")
def lesson_15_remove(ctx: Ctx):
    snapshot = Snapshot(ctx, ["extracted/files/FE8Data.bin"], ["originals"])
    try:
        ctx.go("character", GUARD, "stats")
        yield 2000
        ctx.page("character")._form._remove()
        yield 1000
        ctx.shell.session.save()
        yield from reindex(ctx)
        ctx.go("characters")
        yield 1000
        hub = ctx.page("characters")
        hub._category.set("all")
        hub._query.set("TUTORIAL")
        yield 1500
        ctx.grab("15-c-removed.png", lesson=15,
                 caption="After **Remove** on the Guard (nothing named it, and it was the last record, so no other "
                         "record moved) and **Save FE8Data.bin**: **Characters** finds nothing for *TUTORIAL*. Its "
                         "name text `MPID_TUTORIAL_GUARD` and portrait `FID_TGUARD` are still in the project.",
                 alt="Characters page with the search TUTORIAL and no matching card.")
        hub._query.set("")
        hub._category.set("playable")
    finally:
        ctx.go("home")
        yield 500
        snapshot.restore()
        ctx.shell.session.revert()
        yield from reindex(ctx)


# -- 16-20 Game Data --
@step("16")
def lesson_16(ctx: Ctx):
    ctx.go("data")
    yield 1200
    ctx.grab("16-data-hub.png", lesson=16,
             caption="**Game Data**: classes, items, skills, terrain, general rules and supports, then script flags, "
                     "AI and rect RIDs. All but the last three are records in FE8Data.bin.",
             alt="Game Data hub with tiles for Classes, Items, Skills, Terrain, General, Supports, Flags, AI and Rect "
                 "RIDs.")
    ctx.go("data", "classes", "JID_FIGHTER")
    yield 2500
    ctx.grab("16-a-setup.png", lesson=16,
             caption="**Game Data › Classes** with `JID_FIGHTER`: bases, caps, growths, weapon ranks, movement type and "
                     "**Promotes to**. Every Fighter in the game uses this record.",
             alt="Classes tab with the class list and the Fighter form.")


@step("74")
def lesson_74(ctx: Ctx):
    ctx.go("data", "classes", "JID_BEAST_C/F")
    yield 2500
    ctx.grab("74-a-setup.png", lesson=74,
             caption="**Game Data › Classes**, `JID_BEAST_C/F` (*Beast Tribe*, Lethe's class in human form): **Promotes to "
                     "/ linked class** `JID_CAT/F`, the class the unit becomes when it transforms, and the innate skills "
                     "`SID_ANIMALIZE` and `SID_HIGHER`. No innate weapon in this form.",
             alt="Classes tab with the Beast Tribe class, its linked class and innate skills.")
    ctx.go("data", "classes", "JID_CAT/F")
    yield 2500
    ctx.grab("74-c-cat.png", lesson=74,
             caption="The linked class `JID_CAT/F` (*Cat*): it links back to `JID_BEAST_C/F`, its **Innate weapon** is "
                     "`IID_CATNAIL` (*Claw*: fang, 8 might, 90 hit) and it adds `SID_LYCANTHROPE`, the transformed "
                     "state. Its stats are the transformed unit's.",
             alt="Classes tab with the Cat class, its linked class, innate weapon and innate skills.")
    ctx.go("character", "PID_LETHE", "stats")
    yield 2500
    ctx.grab("74-b-result.png", lesson=74,
             caption="Lethe's **Stats**: **Class (JID)** `JID_BEAST_C/F`, **Transform gauge** 16 (she starts four "
                     "points from transforming) and the personal skill `SID_EQUIPFANG`.",
             alt="Character page of Lethe with her class, transform gauge and skills.")


@step("75")
def lesson_75(ctx: Ctx):
    ctx.go("data", "items", "IID_SLEEP")
    yield 2500
    ctx.grab("75-a-setup.png", lesson=75,
             caption="**Game Data › Items**, `IID_SLEEP`: weapon type and attack type *rod* (staff), rank B, **Hit** 65, "
                     "range 1–255 (255: Magic / 2), 3 uses, weapon EXP 5, the spell effect `EID_SLEEP`. What the "
                     "staff does belongs to its ID, not to these fields.",
             alt="Items tab with the Sleep staff's record.")
    ctx.go("data", "ai")
    yield 3000
    from fe_modding.gui.cp_data_editor import CpDataPanel
    cp = next(w for w in ctx.find(ctx.page("data"), CpDataPanel))
    ctx.tab(cp._notebook, "Heal")
    yield 1500
    ctx.select_row(cp, "")
    yield 1200
    ctx.grab("75-c-heal.png", lesson=75,
             caption="**Game Data › AI (CP)**, **Heal**: the retreat rules an AI unit follows to heal itself. `SEQ_NOHEAL` selected: **Retreat below HP %** 0, **Stop retreating at HP %** 0, **Try healing items first (0/1)** 1. Healing others is part of the attack scripts (`use_staff(chance=100)`).",
             alt="AI page on the Heal tab with the list of heal records and the selected one's fields.")


@step("17")
def lesson_17(ctx: Ctx):
    ctx.go("data", "items", "IID_IRONAXE")
    yield 2500
    ctx.grab("17-a-setup.png", lesson=17,
             caption="**Game Data › Items** with the Iron Axe: weapon type and rank, might, hit, weight, range, uses, "
                     "price, and the battle model links.",
             alt="Items tab with the item list and the Iron Axe form.")


@step("18")
def lesson_18(ctx: Ctx):
    ctx.go("data", "skills", "SID_TEMPER")
    yield 2500
    ctx.grab("18-a-setup.png", lesson=18,
             caption="**Game Data › Skills** with Tempest (`SID_TEMPER`, Boyd's skill): capacity, icon and the lists of "
                     "who can and cannot have it. Effects are tied to the table position, so skills are edited, "
                     "not added.",
             alt="Skills tab with the skill list and the selected skill's form.")


@step("19")
def lesson_19(ctx: Ctx):
    ctx.go("data", "terrain")
    yield 2500
    click_card(ctx, ctx.page("data"), "Tree")
    yield 1500
    ctx.grab("19-a-setup.png", lesson=19,
             caption="**Game Data › Terrain** with a forest type selected: avoid, defence, healing and one movement "
                     "cost per movement type.",
             alt="Terrain tab with the terrain list and the movement cost table of the selected type.")


@step("20")
def lesson_20(ctx: Ctx):
    ctx.go("data", "general")
    yield 2500
    ctx.grab("20-a-setup.png", lesson=20,
             caption="**Game Data › General**: the difficulty constants, army groups and battle skies.",
             alt="General tab with the difficulty table, army groups and battle skies.")


# -- 21-28 Maps (the Prologue, bmap01) --
@step("21")
def lesson_21(ctx: Ctx):
    builder = build_tab(ctx)
    yield 3500
    set_layers(builder, terrain=False, heights=False, grid=True, props=True, zones=True, units=True)
    builder._select(None)
    yield 1200
    ctx.grab("21-a-setup.png", lesson=21,
             caption="The Prologue's **Build** tab: **Save Chapter**, **Play…**, **Undo/Redo**, the difficulty file "
                     "(**Common**) and section filter, the tool column on the left, the layer checkboxes under the map "
                     "and the selection panel on the right.",
             alt="Build tab with the top bar, tool column, map canvas with units, layer checkboxes and the empty "
                 "selection panel.")
    builder._select(("unit", *find_unit(builder, "PID_BOLE")))
    yield 1500
    ctx.grab("21-b-result.png", lesson=21,
             caption="Clicking a unit selects it: the panel shows its character, class, level, items and AI, with "
                     "**All fields…** for the raw record. Edits here go to the deployment file; **Save Chapter** "
                     "writes them.",
             alt="Build tab with Boyd selected on the map and his deployment fields in the selection panel.")


@step("22")
def lesson_22(ctx: Ctx):
    builder = build_tab(ctx)
    yield 3000
    set_layers(builder, terrain=True, grid=True, units=False)
    builder._select(None)
    builder._choose_tool("terrain")
    yield 1500
    ctx.grab("22-a-setup.png", lesson=22,
             caption="**Paint terrain** with the **Terrain** layer on: pick a terrain type in the panel, then click or "
                     "drag over tiles (**Fill a rectangle** paints a box). The colours are terrain types, not the "
                     "picture.",
             alt="Build tab with the Paint terrain tool, the terrain overlay on the map and the terrain type list in "
                 "the panel.")
    builder._choose_tool("select")
    set_layers(builder, terrain=False, units=True)


@step("23")
def lesson_23(ctx: Ctx):
    builder = build_tab(ctx)
    yield 3000
    set_layers(builder, heights=True, grid=True, units=False)
    builder._choose_tool("heights")
    builder._select(("tile", 8, 7))
    yield 1500
    ctx.grab("23-a-setup.png", lesson=23,
             caption="**Tile heights** on tile (8, 7) with the **Heights** layer on: the panel shows the tile's four "
                     "**Corner heights (steps)** on each layer and its neighbours' shared corners.",
             alt="Build tab with the Tile heights tool, the heights overlay and the corner height fields of the "
                 "selected tile.")
    builder._choose_tool("select")
    set_layers(builder, heights=False, units=True)


@step("24")
def lesson_24(ctx: Ctx):
    builder = build_tab(ctx)
    yield 3000
    set_layers(builder, props=True, grid=True)
    builder._choose_tool("prop")
    yield 1500
    ctx.grab("24-a-setup.png", lesson=24,
             caption="**Place prop**: choose a prop of this map (or add one from another map or a .glb), its angle, "
                     "then click a tile. A prop is only a picture; paint its footprint with Paint terrain.",
             alt="Build tab with the Place prop tool and the prop list, angle and import buttons in the panel.")
    builder._choose_tool("select")
    ctx.go("asset", "map_objects")
    panel = ctx.page("asset")._panels["map_objects"]
    yield Wait(until=lambda: panel.browser._tree.get_children()
               and "Reading" not in str(panel.browser._status.cget("text")), timeout=300_000)
    yield 800
    ctx.select_row(panel, "bmap01")
    yield 3000
    ctx.grab("24-b-map-objects.png", lesson=24,
             caption="**Assets › Map Objects** lists every prop of every chapter map. Select one to export it, edit "
                     "its bounds and flags, or **Add to this map**.",
             alt="Map Objects page with the prop list across maps and the selected prop's details.")


@step("25")
def lesson_25(ctx: Ctx):
    ctx.go("asset", "models", "zmap/bmap01")
    yield 6000
    ctx.grab("25-a-setup.png", lesson=25,
             caption="**Assets › 3D Models** with the Prologue terrain (`zmap/bmap01`): **Export .glb…** writes the "
                     "terrain (and its `_mask.png`), **Import .glb…** opens the import review before anything is "
                     "written.",
             alt="3D Models page with the zmap/bmap01 set selected and the terrain mesh in the preview.")


@step("27")
def lesson_27(ctx: Ctx):
    ctx.go("chapter", "01", "map_settings")
    yield 3000
    ctx.grab("27-a-setup.png", lesson=27,
             caption="The **Map settings** tab: grid size and border, line colour, lighting, distance fog, weather, "
                     "battle sky and fog of war. **Save Chapter** writes them into the map.",
             alt="Map settings tab with the Grid, Lighting, Distance fog, Weather and Advanced groups.")
    ctx.go("chapter", "01", "chapter_data")
    yield 2500
    ctx.grab("27-b-result.png", lesson=27,
             caption="The **Chapter data** tab: the chapter record in FE8Data.bin, with its title, files, map music, "
                     "the objective text keys per difficulty and the scene backgrounds.",
             alt="Chapter data tab with Identity and files, Objectives text keys and Scenes.")


@step("28")
def lesson_28(ctx: Ctx):
    ctx.go("chapter", "01", "battle")
    yield 2500
    ctx.grab("28-a-setup.png", lesson=28,
             caption="The **Battle scenes** tab: one battle backdrop per terrain type of this map. Blank rows use the "
                     "default shown on the right; **Only terrain types on this map** hides the others.",
             alt="Battle scenes tab with terrain types, tile counts, the battle scene per type and Browse buttons.")


# -- 29-32 Units and deployment --
@step("29")
def lesson_29(ctx: Ctx):
    from fe_modding.gui.map_builder import _AddSectionDialog
    builder = build_tab(ctx, "02")
    yield 4000
    builder.open_disposition()
    yield 2500
    window = builder._windows.get("disposition")
    ctx.grab("29-a-setup.png", widget=window, lesson=29,
             caption="**Units list** for Ch.1: every section of the deployment file with its army and role (player "
                     "army, battle start, reinforcement, scene-only), and the units of the selected section.",
             alt="Units list window with the section list and the unit table.")
    window.destroy()
    dialog = _AddSectionDialog(builder, builder._deploy.group_keys())
    dialog._name_var.set("bmap02_tutorial_wave")
    yield 800
    ctx.grab("29-c-add-section.png", widget=dialog, lesson=29,
             caption="**Add section**: the name the script will load (`bmap02_tutorial_wave`) and the section header "
                     "(army, group). The section is added to each difficulty file.",
             alt="Add section dialog with the name field, section header fields, OK and Cancel.")
    dialog.destroy()


@step("30")
def lesson_30(ctx: Ctx):
    builder = build_tab(ctx, "02")
    yield 4000
    builder._choose_tool("unit")
    yield 1500
    ctx.grab("30-c-add-to.png", lesson=30,
             caption="**Place unit**: **Add to** the **Common file (every difficulty)** or to chosen **Difficulty "
                     "files**, in the chosen section. A unit in the common file appears on every difficulty.",
             alt="Build tab with the Place unit tool and its Add to, difficulty and section choices.")
    builder._choose_tool("select")


@step("31")
def lesson_31(ctx: Ctx):
    builder = build_tab(ctx, "02")
    yield 4000
    set_variant(builder, "Normal")
    yield 2500
    builder._select(("unit", *find_unit(builder, enemy=True)))
    yield 1500
    ctx.grab("31-a-setup.png", lesson=31,
             caption="An enemy of Ch.1 selected: its items with the per-slot drop flag, and its deployment flags. The "
                     "drop flag belongs to the item slot, not to the unit.",
             alt="Build tab with an enemy selected and its item slots and flags in the selection panel.")


@step("33")
def lesson_33(ctx: Ctx):
    from fe_modding.gui.script_editor import InsertCallDialog
    ctx.go("chapter", "01", "script", "func_10")
    yield 3500
    ctx.grab("33-a-setup.png", lesson=33,
             caption="The **Script** tab on the Prologue (`C01.cmb`) with a function selected: the code, the "
                     "**Function** list, **Trigger and description** with **Apply to code**, and **Check**/**Save**.",
             alt="Script tab with the decompiled code, the function list, the trigger form and the toolbar.")
    editor = ctx.page("chapter")._script
    dialog = InsertCallDialog(editor, editor._externs, editor._local_defs(), editor._name_values)
    dialog.geometry("1180x560")
    dialog._query.set("TalkEvent")
    yield 800
    ctx.select_row(dialog, "TalkEvent")
    yield 800
    ctx.grab("33-c-call-help.png", widget=dialog, lesson=33,
             caption="**Insert call…**: search the game's script functions; the selected one shows its purpose and "
                     "numbered arguments before it is inserted at the cursor.",
             alt="Insert call dialog with the search box, the function tree and the help for the selected call.")
    dialog.destroy()


@step("34")
def lesson_34(ctx: Ctx):
    ctx.go("data", "flags")
    yield 6000
    ctx.grab("34-a-setup.png", lesson=34,
             caption="**Game Data › Flags**: campaign flags (kept in the save) and chapter flags, with their names, "
                     "users and the room left.",
             alt="Flags page with the Campaign flags, Chapter flags and Save file tabs and the flag table.")


@step("36")
def lesson_36(ctx: Ctx):
    ctx.go("asset", "scripts")
    yield 2000
    ctx.grab("36-a-setup.png", lesson=36,
             caption="**Assets › Scripts**: each chapter's script, then the shared scripts (`startup.cmb` with the "
                     "helpers every chapter calls, and the others).",
             alt="Scripts page with the chapter script cards and the shared scripts section.")


# -- 37 Dialogue --
@step("37")
def lesson_37(ctx: Ctx):
    ctx.go("chapter", "01", "dialogue", "MS_01_OP_01")
    yield 4000
    preview = ctx.page("chapter")._dialogue._preview
    for _ in range(2):
        preview._next()
        yield 1500
    ctx.grab("37-a-setup.png", lesson=37,
             caption="The **Dialogue** tab on `MS_01_OP_01`: the message text with its actions highlighted, the "
                     "**Layout** and action buttons, the portrait seats, and **Live Preview**.",
             alt="Dialogue tab with the message list, the text editor, layout and action buttons, the seats and "
                 "the preview.")


def view(ctx: Ctx, name: str, lesson, route: tuple, caption: str, alt: str, *, select: Optional[str] = None,
         wait: int = 2500, after: Optional[Callable] = None):
    """Open ``route``, optionally select a list/tree row containing ``select`` (or call ``after``), grab."""
    ctx.go(*route)
    yield wait
    if select is not None:
        root = ctx.shell._current
        if route[0] == "asset":  # the Assets page keeps every opened tool; search the shown one only
            root = root._panels[route[1]]
        if not ctx.select_row(root, select):
            print(f"  {name}: no row {select!r}")
        yield 2000
    if after is not None:
        result = after()
        if isinstance(result, Iterator):
            yield from result
        yield 1500
    ctx.grab(name, lesson=lesson, caption=caption, alt=alt)


def select_rid(ctx: Ctx, rid: str) -> None:
    from fe_modding.gui.rect_images import RectImagesPanel
    panel = ctx.find(ctx.page("data"), RectImagesPanel)[0]
    names = list(panel._rid_list.get(0, "end"))
    row = next(i for i, name in enumerate(names) if rid in str(name))
    panel._rid_list.selection_clear(0, "end")
    panel._rid_list.selection_set(row)
    panel._select_rid()


@step("35")
def lesson_35(ctx: Ctx):
    yield from view(ctx, "35-a-setup.png", 35, ("chapter", "02", "script", "func_3"),
                    "A village recipe in Ch.1's script: the visit trigger, the guard flag test, the reward and the "
                    "flag set at the end, so the visit runs once.",
                    "Script tab of Ch.1 with a village visit function selected and its trigger in the form.")


@step("38")
def lesson_38(ctx: Ctx):
    yield from view(ctx, "38-a-setup.png", 38, ("asset", "backgrounds"),
                    "**Assets › Backgrounds** with a conversation background selected: its layers, the rect "
                    "resource that shows it, and the replace controls.",
                    "Backgrounds page with the file list and the selected background's preview.", select="RID_")
    yield from view(ctx, "72-a-setup.png", 72, ("data", "rect_images"),
                    "**Game Data › Rect RIDs**: the RIDs of a rect file, the layers of the selected RID, its "
                    "properties and preview, and where it is **Referenced in**.",
                    "Rect RIDs page with the rect file choice, the RID list, layers, properties and preview.",
                    after=lambda: select_rid(ctx, "RID_END_BOLE"))


@step("72")
def lesson_72(ctx: Ctx):
    ctx.go("data", "rect_images")
    yield 2500
    select_rid(ctx, "RID_END_BOLE")
    yield 2000
    from fe_modding.gui.rect_images import RectImagesPanel
    panel = ctx.find(ctx.page("data"), RectImagesPanel)[0]
    panel._edit()
    yield Wait(until=lambda: ctx.toplevel("Edit RID_END_BOLE") is not None, timeout=10_000)
    dialog = ctx.toplevel("Edit RID_END_BOLE")
    if dialog._parts.size() > 1:
        dialog._parts.selection_clear(0, "end")
        dialog._parts.selection_set(1)
        dialog._select(None)
    yield 2000
    ctx.grab("72-c-edit.png", widget=dialog, lesson=72,
             caption="**Edit RID…** on `RID_END_BOLE`, Boyd's epilogue picture: **RID settings** and its one layer on the "
                     "left, *Layer 0: Rect* selected and its **Properties** in the middle, the **Illustrative preview "
                     "(608 × 448)** on the right. **Apply** saves the rect file; **Revert** drops the edits.",
             alt="Edit RID dialog with the layer list, the properties of the selected layer and the preview.")
    dialog.destroy()
    yield 300


@step("39")
def lesson_39(ctx: Ctx):
    yield from view(ctx, "39-a-setup.png", 39, ("asset", "fonts"),
                    "**Assets › Fonts**: the five text fonts with their glyph sheets. Inline codes in a message can "
                    "switch between them.",
                    "Fonts page with the font list and the selected font's glyph sheet.", select="")


@step("40")
def lesson_40(ctx: Ctx):
    yield from view(ctx, "40-a-setup.png", 40, ("asset", "conversations"),
                    "**Assets › Conversations**: every message file, the chapters' and the shared ones (base "
                    "conversations, world-map narration, support talks).",
                    "Conversations page with the chapter message files and the shared message files.")


@step("41")
def lesson_41(ctx: Ctx):
    yield from view(ctx, "41-a-setup.png", 41, ("chapter", "02", "script", "Opening0"),
                    "Ch.1's `Opening0`: the opening sequence the chapter runs first, with its `ChapterMoviePlay` "
                    "title card and opening scenes.",
                    "Script tab of Ch.1 with the Opening0 function selected.")


@step("43")
def lesson_43(ctx: Ctx):
    yield from view(ctx, "43-a-setup.png", 43, ("data", "ai"),
                    "**Game Data › AI (CP)**: the AI scripts of `cp_data.bin` in the readable AI language, with the "
                    "**Readable/Raw** view, **Apply** and the units that use the selected script.",
                    "AI page with the script list and the readable AI code of the selected script.", select="SEQ_")


@step("44")
def lesson_44(ctx: Ctx):
    def routes():
        page = ctx.shell._current
        for notebook in ctx.find(page, ttk.Notebook):
            for tab_id in notebook.tabs():
                if "Routes" in notebook.tab(tab_id, "text"):
                    notebook.select(tab_id)
                    return
    yield from view(ctx, "44-a-setup.png", 44, ("data", "ai"),
                    "The AI page's **Routes & targets**: target lists that attack and move orders name, and the "
                    "**Items an AI thief may steal**.",
                    "AI page on the Routes and targets tab with target lists and the thief item list.", after=routes)


@step("46")
def lesson_46(ctx: Ctx):
    yield from view(ctx, "46-a-setup.png", 46, ("chapter", "05", "shops"),
                    "A chapter's **Shops** tab: the armory and vendor stock per difficulty, the forge grid, **Copy to "
                    "other difficulties** and **Save Shops**.",
                    "Shops tab with the difficulty choice, armory and vendor lists and the forge section.")


@step("47")
def lesson_47(ctx: Ctx):
    yield from view(ctx, "47-a-setup.png", 47, ("asset", "music"),
                    "**Assets › Music** with a track selected: **Play/Stop**, **Export WAV…**, **Import Replacement "
                    "Audio…**, the track's **Music cues** and **New track…**.",
                    "Music page with the track list and the selected track's controls and cues.",
                    select="gcfe_bgm_evt_ike1")
    yield from view(ctx, "73-tracks.png", 73, ("asset", "sound_room_tracks"),
                    "**Assets › Soundroom Tracks**: the Sound Room's 64 music cues, a table in `main.dol`. Pick and "
                    "reorder them, then **Save tracks**.",
                    "Soundroom Tracks page with the 64 cue slots.")


@step("48")
def lesson_48(ctx: Ctx):
    yield from view(ctx, "48-a-setup.png", 48, ("asset", "sfx"),
                    "**Assets › Sound Effects** with a cue selected: its sound id, volume, pan, range and group in "
                    "`gcfesnd.bin`, preview and replace.",
                    "Sound effects page with the cue list and the selected cue's parameters.", select="SFX_SYS_SELECT1")


@step("49")
def lesson_49(ctx: Ctx):
    yield from view(ctx, "49-a-setup.png", 49, ("asset", "videos"),
                    "**Assets › Videos** with a THP movie selected: the preview, frame counter, **Replace…** and "
                    "**Add…**. Replacements count against the disc size.",
                    "Videos page with the movie list and the preview of the selected video.", select="opening", wait=3000)


@step("50")
def lesson_50(ctx: Ctx):
    yield from view(ctx, "50-a-setup.png", 50, ("asset", "icons"),
                    "**Assets › Icons**: the icon sheets cut into cells, the selected cell with the records that use "
                    "it, **Export icon…** / **Replace icon…** and the whole-sheet actions.",
                    "Icons page with the sheet choice, the icon grid and the selected icon's details.")
    yield from view(ctx, "50-ui-windows.png", 50, ("asset", "ui_windows"),
                    "**Assets › UI Windows**: every image of the selected texture file as thumbnails; select one to "
                    "read its size and format before **Import Replacement Image…**.",
                    "UI Windows page with the file list and the image thumbnails of the selected file.", select="")
    yield from view(ctx, "73-a-setup.png", 73, ("asset", "tutorials"),
                    "**Assets › Tutorials**: the in-game tutorial list, its groups and order, and the flags that "
                    "unlock each entry (**New game starts with it**).",
                    "Tutorials page with the tutorial list and the selected entry's fields.", select="")
    yield from view(ctx, "73-sound-room.png", 73, ("asset", "sound_room"),
                    "**Assets › Soundroom Images**: the Sound Room slideshow pictures, in order, with their offsets.",
                    "Soundroom Images page with the picture list and preview.", select="")
    yield from view(ctx, "73-staff-credits.png", 73, ("asset", "staff_credits"),
                    "**Assets › Staff Credits**: the end credits lines in three columns; edit, add and reorder, then "
                    "**Save credits**.",
                    "Staff Credits page with the credits lines.")


def sample_tone(folder: Path, seconds: float = 4.0, rate: int = 32000) -> Path:
    """A made-for-the-purpose stereo WAV: an A-minor arpeggio of sine tones (no third-party audio)."""
    import math
    import struct
    import wave
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "tutorial_theme.wav"
    notes = (220.0, 261.63, 329.63, 440.0)
    frames = bytearray()
    for i in range(int(seconds * rate)):
        f = notes[int(i / rate * 4) % len(notes)]
        s = 0.25 * math.sin(2 * math.pi * f * i / rate)
        v = int(max(-1.0, min(1.0, s)) * 32767)
        frames += struct.pack("<hh", v, v)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(bytes(frames))
    return path


def sample_icon(folder: Path) -> Path:
    """A made-for-the-purpose 32 x 32 icon: a round shield."""
    from PIL import Image, ImageDraw
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "tutorial_shield.png"
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    d.ellipse([3, 3, 28, 28], fill=(40, 90, 170, 255), outline=(230, 230, 240, 255), width=2)
    d.rectangle([14, 7, 17, 24], fill=(240, 200, 60, 255))
    d.rectangle([8, 13, 23, 16], fill=(240, 200, 60, 255))
    image.save(path)
    return path


@step("47-new")
def lesson_47_new(ctx: Ctx):
    snapshot = Snapshot(ctx, ["extracted/files/Sound/gcfesnd.bin"], ["extracted/files/Sound", "originals"])
    try:
        wav = sample_tone(ctx.project_dir / "capture_samples")
        ctx.go("asset", "music")
        yield 2500
        viewer = ctx.page("asset")._panels["music"]
        with mock.patch("tkinter.simpledialog.askstring", return_value="tutorial_theme"),                 mock.patch("tkinter.filedialog.askopenfilename", return_value=str(wav)),                 mock.patch("tkinter.simpledialog.askfloat", return_value=1.0):
            viewer._add_new_track()
        yield Wait(until=lambda: ctx.select_row(viewer, "tutorial_theme"), timeout=300_000)
        yield 3000
        ctx.grab("47-c-new.png", lesson=47,
                 caption="After **New track…** with a 4-second test tone made for this lesson (stereo, 32 kHz, loop "
                         "from 1.0 s): `tutorial_theme.stm` is in the list and **Music cues** shows its new cue "
                         "`BGM_TUTORIAL_THEME`. Chapters and scripts play it by that name.",
                 alt="Music page with the new tutorial_theme track selected and its cue BGM_TUTORIAL_THEME.")
    finally:
        ctx.go("home")
        yield 500
        snapshot.restore()


@step("48-import")
def lesson_48_import(ctx: Ctx):
    wav = sample_tone(ctx.project_dir / "capture_samples", seconds=0.6)
    ctx.go("asset", "sfx")
    yield 2500
    viewer = ctx.page("asset")._panels["sfx"]
    ctx.later(viewer._add_cue)
    yield Wait(until=lambda: any(isinstance(w, tk.Toplevel) and w.winfo_exists() and "ound" in w.title()
                                 for w in viewer.winfo_children()), timeout=10_000)
    dialog = next(w for w in viewer.winfo_children() if isinstance(w, tk.Toplevel))
    with mock.patch("tkinter.filedialog.askopenfilename", return_value=str(wav)):
        dialog._choose_file()
    dialog._name_var.set("SFX_TUTORIAL_CHIME")
    yield 1200
    ctx.grab("48-c-import.png", widget=dialog, lesson=48,
             caption="**Add…** on Sound Effects with a 0.6-second test tone made for this lesson: **Audio file** (*32000 "
                     "Hz, 0.60 s (mono), about 11 KB once encoded*), **Cue name** `SFX_TUTORIAL_CHIME`, the **Sound "
                     "group** it is loaded with, **Volume**, **Pan**, **Range**, and the warning that new sounds are "
                     "experimental. **Add** encodes it; this capture stops before.",
             alt="Sound effect import dialog with the audio file, cue name, sound group, warning, Add and Cancel.")
    dialog._close()
    yield 300


@step("50-icon")
def lesson_50_icon(ctx: Ctx):
    icon = sample_icon(ctx.project_dir / "capture_samples")
    ctx.go("asset", "icons")
    yield 2500
    viewer = ctx.page("asset")._panels["icons"]
    sword = next(i for i in ctx.shell.session.fe8.items if i.iid == "IID_IRONSWORD")
    viewer.select_icon(f"item:{sword.icon}")
    yield 1500
    with mock.patch("tkinter.filedialog.askopenfilename", return_value=str(icon)):
        viewer._replace_icon()
    yield 1500
    ctx.grab("50-b-result.png", lesson=50,
             caption="**Replace icon…** on the Iron Sword's cell (*Icon 96 (row 3, column 0)*, 24 × 24, *used by: "
                     "IRONSWORD*) with a 32 × 32 shield drawn for this lesson, stretched to the cell: the sheet "
                     "redraws and the status says *not saved yet*. **Save** writes `window/icon.tpl`; this capture "
                     "uses **Discard changes**.",
             alt="Icons page with the replaced icon cell selected and the not saved yet status.")
    viewer._discard()
    yield 500


# -- 51-55 Models and battle presentation --
@step("51")
def lesson_51(ctx: Ctx):
    yield from view(ctx, "51-viewer.png", 51, ("asset", "models", "zu/fig1"),
                    "**Assets › 3D Models** with the Fighter battle model `zu/fig1`: preview with mesh and skeleton, "
                    "animations, and the export/import buttons (**Export .glb…**, **Export .blend…**, **Import "
                    "…**).",
                    "3D Models page with zu/fig1 selected, the posed model, the Skeleton and Animations tabs and the "
                    "button grid.", wait=6000)


@step("53")
def lesson_53(ctx: Ctx):
    ctx.go("asset", "models", "zu/fig1")
    yield 4000
    viewer = ctx.page("asset")._panels["models"]
    preview = viewer._preview
    notebook = preview._anim_list.master.master
    while not isinstance(notebook, ttk.Notebook):
        notebook = notebook.master
    ctx.tab(notebook, "Animations")
    names = list(preview._anim_list.get(0, "end"))
    row = next((i for i, n in enumerate(names) if "_at1_" in str(n).lower()), 0)
    preview._anim_list.selection_set(row)
    preview._anim_list.see(row)
    preview._on_animation_selected()
    yield 3000
    ctx.grab("53-a-setup.png", lesson=53,
             caption="**3D Models** on `zu/fig1`, the Fighter's battle model, **Animations** tab: **Animation files "
                     "(.ga)** lists the set's clips; the selected attack plays on the skeleton with **Play** / "
                     "**Pause** and its frame counter. **Import animation…** and **Events...** work on this set.",
             alt="3D Models page with the Fighter battle model and its Animations tab, an attack clip selected.")
    ctx.later(viewer._edit_events)
    yield Wait(until=lambda: ctx.toplevel("Events -") is not None, timeout=20_000)
    dialog = ctx.toplevel("Events -")
    choices = list(dialog.children.values())
    yield 1500
    ctx.grab("53-c-events.png", widget=dialog, lesson=53,
             caption="**Events...**: one animation's event track, one key per line (frame and codes). **Frame** and "
                     "**Codes (comma-separated)** with **Add**, **Update**, **Delete**; *0 = the blow lands, 1 = the "
                     "swing (miss), 2 = throw/shot release*: combat waits for these. **Save...** writes the set.",
             alt="Events dialog with the animation choice, the list of event keys, frame and codes fields and the "
                 "Add, Update, Delete, Save and Cancel buttons.")
    dialog.destroy()
    yield 300


@step("54")
def lesson_54(ctx: Ctx):
    yield from view(ctx, "54-a-setup.png", 54, ("asset", "models", "xwp/ironaxe"),
                    "The Iron Axe's weapon model (`xwp/ironaxe`) in **3D Models**: the triangle count under the "
                    "preview is the first budget figure to compare after an import.",
                    "3D Models page with the xwp/ironaxe weapon model selected.", wait=6000)


def _table(ctx: Ctx, key: str):
    return ctx.page("asset")._panels[key]


def _pick(panel, iid: str) -> None:
    panel._tree.selection_set(iid)
    panel._tree.see(iid)
    panel._show_selected()


@step("55")
def lesson_55(ctx: Ctx):
    ctx.go("asset", "battle_weapons")
    yield 2500
    weapons = _table(ctx, "battle_weapons")
    _pick(weapons, "IRONAXE")
    yield 5000
    ctx.grab("55-a-setup.png", lesson=55,
             caption="**Assets › Battle Weapons** with `IRONAXE`: its **Type** (`2 - Axe`), **Flight** (`Melee`), "
                     "**Effect** and **Target effect** (`EID_` names, empty for none), and the model it uses "
                     "(`xwp/IRONAXE/IRONAXE.cmp`) in the preview.",
             alt="Battle Weapons page with IRONAXE selected, its fields, Apply, Restore original, Add weapon and "
                 "the axe model preview.")
    ctx.go("asset", "battle_sceneries")
    yield 2500
    sceneries = _table(ctx, "battle_sceneries")
    _pick(sceneries, "map03_ground01")
    yield 6000
    ctx.grab("55-sceneries.png", lesson=55,
             caption="**Assets › Battle Sceneries** with `map03_ground01`, the plain behind the simulator's "
                     "fights: **Place** (outdoors or indoors), **Footstep effect** and **Footstep sound**, and the "
                     "backdrop model.",
             alt="Battle Sceneries page with map03_ground01 selected, its three fields and its model preview.")
    ctx.go("asset", "battle_params")
    yield 2500
    params = _table(ctx, "battle_params")
    _pick(params, "fig1")
    yield 1500
    ctx.grab("55-c-params.png", lesson=55,
             caption="**Assets › Battle Unit Parameters** with `fig1`, the Fighter's battle model: **Move speed** "
                     "and **Attack range** (engine units), run count, blend durations, and the jump, flying, large "
                     "and finisher flags. An empty box removes the line.",
             alt="Battle Unit Parameters page with fig1 selected and its tuning fields.")
    speed = params._vars["移動速度"].get()
    params._vars["移動速度"].set(f"{float(speed) * 2:g}")
    params._apply()
    yield 1500
    ctx.grab("55-b-result.png", lesson=55,
             caption=f"**Move speed** of `fig1` doubled from {speed} and applied: the row is marked *edited* and the "
                     "status says *Edited model fig1.* The change is written to `zdbx.cmp` at once; **Restore "
                     "original** brings back the vanilla text.",
             alt="Battle Unit Parameters with fig1 marked edited and the changed Move speed.")
    params._restore()
    yield 800


@step("69")
def lessons_69_71(ctx: Ctx):
    from types import SimpleNamespace
    from fe_modding.gui.effect_add_dialog import EffectAddDialog
    # -- 69 visual effects --
    ctx.go("asset", "effects")
    yield 3000
    fx = _table(ctx, "effects")
    fx._tree.selection_set("EID_K_FIRE")
    fx._tree.see("EID_K_FIRE")
    fx._show_selected()
    yield 6000
    ctx.grab("69-a-setup.png", lesson=69,
             caption="**Assets › Visual Effects** with `EID_K_FIRE`, the Fire tome's spell: its registry flags, the "
                     "parts of its `yme/` pack, its particle emitters, its textures and the animated preview.",
             alt="Visual Effects page with EID_K_FIRE selected, its details, buttons, texture thumbnails and the "
                 "effect preview.")
    fx._show_particle_details()
    yield Wait(until=lambda: ctx.toplevel("Particle editor") is not None, timeout=20_000)
    yield 3000
    editor = ctx.toplevel("Particle editor")
    yield 1500  # the editor's own default size and pane layout
    first = next((i for i in editor._tree.get_children() if i.startswith("e:")), None)
    if first is not None:
        editor._tree.selection_set(first)
        editor._tree.focus(first)
        editor._show_fields(first)
    yield 2500
    ctx.grab("69-b-result.png", widget=editor, lesson=69,
             caption="**Edit particles…** on `EID_K_FIRE`: the **Timing events**, the material tracks (alpha, "
                     "colour, texture scroll) and each emitter with its stages, curves and keys. Select one to edit "
                     "its fields, **Apply fields**, then **Save effect**; the preview is approximate.",
             alt="Particle editor window with the particle tree, the selected emitter's fields and the preview.")
    editor.destroy()
    dialog = EffectAddDialog(fx, ctx.project, ctx.shell.changelog, fx._entries, lambda name: None)
    dialog._effect_name.set("EID_TUTORIAL_FIRE")
    dialog._clone.set("EID_K_FIRE")
    dialog._template.set("EID_K_FIRE")
    yield 800
    ctx.grab("69-c-add.png", widget=dialog, lesson=69,
             caption="**Add effect…**: a new `EID_` name, then **Clone effect** (copy an existing pack) or **Import "
                     "pack** (a `.cmp` file), and **Copy flags from** an effect whose registry flags fit.",
             alt="Add visual effect dialog with the effect name, the clone and import choices and the flags source.")
    dialog.destroy()
    # -- 70 battle cameras --
    ctx.go("asset", "battle_cameras")
    yield 2500
    cams = _table(ctx, "battle_cameras")
    cams._script_tree.selection_set("standby")
    cams._script_tree.see("standby")
    cams._show_script()
    yield 1000
    ctx.grab("70-a-setup.png", lesson=70,
             caption="**Assets › Battle Cameras**, **Camera scripts (xcam)** with `standby`, the zoom that opens a "
                     "melee fight: rig `cam1`, four keyframes from distance 170 to 70 over 330 ticks.",
             alt="Battle Cameras page with the script list, the standby script's caption, rig and keyframe table.")
    cams._frame_tree.selection_set("3")
    cams._load_frame_fields()
    cams._frame_vars["dist"].set("110")
    cams._update_frame()
    cams._preview()
    yield 5000
    ctx.grab("70-b-result.png", lesson=70,
             caption="The last keyframe's **Distance** changed from 70 to 110 with **Update keyframe**, then "
                     "**Preview**: the built-in fight (Ike against a Fighter) plays with the edited script, ending "
                     "wider. **Apply script** would write it; nothing is written yet.",
             alt="Battle Cameras page with the edited keyframe and the preview fight playing below.")
    cams._show_script()  # drop the unapplied edit
    notebook = next(w for w in ctx.find(cams, ttk.Notebook))
    _tab_named(notebook, "Camera rigs (camera.dbx)")
    yield 600
    cams._rig_tree.selection_set("cam1")
    cams._show_rig()
    yield 800
    ctx.grab("70-c-rigs.png", lesson=70,
             caption="**Camera rigs (camera.dbx)** with `cam1`, the free camera of the opening: position, rotation, "
                     "distance, look-at offset, speed and the units it follows. **Apply rig** writes one rig; "
                     "**Restore camera.dbx** restores them all.",
             alt="Battle Cameras rigs tab with the rig list and cam1's fields.")
    # -- 71 DBX files and the HUD --
    ctx.go("asset", "dbx_files")
    yield 2500
    dbxp = _table(ctx, "dbx_files")
    dbxp._tree.selection_set("zdbx/battle.dbx")
    dbxp._tree.see("zdbx/battle.dbx")
    dbxp._select()
    yield 1200
    ctx.grab("71-a-setup.png", lesson=71,
             caption="**Assets › DBX Files** with `zdbx/battle.dbx`, the battle screen: **Form** lists each block "
                     "(layers, textures, pictures, numbers, gauges) with its fields and an English note per known "
                     "key.",
             alt="DBX Files page with zdbx/battle.dbx selected and its blocks in the Form tab.")
    _tab_named(dbxp._tabs, "Layout")
    yield 300
    dbxp._refresh_views()
    yield 1500
    layout = dbxp._layout
    canvas = layout._canvas
    from fe_modding.formats import dbx as _dbx
    start = next(b.start for b in _dbx.parse(dbxp._current_text()).blocks() if b.name == "WpWinL")
    doc = _dbx.parse(dbxp._current_text())
    block = next(b for b in doc.blocks() if b.start == start)
    field = next(f for f in block.fields if f.key == "pos")
    doc.set_value(field, "63,129")  # what dragging WpWinL 60 pixels down writes
    dbxp._replace_text(doc.text)
    layout.refresh()
    yield 1200
    ctx.grab("71-b-result.png", lesson=71,
             caption="The **Layout** tab draws every widget with a position on the 640 × 480 screen; `WpWinL`, the "
                     "left weapon window, was dragged down. The text changed (**Save** is enabled), but nothing is "
                     "written until **Save**.",
             alt="DBX Files Layout tab with the battle screen widgets drawn as rectangles and WpWinL moved down.")
    dbxp._dirty = False
    dbxp._open("zdbx/battle.dbx")
    yield 500


# -- 56-64 Test and release --
@step("56")
def lesson_56(ctx: Ctx):
    def setup():
        sim = ctx.page("asset")._panels["battle_sim"]
        sim.select_character("PID_IKE", 0)
        sim.select_character("PID_BOLE", 1)
        sim.distance.set(1)
        sim.mode.set("random")
        sim.seed.set("1")
        sim._clear_choices()
    yield from view(ctx, "56-a-setup.png", 56, ("asset", "battle_sim"),
                    "The baseline fixture: Ike (Ranger, level 1, Iron Sword) attacks Boyd (Fighter, level 2, Iron "
                    "Axe) at **Distance** 1, **Random** with **Seed** 1. The **Forecast**, the **Rolls** list and "
                    "the **Fight** log on the right follow every change at once.",
                    "Battle Simulator with Ike as attacker and Boyd as defender, the forecast, the outcome box, the "
                    "rolls table and the fight log.", after=setup, wait=3000)
    sim = ctx.page("asset")._panels["battle_sim"]
    sim._fix_current()
    yield 800
    first = sim._log.decisions[0]
    sim._choices[(first.strike, first.kind)] = not first.result
    sim.rerun()
    yield 1500
    ctx.grab("56-c-fixed.png", lesson=56,
             caption="**Fix this fight** copies every roll of the random fight into **Fixed** mode; double-clicking "
                     "Ike's first hit roll flipped it (marked `*`). The fight is re-run with only that change.",
             alt="Battle Simulator in Fixed mode with the first roll flipped and the fight log showing the changed "
                 "result.")
    sim.distance.set(2)
    sim.rerun()
    yield 1500
    ctx.grab("56-d-distance.png", lesson=56,
             caption="The boundary case: at **Distance** 2 neither iron weapon reaches, so the forecast reads "
                     "*cannot attack* for both sides and no roll is asked for.",
             alt="Battle Simulator at distance 2 with both sides unable to attack and an empty rolls table.")
    sim.distance.set(1)
    sim.mode.set("random")
    sim._clear_choices()
    yield 1000
    sim._render()
    yield Wait(until=lambda: ctx.toplevel("Battle Simulator - fight") is not None, timeout=60_000)
    yield 9000
    ctx.grab("56-b-result.png", widget=ctx.toplevel("Battle Simulator - fight"), lesson=56,
             caption="**Render fight** stages the baseline fight with the battle models (`zu/reng` against `zu/fig1`), "
                     "the weapons, camera and the **Scenery** `map03_ground01`; **Pause**, **Replay** and the time "
                     "slider scrub it. It checks presentation; the forecast and log check the numbers.",
             alt="Battle render window with Ike and Boyd facing each other on a grass plain, HP bars at the top and "
                 "Pause, Replay and a time slider at the bottom.")
    ctx.close("Battle Simulator - fight")


def scroll_to(scroll, widget, offset: int = 10) -> None:
    """Scroll a ScrollFrame so ``widget`` (inside its body) is near the top."""
    scroll.update_idletasks()
    body = scroll.body
    y = widget.winfo_rooty() - body.winfo_rooty() - offset
    scroll._canvas.yview_moveto(max(0.0, y / max(1, body.winfo_height())))
    scroll.update_idletasks()


def section_label(root, text: str):
    return next(w for w in ctx_find_all(root) if isinstance(w, ttk.Label) and str(w.cget("text")) == text)


def ctx_find_all(root):
    out = []

    def walk(w):
        for c in list(w.children.values()):
            out.append(c)
            walk(c)
    walk(root)
    return out


@step("57")
def lesson_57(ctx: Ctx):
    ctx.go("code")
    yield 2500
    page = ctx.page("code")
    ctx.grab("57-a-setup.png", lesson=57,
             caption="**Tools › Game Code** on the unmodified project: the recognised build (*Path of Radiance "
                     "(USA) · sys/main.dol*), *Identical to the retail executable*, *Vanilla: nothing changed*, "
                     "then the groups of patches (checkboxes) and values (each with its vanilla value and **Reset**).",
             alt="Game Code page with the build summary card and the Chapters and Combat rules groups.")
    row = next(r for r in page._rows if r.tunable.id == "combat.double_attack_threshold")
    row.var.set("5")
    row.apply()
    yield 1500
    page._scroll.scroll_top()
    yield 800
    ctx.grab("57-b-result.png", lesson=57,
             caption="**Double-attack speed gap** set to 5: the value is written to `main.dol` at once, the summary "
                     "reads *1 setting changed from vanilla* and *Differs from the retail executable*, and the "
                     "change is listed under **Changes this session**.",
             alt="Game Code page with the Double-attack speed gap field at 5 next to vanilla 4 and its Reset button.")
    page.run(lambda: page.editor.reset(row.tunable))
    yield 1000
    label = section_label(page._scroll.body, "Developer tools")
    scroll_to(page._scroll, label)
    yield 800
    ctx.grab("60-a-setup.png", lesson=60,
             caption="The **Developer tools** group of Game Code: **Debug menus in the map pause menu**, "
                     "**Development menu at startup** and the overlays that stay on (performance meters, safe "
                     "frame, process tree). Each is a patch: tick to write it, untick to restore the retail bytes.",
             alt="Game Code page scrolled to the Developer tools group with its six checkboxes.")


def _tab_named(notebook: ttk.Notebook, label: str) -> None:
    for tab_id in notebook.tabs():
        if notebook.tab(tab_id, "text") == label:
            notebook.select(tab_id)
            return


def _unit_tile(window, pid: str):
    unit = next(u for u in window.sim.state.living() if u.pid == pid)
    return unit.tile


@step("60")
def lesson_60(ctx: Ctx):
    snapshot = Snapshot(ctx, ["extracted/sys/main.dol"], ["originals"])
    try:
        ctx.go("code")
        yield 3000
        page = ctx.page("code")
        patch, var, box = next(c for c in page._checks if c[0].id == "dev.pause_menus")
        from fe_modding.gui.widgets import ScrollFrame
        for frame in ctx.find(page, ScrollFrame):
            frame.update_idletasks()
            frame._canvas.yview_moveto(max(0.0, box.winfo_rooty() - frame.body.winfo_rooty() - 60)
                                       / max(1, frame.body.winfo_height()))
        var.set(True)
        page._toggle(patch, var)
        yield 2500
        if not ctx.shell._drawer_open:
            ctx.shell.toggle_activity()
        yield 1000
        ctx.grab("60-b-result.png", lesson=60,
                 caption="**Debug menus in the map pause menu** ticked: the change is written to `sys/main.dol` at once and logged in **Changes this session** (*main.dol: Debug menus in the map pause menu: on*). The next build or chapter jump has the developer rows in the map's pause menu.",
                 alt="Game Code page with the debug menus entry ticked and the Changes this session drawer open.")
        ctx.shell.toggle_activity()
        var.set(False)
        page._toggle(patch, var)
        yield 1500
    finally:
        ctx.go("home")
        yield 500
        snapshot.restore()


@step("58")
def lesson_58(ctx: Ctx):
    from fe_modding.playthrough.state import AiTurn
    from fe_modding.gui.playthrough_window import _ForceDialog
    builder = build_tab(ctx, "02")
    yield 4000
    set_variant(builder, "Normal")
    yield 1500
    builder.open_play()
    yield Wait(until=lambda: builder._windows.get("play") is not None
               and builder._windows["play"].sim is not None and builder._windows["play"].sim.needs_input,
               timeout=180_000)
    window = builder._windows["play"]
    window.geometry("1500x920+20+20")
    yield 2500
    ctx.grab("58-a-setup.png", widget=window, lesson=58,
             caption="**Play…** on Ch.1, Normal, with **Skip the opening** ticked: the opening ran without "
                     "stopping and the window waits at turn 1, player phase. Top rows: **Restart**, **Difficulty**, "
                     "**Seed**, the options; then **Step by**, the transport buttons, **End phase**, **Force next "
                     "battle…** and the history slider.",
             alt="Play chapter window on the Ch.1 map at turn 1 with the option rows, transport bar, turn line, "
                 "map and the inspection tabs.")
    window.on_press(_unit_tile(window, "PID_IKE"), None)
    yield 1500
    ctx.grab("58-c-select.png", widget=window, lesson=58,
             caption="Clicking Ike selects him: blue tiles are where he can move, red the tiles he can strike from "
                     "there, and the **Unit** pane lists his stats, items and skills. Click a blue tile to get the "
                     "action menu, with the forecast on each attack entry.",
             alt="Play window with Ike selected, his movement and attack ranges drawn on the map and his Unit pane.")
    window._deselect()
    enemy = next(u for u in window.sim.state.living() if u.faction != 0)
    window.on_press(enemy.tile, None)
    yield 1500
    ctx.grab("58-d-threat.png", widget=window, lesson=58,
             caption="Clicking an enemy shows its reach: orange is every tile it can attack this turn. The **Unit** "
                     "pane adds its AI: attack and move scripts, heal script, MTYPE and order.",
             alt="Play window with an enemy bandit selected, its threat range in orange and its AI lines in the "
                 "Unit pane.")
    window._watch = None
    window._deselect()
    window._auto_messages.set(True)
    window.end_phase()
    yield 3000
    yield Wait(until=lambda: window.sim.needs_input and window._running is None, timeout=300_000)
    yield 2500
    _tab_named(window._tabs, "Log")
    yield 1200
    ctx.grab("58-b-result.png", widget=window, lesson=58,
             caption="After **End phase** the enemy phase ran to turn 2. The **Log** lists it in order: each AI "
                     "unit's scripts and action, every fight with its strikes, and the event checks that ran "
                     "after each action.",
             alt="Play window at turn 2 with the Log pane listing the enemy phase.")
    for _ in range(4000):
        state = window.sim.state
        if any(isinstance(t, AiTurn) and t.candidate and t.candidate.get("ranking") for t in state.pending):
            break
        if window.sim.cursor == 0:
            break
        window.back()
    yield 2000
    _tab_named(window._tabs, "AI")
    yield 1200
    ctx.grab("58-e-rewind.png", widget=window, lesson=58,
             caption="**◀** stepped back through the history into the enemy phase (entry 206 of 225): the status "
                     "bar says a command from here starts a new branch. The **AI** pane shows the Bandit about to "
                     "act on its chosen candidate, attacking Boyd from (11, 17).",
             alt="Play window rewound to an enemy unit's turn with the AI pane showing its script and the "
                 "history slider moved back.")
    ctx.grab("45-b-result.png", widget=window, lesson=45,
             caption="The **AI** pane during an enemy's attack: its registers, the candidate it holds, and **How "
                     "the target was chosen**, every possible attack best first with the points each term adds and "
                     "the unit's MTYPE weights.",
             alt="Play window AI pane with the attack candidate and the ranking table of possible attacks.")
    window.to_end()
    yield 1000
    dialog = _ForceDialog(window, window.sim.state.forced)
    yield 800
    ctx.grab("58-f-force.png", widget=dialog, lesson=58,
             caption="**Force next battle…**: tick **hits** / **crits** per strike in fight order (counters and "
                     "follow-ups included); unlisted strikes hit without crits or skills. **Use random rolls** "
                     "goes back to the seed.",
             alt="Force the next battle dialog with eight strike rows of hits and crits checkboxes and the Use "
                 "random rolls, Force and Cancel buttons.")
    dialog.destroy()
    window.destroy()


SAMPLE_SAVE = Path(r"G:/ROM/SaveFile/chapter1.gci")  # a test save; the tool only reads it


@step("59")
def lesson_59(ctx: Ctx):
    import shutil
    from fe_modding.gui.pages.saves import PlaySaveDialog
    folder = ctx.project_dir / "capture_samples"
    folder.mkdir(exist_ok=True)
    copy = folder / "chapter1.gci"
    edited = folder / "chapter1_gold.gci"
    if not SAMPLE_SAVE.is_file():
        print("no sample save: 59 blocked")
        return
    shutil.copyfile(SAMPLE_SAVE, copy)
    ctx.go("saves", "overview")
    yield 800
    page = ctx.page("saves")
    def pick_file5():
        label = next(l for l in page._labels if "File 5 - bmap05" in l)
        page._block_var.set(label)
        page._select_block()
    page.open_path(copy)
    pick_file5()
    yield 1500
    ctx.grab("59-a-setup.png", lesson=59,
             caption="**Open save file…** on a copy of a test save: **Block** lists the eight blocks of the file "
                     "(five file saves and two suspend checkpoints; *loaded* marks the ones the game loads). The "
                     "*File 5 · bmap05 · base* block is chosen: **Overview** shows its header, the party (gold, bonus "
                     "EXP, map, turn), the options, the map state and the cleared maps.",
             alt="Saves page with the opened file, the block list and the Overview tab fields.")
    ctx.go("saves", "units")
    yield 800
    ctx.select_row(page._tabs["units"], "Ike")
    yield 1200
    ctx.grab("59-c-units.png", lesson=59,
             caption="**Units**: every unit slot of the block. Ike's slot shows his character, class, army, level, "
                     "EXP and HP, his stats gained on top of the class, fixed-growth points, weapon EXP, items, "
                     "supports and skills.",
             alt="Saves Units tab with the unit list and Ike's identity, stats and items fields.")
    ctx.go("saves", "flags")
    yield 1200
    ctx.grab("59-d-flags.png", lesson=59,
             caption="**Flags**: the campaign flags and the chapter flags of the block's map, named from the "
                     "project's scripts. Double-click (or Space) switches one; **Clear chapter flags** resets the "
                     "chapter's.",
             alt="Saves Flags tab with the flag table and the Clear chapter flags button.")
    page.block.party.gold = 12345
    page.mark_dirty()
    for fields in page._fields:
        fields.load()
    with mock.patch("tkinter.filedialog.asksaveasfilename", return_value=str(edited)):
        page._save_as()
    yield 1000
    page.open_path(edited)
    pick_file5()
    ctx.go("saves", "overview")
    yield 1500
    ctx.grab("59-b-result.png", lesson=59,
             caption="**Gold** set to 12345 and written with **Save as…** to `chapter1_gold.gci`: reopening that "
                     "file and the same block shows the new value, and the first copy is untouched. Loading it in "
                     "the game is the next check.",
             alt="Saves Overview of the edited file showing the raised gold value.")
    index = ctx.shell.index
    dialog = PlaySaveDialog(page, page.block, {int(cid): c.title for cid, c in index.by_chapter.items()})
    yield 800
    ctx.grab("59-e-play.png", widget=dialog, lesson=59,
             caption="**Play in Dolphin…**: load the block as saved, or **Start a chapter with this army:** any "
                     "chapter, as after clearing the previous one. Dolphin runs the extracted files with a copy of "
                     "the save alone on memory card A.",
             alt="Play in Dolphin dialog with the two start choices, the chapter list, Play and Cancel.")
    dialog.destroy()


@step("61")
def lesson_61(ctx: Ctx):
    from fe_modding.gui.mod_details_dialog import ModDetailsDialog
    from fe_modding.gui.patch_dialog import ApplyPatchDialog
    project = ctx.project
    build = project.build_dir
    build.mkdir(parents=True, exist_ok=True)
    patch_file = build / "Tutorial Practice.tpatch"
    patched = build / "Tutorial Practice (patched).ciso"
    ctx.go("disc")
    yield 800
    page = ctx.page("disc")
    dialog = ModDetailsDialog(page, project, on_saved=page._render)
    dialog._author.set("Tutorial author")
    dialog._version.set("0.1")
    dialog._description.insert("1.0", "Practice mod from the Tellius Modding tutorials: a new guard, Boyd's copy.")
    dialog._credits.insert("1.0", "Placeholder guard portrait: drawn for the tutorial.")
    yield 600
    ctx.grab("61-a-setup.png", widget=dialog, lesson=61,
             caption="**Disc & Patch › Mod details…**: **Name**, **Author**, **Version**, **Description** and "
                     "**Credits (who made or allowed what)** are saved in the project and shown to whoever "
                     "applies the patch.",
             alt="Mod details dialog filled with the project name, author, version 0.1, a description and a "
                 "credit line.")
    dialog._save()
    yield 800
    with mock.patch("tkinter.filedialog.asksaveasfilename", return_value=str(patch_file)):
        ctx.shell.create_patch()
    yield Wait(until=lambda: not ctx.shell._task_running, timeout=1_200_000)
    yield 1000
    ctx.go("home")
    yield 300
    ctx.go("disc")
    yield 1200
    ctx.grab("61-c-created.png", lesson=61,
             caption="After **Create patch…**: the **Create a patch** card shows the version and author, and "
                     "*Last patch:* with the counts of replaced, added and removed files and the patch size.",
             alt="Disc and Patch page with the Create a patch card showing the last patch line.")
    patcher = ApplyPatchDialog(ctx.app)
    patcher._set_patch(str(patch_file))
    patcher._disc.set(str(project.source_path))
    patcher._output.set(str(patched))
    patcher._update_state()
    yield 800
    ctx.grab("61-apply.png", widget=patcher, lesson=61,
             caption="**Apply patch…** (or **File › Apply patch to a disc…**, or the standalone Tellius Patcher): "
                     "the patch shows its name, game and credits; **Game disc image** must be the clean disc it was "
                     "made from; **Output** is the new image.",
             alt="Apply a patch dialog with the patch, game disc image and output fields filled and the patch "
                 "details shown.")
    patcher._run()
    yield 3000
    yield Wait(until=lambda: "Built" in str(patcher._status.cget("text")) or not str(patcher._status.cget("text")),
               timeout=1_800_000)
    yield 1000
    ctx.grab("61-b-result.png", widget=patcher, lesson=61,
             caption="**Build patched disc** extracted the clean disc, checked every file the patch replaces "
                     "against the retail hash, wrote the patch's files and packed a new image: the status reads "
                     "*Built …*.",
             alt="Apply a patch dialog after the build with the Built status line.")
    patcher.destroy()
    if patched.exists():
        patched.unlink()  # 1.4 GB: the frame is the evidence, the image is not kept


@step("64")
def lesson_64(ctx: Ctx):
    yield from view(ctx, "67-a-setup.png", 67, ("characters",),
                    "**Characters**: search by name or PID, **New character…**, and **Export Excel… / Import Excel…** "
                    "for editing every character in a spreadsheet.",
                    "Characters page with the search box, buttons and the character cards.")


# -- 65 Chapter parts and phases: a map phase added and removed, then a playable part --
@step("65")
def lesson_65(ctx: Ctx):
    snapshot = Snapshot(ctx, CHAPTER_FILES + ["extracted/files/Scripts/C02.cmb"], CHAPTER_FOLDERS)
    try:
        yield Wait(until=lambda: ctx.shell.index is not None, timeout=180_000)
        ctx.go("chapter", "09", "overview")
        yield 3500
        ctx.grab("65-c-phases.png", lesson=65,
                 caption="Ch.8: Despair and Hope (slot 09) has five map phases, `bmap09` to `bmap09_5`: **Map phase** "
                         "lists them in play order and **‹ Phase** / **Phase ›** step through them. Only the script's "
                         "`MapLoad` calls decide when the game loads each one.",
                 alt="Overview of Ch.8 with the map phase list and its phase buttons under the title.")
        ctx.go("chapter", "02", "overview")
        yield 2500
        page = ctx.page("chapter")
        ctx.later(page._add_phase)
        yield Wait(until=lambda: ctx.toplevel("Add phase") is not None, timeout=10_000)
        dialog = ctx.toplevel("Add phase")
        ctx.grab("65-a-setup.png", widget=dialog, lesson=65,
                 caption="**+ Phase…** on Ch.1: *Clone bmap02 into a new map phase.* **Map phase only** copies the "
                         "folder; **Next playable chapter part** also adds an opening for it to the chapter script.",
                 alt="Add phase dialog with the Map phase only and Next playable chapter part choices, Create and "
                     "Cancel.")
        ctx.button(dialog, "Create").invoke()
        yield Wait(until=lambda: "bmap02_2" in page._phase_folders, timeout=30_000)
        yield 2500
        ctx.grab("65-d-map.png", lesson=65,
                 caption="After **Create** with **Map phase only**: *Map phase 2 · bmap02_2*, a copy of `bmap02` whose "
                         "sections are renamed (`bmap02_2_first_n`…). No script loads it yet, so the game never "
                         "shows it; **Remove phase…** deletes it again.",
                 alt="Overview of Ch.1 on its new second map phase with the copied cast.")
        ctx.later(page._remove_phase)
        yield Wait(until=lambda: "bmap02_2" not in page._phase_folders, timeout=30_000)
        yield 1500
        ctx.later(page._add_phase)
        yield Wait(until=lambda: ctx.toplevel("Add phase") is not None, timeout=10_000)
        dialog = ctx.toplevel("Add phase")
        ctx.find(dialog, ttk.Radiobutton, "Next playable chapter part")[0].invoke()
        ctx.button(dialog, "Create").invoke()
        yield Wait(until=lambda: "bmap02_2" in page._phase_folders and page._tab == "script", timeout=30_000)
        yield 3000
        ctx.grab("65-b-result.png", lesson=65,
                 caption="With **Next playable chapter part**: the header now says **Parts** (*Part 2 · bmap02_2*) and "
                         "*Part 2: needs deployment and previous victory*; the Script tab shows the new, unsaved "
                         "`Opening18_2` with its `MapLoad(\"bmap02_2\")`.",
                 alt="Script tab of Ch.1 with the new Opening18_2 function, the Parts list and the part status under "
                     "the title.")
        source = page._script.chapter_source()
        source = source.replace("    WaitM(160)\n    func_7()\n", "    WaitM(160)\n    func_7()\n    Complete18(1)\n", 1)
        source = source.replace('def Opening18_2():\n    MapLoad("bmap02_2")\n',
                                'def Opening18_2():\n    BMSetTurn(1)\n    MapLoad("bmap02_2")\n'
                                '    InstantDisposSetMode("bmap02_2_mikata_n", "bmap02_2_mikata_h", '
                                '"bmap02_2_mikata_m")\n    InstantDisposRank("bmap02_2_first")\n')
        page._script.edit_chapter_source(source, select="Opening18_2")
        yield 2500
        ctx.grab("65-e-linked.png", lesson=65,
                 caption="The part linked: `Complete18(1)` ends part 1's victory function `func_20`, and "
                         "`Opening18_2` sets turn 1, loads `bmap02_2` and deploys its player and enemy sections. The "
                         "status reads *Part 2: script links found*; **Save** writes `C02.cmb` once it compiles.",
                 alt="Script tab of Ch.1 with the completed Opening18_2 and the part status saying script links "
                     "found.")
    finally:
        yield from restore_chapters(ctx, snapshot)


# -- 67 Bulk editing: an Excel round trip on the characters, then Export as text --
@step("67")
def lesson_67(ctx: Ctx):
    from fe_modding import excel_io
    session = ctx.shell.session
    samples = ctx.project_dir / "capture_samples"
    samples.mkdir(parents=True, exist_ok=True)
    book_path = samples / "characters.xlsx"
    excel_io.export_fe8(str(book_path), session.data, only="Characters")
    book = excel_io.read_workbook(str(book_path))
    head = book["Characters"][0]
    row = next(r for r in book["Characters"] if len(r) > 1 and r[1] == GUARD)
    row[head.index("growth_hp")] = "90"
    excel_io.write_workbook(str(book_path), book)
    ctx.go("characters")
    yield 1500
    page = ctx.page("characters")
    with mock.patch("tkinter.filedialog.askopenfilename", return_value=str(book_path)):
        page._import_excel()
    yield 1000
    ctx.go("character", GUARD, "stats")
    yield 2000
    ctx.grab("67-b-result.png", lesson=67,
             caption="After **Import Excel…** of a workbook whose `PID_TUTORIAL_GUARD` row has `growth_hp` 90: the "
                     "Guard's **Personal growth %** HP reads 90 and the status bar names FE8Data.bin as unsaved. "
                     "Nothing is written until **Save FE8Data.bin**.",
             alt="Stats tab of the Guard after the Excel import, with HP personal growth 90 and FE8Data.bin unsaved.")
    session.revert()
    yield 800
    out = samples / "text_export"
    ctx.go("disc")
    yield 1500
    disc = ctx.page("disc")
    with mock.patch("tkinter.filedialog.askdirectory", return_value=str(out)):
        disc._export_text()
    yield Wait(until=lambda: disc._export_status.get().startswith(("Wrote", "Export failed")),
               timeout=300_000)
    yield 1000
    print("text export:", disc._export_status.get(), flush=True)
    from fe_modding.gui.widgets import ScrollFrame
    for frame in ctx.find(disc, ScrollFrame):
        frame._canvas.yview_moveto(1.0)
    yield 600
    ctx.grab("67-c-text.png", lesson=67,
             caption="**Disc & Patch › Export as text…** into a chosen folder: *Wrote 686 files to …\text_export.* "
                     "FE8Data tables, deployments, shops, messages, decompiled scripts, sound cues, the face table "
                     "and the DBX tables, as text for git and diffs.",
             alt="Disc and Patch page with the Export as text card and its result line.")


# -- 68 Find where a record is used --
@step("68")
def lesson_68(ctx: Ctx):
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=180_000)
    ctx.go("home")
    yield 800
    ctx.shell.open_search()
    yield 400
    palette = ctx.shell._palette
    palette._query.set("Zawana")
    yield 900
    ctx.grab("68-a-setup.png", lesson=68, over=(palette,),
             caption="**Ctrl+K** *Zawana*: one row, *Character Zawana — PID_ZAWANAR · Bandit*. The search matches record names and IDs, and the words of every chapter message; his name is in no message text, so no *Message* row appears.",
             alt="Search palette with the query Zawana listing the character and his messages.")
    palette.destroy()
    yield 300
    ctx.go("data", "ai")
    yield 3000
    from fe_modding.gui.cp_data_editor import CpDataPanel
    cp = next(w for w in ctx.find(ctx.page("data"), CpDataPanel))
    ctx.select_row(cp, "SEQ_ALLATK100_NOGREIL")
    yield 1500
    cp._find_uses()
    yield Wait(until=lambda: "Searching" not in str(cp._uses.get(0)), timeout=120_000)
    yield 800
    ctx.grab("68-b-result.png", lesson=68,
             caption="**Game Data › AI (CP)**, `SEQ_ALLATK100_NOGREIL` selected, **Used by** › **Find**: *Scripts/C06.cmb: named 1 time* (Ch.5's script switches Dakova to it) and *zmap/bmap06/dispos.cmp: named 3 times* (units that start with it). The same file search runs before every **Remove**.",
             alt="AI page with an attack script selected and its Used by list after Find.")


# -- 76 Doors, chests and keys: Ch.10 (slot 11) --
@step("76")
def lesson_76(ctx: Ctx):
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=180_000)
    builder = build_tab(ctx, "11")
    yield 5000
    set_layers(builder, zones=True, terrain=True)
    yield 2500
    builder._select(("zone", "func_6"))
    builder._refresh_inspector()
    yield 1500
    ctx.grab("76-a-setup.png", lesson=76,
             caption="Ch.10 (slot 11), **Build** with **Terrain** and **Script zones**: the chest at (2, 5) selected, "
                     "`func_6`, *Location - a unit acts on a tile*, **Action** *chest*. Its function opens the chest "
                     "(`TBoxOpen`), gives the item (`MindGetItem(\"IID_COUNTER\")`) and sets its flag.",
             alt="Build tab of Ch.10 with terrain colours, script zones and a chest zone selected.")
    builder._select(("zone", "func_13"))
    builder._refresh_inspector()
    yield 1500
    ctx.grab("76-c-door.png", lesson=76,
             caption="A door of Ch.10 selected: `func_13`, **Action** *door* at (8, 14). Its function opens it "
                     "(`DoorOpen`) and sets `F0814`, then a story flag for the cell behind it.",
             alt="Build tab of Ch.10 with a door zone selected and its fields.")
    builder._select(("tile", 2, 5))
    builder._refresh_inspector()
    yield 1500
    ctx.grab("76-d-tile.png", lesson=76,
             caption="The chest's tile (2, 5) selected: under **Tile (2, 5)** its terrain type, *Chest (宝箱)*, which makes the *Chest* command appear; the zone only says what opening it does.",
             alt="Build tab with the chest tile selected and its terrain type in the panel.")
    builder._select(None)
    ctx.go("data", "ai")
    yield 3000
    from fe_modding.gui.cp_data_editor import CpDataPanel
    cp = next(w for w in ctx.find(ctx.page("data"), CpDataPanel))
    ctx.tab(cp._notebook, "Steal items")
    yield 1500
    ctx.grab("76-b-result.png", lesson=76,
             caption="**Game Data › AI (CP)**, **Steal items**: *Items an AI thief may steal*, in order, with **Add**, **Remove selected**, **▲ Up**, **▼ Down**. Keys are set per unit: the deployment flags **AI uses Door Key** and **AI uses Chest Key**; thieves with Lockpick (`SID_KEY0`) open both without them.",
             alt="AI page on the Steal items tab with the thief item list.")


# -- 77 Preparations, forced units and bonus EXP --
@step("77")
def lesson_77(ctx: Ctx):
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=180_000)
    ctx.go("chapter", "06", "script", "Opening0")
    yield 3500
    ctx.grab("77-a-setup.png", lesson=77,
             caption="Ch.5's `Opening0` on the **Script** tab: `UnitForcedSallyByPID(\"PID_IKE\")` and the other "
                     "`UnitForcedSallyByPID` lines make units mandatory in the preparations; "
                     "`UnitDontMoveSallyByPID(\"PID_IKE\")` also locks Ike's starting tile.",
             alt="Script tab of Ch.5 on Opening0 with the forced deployment calls.")
    builder = build_tab(ctx, "06")
    yield 4000
    set_variant(builder, "Common")
    yield 2000
    builder._filter_var.set("bmap06_mikata_c")
    builder._refresh_canvas()
    yield 2000
    ctx.grab("77-c-slots.png", lesson=77,
             caption="**Build**, *Common* file, section `bmap06_mikata_c` only: 8 records, Ike, Gatrie, Soren, Boyd, Rhys, Titania, Oscar and Shinon, each appearing at (16, 9) and walking to its own tile (arrows). `RestoreSallyDisposition` calls `SallySetByGroup(\"bmap06_mikata_c\")`: the preparation screen takes its deployment tiles from this group.",
             alt="Build tab of Ch.5 filtered to the player section with its eight slots on the map.")
    builder._filter_var.set("All sections")
    builder._refresh_canvas()
    ctx.go("chapter", "02", "script", "func_21")
    yield 3000
    ctx.grab("77-b-result.png", lesson=77,
             caption="Ch.1's `func_21`, `@on_scenario_end`: the turn bonus. 200 bonus EXP, minus 10 per turn after "
                     "turn 4, recorded with `AchieveSet(\"Ms_ach_02_turn\", v1)` as one line of the chapter's bonus "
                     "results.",
             alt="Script tab of Ch.1 on the scenario-end function that awards bonus experience.")


# -- 78 Script a map cutscene: Ch.2's turn-3 arrival --
@step("78")
def lesson_78(ctx: Ctx):
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=180_000)
    ctx.go("chapter", "03", "script", "func_11")
    yield 3500
    ctx.grab("78-a-setup.png", lesson=78,
             caption="Ch.2's `func_11` (*Before a phase starts*, turn 3, player): Titania's arrival. `CopyMapCamera` "
                     "keeps the view, `Fade` and `InstantFocus` / `InstantSetMapCamera` frame the edge of the map, "
                     "`InstantDispos` places her section, `UnitMoveDirByPID(\"PID_TIAMAT\", \"888888\")` walks her "
                     "six tiles up, then a message and `PastMapCamera` give the view back.",
             alt="Script tab of Ch.2 on the turn-3 function with camera, fade and unit movement calls.")
    script = ctx.page("chapter")._script
    from fe_modding.gui.script_editor import InsertCallDialog
    ctx.later(script._insert_call)
    yield Wait(until=lambda: ctx.toplevel("Insert call") is not None, timeout=10_000)
    dialog = ctx.toplevel("Insert call")
    dialog._query.set("Camera")
    yield 1200
    ctx.grab("78-c-calls.png", widget=dialog, lesson=78,
             caption="**Insert call…** with *Camera* in **Search**: every camera function with **What it does**; "
                     "**Insert** writes the selected call at the cursor.",
             alt="Insert call dialog filtered on Camera with the function list and descriptions.")
    dialog.destroy()
    yield 300


# -- 79 The ending and the war record --
@step("79")
def lesson_79(ctx: Ctx):
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=180_000)
    ctx.go("asset", "conversations", "ending.m")
    yield 3000
    ctx.grab("79-a-setup.png", lesson=79,
             caption="**Assets › Conversations**, `ending.m`: the war record's labels. `MED_CHAPnn_TAG` and "
                     "`MED_CHAPnn_TITLE` name each chapter slot (`MED_CHAP01_TAG` *Prologue*, `MED_CHAP02_TAG` *Chapter 1*), "
                     "`MED_DIED_CHAPnn` the chapter a unit fell in, `MED_REC_LV`, `_WIN` and `_TURN` the column headers.",
             alt="Dialogue editor on ending.m with the war-record label messages.")
    from fe_modding.gui.pages.chapters import open_script
    open_script(ctx.shell, files_root_of(ctx.project) / "Scripts" / "ending.cmb", "Ending", chapter_id="01")
    yield 5000
    ctx.grab("79-c-script.png", lesson=79,
             caption="`ending.cmb`, function `Ending`, in a chapter's **Script** tab (**File** *ending.cmb - shared "
                     "script*): the finale. `BGMPlay(1, \"BGM_ED_STAFF1\")`, the credit names with `func_1(\"RID_END_…\", "
                     "x, y, …)`, then one `func_2(\"RID_END_GRnn\", \"RID_END_LBLnn\", …)` per artwork with its label, "
                     "positions and timings in milliseconds.",
             alt="Script tab on ending.cmb with the Ending function and its slideshow calls.")
    ctx.go("asset", "ending")
    yield 2500
    ctx.select_row(ctx.page("asset")._panels["ending"], "bole_en")
    yield 2500
    ctx.grab("79-b-result.png", lesson=79,
             caption="**Assets › Ending Art**, `bole_en.tpl`: Boyd's war-record card for the English game, his name "
                     "drawn into the picture. The game shows it as `RID_END_BOLE` and writes his level, wins and the "
                     "chapter he fell in over it.",
             alt="Ending Art page with Boyd's English war-record card selected.")


# -- 80 Menus, shortcuts and preferences --
@step("80")
def lesson_80(ctx: Ctx):
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=180_000)
    ctx.go("home")
    yield 1000
    ctx.shell.open_search()
    yield 400
    palette = ctx.shell._palette
    palette._query.set("rect")
    yield 700
    ctx.grab("80-a-setup.png", lesson=80, over=(palette,),
             caption="**Ctrl+K** with *rect*: the **Rect RIDs** tab of Game Data first, then every message whose ID or "
                     "text holds the word. **↑**/**↓** pick, **Enter** opens, **Esc** closes.",
             alt="Search palette over the Home page with the query rect and matching tools and records.")
    palette.destroy()
    yield 200
    ctx.go("chapter", "01", "script")
    yield 3000
    code = ctx.page("chapter")._script._editor
    start = code.text.search(r"\mUnit", "1.0", regexp=True)
    if start:
        code.text.mark_set("insert", f"{start}+4c")
        code.text.see("insert")
        code.text.focus_force()
        yield 300
        code._show_completions(force=True)
    yield 700
    ctx.grab("80-c-complete.png", lesson=80, over=tuple(w for w in (code._popup,) if w is not None),
             caption="Script tab, **Ctrl+Space** with the cursor after `Unit`: the script functions whose names start "
                     "with it; **Enter** or a double-click puts the selected one in place.",
             alt="Script tab with the completion list open under the cursor, listing Unit functions.")
    code._close_popup()
    from fe_modding.gui.tool_setup import ToolSetupDialog
    ctx.later(lambda: ToolSetupDialog(ctx.app))
    yield Wait(until=lambda: ctx.toplevel("disc and media tools") is not None, timeout=10_000)
    yield 500
    dialog = ctx.toplevel("disc and media tools")
    ctx.grab("80-b-result.png", widget=dialog, lesson=80,
             caption="**Settings › Disc and media tools…**: downloads WIT (extract and build discs) and, with "
                     "**Include FFmpeg for audio/video imports**, FFmpeg. **Later** closes without downloading.",
             alt="Set up disc and media tools dialog with the FFmpeg option and Download missing tools button.")
    dialog.destroy()


@step("66")
def lesson_66(ctx: Ctx):
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=180_000)
    builder = build_tab(ctx, "02")
    yield 4000
    set_layers(builder, zones=True)
    builder._choose_tool("zone")
    yield 1500
    ctx.grab("66-a-setup.png", lesson=66,
             caption="The **Script function / zone** tool on Ch.1: the pink rectangles are the script's zones (the "
                     "seize tile, the village visits). The panel makes a **New zone**: its kind, what it is "
                     "**Triggered by** and the function it **Runs**.",
             alt="Build tab of Ch.1 with the zone tool, script zones drawn on the map and the New zone panel.")
    builder._choose_tool("select")
    builder._select(("zone", "func_0"))
    builder._refresh_inspector()
    yield 1500
    ctx.grab("66-c-zone.png", lesson=66,
             caption="Ch.1's seize zone selected: `func_0`, *Location - a unit acts on a tile*, **Action** *seize* at "
                     "(8, 5). **Apply** writes a change into the script, **Delete zone** removes the trigger, **Open in "
                     "Script tab** shows the function (`set(\"gf_complete\")`).",
             alt="Build tab with the seize zone selected and its kind, action, tiles and buttons in the panel.")
    builder._choose_tool("zone")
    builder._zone_kind.set("Area - a unit enters")
    builder._zone_kind_changed()
    builder._zone_mode.set("player")
    builder._zone_function.set("New function")
    builder._add_zone((1, 1, 3, 3))
    yield 2000
    ctx.grab("66-b-result.png", lesson=66,
             caption="A new **Area** zone drawn on tiles (1, 1)–(3, 3), **Triggered by** the player's units: the "
                     "chapter script gets a new, empty function with an `@on_area` trigger (unsaved until **Save** on "
                     "the Script tab). Write what it does there.",
             alt="Build tab of Ch.1 with the new area zone selected in the corner of the map and its fields.")
    script = ctx.page("chapter")._script
    script._revert()
    yield 1500
    builder._choose_tool("select")
    builder = build_tab(ctx, "26")
    yield 5000
    data = builder._map.map_data
    from fe_modding.formats.cmb import script_rocks
    routed = {r.prop_tile for r in script_rocks.routes(ctx.page("chapter")._script.chapter_source()) if r.path}
    rock = next(i for i, inst in enumerate(data.build_inst)
                if "rock" in data.build_desc[inst.desc_index].filename.lower() and (inst.x, inst.y) in routed)
    builder._select(("prop", rock))
    builder._refresh_inspector()
    yield 2000
    ctx.grab("66-d-rock.png", lesson=66,
             caption="Ch.25 (slot 26): a rolling-rock prop selected. Under **Rolling rock**: the **Initial direction** "
                     "and the **Path** (one digit per step: 4 left, 6 right, 2 down, 8 up) of its `SetRock` call, "
                     "**Apply route** and **Remove route**, and the script line that holds it.",
             alt="Build tab of Ch.25 with a rock prop selected and its rolling-rock route fields.")
    builder._select(None)


# -- 04 Dolphin setup and build --
@step("04")
def lesson_04(ctx: Ctx):
    from fe_modding.gui.settings_dialog import SettingsDialog
    ctx.later(lambda: SettingsDialog(ctx.app))
    yield Wait(until=lambda: ctx.toplevel("Settings") is not None, timeout=10_000)
    yield 500
    dialog = ctx.toplevel("Settings")
    ctx.grab("04-a-setup.png", widget=dialog, lesson=4,
             caption="**Settings › Preferences…**: **Dolphin location (Dolphin.exe)** is the emulator the app "
                     "launches; Blender is optional and only used by the .blend model tools.",
             alt="Preferences dialog with theme choice, Dolphin location and Blender location fields with Browse "
                 "buttons.")
    dialog.destroy()
    ctx.go("disc")
    yield 800
    ctx.grab("04-c-build.png", lesson=4,
             caption="The **Build** card on Disc & Patch: **Build disc** packs the saved project files into a new "
                     "image; **Build and play in Dolphin** also starts it.",
             alt="Disc and Patch page with the Build card showing Build disc and Build and play in Dolphin.")
    ctx.shell.build()
    yield 2000
    yield Wait(until=lambda: not ctx.shell._task_running, timeout=1_200_000)
    yield 1000
    ctx.go("home")
    yield 300
    ctx.go("disc")
    yield 1200
    ctx.grab("04-b-result.png", lesson=4,
             caption="After **Build disc**: the status bar reads *Built* and the image path, the project's "
                     "`build/Tutorial Practice.ciso`. Every build overwrites that file; open it in Dolphin, or use "
                     "**Build and play in Dolphin**.",
             alt="Disc and Patch page after a build, with the built image path in the status bar.")
    from fe_modding.gui.pages.chapters import PlayChapterDialog
    index = ctx.shell.index
    dialog = PlayChapterDialog(ctx.shell, choices={c.id: c.title for c in index.chapters})
    yield 800
    ctx.grab("04-d-play-chapter.png", widget=dialog, lesson=4,
             caption="**Play › Play chapter in Dolphin…** (F5): pick a chapter and a **Difficulty**; Dolphin starts "
                     "on the extracted files, without a build, straight in that chapter.",
             alt="Play in Dolphin dialog with the chapter list, the difficulty choice, Play and Cancel.")
    dialog.destroy()


# -- survey (not a lesson): every route's default state, into --survey-dir, to plan steps --
SURVEY_ROUTES = [
    ("chapters",), ("chapter", "01"), ("chapter", "01", "build"), ("chapter", "01", "map_settings"),
    ("chapter", "01", "chapter_data"), ("chapter", "01", "dialogue"), ("chapter", "01", "script"),
    ("chapter", "01", "shops"), ("chapter", "01", "battle"), ("chapter", "02"), ("chapter", "02", "build"),
    ("characters",), ("character", "PID_IKE"), ("character", "PID_IKE", "supports"),
    ("character", "PID_IKE", "look"), ("character", "PID_IKE", "appearances"), ("character", "PID_IKE", "scripts"),
    ("data",), *[("data", k) for k in ("classes", "items", "skills", "terrain", "general", "supports", "flags", "ai",
                                       "rect_images")],
    ("assets",), *[("asset", k) for k in (
        "conversations", "scripts", "portraits", "models", "map_objects", "backgrounds", "illustrations", "ending",
        "world_map", "icons", "fonts", "ui_windows", "etc_graphics", "equipment", "music", "effects",
        "battle_weapons", "battle_sceneries", "battle_cameras", "battle_sim", "battle_params", "dbx_files", "sfx",
        "sound_room", "tutorials", "staff_credits", "sound_room_tracks", "videos")],
    ("tools",), ("check",), ("code",), ("saves",), ("disc",),
]
SURVEY_DIR: list[Path] = []


@step("survey")
def survey(ctx: Ctx):
    out = SURVEY_DIR[0]
    out.mkdir(parents=True, exist_ok=True)
    yield Wait(until=lambda: ctx.shell.index is not None, timeout=120_000)
    for route in SURVEY_ROUTES:
        try:
            ctx.go(*route)
        except Exception as exc:  # noqa: BLE001
            print("route failed", route, exc)
            continue
        yield 2500
        _grab_window(ctx.app).save(out / ("_".join(route) + ".png"))
        print("survey", route, flush=True)


# -- putting the frames in the lessons -------------------------------------------------------------
WIKI = ROOT / "wiki" / "modding"
MARK = "<!-- screenshot {} -->"


def _figure(name: str, entry: dict) -> str:
    src = f"../assets/images/tutorials/screenshots/{name}"
    return (f"{MARK.format(name)}\n<figure class=\"tutorial-figure\" markdown=\"1\">\n\n"
            f"[![{entry['alt']}]({src})]({src})\n\n"
            f"<figcaption markdown=\"span\">{entry['caption']}</figcaption>\n</figure>\n")


#: Concept diagrams (App/tools/build_tutorial_figures.py) and the lesson whose mechanism each explains:
#: (lesson, alt text). They go at the start of "How the editor fits together".
DIAGRAMS = {
    "project": (1, "Source disc, project files and build output: extract once, save edits in the project, build a "
                   "new image to test."),
    "workspace": (2, "Chapter-local resources, shared records, and assets and tools: find the owner before "
                     "changing a value."),
    "chapter": (6, "A chapter is a slot, part and difficulty, connected files, and a story boundary that must agree."),
    "campaign": (8, "A three-chapter campaign exercise with a checkpoint after each chapter and each transition."),
    "character": (10, "Creating a character record, placing the unit in a deployment, and checking it in Play."),
    "terrain": (22, "What you see (props), where you walk (terrain tiles) and where you stand (tile heights) are "
                    "separate layers."),
    "events": (33, "An event as trigger and guard, action, and completion flag."),
    "deployment": (32, "A reinforcement wave needs a deployment section, a script trigger and a once-only guard."),
    "dialogue": (37, "Scene setup, text and timing, then the script call that reaches the message."),
    "media": (47, "Media checks at the boundaries: start, loop or end, and the built game."),
    "assets": (50, "A replaced file must be connected through its identity or table to the screen that uses it."),
    "model": (51, "A small model round trip: export, edit, import review, then pose and attack checks."),
    "testing": (58, "Check, Play and Dolphin answer three different questions."),
    "release": (61, "A release is tested from the recipient's starting point: clean disc, patch, patched disc."),
    "terrain-footprint": (24, "A prop's visible footprint and the terrain tiles painted under it."),
}
DIAGRAM_MARK = "<!-- diagram {} -->"


def _diagram(name: str, alt: str) -> str:
    src = f"../assets/images/tutorials/{name}.svg"
    return (f"{DIAGRAM_MARK.format(name)}\n<figure class=\"tutorial-figure\" markdown=\"1\">\n\n"
            f"[![{alt}]({src})]({src})\n\n"
            f"<figcaption>Concept diagram, not an app screenshot. {alt} Select the image to open it at full "
            f"size.</figcaption>\n</figure>\n")


def insert_diagrams() -> list[str]:
    import re
    changed = []
    for name, (lesson, alt) in DIAGRAMS.items():
        page = sorted(WIKI.glob(f"{lesson:02d}-*.md"))[0]
        text = page.read_text(encoding="utf-8")
        if f"tutorials/{name}.svg" in text and DIAGRAM_MARK.format(name) not in text:
            continue  # placed by hand
        new = re.sub(re.escape(DIAGRAM_MARK.format(name)) + r"\n<figure.*?</figure>\n\n?", "", text, flags=re.S)
        heading = re.search(r"^## How (?:the editor|this surface) fits together\n\n?", new, re.M)
        if heading is None:
            print(f"{page.name}: no 'How the editor fits together' section")
            continue
        new = new[:heading.end()] + _diagram(name, alt) + "\n" + new[heading.end():]
        if new != text:
            page.write_text(new, encoding="utf-8", newline="\n")
            changed.append(page.name)
    return changed


def insert_figures() -> list[str]:
    """Put every logged frame of an existing lesson into its page. A frame already in the page (its
    ``<!-- screenshot … -->`` marker) is refreshed where it stands, so a figure moved beside its step
    stays there; a new one goes to the start of the Guided walkthrough (setup and extra frames) or
    its end (result frames, ``-b-``). Returns the pages changed."""
    import re
    log = json.loads(LOG.read_text(encoding="utf-8"))
    by_lesson: dict[int, list[str]] = {}
    for name, entry in log.items():
        if entry.get("status") in ("captured", "accepted"):
            by_lesson.setdefault(int(entry["lesson"]), []).append(name)
    changed = []
    for lesson, names in sorted(by_lesson.items()):
        pages = sorted(WIKI.glob(f"{lesson:02d}-*.md"))
        if not pages:
            continue  # a planned lesson: the frame waits in the log
        page = pages[0]
        text = original = page.read_text(encoding="utf-8")
        new = []
        for name in sorted(names):
            pattern = re.escape(MARK.format(name)) + r"\n<figure.*?</figure>\n"
            if re.search(pattern, text, flags=re.S):
                text = re.sub(pattern, lambda _m, n=name: _figure(n, log[n]), text, count=1, flags=re.S)
            else:
                new.append(name)
        if new:
            heading = re.search(r"^## Guided walkthrough\n\n?", text, re.M)
            if heading is None:
                print(f"{page.name}: no Guided walkthrough section")
                continue
            after = re.search(r"^## ", text[heading.end():], re.M)
            end = heading.end() + (after.start() if after else len(text) - heading.end())
            top = "".join(_figure(n, log[n]) + "\n" for n in new if "-b-" not in n)
            bottom = "".join(_figure(n, log[n]) + "\n" for n in new if "-b-" in n)
            text = text[:end] + bottom + text[end:]
            text = text[:heading.end()] + top + text[heading.end():]
        if text != original:
            page.write_text(text, encoding="utf-8", newline="\n")
            changed.append(page.name)
    return changed


#: The frames the capture plan (wiki/meta/tutorial-screenshot-plan.md) asks for besides NN-a and NN-b.
PLAN_EXTRAS = ["01-c-extract", "04-c-build", "10-c-stats", "10-d-deployment", "14-c-repeat", "14-d-boss",
               "17-c-weapon-table", "19-c-movement-type", "22-c-painted", "22-d-second-unit", "27-c-objective",
               "29-c-add-section", "30-c-add-to", "32-c-trigger", "32-d-before", "32-e-repeat", "33-c-call-help",
               "33-d-triggered", "35-c-alternate", "36-c-ending", "37-c-caller", "37-d-parse-error", "44-c-in-range",
               "50-c-consumer", "51-c-render", "55-c-layout", "55-d-ranged", "58-c-rewind", "61-c-clean-result",
               "62-c-boundary-one", "62-d-boundary-two"]
#: Why a planned frame is not captured yet. Frames not listed need a scripted Play run or a recorded edit.
BLOCKED = {
    "dolphin": ["04-b", "27-c", "36-c", "40-b", "41-b", "42-b", "46-b", "47-b", "48-b", "49-b", "50-c", "59-b",
                "60-b", "61-b", "61-c", "62-b", "62-c", "62-d", "14-c", "33-d"],
    "blender": ["51-a", "52-a"],
    "sample media": ["42-a", "50-b", "52-b", "53-a", "53-b"],
    "a save file": ["59-a"],
}
LOG_PAGE = ROOT / "wiki" / "meta" / "tutorial-capture-log.md"


def write_log_page() -> None:
    log = json.loads(LOG.read_text(encoding="utf-8"))
    captured = {name.removesuffix(".png") for name in log}
    required = [f"{n:02d}-{x}" for n in range(1, 65) for x in ("a-setup", "b-result")] + PLAN_EXTRAS
    missing = [r for r in required if r not in captured]
    reason = {key: why for why, keys in BLOCKED.items() for key in keys}
    lines = ["---", 'id: "tutorial-capture-log"', 'title: "Tutorial capture log"',
             'description: "Every app screenshot used by the modding tutorials, and the frames still to capture"',
             'games: ["path-of-radiance"]', 'section: "meta"', 'article_type: "reference"',
             'tags: ["Contributing", "Modding app"]', "aliases: []", 'status: "draft"',
             f'last_reviewed: "{_dt.date.today().isoformat()}"', 'sources: ["telliusmodding-source"]',
             'cms_collection: "meta"', 'source_path: "meta/tutorial-capture-log.md"', "---",
             "# Tutorial capture log", "",
             "This page is written by `App/tools/capture_tutorial_screenshots.py` from "
             "`wiki/assets/images/tutorials/screenshots/capture_log.json`; edit the tool, not the page. It records the "
             "[capture plan](tutorial-screenshot-plan.md)'s frames: the ones taken, where each one is used, and the "
             "ones still to take.", "",
             "Every frame was taken by the tool from the real app on a disposable *Tutorial Practice* project "
             "(fresh USA extraction), in the app's default dark theme. A captured frame shows the app state "
             "named in its caption; it is not evidence of in-game behaviour. Frames from lessons 65 and above "
             "illustrate tutorials that the [2026-10-20 review](tutorial-coverage.md#review-2026-10-20) adds and that "
             "are not written yet.",
             "", f"**{len(log)} frames captured; {len(missing)} of the plan's {len(required)} required frames still "
             "to take.**", "", "## Captured frames", "",
             "| Frame | Lesson | Status | Caption |", "| --- | --- | --- | --- |"]
    for name, entry in sorted(log.items()):
        caption = entry["caption"].replace("|", "\\|")
        lines.append(f"| [`{name}`](../assets/images/tutorials/screenshots/{name}) | {entry['lesson']} | "
                     f"{entry['status']} | {caption} |")
    lines += ["", "## Frames still to take", "",
              "| Frame | Needs |", "| --- | --- |"]
    for frame in missing:
        why = reason.get(frame[:4], "a scripted Play run or a recorded edit (app only)")
        lines.append(f"| `{frame}` | {why} |")
    lines += ["", "Frames that need Dolphin are taken in a play session on a build of the capture project. "
              "Sample media (fonts, art, audio, video) must be made for the purpose, so no third-party rights are "
              "involved.", ""]
    LOG_PAGE.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ===================================================================================================
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", type=Path, help="the disposable capture project folder")
    parser.add_argument("--create", type=Path, help="source disc image: create and extract the project first")
    parser.add_argument("--only", nargs="*", help="step keys to run (prefix match, e.g. 01 21)")
    parser.add_argument("--list", action="store_true", help="list the steps")
    parser.add_argument("--survey-dir", type=Path, help="where the survey step writes its pictures")
    parser.add_argument("--insert", action="store_true",
                        help="only put the logged frames into the lesson pages (no capture)")
    args = parser.parse_args(argv)
    if args.insert:
        print("\n".join(insert_figures() + insert_diagrams()) or "no page changed")
        write_log_page()
        return 0
    if args.list:
        print("\n".join(s.key for s in STEPS))
        return 0
    if args.project is None:
        parser.error("--project is required")
    if "my fire emblem mod" in str(args.project).lower():
        parser.error("refusing to run on the working project; use a disposable copy")
    if args.survey_dir:
        SURVEY_DIR.append(args.survey_dir)
    steps = [s for s in STEPS if (s.key != "survey" or args.survey_dir)
             and (not args.only or any(s.key.startswith(o) for o in args.only))]
    if not args.project.is_dir() and args.create is None:
        parser.error("the project does not exist; pass --create with the source disc image")
    return run(steps, args.project, args.create)


if __name__ == "__main__":
    sys.exit(main())
