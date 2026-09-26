"""Compile ``.fe9s`` source to a :class:`~.model.ScriptFile`.

Code generation deliberately mirrors the game's own (C-like) script
compiler instruction-for-instruction, so decompiling a vanilla script and
compiling it back reproduces the original bytes:

* ``if c: A else: B``  ->  ``c; branchz Lelse; A; branch Lend; Lelse: B; Lend:``
* ``while c: A``        ->  ``Ltop: c; branchz Lend; A; branch Ltop; Lend:``
* ``a and b`` / ``a or b`` -> ``a; branchkeepnz/branchkeepz L; b; L:``
* ``x = e`` -> ``pushaddr x; e; store; pop``;  ``x += e`` adds ``deref``/``add``
* ``var x = e`` -> ``pushaddr x; e; store`` (no pop - how vanilla declarations
  with an initializer compile)
* ``f(...)`` as a statement -> args, call, ``pop`` (every call returns a value)
* every function ends with an implicit ``push8 0; return`` (unless ``@naked``)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import ast as A
from .catalog import TRIGGERS, TRIGGERS_BY_DECORATOR, lookup_extern
from .model import (
    EXTERN_CALL,
    LOCAL_CALL,
    OPCODE_BY_NAME,
    OPERAND_WIDTHS,
    BRANCH_OPS,
    PUSHSTR_OPS,
    Function,
    Instr,
    Label,
    RawStr,
    ScriptFile,
    var_op,
)
from .parser import ParseError, parse

BINARY_OPS = {
    "+": "add", "-": "sub", "*": "mul", "/": "div", "%": "mod", "|": "or", "&": "and", "^": "xor",
    "<<": "shl", ">>": "shr", "==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge",
}
UNARY_OPS = {"-": "neg", "~": "bitnot", "not": "not"}
BUILTIN_CALLS = {"streq": "streq", "strne": "strne"}
RESERVED_CALLS = {"printf", "lit", "strofs", "extern", "streq", "strne"}
FLAG_CALLS = {"set", "get", "clr", "regist", "global"}
GLOBAL_TABLE_SLOTS = 32  # init_script_global_state(0x20, ...) at boot


@dataclass
class Diagnostic:
    severity: str  # "error" | "warning"
    line: int
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.severity}: {self.message}"


class CompileError(Exception):
    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        super().__init__("\n".join(str(d) for d in diagnostics if d.severity == "error"))


@dataclass
class CompileResult:
    script: ScriptFile
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]


def _I(name: str, *operands) -> Instr:
    return Instr(OPCODE_BY_NAME[name], list(operands))


class _Pool:
    """The string pool, append-only so existing offsets never move."""

    def __init__(self, entries: list[str]):
        self.entries = list(entries)
        self.offsets: dict[str, int] = {}
        self.size = 0
        for text in self.entries:
            self.offsets.setdefault(text, self.size)
            self.size += len(text.encode("cp932")) + 1

    def intern(self, text: str) -> int:
        if text not in self.offsets:
            self.entries.append(text)
            self.offsets[text] = self.size
            self.size += len(text.encode("cp932")) + 1
        return self.offsets[text]

    def text_at(self, offset: int) -> Optional[str]:
        for text, off in self.offsets.items():
            if off == offset:
                return text
        return None


class _Loop:
    def __init__(self, top: Label, end: Label):
        self.top, self.end = top, end  # `continue` / `break` targets


class _FunctionCompiler:
    def __init__(self, module: "_ModuleCompiler", fd: A.FuncDef):
        self.m = module
        self.fd = fd
        self.code: list = []
        self.slots: dict[str, int] = {}
        self.sizes: dict[str, int] = {}
        self.next_slot = 0
        self.labels: dict[str, Label] = {}
        self.loops: list[_Loop] = []
        for p in fd.params:
            self.declare(p, 1, fd.line)

    # -- helpers --
    def error(self, line: int, message: str) -> None:
        self.m.diag("error", line, message)

    def warn(self, line: int, message: str) -> None:
        self.m.diag("warning", line, message)

    def emit(self, *items) -> None:
        self.code.extend(items)

    def declare(self, name: str, size: int, line: int) -> int:
        if name in self.slots:
            return self.slots[name]
        if name in self.m.globals:
            self.warn(line, f"Local {name!r} hides the global of the same name")
        self.slots[name] = self.next_slot
        self.sizes[name] = size
        self.next_slot += size
        return self.slots[name]

    def label(self, name: str) -> Label:
        return self.labels.setdefault(name, Label(name))

    def resolve(self, name: str, line: int):
        """(is_global, slot) for a variable name."""
        if name in self.slots:
            return False, self.slots[name]
        if name in self.m.globals:
            return True, self.m.globals[name]
        self.error(line, f"Unknown variable {name!r} (declare it with 'var {name}' or assign it first)")
        return False, 0

    # -- expressions --
    def expr(self, e: A.Expr, line: int) -> None:
        if isinstance(e, A.Num):
            self.emit(_I("push8", e.value))
        elif isinstance(e, A.Str):
            self.m.pool.intern(e.value)
            self.emit(_I("pushstr8", e.value))
        elif isinstance(e, A.StrOffset):
            self.emit(_I("pushstr8", RawStr(e.offset)))
        elif isinstance(e, A.Name):
            is_global, slot = self.resolve(e.id, line)
            self.emit(Instr(var_op("pushvar", is_global, False), [slot]))
        elif isinstance(e, A.Index):
            self.expr(e.index, line)
            is_global, slot = self.resolve(e.base.id, line)
            self.emit(Instr(var_op("pusharray", is_global, False), [slot]))
        elif isinstance(e, A.AddrOf):
            self.address(e.target, line)
        elif isinstance(e, A.BinOp):
            self.expr(e.left, line)
            self.expr(e.right, line)
            self.emit(_I(BINARY_OPS[e.op]))
        elif isinstance(e, A.BoolOp):
            end = Label()
            self.expr(e.left, line)
            self.emit(_I("branchkeepnz" if e.op == "and" else "branchkeepz", end))
            self.expr(e.right, line)
            self.emit(end)
        elif isinstance(e, A.UnOp):
            self.expr(e.operand, line)
            self.emit(_I(UNARY_OPS[e.op]))
        elif isinstance(e, A.Call):
            self.call(e, line)
        elif isinstance(e, A.Walrus):
            if isinstance(e.target, A.Name) and e.target.id not in self.slots and e.target.id not in self.m.globals:
                self.declare(e.target.id, 1, line)
            self.address(e.target, line)
            self.expr(e.value, line)
            self.emit(_I("store"))
        else:  # pragma: no cover - parser never builds anything else
            self.error(line, f"Unsupported expression {e!r}")

    def address(self, target, line: int) -> None:
        if isinstance(target, A.Name):
            is_global, slot = self.resolve(target.id, line)
            self.emit(Instr(var_op("pushaddr", is_global, False), [slot]))
        else:
            self.expr(target.index, line)
            is_global, slot = self.resolve(target.base.id, line)
            self.emit(Instr(var_op("pushaddrarray", is_global, False), [slot]))

    def call(self, c: A.Call, line: int) -> None:
        name = c.name
        if not c.extern and name in BUILTIN_CALLS:
            if len(c.args) != 2:
                self.error(line, f"{name}() takes 2 arguments")
            for a in c.args:
                self.expr(a, line)
            self.emit(_I(BUILTIN_CALLS[name]))
            return
        if not c.extern and name == "printf":
            self.error(line, "printf(...) is a statement, it has no value")
            return
        for a in c.args:
            self.expr(a, line)
        if not c.extern and name in self.m.func_index:
            index = self.m.func_index[name]
            want = len(self.m.func_params[name])
            if len(c.args) != want:
                self.error(line, f"{name}() takes {want} argument(s), got {len(c.args)}")
            self.emit(_I("localCall", index))
            return
        if isinstance(name, A.StrOffset):
            self.emit(_I("externCall", RawStr(name.offset), len(c.args)))
            return
        self.m.pool.intern(name)
        self.emit(_I("externCall", name, len(c.args)))
        self.m.check_extern(name, len(c.args), line)
        if name in FLAG_CALLS and c.args and isinstance(c.args[0], A.Str):
            self.m.flag_uses.append((name, c.args[0].value, line))

    # -- statements --
    def block(self, stmts: list) -> None:
        for s in stmts:
            self.stmt(s)

    def stmt(self, s: A.Stmt) -> None:
        line = s.line
        if isinstance(s, A.ExprStmt):
            self.expr(s.expr, line)
            self.emit(_I("pop"))
        elif isinstance(s, A.Assign):
            if isinstance(s.target, A.Name) and s.target.id not in self.slots and s.target.id not in self.m.globals:
                if s.op:
                    self.error(line, f"Unknown variable {s.target.id!r}")
                self.declare(s.target.id, 1, line)
            self.address(s.target, line)
            if s.op:
                self.emit(_I("deref"))
            self.expr(s.value, line)
            if s.op:
                self.emit(_I(BINARY_OPS[s.op]))
            self.emit(_I("store"), _I("pop"))
        elif isinstance(s, A.VarDecl):
            for name, size in s.names:
                if name in self.slots:
                    self.error(line, f"{name!r} is already declared")
                self.declare(name, size, line)
        elif isinstance(s, A.VarInit):
            self.declare(s.name, 1, line)
            self.address(A.Name(s.name), line)
            self.expr(s.value, line)
            self.emit(_I("store"))
        elif isinstance(s, A.Printf):
            for a in s.args:
                self.expr(a, line)
            self.emit(_I("printf", len(s.args)))
        elif isinstance(s, A.Yield):
            self.emit(_I("yield"))
        elif isinstance(s, A.Pass):
            pass
        elif isinstance(s, A.Return):
            self.expr(s.value if s.value is not None else A.Num(0), line)
            self.emit(_I("return"))
        elif isinstance(s, A.If):
            else_label, end_label = Label(), Label()
            self.expr(s.cond, line)
            self.emit(_I("branchz", else_label))
            self.block(s.body)
            if s.orelse:
                self.emit(_I("branch", end_label), else_label)
                self.block(s.orelse)
                self.emit(end_label)
            else:
                self.emit(else_label)
        elif isinstance(s, A.While):
            loop = _Loop(Label(), Label())
            self.emit(loop.top)
            if s.cond is not None:
                self.expr(s.cond, line)
                self.emit(_I("branchz", loop.end))
            self.loops.append(loop)
            self.block(s.body)
            self.loops.pop()
            self.emit(_I("branch", loop.top), loop.end)
        elif isinstance(s, A.DoWhile):
            # Top: body; Next: cond; branchnz Top; End:
            top, loop = Label(), _Loop(Label(), Label())
            self.emit(top)
            self.loops.append(loop)
            self.block(s.body)
            self.loops.pop()
            self.emit(loop.top)
            self.expr(s.cond, line)
            self.emit(_I("branchnz", top), loop.end)
        elif isinstance(s, (A.Break, A.Continue)):
            if not self.loops:
                self.error(line, f"'{'break' if isinstance(s, A.Break) else 'continue'}' outside a loop")
                return
            loop = self.loops[-1]
            self.emit(_I("branch", loop.end if isinstance(s, A.Break) else loop.top))
        elif isinstance(s, A.Goto):
            target = self.label(s.label)
            if s.when is None:
                self.emit(_I("branch", target))
            else:
                self.expr(s.cond, line)
                self.emit(_I("branchz" if s.when == "unless" else "branchnz", target))
        elif isinstance(s, A.LabelStmt):
            label = self.label(s.name)
            if label in self.code:
                self.error(line, f"Label {s.name!r} defined twice")
            self.emit(label)
        elif isinstance(s, A.Asm):
            self.asm(s)
        else:  # pragma: no cover
            self.error(line, f"Unsupported statement {s!r}")

    def asm(self, s: A.Asm) -> None:
        for opname, operands, label_name, line in s.lines:
            if label_name is not None:
                self.emit(self.label(label_name))
                continue
            if opname not in OPCODE_BY_NAME:
                self.error(line, f"Unknown opcode {opname!r}")
                continue
            op = OPCODE_BY_NAME[opname]
            widths = OPERAND_WIDTHS[op]
            if len(operands) != len(widths):
                self.error(line, f"{opname} takes {len(widths)} operand(s)")
                continue
            ops = []
            for i, value in enumerate(operands):
                if op in BRANCH_OPS:
                    if not (isinstance(value, tuple) and value[0] == "label"):
                        self.error(line, f"{opname} needs a label")
                        value = ("label", "?")
                    ops.append(self.label(value[1]))
                elif (op in PUSHSTR_OPS or op == EXTERN_CALL) and i == 0:
                    if isinstance(value, str):
                        self.m.pool.intern(value)
                        ops.append(value)
                    else:
                        ops.append(RawStr(int(value)))
                elif isinstance(value, int):
                    ops.append(value)
                else:
                    self.error(line, f"Bad operand {value!r} for {opname}")
                    ops.append(0)
            self.emit(Instr(op, ops))

    def run(self, naked: bool) -> list:
        self.block(self.fd.body)
        if not naked:
            self.emit(_I("push8", 0), _I("return"))
        defined = {id(x) for x in self.code if isinstance(x, Label)}
        for name, label in self.labels.items():
            if id(label) not in defined:
                self.error(self.fd.line, f"Label {name!r} is used but never defined")
        return self.code


class _ModuleCompiler:
    def __init__(self, module: A.Module, base: Optional[ScriptFile], known_script_functions: dict,
                 global_flags: Optional[list] = None):
        self.module = module
        self.base = base
        self.global_flags = global_flags
        self.flag_uses: list[tuple[str, str, int]] = []  # (native, flag name, line)
        self.diagnostics: list[Diagnostic] = []
        self.pool = _Pool(base.pool if base else [])
        self.globals = {g.name: g.slot for g in module.globals}
        self.func_index = {fd.name: i for i, fd in enumerate(module.functions)}
        self.func_params = {fd.name: fd.params for fd in module.functions}
        self.known_script_functions = known_script_functions

    def diag(self, severity: str, line: int, message: str) -> None:
        self.diagnostics.append(Diagnostic(severity, line, message))

    def check_extern(self, name: str, argc: int, line: int) -> None:
        sig = lookup_extern(name)
        exported_here = {self.export_name(fd) for fd in self.module.functions}
        if sig is not None and sig.source == "unregistered":
            self.diag("warning", line, f"{name}() is registered nowhere in the game - it always returns 0")
        elif sig is not None:
            if sig.argc != argc:
                self.diag("error", line, f"{name}() takes {sig.argc} argument(s), got {argc}")
        elif name in self.known_script_functions:
            want = self.known_script_functions[name]
            if want != argc:
                self.diag("error", line, f"{name}() takes {want} argument(s), got {argc}")
        elif name not in exported_here:
            self.diag("warning", line, f"{name}() isn't a known game function - the game silently returns 0 for unknown names")

    @staticmethod
    def export_name(fd: A.FuncDef) -> Optional[str]:
        for d in fd.decorators:
            if d.name == "export":
                if d.args and isinstance(d.args[0], A.Str):
                    return d.args[0].value
                return fd.name
        return None

    def trigger(self, fd: A.FuncDef) -> tuple[int, list[int]]:
        fn_type, params = 0, []
        for d in fd.decorators:
            if d.name == "trigger":
                values = [self._const(a, d.line) for a in d.args]
                if not values:
                    self.diag("error", d.line, "@trigger(type, params...) needs a type")
                    continue
                fn_type, params = values[0], values[1:]
            elif d.name in TRIGGERS_BY_DECORATOR:
                kind = TRIGGERS_BY_DECORATOR[d.name]
                fn_type = kind.type
                params = []
                given = dict(d.kwargs)
                for i, spec in enumerate(kind.params):
                    if i < len(d.args):
                        value = d.args[i]
                    elif spec.name in given:
                        value = given.pop(spec.name)
                    else:
                        value = A.Num(0)
                    params.append(self._param(spec, value, d.line))
                for key in given:
                    self.diag("error", d.line, f"@{d.name} has no parameter {key!r}")
                if len(d.args) > len(kind.params):
                    self.diag("error", d.line, f"@{d.name} takes {len(kind.params)} parameter(s)")
        return fn_type, params

    def _const(self, e: A.Expr, line: int) -> int:
        if isinstance(e, A.Num):
            return e.value
        if isinstance(e, A.UnOp) and e.op == "-" and isinstance(e.operand, A.Num):
            return -e.operand.value
        if isinstance(e, A.Str):
            return self.pool.intern(e.value)
        if isinstance(e, A.StrOffset):
            return e.offset
        if isinstance(e, A.Name) and e.id == "None":
            return 0
        self.diag("error", line, "Decorator arguments must be constants")
        return 0

    def _param(self, spec, value: A.Expr, line: int) -> int:
        if spec.enum and isinstance(value, A.Str):
            reverse = {v: k for k, v in spec.enum.items()}
            if value.value not in reverse:
                self.diag("error", line, f"{spec.name} must be one of {', '.join(reverse)}")
                return 0
            return reverse[value.value]
        if isinstance(value, A.Str) and not spec.is_label:
            self.diag("error", line, f"{spec.name} is a number, not a string")
            return 0
        result = self._const(value, line)
        if not 0 <= result <= 0xFFFF:
            self.diag("error", line, f"{spec.name}={result} doesn't fit a 16-bit trigger parameter")
            return 0
        return result

    def check_flags(self) -> None:
        """Flag names are bound to table slots by regist()/global(); set/get/clr on
        a name nobody registers silently do nothing (see formats/event_flags.py)."""
        from .. import event_flags

        lines = {fd.name: fd.line for fd in self.module.functions}
        registered = {flag for native, flag, _ in self.flag_uses if native in ("regist", "global")}
        if "RegistGlobalFlags" in lines:
            globals_ = event_flags.global_flags(self.module)
            vanilla = event_flags.global_flags_vanilla()
            for slot, old in enumerate(vanilla):
                new = globals_[slot] if slot < len(globals_) else None
                if new != old and old != event_flags.RESERVED_GLOBAL:
                    self.diag("warning", lines["RegistGlobalFlags"],
                              f"global flag slot {slot} was {old!r} and is now {new!r}: saves made with the "
                              "original startup.cmb will load that bit under the new name; add new flags "
                              "at the end or rename a reserved slot instead")
                    break
        else:
            globals_ = self.global_flags or event_flags.global_flags_vanilla()
            for native, flag, line in self.flag_uses:
                if native == "global":
                    self.diag("warning", line, f'global("{flag}") outside startup.cmb\'s RegistGlobalFlags: '
                              "the name would point into a script that is unloaded with the chapter")
        known = registered | set(globals_)
        for native, flag, line in self.flag_uses:
            if native in ("set", "get", "clr") and flag not in known:
                effect = "always returns 0" if native == "get" else "does nothing"
                self.diag("warning", line, f'{native}("{flag}") {effect}: no regist("{flag}") in this script '
                          "and no global flag has that name")
        if "Startup" in lines:
            locals_ = event_flags.local_flags(self.module)
            seen: set[str] = set()
            for flag in locals_:
                if flag in seen:
                    self.diag("warning", lines["Startup"], f'regist("{flag}") runs twice: the second '
                              "copy uses up a slot nothing can reach")
                seen.add(flag)
            problem = event_flags.capacity_problem(len(globals_), len(locals_))
            if problem:
                self.diag("warning", lines["Startup"], problem)

    def run(self) -> ScriptFile:
        seen = set()
        for fd in self.module.functions:
            if fd.name in seen:
                self.diag("error", fd.line, f"Function {fd.name!r} defined twice")
            seen.add(fd.name)
        exports = {}
        for fd in self.module.functions:
            name = self.export_name(fd)
            if name is not None:
                if name in exports:
                    self.diag("error", fd.line, f"Two functions export the name {name!r}")
                exports[name] = fd

        functions = []
        for i, fd in enumerate(self.module.functions):
            known = {"export", "naked", "trigger"} | set(TRIGGERS_BY_DECORATOR)
            for d in fd.decorators:
                if d.name not in known:
                    self.diag("error", d.line, f"Unknown decorator @{d.name}")
            fc = _FunctionCompiler(self, fd)
            naked = any(d.name == "naked" for d in fd.decorators)
            code = fc.run(naked)
            fn_type, params = self.trigger(fd)
            fn = Function(
                id_string=self.export_name(fd),
                type=fn_type,
                num_args=len(fd.params),
                num_vars=fc.next_slot,
                params=params,
                code=code,
                index=i,
            )
            if self.base is not None and i < len(self.base.functions):
                old = self.base.functions[i]
                fn.raw_reserved_0f = old.raw_reserved_0f
                fn.raw_parent_word = old.raw_parent_word
                fn.raw_id_tail = old.raw_id_tail
                fn.raw_params_pad = old.raw_params_pad
                fn.raw_code_pad = old.raw_code_pad
            functions.append(fn)
        self.check_flags()

        # Global opcodes index the engine's one 32-slot table by absolute slot; the header's
        # reservation (vanilla: highest slot + 1) only counts against that budget at load.
        for g in self.module.globals:
            if not 0 <= g.slot < GLOBAL_TABLE_SLOTS:
                self.diag("error", g.line, f"global {g.name} @ {g.slot}: the engine's global table has "
                          f"slots 0-{GLOBAL_TABLE_SLOTS - 1} only")
        needed = max((g.slot + 1 for g in self.module.globals), default=0)
        if self.base is not None:
            header = self.base.header
            reserved = int.from_bytes(header[0x22:0x24], "little")
            if needed > reserved:
                header = header[:0x22] + needed.to_bytes(2, "little") + header[0x24:]
            tail, tail_entries = self.base.raw_pool_tail, self.base.raw_pool_tail_entries
        else:
            header = default_header("script.cmb", needed)
            tail, tail_entries = b"\x00", -1
        return ScriptFile(
            header=header, pool=self.pool.entries, functions=functions,
            raw_pool_tail=tail, raw_pool_tail_entries=tail_entries,
        )


def default_header(file_name: str, global_count: int = 0) -> bytes:
    name = file_name.encode("ascii", "replace")[:19]
    head = (b"cmb\x00" + name + b"\x00").ljust(0x18, b"\x00")
    return head + (0x20041125).to_bytes(4, "little") + b"\x00" * 6 + global_count.to_bytes(2, "little")


def compile_module(module: A.Module, base: Optional[ScriptFile] = None,
                   known_script_functions: Optional[dict] = None,
                   global_flags: Optional[list] = None) -> CompileResult:
    mc = _ModuleCompiler(module, base, known_script_functions or {}, global_flags)
    script = mc.run()
    if any(d.severity == "error" for d in mc.diagnostics):
        raise CompileError(mc.diagnostics)
    return CompileResult(script, mc.diagnostics)


def compile_source(source: str, base: Optional[ScriptFile] = None,
                   known_script_functions: Optional[dict] = None,
                   global_flags: Optional[list] = None) -> CompileResult:
    """``global_flags``: the project's global flag names in slot order (see
    ``event_flags.global_flags``); vanilla's when omitted."""
    try:
        module = parse(source)
    except ParseError as e:
        raise CompileError([Diagnostic("error", e.line, e.message)]) from None
    return compile_module(module, base, known_script_functions, global_flags)
