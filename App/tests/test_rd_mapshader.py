"""Radiant Dawn's mapshader: the record RFEE01's loader at 0x801369BC reads, and its patcher."""

import os
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import map_file

FE10 = os.environ.get("FE10_EXTRACTED_FILES")


class LayoutTests(unittest.TestCase):
    def test_fields_follow_the_loader(self):
        offsets = {name: offset for name, (offset, _fmt, _since) in map_file.RD_SHADER_FIELDS.items()}
        self.assertEqual((offsets["water"], offsets["tint"], offsets["tint_red"], offsets["hundredths_5c"]),
                         (3, 8, 10, 6))
        since = {name: version for name, (_offset, _fmt, version) in map_file.RD_SHADER_FIELDS.items()}
        self.assertEqual((since["value_60"], since["object"], since["tint"]), (1, 2, 0))


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdTests(unittest.TestCase):
    @staticmethod
    def _map(name):
        from fe_modding import map_props
        _entries, files = map_props.read_map_container(Path(FE10) / "zmap" / name / "map.cmp")
        return files["map.bin"]

    def test_every_retail_record(self):
        versions = Counter()
        for folder in sorted((Path(FE10) / "zmap").glob("bmap*")):
            if not (folder / "map.cmp").is_file():
                continue
            shader = map_file.read_map_bytes(self._map(folder.name)).shader
            if shader is None:
                continue
            versions[shader.version] += 1
            self.assertEqual(shader.tint, 0)  # no retail map uses the ground tint pass
            self.assertIn(shader.water, (0, 1))
            if shader.version < 2:
                self.assertIsNone(shader.get("object"))
        from tests.corpus import per_disc
        # the Japanese maps mostly have the older version 1 record
        self.assertEqual(versions, per_disc(FE10, Counter({2: 31, 1: 12}), jp=Counter({1: 26, 2: 17})))

    def test_patch_keeps_every_other_byte(self):
        from tests.corpus import per_disc
        data = self._map(per_disc(FE10, "bmap0109", jp="bmap0303"))      # bmap0109 is version 1 on JP
        shader = map_file.read_map_bytes(data).shader
        self.assertEqual((shader.version, shader.water, shader.value_60, shader.value_54),
                         per_disc(FE10, (2, 1, 3, 255), jp=(2, 1, 0, 255)))
        out = map_file.patch_shader_field(data, shader, "tint", 1)
        out = map_file.patch_shader_field(out, map_file.read_map_bytes(out).shader, "hundredths_5c", -60)
        after = map_file.read_map_bytes(out).shader
        self.assertEqual((after.tint, after.hundredths_5c), (1, -60))
        # tint, and the bytes of -60 (ffc4) the old value did not share (bmap0303 already had ff)
        self.assertEqual(sum(a != b for a, b in zip(out, data)), per_disc(FE10, 3, jp=2))
        with self.assertRaises(map_file.MapFileError):
            map_file.patch_shader_field(data, shader, "water", 256)
        version1 = map_file.read_map_bytes(self._map("bmap0111")).shader
        with self.assertRaises(map_file.MapFileError):
            map_file.patch_shader_field(self._map("bmap0111"), version1, "object", 1)


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class FormTests(unittest.TestCase):
    def test_map_settings_edits_the_shader_and_keeps_rd_half_sizes(self):
        import tkinter as tk
        from types import SimpleNamespace
        from fe_modding import map_props
        from fe_modding.gui.map_windows import MapSettingsForm
        _entries, files = map_props.read_map_container(Path(FE10) / "zmap" / "bmap0109" / "map.cmp")
        state = {"map.bin": files["map.bin"]}
        editor = SimpleNamespace(map_data=map_file.read_map_bytes(files["map.bin"]), verified_us_map_layout=False,
                                 add_listener=lambda f: None, remove_listener=lambda f: None,
                                 water_names=lambda: [], water_flow=lambda *a: None, import_water=lambda *a: None)
        labels = []

        def edit_map(fn, label, *a, **k):
            fn(state)
            editor.map_data = map_file.read_map_bytes(state["map.bin"])
            labels.append(label)

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        self.addCleanup(root.destroy)
        builder = SimpleNamespace(map_editor=editor, edit_map=edit_map, project=None, changelog=None,
                                  run_undoable=lambda action: action())
        form = MapSettingsForm(root, builder)
        self.assertIn("shader:water", form._vars)
        form._vars["shader:tint"].set(True)
        form._vars["shader:tint_green"].set("0")
        form._apply()
        after = map_file.read_map_bytes(state["map.bin"])
        self.assertEqual((after.shader.tint, after.shader.tint_green), (1, 0))
        # Radiant Dawn's half sizes are floor(size / 2): Apply must not round them up (1-9 is odd-sized)
        self.assertEqual((after.extra.half_x_size, after.extra.half_y_size),
                         (after.capacity.x_size // 2, after.capacity.y_size // 2))
        self.assertNotIn("half", labels[-1])


if __name__ == "__main__":
    unittest.main()
