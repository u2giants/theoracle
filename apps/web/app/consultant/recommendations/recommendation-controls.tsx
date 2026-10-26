'use client';
import {useEffect,useMemo,useState,useSyncExternalStore} from 'react';
import {canonicalJson} from '@oracle/shared/protected-canonical-json';
import {adviceRecordV1,adviceSelectorV1,parseRecommendationIndexV1,parseRecommendationViewV1,parseRecommendationReceiptV1,type AdviceIndexV1,type AdviceSelectorV1,type AdviceRequestV1} from '@oracle/shared';
const endpoint='/api/consultant/replacement/v1/protected/recommendation-actions';
const labels={handoff_rework:'Handoffs and rework',approval_exception:'Approvals and exceptions',information_duplication:'Repeated information'} as const;
const text=(v:unknown)=>typeof v==='string'?v:'';
const date=(v:unknown)=>typeof v==='string'&&Number.isFinite(Date.parse(v))?new Intl.DateTimeFormat('en-US',{year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short',timeZone:'America/New_York'}).format(new Date(v)):'Unavailable';
const rows=(v:unknown)=>Array.isArray(v)?v.map(adviceRecordV1):[];
const words=(v:unknown)=>Array.isArray(v)?v.filter((x):x is string=>typeof x==='string'):[];
const deadline=()=>new Date(Date.now()+25000).toISOString().replace('.000Z','Z').replace(/\.(\d{3})Z$/,'.$1000Z');
const button='rounded border border-slate-400 px-4 py-2 text-sm font-medium hover:bg-slate-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400';
type Pending=Readonly<{operation:'feedback'|'measurement';selector:AdviceSelectorV1;command_id:string}>;
const recoveryKey='oracle2-recommendation-pending-v1',recoveryEvent='oracle2-recommendation-recovery-changed';
const subscribeRecovery=(notify:()=>void)=>{window.addEventListener('storage',notify);window.addEventListener(recoveryEvent,notify);return()=>{window.removeEventListener('storage',notify);window.removeEventListener(recoveryEvent,notify);};};
const recoverySnapshot=()=>{try{return sessionStorage.getItem(recoveryKey)??'';}catch{return '!unavailable';}};
const recoveryServerSnapshot=()=>'!loading';
function recoveredPending(raw:string){if(!raw)return {pending:undefined,error:false};try{const p=adviceRecordV1(JSON.parse(raw));if(Object.keys(p).length!==3||!['feedback','measurement'].includes(text(p.operation))||typeof p.command_id!=='string'||!/^([0-9a-f]{8})(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(p.command_id))throw new Error();return {pending:{operation:p.operation as Pending['operation'],selector:adviceSelectorV1(p.selector),command_id:p.command_id},error:false};}catch{return {pending:undefined,error:true};}}

async function exchange(request:AdviceRequestV1){
 const response=await fetch(endpoint,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},body:canonicalJson(request),signal:AbortSignal.timeout(30000)});
 if(!response.ok)throw new Error('Recommendation review unavailable');
 return new Uint8Array(await response.arrayBuffer());
}
function Measure({value}:{value:unknown}){
 if(value===null||value===undefined)return <span>Unavailable</span>;
 const m=adviceRecordV1(value);
 return <span>{text(m.amount)} {text(m.currency)} {text(m.unit).replaceAll('_',' ')} {text(m.period).replaceAll('_',' ')}</span>;
}
function RecordedMeasurementV1({payload}:{payload:unknown}){
 const p=adviceRecordV1(payload),m=adviceRecordV1(p.measurement);
 return <div className="space-y-1 text-sm"><p>Recorded source-reported value: <Measure value={m}/></p><p>Observation window: {date(m.window_start)} to {date(m.window_end)}. Observed through {date(m.observed_through)}.</p><p>{m.complete===true?'Complete report':'Incomplete report'}{m.censored===true?' · censored':''}. Exact documented population. Assertion revision {String(p.assertion_revision)}.</p><p>Documentary measurement only; causal and realized savings remain unverified.</p></div>;
}
export function RecommendationControlsV1({available}:{available:boolean}){
 const [index,setIndex]=useState<AdviceIndexV1>(),[view,setView]=useState<Readonly<Record<string,unknown>>>(),[selected,setSelected]=useState<AdviceSelectorV1>(),[option,setOption]=useState(''),[reason,setReason]=useState(''),[measurement,setMeasurement]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[receipt,setReceipt]=useState<Readonly<Record<string,unknown>>>();
 const recovery=useSyncExternalStore(subscribeRecovery,recoverySnapshot,recoveryServerSnapshot);
 const recovered=useMemo(()=>recoveredPending(recovery),[recovery]),pending=recovered.pending;
 const recoveryLoaded=recovery!=='!loading'&&!recovered.error;
 function savePending(value:Pending|undefined){if(value)sessionStorage.setItem(recoveryKey,canonicalJson(value));else sessionStorage.removeItem(recoveryKey);window.dispatchEvent(new Event(recoveryEvent));}
 const item=view?.recommendation?adviceRecordV1(view.recommendation):undefined;
 const advice=item?adviceRecordV1(item.advice):undefined;
 const options=rows(advice?.options),sources=rows(view?.measurement_sources);
 const activeMeasurement=measurement!==''?sources[Number(measurement)]:undefined;
 useEffect(()=>{if(!view)return;const timer=setTimeout(()=>{setView(undefined);setIndex(undefined);setSelected(undefined);setNotice('The view window ended. Reload current recommendations before another action.');},Math.max(0,Date.parse(text(view.valid_until))-Date.now()));return()=>clearTimeout(timer);},[view]);
 useEffect(()=>{if(!index)return;const timer=setTimeout(()=>setIndex(undefined),Math.max(0,Date.parse(index.valid_until)-Date.now()));return()=>clearTimeout(timer);},[index]);
 const locked=busy||!recoveryLoaded||!available||!!pending||!item||view?.stale===true||view?.redacted===true||view?.evidence_coverage_gap===true;
 async function refresh(){
  if(busy||pending)return;setBusy(true);setView(undefined);setSelected(undefined);setReceipt(undefined);setNotice('');
  try{setIndex(parseRecommendationIndexV1(await exchange({schema_version:1,operation:'list',caller_deadline:deadline()})));}
  catch{setIndex(undefined);setNotice('Current recommendations are unavailable. Reload when access and evidence are current.');}
  finally{setBusy(false);}
 }
 async function inspect(selector:AdviceSelectorV1){
  if(busy||pending)return;setBusy(true);setView(undefined);setSelected(undefined);setReceipt(undefined);setNotice('');setOption('');setReason('');setMeasurement('');
  try{const next=parseRecommendationViewV1(await exchange({schema_version:1,operation:'inspect',selector,caller_deadline:deadline()}));setSelected(selector);setView(next);if(next.redacted===true)setIndex(undefined);}
  catch{setIndex(undefined);setNotice('This recommendation changed or is unavailable. Reload the list.');}
  finally{setBusy(false);}
 }
 async function record(decision:'accept'|'reject'|'defer'|'measurement'){
  if(locked||!selected||!view||(!reason.trim()&&decision!=='measurement'))return;
  const command_id=crypto.randomUUID(),operation=decision==='measurement'?'measurement':'feedback';
  let request:AdviceRequestV1;
  if(decision==='measurement'){
   const source=sources[Number(measurement)];if(!source||measurement===''||view.measurement_coverage_gap)return;
   request={schema_version:1,operation:'measurement',selector:selected,expected_head:view.head_revision as number,command_id,experiment_id:text(source.experiment_id),phase:source.phase as 'baseline'|'followup',assertion_id:text(source.assertion_id),assertion_revision:source.assertion_revision as number,caller_deadline:deadline()};
  }else{
   if(decision==='accept'&&!options.some(o=>o.option_id===option))return;
   request={schema_version:1,operation:'feedback',selector:selected,expected_head:view.head_revision as number,command_id,decision,option_id:decision==='accept'?option:null,reason:reason.trim(),caller_deadline:deadline()};
  }
  // Once the write may have left this tab, preserve its exact command. A failed
  // response enables receipt-only reconciliation, never a new write or replay.
  try{savePending({operation,selector:selected,command_id});}catch{setNotice('Action recovery could not be saved. No action was sent.');return;}setBusy(true);setNotice('');
  try{setView(parseRecommendationViewV1(await exchange(request)));savePending(undefined);setReason('');setNotice(decision==='measurement'?'Source-reported measurement recorded.':'Personal review recorded.');}
  catch{setView(undefined);setIndex(undefined);setNotice('Outcome unknown. Check the saved receipt before taking another action. Keep this page open.');}
  finally{setBusy(false);}
 }
 async function reconcile(){
  if(!pending||busy)return;setBusy(true);setView(undefined);setNotice('');
  try{
   const result=parseRecommendationReceiptV1(await exchange({schema_version:1,operation:pending.operation==='feedback'?'reconcile-feedback':'reconcile-measurement',selector:pending.selector,command_id:pending.command_id,caller_deadline:deadline()}));
   setReceipt(result);setNotice('A saved receipt was found. Reload current recommendations before another action.');savePending(undefined);setIndex(undefined);setSelected(undefined);
  }catch{setNotice('The receipt is unavailable. The outcome remains unknown; no action was resent.');}
  finally{setBusy(false);}
 }
 return <section className="mx-auto max-w-5xl space-y-6 p-6 text-slate-900">
  <div><h1 className="text-2xl font-semibold">Recommendations and follow-up</h1><p className="mt-2">Compare alternatives, record a personal review and follow source-reported measurements.</p><p className="mt-1 text-sm text-slate-600">A personal review does not approve company policy, execute work or verify savings.</p></div>
  {!available&&<p role="status">Recommendation review is unavailable for this account.</p>}
  <div className="flex flex-wrap gap-3"><button className={button} disabled={!available||!recoveryLoaded||busy||!!pending} onClick={refresh}>Reload current recommendations</button>{pending&&<button className={button} disabled={busy} onClick={reconcile}>Check saved receipt only</button>}</div>
  {(notice||pending||recovered.error)&&<p role="status" className="rounded border border-amber-300 bg-amber-50 p-3">{notice||(pending?'A previous action has an unknown outcome. Check its saved receipt; no action will be resent.':'Saved action recovery is unavailable. New actions are locked in this tab.')}</p>}
  {receipt&&<p>Saved {text(receipt.kind)} receipt, recorded {date(receipt.recorded_at)}. {receipt.original_operation_window_unexpired===false?'The original action window has expired. ':''}This receipt authorizes no new action.</p>}
  {index&&<div className="space-y-4">{index.coverage_gap&&<p role="status">More permitted recommendations exist than this bounded list can show. Coverage is incomplete.</p>}{Object.entries(labels).map(([lens,label])=><section key={lens} className="space-y-2"><h2 className="text-lg font-semibold">{label}</h2><div className="flex flex-wrap gap-3">{index.entries.filter(e=>e.lens===lens).map(e=><button key={canonicalJson(e.selector)} className={button} disabled={busy||!!pending} onClick={()=>inspect(e.selector)}>{e.label}{e.label_truncated?'…':''}</button>)}{!index.entries.some(e=>e.lens===lens)&&<p className="text-sm text-slate-600">No current permitted recommendation listed.</p>}</div></section>)}</div>}
  {view?.redacted===true&&<section className="rounded border p-4"><h2 className="font-semibold">Earlier record — evidence unavailable</h2><p>The earlier action history is retained. Its reasons, source details and measurements are hidden.</p>{rows(view.events).map(e=><p key={text(e.event_id)}>Record {String(e.sequence)} · {text(e.kind)} · {date(e.recorded_at)}</p>)}</section>}
  {item&&advice&&<article className="space-y-6 rounded border p-5">
   <header><h2 className="text-xl font-semibold">{text(item.problem)}</h2><p className="text-sm">Version {String(view?.artifact_version)} · parent version {String(view?.parent_version)} · review due {date(item.review_due)}</p></header>
   <section><h3 className="font-semibold">Scope</h3><p>{text(advice.scope_note)}</p><dl className="grid gap-2 sm:grid-cols-2">{Object.entries(adviceRecordV1(item.scope)).filter(([key])=>key!=='schema_version').map(([key,value])=>{const scope=adviceRecordV1(value);return <div key={key}><dt className="capitalize">{key}</dt><dd>{scope.mode==='all'?'All in the documented scope':scope.mode==='exact'?`${words(scope.identities).length} exact documented identities`:'Unknown'}</dd></div>;})}</dl></section>
   <section><h3 className="font-semibold">Other explanations</h3><ul className="list-disc space-y-1 pl-5">{words(item.competing_explanations).map((v,i)=><li key={i}>{v}</li>)}</ul></section>
   <section className="space-y-3"><h3 className="font-semibold">Alternatives, including no change</h3>{options.map(o=><div key={text(o.option_id)} className="space-y-2 rounded border p-3"><label className="flex items-start gap-3"><input type="radio" name="recommendation-option" disabled={locked} checked={option===o.option_id} onChange={()=>setOption(text(o.option_id))}/><span className="font-medium">{text(o.title)}{o.is_no_change===true?' — no change':''}</span></label>{o.forecast?<div className="text-sm"><p>Forecast only — baseline: <Measure value={adviceRecordV1(o.forecast).baseline}/>; alternative: <Measure value={adviceRecordV1(o.forecast).alternative}/>.</p><p>Assumptions: {words(adviceRecordV1(o.forecast).assumptions).join('; ')}</p></div>:<p className="text-sm">Benefit forecast unavailable.</p>}{rows(o.downstream_costs).map((cost,i)=><p key={i} className="text-sm">{cost.kind==='missing'?'Downstream cost unavailable':<>{text(cost.kind).replaceAll('_',' ')}: <Measure value={cost.measure}/></>}</p>)}<p className="text-sm">Measured basis: {rows(o.measured_basis).length?rows(o.measured_basis).map((basis,i)=><span key={i}>{text(basis.kind).replaceAll('_',' ')}: <Measure value={basis.measure}/>; </span>):'Unavailable.'}</p></div>)}</section>
   <section><h3 className="font-semibold">Effort, risks and ownership</h3><p>{text(item.effort)}</p><ul className="list-disc pl-5">{words(item.risks).map((v,i)=><li key={i}>{v}</li>)}</ul><p>Suggested role: {text(item.owner_role_description)}</p></section>
   <section className="space-y-3"><h3 className="font-semibold">Quoted evidence</h3>{advice.opposing_unknown===true&&<p>Opposing evidence is unknown. Absence of a quote does not settle the issue.</p>}{view?.evidence_coverage_gap===true&&<p role="status">Evidence exceeds this bounded display. Review controls are unavailable.</p>}{Object.entries(adviceRecordV1(view?.evidence)).map(([polarity,quotes])=><div key={polarity}><h4 className="font-medium capitalize">{polarity}</h4>{rows(quotes).length?rows(quotes).map((q,i)=><blockquote className="my-2 border-l-4 border-slate-300 pl-3" key={i}><p className="whitespace-pre-wrap">{text(q.quote)}</p><footer className="text-xs text-slate-600">Original revision {String(q.source_revision)}, characters {String(q.start)}–{String(q.end)} · <a className="underline underline-offset-2" href={`/consultant/replacement/originals/${encodeURIComponent(text(q.source_id))}/${String(q.source_revision)}`}>Open original</a> (access checked separately)</footer></blockquote>):<p className="text-sm">No quote supplied for this category.</p>}</div>)}</section>
   <section className="space-y-3"><h3 className="font-semibold">Personal review</h3><label className="block">Reason<textarea className="mt-1 block min-h-24 w-full rounded border p-2" maxLength={1600} value={reason} disabled={locked} onChange={e=>setReason(e.target.value)}/></label><div className="flex flex-wrap gap-3"><button className={button} disabled={locked||!option||!reason.trim()} onClick={()=>record('accept')}>Accept selected option</button><button className={button} disabled={locked||!reason.trim()} onClick={()=>record('reject')}>Reject recommendation</button><button className={button} disabled={locked||!reason.trim()} onClick={()=>record('defer')}>Defer</button></div></section>
   <section className="space-y-3"><h3 className="font-semibold">Reversible experiments and measurements</h3>{rows(item.experiments).map((plan,i)=><div key={i} className="rounded border p-3"><p>{text(plan.success_metric)}</p><p>Reversible step: {text(plan.reversible_step)}</p><p className="text-sm">Baseline: {date(plan.baseline_start)} to {date(plan.baseline_end)}. Follow-up: {date(plan.followup_start)} to {date(plan.followup_end)}.</p><p className="text-sm">{text(plan.unit)} · {text(plan.currency)} · {text(plan.period)}</p></div>)}{view?.measurement_coverage_gap===true&&<p role="status">Measurement choices are incomplete; recording is unavailable.</p>}<label className="block" htmlFor="qualified-source-reported-value">Qualified source-reported value</label><select id="qualified-source-reported-value" aria-label="Qualified source-reported value" size={2} className="mt-1 block max-w-full rounded border p-2" value={measurement} disabled={locked||view?.measurement_coverage_gap===true} onChange={e=>setMeasurement(e.target.value)}><option value="">Choose an available source record</option>{sources.map((source,i)=>{const m=adviceRecordV1(source.measurement);return <option key={i} value={i}>{text(source.phase)}: {text(m.amount)} {text(m.currency)} {text(m.unit)}, {text(m.period)} · {m.complete===true?'complete':'incomplete'}{m.censored===true?', censored':''}</option>;})}</select>{activeMeasurement&&<dl className="grid gap-2 rounded bg-slate-50 p-3 text-sm sm:grid-cols-2">{Object.entries(adviceRecordV1(activeMeasurement.measurement)).filter(([key])=>!['schema_version','contract'].includes(key)).map(([key,value])=><div key={key}><dt className="capitalize">{key.replaceAll('_',' ')}</dt><dd>{key==='population_id'?'Exact documented population':typeof value==='boolean'?(value?'Yes':'No'):value===null?'Unavailable':['window_start','window_end','observed_through'].includes(key)?date(value):text(value).replaceAll('_',' ')}</dd></div>)}</dl>}<button className={button} disabled={locked||measurement===''||view?.measurement_coverage_gap===true} onClick={()=>record('measurement')}>Record selected source value</button>{!sources.length&&<p>No matching qualified source measurement is available. No amount can be entered here.</p>}{rows(view?.comparisons).map((comparison,i)=><p key={i}>{comparison.state==='reported-difference'?`Reported baseline minus follow-up: ${text(comparison.observed_difference)} ${text(comparison.currency)} ${text(comparison.unit)} ${text(comparison.period)}.`:'Comparison unavailable or incomplete.'} This does not establish causal or realized savings.</p>)}</section>
   <section><h3 className="font-semibold">Recorded personal history</h3>{rows(view?.events).length?rows(view?.events).map(e=><div key={text(e.event_id)} className="my-2 border-t pt-2"><p>{text(e.kind)} · {date(e.recorded_at)}</p>{e.payload!==null&&e.payload!==undefined&&(e.kind==='feedback'?<p>{text(adviceRecordV1(e.payload).decision)} {text(adviceRecordV1(e.payload).reason)}</p>:<RecordedMeasurementV1 payload={e.payload}/>)}</div>):<p>No personal action recorded for this version.</p>}</section>
  </article>}
 </section>;
}
