"""game_code.story_flow: one story-flow interface over PoR's chapter_flow and RD's rd_story, and
Radiant Dawn's Add chapter (chapters_fe10) behind it."""

import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.game_code import rd_story
from fe_modding.game_code.catalog import State
from fe_modding.game_code.story_flow import PorStoryFlow, RdStoryFlow
from fe_modding.game_profile import (CHAPTER_FLOW, HUB, MAP_PHASES, NEW_CAMPAIGN, PATH_OF_RADIANCE_PROFILE,
                                     RADIANT_DAWN_PROFILE)

FILES = os.environ.get("FE10_EXTRACTED_FILES")


class FakeEditor:
    """The CodeEditor surface the flows use: patch states, DOL reads and session writes."""

    def __init__(self):
        self.memory: dict[int, int] = {}
        self.applied: set[str] = set()
        self.dol = self
        self.session = self

    def status(self, patch):
        return SimpleNamespace(state=State.APPLIED if patch.id in self.applied else State.ORIGINAL, detail="")

    def read(self, address, size):
        return bytes(self.memory.get(address + i, 0) for i in range(size))

    def has_section_at(self, address):
        return False

    def _write(self, address, data):
        for i, byte in enumerate(data):
            self.memory[address + i] = byte

    def set_patch(self, patch, on):
        edits = next(iter(patch.versions.values()))
        for edit in edits:
            self._write(edit.address, edit.patched if on else edit.original)
        (self.applied.add if on else self.applied.discard)(patch.id)

    def save(self):
        pass


def _rd_ids():
    ids = {n: f"C{n:04d}" for n in range(rd_story.ENDING)}   # stand-in ids, one per story number
    ids.update({1: "C0101", 2: "C0102", 3: "C0103", rd_story.ENDING: "CFINAL", 56: "C0501"})
    return ids


class RdFlowTests(unittest.TestCase):
    def setUp(self):
        self.editor = FakeEditor()
        self.flow = RdStoryFlow(self.editor, _rd_ids())

    def test_retail_order_in_page_ids(self):
        order = self.flow.order()
        self.assertEqual(order[:4], ["0000", "0101", "0102", "0103"])
        self.assertEqual(order[-1], "final")
        self.assertNotIn("0501", order)
        self.assertEqual(self.flow.next_of("0101"), "0102")
        self.assertIsNone(self.flow.next_of("final"))
        self.assertEqual(self.flow.predecessors("0102"), ["0101"])

    def test_insert_and_remove_an_added_chapter(self):
        self.assertTrue(self.flow.locked("0101"))
        self.assertFalse(self.flow.locked("0501"))
        self.flow.insert_after("0101", "0501")
        self.assertEqual(self.editor.status(rd_story.PATCH).state, State.APPLIED)
        reopened = RdStoryFlow(self.editor, _rd_ids())
        self.assertEqual(reopened.order()[:4], ["0000", "0101", "0501", "0102"])
        self.assertTrue(reopened.removable("0501"))
        self.assertEqual(self.editor.read(rd_story.SUCCESSORS + 1, 1), bytes([56]))
        self.assertEqual(self.editor.read(rd_story.SUCCESSORS + 56, 1), bytes([2]))
        reopened.remove("0501")
        self.assertEqual(reopened.order()[:3], ["0000", "0101", "0102"])
        self.assertEqual(self.editor.read(rd_story.SUCCESSORS, 0x100), bytes(0x100))  # back to retail routing
        self.assertEqual(self.editor.read(rd_story.ARMIES, 0x100), rd_story._retail_armies())

    def test_refusals(self):
        with self.assertRaisesRegex(ValueError, "retail"):
            self.flow.remove("0102")
        with self.assertRaisesRegex(ValueError, "ends the story"):
            self.flow.set_next("final", "0101")
        with self.assertRaisesRegex(ValueError, "last"):
            self.flow.set_order(["0000", "final", "0101"])
        self.assertFalse(self.flow.can_follow("0000"))
        self.assertIn("record", self.flow.outside_reason("0999"))

    def test_set_order_moves_added_chapters(self):
        ids = {**_rd_ids(), 57: "C0502"}
        flow = RdStoryFlow(self.editor, ids)
        flow.insert_after("0101", "0501")
        flow.insert_after("0501", "0502")
        order = flow.order()
        i = order.index("0501")
        order[i], order[i + 1] = order[i + 1], order[i]
        flow.set_order(order)
        self.assertEqual(flow.order()[1:5], ["0101", "0502", "0501", "0102"])

    def test_armies_are_a_field(self):
        self.assertTrue(self.flow.armies)
        self.assertEqual(self.flow.army("0101"), rd_story.Army.MAIN)
        self.assertEqual(self.flow.armies_editable, rd_story.ARMY_RUNTIME_READY)


class PorFlowTests(unittest.TestCase):
    def setUp(self):
        self.editor = FakeEditor()
        self.flow = PorStoryFlow(self.editor)

    def test_two_digit_ids_and_the_ending(self):
        self.assertEqual(self.flow.order()[:3], ["01", "02", "03"])
        self.assertEqual(self.flow.order()[-1], "31")
        self.assertEqual(self.flow.next_of("31"), "32")
        self.assertEqual(self.flow.label("32", {}), "32 · Ending")
        self.assertTrue(self.flow.locked("31"))
        self.assertIn("trial", self.flow.outside_reason("90"))

    def test_insert_and_order(self):
        self.flow.insert_after("05", "40")
        self.assertEqual(self.flow.order()[4:7], ["05", "40", "06"])
        self.assertTrue(self.flow.removable("40"))
        self.flow.remove("40")
        self.assertEqual(self.flow.order()[4:6], ["05", "06"])


class CapabilityTests(unittest.TestCase):
    def test_story_flow_is_on_both_games(self):
        self.assertTrue(PATH_OF_RADIANCE_PROFILE.supports(CHAPTER_FLOW))
        self.assertTrue(RADIANT_DAWN_PROFILE.supports(CHAPTER_FLOW))
        self.assertTrue(RADIANT_DAWN_PROFILE.supports(NEW_CAMPAIGN))
        for feature in (NEW_CAMPAIGN, HUB, MAP_PHASES):
            self.assertTrue(PATH_OF_RADIANCE_PROFILE.supports(feature))
        for feature in (HUB, MAP_PHASES):
            self.assertFalse(RADIANT_DAWN_PROFILE.supports(feature))

    def test_chapter_page_holds_no_game_checks(self):
        source = (Path(__file__).resolve().parents[1] / "fe_modding" / "gui" / "pages" / "chapters.py").read_text(
            encoding="utf-8")
        for check in ("script_dialect", "message_dialect", "open_rd_story"):
            self.assertNotIn(check, source)

    def test_custom_ids(self):
        from fe_modding import chapters_fe10
        self.assertEqual(chapters_fe10.chapter_id_for(56), "0501")
        self.assertEqual(chapters_fe10.chapter_id_for(79), "0524")
        self.assertEqual(chapters_fe10.number_for("0524"), 79)
        self.assertIsNone(chapters_fe10.number_for("0525"))
        self.assertIsNone(chapters_fe10.number_for("0204"))
        with self.assertRaises(ValueError):
            chapters_fe10.chapter_id_for(55)


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class MapPackRenameTests(unittest.TestCase):
    def test_models_and_sections_take_the_new_name(self):
        from fe_modding import chapters
        from fe_modding.formats import lz10, pak

        map_bin = b"bmap0101\x00bmap0101_water0\x00bmap0101:mapdata\x00xbmap0101\x00bmap01010\x00"
        packed = lz10.compress(pak.pack_pak([("bmap0101.gs", b"gs"), ("bmap0101_water0.g", b"g"),
                                             ("boat01.g", b"b"), ("map.bin", map_bin)], [0, 0, 0, 0]))
        out = lz10.decompress(chapters.rename_map_pack(packed, "bmap0101", "bmap0501"))
        entries = pak.read_pak_entries(out)
        self.assertEqual([e.name for e in entries], ["bmap0501.gs", "bmap0501_water0.g", "boat01.g", "map.bin"])
        self.assertEqual(pak.read_pak_file_content(out, entries[3]),
                         b"bmap0501\x00bmap0501_water0\x00bmap0501:mapdata\x00xbmap0101\x00bmap01010\x00")
        self.assertEqual(chapters.rename_map_pack(packed, "bmap0101", "bmap101"), packed)  # other length: kept


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdAddChapterTests(unittest.TestCase):
    """Add chapter on a scratch Radiant Dawn project holding chapter 0204's files."""

    def setUp(self):
        from fe_modding.games import Game
        from fe_modding.project import ModProject

        source = Path(FILES)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "rd flow", Game.RADIANT_DAWN)
        files = self.files = self.project.files_dir
        for rel in ("FE10Data.cms", "Scripts/C0204.cmb", "Mess/c0204.m", "Mess/e_c0204.m", "Mess/n0204.m",
                    "Mess/e_n0204.m", "Mess/common.m", "Mess/e_common.m", "Shop/shopitem_n.bin",
                    "Shop/shopitem_h.bin", "Shop/shopitem_m.bin", "window/title/e_ch0204.cms", "Fonts/talk.cms"):
            (files / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source / rel, files / rel)
        shutil.copytree(source / "zmap" / "bmap0204", files / "zmap" / "bmap0204")
        sys_dir = self.project.extracted_dir / "sys"
        sys_dir.mkdir(exist_ok=True)
        for name in ("main.dol", "boot.bin"):
            shutil.copy(source.parent / "sys" / name, sys_dir / name)
        for path in [*files.rglob("*"), *sys_dir.iterdir()]:
            if path.is_file():
                path.chmod(0o666)

    def test_new_chapter_is_complete_and_reachable(self):
        from fe_modding import chapters
        from fe_modding.formats import fe10data, lz10, message, shop
        from fe_modding.game_adapter import RdDataAdapter
        from fe_modding.game_code.story_flow import open_story_flow

        data = lz10.decompress((self.files / "FE10Data.cms").read_bytes())
        session = SimpleNamespace(data=data, fe10=fe10data.read_fe10data(data))
        adapter = RdDataAdapter(session)
        self.assertIn("0204", adapter.chapter_templates(self.project))
        self.assertEqual(adapter.free_chapters(self.project)[0], "0501")
        flow, why = open_story_flow(self.project)
        self.assertIsNotNone(flow, why)
        retail_next = flow.next_of("0204")
        new, warnings = adapter.add_story_chapter(self.project, "0204", "0501", "II:9-A New Road", "0204", flow)
        self.assertEqual(warnings, [])

        record = fe10data.read_table(new, "chapter")[-1].values
        self.assertEqual((record["cid"], record["number"], record["map"], record["script"], record["messages"],
                          record["title"]), ("C0501", 56, "bmap0501", "C0501", "C0501", "MCT0501"))
        rows = fe10data.read_table(new, "battle_scenery")
        self.assertEqual(rows[-1].values["map"], "bmap0501")
        self.assertEqual(rows[-1].lists["scenery"],
                         next(r for r in rows if r.values["map"] == "bmap0204").lists["scenery"])

        for diff in "cnh":
            raw = (self.files / "zmap" / "bmap0501" / f"dispos_{diff}.bin").read_bytes()
            self.assertNotIn(b"bmap0204", raw)
            self.assertIn(b"bmap0501", raw)
        # the game finds a map's models and sections by the map's name: the copy renames them
        from fe_modding.formats import pak
        packed = lz10.decompress((self.files / "zmap" / "bmap0501" / "map.cmp").read_bytes())
        entries = pak.read_pak_entries(packed)
        self.assertIn("bmap0501.gs", [e.name for e in entries])
        self.assertFalse(any(e.name.startswith("bmap0204") for e in entries))
        map_bin = pak.read_pak_file_content(packed, next(e for e in entries if e.name == "map.bin"))
        self.assertIn(b"bmap0501:mapdata\x00", map_bin)
        self.assertNotIn(b"bmap0204", map_bin)
        script = (self.files / "Scripts" / "C0501.cmb").read_bytes()
        pool_start, table_start = struct.unpack_from("<II", script, 0x24)
        self.assertIn(b"bmap0501_mikata", script[pool_start:table_start])
        self.assertNotIn(b"bmap0204\x00", script[pool_start:table_start])
        self.assertIn(b"\x00C0501\x00", script[pool_start:table_start])  # ChapterTitle("C0501")
        for name in ("c0501.m", "e_c0501.m", "n0501.m", "e_n0501.m"):
            self.assertTrue((self.files / "Mess" / name).is_file(), name)
        self.assertIn("0501", chapters.list_chapter_ids(self.project))
        doc = shop.parse_shop((self.files / "Shop" / "shopitem_n.bin").read_bytes())
        self.assertEqual(doc.shop("W", "0501").items, doc.shop("W", "0204").items)
        titles = {m.speaker: m.text for m in message.read_messages_path(self.files / "Mess" / "e_common.m")}
        self.assertEqual(titles["MCT0501"], "II:9-A New Road")
        self.assertTrue((self.files / "window" / "title" / "e_ch0501.cms").is_file())

        reopened = RdStoryFlow(flow.editor.__class__(self.project.extracted_dir), rd_story.chapter_number_map(new))
        self.assertEqual(reopened.next_of("0204"), "0501")
        self.assertEqual(reopened.next_of("0501"), retail_next)
        self.assertEqual(reopened.order().count("0501"), 1)

    def test_new_campaign(self):
        from fe_modding import campaign
        from fe_modding.formats import dispo, fe10data, lz10, message
        from fe_modding.game_adapter import RdDataAdapter
        from fe_modding.game_code.story_flow import open_story_flow

        data = lz10.decompress((self.files / "FE10Data.cms").read_bytes())
        adapter = RdDataAdapter(SimpleNamespace(data=data, fe10=fe10data.read_fe10data(data)))
        flow, _why = open_story_flow(self.project)
        retail_next = flow.next_of("0204")
        specs = [campaign.ChapterSpec("A New Road", "0204"), campaign.ChapterSpec("Empty Fields", "0204", True)]
        cast = [campaign.CharacterSpec("PID_NEWHERO", "PID_MICAIAH", "Nova", "JID_BLADE")]
        self.assertEqual(adapter.campaign_problems(self.project, specs, cast, "0204"), [])
        bad = [campaign.CharacterSpec("PID_MICAIAH", "PID_NOPE")]
        self.assertEqual(len(adapter.campaign_problems(self.project, specs, bad, "0204")), 2)

        new, ids, warnings = adapter.add_campaign(self.project, specs, cast, "0204", flow)
        self.assertEqual((ids, warnings), (["0501", "0502"], []))
        self.assertEqual([r.values["cid"] for r in fe10data.read_table(new, "chapter")][-2:], ["C0501", "C0502"])
        hero = next(r for r in fe10data.read_fe10data(new).characters if r.id == "PID_NEWHERO")
        self.assertEqual((hero.values["jid"], hero.values["mpid"]), ("JID_BLADE", "MPID_NEWHERO"))
        names = {m.speaker: m.text for m in message.read_messages_path(self.files / "Mess" / "e_common.m")}
        self.assertEqual(names["MPID_NEWHERO"], "Nova")
        # the second chapter keeps only the player's army
        for diff in "nh":
            doc = dispo.parse_dispo((self.files / "zmap" / "bmap0502" / f"dispos_{diff}.bin").read_bytes())
            self.assertTrue(all(not s.units for s in doc.sections if campaign.PLAYER_SECTION_MARK not in s.name))
        (self.files / "FE10Data.cms").write_bytes(lz10.compress(new))
        flow, _why = open_story_flow(self.project)
        self.assertEqual((flow.next_of("0204"), flow.next_of("0501"), flow.next_of("0502")),
                         ("0501", "0502", retail_next))

    def test_added_chapter_is_deleted_and_retail_ones_are_refused(self):
        from fe_modding import chapters
        from fe_modding.formats import fe10data, lz10, message, shop
        from fe_modding.game_adapter import RdDataAdapter
        from fe_modding.game_code.story_flow import open_story_flow

        retail = lz10.decompress((self.files / "FE10Data.cms").read_bytes())
        shops_before = (self.files / "Shop" / "shopitem_n.bin").read_bytes()
        session = SimpleNamespace(data=retail, fe10=fe10data.read_fe10data(retail))
        adapter = RdDataAdapter(session)
        flow, _why = open_story_flow(self.project)
        retail_next = flow.next_of("0204")
        added, _warnings = adapter.add_story_chapter(self.project, "0204", "0501", "II:9-A New Road", "0204", flow)
        self.assertFalse(adapter.deletable("0204"))
        self.assertTrue(adapter.deletable("0501"))

        session = SimpleNamespace(data=added, fe10=fe10data.read_fe10data(added))
        adapter = RdDataAdapter(session)
        flow, _why = open_story_flow(self.project)
        with self.assertRaisesRegex(ValueError, "retail chapter"):
            adapter.remove_story_chapter(self.project, "0204", flow)
        # the story flow reads chapter numbers from the saved database: give it the one with 0501
        (self.files / "FE10Data.cms").write_bytes(lz10.compress(added))
        flow, _why = open_story_flow(self.project)
        data = adapter.remove_story_chapter(self.project, "0501", flow)

        # the record and the battle-scenery row are gone and nothing else changed (the new names stay in
        # the string pool, unused)
        for kind in ("chapter", "battle_scenery", "character", "class", "item"):
            self.assertEqual([(r.values, r.lists) for r in fe10data.read_table(data, kind)],
                             [(r.values, r.lists) for r in fe10data.read_table(retail, kind)], kind)
        self.assertFalse((self.files / "zmap" / "bmap0501").exists())
        for rel in ("Scripts/C0501.cmb", "Mess/c0501.m", "Mess/e_c0501.m", "window/title/e_ch0501.cms"):
            self.assertFalse((self.files / rel).exists(), rel)
        self.assertNotIn("0501", chapters.list_chapter_ids(self.project))
        self.assertEqual((self.files / "Shop" / "shopitem_n.bin").read_bytes(), shops_before)
        titles = {m.speaker for m in message.read_messages_path(self.files / "Mess" / "e_common.m")}
        self.assertNotIn("MCT0501", titles)
        (self.files / "FE10Data.cms").write_bytes(lz10.compress(data))
        flow, _why = open_story_flow(self.project)
        self.assertEqual(flow.next_of("0204"), retail_next)


if __name__ == "__main__":
    unittest.main()
