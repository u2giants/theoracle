'use client';
import {useEffect,useRef,useState} from 'react';
import type {NaturalAnswerPacketV1} from '@oracle/shared/protected-natural-question-contract';
import {QualifiedAnswerView} from './qualified-answer-view';
import {canonicalJson} from '@/lib/replacement-canonical-json';
/** Business questions only; the protected server resolves permitted scope. */
export function ConnectedAnswerPanel(){
 const [question,setQuestion]=useState(''),[submitted,setSubmitted]=useState('');
 const [packet,setPacket]=useState<NaturalAnswerPacketV1|null>(null),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const active=useRef<AbortController|null>(null);
 useEffect(()=>()=>{const previous=active.current;active.current=null;previous?.abort();},[]);
 useEffect(()=>{if(!packet)return;const until=Math.min(30000,Date.parse(packet.expires_at)-Date.now());const timer=setTimeout(()=>{setPacket(null);setMessage('The current reading window ended. Ask again for a fresh access check.');},Number.isFinite(until)?Math.max(0,until):0);return()=>clearTimeout(timer);},[packet]);
 async function ask(){
  active.current?.abort();const controller=new AbortController();active.current=controller;
  setPacket(null);setMessage('');setBusy(true);setSubmitted(question);
  try{
   if(!question.trim()||question.includes('\0')||[...question].length>4096||new TextEncoder().encode(question).length>16384){setMessage('Please use a question of at most 4,096 characters.');return;}
   const body={schema_version:1,protocol:'qualified-natural-question-v1',caller_deadline:new Date(Date.now()+25000).toISOString(),question};
   const response=await fetch('/api/consultant/replacement/v1/protected/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:canonicalJson(body),signal:controller.signal,cache:'no-store'});
   if(!response.ok)throw new Error();const value:NaturalAnswerPacketV1=await response.json();if(active.current!==controller)return;
   setPacket(value);
  }catch{if(active.current===controller)setMessage('Current authorized evidence is unavailable. No earlier answer is shown.');}
  finally{if(active.current===controller)setBusy(false);}
 }
 return <section className="space-y-4">
  <form className="space-y-3" onSubmit={e=>{e.preventDefault();void ask();}}>
   <label className="block">Your question<textarea required maxLength={8192} value={question} onChange={e=>{setQuestion(e.target.value);setPacket(null);}} className="block w-full rounded border p-2" /></label>
   <p className="text-sm">Ask about a process, handoff, exception or earlier account. If the scope is unclear, the Oracle will ask one clarifying question.</p>
   <button disabled={busy} className="rounded border px-3 py-2">{busy?'Reading current evidence…':'Ask'}</button>
  </form>
  {message&&<p role="alert">{message}</p>}
  {packet&&<section aria-label="Current answer" className="space-y-3"><h2 className="font-medium">Your question: {submitted}</h2><QualifiedAnswerView packet={packet}/></section>}
 </section>;
}
