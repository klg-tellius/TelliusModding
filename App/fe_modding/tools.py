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

import subprocess
import sys
from pathlib import Path

from .exceptions import ModdingError
from .runtime_tools import tool_directory

REPO_ROOT = Path(__file__).resolve().parent.parent
WIT_DIR = REPO_ROOT / "tools" / "wit" / "win64"
if not (WIT_DIR / "wit.exe").is_file():
    WIT_DIR = tool_directory("wit")
WIT_EXE = WIT_DIR / "wit.exe"
FFMPEG_DIR = REPO_ROOT / "tools" / "ffmpeg" / "win64"
if not (FFMPEG_DIR / "ffmpeg.exe").is_file():
    FFMPEG_DIR = tool_directory("ffmpeg")
FFMPEG_EXE = FFMPEG_DIR / "ffmpeg.exe"


class ToolError(ModdingError):
    """Raised when the bundled WIT binary is missing or a command fails."""


def wit_path() -> Path:
    if sys.platform != "win32":
        raise ToolError(
            "The bundled WIT binary is Windows-only. Install Wiimm's ISO Tools "
            "for your platform and point WIT_EXE at it."
        )
    if not WIT_EXE.exists():
        raise ToolError("WIT is not installed. Open Settings > Disc and media tools to download it.")
    return WIT_EXE


def _run(args: list[str]) -> subprocess.CompletedProcess:
    exe = wit_path()
    result = subprocess.run(
        [str(exe), *args],
        capture_output=True,
        text=True,
        cwd=str(WIT_DIR),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ToolError(f"wit {args[0]} failed (exit {result.returncode}):\n{detail}")
    return result


def extract_disc(source: Path, dest_dir: Path, *, overwrite: bool = False) -> None:
    """Extract every file of a disc image into dest_dir (flat, no ID subfolder)."""
    source = Path(source)
    if not source.exists():
        raise ToolError(f"Source disc image not found: {source}")

    args = ["EXTRACT", "--pmode", "NONE", str(source), str(dest_dir)]
    if overwrite:
        args.append("-o")
    _run(args)


def build_disc(source_dir: Path, dest_file: Path, *, overwrite: bool = False) -> None:
    """Rebuild a disc image from a previously extracted directory."""
    source_dir = Path(source_dir)
    if not source_dir.exists() or not any(source_dir.iterdir()):
        raise ToolError(f"Nothing to build from - '{source_dir}' is empty or missing. Extract first.")

    dest_file.parent.mkdir(parents=True, exist_ok=True)
    args = ["COPY", str(source_dir), str(dest_file)]
    if overwrite:
        args.append("-o")
    _run(args)


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
