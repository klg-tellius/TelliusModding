"""Phases 5-6 of the PoR/RD parity plan: Radiant Dawn Excel sheets, one Supports tab model per game,
filter chips and the shared Game Data tiles."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import excel_io
from fe_modding.game_adapter import PorDataAdapter, RdDataAdapter
from fe_modding.supports_model import PorSupports, RdSupports, SupportsModel

FE9 = os.environ.get("FE9_EXTRACTED_FILES")
FE10 = os.environ.get("FE10_EXTRACTED_FILES")


class LayoutTests(unittest.TestCase):
    def test_adapters_pick_their_supports_model(self):
        self.assertIs(PorDataAdapter.supports_model, PorSupports)
        self.assertIs(RdDataAdapter.supports_model, RdSupports)
        for model in (PorSupports, RdSupports):
            self.assertTrue(issubclass(model, SupportsModel))
            self.assertEqual(len(model.pair_fields) > 0, True)
        self.assertTrue(PorSupports.can_add_partners)
        self.assertFalse(RdSupports.can_add_partners)  # every supporter lists all the others
        self.assertEqual(PorSupports.conversation_ranks, ("C", "B", "A"))
        self.assertEqual(RdSupports.conversation_ranks, ())

    def test_shared_hub_order(self):
        from fe_modding.gui.pages import data
        por = data.SECTIONS[0][1]
        rd = data.FE10_DATA_TILES
        shared = [key for key in rd if key in por]
        self.assertEqual(shared, [key for key in por if key in rd])  # the same order where both have a tile
        self.assertIn("battle_scenery", por)
        self.assertEqual(data.FE10_GROUPS["supports"][0], "supports")

    def test_character_page_holds_no_supports_game_check(self):
        source = (Path(__file__).resolve().parents[1] / "fe_modding" / "gui" / "pages" / "characters.py").read_text(
            encoding="utf-8")
        for check in ("SUPPORT_LIST", "Fe10CharacterSupportsPanel"):
            self.assertNotIn(check, source)


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdCorpusTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.formats import fe10data, lz10
        self.fe10data = fe10data
        self.data = lz10.decompress((Path(FE10) / "FE10Data.cms").read_bytes())
        self.adapter = RdDataAdapter(SimpleNamespace(data=self.data, fe10=fe10data.read_fe10data(self.data)))

    def test_every_sheet_round_trips_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kind in excel_io.FE10_SHEETS:
                path = Path(tmp) / f"{kind}.xlsx"
                self.adapter.export_excel(path, kind)
                data, errors = self.adapter.import_excel(path, kind)
                self.assertEqual(errors, [], kind)
                self.assertEqual(data, self.data, kind)

    def test_an_edited_cell_and_list_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "characters.xlsx"
            self.adapter.export_excel(path, "character")
            rows = excel_io.read_workbook(path)["Characters"]
            header = rows[0]
            rows[2][header.index("growth_hp")] = 77
            rows[2][header.index("skills")] = "SID_BOSS, SID_CANTO"
            excel_io.write_workbook(path, {"Characters": rows})
            data, errors = self.adapter.import_excel(path, "character")
        self.assertEqual(errors, [])
        record = self.fe10data.read_table(data, "character")[rows[2][0]]
        self.assertEqual((record.values["growth_hp"], record.lists["skills"]), (77, ["SID_BOSS", "SID_CANTO"]))

    def test_a_row_naming_another_record_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "characters.xlsx"
            self.adapter.export_excel(path, "character")
            rows = excel_io.read_workbook(path)["Characters"]
            rows[2][rows[0].index("pid")] = "PID_SOMEONE"
            excel_io.write_workbook(path, {"Characters": rows})
            data, errors = self.adapter.import_excel(path, "character")
        self.assertEqual(data, self.data)
        self.assertIn("not PID_SOMEONE", errors[0])

    def test_chips(self):
        classes, order = self.adapter.categories("class")
        self.assertEqual(order, ["First tier", "Second tier", "Third tier", "Laguz"])
        by_id = dict(zip((r.id for r in self.fe10data.read_table(self.data, "class")), classes))
        self.assertEqual(by_id["JID_SWORDMASTER_SP"], "Third tier")
        self.assertEqual(by_id["JID_LION"], "Laguz")
        items, _order = self.adapter.categories("item")
        self.assertEqual(dict(zip((r.id for r in self.fe10data.read_table(self.data, "item")), items))["IID_STEELSWORD"],
                         "Sword")
        self.assertIsNone(self.adapter.categories("skill"))

    def test_supports(self):
        model = RdSupports(self.data)
        data = model.set_pair(self.data, "PID_IKE", "PID_MIST", ["0", "3"])
        self.assertEqual(RdSupports(data).pair_values("PID_IKE", "PID_MIST"), ("0", "3"))
        self.assertEqual(RdSupports(data).pair_values("PID_MIST", "PID_IKE"),
                         model.pair_values("PID_MIST", "PID_IKE"))  # each character's list is its own
        bonds = model.bonds("PID_IKE")
        data = model.add_bond(self.data, "PID_IKE", "PID_SOTHE")
        self.assertEqual(len(RdSupports(data).bonds("PID_IKE")), len(bonds) + 1)
        with self.assertRaisesRegex(ValueError, "already exists"):
            model.add_bond(self.data, "PID_IKE", bonds[0].other)
        data = model.set_affinity(self.data, "PID_IKE", "fire")
        self.assertEqual(RdSupports(data).affinity_of("PID_IKE"), "fire")
        with self.assertRaises(ValueError):
            model.add_partner(self.data, "PID_IKE", "PID_MIST")


@unittest.skipUnless(FE9, "set FE9_EXTRACTED_FILES to an extracted Path of Radiance files/ directory")
class PorCorpusTests(unittest.TestCase):
    def test_supports_model_reads_and_writes_like_the_panel_did(self):
        data = (Path(FE9) / "FE8Data.bin").read_bytes()
        model = PorSupports(data)
        rows = [r for r in model.partners("PID_IKE") if r.partner]
        partner = rows[0].partner
        data2 = model.set_pair(data, "PID_IKE", partner, ["2", "4", "6"])
        self.assertEqual(PorSupports(data2).pair_values("PID_IKE", partner), ("2", "4", "6"))
        self.assertEqual(PorSupports(data2).pair_values(partner, "PID_IKE"), ("2", "4", "6"))  # both lists
        with self.assertRaisesRegex(ValueError, "rise"):
            model.set_pair(data, "PID_IKE", partner, ["5", "4", "6"])
        self.assertEqual(model.affinity_of("PID_IKE"), "Earth")


if __name__ == "__main__":
    unittest.main()
