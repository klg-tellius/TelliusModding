"""Starting a campaign: the checks, chaining chapters in order, adding characters, blanking deployments.
The real chapter copy needs a game extraction, so the orchestration is tested with a stand-in for it."""

import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fe_modding import campaign
from fe_modding.formats import dispo, fe8data, lz10, message, pak
from fe_modding.games import Game
from fe_modding.project import ModProject
from test_fe8data_tables import build
from dispo_fixture import build_minimal_dispo_bytes as _build_minimal_dispo_bytes


@dataclass
class _Plan:
    fe8data: bytes
    warnings: list = field(default_factory=list)


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = ModProject.create(Path(self._tmp.name), "C", Game.PATH_OF_RADIANCE)
        self.files = self.project.extracted_dir / "files"
        for name in ("c00.m", "c01.m"):
            self._write(f"Mess/{name}", message.write_messages([]))
        self._write("Scripts/C01.cmb", b"")
        self._write("Mess/common.m", message.write_messages([message.Message("MCT01", "Prologue")]))
        self.fe8 = build()
        self.calls = []

    def _write(self, relative, data):
        path = self.files / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def fake_add_chapter(self, project, fe8, template, new_id, title, after, flow):
        self.calls.append((template, new_id, title, after))
        data, index = fe8data.add_record(fe8, "chapter", copy_from=0)
        return _Plan(fe8data.patch_chapter_field(data, index, "chapter_id", new_id), [f"warn {new_id}"])

    # -- checks -------------------------------------------------------------------------------
    def test_a_good_request_has_no_problems(self):
        specs = [campaign.ChapterSpec("One", "01")]
        cast = [campaign.CharacterSpec("PID_NEWBIE", "PID_BOLE", "Newbie")]
        self.assertEqual(campaign.check_campaign(self.project, self.fe8, specs, cast, after=1), [])

    def test_problems_are_listed_together(self):
        specs = [campaign.ChapterSpec("Bad title é", "77"), campaign.ChapterSpec("No script", "00")]
        cast = [campaign.CharacterSpec("pid_low", "PID_IKE"), campaign.CharacterSpec("PID_IKE", "PID_IKE"),
                campaign.CharacterSpec("PID_X", "PID_NOBODY", jid="JID_NOPE")]
        problems = "\n".join(campaign.check_campaign(self.project, self.fe8, specs, cast, after=9))
        for fragment in ("Chapter 09", "template chapter 77 does not exist", "plain ASCII", "no script to copy",
                         "'pid_low'", "PID_IKE already exists", "PID_NOBODY does not exist", "JID_NOPE"):
            self.assertIn(fragment, problems)

    def test_too_many_chapters(self):
        specs = [campaign.ChapterSpec(f"C{i}", "01") for i in range(60)]
        self.assertIn("only 57 chapter numbers are free", "\n".join(campaign.check_campaign(self.project, self.fe8, specs)))

    # -- adding -------------------------------------------------------------------------------
    def test_chapters_are_chained_in_order(self):
        specs = [campaign.ChapterSpec("One", "01"), campaign.ChapterSpec("Two", "01"), campaign.ChapterSpec("Three", "01")]
        result = campaign.add_campaign(self.project, self.fe8, specs, after=1, add_chapter=self.fake_add_chapter)
        self.assertEqual(result.chapter_ids, [33, 34, 35])
        self.assertEqual(self.calls, [("01", 33, "One", 1), ("01", 34, "Two", 33), ("01", 35, "Three", 34)])
        self.assertEqual(result.warnings, ["warn 33", "warn 34", "warn 35"])
        ids = [r.chapter_id for r in fe8data.read_chapter_data(result.fe8data)]
        self.assertEqual(ids[-3:], [33, 34, 35])

    def test_nothing_is_added_when_the_check_fails(self):
        with self.assertRaisesRegex(ValueError, "template chapter 77"):
            campaign.add_campaign(self.project, self.fe8, [campaign.ChapterSpec("A", "77")],
                                  add_chapter=self.fake_add_chapter)
        self.assertEqual(self.calls, [])

    def test_a_failure_names_the_chapters_already_added(self):
        def flaky(project, fe8, template, new_id, title, after, flow):
            if title == "Two":
                raise OSError("disk full")
            return self.fake_add_chapter(project, fe8, template, new_id, title, after, flow)
        specs = [campaign.ChapterSpec("One", "01"), campaign.ChapterSpec("Two", "01")]
        with self.assertRaisesRegex(ValueError, r"(?s)Chapter 34 \(Two\) failed: disk full.*added before it: 33"):
            campaign.add_campaign(self.project, self.fe8, specs, add_chapter=flaky)

    def test_characters_are_copies_with_their_own_name(self):
        cast = [campaign.CharacterSpec("PID_NEWBIE", "PID_BOLE", "Newbie", jid="JID_CLERIC"),
                campaign.CharacterSpec("PID_PLAIN", "PID_MIST")]
        result = campaign.add_campaign(self.project, self.fe8, [], cast)
        self.assertEqual(result.pids, ["PID_NEWBIE", "PID_PLAIN"])
        characters = {c.pid: c for c in fe8data.read_fe8data(result.fe8data).characters}
        self.assertEqual((characters["PID_NEWBIE"].jid, characters["PID_NEWBIE"].mpid), ("JID_CLERIC", "MPID_NEWBIE"))
        self.assertEqual(characters["PID_PLAIN"].mpid, characters["PID_MIST"].mpid)  # shares the template's name
        texts = {m.speaker: m.text for m in message.read_messages_path(self.files / "Mess" / "common.m")}
        self.assertEqual(texts["MPID_NEWBIE"], "Newbie")
        self.assertEqual(texts["MCT01"], "Prologue")

    # -- order ------------------------------------------------------------------------------------
    def test_story_order_sets_only_the_links_that_change(self):
        class Flow:
            available = True
            def __init__(self):
                self.links = {1: 2, 2: 33, 33: 34, 34: 32}
                self.set = None
            def next_of(self, c):
                return self.links.get(c, c + 1)
            def set_many(self, changes):
                self.set = dict(changes)
        flow = Flow()
        campaign.set_story_order(flow, [1, 2, 34, 33])
        self.assertEqual(flow.set, {2: 34, 34: 33, 33: 32})

    def test_story_order_refuses_bad_orders(self):
        flow = type("Flow", (), {"available": True, "next_of": lambda self, c: c + 1,
                                 "set_many": lambda self, ch: None})()
        for order in ([], [33, 33], [1, 95], [1, 32]):
            with self.assertRaises(ValueError):
                campaign.set_story_order(flow, order)

    # -- blank deployments ----------------------------------------------------------------------
    def test_blank_dispos_keeps_sections_and_drops_units(self):
        data = _build_minimal_dispo_bytes()
        before = dispo.parse_dispo(data)
        self.assertTrue(any(s.units for s in before.sections))
        after = dispo.parse_dispo(campaign.blank_dispos_bytes(data))
        self.assertEqual([s.name for s in after.sections], [s.name for s in before.sections])
        self.assertEqual([len(s.units) for s in after.sections], [0] * len(after.sections))

    def test_blank_chapter_units_rewrites_the_pack(self):
        packed = pak.pack_pak([("dispos_n.bin", _build_minimal_dispo_bytes()), ("other.bin", b"keep")], [0, 0])
        self._write("zmap/bmap33/dispos.cmp", lz10.compress(packed))
        self.assertEqual(campaign.blank_chapter_units(self.project, "33"), ["zmap/bmap33/dispos.cmp"])
        out = lz10.decompress((self.files / "zmap/bmap33/dispos.cmp").read_bytes())
        contents = {e.name: pak.read_pak_file_content(out, e) for e in pak.read_pak_entries(out)}
        self.assertEqual(contents["other.bin"], b"keep")
        self.assertEqual(sum(len(s.units) for s in dispo.parse_dispo(contents["dispos_n.bin"]).sections), 0)


if __name__ == "__main__":
    unittest.main()
