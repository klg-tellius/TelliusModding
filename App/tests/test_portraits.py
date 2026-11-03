import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import portraits
from fe_modding.formats import lz10, tpl
from fe_modding.formats.fe9_portraits import (FaceRecord, build_face_cms, build_face_table, large_face_id,
                                              read_face_table)


def _record(fid, filename, flags=0, mini=0xFFFF):
    return FaceRecord(fid, "MPID_" + fid[4:], filename, (-1, -1), (-1, -1), (-1, -1), flags, mini, 0, 0, 0)


def _picture(size, colour):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.paste(Image.new("RGBA", (size[0] // 2, size[1] // 2), colour), (size[0] // 4, size[1] // 4))
    return image


class FaceTableTests(unittest.TestCase):
    def test_round_trip(self):
        records = [_record("FID_B", "B.cms"), _record("FID_A", "A.cms", 3, 13), _record("FID_L_A", "L_A.cms")]
        data = build_face_table(records)
        self.assertEqual(list(read_face_table(data).values()), records)

    def test_duplicate_refused(self):
        with self.assertRaises(ValueError):
            build_face_table([_record("FID_A", "A.cms"), _record("FID_A", "B.cms")])

    def test_large_id(self):
        self.assertEqual(large_face_id("FID_IKE"), "FID_L_IKE")


class FaceTextureTests(unittest.TestCase):
    def test_new_set_keeps_colours_and_layout(self):
        body = _picture((192, 128), (200, 30, 40, 255))
        mouths = [_picture((24, 24), (10, 200, 10, 255))] * 6
        eyes = [_picture((16, 16), (10, 10, 220, 255))] * 6
        menu = _picture((64, 64), (240, 240, 0, 255))
        data, flags = build_face_cms(body, mouths, eyes, menu)
        self.assertEqual(flags, 3)
        infos = tpl.read_tpl_image_info(io.BytesIO(data))
        self.assertEqual(len(infos), 14)
        self.assertTrue(all(i.format == tpl.FORMAT_C8 for i in infos))
        back = tpl.read_tpl_images(io.BytesIO(data))
        for source, decoded in ((body, back[0]), (menu, back[13])):
            a, b = np.array(source, dtype=int), np.array(decoded, dtype=int)
            self.assertTrue(np.array_equal(a[..., 3] > 0, b[..., 3] > 0))
            visible = a[..., 3] > 0
            self.assertLess(np.abs(a[visible][:, :3] - b[visible][:, :3]).max(), 9)

    def test_new_palette_rebuild(self):
        body = _picture((192, 128), (200, 30, 40, 255))
        data, _ = build_face_cms(body, None, None, _picture((64, 64), (0, 0, 255, 255)))
        rebuilt = portraits.rebuild_with_new_palette(data, {0: _picture((96, 64), (20, 220, 90, 255))})
        back = tpl.read_tpl_images(io.BytesIO(rebuilt))
        self.assertEqual(back[0].size, (192, 128))
        self.assertLess(abs(back[0].getpixel((96, 64))[1] - 220), 9)
        self.assertLess(abs(back[1].getpixel((32, 32))[2] - 255), 9)


class AddPortraitTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.games import Game
        from fe_modding.project import ModProject
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "faces", Game.PATH_OF_RADIANCE)
        face = portraits.face_dir(self.project)
        face.mkdir(parents=True)
        source = os.environ.get("FE9_EXTRACTED_FILES")
        if source:
            shutil.copy(Path(source) / "Face" / "facedata.bin", face / "facedata.bin")
        else:
            (face / "facedata.bin").write_bytes(build_face_table([_record("FID_IKE", "IKE.cms")]))

    def test_add_and_remove(self):
        before = portraits.load_faces(self.project)
        small, large = portraits.add_portrait(self.project, "hero", "MPID_HERO", _picture((300, 200), (90, 90, 90, 255)))
        self.assertEqual((small, large), ("FID_HERO", "FID_L_HERO"))
        faces = {r.fid: r for r in portraits.load_faces(self.project)}
        self.assertEqual(faces["FID_HERO"].filename, "HERO.cms")
        self.assertEqual(faces["FID_HERO"].mini_portrait, 1)
        self.assertEqual(faces["FID_L_HERO"].mini_portrait, 0xFFFF)
        images = tpl.read_tpl_images(io.BytesIO(lz10.decompress(
            (portraits.face_dir(self.project) / "HERO.cms").read_bytes())))
        self.assertEqual([i.size for i in images], [(192, 128), (64, 64)])
        with self.assertRaises(ValueError):
            portraits.add_portrait(self.project, "HERO", "MPID_HERO", _picture((10, 10), (0, 0, 0, 255)))
        self.assertEqual(portraits.remove_portrait(self.project, "FID_HERO"), ["FID_HERO", "FID_L_HERO"])
        self.assertEqual(portraits.load_faces(self.project), before)
        self.assertFalse((portraits.face_dir(self.project) / "HERO.cms").exists())

    def test_parts_need_positions(self):
        with self.assertRaises(ValueError):
            portraits.add_portrait(self.project, "HERO", "MPID_HERO", _picture((192, 128), (1, 2, 3, 255)),
                                   small_eyes=[_picture((16, 16), (0, 0, 0, 255))] * 6)


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class RetailFaceTableTests(unittest.TestCase):
    def test_byte_identical_rebuild(self):
        data = (Path(os.environ["FE9_EXTRACTED_FILES"]) / "Face" / "facedata.bin").read_bytes()
        self.assertEqual(build_face_table(list(read_face_table(data).values())), data)


if __name__ == "__main__":
    unittest.main()
