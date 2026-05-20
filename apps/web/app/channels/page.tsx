// Channels index — when no channel is selected.
import { requireEmployee } from '@/lib/auth-guard';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export const dynamic = 'force-dynamic';

export default async function ChannelsIndexPage() {
  const me = await requireEmployee();
  return (
    <div className="flex h-screen items-center justify-center p-6">
      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>Welcome, {me.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>Pick a channel on the left to start chatting.</p>
          <p className="text-muted-foreground">
            Mention <code>@oracle</code> in any message to ask the Oracle for help. The
            Oracle will only respond when directly addressed (Phase 3); proactive lull and
            contradiction interjections arrive in Phase 6.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
