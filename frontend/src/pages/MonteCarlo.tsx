import {useState} from 'react';
import type {Study,MonteCarlo,User} from '../types/domain';
import {mcApi,type McConfig} from '../api/mc';
import {PageTitle} from '../components/common/PageTitle';
import {Badge} from '../components/common/Badge';
import {Empty} from '../components/common/Empty';
import {Notice} from '../components/common/Notice';
import {Table} from '../components/common/Table';
import {useAsync} from '../hooks/useAsync';
import {dec,pct,scientific} from '../utils/format';

const DEFAULTS:McConfig={study_id:0,name:'固定边际条件抽样检验',seed:20261116,epsilon:0.01,min_draws:100,max_draws:20000,batch_size:500};

function verdictLabel(v:string){return v==='reject'?'拒绝独立（显著关联）':'未拒绝独立';}

export function MonteCarloPage({studies,mcRuns,user,reloadMc}:{studies:Study[];mcRuns:MonteCarlo[];user:User;reloadMc:()=>Promise<any>}){
 const [form,setForm]=useState<McConfig>(DEFAULTS);
 const [selectedId,setSelectedId]=useState(0);
 const {busy,error,message,act}=useAsync();
 const selected=mcRuns.find(m=>m.id===selectedId)||mcRuns[0];
 const set=<K extends keyof McConfig>(k:K,v:McConfig[K])=>setForm(f=>({...f,[k]:v}));
 const studyName=(id:number)=>studies.find(s=>s.id===id)?.name||('#'+id);
 const active=selected;
 const r=active?.result;
 const live=active?.ledger;
 const canWrite=user.role!=='viewer';
 const canPause=active&&!active.is_stale&&(active.status==='running'||active.status==='queued');
 const canResume=active&&!active.is_stale&&active.status==='paused';
 return <>
  <PageTitle index="05 / CONDITIONAL MONTE CARLO" title="固定行列合计，再问关联是否罕见。" description="Patefield 固定边际条件抽样：整体 Pearson χ² 的 Monte Carlo p 与逐格 Haberman 残差的全表 BH-FDR 校正；支持按精度提前停止、并发分批、中断续跑，同种子结果可复算。"/>
  <Notice error={error} message={message}/>
  <div className="config-grid">
   <form className="editor" onSubmit={e=>{e.preventDefault();act(async()=>{const created=await mcApi.create({...form,study_id:form.study_id||studies[0]?.id});await reloadMc();setSelectedId(created.id);},'条件抽样检验已排队，worker 将并发分批执行')}}>
    <h2>配置一次条件抽样检验</h2>
    <fieldset disabled={busy||!canWrite||!studies.length}>
     <label>检验名称<input value={form.name} maxLength={100} onChange={e=>set('name',e.target.value)} required/></label>
     <label>列联研究<select value={form.study_id||studies[0]?.id||''} onChange={e=>set('study_id',+e.target.value)}>{studies.map(s=><option key={s.id} value={s.id}>{s.name} / {s.rows}×{s.columns} / N={s.total}</option>)}</select></label>
     <div className="form-grid">
      <label>随机种子（同种子可复算）<input type="number" min={0} max={2147483647} step={1} value={form.seed} onChange={e=>set('seed',+e.target.value)} required/></label>
      <label>目标精度 ε（99%置信半宽上限）<input type="number" min={0.0001} max={0.1} step={0.0001} value={form.epsilon} onChange={e=>set('epsilon',+e.target.value)} required/></label>
      <label>最少有效抽样量<input type="number" min={100} max={10000000} step={100} value={form.min_draws} onChange={e=>set('min_draws',+e.target.value)} required/></label>
      <label>抽样预算上限（耗尽即判未定）<input type="number" min={100} max={10000000} step={100} value={form.max_draws} onChange={e=>set('max_draws',+e.target.value)} required/></label>
      <label>单批抽样量（并发分批）<input type="number" min={10} max={100000} step={10} value={form.batch_size} onChange={e=>set('batch_size',+e.target.value)} required/></label>
     </div>
     <div className="protocol-check"><b>停止与误差保障</b><p>达到 ε 对应 Wilson 99% 半宽且不少于最少抽样量即提前停止；预算耗尽仍未达精度则明确“结论未定”。每个批次由 (种子, 批次号) 派生独立随机流，乱序返回、重复投递、中断续跑与同种子顺序执行得到相同停止位置与结论；停止后的晚到批次不计入。</p></div>
     <button className="primary">{busy?'正在提交…':'提交条件抽样检验 →'}</button>
    </fieldset>
    {!canWrite&&<p>导览观察员可读取检验结果，提交与暂停/恢复需研究员权限。</p>}
   </form>
   <aside className="method-notes">
    <small>READING ORDER / 判定口径</small>
    <h2>整体先于<br/>逐格。</h2>
    <ol>
     <li><b>固定边际条件分布</b><p>每张模拟表与观察表行列合计完全一致，稀疏表下不再依赖渐近 χ² 近似。</p></li>
     <li><b>整体关联 p</b><p>以模拟 χ² ≥ 观察 χ² 的加一估计给出 Monte Carlo p，并附 Wilson 99% 置信区间。</p></li>
     <li><b>逐格 BH-FDR</b><p>逐格 p 经 Benjamini–Hochberg 全表误报控制（FDR 5%），未校正残差不再被读作显著偏好。</p></li>
    </ol>
    <p className="fine">条件检验回答“在固定边际下关联是否罕见”，不证明因果偏好；结论仍需独立小样试验。</p>
   </aside>
  </div>

  <div className="section-title"><h2>检验队列</h2><small>每3秒刷新有效抽样量与判定状态</small></div>
  {!mcRuns.length?<Empty title="还没有条件抽样检验" help="选择列联研究并配置精度与预算后提交。"/>
   :<Table headers={['检验 / 研究','状态','有效抽样量','目标精度 ε','停止原因','失效','']}>
    {mcRuns.map(m=><tr key={m.id} className={selected?.id===m.id?'selected':''}>
     <td><small>MC / {String(m.id).padStart(3,'0')} · seed {m.seed}</small><strong>{m.name}</strong><small>{studyName(m.study_id)}</small></td>
     <td><Badge status={m.status}/></td>
     <td>{m.ledger?.draws??0}<small>预算 {m.max_draws.toLocaleString()}</small></td>
     <td>{dec(m.epsilon,4)}</td>
     <td>{m.result?.stop_reason||'—'}</td>
     <td>{m.is_stale?'已失效':'有效'}</td>
     <td><button className="text-button" onClick={()=>setSelectedId(m.id)}>查看判定依据 ↗</button></td>
    </tr>)}
   </Table>}

  {active&&<section className="mc-detail">
   <div className="run-selector">
    <select aria-label="选择检验" value={active.id} onChange={e=>setSelectedId(+e.target.value)}>{mcRuns.map(m=><option key={m.id} value={m.id}>{m.name} / {studyName(m.study_id)}</option>)}</select>
    <Badge status={active.status}/>
    {canWrite&&<div className="actions">
     <button disabled={!canPause||busy} onClick={()=>act(async()=>{await mcApi.setStatus(active.id,'paused');await reloadMc();},'检验已暂停，在途批次返回后不再调度')}>暂停</button>
     <button className="primary" disabled={!canResume||busy} onClick={()=>act(async()=>{await mcApi.setStatus(active.id,'running');await reloadMc();},'检验已恢复，按同种子从下个批次续跑')}>恢复</button>
    </div>}
    <small>SHA-256 {active.source_fingerprint.slice(0,26)}…</small>
   </div>

   {active.is_stale&&<div className="notice error" role="alert">源数据已更新，本检验已失效（{active.stale_reason||'源指纹改变'}）。历史结果与对应图仍可查看，但不再代表当前数据；请基于新数据另建检验。</div>}
   {active.error&&<div className="notice error" role="alert">{active.error}</div>}

   <div className="mc-live">
    <span>有效抽样量 <b>{live?.draws??0}</b></span>
    <span>已合并批次 <b>{live?.next_index??0}</b></span>
    <span>在途批次 <b>{Object.keys(active.in_flight||{}).length}</b></span>
    <span>待合并乱序批次 <b>{Object.keys(active.pending_batches||{}).length}</b></span>
    <span>整体极端计数 <b>{live?.overall_extreme??0}</b></span>
    <span>停止批次位置 <b>{active.stop_index??'未停止'}</b></span>
   </div>

   {!r?.effective_draws?<Empty title="检验进行中或尚未产出判定" help="达到精度或耗尽预算后，这里给出整体关联与逐格 BH 判定；中断期间可暂停后恢复续跑。"/>
    :<>
     <div className={'mc-verdict '+r.decision} role="status">
      <small>FINAL DECISION / {r.stop_reason}</small>
      <h2>{r.decision==='succeeded'?(r.overall.verdict==='reject'?'拒绝行列表独立：存在显著关联。':'未拒绝行列表独立。'):'结论未定（预算耗尽或中断）'}</h2>
      <p>{r.conclusion}</p>
     </div>
     <div className="inertia-summary">
      <div><small>观察 Pearson χ²</small><b>{dec(r.overall.observed_chi_square)}</b></div>
      <div><small>Monte Carlo p（加一估计）</small><b>{scientific(r.overall.p_value)}</b></div>
      <div><small>p 的 Wilson 99% 区间</small><b><span>{scientific(r.overall.p_ci_low)} – {scientific(r.overall.p_ci_high)}</span></b></div>
      <div><small>渐近 χ² p（对照）</small><b>{scientific(r.overall.asymptotic_p_value)}</b><small className={r.overall.asymptotic_reliable?'':'warn'}>{r.overall.asymptotic_reliable?'期望计数规则未触发':'稀疏表：渐近 p 不可靠'}</small></div>
      <div><small>有效抽样 / 目标精度</small><b>{r.effective_draws.toLocaleString()}<span> ε={dec(r.epsilon_target,4)}</span></b><small>最差半宽 {dec(r.worst_case_half_width,5)}</small></div>
     </div>
     <div className="section-title"><h2>逐格判断（全表 BH-FDR {pct(r.bh_fdr)} 控制）</h2><small>极端次数=模拟 |校正残差| ≥ 观察值的批次数；区间为 Wilson 99%</small></div>
     <Table headers={['行 × 列','观察 / 期望','|校正残差|','极端次数','MC p','p 99%区间','BH 校正 p','判定']}>
      {r.cells.map(c=>{const row=r.row_categories?.[c.row_index];const col=r.column_categories?.[c.column_index];
       return <tr key={c.row_index+'-'+c.column_index} className={c.verdict==='reject'?'mc-reject':''}>
        <td><strong>{row?.label||c.row_index} × {col?.label||c.column_index}</strong><small>{row?.code} / {col?.code}</small></td>
        <td>{c.observed}<small>E={dec(c.expected,2)}</small></td>
        <td>{dec(c.adjusted_residual_abs,2)}</td>
        <td>{c.extreme_count}</td>
        <td>{scientific(c.p_value)}</td>
        <td>{scientific(c.p_ci_low)}–{scientific(c.p_ci_high)}</td>
        <td>{scientific(c.bh_adjusted_p)}</td>
        <td><span className={'mc-cell-verdict '+c.verdict}>{verdictLabel(c.verdict)}</span></td>
      </tr>})}
     </Table>
     <p className="fine">逐格判定基于固定边际条件抽样并经全表 BH 校正，控制错误发现率；“未拒绝”不等于无差异，仅表示当前抽样证据不足。结构关联不等于因果偏好。</p>
    </>}
  </section>}
 </>;
}
