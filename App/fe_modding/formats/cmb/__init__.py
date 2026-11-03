"""Event-script (``Scripts/CNN.cmb``) toolchain: a lossless symbolic model,
a binary reader/writer, an extern catalogue, and a decompiler/compiler for a
Python-style source language (``.fe9s``) - see ``docs/app/script-language.md``."""

from .binary import CmbError, read_cmb, read_cmb_path, write_cmb, write_cmb_path
from .compiler import CompileError, CompileResult, Diagnostic, compile_source
from .decompiler import decompile
from .model import Function, Instr, Label, RawStr, ScriptFile
