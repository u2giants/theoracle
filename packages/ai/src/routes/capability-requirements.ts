import type { ModelCapability } from '../model-capabilities/types';
import type { ModelSlot } from './errors';

export type CapabilityRequirement =
  | { kind: 'capability'; field: keyof Pick<ModelCapability, 'vision' | 'thinking' | 'structuredOutputs' | 'toolCalling' | 'outputCap' | 'pdf' | 'promptCaching'>; label: string }
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
    case 'general':
    case 'translation':
      return [];
  }
}

export function missingRequirements(
  model: Pick<
    ModelCapability,
    | 'vision'
    | 'thinking'
    | 'structuredOutputs'
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
