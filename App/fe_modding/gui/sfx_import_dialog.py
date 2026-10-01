"""Dialog for adding a new sound effect cue, or replacing the audio of an
existing one, from a WAV/MP3/OGG/FLAC file.

Both go through ``formats/musyx_write.py``: the audio is encoded to
DSP-ADPCM and added to a MusyX bank as a new sample + macro + FX entry, and
``Sound/gcfesnd.bin`` either gains a new ``SFX_*`` record or has one record's
sound id repointed. All new file contents are built first and only written
once every step has worked, so a failure leaves the project untouched. The
originals are kept by ``ModProject.write_keeping_original``.

Untested in the game: the loader's tolerance of these tables growing is
inferred from the public MusyX source, not verified in Dolphin."""

from __future__ import annotations

import queue
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import tools
from ..formats import gcfesnd, musyx, musyx_write
from ..project import ModProject
from .changelog import ChangeLog

AUDIO_TYPES = [("Audio files", "*.wav *.mp3 *.ogg *.flac *.m4a *.aac *.wma"), ("All files", "*.*")]
LONG_SECONDS = 10.0
LARGE_BYTES = 256 * 1024


class SfxImportDialog(tk.Toplevel):
    """``replace_cue=None`` adds a new cue, otherwise replaces that cue's audio."""

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog,
                 replace_cue: gcfesnd.SfxCue | None, on_done):
        super().__init__(parent)
        self.title("Replace sound effect audio" if replace_cue else "Add sound effect")
        self.transient(parent)
        self.resizable(False, False)
        self._project = project
        self._changelog = changelog
        self._replace = replace_cue
        self._on_done = on_done
        self._sound_dir = project.extracted_dir / "files" / "Sound"
        self._scratch = Path(tempfile.mkdtemp(prefix="tellius_sfxin_"))
        self._rate = 0
        self._pcm: list[int] = []
        self._busy = False

        self._banks = musyx.SoundBanks(self._sound_dir)
        self._groups = musyx_write.fx_groups(self._banks)
        self._build()
        self.grab_set()

    # -- layout ---------------------------------------------------------------
    def _build(self) -> None:
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        row = 0

        ttk.Label(body, text="Audio file").grid(row=row, column=0, sticky="w")
        self._file_var = tk.StringVar()
        ttk.Entry(body, textvariable=self._file_var, width=46, state="readonly").grid(row=row, column=1, padx=6)
        ttk.Button(body, text="Browse...", command=self._choose_file).grid(row=row, column=2)
        row += 1
        self._file_info = ttk.Label(body, text="", style="Muted.TLabel", wraplength=470, justify="left")
        self._file_info.grid(row=row, column=0, columnspan=3, sticky="w", pady=(2, 8))
        row += 1

        if self._replace is None:
            ttk.Label(body, text="Cue name").grid(row=row, column=0, sticky="w")
            self._name_var = tk.StringVar(value="SFX_")
            ttk.Entry(body, textvariable=self._name_var, width=46).grid(row=row, column=1, padx=6, sticky="w")
            row += 1
        else:
            ttk.Label(body, text="Replacing").grid(row=row, column=0, sticky="w")
            ttk.Label(body, text=self._replace.name, font=("Segoe UI", 9, "bold")).grid(row=row, column=1, padx=6, sticky="w")
            row += 1

        ttk.Label(body, text="Sound group").grid(row=row, column=0, sticky="w", pady=(6, 0))
        labels = [f"{g.bank} group {g.group_id} ({g.entries} sounds)" for g in self._groups]
        self._group_var = tk.StringVar(value=self._default_group_label(labels))
        ttk.Combobox(body, textvariable=self._group_var, values=labels, state="readonly", width=43).grid(
            row=row, column=1, padx=6, pady=(6, 0), sticky="w")
        row += 1
        ttk.Label(
            body,
            text="Which sounds are loaded together. A sound is only available while its group is loaded;\n"
            "the group holding the menu sounds (SYS) is the safest choice for a new cue."
            if self._replace is None else
            "A replaced cue keeps the group its old sound was in, when that is known.",
            style="Muted.TLabel", justify="left").grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1

        if self._replace is None:
            settings = ttk.Frame(body)
            settings.grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
            self._volume = tk.IntVar(value=127)
            self._pan = tk.IntVar(value=64)
            self._range = tk.IntVar(value=200)
            for label, var, low, high in (("Volume", self._volume, 0, 127), ("Pan", self._pan, 0, 127),
                                          ("Range", self._range, 0, 100000)):
                ttk.Label(settings, text=label).pack(side="left", padx=(0, 4))
                ttk.Spinbox(settings, textvariable=var, from_=low, to=high, width=7).pack(side="left", padx=(0, 14))
            row += 1

        self._status = ttk.Label(body, text="", wraplength=470, justify="left")
        self._status.grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 0))
        row += 1
        self._progress = ttk.Progressbar(body, mode="indeterminate")
        self._progress.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._progress.grid_remove()
        row += 1

        ttk.Label(
            body,
            text="Experimental: the game hasn't been tested with new sounds. Keep a backup;\n"
            "original files are kept by the project and can be restored.",
            style="Muted.TLabel", justify="left").grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 0))
        row += 1

        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=(12, 0))
        self._go = ttk.Button(buttons, text="Replace" if self._replace else "Add", command=self._run, state="disabled")
        self._go.pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self._close).pack(side="right", padx=(0, 6))
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _default_group_label(self, labels: list[str]) -> str:
        """The old sound's group for a replace, else the group of the menu sounds."""
        wanted = None
        if self._replace is not None:
            entry = self._banks.fx_entry(self._replace.sound_id)
            wanted = entry.group_id if entry else None
        if wanted is None:
            select = next((c for c in gcfesnd.read_sfx_cues_path(self._sound_dir / "gcfesnd.bin")
                           if c.name == "SFX_SYS_SELECT1"), None)
            entry = self._banks.fx_entry(select.sound_id) if select else None
            wanted = entry.group_id if entry else None
        for group, label in zip(self._groups, labels):
            if group.group_id == wanted:
                return label
        return labels[0] if labels else ""

    # -- audio --------------------------------------------------------------------
    def _choose_file(self) -> None:
        chosen = filedialog.askopenfilename(title="Choose audio", filetypes=AUDIO_TYPES, parent=self)
        if not chosen:
            return
        source = Path(chosen)
        try:
            wav = source
            if source.suffix.lower() != ".wav":
                wav = self._scratch / "converted.wav"
                tools.decode_audio_to_wav(source, wav)
            rate, pcm = musyx_write.load_mono_wav(wav)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read the audio", str(exc), parent=self)
            return
        self._file_var.set(str(source))
        self._rate, self._pcm = rate, pcm
        seconds = len(pcm) / rate if rate else 0.0
        size = len(pcm) // 14 * 8 + 8
        notes = [f"{rate} Hz, {seconds:.2f} s (mono), about {size / 1024:.0f} KB once encoded."]
        if seconds > LONG_SECONDS:
            notes.append("Long for a sound effect: it takes that much sound memory (ARAM) while its group is loaded.")
        if size > LARGE_BYTES:
            notes.append("This is large; the game's sound memory is nearly full already.")
        self._file_info.config(text=" ".join(notes))
        self._go.config(state="normal")

    def _selected_group(self) -> musyx_write.FxGroupInfo:
        labels = [f"{g.bank} group {g.group_id} ({g.entries} sounds)" for g in self._groups]
        return self._groups[labels.index(self._group_var.get())]

    # -- work -----------------------------------------------------------------------
    def _run(self) -> None:
        if self._busy or not self._pcm:
            return
        group = self._selected_group()
        try:
            if self._replace is None:
                name = self._name_var.get().strip()
                gcfesnd.validate_sfx_name(name)
                settings = dict(volume=self._volume.get(), pan=self._pan.get(), range_value=self._range.get())
        except (gcfesnd.GcfesndError, tk.TclError) as exc:
            messagebox.showerror("Check the settings", str(exc), parent=self)
            return

        pcm, rate = self._pcm, self._rate
        sound_dir = self._sound_dir

        def work():
            if self._replace is None:
                return musyx_write.add_cue(sound_dir, name, group.bank, group.group_id, pcm, rate, **settings)
            current = self._banks.fx_entry(self._replace.sound_id)
            return musyx_write.replace_cue(
                sound_dir, self._replace.name, pcm, rate,
                bank_name=group.bank if current is None or group.group_id != current.group_id else None,
                group_id=group.group_id if current is None or group.group_id != current.group_id else None)

        self._busy = True
        self._go.config(state="disabled")
        self._status.config(text="Encoding... (DSP-ADPCM is slow: roughly twice the clip's length)")
        self._progress.grid()
        self._progress.start(12)
        results: "queue.Queue" = queue.Queue()

        def worker():
            try:
                results.put(("ok", work()))
            except Exception as exc:  # noqa: BLE001
                results.put(("error", str(exc) or exc.__class__.__name__))

        threading.Thread(target=worker, daemon=True).start()
        self._poll(results)

    def _poll(self, results: "queue.Queue") -> None:
        try:
            status, payload = results.get_nowait()
        except queue.Empty:
            self.after(150, lambda: self._poll(results))
            return
        self._progress.stop()
        self._progress.grid_remove()
        self._busy = False
        if status == "error":
            self._status.config(text="")
            self._go.config(state="normal")
            messagebox.showerror("Could not add the sound", payload, parent=self)
            return
        sound, files = payload
        try:
            for name, data in files.items():
                self._project.write_keeping_original(self._sound_dir / name, data)
        except OSError as exc:
            messagebox.showerror("Could not write the files", str(exc), parent=self)
            self._go.config(state="normal")
            return
        what = self._replace.name if self._replace else self._name_var.get().strip()
        self._changelog.append(what, f"{'Replaced audio of' if self._replace else 'Added'} sound effect "
                                     f"(sound id {sound.fx_id}, {sound.bank_name})")
        self._on_done(what)
        self._close()

    def _close(self) -> None:
        if self._busy:
            return
        import shutil
        shutil.rmtree(self._scratch, ignore_errors=True)
        self.grab_release()
        self.destroy()
