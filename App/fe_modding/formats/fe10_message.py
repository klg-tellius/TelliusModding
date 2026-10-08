"""Radiant Dawn message text: the byte-code that replaced Path of Radiance's ``$`` commands.

A Radiant Dawn ``Mess/*.m`` file has the same container as Path of Radiance (``message.py``),
but the text inside a message is no longer printable ``$X`` commands. Every command starts with
a control byte below 0x20, and the byte says how long the command is. The interpreter is
``mess_exec_command`` (US RFEE01 ``FUN_80149434``); ``mess_open_box_sized`` (``FUN_8014a6cc``)
skips commands with the same length rules when it measures a box's text.

======  =========================================================================================
Byte    Command
======  =========================================================================================
00      End of the message.
01 X    One-letter command (``H`` suspend, ``@``/``*`` release the script, ``a``/``s`` mouth set...).
02 XY   Two-letter command (``w4`` pause, ``mc``/``md`` mouth, ``sd``/``se`` skip, ``ec`` eyes...).
03 XYZ  Three-letter command (only ``DFC``).
04 X..| A letter and an argument ending at ``|`` (``R`` layout, ``B`` background, ``FT`` fade time,
        ``V`` voice, ``S`` sound...). The argument is read Shift-JIS aware: the second byte of a
        two-byte character is never taken for the ``|``.
05 XY|..||  A two-letter list command: fields ending at ``|``, closed by an empty field
        (``FL`` the cast list, ``rc``, ``FX``).
07 a p  Actor ``a`` (an index into the ``FL`` list, hex digit) speaks at position ``p``.
08 p s  Show the current actor at position ``p``, facing ``s`` (``D`` default, ``L``, ``R``),
        and end the text tick. ``0e`` does the same without ending the tick.
09      Remove the current actor's portrait; ``0f`` does the same without ending the tick.
0a      New line.
0b ..   Two ignored bytes.
0c a p  Select actor ``a`` at position ``p`` (no speaker change).
0d p s  The current actor takes over the portrait already shown at position ``p``.
10      Scroll the box to a new page.
11      Wait for the A button (or the ``s`` auto-advance delay).
12      End the current text tick.
======  =========================================================================================

Everything else is text: Shift-JIS on the US and JP discs (the European discs use their own
single-byte tables, chosen with ``encoding``), plus the glyph-level markup PoR already had
(``#F01`` fonts, ``#C22`` colours, ``@{0}`` values, ``@[A]`` button icons).

**Readable notation.** The editor shows a message as text with ``<...>`` tags. ``<`` and ``>``
never occur in Radiant Dawn text bytes (they are not Shift-JIS trail bytes and no vanilla text
uses them), so the notation is lossless: ``to_raw(to_display(text)) == text`` for every message.

* ``<H>``, ``<w4>``, ``<DFC>``: one- to three-letter commands (01, 02, 03);
* ``<R:上下会話>``, ``<FT:2000>``, ``<V0:VOICE_X>``: a 04 command, name then ``:`` then argument;
* ``<FL|PUGO|IKE>``: a 05 list command (``<FL|>`` for an empty list);
* ``<speaker:04>``, ``<show:4D>``, ``<hide>``, ``<wait>``, ``<page>``...: the single-byte commands;
* a real line break is the 0a new line;
* ``<0x06>``: a byte that is neither text nor a command (kept as is).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ENCODING = "cp932"  # Shift-JIS plus the NEC rows the fonts carry (US and JP discs)
#: Command arguments (layout, background, voice and portrait names) are Shift-JIS on every disc.
ARG_ENCODING = "cp932"

# Fixed total lengths of the single-byte commands (opcode -> bytes including the opcode).
_FIXED = {0x01: 2, 0x02: 3, 0x03: 4, 0x07: 3, 0x08: 3, 0x09: 1, 0x0A: 1, 0x0B: 3, 0x0C: 3,
          0x0D: 3, 0x0E: 3, 0x0F: 1, 0x10: 1, 0x11: 1, 0x12: 1}
#: Notation names of the single-byte commands (four letters or more, so they never clash with
#: the one- to three-letter commands).
OP_NAMES = {0x07: "speaker", 0x08: "show", 0x09: "hide", 0x0B: "skip", 0x0C: "seat", 0x0D: "attach",
            0x0E: "show_now", 0x0F: "hide_now", 0x10: "page", 0x11: "wait", 0x12: "tick"}
_OP_BY_NAME = {name: op for op, name in OP_NAMES.items()}
_OPS_WITH_ARGS = {0x07, 0x08, 0x0B, 0x0C, 0x0D, 0x0E}
# 04 commands whose second character is part of the name (FT2000 -> <FT:2000>, V0VOICE -> <V0:VOICE>).
_TWO_LETTER_04 = "FNrV"
_SPECIAL = set("<>:|")


def _is_sjis_lead(byte: int) -> bool:
    return 0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xFC


def _is_sjis_trail(byte: int) -> bool:
    return 0x40 <= byte <= 0x7E or 0x80 <= byte <= 0xFC


def _field_end(raw: bytes, start: int) -> int:
    """Index of the ``|`` that ends a field starting at ``start`` (Shift-JIS aware, like
    ``mess_read_field`` FUN_80148728), or -1 when the message ends first."""
    i = start
    while i < len(raw):
        byte = raw[i]
        if byte == 0x7C:
            return i
        if byte == 0:
            return -1
        if _is_sjis_lead(byte) and i + 1 < len(raw) and _is_sjis_trail(raw[i + 1]):
            i += 2
        else:
            i += 1
    return -1


@dataclass(frozen=True)
class Token:
    """One piece of a message: ``kind`` is ``text``, ``newline``, ``command`` or ``byte``.

    ``op`` is the control byte of a command; ``name`` its letters (``w4``, ``R``, ``FL``) or the
    notation name of a single-byte command; ``args`` the decoded argument(s)."""
    kind: str
    raw: bytes
    offset: int
    op: int = 0
    name: str = ""
    args: tuple[str, ...] = ()


def tokenize(raw: bytes, encoding: str = ENCODING) -> list[Token]:
    """Split a message's bytes into tokens; ``b"".join(t.raw for t in tokens) == raw``."""
    tokens: list[Token] = []
    text = bytearray()
    text_start = 0
    i = 0

    def flush():
        if text:
            tokens.append(Token("text", bytes(text), text_start))
            text.clear()

    while i < len(raw):
        byte = raw[i]
        if byte >= 0x20 or byte in (0x00, 0x06) or byte > 0x12:
            if byte < 0x20:
                flush()
                tokens.append(Token("byte", raw[i:i + 1], i))
                i += 1
                continue
            if not text:
                text_start = i
            if _is_sjis_lead(byte) and i + 1 < len(raw) and _is_sjis_trail(raw[i + 1]):
                text += raw[i:i + 2]
                i += 2
            else:
                text.append(byte)
                i += 1
            continue
        flush()
        token = _command(raw, i, encoding)
        if token is None:
            tokens.append(Token("byte", raw[i:i + 1], i))
            i += 1
        else:
            tokens.append(token)
            i += len(token.raw)
    flush()
    return tokens


def _decode(data: bytes, encoding: str) -> str | None:
    try:
        text = data.decode(encoding)
    except UnicodeDecodeError:
        return None
    return text if text.encode(encoding, errors="replace") == data else None


def _command(raw: bytes, i: int, encoding: str) -> Token | None:
    op = raw[i]
    if op == 0x0A:
        return Token("newline", raw[i:i + 1], i, op)
    if op in _FIXED:
        end = i + _FIXED[op]
        if end > len(raw) or 0 in raw[i + 1:end]:
            return None
        body = raw[i + 1:end]
        if op in (0x01, 0x02, 0x03):
            return Token("command", raw[i:end], i, op, body.decode("latin-1"))
        return Token("command", raw[i:end], i, op, OP_NAMES[op],
                     (body.decode("latin-1"),) if body else ())
    if op == 0x04:
        if i + 1 >= len(raw) or raw[i + 1] == 0x7C:
            return None
        end = _field_end(raw, i + 1)
        if end < 0:
            return None
        body = raw[i + 1:end]
        split = 2 if chr(body[0]) in _TWO_LETTER_04 and len(body) >= 2 and body[1] < 0x80 else 1
        name = body[:split].decode("latin-1")
        arg = _decode(body[split:], ARG_ENCODING)
        return Token("command", raw[i:end + 1], i, op, name, (arg,) if arg is not None else ())
    if op == 0x05:
        fields = []
        j = i + 1
        while True:
            end = _field_end(raw, j)
            if end < 0:
                return None
            if end == j:
                break
            fields.append(raw[j:end])
            j = end + 1
        if not fields:
            return None
        name = fields[0].decode("latin-1")
        args = tuple(_decode(f, ARG_ENCODING) for f in fields[1:])
        return Token("command", raw[i:j + 1], i, op, name, args if None not in args else ())
    return None


# -- readable notation ---------------------------------------------------------------------------
def _hex(data: bytes) -> str:
    return "".join(f"<0x{b:02X}>" for b in data)


def _plain(text: str) -> bool:
    return bool(text) and all(0x20 < ord(c) < 0x7F and c not in _SPECIAL for c in text)


def _text_display(data: bytes, encoding: str) -> str:
    out = []
    i = 0
    while i < len(data):
        size = 2 if _is_sjis_lead(data[i]) and i + 1 < len(data) and _is_sjis_trail(data[i + 1]) else 1
        unit = data[i:i + size]
        char = _decode(unit, encoding)
        out.append(char if char is not None and not (set(char) & {"<", ">"})
                   and (char.isprintable() or char == "　") else _hex(unit))
        i += size
    return "".join(out)


def _arg_ok(arg: str) -> bool:
    return not (set(arg) & _SPECIAL) and arg.isprintable()


def token_display(token: Token, encoding: str = ENCODING) -> str:
    """The notation of one token (see the module docstring)."""
    if token.kind == "text":
        return _text_display(token.raw, encoding)
    if token.kind == "newline":
        return "\n"
    if token.kind == "byte":
        return _hex(token.raw)
    op = token.op
    if op in (0x01, 0x02, 0x03):
        name = token.name
        if _plain(name) and not name.startswith("0x"):
            return f"<{name}>"
    elif op in OP_NAMES:
        if op not in _OPS_WITH_ARGS:
            return f"<{OP_NAMES[op]}>"
        if _plain(token.args[0]):
            return f"<{OP_NAMES[op]}:{token.args[0]}>"
    elif op == 0x04:
        if token.args and _plain(token.name) and _arg_ok(token.args[0]):
            return f"<{token.name}:{token.args[0]}>"
    elif op == 0x05:
        if (token.args or len(token.raw) == len(token.name) + 3) and _plain(token.name) \
                and all(_arg_ok(a) and a for a in token.args):
            fields = (token.name,) + token.args
            return "<" + ("|".join(fields) if len(fields) > 1 else token.name + "|") + ">"
    return _hex(token.raw)


def to_display(text: str, encoding: str = ENCODING) -> str:
    """A message's text (the cp437 string ``message.read_messages`` gives) in the notation."""
    return "".join(token_display(t, encoding) for t in tokenize(text.encode("cp437"), encoding))


_TAG = re.compile(r"<([^<>]*)>")


def _tag_raw(inner: str, encoding: str) -> bytes:
    if re.fullmatch(r"0x[0-9A-Fa-f]{2}", inner):
        return bytes((int(inner[2:], 16),))
    if "|" in inner:
        fields = inner.split("|")
        if fields[-1] == "" and len(fields) == 2:
            fields = fields[:1]
        if any(not f for f in fields):
            raise ValueError(f"<{inner}>: empty field")
        return b"\x05" + b"".join(f.encode(ARG_ENCODING) + b"|" for f in fields) + b"|"
    if ":" in inner:
        name, arg = inner.split(":", 1)
        if name in _OP_BY_NAME:
            op = _OP_BY_NAME[name]
            if op not in _OPS_WITH_ARGS or len(arg.encode("latin-1", errors="replace")) != 2:
                raise ValueError(f"<{inner}>: {name} takes two characters, like <{name}:04>")
            return bytes((op,)) + arg.encode("latin-1")
        if not 1 <= len(name) <= 2 or not _plain(name):
            raise ValueError(f"<{inner}>: unknown command")
        return b"\x04" + name.encode("latin-1") + arg.encode(ARG_ENCODING) + b"|"
    if inner in _OP_BY_NAME:
        op = _OP_BY_NAME[inner]
        if op in _OPS_WITH_ARGS:
            raise ValueError(f"<{inner}> needs two characters, like <{inner}:04>")
        return bytes((op,))
    if 1 <= len(inner) <= 3 and _plain(inner):
        return bytes((len(inner),)) + inner.encode("latin-1")
    raise ValueError(f"<{inner}>: unknown command")


def to_raw(display: str, encoding: str = ENCODING) -> str:
    """Notation back to the cp437 message string (raises ValueError / UnicodeEncodeError)."""
    out = bytearray()
    position = 0
    for match in _TAG.finditer(display):
        out += display[position:match.start()].replace("\r", "").encode(encoding)
        out += _tag_raw(match.group(1), encoding)
        position = match.end()
    rest = display[position:]
    if "<" in rest or ">" in rest:
        raise ValueError("Unmatched < or > (write <0x3C> / <0x3E> for the bytes themselves)")
    out += rest.replace("\r", "").encode(encoding)
    if 0 in out:
        raise ValueError("A message cannot contain a 0 byte")
    return out.decode("cp437")


def plain_text(text: str, encoding: str = ENCODING) -> str:
    """The words a message shows, without commands (for lists and searches)."""
    parts = []
    for token in tokenize(text.encode("cp437"), encoding):
        if token.kind == "text":
            parts.append(_text_display(token.raw, encoding))
        elif token.kind == "newline" or (token.op == 0x11):
            parts.append(" ")
    return re.sub(r"\s+", " ", "".join(parts)).strip()


# -- command catalogue ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CommandInfo:
    label: str
    group: str
    description: str
    confidence: str = "Confirmed"


_C, _P = "Confirmed", "Plausible"
#: What each command does, from ``mess_exec_command`` (FUN_80149434) and its helpers.
#: Keys: the notation name; ``#`` stands for one digit/letter argument (``w#`` is ``w0``..``w9``).
COMMANDS: dict[str, CommandInfo] = {
    # 01: one letter
    "H": CommandInfo("Suspend", "Flow", "Stop here and keep the scene until the event script resumes the message "
                     "(TalkResume / the next TalkEvent). Same as Path of Radiance $H."),
    "@": CommandInfo("Release script", "Flow", "Let the event script that is waiting on this message continue "
                     "(Path of Radiance $UB). Vanilla follows it with <H>."),
    "*": CommandInfo("Release script (marked)", "Flow", "Like <@>, and sets message flag 0x100 first; when that flag is "
                     "already set it does nothing (Path of Radiance $Ub)."),
    "G": CommandInfo("Dissolve text", "Text", "Fade the box text out in a random pattern (64 x 8 cells), then end the "
                     "tick. World-map narration uses it before <P>.", _P),
    "P": CommandInfo("Clear box", "Text", "Fade out and clear the current text box, then end the tick.", _P),
    "a": CommandInfo("Mouth set 2", "Portraits", "Use the second mouth set for the current actor's portrait "
                     "(Path of Radiance $FA)."),
    "s": CommandInfo("Mouth set 1", "Portraits", "Back to the first mouth set (Path of Radiance $FS)."),
    "=": CommandInfo("No effect (=)", "Flow", "Not a command the game knows: it skips the two bytes and goes on with "
                     "the text. Vanilla puts it before some subtitle lines of the voiced 字幕会話 scenes."),
    "I": CommandInfo("Flag I", "Flow", "Sets message flags 0x30000.", _P),
    "J": CommandInfo("Flag J", "Flow", "Sets message flag 0x1 (shop greetings).", _P),
    "S": CommandInfo("Flag S", "Flow", "Sets message flag 0x10000.", _P),
    "c": CommandInfo("Flag c", "Flow", "Sets message flags 0xD0000.", _P),
    "g": CommandInfo("Flag g", "Flow", "Sets message flags 0x30000 and resets the current box's state byte "
                     "(world-map narration).", _P),
    # 02: two letters
    "w#": CommandInfo("Pause", "Text", "Pause 2^n text ticks (scaled by the Message Speed option); skipped while "
                      "A fast-forwards the page."),
    "mc": CommandInfo("Mouth still", "Portraits", "Keep the speaker's mouth closed (vanilla wraps '...' in <mc>...<md>)."),
    "md": CommandInfo("Mouth moving", "Portraits", "The speaker's mouth moves with the text again."),
    "mo": CommandInfo("Mouth open", "Portraits", "Hold the speaker's mouth open.", _P),
    "ec": CommandInfo("Eyes closed", "Portraits", "Close the current actor's eyes."),
    "eh": CommandInfo("Eyes half-open", "Portraits", "Half-close the current actor's eyes."),
    "eo": CommandInfo("Eyes normal", "Portraits", "Open eyes with normal blinking."),
    "eO": CommandInfo("Eyes wide", "Portraits", "The fourth eye state (flag 6).", _P),
    "bn": CommandInfo("Blink normal", "Portraits", "Blink mode 1 for the current actor.", _P),
    "bf": CommandInfo("Blink fast", "Portraits", "Blink mode 2 for the current actor.", _P),
    "bs": CommandInfo("Blink slow", "Portraits", "Blink mode 3 for the current actor.", _P),
    "sd": CommandInfo("Disable skipping", "Flow", "B no longer skips the conversation (Path of Radiance $SD); used "
                      "before choices."),
    "se": CommandInfo("Enable skipping", "Flow", "B skips the conversation again (Path of Radiance $SE)."),
    "nc": CommandInfo("Toggle nameplate", "Boxes", "Show or hide the speaker's nameplate (Path of Radiance $ND)."),
    "O#": CommandInfo("Typing sound", "Text", "Text-typing sound n (0 silent, 2 the ancient language...)."),
    "F#": CommandInfo("Screen transition", "Scene", "Start screen transition 0-3 (engine kinds 2, 3, 5, 6) over the "
                      "<FT:ms> duration. Vanilla ends scenes with <F1> and opens them with <F2>.", _P),
    "f+": CommandInfo("Show window", "Boxes", "Fade the layout's window frame in."),
    "f-": CommandInfo("Hide window", "Boxes", "Fade the layout's window frame out."),
    "VW": CommandInfo("Wait for voice", "Sound", "Wait until the current voice line has finished (A skips it)."),
    "v#": CommandInfo("Stop voice", "Sound", "Fade out the voice playing on channel n."),
    "KH": CommandInfo("Release boxes", "Boxes", "Clears the hold state (+0x70) of all nine text boxes.", _P),
    "PL": CommandInfo("Portrait flag L", "Portraits", "Sets portrait flag 0x40000 on the current actor.", _P),
    "PH": CommandInfo("Portrait flag H", "Portraits", "Sets portrait flag 0x20000 on the current actor.", _P),
    "WO": CommandInfo("Window flag on", "Boxes", "Sets message flag 0x1000.", _P),
    "WX": CommandInfo("Window flag off", "Boxes", "Clears message flag 0x1000.", _P),
    "BO": CommandInfo("Flag BO", "Scene", "Sets message flag 0x8000 (unless the scene runs without a layout). Most "
                      "conversations open with it.", _P),
    # 03
    "DFC": CommandInfo("Disable skipping (DFC)", "Flow", "Disables skipping like <sd> and clears the box's +0x1e9 "
                       "byte (Path of Radiance $DC).", _P),
    # 04: name + argument
    "R:": CommandInfo("Layout", "Scene", "Conversation layout (window/RectDesc descriptor), e.g. 上下会話 two-box talk."),
    "B:": CommandInfo("Background", "Scene", "Background image, shown with the current transition."),
    "b:": CommandInfo("Background (cut)", "Scene", "Background image, swapped without a transition."),
    "FT:": CommandInfo("Transition time", "Scene", "Duration in milliseconds of the next <F#> screen transition and "
                      "background change."),
    "NF:": CommandInfo("Box without portrait", "Boxes", "Open the box at a position (digit + facing) for a speaker that "
                      "has no portrait.", _P),
    "S:": CommandInfo("Sound effect", "Sound", "Play a sound effect by name."),
    "V#:": CommandInfo("Voice", "Sound", "Play a voice line by name on channel n (VOICE_...)."),
    "W:": CommandInfo("Pause (ms)", "Text", "Pause for this many milliseconds, then go on."),
    "s:": CommandInfo("Auto-advance", "Text", "Following <wait>s continue by themselves after this many "
                     "milliseconds (voiced scenes)."),
    "rb:": CommandInfo("Start process", "Scene", "Start a named scene process.", _P),
    "rk:": CommandInfo("Stop process", "Scene", "Stop a named scene process.", _P),
    # 05: lists
    "FL|": CommandInfo("Cast", "Portraits", "The actors of the conversation: portrait names (FID_ + name). "
                      "<speaker:a.>, <seat:a.> use their index (0-F). FID_IKE, FID_MICAIAH, FID_SOTHE, "
                      "FID_LUCHINO, FID_MEG and FID_ME are swapped for the unit's current look."),
    "rc|": CommandInfo("Move object", "Scene", "rc|name|a|b|x|y|z: place a scene object (passes five numbers to "
                      "the object).", _P),
    "FX|": CommandInfo("Effect", "Scene", "FX|name|n: start a named effect and keep its handle for the scene.", _P),
    # single-byte commands
    "speaker": CommandInfo("Speaker", "Boxes", "Actor a (cast index) speaks at position p: sets the box and the "
                           "nameplate; the box is cleared when the speaker changes."),
    "seat": CommandInfo("Select actor", "Boxes", "Make actor a at position p current without changing the speaker."),
    "show": CommandInfo("Show actor", "Portraits", "Bring the current actor's portrait and box in at position p "
                        "(facing D default, L left, R right) and end the tick.", _P),
    "show_now": CommandInfo("Show actor (no wait)", "Portraits", "Like <show>, but the text goes on at once.", _P),
    "attach": CommandInfo("Take over portrait", "Portraits", "The current actor takes the portrait already shown at "
                          "position p.", _P),
    "hide": CommandInfo("Remove actor", "Portraits", "Remove the current actor's portrait and box, and end the tick."),
    "hide_now": CommandInfo("Remove actor (no wait)", "Portraits", "Like <hide>, but the text goes on at once."),
    "page": CommandInfo("New page", "Text", "Scroll the box to a fresh page."),
    "wait": CommandInfo("Wait for A", "Text", "Show the arrow and wait for A (or the <s:ms> auto-advance delay)."),
    "tick": CommandInfo("End tick", "Text", "End the current text tick without waiting."),
    "skip": CommandInfo("Ignored", "Flow", "Two bytes the game skips."),
}


def command_key(token: Token) -> str:
    """The ``COMMANDS`` key of a command token ('' when it has none)."""
    if token.kind != "command":
        return ""
    if token.op in OP_NAMES:
        return OP_NAMES[token.op]
    suffix = {0x04: ":", 0x05: "|"}.get(token.op, "")
    name = token.name
    if name + suffix in COMMANDS:
        return name + suffix
    if len(name) == 2 and name[0] + "#" + suffix in COMMANDS and token.op in (0x02, 0x04):
        return name[0] + "#" + suffix
    return ""


def describe(token: Token) -> str:
    info = COMMANDS.get(command_key(token))
    if info is None:
        return "Unknown command" if token.kind == "command" else ""
    return info.label + ": " + info.description + ("" if info.confidence == "Confirmed" else f"  [{info.confidence}]")


# -- steps ------------------------------------------------------------------------------------
#: Commands kept inside a line of text (they do not end the line in the step list).
_INLINE_02 = re.compile(r"w[0-9]|m[cdo]")


def _inline(token: Token) -> bool:
    return token.kind in ("text", "newline") or (token.op == 0x02 and bool(_INLINE_02.fullmatch(token.name)))


@dataclass
class Step:
    """A run of tokens shown as one row: a ``line`` (text with inline pauses and mouth codes, plus
    the ``<wait>`` / page ending) or one command. ``display`` is its exact notation."""
    kind: str                    # "line" or a COMMANDS key, or "raw"
    display: str
    fields: dict = field(default_factory=dict)


LINE_ENDINGS = (("", "No wait"), ("<wait>", "Wait for A"), ("<wait>\n", "Wait for A, then a new line"),
                ("<wait><page>", "Wait for A, then a new page"))


def decompile(text: str, encoding: str = ENCODING) -> list[Step]:
    """Steps of a message; ``"".join(s.display for s in steps) == to_display(text)``."""
    tokens = tokenize(text.encode("cp437"), encoding)
    steps: list[Step] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if _inline(token) and not (token.kind == "newline" and steps and steps[-1].kind == "line"
                                   and steps[-1].fields["end"] == "<wait>"):
            j = i
            while j < len(tokens) and _inline(tokens[j]):
                j += 1
            body = "".join(token_display(t, encoding) for t in tokens[i:j])
            end = ""
            if j < len(tokens) and tokens[j].op == 0x11:
                end = "<wait>"
                j += 1
                if j < len(tokens) and tokens[j].kind == "newline":
                    end, j = "<wait>\n", j + 1
                elif j < len(tokens) and tokens[j].op == 0x10:
                    end, j = "<wait><page>", j + 1
            steps.append(Step("line", body + end, {"text": body, "end": end}))
            i = j
            continue
        display = token_display(token, encoding)
        key = (command_key(token) if display.startswith("<") and not display.startswith("<0x") else "") or "raw"
        if key == "wait":
            end = "<wait>"
            if i + 1 < len(tokens) and tokens[i + 1].kind == "newline":
                end, i = "<wait>\n", i + 1
            elif i + 1 < len(tokens) and tokens[i + 1].op == 0x10:
                end, i = "<wait><page>", i + 1
            steps.append(Step("line", end, {"text": "", "end": end}))
            i += 1
            continue
        steps.append(Step(key, display, _fields(token, key, display)))
        i += 1
    return steps


def _fields(token: Token, key: str, display: str) -> dict:
    if key == "raw" or not display.startswith("<"):
        return {"source": display}
    if token.op in _OPS_WITH_ARGS:
        arg = token.args[0]
        return {"a": arg[0], "b": arg[1]}
    if token.op == 0x05:
        return {"items": list(token.args)}
    if token.op == 0x04:
        fields = {"value": token.args[0] if token.args else ""}
        if key == "V#:":
            fields["n"] = token.name[1]
        return fields
    if key.endswith("#"):
        return {"n": token.name[1]}
    return {}


def render_step(step: Step) -> str:
    """Notation of a step from its fields."""
    f = step.fields
    kind = step.kind
    if kind == "line":
        return f["text"] + f["end"]
    if kind == "raw":
        return f["source"]
    if kind in _OP_BY_NAME:
        return f"<{kind}:{f['a']}{f['b']}>" if _OP_BY_NAME[kind] in _OPS_WITH_ARGS else f"<{kind}>"
    if kind.endswith("|"):
        items = [str(item) for item in f["items"]]
        return "<" + ("|".join([kind[:-1]] + items) if items else kind) + ">"
    if kind.endswith(":"):
        name = kind[0] + f["n"] if kind == "V#:" else kind[:-1]
        return f"<{name}:{f['value']}>"
    if kind.endswith("#"):
        return f"<{kind[0]}{f['n']}>"
    return f"<{kind}>"


def compile_steps(steps: list[Step], encoding: str = ENCODING) -> str:
    """The cp437 message string of the steps."""
    return to_raw("".join(step.display for step in steps), encoding)


def edited(step: Step, **changes) -> Step:
    fields = dict(step.fields)
    fields.update(changes)
    new = Step(step.kind, "", fields)
    new.display = render_step(new)
    return new


def new_step(kind: str) -> Step:
    defaults = {"line": {"text": "", "end": "<wait>\n"}, "raw": {"source": ""}}
    if kind in defaults:
        fields = dict(defaults[kind])
    elif kind in ("speaker", "seat"):
        fields = {"a": "0", "b": "0"}
    elif kind in ("show", "show_now", "attach"):
        fields = {"a": "0", "b": "D"}
    elif kind == "skip":
        fields = {"a": "0", "b": "0"}
    elif kind.endswith("|"):
        fields = {"items": []}
    elif kind.endswith(":"):
        fields = {"value": {"FT:": "1000", "W:": "1000", "s:": "500"}.get(kind, "")}
        if kind == "V#:":
            fields["n"] = "0"
    elif kind.endswith("#"):
        fields = {"n": {"w#": "4", "O#": "1", "F#": "2"}.get(kind, "0")}
    else:
        fields = {}
    step = Step(kind, "", fields)
    step.display = render_step(step)
    return step


def validate_step(step: Step, encoding: str = ENCODING) -> str | None:
    """Why a step cannot be written, or None."""
    try:
        to_raw(step.display, encoding)
    except (ValueError, UnicodeEncodeError) as error:
        return str(error)
    if step.kind in ("speaker", "seat") and not all(c in "0123456789ABCDEF" for c in (step.fields["a"], step.fields["b"])):
        return "Actor and position are hex digits (0-9, A-F)."
    if step.kind in ("show", "show_now", "attach") and step.fields["b"] not in "DLR":
        return "Facing is D, L or R."
    return None


def summary(step: Step, cast: list[str] | None = None) -> str:
    """Short text for a step row."""
    f = step.fields
    if step.kind == "line":
        words = plain_text(to_raw(f["text"])) if f["text"] else ""
        end = dict(LINE_ENDINGS).get(f["end"], f["end"])
        return (words[:70] + ("…" if len(words) > 70 else "")) + (f"   [{end}]" if f["end"] else "")
    if step.kind in ("speaker", "seat"):
        actor = f["a"]
        name = ""
        if cast is not None:
            index = int(actor, 16)
            name = cast[index] if index < len(cast) else "?"
        return f"actor {actor}{(' ' + name) if name else ''} at position {f['b']}"
    if step.kind in ("show", "show_now", "attach"):
        return f"position {f['a']}, facing {dict(D='default', L='left', R='right').get(f['b'], f['b'])}"
    if step.kind.endswith("|"):
        return ", ".join(f["items"]) or "(empty)"
    if step.kind == "R:":
        return layout_label(f["value"])
    if "value" in f:
        return (f"{f['n']}: " if "n" in f else "") + f["value"]
    if "n" in f:
        return f["n"]
    if step.kind == "raw":
        return f["source"]
    return ""


def cast_of(steps: list[Step]) -> list[str]:
    """The last <FL> list of the steps (portrait names without FID_)."""
    cast: list[str] = []
    for step in steps:
        if step.kind == "FL|":
            cast = list(step.fields["items"])
    return cast


#: The step kinds offered by "Add step" (grouped by ``CommandInfo.group``).
ADDABLE = ("line", "FL|", "speaker", "seat", "show", "show_now", "attach", "hide", "hide_now", "R:", "B:", "b:",
           "FT:", "F#", "f+", "f-", "ec", "eh", "eo", "mc", "md", "a", "s", "nc", "w#", "W:", "s:", "page", "tick",
           "P", "G", "O#", "V#:", "VW", "v#", "S:", "H", "@", "*", "sd", "se", "raw")


def step_label(kind: str) -> str:
    if kind == "line":
        return "Line of text"
    if kind == "raw":
        return "Raw code"
    info = COMMANDS.get(kind)
    return info.label if info else kind


#: English names of the Radiant Dawn layouts (window/RectDesc descriptors), in order of use in the
#: US English text (counts per <R:...> over every e_*.m file).
LAYOUT_NAMES: dict[str, str] = {
    "上下会話": "Two-box talk",                      # 4913
    "背景会話": "Background scene",                  # 691
    "TUT会話": "Tutorial talk",                      # 390
    "背景上下会話": "Two-box talk over background",  # 125
    "紹介会話": "Introduction",                      # 69
    "GMAP会話": "World map narration",               # 43
    "TUT小会話": "Tutorial info windows",            # 41
    "背景なし会話": "Scene without background",      # 30
    "字幕会話": "Subtitles (voiced scenes)",         # 20
    "ダイアログ会話": "Dialog popup",                # 13
    "BASE_SHOP_MESS": "Base shop greeting",          # 13
    "背景のみ会話": "Text box over background",      # 10
    "のみ会話": "Text box only",                     # 10
}


def layout_label(name: str) -> str:
    """'English name (ID)' for a known layout, otherwise the ID itself."""
    english = LAYOUT_NAMES.get(name)
    return f"{english} ({name})" if english else name


def layout_from_label(label: str) -> str:
    label = label.strip()
    if label.endswith(")") and " (" in label:
        name = label[label.rindex(" (") + 2:-1]
        if name in LAYOUT_NAMES:
            return name
    return label


#: Starting points for a new message (notation). Vanilla messages end with <wait>; a script
#: plays them with TalkEvent("MS_...").
TEMPLATES: dict[str, str] = {
    "Two-box talk": "<FL|IKE|MICAIAH><R:上下会話><speaker:00><show:0D>First line.<wait>\n"
                    "<speaker:11><show:1D>Reply.<wait>",
    "Background scene": "<FL|IKE|MICAIAH><BO><R:背景会話><seat:01><show_now:1D><seat:13><show:3D>"
                        "<B:デイン-路地-昼><speaker:01>First line.<wait>\n<speaker:13>Reply.<wait>",
    "Empty": "",
}

#: File-name prefixes of the language variants (``mess/%s%s`` with the table at US 0x804cce58).
LANGUAGES = {"": "Japanese", "e_": "English", "d_": "German", "f_": "French", "s_": "Spanish", "i_": "Italian"}


def language_of(file_name: str) -> str:
    """The language of a Mess file from its prefix (``e_c0101.m`` -> ``English``)."""
    prefix = file_name[:2].lower()
    return LANGUAGES.get(prefix, LANGUAGES[""]) if prefix.endswith("_") else LANGUAGES[""]


def decoded_language(file_name: str) -> bool:
    """False for the European language files, whose single-byte text tables are not decoded yet:
    their accented letters show as half-width katakana (the bytes are still kept exactly)."""
    return language_of(file_name) in ("Japanese", "English")
