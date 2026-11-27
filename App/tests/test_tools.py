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
                disc = Path(tmp) / ("d.wbfs" if wii else "d.iso")
                disc.write_bytes(b"x")
                project.set_source(disc)
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

    def test_radiant_dawn_build_uses_wit_and_wbfs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = ModProject.create(Path(tmp), "RD Build", Game.RADIANT_DAWN)
            _make_layout(project.extracted_dir, wii=True)
            with mock.patch.object(tools, "build_disc") as build:
                output = project.build()
            self.assertEqual(output, project.build_dir / "RD Build.wbfs")
            build.assert_called_once_with(project.disc_tree(), output, overwrite=True)


class ShiftJisNameTests(unittest.TestCase):
    """WIT extracts a Shift-JIS disc name byte per character (``knight1_sp_\\x82\\x86``); Dolphin opens
    the file by its real name (``knight1_sp_ｆ``) and 4-P's opening crashed without it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        model = self.root / "files" / "ymu" / "knight1_sp_\x82\x86"
        model.mkdir(parents=True)
        (model / "pack.cmp").write_bytes(b"model")
        (self.root / "files" / "ymu" / "armor2_\x82\x94.tpl").write_bytes(b"tex")
        (self.root / "files" / "plain.bin").write_bytes(b"x")

    def names(self):
        return sorted(str(p.relative_to(self.root)).replace("\\", "/") for p in (self.root / "files").rglob("*"))

    def test_extracted_names_are_fixed_once(self):
        fixed = tools.fix_extracted_names(self.root)
        self.assertEqual(len(fixed), 2)
        self.assertEqual(self.names(), ["files/plain.bin", "files/ymu", "files/ymu/armor2_ｔ.tpl",
                                        "files/ymu/knight1_sp_ｆ", "files/ymu/knight1_sp_ｆ/pack.cmp"])
        self.assertEqual(tools.fix_extracted_names(self.root), [])

    def test_build_hands_wit_the_byte_form_and_restores_the_names(self):
        tools.fix_extracted_names(self.root)
        seen = {}

        def run(args, **_kwargs):
            seen["names"] = self.names()
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch.object(tools, "wit_path", return_value=Path("wit.exe")), \
                mock.patch.object(tools.subprocess, "run", side_effect=run):
            tools.build_disc(self.root, self.root / "out.wbfs")
        self.assertIn("files/ymu/knight1_sp_\x82\x86/pack.cmp", seen["names"])
        self.assertIn("files/ymu/knight1_sp_ｆ/pack.cmp", self.names())

    def test_a_failed_build_still_restores_the_names(self):
        tools.fix_extracted_names(self.root)
        with mock.patch.object(tools, "wit_path", return_value=Path("wit.exe")), \
                mock.patch.object(tools.subprocess, "run",
                                  return_value=subprocess.CompletedProcess([], 1, "", "boom")):
            with self.assertRaises(ToolError):
                tools.build_disc(self.root, self.root / "out.wbfs")
        self.assertIn("files/ymu/knight1_sp_ｆ/pack.cmp", self.names())

    def test_latin_1_names_that_are_not_shift_jis_are_left_alone(self):
        (self.root / "files" / "caf\xe9.txt").write_bytes(b"x")  # 0xE9 alone is not a whole SJIS character
        tools.fix_extracted_names(self.root)
        self.assertIn("files/caf\xe9.txt", self.names())


if __name__ == "__main__":
    unittest.main()


class FindWitTests(unittest.TestCase):
    def test_wit_next_to_the_program_is_found(self):
        import tempfile
        from unittest import mock
        from pathlib import Path
        from fe_modding import tools as tools_module
        with tempfile.TemporaryDirectory() as temporary:
            here = Path(temporary)
            (here / 'wit').mkdir()
            (here / 'wit' / 'wit.exe').write_bytes(b'x')
            with mock.patch.object(tools_module, '_program_dir', return_value=here), \
                    mock.patch.object(tools_module, 'REPO_ROOT', here / 'none'), \
                    mock.patch.object(tools_module, 'tool_directory', return_value=here / 'none'), \
                    mock.patch('fe_modding.config.load_setting', return_value=None), \
                    mock.patch.object(tools_module.shutil, 'which', return_value=None):
                self.assertEqual(tools_module.find_wit(), here / 'wit' / 'wit.exe')


class FindDolphinToolTests(unittest.TestCase):
    """Tellius Patcher on a player's PC has no Dolphin path in the settings: DolphinTool is still
    found in the usual folders, next to the program, or where the player points."""

    def isolated(self, root, **extra):
        from fe_modding import emulator
        patches = [mock.patch.object(tools, "_program_dir", return_value=root / "program"),
                   mock.patch.object(tools, "_saved", return_value=extra.get("saved")),
                   mock.patch.object(emulator, "configured_dolphin", return_value=None),
                   mock.patch.object(emulator, "candidate_paths", return_value=extra.get("installs", [])),
                   mock.patch.object(tools.shutil, "which", return_value=None)]
        stack = __import__("contextlib").ExitStack()
        for item in patches:
            stack.enter_context(item)
        return stack

    def test_found_in_a_usual_install_folder_without_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Dolphin-x64").mkdir()
            (root / "Dolphin-x64" / "DolphinTool.exe").write_bytes(b"")
            with self.isolated(root, installs=[root / "Dolphin-x64" / "Dolphin.exe"]):
                self.assertEqual(tools.dolphin_tool_path(), root / "Dolphin-x64" / "DolphinTool.exe")

    def test_missing_is_a_dolphin_tool_missing_error(self):
        with tempfile.TemporaryDirectory() as temporary, self.isolated(Path(temporary)):
            with self.assertRaises(tools.DolphinToolMissing):
                tools.dolphin_tool_path()

    def test_remember_accepts_the_dolphin_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "DolphinTool.exe").write_bytes(b"")
            with mock.patch("fe_modding.config.save_setting") as save:
                self.assertEqual(tools.remember_dolphin_tool(root), root / "DolphinTool.exe")
            save.assert_called_once_with(tools.DOLPHIN_TOOL_SETTING, str(root / "DolphinTool.exe"))
            (root / "empty").mkdir()
            with self.assertRaises(ToolError):
                tools.remember_dolphin_tool(root / "empty")
