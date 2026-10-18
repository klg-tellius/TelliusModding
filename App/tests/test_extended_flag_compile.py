import unittest

from fe_modding.formats.extended_flags import FlagLayout, FlagCompileContext, HUB_ALIASES
from fe_modding.formats import event_flags as ef
from fe_modding.formats.cmb import compile_source, CompileError


def startup(names):
    return 'def Startup():\n' + ''.join(f'    regist("{name}")\n' for name in names)


class ExtendedCompileTests(unittest.TestCase):
    def test_hub_and_two_extra_flags_do_not_consume_vanilla_slots(self):
        # Chapter 17/C18: 30 globals + 58 locals, plus 18 hub aliases.
        globals_ = ef.global_flags_vanilla() + list(HUB_ALIASES)
        layout = FlagLayout().add("extra_a", "chapter", 18).add("extra_b", "chapter", 18)
        context = FlagCompileContext(layout, 18)
        names = [f"local_{i}" for i in range(58)] + ["extra_a", "extra_b"]
        result = compile_source(startup(names), global_flags=globals_, flag_context=context)
        self.assertEqual(result.diagnostics, [])
        self.assertEqual(context.vanilla_counts(globals_, names), (30, 58))
        legacy = compile_source(startup(names), global_flags=globals_)
        self.assertTrue(legacy.diagnostics)

    def test_explicit_assignment_required_and_vanilla_exhaustion_is_error(self):
        names = [f"local_{i}" for i in range(67)]
        with self.assertRaises(CompileError):
            compile_source(startup(names), flag_context=FlagCompileContext(FlagLayout(), 18))
        layout = FlagLayout()
        for name in names:
            layout = layout.add(name, "chapter", 18)
        self.assertEqual(compile_source(startup(names), flag_context=FlagCompileContext(layout, 18)).diagnostics, [])

    def test_wrong_chapter_missing_registration_tombstone_and_hub_local_rejected(self):
        layout = FlagLayout().add("extra", "chapter", 18)
        context = FlagCompileContext(layout, 18)
        for source in (startup(["other"]), startup(["extra", "extra"]), startup(["extra", "HUB_ACTIVE"])):
            with self.assertRaises(CompileError):
                compile_source(source, flag_context=context)
        with self.assertRaises(CompileError):
            compile_source(startup(["extra"]), flag_context=FlagCompileContext(layout))
        deleted = layout.delete(layout.entries[0])
        with self.assertRaises(CompileError):
            compile_source(startup(["extra"]), flag_context=FlagCompileContext(deleted, 18))

    def test_campaign_registration_required_and_manifest_does_not_change_bytecode(self):
        layout = FlagLayout().add("campaign_extra", "campaign")
        source = startup(["local_a"])
        with self.assertRaises(CompileError):
            compile_source(source, flag_context=FlagCompileContext(layout, 18))
        globals_ = ef.global_flags_vanilla() + ["campaign_extra"]
        plain = compile_source(source, global_flags=globals_)
        extended = compile_source(source, global_flags=globals_, flag_context=FlagCompileContext(layout, 18))
        from fe_modding.formats.cmb import write_cmb
        self.assertEqual(write_cmb(plain.script), write_cmb(extended.script))

    def test_startup_budget_and_fe10_rejection(self):
        from fe_modding.formats.cmb.model import FE10
        source = 'def RegistGlobalFlags():\n' + ''.join(f'    extern("global", "new_{i}")\n' for i in range(90))
        with self.assertRaises(CompileError):
            compile_source(source, flag_context=FlagCompileContext(FlagLayout()))
        with self.assertRaises(CompileError):
            compile_source(startup(["local_a"]), dialect=FE10,
                           flag_context=FlagCompileContext(FlagLayout(), 18))


if __name__ == "__main__":
    unittest.main()
