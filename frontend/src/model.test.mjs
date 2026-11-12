import test from 'node:test';
import assert from 'node:assert/strict';
import {currentFrame,metric,safeArtifact} from './model.ts';
const f=(t,positions=[])=>({frame_index:Math.round(t*25),timestamp_s:t,shot_id:0,positions});
test('timeline never borrows a future frame or carries points across missing positions',()=>{
 const rows=[f(0,[{track_id:1}]),f(.04),f(.08,[{track_id:2}])];
 assert.equal(currentFrame(rows,-.01),undefined);
 assert.equal(currentFrame(rows,.03).positions[0].track_id,1);
 assert.deepEqual(currentFrame(rows,.04).positions,[]);
 assert.deepEqual(currentFrame(rows,.079).positions,[]);
 assert.equal(currentFrame(rows,.081).positions[0].track_id,2);
 assert.equal(currentFrame(rows,.2),undefined);
});
test('large timestamp gaps do not persist old radar positions',()=>{
 const rows=[f(0),f(.04,[{track_id:1}]),f(2)];
 assert.equal(currentFrame(rows,1),undefined);
 assert.equal(currentFrame([],0),undefined);
});
test('unavailable metrics are not zero; unsafe artifact paths are rejected',()=>{
 assert.equal(metric(null),'—');assert.equal(metric(undefined),'—');assert.equal(metric(NaN),'—');assert.equal(metric(0,' km/h'),'0.0 km/h');
 for(const p of ['../secret','tactics/../../file','/secret','file?token=secret','file\\x'])assert.equal(safeArtifact(p),false);
 assert.equal(safeArtifact('tactics/heatmap-abcd.png'),true);
});
