"""Download external disc/media tools without requiring a manual installation."""
import queue
import threading
import tkinter as tk
from tkinter import ttk

from .. import runtime_tools, tools


class ToolSetupDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Set up disc and media tools")
        self.geometry("560x310")
        self.resizable(False, False)
        self.transient(parent)
        self.events = queue.Queue()
        self.running = False
        frame = ttk.Frame(self, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Disc and media tools", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, wraplength=510, text=(
            "Python and the app libraries are already included. Download WIT to extract and build discs, "
            "and FFmpeg to import audio/video. These downloads come from wit.wiimm.de and gyan.dev "
            "(about 125 MB total), are checksum-verified, and need no administrator access."
        )).pack(anchor="w", pady=12)
        self.media = tk.BooleanVar(value=True)
        self.media_box = ttk.Checkbutton(frame, text="Include FFmpeg for audio/video imports", variable=self.media)
        self.media_box.pack(anchor="w")
        self.status = tk.StringVar(value="Your game files are not downloaded or included.")
        ttk.Label(frame, textvariable=self.status, wraplength=510).pack(anchor="w", pady=12)
        row = ttk.Frame(frame)
        row.pack(fill="x")
        self.install = ttk.Button(row, text="Download missing tools", command=self.start)
        self.install.pack(side="left")
        self.close = ttk.Button(row, text="Later", command=self.destroy)
        self.close.pack(side="right")
        self.protocol("WM_DELETE_WINDOW", lambda: None if self.running else self.destroy())

    def start(self):
        self.running = True
        for widget in (self.install, self.close, self.media_box):
            widget.configure(state="disabled")
        names = ["wit"] + (["ffmpeg"] if self.media.get() else [])

        def worker():
            try:
                for name in names:
                    existing = tools.WIT_EXE if name == "wit" else tools.FFMPEG_EXE
                    if not existing.is_file():
                        runtime_tools.install_tool(name, lambda text: self.events.put(("progress", text)))
                self.events.put(("done", "Tools are ready. You can now create or open a project."))
            except Exception as error:
                self.events.put(("error", f"Setup failed: {error}"))

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self.poll)

    def poll(self):
        while not self.events.empty():
            kind, message = self.events.get_nowait()
            self.status.set(message)
            if kind in {"done", "error"}:
                self.running = False
                self.install.configure(state="normal")
                self.media_box.configure(state="normal")
                self.close.configure(state="normal", text="Close")
        if self.running:
            self.after(100, self.poll)
