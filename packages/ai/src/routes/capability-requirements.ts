import type { ModelCapability } from '../model-capabilities/types';
import type { ModelSlot } from './errors';

export type CapabilityRequirement =
  | { kind: 'capability'; field: keyof Pick<ModelCapability, 'vision' | 'thinking' | 'structuredOutputs' | 'strictJsonSchema' | 'deepSchemaAccepted' | 'adapterParamsSafe' | 'toolCalling' | 'outputCap' | 'pdf' | 'promptCaching'>; label: string }
  | { kind: 'context'; minExclusive: number; label: string };

export function requiredCapabilitiesFor(slot: ModelSlot): CapabilityRequirement[] {
  switch (slot) {
    case 'interview':
      return [
        { kind: 'capability', field: 'toolCalling', label: 'tools' },
        { kind: 'capability', field: 'structuredOutputs', label: 'structured outputs' },
        { kind: 'capability', field: 'vision', label: 'vision' },
        { kind: 'context', minExclusive: 100_000, label: 'context > 100K' },
      ];
    case 'extraction':
      return [
        { kind: 'capability', field: 'structuredOutputs', label: 'structured outputs' },
        { kind: 'context', minExclusive: 100_000, label: 'context > 100K' },
      ];
    case 'synthesis':
      return [
        { kind: 'context', minExclusive: 400_000, label: 'context > 400K' },
        { kind: 'capability', field: 'structuredOutputs', label: 'structured outputs' },
        { kind: 'capability', field: 'thinking', label: 'reasoning' },
        { kind: 'capability', field: 'outputCap', label: 'output cap' },
      ];
    case 'vision':
      return [{ kind: 'capability', field: 'vision', label: 'vision' }];
    case 'workflow_read':
      return [
        { kind: 'capability', field: 'strictJsonSchema', label: 'strict JSON Schema enforcement' },
        { kind: 'capability', field: 'deepSchemaAccepted', label: 'deep Oracle schema accepted' },
        { kind: 'capability', field: 'adapterParamsSafe', label: 'adapter params accepted by model' },
        { kind: 'context', minExclusive: 100_000, label: 'context > 100K' },
      ];
    case 'model_merge':
      return [{ kind: 'capability', field: 'strictJsonSchema', label: 'strict JSON Schema enforcement' }];
    case 'macro':
      // Macro understanding (source outlines, relationship extraction, coverage
      // audits) emits deep nested JSON. It MUST have real structured-output
      // support — this is the exact capability whose absence made the Qwen
      // json_object route throw AllCandidatesFailedError. See AGENT_ERROR_LOG.md.
      return [
        { kind: 'capability', field: 'strictJsonSchema', label: 'strict JSON Schema enforcement' },
        { kind: 'capability', field: 'deepSchemaAccepted', label: 'deep Oracle schema accepted' },
        { kind: 'capability', field: 'adapterParamsSafe', label: 'adapter params accepted by model' },
      ];
    case 'general':
    case 'translation':
      return [];
  }
}

export function missingRequirements(
  model: Pick<
    ModelCapability,
    | 'provider'
    | 'vision'
    | 'thinking'
    | 'structuredOutputs'
    | 'strictJsonSchema'
    | 'deepSchemaAccepted'
    | 'adapterParamsSafe'
    | 'toolCalling'
    | 'outputCap'
    | 'pdf'
    | 'promptCaching'
    | 'contextLength'
  >,
  slot: ModelSlot,
): string[] {
  const missing: string[] = [];
  for (const req of requiredCapabilitiesFor(slot)) {
    if (req.kind === 'capability') {
      if (!model[req.field]) missing.push(req.label);
    } else if (model.contextLength == null || model.contextLength <= req.minExclusive) {
      missing.push(req.label);
    }
  }
  return missing;
}
