"""Downloading and installing Jade's Tellius Forge add-on in Blender, without network or Blender."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import blender

ADDON = b'bl_info = {\n    "name": "Tellius Forge",\n    "version": (0, 27, 1),\n}\n'


def _fetch(release_assets=None, release_error=False, main=ADDON):
    calls = []

    def fetch(url):
        calls.append(url)
        if url.endswith("/releases/latest"):
            if release_error:
                raise OSError("rate limited")
            return json.dumps({"assets": release_assets or []}).encode()
        if url == "https://example.invalid/tellius-forge.py":
            return ADDON.replace(b"27", b"28")
        if url.endswith("/main/plugin/tellius-forge.py"):
            if main is None:
                raise OSError("offline")
            return main
        raise AssertionError(url)

    fetch.calls = calls
    return fetch


class DownloadTests(unittest.TestCase):
    def test_release_asset_is_preferred(self):
        assets = [{"name": "tellius-forge-toolkit.7z", "browser_download_url": "x"},
                  {"name": "tellius-forge.py", "browser_download_url": "https://example.invalid/tellius-forge.py"}]
        version, source = blender.download_tellius_forge(_fetch(assets))
        self.assertEqual(version, "v0.28.1")
        self.assertIn(b"Tellius Forge", source)

    def test_main_branch_when_there_is_no_release(self):
        self.assertEqual(blender.download_tellius_forge(_fetch())[0], "v0.27.1")
        self.assertEqual(blender.download_tellius_forge(_fetch(release_error=True))[0], "v0.27.1")

    def test_other_files_and_failures_are_refused(self):
        with self.assertRaises(blender.BlenderError):
            blender.download_tellius_forge(_fetch(main=b"<html>not found</html>"))
        with self.assertRaises(blender.BlenderError):
            blender.download_tellius_forge(_fetch(main=None))


class InstallTests(unittest.TestCase):
    def test_install_runs_blender_on_the_downloaded_file_and_needs_its_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "blender.exe"
            exe.write_bytes(b"")
            seen = {}

            def confirmed(args, **kwargs):
                addon = Path(args[args.index("--") + 1])
                seen["name"], seen["module"], seen["data"] = addon.name, args[-1], addon.read_bytes()
                return SimpleNamespace(returncode=0, stdout="TELLIUS_ADDON_INSTALLED\n", stderr="")

            self.assertEqual(blender.install_tellius_forge(exe, run=confirmed, fetch=_fetch()), (exe, "v0.27.1"))
            self.assertEqual((seen["name"], seen["module"], seen["data"]), ("tellius-forge.py", "tellius-forge", ADDON))
            quiet = lambda args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr="")  # noqa: E731
            with self.assertRaises(blender.BlenderError):
                blender.install_tellius_forge(exe, run=quiet, fetch=_fetch())


if __name__ == "__main__":
    unittest.main()
