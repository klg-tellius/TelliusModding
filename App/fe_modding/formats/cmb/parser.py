"""Lexer and recursive-descent parser for the ``.fe9s`` script language.

The language is Python-shaped (indentation blocks, ``#`` comments, ``def``,
``if``/``elif``/``else``, ``while``, ``and``/``or``/``not``) with a few
additions a stack VM needs: ``var`` declarations, ``global name @ slot``,
labels/``goto`` and an ``asm:`` escape hatch, plus ``switch``/``case`` and
``++``/``--`` for Radiant Dawn's compiler idioms. See
``docs/app/script-language.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import ast as A


class ParseError(Exception):
    def __init__(self, message: str, line: int):
        super().__init__(f"line {line}: {message}")
        self.message = message
        self.line = line


@dataclass
class Token:
    kind: str  # NAME NUM STR OP NEWLINE INDENT DEDENT EOF
    value: object
    line: int


_TOKEN_RE = re.compile(
    r"""
    (?P<ws>[ \t]+)
  | (?P<comment>\#[^\n]*)
  | (?P<num>0[xX][0-9a-fA-F]+|\d+)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<str>"(?:[^"\\\n]|\\.)*")
  | (?P<op>:=|<<=|>>=|\*\*|\+\+|--|<<|>>|<=|>=|==|!=|\+=|-=|\*=|/=|%=|&=|\|=|\^=|[-+*/%&|^~<>=()\[\],:@.;])
    """,
    re.VERBOSE,
)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "0": "\0"}


def unescape(body: str, line: int) -> str:
    out = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        nxt = body[i + 1]
        if nxt in _ESCAPES:
            out.append(_ESCAPES[nxt])
            i += 2
        elif nxt == "x":
            out.append(chr(int(body[i + 2:i + 4], 16)))
            i += 4
        elif nxt == "u":
            out.append(chr(int(body[i + 2:i + 6], 16)))
            i += 6
        else:
            raise ParseError(f"Unknown escape \\{nxt}", line)
    return "".join(out)


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    indents = [0]
    depth = 0  # bracket nesting: newlines inside () [] are ignored
    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if depth == 0:
            if not stripped or stripped.startswith("#"):
                continue
            width = len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())
            if width > indents[-1]:
                indents.append(width)
                tokens.append(Token("INDENT", None, lineno))
            else:
                while width < indents[-1]:
                    indents.pop()
                    tokens.append(Token("DEDENT", None, lineno))
                if width != indents[-1]:
                    raise ParseError("Inconsistent indentation", lineno)
        pos = 0
        while pos < len(line):
            m = _TOKEN_RE.match(line, pos)
            if not m:
                raise ParseError(f"Unexpected character {line[pos]!r}", lineno)
            pos = m.end()
            kind = m.lastgroup
            text = m.group()
            if kind in ("ws", "comment"):
                continue
            if kind == "num":
                tokens.append(Token("NUM", int(text, 0), lineno))
            elif kind == "name":
                tokens.append(Token("NAME", text, lineno))
            elif kind == "str":
                tokens.append(Token("STR", unescape(text[1:-1], lineno), lineno))
            else:
                if text in "([":
                    depth += 1
                elif text in ")]":
                    depth = max(0, depth - 1)
                tokens.append(Token("OP", text, lineno))
        if depth == 0 and stripped and not stripped.startswith("#"):
            tokens.append(Token("NEWLINE", None, lineno))
    last = tokens[-1].line if tokens else 1
    while len(indents) > 1:
        indents.pop()
        tokens.append(Token("DEDENT", None, last))
    tokens.append(Token("EOF", None, last))
    return tokens


_COMPARE = ("==", "!=", "<", "<=", ">", ">=")
_BINARY_LEVELS = [("|",), ("^",), ("&",), ("<<", ">>"), ("+", "-"), ("*", "/", "%")]
AUG_OPS = {"+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="}
KEYWORDS = {
    "def", "if", "elif", "else", "while", "do", "break", "continue", "return", "yield", "pass",
    "var", "global", "goto", "unless", "asm", "and", "or", "not", "True", "False", "None",
    "switch", "case", "default",
}


class Parser:
    def __init__(self, source: str):
        self.tokens = tokenize(source)
        self.pos = 0

    # -- token helpers --
    @property
    def tok(self) -> Token:
        return self.tokens[self.pos]

    def peek(self, n: int = 1) -> Token:
        return self.tokens[min(self.pos + n, len(self.tokens) - 1)]

    def at(self, kind: str, value=None) -> bool:
        t = self.tok
        return t.kind == kind and (value is None or t.value == value)

    def at_op(self, value: str) -> bool:
        return self.at("OP", value)

    def at_kw(self, value: str) -> bool:
        return self.at("NAME", value)

    def take(self) -> Token:
        t = self.tok
        self.pos += 1
        return t

    def expect(self, kind: str, value=None) -> Token:
        if not self.at(kind, value):
            want = value if value is not None else kind
            got = self.tok.value if self.tok.value is not None else self.tok.kind
            raise ParseError(f"Expected {want!r}, found {got!r}", self.tok.line)
        return self.take()

    def expect_name(self) -> str:
        t = self.expect("NAME")
        if t.value in KEYWORDS:
            raise ParseError(f"{t.value!r} is a keyword", t.line)
        return t.value

    # -- module --
    def parse_module(self) -> A.Module:
        module = A.Module(globals=[], functions=[])
        while not self.at("EOF"):
            if self.at("NEWLINE"):
                self.take()
            elif self.at_kw("global"):
                line = self.take().line
                name = self.expect_name()
                self.expect("OP", "@")
                slot = self.expect("NUM").value
                self.expect("NEWLINE")
                module.globals.append(A.GlobalDecl(name, slot, line))
            elif self.at_op("@") or self.at_kw("def"):
                module.functions.append(self.parse_funcdef())
            else:
                raise ParseError("Expected a function definition or a global declaration", self.tok.line)
        return module

    def parse_funcdef(self) -> A.FuncDef:
        decorators = []
        while self.at_op("@"):
            line = self.take().line
            name = self.expect("NAME").value
            while self.at_op("."):
                self.take()
                name += "." + self.expect("NAME").value
            args, kwargs = [], {}
            if self.at_op("("):
                args, kwargs = self.parse_call_args(allow_kwargs=True)
            self.expect("NEWLINE")
            decorators.append(A.Decorator(name, args, kwargs, line))
        line = self.expect("NAME", "def").line
        name = self.expect_name()
        self.expect("OP", "(")
        params = []
        while not self.at_op(")"):
            params.append(self.expect_name())
            if not self.at_op(")"):
                self.expect("OP", ",")
        self.take()
        self.expect("OP", ":")
        body = self.parse_suite()
        return A.FuncDef(name, params, body, decorators, line)

    def parse_suite(self) -> list:
        if not self.at("NEWLINE"):
            return [self.parse_simple_stmt()]
        self.take()
        self.expect("INDENT")
        body = []
        while not self.at("DEDENT"):
            body.extend(self.parse_stmt())
        self.take()
        return body

    # -- statements --
    def parse_stmt(self) -> list:
        t = self.tok
        if t.kind == "NAME":
            if t.value == "if":
                return [self.parse_if()]
            if t.value == "while":
                self.take()
                if self.at_kw("True") and self.peek().kind == "OP" and self.peek().value == ":":
                    self.take()
                    cond = None
                else:
                    cond = self.parse_expr()
                self.expect("OP", ":")
                return [A.While(cond, self.parse_suite(), line=t.line)]
            if t.value == "do" and self.peek().kind == "OP" and self.peek().value == ":":
                self.take()
                self.take()
                body = self.parse_suite()
                self.expect("NAME", "while")
                cond = self.parse_expr()
                self.expect("NEWLINE")
                return [A.DoWhile(body, cond, line=t.line)]
            if t.value == "asm":
                return [self.parse_asm()]
            if t.value == "switch":
                return [self.parse_switch()]
            if self.peek().kind == "OP" and self.peek().value == ":" and t.value not in KEYWORDS \
                    and self.peek(2).kind == "NEWLINE":
                self.take()
                self.take()
                self.take()
                return [A.LabelStmt(t.value, line=t.line)]
        return [self.parse_simple_stmt()]

    def parse_if(self) -> A.If:
        line = self.take().line  # if / elif
        cond = self.parse_expr()
        self.expect("OP", ":")
        body = self.parse_suite()
        orelse = []
        if self.at_kw("elif"):
            orelse = [self.parse_if()]
        elif self.at_kw("else"):
            self.take()
            self.expect("OP", ":")
            orelse = self.parse_suite()
        return A.If(cond, body, orelse, line=line)

    def parse_switch(self) -> A.Switch:
        line = self.take().line
        value = self.parse_expr()
        self.expect("OP", ":")
        self.expect("NEWLINE")
        self.expect("INDENT")
        cases = []
        while not self.at("DEDENT"):
            t = self.tok
            if cases and not cases[-1].values:
                raise ParseError("'default:' must be the last branch of a switch", t.line)
            if self.at_kw("case"):
                self.take()
                values = [self.parse_expr()]
                while self.at_op(","):
                    self.take()
                    values.append(self.parse_expr())
            elif self.at_kw("default"):
                self.take()
                values = []
            else:
                raise ParseError("Expected 'case' or 'default' inside a switch", t.line)
            self.expect("OP", ":")
            cases.append(A.Case(values, self.parse_suite(), t.line))
        self.take()
        if not cases:
            raise ParseError("A switch needs at least one case", line)
        return A.Switch(value, cases, line=line)

    def parse_simple_stmt(self) -> A.Stmt:
        t = self.tok
        line = t.line
        stmt = None
        if t.kind == "NAME" and t.value in ("break", "continue", "yield", "pass"):
            self.take()
            stmt = {"break": A.Break, "continue": A.Continue, "yield": A.Yield, "pass": A.Pass}[t.value](line=line)
        elif self.at_kw("return"):
            self.take()
            value = None if self.at("NEWLINE") else self.parse_expr()
            stmt = A.Return(value, line=line)
        elif self.at_kw("goto"):
            self.take()
            label = self.expect_name()
            cond = when = None
            if self.at_kw("if") or self.at_kw("unless"):
                when = self.take().value
                cond = self.parse_expr()
            stmt = A.Goto(label, cond, when, line=line)
        elif self.at_kw("var"):
            stmt = self.parse_var()
        elif self.at_kw("printf") and self.peek().kind == "OP" and self.peek().value == "(":
            self.take()
            args, _ = self.parse_call_args()
            stmt = A.Printf(args, line=line)
        else:
            expr = self.parse_expr()
            if self.at_op("=") or (self.tok.kind == "OP" and self.tok.value in AUG_OPS):
                op = self.take().value
                if not isinstance(expr, (A.Name, A.Index)):
                    raise ParseError("Can only assign to a variable or an array element", line)
                value = self.parse_expr()
                stmt = A.Assign(expr, value, None if op == "=" else op[:-1], line=line)
            else:
                if not isinstance(expr, (A.Call, A.IncDec)):
                    raise ParseError("An expression statement must be a function call or ++/--", line)
                stmt = A.ExprStmt(expr, line=line)
        self.expect("NEWLINE")
        return stmt

    def parse_var(self) -> A.Stmt:
        line = self.take().line
        items = []
        while True:
            name = self.expect_name()
            size = 1
            if self.at_op("["):
                self.take()
                size = self.expect("NUM").value
                self.expect("OP", "]")
            if self.at_op("="):
                if items or size != 1:
                    raise ParseError("'var x = value' declares a single variable", line)
                self.take()
                return A.VarInit(name, self.parse_expr(), line=line)
            items.append((name, size))
            if not self.at_op(","):
                return A.VarDecl(items, line=line)
            self.take()

    def parse_asm(self) -> A.Asm:
        line = self.take().line
        self.expect("OP", ":")
        self.expect("NEWLINE")
        self.expect("INDENT")
        lines = []
        while not self.at("DEDENT"):
            t = self.expect("NAME")
            if self.at_op(":"):
                self.take()
                lines.append((None, [], t.value, t.line))
            else:
                operands = []
                while not self.at("NEWLINE"):
                    if self.at("NUM") or self.at("STR") or self.at("NAME"):
                        operands.append(self.take().value if not self.at("NAME") else ("label", self.take().value))
                    elif self.at_op("-"):
                        self.take()
                        operands.append(-self.expect("NUM").value)
                    else:
                        raise ParseError("Bad asm operand", self.tok.line)
                    if self.at_op(","):
                        self.take()
                lines.append((t.value, operands, None, t.line))
            self.expect("NEWLINE")
        self.take()
        return A.Asm(lines, line=line)

    # -- expressions --
    def parse_call_args(self, allow_kwargs: bool = False):
        self.expect("OP", "(")
        args, kwargs = [], {}
        while not self.at_op(")"):
            if allow_kwargs and self.tok.kind == "NAME" and self.peek().kind == "OP" and self.peek().value == "=":
                key = self.take().value
                self.take()
                kwargs[key] = self.parse_expr()
            else:
                args.append(self.parse_expr())
            if not self.at_op(")"):
                self.expect("OP", ",")
        self.take()
        return args, kwargs

    def parse_expr(self) -> A.Expr:
        return self.parse_or()

    def parse_or(self):
        left = self.parse_and()
        while self.at_kw("or"):
            self.take()
            left = A.BoolOp("or", left, self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.at_kw("and"):
            self.take()
            left = A.BoolOp("and", left, self.parse_not())
        return left

    def parse_not(self):
        if self.at_kw("not"):
            self.take()
            return A.UnOp("not", self.parse_not())
        return self.parse_compare()

    def parse_compare(self):
        left = self.parse_binary(0)
        if self.tok.kind == "OP" and self.tok.value in _COMPARE:
            op = self.take().value
            left = A.BinOp(op, left, self.parse_binary(0))
            if self.tok.kind == "OP" and self.tok.value in _COMPARE:
                raise ParseError("Chained comparisons aren't supported; use 'and'", self.tok.line)
        return left

    def parse_binary(self, level: int):
        if level == len(_BINARY_LEVELS):
            return self.parse_unary()
        left = self.parse_binary(level + 1)
        while self.tok.kind == "OP" and self.tok.value in _BINARY_LEVELS[level]:
            op = self.take().value
            left = A.BinOp(op, left, self.parse_binary(level + 1))
        return left

    def parse_unary(self):
        if self.tok.kind == "OP" and self.tok.value in ("++", "--"):
            t = self.take()
            target = self.parse_postfix()
            if not isinstance(target, (A.Name, A.Index)):
                raise ParseError(f"'{t.value}' needs a variable or array element", t.line)
            return A.IncDec(target, t.value, prefix=True)
        if self.tok.kind == "OP" and self.tok.value in ("-", "~"):
            op = self.take().value
            return A.UnOp(op, self.parse_unary())
        if self.at_op("&"):
            line = self.take().line
            target = self.parse_postfix()
            if not isinstance(target, (A.Name, A.Index)):
                raise ParseError("'&' needs a variable or array element", line)
            return A.AddrOf(target)
        return self.parse_postfix()

    def parse_postfix(self):
        t = self.tok
        if t.kind == "NUM":
            self.take()
            return A.Num(t.value)
        if t.kind == "STR":
            self.take()
            return A.Str(t.value)
        if self.at_op("("):
            self.take()
            expr = self.parse_expr()
            if self.at_op(":="):
                line = self.take().line
                if not isinstance(expr, (A.Name, A.Index)):
                    raise ParseError("':=' needs a variable or array element on the left", line)
                expr = A.Walrus(expr, self.parse_expr())
            self.expect("OP", ")")
            return expr
        if t.kind == "NAME":
            if t.value == "True":
                self.take()
                return A.Num(1)
            if t.value in ("False", "None"):
                self.take()
                return A.Num(0)
            if t.value in KEYWORDS:
                raise ParseError(f"Unexpected {t.value!r}", t.line)
            self.take()
            if self.at_op("("):
                args, _ = self.parse_call_args()
                return self._make_call(t, args)
            if self.at_op("["):
                self.take()
                index = self.parse_expr()
                self.expect("OP", "]")
                target = A.Index(A.Name(t.value), index)
            else:
                target = A.Name(t.value)
            if self.tok.kind == "OP" and self.tok.value in ("++", "--"):
                return A.IncDec(target, self.take().value)
            return target
        raise ParseError(f"Unexpected {t.value if t.value is not None else t.kind!r}", t.line)

    def _make_call(self, t: Token, args: list):
        name = t.value
        if name == "lit":
            if len(args) != 1 or not _const_int(args[0]):
                raise ParseError("lit() takes one integer constant", t.line)
            return A.Num(_const_int(args[0])[0], raw=True)
        if name == "strofs":
            if len(args) != 1 or not _const_int(args[0]):
                raise ParseError("strofs() takes one integer constant", t.line)
            return A.StrOffset(_const_int(args[0])[0])
        if name == "extern":
            if not args or not isinstance(args[0], (A.Str, A.StrOffset)):
                raise ParseError('extern() needs a name string first: extern("Name", ...)', t.line)
            target = args[0].value if isinstance(args[0], A.Str) else args[0]
            return A.Call(target, args[1:], extern=True)
        return A.Call(name, args)


def _const_int(expr) -> tuple[int] | None:
    if isinstance(expr, A.Num):
        return (expr.value,)
    if isinstance(expr, A.UnOp) and expr.op == "-" and isinstance(expr.operand, A.Num):
        return (-expr.operand.value,)
    return None


def parse(source: str) -> A.Module:
    return Parser(source).parse_module()
