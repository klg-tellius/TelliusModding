"""Fixes from the release 1.0 tests run on the real discs (2026-11-25): model folders copied in
input/output projects, a character's own Radiant Dawn battle row, animation packs over the vanilla
files, the release check's summary on a non-UTF-8 console."""

import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import animation_catalog, model_slots
from fe_modding.formats import fe10_battle
from fe_modding.game_files import OverlayFiles
from tests.synthetic_data import fe10_battle_file


class OverlayTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup, tmp)
        root = Path(tmp.name)
        self.input, self.output = root / "input", root / "output"
        self.input.mkdir()
        self.output.mkdir()
        self.files = OverlayFiles(self.input, self.output, root / "overlay.json")

    def _cleanup(self, tmp):
        for path in Path(tmp.name).rglob("*"):
            if path.is_file():
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        tmp.cleanup()

    def vanilla(self, rel: str, data: bytes, read_only: bool = True) -> None:
        path = self.input / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if read_only:
            os.chmod(path, stat.S_IREAD)


class CopyFolderTests(OverlayTestCase):
    def test_copy_of_a_read_only_vanilla_folder_can_be_renamed_and_keeps_edits(self):
        self.vanilla("files/zu/swoL/swoL.tpl", b"texture")
        self.vanilla("files/zu/swoL/ax.pak", b"vanilla axe")
        self.files.write("files/zu/swoL/ax.pak", b"edited axe")    # an edit in the project
        source = self.files.at("files/zu/swoL")
        dest = self.files.at("files/zu/cesr")
        model_slots._copy_folder(source, dest)
        self.assertEqual((dest / "ax.pak").read_bytes(), b"edited axe")
        copied = (dest / "swoL.tpl").real()
        self.assertTrue(str(copied).startswith(str(self.output)))
        self.assertTrue(copied.stat().st_mode & stat.S_IWRITE)       # not the store's read-only flag
        (dest / "swoL.tpl").rename(dest / "cesr.tpl")             # failed with "Access denied" before
        self.assertEqual((dest / "cesr.tpl").read_bytes(), b"texture")
        self.assertEqual((self.input / "files/zu/swoL/swoL.tpl").read_bytes(), b"texture")


class AnimationContainerTests(OverlayTestCase):
    def test_path_of_radiance_lists_every_weapon_pack_when_one_is_edited(self):
        for weapon in ("ax", "ha", "no"):
            self.vanilla(f"files/zu/fig1/fig1_{weapon}.pak", weapon.encode())
        self.files.write("files/zu/fig1/fig1_ax.pak", b"edited")
        containers = animation_catalog.animation_containers(self.files.at("files/zu/fig1/fig1_ax.pak"))
        self.assertEqual([c.name for c in containers], ["fig1_ax.pak", "fig1_ha.pak", "fig1_no.pak"])
        self.assertEqual(containers[0].read_bytes(), b"edited")

    def test_radiant_dawn_reads_edited_packs_when_pack_cmp_is_vanilla(self):
        self.vanilla("files/zu/drm1/pack.cmp", b"body")
        self.vanilla("files/zu/drm1/ax.pak", b"vanilla ax")
        self.vanilla("files/zu/drm1/ha.pak", b"vanilla ha")
        self.files.write("files/zu/drm1/ax.pak", b"edited ax")
        containers = animation_catalog.animation_containers(self.files.at("files/zu/drm1/pack.cmp"))
        self.assertEqual({c.name: c.read_bytes() for c in containers},
                         {"ax.pak": b"edited ax", "ha.pak": b"vanilla ha"})


class _Project:
    def __init__(self, data: bytes):
        self.data = data

    def read_logical(self, name: str) -> bytes:
        assert name == "battle_data"
        return self.data


class RdOwnRowTests(unittest.TestCase):
    def test_a_character_row_keyed_by_animation_id_is_pointed_at_the_model(self):
        # Edward's row is keyed AID_SWORDER1_E + PID_EDDIE + JID_BLADE: assigning by character and
        # class was refused ("Row 4 comes first in the game's lookup").
        data = fe10_battle.update_battle_selector(fe10_battle_file(), 0, aid="AID_ALPHA",
                                                  pid="PID_ALPHA", jid="JID_SWORD")
        project = _Project(data)
        with mock.patch.object(model_slots, "vanilla_battle_codes", return_value={"modelA", "modelB"}):
            result = model_slots._rd_assign(project, "modelB", aid=None, pid="PID_ALPHA", jid="JID_SWORD")
        battle = fe10_battle.read_fe10_battle(result)
        rows = [dict(r.strings) for r in battle.table("FE10BAnimData").records]
        self.assertEqual(len(rows), 2)                      # no extra row
        self.assertEqual(rows[0].get(12), "UNIT_B")
        self.assertEqual(rows[0].get(0), "AID_ALPHA")
        self.assertEqual(fe10_battle.select_battle_row(battle, "AID_ALPHA", "PID_ALPHA", "JID_SWORD"), 0)


class ReleaseCheckOutputTests(unittest.TestCase):
    def test_summary_prints_on_a_cp1252_console(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import release_check
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with mock.patch.object(sys, "stdout", stream):
            release_check._print_safely("coverage: 0.0006 % ✓ 剣士エディ")
        stream.flush()
        self.assertIn(b"coverage: 0.0006 %", stream.buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
