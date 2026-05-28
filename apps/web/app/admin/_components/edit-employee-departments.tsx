'use client';

import { useActionState, useState } from 'react';
import {
  updateEmployeeDepartments,
  type UpdateEmployeeDepartmentsState,
} from '../_actions';
import { Button } from '@/components/ui/button';

const initial: UpdateEmployeeDepartmentsState = { ok: false };

export interface EditEmployeeDepartmentsProps {
  employeeId: string;
  /** Department enum IDs the employee is currently assigned to. */
  currentDepartmentIds: string[];
  /** All departments to choose from, ordered for display. */
  departmentOptions: { id: string; displayLabel: string }[];
  /** Display labels for the current assignment, for the collapsed summary. */
  currentSummary: string;
}

export function EditEmployeeDepartments(props: EditEmployeeDepartmentsProps) {
  const [open, setOpen] = useState(false);
  const [state, dispatch, isPending] = useActionState(
    updateEmployeeDepartments,
    initial,
  );

  if (!open) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs">{props.currentSummary || '—'}</span>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="text-[11px] text-primary underline-offset-2 hover:underline"
        >
          edit
        </button>
      </div>
    );
  }

  return (
    <form action={dispatch} className="space-y-2">
      <input type="hidden" name="employeeId" value={props.employeeId} />
      <div className="grid grid-cols-2 gap-y-1 gap-x-3">
        {props.departmentOptions.map((d) => (
          <label key={d.id} className="flex items-center gap-1.5 text-xs">
            <input
              type="checkbox"
              name="departmentIds"
              value={d.id}
              defaultChecked={props.currentDepartmentIds.includes(d.id)}
              className="h-3.5 w-3.5"
            />
            {d.displayLabel}
          </label>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={isPending}>
          {isPending ? 'Saving…' : 'Save'}
        </Button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-[11px] text-muted-foreground hover:underline"
        >
          cancel
        </button>
        {state.ok && !isPending && (
          <span className="text-[11px] text-green-600">Saved.</span>
        )}
        {state.error && (
          <span className="text-[11px] text-red-600">{state.error}</span>
        )}
      </div>
    </form>
  );
}
