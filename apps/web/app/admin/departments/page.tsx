// Admin → Departments tab.
//
// The list of departments is a FIXED ENUM defined in
// packages/shared/src/domains.ts. Adding or removing a department requires a
// code change + migration. What an admin CAN do here:
//   - Rename the display label.
//   - Edit the description.
//   - Add or remove members (writes both the join table and the legacy
//     employees.departments text[] used by retrieval-plan).
//   - Assign a department head — restricted to current members.

import { asc } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  departments,
  employeeDepartments,
  employees,
} from '@oracle/db/schema';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DepartmentCard } from './_components/edit-department-row';

export default async function AdminDepartmentsPage() {
  const db = getDirectDb();

  // One round trip per concept. Total query cost is tiny (9 dept rows,
  // <100 employees, <500 join rows expected for years).
  const [deptRows, allEmployees, memberJoins] = await Promise.all([
    db
      .select({
        id: departments.id,
        displayLabel: departments.displayLabel,
        description: departments.description,
        headEmployeeId: departments.headEmployeeId,
      })
      .from(departments)
      .orderBy(asc(departments.displayLabel)),
    db
      .select({
        id: employees.id,
        name: employees.name,
        email: employees.email,
      })
      .from(employees)
      .orderBy(asc(employees.name)),
    db
      .select({
        departmentId: employeeDepartments.departmentId,
        employeeId: employeeDepartments.employeeId,
      })
      .from(employeeDepartments),
  ]);

  // departmentId → Set<employeeId>
  const membersByDept = new Map<string, Set<string>>();
  for (const j of memberJoins) {
    let s = membersByDept.get(j.departmentId);
    if (!s) {
      s = new Set();
      membersByDept.set(j.departmentId, s);
    }
    s.add(j.employeeId);
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Departments</h1>
        <p className="text-sm text-muted-foreground">
          Org-unit list. Used for routing clarification requests to the right
          people. Department IDs are fixed in code; the label, description,
          membership, and head are editable below.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{deptRows.length} departments</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {deptRows.map((d) => {
              const memberSet = membersByDept.get(d.id) ?? new Set<string>();
              const members = allEmployees.filter((e) => memberSet.has(e.id));
              const nonMembers = allEmployees.filter((e) => !memberSet.has(e.id));
              return (
                <DepartmentCard
                  key={d.id}
                  id={d.id}
                  displayLabel={d.displayLabel}
                  description={d.description}
                  headEmployeeId={d.headEmployeeId}
                  members={members}
                  nonMembers={nonMembers}
                />
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
