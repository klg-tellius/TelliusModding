"""Message creation used by game-data text selectors."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from fe_modding.formats import message
from fe_modding.game_profile import PATH_OF_RADIANCE_PROFILE, RADIANT_DAWN_PROFILE
from fe_modding.gui import message_reference as refs


class _Project:
    def __init__(self, root: Path, profile):
        self.extracted_dir = root / "extracted"
        self.profile = profile
        self.written = []

    def write_keeping_original(self, path, data):
        self.written.append(Path(path))
        Path(path).write_bytes(data)


class MessageReferenceTests(unittest.TestCase):
    def test_fe9_create_and_preserve_existing_messages(self):
        with TemporaryDirectory() as tmp:
            project = _Project(Path(tmp), PATH_OF_RADIANCE_PROFILE)
            path = project.extracted_dir / "files" / "Mess" / "common.m"
            path.parent.mkdir(parents=True)
            path.write_bytes(message.write_messages([message.Message("MIID_OLD", "Old item")]))
            refs.create_message(project, "MIID_NEW", "New item")
            self.assertEqual({m.speaker: m.text for m in message.read_messages_path(path)},
                             {"MIID_OLD": "Old item", "MIID_NEW": "New item"})
            self.assertEqual(project.written, [path])
            self.assertEqual(refs.message_texts(project)["MIID_NEW"], "New item")
            with self.assertRaisesRegex(ValueError, "already exists"):
                refs.create_message(project, "MIID_NEW", "Another item")

    def test_fe10_uses_english_common_file(self):
        with TemporaryDirectory() as tmp:
            project = _Project(Path(tmp), RADIANT_DAWN_PROFILE)
            folder = project.extracted_dir / "files" / "Mess"
            folder.mkdir(parents=True)
            (folder / "common.m").write_bytes(message.write_messages([message.Message("MIID_OLD", "Old")]))
            english = folder / "e_common.m"
            english.write_bytes(message.write_messages([message.Message("MIID_OLD", "Old")]))
            refs.create_message(project, "MIID_NEW", "New item")
            self.assertEqual(project.written, [english])
            self.assertEqual(refs.message_texts(project)["MIID_NEW"], "New item")
            self.assertEqual(len(message.read_messages_path(folder / "common.m")), 1)

    def test_suggested_ids_are_unique(self):
        self.assertEqual(refs.suggested_id("MIID_", "Iron Sword", {"MIID_IRON_SWORD"}),
                         "MIID_IRON_SWORD_2")


if __name__ == "__main__":
    unittest.main()
