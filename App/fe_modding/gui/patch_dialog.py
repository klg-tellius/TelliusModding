"""Apply a mod patch (``.tpatch``, see ``patch.py``) to a retail disc image.

Needs no project, so the launcher's File menu offers it as well as the Disc
& Patch page: this is what someone who received a mod runs."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from .. import patch
from ..exceptions import ModdingError
from ..games import get_game_info


class ApplyPatchDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, *, patch_path: str = ""):
        super().__init__(parent)
        self.title("Apply a patch")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self._info: Optional[patch.PatchInfo] = None
        self._busy = False

        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Apply a patch", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Label(body, text="Builds a playable disc image from a mod patch and your own copy of the game.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 14))

        self._patch = tk.StringVar()
        self._disc = tk.StringVar()
        self._output = tk.StringVar()
        self._row(body, "Patch", self._patch, self._browse_patch)
        self._about = ttk.Label(body, text="", style="Caption.TLabel", wraplength=520, justify="left")
        self._about.pack(anchor="w", pady=(0, 8))
        self._row(body, "Game disc image", self._disc, self._browse_disc)
        self._row(body, "Output", self._output, self._browse_output)

        footer = ttk.Frame(body)
        footer.pack(fill="x", pady=(14, 0))
        self._progress = ttk.Progressbar(footer, mode="indeterminate", length=180)
        self._status = ttk.Label(footer, text="", style="Caption.TLabel")
        self._status.pack(side="left")
        self._close = ttk.Button(footer, text="Close", command=self._on_close)
        self._close.pack(side="right")
        self._apply = ttk.Button(footer, text="Build patched disc", style="Accent.TButton", command=self._run)
        self._apply.pack(side="right", padx=(0, 8))

        for var in (self._patch, self._disc, self._output):
            var.trace_add("write", lambda *_: self._update_state())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        if patch_path:
            self._set_patch(patch_path)
        self._update_state()
        self.grab_set()
        self.focus_set()

    def _row(self, parent: tk.Misc, label: str, var: tk.StringVar, browse) -> None:
        ttk.Label(parent, text=label, style="Strong.TLabel").pack(anchor="w")
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(2, 8))
        ttk.Entry(row, textvariable=var, width=64).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=browse).pack(side="left", padx=(8, 0))

    # -- choosing files ---------------------------------------------------------------------
    def _browse_patch(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Choose the patch", parent=self,
            filetypes=[("Tellius patches", f"*{patch.PATCH_EXTENSION}"), ("All files", "*.*")])
        if chosen:
            self._set_patch(chosen)

    def _set_patch(self, path: str) -> None:
        self._patch.set(path)
        try:
            info = patch.read_patch(path)
        except ModdingError as exc:
            self._info = None
            self._about.configure(text=str(exc))
            return
        self._info = info
        game = get_game_info(info.game)
        parts = [info.name or Path(path).stem, game.display_name]
        if info.disc_id:
            parts.append(f"disc {info.disc_id}")
        counts = f"{len(info.replace)} replaced, {len(info.add)} added, {len(info.remove)} removed files"
        self._about.configure(text="  ·  ".join(parts) + f"\n{counts}"
                              + (f"\n{info.description}" if info.description else ""))
        if not self._output.get():
            name = Path(path).with_suffix(game.build_extension).name
            self._output.set(str(Path(path).with_name(name)))

    def _browse_disc(self) -> None:
        formats = get_game_info(self._info.game).disc_formats if self._info else (".iso", ".gcm", ".ciso",
                                                                                  ".wbfs", ".wdf", ".wia")
        chosen = filedialog.askopenfilename(
            title="Choose your game disc image", parent=self,
            filetypes=[("Disc images", " ".join(f"*{ext}" for ext in formats)), ("All files", "*.*")])
        if chosen:
            self._disc.set(chosen)

    def _browse_output(self) -> None:
        ext = get_game_info(self._info.game).build_extension if self._info else ""
        current = Path(self._output.get()) if self._output.get() else None
        chosen = filedialog.asksaveasfilename(
            title="Save the patched disc as", parent=self, defaultextension=ext,
            initialdir=str(current.parent) if current else None,
            initialfile=current.name if current else "",
            filetypes=[("Disc image", f"*{ext}")] if ext else [("All files", "*.*")])
        if chosen:
            self._output.set(chosen)

    # -- running ----------------------------------------------------------------------------
    def _update_state(self) -> None:
        ready = self._info is not None and self._disc.get() and self._output.get() and not self._busy
        self._apply.configure(state="normal" if ready else "disabled")

    def _run(self) -> None:
        patch_path, disc, output = self._patch.get(), self._disc.get(), self._output.get()
        if Path(output).exists() and not messagebox.askyesno(
                "Replace the file?", f"{output} already exists. Replace it?", parent=self):
            return
        self._busy = True
        self._update_state()
        self._close.configure(state="disabled")
        self._status.configure(text="Extracting, patching and building - this takes a minute …")
        self._progress.pack(side="left", padx=(8, 0))
        self._progress.start(12)
        results: "queue.Queue" = queue.Queue()

        def worker():
            try:
                results.put(("ok", patch.apply_patch_to_disc(patch_path, disc, output)))
            except ModdingError as exc:
                results.put(("error", str(exc)))
            except OSError as exc:
                results.put(("error", f"Unexpected error: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                status, payload = results.get_nowait()
            except queue.Empty:
                self.after(150, poll)
                return
            self._busy = False
            self._progress.stop()
            self._progress.pack_forget()
            self._close.configure(state="normal")
            self._update_state()
            if status == "ok":
                self._status.configure(text=f"Built {output}")
                if payload:
                    messagebox.showwarning("Disc image is oversized", payload, parent=self)
                messagebox.showinfo("Patched disc ready", f"Built {output}", parent=self)
            else:
                self._status.configure(text="")
                messagebox.showerror("Could not apply the patch", payload, parent=self)
        poll()

    def _on_close(self) -> None:
        if not self._busy:
            self.destroy()
