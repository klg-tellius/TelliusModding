import json
import unittest
from pathlib import Path

from fe_modding.formats.extended_flags import FlagLayout
from fe_modding.game_code.dol import Dol
from fe_modding.game_code.extended_flag_candidate import build_candidate
from fe_modding.game_code.extended_flag_installation import inspect_runtime, receipt_for, rebuild_installed, RuntimeState
from fe_modding.game_code.extended_flag_runtime import BASE

RETAIL = Path(__file__).resolve().parents[2] / "research/main_dol/dols"


class InstallationTests(unittest.TestCase):
    def candidate(self, region, hub=None):
        path = RETAIL / f"{region}.dol"
        if not path.exists():
            self.skipTest("retail DOL unavailable")
        layout = FlagLayout().add("custom", "chapter", 18)
        candidate = build_candidate(Dol.open(path), region, layout, hub_chapter=hub)
        return layout, candidate, receipt_for(candidate, layout)

    def test_verified_installation_and_compatible_updates_all_regions(self):
        from fe_modding.game_code.chapter_flow import FLOW_TABLE
        for region in ("GFEE01", "GFEP01", "GFEJ01"):
            for hub in (None, 40):
                layout, candidate, receipt = self.candidate(region, hub)
                dol = Dol(candidate.executable)
                if hub is not None:
                    dol.write(FLOW_TABLE + 5, b"\x09")
                self.assertEqual(inspect_runtime(dol, region, layout, receipt).state, RuntimeState.MATCHING)
                new = layout.add("another", "campaign")
                before = bytes(dol.data)
                rebuilt = rebuild_installed(dol, region, layout, new, receipt)
                self.assertEqual(bytes(dol.data), before)
                result = Dol(rebuilt.executable)
                self.assertEqual(inspect_runtime(result, region, new, receipt_for(rebuilt, new)).state, RuntimeState.MATCHING)
                if hub is not None:
                    self.assertEqual(result.read(FLOW_TABLE + 5, 1), b"\x09")

    def test_missing_mismatched_and_corrupt_metadata_or_hooks(self):
        layout, candidate, receipt = self.candidate("GFEE01", 40)
        dol = Dol(candidate.executable)
        self.assertEqual(inspect_runtime(dol, "GFEE01", FlagLayout(), receipt).state, RuntimeState.MANIFEST_MISMATCH)
        self.assertEqual(inspect_runtime(dol, "GFEE01", layout, None).state, RuntimeState.CONFLICT)
        for address in (BASE, BASE + len(candidate.image.data) - 1, candidate.image.edits[0].address):
            corrupt = Dol(candidate.executable)
            corrupt.write(address, bytes([corrupt.read(address, 1)[0] ^ 1]))
            self.assertEqual(inspect_runtime(corrupt, "GFEE01", layout, receipt).state, RuntimeState.CONFLICT)
        unsupported = json.loads(receipt)
        unsupported["revision"] = 999
        self.assertEqual(inspect_runtime(dol, "GFEE01", layout, json.dumps(unsupported)).state, RuntimeState.UNSUPPORTED)
        pristine = Dol.open(RETAIL / "GFEE01.dol")
        self.assertEqual(inspect_runtime(pristine, "GFEE01", None, None).state, RuntimeState.ABSENT)
        self.assertEqual(inspect_runtime(pristine, "GFEE01", layout, receipt).state, RuntimeState.CONFLICT)

    def test_tampered_receipt_cannot_bless_changed_code(self):
        import hashlib
        layout, candidate, receipt = self.candidate("GFEE01")
        dol = Dol(candidate.executable)
        dol.write(BASE + 0x100, b"\0\0\0\0")
        modified = json.loads(receipt)
        modified["section_sha256"] = hashlib.sha256(dol.read(BASE, len(candidate.image.data))).hexdigest()
        self.assertEqual(inspect_runtime(dol, "GFEE01", layout, json.dumps(modified)).state, RuntimeState.CONFLICT)

    def test_editor_preserves_dependencies_and_allows_other_flow_edits(self):
        import tempfile
        from fe_modding.formats.extended_flags import MANIFEST_NAME
        from fe_modding.game_code.extended_flag_installation import RECEIPT_NAME
        from fe_modding.game_code.editor import CodeEditor
        from fe_modding.game_code.chapter_flow import ChapterFlow, FLOW_PATCH
        from fe_modding.game_code.hub_flow import HubFlow
        layout, candidate, receipt = self.candidate("GFEE01", 40)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            extracted = root / "extracted"
            (extracted / "sys").mkdir(parents=True)
            path = extracted / "sys/main.dol"
            path.write_bytes(candidate.executable)
            (extracted / "sys/boot.bin").write_bytes(b"GFEE01" + bytes(0x43a))
            (root / MANIFEST_NAME).write_text(layout.to_json(), encoding="utf-8")
            (root / RECEIPT_NAME).write_text(receipt, encoding="utf-8")
            editor = CodeEditor(extracted)
            self.assertTrue(HubFlow(editor).installed)
            ChapterFlow(editor).set_next(5, 9)
            before = path.read_bytes()
            for operation in (lambda e: ChapterFlow(e).set_next(40, 8),
                              lambda e: ChapterFlow(e).set_next(8, 40),
                              lambda e: ChapterFlow(e).remove(40),
                              lambda e: HubFlow(e).remove(),
                              lambda e: e.set_patch(FLOW_PATCH, False),
                              lambda e: e.reset(FLOW_PATCH)):
                with self.assertRaises(ValueError):
                    operation(CodeEditor(extracted))
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
