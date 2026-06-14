// Server-side Supabase clients for Next.js App Router (RSC, route handlers).
// Uses @supabase/ssr cookie storage (v0.10+ getAll/setAll shape).
//
// IMPORTANT: There are two clients here.
//   * `createAuthClient`         — uses the anon key + user cookies. RLS applies.
//   * `createServiceRoleClient`  — uses the service role key. Bypasses RLS.
//
// Browser/client code must never import this file.

import { createServerClient, type CookieOptions } from '@supabase/ssr';
import { createClient } from '@supabase/supabase-js';
import WebSocket from 'ws';

export type CookieAdapter = {
  getAll(): Array<{ name: string; value: string }>;
  setAll(
    cookies: Array<{ name: string; value: string; options?: CookieOptions }>,
  ): void;
};

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Missing required env var ${name}.`);
  return v;
}

const WebSocketTransport = WebSocket as unknown as typeof globalThis.WebSocket;

export function createAuthClient(cookies: CookieAdapter) {
  return createServerClient(
    requireEnv('NEXT_PUBLIC_SUPABASE_URL'),
    requireEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY'),
    {
      cookies: {
        getAll: () => cookies.getAll(),
        setAll: (toSet) => cookies.setAll(toSet),
      },
    },
  );
}

/**
 * Service-role Supabase client (server-only). Bypasses RLS. Use for:
 *   - first-login linking (writes to employees)
 *   - Oracle route handlers that need to fetch context across employees/channels
 *
 * NEVER ship this client to the browser.
 */
export function createServiceRoleClient() {
  return createClient(
    requireEnv('NEXT_PUBLIC_SUPABASE_URL'),
    requireEnv('SUPABASE_SERVICE_ROLE_KEY'),
    {
      auth: {
        persistSession: false,
        autoRefreshToken: false,
      },
      realtime: {
        transport: WebSocketTransport,
      },
    },
  );
}

/**
 * Helper used by the /auth/callback route: given the current cookie store,
 * return { user, employee } if the employee is approved, else { error }.
 */
export async function resolveCurrentSession(cookies: CookieAdapter) {
  const supabase = createAuthClient(cookies);
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) {
    return { ok: false as const, reason: 'no_session' as const };
  }
  return { ok: true as const, user: data.user };
}

/**
 * Helper to convert the Supabase user object's app_metadata into our
 * AuthProvider enum value. For the magic-link dev stub this returns
 * 'magic_link_dev'.
 */
export function resolveAuthProvider(user: { app_metadata?: { provider?: string } }) {
  const p = user.app_metadata?.provider;
  if (p === 'google') return 'google' as const;
  if (p === 'azure' || p === 'microsoft') return 'microsoft' as const;
  if (p === 'authentik' || p === 'oidc') return 'authentik' as const;
  // Email magic-link is the Phase 1 stub.
  return 'magic_link_dev' as const;
}
