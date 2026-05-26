// R10 — Evals dashboard placeholder.
//
// docs/oracle/06-evaluation-framework.md mandates that initial evals are
// run via CLI scripts, not through a web UI. This page is the placeholder
// the spec calls for (task 6: "Add eval results dashboard placeholder if
// evals not implemented yet").

export const dynamic = 'force-dynamic';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default async function AdminAIEvalsPage() {
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Eval results</h1>
        <p className="text-sm text-muted-foreground">
          Placeholder. The eval framework intentionally runs from CLI scripts (no web UI)
          during the initial retrofit — see{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">
            docs/oracle/06-evaluation-framework.md
          </code>
          .
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Current smoke gates (run locally or in CI)</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-xs">
            <thead className="border-b text-left">
              <tr>
                <th className="py-2">Phase</th>
                <th>Command</th>
                <th className="text-right">Assertions</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b">
                <td className="py-2">R2 — OracleAIClient pipeline</td>
                <td>
                  <code className="font-mono">pnpm --filter @oracle/ai verify:r2</code>
                </td>
                <td className="text-right">16</td>
              </tr>
              <tr className="border-b">
                <td className="py-2">R5 — Quote validator + promotion decider</td>
                <td>
                  <code className="font-mono">pnpm --filter @oracle/engines verify:r5</code>
                </td>
                <td className="text-right">33</td>
              </tr>
              <tr className="border-b">
                <td className="py-2">R5.5 — Entity resolver + taxonomy validator</td>
                <td>
                  <code className="font-mono">pnpm --filter @oracle/engines verify:r5.5</code>
                </td>
                <td className="text-right">45</td>
              </tr>
              <tr className="border-b">
                <td className="py-2">R6 — Circuit breaker + domain mapping</td>
                <td>
                  <code className="font-mono">pnpm --filter @oracle/engines verify:r6</code>
                </td>
                <td className="text-right">30</td>
              </tr>
              <tr className="border-b">
                <td className="py-2">R7 — Cache profitability + estimate</td>
                <td>
                  <code className="font-mono">pnpm --filter @oracle/engines verify:r7</code>
                </td>
                <td className="text-right">19</td>
              </tr>
              <tr className="border-b">
                <td className="py-2">R9 — Synthesis diff validator</td>
                <td>
                  <code className="font-mono">pnpm --filter @oracle/engines verify:r9</code>
                </td>
                <td className="text-right">21</td>
              </tr>
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted-foreground">
            Total: 164 deterministic assertions across the AI retrofit pure-function
            modules. All run in milliseconds without API keys, database, or network
            access.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Why no web UI yet</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            Per <code className="rounded bg-muted px-1 py-0.5 text-xs">06-evaluation-framework.md</code>,
            the first goal is to prove extraction, validation, retrieval, and synthesis quality
            without creating a dashboard project that distracts from the core pipeline.
          </p>
          <p>
            External eval tooling (Braintrust, LangSmith, Promptfoo) can be reconsidered after:
          </p>
          <ol className="ml-4 list-decimal space-y-1">
            <li>candidate-before-claim pipeline works (✓ done, R6 / R7)</li>
            <li>OracleAIClient / provider adapters work (✓ done, R2 / R6–R9)</li>
            <li>context packs and usage logging work (✓ done, R3)</li>
            <li>at least 5 local extraction fixtures exist (⬜ pending)</li>
            <li>costs and validation failures are measurable (✓ R10 ships the metrics now)</li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
