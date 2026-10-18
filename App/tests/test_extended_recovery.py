import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fe_modding import project_transaction as tx
from fe_modding.extended_hub import PreparedFile
from fe_modding.gui.extended_recovery import resolve_recovery


class RecoveryDialogTests(unittest.TestCase):
    def test_absent_journal_opens_without_dialog(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("fe_modding.gui.extended_recovery.tk.Toplevel") as dialog:
                self.assertTrue(resolve_recovery(Mock(), SimpleNamespace(directory=Path(tmp))))
                dialog.assert_not_called()

    def test_cancel_preserves_journal_and_recover_restores_previous_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "file"
            target.write_bytes(b"before")
            manifest = tx._manifest
            def interrupt(journal, data):
                if data["state"] == "complete":
                    raise KeyboardInterrupt()
                return manifest(journal, data)
            with patch.object(tx, "_manifest", side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
                tx.commit(root, (PreparedFile(target, b"before", b"after"),))
            for action, expected in (("Cancel", False), ("Recover previous files", True)):
                callbacks = {}
                parent = Mock()
                parent.wait_window.side_effect = lambda dialog: callbacks[action]()
                def button(*args, **kwargs):
                    callbacks[kwargs["text"]] = kwargs["command"]
                    return Mock()
                with patch("fe_modding.gui.extended_recovery.tk.Toplevel"), \
                     patch("fe_modding.gui.extended_recovery.ttk.Frame"), \
                     patch("fe_modding.gui.extended_recovery.ttk.Label"), \
                     patch("fe_modding.gui.extended_recovery.ttk.Button", side_effect=button):
                    self.assertEqual(resolve_recovery(parent, SimpleNamespace(directory=root)), expected)
                self.assertEqual(target.read_bytes(), b"before" if expected else b"after")
                self.assertEqual((root / tx.JOURNAL).exists(), not expected)


if __name__ == "__main__":
    unittest.main()
