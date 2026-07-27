export const BUSINESS_OBJECT_KINDS = [
  'process',
  'responsibility_model',
  'rule_set',
  'reference_dataset',
  'conversation_model',
  'narrative_macro',
] as const;

export type BusinessObjectKind = (typeof BUSINESS_OBJECT_KINDS)[number];

export const BUSINESS_MODEL_SHAPES = [
  'process',
  'responsibilities',
  'ruleset',
  'reference',
  'conversation',
  'narrative',
] as const;

export type BusinessModelShape = (typeof BUSINESS_MODEL_SHAPES)[number];

export interface BusinessShapeDetailAdapter {
  readonly table: string;
  readonly requiredFields: readonly string[];
  readonly optionalFields: readonly string[];
  toPersistenceRow(elementId: string, detail: Readonly<Record<string, unknown>>): {
    row: Record<string, unknown> | null;
    errors: string[];
  };
  render(detail: Readonly<Record<string, unknown>>): string;
}

export interface BusinessShapeContract {
  readonly objectKind: BusinessObjectKind;
  readonly allowedElementKinds: readonly string[];
  readonly allowedRelationKinds: readonly string[];
  readonly primaryElementKinds: readonly string[];
  readonly primaryRelationKinds: readonly string[];
  readonly readInstruction: string;
  readonly extractionDirective: string;
  readonly mergePromptFragment: string;
  readonly detail: BusinessShapeDetailAdapter;
}

function adapter(
  table: string,
  requiredFields: readonly string[],
  optionalFields: readonly string[],
  requiredAnyFields: readonly string[] = [],
): BusinessShapeDetailAdapter {
  return {
    table,
    requiredFields,
    optionalFields,
    toPersistenceRow(elementId, detail) {
      const errors = requiredFields
        .filter((field) => {
          const value = detail[field];
          return typeof value !== 'string' || value.trim().length === 0;
        })
        .map((field) => `${table}.${field} is required`);
      const allowed = new Set([...requiredFields, ...optionalFields]);
      const unknown = Object.keys(detail).filter((field) => !allowed.has(field));
      errors.push(...unknown.map((field) => `${table}.${field} is not allowed`));
      if (
        requiredAnyFields.length > 0 &&
        !requiredAnyFields.some((field) => {
          const value = detail[field];
          return value === true || (typeof value === 'string' && value.trim().length > 0);
        })
      ) {
        errors.push(`${table} requires at least one of ${requiredAnyFields.join(', ')}`);
      }
      if (errors.length > 0) return { row: null, errors };
      return {
        row: Object.fromEntries([
          ['elementId', elementId],
          ...[...requiredFields, ...optionalFields]
            .filter((field) => detail[field] !== undefined)
            .map((field) => [field, detail[field]]),
        ]),
        errors: [],
      };
    },
    render(detail) {
      return [...requiredFields, ...optionalFields]
        .filter((field) => detail[field] !== undefined && detail[field] !== null)
        .map((field) => `${field}: ${String(detail[field])}`)
        .join(' · ');
    },
  };
}

export const BUSINESS_MODEL_SHAPE_REGISTRY = {
  process: {
    objectKind: 'process',
    allowedElementKinds: [
      'step',
      'decision',
      'approval_gate',
      'system_entry',
      'artifact',
      'terminal',
    ],
    allowedRelationKinds: ['sequence', 'handoff', 'branch', 'loop', 'exception'],
    primaryElementKinds: [],
    primaryRelationKinds: ['sequence', 'handoff', 'branch', 'loop', 'exception'],
    readInstruction:
      'Reconstruct steps, decisions, approvals, handoffs, branches, loops, and outcomes.',
    extractionDirective: 'Extract one canonical claim per transition, handoff, or branch.',
    mergePromptFragment:
      'Compare ordered steps, owners, branches, loops, systems, paths, and terminal outcomes.',
    detail: adapter(
      'business_process_details',
      ['nodeType'],
      ['laneLabel', 'presentationLabel'],
    ),
  },
  responsibilities: {
    objectKind: 'responsibility_model',
    allowedElementKinds: ['responsibility'],
    allowedRelationKinds: [],
    primaryElementKinds: ['responsibility'],
    primaryRelationKinds: [],
    readInstruction:
      'Identify roles and concrete owner-action-object responsibilities, including triggers and systems.',
    extractionDirective:
      'Extract one canonical claim per owner-action-object responsibility record.',
    mergePromptFragment:
      'Compare the role, action, object, trigger, required system, and resolved owner.',
    detail: adapter(
      'business_responsibility_details',
      ['role', 'action', 'object'],
      ['trigger', 'requiredSystem'],
    ),
  },
  ruleset: {
    objectKind: 'rule_set',
    allowedElementKinds: ['rule'],
    allowedRelationKinds: ['applicability', 'exception'],
    primaryElementKinds: ['rule'],
    primaryRelationKinds: ['applicability', 'exception'],
    readInstruction:
      'Identify scoped rules, conditions, requirements, effects, exceptions, and rule groups.',
    extractionDirective: 'Extract one canonical claim per rule, condition, effect, or exception.',
    mergePromptFragment: 'Compare scope, condition, effect, exception, and applicability.',
    detail: adapter('business_rule_details', ['scope', 'effect'], ['condition', 'exception']),
  },
  reference: {
    objectKind: 'reference_dataset',
    allowedElementKinds: ['attribute', 'relationship'],
    allowedRelationKinds: ['relationship'],
    primaryElementKinds: ['attribute', 'relationship'],
    primaryRelationKinds: ['relationship'],
    readInstruction:
      'Identify entities, attributes, values, and relationships without forcing sequence.',
    extractionDirective: 'Extract one canonical claim per attribute or entity relationship.',
    mergePromptFragment:
      'Compare entity type, constrained attribute key/value, and reference kind.',
    detail: adapter(
      'business_reference_details',
      ['entityType', 'attributeKey', 'attributeValue', 'referenceKind'],
      [],
    ),
  },
  conversation: {
    objectKind: 'conversation_model',
    allowedElementKinds: ['decision', 'assertion', 'open_question', 'problem', 'action_item'],
    allowedRelationKinds: [],
    primaryElementKinds: ['decision', 'assertion', 'open_question', 'problem', 'action_item'],
    primaryRelationKinds: [],
    readInstruction:
      'Identify decisions, assertions, disagreements, open questions, problems, and action items.',
    extractionDirective:
      'Extract one canonical claim per decision, assertion, open question, problem, or action item.',
    mergePromptFragment:
      'Compare decision state, disagreement, speaker, due date, action state, and meeting.',
    detail: adapter(
      'business_conversation_details',
      [],
      [
        'decisionStatus',
        'contested',
        'speaker',
        'dueDate',
        'actionStatus',
        'meetingReference',
      ],
      [
        'decisionStatus',
        'contested',
        'speaker',
        'dueDate',
        'actionStatus',
        'meetingReference',
      ],
    ),
  },
  narrative: {
    objectKind: 'narrative_macro',
    allowedElementKinds: ['asserted_fact', 'goal', 'constraint', 'risk', 'rationale'],
    allowedRelationKinds: [],
    primaryElementKinds: ['asserted_fact'],
    primaryRelationKinds: [],
    readInstruction: 'Identify explicit operational facts that do not fit another source shape.',
    extractionDirective: 'Extract one canonical claim per explicit operational fact.',
    mergePromptFragment: 'Compare the limited goal, constraint, risk, and rationale fields.',
    detail: adapter(
      'business_narrative_macro_details',
      ['macroKind'],
      ['goal', 'constraint', 'risk', 'rationale'],
    ),
  },
} as const satisfies Record<BusinessModelShape, BusinessShapeContract>;

export function validateBusinessShapeElement(input: {
  shape: string;
  elementKind: string;
  detail: Readonly<Record<string, unknown>>;
  elementId?: string;
}): { row: Record<string, unknown> | null; errors: string[] } {
  if (!BUSINESS_MODEL_SHAPES.includes(input.shape as BusinessModelShape)) {
    return { row: null, errors: [`Unknown business-model shape: ${input.shape}`] };
  }
  const contract = BUSINESS_MODEL_SHAPE_REGISTRY[input.shape as BusinessModelShape];
  if (!contract.allowedElementKinds.includes(input.elementKind as never)) {
    return {
      row: null,
      errors: [`${input.elementKind} is not allowed for shape ${input.shape}`],
    };
  }
  return contract.detail.toPersistenceRow(input.elementId ?? 'pending', input.detail);
}

export function validateBusinessShapeRelation(input: {
  shape: string;
  relationKind: string;
}): string[] {
  if (!BUSINESS_MODEL_SHAPES.includes(input.shape as BusinessModelShape)) {
    return [`Unknown business-model shape: ${input.shape}`];
  }
  const contract = BUSINESS_MODEL_SHAPE_REGISTRY[input.shape as BusinessModelShape];
  return contract.allowedRelationKinds.includes(input.relationKind as never)
    ? []
    : [`${input.relationKind} is not allowed for shape ${input.shape}`];
}
