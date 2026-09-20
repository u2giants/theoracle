/** Citation integrity is a necessary boundary, not proof of semantic entailment. */
export function assertKnownBusinessCitations(
  text: string,
  includedClaimIds: readonly string[],
  options: { requireAtLeastOne?: boolean } = {},
): void {
  const allowed = new Set(includedClaimIds);
  let citationCount = 0;
  for (const match of text.matchAll(/\[claim:([^\]\r\n]+)\]/g)) {
    citationCount += 1;
    if (!allowed.has(match[1]!)) {
      throw new Error('Business answer cited a claim outside the supplied approved evidence.');
    }
  }
  if (options.requireAtLeastOne && allowed.size > 0 && citationCount === 0) {
    throw new Error('Business answer used approved evidence without citing any supplied claim.');
  }
}
