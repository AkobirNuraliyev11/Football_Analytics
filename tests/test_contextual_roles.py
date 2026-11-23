import unittest
import numpy as np
from football_intelligence.contextual_roles import ContextualRoles,kit_features


class ContextualRolesTests(unittest.TestCase):
    def records(self):
        records=[];features={}
        for i in range(8):
            role='official' if i==6 else 'outfield'
            team='A' if i<3 else 'B' if i!=6 else 'unknown'
            records.append(dict(track_id=i,kind='person',role=role,role_candidate=role,team=team,
                                continuity_segment=0,confirmed=True,continuity_safe=True,confidence=.95))
            features[i]=np.array([1.3,.5,.5] if i<3 else [.5,.6,.8] if i<6 else [.7,1.3,1.5])
        return records,features

    def test_supported_official_kit_corrects_role_without_self_training(self):
        engine=ContextualRoles();records,features=self.records()
        for i in range(12):out=engine.update(records,features,timestamp_s=i*.04,shot_id=0)
        self.assertEqual(out[7]['role'],'official');self.assertEqual(out[7]['team'],'unknown')
        self.assertEqual(out[7]['role_evidence'],'experimental_contextual_kit')
        self.assertTrue(all(x['role']=='outfield' for x in out[:6]))
        self.assertEqual(engine.histories[(7,0)]['group'],'B')
        self.assertEqual(records[7]['role'],'outfield')

    def test_missing_anchor_or_second_team_cannot_infer_roles(self):
        for excluded in ({6},{3,4,5}):
            engine=ContextualRoles();records,features=self.records()
            records=[r for r in records if r['track_id'] not in excluded]
            for i in range(15):out=engine.update(records,features,timestamp_s=i*.04,shot_id=0)
            self.assertFalse(any(r.get('role_evidence') for r in out))

    def test_identity_cut_gap_and_missing_features_reset_consensus(self):
        for case in ('identity','shot','gap','missing','unsafe'):
            engine=ContextualRoles();records,features=self.records()
            for i in range(12):out=engine.update(records,features,timestamp_s=i*.04,shot_id=0)
            self.assertEqual(out[7]['role'],'official')
            if case=='identity':records[7]['continuity_segment']=1
            if case=='missing':features.pop(7)
            if case=='unsafe':records[7]['continuity_safe']=False
            out=engine.update(records,features,timestamp_s=1 if case=='gap' else .48,shot_id=int(case=='shot'))
            self.assertNotIn('role_evidence',out[7])

    def test_anchor_identity_break_removes_old_official_prototype(self):
        engine=ContextualRoles();records,features=self.records()
        for i in range(12):engine.update(records,features,timestamp_s=i*.04,shot_id=0)
        records[6]['continuity_segment']=1
        out=engine.update(records,features,timestamp_s=.48,shot_id=0)
        self.assertNotIn((6,0),engine.histories)
        self.assertNotIn('role_evidence',out[7])

    def test_overlapping_kit_colors_and_goalkeepers_do_not_get_override(self):
        for case in ('same_kit','goalkeeper'):
            engine=ContextualRoles();records,features=self.records()
            if case=='same_kit':features[6]=features[7]=features[3].copy()
            else:records[7].update(role='goalkeeper',role_candidate='goalkeeper')
            for i in range(15):out=engine.update(records,features,timestamp_s=i*.04,shot_id=0)
            self.assertNotIn('role_evidence',out[7])

    def test_small_clipped_overlapped_and_no_grass_crops_have_no_feature(self):
        rgb=np.full((360,640,3),(40,100,40),dtype=np.uint8)
        box=dict(x_min=100,y_min=100,x_max=130,y_max=160)
        r=dict(track_id=1,kind='person',bbox=box)
        rgb[100:160,100:130]=(60,140,160)
        self.assertIn(1,kit_features(rgb,[r]))
        r2=dict(track_id=2,kind='person',bbox=box)
        self.assertEqual(kit_features(rgb,[r,r2]),{})
        r['bbox']=dict(x_min=100,y_min=100,x_max=130,y_max=120)
        self.assertEqual(kit_features(rgb,[r]),{})
        self.assertEqual(kit_features(np.zeros_like(rgb),[r]),{})
