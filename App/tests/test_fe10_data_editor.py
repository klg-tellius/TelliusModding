"""Exercise form edits through the real FE10 data codec without opening a window."""
import struct
import sys
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import fe10data
from fe_modding.gui.fe10_data_editor import Fe10DataEditor
from tests.test_fe10data import _container


class BiorhythmFormTests(unittest.TestCase):
    def editor(self, text):
        data = _container(struct.pack(">40f", *([0.5] * 40)), [], [("BioData", 0)])
        return SimpleNamespace(
            kind="biorhythm", _tab="biorhythm", _selected={"biorhythm": 0},
            _vars={"value_0": Mock(get=Mock(return_value=text))},
            _data=data, _db=fe10data.Fe10Data({"biorhythm": fe10data.read_table(data, "biorhythm")}),
            _text=Fe10DataEditor._text, _replace=Mock(),
        )

    def test_decimal_edits_reach_the_binary_data(self):
        for value in ("1.25", "-2.5", "1e-2"):
            with self.subTest(value=value):
                editor = self.editor(value)
                with patch("fe_modding.gui.fe10_data_editor.messagebox.showerror") as error:
                    Fe10DataEditor._apply_field(editor, "value_0", 0)
                error.assert_not_called()
                editor._replace.assert_called_once()
                data = editor._replace.call_args.args[0]
                records = fe10data.read_table(data, "biorhythm")
                self.assertAlmostEqual(records[0].values["value_0"], float(value))
                self.assertEqual(records[0].values["value_1"], 0.5)
                self.assertEqual(records[1].values["value_0"], 0.5)

    def test_invalid_decimal_keeps_the_original_value(self):
        editor = self.editor("invalid")
        with patch("fe_modding.gui.fe10_data_editor.messagebox.showerror") as error:
            Fe10DataEditor._apply_field(editor, "value_0", 0)
        error.assert_called_once()
        editor._replace.assert_not_called()
        editor._vars["value_0"].set.assert_called_once_with("0.5")
