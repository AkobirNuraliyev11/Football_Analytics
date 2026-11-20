"""Create a new local review job from fingerprinted saved observations, without inference.

Original job and predictions remain unchanged. This updates geometry/maps only;
it does not rerun detection, tracking or classification, and generates no videos.
"""
import argparse,json,shutil,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.jobs import JobStore,run_one
from football_intelligence.model_assets import sha256
from football_intelligence.ingestion import write_manifest


def review_saved_job(source_root, identity, destination_root):
    if Path(source_root).resolve()==Path(destination_root).resolve():
        raise ValueError('Use a separate review workspace to preserve the original queue')
    original=JobStore(source_root);parent=original.get(identity)
    if parent['status']!='completed':raise ValueError('Source job must be completed')
    src=original.directory(identity);analysis=src/'analysis'
    core=('manifest.json','tracks.jsonl','calibrations.jsonl','telemetry.jsonl','telemetry-summary.json')
    if sha256(src/'source.video')!=parent['source_sha256']:raise ValueError('Source fingerprint mismatch')
    for name in core:
        if sha256(analysis/name)!=parent['result']['artifacts'][name]['sha256']:
            raise ValueError('Saved artifact fingerprint mismatch: '+name)
    store=JobStore(destination_root)
    with store.worker_lock():
        with store.connect() as db:
            if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','cancel_requested')").fetchone()[0]:
                raise ValueError('Review queue must be idle')
        new_id=str(uuid.uuid4());dest=store.directory(new_id);dest.mkdir()
        shutil.copyfile(src/'source.video',dest/'source.video')
        store.enqueue(new_id,parent['source_sha256'],parent['max_frames'],render_media=False,parent_id=identity)
        def cached_pipeline(source,output,**options):
            output.mkdir(exist_ok=False)
            for name in core:
                shutil.copyfile(analysis/name,output/name)
                if sha256(output/name)!=parent['result']['artifacts'][name]['sha256']:
                    raise ValueError('Artifact changed during copy')
            manifest=json.loads((output/'manifest.json').read_text())
            manifest['saved_observations_review']={'parent_job':identity,'detector_rerun':False,
                'tracker_rerun':False,'classifier_rerun':False,
                'note':'New geometry/maps from existing predictions; original errors may remain.'}
            manifest['preview_enabled']=False
            manifest['artifacts']=[n for n in manifest['artifacts'] if n!='preview.mp4']
            manifest['video']['source']=str(source)
            write_manifest(output/'manifest.json',manifest)
            last=json.loads((output/'tracks.jsonl').read_text().splitlines()[-1])
            options['progress_callback'](manifest['processed_frames'],last['timestamp_s'])
            return manifest
        run_one(store,pipeline=cached_pipeline)
        result=store.get(new_id)
        if result['status']!='completed':raise RuntimeError(result['error'])
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_id');parser.add_argument('--source-data-dir',type=Path,default=Path('data/backend'))
    parser.add_argument('--review-data-dir',type=Path,default=Path('data/review-backend'))
    a=parser.parse_args();r=review_saved_job(a.source_data_dir,a.job_id,a.review_data_dir)
    print(json.dumps({'job_id':r['id'],'status':r['status'],'coverage':r['result']['coverage'],
                      'metric_measurements_available':r['result']['metric_measurements_available']},indent=2))
