import type { RetrievalPlan } from '@oracle/ai';
import {
  buildBusinessAnswerContext,
  type BusinessAnswerClaim,
  type BusinessAnswerRelationship,
} from './business-answer-context';

/** Uses the same approved-claim search for every pass; never queries raw sources. */
export async function retrieveBusinessAnswerContext(args: {
  plan: RetrievalPlan;
  search: (plan: RetrievalPlan) => Promise<BusinessAnswerClaim[]>;
  getRelationships: (claimIds: string[]) => Promise<BusinessAnswerRelationship[]>;
  getEligibleSupports: (claimIds: string[]) => Promise<Array<{ id: string; summary: string; claimKind: string | null }>>;
  maxAdditionalDomainSearches?: number;
  maxCharacters?: number;
}) {
  const maxAdditional = args.maxAdditionalDomainSearches ?? 2;
  if (!Number.isInteger(maxAdditional) || maxAdditional < 0 || maxAdditional > 6) {
    throw new Error('Business answer domain-search budget must be an integer from 0 to 6.');
  }
  const domains = [...new Set(args.plan.topDomainHints)]
    .filter((domain) => !args.plan.excludedTopDomains?.includes(domain));
  // A cross-functional search can otherwise spend all eight results on one domain.
  // These passes preserve every approval, entity, time, and privacy filter in search.
  const additionalDomains = domains.length > 1 ? domains.slice(0, maxAdditional) : [];
  const plans = [args.plan, ...additionalDomains.map((domain): RetrievalPlan => ({
    ...args.plan,
    topDomainHints: [domain],
    searchScope: 'domain_filtered',
  }))];
  const results = await Promise.all(plans.map((plan) => args.search(plan)));
  // Round-robin retains each department's highest-ranked evidence before lower ranks.
  const claimsById = new Map<string, BusinessAnswerClaim>();
  for (let rank = 0; rank < Math.max(0, ...results.map((result) => result.length)); rank++) {
    for (const result of results) {
      const claim = result[rank];
      if (claim && !claimsById.has(claim.id)) claimsById.set(claim.id, claim);
    }
  }
  const claims = [...claimsById.values()];
  const relationships = claims.length ? await args.getRelationships(claims.map((claim) => claim.id)) : [];
  const supportIds = [...new Set(relationships.flatMap((r) => r.supportClaims.map((c) => c.id)))];
  const eligible = new Map((supportIds.length ? await args.getEligibleSupports(supportIds) : []).map((c) => [c.id, c]));
  const eligibleRelationships = relationships
    .filter((r) => r.supportClaims.length > 0 && r.supportClaims.every((c) => eligible.has(c.id)))
    .map((r) => ({ ...r, supportClaims: r.supportClaims.map((c) => ({ ...c, ...eligible.get(c.id)! })) }));
  const context = buildBusinessAnswerContext({ claims, relationships: eligibleRelationships, maxCharacters: args.maxCharacters });
  const evidenceById = new Map<string, BusinessAnswerClaim>();
  for (const claim of [...claims, ...eligibleRelationships.flatMap((relationship) => relationship.supportClaims)]) {
    if (!evidenceById.has(claim.id)) evidenceById.set(claim.id, claim);
  }
  return {
    ...context,
    ineligibleRelationshipCount: relationships.length - eligibleRelationships.length,
    evidenceClaims: context.includedClaimIds.map((id) => evidenceById.get(id)!).filter(Boolean),
    evidenceRelationships: context.includedRelationshipIds
      .map((id) => eligibleRelationships.find((relationship) => relationship.id === id)!)
      .filter(Boolean),
    searchCount: plans.length,
    searchedDomains: domains,
    expandedDomains: additionalDomains,
    unexpandedDomains: domains.filter((domain) => domains.length > 1 && !additionalDomains.includes(domain)),
    emptySearches: plans.flatMap((plan, index) => results[index]!.length ? [] : [plan.topDomainHints]),
  };
}
