"""GPU (wgpu / WebGPU) renderer behind ``model_viewer._ModelCanvas``.

The numpy rasterizer in ``_ModelCanvas._rasterize()`` walks every triangle in
Python, which costs hundreds of milliseconds per frame on a merged chapter
scene (terrain + every ``mapbuildinst`` prop). This module draws the same
triangles on the GPU instead: geometry and textures are uploaded once per
model, and each frame only a small camera uniform changes.

wgpu was picked for portability: it runs on Vulkan/DX12 on Windows, Metal on
macOS (where OpenGL is deprecated) and Vulkan/GL on Linux, ships
platform wheels that don't depend on the Python ABI, and renders offscreen,
so there is no native-window integration with Tk to get wrong on some OS.
The frame is read back and shown as a single Tk image, like the CPU path.

The shader reproduces the CPU renderer's rules:

* flat per-face brightness ``0.35 + 0.65 * max(-nz, 0)`` and the
  "stored face normal faces away" backface rule (independent of winding);
* ``model_viewer._sample_texture_layers()``'s layer blend, nearest
  filtering, GX wrap modes (clamp / repeat / mirror) and ``flip_v``;
* the opaque / translucent / additive split of the CPU blend code.

wgpu is optional: ``create_renderer()`` returns ``None`` when it is missing or
no adapter is available, and the canvas keeps using the numpy rasterizer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from PIL import Image

try:
    import wgpu
except ImportError:  # optional dependency, see requirements.txt
    wgpu = None

log = logging.getLogger(__name__)

MAX_LAYERS = 4
BACKGROUND = (43, 43, 43)
MSAA_SAMPLES = 4

# vertex: position(3) normal(3) color(3) alpha(1) uv x MAX_LAYERS (8)
_FLOATS_PER_VERTEX = 19
#: Vertex float 18: the shape's cull mode (model_viewer._chunk_cull).
CULL_CODES = {"back": 0.0, "none": 1.0, "front": 2.0}

_ROLE_CODES = {
    "callback_uv2_detail": 1,
    "map_selector": 2,
    "map_projected_light": 3,
    "light": 4,
}

_WRAP_MODES = {0: "clamp-to-edge", 1: "repeat", 2: "mirror-repeat"}

_SHADER = """
struct Camera {
    rot0: vec4<f32>,
    rot1: vec4<f32>,
    rot2: vec4<f32>,
    center: vec4<f32>,
    // x/y: world units -> NDC (sign included), z: depth scale,
    // w: perspective (0 = orthographic, else 1 / eye distance)
    scale: vec4<f32>,
};

struct Batch {
    info: vec4<u32>,   // x = layer count (0 = flat colour)
    roles: vec4<u32>,
    flips: vec4<u32>,
    scales: array<vec4<f32>, 4>,
};

@group(0) @binding(0) var<uniform> camera: Camera;
@group(1) @binding(0) var<uniform> batch: Batch;
@group(1) @binding(1) var t0: texture_2d<f32>;
@group(1) @binding(2) var t1: texture_2d<f32>;
@group(1) @binding(3) var t2: texture_2d<f32>;
@group(1) @binding(4) var t3: texture_2d<f32>;
@group(1) @binding(5) var s0: sampler;
@group(1) @binding(6) var s1: sampler;
@group(1) @binding(7) var s2: sampler;
@group(1) @binding(8) var s3: sampler;

struct VIn {
    @location(0) position: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) color: vec3<f32>,
    @location(3) alpha: f32,
    @location(4) uv01: vec4<f32>,
    @location(5) uv23: vec4<f32>,
    @location(6) cull: f32,  // 0 back faces, 1 none (both sides), 2 front faces
};

struct VOut {
    @builtin(position) clip: vec4<f32>,
    @location(0) color: vec3<f32>,
    @location(1) alpha: f32,
    @location(2) brightness: f32,
    @location(3) uv01: vec4<f32>,
    @location(4) uv23: vec4<f32>,
};

// model_viewer.PERSPECTIVE_NEAR
const PERSPECTIVE_NEAR: f32 = 0.05;

fn rotate(p: vec3<f32>) -> vec3<f32> {
    return vec3<f32>(dot(camera.rot0.xyz, p), dot(camera.rot1.xyz, p), dot(camera.rot2.xyz, p));
}

@vertex
fn vs_main(v: VIn) -> VOut {
    var out: VOut;
    let r = rotate(v.position - camera.center.xyz);
    let n = rotate(v.normal);
    let nz = n.z;
    // facing: the normal against the ray from the eye. The eye sits at z = -1 / w-scale under
    // perspective (the ray, scaled by w-scale: r * w + (0, 0, 1)); orthographic rays are all +Z.
    // The normal is the face's, so all three corners agree (n . (corner - eye) is the same)
    var facing = nz;
    if (camera.scale.w > 0.0) {
        facing = dot(n, r * camera.scale.w + vec3<f32>(0.0, 0.0, 1.0));
    }
    // an alpha below -0.5 marks an effect triangle (battle_stage.effect_alpha): unlit, seen from both sides,
    // its real alpha being -1 - value
    let effect = v.alpha < -0.5;
    if (effect || (v.cull > 0.5 && v.cull < 1.5)) {
        facing = -1.0;  // drawn from both sides
    } else if (v.cull >= 1.5) {
        facing = -facing;  // front faces culled
    }
    // perspective divisor (1 when orthographic)
    let w = 1.0 + r.z * camera.scale.w;
    // depth = 1 - near / w under perspective: clip z stays linear in the
    // position, so the clip stage cuts triangles crossing the near plane
    // (w = near) correctly instead of stretching them
    var z = 0.5 + r.z * camera.scale.z;
    if (camera.scale.w > 0.0) {
        z = w - PERSPECTIVE_NEAR;
    }
    // a corner behind the eye is never culled here: the clip stage cuts that triangle at the near
    // plane (corners can disagree when the stored normal is not exactly the face's)
    if (facing >= 0.0 && (camera.scale.w <= 0.0 || w > PERSPECTIVE_NEAR)) {
        // back-facing: the whole triangle shares this normal, so all three
        // vertices land outside the clip volume and it is dropped
        out.clip = vec4<f32>(2.0, 2.0, 2.0, 1.0);
    } else {
        out.clip = vec4<f32>(r.x * camera.scale.x, r.y * camera.scale.y, z, w);
    }
    out.color = v.color / 255.0;
    out.alpha = v.alpha;
    out.brightness = 0.35 + 0.65 * max(-nz, 0.0);
    if (effect) {
        out.alpha = -1.0 - v.alpha;
        out.brightness = 1.0;
    }
    out.uv01 = v.uv01;
    out.uv23 = v.uv23;
    return out;
}

fn layer_uv(uv: vec2<f32>, i: u32) -> vec2<f32> {
    if (batch.flips[i] != 0u) {
        return vec2<f32>(uv.x, 1.0 - uv.y);
    }
    return uv;
}

fn shade(f: VOut) -> vec4<f32> {
    let n = batch.info.x;
    if (n == 0u) {
        return vec4<f32>(f.color * f.brightness, f.alpha);
    }
    var samples: array<vec4<f32>, 4>;
    samples[0] = textureSampleLevel(t0, s0, layer_uv(f.uv01.xy, 0u), 0.0);
    samples[1] = textureSampleLevel(t1, s1, layer_uv(f.uv01.zw, 1u), 0.0);
    samples[2] = textureSampleLevel(t2, s2, layer_uv(f.uv23.xy, 2u), 0.0);
    samples[3] = textureSampleLevel(t3, s3, layer_uv(f.uv23.zw, 3u), 0.0);

    var sampled = samples[0].rgb * batch.scales[0].rgb;
    let alpha = samples[0].a;
    var pending = false;
    var pending_detail = vec3<f32>(0.0);
    var saw_selector = false;
    for (var i = 1u; i < n; i = i + 1u) {
        let s = samples[i];
        let role = batch.roles[i];
        if (role == 1u) {
            pending_detail = s.rgb * batch.scales[i].rgb;
            pending = true;
        } else if (role == 2u) {
            saw_selector = true;
            if (pending) {
                let selector = (s.r + s.g + s.b) / 3.0;
                sampled = mix(sampled, pending_detail, selector);
                pending = false;
            }
        } else if (role == 3u) {
            sampled = sampled * s.rgb;
        } else if (role == 4u) {
            let luma = (s.r + s.g + s.b) / 3.0;
            if (pending && !saw_selector) {
                let mask = clamp((1.0 - luma - 0.20) * 3.0, 0.0, 0.60);
                sampled = mix(sampled, pending_detail, mask);
            }
            sampled = sampled * (0.7 + luma * 0.6);
        }
    }
    return vec4<f32>(clamp(sampled * f.brightness, vec3<f32>(0.0), vec3<f32>(1.0)), alpha * f.alpha);
}

@fragment
fn fs_opaque(f: VOut) -> @location(0) vec4<f32> {
    let c = shade(f);
    if (c.a < 0.995) {
        discard;
    }
    return vec4<f32>(c.rgb, 1.0);
}

@fragment
fn fs_translucent(f: VOut) -> @location(0) vec4<f32> {
    let c = shade(f);
    if (c.a <= 0.001 || c.a >= 0.995) {
        discard;
    }
    return c;
}

@fragment
fn fs_additive(f: VOut) -> @location(0) vec4<f32> {
    let c = shade(f);
    if (c.a <= 0.001) {
        discard;
    }
    return c;
}
"""


@dataclass
class _Batch:
    first_vertex: int
    vertex_count: int
    additive: bool
    bind_group: object


class _Device:
    """The process-wide wgpu device and everything that doesn't depend on a
    particular model: shader, pipelines, layouts, samplers, a dummy texture.
    Created lazily - requesting an adapter takes around a second."""

    def __init__(self) -> None:
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        if adapter is None:
            raise RuntimeError("no GPU adapter")
        self.adapter_info = adapter.info
        self.device = adapter.request_device_sync()
        device = self.device

        shader = device.create_shader_module(code=_SHADER)
        self.camera_layout = device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.VERTEX,
                    "buffer": {"type": wgpu.BufferBindingType.uniform},
                }
            ]
        )
        batch_entries = [
            {
                "binding": 0,
                "visibility": wgpu.ShaderStage.FRAGMENT,
                "buffer": {"type": wgpu.BufferBindingType.uniform},
            }
        ]
        for i in range(MAX_LAYERS):
            batch_entries.append(
                {
                    "binding": 1 + i,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "texture": {
                        "sample_type": wgpu.TextureSampleType.float,
                        "view_dimension": wgpu.TextureViewDimension.d2,
                    },
                }
            )
            batch_entries.append(
                {
                    "binding": 1 + MAX_LAYERS + i,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "sampler": {"type": wgpu.SamplerBindingType.filtering},
                }
            )
        self.batch_layout = device.create_bind_group_layout(entries=batch_entries)
        pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[self.camera_layout, self.batch_layout])

        vertex_state = {
            "module": shader,
            "entry_point": "vs_main",
            "buffers": [
                {
                    "array_stride": _FLOATS_PER_VERTEX * 4,
                    "step_mode": wgpu.VertexStepMode.vertex,
                    "attributes": [
                        {"format": wgpu.VertexFormat.float32x3, "offset": 0, "shader_location": 0},
                        {"format": wgpu.VertexFormat.float32x3, "offset": 12, "shader_location": 1},
                        {"format": wgpu.VertexFormat.float32x3, "offset": 24, "shader_location": 2},
                        {"format": wgpu.VertexFormat.float32, "offset": 36, "shader_location": 3},
                        {"format": wgpu.VertexFormat.float32x4, "offset": 40, "shader_location": 4},
                        {"format": wgpu.VertexFormat.float32x4, "offset": 56, "shader_location": 5},
                        {"format": wgpu.VertexFormat.float32, "offset": 72, "shader_location": 6},
                    ],
                }
            ],
        }

        def pipeline(entry_point: str, blend: dict | None):
            target = {"format": wgpu.TextureFormat.rgba8unorm}
            if blend is not None:
                target["blend"] = blend
            return device.create_render_pipeline(
                layout=pipeline_layout,
                vertex=vertex_state,
                primitive={
                    "topology": wgpu.PrimitiveTopology.triangle_list,
                    "cull_mode": wgpu.CullMode.none,
                },
                depth_stencil={
                    "format": wgpu.TextureFormat.depth32float,
                    "depth_write_enabled": True,
                    "depth_compare": wgpu.CompareFunction.less,
                },
                multisample={"count": MSAA_SAMPLES},
                fragment={"module": shader, "entry_point": entry_point, "targets": [target]},
            )

        alpha_keep = {"operation": "add", "src_factor": "zero", "dst_factor": "one"}
        self.opaque = pipeline("fs_opaque", None)
        self.translucent = pipeline(
            "fs_translucent",
            {
                "color": {"operation": "add", "src_factor": "src-alpha", "dst_factor": "one-minus-src-alpha"},
                "alpha": alpha_keep,
            },
        )
        self.additive = pipeline(
            "fs_additive",
            {"color": {"operation": "add", "src_factor": "src-alpha", "dst_factor": "one"}, "alpha": alpha_keep},
        )

        self._samplers: dict[tuple[int, int], object] = {}
        dummy = device.create_texture(
            size=(1, 1, 1),
            format=wgpu.TextureFormat.rgba8unorm,
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        )
        device.queue.write_texture(
            {"texture": dummy}, np.full(4, 255, np.uint8), {"bytes_per_row": 4}, (1, 1, 1)
        )
        self.dummy_view = dummy.create_view()

    def sampler(self, wrap_s: int, wrap_t: int):
        key = (wrap_s, wrap_t)
        if key not in self._samplers:
            self._samplers[key] = self.device.create_sampler(
                address_mode_u=_WRAP_MODES.get(wrap_s, "repeat"),
                address_mode_v=_WRAP_MODES.get(wrap_t, "repeat"),
                mag_filter="nearest",
                min_filter="nearest",
            )
        return self._samplers[key]


_shared_device: _Device | None = None
_device_failed = False


def _get_device() -> _Device | None:
    global _shared_device, _device_failed
    if _shared_device is None and not _device_failed:
        if wgpu is None:
            _device_failed = True
            log.info("wgpu not installed - 3D views use the CPU rasterizer")
            return None
        try:
            _shared_device = _Device()
        except Exception:  # noqa: BLE001 - any adapter/driver failure means "use the CPU path"
            _device_failed = True
            log.warning("GPU renderer unavailable - 3D views use the CPU rasterizer", exc_info=True)
    return _shared_device


def create_renderer() -> "GpuSceneRenderer | None":
    """A renderer on the shared device, or ``None`` when no GPU path is
    available (wgpu missing, no adapter, driver error)."""
    shared = _get_device()
    return GpuSceneRenderer(shared) if shared is not None else None


def _layer_list(tri) -> list:
    """(texture, role, flip_v, color_scale, wrap_s, wrap_t, uv) per layer, in
    the same order ``_ModelCanvas._rasterize()`` blends them."""
    if tri.texture_layers:
        return [
            (layer.texture, layer.role, layer.flip_v, tuple(layer.color_scale), layer.wrap_s, layer.wrap_t, layer.uv)
            for layer in tri.texture_layers[:MAX_LAYERS]
        ]
    if tri.texture is not None and tri.uv is not None:
        return [(tri.texture, "diffuse", False, (1.0, 1.0, 1.0), 1, 1, tri.uv)]
    return []


class GpuSceneRenderer:
    """One canvas's GPU state: its model's vertex buffer, textures and batches
    plus render targets sized to the canvas."""

    def __init__(self, shared: _Device) -> None:
        self._shared = shared
        self._device = shared.device
        self._camera_buffer = self._device.create_buffer(
            size=5 * 16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
        )
        self._camera_group = self._device.create_bind_group(
            layout=shared.camera_layout,
            entries=[{"binding": 0, "resource": {"buffer": self._camera_buffer}}],
        )
        self._batches: list[_Batch] = []
        self._vertex_buffer = None
        self._vertices: np.ndarray | None = None
        self._order: np.ndarray | None = None
        self._textures: dict[int, object] = {}
        self._size: tuple[int, int] | None = None
        self._targets: tuple | None = None

    # -- model --------------------------------------------------------------
    def set_triangles(self, triangles: list) -> None:
        """Upload ``triangles`` (``model_viewer._Triangle``). Triangles are
        grouped into draw batches by blend mode and texture-layer setup; the
        batch order is kept so ``update_positions()`` can rewrite geometry
        for a posed frame without regrouping."""
        self._batches = []
        self._textures = {}
        self._vertex_buffer = None
        self._vertices = None
        self._order = None
        if not triangles:
            return

        groups: dict[tuple, list[int]] = {}
        layers_by_tri = []
        for index, tri in enumerate(triangles):
            layers = _layer_list(tri)
            layers_by_tri.append(layers)
            key = (
                tri.blend_mode == "additive",
                tuple((id(t), role, flip, scale, ws, wt) for t, role, flip, scale, ws, wt, _uv in layers),
            )
            groups.setdefault(key, []).append(index)

        order = np.fromiter((i for idxs in groups.values() for i in idxs), dtype=np.int64, count=len(triangles))
        ordered = [triangles[i] for i in order.tolist()]
        vertices = np.zeros((len(ordered), 3, _FLOATS_PER_VERTEX), dtype=np.float32)
        self._fill_geometry(vertices, ordered)
        vertices[:, :, 6:9] = np.array([t.color for t in ordered], dtype=np.float32)[:, None, :]
        vertices[:, :, 9] = np.array([t.alpha for t in ordered], dtype=np.float32)[:, None]
        vertices[:, :, 18] = np.array([CULL_CODES.get(getattr(t, "cull", "back"), 0.0) for t in ordered],
                                      dtype=np.float32)[:, None]
        for slot in range(MAX_LAYERS):
            uvs = [layers_by_tri[i][slot][6] if slot < len(layers_by_tri[i]) else ((0, 0), (0, 0), (0, 0)) for i in order.tolist()]
            vertices[:, :, 10 + slot * 2 : 12 + slot * 2] = np.array(uvs, dtype=np.float32)

        self._vertices = vertices
        self._order = order
        self._vertex_buffer = self._device.create_buffer_with_data(
            data=vertices, usage=wgpu.BufferUsage.VERTEX | wgpu.BufferUsage.COPY_DST
        )

        first = 0
        for (additive, _signature), idxs in groups.items():
            layers = layers_by_tri[idxs[0]]
            self._batches.append(_Batch(first * 3, len(idxs) * 3, additive, self._batch_group(layers)))
            first += len(idxs)

    @staticmethod
    def _fill_geometry(vertices: np.ndarray, ordered: list) -> None:
        vertices[:, 0, 0:3] = np.array([t.a for t in ordered], dtype=np.float32)
        vertices[:, 1, 0:3] = np.array([t.b for t in ordered], dtype=np.float32)
        vertices[:, 2, 0:3] = np.array([t.c for t in ordered], dtype=np.float32)
        vertices[:, :, 3:6] = np.array([t.normal for t in ordered], dtype=np.float32)[:, None, :]

    def update_positions(self, triangles: list) -> bool:
        """Rewrite positions/normals for a posed copy of the current model
        (same triangles, same order - see ``model_viewer._skin_triangles()``).
        Returns False when ``triangles`` doesn't match the uploaded model."""
        if self._vertices is None or self._order is None or len(triangles) != len(self._order):
            return False
        ordered = [triangles[i] for i in self._order.tolist()]
        self._fill_geometry(self._vertices, ordered)
        self._device.queue.write_buffer(self._vertex_buffer, 0, self._vertices)
        return True

    def update_arrays(self, positions: np.ndarray, normals: np.ndarray | None = None,
                      changed: np.ndarray | None = None, alphas: np.ndarray | None = None) -> bool:
        """``update_positions()`` from arrays: ``positions`` (n, 3, 3) and
        ``normals`` (n, 3) in the uploaded triangles' order, and optionally
        each triangle's alpha (n,) (animated effect materials). ``changed`` (a
        boolean mask in that order) limits the upload to those triangles:
        they are written in the few contiguous runs they occupy."""
        if self._vertices is None or self._order is None or len(positions) != len(self._order):
            return False
        if changed is None:
            self._vertices[:, :, 0:3] = positions[self._order]
            if normals is not None:
                self._vertices[:, :, 3:6] = normals[self._order][:, None, :]
            if alphas is not None:
                self._vertices[:, :, 9] = alphas[self._order][:, None]
            self._device.queue.write_buffer(self._vertex_buffer, 0, self._vertices)
            return True
        runs = self._runs(changed)
        stride = self._vertices[0].nbytes  # bytes per triangle
        for start, end in runs:
            source = self._order[start:end]
            self._vertices[start:end, :, 0:3] = positions[source]
            if normals is not None:
                self._vertices[start:end, :, 3:6] = normals[source][:, None, :]
            if alphas is not None:
                self._vertices[start:end, :, 9] = alphas[source][:, None]
            self._device.queue.write_buffer(self._vertex_buffer, start * stride,
                                            np.ascontiguousarray(self._vertices[start:end]))
        return True

    def _runs(self, changed: np.ndarray) -> list[tuple[int, int]]:
        """Contiguous ``[start, end)`` runs of the ordered buffer holding ``changed`` triangles."""
        key = (id(changed), id(self._order))
        cached = getattr(self, "_runs_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        flags = np.asarray(changed, dtype=bool)[self._order].astype(np.int8)
        edges = np.diff(np.concatenate(([0], flags, [0])))
        runs = list(zip(np.nonzero(edges == 1)[0].tolist(), np.nonzero(edges == -1)[0].tolist()))
        self._runs_cache = (key, runs, changed)  # keep the mask alive so its id stays its own
        return runs

    def _texture_view(self, array: np.ndarray):
        key = id(array)
        if key not in self._textures:
            data = np.asarray(array, dtype=np.uint8)
            if data.ndim == 2:
                data = np.repeat(data[..., None], 3, axis=2)
            if data.shape[2] == 3:
                data = np.concatenate((data, np.full(data.shape[:2] + (1,), 255, np.uint8)), axis=2)
            data = np.ascontiguousarray(data[..., :4])
            height, width = data.shape[:2]
            texture = self._device.create_texture(
                size=(width, height, 1),
                format=wgpu.TextureFormat.rgba8unorm,
                usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
            )
            self._device.queue.write_texture(
                {"texture": texture}, data, {"bytes_per_row": width * 4, "rows_per_image": height}, (width, height, 1)
            )
            # keep the source array alive so its id can't be reused while cached
            self._textures[key] = (array, texture.create_view())
        return self._textures[key][1]

    def _batch_group(self, layers: list):
        info = np.zeros(4, dtype=np.uint32)
        roles = np.zeros(4, dtype=np.uint32)
        flips = np.zeros(4, dtype=np.uint32)
        scales = np.ones((4, 4), dtype=np.float32)
        info[0] = len(layers)
        views = []
        samplers = []
        for i in range(MAX_LAYERS):
            if i < len(layers):
                texture, role, flip, scale, wrap_s, wrap_t, _uv = layers[i]
                roles[i] = _ROLE_CODES.get(role, 0)
                flips[i] = 1 if flip else 0
                scales[i, :3] = scale
                views.append(self._texture_view(texture))
                samplers.append(self._shared.sampler(wrap_s, wrap_t))
            else:
                views.append(self._shared.dummy_view)
                samplers.append(self._shared.sampler(1, 1))
        uniform = info.tobytes() + roles.tobytes() + flips.tobytes() + scales.tobytes()
        buffer = self._device.create_buffer_with_data(data=uniform, usage=wgpu.BufferUsage.UNIFORM)
        entries = [{"binding": 0, "resource": {"buffer": buffer}}]
        entries += [{"binding": 1 + i, "resource": views[i]} for i in range(MAX_LAYERS)]
        entries += [{"binding": 1 + MAX_LAYERS + i, "resource": samplers[i]} for i in range(MAX_LAYERS)]
        return self._device.create_bind_group(layout=self._shared.batch_layout, entries=entries)

    # -- frame --------------------------------------------------------------
    def _ensure_targets(self, width: int, height: int) -> None:
        if self._size == (width, height):
            return
        device = self._device
        color = device.create_texture(
            size=(width, height, 1),
            format=wgpu.TextureFormat.rgba8unorm,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
            sample_count=MSAA_SAMPLES,
        )
        resolve = device.create_texture(
            size=(width, height, 1),
            format=wgpu.TextureFormat.rgba8unorm,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
        )
        depth = device.create_texture(
            size=(width, height, 1),
            format=wgpu.TextureFormat.depth32float,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
            sample_count=MSAA_SAMPLES,
        )
        stride = (width * 4 + 255) // 256 * 256
        readback = device.create_buffer(
            size=stride * height, usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ
        )
        self._targets = (color.create_view(), resolve, resolve.create_view(), depth.create_view(), readback, stride)
        self._size = (width, height)

    def render(self, *args, **kwargs) -> np.ndarray:
        """``render_image()`` as an (height, width, 3) uint8 array, the
        shape ``_ModelCanvas._rasterize()`` returns."""
        return np.asarray(self.render_image(*args, **kwargs))

    def render_image(
        self,
        width: int,
        height: int,
        rotation: np.ndarray,
        center: tuple[float, float, float],
        scale: float,
        extent: float,
        screen_x_sign: float,
        screen_y_sign: float,
        perspective: float = 0.0,
    ) -> Image.Image:
        """Draw the model and return the RGB frame - the same camera as
        ``_ModelCanvas._rasterize()``'s ``to_screen()``."""
        width, height = max(int(width), 1), max(int(height), 1)
        self._ensure_targets(width, height)
        color_view, resolve, resolve_view, depth_view, readback, stride = self._targets

        camera = np.zeros((5, 4), dtype=np.float32)
        camera[0:3, 0:3] = rotation
        camera[3, 0:3] = center
        # to_screen(): sx = w/2 + rx*scale*xsign, sy = h/2 - ry*scale*ysign;
        # NDC y points up, so the canvas's downward y flips back.
        camera[4, 0] = scale * screen_x_sign / (width / 2.0)
        camera[4, 1] = scale * screen_y_sign / (height / 2.0)
        # rotated z stays within ~0.87 * extent of the center; leave room for poses
        camera[4, 2] = 0.25 / max(extent, 1e-6)
        camera[4, 3] = perspective
        self._device.queue.write_buffer(self._camera_buffer, 0, camera)

        encoder = self._device.create_command_encoder()
        bg = tuple(c / 255.0 for c in BACKGROUND) + (1.0,)
        render_pass = encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": color_view,
                    "resolve_target": resolve_view,
                    "clear_value": bg,
                    "load_op": wgpu.LoadOp.clear,
                    "store_op": wgpu.StoreOp.discard,
                }
            ],
            depth_stencil_attachment={
                "view": depth_view,
                "depth_clear_value": 1.0,
                "depth_load_op": wgpu.LoadOp.clear,
                "depth_store_op": wgpu.StoreOp.discard,
            },
        )
        if self._batches:
            render_pass.set_bind_group(0, self._camera_group)
            render_pass.set_vertex_buffer(0, self._vertex_buffer)
            for pipeline, additive in (
                (self._shared.opaque, False),
                (self._shared.translucent, False),
                (self._shared.additive, True),
            ):
                render_pass.set_pipeline(pipeline)
                for batch in self._batches:
                    if batch.additive == additive:
                        render_pass.set_bind_group(1, batch.bind_group)
                        render_pass.draw(batch.vertex_count, 1, batch.first_vertex, 0)
        render_pass.end()
        encoder.copy_texture_to_buffer(
            {"texture": resolve},
            {"buffer": readback, "offset": 0, "bytes_per_row": stride, "rows_per_image": height},
            (width, height, 1),
        )
        self._device.queue.submit([encoder.finish()])

        readback.map_sync(wgpu.MapMode.READ)
        try:
            # PIL's native RGBX unpack (also drops the row padding) is several
            # times faster than slicing the channels off with numpy
            image = Image.frombytes("RGB", (width, height), readback.read_mapped(copy=False), "raw", "RGBX", stride, 1)
        finally:
            readback.unmap()
        return image
