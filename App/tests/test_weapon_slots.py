"""New weapons (``weapon_slots``): model slots, the one-go weapon, effect safety and effect
recolouring, on synthetic files (no disc needed)."""

import io
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fe_modding import recolour, weapon_slots  # noqa: E402
from fe_modding.exceptions import ProjectError  # noqa: E402
from fe_modding.formats import (battle_weapons as bw, effects, fe8data, fe10_battle, fe10_battle_weapons as fw,  # noqa: E402
                                lz10, message, pak, tpl, zdbx)
from fe_modding.games import Game  # noqa: E402
from fe_modding.project import ModProject  # noqa: E402
from synthetic_data import fe10_battle_file  # noqa: E402
from test_item_rules import _complete_fixture as _fe8data  # noqa: E402


def _texture(colour=(255, 200, 40, 255)) -> bytes:
    return tpl.build_tpl([(Image.new("RGBA", (8, 8), colour), tpl.FORMAT_RGB5A3)])


def _effect(name: str, anim: bytes, colour=(255, 200, 40, 255)) -> bytes:
    return effects.build_effect_pack({f"{name}.g": b"skel", f"{name}.ga": anim, f"{name}.gs": b"mesh",
                                      f"{name}.tpl": _texture(colour)})


class _PorFixture:
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "Weapons", Game.PATH_OF_RADIANCE)
        files = self.project.extracted_dir / "files"
        (files / "xwp" / "testitem").mkdir(parents=True)
        pack = pak.pack_pak([("testitem.g", b"g"), ("testitem.gs", b"gs"), ("testitem.tpl", b"t")])
        (files / "xwp" / "testitem" / "testitem.cmp").write_bytes(lz10.compress(pack))
        tables = [
            ("xwp/TESTITEM.dbx", bw.new_weapon_dbx("TESTITEM", kind=0, missile=0, model="testitem",
                                                  effect_id="EID_GALE")),
            ("xwp/HANDAXE.dbx", bw.new_weapon_dbx("HANDAXE", kind=7, missile=1, model="handaxe",
                                                 effect_id="EID_SPARK", damage_effect_id="EID_SPARK")),
        ]
        (files / "zdbx.cmp").write_bytes(zdbx.build_zdbx_archive([(n, zdbx.encode_dbx(t)) for n, t in tables]))
        (files / "yme").mkdir()
        (files / "yme" / "EID_GALE.cmp").write_bytes(_effect("EID_GALE", b"gale"))
        (files / "yme" / "EID_SPARK.cmp").write_bytes(_effect("EID_SPARK", b"spark"))
        (files / "Mess").mkdir()
        (files / "Mess" / "common.m").write_bytes(message.write_messages([message.Message("MIID_TESTITEM", "Test")]))
        (files / "FE8Data.bin").write_bytes(_fe8data())
        self.files = self.project.files_root


class PorWeaponTests(_PorFixture, unittest.TestCase):
    def test_clone_weapon_model_renames_pack_and_entries(self):
        written = weapon_slots.clone_weapon_model(self.project, "testitem", "saber")
        self.assertEqual([p.name for p in written], ["saber.cmp"])
        data = lz10.decompress((self.files / "xwp" / "saber" / "saber.cmp").read_bytes())
        self.assertEqual([e.name for e in pak.read_pak_entries(data)], ["saber.g", "saber.gs", "saber.tpl"])
        self.assertEqual(weapon_slots.weapon_models(self.project), ["saber", "testitem"])
        self.assertTrue(weapon_slots.is_added_model(self.project, "saber"))
        self.assertFalse(weapon_slots.is_added_model(self.project, "testitem"))
        with self.assertRaises(ProjectError):
            weapon_slots.clone_weapon_model(self.project, "testitem", "saber")
        with self.assertRaises(ProjectError):
            weapon_slots.clone_weapon_model(self.project, "testitem", "Bad Name")
        with self.assertRaises(ProjectError):
            weapon_slots.remove_weapon_model(self.project, "testitem")
        weapon_slots.remove_weapon_model(self.project, "saber")
        self.assertEqual(weapon_slots.weapon_models(self.project), ["testitem"])

    def test_effect_safety_follows_vanilla_use_and_clones(self):
        sword = (0, 0)
        self.assertEqual(weapon_slots.safe_effects(self.project, sword, "effect"), ["EID_GALE"])
        self.assertEqual(weapon_slots.effect_warnings(self.project, sword, {"effect": "EID_GALE"}), [])
        notes = weapon_slots.effect_warnings(self.project, sword, {"effect": "EID_SPARK", "target": "EID_SPARK"})
        self.assertEqual(len(notes), 2)
        self.assertIn("Thrown axe", notes[0])
        self.assertIn("EID_GALE", notes[0])
        self.assertIn("leave it empty", notes[1])
        # a recoloured clone of the gale keeps its skeleton and animation: it counts as the gale
        (self.files / "yme" / "EID_BLUE.cmp").write_bytes(_effect("EID_BLUE", b"gale", (40, 90, 255, 255)))
        self.assertEqual(weapon_slots.effect_origin(self.project, "EID_BLUE", ["EID_GALE"]), "EID_GALE")
        self.assertEqual(weapon_slots.effect_warnings(self.project, sword, {"effect": "EID_BLUE"}), [])

    def test_add_weapon_writes_item_model_table_and_texts(self):
        spec = weapon_slots.WeaponSpec("saber", "IID_TESTITEM", name="Lightsaber", description="A blade of light.",
                                       effects={"effect": "EID_SPARK"}, trail_colour=4)
        self.assertEqual(weapon_slots.weapon_templates(self.project, _fe8data()), ["IID_TESTITEM"])
        result = weapon_slots.add_weapon(self.project, _fe8data(), spec)

        self.assertEqual(result.model, "saber")
        self.assertEqual(len(result.warnings), 1)  # EID_SPARK is a thrown weapon's effect
        item = next(i for i in fe8data.read_fe8data(result.game_data).items if i.iid == "IID_SABER")
        self.assertEqual((item.miid, item.help_key, item.trail_color), ("MIID_SABER", "MH_I_SABER", 4))
        table = bw.read_weapon(dict(zdbx.read_zdbx_files((self.files / "zdbx.cmp").read_bytes()))
                               ["xwp/SABER.dbx"].decode("shift_jis"))
        self.assertEqual((table.model_folder, table.model, table.kind, table.missile, table.effect_id),
                         ("xwp/SABER", "saber", 0, 0, "EID_SPARK"))
        self.assertTrue((self.files / "xwp" / "saber" / "saber.cmp").is_file())
        texts = {m.speaker: m.text for m in message.read_messages_path(self.files / "Mess" / "common.m")}
        self.assertEqual((texts["MIID_SABER"], texts["MH_I_SABER"], texts["MIID_TESTITEM"]),
                         ("Lightsaber", "A blade of light.", "Test"))
        with self.assertRaises(ProjectError):
            weapon_slots.add_weapon(self.project, result.game_data, spec)

    def test_add_weapon_without_model_and_with_cleared_effect(self):
        spec = weapon_slots.WeaponSpec("PLAIN", "TESTITEM", model_from="", effects={"effect": ""})
        result = weapon_slots.add_weapon(self.project, _fe8data(), spec)
        self.assertIsNone(result.model)
        self.assertEqual(result.warnings, [])
        text = dict(zdbx.read_zdbx_files((self.files / "zdbx.cmp").read_bytes()))["xwp/PLAIN.dbx"].decode("shift_jis")
        table = bw.read_weapon(text)
        self.assertEqual((table.model_folder, table.effect_id), (None, None))


class PorWeaponPageTests(_PorFixture, unittest.TestCase):
    """The Battle Weapons page and its New weapon... dialog, driven without a person."""

    def setUp(self):
        super().setUp()
        import tkinter as tk
        from unittest import mock
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.mock = mock

    def test_new_weapon_dialog_and_effect_boxes(self):
        from fe_modding.gui import battle_weapons_viewer as page_module, weapon_wizard
        from fe_modding.gui.changelog import ChangeLog
        from fe_modding.gui.fe8_session import Fe8DataSession

        changelog = ChangeLog()
        session = Fe8DataSession(self.project, changelog)
        page = page_module.battle_weapons_panel(self.root, self.project, changelog, session)
        page._tree.selection_set("TESTITEM")
        page._show_selected()
        self.assertEqual(page._boxes["effectId"].cget("values")[1], "EID_GALE")
        self.assertIn("EID_GALE", page._detail.cget("text"))

        dialog = weapon_wizard.NewWeaponDialog(page, self.project, changelog, session, page._weapon_added)
        dialog._key.set("IID_SABER")
        dialog._item_name.set("Lightsaber")
        dialog._effects["effect"].set("EID_SPARK")
        self.assertIn("EID_SPARK", dialog._warning.cget("text"))
        dialog._effects["effect"].set("EID_GALE")
        self.assertEqual(dialog._warning.cget("text"), "")
        dialog._trail.set("4: Blue")
        with self.mock.patch.object(weapon_wizard.messagebox, "showwarning"):
            dialog._create()
        self.assertFalse(session.dirty)
        item = next(i for i in fe8data.read_fe8data((self.files / "FE8Data.bin").read_bytes()).items
                    if i.iid == "IID_SABER")
        self.assertEqual(item.trail_color, 4)
        self.assertIn("SABER", page._tables)
        self.assertEqual(page._selected(), "SABER")
        # an unsafe effect asks first; "no" leaves the table alone
        page._vars["effectId"].set("EID_SPARK")
        with self.mock.patch.object(page_module.messagebox, "askyesno", return_value=False) as asked:
            page._apply()
        self.assertTrue(asked.called)
        table = bw.read_weapon(dict(zdbx.read_zdbx_files((self.files / "zdbx.cmp").read_bytes()))
                               ["xwp/SABER.dbx"].decode("shift_jis"))
        self.assertEqual(table.effect_id, "EID_GALE")

    def test_recolour_dialog(self):
        from fe_modding.gui.effects_viewer import EffectRecolourDialog

        parts = effects.read_effect_pack((self.files / "yme" / "EID_GALE.cmp").read_bytes())
        dialog = EffectRecolourDialog(self.root, "EID_GALE", parts)
        dialog._hue.set(220)
        dialog._update()
        dialog._ok()
        new_parts, description = dialog.result
        self.assertIn("tinted", description)
        self.assertNotEqual(new_parts["EID_GALE.tpl"], parts["EID_GALE.tpl"])


class Fe10WeaponRowTests(unittest.TestCase):
    def test_add_and_remove_rows(self):
        data = fe10_battle_file()
        out, index = fw.add_weapon(data, 0, "SABER", model="saber", labels={"hit": None, "effect": "EID_GALE"})
        self.assertEqual(index, 2)
        rows = fw.read_weapons(out)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2].labels["key"], "SABER")
        self.assertEqual(rows[2].labels["model"], "saber")
        self.assertIsNone(rows[2].labels["hit"])
        self.assertEqual(rows[2].labels["effect"], "EID_GALE")
        self.assertEqual((rows[2].type, rows[2].labels["name"]), (rows[0].type, rows[0].labels["name"]))
        self.assertEqual(rows[0].labels, fw.read_weapons(data)[0].labels)
        # other tables are untouched
        before, after = fe10_battle.read_fe10_battle(data), fe10_battle.read_fe10_battle(out)
        self.assertEqual([r.strings for r in before.table("FE10BWeaponType").records],
                         [r.strings for r in after.table("FE10BWeaponType").records])
        with self.assertRaises(ValueError):
            fw.add_weapon(out, 0, "saber")
        with self.assertRaises(ValueError):
            fw.remove_weapon(out, 1, vanilla_rows=2)
        self.assertEqual(fw.read_weapons(fw.remove_weapon(out, 2, vanilla_rows=2)), fw.read_weapons(data))


class EffectRecolourTests(unittest.TestCase):
    def _colour(self, parts):
        image = tpl.read_tpl_images(io.BytesIO(parts["EID_X.tpl"]))[0].convert("RGBA")
        return image.getpixel((0, 0))

    def test_tint_and_shift(self):
        parts = effects.read_effect_pack(_effect("EID_X", b"a"))
        tinted, notes = recolour.recolour_effect_pack(parts, hue=220)
        self.assertEqual(notes, [])
        r, g, b, _a = self._colour(tinted)
        self.assertGreater(b, r)
        self.assertEqual(tinted["EID_X.ga"], parts["EID_X.ga"])
        shifted, _ = recolour.recolour_effect_pack(parts, shift=180)
        r, g, b, _a = self._colour(shifted)
        self.assertGreater(b, r)
        with self.assertRaises(ValueError):
            recolour.recolour_effect_pack(parts)

    def test_tint_keeps_white_core_and_skips_grey_textures(self):
        white = recolour.tint(np.array([[255, 255, 255, 255], [0, 0, 0, 0]], np.uint8), 0)
        self.assertEqual(white.tolist(), [[255, 255, 255, 255], [0, 0, 0, 0]])
        grey = {"EID_X.tpl": tpl.build_tpl([(Image.new("RGBA", (8, 8), (200, 200, 200, 255)), tpl.FORMAT_I8)])}
        out, notes = recolour.recolour_effect_pack(grey, hue=0)
        self.assertEqual(out, grey)
        self.assertIn("greyscale", notes[0])
        self.assertIn("no texture", recolour.recolour_effect_pack({"EID_X.g": b"g"}, hue=0)[1][0])


if __name__ == "__main__":
    unittest.main()
