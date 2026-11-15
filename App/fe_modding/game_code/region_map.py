"""Address maps between regional builds of one game's main.dol.

A map is built offline from two retail executables (:func:`build`) and stored as data
(``rd_region_blocks``). It has two parts:

* **code blocks**: runs of instructions that are equal once relocatable operands are masked
  (:func:`ppc.mask_words`), so an address inside a run maps to the same instruction in the
  other build;
* **data anchors**: the absolute addresses (``lis`` + ``addi``/load pairs, r2/r13 small-data
  accesses, branch targets) that aligned instructions form in each build. Between two anchors
  with the same distance, data maps by that distance.

:func:`translate` then moves an address from the reference build to the other one, or returns
None when it falls outside what the two builds share. A caller still checks the bytes at the
translated address before trusting it.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from .dol import Dol
from .ppc import mask_words, sext16

GRAM = 8


@dataclass(frozen=True)
class RegionMap:
    code: tuple[tuple[int, int, int], ...]     # (reference address, other address, length in bytes), sorted
    data: tuple[tuple[int, int], ...]          # (reference address, other address) anchors, sorted

    def translate(self, address: int) -> int | None:
        starts = [c[0] for c in self.code]
        i = bisect_right(starts, address) - 1
        if i >= 0:
            ref, other, length = self.code[i]
            if address < ref + length:
                return other + (address - ref)
        return self.translate_data(address)

    def translate_data(self, address: int) -> int | None:
        keys = [d[0] for d in self.data]
        i = bisect_right(keys, address) - 1
        if i < 0:
            return None
        ref, other = self.data[i]
        if ref == address:
            return other
        if i + 1 >= len(self.data):
            return None
        nxt_ref, nxt_other = self.data[i + 1]
        if nxt_other - nxt_ref != other - ref:
            return None
        return address + (other - ref)


def _text(dol: Dol) -> list[tuple[int, list[int], list[int]]]:
    sda = dol.sda_bases()
    out = []
    for s in dol.text_sections:
        words = list(dol.words(s.address, s.size // 4))
        out.append((s.address, words, mask_words(words, sda)))
    return out


def _align(ref_masked: list[int], other_masked: list[int]) -> list[tuple[int, int, int]]:
    """Runs (ref index, other index, word count) of equal masked words, in order."""
    def grams(m):
        seen: dict[tuple, int] = {}
        dup = set()
        for i in range(len(m) - GRAM + 1):
            g = tuple(m[i:i + GRAM])
            if g in seen:
                dup.add(g)
            else:
                seen[g] = i
        return {g: i for g, i in seen.items() if g not in dup}
    gr, go = grams(ref_masked), grams(other_masked)
    # Each gram unique in both builds anchors a run, extended both ways while the masked words
    # stay equal. Runs may come in any order: the linker does not keep every object file in place.
    pairs = sorted((i, go[g]) for g, i in gr.items() if g in go)
    runs: list[tuple[int, int, int]] = []
    covered_to = -1
    for r, o in pairs:
        if r < covered_to and runs and r - runs[-1][0] == o - runs[-1][1]:
            continue
        s_r, s_o = r, o
        while s_r > 0 and s_o > 0 and ref_masked[s_r - 1] == other_masked[s_o - 1]:
            s_r -= 1
            s_o -= 1
        e_r, e_o = r, o
        while e_r < len(ref_masked) and e_o < len(other_masked) and ref_masked[e_r] == other_masked[e_o]:
            e_r += 1
            e_o += 1
        runs.append((s_r, s_o, e_r - s_r))
        covered_to = max(covered_to, e_r)
    # keep, for every reference word, only the longest run that covers it
    runs.sort(key=lambda run: -run[2])
    owner = [-1] * len(ref_masked)
    kept: list[tuple[int, int, int]] = []
    for s_r, s_o, n in runs:
        free = [k for k in range(s_r, s_r + n) if owner[k] < 0]
        if not free:
            continue
        # split into the contiguous free stretches
        start = prev = free[0]
        for k in free[1:] + [None]:
            if k is None or k != prev + 1:
                kept.append((start, s_o + (start - s_r), prev - start + 1))
                if k is not None:
                    start = k
            if k is not None:
                prev = k
        for k in free:
            owner[k] = 1
    return sorted(kept)


def _opcode(w: int) -> int:
    op = w >> 26
    return (op << 10) | ((w >> 1) & 0x3FF) if op in (19, 31, 59, 63) else op << 10


def _fill(runs: list[tuple[int, int, int]], ref_words: list[int], other_words: list[int]) -> list[tuple[int, int, int]]:
    """Runs for the gaps between two neighbouring runs, matched loosely: a gap of the same
    length on both sides maps word for word; otherwise words map inwards from each end while
    their opcodes agree (register choices and offsets often differ between builds). The
    caller checks the bytes it relies on, so a loose run only proposes a counterpart."""
    extra = []
    for (ar, ao, an), (br, bo, _) in zip(runs, runs[1:]):
        gr, go = ar + an, ao + an
        n_ref, n_other = br - gr, bo - go
        if n_ref <= 0 or n_other <= 0 or n_ref > 4096 or n_other > 4096:
            continue
        if n_ref == n_other:
            extra.append((gr, go, n_ref))
            continue
        k = 0
        while k < min(n_ref, n_other) and _opcode(ref_words[gr + k]) == _opcode(other_words[go + k]):
            k += 1
        if k:
            extra.append((gr, go, k))
        j = 0
        while (j < min(n_ref, n_other) - k
               and _opcode(ref_words[br - 1 - j]) == _opcode(other_words[bo - 1 - j])):
            j += 1
        if j:
            extra.append((br - j, bo - j, j))
    return sorted(runs + extra)


def _absolute(words: list[int], i: int, sda: tuple[int | None, int | None], base: int) -> int | None:
    """The absolute address instruction ``i`` forms: a branch target, a lis-based low half
    (looking back for the lis of the same register), or an r2/r13 small-data access."""
    w = words[i]
    op, rd, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
    if op == 18:
        li = w & 0x03FFFFFC
        if li & 0x02000000:
            li -= 0x04000000
        return (li if w & 2 else base + i * 4 + li) & 0xFFFFFFFF
    if op in (14, 24) or 32 <= op < 56:
        src = rd if op == 24 else ra
        r2, r13 = sda
        if op != 24 and src == 13 and r13 is not None:
            return (r13 + sext16(imm)) & 0xFFFFFFFF
        if op != 24 and src == 2 and r2 is not None:
            return (r2 + sext16(imm)) & 0xFFFFFFFF
        for j in range(i - 1, max(-1, i - 12), -1):
            p = words[j]
            if p >> 26 == 15 and (p >> 16) & 31 == 0 and (p >> 21) & 31 == src:
                high = (p & 0xFFFF) << 16
                return (high | imm) if op == 24 else (high + sext16(imm)) & 0xFFFFFFFF
    return None


def _mask_data(words: list[int]) -> list[int]:
    return [0x80000000 if 0x80000000 <= w < 0x81800000 else w for w in words]


def build(reference: Dol, other: Dol) -> RegionMap:
    ref_text, other_text = _text(reference), _text(other)
    ref_sda, other_sda = reference.sda_bases(), other.sda_bases()
    code: list[tuple[int, int, int]] = []
    data: dict[int, int] = {}
    clash: set[int] = set()
    for (ra, rw, rm), (oa, ow, om) in zip(ref_text, other_text):
        strict = _align(rm, om)
        for r, o, n in _fill(strict, rw, ow):
            code.append((ra + r * 4, oa + o * 4, n * 4))
        for r, o, n in strict:                    # data anchors only from exactly matching code
            for k in range(n):
                a = _absolute(rw, r + k, ref_sda, ra)
                b = _absolute(ow, o + k, other_sda, oa)
                if a is None or b is None or 0x80000000 > a or a >= 0x81800000:
                    continue
                if data.get(a, b) != b:
                    clash.add(a)
                data[a] = b
    # data sections: words compared with pointer-like values masked
    ref_data = [x for x in reference.sections if not x.is_text]
    other_data = [x for x in other.sections if not x.is_text]
    for rs, os_ in zip(ref_data, other_data):
        rw = list(reference.words(rs.address, rs.size // 4))
        ow = list(other.words(os_.address, os_.size // 4))
        for r, o, n in _align(_mask_data(rw), _mask_data(ow)):
            code.append((rs.address + r * 4, os_.address + o * 4, n * 4))
    for a in clash:
        data.pop(a, None)
    # a data anchor inside aligned code is a branch target; code blocks already cover it
    return RegionMap(tuple(sorted(code)), tuple(sorted(data.items())))
