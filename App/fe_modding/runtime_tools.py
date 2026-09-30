"""Verified, per-user downloads of external tools (never bundled game data)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import urllib.request
import zipfile

TOOLS = {
    "wit": {
        "version": "3.05a-r8638",
        "url": "https://wit.wiimm.de/download/wit-v3.05a-r8638-cygwin64.zip",
        "sha256": "049670558970f0cea2796d68e0ba1e48491474b5708bf12a95ab8a185f4e59c1",
        "exe": "wit.exe",
        "max_bytes": 25_000_000,
    },
    "ffmpeg": {
        "version": "8.1.2",
        "url": "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip",
        "sha256": "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec",
        "exe": "ffmpeg.exe",
        "max_bytes": 150_000_000,
    },
}


def install_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "TelliusModding" / "tools"


def tool_directory(name: str, root: Path | None = None) -> Path:
    return (root if root is not None else install_root()) / f"{name}-{TOOLS[name]['version']}"


def unpack_tool(name: str, archive: Path, destination: Path) -> None:
    """Check the pinned hash, extract into staging, then publish atomically."""
    spec = TOOLS[name]
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != spec["sha256"]:
        raise ValueError(f"{name}: download checksum does not match; nothing was installed.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".install-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "tool"
        stage.mkdir()
        with zipfile.ZipFile(archive) as package:
            members = package.infolist()
            if sum(item.file_size for item in members) > 750_000_000:
                raise ValueError("Tool archive exceeds the unpacked size limit.")
            seen = set()
            for item in members:
                path = PurePosixPath(item.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts or any(":" in part for part in path.parts):
                    raise ValueError("Unsafe path in tool archive.")
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Links are not allowed in tool archives.")
                if item.is_dir():
                    continue
                # Keep the tool and its adjacent DLLs, plus upstream notices.
                is_binary = path.name.lower() == spec["exe"] or path.suffix.lower() == ".dll"
                is_notice = path.suffix.lower() in {".txt", ".md"} or path.name.lower().startswith(("license", "copying", "copyright"))
                if not (is_binary or is_notice):
                    continue
                relative = Path(path.name) if is_binary else Path("upstream") / Path(*path.parts)
                key = relative.as_posix().casefold()
                if key in seen:
                    raise ValueError("Duplicate destination in tool archive.")
                seen.add(key)
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(item) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        if not (stage / spec["exe"]).is_file():
            raise ValueError(f"The archive does not contain {spec['exe']}.")
        if destination.exists():
            raise FileExistsError(f"Tool directory already exists: {destination}")
        stage.replace(destination)


def install_tool(name: str, progress=lambda message: None, *, root: Path | None = None) -> Path:
    spec = TOOLS[name]
    destination = tool_directory(name, root)
    exe = destination / spec["exe"]
    if exe.is_file():
        return exe
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".download-", dir=destination.parent) as temporary:
        archive = Path(temporary) / "tool.zip"
        request = urllib.request.Request(spec["url"], headers={"User-Agent": "TelliusModding-tool-setup"})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
            received = 0
            while block := response.read(1024 * 1024):
                received += len(block)
                if received > spec["max_bytes"]:
                    raise ValueError("Tool download exceeds its size limit.")
                output.write(block)
                progress(f"Downloading {name}: {received // (1024 * 1024)} MB")
        progress(f"Verifying and installing {name}...")
        unpack_tool(name, archive, destination)
    return exe
