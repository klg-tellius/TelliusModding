"""Shared base class for every embedded editor panel in the workspace.

Every editor (dialogue/deployment/backgrounds/portraits/music/videos/stats/
scripts/maps) already follows the same shape: a ``self._dirty`` flag set on
every successful apply, and a ``_confirm_discard()`` method
(``messagebox.askyesno(...)``) that asks before losing unsaved work. Before
this module, that contract was tied to ``tk.Toplevel.protocol("WM_DELETE_WINDOW", ...)``
- each editor was its own popup window, and closing the window was the only
place "is it safe to lose this?" got checked.

Now that editors are embedded panels the workspace swaps in and out
(``fe_modding/gui/app.py``), the same question comes up on every panel
switch instead of just on window close. ``EditorPanel`` exposes that
existing per-editor contract uniformly so ``MainWindow`` can call one method
- ``confirm_navigate_away()`` - regardless of which editor is currently
showing, without needing to know each editor's internals.
"""

from __future__ import annotations

from tkinter import ttk


class EditorPanel(ttk.Frame):
    """Base class for every embedded editor. Subclasses set ``self._dirty``
    on every successful apply (already true of every editor - this class
    doesn't change that behavior, just gives it a name the workspace can
    call generically) and keep their existing ``_confirm_discard()`` method
    for the actual "discard changes?" prompt."""

    #: Short label naming this panel (tabs, the unsaved list).
    display_name: str = ""

    @property
    def dirty(self) -> bool:
        return bool(getattr(self, "_dirty", False))

    def confirm_navigate_away(self) -> bool:
        """Returns True if it's safe to switch away from this panel (either
        it has no unsaved changes, or the user confirmed discarding them).
        Returns False if the switch should be aborted and this panel should
        stay visible."""
        if not self.dirty:
            return True
        confirm = getattr(self, "_confirm_discard", None)
        if confirm is None:
            return True
        return bool(confirm())

    def save_changes(self) -> bool:
        """Save this panel's unsaved edits with its own Save (``save()``, else
        ``_save()``; they report their own errors). True when nothing is left
        unsaved."""
        if not self.dirty:
            return True
        save = getattr(self, "save", None) or getattr(self, "_save", None)
        if save is None:
            return False
        save()
        return not self.dirty

    def cleanup(self) -> None:
        """Called once, when the project closes or the app exits - panels
        are created lazily and then kept alive (shown/hidden, never
        destroyed) for the rest of the session, so anything a panel would
        have torn down in an old Toplevel's WM_DELETE_WINDOW handler
        (stopping playback, removing a scratch temp dir) needs to happen
        here instead. No-op by default; override where there's actually
        something to release (music/video editors)."""
