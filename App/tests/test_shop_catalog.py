"""The Shops tab's item catalogue for each game's database session."""

import unittest
from types import SimpleNamespace

from fe_modding.gui.shop_editor import ShopEditor


def _editor(session):
    """The parts of ShopEditor that _refresh_catalog uses."""
    return SimpleNamespace(_session_provider=lambda: session, _index_provider=lambda: None, _subscribed=session,
                           _picker_boxes=[], _forge_boxes=[], _forge_checks={})


class ShopCatalogTests(unittest.TestCase):
    def test_radiant_dawn_items_build_the_catalogue(self):
        item = SimpleNamespace(values={"iid": "IID_BRONZESWORD", "price": 7, "uses": 50, "icon": 21,
                                       "weapon_type": "sword"})
        session = SimpleNamespace(available=True, fe8=None, fe10=SimpleNamespace(tables={"item": [item]}))
        editor = _editor(session)
        ShopEditor._refresh_catalog(editor)
        self.assertEqual(editor._prices, {"IID_BRONZESWORD": 350})
        self.assertEqual(editor._weapon, {"IID_BRONZESWORD": "sword"})
        self.assertIs(editor._items["IID_BRONZESWORD"].record, item)


if __name__ == "__main__":
    unittest.main()
