"""Frame samples for the decoded part of a .ga particle table.

The curve values and stage windows come from the game format. Position
integration and billboard geometry are preview approximations until compared
against the game's particle draw path frame by frame.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import animation


@dataclass(frozen=True)
class Stage:
    emitter: animation.ParticleEmitterLayout
    layout: animation.ParticleStageLayout
    curves: tuple[tuple[int, tuple[tuple[int, float], ...]], ...]


@dataclass(frozen=True)
class Sample:
    name_path: str
    material_index: int
    draw_flags: int
    position: tuple[float, float, float]
    scale: tuple[float, float]
    rotation_degrees: float
    color: tuple[float, float, float]
    alpha: float
    velocity: tuple[float, float, float]


def read_stages(data: bytes) -> tuple[Stage, ...]:
    layout = animation.read_particle_table_layout(data)
    if layout is None:
        return ()
    stages = []
    for emitter in layout.emitters:
        for index in range(emitter.stage_count):
            stage = animation.read_particle_stage(data, emitter, index)
            curves = tuple(
                (curve.channel, animation.read_particle_curve_keys(data, emitter, curve))
                for curve in (animation.read_particle_curve(data, emitter, n)
                              for n in range(stage.first_curve, stage.first_curve + stage.curve_count))
            )
            stages.append(Stage(emitter, stage, curves))
    return tuple(stages)


def _integrate(keys: tuple[tuple[int, float], ...], time: float) -> float:
    """Integral of the clamped, linearly interpolated velocity curve."""
    if time <= 0 or not keys:
        return 0.0
    cuts = [0.0, *(float(frame) for frame, _ in keys if 0 < frame < time), time]
    return sum((animation.sample_particle_curve(keys, a) +
                animation.sample_particle_curve(keys, b)) * (b - a) / 2
               for a, b in zip(cuts, cuts[1:]))


def sample(stages: tuple[Stage, ...], frame: float) -> tuple[Sample, ...]:
    result = []
    for stage in stages:
        layout, emitter = stage.layout, stage.emitter
        if not layout.start_frame <= frame <= layout.end_frame:
            continue
        local = max(0.0, frame - layout.start_frame)
        channels = {channel: keys for channel, keys in stage.curves}

        def value(channel: int, default: float) -> float:
            keys = channels.get(channel)
            return animation.sample_particle_curve(keys, local) if keys else default

        velocity = tuple(value(i, 0.0) for i in range(3))
        position = tuple(layout.initial_position[i] + _integrate(channels.get(i, ()), local)
                         for i in range(3))
        common_scale = value(3, 1.0)
        scale = (max(0.0, value(8, emitter.initial_scale_st[0] * common_scale)),
                 max(0.0, value(9, emitter.initial_scale_st[1] * common_scale)))
        color = tuple(max(0.0, min(1.0, value(i, 1.0))) for i in (5, 6, 7))
        result.append(Sample(emitter.name_path, emitter.material_index, emitter.draw_flags,
                             position, scale, emitter.initial_rotation_degrees + value(10, 0.0),
                             color, max(0.0, min(1.0, value(4, 1.0))), velocity))
    return tuple(result)
