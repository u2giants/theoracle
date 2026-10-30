'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

// Admin-only "Rebuild map" (plan step 10): queues resolve; the worker chains
// project and communities after it.
export function RebuildMapButton() {
  const [state, setState] = useState<'idle' | 'busy'>('idle');
  const [message, setMessage] = useState<string | null>(null);

  async function rebuild() {
    setState('busy');
    setMessage(null);
    try {
      const response = await fetch('/api/brain/map/rebuild', { method: 'POST' });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail ?? body.error ?? `failed (${response.status})`);
      setMessage(
        body.queued
          ? 'Rebuild queued: matching, graph and area reports will refresh in turn.'
          : 'A rebuild is already queued or running.',
      );
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'rebuild failed');
    } finally {
      setState('idle');
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="outline" onClick={rebuild} disabled={state === 'busy'}>
        Rebuild map
      </Button>
      {message && <span className="text-sm text-muted-foreground">{message}</span>}
    </div>
  );
}
