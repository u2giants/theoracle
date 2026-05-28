'use client';

import { useActionState } from 'react';
import { addEmployee, type AddEmployeeState } from '../_actions';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const initial: AddEmployeeState = { ok: false };

export interface AddEmployeeFormProps {
  departmentOptions: { id: string; displayLabel: string }[];
}

export function AddEmployeeForm({ departmentOptions }: AddEmployeeFormProps) {
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
      </div>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Department(s)</legend>
        <div className="grid grid-cols-3 gap-y-1 gap-x-4">
          {departmentOptions.map((d) => (
            <label key={d.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="departmentIds"
                value={d.id}
                className="h-4 w-4"
              />
              {d.displayLabel}
            </label>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">
          Pick one or more. Used to route clarification requests and as a soft
          retrieval hint.
        </p>
      </fieldset>

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
