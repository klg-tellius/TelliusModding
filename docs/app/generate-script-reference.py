"""Generate reviewed FE9 function docs; optionally refresh examples with --scripts DIR."""
from collections import Counter, defaultdict
import argparse
import csv
from dataclasses import fields, is_dataclass
import hashlib
import json
from pathlib import Path
import sys
from script_reference_details import DETAILS

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def collect(directory, catalog):
    sys.path.insert(0, str(ROOT / 'App'))
    from fe_modding.formats.cmb import ast as A, read_cmb
    from fe_modding.formats.cmb.decompiler import Decompiler, expr_to_source

    def walk(value):
        if isinstance(value, A.Call):
            yield value
        if isinstance(value, (list, tuple)):
            for item in value:
                yield from walk(item)
        elif is_dataclass(value):
            for field in fields(value):
                yield from walk(getattr(value, field.name))

    paths = sorted(directory.glob('*.cmb'))
    if not paths:
        raise ValueError('No .cmb files in supplied directory')
    entries = defaultdict(lambda: dict(calls=[], argument_values=[], observed_calls=0))
    provenance, helpers = [], {}
    for path in paths:
        data = path.read_bytes()
        provenance.append(dict(file=path.name, sha256=hashlib.sha256(data).hexdigest(), size=len(data)))
        script = read_cmb(data)
        module = Decompiler(script).module()
        local_names = {f.name: raw.id_string for f, raw in zip(module.functions, script.functions)}
        for index, (function, raw) in enumerate(zip(module.functions, script.functions)):
            if path.name.lower() == 'startup.cmb' and raw.id_string in catalog and catalog[raw.id_string]['source'] == 'script':
                helpers[raw.id_string] = dict(function_index=index, argument_count=raw.num_args)
            for call in walk(function.body):
                name = call.name
                if not isinstance(name, str):
                    continue
                if not call.extern and name in local_names:
                    name = local_names[name]
                if name not in catalog:
                    continue
                entry = entries[name]
                entry['observed_calls'] += 1
                rendered = expr_to_source(call)
                sample = dict(file=path.name, function=raw.id_string or function.name, index=index, call=rendered)
                if len(entry['calls']) < 3 and not any(s['call'] == rendered for s in entry['calls']):
                    entry['calls'].append(sample)
                for i, arg in enumerate(call.args):
                    while len(entry['argument_values']) <= i:
                        entry['argument_values'].append([])
                    literal = isinstance(arg, (A.Num, A.Str)) or (isinstance(arg, A.UnOp) and isinstance(arg.operand, A.Num))
                    if literal:
                        value = expr_to_source(arg)
                        if value not in entry['argument_values'][i] and len(entry['argument_values'][i]) < 6:
                            entry['argument_values'][i].append(value)
    output = dict(scope='Locally available extracted project; includes edited files. Observations are not exhaustive valid ranges or pristine-retail certification.', files=provenance, helpers=dict(sorted(helpers.items())), calls=dict(sorted(entries.items())))
    (ROOT / 'research/main_dol/notes/script_reference_observations.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Recorded {len(paths)} file hashes, {len(helpers)} helper definitions, {len(entries)} call names.')


def cell(value):
    return str(value).replace('|', '&#124;').replace('\n', ' ')


def anchor(name):
    return 'call-' + name.lower().replace('_', '-')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scripts', type=Path, help='Refresh bounded examples from an extracted Scripts directory (read-only)')
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'App/fe_modding/formats/cmb/externs_fe9.json').read_text(encoding='utf-8'))['externs']
    if args.scripts:
        collect(args.scripts, catalog)
    evidence = json.loads((ROOT / 'research/main_dol/notes/script_reference_observations.json').read_text(encoding='utf-8'))
    with (ROOT / 'research/main_dol/fe9_script_externs.tsv').open(encoding='utf-8') as stream:
        natives = {r['name']: r for r in csv.DictReader(stream, delimiter='\t')}
    assert {n for n,e in catalog.items() if e['source'] == 'native'} == set(natives)
    assert set(DETAILS) <= set(catalog), sorted(set(DETAILS) - set(catalog))
    assert len({anchor(n) for n in catalog}) == len(catalog), 'Anchor collision'
    for name, entry in catalog.items():
        if name in natives:
            assert entry['argc'] == int(natives[name]['argc']), name
        if name in DETAILS and entry['argc'] >= 0:
            assert len(DETAILS[name]['args']) == entry['argc'], (name, len(DETAILS[name]['args']), entry['argc'])
        if entry['source'] == 'script':
            assert name in DETAILS, f'Missing helper description: {name}'
            assert evidence['helpers'][name]['argument_count'] == entry['argc'], name
    reviewed = Counter(catalog[n]['source'] for n in DETAILS)
    lines = ['# Path of Radiance script function reference', '',
        'Companion to the [Python-style scripting tutorial](script-tutorial.md). These calls are for US Path of Radiance.', '',
        '## Calling functions', '',
        'Arguments are positional: write them in the order shown. The names in signatures explain their purpose; keyword arguments are not supported. Calls are case-sensitive.', '',
        'A return value is not necessarily a success code. Some calls return a unit handle, an index, a count, or a sentinel such as -1. Calls that start animations may return before the animation finishes; use the matching wait call.', '',
        '## Shared conventions', '',
        '- **Units:** use the numeric handle returned by UnitGetByPID or another unit lookup. A handle is neither a PID string nor a memory address. Zero means no unit. Do not invent handles or keep them after their unit has been removed.',
        '- **Force IDs:** 0 player, 1 enemy, 2 orderable ally, 3 other/green, 4 free pool, 5 player reserve, 6 inactive/death-flagged, 7 special inactive. These are different from phase IDs.',
        '- **Coordinates:** map-grid coordinates include borders. Screen and world-map coordinates follow their own conventions.',
        '- **Output arguments:** pass &variable where a call writes a result into a local variable. Reserve each output before calling.',
        '- **Flags:** register before use and preserve registration order for save compatibility. See the tutorial’s named-flag lesson.', '',
        '## Function index', '', '| Function | Purpose |', '|---|---|']
    for name, detail in sorted(DETAILS.items()):
        lines.append(f"| [{name}](#{anchor(name)}) | {cell(detail['behavior'])} |")
    lines += ['', '## Detailed entries', '']
    for name, detail in sorted(DETAILS.items()):
        entry = catalog[name]
        names = [a[0] for a in detail['args']]
        lines += [f'<a id="{anchor(name)}"></a>', f'### {name}', '',
                  f"`{name}({', '.join(names)})`", '', detail['behavior'], '']
        if names:
            lines += ['| Argument | Meaning and restrictions |', '|---|---|']
            for arg_name, meaning in detail['args']:
                lines.append(f'| `{arg_name}` | {cell(meaning)} |')
            lines.append('')
        else:
            lines += ['**Arguments:** none.', '']
        lines += ['**Returns:** ' + detail['returns'], '']
        if detail['notes']:
            lines += ['**Usage:** ' + detail['notes'], '']
        if detail.get('example'):
            body = detail['example'].replace('var ', '')
            example = f'def example_{name.lower()}():\n' + '\n'.join('    ' + row for row in body.splitlines())
            lines += ['```fe9s', example, '```', '']
        if entry['source'] == 'script':
            lines += ['Requires the shared `startup.cmb` helpers to be loaded.', '']
        lines += ['[Back to index](#function-index)', '']
    assert set(DETAILS) == set(catalog), sorted(set(catalog) - set(DETAILS))
    (HERE / 'script-call-reference.md').write_text('\n'.join(lines),encoding='utf-8', newline='\n')
    print(f'Wrote {len(DETAILS)} entries with named arguments and descriptions.')


if __name__ == '__main__':
    main()
