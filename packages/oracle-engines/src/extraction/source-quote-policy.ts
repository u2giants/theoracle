import {
  MARKDOWN_DOCUMENT_NORMALIZATION_POLICY,
  PDF_OCR_NORMALIZATION_POLICY,
  STRICT_VERBATIM_POLICY,
  type NormalizationPolicy,
  type ValidateQuoteInput,
} from './types';

/**
 * Source classes that materially change deterministic quote validation.
 *
 * Keep this list semantic rather than provider-specific: both readers and
 * claim extraction must resolve through the same policy names.
 */
export type QuoteSourceKind =
  | 'native_text_document'
  | 'pdf_or_word_document'
  | 'vision_transcription'
  | 'transcript_message'
  | 'strict_source';

export type SourceQuotePolicyName =
  | 'markdown_document'
  | 'pdf_ocr_document'
  | 'vision_transcription_strict'
  | 'transcript_fuzzy'
  | 'strict_verbatim';

export type SourceQuotePolicy = {
  name: SourceQuotePolicyName;
  sourceKind: QuoteSourceKind;
  normalizationPolicy: NormalizationPolicy;
  allowFuzzy: boolean;
  fuzzyMinOverlap?: number;
};

export const VISION_TRANSCRIPTION_QUOTE_POLICY: SourceQuotePolicy = Object.freeze({
  name: 'vision_transcription_strict',
  sourceKind: 'vision_transcription',
  normalizationPolicy: STRICT_VERBATIM_POLICY,
  allowFuzzy: false,
});

export const TRANSCRIPT_FUZZY_QUOTE_POLICY: SourceQuotePolicy = Object.freeze({
  name: 'transcript_fuzzy',
  sourceKind: 'transcript_message',
  normalizationPolicy: PDF_OCR_NORMALIZATION_POLICY,
  allowFuzzy: true,
  fuzzyMinOverlap: 0.5,
});

const SOURCE_QUOTE_POLICIES: Record<QuoteSourceKind, SourceQuotePolicy> = {
  native_text_document: {
    name: 'markdown_document',
    sourceKind: 'native_text_document',
    normalizationPolicy: MARKDOWN_DOCUMENT_NORMALIZATION_POLICY,
    allowFuzzy: false,
  },
  pdf_or_word_document: {
    name: 'pdf_ocr_document',
    sourceKind: 'pdf_or_word_document',
    normalizationPolicy: PDF_OCR_NORMALIZATION_POLICY,
    allowFuzzy: false,
  },
  vision_transcription: VISION_TRANSCRIPTION_QUOTE_POLICY,
  transcript_message: TRANSCRIPT_FUZZY_QUOTE_POLICY,
  strict_source: {
    name: 'strict_verbatim',
    sourceKind: 'strict_source',
    normalizationPolicy: STRICT_VERBATIM_POLICY,
    allowFuzzy: false,
  },
};

export function resolveSourceQuotePolicy(sourceKind: QuoteSourceKind): SourceQuotePolicy {
  return SOURCE_QUOTE_POLICIES[sourceKind];
}

export function quoteValidationOptionsForSource(
  sourceKind: QuoteSourceKind,
): Pick<ValidateQuoteInput, 'normalizationPolicy' | 'allowFuzzy' | 'fuzzyMinOverlap'> {
  const policy = resolveSourceQuotePolicy(sourceKind);
  return {
    normalizationPolicy: policy.normalizationPolicy,
    allowFuzzy: policy.allowFuzzy,
    fuzzyMinOverlap: policy.fuzzyMinOverlap,
  };
}

export function quoteSourceKindForDocument(input: {
  fileType: string;
  fileName: string;
}): QuoteSourceKind {
  const fileType = input.fileType.toLowerCase();
  const extension = input.fileName.toLowerCase().split('.').pop() ?? '';
  if (
    fileType.startsWith('image/') ||
    ['png', 'jpg', 'jpeg', 'webp', 'heic', 'heif'].includes(extension)
  ) {
    return 'vision_transcription';
  }
  if (
    fileType === 'application/pdf' ||
    fileType.includes('wordprocessingml') ||
    fileType === 'application/msword' ||
    fileType.includes('spreadsheet') ||
    fileType === 'application/vnd.ms-excel' ||
    ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv'].includes(extension)
  ) {
    return 'pdf_or_word_document';
  }
  if (fileType.startsWith('text/') || ['txt', 'md', 'markdown', 'vtt'].includes(extension)) {
    return 'native_text_document';
  }
  return 'strict_source';
}

export function alternateSourceQuotePolicies(selected: SourceQuotePolicyName): SourceQuotePolicy[] {
  const policies = Object.values(SOURCE_QUOTE_POLICIES);
  return policies.filter(
    (policy, index) =>
      policy.name !== selected &&
      policies.findIndex((candidate) => candidate.name === policy.name) === index,
  );
}

/** @deprecated Prefer alternateSourceQuotePolicies for all source kinds. */
export const alternateDocumentQuotePolicies = alternateSourceQuotePolicies;
