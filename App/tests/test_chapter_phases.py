"""Phase folder lifecycle and chapter-part helpers."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fe_modding import chapter_phase_ops
from fe_modding.formats import dispo, lz10, pak
from fe_modding.games import Game
from test_formats import _build_minimal_dispo_bytes


class PhaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = SimpleNamespace(
            extracted_dir=self.root, game=Game.PATH_OF_RADIANCE,
            has_extracted_files=True, name="Test", directory=self.root.parent,
            game_info=SimpleNamespace(short_code="PoR"))
        self.zmap = self.root / "files" / "zmap"
        source = self.zmap / "bmap09"
        source.mkdir(parents=True)
        (source / "map.cmp").write_bytes(b"map")
        doc = dispo.parse_dispo(_build_minimal_dispo_bytes())
        doc.section("SECA").name = "bmap09_first_n"
        dispo._set_section_table(doc, [doc.sections[i] for i in doc.table_order])
        archive = pak.pack_pak([("dispos_n.bin", dispo.build_dispo(doc))])
        (source / "dispos.cmp").write_bytes(lz10.compress(archive))

    def test_missing_map_does_not_create_a_phase(self):
        (self.zmap / "bmap09" / "map.cmp").unlink()
        with self.assertRaisesRegex(ValueError, "no map.cmp"):
            chapter_phase_ops.plan_clone(self.project, "09", "bmap09")
        self.assertFalse((self.zmap / "bmap09_2").exists())

    def test_clone_renames_longer_deployment_sections(self):
        clone = chapter_phase_ops.plan_clone(self.project, "09", "bmap09")
        self.assertEqual(clone.folder, "bmap09_2")
        chapter_phase_ops.create_phase(clone)
        target = self.zmap / clone.folder
        self.assertEqual((target / "map.cmp").read_bytes(), b"map")
        packed = lz10.decompress((target / "dispos.cmp").read_bytes())
        entry = pak.read_pak_entries(packed)[0]
        doc = dispo.parse_dispo(pak.read_pak_file_content(packed, entry))
        self.assertIsNotNone(doc.section("bmap09_2_first_n"))
        self.assertIsNone(doc.section("bmap09_first_n"))
        self.assertEqual(chapter_phase_ops.next_folder(self.project, "09"), "bmap09_3")

    def test_clone_and_remove_battle_scene_row(self):
        from fe_modding.formats import fe8data
        from test_fe8data_tables import build
        data = build()
        rows = fe8data.read_battle_terrain(data)
        rows.append(fe8data.BattleTerrainRow("bmap09", list(rows[1].scenes)))
        data = fe8data.write_battle_terrain(data, rows)
        clone = chapter_phase_ops.plan_clone(self.project, "09", "bmap09", data)
        self.assertIn("bmap09_2", [row.map_name for row in fe8data.read_battle_terrain(clone.fe8data)])
        chapter_phase_ops.create_phase(clone)
        _path, updated = chapter_phase_ops.plan_remove(
            self.project, "09", "bmap09_2", "", clone.fe8data)
        self.assertNotIn("bmap09_2", [row.map_name for row in fe8data.read_battle_terrain(updated)])

    def test_remove_requires_unreferenced_secondary_phase(self):
        clone = chapter_phase_ops.plan_clone(self.project, "09", "bmap09")
        chapter_phase_ops.create_phase(clone)
        with self.assertRaisesRegex(ValueError, "primary"):
            chapter_phase_ops.plan_remove(self.project, "09", "bmap09", "")
        with self.assertRaisesRegex(ValueError, "references"):
            chapter_phase_ops.plan_remove(
                self.project, "09", "bmap09_2", 'MapLoad("bmap09_2")')
        path, _ = chapter_phase_ops.plan_remove(self.project, "09", "bmap09_2", "")
        chapter_phase_ops.remove_phase(self.project, path)
        self.assertFalse(path.exists())

    def test_remove_checks_saved_script_even_when_unsaved_text_is_clear(self):
        from fe_modding.formats.cmb import compile_source, write_cmb
        clone = chapter_phase_ops.plan_clone(self.project, "09", "bmap09")
        chapter_phase_ops.create_phase(clone)
        scripts = self.root / "files" / "Scripts"
        scripts.mkdir()
        source = 'def Opening0():\n    MapLoad("bmap09_2")\n'
        (scripts / "C09.cmb").write_bytes(write_cmb(compile_source(source).script))
        with self.assertRaisesRegex(ValueError, "C09.cmb still references"):
            chapter_phase_ops.plan_remove(self.project, "09", "bmap09_2", "")

    def test_part_status_tracks_deployment_and_victory_links(self):
        source = chapter_phase_ops.add_part_opening(
            "def Startup():\n    pass\n", 2, "bmap09_2")
        self.assertEqual(chapter_phase_ops.part_setup_issues(source, "bmap09_2"),
                         (2, ["deployment", "previous victory"]))
        linked = source.replace('    MapLoad("bmap09_2")',
                                '    MapLoad("bmap09_2")\n'
                                '    DisposFirst("bmap09_2_first_n")')
        linked += '\ndef Victory():\n    Complete18(1)\n'
        self.assertEqual(chapter_phase_ops.part_setup_issues(linked, "bmap09_2"), (2, []))
        self.assertIsNone(chapter_phase_ops.part_setup_issues(linked, "bmap09_3"))
    def test_cancelled_phase_switch_keeps_the_old_selection(self):
        from fe_modding.gui.pages.chapters import ChapterPage
        page = SimpleNamespace(
            _phase="bmap09", _phase_var=Mock(),
            _map=SimpleNamespace(dirty=True, display_name="Map"),
            _deployment=SimpleNamespace(dirty=False, display_name="Deployment"))
        with patch("fe_modding.gui.pages.chapters.messagebox.askyesno", return_value=False):
            self.assertFalse(ChapterPage._set_phase(page, "bmap09_2"))
        self.assertEqual(page._phase, "bmap09")
        page._phase_var.set.assert_called_once_with("bmap09")
        self.assertTrue(page._map.dirty)
    def test_playable_part_limit_and_order(self):
        source = "def Startup():\n    pass\n"
        for part in (2, 3, 4):
            self.assertEqual(chapter_phase_ops.next_part(source), part)
            source = chapter_phase_ops.add_part_opening(source, part, f"bmap09_{part}")
            self.assertIn(f"Opening18_{part}", source)
        from fe_modding.formats.cmb import compile_source
        compiled = compile_source(source)
        self.assertEqual([fn.id_string for fn in compiled.script.functions if fn.id_string],
                         ["Opening18_2", "Opening18_3", "Opening18_4"])
        with self.assertRaisesRegex(ValueError, "at most four"):
            chapter_phase_ops.next_part(source)
        with self.assertRaisesRegex(ValueError, "gap"):
            chapter_phase_ops.next_part(
                "@export\ndef Opening18_3():\n    pass\n")


if __name__ == "__main__":
    unittest.main()
