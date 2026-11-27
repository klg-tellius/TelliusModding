"""Wrappers around bundled third-party binaries. Everything here just shells
out to a tool and turns failures into ToolError - no format-specific logic
lives in this module.

**WIT** (tools/wit/win64/wit.exe) reads and writes GameCube/Wii disc images
(ISO, GCM, CISO, WBFS, WDF, WIA). It does every extract, and the Radiant
Dawn rebuild.

It can't rebuild Path of Radiance: WIT composes every extracted (FST)
directory as a *Wii* disc, even a GameCube one (that is also why plain .iso
output came out at the 4.7 GB Wii single-layer size). Dolphin boots such an
image in Wii mode and crashes at once. GameCube builds go through
fe_modding.formats.gcdisc instead - see ModProject.build().

**DolphinTool** (next to the configured Dolphin.exe) converts a ``.rvz`` image to an ISO, because
WIT cannot read RVZ; the temporary ISO is extracted by WIT and deleted.

**FFmpeg** (tools/ffmpeg/win64/ffmpeg.exe) decodes an arbitrary input video
(whatever container/codec) into a PNG frame sequence and a WAV audio track,
for the video importer (fe_modding.formats.thp / video_viewer.py) - the
one place this app needs to read a *general* video format rather than a
Fire Emblem-specific one. It never touches THP itself; the actual
THP-specific encoding is this project's own code.

It's also used to decode an arbitrary input *audio* file (MP3, OGG, FLAC,
...) into WAV for the music importer (fe_modding.gui.music_editor) - same
reasoning, stm.py only reads WAV, so anything else goes through here first.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from .exceptions import ModdingError
from .games import DOLPHIN_ONLY_FORMATS
from .runtime_tools import tool_directory

REPO_ROOT = Path(__file__).resolve().parent.parent
WIT_DIR = REPO_ROOT / "tools" / "wit" / "win64"
if not (WIT_DIR / "wit.exe").is_file():
    WIT_DIR = tool_directory("wit")
WIT_EXE = WIT_DIR / "wit.exe"
WIT_SETTING = "wit_exe"  # a wit.exe the user pointed at (the patcher's "Locate WIT" choice)
FFMPEG_DIR = REPO_ROOT / "tools" / "ffmpeg" / "win64"
if not (FFMPEG_DIR / "ffmpeg.exe").is_file():
    FFMPEG_DIR = tool_directory("ffmpeg")
FFMPEG_EXE = FFMPEG_DIR / "ffmpeg.exe"


DOLPHIN_TOOL_NAMES = ("DolphinTool.exe", "DolphinTool", "dolphin-tool")
GAMECUBE_LAYOUT = ("sys", "files")
WII_LAYOUT_EXTRA = ("disc", "ticket.bin", "tmd.bin", "cert.bin")


class ToolError(ModdingError):
    """Raised when the bundled WIT binary is missing or a command fails."""


def _program_dir() -> Path:
    """The folder of the running program (the .exe once frozen, where a mod author may put WIT)."""
    return Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0] or ".").resolve().parent


def wit_candidates() -> list[Path]:
    """Where WIT may already be, best first: the repository copy, the per-user install, next to the
    program (``wit.exe``, ``wit/`` or ``tools/wit/win64/``), the saved choice, then the PATH."""
    found = [REPO_ROOT / "tools" / "wit" / "win64" / "wit.exe", tool_directory("wit") / "wit.exe"]
    here = _program_dir()
    found += [here / "wit.exe", here / "wit" / "wit.exe", here / "tools" / "wit" / "win64" / "wit.exe"]
    try:
        from .config import load_setting
        saved = load_setting(WIT_SETTING)
    except Exception:  # noqa: BLE001 - an unreadable settings file must not hide an installed WIT
        saved = None
    if saved:
        found.append(Path(saved))
    hit = shutil.which("wit")
    if hit:
        found.append(Path(hit))
    return found


def find_wit() -> Optional[Path]:
    return next((path for path in wit_candidates() if path.is_file()), None)


def remember_wit(exe: Path | str) -> Path:
    """Use this wit.exe from now on (saved in the settings)."""
    exe = Path(exe)
    if exe.name.lower() not in ("wit.exe", "wit") or not exe.is_file():
        raise ToolError(f"{exe} is not wit.exe.")
    from .config import save_setting
    save_setting(WIT_SETTING, str(exe))
    return exe


def wit_path() -> Path:
    if sys.platform != "win32":
        raise ToolError(
            "The bundled WIT binary is Windows-only. Install Wiimm's ISO Tools "
            "for your platform and point WIT_EXE at it."
        )
    exe = find_wit()
    if exe is None:
        raise ToolError("WIT is not installed. Open Settings > Disc and media tools to download it.")
    return exe


def _run(args: list[str]) -> subprocess.CompletedProcess:
    exe = wit_path()
    result = subprocess.run(
        [str(exe), *args],
        capture_output=True,
        text=True,
        cwd=str(exe.parent),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ToolError(f"wit {args[0]} failed (exit {result.returncode}):\n{detail}")
    return result


DOLPHIN_TOOL_SETTING = "dolphin_tool_path"  # a DolphinTool the user pointed at (Tellius Patcher asks)


class DolphinToolMissing(ToolError):
    """A .rvz disc needs DolphinTool and none was found; the patcher then asks where it is."""


def _saved(key: str) -> Optional[str]:
    try:
        from .config import load_setting
        return load_setting(key)
    except Exception:  # noqa: BLE001 - an unreadable settings file must not hide an installed tool
        return None


def dolphin_tool_candidates(dolphin: Optional[Path | str] = None) -> list[Path]:
    """Where DolphinTool may be, best first: the saved choice, next to the configured (or found)
    Dolphin, next to this program, in the usual Dolphin install folders, then the PATH."""
    from .emulator import candidate_paths, configured_dolphin
    folders = []
    saved = _saved(DOLPHIN_TOOL_SETTING)
    found = [Path(saved)] if saved else []
    if dolphin is None:
        dolphin = configured_dolphin()
    if dolphin:
        folders.append(Path(dolphin).parent)
    folders.append(_program_dir())
    folders += [path.parent for path in candidate_paths()]
    found += [folder / name for folder in folders for name in DOLPHIN_TOOL_NAMES]
    for name in DOLPHIN_TOOL_NAMES:
        hit = shutil.which(name)
        if hit:
            found.append(Path(hit))
    return found


def find_dolphin_tool(dolphin: Optional[Path | str] = None) -> Optional[Path]:
    return next((path for path in dolphin_tool_candidates(dolphin) if path.is_file()), None)


def remember_dolphin_tool(chosen: Path | str) -> Path:
    """Use this DolphinTool from now on. ``chosen`` may be DolphinTool itself, Dolphin.exe or the
    Dolphin folder: Dolphin's release ships DolphinTool beside Dolphin.exe."""
    chosen = Path(chosen)
    folder = chosen if chosen.is_dir() else chosen.parent
    candidates = [chosen] if chosen.is_file() and chosen.name in DOLPHIN_TOOL_NAMES else []
    candidates += [folder / name for name in DOLPHIN_TOOL_NAMES]
    exe = next((path for path in candidates if path.is_file()), None)
    if exe is None:
        raise ToolError(f"DolphinTool was not found in {folder}. Choose the folder where Dolphin is installed "
                        "(Dolphin's download has DolphinTool.exe next to Dolphin.exe).")
    from .config import save_setting
    save_setting(DOLPHIN_TOOL_SETTING, str(exe))
    return exe


def dolphin_tool_path(dolphin: Optional[Path | str] = None) -> Path:
    """``DolphinTool``, which converts ``.rvz`` discs (see :func:`dolphin_tool_candidates`)."""
    exe = find_dolphin_tool(dolphin)
    if exe is None:
        raise DolphinToolMissing(
            ".rvz discs are converted with DolphinTool, which ships with Dolphin, and it was not found. "
            "Set the Dolphin path in Settings (or, in Tellius Patcher, choose the Dolphin folder when asked), "
            "or use a .iso/.wbfs/.ciso dump.")
    return exe


def convert_to_iso(source: Path, dest_iso: Path) -> None:
    """Convert a Dolphin-only disc image (.rvz) to a plain ISO with DolphinTool."""
    exe = dolphin_tool_path()
    result = subprocess.run(
        [str(exe), "convert", "-i", str(source), "-o", str(dest_iso), "-f", "iso"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ToolError(f"DolphinTool convert failed (exit {result.returncode}):\n{detail}")
    if not Path(dest_iso).is_file():
        raise ToolError(f"DolphinTool reported success but wrote no ISO for {source}.")


def check_extracted_layout(dest_dir: Path, *, wii: bool) -> None:
    """Raise ToolError unless ``dest_dir`` holds a complete extracted disc: ``sys/`` and ``files/``
    plus, for a Wii disc, ``disc/``, ``ticket.bin``, ``tmd.bin`` and ``cert.bin`` (what WIT needs to
    compose the disc again)."""
    dest_dir = Path(dest_dir)
    required = list(GAMECUBE_LAYOUT) + (list(WII_LAYOUT_EXTRA) if wii else [])
    missing = [name for name in required if not (dest_dir / name).exists()]
    if missing:
        raise ToolError(
            f"The extracted disc is incomplete - missing {', '.join(missing)}. "
            "Was the right partition extracted?"
        )


def _wit_form_to_name(name: str) -> Optional[str]:
    """The real name of a file WIT extracted from a Shift-JIS disc name, or None when ``name`` is not one.

    WIT on Windows writes each byte of a disc name as one character (``82 86`` becomes ``\\x82\\x86``),
    so Radiant Dawn's ``ymu/knight1_sp_ｆ`` is extracted as ``knight1_sp_\\x82\\x86``. Dolphin, which
    looks the file up by its decoded name, then can't open it and 4-P's opening crashes."""
    if not any(0x80 <= ord(c) <= 0xFF for c in name) or any(ord(c) > 0xFF for c in name):
        return None
    try:
        real = name.encode("latin-1").decode("shift_jis")
    except UnicodeDecodeError:
        return None
    return real if real != name else None


def _name_to_wit_form(name: str) -> Optional[str]:
    """The byte-per-character form WIT reads back as these Shift-JIS bytes (a real ``ｆ`` it turns into
    ``F``), or None for a plain ASCII name."""
    if name.isascii():
        return None
    try:
        return name.encode("shift_jis").decode("latin-1")
    except UnicodeEncodeError:
        return None


def _rename_tree(root: Path, rename) -> list[tuple[Path, Path]]:
    """Rename every entry under ``root`` whose name ``rename`` maps, deepest first; the renames made."""
    done = []
    if not root.is_dir():
        return done
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        new = rename(path.name)
        if new is not None and not (path.parent / new).exists():
            path.rename(path.parent / new)
            done.append((path.parent / new, path))
    return done


def fix_extracted_names(dest_dir: Path) -> list[str]:
    """Give the files WIT extracted under byte-per-character names their real Shift-JIS names (four on the
    US Radiant Dawn disc); the names fixed. Safe to run again. :func:`build_disc` turns them back for WIT."""
    return [str(new.relative_to(dest_dir)) for new, _old in _rename_tree(Path(dest_dir) / "files", _wit_form_to_name)]


def extract_disc(source: Path, dest_dir: Path, *, overwrite: bool = False, wii: bool = False) -> None:
    """Extract every file of a disc image into dest_dir (flat, no ID subfolder).

    ``wii`` marks a Wii disc: its DATA partition is selected explicitly and the extracted layout
    is checked. A ``.rvz`` image is first converted to a temporary ISO beside ``dest_dir``."""
    source = Path(source)
    dest_dir = Path(dest_dir)
    if not source.exists():
        raise ToolError(f"Source disc image not found: {source}")

    if source.suffix.lower() in DOLPHIN_ONLY_FORMATS:
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".rvz_", dir=dest_dir.parent) as temp:
            iso = Path(temp) / (source.stem + ".iso")
            convert_to_iso(source, iso)
            extract_disc(iso, dest_dir, overwrite=overwrite, wii=wii)
        return

    args = ["EXTRACT", "--pmode", "NONE"]
    if wii:
        args += ["--psel", "DATA"]
    args += [str(source), str(dest_dir)]
    if overwrite:
        args.append("-o")
    _run(args)
    check_extracted_layout(dest_dir, wii=wii)
    fix_extracted_names(dest_dir)


def build_disc(source_dir: Path, dest_file: Path, *, overwrite: bool = False) -> None:
    """Rebuild a disc image from a previously extracted directory."""
    source_dir = Path(source_dir)
    if not source_dir.exists() or not any(source_dir.iterdir()):
        raise ToolError(f"Nothing to build from - '{source_dir}' is empty or missing. Extract first.")

    dest_file.parent.mkdir(parents=True, exist_ok=True)
    args = ["COPY", str(source_dir), str(dest_file)]
    if overwrite:
        args.append("-o")
    # WIT writes a name's characters back as bytes: give it the byte-per-character form of the
    # Shift-JIS names for the build, then put the real names back
    renamed = _rename_tree(source_dir / "files", _name_to_wit_form)
    try:
        _run(args)
    finally:
        for new, old in reversed(renamed):
            new.rename(old)


def ffmpeg_path() -> Path:
    if sys.platform != "win32":
        raise ToolError(
            "The bundled FFmpeg binary is Windows-only. Install FFmpeg for your "
            "platform and point FFMPEG_EXE at it."
        )
    if not FFMPEG_EXE.exists():
        raise ToolError("FFmpeg is not installed. Open Settings > Disc and media tools to download it.")
    return FFMPEG_EXE


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    exe = ffmpeg_path()
    result = subprocess.run(
        [str(exe), "-y", "-hide_banner", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ToolError(f"ffmpeg failed (exit {result.returncode}):\n{result.stderr.strip()}")
    return result


def decode_video_to_frames(source: Path, dest_dir: Path, *, width: int, height: int, fps: float) -> list[Path]:
    """Decode any video file ffmpeg can read into a numbered PNG sequence,
    scaled/padded to exactly width x height and resampled to fps. Returns
    the frame paths in order."""
    source = Path(source)
    if not source.exists():
        raise ToolError(f"Source video not found: {source}")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    _run_ffmpeg(["-i", str(source), "-vf", scale_filter, "-r", f"{fps}", str(dest_dir / "frame%06d.png")])

    frames = sorted(dest_dir.glob("frame*.png"))
    if not frames:
        raise ToolError(f"FFmpeg produced no frames from {source}.")
    return frames


def decode_video_to_wav(source: Path, dest_wav: Path, *, sample_rate: int, channels: int) -> bool:
    """Decode a video's audio track to 16-bit PCM WAV. Returns False (and
    leaves nothing written) if the source has no audio track, rather than
    raising - a silent input video is valid, just less common."""
    source = Path(source)
    dest_wav = Path(dest_wav)
    try:
        _run_ffmpeg(
            [
                "-i", str(source),
                "-vn",
                "-ar", str(sample_rate),
                "-ac", str(channels),
                "-sample_fmt", "s16",
                str(dest_wav),
            ]
        )
    except ToolError as exc:
        if "Output file does not contain any stream" in str(exc) or "does not contain any stream" in str(exc):
            return False
        raise
    return dest_wav.exists()


def decode_audio_to_wav(source: Path, dest_wav: Path) -> None:
    """Decode any audio file ffmpeg can read (MP3, OGG, FLAC, M4A, ...)
    into 16-bit PCM WAV. Sample rate and channel count are left as the
    source has them - stm.wav_path_to_stm_audio() already validates those
    against what the STM format supports (mono/stereo, any sample rate)."""
    source = Path(source)
    dest_wav = Path(dest_wav)
    if not source.exists():
        raise ToolError(f"Source audio not found: {source}")
    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(["-i", str(source), "-vn", "-sample_fmt", "s16", str(dest_wav)])
