import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fe_modding.formats import fe9_message_scene as ms
from fe_modding.formats.fe9_conversation import build_timeline
from fe_modding.formats.message import Message, read_messages, read_messages_path, write_messages

import io


def raw(text):
    return ms.to_raw(text)


class DecompileTests(unittest.TestCase):
    def kinds(self, text):
        return [(s.kind, {k: v for k, v in s.fields.items() if k != "trail"}) for s in ms.decompile(raw(text))]

    def test_seat_style_scene(self):
        text = "$R背景会話|$B村-崖|$<$F1$FCL_TIAMAT|$F1$PThat's it.$w4 Ike.$K\n$F3$FD$F3$Fc$=9999"
        self.assertEqual(self.kinds(text), [
            ("layout", {"layout": "背景会話"}),
            ("background", {"background": "村-崖"}),
            ("fade_in", {}),
            ("load_portrait", {"seat": 1, "fid": "L_TIAMAT"}),
            ("line", {"select": "F", "index": 1, "flush": True, "text": "That's it.$w4 Ike.", "wait": True}),
            ("remove_portrait", {"seat": 3}),
            ("eyes", {"seat": 3, "mode": "c"}),
            ("transition", {"ms": 9999}),
        ])
        steps = ms.decompile(raw(text))
        self.assertEqual(steps[4].fields["trail"], 1)

    def test_box_style_scene(self):
        text = "$R上下会話|$s0$FS$c0ZAWANAR|$s0Hey, $MC...$MD$K\n$d0$c1IKE|$Ub$HNo.$K$N$UB$H"
        self.assertEqual([k for k, _ in self.kinds(text)], [
            "layout", "select_box", "mouth_set", "show_speaker", "line", "dismiss_box",
            "show_speaker", "control", "yield", "line", "line", "control", "yield"])
        self.assertEqual(self.kinds(text)[4][1]["text"], "Hey, $MC...$MD")

    def test_round_trip_and_canonical_forms(self):
        text = raw("$RGMAP会話|$O3$GNarration.$K$W-$W+$WD$ND$Ff$FA$F2$W1text$K$K$>$Cx|$Q")
        steps = ms.decompile(text)
        self.assertEqual(ms.compile_steps(steps), text)
        for step in steps:
            self.assertEqual(ms.render_step(step.edited()), step.raw, step.kind)
        self.assertEqual(steps[-1].kind, "raw")  # unknown command kept byte for byte

    def test_editing_regenerates_only_that_step(self):
        text = raw("$R背景会話|$F1$FCL_IKE|$F1$PHello.$K")
        steps = ms.decompile(text)
        steps[1] = steps[1].edited(fid="L_MIST", seat=2)
        steps[2] = steps[2].edited(text="Hi, $w2there.", wait=False)
        self.assertEqual(ms.compile_steps(steps), raw("$R背景会話|$F2$FCL_MIST|$F1$PHi, $w2there."))

    def test_new_steps_and_validation(self):
        line = ms.new_step("line", select="s", index=1, flush=False, text="Yes.")
        self.assertEqual(ms.render_step(line), "$s1Yes.$K")
        self.assertIsNotNone(ms.validate_step(ms.new_step("load_portrait")))
        self.assertIsNotNone(ms.validate_step(ms.new_step("line", text="€")))
        self.assertIsNone(ms.validate_step(ms.new_step("load_portrait", fid="IKE")))

    def test_offsets(self):
        steps = ms.decompile(raw("$R上下会話|$c0IKE|$s0Hi.$K"))
        offsets = ms.step_offsets(steps)
        self.assertEqual(offsets, [0, 11, 18])
        self.assertEqual(ms.step_at_offset(offsets, 20), 2)

    def test_templates_decompile_cleanly(self):
        for name, text in ms.TEMPLATES.items():
            steps = ms.decompile(text)
            self.assertEqual(ms.compile_steps(steps), text)
            self.assertNotIn("raw", [s.kind for s in steps], name)
            build_timeline(text)

    def test_engine_name_hash(self):
        from fe_modding.formats.message import engine_name_hash
        self.assertEqual(engine_name_hash("A"), (65, 65))
        self.assertEqual(engine_name_hash("AB"), ((65 * 37 + 66) % 509, 65 * 31 + 66))
        # Bytes are sign-extended (extsb): 0x80 counts as -128.
        self.assertEqual(engine_name_hash("Ç"), ((-128 & 0xFFFFFFFF) % 509, -128 & 0xFFFFFFFF))

    def test_sorted_write_round_trip(self):
        messages = sorted([Message("MS_02_B", "b"), Message("MS_02_A", "a")],
                          key=lambda m: m.speaker.encode("cp437"))
        again = read_messages(io.BytesIO(write_messages(messages)))
        self.assertEqual([m.speaker for m in again], ["MS_02_A", "MS_02_B"])


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED"), "set FE9_EXTRACTED to the extracted FE9 project")
class VanillaTests(unittest.TestCase):
    def test_every_message_round_trips(self):
        root = Path(os.environ["FE9_EXTRACTED"])
        files = sorted(root.glob("**/Mess/*.m"))
        self.assertTrue(files)
        count = 0
        for path in files:
            for msg in read_messages_path(path):
                steps = ms.decompile(msg.text)
                self.assertEqual(ms.compile_steps(steps), msg.text, (path.name, msg.speaker))
                self.assertNotIn("raw", [s.kind for s in steps], (path.name, msg.speaker))
                for step in steps:
                    self.assertEqual(ms.render_step(step.edited()), step.raw, (path.name, msg.speaker, step.kind))
                count += 1
        self.assertGreater(count, 4000)

    def test_vanilla_ids_are_sorted(self):
        root = Path(os.environ["FE9_EXTRACTED"])
        for path in sorted(root.glob("**/Mess/*.m")):
            if path.name == "c90.m":  # project-made chapter (duplicated from c01), not on the disc

                continue
            ids = [m.speaker.encode("cp437") for m in read_messages_path(path)]
            self.assertEqual(ids, sorted(ids), path.name)


if __name__ == "__main__":
    unittest.main()
