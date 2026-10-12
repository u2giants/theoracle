export interface Evidence { ref: { source_id: string; revision: number }; start: number; end: number; quote: string }
export interface Finding { finding_id: string; kind: string; text: string; status: string; origin: string; evidence_refs?: Evidence[] }
export interface Observation { observation_id: string; evidence: Evidence[] }
export interface WorkflowModel {
  workflow_id: string; scope: string; completeness: string;
  steps: Array<{ step_id: string; label: string; kind: string; role_id?: string; support: { observation_ids: string[] } }>;
  gateways: Array<{ gateway_id: string; kind: string; support: { observation_ids: string[] } }>;
  transitions: Array<{ transition_id: string; from_id: string; to_id: string; condition_id?: string; rework: boolean; support: { observation_ids: string[] } }>;
  conditions: Array<{ condition_id: string; wording: string; applicability: string }>;
}
export interface ProcessModel { process_id: string; label: string; scope: string; completeness: string; workflow_ids: string[] }
export interface OperatingModel { state: string; processes?: ProcessModel[]; observations?: Observation[]; workflows?: WorkflowModel[]; interfaces?: unknown[]; findings?: Finding[]; reviewer_quarantine?: Finding[]; citations?: Evidence[]; analysis?: { state: string; measurements?: Record<string, string | number>; actual_data_acceptance?: string }; coverage_state?: string; declared_population?: string[]; continuation?: unknown; error?: string }
