import os
import struct
import sys
import unittest
from pathlib import Path
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fe_modding.formats.fe9_conversation import InitialContext, build_timeline, tokenize
from fe_modding.formats.fe9_portraits import FaceAsset, FaceRecord, read_face_table
from fe_modding.formats.fe9_font import GameFont
from fe_modding.formats.fe9_conversation_assets import ConversationAssets, read_rect_resources
from fe_modding.formats.fe9_conversation_render import ConversationRenderer
from fe_modding.formats.fe9_conversation_context import resolve_context
from fe_modding.formats.message import read_messages_path


class FaceTableTests(unittest.TestCase):
    def table(self):
        # Actual relocatable format: count, body-relative record pointer, 32-byte
        # records, strings, relocation offsets. This is deliberately not FDAT.
        body = bytearray(40)
        struct.pack_into('>II', body, 0, 1, 8)
        for offset, value in zip((8,12,16), (b'FID_TEST',b'MPID_TEST',b'TEST.cms')):
            struct.pack_into('>I', body, offset, len(body))
            body.extend(value+b'\0')
        struct.pack_into('>6hHHBBh', body, 20, 1,2, 7,2, 4,7, 3,0xffff,1,54,-3)
        reloc = len(body)
        body.extend(struct.pack('>4I',4,8,12,16))
        return struct.pack('>8I',32+len(body),reloc,4,0,0,0,0,0)+body

    def test_real_record_offsets(self):
        record = read_face_table(self.table())['FID_TEST']
        self.assertEqual(record.filename,'TEST.cms')
        self.assertEqual(record.left_eye,(1,2))
        self.assertEqual(record.right_eye,(7,2))
        self.assertEqual(record.mouth,(4,7))
        self.assertEqual(record.depth,54)
        self.assertEqual(record.mini_portrait,0xffff)
        self.assertEqual(record.menu_offset,-3)

    def test_malformed_record_rejected(self):
        data = bytearray(self.table())
        struct.pack_into('>I',data,36,0xffffff00)
        with self.assertRaises(ValueError): read_face_table(data)
        with self.assertRaises(ValueError): read_face_table(b'FDAT'+bytes(80))

    def test_texture_identity_and_mirroring(self):
        rec = read_face_table(self.table())['FID_TEST']
        images = (Image.new('RGBA',(12,12)),) + tuple(Image.new('RGBA',(2,2),(i,0,0,255)) for i in range(1,13))
        asset = FaceAsset(rec,images)
        out = asset.compose(mouth_variant=1,left_eye_frame=1,right_eye_frame=2)
        self.assertEqual(out.getpixel((4,7))[0],6)
        self.assertEqual(out.getpixel((1,2))[0],8)
        self.assertEqual(out.getpixel((7,2))[0],12)
        self.assertEqual(asset.compose(mouth_variant=1,left_eye_frame=1,right_eye_frame=2,mirrored=True).tobytes(),ImageOps.mirror(out).tobytes())
        with self.assertRaises(ValueError): FaceAsset(rec,images[:5]).compose(mouth_variant=1)


class TimelineTests(unittest.TestCase):
    def test_large_small_and_inline_load(self):
        timeline = build_timeline('$F0$FCL_IKE|$c1MIST|Hi$K')
        scene = timeline.events[-1].state
        self.assertEqual(scene.portraits[0].fid,'FID_L_IKE')
        self.assertEqual(scene.portraits[1].fid,'FID_MIST')
        self.assertEqual(scene.boxes[1].text,'Hi')

    def test_context_alias_and_no_silent_fallback(self):
        self.assertIn('needs a character alias',build_timeline('$FCLME|').diagnostics[0].description)
        t = build_timeline('$FCLME|',context=InitialContext(aliases=(('LME','L_MIST'),)))
        self.assertEqual(t.events[-1].state.portraits[0].fid,'FID_L_MIST')
        self.assertFalse(t.diagnostics)

    def test_same_timestamp_input_waits_are_not_skipped(self):
        t = build_timeline('$F0$FA$K$FS$K',context=InitialContext(portraits=('IKE',)+('',)*8))
        a = t.advance(0,0)
        self.assertTrue(t.events[a].wait)
        self.assertEqual(t.events[a].state.portraits[0].mouth,1)
        # The command after an input wait runs on the next text tick, not at the same time.
        self.assertEqual(t.advance(a,0),a)
        b = t.advance(a,t.duration_ms)
        self.assertGreater(b,a)
        self.assertEqual(t.events[b].state.portraits[0].mouth,0)
        self.assertTrue(t.events[b].wait)

    def test_exponential_frame_wait(self):
        # $wN blocks 2^N frames, then the rest of the 4-frame Normal text tick: 16+4, then +4 after
        # the input wait, then 8+4 frames.
        t = build_timeline('$w4$K$w3$K')
        self.assertEqual([e.time_ms for e in t.events if e.wait],[333,600])
        slow = build_timeline('ab$K',text_speed='slow')
        self.assertEqual(next(e for e in slow.events if e.wait).time_ms,333)  # 2 glyphs x 10 frames
        fast = build_timeline('ab$Y$K',text_speed='max')
        self.assertEqual(next(e for e in fast.events if e.wait).time_ms,17)  # $Y ends the frame's tick
        with self.assertRaises(ValueError): build_timeline('',text_speed='turbo')

    def test_independent_boxes_and_deferred_scroll(self):
        t = build_timeline('$c0MIST|one\ntwo\nthree$K\n$c1IKE|yes$K$d0')
        wait = [e for e in t.events if e.wait][-1]
        self.assertEqual(wait.state.boxes[0].text.rstrip(),'one\ntwo\nthree')
        self.assertEqual(wait.state.boxes[1].text,'yes')
        self.assertFalse(t.events[-1].state.boxes[0].visible)
        self.assertEqual(t.events[-1].state.portraits[0].fid,'')

    def test_expression_and_event_resume(self):
        t = build_timeline('$F0$FS$FCIKE|$Fc$MC...$H$Fo$MDyes$K')
        waits = [e for e in t.events if e.wait]
        self.assertEqual(len(waits),2)
        self.assertEqual(waits[0].state.portraits[0].mouth,0)
        self.assertEqual(waits[0].state.portraits[0].eye_mode,3)
        self.assertFalse(waits[0].state.mouth_enabled)
        self.assertEqual(waits[-1].state.portraits[0].eye_mode,5)
        self.assertTrue(waits[-1].state.mouth_enabled)

    def test_replay_equals_seek_and_restart(self):
        source='$c0MIST|hello$K$Pgoodbye$w4$K$d0$c1IKE|...$K'
        t=build_timeline(source)
        fresh=build_timeline(source)
        index=0
        for target in range(len(t.events)):
            while index<target:
                index+=1
            self.assertEqual(t.events[index],fresh.events[target])
        self.assertEqual(t.events[0].state,fresh.events[0].state)

    def test_skip_release_and_nonblocking_fade(self):
        t = build_timeline('$=0500$<$SD$c0IKE|Hi$K$SE$UB$H')
        waits = [e for e in t.events if e.wait]
        self.assertFalse(waits[0].state.skippable)
        self.assertTrue(waits[1].state.skippable and waits[1].state.script_released)
        fade = waits[0].state.screen_fade
        self.assertEqual((fade[0], fade[1]), ('in', 0))
        self.assertEqual(fade[2], 500)  # 30 frames
        # The text runs during the fade instead of after it.
        self.assertLess(next(e for e in t.events if e.kind == 'text').time_ms, 500)

    def test_icon_counts_in_window_width(self):
        plain = build_timeline('$c0IKE|ab$K', measure=lambda s: len(s))
        icon = build_timeline('$c0IKE|#P027ab$K', measure=lambda s: 24*s.count('#P') + len(s.replace('#P027', '')))
        self.assertEqual(icon.events[-1].state.boxes[0].text, '#P027ab')
        self.assertEqual(plain.events[-1].state.boxes[0].width, 368)
        big = build_timeline('$c0IKE|' + 'x'*150 + '#P027$K', measure=lambda s: 24*s.count('#P') + len(s.replace('#P027', '')))
        self.assertEqual(big.events[-1].state.boxes[0].width, 150 + 24 + 224)

    def test_resource_parser_rejects_bad_bounds(self):
        with self.assertRaises(ValueError): read_rect_resources(bytes(32))
        with self.assertRaises(ValueError): GameFont(bytes(48))

    def test_portrait_transition_keeps_both_endpoints(self):
        t=build_timeline('$FCIKE|$FD')
        transitions=[e for e in t.events if e.kind=='transition']
        self.assertEqual(len(transitions),2)
        self.assertEqual(transitions[0].transition_from.portraits[0].fid,'')
        self.assertEqual(transitions[0].state.portraits[0].fid,'FID_IKE')
        self.assertEqual(transitions[1].state.portraits[0].fid,'')
        self.assertEqual(transitions[0].transition_duration_ms,133)


@unittest.skipUnless(os.environ.get('FE9_EXTRACTED'), 'set FE9_EXTRACTED for local asset validation')
class LocalResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets=ConversationAssets(Path(os.environ['FE9_EXTRACTED']))

    def test_all_face_records_and_composition(self):
        self.assertGreater(len(self.assets.faces),300)
        for fid in ('FID_IKE','FID_L_IKE','FID_MIST','FID_L_GREIL','FID_IKE2','FID_BK'):
            if fid not in self.assets.faces: continue
            with self.subTest(fid=fid):
                face=self.assets.face(fid)
                image=face.compose()
                self.assertEqual(image.size,face.images[0].size)
                self.assertIsNotNone(image.getbbox())

    def test_game_font_lookup_matches_engine(self):
        system=self.assets.font('system')  # from Fonts/system.cms, as load_system_font does
        self.assertEqual(system.glyph('①').code,0x8740)  # NEC row: circled 1
        self.assertEqual(system.glyph('唸').code,0x8199)  # absent from system.cms: white star
        self.assertEqual(self.assets.font('alpha').glyph('~').code,0x20)  # no star either: first record
        with self.assertRaises(ValueError):
            system.glyph('é')  # no CP932 encoding at all

    def test_real_font_and_descriptor_render(self):
        r=ConversationRenderer(self.assets)
        t=build_timeline('$c0MIST|Are you all right?$K',measure=r.measure)
        e=next(e for e in t.events if e.wait)
        a=r.render(e); b=r.render(e)
        self.assertEqual(a.image.size,(608,448))
        self.assertEqual(a.image.tobytes(),b.image.tobytes())
        self.assertFalse([d for d in a.diagnostics if 'No scene background' not in d.description])
        self.assertFalse(self.assets.refresh())

    def test_inline_icon_draws_and_measures(self):
        r=ConversationRenderer(self.assets)
        self.assertEqual(r.measure('#P027'),24)
        t=build_timeline('$c0MIST|#P027OK$K',measure=r.measure)
        e=next(e for e in t.events if e.wait)
        result=r.render(e)
        self.assertFalse([d for d in result.diagnostics if 'No scene background' not in d.description])

    def test_text_scale_markup(self):
        r=ConversationRenderer(self.assets)
        plain=r.measure('Exceed 15 turns')
        self.assertEqual(r.measure('#X3AExceed 15 turns#x'),round(plain*0x3A/64))
        self.assertEqual(r.measure('#Y80Exceed 15 turns#y'),plain)  # height only
        self.assertEqual(r.measure('#S80ab#s'),2*r.measure('ab'))
        self.assertEqual(r.measure('#yabcd'),r.measure('cd'))  # measure_text_width skips 4 bytes
        t=build_timeline('$c0MIST|#S50Demo#s$K',measure=r.measure)
        e=next(e for e in t.events if e.wait)
        self.assertEqual(e.state.boxes[0].text,'#S50Demo#s')
        self.assertFalse([d for d in r.render(e).diagnostics if 'No scene background' not in d.description])

    def test_text_effect_markup(self):
        r=ConversationRenderer(self.assets)
        self.assertEqual(r.measure('#I40#R00#E#Oab#i#e#o'),r.measure('ab'))  # state codes add no width
        t=build_timeline('$c0MIST|#I40#R00#E#Oab#i#e#o#D$K',measure=r.measure)
        e=next(e for e in t.events if e.wait)
        self.assertEqual(e.state.boxes[0].text,'#I40#R00#E#Oab#i#e#o#D')
        self.assertFalse([d for d in r.render(e).diagnostics if 'No scene background' not in d.description])
        from PIL import Image
        plain=Image.new('RGBA',(80,40)); fx=Image.new('RGBA',(80,40))
        r._text(plain,'ab',(10,5)); r._text(fx,'ab',(10,5),shadow=True,outline=True)
        self.assertGreater(sum(fx.getchannel('A').histogram()[1:]),sum(plain.getchannel('A').histogram()[1:]))

    def test_chapter_two_ending_continuations(self):
        messages={m.speaker:m.text for m in read_messages_path(self.assets.files/'Mess/c02.m')}
        renderer=ConversationRenderer(self.assets)
        for mid,text in messages.items():
            if '_ED_' not in mid: continue
            with self.subTest(message=mid):
                resolution=resolve_context(self.assets.files/'Scripts/C02.cmb',messages,mid)
                self.assertIsNotNone(resolution.context)
                if mid!='MS_02_ED_01_01':
                    self.assertEqual(resolution.context.layout,'背景会話')
                    self.assertEqual(resolution.context.portraits[3],'FID_L_IKE')
                timeline=build_timeline(text,context=resolution.context,measure=renderer.measure)
                for event in timeline.events:
                    if event.wait:
                        self.assertFalse(renderer.render(event).diagnostics)

    def test_preview_selection_reset_autoadvance_and_position(self):
        import tkinter as tk
        from types import SimpleNamespace
        from fe_modding.games import Game
        from fe_modding.gui.conversation_preview import ConversationPreview
        root=tk.Tk(); root.withdraw()
        preview=ConversationPreview(root,SimpleNamespace(game=Game.PATH_OF_RADIANCE,
                                     extracted_dir=self.assets.files.parent))
        positions=[]
        preview.on_position=lambda offset,kind: positions.append((offset,kind))
        try:
            self.assertTrue(preview._auto.get())
            preview.update_message('first','$c0MIST|Hello$KAgain$K',message_id=1)
            self.assertEqual(preview._index,0)
            preview._next()
            self.assertGreater(preview._index,0)
            self.assertEqual(positions[-1][1],'wait')
            preview._auto.set(False)
            preview._toggle_play()
            # Continuing from a wait must not pause again before the next glyph.
            self.assertTrue(preview._playing)
            preview.update_message('second','$c1IKE|Yes$K',message_id=2)
            self.assertEqual(preview._index,0)
            self.assertEqual(positions[-1][0],0)
            self.assertFalse(preview._playing)
            preview._restart(); preview._step(); preview._previous()
            root.update_idletasks()
        finally:
            preview.cleanup(); root.destroy()

    def test_editor_highlight_does_not_edit_text_or_cursor(self):
        import tkinter as tk
        from types import SimpleNamespace
        from fe_modding.gui.dialogue_editor import DialogueEditor
        root=tk.Tk(); root.withdraw()
        widget=tk.Text(root)
        widget.insert('1.0','$c0MIST|Hello$K')
        widget.mark_set('insert','1.3'); widget.edit_modified(False)
        try:
            from fe_modding.formats.dialogue_notation import parse
            state = SimpleNamespace(_text_widget=widget, _document=parse('$c0MIST|Hello$K'), _scene=None)
            DialogueEditor._highlight_playback_position(state,10,'text')
            self.assertEqual(tuple(map(str,widget.tag_ranges('playback_position'))),('1.10','1.11'))
            self.assertEqual(widget.index('insert'),'1.3')
            self.assertFalse(widget.edit_modified())
            self.assertEqual(widget.get('1.0','end-1c'),'$c0MIST|Hello$K')
        finally: root.destroy()


if __name__=='__main__': unittest.main()
