"""Video viewer/importer: browse, play, and replace the game's cutscenes
(``Movie/*.thp``).

Playback: frame decode is fast (~3ms/frame in testing, well under the
~33ms/frame budget for 30fps), so frames are decoded live during playback
rather than pre-extracted. Audio plays separately via winsound (Windows-only,
same constraint as tools.py) against a temp WAV decoded from the current
frame onward - there's no way to feed winsound live PCM, only a file.

Import: replaces a cutscene with any video FFmpeg can read (tools.py's
decode_video_to_frames()/decode_video_to_wav() - the general "arbitrary
video format" problem, which is not this app's job to solve itself),
scaled/padded to the target slot's own dimensions and frame rate, then
re-encoded to THP by fe_modding.formats.thp.encode_thp() - real work (JPEG
frame packaging, DSP-ADPCM audio, a frame-chain header where each frame
describes its *neighbors'* sizes rather than its own), not a quick format
conversion. **Genuinely slow** - JPEG-encoding thousands of frames plus
real DSP-ADPCM audio encoding (itself ~1.7x realtime per channel, same as
the music editor) means a full-length cutscene can take several minutes;
runs on a background thread with a progress bar and an upfront time
estimate, same pattern as the music editor's import.

"New Video..." writes a brand-new .thp into Movie/ instead of overwriting
an existing one - shares _extract_source()/_confirm_and_encode() with
Import (both now take dest_path/width/height/fps/audio_frequency
explicitly rather than reading them off a selected file's self._info,
since a new video has no existing slot to inherit them from - the one
genuine behavioral difference is _NewVideoDialog asking for target
dimensions/fps up front, validated against THP's own documented
constraints (width/height a multiple of 16, width <= thp.MAX_WIDTH) before
any FFmpeg work starts). Unlike a new sound track, a new video is
genuinely wireable without further reverse-engineering: MoviePlay's
argument is a literal path string baked into a script's bytecode (see
GAME_NOTES.md's Cutscene video section), so editing the call in the
Script editor's source (``MoviePlay("Movie/new.thp")``) wires the new file
in directly - the compiler adds any new string to the script's pool.
"""

from __future__ import annotations

import queue
import shutil
import struct
import tempfile
import threading
import tkinter as tk
import wave
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import ImageTk

from .. import tools
from ..exceptions import ModdingError
from ..formats import stm, thp
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel

try:
    import winsound
except ImportError:
    winsound = None

PREVIEW_MAX_SIZE = (640, 480)


class VideoViewer(EditorPanel):
    display_name = "Videos"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._current_path: Path | None = None
        self._current_file: object | None = None  # open binary file handle for the selected video
        self._info: thp.ThpInfo | None = None
        self._offsets: list[int] = []
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._playing = False
        self._scrubbing = False
        self._task_running = False
        self._scratch_dir = Path(tempfile.mkdtemp(prefix="tellius_video_"))

        self._build_widgets()
        self._load_video_list()

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=1)
        ttk.Label(left, text="Cutscenes").pack(anchor="w")
        self._file_list = tk.Listbox(left, exportselection=False)
        self._file_list.pack(fill="both", expand=True, pady=(4, 0))
        self._file_list.bind("<<ListboxSelect>>", lambda e: self._on_file_selected())

        right = ttk.Frame(paned, padding=8)
        paned.add(right, weight=3)

        self._info_label = ttk.Label(right, text="(no video selected)", style="Muted.TLabel")
        self._info_label.pack(anchor="w")

        self._preview_label = ttk.Label(right, relief="groove", background="black")
        self._preview_label.pack(pady=(8, 8), fill="both", expand=True)

        self._frame_var = tk.IntVar(value=0)
        self._frame_slider = ttk.Scale(right, from_=0, to=0, orient="horizontal", command=self._on_slider_moved)
        self._frame_slider.pack(fill="x")
        self._frame_label = ttk.Label(right, text="Frame 0 / 0", style="Muted.TLabel")
        self._frame_label.pack(anchor="w")

        button_row = ttk.Frame(right)
        button_row.pack(fill="x", pady=(8, 0))
        self._play_button = ttk.Button(button_row, text="Play", command=self._play, state="disabled")
        self._play_button.pack(side="left")
        self._pause_button = ttk.Button(button_row, text="Pause", command=self._pause, state="disabled")
        self._pause_button.pack(side="left", padx=(6, 0))
        self._export_audio_button = ttk.Button(
            button_row, text="Export Audio as WAV...", command=self._export_audio, state="disabled"
        )
        self._export_audio_button.pack(side="left", padx=(6, 0))
        self._import_button = ttk.Button(
            button_row, text="Import Replacement Video...", command=self._import_video, state="disabled"
        )
        self._import_button.pack(side="left", padx=(6, 0))
        self._add_video_button = ttk.Button(button_row, text="New Video...", command=self._add_new_video)
        self._add_video_button.pack(side="left", padx=(6, 0))

        self._progress = ttk.Progressbar(right, mode="indeterminate")
        self._status_label = ttk.Label(right, text="", style="Muted.TLabel")
        self._status_label.pack(anchor="w", pady=(4, 0))

    # -- data loading ---------------------------------------------------------
    def _load_video_list(self) -> None:
        self._file_list.delete(0, "end")
        movie_dir = self._project.extracted_dir / "files" / "Movie"
        self._all_files = sorted(movie_dir.glob("*.thp")) if movie_dir.exists() else []
        for path in self._all_files:
            self._file_list.insert("end", path.stem)

        if not self._all_files:
            ttk.Label(
                self._file_list.master,
                text="No video files found.\nExtract the project first.",
                style="Muted.TLabel",
            ).pack(pady=8)

    def _on_file_selected(self) -> None:
        selection = self._file_list.curselection()
        if not selection:
            return
        self._pause()
        self._close_current_file()

        self._current_path = self._all_files[selection[0]]
        self._status_label.config(text="Loading...")
        self._play_button.config(state="disabled")
        self._export_audio_button.config(state="disabled")

        try:
            self._current_file = open(self._current_path, "rb")
            self._info = thp.read_info(self._current_file)
            self._offsets = thp.iter_frame_offsets(self._current_file, self._info)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read video", str(exc), parent=self)
            return

        duration = self._info.num_frames / self._info.fps
        audio_note = f", {self._info.audio_channels}ch {self._info.audio_frequency}Hz audio" if self._info.has_audio else " (no audio)"
        self._info_label.config(
            text=f"{self._current_path.stem}: {self._info.width}x{self._info.height}, "
            f"{self._info.fps:.2f} fps, {self._info.num_frames} frames, {duration:.1f}s{audio_note}"
        )
        self._frame_slider.config(to=max(self._info.num_frames - 1, 0))
        self._frame_var.set(0)
        self._show_frame(0)

        self._play_button.config(state="normal")
        self._refresh_action_button_states()
        self._status_label.config(text="")

    def _close_current_file(self) -> None:
        if self._current_file is not None:
            self._current_file.close()
            self._current_file = None

    # -- frame display --------------------------------------------------------
    def _on_slider_moved(self, value: str) -> None:
        if self._playing:
            return
        frame_index = int(float(value))
        self._show_frame(frame_index)

    def _show_frame(self, frame_index: int) -> None:
        if self._current_file is None or not self._offsets:
            return
        frame_index = max(0, min(frame_index, len(self._offsets) - 1))
        try:
            image, _audio = thp.read_frame(self._current_file, self._offsets[frame_index], self._info)
        except Exception as exc:  # noqa: BLE001
            self._status_label.config(text=f"Could not decode frame {frame_index}: {exc}")
            return

        if image is not None:
            preview = image.copy()
            preview.thumbnail(PREVIEW_MAX_SIZE)
            self._preview_photo = ImageTk.PhotoImage(preview)
            self._preview_label.config(image=self._preview_photo)

        self._frame_label.config(text=f"Frame {frame_index} / {len(self._offsets) - 1}")

    # -- playback -----------------------------------------------------------
    def _play(self) -> None:
        if self._info is None or self._playing:
            return
        self._playing = True
        self._play_button.config(state="disabled")
        self._pause_button.config(state="normal")

        start_frame = int(self._frame_slider.get())
        if winsound is not None and self._info.has_audio:
            self._run_task(
                "Preparing audio...",
                lambda: self._decode_audio_from(start_frame),
                on_success=lambda wav_path: self._start_playback(start_frame, wav_path),
            )
        else:
            self._start_playback(start_frame, None)

    def _start_playback(self, start_frame: int, wav_path: Path | None) -> None:
        if not self._playing:
            return  # paused while audio was being prepared
        if wav_path is not None and winsound is not None:
            winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        self._playback_frame = start_frame
        self._advance_playback()

    def _advance_playback(self) -> None:
        # Simple fixed-interval stepping, no drift correction against a clock -
        # over a long cutscene, accumulated per-frame overhead (decode + Tk
        # redraw) can let video drift a little behind the audio. Good enough
        # for a preview; a real player would resync against elapsed wall time.
        if not self._playing or self._info is None:
            return
        if self._playback_frame >= len(self._offsets):
            self._pause()
            return

        self._frame_slider.set(self._playback_frame)
        self._show_frame(self._playback_frame)
        self._playback_frame += 1

        interval_ms = max(1, round(1000 / self._info.fps))
        self.after(interval_ms, self._advance_playback)

    def _pause(self) -> None:
        self._playing = False
        self._play_button.config(state="normal" if self._info is not None else "disabled")
        self._pause_button.config(state="disabled")
        if winsound is not None:
            winsound.PlaySound(None, winsound.SND_PURGE)

    def _decode_audio_from(self, start_frame: int) -> Path:
        channels = [[] for _ in range(self._info.audio_channels)]
        with open(self._current_path, "rb") as f:
            for offset in self._offsets[start_frame:]:
                _image, audio = thp.read_frame(f, offset, self._info)
                for ch in range(len(channels)):
                    channels[ch].extend(audio[ch] if ch < len(audio) else [])

        num_samples = len(channels[0]) if channels else 0
        interleaved = [0] * (num_samples * self._info.audio_channels)
        for ch, pcm in enumerate(channels):
            interleaved[ch :: self._info.audio_channels] = pcm

        wav_path = self._scratch_dir / f"{self._current_path.stem}_{start_frame}.wav"
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(self._info.audio_channels)
            w.setsampwidth(2)
            w.setframerate(self._info.audio_frequency)
            w.writeframes(struct.pack(f"<{len(interleaved)}h", *interleaved))
        return wav_path

    # -- export -----------------------------------------------------------
    def _export_audio(self) -> None:
        if self._current_path is None or self._info is None or not self._info.has_audio:
            return
        chosen = filedialog.asksaveasfilename(
            title="Export audio as WAV",
            initialfile=f"{self._current_path.stem}.wav",
            defaultextension=".wav",
            filetypes=[("WAV audio", "*.wav")],
            parent=self,
        )
        if not chosen:
            return

        def work():
            return self._decode_audio_from(0)

        def on_success(wav_path: Path):
            shutil.copyfile(wav_path, chosen)
            self._status_label.config(text=f"Exported to {chosen}")

        self._run_task("Decoding audio...", work, on_success=on_success)

    # -- import -----------------------------------------------------------
    def _import_video(self) -> None:
        if self._current_path is None or self._info is None:
            return

        chosen = filedialog.askopenfilename(
            title=f"Choose a replacement video ({self._info.width}x{self._info.height} - it will be "
            "scaled/letterboxed to fit)",
            filetypes=[("Videos", "*.mp4 *.mkv *.avi *.mov *.webm *.wmv"), ("All files", "*.*")],
            parent=self,
        )
        if not chosen:
            return

        info = self._info
        self._run_task(
            "Decoding source video with FFmpeg...",
            lambda: self._extract_source(
                Path(chosen), info.width, info.height, info.fps, info.audio_frequency or 32000, info.audio_channels or 2
            ),
            on_success=lambda result: self._confirm_and_encode(
                result, self._current_path, info.fps, info.audio_frequency or 32000, self._on_import_done
            ),
        )

    def _extract_source(
        self, source: Path, width: int, height: int, fps: float, audio_frequency: int, audio_channels: int
    ) -> tuple[list[Path], Path | None]:
        frames_dir = self._scratch_dir / "import_frames"
        if frames_dir.exists():
            shutil.rmtree(frames_dir)
        frame_paths = tools.decode_video_to_frames(source, frames_dir, width=width, height=height, fps=fps)

        wav_path = self._scratch_dir / "import_audio.wav"
        has_audio = tools.decode_video_to_wav(source, wav_path, sample_rate=audio_frequency, channels=audio_channels)
        return frame_paths, (wav_path if has_audio else None)

    def _confirm_and_encode(
        self, result: tuple[list[Path], Path | None], dest_path: Path, fps: float, audio_frequency: int, on_success
    ) -> None:
        frame_paths, wav_path = result
        num_frames = len(frame_paths)
        duration = num_frames / fps
        # rough combined heuristic from measured JPEG-encode + DSP-ADPCM-encode throughput -
        # not a guarantee, just enough to set expectations before a multi-minute operation.
        est_seconds = num_frames * 0.08 + (duration * 3.5 if wav_path else 0)

        if not messagebox.askyesno(
            "Encode?",
            f"Decoded {num_frames} frames ({duration:.1f}s){' with audio' if wav_path else ' (no audio track found)'}.\n\n"
            f"This will encode all of it to THP and write {dest_path.name}.\n"
            f"Encoding is slow - expect roughly {est_seconds:.0f}s. Continue?",
            parent=self,
        ):
            return

        def work():
            pcm_channels = None
            if wav_path is not None:
                audio = stm.wav_path_to_stm_audio(wav_path)
                pcm_channels = audio.channels

            # Pass paths, not pre-opened Images: a multi-minute source video
            # can decode to thousands of frames, and thp.encode_thp() opens,
            # encodes, and closes each on its own turn - opening them all
            # upfront would exhaust both memory (every frame's full pixel
            # buffer resident at once) and the OS's open-file-handle limit
            # well before encoding even starts.
            data = thp.encode_thp(frame_paths, pcm_channels, audio_frequency, fps)
            dest_path.write_bytes(data)
            return data

        self._run_task(f"Encoding (~{est_seconds:.0f}s expected)...", work, on_success=on_success)

    def _on_import_done(self, data: bytes) -> None:
        self._close_current_file()
        self._current_file = open(self._current_path, "rb")
        self._info = thp.read_info(self._current_file)
        self._offsets = thp.iter_frame_offsets(self._current_file, self._info)

        duration = self._info.num_frames / self._info.fps
        audio_note = f", {self._info.audio_channels}ch {self._info.audio_frequency}Hz audio" if self._info.has_audio else " (no audio)"
        self._info_label.config(
            text=f"{self._current_path.stem}: {self._info.width}x{self._info.height}, "
            f"{self._info.fps:.2f} fps, {self._info.num_frames} frames, {duration:.1f}s{audio_note}"
        )
        self._frame_slider.config(to=max(self._info.num_frames - 1, 0))
        self._frame_slider.set(0)
        self._show_frame(0)
        self._status_label.config(text=f"Replaced {self._current_path.name}")
        self._changelog.append(self._current_path.stem, "Replaced cutscene video")

    def _add_new_video(self) -> None:
        movie_dir = self._project.extracted_dir / "files" / "Movie"
        if not movie_dir.exists():
            messagebox.showerror("No Movie folder", "Extract the project first.", parent=self)
            return

        name = simpledialog.askstring(
            "New video name",
            "Internal filename (no extension) - match the game's existing naming, e.g. s99:",
            parent=self,
        )
        if not name:
            return
        name = name.strip()
        if not name or name != Path(name).name:
            messagebox.showerror("Invalid name", "Enter a plain filename with no path separators.", parent=self)
            return

        dest = movie_dir / f"{name}.thp"
        if dest.exists():
            messagebox.showerror("Already exists", f"{dest.name} already exists.", parent=self)
            return

        dims_dialog = _NewVideoDialog(self)
        self.wait_window(dims_dialog)
        if dims_dialog.result is None:
            return
        width, height, fps = dims_dialog.result

        chosen = filedialog.askopenfilename(
            title=f"Choose a source video ({width}x{height} - it will be scaled/letterboxed to fit)",
            filetypes=[("Videos", "*.mp4 *.mkv *.avi *.mov *.webm *.wmv"), ("All files", "*.*")],
            parent=self,
        )
        if not chosen:
            return

        self._run_task(
            "Decoding source video with FFmpeg...",
            lambda: self._extract_source(Path(chosen), width, height, fps, 32000, 2),
            on_success=lambda result: self._confirm_and_encode(
                result, dest, fps, 32000, lambda data: self._on_new_video_added(dest, data)
            ),
        )

    def _on_new_video_added(self, dest: Path, data: bytes) -> None:
        self._load_video_list()
        if dest in self._all_files:
            idx = self._all_files.index(dest)
            self._file_list.selection_clear(0, "end")
            self._file_list.selection_set(idx)
            self._file_list.see(idx)
            self._on_file_selected()
        self._status_label.config(
            text=f"Added {dest.name} - call MoviePlay(\"Movie/{dest.name}\") in a chapter's Script editor "
            "to make it play."
        )
        self._changelog.append(dest.stem, "Added new video")

    # -- background task plumbing (mirrors app.py's _run_task) --------------
    def _run_task(self, status_text: str, work_fn, on_success) -> None:
        self._task_running = True
        self._file_list.config(state="disabled")
        self._import_button.config(state="disabled")
        self._export_audio_button.config(state="disabled")
        self._add_video_button.config(state="disabled")
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
            self._status_label.config(text="")  # on_success sets its own final status if it wants one to persist
            on_success(payload)
        else:
            self._status_label.config(text="")
            messagebox.showerror("Operation failed", payload, parent=self)
            self._playing = False
            self._play_button.config(state="normal")
            self._pause_button.config(state="disabled")

        # on_success may have kicked off a *new* background task (the import flow's
        # extract-then-confirm-then-encode chain) - don't clobber its disabled buttons.
        if not self._task_running:
            self._refresh_action_button_states()

    def _refresh_action_button_states(self) -> None:
        loaded = self._info is not None
        self._import_button.config(state="normal" if loaded else "disabled")
        self._export_audio_button.config(state="normal" if (loaded and self._info.has_audio) else "disabled")
        self._add_video_button.config(state="normal")

    # -- cleanup ----------------------------------------------------------
    def cleanup(self) -> None:
        self._pause()
        self._close_current_file()
        shutil.rmtree(self._scratch_dir, ignore_errors=True)


class _NewVideoDialog(tk.Toplevel):
    """Prompts for a new video's target width/height/frame rate. Unlike
    Import (which reuses an existing slot's own dimensions), a brand-new
    video has no slot to inherit from, so this validates THP's own
    documented encoding constraints (width/height each a multiple of 16,
    width capped at thp.MAX_WIDTH) up front, before any FFmpeg work
    starts."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("New video dimensions")
        self.resizable(False, False)
        self.result: tuple[int, int, float] | None = None

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text=f"Width and height must each be a multiple of 16\n(width ≤ {thp.MAX_WIDTH}) - THP's own "
            "encoding requirement.",
            style="Muted.TLabel",
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self._width_var = tk.StringVar(value="640")
        self._height_var = tk.StringVar(value="480")
        self._fps_var = tk.StringVar(value="30")

        for i, (label, var) in enumerate(
            [("Width:", self._width_var), ("Height:", self._height_var), ("Frame rate:", self._fps_var)]
        ):
            ttk.Label(frame, text=label).grid(row=i + 1, column=0, sticky="w", pady=4)
            ttk.Entry(frame, textvariable=var, width=10).grid(row=i + 1, column=1, sticky="w", padx=(6, 0))

        button_row = ttk.Frame(frame)
        button_row.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(button_row, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(button_row, text="Continue", command=self._on_apply).pack(side="right", padx=(0, 6))

        self.transient(parent)
        self.grab_set()

    def _on_apply(self) -> None:
        try:
            width = int(self._width_var.get())
            height = int(self._height_var.get())
            fps = float(self._fps_var.get())
        except ValueError:
            messagebox.showerror("Invalid value", "Width/height must be whole numbers, frame rate a number.", parent=self)
            return
        if width % 16 or height % 16:
            messagebox.showerror("Invalid dimensions", "Width and height must each be a multiple of 16.", parent=self)
            return
        if width > thp.MAX_WIDTH:
            messagebox.showerror("Invalid dimensions", f"Width must be at most {thp.MAX_WIDTH}.", parent=self)
            return
        if fps <= 0:
            messagebox.showerror("Invalid frame rate", "Frame rate must be positive.", parent=self)
            return
        self.result = (width, height, fps)
        self.destroy()
