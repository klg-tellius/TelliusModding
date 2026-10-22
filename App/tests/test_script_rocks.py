"""Rolling-rock script edits used by the Build tab."""

import unittest

from fe_modding.formats.cmb import compile_source, script_rocks


class RockRouteTests(unittest.TestCase):
    def test_add_update_move_and_remove(self):
        source = "@export\ndef RegistLocationTT():\n    pass\n"
        source = script_rocks.set_route(source, 3, 4, 2, "668")
        self.assertEqual(script_rocks.routes(source)[0].tiles(), [(3, 4), (4, 4), (5, 4), (6, 4), (6, 3)])
        source = script_rocks.set_route(source, 3, 4, 8, "246")
        route = script_rocks.routes(source)[0]
        self.assertEqual((route.direction, route.path), (8, "246"))
        source = script_rocks.move_route(source, (3, 4), (5, 4))
        self.assertEqual((script_rocks.routes(source)[0].x, script_rocks.routes(source)[0].y), (5, 4))
        source = script_rocks.remove_route(source, (5, 4))
        self.assertEqual(script_rocks.routes(source), [])
        compile_source(source)

    def test_shared_path_gets_own_registration(self):
        source = ('@export\ndef RegistLocationTT():\n'
                  '    var p = TTPMEntry("666")\n'
                  '    SetRock(3, 4, 2, p)\n'
                  '    SetRock(9, 4, 2, p)\n')
        source = script_rocks.set_route(source, 3, 4, 8, "246")
        routes = script_rocks.routes(source)
        self.assertEqual([(route.path, route.direction) for route in routes], [("246", 8), ("666", 2)])
        compile_source(source)

    def test_invalid_path_rejected(self):
        with self.assertRaises(ValueError):
            script_rocks.set_route("", 1, 2, 2, "nope")

    def test_numeric_slot_and_new_registration_function(self):
        source = ('@export\ndef RegistLocationTT():\n'
                  '    TTPMEntry("66")\n'
                  '    SetRock(3, 4, 2, 0)\n')
        changed = script_rocks.set_route(source, 3, 4, 1, "44")
        self.assertIn('TTPMEntry("44")', changed)
        self.assertEqual(script_rocks.routes(changed)[0].path, "44")
        compile_source(changed)
        added = script_rocks.set_route("", 1, 2, 2, "66")
        self.assertEqual(script_rocks.routes(added)[0].function, "RegistLocationTT")
        compile_source(added)

    def test_removing_only_call_keeps_function_valid(self):
        source = '@export\ndef RegistLocationTT():\n    SetRock(3, 4, 2, 0)\n'
        removed = script_rocks.remove_route(source, (3, 4))
        self.assertIn('    pass', removed)
        compile_source(removed)

    def test_retail_layout_paths_in_startup_and_props_one_step_ahead(self):
        """Ch.25: Startup registers the paths in order; each SetRock in its own function names a slot,
        and its prop sits one step from the call in the initial direction."""
        source = ('@export\ndef Startup():\n    TTPMInit()\n    TTPMEntry("6622")\n    TTPMEntry("2244")\n\n'
                  'def func_4():\n    SetRock(4, 11, 2, 0)\n\n'
                  'def func_5():\n    SetRock(7, 6, 4, 1)\n')
        found = script_rocks.routes(source)
        self.assertEqual([(r.path, r.prop_tile) for r in found], [("6622", (5, 11)), ("2244", (7, 7))])
        self.assertEqual(len(script_rocks.route_for_prop(source, (5, 11))), 1)
        self.assertEqual(script_rocks.route_for_prop(source, (4, 11)), [])
        changed = script_rocks.set_prop_route(source, (7, 7), 2, "66")   # now starts to the right
        route = script_rocks.route_for_prop(changed, (7, 7))[0]
        self.assertEqual(((route.x, route.y), route.direction, route.path), ((6, 7), 2, "66"))
        self.assertIn('TTPMEntry("66")', changed)
        compile_source(changed)
        moved = script_rocks.move_prop_route(changed, (5, 11), (6, 11))
        self.assertEqual([(r.x, r.y) for r in script_rocks.route_for_prop(moved, (6, 11))], [(5, 11)])
        removed = script_rocks.remove_prop_route(moved, (6, 11))
        self.assertEqual(script_rocks.route_for_prop(removed, (6, 11)), [])
        compile_source(removed)
        added = script_rocks.set_prop_route("", (3, 3), 4, "222")
        self.assertEqual([(r.x, r.y) for r in script_rocks.routes(added)], [(3, 2)])

    def test_retail_path_length_is_allowed(self):
        path = "2226662224444226666222444442424242222222"  # 40 steps, the longest in Ch.25
        self.assertEqual(script_rocks.routes(script_rocks.set_route("", 1, 2, 2, path))[0].path, path)


if __name__ == "__main__":
    unittest.main()
