import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fe_modding import runtime_tools


class ToolInstallTests(unittest.TestCase):
    def archive(self, root, entries):
        path = root / 'tool.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return path, dict(runtime_tools.TOOLS['wit'], sha256=digest)

    def test_only_tool_dependencies_and_notices_are_installed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, spec = self.archive(root, {
                'package/bin/wit.exe': b'synthetic executable',
                'package/bin/runtime.dll': b'synthetic dependency',
                'package/LICENSE': b'license text',
                'package/bin/unrelated.exe': b'not installed',
            })
            with patch.dict(runtime_tools.TOOLS, wit=spec):
                runtime_tools.unpack_tool('wit', archive, root / 'installed')
            self.assertTrue((root / 'installed/wit.exe').is_file())
            self.assertTrue((root / 'installed/runtime.dll').is_file())
            self.assertTrue((root / 'installed/upstream/package/LICENSE').is_file())
            self.assertFalse((root / 'installed/unrelated.exe').exists())

    def test_checksum_failure_does_not_publish_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, _ = self.archive(root, {'wit.exe': b'wrong bytes'})
            with self.assertRaisesRegex(ValueError, 'checksum'):
                runtime_tools.unpack_tool('wit', archive, root / 'installed')
            self.assertFalse((root / 'installed').exists())

    def test_traversal_and_missing_executable_do_not_publish(self):
        for entries in ({'../outside.dll': b'x', 'wit.exe': b'x'}, {'README.txt': b'x'}):
            with self.subTest(entries=list(entries)), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive, spec = self.archive(root, entries)
                with patch.dict(runtime_tools.TOOLS, wit=spec), self.assertRaises(ValueError):
                    runtime_tools.unpack_tool('wit', archive, root / 'installed')
                self.assertFalse((root / 'installed').exists())
                self.assertFalse((root / 'outside.dll').exists())

    def test_existing_install_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, spec = self.archive(root, {'wit.exe': b'new'})
            destination = root / 'installed'
            destination.mkdir()
            (destination / 'wit.exe').write_bytes(b'old')
            with patch.dict(runtime_tools.TOOLS, wit=spec), self.assertRaises(FileExistsError):
                runtime_tools.unpack_tool('wit', archive, destination)
            self.assertEqual((destination / 'wit.exe').read_bytes(), b'old')


if __name__ == '__main__':
    unittest.main()
