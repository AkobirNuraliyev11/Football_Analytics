import unittest
from football_intelligence.benchmarks.sensor_reference import SensorSeries


class SensorReferenceTests(unittest.TestCase):
    def test_identical_duplicates_collapse_but_conflicts_stay_unavailable(self):
        series=SensorSeries([(0,(0,0)),(.1,(1,1)),(.1,(1,1)),(.2,(2,2)),(.2,(3,3)),(.3,(4,4))])
        self.assertEqual(series.sample(.1),(1,1))
        self.assertEqual(series.identical_duplicates,1)
        self.assertEqual(series.duplicate_rows,2)
        self.assertIsNone(series.sample(.2))
        self.assertIsNone(series.sample(.15))
        self.assertIsNone(series.interval(.1,.3))

    def test_time_interpolation_and_no_extrapolation(self):
        series=SensorSeries([(0,(0,2)),(.1,(2,4)),(.2,(4,6))])
        self.assertEqual(series.sample(.05),(1,3))
        self.assertEqual(series.interval(.05,.15),((1,3),(3,5)))
        self.assertIsNone(series.sample(-.01))
        self.assertIsNone(series.sample(.21))

    def test_missing_sample_invalidates_entire_interval(self):
        series=SensorSeries([(0,(0,0)),(.1,(1,0)),(.3,(3,0)),(.4,(4,0))])
        self.assertIsNone(series.sample(.2))
        self.assertIsNone(series.interval(0,.4))
        self.assertEqual(series.interval(.3,.4),((3,0),(4,0)))

    def test_nonfinite_and_reversed_intervals_rejected(self):
        with self.assertRaises(ValueError):SensorSeries([(0,(float('nan'),0))])
        series=SensorSeries([(0,(0,0))])
        for start,end in [(1,0),(0,0),(0,float('inf'))]:
            with self.assertRaises(ValueError):series.interval(start,end)
