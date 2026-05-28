'use client';

import { useActionState, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  addDepartmentMember,
  removeDepartmentMember,
  updateDepartment,
  type MemberMutationState,
  type UpdateDepartmentState,
} from '../_actions';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const initialUpdate: UpdateDepartmentState = { ok: false };
const initialMember: MemberMutationState = { ok: false };

export interface DepartmentCardProps {
  id: string;
  displayLabel: string;
  description: string | null;
  headEmployeeId: string | null;
  /** Employees currently assigned to this department. */
  members: { id: string; name: string; email: string }[];
  /** Employees NOT in this department, used to populate "Add member". */
  nonMembers: { id: string; name: string; email: string }[];
}

export function DepartmentCard(props: DepartmentCardProps) {
  const router = useRouter();
  const [updateState, dispatchUpdate, isUpdatePending] = useActionState(
    updateDepartment,
    initialUpdate,
  );
  const [addState, dispatchAdd, isAddPending] = useActionState(
    addDepartmentMember,
    initialMember,
  );
  const [removeState, dispatchRemove, isRemovePending] = useActionState(
    removeDepartmentMember,
    initialMember,
  );

  // After any successful action, refresh the server data so the card
  // re-renders with the new state (head dropdown options, member list, etc.).
  useEffect(() => {
    if (updateState.ok || addState.ok || removeState.ok) {
      router.refresh();
    }
  }, [updateState.ok, addState.ok, removeState.ok, router]);

  const [selectedNonMemberId, setSelectedNonMemberId] = useState('');

  return (
    <section className="rounded-lg border bg-card p-4 space-y-4">
      {/* Top: label + description + head */}
      <form action={dispatchUpdate} className="space-y-3">
        <input type="hidden" name="id" value={props.id} />

        <div className="flex items-start gap-2">
          <div className="flex-1 space-y-1">
            <label className="text-[11px] font-medium uppercase text-muted-foreground">
              Display label
            </label>
            <Input
              name="displayLabel"
              defaultValue={props.displayLabel}
              className="h-9 max-w-sm text-sm"
              required
            />
          </div>
          <code className="mt-5 rounded bg-muted px-1.5 py-0.5 text-[10px]">
            {props.id}
          </code>
        </div>

        <div className="space-y-1">
          <label className="text-[11px] font-medium uppercase text-muted-foreground">
            Description
          </label>
          <textarea
            name="description"
            defaultValue={props.description ?? ''}
            placeholder="Optional"
            rows={2}
            className="flex w-full max-w-md rounded-md border border-input bg-background px-3 py-1.5 text-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>

        <div className="space-y-1">
          <label className="text-[11px] font-medium uppercase text-muted-foreground">
            Department head
          </label>
          <select
            name="headEmployeeId"
            defaultValue={props.headEmployeeId ?? 'none'}
            className="flex h-9 w-full max-w-sm rounded-md border border-input bg-background px-2 text-sm"
          >
            <option value="none">— no head assigned —</option>
            {props.members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
          <p className="text-[11px] text-muted-foreground">
            Only current members are eligible. To assign someone new as head,
            add them as a member first.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button type="submit" size="sm" disabled={isUpdatePending}>
            {isUpdatePending ? 'Saving…' : 'Save'}
          </Button>
          {updateState.ok && !isUpdatePending && (
            <span className="text-xs text-green-600">Saved.</span>
          )}
          {updateState.error && (
            <span className="text-xs text-red-600">{updateState.error}</span>
          )}
        </div>
      </form>

      {/* Members */}
      <div className="space-y-2 border-t pt-3">
        <div className="flex items-baseline justify-between">
          <h3 className="text-sm font-semibold">Members ({props.members.length})</h3>
        </div>

        {props.members.length === 0 ? (
          <p className="text-xs text-muted-foreground">No one assigned yet.</p>
        ) : (
          <ul className="space-y-1">
            {props.members.map((m) => (
              <li
                key={m.id}
                className="flex items-center justify-between rounded border bg-background px-2 py-1 text-xs"
              >
                <div>
                  <span className="font-medium">{m.name}</span>{' '}
                  <span className="text-muted-foreground">{m.email}</span>
                </div>
                <form action={dispatchRemove}>
                  <input type="hidden" name="departmentId" value={props.id} />
                  <input type="hidden" name="employeeId" value={m.id} />
                  <button
                    type="submit"
                    disabled={isRemovePending}
                    className="text-[11px] text-red-600 hover:underline disabled:opacity-50"
                    aria-label={`Remove ${m.name}`}
                  >
                    remove
                  </button>
                </form>
              </li>
            ))}
          </ul>
        )}

        {removeState.error && (
          <p className="text-xs text-red-600">{removeState.error}</p>
        )}

        {/* Add member */}
        {props.nonMembers.length > 0 && (
          <form
            action={dispatchAdd}
            className="flex items-center gap-2 pt-2"
            onSubmit={() => setSelectedNonMemberId('')}
          >
            <input type="hidden" name="departmentId" value={props.id} />
            <select
              name="employeeId"
              value={selectedNonMemberId}
              onChange={(e) => setSelectedNonMemberId(e.target.value)}
              className="flex h-8 flex-1 max-w-xs rounded-md border border-input bg-background px-2 text-xs"
              required
            >
              <option value="">+ Add member…</option>
              {props.nonMembers.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name} ({e.email})
                </option>
              ))}
            </select>
            <Button
              type="submit"
              size="sm"
              variant="outline"
              disabled={isAddPending || !selectedNonMemberId}
            >
              {isAddPending ? 'Adding…' : 'Add'}
            </Button>
            {addState.error && (
              <span className="text-xs text-red-600">{addState.error}</span>
            )}
          </form>
        )}
      </div>
    </section>
  );
}
