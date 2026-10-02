"""Chapter playthrough: play a chapter on its top-down map without the game.

The package has no Tk code. It turns a chapter's files (map, deployment,
``FE8Data.bin``, event script, ``cp_data.bin``, messages) into a
:class:`~.world.World` (what never changes during play) and a
:class:`~.state.GameState` (everything that does), and runs the game on the
state one small step at a time:

- :mod:`.movement` - movement ranges and paths (terrain costs per movement
  type, map links, blocking units);
- :mod:`.combat` - a unit's battle numbers, through :mod:`fe_modding.battle_sim`;
- :mod:`.actions` - the player's commands (move, attack, shove, canto, visit,
  talk, wait) and what they change;
- :mod:`.engine` - the task queue: phases, triggers, event scripts, messages
  and AI runs, each advanced one line per step;
- :mod:`.simulation` - the history of states, so play can be stepped back and
  forward and replayed from any point.

The whole :class:`~.state.GameState` is plain data (no generators, no
closures), so a snapshot is a deep copy and rewinding restores one.
"""

from .simulation import Simulation
from .state import GameState, SimUnit
from .world import World

__all__ = ["GameState", "SimUnit", "Simulation", "World"]
