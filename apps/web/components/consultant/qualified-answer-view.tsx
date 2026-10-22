'use client';
import { useEffect,useState } from 'react';
const record=(v:unknown):Record<string,unknown>|null=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:null;
const recordedTime=(value:string)=>new Date(value).toLocaleString('en-US',{timeZone:'America/New_York',year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit',timeZoneName:'short'});
/** Rendering only. The protected consumer remains the sole answer authority. */
export function QualifiedAnswerView({packet}:{packet:unknown}){
 const value=record(packet),answer=record(value?.answer),expires=typeof value?.expires_at==='string'?value.expires_at:'';
 const [lease,setLease]=useState({expires:'',active:false});
 useEffect(()=>{
  let close:ReturnType<typeof setTimeout>|undefined;
  const open=setTimeout(()=>{
   const remaining=Math.min(30000,Date.parse(expires)-Date.now()),allowed=Number.isFinite(remaining)&&remaining>0;
   setLease({expires,active:allowed});
   close=setTimeout(()=>setLease({expires,active:false}),allowed?remaining:0);
  },0);
  return()=>{clearTimeout(open);if(close!==undefined)clearTimeout(close);};
 },[expires]);
 if(lease.expires!==expires||!lease.active)return <p>Request a fresh access check to see current evidence.</p>;
 if(value?.protocol==='qualified-natural-answer-v1'&&value.state==='clarification'&&value.answer===null&&typeof value.clarification==='string')return <p aria-live="polite">{value.clarification}</p>;
 if(!answer)return <p>Current qualified evidence is unavailable.</p>;
 if(answer.business_accepted!==false||answer.provider_generation_used!==false||!Array.isArray(answer.records)||typeof answer.answer_text!=='string')return <p>Current qualified evidence is unavailable.</p>;
 function quotes(item:Record<string,unknown>,kind:string){
  const evidence=record(item.evidence),group=evidence?.[kind];if(!Array.isArray(group))return null;
  return group.map((raw,i)=>{const q=record(raw),ref=record(q?.ref);if(typeof q?.quote!=='string'||typeof ref?.source_id!=='string'||typeof ref.revision!=='number')return null;
   return <blockquote className="border-l-2 pl-3" key={`${kind}:${i}`}><p>{kind==='opposing'?'Opposing evidence':kind==='unknown'?'Uncertainty':kind==='temporal'?'Date evidence':'Supporting evidence'}</p><p>{q.quote}</p><p className="text-sm">Retained qualified original · revision {ref.revision}</p><a className="underline" href={`/consultant/replacement/originals/${encodeURIComponent(ref.source_id)}/${ref.revision}`}>Open original under current access</a></blockquote>;
  });
 }
 const coverage=record(answer.coverage);
 function scopeText(value:unknown){const scope=record(value);return ['process','customer','product','region'].map(dimension=>{const part=record(scope?.[dimension]);return `${dimension}: ${part?.mode==='all'?'all within the declared model':part?.mode==='exact'?`${Array.isArray(part.identities)?part.identities.length:0} explicitly bounded identities`:'unknown'}`;}).join(' · ');}
 return <article aria-live="polite" className="space-y-4"><p className="whitespace-pre-wrap">{answer.answer_text}</p>
  <details><summary>Coverage and limits</summary><p>Declared population: {String(coverage?.declared_population??'Unknown')}</p><p>Model revision {String(answer.model_version)} · {String(coverage?.declared_process_count)} declared processes · {String(coverage?.declared_assertion_count)} declared statements.</p><p>{String(coverage?.returned_assertion_count)} statements shown from {String(coverage?.selected_assertion_count)} selected statements. {coverage?.complete_within_declared_model===true?'Complete within this declared model and selected scope.':'Coverage is incomplete; omitted records must not be treated as absent.'} Company-wide completeness is not verified.</p><p>Selection uses bounded lexical matching of retained qualified records. Semantic search and generated interpretation have not been used.</p></details>
  <details><summary>Dates and retained history</summary><p>Business date checked: {typeof answer.valid_at==='string'?recordedTime(answer.valid_at):'Unknown'}</p><p>{typeof answer.known_at==='string'?`Only accounts recorded by ${recordedTime(answer.known_at)} are selected.`:'Current retained account selected.'}</p><p>Fresh access check: {typeof value?.checked_at==='string'?recordedTime(value.checked_at):'Unknown'}. This does not renew the original delivery or approval.</p><p>Original delivery: {typeof value?.retained_delivered_at==='string'?recordedTime(value.retained_delivered_at):'Unknown'}</p></details>
  {answer.records.map((raw,i)=>{const item=record(raw),assertion=record(item?.assertion);if(!item||!assertion||typeof assertion.value!=='string')return null;
   return <section key={i} className="space-y-2 rounded border p-3"><p>{assertion.value}</p><p className="text-sm">Reported account · {item.applicability==='unknown'?'Applicability unknown':'Applies to the selected scope'}</p><details><summary>Scope and dates for this statement</summary><p>{scopeText(assertion.scope)}</p><p>{assertion.valid_time==='evidenced'&&typeof assertion.valid_from==='string'?`Applies from ${recordedTime(assertion.valid_from)}${typeof assertion.valid_to==='string'?` until ${recordedTime(assertion.valid_to)}`:'; no evidenced end date'}.`:'Business validity dates are unknown.'}</p><p>This is a reported account; it is not confirmed company policy.</p></details><details open><summary>Sources, opposing accounts and uncertainty</summary>{['supporting','opposing','unknown','temporal'].map(kind=>quotes(item,kind))}</details></section>;
  })}
  {Array.isArray(answer.findings)&&answer.findings.map((raw,i)=>{const f=record(raw);return typeof f?.text==='string'?<p key={i}>Retained finding: {f.text} ({String(f.status)})</p>:null;})}
  {Array.isArray(answer.business_decisions_as_of)&&answer.business_decisions_as_of.map((raw,i)=>{const d=record(raw);return typeof d?.decision_kind==='string'&&typeof d.recorded_at==='string'?<p key={i}>Retained {d.decision_kind} decision recorded {recordedTime(d.recorded_at)}. {d.withdrawn_as_of===true?'Withdrawn by the selected known time.':d.challenged_as_of===true?'Challenged by the selected known time.':'No withdrawal or challenge recorded by the selected known time.'}</p>:null;})}
  {Array.isArray(answer.caveats)&&answer.caveats.map((c,i)=>typeof c==='string'?<p className="text-sm" key={i}>{c}</p>:null)}
 </article>;
}
