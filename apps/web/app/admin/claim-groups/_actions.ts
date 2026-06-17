'use server';

import { and, eq, isNull } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import {
  claimReviewGroupMembers,
  claimReviewGroups,
  employees,
} from '@oracle/db/schema';

function refreshGroupPages() {
  revalidatePath('/admin/claim-groups');
  revalidatePath('/admin/claims');
  revalidatePath('/claims');
}

export async function createClaimReviewGroup(formData: FormData) {
  const me = await requireAdmin();
  const name = String(formData.get('name') ?? '').trim();
  const description = String(formData.get('description') ?? '').trim();
  if (!name) throw new Error('Group name is required.');

  const db = getDirectDb();
  await db.insert(claimReviewGroups).values({
    name,
    description: description || null,
    createdByEmployeeId: me.id,
  });

  refreshGroupPages();
}

export async function addClaimReviewGroupMember(formData: FormData) {
  const me = await requireAdmin();
  const groupId = String(formData.get('groupId') ?? '').trim();
  const employeeId = String(formData.get('employeeId') ?? '').trim();
  if (!groupId || !employeeId) throw new Error('Choose a group and employee.');

  const db = getDirectDb();
  const [group] = await db
    .select({ id: claimReviewGroups.id })
    .from(claimReviewGroups)
    .where(and(eq(claimReviewGroups.id, groupId), isNull(claimReviewGroups.archivedAt)))
    .limit(1);
  if (!group) throw new Error('Group not found.');

  const [employee] = await db
    .select({ id: employees.id })
    .from(employees)
    .where(and(eq(employees.id, employeeId), isNull(employees.disabledAt)))
    .limit(1);
  if (!employee) throw new Error('Employee not found or disabled.');

  await db
    .insert(claimReviewGroupMembers)
    .values({ groupId, employeeId, addedByEmployeeId: me.id })
    .onConflictDoNothing();

  refreshGroupPages();
}

export async function removeClaimReviewGroupMember(formData: FormData) {
  await requireAdmin();
  const groupId = String(formData.get('groupId') ?? '').trim();
  const employeeId = String(formData.get('employeeId') ?? '').trim();
  if (!groupId || !employeeId) throw new Error('Choose a group and employee.');

  const db = getDirectDb();
  await db
    .delete(claimReviewGroupMembers)
    .where(
      and(
        eq(claimReviewGroupMembers.groupId, groupId),
        eq(claimReviewGroupMembers.employeeId, employeeId),
      ),
    );

  refreshGroupPages();
}

export async function archiveClaimReviewGroup(formData: FormData) {
  await requireAdmin();
  const groupId = String(formData.get('groupId') ?? '').trim();
  if (!groupId) throw new Error('Missing group.');

  const db = getDirectDb();
  await db
    .update(claimReviewGroups)
    .set({ archivedAt: new Date(), updatedAt: new Date() })
    .where(eq(claimReviewGroups.id, groupId));

  refreshGroupPages();
}
