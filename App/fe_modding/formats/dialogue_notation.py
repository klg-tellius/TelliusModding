"""Lossless, human-readable dialogue notation and byte/source position mapping.

Tags use <Action:argument>. Within arguments &amp;, &lt; and &gt; escape
reserved characters. Literal angle brackets and undecoded bytes use <Bytes:HEX>.
The game still receives its original dialect; this notation is only an editor format.
"""
from __future__ import annotations

from dataclasses import dataclass
import html
import re

from . import fe10_message as rd
from .fe9_conversation import tokenize
from .fe9_message_scene import to_raw

FE9_NAMES = {
    'R': 'Layout', 'B': 'Background', 'c': 'Show speaker', 'C': 'Control',
    'FC': 'Portrait', 'FD': 'Remove portrait', 'Fc': 'Close eyes',
    'Fh': 'Half-open eyes', 'Fo': 'Hold eyes open', 'Fd': 'Normal eyes',
    'Ff': 'Quick blinking', 'Fs': 'Normal blinking', 'FS': 'Mouth set 1',
    'FA': 'Mouth set 2', 'F': 'Seat', 's': 'Box', 'd': 'Dismiss box',
    'w': 'Pause power', 'W': 'Small box', 'O': 'Typing sound',
    '=': 'Transition ms', 'MC': 'Stop mouth', 'MD': 'Resume mouth',
    'UB': 'Release script', 'Ub': 'Release script alias', 'SD': 'Disable skipping',
    'DC': 'Disable skipping alias', 'SE': 'Enable skipping', 'ND': 'Toggle nameplate',
    'W+': 'Show windows', 'W-': 'Hide windows', 'WD': 'Hide current window',
    'K': 'Wait', 'P': 'Clear box', 'N': 'New line', 'H': 'Yield to script',
    'G': 'Narration', 'Y': 'Continue', '<': 'Fade in', '>': 'Fade out',
}
FE10_NAMES = {
    'R:': 'Layout', 'B:': 'Background', 'FL|': 'Cast', 'FT:': 'Transition ms',
    'speaker': 'Speaker', 'seat': 'Seat', 'show': 'Show portrait',
    'hide': 'Remove portrait', 'show_now': 'Show portrait now',
    'hide_now': 'Remove portrait now', 'attach': 'Attach portrait',
    'wait': 'Wait', 'page': 'New page', 'tick': 'Continue',
    'H': 'Yield to script', '@': 'Release script', '*': 'Release script marked',
    'P': 'Clear box', 'mc': 'Stop mouth', 'md': 'Resume mouth',
    'sd': 'Disable skipping', 'se': 'Enable skipping',
}
for _key, _info in rd.COMMANDS.items():
    FE10_NAMES.setdefault(_key, _info.label)
FE10_NAMES['w#'] = 'Pause power'
TAG = re.compile(r'<([^<>]*)>')


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    byte_start: int
    byte_end: int
    action: bool = False


@dataclass(frozen=True)
class Document:
    text: str
    raw: str
    spans: tuple[Span, ...]

    def at_byte(self, offset: int) -> Span | None:
        return next((s for s in self.spans if s.byte_start <= offset < s.byte_end), None)

    def byte_at(self, position: int) -> int:
        span = next((s for s in self.spans if s.start <= position < s.end), None)
        return span.byte_start if span else len(self.raw)


class NotationError(ValueError):
    def __init__(self, message: str, start: int, end: int):
        super().__init__(message)
        self.start, self.end = start, end


def _escape(value):
    return html.escape(value, quote=False)


def _fe9_tag(inner):
    name, sep, value = inner.partition(':')
    name, value = name.strip(), html.unescape(value)
    if name == 'Markup':
        if not value.startswith('#'):
            raise ValueError('Markup must begin with #')
        raw = to_raw(value)
        tokens = tokenize(raw)
        if len(tokens) != 1 or tokens[0].code != 'markup':
            raise ValueError('Expected one markup code')
        return raw
    reverse = {v.casefold(): k for k, v in FE9_NAMES.items()}
    code = reverse.get(name.casefold())
    if code is None:
        raise ValueError(f'Unknown action: {name}')
    if code in ('R', 'B', 'c', 'C', 'FC'):
        if not sep or '|' in value:
            raise ValueError(f'{name} needs a value without |')
        if code == 'c' and (not value or value[0] not in '0123'):
            raise ValueError('Show speaker needs a box digit (0–3) followed by a portrait ID')
        raw = to_raw('$' + code + value + '|')
    elif code in ('F', 's', 'd', 'w', 'W', 'O', '='):
        if not value.isascii() or not value.isdigit():
            raise ValueError(f'{name} needs a number')
        maximum = 9999 if code == '=' else 3 if code in ('s', 'd', 'W') else 8 if code == 'F' else 9
        if int(value) > maximum:
            raise ValueError(f'{name} must be between 0 and {maximum}')
        raw = '$' + code + (f'{int(value):04d}' if code == '=' else str(int(value)))
    else:
        if sep:
            raise ValueError(f'{name} does not take a value')
        raw = '$' + code
    tokens = tokenize(raw)
    if len(tokens) != 1 or tokens[0].code != code:
        raise ValueError(f'Invalid {name} action')
    return raw


def _tag_raw(inner, fe10):
    name, sep, value = inner.partition(':')
    if name.strip().casefold() == 'bytes':
        try:
            data = bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError('Bytes needs hexadecimal pairs') from exc
        if not data or b'\0' in data:
            raise ValueError('Bytes must be nonempty and cannot contain 00')
        return data.decode('cp437')
    if not fe10:
        return _fe9_tag(inner)
    reverse = {v.casefold(): k for k, v in FE10_NAMES.items()}
    code = reverse.get(name.casefold())
    if code:
        value = html.unescape(value)
        if code.endswith('#'):
            if len(value) != 1 or value not in '0123456789ABCDEF':
                raise ValueError(f'{name} needs one digit')
            inner = code[0] + value
        elif code == 'V#:':
            channel, delimiter, voice = value.partition(':')
            if not delimiter or len(channel) != 1 or channel not in '0123456789ABCDEF':
                raise ValueError('Voice needs channel:voice ID, e.g. 0:VOICE_IKE')
            inner = 'V' + channel + ':' + voice
        elif code.endswith((':', '|')):
            if not sep:
                raise ValueError(f'{name} needs a value')
            inner = code + value
        else:
            inner = code + (':' + value if sep else '')
    raw = rd.to_raw('<' + inner + '>')
    for step in rd.decompile(raw):
        problem = rd.validate_step(step)
        if problem:
            raise ValueError(problem)
    return raw


def parse(text: str, fe10: bool = False) -> Document:
    """Parse a draft strictly; an error never discards or repairs user text."""
    raw, spans = [], []
    pos = byte = 0
    while pos < len(text):
        start = pos
        try:
            if text[pos] == '<':
                match = TAG.match(text, pos)
                if not match:
                    raise ValueError('Unclosed action; use <Bytes:3C> for a literal <')
                pos = match.end()
                chunk = _tag_raw(match.group(1), fe10)
                action = True
            else:
                if text[pos] == '>':
                    raise ValueError('Use <Bytes:3E> for a literal >')
                pos += 1
                chunk = text[start:pos].encode(rd.ENCODING if fe10 else 'shift_jis').decode('cp437')
                action = False
            if '\0' in chunk:
                raise ValueError('A message cannot contain a zero byte')
        except (ValueError, UnicodeError) as exc:
            line = text.count('\n', 0, start) + 1
            column = start - text.rfind('\n', 0, start)
            raise NotationError(f'Line {line}, column {column}: {exc}', start, max(start + 1, pos)) from exc
        raw.append(chunk)
        spans.append(Span(start, pos, byte, byte + len(chunk), action))
        byte += len(chunk)
    return Document(text, ''.join(raw), tuple(spans))


def display(raw: str, fe10: bool = False) -> Document:
    """Decode for editing, retaining every byte including unknown commands."""
    parts = []
    if fe10:
        for token in rd.tokenize(raw.encode('cp437')):
            part = rd.token_display(token)
            key = rd.command_key(token)
            if key in FE10_NAMES and part.startswith('<') and not part.startswith('<0x'):
                name = FE10_NAMES[key]
                if key.endswith('#'):
                    value = token.name[1:]
                elif key == 'V#:':
                    value = token.name[1:] + ':' + token.args[0]
                elif key.endswith('|'):
                    value = '|'.join(token.args)
                else:
                    value = token.args[0] if token.args else None
                part = '<' + name + (':' + _escape(value) if value is not None else '') + '>'
            try:
                if parse(part, True).raw != token.raw.decode('cp437'):
                    raise ValueError('Noncanonical bytes')
            except (ValueError, UnicodeError):
                part = '<Bytes:' + token.raw.hex().upper() + '>'
            parts.append(part)
    else:
        try:
            tokens = tokenize(raw)
        except UnicodeError:
            return parse('<Bytes:' + raw.encode('cp437').hex().upper() + '>')
        for i, token in enumerate(tokens):
            source = raw[token.offset:tokens[i + 1].offset if i + 1 < len(tokens) else len(raw)]
            if token.code == 'text':
                part = token.arg
                if part in ('<', '>') or part.encode('shift_jis', errors='replace').decode('cp437') != source:
                    part = '<Bytes:' + source.encode('cp437').hex().upper() + '>'
            elif token.code in FE9_NAMES:
                part = '<' + FE9_NAMES[token.code] + (':' + _escape(token.arg) if token.arg or token.code in ('R', 'B', 'c', 'C', 'FC') else '') + '>'
            elif token.code == 'markup':
                part = '<Markup:' + _escape(token.arg) + '>'
            else:
                part = '<Bytes:' + source.encode('cp437').hex().upper() + '>'
            try:
                if parse(part).raw != source:
                    raise ValueError('Noncanonical bytes')
            except (ValueError, UnicodeError):
                part = '<Bytes:' + source.encode('cp437').hex().upper() + '>'
            parts.append(part)
    document = parse(''.join(parts), fe10)
    if document.raw != raw:
        # Preserve malformed/unknown input rather than normalizing it away.
        return parse(''.join('<Bytes:' + raw[i:i+1].encode('cp437').hex().upper() + '>' for i in range(len(raw))), fe10)
    return document
