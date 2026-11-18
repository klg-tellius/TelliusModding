"""Radiant Dawn Game Code on the European and Japanese builds (rd_regions, rd_region_table).

The disc checks need each region's extracted disc:

    FE10_EXTRACTED      = .../RFEE01     (the US one, as elsewhere)
    FE10_EU_EXTRACTED   = .../RFEP01
    FE10_JP_EXTRACTED   = .../RFEJ01
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from fe_modding.game_code import chapter_jump_fe10, entries_fe10, rd_hub, rd_regions, rd_story, verify  # noqa: F401
from fe_modding.game_code.catalog import CATALOG, Session, State
from fe_modding.game_code.dol import Dol
from fe_modding.game_code.rd_region_table import SDA, TABLE, VERIFIED
from fe_modding.game_code.versions import ALL_VERSIONS, identify

ENV = {"RFEE01": "FE10_EXTRACTED", "RFEP01": "FE10_EU_EXTRACTED", "RFEJ01": "FE10_JP_EXTRACTED"}


def _dol(code: str) -> Dol | None:
    """``code``'s retail main.dol, from its variable; None when unset or when it points at another
    region (a full run may point FE10_EXTRACTED at the European or Japanese disc)."""
    from tests.corpus import disc_id
    root = os.environ.get(ENV[code])
    path = Path(root) / "sys" / "main.dol" if root else None
    if path is None or not path.is_file() or disc_id(Path(root) / "files") != code:
        return None
    return Dol.open(path)


def _rd_entries():
    return [e for e in CATALOG.entries_for("RFEE01")] + [rd_story.PATCH, rd_hub.PATCH]


class RegionPortTests(unittest.TestCase):
    def test_versions_are_known(self):
        for code, region in (("RFEP01", "EU"), ("RFEJ01", "JP")):
            self.assertEqual(ALL_VERSIONS[code].region, region)
            self.assertEqual(ALL_VERSIONS[code].family, "R")

    def test_moving_to_the_same_build_changes_nothing(self):
        """Relocation with the identity map rebuilds every US byte unchanged."""
        for entry in _rd_entries():
            ported = rd_regions.port_sites(entry, lambda a: a, SDA["RFEE01"], SDA["RFEE01"])
            for us, same in zip(entry.versions["RFEE01"], ported):
                self.assertEqual(us, same, entry.id)

    def test_checked_entries_have_their_region_sites(self):
        for code in rd_regions.REGIONS:
            for entry in _rd_entries():
                self.assertEqual(code in entry.versions, entry.id in VERIFIED[code], (code, entry.id))
        self.assertEqual(len(VERIFIED["RFEP01"]), len(_rd_entries()))
        missing = {e.id for e in _rd_entries()} - VERIFIED["RFEJ01"]
        self.assertEqual(missing, {"rd.skill.wrath_hp_ratio"})
        self.assertNotIn(CATALOG.entries["rd.skill.wrath_hp_ratio"], CATALOG.entries_for("RFEJ01"))

    def test_moved_branches_reach_the_moved_routine(self):
        """The one-RN hit patch calls the single-roll routine: on each build the call lands on
        that build's copy of it."""
        entry = CATALOG.entries["rd.combat.single_roll_hit"]
        for code in rd_regions.REGIONS:
            edit, = entry.versions[code]
            word = int.from_bytes(edit.patched, "big")
            offset = word & 0x03FFFFFC
            if offset & 0x02000000:
                offset -= 0x04000000
            self.assertEqual(edit.address + offset, TABLE[0x80089D68][rd_regions.REGIONS.index(code)])

    def test_story_runtime_reads_each_builds_party(self):
        """The story hook's party and chapter addresses are the region's own (party at r13 data)."""
        for code in rd_regions.REGIONS:
            hook = next(e for e in rd_story.PATCH.versions[code] if e.address == rd_story.HOOK)
            us_hook = next(e for e in rd_story.PATCH.versions["RFEE01"] if e.address == rd_story.HOOK)
            self.assertEqual(len(hook.patched), len(us_hook.patched))
            self.assertNotEqual(hook.patched, us_hook.patched)


class RegionDiscTests(unittest.TestCase):
    def test_every_entry_applies_and_reverts_on_each_build(self):
        ran = 0
        for code in ENV:
            dol = _dol(code)
            if dol is None:
                continue
            ran += 1
            with self.subTest(code=code):
                ident = identify(dol)
                self.assertEqual((ident.version.code, ident.pristine), (code, True))
                self.assertEqual(verify.verify(dol), [])

    def test_story_hub_and_jump_install_on_each_build(self):
        for code in ENV:
            dol = _dol(code)
            if dol is None:
                continue
            with self.subTest(code=code):
                retail = Dol(bytes(dol.data))
                session = Session(dol, ALL_VERSIONS[code], retail.read)
                for patch in (rd_story.PATCH, rd_hub.PATCH, chapter_jump_fe10.JUMP_PATCH):
                    self.assertEqual(session.patch_status(patch).state, State.ORIGINAL, patch.id)
                session.set_patch(rd_story.PATCH, True)
                session.set_patch(rd_hub.PATCH, True)
                chapter_jump_fe10.install(session, 5, 1)
                for patch in (rd_story.PATCH, rd_hub.PATCH, chapter_jump_fe10.JUMP_PATCH):
                    self.assertEqual(session.patch_status(patch).state, State.APPLIED, patch.id)
                for patch in (chapter_jump_fe10.JUMP_PATCH, rd_hub.PATCH, rd_story.PATCH):
                    session.set_patch(patch, False)
                self.assertEqual(dol.sha1(), retail.sha1())


if __name__ == "__main__":
    unittest.main()


class RegionCodecTests(unittest.TestCase):
    def test_european_text_table(self):
        from fe_modding.formats import fe10_message as F
        raw = bytes([0x6D, 0xD6, 0x67, 0x65, 0x6E, 0x81, 0x63, 0xDF, 0x51, 0x75, 0xC9])   # mögen…¿Qué
        self.assertEqual(raw.decode(F.EU_ENCODING), "mögen…¿Qué")
        self.assertEqual("mögen…¿Qué".encode(F.EU_ENCODING), raw)
        self.assertEqual(len(F.EU_TABLE), 0xDF - 0xA1 + 1)
        self.assertEqual(F.encoding_for("d_c0101.m"), F.EU_ENCODING)
        self.assertEqual(F.encoding_for("e_c0101.m", "RFEP01"), F.EU_ENCODING)
        self.assertEqual(F.encoding_for("e_c0101.m", "RFEE01"), F.ENCODING)   # US English uses ｢｣
        self.assertEqual(F.encoding_for("c0101.m", "RFEP01"), F.ENCODING)
        with self.assertRaises(UnicodeEncodeError):
            "ｱ".encode(F.EU_ENCODING)

    def test_logical_file_falls_back_to_the_disc_s_own_name(self):
        import tempfile
        from fe_modding.game_profile import RADIANT_DAWN_PROFILE as profile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Sound").mkdir()
            (root / "Sound" / "sound.brsar").write_bytes(b"x")
            self.assertEqual(profile.path(root, "sound_archive"), root / "Sound" / "sound.brsar")
            (root / "Sound" / "sound_us.brsar").write_bytes(b"x")
            self.assertEqual(profile.path(root, "sound_archive"), root / "Sound" / "sound_us.brsar")

    def test_save_names_and_folders(self):
        from fe_modding.formats import save_file_fe10 as sf
        self.assertEqual(sf.file_name("RFEP01"), "FE10_EU.dat")
        self.assertEqual(sf.data_path("RFEP01").as_posix(), "Wii/title/00010000/52464550/data")
        self.assertEqual(sf.data_path("RFEJ01").as_posix(), "Wii/title/00010000/5246454a/data")
        # a Japanese file: six file records and one checkpoint after the system record
        save = sf.SaveFile.from_bytes(bytes([0xFF]) * sf.JP_FILE_SIZE)
        self.assertEqual(len(save.records), 7)
        self.assertEqual([r.checkpoint for r in save.records], [False] * 6 + [True])
        self.assertEqual(save.records[-1].offset, 0x94000)
        with self.assertRaises(ValueError):
            sf.SaveFile.from_bytes(bytes(0x1000))


def _files(code: str) -> Path | None:
    root = os.environ.get(ENV[code])
    path = Path(root) / "files" if root else None
    return path if path is not None and path.is_dir() else None


class RegionCorpusTests(unittest.TestCase):
    def test_japanese_items_have_no_article(self):
        from fe_modding.formats import fe10data, lz10
        files = _files("RFEJ01")
        if files is None:
            self.skipTest("set FE10_JP_EXTRACTED")
        data = lz10.decompress((files / "FE10Data.cms").read_bytes())
        self.assertEqual(fe10data.item_fixed(data), fe10data.ITEM_FIXED_JP)
        items = fe10data.read_table(data, "item")
        self.assertEqual((len(items), items[2].values["iid"], items[-1].end),
                         (293, "IID_IRONSWORD", fe10data.table_start(data, "skill")))
        self.assertNotIn("article", {d.key for d in fe10data.field_defs("item", data)})

    def test_european_language_files_round_trip(self):
        from fe_modding.formats import dialogue_notation, fe10_message as F, message
        from tests.corpus import sample
        files = _files("RFEP01")
        if files is None:
            self.skipTest("set FE10_EU_EXTRACTED")
        paths = sample(sorted((files / "Mess").glob("?_*.m")), keep=("d_c0101", "s_ending", "i_common"))
        for path in paths:
            encoding = F.encoding_for(path.name, "RFEP01")
            for m in message.read_messages_path(path):
                shown = F.to_display(m.text, encoding)
                self.assertEqual(F.to_raw(shown, encoding), m.text, path.name)
                self.assertEqual(dialogue_notation.display(m.text, True, encoding).raw, m.text, path.name)
        text = F.to_display(message.read_messages_path(files / "Mess" / "d_c0101.m")[5].text, F.EU_ENCODING)
        self.assertIn("Göttin", text)

    def test_european_scripts_call_only_known_functions(self):
        from types import SimpleNamespace
        from fe_modding.formats.cmb import read_cmb_path
        from fe_modding.playthrough import natives
        from fe_modding.playthrough.dialect import dialect_for
        files = _files("RFEP01")
        if files is None:
            self.skipTest("set FE10_EU_EXTRACTED")
        startup = read_cmb_path(files / "Scripts" / "startup.cmb")
        from fe_modding.formats.cmb.catalog import FE10_EU_ONLY_EXTERNS
        for stem in ("C0315", "CFINAL", "T01"):
            world = SimpleNamespace(scripts=[read_cmb_path(files / "Scripts" / f"{stem}.cmb"), startup],
                                    dialect=dialect_for("fe10"))
            unclassified = natives.audit_scripts(world)["unclassified"]
            if stem.startswith("C"):        # chapters: as on the US disc, nothing unclassified
                self.assertEqual(unclassified, [], stem)
            # the trial maps call unclassified natives on every disc; none of them European-only
            self.assertFalse(set(unclassified) & set(FE10_EU_ONLY_EXTERNS), stem)
