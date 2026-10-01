"""Sound effects page: lists every ``SFX_*`` cue of ``Sound/gcfesnd.bin``
with its decoded parameters (see ``formats/gcfesnd.py`` for the record
layout; the meaning of the last two fields is inferred), plays them, and
can add a new cue or replace a cue's audio (``sfx_import_dialog.py``).

Playback resolves a cue's sound id through the MusyX banks (``formats/musyx.py``)
to one DSP-ADPCM sample, or, for the sequenced cues (both id bytes equal, an
index into ``gcfesnd.stbl``), renders the song from ``gcfesnd.slib``
(``formats/musyx_song.py``). The result goes to a scratch WAV played with the
stdlib ``winsound`` (Windows-only, like the Music page). Envelopes, panning
and layered samples of the original sound macros are ignored, so it is an
approximation of the in-game sound."""

from __future__ import annotations

import shutil
import tempfile
import tkinter as tk
import wave
from pathlib import Path
from tkinter import messagebox, ttk

import numpy as np

from ..formats import gcfesnd, musyx, musyx_song
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .sfx_import_dialog import SfxImportDialog

try:
    import winsound
except ImportError:
    winsound = None

ALL_GROUPS = "All"
COLUMNS = (
    ("name", "Cue", 300, "w"),
    ("sound_id", "Sound id", 70, "e"),
    ("volume", "Volume", 60, "e"),
    ("pan", "Pan", 50, "e"),
    ("flags", "Flags", 50, "e"),
    ("range", "Range", 60, "e"),
)


class SfxViewer(EditorPanel):
    display_name = "Sound effects"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._cues: list[gcfesnd.SfxCue] = []
        self._by_iid: dict[str, gcfesnd.SfxCue] = {}
        self._banks: musyx.SoundBanks | None = None
        self._stbl_names: list[str] = []
        self._slib: bytes = b""
        self._scratch_dir = Path(tempfile.mkdtemp(prefix="tellius_sfx_"))
        self.bind("<Destroy>", self._on_destroy)
        self.bind("<Unmap>", self._on_unmap)
        self._build_widgets()
        self._load()

    def _build_widgets(self) -> None:
        top = ttk.Frame(self, padding=(8, 8, 8, 0))
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self._query = tk.StringVar()
        ttk.Entry(top, textvariable=self._query).pack(side="left", fill="x", expand=True, padx=(6, 12))
        self._query.trace_add("write", lambda *_: self._refresh())
        ttk.Label(top, text="Group").pack(side="left")
        self._group = tk.StringVar(value=ALL_GROUPS)
        self._group_box = ttk.Combobox(top, textvariable=self._group, state="readonly", width=12, values=[ALL_GROUPS])
        self._group_box.pack(side="left", padx=(6, 0))
        self._group_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh())

        self._count = ttk.Label(self, text="", style="Muted.TLabel", padding=(8, 4))
        self._count.pack(anchor="w")

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(body)
        body.add(left, weight=3)
        self._tree = ttk.Treeview(left, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for key, title, width, anchor in COLUMNS:
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor=anchor, stretch=key == "name")
        scroll = ttk.Scrollbar(left, command=self._tree.yview)
        self._tree.config(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._show_detail())
        self._tree.bind("<Double-1>", lambda _e: self._play())
        self._tree.bind("<Return>", lambda _e: self._play())

        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        body.add(right, weight=2)
        self._title = ttk.Label(right, text="(no cue selected)", font=("Segoe UI", 12, "bold"))
        self._title.pack(anchor="w")
        self._detail = ttk.Label(right, text="", justify="left")
        self._detail.pack(anchor="w", pady=(8, 0))
        playback = ttk.Frame(right)
        playback.pack(anchor="w", pady=(12, 0))
        self._play_button = ttk.Button(playback, text="Play", command=self._play, state="disabled")
        self._play_button.pack(side="left")
        self._stop_button = ttk.Button(playback, text="Stop", command=self._stop, state="disabled")
        self._stop_button.pack(side="left", padx=(6, 0))
        edit = ttk.Frame(right)
        edit.pack(anchor="w", pady=(14, 0))
        ttk.Button(edit, text="Add sound effect...", command=self._add_cue).pack(side="left")
        self._replace_button = ttk.Button(edit, text="Replace audio...", command=self._replace_cue, state="disabled")
        self._replace_button.pack(side="left", padx=(6, 0))
        self._play_status = ttk.Label(right, text="", style="Muted.TLabel", wraplength=360, justify="left")
        self._play_status.pack(anchor="w", pady=(6, 0))
        if winsound is None:
            self._play_status.config(text="Playback needs Windows (winsound) - not available here.")
        ttk.Label(
            right,
            text="Cue names and parameters come from Sound/gcfesnd.bin.\n"
            "Playback decodes the cue's sample from the MusyX banks, or renders\n"
            "the sequenced songs of gcfesnd.slib; envelopes, panning and\n"
            "layering are ignored, so it is only approximate.\n"
            "Range is inferred from the game's accessors, not confirmed.",
            style="Muted.TLabel",
            justify="left",
        ).pack(anchor="w", side="bottom")

    def _on_unmap(self, event: tk.Event) -> None:
        if event.widget is self:
            self._stop()

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self:
            if winsound is not None:
                winsound.PlaySound(None, winsound.SND_PURGE)
            shutil.rmtree(self._scratch_dir, ignore_errors=True)

    def _load(self) -> None:
        path = self._project.extracted_dir / "files" / "Sound" / "gcfesnd.bin"
        if not path.exists():
            self._count.config(text="Sound/gcfesnd.bin not found. Extract the project first.")
            return
        try:
            self._cues = gcfesnd.read_sfx_cues_path(path)
        except gcfesnd.GcfesndError as exc:
            self._count.config(text=f"Could not read gcfesnd.bin: {exc}")
            return
        try:
            self._banks = musyx.SoundBanks(path.parent)
            stbl = path.with_suffix(".stbl")
            if stbl.exists():
                self._stbl_names = musyx.read_stbl_names(stbl)
            slib = path.with_suffix(".slib")
            if slib.exists():
                self._slib = slib.read_bytes()
        except (musyx.MusyxError, OSError, ValueError) as exc:
            self._play_status.config(text=f"Playback unavailable: {exc}")
        groups = sorted({c.group for c in self._cues})
        self._group_box.config(values=[ALL_GROUPS, *groups])
        self._refresh()

    def _refresh(self) -> None:
        query = self._query.get().strip().lower()
        group = self._group.get()
        self._tree.delete(*self._tree.get_children())
        self._by_iid.clear()
        shown = 0
        for index, cue in enumerate(self._cues):
            if group != ALL_GROUPS and cue.group != group:
                continue
            if query and query not in cue.name.lower() and query != f"{cue.sound_id}":
                continue
            iid = str(index)
            self._by_iid[iid] = cue
            self._tree.insert("", "end", iid=iid, values=(
                cue.name, cue.sound_id, cue.volume, cue.pan, cue.flags, cue.range_value))
            shown += 1
        self._count.config(text=f"{shown} of {len(self._cues)} sound effects")

    def _selected_cue(self) -> gcfesnd.SfxCue | None:
        selection = self._tree.selection()
        return self._by_iid.get(selection[0]) if selection else None

    def _show_detail(self) -> None:
        cue = self._selected_cue()
        if cue is None:
            return
        self._stop()
        self._play_button.config(state="normal" if winsound and self._banks else "disabled")
        self._replace_button.config(state="normal")
        sharing = sum(1 for c in self._cues if c.sound_id == cue.sound_id)
        self._title.config(text=cue.name)
        self._detail.config(text=(
            f"Group: {cue.group}\n"
            f"Sound id: {cue.sound_id} ({cue.sound_id:#x}), shared by {sharing} cue(s)\n"
            f"Default volume: {cue.volume}/127\n"
            f"Pan: {cue.pan} (64 = centre)\n"
            f"Flags: {cue.flags:#04x} (voice class {cue.voice_class})\n"
            f"Bytes +0x0C: {cue.extra.hex(' ')}\n"
            f"Range (+0x10): {cue.range_value}\n"
            f"Record offset: {cue.offset:#x}"))

    # -- adding / replacing ---------------------------------------------------
    def _open_import(self, cue: gcfesnd.SfxCue | None) -> None:
        if not self._cues:
            messagebox.showinfo("Sound effects", "Extract the project first.", parent=self)
            return
        self._stop()
        try:
            SfxImportDialog(self, self._project, self._changelog, cue, self._after_edit)
        except (musyx.MusyxError, OSError) as exc:
            messagebox.showerror("Sound effects", f"Could not open the sound banks: {exc}", parent=self)

    def _add_cue(self) -> None:
        self._open_import(None)

    def _replace_cue(self) -> None:
        cue = self._selected_cue()
        if cue is not None:
            self._open_import(cue)

    def _after_edit(self, name: str) -> None:
        """Reload the tables and select the cue that was just added/replaced."""
        for wav in self._scratch_dir.glob("*.wav"):
            wav.unlink(missing_ok=True)
        self._load()
        for iid, cue in self._by_iid.items():
            if cue.name == name:
                self._tree.selection_set(iid)
                self._tree.see(iid)
                break
        self._play_status.config(text=f"Saved {name}. Build the project to use it in the game.")

    # -- playback -----------------------------------------------------------
    def _render(self, cue: gcfesnd.SfxCue) -> tuple[int, np.ndarray]:
        """(sample rate, int16 samples) of a cue: an FX sound, else a song."""
        assert self._banks is not None
        if self._banks.fx_entry(cue.sound_id) is not None:
            sfx = self._banks.render(cue.sound_id)
            return sfx.sample_rate, np.asarray(sfx.samples, dtype=np.int16)
        song = cue.sound_id >> 8
        if cue.sound_id > 0xFF and self._slib:
            return musyx_song.render_song(self._banks, self._slib, song)
        raise musyx.MusyxError(f"Sound id {cue.sound_id} is neither an FX id nor a song.")

    def _play(self) -> None:
        cue = self._selected_cue()
        if cue is None or winsound is None or self._banks is None:
            return
        wav_path = self._scratch_dir / f"{cue.sound_id}.wav"
        if not wav_path.exists():
            self._play_status.config(text=f"Rendering {cue.name}...")
            self.update_idletasks()
            try:
                rate, samples = self._render(cue)
            except (musyx.MusyxError, musyx_song.SongError, OSError) as exc:
                self._play_status.config(text=f"Can't play {cue.name}: {exc}")
                return
            _write_wav(wav_path, rate, samples)
        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        self._stop_button.config(state="normal")
        self._play_status.config(text=f"Playing {cue.name}{self._song_note(cue)}")

    def _song_note(self, cue: gcfesnd.SfxCue) -> str:
        if self._banks is None or self._banks.fx_entry(cue.sound_id) is not None or cue.sound_id <= 0xFF:
            return ""
        index = cue.sound_id >> 8
        name = self._stbl_names[index] if index < len(self._stbl_names) else f"song {index}"
        return f" (sequenced: {name}, approximate)"

    def _stop(self) -> None:
        if winsound is not None:
            winsound.PlaySound(None, winsound.SND_PURGE)
        self._stop_button.config(state="disabled")
        if self._play_status.cget("text").startswith("Playing "):
            self._play_status.config(text="")


def _write_wav(path: Path, rate: int, samples: np.ndarray) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(np.asarray(samples, dtype="<i2").tobytes())
