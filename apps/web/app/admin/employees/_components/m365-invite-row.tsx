'use client';

import { useActionState } from 'react';
import { inviteFromM365, type InviteFromM365State } from '../_actions';
import { Button } from '@/components/ui/button';

const initial: InviteFromM365State = { ok: false };

export interface M365InviteRowProps {
  email: string;
  displayName: string;
  jobTitle: string | null;
}

export function M365InviteRow(props: M365InviteRowProps) {
  const [state, dispatch, isPending] = useActionState(inviteFromM365, initial);

  return (
    <tr className="border-b last:border-0">
      <td className="py-2 pr-4 font-medium">{props.displayName}</td>
      <td className="py-2 pr-4">{props.email}</td>
      <td className="py-2 pr-4 text-muted-foreground">{props.jobTitle ?? '—'}</td>
      <td className="py-2 pr-4">
        {state.ok ? (
          state.emailFailed ? (
            <span className="text-xs text-amber-600">
              Added (email failed — invite manually).
            </span>
          ) : (
            <span className="text-xs text-green-600">Invited.</span>
          )
        ) : (
          <form action={dispatch} className="flex items-center gap-2">
            <input type="hidden" name="email" value={props.email} />
            <input type="hidden" name="name" value={props.displayName} />
            <input type="hidden" name="jobTitle" value={props.jobTitle ?? ''} />
            <Button type="submit" size="sm" disabled={isPending}>
              {isPending ? 'Inviting…' : 'Invite'}
            </Button>
            {state.error && (
              <span className="text-xs text-red-600">{state.error}</span>
            )}
          </form>
        )}
      </td>
    </tr>
  );
}
