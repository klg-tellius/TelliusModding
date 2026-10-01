import os
import tempfile
import unittest
from pathlib import Path

from fe_modding.formats import effect_registry as er
from fe_modding.formats import effects


def _registry() -> bytes:
    return er.build_effect_registry([
        er.make_record("EID_ZETA", 0x04000500),
        er.make_record("EID_ALPHA", 0x02050500, "EID_ZETA"),
    ])


def _pack(name: str, tpl: bool = True) -> bytes:
    parts = {f"{name}.g": b"g" * 40, f"{name}.gs": b"s" * 50, f"{name}.ga": b"a" * 60}
    if tpl:
        parts[f"{name}.tpl"] = b"t" * 70
    return effects.build_effect_pack(parts)


class RegistryBuildTests(unittest.TestCase):
    def test_round_trip_keeps_records(self):
        recs = er.read_effect_registry(_registry())
        self.assertEqual([r.eid_name for r in recs], ["EID_ZETA", "EID_ALPHA"])
        self.assertEqual(recs[1].next_in_chain, "EID_ZETA")
        self.assertEqual(recs[0].flags, 0x04000500)
        self.assertEqual(er.build_effect_registry(recs), _registry())

    def test_add_record_appends_and_fixes_pointers(self):
        out = effects.add_registry_record(_registry(), "EID_MID", flags=0x05000500, next_in_chain="EID_ALPHA")
        recs = er.read_effect_registry(out)
        self.assertEqual([r.eid_name for r in recs], ["EID_ZETA", "EID_ALPHA", "EID_MID"])
        self.assertEqual(er.chain(recs, "EID_MID"), ["EID_MID", "EID_ALPHA", "EID_ZETA"])

    def test_add_rejects_duplicates_bad_names_and_bad_chain(self):
        with self.assertRaises(effects.EffectError):
            effects.add_registry_record(_registry(), "EID_ZETA", flags=0)
        with self.assertRaises(effects.EffectError):
            effects.add_registry_record(_registry(), "fire", flags=0)
        with self.assertRaises(effects.EffectError):
            effects.add_registry_record(_registry(), "EID_NEW", flags=0, next_in_chain="EID_NOPE")


class PackTests(unittest.TestCase):
    def test_round_trip_and_validate(self):
        parts = effects.read_effect_pack(_pack("EID_X"))
        self.assertEqual(list(parts), ["EID_X.g", "EID_X.gs", "EID_X.ga", "EID_X.tpl"])
        self.assertEqual(effects.validate_pack(parts), "EID_X")

    def test_validate_rejects_incomplete(self):
        with self.assertRaises(effects.EffectError):
            effects.validate_pack({"EID_X.g": b"", "EID_X.gs": b""})

    def test_rename_and_replace_part(self):
        parts = effects.rename_pack(effects.read_effect_pack(_pack("EID_X")), "EID_Y")
        self.assertEqual(effects.validate_pack(parts), "EID_Y")
        swapped = effects.replace_part(parts, "tpl", b"new")
        self.assertEqual(swapped["EID_Y.tpl"], b"new")
        self.assertEqual(list(swapped), list(parts))
        added = effects.replace_part({"EID_Y.g": b"1"}, "tpl", b"2")
        self.assertEqual(added["EID_Y.tpl"], b"2")

    def test_not_a_pack(self):
        with self.assertRaises(effects.EffectError):
            effects.read_effect_pack(b"junk")


class ListTests(unittest.TestCase):
    def test_lists_registered_and_orphans(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = Path(tmp)
            (files / "yme").mkdir()
            effects.registry_path(files).write_bytes(_registry())
            effects.pack_path(files, "EID_ALPHA").write_bytes(_pack("EID_ALPHA"))
            effects.pack_path(files, "EID_ORPHAN").write_bytes(_pack("EID_ORPHAN", tpl=False))
            got = {e.name: e for e in effects.list_effects(files)}
        self.assertEqual(set(got), {"EID_ALPHA", "EID_ZETA", "EID_ORPHAN"})
        self.assertTrue(got["EID_ALPHA"].registered and got["EID_ALPHA"].has_pack)
        self.assertFalse(got["EID_ZETA"].has_pack)
        self.assertFalse(got["EID_ORPHAN"].registered)
        self.assertEqual(got["EID_ALPHA"].next_in_chain, "EID_ZETA")


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "FE9_EXTRACTED_FILES not set")
class CorpusTests(unittest.TestCase):
    def test_vanilla_registry_rebuilds_identically(self):
        data = effects.registry_path(Path(os.environ["FE9_EXTRACTED_FILES"])).read_bytes()
        self.assertEqual(er.build_effect_registry(er.read_effect_registry(data)), data)

    def test_vanilla_packs_repack_to_same_parts(self):
        for p in sorted((Path(os.environ["FE9_EXTRACTED_FILES"]) / "yme").glob("EID_*.cmp"))[:20]:
            parts = effects.read_effect_pack(p.read_bytes())
            self.assertEqual(effects.read_effect_pack(effects.build_effect_pack(parts)), parts, p.name)


if __name__ == "__main__":
    unittest.main()
