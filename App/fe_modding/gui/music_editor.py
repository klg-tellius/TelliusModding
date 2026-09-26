"""Music editor: browse, play, export, and replace the game's background
music (``Sound/*.stm``).

Import accepts WAV directly, or any other format the bundled FFmpeg can
decode (MP3, OGG, FLAC, ...) - non-WAV input is transcoded to a scratch
16-bit PCM WAV first via tools.decode_audio_to_wav(), then handled exactly
like a native WAV pick. See tools.py's module docstring for why FFmpeg is
already a bundled dependency (it's also used for THP video import).

Playback uses the stdlib ``winsound`` module (Windows-only, same constraint
as the rest of this app - see tools.py) against a WAV file decoded to a
scratch temp file; there's no in-memory playback API in the standard
library.

Encoding (Import) is slow - real DSP-ADPCM encoding, not a quick format
conversion (see fe_modding.formats.dsp_adpcm's docstring for why: it's an
iterative statistical fit, not a formula) - roughly 1.5-2x realtime *per
channel*, so a stereo track takes about 3-4x its own length to encode.
Runs on a background thread with a progress bar, same pattern as disc
extract/build in app.py, just implemented locally here rather than shared -
see CLAUDE.md for why that duplication is deliberate.

"New Track..." writes a brand-new .stm file into Sound/ - straightforward
since stm.write_stm() already produces a fully self-contained file, no
format-layer change needed. It's honestly labeled as *unwired*, though:
nothing reverse-engineered anywhere in this app's formats package maps a
track ID/name to a Sound/*.stm filename for the game to actually play one,
so a new track sits on disc and is visible/playable in this editor but isn't
audible in-game until that lookup is found and patched separately - see the
in-app note next to the button, and don't claim otherwise. Shares
_prompt_for_audio()/_confirm_and_encode() with _import_audio() (the WAV
pick/loop-prompt/decode step, and the confirm-with-time-estimate/background-
encode step) - genuine duplication between the two flows added in the same
change, factored out rather than copy-pasted.
"""

from __future__ import annotations

import queue
import shutil
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .. import tools
from ..exceptions import ModdingError
from ..formats import stm
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel

try:
    import winsound
except ImportError:
    winsound = None


class MusicEditor(EditorPanel):
    display_name = "Music"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._current_path: Path | None = None
        self._current_audio: stm.StmAudio | None = None
        self._playback_wav: Path | None = None
        self._task_running = False
        self._scratch_dir = Path(tempfile.mkdtemp(prefix="tellius_music_"))

        self._build_widgets()
        self._load_track_list()

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=1)
        ttk.Label(left, text="Tracks").pack(anchor="w")

        search_var = tk.StringVar()
        ttk.Entry(left, textvariable=search_var).pack(fill="x", pady=(4, 4))
        search_var.trace_add("write", lambda *_: self._apply_filter(search_var.get()))

        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self._file_list = tk.Listbox(list_frame, exportselection=False)
        self._file_list.pack(fill="both", expand=True, side="left")
        scrollbar = ttk.Scrollbar(list_frame, command=self._file_list.yview)
        scrollbar.pack(fill="y", side="right")
        self._file_list.config(yscrollcommand=scrollbar.set)
        self._file_list.bind("<<ListboxSelect>>", lambda e: self._on_file_selected())

        right = ttk.Frame(paned, padding=8)
        paned.add(right, weight=2)

        self._track_label = ttk.Label(right, text="(no track selected)", font=("Segoe UI", 12, "bold"))
        self._track_label.pack(anchor="w")
        self._info_label = ttk.Label(right, text="", style="Muted.TLabel")
        self._info_label.pack(anchor="w", pady=(0, 12))

        playback_row = ttk.Frame(right)
        playback_row.pack(fill="x", pady=(0, 8))
        self._play_button = ttk.Button(playback_row, text="Play", command=self._play, state="disabled")
        self._play_button.pack(side="left")
        self._stop_button = ttk.Button(playback_row, text="Stop", command=self._stop, state="disabled")
        self._stop_button.pack(side="left", padx=(6, 0))
        if winsound is None:
            ttk.Label(right, text="Playback needs Windows (winsound) - not available here.", foreground="#a33").pack(
                anchor="w"
            )

        io_row = ttk.Frame(right)
        io_row.pack(fill="x", pady=(0, 8))
        self._export_button = ttk.Button(io_row, text="Export WAV...", command=self._export_wav, state="disabled")
        self._export_button.pack(side="left")
        self._import_button = ttk.Button(
            io_row, text="Import Replacement Audio...", command=self._import_audio, state="disabled"
        )
        self._import_button.pack(side="left", padx=(6, 0))
        self._add_track_button = ttk.Button(io_row, text="New Track...", command=self._add_new_track)
        self._add_track_button.pack(side="left", padx=(6, 0))

        self._progress = ttk.Progressbar(right, mode="indeterminate")
        self._status_label = ttk.Label(right, text="", style="Muted.TLabel", wraplength=480)
        self._status_label.pack(anchor="w", fill="x", pady=(8, 0))

        ttk.Label(
            right,
            text="Import accepts WAV, MP3, OGG, FLAC, and other common formats\n"
            "(converted automatically via the bundled FFmpeg). Mono or\n"
            "stereo only.\n\n"
            "A new track is written to Sound/ but nothing here maps a track\n"
            "ID to a filename for the game to actually play it - that lookup\n"
            "hasn't been reverse-engineered, so a new track needs manual\n"
            "wiring elsewhere before it's audible in-game.",
            style="Muted.TLabel",
            justify="left",
        ).pack(anchor="w", side="bottom", pady=(8, 0))

    # -- data loading ---------------------------------------------------------
    def _load_track_list(self) -> None:
        sound_dir = self._project.extracted_dir / "files" / "Sound"
        self._all_files = sorted(sound_dir.glob("*.stm")) if sound_dir.exists() else []
        self._apply_filter("")

        if not self._all_files:
            ttk.Label(
                self._file_list.master,
                text="No music files found.\nExtract the project first.",
                style="Muted.TLabel",
            ).pack(pady=8)

    def _apply_filter(self, query: str) -> None:
        query = query.strip().lower()
        self._filtered_files = [p for p in self._all_files if query in p.stem.lower()]
        self._file_list.delete(0, "end")
        for path in self._filtered_files:
            self._file_list.insert("end", path.stem)

    def _on_file_selected(self) -> None:
        selection = self._file_list.curselection()
        if not selection:
            return
        self._stop()
        self._current_path = self._filtered_files[selection[0]]
        self._track_label.config(text=self._current_path.stem)
        self._info_label.config(text="Loading...")
        self._play_button.config(state="disabled")
        self._export_button.config(state="disabled")
        self._import_button.config(state="disabled")

        self._run_task(
            f"Decoding {self._current_path.name} ...",
            lambda: stm.read_stm_path(self._current_path),
            on_success=self._on_track_loaded,
        )

    def _on_track_loaded(self, audio: stm.StmAudio) -> None:
        self._current_audio = audio
        num_samples = len(audio.channels[0])
        duration = num_samples / audio.sample_rate
        loop_text = f", loops at {audio.loop_start / audio.sample_rate:.1f}s" if audio.loop_start is not None else ""
        self._info_label.config(
            text=f"{audio.sample_rate} Hz, {len(audio.channels)}ch, {duration:.1f}s{loop_text}"
        )
        self._status_label.config(text="")
        self._play_button.config(state="normal" if winsound else "disabled")
        self._export_button.config(state="normal")
        self._import_button.config(state="normal")
        self._playback_wav = None

    # -- playback -----------------------------------------------------------
    def _play(self) -> None:
        if winsound is None or self._current_audio is None:
            return
        if self._playback_wav is None:
            self._playback_wav = self._scratch_dir / f"{self._current_path.stem}.wav"
            stm.stm_to_wav_path(self._current_audio, self._playback_wav)
        winsound.PlaySound(str(self._playback_wav), winsound.SND_FILENAME | winsound.SND_ASYNC)
        self._stop_button.config(state="normal")

    def _stop(self) -> None:
        if winsound is not None:
            winsound.PlaySound(None, winsound.SND_PURGE)
        self._stop_button.config(state="disabled")

    # -- export / import -------------------------------------------------------
    def _export_wav(self) -> None:
        if self._current_audio is None or self._current_path is None:
            return
        chosen = filedialog.asksaveasfilename(
            title="Export as WAV",
            initialfile=f"{self._current_path.stem}.wav",
            defaultextension=".wav",
            filetypes=[("WAV audio", "*.wav")],
            parent=self,
        )
        if not chosen:
            return
        try:
            stm.stm_to_wav_path(self._current_audio, chosen)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not export", str(exc), parent=self)
            return
        self._status_label.config(text=f"Exported to {chosen}")

    def _import_audio(self) -> None:
        if self._current_path is None or self._current_audio is None:
            return
        new_audio = self._prompt_for_audio(
            should_ask_loop=self._current_audio.loop_start is not None, already_loops=True
        )
        if new_audio is None:
            return
        self._confirm_and_encode(new_audio, self._current_path, verb="replace", on_success=self._on_import_done)

    def _on_import_done(self, new_audio: stm.StmAudio) -> None:
        self._current_audio = new_audio
        self._playback_wav = None
        self._on_track_loaded(new_audio)
        self._status_label.config(text=f"Replaced {self._current_path.name}")
        self._changelog.append(self._current_path.stem, "Replaced audio track")

    def _add_new_track(self) -> None:
        sound_dir = self._project.extracted_dir / "files" / "Sound"
        if not sound_dir.exists():
            messagebox.showerror("No Sound folder", "Extract the project first.", parent=self)
            return

        name = simpledialog.askstring(
            "New track name",
            "Internal filename (no extension) - match the game's existing naming, e.g. C01_M:",
            parent=self,
        )
        if not name:
            return
        name = name.strip()
        if not name or name != Path(name).name:
            messagebox.showerror("Invalid name", "Enter a plain filename with no path separators.", parent=self)
            return

        dest = sound_dir / f"{name}.stm"
        if dest.exists():
            messagebox.showerror("Already exists", f"{dest.name} already exists.", parent=self)
            return

        new_audio = self._prompt_for_audio(should_ask_loop=True, already_loops=False)
        if new_audio is None:
            return
        self._confirm_and_encode(new_audio, dest, verb="create", on_success=lambda audio: self._on_new_track_added(dest, audio))

    def _on_new_track_added(self, dest: Path, new_audio: stm.StmAudio) -> None:
        self._load_track_list()
        if dest in self._filtered_files:
            idx = self._filtered_files.index(dest)
            self._file_list.selection_clear(0, "end")
            self._file_list.selection_set(idx)
            self._file_list.see(idx)
        self._current_path = dest
        self._track_label.config(text=dest.stem)
        self._on_track_loaded(new_audio)
        self._status_label.config(text=f"Added {dest.name} - not wired to any in-game trigger yet.")
        self._changelog.append(dest.stem, "Added new (unwired) track")

    # -- shared import/add-track plumbing --------------------------------
    def _prompt_for_audio(self, should_ask_loop: bool, already_loops: bool) -> "stm.StmAudio | None":
        """Pick a WAV, resolve its loop point (if any), and decode it - the
        part shared by _import_audio() (replacing a track, which may
        already loop) and _add_new_track() (a brand-new track, so the user
        is asked outright rather than defaulting from existing metadata).
        Returns None if cancelled at any step."""
        chosen = filedialog.askopenfilename(
            title="Choose audio to import",
            filetypes=[
                ("Audio files", "*.wav *.mp3 *.ogg *.flac *.m4a *.aac *.wma"),
                ("WAV audio", "*.wav"),
                ("All files", "*.*"),
            ],
            parent=self,
        )
        if not chosen:
            return None

        chosen_path = Path(chosen)
        if chosen_path.suffix.lower() != ".wav":
            converted = self._scratch_dir / f"{chosen_path.stem}_import.wav"
            try:
                tools.decode_audio_to_wav(chosen_path, converted)
            except ModdingError as exc:
                messagebox.showerror("Could not convert audio", str(exc), parent=self)
                return None
            chosen = str(converted)

        loop_seconds = None
        if should_ask_loop:
            prompt = (
                "This track loops in-game. Should the replacement also loop?\n\n"
                "You'll be asked for a loop start time next."
                if already_loops
                else "Should this track loop when it reaches the end?\n\nYou'll be asked for a loop start time next."
            )
            if messagebox.askyesno("Looping track", prompt, parent=self):
                loop_seconds = simpledialog.askfloat(
                    "Loop point",
                    "Loop start, in seconds from the beginning of the audio:",
                    initialvalue=0.0,
                    minvalue=0.0,
                    parent=self,
                )
                if loop_seconds is None:
                    return None

        try:
            audio = stm.wav_path_to_stm_audio(chosen)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read WAV", str(exc), parent=self)
            return None

        if loop_seconds is not None:
            audio.loop_start = round(loop_seconds * audio.sample_rate)
            if audio.loop_start >= len(audio.channels[0]):
                messagebox.showerror("Invalid loop point", "The loop start is past the end of the audio.", parent=self)
                return None

        return audio

    def _confirm_and_encode(self, audio: "stm.StmAudio", dest_path: Path, verb: str, on_success) -> None:
        duration = len(audio.channels[0]) / audio.sample_rate
        est_seconds = duration * len(audio.channels) * 2  # rough: ~2x realtime per channel, observed ~1.7x
        if not messagebox.askyesno(
            "Encode?",
            f"This will encode {duration:.1f}s of audio ({len(audio.channels)} channel(s)) and {verb} "
            f"{dest_path.name}.\n\nEncoding is slow - expect roughly {est_seconds:.0f}s. Continue?",
            parent=self,
        ):
            return

        def work():
            data = stm.write_stm(audio)
            dest_path.write_bytes(data)
            return audio

        self._run_task(f"Encoding (~{est_seconds:.0f}s expected)...", work, on_success=on_success)

    # -- background task plumbing (mirrors app.py's _run_task) --------------
    def _run_task(self, status_text: str, work_fn, on_success) -> None:
        self._task_running = True
        self._file_list.config(state="disabled")
        self._status_label.config(text=status_text)
        self._progress.pack(fill="x", pady=(4, 0))
        self._progress.start(12)

        result_queue: "queue.Queue" = queue.Queue()

        def worker():
            try:
                result = work_fn()
                result_queue.put(("ok", result))
            except ModdingError as exc:
                result_queue.put(("error", str(exc)))
            except Exception as exc:  # noqa: BLE001
                result_queue.put(("error", f"Unexpected error: {exc}"))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_task(result_queue, on_success)

    def _poll_task(self, result_queue: "queue.Queue", on_success) -> None:
        try:
            status, payload = result_queue.get_nowait()
        except queue.Empty:
            self.after(150, lambda: self._poll_task(result_queue, on_success))
            return

        self._progress.stop()
        self._progress.pack_forget()
        self._task_running = False
        self._file_list.config(state="normal")

        if status == "ok":
            on_success(payload)
        else:
            self._status_label.config(text="")
            messagebox.showerror("Operation failed", payload, parent=self)

    # -- cleanup ----------------------------------------------------------
    def cleanup(self) -> None:
        self._stop()
        shutil.rmtree(self._scratch_dir, ignore_errors=True)
