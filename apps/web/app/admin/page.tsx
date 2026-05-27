// Admin → Employees tab.
// Demonstrates Phase 1 acceptance gate #3 — admin can read ALL employees via
// the privileged DIRECT_URL connection (service role bypasses RLS).

import { eq, sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { employees, employeeIdentities } from '@oracle/db/schema';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AddEmployeeForm } from './_components/add-employee-form';

export default async function AdminEmployeesPage() {
  const db = getDirectDb();

  // Pull employees with their list of linked identity providers (post
  // D2.multi-identity). string_agg gives us a per-row provider summary so we
  // don't N+1.
  const rows = await db
    .select({
      id: employees.id,
      name: employees.name,
      email: employees.email,
      role: employees.role,
      departments: employees.departments,
      isAdmin: employees.isAdmin,
      lastLoginAt: employees.lastLoginAt,
      identityProviders: sql<string | null>`
        string_agg(${employeeIdentities.authProvider}::text, ', ' ORDER BY ${employeeIdentities.authProvider})
      `,
    })
    .from(employees)
    .leftJoin(employeeIdentities, eq(employeeIdentities.employeeId, employees.id))
    .groupBy(employees.id)
    .orderBy(employees.createdAt);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Employees</h1>
        <p className="text-sm text-muted-foreground">
          Authorization roster. Adding a row here is what authorizes a person to sign
          into Oracle (spec Part 4.3). Department determines which knowledge domains the
          Oracle prioritizes when retrieving context for that employee&apos;s questions.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add employee</CardTitle>
        </CardHeader>
        <CardContent>
          <AddEmployeeForm />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{rows.length} employees</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Email</th>
                  <th className="py-2 pr-4">Role</th>
                  <th className="py-2 pr-4">Department(s)</th>
                  <th className="py-2 pr-4">Admin</th>
                  <th className="py-2 pr-4">Identities</th>
                  <th className="py-2 pr-4">Last login</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id} className="border-b last:border-0">
                    <td className="py-2 pr-4 font-medium">{e.name}</td>
                    <td className="py-2 pr-4">{e.email}</td>
                    <td className="py-2 pr-4">{e.role}</td>
                    <td className="py-2 pr-4">
                      {e.departments.length > 0 ? e.departments.join(', ') : '—'}
                    </td>
                    <td className="py-2 pr-4">{e.isAdmin ? 'yes' : 'no'}</td>
                    <td className="py-2 pr-4">{e.identityProviders ?? '—'}</td>
                    <td className="py-2 pr-4">
                      {e.lastLoginAt
                        ? new Date(e.lastLoginAt).toLocaleString()
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
