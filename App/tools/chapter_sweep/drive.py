"""Play a chapter-sweep run tree from New Game to the end, keeping every save the game writes.

    python -m tools.chapter_sweep.drive --run G:/ROM/tellius_test/sweep_run_por
        --out G:/ROM/tellius_test/sweep_out_por [--minutes 600]

Set ``TELLIUS_DOLPHIN`` to Dolphin.exe (default ``G:\\Dolphin-x64\\Dolphin.exe``). Needs a tree from
``tools.chapter_sweep.build``. Keys are sent with SendInput (``tools/dolphin_input``) to a Dolphin with
background input, so the PC is usable but keyboard keys the driver uses must not be pressed;
only one Dolphin may run. ``--out`` gets ``saves/`` (one copy each time the game writes its save,
named after the chapter it holds), ``shots/`` (a screenshot of every new screen) and ``log.txt``.
Creating ``<out>/STOP`` stops the driver and leaves Dolphin open (to look at a screen by hand).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "tools.chapter_sweep"

from tools import dolphin_input as di  # noqa: E402
from tools.dolphin_ram import PROCESS_POOLS, DolphinRam  # noqa: E402

DOLPHIN = Path(os.environ.get("TELLIUS_DOLPHIN", r"G:\Dolphin-x64\Dolphin.exe"))


@dataclass(frozen=True)
class Build:
    """One US build. ``party`` is ``party_data`` (both games: +0x10 chapter, +0x11 phase = army id,
    +0x12 turn, u16)."""
    game_id: str
    party: int
    save_folder: str               # where the game's save file is, under the Dolphin user folder
    save_glob: str
    difficulty: tuple = ()         # (offset in party_data, value) checked once the first map runs

    @property
    def process_pool(self) -> tuple:
        return PROCESS_POOLS[self.game_id]

    @property
    def wii(self) -> bool:
        return self.game_id.startswith("R")


#: PoR: party+0xA6 = 1 is Difficult (the menu's third choice; Easy and Normal show tutorials).
#: Radiant Dawn: Normal (Hard is locked on a new file); its save is the NAND file FE10_US.dat.
BUILDS = {"GFEE01": Build("GFEE01", 0x80330708, "card", "*.gci", (0xA6, 1)),
          "RFEE01": Build("RFEE01", 0x803CAB38, "Wii/title/00010000/52464545/data", "FE10_*.dat")}

#: Processes that are always there or only decorate the screen.
NOISE = {"E_Fade", "E_ForceFade", "E_Flash", "E_Wipe", "GameController", "FaceResMan", "E_BackLetter",
         "E_BackDraw", "AutoProc", "E_MapCloud", "E_BMapVisualize", "E_MapWeatherBridge", "E_MapWeather",
         "E_MapShader", "E_CtrlInfo", "E_UnitInfo", "E_TerInfo", "E_BMapBGMCtrl", "E_MuEffect", "E_FaceEyeCtrl"}
EVENT = {"E_Event", "E_Talk", "E_TalkWindow", "E_THPP", "E_MovieWait", "E_EventCaller"}
TITLE = {"E_OpeningLogo", "E_OpeningLogoWait", "E_Title", "TitleProc", "TitleMovieProc"}
#: File-menu processes that mean "busy, wait" (reading or writing the save).
BUSY = {"E_MCCreate", "E_MCWrite", "E_MCRead", "E_OpenSeq", "E_FileMenuWait", "Unknown", "E_LoadChapTex",
        "E_JoinSaveDataThread"}
MESSAGE = {"E_FileMenuMessWin", "E_SysMessWin"}     # a Yes/No or OK box over the file menu


@dataclass
class State:
    names: frozenset
    chapter: int
    phase: int
    turn: int

    def key(self) -> str:
        shown = sorted(n for n in self.names if n not in NOISE)
        return f"ch{self.chapter} ph{self.phase} t{self.turn} " + ",".join(shown)


@dataclass
class Sweep:
    run: Path
    out: Path
    user: Path
    build: Build
    log_file: object = None
    pid: int = 0
    ram: DolphinRam = None
    seen: set = field(default_factory=set)
    saves: dict = field(default_factory=dict)       # card file name -> (size, mtime) last copied
    save_count: int = 0
    difficulty_checked: bool = False
    last_key: str = ""
    since: float = 0.0
    start: float = 0.0
    last_press: float = 0.0
    keep_open: bool = False
    toggle: bool = False
    finale_seen: bool = False
    finished: bool = False

    @property
    def card(self) -> Path:
        """The folder holding the game's save: PoR's GCI folder (Slot A), RD's NAND title data."""
        return self.out / "card" if self.build.save_folder == "card" else self.user / self.build.save_folder

    # -- plumbing ---------------------------------------------------------------------------------
    def log(self, text: str) -> None:
        line = f"{time.time() - self.start:8.1f} {text}"
        print(line, flush=True)
        self.log_file.write(line + "\n")
        self.log_file.flush()

    def boot(self) -> None:
        di.configure(self.user)
        self.card.mkdir(parents=True, exist_ok=True)
        args = [str(DOLPHIN), "--user", str(self.user), "--batch", "--exec", str(self.run / "sys" / "main.dol"),
                "--config=Dolphin.DSP.Volume=0", "--config=Dolphin.Interface.ConfirmStop=False",
                "--config=Dolphin.Core.SlotA=8", f"--config=Dolphin.Core.GCIFolderAPathOverride={self.card}",
                "--config=Dolphin.Core.SlotB=0", "--config=Dolphin.Core.EnableCheats=False",
                "--config=Dolphin.Analytics.Enabled=False", "--config=Dolphin.Analytics.PermissionAsked=True"]
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

    def stop(self) -> None:
        subprocess.run(["taskkill", "/PID", str(self.pid)], capture_output=True)
        time.sleep(4)
        subprocess.run(["taskkill", "/F", "/PID", str(self.pid)], capture_output=True)

    def state(self) -> State:
        b = self.build
        names = frozenset(self.ram.processes(b.process_pool))
        party = self.ram.read(b.party + 0x10, 4)
        return State(names, party[0], party[1], int.from_bytes(party[2:4], "big"))

    def press(self, *buttons: str, gap: float = 0.35) -> None:
        for button in buttons:
            di.tap(di.BUTTONS[button][0], 0.08)
            time.sleep(gap)
        self.last_press = time.time()

    def shot(self, name: str) -> None:
        folder = self.out / "shots"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            di.grab(self.pid, str(folder / f"{int(time.time() - self.start):06d}_{name}.png"))
        except (OSError, ValueError) as error:   # an empty frame while a movie switches modes
            self.log(f"no screenshot: {error}")

    def collect_saves(self, st: State) -> None:
        for path in self.card.glob(self.build.save_glob):
            stamp = (path.stat().st_size, path.stat().st_mtime_ns)
            if self.saves.get(path.name) == stamp:
                continue
            time.sleep(1.0)             # let Dolphin finish writing
            stamp = (path.stat().st_size, path.stat().st_mtime_ns)
            target = self.out / "saves" / f"{self.save_count + 1:03d}_chapter{st.chapter:02d}_{path.name}"
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(path, target)
            except PermissionError:     # still open in Dolphin (the NAND file): next tick
                continue
            self.saves[path.name] = stamp
            self.save_count += 1
            self.log(f"SAVE {target.name}")

    # -- policy -----------------------------------------------------------------------------------
    def step(self, st: State) -> None:
        n, now = st.names, time.time()
        idle = now - self.since          # time the screen has not changed
        if "Finale" in n:
            self.finale_seen = True
        if self.finale_seen and n & TITLE:
            self.finished = True        # the ending is over (and its clear save written): back at the title
            return
        if n & TITLE:
            if now - self.last_press > 1.0:
                self.press("A")
            return
        if "E_FileMenu" in n and st.chapter == 0:
            self.new_game(st, idle)
            return
        if "E_FileMenu" in n:
            self.save_menu(st, idle)
            return
        if st.chapter and not self.difficulty_checked and "E_BMapMain" in n and self.build.difficulty:
            offset, wanted = self.build.difficulty
            difficulty = self.ram.u8(self.build.party + offset)
            self.log(f"difficulty byte {difficulty}")
            if difficulty != wanted:
                raise RuntimeError("New Game did not pick the hardest difficulty (tutorials would block the run)")
            self.difficulty_checked = True
        if "DivForceProc" in n:           # RD Part 4: split the army. "+" = End, "Finished choosing units?" = No
            if idle > 1.0 and now - self.last_press > 2.0:
                if "E_Menu" in n:
                    self.press("Left", "A", gap=0.6)
                    self.log(f"chapter {st.chapter}: armies kept as the game split them")
                else:
                    self.press("B", gap=0.6)
                    self.press("Start")
            return
        if n & EVENT and "E_Menu" in n and not n & {"E_Talk", "E_TalkWindow"}:
            # a menu inside an event, e.g. "Your pack is full" -> pick the item -> "Drop this item?" (No)
            if idle > 1.5 and now - self.last_press > 2.0:
                self.press("A", gap=0.8)
                self.press("Left", "A", gap=0.5)
                self.log(f"chapter {st.chapter}: answered an event menu (A, Left, A)")
            return
        if n & EVENT:
            if now - self.last_press > 0.6:
                self.toggle = not self.toggle    # Start skips an event; A advances one that can't be skipped
                self.press("Start" if self.toggle else "A")
            return
        if n & {"BasesProc", "BaseProc"}:  # base (PoR / RD): End is the last line (Up wraps), "Leave base?" = Yes
            if idle < 1.0 or now - self.last_press < 2.0:
                return
            extra = {x for x in n if x.startswith("Base") or x.startswith("E_Trade")} - {"BasesProc", "BaseProc"}
            if extra or "E_Menu" not in n:
                self.press("B")          # inside Outfit, Manage... or a report
                if idle > 8:
                    self.press("A")
            else:
                self.press("Up", gap=0.6)
                self.press("A", gap=1.2)
                self.press("A")
                self.log(f"chapter {st.chapter}: base, End")
            return
        if "BMapSallyProc" in n:          # preparations: Start = Fight, "Begin now?" defaults to Yes
            if idle < 1.0 or now - self.last_press < 2.0:
                return
            if n & {"E_SallyList"} or "E_Menu" not in n:
                self.press("B")          # a sub-screen we did not mean to open
            else:
                self.press("Start", gap=1.2)
                self.press("A")
                self.log(f"chapter {st.chapter}: preparations, Fight")
            return
        if "E_BMapPlph" in n:
            self.player_phase(st, idle)
            return
        if "E_BMapMain" in n and st.phase != 0 and not n & {"E_Talk", "E_Menu"}:
            return                       # enemy/ally phase: the victory event takes over
        if idle > 1.5 and now - self.last_press > 1.0:
            self.press("A")

    def new_game(self, st: State, idle: float) -> None:
        n = st.names
        if n & BUSY:
            return
        if idle < 1.5 or time.time() - self.last_press < 2.0:
            return
        if "E_RankSeleWin" in n:         # Radiant Dawn: Easy / Normal / Hard (locked on a new file)
            self.press("Right", gap=0.6)
            self.shot("difficulty")
            self.press("A")
            self.log("New Game: Normal")
            return
        if not self.build.wii and not n & MESSAGE and self.difficulty_dialog():
            self.press("Right", "Right", gap=0.6)
            self.shot("difficulty")
            self.press("A")
            self.log("New Game: Difficult")
            return
        # "create a file?" Yes / "file created" / top menu New Game / slot 1
        self.press("A")

    def save_menu(self, st: State, idle: float) -> None:
        """Between chapters: the file list opens on the file in play; "Would you like to save?"
        (and "Overwrite?") default to No."""
        n = st.names
        if n & BUSY:
            return
        if idle < 1.0 or time.time() - self.last_press < 1.5:
            return
        if n & MESSAGE:
            self.press("Left", gap=0.4)
            self.press("A")
        else:
            self.press("A")

    def difficulty_dialog(self) -> bool:
        """The New Game difficulty box (dark navy) is over the slot list (green and brown)."""
        image = self.grab()
        if image is None:
            return False
        w, h = image.size
        for fx, fy in ((650 / 960, 300 / 508), (260 / 960, 180 / 508)):
            r, g, b = image.getpixel((int(fx * w), int(fy * h)))
            if not (r <= 8 and g <= 10 and b >= 10):
                return False
        return True

    def grab(self):
        path = self.out / "probe.png"
        try:
            di.grab(self.pid, str(path))
            from PIL import Image
            return Image.open(path).convert("RGB")
        except (OSError, ValueError):
            return None

    def player_phase(self, st: State, idle: float) -> None:
        n = st.names
        if "E_Jyokyo" in n or "E_Xinfo" in n:
            self.press("B")
            return
        if "E_Menu" in n:
            self.press("B")              # some menu we did not open on purpose
            return
        if idle < 1.0 or time.time() - self.last_press < 1.5:
            return
        if st.turn > 1:
            self.log(f"WARNING chapter {st.chapter}: turn {st.turn} player phase (no victory after turn 1)")
        if self.build.wii:
            self.press("WA", gap=0.9)       # Radiant Dawn: map menu on Wii A
        else:
            self.press("Minus", gap=0.8)    # map menu (Z)
        if "E_Menu" in self.state().names:  # End is the last line
            self.press("Up", gap=0.4)
            self.press("A", gap=0.8)
            self.log(f"chapter {st.chapter}: ended turn {st.turn}")

    # -- loop -------------------------------------------------------------------------------------
    def play(self, minutes: float) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        self.log_file = open(self.out / "log.txt", "a", encoding="utf-8")
        self.start = self.since = time.time()
        self.boot()
        deadline = time.time() + minutes * 60
        last_chapter, chapter_since = 0, time.time()
        try:
            while time.time() < deadline:
                if (self.out / "STOP").exists():
                    (self.out / "STOP").unlink()
                    self.log("STOP file: driver stopped, Dolphin left open")
                    self.keep_open = True
                    return
                try:
                    st = self.state()
                except OSError:
                    self.log("Dolphin closed")
                    return
                key = st.key()
                if key != self.last_key:
                    self.last_key, self.since = key, time.time()
                    self.log(key)
                    sig = ",".join(sorted(n for n in st.names if n not in NOISE))
                    if sig not in self.seen:
                        self.seen.add(sig)
                        self.shot(f"ch{st.chapter:02d}")
                if st.chapter != last_chapter:
                    self.log(f"=== chapter {st.chapter}")
                    last_chapter, chapter_since = st.chapter, time.time()
                elif time.time() - chapter_since > 900:
                    self.shot(f"stalled_ch{st.chapter:02d}")
                    self.log(f"STALLED: chapter {st.chapter} for 15 min ({key})")
                    chapter_since = time.time()
                self.collect_saves(st)
                if time.time() - self.since > 90:
                    self.shot(f"stuck_ch{st.chapter:02d}")
                    self.log("STUCK for 90 s; pressing B, A")
                    self.press("B", "A")
                    self.since = time.time()
                self.step(st)
                if self.finished:
                    self.shot("finished")
                    self.log("FINISHED: the ending is over")
                    return
                time.sleep(0.25)
        finally:
            self.log(f"done: {self.save_count} saves")
            self.log_file.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--user", type=Path, help="Dolphin user folder (default <out>/user, wiped)")
    parser.add_argument("--minutes", type=float, default=600)
    parser.add_argument("--keep-open", action="store_true", help="leave Dolphin running at the end")
    parser.add_argument("--resume", type=Path,
                        help="a save file this run made (saves/NNN_...): restart its chapter instead of New Game")
    args = parser.parse_args()
    user = args.user or args.out / "user"
    manifest = json.loads((args.run / "sweep.json").read_text(encoding="utf-8"))
    for folder in (user, args.out / "card"):
        if folder.exists():
            shutil.rmtree(folder)
    sweep = Sweep(args.run, args.out, user, BUILDS[manifest["region"]])
    if args.resume:
        card = sweep.card
        card.mkdir(parents=True)
        name = args.resume.name.split("_", 2)[2]          # NNN_chapterNN_<save file name>
        seeded = card / name
        shutil.copy2(args.resume, seeded)
        sweep.saves[name] = (seeded.stat().st_size, seeded.stat().st_mtime_ns)
        sweep.save_count = len(list((args.out / "saves").glob("*")))
        sweep.difficulty_checked = True   # the file keeps the difficulty it was made with
    try:
        sweep.play(args.minutes)
    finally:
        if not (args.keep_open or sweep.keep_open) and sweep.pid:
            sweep.stop()


if __name__ == "__main__":
    main()
