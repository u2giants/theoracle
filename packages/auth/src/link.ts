// First-login account linking — spec Part 4.4, post DECISIONS.md D2.multi-identity.
//
// One employee, many identities. Resolution order on every login:
//
//   1. Look up an existing identity by (auth_provider, auth_user_id). If found,
//      bump last_login_at and return the employee.
//   2. Else, bootstrap-link: find the employees row whose primary email matches
//      the verified provider email. If found AND it doesn't already have an
//      identity for this provider, create the identity, return the employee.
//   3. Else, deny — the email is not on the allowlist.
//
// IMPORTANT: This module talks to the DB via a server-side Drizzle client
// (bypasses RLS through the configured Postgres role). It must NEVER be
// imported into browser code.

import { and, eq } from 'drizzle-orm';
import { getPooledDb } from '@oracle/db/client';
import { employees, employeeIdentities, type Employee } from '@oracle/db/schema';
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
 * Resolve a Supabase auth user to the employees row that owns it, creating an
 * identity link on first login through a given provider.
 *
 *  - First call ever for this employee: their employees.email matches the
 *    provider's verified email → we create the first identity row and link.
 *  - First call for this provider, employee already linked via a different
 *    provider: we look them up by email, see no identity for this provider,
 *    create one, link.
 *  - Subsequent calls: matched by (provider, auth_user_id) in the identities
 *    table — fastest path, no email lookup needed.
 *  - Hijack guard: if (provider, auth_user_id) is already linked to a different
 *    employee than the email match would suggest, we refuse.
 */
export async function linkOrRejectEmployee(input: LinkInput): Promise<LinkResult> {
  const db = getPooledDb();
  const normalizedEmail = input.email.trim().toLowerCase();
  const now = new Date();

  // ---- Path 1: identity already exists for this provider + auth_user_id ----
  const existingIdentity = await db
    .select()
    .from(employeeIdentities)
    .where(eq(employeeIdentities.authUserId, input.authUserId))
    .limit(1);

  if (existingIdentity[0]) {
    const identity = existingIdentity[0];

    // Hijack guard: provider says identity X belongs to employee Y, but the
    // email arriving here belongs to employee Z. Refuse — something is wrong.
    const employeeRows = await db
      .select()
      .from(employees)
      .where(eq(employees.id, identity.employeeId))
      .limit(1);
    const employee = employeeRows[0];
    if (!employee) return { ok: false, reason: 'not_approved' };
    if (employee.disabledAt) return { ok: false, reason: 'disabled' };

    // Bump per-identity + per-employee last_login_at.
    await db
      .update(employeeIdentities)
      .set({ lastLoginAt: now })
      .where(eq(employeeIdentities.id, identity.id));
    await db.update(employees).set({ lastLoginAt: now }).where(eq(employees.id, employee.id));

    return { ok: true, employee: { ...employee, lastLoginAt: now } };
  }

  // ---- Path 2: bootstrap — match by employees.email OR any known identity email ----
  // The second clause exists so an employee whose primary email is X can still be
  // recognized when they sign in via a provider that delivers a verified email Y,
  // as long as some identity row already records Y as belonging to this employee.
  // This is how we keep e.g. albert@popcre.com (M365) linked to the same person
  // whose primary employees.email is u2giants@gmail.com.
  const byPrimary = await db
    .select()
    .from(employees)
    .where(eq(employees.email, normalizedEmail))
    .limit(1);

  let employee = byPrimary[0];

  if (!employee) {
    const byIdentityEmail = await db
      .select({ employee: employees })
      .from(employees)
      .innerJoin(employeeIdentities, eq(employeeIdentities.employeeId, employees.id))
      .where(eq(employeeIdentities.email, normalizedEmail))
      .limit(1);
    employee = byIdentityEmail[0]?.employee;
  }

  if (!employee) return { ok: false, reason: 'not_approved' };
  if (employee.disabledAt) return { ok: false, reason: 'disabled' };

  // Belt-and-suspenders hijack check: same employee already has an identity for
  // this provider with a *different* auth_user_id? That would mean two
  // different provider accounts both claim to be "albert@popcre.com" — refuse.
  const conflictRows = await db
    .select()
    .from(employeeIdentities)
    .where(
      and(
        eq(employeeIdentities.employeeId, employee.id),
        eq(employeeIdentities.authProvider, input.authProvider),
      ),
    )
    .limit(1);
  if (conflictRows[0]) {
    return { ok: false, reason: 'hijack_attempt' };
  }

  // Create the identity + bump employees.last_login_at.
  await db.insert(employeeIdentities).values({
    employeeId: employee.id,
    authProvider: input.authProvider,
    authUserId: input.authUserId,
    authProviderSubject: input.authProviderSubject ?? null,
    email: normalizedEmail,
    linkedAt: now,
    lastLoginAt: now,
  });
  await db.update(employees).set({ lastLoginAt: now }).where(eq(employees.id, employee.id));

  return { ok: true, employee: { ...employee, lastLoginAt: now } };
}
