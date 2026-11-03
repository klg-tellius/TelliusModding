import unittest

try:
    from fe_modding.gui.dialogue_editor import DialogueEditor
except Exception:  # noqa: BLE001 - needs Tkinter
    DialogueEditor = None


@unittest.skipIf(DialogueEditor is None, "Tkinter is unavailable")
class ChapterExportTests(unittest.TestCase):
    def test_blocks_keep_their_lines(self):
        text = "# Tellius dialogue export: c05.m\n=== MS_A ===\nhello\n<Wait>\n\n=== MS_B ===\nbye\n"
        self.assertEqual(DialogueEditor.parse_chapter_export(text), [("MS_A", "hello\n<Wait>"), ("MS_B", "bye")])

    def test_text_before_the_first_id_is_refused(self):
        with self.assertRaises(ValueError):
            DialogueEditor.parse_chapter_export("stray\n=== MS_A ===\nhi")


if __name__ == "__main__":
    unittest.main()
