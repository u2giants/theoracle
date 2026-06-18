export const dynamic = 'force-dynamic';

import { asc, eq, isNull } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  claimReviewGroupMembers,
  claimReviewGroups,
  employees,
} from '@oracle/db/schema';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  addClaimReviewGroupMember,
  archiveClaimReviewGroup,
  createClaimReviewGroup,
  removeClaimReviewGroupMember,
} from './_actions';

export default async function AdminClaimGroupsPage() {
  const db = getDirectDb();
  const [groups, employeeRows, memberRows] = await Promise.all([
    db
      .select({
        id: claimReviewGroups.id,
        name: claimReviewGroups.name,
        description: claimReviewGroups.description,
      })
      .from(claimReviewGroups)
      .where(isNull(claimReviewGroups.archivedAt))
      .orderBy(asc(claimReviewGroups.name)),
    db
      .select({
        id: employees.id,
        name: employees.name,
        role: employees.role,
        email: employees.email,
      })
      .from(employees)
      .where(isNull(employees.disabledAt))
      .orderBy(asc(employees.name)),
    db
      .select({
        groupId: claimReviewGroupMembers.groupId,
        employeeId: claimReviewGroupMembers.employeeId,
        employeeName: employees.name,
        employeeRole: employees.role,
      })
      .from(claimReviewGroupMembers)
      .innerJoin(employees, eq(employees.id, claimReviewGroupMembers.employeeId))
      .where(isNull(employees.disabledAt))
      .orderBy(asc(employees.name)),
  ]);

  const membersByGroup = new Map<string, typeof memberRows>();
  for (const member of memberRows) {
    const members = membersByGroup.get(member.groupId) ?? [];
    members.push(member);
    membersByGroup.set(member.groupId, members);
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Review Groups</h1>
        <p className="text-sm text-muted-foreground">
          Reusable people lists for sending claim-review questions to several
          employees at once.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">New group</CardTitle>
        </CardHeader>
        <CardContent>
          <form action={createClaimReviewGroup} className="grid gap-3 md:grid-cols-[18rem_1fr_auto]">
            <label className="text-xs font-medium text-muted-foreground">
              Name
              <input
                name="name"
                required
                maxLength={120}
                className="mt-1 w-full rounded border bg-background px-3 py-2 text-sm text-foreground"
              />
            </label>
            <label className="text-xs font-medium text-muted-foreground">
              Description
              <input
                name="description"
                className="mt-1 w-full rounded border bg-background px-3 py-2 text-sm text-foreground"
              />
            </label>
            <button
              type="submit"
              className="self-end rounded bg-foreground px-3 py-2 text-sm text-background hover:bg-foreground/90"
            >
              Create group
            </button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{groups.length} groups</CardTitle>
        </CardHeader>
        <CardContent>
          {groups.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No review groups yet.
            </p>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {groups.map((group) => {
                const members = membersByGroup.get(group.id) ?? [];
                const memberIds = new Set(members.map((member) => member.employeeId));
                const availableEmployees = employeeRows.filter((employee) => !memberIds.has(employee.id));

                return (
                  <section key={group.id} className="rounded border bg-background p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h2 className="font-medium">{group.name}</h2>
                        {group.description && (
                          <p className="mt-1 text-xs text-muted-foreground">{group.description}</p>
                        )}
                      </div>
                      <form action={archiveClaimReviewGroup}>
                        <input type="hidden" name="groupId" value={group.id} />
                        <button
                          type="submit"
                          className="rounded border px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                        >
                          Archive
                        </button>
                      </form>
                    </div>

                    <div className="mt-4 space-y-2">
                      <div className="text-xs font-medium text-muted-foreground">
                        {members.length} members
                      </div>
                      {members.length === 0 ? (
                        <p className="text-xs text-muted-foreground">No members yet.</p>
                      ) : (
                        <ul className="space-y-2">
                          {members.map((member) => (
                            <li
                              key={`${group.id}-${member.employeeId}`}
                              className="flex items-center justify-between gap-3 rounded bg-muted px-2 py-1.5"
                            >
                              <span className="min-w-0 text-xs">
                                <span className="font-medium text-foreground">{member.employeeName}</span>
                                <span className="text-muted-foreground"> - {member.employeeRole}</span>
                              </span>
                              <form action={removeClaimReviewGroupMember}>
                                <input type="hidden" name="groupId" value={group.id} />
                                <input type="hidden" name="employeeId" value={member.employeeId} />
                                <button
                                  type="submit"
                                  className="rounded border bg-background px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
                                >
                                  Remove
                                </button>
                              </form>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>

                    <form action={addClaimReviewGroupMember} className="mt-4 flex gap-2">
                      <input type="hidden" name="groupId" value={group.id} />
                      <select
                        name="employeeId"
                        className="min-w-0 flex-1 rounded border bg-background px-2 py-1 text-xs text-foreground"
                        disabled={availableEmployees.length === 0}
                      >
                        <option value="">Add member</option>
                        {availableEmployees.map((employee) => (
                          <option key={employee.id} value={employee.id}>
                            {employee.name} - {employee.role}
                          </option>
                        ))}
                      </select>
                      <button
                        type="submit"
                        disabled={availableEmployees.length === 0}
                        className="rounded bg-muted px-2 py-1 text-xs text-foreground hover:bg-muted/80 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Add
                      </button>
                    </form>
                  </section>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
