"""Tests for the event-script toolchain (fe_modding.formats.cmb)."""

import os
import unittest
from pathlib import Path

from fe_modding.formats.cmb import (
    CompileError,
    compile_source,
    decompile,
    read_cmb,
    write_cmb,
)
from fe_modding.formats.cmb.catalog import TRIGGERS_BY_DECORATOR
from fe_modding.formats.cmb.model import Instr, Label


def listing(fn) -> list[str]:
    """Readable instruction list with labels numbered by position."""
    names = {}
    for item in fn.code:
        if isinstance(item, Label):
            names[id(item)] = f"L{len(names)}"
    out = []
    for item in fn.code:
        if isinstance(item, Label):
            out.append(names[id(item)] + ":")
        else:
            ops = [names[id(o)] if isinstance(o, Label) else repr(o) for o in item.operands]
            out.append(f"{item.name} {', '.join(ops)}".strip())
    return out


def compile_fn(body: str, params: str = "", decorators: str = ""):
    source = f"{decorators}def f({params}):\n" + "".join("    " + line + "\n" for line in body.splitlines())
    return compile_source(source).script.functions[0]


EPILOGUE = ["push8 0", "return"]


class CompilerCodegenTests(unittest.TestCase):
    def test_call_statement_pops_result(self):
        fn = compile_fn('TalkEvent("MS_01")')
        self.assertEqual(listing(fn), ["pushstr8 'MS_01'", "externCall 'TalkEvent', 1", "pop"] + EPILOGUE)

    def test_if_else(self):
        fn = compile_fn("if arg0 == 1:\n    WaitM(1)\nelse:\n    WaitM(2)", "arg0")
        self.assertEqual(listing(fn), [
            "pushvar8 0", "push8 1", "eq", "branchz L0",
            "push8 1", "externCall 'WaitM', 1", "pop", "branch L1",
            "L0:", "push8 2", "externCall 'WaitM', 1", "pop", "L1:",
        ] + EPILOGUE)

    def test_while_break_continue(self):
        fn = compile_fn("while arg0:\n    if arg0 == 3:\n        break\n    continue", "arg0")
        self.assertEqual(listing(fn), [
            "L0:", "pushvar8 0", "branchz L2",
            "pushvar8 0", "push8 3", "eq", "branchz L1", "branch L2", "L1:",
            "branch L0", "branch L0", "L2:",
        ] + EPILOGUE)

    def test_do_while(self):
        fn = compile_fn("do:\n    if arg0:\n        break\n    arg0 = Foo()\nwhile arg0 == 2", "arg0")
        self.assertEqual(listing(fn), [
            "L0:", "pushvar8 0", "branchz L1", "branch L3", "L1:",
            "pushaddr8 0", "externCall 'Foo', 0", "store", "pop",
            "L2:", "pushvar8 0", "push8 2", "eq", "branchnz L0", "L3:",
        ] + EPILOGUE)

    def test_short_circuit(self):
        fn = compile_fn("return arg0 and arg1 or 5", "arg0, arg1")
        self.assertEqual(listing(fn), [
            "pushvar8 0", "branchkeepnz L0", "pushvar8 1", "L0:", "branchkeepz L1", "push8 5", "L1:", "return",
        ] + EPILOGUE)

    def test_assignment_forms(self):
        fn = compile_fn("var x = 7\nx = 8\nx -= 1\nvar y[3]\ny[2] = x")
        self.assertEqual(listing(fn), [
            "pushaddr8 0", "push8 7", "store",
            "pushaddr8 0", "push8 8", "store", "pop",
            "pushaddr8 0", "deref", "push8 1", "sub", "store", "pop",
            "push8 2", "pushaddrarray8 1", "pushvar8 0", "store", "pop",
        ] + EPILOGUE)
        self.assertEqual(fn.num_vars, 4)

    def test_walrus_in_loop_condition(self):
        fn = compile_fn("while (u := ForceGetFirst(1)):\n    UnitEscape(u, 0)")
        self.assertEqual(listing(fn)[:6], ["L0:", "pushaddr8 0", "push8 1", "externCall 'ForceGetFirst', 1", "store", "branchz L1"])

    def test_negative_literal_and_lit(self):
        fn = compile_fn("return -1 + lit(-2)")
        self.assertEqual(listing(fn)[:4], ["push8 1", "neg", "push8 -2", "add"])

    def test_local_call_and_export(self):
        result = compile_source("@export\ndef Helper(a):\n    return a\n\ndef g():\n    Helper(3)\n")
        helper, g = result.script.functions
        self.assertEqual(helper.id_string, "Helper")
        self.assertIsNone(g.id_string)
        self.assertEqual(listing(g)[:3], ["push8 3", "localCall 0", "pop"])

    def test_trigger_decorator(self):
        result = compile_source('@on_talk(pid1="PID_IKE", pid2="PID_TIAMAT", name="talk")\ndef f():\n    pass\n')
        fn = result.script.functions[0]
        self.assertEqual(fn.type, TRIGGERS_BY_DECORATOR["on_talk"].type)
        pool = result.script.pool
        self.assertEqual(len(fn.params), 4)
        self.assertIn("PID_IKE", pool)
        self.assertEqual(fn.params[2], 0)

    def test_phase_enum(self):
        fn = compile_source('@on_phase(turn_from=2, turn_to=2, phase="enemy")\ndef f():\n    pass\n').script.functions[0]
        self.assertEqual((fn.type, fn.params), (6, [2, 2, 1]))

    def test_goto_and_asm(self):
        fn = compile_fn("goto done unless arg0\nWaitM(1)\ndone:\nasm:\n    push8 4\n    pop", "arg0")
        self.assertEqual(listing(fn), [
            "pushvar8 0", "branchz L0", "push8 1", "externCall 'WaitM', 1", "pop", "L0:", "push8 4", "pop",
        ] + EPILOGUE)


class CompilerDiagnosticsTests(unittest.TestCase):
    def assert_error(self, source: str, fragment: str):
        with self.assertRaises(CompileError) as ctx:
            compile_source(source)
        self.assertIn(fragment, str(ctx.exception))

    def test_wrong_argc_for_known_extern(self):
        self.assert_error("def f():\n    TalkEvent(1, 2)\n", "TalkEvent() takes 1 argument")

    def test_unknown_variable(self):
        self.assert_error("def f():\n    return nope\n", "Unknown variable 'nope'")

    def test_break_outside_loop(self):
        self.assert_error("def f():\n    break\n", "outside a loop")

    def test_parse_error_has_line(self):
        with self.assertRaises(CompileError) as ctx:
            compile_source("def f():\n    x = = 1\n")
        self.assertEqual(ctx.exception.diagnostics[0].line, 2)

    def test_unknown_extern_is_a_warning(self):
        result = compile_source("def f():\n    NotARealFunction(1)\n")
        self.assertTrue(any("NotARealFunction" in d.message for d in result.warnings))

    def test_global_slot_outside_engine_table(self):
        self.assert_error("global far @ 32\ndef f():\n    far = 1\n", "slots 0-31 only")


class GlobalReservationTests(unittest.TestCase):
    SOURCE = "global a @ 1\nglobal b @ 5\ndef f():\n    a = b\n"

    def test_fresh_header_reserves_highest_slot_plus_one(self):
        header = compile_source(self.SOURCE).script.header
        self.assertEqual(int.from_bytes(header[0x22:0x24], "little"), 6)

    def test_base_reservation_grows_but_never_shrinks(self):
        base = compile_source("def f():\n    return 0\n").script
        base.header = base.header[:0x22] + (8).to_bytes(2, "little") + base.header[0x24:]
        kept = compile_source(self.SOURCE, base=base).script.header
        self.assertEqual(int.from_bytes(kept[0x22:0x24], "little"), 8)
        base.header = base.header[:0x22] + (2).to_bytes(2, "little") + base.header[0x24:]
        grown = compile_source(self.SOURCE, base=base).script.header
        self.assertEqual(int.from_bytes(grown[0x22:0x24], "little"), 6)


class BinaryRoundTripTests(unittest.TestCase):
    SOURCE = (
        '@export\ndef Startup():\n    regist("flag")\n\n'
        '@on_phase(turn_from=1, turn_to=1, phase="player")\ndef turn1():\n'
        '    if not get("flag"):\n        TalkEvent("MS_TEST")\n        set("flag")\n'
    )

    def test_compiled_file_reads_back(self):
        script = compile_source(self.SOURCE).script
        data = write_cmb(script)
        again = read_cmb(data)
        self.assertEqual(write_cmb(again), data)
        self.assertEqual([f.id_string for f in again.functions], ["Startup", None])
        self.assertEqual(again.functions[1].params, [1, 1, 0])

    def test_decompile_compile_is_lossless(self):
        data = write_cmb(compile_source(self.SOURCE).script)
        script = read_cmb(data)
        source, stats = decompile(script)
        self.assertEqual(stats.asm, 0)
        self.assertEqual(write_cmb(compile_source(source, base=script).script), data)

    def test_do_while_and_empty_else_decompile_structured(self):
        source = (
            "def f(a):\n"
            "    do:\n        a = Foo()\n    while a == 2\n"
            "    if a:\n        if not Bar():\n            Foo()\n        else:\n            pass\n"
        )
        compiled = compile_source(source).script
        # read back from bytes too: there the empty else's two labels merge
        for script in (compiled, read_cmb(write_cmb(compiled))):
            text, stats = decompile(script)
            self.assertEqual((stats.goto, stats.asm), (0, 0))
            self.assertIn("    do:\n", text)
            self.assertIn("    while arg0 == 2\n", text)
            self.assertIn("        else:\n            pass\n", text)
            self.assertEqual(write_cmb(compile_source(text, base=script).script), write_cmb(script))

    def test_padding_that_decodes_as_code(self):
        # C01 function 6 pads with 00 39 07, which reads as `nop; return`
        epilogue = bytes([0x19, 0x00, 0x39])
        for yields in range(4):  # each `yield` is one byte: find a 3-byte pad
            script = compile_source("def f():\n    Foo()\n" + "    yield\n" * yields).script
            data = bytearray(write_cmb(script))  # the only function's code ends the file
            if data[-6:-3] == epilogue:
                break
        else:
            self.fail("no layout with a 3-byte pad")
        data[-3:] = b"\x00\x39\x07"
        again = read_cmb(bytes(data))
        self.assertEqual(listing(again.functions[0])[-2:], EPILOGUE)
        self.assertEqual(again.functions[0].raw_code_pad, b"\x00\x39\x07")
        self.assertEqual(write_cmb(again), bytes(data))

    def test_adding_code_relayouts_file(self):
        data = write_cmb(compile_source(self.SOURCE).script)
        script = read_cmb(data)
        source, _ = decompile(script)
        source += '\n@on_phase(turn_from=2, turn_to=2, phase="enemy")\ndef turn2():\n    TalkEvent("MS_NEW_STRING")\n'
        rebuilt = read_cmb(write_cmb(compile_source(source, base=script).script))
        self.assertEqual(len(rebuilt.functions), 3)
        self.assertIn("MS_NEW_STRING", rebuilt.pool)
        self.assertEqual(rebuilt.pool[:len(script.pool)], script.pool)  # old offsets unchanged
        new_fn = rebuilt.functions[2]
        self.assertEqual(listing(new_fn)[:2], ["pushstr8 'MS_NEW_STRING'", "externCall 'TalkEvent', 1"])


class SourceToolsTests(unittest.TestCase):
    SOURCE = (
        "# function 0\n@export\n@on_phase(turn_from=1, turn_to=1, phase=\"player\")\ndef first():\n    second()\n\n"
        "# function 1\ndef second():\n    WaitM(1)\n"
    )

    def test_spans(self):
        from fe_modding.formats.cmb import source_tools as st
        spans = st.function_spans(self.SOURCE)
        self.assertEqual([s.name for s in spans], ["first", "second"])
        self.assertEqual((spans[0].first_line, spans[0].def_line, spans[0].last_line), (1, 4, 5))
        self.assertEqual(spans[0].export_id, "first")
        self.assertEqual(spans[0].trigger_values, {"turn_from": 1, "turn_to": 1, "phase": "player"})

    def test_form_rewrite_and_rename(self):
        from fe_modding.formats.cmb import source_tools as st
        span = st.function_spans(self.SOURCE)[1]
        decorators = st.decorator_source(None, "renamed", 11, {"pid": "PID_IKE"})
        text = st.replace_decorators(self.SOURCE, span, decorators, "renamed")
        self.assertIn('@on_death(pid="PID_IKE")\ndef renamed():', text)
        self.assertIn("    renamed()", text)  # call site renamed too
        fn = compile_source(text).script.functions[1]
        self.assertEqual(fn.type, 11)

    def test_description(self):
        from fe_modding.formats.cmb import source_tools as st
        span = st.function_spans(self.SOURCE)[1]
        self.assertEqual(span.description, "")  # the decompiler's "function N" comment isn't one
        text = st.replace_decorators(self.SOURCE, span, [], description="Talk with Ike")
        self.assertIn("# function 1\n# Talk with Ike\ndef second():", text)
        span = st.function_spans(text)[1]
        self.assertEqual(span.description, "Talk with Ike")
        text = st.replace_decorators(text, span, [], description="Reworded")
        self.assertEqual(st.function_spans(text)[1].description, "Reworded")
        self.assertNotIn("Talk with Ike", text)

    def test_new_duplicate_delete(self):
        from fe_modding.formats.cmb import source_tools as st
        text, name = st.new_function_source(self.SOURCE)
        self.assertEqual(name, "new_event")
        spans = st.function_spans(text)
        text, copy = st.duplicate_function_source(text, spans[0])
        self.assertEqual(copy, "first_copy")
        script = compile_source(text).script
        self.assertEqual([f.id_string for f in script.functions], ["first", None, None, None])
        text = st.delete_function_source(text, st.function_spans(text)[1])
        self.assertEqual([s.name for s in st.function_spans(text)], ["first", "new_event", "first_copy"])


SCRIPTS = Path(os.environ.get("FE9_EXTRACTED_FILES", "")) / "Scripts"


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class VanillaCorpusTests(unittest.TestCase):
    def test_every_script_round_trips(self):
        paths = sorted(SCRIPTS.glob("*.cmb"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(script=path.name):
                data = path.read_bytes()
                script = read_cmb(data)
                self.assertEqual(write_cmb(script), data)
                source, stats = decompile(script, path.name)
                self.assertEqual(write_cmb(compile_source(source, base=script).script), data)


if __name__ == "__main__":
    unittest.main()
