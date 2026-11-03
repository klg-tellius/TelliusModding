"""Smoke test for the general DBX editor's archive workflow."""

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
from fe_modding.gui.changelog import ChangeLog
from fe_modding.gui.dbx_files_viewer import DbxFilesViewer
from fe_modding.project import ModProject


class DbxFilesViewerTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "DBX", Game.PATH_OF_RADIANCE)
        files = self.project.extracted_dir / "files"
        files.mkdir(parents=True, exist_ok=True)
        (files / "zdbx.cmp").write_bytes(zdbx.build_zdbx_archive([
            ("zdbx/system.dbx", b"# first\r\n{\r\n\tclass\tSystem\r\n}\r\n"),
            ("ztex/image.tpl", b"\x00\xff"),
        ]))
        self.viewer = DbxFilesViewer(self.root, self.project, ChangeLog())
        self.addCleanup(self.viewer.destroy)

    def test_edit_add_delete_restore(self):
        path = "zdbx/system.dbx"
        self.viewer._open(path)
        self.viewer._editor.insert("end-1c", "# added\n")
        self.assertTrue(self.viewer.save())
        self.assertIn("# added\r\n", battle_tables.read_entry(self.project, path))
        self.assertEqual(battle_tables.inventory(self.project)[path], "edited")

        with patch("fe_modding.gui.dbx_files_viewer.messagebox.askyesno", return_value=True):
            self.viewer._delete()
        self.assertEqual(battle_tables.inventory(self.project)[path], "deleted")
        self.viewer._restore()
        self.assertEqual(battle_tables.inventory(self.project)[path], "original")

        self.viewer._open("xcam/new.dbx", new=True)
        self.viewer._editor.insert("1.0", "{\n\tclass\tCameraAnime\n}\n")
        self.assertTrue(self.viewer.save())
        self.assertEqual(battle_tables.inventory(self.project)["xcam/new.dbx"], "added")
        self.viewer._restore()
        self.assertNotIn("xcam/new.dbx", battle_tables.inventory(self.project))
        entries = zdbx.read_zdbx_files((self.project.extracted_dir / "files" / "zdbx.cmp").read_bytes())
        self.assertEqual(entries[1], ("ztex/image.tpl", b"\x00\xff"))
