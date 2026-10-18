import unittest
from pathlib import Path

from fe_modding.formats.extended_flags import FlagLayout
from fe_modding.game_code.dol import Dol, DolError
from fe_modding.game_code.extended_flag_runtime import build_core
from fe_modding.game_code.extended_flag_load import build_card_open_fragment
from fe_modding.game_code.extended_flag_container import container_name, build_container_fragment, FILENAMES

RETAIL = Path(__file__).resolve().parents[2] / "research/main_dol/dols"


class ContainerTests(unittest.TestCase):
    def test_name_stability_and_input_validation(self):
        identity = bytes.fromhex("0123456789abcdef0123456789abcdef")
        first = container_name(identity)
        self.assertEqual(first, container_name(identity))
        self.assertRegex(first, r"^X[A-Z2-7]{9}$")
        self.assertNotEqual(first, container_name(bytes.fromhex("1123456789abcdef0123456789abcdef")))
        for bad in (b"", bytes(16), bytes(17), "not bytes"):
            with self.assertRaises(ValueError):
                container_name(bad)

    def test_regional_filename_edits_are_bounded_and_leave_retail_input_untouched(self):
        layout = FlagLayout()
        expected = container_name(bytes.fromhex(layout.identity))
        for region, (at, original) in FILENAMES.items():
            if not (RETAIL / f"{region}.dol").exists():
                self.skipTest("retail DOL unavailable")
            dol = Dol.open(RETAIL / f"{region}.dol")
            before = bytes(dol.data)
            core = build_core(dol, region, layout)
            with self.assertRaisesRegex(ValueError, "validation"):
                build_container_fragment(dol, region, core)
            guarded = build_card_open_fragment(dol, region, core)
            image = build_container_fragment(dol, region, guarded)
            edit = image.edits[-1]
            self.assertEqual(edit.address, at)
            self.assertEqual(edit.original, original)
            self.assertEqual(len(edit.patched), len(original))
            self.assertEqual(edit.patched.split(b"\0")[0].decode("ascii"), expected)
            self.assertEqual(bytes(dol.data), before)
            with self.assertRaises(ValueError):
                build_container_fragment(dol, region, image)
            dol.write(at, b"!")
            with self.assertRaises(DolError):
                build_container_fragment(dol, region, guarded)


if __name__ == "__main__":
    unittest.main()
