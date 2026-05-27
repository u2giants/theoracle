'use client';

import { useActionState } from 'react';
import { addEmployee, type AddEmployeeState } from '../_actions';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const initial: AddEmployeeState = { ok: false };

export function AddEmployeeForm() {
  const [state, dispatch, isPending] = useActionState(addEmployee, initial);

  return (
    <form action={dispatch} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label htmlFor="ae-name" className="text-sm font-medium">Name</label>
          <Input id="ae-name" name="name" placeholder="Jane Smith" required />
        </div>
        <div className="space-y-1">
          <label htmlFor="ae-email" className="text-sm font-medium">Email</label>
          <Input id="ae-email" name="email" type="email" placeholder="jane@company.com" required />
        </div>
        <div className="space-y-1">
          <label htmlFor="ae-role" className="text-sm font-medium">Role / title</label>
          <Input id="ae-role" name="role" placeholder="Production Coordinator" required />
        </div>
        <div className="space-y-1">
          <label htmlFor="ae-departments" className="text-sm font-medium">
            Department(s)
          </label>
          <Input
            id="ae-departments"
            name="departments"
            placeholder="e.g. Creative, Production"
            required
          />
          <p className="text-[11px] text-muted-foreground">
            Comma-separated. Used as a soft hint when the Oracle retrieves
            relevant knowledge for this employee&apos;s questions.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          id="ae-isAdmin"
          name="isAdmin"
          type="checkbox"
          value="true"
          className="h-4 w-4"
        />
        <label htmlFor="ae-isAdmin" className="text-sm font-medium cursor-pointer">
          Grant admin access
        </label>
      </div>

      {state.error && (
        <p className="text-sm text-red-600">{state.error}</p>
      )}
      {state.ok && (
        <p className="text-sm text-green-600">Employee added. They can now sign in.</p>
      )}

      <Button type="submit" disabled={isPending} size="sm">
        {isPending ? 'Adding…' : 'Add employee'}
      </Button>
    </form>
  );
}
