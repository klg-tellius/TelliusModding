"""Radiant Dawn conversation preview pieces: frames, balloon geometry, rect layouts, faces, fonts.

Corpus tests need ``FE10_EXTRACTED_FILES`` / ``FE10_EXTRACTED`` (see test_fe10_corpus.py)."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import fe10_conversation, fe10_message, fe10_rect


def _files() -> Path | None:
    value = os.environ.get("FE10_EXTRACTED_FILES")
    if value:
        return Path(value)
    root = os.environ.get("FE10_EXTRACTED")
    return Path(root) / "files" if root else None


FILES = _files()


def raw(display: str) -> str:
    return fe10_message.to_raw(display)


class FramesTest(unittest.TestCase):
    def test_one_frame_per_wait_plus_the_end(self):
        text = raw("<FL|LEONARDO|MICAIAH><R:上下会話><speaker:00><show:0D>Micaiah!<wait>\n"
                   "<speaker:11><show:1D>Leonardo!<w4> How?<wait>")
        frames = fe10_conversation.build_frames(text)
        self.assertEqual([f.kind for f in frames], ["wait", "wait", "end"])
        first, second = frames[0], frames[1]
        self.assertEqual(first.layout, "上下会話")
        self.assertEqual([(a.name, a.position, a.visible) for a in first.actors], [("LEONARDO", 0, True)])
        self.assertEqual([(b.position, b.speaker, b.text) for b in first.boxes], [(0, 0, "Micaiah!")])
        self.assertEqual([(b.position, b.speaker) for b in second.boxes], [(0, 0), (1, 1)])
        self.assertEqual(second.boxes[1].text, "Leonardo! How?")  # pauses are not text
        display = fe10_message.to_display(text)
        self.assertEqual(first.offset, display.index("<wait>") + len("<wait>"))
        self.assertEqual(fe10_conversation.frame_before(frames, 0), 0)
        self.assertEqual(fe10_conversation.frame_before(frames, len(display)), 1)  # the last <wait> ends the text

    def test_speaker_change_clears_the_box_and_page_clears_it(self):
        text = raw("<FL|A|B><R:背景会話><speaker:01>One<wait>\n<speaker:11>Two<wait><page>More<wait>")
        frames = fe10_conversation.build_frames(text)
        self.assertEqual(frames[0].boxes[0].text, "One")
        self.assertEqual(frames[1].boxes[0].text, "Two")
        self.assertEqual(frames[2].boxes[0].text, "More")

    def test_hide_removes_the_actor_and_its_box(self):
        text = raw("<FL|A><R:上下会話><speaker:00><show:0D>Hi<wait><hide><H>")
        frames = fe10_conversation.build_frames(text)
        self.assertEqual(frames[-2].kind, "suspend")
        self.assertFalse(frames[-1].actors[0].visible)
        self.assertEqual(frames[-1].boxes, ())


class BalloonTest(unittest.TestCase):
    def test_width_rounds_to_tiles_and_clamps(self):
        self.assertEqual(fe10_rect.balloon(0, 0)["width"], 0x150)        # minimum 336
        self.assertEqual(fe10_rect.balloon(0, 200)["width"], 432)        # 200 + 224 -> 9 tiles
        self.assertEqual(fe10_rect.balloon(0, 1000)["width"], 0x240)     # maximum 576
        self.assertEqual(fe10_rect.balloon(0, 200, no_portrait=True)["width"], 336)

    def test_positions_match_the_engine_table(self):
        top_left = fe10_rect.balloon(0, 200)
        self.assertEqual(top_left["box"], (16, 20))
        self.assertEqual(top_left["text"], (192, 32))
        self.assertEqual(top_left["anchor"], (112, 130))
        bottom_right = fe10_rect.balloon(1, 200)
        self.assertEqual(bottom_right["box"], (0x250 - 432, 316))
        self.assertEqual(bottom_right["anchor"], (496, 426))  # the 上下会話 seat 1 is (496, 427)
        for position in range(8):
            self.assertIn("cursor", fe10_rect.balloon(position, 100))
        with self.assertRaises(ValueError):
            fe10_rect.balloon(8, 100)


class ProfileFontsTest(unittest.TestCase):
    def test_radiant_dawn_lists_its_eleven_fonts(self):
        from fe_modding.game_profile import FONTS, PATH_OF_RADIANCE_PROFILE, RADIANT_DAWN_PROFILE

        self.assertTrue(RADIANT_DAWN_PROFILE.supports(FONTS))
        names = [name for name, _ in RADIANT_DAWN_PROFILE.font_files]
        self.assertEqual(names[:6], ["system", "system_w", "fe_font", "fe_font_w", "talk", "talk_w"])
        self.assertEqual(len(names), 11)
        self.assertTrue(all(path.endswith(".cms") for _, path in RADIANT_DAWN_PROFILE.font_files))
        self.assertEqual(len(PATH_OF_RADIANCE_PROFILE.font_files), 5)
        self.assertEqual(RADIANT_DAWN_PROFILE.message_dialect, "fe10")


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to the files/ folder of an extracted Radiant Dawn disc")
class CorpusTest(unittest.TestCase):
    def test_layouts_have_textboxes_and_seats(self):
        layouts = fe10_rect.read_rect_path(FILES / "window" / "RectDesc_en.bin")
        two_box = layouts["RID_上下会話"]
        boxes = two_box.textboxes()
        self.assertEqual([b.position for b in boxes], list(range(8)))
        self.assertEqual((boxes[0].line_height, boxes[0].lines), (28, 3))
        self.assertEqual(boxes[0].cursor, "RID_PAGECUR")
        seats = two_box.seats()
        self.assertEqual((seats[0].x, seats[0].y, seats[0].facing), (112, 131, 1))
        self.assertEqual((seats[1].x, seats[1].y, seats[1].facing), (496, 427, 0))
        scene = layouts["RID_背景会話"]
        self.assertEqual(scene.textboxes()[0].position, -1)
        self.assertEqual(scene.textboxes()[0].window, "RID_TW")
        self.assertEqual(len(scene.seats()), 9)
        base = fe10_rect.read_rect_path(FILES / "window" / "RectBase_en.bin")
        for name in fe10_message.LAYOUT_NAMES:
            self.assertTrue("RID_" + name in layouts or "RID_" + name in base, name)

    def test_backgrounds_resolve_to_textures(self):
        backgrounds = fe10_rect.read_rect_path(FILES / "s" / "rect.bin")
        self.assertGreater(len(backgrounds), 400)
        quad = backgrounds["RID_デイン-路地-昼"].quads()[0]
        self.assertEqual(quad.file, "s/fur")
        self.assertTrue((FILES / quad.file).is_file())

    def test_faces_compose_and_the_cut_in_is_a_crop_of_the_body(self):
        import numpy as np

        from fe_modding.formats.fe10_faces import CUT_IN, FaceLibrary

        library = FaceLibrary(FILES)
        self.assertEqual(len(library.records), 316)
        record, large = library.lookup("IKE")
        self.assertFalse(large)
        self.assertEqual(record.filename, "IKE.cms")
        self.assertEqual(record.cut_in_origin, (83, 78))
        self.assertTrue(library.lookup("L_IKE")[1])
        images = library.images(record)
        x, y = record.cut_in_origin
        body = np.asarray(images[1])[y:y + 128, x:x + 192]
        cut = np.asarray(images[CUT_IN])
        opaque = (body[..., 3] > 200) & (cut[..., 3] > 200)
        self.assertTrue(np.array_equal(body[opaque], cut[opaque]))
        self.assertEqual(library.compose("L_IKE").size, (336, 336))
        self.assertEqual(library.compose("IKE").size, (192, 128))
        self.assertIsNone(library.compose("NOBODY_AT_ALL"))

    def test_every_chapter_conversation_builds_frames_and_renders(self):
        from fe_modding.formats import message
        from fe_modding.formats.fe10_conversation_render import Fe10ConversationAssets, render

        assets = Fe10ConversationAssets(FILES)
        messages = message.read_messages_path(FILES / "Mess" / "e_c0101.m")
        for msg in messages:
            frames = fe10_conversation.build_frames(msg.text)
            with self.subTest(id=msg.speaker):
                self.assertEqual(frames[-1].kind, "end")
                image = render(frames[0], assets)
                self.assertEqual(image.size, (640, 480))
        self.assertEqual(assets.character_name("L_EDDIE"), "Edward")

    def test_fonts_rebuild_with_the_same_glyphs(self):
        from fe_modding.formats import fe9_font, lz10
        from fe_modding.game_profile import RADIANT_DAWN_PROFILE

        for name, rel in RADIANT_DAWN_PROFILE.font_files:
            data = lz10.decompress((FILES / rel).read_bytes())
            font = fe9_font.GameFont(data)
            rebuilt = fe9_font.GameFont(fe9_font.rebuild(font))
            with self.subTest(font=name):
                self.assertEqual(set(font.glyphs), set(rebuilt.glyphs))
                self.assertEqual((font.ascent, font.descent), (rebuilt.ascent, rebuilt.descent))


if __name__ == "__main__":
    unittest.main()
