'use client';
import { useEffect, useRef, useState } from 'react';

export function SourceDownload() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function download() {
    controller.current?.abort();
    const abort = new AbortController(); controller.current = abort;
    setBusy(true); setError('');
    try {
      const response = await fetch('/api/consultant/source?metadata=1', { credentials: 'same-origin', cache: 'no-store', signal: abort.signal });
      if (!response.ok) throw new Error('Source download is unavailable.');
      const descriptor = await response.json();
      if (!Number.isSafeInteger(descriptor.bytes) || descriptor.bytes < 1 || descriptor.bytes > 64 * 1024 * 1024 || descriptor.chunk_bytes !== 1024 * 1024 || !/^[0-9a-f]{64}$/.test(descriptor.sha256) || !/^[0-9a-f]{40}$/.test(descriptor.revision)) throw new Error('Source download could not be verified.');
      const chunks: ArrayBuffer[] = [];
      for (let start = 0; start < descriptor.bytes; start += descriptor.chunk_bytes) {
        const end = Math.min(start + descriptor.chunk_bytes, descriptor.bytes) - 1;
        const part = await fetch('/api/consultant/source', { credentials: 'same-origin', cache: 'no-store', signal: abort.signal, headers: { Range: `bytes=${start}-${end}`, 'If-Match': `"${descriptor.sha256}"` } });
        if (part.status !== 206 || part.headers.get('etag') !== `"${descriptor.sha256}"` || part.headers.get('x-oracle-source-revision') !== descriptor.revision || part.headers.get('content-range') !== `bytes ${start}-${end}/${descriptor.bytes}`) throw new Error('Source access or revision changed. Restart the download.');
        const bytes = await part.arrayBuffer();
        if (bytes.byteLength !== end - start + 1) throw new Error('Source download was incomplete.');
        chunks.push(bytes);
      }
      const blob = new Blob(chunks, { type: 'application/gzip' });
      const seal = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())), value => value.toString(16).padStart(2, '0')).join('');
      if (seal !== descriptor.sha256 || abort.signal.aborted) throw new Error('Source download could not be verified.');
      const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'oracle-source.tar.gz'; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (problem) { if (!abort.signal.aborted) setError(problem instanceof Error ? problem.message : 'Source download failed.'); }
    finally { if (controller.current === abort) setBusy(false); }
  }
  return <div><a className="underline" href="/api/consultant/source" aria-disabled={busy} onClick={event => { event.preventDefault(); if (!busy) void download(); }}>{busy ? 'Preparing source download…' : 'Download corresponding source (AGPL)'}</a>{error && <p role="alert">{error}</p>}</div>;
}
