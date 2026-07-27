import { desc } from 'drizzle-orm';
import { NextResponse } from 'next/server';
import { getDirectDb } from '@oracle/db/client';
import {
  businessModelChanges,
  businessObjects,
  businessObjectVersions,
  recommendations,
} from '@oracle/db/schema';
import { requireAdmin } from '@/lib/auth-guard';

export const dynamic = 'force-dynamic';

export interface AdminBusinessModelObject {
  id: string;
  objectKind: string;
  name: string;
  slug: string;
  status: string;
  currentVersionId: string | null;
  summary: string | null;
  updatedAt: Date;
}

export async function GET() {
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const db = getDirectDb();
  const [objects, versions, proposals, consultantRecommendations] = await Promise.all([
    db
      .select()
      .from(businessObjects)
      .orderBy(desc(businessObjects.updatedAt))
      .limit(100),
    db
      .select()
      .from(businessObjectVersions)
      .orderBy(desc(businessObjectVersions.createdAt))
      .limit(200),
    db
      .select()
      .from(businessModelChanges)
      .orderBy(desc(businessModelChanges.createdAt))
      .limit(200),
    db
      .select()
      .from(recommendations)
      .orderBy(desc(recommendations.createdAt))
      .limit(200),
  ]);

  return NextResponse.json({
    objects,
    versions,
    proposals,
    recommendations: consultantRecommendations,
    readOnly: true,
  });
}
