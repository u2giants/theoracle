'use client';

import { useActionState } from 'react';
import {
  assignClaimQuestionWithState,
  type AssignClaimQuestionState,
} from '@/app/admin/claims/_actions';

type EmployeeOption = {
  id: string;
  name: string;
  role: string;
};

const initialState: AssignClaimQuestionState = {
  status: 'idle',
  message: null,
};

export function AssignQuestionForm({
  claimId,
  claimSummary,
  employees,
  compact = false,
}: {
  claimId: string;
  claimSummary: string;
  employees: EmployeeOption[];
  compact?: boolean;
}) {
  const [state, formAction, isPending] = useActionState(
    assignClaimQuestionWithState,
    initialState,
  );

  return (
    <form action={formAction} className="mt-2 space-y-2">
      <input type="hidden" name="claimId" value={claimId} />
      <label className="block text-[11px] font-medium text-muted-foreground">
        Person
        <select
          name="targetEmployeeId"
          required
          className="mt-1 w-full rounded border bg-background px-2 py-1 text-xs text-foreground"
        >
          <option value="">Choose a person</option>
          {employees.map((employee) => (
            <option key={employee.id} value={employee.id}>
              {employee.name} - {employee.role}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-[11px] font-medium text-muted-foreground">
        Question
        <textarea
          name="question"
          rows={compact ? 3 : 3}
          defaultValue={`Can you help correct or confirm this claim?\n\n${claimSummary}`}
          className="mt-1 w-full rounded border bg-background px-2 py-1 text-xs text-foreground"
        />
      </label>
      <button
        type="submit"
        disabled={isPending}
        className="rounded bg-muted px-2 py-1 text-xs text-foreground hover:bg-muted/80 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isPending ? 'Assigning...' : 'Assign question'}
      </button>
      {state.message && (
        <p
          className={`text-[11px] ${
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
