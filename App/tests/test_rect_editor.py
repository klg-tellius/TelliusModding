"""Non-image RID editing and preview contracts."""
from __future__ import annotations

import tempfile
import struct
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from fe_modding import rect_catalog, rect_editor
from fe_modding.formats import fe10_rect, rect
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


class RadiantDawnRectEditorTests(unittest.TestCase):
    def test_edit_non_image_layers_preserves_unknown_bytes(self):
        doc = fe10_rect.EditableRect([], [], [], bytes(12))
        box = fe10_rect.new_image_resource("RID_BOX", "s/unused", 16, 16)
        textbox = bytearray(0x30)
        textbox[0] = 2
        textbox[3] = 0x7a  # undecoded field must survive the edit
        struct.pack_into(">hhhhH", textbox, 0x14, 10, 20, 30, 40, 150)
        textbox[0x26:0x2a] = bytes((28, 3, 7, 255))
        seats = bytearray(18)
        seats[0] = 4
        struct.pack_into(">HhhHBB", seats, 8, 1, 60, 130, 0, 1, 0)
        box.layers = [fe10_rect.EditableLayer(bytes(textbox), {8: "RID_FRAME"}),
                      fe10_rect.EditableLayer(bytes(seats))]
        doc.add(box)
        doc.add(fe10_rect.new_image_resource("RID_FRAME", "s/frame", 16, 16))
        with tempfile.TemporaryDirectory() as root:
            files = Path(root) / "files"
            files.mkdir()
            path = files / "rect.bin"
            original = doc.build()
            path.write_bytes(original)
            project = SimpleNamespace(files_dir=files, game=Game.RADIANT_DAWN)
            edited = fe10_rect.read_editable_rect(original).find("RID_BOX")
            edited.layers[0] = rect_editor.update(edited.layers[0], {"text_x": "45", "width": "200"})
            edited.layers[1] = rect_editor.update(edited.layers[1], {"seats": "77, 142, 0, 1, 0"})
            changed = rect_editor.prepare_edit(project, path, "RID_BOX", edited, original)[path]
            saved = fe10_rect.read_editable_rect(changed).find("RID_BOX")
            self.assertEqual(struct.unpack_from(">h", saved.layers[0].raw, 0x14)[0], 45)
            self.assertEqual(struct.unpack_from(">H", saved.layers[0].raw, 0x1c)[0], 200)
            self.assertEqual(saved.layers[0].raw[3], 0x7a)
            self.assertEqual(saved.layers[1].raw[3:], seats[3:8] + seats[8:10] +
                             struct.pack(">hhHBB", 77, 142, 0, 1, 0))

    def test_rejects_change_to_seat_count(self):
        raw = bytearray(18)
        raw[0] = 4
        struct.pack_into(">H", raw, 8, 1)
        layer = fe10_rect.EditableLayer(bytes(raw))
        with self.assertRaisesRegex(ValueError, "number of portrait seats"):
            rect_editor.update(layer, {"seats": ""})


if __name__ == "__main__":
    unittest.main()
