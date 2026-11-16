import {request,post} from './client';import type {MonteCarlo} from '../types/domain';
export type McConfig={study_id:number;name:string;seed:number;epsilon:number;min_draws:number;max_draws:number;batch_size:number};
export const mcApi={
 list:()=>request<MonteCarlo[]>('/monte-carlo'),
 create:(data:McConfig)=>post('/monte-carlo',data),
 setStatus:(id:number,status:'running'|'paused')=>request('/monte-carlo/'+id+'/status',{method:'PATCH',body:JSON.stringify({status})}),
};
