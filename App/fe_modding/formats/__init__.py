"""Parsers/serializers for Path of Radiance's internal file formats.

Reverse-engineered by hand (offsets found by manual inspection of the game's
files, not from any public documentation), refactored from a set of one-off
scripts into reusable functions. Every format here was only ever confirmed
against Path of Radiance; Radiant Dawn shares the engine but hasn't been
checked against these parsers yet, and offsets may differ.

Each module takes bytes/paths in and returns plain Python data out (dicts,
dataclasses, lists of tuples) rather than writing CSVs directly - use
csv.writer yourself, or a module's optional to_csv() helper, if you want a
file.
"""
