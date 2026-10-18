from pathlib import Path
import tempfile
import unittest

from fe_modding import flag_excel, excel_io
from fe_modding.formats import event_flags as ef
from fe_modding.formats.extended_flags import FlagLayout, HUB_ALIASES


class ExtendedExcelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "flags.xlsx"
        self.layout = FlagLayout().add("custom", "chapter", 18)
        self.campaign = ef.global_flags_vanilla() + list(HUB_ALIASES)
        self.chapters = {"18": ["retail", "custom"]}
        flag_excel.export_flags(self.path, self.campaign, self.chapters, layout=self.layout)

    def test_round_trip_and_appended_extended_slot(self):
        layout, additions = flag_excel.plan_banked_import(self.path, self.campaign, self.chapters, self.layout)
        self.assertEqual(layout, self.layout)
        self.assertFalse(any(additions.values()))
        sheets = excel_io.read_workbook(self.path)
        sheets["Chapter Flags"].append(["18", 2, "another", "extended", None])
        excel_io.write_workbook(self.path, sheets)
        layout, additions = flag_excel.plan_banked_import(self.path, self.campaign, self.chapters, self.layout)
        self.assertEqual(layout.find("another", 18).slot, 1)
        self.assertEqual(additions["18"], ["another"])

    def test_changed_identity_bank_or_slot_and_overflow_rejected(self):
        original = excel_io.read_workbook(self.path)
        import copy
        for issue in ("identity", "bank", "slot", "overflow"):
            sheets = copy.deepcopy(original)
            if issue == "identity":
                sheets["Flag Layout"][1][1] = FlagLayout().identity
            elif issue == "bank":
                sheets["Chapter Flags"][2][3] = "vanilla"
            elif issue == "slot":
                sheets["Chapter Flags"][2][4] = 99
            else:
                for i in range(65):
                    sheets["Chapter Flags"].append(["18", i + 2, f"extra{i}", "vanilla", None])
            excel_io.write_workbook(self.path, sheets)
            with self.subTest(issue=issue), self.assertRaises(ValueError):
                flag_excel.plan_banked_import(self.path, self.campaign, self.chapters, self.layout)

    def test_legacy_workbook_additions_are_vanilla(self):
        chapters = {"18": self.chapters["18"] + ["old_format_new"]}
        flag_excel.export_flags(self.path, self.campaign, chapters)
        layout, additions = flag_excel.plan_banked_import(self.path, self.campaign, self.chapters, self.layout)
        self.assertEqual(layout, self.layout)
        self.assertEqual(additions["18"], ["old_format_new"])


if __name__ == "__main__":
    unittest.main()
