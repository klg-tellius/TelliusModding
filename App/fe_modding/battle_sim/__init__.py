"""Battle simulator: a forecast and a strike-by-strike fight between two units.

The package has no Tk code, so it can be tested and reused outside the
workspace:

- :mod:`.units` builds a :class:`~.units.Combatant` from ``FE8Data.bin``
  records (a character, or a bare class for a raw battle model). Every value
  is a plain field the user can change; nothing is written back to the game.
- :mod:`.rules_fe9` holds Path of Radiance's combat rules: the forecast
  (Atk, Hit, Crit, attack speed), strike counts and the skill effects.
- :mod:`.rng` is the seedable random-number stream.
- :mod:`.engine` runs the fight. The same code serves both modes: each
  question it asks ("does strike 3 hit?", "does Luna trigger?") goes to an
  outcome source, which is either the random stream or the user's fixed
  per-strike choices.
"""

from .engine import BattleLog, Decision, FixedOutcomes, RngOutcomes, Strike, simulate
from .rng import Fe9Rng
from .rules_fe9 import Fe9Rules, Forecast, SideForecast
from .units import Combatant, from_character, from_class

__all__ = [
    "BattleLog", "Combatant", "Decision", "Fe9Rng", "Fe9Rules", "FixedOutcomes", "Forecast", "RngOutcomes",
    "SideForecast", "Strike", "from_character", "from_class", "simulate",
]
