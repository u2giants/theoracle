import type { OracleModelRoute, RouteCandidate } from '@oracle/ai';

export const MAX_SAFE_INLINE_ATTACHMENT_BYTES = 14 * 1024 * 1024;

export type ChatAttachmentPart =
  | { type: 'image'; mimeType: string; data: string }
  | { type: 'file'; data: string; mimeType: string; fileName?: string }
  | { type: 'text'; text: string };

export interface MaterializedChatAttachment {
  fileType: string;
  fileName: string;
  buffer: Buffer;
}

export interface AttachmentSafeCandidateSelection {
  candidates: RouteCandidate[];
  constrainedToVertex: boolean;
}

export class ChatAttachmentSafetyError extends Error {
  readonly code:
    | 'unsupported_attachment'
    | 'attachment_download_failed'
    | 'attachment_route_incompatible'
    | 'attachments_too_large';

  constructor(
    code: ChatAttachmentSafetyError['code'],
    message: string,
  ) {
    super(message);
    this.name = 'ChatAttachmentSafetyError';
    this.code = code;
  }
}

export function toCanonicalAttachmentPart(
  attachment: MaterializedChatAttachment,
): ChatAttachmentPart {
  if (attachment.fileType.startsWith('image/')) {
    return {
      type: 'image',
      mimeType: attachment.fileType,
      data: attachment.buffer.toString('base64'),
    };
  }
  if (attachment.fileType === 'application/pdf') {
    return {
      type: 'file',
      mimeType: attachment.fileType,
      data: attachment.buffer.toString('base64'),
      fileName: attachment.fileName,
    };
  }
  if (attachment.fileType.startsWith('text/')) {
    return {
      type: 'text',
      text: `\n\n[File: ${attachment.fileName}]\n${attachment.buffer.toString('utf8')}\n[/File]`,
    };
  }
  throw new ChatAttachmentSafetyError(
    'unsupported_attachment',
    `The attached file "${attachment.fileName}" cannot be sent safely to the selected AI model. Remove it or upload a PDF, image, or text file.`,
  );
}

export function isAttachmentCapableRoute(route: OracleModelRoute): boolean {
  if (route.supportsVision) return true;
  return /claude|gpt-4o|gemini|llava|pixtral|qwen.*vl|minicpm/i.test(route.modelId);
}

/**
 * Keep only candidates that can receive binary attachments. When the complete
 * fallback payload is too large for the conservative cross-provider inline
 * budget, keep Vertex candidates only if one PDF is file-cached and the
 * remaining live attachments still fit. This turns an unsafe fallback into a
 * clear all-candidates failure instead of an answer that omitted a document.
 */
export function selectAttachmentSafeCandidates(input: {
  candidates: RouteCandidate[];
  hasBinaryAttachments: boolean;
  hasPdfAttachments: boolean;
  totalBinaryBytes: number;
  cachedPdfBytes?: number;
}): AttachmentSafeCandidateSelection {
  if (!input.hasBinaryAttachments) {
    return { candidates: input.candidates, constrainedToVertex: false };
  }
  if (input.candidates.length === 0) {
    throw new ChatAttachmentSafetyError(
      'attachment_route_incompatible',
      'No approved interview model is available to read this attachment.',
    );
  }

  const canReceiveEveryBinaryPart = (route: OracleModelRoute) =>
    isAttachmentCapableRoute(route) &&
    (!input.hasPdfAttachments ||
      route.provider === 'vertex' ||
      route.provider === 'google' ||
      route.provider === 'anthropic' ||
      route.provider === 'openai');

  if (!canReceiveEveryBinaryPart(input.candidates[0]!.route)) {
    throw new ChatAttachmentSafetyError(
      'attachment_route_incompatible',
      'The selected interview model cannot read this attachment. Choose an attachment-capable interview model and try again.',
    );
  }

  const capable = input.candidates.filter((candidate) =>
    canReceiveEveryBinaryPart(candidate.route),
  );
  if (capable.length === 0) {
    throw new ChatAttachmentSafetyError(
      'attachment_route_incompatible',
      'None of the approved interview models can read this attachment.',
    );
  }

  if (input.totalBinaryBytes <= MAX_SAFE_INLINE_ATTACHMENT_BYTES) {
    return { candidates: capable, constrainedToVertex: false };
  }

  const cachedPdfBytes = input.cachedPdfBytes ?? 0;
  const remainingLiveBytes = input.totalBinaryBytes - cachedPdfBytes;
  const vertexCandidates = capable.filter((candidate) => candidate.route.provider === 'vertex');
  if (
    cachedPdfBytes > 0 &&
    remainingLiveBytes <= MAX_SAFE_INLINE_ATTACHMENT_BYTES &&
    vertexCandidates.length > 0
  ) {
    return { candidates: vertexCandidates, constrainedToVertex: true };
  }

  throw new ChatAttachmentSafetyError(
    'attachments_too_large',
    'These attachments are too large to send safely without risking a missing document. Send fewer or smaller files and try again.',
  );
}
