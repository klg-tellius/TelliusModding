import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.gui.prop_browser import MapObjectsPanel, PropBrowser


class _Tree:
    def __init__(self):
        self.rows = {}
        self._selection = ()
        self.seen = None

    def selection(self):
        return self._selection

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *rows):
        for row in rows:
            self.rows.pop(row, None)
        self._selection = ()

    def insert(self, _parent, _where, values):
        row = f"row{len(self.rows)}"
        self.rows[row] = values
        return row

    def selection_set(self, row):
        self._selection = (row,)

    def see(self, row):
        self.seen = row


class _Label:
    def __init__(self):
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


class _Paned:
    def __init__(self):
        self.positions = []

    def sashpos(self, sash, position):
        self.positions.append((sash, position))


class PropBrowserSelectionTests(unittest.TestCase):
    @staticmethod
    def _prop(name):
        obj = SimpleNamespace(flag_bits_b=0, effect_type=0, size_y=5, offset_y=0)
        return SimpleNamespace(map_name="bmap01", name=name, path=Path("map.cmp"), obj=obj,
                               instances=1, animated=False, footprint=(1, 1))

    def test_first_visible_object_is_selected(self):
        props = [self._prop("tree"), self._prop("barrel")]
        browser = SimpleNamespace(
            _map_labels={}, _tree=_Tree(), _rows={}, _props=props, _status=_Label(),
            selected=lambda: None, _visible=lambda: props,
        )

        PropBrowser._fill(browser)

        self.assertEqual(browser._tree.selection(), ("row0",))
        self.assertEqual(browser._tree.seen, "row0")
        self.assertEqual(browser._rows["row0"].name, "tree")

    def test_initial_sash_waits_for_layout_and_keeps_both_panes_visible(self):
        paned = _Paned()
        browser = SimpleNamespace(_sash_initialized=False, _paned=paned)

        PropBrowser._initialize_sash(browser, SimpleNamespace(width=1))
        self.assertEqual(paned.positions, [])

        PropBrowser._initialize_sash(browser, SimpleNamespace(width=800))
        self.assertEqual(paned.positions, [(0, 480)])
        self.assertTrue(browser._sash_initialized)

        PropBrowser._initialize_sash(browser, SimpleNamespace(width=1200))
        self.assertEqual(paned.positions, [(0, 480)])

    def test_clearing_selection_clears_the_definition_form(self):
        fields = {"offset_x": SimpleNamespace(value="old", set=lambda value: None)}
        toggles = [("flag_bits_a", 1, SimpleNamespace(value=True, set=lambda value: None))]
        panel = SimpleNamespace(
            _info=object(), _export=_Label(), _apply_button=_Label(), _vars=fields,
            _toggles=toggles, _form_status=_Label(),
        )

        MapObjectsPanel._selected(panel, None)

        self.assertIsNone(panel._info)
        self.assertEqual(panel._form_status.options["text"], "Select an object above.")


if __name__ == "__main__":
    unittest.main()
