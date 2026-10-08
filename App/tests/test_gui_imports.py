"""Every module of the app imports: GUI modules are often imported only when a button is pressed, so a
syntax or import error there would otherwise show up as a button that does nothing."""

import importlib
import pkgutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fe_modding


class ImportEveryModule(unittest.TestCase):
    def test_every_module_imports(self):
        try:
            import tkinter  # noqa: F401
        except ImportError:
            self.skipTest("needs Tkinter")
        failed = []
        for info in pkgutil.walk_packages(fe_modding.__path__, "fe_modding."):
            if info.name.endswith("__main__"):
                continue
            try:
                importlib.import_module(info.name)
            except Exception as exc:  # noqa: BLE001 - collect them all
                failed.append(f"{info.name}: {type(exc).__name__}: {exc}")
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
