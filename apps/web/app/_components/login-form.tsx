'use client';

import { useState } from 'react';
import { createSupabaseBrowserClient } from '@oracle/auth/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export function LoginForm() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function sendMagicLink(e: React.FormEvent) {
    e.preventDefault();
    setStatus('sending');
    setErrorMsg(null);
    try {
      const supabase = createSupabaseBrowserClient();
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: {
          emailRedirectTo: `${window.location.origin}/auth/callback`,
        },
      });
      if (error) throw error;
      setStatus('sent');
    } catch (err) {
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : 'Failed to send magic link.');
    }
  }

  if (status === 'sent') {
    return (
      <div className="text-sm">
        <p>
          A sign-in link has been sent to <strong>{email}</strong>. Check your inbox.
        </p>
        <p className="mt-2 text-muted-foreground">
          Phase 1 stub: production builds wire Microsoft / Google / Authentik OIDC.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={sendMagicLink} className="space-y-4">
      <Input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@popcreations.com"
        autoComplete="email"
      />
      <Button type="submit" disabled={status === 'sending'} className="w-full">
        {status === 'sending' ? 'Sending…' : 'Send magic link'}
      </Button>
      {errorMsg ? <p className="text-sm text-destructive">{errorMsg}</p> : null}
      <p className="text-xs text-muted-foreground">
        Magic link is the Phase 1 dev stub. Production: Microsoft 365, Google, Authentik.
      </p>
    </form>
  );
}
