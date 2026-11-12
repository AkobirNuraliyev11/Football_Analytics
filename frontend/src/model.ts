export type Detection={track_id:number;kind:string;team:string;role:string;telemetry?:{speed_kmh:number|null;observed_distance_m:number|null;sprint_count:number|null;reasons?:string[]}};
export type Frame={frame_index:number;timestamp_s:number;shot_id:number;detections?:Detection[];positions?:{track_id:number;team:string;x_m:number;y_m:number;role:string}[];quality?:string};
export type Heatmap={file:string;identity:{type:string;team:string;track_id?:number;role?:string};observed_person_seconds:number;quality:string};
export type EventRow={event_id:number;kind:string;start_s:number;end_s:number;track_ids:number[]};
export type Review={title:string;frames:Frame[];radar:Frame[];heatmaps:Heatmap[];coverage?:{sample_fraction:number};pitch:{length_m:number;width_m:number};video?:string;measurement_available:boolean;events_status:string;events:EventRow[];scope:string;fragments?:Record<string,unknown>[]};
export type Job={id:string;status:string;processed_frames:number;timestamp_s:number|null;error:string|null;created_at:string;render_media:number;result?:{metric_measurements_available:boolean;events_status:string;artifacts:Record<string,unknown>}};
// A frame is valid only until its actual successor, capped at the supported gap.
// No nearest-future sample or stale position persistence across missing frames.
export function currentFrame(rows:Frame[],time:number,maxGap=.25):Frame|undefined {
 let lo=0,hi=rows.length;while(lo<hi){const mid=(lo+hi)>>>1;if(rows[mid].timestamp_s<=time+1e-6)lo=mid+1;else hi=mid;}
 const r=rows[lo-1];if(!r)return undefined;
 const next=rows[lo];const prior=rows[lo-2];
 const cadence=prior?Math.min(maxGap,r.timestamp_s-prior.timestamp_s):0;
 const validity=next&&next.timestamp_s-r.timestamp_s<=maxGap?next.timestamp_s-r.timestamp_s:cadence;
 if(time-r.timestamp_s>validity+1e-6)return undefined;return r;
}
export function metric(value:unknown,unit=''){return typeof value==='number'&&Number.isFinite(value)?`${value.toFixed(1)}${unit}`:'—';}
export function heatmapName(h:Heatmap){return h.identity.type==='team'?`Team ${h.identity.team}`:`Track #${h.identity.track_id} · ${h.identity.role}`;}
export function clock(s:number){return `${Math.floor(s/60).toString().padStart(2,'0')}:${Math.floor(s%60).toString().padStart(2,'0')}`;}
export function safeArtifact(name:string){return name.split('/').every(p=>p!=='.'&&p!=='..'&&/^[a-zA-Z0-9_.-]+$/.test(p));}
