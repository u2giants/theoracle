'use client';

import { useState } from 'react';
import { createSupabaseBrowserClient } from '@oracle/auth/client';
import { Button } from '@/components/ui/button';

const BUCKET = 'company_documents';

export function DocumentUpload({
  channelId,
  employeeId,
  onDone,
}: {
  channelId: string;
  employeeId: string;
  onDone: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function upload() {
    if (!file) return;
    setStatus('uploading');
    setErrorMsg(null);
    const supabase = createSupabaseBrowserClient();

    // Storage path: <employeeId>/<channelId>/<timestamp>-<filename>
    const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
    const path = `${employeeId}/${channelId}/${Date.now()}-${safeName}`;

    try {
      // 1. Upload bytes to Storage.
      const { error: uploadErr } = await supabase.storage
        .from(BUCKET)
        .upload(path, file, { upsert: false });
      if (uploadErr) throw uploadErr;

      // 2. Insert documents row.
      const { data: doc, error: docErr } = await supabase
        .from('documents')
        .insert({
          uploader_id: employeeId,
          file_name: file.name,
          storage_bucket: BUCKET,
          storage_path: path,
          file_type: file.type || 'application/octet-stream',
          status: 'pending_processing',
        })
        .select()
        .single();
      if (docErr) throw docErr;

      // 3. Post an attachment message so the upload appears in the channel.
      const { data: msg, error: msgErr } = await supabase
        .from('messages')
        .insert({
          channel_id: channelId,
          employee_id: employeeId,
          role: 'user',
          content: `Attached: ${file.name}`,
        })
        .select()
        .single();
      if (msgErr) throw msgErr;

      const { error: attachErr } = await supabase.from('message_attachments').insert({
        message_id: msg.id,
        document_id: doc.id,
      });
      if (attachErr) throw attachErr;

      setStatus('done');
      onDone();
    } catch (err) {
      console.error('[upload] failed', err);
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : 'Upload failed.');
    }
  }

  return (
    <div className="flex items-center gap-3">
      <input
        type="file"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="text-sm"
        disabled={status === 'uploading'}
      />
      <Button
        type="button"
        size="sm"
        onClick={upload}
        disabled={!file || status === 'uploading'}
      >
        {status === 'uploading' ? 'Uploading…' : 'Upload'}
      </Button>
      {errorMsg ? <span className="text-xs text-destructive">{errorMsg}</span> : null}
      <p className="text-xs text-muted-foreground">
        Stored in <code>{BUCKET}</code> bucket. Ingestion runs in Phase 4.
      </p>
    </div>
  );
}
