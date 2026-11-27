import hashlib
from pathlib import Path
import tempfile
import unittest
import urllib.error
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


class DownloadFallbackTests(unittest.TestCase):
    """The patcher failed for a player whose network never reached wit.wiimm.de (WinError 10060):
    every source is tried in turn, and a total failure says how to install WIT by hand."""

    PAYLOAD = b'pinned archive bytes'

    def spec(self, **extra):
        return dict(runtime_tools.TOOLS['wit'], url='https://primary.example/wit.zip',
                    mirrors=('https://mirror.example/wit.zip',),
                    sha256=hashlib.sha256(self.PAYLOAD).hexdigest(), **extra)

    def test_mirror_is_used_when_the_primary_times_out(self):
        calls = []

        def fetch(name, url, archive, progress, timeout):
            calls.append(url)
            if 'primary' in url:
                raise urllib.error.URLError(TimeoutError(10060, 'timed out'))
            archive.write_bytes(self.PAYLOAD)

        with tempfile.TemporaryDirectory() as temporary, patch.dict(runtime_tools.TOOLS, wit=self.spec()):
            archive = Path(temporary) / 'tool.zip'
            used = runtime_tools.download_archive('wit', archive, fetch=fetch, sleep=lambda s: None)
            self.assertEqual(used, 'https://mirror.example/wit.zip')
            self.assertEqual(archive.read_bytes(), self.PAYLOAD)
        self.assertEqual(calls, ['https://primary.example/wit.zip'] * 2 + ['https://mirror.example/wit.zip'])

    def test_wrong_bytes_from_a_source_are_not_kept(self):
        def fetch(name, url, archive, progress, timeout):
            archive.write_bytes(b'tampered' if 'primary' in url else self.PAYLOAD)

        with tempfile.TemporaryDirectory() as temporary, patch.dict(runtime_tools.TOOLS, wit=self.spec()):
            archive = Path(temporary) / 'tool.zip'
            self.assertIn('mirror', runtime_tools.download_archive('wit', archive, fetch=fetch, sleep=lambda s: None))

    def test_total_failure_lists_sources_and_manual_steps(self):
        def fetch(name, url, archive, progress, timeout):
            raise urllib.error.URLError(TimeoutError(10060, 'timed out'))

        with tempfile.TemporaryDirectory() as temporary, patch.dict(runtime_tools.TOOLS, wit=self.spec()):
            with self.assertRaises(runtime_tools.ToolDownloadError) as caught:
                runtime_tools.download_archive('wit', Path(temporary) / 'tool.zip', fetch=fetch, sleep=lambda s: None)
        message = str(caught.exception)
        for text in ('primary.example', 'mirror.example', 'by hand', 'wit.exe'):
            self.assertIn(text, message)

    def test_a_missing_mirror_file_is_not_retried(self):
        calls = []

        def fetch(name, url, archive, progress, timeout):
            calls.append(url)
            raise urllib.error.HTTPError(url, 404, 'Not Found', None, None)

        with tempfile.TemporaryDirectory() as temporary, patch.dict(runtime_tools.TOOLS, wit=self.spec()):
            with self.assertRaises(runtime_tools.ToolDownloadError):
                runtime_tools.download_archive('wit', Path(temporary) / 'tool.zip', fetch=fetch, sleep=lambda s: None)
        self.assertEqual(len(calls), 2)

    def test_pinned_wit_has_a_mirror(self):
        self.assertTrue(runtime_tools.TOOLS['wit']['mirrors'])
        self.assertTrue(all(url.endswith(runtime_tools.archive_name('wit')) for url in runtime_tools.TOOLS['wit']['mirrors']))

    def test_manual_archive_is_checksum_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'wit.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('wit.exe', b'x')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                runtime_tools.install_from_archive('wit', archive, root=root / 'tools')
