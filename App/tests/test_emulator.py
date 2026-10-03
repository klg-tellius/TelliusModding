"""Finding and launching Dolphin, without Dolphin: lookups and the process start are injected."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import emulator


class FindTests(unittest.TestCase):
    def test_configured_path_wins_and_must_exist(self):
        exists = lambda p: str(p) == "/opt/Dolphin.exe"  # noqa: E731
        self.assertEqual(emulator.find_dolphin("/opt/Dolphin.exe", is_file=exists), Path("/opt/Dolphin.exe"))
        self.assertIsNone(emulator.find_dolphin("/missing/Dolphin.exe", is_file=exists, which=lambda n: "/usr/bin/x"))

    def test_install_folder_then_path(self):
        env = {"ProgramFiles": "/pf"}
        target = Path("/pf/Dolphin-x64/Dolphin.exe")
        self.assertEqual(emulator.find_dolphin(None, environ=env, is_file=lambda p: p == target, which=lambda n: None), target)
        self.assertEqual(emulator.find_dolphin(None, environ={}, is_file=lambda p: False,
                                               which=lambda n: "/usr/bin/dolphin-emu" if n == "dolphin-emu" else None),
                         Path("/usr/bin/dolphin-emu"))
        self.assertIsNone(emulator.find_dolphin(None, environ={}, is_file=lambda p: False, which=lambda n: None))


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.image = Path(self._tmp.name) / "mod.ciso"
        self.image.write_bytes(b"x")
        self.dolphin = Path(self._tmp.name) / "Dolphin.exe"
        self.dolphin.write_bytes(b"x")

    def test_command_line(self):
        self.assertEqual(emulator.command("D", "I"), ["D", "--exec=I", "--batch"])
        self.assertEqual(emulator.command("D", "I", batch=False, save_state="s.sav"), ["D", "--exec=I", "--save_state=s.sav"])

    def test_launch_starts_the_process(self):
        started = []
        proc = emulator.launch(self.image, self.dolphin, popen=lambda args: started.append(args) or "proc")
        self.assertEqual(proc, "proc")
        self.assertEqual(started, [[str(self.dolphin), f"--exec={self.image}", "--batch"]])

    def test_missing_image_or_dolphin(self):
        with self.assertRaisesRegex(emulator.EmulatorError, "build the project first"):
            emulator.launch(self.image.with_name("none.ciso"), self.dolphin)
        with self.assertRaisesRegex(emulator.EmulatorError, "Settings > Preferences"):
            emulator.launch(self.image, self.dolphin.with_name("Nope.exe"))

    def test_start_failure_is_reported(self):
        def boom(args):
            raise OSError("denied")
        with self.assertRaisesRegex(emulator.EmulatorError, "denied"):
            emulator.launch(self.image, self.dolphin, popen=boom)


if __name__ == "__main__":
    unittest.main()
