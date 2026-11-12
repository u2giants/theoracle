// Client-side reads of the brain through the /api/brain proxy (plan step 10).
// The proxy adds the shared token and the logged-in user; pages never see it.

export type Stance = 'policy' | 'practice' | 'report' | 'inference';

export type Translations = Record<string, Record<string, string>>;

/** Prefer the viewer-language field from the sidecar; else the canonical text. */
export function pickText(
  translations: Translations | undefined,
  lang: string,
  field: string,
  fallback: string,
): string {
  if (lang === 'zh-CN') {
    const zh = translations?.['zh-CN']?.[field];
    if (zh) return zh;
  }
  return fallback;
}

export type SourceRef = { id: string; title: string };

export type FunctionAssignment = {
  function_id: string;
  key: string;
  name: string;
  weight: number;
  origin: 'auto' | 'admin';
};

export type FunctionRow = {
  id: string;
  key: string;
  name: string;
  description: string;
  aliases: string[];
  parent_id: string | null;
  sort: number;
  active: boolean;
};

export type Finding = {
  text: string;
  kind: string;
  stance: Stance | string;
  source_ids: string[];
  sources: SourceRef[];
};

export type CommunityCard = {
  id: string;
  level: number;
  parent_id: string | null;
  title: string;
  summary: string;
  finding_count: number;
  entity_count: number;
  translations?: Translations;
};

export type GraphNode = {
  id: string;
  type: string;
  name: string;
  mention_count: number;
  source_count: number;
};

export type GraphEdge = {
  source: string;
  target: string;
  rel_type: string;
  weight: number;
};

export type GraphPayload = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
  truncated: boolean;
  notice: string | null;
};

export type CommunityDetail = {
  id: string;
  level: number;
  parent_id: string | null;
  title: string;
  summary: string;
  report_md: string;
  findings: Finding[];
  graph: GraphPayload;
  children: { id: string; title: string }[];
  translations?: Translations;
};

export type Quote = {
  quote: string;
  chunk_id: string;
  source_id: string;
  source_title: string;
  stance?: string;
  description?: string;
};

export type ReviewFlag = {
  id: string;
  item_type: 'entity' | 'relation' | 'community';
  item_id: string;
  label: string;
  note: string | null;
  created_by: string | null;
  created_at: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  action: string | null;
};

export type EntityDetail = {
  id: string;
  type: string;
  canonical_name: string;
  description: string;
  mention_count: number;
  source_count: number;
  aliases: string[];
  sources: { id: string; title: string; kind: string; mentions: number }[];
  mentions: Quote[];
  neighbours: Record<
    string,
    { entity_id: string; name: string; type: string; direction: 'in' | 'out'; quotes: Quote[] }[]
  >;
  functions: FunctionAssignment[];
  translations?: Translations;
};

export type SourceChunks = {
  source: {
    id: string;
    kind: string;
    title: string;
    original_filename: string | null;
    bytes: number;
    department_hint: string | null;
    effective_date: string | null;
    created_at: string | null;
    read_state: string;
    read_notes?: {
      unreadable_regions?: { locator: Record<string, unknown> | null; note: string }[];
    } | null;
  };
  chunks: {
    id: string;
    ordinal: number;
    locator: Record<string, unknown> | null;
    text: string;
    passage_kind: string | null;
  }[];
  functions: FunctionAssignment[];
};

export async function brainGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api/brain/${path.replace(/^\/+/, '')}`, {
    cache: 'no-store',
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? body.error ?? `request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export async function brainPost<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`/api/brain/${path.replace(/^\/+/, '')}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload ?? {}),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? body.error ?? `request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export async function brainPut<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`/api/brain/${path.replace(/^\/+/, '')}`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload ?? {}),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? body.error ?? `request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function sourceHref(sourceId: string, chunkId?: string | null): string {
  const base = `/map/source/${encodeURIComponent(sourceId)}`;
  return chunkId ? `${base}?chunk=${encodeURIComponent(chunkId)}` : base;
}

export function describeLocator(locator: Record<string, unknown> | null | undefined): string {
  if (!locator) return '';
  const parts: string[] = [];
  if (locator.page !== undefined) parts.push(`page ${String(locator.page)}`);
  if (locator.sheet !== undefined) parts.push(`sheet ${String(locator.sheet)}`);
  if (locator.range !== undefined) parts.push(String(locator.range));
  if (locator.slide !== undefined) parts.push(`slide ${String(locator.slide)}`);
  if (locator.turn !== undefined) parts.push(`turn ${String(locator.turn)}`);
  if (locator.speaker !== undefined) parts.push(String(locator.speaker));
  if (locator.t0 !== undefined) parts.push(String(locator.t0));
  if (locator.image) parts.push('image');
  return parts.join(' · ');
}
