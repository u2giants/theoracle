import type { Observation, WorkflowModel } from '@/lib/operating-model-types';
export function WorkflowCanvas({ workflow, observations = [] }: { workflow: WorkflowModel; observations?: Observation[] }) {
  const nodes = [...workflow.steps.map(step => ({ id: step.step_id, label: step.label, kind: step.kind })), ...workflow.gateways.map(gateway => ({ id: gateway.gateway_id, label: gateway.kind.replaceAll('_', ' '), kind: 'gateway' }))];
  const positions = new Map(nodes.map((node, index) => [node.id, { x: 120 + (index % 2) * 260, y: 55 + Math.floor(index / 2) * 100 }]));
  const height = Math.max(140, Math.ceil(nodes.length / 2) * 100);
  const byObservation = new Map(observations.map(observation => [observation.observation_id, observation]));
  return <section className="rounded-xl border border-slate-200 bg-white p-5">
    <h2 className="font-semibold">{workflow.workflow_id}</h2>
    <p className="text-sm text-slate-600">Reported map · {workflow.scope} · {workflow.completeness}</p>
    <svg viewBox={`0 0 520 ${height}`} role="img" aria-label={`Reported workflow ${workflow.workflow_id}`} className="mt-4 w-full">
      {workflow.transitions.map(edge => {
        const from = positions.get(edge.from_id); const to = positions.get(edge.to_id);
        if (!from || !to) return null;
        return <g key={edge.transition_id}><line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={edge.rework ? '#b45309' : '#64748b'} strokeWidth="2" strokeDasharray={edge.rework ? '5 4' : undefined} /><text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 7} fontSize="10" textAnchor="middle">{edge.transition_id}</text></g>;
      })}
      {nodes.map(node => { const position = positions.get(node.id)!; return <g key={node.id}><rect x={position.x - 105} y={position.y - 22} width="210" height="44" rx={node.kind === 'gateway' ? 3 : 12} fill={node.kind === 'gateway' ? '#e0e7ff' : '#f8fafc'} stroke="#94a3b8" /><text x={position.x} y={position.y + 4} fontSize="11" textAnchor="middle">{node.label.slice(0, 32)}</text><title>{node.label} ({node.id})</title></g>; })}
    </svg>
    <ul className="mt-4 space-y-2 text-sm">{workflow.transitions.map(edge => {
      const condition = workflow.conditions.find(item => item.condition_id === edge.condition_id);
      const evidence = edge.support.observation_ids.flatMap(id => byObservation.get(id)?.evidence ?? []);
      return <li key={edge.transition_id}>{edge.from_id} → {edge.to_id}{edge.rework ? ' · rework' : ''}{condition ? ` · ${condition.wording} (${condition.applicability})` : ''}<details><summary>Source support</summary>{evidence.map((quote, index) => <blockquote key={index} className="my-2 border-l-2 pl-3"><p>{quote.quote}</p><small>Source {quote.ref.source_id}, revision {quote.ref.revision}, characters {quote.start}–{quote.end}</small></blockquote>)}</details></li>;
    })}</ul>
  </section>;
}
