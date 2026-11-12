import type {Job,Review,Frame,Heatmap,EventRow} from './model';
import {safeArtifact} from './model';
export async function request<T>(path:string, options:RequestInit={},signal?:AbortSignal):Promise<T>{
 const response=await fetch(path,{...options,signal,credentials:'same-origin'});
 if(!response.ok){let detail=`Request failed (${response.status})`;try{const body=await response.json();detail=typeof body.detail==='string'?body.detail:detail;}catch{}throw new Error(detail);}
 return response.json();
}
export function artifact(job:string,name:string){if(!safeArtifact(name))throw new Error('Invalid artifact name');return `/jobs/${encodeURIComponent(job)}/artifacts/${name.split('/').map(encodeURIComponent).join('/')}`;}
export async function page<T>(path:string,signal?:AbortSignal){return request<{items:T[];next_offset:number|null}>(path,{},signal);}
export async function loadReview(job:Job, signal:AbortSignal):Promise<Review>{
 const [result,heat,events,manifest]=await Promise.all([
 request<NonNullable<Job['result']>>(`/jobs/${job.id}/results`,{},signal),
 request<{items:Heatmap[];coverage?:{sample_fraction:number}}>(`/jobs/${job.id}/heatmaps`,{},signal),
 page<EventRow>(`/jobs/${job.id}/events?limit=100`,signal),
 request<{pitch:{length_m:number;width_m:number}}>(artifact(job.id,'manifest.json'),{},signal)]);
 return {title:`Analysis ${job.id.slice(0,8)}`,frames:[],radar:[],heatmaps:heat.items,coverage:heat.coverage,pitch:manifest.pitch,
 video:result.artifacts['preview.mp4']?artifact(job.id,'preview.mp4'):undefined,measurement_available:result.metric_measurements_available,
 detection_quality:result.detection_quality,events_status:result.events_status,events:events.items,scope:'Local tracking IDs; observed continuous fragments, not full-match athlete totals.'};
}
export async function frameWindow(job:string,kind:string,start:number,end:number,signal:AbortSignal){
 const rows:Frame[]=[];let offset:number|null=0;
 while(offset!==null){const p: {items:Frame[];next_offset:number|null}=await page<Frame>(`/jobs/${job}/frames/${kind}?start_s=${start}&end_s=${end}&limit=500&offset=${offset}`,signal);rows.push(...p.items);offset=p.next_offset;}
 return rows;
}
