"""What the Build tab says a deployment section is for, from the retail section names."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from fe_modding.gui.map_builder import MapBuilder
except ImportError:  # no Tkinter
    MapBuilder = None


@unittest.skipIf(MapBuilder is None, "needs Tkinter")
class SectionRoles(unittest.TestCase):
    def test_roles_from_retail_names(self):
        role = MapBuilder._section_role
        self.assertEqual(role("bmap06_mikata_n", None), ", player army")
        self.assertEqual(role("bmap06_first_n", None), ", battle start")
        self.assertEqual(role("bmap06_zoen_h", None), ", reinforcements")
        self.assertEqual(role("bmap07_dispos_z01_h", None), ", reinforcements")
        self.assertEqual(role("bmap06_event01_c", None), ", event scene only, not in the battle")
        self.assertEqual(role("bmap05_first_boss_n", None), ", boss")

    def test_sections_the_script_never_names(self):
        deployed = {"bmap06_first", "bmap06_mikata_c"}  # scripts name the n/h/m trio by its base
        self.assertEqual(MapBuilder._section_role("bmap06_first_h", deployed), ", battle start")
        self.assertEqual(MapBuilder._section_role("bmap06_mikata_c", deployed), ", player army")
        self.assertEqual(MapBuilder._section_role("bmap06_extra_n", deployed), ", not deployed by the script")


if __name__ == "__main__":
    unittest.main()
