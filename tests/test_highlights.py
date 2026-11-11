from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from football_intelligence.config import AppConfig
from football_intelligence.highlights import plan_windows, plan_highlights, extract_highlights, write_plan
from football_intelligence.model_assets import sha256
from test_telemetry import frame


def event(identity, start, end, shot=0):
    return dict(event_id=identity,start_s=start,end_s=end,shot_id=shot,
                kind='sprint_candidate',measurement_quality='input_validated')


def analysis_fixture(root, source, times, *, valid=True, moving=True):
    analysis=root/'analysis';analysis.mkdir()
    config=AppConfig().to_dict()
    manifest=dict(status='completed',match_id='fixture',processed_frames=len(times),
                  source_sha256=sha256(source),pitch=config['pitch'],analytics=config['analytics'])
    (analysis/'manifest.json').write_text(json.dumps(manifest))
    rows=[]
    for index,t in enumerate(times):
        row=frame(t,x=6*t if moving else 0,ground_contact_reliable=valid)
        row['frame_index']=index;rows.append(row)
    (analysis/'tracks.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    return analysis


class HighlightPlanTests(unittest.TestCase):
    def test_planning_uses_analysis_thresholds_instead_of_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.write_bytes(b'fixture')
            analysis=analysis_fixture(root,source,[i/10 for i in range(31)])
            self.assertEqual(len(plan_highlights(analysis)['events']),1)
            path=analysis/'manifest.json';manifest=json.loads(path.read_text())
            manifest['analytics'].update(sprint_threshold_kmh=30.,highlight_padding_s=.25)
            path.write_text(json.dumps(manifest))
            result=plan_highlights(analysis)
            self.assertEqual(result['events'],[])
            self.assertEqual(result['status'],'available')
            self.assertEqual(result['padding_s'],.25)

    def test_merge_padding_and_shot_boundaries(self):
        frames=[dict(frame_index=i,timestamp_s=i*.1,shot_id=0 if i<6 else 1) for i in range(10)]
        windows=plan_windows([event(1,.1,.2),event(2,.4,.5),event(3,.7,.8,1)],frames,.2)
        self.assertEqual([(w['start_frame'],w['end_frame']) for w in windows],[(0,5),(6,9)])
        self.assertEqual(windows[0]['event_ids'],[1,2])
        self.assertEqual(windows[0]['frame_count'],6)

    def test_invalid_or_experimental_events_fail(self):
        frames=[dict(frame_index=i,timestamp_s=i*.1,shot_id=0) for i in range(10)]
        for change in [dict(end_s=2),dict(start_s=float('nan')),dict(shot_id=1),
                       dict(measurement_quality='experimental_estimate')]:
            with self.assertRaises(ValueError):
                plan_windows([event(1,.1,.2)|change],frames,.1)
        with self.assertRaises(ValueError):
            plan_windows([],frames[:2]+frames[3:],.1)
        with self.assertRaises(ValueError):
            plan_windows([],frames,-1)

    def test_unavailable_differs_from_valid_no_events_and_plan_is_data_only(self):
        for valid,status in [(False,'unavailable'),(True,'available')]:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'source';source.write_bytes(b'fixture')
                analysis=analysis_fixture(root,source,[i/10 for i in range(31)],valid=valid,moving=False)
                with patch('football_intelligence.analysis.PreviewWriter',side_effect=AssertionError('No encoder')):
                    result=write_plan(analysis,root/'plan.json')
                    extracted=extract_highlights(source,analysis,root/'empty')
                self.assertEqual(result['status'],status)
                self.assertEqual(result['windows'],[])
                self.assertEqual(extracted['clips_written'],0)
                self.assertEqual(list((root/'empty').glob('*.mp4')),[])
                with self.assertRaises(FileExistsError):
                    write_plan(analysis,root/'plan.json')


@unittest.skipUnless(all(importlib.util.find_spec(n) for n in ('av','numpy')), 'Requires video extras')
class HighlightExtractionTests(unittest.TestCase):
    def setup_source(self, root, count=23):
        import av
        import numpy as np
        source=root/'source.mkv'
        times=[round(i*.15+(.02 if i%2 else 0),3) for i in range(count)]
        with av.open(str(source),'w') as container:
            stream=container.add_stream('ffv1',rate=25)
            stream.width,stream.height,stream.pix_fmt=64,48,'yuv420p'
            stream.time_base=stream.codec_context.time_base=Fraction(1,1000)
            for index,t in enumerate(times):
                image=av.VideoFrame.from_ndarray(np.full((48,64,3),(index*8)%256,dtype=np.uint8),format='rgb24')
                image.pts=5000+round(t*1000);image.time_base=Fraction(1,1000)
                for packet in stream.encode(image):container.mux(packet)
            for packet in stream.encode():container.mux(packet)
        return source,times

    def test_variable_timestamps_source_origin_and_clip_provenance(self):
        from football_intelligence.video import iter_frames
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,times=self.setup_source(root)
            analysis=analysis_fixture(root,source,times)
            result=extract_highlights(source,analysis,root/'clips',padding_s=0)
            self.assertEqual(result['clips_written'],1)
            window=result['windows'][0]
            frames=list(iter_frames(root/'clips'/window['file']))
            self.assertEqual(len(frames),window['frame_count'])
            expected=times[window['start_frame']:window['end_frame']+1]
            for decoded,t in zip(frames,expected):
                self.assertAlmostEqual(decoded.timestamp_s,t-expected[0],places=5)
            self.assertEqual(sha256(root/'clips'/window['file']),window['sha256'])
            self.assertFalse(result['audio_included'])
            self.assertTrue((root/'clips/index.html').is_file())
            playlist=json.loads((root/'clips/playlist.json').read_text())
            self.assertEqual(playlist['clips'][0]['sha256'],window['sha256'])
            for filename,digest in result['viewer_sha256'].items():
                self.assertEqual(sha256(root/'clips'/filename),digest)
            with self.assertRaises(FileExistsError):
                extract_highlights(source,analysis,root/'clips')

    def test_wrong_source_and_mismatched_timing_publish_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,times=self.setup_source(root)
            analysis=analysis_fixture(root,source,times)
            other=root/'wrong';other.write_bytes(b'wrong video')
            with self.assertRaisesRegex(ValueError,'differs'):
                extract_highlights(other,analysis,root/'failed')
            self.assertFalse((root/'failed').exists())
            path=analysis/'tracks.jsonl'
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            rows[5]['timestamp_s']+=.001
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaisesRegex(ValueError,'timestamps'):
                extract_highlights(source,analysis,root/'failed')
            self.assertFalse((root/'failed').exists())
            self.assertFalse(list(root.glob('.highlights-*')))

    @unittest.skipUnless(importlib.util.find_spec('cv2'), 'Requires overlay extras')
    def test_overlay_extraction_and_failure_publish_together(self):
        from football_intelligence.video import iter_frames
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,times=self.setup_source(root)
            analysis=analysis_fixture(root,source,times)
            result=extract_highlights(source,analysis,root/'annotated',overlays=True,padding_s=0)
            self.assertTrue(result['overlays_included'])
            clip=list(iter_frames(root/'annotated'/result['windows'][0]['file']))
            self.assertEqual(len(clip),result['windows'][0]['frame_count'])
            self.assertEqual(clip[0].timestamp_s,0.)
            self.assertGreater(int(clip[0].rgb[:16].max())-int(clip[0].rgb[:16].min()),50)
            with patch('football_intelligence.highlight_viewer.overlay_candidate',side_effect=ValueError('Overlay failed')):
                with self.assertRaisesRegex(ValueError,'Overlay failed'):
                    extract_highlights(source,analysis,root/'failed',overlays=True)
            self.assertFalse((root/'failed').exists())
            self.assertFalse(list(root.glob('.highlights-*')))

    def test_multiple_shots_and_late_failure_are_atomic(self):
        from football_intelligence.video import iter_frames
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,times=self.setup_source(root,46)
            analysis=analysis_fixture(root,source,times)
            path=analysis/'tracks.jsonl'
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            for row in rows[23:]:row['shot_id']=1
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            result=extract_highlights(source,analysis,root/'clips',padding_s=1.)
            self.assertEqual(result['clips_written'],2)
            self.assertEqual([(w['start_frame'],w['end_frame']) for w in result['windows']],[(0,22),(23,45)])
            for window in result['windows']:
                clip=list(iter_frames(root/'clips'/window['file']))
                self.assertEqual(len(clip),23)
                self.assertEqual(clip[0].timestamp_s,0.)
            rows[30]['timestamp_s']+=.001
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaisesRegex(ValueError,'timestamps'):
                extract_highlights(source,analysis,root/'failed')
            self.assertFalse((root/'failed').exists())
            self.assertFalse(list(root.glob('.highlights-*')))
