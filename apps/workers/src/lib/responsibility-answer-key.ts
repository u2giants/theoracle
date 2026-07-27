import { normalizeResponsibilityPart } from '@oracle/engines';

export type ResponsibilityAnswerKeyRecord = {
  role: string;
  action: string;
  object: string;
};

export function scoreResponsibilityAnswerKey(args: {
  expected: readonly ResponsibilityAnswerKeyRecord[];
  actual: readonly ResponsibilityAnswerKeyRecord[];
}): { matched: number; expected: number; recall: number; missing: ResponsibilityAnswerKeyRecord[] } {
  const actualKeys = new Set(
    args.actual.map((item) =>
      [item.role, item.action, item.object].map(normalizeResponsibilityPart).join('|'),
    ),
  );
  const missing = args.expected.filter(
    (item) =>
      !actualKeys.has(
        [item.role, item.action, item.object].map(normalizeResponsibilityPart).join('|'),
      ),
  );
  return {
    matched: args.expected.length - missing.length,
    expected: args.expected.length,
    recall: args.expected.length === 0 ? 1 : (args.expected.length - missing.length) / args.expected.length,
    missing,
  };
}
