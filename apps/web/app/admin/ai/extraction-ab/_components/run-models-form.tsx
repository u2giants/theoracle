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
  runStatus,
  lastRunError,
}: {
  reviewEventId: string;
  hasTest: boolean;
  runStatus?: string | null;
  lastRunError?: string | null;
}) {
  const [state, formAction, isPending] = useActionState(runExtractionAbTest, initialState);
  const isActive = runStatus === 'queued' || runStatus === 'running';
  const messageClass =
    state.status === 'error' || runStatus === 'failed'
      ? 'text-red-700'
      : state.status === 'success'
        ? 'text-green-700'
        : 'text-muted-foreground';
  const buttonText = isPending
    ? 'Queueing...'
    : runStatus === 'queued'
      ? 'Queued'
      : runStatus === 'running'
        ? 'Running...'
        : hasTest
          ? 'Re-run models'
          : 'Run Gemini 3.1 + Qwen';
  const statusMessage = isPending
    ? 'Queueing this row for the worker.'
    : isActive
      ? 'Worker is running this row. Results will refresh automatically.'
      : runStatus === 'failed' && lastRunError
        ? lastRunError
        : state.message;

  return (
    <form action={formAction} className="flex flex-col items-end gap-1">
      <input type="hidden" name="reviewEventId" value={reviewEventId} />
      <button
        type="submit"
        disabled={isPending || isActive}
        className="rounded bg-foreground px-3 py-1.5 text-xs text-background hover:bg-foreground/90 disabled:cursor-wait disabled:opacity-60"
      >
        {buttonText}
      </button>
      <p
        aria-live="polite"
        role={state.status === 'error' ? 'alert' : 'status'}
        className={`max-w-[18rem] text-right text-[11px] ${messageClass}`}
      >
        {statusMessage}
      </p>
    </form>
  );
}
