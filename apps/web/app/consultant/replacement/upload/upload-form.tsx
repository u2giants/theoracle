'use client';
import { useRef,useState } from 'react';
import { createOriginalUploadSession,type OriginalUploadSession } from '@/lib/replacement-original-upload';
export default function OriginalUploadForm(){
 const [file,setFile]=useState<File|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const session=useRef<OriginalUploadSession|null>(null);
 async function upload(){if(!file||busy)return;setBusy(true);setMessage('Uploading original…');session.current=createOriginalUploadSession();
  try{const result=await session.current.run(file,value=>setMessage(value.state==='receiving'?`Received ${value.received_bytes} of ${file.size} bytes.`:'Upload in progress.'));
   setMessage(result.state==='committed'?'Original uploaded. Reading and review are still required.':result.state==='cancelled'?'Upload closed. No rollback or remote stop is confirmed.':'Upload outcome is unknown.');
  }catch(error){setMessage(error instanceof Error?error.message:'Upload outcome is unknown.');}finally{setBusy(false);session.current=null;}
 }
 return <form className="space-y-4" onSubmit={event=>{event.preventDefault();void upload();}}><label className="block">Original PDF<input className="block" type="file" accept="application/pdf" disabled={busy} onChange={event=>{setFile(event.target.files?.[0]??null);setMessage('');}} /></label><button type="submit" disabled={!file||busy}>Upload original</button>{busy&&<button type="button" onClick={()=>{session.current?.cancel();setMessage('Stopping further data after the current request. Remote stop is not confirmed.');}}>Stop sending</button>}<p role="status" aria-live="polite">{message}</p></form>;
}
