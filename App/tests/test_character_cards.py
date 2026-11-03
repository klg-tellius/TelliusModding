import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.gui.pages.characters import _card_subtitle, _matches_filter
from fe_modding.gui.widgets import _square_thumbnail
from fe_modding.formats import fe10_message
from fe_modding.project_index import GENERIC, NAMED, _fe10_message_cast_hits, _fe10_playable_name_keys


class CharacterFilterTests(unittest.TestCase):
    def character(self, category=NAMED):
        return SimpleNamespace(category=category, name="Ike", pid="PID_IKE",
                               variants=("PID_IKE_EVENT",), class_name="Hero")

    def test_search_still_respects_selected_category(self):
        self.assertFalse(_matches_filter(self.character(NAMED), GENERIC, ["ike"]))
        self.assertTrue(_matches_filter(self.character(NAMED), NAMED, ["ike"]))

    def test_search_matches_name_pid_variant_and_class(self):
        character = self.character()
        for word in ("ike", "pid_ike", "event", "hero"):
            self.assertTrue(_matches_filter(character, "all", [word]))
        self.assertFalse(_matches_filter(character, "all", ["mist"]))

    def test_tile_shows_only_current_class(self):
        character = SimpleNamespace(class_name="Hero", jid="JID_HERO",
                                    promoted_class_name="Vanguard")
        self.assertEqual(_card_subtitle(character), "Hero")


class RadiantDawnCategoryTests(unittest.TestCase):
    def test_support_roster_marks_every_variant_name_group_playable(self):
        characters = [
            SimpleNamespace(values={"pid": "PID_IKE", "mpid": "MPID_IKE"}),
            SimpleNamespace(values={"pid": "PID_IKE_EVENT", "mpid": "MPID_IKE"}),
            SimpleNamespace(values={"pid": "PID_BLACKKNIGHT", "mpid": "MPID_BLACKKNIGHT"}),
        ]
        supports = [SimpleNamespace(values={"pid": "PID_IKE"})]

        self.assertEqual(_fe10_playable_name_keys(characters, supports), {"MPID_IKE"})

    def test_message_cast_tracks_speakers_and_shown_portraits(self):
        text = fe10_message.to_raw(
            "<FL|IKE|MICAIAH><seat:00><show:0D><speaker:11>Words.<wait>")

        self.assertEqual(_fe10_message_cast_hits(text), {"IKE": "portrait", "MICAIAH": "speaker"})


class RadiantDawnThumbnailTests(unittest.TestCase):
    def test_wide_portrait_is_cropped_equally_from_both_sides(self):
        image = Image.new("RGBA", (6, 4), "black")
        for x in range(6):
            for y in range(4):
                image.putpixel((x, y), (x * 40, 0, 0, 255))

        thumbnail = _square_thumbnail(image, 4)

        self.assertEqual(thumbnail.size, (4, 4))
        self.assertEqual(thumbnail.getpixel((0, 0))[0], 40)
        self.assertEqual(thumbnail.getpixel((3, 0))[0], 160)


if __name__ == "__main__":
    unittest.main()
