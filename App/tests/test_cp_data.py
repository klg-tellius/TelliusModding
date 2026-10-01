import os
import struct
import unittest
from pathlib import Path

from fe_modding.formats import cp_data as cp
from fe_modding.formats.cp_data import Entry, HealRecord, MType, Script, Section, SectionRef


def _doc() -> cp.CpDocument:
    head = Section(cp.HEAD_SECTION, [0, "2005/01/01 00:00:00", "author", SectionRef("TBL_STEALITEMS"),
                                      SectionRef("MTYPE_A"), SectionRef("SEQ_ATK"), SectionRef("SEQ_MOV"),
                                      SectionRef("SEQ_HEAL"), SectionRef("ATK_SEQID_LIST")])
    steal = Section("TBL_STEALITEMS", ["IID_VULNERARY", "IID_ELIXIR", 0])
    route = Section("TBL_MAP01_ROUTE", [(3 << 16) | 4, (5 << 16) | 6, 0xFFFF0000])
    pids = Section("TBL_PID_IKE", ["PID_IKE", 0])
    mtype = Section("MTYPE_A", [])
    cp.write_mtype(mtype, MType("MTYPE_A", {k: i for i, k in enumerate(cp.MTYPE_FIELD_NAMES)}))
    atk, mov, heal = Section("SEQ_ATK", []), Section("SEQ_MOV", []), Section("SEQ_HEAL", [])
    cp.write_script(atk, Script("SEQ_ATK", 0, [Entry(101, 100, 0xFFFF, 0, 0, SectionRef("TBL_PID_IKE")),
                                               Entry(0, 0, 0xFFFF, 99), Entry(1001)]))
    cp.write_script(mov, Script("SEQ_MOV", 0, [Entry(216, 0, 0xFFFF, 4, 0, SectionRef("TBL_MAP01_ROUTE")),
                                               Entry(1001)]))
    cp.write_heal(heal, HealRecord("SEQ_HEAL", 0, 50, 100, 1))
    lists = [Section("ATK_SEQID_LIST", ["SEQ_ATK", 0]), Section("MOV_SEQID_LIST", ["SEQ_MOV", 0]),
             Section("HEAL_SEQID_LIST", ["SEQ_HEAL", 0]), Section("MTYPE_TABLEID_LIST", ["MTYPE_A", 0])]
    return cp.CpDocument([head, steal, route, pids, mtype, atk, mov, heal] + lists, [])


class CpDataTests(unittest.TestCase):
    def test_build_then_parse_keeps_every_section(self):
        doc = _doc()
        data = cp.build_cp_data(doc)
        parsed = cp.parse_cp_data(data)
        self.assertEqual([(s.name, s.words) for s in parsed.sections], [(s.name, s.words) for s in doc.sections])
        self.assertEqual(cp.build_cp_data(parsed), data)
        size, pool_end, relocations, count = struct.unpack_from(">4I", data, 0)
        self.assertEqual((size, count), (len(data), len(doc.sections)))
        table = pool_end + 0x20 + 4 * relocations
        names = data[table + 8 * count:].split(b"\0")[:count]
        self.assertEqual(names, sorted(names))

    def test_typed_views(self):
        doc = cp.parse_cp_data(cp.build_cp_data(_doc()))
        script = cp.read_script(doc.section("SEQ_ATK"))
        self.assertEqual([e.op_name for e in script.entries], ["ATTACK", "LABEL", "END"])
        self.assertEqual(script.entries[0].e, SectionRef("TBL_PID_IKE"))
        self.assertEqual(cp.script_labels(script), [99])
        self.assertEqual(cp.read_heal(doc.section("SEQ_HEAL")), HealRecord("SEQ_HEAL", 0, 50, 100, 1))
        self.assertEqual(cp.read_mtype(doc.section("MTYPE_A")).values["terrain"], cp.MTYPE_FIELD_NAMES.index("terrain"))
        self.assertEqual(cp.read_route(doc.section("TBL_MAP01_ROUTE")), [(3, 4), (5, 6)])
        self.assertEqual(cp.read_list(doc.section("TBL_STEALITEMS")), ["IID_VULNERARY", "IID_ELIXIR"])
        self.assertEqual(cp.id_problems(doc), [])

    def test_signed_mtype_bytes_and_negative_ops(self):
        section = Section("MTYPE_X", [])
        values = {k: 0 for k in cp.MTYPE_FIELD_NAMES}
        values["terrain"] = -5
        cp.write_mtype(section, MType("MTYPE_X", values))
        self.assertEqual(cp.read_mtype(section).values["terrain"], -5)
        self.assertEqual(Entry.from_words([0xFFFFFFFE, 0, 0, 0, 0, "x", 0]).op, -2)

    def test_edit_grow_and_add_script(self):
        doc = _doc()
        route = doc.section("TBL_MAP01_ROUTE")
        cp.write_route(route, [(1, 1), (2, 2), (3, 3)])
        section = Section("SEQ_NEW", [])
        cp.write_script(section, Script("SEQ_NEW", cp.add_to_id_list(doc, "ATK_SEQID_LIST", "SEQ_NEW"),
                                        [Entry(1001)]))
        doc.sections.append(section)
        parsed = cp.parse_cp_data(cp.build_cp_data(doc))
        self.assertEqual(cp.read_route(parsed.section("TBL_MAP01_ROUTE")), [(1, 1), (2, 2), (3, 3)])
        self.assertEqual(cp.attack_scripts(parsed), ["SEQ_ATK", "SEQ_NEW"])
        self.assertEqual(cp.id_problems(parsed), [])
        # the script pointing at the route follows it to its new address
        move = cp.read_script(parsed.section("SEQ_MOV"))
        self.assertEqual(move.entries[0].e, SectionRef("TBL_MAP01_ROUTE"))

    def test_id_problem_and_rename(self):
        doc = _doc()
        cp.write_heal(doc.section("SEQ_HEAL"), HealRecord("SEQ_HEAL", 3, 50, 100, 1))
        self.assertEqual(len(cp.id_problems(doc)), 1)
        cp.rename_section(doc, "SEQ_MOV", "SEQ_WALK")
        self.assertEqual(cp.move_scripts(doc), ["SEQ_WALK"])
        self.assertEqual(doc.section("SEQ_WALK").words[5], "SEQ_WALK")
        self.assertEqual(doc.section(cp.HEAD_SECTION).words[6], SectionRef("SEQ_WALK"))
        with self.assertRaises(ValueError):
            cp.rename_section(doc, "SEQ_ATK", "SEQ_WALK")

    def test_dangling_pointer_is_refused(self):
        doc = _doc()
        doc.sections.remove(doc.section("TBL_PID_IKE"))
        with self.assertRaises(ValueError):
            cp.build_cp_data(doc)


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class DiscCpDataTests(unittest.TestCase):
    def setUp(self):
        self.data = (Path(os.environ["FE9_EXTRACTED_FILES"]) / "cp_data.bin").read_bytes()
        self.doc = cp.parse_cp_data(self.data)

    def test_vanilla_round_trips_byte_for_byte(self):
        self.assertEqual(len(self.doc.sections), 134)
        self.assertEqual(cp.build_cp_data(self.doc), self.data)

    def test_every_section_has_a_typed_reading(self):
        scripts = heals = mtypes = 0
        for section in self.doc.sections:
            if cp.is_script_section(section):
                scripts += 1
                script = cp.read_script(section)
                for entry in script.entries:
                    self.assertIn(entry.op, cp.OPCODES, section.name)
                cp.write_script(Section(section.name, []), script)
            elif cp.is_heal_section(section):
                heals += 1
                cp.read_heal(section)
            elif cp.is_mtype_section(section):
                mtypes += 1
                cp.read_mtype(section)
        self.assertEqual((scripts, heals, mtypes), (69, 6, 32))
        self.assertEqual(len(cp.attack_scripts(self.doc)) + len(cp.move_scripts(self.doc)), 69)
        self.assertEqual(cp.id_problems(self.doc), [])

    def test_typed_edit_writes_back_identically(self):
        for section in self.doc.sections:
            before = list(section.words)
            if cp.is_script_section(section):
                cp.write_script(section, cp.read_script(section))
            elif cp.is_heal_section(section):
                cp.write_heal(section, cp.read_heal(section))
            elif cp.is_mtype_section(section):
                cp.write_mtype(section, cp.read_mtype(section))
            elif cp.is_route_section(section):
                cp.write_route(section, cp.read_route(section))
            self.assertEqual(section.words, before, section.name)

    def test_head_points_at_the_defaults(self):
        head = self.doc.section(cp.HEAD_SECTION).words
        self.assertEqual(head[3:], [SectionRef("TBL_STEALITEMS"), SectionRef("MTYPE_NORMAL"),
                                    SectionRef("SEQ_NOATTACK"), SectionRef("SEQ_NOMOVE"),
                                    SectionRef("SEQ_NOHEAL"), SectionRef("ATK_SEQID_LIST")])
        self.assertEqual(head[2], "hiroto-murakami")


if __name__ == "__main__":
    unittest.main()
