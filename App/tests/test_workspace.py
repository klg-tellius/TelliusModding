"""The redesigned workspace: chapter helpers, the project index and the
shell's routing/history."""

from __future__ import annotations

import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

from fe_modding import chapters
from fe_modding.games import Game
from fe_modding.project_index import ProjectIndex


def _fake_project(extracted: Path):
    return SimpleNamespace(extracted_dir=extracted, game=Game.PATH_OF_RADIANCE, has_extracted_files=True,
                           name="Test", directory=extracted.parent,
                           game_info=SimpleNamespace(short_code="PoR"))


class ChapterHelperTests(unittest.TestCase):
    def test_map_folder_to_chapter(self):
        self.assertEqual(chapters.chapter_of_map_folder("bmap06_2"), "06")
        self.assertEqual(chapters.chapter_of_map_folder("bmap31"), "31")
        self.assertIsNone(chapters.chapter_of_map_folder("trial_01"))
        self.assertIsNone(chapters.chapter_of_map_folder("always"))

    def test_phases_in_play_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            zmap = Path(tmp) / "files" / "zmap"
            for name in ("bmap09_3", "bmap09", "bmap09_10", "bmap09_2", "bmap10", "bmap090x"):
                (zmap / name).mkdir(parents=True)
            project = _fake_project(Path(tmp))
            self.assertEqual(chapters.chapter_phases(project, "09"), ["bmap09", "bmap09_2", "bmap09_3", "bmap09_10"])
            self.assertEqual(chapters.chapter_phases(project, "11"), [])

    def test_asset_file_lists(self):
        from fe_modding.gui.pages.text_assets import message_files, script_files
        with tempfile.TemporaryDirectory() as tmp:
            files = Path(tmp) / "files"
            (files / "Mess").mkdir(parents=True)
            (files / "Scripts").mkdir()
            for name in ("c10.m", "common.m", "c02.m", "a.m"):
                (files / "Mess" / name).touch()
            for name in ("C10.cmb", "zz.cmb", "startup.cmb", "C02.cmb", "C07.cmb"):
                (files / "Scripts" / name).touch()
            project = _fake_project(Path(tmp))
            self.assertEqual([(p.name, c) for p, c in message_files(project)],
                             [("c02.m", "02"), ("c10.m", "10"), ("a.m", None), ("common.m", None)])
            # C07 has no chapter page (no c07.m): it is listed with the shared scripts
            self.assertEqual([(p.name, c) for p, c in script_files(project)],
                             [("C02.cmb", "02"), ("C10.cmb", "10"), ("startup.cmb", None), ("C07.cmb", None),
                              ("zz.cmb", None)])

    def test_display_title_falls_back_to_number(self):
        self.assertEqual(chapters.chapter_display_title("01", {"01": "Prologue: Mercenaries"}), "Prologue: Mercenaries")
        self.assertEqual(chapters.chapter_display_title("32", {}), "Chapter 32")


class PageHelperTests(unittest.TestCase):
    def test_plain_text_strips_commands(self):
        from fe_modding.gui.shell import plain_text
        text = "$R上下会話|$FCL_IKE|$c0IKANAU|This$MC... $MD$w3This\ncan't be$K"
        self.assertEqual(plain_text(text), "This... This can't be")

    def test_section_titles(self):
        from fe_modding.gui.pages.chapters import _message_group, _section_title
        self.assertEqual(_section_title("bmap03_mikata_n"), "Player units")
        self.assertEqual(_section_title("bmap06_2_mikata_h"), "Player units")
        self.assertEqual(_section_title("bmap03_first_boss_n"), "Boss (first_boss)")
        self.assertEqual(_section_title("bmap03_first_n"), "First")
        self.assertEqual(_message_group("MS_03_OP_01"), "OP")
        self.assertEqual(_message_group("MDIE_IKE_MAP1"), "MDIE")


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED"), "set FE9_EXTRACTED to the extracted FE9 project")
class ProjectIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = ProjectIndex(_fake_project(Path(os.environ["FE9_EXTRACTED"])))
        cls.index.build()

    def test_builds_without_error(self):
        self.assertIsNone(self.index.error)

    def test_ike(self):
        ike = self.index.by_pid["PID_IKE"]
        self.assertEqual(ike.name, "Ike")
        self.assertEqual(ike.portrait_file, "IKE.cms")
        self.assertEqual(ike.class_name, "Ranger")
        self.assertEqual(ike.category, "playable")
        self.assertIn("PID_IKE_EV", ike.variants)
        self.assertTrue(ike.battle_model and ike.battle_model.startswith("zu/"))
        self.assertTrue(ike.map_model and ike.map_model.startswith("ymu/"))

    def test_story_copies_group_under_main_record(self):
        boyd_map1 = self.index.by_pid["PID_BOLE_MAP1"]
        self.assertEqual(boyd_map1.main_pid, "PID_BOLE")
        self.assertNotIn(boyd_map1, self.index.main_characters())

    def test_chapters_have_game_titles_and_phases(self):
        prologue = self.index.by_chapter["01"]
        self.assertEqual(prologue.title, "Prologue: Mercenaries")
        self.assertEqual(self.index.by_chapter["07"].phases, ("bmap07",))
        self.assertIn("bmap06_2", self.index.by_chapter["06"].phases)

    def test_appearances(self):
        boyd = [c.pid for c in self.index.family("PID_BOLE")]
        folders = {d.folder for d in self.index.deployments_of(boyd)}
        self.assertIn("bmap01", folders)  # PID_BOLE_MAP1, the Prologue's Boyd
        self.assertTrue(any(r.chapter_id == "01" for r in self.index.messages_of(["PID_IKE"])))
        self.assertTrue(any(r.chapter_id == "01" for r in self.index.script_refs_of(["PID_IKE"])))


class _FakePage:
    """Stands in for a page: records what it was asked to show."""

    def __init__(self, kind, refuse=()):
        self.kind, self.refuse, self.shown = kind, set(refuse), []

    def __call__(self, shell):
        from fe_modding.gui.shell import Page

        outer = self

        class P(Page):
            kind = outer.kind

            def show(self, route):
                outer.shown.append(route)
                return route not in outer.refuse

            def crumbs(self, route):
                return [(outer.kind, None)]

        return P(shell)


class ShellRoutingTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        from fe_modding.gui.changelog import ChangeLog
        from fe_modding.gui.shell import Shell
        self.pages = {k: _FakePage(k, refuse={("chapter", "99")} if k == "chapter" else ())
                      for k in ("home", "chapters", "chapter", "characters", "character")}
        self.shell = Shell(self.root, _fake_project(Path(self.tmp.name)), ChangeLog(), self.pages,
                           on_close_project=lambda: None)

    def tearDown(self):
        self.root.destroy()
        self.tmp.cleanup()

    def test_back_and_forward(self):
        s = self.shell
        for route in (("home",), ("chapters",), ("chapter", "03"), ("character", "PID_IKE")):
            self.assertTrue(s.navigate(route))
        s.back()
        self.assertEqual(s.route, ("chapter", "03"))
        s.back()
        self.assertEqual(s.route, ("chapters",))
        s.forward()
        self.assertEqual(s.route, ("chapter", "03"))
        s.navigate(("home",))
        s.forward()  # a new navigation clears the forward history
        self.assertEqual(s.route, ("home",))

    def test_refused_route_keeps_current_page(self):
        s = self.shell
        s.navigate(("chapter", "03"))
        self.assertFalse(s.navigate(("chapter", "99")))
        self.assertEqual(s.route, ("chapter", "03"))

    def test_replace_route_adds_no_history(self):
        s = self.shell
        s.navigate(("home",))
        s.navigate(("chapter", "03"))
        s.replace_route(("chapter", "03", "map"))
        s.back()
        self.assertEqual(s.route, ("home",))


class SaveAllTests(unittest.TestCase):
    """Closing (or building) with unsaved edits can save them all first."""

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        from fe_modding.gui.changelog import ChangeLog
        from fe_modding.gui.editor_panel import EditorPanel
        from fe_modding.gui.shell import Page, Shell

        class Public(EditorPanel):  # a ``save() -> bool`` editor
            display_name = "Public"

            def save(self):
                self._dirty = False
                return True

        class Private(EditorPanel):  # a ``_save() -> None`` editor
            display_name = "Private"

            def _save(self):
                self._dirty = False

        class Failing(EditorPanel):  # its save reports an error and keeps the edits
            display_name = "Failing"

            def _save(self):
                pass

        self.panels = {}
        outer = self

        def page(shell):
            class P(Page):
                kind = "home"

                def show(self, route):
                    return True

                def crumbs(self, route):
                    return [("home", None)]

                def panels(self):
                    return list(outer.panels.values())

            for cls in (Public, Private, Failing):
                outer.panels[cls.display_name] = cls(shell)
            return P(shell)

        self.shell = Shell(self.root, _fake_project(Path(self.tmp.name)), ChangeLog(), {"home": page},
                           on_close_project=lambda: None)
        self.shell.navigate(("home",))

    def tearDown(self):
        self.root.destroy()
        self.tmp.cleanup()

    def _dirty(self, *names):
        for name in names:
            self.panels[name]._dirty = True

    def test_save_all_saves_every_kind_of_editor(self):
        self._dirty("Public", "Private")
        self.assertEqual(self.shell.save_all(), [])
        self.assertEqual(self.shell.unsaved(), [])

    def test_save_all_reports_what_stayed_unsaved(self):
        self._dirty("Public", "Failing")
        self.assertEqual(self.shell.save_all(), ["Failing"])
        self.assertEqual(self.shell.unsaved(), ["Failing"])

    def test_confirm_unsaved_choices(self):
        from unittest import mock
        ask = "fe_modding.gui.shell.messagebox.askyesnocancel"
        self.assertTrue(self.shell.confirm_unsaved("", "close."))  # nothing unsaved: no question
        self._dirty("Public")
        with mock.patch(ask, return_value=None):
            self.assertFalse(self.shell.confirm_unsaved("", "close."))  # Cancel
        self.assertEqual(self.shell.unsaved(), ["Public"])
        with mock.patch(ask, return_value=False):
            self.assertTrue(self.shell.confirm_unsaved("", "close."))  # No: go on, nothing saved
        self.assertEqual(self.shell.unsaved(), ["Public"])
        with mock.patch(ask, return_value=True):
            self.assertTrue(self.shell.confirm_unsaved("", "close."))  # Yes: saved, then go on
        self.assertEqual(self.shell.unsaved(), [])
        self._dirty("Failing")
        with mock.patch(ask, return_value=True), mock.patch("fe_modding.gui.shell.messagebox.showerror") as error:
            self.assertFalse(self.shell.confirm_unsaved("", "close."))  # a failed save stops the close
        error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
