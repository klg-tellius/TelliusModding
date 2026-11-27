"""3D Models › New character model: New slot, then Fit new rig on the new slot."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from fe_modding.gui import model_viewer as mv
except ImportError as exc:  # no tkinter
    mv = None
    SKIP = str(exc)


class _Dialog:
    def __init__(self, result, new_label):
        self.result, self.new_label = result, new_label


@unittest.skipIf(mv is None, "tkinter is not available")
class NewCharacterModelTests(unittest.TestCase):
    def _viewer(self, new_label):
        viewer = object.__new__(mv.ModelViewer)
        viewer._project = object()
        viewer._changelog = mock.Mock()
        viewer._selected_set = lambda: ("zu/fig1", Path("zu/fig1/fig1_ax.pak"))
        viewer._game_data_saved = lambda: True
        viewer._reload_game_data = mock.Mock()
        viewer._load_set_list = mock.Mock()
        viewer._all_sets = [("zu/fig1", Path("zu/fig1/fig1_ax.pak")), ("zu/ces1", Path("zu/ces1/ces1_ax.pak"))]
        viewer._select_set = mock.Mock()
        viewer._fit_rig_onto = mock.Mock()
        viewer.wait_window = lambda dialog: None
        dialog = _Dialog("New battle model zu/ces1 (copy of fig1), used by PID_BOLE as JID_FIGHTER", new_label)
        return viewer, dialog

    def test_the_model_is_fitted_onto_the_new_slot(self):
        viewer, dialog = self._viewer("zu/ces1")
        with mock.patch.object(mv.filedialog, "askopenfilename", return_value="/tmp/hero.glb"), \
                mock.patch.object(mv, "_NewSlotDialog", return_value=dialog):
            viewer._new_character_model()
        viewer._changelog.append.assert_called_once_with("zu/fig1", dialog.result)
        viewer._select_set.assert_called_once_with("zu/ces1")
        viewer._fit_rig_onto.assert_called_once_with("zu/ces1", Path("zu/ces1/ces1_ax.pak"), Path("/tmp/hero.glb"))

    def test_a_slot_sharing_the_source_files_is_not_fitted(self):
        viewer, dialog = self._viewer("zu/fig1")
        with mock.patch.object(mv.filedialog, "askopenfilename", return_value="/tmp/hero.glb"), \
                mock.patch.object(mv, "_NewSlotDialog", return_value=dialog), \
                mock.patch.object(mv.messagebox, "showinfo") as info:
            viewer._new_character_model()
        info.assert_called_once()
        viewer._fit_rig_onto.assert_not_called()

    def test_cancelling_the_slot_stops_before_the_fit(self):
        viewer, dialog = self._viewer("zu/ces1")
        dialog.result = None
        with mock.patch.object(mv.filedialog, "askopenfilename", return_value="/tmp/hero.glb"), \
                mock.patch.object(mv, "_NewSlotDialog", return_value=dialog):
            viewer._new_character_model()
        viewer._fit_rig_onto.assert_not_called()
        viewer._changelog.append.assert_not_called()


if __name__ == "__main__":
    unittest.main()
