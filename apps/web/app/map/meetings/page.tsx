import { requireAdmin } from '@/lib/auth-guard';
import { MeetingsClient } from './_components/meetings-client';

export const dynamic = 'force-dynamic';

export default async function MapMeetingsPage() {
  await requireAdmin();
  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Meeting transcripts</h1>
        <p className="text-sm text-muted-foreground">
          Every Teams meeting and call transcript in the company, collected hourly, with a
          one-paragraph summary. Nothing here is added to the Company Map.
        </p>
      </div>
      <MeetingsClient />
    </main>
  );
}
