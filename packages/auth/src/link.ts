// First-login account linking — spec Part 4.4.
//
// Called server-side after Supabase Auth returns a verified user. We:
//   1. Look up the employee by email.
//   2. If missing or disabled → deny.
//   3. If found:
//        - set auth_user_id if empty (anti-hijack: only if it was null OR matches)
//        - store auth_provider / auth_provider_subject
//        - bump last_login_at
//        - return the employee
//
// IMPORTANT: This module talks to the DB via the SERVICE ROLE Drizzle client
// (bypasses RLS). It must NEVER be imported into browser code.

import { eq } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { employees, type Employee } from '@oracle/db/schema';
import type { AuthProvider } from '@oracle/shared';

export type LinkInput = {
  authUserId: string; // Supabase auth.users.id
  email: string; // verified provider email
  authProvider: AuthProvider;
  authProviderSubject?: string; // stable provider-side user id, if available
};

export type LinkResult =
  | { ok: true; employee: Employee }
  | { ok: false; reason: 'not_approved' | 'disabled' | 'hijack_attempt' };

/**
 * Link a Supabase auth user to an employees row.
 *
 * Per spec 4.4:
 *   - First login: set auth_user_id if it was null.
 *   - Subsequent logins: must match the previously-linked auth_user_id; if a
 *     different auth_user_id arrives for the same email we treat it as a hijack
 *     attempt and refuse (could be a tenant misconfig, or email reuse).
 */
export async function linkOrRejectEmployee(input: LinkInput): Promise<LinkResult> {
  const db = getDirectDb();
  const normalizedEmail = input.email.trim().toLowerCase();

  const existing = await db
    .select()
    .from(employees)
    .where(eq(employees.email, normalizedEmail))
    .limit(1);

  const row = existing[0];
  if (!row) return { ok: false, reason: 'not_approved' };
  if (row.disabledAt) return { ok: false, reason: 'disabled' };

  // Hijack guard.
  if (row.authUserId && row.authUserId !== input.authUserId) {
    return { ok: false, reason: 'hijack_attempt' };
  }

  // Update on every login: refresh last_login_at, persist provider metadata,
  // and set auth_user_id on first link.
  const [updated] = await db
    .update(employees)
    .set({
      authUserId: input.authUserId,
      authProvider: input.authProvider,
      authProviderSubject: input.authProviderSubject ?? row.authProviderSubject ?? null,
      lastLoginAt: new Date(),
    })
    .where(eq(employees.id, row.id))
    .returning();

  if (!updated) {
    // Concurrent disable/delete — be defensive.
    return { ok: false, reason: 'not_approved' };
  }

  return { ok: true, employee: updated };
}
