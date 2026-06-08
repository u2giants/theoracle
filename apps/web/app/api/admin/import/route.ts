import { randomUUID } from 'node:crypto';
import { NextResponse, type NextRequest } from 'next/server';
import { eq } from 'drizzle-orm';
import { z } from 'zod';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { channelParticipants, channels, messages } from '@oracle/db/schema';

export const dynamic = 'force-dynamic';

const MAX_IMPORT_CHARS = 100_000;
const MAX_MESSAGE_CHARS = 9_000;
type OracleDb = ReturnType<typeof getDirectDb>;

const BodySchema = z.object({
  title: z.string().trim().min(1).max(120),
  sourceLabel: z.string().trim().max(200).optional(),
  content: z.string().trim().min(20).max(MAX_IMPORT_CHARS),
  channelId: z.uuid().optional(),
});

function splitIntoMessageSizedChunks(content: string): string[] {
  const normalized = content.replace(/\r\n/g, '\n').trim();
  if (normalized.length <= MAX_MESSAGE_CHARS) return [normalized];

  const chunks: string[] = [];
  let current = '';
  const paragraphs = normalized.split(/\n{2,}/);

  for (const paragraph of paragraphs) {
    const candidate = current ? `${current}\n\n${paragraph}` : paragraph;
    if (candidate.length <= MAX_MESSAGE_CHARS) {
      current = candidate;
      continue;
    }

    if (current) {
      chunks.push(current);
      current = '';
    }

    if (paragraph.length <= MAX_MESSAGE_CHARS) {
      current = paragraph;
      continue;
    }

    for (let start = 0; start < paragraph.length; start += MAX_MESSAGE_CHARS) {
      chunks.push(paragraph.slice(start, start + MAX_MESSAGE_CHARS));
    }
  }

  if (current) chunks.push(current);
  return chunks;
}

async function resolveImportChannel(db: OracleDb, args: {
  channelId?: string;
  title: string;
  employeeId: string;
}) {
  if (args.channelId) {
    const [channel] = await db
      .select({ id: channels.id, status: channels.status, isGroupChat: channels.isGroupChat })
      .from(channels)
      .where(eq(channels.id, args.channelId))
      .limit(1);

    if (!channel || channel.status !== 'active' || !channel.isGroupChat) {
      throw new Error('Target channel must be an active group channel.');
    }

    await db
      .insert(channelParticipants)
      .values({ channelId: channel.id, employeeId: args.employeeId })
      .onConflictDoNothing();
    return channel.id;
  }

  const safeTitle = args.title.replace(/\s+/g, ' ').trim();
  const [channel] = await db
    .insert(channels)
    .values({
      name: `Import: ${safeTitle}`,
      isGroupChat: true,
      status: 'active',
    })
    .returning({ id: channels.id });

  if (!channel) throw new Error('Failed to create import channel.');

  await db
    .insert(channelParticipants)
    .values({ channelId: channel.id, employeeId: args.employeeId })
    .onConflictDoNothing();

  return channel.id;
}

export async function POST(request: NextRequest) {
  let me;
  try {
    me = await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 });
  }

  let body: z.infer<typeof BodySchema>;
  try {
    body = BodySchema.parse(await request.json());
  } catch (err) {
    return NextResponse.json(
      { error: 'Invalid request body', detail: err instanceof Error ? err.message : 'validation failed' },
      { status: 400 },
    );
  }

  const db = getDirectDb();
  const importId = randomUUID();
  const chunks = splitIntoMessageSizedChunks(body.content);

  try {
    const result = await db.transaction(async (tx) => {
      const channelId = await resolveImportChannel(tx as ReturnType<typeof getDirectDb>, {
        channelId: body.channelId,
        title: body.title,
        employeeId: me.id,
      });

      const now = new Date().toISOString();
      const inserted = await tx
        .insert(messages)
        .values(
          chunks.map((chunk, index) => ({
            channelId,
            employeeId: me.id,
            role: 'user' as const,
            content: chunk,
            clientMessageId: `admin-import:${importId}:${index + 1}`,
            extractionStatus: 'pending' as const,
            metadataJson: {
              importId,
              importSource: 'admin_raw_import',
              title: body.title,
              sourceLabel: body.sourceLabel ?? null,
              part: index + 1,
              totalParts: chunks.length,
              importedByEmployeeId: me.id,
              importedAt: now,
            },
          })),
        )
        .returning({ id: messages.id });

      return { channelId, messageIds: inserted.map((row) => row.id) };
    });

    return NextResponse.json(
      {
        importId,
        channelId: result.channelId,
        messageIds: result.messageIds,
        messageCount: result.messageIds.length,
        status: 'pending_extraction',
      },
      { status: 201 },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Import failed';
    const status = message.includes('Target channel') ? 400 : 500;
    return NextResponse.json({ error: message }, { status });
  }
}
