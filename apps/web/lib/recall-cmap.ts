// Company Map capture of finished Recall.ai meeting transcripts (plan step 12).
// When Recall reports a transcript or bot as done, download the final
// transcript JSON and hand it to the brain as a `transcript` source. The
// brain's transcript reader already understands Recall's JSON shape.

import { recallApiKey, recallBaseUrl } from '@/lib/recall';
import { brainService } from '@/lib/brain-service';

type RecallEvent = {
  event?: string;
  data?: {
    transcript?: { id?: string };
    bot?: { id?: string };
  };
};

async function recallGet(path: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${recallBaseUrl()}${path}`, {
    headers: { Authorization: recallApiKey(), accept: 'application/json' },
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) throw new Error(`Recall ${path} failed (${res.status})`);
  return (await res.json()) as Record<string, unknown>;
}

function downloadUrlFromBot(bot: Record<string, unknown>): string | null {
  const recordings = Array.isArray(bot.recordings) ? bot.recordings : [];
  for (const rec of recordings as Record<string, unknown>[]) {
    const shortcuts = rec.media_shortcuts as Record<string, unknown> | undefined;
    const transcript = shortcuts?.transcript as { data?: { download_url?: string } } | undefined;
    if (transcript?.data?.download_url) return transcript.data.download_url;
  }
  return null;
}

// Returns the transcript id or bot id the event refers to, or null when the
// event is not a "finished" event this capture cares about.
export function finishedTranscriptRef(event: unknown): { transcriptId?: string; botId?: string } | null {
  const e = event as RecallEvent;
  if (e?.event === 'transcript.done' && e.data?.transcript?.id) {
    return { transcriptId: e.data.transcript.id };
  }
  if (e?.event === 'bot.done' && e.data?.bot?.id) {
    return { botId: e.data.bot.id };
  }
  return null;
}

export async function recordFinishedTranscript(event: unknown): Promise<boolean> {
  const ref = finishedTranscriptRef(event);
  if (!ref) return false;
  let downloadUrl: string | null = null;
  let title = 'Teams meeting transcript';
  if (ref.transcriptId) {
    const t = await recallGet(`/api/v1/transcript/${encodeURIComponent(ref.transcriptId)}/`);
    downloadUrl = (t.data as { download_url?: string } | undefined)?.download_url ?? null;
    const created = typeof t.created_at === 'string' ? t.created_at : null;
    if (created) title = `Teams meeting transcript — ${created.slice(0, 10)}`;
  } else if (ref.botId) {
    const bot = await recallGet(`/api/v1/bot/${encodeURIComponent(ref.botId)}/`);
    downloadUrl = downloadUrlFromBot(bot);
    const joinAt = typeof bot.join_at === 'string' ? bot.join_at : null;
    if (joinAt) title = `Teams meeting transcript — ${joinAt.slice(0, 10)}`;
  }
  if (!downloadUrl) return false;
  const res = await fetch(downloadUrl, { signal: AbortSignal.timeout(60_000) });
  if (!res.ok) throw new Error(`Recall transcript download failed (${res.status})`);
  const text = await res.text();
  if (!text.trim() || text.trim() === '[]') return false;
  const posted = await brainService('sources/transcript', {
    method: 'POST',
    body: { text, title },
  });
  if (posted.status >= 300) throw new Error(`brain transcript intake failed (${posted.status})`);
  return true;
}
