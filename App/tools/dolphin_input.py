"""Drive one running Dolphin from separate calls, for unattended in-game checks of Radiant Dawn.

Set ``TELLIUS_DOLPHIN`` to Dolphin.exe. Run trees come from ``tools/session_playtest`` (``assemble_run_tree``).
Radiant Dawn reads the emulated Wii Remote held sideways, not the GameCube pad: the keys below are bound to
both, with Dolphin's background input on, so the Dolphin window need not have focus. Windows only.

Usage (python -m tools.dolphin_input ...):

  dolphin_input start <run tree> <user dir> [state file]   configure, boot (optionally from a save state), return
  dolphin_input press <out png or -> <key> [<key> ...]      press keys in turn (0.5 s apart), then screenshot
  dolphin_input hold <key> <seconds>                        hold one key
  dolphin_input shot <out png>
  dolphin_input save <slot>        save state to slot 1 or 2 (Dolphin hotkeys, see HOTKEYS)
  dolphin_input load 1
  dolphin_input stop

Buttons (Wii Remote held sideways, Radiant Dawn's default; the GameCube pad gets the same keys):
A=2 (OK), B=1 (Cancel), Start=+, Minus=-, Home, Up/Down/Left/Right = D-pad, WA=Wii A.
WA (NOCONVERT) does not reach the game: open the map menu with A on an empty tile. Only save-state
slot 1 works (KANA is not a usable hotkey); the --save_state start argument did not load a state either.
Keys are spare DirectInput keys no Windows application uses: the Japanese-keyboard keys sent as extended
scan codes E0 11..E0 17, YEN, CONVERT and NOCONVERT; F13-F15 and KANA are Dolphin hotkeys. DirectInput
has no codes for F16 and above, so Dolphin can't bind them.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

DOLPHIN = Path(os.environ.get("TELLIUS_DOLPHIN", "Dolphin.exe"))
SOURCE = Path.home() / "AppData/Roaming/Dolphin Emulator/Config"
STATE = Path(tempfile.gettempdir()) / "tellius_dolphin_input.json"

# name -> (Dolphin key name, scan code, extended)
KEYCODES = {
    "AT": (0x11, True), "COLON": (0x12, True), "UNDERLINE": (0x13, True), "KANJI": (0x14, True),
    "STOP": (0x15, True), "AX": (0x16, True), "UNLABELED": (0x17, True),
    "F13": (0x64, False), "F14": (0x65, False), "F15": (0x66, False),
    "KANA": (0x70, False), "CONVERT": (0x79, False), "NOCONVERT": (0x7B, False), "YEN": (0x7D, False),
}
BUTTONS = {  # button -> (key, Wii Remote control, GameCube control)
    "A": ("AT", "Buttons/2", "Buttons/A"),
    "B": ("COLON", "Buttons/1", "Buttons/B"),
    "Start": ("UNDERLINE", "Buttons/+", "Buttons/Start"),
    "Up": ("KANJI", "D-Pad/Up", "D-Pad/Up"),
    "Left": ("STOP", "D-Pad/Left", "D-Pad/Left"),
    "Down": ("AX", "D-Pad/Down", "D-Pad/Down"),
    "Right": ("UNLABELED", "D-Pad/Right", "D-Pad/Right"),
    "Minus": ("YEN", "Buttons/-", "Buttons/Z"),
    "WA": ("NOCONVERT", "Buttons/A", "Buttons/X"),
    "Home": ("CONVERT", "Buttons/Home", "Buttons/Y"),
}
HOTKEYS = {  # key -> Dolphin hotkey
    "F13": "General/Take Screenshot",
    "F14": "Save State/Save State Slot 1",
    "F15": "Load State/Load State Slot 1",
    "KANA": "Save State/Save State Slot 2",
}

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
user32.SetProcessDPIAware()


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def send(key, up):
    scan, ext = KEYCODES[key]
    inp = INPUT(type=1)
    inp.ki = KEYBDINPUT(0, scan, 0x0008 | (0x0001 if ext else 0) | (0x0002 if up else 0), 0, None)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def tap(key, hold=0.15):
    send(key, False)
    time.sleep(hold)
    send(key, True)


def _set(text, control, value):
    line = f"{control} = {value}"
    if re.search(rf"^{re.escape(control)} = .*$", text, re.M):
        return re.sub(rf"^{re.escape(control)} = .*$", line, text, count=1, flags=re.M)
    return text.rstrip("\n") + "\n" + line + "\n"


def configure(user):
    cfg = user / "Config"
    cfg.mkdir(parents=True, exist_ok=True)
    for name in ("Dolphin.ini", "GFX.ini", "GCPadNew.ini", "WiimoteNew.ini", "Qt.ini"):
        if (SOURCE / name).is_file():
            shutil.copy2(SOURCE / name, cfg / name)
    pad = (cfg / "GCPadNew.ini").read_text(encoding="utf-8")
    p1, sep, rest = pad.partition("[GCPad2]")
    wii = (cfg / "WiimoteNew.ini").read_text(encoding="utf-8")
    w1, wsep, wrest = wii.partition("[Wiimote2]")
    for key, wcontrol, gcontrol in BUTTONS.values():
        p1 = _set(p1, gcontrol, f"`{key}`")
        w1 = _set(w1, wcontrol, f"`{key}`")
    w1 = _set(w1, "Options/Sideways Wiimote", "True")
    w1 = _set(w1, "Source", "1")
    (cfg / "GCPadNew.ini").write_text(p1 + sep + rest, encoding="utf-8")
    (cfg / "WiimoteNew.ini").write_text(w1 + wsep + wrest, encoding="utf-8")
    ini = (cfg / "Dolphin.ini").read_text(encoding="utf-8")
    ini = re.sub(r"^BackgroundInput = .*\n", "", ini, flags=re.M)
    for section in ("Input", "General"):
        if re.search(rf"^\[{section}\]$", ini, re.M):
            ini = re.sub(rf"^\[{section}\]\n", f"[{section}]\nBackgroundInput = True\n", ini, count=1, flags=re.M)
        else:
            ini += f"\n[{section}]\nBackgroundInput = True\n"
    (cfg / "Dolphin.ini").write_text(ini, encoding="utf-8")
    (cfg / "Hotkeys.ini").write_text("[Hotkeys]\nDevice = DInput/0/Keyboard Mouse\n" + "".join(
        f"{control} = `{key}`\n" for key, control in HOTKEYS.items()), encoding="utf-8")


def window(pid):
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            r = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(r))
            found.append((r.right * r.bottom, hwnd, r.right, r.bottom))
        return True
    user32.EnumWindows(cb, 0)
    return max(found) if found else None


def grab(pid, path):
    win = window(pid)
    if not win:
        print("no window")
        return
    _a, hwnd, w, h = win
    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 3)
    buf = ctypes.create_string_buffer(w * h * 4)

    class BMI(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]
    bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB").resize((w // 2, h // 2)).save(path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    print("shot", path)


def main():
    cmd = sys.argv[1]
    if cmd == "start":
        run, user = Path(sys.argv[2]), Path(sys.argv[3])
        configure(user)
        args = [str(DOLPHIN), "--user", str(user), "--batch", "--exec", str(run / "sys" / "main.dol"),
                "--config=Dolphin.DSP.Volume=0", "--config=Dolphin.Interface.ConfirmStop=False",
                "--config=Dolphin.Core.EnableCheats=False",
                "--config=Dolphin.Analytics.Enabled=False", "--config=Dolphin.Analytics.PermissionAsked=True"]
        if len(sys.argv) > 4:
            args += ["--save_state", sys.argv[4]]
        proc = subprocess.Popen(args, creationflags=0x00000008)  # DETACHED_PROCESS
        STATE.write_text(json.dumps({"pid": proc.pid, "user": str(user)}))
        print("started", proc.pid)
        return
    state = json.loads(STATE.read_text())
    pid = state["pid"]
    if cmd == "press":
        out = sys.argv[2]
        for button in sys.argv[3:]:
            if button.startswith("wait"):
                time.sleep(float(button[4:]))
                continue
            tap(BUTTONS[button][0])
            time.sleep(0.5)
        time.sleep(0.5)
        if out != "-":
            grab(pid, out)
    elif cmd == "hold":
        key = BUTTONS[sys.argv[2]][0]
        send(key, False)
        time.sleep(float(sys.argv[3]))
        send(key, True)
    elif cmd == "shot":
        grab(pid, sys.argv[2])
    elif cmd in ("save", "load"):
        slot = int(sys.argv[2])
        key = {("save", 1): "F14", ("load", 1): "F15", ("save", 2): "KANA"}[(cmd, slot)]
        tap(key, 0.2)
        time.sleep(2)
        print(cmd, slot)
    elif cmd == "stop":
        subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True)
        time.sleep(4)
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        print("stopped")


if __name__ == "__main__":
    main()
