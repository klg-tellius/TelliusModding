"""Read and write ``zdbx.cmp`` - the battle engine's text tables.

The battle engine (codename "kiribato", キリバト, from the files' own
comments) opens ``zdbx.cmp`` when a battle scene starts and reads its tables
by name (``open_zdbx_cmp_database_handle``, ``populate_job_list``,
``load_actor_param_database_entry``). The class-change scene reads
``zdbx/jobList.dbx`` and ``zu/*_prm.dbx`` the same way.

**Container**: LZ10 (:mod:`lz10`) around a :mod:`pak` archive of 449
entries: ``.dbx`` text files (Shift-JIS, ``#`` comments, ``{ ... }``
blocks of tab-separated key/value lines) and a few ``.tpl`` textures.
:func:`build_zdbx_archive` rebuilds the vanilla pack byte for byte.

**Folders**:

- ``zdbx/`` (11) - master tables: ``jobList.dbx`` (class to battle model),
  ``classList.dbx`` (Japanese class names to model codes), ``bgList.dbx``
  (chapter to battle scenery), ``skill.dbx``, ``effectList.dbx``
  (``EID_K_`` names; the shipped ``FE8Effect.bin`` drops the ``K_``),
  ``weaponList.dbx``, ``camera.dbx``, ``param.dbx``, ``battle.dbx``,
  ``system.dbx``, ``lensflare.dbx``.
- ``zu/`` (184) - two files per battle-model code, matching the
  ``files/zu/<code>/`` folders:
  - ``<code>.dbx`` (``class Model``): ``folder``, ``model`` (the ``.gs``/
    ``.g`` name inside the packs) and one line per weapon and action naming
    the ``.ga`` to play (``ax_攻撃1 fig1_at1_ax``).
  - ``<code>_prm.dbx`` (``class Param``): ``texnum N`` followed by N
    texture lines (army keys ``自軍``/``敵軍``/``中立``/``味方`` =
    player/enemy/other/ally, or ``PID_``/``AID_`` keys) naming
    ``zu/<code>/<value>.tpl``, then tuning keys: ``移動速度`` (move speed),
    ``間合い`` (range), ``ジャンプ攻撃``/``ジャンプ攻撃２``/``ジャンプ必殺``/
    ``ジャンプ止め``/``ジャンプ奥義`` (jump variants), ``飛行系`` (flying),
    ``止め飛び去り``, ``走り回数`` (run count), ``ダメージ後退`` (knockback),
    ``補間速度``/``移動補間速度``/``待機補間速度`` (blend speeds), ``大型``
    (large).
- ``xwp/`` (91) - one file per weapon code (:mod:`battle_weapons`);
  ``zbg/`` (117) - one ``param.dbx`` per battle scenery
  (:mod:`battle_scenery`); ``xcam/`` (19) - camera scripts per action and
  ``zdbx/camera.dbx`` the camera rigs (:mod:`battle_camera`); the tuning keys
  of ``zu/*_prm.dbx`` are :mod:`battle_params`; :mod:`dbx` edits any of them
  losslessly. ``ztool/`` (15) and ``ztex/`` (12) - the in-game battle tool's
  window layouts and textures.

**Battle model lookup** (``build_battle_preview_weapon_string``): the
job list is loaded into a table keyed by the first column; a line
``JID_X PID_Y=code`` is keyed ``JID_X+PID_Y`` and its code is cut to 4
characters. The engine tries the unit's animation ID (``AID_`` base name,
the same one ``FE8Anim.bin`` uses), then ``JID+PID``, then the class alone.
The model files are ``zu/<code>/<code>_<weapon>.cmp``, falling back to
``.pak`` (``resolve_and_load_category_named_script``).

**Battle texture lookup** (``resolve_and_apply_actor_texture_param``): the
``texnum`` lines of ``zu/<code>_prm.dbx`` are tried by the unit's AID, then
its PID, then its army key; ``_null_`` (or no line) falls back to the model
code itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import lz10, pak

JOB_LIST = "zdbx/jobList.dbx"
MODEL_CODE_RE = re.compile(r"^[a-z0-9]{4}$")


@dataclass(frozen=True)
class DbxEntry:
    name: str  # archive-relative path, e.g. "zdbx/skill.dbx"
    text: str  # Shift-JIS decoded contents (.tpl entries: latin-1)


def read_zdbx_files(data: bytes) -> list[tuple[str, bytes]]:
    """Every entry of a ``zdbx.cmp`` blob as (name, raw bytes), in pack order."""
    dec = lz10.decompress(data)
    return [(entry.name, pak.read_pak_file_content(dec, entry)) for entry in pak.read_pak_entries(dec)]


def read_zdbx_archive(data: bytes) -> list[DbxEntry]:
    """Decompress a ``zdbx.cmp`` blob and decode every entry to text."""
    result = []
    for name, content in read_zdbx_files(data):
        text = content.decode("shift_jis", errors="replace") if name.endswith(".dbx") else content.decode("latin-1")
        result.append(DbxEntry(name=name, text=text))
    return result


def read_zdbx_path(path: Path | str) -> list[DbxEntry]:
    return read_zdbx_archive(Path(path).read_bytes())


def build_zdbx_archive(files: list[tuple[str, bytes]]) -> bytes:
    """Pack and compress (name, raw bytes) entries into a ``zdbx.cmp`` blob."""
    return lz10.compress(pak.pack_pak(files))


def encode_dbx(text: str) -> bytes:
    return text.encode("shift_jis")


def folder_of(entry: DbxEntry) -> str:
    """The top-level folder an entry belongs to (e.g. "zdbx", "zu", "xcam")."""
    return entry.name.split("/", 1)[0]


# -- jobList.dbx --------------------------------------------------------------

def _job_line_key(line: str) -> tuple[str, str] | None:
    """(lookup key, code) of one job-list line, keyed like the engine's table."""
    fields = line.split("#", 1)[0].split()
    if len(fields) != 2 or not fields[0].startswith(("JID_", "AID_")):
        return None
    key, value = fields
    if "=" in value:
        pid, code = value.split("=", 1)
        return f"{key}+{pid}", code[:4]
    return key, value


def job_list_models(text: str) -> dict[str, str]:
    """The job list as the engine's table: ``JID_X``, ``JID_X+PID_Y`` or
    ``AID_X`` -> model code (later lines replace earlier ones)."""
    models = {}
    for line in text.splitlines():
        parsed = _job_line_key(line)
        if parsed:
            models[parsed[0]] = parsed[1]
    return models


def job_list_lines(text: str) -> list[tuple[str, str, str]]:
    """Every job-list line as ``(key, code, comment)``, in file order; the key
    is ``JID_X``, ``JID_X+PID_Y`` or ``AID_X`` as in :func:`job_list_models`."""
    out = []
    for line in text.splitlines():
        parsed = _job_line_key(line)
        if parsed:
            out.append((*parsed, line.split("#", 1)[1].strip() if "#" in line else ""))
    return out


def remove_job_lines(text: str, *, key: str | None = None, code: str | None = None) -> tuple[str, int]:
    """Drop the job-list lines with lookup ``key``, or selecting ``code``;
    return the new text and how many lines went."""
    lines = text.split("\n")
    kept = []
    for line in lines:
        parsed = _job_line_key(line.rstrip("\r"))
        if parsed and ((key is not None and parsed[0] == key) or (code is not None and parsed[1] == code)):
            continue
        kept.append(line)
    return "\n".join(kept), len(lines) - len(kept)


def release_job_lines(text: str, code: str, original_text: str) -> tuple[str, int]:
    """Stop every job-list line from selecting ``code``: a line whose key
    ``original_text`` also has goes back to that original line, the others
    are dropped. Returns the new text and how many lines changed."""
    originals = {}
    for line in original_text.split("\n"):
        parsed = _job_line_key(line.rstrip("\r"))
        if parsed:
            originals[parsed[0]] = line.rstrip("\r")
    out, changed = [], 0
    for line in text.split("\n"):
        parsed = _job_line_key(line.rstrip("\r"))
        if parsed and parsed[1] == code:
            changed += 1
            if parsed[0] in originals:
                out.append(originals[parsed[0]] + ("\r" if line.endswith("\r") else ""))
            continue
        out.append(line)
    return "\n".join(out), changed


def battle_model_for(models: dict[str, str], jid: str, pid: str | None = None, aid: str | None = None) -> str | None:
    """The code the engine picks: the AID line, then JID+PID, then JID."""
    for key in (aid, f"{jid}+{pid}" if pid else None, jid):
        if key and models.get(key):
            return models[key]
    return None


def set_job_model(text: str, code: str, *, jid: str | None = None, pid: str | None = None,
                  aid: str | None = None, comment: str = "") -> str:
    """Point a job-list key at ``code``: an ``AID_`` base name, a class, or a
    class plus character. Replaces the line with that key, or adds one
    before the closing brace."""
    if not MODEL_CODE_RE.match(code):
        raise ValueError(f"Model code {code!r} must be 4 lowercase letters or digits.")
    if aid:
        key, line = aid, f"\t\t{aid}\t\t{code}"
    elif jid and pid:
        key, line = f"{jid}+{pid}", f"\t\t{jid}\t\t{pid}={code}"
    elif jid:
        key, line = jid, f"\t\t{jid}\t\t{code}"
    else:
        raise ValueError("Give an aid, a jid, or a jid and a pid.")
    if comment:
        line += f"\t\t#{comment}"
    lines = text.split("\n")
    for i, old in enumerate(lines):
        parsed = _job_line_key(old.rstrip("\r"))
        if parsed and parsed[0] == key:
            lines[i] = line + ("\r" if old.endswith("\r") else "")
            return "\n".join(lines)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "}":
            eol = "\r" if lines[i].endswith("\r") else ""
            lines.insert(i, line + eol)
            return "\n".join(lines)
    raise ValueError("No closing brace in the job list.")


# -- zu/<code>.dbx and zu/<code>_prm.dbx ---------------------------------------

def _replace_value(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s+)\S+", re.MULTILINE)
    if not pattern.search(text):
        raise ValueError(f"No {key!r} line.")
    return pattern.sub(lambda m: m.group(1) + value, text, count=1)


def clone_model_dbx(text: str, new_code: str) -> str:
    """A ``zu/<code>.dbx`` for a copied model folder: ``name`` and
    ``folder`` renamed; the model and animation names inside the packs stay."""
    text = _replace_value(text, "name", new_code)
    return _replace_value(text, "folder", f"zu/{new_code}")


def clone_param_dbx(text: str, new_code: str) -> str:
    """A ``zu/<code>_prm.dbx`` for a copied model folder (texture names stay)."""
    return _replace_value(text, "name", new_code)


def param_textures(text: str) -> dict[str, str]:
    """The ``texnum`` lines of a ``_prm.dbx``: key (army, PID or AID) -> texture name."""
    lines = [line.split("#", 1)[0].split() for line in text.splitlines()]
    lines = [fields for fields in lines if fields]
    for i, fields in enumerate(lines):
        if fields[0] == "texnum" and len(fields) > 1:
            count = int(fields[1])
            return {f[0]: f[1] for f in lines[i + 1 : i + 1 + count] if len(f) >= 2}
    return {}


def remove_param_texture(text: str, key: str) -> str:
    """Drop one ``texnum`` line of a ``_prm.dbx``, keeping the count right."""
    textures = param_textures(text)
    if key not in textures:
        raise ValueError(f"No texture line {key!r}.")
    lines = text.split("\n")
    start = next(i for i, line in enumerate(lines) if line.split("#", 1)[0].split()[:1] == ["texnum"])
    eol = "\r" if lines[start].endswith("\r") else ""
    indent = re.match(r"\s*", lines[start]).group(0)
    rows = [i for i in range(start + 1, len(lines)) if lines[i].split("#", 1)[0].split()][: len(textures)]
    del lines[next(i for i in rows if lines[i].split()[0] == key)]
    lines[start] = f"{indent}texnum\t{len(textures) - 1}{eol}"
    return "\n".join(lines)


def set_param_texture(text: str, key: str, texture: str) -> str:
    """Set (or add) one ``texnum`` line of a ``_prm.dbx``, keeping the count right."""
    textures = param_textures(text)
    lines = text.split("\n")
    start = next(i for i, line in enumerate(lines) if line.split("#", 1)[0].split()[:1] == ["texnum"])
    eol = "\r" if lines[start].endswith("\r") else ""
    indent = re.match(r"\s*", lines[start]).group(0)
    count = len(textures)
    rows = [i for i in range(start + 1, len(lines)) if lines[i].split("#", 1)[0].split()][:count]
    for i in rows:
        if lines[i].split()[0] == key:
            lines[i] = f"{indent}{key}\t{texture}{eol}"
            return "\n".join(lines)
    lines.insert((rows[-1] if rows else start) + 1, f"{indent}{key}\t{texture}{eol}")
    lines[start] = f"{indent}texnum\t{count + 1}{eol}"
    return "\n".join(lines)
