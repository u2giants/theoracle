import assert from 'node:assert/strict';
import {
  assertEvidenceLocale,
  assertReconciledBusinessAnswer,
  hasBusinessAnswerIntent,
  providerIndependenceFamily,
  renderReconciledBusinessAnswer,
  shouldReconcileBusinessAnswer,
  validateReconciliation,
  validateSemanticReview,
  type BusinessAnswerReconciliation,
} from '../business-answer-reconciliation';

const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const claims = [
  { id: id(1), summary: 'Changed reorders require PPS submission.', claimKind: 'rule' },
  { id: id(2), summary: 'Rush requests still require expedited licensor approval.', claimKind: 'exception' },
  { id: id(3), summary: 'China sourcing confirms factory construction constraints.', claimKind: 'responsibility' },
];
const relationships = [{
  id: id(99),
  summary: 'Approved relationship: China constraints are checked before the PPS gate.',
  supportClaims: [claims[0]!, claims[2]!],
}];
const reconciliation: BusinessAnswerReconciliation = {
  questionFacets: [
    { id: 'facet-1', label: 'PPS and reorder rule', status: 'documented', claimIds: [id(1)] },
    { id: 'facet-2', label: 'Rush exception', status: 'documented', claimIds: [id(2)] },
    { id: 'facet-3', label: 'China handoff', status: 'partial', claimIds: [id(3)] },
  ],
  claimAssessments: claims.map((claim, index) => ({
    claimId: claim.id, disposition: 'must_address' as const,
    categories: [index === 1 ? 'exception' as const : index === 2 ? 'owner' as const : 'condition' as const],
    reason: 'Directly answers a requested facet.',
  })),
  connections: [{ relationshipId: null, claimIds: [id(1), id(3)], statement: 'China constraints must be reconciled before the PPS gate.', status: 'inference' }],
  gaps: [{ id: 'gap-1', facet: 'China handoff', consideredClaimIds: [id(3)], reason: 'The supplied evidence does not identify the final handoff owner.' }],
};
const coverage = validateReconciliation(reconciliation, claims.map((claim) => claim.id), relationships);
assert.deepEqual(coverage.mustAddressClaimIds, claims.map((claim) => claim.id));
const rendered = renderReconciledBusinessAnswer({ reconciliation, claims, relationships, locale: 'en', evidenceTruncated: false });
for (const claim of claims) assert(rendered.includes(`${claim.summary} [claim:${claim.id}]`));
assert(rendered.includes('[gap-1]'));
assert(rendered.includes('Interpretation:'));
assert(!rendered.includes('###'));
assert(!rendered.includes('**'));
assertReconciledBusinessAnswer({ text: rendered, includedClaimIds: claims.map((claim) => claim.id), ...coverage });

const invalidAbsent = structuredClone(reconciliation);
invalidAbsent.questionFacets[0] = { ...invalidAbsent.questionFacets[0]!, status: 'not_documented' };
assert.throws(() => validateReconciliation(invalidAbsent, claims.map((claim) => claim.id), relationships), /calls supplied evidence absent/);
const skipped = structuredClone(reconciliation);
skipped.claimAssessments.pop();
assert.throws(() => validateReconciliation(skipped, claims.map((claim) => claim.id), relationships), /skipped 1 supplied claims/);
const outsideFacet = structuredClone(reconciliation);
outsideFacet.questionFacets[2]!.claimIds = [];
outsideFacet.questionFacets[2]!.status = 'not_documented';
assert.throws(() => validateReconciliation(outsideFacet, claims.map((claim) => claim.id), relationships), /mandatory claims outside/);
const emptyPartial = structuredClone(reconciliation);
emptyPartial.questionFacets[2]!.claimIds = [];
assert.throws(() => validateReconciliation(emptyPartial, claims.map((claim) => claim.id), relationships), /partial without any established evidence/);
const canonicalAbsenceClaims = claims.map((claim, index) => index === 0
  ? { ...claim, summary: 'We do not have a separate PPS bypass.' }
  : claim);
const canonicalAbsenceAnswer = renderReconciledBusinessAnswer({
  reconciliation, claims: canonicalAbsenceClaims, relationships, locale: 'en', evidenceTruncated: false,
});
assert.doesNotThrow(() => assertReconciledBusinessAnswer({
  text: canonicalAbsenceAnswer, includedClaimIds: claims.map((claim) => claim.id), ...coverage,
}));
assert.throws(() => assertReconciledBusinessAnswer({
  text: `Rule [claim:${id(1)}]`, includedClaimIds: claims.map((claim) => claim.id),
  mustAddressClaimIds: [id(1), id(2)], gapIds: [],
}), /omitted 1 mandatory/);

validateSemanticReview({ pass: true, violations: [] }, claims.map((claim) => claim.id));
assert.throws(() => validateSemanticReview({ pass: true, violations: [{
  type: 'false_absence', sentence: 'Missing.', claimIds: [id(1)], repairInstruction: 'Use supplied evidence.',
}] }, claims.map((claim) => claim.id)), /contradicts/);
assert.equal(shouldReconcileBusinessAnswer('Explain the licensing handoff and exceptions.', 3), true);
assert.equal(shouldReconcileBusinessAnswer('Thanks, that helps.', 3), false);
assert.equal(shouldReconcileBusinessAnswer('Explain the process.', 1), true);
assert.equal(hasBusinessAnswerIntent('Explain the process.'), true);
assert.equal(hasBusinessAnswerIntent('Who has responsibility for licensing approvals?'), true);
assert.equal(hasBusinessAnswerIntent('Sales were strong with this customer.'), true);
assert.equal(hasBusinessAnswerIntent('Thanks, got it.'), false);
assert.equal(providerIndependenceFamily('google'), 'gemini');
assert.equal(providerIndependenceFamily('vertex'), 'gemini');
assert.equal(providerIndependenceFamily('anthropic'), 'anthropic');
assert.throws(() => providerIndependenceFamily(undefined), /Provider identity is required/);
assert.equal(shouldReconcileBusinessAnswer('这个审批流程如何影响中国团队？', 3), true);
assert.equal(shouldReconcileBusinessAnswer('Hello, how are you?', 3), false);
const chineseReconciliation = structuredClone(reconciliation);
chineseReconciliation.questionFacets = [
  { ...chineseReconciliation.questionFacets[0]!, label: '补货订单的样品审批规则' },
  { ...chineseReconciliation.questionFacets[1]!, label: '加急订单例外' },
  { ...chineseReconciliation.questionFacets[2]!, label: '中国团队交接', },
];
chineseReconciliation.connections[0]!.statement = '中国团队的限制需要在样品审批前解决。';
chineseReconciliation.gaps[0]!.facet = '中国团队交接';
validateReconciliation(chineseReconciliation, claims.map((claim) => claim.id), relationships, 'zh-CN');
const chineseClaims = claims.map((claim, index) => ({ ...claim, localized: true, summary: ['变更后的补货订单需要提交产前样。', '加急请求仍然需要许可方审批。', '中国采购团队确认工厂结构限制。'][index]! }));
const chineseRelationships = [{ ...relationships[0]!, summary: '中国团队的限制需要在产前样审批之前完成检查。', supportClaims: [chineseClaims[0]!, chineseClaims[2]!] }];
assertEvidenceLocale(chineseClaims, 'zh-CN');
assert.throws(() => assertEvidenceLocale(claims, 'zh-CN'), /missing 3 approved claim translations/);
const chinese = renderReconciledBusinessAnswer({ reconciliation: chineseReconciliation, claims: chineseClaims, relationships: chineseRelationships, locale: 'zh-CN', evidenceTruncated: false });
assert(chinese.includes('有证据支持的关联:'));
assert(chinese.includes('当前检索到的有限证据只能部分说明这一方面。'));
assert(chinese.includes('基于证据的解释:'));
assert.throws(() => validateReconciliation(reconciliation, claims.map((claim) => claim.id), relationships, 'zh-CN'), /did not preserve/);
const mostlyEnglishChinese = structuredClone(chineseReconciliation);
mostlyEnglishChinese.questionFacets[0]!.label = 'PPS approval workflow 中国';
assert.throws(() => validateReconciliation(mostlyEnglishChinese, claims.map((claim) => claim.id), relationships, 'zh-CN'), /did not preserve/);
const unboundedAbsenceLabel = structuredClone(reconciliation);
unboundedAbsenceLabel.questionFacets[0]!.label = 'No documented process';
assert.throws(() => validateReconciliation(unboundedAbsenceLabel, claims.map((claim) => claim.id), relationships), /employee-visible label/);
const unboundedAbsenceConnection = structuredClone(reconciliation);
unboundedAbsenceConnection.connections[0]!.statement = 'We do not have a documented handoff.';
assert.throws(() => validateReconciliation(unboundedAbsenceConnection, claims.map((claim) => claim.id), relationships), /outside a bounded facet gap/);
const documented = structuredClone(reconciliation);
documented.connections = [{
  relationshipId: relationships[0]!.id,
  claimIds: [id(1), id(3)],
  statement: 'Model-authored wording must not be served.',
  status: 'documented',
}];
validateReconciliation(documented, claims.map((claim) => claim.id), relationships);
const documentedAnswer = renderReconciledBusinessAnswer({ reconciliation: documented, claims, relationships, locale: 'en', evidenceTruncated: false });
assert(documentedAnswer.includes(relationships[0]!.summary));
assert(!documentedAnswer.includes('Model-authored wording must not be served.'));
const incompleteRelationship = structuredClone(documented);
incompleteRelationship.connections[0]!.claimIds = [id(1)];
assert.throws(() => validateReconciliation(incompleteRelationship, claims.map((claim) => claim.id), relationships), /cite every premise/);
const inventedRelationship = structuredClone(documented);
inventedRelationship.connections[0]!.relationshipId = id(98);
assert.throws(() => validateReconciliation(inventedRelationship, claims.map((claim) => claim.id), relationships), /unknown approved relationship/);
const contradictory = structuredClone(reconciliation);
contradictory.claimAssessments[0]!.disposition = 'not_relevant';
assert.throws(() => validateReconciliation(contradictory, claims.map((claim) => claim.id), relationships), /classified as not relevant/);
const duplicateLabel = structuredClone(reconciliation);
duplicateLabel.questionFacets[1]!.label = duplicateLabel.questionFacets[0]!.label;
assert.throws(() => validateReconciliation(duplicateLabel, claims.map((claim) => claim.id), relationships), /duplicated facet label/);
const noEvidence = structuredClone(reconciliation);
noEvidence.questionFacets = [{ id: 'facet-1', label: 'Unknown policy', status: 'not_documented', claimIds: [] }];
noEvidence.claimAssessments = claims.map((claim) => ({ claimId: claim.id, disposition: 'not_relevant', categories: ['background'], reason: 'Does not answer the question.' }));
noEvidence.connections = [];
noEvidence.gaps = [{ id: 'gap-1', facet: 'Unknown policy', consideredClaimIds: claims.map((claim) => claim.id), reason: 'Bounded evidence does not answer this facet.' }];
assert.doesNotThrow(() => validateReconciliation(noEvidence, claims.map((claim) => claim.id), relationships));
const truncatedAnswer = renderReconciledBusinessAnswer({ reconciliation, claims, relationships, locale: 'en', evidenceTruncated: true });
assert(truncatedAnswer.startsWith('Evidence scope:'));
console.log('business-answer-reconciliation: PASS (canonical rendering, full accounting, bounded gaps, semantic gate, intent routing; 0 skipped).');
