import os
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import rect, tpl
from fe_modding.formats.fe9_conversation_assets import read_rect_resources


def _small_file() -> rect.RectFile:
    doc = rect.RectFile(resources=[], address_order=[], pool_order=[])
    doc.add(rect.new_background("RID_B", "s/bbb", 608, 296, textures=2, duration=1.5, brightness=200))
    doc.add(rect.new_background("RID_A", "s/aaa", 608, 448, effect=rect.EFFECT_SNOW))
    return doc


class RectBuildTests(unittest.TestCase):
    def test_build_then_parse_is_stable(self):
        data = _small_file().build()
        again = rect.parse_rect(data)
        self.assertEqual(again.build(), data)
        self.assertEqual([r.name for r in again.resources], ["RID_A", "RID_B"])  # export table sorted by name
        b = again.find("RID_B")
        self.assertEqual((b.mode, b.depth, b.duration, b.brightness), (2, 900, 1.5, 200))
        self.assertEqual([(l.file, l.texture, l.src) for l in b.layers],
                         [("s/bbb", 0, (0, 0, 608, 296)), ("s/bbb", 1, (0, 0, 608, 296))])
        self.assertEqual(again.find("RID_A").effect, rect.EFFECT_SNOW)

    def test_header_and_tables_are_consistent(self):
        data = _small_file().build()
        size, data_size, relocs, exports, imports = [int.from_bytes(data[i:i + 4], "big") for i in range(0, 20, 4)]
        self.assertEqual((size, exports, imports), (len(data), 2, 0))
        # 2 descriptors' name pointers + 3 layer pointers + 3 file pointers + 3 layer slots
        self.assertEqual(relocs, 2 + 3 + 3)
        table = 0x20 + data_size + 4 * relocs
        names = table + 8 * exports
        self.assertEqual(data[names:], b"RID_A\0RID_B\0")

    def test_the_conversation_reader_agrees(self):
        resources = read_rect_resources(_small_file().build())
        self.assertEqual(set(resources), {"RID_A", "RID_B"})
        self.assertEqual([p.resource for p in resources["RID_B"].parts], ["s/bbb", "s/bbb"])

    def test_add_keeps_shift_jis_order_and_rejects_duplicates(self):
        doc = _small_file()
        doc.add(rect.new_background("RID_街", "s/ccc", 8, 8))
        doc.add(rect.new_background("RID_AA", "s/ddd", 8, 8))
        self.assertEqual([r.name for r in doc.resources], ["RID_A", "RID_AA", "RID_B", "RID_街"])
        with self.assertRaises(rect.RectError):
            doc.add(rect.new_background("RID_A", "s/eee", 8, 8))
        doc.remove("RID_AA")
        self.assertIsNone(rect.parse_rect(doc.build()).find("RID_AA"))

    def test_out_of_range_fields_are_refused(self):
        doc = _small_file()
        doc.find("RID_A").effect = 300
        with self.assertRaises(rect.RectError):
            doc.build()

    def test_validate_reports_missing_and_out_of_range_layers(self):
        doc = _small_file()
        sizes = {"s/aaa": [(608, 448)], "s/bbb": [(608, 296)] * 2}
        self.assertEqual(rect.validate(doc, sizes.get), [])
        doc.find("RID_B").layers[1].texture = 5
        doc.find("RID_A").layers[0].src = (0, 0, 700, 448)
        doc.add(rect.new_background("RID_C", "s/none", 8, 8))
        problems = rect.validate(doc, sizes.get)
        self.assertEqual(len(problems), 3)

    def test_add_background_writes_a_clamped_cmpr_tpl(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = _small_file()
            images = [Image.new("RGB", (64, 32), (200, 10, 10)), Image.new("RGB", (64, 32), (10, 200, 10))]
            resource = rect.add_background(doc, tmp, "RID_NEW", images, duration=2.0)
            path = Path(tmp) / resource.layers[0].file
            infos = tpl.read_tpl_image_info_path(path)
            self.assertEqual([(i.width, i.height, i.format, i.wrap_s) for i in infos],
                             [(64, 32, tpl.FORMAT_CMPR, tpl.WRAP_CLAMP)] * 2)
            known = {"s/aaa": [(608, 448)], "s/bbb": [(608, 296)] * 2}

            def sizes(path):
                if path in known:
                    return known[path]
                target = Path(tmp) / path
                return [(i.width, i.height) for i in tpl.read_tpl_image_info_path(target)] if target.is_file() else None

            self.assertEqual(rect.validate(doc, sizes), [])
            with self.assertRaises(rect.RectError):
                rect.add_background(doc, tmp, "RID_BAD", [Image.new("RGB", (8, 8)), Image.new("RGB", (16, 8))])

    def test_free_tpl_name_skips_taken_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(rect.free_tpl_name(tmp), "00a")
            (Path(tmp) / "00a").write_bytes(b"")
            self.assertEqual(rect.free_tpl_name(tmp), "00b")


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class RealRectTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.environ["FE9_EXTRACTED_FILES"])
        self.data = (self.root / "s" / "rect.bin").read_bytes()

    def test_vanilla_file_rebuilds_byte_for_byte(self):
        doc = rect.parse_rect(self.data)
        self.assertEqual(doc.build(), self.data)
        self.assertEqual((len(doc.resources), sum(len(r.layers) for r in doc.resources)), (195, 316))

    def test_known_resources(self):
        doc = rect.parse_rect(self.data)
        night = doc.find("RID_アジト-作戦室-夜")
        self.assertEqual((len(night.layers), night.mode, night.depth, night.brightness), (4, 2, 900, 184))
        self.assertAlmostEqual(night.duration, 1.85, places=5)
        self.assertEqual([l.texture for l in night.layers], [0, 1, 2, 3])
        self.assertEqual(doc.find("RID_タイトル炎_JP").effect, rect.EFFECT_NONE)
        self.assertEqual(doc.find("RID_砂漠").effect, rect.EFFECT_SAND)
        self.assertEqual(doc.find("RID_山裾-雪").effect, rect.EFFECT_SNOW)

    def test_every_layer_source_matches_its_texture(self):
        doc = rect.parse_rect(self.data)

        def sizes(path):
            target = self.root / path
            return [(i.width, i.height) for i in tpl.read_tpl_image_info_path(target)] if target.is_file() else None

        # One vanilla layer (RID_地図ドラゴン13) asks for 432 rows of a 430-row texture.
        self.assertEqual(len(rect.validate(doc, sizes)), 1)

    def test_compat_reader_sees_every_resource(self):
        entries = rect.read_rects_path(self.root / "s" / "rect.bin")
        self.assertEqual(len(entries), 195)
        self.assertEqual(entries[0].resource_id, "RID_アジト-作戦室".encode("shift_jis"))


if __name__ == "__main__":
    unittest.main()
