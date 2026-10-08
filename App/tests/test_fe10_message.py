"""Radiant Dawn message byte-code: tokenizer, readable notation and steps (formats/fe10_message.py).

The corpus tests run on every ``Mess/*.m`` of an extracted Radiant Dawn disc when
``FE10_EXTRACTED_FILES`` / ``FE10_EXTRACTED`` is set (see test_fe10_corpus.py).
"""

import io
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import fe10_message as F
from fe_modding.formats import message


def _files() -> Path | None:
    value = os.environ.get("FE10_EXTRACTED_FILES")
    if value:
        return Path(value)
    root = os.environ.get("FE10_EXTRACTED")
    return Path(root) / "files" if root else None


FILES = _files()

# A vanilla-shaped message: cast list, layout, two actors, a line with pauses and the mouth codes.
SAMPLE = (b"\x05FL|PUGO|IKE||\x02BO\x04R" + "上下会話".encode("cp932") + b"|\x0c01\x0e1D"
          b"\x0704\x084DWho are you?\x02w2 Answer\x02mc...\x02md\x11\n\x0711Ike.\x11\x10\x01*\x01H")


def cp437(data: bytes) -> str:
    return data.decode("cp437")


class TokenizeTest(unittest.TestCase):
    def test_tokens_cover_every_byte(self):
        tokens = F.tokenize(SAMPLE)
        self.assertEqual(b"".join(t.raw for t in tokens), SAMPLE)
        names = [t.name for t in tokens if t.kind == "command"]
        self.assertEqual(names, ["FL", "BO", "R", "seat", "show_now", "speaker", "show", "w2", "mc", "md", "wait",
                                 "speaker", "wait", "page", "*", "H"])
        fl = tokens[0]
        self.assertEqual(fl.args, ("PUGO", "IKE"))
        layout = next(t for t in tokens if t.name == "R")
        self.assertEqual(layout.args, ("上下会話",))

    def test_field_end_skips_a_shift_jis_trail_byte_equal_to_bar(self):
        # ポ is 83 7C: its second byte is '|', which must not end the argument.
        raw = b"\x04B" + "ポ-路地".encode("cp932") + b"|text"
        tokens = F.tokenize(raw)
        self.assertEqual(tokens[0].args, ("ポ-路地",))
        self.assertEqual(tokens[1].raw, b"text")

    def test_truncated_command_becomes_bytes(self):
        tokens = F.tokenize(b"ab\x07")
        self.assertEqual([t.kind for t in tokens], ["text", "byte"])
        tokens = F.tokenize(b"\x04Rno bar")
        self.assertEqual(tokens[0].kind, "byte")
        self.assertEqual(b"".join(t.raw for t in tokens), b"\x04Rno bar")


class NotationTest(unittest.TestCase):
    def test_display_of_the_sample(self):
        display = F.to_display(cp437(SAMPLE))
        self.assertEqual(display, "<FL|PUGO|IKE><BO><R:上下会話><seat:01><show_now:1D><speaker:04><show:4D>"
                                  "Who are you?<w2> Answer<mc>...<md><wait>\n<speaker:11>Ike.<wait><page><*><H>")
        self.assertEqual(F.to_raw(display), cp437(SAMPLE))

    def test_round_trip_of_odd_bytes(self):
        for raw in (b"\x06x", b"\x13", b"a<b", b"\x01:", b"\x01|", b"\x02<>", b"\x05FL||", b"\x05FL|A||",
                    b"\x04FT2000|", b"\x04V0VOICE_X|", b"\x04NF0D|", b"\x0bAB", b"\x07\x80\x81",
                    b"\x81\x40\x81\x40", "①".encode("cp932"), b"\x03DFC", b"\x01=", b"\xff\xfe"):
            with self.subTest(raw=raw):
                display = F.to_display(cp437(raw))
                self.assertEqual(F.to_raw(display), cp437(raw), display)

    def test_typed_notation(self):
        self.assertEqual(F.to_raw("<FL|>"), cp437(b"\x05FL||"))
        self.assertEqual(F.to_raw("<V3:VOICE_A><VW><v3>"), cp437(b"\x04V3VOICE_A|\x02VW\x02v3"))
        self.assertEqual(F.to_raw("a\nb<wait>"), cp437(b"a\nb\x11"))
        self.assertEqual(F.to_raw("<0x41>"), "A")
        for bad in ("<speaker:1>", "<speaker>", "<nope:x>", "a < b", "<abcd>", "<FL||x>"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    F.to_raw(bad)

    def test_plain_text(self):
        self.assertEqual(F.plain_text(cp437(SAMPLE)), "Who are you? Answer... Ike.")

    def test_every_command_key_has_a_description(self):
        for token in F.tokenize(SAMPLE):
            if token.kind == "command":
                self.assertTrue(F.command_key(token), token)
                self.assertNotEqual(F.describe(token), "Unknown command")


class StepsTest(unittest.TestCase):
    def test_decompile_groups_lines(self):
        steps = F.decompile(cp437(SAMPLE))
        kinds = [s.kind for s in steps]
        self.assertEqual(kinds, ["FL|", "BO", "R:", "seat", "show_now", "speaker", "show", "line", "speaker",
                                 "line", "*", "H"])
        line = steps[7]
        self.assertEqual(line.fields, {"text": "Who are you?<w2> Answer<mc>...<md>", "end": "<wait>\n"})
        self.assertEqual(steps[9].fields["end"], "<wait><page>")
        self.assertEqual("".join(s.display for s in steps), F.to_display(cp437(SAMPLE)))
        for step in steps:
            self.assertEqual(F.render_step(step), step.display)
        self.assertEqual(F.cast_of(steps), ["PUGO", "IKE"])
        self.assertEqual(F.summary(steps[5], F.cast_of(steps)), "actor 0 PUGO at position 4")

    def test_edit_and_compile(self):
        steps = F.decompile(cp437(SAMPLE))
        steps[7] = F.edited(steps[7], text="Hello!")
        steps[2] = F.edited(steps[2], value="背景会話")
        steps.insert(3, F.new_step("ec"))
        text = F.compile_steps(steps)
        self.assertIn("Hello!".encode(), text.encode("cp437"))
        self.assertEqual(F.to_display(text).count("<ec>"), 1)
        self.assertIn("<R:背景会話>", F.to_display(text))

    def test_new_steps_are_valid(self):
        for kind in F.ADDABLE:
            with self.subTest(kind=kind):
                step = F.new_step(kind)
                if kind in ("raw", "B:", "b:", "R:", "S:", "V#:", "rb:", "rk:", "NF:"):
                    continue  # need a value first
                self.assertIsNone(F.validate_step(step), step.display)

    def test_validate_rejects_bad_fields(self):
        self.assertIsNotNone(F.validate_step(F.edited(F.new_step("speaker"), a="G")))
        self.assertIsNotNone(F.validate_step(F.edited(F.new_step("show"), b="X")))


class TextOrderTest(unittest.TestCase):
    def test_text_order_reproduces_the_blob_layout(self):
        messages = [message.Message(speaker="MS_A", text="first"), message.Message(speaker="MS_B", text="second")]
        data = message.write_messages(messages, text_order=["MS_B", "MS_A"])
        self.assertEqual(message.read_messages(io.BytesIO(data)), messages)
        self.assertEqual(message.read_text_order(io.BytesIO(data)), ["MS_B", "MS_A"])
        self.assertLess(data.index(b"second"), data.index(b"first"))
        # Unknown IDs follow in table order.
        data = message.write_messages(messages + [message.Message("MS_C", "third")], text_order=["MS_B"])
        self.assertEqual(message.read_text_order(io.BytesIO(data)), ["MS_B", "MS_A", "MS_C"])


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to the files/ folder of an extracted Radiant Dawn disc")
class CorpusTest(unittest.TestCase):
    def paths(self):
        paths = sorted((FILES / "Mess").glob("*.m"))
        self.assertGreater(len(paths), 200)
        return paths

    def test_every_mess_file_rebuilds_byte_identically(self):
        for path in self.paths():
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                rebuilt = message.write_messages(message.read_messages_path(path), message.read_text_order_path(path))
                self.assertEqual(rebuilt, raw)

    def test_every_message_round_trips_through_the_notation_and_the_steps(self):
        for path in self.paths():
            if path.name[:2].lower() in ("d_", "f_", "i_", "s_"):
                continue  # German/French/Italian/Spanish files use their own single-byte tables (later phase)
            for msg in message.read_messages_path(path):
                display = F.to_display(msg.text)
                with self.subTest(path=path.name, id=msg.speaker):
                    self.assertEqual(F.to_raw(display), msg.text)
                    self.assertNotIn("<0x", display)
                    steps = F.decompile(msg.text)
                    self.assertEqual("".join(s.display for s in steps), display)
                    for step in steps:
                        self.assertNotEqual(step.kind, "raw", step.display)
                        self.assertEqual(F.render_step(step), step.display)


if __name__ == "__main__":
    unittest.main()
