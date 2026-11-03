import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import rig_contract, rig_fit
from fe_modding.formats import animation
from fe_modding.gui import model_viewer as mv

FILES = os.environ.get("FE9_EXTRACTED_FILES")


def _anim(events):
    header = animation.GaHeader(words=(0, 0, 0, 0x11, 0, 1, 10, 0, 0, 0, 0, 0))
    curves = [animation.AnimCurve(0, 3, 4, 10, [animation.Keyframe(0, 0), animation.Keyframe(10, 16)])]
    anim = animation.GaAnimation(header, [animation.BoneGroup(0, 16, 0, 1)], curves)
    data = animation.write_animation(anim)
    return rig_contract.replace_events(data, events) if events else data


class EventTests(unittest.TestCase):
    def test_replace_events_round_trips(self):
        events = [animation.EventKey(8, (1,)), animation.EventKey(3, (22, 1510)), animation.EventKey(9, (0,))]
        data = _anim(events)
        read = animation.read_animation_bytes(data).events
        self.assertEqual([(e.frame, e.codes) for e in read], [(3, (22, 1510)), (8, (1,)), (9, (0,))])
        cleared = animation.read_animation_bytes(rig_contract.replace_events(data, [])).events
        self.assertEqual(cleared, [])

    def test_missing_combat_codes_are_errors(self):
        vanilla = _anim([animation.EventKey(5, (1,)), animation.EventKey(6, (0, 2510))])
        self.assertEqual(rig_contract.event_errors("at1", vanilla, vanilla), [])
        only_sound = _anim([animation.EventKey(6, (2510,))])
        errors = rig_contract.event_errors("at1", only_sound, vanilla)
        self.assertEqual(len(errors), 1)
        self.assertIn("0 (", errors[0])
        self.assertIn("1 (", errors[0])
        # an animation whose original has none needs none
        self.assertEqual(rig_contract.event_errors("dam", only_sound, _anim([])), [])


class NamingTests(unittest.TestCase):
    def test_fallback_uses_base_clip_then_same_role_of_another_weapon(self):
        available = {"fig1_cr1_ax": "fig1_cr1_ax", "fig1_dam_ax": "fig1_dam_ax", "fig1_poi_ax@ha": "x"}
        self.assertEqual(mv._fallback_animation("fig1_cr1_ax_at1", available), "fig1_cr1_ax")
        self.assertEqual(mv._fallback_animation("fig1_dam_no", available), "fig1_dam_ax")
        self.assertIsNone(mv._fallback_animation("fig1_poi_no", available))
        self.assertIsNone(mv._fallback_animation("fig1_ded_no", available))

    def test_kit_names_split_only_differing_duplicates(self):
        entries = [("a_dam_ax.ga", "ax", b"1"), ("a_dam_ax.ga", "ha", b"1"), ("a_poi_ax.ga", "ax", b"1"),
                   ("a_poi_ax.ga", "ha", b"2")]
        names = sorted(n for n, *_ in mv.kit_animation_names(entries))
        self.assertEqual(names, ["a_dam_ax", "a_poi_ax@ax", "a_poi_ax@ha"])

    def test_role_descriptions(self):
        self.assertEqual(rig_contract.describe_role("ax_必殺1_攻撃1"), "ax: critical 1, then attack 1")
        self.assertEqual(rig_contract.describe_battle_file("fig1_cr1_ax_at1"), "critical 1, followed by attack 1")
        self.assertEqual(rig_contract.describe_map_file("atk1_AX"), "attack")


@unittest.skipUnless(FILES, "set FE9_EXTRACTED_FILES to the extracted disc's files folder")
class DiscRigKitTests(unittest.TestCase):
    def test_fighter_kit_lists_roles_weapons_and_required_events(self):
        files = Path(FILES)
        roles = rig_contract.read_battle_roles((files / "zdbx.cmp").read_bytes(), "fig1")
        self.assertIn(("ax_必殺1_攻撃1", "fig1_cr1_ax_at1"), roles)
        self.assertEqual(len(roles), 39)
        with tempfile.TemporaryDirectory() as tmp:
            written = mv.export_rig_kit(files / "ymu/fighter/pack.cmp", Path(tmp) / "fighter.glb")
            sheet = written[1].read_text(encoding="utf-8")
            self.assertIn("`_s1_`", sheet)
            self.assertIn("`wait_AX`: shows Ax", sheet)
            written = mv.export_rig_kit(files / "zu/fig1/fig1_ax.pak", Path(tmp) / "fig1.glb")
            sheet = written[1].read_text(encoding="utf-8")
            self.assertIn("`_r_hand_`", sheet)
            self.assertIn("**0**", sheet)
            self.assertIn("ax: critical 1, then attack 1", sheet)


@unittest.skipUnless(FILES, "set FE9_EXTRACTED_FILES to the extracted disc's files folder")
class DiscRigFitTests(unittest.TestCase):
    def test_a_set_fitted_onto_its_own_rig_maps_each_bone_to_itself(self):
        import json
        import struct

        files = Path(FILES)
        container = files / "ymu/fighter/pack.cmp"
        glb, _bones, _named = mv.rig_kit_glb(container)
        # the kit as a "foreign" model: anchors renamed (a model may not use anchor names)
        n = struct.unpack_from("<I", glb, 12)[0]
        doc = json.loads(glb[20:20 + n])
        for node in doc["nodes"]:
            if rig_fit.is_anchor(node.get("name", "")):
                node["name"] = "x" + node["name"]
        js = json.dumps(doc).encode()
        js += b" " * (-len(js) % 4)
        rest = glb[20 + n:]
        model_glb = struct.pack("<III", 0x46546C67, 2, 20 + len(js) + len(rest)) + struct.pack("<II", len(js), 0x4E4F534A) + js + rest
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "model.glb"
            model_path.write_bytes(model_glb)
            setup = mv.prepare_rig_fit(container, model_path)
            self.assertEqual(setup.weapon_bones, {"Ax", "Ax1"})
            for name in ("Hip", "L_arm1", "L_arm2", "L_hand", "R_leg1", "L_foot"):
                self.assertEqual(setup.mapping[name], name)
            # the right hand holds the axe mesh, which the guess takes for the hand: fixed by hand,
            # as in the mapping dialog
            mapping = dict(setup.mapping, R_arm1="R_arm1", R_arm2="R_arm2", R_hand="R_hand")
            result = mv.fit_new_rig(container, setup, mapping)
        self.assertIn(container, result.outputs)
        self.assertGreater(len(result.outputs), 20)  # the pack and every loose animation


if __name__ == "__main__":
    unittest.main()
