"""Drive one Dolphin run of a check: boot the run tree, get through the title, events and menus with the
chapter-sweep policy, and stop where the check wants to look.

Adds to the chapter sweep's driver: a seeded save (PoR GCI folder, RD NAND), Dolphin's log file with
memory errors (invalid reads and writes are logged instead of shown as a blocking alert), and
:meth:`Driver.until`, which plays until a condition holds.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from tools import dolphin_input as di
from tools.chapter_sweep.drive import BUILDS, DOLPHIN, State, Sweep
from tools.dolphin_ram import DolphinRam

INVALID = re.compile(r"Invalid (read|write)[^\n]*", re.I)


class Timeout(RuntimeError):
    pass


class Driver(Sweep):
    def __init__(self, run: Path, out: Path, region: str):
        build = BUILDS["GFEE01" if region.startswith("G") else "RFEE01"]
        if region not in ("GFEE01", "RFEE01"):
            from dataclasses import replace
            build = replace(build, game_id=region)
        super().__init__(run, out, out / "user", build)

    @property
    def card(self) -> Path:
        return self.out / "card" if not self.build.wii else self.user / self.build.save_folder

    def boot(self) -> None:
        for folder in (self.user, self.out / "card"):
            if folder.exists():
                shutil.rmtree(folder)
        di.configure(self.user)
        config = self.user / "Config"
        logger = ("[Logs]\nMI = True\nMEMMAP = True\nOSREPORT = True\nPOWERPC = True\n"
                  "[Options]\nVerbosity = 3\nWriteToFile = True\nWriteToConsole = False\nWriteToWindow = False\n")
        (config / "Logger.ini").write_text(logger, encoding="utf-8")
        self.card.mkdir(parents=True, exist_ok=True)
        for path in (self.run / "card").glob("*"):
            shutil.copy2(path, self.card / path.name)
            self.saves[path.name] = (self.card / path.name).stat().st_size, (self.card / path.name).stat().st_mtime_ns
        args = [str(DOLPHIN), "--user", str(self.user), "--batch", "--exec", str(self.run / "sys" / "main.dol"),
                "--config=Dolphin.DSP.Volume=0", "--config=Dolphin.Interface.ConfirmStop=False",
                "--config=Dolphin.Interface.UsePanicHandlers=False",
                "--config=Dolphin.Core.EnableCheats=False",
                "--config=Dolphin.Analytics.Enabled=False", "--config=Dolphin.Analytics.PermissionAsked=True"]
        if not self.build.wii:
            args += ["--config=Dolphin.Core.SlotA=8", f"--config=Dolphin.Core.GCIFolderAPathOverride={self.card}",
                     "--config=Dolphin.Core.SlotB=0"]
        proc = subprocess.Popen(args, creationflags=0x00000008)
        self.pid = proc.pid
        di.STATE.write_text(json.dumps({"pid": self.pid, "user": str(self.user)}))
        for _ in range(120):
            time.sleep(0.5)
            self.ram = DolphinRam.attach(self.pid)
            if self.ram is not None and self.ram.game_id() == self.build.game_id:
                break
        else:
            raise RuntimeError("Dolphin did not start the game")
        self.log(f"booted {self.build.game_id} pid {self.pid}")

    # -- observation -----------------------------------------------------------------------------
    def log_text(self) -> str:
        path = self.user / "Logs" / "dolphin.log"
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""

    def invalid_accesses(self) -> list[str]:
        return sorted(set(m.group(0).strip() for m in INVALID.finditer(self.log_text())))

    def snap(self, name: str) -> Optional[Path]:
        folder = self.out / "shots"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}.png"
        try:
            di.grab(self.pid, str(path))
        except (OSError, ValueError):
            return None
        return path if path.is_file() else None

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    # -- control -------------------------------------------------------------------------------------
    def until(self, done: Callable[[State], bool], minutes: float = 5.0, policy: bool = True,
              label: str = "") -> State:
        """Play (with the sweep policy when ``policy``) until ``done(state)``; raise :class:`Timeout`."""
        deadline = time.time() + minutes * 60
        while time.time() < deadline:
            st = self.state()
            key = st.key()
            if key != self.last_key:
                self.last_key, self.since = key, time.time()
                self.log(key)
            self.collect_saves(st)
            if done(st):
                return st
            if policy:
                if time.time() - self.since > 90:
                    self.log("STUCK for 90 s; pressing B, A")
                    self.press("B", "A")
                    self.since = time.time()
                self.step(st)
            time.sleep(0.25)
        self.snap(f"timeout_{label or 'until'}")
        raise Timeout(f"{label or 'condition'} not reached in {minutes} min (last: {self.last_key})")

    def player_phase(self, st: State, idle: float) -> None:   # the sweep ends turns; a check stops instead
        if getattr(self, "end_turns", False):
            super().player_phase(st, idle)

    def to_player_phase(self, minutes: float = 6.0) -> State:
        """Play to the first player phase on the map, with no menu open."""
        return self.until(lambda s: "E_BMapPlph" in s.names and not s.names & {"E_Menu", "E_Talk", "E_Event"}
                          and time.time() - self.since > 2.0, minutes, label="player phase")

    def start_session(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        self.log_file = open(self.out / "log.txt", "w", encoding="utf-8")
        self.start = self.since = time.time()
        self.boot()

    def close(self) -> None:
        try:
            if self.pid:
                self.stop()
        finally:
            if self.log_file:
                self.log_file.close()
