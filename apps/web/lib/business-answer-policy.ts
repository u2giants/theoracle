/** Citation integrity is a necessary boundary, not proof of semantic entailment. */
export function assertKnownBusinessCitations(text: string, includedClaimIds: readonly string[]): void {
  const allowed = new Set(includedClaimIds);
  for (const match of text.matchAll(/\[claim:([^\]\r\n]+)\]/g)) {
    if (!allowed.has(match[1]!)) {
      throw new Error('Business answer cited a claim outside the supplied approved evidence.');
    }
  }
}
