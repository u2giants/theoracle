// Teams "quote reply" parsing (plan_interview_conversation_rebuild.md Step 2).
//
// When an employee quote-replies to one of The Oracle's messages, Teams puts
// the quoted message's id into quote markup inside `activity.text` and/or a
// `text/html` attachment (`<blockquote itemtype="...Reply" itemid="171...">`,
// or `<quoted messageId="171..."/>`). The brain uses these ids to file the
// reply on the exact question that was quoted. Ids are untrusted: the brain
// only honours ids that belong to its own messages to this same employee.

export const MAX_QUOTED_IDS = 5;

export type ParsedQuote = { quotedIds: string[]; plainText: string };

type AttachmentLike = { contentType?: string | null; content?: unknown };

const ID_ATTR = /\b(?:messageId|itemid)\s*=\s*["']?([^"'\s/>]+)/gi;
const QUOTE_BLOCKS: RegExp[] = [
  /<blockquote\b[\s\S]*?<\/blockquote>/gi,
  /<quoted\b[^>]*\/>/gi,
  /<quoted\b[\s\S]*?<\/quoted>/gi,
];

function collectIds(source: string, into: string[]): void {
  for (const match of source.matchAll(ID_ATTR)) {
    const id = match[1] ?? '';
    if (!/^[0-9]{1,32}$/.test(id)) continue;
    if (!into.includes(id) && into.length < MAX_QUOTED_IDS) into.push(id);
  }
}

function stripTags(html: string): string {
  return html
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

export function parseQuote(text: string | null | undefined, attachments?: AttachmentLike[] | null): ParsedQuote {
  const quotedIds: string[] = [];
  const raw = text ?? '';
  collectIds(raw, quotedIds);
  for (const attachment of attachments ?? []) {
    if (attachment?.contentType !== 'text/html' || typeof attachment.content !== 'string') continue;
    collectIds(attachment.content, quotedIds);
  }
  let body = raw;
  for (const block of QUOTE_BLOCKS) body = body.replace(block, ' ');
  return { quotedIds, plainText: stripTags(body) };
}
