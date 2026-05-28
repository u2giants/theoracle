// Admin → Departments tab.
//
// The list of departments is a FIXED ENUM defined in
// packages/shared/src/domains.ts. Adding or removing a department requires a
// code change + migration. What an admin CAN do here:
//   - Rename the display label.
//   - Edit the description.
//   - Assign (or clear) the department head — used as the prioritized
//     recipient for clarification requests routed to this department.
//
// Department membership is many-to-many via the `employee_departments` table.
// Membership management lives on the Employees page, not here.

import { asc, eq, sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  departments,
  employeeDepartments,
  employees,
} from '@oracle/db/schema';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EditDepartmentRow } from './_components/edit-department-row';

export default async function AdminDepartmentsPage() {
  const db = getDirectDb();

  const [deptRows, employeeRows] = await Promise.all([
    db
      .select({
        id: departments.id,
        displayLabel: departments.displayLabel,
        description: departments.description,
        headEmployeeId: departments.headEmployeeId,
        memberCount: sql<number>`count(${employeeDepartments.employeeId})::int`,
        memberSummary: sql<string | null>`
          string_agg(${employees.name}, ', ' ORDER BY ${employees.name})
        `,
      })
      .from(departments)
      .leftJoin(
        employeeDepartments,
        eq(employeeDepartments.departmentId, departments.id),
      )
      .leftJoin(employees, eq(employees.id, employeeDepartments.employeeId))
      .groupBy(departments.id)
      .orderBy(asc(departments.displayLabel)),
    db
      .select({
        id: employees.id,
        name: employees.name,
        email: employees.email,
      })
      .from(employees)
      .orderBy(asc(employees.name)),
  ]);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Departments</h1>
        <p className="text-sm text-muted-foreground">
          Org-unit list. Used for routing clarification requests to the right
          people. The enum values are fixed in code; renaming the label, editing
          the description, or assigning a head is a one-click action below.
          Membership is managed on the{' '}
          <a href="/admin" className="underline">
            Employees
          </a>{' '}
          page.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{deptRows.length} departments</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="py-2 pr-4 w-32">ID</th>
                  <th className="py-2 pr-4">Label / Description / Head</th>
                  <th className="py-2 pr-4 w-64">Members</th>
                </tr>
              </thead>
              <tbody>
                {deptRows.map((d) => (
                  <EditDepartmentRow
                    key={d.id}
                    id={d.id}
                    displayLabel={d.displayLabel}
                    description={d.description}
                    headEmployeeId={d.headEmployeeId}
                    memberCount={d.memberCount}
                    memberSummary={d.memberSummary ?? ''}
                    employees={employeeRows}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
