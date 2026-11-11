import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from football_intelligence.highlight_viewer import active_events, overlay_candidate, write_viewer


def candidate():
    return dict(event_id=1,kind='duel_candidate',shot_id=0,start_s=1.,end_s=2.,
                track_ids=[1,2],truncated=True)


def window():
    return dict(clip_id=1,file='clip-0001.mp4',sha256='test',shot_id=0,start_s=.5,end_s=2.5,
                event_ids=[1],frame_count=21)


def result():
    return dict(status='available',match_id='<script>alert("x")</script>',source_sha256='source',
                overlays_included=True,events=[candidate()],windows=[window()])


class ViewerTests(unittest.TestCase):
    def test_padding_and_shot_change_never_activate_candidate(self):
        self.assertEqual(active_events([candidate()],window(),.5),[])
        self.assertEqual(len(active_events([candidate()],window(),1.)),1)
        self.assertEqual(len(active_events([candidate()],window(),2.)),1)
        self.assertEqual(active_events([candidate()],window(),2.1),[])
        self.assertEqual(active_events([candidate()|dict(shot_id=1)],window(),1.5),[])

    def test_relative_cues_safe_html_and_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);playlist=write_viewer(root,result())
            event=playlist['clips'][0]['events'][0]
            self.assertEqual((event['clip_start_s'],event['clip_end_s']),(.5,1.5))
            self.assertTrue(event['truncated'])
            html=(root/'index.html').read_text()
            self.assertNotIn('<script>',html)
            self.assertIn('&lt;script&gt;',html)
            self.assertIn('src="clip-0001.mp4"',html)
            self.assertIn('cut short at a recording or measurement boundary',html)
            self.assertNotIn('https://',html)
            self.assertEqual(json.loads((root/'playlist.json').read_text()),playlist)

    def test_empty_states_and_external_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for status,phrase in [('unavailable','Measurements unavailable'),('available','No qualifying candidates')]:
                write_viewer(root,result()|dict(status=status,events=[],windows=[]))
                self.assertIn(phrase,(root/'index.html').read_text())
            for file in ['../elsewhere.mp4','https://example.com/video.mp4','x" onerror="alert(1)']:
                with self.assertRaises(ValueError):
                    write_viewer(root,result()|dict(windows=[window()|dict(file=file)]))


@unittest.skipUnless(all(importlib.util.find_spec(n) for n in ('numpy','cv2')), 'Requires overlay extras')
class OverlayTests(unittest.TestCase):
    def test_only_current_observed_participants_receive_boxes(self):
        import numpy as np
        rgb=np.zeros((180,320,3),dtype=np.uint8)
        frame=dict(timestamp_s=1.5,detections=[dict(track_id=1,bbox=dict(x_min=30,y_min=70,x_max=60,y_max=120)),
                                             dict(track_id=3,bbox=dict(x_min=150,y_min=70,x_max=180,y_max=120))])
        rendered=overlay_candidate(rgb,frame,[candidate()],window())
        self.assertGreater(int(rendered[70,30].sum()),0)
        self.assertEqual(int(rendered[70,150].sum()),0)
        self.assertEqual(int(rgb.sum()),0)
        # Missing participants and context padding cannot retain old boxes.
        empty=overlay_candidate(rgb,dict(timestamp_s=1.6,detections=[]),[candidate()],window())
        padding=overlay_candidate(rgb,frame|dict(timestamp_s=.5),[candidate()],window())
        self.assertEqual(int(empty[50:].sum()),0)
        self.assertEqual(int(padding[50:].sum()),0)

    def test_invalid_observed_boxes_fail(self):
        import numpy as np
        frame=dict(timestamp_s=1.5,detections=[dict(track_id=1,bbox=dict(x_min=-1,y_min=0,x_max=20,y_max=30))])
        with self.assertRaises(ValueError):
            overlay_candidate(np.zeros((100,200,3),dtype=np.uint8),frame,[candidate()],window())
