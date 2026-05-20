// Next 15 cookie adapter — wraps next/headers cookies() for @oracle/auth.

import { cookies } from 'next/headers';
import {
  createAuthClient,
  createServiceRoleClient,
  type CookieAdapter,
} from '@oracle/auth/server';

async function makeAdapter(): Promise<CookieAdapter> {
  const store = await cookies();
  return {
    get(name) {
      return store.get(name)?.value;
    },
    set(name, value, options) {
      try {
        store.set({ name, value, ...options });
      } catch {
        // Setting cookies from a Server Component is not allowed.
        // Auth callback / route handlers use the route-handler variant below.
      }
    },
    remove(name, options) {
      try {
        store.set({ name, value: '', ...options, maxAge: 0 });
      } catch {
        // ditto
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
