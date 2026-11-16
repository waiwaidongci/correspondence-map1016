import {useEffect,useCallback,useState} from 'react';import {mcApi} from '../api/mc';import type {MonteCarlo} from '../types/domain';
export function useMc(){const [runs,setRuns]=useState<MonteCarlo[]>([]),[error,setError]=useState('');
 const reload=useCallback(async()=>{try{setRuns(await mcApi.list());setError('')}catch(e){setError(e.message)}},[]);
 useEffect(()=>{reload();const t=setInterval(reload,3000);return()=>clearInterval(t)},[reload]);
 return {mcRuns:runs,mcError:error,reloadMc:reload};}
