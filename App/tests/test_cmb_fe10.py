"""Radiant Dawn event scripts: the FE10 dialect of fe_modding.formats.cmb, its
catalogues and flag table."""

import os
import unittest
from pathlib import Path

from fe_modding.formats import event_flags
from fe_modding.formats.cmb import CmbError, CompileError, compile_source, decompile, read_cmb, write_cmb
from fe_modding.formats.cmb.catalog import load_externs, lookup_extern, triggers
from fe_modding.formats.cmb.compiler import default_header
from fe_modding.formats.cmb.model import FE9, FE10, detect_dialect
from fe_modding.formats.cmb.parser import parse
from fe_modding.formats.cmb import source_tools as st
from tests.test_cmb import listing


def compile10(body: str, params: str = "", decorators: str = ""):
    source = f"{decorators}def f({params}):\n" + "".join("    " + line + "\n" for line in body.splitlines())
    return compile_source(source, dialect=FE10).script


def fn10(body: str, params: str = "", decorators: str = ""):
    return compile10(body, params, decorators).functions[0]


class DialectTests(unittest.TestCase):
    def test_detected_from_the_build_stamp(self):
        self.assertIs(detect_dialect(default_header("C0101.cmb", 0, FE10)), FE10)
        self.assertIs(detect_dialect(default_header("C01.cmb")), FE9)
        self.assertIs(read_cmb(write_cmb(compile10("Foo()"))).dialect, FE10)

    def test_base_dialect_wins(self):
        base = read_cmb(write_cmb(compile10("Foo()")))
        self.assertIs(compile_source("def f():\n    x = 1\n", base=base).script.dialect, FE10)


class Fe10CodegenTests(unittest.TestCase):
    def test_assignment_is_assign_without_pop(self):
        self.assertEqual(listing(fn10("x = 1\nx += 2")), [
            "pushaddr8 0", "push8 1", "assign",
            "pushaddr8 0", "deref", "push8 2", "add", "assign", "ret0"])

    def test_returns_and_epilogue(self):
        self.assertEqual(listing(fn10("if arg0:\n    return 1\nreturn 0", "arg0")),
                         ["pushvar8 0", "branchz L0", "ret1", "L0:", "ret0"])
        self.assertEqual(listing(fn10("return arg0", "arg0")), ["pushvar8 0", "return"])
        self.assertEqual(listing(fn10("Foo()")), ["externCall 'Foo', 0", "pop", "ret0"])

    def test_triggered_functions_keep_the_old_epilogue(self):
        fn = fn10("Foo()", decorators='@on_phase(turn_from=1, turn_to=1, phase="player")\n')
        self.assertEqual(listing(fn)[-2:], ["push8 0", "return"])

    def test_inc_dec(self):
        self.assertEqual(listing(fn10("x = 0\nx++\n++x\nFoo(x--)")), [
            "pushaddr8 0", "push8 0", "assign",
            "pushvar8 0", "pushaddr8 0", "inc", "pop",
            "pushaddr8 0", "inc", "pushvar8 0", "pop",
            "pushvar8 0", "pushaddr8 0", "dec", "externCall 'Foo', 1", "pop", "ret0"])

    def test_switch(self):
        fn = fn10("switch arg0:\n    case 0, 5:\n        return 1\n    case 2:\n        Foo()\n        break\n"
                  "    default:\n        Bar()", "arg0")
        self.assertEqual(listing(fn), [
            "pushvar8 0",
            "dup", "push8 0", "eq", "branchnz L0", "dup", "push8 5", "eq", "branchnz L0", "branch L1",
            "L0:", "ret1",
            "L1:", "dup", "push8 2", "eq", "branchnz L2", "branch L3",
            "L2:", "externCall 'Foo', 0", "pop", "branch L4",
            "L3:", "externCall 'Bar', 0", "pop",
            "L4:", "pop", "ret0"])

    def test_continue_in_a_switch_goes_to_the_loop(self):
        fn = fn10("while arg0:\n    switch arg0:\n        case 1:\n            continue\n", "arg0")
        self.assertEqual(listing(fn), [
            "L0:", "pushvar8 0", "branchz L3",
            "pushvar8 0", "dup", "push8 1", "eq", "branchnz L1", "branch L2",
            "L1:", "pop", "branch L0",  # continue: drop the switch value, back to the loop's top
            "L2:", "pop", "branch L0", "L3:", "ret0"])

    def test_long_local_call_index(self):
        source = "".join(f"def f{i}():\n    pass\n\n" for i in range(200)) + "def main():\n    f150()\n    f5()\n"
        script = compile_source(source, dialect=FE10).script
        data = write_cmb(script)
        again = read_cmb(data)
        self.assertEqual([i.operands for i in again.functions[200].instructions() if i.op == 0x37], [[150], [5]])
        self.assertEqual(write_cmb(again), data)
        with self.assertRaises(CmbError):
            write_cmb(compile_source(source).script)  # Path of Radiance's localCall index is one signed byte

    def test_fe9_rejects_fe10_constructs(self):
        for body in ("x = 0\nx++", "switch 1:\n    case 1:\n        pass"):
            with self.subTest(body=body), self.assertRaises(CompileError):
                compile_source("def f():\n" + "".join("    " + ln + "\n" for ln in body.splitlines()))


class Fe10RoundTripTests(unittest.TestCase):
    SOURCE = (
        "def helper(a):\n"
        "    v = UnitGetForce(a)\n"
        "    switch v:\n        case 0, 5:\n            return 1\n        default:\n            break\n"
        "    return 0\n\n"
        "def counter(a):\n    var n = 0\n    while n < a:\n        yield\n        ++n\n\n"
        '@on_rescue(pid1="PID_EDDIE", pid2=None, flag=1, name="F_RESCUE")\ndef rescued():\n'
        '    TalkEvent("MS_TEST")\n'
    )

    def test_decompile_compile_is_lossless(self):
        script = compile_source(self.SOURCE, dialect=FE10).script
        data = write_cmb(script)
        again = read_cmb(data)
        source, stats = decompile(again)
        self.assertEqual((stats.goto, stats.asm), (0, 0))
        self.assertIn("    switch v1:\n        case 0, 5:\n            return 1\n", source)
        self.assertIn("        ++v1\n", source)
        self.assertIn("@on_rescue(", source)
        self.assertEqual(write_cmb(compile_source(source, base=again).script), data)

    def test_trigger_kinds(self):
        kinds = triggers(FE10)
        self.assertEqual([p.name for p in kinds[14].params], ["name", "flag"])
        self.assertEqual({k.decorator for t, k in kinds.items() if t >= 17},
                         {"on_rescue", "on_give_take", "on_move_through", "on_epilogue"})
        spans = st.function_spans(self.SOURCE, FE10)
        self.assertEqual(spans[-1].trigger_type, 17)
        self.assertEqual(spans[-1].trigger_values["pid1"], "PID_EDDIE")
        self.assertEqual(st.function_spans(self.SOURCE)[-1].trigger_type, 0)  # unknown to Path of Radiance


class Fe10CatalogueTests(unittest.TestCase):
    def test_catalogue(self):
        externs = load_externs(FE10)
        self.assertEqual(sum(1 for e in externs.values() if e.source == "native"), 656)
        self.assertEqual(lookup_extern("StaffRoll", "fe10").argc, 0)
        self.assertEqual(lookup_extern("StaffRoll").argc, 1)
        self.assertEqual(lookup_extern("WaitM", "fe10").source, "script")  # a startup.cmb helper in RD

    def test_native_argc_mismatch_is_a_warning(self):
        result = compile_source("def f():\n    StaffRoll(1)\n", dialect=FE10)
        self.assertTrue(any("StaffRoll" in d.message for d in result.warnings))
        with self.assertRaises(CompileError):
            compile_source("def f():\n    UnitGetByPID()\n")

    def test_flag_table(self):
        table = event_flags.flag_table("fe10")
        self.assertEqual(table.slot_count, 128)
        self.assertEqual(len(event_flags.global_flags_vanilla(table)), 27)
        self.assertEqual(event_flags.slot_names(["a"], ["b"], 128)[127], "b")
        self.assertIsNone(event_flags.capacity_problem(27, 100, 128))
        self.assertIsNotNone(event_flags.capacity_problem(27, 100))


FILES = Path(os.environ.get("FE10_EXTRACTED_FILES", ""))


@unittest.skipUnless(os.environ.get("FE10_EXTRACTED_FILES"), "set FE10_EXTRACTED_FILES to an extracted RD files/ directory")
class Fe10VanillaCorpusTests(unittest.TestCase):
    def test_every_script_round_trips(self):
        paths = sorted((FILES / "Scripts").glob("*.cmb"))
        self.assertEqual(len(paths), 50)
        asm = 0
        for path in paths:
            with self.subTest(script=path.name):
                data = path.read_bytes()
                script = read_cmb(data)
                self.assertIs(script.dialect, FE10)
                self.assertEqual(write_cmb(script), data)
                source, stats = decompile(script, path.name)
                asm += stats.asm
                self.assertEqual(write_cmb(compile_source(source, base=script).script), data)
        self.assertLessEqual(asm, 1)

    def test_vanilla_global_flags(self):
        startup = FILES / "Scripts" / "startup.cmb"
        self.assertEqual(event_flags.global_flags_from_cmb(startup),
                         event_flags.global_flags_vanilla(event_flags.FE10_FLAGS))

    def test_catalogue_covers_every_call(self):
        """Every name vanilla calls is a native, a startup.cmb helper, an unregistered name the
        catalogue lists, or a function some script exports."""
        externs = load_externs(FE10)
        paths = sorted((FILES / "Scripts").glob("*.cmb"))
        modules = [parse(decompile(read_cmb(p.read_bytes()), p.name)[0]) for p in paths]
        exported = set().union(*(event_flags.exported_functions(m) for m in modules))
        missing = set()
        for module in modules:
            local = {fd.name for fd in module.functions}
            for call in event_flags._calls(module.functions):
                name = call.name
                if isinstance(name, str) and (call.extern or name not in local) and name not in exported \
                        and name not in ("streq", "strne") and name not in externs:
                    missing.add(name)
        self.assertEqual(missing, set())


if __name__ == "__main__":
    unittest.main()
