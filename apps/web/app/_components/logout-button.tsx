import { Button } from '@/components/ui/button';

// Renders a form posting to /auth/signout. Using a form (not a fetch from a
// client component) keeps the redirect server-driven and works even with
// JS disabled.
export function LogoutButton({
  className,
  variant = 'ghost',
}: {
  className?: string;
  variant?: 'ghost' | 'outline' | 'default';
}) {
  return (
    <form action="/auth/signout" method="post" className={className}>
      <Button type="submit" variant={variant} size="sm">
        Sign out
      </Button>
    </form>
  );
}
