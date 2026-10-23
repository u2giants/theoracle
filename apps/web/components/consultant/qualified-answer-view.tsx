'use client';
import { useEffect,useState } from 'react';
import type {QuestionEffectPacketV1} from '@oracle/shared/protected-conversation-contract';
const record=(v:unknown):Record<string,unknown>|null=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:null;
const recordedTime=(value:string)=>new Date(value).toLocaleString('en-US',{timeZone:'America/New_York',year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit',timeZoneName:'short'});
/** Rendering only. The protected consumer remains the sole answer authority. */
export function QualifiedAnswerView({packet}:{packet:unknown}){
 return <QualifiedAnswerDisplay packet={packet} variant="old"/>;
}
/** Same factual renderer; new effect flags remain explicit, never relabeled old. */
export function QualifiedQuestionEffectView({packet}:{packet:Readonly<QuestionEffectPacketV1>}){
 return <QualifiedAnswerDisplay packet={packet} variant={packet.purpose==='qualified-answer-synthesis-v1'?'synthesis':'vector'}/>;
}
function QualifiedAnswerDisplay({packet,variant}:{packet:unknown;variant:'old'|'vector'|'synthesis'}){
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
 if(variant!=='old'){
  if(value?.protocol!=='question-effect-result-v1'||value.automatic_retry_allowed!==false||value.semantic_entailment_verified!==false||value.business_accepted!==false)return <p>Current qualified evidence is unavailable.</p>;
  if(value.state==='unknown')return <p role="status">The answer outcome is uncertain. Your response remains saved. Nothing will be sent again automatically.</p>;
  if(value.state==='unavailable')return <p role="status">Model assistance is unavailable. Your response remains saved.</p>;
  if(value.state==='clarification'&&typeof value.clarification==='string')return <p role="status">{value.clarification}</p>;
  if(value.state!=='observed'||value.provider_dispatched!==true)return <p>Current qualified evidence is unavailable.</p>;
 }
 if(!answer)return <p>Current qualified evidence is unavailable.</p>;
 if(variant==='old'&&(answer.business_accepted!==false||answer.provider_generation_used!==false||!Array.isArray(answer.records)||typeof answer.answer_text!=='string'))return <p>Current qualified evidence is unavailable.</p>;
 if(variant!=='old'&&(answer.business_accepted!==false||!Array.isArray(answer.records)||typeof answer.answer_text!=='string'||answer.selection!==(variant==='vector'?'qualified-vector-records-v1':'qualified-retained-facts-synthesis-v1')||answer.provider_generation_used!==(variant==='synthesis')||answer.query_embedding_used!==(variant==='vector')))return <p>Current qualified evidence is unavailable.</p>;
 const synthesis=variant==='synthesis'?record(value?.synthesis):null;
 if(variant==='synthesis'&&(synthesis?.protocol!=='qualified-answer-synthesis-references-v1'||synthesis.semantic_entailment_verified!==false||synthesis.business_accepted!==false||!Array.isArray(synthesis.factual_groups)||!Array.isArray(synthesis.gap_codes)))return <p>Current qualified evidence is unavailable.</p>;
 const classifications=new Map<string,string>();
 if(synthesis)for(const raw of synthesis.factual_groups as unknown[]){const group=record(raw);if(group&&Array.isArray(group.assertion_ids))for(const id of group.assertion_ids)if(typeof id==='string'&&typeof group.classification==='string')classifications.set(id,group.classification);}
 const interpretation=record(synthesis?.interpretation);
 function quotes(item:Record<string,unknown>,kind:string){
  const evidence=record(item.evidence),group=evidence?.[kind];if(!Array.isArray(group))return null;
  return group.map((raw,i)=>{const q=record(raw),ref=record(q?.ref);if(typeof q?.quote!=='string'||typeof ref?.source_id!=='string'||typeof ref.revision!=='number')return null;
   return <blockquote className="border-l-2 pl-3" key={`${kind}:${i}`}><p>{kind==='opposing'?'Opposing evidence':kind==='unknown'?'Uncertainty':kind==='temporal'?'Date evidence':'Supporting evidence'}</p><p>{q.quote}</p><p className="text-sm">Retained qualified original · revision {ref.revision}</p><a className="underline" href={`/consultant/replacement/originals/${encodeURIComponent(ref.source_id)}/${ref.revision}`}>Open original under current access</a></blockquote>;
  });
 }
 const coverage=record(answer.coverage);
 function scopeText(value:unknown){const scope=record(value);return ['process','customer','product','region'].map(dimension=>{const part=record(scope?.[dimension]);return `${dimension}: ${part?.mode==='all'?'all within the declared model':part?.mode==='exact'?`${Array.isArray(part.identities)?part.identities.length:0} explicitly bounded identities`:'unknown'}`;}).join(' · ');}
 return <article aria-live="polite" className="space-y-4"><p className="whitespace-pre-wrap">{answer.answer_text as string}</p>
  <details><summary>Coverage and limits</summary><p>Declared population: {String(coverage?.declared_population??'Unknown')}</p><p>Model revision {String(answer.model_version)} · {String(coverage?.declared_process_count)} declared processes · {String(coverage?.declared_assertion_count)} declared statements.</p><p>{String(coverage?.returned_assertion_count)} statements shown from {String(coverage?.selected_assertion_count)} selected statements. {coverage?.complete_within_declared_model===true?'Complete within this declared model and selected scope.':'Coverage is incomplete; omitted records must not be treated as absent.'} Company-wide completeness is not verified.</p><p>{variant==='old'?'Selection uses bounded lexical matching of retained qualified records. Semantic search and generated interpretation have not been used.':variant==='vector'?'Selection used a recorded question embedding and retained qualified records. Search quality and semantic meaning remain unverified.':'A model grouped retained qualified records. Factual words and quotes below remain the retained records; semantic entailment and business acceptance remain unverified.'}</p></details>
  <details><summary>Dates and retained history</summary><p>Business date checked: {typeof answer.valid_at==='string'?recordedTime(answer.valid_at):'Unknown'}</p><p>{typeof answer.known_at==='string'?`Only accounts recorded by ${recordedTime(answer.known_at)} are selected.`:'Current retained account selected.'}</p><p>Fresh access check: {typeof value?.checked_at==='string'?recordedTime(value.checked_at):'Unknown'}. This does not renew the original delivery or approval.</p><p>Original delivery: {typeof value?.retained_delivered_at==='string'?recordedTime(value.retained_delivered_at):'Unknown'}</p></details>
  {(answer.records as unknown[]).map((raw,i)=>{const item=record(raw),assertion=record(item?.assertion);if(!item||!assertion||typeof assertion.value!=='string')return null;
   return <section key={i} data-qualified-assertion={typeof assertion.assertion_id==='string'?assertion.assertion_id:undefined} className="space-y-2 rounded border p-3"><p>{assertion.value}</p>{typeof assertion.assertion_id==='string'&&classifications.has(assertion.assertion_id)&&<p>{classifications.get(assertion.assertion_id)==='opposed'?'Opposing accounts retained':classifications.get(assertion.assertion_id)==='unknown'?'Uncertainty retained':'Reported account'}</p>}<p className="text-sm">Reported account · {item.applicability==='unknown'?'Applicability unknown':'Applies to the selected scope'}</p><details><summary>Scope and dates for this statement</summary><p>{scopeText(assertion.scope)}</p><p>{assertion.valid_time==='evidenced'&&typeof assertion.valid_from==='string'?`Applies from ${recordedTime(assertion.valid_from)}${typeof assertion.valid_to==='string'?` until ${recordedTime(assertion.valid_to)}`:'; no evidenced end date'}.`:'Business validity dates are unknown.'}</p><p>This is a reported account; it is not confirmed company policy.</p></details><details open><summary>Sources, opposing accounts and uncertainty</summary>{['supporting','opposing','unknown','temporal'].map(kind=>quotes(item,kind))}</details></section>;
  })}
  {synthesis&&<section aria-label="Synthesis limits"><p>These groups do not establish company policy.</p>{(synthesis.gap_codes as string[]).map(code=><p key={code}>{({unconfirmed_policy:'Company policy remains unconfirmed.',coverage_incomplete:'Coverage is incomplete.',missing_evidence:'Supporting evidence is missing.',opposing_accounts:'Opposing accounts remain unresolved.',applicability_unknown:'Applicability remains unknown.'} as Record<string,string>)[code]??'An unresolved gap remains.'}</p>)}</section>}
  {interpretation?.classification==='inference/unverified interpretation'&&typeof interpretation.text==='string'&&<section aria-label="Unverified interpretation"><p>Inference / unverified interpretation</p><p>{interpretation.text}</p><p>This is separate from the factual records and is not company policy.</p></section>}
  {Array.isArray(answer.findings)&&answer.findings.map((raw,i)=>{const f=record(raw);return typeof f?.text==='string'?<p key={i}>Retained finding: {f.text} ({String(f.status)})</p>:null;})}
  {Array.isArray(answer.business_decisions_as_of)&&answer.business_decisions_as_of.map((raw,i)=>{const d=record(raw);return typeof d?.decision_kind==='string'&&typeof d.recorded_at==='string'?<p key={i}>Retained {d.decision_kind} decision recorded {recordedTime(d.recorded_at)}. {d.withdrawn_as_of===true?'Withdrawn by the selected known time.':d.challenged_as_of===true?'Challenged by the selected known time.':'No withdrawal or challenge recorded by the selected known time.'}</p>:null;})}
  {Array.isArray(answer.caveats)&&answer.caveats.map((c,i)=>typeof c==='string'?<p className="text-sm" key={i}>{c}</p>:null)}
 </article>;
}
