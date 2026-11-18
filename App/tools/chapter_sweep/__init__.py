"""Chapter sweep: play a whole Path of Radiance or Radiant Dawn story in Dolphin, unattended, and keep
the game's own save after every chapter.

``build`` makes a run tree whose every story chapter is won as soon as the player ends turn 1 (the
victory is set when the turn 1 enemy phase starts; a multipart chapter wins the current part).
``drive`` boots it from New Game and plays: it reads the emulated RAM (``tools/dolphin_ram``) to know
which game processes run, skips events, ends turn 1 from the map menu, answers the base,
preparations and save menus, and copies the save file into ``saves/`` each time the game writes it.
"""
