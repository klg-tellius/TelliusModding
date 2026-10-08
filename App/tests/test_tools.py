import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import tools
from fe_modding.exceptions import ProjectError
from fe_modding.games import Game
from fe_modding.project import ModProject
from fe_modding.tools import ToolError


def _make_layout(dest: Path, *, wii: bool, skip: tuple[str, ...] = ()) -> None:
    names = ["sys/boot.bin", "files/a.bin"]
    if wii:
        names += ["disc/header.bin", "ticket.bin", "tmd.bin", "cert.bin"]
    for name in names:
        if name in skip or name.split("/")[0] in skip:
            continue
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")


class FakeRun:
    """Stands in for subprocess.run: records commands and fakes WIT / DolphinTool output."""

    def __init__(self, *, wii: bool, convert_code: int = 0, skip: tuple[str, ...] = ()):
        self.calls: list[list[str]] = []
        self.wii, self.convert_code, self.skip = wii, convert_code, skip

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        if Path(args[0]).name.lower().startswith("dolphintool"):
            if self.convert_code == 0:
                Path(args[args.index("-o") + 1]).write_bytes(b"iso")
            return subprocess.CompletedProcess(args, self.convert_code, "", "no good" if self.convert_code else "")
        if args[1] == "EXTRACT":
            _make_layout(Path(args[-2] if args[-1] == "-o" else args[-1]), wii=self.wii, skip=self.skip)
        return subprocess.CompletedProcess(args, 0, "", "")


class ExtractDiscTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.dest = self.root / "out" / "extracted"
        self.wit = mock.patch.object(tools, "wit_path", return_value=Path("wit.exe"))
        self.wit.start()
        self.addCleanup(self.wit.stop)

    def _image(self, name: str) -> Path:
        path = self.root / name
        path.write_bytes(b"disc")
        return path

    def test_wii_extract_selects_the_data_partition(self):
        run = FakeRun(wii=True)
        with mock.patch.object(tools.subprocess, "run", run):
            tools.extract_disc(self._image("rd.wbfs"), self.dest, overwrite=True, wii=True)
        (call,) = run.calls
        self.assertEqual(call[1:6], ["EXTRACT", "--pmode", "NONE", "--psel", "DATA"])
        self.assertEqual(call[-1], "-o")

    def test_gamecube_extract_has_no_partition_selector(self):
        run = FakeRun(wii=False)
        with mock.patch.object(tools.subprocess, "run", run):
            tools.extract_disc(self._image("por.iso"), self.dest)
        self.assertNotIn("--psel", run.calls[0])
        self.assertEqual(run.calls[0][1:4], ["EXTRACT", "--pmode", "NONE"])

    def test_wii_layout_is_validated(self):
        for missing in ("ticket.bin", "tmd.bin", "cert.bin", "disc", "files", "sys"):
            run = FakeRun(wii=True, skip=(missing,))
            with self.subTest(missing=missing), mock.patch.object(tools.subprocess, "run", run):
                with self.assertRaises(ToolError) as caught:
                    tools.extract_disc(self._image("rd.wbfs"), self.root / f"o_{missing}", wii=True)
                self.assertIn(missing, str(caught.exception))

    def test_a_gamecube_disc_needs_no_wii_files(self):
        tools.check_extracted_layout(self._make(wii=False), wii=False)
        with self.assertRaises(ToolError):
            tools.check_extracted_layout(self._make(wii=False), wii=True)

    def _make(self, *, wii: bool) -> Path:
        folder = Path(tempfile.mkdtemp(dir=self.root))
        _make_layout(folder, wii=wii)
        return folder

    def test_rvz_is_converted_to_a_temporary_iso_first(self):
        run = FakeRun(wii=True)
        dolphin = self.root / "Dolphin.exe"
        dolphin.write_bytes(b"")
        (self.root / "DolphinTool.exe").write_bytes(b"")
        with mock.patch.object(tools.subprocess, "run", run), \
                mock.patch("fe_modding.emulator.configured_dolphin", return_value=dolphin):
            tools.extract_disc(self._image("rd.rvz"), self.dest, wii=True)
        convert, extract = run.calls
        self.assertEqual(Path(convert[0]).name, "DolphinTool.exe")
        self.assertEqual(convert[1], "convert")
        self.assertEqual(convert[convert.index("-f") + 1], "iso")
        iso = Path(convert[convert.index("-o") + 1])
        self.assertEqual(iso.suffix, ".iso")
        self.assertEqual(extract[extract.index("--psel") + 1], "DATA")
        self.assertEqual(extract[-2], str(iso))
        self.assertFalse(iso.exists(), "the temporary ISO is deleted")
        self.assertEqual(list(self.dest.parent.glob(".rvz_*")), [])

    def test_rvz_without_dolphin_explains_itself(self):
        with mock.patch("fe_modding.emulator.configured_dolphin", return_value=None):
            with self.assertRaises(ToolError) as caught:
                tools.extract_disc(self._image("rd.rvz"), self.dest, wii=True)
        self.assertIn("Dolphin", str(caught.exception))

    def test_rvz_without_dolphintool_next_to_dolphin(self):
        dolphin = self.root / "Dolphin.exe"
        dolphin.write_bytes(b"")
        with mock.patch("fe_modding.emulator.configured_dolphin", return_value=dolphin):
            with self.assertRaises(ToolError) as caught:
                tools.dolphin_tool_path()
        self.assertIn("DolphinTool", str(caught.exception))

    def test_failed_conversion_is_a_tool_error_and_cleans_up(self):
        dolphin = self.root / "Dolphin.exe"
        dolphin.write_bytes(b"")
        (self.root / "DolphinTool.exe").write_bytes(b"")
        run = FakeRun(wii=True, convert_code=1)
        with mock.patch.object(tools.subprocess, "run", run), \
                mock.patch("fe_modding.emulator.configured_dolphin", return_value=dolphin):
            with self.assertRaises(ToolError) as caught:
                tools.extract_disc(self._image("rd.rvz"), self.dest, wii=True)
        self.assertIn("no good", str(caught.exception))
        self.assertEqual(list(self.dest.parent.glob(".rvz_*")), [])

    def test_missing_source(self):
        with self.assertRaises(ToolError):
            tools.extract_disc(self.root / "nope.wbfs", self.dest, wii=True)


class ProjectExtractTests(unittest.TestCase):
    def test_project_passes_the_platform_to_the_extractor(self):
        with tempfile.TemporaryDirectory() as tmp:
            for game, wii in ((Game.RADIANT_DAWN, True), (Game.PATH_OF_RADIANCE, False)):
                project = ModProject.create(Path(tmp), f"p{wii}", game)
                disc = project.directory / "source" / ("d.wbfs" if wii else "d.iso")
                disc.write_bytes(b"x")
                project.source_iso = disc.name
                with mock.patch.object(tools, "extract_disc") as extract:
                    project.extract()
                self.assertEqual(extract.call_args.kwargs["wii"], wii)

    def test_rvz_can_be_chosen_as_a_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = ModProject.create(Path(tmp), "r", Game.RADIANT_DAWN)
            disc = Path(tmp) / "Radiant Dawn.rvz"
            disc.write_bytes(b"RVZ\x01")
            self.assertEqual(project.set_source(disc).name, "Radiant Dawn.rvz")
            with self.assertRaises(ProjectError):
                project.set_source(Path(tmp) / "x.zip")


if __name__ == "__main__":
    unittest.main()
