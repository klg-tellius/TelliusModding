"""The examples and function names of ``docs/app/agent-modding-api.md``, the guide for agents.

Without a disc: every Python block parses, every ``module:function`` the guide names exists, and
every ``from fe_modding... import`` of an example resolves. With ``FE9_EXTRACTED`` /
``FE10_EXTRACTED`` (the folders holding ``sys/`` and ``files/``): each ``# example:`` block runs on
a throwaway project that reads that disc and writes to a temporary folder.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import re
import tempfile
import unittest
from pathlib import Path

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "app" / "agent-modding-api.md"
BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)
#: `module:name` or `module:name`, `other` ... in the guide's tables (module relative to fe_modding)
REFERENCE = re.compile(r"`([a-z_][a-z0-9_.]*):([A-Za-z_][A-Za-z0-9_]*)`((?:, `[A-Za-z_][A-Za-z0-9_]*`)*)")


def _blocks() -> list[str]:
    return BLOCK.findall(GUIDE.read_text(encoding="utf-8"))


def _examples() -> dict[str, str]:
    found = {}
    for block in _blocks():
        match = re.match(r"# example: ([\w-]+)", block)
        if match:
            found[match.group(1)] = block
    return found


class GuideWithoutDiscTest(unittest.TestCase):
    def test_every_block_parses(self):
        blocks = _blocks()
        self.assertGreater(len(blocks), 5)
        for block in blocks:
            with self.subTest(block=block.splitlines()[0]):
                ast.parse(block)

    def test_examples_are_named_once(self):
        names = [re.match(r"# example: ([\w-]+)", b).group(1) for b in _blocks() if b.startswith("# example:")]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 8)

    def test_named_functions_exist(self):
        text = GUIDE.read_text(encoding="utf-8")
        checked = 0
        for match in REFERENCE.finditer(text):
            module_name, first, more = match.groups()
            module = importlib.import_module(f"fe_modding.{module_name}")
            for name in [first] + re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", more):
                with self.subTest(reference=f"{module_name}:{name}"):
                    self.assertTrue(hasattr(module, name), f"fe_modding.{module_name} has no {name}")
                checked += 1
        self.assertGreater(checked, 100)

    def test_example_imports_resolve(self):
        for name, block in _examples().items():
            for node in ast.walk(ast.parse(block)):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fe_modding"):
                    module = importlib.import_module(node.module)
                    for alias in node.names:
                        with self.subTest(example=name, name=f"{node.module}.{alias.name}"):
                            self.assertTrue(hasattr(module, alias.name)
                                            or importlib.util.find_spec(f"{node.module}.{alias.name}"))

    def test_shared_adapter_methods_exist(self):
        from fe_modding.game_adapter import DataAdapter
        from fe_modding.game_code.story_flow import StoryFlow
        text = GUIDE.read_text(encoding="utf-8")
        for name in set(re.findall(r"DataAdapter\.([a-z_]+)", text)):
            self.assertTrue(hasattr(DataAdapter, name), name)
        for name in ("set_next", "insert_after", "set_order", "remove", "order"):
            self.assertTrue(hasattr(StoryFlow, name), name)


#: examples that only read
READ_ONLY = {"check"}


def _session(project):
    from fe_modding.gui.changelog import ChangeLog
    from fe_modding.gui.fe8_session import Fe8DataSession, Fe10DataSession
    return (Fe10DataSession if project.profile.data_dialect == "fe10" else Fe8DataSession)(project, ChangeLog())


def _record(project, kind, record_id):
    session = _session(project)
    index = session.adapter.index_of(kind, record_id)
    if index is None:
        return None
    if getattr(session, "fe10", None) is not None:
        return session.fe10.tables[kind][index].values
    return vars(getattr(session.fe8, {"character": "characters", "item": "items"}[kind])[index])


def _common_text(project, key):
    from fe_modding.formats import message
    from fe_modding.game_profile import message_prefix
    path = project.files_root / "Mess" / f"{message_prefix(project)}common.m"
    return next((m.text for m in message.read_messages_path(path) if m.speaker == key), None)


def _check_shop(project):
    from fe_modding.formats import shop
    doc = shop.parse_shop(project.profile.shop_path(project.files_root, "n").read_bytes())
    return doc.shop("W", doc.chapters()[0]).items[-1] == "IID_STEELSWORD"


#: what each example must have changed, read back from the project's files
CHECKS = {
    "edit-character": lambda p: _record(p, "character", "PID_MICAIAH" if p.profile.data_dialect == "fe10"
                                        else "PID_IKE")["level"] == 5,
    "add-item": lambda p: _record(p, "item", "IID_AGENTBLADE")["might"] == 9
    and _common_text(p, "MIID_AGENTBLADE") == "Agent Blade",
    "add-character": lambda p: _record(p, "character", "PID_AGENT") is not None
    and _common_text(p, "MPID_AGENT") == "Agent",
    "edit-shop": _check_shop,
}


class _DiscExamples:
    """Runs each example on a new project over the disc in ``ENV``."""

    ENV = ""
    GAME = None

    def _project(self):
        from fe_modding.formats import game_text
        from fe_modding.game_files import OVERLAY_FILE, OverlayFiles
        from fe_modding.project import LAYOUT_OVERLAY, ModProject

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = ModProject.create(Path(tmp.name), "agent guide", self.GAME, layout=LAYOUT_OVERLAY)
        # the disc is read in place, never registered nor marked read-only
        project._files = OverlayFiles(Path(os.environ[self.ENV]), project.output_dir,
                                      project.directory / OVERLAY_FILE)
        game_text.use_for_extraction(project.files.at(""))
        return project

    def test_examples(self):
        for name, block in _examples().items():
            with self.subTest(example=name):
                project = self._project()
                exec(compile(block, f"<{GUIDE.name}: {name}>", "exec"), {"project": project})
                if name not in READ_ONLY:
                    self.assertTrue(project.files.changes(), f"{name} changed no file")
                if name in CHECKS:
                    self.assertTrue(CHECKS[name](project), f"{name}: the change is not in the files")


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED"), "set FE9_EXTRACTED to an extracted Path of Radiance disc")
class PorGuideExamplesTest(_DiscExamples, unittest.TestCase):
    ENV = "FE9_EXTRACTED"

    @property
    def GAME(self):
        from fe_modding.games import Game
        return Game.PATH_OF_RADIANCE


@unittest.skipUnless(os.environ.get("FE10_EXTRACTED"), "set FE10_EXTRACTED to an extracted Radiant Dawn disc")
class RdGuideExamplesTest(_DiscExamples, unittest.TestCase):
    ENV = "FE10_EXTRACTED"

    @property
    def GAME(self):
        from fe_modding.games import Game
        return Game.RADIANT_DAWN


if __name__ == "__main__":
    unittest.main()
