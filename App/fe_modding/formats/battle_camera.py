"""Battle cameras: ``zdbx/camera.dbx`` (the rigs) and ``xcam/*.dbx`` (scripts).

**Rigs** - ``zdbx/camera.dbx`` has one ``class Camera`` block per camera:

- ``cam0``: the scene camera (``enable``, ``eyeCenter``, ``pos``, ``rot``).
- ``cam1``: the free camera orbiting a point (``dest``, ``attract``,
  ``dist``, ``rot``).
- ``camCharaL0``/``camCharaR0``: unit cameras that follow an actor
  (``entityClass Actor``, ``entityName`` / ``entityName1`` / ``entityName2``
  = ``charaAtk``/``charaDef``/``charaSup``, the slot to follow first, second
  and third), with ``dist``, ``offs`` (look-at offset) and ``rot``.
- ``camCharaL1``/``camCharaR1``: weapon cameras (``entityClass Weapon``,
  ``weapon0``/``weapon1``/``weapon2``) with a ``speed``.

Angles are degrees. Vanilla keeps a typo, ``rot -2.-2, 180.0, 0.0`` on
``cam1``; values that do not parse are kept as text and only replaced when
edited.

**Scripts** - each ``xcam/<name>.dbx`` is one ``class CameraAnime`` block
that moves one of the rigs through keyframes during a battle action
(``atk_l``, ``crit_r``, ``class_chg``, ``standby`` ...): ``name``,
``caption`` (Japanese description), optional ``folder``, ``camera`` (the rig
moved), ``num`` (keyframe count) and then ``num`` times ``pos``, ``rot``,
``dist`` and ``time``. ``time`` is the keyframe's duration in engine time
units (0 = cut straight to it); the unit has not been measured.

**Packs** - more scripts sit in ``xcam/<folder>/cam.cmp`` (an LZ10 pak, read with
:func:`read_script_pack`):

- ``xcam/<model>/cam.cmp``: one script per battle clip, named like the clip
  (``fig1_at1_ax``, ``mgm1_at1_no``), plus lists (``fig1_ax.dbx``,
  ``num``/``camanim``) per weapon. Loaded with the model
  (``load_camera_compare_script`` in ``setup_battle_scene``); whenever an
  actor switches clip (``gactor_switch_animation_module``) the script named
  by the clip's first 11 characters plays, if there is one.
- ``xcam/magic/cam.cmp``: ``<NAME>_at0`` (the spell leaves the caster) and
  ``<NAME>_at1`` (it hits) per tome (``WIND_at0``...), created by
  ``gactor_create_weapon_instance`` for magic weapons. The sibling
  ``magic.cmp`` (also ``_cr0``/``_sk0``...) is never loaded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import dbx, lz10, pak

NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
VEC_KEYS = ("pos", "rot", "dest", "offs")
FLOAT_KEYS = ("dist", "speed")
INT_KEYS = ("enable", "eyeCenter", "attract")
TEXT_KEYS = ("entityClass", "entityName", "entityName1", "entityName2")
CAMERA_FIELDS = VEC_KEYS + FLOAT_KEYS + INT_KEYS + TEXT_KEYS
ENTITY_CLASSES = ("Actor", "Weapon")
KEYFRAME_KEYS = ("pos", "rot", "dist", "time")


class CameraError(dbx.DbxError):
    pass


def _number(text: str) -> float:
    try:
        return float(text)
    except ValueError as exc:
        raise CameraError(f"{text!r} is not a number.") from exc


def format_vec(values) -> str:
    """``a, b, c`` with two decimals, as the vanilla scripts write them."""
    values = list(values)
    if len(values) != 3:
        raise CameraError("A position or rotation needs three numbers.")
    return ", ".join(f"{_number(str(v)):.2f}" for v in values)


def parse_vec(text: str) -> tuple[float, float, float] | None:
    """The three numbers of ``a, b, c``; None when the text is not three numbers."""
    parts = [p.strip() for p in text.split(",")]
    try:
        values = tuple(float(p) for p in parts)
    except ValueError:
        return None
    return values if len(values) == 3 else None


def _check(key: str, value: str) -> str:
    value = str(value).strip()
    if key in VEC_KEYS:
        return format_vec(value.split(","))
    if key in FLOAT_KEYS:
        return f"{_number(value):g}"
    if key in INT_KEYS:
        if value not in ("0", "1"):
            raise CameraError(f"{key} must be 0 or 1.")
        return value
    if key in TEXT_KEYS:
        if not value or not NAME_RE.match(value):
            raise CameraError(f"{key} must be a name (letters and digits).")
        return value
    raise CameraError(f"Unknown camera field {key!r}.")


# -- camera.dbx -----------------------------------------------------------------

@dataclass(frozen=True)
class CameraRig:
    name: str
    fields: tuple[tuple[str, str], ...]  # (key, raw value) in file order, without class/name

    def get(self, key: str, default: str = "") -> str:
        return next((v for k, v in self.fields if k == key), default)

    @property
    def entity_class(self) -> str:
        return self.get("entityClass")


def read_rigs(text: str) -> list[CameraRig]:
    return [CameraRig(b.name or "", tuple((f.key, f.value) for f in b.fields if f.key not in ("class", "name")))
            for b in dbx.parse(text).blocks() if b.cls == "Camera"]


def set_rig_field(text: str, camera: str, key: str, value: str) -> str:
    """Set (or add) one field of the camera named ``camera``; an empty value
    removes an optional text field (``entityName1``...)."""
    if key not in CAMERA_FIELDS:
        raise CameraError(f"Unknown camera field {key!r}.")
    doc = dbx.parse(text)
    try:
        block = doc.find("Camera", camera)
    except dbx.DbxError as exc:
        raise CameraError(f"No camera named {camera!r}.") from exc
    existing = next((f for f in block.fields if f.key == key), None)
    if not str(value).strip() and key in ("entityName1", "entityName2"):
        if existing:
            doc.remove_field(existing)
        return doc.text
    value = _check(key, value)
    if existing is None:
        doc.add_field(block, key, value)
    else:
        doc.set_value(existing, value)
    return doc.text


# -- xcam/*.dbx -----------------------------------------------------------------

@dataclass(frozen=True)
class Keyframe:
    pos: tuple[float, float, float]
    rot: tuple[float, float, float]
    dist: float
    time: int


@dataclass(frozen=True)
class CameraScript:
    name: str
    caption: str
    camera: str
    keyframes: tuple[Keyframe, ...]


def read_script(text: str) -> CameraScript:
    try:
        block = dbx.parse(text).find("CameraAnime")
    except dbx.DbxError as exc:
        raise CameraError("No CameraAnime block.") from exc
    pos, rot, dist, time = (block.get_all(k) for k in KEYFRAME_KEYS)
    declared = int(block.get("num", "0") or 0)
    if not (len(pos) == len(rot) == len(dist) == len(time) == declared):
        raise CameraError(f"num says {declared} keyframes but the block has {len(pos)}/{len(rot)}/{len(dist)}/{len(time)}.")
    frames = []
    for p, r, d, t in zip(pos, rot, dist, time):
        vp, vr = parse_vec(p), parse_vec(r)
        if vp is None or vr is None:
            raise CameraError(f"Bad pos/rot keyframe: {p!r} / {r!r}.")
        frames.append(Keyframe(vp, vr, _number(d), int(_number(t))))
    return CameraScript(block.name or "", block.get("caption", ""), block.get("camera", ""), tuple(frames))


def read_script_pack(data: bytes) -> list[CameraScript]:
    """The ``CameraAnime`` scripts of an ``xcam/<folder>/cam.cmp`` pack (lists are skipped)."""
    raw = lz10.decompress(data)
    scripts = []
    for entry in pak.read_pak_entries(raw):
        text = pak.read_pak_file_content(raw, entry).decode("cp932", errors="replace")
        if "CameraAnime" not in text:
            continue
        try:
            scripts.append(read_script(text))
        except (CameraError, dbx.DbxError, ValueError):
            continue
    return scripts


def _check_frame(frame: Keyframe) -> list[tuple[str, str]]:
    if frame.time < 0:
        raise CameraError("A keyframe time cannot be negative.")
    return [("pos", format_vec(frame.pos)), ("rot", format_vec(frame.rot)),
            ("dist", f"{frame.dist:.2f}"), ("time", str(int(frame.time)))]


def set_script_keyframes(text: str, keyframes: list[Keyframe]) -> str:
    """Replace the whole keyframe list (and ``num``), leaving the header lines."""
    if not keyframes:
        raise CameraError("A camera script needs at least one keyframe.")
    rows = [row for frame in keyframes for row in _check_frame(frame)]
    doc = dbx.parse(text)
    try:
        block = doc.find("CameraAnime")
    except dbx.DbxError as exc:
        raise CameraError("No CameraAnime block.") from exc
    num = next((f for f in block.fields if f.key == "num"), None)
    if num is None:
        raise CameraError("The script has no num line.")
    for field in sorted((f for f in block.fields if f.key in KEYFRAME_KEYS), key=lambda f: -f.line):
        doc.remove_field(field)
    block = doc.find("CameraAnime")
    num = next(f for f in block.fields if f.key == "num")
    doc.set_value(num, str(len(keyframes)))
    anchor = num
    for key, value in rows:
        doc.add_field(block, key, value, after=anchor)
        anchor = dbx.Field(anchor.line + 1, key, value, "")
    return doc.text


def set_script_field(text: str, key: str, value: str) -> str:
    """Set the ``camera`` rig or the ``caption`` of a script."""
    value = str(value).strip()
    if key == "camera":
        if not NAME_RE.match(value):
            raise CameraError("camera must be a rig name such as camCharaL0.")
    elif key != "caption":
        raise CameraError(f"Unknown script field {key!r}.")
    doc = dbx.parse(text)
    block = doc.find("CameraAnime")
    existing = next((f for f in block.fields if f.key == key), None)
    if existing is None:
        doc.add_field(block, key, value)
    else:
        doc.set_value(existing, value)
    return doc.text


def new_script(name: str, camera: str, caption: str = "", keyframes: list[Keyframe] | None = None,
               eol: str = "\r\n") -> str:
    """A fresh ``xcam/<name>.dbx`` (one default keyframe unless given)."""
    if not NAME_RE.match(name):
        raise CameraError("Script name must be letters, digits and underscores.")
    if not NAME_RE.match(camera):
        raise CameraError("camera must be a rig name such as camCharaL0.")
    frames = keyframes or [Keyframe((0.0, 7.0, 0.0), (5.0, 180.0, 0.0), 60.0, 0)]
    lines = ["#", f"# {caption or name}", "#", "", "{", "\tclass\tCameraAnime", f"\tname\t{name}",
             f"\tcaption\t{caption}", f"\tcamera\t{camera}", "\tnum\t0", "}"]
    return set_script_keyframes(eol.join(lines) + eol, frames)
