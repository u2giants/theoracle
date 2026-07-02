'use server';

import { revalidatePath } from 'next/cache';
import { z } from 'zod';
import { getDirectDb } from '@oracle/db/client';
import { documents } from '@oracle/db/schema';
import { eq } from 'drizzle-orm';
import { triggerTask } from '@/lib/trigger';

const generateOutlineSchema = z.object({
  documentId: z.string().uuid(),
  force: z.coerce.boolean().optional(),
});

export async function generateSourceOutline(formData: FormData) {
  const parsed = generateOutlineSchema.parse({
    documentId: formData.get('documentId'),
    force: formData.get('force') === 'true',
  });

  const db = getDirectDb();
  const [doc] = await db
    .select({ id: documents.id })
    .from(documents)
    .where(eq(documents.id, parsed.documentId))
    .limit(1);
  if (!doc) {
    throw new Error('Document not found.');
  }

  const dispatched = await triggerTask('source-outline', parsed);
  if (!dispatched) {
    throw new Error('Could not dispatch source outline generation.');
  }

  revalidatePath('/admin/documents');
}
