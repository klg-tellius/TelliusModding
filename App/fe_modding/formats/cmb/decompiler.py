"""Decompile a :class:`~.model.ScriptFile` to ``.fe9s`` source.

Every function is decompiled in the most readable form that provably
round-trips: the result is compiled back and compared byte-for-byte with
the original code. The forms, best first:

1. ``structured`` - if/elif/else, while, break/continue, and/or.
2. ``goto`` - same statements and expressions, but control flow as labels
   and ``goto L`` / ``goto L unless cond`` / ``goto L if cond``.
3. ``asm`` - the raw instructions in an ``asm:`` block (``@naked``).

So decompile -> compile is always lossless.
"""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field
from typing import Optional

from . import ast as A
from .binary import _encode_code, _pool_layout
from .catalog import TRIGGERS
from .compiler import (
    BINARY_OPS,
    RESERVED_CALLS,
    UNARY_OPS,
    CompileError,
    _FunctionCompiler,
    _ModuleCompiler,
)
from .model import (
    BRANCH_OPS,
    EXTERN_CALL,
    LOCAL_CALL,
    OPCODES,
    PUSH_OPS,
    PUSHSTR_OPS,
    Function,
    Instr,
    Label,
    RawStr,
    ScriptFile,
    var_op_info,
)
from .parser import KEYWORDS

_OP_TO_BINARY = {v: k for k, v in BINARY_OPS.items()}
_OP_TO_UNARY = {v: k for k, v in UNARY_OPS.items()}
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GLOBAL_NAME = re.compile(r"^g(_m)?\d+$")


class _Fail(Exception):
    pass


@dataclass
class _Deref:
    addr: A.AddrOf


@dataclass
class _DoCond:
    """The `branchnz` back to a do-while's top, found at the end of its body."""
    cond: object


@dataclass
class _AssignExpr:
    target: object
    value: object
    op: Optional[str]


def is_identifier(text: str) -> bool:
    return bool(_IDENT.match(text)) and text not in KEYWORDS and not keyword.iskeyword(text)


@dataclass
class DecompileStats:
    structured: int = 0
    goto: int = 0
    asm: int = 0
    asm_functions: list = field(default_factory=list)


class _Names:
    """Def names, and which call names need the extern("...") form."""

    def __init__(self, script: ScriptFile):
        self.defs: list[str] = []
        taken = set()
        ids = {fn.id_string for fn in script.functions if fn.id_string}
        for i, fn in enumerate(script.functions):
            name = fn.id_string
            if not (name and is_identifier(name) and name not in taken and name not in RESERVED_CALLS):
                name = f"func_{i}"
                while name in taken or name in ids:
                    name += "_"
            taken.add(name)
            self.defs.append(name)
        self.def_set = set(self.defs)

    def extern_needs_quotes(self, name) -> bool:
        return not isinstance(name, str) or not is_identifier(name) or name in self.def_set or name in RESERVED_CALLS


def var_name(fn: Function, slot: int, is_global: bool) -> str:
    if is_global:
        return f"g{slot}" if slot >= 0 else f"g_m{-slot}"
    if 0 <= slot < fn.num_args:
        return f"arg{slot}"
    return f"v{slot}" if slot >= 0 else f"v_m{-slot}"


class _Builder:
    """Turns one function's code into statements (structured or goto form)."""

    def __init__(self, fn: Function, code: list, names: _Names, functions: list, structured: bool):
        self.fn = fn
        self.code = code
        self.names = names
        self.functions = functions
        self.structured = structured
        self.index = {id(x): i for i, x in enumerate(code) if isinstance(x, Label)}
        self.back: dict[int, list[int]] = {}      # label -> backward `branch`es (while)
        self.back_nz: dict[int, list[int]] = {}   # label -> backward `branchnz`es (do-while)
        for i, x in enumerate(code):
            if isinstance(x, Instr) and x.op in (0x3A, 0x3B):
                target = self.index[id(x.operands[0])]
                if target <= i:
                    table = self.back if x.op == 0x3A else self.back_nz
                    table.setdefault(id(x.operands[0]), []).append(i)
        self.label_names: dict[int, str] = {}

    def label_name(self, label: Label) -> str:
        return self.label_names.setdefault(id(label), f"L{len(self.label_names) + 1}")

    # -- expressions --
    def step(self, i: int, stack: list, stop: Optional[int]) -> int:
        """Apply one expression-building instruction; return the next index."""
        ins = self.code[i]
        op = ins.op
        info = var_op_info(op)
        if op in PUSH_OPS:
            v = ins.operands[0]
            stack.append(A.Num(v, raw=v < 0))
        elif op in PUSHSTR_OPS:
            v = ins.operands[0]
            stack.append(A.StrOffset(v.offset) if isinstance(v, RawStr) else A.Str(v))
        elif info is not None:
            mode, is_global, _ = info
            name = A.Name(var_name(self.fn, ins.operands[0], is_global))
            if mode == "pushvar":
                stack.append(name)
            elif mode == "pusharray":
                stack.append(A.Index(name, self.pop(stack)))
            elif mode == "pushaddr":
                stack.append(A.AddrOf(name))
            elif mode == "pushaddrarray":
                stack.append(A.AddrOf(A.Index(name, self.pop(stack))))
            else:
                raise _Fail(f"{OPCODES[op]} isn't expressible")
        elif op == 0x21:  # store: [addr, value] -> [value]
            value, addr = self.pop(stack), self.pop(stack)
            if not isinstance(addr, A.AddrOf):
                raise _Fail("store to a non-address")
            # x op= e compiles to: pushaddr x; deref; e; op; store
            if isinstance(value, A.BinOp) and isinstance(value.left, _Deref) and value.left.addr is addr:
                stack.append(_AssignExpr(addr.target, self.clean(value.right), value.op))
            else:
                stack.append(A.Walrus(addr.target, self.clean(value)))
        elif op == 0x1F:  # deref: [addr] -> [addr, *addr]
            if not stack or not isinstance(stack[-1], A.AddrOf):
                raise _Fail("deref of a non-address")
            stack.append(_Deref(stack[-1]))
        elif OPCODES[op] in _OP_TO_BINARY:
            b, a = self.pop(stack), self.pop(stack)
            stack.append(A.BinOp(_OP_TO_BINARY[OPCODES[op]], a, b))
        elif op in (0x35, 0x36):
            b, a = self.pop(stack), self.pop(stack)
            stack.append(A.Call(OPCODES[op], [a, b]))
        elif OPCODES[op] in _OP_TO_UNARY:
            stack.append(A.UnOp(_OP_TO_UNARY[OPCODES[op]], self.pop(stack)))
        elif op == EXTERN_CALL:
            name, argc = ins.operands
            args = self.pop_n(stack, argc)
            if isinstance(name, RawStr):
                stack.append(A.Call(A.StrOffset(name.offset), args, extern=True))
            else:
                stack.append(A.Call(name, args, extern=self.names.extern_needs_quotes(name)))
        elif op == LOCAL_CALL:
            idx = ins.operands[0]
            if not 0 <= idx < len(self.functions):
                raise _Fail("localCall to a missing function")
            args = self.pop_n(stack, self.functions[idx].num_args)
            stack.append(A.Call(self.names.defs[idx], args))
        elif op in (0x3C, 0x3E):  # branchkeepz (or) / branchkeepnz (and)
            left = self.pop(stack)
            target = self.index[id(ins.operands[0])]
            if target <= i:
                raise _Fail("backward short-circuit")
            right = self.subexpr(i + 1, target)
            stack.append(A.BoolOp("or" if op == 0x3C else "and", left, right))
            return target if target == stop else target + 1
        else:
            raise _Fail(f"{OPCODES[op]} in an expression")
        return i + 1

    def subexpr(self, start: int, stop: int):
        stack: list = []
        i = start
        while i < stop:
            if isinstance(self.code[i], Label):
                raise _Fail("label inside an expression")
            i = self.step(i, stack, stop)
        if len(stack) != 1:
            raise _Fail("short-circuit operand isn't one value")
        return self.clean(stack[0])

    @staticmethod
    def pop(stack: list):
        if not stack:
            raise _Fail("stack underflow")
        return stack.pop()

    def pop_n(self, stack: list, n: int) -> list:
        if len(stack) < n:
            raise _Fail("stack underflow")
        args = stack[len(stack) - n:] if n else []
        del stack[len(stack) - n:]
        return [self.clean(a) for a in args]

    def clean(self, e):
        """Reject internal nodes that can't be written as source."""
        if isinstance(e, (_Deref, _AssignExpr)):
            raise _Fail("assignment used as a value")
        for child in _children(e):
            self.clean(child)
        return e

    # -- statements --
    def statement(self, i: int, end: int, loop, out: list) -> int:
        stack: list = []
        while True:
            if i >= end or isinstance(self.code[i], Label):
                self.flush(stack, 0, out)
                return i
            ins = self.code[i]
            op = ins.op
            if op == 0x20:  # pop: the value of an expression statement
                self.flush(stack, 1, out)
                e = stack.pop()
                if isinstance(e, _AssignExpr):
                    out.append(A.Assign(e.target, e.value, e.op))
                elif isinstance(e, A.Walrus):
                    out.append(A.Assign(e.target, e.value))
                elif isinstance(e, A.Call):
                    out.append(A.ExprStmt(self.clean(e)))
                else:
                    raise _Fail("non-call expression statement")
                return i + 1
            if op == 0x41:  # printf
                self.flush(stack, ins.operands[0], out)
                out.append(A.Printf(self.pop_n(stack, ins.operands[0])))
                return i + 1
            if op == 0x3F:
                self.flush(stack, 0, out)
                out.append(A.Yield())
                return i + 1
            if op == 0x39:
                self.flush(stack, 1, out)
                out.append(A.Return(self.clean(stack.pop())))
                return i + 1
            if op in (0x3A, 0x3B, 0x3D):
                self.flush(stack, 0 if op == 0x3A else 1, out)
                cond = self.clean(stack.pop()) if op != 0x3A else None
                if self.structured and op == 0x3B and loop and len(loop) == 3 and ins.operands[0] is loop[2]:
                    out.append(_DoCond(cond))
                    return i + 1
                if self.structured:
                    return self.structured_branch(i, end, loop, out, cond)
                label = self.label_name(ins.operands[0])
                when = {0x3A: None, 0x3B: "if", 0x3D: "unless"}[op]
                out.append(A.Goto(label, cond, when))
                return i + 1
            i = self.step(i, stack, None)

    def flush(self, stack: list, keep: int, out: list) -> None:
        """Values a statement leaves beneath the ones it consumes can only be
        `var x = e` declarations (vanilla never pops those)."""
        if len(stack) < keep:
            raise _Fail("stack underflow")
        leaked = stack[:len(stack) - keep]
        del stack[:len(stack) - keep]
        for e in leaked:
            if not (isinstance(e, A.Walrus) and isinstance(e.target, A.Name) and not _GLOBAL_NAME.match(e.target.id)):
                raise _Fail("value left on the stack")
            out.append(A.VarInit(e.target.id, self.clean(e.value)))

    def structured_branch(self, i: int, end: int, loop, out: list, cond) -> int:
        ins = self.code[i]
        target = self.index[id(ins.operands[0])]
        if ins.op == 0x3A:
            if loop and ins.operands[0] is loop[1]:
                out.append(A.Break())
            elif loop and ins.operands[0] is loop[0]:
                out.append(A.Continue())
            else:
                raise _Fail("unstructured branch")
            return i + 1
        if ins.op != 0x3D or not i < target <= end:
            raise _Fail("unstructured conditional branch")
        prev = self.code[target - 1]
        if isinstance(prev, Instr) and prev.op == 0x3A and not (loop and prev.operands[0] in loop):
            else_end = self.index[id(prev.operands[0])]
            if target < else_end <= end:
                body = self.block(i + 1, target - 1, loop)
                orelse = self.block(target, else_end, loop) or [A.Pass()]
                out.append(A.If(cond, body, orelse))
                return else_end
            if else_end == target:
                # A jump to the very next label: either the last statement of
                # the body is an if/else nested inside it, or this if has an
                # empty `else: pass`, which still compiles to that jump.
                try:
                    body = self.block(i + 1, target, loop)
                except _Fail:
                    body = self.block(i + 1, target - 1, loop)
                    out.append(A.If(cond, body, [A.Pass()]))
                    return target
                out.append(A.If(cond, body, []))
                return target
        out.append(A.If(cond, self.block(i + 1, target, loop), []))
        return target

    def block(self, start: int, end: int, loop) -> list:
        out: list = []
        i = start
        while i < end:
            item = self.code[i]
            if isinstance(item, Label):
                if not self.structured:
                    out.append(A.LabelStmt(self.label_name(item)))
                    i += 1
                    continue
                backs = [b for b in self.back.get(id(item), []) if b < end]
                if backs:
                    b = max(backs)
                    end_label = self.code[b + 1] if b + 1 < len(self.code) and isinstance(self.code[b + 1], Label) else None
                    cond, body_start = self.loop_condition(i + 1, b, end_label)
                    body = self.block(body_start, b, (item, end_label))
                    out.append(A.While(cond, body))
                    i = b + 1
                    continue
                backs = [b for b in self.back_nz.get(id(item), []) if b < end]
                if backs:
                    b = max(backs)
                    end_label = self.code[b + 1] if b + 1 < len(self.code) and isinstance(self.code[b + 1], Label) else None
                    # `continue` would jump to an unnamed label before the
                    # condition; vanilla never does, so it isn't recognised
                    body = self.block(i + 1, b + 1, (Label(), end_label, item))
                    if not body or not isinstance(body[-1], _DoCond):
                        raise _Fail("do-while without a trailing condition")
                    out.append(A.DoWhile(body[:-1], body[-1].cond))
                    i = b + 1
                    continue
                i += 1
                continue
            i = self.statement(i, end, loop, out)
        return out

    def loop_condition(self, start: int, stop: int, end_label):
        if end_label is None:
            return None, start
        stack: list = []
        i = start
        try:
            while i < stop and isinstance(self.code[i], Instr):
                ins = self.code[i]
                if ins.op == 0x3D and ins.operands[0] is end_label and len(stack) == 1:
                    return self.clean(stack[0]), i + 1
                i = self.step(i, stack, None)
        except _Fail:
            pass
        return None, start


def _children(e) -> list:
    if isinstance(e, (A.BinOp, A.BoolOp)):
        return [e.left, e.right]
    if isinstance(e, A.UnOp):
        return [e.operand]
    if isinstance(e, A.Index):
        return [e.index]
    if isinstance(e, A.AddrOf):
        return [e.target]
    if isinstance(e, A.Call):
        return list(e.args)
    if isinstance(e, A.Walrus):
        return [e.target, e.value]
    return []


# -- asm form ---------------------------------------------------------------


def _asm_body(code: list) -> list:
    names: dict[int, str] = {}

    def name(label):
        return names.setdefault(id(label), f"L{len(names) + 1}")

    lines = []
    for item in code:
        if isinstance(item, Label):
            lines.append((None, [], name(item), 0))
            continue
        ops = []
        for value in item.operands:
            if isinstance(value, Label):
                ops.append(("label", name(value)))
            elif isinstance(value, RawStr):
                ops.append(value.offset)
            else:
                ops.append(value)
        lines.append((item.name, ops, None, 0))
    return [A.Asm(lines)]


# -- whole-function decompilation ---------------------------------------------


def _trigger_decorator(fn: Function, pool_text: dict) -> Optional[A.Decorator]:
    kind = TRIGGERS.get(fn.type)
    if fn.type == 0 and not fn.params:
        return None
    if kind is None or fn.type == 0 or len(fn.params) != len(kind.params):
        args = [A.Num(fn.type)] + [A.Num(p) for p in fn.params]
        return A.Decorator("trigger", args, {})
    kwargs = {}
    for spec, value in zip(kind.params, fn.params):
        if spec.is_label:
            if value == 0:
                kwargs[spec.name] = A.Name("None")
            elif value in pool_text:
                kwargs[spec.name] = A.Str(pool_text[value])
            else:
                kwargs[spec.name] = A.Num(value)
        elif spec.enum and value in spec.enum:
            kwargs[spec.name] = A.Str(spec.enum[value])
        else:
            kwargs[spec.name] = A.Num(value)
    return A.Decorator(kind.decorator, [], kwargs)


class Decompiler:
    def __init__(self, script: ScriptFile, known_script_functions: Optional[dict] = None):
        self.script = script
        self.names = _Names(script)
        self.known = known_script_functions or {}
        _, self.offsets = _pool_layout(script)
        self.pool_text = {}
        for text, off in self.offsets.items():
            self.pool_text.setdefault(off, text)
        self.stats = DecompileStats()
        self.globals = sorted({
            ins.operands[0]
            for fn in script.functions for ins in fn.instructions()
            if var_op_info(ins.op) and var_op_info(ins.op)[1]
        })

    def module(self) -> A.Module:
        functions = []
        for i, fn in enumerate(self.script.functions):
            functions.append(self.function(i, fn))
        globals_ = [A.GlobalDecl(var_name(None, s, True), s) for s in self.globals]
        return A.Module(globals_, functions)

    def _skeleton(self) -> A.Module:
        return A.Module(
            [A.GlobalDecl(var_name(None, s, True), s) for s in self.globals],
            [A.FuncDef(self.names.defs[i], [f"arg{k}" for k in range(fn.num_args)], [], [])
             for i, fn in enumerate(self.script.functions)],
        )

    def function(self, i: int, fn: Function) -> A.FuncDef:
        decorators = []
        if fn.id_string is not None:
            if self.names.defs[i] == fn.id_string:
                decorators.append(A.Decorator("export", [], {}))
            else:
                decorators.append(A.Decorator("export", [A.Str(fn.id_string)], {}))
        trig = _trigger_decorator(fn, self.pool_text)
        if trig is not None:
            decorators.append(trig)
        params = [f"arg{k}" for k in range(fn.num_args)]
        locals_ = [(var_name(fn, s, False), 1) for s in range(fn.num_args, fn.num_vars)]
        header = [A.VarDecl(locals_)] if locals_ else []

        code = fn.code
        has_epilogue = (len(code) >= 2 and isinstance(code[-1], Instr) and code[-1].op == 0x39
                        and isinstance(code[-2], Instr) and code[-2].op == 0x19 and code[-2].operands == [0])
        attempts = []
        if has_epilogue:
            attempts += [("structured", code[:-2], True, False), ("goto", code[:-2], False, False)]
        attempts.append(("goto", code, False, True))
        for form, body_code, structured, naked in attempts:
            try:
                builder = _Builder(fn, body_code, self.names, self.script.functions, structured)
                body = builder.block(0, len(body_code), None)
            except _Fail:
                continue
            decos = decorators + ([A.Decorator("naked", [], {})] if naked else [])
            # Locals are declared implicitly by their first assignment, so the
            # upfront `var` list is only kept when slot order needs it.
            for head in ([], header) if header else ([],):
                fd = A.FuncDef(self.names.defs[i], params, head + body, decos)
                if self._verify(i, fd, fn):
                    setattr(self.stats, form, getattr(self.stats, form) + 1)
                    return fd
        self.stats.asm += 1
        self.stats.asm_functions.append(i)
        return A.FuncDef(self.names.defs[i], params, header + _asm_body(code),
                         decorators + [A.Decorator("naked", [], {})])

    def _verify(self, i: int, fd: A.FuncDef, fn: Function) -> bool:
        skeleton = self._skeleton()
        skeleton.functions[i] = fd
        mc = _ModuleCompiler(skeleton, self.script, self.known)
        try:
            fc = _FunctionCompiler(mc, fd)
            code = fc.run(any(d.name == "naked" for d in fd.decorators))
        except Exception:
            return False
        if any(d.severity == "error" for d in mc.diagnostics) or fc.next_slot != fn.num_vars:
            return False
        try:
            return _encode_code(code, self.offsets) == _encode_code(fn.code, self.offsets)
        except Exception:
            return False


# -- printing ---------------------------------------------------------------

_PREC = {"or": 1, "and": 2, "not": 3, "==": 4, "!=": 4, "<": 4, "<=": 4, ">": 4, ">=": 4,
         "|": 5, "^": 6, "&": 7, "<<": 8, ">>": 8, "+": 9, "-": 9, "*": 10, "/": 10, "%": 10}
_UNARY_PREC = 11
_ATOM = 12


def _prec(e) -> int:
    if isinstance(e, (A.BinOp, A.BoolOp)):
        return _PREC[e.op]
    if isinstance(e, A.UnOp):
        return 3 if e.op == "not" else _UNARY_PREC
    if isinstance(e, A.AddrOf):
        return _UNARY_PREC
    return _ATOM


def quote(text: str) -> str:
    out = ['"']
    for ch in text:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def expr_to_source(e) -> str:
    if isinstance(e, A.Num):
        return f"lit({e.value})" if e.raw else str(e.value)
    if isinstance(e, A.Str):
        return quote(e.value)
    if isinstance(e, A.StrOffset):
        return f"strofs({e.offset})"
    if isinstance(e, A.Name):
        return e.id
    if isinstance(e, A.Index):
        return f"{e.base.id}[{expr_to_source(e.index)}]"
    if isinstance(e, A.AddrOf):
        return "&" + expr_to_source(e.target)
    if isinstance(e, (A.BinOp, A.BoolOp)):
        p = _PREC[e.op]
        left, right = expr_to_source(e.left), expr_to_source(e.right)
        compare = p == 4
        if _prec(e.left) < p or (compare and _prec(e.left) <= p):
            left = f"({left})"
        if _prec(e.right) <= p:
            right = f"({right})"
        return f"{left} {e.op} {right}"
    if isinstance(e, A.UnOp):
        inner = expr_to_source(e.operand)
        if e.op == "not":
            if _prec(e.operand) < 3:
                inner = f"({inner})"
            return f"not {inner}"
        if _prec(e.operand) < _UNARY_PREC or (isinstance(e.operand, A.Num) and e.operand.raw):
            inner = f"({inner})"
        return f"{e.op}{inner}"
    if isinstance(e, A.Walrus):
        return f"({expr_to_source(e.target)} := {expr_to_source(e.value)})"
    if isinstance(e, A.Call):
        args = [expr_to_source(a) for a in e.args]
        if e.extern:
            target = quote(e.name) if isinstance(e.name, str) else expr_to_source(e.name)
            return f"extern({', '.join([target] + args)})"
        return f"{e.name}({', '.join(args)})"
    raise TypeError(e)


def _decorator_source(d: A.Decorator) -> str:
    parts = [expr_to_source(a) for a in d.args] + [f"{k}={expr_to_source(v)}" for k, v in d.kwargs.items()]
    return f"@{d.name}({', '.join(parts)})" if parts else f"@{d.name}"


def stmts_to_source(stmts: list, indent: int) -> list[str]:
    pad = "    " * indent
    lines: list[str] = []
    for s in stmts:
        if isinstance(s, A.ExprStmt):
            lines.append(pad + expr_to_source(s.expr))
        elif isinstance(s, A.Assign):
            lines.append(f"{pad}{expr_to_source(s.target)} {s.op or ''}= {expr_to_source(s.value)}")
        elif isinstance(s, A.VarDecl):
            lines.append(pad + "var " + ", ".join(n if size == 1 else f"{n}[{size}]" for n, size in s.names))
        elif isinstance(s, A.VarInit):
            lines.append(f"{pad}var {s.name} = {expr_to_source(s.value)}")
        elif isinstance(s, A.Printf):
            lines.append(f"{pad}printf({', '.join(expr_to_source(a) for a in s.args)})")
        elif isinstance(s, A.Yield):
            lines.append(pad + "yield")
        elif isinstance(s, A.Pass):
            lines.append(pad + "pass")
        elif isinstance(s, A.Return):
            lines.append(pad + "return" + ("" if s.value is None else " " + expr_to_source(s.value)))
        elif isinstance(s, A.If):
            keyword_ = "if"
            node = s
            while True:
                lines.append(f"{pad}{keyword_} {expr_to_source(node.cond)}:")
                lines.extend(stmts_to_source(node.body, indent + 1) or [pad + "    pass"])
                if len(node.orelse) == 1 and isinstance(node.orelse[0], A.If):
                    node = node.orelse[0]
                    keyword_ = "elif"
                    continue
                if node.orelse:
                    lines.append(pad + "else:")
                    lines.extend(stmts_to_source(node.orelse, indent + 1))
                break
        elif isinstance(s, A.While):
            lines.append(f"{pad}while {'True' if s.cond is None else expr_to_source(s.cond)}:")
            lines.extend(stmts_to_source(s.body, indent + 1) or [pad + "    pass"])
        elif isinstance(s, A.DoWhile):
            lines.append(pad + "do:")
            lines.extend(stmts_to_source(s.body, indent + 1) or [pad + "    pass"])
            lines.append(f"{pad}while {expr_to_source(s.cond)}")
        elif isinstance(s, A.Break):
            lines.append(pad + "break")
        elif isinstance(s, A.Continue):
            lines.append(pad + "continue")
        elif isinstance(s, A.Goto):
            tail = "" if s.when is None else f" {s.when} {expr_to_source(s.cond)}"
            lines.append(f"{pad}goto {s.label}{tail}")
        elif isinstance(s, A.LabelStmt):
            lines.append(f"{pad}{s.name}:")
        elif isinstance(s, A.Asm):
            lines.append(pad + "asm:")
            for opname, operands, label, _ in s.lines:
                if label is not None:
                    lines.append(f"{pad}    {label}:")
                    continue
                ops = []
                for v in operands:
                    if isinstance(v, tuple):
                        ops.append(v[1])
                    elif isinstance(v, str):
                        ops.append(quote(v))
                    else:
                        ops.append(str(v))
                lines.append(f"{pad}    {opname}" + (" " + ", ".join(ops) if ops else ""))
        else:  # pragma: no cover
            raise TypeError(s)
    return lines


def function_to_source(fd: A.FuncDef, comment: Optional[str] = None) -> list[str]:
    lines = []
    if comment:
        lines.extend(f"# {c}" for c in comment.splitlines())
    lines.extend(_decorator_source(d) for d in fd.decorators)
    lines.append(f"def {fd.name}({', '.join(fd.params)}):")
    lines.extend(stmts_to_source(fd.body, 1) or ["    pass"])
    return lines


def module_to_source(module: A.Module, header_comment: Optional[str] = None, comments: Optional[dict] = None) -> str:
    lines = []
    if header_comment:
        lines.extend(f"# {c}" for c in header_comment.splitlines())
        lines.append("")
    for g in module.globals:
        lines.append(f"global {g.name} @ {g.slot}")
    if module.globals:
        lines.append("")
    for i, fd in enumerate(module.functions):
        lines.append("")
        lines.extend(function_to_source(fd, (comments or {}).get(i)))
    return "\n".join(lines).lstrip("\n") + "\n"


def decompile(script: ScriptFile, file_name: str = "", known_script_functions: Optional[dict] = None):
    """Return ``(source, stats)``."""
    d = Decompiler(script, known_script_functions)
    module = d.module()
    comments = {}
    for i, fn in enumerate(script.functions):
        kind = TRIGGERS.get(fn.type)
        text = f"function {i}"
        if kind is not None and fn.type != 0:
            text += f" - {kind.title}"
        comments[i] = text
    header = f"Decompiled from {file_name}" if file_name else None
    return module_to_source(module, header, comments), d.stats
