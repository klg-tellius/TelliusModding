import os
import unittest
from pathlib import Path

import numpy as np

from fe_modding.formats import animation, effects, particle_preview
from fe_modding.gui.model_viewer import _load_model_set, _particle_triangles


class ParticleSamplingTest(unittest.TestCase):
    def test_window_and_global_translation_curve(self):
        emitter = animation.ParticleEmitterLayout(
            0, "|root|", 0, 0, 1, 4, 0, (1.0, 1.0), 0.0, 1, 0, 0, 0, 0, 1)
        stage = animation.ParticleStageLayout(0, 0, 5, 15, (2.0, 3.0, 4.0), 0, 1)
        prepared = (particle_preview.Stage(emitter, stage, ((0, ((0, 1.0), (10, 3.0))),)),)
        self.assertEqual(particle_preview.sample(prepared, 4), ())
        at_ten = particle_preview.sample(prepared, 10)
        self.assertEqual(len(at_ten), 1)
        self.assertAlmostEqual(at_ten[0].position[0], 5.0)  # initial 2 + frame-10 offset 3
        self.assertEqual(particle_preview.sample(prepared, 16), ())

    def test_later_stage_does_not_restart_its_curves(self):
        emitter = animation.ParticleEmitterLayout(
            0, "|root|", 0, 0, 1, 4, 0, (1.0, 1.0), 0.0, 1, 0, 0, 0, 0, 1)
        stage = animation.ParticleStageLayout(0, 0, 12, 27, (0.0, 0.0, 0.0), 0, 1)
        prepared = (particle_preview.Stage(
            emitter, stage, ((4, ((13, 0.0), (14, 0.25), (16, 1.0), (27, 0.0))),)),)
        # EID_K_ATTACK has this exact shape: restarting the curve at local frame zero kept the
        # particle invisible until frame 26 and made a false second burst after the hit.
        self.assertEqual(particle_preview.sample(prepared, 12)[0].alpha, 0.0)
        self.assertEqual(particle_preview.sample(prepared, 16)[0].alpha, 1.0)


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "FE9_EXTRACTED_FILES not set")
class ParticleCorpusTest(unittest.TestCase):
    def test_meshless_effect_has_textured_visible_stage(self):
        path = Path(os.environ["FE9_EXTRACTED_FILES"]) / "yme" / "EID_BADSTATUS1.cmp"
        parts = effects.read_effect_pack(path.read_bytes())
        ga = next(blob for name, blob in parts.items() if name.endswith(".ga"))
        loaded = _load_model_set(path.stem, path)
        self.assertFalse(loaded.triangles)
        samples = particle_preview.sample(particle_preview.read_stages(ga), 30)
        faces = _particle_triangles(samples, loaded.particle_materials, np.eye(3))
        self.assertGreater(len(faces), 0)
        self.assertTrue(any(face.texture is not None and face.alpha > 0 for face in faces))


if __name__ == "__main__":
    unittest.main()
