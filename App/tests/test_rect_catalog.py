"""Focused checks for the rect RID catalogue and FE10 writer."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from fe_modding import rect_catalog as catalog
from fe_modding.formats import fe10_rect, message, rect, soundroom
from fe_modding.formats.cmb import compile_source, read_cmb, write_cmb
from fe_modding.games import Game


class RectCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.files = Path(self.temp.name) / "extracted" / "files"
        (self.files / "s").mkdir(parents=True)
        self.project = SimpleNamespace(files_dir=self.files, game=Game.PATH_OF_RADIANCE)

    def _write_rect(self):
        doc = rect.RectFile(resources=[], address_order=[], pool_order=[])
        doc.add(rect.new_background("RID_A", "s/aaa", 32, 32))
        doc.add(rect.RectResource("RID_BOX", layers=[rect.TextboxLayer(window="RID_A")]))
        path = self.files / "s" / "rect.bin"
        path.write_bytes(doc.build())
        return path

    def test_selected_file_catalog_and_references(self):
        path = self._write_rect()
        self.assertEqual(catalog.rect_paths(self.project), [path])
        doc = catalog.read_doc(self.project, path)
        self.assertEqual([item.name for item in doc.resources], ["RID_A", "RID_BOX"])
        self.assertEqual([(i, layer.file) for i, layer in catalog.image_layers(doc.find("RID_A"))],
                         [(0, "s/aaa")])
        refs = catalog.collect_references(self.project, "RID_A")
        self.assertEqual([(ref.kind, ref.location) for ref in refs],
                         [("Rect", "RID_BOX, layer 0, window")])

    def test_rename_updates_rect_dialogue_and_soundroom(self):
        path = self._write_rect()
        (self.files / "Mess").mkdir()
        mess = self.files / "Mess" / "c01.m"
        mess.write_bytes(message.write_messages([
            message.Message("MID_1", "$BA|"),
            message.Message("MID_2", "$RA|"),
        ]))
        sound = self.files / "soundroom.bin"
        sound.write_bytes(soundroom.build_soundroom([soundroom.SoundRoomEntry("RID_A")]))
        changes = catalog.prepare_rename(self.project, "RID_A", "RID_NEW")
        self.assertEqual(set(changes), {path, mess, sound})
        renamed = rect.parse_rect(changes[path])
        self.assertIsNotNone(renamed.find("RID_NEW"))
        self.assertEqual(renamed.find("RID_BOX").layers[0].window, "RID_NEW")
        self.assertIn(b"$BNEW|", changes[mess])
        self.assertEqual(soundroom.read_soundroom(changes[sound])[0].name, "RID_NEW")

    def test_script_reference_is_listed_and_renamed(self):
        self._write_rect()
        scripts = self.files / "Scripts"
        scripts.mkdir()
        path = scripts / "C01.cmb"
        path.write_bytes(write_cmb(compile_source('def f():\n    RectBuild("RID_A")\n').script))
        refs = catalog.collect_references(self.project, "RID_A")
        self.assertTrue(any(ref.kind == "Script" and ref.path == path for ref in refs))
        changes = catalog.prepare_rename(self.project, "RID_A", "RID_NEW")
        self.assertIn(path, changes)
        self.assertIn("RID_NEW", read_cmb(changes[path]).pool)

    def test_unreadable_rect_does_not_hide_valid_references(self):
        self._write_rect()
        bad = self.files / "window" / "RectDesc.bin"
        bad.parent.mkdir()
        bad.write_bytes(b"broken")
        refs = catalog.collect_references(self.project, "RID_A")
        self.assertTrue(any(ref.kind == "Rect" for ref in refs))
        self.assertTrue(any(ref.kind == "Unreadable rect" and ref.path == bad for ref in refs))
        with self.assertRaises(Exception):
            catalog.prepare_rename(self.project, "RID_A", "RID_NEW")

    def test_add_and_replace_keep_other_reference(self):
        path = self._write_rect()
        first = Image.new("RGBA", (32, 32), "red")
        changes = catalog.prepare_add(self.project, path, "RID_NEW", [first])
        self.assertEqual(len(changes), 2)
        for changed, data in changes.items():
            changed.write_bytes(data)
        doc = catalog.read_doc(self.project, path)
        self.assertEqual(len(list(catalog.image_layers(doc.find("RID_NEW")))), 1)
        replacement = Image.new("RGBA", (32, 32), "blue")
        changes = catalog.prepare_replace(self.project, path, "RID_NEW", 0, replacement)
        updated = rect.parse_rect(changes[path])
        self.assertNotEqual(updated.find("RID_NEW").layers[0].file, "s/aaa")
        self.assertEqual(updated.find("RID_A").layers[0].file, "s/aaa")


class Fe10EditableRectTests(unittest.TestCase):
    def test_add_and_roundtrip(self):
        doc = fe10_rect.EditableRect([], [], [], bytes(12))
        doc.add(fe10_rect.new_image_resource("RID_A", "s/aaa", 32, 32, 2))
        raw = doc.build()
        reread = fe10_rect.read_editable_rect(raw)
        self.assertEqual(reread.build(), raw)
        self.assertEqual([layer.texture for layer in reread.find("RID_A").layers], [0, 1])
        self.assertEqual(fe10_rect.read_rect(raw)["RID_A"].quads()[1].file, "s/aaa")

    def test_fe10_rect_pointer_reference(self):
        doc = fe10_rect.EditableRect([], [], [], bytes(12))
        doc.add(fe10_rect.new_image_resource("RID_A", "s/aaa", 32, 32))
        box = fe10_rect.new_image_resource("RID_BOX", "s/bbb", 32, 32)
        box.layers = [fe10_rect.EditableLayer(bytes([2]) + bytes(0x2f), {8: "RID_A"})]
        doc.add(box)
        with tempfile.TemporaryDirectory() as root:
            files = Path(root) / "files"
            (files / "window").mkdir(parents=True)
            path = files / "window" / "RectDesc.bin"
            path.write_bytes(doc.build())
            project = SimpleNamespace(files_dir=files, game=Game.RADIANT_DAWN)
            refs = catalog.collect_references(project, "RID_A")
            self.assertTrue(any(ref.kind == "Rect" and "RID_BOX" in ref.location for ref in refs))
            changed = catalog.prepare_rename(project, "RID_A", "RID_NEW")[path]
            renamed = fe10_rect.read_editable_rect(changed)
            self.assertEqual(renamed.find("RID_BOX").layers[0].strings[8], "RID_NEW")

    def test_fe10_dialogue_reference_and_rename(self):
        doc = fe10_rect.EditableRect([], [], [], bytes(12))
        doc.add(fe10_rect.new_image_resource("RID_A", "s/aaa", 32, 32))
        with tempfile.TemporaryDirectory() as root:
            files = Path(root) / "files"
            (files / "s").mkdir(parents=True)
            (files / "Mess").mkdir()
            rect_path = files / "s" / "rect.bin"
            rect_path.write_bytes(doc.build())
            mess_path = files / "Mess" / "e_c0101.m"
            mess_path.write_bytes(message.write_messages([message.Message("MID_A", "\x04B:A|")]))
            project = SimpleNamespace(files_dir=files, game=Game.RADIANT_DAWN)
            refs = catalog.collect_references(project, "RID_A")
            self.assertTrue(any(ref.kind == "Dialogue" and ref.location == "MID_A" for ref in refs))
            changes = catalog.prepare_rename(project, "RID_A", "RID_NEW")
            self.assertIn(b"\x04B:NEW|", changes[mess_path])

    def test_rename_keeps_other_raw_layer_fields(self):
        doc = fe10_rect.EditableRect([], [], [], bytes(12))
        doc.add(fe10_rect.new_image_resource("RID_A", "s/aaa", 32, 32))
        old = doc.build()
        with tempfile.TemporaryDirectory() as root:
            files = Path(root) / "files"
            (files / "s").mkdir(parents=True)
            path = files / "s" / "rect.bin"
            path.write_bytes(old)
            project = SimpleNamespace(files_dir=files, game=Game.RADIANT_DAWN)
            changes = catalog.prepare_rename(project, "RID_A", "RID_B")
            self.assertEqual(list(fe10_rect.read_rect(changes[path])), ["RID_B"])
            self.assertEqual(fe10_rect.read_editable_rect(changes[path]).build(), changes[path])


if __name__ == "__main__":
    unittest.main()
