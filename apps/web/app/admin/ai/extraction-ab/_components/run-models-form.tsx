'use client';

import { useActionState } from 'react';
import {
  runExtractionAbTest,
  type ExtractionAbActionState,
} from '../_actions';

const initialState: ExtractionAbActionState = {
  status: 'idle',
  message: '',
};

export function RunModelsForm({
  reviewEventId,
  hasTest,
}: {
  reviewEventId: string;
  hasTest: boolean;
}) {
  const [state, formAction, isPending] = useActionState(runExtractionAbTest, initialState);
  const messageClass =
    state.status === 'error'
      ? 'text-red-700'
      : state.status === 'success'
        ? 'text-green-700'
        : 'text-muted-foreground';

  return (
    <form action={formAction} className="flex flex-col items-end gap-1">
      <input type="hidden" name="reviewEventId" value={reviewEventId} />
      <button
        type="submit"
        disabled={isPending}
        className="rounded bg-foreground px-3 py-1.5 text-xs text-background hover:bg-foreground/90 disabled:cursor-wait disabled:opacity-60"
      >
        {isPending ? 'Running models...' : hasTest ? 'Re-run models' : 'Run Gemini 3.1 + Qwen'}
      </button>
      <p
        aria-live="polite"
        role={state.status === 'error' ? 'alert' : 'status'}
        className={`max-w-[18rem] text-right text-[11px] ${messageClass}`}
      >
        {isPending ? 'Running Gemini and Qwen. This can take a few seconds.' : state.message}
      </p>
    </form>
  );
}
