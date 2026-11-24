import unittest
from football_intelligence.telemetry import TelemetryEngine
from test_telemetry import frame


def observed(t,x,radius=.3):
    evidence={'status':'line_checked_estimate','ground_evidence':'visible_feet_candidate','camera_stable':True}
    if radius is not None:evidence['pixel_localization_radius_m']=radius
    return frame(t,x=x,measurement_evidence=evidence)

class UncertainMotionTests(unittest.TestCase):
    def test_opt_in_requires_experimental_mode(self):
        with self.assertRaises(ValueError):TelemetryEngine(uncertainty_aware_displacement=True)

    def test_compatible_jitter_retained_only_with_known_bounds(self):
        for enabled,radius,expected in [(False,.3,'withheld'),(True,None,'withheld'),(True,.3,'warming_up')]:
            engine=TelemetryEngine(experimental=True,uncertainty_aware_displacement=enabled)
            engine.update(observed(0,0,radius))
            out=engine.update(observed(.04,.6,radius))['observations'][0]
            self.assertEqual(out['status'],expected)
            self.assertIsNone(out['speed_kmh'])

    def test_impossible_jump_and_missing_position_still_split(self):
        engine=TelemetryEngine(experimental=True,uncertainty_aware_displacement=True)
        first=engine.update(observed(0,0))['observations'][0]['fragment_id']
        row=engine.update(observed(.04,3))['observations'][0]
        self.assertEqual(row['reasons'],['implausible_displacement'])
        second=engine.update(observed(.08,3))['observations'][0]['fragment_id']
        self.assertNotEqual(first,second)
        missing=observed(.12,3);missing['detections'][0]['pitch_position_candidate']=None
        engine.update(missing)
        third=engine.update(observed(.16,3))['observations'][0]['fragment_id']
        self.assertNotEqual(second,third)
        self.assertEqual(engine.finish()['measured_observations'],0)
