import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.games import Game


def _boot(root: Path, disc_id: bytes) -> None:
    (root / "sys").mkdir(parents=True, exist_ok=True)
    (root / "sys" / "boot.bin").write_bytes(disc_id + bytes([0, 1]) + bytes(0x438))


class UnavailableStateTests(unittest.TestCase):
    """Features without a Radiant Dawn codec report it instead of reading the wrong layout."""

    def setUp(self):
        from fe_modding.project import ModProject

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = ModProject.create(Path(self._tmp.name), "RD", Game.RADIANT_DAWN)
        # a disc whose root FE8Data.bin (a leftover Path of Radiance database) must not be mistaken
        # for the game data
        files = self.project.files_dir
        files.mkdir(parents=True, exist_ok=True)
        (files / "FE8Data.bin").write_bytes(bytes(64))

    def test_validator_checks_the_radiant_dawn_database_not_the_leftover(self):
        from fe_modding import validator

        report = validator.validate_project(self.project)  # no FE10Data.cms extracted in this stand-in
        self.assertEqual([i.severity for i in report.issues], [validator.ERROR])
        self.assertIn("FE10Data.cms", report.issues[0].message)

    def test_character_index_accepts_decoded_radiant_dawn_tables(self):
        from fe_modding import project_index

        self.assertTrue(project_index.supported(self.project))

    def test_game_data_session_is_unavailable_with_a_reason(self):
        from fe_modding.gui.changelog import ChangeLog
        from fe_modding.gui.fe8_session import Fe8DataSession

        session = Fe8DataSession(self.project, ChangeLog(self.project))
        self.assertFalse(session.available)
        self.assertIn("not available for Radiant Dawn yet", session.unavailable_reason)
        self.assertEqual(session.file_label, "FE10Data.cms")

    def test_radiant_dawn_session_uses_fe10data_not_the_leftover_fe8_file(self):
        from fe_modding.gui.changelog import ChangeLog
        from fe_modding.gui.fe8_session import Fe10DataSession

        session = Fe10DataSession(self.project, ChangeLog(self.project))
        self.assertFalse(session.available)
        self.assertIn("FE10Data.cms not found", session.unavailable_reason)
        self.assertIsNone(session.fe8)

    def test_radiant_dawn_gets_the_tables_only_game_data(self):
        from fe_modding.game_profile import DATA_TABLES, GAME_DATA

        self.assertTrue(self.project.profile.supports(DATA_TABLES))
        self.assertFalse(self.project.profile.supports(GAME_DATA))

    def test_both_games_use_the_shared_game_data_page_owner(self):
        from fe_modding.gui.pages import data

        sentinel = object()
        shell = SimpleNamespace(project=self.project)
        with patch.object(data, "GameDataPage", return_value=sentinel) as page:
            self.assertIs(data.game_data_page(shell), sentinel)
        page.assert_called_once_with(shell)
        self.assertFalse(any("characters" in keys for _heading, keys in data.FE10_SECTIONS))

    def test_phase_two_to_four_routes_keep_shared_surface_owners(self):
        from fe_modding.gui.cp_data_editor import CpDataPanel
        from fe_modding.gui.dialogue_editor import DialogueEditor
        from fe_modding.gui.font_viewer import FontViewer
        from fe_modding.gui.pages import data
        from fe_modding.gui.pages.assets import TOOLS_BY_KEY
        from fe_modding.gui.pages.flags import FlagsPanel
        from fe_modding.gui.pages import text_assets
        from fe_modding.gui.pages.text_assets import ConversationsPanel, ScriptsPanel
        from fe_modding.gui.script_editor import ScriptEditor

        self.assertIs(TOOLS_BY_KEY["conversations"][4], ConversationsPanel)
        self.assertIs(TOOLS_BY_KEY["scripts"][4], ScriptsPanel)
        self.assertIs(TOOLS_BY_KEY["fonts"][4], FontViewer)
        self.assertIs(text_assets.DialogueEditor, DialogueEditor)
        self.assertIs(text_assets.ScriptEditor, ScriptEditor)
        self.assertIs(data.FlagsPanel, FlagsPanel)
        self.assertIs(data.CpDataPanel, CpDataPanel)
        self.assertFalse(hasattr(data, "Fe10GameDataPage"))

    def test_animation_data_route_uses_the_shared_viewer(self):
        from fe_modding.gui.animation_data_viewer import AnimationDataViewer
        from fe_modding.gui.pages.assets import TOOLS_BY_KEY

        self.assertIs(TOOLS_BY_KEY["animation_data"][4], AnimationDataViewer)

    def test_phase_seven_routes_use_shared_editors_and_rd_gates(self):
        from fe_modding.game_profile import AUDIO, VIDEO
        from fe_modding.gui.music_editor import MusicEditor
        from fe_modding.gui.pages.assets import ASSET_FEATURES, TOOLS_BY_KEY
        from fe_modding.gui.sfx_viewer import SfxViewer
        from fe_modding.gui.soundroom_editor import SoundRoomEditor
        from fe_modding.gui.soundroom_tracks_editor import SoundRoomTracksEditor
        from fe_modding.gui.video_viewer import VideoViewer

        expected = {
            "music": (MusicEditor, AUDIO),
            "sfx": (SfxViewer, AUDIO),
            "sound_room": (SoundRoomEditor, AUDIO),
            "sound_room_tracks": (SoundRoomTracksEditor, AUDIO),
            "videos": (VideoViewer, VIDEO),
        }
        for key, (owner, feature) in expected.items():
            self.assertIs(TOOLS_BY_KEY[key][4], owner)
            self.assertEqual(ASSET_FEATURES[key], feature)
            self.assertTrue(self.project.profile.supports(feature))

    def test_model_slots_refuse_the_other_games_battle_and_anim_files(self):
        from fe_modding import model_slots
        from fe_modding.exceptions import ProjectError

        for name in ("battle_data", "anim_data", "game_data"):
            with self.assertRaises(ProjectError) as caught:
                model_slots._logical(self.project, name)
            self.assertIn("not available for Radiant Dawn yet", str(caught.exception))

    def test_play_in_dolphin_is_enabled_and_reports_missing_game_data(self):
        from fe_modding import emulator
        from fe_modding.game_profile import PLAY

        root = self.project.extracted_dir
        _boot(root, b"RFEE01")
        (root / "sys" / "main.dol").write_bytes(b"x")
        self.assertTrue(self.project.profile.supports(PLAY))
        with self.assertRaises(emulator.EmulatorError) as caught:
            emulator.prepare_chapter_run(root, Path(self._tmp.name) / "run", 1, 0)
        self.assertIn("FE10Data.cms could not be read", str(caught.exception))

    def test_chapter_listing_uses_the_radiant_dawn_scheme(self):
        from fe_modding import chapters

        mess = self.project.files_dir / "Mess"
        mess.mkdir(parents=True)
        for name in ("c0102", "c0101", "c0407a", "cfinal", "common", "e_c0101", "c0000"):
            (mess / f"{name}.m").write_bytes(b"")
        self.assertEqual(chapters.list_chapter_ids(self.project), ["0000", "0101", "0102", "0407a", "final"])

    def test_scripts_load_and_save_in_the_radiant_dawn_dialect(self):
        from fe_modding import script_sources
        from fe_modding.formats.cmb import compile_source, read_cmb, write_cmb
        from fe_modding.formats.cmb.model import FE10

        scripts = self.project.files_dir / "Scripts"
        scripts.mkdir(parents=True)
        path = scripts / "C0101.cmb"
        path.write_bytes(write_cmb(compile_source("def f(a):\n    a = 1\n    return 0\n", dialect=FE10).script))
        self.assertEqual(script_sources.chapter_script(self.project, "0101"), path)
        loaded = script_sources.load(self.project, path)
        self.assertIn("    arg0 = 1\n", loaded.source)
        script_sources.save(self.project, loaded, loaded.source.replace("arg0 = 1", "arg0 += 2"))
        self.assertIs(read_cmb(path.read_bytes()).dialect, FE10)
        self.assertIn("arg0 += 2", script_sources.peek(self.project, path))

    def test_asset_lists_group_files_by_radiant_dawn_chapter(self):
        from fe_modding.gui.pages import text_assets

        files = self.project.files_dir
        (files / "Mess").mkdir(parents=True)
        (files / "Scripts").mkdir()
        for name in ("c0102", "c0101", "c0407a", "common", "e_c0101"):
            (files / "Mess" / f"{name}.m").write_bytes(b"")
        for name in ("C0407a", "C0101", "startup", "CFINAL"):
            (files / "Scripts" / f"{name}.cmb").write_bytes(b"")
        self.assertEqual([(p.name, c) for p, c in text_assets.message_files(self.project)],
                         [("c0101.m", "0101"), ("c0102.m", "0102"), ("c0407a.m", "0407a"),
                          ("common.m", None), ("e_c0101.m", None)])
        self.assertEqual([(p.name, c) for p, c in text_assets.script_files(self.project)],
                         [("C0101.cmb", "0101"), ("C0407a.cmb", "0407a"), ("startup.cmb", None),
                          ("CFINAL.cmb", None)])

    def test_asset_tools_without_a_decoder_are_listed_for_gating(self):
        from fe_modding.gui.pages.assets import ASSET_FEATURES, TOOLS_BY_KEY
        from fe_modding.game_profile import (
            AUDIO, BATTLE_CAMERAS, BATTLE_DATA, BATTLE_SIM, CHAPTERS, EFFECTS, ICONS, MODELS, VIDEO,
            PATH_OF_RADIANCE_PROFILE, RADIANT_DAWN_PROFILE,
        )

        self.assertTrue(set(ASSET_FEATURES) <= set(TOOLS_BY_KEY))
        for key, feature in ASSET_FEATURES.items():
            self.assertTrue(PATH_OF_RADIANCE_PROFILE.supports(feature), key)
            # Phase 5 maps and Phase 6 icons/models/effects use shared browsers. Unsafe RD model
            # and effect mutation remains locked inside the individual viewers.
            if feature not in (AUDIO, BATTLE_CAMERAS, BATTLE_DATA, BATTLE_SIM, CHAPTERS, EFFECTS,
                                ICONS, MODELS, VIDEO):
                self.assertFalse(RADIANT_DAWN_PROFILE.supports(feature), key)


if __name__ == "__main__":
    unittest.main()
