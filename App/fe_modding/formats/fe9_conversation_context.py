"""Resolve unambiguous TalkEvent continuation context from a chapter's CFG.

This follows both sides of branches; it never guesses the player's event flags.
Only message-owned layout/background/face state is propagated. It does not run
the event VM, recreate the map, or carry state from the previously selected UI row.
"""
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from .event_script import read_script_path
from .fe9_conversation import InitialContext, build_timeline, tokenize


@dataclass(frozen=True)
class ContextResolution:
    context: InitialContext | None
    description: str
    sources: tuple[str, ...] = ()


def resolve_context(script: Path, messages: dict[str, str], target: str) -> ContextResolution:
    if not script.is_file():
        return ContextResolution(None, "No chapter script available for initial context")
    contexts = set()
    evidence = set()
    compiled = {}
    for function in read_script_path(script):
        instructions = function.instructions
        sites = {i: instructions[i-1][2] for i, ins in enumerate(instructions)
                 if i and ins[1:3] == ['externCall', 'TalkEvent']
                 and instructions[i-1][1].startswith('pushstr')}
        if target not in sites.values():
            continue
        by_offset = {ins[0]: i for i, ins in enumerate(instructions)}
        pending = deque([(0, InitialContext(), '')])
        seen = set()
        while pending:
            index, context, source = pending.popleft()
            key = (index, context)
            if key in seen or index >= len(instructions):
                continue
            seen.add(key)
            if len(seen) > 10000:
                return ContextResolution(None, "Initial-context control flow exceeds the analysis limit")
            ins = instructions[index]
            if index in sites:
                mid = sites[index]
                if mid == target:
                    contexts.add(context)
                    if source: evidence.add(source)
                    continue
                if mid not in messages:
                    continue
                cache_key = (mid, context)
                if cache_key not in compiled:
                    state = build_timeline(messages[mid], context=context).events[-1].state
                    compiled[cache_key] = InitialContext(state.layout, state.background,
                                                        tuple(p.fid for p in state.portraits), context.aliases)
                context, source = compiled[cache_key], mid
            opcode = ins[1]
            if opcode in ('return', 'end'):
                continue
            if opcode.startswith('branch'):
                destination = by_offset.get(ins[0] + 1 + ins[2])
                if destination is not None:
                    pending.append((destination, context, source))
                if opcode == 'branch':
                    continue
            pending.append((index+1, context, source))
    if len(contexts) == 1:
        context = contexts.pop()
        description = (f"Context from {script.name}: " + ', '.join(sorted(evidence))) if evidence else "Message starts a conversation"
        return ContextResolution(context, description, tuple(sorted(evidence)))
    if contexts:
        return ContextResolution(None, "Initial context depends on event branches; choose it in Initial scene context")
    return ContextResolution(None, "No direct TalkEvent call found; set inherited scene context if needed")


def context_after_message(script: Path, messages: dict[str, str], source: str,
                          target: str) -> ContextResolution:
    """Preview override: inherit the selected predecessor's final scene."""
    if not source:
        return ContextResolution(InitialContext(), "No inherited message context")
    if source == target:
        raise ValueError("A message cannot inherit from itself")
    if source not in messages:
        raise ValueError(f"Message not found in this chapter: {source}")
    initial = resolve_context(script, messages, source)
    if initial.context is None and not any(t.code == 'R' for t in tokenize(messages[source])):
        raise ValueError(f"Cannot resolve {source}'s initial context: {initial.description}")
    state = build_timeline(messages[source], context=initial.context).events[-1].state
    context = InitialContext(state.layout, state.background, tuple(p.fid for p in state.portraits),
                             initial.context.aliases if initial.context else ())
    return ContextResolution(context, f"Preview inherits from {source}", (source,))
