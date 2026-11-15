"""The Battle Data and Battle Cameras pages: one page shape, one adapter per game."""

import os
import shutil
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import battle_tables
from fe_modding.formats import zdbx
from fe_modding.games import Game
from fe_modding.gui.battle_browser import BattleBrowser
from fe_modding.gui.battle_camera_adapters import (Fe10CameraAdapter, PorCameraAdapter,
                                                   battle_camera_viewer)
from fe_modding.gui.battle_data_adapters import DbxAdapter, Fe10BattleAdapter, battle_data_viewer
from fe_modding.gui.changelog import ChangeLog
from fe_modding.project import ModProject

T, NL = chr(9), chr(13) + chr(10)  # the files use tabs and CRLF
CAMERA_SCRIPT = NL.join(["{", T + "class" + T + "CameraAnime", T + "name" + T + "atk_l", T + "caption" + T + "Attack",
                         T + "camera" + T + "cam1", T + "num" + T + T + "1", T + "pos" + T + T + "0.00, 7.00, 0.00",
                         T + "rot" + T + T + "0.00, 180.00, 0.00", T + "dist" + T + "40.00", T + "time" + T + "0", "}", ""])
CAMERA_RIGS = NL.join(["{", T + "class" + T + "Camera", T + "name" + T + "cam1", T + "enable" + T + "1",
                       T + "eyeCenter" + T + "1", T + "pos" + T + T + "0.0, 9.5, 60.0", T + "rot" + T + T + "-5.0, 0.0, 0.0",
                       "}", ""])


class _TkCase(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def page(self, factory, project):
        page = factory(self.root, project, ChangeLog())
        self.addCleanup(page.destroy)
        return page


class PorBattleDataTests(_TkCase):
    def setUp(self):
        super().setUp()
        self.project = ModProject.create(self.tmp, "DBX", Game.PATH_OF_RADIANCE)
        files = self.project.extracted_dir / "files"
        files.mkdir(parents=True, exist_ok=True)
        (files / "zdbx.cmp").write_bytes(zdbx.build_zdbx_archive([
            ("zdbx/system.dbx", b"# first\r\n{\r\n\tclass\tSystem\r\n}\r\n"),
            ("ztex/image.tpl", b"\x00\xff"),
        ]))
        self.view = self.page(battle_data_viewer, self.project)
        self.adapter = self.view.adapter

    def test_the_page_uses_the_dbx_adapter_and_groups_by_folder(self):
        self.assertIsInstance(self.view, BattleBrowser)
        self.assertIsInstance(self.adapter, DbxAdapter)
        # one folder of text tables: the list is flat (groups only show when there are several)
        self.assertEqual(self.view._tree.get_children(), ("zdbx/system.dbx",))
        self.assertEqual(self.view._tree.item("zdbx/system.dbx", "text"), "system.dbx")

    def test_edit_add_delete_restore(self):
        path = "zdbx/system.dbx"
        self.view.select(path)
        self.adapter._editor.insert("end-1c", "# added\n")
        self.assertTrue(self.view.dirty)
        self.assertTrue(self.view.save())
        self.assertFalse(self.view.dirty)
        self.assertIn("# added\r\n", battle_tables.read_entry(self.project, path))
        self.assertEqual(battle_tables.inventory(self.project)[path], "edited")

        with patch("fe_modding.gui.battle_data_adapters.messagebox.askyesno", return_value=True):
            self.adapter._delete()
        self.assertEqual(battle_tables.inventory(self.project)[path], "deleted")
        self.adapter._restore()
        self.assertEqual(battle_tables.inventory(self.project)[path], "original")

        with patch("fe_modding.gui.battle_data_adapters.simpledialog.askstring", return_value="xcam/new.dbx"):
            self.adapter._add()
        self.adapter._editor.insert("1.0", "{\n\tclass\tCameraAnime\n}\n")
        self.assertTrue(self.view.save())
        self.assertEqual(battle_tables.inventory(self.project)["xcam/new.dbx"], "added")
        self.assertEqual(self.view.selected(), "xcam/new.dbx")
        self.adapter._restore()
        self.assertNotIn("xcam/new.dbx", battle_tables.inventory(self.project))
        entries = zdbx.read_zdbx_files((self.project.extracted_dir / "files" / "zdbx.cmp").read_bytes())
        self.assertEqual(entries[1], ("ztex/image.tpl", b"\x00\xff"))

    def test_leaving_an_edited_file_asks_and_cancel_keeps_it(self):
        self.view.select("zdbx/system.dbx")
        self.adapter._editor.insert("end-1c", "# draft\n")
        with patch("fe_modding.gui.battle_data_adapters.messagebox.askyesnocancel", return_value=None):
            self.assertFalse(self.adapter.leave())
        self.assertTrue(self.view.dirty)
        with patch("fe_modding.gui.battle_data_adapters.messagebox.askyesnocancel", return_value=False):
            self.assertTrue(self.adapter.leave())
        self.assertFalse(self.view.dirty)


class PorBattleCameraTests(_TkCase):
    def setUp(self):
        super().setUp()
        self.project = ModProject.create(self.tmp, "Cameras", Game.PATH_OF_RADIANCE)
        files = self.project.extracted_dir / "files"
        files.mkdir(parents=True, exist_ok=True)
        (files / "zdbx.cmp").write_bytes(zdbx.build_zdbx_archive([
            ("xcam/atk_l.dbx", CAMERA_SCRIPT.encode()),
            ("zdbx/camera.dbx", CAMERA_RIGS.encode()),
        ]))
        self.view = self.page(battle_camera_viewer, self.project)
        self.adapter = self.view.adapter

    def test_scripts_and_rigs_are_two_groups_of_one_list(self):
        self.assertIsInstance(self.adapter, PorCameraAdapter)
        groups = self.view._tree.get_children()
        self.assertEqual([self.view._tree.item(g, "text") for g in groups],
                         ["Camera scripts (xcam)", "Camera rigs (camera.dbx)"])
        self.assertEqual(self.view._tree.get_children(groups[0]), ("script:atk_l",))
        self.assertEqual(self.view._tree.get_children(groups[1]), ("rig:cam1",))

    def test_apply_a_keyframe_then_restore(self):
        self.view.select("script:atk_l")
        self.assertEqual(len(self.adapter._frames), 1)
        self.adapter._frame_tree.selection_set("0")
        self.adapter._load_frame_fields()
        self.adapter._frame_vars["time"].set("25")
        self.adapter._update_frame()
        self.adapter._apply_script()
        self.assertIn("25", battle_tables.read_entry(self.project, "xcam/atk_l.dbx"))
        self.assertEqual(self.view._tree.item("script:atk_l", "values")[1], "edited")
        self.adapter._restore()
        self.assertFalse(battle_tables.is_modified(self.project, "xcam/atk_l.dbx"))


@unittest.skipUnless(os.environ.get("FE10_EXTRACTED_FILES"), "set FE10_EXTRACTED_FILES to an extracted RD files/ directory")
class RdBattlePagesTests(_TkCase):
    def setUp(self):
        super().setUp()
        source = Path(os.environ["FE10_EXTRACTED_FILES"])
        self.project = ModProject.create(self.tmp, "RD battle", Game.RADIANT_DAWN)
        files = self.project.extracted_dir / "files"
        files.mkdir(parents=True, exist_ok=True)
        shutil.copy(source / "FE10Battle.cms", files / "FE10Battle.cms")
        shutil.copytree(source / "xcam", files / "xcam")

    def test_battle_data_lists_every_table_and_edits_a_scenery_choice(self):
        view = self.page(battle_data_viewer, self.project)
        adapter = view.adapter
        self.assertIsInstance(adapter, Fe10BattleAdapter)
        groups = view._tree.get_children()
        self.assertEqual(len(groups), len(adapter._document.tables) + 1)   # + the camera arrays
        view.select("FE10BMapData:0")
        self.assertIn("Map key:", adapter._detail.get("1.0", "end"))
        before = adapter._document.map_data[0].model_indices[0]
        with patch("fe_modding.gui.battle_data_adapters.simpledialog.askinteger", side_effect=[0, -1]):
            adapter._edit_map_variant()
        self.assertTrue(view.dirty)
        self.assertIsNone(adapter._document.map_data[0].model_indices[0])
        with patch("fe_modding.gui.battle_browser.messagebox.askyesno", return_value=True):
            view._discard()
        self.assertFalse(view.dirty)
        self.assertEqual(adapter._document.map_data[0].model_indices[0], before)

    def test_battle_cameras_list_the_clips_against_the_registry(self):
        view = self.page(battle_camera_viewer, self.project)
        adapter = view.adapter
        self.assertIsInstance(adapter, Fe10CameraAdapter)
        states = {view._tree.item(k, "values")[2] for k in view._tree.get_children()}
        self.assertIn("registered", states)
        self.assertGreater(len(view._tree.get_children()), 50)


if __name__ == "__main__":
    unittest.main()
