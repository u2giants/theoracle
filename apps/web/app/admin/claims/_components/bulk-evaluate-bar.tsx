'use client';

import { useActionState } from 'react';
import {
  assignClaimQuestionBulkWithState,
  type AssignClaimQuestionState,
} from '@/app/admin/claims/_actions';

type EmployeeOption = {
  id: string;
  name: string;
  role: string;
};

type GroupOption = {
  id: string;
  name: string;
  memberCount: number;
};

const initialState: AssignClaimQuestionState = {
  status: 'idle',
  message: null,
};

/**
 * Bulk "ask selected to evaluate" bar for the claims table. Row checkboxes on
 * pending claims associate to this form via the HTML `form="bulk-evaluate"`
 * attribute (the form lives outside the table so per-row forms don't nest).
 * The reviewer ticks claims, picks people/groups here, and each selected claim
 * is routed to those recipients — China-team recipients are asked in Chinese
 * automatically (handled server-side per recipient locale).
 */
export function BulkEvaluateBar({
  employees,
  groups,
}: {
  employees: EmployeeOption[];
  groups: GroupOption[];
}) {
  const [state, formAction, isPending] = useActionState(
    assignClaimQuestionBulkWithState,
    initialState,
  );

  return (
    <form
      id="bulk-evaluate"
      action={formAction}
      className="flex flex-wrap items-end gap-3 rounded border border-dashed p-3 text-sm"
    >
      <label className="block text-[11px] font-medium text-muted-foreground">
        People
        <select
          name="targetEmployeeIds"
          multiple
          size={4}
          className="mt-1 w-56 rounded border bg-background px-2 py-1 text-xs text-foreground"
        >
          {employees.map((employee) => (
            <option key={employee.id} value={employee.id}>
              {employee.name} - {employee.role}
            </option>
          ))}
        </select>
      </label>
      {groups.length > 0 && (
        <label className="block text-[11px] font-medium text-muted-foreground">
          Groups
          <select
            name="targetGroupIds"
            multiple
            size={Math.min(groups.length, 4)}
            className="mt-1 w-56 rounded border bg-background px-2 py-1 text-xs text-foreground"
          >
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name} ({group.memberCount})
              </option>
            ))}
          </select>
        </label>
      )}
      <button
        type="submit"
        disabled={isPending}
        className="rounded bg-foreground px-3 py-1 text-xs text-background hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isPending ? 'Sending…' : 'Ask selected to evaluate'}
      </button>
      <span className="w-full text-xs text-muted-foreground">
        Tick pending claims below, choose who should weigh in, then send. Each
        recipient is asked in their own language — China-team members get the
        question in Chinese automatically. Anyone already asked about a given
        claim is skipped.
      </span>
      {state.message && (
        <p
          className={`w-full text-[11px] ${
            state.status === 'success' ? 'text-green-700' : 'text-red-700'
          }`}
          role={state.status === 'error' ? 'alert' : 'status'}
        >
          {state.message}
        </p>
      )}
    </form>
  );
}
