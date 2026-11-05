"""Radiant Dawn music: new stream sounds in sound_us.brsar, new cues in sound_data, and the
Music page's add/remove through rd_music."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.exceptions import ProjectError
from fe_modding.games import Game

FE10 = os.environ.get("FE10_EXTRACTED_FILES")
TEMPLATE = "fe10_bgm_sys_base2_32k.brstm"


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class FormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fe_modding.formats import lz10
        cls.archive = (Path(FE10) / "Sound" / "sound_us.brsar").read_bytes()
        cls.cues = lz10.decompress((Path(FE10) / "Sound" / "sound_data_en.cms").read_bytes())

    def test_every_retail_name_is_found_through_the_tree(self):
        from fe_modding.formats import brsar
        archive = brsar.read_brsar(self.archive)
        strings, trees = brsar._symb_layout(self.archive, archive)
        self.assertTrue(all(brsar.tree_lookup(*trees[0], strings, s.name) == s.index for s in archive.sounds))
        self.assertTrue(all(brsar.tree_lookup(*trees[3], strings, b.name) == b.index for b in archive.banks))
        self.assertIsNone(brsar.tree_lookup(*trees[0], strings, "STRM_NOT_A_SOUND"))

    def test_add_and_remove_a_stream_sound(self):
        from fe_modding.formats import brsar
        archive = brsar.read_brsar(self.archive)
        template = next(s for s in archive.sounds if s.name == "STRM_BGM_SYS_KYOTEN1")
        spec = brsar.stream_spec(archive, template.index, "STRM_BGM_TEST_ONE", "strm/test_one.brstm", 1234, 2)
        one = brsar.add_stream_sound(self.archive, spec)
        added = brsar.read_brsar(one)
        self.assertEqual(len(added.sounds), len(archive.sounds) + 1)
        sound = added.sounds[-1]
        self.assertEqual((sound.name, sound.external_path, sound.sound_type, sound.volume),
                         ("STRM_BGM_TEST_ONE", "strm/test_one.brstm", 2, template.volume))
        self.assertEqual(brsar.sound_id_of(one, "STRM_BGM_TEST_ONE"), len(archive.sounds))
        self.assertTrue(all(brsar.sound_id_of(one, s.name) == s.index for s in archive.sounds))
        self.assertTrue(all(a.raw == b.raw for a, b in zip(archive.sounds, added.sounds)))
        self.assertTrue(all((a.header, a.wave_data) == (b.header, b.wave_data)
                            for a, b in zip(archive.files, added.files)))
        two = brsar.add_stream_sound(one, brsar.stream_spec(added, sound.index, "STRM_BGM_TEST_TWO",
                                                            "strm/test_two.brstm", 99))
        self.assertEqual(brsar.remove_added_sound(two, self.archive, "STRM_BGM_TEST_TWO"), one)
        self.assertEqual(brsar.remove_added_sound(one, self.archive, "STRM_BGM_TEST_ONE"), self.archive)
        with self.assertRaises(brsar.BrsarError):
            brsar.remove_added_sound(one, self.archive, "STRM_BGM_SYS_KYOTEN1")
        with self.assertRaises(brsar.BrsarError):
            brsar.add_stream_sound(one, spec)
        wave = next(s for s in archive.sounds if s.sound_type == 3)
        with self.assertRaises(brsar.BrsarError):
            brsar.stream_spec(archive, wave.index, "STRM_X", "strm/x.brstm", 1)

    def test_one_entry_rwsd_and_a_new_wave_sound(self):
        from fe_modding.formats import brsar, rwsd
        archive = brsar.read_brsar(self.archive)
        sound = next(s for s in archive.sounds if s.name == "SE1_SYS_SELECT2")
        source = archive.files[sound.file_index]
        document = rwsd.read_rwsd(source.header, source.wave_data)
        header, wave = rwsd.single_entry_rwsd(document, sound.info_index)
        one = rwsd.read_rwsd(header, wave)
        self.assertEqual((len(one.entries), one.entries[0].wave_index), (1, 0))
        self.assertEqual(rwsd.decode_wave(one, 0),
                         rwsd.decode_wave(document, document.entries[sound.info_index].wave_index))
        tone = rwsd.RwsdAudio(32000, (tuple((i * 37) % 2000 - 1000 for i in range(3200)),))
        header, wave = rwsd.replace_wave(one, 0, tone)
        out = brsar.add_wave_sound(self.archive, brsar.wave_spec(archive, sound.index, "SE_TEST_BEEP", header, wave))
        added = brsar.read_brsar(out)
        new = added.sounds[-1]
        self.assertEqual((new.name, new.sound_type, new.info_index), ("SE_TEST_BEEP", 3, 0))
        self.assertEqual(brsar.sound_id_of(out, "SE_TEST_BEEP"), new.index)
        self.assertEqual({group for group, _ in added.files[new.file_index].group_refs},
                         {group for group, _ in source.group_refs})
        self.assertEqual((added.files[new.file_index].header, added.files[new.file_index].wave_data), (header, wave))
        self.assertTrue(all((a.header, a.wave_data) == (b.header, b.wave_data)
                            for a, b in zip(archive.files, added.files)))
        self.assertEqual(brsar.remove_added_sound(out, self.archive, "SE_TEST_BEEP"), self.archive)
        stream = next(s for s in archive.sounds if s.sound_type == 2)
        with self.assertRaises(brsar.BrsarError):
            brsar.wave_spec(archive, stream.index, "SE_X", header, wave)

    def test_add_and_remove_a_cue(self):
        from fe_modding.formats import fe10_sound, fe8data
        out = fe10_sound.add_cue(self.cues, "BGM_TEST_ONE", "STRM_BGM_TEST_ONE", "BGM_BASE1")
        cues, old = fe10_sound.cue_map(out), fe10_sound.cue_map(self.cues)
        self.assertEqual(cues["BGM_TEST_ONE"].resource, "STRM_BGM_TEST_ONE")
        self.assertEqual(cues["BGM_TEST_ONE"].raw_words, old["BGM_BASE1"].raw_words)
        self.assertTrue(all(cues[name].resource == cue.resource for name, cue in old.items()))
        names = [raw for _offset, raw in fe10_sound._raw_symbols(out)]
        self.assertEqual(names, sorted(names))
        back = fe10_sound.remove_cue(out, "BGM_TEST_ONE", self.cues)
        self.assertEqual(set(fe10_sound.cue_map(back)), set(old))
        with self.assertRaises(fe10_sound.Fe10SoundError):
            fe10_sound.remove_cue(out, "BGM_BASE1", self.cues)
        with self.assertRaises(fe10_sound.Fe10SoundError):
            fe10_sound.add_cue(self.cues, "BGM_BASE1", "STRM_X", "BGM_BASE1")
        with self.assertRaises(fe10_sound.Fe10SoundError):
            fe10_sound.add_cue(self.cues, "bad name", "STRM_X", "BGM_BASE1")


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class ProjectTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.project import ModProject

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "music", Game.RADIANT_DAWN)
        files = self.project.extracted_dir / "files"
        for rel in ("Sound/sound_us.brsar", "Sound/sound_data_en.cms", f"Sound/strm/{TEMPLATE}"):
            (files / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(Path(FE10) / rel, files / rel)
            (files / rel).chmod(0o666)

    def _strm(self, name):
        from fe_modding.game_profile import files_root_of
        return files_root_of(self.project) / "Sound" / "strm" / name

    def test_new_track_and_its_removal(self):
        from fe_modding import rd_music
        from fe_modding.formats import brsar, fe10_sound
        template = self._strm(TEMPLATE)
        data = template.read_bytes()
        cue, sound = rd_music.add_track(self.project, "my_theme", data, template, 2)
        self.assertEqual((cue, sound), ("BGM_MY_THEME", "STRM_BGM_MY_THEME"))
        new = self._strm("my_theme.brstm")
        self.assertEqual(new.read_bytes(), data)
        self.assertEqual(fe10_sound.cue_map(self.project.read_logical("sound_data"))[cue].resource, sound)
        self.assertEqual([s.name for s in rd_music.stream_sounds(self.project, new)], [sound])
        self.assertTrue(rd_music.is_added_stream(self.project, new))
        self.assertFalse(rd_music.is_added_stream(self.project, template))
        self.assertEqual(rd_music.added_cues(self.project), {cue})
        with self.assertRaises(ProjectError):
            rd_music.add_track(self.project, "my_theme", data, template, 2)
        with self.assertRaises(ProjectError):
            rd_music.remove_track(self.project, template)

        self.assertEqual(rd_music.remove_track(self.project, new), [cue])
        self.assertFalse(new.exists())
        self.assertEqual(rd_music.added_cues(self.project), set())
        archive = self._strm("x").parent.parent / "sound_us.brsar"
        self.assertEqual(archive.read_bytes(), (Path(FE10) / "Sound" / "sound_us.brsar").read_bytes())
        self.assertIsNone(brsar.sound_id_of(archive.read_bytes(), sound))

    def test_new_sound_effect_and_its_removal(self):
        from fe_modding import rd_music
        from fe_modding.formats import brsar, fe10_sound
        archive = self._strm("x").parent.parent / "sound_us.brsar"
        before = archive.read_bytes()
        self.assertEqual(rd_music.wave_template(self.project, None), "SFX_SYS_SELECT1")
        stereo = [[(i * 53) % 3000 - 1500 for i in range(4000)]] * 2  # mixed down to the template's mono
        sound = rd_music.add_sfx(self.project, "SFX_TEST_BEEP", 32000, stereo, "SFX_SYS_SELECT1")
        self.assertEqual(sound, "SE_TEST_BEEP")
        cues = fe10_sound.cue_map(self.project.read_logical("sound_data"))
        self.assertEqual(cues["SFX_TEST_BEEP"].resource, "SE_TEST_BEEP")
        self.assertIsNotNone(brsar.sound_id_of(archive.read_bytes(), "SE_TEST_BEEP"))
        self.assertEqual(rd_music.wave_template(self.project, "SFX_TEST_BEEP"), "SFX_TEST_BEEP")
        with self.assertRaises(ProjectError):
            rd_music.add_sfx(self.project, "SFX_TEST_BEEP", 32000, stereo, "SFX_SYS_SELECT1")
        with self.assertRaises(ProjectError):
            rd_music.remove_sfx(self.project, "SFX_SYS_SELECT1")
        rd_music.remove_sfx(self.project, "SFX_TEST_BEEP")
        self.assertEqual(archive.read_bytes(), before)
        self.assertNotIn("SFX_TEST_BEEP", fe10_sound.cue_map(self.project.read_logical("sound_data")))

    def test_new_cue_for_a_retail_track(self):
        from fe_modding import rd_music
        from fe_modding.formats import fe10_sound
        template = self._strm(TEMPLATE)
        resource = rd_music.add_cue(self.project, "BGM_BASE_AGAIN", template)
        cues = fe10_sound.cue_map(self.project.read_logical("sound_data"))
        self.assertEqual(cues["BGM_BASE_AGAIN"].resource, resource)
        rd_music.remove_cue(self.project, "BGM_BASE_AGAIN")
        self.assertNotIn("BGM_BASE_AGAIN", fe10_sound.cue_map(self.project.read_logical("sound_data")))
        with self.assertRaises(ProjectError):
            rd_music.remove_cue(self.project, "BGM_BASE1")


if __name__ == "__main__":
    unittest.main()
