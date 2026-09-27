"""The Script editor's context-aware completion (fe_modding.script_suggestions)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fe_modding import script_suggestions as ss
from fe_modding.formats.cmb.catalog import load_externs


def _project(extracted: Path):
    return SimpleNamespace(extracted_dir=extracted)


class ArgContextTests(unittest.TestCase):
    def test_first_argument(self):
        ctx = ss.arg_context('    MoviePlay(')
        self.assertEqual((ctx.function, ctx.index, ctx.in_string, ctx.partial), ("MoviePlay", 0, False, ""))

    def test_inside_string(self):
        ctx = ss.arg_context('    MoviePlay("Movie/op')
        self.assertEqual((ctx.function, ctx.index, ctx.in_string, ctx.partial), ("MoviePlay", 0, True, "Movie/op"))

    def test_later_argument_and_nesting(self):
        ctx = ss.arg_context('    UnitMove(UnitGetByPID("PID_IKE"), 3, ')
        self.assertEqual((ctx.function, ctx.index), ("UnitMove", 2))
        ctx = ss.arg_context('    UnitMove(UnitGetByPID("PID_I')
        self.assertEqual((ctx.function, ctx.index, ctx.partial), ("UnitGetByPID", 0, "PID_I"))

    def test_commas_and_parens_in_strings_are_ignored(self):
        ctx = ss.arg_context('    Foo("a, (b", ')
        self.assertEqual((ctx.function, ctx.index), ("Foo", 1))

    def test_outside_calls_and_comments(self):
        self.assertIsNone(ss.arg_context("    x = 1"))
        self.assertIsNone(ss.arg_context("    Fade(1, 2)"))
        self.assertIsNone(ss.arg_context("    # MoviePlay("))

    def test_kinds(self):
        externs = load_externs()
        self.assertEqual(ss.resolve_kind("MoviePlay", 0, externs), "movie")
        self.assertEqual(ss.resolve_kind("DisposSetMode", 2, externs), "group")
        self.assertEqual(ss.resolve_kind("RectSet", 0, externs), "rect")
        self.assertEqual(ss.resolve_kind("MapLoad", 0, externs), "map")
        if "BGMPlay" in externs:
            self.assertEqual(ss.resolve_kind("BGMPlay", 1, externs), "bgm")
        self.assertIsNone(ss.resolve_kind("Fade", 0, externs))
        self.assertEqual(ss.prefix_kind("PID_IK"), "pid")
        self.assertIsNone(ss.prefix_kind("Pi"))


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        movie = root / "files" / "Movie"
        movie.mkdir(parents=True)
        for name in ("op.thp", "ed.thp", "s06.thp"):
            (movie / name).write_bytes(b"THP\x00")
        for folder in ("bmap06", "bmap06_2", "bmap07"):
            (root / "files" / "zmap" / folder).mkdir(parents=True)
        self.provider = ss.ScriptSuggestions(_project(root))
        self.externs = load_externs()

    def tearDown(self):
        self._tmp.cleanup()

    def complete(self, before, after="", force=False, **kw):
        return self.provider.completions(before, after, force=force, externs=self.externs,
                                         identifiers=lambda word: [n for n in ("MoviePlay", "MapLoad") if n.startswith(word)],
                                         **kw)

    def test_movies_after_open_paren_are_quoted(self):
        items = self.complete("    MoviePlay(")
        self.assertEqual([c.text for c in items], ['"Movie/ed.thp"', '"Movie/op.thp"', '"Movie/s06.thp"'])
        self.assertTrue(all(c.replace == 0 for c in items))

    def test_movies_inside_string_replace_the_partial_and_close_the_quote(self):
        items = self.complete('    MoviePlay("Movie/o')
        self.assertEqual([(c.text, c.replace) for c in items], [('Movie/op.thp"', 7)])
        items = self.complete('    MoviePlay("Movie/o', after='")')
        self.assertEqual(items[0].text, "Movie/op.thp")

    def test_maps_and_pool_values(self):
        items = self.complete('    MapLoad("bmap06')
        self.assertEqual([c.text.rstrip('"') for c in items], ["bmap06", "bmap06_2"])
        items = self.complete("    UnitGetByPID(", pool=["PID_IKE", "BGM_X"])
        self.assertEqual([c.text for c in items], ['"PID_IKE"'])

    def test_prefix_outside_calls(self):
        items = self.complete("    var who = PID_I", pool=["PID_IKE", "PID_TITANIA"])
        self.assertEqual([(c.text, c.replace) for c in items], [('"PID_IKE"', 5)])

    def test_function_names_otherwise(self):
        self.assertEqual([c.text for c in self.complete("    Mo")], ["MoviePlay"])
        self.assertEqual(self.complete("    M"), [])
        self.assertEqual(self.complete("    x = 1 "), [])
        self.assertEqual(self.complete('    x = "Mo'), [])

    def test_chapter_script_names(self):
        self.assertEqual(ss.chapter_of_script(Path("C06.cmb")), "06")
        self.assertIsNone(ss.chapter_of_script(Path("startup.cmb")))


if __name__ == "__main__":
    unittest.main()
