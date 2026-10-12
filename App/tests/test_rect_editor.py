"""Non-image RID editing and preview contracts."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from fe_modding import rect_catalog, rect_editor
from fe_modding.formats import rect
from fe_modding.games import Game


def sample():
    doc = rect.RectFile([], [], [])
    doc.add(rect.RectResource("RID_LAYOUT", mode=rect.MODE_STACK, layers=[
        rect.GradientLayer((10, 10, 90, 50), ((200, 0, 0, 255),) * 4),
        rect.TextLayer("Sample", 15, 15),
        rect.TextboxLayer(window="RID_FRAME", text_x=18, text_y=55, width=90),
        rect.SeatsLayer([(60, 130, 0, 0, 0)]),
    ]))
    doc.add(rect.RectResource("RID_FRAME", layers=[rect.GradientLayer((0, 0, 100, 100))]))
    return doc


class RectEditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        files = Path(self.temp.name) / "files"
        (files / "window").mkdir(parents=True)
        self.path = files / "window" / "RectDesc.bin"
        self.path.write_bytes(sample().build())
        self.project = SimpleNamespace(files_dir=files, game=Game.PATH_OF_RADIANCE)

    def test_edit_round_trip_preserves_unselected_fields_and_other_resources(self):
        original = self.path.read_bytes()
        resource = rect.parse_rect(original).find("RID_LAYOUT")
        edited = rect_editor.update(resource, {"depth": "600", "brightness": "220"})
        edited.layers[1] = rect_editor.update(edited.layers[1], {"text": "New text", "x": "30"})
        edited.layers[2] = rect_editor.update(edited.layers[2], {"width": "150"})
        edited.layers[3] = rect_editor.update(edited.layers[3], {"seats": "77, 142, 0, 1, 0"})
        result = rect.parse_rect(rect_editor.prepare_edit(self.project, self.path, "RID_LAYOUT", edited, original)[self.path])
        self.assertEqual(result.find("RID_LAYOUT").depth, 600)
        self.assertEqual(result.find("RID_LAYOUT").layers[1].text, "New text")
        self.assertEqual(result.find("RID_LAYOUT").layers[3].seats[0][:2], (77, 142))
        self.assertEqual(result.find("RID_FRAME"), rect.parse_rect(original).find("RID_FRAME"))

    def test_rejects_new_missing_link_and_stale_source(self):
        original = self.path.read_bytes()
        edited = rect.parse_rect(original).find("RID_LAYOUT")
        edited.layers[2].window = "RID_MISSING"
        with self.assertRaisesRegex(ValueError, "Unknown RID link"):
            rect_editor.prepare_edit(self.project, self.path, "RID_LAYOUT", edited, original)
        self.path.write_bytes(original + b"changed")
        with self.assertRaisesRegex(ValueError, "changed since"):
            rect_editor.prepare_edit(self.project, self.path, "RID_LAYOUT", edited, original)

    def test_field_validation_and_preview(self):
        field = next(item for item in rect_editor.fields_for(rect.TextLayer("x")) if item.name == "x")
        with self.assertRaises(ValueError):
            rect_editor.parse(field, "40000")
        with self.assertRaises(ValueError):
            rect_editor.parse(rect_editor.Field("colors", "Colors", "colors"), "#FF0000FF")
        resource = sample().find("RID_LAYOUT")
        image, notes = rect_editor.render(self.project, resource, {r.name: r for r in sample().resources})
        self.assertIsInstance(image, Image.Image)
        self.assertEqual(image.size, (608, 448))
        self.assertFalse(notes)
        self.assertNotEqual(image.getpixel((20, 20)), (30, 34, 42, 255))

    def test_failed_save_restores_original_bytes(self):
        original = self.path.read_bytes()
        edited = rect.parse_rect(original).find("RID_LAYOUT")
        edited.depth = 601
        changes = rect_editor.prepare_edit(self.project, self.path, "RID_LAYOUT", edited, original)

        def fail_after_write(path, data):
            path.write_bytes(data)
            raise OSError("simulated write failure")

        project = SimpleNamespace(files_dir=self.project.files_dir, write_keeping_original=fail_after_write)
        with self.assertRaises(OSError):
            rect_catalog.save_changes(project, changes, SimpleNamespace(append=lambda *args: None), "Edit")
        self.assertEqual(self.path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
