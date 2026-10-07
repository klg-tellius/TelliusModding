"""The event-script interpreter: runs a ``.cmb`` function one instruction per step.

Semantics are those of the game's ``script_interpreter_main_loop`` as
:mod:`fe_modding.formats.cmb.model` and the archive's ``event-script`` /
``events-scripting`` articles describe them:

- operands are signed; ``frame[0..num_args-1]`` are the arguments and the
  other locals start at 0; the 32 globals are shared by every script;
- every call leaves exactly one value on the stack; ``return`` pops one;
- ``branchz``/``branchnz`` pop and test; ``branchkeepz`` (``or``) jumps with
  1 when the value is non-zero, ``branchkeepnz`` (``and``) with 0 when it is
  zero, otherwise they drop it;
- ``store`` writes through an address and leaves the value; ``deref`` reads
  through the address on top and keeps it;
- an ``externCall`` name is looked up among the natives first, then among
  the named functions of the loaded scripts, chapter first (the global
  chain); an unknown name returns 0, like the game.

Addresses are ``("L", depth, slot)`` (a local of the frame at that depth) or
``("G", slot)``, so a running script stays plain data.
"""

from __future__ import annotations

from typing import Optional

from ..formats.cmb.binary import _pool_layout
from ..formats.cmb.model import (EXTERN_CALL, LOCAL_CALL, OPCODES, RETURN, Label, RawStr, var_op_info)
from .state import Frame, GameState, ScriptRun
from .world import World

#: Instructions a single event may run before it is stopped (a loop waiting on something the simulator doesn't model).
MAX_INSTRUCTIONS = 200_000

_BINARY = {
    "add": lambda a, b: a + b, "sub": lambda a, b: a - b, "mul": lambda a, b: a * b,
    "div": lambda a, b: int(a / b) if b else 0, "mod": lambda a, b: (abs(a) % abs(b)) * (1 if a >= 0 else -1) if b else 0,
    "or": lambda a, b: a | b, "and": lambda a, b: a & b, "xor": lambda a, b: a ^ b,
    "shl": lambda a, b: a << (b & 31), "shr": lambda a, b: a >> (b & 31),
    "eq": lambda a, b: int(a == b), "ne": lambda a, b: int(a != b), "lt": lambda a, b: int(a < b),
    "le": lambda a, b: int(a <= b), "gt": lambda a, b: int(a > b), "ge": lambda a, b: int(a >= b),
}


def _s32(value) -> int:
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, int):
        return value
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


def _num(value) -> int:
    """A stack value as a number (a string or an address counts as non-zero)."""
    if isinstance(value, int):
        return value
    return 1 if value else 0


class ScriptError(RuntimeError):
    pass


class _Code:
    """Per-function instruction list with label targets resolved (cached on the world)."""

    def __init__(self, fn):
        self.instrs = []
        targets = {}
        for item in fn.code:
            if isinstance(item, Label):
                targets[id(item)] = len(self.instrs)
            else:
                self.instrs.append(item)
        self.targets = targets


def code(world: World, script: int, function: int) -> _Code:
    cache = getattr(world, "_code_cache", None)
    if cache is None:
        cache = world._code_cache = {}
    key = (script, function)
    if key not in cache:
        cache[key] = _Code(world.scripts[script].functions[function])
    return cache[key]


def raw_string(world: World, script: int, offset: int) -> str:
    cache = getattr(world, "_pool_blob", None)
    if cache is None:
        cache = world._pool_blob = {}
    if script not in cache:
        cache[script] = _pool_layout(world.scripts[script])[0]
    blob = cache[script]
    end = blob.find(b"\x00", offset)
    return blob[offset:end if end >= 0 else len(blob)].decode("shift_jis", errors="replace")


def disassemble(ins) -> str:
    parts = []
    for o in ins.operands:
        if isinstance(o, Label):
            parts.append(o.name or "label")
        elif isinstance(o, RawStr):
            parts.append(f"str@{o.offset}")
        elif isinstance(o, str):
            parts.append(repr(o))
        else:
            parts.append(str(o))
    return f"{ins.name} {', '.join(parts)}".rstrip()


class VM:
    """Runs the :class:`ScriptRun` at the front of the queue."""

    def __init__(self, world: World, state: GameState, run: ScriptRun):
        self.world, self.state, self.run = world, state, run
        self.inserted: list = []  # tasks to run before the script continues

    # -- memory ---------------------------------------------------------------------------------
    def _cell(self, addr) -> tuple:
        if not isinstance(addr, tuple):
            raise ScriptError(f"not an address: {addr!r}")
        if addr[0] == "G":
            slot = addr[1]
            if not 0 <= slot < len(self.state.globals):
                raise ScriptError(f"global slot {slot} out of range")
            return self.state.globals, slot
        frame = self.run.frames[addr[1]]
        slot = addr[2]
        if slot < 0:
            raise ScriptError(f"local slot {slot}")
        while slot >= len(frame.locals):
            frame.locals.append(0)
        return frame.locals, slot

    def read(self, addr):
        cells, slot = self._cell(addr)
        return cells[slot]

    def write(self, addr, value) -> None:
        cells, slot = self._cell(addr)
        cells[slot] = value

    # -- stepping -------------------------------------------------------------------------------
    def describe(self) -> str:
        frame = self.run.frames[-1]
        c = code(self.world, frame.script, frame.function)
        if frame.pc >= len(c.instrs):
            return "(end)"
        return disassemble(c.instrs[frame.pc])

    def step(self) -> bool:
        """Run one instruction. Returns True when the event has finished."""
        run = self.run
        if not run.frames:
            return True
        frame: Frame = run.frames[-1]
        c = code(self.world, frame.script, frame.function)
        if frame.pc >= len(c.instrs):  # fell off the end: implicit return 0
            return self._return(0)
        ins = c.instrs[frame.pc]
        frame.pc += 1
        op, name, stack = ins.op, ins.name, frame.stack
        info = var_op_info(op)
        if info is not None:
            mode, is_global, _wide = info
            slot = ins.operands[0]
            base = ("G", slot) if is_global else ("L", len(run.frames) - 1, slot)
            if mode in ("pusharray", "pushaddrarray"):
                index = _num(stack.pop())
                base = base[:-1] + (base[-1] + index,)
            elif mode in ("pusharrayP", "pushaddrarrayP"):
                index = _num(stack.pop())
                pointer = self.read(base)
                if not isinstance(pointer, tuple):
                    raise ScriptError(f"{name}: slot {slot} holds no address")
                base = pointer[:-1] + (pointer[-1] + index,)
            stack.append(self.read(base) if mode.startswith("pusharray") or mode == "pushvar" else base)
        elif name in ("push8", "push16", "push32"):
            stack.append(ins.operands[0])
        elif name.startswith("pushstr"):
            value = ins.operands[0]
            stack.append(raw_string(self.world, frame.script, value.offset) if isinstance(value, RawStr) else value)
        elif name == "deref":
            stack.append(self.read(stack[-1]))
        elif name == "pop":
            if stack:
                stack.pop()
        elif name == "store":
            value, addr = stack.pop(), stack.pop()
            self.write(addr, value)
            stack.append(value)
        elif name in _BINARY:
            b, a = stack.pop(), stack.pop()
            if name in ("eq", "ne") and (isinstance(a, str) or isinstance(b, str)):
                stack.append(int((a == b) == (name == "eq")))
            else:
                stack.append(_s32(_BINARY[name](_num(a), _num(b))))
        elif name in ("streq", "strne"):
            b, a = stack.pop(), stack.pop()
            stack.append(int((str(a) == str(b)) == (name == "streq")))
        elif name == "neg":
            stack.append(_s32(-_num(stack.pop())))
        elif name == "bitnot":
            stack.append(_s32(~_num(stack.pop())))
        elif name == "not":
            stack.append(int(not _num(stack.pop())))
        elif op == LOCAL_CALL:
            self._call(frame.script, ins.operands[0])
        elif op == EXTERN_CALL:
            self._extern(ins.operands[0], ins.operands[1], frame)
        elif op == RETURN:
            return self._return(stack.pop() if stack else 0)
        elif name == "branch":
            frame.pc = c.targets[id(ins.operands[0])]
        elif name in ("branchz", "branchnz"):
            value = _num(stack.pop())
            if (value == 0) == (name == "branchz"):
                frame.pc = c.targets[id(ins.operands[0])]
        elif name == "branchkeepz":  # `or`: a true left side decides
            value = _num(stack.pop())
            if value:
                stack.append(1)
                frame.pc = c.targets[id(ins.operands[0])]
        elif name == "branchkeepnz":  # `and`: a false left side decides
            value = _num(stack.pop())
            if not value:
                stack.append(0)
                frame.pc = c.targets[id(ins.operands[0])]
        elif name == "printf":
            count = ins.operands[0]
            args = stack[len(stack) - count:] if count else []
            del stack[len(stack) - count:]
            self.state.emit("script", "printf " + " ".join(str(a) for a in args))
        elif name in ("nop", "nop4", "yield"):
            pass
        elif name in ("ret0", "ret1"):
            return self._return(int(name == "ret1"))
        elif name == "dup":
            stack.append(stack[-1])
        else:
            raise ScriptError(f"opcode {OPCODES[op]} is not supported")
        return not run.frames

    # -- calls ----------------------------------------------------------------------------------
    def _call(self, script: int, function: int, args: Optional[list] = None) -> None:
        caller = self.run.frames[-1]
        fn = self.world.scripts[script].functions[function]
        if args is None:
            n = fn.num_args
            args = caller.stack[len(caller.stack) - n:] if n else []
            del caller.stack[len(caller.stack) - n:]
        local = list(args) + [0] * max(0, fn.num_vars - len(args))
        self.run.frames.append(Frame(script, function, 0, [], local))

    def _return(self, value) -> bool:
        self.run.frames.pop()
        if not self.run.frames:
            return True
        self.run.frames[-1].stack.append(value)
        return False

    def _extern(self, name, argc: int, frame: Frame) -> None:
        if isinstance(name, RawStr):
            name = raw_string(self.world, frame.script, name.offset)
        args = frame.stack[len(frame.stack) - argc:] if argc else []
        del frame.stack[len(frame.stack) - argc:]
        from . import natives

        handler = natives.HANDLERS.get(name)
        if handler is not None:
            frame.stack.append(_s32(handler(self, list(args))))
            return
        target = self._find(name, frame.script)
        if target is not None:
            script, function = target
            self._call(script, function, list(args))
            return
        frame.stack.append(natives.unmodelled(self, name, list(args)))

    def _find(self, name: str, current: int) -> Optional[tuple]:
        order = [current] + [i for i in range(len(self.world.scripts)) if i != current]
        for si in order:
            for fi, fn in enumerate(self.world.scripts[si].functions):
                if fn.id_string == name:
                    return si, fi
        return None

    # -- helpers for natives --------------------------------------------------------------------
    def insert(self, *tasks) -> None:
        """Run ``tasks`` before the script continues (a conversation, a fight...)."""
        self.inserted.extend(tasks)

    @property
    def ctx(self) -> dict:
        return self.run.ctx


def step(world: World, state: GameState, run: ScriptRun) -> tuple:
    """One instruction of ``run`` (the task at the front of the queue).
    Returns ``(finished, description, inserted tasks)``."""
    vm = VM(world, state, run)
    frame = run.frames[-1] if run.frames else None
    where = ""
    if frame is not None:
        where = f"{run.name}" if len(run.frames) == 1 else f"{run.name} > {_fn_name(world, frame)}"
        where += f" #{frame.pc}: {vm.describe()}"
    run.executed += 1
    if run.executed > MAX_INSTRUCTIONS:
        state.emit("warn", f"Script {run.name} stopped after {MAX_INSTRUCTIONS} instructions (a loop waiting on "
                           "something the simulator doesn't model?)")
        run.frames.clear()
        return True, where, []
    try:
        finished = vm.step()
    except (ScriptError, IndexError, KeyError, TypeError) as exc:
        state.emit("warn", f"Script {run.name} stopped: {exc}")
        run.frames.clear()
        finished = True
    return finished, where, vm.inserted


def _fn_name(world: World, frame: Frame) -> str:
    from .triggers import function_names

    return function_names(world, frame.script)[frame.function]
