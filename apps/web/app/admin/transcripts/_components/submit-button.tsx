'use client';

import { useFormStatus } from 'react-dom';

// Submit button that reflects its parent <form>'s pending state.
//
// useFormStatus() only reports the pending state of the form this component is
// rendered INSIDE, so this must live under a <form action={...}> — not be the
// form itself. While the server action is in flight the button is disabled and
// swaps its label to `pendingLabel`. `children` is the idle label; `className`
// passes through so each call site keeps its existing button styles.
export function SubmitButton({
  children,
  pendingLabel,
  className,
  title,
}: {
  children: React.ReactNode;
  pendingLabel: React.ReactNode;
  className?: string;
  title?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      aria-busy={pending}
      className={`${className ?? ''} disabled:cursor-not-allowed disabled:opacity-60`}
      title={title}
    >
      {pending ? pendingLabel : children}
    </button>
  );
}
