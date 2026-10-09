import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fe_modding.formats import dialogue_notation as n, fe10_message as rd
from fe_modding.formats import fe9_message_scene as ms
from fe_modding.formats.message import Message


class NotationTests(unittest.TestCase):
    def test_fe9_templates_round_trip(self):
        for raw in ms.TEMPLATES.values():
            with self.subTest(raw=raw):
                self.assertEqual(n.parse(n.display(raw).text).raw, raw)

    def test_fe10_templates_round_trip(self):
        for source in rd.TEMPLATES.values():
            raw = rd.to_raw(source)
            with self.subTest(source=source):
                self.assertEqual(n.parse(n.display(raw, True).text, True).raw, raw)

    def test_every_fe9_action_round_trips(self):
        raw = ms.to_raw('$R背景会話|$B村-崖|$<$F1$FCL_TIAMAT|$F1$PHello.$w4世界$K\n'
                        '$F3$FD$Fc$Fh$Fo$Fd$Ff$Fs$FS$FA$c0IKE|$s0$d0$W1$W-$W+$WD'
                        '$ND$MC$MD$N$O3$G$Y$SD$SE$DC$Ub$UB$H$=9999$>$C|#C22#c$Q')
        shown = n.display(raw)
        self.assertIn('<Seat:1>', shown.text)
        self.assertIn('<Portrait:L_TIAMAT>', shown.text)
        self.assertIn('世界', shown.text)
        self.assertEqual(n.parse(shown.text).raw, raw)

    def test_all_fe10_catalogue_actions_round_trip(self):
        for key in rd.COMMANDS:
            with self.subTest(key=key):
                raw = rd.to_raw(rd.new_step(key).display)
                self.assertEqual(n.parse(n.display(raw, True).text, True).raw, raw)

    def test_fe10_rejects_invalid_actor_and_facing(self):
        for source in ('<Speaker:ZZ>', '<Show portrait:0X>', '<Pause power:99>'):
            with self.subTest(source=source), self.assertRaises(n.NotationError):
                n.parse(source, True)

    def test_mapping_tracks_multibyte_text_and_commands(self):
        doc = n.parse('<Seat:2>日<Wait>')
        self.assertEqual(doc.at_byte(0).start, 0)
        self.assertEqual(doc.at_byte(2).end, len('<Seat:2>'))
        self.assertEqual(doc.at_byte(3), doc.at_byte(4))
        self.assertEqual(doc.text[doc.at_byte(5).start:doc.at_byte(5).end], '<Wait>')
        self.assertEqual(doc.byte_at(len(doc.text)), len(doc.raw))

    def test_fe10_mapping_tracks_bytes_not_notation(self):
        doc = n.parse('<Speaker:04>日<Wait>', True)
        self.assertEqual(doc.raw, rd.to_raw('<speaker:04>日<wait>'))
        self.assertEqual(doc.text[doc.at_byte(5).start:doc.at_byte(5).end], '<Wait>')

    def test_reserved_characters_and_unknown_commands(self):
        raw = ms.to_raw('a < b > c $Q#C22')
        self.assertEqual(n.parse(n.display(raw).text).raw, raw)
        raw = ms.to_raw('$Bfoo<&bar>|')
        self.assertEqual(n.parse(n.display(raw).text).raw, raw)

    def test_invalid_drafts_report_positions(self):
        for text in ('hello\n<Wait', '<Unknown>', '<Seat:9>', '<Box:4>', '<Wait:1>', '<Bytes:00>', '<Layout:a|b>'):
            with self.subTest(text=text), self.assertRaises(n.NotationError):
                n.parse(text)
        try:
            n.parse('hello\n<Unknown>')
        except n.NotationError as error:
            self.assertIn('Line 2, column 1', str(error))
            self.assertEqual(error.start, 6)

    def test_malformed_byte_preservation(self):
        for data in (b'\xff', b'\x81', b'$R\xff|', b'$Q', b'#'):
            raw = data.decode('cp437')
            with self.subTest(data=data):
                self.assertEqual(n.display(raw).raw, raw)


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except tk.TclError as error:
            raise unittest.SkipTest(str(error))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        from tkinter import ttk
        from fe_modding.gui.dialogue_editor import DialogueEditor
        from fe_modding.project import ModProject
        from fe_modding.games import Game
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        project = ModProject('Test', Game.PATH_OF_RADIANCE, Path(self.temp.name))
        class Preview(ttk.Frame):
            def __init__(self, parent, project):
                super().__init__(parent)
            assets = None
            def update_message(self, *args, **kwargs):
                self.last = args
            def set_inheritance_source(self, *args):
                pass
            def cleanup(self):
                pass
        with patch('fe_modding.gui.dialogue_editor.ConversationPreview', Preview):
            self.editor = DialogueEditor(self.root, project, Mock())
        self.addCleanup(self.editor.destroy)
        self.addCleanup(self.editor.cleanup)
        self.editor._current_path = Path(self.temp.name) / 'files' / 'Mess' / 'c01.m'
        self.editor._messages = [Message('MS_A', ms.to_raw('$F1$P日Hello$K')), Message('MS_B', 'second')]
        self.editor._select_index(0)
        self.root.update()

    def test_editor_has_action_tags_seats_and_playback_mapping(self):
        editor = self.editor
        self.assertIsNotNone(editor._scene)
        self.assertTrue(editor._text_widget.tag_ranges('action'))
        editor._highlight_playback_position(5, 'text')
        span = editor._document.at_byte(5)
        start, end = editor._text_widget.tag_ranges('playback_position')
        self.assertEqual(editor._text_widget.get(start, end), editor._document.text[span.start:span.end])
        editor._highlight_playback_position(0, 'command')
        self.assertEqual(editor._text_widget.get(*editor._text_widget.tag_ranges('playback_position')), '<Seat:1>')

    def test_insert_undo_redo_and_seat_actions(self):
        editor = self.editor
        before = editor._text_widget.get('1.0', 'end-1c')
        editor._text_widget.mark_set('insert', 'end-1c')
        editor._scene.insert_steps([ms.new_step('select_seat', seat=2)])
        editor._flush_edit()
        self.assertTrue(editor._messages[0].text.endswith('$F2'))
        editor._text_widget.edit_undo()
        editor._flush_edit()
        self.assertEqual(editor._text_widget.get('1.0', 'end-1c'), before)
        editor._text_widget.edit_redo()
        editor._flush_edit()
        self.assertTrue(editor._messages[0].text.endswith('$F2'))

    def test_invalid_draft_survives_switch_and_blocks_save(self):
        editor = self.editor
        original = editor._messages[0].text
        editor._replace_selection('hello <Unknown>', whole=True)
        self.assertEqual(editor._messages[0].text, original)
        self.assertIsNone(editor._document)
        editor._select_index(1)
        editor._select_index(0)
        self.assertEqual(editor._text_widget.get('1.0', 'end-1c'), 'hello <Unknown>')
        with patch('fe_modding.gui.dialogue_editor.messagebox.showerror') as error, patch('fe_modding.gui.dialogue_editor.message.write_messages_path') as write:
            editor._save()
            error.assert_called_once()
            write.assert_not_called()
        editor._replace_selection('fixed<Wait>', whole=True)
        self.assertFalse(editor._drafts)
        self.assertEqual(editor._messages[0].text, 'fixed$K')

    def test_playback_preserves_selection_cursor_and_undo_state(self):
        editor = self.editor
        editor._text_widget.mark_set('insert', '1.3')
        editor._text_widget.tag_add('sel', '1.0', '1.2')
        before = editor._text_widget.get('1.0', 'end-1c')
        editor._text_widget.edit_modified(False)
        editor._highlight_playback_position(3, 'command')
        self.assertEqual(editor._text_widget.index('insert'), '1.3')
        self.assertEqual(tuple(map(str, editor._text_widget.tag_ranges('sel'))), ('1.0', '1.2'))
        self.assertFalse(editor._text_widget.edit_modified())
        self.assertEqual(editor._text_widget.get('1.0', 'end-1c'), before)
        self.assertFalse([tag for tag in editor._text_widget.tag_names() if tag.startswith('action_frame_')])

    def test_fe10_preview_reports_byte_offsets(self):
        from fe_modding.gui.fe10_conversation_preview import Fe10ConversationPreview
        with patch.object(Fe10ConversationPreview, '_schedule'):
            preview = Fe10ConversationPreview(self.root, self.editor._project)
            self.addCleanup(preview.destroy)
            raw = rd.to_raw('<speaker:04>日Hello<wait><speaker:14>Bye<wait>')
            preview.update_message('MS_TEST', raw)
            positions = []
            preview.on_position = lambda offset, kind: positions.append(offset)
            preview._show(0)
            self.assertEqual(positions[-1], raw.index(chr(0x11)))
            preview._show(1)
            self.assertEqual(positions[-1], raw.rindex(chr(0x11)))
            doc = n.display(raw, True)
            span = doc.at_byte(positions[-1])
            self.assertEqual(doc.text[span.start:span.end], '<Wait>')

    def test_import_export_and_undo(self):
        editor = self.editor
        source = Path(self.temp.name) / 'source.txt'
        target = Path(self.temp.name) / 'export.txt'
        source.write_text('<Seat:2>Hello<Wait>', encoding='utf-8')
        before = editor._text_widget.get('1.0', 'end-1c')
        with patch('fe_modding.gui.dialogue_editor.filedialog.askopenfilename', return_value=str(source)), patch('fe_modding.gui.dialogue_editor.messagebox.askyesnocancel', return_value=True):
            editor._import_text()
        self.assertEqual(editor._messages[0].text, '$F2Hello$K')
        with patch('fe_modding.gui.dialogue_editor.filedialog.asksaveasfilename', return_value=str(target)):
            editor._export_text()
        self.assertEqual(target.read_text(encoding='utf-8'), source.read_text(encoding='utf-8'))
        editor._text_widget.edit_undo()
        editor._flush_edit()
        self.assertEqual(editor._text_widget.get('1.0', 'end-1c'), before)


if __name__ == '__main__':
    unittest.main()
