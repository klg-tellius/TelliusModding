"""Read (and write) the emulated RAM of a running Dolphin from outside, with no debugger.

Dolphin keeps MEM1 in a shared memory view of its own process: a committed MEM_MAPPED region of
0x2000000 bytes (24 MB used on GameCube and Wii) that starts with the disc's game ID. On a Wii
game MEM2 is a second mapped region of 0x4000000 bytes. ``DolphinRam.attach(pid)`` finds them with
VirtualQueryEx; ``read``/``write`` take emulated addresses (0x80000000 or 0x90000000 based).
Reads are a few microseconds, so a driver can poll every frame. Windows only.

    python -m tools.dolphin_ram <pid> procs        list the live processes of the game's process pool
    python -m tools.dolphin_ram <pid> read <address> <length>
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import sys
from typing import Optional

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_VM_READ, PROCESS_VM_WRITE, PROCESS_VM_OPERATION, PROCESS_QUERY_INFORMATION = 0x10, 0x20, 0x08, 0x400
MEM_COMMIT, MEM_MAPPED = 0x1000, 0x40000
MEM1_SIZE, MEM2_SIZE = 0x2000000, 0x4000000


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


kernel32.OpenProcess.restype = wt.HANDLE
kernel32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION),
                                    ctypes.c_size_t]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                       ctypes.POINTER(ctypes.c_size_t)]
kernel32.WriteProcessMemory.argtypes = kernel32.ReadProcessMemory.argtypes

#: Process pool of each build: (address, slot size). 256 slots, +0x00 script, +0x04 PC, +0x14 name
#: pointer; a free slot has script 0. PoR: ``find_process_by_script`` (0x8000C0C0). Radiant Dawn:
#: the loops at 0x80083214 / 0x80087098 (``li r0,0x100``), slots of 0xB0 bytes.
PROCESS_POOLS = {"GFEE01": (0x802A66D8, 0x70), "RFEE01": (0x803D9A58, 0xB0)}
PROCESS_COUNT = 256


class DolphinRam:
    def __init__(self, handle, mem1: int, mem2: Optional[int]):
        self.handle, self.mem1, self.mem2 = handle, mem1, mem2

    @classmethod
    def attach(cls, pid: int, game_id: Optional[bytes] = None) -> Optional["DolphinRam"]:
        """None while the emulated RAM isn't there yet (Dolphin still starting)."""
        handle = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
                                      | PROCESS_QUERY_INFORMATION, False, pid)
        if not handle:
            raise OSError(ctypes.get_last_error(), f"cannot open process {pid}")
        mem1 = mem2 = None
        info = MEMORY_BASIC_INFORMATION()
        address = 0
        while kernel32.VirtualQueryEx(handle, ctypes.c_void_p(address), ctypes.byref(info), ctypes.sizeof(info)):
            base = info.BaseAddress or 0
            if info.State == MEM_COMMIT and info.Type == MEM_MAPPED:
                if info.RegionSize == MEM1_SIZE and mem1 is None:
                    head = _read(handle, base, 6)
                    if head and head[:1].isalnum() and (game_id is None or head == game_id):
                        mem1 = base
                elif info.RegionSize == MEM2_SIZE and mem1 is not None and mem2 is None:
                    mem2 = base
            address = base + info.RegionSize
            if address >= 0x7FFFFFFFFFFF:
                break
        if mem1 is None:
            kernel32.CloseHandle(handle)
            return None
        return cls(handle, mem1, mem2)

    def close(self) -> None:
        kernel32.CloseHandle(self.handle)

    def _host(self, address: int, length: int) -> int:
        offset = address & 0x0FFFFFFF
        if address & 0x10000000:
            if self.mem2 is None or offset + length > MEM2_SIZE:
                raise ValueError(f"no MEM2 at {address:#x}")
            return self.mem2 + offset
        if offset + length > MEM1_SIZE:
            raise ValueError(f"outside MEM1: {address:#x}")
        return self.mem1 + offset

    def read(self, address: int, length: int) -> bytes:
        data = _read(self.handle, self._host(address, length), length)
        if data is None:
            raise OSError(ctypes.get_last_error(), f"read {address:#x}")
        return data

    def write(self, address: int, data: bytes) -> None:
        done = ctypes.c_size_t()
        buf = ctypes.create_string_buffer(data, len(data))
        if not kernel32.WriteProcessMemory(self.handle, ctypes.c_void_p(self._host(address, len(data))), buf,
                                           len(data), ctypes.byref(done)):
            raise OSError(ctypes.get_last_error(), f"write {address:#x}")

    def u8(self, address: int) -> int:
        return self.read(address, 1)[0]

    def u16(self, address: int) -> int:
        return struct.unpack(">H", self.read(address, 2))[0]

    def u32(self, address: int) -> int:
        return struct.unpack(">I", self.read(address, 4))[0]

    def cstring(self, address: int, limit: int = 64) -> str:
        if not 0x80000000 <= address < 0x81800000:
            return ""
        raw = self.read(address, limit)
        return raw.split(b"\0", 1)[0].decode("latin-1")

    def game_id(self) -> str:
        return self.read(0x80000000, 6).decode("latin-1")

    def processes(self, pool: tuple[int, int]) -> list[str]:
        """Names of the live processes, in pool order. ``pool``: a :data:`PROCESS_POOLS` value."""
        address, size = pool
        raw = self.read(address, size * PROCESS_COUNT)
        names = []
        for slot in range(PROCESS_COUNT):
            script, _pc, name = struct.unpack_from(">II12xI", raw, slot * size)
            if script:
                names.append(self.cstring(name) or f"?{script:08X}")
        return names


def _read(handle, host: int, length: int) -> Optional[bytes]:
    buf = ctypes.create_string_buffer(length)
    done = ctypes.c_size_t()
    if not kernel32.ReadProcessMemory(handle, ctypes.c_void_p(host), buf, length, ctypes.byref(done)):
        return None
    return buf.raw[:done.value]


def main() -> None:
    pid, command = int(sys.argv[1]), sys.argv[2]
    ram = DolphinRam.attach(pid)
    if ram is None:
        sys.exit("no emulated RAM found (game not running?)")
    if command == "procs":
        print(ram.game_id(), ", ".join(ram.processes(PROCESS_POOLS[ram.game_id()])))
    elif command == "read":
        print(ram.read(int(sys.argv[3], 16), int(sys.argv[4], 0)).hex(" "))


if __name__ == "__main__":
    main()
