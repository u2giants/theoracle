'use client';

import { useActionState } from 'react';
import {
  updateEmployeeAccess,
  type UpdateEmployeeAccessState,
} from '../_actions';
import { Button } from '@/components/ui/button';

const initial: UpdateEmployeeAccessState = { ok: false };

export function EmployeeAccessForm({
  employeeId,
  disabled,
  disabledAt,
  isCurrentUser,
}: {
  employeeId: string;
  disabled: boolean;
  disabledAt: string | null;
  isCurrentUser: boolean;
}) {
  const [state, dispatch, isPending] = useActionState(updateEmployeeAccess, initial);
  const disabledDate = disabledAt ? new Date(disabledAt).toLocaleDateString() : null;

  return (
    <form
      action={dispatch}
      className="flex min-w-32 flex-col items-start gap-1"
      onSubmit={(event) => {
        if (!disabled && !window.confirm('Disable this employee account? They will no longer be able to sign in.')) {
          event.preventDefault();
        }
      }}
    >
      <input type="hidden" name="employeeId" value={employeeId} />
      <input type="hidden" name="action" value={disabled ? 'enable' : 'disable'} />
      <div className="flex items-center gap-2">
        <span
          className={
            disabled
              ? 'rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground'
              : 'rounded bg-green-50 px-1.5 py-0.5 text-[11px] text-green-700'
          }
        >
          {disabled ? 'disabled' : 'active'}
        </span>
        <Button
          type="submit"
          size="sm"
          disabled={isPending || (!disabled && isCurrentUser)}
          className={disabled ? '' : 'bg-muted text-foreground hover:bg-muted/80'}
        >
          {isPending ? 'Saving...' : disabled ? 'Re-enable' : 'Disable'}
        </Button>
      </div>
      {disabledDate && (
        <span className="text-[11px] text-muted-foreground">since {disabledDate}</span>
      )}
      {!disabled && isCurrentUser && (
        <span className="text-[11px] text-muted-foreground">current account</span>
      )}
      {state.ok && !isPending && (
        <span className="text-[11px] text-green-600">Saved.</span>
      )}
      {state.error && (
        <span className="text-[11px] text-red-600">{state.error}</span>
      )}
    </form>
  );
}
