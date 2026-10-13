'use client';
import { useState } from 'react';

export function NativeAcceptanceWorkspace(){
  const [status,setStatus]=useState('Ready to check the hosted invented-data test.');
  const [result,setResult]=useState('');const [hash,setHash]=useState('');
  const [token,setToken]=useState('');const [signedIn,setSignedIn]=useState(false);
  const [busy,setBusy]=useState(false);const [attempted,setAttempted]=useState(false);
  async function signIn(){
    setBusy(true);
    try{const response=await fetch('/api/consultant/native-acceptance/session',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({token}),cache:'no-store'});
      if(!response.ok)throw Error();setToken('');setSignedIn(true);setStatus('Signed in for the hosted invented-data test.');
    }catch{setSignedIn(false);setStatus('Hosted invented-data sign-in is unavailable.');}
    finally{setBusy(false);}
  }
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
    {!signedIn&&<form className="space-y-3" onSubmit={event=>{event.preventDefault();void signIn();}}><label className="block" htmlFor="native-token">Invented test sign-in token</label><input id="native-token" type="password" autoComplete="off" value={token} onChange={event=>setToken(event.target.value)} className="w-full rounded border px-3 py-2"/><button className="rounded border px-4 py-2" disabled={busy||!token} type="submit">Sign in</button></form>}
    <div className="flex flex-wrap gap-3">
      <button className="rounded border px-4 py-2 disabled:opacity-50" disabled={busy||attempted||!signedIn} onClick={()=>void act('POST')}>Run invented test</button>
      <button className="rounded border px-4 py-2 disabled:opacity-50" disabled={busy||!signedIn} onClick={()=>void act('GET')}>Read result</button>
    </div>
    <p role="status" aria-live="polite">{status}</p>
    {hash&&<p className="break-all">Result fingerprint: {hash}</p>}
    {result&&<pre className="overflow-auto whitespace-pre-wrap rounded border p-4" aria-label="Invented native result">{result}</pre>}
  </main>;
}
