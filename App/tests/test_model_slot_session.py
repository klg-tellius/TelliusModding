"""3D Models › New slot… / Model tables… write FE8Data.bin on disk (a character's animation ID): the
shared FE8Data.bin copy is saved before (on the user's yes) and read again after, so the next
Save FE8Data.bin from another page cannot undo the assignment."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from fe_modding.gui.model_viewer import ModelViewer


def _viewer(dirty: bool):
    calls = []
    session = SimpleNamespace(dirty=dirty, available=True, save=lambda: calls.append("save"),
                              revert=lambda: calls.append("revert"), on_saved=[lambda: calls.append("index")])
    return SimpleNamespace(_session=session), calls


class SlotSessionTests(unittest.TestCase):
    def test_clean_session_needs_no_save(self):
        viewer, calls = _viewer(dirty=False)
        self.assertTrue(ModelViewer._game_data_saved(viewer))
        self.assertEqual(calls, [])

    def test_unsaved_edits_are_saved_first_or_the_slot_waits(self):
        viewer, calls = _viewer(dirty=True)
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            self.assertTrue(ModelViewer._game_data_saved(viewer))
        self.assertEqual(calls, ["save"])
        viewer, calls = _viewer(dirty=True)
        with mock.patch("tkinter.messagebox.askyesno", return_value=False):
            self.assertFalse(ModelViewer._game_data_saved(viewer))
        self.assertEqual(calls, [])

    def test_the_written_file_is_read_again(self):
        viewer, calls = _viewer(dirty=False)
        ModelViewer._reload_game_data(viewer)
        self.assertEqual(calls, ["revert", "index"])


if __name__ == "__main__":
    unittest.main()
