"""Exercise form edits through the real FE10 data codec without opening a window."""
import os
import shutil
import struct
import sys
import tempfile
import tkinter as tk
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import fe10data
from fe_modding.games import Game
from fe_modding.gui.changelog import ChangeLog
from fe_modding.gui.fe10_data_editor import Fe10DataEditor
from fe_modding.gui.fe8_session import Fe10DataSession
from fe_modding.gui.pages.data import FE10_DATA_TILES, GameDataPage
from fe_modding.gui.widgets import SaveDiscardBar
from fe_modding.project import ModProject
from tests.test_fe10data import _container

FILES = Path(os.environ["FE10_EXTRACTED_FILES"]) if os.environ.get("FE10_EXTRACTED_FILES") else None


class BiorhythmFormTests(unittest.TestCase):
    def editor(self, text):
        data = _container(struct.pack(">40f", *([0.5] * 40)), [], [("BioData", 0)])
        return SimpleNamespace(
            kind="biorhythm", _tab="biorhythm", _selected={"biorhythm": 0},
            _vars={"value_0": Mock(get=Mock(return_value=text))},
            _data=data, _db=fe10data.Fe10Data({"biorhythm": fe10data.read_table(data, "biorhythm")}),
            _text=Fe10DataEditor._text, _replace=Mock(),
        )

    def test_decimal_edits_reach_the_binary_data(self):
        for value in ("1.25", "-2.5", "1e-2"):
            with self.subTest(value=value):
                editor = self.editor(value)
                with patch("fe_modding.gui.fe10_data_editor.messagebox.showerror") as error:
                    Fe10DataEditor._apply_field(editor, "value_0", 0)
                error.assert_not_called()
                editor._replace.assert_called_once()
                data = editor._replace.call_args.args[0]
                records = fe10data.read_table(data, "biorhythm")
                self.assertAlmostEqual(records[0].values["value_0"], float(value))
                self.assertEqual(records[0].values["value_1"], 0.5)
                self.assertEqual(records[1].values["value_0"], 0.5)

    def test_invalid_decimal_keeps_the_original_value(self):
        editor = self.editor("invalid")
        with patch("fe_modding.gui.fe10_data_editor.messagebox.showerror") as error:
            Fe10DataEditor._apply_field(editor, "value_0", 0)
        error.assert_called_once()
        editor._replace.assert_not_called()
        editor._vars["value_0"].set.assert_called_once_with("0.5")


class RecordRouteTests(unittest.TestCase):
    def test_fixed_row_labels_use_decoded_game_data_names(self):
        difficulty = SimpleNamespace(kind="difficulty", id=None, index=0, values={})
        biorhythm = SimpleNamespace(kind="biorhythm", id=None, index=0, values={})

        self.assertEqual(Fe10DataEditor._record_label(difficulty), "Kill EXP base")
        difficulty.index = 9
        self.assertEqual(Fe10DataEditor._record_label(difficulty), "Weapon EXP multiplier (%)")
        self.assertEqual(Fe10DataEditor._record_label(biorhythm), "Row 1")

    def test_record_breadcrumb_resolves_ids_and_fixed_row_indices(self):
        named = SimpleNamespace(id="JID_HERO", index=2)
        fixed = SimpleNamespace(id=None, index=3)
        editor = SimpleNamespace(
            _db=object(),
            _table=lambda _kind: [named, fixed],
            _record_name=lambda record: "Hero" if record is named else "",
            _record_label=lambda record: record.id or f"Row {record.index + 1}",
        )

        self.assertEqual(Fe10DataEditor.record_title(editor, "classes", "JID_HERO"), "Hero")
        self.assertEqual(Fe10DataEditor.record_title(editor, "classes", "3"), "Row 4")
        self.assertEqual(Fe10DataEditor.record_title(editor, "classes", "missing"), "missing")

    def test_growth_edits_remain_visible_to_save_all_with_a_shared_session(self):
        editor = SimpleNamespace(_growth_dirty=True, _session=object(), _dirty=False)
        self.assertTrue(Fe10DataEditor.dirty.fget(editor))
        self.assertFalse(Fe10DataEditor.shares_fe8_session)

    def test_excel_actions_follow_the_tables_with_a_sheet(self):
        from fe_modding.game_adapter import RdDataAdapter

        export, import_ = Mock(), Mock()
        adapter = RdDataAdapter(SimpleNamespace(data=b"", fe10=None))
        editor = SimpleNamespace(
            _tab="chapters", _growth_data=b"growth", _db=object(), _adapter=lambda: adapter,
            _growth_export_button=export, _growth_import_button=import_,
        )
        Fe10DataEditor._sync_growth_excel_buttons(editor)  # chapters: no sheet
        export.pack_forget.assert_called_once_with()
        import_.pack_forget.assert_called_once_with()
        export.pack.assert_not_called()

        for tab in ("growth", "classes", "items", "terrain"):
            export.reset_mock()
            editor._tab = tab
            Fe10DataEditor._sync_growth_excel_buttons(editor)
            export.pack.assert_called_once_with(side="left", padx=(6, 0))


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to exercise the shared RD record browser")
class SharedBrowserCorpusTests(unittest.TestCase):
    def _project(self, root: Path) -> ModProject:
        project = ModProject.create(root, "RD UI parity", Game.RADIANT_DAWN)
        project.files_dir.mkdir(parents=True, exist_ok=True)
        for logical in ("game_data", "growth_data", "ai_data"):
            source = project.profile.path(FILES, logical)
            if source.is_file():
                target = project.profile.path(project.files_dir, logical)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        return project

    def test_list_select_edit_save_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))

            root = tk.Tk()
            root.withdraw()
            self.addCleanup(root.destroy)
            session = Fe10DataSession(project, ChangeLog())
            routes = []
            editor = Fe10DataEditor(root, project, ChangeLog(), session=session, navigate=routes.append)
            editor.pack()
            root.update_idletasks()

            editor.select_tab("classes")
            self.assertGreater(len(editor._browser.labels), 0)
            record = session.fe10.classes[0]
            editor.select_record(record.id)
            self.assertEqual(editor._browser.current, record.index)
            self.assertEqual(editor.record_title("classes", record.id), editor._record_name(record) or record.id)

            numeric = next(field for field in fe10data.field_defs("class") if field.kind != "label")
            old = record.values[numeric.key]
            replacement = float(old) + 0.25 if numeric.kind == "f32" else int(old) + 1
            session.replace(fe10data.patch_field(session.data, "class", record.index, numeric.key, replacement))
            self.assertTrue(session.dirty)
            session.save()
            reopened = Fe10DataSession(project, ChangeLog())
            self.assertEqual(reopened.fe10.classes[record.index].values[numeric.key], replacement)

            current = session.fe10.classes[record.index]
            replacement_2 = float(replacement) + 0.25 if numeric.kind == "f32" else int(replacement) + 1
            session.replace(fe10data.patch_field(session.data, "class", current.index, numeric.key, replacement_2))
            self.assertTrue(session.dirty)
            with patch("fe_modding.gui.fe10_data_editor.messagebox.askyesno", return_value=True):
                editor._revert()
            self.assertFalse(session.dirty)
            self.assertEqual(session.fe10.classes[current.index].values[numeric.key], replacement)

            editor._browser.select(record.index)
            self.assertEqual(routes[-1], ("data", "classes", record.id))

    def test_shared_page_owns_fe10_tables_and_ai(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            root = tk.Tk()
            root.withdraw()
            self.addCleanup(root.destroy)
            changelog = ChangeLog(project)
            session = Fe10DataSession(project, changelog)
            routes = []
            shell = SimpleNamespace(host=root, project=project, changelog=changelog, session=session,
                                    navigate=routes.append, index=None, route=("data",))

            page = GameDataPage(shell)
            self.assertTrue(page._fe10)
            self.assertEqual(page.panels(), [page._editor, page._ai])
            self.assertNotIn("characters", FE10_DATA_TILES)
            self.assertIsInstance(page._editor.toolbar, SaveDiscardBar)
            self.assertEqual(page._editor._browser._tile_width, 230)
            self.assertEqual(page._editor._add_button.cget("text"), "New…")
            self.assertEqual(page._editor._status.cget("text"), "")

            self.assertTrue(page.show(("data", "classes")))
            self.assertEqual(page._editor.winfo_manager(), "pack")
            self.assertEqual(page._editor.toolbar.winfo_manager(), "pack")
            self.assertTrue(page.show(("data", "ai")))
            self.assertEqual(page._ai.winfo_manager(), "pack")
            self.assertEqual(page._editor.toolbar.winfo_manager(), "pack")
            self.assertEqual(page.crumbs(("data", "ai")), [("Game Data", ("data",)), ("AI (CP)", None)])
