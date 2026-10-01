import os
import unittest
from pathlib import Path

from fe_modding.formats import cp_ai_lang as lang
from fe_modding.formats import cp_data as cp
from fe_modding.formats import cp_ops
from fe_modding.formats.cp_data import Entry, Script, Section, SectionRef


def _script(*entries: Entry, name: str = "SEQ_T") -> Script:
    return Script(name, 0, list(entries))


def _compile(text: str, **kw) -> lang.CompileResult:
    return lang.compile_source(text, **kw)


class OpcodeTableTests(unittest.TestCase):
    def test_every_handler_is_described(self):
        self.assertEqual(len(cp_ops.OPS), 52)
        for op, spec in cp_ops.OPS.items():
            self.assertEqual(len({f.slot for f in spec.fields}), len(spec.fields), op)
            self.assertTrue(all(f.slot in "abcdef" for f in spec.fields), op)
            self.assertIn(spec.confidence, ("confirmed", "strong", "tentative"))
        self.assertEqual(len(cp_ops.BY_NAME), 50)  # all but the two header entries

    def test_comparison_codes_match_the_handler(self):
        self.assertEqual(cp_ops.COMPARISONS, {0: ">", 1: ">=", 2: "==", 3: "<=", 4: "<", 5: "!="})


class ReadableCodeTests(unittest.TestCase):
    def test_typical_attack_script(self):
        script = _script(Entry(105, 100, 0xFFFF), Entry(6, 1, 0xFFFF, 0, 99), Entry(107, 80, 0xFFFF),
                         Entry(6, 1, 0xFFFF, 0, 99),
                         Entry(101, 100, 0xFFFF, 0, 1, SectionRef("TBL_PID_LAGU")),
                         Entry(0, 0, 0xFFFF, 99), Entry(1001))
        text = lang.decompile(script)
        self.assertIn("use_staff(chance=100)", text)
        self.assertIn("if found: goto L99", text)
        self.assertIn("attack(chance=100, targets=TBL_PID_LAGU, exclude=True)", text)
        self.assertIn("L99:", text)
        self.assertTrue(text.rstrip().endswith("end()"))
        result = _compile(text)
        self.assertEqual(result.diagnostics, [])
        self.assertEqual(result.entries, script.entries)

    def test_registers_compare_and_names(self):
        script = _script(Entry(500, 0, 98304, 1), Entry(1, 0, 0, 0, 1), Entry(202, 0, 0xFFFF), Entry(1000),
                         Entry(0, 0, 0xFFFF, 1), Entry(3, 0, 0xFFFF, 0, 0, 0, "SEQ_ATTACK1.5RANGEMOVE"),
                         Entry(1000, 0, 0, 0, 1))
        lines = lang.entry_lines(script.entries)
        self.assertEqual(lines[0], "r0 = count_units(range=1.5, weapon_range=True)")
        self.assertEqual(lines[1], "if r0 > 0: goto L1")
        self.assertEqual(lines[5], "set_scripts(move=SEQ_ATTACK1.5RANGEMOVE)")
        self.assertEqual(lines[6], "stop(resume=L1)")
        self.assertEqual(_compile("\n".join(lines)).entries, script.entries)

    def test_result_codes_after_a_talk(self):
        lines = lang.entry_lines([Entry(215, 0, 0xFFFF, 0, 0, "PID_IKE"), Entry(1, 0, 2, 3, 99),
                                  Entry(1, 0, 2, 9, 99), Entry(0, 0, 0xFFFF, 99), Entry(1001)])
        self.assertEqual(lines[1], "if r0 == TALK_QUEUED: goto L99")
        self.assertEqual(lines[2], "if r0 == NONE_FOUND: goto L99")

    def test_threat_limit_and_negative_values(self):
        self.assertEqual(lang.entry_source(Entry(206, 0, 5, 1)), "move_nearest(fallback=True, threat_limit=5)")
        self.assertEqual(lang.entry_source(Entry(600, 0, 0, 0, 0xFFFFFFFD)), "r0 = move_stat(add=-3)")
        self.assertEqual(_compile("r0 = move_stat(add=-3)").entries, [Entry(600, 0, 0, 0, 0xFFFFFFFD)])
        self.assertEqual(_compile("move_nearest(threat_limit=keep)\nend()").entries[0].b, 0)

    def test_unusual_entries_fall_back_to_op(self):
        odd = [Entry(101, 100, 0xFFFF, 7), Entry(213, 1, 2, 3, 4, "x", SectionRef("SEQ_A")),
               Entry(6, 5, 0xFFFF, 0, 1), Entry(0, 0, 3, 1), Entry(-2, 0, 0, 0, 0, "SEQ_X")]
        for entry in odd:
            text = lang.entry_source(entry)
            self.assertTrue(text.startswith("op("), text)
            self.assertEqual(lang._parse_line(text), entry)

    def test_names_need_quotes_only_when_not_identifiers(self):
        self.assertEqual(lang.entry_source(Entry(201, 0, 0xFFFF, 0, 0, "PID WITH SPACE")),
                         'move_to_talk(pid="PID WITH SPACE")')

    def test_errors(self):
        cases = {
            "attak(chance=1)": "unknown function",
            "attack(chance=100, colour=2)": "has no 'colour'",
            "attack()": "needs chance=",
            "count_units(range=1)": "writes a register",
            "r0 = attack(chance=1)": "doesn't write a register",
            "goto L5\nend()": "L5 doesn't exist",
            "op(150)\nend()": "no handler",
            'talk(pid="oops)': "string",
        }
        for text, message in cases.items():
            result = _compile(text)
            self.assertFalse(result.ok, text)
            self.assertIn(message, " ".join(d.message for d in result.errors), text)

    def test_warnings(self):
        result = _compile("attack(chance=150)")
        self.assertTrue(result.ok)
        messages = " ".join(d.message for d in result.diagnostics)
        self.assertIn("outside 0-100", messages)
        self.assertIn("doesn't end with", messages)
        names = lang.Names(pids={"PID_IKE"}, attack_scripts={"SEQ_A"}, move_scripts={"SEQ_M"},
                           sections={"TBL_PID_X"})
        result = _compile("talk(pid=PID_NOBODY)\nset_scripts(attack=SEQ_M)\nattack(chance=1, targets=TBL_NONE)\nend()",
                          names=names)
        messages = [d.message for d in result.diagnostics]
        self.assertTrue(any("not a known PID" in m for m in messages))
        self.assertTrue(any("is a move script" in m for m in messages))
        self.assertTrue(any("no table TBL_NONE" in m for m in messages))

    def test_comments_and_lines(self):
        result = _compile("# header\n\nattack(chance=100)  # go\nL99:  # done\nend()\n")
        self.assertTrue(result.ok)
        self.assertEqual(result.lines, [3, 4, 5])

    def test_fallthrough_labels(self):
        sections = [Section("SEQ_A", [0xFFFFFFFE, 0, 0, 0, 0, "SEQ_A", 0] + [0xFFFFFFFF] + [0] * 6
                            + [4, 0, 0xFFFF, 0, 7, 0, 0]),
                    Section("SEQ_B", [0xFFFFFFFE, 0, 0, 0, 0, "SEQ_B", 0] + [0xFFFFFFFF] + [0] * 6
                            + [0, 0, 0xFFFF, 7, 0, 0, 0, 1001, 0, 0, 0, 0, 0, 0])]
        labels = lang.fallthrough_labels(sections, "SEQ_A")
        self.assertEqual(labels, {7: "SEQ_B"})
        result = _compile("goto L7", fallthrough=labels)
        self.assertTrue(result.ok)
        self.assertIn("SEQ_B", result.diagnostics[0].message)

    def test_field_text_helpers(self):
        self.assertEqual(lang.parse_field_text("TBL_PID_X", "pid_table"), SectionRef("TBL_PID_X"))
        self.assertEqual(lang.parse_field_text("PID_X", "pid"), "PID_X")
        self.assertEqual(lang.parse_field_text("-1", "int"), 0xFFFFFFFF)
        self.assertEqual(lang.parse_field_text("1.5", "fixed"), 98304)
        self.assertEqual(lang.parse_field_text("", "any"), 0)
        self.assertEqual(lang.field_text(0xFFFF), "0xffff")


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to the extracted files folder")
class VanillaScriptsTests(unittest.TestCase):
    def test_every_vanilla_script_round_trips_without_op(self):
        doc = cp.parse_cp_data((Path(os.environ["FE9_EXTRACTED_FILES"]) / "cp_data.bin").read_bytes())
        names = cp.attack_scripts(doc) + cp.move_scripts(doc)
        scripts = [cp.read_script(doc.section(n)) for n in names]
        self.assertEqual(lang.roundtrip_problems(scripts), [])
        for script in scripts:
            self.assertFalse(any(line.startswith("op(") for line in lang.entry_lines(script.entries)), script.name)
            result = lang.compile_source(lang.decompile(script), fallthrough=lang.fallthrough_labels(doc.sections,
                                                                                                       script.name))
            self.assertTrue(result.ok, (script.name, [str(d) for d in result.errors]))
        rebuilt = cp.parse_cp_data(cp.build_cp_data(doc))
        for name, script in zip(names, scripts):
            cp.write_script(rebuilt.section(name), cp.Script(name, script.script_id,
                                                             lang.compile_source(lang.decompile(script)).entries))
        self.assertEqual(cp.build_cp_data(rebuilt), (Path(os.environ["FE9_EXTRACTED_FILES"]) / "cp_data.bin").read_bytes())


if __name__ == "__main__":
    unittest.main()
