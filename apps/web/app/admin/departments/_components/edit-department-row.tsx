'use client';

import { useActionState } from 'react';
import { updateDepartment, type UpdateDepartmentState } from '../_actions';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const initial: UpdateDepartmentState = { ok: false };

export interface EditDepartmentRowProps {
  id: string;
  displayLabel: string;
  description: string | null;
  headEmployeeId: string | null;
  memberCount: number;
  memberSummary: string;
  employees: { id: string; name: string; email: string }[];
}

export function EditDepartmentRow(props: EditDepartmentRowProps) {
  const [state, dispatch, isPending] = useActionState(updateDepartment, initial);

  return (
    <tr className="border-b last:border-0 align-top">
      <td className="py-3 pr-4">
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{props.id}</code>
      </td>
      <td className="py-3 pr-4">
        <form action={dispatch} className="space-y-2">
          <input type="hidden" name="id" value={props.id} />

          <Input
            name="displayLabel"
            defaultValue={props.displayLabel}
            className="h-8 text-sm"
            required
            aria-label="Display label"
          />

          <textarea
            name="description"
            defaultValue={props.description ?? ''}
            placeholder="Optional description"
            rows={2}
            className="flex w-full rounded-md border border-input bg-background px-3 py-1.5 text-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />

          <select
            name="headEmployeeId"
            defaultValue={props.headEmployeeId ?? 'none'}
            className="flex h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
            aria-label="Department head"
          >
            <option value="none">— no head assigned —</option>
            {props.employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name} ({e.email})
              </option>
            ))}
          </select>

          <div className="flex items-center gap-2">
            <Button type="submit" size="sm" disabled={isPending}>
              {isPending ? 'Saving…' : 'Save'}
            </Button>
            {state.ok && !isPending && (
              <span className="text-xs text-green-600">Saved.</span>
            )}
            {state.error && (
              <span className="text-xs text-red-600">{state.error}</span>
            )}
          </div>
        </form>
      </td>
      <td className="py-3 pr-4 text-xs">
        <div className="font-medium">{props.memberCount}</div>
        <div className="text-muted-foreground">{props.memberSummary || '—'}</div>
      </td>
    </tr>
  );
}
