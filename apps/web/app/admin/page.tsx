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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AddEmployeeForm } from './_components/add-employee-form';
import { EditEmployeeDepartments } from './_components/edit-employee-departments';

export default async function AdminEmployeesPage() {
  const db = getDirectDb();

  const [rows, deptOptions] = await Promise.all([
    db
      .select({
        id: employees.id,
        name: employees.name,
        email: employees.email,
        role: employees.role,
        isAdmin: employees.isAdmin,
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
  ]);

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
                  <th className="py-2 pr-4 w-80">Department(s)</th>
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
                    <tr key={e.id} className="border-b last:border-0 align-top">
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
                      <td className="py-2 pr-4">{e.isAdmin ? 'yes' : 'no'}</td>
                      <td className="py-2 pr-4">{e.identityProviders ?? '—'}</td>
                      <td className="py-2 pr-4">
                        {e.lastLoginAt
                          ? new Date(e.lastLoginAt).toLocaleString()
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
    </div>
  );
}
