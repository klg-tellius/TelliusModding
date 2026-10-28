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

"New Track..." writes a brand-new .stm file into Sound/ and adds a music
cue for it: a ``BGM_*`` record in ``Sound/gcfesnd.bin`` naming the file
(``gcfesnd.add_bgm_cue``). The game plays music by cue name (``play_bgm``
looks the name up in the table every record is registered in at boot), so
the new cue works wherever a retail one does: a chapter's map music
(Game Data > Chapters), ``BGMPlay`` in a script. The **Music cues** row lists
the cues that play the selected track; **New cue...** adds another and
**Remove cue** removes an added one. Shares
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
from ..formats import brsar, brstm, fe10_sound, gcfesnd, lz10, stm
from ..games import Game
from ..media_references import executable_bgm_cues, front_end_track_cues
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .widgets import confirm_delete_added, list_buttons, tip

try:
    import winsound
except ImportError:
    winsound = None


def _cue_name_for(path: Path) -> str:
    """``my_theme_32k.stm`` -> ``BGM_MY_THEME``."""
    stem = path.stem.upper()
    for suffix in ("_32K", "_LP"):
        stem = stem.removesuffix(suffix)
    return "BGM_" + stem.removeprefix("GCFE_BGM_").removeprefix("BGM_")


class MusicEditor(EditorPanel):
    display_name = "Music"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._fe10 = project.game == Game.RADIANT_DAWN
        self._changelog = changelog
        self._current_path: Path | None = None
        self._current_audio: stm.StmAudio | None = None
        self._playback_wav: Path | None = None
        self._task_running = False
        self._rd_streams: dict[str, str] | None = None
        self._scratch_dir = Path(tempfile.mkdtemp(prefix="tellius_music_"))
        self._native_bgm_cues = executable_bgm_cues(self._project.extracted_dir / "sys" / "main.dol")

        self._build_widgets()
        self._load_track_list()

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=1)
        tip(ttk.Label(left, text="Tracks"), "The .stm streams of Sound/. The game plays them through music "
            "cues (BGM_ names in Sound/gcfesnd.bin): a new track gets a cue, which chapters (map music) and "
            "scripts (BGMPlay) then name.").pack(anchor="w")

        search_var = tk.StringVar()
        ttk.Entry(left, textvariable=search_var).pack(fill="x", pady=(4, 4))
        search_var.trace_add("write", lambda *_: self._apply_filter(search_var.get()))

        self._delete_button = list_buttons(
            left, "New track…", self._add_new_track, self._delete_track,
            "Removes this stream from the built disc. Front-end menu tracks are protected; "
            "remaining BGM cues and hardcoded executable references are shown first.",
        )
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

        cue_row = ttk.Frame(right)
        cue_row.pack(fill="x", pady=(4, 8))
        tip(ttk.Label(cue_row, text="Music cues:"), "The BGM_ names that play this track. Name one as a "
            "chapter's map music or in a script's BGMPlay.").pack(side="left")
        self._cue_label = ttk.Label(cue_row, text="", style="Muted.TLabel", wraplength=360)
        self._cue_label.pack(side="left", padx=(6, 0))
        self._new_cue_button = ttk.Button(cue_row, text="New cue…", command=self._new_cue, state="disabled")
        self._new_cue_button.pack(side="left", padx=(8, 0))
        self._repoint_button = ttk.Button(cue_row, text="Repoint cue…", command=self._repoint_cue,
                                          state="disabled")
        self._repoint_button.pack(side="left", padx=(6, 0))
        self._remove_cue_button = ttk.Button(cue_row, text="Remove cue", command=self._remove_cue, state="disabled")
        self._remove_cue_button.pack(side="left", padx=(6, 0))

        self._progress = ttk.Progressbar(right, mode="indeterminate")
        self._status_label = ttk.Label(right, text="", style="Muted.TLabel", wraplength=480)
        self._status_label.pack(anchor="w", fill="x", pady=(8, 0))

        tip(self._import_button, "Accepts WAV, MP3, OGG, FLAC and other common formats, converted with FFmpeg. "
                                 "Mono or stereo only.")

    # -- data loading ---------------------------------------------------------
    def _load_track_list(self) -> None:
        sound_dir = self._project.extracted_dir / "files" / "Sound"
        folder = sound_dir / "strm" if self._fe10 else sound_dir
        pattern = "*.brstm" if self._fe10 else "*.stm"
        files = sorted(folder.glob(pattern)) if folder.exists() else []
        # RD's stream folder also holds hundreds of voiced lines.  Music is
        # identified by the retail BGM naming convention; cue joins below
        # retain the symbolic BGM names shown to users.
        if self._fe10:
            streams = self._rd_sound_map()
            referenced = {Path(streams.get(cue.resource, "")).name.casefold()
                          for cue in self._rd_cues() if cue.name.startswith("BGM_")}
            self._all_files = [path for path in files if path.name.casefold() in referenced]
        else:
            self._all_files = files
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

    def select_cue(self, cue_name: str) -> bool:
        """Open the Sound/*.stm file named by a BGM cue in gcfesnd.bin."""
        if self._fe10:
            try:
                cue = next(item for item in self._rd_cues() if item.name == cue_name)
            except (OSError, ValueError, StopIteration):
                return False
            external = self._rd_sound_map().get(cue.resource)
            path = next((item for item in self._all_files
                         if external and item.name.casefold() == Path(external).name.casefold()), None)
            if path is None:
                return False
            self._apply_filter("")
            index = self._filtered_files.index(path)
            self._file_list.selection_set(index)
            self._file_list.activate(index)
            self._file_list.see(index)
            self._on_file_selected()
            return True
        catalog = self._project.extracted_dir / "files" / "Sound" / "gcfesnd.bin"
        try:
            cue = gcfesnd.find_cue(gcfesnd.read_bgm_cues_path(catalog), cue_name)
        except (OSError, gcfesnd.GcfesndError, ValueError):
            return False
        stem = cue.path.rsplit("/", 1)[-1].lower()
        self._apply_filter("")
        for index, path in enumerate(self._filtered_files):
            if path.stem.lower() == stem:
                self._file_list.selection_clear(0, "end")
                self._file_list.selection_set(index)
                self._file_list.activate(index)
                self._file_list.see(index)
                self._on_file_selected()
                return True
        return False

    def _on_file_selected(self) -> None:
        selection = self._file_list.curselection()
        if not selection:
            return
        self._stop()
        self._current_path = self._filtered_files[selection[0]]
        self._delete_button.config(state="normal")
        self._track_label.config(text=self._current_path.stem)
        self._info_label.config(text="Loading...")
        self._play_button.config(state="disabled")
        self._export_button.config(state="disabled")
        self._import_button.config(state="disabled")

        self._run_task(
            f"Decoding {self._current_path.name} ...",
            lambda: brstm.read_brstm_path(self._current_path) if self._fe10 else stm.read_stm_path(self._current_path),
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
        self._show_cues()

    # -- music cues ------------------------------------------------------------
    def _catalog(self) -> Path:
        name = "sound_data_en.cms" if self._fe10 else "gcfesnd.bin"
        return self._project.extracted_dir / "files" / "Sound" / name

    @staticmethod
    def _rd_key(value: str) -> str:
        value = Path(value).stem.casefold().removeprefix("strm_").removeprefix("fe10_")
        value = value.removesuffix("_32k").replace("dark_knight", "dknight").replace("dheginhansea", "dhegin")
        return "".join(character for character in value if character.isalnum())

    def _rd_cues(self):
        return fe10_sound.read_sound_data(lz10.decompress(self._catalog().read_bytes()))

    def _rd_sound_map(self) -> dict[str, str]:
        if self._rd_streams is None:
            path = self._project.extracted_dir / "files" / "Sound" / "sound_us.brsar"
            archive = brsar.read_brsar(path.read_bytes())
            self._rd_streams = {sound.name: sound.external_path for sound in archive.sounds
                                if sound.external_path}
        return self._rd_streams

    def _cues_of(self, path: Path) -> list[gcfesnd.BgmCue]:
        if self._fe10:
            streams = self._rd_sound_map()
            return [cue for cue in self._rd_cues()
                    if cue.name.startswith("BGM_") and streams.get(cue.resource, "").casefold().endswith(
                        "/" + path.name.casefold())]
        try:
            cues = gcfesnd.read_bgm_cues_path(self._catalog())
        except (OSError, gcfesnd.GcfesndError, ValueError):
            return []
        return [c for c in cues if c.path.rsplit("/", 1)[-1].lower() == path.stem.lower()]

    def _added_cues(self, cues: list[gcfesnd.BgmCue]) -> list[gcfesnd.BgmCue]:
        if self._fe10:
            return []
        original = self._project.extracted_bytes(self._catalog())
        try:
            retail = {c.name for c in gcfesnd.read_bgm_cues(original)} if original else set()
        except (gcfesnd.GcfesndError, ValueError):
            retail = set()
        return [c for c in cues if c.name not in retail]

    def _show_cues(self) -> None:
        if self._current_path is None:
            return
        cues = self._cues_of(self._current_path)
        self._cue_label.config(text=", ".join(c.name for c in cues) or "none: the game cannot play this track yet")
        self._new_cue_button.config(state="disabled" if self._fe10 else
                                    ("normal" if self._catalog().is_file() else "disabled"))
        self._repoint_button.config(state="normal" if self._fe10 and self._rd_resources_for(self._current_path)
                                    else "disabled")
        self._remove_cue_button.config(state="normal" if self._added_cues(cues) else "disabled")
        native = sorted(c.name for c in cues if c.name in self._native_bgm_cues)
        if native:
            protected = front_end_track_cues(set(native))
            suffix = " Front-end menu music: it may be replaced, but not deleted." if protected else ""
            self._status_label.config(text=f"Hardcoded in main.dol: {', '.join(native)}.{suffix}")

    def _add_cue(self, path: Path, name: str) -> bool:
        if self._fe10:
            messagebox.showinfo("New music cue", "Adding new Radiant Dawn BRSAR resources is not enabled yet. "
                                "Existing cues can be repointed through decoded sound data.", parent=self)
            return False
        try:
            data = self._catalog().read_bytes()
            data = gcfesnd.add_bgm_cue(data, name, f"sound/{path.stem}")
            self._project.write_keeping_original(self._catalog(), data)
        except (OSError, gcfesnd.GcfesndError, ValueError) as exc:
            messagebox.showerror("Could not add the music cue", str(exc), parent=self)
            return False
        self._changelog.append(name, f"Added music cue for {path.name}")
        return True

    def _rd_resources_for(self, path: Path) -> list[str]:
        if not self._fe10:
            return []
        streams = self._rd_sound_map()
        return list(dict.fromkeys(cue.resource for cue in self._rd_cues()
                                  if streams.get(cue.resource, "").casefold().endswith(
                                      "/" + path.name.casefold())))

    def _repoint_cue(self) -> None:
        if not self._fe10 or self._current_path is None:
            return
        targets = self._rd_resources_for(self._current_path)
        if not targets:
            messagebox.showinfo("Repoint music cue", "This stream has no matching registered STRM resource.",
                                parent=self)
            return
        cues = [cue for cue in self._rd_cues() if cue.name.startswith("BGM_")]
        initial = self._cues_of(self._current_path)
        name = simpledialog.askstring("Repoint music cue", "Existing BGM_ cue name:",
                                      initialvalue=initial[0].name if initial else "BGM_", parent=self)
        if not name:
            return
        name = name.strip().upper()
        if name not in {cue.name for cue in cues}:
            messagebox.showerror("Repoint music cue", f"{name} is not an existing BGM cue.", parent=self)
            return
        resource = targets[0]
        try:
            data = lz10.decompress(self._catalog().read_bytes())
            changed = fe10_sound.repoint_cue(data, name, resource)
            self._project.write_logical("sound_data", changed)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Repoint music cue", str(exc), parent=self)
            return
        self._changelog.append(name, f"Repointed music cue to {resource}")
        self._status_label.config(text=f"{name} now plays {self._current_path.name}.")
        self._show_cues()

    def _new_cue(self) -> None:
        if self._current_path is None:
            return
        name = simpledialog.askstring("New music cue", "Cue name (BGM_ and capitals):",
                                      initialvalue=_cue_name_for(self._current_path), parent=self)
        if name and self._add_cue(self._current_path, name.strip()):
            self._show_cues()

    def _remove_cue(self) -> None:
        if self._current_path is None:
            return
        added = self._added_cues(self._cues_of(self._current_path))
        if not added:
            return
        cue = added[-1]
        if not messagebox.askyesno("Remove cue", f"Remove {cue.name}? Chapters and scripts naming it will play "
                                   "nothing.", parent=self):
            return
        try:
            data = gcfesnd.remove_bgm_cue(self._catalog().read_bytes(), cue.name)
            self._project.write_keeping_original(self._catalog(), data)
        except (OSError, gcfesnd.GcfesndError, ValueError) as exc:
            messagebox.showerror("Could not remove the cue", str(exc), parent=self)
            return
        self._changelog.append(cue.name, "Removed music cue")
        self._show_cues()

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
            (brstm.brstm_to_wav_path if self._fe10 else stm.stm_to_wav_path)(self._current_audio, chosen)
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
        if self._fe10:
            messagebox.showinfo("New track", "Adding a new Radiant Dawn track also requires a new BRSAR stream "
                                "entry and is not enabled yet. Replace an existing track instead.", parent=self)
            return
        sound_dir = self._project.extracted_dir / "files" / "Sound"
        if not sound_dir.exists():
            messagebox.showerror("No Sound folder", "Extract the project first.", parent=self)
            return

        name = simpledialog.askstring(
            "New track name",
            "File name (no extension; lowercase letters, digits and _), e.g. my_theme_32k:",
            parent=self,
        )
        if not name:
            return
        name = name.strip().lower()
        if not name or not all(c.isascii() and (c.isalnum() or c == "_") for c in name):
            messagebox.showerror("Invalid name", "Use lowercase letters, digits and _ only.", parent=self)
            return

        dest = sound_dir / f"{name}.stm"
        if dest.exists():
            messagebox.showerror("Already exists", f"{dest.name} already exists.", parent=self)
            return

        new_audio = self._prompt_for_audio(should_ask_loop=True, already_loops=False)
        if new_audio is None:
            return
        self._confirm_and_encode(new_audio, dest, verb="create", on_success=lambda audio: self._on_new_track_added(dest, audio))

    def _delete_track(self) -> None:
        path = self._current_path
        if path is None:
            return
        if self._fe10:
            messagebox.showinfo("Remove track", "Retail Radiant Dawn streams cannot be removed until BRSAR "
                                "resource rebuilding is enabled. Replace the stream instead.", parent=self)
            return
        catalog = path.parent / "gcfesnd.bin"
        try:
            users = [c.name for c in gcfesnd.read_bgm_cues_path(catalog)
                     if c.path.rsplit("/", 1)[-1].lower() == path.stem.lower()]
        except (OSError, gcfesnd.GcfesndError, ValueError):
            users = []
        protected = front_end_track_cues(set(users))
        reason = (f"It is used by the front-end menu through the hardcoded cue(s) {', '.join(protected)}. "
                  "Replace it instead." if protected else "")
        annotated_users = [f"{name} (hardcoded in main.dol)" if name in self._native_bgm_cues else name
                           for name in users]
        if not confirm_delete_added(self, self._project, path, "track", annotated_users,
                                    allow_retail=True, protected_reason=reason):
            return
        self._stop()
        added = self._added_cues(self._cues_of(path))
        if added:
            try:
                data = self._catalog().read_bytes()
                for cue in added:
                    data = gcfesnd.remove_bgm_cue(data, cue.name)
                self._project.write_keeping_original(self._catalog(), data)
            except (OSError, gcfesnd.GcfesndError, ValueError) as exc:
                messagebox.showerror("Could not remove the track's cues", str(exc), parent=self)
                return
        path.unlink()
        self._changelog.append(path.stem, "Deleted track")
        self._current_path = None
        self._track_label.config(text="(no track selected)")
        self._info_label.config(text="")
        for button in (self._play_button, self._export_button, self._import_button, self._delete_button):
            button.config(state="disabled")
        self._load_track_list()

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
        self._changelog.append(dest.stem, "Added new track")
        cue = _cue_name_for(dest)
        if self._catalog().is_file() and not self._cues_of(dest) and self._add_cue(dest, cue):
            self._status_label.config(text=f"Added {dest.name}, played by the music cue {cue}: name it as a "
                                           "chapter's map music or in a script's BGMPlay.")
        else:
            self._status_label.config(text=f"Added {dest.name}.")
        self._show_cues()

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
            audio = (brstm.wav_path_to_brstm_audio if self._fe10 else stm.wav_path_to_stm_audio)(chosen)
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
            if self._fe10:
                if not dest_path.exists():
                    raise ValueError("A BRSTM template is required for a new stream")
                data = brstm.write_brstm(audio, dest_path.read_bytes())
            else:
                data = stm.write_stm(audio)
            self._project.write_keeping_original(dest_path, data)
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
