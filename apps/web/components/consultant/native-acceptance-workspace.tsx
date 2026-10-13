'use client';
import { useState } from 'react';

export function NativeAcceptanceWorkspace(){
  const [status,setStatus]=useState('Ready to check the hosted invented-data test.');
  const [result,setResult]=useState('');const [hash,setHash]=useState('');
  const [busy,setBusy]=useState(false);const [attempted,setAttempted]=useState(false);
  async function act(method:'POST'|'GET'){
    setBusy(true);setResult('');setHash('');if(method==='POST')setAttempted(true);
    try{const response=await fetch('/api/consultant/native-acceptance',{method,credentials:'same-origin',cache:'no-store'});
      const bytes=await response.arrayBuffer();
      if(!response.ok)throw Error();
      if(response.status===202){setStatus(method==='POST'?'Invented test accepted. Read its result when ready.':'Invented test is pending.');return;}
      const digest=await crypto.subtle.digest('SHA-256',bytes);
      setHash(Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join(''));
      setResult(new TextDecoder('utf-8',{fatal:true}).decode(bytes));setStatus('Hosted invented-data result received.');
    }catch{setStatus('The hosted invented-data test is unavailable. A new start is not attempted automatically.');}
    finally{setBusy(false);}
  }
  return <main className="mx-auto max-w-3xl space-y-6 p-6">
    <h1 className="text-2xl font-semibold">Hosted invented-data test</h1>
    <p>This test uses invented information. Company questions, reports, employee messages and grading remain paused.</p>
    <div className="flex flex-wrap gap-3">
      <button className="rounded border px-4 py-2 disabled:opacity-50" disabled={busy||attempted} onClick={()=>void act('POST')}>Run invented test</button>
      <button className="rounded border px-4 py-2 disabled:opacity-50" disabled={busy} onClick={()=>void act('GET')}>Read result</button>
    </div>
    <p role="status" aria-live="polite">{status}</p>
    {hash&&<p className="break-all">Result fingerprint: {hash}</p>}
    {result&&<pre className="overflow-auto whitespace-pre-wrap rounded border p-4" aria-label="Invented native result">{result}</pre>}
  </main>;
}
