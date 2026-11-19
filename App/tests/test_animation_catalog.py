"""The clip list of a model set, clip writes across weapon archives, .ga imports and playback timing,
on sets written from scratch (no game data)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import animation_catalog as cat
from fe_modding import rig_contract
from fe_modding.formats import animation, lz10, pak, skeleton

RD_FILES = os.environ.get("FE10_EXTRACTED_FILES")
POR_FILES = os.environ.get("FE9_EXTRACTED_FILES")


def _ga(end=10, events=None, bone=0):
    """A one-curve Path of Radiance clip of ``end`` frames on ``bone``."""
    header = animation.GaHeader(words=(0, 0, 0, 0x11, 0, 1, end, 0, 0, 0, 0, 0))
    curves = [animation.AnimCurve(bone, 3, 4, end, [animation.Keyframe(0, 0), animation.Keyframe(end, 16)])]
    anim = animation.GaAnimation(header, [animation.BoneGroup(bone, 16, 0, 1)], curves)
    data = animation.write_animation(anim)
    return rig_contract.replace_events(data, events) if events else data


def _skeleton(count=2):
    floats = tuple([1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0] + [0.5] * 43)
    bones = [skeleton.Bone(f"b{i}", i - 1, (-1, -1, 0x180), floats, (i, 1)) for i in range(count)]
    return skeleton.write_skeleton_file(skeleton.SkeletonFile(root_name="[unknown]", bones=bones))


HIT = [animation.EventKey(4, (1,)), animation.EventKey(6, (0, 1510))]


def _battle_set(root: Path, code="bole", axe_dodge=None) -> Path:
    """A Path of Radiance battle set ``zu/<code>`` with an axe and a hand-axe archive sharing their
    damage clip; ``axe_dodge`` gives the axe archive its own dodge clip (else both share one)."""
    folder = root / "zu" / code
    folder.mkdir(parents=True)
    shared_dam = _ga(10)
    dodge = _ga(8)
    axe = [("fig1.gs", b"gs"), ("fig1.g", _skeleton()), ("fig1_at1_ax.ga", _ga(20, HIT)),
           ("fig1_dam_ax.ga", shared_dam), ("fig1_dog_ax.ga", axe_dodge or dodge)]
    hand = [("fig1.gs", b"gs"), ("fig1.g", _skeleton()), ("fig1_lda_ax.ga", _ga(12, [animation.EventKey(5, (2,))])),
            ("fig1_dam_ax.ga", shared_dam), ("fig1_dog_ax.ga", dodge)]
    (folder / f"{code}_ax.pak").write_bytes(pak.pack_pak(axe))
    (folder / f"{code}_ha.pak").write_bytes(pak.pack_pak(hand))
    return folder / f"{code}_ax.pak"


def _files(container: Path, archive: str) -> dict[str, bytes]:
    return cat.read_container(container.parent / archive)[1]


class ClipListTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_shared_clips_are_listed_once_with_every_archive(self):
        container = _battle_set(self.root)
        clips = cat.set_clips(container)
        by_file = {c.file: c for c in clips}
        self.assertEqual(sorted(by_file), ["fig1_at1_ax.ga", "fig1_dam_ax.ga", "fig1_dog_ax.ga", "fig1_lda_ax.ga"])
        self.assertEqual(by_file["fig1_dam_ax.ga"].packs, ["ax", "ha"])
        self.assertEqual(by_file["fig1_at1_ax.ga"].packs, ["ax"])
        self.assertEqual(by_file["fig1_at1_ax.ga"].role, "attack 1")
        self.assertEqual(by_file["fig1_at1_ax.ga"].frames, 20)
        self.assertEqual(by_file["fig1_at1_ax.ga"].combat_frames(), {0: [6], 1: [4]})
        self.assertEqual(by_file["fig1_lda_ax.ga"].role, "throw")
        tree = cat.clips_by_pack(clips)
        self.assertEqual(list(tree), ["ax", "ha"])
        self.assertEqual([c.file for c in tree["ha"]], ["fig1_lda_ax.ga"])

    def test_same_name_different_bytes_are_two_clips(self):
        container = _battle_set(self.root, axe_dodge=_ga(9))
        dodges = [c for c in cat.set_clips(container) if c.file == "fig1_dog_ax.ga"]
        self.assertEqual([c.packs for c in dodges], [["ax"], ["ha"]])
        clips = cat.set_clips(container)
        self.assertEqual(cat.clip_packs(clips, dodges[1]), ["ha"])
        dam = next(c for c in clips if c.file == "fig1_dam_ax.ga")
        self.assertIsNone(cat.clip_packs(clips, dam))

    def test_an_edit_reaches_every_identical_copy(self):
        container = _battle_set(self.root)
        new = _ga(14)
        out, notes = cat.clip_output(container, "fig1_dam_ax.ga", new)
        self.assertEqual(sorted(p.name for p in out), ["bole_ax.pak", "bole_ha.pak"])
        for path, data in out.items():
            path.write_bytes(data)
        self.assertEqual(_files(container, "bole_ax.pak")["fig1_dam_ax.ga"], new)
        self.assertEqual(_files(container, "bole_ha.pak")["fig1_dam_ax.ga"], new)
        self.assertTrue(any("every copy" in n for n in notes))

    def test_differing_copies_change_one_archive_at_a_time(self):
        container = _battle_set(self.root, axe_dodge=_ga(9))
        out, notes = cat.clip_output(container, "fig1_dog_ax.ga", _ga(11))
        self.assertEqual([p.name for p in out], ["bole_ax.pak"])
        self.assertTrue(any("different" in n for n in notes))
        out, notes = cat.clip_output(container, "fig1_dog_ax.ga", _ga(11), ["ha"])
        self.assertEqual([p.name for p in out], ["bole_ha.pak"])
        with self.assertRaises(cat.ClipError):
            cat.clip_output(container, "fig1_nope.ga", _ga(11))

    def test_map_model_clips_include_loose_files(self):
        folder = self.root / "ymu" / "fighter"
        folder.mkdir(parents=True)
        container = folder / "pack.cmp"
        container.write_bytes(lz10.compress(pak.pack_pak([("body.gs", b"x"), ("wait.ga", _ga(30))])))
        (folder / "atk1.ga").write_bytes(_ga(25, HIT))
        clips = cat.set_clips(container)
        self.assertEqual([(c.file, c.packs) for c in clips], [("wait.ga", ["pack"]), ("atk1.ga", ["loose"])])
        self.assertEqual(clips[0].role, "idle")
        self.assertEqual(clips[1].role, "attack")
        out, _notes = cat.clip_output(container, "atk1.ga", _ga(5))
        self.assertEqual(list(out), [folder / "atk1.ga"])


class GaImportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.container = _battle_set(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_file_without_events_gets_the_replaced_clips_moved_in_proportion(self):
        out, warnings = cat.replace_clip_with_ga(self.container, "fig1_at1_ax.ga", _ga(40))
        data = cat.unpack(self.container, out[self.container])[1]["fig1_at1_ax.ga"]
        events = animation.read_animation_bytes(data).events
        self.assertEqual([(e.frame, e.codes) for e in events], [(8, (1,)), (12, (0, 1510))])
        self.assertTrue(any("20 to 40 frames" in w for w in warnings))

    def test_a_file_with_its_own_events_keeps_them_and_is_warned_about_missing_combat_codes(self):
        ga = _ga(20, [animation.EventKey(3, (1510,))])
        out, warnings = cat.replace_clip_with_ga(self.container, "fig1_at1_ax.ga", ga)
        data = cat.unpack(self.container, out[self.container])[1]["fig1_at1_ax.ga"]
        self.assertEqual([(e.frame, e.codes) for e in animation.read_animation_bytes(data).events], [(3, (1510,))])
        self.assertTrue(any("lacks event code" in w for w in warnings))

    def test_unreadable_files_are_refused(self):
        with self.assertRaises(cat.ClipError):
            cat.replace_clip_with_ga(self.container, "fig1_at1_ax.ga", b"not an animation at all, not at all")

    def test_a_file_for_another_skeleton_is_refused(self):
        with self.assertRaises(cat.ClipError) as caught:
            cat.replace_clip_with_ga(self.container, "fig1_at1_ax.ga", _ga(20, bone=5))
        self.assertIn("2 bones", str(caught.exception))

    def test_shared_clip_import_reaches_both_archives(self):
        out, _w = cat.replace_clip_with_ga(self.container, "fig1_dam_ax.ga", _ga(12))
        self.assertEqual(len(out), 2)


class TimingTests(unittest.TestCase):
    def test_playback_runs_at_sixty_frames_a_second(self):
        self.assertEqual(cat.playback_frame(10.0, 11.0, 120), (60.0, False))
        self.assertEqual(cat.playback_frame(10.0, 11.0, 120, speed=0.5), (30.0, False))
        frame, ended = cat.playback_frame(0.0, 1.5, 59)  # 90 frames into a 59-frame loop (60 positions)
        self.assertAlmostEqual(frame, 30.0)
        self.assertFalse(ended)
        self.assertEqual(cat.playback_frame(0.0, 2.0, 59, loop=False), (59.0, True))
        self.assertEqual(cat.playback_frame(0.0, 0.5, 59, loop=False, start_frame=10), (40.0, False))

    def test_event_marks_follow_the_slider(self):
        events = [animation.EventKey(0, (1,)), animation.EventKey(10, (1510,)), animation.Fe10EventKey(20, ((0, 3),))]
        marks = cat.event_marks(events, 20, x0=100, width=216)
        self.assertEqual(marks, [(108.0, 0, True), (208.0, 10, False), (308.0, 20, True)])
        self.assertEqual(cat.event_marks(events, 20, 0, 10), [])

    def test_retimed_events_and_labels(self):
        moved = cat.retimed_events(HIT, 10, 20)
        self.assertEqual([e.frame for e in moved], [8, 12])
        self.assertEqual(cat.event_code_label(0), "0 hit")
        self.assertEqual(cat.event_code_label((1510, 2)), "1510:2 sound")
        self.assertEqual(cat.event_code_label(50), "50 footstep / dust")


class NamingTests(unittest.TestCase):
    def test_glTF_names_find_their_clip(self):
        from fe_modding.gui import model_viewer as mv

        clips = [cat.ClipInfo("fig1_dog_ax.ga", ["ax"], b""), cat.ClipInfo("fig1_dog_ax.ga", ["ha"], b""),
                 cat.ClipInfo("fig1_at1_ax.ga", ["ax"], b"")]
        self.assertEqual(mv.match_clip("fig1_at1_ax", clips), 2)
        self.assertEqual(mv.match_clip("fig1_dog_ax@ha", clips), 1)
        self.assertEqual(mv.match_clip("FIG1_DOG_AX", clips), 0)
        self.assertIsNone(mv.match_clip("wait", clips))
        self.assertEqual(mv.clip_choice_label(clips[1]), "fig1_dog_ax.ga [ha]")
        self.assertEqual(mv.clip_choice_label(cat.ClipInfo("wait.ga", ["pack"], b"")), "wait.ga")

    def test_roles_by_game(self):
        self.assertEqual(cat.describe_clip("att1_ax.ga", battle=True, fe10=True), "attack 1")
        self.assertEqual(cat.describe_clip("pat1_ax.ga", battle=True, fe10=True), "")
        self.assertEqual(cat.describe_clip("avoid_2.ga", battle=False, fe10=True), "dodge")
        self.assertEqual(cat.describe_clip("fig1_cr1_ax_at1.ga", battle=True, fe10=False),
                         "critical 1, followed by attack 1")


def _moving_ga(end=12, bones=8, events=None):
    """A Path of Radiance clip turning each of ``bones`` bones about Z."""
    header = animation.GaHeader(words=(0, 0, 0, 0x11, 0, 1, end, 0, 0, 0, 0, 0))
    groups, curves = [], []
    for b in range(bones):
        groups.append(animation.BoneGroup(b, 16, len(curves), 1))
        curves.append(animation.AnimCurve(b, 5, 4, end, [animation.Keyframe(0, 0), animation.Keyframe(end, 8 + b)]))
    data = animation.write_animation(animation.GaAnimation(header, groups, curves))
    return rig_contract.replace_events(data, events) if events else data


def _named_skeleton(names):
    floats = tuple([1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0] + [0.0] * 43)
    bones = [skeleton.Bone(n, i - 1, (-1, -1, 0x180), floats, (i, 1)) for i, n in enumerate(names)]
    return skeleton.write_skeleton_file(skeleton.SkeletonFile(root_name="[unknown]", bones=bones))


BODY = ["Hips", "Spine", "Chest", "Neck", "Head", "LeftArm", "LeftForeArm", "LeftHand"]


def _copy_set(root: Path, code: str, names, clips) -> Path:
    folder = root / "zu" / code
    folder.mkdir(parents=True)
    files = [(f"{code}.gs", b"gs"), (f"{code}.g", _named_skeleton(names))] + clips
    (folder / f"{code}_sw.pak").write_bytes(pak.pack_pak(files))
    return folder / f"{code}_sw.pak"


class CopyClipTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = _copy_set(self.root, "swm1", BODY, [("swm1_at1_sw.ga", _moving_ga(12, events=HIT))])
        self.target = _copy_set(self.root, "swf1", BODY, [("swf1_at1_sw.ga", _ga(20)), ("swf1_dog_sw.ga", _ga(8))])

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_copy_moves_the_target_as_the_source_and_keeps_the_source_events(self):
        from fe_modding.formats import engine_pose
        copied = cat.copy_clip(self.source, "swm1_at1_sw.ga", self.target, "swf1_at1_sw.ga")
        self.assertEqual(list(copied.outputs), [self.target])
        self.assertEqual((copied.matched, copied.animated), (8, 8))
        ga = cat.unpack(self.target, copied.outputs[self.target])[1]["swf1_at1_sw.ga"]
        bones = skeleton.read_skeleton_file(_named_skeleton(BODY)).bones
        source = animation.read_animation_bytes(_moving_ga(12))
        result = animation.read_animation_bytes(ga)
        self.assertEqual(result.header.end_frame, 12)
        for frame in (0.0, 6.0, 12.0):
            want, _ = engine_pose.pose(bones, source, frame)
            got, _ = engine_pose.pose(bones, result, frame)
            for a, b in zip(want, got):
                for r in range(3):
                    for c in range(4):
                        self.assertAlmostEqual(a[r][c], b[r][c], places=3)
        self.assertEqual([(k.frame, k.codes) for k in rig_contract._events(ga)], [(4, (1,)), (6, (0, 1510))])

    def test_a_skeleton_with_too_few_shared_bones_is_refused(self):
        other = _copy_set(self.root, "drg1", [f"x{i}" for i in range(8)], [("drg1_at1_sw.ga", _ga(10))])
        with self.assertRaises(cat.ClipError):
            cat.copy_clip(self.source, "swm1_at1_sw.ga", other, "drg1_at1_sw.ga")

    def test_matching_clip_drops_the_set_codes_then_compares_roles(self):
        source = cat.set_clips(self.source)[0]
        targets = cat.set_clips(self.target)
        self.assertEqual(cat.matching_clip(source, "swm1", targets, "swf1").file, "swf1_at1_sw.ga")
        rd = cat.clips_from_animations([("dog1_ax.ga", _ga(8)), ("att1_ax.ga", _ga(8))], battle=True)
        for clip in rd:
            clip.role = cat.FE10_BATTLE_PREFIXES[clip.stem.split("_")[0]]
        self.assertEqual(cat.matching_clip(source, "swm1", rd, "figL").file, "att1_ax.ga")
        dodge = cat.clips_from_animations([("swf1_dog_sw.ga", _ga(8))], battle=True)[0]
        self.assertEqual(cat.matching_clip(dodge, "swf1", rd, "figL").file, "dog1_ax.ga")

    def test_sources_list_the_project_then_each_vanilla_disc_once(self):
        from unittest import mock
        from fe_modding import vanilla_store
        (self.root / "zdbx.cmp").write_bytes(b"")
        disc = self.root / "rd"
        (disc / "files").mkdir(parents=True)
        (disc / "files" / "FE10Data.cms").write_bytes(b"")
        stores = [vanilla_store.VanillaStore("a", disc, "RFEE01", 0, True),
                  vanilla_store.VanillaStore("b", self.root.parent / "missing", "GFEE01", 0, True)]
        with mock.patch.object(vanilla_store, "list_stores", return_value=stores):
            sources = cat.copy_sources(self.root)
        self.assertEqual(sources, [("This project", self.root), ("Vanilla Radiant Dawn (RFEE01)", disc / "files")])
        self.assertEqual(cat.disc_game(self.root), "fe9")
        self.assertEqual([label for label, _ in cat.character_sets(self.root)], ["zu/swf1", "zu/swm1"])


@unittest.skipUnless(RD_FILES and POR_FILES, "set FE9_EXTRACTED_FILES and FE10_EXTRACTED_FILES")
class CrossGameCopyTests(unittest.TestCase):
    def test_a_path_of_radiance_attack_plays_on_a_radiant_dawn_fighter_and_back(self):
        por = Path(POR_FILES) / "zu" / "fig1" / "fig1_ax.pak"
        rd = Path(RD_FILES) / "zu" / "figL" / "pack.cmp"
        there = cat.copy_clip(por, "fig1_at1_ax.ga", rd, "att1_ax.ga")
        self.assertTrue(animation.is_fe10_animation(cat.unpack(rd.parent / "ax.pak", there.outputs[rd.parent / "ax.pak"])[1]["att1_ax.ga"]))
        self.assertGreaterEqual(there.matched, 20)
        back = cat.copy_clip(rd, "att1_ax.ga", por, "fig1_at1_ax.ga")
        self.assertGreaterEqual(back.matched, 20)
        self.assertTrue(any("Events: fig1_at1_ax.ga's" in w for w in back.warnings))


@unittest.skipUnless(RD_FILES, "set FE10_EXTRACTED_FILES to Radiant Dawn's extracted files folder")
class RadiantDawnDiscTests(unittest.TestCase):
    def test_fighter_battle_set_lists_each_weapon_archive(self):
        clips = cat.set_clips(Path(RD_FILES) / "zu" / "figL" / "pack.cmp")
        packs = {p for c in clips for p in c.packs}
        self.assertTrue({"ax", "ha"} <= packs)
        attack = next(c for c in clips if c.file == "att1_ax.ga")
        self.assertEqual(attack.role, "attack 1")
        self.assertTrue(attack.fe10)
        self.assertIn(0, attack.combat_frames())


if __name__ == "__main__":
    unittest.main()
