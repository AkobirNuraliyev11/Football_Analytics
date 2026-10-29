import importlib.util
import unittest

from football_intelligence.classification import TeamRoleClassifier, ClassificationConfig, torso_feature


@unittest.skipUnless(importlib.util.find_spec("numpy"),"Install NumPy")
class ClassificationTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np=np
        self.classifier=TeamRoleClassifier()
        self.time=-.04
        self.colors=[(210,30,30)]*4+[(210,210,210)]*4

    def frame(self,colors=None,roles=None,shot=0,step=.04,points=None):
        colors=colors or self.colors
        rgb=self.np.zeros((100,40*len(colors),3),dtype=self.np.uint8)
        records=[]
        for i,color in enumerate(colors):
            rgb[:,i*40:(i+1)*40]=color
            records.append({"track_id":i+1,"kind":"person","confirmed":True,"confidence":.95,
                "bbox":{"x_min":i*40,"y_min":0,"x_max":(i+1)*40,"y_max":100},
                "role_candidate":roles[i] if roles else "outfield",
                "pitch_position_candidate":points[i] if points else None})
        self.time+=step
        return self.classifier.update(rgb,records,timestamp_s=self.time,shot_id=shot)

    def warmup(self):
        for _ in range(10): result=self.frame()
        return result

    def test_two_teams_learned_without_manual_labels(self):
        result=self.warmup()
        self.assertEqual(len({x["team"] for x in result}),2)
        self.assertNotEqual(result[0]["team"],result[4]["team"])
        self.assertNotIn("unknown",{x["team"] for x in result})
        self.assertEqual(self.classifier.summary()["bootstrap_track_support"],[4,4])

    def test_uniform_shadow_preserves_assignment(self):
        original=self.warmup()
        darker=[tuple(int(v*.35) for v in color) for color in self.colors]
        for _ in range(20): result=self.frame(darker)
        self.assertEqual([x["team"] for x in original],[x["team"] for x in result])

    def test_single_wrong_color_does_not_switch_team(self):
        original=self.warmup()
        changed=self.colors.copy();changed[0]=self.colors[4]
        result=self.frame(changed)
        self.assertEqual(result[0]["team"],original[0]["team"])
        self.assertFalse(result[0]["team_changed"])

    def test_sustained_new_color_corrects_identity_with_flag(self):
        original=self.warmup()
        changed=self.colors.copy();changed[0]=self.colors[4]
        flags=[]
        for _ in range(25):
            result=self.frame(changed)
            flags.append(result[0]["team_changed"])
        self.assertEqual(result[0]["team"],original[4]["team"])
        self.assertEqual(sum(flags),1)

    def test_single_color_does_not_force_two_teams(self):
        for _ in range(15): result=self.frame([(210,30,30)]*8)
        self.assertEqual(self.classifier.summary()["status"],"insufficient_kit_evidence")
        self.assertTrue(all(x["team"]=="unknown" for x in result))

    def test_shot_reset_retains_prototypes_but_not_track_votes(self):
        original=self.warmup()
        centers=self.classifier.summary()["team_centers"]
        result=self.frame(shot=1)
        self.assertTrue(all(x["team"]=="unknown" for x in result))
        for _ in range(6): result=self.frame(shot=1)
        self.assertEqual([x["team"] for x in original],[x["team"] for x in result])
        self.assertEqual(self.classifier.summary()["team_centers"],centers)

    def test_official_never_receives_team_and_not_in_bootstrap(self):
        roles=["outfield"]*8+["official"]
        colors=self.colors+[(220,220,30)]
        for _ in range(12): result=self.frame(colors,roles)
        self.assertEqual(result[-1]["role"],"official")
        self.assertEqual(result[-1]["team"],"unknown")
        self.assertEqual(sum(self.classifier.summary()["bootstrap_track_support"]),8)

    def test_goalkeeper_needs_distinct_kit_and_penalty_geometry(self):
        self.warmup()
        colors=self.colors+[(30,80,220)]
        roles=["outfield"]*8+["goalkeeper"]
        for _ in range(4): result=self.frame(colors,roles)
        self.assertEqual(result[-1]["role"],"unknown")
        points=[None]*8+[{"x_m":5,"y_m":34}]
        result=self.frame(colors,roles,points=points)
        self.assertEqual(result[-1]["role"],"goalkeeper")
        self.assertEqual(result[-1]["team"],"unknown")
        points[-1]={"x_m":52.5,"y_m":34}
        self.assertEqual(self.frame(colors,roles,points=points)[-1]["role"],"unknown")

    def test_dark_crop_stales_to_unknown(self):
        self.warmup()
        for _ in range(52): result=self.frame([(0,0,0)]*8)
        self.assertTrue(all(x["team"]=="unknown" for x in result))

    def test_clipped_and_tiny_crops_are_rejected(self):
        rgb=self.np.zeros((20,20,3),dtype=self.np.uint8)
        box={"x_min":0,"y_min":0,"x_max":2,"y_max":3}
        self.assertIsNone(torso_feature(rgb,box))

    def test_unknown_role_evidence_does_not_stay_confirmed_forever(self):
        self.warmup()
        for _ in range(52): result=self.frame(roles=["unknown"]*8)
        self.assertTrue(all(x["role"]=="unknown" and x["team"]=="unknown" for x in result))

    def test_invalid_configuration_and_time(self):
        with self.assertRaises(ValueError): ClassificationConfig(min_samples=0)
        with self.assertRaises(ValueError): ClassificationConfig(min_bootstrap_tracks=2)
        self.frame()
        with self.assertRaises(ValueError): self.frame(step=0)


if __name__=="__main__": unittest.main()
