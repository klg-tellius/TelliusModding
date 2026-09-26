import struct
import unittest
import zlib

from fe_modding.formats import event_flags as ef
from fe_modding.formats.cmb import compile_source
from fe_modding.formats.cmb.parser import parse

CHAPTER = '''
def RegistLocationFlags():
    regist("chest_1")
    regist("chest_2")

@export
def Startup():
    regist("boss_talk")
    RegistLocationFlags()
    regist("reinforcements")

def turn_two():
    if not get("reinforcements"):
        set("reinforcements")
    clr("chest_1")
    return get("G_フォルカ仲間")
'''


def build_gci(bits: bytes = bytes(ef.BIT_BYTES)) -> bytearray:
    """A .gci holding one 0x4000 save block at the first block position."""
    gci = bytearray(ef.GCI_HEADER_SIZE + 0x26000)
    b = ef.GCI_HEADER_SIZE + ef.BLOCK_OFFSETS[0]
    gci[b + 0x40:b + 0x50] = struct.pack(">4I", ef.SAVE_MAGIC, 0x20050201, 7, 0x4000)
    gci[b + 0x60] = 2
    gci[b + 0x70:b + 0x74] = b"SYSF"
    gci[b + 0xB8:b + 0xBC] = b"BMST"
    gci[b + ef.FLAGS_OFFSET:b + ef.FLAGS_OFFSET + ef.BIT_BYTES] = bits
    name_at = b + ef.FLAGS_OFFSET + ef.BIT_BYTES + 0x140
    gci[name_at:name_at + 6] = b"bmap05"
    crc = zlib.crc32(bytes(gci[b + 0x70:b + 0x4000]))
    gci[b + 0x50:b + 0x54] = crc.to_bytes(4, "big")
    return gci


class HashTests(unittest.TestCase):
    def test_matches_values_read_from_game_ram(self):
        self.assertEqual(ef.flag_hash("gf_complete"), 0x1425CC3D)
        self.assertEqual(ef.flag_hash("G_漆黒の騎士倒した"), 0x92E95D66)  # Shift-JIS, signed bytes
        self.assertEqual(ef.flag_hash("アイクボーレ"), 0xE04451CC)


class SlotTests(unittest.TestCase):
    def test_vanilla_globals_fill_slots_0_to_29(self):
        names = ef.global_flags_vanilla()
        self.assertEqual(len(names), 30)
        self.assertEqual(names[2], "gf_complete")
        self.assertEqual(names[27], "G_漆黒の騎士倒した")

    def test_locals_follow_startup_call_order_from_the_top(self):
        local = ef.local_flags(parse(CHAPTER))
        self.assertEqual(local, ["boss_talk", "chest_1", "chest_2", "reinforcements"])
        slots = ef.slot_names(ef.global_flags_vanilla(), local)
        self.assertEqual(slots[95], "boss_talk")
        self.assertEqual(slots[92], "reinforcements")
        self.assertIsNone(slots[91])

    def test_capacity_needs_one_free_slot(self):
        self.assertIsNone(ef.capacity_problem(30, 65))
        self.assertIn("unregister every global", ef.capacity_problem(30, 66))
        self.assertIn("silently ignored", ef.capacity_problem(30, 70))


class SaveTests(unittest.TestCase):
    def test_reads_bits_lsb_first(self):
        bits = bytearray(ef.BIT_BYTES)
        bits[3] = 0x20  # slot 29
        bits[11] = 0x80  # slot 95
        gci = build_gci(bytes(bits))
        (block,) = ef.save_blocks(bytes(gci))
        self.assertTrue(block.crc_ok)
        self.assertEqual(block.chapter_map, "bmap05")
        on = [i for i, v in enumerate(ef.read_flag_bits(bytes(gci), block)) if v]
        self.assertEqual(on, [29, 95])

    def test_write_re_signs_the_block(self):
        gci = build_gci()
        (block,) = ef.save_blocks(bytes(gci))
        bits = ef.read_flag_bits(bytes(gci), block)
        bits[27] = True
        ef.write_flag_bits(gci, block, bits)
        (again,) = ef.save_blocks(bytes(gci))
        self.assertTrue(again.crc_ok)
        self.assertTrue(ef.read_flag_bits(bytes(gci), again)[27])

    def test_detects_a_stale_crc(self):
        gci = build_gci()
        gci[ef.GCI_HEADER_SIZE + ef.BLOCK_OFFSETS[0] + ef.FLAGS_OFFSET] ^= 1
        (block,) = ef.save_blocks(bytes(gci))
        self.assertFalse(block.crc_ok)


class CompilerTests(unittest.TestCase):
    def flag_warnings(self, source, **kw):
        result = compile_source(source, **kw)
        return [str(d) for d in result.warnings if "regist" in str(d) or "global" in str(d) or "slot" in str(d)]

    def test_registered_and_global_names_are_quiet(self):
        self.assertEqual(self.flag_warnings(CHAPTER), [])

    def test_unregistered_name_warns(self):
        warnings = self.flag_warnings(CHAPTER.replace('clr("chest_1")', 'clr("chest_3")'))
        self.assertEqual(len(warnings), 1)
        self.assertIn('clr("chest_3") does nothing', warnings[0])

    def test_project_globals_replace_vanilla(self):
        warnings = self.flag_warnings(CHAPTER, global_flags=list(ef.ENGINE_FLAGS) + ["G_mod"])
        self.assertTrue(any('get("G_フォルカ仲間") always returns 0' in w for w in warnings))

    def test_global_outside_startup_warns(self):
        source = CHAPTER + '\ndef oops():\n    extern("global", "G_new")\n'
        self.assertTrue(any("outside startup.cmb" in w for w in self.flag_warnings(source)))

    def test_duplicate_regist_warns(self):
        source = CHAPTER.replace('regist("reinforcements")', 'regist("boss_talk")')
        self.assertTrue(any("runs twice" in w for w in self.flag_warnings(source)))


STARTUP = '''
@export
def RegistGlobalFlags():
    extern("global", "G_first")
    extern("global", "G_リザーブド")
    extern("global", "G_last")

@export
def Helper(a, b):
    return a + b
'''


class SourceEditTests(unittest.TestCase):
    def test_chapter_flag_goes_after_the_last_registration(self):
        source = ef.append_registration(CHAPTER, "Startup", "regist", "mod_new")
        self.assertEqual(ef.local_flags(parse(source))[-1], "mod_new")
        self.assertEqual(ef.local_flags(parse(source))[:-1], ef.local_flags(parse(CHAPTER)))
        lines = source.split("\n")
        at = lines.index('    regist("mod_new")')
        self.assertEqual(lines[at - 1], '    regist("reinforcements")')

    def test_registration_through_a_called_function_counts(self):
        source = CHAPTER.replace('    regist("reinforcements")\n', "")
        lines = ef.append_registration(source, "Startup", "regist", "mod_new").split("\n")
        self.assertEqual(lines[lines.index('    regist("mod_new")') - 1], "    RegistLocationFlags()")

    def test_campaign_flag_is_appended(self):
        source = ef.append_registration(STARTUP, "RegistGlobalFlags", "global", "G_mod")
        self.assertEqual(ef.global_flags(parse(source))[-2:], ["G_last", "G_mod"])
        self.assertIn('extern("global", "G_mod")', source)

    def test_rename_keeps_the_slot(self):
        site = ef.registration_sites(parse(STARTUP), "RegistGlobalFlags", "global")[1]
        source = ef.rename_registration(STARTUP, site, ef.RESERVED_GLOBAL, "G_mod")
        self.assertEqual(ef.global_flags(parse(source))[len(ef.ENGINE_FLAGS):], ["G_first", "G_mod", "G_last"])

    def test_uses_and_exports(self):
        uses = ef.flag_uses(parse(CHAPTER))
        self.assertIn(("turn_two", "set"), uses["reinforcements"])
        self.assertEqual(ef.exported_functions(parse(STARTUP)), {"RegistGlobalFlags": 0, "Helper": 2})

    def test_name_checks(self):
        self.assertIsNone(ef.check_flag_name("mod_ok", ["other"]))
        self.assertIn("already", ef.check_flag_name("other", ["other"]))
        self.assertIn("Shift-JIS", ef.check_flag_name("snow☃", []))

    def test_reordering_vanilla_globals_warns(self):
        vanilla = "def RegistGlobalFlags():\n" + "".join(
            f'    extern("global", "{name}")\n' for name, _ in ef.VANILLA_GLOBAL_FLAGS)
        self.assertFalse([d for d in compile_source(vanilla).warnings if "slot" in d.message])
        swapped = vanilla.replace('"G_シノン死亡"', '"G_tmp"').replace('"G_ガトリー死亡"', '"G_シノン死亡"')
        self.assertTrue([d for d in compile_source(swapped).warnings if "slot 8" in d.message])
        renamed = vanilla.replace('"G_リザーブド"', '"G_mod"', 1)
        self.assertFalse([d for d in compile_source(renamed).warnings if "slot" in d.message])


class ScriptSourceTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from fe_modding.formats.cmb import write_cmb

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        scripts = root / "extracted" / "files" / "Scripts"
        scripts.mkdir(parents=True)
        (scripts / "startup.cmb").write_bytes(write_cmb(compile_source(STARTUP).script))
        (scripts / "C05.cmb").write_bytes(write_cmb(compile_source(CHAPTER).script))

        class Project:
            directory = root
            extracted_dir = root / "extracted"

            @staticmethod
            def write_keeping_original(path, data):
                Path(path).write_bytes(data)

        self.project = Project()
        self.scripts = scripts

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_then_load_keeps_the_source(self):
        from fe_modding import script_sources

        path = self.scripts / "C05.cmb"
        loaded = script_sources.load(self.project, path)
        edited = ef.append_registration(loaded.source, "Startup", "regist", "mod_new") + "\n# a comment\n"
        script_sources.save(self.project, loaded, edited)
        again = script_sources.load(self.project, path)
        self.assertEqual(again.note, "your saved source")
        self.assertIn("# a comment", again.source)
        self.assertEqual(script_sources.peek(self.project, path), again.source)

    def test_chapter_compile_sees_project_globals_and_helpers(self):
        from fe_modding import script_sources

        context = script_sources.CompileContext.for_project(self.project)
        self.assertEqual(context.global_flags[-1], "G_last")
        self.assertEqual(context.helpers, {"RegistGlobalFlags": 0, "Helper": 2})
        self.assertEqual([p.name for p in script_sources.shared_scripts(self.project)], ["startup.cmb"])
        self.assertEqual(script_sources.chapter_script(self.project, "5").name, "C05.cmb")


if __name__ == "__main__":
    unittest.main()
