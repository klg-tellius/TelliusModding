import unittest

import numpy as np

from fe_modding.gui import gpu_renderer, model_viewer

RENDERER = gpu_renderer.create_renderer()


def _canvas(yaw=0.6, pitch=-0.4, zoom=1.0):
    canvas = object.__new__(model_viewer._ModelCanvas)
    canvas._yaw, canvas._pitch, canvas._zoom = yaw, pitch, zoom
    canvas._screen_x_sign = 1.0
    canvas._screen_y_sign = 1.0
    canvas._center = (0.0, 0.0, 0.0)
    canvas._extent = 2.0
    return canvas


def _quad(z, texture=None, color=(200, 50, 50), alpha=1.0, blend_mode="normal", layers=(), size=1.0, uv_scale=1.0):
    """Two triangles facing the default camera (+Z normal points away from it)."""
    a, b, c, d = (-size, -size, z), (size, -size, z), (size, size, z), (-size, size, z)
    s = uv_scale
    uv1 = ((0.0, s), (s, s), (s, 0.0))
    uv2 = ((0.0, s), (s, 0.0), (0.0, 0.0))
    normal = (0.0, 0.0, -1.0)
    tris = []
    for (p0, p1, p2), uv in (((a, b, c), uv1), ((a, c, d), uv2)):
        tri_layers = tuple(
            model_viewer._TextureLayer(uv, layer.texture, layer.role, layer.flip_v, layer.color_scale, layer.wrap_s, layer.wrap_t)
            for layer in layers
        )
        tris.append(
            model_viewer._Triangle(
                p0, p1, p2, normal, color,
                uv=uv if texture is not None else None,
                texture=texture,
                texture_layers=tri_layers,
                alpha=alpha,
                blend_mode=blend_mode,
            )
        )
    return tris


def _checker(n=8):
    tex = np.zeros((n, n, 4), dtype=np.uint8)
    tex[..., 3] = 255
    yy, xx = np.mgrid[0:n, 0:n]
    on = (xx + yy) % 2 == 0
    tex[on, :3] = (240, 220, 30)
    tex[~on, :3] = (20, 60, 200)
    return tex


@unittest.skipIf(RENDERER is None, "no wgpu adapter")
class GpuRendererMatchesCpuTest(unittest.TestCase):
    W, H = 160, 120

    def _compare(self, triangles, canvas=None, tolerance=0.02):
        canvas = canvas or _canvas(yaw=0.0, pitch=0.0)
        cpu = canvas._rasterize(triangles, self.W, self.H).astype(np.int16)
        RENDERER.set_triangles(triangles)
        scale = (min(self.W, self.H) * model_viewer.FIT_FRACTION / canvas._extent) * canvas._zoom
        gpu = RENDERER.render(
            self.W, self.H, canvas._rotation_matrix(), canvas._center, scale, canvas._extent,
            canvas._screen_x_sign, canvas._screen_y_sign, canvas._perspective,
        ).astype(np.int16)
        self.assertEqual(gpu.shape, cpu.shape)
        diff = np.abs(gpu - cpu).max(axis=2) > 12
        # edges differ (MSAA, pixel-centre rounding); the bulk must agree
        self.assertLess(diff.mean(), tolerance, f"{diff.mean():.3f} of pixels differ")

    def test_flat_color(self):
        self._compare(_quad(0.0))

    def test_textured_wrap_modes(self):
        tex = _checker()
        for wrap in (0, 1, 2):
            layer = model_viewer._TextureLayer(((0, 0),) * 3, tex, "diffuse", wrap_s=wrap, wrap_t=wrap)
            with self.subTest(wrap=wrap):
                self._compare(_quad(0.0, layers=(layer,), uv_scale=2.0), tolerance=0.08)

    def test_single_texture_path(self):
        self._compare(_quad(0.0, texture=_checker()), tolerance=0.08)

    def test_depth_translucent_and_additive(self):
        tris = _quad(0.5, color=(30, 200, 30))
        tris += _quad(0.0, color=(200, 30, 30), alpha=0.5, size=0.7)
        tris += _quad(-0.2, color=(40, 40, 200), alpha=0.8, blend_mode="additive", size=0.4)
        self._compare(tris)

    def test_backfaces_are_culled(self):
        tris = _quad(0.0)
        for tri in tris:
            tri.normal = (0.0, 0.0, 1.0)
        self._compare(tris)

    def test_rotated_camera(self):
        self._compare(_quad(0.0, texture=_checker()), canvas=_canvas(), tolerance=0.08)

    def test_perspective(self):
        canvas = _canvas(yaw=0.3, pitch=-0.2)
        canvas._perspective = 0.25
        tris = _quad(1.0, color=(30, 200, 30), size=0.8) + _quad(-1.0, color=(200, 30, 30), size=0.3)
        self._compare(tris, canvas=canvas)

    def test_perspective_cuts_triangles_at_the_near_plane(self):
        # one vertex behind the eye (r.z < -1 / perspective): the GPU keeps the
        # part in front of the near plane, the same as that part drawn on its own
        canvas = _canvas(yaw=0.0, pitch=0.0)
        canvas._perspective = 0.25
        normal, color = (0.0, 0.0, -1.0), (30, 200, 30)
        points = [np.array(p) for p in ((0.3, -0.8, 0.0), (1.2, -0.8, 0.0), (0.8, 0.6, -8.0))]
        w = lambda p: 1.0 + p[2] * canvas._perspective
        near = model_viewer.PERSPECTIVE_NEAR
        kept = []
        for a, b in zip(points, points[1:] + points[:1]):
            if w(a) > near:
                kept.append(a)
            if (w(a) > near) != (w(b) > near):
                kept.append(a + (near - w(a)) / (w(b) - w(a)) * (b - a))
        clipped = [model_viewer._Triangle(tuple(kept[0]), tuple(kept[i]), tuple(kept[i + 1]), normal, color)
                   for i in range(1, len(kept) - 1)]
        cpu = canvas._rasterize(clipped, self.W, self.H).astype(np.int16)
        RENDERER.set_triangles([model_viewer._Triangle(*map(tuple, points), normal, color)])
        scale = (min(self.W, self.H) * model_viewer.FIT_FRACTION / canvas._extent) * canvas._zoom
        gpu = RENDERER.render(
            self.W, self.H, canvas._rotation_matrix(), canvas._center, scale, canvas._extent,
            canvas._screen_x_sign, canvas._screen_y_sign, canvas._perspective,
        ).astype(np.int16)
        self.assertGreater((np.abs(cpu - cpu[0, 0]).max(axis=2) > 12).sum(), 200)
        self.assertLess((np.abs(gpu - cpu).max(axis=2) > 12).mean(), 0.02)

    def test_update_positions(self):
        tris = _quad(0.0)
        RENDERER.set_triangles(tris)
        moved = [model_viewer._Triangle(*(tuple(v + 0.3 for v in p) for p in (t.a, t.b, t.c)), t.normal, t.color) for t in tris]
        self.assertTrue(RENDERER.update_positions(moved))
        self.assertFalse(RENDERER.update_positions(moved[:1]))


if __name__ == "__main__":
    unittest.main()
