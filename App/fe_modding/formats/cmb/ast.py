"""Syntax tree for the ``.fe9s`` script language (shared by the parser,
compiler, decompiler and printer)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

# -- expressions ------------------------------------------------------------


@dataclass
class Num:
    value: int
    raw: bool = False  # lit(n): pushed as-is, even if negative


@dataclass
class Str:
    value: str


@dataclass
class StrOffset:
    """strofs(n): a string operand that doesn't point at a pool entry."""

    offset: int


@dataclass
class Name:
    id: str


@dataclass
class Index:
    base: Name
    index: "Expr"


@dataclass
class AddrOf:
    target: Union[Name, Index]


@dataclass
class BinOp:
    op: str  # + - * / % | & ^ << >> == != < <= > >=
    left: "Expr"
    right: "Expr"


@dataclass
class BoolOp:
    op: str  # and / or (short-circuit)
    left: "Expr"
    right: "Expr"


@dataclass
class UnOp:
    op: str  # - ~ not
    operand: "Expr"


@dataclass
class Call:
    name: Union[str, StrOffset]
    args: list
    extern: bool = False  # extern("Name", ...): force an externCall even if a local def has that name


@dataclass
class Walrus:
    """(x := e): assign and use the value (vanilla ``while (u = f()) ...``)."""

    target: Union[Name, Index]
    value: "Expr"


Expr = Union[Walrus, Num, Str, StrOffset, Name, Index, AddrOf, BinOp, BoolOp, UnOp, Call]

# -- statements -------------------------------------------------------------


@dataclass
class Stmt:
    line: int = field(default=0, kw_only=True)


@dataclass
class ExprStmt(Stmt):
    expr: Expr


@dataclass
class Assign(Stmt):
    target: Union[Name, Index]
    value: Expr
    op: Optional[str] = None  # augmented assignment operator (+, -, ...)


@dataclass
class VarDecl(Stmt):
    names: list  # [(name, size)]


@dataclass
class VarInit(Stmt):
    name: str
    value: Expr


@dataclass
class Printf(Stmt):
    args: list


@dataclass
class Yield(Stmt):
    pass


@dataclass
class Pass(Stmt):
    pass


@dataclass
class Return(Stmt):
    value: Optional[Expr]


@dataclass
class If(Stmt):
    cond: Expr
    body: list
    orelse: list


@dataclass
class While(Stmt):
    cond: Optional[Expr]  # None = `while True:` (no condition code at all)
    body: list


@dataclass
class DoWhile(Stmt):
    body: list
    cond: Expr  # checked after each pass: `do:` ... `while cond`


@dataclass
class Break(Stmt):
    pass


@dataclass
class Continue(Stmt):
    pass


@dataclass
class Goto(Stmt):
    label: str
    cond: Optional[Expr] = None
    when: Optional[str] = None  # "if" / "unless"


@dataclass
class LabelStmt(Stmt):
    name: str


@dataclass
class Asm(Stmt):
    lines: list  # [(opcode_name | None, operands, label_name | None, line)]


# -- module -----------------------------------------------------------------


@dataclass
class Decorator:
    name: str
    args: list
    kwargs: dict
    line: int = 0


@dataclass
class FuncDef:
    name: str
    params: list
    body: list
    decorators: list
    line: int = 0


@dataclass
class GlobalDecl:
    name: str
    slot: int
    line: int = 0


@dataclass
class Module:
    globals: list
    functions: list
