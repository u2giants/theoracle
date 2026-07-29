import {
  formatConversationSegment,
  type FormattedMessage,
} from '@oracle/ai';

export interface ConversationWindow {
  segment: FormattedMessage[];
  carryIn: FormattedMessage[];
  formattedCharCount: number;
}

export class ConversationMessageTooLargeError extends Error {
  constructor(messageId: string, requiredChars: number, maxChars: number) {
    super(
      `[conversation-windowing] message ${messageId} cannot fit in an empty extraction window ` +
        `(${requiredChars} formatted characters required; budget ${maxChars}). ` +
        `The message was not truncated. Increase extraction_char_budget or choose an extraction ` +
        `route with a larger verified context window.`,
    );
    this.name = 'ConversationMessageTooLargeError';
  }
}

function formattedLength(segment: FormattedMessage[], carryIn: FormattedMessage[]): number {
  return formatConversationSegment(segment, { carryIn }).length;
}

function carryInThatFits(
  segment: FormattedMessage[],
  carryIn: FormattedMessage[],
  maxChars: number,
): FormattedMessage[] {
  let kept = carryIn;
  while (kept.length > 0 && formattedLength(segment, kept) > maxChars) {
    kept = kept.slice(1);
  }
  return kept;
}

/**
 * Split one chronological conversation only at message boundaries.
 *
 * The last `overlapCount` active messages are repeated as quotable messages in
 * the next window. Their original IDs and timestamps are never rewritten, so
 * the normal candidate hash deduplicates repeated evidence. Earlier carry-in
 * remains explicitly non-quotable through formatConversationSegment().
 */
export function buildConversationWindows(args: {
  segment: FormattedMessage[];
  carryIn?: FormattedMessage[];
  maxChars: number;
  overlapCount: number;
}): ConversationWindow[] {
  const { segment, maxChars } = args;
  if (!Number.isInteger(maxChars) || maxChars <= 0) {
    throw new Error('[conversation-windowing] maxChars must be a positive integer');
  }
  if (!Number.isInteger(args.overlapCount) || args.overlapCount < 0) {
    throw new Error('[conversation-windowing] overlapCount must be a non-negative integer');
  }
  if (segment.length === 0) return [];

  const windows: ConversationWindow[] = [];
  let start = 0;
  while (start < segment.length) {
    let end = start;
    const firstMessage = segment.slice(start, start + 1);
    const fittedCarryIn = carryInThatFits(firstMessage, args.carryIn ?? [], maxChars);

    while (end < segment.length) {
      const proposed = segment.slice(start, end + 1);
      if (formattedLength(proposed, fittedCarryIn) > maxChars) break;
      end += 1;
    }

    if (end === start) {
      const one = segment.slice(start, start + 1);
      throw new ConversationMessageTooLargeError(
        one[0]!.id,
        formattedLength(one, []),
        maxChars,
      );
    }

    const windowSegment = segment.slice(start, end);
    windows.push({
      segment: windowSegment,
      carryIn: fittedCarryIn,
      formattedCharCount: formattedLength(windowSegment, fittedCarryIn),
    });
    if (end === segment.length) break;

    const usableOverlap = Math.min(args.overlapCount, windowSegment.length - 1);
    start = end - usableOverlap;
  }
  return windows;
}

export function contextBoundedConversationChars(args: {
  configuredCharBudget: number;
  contextLengths: number[];
  usableContextRatio: number;
}): number {
  if (args.contextLengths.length === 0 || args.contextLengths.some((n) => !Number.isFinite(n) || n <= 0)) {
    throw new Error(
      '[conversation-windowing] every configured extraction route needs a verified positive context length; windowing will not guess or silently fall back',
    );
  }
  if (!Number.isFinite(args.usableContextRatio) || args.usableContextRatio <= 0 || args.usableContextRatio >= 1) {
    throw new Error('[conversation-windowing] usable context ratio must be greater than 0 and less than 1');
  }
  const smallestContextTokens = Math.min(...args.contextLengths);
  // Three characters per token is deliberately conservative for IDs, JSON,
  // multilingual text, and prompt labels. The remaining context is reserved
  // for the stable prompt, schema, provider framing, and model output.
  const modelBoundChars = Math.floor(smallestContextTokens * 3 * args.usableContextRatio);
  return Math.min(args.configuredCharBudget, modelBoundChars);
}
