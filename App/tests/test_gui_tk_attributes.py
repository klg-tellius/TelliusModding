"""No GUI widget class assigns an attribute Tk uses itself.

``self._name`` is the widget's name in its parent's ``children``: a dialog that stored a StringVar
there raised TypeError on every close (``destroy`` looks it up). ``self._root`` hid ``Misc._root()``,
which ``nametowidget`` calls. Other classes (a cache, a helper) may use these names freely."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

GUI = Path(__file__).resolve().parents[1] / "fe_modding" / "gui"
RESERVED = {"_name", "_w", "_root", "tk", "master", "children", "_tclCommands", "widgetName"}
#: Base-class names that make a class a Tk widget (directly or through the app's own widgets).
WIDGET_HINTS = ("Toplevel", "Frame", "Tk", "Canvas", "Label", "Button", "Entry", "Text", "Listbox", "Notebook",
                "Panel", "Page", "Window", "Dialog", "Widget", "Misc", "Scale", "Spinbox", "Combobox", "Treeview")


def _base_names(node: ast.ClassDef) -> list[str]:
    names = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


class TkAttributeTests(unittest.TestCase):
    def test_widgets_leave_tk_attributes_alone(self):
        problems = []
        for path in sorted(GUI.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
                if not any(hint in name for name in _base_names(cls) for hint in WIDGET_HINTS):
                    continue
                for node in ast.walk(cls):
                    targets = node.targets if isinstance(node, ast.Assign) else (
                        [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else [])
                    for target in targets:
                        if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                                and target.value.id == "self" and target.attr in RESERVED):
                            problems.append(f"{path.relative_to(GUI)}:{node.lineno} {cls.name} sets self.{target.attr}")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
