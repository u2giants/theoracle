import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const REASONS: Record<string, string> = {
  not_approved: 'Your account is not approved for Oracle.',
  disabled: 'Your Oracle access has been disabled.',
  hijack_attempt:
    'A different Oracle identity is already linked to this email. Contact an administrator.',
  no_code: 'Sign-in link was malformed.',
  no_user: 'We could not verify your identity. Please try again.',
  unverified_email: 'Your email is not verified by your identity provider.',
  exchange_failed: 'Sign-in link is invalid or expired.',
  default: 'Your account is not approved for Oracle.',
};

export default async function DeniedPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string }>;
}) {
  const { reason } = await searchParams;
  const message = REASONS[reason ?? 'default'] ?? REASONS.default;

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Access Denied</CardTitle>
        </CardHeader>
        <CardContent>
          <p>{message}</p>
          <p className="mt-4 text-sm text-muted-foreground">
            If you believe this is an error, ask Albert to add your email to the
            employees roster.
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
