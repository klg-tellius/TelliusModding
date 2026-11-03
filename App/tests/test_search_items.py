"""The Ctrl+K palette lists every Game Data tab."""
import types
import unittest

from fe_modding.gui.pages.data import TABS
from fe_modding.gui.shell import Shell


class SearchItemsTests(unittest.TestCase):
    def test_every_game_data_tab_is_listed(self):
        fake = types.SimpleNamespace(_asset_tools=[], index=None)
        routes = {route for _kind, _label, _detail, route in Shell.search_items(fake)}
        for key in TABS:
            self.assertIn(("data", key), routes)


if __name__ == "__main__":
    unittest.main()
