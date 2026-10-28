import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fe_modding import colour_variants, model_slots, portraits
from fe_modding.exceptions import ProjectError
from fe_modding.formats import anim_registry, fe8data, lz10, pak, tpl, zdbx
from fe_modding.formats.fe9_portraits import FaceRecord, build_face_cms, build_face_table
from fe_modding.games import Game
from fe_modding.project import ModProject
from fe_modding.recolour import Recolour, recolour_tpl
from test_model_slots import _fe8data_with_header, _record

RED, GREY, BLUE = (200, 30, 30, 255), (128, 128, 128, 255), (30, 30, 200, 255)
TO_BLUE = Recolour(hue=0, band=20, shift=240)


def _picture(size=(32, 32)) -> Image.Image:
    """Left half red, right half grey, top-left 4x4 transparent."""
    image = Image.new("RGBA", size, GREY)
    image.paste(Image.new("RGBA", (size[0] // 2, size[1]), RED), (0, 0))
    image.paste(Image.new("RGBA", (4, 4), (0, 0, 0, 0)), (0, 0))
    return image


def _cmpr() -> bytes:
    return tpl.build_tpl([(_picture(), tpl.FORMAT_CMPR)])


def _pixels(tpl_bytes: bytes, index: int = 0) -> np.ndarray:
    return np.array(tpl.read_tpl_images(io.BytesIO(tpl_bytes))[index].convert("RGBA"), dtype=int)


class RecolourTests(unittest.TestCase):
    def test_band_and_greys(self):
        out = TO_BLUE.apply(np.array([RED, GREY, (30, 200, 30, 255), (200, 30, 30, 7)], dtype=np.uint8))
        self.assertGreater(out[0, 2], 150)
        self.assertLess(out[0, 0], 60)
        self.assertEqual(tuple(out[1]), GREY)  # grey: no hue to match
        self.assertEqual(tuple(out[2]), (30, 200, 30, 255))  # green: outside the band
        self.assertEqual(out[3, 3], 7)  # alpha kept

    def test_between_takes_source_to_target(self):
        recolour = Recolour.between(RED[:3], BLUE[:3])
        out = recolour.apply(np.array([RED], dtype=np.uint8))[0]
        self.assertLess(np.abs(out[:3].astype(int) - np.array(BLUE[:3])).max(), 3)
        self.assertTrue(Recolour().is_identity)


class MapColoursTests(unittest.TestCase):
    def test_identity_is_byte_exact(self):
        rgb5a3 = tpl.build_tpl([(_picture(), tpl.FORMAT_RGB5A3)])
        face, _flags = build_face_cms(_picture((192, 128)), None, None, _picture((64, 64)))
        for data in (_cmpr(), rgb5a3, face):
            self.assertEqual(tpl.map_colours(data, lambda colours: colours), data)

    def test_cmpr_keeps_indices_and_transparency(self):
        source = _cmpr()
        out = recolour_tpl(source, TO_BLUE)
        self.assertEqual(len(out), len(source))
        before, after = _pixels(source), _pixels(out)
        self.assertTrue(np.array_equal(before[..., 3], after[..., 3]))
        self.assertGreater(after[16, 4, 2], 150)  # red half turned blue
        self.assertTrue(np.array_equal(before[:, 24:], after[:, 24:]))  # grey half untouched

    def test_palette_recolours_every_image_sharing_it(self):
        face, _flags = build_face_cms(_picture((192, 128)), None, None, _picture((64, 64)))
        out = recolour_tpl(face, TO_BLUE)
        for index in (0, 1):
            pixels = _pixels(out, index)
            self.assertGreater(pixels[pixels.shape[0] // 2, 10, 2], 150)
        # only the palette changed: the index bytes of the body are the same
        info = tpl.read_tpl_image_info(io.BytesIO(face))[0]
        span = slice(info.data_addr, info.data_addr + info.data_length)
        self.assertEqual(out[span], face[span])


class VariantProjectTests(unittest.TestCase):
    """PID_TEST owns AID_TESTMODEL (with its event copy PID_TEST_EV); the
    class's AID_CLASSMODEL is shared with the class."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "Variants", Game.PATH_OF_RADIANCE)
        files = self.files = self.project.extracted_dir / "files"
        data = _fe8data_with_header()
        data = fe8data.add_label(data, "AID_CLASSMODEL")
        data = fe8data.patch_class_field(data, 0, "aid", "AID_CLASSMODEL")
        data = fe8data.patch_character_field(data, 0, "mpid", "MPID_TEST")
        data = fe8data.patch_character_field(data, 1, "pid", "PID_TEST_EV")
        for field, value in (("mpid", "MPID_TEST"), ("fid", "FID_TEST"), ("jid", "JID_TESTCLASS"),
                             ("aid_unpromoted", "AID_TESTMODEL")):
            data = fe8data.patch_character_field(data, 1, field, value)
        files.mkdir(parents=True, exist_ok=True)
        (files / "FE8Data.bin").write_bytes(data)

        job_list = ("#\r\n{\r\n\t\tclass JobList\r\n\t\tJID_TESTCLASS\t\ttst1\r\n"
                    "\t\tAID_CLASSMODEL\t\ttst1\r\n}\r\n")
        model = "{\r\n\tclass\tModel\r\n\tname\ttst1\r\n\tfolder\tzu/tst1\r\n\tmodel\ttst1\r\n}\r\n"
        param = "{\r\n\tclass\tParam\r\n\tname\ttst1\r\n\ttexnum\t2\r\n\t自軍\ttst1\r\n\t敵軍\ttst1_1\r\n}\r\n"
        tables = [(zdbx.JOB_LIST, job_list), ("zu/tst1.dbx", model), ("zu/tst1_prm.dbx", param)]
        (files / "zdbx.cmp").write_bytes(zdbx.build_zdbx_archive([(n, zdbx.encode_dbx(t)) for n, t in tables]))
        (files / "zu" / "tst1").mkdir(parents=True)
        for name in ("tst1", "tst1_1"):
            (files / "zu" / "tst1" / f"{name}.tpl").write_bytes(_cmpr())

        records = [_record("AID_TESTMODEL_N", "testmap/", textures=(4, 4, 4, 4)),
                   _record("AID_CLASSMODEL_N", "classmap/", textures=(32, 97, 162, 227)),
                   _record("AID_CLASSMODEL_SW", "classmap/", weapon=1, textures=(32, 97, 162, 227))]
        (files / "FE8Anim.bin").write_bytes(anim_registry.build_anim_registry(records))
        (files / "ymu" / "testmap").mkdir(parents=True)
        (files / "ymu" / "testmap" / "pack.cmp").write_bytes(
            lz10.compress(pak.pack_pak([("body.gs", b"gs"), ("tex_4.tpl", _cmpr())])))
        (files / "ymu" / "classmap").mkdir(parents=True)
        for number in (32, 97, 162, 227):
            (files / "ymu" / "classmap" / f"tex_{number}.tpl").write_bytes(_cmpr())

        face = portraits.face_dir(self.project)
        face.mkdir(parents=True)
        small, _ = build_face_cms(_picture((192, 128)), None, None, _picture((64, 64)))
        large, _ = build_face_cms(_picture((288, 192)), None, None, None)
        (face / "TEST.cms").write_bytes(lz10.compress(small))
        (face / "L_TEST.cms").write_bytes(lz10.compress(large))
        records = [FaceRecord("FID_TEST", "MPID_TEST", "TEST.cms", (-1, -1), (-1, -1), (-1, -1), 0, 1, 0, 0, 0),
                   FaceRecord("FID_L_TEST", "MPID_TEST", "L_TEST.cms", (-1, -1), (-1, -1), (-1, -1), 0, 0xFFFF,
                              0, 0, 0)]
        (face / "facedata.bin").write_bytes(build_face_table(records))

    def _characters(self):
        return {c.pid: c for c in fe8data.read_fe8data((self.files / "FE8Data.bin").read_bytes()).characters
                if c.pid}

    def test_family_suggests_the_event_copy(self):
        self.assertEqual(colour_variants.character_family(self.project, "PID_TEST"), (["PID_TEST_EV"], []))

    def test_character_with_its_own_animation_id(self):
        plan = colour_variants.plan_character_variant(self.project, "PID_TEST", "red", also=["PID_TEST_EV"])
        self.assertEqual(plan.map_clones, [])
        self.assertEqual(plan.map_textures, [("AID_TESTMODEL", (1, 1, 1, 1))])
        self.assertEqual(plan.battle_lines, [("tst1", "PID_TEST", "tst1_red"), ("tst1", "PID_TEST_EV", "tst1_red")])
        colour_variants.apply_variant(self.project, plan, TO_BLUE)

        new_map = self.files / "ymu" / "testmap" / "tex_1.tpl"
        self.assertGreater(_pixels(new_map.read_bytes())[16, 4, 2], 150)  # copied out of pack.cmp, recoloured
        self.assertEqual(model_slots.battle_textures(self.project, "tst1")["PID_TEST_EV"], "tst1_red")
        self.assertGreater(_pixels((self.files / "zu" / "tst1" / "tst1_red.tpl").read_bytes())[16, 4, 2], 150)
        self.assertGreater(_pixels((self.files / "zu" / "tst1" / "tst1.tpl").read_bytes())[16, 4, 0], 150)
        records = model_slots.map_model_records(self.project)
        self.assertEqual(next(r for r in records if r.base_aid == "AID_TESTMODEL").texture_ids, (1, 1, 1, 1))
        faces = {r.fid: r.filename for r in portraits.load_faces(self.project)}
        self.assertEqual((faces["FID_TEST_RED"], faces["FID_L_TEST_RED"]), ("TEST_RED.cms", "L_TEST_RED.cms"))
        characters = self._characters()
        self.assertEqual({characters[p].fid for p in ("PID_TEST", "PID_TEST_EV")}, {"FID_TEST_RED"})
        body = _pixels(lz10.decompress((portraits.face_dir(self.project) / "TEST_RED.cms").read_bytes()))
        self.assertGreater(body[64, 40, 2], 150)

    def test_existing_file_refuses_the_tag(self):
        (self.files / "zu" / "tst1" / "tst1_red.tpl").write_bytes(b"taken")
        with self.assertRaises(ProjectError):
            colour_variants.plan_character_variant(self.project, "PID_TEST", "RED")

    def test_character_sharing_its_class_animation_id(self):
        plan = colour_variants.plan_character_variant(self.project, "PID_TEST_EV", "BLUE", battle=True,
                                                      map_models=False, portrait=False)
        # the event copy shares AID_TESTMODEL with PID_TEST, which is not in the group: no map change,
        # and the battle texture is picked by PID (zu/tst1 has no line for the AID)
        self.assertEqual(plan.battle_lines, [("tst1", "PID_TEST_EV", "tst1_blue")])

        data = fe8data.patch_character_field((self.files / "FE8Data.bin").read_bytes(), 1, "aid_unpromoted", None)
        (self.files / "FE8Data.bin").write_bytes(data)
        plan = colour_variants.plan_character_variant(self.project, "PID_TEST_EV", "BLUE", portrait=False)
        self.assertEqual([c[:2] for c in plan.map_clones], [("AID_CLASSMODEL", "AID_CLASSMODEL_BLUE")])
        self.assertEqual(plan.job_lines, [("tst1", "AID_CLASSMODEL_BLUE")])
        colour_variants.apply_variant(self.project, plan, TO_BLUE)
        self.assertEqual(self._characters()["PID_TEST_EV"].aid_unpromoted, "AID_CLASSMODEL_BLUE")
        self.assertIsNone(self._characters()["PID_TEST"].aid_promoted)
        clones = [r for r in model_slots.map_model_records(self.project) if r.base_aid == "AID_CLASSMODEL_BLUE"]
        self.assertEqual(len(clones), 2)
        self.assertEqual({r.class_folder for r in clones}, {"classmap/"})
        self.assertEqual(len({*clones[0].texture_ids} & {32, 97, 162, 227}), 0)
        self.assertIn(("AID_CLASSMODEL_BLUE", "tst1", ""), model_slots.job_list(self.project))

    def test_class_army_colours(self):
        plan = colour_variants.plan_class_variant(self.project, "JID_TESTCLASS", "敵軍", "BLUE")
        self.assertEqual(plan.battle_lines, [("tst1", "敵軍", "tst1_1_blue")])
        self.assertEqual(plan.map_textures, [("AID_CLASSMODEL", (32, 1, 162, 227))])
        colour_variants.apply_variant(self.project, plan, TO_BLUE)
        self.assertEqual(model_slots.battle_textures(self.project, "tst1")["敵軍"], "tst1_1_blue")
        self.assertEqual(model_slots.battle_textures(self.project, "tst1")["自軍"], "tst1")
        self.assertTrue((self.files / "ymu" / "classmap" / "tex_1.tpl").is_file())

    def test_bad_tag(self):
        for tag in ("", "1RED", "TOOLONGTAG", "SW", "RE D"):
            with self.assertRaises(ProjectError, msg=tag):
                colour_variants.plan_class_variant(self.project, "JID_TESTCLASS", "敵軍", tag)


if __name__ == "__main__":
    unittest.main()
