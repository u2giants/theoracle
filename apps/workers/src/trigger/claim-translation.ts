// Bilingual claim layer (china_imp.md) — claim-translation worker.
//
// Generates display-only translations of an APPROVED claim's summary into every
// supported language other than its source language, and embeds each rendering
// so locale-aware retrieval (packages/ai/src/retrieval.ts) can match a
// same-language query against a same-language embedding.
//
// Triggered by the admin claim-approval action (apps/web/app/admin/claims/_actions.ts)
// and safe to re-run: idempotent on (claim_id, lang) via source_hash. When the
// canonical summary changes, source_hash no longer matches and the row is
// re-translated + re-embedded.
//
// Invariants (china_imp.md):
//   - Canonical claim (claims.summary, in claims.source_lang) is authoritative.
//   - These rows are display-only — never used for quote validation, candidate
//     hashing, or promotion.
//   - All inference goes through OracleAIClient (never a provider SDK directly).

import { task } from '@trigger.dev/sdk/v3';
import { and, eq } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import { z } from 'zod';
import { getDirectDb } from '@oracle/db/client';
import { claims, claimTranslations } from '@oracle/db';
import {
  OracleAIClient,
  buildStandardAdapters,
  embedText,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type RouteCandidate,
} from '@oracle/ai';
import {
  SUPPORTED_LOCALES,
  coerceLocale,
  type SupportedLocale,
} from '@oracle/shared';

const TRANSLATION_PROMPT_VERSION = 'claim-translation-v1';

const LANGUAGE_LABELS: Record<SupportedLocale, string> = {
  en: 'English',
  'zh-CN': 'Simplified Chinese (简体中文)',
};

const payloadSchema = z.object({
  claimId: z.string().uuid(),
});

function sha256(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function buildOracleClient(): OracleAIClient {
  return new OracleAIClient({
    adapters: buildStandardAdapters(),
  });
}

async function resolveTranslationCandidates(
  db: ReturnType<typeof getDirectDb>,
): Promise<RouteCandidate[]> {
  // Admin-selected translation model (Admin → Settings → "Translation model").
  const resolved = await resolveRouteCandidates(db, 'translation');
  for (const skipped of resolved.skipped) {
    console.warn('[claim-translation] skipped translation route candidate', skipped);
  }
  return resolved.candidates;
}

function buildSystemPrompt(targetLabel: string): string {
  return `You are a professional translator for The Oracle, an enterprise knowledge base for POP Creations / Spruce Line.

Translate the business "claim" the user provides into ${targetLabel}.

RULES:
1. Output ONLY the translated text — no preamble, no quotes, no explanation.
2. Preserve the exact meaning. Do not add, omit, soften, or editorialize.
3. Keep proper nouns, product names, system names, and codes as-is unless a well-established ${targetLabel} form exists.
4. Match the register: a concise, factual operational statement.`;
}

/**
 * Translate one approved claim's summary into every supported language other
 * than its source language. Skips languages already up to date (source_hash
 * matches the current summary).
 */
async function translateClaim(claimId: string): Promise<{
  claimId: string;
  status: 'translated' | 'skipped_not_found' | 'skipped_not_approved';
  langs: string[];
}> {
  const db = getDirectDb();

  const [claim] = await db
    .select({
      id: claims.id,
      summary: claims.summary,
      sourceLang: claims.sourceLang,
      status: claims.status,
    })
    .from(claims)
    .where(eq(claims.id, claimId))
    .limit(1);

  if (!claim) return { claimId, status: 'skipped_not_found', langs: [] };
  // Only approved claims are surfaced to readers, so only they need rendering.
  if (claim.status !== 'approved') {
    return { claimId, status: 'skipped_not_approved', langs: [] };
  }

  const sourceLang = coerceLocale(claim.sourceLang);
  const sourceHash = sha256(claim.summary);
  const targets = SUPPORTED_LOCALES.filter((l) => l !== sourceLang);

  const client = buildOracleClient();
  const routeCandidates = await resolveTranslationCandidates(db);
  const route = routeCandidates[0]!.route;
  const translatedLangs: string[] = [];

  for (const lang of targets) {
    const [existing] = await db
      .select({ sourceHash: claimTranslations.sourceHash })
      .from(claimTranslations)
      .where(and(eq(claimTranslations.claimId, claimId), eq(claimTranslations.lang, lang)))
      .limit(1);
    if (existing && existing.sourceHash === sourceHash) {
      continue; // already up to date
    }

    const targetLabel = LANGUAGE_LABELS[lang];
    const blocks = [
      makeBlock({
        id: 'translation-system',
        label: 'Translation system prompt',
        kind: 'stable_system',
        content: buildSystemPrompt(targetLabel),
        reasonIncluded: 'Translation instructions',
      }),
      makeBlock({
        id: 'translation-input',
        label: 'Source claim',
        kind: 'dynamic_input',
        content: `Translate this claim into ${targetLabel}:\n\n${claim.summary}`,
        reasonIncluded: 'Source text to translate',
      }),
    ];

    const result = await client
      .runText({
        taskType: 'claim_translation',
        routeId: route.routeId,
        promptVersion: TRANSLATION_PROMPT_VERSION,
        blocks,
        routeCandidates,
      })
      .catch(async (err) => {
        await logAllCandidatesFailedAttempts({
          db,
          error: err,
          taskType: 'claim-translation',
          slot: 'translation',
        }).catch((logErr) =>
          console.error('[claim-translation] failed to record failed model attempts', logErr),
        );
        throw err;
      });
    await logModelRunAttempts({
      db,
      metadata: result,
      taskType: 'claim-translation',
      slot: 'translation',
    }).catch((logErr) =>
      console.error('[claim-translation] failed to record model attempts', logErr),
    );

    const translated = result.text.trim();
    if (!translated) {
      throw new Error(`[claim-translation] empty translation for claim ${claimId} → ${lang}`);
    }

    const { vector } = await embedText(translated);

    await db
      .insert(claimTranslations)
      .values({
        claimId,
        lang,
        summary: translated,
        embedding: vector,
        sourceHash,
      })
      .onConflictDoUpdate({
        target: [claimTranslations.claimId, claimTranslations.lang],
        set: {
          summary: translated,
          embedding: vector,
          sourceHash,
          updatedAt: new Date(),
        },
      });

    translatedLangs.push(lang);
  }

  return { claimId, status: 'translated', langs: translatedLangs };
}

export const claimTranslationTask = task({
  id: 'claim-translation',
  run: async (rawPayload: unknown) => {
    const { claimId } = payloadSchema.parse(rawPayload);
    return translateClaim(claimId);
  },
});
