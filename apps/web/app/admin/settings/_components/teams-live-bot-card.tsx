'use client';

import { useState, useTransition } from 'react';
import { Bot, Loader2, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

type Provider = 'elevenlabs_streaming' | 'assembly_ai_v3_streaming';

export function TeamsLiveBotCard() {
  const [meetingUrl, setMeetingUrl] = useState('');
  const [provider, setProvider] = useState<Provider>('elevenlabs_streaming');
  const [status, setStatus] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function submit() {
    const trimmed = meetingUrl.trim();
    if (!trimmed) {
      setStatus('Paste a Teams meeting link first.');
      return;
    }
    startTransition(async () => {
      setStatus(null);
      try {
        const res = await fetch('/api/teams/live/start', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            meetingUrl: trimmed,
            provider,
            botName: 'The Oracle',
          }),
        });
        const json = (await res.json()) as { ok?: boolean; error?: string; detail?: string };
        if (!res.ok || !json.ok) {
          setStatus(json.detail ?? json.error ?? 'Could not bring Oracle into the meeting.');
          return;
        }
        setStatus('Oracle is joining the Teams meeting now. If there is a lobby, admit it like any other attendee.');
      } catch (err) {
        setStatus(err instanceof Error ? err.message : 'Could not bring Oracle into the meeting.');
      }
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Bot className="size-4" />
        <span>Paste the Teams meeting link. Oracle joins as a meeting bot and listens only to finalized transcript utterances.</span>
      </div>
      <Input
        value={meetingUrl}
        onChange={(e) => setMeetingUrl(e.target.value)}
        placeholder="https://teams.microsoft.com/l/meetup-join/..."
        aria-label="Teams meeting link"
      />
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="teams-live-provider"
            checked={provider === 'elevenlabs_streaming'}
            onChange={() => setProvider('elevenlabs_streaming')}
          />
          ElevenLabs
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="teams-live-provider"
            checked={provider === 'assembly_ai_v3_streaming'}
            onChange={() => setProvider('assembly_ai_v3_streaming')}
          />
          AssemblyAI
        </label>
        <Button onClick={submit} disabled={isPending} className="ml-auto gap-2">
          {isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          Bring Oracle in
        </Button>
      </div>
      {status && <p className="text-sm text-muted-foreground">{status}</p>}
    </div>
  );
}
