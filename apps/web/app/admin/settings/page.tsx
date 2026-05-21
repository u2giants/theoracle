// Admin → Settings tab.
// Reads current settings from the DB server-side, passes to client components.

import { eq } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ModelPicker } from './_components/model-picker';

export default async function AdminSettingsPage() {
  const db = getDirectDb();

  const modelRow = await db
    .select()
    .from(settings)
    .where(eq(settings.key, 'default_interview_model'))
    .limit(1);

  // The value is stored as a jsonb string — unwrap it.
  const currentModel =
    typeof modelRow[0]?.value === 'string' ? modelRow[0].value : null;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Global Oracle configuration. Changes take effect on the next Oracle reply.
        </p>
      </header>

      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle className="text-base">Oracle model</CardTitle>
          <CardDescription>
            The OpenRouter model used for all Oracle chat replies. Only models
            available on your OpenRouter account are listed.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ModelPicker currentModel={currentModel} />
        </CardContent>
      </Card>
    </div>
  );
}
