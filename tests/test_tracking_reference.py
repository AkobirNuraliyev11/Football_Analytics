import unittest
import importlib.util
AVAILABLE = all(importlib.util.find_spec(name) for name in ('numpy','scipy'))
if AVAILABLE:
    from football_intelligence.benchmarks.tracking_reference import score_tracking


def record(index, ids):
    return dict(frame_index=index,timestamp_s=index*.1,detections=[dict(
        kind='person',track_id=identity,bbox=dict(x_min=x-5,x_max=x+5,y_min=0,y_max=20),
        confirmed=True,continuity_safe=True,continuity_segment=0) for x,identity in ids])


@unittest.skipUnless(AVAILABLE, 'Requires detection extras')
class TrackingReferenceTests(unittest.TestCase):
    def test_id_swap_is_scored_and_missing_stays_in_denominator(self):
        refs={i:{'a':[20,10],'b':[100,10]} for i in range(3)}
        result=score_tracking([record(0,[(20,1),(100,2)]),record(1,[(20,2),(100,1)]),record(2,[])],refs)
        self.assertEqual(result['reference_observations'],6)
        self.assertEqual(result['matched_observations'],4)
        self.assertEqual(result['reference_adjacent_links'],4)
        self.assertEqual(result['adjacent_id_changes'],2)
        self.assertEqual(result['eligible_same_id_links'],0)
        self.assertEqual(result['tracks_associated_with_multiple_references'],2)

    def test_no_link_across_time_gap_or_unsafe_segment(self):
        refs={i:{'a':[20,10]} for i in [0,1,4]}
        a,b,c=[record(i,[(20,1)]) for i in [0,1,4]]
        b['detections'][0]['continuity_segment']=1
        result=score_tracking([a,b,c],refs)
        self.assertEqual(result['reference_adjacent_links'],1)
        self.assertEqual(result['same_id_adjacent_links'],1)
        self.assertEqual(result['eligible_same_id_links'],0)

    def test_ambiguous_and_duplicate_ids(self):
        refs={0:{'a':[20,10],'b':[30,10]}}
        self.assertEqual(score_tracking([record(0,[(25,1)])],refs)['matched_observations'],0)
        with self.assertRaises(ValueError):
            score_tracking([record(0,[(20,1),(100,1)])],refs)

    def test_sustained_continuity_requires_all_intermediate_links(self):
        refs={i:{'a':[20,10]} for i in range(22)}
        rows=[record(i,[(20,1)]) for i in range(22)]
        result=score_tracking(rows,refs)
        self.assertAlmostEqual(result['longest_eligible_continuity_s'],2.1)
        self.assertEqual(result['reference_players_with_two_second_continuity'],1)
        rows[11]['detections']=[]
        result=score_tracking(rows,refs)
        self.assertEqual(result['reference_players_with_two_second_continuity'],0)
        self.assertLessEqual(result['longest_eligible_continuity_s'],1.)
