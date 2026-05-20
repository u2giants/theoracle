// Next 16 cookie adapter — wraps next/headers cookies() for @oracle/auth.
// Uses the @supabase/ssr v0.10+ getAll/setAll cookie shape.

import { cookies } from 'next/headers';
import {
  createAuthClient,
  createServiceRoleClient,
  type CookieAdapter,
} from '@oracle/auth/server';

async function makeAdapter(): Promise<CookieAdapter> {
  const store = await cookies();
  return {
    getAll() {
      return store.getAll().map((c) => ({ name: c.name, value: c.value }));
    },
    setAll(toSet) {
      try {
        for (const { name, value, options } of toSet) {
          store.set({ name, value, ...options });
        }
      } catch {
        // Setting cookies from a Server Component is not allowed; the
        // middleware/route-handler paths still succeed. Supabase tolerates
        // this — the session simply won't be refreshed in RSC.
      }
    },
  };
}

export async function getServerSupabase() {
  const adapter = await makeAdapter();
  return createAuthClient(adapter);
}

export function getServiceRoleSupabase() {
  return createServiceRoleClient();
}
