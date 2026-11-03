"""The simulator's random-number stream.

Path of Radiance's combat rolls go through two entry points in ``main.dol``
(:data:`fe_modding.game_code.entries.ROLL_PERCENT` and ``ROLL_TRUE_HIT``):
a percent roll draws one number 0-99, and the "true hit" roll draws two and
averages them (the archive's ``combat-mechanics`` article). The archive
describes the generator as a three-word chained shift register; its exact
constants and seeding are not decoded, so :class:`Fe9Rng` is a stand-in with
the same shape (a 96-bit xorshift) - it reproduces the game's *distribution*
of hits, not a given save's sequence. A seed always gives the same fight.
"""

from __future__ import annotations

_MASK = 0xFFFFFFFF


class Fe9Rng:
    def __init__(self, seed: int = 0):
        self.seed = seed
        x = (seed ^ 0x6C078965) & _MASK
        self._state = [x or 1, (x * 1812433253 + 1) & _MASK or 2, (x * 0x2545F491 + 3) & _MASK or 3]
        for _ in range(8):  # stir the seed in
            self._next()

    def _next(self) -> int:
        x, y, z = self._state
        t = (x ^ (x << 11)) & _MASK
        x, y = y, z
        z = (z ^ (z >> 19) ^ t ^ (t >> 8)) & _MASK
        self._state = [x, y, z]
        return z

    def rn(self) -> int:
        """One random number 0-99."""
        return self._next() % 100

    def roll_percent(self, chance: int) -> tuple[bool, int]:
        """One roll: succeeds when the number is below ``chance``. Returns (success, number)."""
        n = self.rn()
        return n < chance, n

    def roll_true_hit(self, chance: int) -> tuple[bool, int]:
        """Two rolls averaged (the "true hit" used for Hit). Returns (success, averaged number)."""
        n = (self.rn() + self.rn()) // 2
        return n < chance, n




class Fe10Rng:
    """RFEE01's three-halfword chained shift register (``0x80089D68``)."""

    def __init__(self, seed: int = 0):
        self.seed = seed
        x = seed & 0xFFFFFFFF
        self._state = [((x * 0x41C6 + 0x4E6D) >> 1) & 0xFFFF or 1,
                       ((x * 0x3039 + 0x269E) >> 2) & 0xFFFF or 2,
                       ((x ^ 0xA5A5) + 0x1F3D) & 0xFFFF or 3]
        for _ in range(8):
            self._next()

    def _next(self) -> int:
        a, b, c = self._state
        carry = ((c << 1) | (1 if b & 0x8000 else 0)) & 0xFFFF
        value = (((b * 0x800) + (a >> 5)) & 0xFFFF) ^ carry
        self._state = [value, a, b]
        return value

    def rn(self) -> int:
        return (self._next() * 100) >> 16

    def roll_percent(self, chance: int) -> tuple[bool, int]:
        n = self.rn()
        return n < chance, n

    def roll_true_hit(self, chance: int) -> tuple[bool, int]:
        n = (self.rn() + self.rn()) // 2
        return n < chance, n
