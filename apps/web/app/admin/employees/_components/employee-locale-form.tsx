'use client';

import { useActionState } from 'react';
import { updateEmployeeLocale, type UpdateEmployeeLocaleState } from '../_actions';
import { SUPPORTED_LOCALES, type SupportedLocale } from '@oracle/shared';

const initial: UpdateEmployeeLocaleState = { ok: false };

/** Friendly labels for the locale dropdown. Keyed by SupportedLocale so adding
 *  a new locale to SUPPORTED_LOCALES surfaces a type error here until labeled. */
const LOCALE_LABELS: Record<SupportedLocale, string> = {
  en: 'English',
  'zh-CN': '中文 (Chinese)',
};

/**
 * Inline language selector for one employee. Submits on change. Setting a user
 * to 中文 (zh-CN) puts them in the "China group": they read the Oracle in
 * Chinese and any claim-review question routed to them is auto-translated.
 */
export function EmployeeLocaleForm({
  employeeId,
  currentLocale,
}: {
  employeeId: string;
  currentLocale: SupportedLocale;
}) {
  const [state, dispatch, isPending] = useActionState(updateEmployeeLocale, initial);

  return (
    <form action={dispatch} className="flex flex-col items-start gap-1">
      <input type="hidden" name="employeeId" value={employeeId} />
      <select
        name="locale"
        defaultValue={currentLocale}
        disabled={isPending}
        onChange={(event) => event.currentTarget.form?.requestSubmit()}
        className="rounded border bg-background px-1.5 py-0.5 text-xs text-foreground disabled:opacity-60"
      >
        {SUPPORTED_LOCALES.map((loc) => (
          <option key={loc} value={loc}>
            {LOCALE_LABELS[loc]}
          </option>
        ))}
      </select>
      {isPending && <span className="text-[11px] text-muted-foreground">Saving…</span>}
      {state.ok && !isPending && <span className="text-[11px] text-green-600">Saved.</span>}
      {state.error && <span className="text-[11px] text-red-600">{state.error}</span>}
    </form>
  );
}
