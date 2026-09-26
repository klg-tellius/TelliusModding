# Event script documentation integration

## Published references

- [Game-side guide](https://klg-tellius.github.io/TelliusModding/tellius_archive.html#/events-scripting): module loading, dispatch, frames, trigger/state separation, timing, binary constraints and scope limits. Contains no app instructions.
- [Authoring tutorial](../app/script-tutorial.md): Python-style `.fe9s` lessons, concrete snippets, chapter overhaul, content dependencies, build and runtime validation.
- [Complete call index](../app/script-call-reference.md): all 406 native registrations, 89 startup helpers and two unregistered names. Native names/arities are cross-checked against `fe9_script_externs.tsv`; argument kinds remain inferred hints, not proven contracts.

## Archive integration guidance

The archive's event-script article should link the game-side guide and preserve the detailed format tables. App workflows belong in `docs/app/`, consistent with `doc.md`. Do not present compiler acceptance as runtime validation, or the complete registration index as complete behavioral documentation of every native handler.

The guide consolidates existing game findings; no new executable interpretation or Ghidra changes are claimed. Additional app-level findings are recorded in [known bugs](../app/known-bugs.md): global declarations do not allocate header storage, and two existing edited/backed-up files fail untouched binary preservation. No new unknown-byte interpretation is asserted, so `UNDECODED_BYTES.md` is unchanged.

## Validation scope

The tutorial's tagged examples are checked by `docs/app/check-script-examples.py` for compilation without warnings, binary re-read/write, and decompile/compile equality. The call index is reproducible with `docs/app/generate-script-reference.py`.

Existing toolchain tests pass except for the optional all-project corpus test's `C90.cmb` subcase. All other 43 current project scripts round-trip through both paths. The backed-up original C01 also fails binary equality and must not be described as a verified pristine retail fixture. No new tutorial recipe has been run in Dolphin during this documentation work.
