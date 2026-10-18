from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from fe_modding.extended_hub import PreparedFile
from fe_modding import project_transaction as tx


class TransactionTests(unittest.TestCase):
    def test_live_transaction_lock_blocks_commit_and_recovery(self):
        with tx._exclusive(self.root):
            with self.assertRaisesRegex(RuntimeError, "Another installation"):
                tx.commit(self.root, self.changes)
            with self.assertRaisesRegex(RuntimeError, "Another installation"):
                tx.recover(self.root)
        tx.commit(self.root, self.changes)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a, self.b = self.root / "a", self.root / "b"
        self.a.write_bytes(b"old")
        self.changes = (PreparedFile(self.a, b"old", b"new"), PreparedFile(self.b, None, b"created"))

    def test_success_and_stale_input_rejection(self):
        dependency = self.root / "script"
        dependency.write_bytes(b"script")
        with self.assertRaises(ValueError):
            tx.commit(self.root, self.changes, ((dependency, b"stale"),))
        self.assertEqual(self.a.read_bytes(), b"old")
        self.assertFalse(self.b.exists())
        tx.commit(self.root, self.changes, ((dependency, b"script"),))
        self.assertEqual(self.a.read_bytes(), b"new")
        self.assertEqual(self.b.read_bytes(), b"created")
        self.assertFalse((self.root / tx.JOURNAL).exists())

    def test_second_write_failure_restores_first_file(self):
        replace = tx.os.replace
        def fail_second(src, dst):
            if Path(dst) == self.b:
                raise OSError("injected write failure")
            return replace(src, dst)
        with patch.object(tx.os, "replace", side_effect=fail_second), self.assertRaises(OSError):
            tx.commit(self.root, self.changes)
        self.assertEqual(self.a.read_bytes(), b"old")
        self.assertFalse(self.b.exists())
        self.assertFalse((self.root / tx.JOURNAL).exists())

    def test_failed_rollback_retains_journal_and_can_recover_later(self):
        replace = tx.os.replace
        written = False
        def fail_write_and_rollback(src, dst):
            nonlocal written
            if Path(dst) == self.a:
                if written:
                    raise OSError("injected rollback failure")
                written = True
            if Path(dst) == self.b:
                raise OSError("injected write failure")
            return replace(src, dst)
        with patch.object(tx.os, "replace", side_effect=fail_write_and_rollback), self.assertRaises(RuntimeError):
            tx.commit(self.root, self.changes)
        self.assertTrue((self.root / tx.JOURNAL / "manifest.json").exists())
        self.assertEqual(self.a.read_bytes(), b"new")
        self.assertTrue(tx.recover(self.root))
        self.assertEqual(self.a.read_bytes(), b"old")
        self.assertFalse(self.b.exists())

    def test_interruption_and_external_edits_are_not_overwritten(self):
        replace = tx.os.replace
        def interrupt(src, dst):
            if Path(dst) == self.b:
                raise KeyboardInterrupt()
            return replace(src, dst)
        with patch.object(tx.os, "replace", side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            tx.commit(self.root, self.changes)
        self.a.write_bytes(b"user edit")
        with self.assertRaises(ValueError):
            tx.recover(self.root)
        self.assertEqual(self.a.read_bytes(), b"user edit")
        self.assertTrue((self.root / tx.JOURNAL).exists())
        self.a.write_bytes(b"new")
        tx.recover(self.root)
        self.assertEqual(self.a.read_bytes(), b"old")

    def test_target_bounds_duplicates_and_existing_journal(self):
        for changes in ((PreparedFile(self.root.parent / "outside", None, b"x"),),
                        (self.changes[0], self.changes[0]),
                        (PreparedFile(self.root / tx.JOURNAL / "bad", None, b"x"),)):
            with self.assertRaises(ValueError):
                tx.commit(self.root, changes)
        (self.root / tx.JOURNAL).mkdir()
        with self.assertRaises(FileExistsError):
            tx.commit(self.root, self.changes)
        self.assertEqual(self.a.read_bytes(), b"old")

    def test_corrupt_recovery_payload_is_refused(self):
        replace = tx.os.replace
        def interrupt(src, dst):
            if Path(dst) == self.b:
                raise KeyboardInterrupt()
            return replace(src, dst)
        with patch.object(tx.os, "replace", side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            tx.commit(self.root, self.changes)
        (self.root / tx.JOURNAL / "0.before").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "checksum"):
            tx.recover(self.root)
        self.assertEqual(self.a.read_bytes(), b"new")

    def test_project_commit_is_gated_and_keeps_first_original_when_approved(self):
        from fe_modding.extended_hub import HubProjectUpdate, commit_project_update
        from fe_modding.exceptions import ProjectError
        from fe_modding.game_code import extended_flags
        extracted = self.root / "extracted"
        (extracted / "sys").mkdir(parents=True)
        boot = extracted / "sys" / "boot.bin"
        boot.write_bytes(b"GFEE01")
        target = extracted / "sys" / "example"
        target.write_bytes(b"original")
        backup = self.root / "originals" / "sys" / "example"
        project = SimpleNamespace(directory=self.root, extracted_dir=extracted,
                                  _original_of=lambda path: self.root / "originals" / path.relative_to(extracted))
        update = HubProjectUpdate((PreparedFile(target, b"original", b"changed"),),
                                  ((target, b"original"), (boot, b"GFEE01")), None)
        with self.assertRaises(ProjectError):
            commit_project_update(project, update)
        self.assertEqual(target.read_bytes(), b"original")
        self.assertFalse(backup.exists())
        # Exercise transaction plumbing with inert test bytes, not a game patch.
        with patch.object(extended_flags, "EXTENDED_FLAGS_PATCH", SimpleNamespace(versions={"GFEE01": ()})):
            commit_project_update(project, update)
            self.assertEqual(backup.read_bytes(), b"original")
            second = HubProjectUpdate((PreparedFile(target, b"changed", b"changed again"),),
                                      ((target, b"changed"),), None)
            commit_project_update(project, second)
        self.assertEqual(backup.read_bytes(), b"original")
        self.assertEqual(target.read_bytes(), b"changed again")

    def test_interruption_after_all_replacements_removes_new_files_on_recovery(self):
        manifest = tx._manifest
        def interrupt_completion(journal, data):
            if data["state"] == "complete":
                raise KeyboardInterrupt()
            return manifest(journal, data)
        with patch.object(tx, "_manifest", side_effect=interrupt_completion), self.assertRaises(KeyboardInterrupt):
            tx.commit(self.root, self.changes)
        self.assertTrue(self.b.exists())
        from fe_modding.game_code.extended_flags import require_project_runtime
        from fe_modding.exceptions import ProjectError
        with self.assertRaisesRegex(ProjectError, "needs recovery"):
            require_project_runtime(SimpleNamespace(directory=self.root))
        tx.recover(self.root)
        self.assertEqual(self.a.read_bytes(), b"old")
        self.assertFalse(self.b.exists())
        require_project_runtime(SimpleNamespace(directory=self.root))


if __name__ == "__main__":
    unittest.main()
