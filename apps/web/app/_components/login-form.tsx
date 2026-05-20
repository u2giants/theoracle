'use client';

import { useState } from 'react';
import { createSupabaseBrowserClient } from '@oracle/auth/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

type Status = 'idle' | 'sending' | 'sent' | 'error';

export function LoginForm() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function signInWithOAuth(provider: 'google' | 'azure') {
    setStatus('sending');
    setErrorMsg(null);
    try {
      const supabase = createSupabaseBrowserClient();
      // Microsoft Entra: 'email' is critical — without it, Microsoft Graph returns
      // an empty `mail` field for accounts without an Exchange mailbox and Supabase
      // bails with "Error getting user email from external provider".
      const scopes =
        provider === 'azure' ? 'openid profile email User.Read' : 'openid profile email';
      const { error } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
          scopes,
        },
      });
      if (error) throw error;
      // The browser will redirect to the provider; we never reach here.
    } catch (err) {
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : `Failed to sign in with ${provider}.`);
    }
  }

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
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Button
          type="button"
          variant="outline"
          className="w-full"
          onClick={() => signInWithOAuth('azure')}
          disabled={status === 'sending'}
        >
          Sign in with Microsoft 365
        </Button>
        <Button
          type="button"
          variant="outline"
          className="w-full"
          onClick={() => signInWithOAuth('google')}
          disabled={status === 'sending'}
        >
          Sign in with Google
        </Button>
      </div>

      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-background px-2 text-muted-foreground">or</span>
        </div>
      </div>

      <form onSubmit={sendMagicLink} className="space-y-3">
        <Input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@popcreations.com"
          autoComplete="email"
        />
        <Button type="submit" disabled={status === 'sending'} className="w-full">
          {status === 'sending' ? 'Sending…' : 'Email me a magic link'}
        </Button>
      </form>

      {errorMsg ? <p className="text-sm text-destructive">{errorMsg}</p> : null}
      <p className="text-xs text-muted-foreground">
        Access is restricted to approved employees. Authentik OIDC for internal accounts coming
        later.
      </p>
    </div>
  );
}
