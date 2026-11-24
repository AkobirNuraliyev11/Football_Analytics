import unittest
import numpy as np
from scripts.audit_displacements import decompose


class DisplacementAuditTests(unittest.TestCase):
    def test_camera_translation_cancels_image_translation(self):
        old=np.eye(3);new=np.array([[1,0,-5],[0,1,2],[0,0,1]])
        result=decompose(old,new,[10,20],[15,18],.04)
        np.testing.assert_allclose(result['total_displacement_m'],[0,0])
        np.testing.assert_allclose(result['anchor_component_m'],[5,-2])
        np.testing.assert_allclose(result['mapping_component_m'],[-5,2])
        self.assertEqual(result['apparent_speed_kmh'],0)

    def test_projective_components_reconstruct_total(self):
        old=np.eye(3);new=np.array([[.2,0,2],[0,.3,1],[.001,.002,1]])
        result=decompose(old,new,[10,20],[11,23],.08)
        np.testing.assert_allclose(np.array(result['anchor_component_m'])+result['mapping_component_m'],
                                   result['total_displacement_m'])
        for dt in (0,-1,float('nan')):
            with self.assertRaises(ValueError):decompose(old,new,[10,20],[11,23],dt)
