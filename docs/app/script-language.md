# Script language (`.fe9s`)

For a guided course, read [Modding chapter events](script-tutorial.md). The [complete call index](script-call-reference.md) lists every catalogued native and shared helper, with argument-count evidence and inferred-kind caveats.

Chapter event scripts (`Scripts/CNN.cmb`) are edited as Python-style source. The **Scripts** tab decompiles the chapter's `.cmb` into this language, and saving compiles it back. An untouched script compiles back to the original bytes (checked on all 43 Path of Radiance scripts and on the 50 Radiant Dawn scripts of each region), so you only change what you edit. Radiant Dawn uses the same language with a few additions; see [Radiant Dawn](#radiant-dawn).

Tested in game (Dolphin, Prologue): a new function with a new flag, compiled from source, fired on its turn and gave Ike an item.

You never handle the stack, branch offsets or string-pool offsets: the compiler generates them, choosing the same instructions the game's own compiler used. For the format itself, see `research/CHAPTER_DATA_NOTES.md` §5.3.

## A function

```python
# Anything after # is a comment.
@on_phase(turn_from=2, turn_to=2, phase="enemy")   # when it runs (see Triggers)
def reinforcements():
    if not get("reinforcements_done"):
        var boss = UnitGetByPID("PID_ZAWANA")        # a local variable
        if boss:
            TalkEvent("MS_05_EV_03")
        set("reinforcements_done")
```

- One file holds every function of the chapter, in order. Their position is the game's function index.
- `def name(a, b):` declares arguments. A function without `@export` is anonymous in the game file; `name` is only used in this source.
- `@export` gives the function a global name: the game registers it when the chapter loads, and any loaded script can call it by that name. `@export("Name")` sets the global name when it differs from the `def` name. The engine calls `Startup`, `RegistLocationTT`, `Opening0`, `Opening1`, `Opening2` and `Opening18_2`–`Opening18_4` itself by name; defining `Opening1` gives the chapter a base and `Opening2` a preparations screen (see `research/CHAPTER_DATA_NOTES.md`, "How a chapter starts and ends").
- `@naked` skips the implicit `return 0` at the end (used with `asm:` blocks).

## Triggers

A decorator sets the function's trigger type and parameters. The editor's **Function** form writes it for you.

| Decorator | Runs when | Parameters |
|---|---|---|
| *(none)* | Only when called | — |
| `@on_complete` / `@on_gameover` | Map goal achieved / failed | `flag` |
| `@before_phase` / `@on_phase` | Before / after a phase banner | `turn_from`, `turn_to` (0 = every turn), `phase` = `"player"`, `"enemy"`, `"partner"` |
| `@on_area` | A unit enters a zone | `x1`, `y1`, `x2`, `y2`, `side` (`"player"`/`"enemy"`), `name` |
| `@on_location` | A unit acts on a tile | `x`, `y`, `action` (`"visit"`, `"door"`, `"chest"`, `"seize"`, `"escape"`, `"destroy_house"`, `"arrive"`, `"other"`), `name` |
| `@after_action` | After every action | — |
| `@on_talk` / `@on_battle` | Two units talk / fight | `pid1`, `pid2`, `flag`, `name` |
| `@on_death` / `@on_death_map` | A unit dies (in battle / back on the map) | `pid` |
| `@on_scenario_end` | Scenario complete | `name` |
| `@on_support` | Support conversation | `pid1`, `pid2`, `level` |
| `@on_base_talk` | Base conversation | `flag`, `mpid`, `stars` |
| `@on_select` | Selecting a unit | — |
| `@trigger(type, p1, p2, …)` | Raw form, any type and parameter list | — |

`name` parameters are debug labels the game never shows. `None` means "no value".

## Statements

| Source | Meaning |
|---|---|
| `Name(args)` | Call a game function or another function of this script. Every call returns a value; as a statement it is discarded. |
| `x = expr`, `x += expr` (`-= *= /= %= &= \|= ^= <<= >>=`) | Assignment. The first assignment declares a local. |
| `var x = expr` | Declaration with a value, compiled the way the original scripts compile declarations. Prefer `x = expr` inside loops. |
| `var a, b, buf[4]` | Reserve locals without code (`buf[4]` reserves 4 slots, used as `buf[i]`). |
| `if` / `elif` / `else`, `while cond:`, `while True:`, `break`, `continue` | Control flow. |
| `do:` block, then `while cond` (no colon) on the line after it | Loop that runs its body once before testing `cond`. `C11` asks the Volke question this way. `continue` jumps to the test. |
| `return expr` / `return` | Return a value (default 0). |
| `yield` | Pause the script until the game resumes it (between frames/events). |
| `printf("fmt", args…)` | Debug print (does nothing in the retail game). |
| `pass` | Nothing. |
| `label:` / `goto label` / `goto label if cond` / `goto label unless cond` | Raw jumps, for code that doesn't fit `if`/`while`. |
| `asm:` block | Raw instructions, one per line (`push8 3`, `externCall "WaitM", 1`, `branchz L1`, `L1:`). |
| `switch expr:` with `case a, b:` and `default:` blocks | Radiant Dawn only. Compares the value with each case's values in turn; `break` leaves the switch. A case without `break` goes on to the next case's comparisons. `default:` comes last. |
| `x++`, `x--`, `++x`, `--x` | Radiant Dawn only. Add or subtract 1; as an expression, `x++` is the value before and `++x` the value after (`BMSetLoseTerm(n++, "ML_...")`). |

## Expressions

- Numbers (`12`, `0x1F`), strings (`"PID_IKE"`, escapes `\n \t \" \\ \xNN`), `True`/`False`/`None` (1/0/0).
- Variables: arguments, locals, globals (`global name @ slot` at the top of the file), array elements `buf[i]`, addresses `&x` (for game functions that write into a variable).
- Operators, loosest to tightest: `or`, `and`, `not`, comparisons `== != < <= > >=`, `|`, `^`, `&`, `<< >>`, `+ -`, `* / %`, unary `- ~ &`. `and`/`or` short-circuit.
- `(x := expr)` assigns and uses the value, e.g. `while (u := ForceGetFirst(1)):`.
- `streq(a, b)` / `strne(a, b)` compare two strings.
- `extern("Name", args…)` forces a call to a global name when a function of this script has the same name.
- `lit(-1)` and `strofs(n)` appear only in decompiled output for literal patterns the original compiler never produced.

This is a custom VM language, not Python: use double-quoted strings, integer arithmetic, and explicit conditionals when choosing values. Short-circuit `and`/`or` paths normalize to 0/1 rather than preserving Python-style operand values. A global declaration names one of the engine's 32 shared slots (0–31); compiling sets the file's reservation to the highest declared slot + 1. Globals are not saved and start with leftover memory, so write before reading. See [advanced storage and encoding limits](script-tutorial.md#17-advanced-storage-and-assembly).

## Game functions

There are 406 native functions plus the 89 helpers `startup.cmb` exports. The editor completes their names as you type, shows each signature (argument count and kinds inferred from the vanilla scripts) and flags an unknown name in red. **Insert call…** lists them all, with how often vanilla uses each, and fills the arguments with pickers (characters, items, classes, messages, music).

Compile checks:
- The wrong number of arguments to a known function is an error.
- An unknown name is a warning: the game silently returns 0 for a name it doesn't know. `NormalOnly` and `Easy`, called by vanilla scripts, are two such names.

## Radiant Dawn

Radiant Dawn's scripts use the same source language. The compiler writes Radiant Dawn's own instructions for the same source (an assignment as `assign`, `return 0`/`return 1` as `ret0`/`ret1`, `switch` with `dup`), so decompiling a vanilla script and saving it gives back the original bytes. `switch` and `++`/`--` only compile for Radiant Dawn: Path of Radiance's interpreter has no instruction for them.

Its triggers differ from Path of Radiance's:

| Decorator | Runs when | Parameters |
|---|---|---|
| `@on_base_talk` | Base conversation | `name` (picks `CONV_INFO_DATA_<chapter>_<name>` in FE10Conversation.cms), `flag` |
| `@on_talk` / `@on_battle` | Two units talk / fight | `pid1`, `pid2`, `flag`, `name`: `name` is a one-time flag, or the name of a function of the script that must return non-zero for the event to run |
| `@on_rescue` | Rescue command | `pid1` (rescuer), `pid2` (rescued), `flag` (1 = either way), `name` (one-time flag) |
| `@on_give_take` | Give / Take commands | `pid1` (carrier), `pid2` (other unit), `pid3` (carried unit), `flag`, `name` |
| `@on_move_through` | A moving unit enters a tile; its move stops there | `pid`, `x`, `y` (65535 = any), `name` (flag or condition function, called with x, y) |
| `@on_epilogue` | A character's epilogue entry (the ending) | `pid`, `name` (flag or condition function) |
| `@on_named` | Run by name | `name` |
| `@on_location` | A unit acts on a tile | actions `"visit"`, `"door"`, `"chest"`, `"seize"`, `"escape"`, `"destroy"`, `"arrive"`, `"light_torch"`, `"open"`, `"put_out_torch"` (other numbers stay numbers) |

`phase` and `side` take `"player"`, `"enemy"` or `"other"`. `None` in a character parameter means anyone.

There are 656 native functions (each with a description in the editor) plus the 511 helpers Radiant Dawn's `startup.cmb` exports; `WaitM`, `WaitF` and `InstantDispos`, natives in Path of Radiance, are helpers there. Vanilla still calls `StaffRoll`, `WarRecord` and `VOICEAllStop` with one argument more than they take; for natives a wrong argument count is a warning in Radiant Dawn, and the extra value is ignored. The flag table has 128 slots. Radiant Dawn's difficulty functions use its own numbering: `Normal()`, `Hard()`, `Maniac()`, `Easy()`.

Not tested in game yet for Radiant Dawn: a compiled script change has not been run in Dolphin.

## Editing in the app

- The **Function** drop-down (pick which function to edit; it also follows the cursor), the **Function** form (name, description, export, trigger and its parameters) and **New / Duplicate / Delete** all edit the source text. **Apply to code** rewrites the selected function's decorators and renames its calls. The description is stored as the `# ...` comment lines just above the function (the decompiler's own `# function N - ...` line is not part of it), and its first line is shown next to the name in the drop-down.
- **Check** compiles without saving. Errors and warnings are listed under the editor; click one to jump to its line.
- On Radiant Dawn, which has no chapter pages yet, open scripts from **Assets › Scripts**; the flags are in **Game Data › Flags**.
- **Save** compiles and writes `Scripts/CNN.cmb`. The first save keeps the extracted file in the project's originals. It also stores your source, with its names and comments, in `script_sources/CNN.fe9s`. That source is reloaded while it still matches the `.cmb`; if the `.cmb` changed elsewhere, the file is decompiled again and the old source is kept as `.fe9s.bak`.
- The **Bytecode** tab shows the selected function's compiled instructions.
- **Revert to file** discards the source and decompiles the `.cmb` again.

Deleting a function moves the ones after it up one index. Calls between this script's functions are compiled by name, so they stay right.

## Command line

Run from `App/`:

```bash
python -m fe_modding.formats.cmb decompile C05.cmb -o c05.fe9s
```

```bash
python -m fe_modding.formats.cmb compile c05.fe9s -o C05.cmb --base C05.cmb
```

```bash
python -m fe_modding.formats.cmb roundtrip <extracted>/files/Scripts
```

`--base` keeps the original file's header, string order and padding, so unchanged content stays byte-identical.
