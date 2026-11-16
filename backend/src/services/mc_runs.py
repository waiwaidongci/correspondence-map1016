from datetime import datetime,timezone
from sqlalchemy import select
from fastapi import HTTPException
from src.models import MonteCarloRun,ContingencyStudy
from src.constants.enums import McStatus
from src.utils.serialize import row
from src.services.catalog import table_data
from src.services import mc_engine
from src.services.mc_fingerprint import mc_fingerprint
from .audit import record

TERMINAL={McStatus.SUCCEEDED,McStatus.INDETERMINATE,McStatus.FAILED,McStatus.STALE}
IN_FLIGHT_GRACE_SECONDS=300
MAX_PENDING=500
DISPATCH_CONCURRENCY=2


def list_runs(db):
 return [row(x) for x in db.scalars(select(MonteCarloRun).order_by(MonteCarloRun.id.desc()))]

def get_run(db,id):
 obj=db.get(MonteCarloRun,id)
 if not obj:raise HTTPException(404,'条件抽样检验不存在')
 return obj

def _active_inputs(db,study_id):
 study,rows,cols,cells,table=table_data(db,study_id)
 A,keep_r,keep_c,n=mc_engine.active_table(table)
 active_rows=[rows[i] for i in range(len(rows)) if keep_r[i]]
 active_cols=[cols[j] for j in range(len(cols)) if keep_c[j]]
 return study,active_rows,active_cols,A

def create_run(db,data,user):
 if not db.get(ContingencyStudy,data.study_id):raise HTTPException(404,'列联研究不存在')
 if data.min_draws>data.max_draws:raise HTTPException(422,'最少抽样量不能超过预算上限')
 if not (mc_engine.MIN_DRAWS<=data.min_draws and data.max_draws<=mc_engine.MAX_DRAWS_LIMIT):
  raise HTTPException(422,'抽样量超出允许范围')
 if not (mc_engine.BATCH_MIN<=data.batch_size<=mc_engine.BATCH_MAX):raise HTTPException(422,'批次大小超出允许范围')
 if not (mc_engine.EPS_MIN<=data.epsilon<=mc_engine.EPS_MAX):raise HTTPException(422,'精度目标超出允许范围')
 study,active_rows,active_cols,A=_active_inputs(db,data.study_id)
 fingerprint=mc_fingerprint(study,active_rows,active_cols,A.tolist())
 target=mc_engine.stopping_plan(data.max_draws,data.epsilon,data.min_draws)
 obj=MonteCarloRun(study_id=data.study_id,name=data.name,seed=data.seed,epsilon=data.epsilon,
  min_draws=data.min_draws,max_draws=data.max_draws,batch_size=data.batch_size,
  source_fingerprint=fingerprint,status=McStatus.QUEUED,creator_id=user.id,
  ledger={'draws':0,'overall_extreme':0,'cell_extreme':[[0]*A.shape[1] for _ in range(A.shape[0])],
   'next_index':0,'distinct_tables':None,'degenerate':False},
  pending_batches={},in_flight={},stop_index=None)
 db.add(obj);db.commit();record(db,user.email,'mc.queued',{'mc_run_id':obj.id,'target_draws':target})
 from src.worker import mc_dispatch
 try:mc_dispatch.delay(obj.id)
 except Exception:obj.status=McStatus.FAILED;obj.error='队列不可用';db.commit();raise HTTPException(503,obj.error)
 return row(obj)

def invalidate_study(db,study_id,reason):
 """Source data changed: mark every non-terminal and open run stale; stored results stay readable."""
 runs=db.scalars(select(MonteCarloRun).where(MonteCarloRun.study_id==study_id,MonteCarloRun.is_stale.is_(False))).all()
 count=0
 for obj in runs:
  obj.is_stale=True;obj.stale_reason=reason;obj.in_flight={}
  if obj.status not in (McStatus.SUCCEEDED,McStatus.INDETERMINATE,McStatus.FAILED):
   obj.status=McStatus.STALE
  count+=1
 if count:db.commit()
 return count

def set_status(db,id,status,user):
 obj=get_run(db,id)
 if obj.is_stale:raise HTTPException(409,'源数据已更新，该检验已失效；请基于新数据另建检验')
 if obj.status in TERMINAL:raise HTTPException(409,'检验已结束，不能再暂停或恢复')
 if status=='paused':
  if obj.status not in (McStatus.QUEUED,McStatus.RUNNING):raise HTTPException(409,'仅排队或计算中的检验可暂停')
  obj.status=McStatus.PAUSED;obj.in_flight={}
  record(db,user.email,'mc.paused',{'mc_run_id':id})
 else:
  if obj.status!=McStatus.PAUSED:raise HTTPException(409,'仅已暂停的检验可恢复')
  obj.status=McStatus.RUNNING
  record(db,user.email,'mc.resumed',{'mc_run_id':id})
 obj.updated_at=datetime.now(timezone.utc);db.commit()
 from src.worker import mc_dispatch
 if status=='running':
  try:mc_dispatch.delay(id)
  except Exception:pass
 return row(obj)

def _now_ts():return datetime.now(timezone.utc).timestamp()

def dispatch(db,id):
 """Fill in-flight slots up to the concurrency cap. Stale/paused/terminal runs schedule nothing."""
 obj=db.get(MonteCarloRun,id)
 if not obj or obj.is_stale or obj.status in (McStatus.PAUSED,McStatus.STALE) or obj.status in TERMINAL:return {'scheduled':0}
 if obj.status==McStatus.QUEUED:obj.status=McStatus.RUNNING
 ledger=dict(obj.ledger);in_flight=dict(obj.in_flight);pending=dict(obj.pending_batches)
 now=_now_ts()
 for key,tuple_ in list(in_flight.items()):
  if now-float(tuple_[1])>IN_FLIGHT_GRACE_SECONDS:del in_flight[key]
 if len(pending)>MAX_PENDING:
  obj.status=McStatus.FAILED;obj.error='待合并批次积压超限';db.commit();raise RuntimeError(obj.error)
 next_index=int(ledger['next_index'])
 total_batches=(obj.max_draws+obj.batch_size-1)//obj.batch_size
 scheduled=0
 from src.worker import mc_batch
 index=next_index
 while len(in_flight)<DISPATCH_CONCURRENCY and index<total_batches:
  if str(index) in in_flight or str(index) in pending:
   index+=1;continue
  size=min(obj.batch_size,obj.max_draws-index*obj.batch_size)
  try:task=mc_batch.delay(id,index,size);in_flight[str(index)]=[task.id,now]
  except Exception:break
  scheduled+=1;index+=1
 obj.in_flight=in_flight;obj.updated_at=datetime.now(timezone.utc);db.commit()
 return {'scheduled':scheduled}

def merge_batch(db,id,batch_index,overall_extreme,cell_extreme,distinct_tables,task_id):
 """Idempotent contiguous-prefix merge; out-of-order batches wait, duplicates and late batches drop."""
 obj=db.get(MonteCarloRun,id)
 if not obj:return {'accepted':False,'reason':'missing'}
 if obj.is_stale:return {'accepted':False,'reason':'stale'}
 if obj.stop_index is not None and batch_index>=obj.stop_index:return {'accepted':False,'reason':'late'}
 ledger=dict(obj.ledger);pending=dict(obj.pending_batches);in_flight=dict(obj.in_flight)
 in_flight.pop(str(batch_index),None)
 if batch_index<int(ledger['next_index']) or str(batch_index) in pending:
  obj.in_flight=in_flight;db.commit();return {'accepted':False,'reason':'duplicate'}
 pending[str(batch_index)]={'overall':int(overall_extreme),'cells':cell_extreme,'distinct':int(distinct_tables)}
 applied=[]
 while str(ledger['next_index']) in pending:
  idx=ledger['next_index'];payload=pending.pop(str(idx))
  ledger['draws']=int(ledger['draws'])+obj.batch_size if (idx+1)*obj.batch_size<=obj.max_draws else int(ledger['draws'])+(obj.max_draws-idx*obj.batch_size)
  ledger['overall_extreme']=int(ledger['overall_extreme'])+payload['overall']
  cells=[[int(a)+int(b) for a,b in zip(line,pl)] for line,pl in zip(ledger['cell_extreme'],payload['cells'])]
  ledger['cell_extreme']=cells
  if ledger['distinct_tables'] is None:ledger['distinct_tables']=payload['distinct']
  elif idx<mc_engine.DEGENERATE_BATCHES:ledger['distinct_tables']=max(ledger['distinct_tables'],payload['distinct'])
  ledger['next_index']=idx+1;applied.append(idx)
 obj.ledger=ledger;obj.pending_batches=pending;obj.in_flight=in_flight
 stop_index=None
 if ledger['next_index']>=mc_engine.DEGENERATE_BATCHES and int(ledger['distinct_tables'])==1:
  ledger['degenerate']=True;stop_index=ledger['next_index']
 elif mc_engine.meets_requirements(int(ledger['draws']),obj.epsilon,obj.min_draws) or int(ledger['draws'])>=obj.max_draws:
  stop_index=ledger['next_index']
 if stop_index is not None:
  obj.stop_index=stop_index;obj.in_flight={};obj.pending_batches={}
  try:
   _,active_rows,active_cols,A=_active_inputs(db,obj.study_id)
   inference=mc_engine.build_inference(ledger,A,obj.epsilon,obj.max_draws,obj.min_draws)
   inference['applied_batches']=stop_index;inference['distinct_tables']=ledger['distinct_tables']
   inference['row_categories']=[{k:r[k] for k in ('id','code','label')} for r in active_rows]
   inference['column_categories']=[{k:c[k] for k in ('id','code','label')} for c in active_cols]
   obj.result=inference;obj.status=inference['decision'];obj.error=None
   record(db,'worker','mc.stopped',{'mc_run_id':id,'status':obj.status,'reason':inference['stop_reason'],'draws':ledger['draws']})
  except Exception as e:
   db.rollback();obj=db.get(MonteCarloRun,id);obj.ledger=ledger;obj.status=McStatus.FAILED;obj.error=str(e)[:1000]
   record(db,'worker','mc.failed',{'mc_run_id':id,'error':obj.error})
 obj.ledger=ledger;obj.updated_at=datetime.now(timezone.utc);db.commit()
 if not obj.is_stale and obj.status not in TERMINAL and obj.status!=McStatus.PAUSED:
  from src.worker import mc_dispatch
  try:mc_dispatch.delay(id)
  except Exception:pass
 return {'accepted':True,'applied':applied,'stopped':stop_index is not None}
