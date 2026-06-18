// Admin → Employees tab.
// Demonstrates Phase 1 acceptance gate #3 — admin can read ALL employees via
// the privileged DIRECT_URL connection (service role bypasses RLS).

import { asc, eq, sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  departments,
  employees,
  employeeDepartments,
  employeeIdentities,
} from '@oracle/db/schema';
import { requireAdmin } from '@/lib/auth-guard';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  getGraphConfigOrNull,
  listTenantUsers,
  type GraphTenantUser,
} from '@/lib/microsoft-graph';
import { formatNYDateTime } from '@/lib/time';
import { AddEmployeeForm } from './_components/add-employee-form';
import { EmployeeAccessForm } from './_components/employee-access-form';
import { EditEmployeeDepartments } from './_components/edit-employee-departments';
import { M365InviteRow } from './_components/m365-invite-row';

export default async function AdminEmployeesPage() {
  const me = await requireAdmin();
  const db = getDirectDb();

  const graphConfigured = getGraphConfigOrNull() !== null;
  const m365UsersPromise: Promise<GraphTenantUser[] | { error: string }> =
    graphConfigured
      ? listTenantUsers().catch((err: unknown) => ({
          error: err instanceof Error ? err.message : String(err),
        }))
      : Promise.resolve([]);

  const [rows, deptOptions, m365Result] = await Promise.all([
    db
      .select({
        id: employees.id,
        name: employees.name,
        email: employees.email,
        role: employees.role,
        isAdmin: employees.isAdmin,
        disabledAt: employees.disabledAt,
        lastLoginAt: employees.lastLoginAt,
        identityProviders: sql<string | null>`
          string_agg(DISTINCT ${employeeIdentities.authProvider}::text, ', ')
        `,
        // Enum IDs from the new join table (authoritative for routing).
        departmentIds: sql<string[]>`
          coalesce(
            array_remove(array_agg(DISTINCT ${employeeDepartments.departmentId}::text), NULL),
            '{}'
          )
        `,
        // Human-readable summary string for the collapsed view.
        departmentLabels: sql<string | null>`
          string_agg(DISTINCT ${departments.displayLabel}, ', ' ORDER BY ${departments.displayLabel})
        `,
        // Legacy text[] kept until retrieval-plan migrates off it.
        legacyDepartments: employees.departments,
      })
      .from(employees)
      .leftJoin(employeeIdentities, eq(employeeIdentities.employeeId, employees.id))
      .leftJoin(employeeDepartments, eq(employeeDepartments.employeeId, employees.id))
      .leftJoin(departments, eq(departments.id, employeeDepartments.departmentId))
      .groupBy(employees.id)
      .orderBy(employees.createdAt),
    db
      .select({ id: departments.id, displayLabel: departments.displayLabel })
      .from(departments)
      .orderBy(asc(departments.displayLabel)),
    m365UsersPromise,
  ]);

  // Diff the tenant directory against existing employees by email (case-
  // insensitive). Already-onboarded users drop off this list.
  const existingEmails = new Set(rows.map((r) => r.email.toLowerCase()));
  const activeCount = rows.filter((r) => !r.disabledAt).length;
  const disabledCount = rows.length - activeCount;
  const m365Error =
    Array.isArray(m365Result) ? null : 'error' in m365Result ? m365Result.error : null;
  const m365UsersToInvite = Array.isArray(m365Result)
    ? m365Result
        .filter((u) => u.accountEnabled && !existingEmails.has(u.email))
        .sort((a, b) => a.displayName.localeCompare(b.displayName))
    : [];

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Employees</h1>
        <p className="text-sm text-muted-foreground">
          Authorization roster. Adding a row here is what authorizes a person to
          sign into Oracle (spec Part 4.3). Department membership is many-to-many
          and drives clarification routing (see{' '}
          <a href="/admin/departments" className="underline">
            Departments
          </a>
          ).
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add employee</CardTitle>
        </CardHeader>
        <CardContent>
          <AddEmployeeForm departmentOptions={deptOptions} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {activeCount} active employees
            {disabledCount > 0 && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {disabledCount} disabled
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Email</th>
                  <th className="py-2 pr-4">Role</th>
                  <th className="py-2 pr-4 w-80">Department(s)</th>
                  <th className="py-2 pr-4">Access</th>
                  <th className="py-2 pr-4">Admin</th>
                  <th className="py-2 pr-4">Identities</th>
                  <th className="py-2 pr-4">Last login</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => {
                  // Prefer join-table summary when present; fall back to the
                  // legacy text[] for employees who haven't been migrated yet.
                  const summary =
                    e.departmentLabels ??
                    (e.legacyDepartments.length > 0
                      ? `${e.legacyDepartments.join(', ')} (unmapped)`
                      : '');
                  return (
                    <tr
                      key={e.id}
                      className={`border-b last:border-0 align-top ${e.disabledAt ? 'opacity-60' : ''}`}
                    >
                      <td className="py-2 pr-4 font-medium">{e.name}</td>
                      <td className="py-2 pr-4">{e.email}</td>
                      <td className="py-2 pr-4">{e.role}</td>
                      <td className="py-2 pr-4">
                        <EditEmployeeDepartments
                          employeeId={e.id}
                          currentDepartmentIds={e.departmentIds}
                          departmentOptions={deptOptions}
                          currentSummary={summary}
                        />
                      </td>
                      <td className="py-2 pr-4">
                        <EmployeeAccessForm
                          employeeId={e.id}
                          disabled={!!e.disabledAt}
                          disabledAt={e.disabledAt?.toISOString() ?? null}
                          isCurrentUser={e.id === me.id}
                        />
                      </td>
                      <td className="py-2 pr-4">{e.isAdmin ? 'yes' : 'no'}</td>
                      <td className="py-2 pr-4">{e.identityProviders ?? '—'}</td>
                      <td className="py-2 pr-4">
                        {e.lastLoginAt
                          ? formatNYDateTime(e.lastLoginAt)
                          : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            M365 users not yet in Oracle
            {graphConfigured && !m365Error && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {m365UsersToInvite.length} found
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!graphConfigured ? (
            <p className="text-sm text-muted-foreground">
              Microsoft Graph backend not configured. Set{' '}
              <code>AZURE_TENANT_ID</code>, <code>AZURE_GRAPH_CLIENT_ID</code>,
              and <code>AZURE_GRAPH_CLIENT_SECRET</code> in the environment to
              enable the tenant directory pull.
            </p>
          ) : m365Error ? (
            <p className="text-sm text-red-600">
              Graph call failed: {m365Error}
            </p>
          ) : m365UsersToInvite.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Every active M365 user is already in Oracle.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4">Name</th>
                    <th className="py-2 pr-4">Email</th>
                    <th className="py-2 pr-4">Job title</th>
                    <th className="py-2 pr-4 w-48">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {m365UsersToInvite.map((u) => (
                    <M365InviteRow
                      key={u.id}
                      email={u.email}
                      displayName={u.displayName}
                      jobTitle={u.jobTitle}
                    />
                  ))}
                </tbody>
              </table>
              <p className="mt-3 text-[11px] text-muted-foreground">
                Invite pre-provisions an Oracle employee row using the M365 name
                + email and sends a Supabase invite email (Brevo). The user can
                then sign in via Microsoft SSO or magic link — either way, the
                identity linker merges them into this row. Department(s) can be
                assigned via the inline editor above once the row appears.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
